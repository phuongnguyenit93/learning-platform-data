# Key Names and Data Types

In Spring Batch, JobParameters are the set of named input parameters for a Job run. Each parameter has a key, a value, and a data type. When injecting parameters into a reader, processor, writer, or Tasklet, the key name in SpEL must match the created key; the value's data type also needs to be compatible with the Java type accepted by the bean.

Using clear key names and choosing appropriate data types makes Jobs easier to configure, test, operate, and restart. A key like `business.date` can represent the business date; `tenant.id` can be an integer; `input.file` can be a file path. Using inconsistent names or injecting the wrong type can prevent bean initialization, misparse data, or accidentally create a different JobInstance.

## 1. JobParameters Consist of Key, Value, and Type

Each JobParameter has three important parts:

- **Key:** the identifier name of the parameter, for example `input.file`.
- **Value:** the input value, for example `/data/orders.csv`.
- **Type:** the Java type of the value, such as `String`, `Long`, `Double`, or a type supported by the configured conversion/serialization mechanism.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/orders.csv", true)
        .addLong("tenant.id", 42L, true)
        .addString("business.date", "2026-11-15", true)
        .addString("requested.by", "scheduler", false)
        .toJobParameters();
```

The parameters above have keys and types as follows:

| Key | Example Value | Type | Identifying |
|---|---|---|---|
| `input.file` | `/data/orders.csv` | `String` | Yes |
| `tenant.id` | `42` | `Long` | Yes |
| `business.date` | `2026-11-15` | `String` | Yes |
| `requested.by` | `scheduler` | `String` | No |

The key is used to access the value in JobParameters or SpEL. The type determines how the value is stored, converted, and injected. The identifying flag determines whether the parameter participates in identifying the JobInstance.

## 2. Key Naming Rules

Key names should describe the business or technical meaning of the value. Operators looking at JobParameters should understand what a parameter is for without reading code.

Examples of meaningful names:

| Recommended | Avoid | Reason |
|---|---|---|
| `input.file` | `f1` | Clearly states this is the input file. |
| `business.date` | `date` | Distinguishes business date from system date or execution creation date. |
| `tenant.id` | `id` | Shows which entity the ID belongs to. |
| `source.system` | `source` | Explicitly states this is the source system. |
| `dry.run` | `flag` | Describes the toggle behavior. |
| `batch.sequence` | `n` | Indicates the batch sequence number. |
| `requested.by` | `user` | Clearly expresses the requester. |

### Use a Consistent Convention

A common convention is lowercase words separated by dots:

```text
input.file
input.encoding
business.date
business.time-zone
tenant.id
source.system
target.table
batch.sequence
dry.run
requested.by
```

You can also use camelCase if the project standardizes on it, such as `inputFile`, `businessDate`, `tenantId`. The important thing is to pick one convention and apply it consistently across JobParameters, SpEL, tests, and operational docs.

### Keys Are Case-Sensitive

Do not treat `input.file`, `input.File`, and `INPUT.FILE` as the same key. Use the exact same casing where parameters are created and where they are injected.

### Avoid Overly Generic or Ambiguous Keys

Keys like `id`, `type`, `date`, `mode` can cause confusion as a Job evolves. If a Job needs both the file creation date and the business date, use `file.created-at` and `business.date` instead of two keys both named `date` at different layers.

Do not reuse the same key for two different meanings just because they happen to share the same data type. A key is the Job's input contract; changing a key's meaning can cause old scheduler commands to pass the wrong data.

## 3. Accessing Keys with SpEL

In a Batch-scoped bean, JobParameters can be injected with the expression:

```java
@Value("#{jobParameters['input.file']}")
private String inputFile;
```

Or injected via a bean factory method parameter:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

`jobParameters['input.file']` looks up the exact key containing a dot. Bracket notation is especially useful for keys containing dots or characters unsuitable for property notation.

Do not write `jobParameters.input.file` to access the key `input.file`; SpEL may interpret that as nested property access. Use `jobParameters['input.file']` so the key is treated as a single string.

## 4. Why Beans Need StepScope or JobScope

JobParameters only have values when a specific JobExecution is created. If a singleton bean is initialized as soon as the application context starts, the run's JobParameters do not yet exist to be injected.

`@StepScope` creates the bean within StepExecution scope and allows evaluating SpEL when the Step starts. This is the usual choice for readers, processors, or writers that depend on a Step's parameters.

```java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['tenant.id']}") Long tenantId) {

    return input -> new Order(
            input.orderId(),
            tenantId,
            input.amount());
}
```

`@JobScope` creates the bean within JobExecution scope. It fits when a bean needs to share a Job-level parameter across multiple Steps. Consider concurrency and bean lifecycle; do not store mutable per-Step state in a Job-scoped singleton if multiple Steps/workers can access it concurrently.

Guidelines:

- Readers typically use `@StepScope` when depending on JobParameters or Step ExecutionContext.
- Processors/writers only need a scope when injecting dynamic parameters or per-execution state.
- Beans not depending on execution can remain singletons.
- Do not inject JobParameters into a singleton and expect it to automatically change per launch.

## 5. Common Data Types

The data type should reflect the true nature of the value. Do not store everything as a String if the application needs arithmetic or date comparisons.

| Data | Common Type | Example Key |
|---|---|---|
| Path, file name, source code | `String` | `input.file`, `source.system` |
| ID, count, sequence | `Long` | `tenant.id`, `batch.sequence` |
| Ratio or floating-point threshold | `Double` | `quality.threshold` |
| On/off flag | `Boolean` | `dry.run` |
| Business date | `LocalDate` or ISO date string | `business.date` |
| Absolute point in time | `Instant` or ISO-8601 string with offset | `requested.at` |
| Time zone | `ZoneId` or timezone ID string | `business.time-zone` |
| Small set of choices | Enum or `String` | `import.mode` |

Spring Batch 5 uses typed JobParameters. Common types have convenience methods on `JobParametersBuilder`; other types must be supported by the configured conversion service/`JobParametersConverter` to store and restore metadata. If using custom types, verify conversion to/from storage format and ensure restart compatibility.

## 6. Creating Parameters with JobParametersBuilder

Convenience methods make the type explicit:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/orders.csv", true)
        .addLong("tenant.id", 42L, true)
        .addDouble("quality.threshold", 0.98, false)
        .addString("import.mode", "FULL", true)
        .addString("requested.by", "scheduler", false)
        .toJobParameters();
```

The `identifying` parameter is the last argument in overloads that take an identifying flag:

- `true`: the value participates in identifying the JobInstance.
- `false`: the value does not participate in identifying the JobInstance.

In Spring Batch 5, you can create a typed JobParameter using the generic `addJobParameter` API:

```java
JobParameters parameters = new JobParametersBuilder()
        .addJobParameter(
                "dry.run",
                Boolean.TRUE,
                Boolean.class,
                false)
        .toJobParameters();
```

Using custom types requires conversion service support to convert values when metadata is persisted and read back. For common types, prefer convenience methods or types supported out of the box by the framework. Do not pass arbitrary objects into JobParameters without verifying serialization/conversion.

## 7. Injecting String, Long, and Boolean

Example of injecting simple types:

```java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['dry.run']}") Boolean dryRun) {

    return (contribution, chunkContext) -> {
        if (Boolean.TRUE.equals(dryRun)) {
            log.info("Dry run for tenant {} using {}", tenantId, inputFile);
            return RepeatStatus.FINISHED;
        }

        importService.importFile(inputFile, tenantId);
        return RepeatStatus.FINISHED;
    };
}
```

The target type must be compatible with the actual JobParameter type. If a parameter was created with `addLong`, inject into `Long` or a compatible type. If created with `addString`, do not assume strings will automatically convert to numeric types everywhere; configure conversion explicitly or parse with validation.

For Booleans, avoid string comparisons like `"true"` if the JobParameter is already typed as Boolean. Use `Boolean.TRUE.equals(dryRun)` to avoid a NullPointerException when the parameter may be absent.

## 8. Dates, Times, and Time Zones

Business dates usually do not need time or timezone. Use `LocalDate` or an ISO date string `yyyy-MM-dd` for clear representation:

```java
LocalDate businessDate = LocalDate.parse("2026-11-15");
```

If the Job needs an absolute point in time, use `Instant` or an ISO-8601 string with an offset, such as `2026-11-15T09:30:00+07:00`. If scheduling according to a business timezone is required, pass an additional `business.time-zone` such as `Asia/Ho_Chi_Minh`.

Example using String to preserve a clear format and parsing inside the bean:

```java
@Bean
@StepScope
Tasklet dailyTasklet(
        @Value("#{jobParameters['business.date']}") String dateValue,
        @Value("#{jobParameters['business.time-zone']}") String zoneValue) {

    LocalDate businessDate = LocalDate.parse(dateValue);
    ZoneId businessZone = ZoneId.of(zoneValue);

    return (contribution, chunkContext) -> {
        reportService.createDailyReport(businessDate, businessZone);
        return RepeatStatus.FINISHED;
    };
}
```

This snippet illustrates parsing when creating the StepScope bean; in real applications, validate parameters before performing side effects and translate `DateTimeParseException`/`ZoneRulesException` into an input error with a clear message.

Do not use `LocalDateTime` to represent an absolute instant if the timezone is unknown. The same LocalDateTime can correspond to different instants in different timezones. For data compared across systems, prefer Instant or an explicit offset.

## 9. Missing Keys, Null Values, and Defaults

Not every Job has all parameters required. Distinguish between:

- Required parameters: missing is a configuration/input error and the Job should fail fast.
- Optional parameters: can use a defined default value.
- Blankable parameters: must clarify whether empty differs from omitted.

You can use the Elvis operator in SpEL for simple defaults:

```java
@Value("#{jobParameters['import.mode'] ?: 'INCREMENTAL'}")
String importMode
```

However, do not use a default for a required parameter like `input.file`. If the file is missing, the Job should report a clear error rather than silently running with an incorrect default path.

Another approach is validating parameters in a validator/Tasklet at the start of the Job:

```java
public void validateRequiredParameters(JobParameters parameters) {
    String inputFile = parameters.getString("input.file");
    Long tenantId = parameters.getLong("tenant.id");

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("Missing JobParameter: input.file");
    }

    if (tenantId == null || tenantId <= 0) {
        throw new IllegalArgumentException("Invalid JobParameter: tenant.id");
    }
}
```

`JobParametersValidator` is the proper place to validate the Job-level parameter contract before Steps execute the main work:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return parameters -> {
        String inputFile = parameters.getString("input.file");
        Long tenantId = parameters.getLong("tenant.id");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "Parameter input.file is required");
        }

        if (tenantId == null || tenantId <= 0) {
            throw new JobParametersInvalidException(
                    "Parameter tenant.id must be positive");
        }
    };
}
```

Attach the validator to the Job builder or corresponding Job configuration to validate before Steps run. Validators should check value validity and not perform side effects like moving files or writing business data.

## 10. Identifying and Non-Identifying Parameters

Not all JobParameters play the same role in determining a JobInstance.

- **Identifying parameter:** participates in JobInstance identity alongside the Job name.
- **Non-identifying parameter:** stored in the JobExecution without changing JobInstance identity.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("business.date", "2026-11-15", true)
        .addLong("tenant.id", 42L, true)
        .addString("requested.by", "scheduler", false)
        .addString("notification.email", "ops@example.com", false)
        .toJobParameters();
```

The business date and tenant can identify a specific import run. The requester or notification address may simply be operational metadata and need not create a new JobInstance. The identifying decision should be based on business meaning, not merely whether a parameter changes.

### Changing Type Also Changes the Contract

If `tenant.id` was previously created as a `Long`, and a new version creates the same key as a `String`, the JobParameters no longer have the same data type. This can affect identity, conversion, metadata, and restarts. Keep types stable across Job versions.

Similarly, changing value normalization can create a different JobInstance: `"2026-11-15"` and `"15/11/2026"` are two different Strings even if they express the same date. Use a canonical format such as ISO-8601.

## 11. Reading JobParameters Directly in Code

Besides SpEL, JobParameters can be obtained from `StepExecution` or `JobExecution` when code has an execution context:

```java
public class ParameterAwareTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = contribution.getStepExecution();
        JobParameters parameters = stepExecution
                .getJobExecution()
                .getJobParameters();

        String inputFile = parameters.getString("input.file");
        Long tenantId = parameters.getLong("tenant.id");

        // Perform work based on the validated parameters.
        return RepeatStatus.FINISHED;
    }
}
```

This approach is useful when many parameters must be read or structured validation is needed. For beans created with `@StepScope`, SpEL is usually more concise. Do not access static/global state to retrieve the current Job's parameters; use the execution object passed by the framework.

## 12. Distinguishing JobParameters from ExecutionContext

Both objects often appear together when injecting data, but they serve different purposes:

| Characteristic | JobParameters | ExecutionContext |
|---|---|---|
| Role | Input to JobInstance/JobExecution | State of Job/Step during execution |
| Mutability | Immutable after the Job is created | Updatable during execution |
| Source | Scheduler, command line, launch API, or caller application | Reader, writer, Tasklet, listener, and framework |
| Example | `business.date`, `input.file`, `tenant.id` | `orders.reader.current.index`, `last.processed.id` |
| Restart | Preserves identity and inputs of the business run | Stores checkpoints to resume unfinished work |

Do not write continuously changing checkpoints into JobParameters. JobParameters describe inputs; ExecutionContext stores progress and recoverable state.

Step ExecutionContext can be injected with different SpEL from JobParameters:

```java
@Value("#{stepExecutionContext['minIdInclusive']}") Long minId
```

And Job ExecutionContext:

```java
@Value("#{jobExecutionContext['staging.batch.id']}") String stagingBatchId
```

These keys are not keys in JobParameters. Use the proper scope to avoid reading from the wrong data source.

## 13. Key Names in Reader, Processor, and Writer

A Job often has multiple components needing parameters. Define keys according to the Job's shared contract and only inject the keys each component needs.

Example:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['business.date']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, tenant_id, amount
                    FROM orders
                    WHERE tenant_id = ?
                      AND business_date = ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, tenantId);
                statement.setDate(2, Date.valueOf(businessDate));
            })
            .rowMapper(new OrderRowMapper())
            .saveState(true)
            .build();
}
```

The example uses `tenant.id` and `business.date` consistently in JobParameters and SQL. In real applications, parse `business.date` to `LocalDate` after validation, then bind with the JDBC type matching the schema. Use prepared statements to bind values; do not concatenate JobParameters directly into SQL strings.

Do not name keys after local variables of a single class if that key serves as a contract between scheduler, Job, and multiple components. Name keys after stable business meanings.

## 14. Standardizing Value Formats

Even when the data type is String, values should have a canonical format so systems construct identical JobParameters.

Examples:

| Data Kind | Recommended Format | Example |
|---|---|---|
| Date | ISO-8601 date | `2026-11-15` |
| Timestamp with timezone | ISO-8601 offset datetime | `2026-11-15T09:30:00+07:00` |
| UTC Instant | ISO-8601 instant | `2026-11-15T02:30:00Z` |
| Enum/mode | Canonical uppercase or lowercase per convention | `FULL`, `INCREMENTAL` |
| Tenant code | Canonical string or integer depending on domain | `42` |
| Boolean | Lowercase `true` or `false` if using String | `true` |

Do not use multiple representations for the same value if the key is identifying. Canonical formats ensure two launches of the same business run yield the same JobInstance.

## 15. Avoiding Secrets in JobParameters

JobParameters are typically persisted in JobRepository to support identification and restarts. Therefore, do not pass passwords, access tokens, private keys, or sensitive credentials as JobParameters.

Instead:

- Use a secret manager or the environment's credential provider.
- Pass a non-sensitive credential/profile name or secret reference if configuration selection is needed.
- Use Spring configuration to inject secrets into clients via the application's security mechanism.
- Do not log full JobParameters if they could contain sensitive data.
- Control access to the metadata database and operational dashboards.

For example, you can pass `source.profile=partner-a` and let the application fetch the corresponding credential from a secret store. Do not pass `source.password=...` in JobParameters.

## 16. Custom Parameters and Conversion

Spring Batch 5 allows JobParameters with more specific data types than traditional primitives. However, JobRepository needs to convert values to a storage form and restore them when reading metadata.

If using custom types:

1. Verify that the conversion service/`JobParametersConverter` supports that type.
2. Configure a bidirectional converter if metadata must be read back.
3. Use a stable storage format that remains parseable across upgrades.
4. Avoid storing objects tied to implementation classes or volatile libraries.
5. Test launching, persisting metadata, reading back JobParameters, and restarting.

For example, instead of storing a custom `BusinessPeriod` object if no converter exists, pass two simple keys:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("period.start", "2026-11-01", true)
        .addString("period.end", "2026-11-30", true)
        .toJobParameters();
```

The application parses both values into `LocalDate` and constructs `BusinessPeriod` after validation. This keeps the JobParameters contract clear and easy to operate from a scheduler or API.

## 17. Testing Key Names and Data Types

Parameter injection tests should verify both keys and types. A misspelled key can return null; an incompatible type can prevent bean creation or fail during Step execution.

Example of testing a StepScope bean with JobParameters:

```java
@SpringBatchTest
class OrderReaderParameterTest {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void readerReceivesInputFileParameter() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "classpath:orders.csv", true)
                .addLong("tenant.id", 42L, true)
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            ItemReader<OrderInput> reader = applicationContext.getBean(
                    "orderReader", ItemReader.class);
            assertThat(reader).isNotNull();
            return null;
        });
    }
}
```

The test snippet demonstrates creating a StepExecution with JobParameters and accessing a bean in StepScope. Real tests should read the first item or inspect reader configuration to confirm the exact resource and query, rather than only asserting the bean is non-null.

Cases to test:

- Correct keys and matching value types.
- Missing keys for required parameters.
- Empty values or malformed date formats.
- Invalid `Long` or out-of-range values.
- Omitted Booleans or default values.
- Identifying parameters kept identical upon restart.
- Custom types serializing/converting and reading back from JobRepository.

## 18. Common Errors

### Wrong Key Name in SpEL

JobParameters has `input.file`, but the bean injects `inputFile`. The result may be null or an initialization error. Keep keys centralized and use them consistently across builders, SpEL, validators, and tests.

### Using Property Notation for Dotted Keys

`jobParameters.input.file` is not a safe way to access the key `input.file`. Use `jobParameters['input.file']`.

### Injecting into a Singleton Bean

Singletons are created before the Job runs, so they lack a specific execution's JobParameters. Use `@StepScope` or `@JobScope` when injecting dynamic parameters.

### Creating a Long but Injecting a String or Vice Versa

Incompatible parameter and bean types can cause conversion errors. Choose clear types and test conversion.

### Using String for Every Value

This pushes parsing errors deep into the Step and obscures validation. Use numeric types for numbers, or parse Strings early using canonical formats.

### Changing Identifying Parameter Types Across Versions

Changing `tenant.id` from Long to String can affect JobInstance identity and restarts. Keep types stable or have a migration/compatibility plan.

### Adding Random Timestamps to Identifying Parameters

Every launch may create a new JobInstance, preventing restarts from resuming the old business run. Only use identifying values that reflect business run identity.

### Using Defaults for Required Parameters

A Job might run on the wrong input if `input.file` is missing without raising an error. Use a validator to reject missing or invalid parameters.

### Passing Passwords/Tokens in JobParameters

Metadata may be persisted and shown to operators. Use a secret store and pass only non-sensitive references.

### Storing Custom Objects Without a Converter

A Job may run the first time but fail when saving/reading metadata or restarting. Test bidirectional conversion/serialization before using custom types.

## 19. Key and Type Design Workflow

When adding a new JobParameter, follow this sequence:

1. Define the business or technical meaning of the value.
2. Choose a stable, readable, unambiguous key name.
3. Choose a Java type reflecting the true nature of the value.
4. Choose a canonical format for dates, times, enums, and identifiers.
5. Decide whether the parameter is identifying based on JobInstance identity.
6. Build parameters with `JobParametersBuilder` or a standardized launch mechanism.
7. Inject via `@Value("#{jobParameters['key']}")` in a Batch-scoped bean.
8. Validate required parameters, value ranges, and formats before side effects.
9. Verify custom types have conversion/serialization compatible with JobRepository.
10. Ensure key types and semantics stay stable across restarts and upgrades.
11. Do not put secrets in JobParameters; use secret references or credential providers.
12. Write tests for valid/invalid keys, missing values, conversion, and JobInstance identity.

| Need | Recommended Design |
|---|---|
| Input file path | `input.file` of type `String`, validate file before reading. |
| Tenant ID | `tenant.id` of type `Long` or supported domain ID type. |
| Business date | `business.date` as ISO `LocalDate` or canonical String. |
| Run mode | `import.mode` as enum/String with an allowed value set. |
| Dry-run toggle | `dry.run` of type Boolean, non-identifying if it does not alter business identity. |
| Requester code | `requested.by` of type String, usually non-identifying. |
| Connection secret | Pass `source.profile`/secret reference; do not pass password/token. |

## Conclusion

Key names and data types form the Job's input contract. Use meaningful, consistent keys like `input.file`, `business.date`, and `tenant.id`; access dotted keys with `jobParameters['key']`; and inject dynamic parameters inside `@StepScope` or `@JobScope` beans. Choose types matching the values, standardize date/time formats, validate required parameters, and keep identifying flags and data types stable so JobInstance and restarts work correctly. For custom types, verify bidirectional conversion/serialization; keep secrets out of JobParameters and clearly separate input JobParameters from ExecutionContext used to store progress.
