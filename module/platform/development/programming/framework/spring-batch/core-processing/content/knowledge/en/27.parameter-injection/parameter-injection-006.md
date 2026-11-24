# Missing Parameters

In Spring Batch, a bean can receive JobParameters via late binding, such as through a SpEL expression in `@Value`. However, a required parameter may not be passed when the Job launches. When a key does not exist, the access expression typically returns `null`; if the bean requires a non-nullable value or the code assumes the value is always present, the Step may fail during bean creation or when using the parameter.

Three cases must be distinguished:

- **Missing parameter**: JobParameters does not contain the requested key.
- **Present but empty or blank parameter**: the key is present, but the value is an empty string or contains only whitespace.
- **Present parameter with a default or business value**: the key is explicitly passed and has a value.

How to handle each depends on the parameter's meaning. If the parameter is required, validate it before the Job runs and report a clear error. If the parameter is optional, use a nullable type or an intentional default. Do not let a missing key silently turn into an incorrect value and cause the Job to process the wrong data.

## 1. What Does a Missing Parameter Mean?

JobParameters is the key-value set passed to JobLauncher when launching a Job. Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

jobLauncher.run(importJob, parameters);
~~~

In this run, the Job has two keys:

- inputFile
- businessDate

If a bean tries to read an additional key `mode`:

~~~java
@Value("#{jobParameters['mode']}")
String mode
~~~

then the `mode` key is not in JobParameters. In a map access expression, the resolved value is `null`.

A missing key is not the same as passing the string `"null"`, an empty string, or the value `"FULL"`. These are distinct states and should be handled separately.

A common mistake is assuming a parameter is always present:

~~~java
String mode = jobParameters.getString("mode");
String normalized = mode.trim();
~~~

If `mode` does not exist, `mode` is `null` and calling `trim()` throws a `NullPointerException`. The problem starts with not clearly defining whether the parameter is required or optional.

## 2. SpEL Accessing JobParameters

Spring Batch exposes JobParameters in the execution context so scoped beans can access them with SpEL.

Example:

~~~java
@Bean
@StepScope
public ItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    // ...
}
~~~

Points to remember:

- `jobParameters['inputFile']` accesses the key by name.
- Key names are case-sensitive.
- Missing keys typically return `null`.
- Values are converted to the Java parameter type if Spring has a matching converter.
- Resolution happens when the scoped bean is created during Job/Step execution, not when the ApplicationContext starts up.

JobParameters can be accessed from both JobScope and StepScope. StepScope can also access Job ExecutionContext and Step ExecutionContext.

If the error is an inactive scope, that is a different issue from a missing key. An inactive scope typically occurs when the bean is accessed outside the Job/Step lifecycle. When the scope is active but the key is missing, the expression can still resolve to `null`.

## 3. Missing vs Empty and Blank

Suppose a parameter is named `mode`:

| State | Launch Example | Meaning |
|---|---|---|
| Missing | Key `mode` not added | No value was passed |
| Empty | mode = "" | Key exists, but string is empty |
| Blank | mode = "   " | Key exists, but contains no meaningful content |
| Populated | mode = "FULL" | Explicit value provided |

For strings, checking only for `null` is insufficient if empty or whitespace-only strings are also invalid.

Example:

~~~java
if (mode == null) {
    throw new IllegalArgumentException("mode is required");
}
~~~

This condition still accepts an empty string. You can use Spring's `StringUtils`:

~~~java
if (!StringUtils.hasText(mode)) {
    throw new IllegalArgumentException(
            "Parameter 'mode' must contain text");
}
~~~

`StringUtils.hasText` returns `false` for `null`, empty strings, and whitespace-only strings.

Explicitly decide whether empty/blank is treated as missing or has a distinct meaning. Do not let different components in the Job interpret it inconsistently.

## 4. Required Parameters Should Be Validated Before the Job Runs

If a missing parameter prevents the Job from executing its business logic properly, reject the JobParameters before any Step starts. Spring Batch provides `JobParametersValidator` for this purpose.

Example custom validator:

~~~java
public class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");

        if (!StringUtils.hasText(inputFile)) {
            throw new JobParametersInvalidException(
                    "Required parameter 'inputFile' is missing or blank");
        }

        String businessDate =
                parameters.getString("businessDate");

        if (!StringUtils.hasText(businessDate)) {
            throw new JobParametersInvalidException(
                    "Required parameter 'businessDate' is missing or blank");
        }
    }
}
~~~

Attach the validator to the Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importStep,
        JobParametersValidator importJobParametersValidator) {

    return new JobBuilder("customerImportJob", jobRepository)
            .validator(importJobParametersValidator)
            .start(importStep)
            .build();
}
~~~

If `inputFile` or `businessDate` is missing, the Job is rejected with `JobParametersInvalidException`. The Step does not have to wait until the reader is created to discover the error.

This is a good choice for parameters that define the dataset or required processing behavior. Error messages should state the parameter name and exact requirement rather than just saying "invalid parameters".

## 5. Using DefaultJobParametersValidator

For simple rules, Spring Batch provides `DefaultJobParametersValidator` to declare required keys and optional keys.

Example:

~~~java
@Bean
public JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"mode", "encoding"});
}
~~~

In this example:

- `inputFile` and `businessDate` are required keys.
- `mode` and `encoding` are accepted optional keys.
- Keys outside these lists are handled according to the validator's rules.

You can attach this validator to the Job via `.validator(...)` as shown in the previous section.

If you need to check for blank strings, date formats, value ranges, or relationships between multiple parameters, a custom `JobParametersValidator` is usually clearer. For example, `mode` can only be `FULL` or `DELTA`; `businessDate` must match a date format; `inputFile` must be supplied when `mode` is `FULL`.

## 6. Optional Parameters Can Accept Null

If a parameter is genuinely optional, inject it into a reference type such as `String`, `Long`, `Integer`, or `Boolean` and handle `null` explicitly.

Example:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return input -> {
        if (tenantId == null) {
            return convertWithoutTenant(input);
        }

        return convertForTenant(input, tenantId);
    };
}
~~~

When `tenantId` is not passed, the bean receives `null` and executes the default business branch.

For numeric types, use wrapper types:

~~~java
@Value("#{jobParameters['maxRows']}")
Integer maxRows
~~~

If `maxRows` is missing, the value can be `null`. Do not use primitive `int` if the parameter might not exist, because primitives cannot represent `null` and conversion may fail.

Similarly, use `Boolean` instead of `boolean` when you need to distinguish "not passed" from `false`.

## 7. Using Default Values in SpEL

For optional parameters with sensible defaults, you can use SpEL's Elvis operator:

~~~java
@Bean
@StepScope
public ItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
        String encoding,

        @Value("#{jobParameters['pageSize'] ?: 500}")
        Integer pageSize) {

    return buildReader(encoding, pageSize);
}
~~~

If the key is absent or the expression evaluates to `null`, the default is used:

- `encoding` defaults to `UTF-8`.
- `pageSize` defaults to `500`.

Default values should reflect clearly defined business or technical rules. Do not set arbitrary defaults for parameters defining a dataset, tenant, or business date, because the Job might run on a different dataset than the caller intended.

For strings, also check for blankness. Do not assume whitespace-only strings are equivalent to `null` in every expression. You can inject the value and then normalize and validate with `StringUtils.hasText`.

## 8. SpEL Defaults Do Not Add Parameters to JobParameters

This is an important distinction.

Suppose a Job is launched without `encoding`:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .toJobParameters();
~~~

The bean uses:

~~~java
@Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
String encoding
~~~

Inside the bean, `encoding` receives `UTF-8`. However, `JobParameters` still does not contain the `encoding` key. The default is only applied during injection; it does not modify `JobParameters` and does not automatically become an identifying parameter.

This has consequences:

- `JobInstance` identity does not change because a default was injected.
- `JobRepository` does not treat the default as a parameter passed by the caller.
- A restart running newer code with a different default might process differently from the prior run.
- `JobParameters` logs may not display the applied default value.

If the default affects business outcomes, consider normalizing parameters before launch, passing the value explicitly, or storing the resolved configuration in `ExecutionContext` for consistent restarts.

## 9. Distinguishing Optional Parameters from Non-Identifying Parameters

A non-identifying parameter is still a parameter present in `JobParameters`. It simply does not participate in identifying the `JobInstance`.

Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("mode", "FULL", false)
        .toJobParameters();
~~~

`mode` exists and can be injected normally:

~~~java
@Value("#{jobParameters['mode']}")
String mode
~~~

Only if `mode` is not passed is the key actually missing. Setting `identifying=false` does not mean the parameter is optional; it only controls `JobInstance` identity.

A parameter can be:

- Required and identifying.
- Required but non-identifying.
- Optional, and identifying when provided.
- Optional and non-identifying.

These are two separate design axes: requiredness belongs to business validation; identifying belongs to `JobInstance` identity and restarts.

If `mode` changes the dataset or business outcome, consider making it an identifying parameter. If `mode` is non-identifying, ensure it does not change between restarts in a way that causes inconsistent results.

## 10. Checking Parameters Directly in JobParameters

Besides SpEL, you can read JobParameters in code via the `JobParameters` API.

Example in a validator:

~~~java
String inputFile = parameters.getString("inputFile");
Long maxRows = parameters.getLong("maxRows");
Double threshold = parameters.getDouble("threshold");
~~~

These getters return `null` when the corresponding key has no matching value. Check for `null` before using them.

If you need to distinguish a missing key from a key that exists with an empty value, inspect the parameters map:

~~~java
boolean supplied =
        parameters.getParameters().containsKey("mode");

String mode = parameters.getString("mode");
~~~

Then handle each state:

~~~java
if (!supplied) {
    // Caller did not pass mode.
} else if (!StringUtils.hasText(mode)) {
    // Key is present but value is empty or blank.
} else {
    // Value is present.
}
~~~

The map API and `JobParameter` types may vary across Spring Batch versions. Use the getter matching the parameter's data type in your project's version.

## 11. A Misspelled Parameter Is the Same as Missing

A common bug is a typo or casing mismatch between launch time and injection time.

For example, the caller passes:

~~~java
.addString("inputFile", "/data/orders.csv", true)
~~~

but the bean reads:

~~~java
@Value("#{jobParameters['inputfile']}")
String inputFile
~~~

Because the key names differ, the expression finds no value. The outcome is identical to omitting the parameter.

Declare key names as constants for consistent reuse:

~~~java
public final class ImportParameterNames {

    public static final String INPUT_FILE = "inputFile";
    public static final String BUSINESS_DATE = "businessDate";
    public static final String MODE = "mode";

    private ImportParameterNames() {
    }
}
~~~

When building JobParameters and writing validators, use the same key names. SpEL annotations still require literal strings, so add tests to catch mismatched names.

## 12. Parameter Exists With the Wrong Type

A key may exist, but its value cannot be converted to the Java type requested by the bean.

For example, the caller passes:

~~~java
.addString("pageSize", "many", false)
~~~

but the bean injects:

~~~java
@Value("#{jobParameters['pageSize']}")
Integer pageSize
~~~

Spring needs to convert the value to `Integer`. The string `"many"` is not a valid number, so scoped bean creation may fail due to a conversion error.

A better approach is to use the right `JobParameter` type at launch time:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addLong("pageSize", 500L, false)
        .toJobParameters();
~~~

Or validate the string before converting if the parameter comes from a text source. The error message should state the parameter name and expected type.

Do not catch every conversion exception and silently substitute `0`. A value of `0` may mean something different from a missing parameter or invalid input.

## 13. Using Defaults in a Controlled Way

If defaults are reasonable, centralize normalization logic in one clear configuration instead of scattering Elvis operators across multiple beans.

Example:

~~~java
public record ImportOptions(
        String encoding,
        int pageSize,
        boolean dryRun) {
}
~~~

Bean creating the options:

~~~java
@Bean
@JobScope
public ImportOptions importOptions(
        @Value("#{jobParameters['encoding'] ?: 'UTF-8'}")
        String encoding,

        @Value("#{jobParameters['pageSize'] ?: 500}")
        Integer pageSize,

        @Value("#{jobParameters['dryRun'] ?: false}")
        Boolean dryRun) {

    if (pageSize == null || pageSize < 1) {
        throw new IllegalArgumentException(
                "pageSize must be greater than zero");
    }

    return new ImportOptions(
            encoding,
            pageSize,
            dryRun);
}
~~~

Steps can share `ImportOptions` within the same `JobExecution`.

The example above shows defaults applied at injection time, followed by range validation. Defaults do not replace validation: `pageSize = -1` is still invalid even though the key exists.

If these options must stay identical across restarts, ensure the resolved values are persisted or that default rules remain stable across application versions.

## 14. Do Not Use Defaults to Hide Required Parameters

Example of what not to do:

~~~java
@Value("#{jobParameters['tenantId'] ?: 'DEFAULT_TENANT'}")
String tenantId
~~~

If `tenantId` identifies which customer's data to access, automatically falling back to `DEFAULT_TENANT` can cause the Job to read or write the wrong tenant's data.

For required parameters:

- Do not provide fake defaults.
- Use `JobParametersValidator`.
- Fail with a clear error before Steps run.
- Do not proceed when information identifying data scope is missing.

Defaults are only appropriate when there is a business-approved default value and every run omitting the parameter is meant to use that exact value.

## 15. Checking Missing ExecutionContext Keys

The same mechanism applies to Job ExecutionContext and Step ExecutionContext.

Example:

~~~java
@Value("#{jobExecutionContext['reportId']}")
Long reportId
~~~

If the `reportId` key has not yet been written by an earlier Step or promoted, the value may be `null`.

With Step ExecutionContext:

~~~java
@Value("#{stepExecutionContext['fromId']}")
Long fromId
~~~

If the Partitioner did not populate `fromId`, the worker lacks a lower bound. Do not use arbitrary defaults, or the worker may read the wrong data range.

When reading a context key produced by an earlier Step:

- Verify the preceding Step wrote the key.
- Verify the promotion listener ran if the key needs to be promoted to Job context.
- Check flow conditions so the consuming Step only runs after the producer succeeds.
- Validate the key before creating the reader or writer.

If the key is required, fail explicitly instead of defaulting to `0` or an empty string.

## 16. When Do Missing Parameter Errors Occur?

Detection timing depends on how injection and validation are set up:

| Approach | Detection Timing |
|---|---|
| JobParametersValidator | Before Steps start |
| Inject reference type and check in factory method | When the scoped bean is created |
| Use `null` and call a method without checking | When code uses the value |
| Inject primitive or non-convertible type | When Spring resolves/converts the value |
| Read an unpopulated ExecutionContext key | When the scoped bean resolves or code accesses it |

Detecting early is better. For required `inputFile`, `tenantId`, or `businessDate`, a validator lets operators see the error immediately at launch instead of waiting for reader initialization.

If a parameter depends on the result of a previous Step, a Job-level validator cannot validate a key that does not yet exist at launch time. In that case, validate after the previous Step finishes and before the consuming Step begins.

## 17. Distinguishing Inactive Scope Errors from Missing Parameters

These two errors have different causes:

**Inactive scope**: Spring has no `JobExecution` or `StepExecution` bound to the current thread to resolve the target bean. Typically happens when accessing a scoped bean outside the batch lifecycle or from a thread lacking the right context.

**Missing parameter**: The scope is active, but the accessed key is absent from `JobParameters` or `ExecutionContext`. The expression may return `null` or cause a conversion error if the target demands an incompatible type.

How to diagnose:

1. Determine whether the error occurs during ApplicationContext startup or when the Step runs.
2. Check whether the bean has the right `@JobScope`/`@StepScope`.
3. Check whether the scope is active on the current thread.
4. Print the list of parameter names allowed to be logged, avoiding sensitive values.
5. Compare exact key names between caller and expression.
6. Check whether the parameter was passed in this launch.
7. Check the `JobParameter` type and target Java type.

Do not fix a scope error by adding a default parameter. Likewise, do not fix a missing key by changing threads or scopes if the scope is already working properly.

## 18. Testing Required and Optional Parameters

Test the validator independently:

~~~java
@Test
void rejectsMissingInputFile() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters));
}
~~~

Testing blank values:

~~~java
@Test
void rejectsBlankInputFile() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "   ", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters));
}
~~~

Testing optional parameters:

~~~java
@Test
void acceptsMissingOptionalMode() {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "/data/orders.csv", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    assertDoesNotThrow(
            () -> validator.validate(parameters));
}
~~~

Beyond the validator, test actual scoped beans to confirm:

- Present parameters are injected accurately.
- Missing parameters receive `null` or defaults per design.
- Blank parameters are handled properly.
- Wrong-type parameters produce clear errors.
- Misspelled SpEL keys are caught.
- The Job does not run the Step when a required parameter is missing.

## 19. Testing Default Values in StepScope

Use Spring Batch test support or run the Job with `JobLauncherTestUtils` to activate scopes in the real lifecycle.

Example Job-level test:

~~~java
@Test
void usesDefaultEncodingWhenParameterIsMissing() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", testFile.toString(), true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution execution =
            jobLauncherTestUtils.launchJob(parameters);

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    // Verify reader is created with UTF-8 encoding
}
~~~

To confirm the injected value, inspect reader behavior or a test probe component. Avoid calling bean constructors directly, as that does not test late binding.

Also test when the caller passes an encoding other than `UTF-8` and when `encoding` is a blank string.

## 20. Missing Parameters on Restart

Job restarts typically reuse the same `JobInstance`, identified by Job name and identifying `JobParameters`. On restart, the caller must supply the exact identifying parameters so Spring Batch finds the old `JobInstance`.

If an identifying parameter is missing, `JobLauncher` may find a different `JobInstance` or fail to locate the instance to restart. If a non-identifying parameter is missing or changed, `JobInstance` identity may stay the same, but Job behavior could change.

First run example:

~~~java
JobParameters firstRun = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("encoding", "UTF-8", false)
        .toJobParameters();
~~~

On restart, if `encoding` is omitted and the code uses a different default, the reader may read the file differently from the first run. Thus, even optional parameters need to remain consistent if they affect results.

For defaults that affect outcomes, consider:

- Passing the value explicitly from the start.
- Normalizing `JobParameters` before launch.
- Storing resolved values in `JobExecutionContext`.
- Keeping defaults compatible across application versions.
- Logging/auditing the effective configuration for restart investigations.

## 21. Logging Missing Parameters

Error messages should state which key is missing and whether it is required or optional. Do not log full `JobParameters` if they contain tokens, passwords, or sensitive data.

Example:

~~~java
if (!StringUtils.hasText(inputFile)) {
    log.error("Required JobParameter 'inputFile' is missing");
    throw new JobParametersInvalidException(
            "Required JobParameter 'inputFile' is missing");
}
~~~

For optional parameters, you can log the applied default value:

~~~java
if (!StringUtils.hasText(encoding)) {
    log.info("No encoding supplied; using UTF-8");
    encoding = "UTF-8";
}
~~~

For traceability, log the `JobExecution` ID, Job name, and parameter name. Only log parameter values when data policy permits.

## 22. Common Errors

### Assuming All JobParameters Exist

Unpassed keys may resolve to `null`. Define required vs optional and validate accordingly.

### Using Primitives for Optional Parameters

`int`, `long`, and `boolean` cannot represent `null`. Use `Integer`, `Long`, or `Boolean` when you need to distinguish missing from `0`/`false`.

### Checking Only Null for Strings

Empty or whitespace strings can still be invalid. Use `StringUtils.hasText` or appropriate normalization rules.

### Using Defaults for Parameters Identifying Tenants or Data

The Job may process the wrong scope. Parameters identifying data should be validated as required.

### Confusing Non-Identifying with Optional

Non-identifying parameters can still be passed and injected. The identifying flag only governs `JobInstance` identity.

### Confusing SpEL Defaults with Saved JobParameters

Defaults apply only to the bean at injection time. They do not add keys to `JobParameters` or metadata.

### Misspelling Key Names

Key names are case-sensitive. Use constants and validator tests to catch typos.

### Injecting the Wrong Type

A value may exist, yet conversion fails. Use properly typed `JobParameter` values and validate value ranges.

### Using Property Placeholders Instead of SpEL

`JobParameters` are accessed via SpEL execution context. Property placeholder syntax is for application configuration and has a different meaning.

### Letting Errors Surface Deep Inside a Reader

A missing `inputFile` might only surface when the reader opens the resource. Use `JobParametersValidator` to fail early.

### Changing Defaults Between Restarts

The `JobInstance` may remain the same while behavior changes. Keep effective configuration consistent or persist resolved values.

## 23. Workflow for Handling Missing Parameters

When a bean needs a parameter, determine:

1. Is the key required by business rules?
2. Does the caller always pass the key in `JobParameters`?
3. Can the key exist yet be empty or blank?
4. Does the key participate in identifying the `JobInstance`?
5. Does the `JobParameter` type match the injected Java type?
6. If optional, is the default business-approved?
7. Could the default alter the dataset or outcome on restart?
8. Can the key be validated via `JobParametersValidator` before Steps run?
9. If the key comes from `ExecutionContext`, has the producer Step written and promoted it properly?
10. Do logs clearly name the key without exposing sensitive data?

Missing parameters are a normal scenario that requires deliberate design. For required parameters, `JobParametersValidator` rejects runs early and surfaces clear errors. For optional parameters, use reference types, controlled defaults, and blank/type-conversion checks. Always separate requiredness from identifying flags, because these two attributes solve two different problems: input validation and `JobInstance` identity.
