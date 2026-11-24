# Late Binding from ExecutionContext in Spring Batch

In Spring Batch, many values are only known when a Job or Step starts running. For example, a file path comes from JobParameters, an ID range is assigned to a worker by a Partitioner, or an intermediate filename is produced by a previous Step. If a bean reads these values when Spring initializes the application context, the runtime data does not exist yet and injection may fail.

**Late binding** defers actual bean creation until the corresponding scope becomes active. Spring Batch provides StepScope and JobScope, combined with SpEL to pull data from JobParameters, JobExecutionContext, and StepExecutionContext. As a result, a reader, processor, writer, or Step can receive the exact values at runtime.

This lesson explains how to late-bind values from ExecutionContext, distinguish Job and Step contexts, register beans with the appropriate scope, pass data between Steps, provide per-partition contexts, and ensure state can be persisted and restored on restart.

## 1. What Is Late Binding?

Late binding is the technique of binding values to a bean at the moment the bean is actually used inside a Job or Step, rather than binding them when the application context initializes.

For example, a Job receives a parameter:

~~~text
input.file = /data/in/customer-20261115.csv
~~~

The reader needs this path to open the file. If the reader is a regular singleton, Spring may instantiate the reader at application startup, when no JobExecution or JobParameters exist yet. A SpEL expression reading JobParameters at that point has no suitable execution context.

When declaring the reader with @StepScope, Spring creates a scoped proxy at startup and only creates the target reader when the StepExecution begins. By then, JobParameters and StepExecutionContext are ready.

~~~mermaid
flowchart TD
    A["Application starts"] --> B["Spring creates scoped proxy"]
    B --> C["Job is launched"]
    C --> D["JobExecution and StepExecution are created"]
    D --> E["StepScope becomes active"]
    E --> F["Create target bean"]
    F --> G["Evaluate SpEL from ExecutionContext"]
    G --> H["Reader or Writer uses runtime value"]
~~~

Late binding is useful when the same Step configuration needs to process different files, business dates, or partitions with different input data.

## 2. Where Does ExecutionContext Store Data?

Spring Batch has different storage scopes. You need to choose the right place so Steps and workers see the right values.

| Storage Location | Scope | Who typically reads it? | Examples |
|---|---|---|---|
| JobParameters | Input of a JobInstance or JobExecution per identifying flag | Job and all Steps | businessDate, input.file, batchId |
| JobExecutionContext | Shared across Steps within a JobExecution | Subsequent Steps and JobScope | intermediate file, watermark |
| StepExecutionContext | Specific to a single StepExecution | StepScope of that Step | checkpoint, minId, maxId, partition key |

ExecutionContext is a key-value region managed by Spring Batch and persisted in the JobRepository. Values can be restored on restart if updated and saved at the proper time.

### JobParameters Are Not ExecutionContext

JobParameters are input data supplied by the caller when launching a Job. They fit values that identify a processing run, such as a business date or batch ID.

ExecutionContext stores state generated during execution. For example, the first Step creates a normalized file and stores its path for a later Step to read.

### JobExecutionContext and StepExecutionContext Differ

- JobExecutionContext belongs to a JobExecution and can share data between Steps within that run.
- StepExecutionContext belongs to a StepExecution, so each Step and each worker partition has its own context.
- When a Job restarts, a new JobExecution is created for the same JobInstance; context state is restored according to Spring Batch's restart mechanism.

Do not put per-partition data into a shared JobExecutionContext. Each worker needs its own context so it does not overwrite another worker's values.

## 3. SpEL for Accessing Runtime Data

Spring Batch supports SpEL for reading values from the active scope.

| Expression | Value |
|---|---|
| `#{jobParameters['input.file']}` | JobParameter named input.file |
| `#{jobParameters['businessDate']}` | JobParameter for business date |
| `#{jobExecutionContext['validatedFile']}` | Key in JobExecutionContext |
| `#{stepExecutionContext['minId']}` | Key in StepExecutionContext |
| `#{stepExecution.stepName}` | Name of the current Step |
| `#{stepExecution.id}` | ID of the StepExecution |
| `#{jobExecution.id}` | ID of the JobExecution |

Example injecting a key from StepExecutionContext:

~~~java
@Value("#{stepExecutionContext['minId']}")
Long minId
~~~

Example injecting a key from JobExecutionContext:

~~~java
@Value("#{jobExecutionContext['validatedFile']}")
String validatedFile
~~~

These expressions must be evaluated when the bean is created within a scope that has the corresponding execution context. Therefore, late binding must be paired with an appropriate @StepScope or @JobScope.

### Keys Must Exist and Have the Right Type

If a worker expects a minId key but the Partitioner did not write that key, the bean may receive null or a conversion error depending on the parameter type and configuration. For required data, validate the value before creating the reader or executing queries.

Prefer wrapper types like Long when you need to detect null. Then check validity conditions and throw a clear configuration error if the key is missing.

## 4. Why Is @StepScope Needed?

@StepScope creates a bean whose lifecycle is tied to the current StepExecution. The bean is created when the Step scope is active and values from StepExecutionContext, JobExecutionContext, or JobParameters are accessible.

Example of a reader receiving a file path from JobParameters:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
            "Missing JobParameter input.file"
        );
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .delimited()
        .names("customerId", "fullName", "email")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName"),
            fields.readString("email")
        ))
        .saveState(true)
        .build();
}
~~~

When the Job is launched with input.file, the target reader is created inside Step scope and receives the runtime path. Another Job can pass a different path and receive a separate target reader for its StepExecution.

### @StepScope Is a Meta-Annotation

@StepScope is a convenience annotation that declares the step scope with the appropriate proxy mode. There is no need to add another @Scope("step") on the same bean.

Placing it directly on the @Bean method is the clearest way in Java configuration:

~~~java
@Bean
@StepScope
ItemReader<CustomerInput> customerReader(...) {
    // Create reader based on runtime data.
}
~~~

## 5. Late Binding from StepExecutionContext

StepExecutionContext is suitable for data specific to a Step or a worker partition. For example, a Partitioner splits a table into ID ranges and writes minId and maxId into each partition's context.

The worker reader can retrieve those two values:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> partitionCustomerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobParameters['batchId']}") String batchId) {

    if (minId == null || maxId == null || minId > maxId) {
        throw new IllegalArgumentException(
            "Invalid partition range"
        );
    }

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("partitionCustomerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name
            FROM customer_source
            WHERE batch_id = ?
              AND customer_id >= ?
              AND customer_id <= ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps -> {
            ps.setString(1, batchId);
            ps.setLong(2, minId);
            ps.setLong(3, maxId);
        })
        .rowMapper((rs, rowNum) -> new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name")
        ))
        .saveState(true)
        .build();
}
~~~

In this example:

- minId and maxId come from the worker's own StepExecutionContext.
- batchId comes from shared JobParameters.
- @StepScope ensures the values are read when the worker StepExecution already exists.
- The reader only queries data within the assigned batch and range.

The same worker Step definition can be used for multiple partitions. Each partition has its own StepExecution, so the scoped reader receives its own range.

## 6. Partitioner Producing Data for Late Binding

A Partitioner returns a map of partition names to corresponding ExecutionContexts:

~~~java
public class CustomerRangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions =
            new LinkedHashMap<>();

        long[][] ranges = {
            {1L, 250L},
            {251L, 500L},
            {501L, 750L},
            {751L, 1000L}
        };

        for (int i = 0; i < Math.min(gridSize, ranges.length); i++) {
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", ranges[i][0]);
            context.putLong("maxId", ranges[i][1]);
            context.putString("partitionName", "partition" + i);

            partitions.put("partition" + i, context);
        }

        return partitions;
    }
}
~~~

Each context is a new object. Do not share one ExecutionContext across multiple partitions because worker values could be overwritten.

Configuring the manager Step:

~~~java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
~~~

When the manager creates worker StepExecutions, Spring Batch attaches each partition's ExecutionContext to that execution. The scoped reader then reads minId and maxId.

### Partition Names and Context Keys Are Two Different Concepts

Map key names like partition0 help Spring Batch identify partitions. Keys inside ExecutionContext such as partitionName, minId, or maxId are the data the worker needs.

You can store partitionName in the context if the worker needs it, though this is optional if the name can be obtained from StepExecution in an appropriate way.

## 7. @JobScope and Late Binding from JobExecutionContext

@JobScope creates a bean whose lifecycle is tied to a JobExecution. It is useful when a bean needs access to JobParameters or JobExecutionContext and is used within the Job's scope.

For example, a Step built according to a business date parameter:

~~~java
@Bean
@JobScope
Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveStep", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
~~~

The businessDate value is bound when the JobExecution is active. This approach is useful when Step configuration itself depends on JobParameters.

However, not every bean needs JobScope. If only a reader or writer needs Step-level runtime data, @StepScope is usually more suitable.

### Reading Data from JobExecutionContext

Example of a job-scoped bean receiving a path stored by an earlier Step in JobExecutionContext:

~~~java
@Bean
@JobScope
ArchivePlan archivePlan(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    if (validatedFile == null || validatedFile.isBlank()) {
        throw new IllegalStateException(
            "validatedFile not found in JobExecutionContext"
        );
    }

    return new ArchivePlan(validatedFile);
}
~~~

A Step-scoped bean can also read JobExecutionContext:

~~~java
@Bean
@StepScope
ItemReader<CustomerInput> validatedFileReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {
    // Create reader using the file validated by the previous Step.
}
~~~

Choose the scope according to the bean lifecycle needed. Data in JobExecutionContext has JobExecution scope, yet a bean reading that data can still be StepScope if it is only used in one Step.

## 8. Passing Data from an Earlier Step to a Later Step

A common scenario:

1. A validate Step inspects the input file.
2. The validate Step produces a normalized file.
3. The validate Step stores the path in StepExecutionContext.
4. After the Step finishes, the key is promoted to JobExecutionContext.
5. An import Step uses late binding to retrieve that path.

Data can be written into StepExecutionContext inside a Tasklet:

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputValidationTasklet tasklet,
        ExecutionContextPromotionListener promotionListener) {

    return new StepBuilder("validateInputStep", jobRepository)
        .tasklet(tasklet, transactionManager)
        .listener(promotionListener)
        .build();
}
~~~

Inside the Tasklet:

~~~java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception {

    String validatedPath = validateAndPrepareInput();

    contribution.getStepExecution()
        .getExecutionContext()
        .putString("validatedFile", validatedPath);

    return RepeatStatus.FINISHED;
}
~~~

Registering the promotion listener:

~~~java
@Bean
ExecutionContextPromotionListener promotionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"validatedFile"});
    listener.setStatuses(new String[] {"COMPLETED"});

    return listener;
}
~~~

After validateInputStep completes with a matching status, the listener promotes the validatedFile key from StepExecutionContext to JobExecutionContext.

The import Step can use:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> importReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("importReader")
        .resource(new FileSystemResource(validatedFile))
        .delimited()
        .names("customerId", "fullName")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName")
        ))
        .saveState(true)
        .build();
}
~~~

Do not assume a key written into StepExecutionContext automatically appears in JobExecutionContext. For a later Step to read the key, promote it or write it to JobExecutionContext through an appropriate mechanism.

### Promote Only Data That Actually Needs to Be Shared

StepExecutionContext should hold Step-specific state. Only promote keys needed by subsequent Steps to JobExecutionContext. This avoids bloating the shared context and sharing unnecessary internal state.

## 9. Late Binding from JobParameters

JobParameters are a common data source for late binding. For example, a caller launches the Job with:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "/data/in/customer.csv")
    .addString("businessDate", "2026-11-15")
    .addString("batchId", "BATCH-20261115")
    .toJobParameters();

jobLauncher.run(importJob, parameters);
~~~

The reader can receive input.file directly:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Create reader using the runtime path.
}
~~~

A processor or writer can also receive businessDate or batchId via @StepScope.

JobParameters fit stable input data for a run. If a Step produces a new value at runtime, store that value in ExecutionContext rather than trying to modify JobParameters.

### Identifying and Non-Identifying Parameters

A JobParameter has an identifying flag that determines JobInstance identity. A non-identifying parameter can still be read via SpEL without changing identity.

Late binding does not alter this rule. For example, requestedBy as non-identifying can still be injected, while changing requestedBy does not create a new JobInstance.

## 10. Combining Multiple Data Sources in One Bean

A bean may need data from multiple scopes. For example, a reader using batchId from JobParameters and minId and maxId from the partition context:

~~~java
@Bean
@StepScope
ItemReader<Customer> customerReader(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new CustomerRangeReader(batchId, minId, maxId);
}
~~~

This makes sense because:

- batchId describes the overall data batch.
- minId and maxId describe the worker's specific slice of data.
- StepScope provides both JobParameters and StepExecutionContext when the Step runs.

Do not copy batchId into every partition context if JobParameters is already the canonical source and workers can read it directly. Avoid duplicating the same value across multiple places with the risk of inconsistency.

## 11. Default Values and Validating Required Keys

Some keys are optional. SpEL can use the Elvis operator to provide a default value:

~~~java
@Value("#{jobParameters['output.mode'] ?: 'STANDARD'}")
String outputMode
~~~

Defaults should only be used when there is a clear business meaning. For required input.file, minId, or batchId, do not silently fall back to a default that could cause a worker to read the wrong data.

Validation can be performed in the factory method:

~~~java
@Bean
@StepScope
CustomerRangeReader customerRangeReader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    if (minId == null || maxId == null) {
        throw new IllegalStateException(
            "Partition context must contain minId and maxId"
        );
    }

    if (minId > maxId) {
        throw new IllegalArgumentException(
            "minId must be less than or equal to maxId"
        );
    }

    return new CustomerRangeReader(minId, maxId);
}
~~~

Specific error messages help distinguish missing-context errors from database query failures or data errors.

### Use Appropriate Data Types

If the context stores a Long via putLong, inject it into a Long. If a date string is stored, you can inject a String and parse explicitly with LocalDate.parse. Avoid complex implicit casting or primitive types when a value might be missing.

## 12. Bean Creation Timing and Scoped Proxies

When the application context starts, Spring creates a scoped proxy for @StepScope or @JobScope beans. The proxy stands in for the actual bean without needing to create the target immediately.

When the corresponding StepExecution or JobExecution becomes active, the proxy obtains the target bean inside that scope. @Value expressions are evaluated when the target is created.

This allows one bean definition to be used across multiple runs while each execution gets its own runtime data.

~~~mermaid
sequenceDiagram
    participant App as ApplicationContext
    participant Proxy as Scoped Proxy
    participant Job as JobExecution
    participant Step as StepExecution
    participant Target as Target Bean

    App->>Proxy: Create proxy at startup
    Job->>Step: Start Step
    Step->>Proxy: Call reader
    Proxy->>Target: Create target in StepScope
    Target->>Target: Read SpEL from ExecutionContext
    Target-->>Proxy: Return configured target
    Proxy-->>Step: Perform operation
~~~

### Do Not Invoke the Scope Too Early

If a singleton bean invokes a method on the scoped target directly while the application context is starting up, no StepExecution exists yet and Spring cannot locate a current context.

A common error looks like:

~~~text
Scope 'step' is not active for the current thread
~~~

The cause is usually that a scoped bean was accessed before the Step started or from a thread without an appropriate execution context.

Let the framework call scoped beans during the Step lifecycle. Avoid calling methods on a reader or writer in a constructor, @PostConstruct, or during Job configuration if that call forces early target creation.

## 13. Scope of Reader, Processor, and Writer

Late binding is not just for readers. Any component needing runtime data can use the appropriate scope.

### Reader

A reader can receive an input file or partition range. This is the most common case because the read source varies by JobParameters or partition.

### Processor

A processor can receive businessDate, tenant, or a configuration code to apply transformation rules:

~~~java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['businessDate']}")
        String businessDate) {

    LocalDate effectiveDate = LocalDate.parse(businessDate);

    return input -> mapOrder(input, effectiveDate);
}
~~~

### Writer

A writer can receive a partition name or dedicated output path:

~~~java
@Bean
@StepScope
ItemWriter<Customer> customerWriter(
        @Value("#{stepExecutionContext['partitionName']}")
        String partitionName,
        CustomerRepository repository) {

    return chunk -> {
        for (Customer customer : chunk.getItems()) {
            repository.saveProcessed(customer, partitionName);
        }
    };
}
~~~

Only scope beans that truly need runtime data. A stateless service that does not depend on execution context should usually be a singleton for reuse and ease of testing.

## 14. @StepScope in Partitioning

Partitioning is a scenario where late binding from StepExecutionContext shows clear benefits.

Each partition has its own ExecutionContext:

~~~text
partition0:
  minId = 1
  maxId = 250

partition1:
  minId = 251
  maxId = 500

partition2:
  minId = 501
  maxId = 750
~~~

The worker Step definition is identical, yet each worker StepExecution has a different context. A @StepScope bean is instantiated within each StepExecution's scope, so the reader receives the matching range.

Requirements:

- The Partitioner creates a fresh context for each partition.
- Keys in the context match the SpEL expressions consistently.
- Partition names remain stable if restart is needed.
- Workers use @StepScope for beans that late-bind partition values.
- Queries use the exact assigned range and shared batch filter.
- The partition plan is deterministic and non-overlapping.

### @JobScope in Partitioning Requires Caution

JobScope is scoped to a JobExecution, meaning a single target bean can be shared across the Job. In partitioning or multi-threaded processing, Spring Batch does not always control threads spawned by an execution mechanism to bind the job scope context properly.

Therefore, do not rely on JobScope in partition workers or multi-threaded Steps without verifying the execution model and scope context support of your version. For partition-specific data, use StepExecutionContext and @StepScope. For shared data, use JobParameters or pass it safely via context or stateless beans.

## 15. StepScope and Multi-Threaded Steps

Partitioning must be distinguished from a multi-threaded Step.

In partitioning, each worker has its own StepExecution. Therefore, each worker's StepScope can receive its own context.

In a multi-threaded Step, multiple threads can process concurrently within a single StepExecution. A Step-scoped bean is bound to that StepExecution and does not automatically create a separate target per item or per thread. If the bean contains mutable state, threads can access it concurrently.

Principles:

- Do not store the current item in a field of a step-scoped processor shared across threads.
- Readers and writers must support concurrency according to the configuration.
- Do not assume StepScope equals thread scope.
- Use stateless objects or thread-safe state.
- Test concurrent behavior with the actual TaskExecutor.

Late binding solves bean lifecycle and configuration data injection. It does not automatically make a bean thread-safe.

## 16. ExecutionContext Is Saved and Restored on Restart

ExecutionContext is part of restart metadata. A reader or writer supporting ItemStream can save checkpoints in StepExecutionContext.

The ItemStream lifecycle consists of:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

- open(...) restores saved state or initializes fresh state.
- update(...) writes current state into ExecutionContext at checkpoints.
- close() closes resources when the Step ends.

Standard readers such as FlatFileItemReader can save read positions when saveState is enabled. On restart, Spring Batch restores the context and the reader resumes from the checkpoint.

### Late Binding Does Not Save Checkpoints Automatically

@StepScope only helps a bean receive runtime values. It does not make a reader restartable or save read positions by itself.

You need:

- A reader implementing ItemStream or wrapped by a state-managing component.
- A stable reader name.
- saveState enabled when restart is needed.
- ExecutionContext used to persist the appropriate state.
- No overwriting of internal reader checkpoint keys.
- A stable data source and partition plan between the original run and restart.

### Do Not Confuse Configuration Data with Checkpoints

minId and maxId are data describing the partition range. Current item count or current row is the reader's checkpoint. Both may reside in StepExecutionContext, yet they serve different purposes.

Do not manually alter internal reader keys unless you understand how the reader restores state. Use separate keys with clear prefixes for application data.

## 17. ExecutionContext Must Contain Serializable Data

JobRepository persists ExecutionContext to the metadata store. Therefore, values must be compatible with the serializer and storage configuration.

Should store:

- String, Long, Integer, Double, Boolean.
- Date/time or types supported by the serializer.
- IDs, paths, ranges, and partition codes.
- Small structures that serialize reliably.

Should not store:

- JDBC Connection or ResultSet.
- Open InputStream, Reader, or file handles.
- Thread, Executor, or Spring beans.
- Large entity graphs or objects with circular references.
- Objects depending on unrecoverable runtime resources.

Instead of storing a FileInputStream, store the file path and open the stream in the reader when the Step starts. Instead of storing a repository, store the batch ID so the scoped bean receives the repository via dependency injection and queries as needed.

## 18. Naming Keys in ExecutionContext

Context keys form a contract between writers and readers. Name them meaningfully, keep them stable, and avoid colliding with internal framework keys.

Example:

~~~java
context.putString("input.validatedFile", path);
context.putString("batch.sourceId", batchId);
context.putLong("partition.minId", minId);
context.putLong("partition.maxId", maxId);
context.putString("partition.name", partitionName);
~~~

Corresponding SpEL:

~~~java
@Value("#{jobExecutionContext['input.validatedFile']}")
String validatedFile
~~~

~~~java
@Value("#{stepExecutionContext['partition.minId']}")
Long minId
~~~

Using namespaces or prefixes helps separate application keys from checkpoint keys created by readers/writers.

### Avoid Changing Key Semantics

If an old JobInstance may be restarted, do not change the meaning of context keys across application versions without a compatibility plan. For instance, if minId was previously inclusive but a new version treats it as exclusive, a restart may skip or duplicate records.

When context schema changes are needed, consider versioning:

~~~java
context.putString("partition.context.version", "v2");
~~~

Workers check the version before use and reject incompatible contexts rather than guessing.

## 19. Late Binding and JobParameters Validation

Late binding does not replace input validation. JobParameters should be validated before the Step begins.

Example validator:

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return parameters -> {
        String inputFile = parameters.getString("input.file");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "JobParameter input.file is required"
            );
        }
    };
}
~~~

Attach the validator to the Job:

~~~java
return new JobBuilder("importJob", jobRepository)
    .start(importStep)
    .validator(importParametersValidator)
    .build();
~~~

The validator enforces the Job's input contract. A @StepScope bean should still validate StepExecutionContext keys because those may be produced during execution.

Division of responsibilities:

- JobParametersValidator checks parameters provided by the caller.
- Partitioner validates and creates partition ranges.
- Step-scoped beans check required values when created.
- Readers/writers check resources and state during execution.

## 20. Common Mistakes with Late Binding

### Forgetting @StepScope

A singleton reader attempting to read stepExecutionContext before the Step runs may fail to find the scope or receive wrong values. Use @StepScope for beans requiring Step-level runtime data.

### Using JobScope for partition-specific data

JobExecutionContext is shared across the JobExecution. Do not place per-partition minId/maxId there. Use StepExecutionContext and StepScope.

### Writing to StepExecutionContext but reading from JobExecutionContext

The two contexts are distinct. For a later Step to read a key, promote it or write it to JobExecutionContext.

### Misspelling keys

If the Partitioner writes minID while SpEL reads minId, the worker will not get the expected value. Use constants or consistent key conventions.

### Injecting into a singleton service

A singleton bean without a suitable execution scope may be instantiated before the JobExecution. If a service needs runtime data, pass values from a scoped bean into method arguments or give that bean an appropriate scope.

### Invoking scoped beans too early

Calling the target in a constructor, @PostConstruct, or at application context initialization can trigger a scope-not-active error. Only access the bean during the Job/Step lifecycle.

### Using primitives for optional or missing keys

If Long minId has no value, using primitive long can cause a conversion error. Use wrapper types and check for null before using.

### Storing non-serializable objects

ExecutionContext is persisted in the JobRepository. Connections, streams, or beans are unsuitable for storage. Store only small, recoverable data.

### Sharing one ExecutionContext across multiple partitions

Workers could share the same object and overwrite values. Create a fresh context for each partition.

### Confusing StepScope with thread scope

One StepExecution can be processed by multiple threads. Scoped beans do not automatically create an instance per thread. Ensure state is thread-safe.

### Assuming @StepScope automatically enables restart

Scope does not replace ItemStream, checkpoints, or saveState. Readers must support saving and restoring state.

## 21. Testing Late Binding

You should test both value injection and the actual lifecycle of scoped beans.

### Testing a reader receiving JobParameters

1. Create JobParameters containing input.file.
2. Run the Step in a Spring Batch test context.
3. Verify the reader opens the expected resource.
4. Verify the read data matches the passed file.
5. Run another JobExecution with a different file and verify the reader receives the new value.

Do not simply create an application context and call the reader directly when StepScope has not been activated.

### Testing a reader receiving StepExecutionContext

1. Create a StepExecutionContext with minId and maxId.
2. Run the worker Step.
3. Verify the reader receives both values properly.
4. Verify the query reads only the worker's range.
5. Create a second worker with a different range and verify contexts are not mixed up.

### Testing data passing between Steps

1. The first Step writes validatedFile into StepExecutionContext.
2. ExecutionContextPromotionListener promotes the key when the Step succeeds.
3. The next Step reads the key from jobExecutionContext.
4. Verify the reader opens the normalized file.
5. Verify that when the first Step fails, the key is not promoted according to the status configuration.

### Testing restart

1. Process part of the data and make the Step fail.
2. Verify ExecutionContext is saved at the checkpoint.
3. Restart the same JobInstance.
4. Verify the scoped bean is created with the restored context.
5. Verify the reader resumes from the right position without skipping or duplicating records.

### Testing partitions

Create multiple partitions with different contexts and verify each worker has its own StepExecutionContext. Do not test only the map returned by the Partitioner; verify the @StepScope bean actually receives the right values when the worker runs.

You can use JobLauncherTestUtils, JobRepositoryTestUtils, and Spring Batch scope test utilities appropriate for your library version. The key thing to verify is that the bean is created in the real scope and receives the right execution context, not just testing a SpEL expression as a string.

## 22. Workflow for Implementing Late Binding from ExecutionContext

When a bean needs runtime data, you can follow this sequence:

1. **Identify the source:** JobParameters, JobExecutionContext, or StepExecutionContext.
2. **Choose the scope:** use @StepScope for Step/partition data; use @JobScope for Job-level data when supported.
3. **Define keys:** name them clearly and consistently between writers and readers.
4. **Produce the data:** Partitioner, Tasklet, or listener writes values into the proper context.
5. **Share if needed:** promote keys from StepExecutionContext to JobExecutionContext when a later Step needs them.
6. **Bind via SpEL:** use @Value with the corresponding key.
7. **Validate values:** verify required keys, data types, and ranges.
8. **Keep context serializable:** store only small, recoverable data.
9. **Design for restart:** keep keys and context semantics stable; readers persist appropriate checkpoints.
10. **Test the scope:** run real Steps/Jobs in a test context, including multiple executions and partitions.

## 23. Key Takeaways

- Late binding defers data binding until a JobExecution or StepExecution is active.
- @StepScope creates beans per StepExecution and fits readers, processors, and writers needing Step-specific or partition-specific data.
- @JobScope creates beans per JobExecution and fits data shared within the Job when the execution model supports that scope.
- Use `#{stepExecutionContext['key']}` to read keys from StepExecutionContext.
- Use `#{jobExecutionContext['key']}` to read keys from JobExecutionContext.
- Use `#{jobParameters['key']}` to read JobParameters.
- StepExecutionContext is isolated per StepExecution; partition workers should not share contexts.
- For a later Step to read a key produced by an earlier Step, promote the key or write it to JobExecutionContext.
- @StepScope does not automatically make a bean thread-safe or enable restarts.
- ExecutionContext must hold serializable data; do not store connections, streams, or Spring beans.
- Readers need appropriate ItemStream/checkpoint/saveState support to recover on restart.
- Validate required keys and data types before use.
- Test beans in real scopes, including JobParameters, partition contexts, promotion, and restarts.

Late binding from ExecutionContext allows a single Step configuration to serve multiple runs and multiple partitions while still receiving accurate runtime data. By choosing the right scope, storing keys at the right level, and keeping ExecutionContext recoverable, Spring Batch can pass state across stages cleanly and reliably.

