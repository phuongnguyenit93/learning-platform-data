# Scope When Testing Jobs

In Spring Batch, many beans can only be created or used properly while a job or step is running. Two important scopes are `@JobScope` and `@StepScope`. They allow beans to receive runtime values from `JobParameters`, `JobExecutionContext`, or `StepExecutionContext` via late binding.

When writing tests, you need to set up the proper execution context so scoped beans behave just as they do in a real job. Without an active `JobExecution` or `StepExecution`, the application may fail to find the scope, fail to resolve SpEL, or create beans with wrong runtime data. Spring Batch Test provides listeners and utilities to establish these scopes in unit tests and integration tests.

## 1. Why Does Scope Matter When Testing?

An ordinary bean can be instantiated right when the Spring ApplicationContext starts up. However, beans with `@StepScope` or `@JobScope` depend on Spring Batch's execution context. Values such as input filenames, business dates, partition ranges, or checkpoints only exist when a job or step begins.

Example of a reader receiving a path from JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readBigDecimal("amount")))
            .build();
}
```

This reader bean needs `inputFile` at the moment the step execution is active. In a test, merely creating the ApplicationContext and calling `orderReader()` directly is not enough. The test needs to activate step scope and provide a `StepExecution` with suitable JobParameters.

## 2. Distinguishing Singleton, JobScope, and StepScope

| Scope | Lifecycle | Best suited for |
|---|---|---|
| Singleton (default) | One instance in the ApplicationContext | Shared stateless services/components that do not depend on a specific execution. |
| `@JobScope` | One instance within a single `JobExecution` | Beans needing JobParameters or Job ExecutionContext and shared across steps of the same job execution. |
| `@StepScope` | One instance within a single `StepExecution` | Readers, writers, processors, or tasklets needing step/partition-specific parameters. |

On restart, a new `JobExecution` is created for the same `JobInstance`; job-scoped beans have a lifecycle tied to the new execution. Each worker/partition has its own `StepExecution`, so step-scoped beans can receive data specific to that partition.

Do not use `@JobScope` or `@StepScope` just to avoid passing parameters between classes. Use scopes when a bean genuinely depends on job/step execution data. Business services that do not depend on execution should normally stay stateless and use singleton scope.

## 3. Late Binding and Proxies in Scoped Beans

Spring Batch creates scoped beans through proxies. A proxy bean can be injected into configuration or singleton components before the scope actually becomes active. The target object is instantiated when the corresponding execution begins and late-bound values are resolved.

Examples of commonly used expressions:

| SpEL | Value obtained from |
|---|---|
| `#{jobParameters['inputFile']}` | JobParameters of the current job execution. |
| `#{jobExecutionContext['batchReference']}` | Job ExecutionContext. |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext of the current step. |
| `#{stepExecution.stepName}` | Name of the current step. |
| `#{jobExecution.jobInstance.jobName}` | Job name of the current execution. |

Tests must set up the proper context before calling methods on the proxy. Calling a scoped bean outside its scope usually triggers an error like `ScopeNotActiveException` or a message stating the scope is not registered/active, depending on Spring version and configuration.

## 4. Required Dependencies for Spring Batch Test

To test scopes and job/step execution, add the `spring-batch-test` module matching the version of Spring Batch in use.

Gradle example:

```groovy
dependencies {
    testImplementation("org.springframework.batch:spring-batch-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If the project uses Spring Boot dependency management or the Spring Batch BOM, let dependency versions be managed centrally to avoid version mismatches between `spring-batch-core` and `spring-batch-test`.

Useful components:

- `@SpringBatchTest`: configures Spring Batch test support and testing utilities.
- `StepScopeTestExecutionListener`: activates step scope for the test method.
- `JobScopeTestExecutionListener`: activates job scope for the test method.
- `StepScopeTestUtils`: executes a block of code inside step scope with a provided `StepExecution`.
- `JobScopeTestUtils`: executes a block of code inside job scope with a provided `JobExecution`.
- `MetaDataInstanceFactory`: constructs metadata objects such as `JobExecution` and `StepExecution` for tests.
- `JobLauncherTestUtils`: launches jobs/steps in integration tests.
- `JobRepositoryTestUtils`: helps clean up test metadata when needed.

Exact package names and overloads may vary by Spring Batch version. Use the APIs provided by the exact `spring-batch-test` version in your project.

## 5. Using @SpringBatchTest in Integration Tests

`@SpringBatchTest` is a convenient way to test jobs or steps configured in a Spring context. This annotation registers test utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils` and enables the listeners required to work with job/step scopes.

Example test structure:

```java
@SpringBootTest
@SpringBatchTest
class OrderImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importsOrdersUsingTestParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

This example assumes the job is configured in the application context and the test has an appropriate database/schema. `JobLauncherTestUtils` needs to know which job to run; if the context contains multiple jobs, you may need to configure the job name on the test utility according to your version's API.

`@SpringBatchTest` does not automatically supply test files or a pre-populated database. Tests still must create inputs and configure datasources, metadata schemas, and required business data.

## 6. Testing a StepScope Bean with StepScopeTestUtils

If you only want to test a reader, processor, or writer without running the entire job, you can use `StepScopeTestUtils.doInStepScope`.

Example testing a reader receiving `inputFile` from JobParameters:

```java
@SpringJUnitConfig(OrderBatchConfiguration.class)
class OrderReaderScopeTest {

    @Autowired
    private FlatFileItemReader<OrderInput> orderReader;

    @Test
    void readsFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            orderReader.open(stepExecution.getExecutionContext());
            try {
                OrderInput first = orderReader.read();
                assertThat(first.orderId()).isEqualTo("O-001");
            } finally {
                orderReader.close();
            }
            return null;
        });
    }
}
```

The key point is that `StepScopeTestUtils` establishes the context for calls inside the lambda. Upon exiting the block, step scope is closed again. Operations accessing the scoped bean must take place inside that block.

If the reader is configured with `@StepScope`, inject the proxy into the test. Do not invoke the `@Bean` factory method directly to fetch a target object outside scope.

## 7. Creating a StepExecution with JobParameters and ExecutionContext

`MetaDataInstanceFactory` helps build test metadata without launching a real job.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "src/test/resources/orders.csv")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putLong("minId", 100L);
stepExecution.getExecutionContext().putLong("maxId", 200L);

stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "TEST-BATCH-01");
```

When testing scoped beans:

- `jobParameters` comes from `stepExecution.getJobParameters()` via the linked JobExecution.
- `stepExecutionContext` comes from `stepExecution.getExecutionContext()`.
- `jobExecutionContext` comes from `stepExecution.getJobExecution().getExecutionContext()`.

This allows testing SpEL expressions without running the entire job flow. Ensure the exact keys and data types expected by the bean are populated.

## 8. Using StepScopeTestExecutionListener

When you want multiple test methods in a class to have step scope automatically, you can use `StepScopeTestExecutionListener`. The listener sets up a `StepExecution` for the test method and closes the scope after the test finishes.

Example:

```java
@SpringJUnitConfig(OrderBatchConfiguration.class)
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class OrderReaderStepScopeTest {

    @Autowired
    private FlatFileItemReader<OrderInput> orderReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .toJobParameters();

        StepExecution execution = MetaDataInstanceFactory
                .createStepExecution(parameters);
        execution.getExecutionContext().putString("region", "NORTH");
        return execution;
    }

    @Test
    void readsWithActiveStepScope() throws Exception {
        orderReader.open(new ExecutionContext());
        try {
            assertThat(orderReader.read()).isNotNull();
        } finally {
            orderReader.close();
        }
    }
}
```

The listener can look for a `getStepExecution` factory method on the test class to obtain a custom execution; if absent, the listener uses default metadata. Consult the API documentation for your exact version regarding factory method conventions and listener registration.

When using `@SpringBatchTest`, scope listeners are already registered on the test context; avoid duplicate registration that causes conflicts. If declaring `@TestExecutionListeners` manually, use `MERGE_WITH_DEFAULTS` when other default Spring Test listeners must be retained.

## 9. Testing a JobScope Bean with JobScopeTestUtils

`@JobScope` ties a bean's lifecycle to a single `JobExecution`. The bean can read JobParameters or the Job ExecutionContext and is shared across steps belonging to the same job execution.

Example of a job-scoped bean:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['batchReference']}") String batchReference) {

    return new BatchRunDescriptor(businessDate, batchReference);
}
```

A test can construct a `JobExecution` and run code inside job scope:

```java
@SpringJUnitConfig(BatchConfiguration.class)
class BatchRunDescriptorTest {

    @Autowired
    private BatchRunDescriptor batchRunDescriptor;

    @Test
    void resolvesJobScopedValues() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution jobExecution = MetaDataInstanceFactory
                .createJobExecution(parameters);
        jobExecution.getExecutionContext()
                .putString("batchReference", "BATCH-TEST-01");

        JobScopeTestUtils.doInJobScope(jobExecution, () -> {
            assertThat(batchRunDescriptor.businessDate())
                    .isEqualTo("2026-11-15");
            assertThat(batchRunDescriptor.batchReference())
                    .isEqualTo("BATCH-TEST-01");
            return null;
        });
    }
}
```

`JobScopeTestUtils` sets up job scope for the duration of the callback. If the version in use does not provide this utility or the test needs to verify the entire job lifecycle, you can use `JobScopeTestExecutionListener` or launch the job via `JobLauncherTestUtils`.

## 10. Using JobScopeTestExecutionListener

Similar to step scope, job scope has a listener to activate the context during test methods.

```java
@SpringJUnitConfig(BatchConfiguration.class)
@TestExecutionListeners(
        listeners = JobScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class BatchRunDescriptorScopeTest {

    @Autowired
    private BatchRunDescriptor batchRunDescriptor;

    public JobExecution getJobExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution execution = MetaDataInstanceFactory
                .createJobExecution(parameters);
        execution.getExecutionContext()
                .putString("batchReference", "BATCH-TEST-01");
        return execution;
    }

    @Test
    void readsValuesFromActiveJobScope() {
        assertThat(batchRunDescriptor.businessDate())
                .isEqualTo("2026-11-15");
    }
}
```

The listener sets up a `JobExecution` for the test method using Spring Batch Test's factory-method convention. When using `@SpringBatchTest`, verify whether the listener is already auto-registered so you do not configure it twice.

## 11. When to Use Utilities, Listeners, or Run the Full Job?

These approaches serve different levels of testing:

| Approach | Scope | When appropriate |
|---|---|---|
| `StepScopeTestUtils` | One block of code inside StepScope | Testing a scoped reader/processor/writer independently of Job flow. |
| `JobScopeTestUtils` | One block of code inside JobScope | Testing a bean depending on JobParameters/JobExecutionContext. |
| Scope test execution listener | Scope activated for test methods | Multiple test methods needing the same kind of metadata setup. |
| `JobLauncherTestUtils` | Launches a real job/step in the test context | Verifying wiring, flow, transactions, and interactions across components. |

Test scoped beans in isolation when isolating bugs in late binding or bean logic. Use integration tests when confirming that Spring Batch actually creates the scope, launches the step, and persists metadata as expected.

## 12. Testing a StepScope Reader with Data in Step ExecutionContext

A partitioned reader normally fetches its data range from the Step ExecutionContext. The test must populate the corresponding keys before activating step scope.

Example:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .selectClause("select id, name")
            .fromClause("from customer")
            .whereClause("where id between :minId and :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new CustomerInput(
                    rs.getLong("id"), rs.getString("name")))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Test:

```java
StepExecution execution = MetaDataInstanceFactory.createStepExecution();
execution.getExecutionContext().putLong("minId", 100L);
execution.getExecutionContext().putLong("maxId", 199L);

StepScopeTestUtils.doInStepScope(execution, () -> {
    customerReader.open(execution.getExecutionContext());
    try {
        CustomerInput item = customerReader.read();
        assertThat(item).isNotNull();
        assertThat(item.id()).isBetween(100L, 199L);
    } finally {
        customerReader.close();
    }
    return null;
});
```

The test requires a test database with the matching schema and data. If you only want to test SpEL or parameter reception, you can mock dependencies instead of spinning up a real database; however, to verify paging queries and row mapping, a database integration test is necessary.

## 13. Scopes and Per-Partition Testing

Each partition has its own `StepExecution`, so step-scoped beans should receive the context of the matching partition. When testing a worker step, construct a StepExecution whose `ExecutionContext` reflects the simulated partition.

Example of two partitions:

```java
StepExecution north = MetaDataInstanceFactory.createStepExecution();
north.getExecutionContext().putString("region", "NORTH");

StepExecution south = MetaDataInstanceFactory.createStepExecution();
south.getExecutionContext().putString("region", "SOUTH");
```

You can execute the same proxy inside two separate scopes to verify values resolve per execution:

```java
String northRegion = StepScopeTestUtils.doInStepScope(north,
        () -> regionScopedReader.region());

String southRegion = StepScopeTestUtils.doInStepScope(south,
        () -> regionScopedReader.region());

assertThat(northRegion).isEqualTo("NORTH");
assertThat(southRegion).isEqualTo("SOUTH");
```

This example assumes a `regionScopedReader` bean has a `region()` method purely to illustrate late-bound values. In real applications, test the worker's read/write behavior instead of adding test-only accessors that serve no purpose in the production API.

Do not run multiple test scopes concurrently on the same thread or share the same scoped target instance. Scope contexts are bound per execution/thread and managed by Spring Batch Test; when testing real concurrency, use a separate integration test to verify thread safety.

## 14. Testing ExecutionContext vs. JobParameters

A common mistake is placing data into the wrong context. JobParameters are inputs for the run; Step ExecutionContext and Job ExecutionContext are runtime state.

| Data to test | Where to set it |
|---|---|
| File path passed when launching the job | `JobParameters` |
| Business date provided by scheduler | `JobParameters` |
| Partition min/max IDs | `StepExecution.getExecutionContext()` |
| File validated and promoted by an earlier step | `JobExecution.getExecutionContext()` |
| Reader checkpoint | Step ExecutionContext via reader/stream lifecycle |

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putString("partition", "P-01");
stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "B-20261115-01");
```

A bean using `#{jobParameters['businessDate']}` needs the value in JobParameters. A bean using `#{stepExecutionContext['partition']}` needs the value in Step ExecutionContext. A bean using `#{jobExecutionContext['batchReference']}` needs the value in Job ExecutionContext.

## 15. Testing a Step-Scoped Tasklet

A Tasklet can be declared `@StepScope` to receive runtime parameters. You can test the tasklet directly in step scope instead of running the whole job.

```java
@Bean
@StepScope
Tasklet archiveFileTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        archiveService.archive(inputFile);
        return RepeatStatus.FINISHED;
    };
}
```

In the test, create a StepExecution with JobParameters and invoke the tasklet inside `StepScopeTestUtils`. If the test only verifies that the parameter was passed properly, you can mock `archiveService` and verify the invocation. If you want to test transactions, metadata, or restarts, run the step through `JobLauncherTestUtils` with a test repository.

Do not call the factory method `archiveFileTasklet(...)` directly in a test to pass dummy values and conclude that scoping works. Doing so tests an ordinary Java method, not Spring Batch's late binding or proxy behavior.

## 16. Testing Job-Scoped Beans Shared Across Steps

`@JobScope` is useful when multiple steps in the same JobExecution need a bean holding shared metadata, such as a batch descriptor. To verify this, ensure accesses occur within the same JobScope and the same `JobExecution`.

Bean example:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    return new BatchRunDescriptor(businessDate);
}
```

In an integration test, launch the job with test JobParameters and inject the bean proxy into components used by the job. Steps in the same JobExecution will resolve the same job-scoped target within scope.

When testing two different JobExecutions, establish two separate job scopes. Do not retain a reference to the target object of an earlier execution and use it after the scope closes. Always access via the proxy within the corresponding execution boundary.

## 17. Testing Restart with Scoped Beans

Restart creates a new `JobExecution` for the same `JobInstance`. Because scopes are bound to executions, job-scoped and step-scoped beans are instantiated in the context of the new execution. Late-bound values are resolved from the parameters and ExecutionContext of the restart run.

When testing restart, verify:

- Identifying JobParameters remain identical so the same JobInstance is resumed.
- A new JobExecution is created.
- Already completed steps are skipped by default, unless `allowStartIfComplete(true)`.
- Failed steps are re-run according to flow and `startLimit`.
- Readers/writers restore checkpoints from ExecutionContext.
- Scoped beans receive the right JobParameters and context of the new execution.
- Beans do not retain mutable data from the old execution.

An isolated scope test is not enough to prove restart works. You need an integration test with a persistent JobRepository or appropriate test repository, running a failing job and restarting it with the same identifying parameters.

## 18. Scope and Concurrency in Tests

Local partitioning or a multi-threaded step can run multiple workers concurrently. `@StepScope` creates separate targets per StepExecution, yet does not guarantee every dependency used by the target is thread-safe.

For instance, a step-scoped reader may inject a shared singleton service. If that service holds mutable state, multiple workers can still trigger race conditions.

When testing concurrency:

- Verify each worker has its own `StepExecution` and `ExecutionContext`.
- Verify late binding receives the right partition key/range.
- Do not share stateful readers/writers across workers if the implementation is not thread-safe.
- Check whether singleton dependencies injected into scoped beans are safe for concurrent calls.
- Use a database or test resources capable of simulating real concurrency when verifying locks and transactions.
- Do not assume a sequentially executed unit test proves thread safety.

## 19. Common Mistakes When Testing Scopes

| Symptom | Common cause | Resolution |
|---|---|---|
| `ScopeNotActiveException` | Calling scoped proxy outside job/step scope. | Use `StepScopeTestUtils`, `JobScopeTestUtils`, listeners, or launch the job. |
| SpEL returns `null` | Key missing from JobParameters/ExecutionContext or misspelled key name. | Populate the right context and data type before invoking the bean. |
| Bean is created but uses stale values | Test invoked target outside scope or retained a reference across executions. | Inject the proxy and access it within the matching scope. |
| `@StepScope` is not applied | Bean was not declared scoped or scope configuration is not enabled. | Check annotations/configuration and Spring Batch dependencies. |
| Reader test cannot find file | JobParameters point to the wrong path or resource does not exist in test. | Use an existing test resource and deterministic path. |
| `JobParameters` are right but step context lacks key | Key was mistakenly placed into Job ExecutionContext. | Put the key in `stepExecution.getExecutionContext()`. |
| Job-scoped bean fails to resolve | No active JobExecution scope exists. | Use JobScopeTestUtils/listener or launch the job. |
| Isolated test passes but real job fails | Unit test only checks the bean, not wiring/flow/transactions. | Add an integration test with JobLauncherTestUtils. |
| Test affected by previous execution | Shared test metadata/database or uncleaned data. | Use isolated test data and clean JobRepository in a controlled way. |
| Scoped bean encounters race condition | Singleton dependency inside the bean is not thread-safe. | Inspect the entire dependency graph and run concurrency tests. |

## 20. Process for Writing Tests for Scoped Components

When testing a bean with `@JobScope` or `@StepScope`, follow this sequence:

1. **Identify the scope:** does the bean depend on JobExecution or StepExecution?
2. **List late-bound keys:** which JobParameters, Job ExecutionContext, or Step ExecutionContext keys are used?
3. **Choose the test level:** isolated bean test, scope listener test, or full job/step run?
4. **Create metadata:** use `MetaDataInstanceFactory` to construct the appropriate JobExecution/StepExecution.
5. **Populate context data:** add keys and values with the exact types before activating the scope.
6. **Activate the scope:** use `StepScopeTestUtils`, `JobScopeTestUtils`, or the corresponding listener.
7. **Invoke via proxy:** do not obtain the target object by calling factory methods outside scope.
8. **Verify behavior:** confirm the bean receives the right parameters and executes the expected logic.
9. **Release resources:** close readers/writers or resources opened during the test.
10. **Add integration tests:** verify flow, transactions, repository persistence, and restarts as needed.

For readers/writers implementing `ItemStream`, test `open`, `read`/`write`, `update`, and `close` according to the real lifecycle. Do not only call a business method while ignoring resource management.

## 21. Points to Remember

- `@JobScope` binds a bean to a `JobExecution`; `@StepScope` binds a bean to a `StepExecution`.
- Scoped beans are normally injected via proxies and only resolve late-bound values when the corresponding scope is active.
- Use `spring-batch-test` for listeners and utilities supporting scope testing.
- `@SpringBatchTest` is convenient for job/step integration tests and enables scope test listeners.
- `StepScopeTestUtils` executes callbacks inside StepScope with a specific `StepExecution`.
- `JobScopeTestUtils` executes callbacks inside JobScope with a specific `JobExecution` when provided by the library version.
- `MetaDataInstanceFactory` builds test metadata; you must populate JobParameters and ExecutionContext with the exact keys/types yourself.
- `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener` can establish scopes for test methods.
- Distinguish JobParameters, Job ExecutionContext, and Step ExecutionContext so test data is placed in the right location.
- Isolated scoped-bean tests do not replace integration tests for flow, transactions, repository, and restart.
- `@StepScope` does not make every internal dependency thread-safe automatically; concurrency tests must examine the full dependency graph.
- Do not retain target objects of scoped beans after the execution scope has closed.

When testing jobs or steps with scoped components, always set up the proper execution context before accessing the bean. Use utilities/listeners for isolated scope tests and `JobLauncherTestUtils` for integration tests. This approach verifies late binding, bean lifecycles, runtime parameters, and Spring Batch behavior in a test environment closely matching real job runs.
