# A Tasklet reading the ExecutionContext

In Spring Batch, `ExecutionContext` is a key-value storage area attached to one execution of a job or a step. It helps store runtime state, checkpoints, and small pieces of data that need to be passed between processing phases. A `Tasklet` can read the `ExecutionContext` to continue its work based on previously saved state or to use information produced by an earlier step.

For example, the first step checks the input file and stores the path of the confirmed file. The next step uses a tasklet to read that path from the Job ExecutionContext and then performs the next operation. This approach lets steps exchange metadata without passing a large object through memory or coupling them tightly through global variables.

## 1. ExecutionContext in Spring Batch

`ExecutionContext` is a key-value structure that Spring Batch stores together with the execution metadata. It is commonly used to:

- Store checkpoints of a reader or writer to support restart.
- Store the small amount of state needed to continue a step.
- Share metadata between steps within the same JobExecution.
- Store runtime information such as intermediate file paths, record counts, or batch codes.

There are two main ExecutionContext scopes:

| Scope | Attached to | Lifecycle and purpose |
|---|---|---|
| Step ExecutionContext | One `StepExecution` | Stores the step's own state, for example reader checkpoints, processing position, or internal step metadata. |
| Job ExecutionContext | One `JobExecution` | Stores job-scoped state, commonly used to share small pieces of information between steps. |

Each `StepExecution` has its own ExecutionContext. Each `JobExecution` also has its own ExecutionContext. When a job runs through multiple steps, the steps can access the same Job ExecutionContext through the JobExecution they belong to, while each step still has an independent Step ExecutionContext.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |      +-- validatedFile
  |      +-- batchReference
  |
  +-- StepExecution: validateInputStep
  |      +-- Step ExecutionContext
  |             +-- scannedLine
  |             +-- validationCount
  |
  +-- StepExecution: importDataStep
         +-- Step ExecutionContext
                +-- readerCheckpoint
                +-- writtenCount
```

The Job ExecutionContext has a broader scope and can be used by the steps in the same JobExecution. The Step ExecutionContext belongs to a single step execution and usually holds state serving that step itself.

## 2. Through which objects does a Tasklet get the ExecutionContext?

In Spring Batch, `Tasklet` has an `execute` method with two parameters:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

`StepContribution` and `ChunkContext` provide information about the current execution. From them, the tasklet can get the `StepExecution`, the `JobExecution`, and the two corresponding ExecutionContexts.

The commonly used direct access path is:

```java
StepExecution stepExecution = contribution.getStepExecution();

ExecutionContext stepContext = stepExecution.getExecutionContext();
ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();
```

Where:

- `stepExecution.getExecutionContext()` returns the Step ExecutionContext.
- `stepExecution.getJobExecution().getExecutionContext()` returns the Job ExecutionContext.
- `chunkContext.getStepContext().getStepExecution()` can also be used to get the current StepExecution.

An example of reading both scopes:

```java
@Bean
Step inspectContextStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet inspectTasklet = (contribution, chunkContext) -> {
        StepExecution stepExecution = contribution.getStepExecution();

        ExecutionContext stepContext = stepExecution.getExecutionContext();
        ExecutionContext jobContext =
                stepExecution.getJobExecution().getExecutionContext();

        // Read the values that have been set in the context.
        if (stepContext.containsKey("validatedRecordCount")) {
            long count = stepContext.getLong("validatedRecordCount");
            System.out.println("Step count: " + count);
        }

        if (jobContext.containsKey("batchReference")) {
            String reference = jobContext.getString("batchReference");
            System.out.println("Batch reference: " + reference);
        }

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("inspectContextStep", jobRepository)
            .tasklet(inspectTasklet, transactionManager)
            .build();
}
```

This example assumes the keys were created earlier. In a real application, you need to check that the key exists and that the value has the expected data type before using it.

## 3. Reading values safely from the ExecutionContext

The ExecutionContext is a key-value area. The tasklet needs to know the key name and the data type that was stored. You can use `containsKey` before reading to distinguish the case where the key has not been created from the case where the value is valid.

```java
ExecutionContext context =
        contribution.getStepExecution().getExecutionContext();

if (!context.containsKey("inputFile")) {
    throw new IllegalStateException(
            "ExecutionContext does not contain inputFile");
}

String inputFile = context.getString("inputFile");
```

Some common accessor methods:

| Method | Purpose |
|---|---|
| `putString(key, value)` | Store a string. |
| `getString(key)` | Read a string. |
| `putLong(key, value)` | Store a long integer. |
| `getLong(key)` | Read a long integer. |
| `putInt(key, value)` | Store an integer. |
| `getInt(key)` | Read an integer. |
| `put(key, value)` | Store a value supported by the serializer. |
| `get(key)` | Read a value as an object. |
| `containsKey(key)` | Check whether the key exists. |
| `remove(key)` | Remove the key from the context. |

Give keys meaningful names and avoid reusing the same name for different purposes. For example, `validatedInputFile`, `importedRecordCount`, or `reportOutputPath` are easier to understand than generic names such as `value1` or `data`.

If a key may not exist yet, handle it explicitly. Do not assume that `getString`, `getLong`, or an object cast always returns a valid value. Check the key, the type, and the business conditions before performing the next task.

### Checking the data type

When using `put` and `get`, the value is stored as an object. You need to ensure the written type and the read type are compatible:

```java
context.put("recordCount", 125L);

Object value = context.get("recordCount");
if (!(value instanceof Long recordCount)) {
    throw new IllegalStateException("recordCount has an unexpected type");
}
```

For common types such as String, Long, or Integer, the specialized methods `putString`, `getString`, `putLong`, and `getLong` make the code easier to read. For custom objects, you need to ensure the ExecutionContext serializer can store and restore that data type.

## 4. A Tasklet reading the Step ExecutionContext

The Step ExecutionContext suits data that is only meaningful within the current step. For example, a tasklet that splits work into multiple calls can store the number of passes or a checkpoint specific to the step.

An example of a tasklet reading a saved position:

```java
@Bean
Step resumeLocalWorkStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();

        long lastProcessedId = context.containsKey("lastProcessedId")
                ? context.getLong("lastProcessedId")
                : 0L;

        // Continue the work from the next ID.
        long nextId = lastProcessedId + 1;
        System.out.println("Continue from ID: " + nextId);

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("resumeLocalWorkStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

In the example, `lastProcessedId` belongs to this step alone. If the job has another step, that step does not automatically see the current step's Step ExecutionContext.

If the tasklet needs to update state so that the next call in the same step continues from the new position, it can write a value into the context:

```java
context.putLong("lastProcessedId", nextId);
```

Saving state must be tied to the transaction and the execution lifecycle. In a tasklet step, each call to `execute` is coordinated within a transaction according to the step configuration. If the tasklet returns `RepeatStatus.CONTINUABLE`, the framework can call the tasklet again; you need to design the context updates and the business operations to be consistent so that the next call does not wrongly repeat work.

## 5. A Tasklet reading the Job ExecutionContext

The Job ExecutionContext suits metadata that needs to be shared between steps belonging to the same JobExecution. For example, the first step checks the file and stores the confirmed path; the later step reads that path to import.

A tasklet can get the Job ExecutionContext through the StepExecution:

```java
ExecutionContext jobContext = contribution.getStepExecution()
        .getJobExecution()
        .getExecutionContext();

if (!jobContext.containsKey("validatedInputFile")) {
    throw new IllegalStateException("validatedInputFile is missing");
}

String inputFile = jobContext.getString("validatedInputFile");
```

Values in the Job ExecutionContext exist at the JobExecution scope. If the job is restarted and a new JobExecution is created for the same JobInstance, the Job ExecutionContext of the previous execution is not a permanently shared state area for every execution. Data that needs to be restored must be saved and recovered through Spring Batch's restart mechanism, or recreated by the earlier steps according to the flow.

Do not use the Job ExecutionContext as a global store across different job runs. If data must exist independently of the JobExecution, save it in the business database or an appropriate storage system and then pass a reference key through the parameters/context.

## 6. Moving data from the Step ExecutionContext to the Job ExecutionContext

A step usually writes data into the Step ExecutionContext. For the next step to read that data at the job scope, you can use `ExecutionContextPromotionListener`.

For example, the file-checking step stores the confirmed path in the Step ExecutionContext:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener promotionListener) {

    Tasklet validateTasklet = (contribution, chunkContext) -> {
        String validatedFile = "data/ready/orders.csv";

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("validatedInputFile", validatedFile);

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateTasklet, transactionManager)
            .listener(promotionListener)
            .build();
}

@Bean
ExecutionContextPromotionListener promotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[]{"validatedInputFile"});
    return listener;
}
```

When the step completes with a status the listener allows (by default `COMPLETED`), the listener moves the configured keys from the Step ExecutionContext to the Job ExecutionContext. The later step can read `validatedInputFile` from the Job ExecutionContext.

```text
validateInputStep
       |
       | Step ExecutionContext:
       | validatedInputFile = data/ready/orders.csv
       |
       v
ExecutionContextPromotionListener
       |
       v
Job ExecutionContext:
  validatedInputFile = data/ready/orders.csv
       |
       v
importOrdersStep reads the value
```

Only promote the keys that other steps need. Avoid moving all of a step's internal state into the Job ExecutionContext, because that widens the scope of shared data and easily causes key-name collisions.

### Configuring the promotion statuses

The listener can be configured to promote keys when the step ends with certain `ExitStatus` values. By default, the listener usually applies to `COMPLETED`. If you change the list of statuses, make sure you only promote when the data has been fully and validly created.

If a key does not exist in the Step ExecutionContext, the behavior may depend on the listener's strict configuration. When the data is mandatory, enable strict checking or check the key yourself before the step ends so that errors are detected early.

## 7. A Tasklet reading context through late binding

Besides getting the `ExecutionContext` directly from the `StepContribution`, Spring Batch also supports late binding in beans with `@StepScope`. Context values can be injected through SpEL.

Some common expressions:

| Expression | Data source |
|---|---|
| `#{jobParameters['inputFile']}` | The JobParameters of the run. |
| `#{stepExecutionContext['checkpoint']}` | The Step ExecutionContext of the current step. |
| `#{jobExecutionContext['validatedInputFile']}` | The Job ExecutionContext of the current JobExecution. |

An example of a tasklet reading a promoted value:

```java
@Bean
@StepScope
Tasklet importValidatedFileTasklet(
        @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalStateException("No validated input file found");
        }

        // Perform the operation that uses inputFile.
        System.out.println("Importing: " + inputFile);
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` is very important in this case because the context value only exists once the step execution starts. If you inject a runtime value into a singleton bean created when the application context starts, the expression may not be evaluated in the correct execution scope.

Late binding suits cases where a tasklet or reader needs a simple value. If you need to check many keys, handle complex types, or have fallback logic, reading the ExecutionContext directly through the StepExecution can be clearer.

## 8. A complete example: the first step writes context, the later tasklet reads it

Suppose the job has two steps:

1. `prepareFileStep`: checks the input file and stores the confirmed path in the Step ExecutionContext.
2. `importFileStep`: receives the path that has been promoted to the Job ExecutionContext and performs the import operation.

```java
@Configuration
public class FileImportJobConfiguration {

    @Bean
    ExecutionContextPromotionListener filePromotionListener() {
        ExecutionContextPromotionListener listener =
                new ExecutionContextPromotionListener();
        listener.setKeys(new String[]{"validatedInputFile"});
        return listener;
    }

    @Bean
    Step prepareFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ExecutionContextPromotionListener filePromotionListener) {

        Tasklet prepareTasklet = (contribution, chunkContext) -> {
            String file = "data/ready/orders.csv";

            // You can check the file's existence, read permission, and metadata here.
            contribution.getStepExecution()
                    .getExecutionContext()
                    .putString("validatedInputFile", file);

            return RepeatStatus.FINISHED;
        };

        return new StepBuilder("prepareFileStep", jobRepository)
                .tasklet(prepareTasklet, transactionManager)
                .listener(filePromotionListener)
                .build();
    }

    @Bean
    @StepScope
    Tasklet importFileTasklet(
            @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {

        return (contribution, chunkContext) -> {
            if (inputFile == null || inputFile.isBlank()) {
                throw new IllegalStateException("validatedInputFile is missing");
            }

            // Perform the import work using inputFile.
            System.out.println("Import file: " + inputFile);
            return RepeatStatus.FINISHED;
        };
    }

    @Bean
    Step importFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet importFileTasklet) {

        return new StepBuilder("importFileStep", jobRepository)
                .tasklet(importFileTasklet, transactionManager)
                .build();
    }

    @Bean
    Job fileImportJob(
            JobRepository jobRepository,
            Step prepareFileStep,
            Step importFileStep) {

        return new JobBuilder("fileImportJob", jobRepository)
                .start(prepareFileStep)
                .next(importFileStep)
                .build();
    }
}
```

The example illustrates the metadata-exchange mechanism. In a real application, the preparation step must check the actual file and should store an immutable identifier or a path that has been fixed for the batch. The import step needs to process the file with appropriate business logic, and can use a chunk-oriented step if it needs to read and write many items.

## 9. How do ExecutionContext and JobParameters differ?

Both components provide data to the job but have different origins and purposes.

| Criterion | JobParameters | ExecutionContext |
|---|---|---|
| Source | Provided when the job is launched. | Updated during execution by the job, a step, or a stream component. |
| Role | Input that identifies the unit of processing; identifying parameters contribute to determining the JobInstance. | Stores runtime state, checkpoints, and metadata between steps. |
| When data is available | Available before the job starts. | Can be created or updated while the job/step runs. |
| Scope | Attached to the JobExecution and to JobInstance identity through identifying values. | Has JobExecution or StepExecution scope. |
| Examples | `businessDate`, `inputFile`, `sourceSystem`. | `validatedInputFile`, `lastProcessedId`, `readerCheckpoint`. |

If the caller supplies the business date, it is usually a JobParameter. If a step checks the file and only then determines the accepted path, that path can be written to the ExecutionContext. Do not use the ExecutionContext in place of the job's initial identifying parameters.

## 10. ExecutionContext and restart

The ExecutionContext supports restart because the state is stored in the JobRepository together with the execution metadata. However, you need to clearly understand which execution a context belongs to and when the state is saved.

### Step ExecutionContext

The Step ExecutionContext usually holds the step's own checkpoints. In a chunk-oriented step, Spring Batch updates the stream state at the commit boundary. In a tasklet step, each tasklet call is managed in a transaction according to the configuration; the step state is saved according to the corresponding execution lifecycle.

If a tasklet updates the context and then the transaction rolls back, do not assume that change has been durably saved. Updating the context and the related business operations need to be part of a consistent transaction design.

### Job ExecutionContext

The Job ExecutionContext stores state shared within one JobExecution. Data needed by a later step can be promoted from an earlier step. When a job restarts, Spring Batch creates a new JobExecution for the same JobInstance; the new execution's context is restored or built according to the framework's restart mechanism and the steps that run again. Do not regard the Job ExecutionContext as a variable shared among all the JobExecutions of a JobInstance.

For example, if `prepareFileStep` has completed and `importFileStep` fails, when the same JobInstance is restarted, the completed step is usually skipped. The new execution's Job ExecutionContext is initialized according to the framework's metadata/restart state. If the promoted data needs to be reused, you must ensure that the restart mechanism and the corresponding context data are saved/restored correctly; otherwise, design the flow so the preparation step runs again or recreates the necessary metadata.

For important data, do not rely solely on a context key without checking the existence and validity of the referenced resource. Check the file, batch ID, or version before using it.

## 11. Choosing the right context scope

Not every value should go into the Job ExecutionContext. Choose the scope based on where the data is used and its lifecycle.

| Data | Usually suitable place to store | Reason |
|---|---|---|
| The reader's current line position | Step ExecutionContext | State specific to the reader/step. |
| The number of items processed in a step | Step ExecutionContext or StepExecution counters | Only meaningful within that step. |
| A checked file needed in the next step | Step ExecutionContext, then promote to the Job ExecutionContext | Metadata that must be shared within the same JobExecution. |
| A business date passed in by the scheduler | JobParameters | It is the input of the run and can take part in identity. |
| A large payload or a list of hundreds of thousands of records | Database, file, or object storage | The ExecutionContext should only hold small metadata. |
| State that must persist across multiple JobExecutions or multiple jobs | Business database or a dedicated storage system | Context is attached to an execution; it is not a long-term data store. |

The Job ExecutionContext should contain small values such as a file path, a batch reference, a snapshot version, or aggregate counts. If you need to share a large data set, store the data in an appropriate place and put only a key or a reference path into the context.

## 12. Rules for naming keys and managing context data

The ExecutionContext is a shared map within its scope. If multiple steps write keys with the same name, values can be overwritten or cause confusion.

Some useful rules:

- Use key names that clearly describe their meaning, for example `validatedInputFile` instead of `file`.
- You can add a prefix by step or business domain, for example `validation.outputFile` or `orders.batchReference`.
- Keep the data types consistent between where it is written and where it is read.
- Check required keys before using them.
- Store only the small data needed for orchestration or restart.
- Remove a key when it is no longer needed if keeping it causes confusion or increases the metadata size.
- Do not store passwords, tokens, or secret information in the ExecutionContext without an appropriate protection mechanism.

An example of writing multiple values:

```java
ExecutionContext context = contribution.getStepExecution()
        .getExecutionContext();

context.putString("validation.outputFile", "data/ready/orders.csv");
context.putLong("validation.recordCount", 1200L);
context.putString("validation.batchReference", "BATCH-20261115-01");
```

When reading, use the correct key and type:

```java
ExecutionContext context = contribution.getStepExecution()
        .getExecutionContext();

String outputFile = context.getString("validation.outputFile");
long recordCount = context.getLong("validation.recordCount");
String batchReference = context.getString("validation.batchReference");
```

If keys may not exist in one branch of the flow, check before reading and clearly define the behavior when data is missing.

## 13. Serialization and the stored data types

The ExecutionContext is stored through the JobRepository, so values must be writable and readable by Spring Batch's serializer. Simple data types such as String, integers, and Boolean are usually convenient. For custom objects, pay attention to the serializer and to compatibility when deploying a new version of the application.

Do not store objects that depend on open resources directly, such as `InputStream`, `ResultSet`, `EntityManager`, or service beans. These objects are not state that can be safely recovered after the process ends.

Instead, store enough information to reopen the resource:

```java
context.putString("inputFilePath", "/data/batch/orders.csv");
context.putLong("lastProcessedId", 98765L);
context.putString("snapshotVersion", "CUSTOMER-2026-11-15");
```

On restart, the tasklet or reader uses these values to reopen the file, build a query, or choose the right snapshot. If you use a custom object, make sure the schema/data type does not change in a way that makes the old metadata impossible to deserialize.

## 14. Common mistakes when a Tasklet reads the ExecutionContext

| Problem | Common cause | How to handle |
|---|---|---|
| Key not found | The earlier step has not written the key, the flow branched, or promotion has not run. | Check the step that creates the data, the promotion listener, and the flow branch. |
| Reading the wrong Step ExecutionContext | The key is stored in the Job ExecutionContext or vice versa. | Identify the correct scope when writing and reading. |
| The later step does not see the earlier step's data | Written only to the Step ExecutionContext but not promoted. | Use `ExecutionContextPromotionListener` or an appropriate data-passing mechanism. |
| Value of the wrong type | The writer and the reader use different types. | Use keys with a clear type convention and check before casting. |
| The value is no longer correct after restart | The file or resource has changed; the context only stores the old path. | Keep the resource immutable and store a batch ID/version/checksum. |
| The context holds too much data | The ExecutionContext is used as a data store. | Store large data in a database/file/object storage and keep only a reference. |
| A context update is not saved as expected | The transaction rolled back or the update happened outside the framework-managed lifecycle. | Update within a transaction and understand when checkpoints are persisted. |
| Old data is overwritten | Multiple steps share a key or use names that are too generic. | Use namespaced keys and clearly define ownership. |
| Deserialization error after an upgrade | A stored custom object is incompatible with the new version. | Prefer stable data types, manage versions, and plan for metadata compatibility. |

## 15. How to read Tasklet code that uses the ExecutionContext

When you encounter a tasklet that reads context, follow these steps:

1. **Find the key's source:** find where `putString`, `putLong`, or `put` is called, or where a reader/writer stores a checkpoint.
2. **Determine the scope:** is the key in the Step ExecutionContext or the Job ExecutionContext?
3. **Check promotion:** if another step needs to use the current step's key, is there a listener or promotion mechanism?
4. **Check the data type:** do the writer and the reader use the same type?
5. **Check when it is saved:** in which transaction, and at which commit boundary, is the context updated?
6. **Check restart:** when the step runs again, is the key restored, recreated, or does it require the earlier step to run again?
7. **Check the referenced resource:** is the file, snapshot, or batch ID still valid?
8. **Check missing-key handling:** does the tasklet report a clear error or accidentally use an unsafe null/default value?

In particular, if the tasklet gets its value with `@Value("#{jobExecutionContext['...']}")`, find the earlier step that wrote and promoted that key. If the tasklet reads directly from `contribution.getStepExecution()`, determine that the context belongs to the correct current StepExecution.

## 16. Key points to remember

- `ExecutionContext` is a key-value area stored together with Spring Batch's metadata.
- The Step ExecutionContext belongs to a StepExecution; the Job ExecutionContext belongs to a JobExecution.
- A tasklet can get the StepExecution from the `StepContribution` or `ChunkContext` and then read the two corresponding context scopes.
- Use `containsKey` and check the data type before using a required key.
- Data in the Step ExecutionContext does not automatically appear in the Job ExecutionContext.
- Use `ExecutionContextPromotionListener` to promote the keys that need to be shared to later steps.
- `@StepScope` combined with SpEL such as `#{stepExecutionContext['key']}` or `#{jobExecutionContext['key']}` supports late binding.
- JobParameters are the input at launch; the ExecutionContext stores state that arises during execution.
- The context should only contain small metadata and data types that can be serialized/deserialized safely.
- Do not treat the Job ExecutionContext as a long-term store shared across all JobExecutions.
- On restart, you must clearly understand which execution owns the context and ensure the referenced resources remain consistent.

When a tasklet reads the ExecutionContext, determine the correct context scope, where the key is created, the data type, and when the state is saved. If you need to move metadata from one step to another, promote it deliberately to the Job ExecutionContext. This approach lets the job exchange small pieces of data clearly and lets that data be tracked and recovered within Spring Batch's execution lifecycle.
