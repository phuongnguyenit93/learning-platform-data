# `@Value` from `jobExecutionContext`

In Spring Batch, `JobExecution` has a job-scoped `ExecutionContext`. This context stores small values that need to be shared across multiple steps within the same job run. One step can produce a file path, staging batch ID, normalized business date, or record count; a subsequent step can read those values to configure a reader, processor, writer, or tasklet.

Spring Batch supports **late binding** via Spring Expression Language (SpEL). For a bean created within a step's scope, you can inject a value from the job execution context using the expression:

```java
@Value("#{jobExecutionContext['generatedFile']}")
String generatedFile
```

`jobExecutionContext` is a context variable provided by Spring Batch while a step is running. The expression is resolved when the scoped target bean is created for the execution, not when the application context starts up. Therefore, a `@StepScope` bean can receive values that a previous step saved and promoted to the job context.

This is a mechanism for sharing small data between steps. It is not a way to pass arbitrary objects across threads or replace a business database. Store IDs, URIs, versions, counts, or small configuration values in the context; large data should reside in a database, staging table, or object storage.

## What is JobExecutionContext?

Each job run has a `JobExecution`. `JobExecution` holds its own job-scoped `ExecutionContext`. Values in this context can be used by steps belonging to the same execution.

```text
JobInstance
    |
    +-- JobExecution #101
           |
           +-- JobExecutionContext
           |      generatedFile = "staging/orders.csv"
           |      importedCount = 12500
           |
           +-- StepExecution: prepareStep
           |      StepExecutionContext
           |        tempFileId = "tmp-42"
           |
           +-- StepExecution: importStep
           |      StepExecutionContext
           |        lastReadLine = 800
           |
           +-- StepExecution: summaryStep
                  StepExecutionContext
                    reportPage = 1
```

The job context is suitable for values shared across steps, such as `generatedFile` or `importedCount`. The step context is for checkpoints and state specific to a single step, such as a reader position or writer state.

| Expression Source | Scope | Example |
| --- | --- | --- |
| `jobExecutionContext` | Entire current `JobExecution` | `#{jobExecutionContext['generatedFile']}` |
| `stepExecutionContext` | Current `StepExecution` | `#{stepExecutionContext['lastReadLine']}` |
| `jobParameters` | Parameters used to identify/configure the job execution | `#{jobParameters['businessDate']}` |

These three sources serve different purposes. If a value is only used to configure the run and is available at launch time, it should normally be passed via `JobParameters`. If one step produces a value for a later step to use, the job context is the appropriate place. If a value is only an internal checkpoint of a single step, keep it in the step context.

## `@Value` and SpEL Late Binding

`@Value` is a Spring annotation for injecting values. When used with a Spring Batch scope, SpEL expressions can read context variables provided by the framework.

```java
@Bean
@StepScope
ItemReader<OrderInput> orderReader(
        @Value("#{jobExecutionContext['generatedFile']}") String inputFile) {

    return buildOrderReader(inputFile);
}
```

Key parts:

- `@Bean` registers the reader in the Spring application context.
- `@StepScope` creates a target bean per `StepExecution`.
- `@Value(...)` instructs Spring to resolve the SpEL expression.
- `jobExecutionContext` is the context of the `JobExecution` containing the current step.
- `['generatedFile']` accesses the key in the context map.

Bracket notation should be used to access keys, especially when key names contain dots, hyphens, or characters unsuitable for property navigation. For example, `#{jobExecutionContext['input.file.name']}`.

### Difference Between `#{...}` and `${...}`

In `@Value`, the two common syntaxes have different meanings:

| Syntax | Value Source | Example |
| --- | --- | --- |
| `#{...}` | SpEL expression, can access Spring Batch context | `#{jobExecutionContext['generatedFile']}` |
| `${...}` | Property placeholder from Spring configuration | `${batch.input.directory}` |

For example, `${batch.input.directory}` typically retrieves a value from `application.yml`, the environment, or a property source. `#{jobExecutionContext['generatedFile']}` retrieves a value stored in the context of a specific job execution.

Do not write `@Value("${jobExecutionContext['generatedFile']}")` to access the batch context; that is a property placeholder and does not provide the intended late binding.

## Why is `@StepScope` Needed?

Spring creates regular singleton beans when the application context is initialized. At that point, there is no specific `JobExecution` or `StepExecution`, so variables like `jobExecutionContext` do not yet have data for a run.

`@StepScope` defers creating the target bean until the step actually runs. When the target is created, Spring Batch has bound the current `StepExecution` to the scope and can resolve expressions such as `jobExecutionContext`.

```java
@Bean
@StepScope
Tasklet publishTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String fileKey) {

    return (contribution, chunkContext) -> {
        publishFile(fileKey);
        return RepeatStatus.FINISHED;
    };
}
```

If `@StepScope` is omitted, Spring may attempt to resolve the expression during singleton initialization before the job runs. At that time, there is no appropriate execution context to inject. This is one of the most common errors when using `@Value` with job/step context.

`@StepScope` creates a scoped proxy so other beans can inject the reader/tasklet from the application context. The real target is created when the step scope is active. Therefore, the `@Bean` method can be wired during step configuration while the context value is resolved later when the step runs.

## Example: First Step Creates File, Next Step Reads from jobExecutionContext

Suppose a job has two steps:

1. `prepareFileStep` creates a staging file and saves the file key into the step context.
2. `importFileStep` reads that key from the job execution context to configure the reader.

The value is written into the first step's step context, then `ExecutionContextPromotionListener` promotes the key to the job context when the step completes.

### First Step Writes Value to StepExecutionContext

```java
public class PrepareFileTasklet implements Tasklet {

    private final StagingService stagingService;

    public PrepareFileTasklet(StagingService stagingService) {
        this.stagingService = stagingService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StagingResult result = stagingService.prepareOrdersFile();

        ExecutionContext stepContext =
                contribution.getStepExecution().getExecutionContext();
        stepContext.putString("generatedFile", result.objectKey());
        stepContext.putLong("importedCount", result.recordCount());

        return RepeatStatus.FINISHED;
    }
}
```

`StagingResult` is an application-defined data type. The actual file is stored in staging storage; the context only holds the key and small record count.

### Promoting Keys to Job Context

```java
@Bean
ExecutionContextPromotionListener prepareFilePromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {
            "generatedFile",
            "importedCount"
    });
    listener.setStrict(true);
    return listener;
}
```

The listener is attached to the step that produces the data. With the common default status configuration, the listener promotes when the step finishes with exit status `COMPLETED`. `strict=true` turns a missing required key into an explicit error instead of silently ignoring it.

```java
@Bean
Step prepareFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PrepareFileTasklet tasklet,
        ExecutionContextPromotionListener prepareFilePromotionListener) {

    return new StepBuilder("prepareFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(prepareFilePromotionListener)
            .build();
}
```

After the step finishes, `generatedFile` and `importedCount` are in the `JobExecution` context. The next step can inject these keys using `@Value`.

### Next Step Injects from jobExecutionContext

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> stagingOrderReader(
        @Value("#{jobExecutionContext['generatedFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("stagingOrderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

The target reader is created when `importFileStep` begins. At that time, `prepareFileStep` has completed and the promotion listener has moved the key to the job context. The reader receives the exact resource for the current run.

### Injecting Multiple Values at Once

Multiple keys can be injected via separate `@Value` parameters:

```java
@Bean
@StepScope
Tasklet importSummaryTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String fileKey,
        @Value("#{jobExecutionContext['importedCount']}") Long importedCount) {

    return (contribution, chunkContext) -> {
        importSummaryService.record(fileKey, importedCount);
        return RepeatStatus.FINISHED;
    };
}
```

Use wrapper types such as `Long` if a value can be missing or has a default. If a primitive `long` is used, null cannot be represented and injection may fail when the key does not exist yet.

## Writing Directly to JobExecutionContext

Besides a promotion listener, code inside a step can access `JobExecution` and place values directly into the job context:

```java
JobExecution jobExecution =
        contribution.getStepExecution().getJobExecution();

jobExecution.getExecutionContext()
        .putString("generatedFile", result.objectKey());
```

Then the next step can use:

```java
@Value("#{jobExecutionContext['generatedFile']}") String inputFile
```

However, it is important to understand `JobRepository`'s job context persistence lifecycle and transaction boundaries. When data is produced in one step and needs to be published after the step succeeds, `ExecutionContextPromotionListener` usually expresses intent more clearly: the step writes state to its own context, and the listener promotes an allowlist of keys when the step reaches the desired exit status.

Do not both write directly to the job context and promote the same key without a clear write rule; two sources can overwrite each other or make the result depend on execution order.

## Reading stepExecutionContext or jobExecutionContext?

Choose the right context based on where the value is stored:

```java
@Bean
@StepScope
Tasklet tasklet(
        @Value("#{stepExecutionContext['currentPage']}") Integer currentPage,
        @Value("#{jobExecutionContext['generatedFile']}") String generatedFile) {

    return (contribution, chunkContext) -> {
        // currentPage is state of the current step.
        // generatedFile is a value shared at the job level.
        return RepeatStatus.FINISHED;
    };
}
```

If `generatedFile` was only saved in the previous step's step context without promotion, the expression `jobExecutionContext['generatedFile']` will not find that key. You must either promote the key or save it directly to the job context through a controlled mechanism.

Do not attempt to read another step's step context via `stepExecutionContext`; that variable always represents the current step. To share across steps, use the job context or a business store.

## JobScope and StepScope

Spring Batch provides both `@StepScope` and `@JobScope` to create beans per execution context.

| Scope | Target Bean Lifecycle | Typical Use |
| --- | --- | --- |
| `@StepScope` | One target per `StepExecution` | Reader, processor, writer, or tasklet depending on the running step's context |
| `@JobScope` | One target per `JobExecution` | Component needing to hold shared state/configuration at the job level |

Example of a job-scoped bean reading a value already present in the job context:

```java
@Bean
@JobScope
JobRunDescriptor jobRunDescriptor(
        @Value("#{jobExecutionContext['businessDate']}") String businessDate) {

    return new JobRunDescriptor(businessDate);
}
```

`JobRunDescriptor` is an application-defined type. `@JobScope` is appropriate when the bean is created at a time when the key is already available and needs to be shared across the job execution.

If the value is only produced in a step that runs after the job starts, consider when the job-scoped bean is first accessed. A job-scoped target is created only once per execution; if it is initialized before the key is written to the job context, the injected value may not reflect the new data. For readers/tasklets of a consuming step, `@StepScope` is usually safer and more predictable because the target is created when that step starts, after the producing step.

Do not use a regular singleton bean to directly inject a value depending on a specific `JobExecution`. Singletons persist across multiple executions and do not have a single job context to bind to.

## Default Values When a Key Does Not Exist

SpEL supports the Elvis operator `?:` to provide a default value when the left-hand expression is null.

```java
@Bean
@StepScope
Tasklet publishTasklet(
        @Value("#{jobExecutionContext['format'] ?: 'CSV'}") String format) {

    return (contribution, chunkContext) -> {
        publishUsingFormat(format);
        return RepeatStatus.FINISHED;
    };
}
```

If the `format` key does not exist or has a null value, the bean receives `CSV`. This approach fits optional values that have a valid default.

Do not use a default to mask a missing required key. For example, if a later step must read the exact file generated by a previous step, defaulting to another path could cause the job to process the wrong data. For required keys, use strict promotion mode and validate the key before the consuming step runs.

### Checking Required Keys

If you want an error with a clear message when a key does not exist, you can check inside the tasklet/service using the context API:

```java
ExecutionContext context =
        contribution.getStepExecution().getJobExecution().getExecutionContext();

if (!context.containsKey("generatedFile")) {
    throw new IllegalStateException(
            "Required job context key 'generatedFile' is missing");
}

String generatedFile = context.getString("generatedFile");
```

This is an option when you want runtime error control. With constructor injection via `@Value`, you can use strict promotion in the preceding step to catch missing keys earlier.

## Type Conversion and Data Types

`ExecutionContext` stores values by key. When injecting with `@Value`, Spring performs type conversion if a matching converter exists. Even so, it is best to store the right type from the start and use the corresponding target type.

```java
// Previous step
stepContext.putLong("importedCount", 12500L);
stepContext.putInt("retryWindow", 3);
stepContext.putString("businessDate", "2026-11-15");

// Next step
@Value("#{jobExecutionContext['importedCount']}") Long importedCount
@Value("#{jobExecutionContext['retryWindow']}") Integer retryWindow
@Value("#{jobExecutionContext['businessDate']}") String businessDate
```

Guidelines:

- Use `putString`, `putLong`, `putInt`, `putBoolean` matching the data type.
- Use wrapper types (`Long`, `Integer`, `Boolean`) if the key might be missing.
- Use a stable format for dates/times if cross-version compatibility is needed.
- Avoid storing JPA entities, proxies, streams, or large object graphs.
- Ensure the `JobRepository` serializer can persist and restore the chosen data types.
- Keep key types and semantics compatible while old executions may still need to be restarted.

Do not rely on implicit conversion for complex data. If you need to pass a custom object, consider storing an ID/URI and re-querying it from the business data store.

## Key Names and SpEL Syntax

Keys are strings in `ExecutionContext`. Choose clear, stable names and avoid collisions between components.

Example:

```java
context.putString("report.objectKey", objectKey);
context.putLong("report.recordCount", recordCount);
context.putString("validation.resultCode", resultCode);
```

Access using bracket notation:

```java
@Value("#{jobExecutionContext['report.objectKey']}") String objectKey
@Value("#{jobExecutionContext['report.recordCount']}") Long recordCount
@Value("#{jobExecutionContext['validation.resultCode']}") String resultCode
```

Dots in a key are part of the key name; they do not automatically create nested maps. Therefore, the syntax `['report.objectKey']` accurately accesses the string key.

Do not use overly generic names like `data`, `result`, or `value` in a job context with multiple steps. Namespacing by business domain or producing step reduces conflicts and aids traceability.

## `@Value` from jobExecutionContext in a Reader

Readers are often the clearest use case for late binding. A previous step determines the file or resource; the subsequent step's reader is configured with that value.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

The target reader is created in step scope, so `inputFile` is resolved for the current `JobExecution`. `saveState(true)` saves the reader checkpoint to support restart; it does not replace ensuring that `inputFile` points to the same data source upon restart.

If `inputFile` is produced in a previous step, promote the key to the job context after that step completes. If the file is passed at launch time, using `jobParameters` may be more appropriate:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
```

## `@Value` from jobExecutionContext in a Processor or Writer

Processors and writers can also be step-scoped beans if they need values produced by a previous step.

```java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobExecutionContext['businessDate']}") String businessDate,
        OrderMapper mapper) {

    return input -> mapper.toOrder(input, businessDate);
}
```

```java
@Bean
@StepScope
ItemWriter<Order> orderWriter(
        @Value("#{jobExecutionContext['targetTable']}") String targetTable,
        OrderWriteService writeService) {

    return chunk -> writeService.write(targetTable, chunk.getItems());
}
```

These examples illustrate scoped injection. If `targetTable` is used to build dynamic SQL, do not concatenate strings directly from untrusted data; table names must be controlled via an allowlist or fixed mapping. A context value does not automatically become trusted data just because it is stored in the repository.

## Using `@Value` in a Tasklet

A Tasklet can receive job context values directly via a bean method constructor/parameters:

```java
@Bean
@StepScope
Tasklet sendReportTasklet(
        @Value("#{jobExecutionContext['reportObjectKey']}") String reportObjectKey,
        ReportPublisher publisher) {

    return (contribution, chunkContext) -> {
        publisher.publish(reportObjectKey);
        return RepeatStatus.FINISHED;
    };
}
```

If the tasklet is a class instantiated with `new` inside a singleton bean, `@Value` on its constructor or fields will not be processed automatically by Spring. Let Spring create the tasklet bean with the appropriate scope, or use the `StepExecution`/`JobExecution` API inside `execute`.

Example of accessing the context directly in a tasklet:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext jobContext =
            contribution.getStepExecution()
                    .getJobExecution()
                    .getExecutionContext();

    String reportObjectKey = jobContext.getString("reportObjectKey");
    publish(reportObjectKey);

    return RepeatStatus.FINISHED;
}
```

Choose constructor injection when you want dependencies to be explicitly visible in bean configuration. Accessing via `StepExecution` is useful when keys are optional or multiple values need to be checked/read dynamically.

## Context Values Produced in a Previous Step

To ensure a later step injects the right value, maintain the lifecycle order:

1. The producing step writes the key to the step context or job context.
2. If the key is in the step context, the promotion listener promotes the key after the step completes with an allowed status.
3. `JobRepository` persists the job context according to the step/job lifecycle.
4. The next step starts.
5. The `@StepScope` target bean is created and SpEL reads the job context.

If the later step's bean is initialized too early in an inappropriate scope, or the key has not been promoted yet, the expression may return null or fail to find the value.

### Promotion Listener and Statuses

`ExecutionContextPromotionListener` allows declaring the list of keys and exit statuses that permit promotion:

```java
listener.setKeys(new String[] { "inputFile", "businessDate" });
listener.setStatuses(new String[] { "COMPLETED" });
listener.setStrict(true);
```

`statuses` evaluates the step's `ExitStatus`. If the application uses custom exit codes, declare the exact codes that should permit promotion. Do not promote incomplete results just so the next step has data; clearly define which statuses guarantee the key is valid.

## JobParameters, jobExecutionContext, and stepExecutionContext

Do not use the job context for every type of parameter. Choose the source based on data lifecycle:

| Need | Recommended Source | Expression |
| --- | --- | --- |
| Business date passed by caller at launch | Job parameters | `#{jobParameters['businessDate']}` |
| File generated by a preparation step | Job execution context after promotion | `#{jobExecutionContext['generatedFile']}` |
| Reader page/offset of current step | Step execution context | `#{stepExecutionContext['nextPage']}` |
| Static configuration from application.yml | Property placeholder | `${batch.reader.page-size}` |
| Large business data | Database/staging/object storage | Context only stores ID/URI |

Job parameters determine `JobInstance` identity based on identifying flags. The job context is the state of a `JobExecution`; it does not replace identifying parameters. If you need to restart the same instance, keep identifying parameters unchanged and ensure persisted context values remain compatible.

## Restart and Injected Values

When a job restarts, Spring Batch creates a new `JobExecution` for the same `JobInstance` if the status permits. The job context is restored from metadata according to restart semantics. `@StepScope` beans of the restarted step are created for the new `StepExecution` and can read the persisted job context values.

For example, `prepareFileStep` completed and promoted `generatedFile`, but `importFileStep` failed. On restart:

- The completed prepare step may be skipped per restart semantics.
- The job context from the previous execution is restored by the repository mechanism.
- The import step restarts and a new target reader is created.
- `@Value("#{jobExecutionContext['generatedFile']}")` receives the saved key again.
- The reader must use the exact file/version created by the previous run.

The referenced resource must still exist as long as the job can be restarted. If the file is deleted or overwritten, the expression can still resolve the path, but the reader cannot read the original data.

Do not create new identifying parameters on restart just to refresh a file path. If you need to execute a new business run, intentionally create a new logical instance and clearly define a new output resource.

## Threading and Context Scope

`jobExecutionContext` belongs to a `JobExecution`; `stepExecutionContext` belongs to a `StepExecution`. Scoped beans use proxies to access the context attached to the current execution.

In multi-threaded or partitioned steps, be cautious with bean scope and mutable data. A shared job context value should not be written concurrently by multiple workers without synchronization rules. If each partition has its own state, store that state in the corresponding step/partition execution context.

`@Value` injects a value when the target bean is created; it is not a subscription that automatically updates the field whenever the context changes. If a key is modified after the target bean has been created, the injected field may still hold the old value. Therefore, only inject values that are ready before the step-scoped bean is created. For data that must be read dynamically later, access the context via the execution API at the time of use or design a controlled state-reading service.

## Security and Data Size

The job execution context is persisted in the batch metadata database and may appear in backups or operational tools. Do not store passwords, access tokens, private keys, or unnecessary personal/sensitive payloads.

If a later step needs credentials to access a resource, store a secret reference and fetch the secret from a secret manager at runtime. If you need to pass a large file, store the file in object storage and inject the object key/version instead of a byte array.

The context should stay small and have stable types. Keys may persist across multiple deployments if a job has not completed; changing data types or key names can make old restarts incompatible.

## Common Errors When Using `@Value` from jobExecutionContext

### Forgetting `@StepScope`

Singleton beans are created before a specific job execution exists. SpEL has no proper context to resolve. Use `@StepScope` for readers/processors/writers/tasklets that depend on execution context.

### Reading the Wrong Step Context

`stepExecutionContext` is the context of the current step, not the previous step. If a later step needs a key from a prior step, promote the key to the job context or save it directly into the job context with a clear lifecycle.

### Forgetting Promotion

The preceding step writes a key to the step context, but the next step reads `jobExecutionContext`. Keys do not automatically appear in the job context. Register `ExecutionContextPromotionListener` with the right keys and statuses.

### Using JobScope for a Value Produced After a Step

A job-scoped bean is created only once per job execution. If the target is initialized before the key is created, the injected field may not hold the expected value. For beans consumed in a later step, use StepScope to late-bind when that step starts.

### Using `${...}` Instead of `#{...}`

`${...}` is a property placeholder; `#{...}` is a SpEL expression used to access the batch context.

### Missing Key or Typo

Map lookups can return null. Use strict promotion for required keys, validate keys, and choose wrapper types if null is possible.

### Using Primitives for Optional Values

Primitives such as `long` cannot represent null. Use `Long` or provide a meaningful SpEL default.

### Injecting Large Objects into Beans

The context is not a data store. Store IDs/URIs/versions and read data from staging/database/object storage.

### Changing Keys or Data Types While Old Jobs Can Still Restart

Persisted execution contexts may become incompatible. Keep the key/type contract stable or have a migration plan.

### Expecting `@Value` Fields to Auto-Update When Context Changes

Values are resolved when the scoped target bean is created. If dynamic data is needed, access the execution context at the time of use.

## Testing `@Value` from jobExecutionContext

Unit testing a SpEL expression in isolation is not enough to prove late binding works in the job lifecycle. There should be an integration test running at least two steps with `JobRepository` and real scopes.

### End-to-End Promotion and Injection Test

A test can:

1. Run `prepareFileStep`, writing `generatedFile` into the step context.
2. Let the promotion listener promote the key after the step completes.
3. Run `importFileStep` with a `@StepScope` reader/tasklet injecting the key from the job context.
4. Use a test double service or writer to record the received value.
5. Verify that the next step receives the right value and processes the right resource.

Example consuming tasklet:

```java
@Bean
@StepScope
Tasklet consumeGeneratedFileTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String generatedFile,
        FileImportService importService) {

    return (contribution, chunkContext) -> {
        importService.importFile(generatedFile);
        return RepeatStatus.FINISHED;
    };
}
```

In the test, mock or fake `FileImportService` and verify that `importFile` receives the exact key produced by the prior step. Do not hard-code a value different from the promoted data.

### Testing Missing Keys

Create a fixture that does not write the key or configure a strict listener. Verify that the producing step fails or the consuming step stops with a clear error per contract. Do not let the job silently use an unrelated default file.

### Testing Default Values

For optional keys, verify that the Elvis expression provides the default when the key is absent and uses the context value when the key is present.

### Testing Type Conversion

Write `Long`, `Integer`, or `String` into the context and verify the bean receives the expected type/value. For custom types, test the serializer and metadata deserialization.

### Testing Restart

Let the producing step finish and the consuming step fail. Restart with the same identifying parameters; verify that the `@StepScope` bean is recreated and injects the value saved in the job context. Verify that the referenced resource still exists and has the right version.

### Testing Scope Timing

Ensure the bean is not initialized before the key is produced. You can record the value received in a fake service in the consuming step. If switching a bean from `@StepScope` to `@JobScope`, test when the target is created and avoid initializing it before data is ready.

## Design Principles

When using `@Value` from the job execution context, determine:

1. In which step and in which context is the key created?
2. If the key is in the step context, has a promotion listener promoted it?
3. Which step consumes the value, and does the bean have the appropriate `@StepScope`?
4. Is the target bean created after the key is ready?
5. Is the key required or optional; is strict promotion or a default needed?
6. Are the written and injected data types compatible?
7. Is the value small, stable, and serializer-compatible?
8. Does the referenced resource remain available on restart?
9. Are identifying parameters stable across restarts?
10. Have integration tests verified promotion, injection, missing keys, and restart?

For most cases, the clearest pattern is for the producing step to write keys into the step context, `ExecutionContextPromotionListener` to promote keys after the step succeeds, and the consuming step's bean to use `@StepScope` with `@Value("#{jobExecutionContext['key']}")`. This clarifies the data source, injection timing, and sharing scope.

## Takeaways

`@Value("#{jobExecutionContext['key']}")` uses SpEL to inject a value from the `JobExecution` context. Execution-dependent beans must use an appropriate scope, typically `@StepScope`, so the target is created when the step runs rather than at application startup. If a previous step writes a key into the step context, promote it to the job context via `ExecutionContextPromotionListener` before the next step starts. Use `stepExecutionContext` for the current step's state, `jobParameters` for launch-time input data, and `${...}` for configuration properties. Choose wrapper types/defaults for optional keys, strict promotion for required keys, store small and stable values, and maintain suitable resources/identifying parameters for restarts. Test end-to-end to confirm the target bean receives the right value after promotion and can recover on restart.
