# Default Parameters and Determinism

In Spring Batch, `JobParameters` provides the input data for a Job launch. Some parameters may be passed in by a scheduler, the command line, or an API; others may be assigned default values by the application when the caller omits them. How these values are chosen and normalized directly affects the **determinism of the JobInstance**.

Spring Batch identifies a `JobInstance` based on the Job name and the JobParameters marked as *identifying*. When the same Job is launched with the same set of identifying parameters, that request represents the same JobInstance. If a default value changes unexpectedly, the application can accidentally create a new JobInstance; if a value changes when it should have stayed the same, the ability to restart can be affected.

Therefore, when designing JobParameters, you need to decide clearly which parameters have default values, where the default values are computed from, and whether a change in a parameter represents a new piece of business work.

## 1. JobParameters and the identity of a JobInstance

`JobParameters` is the collection of parameters passed in when launching a Job. For example, an order import Job might receive the business date, the input file, and the processing mode:

```text
businessDate = 2026-11-15
inputFile    = data/orders-2026-11-15.csv
mode         = FULL
```

Spring Batch distinguishes two kinds of parameters:

- **Identifying parameter:** takes part in identifying the JobInstance. Changing this value can create a different JobInstance.
- **Non-identifying parameter:** is stored as input data of the run but does not take part in determining the JobInstance identity.

The general relationship:

```text
Job name + identifying JobParameters
                  |
                  v
             JobInstance
                  |
                  +-- JobExecution #1
                  +-- JobExecution #2 (restart)
```

A JobInstance represents the logical business work to be completed; a JobExecution represents each attempt to execute that work. Identifying parameters therefore need to correctly describe the business boundary of a piece of work.

## 2. What are default parameters?

Spring Batch provides an API for building `JobParameters`, but choosing default values is usually the responsibility of the application or the launching component. For example, an API may allow the caller to omit `mode`; the service then assigns `FULL`. Another parameter such as `businessDate` may be required to be passed explicitly because the business date determines the dataset being processed.

For example, the application sets a default for the processing mode:

```java
String mode = requestMode;

if (mode == null || mode.isBlank()) {
    mode = "FULL";
}
```

Then put the resolved value into the JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("mode", mode, true)
        .toJobParameters();
```

The key point is that the Job receives a concrete value and does not need to guess whether the caller passed the parameter. Defaulting should be done at a clear boundary, such as the service that launches the Job or the layer that converts input parameters.

### Choosing default values by business meaning

A default value needs a clear business meaning:

- `mode=FULL` can be a reasonable default if the default process must import all of the data.
- `businessDate` can be required if running on the wrong date affects the result.
- `inputFile` can be derived from the business date under a stable file-naming convention.
- `notificationEmail` can be taken from the application configuration if it is used only to send notifications and does not change the dataset to be processed.

Do not set a default value merely to avoid validating input. If there is no safe and meaningful default value, require the caller to pass the parameter or reject the request with a clear message.

## 3. Building JobParameters after applying defaults

The example below illustrates a service that receives optional parameters and creates JobParameters. The business date is required; the processing mode defaults to `FULL`; the email for receiving notifications can be taken from configuration and marked non-identifying:

```java
public JobParameters createParameters(
        String requestedBusinessDate,
        String requestedMode,
        String requestedInputFile,
        String defaultNotificationEmail) {

    if (requestedBusinessDate == null || requestedBusinessDate.isBlank()) {
        throw new IllegalArgumentException("businessDate is required");
    }

    String businessDate = requestedBusinessDate.trim();
    String mode = (requestedMode == null || requestedMode.isBlank())
            ? "FULL"
            : requestedMode.trim().toUpperCase(Locale.ROOT);

    String inputFile = (requestedInputFile == null || requestedInputFile.isBlank())
            ? "data/orders-" + businessDate + ".csv"
            : requestedInputFile.trim();

    return new JobParametersBuilder()
            .addString("businessDate", businessDate, true)
            .addString("mode", mode, true)
            .addString("inputFile", inputFile, true)
            .addString("notificationEmail", defaultNotificationEmail, false)
            .toJobParameters();
}
```

In this example:

- `businessDate` identifies the date of the data to be processed, so it is identifying.
- `mode` changes the processing scope (`FULL` or another mode), so it is treated as identifying if the two modes represent two different logical pieces of work.
- `inputFile` is identifying if different files correspond to a different business dataset.
- `notificationEmail` only changes the notification recipient, so it can be non-identifying.

Marking a parameter identifying must be based on business rules, not on the data type or on whether the parameter is passed in from outside.

Note: the example uses `requestedBusinessDate` as a string already normalized to a consistent format, such as `yyyy-MM-dd`. A real application should parse and validate the date before creating JobParameters, and also normalize file names according to the system's rules.

## 4. Determinism of the JobInstance

A launch request is deterministic when the same Job name and the same identifying values produce the same JobInstance identity. It can be expressed as a rule:

```text
JobInstance identity = Job name + identifying JobParameters
```

Suppose `importOrdersJob` uses `businessDate` and `mode` as identifying parameters:

| Call | businessDate | mode | JobInstance |
|---|---|---|---|
| A | `2026-11-15` | `FULL` | Instance X |
| B | `2026-11-15` | `FULL` | Instance X |
| C | `2026-11-15` | `DELTA` | Instance Y |
| D | `2026-11-16` | `FULL` | Instance Z |

Calls A and B have the same identity because the identifying parameters are the same. Call C creates a different identity because the processing mode changed; call D differs because the business date changed.

If call A has completed, call B with the same identifying parameters is usually rejected with `JobInstanceAlreadyCompleteException`. If call A failed and can be restarted, call B can create a new JobExecution on the same JobInstance. This is how Spring Batch distinguishes a restart from a new piece of business work.

### Default values affect determinism

Suppose `mode` is not passed by the caller. If the application always defaults it to `FULL`, every call on the same day with the same file will have the same identifying parameters. A retry therefore continues to target the same JobInstance.

Conversely, if the default is computed from a value that changes on every call, such as the current timestamp, each call can create a new JobInstance. A retry that seems to be the same business work then becomes a new piece of work, destroying the meaning of restart.

## 5. Identifying and non-identifying parameters

The `JobParametersBuilder` methods let you specify whether a parameter takes part in identifying the JobInstance:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", true)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

In the example above, changing the email does not create a new JobInstance, while changing the date or mode creates a different identity.

Non-identifying does not mean the parameter is ignored. The value can still be read through `JobExecution.getJobParameters()` and used during the run. It simply does not take part in identifying the JobInstance.

Mark a parameter identifying when changing its value means processing a different logical piece of work. Mark it non-identifying when changing the value does not change the work's identity, such as a notification option or tracking information that does not affect the processed data.

### Risks of marking incorrectly

If a parameter changes the dataset but is marked non-identifying, a new request can point to the old JobInstance. This can lead to being unable to launch because the instance has completed, or cause a restart to use metadata that does not match the business intent.

If a parameter does not change the business work but is marked identifying, each small change can create a new JobInstance. This fragments the metadata history and means a retry is no longer tied to the previous work.

## 6. Default values must be stable across retries

An important principle is that the default of an identifying parameter must be computed by the same rule for every attempt at the same work.

For example, if the business date defaults to the current date, a run at 23:59 and a retry at 00:01 can receive two different dates. The system then creates two different JobInstances even though the operator only wanted to retry the same processing batch.

There are several design approaches:

- For a scheduled Job, the scheduler explicitly passes the business date into the JobParameters.
- For a manually launched Job, the API requires the user to choose the date or uses a default date determined in advance in the business configuration.
- If the default date is computed in the business time zone, compute that value once at the launch boundary and store it so a retry uses the original value.
- When the caller resubmits a request, keep the identifying parameters of the original request instead of recomputing the default at retry time.

For example, the scheduler can pass the business date explicitly:

```java
String businessDate = scheduledBusinessDate.format(
        DateTimeFormatter.ISO_LOCAL_DATE
);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("mode", "FULL", true)
        .toJobParameters();
```

The value `scheduledBusinessDate` must be determined from the business calendar and kept unchanged for retries of the same schedule run. Do not call `LocalDate.now()` in several different places during a retry and then expect the identification result to always be the same.

## 7. Normalizing parameters before building JobParameters

Two values can be the same in business meaning but differ in representation. For example, `FULL`, `full`, and ` FULL ` can be sent by the caller. If passed verbatim into identifying parameters, Spring Batch treats them as different values.

Therefore, normalize before building JobParameters:

- Trim whitespace at the start and end of the string.
- Normalize upper/lower case by convention, for example using `Locale.ROOT` for mode codes.
- Normalize dates into a single format, such as ISO `yyyy-MM-dd`.
- Normalize file paths or data source codes according to the rules of the operating system and the business.
- Validate enums, numeric ranges, and required values before launching.
- Do not use locale-dependent display values as identifiers if a stable code can be used.

Example:

```java
String normalizedMode = rawMode == null || rawMode.isBlank()
        ? "FULL"
        : rawMode.trim().toUpperCase(Locale.ROOT);

LocalDate parsedDate = LocalDate.parse(rawBusinessDate);
String normalizedDate = parsedDate.format(DateTimeFormatter.ISO_LOCAL_DATE);
```

Normalization lets the same business request produce the same set of identifying parameters, regardless of whether the caller sends different spellings or whitespace.

## 8. JobParametersIncrementer and creating the next instance

Spring Batch has `JobParametersIncrementer` to create the next JobParameters set based on the current one. An application can attach an incrementer to the Job and use APIs such as `JobOperator.startNextInstance` to request starting a next JobInstance.

For example, `RunIdIncrementer` is commonly used to increment the `run.id` parameter:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .incrementer(new RunIdIncrementer())
            .build();
}
```

An incrementer can produce a parameter set with an increasing `run.id`. If `run.id` is identifying, each new value creates a new JobInstance. This behavior is appropriate when the business requires a next independent run.

Do not use an incrementer to replace the restart mechanism. Restart is meant to continue the same JobInstance after a failed or stopped execution; creating a new `run.id` usually means creating a new JobInstance. In addition, `JobLauncher.run()` does not automatically increment parameters just because the Job has an incrementer attached; the incrementer is used by APIs that launch the next instance, such as `JobOperator.startNextInstance`.

## 9. Distinguishing retry, restart, and a new run

These terms are easy to confuse when designing default parameters:

| Action | JobInstance | JobExecution | Meaning |
|---|---|---|---|
| Restart a failed JobInstance | Unchanged | Creates a new execution | Continues the old logical work |
| Launch with the same identifying parameters after the instance has completed | Same identity | Usually rejected | Does not automatically rerun completed work |
| Launch with a new identifying parameter | Creates a new instance | Creates a new execution | Starts different logical work |
| Use an incrementer to create a new run ID | Usually creates a new instance if the run ID is identifying | Creates a new execution | Creates a next independent processing pass |

A repeated API call due to a client timeout is not necessarily a restart. If the first request already created a JobExecution but the client did not receive the response, the second request with the same identifying parameters can hit an instance-running or instance-already-complete error. The API should have a way to look up by business key or request ID so the caller can find the original execution instead of creating a new random parameter.

## 10. Designing idempotency for the launch API

For a Job launch API, the client may resend a request due to a timeout or a lost connection. If every call adds a timestamp as an identifying parameter, the system will create many JobInstances for the same business request.

A stable design usually includes:

1. Determine the business key of the request, for example the business date and the data source code.
2. Normalize the business key and convert the necessary components into identifying JobParameters.
3. Optionally store the client's request ID in a separate data store to trace request intake.
4. When the client resends the same request, look up the execution already created or handle the running/completed state according to business rules.
5. Create a new identifying parameter only when you truly want to start a new logical piece of work.

Do not rely on JobParameters to solve every HTTP idempotency scenario by themselves. The JobRepository protects the identity and state of the JobInstance, while the API needs to design its response and lookup mechanism to suit clients resending requests.

## 11. Inspecting and observing JobParameters

When investigating why a request created a new JobInstance or was rejected, record the normalized identifying parameters and the JobInstance/JobExecution IDs. Do not log secrets or sensitive data.

You can read the parameters from the JobExecution:

```java
JobParameters parameters = execution.getJobParameters();

String businessDate = parameters.getString("businessDate");
String mode = parameters.getString("mode");
Long runId = parameters.getLong("run.id");

log.info(
        "jobInstanceId={}, executionId={}, businessDate={}, mode={}, runId={}",
        execution.getJobInstance().getId(),
        execution.getId(),
        businessDate,
        mode,
        runId
);
```

If a parameter can be absent, handle the `null` value before using it. Do not assume all parameters always exist just because some launch flows have defaults.

## 12. Common misconceptions

**Assuming Spring Batch sets a default for every parameter.** Choosing default values usually belongs to the application, the scheduler, or the parameter conversion layer. JobParametersBuilder only builds the parameter set from the values provided.

**Using the current time as an identifying default on every call.** A changing timestamp creates a new JobInstance, so a retry no longer targets the same logical work.

**Assuming a non-identifying parameter has no effect.** This parameter is still stored and can be used by the Job; it just does not take part in identifying the JobInstance.

**Marking every parameter as identifying.** Only values that identify the business work should take part in the identity. Auxiliary information such as the notification recipient usually does not need to create a new instance.

**Using RunIdIncrementer to restart.** An incrementer usually creates a new identifier for the next instance. Restart keeps the JobInstance and creates a new JobExecution on that instance.

**Not normalizing strings.** Differences in whitespace, upper/lower case, or date format can produce different identifying parameters. Normalize before calling JobLauncher.

## 13. How to design suitable defaults and identity

Start from the business question: do two requests need to be considered the same piece of work to be completed? If so, they must produce the same Job name and the same set of identifying parameters after normalization. If not, at least one identifying parameter must differ.

Set defaults at a clear launch boundary, choose stable values with business meaning, validate input, and then create JobParameters with the identifying flag declared explicitly. Use JobParametersIncrementer when you need to deliberately create the next instance; use restart when you need to continue the same instance. This design lets retries repeat deterministically, keeps the JobInstance history easy to understand, and helps the application avoid creating unintended duplicate processing.
