# @Value from jobParameters

In Spring Batch, JobParameters are the input values passed when launching a Job. A Step may need to read a file name, business date, tenant ID, record limit, or processing mode. These values can be retrieved using a SpEL expression in the `@Value` annotation, for example `@Value("#{jobParameters['inputFile']}")`.

Because JobParameters are only available when the JobExecution starts, a bean that receives these values needs to be created within the proper execution scope. The standard approach is to declare the bean as `@StepScope`. Spring creates a scoped proxy when the application context starts up and only instantiates the target bean when the Step begins, at which point JobParameters are already available.

## 1. What are JobParameters?

`JobParameters` is an immutable set of input parameters bound to a JobInstance/JobExecution. They specify which data a run should process and under what conditions.

For example, an order import Job might receive:

| Parameter | Example | Purpose |
|---|---|---|
| `inputFile` | `/data/in/orders.csv` | Input file to read. |
| `businessDate` | `2026-11-15` | Business date of the batch. |
| `tenantId` | `42` | Customer/tenant scope to process. |
| `maxRows` | `10000` | Row limit for the run. |
| `importMode` | `INCREMENTAL` | Import mode. |

Parameters are passed into the Job upon launch, typically via `JobParametersBuilder`. For example:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addLong("tenantId", 42L, true)
        .addLong("maxRows", 10_000L, false)
        .addString("importMode", "INCREMENTAL", true)
        .toJobParameters();
```

A parameter marked `true` is an identifying parameter, participating in identifying the JobInstance. A parameter marked `false` does not participate in identification. The choice of identifying parameters affects restarts: the same Job name and the same identifying parameters will point to the same JobInstance; changing an identifying parameter may create a new JobInstance.

## 2. Reading JobParameters with @Value and SpEL

Spring Batch provides contextual variables in SpEL. To read a JobParameter by name, use the expression:

```java
@Value("#{jobParameters['inputFile']}")
```

Where:

- `#{...}` is the SpEL expression syntax.
- `jobParameters` is the map containing the parameters of the current JobExecution.
- `['inputFile']` retrieves the value by the key `inputFile`.

Example of reading the business date:

```java
@Value("#{jobParameters['businessDate']}") String businessDate
```

The key name must match the name used when creating the JobParameters. If the key does not exist, the expression may return `null`; in that case, the application needs to determine whether the parameter is required or optional and handle it appropriately.

## 3. Why is @StepScope Needed?

Regular Spring beans have singleton scope and are initialized when the application context is created. At that time, there is no specific JobExecution yet, so variables such as `jobParameters`, `stepExecutionContext`, or `jobExecutionContext` do not yet have values for a run.

`@StepScope` defers target bean creation until the Step starts. The bean is bound to a StepExecution and can access the values belonging to that run.

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

When the Step starts, Spring creates the reader with the exact `inputFile` of the current JobExecution. If another Job runs concurrently with a different file, each StepExecution has its target bean initialized in its respective scope.

Do not omit `@StepScope` from a bean that has `@Value` referencing JobParameters and expect Spring to know which run's parameters to retrieve. A singleton bean is not bound to a specific JobExecution.

## 4. Reading Multiple JobParameters in the Same Bean

A Step-scoped bean can receive multiple parameters via its constructor or `@Bean` method parameters:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The example takes `businessDate` and `tenantId` to illustrate injecting multiple parameters; if the reader does not need to use those values, remove them from the bean signature. Do not keep unused parameters just to make the configuration longer.

Values can be injected via fields or constructors in a `@Component @StepScope` class. Constructor injection typically makes dependencies explicit and easier to test.

## 5. Type Conversion

JobParameters can contain data types supported by Spring Batch. When using `@Value`, the value goes through Spring's conversion mechanism to be assigned to the target type if an appropriate converter is available.

Example of an integer parameter:

```java
@Bean
@StepScope
public Tasklet processTenantTasklet(
        @Value("#{jobParameters['tenantId']}") Long tenantId) {

    return (contribution, chunkContext) -> {
        // Use tenantId to limit the processing scope.
        return RepeatStatus.FINISHED;
    };
}
```

For business dates, a well-controlled approach is to pass an ISO-8601 string and parse it explicitly:

```java
import java.time.LocalDate;

@Bean
@StepScope
public Tasklet dailyTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        // Process data for the given date.
        return RepeatStatus.FINISHED;
    };
}
```

If you want to inject a `LocalDate` type directly, ensure the application's ConversionService has a converter matching the JobParameter representation. Do not assume all versions of Spring Batch/Spring automatically convert all date/time types using the same rules.

For numeric parameters, use a type corresponding to the JobParameter type created. If a `Long` is passed but an `Integer` is injected, a valid conversion and overflow control are required. The clearest approach is to keep types consistent between where JobParameters are created and where they are injected.

## 6. Required and Optional Parameters

If a parameter is required, validate it explicitly when the target bean is initialized. For example:

```java
@Bean
@StepScope
public Tasklet importTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter 'inputFile' is missing");
    }

    return (contribution, chunkContext) -> {
        // Perform the import.
        return RepeatStatus.FINISHED;
    };
}
```

Validating in the bean factory ensures configuration errors are caught when the Step initializes, with a clear message. You can validate earlier in a validation Step if you want the Job to fail with a specific business status and audit record before creating the reader.

For optional parameters, SpEL supports the Elvis operator `?:` to use a default value when the left-hand expression is null:

```java
@Value("#{jobParameters['maxRows'] ?: 1000}") Integer maxRows
```

The example above uses 1000 when `maxRows` is not passed. Use a default only when that value is genuinely a business policy. Do not silently set defaults for required parameters such as source file, tenant, or data cutoff date, as this may cause the Job to process the wrong data.

String default values can also be used:

```java
@Value("#{jobParameters['importMode'] ?: 'INCREMENTAL'}") String importMode
```

Default values must align with the Job's identification and restart rules. If the import mode changes the meaning of the unit of work, pass it as an identifying parameter instead of silently using a different default across runs.

## 7. Using JobParameters in a Processor

A Processor may need parameters to apply rules by tenant, business date, or processing mode. In that case, declare the Processor as Step-scoped:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class TenantOrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    private final Long tenantId;

    public TenantOrderProcessor(
            @Value("#{jobParameters['tenantId']}") Long tenantId) {
        this.tenantId = tenantId;
    }

    @Override
    public ProcessedOrder process(Order order) {
        if (!tenantId.equals(order.tenantId())) {
            return null;
        }
        return ProcessedOrder.from(order);
    }
}
```

In the example, the Processor only keeps items belonging to the requested tenant; items from other tenants are filtered out because the method returns `null`. If a different tenant is a data error rather than a filter condition, throw a business exception and configure an appropriate skip/fail policy.

`@StepScope` is also useful when the same Job runs concurrently for multiple tenants. Each StepExecution receives its own `tenantId` value, rather than storing one run's parameter in a field of a shared singleton Processor.

## 8. Using JobParameters in a Writer or Tasklet

A Writer may need parameters to write to a target table by data period. A Tasklet may need parameters to invoke a procedure or generate an output file.

Example of a Tasklet receiving a business date:

```java
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public Tasklet closeBusinessDayTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        // Call the period-closing service for date.
        return RepeatStatus.FINISHED;
    };
}
```

Do not inject JobParameters directly into a singleton Writer/Tasklet if that bean is shared across multiple executions. Use the appropriate scope so each run receives the right value.

## 9. Distinguishing jobParameters from ExecutionContexts

SpEL in Spring Batch can read multiple types of contextual data. Choose the right source:

| Expression | Data Source | When to Use |
|---|---|---|
| `#{jobParameters['inputFile']}` | JobParameters | Input values passed when launching the Job. |
| `#{jobExecutionContext['batchId']}` | Job ExecutionContext | Small values shared across Steps within the same JobExecution. |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext | Checkpoints or data ranges specific to a Step/partition. |
| `#{stepExecution.stepName}` | StepExecution | Metadata of the current Step. |
| `#{jobExecution.id}` | JobExecution | ID of the current run, often used for tracing/auditing. |

Example of a partition reader receiving an ID range from the Step ExecutionContext:

```java
@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {
    // Create a reader querying minId..maxId.
}
```

Here `minId` and `maxId` are generated by a Partitioner, not passed directly as launch parameters. If mistakenly retrieved from `jobParameters`, the worker may not receive its partition-specific range.

JobParameters should hold inputs and caller choices. ExecutionContext should hold execution state or intermediate data saved for a Step to resume/share.

## 10. JobParameters Are Immutable and Affect Restart

JobParameters are bound to a JobInstance/JobExecution and should not be treated as a mutable map to modify while the Job is running. If you need to store computed results or intermediate state, use ExecutionContext or a business database.

For example, the Job is launched with:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
```

If the Job fails and needs to be restarted, reuse the same identifying parameters. That way, the Step-scoped bean will be created for the new JobExecution while receiving the same input values, ensuring the restart processes the original file and business date.

If `businessDate` or `inputFile` is changed in the next invocation and they are identifying parameters, Spring Batch creates a new JobInstance. This is a new logical run, not a restart of the old instance.

Do not use `@Value` to read a newly generated `run.id` each time if the goal is to resume an old JobInstance. `RunIdIncrementer` may create a new identifying parameter and therefore create a new JobInstance.

## 11. Complete Job Configuration Example

The following example combines JobParameters, a Step-scoped Reader, and a chunk Step in Spring Batch 5 and later:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportJobConfig {

    @Bean
    @StepScope
    public FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            ItemProcessor<Order, ProcessedOrder> orderProcessor,
            ItemWriter<ProcessedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, ProcessedOrder>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

In the configuration above, Spring injects a scoped proxy of `orderReader` into the Step. When the Step executes, the proxy retrieves the target reader for the current StepExecution with `inputFile` from JobParameters. `Order`, `ProcessedOrder`, Processor, and Writer are application types declared elsewhere.

When launching:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.csv", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

`inputFile` is an identifying parameter in this example. When restarting the same JobInstance, reuse this exact value.

## 12. Testing @StepScope Beans

A Step-scoped bean cannot have its target instantiated normally outside a Step because the contextual variables do not exist yet. When unit tests need to verify late binding, `StepScopeTestUtils` can be used to open a simulated Step scope with a specific `StepExecution` and JobParameters.

Example of a small settings class:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class ImportSettings {

    private final String inputFile;

    public ImportSettings(
            @Value("#{jobParameters['inputFile']}") String inputFile) {
        this.inputFile = inputFile;
    }

    public String inputFile() {
        return inputFile;
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ImportSettingsTest {

    @Autowired
    private ImportSettings importSettings;

    @Test
    void injectsInputFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "/tmp/orders.csv")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        String inputFile = StepScopeTestUtils.doInStepScope(
                stepExecution,
                importSettings::inputFile);

        assertEquals("/tmp/orders.csv", inputFile);
    }
}
```

The test context needs Spring Batch test support and component scanning or a bean definition for `ImportSettings`. `StepScopeTestUtils.doInStepScope()` opens the scope while the callback executes, so `jobParameters` has a value. In addition to this unit test, an integration test with `@SpringBatchTest` and `JobLauncherTestUtils` can verify that the actual Job receives the right parameters upon launch.

## 13. Common Errors When Using @Value from jobParameters

| Error | Cause | How to Fix |
|---|---|---|
| `jobParameters` does not exist when creating bean | A singleton bean is initialized outside Step scope. | Place `@StepScope` on the bean that needs late binding. |
| Injected value is `null` | Wrong key name or caller did not pass the parameter. | Check JobParameters and validate required parameters. |
| Cannot convert type | JobParameter type and target type are incompatible or converter is missing. | Align types; parse explicitly or register a converter. |
| Changing parameters on restart | Creates a new JobInstance if the parameter is identifying. | Keep identifying parameters unchanged when restarting. |
| Using JobParameters to store progress | Input parameters are not mutable checkpoints. | Use Step/Job ExecutionContext or a database. |
| Using mutable fields in a singleton to store parameters | Multiple concurrent JobExecutions can overwrite data. | Use StepScope or JobScope as appropriate. |
| Using defaults for required parameters | The Job may process the wrong source or data period. | Validate and fail with a clear error when parameters are missing. |
| Confusing JobParameters with StepExecutionContext | Partition/checkpoint values are not in JobParameters. | Use the right SpEL variable according to the data source. |
| Putting secrets into JobParameters | Metadata and logs may store/display parameters. | Use a secret manager or dedicated security configuration. |

## Conclusion

`@Value("#{jobParameters['...']}")` allows injecting Job input parameters into a Reader, Processor, Writer, or Tasklet. Because JobParameters only exist for a single execution, beans needing late binding should be declared `@StepScope` (or another appropriate scope) so the target bean is created when the Step starts. Keep parameter types consistent, validate required values, use defaults only when business-meaningful, and keep identifying parameters unchanged on restart. Distinguishing JobParameters from Job/Step ExecutionContext keeps configuration clear and preserves accurate checkpoints across executions.
