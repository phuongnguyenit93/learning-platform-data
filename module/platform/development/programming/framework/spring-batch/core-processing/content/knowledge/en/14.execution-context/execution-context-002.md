# JobExecutionContext and StepExecutionContext

In Spring Batch, `ExecutionContext` is a key-value storage area that the framework uses to hold execution state between processing stages and to support restart. There are two main context scopes: **JobExecutionContext**, which is tied to one Job execution, and **StepExecutionContext**, which is tied to one Step execution.

Both contexts can hold data that needs to be persisted, but their usage scope and update timing differ. The job context is suitable for information that needs to be shared among multiple Steps within the same JobExecution. The step context is suitable for the private state of a single Step, especially the reader's checkpoint or processing progress that must be restored when the Step is restarted.

## 1. What Is ExecutionContext?

`ExecutionContext` is a key-value structure managed by Spring Batch and stored in the `JobRepository`. Components in a Job can write state into the context and read that state back during execution.

For example, a data-import Job may need to store:

- The version of the input file that has been validated.
- The number of valid records after the validation Step.
- The data snapshot ID used in the run.
- The current read position of a file or database reader.
- The last key processed when reading page by page.

`ExecutionContext` provides operations such as `putString`, `putLong`, `putInt`, `put`, and the corresponding getter methods. For example:

```java
ExecutionContext context = new ExecutionContext();
context.putString("sourceVersion", "v3");
context.putLong("validRecordCount", 12_500L);

String version = context.getString("sourceVersion");
long count = context.getLong("validRecordCount");
```

The code above only illustrates the context API. In a Spring Batch application, the context is typically obtained from the `JobExecution` or `StepExecution` that the framework creates and manages, rather than creating a new context yourself and expecting the framework to persist it.

## 2. Two Context Scopes

Each `JobExecution` has a JobExecutionContext. Each `StepExecution` has its own StepExecutionContext. A JobExecution can run multiple Steps; the Steps can share data through the JobExecutionContext, whereas the StepExecutionContext belongs to its corresponding Step.

```text
JobInstance
    |
    v
JobExecution
    |
    +---- JobExecutionContext
    |       (data shared within a Job run)
    |
    +---- StepExecution A
    |        |
    |        +---- StepExecutionContext A
    |
    +---- StepExecution B
    |        |
    |        +---- StepExecutionContext B
    |
    +---- StepExecution C
             |
             +---- StepExecutionContext C
```

| Criterion | JobExecutionContext | StepExecutionContext |
|---|---|---|
| Scope | One JobExecution | One StepExecution |
| Who can use it? | Steps within the same JobExecution | The executing Step and components that belong to that Step |
| Suitable data | Intermediate results or parameters that later Steps need | Reader checkpoint, internal state, and the Step's own progress |
| Metadata storage | Tied to the JobExecution | Tied to the StepExecution |
| Restart | Restored for the next run of the same JobInstance according to the saved metadata | Used to restore Step state when the Step is restarted |

The JobExecutionContext is not a shared memory area for all Jobs in the application. It belongs to a specific JobExecution. The StepExecutionContext is also not automatically shared between different Steps.

## 3. What Is JobExecutionContext Used For?

JobExecutionContext is suitable when one Step produces information that the next Step needs to use. For example:

1. The first Step checks the input file and determines the version.
2. The next Step imports data according to the validated version.
3. The last Step creates a report using the number of imported records.

Values such as `sourceVersion`, `validRecordCount`, or `batchReference` can be stored in the JobExecutionContext so later Steps can access them.

### Writing to JobExecutionContext

In a Tasklet, you can access the JobExecution through the StepExecution:

```java
@Component
public class RecordBatchMetadataTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution
                .getStepExecution()
                .getJobExecution();

        ExecutionContext jobContext = jobExecution.getExecutionContext();
        jobContext.putString("sourceVersion", "v3");
        jobContext.putLong("validRecordCount", 12_500L);

        return RepeatStatus.FINISHED;
    }
}
```

The JobExecutionContext can be read by later Steps through their JobExecution. Spring Batch manages persisting the context metadata at Job/Step lifecycle milestones. When a Step completes, the JobExecutionContext is updated in the repository so subsequent Steps and the restart process can use the saved state.

### Reading JobExecutionContext in the Next Step

With a bean annotated with `@StepScope`, you can late-bind the value using SpEL:

```java
@Bean
@StepScope
Tasklet createSummaryTasklet(
        @Value("#{jobExecutionContext['validRecordCount']}") Long validRecordCount,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        SummaryService summaryService) {

    return (contribution, chunkContext) -> {
        summaryService.createSummary(validRecordCount, sourceVersion);
        return RepeatStatus.FINISHED;
    };
}
```

`jobExecutionContext` is the SpEL context that Spring Batch provides in the appropriate scope. `@StepScope` causes the value to be obtained once the current StepExecution exists. You need to handle the case where the key has no value, if the previous Step did not run, was skipped, or did not write that key.

## 4. What Is StepExecutionContext Used For?

StepExecutionContext is for the internal state of a single Step. For example:

- The byte position or line number read from a file.
- The last page or key read from a database.
- The number of items processed in a multi-pass task.
- Temporary codes or intermediate state that only the current Step needs.

In a Tasklet, you can obtain the StepExecutionContext from the `StepContribution`:

```java
@Component
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext stepContext = contribution
                .getStepExecution()
                .getExecutionContext();

        stepContext.putString("validatedFile", "customers-20261115.csv");
        stepContext.putInt("validationWarnings", 4);

        return RepeatStatus.FINISHED;
    }
}
```

These values belong to the current Step. Other Steps do not automatically see them through their own StepExecutionContext. If a later Step needs to use `validatedFile`, you need to move that value to the JobExecutionContext, for example using `ExecutionContextPromotionListener`.

## 5. Promotion: Moving Data from Step Context to Job Context

A common pattern is for a Step to write its results to the StepExecutionContext, and then promote selected keys to the JobExecutionContext when the Step completes. Spring Batch provides `ExecutionContextPromotionListener` for this purpose.

### Declaring the Listener

```java
@Bean
ExecutionContextPromotionListener promoteValidationResults() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {
            "validatedFile",
            "validationWarnings"
    });

    return listener;
}
```

### Attaching the Listener to the Step

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateInputTasklet tasklet,
        ExecutionContextPromotionListener promoteValidationResults) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(promoteValidationResults)
            .build();
}
```

When the Step ends with an appropriate ExitStatus (by default the listener typically promotes only on `COMPLETED`), the declared keys are copied from the StepExecutionContext to the JobExecutionContext. You can configure the statuses that are allowed to promote if the business needs different behavior; you should not promote invalid data or the results of a failed Step.

After that, the next Step can read `validatedFile` or `validationWarnings` through `jobExecutionContext`. This approach makes it clear which data is allowed to leave the Step scope and be shared with the rest of the Job.

## 6. How Do JobParameters Differ from ExecutionContext?

JobParameters and ExecutionContext can both contain data that the Job uses, but they serve two different purposes.

| Criterion | JobParameters | ExecutionContext |
|---|---|---|
| Source | Passed by the caller when launching the Job | Written by the Job/Step/reader during execution |
| Role | Input that defines the work to run | State and checkpoint of the running process |
| Can it be changed in a Step? | No; it is treated as the input of the execution | Yes; the context is updated during the lifecycle |
| Effect on JobInstance | Identifying parameters participate in identifying the JobInstance | Does not participate in identifying the JobInstance |
| Example | Business date, file code, batch ID | Read position, number of valid records, validated version |

For example, `businessDate` should be a JobParameter because the caller chooses the business date to process. Meanwhile, `lastProcessedId` is a checkpoint that the reader updates while reading and belongs in the StepExecutionContext.

Do not use ExecutionContext to replace input JobParameters or to create a new JobInstance. If a run's logic differs by date or file, express that difference using identifying JobParameters.

## 7. How Does the Context Support Restart?

Spring Batch distinguishes between `JobInstance` and `JobExecution`. A JobInstance represents a logical run, identified by the Job name and the identifying JobParameters. If a Job fails and is then restarted, Spring Batch creates a new JobExecution for the same JobInstance.

The saved ExecutionContext metadata is part of the recovery information. On restart, the framework uses the state saved from the previous execution to restore the appropriate Job context and Step context. As a result, a Step can continue from its checkpoint instead of always starting over from the beginning by default.

```text
JobInstance (businessDate=2026-11-15)
        |
        +---- JobExecution 1: FAILED
        |          |
        |          +---- Saved JobExecutionContext
        |          |
        |          +---- StepExecutionContext with checkpoint
        |
        +---- Restart
                   |
                   v
             JobExecution 2
                   |
                   +---- Restores the saved context
                   |
                   +---- Continues the Step from its state/checkpoint
```

For example, the reader has read and committed up to `customerId=5000`. The StepExecutionContext can store the corresponding checkpoint. On restart, the reader restores its position and continues from the unfinished part. The JobExecutionContext can hold the `sourceVersion` that the Step validated so later Steps still use the correct data version.

Restartability also depends on whether the reader supports saving/restoring state, whether the input source is stable, and whether the write operations are safe to perform again. Having an ExecutionContext does not automatically make every external side effect rollback-able.

## 8. A Reader Saving Its Own Checkpoint in StepExecutionContext

Many of Spring Batch's built-in readers implement `ItemStream` and save their state to the StepExecutionContext themselves. For example, `FlatFileItemReader` can save the read position to support restart:

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
            .saveState(true)
            .build();
}
```

With `saveState(true)`, the reader can write state information into the ExecutionContext during the lifecycle managed by Spring Batch. When the Step restarts, the reader uses that information to continue reading. The internal keys are managed by the reader; the application should not modify these keys without a reason and a clear understanding of the reader's contract.

With a custom reader, if you need restart, you can implement `ItemStream` to open the resource, save state, and restore the read position:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

In real implementations, `ItemStreamReader<T>` combines `ItemReader<T>` and `ItemStream`. `open()` receives the saved context to restore from; `update()` writes the current checkpoint; `close()` releases resources. Spring Batch calls these lifecycle methods at the appropriate milestones of the Step.

## 9. When JobExecutionContext and StepExecutionContext Are Saved

Both contexts are stored in the metadata repository, but their update timing is tied to different lifecycles:

- **StepExecutionContext:** with a chunk-oriented Step, the reader state and checkpoint are typically updated at the chunk commit boundary. This enables restoring from the most recently committed checkpoint.
- **JobExecutionContext:** shared among Steps within the same JobExecution and updated by the repository at Job/Step management milestones, especially when a Step completes. Later Steps can read the data that has been saved/promoted.

Do not assume every change to the context is written to the database immediately at the moment `put()` is called. Persistence depends on the Step lifecycle, the transaction, and the repository. If the application is stopped abruptly before the metadata update milestone, changes that were not committed may not exist after restart.

Therefore, store in the context only state that can be restored according to the save milestones the framework provides. If you need to record each business event immediately or store detailed history, use a separate business/audit table with an appropriate transaction, and do not rely on the context as an event log.

## 10. Context Design Principles

### Use Meaningful Keys and Avoid Name Collisions

Name keys so they clearly describe their scope, for example `customerImport.lastProcessedId`, `validation.validRecordCount`, or `report.outputVersion`. Avoid generic names such as `status`, `count`, or `value` when multiple components write to the context.

A separate StepExecutionContext for each Step helps reduce key conflicts. The JobExecutionContext is shared among Steps, so you need a key naming convention and must clearly determine which Step owns writing each key.

### Store Small, Serializable Values

ExecutionContext is stored in the repository, so values must be supported by the configured serializer. Simple types such as String, numbers, booleans, dates represented in a stable way, or small objects with clear serialization are generally suitable.

Avoid storing:

- A list of millions of records.
- File content or large payloads.
- JDBC Connections, HTTP clients, streams, or open resources.
- Spring beans, proxies, or objects containing runtime state that cannot be serialized reliably.
- Passwords, access tokens, or secrets.

Instead of storing large data, store an identifier, path, checksum, or reference key to data managed in an appropriate place. Do not store secrets in the context because the metadata may be accessed by operational tools or by people with permission to read the repository.

### Do Not Use the Context as a Shared Cache

The context serves execution state and restart; it is not a general-purpose cache across multiple JobInstances or multiple nodes. If you need a cache, use a dedicated cache with an appropriate TTL, size limit, and invalidation policy.

### Be Careful with Parallel Steps

Steps that run sequentially can pass data through the JobExecutionContext in flow order. If multiple Steps run in parallel and update the JobExecutionContext at the same time, overwrites or logical conflicts may occur. You should use separate keys, avoid having multiple writers own the same key, and consider storing state in a business repository with transaction control when concurrent updates are needed.

## 11. Accessing the Context via API in Code

Besides SpEL in `@StepScope` beans, you can obtain the context directly from the execution objects.

### Getting the StepExecutionContext

```java
StepExecution stepExecution = contribution.getStepExecution();
ExecutionContext stepContext = stepExecution.getExecutionContext();

stepContext.putLong("processedCount", 2_000L);
long processedCount = stepContext.getLong("processedCount", 0L);
```

### Getting the JobExecutionContext

```java
JobExecution jobExecution = stepExecution.getJobExecution();
ExecutionContext jobContext = jobExecution.getExecutionContext();

jobContext.putString("reportVersion", "2026-11");
String reportVersion = jobContext.getString("reportVersion");
```

### Getting the Context from ChunkContext

`ChunkContext` provides a `StepContext`, from which you can access the context maps for read purposes:

```java
StepContext stepContext = chunkContext.getStepContext();
Map<String, Object> stepValues = stepContext.getStepExecutionContext();
Map<String, Object> jobValues = stepContext.getJobExecutionContext();
```

These maps are useful for reading values in a Tasklet. When you need to write and manage state, you should obtain the `ExecutionContext` from the `StepExecution` or `JobExecution` as in the examples above so you use the official update API.

## 12. Common Mistakes

**Using the StepExecutionContext to pass data to another Step:** a later Step has its own StepExecutionContext and therefore does not automatically see the previous Step's keys. Promote the keys that need to be shared to the JobExecutionContext.

**Putting all data into the JobExecutionContext:** the Job-level context has a broader scope, but it is not a place to hold all state. The reader's internal checkpoint should reside in the StepExecutionContext.

**Confusing ExecutionContext with JobParameters:** JobParameters are launch input and participate in identifying the JobInstance if marked as identifying; ExecutionContext is state that is updated while running.

**Assuming calling `put()` writes to the database immediately:** the repository saves the context according to the lifecycle and transaction. Changes that have not reached a save milestone may be gone after a failure.

**Storing non-serializable objects:** the Job may fail when the repository tries to save the context. Store only values compatible with the configured serializer.

**Storing large payloads or secrets:** the metadata grows large and may expose sensitive data. Store only reference keys or minimal information.

**Letting multiple parallel Steps write the same key:** data may be overwritten or may not reflect the expected result. Assign key ownership or use an appropriate data store for concurrent updates.

**Using the context in place of business tables:** the context serves coordination and restart; data that needs long-term querying, auditing, or business reporting should be stored in the business schema.

## Conclusion

`JobExecutionContext` stores state shared among Steps within the same JobExecution. `StepExecutionContext` stores the private state of a single Step, which is especially useful for the reader's checkpoint and restart. Data that needs to be moved from one Step to another can be promoted using `ExecutionContextPromotionListener`. Distinguish the context from JobParameters, store small serializable values, use clear keys, and understand when the repository updates metadata. When the scopes are designed correctly, the two contexts help a Job share intermediate results and reliably restore progress after a failure.
