# String, Long, Double, and Date Parameters

`JobParameters` is the collection of input values passed when launching a Spring Batch job. These values tell the job which data to process and can provide operational information such as a file name, a customer code, a business date, or an applicable exchange rate. Spring Batch stores the parameters together with the execution metadata in the `JobRepository`, so it can look up history and determine whether a run is a restart of a previous piece of work.

Each job parameter has a name, a value, a data type, and an `identifying` flag. The four common types are `String`, `Long`, `Double`, and `Date`. Choosing the right type helps the application pass data clearly, avoids having to parse strings in every step, and gives precise control over the identity of the `JobInstance`.

## 1. What are JobParameters used for?

A job is usually designed to run many times with different inputs. For example, `dailyReportJob` can generate a report for each day; `customerImportJob` can import different files; `recalculateAccountJob` can process a group of accounts.

Instead of writing a separate job for each day or each file, the application defines one job and passes `JobParameters` for each launch.

Example:

| Parameter | Example value | Purpose |
|---|---|---|
| `inputFile` | `file:/data/customers-2026-11-15.csv` | The file to import |
| `tenantId` | `1205` | The tenant's customer scope |
| `exchangeRate` | `1.08` | The exchange rate used in the calculation |
| `businessDate` | `2026-11-15` | The business date to process |

These values can affect the data selected, the processing rules, and the output. They are also stored in the metadata so operators know which inputs the job ran with.

## 2. A JobParameter has a data type and an identifying flag

A `JobParameter` is not just a text string. It consists of:

- **Name:** the key a step or job uses to retrieve the value, for example `businessDate`.
- **Value:** the data being passed, for example 15 November 2026.
- **Type:** the Java class of the value, for example `String`, `Long`, `Double`, or `Date`.
- **Identifying:** the flag that determines whether the parameter takes part in forming the `JobInstance` identity.

`JobParameters` is an immutable object once created. When a different parameter set is needed, the application creates a new `JobParameters` instead of modifying the one used for an execution.

Two common groups of parameters:

| Group | Role | Examples |
|---|---|---|
| Identifying parameter | Identifies the specific business work and takes part in forming the `JobInstance` | `businessDate`, `inputFile`, `tenantId` |
| Non-identifying parameter | Adds information to the run without changing the instance identity | `requestedBy`, `notificationEmail`, `traceLabel` |

For example, if `businessDate` is identifying and `requestedBy` is non-identifying, two requests to run `dailyReportJob` with the same business date but submitted by two different people still point to the same `JobInstance`.

The choice of identifying should be based on business meaning. If `tenantId` and `businessDate` identify a separate report for each tenant each day, both should be identifying. If `requestedBy` is only used for audit recording, it usually does not need to be part of the identity.

## 3. Creating JobParameters with JobParametersBuilder

`JobParametersBuilder` is a convenient way to create a typed parameter set. The methods `addString`, `addLong`, `addDouble`, and `addDate` accept the corresponding value and have overloads that let you specify the identifying flag.

Example combining all four types:

```java
import java.util.Date;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

Date businessDate = new Date();

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/customers.csv", true)
        .addLong("tenantId", 1205L, true)
        .addDouble("exchangeRate", 1.08D, false)
        .addDate("businessDate", businessDate, true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In the example:

- `inputFile` is a `String` that identifies the data source to import.
- `tenantId` is a `Long` that identifies the tenant to process.
- `exchangeRate` is a `Double` that supplies the exchange rate but does not take part in the instance identity.
- `businessDate` is a `Date` that identifies the business date or point in time, according to the application's convention.
- `requestedBy` is a `String` that records the source of the request and does not change the instance identity.

Whether a parameter is identifying or non-identifying is specified by the last boolean argument. You should pass this value explicitly instead of relying on the default overload, because the identifying flag directly affects whether Spring Batch considers two launches to be the same `JobInstance`.

After creating it, pass the parameter set to the `JobLauncher`:

```java
JobExecution execution = jobLauncher.run(myJob, parameters);
```

`JobLauncher` uses the job name and the identifying parameters to find or create the `JobInstance`, and then creates a `JobExecution` if the instance state allows it.

## 4. String parameter

`String` suits text values or identifiers with a string structure, such as:

- The path or name of the input file.
- A tenant code, branch code, or business code if the system defines them as strings.
- The report language or format.
- A data region name, business type, or request label.

Creating the parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/orders.csv", true)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();
```

Reading the parameters:

```java
String inputFile = parameters.getString("inputFile");
String requestedBy = parameters.getString("requestedBy");
```

Some notes when using `String`:

- Do not turn every value into a string just because strings are easy to pass. Numeric codes that require calculation or numeric comparison should use an appropriate numeric type.
- Normalize values that carry identifying meaning. For example, `orders.csv` and `./orders.csv` may point to the same file but are two different strings; if used as an identifying parameter, they can produce different identities.
- Define clear rules for upper/lower case, whitespace, and Unicode normalization if the value takes part in the identity.
- Do not pass passwords, access tokens, or secret data in `JobParameters`, because the metadata is stored for tracking and may be displayed in operational tools or logs.

## 5. Long parameter

`Long` is the signed 64-bit integer type in Java. It suits integer values that may exceed the range of `Integer`, for example:

- The ID of a tenant, customer, or account.
- A record sequence number or a numeric checkpoint.
- The number of items, the page number, or a processing limit.
- An epoch timestamp if the application's convention is to use an integer.

Creating and reading the parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("tenantId", 1205L, true)
        .addLong("pageSize", 500L, false)
        .toJobParameters();

Long tenantId = parameters.getLong("tenantId");
Long pageSize = parameters.getLong("pageSize");
```

The suffix `L` makes it clear the literal is of type `long`. When the value comes from an external API or configuration, you need to verify that the input string can be converted to a valid integer within the range of `Long`.

Do not use `Long` for codes with leading zeros if the zeros are part of the code. For example, the customer code `001205` may need to remain a `String`; converting it to `Long` would lose the leading zeros and change the identifying value.

## 6. Double parameter

`Double` is the 64-bit IEEE 754 floating-point type. It suits some measurement values or approximate calculation parameters, for example:

- A conversion rate or a percentage.
- A simulation coefficient.
- A measurement threshold with a fractional part.
- An adjustment factor that does not require absolutely exact decimal representation.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addDouble("exchangeRate", 1.08D, false)
        .addDouble("threshold", 0.75D, false)
        .toJobParameters();

Double exchangeRate = parameters.getDouble("exchangeRate");
Double threshold = parameters.getDouble("threshold");
```

`Double` can represent some decimal numbers only approximately. For instance, many values such as `0.1` have no exact finite binary representation. Therefore, do not use `Double` for currency, balances, or financial calculations that must be exact down to the smallest unit.

For currency, consider passing the value in the smallest unit as a `Long` (for example, a number of cents) or using `BigDecimal` when your Spring Batch version and configuration support custom parameter types together with a durable conversion mechanism. If you use `BigDecimal`, make sure the converter and the storage/read format are stable across runs and application versions.

## 7. Date parameter

`Date` in Java usually means `java.util.Date`, which represents a point on the timeline with millisecond precision. It does not store a time zone name such as `Asia/Ho_Chi_Minh`; in essence, it represents an instant. The time zone is only used when converting the instant into a date-time string for users or when interpreting the business date.

Creating the parameters:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

Date businessDate = Date.from(
        LocalDate.of(2026, 11, 15)
                .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant()
);

JobParameters parameters = new JobParametersBuilder()
        .addDate("businessDate", businessDate, true)
        .toJobParameters();
```

Reading the parameters:

```java
Date businessDate = parameters.getDate("businessDate");
```

### How does Date differ from a business date?

A `Date` is a point in time, whereas the business may only care about a calendar day such as "15 November". If you create the `Date` in the server's time zone, the same calendar day can convert to a different instant when the application runs on a server in another time zone.

To avoid discrepancies:

1. Clearly define which time zone the business date belongs to.
2. Convert the calendar date into an instant using a prescribed `ZoneId`, not relying on the server's default time zone.
3. Keep the same conversion rule on every node that launches the job.
4. If the parameter is truly a date without a time, prefer a pure-date representation such as `LocalDate` when the Spring Batch version in use supports that typed parameter.

In Spring Batch versions that support Java Time parameters, `JobParametersBuilder` has methods such as `addLocalDate`, `addLocalDateTime`, and `addLocalTime`. For example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .toJobParameters();
```

The Java Time API and the supported parameter types depend on the Spring Batch version. If the project uses an older version that supports only `Date`, you need to agree on the time zone and the instant normalization approach across environments.

## 8. Reading JobParameters in the job and step

After the launcher passes the parameters, components in the job can retrieve the values through `JobParameters`. For example, from `JobExecution`:

```java
public void printParameters(JobExecution jobExecution) {
    JobParameters parameters = jobExecution.getJobParameters();

    String inputFile = parameters.getString("inputFile");
    Long tenantId = parameters.getLong("tenantId");
    Double exchangeRate = parameters.getDouble("exchangeRate");
    Date businessDate = parameters.getDate("businessDate");

    // Use the values in the business logic.
}
```

The getters return `null` if the parameter does not exist or has no value. Therefore, if a parameter is required, check it as soon as the job starts and report a clear parameter error instead of letting a `NullPointerException` appear in the middle of a step.

You can use `JobParametersValidator` to check the input before the job executes. A validator can confirm required parameters, value ranges, relationships between parameters, and business formats.

A simple validation example:

```java
public void validate(JobParameters parameters) {
    String inputFile = parameters.getString("inputFile");
    Long tenantId = parameters.getLong("tenantId");

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    if (tenantId == null || tenantId <= 0) {
        throw new IllegalArgumentException("tenantId must be positive");
    }
}
```

The code above illustrates the validation logic; in a real application you should implement it via the `JobParametersValidator` interface and throw `JobParametersInvalidException` for invalid parameters.

## 9. How does the data type affect the JobInstance?

Identifying parameters take part in forming the identity of the `JobInstance`. Therefore, the name, type, and value must be created consistently on every launch.

For example, the following parameter sets should not be considered equivalent if the application creates them with different types:

```java
// First parameter set
new JobParametersBuilder()
        .addString("tenantId", "1205", true)
        .toJobParameters();

// Second parameter set
new JobParametersBuilder()
        .addLong("tenantId", 1205L, true)
        .toJobParameters();
```

One set uses `String`, the other uses `Long`. Although a person might read both as the number 1205, they have different types and you should not rely on them producing the same instance identity. Agree on the parameter type from the job's design stage and keep it stable across deployment versions.

Some situations that commonly cause unintended instances:

- One node sends `tenantId` as a `Long`, another node sends it as a `String`.
- The business date is converted into a `Date` using each server's default time zone.
- A path string with or without the `./` prefix, with different upper/lower case, or with a different normalization approach.
- A `run.id` parameter is added to the identifying parameters on every launch.
- An operational parameter such as `requestedBy` is marked identifying even though it does not represent new business work.

If the same business period must be treated as the same instance, all launchers must agree on the name, type, normalized value, and identifying flag of the relevant parameters.

## 10. JobParameters and restart

When a job fails or stops, Spring Batch can restart the same `JobInstance` by launching again with the same identifying parameters, if the job allows restart and the execution state is appropriate.

For example, the first run used:

```text
jobName = dailyReportJob
businessDate = 2026-11-15 (identifying Date or LocalDate)
tenantId = 1205 (identifying Long)
requestedBy = scheduler (non-identifying String)
```

If the run fails, the restart request must keep the identifying parameters unchanged. Changing `businessDate` or `tenantId` can create a different `JobInstance` instead of restarting the previous instance.

Non-identifying parameters can change without changing the instance identity, but you need to consider the operational meaning. For example, changing `requestedBy` from `scheduler` to `operator` may still point to the same instance; however, steps should not rely on a non-identifying parameter that can change between restarts to decide core business data.

Do not use a parameter whose value changes on every call, such as the current timestamp, as identifying if the goal is to restart the same work. If you need to create a new intentional processing run, use a business parameter that clearly expresses the reprocess run or the processing version.

## 11. Passing parameters from the command line and orchestration systems

An application can receive job parameters from a REST API, a scheduler, the command line, or an orchestration system. Whatever the input source, the application needs to convert the values to the desired Java types before creating `JobParameters`.

Example of an API receiving a payload:

```json
{
  "inputFile": "file:/data/customers.csv",
  "tenantId": 1205,
  "exchangeRate": 1.08,
  "businessDate": "2026-11-15"
}
```

Do not assume that JSON values or command-line strings already have the correct type in `JobParameters`. The application needs to parse and validate the data, especially numbers, dates, and time zones. A date string such as `15/11/2026` can be interpreted differently depending on the locale; an ISO format such as `2026-11-15` is easier to exchange and check.

For a `Date` parameter, you need to specify whether the input string represents a calendar date or a point in time with a time zone. If it represents an instant, use a format with an explicit offset or UTC. If it represents a business date, use a fixed date and time-zone convention.

## 12. Custom types and convertibility

The types `String`, `Long`, `Double`, and `Date` are common, easy to understand, and usually supported directly by Spring Batch versions. Newer versions of Spring Batch support typed `JobParameter` more flexibly, allowing other types if there is a corresponding string-conversion and store/read mechanism.

If you want to use `BigDecimal`, `UUID`, `LocalDate`, or your own business type, you need to confirm the Spring Batch version and the conversion service configuration. Make sure that:

- The value can be converted from its stored form back to the correct Java type.
- The representation is stable and does not depend on the default locale or timezone.
- Every node in a distributed environment uses the same converter and the same normalization rules.
- The job can read old metadata after the application is upgraded.

Do not use a complex custom object as an identifying parameter if you have not clearly defined how to produce a stable key. For instance identity, simple, immutable values with a standard representation are usually easier to operate.

## 13. Common mistakes when using parameter types

| Situation | Cause | Remedy |
|---|---|---|
| Cannot read a parameter with the desired getter | Wrong parameter name or wrong Java type | Check the name and type at creation and use the corresponding getter |
| Same data but a new JobInstance is created | Different identifying type or value | Normalize the type, value, and identifying flag in every launcher |
| Leading zeros in a code are lost | Used `Long` for a string-based identifier | Use `String` if the zeros are part of the code |
| Currency results have small discrepancies | Used `Double` for a calculation that needs decimal precision | Use an integer in the smallest unit or `BigDecimal` with an appropriate converter |
| The job processes a different date across nodes | Created `Date` with different default timezones | Use a fixed business timezone or `LocalDate` if supported |
| Restart does not find the old instance | An identifying parameter was changed or a timestamp/run ID was added | Restore the exact identifying parameters of the previous instance |
| A step raises NullPointerException | A required parameter was not passed | Validate parameters before executing the job |
| Old parameters cannot be read after an upgrade | The converter or storage type changed | Maintain converter compatibility and check the metadata before upgrading |

## 14. Complete example: importing data by tenant and business date

Suppose the system needs to import order data from a CSV file for one tenant on one day. The job uses these parameters:

| Name | Type | Identifying | Meaning |
|---|---|---|---|
| `inputFile` | `String` | Yes | The specific input file |
| `tenantId` | `Long` | Yes | The tenant to import |
| `businessDate` | `Date` | Yes | The business date normalized to the prescribed timezone |
| `exchangeRate` | `Double` | No | The exchange rate used for auxiliary calculations |
| `requestedBy` | `String` | No | The request source for audit |

Creating the parameters:

```java
Date businessDate = Date.from(
        LocalDate.of(2026, 11, 15)
                .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant()
);

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "file:/data/orders-2026-11-15.csv", true)
        .addLong("tenantId", 1205L, true)
        .addDate("businessDate", businessDate, true)
        .addDouble("exchangeRate", 1.08D, false)
        .addString("requestedBy", "nightly-scheduler", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

When the job starts, the application can read and verify the parameters:

```java
JobParameters parameters = jobExecution.getJobParameters();

String inputFile = parameters.getString("inputFile");
Long tenantId = parameters.getLong("tenantId");
Date businessDate = parameters.getDate("businessDate");
Double exchangeRate = parameters.getDouble("exchangeRate");

if (inputFile == null || tenantId == null || businessDate == null) {
    throw new IllegalArgumentException("Missing required job parameter");
}
```

If the scheduler resends exactly the same set of identifying parameters, Spring Batch recognizes it as the same business work. If the previous execution failed and the job allows restart, the next launch can restart the instance. If the business date or tenant changes, it is a different instance. `exchangeRate` and `requestedBy` do not change the identity in this example, but the application must still decide whether changing them between restarts is consistent with the business rules.

## 15. Principles to remember

- `JobParameters` is a collection of parameters with a name, value, data type, and identifying flag.
- `String` suits text, paths, and codes that must preserve characters such as leading zeros.
- `Long` suits integer IDs, counts, or 64-bit integer values.
- `Double` suits approximate real numbers; avoid it for currency that needs decimal precision.
- `Date` represents an instant and does not itself carry a timezone or calendar-day meaning; normalize it according to the business timezone.
- `JobParametersBuilder` helps create typed parameters and clearly marks identifying/non-identifying.
- Only identifying parameters take part in identifying the `JobInstance`; changing them can create a new instance instead of a restart.
- Launchers in a multi-node environment must agree on the type, normalized value, and identifying flag.
- Validate required parameters before the job runs so input errors are detected early.
- For custom types or Java Time, check the support of the Spring Batch version and make sure the converter is stable across restarts/upgrades.

Choosing the right `String`, `Long`, `Double`, and `Date` helps `JobParameters` express the input data clearly, supports accurate validation and metadata storage, and keeps the `JobInstance` identity stable across launches and restarts.
