# Do Not Overcomplicate Expression Concatenation

In Spring Batch, `@StepScope` and `@JobScope` frequently use SpEL to retrieve values from `JobParameters`, `ExecutionContext`, or execution metadata. Short expressions like `#{jobParameters['input.file']}` are very useful because they clearly show which value a bean expects when the step or job starts.

When expressions start containing multiple string concatenations, nested ternaries, nested conditions, type conversions, or accesses across multiple data sources, configuration becomes hard to read and hard to test. At that point, SpEL is carrying business logic that Java code or a dedicated component can express much more clearly.

The principle to follow is to keep expressions at the level of simple lookups and simple defaults. Move parsing, normalization, path assembly, strategy selection, and parameter validation into Java methods, factories, or validators that can be unit tested independently.

## 1. Parameter Injection in Spring Batch

Parameter injection allows a scoped bean to receive values known only when the job is launched. For example, a reader needs the file name passed in `JobParameters`, or a worker needs an ID range placed in the `StepExecution` context.

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .resource(new FileSystemResource(inputFile))
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(OrderRow.class)
        .build();
}
```

The expression `#{jobParameters['input.file']}` accesses a single key. It is easy to understand, easy to inspect, and does not force readers to mentally simulate multi-step SpEL evaluation.

Values are resolved when the scoped target is created inside an active scope. Therefore, beans needing late binding are typically declared with `@StepScope` or `@JobScope`; a regular singleton cannot receive per-JobExecution values by reading JobParameters at startup.

## 2. When Does an Expression Become Too Complex?

An expression can become hard to maintain when it exhibits one or more of these traits:

- Multiple string concatenations to build paths, URLs, file names, or query strings.
- Nested conditional operators (`?:`) to choose modes or strategies.
- Multi-layered null checks, blank checks, formatting, and defaults.
- Converting enums, dates, numbers, or collections directly inside the annotation.
- Reading multiple keys from JobParameters and ExecutionContext and combining them.
- Calling bean methods to perform business logic.
- Expressing authorization or data-selection rules inside a hard-to-read string.

Example of a hard-to-maintain expression:

```java
@Value("#{jobParameters['mode'] == 'FULL' ?
    (jobParameters['region'] == 'ALL' ?
        jobParameters['baseDir'] + '/full/all-' + jobParameters['date'] + '.csv' :
        jobParameters['baseDir'] + '/full/' + jobParameters['region'] + '-' + jobParameters['date'] + '.csv') :
    jobParameters['baseDir'] + '/delta/' + jobParameters['region'] + '-' + jobParameters['date'] + '.csv'}")
String inputFile
```

Readers must decipher conditional structures, file naming rules, region handling, and mode logic right inside an annotation. When rules change, it is easy to break parentheses or generate invalid paths.

Instead of expanding the expression, inject each simple value and process it in Java.

## 3. Keep SpEL at Single-Value Lookup Level

Expressions that are generally readable and well-suited for parameter injection:

| Need | Simple Expression |
|---|---|
| Retrieve input file | `#{jobParameters['input.file']}` |
| Retrieve business date | `#{jobParameters['businessDate']}` |
| Retrieve tenant | `#{jobParameters['tenantId']}` |
| Retrieve partition start key | `#{stepExecutionContext['minId']}` |
| Retrieve saved job-level watermark | `#{jobExecutionContext['watermark']}` |
| Retrieve current step name | `#{stepExecution.stepName}` |

These expressions make the data source clear while keeping processing logic outside configuration. If a simple default is needed, you can use SpEL's Elvis operator:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['delimiter'] ?: ','}") String delimiter) {
    return new OrderReader(delimiter);
}
```

Use defaults in expressions only when the rule is genuinely simple and the default value is business-valid. For required parameters, report clear errors via a validator instead of silently substituting a default value.

## 4. Move Configuration Construction Logic to Java

The following example separates reading parameters from building options. The scoped bean injects only raw values; a factory handles normalization and rule checks.

```java
public record ImportOptions(
        Path inputPath,
        ImportMode mode,
        int pageSize,
        String region) {
}

public enum ImportMode {
    FULL,
    INCREMENTAL
}

@Component
public class ImportOptionsFactory {

    public ImportOptions create(
            String inputFile,
            String modeValue,
            Integer pageSizeValue,
            String regionValue) {

        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("input.file is required");
        }

        ImportMode mode = ImportMode.valueOf(
            modeValue == null ? "INCREMENTAL" : modeValue.toUpperCase(Locale.ROOT));

        int pageSize = pageSizeValue == null ? 500 : pageSizeValue;
        if (pageSize < 1 || pageSize > 5000) {
            throw new IllegalArgumentException("pageSize must be between 1 and 5000");
        }

        String region = regionValue == null || regionValue.isBlank()
            ? "GLOBAL"
            : regionValue.trim().toUpperCase(Locale.ROOT);

        return new ImportOptions(
            Path.of(inputFile).normalize(), mode, pageSize, region);
    }
}
```

The scoped reader receives individual parameters and calls the factory:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['mode']}") String mode,
        @Value("#{jobParameters['pageSize']}") Integer pageSize,
        @Value("#{jobParameters['region']}") String region,
        ImportOptionsFactory optionsFactory) {

    ImportOptions options =
        optionsFactory.create(inputFile, mode, pageSize, region);

    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .resource(new FileSystemResource(options.inputPath().toFile()))
        .delimited()
        .delimiter(";")
        .names("orderId", "customerId", "amount")
        .targetType(OrderRow.class)
        .build();
}
```

In a real application, if `delimiter` is also an option, pass it into `ImportOptions` and the builder. The key point is that enum parsing, region normalization, page size validation, and `Path` construction live in Java, where IDEs support refactoring and unit testing.

## 5. Use JobParametersValidator for Input Data

Do not cram complex validation into SpEL. Job parameters should be validated before steps perform work. Spring Batch supports `JobParametersValidator` to check parameters at the job level.

Example using the default validator to require certain keys:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] { "input.file", "businessDate" },
        new String[] { "requestedBy", "traceId" }
    );
}
```

Register the validator on the job:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
        .validator(importParametersValidator)
        .start(importOrdersStep)
        .build();
}
```

If you need to validate date formats, page size bounds, relationships between `fromDate` and `toDate`, or tenant-specific rules, write a custom validator. The validator can use Java's `LocalDate`, enums, and business services; there is no need to express those rules in SpEL.

## 6. Custom Validator Example

```java
public class ImportParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("input.file");
        String businessDate = parameters.getString("businessDate");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException("input.file is required");
        }

        if (businessDate == null) {
            throw new JobParametersInvalidException("businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "businessDate must use ISO-8601 format");
        }
    }
}
```

The validator runs before the job enters steps, ensuring parameter errors are reported at the proper boundary. There is no need to let the reader open a file before discovering the business date is invalid.

## 7. Distinguishing SpEL #{...} from Placeholder ${...}

In `@Value`, these two syntaxes often appear side by side but serve different purposes:

| Syntax | Typical Value Source | Example |
|---|---|---|
| `#{...}` | Spring Expression Language, can access JobParameters, ExecutionContext, and beans | `#{jobParameters['input.file']}` |
| `${...}` | Property placeholder from application properties, environment, or property sources | `${batch.import.default-page-size:500}` |

For example, application defaults can live in `application.yml`:

```yaml
batch:
  import:
    default-page-size: 500
    archive-directory: /var/batch/archive
```

A scoped bean can receive both job parameters and application configuration properties:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("${batch.import.default-page-size:500}") Integer defaultPageSize) {

    return new OrderReader(inputFile, defaultPageSize);
}
```

`input.file` varies per `JobExecution`; `defaultPageSize` is application deployment configuration. Do not use `JobParameters` for every static config value, and do not use property placeholders to simulate per-run parameters.

## 8. Do Not Assemble Paths or URLs with SpEL

Concatenating path strings in expressions easily causes separator bugs, inconsistent Windows/Linux path handling, and makes security checks difficult to enforce. Use appropriate Java APIs.

Avoid:

```java
@Value("#{jobParameters['baseDir'] + '/' + jobParameters['fileName']}")
String path
```

Instead, inject the two values separately and use `Path.resolve`:

```java
@Bean
@StepScope
FileSystemResource inputResource(
        @Value("#{jobParameters['baseDir']}") String baseDir,
        @Value("#{jobParameters['fileName']}") String fileName) {

    Path path = Path.of(baseDir).resolve(fileName).normalize();
    return new FileSystemResource(path);
}
```

In production code, if `fileName` comes from an external caller, verify that it cannot escape the allowed directory via path traversal. Resolve the base directory to an absolute path and verify `path.startsWith(base)` before opening the file.

For URLs, use `URI`/`UriComponentsBuilder` and properly encoded components instead of string concatenation in SpEL.

## 9. Do Not Use Nested Ternaries to Select Business Modes

Nested ternaries in SpEL make expressions hard to read, especially when multiple import modes exist:

```java
@Value("#{jobParameters['mode'] == 'FULL' ?
    (jobParameters['region'] == 'NORTH' ? 'N1' :
        (jobParameters['region'] == 'SOUTH' ? 'S1' : 'ALL')) : 'DELTA'}")
String route
```

Instead, move the selection into Java:

```java
public ImportRoute resolveRoute(ImportMode mode, Region region) {
    if (mode == ImportMode.FULL && region == Region.NORTH) {
        return ImportRoute.FULL_NORTH;
    }
    if (mode == ImportMode.FULL && region == Region.SOUTH) {
        return ImportRoute.FULL_SOUTH;
    }
    if (mode == ImportMode.FULL) {
        return ImportRoute.FULL_ALL;
    }
    return ImportRoute.DELTA;
}
```

Java logic can use enums, switch expressions, or the strategy pattern. You can write unit tests for every mode/region combination without starting a Spring context.

## 10. Use a Resolver or Factory When Multiple Beans Share Rules

If readers, writers, and tasklets all need the same normalization for a parameter, do not duplicate expressions or logic across beans. Create a shared resolver/factory.

```java
@Component
public class BatchParameterResolver {

    public LocalDate requiredBusinessDate(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }
        return LocalDate.parse(value);
    }

    public Path requiredInputPath(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("input.file is required");
        }
        return Path.of(value).toAbsolutePath().normalize();
    }
}
```

Scoped beans inject simple values and call the resolver:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        BatchParameterResolver resolver) {

    Path path = resolver.requiredInputPath(inputFile);
    LocalDate date = resolver.requiredBusinessDate(businessDate);
    return new OrderReader(path, date);
}
```

The resolver should be a stateless singleton if it only performs pure conversion/validation. Do not store `JobParameters` or execution state in mutable fields of the resolver.

## 11. Inject Appropriate Data Types

Do not turn every parameter into a String and parse manually inside SpEL. Spring provides type conversion for supported injected values; you can also pass `JobParameters` with the right data type at launch time.

Example creating typed parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "data/orders.csv", true)
    .addLong("pageSize", 500L, false)
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();
```

Injecting values into a scoped bean:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['pageSize']}") Long pageSize) {

    int effectivePageSize = pageSize == null ? 500 : Math.toIntExact(pageSize);
    return new OrderReader(Path.of(inputFile), effectivePageSize);
}
```

Choose a Java type matching the created `JobParameter` type. If defaults or range checks are needed, handle them in Java or a validator. Using `Long` instead of `long` also allows representing an omitted key as `null`, depending on conversion and configuration.

## 12. Keep Expressions Independent of Business Logic

SpEL is suited for fetching data from context or calling a simple bean method in certain cases, yet invoking complex services from expressions hides dependencies and complicates testing.

Do not let expressions execute database queries, make HTTP calls, perform authorization, or select business workflows. Those actions may execute when the target is created, obscuring when side effects happen and making errors hard to diagnose.

If data lookups are required, inject the service into the scoped bean and call it inside a clearly named method, or execute it within a tasklet/processor fitting the lifecycle. Bean configuration should make dependencies explicit through constructor or method parameters.

## 13. When to Use JobScope vs StepScope for Parameter Injection?

Choose the scope based on the scope of the data and state:

| Scope | Suitable When | Example |
|---|---|---|
| `@StepScope` | Values or state specific to one `StepExecution` | Reader receiving `minId`, `maxId`, file path, or cursor |
| `@JobScope` | Values shared across one `JobExecution` | Shared policy or output name for sequential steps |
| Singleton | Static, stateless, application-wide configuration | Pure resolver, validator, or factory |

Do not place mutable per-worker state into a singleton. For partitioning, `stepExecutionContext` combined with `@StepScope` is usually the clearest way for each worker to receive its own parameters.

## 14. Simple Defaults and Required Parameters

SpEL can apply simple defaults, but two scenarios must be distinguished:

- Optional parameters with valid defaults: use the Elvis operator or handle null in Java.
- Required parameters: validate and report clear errors before the step starts.

Example of an optional parameter:

```java
@Value("#{jobParameters['delimiter'] ?: ','}") String delimiter
```

Example of a required parameter that should be checked by a validator instead of chaining operators to return an error string or substitute value:

```java
if (parameters.getString("input.file") == null) {
    throw new JobParametersInvalidException("input.file is required");
}
```

Do not use defaults to silently turn a missing parameter into a broader data scope, such as defaulting `tenantId` to `ALL`, unless that is an explicit, permitted business rule.

## 15. Testing Parameter Injection

Tests should verify both expression resolution and the Java logic called after injection.

Useful test cases:

1. Valid `JobParameters` construct the reader with the exact file and options.
2. Absent optional parameter receives the defined default.
3. Missing required parameter causes the validator to reject the job before reading data.
4. Invalid enum value reports a clear parameter error.
5. Two `JobExecutions` with different inputs receive separate scoped targets.
6. Two partitions receive distinct values from `StepExecution` context.
7. Restarting the same `JobInstance` reuses identifying parameters and expected checkpoints.
8. Refactoring messages or Java code style does not break SpEL lookups.

Unit tests for factories/resolvers can verify paths, enums, dates, defaults, and numeric bounds. Integration tests with `JobRepository` and real scopes verify late binding works when the step starts.

## 16. Common Errors

| Error | Consequence | How to Fix |
|---|---|---|
| Nested ternaries in `@Value` | Expression hard to read and error-prone to edit | Move selection to a Java method or strategy |
| Concatenating paths/URLs in SpEL | Wrong separators, encoding, or unsafe path handling | Use `Path`, `URI`, or dedicated builders |
| Parsing enums/dates/numbers inside expressions | Hard-to-diagnose conversion errors | Inject raw values and parse in factory/validator |
| Using SpEL to validate multiple parameters | Business rules hidden inside annotations | Use `JobParametersValidator` |
| Calling complex services from expressions | Hidden dependencies and side effects | Inject services explicitly and call from Java |
| Using `${...}` for `JobParameters` | Confuses config properties with per-execution data | Use `#{jobParameters[...]}` |
| Using `#{...}` for static application config | Configuration bound to wrong source | Use property placeholders or `@ConfigurationProperties` |
| Defaults for required parameters | Job may run with the wrong scope | Validate and fail early |
| Injecting `JobParameters` into singletons | No per-execution values | Use scoped beans/proxies |
| Repeating the same expression across beans | Rules diverge when changed | Use shared factory/resolver |

## 17. Maintainable Expression Design Workflow

When declaring a scoped bean, follow this sequence:

1. Identify whether the value comes from `JobParameters`, `StepExecutionContext`, `JobExecutionContext`, or application properties.
2. Use a short expression to fetch each value.
3. Determine which parameters are required and which have valid defaults.
4. Put parsing, normalization, value combination, and business rules into Java.
5. Use `JobParametersValidator` for conditions that must be checked before steps run.
6. Use a factory/resolver if multiple beans need the same conversion rules.
7. Choose `@StepScope` or `@JobScope` according to the required target lifecycle.
8. Write unit tests for Java logic and integration tests for late binding.

Expressions should be short enough that readers see the data source without having to decode an entire algorithm.

## Conclusion

Do not overcomplicate SpEL string concatenation in Spring Batch `@Value` annotations. Keep expressions at simple lookups such as `#{jobParameters['input.file']}` or `#{stepExecutionContext['minId']}`; move path assembly, enum/date parsing, mode selection, complex defaults, and validation into Java factories, resolvers, or `JobParametersValidator`.

This separation keeps reader/writer configuration readable, makes business rules unit-testable, and surfaces parameter errors early. Distinguish `#{...}` for SpEL from `${...}` for application properties, use scoped beans to late-bind per-execution values, and keep expressions free of hidden logic or side effects.
