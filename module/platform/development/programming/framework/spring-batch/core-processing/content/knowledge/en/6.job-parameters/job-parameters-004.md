# Input Parameters from the Command Line

Spring Batch lets you pass input data to a Job right when launching the application from the command line. These values are converted into `JobParameters` and accompany the Job's run. They can identify the unit of work to process, for example a business date, a data batch ID, or an input file path.

For example, a Job that aggregates revenue by day can be run with the `businessDate` parameter:

```bash
java -jar daily-sales-batch.jar businessDate=2026-11-15
```

In a Spring Boot application with Spring Batch configured to launch Jobs automatically, arguments in the form `key=value` are converted into JobParameters by `JobLauncherApplicationRunner`. For an application that manages launching itself, you can read the arguments via `ApplicationRunner` or `CommandLineRunner`, and then create `JobParameters` with `JobParametersBuilder`.

## 1. What are command line parameters?

Command line parameters are values that an operator or a scheduling system passes in when invoking the Java process. For example:

```bash
java -jar daily-sales-batch.jar businessDate=2026-11-15 regionId=12
```

Here:

- `businessDate=2026-11-15` indicates the date of the data to aggregate.
- `regionId=12` indicates the region to process.

When converted into `JobParameters`, these values become input data attached to a Job launch. Spring Batch stores the JobParameters metadata in the `JobRepository`, which makes it possible to identify the JobInstance and look up execution history.

Do not confuse application parameters with Job parameters. For example, `--spring.batch.job.name=dailySalesJob` is a Spring Boot configuration option for choosing the Job to run; `businessDate=2026-11-15` is a JobParameter passed to the Job.

## 2. Passing JobParameters in a Spring Boot application

For a Spring Boot application with Spring Batch auto-configuration, `JobLauncherApplicationRunner` can launch the Job automatically when the application starts. Arguments in the form `key=value` are converted into JobParameters.

Example of running a JAR file:

```bash
java -jar target/daily-sales-batch.jar businessDate=2026-11-15
```

If the application has multiple Jobs, you can specify the Job to run with the `spring.batch.job.name` property:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15
```

In the command above, the two groups of arguments serve different purposes:

| Argument | Role |
|---|---|
| `--spring.batch.job.name=dailySalesJob` | A Spring Boot property that selects the Job to be launched. |
| `businessDate=2026-11-15` | A JobParameter passed into the Job. |

An example with multiple JobParameters:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12 \
    requestedBy=scheduler
```

When the application starts, Spring Boot reads the configuration properties, selects the Job, and converts the appropriate Job arguments into `JobParameters`. The Job is then launched through the `JobLauncher`.

### Distinguishing configuration options from JobParameters

Typically, Spring Boot configuration options have the `--` prefix, while a JobParameter under the default syntax is written as `key=value`:

```bash
java -jar app.jar \
    --spring.batch.job.name=customerImportJob \
    inputFile=/data/customers.csv \
    importDate=2026-11-15
```

`spring.batch.job.name` selects the Job bean. `inputFile` and `importDate` are business data that the Job receives. The parameter names must correspond to how the Job and its inner components read JobParameters.

## 3. Data types and JobParameters syntax

Under the default configuration, a `key=value` argument is converted into a JobParameter of type `String`. For example:

```bash
java -jar app.jar businessDate=2026-11-15 source=ERP
```

When another data type is needed, `DefaultJobParametersConverter` supports specifying the Java type and the identifying flag with this syntax:

```text
parameterName=parameterValue,fully.qualified.Type,identifying
```

Example of passing an integer of type `Long` and marking it as an identifying parameter:

```bash
java -jar app.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12,java.lang.Long,true \
    requestedBy=nightly-scheduler,java.lang.String,false
```

In this example:

- `businessDate` is a String and by default is an identifying parameter.
- `regionId` is converted to `Long` and marked as identifying.
- `requestedBy` is a String but does not take part in identifying the JobInstance.

The specified data type must be supported by the application's converter and ConversionService. If you use a date-time type or a custom type, make sure the string format can be converted to that type. If you do not need a special type, passing a String and then converting and validating it in the application logic is usually simpler.

### Identifying and non-identifying parameters

JobParameters can consist of identifying and non-identifying parameters:

- Identifying parameters take part in forming the key of the `JobInstance` together with the Job name.
- Non-identifying parameters are still stored and can be used by the Job, but do not change the JobInstance identity.

For example, `businessDate` and `regionId` can identify one aggregation unit; `requestedBy` only stores the request source:

```text
dailySalesJob
  businessDate=2026-11-15  (identifying)
  regionId=12              (identifying)
  requestedBy=scheduler    (non-identifying)
```

If the same Job is called again with the same `businessDate` and `regionId`, changing `requestedBy` does not create a new JobInstance. This is an important point when designing run commands and the restart process.

## 4. Reading command line arguments with ApplicationRunner

Not every application uses Spring Boot's automatic launch mechanism. You can read command line arguments yourself with `ApplicationRunner`, create JobParameters, and call the `JobLauncher` with your own logic.

The following example receives the business date from the `--business-date` option:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesCommandLineConfig {

    @Bean
    public ApplicationRunner launchDailySales(
            JobLauncher jobLauncher,
            Job dailySalesJob) {

        return (ApplicationArguments args) -> {
            var values = args.getOptionValues("business-date");
            if (values == null || values.size() != 1
                    || values.get(0).isBlank()) {
                throw new IllegalArgumentException(
                        "Required option: --business-date=yyyy-MM-dd");
            }

            String businessDate = values.get(0);

            JobParameters parameters = new JobParametersBuilder()
                    .addString("businessDate", businessDate, true)
                    .toJobParameters();

            jobLauncher.run(dailySalesJob, parameters);
        };
    }
}
```

Run the application with:

```bash
java -jar target/daily-sales-batch.jar --business-date=2026-11-15
```

`ApplicationArguments` distinguishes options in the form `--key=value` from arguments that have no option name. In this example, the application reads `business-date`, then explicitly maps it to a JobParameter named `businessDate`. This mapping means the option name on the command line does not have to match the JobParameter name.

If the application uses a custom runner like the one above in Spring Boot, you need to disable the automatic Job launch mechanism so that both `JobLauncherApplicationRunner` and the custom runner do not launch the same Job:

```properties
spring.batch.job.enabled=false
```

You can set this property in `application.properties` or pass it via the command line:

```bash
java -jar target/daily-sales-batch.jar \
    --spring.batch.job.enabled=false \
    --business-date=2026-11-15
```

Once auto-run is disabled, the custom runner is responsible for reading and validating the arguments, creating the JobParameters, and then calling the JobLauncher.

## 5. Using CommandLineJobRunner in a traditional configuration

Spring Batch also provides `CommandLineJobRunner` for the traditional launch approach, commonly seen in applications configured with XML or having an application context prepared for this runner. The command needs to specify the configuration path, the Job name, and the JobParameters:

```bash
java -cp "<application-classpath>" \
    org.springframework.batch.core.launch.support.CommandLineJobRunner \
    classpath:/jobs/daily-sales-job.xml \
    dailySalesJob \
    businessDate=2026-11-15
```

The components of the command:

1. `<application-classpath>` contains Spring Batch, the Spring Framework, the database driver, and the application libraries.
2. `CommandLineJobRunner` is the class that receives the command and coordinates the launch.
3. `classpath:/jobs/daily-sales-job.xml` is the location of the application context containing the Job configuration and related components.
4. `dailySalesJob` is the identifying name of the Job in the context.
5. `businessDate=2026-11-15` is the JobParameter.

`CommandLineJobRunner` suits applications that use a configuration mechanism the runner can load. For a Spring Boot application packaged as an executable JAR, the more common approach is to call `java -jar` and use `JobLauncherApplicationRunner`, or to write your own `ApplicationRunner` when you need control over argument parsing.

## 6. Validating input parameters

Do not assume the person running the job always passes all parameters in the right format. The Job needs to clearly define required parameters, optional parameters, and validity rules.

### Validation at the command line level

With a custom runner, you can check that the option exists, appears only once, and has a non-empty value before calling the JobLauncher. If the parameter is a date, you can parse it with `LocalDate` to detect a wrongly formatted date:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

String businessDate = values.get(0);
try {
    LocalDate.parse(businessDate);
} catch (DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "business-date must use yyyy-MM-dd", ex);
}
```

### Validation with JobParametersValidator

Spring Batch lets you attach a `JobParametersValidator` to a Job to check the parameter set before execution. For example, using `DefaultJobParametersValidator` to require `businessDate`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersValidator;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.job.DefaultJobParametersValidator;
import org.springframework.context.annotation.Bean;

@Bean
public Job dailySalesJob(
        JobRepository jobRepository,
        Step aggregateSalesStep) {

    JobParametersValidator validator =
            new DefaultJobParametersValidator(
                    new String[] {"businessDate"},
                    new String[] {"regionId", "requestedBy"});

    return new JobBuilder("dailySalesJob", jobRepository)
            .validator(validator)
            .start(aggregateSalesStep)
            .build();
}
```

In this configuration, `businessDate` is a required parameter; `regionId` and `requestedBy` are the optional parameters that are allowed. If the application has many parameters or complex business rules, you can implement a dedicated validator to check the date format, the time range, the batch ID, or the combination of parameters.

Command line validation gives early, easy-to-understand error messages to operators. The Job's validator is still necessary because the Job can be launched from a scheduler, an API, or another Java component, not only from the command line.

## 7. Extracting JobParameters inside a Step

Once the Job has been launched, the processing components can read the JobParameters through `StepExecution` or `ChunkContext`. For example, a Tasklet can get the business date from `StepContribution`:

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class DailySummaryTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String businessDate = contribution.getStepExecution()
                .getJobParameters()
                .getString("businessDate");

        System.out.println("Processing business date: " + businessDate);
        return RepeatStatus.FINISHED;
    }
}
```

If you use a data type other than String, you need to read it with the corresponding type or convert it explicitly. Prefer taking parameters from `JobParameters` rather than re-reading `System.getProperty` or environment variables in every Step; this keeps the input data tied to the run's metadata and enables accurate tracing.

## 8. Quoting rules and how to pass values

The command line is parsed by the shell before Java receives the arguments. If a value contains whitespace or special characters, it needs to be quoted according to the shell's syntax.

Example with Bash or PowerShell:

```bash
java -jar daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    'requestedBy=nightly operations'
```

Example with Windows Command Prompt:

```bat
java -jar daily-sales-batch.jar --spring.batch.job.name=dailySalesJob businessDate=2026-11-15 "requestedBy=nightly operations"
```

Shells can have different escape rules for quotes, spaces, commas, and special characters. Check the actual arguments the application receives if a value is split or altered unintentionally.

Do not pass passwords, access tokens, or secrets directly via the command line. These values can appear in shell history, the process list, or system logs. Use environment variables, a secret manager, or a secure configuration mechanism, and pass only the necessary reference into JobParameters.

## 9. Common mistakes

| Mistake | Cause | Remedy |
|---|---|---|
| The Job does not receive the parameter | The key name is wrong or the argument is passed as an option that the runner does not read as a JobParameter. | Check the `key=value` syntax and the runner mechanism in use. |
| Boot runs the wrong Job | The Job to run is not specified in an application with multiple Jobs. | Use `--spring.batch.job.name=<jobName>` or configure the appropriate Job name. |
| The Job is launched twice | The auto runner and a custom runner are both active. | Disable `spring.batch.job.enabled` when managing the launch yourself. |
| A value is split into multiple arguments | Missing quotes when the value contains whitespace. | Quote the entire `key=value` token according to the shell. |
| Type conversion fails | The converter does not support the type or the value format is invalid. | Use the default String type or configure the converter and format explicitly. |
| The JobInstance has completed so the launch is rejected | The identifying JobParameters are the same as an instance that is `COMPLETED`. | Use restart if the instance is not completed; if new work is needed, create an identifying parameter with business meaning. |
| A parameter is changed but is still treated as the same instance | Only a non-identifying parameter was changed. | Check the identifying flag of the JobParameters. |
| Sensitive information is exposed | A secret is passed directly on the command line. | Use environment variables or a secret manager. |

## 10. The command-line Job run process in practice

An operational process usually consists of the following steps:

1. Determine the Job to run and the required business parameters.
2. Choose identifying parameters so that they correctly represent the unit of work to process.
3. Check that the JAR file, the environment configuration, the database, and the metadata schema are ready.
4. Pass the Job name together with the JobParameters using the syntax of the runner in use.
5. Check the logs and the `JobExecution` to determine whether the Job has started, is running, or has finished.
6. If the launch fails, read the exception and the metadata to distinguish a parameter error, a running instance, a completed instance, or a processing error in a Step.

Example of a scheduled run command:

```bash
java -jar /opt/batch/daily-sales-batch.jar \
    --spring.batch.job.name=dailySalesJob \
    businessDate=2026-11-15 \
    regionId=12,java.lang.Long,true \
    requestedBy=nightly-scheduler,java.lang.String,false
```

This command passes the business date and the region as the data that identifies the work, and also stores the caller as `requestedBy`. If the scheduler resends the same command after the Job has completed, Spring Batch recognizes the same JobInstance and rejects the duplicate launch. If the Job failed, the same identifying parameters can be used to restart when the configuration allows.

## Conclusion

Command line parameters are a convenient way to supply input data to a Job without modifying the source code on every run. In Spring Boot, `key=value` arguments can be converted into JobParameters by `JobLauncherApplicationRunner`; the application can also read `ApplicationArguments` itself and call the `JobLauncher`. You need to distinguish configuration options such as `spring.batch.job.name` from JobParameters, choose the right identifying parameters, check types and values, and control duplicate launches. When the parameters are designed correctly, the Job can run by day, batch, or business request and be tracked and restarted through Spring Batch's metadata.
