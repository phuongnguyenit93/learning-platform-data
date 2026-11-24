# Parameter Converter

In Spring Batch, `JobParameters` is the set of input parameters that determines how a `Job` is run and, for identifying parameters, determines which logical `JobInstance` will be used. When parameters come from the command line, a configuration file, or an operations interface, the initial data is usually strings. `JobParametersConverter` converts `Properties`-style data into `JobParameters` with appropriate data types and identifying flags; it can also convert `JobParameters` back into `Properties`.

The parameter converter forms a bridge between the way operators pass parameters and Spring Batch's typed parameter model. As a result, a job can receive a business date, a quantity, a flag, or other data types under a consistent convention, instead of parsing strings itself in every reader, processor, or tasklet.

## What does JobParametersConverter do?

`JobParametersConverter` is an interface in Spring Batch that provides conversion in two directions:

```java
public interface JobParametersConverter {
    JobParameters getJobParameters(Properties properties);

    Properties getProperties(JobParameters parameters);
}
```

The method names make the two directions clear:

- `getJobParameters(Properties)`: reads the input properties and creates `JobParameters`.
- `getProperties(JobParameters)`: represents the existing parameters as `Properties`, which is often useful for displaying, storing, or passing parameters on again.

For example, an operations interface sends the values `businessDate`, `maxRows`, and `requestedBy`. The converter can convert these values into parameters of type `String`, `Long`, and with the corresponding identifying flags. When the job runs, the batch components read the values from `JobParameters` instead of having to know whether the data was originally entered from the CLI, a file, or an API.

The general processing flow:

```text
CLI / file / operations interface
              |
              v
       Properties (String values)
              |
              v
     JobParametersConverter
              |
              v
        JobParameters
              |
              v
        JobLauncher.run(...)
              |
              v
  JobRepository / JobInstance / JobExecution
```

The converter is responsible for representation and type conversion. `JobLauncher` uses `JobParameters` to launch the job; `JobRepository` uses the identifying parameters together with the job name to identify the `JobInstance`.

## DefaultJobParametersConverter

Spring Batch provides `DefaultJobParametersConverter` as the default implementation. This converter supports representing a parameter as a property key and value, where the value can contain data type information and the identifying flag following the syntax used by the Spring Batch version.

With the common syntax of `DefaultJobParametersConverter`, a parameter can be represented as follows:

```text
parameterName=parameterValue,fully.qualified.TypeName,identifying
```

Where:

- `parameterName` is the parameter name.
- `parameterValue` is the string value to convert.
- `fully.qualified.TypeName` is the fully qualified name of the target data type, if the syntax of the version in use requires declaring the type.
- `identifying` indicates whether the parameter takes part in identifying the `JobInstance`.

Illustrative example:

```properties
businessDate=2026-11-15,java.lang.String,true
maxRows=5000,java.lang.Long,false
requestedBy=night-scheduler,java.lang.String,false
```

In this example, `businessDate` is an identifying parameter because it determines the business date to be processed. `maxRows` and `requestedBy` are non-identifying on the assumption that changing an operational limit or the person who launches the job does not create a new logical job. The identifying decision must be based on actual business needs, not just on the data type.

The specific format and the set of convertible data types depend on the Spring Batch version and the configured `ConversionService`. When using this syntax in the command line or a properties file, check the documentation for your project's exact version; do not assume every version supports the same types or the same default rules.

### Converting Properties to JobParameters

Example of using the converter directly:

```java
Properties properties = new Properties();
properties.setProperty(
        "businessDate",
        "2026-11-15,java.lang.String,true");
properties.setProperty(
        "maxRows",
        "5000,java.lang.Long,false");
properties.setProperty(
        "requestedBy",
        "night-scheduler,java.lang.String,false");

JobParametersConverter converter = new DefaultJobParametersConverter();
JobParameters parameters = converter.getJobParameters(properties);
```

After conversion, the job receives typed values:

```java
String businessDate = parameters.getString("businessDate");
Long maxRows = parameters.getLong("maxRows");
String requestedBy = parameters.getString("requestedBy");
```

`JobParameters` stores the value together with the data type and the identifying flag. As a result, batch components can access the parameter in the desired type and the repository has enough information to identify the instance.

### Converting JobParameters to Properties

The reverse direction is useful when you need to display or pass on a parameter set that has been created:

```java
Properties properties = converter.getProperties(parameters);
properties.forEach((name, value) ->
        System.out.println(name + "=" + value));
```

The resulting representation depends on the implementation and version. With the default converter, the type and identifying information is represented in a format the converter can read back. If the application defines its own converter, the two methods must be designed to be compatible: data produced by `getProperties` must be readable by `getJobParameters` without changing the type or the identifying flag.

## How do the converter and JobParametersBuilder differ?

Both tools create `JobParameters`, but they serve two different ways of entering data.

| Tool | Input | Suitable usage |
| --- | --- | --- |
| `JobParametersConverter` | `Properties`, usually with string values | Converting parameters from the CLI, a configuration file, or an operations interface |
| `JobParametersBuilder` | Already-typed Java values | Creating parameters directly in application code |
| `JobParametersValidator` | An already-created `JobParameters` set | Checking validity and business rules before processing |
| `JobParametersIncrementer` | The current parameter set or the initial state | Creating the next parameter set, commonly used when a new instance is needed |

For example, when a service receives a `LocalDate` from a request already parsed by the web framework, you can use `JobParametersBuilder` to create the parameter. If a batch operator enters `businessDate=2026-11-15` via the CLI, the converter is better suited to turning the string into Spring Batch's parameter model.

The converter does not replace the validator. A date string can be converted to a `String` successfully but still be invalid from a business standpoint, for example a date outside the period allowed for settlement. Checking conditions such as the date range, the existence of the source file, or the permission to run the job is the responsibility of the validator or the business layer.

## Data types and ConversionService

Typed parameters help the job avoid parsing strings in many places. Commonly used types include `String`, `Long`, `Double`, and date types supported by the Spring Batch version or the configured conversion service.

Example of choosing types:

| Business value | Suggested parameter type | Reason |
| --- | --- | --- |
| Processing date `2026-11-15` | `String` in ISO format or a supported date type | Represents the date clearly and is easy to pass via the CLI |
| Maximum record count `5000` | `Long` | Can be used directly as an integer |
| Ratio threshold `0.95` | `Double` | Suits a decimal value when business precision allows |
| Customer code `000123` | `String` | Preserves the leading zeros, avoiding being interpreted as a number |
| Run mode `dry-run` | `String` or an enum via a dedicated converter | Converts into a controlled business choice |

Do not convert an identifier into a number just because it contains digits. For example, `000123` converted to `Long` loses the leading zeros. Also be careful when using `Double` for currency or numbers that need decimal precision; in those cases you should usually use an appropriate decimal representation or a string with clear parsing rules.

### Date types

For a business date, use a stable format such as ISO-8601, for example `2026-11-15`. If the default converter in your project's version does not directly support the `LocalDate` type, you can keep the parameter as a `String` and parse it once in the configuration layer/validator, or provide a custom converter to convert it to `LocalDate`.

For timestamps, you need to specify the time zone and format clearly. A value such as `2026-11-15T09:30:00` carries no offset, so it can be interpreted differently in different environments. If the instant must be consistent across nodes, pass a timestamp with an offset or normalize to UTC.

### Registering a custom type conversion

If you need a data type that the default converter does not support, you can extend the `ConversionService` that `DefaultJobParametersConverter` uses (the specific configuration API depends on the version). Another approach is to implement your own `JobParametersConverter` to fully control the syntax and conversion rules.

Example of the idea of converting an ISO date value into `LocalDate` in a custom converter:

```java
LocalDate businessDate = LocalDate.parse(dateText);
```

At the step of building `JobParameters`, Spring Batch versions that support custom-typed parameters can store `LocalDate` directly together with the identifying flag. If the project uses a version that supports only a fixed set of types, keep the parameter as a `String` or use a type that version supports; do not assume that parsing in just one place means every metadata API can store the new type.

## Implementing your own JobParametersConverter

When the application's input format differs from the default syntax, you can implement the `JobParametersConverter` interface. For example, a system allows only two known parameters: `businessDate` and `maxRows`. The converter below shows how to control the parameter schema explicitly.

```java
public class SettlementParametersConverter implements JobParametersConverter {

    @Override
    public JobParameters getJobParameters(Properties properties) {
        JobParametersBuilder builder = new JobParametersBuilder();

        String businessDate = properties.getProperty("businessDate");
        if (businessDate != null && !businessDate.isBlank()) {
            builder.addString("businessDate", businessDate, true);
        }

        String maxRows = properties.getProperty("maxRows");
        if (maxRows != null && !maxRows.isBlank()) {
            builder.addLong("maxRows", Long.valueOf(maxRows), false);
        }

        return builder.toJobParameters();
    }

    @Override
    public Properties getProperties(JobParameters parameters) {
        Properties properties = new Properties();

        JobParameter<?> businessDate =
                parameters.getParameters().get("businessDate");
        if (businessDate != null) {
            properties.setProperty(
                    "businessDate",
                    businessDate.getValue().toString());
        }

        JobParameter<?> maxRows = parameters.getParameters().get("maxRows");
        if (maxRows != null) {
            properties.setProperty("maxRows", maxRows.getValue().toString());
        }

        return properties;
    }
}
```

This is a converter following the example's fixed schema: `businessDate` is always an identifying `String`, while `maxRows` is always a non-identifying `Long`. The `getProperties` method returns the values as strings under the exact property names. When extending the converter to many parameters, you need to decide clearly how to handle unknown properties, empty values, wrong types, the identifying flag, and preserving information in two-way conversion.

In real code, you need to add error handling with clear messages. For example, `maxRows=abc` will cause a `Long` parse error; map that error to an understandable parameter error so the operator knows the property name and the required format. Do not silently replace a wrong value with `0` or a default that could change the processing scope.

### Rules for designing a custom converter

- Clearly define the supported property names and data types.
- Set the identifying flag according to business meaning.
- Use date, number, and boolean formats that are stable across environments.
- Decide clearly whether to reject unknown properties or ignore them.
- Preserve the necessary information when converting `JobParameters` back to `Properties`.
- Do not write secret information into logs or into parameter representations that may be displayed to operators.
- Write understandable parse errors that identify the property and the expected format.

## Using the converter with the job launch mechanism

The converter is only used when the launching component needs to convert `Properties`-style input into `JobParameters`. Launchers or runners that receive parameters from the command line usually have a configuration point for the converter. The application can also call the converter directly before calling `JobLauncher`.

Example of manual integration:

```java
Properties input = new Properties();
input.setProperty("businessDate", "2026-11-15");
input.setProperty("maxRows", "5000");

JobParametersConverter converter = new SettlementParametersConverter();
JobParameters parameters = converter.getJobParameters(input);

JobExecution execution = jobLauncher.run(settlementJob, parameters);
```

In this case, the service clearly controls the property source and the converter. If you use `CommandLineJobRunner`, the Spring Boot runner, or another infrastructure launcher, configure the converter at the extension point that version provides. The auto-configuration mechanism and bean names may differ between versions; do not assume that merely declaring an arbitrary bean means every runner will automatically use it.

When calling `JobLauncher.run(job, parameters)` with `JobParameters` created directly by `JobParametersBuilder`, the converter does not run again automatically. The two ways of creating parameters are separate choices depending on the input source.

## Identifying parameters and the JobInstance identity

The converter can assign an identifying flag to each parameter. This flag directly affects how the `JobRepository` identifies the `JobInstance`.

Example:

```properties
businessDate=2026-11-15,java.lang.String,true
requestedBy=operator-01,java.lang.String,false
```

Two launches of the same job with `businessDate=2026-11-15` but different `requestedBy` still have the same `JobInstance` identity, if `requestedBy` is non-identifying. If `businessDate` changes, Spring Batch treats it as a different logical job.

Marking incorrectly can cause two kinds of problems:

- Marking an operational parameter as identifying makes each new value create an unintended new `JobInstance`. For example, adding a new timestamp on every retry can make the new run no longer a restart of the old instance.
- Marking a business parameter as non-identifying makes two requests that process different data be treated as the same logical job. This can cause conflicts during concurrent runs or restart.

The converter should focus on converting data according to convention. The identifying rules need to be agreed with the business design and the job's restart flow.

## The converter does not replace JobParametersValidator

A successful conversion only indicates the data can be represented as a parameter type. It does not guarantee the value is appropriate for the business.

For example, `maxRows=0` can parse into a valid `Long` but the job does not allow a limit of 0. `businessDate=2099-01-01` can be correctly formatted but lie outside the data period the system allows. These conditions need to be checked with `JobParametersValidator` or the business layer before the job processes.

Validator example:

```java
public class SettlementParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String businessDate = parameters.getString("businessDate");
        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        Long maxRows = parameters.getLong("maxRows");
        if (maxRows != null && maxRows <= 0) {
            throw new JobParametersInvalidException(
                    "maxRows must be greater than zero");
        }
    }
}
```

The validator checks business rules on the already-created `JobParameters`. The converter handles syntax, data types, and the identifying flag. Separating the two responsibilities lets format errors and business errors be handled clearly.

## Common errors when converting parameters

### Cannot convert the data type

The input value does not match the declared type, for example `maxRows=abc` but the target type is `Long`. Check the format, the fully qualified type name, and the `ConversionService`'s ability to convert.

### Missing required parameter

The property is absent from the input or its name is misspelled. The converter can produce a parameter set missing a value if the design allows it; the validator should detect a required parameter that was not provided and report a specific error.

### Values containing commas or special characters

If the converter syntax uses commas to separate the value, type, and identifying flag, a value containing a comma can be parsed incorrectly without a supported escape mechanism. Use the prescribed format, avoid arbitrarily concatenating strings, or write your own converter with clear escaping rules.

### Wrong identifying flag

A parameter unintentionally marked identifying can create a new instance on every call. Check the parameter representation, the converter's identifying default, and how the `JobParameters` is created.

### Incompatible two-way conversion

The converter reads one format but `getProperties` outputs another format or drops the type/identifying flag. When a round-trip is needed, ensure the output representation can be read back without changing the parameter's meaning.

### Changing the parameter type between deployments

If a job has stored metadata with an old parameter type and then the application changes the converter to a new type, you need to assess the ability to read old executions and the instance identity. Maintain a compatible convention or have a migration plan; do not change an identifying type arbitrarily between deployments.

### Exposure of sensitive data

Parameters passed on the command line can appear in the process list, shell history, or logs depending on the environment. Do not pass passwords, access tokens, or secrets directly through job parameters. Pass a safe reference identifier to a secret manager or protected configuration instead.

## Testing the converter

The converter is a component that converts input data, so it can be tested independently without running the entire job.

Basic test example with JUnit:

```java
@Test
void convertsPropertiesToTypedJobParameters() {
    Properties properties = new Properties();
    properties.setProperty("businessDate", "2026-11-15");
    properties.setProperty("maxRows", "5000");

    JobParametersConverter converter = new SettlementParametersConverter();
    JobParameters parameters = converter.getJobParameters(properties);

    assertEquals("2026-11-15", parameters.getString("businessDate"));
    assertEquals(5000L, parameters.getLong("maxRows"));
    assertTrue(parameters.getParameters().get("businessDate").isIdentifying());
    assertFalse(parameters.getParameters().get("maxRows").isIdentifying());
}
```

You should also test these cases:

- A property is absent or has an empty value.
- A numeric value is invalid or exceeds limits.
- An unsupported property.
- A data type with no corresponding converter.
- The identifying flag is preserved in two-way conversion.
- A date value with an invalid format or timezone.
- A value containing a separator or special characters under the chosen syntax.

With the default converter, tests need to use the syntax and types supported by your project's exact Spring Batch version. With a custom converter, testing the two-way contract helps avoid unintended changes when modifying the input format.

## Suggestions for choosing a conversion approach

| Parameter source | Approach |
| --- | --- |
| A Java service that already has strongly typed values | Use `JobParametersBuilder` |
| CLI or properties file using the standard syntax | Use `DefaultJobParametersConverter` |
| An API that receives JSON with its own schema | Parse and validate the request, then use the builder or a dedicated converter |
| Need a custom business type | Extend `ConversionService` or implement `JobParametersConverter` |
| Need to check values against business rules | Use `JobParametersValidator` after conversion |

Choose the default converter when its syntax and data types meet your needs. Implement your own converter only when you need a different input convention, alias mapping, a specialized data type, or strict control over the parameter schema. The simpler and more stable the converter, the easier operation, restart, and user support become.

## Takeaways

`JobParametersConverter` converts between `Properties` and `JobParameters`. `DefaultJobParametersConverter` meets common parameter syntax, while a custom converter lets you control data types, property names, and the identifying flag according to the application's conventions. The converter handles representation and type conversion; `JobParametersValidator` checks business validity; `JobParametersBuilder` suits creating parameters directly from Java code. Keep formats stable, preserve the identifying flag, test two-way conversion, and avoid passing secrets via command-line parameters.
