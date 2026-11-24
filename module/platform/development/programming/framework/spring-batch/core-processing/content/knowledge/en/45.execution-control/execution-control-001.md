# Starting a Job from the Command Line in Spring Batch

In a batch processing system, a job is often triggered on a schedule, by an orchestration tool, from an operations pipeline, or via a manual command when data for a specific date needs to be processed. **Starting a job from the command line** is how you launch a job without a web interface: the process accepts input parameters, connects to the `JobRepository`, executes the steps, records status, and returns a result to the operating system.

This lesson belongs to **Spring Batch Core Processing → Execution control**, using **Java 17, Spring Boot 3.x, and Spring Batch 5.x** to explain how to package the application, run a job via `java -jar`, select a job, pass `JobParameters`, handle duplicate launches/restarts, and integrate with a scheduler. At the end, the lesson introduces Spring Batch's `CommandLineJobRunner` for systems that do not use Spring Boot's default startup mechanism.

## 1. What Does the Command Line Control?

A batch invocation command should clearly answer:

1. **Which application to run?** The JAR path or classpath.
2. **Which job to run?** The `Job` name registered in the Spring context.
3. **Which data to process?** The `JobParameters`, such as business date and region.
4. **Based on which run?** Creating a new `JobInstance` or restarting a failed instance.
5. **How to report the result?** The `JobExecution` status, logs, and process exit code.

Flow with a Spring Boot batch application:

```text
Shell / Cron / Kubernetes Job / CI
        |
        | java -jar report-batch.jar ... businessDate=2026-11-16
        v
Spring Boot application
        |
        +-- Application properties: --spring.*
        +-- Job parameters: name=value
        v
JobLauncherApplicationRunner
        |
        v
JobLauncher --> JobRepository
        |           |
        |           +-- JobInstance / JobExecution / StepExecution
        v
Job --> Step --> Tasklet or Reader/Processor/Writer
        |
        v
JobExecution: COMPLETED / FAILED / STOPPED ...
        |
        v
Logs, metadata, process exit code
```

You must distinguish a job's **`BatchStatus`/`ExitStatus`** from the **Java process exit code**. Both are useful, but they are not the same thing; how to link them is explained in section 7.

## 2. Two Options for Running from the Command Line

| Option | Invocation | Best-Fit Scenario |
| --- | --- | --- |
| Spring Boot executable JAR | `java -jar app.jar ...` | Modern Spring Boot applications, deployed with Docker, cron, or a scheduler |
| `CommandLineJobRunner` | `java -cp ... org.springframework.batch.core.launch.support.CommandLineJobRunner ...` | Traditional Spring Batch, manually selecting the Spring context, often using XML configuration |

Both options use Spring Batch infrastructure, but they have **their own syntax and startup behavior**. The main body of this lesson uses `java -jar` with Spring Boot because that is the common deployment path in Spring Boot 3 projects.

## 3. Preparing a JAR-Runnable Batch Application

Suppose the `dailyReportJob` job generates a report for `businessDate=2026-11-16` and `region=VN`.

### 3.1. Dependencies and Application Configuration

Example `build.gradle` for a project already using the Spring Boot plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    runtimeOnly 'com.h2database:h2'
}
```

H2 is used here to illustrate Spring Batch metadata; if you run jobs that need to **restart across multiple JVM processes**, use a persistent database such as PostgreSQL or MySQL and manage the schema appropriately. In-memory H2 usually loses history after the JVM exits.

`src/main/resources/application.properties`:

```properties
spring.application.name=report-batch

# Only for the H2 example: create the BATCH_* metadata tables.
spring.batch.jdbc.initialize-schema=always

# Allow Spring Boot to run the job when the application starts.
spring.batch.job.enabled=true
```

For Spring Boot 3 and standard batch auto-configuration, you do not need to add `@EnableBatchProcessing` to create the default infrastructure. Enabling this annotation can alter the auto-configuration mechanism managed by Boot, so only use it when you actually configure the batch infrastructure yourself.

### 3.2. Entry Point for the Executable JAR

File `src/main/java/com/example/batch/ReportBatchApplication.java`:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportBatchApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportBatchApplication.class, args);
    }
}
```

`SpringApplication.run(...)` loads the configuration, creates the beans, and invokes Spring Boot's startup runners. When a matching `Job` exists and the runner is not disabled, Spring Boot will launch the job during startup.

### 3.3. Creating a Job That Accepts Command-Line Parameters

File `src/main/java/com/example/batch/DailyReportJobConfig.java`:

```java
package com.example.batch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailyReportJobConfig {

    @Bean
    public Job dailyReportJob(
            JobRepository jobRepository, Step reportStep) {

        return new JobBuilder("dailyReportJob", jobRepository)
                .start(reportStep)
                .build();
    }

    @Bean
    public Step reportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet reportTasklet) {

        return new StepBuilder("reportStep", jobRepository)
                .tasklet(reportTasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    public Tasklet reportTasklet(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['region']}") String region) {

        return (contribution, chunkContext) -> {
            if (businessDate == null || businessDate.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing parameter: businessDate");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException(
                        "Missing parameter: region");
            }

            LocalDate date = LocalDate.parse(businessDate);
            System.out.printf(
                    "Generating report: businessDate=%s, region=%s%n",
                    date, region
            );

            // Real application: read data, process it, and write the report.
            return RepeatStatus.FINISHED;
        };
    }
}
```

In this example:

- `dailyReportJob` is the **job name** that Spring Batch uses when identifying a `JobInstance`.
- `reportStep` is the step that performs the work; a small tasklet is used here for easy observation.
- `@StepScope` allows creating the tasklet with the **parameter values of that step execution**, rather than trying to read job parameters while the application is creating beans.
- `#{jobParameters['businessDate']}` and `#{jobParameters['region']}` retrieve values from `JobParameters`. Parameter names are case-sensitive.
- `LocalDate.parse(...)` here accepts the ISO format `yyyy-MM-dd`. Entering an invalid date causes the step to fail; in a real system there should be clear validation before processing expensive data.

## 4. Building the JAR and Starting the Job

### 4.1. Packaging

On Linux/macOS:

```bash
./gradlew bootJar
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootJar
```

After building, the executable JAR file is usually located in `build/libs/`. Suppose the generated file is `report-batch-0.0.1-SNAPSHOT.jar` (this is an **example name**; replace it with the actual file name).

### 4.2. Running the Job with a Business Date

On Linux/macOS:

```bash
java -jar build/libs/report-batch-0.0.1-SNAPSHOT.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

On Windows PowerShell, the easiest command to copy uses a single line:

```powershell
java -jar "build/libs/report-batch-0.0.1-SNAPSHOT.jar" --spring.batch.job.name=dailyReportJob businessDate=2026-11-16 region=VN
```

The tasklet is expected to print:

```text
Generating report: businessDate=2026-11-16, region=VN
```

Spring Batch then records the execution result in the `JobRepository`. A successful job normally has `BatchStatus.COMPLETED`. To confirm that the business processing is accurate, in addition to the success status you also need to verify the output file or data.

### 4.3. Distinguishing Application Options from Job Parameters

This is the most common source of errors when invoking batch jobs from the shell:

```text
--spring.batch.job.name=dailyReportJob    Application property
--spring.profiles.active=prod             Application property
businessDate=2026-11-16                  JobParameter
region=VN                                JobParameter
```

With Spring Boot 3's default `JobLauncherApplicationRunner` mechanism, **non-option arguments** of the form `name=value` are converted into job parameters. Arguments starting with `--` are treated by Spring Boot as application properties.

| Passed on the Command Line | Purpose |
| --- | --- |
| `--spring.batch.job.name=dailyReportJob` | Selects the job automatically run by Boot |
| `--spring.profiles.active=prod` | Selects the configuration profile |
| `businessDate=2026-11-16` | Passes the `businessDate` parameter to the job |
| `region=VN` | Passes the `region` parameter to the job |
| `--businessDate=2026-11-16` | Creates a `businessDate` property, **not automatically passed as a JobParameter** via the default runner |

An easy-to-make mistake:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  --businessDate=2026-11-16 \
  --region=VN
```

In the example above, the tasklet using `#{jobParameters['businessDate']}` will not receive the expected value. The fix is to **omit `--` before business parameters**:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

When a value contains spaces, wrap the entire argument in quotes:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  'businessDate=2026-11-16' \
  'region=South East Asia'
```

Quoting rules depend on the shell. In PowerShell you can use `"region=South East Asia"`. For real operations, prefer stable region codes such as `VN` or `SG`.

## 5. Selecting a Job and Controlling the Startup Runner

### 5.1. When the Application Has One `Job`

If the Spring context has only one `Job` bean, Spring Boot can automatically run that job on startup with `spring.batch.job.enabled=true`. In operational scripts, you should still explicitly pass `--spring.batch.job.name=dailyReportJob` to avoid ambiguity if more jobs are added to the project later.

### 5.2. When the Application Has Multiple `Job`s

Suppose the context has `dailyReportJob` and `monthEndJob`:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

To run the other job:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=monthEndJob \
  accountingMonth=2026-11
```

Do not rely on bean creation order or class names to decide which job runs. `spring.batch.job.name` must match the configured job name; business parameters for each job may differ.

### 5.3. When Automatic Job Execution Must Be Disabled

If the application uses a REST API, an internal scheduler, or calls `JobLauncher` itself, you can disable the startup runner:

```properties
spring.batch.job.enabled=false
```

Or on the command line:

```bash
java -jar report-batch.jar --spring.batch.job.enabled=false
```

In this case, `java -jar` **only starts the application**. Non-option arguments like `businessDate=...` do not automatically trigger the job when the runner is disabled; application code must explicitly call `JobLauncher`.

## 6. How `JobParameters` Determine New Jobs, Re-runs, and Restarts

Spring Batch distinguishes:

| Component | Meaning |
| --- | --- |
| `Job` | Processing flow definition, e.g., `dailyReportJob` |
| `JobInstance` | Logical unit of work identified by **job name + identifying parameters** |
| `JobExecution` | A single execution attempt of an instance, with its own status and metadata |

Example command:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

Assuming both parameters are identifying, the first run may create:

```text
JobInstance A (dailyReportJob, 2026-11-16, VN)
└── JobExecution #1: COMPLETED
```

Running the exact same command again against a repository that retains metadata:

```text
JobInstance A
└── JobExecution #1: COMPLETED
    └── request to run again → JobInstanceAlreadyCompleteException
```

A completed instance normally cannot be run again. `JobInstanceAlreadyCompleteException` is a Spring Batch control mechanism, not a Java JAR error.

### 6.1. Running for a Different Date

Change an identifying parameter:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-17 region=VN
```

When `businessDate` is identifying, the new value creates a different `JobInstance`.

### 6.2. Running an Independent Instance for the Same Date

You can supply a separate identifying `run.id` for each run:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN run.id=001
```

The next run:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN run.id=002
```

Two commands with different `run.id` values create different instances **when `run.id` is identifying**. That does not automatically prevent writing duplicate data; the job still needs idempotency logic, unique key constraints, or appropriate reprocessing rules.

Configuring `RunIdIncrementer` in the job definition **does not mean** every `java -jar` command automatically increments `run.id`. An incrementer is typically used by mechanisms that explicitly request the "next instance", and it does not implicitly replace fixed parameters passed by the user to the startup runner.

### 6.3. Restarting a Failed Job

If `JobExecution #1` ends in `FAILED` and the job is restartable:

```text
JobInstance B (dailyReportJob, 2026-11-16, VN)
└── JobExecution #1: FAILED
```

You can launch it again **with the same identifying parameters** on a persistent `JobRepository`:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
```

Spring Batch can create `JobExecution #2` under the same instance B:

```text
JobInstance B
├── JobExecution #1: FAILED
└── JobExecution #2: COMPLETED
```

The ability to resume from a checkpoint depends on the reader/writer, `ExecutionContext`, step statuses, and restart configuration. **Do not change an identifying `run.id` when you want to restart the same instance**; changing identifying parameters makes the request a new instance.

### 6.4. Typed Parameter Syntax in Spring Batch 5

Spring Batch 5 supports `DefaultJobParametersConverter` with the full parameter syntax:

```text
name=value,type,identifying
```

Example:

```text
businessDate=2026-11-16,java.lang.String,true
region=VN,java.lang.String,true
traceId=trace-123,java.lang.String,false
```

The command can be written as:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  'businessDate=2026-11-16,java.lang.String,true' \
  'region=VN,java.lang.String,true' \
  'traceId=trace-123,java.lang.String,false'
```

`businessDate` and `region` participate in identifying the instance; `traceId` does not. If you only change `traceId`, Spring Batch still treats it as the same instance based on the two identifying parameters. For the tasklet example that receives `String`, specifying `java.lang.String` keeps the values compatible with the existing code.

**Version note:** converters and parameter syntax have changed across Spring Batch versions. The examples here target Spring Batch 5; older projects using `LegacyJobParametersConverter` may use a different syntax. When a custom converter is configured, you must follow the contract of that specific converter.

## 7. Tracking Job Status and Process Exit Code

### 7.1. Viewing `JobExecution` in Metadata

When Spring Batch infrastructure uses a database to store history, you can query:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailyReportJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

| `BatchStatus` | Meaning |
| --- | --- |
| `STARTING` / `STARTED` | Preparing or currently executing |
| `COMPLETED` | Completed according to Spring Batch semantics |
| `FAILED` | An error prevented the job from completing |
| `STOPPING` / `STOPPED` | Stopping or stopped |
| `ABANDONED` | Execution abandoned by batch administration |

`ExitStatus` can carry a more specific code or description than `BatchStatus`, such as a code returned by a listener or flow. Both statuses are still **different** from the JVM process exit code.

Besides the overall status, you should monitor step names, read/write/skip item counts, error details, and business outputs. A job with allowed skips can still end as `COMPLETED`, so checking status alone is not enough to conclude that all data was processed.

### 7.2. Why Does a Scheduler Need an Exit Code?

Shells, cron, Task Scheduler, Kubernetes, and CI tools commonly follow the convention:

```text
0    → process succeeded
!= 0 → process failed
```

You should not assume `BatchStatus.FAILED` automatically becomes a non-zero exit code in **every deployment setup**. You need to understand the runner and application lifecycle. One proactive approach for a synchronous batch application is to register a `JobExecutionListener` that also implements Spring Boot's `ExitCodeGenerator`.

Example class `BatchExitCodeListener.java`:

```java
package com.example.batch;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.boot.ExitCodeGenerator;

public class BatchExitCodeListener
        implements JobExecutionListener, ExitCodeGenerator {

    private volatile int exitCode = 0;

    @Override
    public void afterJob(JobExecution jobExecution) {
        exitCode = jobExecution.getStatus() == BatchStatus.COMPLETED
                ? 0
                : 1;
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
```

Register it as a bean and attach the listener to the job:

```java
@Bean
public BatchExitCodeListener batchExitCodeListener() {
    return new BatchExitCodeListener();
}

@Bean
public Job dailyReportJob(
        JobRepository jobRepository,
        Step reportStep,
        BatchExitCodeListener exitCodes) {

    return new JobBuilder("dailyReportJob", jobRepository)
            .listener(exitCodes)
            .start(reportStep)
            .build();
}
```

The `dailyReportJob(...)` bean snippet above **replaces** the bean definition of the same name in section 3; do not declare two beans with the same name at the same time.

Update the entry point to return the exit code to the operating system:

```java
public static void main(String[] args) {
    var context = SpringApplication.run(
            ReportBatchApplication.class, args);
    System.exit(SpringApplication.exit(context));
}
```

`SpringApplication.exit(context)` reads the `ExitCodeGenerator` beans in the context. For a **synchronous** job, the listener updates `exitCode` when the job finishes: `0` if `COMPLETED`, `1` otherwise. Applications with multiple jobs or an asynchronous launcher need an explicit mechanism to aggregate results and wait for completion rather than relying directly on the simple status variable above.

### 7.3. Checking the Exit Code from the Shell

Linux/macOS:

```bash
java -jar report-batch.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-16 region=VN
echo "Exit code: $?"
```

PowerShell:

```powershell
java -jar "report-batch.jar" --spring.batch.job.name=dailyReportJob businessDate=2026-11-16 region=VN
$LASTEXITCODE
```

In a script, capture the status immediately after `java` exits so subsequent shell commands do not overwrite the original exit code.

## 8. Wrapping the Command Line in an Operational Script

A script helps operators pass the date accurately and keeps invocation consistent across environments.

Example `run-daily-report.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_JAR="/opt/batch/report-batch.jar"
REGION="${REPORT_REGION:-VN}"

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 yyyy-MM-dd" >&2
  exit 2
fi

BUSINESS_DATE="$1"

exec java -jar "$APP_JAR" \
  --spring.profiles.active=prod \
  --spring.batch.job.name=dailyReportJob \
  "businessDate=$BUSINESS_DATE" \
  "region=$REGION"
```

Invoke the script:

```bash
chmod +x run-daily-report.sh
./run-daily-report.sh 2026-11-16
```

With `exec`, the shell is replaced by the Java process so the scheduler directly receives Java's exit code. Passing the business date explicitly helps avoid confusion between the server's local timezone date, the scheduler trigger time, and the business date to process.

Example `run-daily-report.ps1` for PowerShell:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $BusinessDate,
    [string] $Region = "VN"
)

$jarPath = "C:\batch\report-batch.jar"

& java -jar $jarPath `
  --spring.profiles.active=prod `
  --spring.batch.job.name=dailyReportJob `
  "businessDate=$BusinessDate" `
  "region=$Region"

$batchExitCode = $LASTEXITCODE
exit $batchExitCode
```

Invoke:

```powershell
.\run-daily-report.ps1 -BusinessDate "2026-11-16" -Region "VN"
```

In PowerShell, the line-continuation backtick must be at the very end of the line with no trailing spaces. If line breaks are not needed, writing the Java command on a single line is less error-prone.

When using a scheduler:

- **Cron:** configure absolute JAR paths, environment variables, and an explicit timezone.
- **Windows Task Scheduler:** verify the program path, working directory, and account permissions for files and the database.
- **Kubernetes Job/CronJob:** keep the Java process as the main process; choose retry/concurrency policies compatible with Spring Batch instance identity and restartability.
- **CI/CD:** record the job name, business date, process exit code, and links to logs/metadata for the run.

Do not allow two processes to run concurrently on the same data unless the job is designed for concurrency. `JobExecutionAlreadyRunningException` can occur if the same instance is already running, and even two different instances can contend for resources or write duplicate business data.

## 9. Spring Batch `CommandLineJobRunner`

In Spring Batch applications that do not rely on Spring Boot's startup runner, the traditional class is:

```text
org.springframework.batch.core.launch.support.CommandLineJobRunner
```

General syntax:

```text
java -cp <classpath> \
  org.springframework.batch.core.launch.support.CommandLineJobRunner \
  <context-location> <job-name> [job-parameters...]
```

Example with an XML Spring context **that already exists in the application**:

```bash
java -cp "target/classes:target/dependency/*" \
  org.springframework.batch.core.launch.support.CommandLineJobRunner \
  classpath:jobs/report-job.xml \
  dailyReportJob \
  businessDate=2026-11-16 \
  region=VN
```

In the sample command:

- `-cp` includes the project classes and required libraries; the `target/dependency` folder must be prepared by a separate build step and does not appear automatically from every Maven command.
- `classpath:jobs/report-job.xml` points to the XML file creating the Spring context containing the job. This is a **hypothetical file** for the traditional example, not created in the sample Boot project in section 3.
- `dailyReportJob` is the job name, and the trailing arguments are `JobParameters` converted by the runner.
- Windows uses `;` as the classpath separator; Unix uses `:`.

Do not take a **Spring Boot executable fat JAR** containing nested dependencies and assume it acts as a flat classpath for `java -cp`. If the project is already packaged and operated using Boot's mechanism, `java -jar` is the better choice. `CommandLineJobRunner` has a mechanism to map exit status to process exit code through runner components, but the exact configuration depends on the application and Spring Batch version.

## 10. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Unable to access jarfile` | Wrong JAR name, not built yet, or incorrect path | Verify the file in `build/libs` and read permissions |
| App starts but job does not run | `spring.batch.job.enabled=false`, missing `Job` bean, runner reconfigured | Check Boot configuration and startup logs |
| Wrong job selected | Job name does not match the actual bean | Pass exact `--spring.batch.job.name` |
| `businessDate` is `null` | Used `--businessDate=...` or wrong key | Pass non-option `businessDate=...`, check key name in SpEL |
| `JobInstanceAlreadyCompleteException` | Instance for those identifying parameters is already complete | Use a new instance if an independent run is intended; do not delete metadata arbitrarily |
| `JobExecutionAlreadyRunningException` | An execution of this instance is still running | Check active processes and concurrency policy |
| Unable to restart job | Metadata lost or step/job does not support restart | Use a persistent database, keep identifying parameters, and review state |
| Missing `BATCH_*` tables | Metadata schema not created | Create the version-matched schema via migration or appropriate test configuration |
| Job `FAILED` but scheduler reports success | Process exit code not mapped from batch status | Implement proper exit-code handling and check `$?`/`$LASTEXITCODE` |
| JVM does not exit | Application still has a web server or background threads | Use a non-web batch process or close the context cleanly |
| Re-run writes duplicate data | New instance reprocesses input, writer is not idempotent | Use business keys, unique constraints, or deduplication logic |

**Security note:** `JobParameters` are typically stored in `JobRepository` metadata, and command-line arguments can appear in shell history, process listings, or logs. Never put passwords, tokens, or secrets in `JobParameters` for convenience. Use protected environment variables, a secret manager, or appropriate deployment configuration.

## 11. Practice Exercises

1. Create a Boot application with `dailyReportJob`, package it with `bootJar`, and run it with `businessDate=2026-11-16 region=VN`.
2. Inspect the logs, `JobExecution`, and the `BATCH_JOB_INSTANCE` and `BATCH_JOB_EXECUTION` tables to see the job complete.
3. On a **persistent repository**, run the same identifying parameters again after the job is `COMPLETED`. Explain why the instance identification error occurs.
4. Change `businessDate` to run a new instance. Try adding an identifying `run.id` with a new value to run an independent instance for the same date.
5. Pass `--businessDate=2026-11-16` and compare it with `businessDate=2026-11-16`. Check the value the tasklet actually receives.
6. Pass `businessDate=not-a-date`, observe the step/job becoming `FAILED` and the process exit code. If needed, add `ExitCodeGenerator` from section 7.
7. Put the command into a script taking the date as an argument, run it via a simulated scheduler, and verify the script returns the expected exit code.
8. Create a restartable `FAILED` scenario, re-run with the **same identifying parameters**, and observe the new execution under the same instance.

When implementing command-line job execution, control the entire path **command → application configuration → job name → `JobParameters` → `JobInstance`/`JobExecution` → business output → process exit code**. Clearly defining each part keeps invocations consistent, observable, and recoverable when a batch job encounters an error.
