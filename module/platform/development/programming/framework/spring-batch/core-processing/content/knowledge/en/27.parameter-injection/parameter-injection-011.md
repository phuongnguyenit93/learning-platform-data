# Testing Parameter Binding

In Spring Batch, many beans receive their input data only when the job or step starts running. These values are typically injected with SpEL from `JobParameters`, `JobExecutionContext`, or `StepExecutionContext` via `@JobScope` and `@StepScope`. This mechanism is called late binding.

When testing, merely creating the Spring `ApplicationContext` is not enough to prove parameter binding works. Tests must supply the right execution context, activate the corresponding scope, and access the bean through its scoped proxy. For integration testing, launch the job or step with real `JobParameters` to verify the full path from launcher to bean.

## 1. Parameter Binding in Spring Batch

Spring Batch has three data sources commonly used in SpEL expressions:

| Source | SpEL Example | Scope |
|---|---|---|
| `JobParameters` | `#{jobParameters['inputFile']}` | Parameters supplied when launching the job. |
| Job `ExecutionContext` | `#{jobExecutionContext['batchReference']}` | Runtime metadata belonging to one `JobExecution`. |
| Step `ExecutionContext` | `#{stepExecutionContext['minId']}` | Runtime metadata belonging to one `StepExecution`. |

Example of a reader receiving file/business date from `JobParameters` and an ID range from Step `ExecutionContext`:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate " +
                    "and order_id between :minId and :maxId")
            .parameterValues(Map.of(
                    "businessDate", businessDate,
                    "minId", minId,
                    "maxId", maxId))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"), rs.getBigDecimal("amount")))
            .pageSize(200)
            .saveState(true)
            .build();
}
```

`@StepScope` lets Spring create the target bean when a `StepExecution` is active. Only then are SpEL expressions resolved with the current execution's data.

## 2. Distinguishing JobParameters from ExecutionContext in Tests

A common mistake is placing values in the wrong source. `JobParameters` are the inputs of a job launch; `ExecutionContext` stores state produced during execution.

| Data | Where to Set in Tests |
|---|---|
| File path passed by scheduler | `JobParameters` |
| Business date of the run | `JobParameters` |
| Batch code written by prior step for next step | `JobExecution.getExecutionContext()` |
| Min/max ID of a partition | `StepExecution.getExecutionContext()` |
| Reader checkpoint | Step `ExecutionContext` via `ItemStream` lifecycle |

Example creating test metadata with all three sources:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "src/test/resources/orders.csv", true)
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putLong("minId", 100L);
stepExecution.getExecutionContext().putLong("maxId", 199L);

stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "TEST-BATCH-01");
```

Then:

- `#{jobParameters['businessDate']}` reads from `JobParameters` of the `JobExecution` linked to `StepExecution`.
- `#{stepExecutionContext['minId']}` reads from Step `ExecutionContext`.
- `#{jobExecutionContext['batchReference']}` reads from Job `ExecutionContext`.

Tests must place values into the right context before the scoped target bean is created.

## 3. Why Is @StepScope or @JobScope Needed?

Default singleton beans are created when the `ApplicationContext` starts up. At that time, Spring Batch does not yet have a specific `JobExecution` or `StepExecution` to resolve runtime parameters.

`@StepScope` and `@JobScope` create proxies to defer creating target beans until the corresponding scope is active.

| Scope | Bound To | Commonly Bindable Data |
|---|---|---|
| Singleton | `ApplicationContext` | Static configuration, dependencies independent of execution. |
| `@JobScope` | One `JobExecution` | `JobParameters`, Job `ExecutionContext`. |
| `@StepScope` | One `StepExecution` | `JobParameters`, Job `ExecutionContext`, Step `ExecutionContext`. |

A `@JobScope` bean has no single specific step to read Step `ExecutionContext`. If values vary per step or partition, use `@StepScope`.

When testing, access the bean via its proxy inside the scope. Do not call the `@Bean` factory method directly to obtain the target object outside the scope and assume late binding was tested.

## 4. Preparing Testing Dependencies

Add `spring-batch-test` with a version compatible with your Spring Batch version:

```groovy
dependencies {
    testImplementation("org.springframework.batch:spring-batch-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If the project uses Spring Boot dependency management or the Spring Batch BOM, let versions be managed centrally to avoid mismatches between `spring-batch-core` and `spring-batch-test`.

Common utilities:

- `MetaDataInstanceFactory`: creates `JobExecution` and `StepExecution` for tests.
- `StepScopeTestUtils`: runs a callback inside `StepScope` with a given `StepExecution`.
- `JobScopeTestUtils`: runs a callback inside `JobScope` with a given `JobExecution`.
- `StepScopeTestExecutionListener`: activates `StepScope` for test methods.
- `JobScopeTestExecutionListener`: activates `JobScope` for test methods.
- `@SpringBatchTest`: registers Spring Batch test utilities, including scope listeners and launcher/repository utilities.
- `JobLauncherTestUtils`: runs a job or step in integration tests.

Exact package names, overloads, and configuration details depend on version. Use APIs from the exact `spring-batch-test` version declared in your project.

Besides the test dependency, `ApplicationContext` needs Spring Batch configuration to register scopes. This is usually provided by `@EnableBatchProcessing`, `DefaultBatchConfiguration`, or Spring Boot auto-configuration. `@SpringBatchTest` supports testing; it does not replace the application's batch infrastructure and datasource configuration.

## 5. Testing StepScope Beans with StepScopeTestUtils

`StepScopeTestUtils.doInStepScope` fits when you only want to test a single scoped reader, processor, writer, or component without running the entire job.

Suppose you have an options bean receiving parameters:

```java
public class OrderImportOptions {

    private final String inputFile;
    private final String businessDate;

    public OrderImportOptions(String inputFile, String businessDate) {
        this.inputFile = inputFile;
        this.businessDate = businessDate;
    }

    public String inputFile() {
        return inputFile;
    }

    public String businessDate() {
        return businessDate;
    }
}
```

Declaring the scoped bean:

```java
@Configuration
public class OrderOptionsConfiguration {

    @Bean
    @StepScope
    OrderImportOptions orderImportOptions(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        return new OrderImportOptions(inputFile, businessDate);
    }
}
```

Test:

```java
@SpringJUnitConfig({BatchInfrastructureConfiguration.class,
        OrderOptionsConfiguration.class})
class OrderImportOptionsTest {

    @Autowired
    private OrderImportOptions orderImportOptions;

    @Test
    void bindsValuesFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            assertThat(orderImportOptions.inputFile())
                    .isEqualTo("src/test/resources/orders.csv");
            assertThat(orderImportOptions.businessDate())
                    .isEqualTo("2026-11-15");
            return null;
        });
    }
}
```

`BatchInfrastructureConfiguration` in this example represents your application's actual batch configuration, which registers `StepScope`. It can be replaced by `@EnableBatchProcessing` or the Spring Boot configuration in use.

The key point is that the callback executes inside `StepScope`. When the callback finishes, the scope closes. Do not call `orderImportOptions.inputFile()` before or after the callback.

## 6. Creating StepExecution with JobParameters

`MetaDataInstanceFactory` can create a `StepExecution` linked to a `JobExecution` and `JobParameters`. This is a simple way to test late binding without starting `JobLauncher`.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "orders.csv", true)
        .addLong("tenantId", 42L, true)
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);
```

In a bean with numeric binding:

```java
@Bean
@StepScope
TenantOptions tenantOptions(
        @Value("#{jobParameters['tenantId']}") Long tenantId) {
    return new TenantOptions(tenantId);
}
```

The test can confirm the value converts to the expected Java type. If the parameter was stored with an incompatible type or the key is missing, resolution/conversion may fail when the scoped target is created.

For dates, complex identifiers, or values with custom formats, you can bind as a `String` and parse/validate inside the factory method or a dedicated component. This makes formatting errors clear and easy to test.

## 7. Testing Step ExecutionContext Binding

A step-scoped bean often receives data prepared by a partitioner or an earlier step. Tests must write keys into `stepExecution.getExecutionContext()`.

Example bean:

```java
@Bean
@StepScope
CustomerRangeOptions customerRangeOptions(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new CustomerRangeOptions(minId, maxId);
}
```

Test:

```java
@Test
void bindsPartitionRangeFromStepExecutionContext() throws Exception {
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    stepExecution.getExecutionContext().putLong("minId", 100L);
    stepExecution.getExecutionContext().putLong("maxId", 199L);

    StepScopeTestUtils.doInStepScope(stepExecution, () -> {
        assertThat(customerRangeOptions.minId()).isEqualTo(100L);
        assertThat(customerRangeOptions.maxId()).isEqualTo(199L);
        return null;
    });
}
```

Do not put `minId` and `maxId` into `JobParameters` if the bean reads `stepExecutionContext`. Even with the same key name, the two data sources are distinct areas.

## 8. Testing Job ExecutionContext Binding

Job `ExecutionContext` often holds metadata written by a prior step and promoted for later steps to use. Beans can read this value via `@JobScope` or `@StepScope`.

Example:

```java
@Bean
@JobScope
BatchRunOptions batchRunOptions(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['batchReference']}") String batchReference) {

    return new BatchRunOptions(businessDate, batchReference);
}
```

Test:

```java
@Test
void bindsJobExecutionContextValue() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution jobExecution = MetaDataInstanceFactory
            .createJobExecution(parameters);
    jobExecution.getExecutionContext()
            .putString("batchReference", "BATCH-TEST-01");

    JobScopeTestUtils.doInJobScope(jobExecution, () -> {
        assertThat(batchRunOptions.businessDate())
                .isEqualTo("2026-11-15");
        assertThat(batchRunOptions.batchReference())
                .isEqualTo("BATCH-TEST-01");
        return null;
    });
}
```

The test must put `batchReference` into Job `ExecutionContext` before accessing the bean. If the value is produced by a prior step, test the promotion listener separately or run an integration test to prove the value actually transfers from Step `ExecutionContext` to Job `ExecutionContext`.

## 9. Testing Scopes with TestExecutionListener

If multiple test methods in a class need an active scope, you can use `StepScopeTestExecutionListener` or `JobScopeTestExecutionListener`. The listener sets up the execution context for each test method and closes the scope after the test finishes.

StepScope example:

```java
@SpringJUnitConfig({BatchInfrastructureConfiguration.class,
        OrderOptionsConfiguration.class})
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class OrderOptionsListenerTest {

    @Autowired
    private OrderImportOptions orderImportOptions;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();
        return MetaDataInstanceFactory.createStepExecution(parameters);
    }

    @Test
    void resolvesParametersInsideStepScope() {
        assertThat(orderImportOptions.inputFile())
                .isEqualTo("src/test/resources/orders.csv");
    }
}
```

The listener can retrieve the `StepExecution` from a `getStepExecution()` factory method on the test class. If no factory method is provided, the listener uses default metadata. Method conventions and registration details should be checked against your Spring Batch Test version.

Similarly, `JobScopeTestExecutionListener` can be used with a `getJobExecution()` method to provide a `JobExecution` with custom `JobParameters` and Job `ExecutionContext`.

When using `@SpringBatchTest`, scope-supporting listeners are usually already registered. Avoid registering duplicate listeners unnecessarily; if declaring `@TestExecutionListeners` manually, consider `MERGE_WITH_DEFAULTS` to retain Spring Test's other default listeners.

## 10. Testing with @SpringBatchTest and JobLauncherTestUtils

Testing a scoped bean in isolation only proves late binding inside a simulated scope. To verify the job truly receives parameters from the launcher, creates scopes, runs steps, and persists metadata accurately, run integration tests.

```java
@SpringBootTest
@SpringBatchTest
class OrderImportJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void launchesJobWithRuntimeParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getJobParameters().getString("businessDate"))
                .isEqualTo("2026-11-15");
    }
}
```

This test assumes the `ApplicationContext` has one job configured for `JobLauncherTestUtils`, the datasource and Spring Batch schema are ready, and the input file is at the specified location. If the context has multiple jobs, explicitly configure the job under test per your `JobLauncherTestUtils` version's API.

`@SpringBatchTest` supplies testing utilities, but does not automatically create business data or database schemas. Tests must prepare those dependencies.

## 11. Testing a Single Step with JobLauncherTestUtils

When you do not need to run the whole job, launch a single step with `launchStep`:

```java
@Test
void launchesImportStepWithParameters() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "src/test/resources/orders.csv", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "importOrdersStep", parameters);

    StepExecution stepExecution = execution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName().equals("importOrdersStep"))
            .findFirst()
            .orElseThrow();

    assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

`launchStep` is useful for focusing on one step's reader/processor/writer and parameter binding. However, it does not test the entire job flow, data produced by an earlier step, or listener promotion across steps. For those cases, run the full job.

## 12. Testing Data Promoted from Step ExecutionContext

Suppose a preparation step writes `validatedInputFile` to Step `ExecutionContext` and `ExecutionContextPromotionListener` moves this key to Job `ExecutionContext`.

A unit test of the listener alone can create a `StepExecution`, set the key, and invoke the listener per step lifecycle. However, a more reliable way to confirm all wiring works is a two-step integration test:

```text
prepareFileStep
   |
   +-- Step ExecutionContext:
   |      validatedInputFile = /test/orders.csv
   |
   v
ExecutionContextPromotionListener
   |
   v
Job ExecutionContext:
   validatedInputFile = /test/orders.csv
   |
   v
importFileStep reads #{jobExecutionContext['validatedInputFile']}
```

Bean in the subsequent step:

```java
@Bean
@StepScope
ValidatedFileOptions validatedFileOptions(
        @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {
    return new ValidatedFileOptions(inputFile);
}
```

In the integration test, launch the job with test data and verify the subsequent step receives the exact file path. If the test only places the value directly into Job `ExecutionContext`, it verifies binding but not that the promotion listener works.

## 13. Testing Missing or Malformed Parameters

Parameters are not always passed completely. Tests should confirm the application reacts clearly when keys are missing or values are invalid.

Example validation in a factory method:

```java
@Bean
@StepScope
OrderImportOptions orderImportOptions(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    LocalDate parsedDate;
    try {
        parsedDate = LocalDate.parse(businessDate);
    } catch (DateTimeParseException exception) {
        throw new IllegalArgumentException(
                "businessDate must use ISO-8601 date format", exception);
    }

    return new OrderImportOptions(inputFile, parsedDate.toString());
}
```

Cases to test:

- Omitting `inputFile`.
- `inputFile` as an empty or whitespace-only string.
- Omitting `businessDate`.
- Malformed date.
- `tenantId` unconvertible to the injected type.
- Missing or misspelled key in `ExecutionContext`.

For required values, report clear errors when the scoped target is created or during an input validation step. Do not silently fall back to a default if doing so could cause the job to process the wrong data.

## 14. Testing Default and Optional Values

Some parameters may be optional. Define explicit default behavior and test both parameter-present and parameter-absent cases.

Example using the SpEL Elvis operator:

```java
@Bean
@StepScope
ImportOptions importOptions(
        @Value("#{jobParameters['delimiter'] ?: ','}") String delimiter) {
    return new ImportOptions(delimiter);
}
```

Tests should verify:

- When `delimiter` is present, the bean receives the exact passed value.
- When `delimiter` is absent, the bean uses the default comma.
- Unsupported values are rejected if input format forbids them.

Only use defaults for genuinely optional parameters. For required file paths, business dates, or tenant IDs, defaults can make the job run on the wrong data.

## 15. Testing JobParameters Data Types

`JobParameters` can contain types supported by Spring Batch, such as `String`, `Long`, `Double`, `Date`, and temporal types in supported versions. Beans can bind directly to compatible types or accept `String` and convert.

Example:

```java
@Bean
@StepScope
TenantOptions tenantOptions(
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['dryRun']}") Boolean dryRun) {

    return new TenantOptions(tenantId, dryRun);
}
```

Test:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("tenantId", 42L, true)
        .addString("dryRun", "true", false)
        .toJobParameters();
```

In this example, `dryRun` is stored as a `String`; binding to `Boolean` depends on the conversion service and actual configuration. To avoid ambiguity, store parameters using their matching supported types and test conversion on the exact version in use.

Do not assume two parameters with identical string representations share the same type. Tests should verify both value and type after binding.

## 16. Identifying and Non-Identifying Parameters

`JobParameters` can contain identifying and non-identifying values. Identifying parameters participate in identifying the `JobInstance`; non-identifying parameters do not alter identity.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders.csv", true)
        .addString("requestedBy", "integration-test", false)
        .toJobParameters();
```

When testing parameter binding, verify:

- Beans receive the right identifying values.
- Beans receive the right non-identifying values if they use them.
- Two runs with the same identifying parameters belong to the same `JobInstance` per repository semantics.
- Changing an identifying parameter creates a different `JobInstance`.
- On restart, identifying values remain unchanged.

Do not add a new timestamp or UUID as an identifying parameter in restart tests if the goal is resuming the same `JobInstance`. However, non-identifying parameters should also not be altered arbitrarily if they affect the bean's business logic.

## 17. Testing Multiple Executions with the Same Scoped Proxy

A scoped proxy can be injected into a test class. When each scope is activated with a different execution, the target bean must be created/resolved for the corresponding context.

Example:

```java
@Test
void sameProxyResolvesDifferentStepParameters() throws Exception {
    StepExecution first = MetaDataInstanceFactory.createStepExecution(
            new JobParametersBuilder()
                    .addString("businessDate", "2026-11-15", true)
                    .toJobParameters());

    StepExecution second = MetaDataInstanceFactory.createStepExecution(
            new JobParametersBuilder()
                    .addString("businessDate", "2026-11-16", true)
                    .toJobParameters());

    String firstDate = StepScopeTestUtils.doInStepScope(first,
            () -> orderImportOptions.businessDate());

    String secondDate = StepScopeTestUtils.doInStepScope(second,
            () -> orderImportOptions.businessDate());

    assertThat(firstDate).isEqualTo("2026-11-15");
    assertThat(secondDate).isEqualTo("2026-11-16");
}
```

This test catches beans retaining stale values outside scope or accidentally reusing state from an earlier execution. Do not retain references to target objects from closed scopes; access them via the proxy inside each execution's callback.

## 18. Testing Parameter Binding in Partitioning

In partitioning, each worker has its own `StepExecution` and Step `ExecutionContext`. The same `@StepScope` bean definition can receive different `minId` and `maxId` per partition.

Example testing two ranges:

```java
StepExecution north = MetaDataInstanceFactory.createStepExecution();
north.getExecutionContext().putString("region", "NORTH");
north.getExecutionContext().putLong("minId", 1L);
north.getExecutionContext().putLong("maxId", 100L);

StepExecution south = MetaDataInstanceFactory.createStepExecution();
south.getExecutionContext().putString("region", "SOUTH");
south.getExecutionContext().putLong("minId", 101L);
south.getExecutionContext().putLong("maxId", 200L);
```

Run the bean inside each scope and assert the corresponding region/range. This tests the worker's parameter binding. To test that the partitioner creates the right contexts, test the partitioner separately; to test the manager coordinating workers, write an integration test for the partitioned step.

`@StepScope` creates targets per `StepExecution`, but does not automatically make inner singleton dependencies thread-safe. Sequential binding tests do not replace concurrency tests.

## 19. Testing Restarts and Parameter Binding

Restarts create a new `JobExecution` for the same `JobInstance`. Scoped beans are created in the new execution's context, so verify they receive the right parameters and restored `ExecutionContext`.

A restart integration test typically follows these steps:

1. Launch the job with fixed identifying parameters.
2. Trigger a controlled step failure after checkpoints have been saved.
3. Verify the first `JobExecution` is `FAILED`.
4. Fix the failure cause in the test.
5. Restart the same `JobInstance` using the original identifying parameters or `JobOperator`.
6. Verify a new `JobExecution` is created.
7. Verify scoped beans receive the right `JobParameters` and required context.
8. Verify readers/writers restore checkpoints and results are not duplicated.

Isolated scope tests only prove value resolution within one simulated execution. They do not prove `JobRepository` saves/restores context properly or that step flows restart cleanly. Those require integration tests.

## 20. Checking Scope and SpEL Errors

Common errors during parameter binding:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ScopeNotActiveException` | Accessing scoped bean outside `JobScope`/`StepScope`. | Use scope utilities/listeners or launch the job/step. |
| Cannot resolve `jobParameters` | No active `JobExecution` or bean lacks proper scope. | Use `@StepScope`/`@JobScope` and establish execution context. |
| SpEL returns `null` | Wrong key or value not yet placed in context. | Check exact key name and context source. |
| Value converts to wrong type | `JobParameter` type incompatible with method argument type. | Use explicit types or parse/validate `String`. |
| Bean retains old value across two tests | Target scoped bean reference retained or scope not closed properly. | Access via proxy inside each scope and let utilities manage lifecycle. |
| Step context misses job context value | Key placed in wrong scope or missing promotion from prior step. | Set `JobExecutionContext` properly or test promotion flow. |
| `@JobScope` fails to resolve step key | Job scope has no single specific `StepExecution`. | Use `@StepScope` when Step `ExecutionContext` is needed. |
| Isolated test passes but launching job fails | Test utility does not verify full wiring, flow, or repository. | Add integration test with `JobLauncherTestUtils`. |
| Test fails due to stale metadata | Shared `JobRepository` across tests or existing `JobInstance`. | Use isolated test parameters and clean metadata intentionally. |

When investigating, determine whether the error occurs during `ApplicationContext` creation, scope activation, or individual expression resolution. These three phases usually point to different root causes.

## 21. Points to Remember

- Parameter binding typically uses SpEL to read data from `JobParameters`, Job `ExecutionContext`, and Step `ExecutionContext`.
- `@StepScope` fits when a bean needs per-step/per-partition parameters; `@JobScope` fits data shared across a `JobExecution`.
- Scoped beans are accessed through proxies; targets and late-bound values are only resolved when the corresponding scope is active.
- `MetaDataInstanceFactory` creates test `JobExecution`/`StepExecution` instances; place parameters and contexts in the right source before invoking beans.
- `StepScopeTestUtils` and `JobScopeTestUtils` execute callbacks inside their respective scopes.
- `StepScopeTestExecutionListener` and `JobScopeTestExecutionListener` can activate scopes for test methods.
- `@SpringBatchTest` and `JobLauncherTestUtils` are suited for verifying jobs/steps actually launched with `JobParameters`.
- Placing a value in Step `ExecutionContext` does not make it automatically appear in Job `ExecutionContext`; promotion or an explicit transfer mechanism is needed.
- Isolated bean tests do not replace integration tests for flow, transactions, metadata promotion, and restarts.
- Test valid, missing, malformed, wrong-type, and default parameters.
- Keep identifying parameters stable when testing restarts of the same `JobInstance`.
- Partition tests must create separate `StepExecution` instances with separate contexts per worker.
- Do not retain scoped bean target objects after the scope closes and do not assume scopes automatically guarantee thread safety for shared dependencies.

Testing parameter binding must simulate the actual execution lifecycle the bean depends on. Use scope utilities or listeners when testing a single component, and use `JobLauncherTestUtils` when verifying the entire job flow. When `JobParameters` and `ExecutionContext` are placed in the right locations, tests catch key typos, type mismatches, missing context, and broken late binding early before batches run in production.
