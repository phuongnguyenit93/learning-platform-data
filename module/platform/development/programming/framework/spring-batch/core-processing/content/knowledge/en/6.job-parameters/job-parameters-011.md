# Displaying Parameters in Metadata

In Spring Batch, `JobParameters` is the set of input values passed when launching a Job. These parameters can determine the data scope to process, for example the business date, file name, customer code, or import batch code. Spring Batch stores the parameters in the metadata repository so a run can be looked up again, the `JobInstance` can be identified, and restart can be supported.

With a JDBC JobRepository, the parameters of each run are stored in the `BATCH_JOB_EXECUTION_PARAMS` table. This table ties the parameters to the `JobExecution`, so you can see which values a run received, what their data types were, and which parameters take part in identifying the JobInstance. You can read the data via SQL or use Spring Batch's `JobExplorer`/`JobExecution` API.

## 1. What are JobParameters and where are they stored?

`JobParameters` is the set of parameters passed to the Job at launch. Each parameter has a name, a value, a data type, and an identifying property. For example, an order import Job might receive:

| Parameter name | Example value | Identifying |
|---|---|---|
| `businessDate` | `2026-11-15` | Yes |
| `inputFile` | `orders-2026-11-15.csv` | Yes |
| `requestedBy` | `scheduler` | No |
| `dryRun` | `false` | No |

When the `JobLauncher` launches the Job, Spring Batch creates or finds the `JobInstance` based on the Job name and the identifying parameters. Each specific execution is represented by a `JobExecution`. Parameters are stored per `JobExecution`, so the same JobInstance can have multiple JobExecutions and each execution has parameter records tied to its own ID.

The general relationship:

```text
BATCH_JOB_INSTANCE
  JOB_INSTANCE_ID
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION
  JOB_EXECUTION_ID
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION_PARAMS
  JOB_EXECUTION_ID
  PARAMETER_NAME / KEY_NAME
  PARAMETER_VALUE / *_VAL
  IDENTIFYING
```

`BATCH_JOB_EXECUTION_PARAMS` is the table to look at when you want to know which parameters an execution was launched with. It is not the table that stores Step checkpoints; checkpoints and execution state live in the corresponding ExecutionContext tables.

## 2. Identifying and non-identifying parameters

Each `JobParameter` has an identifying property. Identifying parameters take part in forming the JobInstance's identity key; non-identifying parameters are stored with the execution but do not change the JobInstance identity.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addString("requestedBy", "scheduler", false)
        .addString("dryRun", "false", false)
        .toJobParameters();
```

In the example, `businessDate` and `inputFile` take part in identifying the JobInstance. `requestedBy` and `dryRun` are additional information for the execution. If the same Job name and the same identifying parameters are sent again, Spring Batch determines it is the same JobInstance, even when the non-identifying parameters differ.

The choice of identifying parameters should stay close to business meaning:

- The business date is usually identifying if each date is a separate processing batch.
- A file code or batch code can be identifying if it uniquely identifies the dataset to process.
- The requester, log labels, or request correlation information are usually non-identifying.
- A flag that changes the business result may need to be identifying, depending on whether the two run modes are considered the same JobInstance.

Do not mechanically mark all parameters as identifying. If a value only serves logging but is marked identifying, each different value can create a new JobInstance. Conversely, if a parameter changes the business dataset but is not identifying, two different requests may be treated as the same JobInstance.

## 3. The BATCH_JOB_EXECUTION_PARAMS table in Spring Batch 5

Starting with Spring Batch 5, the standard schema of the parameters table uses a more general structure. Commonly seen columns include:

| Column | Meaning |
|---|---|
| `JOB_EXECUTION_ID` | The ID of the JobExecution that owns the parameter. |
| `PARAMETER_NAME` | The parameter name. |
| `PARAMETER_TYPE` | The Java class name of the parameter's data type. |
| `PARAMETER_VALUE` | The parameter value represented as a string. |
| `IDENTIFYING` | A flag indicating whether the parameter takes part in identifying the JobInstance. |

Illustrative sample data:

| JOB_EXECUTION_ID | PARAMETER_NAME | PARAMETER_TYPE | PARAMETER_VALUE | IDENTIFYING |
|---:|---|---|---|---|
| 9002 | `businessDate` | `java.lang.String` | `2026-11-15` | `Y` |
| 9002 | `inputFile` | `java.lang.String` | `orders-2026-11-15.csv` | `Y` |
| 9002 | `requestedBy` | `java.lang.String` | `scheduler` | `N` |
| 9002 | `recordLimit` | `java.lang.Long` | `5000` | `N` |

The specific column names and types need to be checked against the schema script shipped with the Spring Batch version you are running. Do not assume the schema of every version matches the sample table.

### Why is there a PARAMETER_TYPE?

Spring Batch 5 supports `JobParameter` with a generic data type. Therefore, the metadata needs to store the type information so that, when read back, the value can be converted to the correct Java type. For example, the value `5000` could be a `String`, a `Long`, or another type; looking only at `PARAMETER_VALUE`, you cannot determine the exact type.

For custom data types, converting to and from a string requires an appropriate converter. If the application uses a custom type in JobParameters, make sure the serialization/deserialization is compatible across the application versions that can read the same metadata.

## 4. Differences from the Spring Batch 4 schema

In Spring Batch versions before 5, `BATCH_JOB_EXECUTION_PARAMS` typically stored values in separate columns for each data type group. Commonly seen columns include:

| Old column | Meaning |
|---|---|
| `JOB_EXECUTION_ID` | The ID of the JobExecution. |
| `TYPE_CD` | The data type code. |
| `KEY_NAME` | The parameter name. |
| `STRING_VAL` | The String-typed value. |
| `DATE_VAL` | The Date-typed value. |
| `LONG_VAL` | The Long-typed value. |
| `DOUBLE_VAL` | The Double-typed value. |
| `IDENTIFYING` | The identifying flag. |

When moving from Spring Batch 4 to Spring Batch 5, the parameter structure changes from type-specific value columns to the column set `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING`. Therefore, SQL queries against this table need to be updated for the new schema.

Do not run a Spring Batch 5 application on the old schema without migration. The framework may report missing columns or parameter read/write errors. Also, do not take the Spring Batch 5 DDL and apply it to an application still running Spring Batch 4. Always get the schema script corresponding to the actual version.

## 5. Querying parameters with SQL

SQL is useful when you need to inspect metadata directly, produce operational reports, or investigate a specific run. With the Spring Batch 5 schema, you can query parameters by `JOB_EXECUTION_ID`:

```sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002
ORDER BY PARAMETER_NAME;
```

The result shows all the parameters stored for execution 9002, including name, type, value, and identifying flag. Replace the sample ID with the actual ID you need to look up.

### Display parameters along with the Job name and execution status

To see parameters in the Job's context, you can JOIN with the execution and instance tables:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS p
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_EXECUTION_ID = p.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = 9002
ORDER BY p.PARAMETER_NAME;
```

This query helps relate a parameter to the Job name, JobInstance, JobExecution, and the run's status. The time column names may differ between schema versions; adjust to the actual DDL.

### Viewing parameter history across multiple runs

When you need to compare runs of the same Job, filter by Job name and sort by execution:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
JOIN BATCH_JOB_EXECUTION_PARAMS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC, p.PARAMETER_NAME;
```

The query can return multiple rows for each JobExecution because each parameter is a separate row. A JobInstance can have multiple JobExecutions; therefore, use both `JOB_INSTANCE_ID` and `JOB_EXECUTION_ID` when you need to distinguish a business run from a run attempt.

### Querying the Spring Batch 4 schema

If the application still uses the old schema, the SQL takes a different form:

```sql
SELECT
    JOB_EXECUTION_ID,
    KEY_NAME,
    TYPE_CD,
    STRING_VAL,
    DATE_VAL,
    LONG_VAL,
    DOUBLE_VAL,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002
ORDER BY KEY_NAME;
```

In the old schema, typically only one of the type-specific value columns holds the value for a parameter. Do not apply this query to the Spring Batch 5 schema.

## 6. Displaying parameters with JobExplorer

In a Java application, prefer the Spring Batch API when you need to read metadata. `JobExplorer` lets you look up a `JobExecution`; from there you can get the `JobParameters` that the execution used.

Example with Spring Batch 5:

```java
@Service
public class JobParameterQueryService {

    private final JobExplorer jobExplorer;

    public JobParameterQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printParameters(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
        if (execution == null) {
            System.out.println("JobExecution not found: " + jobExecutionId);
            return;
        }

        JobParameters parameters = execution.getJobParameters();

        parameters.getParameters().forEach((name, parameter) -> {
            System.out.printf(
                    "%s=%s (type=%s, identifying=%s)%n",
                    name,
                    parameter.getValue(),
                    parameter.getType().getName(),
                    parameter.isIdentifying());
        });
    }
}
```

In Spring Batch 5, `JobParameters.getParameters()` returns a map of `JobParameter<?>`. Each parameter provides the value, type, and identifying flag. This way of reading avoids having to decode the SQL storage structure yourself and is better suited when the schema changes between versions.

When a JobExecution is running, the data read from the repository reflects the metadata that was stored at the time of the query. It does not necessarily reflect uncommitted changes or temporary state in the memory of the running process.

### Reading a specific parameter

If you know the parameter name, you can get it directly from `JobParameters`:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    JobParameters parameters = execution.getJobParameters();
    String inputFile = parameters.getString("inputFile");
    Long recordLimit = parameters.getLong("recordLimit");
}
```

The type-specific getter methods need to match the actual stored type. If a parameter has a custom type, use the generic parameter API and the corresponding converter instead of casting arbitrarily.

## 7. Displaying parameters in listeners and logs

While the Job runs, a listener can read JobParameters from the `JobExecution` to record the execution's context. For example, a `JobExecutionListener` can log non-sensitive information before the Job starts:

```java
public class JobParameterLoggingListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        JobParameters parameters = jobExecution.getJobParameters();

        String businessDate = parameters.getString("businessDate");
        String inputFile = parameters.getString("inputFile");

        System.out.printf(
                "Starting job=%s, executionId=%d, businessDate=%s, inputFile=%s%n",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                businessDate,
                inputFile);
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        System.out.printf(
                "Finished executionId=%d, status=%s, exitCode=%s%n",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

Register the listener with the Job using `.listener(jobParameterLoggingListener)`. In a real system, you need to filter or mask sensitive parameters before logging. Do not log the entire `JobParameters` via a `toString()` call without controlling what content may appear.

A listener is suitable for recording start/end information. If you need to display execution history on an admin screen, use a `JobExplorer` query service instead of relying on application logs.

## 8. How do JobParameters differ from ExecutionContext?

Both mechanisms can store data related to an execution but serve different purposes:

| Criterion | JobParameters | ExecutionContext |
|---|---|---|
| When provided | Passed when the Job is launched. | Updated during execution. |
| Purpose | Describes the input and identifies the business run. | Stores state, checkpoints, and data that needs to be recovered/shared. |
| Scope | Tied to the JobExecution. | Has JobExecution or StepExecution scope. |
| Identifying | Has an identifying flag to identify the JobInstance. | Not used to identify the JobInstance. |
| Metadata table | `BATCH_JOB_EXECUTION_PARAMS`. | `BATCH_JOB_EXECUTION_CONTEXT` and `BATCH_STEP_EXECUTION_CONTEXT`. |

For example, `businessDate` and `inputFile` are inputs of the Job and so are usually JobParameters. The position of the last line read in a file is progress state and so belongs to the Step ExecutionContext. Do not store continuously changing checkpoints as JobParameters because JobParameters describe the input of a run, while ExecutionContext is designed for state during the run.

## 9. Parameters and restart

When a Job fails and is restarted, Spring Batch uses the identifying parameters to identify the corresponding JobInstance. The next run creates a new JobExecution for the same JobInstance if the restart conditions are met.

This has several consequences:

- When you want to restart, you must keep the exact JobInstance identity via the identifying parameters.
- If you change an identifying parameter, Spring Batch may treat it as a new JobInstance instead of a restart.
- Non-identifying parameters do not take part in identification, but are still stored for each JobExecution.
- The parameters used in a specific execution can be reviewed through that execution's own metadata.

For example, `businessDate` identifies the business batch; `requestedBy` only records who sent the request. If the Job fails, changing `businessDate` can create a different JobInstance. If only `requestedBy` is changed, the JobInstance identity is still based on the identifying parameters.

Do not automatically add a timestamp to the identifying parameters each time the caller retries a request. If the earlier request was already accepted by the JobRepository but the response was lost, a new timestamp creates a new identity and can cause the data to be processed again. Use an idempotency key or business key so the caller can recognize the earlier request.

## 10. Displaying parameters on an admin screen

A Batch monitoring screen usually needs to display enough information for operators to recognize a run and understand the data scope:

- The Job name and JobInstance ID.
- The JobExecution ID and current status.
- The start time, end time, and run duration.
- The parameter name, the value (masked if needed), the data type, and the identifying flag.
- The exit code/message and controlled error information.

You should group parameters by JobExecution. If you display the history of multiple runs, allow users to distinguish executions of the same JobInstance. An illustrative table:

| JobExecution | Status | Parameter | Value | Identifying |
|---:|---|---|---|---|
| 9002 | `COMPLETED` | `businessDate` | `2026-11-15` | Yes |
| 9002 | `COMPLETED` | `inputFile` | `orders-2026-11-15.csv` | Yes |
| 9002 | `COMPLETED` | `requestedBy` | `scheduler` | No |

If you display multiple JobExecutions, do not merge parameters by JobInstance only and lose the execution ID. That can make operators misunderstand the values used in a specific run.

For custom types, you can display the type name and a safe representation of the value. Do not assume every value is a string that can be put directly into HTML or logs; encode the output and limit the length.

## 11. Security when storing and displaying parameters

JobParameters are stored in the metadata repository, which usually outlives the original request. Therefore, do not pass secrets just so a Step can read them.

Avoid storing directly:

- Database passwords or service passwords.
- Access tokens, refresh tokens, API keys, or private keys.
- URLs containing login credentials.
- Personal data content or large payloads not needed to identify the Job.

Instead, store a safe reference such as a configuration code, a secret alias, or a resource ID; the Step fetches the secret from a secret manager or appropriate secure configuration at execution time.

If a parameter contains sensitive data due to business requirements, you need to assess the read permissions on the metadata table, access to the admin screen, the encryption policy, retention, and log masking. `PARAMETER_VALUE` can be read by anyone with database query permission; hiding the value in the UI does not by itself protect the data in the database.

When logging, only log the parameter name or the values that have been allowed. You can use an allow-list to log some fields such as `businessDate` and mask the others. Avoid logging an exception message verbatim if it may contain all the parameters.

## 12. Limitations and notes when querying metadata directly

SQL is very useful for investigation, but the table structure is an implementation detail of the JDBC JobRepository and may change by version, database, or table prefix.

Some principles:

- Use the correct schema script for the Spring Batch version.
- Determine the table prefix if the application does not use the default `BATCH_`.
- Do not assume the data types and parameter storage are the same between Batch 4 and Batch 5.
- Only use `SELECT` statements for ordinary display and reporting needs.
- Do not directly update or delete the parameters of a running execution.
- When you need to read metadata in the application, prefer `JobExplorer` and `JobExecution`.
- When you need a migration, use a versioned process and test on a copy of the data.

If the application uses a custom repository or does not use the JDBC JobRepository, the way metadata is stored can differ. Do not assume the `BATCH_JOB_EXECUTION_PARAMS` table always exists in every kind of repository.

## 13. Common mistakes

### The BATCH_JOB_EXECUTION_PARAMS table cannot be found

The schema may not have been initialized, the datasource may point to the wrong database, or the repository may use a different table prefix. Check the datasource configuration, `spring.batch.jdbc.initialize-schema`, the schema owner, and the prefix.

### The SQL uses the PARAMETER_NAME column but the database only has KEY_NAME

This is usually a sign that the old Spring Batch 4 schema is in use while the SQL was written for Spring Batch 5, or vice versa. Determine the framework version and the DDL in use, and then adjust the query.

### The displayed value is not the expected type

In the Batch 5 schema, `PARAMETER_VALUE` is a string representation and `PARAMETER_TYPE` indicates the type to restore. Do not parse every value into String or Long yourself. Use the JobParameters API or an appropriate converter.

### The parameters are not seen in the expected run

You may be looking up the wrong `JOB_EXECUTION_ID`, confusing JobExecutions of the same JobInstance, or using the wrong database/schema. JOIN through JobExecution and JobInstance to confirm the right run.

### Confusing parameters with checkpoints

`BATCH_JOB_EXECUTION_PARAMS` stores the input of a JobExecution. Checkpoints during processing live in the ExecutionContext. Look up the right table according to your purpose.

### Exposing sensitive information in the UI or logs

JobParameters can be stored for a long time. Check the parameter content before displaying or logging it; mask sensitive values and restrict read permission on metadata.

## 14. Process for looking up the parameters of a run

When you need to know which parameters a Job ran with, you can follow this sequence:

1. Determine the Job name and the `JOB_EXECUTION_ID` to look up.
2. Check `BATCH_JOB_EXECUTION` to confirm the status and run time.
3. Query `BATCH_JOB_EXECUTION_PARAMS` by execution ID or use `JobExplorer`.
4. Read the name, type, value, and identifying flag of each parameter.
5. Cross-check the identifying parameters against the JobInstance to understand why Spring Batch considered the run the same or a different instance.
6. If you need to check progress or the restart position, also look at the corresponding Job/Step ExecutionContext.
7. Mask or remove sensitive values before putting the results on an admin screen or into logs.

## Conclusion

Spring Batch stores the `JobParameters` of each run in `BATCH_JOB_EXECUTION_PARAMS`. With Spring Batch 5, the table typically has the columns `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING`; the Spring Batch 4 schema uses a different column structure. You can display parameters with SQL for investigation or use `JobExplorer` and `JobExecution.getJobParameters()` in the application. When presenting metadata, you need to distinguish identifying from non-identifying parameters, distinguish JobParameters from ExecutionContext, and protect sensitive values that have been stored long-term.
