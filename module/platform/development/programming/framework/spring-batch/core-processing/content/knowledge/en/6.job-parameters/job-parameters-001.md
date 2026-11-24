# JobParameters Identify the JobInstance

In Spring Batch, a job can be run many times to process different business periods or different datasets. The framework needs to know whether two launch requests represent the same logical piece of work. For example, importing the order file for 15/11 is one piece of work; importing the file for 16/11 is another. Spring Batch uses the **Job name combined with the identifying `JobParameters`** to identify a `JobInstance`.

For this reason, JobParameters are not just input values used by a reader or processor. Marking which parameters take part in identification also determines how Spring Batch distinguishes a new run from a restart, detects duplicate requests, and stores execution history.

## 1. What are JobParameters?

`JobParameters` is the set of parameters passed in when launching a `Job`. Parameters can describe the data to be processed or provide information to the process, for example:

- The business date to import.
- The input file path.
- The source system code.
- The range of record IDs to process.
- The person or system that requested the run.
- A request ID used to track an intake.

A parameter has a name, a value, a data type, and an `identifying` property. This property indicates whether the parameter takes part in identifying the JobInstance.

Example of a parameter set for an order import job:

```text
businessDate = 2026-11-15    identifying = true
inputFile    = orders.csv   identifying = true
requestedBy  = scheduler    identifying = false
```

In the example, the business date and the input file determine the logical piece of work to process. `requestedBy` only records who requested the run, so it does not change the identity of the JobInstance.

## 2. How is a JobInstance identified?

A `JobInstance` is identified by two components:

1. The name of the `Job`.
2. The `JobParameters` with `identifying=true`.

This concept can be expressed as a formula:

```text
JobInstance identity = Job name + identifying JobParameters
```

For example, the job `importOrdersJob` running with `businessDate=2026-11-15` and `sourceSystem=ERP`:

```text
Job name: importOrdersJob

Identifying parameters:
  businessDate = 2026-11-15
  sourceSystem = ERP

              |
              v
JobInstance: importOrdersJob / 2026-11-15 / ERP
```

If the same job is run with the same identifying values, Spring Batch determines that it is the same JobInstance. If the job name changes or one identifying parameter changes, the result is a different JobInstance.

| Job name | Identifying parameters | Result |
|---|---|---|
| `importOrdersJob` | `businessDate=2026-11-15` | Instance A |
| `importOrdersJob` | `businessDate=2026-11-15` | Same instance A |
| `importOrdersJob` | `businessDate=2026-11-16` | Instance B |
| `importCustomersJob` | `businessDate=2026-11-15` | Instance C |

Two jobs with different names do not share a JobInstance, even if they receive the same parameters. Similarly, two runs of the same job name with different identifying values represent two different logical processing units.

## 3. Creating JobParameters with JobParametersBuilder

Typically, the application creates parameters with `JobParametersBuilder`. The builder lets you add values one at a time and explicitly specify the identifying property.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

The important arguments of `addString` are the parameter name, the value, and the identifying flag. The flag `true` means the parameter takes part in identifying the JobInstance; the flag `false` means it does not.

Once created, pass the JobParameters to the JobLauncher:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

The builder also supports data types other than strings, such as long integers, floating-point numbers, or date types, depending on the API of the Spring Batch version in use. Choose a type that fits the meaning of the data and keep the representation stable between runs.

An important note: builder methods that do not specify the identifying flag may apply a default value depending on the version's API. When the JobInstance identity has business meaning, you should pass the flag explicitly so that readers of the code immediately understand which parameters affect the identity.

## 4. Distinguishing identifying and non-identifying parameters

The two groups of parameters serve different purposes:

| Parameter type | `identifying` | Affects JobInstance | Examples |
|---|---:|---|---|
| Identifying parameter | `true` | Yes | Business date, batch ID, source system, input file version. |
| Non-identifying parameter | `false` | No | Requester, trace information, operational notes, or intake information. |

### Identifying parameters

Identifying parameters must describe the logical unit of work. If two requests process two different datasets, they usually need at least one different identifying value.

For example, a reconciliation job by date and source system could use:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .toJobParameters();
```

The business date and the source system determine one reconciliation scope. Running the same job with a different date or a different source creates a new JobInstance.

### Non-identifying parameters

A non-identifying parameter can still be read in the job, but changing its value does not create a new JobInstance.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "manual-user", false)
        .addString("requestId", "REQ-83921", false)
        .toJobParameters();
```

Here, `requestedBy` and `requestId` are request-tracking information. If only `requestId` changes, Spring Batch still identifies the same JobInstance because the identifying parameters have not changed.

This also means you should not put a value that changes the dataset or the business result into the non-identifying group. If `inputFile` changes to a file containing different data but is still not identifying, two requests may be treated as the same logical piece of work. Choose identifying parameters based on the data that actually needs to be processed.

## 5. The relationship between JobInstance and JobExecution

A `JobInstance` represents a logical processing unit. A `JobExecution` represents one specific execution of that unit. A JobInstance can have multiple JobExecutions if a previous run failed and was restarted.

```text
Job: importOrdersJob
          |
          +-- JobInstance (businessDate=2026-11-15)
                    |
                    +-- JobExecution #1: FAILED
                    |
                    +-- JobExecution #2: COMPLETED

          +-- JobInstance (businessDate=2026-11-16)
                    |
                    +-- JobExecution #3: COMPLETED
```

When launching again with the same job name and the same identifying parameters:

- If the JobInstance has never run, Spring Batch creates the instance and the first execution.
- If the instance has an active execution, another launch request is usually rejected.
- If the previous execution failed or stopped in a way that allows restart, the framework can create a new execution for the same instance.
- If the instance has already completed, calling again with the same identity usually raises `JobInstanceAlreadyCompleteException`.

Thus, JobParameters help the framework determine which piece of work a request belongs to; the stored state of the JobInstance determines whether the next request can be executed as a new run or as a restart.

## 6. Which parameter changes create a new JobInstance?

Only changing identifying parameters changes the identity. Changing a non-identifying parameter does not create a new instance.

Suppose the initial parameter set is:

```text
businessDate = 2026-11-15   identifying = true
sourceSystem = ERP          identifying = true
requestedBy  = scheduler    identifying = false
```

| Run | Change | Identity result |
|---|---|---|
| A | Initial parameter set | Creates instance A |
| B | Only change `requestedBy` to `operator` | Still instance A |
| C | Change `businessDate` to `2026-11-16` | Creates instance B |
| D | Change `sourceSystem` to `CRM` | Creates instance C |
| E | Change both the date and the source | Creates instance D |

Remember that changing a non-identifying parameter does not create a new JobInstance. If the current instance is already `COMPLETED`, calling the launcher again with the same identifying parameters can still be rejected, even if the `requestedBy` value is different.

## 7. JobParameters and JobParametersValidator solve two different problems

The identifying property answers the question: "Which JobInstance does this parameter set represent?" It does not by itself check whether the parameters are valid from a business perspective.

For example, `businessDate=2026-11-15` may be a valid value, while `businessDate=tomorrow` may not match the format the application requires. Both can still be structurally identifying values, but the application needs a validator to reject invalid data.

Spring Batch supports `JobParametersValidator` to check parameters before the job executes. For example, you can check required parameters such as the business date and the input file:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(parameters -> {
                String businessDate = parameters.getString("businessDate");
                String inputFile = parameters.getString("inputFile");

                if (businessDate == null || businessDate.isBlank()) {
                    throw new JobParametersInvalidException(
                            "businessDate is required");
                }
                if (inputFile == null || inputFile.isBlank()) {
                    throw new JobParametersInvalidException(
                            "inputFile is required");
                }
            })
            .start(importOrdersStep)
            .build();
}
```

The example above uses a lambda to illustrate the check. In a real application, you can extract the validator into a separate bean and check the date format, whether the file exists, whether the data range is valid, and whether the caller is authorized to process it.

A parameter being identifying does not mean it is required. A parameter being non-identifying also does not mean it needs no validation. The two concepts serve two different purposes.

## 8. Choosing identifying parameters by business unit

Choosing identifying parameters should start from the question: "Which pieces of information identify one logical processing run in the business?" Do not decide based only on which values happen to be available in the request.

Examples for some jobs:

| Job type | Identifying parameters that can be used | Reason |
|---|---|---|
| Daily order import | `businessDate`, `sourceSystem` | Each day and data source is one import unit. |
| Import of one uploaded file | `batchId` or an immutable file ID | Each file/batch must be processed exactly once logically. |
| Account reconciliation | `businessDate`, `accountGroup` | Distinguishes the reconciliation period and the account scope. |
| Monthly report generation | `reportMonth`, `reportType` | Each report type for a month is one unit of work. |
| Synchronization by ID range | `fromId`, `toId`, `sourceSystem` | Distinguishes the range of records being processed. |

There is no single parameter set for every job. Choose values sufficient to distinguish two datasets or two independent logical processing runs, while staying stable across restarts.

### Using the file path as an identifying parameter

A file path can be an identifying parameter if that path is a stable representation of an input file. However, pay attention to the case where the file is overwritten:

- The first time, `data/orders.csv` contains data A and the job fails.
- Afterwards, the file at the same path is replaced with data B.
- The rerun uses the same identifying parameter `inputFile=data/orders.csv`.

Spring Batch still recognizes the same JobInstance, even though the file content has changed. This can make the old checkpoint no longer fit the new data. For files that can be replaced, use an immutable batch ID, a file version, or a content checksum as part of the identity; also store the input file immutably throughout the restart lifecycle.

## 9. Normalizing parameter values for a stable identity

Two values with the same business meaning but different representations can still produce different identities. For example:

```text
businessDate = 2026-11-15
businessDate = 15/11/2026
```

If the application passes these two strings as different values, Spring Batch may treat them as two different identifying values. Similarly, differences in upper/lower case, whitespace, or time zone also need to be handled consistently according to the application's conventions.

Some principles:

- Use a standard format for dates and times, such as a consistent ISO representation.
- Normalize system codes, customer codes, or batch codes before creating the parameters.
- Remove extra whitespace if whitespace carries no business meaning.
- Specify the time zone explicitly when a parameter has a time component.
- Do not use temporary paths that change with every upload if they are not a business identity.
- Do not reuse the same identity for different input contents.

Normalization helps avoid creating JobInstances that are duplicates from a business perspective but differ in how the parameters are represented.

## 10. Timestamp and UUID: when should they be used?

A common mistake is adding a new timestamp or UUID to every JobLauncher call and marking it identifying:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("requestId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

Because `requestId` changes on every call, each request creates a new JobInstance. This approach can be appropriate if each request really is an independent processing unit that must be run separately. But if the goal is to restart a failed instance, this approach means the application no longer reuses the old identity.

If the UUID only serves tracing or recording the request, it can be marked non-identifying:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("requestId", UUID.randomUUID().toString(), false)
        .toJobParameters();
```

However, make sure `requestId` does not change the dataset or the business logic. If each request UUID represents a meaningful independent processing run, it should take part in identification. If it is merely a code for tracking an intake, it should usually be non-identifying.

## 11. New run, restart, and rerunning the same data

These three requests need to be clearly distinguished:

### New run for a different data unit

For example, the order import job has processed 15/11 and needs to process 16/11. Pass `businessDate=2026-11-16` if the date is identifying. Spring Batch creates a new JobInstance.

### Restart a failed instance

If the job for 15/11 failed, reuse the same job name and the identifying parameters of that run. Spring Batch creates a new JobExecution for the same JobInstance if the state and configuration allow it.

### Reprocessing the same data under a new business request

Sometimes the business requires rerunning data that has already completed, for example rerunning a report after changing the algorithm or performing a controlled reprocessing batch. This is a new processing unit from a business perspective, not a restart of the old execution. An additional identifying parameter is needed, such as `reprocessVersion`, `reprocessBatchId`, or an explicitly issued processing-run ID.

Do not delete the metadata of a completed JobInstance just to call again with the same parameters. Doing so can lose history and leave the framework unable to recognize the relationship between executions.

## 12. JobParametersIncrementer and generating the next identity

Some jobs need to create a new JobInstance on every run, even if the other business parameters do not change. Spring Batch has `JobParametersIncrementer` to help generate the next parameter set based on the previous one.

A familiar example is `RunIdIncrementer`, commonly used to increment the `run.id` parameter:

```java
@Bean
Job reportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("reportJob", jobRepository)
            .start(reportStep)
            .incrementer(new RunIdIncrementer())
            .build();
}
```

The incrementer describes how to produce the parameter set for the next instance when invoked by an API or orchestration component that supports this mechanism, such as the start-next-instance operation of `JobOperator`. Merely declaring an incrementer does not mean every `JobLauncher.run(job, parameters)` call will automatically increment `run.id`; when calling JobLauncher directly, the application still passes a specific set of JobParameters.

`run.id` is usually an identifying parameter. When the value increments, a new JobInstance is created. This is appropriate for intentionally independent logical runs, but you should not increment the run ID when you want to restart a failed instance.

## 13. How do JobParameters differ from ExecutionContext?

Both components can hold key-value data but serve different purposes.

| Criterion | `JobParameters` | `ExecutionContext` |
|---|---|---|
| Source | Provided when the job is launched. | Updated by the job/step during execution. |
| Purpose | Describes the input of one processing run and identifies the JobInstance through identifying parameters. | Stores runtime state and checkpoints to support restart or to exchange metadata between steps. |
| Timing | Exists before the job starts. | Updated while running. |
| Examples | Business date, input file, source system. | The file line already read, an intermediate file name, the number of items processed. |

For example, `businessDate` is a JobParameter because it identifies the business period. `currentLine` can be a value in the Step ExecutionContext because it represents the reader's progress. Do not use ExecutionContext to replace identifying input parameters, and do not use JobParameters to store continuously changing checkpoints.

## 14. JobRepository stores and looks up identity

Spring Batch uses `JobRepository` to store the metadata of JobInstances and their executions. In a database-backed configuration, the repository writes information into the framework's metadata tables.

When the JobLauncher receives a request, the JobRepository helps determine the corresponding JobInstance based on the job name and identifying parameters. The repository also manages the creation of JobExecutions, stores state, and supports history queries.

This has an operational consequence: if the metadata is deleted or the repository is not durable, the framework may lose the ability to recognize previous instances. In environments that need restart across application launches, use a JobRepository that stores metadata durably and keep the schema compatible with the Spring Batch version.

JobRepository does not by itself guarantee that business data is not duplicated. It manages the framework's identity and execution state. Unique constraints, idempotency, and concurrency control on business tables are still designed by the application.

## 15. Common JobParameters design mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Marking a new UUID as identifying on every run | Each request creates a new JobInstance; restart does not find the old instance. | Use a UUID as identifying only when it represents an independent processing unit. |
| Putting parameters that affect data into the non-identifying group | Two different datasets may be treated as the same JobInstance. | Put every attribute needed to distinguish the data into the identifying parameters. |
| Using the same identifying parameters for multiple business periods | A later request may hit an already-completed or already-running instance error. | Add identifying values that accurately reflect the period or processing scope. |
| Changing the parameter format between runs | The same business meaning can create several different instances. | Normalize the format before building JobParameters. |
| Using a file that can be overwritten as the identifying input | Restart may read new content with an old checkpoint. | Store the file immutably and identify by batch ID or version/checksum. |
| Thinking identifying is the same as required | A missing parameter can still produce a parameter set if there is no validator. | Use JobParametersValidator to check required parameters and format. |
| Thinking non-identifying means not used in the job | Misses tracking information that is needed. | Use non-identifying for metadata that does not change the processing unit. |
| Adding a run ID yourself on restart | Accidentally creates a new instance instead of continuing the old one. | Keep the identity unchanged on restart; only increment the run ID for a new processing run. |

## 16. Process for designing identifying parameters

When building a new job, you can follow these steps:

1. **Identify the business processing unit:** for example a file, a day, an account group, or an ID range.
2. **List the input data that affects the result:** determine which values make two runs into two different logical pieces of work.
3. **Choose identifying parameters:** put the values needed to distinguish processing units into the identifying group.
4. **Choose non-identifying parameters:** add trace information, the requester, or operational notes if needed without changing the identity.
5. **Normalize values:** standardize the format of dates, codes, paths, time zones, and the representation of data ranges.
6. **Build a validator:** check required parameters, data types, and business rules before running.
7. **Define rerun behavior:** clarify which cases are a new run, which are a restart, and which are intentional reprocessing.
8. **Check the repository:** ensure metadata is stored durably and that application instances see a consistent state.
9. **Check side effects:** ensure that restart or rerun does not create duplicate data in the business system.

Example of a complete parameter set:

```java
JobParameters parameters = new JobParametersBuilder()
        // Identify the business period and the data source.
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .addString("batchId", "ERP-20261115-001", true)

        // Only for request tracking.
        .addString("requestedBy", "nightly-scheduler", false)
        .addString("requestId", "REQ-83921", false)
        .toJobParameters();
```

Here, the business date, source system, and batch ID determine the dataset to process. The requester and request ID only support tracking. To restart, the application reuses these identifying parameters. To process a different batch, the batch ID or another suitable identifying value must change.

## 17. Key points to remember

- A `JobInstance` is identified by the `Job` name and the `JobParameters` with `identifying=true`.
- Changing an identifying parameter creates a new JobInstance; changing a non-identifying parameter does not change the identity.
- A JobInstance can have multiple JobExecutions across restarts.
- To restart, you must reuse the exact job name and identifying parameters of the failed instance.
- Do not add a timestamp or UUID that changes on every run to the identifying parameters if the goal is restart.
- Parameters that affect the dataset or the business result usually must take part in identification.
- Identifying is not the same as required; use JobParametersValidator to check required parameters and validity.
- Normalize parameter values and keep input data immutable so that a restart does not use the wrong data.
- `JobParameters` are the job's input; `ExecutionContext` stores runtime state and checkpoints.
- `JobParametersIncrementer` can generate a parameter set for a next instance when used by a suitable orchestration API; JobLauncher does not automatically increment parameters just because a job has an incrementer.

When reading the code of a Spring Batch application, look for where `JobParameters` are created, check the identifying flag of each value, and compare them against the business data unit. From there you can understand why one request creates a new JobInstance, why another request is treated as a restart, and how to design parameters that are stable for both operations and failure recovery.
