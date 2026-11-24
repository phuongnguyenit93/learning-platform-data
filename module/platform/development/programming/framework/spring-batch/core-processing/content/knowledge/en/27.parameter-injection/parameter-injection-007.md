# Default Parameters

In Spring Batch, a Job typically receives input data through `JobParameters`, such as business date, file path, source code, or page size. Not every parameter has to be passed by the caller. For optional parameters, the application can supply a **default value** so the Step still runs when `JobParameters` does not contain that key.

When injecting parameters into a `@StepScope` bean, you can use SpEL to read `JobParameters` and the Elvis operator `?:` to select a fallback value when the parameter is missing or `null`:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

If the caller does not pass `inputFile`, the reader uses `data/orders.csv`. If the caller passes a value, the passed value is used. Default parameters help reduce repetitive configuration, but they must be designed carefully so they do not make the Job read the wrong data or change results on restart.

## 1. JobParameters and Optional Parameters

`JobParameters` is the set of input parameters bound to a `JobExecution`. Some parameters identify the logical unit of work (`identifying`), while others only provide supplemental information (`non-identifying`).

Example of an order import Job:

| Parameter | Required? | Example | Role |
|---|---|---|---|
| `businessDate` | Yes | `2026-11-15` | Identifies the business period to import |
| `inputFile` | No | `data/orders.csv` | Input file; can have a default |
| `pageSize` | No | `500` | Number of rows read per page |
| `sourceSystem` | Depends on business | `ERP` | Identifies the source system |

An optional parameter can be handled in two ways:

- The launcher passes a specific value; the Step uses that value.
- The launcher omits the key; the Step uses the default configured in the injection expression or in the `JobParameters` construction layer.

Defaults should only apply to parameters that genuinely have a safe default value. Parameters such as business date, tenant, or source account should usually not be guessed, as choosing the wrong one will process the wrong data.

## 2. Using the SpEL Elvis Operator for Defaults

In `@Value`, the `#{...}` expression is SpEL. You can use the Elvis operator `?:` to choose a default value when the left-hand expression has no value:

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

Meaning:

- `jobParameters['inputFile']`: reads the `JobParameter` with key `inputFile`.
- `?:`: if the left-hand expression has no value, use the right-hand expression.
- `'data/orders.csv'`: default string.

Some other examples:

```java
@Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize

@Value("#{jobParameters['delimiter'] ?: ','}") String delimiter

@Value("#{jobParameters['includeInactive'] ?: false}") Boolean includeInactive

@Value("#{jobParameters['maxRetries'] ?: 3}") Integer maxRetries
```

Provide defaults with the matching data type. For example, `500` is an integer, `false` is a boolean, and `','` is a string. Spring performs type conversion when injecting into the method parameter if a matching converter exists.

Do not use string defaults for numeric values unnecessarily. Writing `?: 500` makes the numeric type clearer than `?: '500'`, especially when the expression is used in arithmetic or comparisons.

## 3. Complete Example with @StepScope

Suppose the order import Job has two optional parameters: `inputFile` and `pageSize`. The default file is `data/orders.csv`; the default page size is 500.

```java
@Configuration
public class OrderImportConfiguration {

    @Bean
    @StepScope
    public JdbcPagingItemReader<Order> orderReader(
            DataSource dataSource,
            PagingQueryProvider queryProvider,
            RowMapper<Order> orderRowMapper,
            @Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        return new JdbcPagingItemReaderBuilder<Order>()
                .name("orderReader")
                .dataSource(dataSource)
                .queryProvider(queryProvider)
                .parameterValues(Map.of("businessDate", businessDate))
                .rowMapper(orderRowMapper)
                .pageSize(pageSize)
                .saveState(true)
                .build();
    }
}
```

In this example, `pageSize` has a default of 500, while `businessDate` is required so it has no arbitrary default. `@StepScope` allows SpEL to be evaluated once the current `StepExecution` exists.

If using `FlatFileItemReader`, the same approach applies to `inputFile`:

```java
@Bean
@StepScope
public ItemStreamReader<Order> fileOrderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("fileOrderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Declare the return type as `ItemStreamReader<Order>` to indicate the reader also supports the `open()`, `update()`, and `close()` lifecycle for checkpoints/restarts.

## 4. Passed Values Take Precedence Over Defaults

Defaults are only used when the `JobParameter` does not provide a value. If the caller passes a valid value, that value takes precedence.

Example expression:

```java
@Value("#{jobParameters['pageSize'] ?: 500}") Integer pageSize
```

| JobParameters | Injected Value |
|---|---:|
| No `pageSize` key | 500 |
| `pageSize=100` | 100 |
| `pageSize=1000` | 1000 |
| Key has null value | 500 |

Do not confuse a default with overriding a value the caller passed. If the caller requests `pageSize=1000`, the Step must use 1000 rather than forcing 500.

For string parameters, define how empty or whitespace-only strings are handled. The Elvis operator handles absent/null values; do not rely on it to replace validation for empty strings or invalid data. Check explicitly in the factory method, validator, or service:

```java
if (inputFile == null || inputFile.isBlank()) {
    throw new IllegalArgumentException("inputFile must not be blank");
}
```

If you want empty strings treated as not passed, normalize inputs at the launch layer or use explicit, tested SpEL/Java logic for that case.

## 5. Distinguishing SpEL Defaults from Spring Property Placeholders

Spring has two common default syntaxes, but they pull values from two different sources.

**SpEL reading JobParameters:**

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

This expression reads a parameter of the current `JobExecution`. This is how to set a default for a `JobParameter` in a batch bean with an appropriate scope.

**Property placeholder reading application configuration:**

```java
@Value("${batch.input-file:data/orders.csv}")
String inputFile
```

This expression reads the `batch.input-file` property from the Spring Environment, such as `application.yml`, environment variables, or other property sources. The part after `:` is the property placeholder default.

| Syntax | Source | When to Use? |
|---|---|---|
| `#{jobParameters['inputFile'] ?: 'data/orders.csv'}` | JobParameters | Value varies per Job run |
| `${batch.input-file:data/orders.csv}` | Spring Environment | Application/environment configuration value |

Do not swap `${...}` for `#{...}` or vice versa without identifying the right data source. Properties typically describe deployment configuration; `JobParameters` describe inputs of a single batch run.

You can combine both sources if business rules require preferring a `JobParameter`, then an application property, and finally a fallback. However, long expressions are hard to read; it is usually better to compute the value in a factory/service or materialize the default before launch so precedence rules stay clear.

## 6. Materializing Defaults When Building JobParameters

Another option is to populate defaults before launching the Job. This produces complete `JobParameters` from the start:

```java
public JobParameters buildParameters(
        String businessDate,
        String requestedInputFile,
        Integer requestedPageSize) {

    String inputFile = requestedInputFile != null && !requestedInputFile.isBlank()
            ? requestedInputFile
            : "data/orders.csv";

    int pageSize = requestedPageSize != null
            ? requestedPageSize
            : 500;

    return new JobParametersBuilder()
            .addString("businessDate", businessDate, true)
            .addString("inputFile", inputFile, true)
            .addLong("pageSize", (long) pageSize, false)
            .toJobParameters();
}
```

Here, `inputFile` and `pageSize` are computed before calling `JobLauncher`. The Step simply injects the keys already in `JobParameters`:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
@Value("#{jobParameters['pageSize']}") Long pageSize
```

Benefits of materializing defaults:

- `JobParameters` records the exact values actually used for the run.
- Metadata clearly shows the selected file and page size.
- Restarting the same `JobInstance` receives the exact saved values again.
- Logs, audits, and operational dashboards are easier to explain.
- Avoids a default changing between two deployments and causing the same `JobInstance` to run with different configuration.

This is usually the better choice for defaults that affect business data, input sources, or restart results.

## 7. Default Parameters and Identifying JobParameters

A `JobInstance` is identified by Job name and the `JobParameters` marked as identifying. When adding defaults, decide whether that parameter participates in identifying the logical job.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders.csv", true)
        .addLong("pageSize", 500L, false)
        .toJobParameters();
```

In this example:

- `businessDate` is identifying because it defines the business period.
- `inputFile` is identifying if two different files represent two different logical jobs.
- `pageSize` is non-identifying because it is a performance parameter and does not change the business dataset.

The identifying vs non-identifying decision must follow business meaning, not whether the parameter has a default. If changing a parameter changes the data to process, consider including it in identity. If it only changes how execution runs without changing the logical job, it can be non-identifying.

Restarts require keeping identifying parameters unchanged to resume the same `JobInstance`. If a default is recomputed and an identifying value differs, Spring Batch may create a different `JobInstance` instead of restarting the old execution.

## 8. Injected Defaults Do Not Automatically Become Saved JobParameters

This is an important difference between defaults in `@Value` and defaults materialized before launch.

Suppose `JobParameters` has no `inputFile` key, and the bean injects:

```java
@Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}")
String inputFile
```

The target bean uses `data/orders.csv`, but that does not mean `JobParameters` in `JobRepository` has had the `inputFile` key added. The default value is only used when evaluating the expression to create the bean.

If a later application version changes the default to `data/orders-v2.csv`, a restarted execution that had not previously saved `inputFile` might receive the new default. The same `JobInstance` could inadvertently process a different file.

For defaults that affect data, add the value to `JobParameters` before launch or store the selection in durable metadata. Do not rely on an in-code fallback that can change across deployments to re-determine the data source for an in-flight execution.

## 9. Dynamic Defaults and Restart Risks

A dynamic default is a value computed when the Job runs, such as the current date or a timestamp:

```java
@Value("#{jobParameters['businessDate'] ?: T(java.time.LocalDate).now().toString()}")
String businessDate
```

This expression looks convenient when the caller omits the date. However, if the Job runs first on the 15th and fails, restarting on the 16th may evaluate the default to the 16th. The Job could process different data from the first run.

For dynamic defaults:

- Compute the value once at the launch layer.
- Put that value into `JobParameters`, usually as identifying if it defines the business period.
- On restart, reuse the exact old `JobInstance` and parameters.
- Do not call `now()` or generate a new UUID every time the target bean is created if the value must stay stable across restarts.

Example of generating a default date before launch:

```java
LocalDate effectiveDate = requestedDate != null
        ? requestedDate
        : LocalDate.now(clock);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", effectiveDate.toString(), true)
        .toJobParameters();
```

Injecting `businessDate` from `JobParameters` ensures all restarts use the same business date.

## 10. Defaults Do Not Replace Validation

A default only solves the case where a parameter is not supplied. It does not prove a value is valid.

For example, `pageSize` defaults to 500, yet a caller could pass `-1`. The reader still receives the caller's value if the expression only checks for null. Range validation is needed:

```java
if (pageSize == null || pageSize < 1 || pageSize > 10_000) {
    throw new IllegalArgumentException("pageSize must be between 1 and 10000");
}
```

For `inputFile`, verify the file exists and is readable. For `businessDate`, parse according to the specified format and confirm the business period is permitted to run.

You can validate `JobParameters` before the Job runs using `JobParametersValidator`. For instance, `DefaultJobParametersValidator` checks lists of required and optional keys. However, **an optional key is not synonymous with having a default value**: the validator only checks the validity of the parameter set; it does not automatically add missing values to `JobParameters`.

If defaults need to be persisted in metadata, add them with `JobParametersBuilder` before launch. If required parameters need checking, use a validator. These two responsibilities work together rather than replacing one another.

## 11. Example Using JobParametersValidator with Defaults

A clean organization is to materialize defaults first, then validate the complete `JobParameters` set:

```java
@Bean
public JobParametersValidator orderImportParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"businessDate", "inputFile"},
            new String[] {"pageSize", "sourceSystem"}
    );
}
```

In the launch flow, the application can:

1. Receive parameters from an API, scheduler, or command line.
2. Populate `inputFile`/`pageSize` if omitted by the caller and allowed by business rules.
3. Normalize dates, paths, and string values.
4. Build the complete `JobParameters`.
5. Call the validator to check required/optional keys and related rules.
6. Invoke `JobLauncher`.

`DefaultJobParametersValidator` checks required and optional keys as configured. If you need to validate values such as positive page size, valid date format, or file existence, use a custom validator or check at the appropriate layer.

## 12. Default Parameters for Multiple Data Types

When injecting defaults, pay attention to data types and conversion:

| Type | SpEL Example | Method Parameter Type |
|---|---|---|
| String | `#{jobParameters['delimiter'] ?: ','}` | `String` |
| Integer | `#{jobParameters['pageSize'] ?: 500}` | `Integer` |
| Long | `#{jobParameters['maxRows'] ?: 100000L}` | `Long` |
| Boolean | `#{jobParameters['enabled'] ?: true}` | `Boolean` |
| BigDecimal | `#{jobParameters['minimumAmount'] ?: 0.00}` | `BigDecimal` |

For floating-point numbers or currency, control scale/rounding according to business rules. Do not use floating-point types for monetary calculations when decimal precision is required; use `BigDecimal` and explicit rounding rules.

For dates and times, usually pass ISO-formatted strings or a `JobParameter` type supported by your Spring Batch version, then parse and validate explicitly. If the default is the current date, materialize it before launch so restarts do not change the date.

## 13. Using Defaults in @StepScope and @JobScope

`@StepScope` fits when a bean needs parameters scoped to a `StepExecution`, such as a reader receiving `minId`/`maxId` per partition. `@JobScope` fits when a bean needs data scoped to a `JobExecution` and shared by multiple Steps.

Example of a step-scoped reader:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile'] ?: 'data/orders.csv'}") String inputFile) {
    // Initialize the reader with inputFile already defaulted.
    return createOrderReader(inputFile);
}
```

Example of a job-scoped coordinator:

```java
@Bean
@JobScope
public ImportCoordinator importCoordinator(
        @Value("#{jobParameters['sourceSystem'] ?: 'ERP'}") String sourceSystem) {
    return new ImportCoordinator(sourceSystem);
}
```

The scope determines when the expression is evaluated and the target bean's lifecycle. A default expression does not turn a singleton bean into step-scoped; if late binding from `JobParameters` is needed, use the appropriate scope.

## 14. Common Misconceptions

**Assuming `@Value` defaults are added to `JobParameters`.** They are only values injected into the bean. If persistence/auditing/stable restarts are needed, materialize defaults before launch.

**Confusing `${property:default}` with `#{jobParameters['key'] ?: default}`.** One syntax reads Spring Environment, while the other reads `JobParameters`.

**Assuming optional keys in a validator automatically have defaults.** Optional only means the key is allowed to be absent; the validator does not supply a value.

**Using the current date as a bean default and expecting stable restarts.** A restart on another day may use a different date. Compute defaults once and store them in `JobParameters`.

**Assuming defaults guarantee valid data.** Callers can still pass invalid values. Validate types, ranges, formats, and resource existence.

**Using defaults for required business parameters.** A wrong guess can cause the Job to process the wrong tenant, period, or file. Only set defaults when business rules are explicit.

**Assuming `@StepScope` automatically preserves defaults across restarts.** Scope manages lifecycle; `JobRepository` persists `JobParameters` and `ExecutionContext`. Dynamically injected defaults do not automatically become metadata.

## 15. Testing Default Parameters

Test parameter-present, parameter-missing, and invalid-value cases:

1. Omit `inputFile`: the bean receives the default `data/orders.csv`.
2. Pass `inputFile=custom.csv`: the bean receives `custom.csv`.
3. Omit `pageSize`: the bean receives 500.
4. Pass `pageSize=1000`: the bean receives 1000.
5. Pass `pageSize=-1`: validation rejects the value.
6. Pass empty string or whitespace: the application handles it per defined rules without accidentally treating it as a valid path.
7. Launch a Job without optional parameters, then restart after changing the in-code default: confirm the metadata strategy prevents unintended input source changes.
8. Run two `JobExecutions` with different `JobParameters` concurrently: confirm step-scoped beans do not share runtime values.

Late binding tests require an active Step context. You can use Spring Batch Test utilities to create a `StepExecution` and run code inside step scope. For integration tests, inspect both `JobParameters` persisted in `JobRepository` and the actual values received by the bean.

## 16. Designing Default Parameters Safely

Before setting a default, determine whether the parameter is truly optional and whether the fallback value is business-safe. For environment-specific configuration, use Spring property placeholders. For per-run values, read `JobParameters` via SpEL in a bean with `@StepScope` or `@JobScope` as appropriate.

If a default affects input data, business period, or restart results, compute the default at the launch layer and save it into `JobParameters` so metadata accurately reflects what was used. Use validators to check required/optional parameters and separately validate formats, ranges, and resources. Avoid dynamic defaults like current date recomputed every time a bean is created.

Default parameters make Jobs easier to use and reduce repetitive configuration. When properly combined with late binding, validation, identifying parameters, and restarts, applications can support optional parameters while keeping inputs clear, traceable, and consistent across executions.
