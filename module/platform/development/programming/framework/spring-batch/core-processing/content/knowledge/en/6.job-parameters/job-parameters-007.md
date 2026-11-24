# Parameter Validation in Spring Batch

**JobParameters** is the input data passed when launching a Job. They typically identify the batch to process, such as a business date, a file path, a customer code, or a data range. Before the Job executes its Steps, the application needs to confirm that these parameters are complete, of the correct type, in the correct format, and consistent with business rules.

Spring Batch provides the **JobParametersValidator** mechanism to validate parameters at the Job level. A validator lets you reject a run as soon as the input is invalid, before the Job enters the data processing flow. This lesson covers how to validate required parameters, optional parameters, types, and values, how to attach a validator to a Job, and how to test and handle parameters on restart.

## 1. What are JobParameters?

JobParameters is a collection of name/value pairs passed to a Job when it is launched. For example, a customer data import Job might receive:

| Parameter name | Example | Purpose |
|---|---|---|
| **inputFile** | **data/customers.csv** | The file to import |
| **businessDate** | **2026-11-15** | The business date of the batch |
| **region** | **APAC** | The regional scope |
| **maxRows** | **50000** | A limit on the number of rows processed |
| **dryRun** | **true** | A trial run in a mode that does not write official data |

These parameters are used to configure the work at run time. They allow the same Job definition to process many different files, dates, or data ranges.

JobParameters are the Job's input data, not the data of each item. For example:

- **businessDate** is a parameter of the whole run.
- The customer code in each CSV row is item data.
- The rule that validates **businessDate** falls within the scope of JobParameters validation.
- The rule that validates the customer code on each row belongs to item processing, usually in an ItemProcessor or a data validation component.

### JobParameters and JobInstance

Spring Batch uses the Job name together with the **identifying JobParameters** to identify a JobInstance. A JobInstance represents a logical processing run, for example importing data for one business date.

A JobInstance can have multiple JobExecutions if the first run fails and is later restarted. Restarts use the same set of identifying parameters to continue the existing instance.

~~~mermaid
flowchart TD
    A["Job name + identifying JobParameters"] --> B["JobInstance"]
    B --> C["JobExecution 1st run"]
    B --> D["JobExecution on restart"]
    B --> E["Next JobExecution"]
~~~

This means that the choice of which parameters are identifying directly affects how Spring Batch recognizes a run. The validator checks the validity of values; the identifying flag determines whether a value takes part in identifying the JobInstance.

## 2. Why validate JobParameters?

If a Job runs with missing or wrong parameters, the error may only appear when a Step starts reading a file, querying the database, or writing data. By then, the system has already created metadata and may have performed part of the work before the problem is detected.

Parameter validation helps detect input errors earlier.

For example, an import Job requires **inputFile** and **businessDate**. If **inputFile** is missing, the reader may fail when opening the resource. If **businessDate** is in the wrong format, the processor or the query may fail when converting the value.

A Job-level validator can check conditions before the Steps begin:

- Required parameters must be present.
- Parameter names must be within the allowed set.
- Values must not be empty or contain only whitespace.
- Values must have the correct format.
- Numeric values must be within limits.
- The start date must not be after the end date.
- Related parameters must be provided together.
- The processing mode must be in the supported list.

As a result, input errors are reported with a clear message and are not confused with data read errors or infrastructure errors.

## 3. The JobParametersValidator mechanism

Spring Batch defines the **JobParametersValidator** interface:

~~~java
public interface JobParametersValidator {
    void validate(JobParameters parameters)
        throws JobParametersInvalidException;
}
~~~

The validator receives the **JobParameters** and checks the entire set of parameters. If the parameters are valid, the method ends normally. If not, the validator throws a **JobParametersInvalidException** with explanatory information.

A simple validator example:

~~~java
public class RequiredInputValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "The inputFile parameter is required."
            );
        }
    }
}
~~~

This validator requires the **inputFile** parameter to exist and have content. When the condition is not met, the Job is rejected with an invalid-parameter error.

### Where is the validator called?

The validator is attached to the Job. Spring Batch performs the parameter validation at the Job level before the Step flow begins processing. This makes it the right place to check input conditions common to the whole Job.

~~~mermaid
flowchart TD
    A["Receive JobParameters"] --> B["JobParametersValidator"]
    B --> C{"Parameters valid?"}
    C -- "No" --> D["JobParametersInvalidException"]
    C -- "Yes" --> E["Start Job flow"]
    E --> F["Step 1"]
    F --> G["Next Step"]
~~~

If the validator throws an exception, the Job does not enter the Steps in the normal flow. The application can catch the error where the Job is called to return an appropriate message to the user or the scheduling system.

A validator does not fix values by itself, add missing parameters, or modify JobParameters. Normalize and supply default values in the layer that creates the parameters or before calling the Job, if the business allows it.

## 4. Validating required and optional parameters with DefaultJobParametersValidator

For simple rules about parameter names, Spring Batch provides **DefaultJobParametersValidator**.

This validator lets you declare:

- **Required keys:** parameter names that must be present.
- **Optional keys:** parameter names that are allowed but not required.

For example, a Job needs **inputFile** and **businessDate**, and also allows **region** and **maxRows**:

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] {
            "inputFile",
            "businessDate"
        },
        new String[] {
            "region",
            "maxRows"
        }
    );
}
~~~

Attach the validator to the Job:

~~~java
@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importCustomersJob", jobRepository)
        .validator(importParametersValidator)
        .start(importCustomersStep)
        .build();
}
~~~

With the configuration above:

| Parameter set received | Result |
|---|---|
| **inputFile**, **businessDate** | Valid in terms of names and presence |
| With **region** added | Allowed |
| With **maxRows** added | Allowed |
| Missing **inputFile** | Invalid |
| Missing **businessDate** | Invalid |
| Has **unexpectedKey** | Invalid because it is not in the allowed list |

**DefaultJobParametersValidator** suits cases where you need to check the set of parameter names and their presence. It does not check complex business rules such as whether a date is in the correct format, whether a quantity is greater than zero, whether a file is readable, or whether two dates are in the right order.

If a Job has both name rules and value rules, use a custom validator or combine the checks in a dedicated validator class.

## 5. Writing a custom validator for business rules

A custom validator implements **JobParametersValidator** and checks specific values. For example, an import Job requires:

- **inputFile:** the input file path, must not be empty.
- **businessDate:** a date in ISO format **yyyy-MM-dd**.
- **mode:** accepts only **FULL** or **DELTA**.
- **maxRows:** if provided, it must be greater than 0.

~~~java
public class CustomerImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        String businessDate = parameters.getString("businessDate");
        String mode = parameters.getString("mode");
        Long maxRows = parameters.getLong("maxRows");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "inputFile must not be empty."
            );
        }

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                "businessDate is a required parameter."
            );
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "businessDate must use the format yyyy-MM-dd."
            );
        }

        if (mode != null
                && !mode.equals("FULL")
                && !mode.equals("DELTA")) {
            throw new JobParametersInvalidException(
                "mode accepts only FULL or DELTA."
            );
        }

        if (maxRows != null && maxRows <= 0) {
            throw new JobParametersInvalidException(
                "maxRows must be greater than 0."
            );
        }
    }
}
~~~

Register the validator as a bean:

~~~java
@Bean
JobParametersValidator customerImportParametersValidator() {
    return new CustomerImportParametersValidator();
}
~~~

Then attach it to the Job with **.validator(...)** as in the previous example.

### Why check each condition?

**Presence check**

**getString("inputFile")** returns **null** when the parameter is absent. Also check **isBlank()** to reject empty strings or strings containing only whitespace.

**Format check**

**LocalDate.parse(...)** validates the date in the default ISO format. Values such as **15/11/2026** or **2026-13-40** are not accepted in this example.

**Value domain check**

**mode** accepts only the two supported business values. This prevents an arbitrary value from going deep into the Steps and producing undefined behavior.

**Limit check**

**maxRows** is an optional parameter. If present, the value must be greater than 0. If absent, the Job can use a default limit configured in another component.

### Combine multiple errors or stop at the first error?

The example above throws an exception as soon as it hits the first failing condition. This approach is simple and suits many Jobs.

If you want to report multiple errors at once, the validator can collect the messages into a list and then throw a single **JobParametersInvalidException** containing all the results. This lets the caller fix multiple parameters in one go, but the messages must be clear and must not reveal sensitive data.

## 6. Validating parameters in relation to each other

Many rules cannot be checked by looking at each parameter independently. For example:

- **fromDate** must be less than or equal to **toDate**.
- **region** is required when **mode** is **REGIONAL**.
- **maxRows** may only be used when **dryRun** is on.
- **inputFile** and **sourceSystem** must be present together.
- Only one of **customerId** or **allCustomers** is allowed.

A custom validator can check these relationships:

~~~java
public class DateRangeParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String fromValue = parameters.getString("fromDate");
        String toValue = parameters.getString("toDate");

        if (fromValue == null || toValue == null) {
            throw new JobParametersInvalidException(
                "Both fromDate and toDate must be provided."
            );
        }

        final LocalDate fromDate;
        final LocalDate toDate;

        try {
            fromDate = LocalDate.parse(fromValue);
            toDate = LocalDate.parse(toValue);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                "fromDate and toDate must use the format yyyy-MM-dd."
            );
        }

        if (fromDate.isAfter(toDate)) {
            throw new JobParametersInvalidException(
                "fromDate must not be after toDate."
            );
        }
    }
}
~~~

Here, the validator checks presence, format, and ordering relationship. The conditions are placed side by side so readers can understand the Job's input contract.

With many parameters that have complex relationships, split each group of rules into its own method such as **validateDateRange(...)**, **validateMode(...)**, or **validateInputSource(...)**. This makes the validator easier to read and test.

## 7. Distinguishing name, type, and value checks

A JobParameters can contain many kinds of values. You need to distinguish three layers of checking:

| Check layer | Question to answer | Example |
|---|---|---|
| Parameter name | Is it the allowed set of parameters? | Is **inputFile** supported? |
| Data type | Does the value have the required type? | Is **maxRows** a long integer? |
| Value and business | Is the value valid according to the rules? | Is **maxRows** greater than 0? |

**DefaultJobParametersValidator** mainly handles the name and presence layer. A custom validator can read values in the appropriate type and check formats and business rules.

Use appropriate data types when building JobParameters instead of always converting everything to strings. Spring Batch supports standard parameter types such as String, Long, Double, and Date; the JobParameter model also stores the type information along with the identifying flag. When receiving data from external systems, convert it and report an error in the parameter intake layer if a value cannot be converted to the desired type.

Example of building parameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("inputFile", "data/customers.csv", true)
    .addString("businessDate", "2026-11-15", true)
    .addLong("maxRows", 50000L, false)
    .addString("region", "APAC", false)
    .toJobParameters();
~~~

In the example:

- **inputFile** and **businessDate** are marked identifying.
- **maxRows** and **region** do not take part in identifying the JobInstance.
- **toJobParameters()** creates the parameter set used when launching the Job.

The identifying flag must be chosen according to business meaning. If a parameter changes the data unit or the logical result of the run, it may need to be part of the identity. If a parameter only adjusts how the job is operated without creating a new logical piece of work, it may not need to be identifying.

## 8. Identifying parameters and restart

Parameter validation does not replace the JobInstance identification rules. A parameter set can be valid and still not create a new JobInstance if the identifying parameters do not change.

For example, a Job that imports data by day:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("inputFile", "data/customers-20261115.csv", true)
    .addString("notificationEmail", "ops@example.com", false)
    .toJobParameters();
~~~

If a run fails and needs a restart, use the same identifying parameters so Spring Batch finds the right JobInstance. You can change a non-identifying parameter if that fits the design, but you must be sure the change does not alter the processing meaning or cause discrepancies on restart.

Some principles:

- Use identifying parameters to identify the batch or the logical unit of work.
- Keep the identifying parameters unchanged when restarting a failed or stopped JobInstance.
- Create a new identifying parameter only when you truly want to create a new JobInstance.
- Do not add a new timestamp or UUID to the identifying parameters on each restart attempt.
- If an operational parameter is non-identifying but affects the business result, reconsider the identity design.

For example, if each run adds an identifying timestamp, a restart becomes a new JobInstance. The Job may start over from the beginning instead of recovering the previous instance's checkpoint.

The validator should check the parameters needed for the Job's logic, while the decision of whether to restart or create a new instance belongs to how the JobParameters are built and to the JobRepository mechanism.

## 9. Default values and parameter normalization

Not every parameter requires the caller to provide it. Some parameters can have default values, for example:

- **mode** defaults to **FULL**.
- **maxRows** defaults to 100000.
- **region** defaults to the region configured for the tenant.
- **dryRun** defaults to **false**.

There are two common ways to handle this:

**Approach 1: add default values before creating JobParameters.**

The layer that receives the request or the Job launch service can normalize the input, add default values, and then create the JobParameters. The validator receives the normalized parameter set.

**Approach 2: handle missing values in the component that uses the parameter.**

If a parameter is optional, the validator can accept a **null** value, while a Step or a configuration bean can use the default value.

Do not let several components each pick different default values. Designate one place responsible for normalization so the Job's behavior is consistent across launch methods.

Example of handling defaults in the validator:

~~~java
String mode = parameters.getString("mode");

if (mode != null
        && !mode.equals("FULL")
        && !mode.equals("DELTA")) {
    throw new JobParametersInvalidException(
        "mode accepts only FULL or DELTA."
    );
}
~~~

In this case, **null** is accepted and the executing component can interpret it as **FULL**. If you want the default value to appear explicitly in the metadata and to matter for identification, add it to the JobParameters before launching instead of leaving it implicit in the Step.

## 10. Parameter validation and checking input resources

A parameter can have the correct format while the resource it points to does not exist or is not accessible.

For example, **inputFile** can be a valid string but the file has been deleted. You can check the file's existence and read permission in the validator:

~~~java
String inputFile = parameters.getString("inputFile");

if (inputFile == null || inputFile.isBlank()) {
    throw new JobParametersInvalidException(
        "inputFile is required."
    );
}

try {
    Path path = Path.of(inputFile);

    if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
        throw new JobParametersInvalidException(
            "The input file does not exist or is not readable."
        );
    }
} catch (InvalidPathException ex) {
    throw new JobParametersInvalidException(
        "inputFile is not a valid path."
    );
}
~~~

However, you need to distinguish two groups of checks:

- **Parameter validation:** the value is present, correctly formatted, and satisfies the input contract.
- **Resource validation:** whether the file, database, API, or source system is ready at execution time.

Resource validation in a validator can be useful for simple local files. For remote sources, network checks, or large queries, do not make the validator too slow or give it side effects. A resource can change state between the time of validation and when a Step actually uses it.

You can organize an input preparation Step for deeper checks:

1. The validator confirms required parameters and format.
2. A Step checks the file, access permission, schema, or source state.
3. The data import Step starts only when the resource check succeeds.

This split lets the validator keep the responsibility of checking the parameter contract, while the Step is responsible for checking execution conditions.

## 11. Reading JobParameters in a Step

After the parameters have been validated, components in a Step can use them. For beans that need values at run time, Spring Batch provides **@StepScope** and late binding.

Example of a reader receiving a file path:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .build();
}
~~~

When the Step starts, Spring Batch creates the bean in scope and injects the **inputFile** value from JobParameters. The validator has already checked that this parameter is present and non-empty before the Step enters processing.

You can read other parameters in a similar way:

~~~java
@Value("#{jobParameters['businessDate']}")
String businessDate
~~~

Do not use **@StepScope** merely to replace every bean configuration. Use it only when the bean needs access to JobParameters, StepExecutionContext, or JobExecutionContext at runtime.

The Job-level validator should check the parameters before they are used in beans with late binding. This helps avoid confusing errors when a bean is created and the parameter does not exist.

## 12. Combining the default validator and custom rules

In a real Job, you may need both a check of the parameter name set and a check of the values. You can create a validator that coordinates the two parts:

~~~java
public class CombinedImportParametersValidator
        implements JobParametersValidator {

    private final JobParametersValidator keysValidator =
        new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"mode", "maxRows"}
        );

    private final JobParametersValidator valuesValidator =
        new CustomerImportParametersValidator();

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        keysValidator.validate(parameters);
        valuesValidator.validate(parameters);
    }
}
~~~

Then attach **CombinedImportParametersValidator** to the Job.

The order of checks is meaningful: check the name set and presence first, and only then read and check the values. If a required parameter is missing, the error is reported right at the first step.

With a combined validator, make sure the custom validator correctly handles the case where an optional parameter is absent. Avoid assuming a parameter always exists if it is not declared as required.

## 13. Validation error messages

Error messages should help operators know which parameter to fix and why. Avoid overly generic messages such as **Invalid parameters** if you can state the specific condition.

Example:

| Situation | Suitable message |
|---|---|
| Missing **inputFile** | **inputFile is a required parameter.** |
| Date in the wrong format | **businessDate must use the format yyyy-MM-dd.** |
| Unsupported **mode** | **mode accepts only FULL or DELTA.** |
| **maxRows** equals 0 | **maxRows must be greater than 0.** |
| One end of the date range is missing | **Both fromDate and toDate must be provided.** |
| Invalid date range | **fromDate must not be after toDate.** |

Do not put all parameter values into logs by default. Some parameters may contain personal information, tokens, sensitive paths, or internal reference codes. Log the parameter name and the cause, and mask or remove sensitive values.

In the Job launch layer, you can catch **JobParametersInvalidException** to convert it into an appropriate response:

~~~java
try {
    jobLauncher.run(importCustomersJob, parameters);
} catch (JobParametersInvalidException ex) {
    // Return the input error to the caller or record the invalid request.
    throw ex;
}
~~~

This is an example illustrating the error-handling boundary. How to return an HTTP status, write logs, or report the error to the scheduler depends on the application calling the Job.

## 14. Testing JobParametersValidator

A validator is an independent Java component, so it can be tested without running the entire Job. You should have cases for valid input, missing parameters, wrong format, wrong value domain, and wrong relationships between parameters.

Example of testing a custom validator with JUnit:

~~~java
class CustomerImportParametersValidatorTest {

    private final CustomerImportParametersValidator validator =
        new CustomerImportParametersValidator();

    @Test
    void acceptsValidParameters() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "2026-11-15")
            .addString("mode", "FULL")
            .addLong("maxRows", 1000L)
            .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(parameters));
    }

    @Test
    void rejectsMissingInputFile() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }

    @Test
    void rejectsInvalidBusinessDate() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "15/11/2026")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }

    @Test
    void rejectsUnsupportedMode() {
        JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "data/customers.csv")
            .addString("businessDate", "2026-11-15")
            .addString("mode", "UNKNOWN")
            .toJobParameters();

        assertThrows(
            JobParametersInvalidException.class,
            () -> validator.validate(parameters)
        );
    }
}
~~~

The tests above focus on the input contract. With **DefaultJobParametersValidator**, you should also test:

- All required keys present.
- Each required key missing in turn.
- Only optional keys present.
- A key outside the required and optional lists.
- Invalid required/optional configuration.

Besides testing the validator on its own, you need integration tests to confirm the Job actually uses the configured validator. A correctly written validator that is not attached to the Job will not protect the launch flow.

### Testing at the Job level

You can use Spring Batch's test utilities or launch the Job in a test context to confirm:

- Valid parameters let the Job enter the Step.
- Invalid parameters cause the Job to be rejected before a Step processes data.
- Identifying parameters create the correct JobInstance.
- The same identifying parameters can be used on restart depending on the instance state.
- Non-identifying parameters do not accidentally create a new JobInstance.

Do not only check the exception. Confirm that the Step is not executed when validation fails, for example with a listener, a mock, or the state of the output data.

## 15. Common design mistakes

### Not attaching the validator to the Job

Creating a class that implements **JobParametersValidator** does not mean Spring Batch automatically uses it. You must attach the validator to the Job with **.validator(...)** or the corresponding configuration.

### Only validating parameters in the reader

If you check required parameters inside the reader, the Job can start and part of the Step lifecycle has already occurred before the error is detected. General input conditions should be checked at the Job level.

### Using DefaultJobParametersValidator to validate values

The default validator mainly checks the names of required and optional parameters. It does not replace a custom validator for date formats, numeric limits, or relationships between parameters.

### Treating a non-empty string as a valid value

A string can have content but be in the wrong format or have no business meaning. For example, **businessDate=tomorrow** is not a valid ISO date. You need to check both format and value domain.

### Making every parameter identifying

If every run adds an identifying timestamp or UUID, Spring Batch will create a new JobInstance instead of restarting the old instance. Only mark parameters as identifying if they truly identify the logical unit of work.

### Making a result-affecting parameter non-identifying without consideration

If two runs share the same JobInstance but **mode** or **inputFile** changes in a way that changes the data to be processed, a restart can continue with different input than the original run. You need to choose a suitable identity and keep the parameters consistent throughout the JobInstance lifecycle.

### A validator that performs side effects

Do not let a validator write business data, send notifications, or change the state of the source. A validator should check and reject input. Side effects belong to dedicated Steps or services.

### A validator that is too slow or depends on an unstable service

If a validator calls many APIs or runs large queries, the Job launch time can increase and infrastructure errors get mistaken for parameter errors. Keep Job-level checks fast and deterministic; move in-depth resource checks into a preparation Step where appropriate.

### Error messages that leak data

Do not log every JobParameters verbatim. Protect tokens, personal information, sensitive paths, and internal data.

## 16. Process for building parameter validation

When adding validation to a new Job, you can follow this sequence:

1. **List the parameters:** clearly record the name, type, meaning, and which parameters are required.
2. **Determine identity:** decide which parameters take part in identifying the JobInstance.
3. **Define valid values:** date formats, numeric domains, enum lists, and limits.
4. **Define relationships:** rules between parameters such as date ranges or processing modes.
5. **Choose validators:** use DefaultJobParametersValidator for required/optional keys and a custom validator for value rules.
6. **Attach the validator to the Job:** configure **.validator(...)** in the JobBuilder.
7. **Normalize defaults:** handle default values in one consistent place before launching.
8. **Test:** check the valid, missing, wrong-format, wrong-relationship, and restart cases.
9. **Observe errors:** ensure messages are clear and do not expose sensitive data.

A parameter contract table can help development and operations teams agree on how to call the Job:

| Parameter | Type | Required | Identifying | Rule |
|---|---|---:|---:|---|
| **inputFile** | String | Yes | Yes | A valid input path or source code |
| **businessDate** | String | Yes | Yes | An ISO date **yyyy-MM-dd** |
| **mode** | String | No | Depends on the business | **FULL** or **DELTA** |
| **maxRows** | Long | No | Usually no | Greater than 0 |
| **notificationEmail** | String | No | No | A valid email address if present |

This table is an example. Each Job needs to define its parameter contract according to its own business, restart approach, and how external systems launch the Job.

## 17. Key points to remember

- JobParameters are the input data set of one Job run.
- JobParametersValidator checks parameters at the Job level before the Step flow begins.
- **DefaultJobParametersValidator** checks required keys and optional keys.
- A custom validator checks format, type, value domain, and relationships between parameters.
- The validator throws **JobParametersInvalidException** when the input is invalid.
- You must attach the validator to the Job with **.validator(...)** for Spring Batch to use it.
- Identifying parameters determine the JobInstance; they must be consistent on restart.
- Default values should be normalized in one consistent place.
- Parameter validation is different from resource checking and per-item validation.
- A validator should be fast, deterministic, free of side effects, and must not leak sensitive data.
- Test the validator on its own and also run integration tests to ensure the Job actually applies the rules.

Parameter validation ensures a Job starts only when the input meets the defined contract. With correct checks at the Job level and a consistent design of identifying parameters, a Spring Batch application will have fewer late-surfacing errors, be easier to operate, and support more reliable restart.

