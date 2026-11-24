# JobParameters at Launch

In Spring Batch, `JobParameters` is the collection of input values passed in each time a Job is launched. When calling `JobLauncher.run(job, jobParameters)`, the application supplies the Job to run together with the parameters that describe that run, such as the business date, the input file code, the data range, or the customer code.

JobParameters have two important roles. First, they provide the data the Job and Steps use to do their work. Second, the parameters marked as **identifying** take part in identifying the `JobInstance`. Therefore, the choice of parameters directly affects whether a launch is treated as a new run or as a restart of an existing JobInstance.

## 1. How does JobLauncher receive JobParameters?

`JobLauncher` is the API for launching a Job. The basic method takes two arguments: the Job definition and the JobParameters object.

```java
JobExecution run(Job job, JobParameters jobParameters)
```

For example, the application has a Job that calculates daily billing. When launching, the service creates the `businessDate` parameter and passes it to the JobLauncher:

```java
@Service
public class BillingJobService {

    private final JobLauncher jobLauncher;
    private final Job dailyBillingJob;

    public BillingJobService(
            JobLauncher jobLauncher,
            Job dailyBillingJob) {
        this.jobLauncher = jobLauncher;
        this.dailyBillingJob = dailyBillingJob;
    }

    public JobExecution launch(LocalDate businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addLocalDate("businessDate", businessDate, true)
                .toJobParameters();

        return jobLauncher.run(dailyBillingJob, parameters);
    }
}
```

In the example, `businessDate` is an identifying parameter. If the service is called multiple times with the same date and the same Job name, those calls target the same JobInstance. Whether the launch succeeds also depends on the existing execution state: the instance is running, completed, or failed.

`JobLauncher.run()` returns a `JobExecution`, which contains information about the execution that was created. You should not assume that receiving this object means the Job has completed. With a synchronous launcher, the call usually returns only after the Job finishes. With an asynchronous launcher, the call may return when the Job has just started or has been placed into the executor. How it runs depends on the JobLauncher configuration.

## 2. Creating JobParameters with JobParametersBuilder

`JobParametersBuilder` helps create a `JobParameters` object clearly. Each parameter has a name, a value, and a flag that determines whether it takes part in identifying the JobInstance.

An example combining several data types:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("inputFile", "customers-20261115.csv", true)
        .addLong("requestedBy", 1024L, false)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

In the example:

- `businessDate` identifies the business period to be processed.
- `inputFile` identifies the data source of the run.
- `requestedBy` records who requested the Job run.
- `notificationEmail` specifies where to send notifications.

The first two parameters are identifying (`true`); the last two are non-identifying (`false`). When the requester or the notification address changes, the JobInstance stays the same as long as the identifying parameters do not change.

Commonly used builder methods include:

| Method | Value type | Example |
|---|---|---|
| `addString()` | String | File code, processing period name |
| `addLong()` | Long integer | ID, sequence number |
| `addDouble()` | Floating-point number | Threshold or numeric value |
| `addDate()` | `java.util.Date` | A point in time using the legacy API |
| `addLocalDate()` | `java.time.LocalDate` | Business date |
| `addLocalDateTime()` | `java.time.LocalDateTime` | Business date and time |

The specific types and overloads depend on the Spring Batch version. In versions that support it, the overload with a boolean parameter lets you specify identifying explicitly. Use data types that fit the business meaning, and avoid turning every value into a string if the Job needs to compare, compute, or validate them.

After calling `toJobParameters()`, the application obtains a `JobParameters` object to pass to the JobLauncher. Build a new object for each launch; the builder helps gather the parameters before creating the input object.

## 3. Identifying and non-identifying parameters

This is the most important point when designing JobParameters.

### Identifying parameters

Identifying parameters are used together with the Job name to identify the `JobInstance`. For example, the Job `dailyBillingJob` has the identifying parameter `businessDate=2026-11-15`. The combination of the Job name and the identifying parameters identifies one instance for that day's billing period.

If you change an identifying parameter, Spring Batch treats the new combination as a different JobInstance. For example:

```text
dailyBillingJob + businessDate=2026-11-15
        -> JobInstance A

dailyBillingJob + businessDate=2026-11-16
        -> JobInstance B
```

This is appropriate when the parameter represents an independent unit of work, such as a ledger closing date, an input file code, or a payment period code.

### Non-identifying parameters

Non-identifying parameters are stored with the execution and can be read within the Job, but they do not take part in creating the JobInstance identity. Changing a non-identifying value does not create a new JobInstance by itself.

For example, `requestedBy` or `notificationEmail` are usually just operational information. Two launches with the same `businessDate` and `inputFile` but different `requestedBy` still target the same JobInstance.

You should not mark a value as non-identifying if it can change business data in a way that is incompatible across restarts. For example, if `exchangeRate` determines the amount written to the database, changing the exchange rate in a restart while keeping the same JobInstance can cause part of the data to be calculated at the old rate and the rest at the new rate. If a value determines the business content of the run, you should usually put it in the identifying set or store an immutable snapshot tied to the JobInstance.

### Comparison table

| Criterion | Identifying | Non-identifying |
|---|---|---|
| Takes part in identifying the JobInstance | Yes | No |
| Does changing the value create a new instance? | Yes | No |
| Use for restarting the same instance | Must stay unchanged | Can change depending on the API and process, but business consistency must be ensured |
| Suitable examples | Business date, file code, reconciliation period | Requester, notification address, tracking label |

## 4. JobParameters determine the JobInstance and restart

Spring Batch distinguishes `JobInstance` from `JobExecution`:

- `JobInstance` represents a logical run, identified by the Job name and the identifying parameters.
- `JobExecution` represents one specific execution of a JobInstance.

A JobInstance can have multiple JobExecutions if a previous run failed or was stopped and was then restarted.

```text
Job: dailyBillingJob
Identifying parameter: businessDate=2026-11-15
                   |
                   v
             JobInstance
                   |
          +--------+--------+
          |                 |
          v                 v
    JobExecution 1     JobExecution 2
       FAILED            COMPLETED
          |                 ^
          +---- restart ----+
```

When restarting, the application usually sends the same Job name and the same identifying parameters again to target the old JobInstance. If you add a new timestamp as an identifying parameter on each retry, Spring Batch creates a new JobInstance and treats this as new work from the beginning, not as a restart of the failed instance.

Some common results when launching:

| JobInstance state | Common result |
|---|---|
| Does not exist yet | Spring Batch creates a new JobInstance and JobExecution |
| Has a running execution | May receive `JobExecutionAlreadyRunningException` |
| Previous execution is COMPLETED | May receive `JobInstanceAlreadyCompleteException` |
| Previous execution is FAILED or STOPPED | Can be restarted if the Job and Step allow it |
| The Job does not allow restart | May receive `JobRestartException` |
| Invalid parameters | May receive `JobParametersInvalidException` |

The specific exceptions also depend on the state, the validator, and the JobRepository configuration. The application should handle them to return an appropriate operational message instead of treating every launch error as a data-processing error inside a Step.

## 5. Reading JobParameters inside the Job and Step

JobParameters can be accessed through the `StepExecution` or the `ChunkContext` while the Step runs. With a Tasklet, you can get the parameters from the `StepContribution`:

```java
@Bean
@StepScope
Tasklet billingTasklet() {
    return (contribution, chunkContext) -> {
        LocalDate businessDate = (LocalDate) chunkContext
                .getStepContext()
                .getJobParameters()
                .get("businessDate");

        // Perform processing for businessDate.
        return RepeatStatus.FINISHED;
    };
}
```

In a Spring Batch application, `@StepScope` allows a bean to be instantiated within the scope of a StepExecution, so it can access the run's parameters. You need to make sure the data type you retrieve matches the type that was put into the JobParameters.

For a reader or writer, you can use late binding through `@Value`:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

Here `inputFile` is taken from the JobParameters of the current JobExecution. `@StepScope` is very important because the parameter value is only available when the Step executes; a singleton bean created at application startup cannot know the parameters of a future launch on its own.

If a parameter is taken from a file or an external source, you need to check access permissions, the path, the format, and the existence of the file before processing. You should not blindly trust values sent by the API or the operator.

## 6. Validating JobParameters before processing

JobParameters are the input of the Job, so they need to be validated before work begins. A Job may need a valid business date, file code, or data range. If a parameter is missing or a value is inappropriate, you should reject the launch early to avoid creating a failed execution after it has already taken up resources.

Spring Batch provides `JobParametersValidator`. You can use the default validator or implement your own business rules.

An example validator that requires `businessDate` and `inputFile`:

```java
public class BillingParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters.getLocalDate("businessDate") == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }
    }
}
```

Attach the validator to the Job when building it:

```java
@Bean
Job dailyBillingJob(
        JobRepository jobRepository,
        Step billingStep,
        BillingParametersValidator validator) {

    return new JobBuilder("dailyBillingJob", jobRepository)
            .validator(validator)
            .start(billingStep)
            .build();
}
```

The validator should check the validity of the parameters at the input level: whether they are required, the data type, the value domain, and the relationships between parameters. Rules that depend on data that changes over time may need additional checks inside the Step to avoid drawing the wrong conclusion at launch time.

## 7. Using JobParametersIncrementer when you need the next instance

In some processes, a Job needs to be run many times without a natural business parameter such as a date or file code. Spring Batch supports `JobParametersIncrementer` to create the parameter set for the next instance. A familiar example is `RunIdIncrementer`, which uses an incrementing `run.id` parameter.

```java
@Bean
Job reportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("reportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

The incrementer is used by mechanisms that require the next instance, such as `JobOperator.startNextInstance()`. It does not automatically change the parameters when the application calls `JobLauncher.run(job, parameters)` directly. With `JobLauncher.run()`, the application is responsible for building the JobParameters to pass.

You should not use `RunIdIncrementer` to dodge a restart error. Each new `run.id` creates a new JobInstance if that parameter is identifying; the Job may then reprocess the data from the beginning. Use an incrementer only when the business truly requires a new logical run.

## 8. Designing stable and safe JobParameters

A good set of JobParameters needs to describe the scope of work clearly and support recovery when needed.

### Choose identifying parameters by business unit

Determine what makes one run different from another. For a reconciliation Job, it could be the reconciliation date and the data source code. For an import Job, it could be the file code or the file version. Do not choose an identifying parameter just because it is convenient for generating a unique value.

### Avoid arbitrary timestamps

Adding `LocalDateTime.now()` or a UUID to the identifying parameters on every launch makes each call create a different instance. When the caller retries because of a timeout, the application may reprocess all the data. If the goal is to prevent duplicate requests, use a stable request ID or an idempotency key that is stored and checked explicitly, instead of generating a new ID on each retry.

### Keep the input immutable across restarts

If JobParameters contain a file path, the content at that path needs to stay stable throughout the run and any restarts. If the file is replaced midway, the checkpoint may point to a position that is no longer correct. You can use versioned file names, a checksum, or store an immutable copy of the input data.

### Do not pass secrets in JobParameters

JobParameters are usually stored in the metadata repository to support history and restart. Therefore, you should not pass passwords, access tokens, or secret information directly into parameters. Pass a reference code to the secret or to a secure configuration, and then retrieve the secret value from a secret manager or the application's security mechanism when needed.

### Control size and format

Avoid passing large payloads or entire lists of records in JobParameters. Pass only identifiers, ranges, or references to the data. Large data should live in a file, a database, or object storage; JobParameters should contain only the information the Job needs to find the right source.

## 9. Example of a launch flow from an API

An API can accept a request to run a report for a given day. The controller does basic request validation, and the service builds the JobParameters and calls the JobLauncher:

```java
@RestController
@RequestMapping("/reports")
public class ReportController {

    private final JobLauncher jobLauncher;
    private final Job dailyReportJob;

    public ReportController(
            JobLauncher jobLauncher,
            Job dailyReportJob) {
        this.jobLauncher = jobLauncher;
        this.dailyReportJob = dailyReportJob;
    }

    @PostMapping
    public ResponseEntity<String> launch(
            @RequestParam LocalDate businessDate) throws Exception {

        JobParameters parameters = new JobParametersBuilder()
                .addLocalDate("businessDate", businessDate, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(
                dailyReportJob, parameters);

        return ResponseEntity.accepted().body(
                "Job execution id: " + execution.getId());
    }
}
```

The example returns HTTP `202 Accepted` to indicate that the request has been accepted. This is appropriate when the Job runs asynchronously or may take a long time. A separate status endpoint can use JobExplorer to return the JobExecution status to the client. If the JobLauncher runs synchronously, the controller may have to wait for the Job to complete before returning the response; in that case you need to consider timeouts and configure the launcher appropriately.

In production, the API needs to handle the case where a Job for the same day is already running or has already completed. It can return an appropriate HTTP code and the existing status information instead of treating launch exceptions as unclassified server errors.

## 10. Common errors when passing JobParameters

**Creating a new timestamp on every retry:** this creates a new JobInstance, defeats the purpose of restart, and may cause data to be reprocessed.

**Marking all parameters as identifying:** operational information such as the requester or the notification address can create unnecessary new JobInstances.

**Marking a business value as non-identifying:** a restart may use a different value than the first run, leading to inconsistent results across chunks.

**Passing the wrong data type:** a value read as a different type from the stored one can cause conversion or casting errors. You need to keep parameter types consistent between where you launch and where you read.

**Putting large data or secrets into parameters:** the metadata repository may store these values, causing metadata bloat or exposing sensitive information.

**Believing the incrementer runs automatically when calling JobLauncher:** `JobLauncher.run()` uses exactly the parameter set passed in; if you need a new instance, the caller must create appropriate parameters or use the `startNextInstance` mechanism.

**Skipping input validation:** the Job may start and then fail right away in a Step because of missing parameters or invalid data. A validator helps detect errors within the scope of parameters early.

## Conclusion

When launching a Job, the application passes `JobParameters` into `JobLauncher.run()`. This parameter set both provides input for the work and identifies the JobInstance through the values marked identifying. Choose identifying parameters by business unit, use non-identifying parameters for supporting information, validate data before running, and keep values that affect results stable across restarts. When designed correctly, JobParameters help distinguish a new run from a restart, support execution monitoring, and limit unintended duplicate processing.
