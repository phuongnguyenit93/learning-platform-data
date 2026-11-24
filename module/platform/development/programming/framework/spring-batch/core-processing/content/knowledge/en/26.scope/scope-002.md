# Late Binding from JobParameters

In Spring Batch, `JobParameters` are input values passed when launching a Job, such as a file path, business date, batch ID, or processing mode. Many batch beans need these values to know which source to read, what data range to filter, or where to write results.

The problem is that ordinary Spring beans are typically created when the application context starts up, whereas `JobParameters` are only available when a specific JobExecution and StepExecution begin. **Late binding** bridges this gap: Spring defers creating or resolving configuration values until the Job or Step scope is active, and then injects values from `JobParameters` using SpEL.

In Spring Batch, the most common pattern is declaring a bean with `@StepScope` and reading parameters via an expression such as `@Value("#{jobParameters['input.file']}")`. This is especially useful for `ItemReader`, `ItemWriter`, `Tasklet`, and dependencies whose configuration changes from run to run.

## 1. What Are JobParameters?

`JobParameters` are the set of parameters supplied when launching a Job. They describe the work to be performed, for example:

- `input.file`: path to the input file.
- `businessDate`: business date to process.
- `batchId`: data batch identifier.
- `sourceSystem`: source system.
- `output.directory`: directory for generated results.
- `mode`: run mode such as FULL or DELTA.

Example of creating JobParameters in Java:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/in/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("batchId", "BATCH-20261115-01", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Each parameter added to the builder has a name, a value, and an identifying flag. This flag determines whether the parameter participates in identifying the `JobInstance`. It does not determine whether the parameter can be injected into a bean: both identifying and non-identifying JobParameters can be read via late binding.

JobParameters are the input data of a JobExecution and are treated as immutable during execution. If you need to store progress or results generated while the Job runs, use `ExecutionContext` or an appropriate business data store instead of attempting to modify JobParameters.

## 2. What Problem Does Late Binding Solve?

Suppose an application has a Job that imports customers from a file. Each run may receive a different file:

```text
Run A: input.file = /data/customers-2026-11-14.csv
Run B: input.file = /data/customers-2026-11-15.csv
```

If the reader is created as a regular singleton and receives the file path as soon as the application context starts, the reader does not know the JobParameters of each individual run. The bean could hold a fixed path or lack the required value.

Late binding allows the reader to be configured when the Step starts. By then Spring Batch already has the `StepExecution`, `JobExecution`, and `JobParameters`, so SpEL expressions can retrieve the exact value for the current run.

```text
Application context starts
          |
          v
Register reader scoped proxy
          |
          v
Launch Job with JobParameters
          |
          v
Step starts, StepScope is activated
          |
          v
Create target reader for the current StepExecution
          |
          v
Inject input.file from JobParameters
          |
          v
Reader opens the exact file for the run
```

As a result, the same Job configuration can process different files or business dates without needing a separate reader bean for each value.

## 3. Why Is `@StepScope` Needed?

`@StepScope` marks a bean as scoped to a single `StepExecution`. Spring creates a scoped proxy when the application context starts; the actual target bean is created when the corresponding StepExecution becomes active. Only then can values such as `jobParameters`, `stepExecutionContext`, and `jobExecutionContext` be resolved.

Example:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

The key point is that `@StepScope` is placed on the `@Bean` method creating the reader. Spring registers a proxy for the bean; when the Step needs to use the reader, the proxy delegates calls to the target created within the scope of the current StepExecution.

If `@StepScope` is omitted, Spring may try to instantiate the reader while initializing the application context. At that time there are no JobParameters for a specific run to resolve the expression. An error can occur at startup or when the bean is initialized, depending on the configuration.

## 4. Reading JobParameters with SpEL

Spring Batch exposes context variables for SpEL. To read JobParameters, use `jobParameters` and access by key:

```java
@Value("#{jobParameters['input.file']}") String inputFile
```

For keys containing dots or special characters, bracket notation is clearer and safer than dot notation.

Some examples:

```java
@Value("#{jobParameters['businessDate']}") String businessDate
@Value("#{jobParameters['batchId']}") String batchId
@Value("#{jobParameters['sourceSystem']}") String sourceSystem
@Value("#{jobParameters['output.directory']}") String outputDirectory
```

The value is converted to the method parameter type according to Spring's conversion mechanism and the stored JobParameter type. When using date or numeric types, ensure the JobParameter type and the receiving type are compatible; when the input format is complex, you can accept a `String` and parse it explicitly for clear error messages.

Example of parsing a date:

```java
@Bean
@StepScope
Tasklet reconcileTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        ReconciliationService service) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        service.reconcile(date);
        return RepeatStatus.FINISHED;
    };
}
```

In this example, the date is parsed when the bean is created inside the Step scope. If the string is not in ISO `yyyy-MM-dd` format, `LocalDate.parse()` throws an exception and the Step cannot initialize the bean successfully. More explicit validation can be performed before calling the service.

## 5. Late Binding for ItemReader

An `ItemReader` often needs to know the resource, query, or data range before starting to read. This is one of the most common use cases for `@StepScope`.

Example of a reader reading a file passed from JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("Job parameter input.file is required");
    }

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

The Step uses the reader as a normal dependency:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

`customerReader` is injected as a scoped proxy. When the Step runs, the proxy resolves the target reader with the file path of the current JobExecution.

With a reader using `saveState(true)`, Spring Batch can save checkpoints in the StepExecutionContext to support restarts. Late binding determines the input resource; checkpointing tracks the saved read position. The two mechanisms are related but solve different problems.

## 6. Late Binding for Tasklet

A Tasklet can also receive JobParameters when the bean is created. For example, a Tasklet generating a report for a business date:

```java
@Bean
@StepScope
Tasklet generateDailyReportTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['output.directory']}") String outputDirectory,
        ReportService reportService) {

    LocalDate date = LocalDate.parse(businessDate);
    Path output = Path.of(outputDirectory);

    return (contribution, chunkContext) -> {
        reportService.generate(date, output);
        return RepeatStatus.FINISHED;
    };
}
```

Declaring the Step:

```java
@Bean
Step generateDailyReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet generateDailyReportTasklet) {

    return new StepBuilder("generateDailyReportStep", jobRepository)
            .tasklet(generateDailyReportTasklet, transactionManager)
            .build();
}
```

The Tasklet is created when StepScope is active, so it can use the exact date and directory of the current run. If a Tasklet is declared as a singleton, it should not read JobParameters directly in its constructor or field initializers because no execution context exists at that time.

## 7. Late Binding for ItemProcessor and ItemWriter

A processor may need a parameter to select transformation rules, while a writer may need a table name, directory, or write mode per run.

Example of a processor receiving the processing mode:

```java
@Bean
@StepScope
ItemProcessor<CustomerInput, Customer> customerProcessor(
        @Value("#{jobParameters['mode']}") String mode,
        CustomerMappingService mappingService) {

    return input -> mappingService.map(input, mode);
}
```

Example of a writer receiving a batch ID:

```java
@Bean
@StepScope
JdbcBatchItemWriter<Customer> customerWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO imported_customer
                        (batch_id, customer_id, full_name)
                    VALUES
                        (:batchId, :customerId, :fullName)
                    """)
            .itemSqlParameterSourceProvider(item -> {
                MapSqlParameterSource params =
                        new MapSqlParameterSource();
                params.addValue("batchId", batchId);
                params.addValue("customerId", item.customerId());
                params.addValue("fullName", item.fullName());
                return params;
            })
            .build();
}
```

The examples above illustrate the concept of late binding; the writer type and mapping should match the application's actual model. Do not use JobParameters to alter table names or dynamically concatenate SQL from untrusted input. If a parameter affects SQL structure, use an allowlist and parameter binding for data values.

## 8. Distinguishing `@StepScope` and `@JobScope`

Spring Batch has two scopes commonly used for late binding:

- `@StepScope`: the bean has a lifecycle tied to one StepExecution.
- `@JobScope`: the bean has a lifecycle tied to one JobExecution.

Both can read `jobParameters`, but the bean creation scope differs.

| Criterion | `@StepScope` | `@JobScope` |
|---|---|---|
| Scope | One StepExecution | One JobExecution |
| Commonly used for | Reader, processor, writer, Tasklet, and Step-specific dependencies | Dependencies that must exist across the Job and are used by multiple Steps |
| Can read JobParameters | Yes | Yes |
| Can read StepExecutionContext | Yes | Not the right scope to bind to a specific StepExecution |
| Can read JobExecutionContext | Yes | Yes |

Example of a JobScope bean:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new BatchRunDescriptor(batchId, businessDate);
}
```

A Step can receive `BatchRunDescriptor` as a dependency. The bean is created within the scope of the current JobExecution, so Steps in the same JobExecution can use the same scoped descriptor.

In most cases where a reader needs a Step-specific resource, use `@StepScope`. Use `@JobScope` when shared state or configuration at the JobExecution level is genuinely needed. Job scope has limitations in certain parallel/partitioning execution models because the JobExecution context may be accessed concurrently; check your version's support and design appropriate thread safety.

## 9. Reading JobParameters and ExecutionContext Together

Late binding does not apply only to JobParameters. A `@StepScope` bean can receive data from multiple contexts:

```java
@Bean
@StepScope
Tasklet exportPartitionTasklet(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        ExportService exportService) {

    return (contribution, chunkContext) -> {
        exportService.export(batchId, minId, maxId, sourceVersion);
        return RepeatStatus.FINISHED;
    };
}
```

In this example:

- `jobParameters['batchId']` is the input provided by the caller when launching the Job.
- `stepExecutionContext['minId']` and `maxId` are the range assigned to the current Step, for example by a `Partitioner`.
- `jobExecutionContext['sourceVersion']` is state or metadata shared across the JobExecution, typically written or promoted by an earlier Step.

Fetching values from a context requires the key to already exist at the time the bean is created. If the key has not been written or the earlier Step did not run, the value may be `null`; check and fail with a clear error rather than letting the error surface late in the service.

## 10. Identifying and Non-Identifying JobParameters

Each JobParameter has an identifying flag. Identifying parameters participate in forming the `JobInstance` identity; non-identifying parameters can still be read but do not affect the instance identity.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/customers-2026-11-15.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Here, the file and business date identify the work to be run; the requester is merely additional metadata.

A parameter can still be late-bound even if it is non-identifying:

```java
@Value("#{jobParameters['requestedBy']}") String requestedBy
```

Mark values that change the business unit of work—such as the input file, processing date, or batch ID—as identifying. If a value affects which data should be processed but is marked non-identifying, a launch may be treated as the same JobInstance as a previous execution. This makes restarts and reconciliation confusing if the value changes.

When restarting, keep identifying parameters stable. Do not add a new timestamp or UUID just to avoid `JobInstanceAlreadyCompleteException`; doing so creates a new JobInstance instead of restarting the previous work.

## 11. Data Types and Parameter Conversion

JobParameters support data types managed by Spring Batch. When injecting into a bean, Spring must convert the value to the method parameter or field type.

Example using a string:

```java
@Bean
@StepScope
Tasklet closeBusinessDayTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        ClosingService closingService) {

    LocalDate date = LocalDate.parse(businessDate);
    return (contribution, chunkContext) -> {
        closingService.close(date);
        return RepeatStatus.FINISHED;
    };
}
```

If the application creates parameters of type `LocalDate` and the Spring Batch/ConversionService version in use supports the corresponding conversion, you can inject the date type directly. However, for custom formats or cross-version compatibility, accepting a `String` and parsing explicitly often gives better control over formatting and error messages.

With numbers:

```java
@Value("#{jobParameters['pageSize']}") Integer pageSize
```

Verify that the value lies within a valid range before using it. A `pageSize` of 0 or a negative number can cause the reader to fail or create unexpected load.

## 12. Required Parameters and Default Values

If a required parameter is missing, fail early with an understandable message. You can check for null/blank right when creating the StepScope bean:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> reader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter 'input.file' is missing");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName")
            .targetType(CustomerInput.class)
            .build();
}
```

For optional parameters, you can use a default value in SpEL:

```java
@Value("#{jobParameters['mode'] ?: 'FULL'}") String mode
```

If `mode` has no value, the bean receives `FULL`. Afterward, validate that the value is within the supported set, such as `FULL` or `DELTA`. Do not use a default for a required parameter like an input file path if doing so could cause the Job to accidentally read a default resource by mistake.

## 13. Late Binding and the Scoped Proxy Lifecycle

A `@StepScope` bean does not have its target created immediately when the application context starts. Spring registers a proxy so other beans can inject the dependency early. When a StepExecution becomes active, the proxy looks up the current scope context and creates or retrieves the corresponding target bean.

This explains why you can inject a `@StepScope` reader into a `@Bean` method defining a Step even though JobParameters do not yet exist at configuration time:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader) {

    return new StepBuilder("importStep", jobRepository)
            .<CustomerInput, Customer>chunk(100, transactionManager)
            .reader(reader)
            .build();
}
```

Here `reader` is a proxy. Passing the proxy into the Step does not require the target reader to be instantiated at Step declaration time.

Do not invoke the `@Bean` method directly to obtain the target and read fields depending on JobParameters outside an active Step. A scoped bean can only resolve its context when the corresponding scope has been opened.

## 14. Why Shouldn't You Inject JobParameters into a Singleton Bean?

A singleton bean is usually created once for the application context and may be used across multiple JobExecutions. If JobParameters are stored in a singleton field, the value may not exist at initialization time or may be shared across runs.

Example of an inappropriate design:

```java
@Component
public class CustomerReaderFactory {

    @Value("#{jobParameters['input.file']}")
    private String inputFile;

    // A singleton does not have a specific StepExecution to resolve parameters.
}
```

Instead, place the late-bound value on a bean created with StepScope:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Create the reader from the current StepExecution's parameters.
}
```

If a singleton service needs values that vary by run, pass those values as method arguments from a StepScope component rather than storing JobParameters in a mutable field on the singleton.

## 15. Late Binding in Partitioning and Parallel Execution

In partitioning, each worker StepExecution has its own `StepExecutionContext`. A `@StepScope` reader can receive both the Job's shared JobParameters and the partition's specific range:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createReader(dataSource, batchId, minId, maxId);
}
```

JobParameters identify the overall batch; StepExecutionContext specifies the data range that the current partition is assigned to process. Because each worker has its own StepExecution, `@StepScope` ensures each worker receives its own min/max bounds.

With multi-threaded Steps or manually spawned threads, the scope context may not automatically propagate to threads created by the application. Use concurrency models supported by Spring Batch and avoid accessing scoped proxies from threads lacking context. `@JobScope` also requires care in partitioning or parallel flows because multiple workers can access the same JobExecution-scoped bean.

## 16. Testing Late Binding from JobParameters

Tests should prove that the same Job can receive different parameters across different runs and that StepScope beans receive the corresponding values.

With Spring Batch Test:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class LateBindingJobParametersTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void readsInputFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "/test-data/customers.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

The test above requires a fixture file at the corresponding path and appropriate outputs/assertions. Additional tests should be added running with a different file to prove the reader does not retain old values across JobExecutions.

Scenarios to verify:

- Required parameter is present and the bean receives the right value.
- Required parameter is missing or blank: Job/Step fails with a clear message.
- Optional parameter is absent: default is applied properly.
- Parameter has wrong type or format: validation fails early.
- Two JobExecutions use two different values: each StepScope bean uses its execution's value.
- Restart of the same JobInstance: identifying parameters and input resource stay stable.
- Partition: each worker receives the right shared JobParameters and its own StepExecutionContext.

Do not retrieve a StepScope bean and invoke context-dependent methods directly in a unit test when StepScope has not been opened. Run the Step/Job with Spring Batch Test or use the scope test utility appropriate for your framework version.

## 17. Common Mistakes

**Forgetting `@StepScope`:** SpEL needs JobParameters when the bean is created, whereas singletons are normally initialized before the Job runs. Place `@StepScope` on beans that need per-StepExecution values.

**Using the wrong key:** the name in `jobParameters['...']` must match the exact key added to `JobParametersBuilder`.

**Confusing JobParameters with ExecutionContext:** JobParameters are launch inputs; ExecutionContext stores state generated during execution.

**Assuming only identifying parameters are injected:** the identifying flag affects JobInstance identity, not whether late binding works.

**Marking input as non-identifying:** if the input file or business date changes without participating in identity, a launch may be treated as the same JobInstance. Choose the identifying flag according to business meaning.

**Not checking for null or providing defaults:** a missing parameter can cause obscure bean initialization failures or pass null down to a reader/service.

**Injecting dynamic values into singleton fields:** multiple JobExecutions can share the bean and retain wrong values. Use the appropriate scope or pass parameters via method arguments.

**Using `@JobScope` instead of `@StepScope` everywhere:** beans tied to a Step's reader/processor/writer should usually be StepScope so they receive the right StepExecution context.

**Assuming scope automatically propagates to any thread:** application-created threads may lack StepContext. Use an appropriate concurrency mechanism and test it.

**Changing identifying JobParameters on restart:** doing so creates a new JobInstance instead of resuming the old one.

**Using JobParameters to store progress:** JobParameters are not the place to update checkpoints. Use StepExecutionContext, JobExecutionContext, or a business data store.

## Conclusion

Late binding lets beans receive JobParameters at the moment a Job or Step actually runs, rather than at application context startup. In Spring Batch, `@StepScope` is the common choice for readers, processors, writers, and Tasklets that need per-StepExecution parameters; `@JobScope` fits dependencies scoped to a JobExecution. Use SpEL such as `#{jobParameters['input.file']}` to retrieve values, validate required parameters and data types, and choose the identifying flag according to the business unit of work. Keep JobParameters stable on restart, use ExecutionContext for checkpoints, and test multiple JobExecutions to ensure scoped beans always receive the inputs of the current run.
