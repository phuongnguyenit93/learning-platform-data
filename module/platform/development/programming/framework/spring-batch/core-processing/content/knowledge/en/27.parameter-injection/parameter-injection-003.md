# `@Value` from `stepExecutionContext`

In Spring Batch, `StepExecutionContext` is a key-value area bound to a single Step execution. It typically stores data specific to that Step, such as partition ranges, the last read key, file position, or checkpoints needed to recover upon restart. A bean that needs these values can receive them using Spring Expression Language (SpEL) via `@Value`.

The typical expression is `@Value("#{stepExecutionContext['key']}")`. The bean must be declared with `@StepScope` so Spring defers target creation until the current StepExecution becomes active. At that point, Spring Batch can resolve `stepExecutionContext` and inject the value belonging to the exact StepExecution.

## 1. What is StepExecutionContext?

Each `StepExecution` has its own `ExecutionContext`. This context stores values that need to persist within the scope of the Step, including reader state, data supplied by a partitioner, or intermediate information the Step needs to use.

For example, a Step might store:

- `minId`, `maxId`: the ID range assigned to the current partition.
- `inputFile`: the file the Step is processing.
- `lastProcessedId`: the last processed key.
- `sourceVersion`: the version of the input snapshot.
- `validatedRecordCount`: the number of validated records.

You can access the context via `StepExecution`:

```java
StepExecution stepExecution = contribution.getStepExecution();
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("minId", 1L);
context.putLong("maxId", 100_000L);
```

Keys and values are stored per StepExecution. Two different StepExecutions can use the same key name while holding different values. Therefore, `stepExecutionContext` is appropriate for data specific to the current Step, not as a shared area across all Steps in a Job.

## 2. Reading Context with `@Value`

Spring Batch exposes execution context maps to SpEL when the appropriate scope is active. To retrieve a key from StepExecutionContext, use the `stepExecutionContext` variable name and map access syntax:

```java
@Value("#{stepExecutionContext['minId']}") Long minId
```

Full example with a reader bean:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createCustomerReader(dataSource, minId, maxId);
}
```

`minId` and `maxId` are retrieved from the running StepExecution's context. If the same worker Step is used for multiple partitions, each worker StepExecution has its own context, so each reader instance receives its assigned range.

For keys containing dots, hyphens, or characters unsuitable for property syntax, use bracket notation:

```java
@Value("#{stepExecutionContext['input.file']}") String inputFile
@Value("#{stepExecutionContext['source-version']}") String sourceVersion
```

The key name in SpEL must match the exact key written into `ExecutionContext`.

## 3. Why is `@StepScope` Needed?

Regular singleton beans are typically created when Spring starts the application context. However, `StepExecutionContext` only makes sense once a specific StepExecution begins. If a singleton attempts to read `stepExecutionContext` at startup, there is no current StepExecution to resolve the value.

`@StepScope` lets Spring create a scoped proxy first, then create the target bean when StepScope is activated for the current StepExecution. Only when the target is created is the SpEL expression evaluated against the corresponding context.

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> inputReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("inputReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
```

The Step bean can accept the reader as a regular dependency:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> inputReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(inputReader)
            .writer(customerWriter)
            .build();
}
```

`inputReader` injected here is a scoped proxy. Declaring the Step does not force the target reader to be instantiated at application context startup. When the Step runs, the proxy retrieves the target belonging to the current StepExecution.

## 4. Distinguishing `stepExecutionContext` from `jobExecutionContext`

Spring Batch provides several similarly named SpEL variables. Choose the right context based on where the data is stored:

| SpEL variable | Data Source | Scope |
|---|---|---|
| `stepExecutionContext` | `StepExecution.getExecutionContext()` | One StepExecution |
| `jobExecutionContext` | `JobExecution.getExecutionContext()` | One JobExecution, shareable across Steps |
| `jobParameters` | Parameters when launching the Job | Inputs to the JobExecution |

Example of a bean receiving all three types:

```java
@Bean
@StepScope
Tasklet exportTasklet(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        ExportService exportService) {

    return (contribution, chunkContext) -> {
        exportService.export(batchId, sourceVersion, minId, maxId);
        return RepeatStatus.FINISHED;
    };
}
```

In the example:

- `batchId` is the input provided by the caller when launching the Job.
- `sourceVersion` is metadata stored in JobExecutionContext.
- `minId` and `maxId` are the range specific to the current StepExecution.

If data is created in an earlier Step and needed in a later Step, you should normally promote the key from StepExecutionContext to JobExecutionContext or write it to a business data store. A later Step cannot directly read an earlier Step's StepExecutionContext via `stepExecutionContext`.

## 5. Populating the Context with a Partitioner

A classic use case for `@Value` from `stepExecutionContext` is partitioning. A `Partitioner` returns a map of partition names and `ExecutionContext` instances for each partition. Spring Batch uses those contexts to initialize worker StepExecutions.

Example of splitting a customer table into ID ranges:

```java
@Component
public class CustomerPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        ExecutionContext first = new ExecutionContext();
        first.putLong("minId", 1L);
        first.putLong("maxId", 50_000L);
        partitions.put("partition0", first);

        ExecutionContext second = new ExecutionContext();
        second.putLong("minId", 50_001L);
        second.putLong("maxId", 100_000L);
        partitions.put("partition1", second);

        return partitions;
    }
}
```

The worker reader obtains the range from StepExecutionContext:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("partitionReader")
            .dataSource(dataSource)
            .queryProvider(customerQueryProvider(dataSource))
            .parameterValues(Map.of(
                    "minId", minId,
                    "maxId", maxId))
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
```

The query provider needs to use the two parameters to filter the range, for example:

```sql
SELECT id, full_name, email
FROM customer
WHERE id BETWEEN :minId AND :maxId
ORDER BY id ASC
```

Each worker has its own StepExecutionContext. `partition0` receives `minId=1`, `maxId=50000`; `partition1` receives `minId=50001`, `maxId=100000`. The same worker Step definition can be used for all partitions without creating a singleton reader with a fixed range.

In practice, ensure data ranges do not overlap and cover the exact record set. The paging reader's sort key must be stable, ideally containing a unique key, to avoid skipping or duplicating rows across pages.

## 6. Populating Context Before the StepScope Bean Is Created

Values injected via `@Value` are resolved when the scoped target bean is created. Therefore, keys must already be present in StepExecutionContext at the moment the bean is initialized.

This is why a partitioner fits well: it creates the context for each partition before the worker Step starts. When the worker creates the reader, `minId` and `maxId` already exist.

Conversely, if a `beforeStep()` listener writes a key into StepExecutionContext after a StepScope bean has already been initialized, the `@Value` field in that bean will not automatically update. `@Value` is bound when the target bean is created, not a dynamic binding re-evaluated on every field read.

If you need values produced after the Step has started:

- Use `StepExecution` or `ExecutionContext` directly at the time you need to read them.
- Put the data into JobExecutionContext in an earlier Step and use `jobExecutionContext` in the next Step.
- Use `ExecutionContextPromotionListener` if keys need to be promoted when the previous Step finishes.
- Design a scoped bean that is only created after the keys are ready.

Do not rely on incidental initialization order between listeners and scoped beans to pass data.

## 7. Late Binding for ItemReader

Readers are usually the component that most needs StepExecutionContext data, since each Step or partition may read a different file, tenant, or data range.

Example of a reader obtaining the file name and starting line number from context:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile,
        @Value("#{stepExecutionContext['startLine']}") Integer startLine) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("stepExecutionContext.inputFile is required");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(Math.max(0, startLine - 1))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
```

This example assumes `startLine` is a 1-based starting line number and headers are accounted for in the reader's line-skipping rules. In real applications, clearly define headers, checkpoints, and offset semantics so lines are neither skipped nor read twice.

## 8. Late Binding for ItemProcessor and ItemWriter

Processors or writers can also receive parameters specific to a StepExecution. For example, a processor receives a region code assigned by a partitioner:

```java
@Bean
@StepScope
ItemProcessor<CustomerInput, Customer> customerProcessor(
        @Value("#{stepExecutionContext['regionCode']}") String regionCode,
        CustomerMappingService mappingService) {

    return input -> mappingService.mapForRegion(input, regionCode);
}
```

A writer can attach a batch ID or partition name to output data:

```java
@Bean
@StepScope
JdbcBatchItemWriter<Customer> customerWriter(
        DataSource dataSource,
        @Value("#{stepExecutionContext['partitionName']}") String partitionName) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer_result
                        (partition_name, customer_id, full_name)
                    VALUES
                        (:partitionName, :customerId, :fullName)
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new BeanPropertyItemSqlParameterSourceProvider<Customer>()
                            .createSqlParameterSource(item))
            .build();
}
```

The writer snippet above only illustrates the idea of retrieving the partition name; to additionally bind `partitionName` into each parameter source, the application must use a custom `ItemSqlParameterSourceProvider` or an output DTO that already includes that field. Do not copy this mapping verbatim if the current provider does not supply the corresponding SQL key.

Another option is to inject `partitionName` into a custom writer and create a parameter source containing both the item fields and the partition name. Whichever approach is chosen, the bean needs `@StepScope` to receive each worker's own context.

## 9. Late Binding for Tasklet

A Tasklet can also read values from StepExecutionContext. For example, a worker Tasklet processing an assigned file:

```java
@Bean
@StepScope
Tasklet processFileTasklet(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile,
        @Value("#{stepExecutionContext['fileType']}") String fileType,
        FileProcessingService fileProcessingService) {

    return (contribution, chunkContext) -> {
        fileProcessingService.process(inputFile, fileType);
        return RepeatStatus.FINISHED;
    };
}
```

Tasklets can be used in a partitioning worker Step or in a Step where input data is set before the Step starts. If the Tasklet needs to read keys written during the current `execute()` call itself, access `StepExecution` via `StepContribution` or `ChunkContext` instead of expecting `@Value` to auto-update.

## 10. Data Types and Value Conversion

`ExecutionContext` stores objects by key. When using `@Value`, Spring resolves the value and converts it to the bean parameter type according to the available conversion service.

Example of context storing numeric types:

```java
context.putLong("minId", 100L);
context.putInt("pageSize", 500);
context.putString("regionCode", "NORTH");
```

Bean receiving corresponding values:

```java
@Bean
@StepScope
Tasklet regionTasklet(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['pageSize']}") Integer pageSize,
        @Value("#{stepExecutionContext['regionCode']}") String regionCode) {

    return (contribution, chunkContext) -> {
        processRegion(minId, pageSize, regionCode);
        return RepeatStatus.FINISHED;
    };
}
```

Store values using the exact type needed, such as `putLong()` for ID keys and `putInt()` for page size. This reduces conversion errors and clarifies the context schema.

For dates and times, store a stable representation such as ISO-8601 and parse explicitly, or use a type supported by the JobRepository serializer. Do not assume every custom object can be serialized safely.

## 11. Missing Keys and Default Values

If a key does not exist in StepExecutionContext, the expression may return `null`. If a bean parameter takes a primitive type such as `long` or `int`, converting null can fail. For keys that may be absent, use wrapper types like `Long` or `Integer`, then validate explicitly.

Example:

```java
@Bean
@StepScope
Tasklet optionalRangeTasklet(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    if (minId == null || maxId == null) {
        throw new IllegalStateException(
                "minId and maxId must be provided in StepExecutionContext");
    }

    if (minId > maxId) {
        throw new IllegalArgumentException("Invalid ID range");
    }

    return (contribution, chunkContext) -> {
        processRange(minId, maxId);
        return RepeatStatus.FINISHED;
    };
}
```

If a key is truly optional, you can use the Elvis operator in SpEL:

```java
@Value("#{stepExecutionContext['pageSize'] ?: 500}") Integer pageSize
```

Default values should only be used when there is a clear business meaning. For `minId`, `maxId`, or a required file, silently substituting a default could make the Step process the wrong data range. Fail fast with a message stating the missing key.

## 12. Saving Data into StepExecutionContext

Data can be written to the context from a Tasklet through StepExecution:

```java
@Component
public class PrepareRangeTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context = contribution
                .getStepExecution()
                .getExecutionContext();

        context.putLong("minId", 1L);
        context.putLong("maxId", 100_000L);

        return RepeatStatus.FINISHED;
    }
}
```

Values are stored in the current StepExecution's context. A `@StepScope` bean can read the key if the target bean is created after the key has been written. However, if a reader or processor was already created before the Tasklet wrote the key, the injected `@Value` will not change automatically.

If a Step needs to produce context for the next Step, it can write to JobExecutionContext or promote keys when the Step completes. Example using `ExecutionContextPromotionListener`:

```java
@Bean
ExecutionContextPromotionListener promoteRange() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"minId", "maxId"});
    return listener;
}
```

The next Step reads the promoted values via `#{jobExecutionContext['minId']}` and `#{jobExecutionContext['maxId']}`. It does not read the previous Step's context using `stepExecutionContext`.

## 13. Persistence Timing and Restart

StepExecutionContext is managed by `JobRepository`. For chunk-oriented Steps, reader/ItemStream state is typically updated at chunk commit boundaries. When a Step restarts, the framework can restore the latest saved checkpoint.

Late binding only helps a bean receive values from the context. It does not by itself guarantee that a key has been persisted or that the value remains valid upon restart. For reliable restarts:

- Use a reader/ItemStream that supports saving and restoring state if checkpointing is needed.
- Keep reader names stable because the name often participates in building internal context keys.
- Do not change partition ranges between restarts of the same JobInstance.
- Store values needed for recovery in the context or a durable data store before the appropriate commit point.
- Ensure data sources and input resources remain stable across restarts.

For example, `minId` and `maxId` generated by a partitioner must represent the same ranges when the same JobInstance restarts. If `partition0` was IDs 1–50,000 on the first run but uses IDs 1–60,000 on restart, the old checkpoint may no longer correspond to the new range.

## 14. Late Binding Is Not Dynamic Context Access

A common misconception is that `@Value("#{stepExecutionContext['key']}")` always reads the latest value every time the bean uses the field or method. In reality, SpEL is resolved when the scoped target bean is created and the value is injected at that point.

If the context changes after the target has been created, the injected field does not automatically update. Example:

```java
@Bean
@StepScope
SomeService someService(
        @Value("#{stepExecutionContext['status']}") String status) {
    // status is the value bound when the target bean is created.
    return new SomeService(status);
}
```

If a callback in the same Step modifies `status`, `SomeService` does not automatically receive the new value. When you need to read fresh state, access the context directly in the callback or pass the new value as a method argument.

This is also why required input keys should be created before the worker Step starts, rather than relying on a scoped bean updating itself when the context changes.

## 15. Scope and Parallel Execution

In partitioning, each worker has its own StepExecution and StepExecutionContext. `@StepScope` beans are resolved per worker execution, so each worker can receive a different `minId`, `maxId`, `regionCode`, or `inputFile`.

Do not store partition-specific data in mutable fields of a singleton bean. If a singleton service is used concurrently by multiple workers, it may receive calls with different parameters; the service must be thread-safe and not keep per-partition state in shared fields.

For manually spawned threads, the Step scope context may not propagate to new threads. Use the concurrency models supported by Spring Batch and avoid invoking a scoped proxy from a thread without a StepContext. If you must pass data to a separate async task, pass immutable values as method parameters or message payloads.

## 16. Security and Context Size

ExecutionContext is persisted in the metadata repository, so it should only hold small data serializable by the application's configured serializer.

Store:

- IDs, counts, ranges, versions, or reference codes.
- Controlled resource paths.
- Primitives, Strings, or small types with clear serialization.

Avoid storing:

- Passwords, access tokens, private keys, or secrets.
- JDBC Connections, file streams, HTTP clients, or Spring beans.
- Entire files or lists of millions of items.
- Large runtime objects or objects that do not serialize reliably.

If the context needs to reference sensitive data, store the ID of a protected record rather than its payload. For files, store the path and a checksum or version to verify the resource upon restart.

## 17. Testing `@Value` from StepExecutionContext

Tests should demonstrate that `@StepScope` beans receive the right values per StepExecution, especially when the same worker Step runs across multiple partitions.

Scenarios to test:

1. Context has valid keys: the bean receives the right values.
2. Key is missing: the Step fails fast with a clear message.
3. Value has wrong type: conversion or validation reports an appropriate error.
4. Two partitions have different ranges: each reader receives its exact `minId` and `maxId`.
5. Key written before target bean creation: the value is bound properly.
6. Key written after target bean creation: the injected value does not auto-update.
7. Restart: the partitioner recreates the same names and ranges; checkpoints are restored properly.

Example Step test with `JobLauncherTestUtils`:

```java
@SpringBatchTest
@SpringJUnitConfig(PartitionJobTestConfiguration.class)
class StepExecutionContextBindingTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void bindsPartitionRangeToReader() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "BATCH-TEST-01", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(expectedIds, outputRepository.findAllIds());
    }
}
```

The test needs to configure a partitioner with deterministic ranges and an appropriate output repository. You can verify the output data or use a probe service to prove each worker received the right range. Do not only assert that the Job `COMPLETED`, because a Job might still complete even if a reader received the wrong key or range.

## 18. Common Errors

**Forgetting `@StepScope`:** a singleton bean has no specific StepExecution at initialization. Use `@StepScope` on beans requiring per-Step late binding.

**Using the wrong SpEL variable name:** you must use `stepExecutionContext`, not `stepContext` or `stepExecution` when accessing the context map.

**Using the wrong key:** the key in `@Value` must match the exact key written into `ExecutionContext`.

**Confusing with JobExecutionContext:** data shared across Steps belongs in JobExecutionContext or a shared data store, not a prior Step's StepExecutionContext.

**Creating the key after the bean was initialized:** `@Value` does not auto-update. Populate the context before the target bean is created or read the context directly when needed.

**Using primitives for keys that may be missing:** null cannot safely convert to `long` or `int`. Use wrapper types and validate.

**Treating the context as an in-memory cache:** the context is managed and persisted according to the JobRepository lifecycle. Do not assume every `put()` is immediately flushed to the database.

**Storing large objects or secrets:** bloats metadata or exposes sensitive data. Store only small metadata and references.

**Using mutable singleton state for partitions:** multiple workers can overwrite each other's values. Use StepScope and local variables.

**Changing partition ranges on restart:** old checkpoints may no longer match new data. Keep partition names and ranges stable for the same JobInstance.

## Conclusion

`@Value("#{stepExecutionContext['key']}")` lets beans retrieve values from the current StepExecution's ExecutionContext. The bean requires `@StepScope` so the target is created once the StepExecution exists and the context can be resolved. This is particularly useful for readers, processors, writers, and Tasklets in partitioning, where each worker receives its own range or resource. Distinguish StepExecutionContext from JobExecutionContext and JobParameters, ensure keys exist before target bean creation, validate nulls/types, keep the context small and serializable, and maintain stable ranges across restarts.
