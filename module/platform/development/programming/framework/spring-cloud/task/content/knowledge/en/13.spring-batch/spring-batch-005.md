# Selecting a Job and Passing JobParameters

In a **Spring Cloud Task** application, the Spring Boot process starts up, performs finite work, and exits; **TaskRepository** records the history of that run as a `TaskExecution`. When the work requires chunk-oriented reading, checkpoints, retries, and restarting after failures, we typically integrate **Spring Batch**. At that point, an application may contain **multiple `Job`s**, and each launch must specify **which Job runs** and **which `JobParameters` are passed in**.

This lesson belongs to the **Spring Batch** chapter. Its goal is to distinguish selecting a `Job` from passing `JobParameters`, understand how to select a Job when Spring Boot auto-runs Batch Jobs or when the application explicitly calls `JobLauncher`, understand the impact of parameters on **`JobInstance`**, handle re-runs, and correlate results between **TaskRepository** and **JobRepository**. The running example throughout is a system with two Jobs: `importOrdersJob` for importing orders and `dailyReportJob` for aggregating daily reports.

> **Version scope:** Java examples use familiar APIs from **Spring Boot 3.x / Spring Batch 5.x** and compatible Spring Cloud Task, such as `JobBuilder`, `StepBuilder`, `JobLauncher`, and `JobParametersBuilder`. Newer branches may change APIs, starter sets, or auto-configuration behavior. Check the BOM and documentation for your exact version before copying into a project.

## 1. Distinguishing Three Entities: Task, Job, and JobInstance

A single JAR launch normally creates one `TaskExecution`. Internally, the application can run one or more Spring Batch `Job`s, each with its own `JobExecution`. Spring Batch identifies a `JobInstance` by **Job name + set of JobParameters with `identifying=true`**.

| Concept | Represents | Example |
| --- | --- | --- |
| `TaskExecution` | A single run of a Spring Cloud Task process | Data import process launched at 02:00 |
| `Job` | Processing definition organized into Steps | `importOrdersJob`, `dailyReportJob` |
| `JobParameters` | Values passed **to a JobExecution** | `businessDate=2026-11-23`, `sourceId=partner-A` |
| `JobInstance` | A *logical* execution unit distinguished by Job name and identifying parameters | `importOrdersJob` for date 2026-11-23 and source partner-A |
| `JobExecution` | A single **execution attempt** of a JobInstance (including restarts) | Attempt 1 failed; attempt 2 succeeded |
| `JobRepository` | Stores metadata for Jobs, Steps, parameters, and checkpoints | Tables `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` |
| `TaskRepository` | Stores Task process lifecycle and Task–Batch links | `TASK_EXECUTION`, `TASK_TASK_BATCH` |

Example of the same JobInstance attempted twice:

~~~text
TaskExecution #101
  └── Job: importOrdersJob
      ├── identifying: businessDate=2026-11-23
      ├── identifying: sourceId=partner-A
      └── JobExecution #501: FAILED

TaskExecution #102 (process re-run)
  └── Job: importOrdersJob
      ├── identifying: businessDate=2026-11-23
      ├── identifying: sourceId=partner-A
      └── JobExecution #502: COMPLETED
             (same JobInstance as #501)
~~~

In this example, **the TaskExecution ID changes** between the two processes, while **the JobInstance remains unchanged** because the Job name and identifying parameters did not change. This is how Spring Batch looks up saved checkpoint state when a Job supports restarts.

### Selection and Launch Diagram

~~~mermaid
flowchart TD
    A["Cron / API / operator"] --> B["Run Spring Boot Task"]
    B --> C["TaskRepository: TaskExecution"]
    B --> D{"Which Job to run?"}
    D --> E["importOrdersJob"]
    D --> F["dailyReportJob"]
    E --> G["JobLauncher + JobParameters"]
    F --> G
    G --> H[("JobRepository: JobInstance, JobExecution, StepExecution")]
    G --> I["Process via Step / chunk / tasklet"]
    I --> J["Read status COMPLETED / FAILED / STOPPED"]
    J --> K["Update Task result; exit process"]
    H -. "Task–Batch link" .-> C
~~~

**Selecting the Job** determines which workflow runs. **JobParameters** determine which data/period is processed and, depending on the identifying flag, which JobInstance is looked up. These are two distinct decisions, and both must be accurate.

## 2. How an Application with Multiple Jobs Is Structured

Suppose the application defines these beans:

~~~java
@Configuration
public class BatchJobsConfiguration {

    @Bean
    Job importOrdersJob(JobRepository repo,
                        @Qualifier("importOrdersStep") Step step) {
        return new JobBuilder("importOrdersJob", repo)
                .start(step)
                .build();
    }

    @Bean
    Job dailyReportJob(JobRepository repo,
                       @Qualifier("dailyReportStep") Step step) {
        return new JobBuilder("dailyReportJob", repo)
                .start(step)
                .build();
    }
}
~~~

The `importOrdersStep` and `dailyReportStep` beans must be defined in Step configuration; the snippet above highlights **Job names**. In practice, Spring Batch identifies a Job by **`Job.getName()`** (the string passed to `new JobBuilder(...)`), so do not always assume the bean name and Job name are guaranteed to match.

For instance, the same image containing two workflows will serve two operational requests:

- When a partner sends a file: select **`importOrdersJob`** and pass `sourceId`, `businessDate`.
- At daily cutoff time: select **`dailyReportJob`** and pass `businessDate`, possibly adding `tenantId`.

If the wrong Job runs, parameters might still parse successfully while executing the wrong business workflow. Therefore, when an application has multiple Jobs, there must be an **explicit** selection mechanism and name validation.

## 3. Approach A: Spring Boot Auto-Launches the Selected Job

Spring Boot provides a mechanism to automatically run a Spring Batch Job on application startup if Batch auto-configuration is active. When only one `Job` exists, Boot typically launches that Job automatically. When **multiple Job beans** exist, select one using the property:

~~~properties
spring.batch.job.name=importOrdersJob
~~~

This is a **Spring Boot / Spring Batch** property, not `spring.cloud.task.job-name`. Older Spring Cloud Task branches had `spring.cloud.task.batch.job-names`, which is **deprecated**; use `spring.batch.job.name` when supported by your Spring Boot version.

Example configuration:

~~~yaml
spring:
  application:
    name: order-processing-task
  main:
    web-application-type: none
  datasource:
    url: ${BATCH_DB_URL}
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: true
  cloud:
    task:
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

`spring.batch.job.enabled=true` instructs Boot to execute its auto-launch mechanism when eligible; in common Boot branches, this is the default behavior. `spring.cloud.task.batch.fail-on-job-failure=true` lets Spring Cloud Task integration translate a failed Job into a non-zero Task exit code so the orchestrator detects the error. This property requires the **matching Task–Batch integration module and a supporting version**.

### 3.1. Commands to Select a Job and Pass Parameters

~~~bash
java -jar batch-task.jar \
  --spring.batch.job.name=importOrdersJob \
  businessDate=2026-11-23 \
  sourceId=partner-A

java -jar batch-task.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-23
~~~

**Important syntax distinction:**

| Command Argument | Category | Effect |
| --- | --- | --- |
| `--spring.batch.job.name=importOrdersJob` | Spring Boot property | Selects which Job the startup runner launches |
| `businessDate=2026-11-23` | Batch JobParameter | Passes the business date to the Job |
| `sourceId=partner-A` | Batch JobParameter | Passes the source identifier to the Job |

Spring Boot places arguments prefixed with **`--`** into the `Environment` as application properties. The default Batch Job auto-runner treats **`key=value` arguments without `--`** as `JobParameters`.

Consequently, this command **does not pass the date into the Batch Job via the default mechanism**:

~~~bash
# Do not use this syntax if you want the startup runner to auto-map
# businessDate into JobParameters:
java -jar batch-task.jar \
  --spring.batch.job.name=dailyReportJob \
  --businessDate=2026-11-23
~~~

`--businessDate=...` is a **Spring Boot property**, so it appears in `Environment` but does not automatically become a `JobParameter`. This is the root cause of many errors where a Job uses `@StepScope` yet `jobParameters['businessDate']` evaluates to null.

### 3.2. Receiving JobParameters Inside a Step

A `@StepScope` bean can retrieve parameters via expressions:

~~~java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobParameters['sourceId']}") String sourceId,
        @Value("#{jobParameters['businessDate']}") String date,
        OrderImportService service) {

    return (contribution, chunkContext) -> {
        if (sourceId == null || sourceId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing sourceId JobParameter");
        }
        LocalDate businessDate = LocalDate.parse(date);
        service.importSource(sourceId, businessDate);
        return RepeatStatus.FINISHED;
    };
}
~~~

This is a simple **Tasklet** example; the application still needs an `OrderImportService` bean, a Step using this Tasklet, and corresponding Job/JobRepository/transaction manager configuration. Relevant imports: `org.springframework.batch.core.configuration.annotation.StepScope`, `org.springframework.batch.core.step.tasklet.Tasklet`, `org.springframework.batch.repeat.RepeatStatus`, `org.springframework.beans.factory.annotation.Value`, `java.time.LocalDate`.

`@StepScope` ensures values are resolved **when the Step executes** and `JobParameters` are available. Creating a singleton bean and trying to resolve `jobParameters` at context startup fails because the scope is not active yet.

**Transaction note:** real data import steps typically use chunk-oriented processing with `ItemReader`, `ItemProcessor`, `ItemWriter`, and `ExecutionContext` for checkpoints; the Tasklet above is only for demonstrating parameter binding.

### 3.3. Controlling Multi-Job Applications

If an application has two Jobs and `spring.batch.job.name` is omitted, do not expect the startup runner to guess which Job to run. On current Boot versions, multiple Jobs require specifying the Job name; if missing or invalid, the application may fail on startup.

For controllable operations:

1. Give Jobs stable, distinct names reflecting their business purpose.
2. Pass the **Job name** in the launcher, deployment manifest, or schedule.
3. Pass all required JobParameters for the selected Job.
4. Observe logs confirming the launched Job name and identifying parameters after startup.
5. When a Job fails, ensure the **process exit code** propagates to the scheduler.

## 4. Approach B: Explicitly Selecting and Running a Job with JobLauncher

If you need more complex routing rules—such as `--job=importOrdersJob`, caller allowlisting, or different parameter mappings per Job—you can **disable Boot's automatic Job execution** and write your own runner to select and launch it:

~~~yaml
spring:
  application:
    name: controlled-batch-task
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
  cloud:
    task:
      initialize-enabled: false
~~~

With `spring.batch.job.enabled=false`, Boot does not auto-launch Jobs on startup; application code is responsible for **selecting and calling `JobLauncher` exactly once**. Avoid enabling auto-run alongside a custom runner; otherwise the same Job could execute twice or throw `JobExecutionAlreadyRunningException`.

Example routing between two fixed Jobs in Spring Batch 5.x:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchTaskDispatcher {

    @Bean
    ApplicationRunner launchSelectedJob(
            @Qualifier("importOrdersJob") Job importJob,
            @Qualifier("dailyReportJob") Job reportJob,
            JobLauncher jobLauncher) {

        return args -> {
            String requested = required(args, "job");
            String date = LocalDate
                    .parse(required(args, "business-date"))
                    .toString();

            Job selected = switch (requested) {
                case "importOrdersJob" -> importJob;
                case "dailyReportJob" -> reportJob;
                default -> throw new IllegalArgumentException(
                        "Unsupported job: " + requested);
            };

            JobParametersBuilder builder = new JobParametersBuilder()
                    .addString("businessDate", date, true)
                    .addString(
                            "requestedBy",
                            optional(args, "requested-by", "scheduler"),
                            false);

            if ("importOrdersJob".equals(requested)) {
                builder.addString(
                        "sourceId", required(args, "source-id"), true);
            }

            JobParameters parameters = builder.toJobParameters();
            JobExecution execution = jobLauncher.run(selected, parameters);

            // This pattern requires a synchronous JobLauncher.
            if (execution.isRunning()) {
                throw new IllegalStateException(
                        "JobLauncher returned before job completed");
            }
            if (execution.getStatus() != BatchStatus.COMPLETED) {
                throw new IllegalStateException(
                        "Batch job ended with " + execution.getStatus());
            }
        };
    }

    private static String required(
            ApplicationArguments args, String key) {

        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1 ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected one --" + key + "=value");
        }
        return values.get(0);
    }

    private static String optional(
            ApplicationArguments args, String key, String fallback) {
        if (!args.containsOption(key)) {
            return fallback;
        }
        return required(args, key);
    }
}
~~~

Running with **application arguments** (different syntax from Approach A):

~~~bash
java -jar batch-task.jar \
  --job=importOrdersJob \
  --business-date=2026-11-23 \
  --source-id=partner-A \
  --requested-by=scheduler

java -jar batch-task.jar \
  --job=dailyReportJob \
  --business-date=2026-11-23
~~~

In this approach, `ApplicationArguments` reads the `--job`, `--business-date`, and `--source-id` options. The program **explicitly constructs** `JobParameters` using `JobParametersBuilder`. There is no automatic conversion from `--business-date` options into Batch JobParameters unless written like this.

**Important limitation of the example:** `JobLauncher` **does not guarantee** synchronous execution in all configurations. The example expects the launcher to return after the Job completes; if `JobLauncher` uses an asynchronous executor, `run()` returning does not mean the Job is done. For finite Task processes, configure a synchronous `JobLauncher`, or implement waiting/polling until `JobExecution` reaches a terminal status **before the Task exits**, handling timeouts and exceptions. The `execution.isRunning()` check here is a defensive guard, not a substitute for a completion-waiting strategy.

Additionally, when launching a Job in code, default integration's `spring.cloud.task.batch.fail-on-job-failure` is not an excuse to skip checking `JobExecution`. The snippet above **explicitly throws an exception** when the Job ends unsuccessfully so the Task layer knows an error occurred.

## 5. JobParameters: Identifying vs. Non-Identifying

`JobParameters` is not merely a `Map<String, String>`. In Spring Batch, each parameter also has a **value type** and an **`identifying`** flag. The set of identifying parameters together with the **Job name** determines the `JobInstance`.

Example:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-23", true)
        .addString("sourceId", "partner-A", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

| Parameter | Identifying? | Meaning |
| --- | --- | --- |
| `businessDate` | **true** | Selects the data period to process |
| `sourceId` | **true** | Selects the data source to import |
| `requestedBy` | **false** | Records who or which system requested the run; does not alter JobInstance identity |

For example, attempt 1 with `requestedBy=scheduler` and a restart with `requestedBy=operator` still point to **the same JobInstance**, provided the Job name and both identifying parameters stay the same. Changing `businessDate` or `sourceId` creates a **different JobInstance**.

### 5.1. Why Use Non-Identifying Parameters?

Some metadata is helpful for auditing but does not define the **logical dataset**:

- Name of the requesting system (`requestedBy`).
- Operational request ID (`requestId`), when the goal is tracing without altering the JobInstance.
- Display flags or logging levels that do not affect the business dataset.

Conversely, attributes determining input data—such as `sourceVersion` or `tenantId`—may need to be identifying if they change which dataset the Job processes. The choice must derive from **business rules**, not because a parameter looks "important" visually.

### 5.2. Do Not Automatically Add `run.id` on Every Retry

A common mistake is always appending the current timestamp:

~~~java
// Careful: addLong uses identifying = true by default.
new JobParametersBuilder()
        .addString("businessDate", "2026-11-23")
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
~~~

Each attempt with a different `run.id` creates a **new JobInstance**, so Spring Batch no longer treats it as a retry/restart of the previous JobInstance, and prior checkpoints will not be reused. Only create a new instance when intentionally processing a distinct logical run; never use `run.id` to "work around" `JobInstanceAlreadyCompleteException` without understanding the consequences.

### 5.3. JobParameters Data Types

In the Spring Batch 5 API, `JobParametersBuilder` supports multiple types such as `String`, `Long`, `Double`, `Date`, and version-dependent type conversions. For business dates, passing an ISO `yyyy-MM-dd` string and parsing it inside the Step simplifies examples and avoids UTC timezone mismatches.

Typed parameters can also be used via version-supported converters/CLI syntax. For Boot's startup runner CLI, **type syntax in Batch 5/6 is not uniform across all versions**; inspect the actual `JobParametersConverter`. In basic practice, `businessDate=2026-11-23` is parsed as a string parameter and validated by the application.

## 6. Re-running and Handling Completed Jobs

Spring Batch enforces important rules:

| Scenario When Calling the Same Job Name | Identifying Params | Typical Outcome |
| --- | --- | --- |
| No existing JobInstance | New | Creates a new JobInstance and JobExecution |
| Previous run `FAILED`, Job allows restart | Unchanged | Creates a **new JobExecution under the same JobInstance** |
| Previous run `COMPLETED` | Unchanged | Disallows re-running the same JobInstance; may throw `JobInstanceAlreadyCompleteException` |
| A JobExecution is currently running | Unchanged | May throw `JobExecutionAlreadyRunningException` |
| Change identifying date or `sourceId` | Different | Creates a **new JobInstance** |
| Change only non-identifying `requestedBy` | Unchanged | Still treated as the same JobInstance; prior state rules apply |

These rules assume **`JobRepository` is a shared, durable store** and Job identification configuration is consistent. If each process uses a separate metadata DB or wipes Batch tables, Spring Batch cannot recognize previous JobInstances.

### 6.1. Restarts Must Preserve Identifying Params

Suppose importing the `partner-A` file for `2026-11-23` fails after reading 70%:

~~~text
Attempt 1:
  importOrdersJob
  businessDate=2026-11-23 (identifying)
  sourceId=partner-A        (identifying)
  requestedBy=scheduler     (non-identifying)
  JobExecution #501 = FAILED

Attempt 2:
  importOrdersJob
  businessDate=2026-11-23 (identifying)
  sourceId=partner-A        (identifying)
  requestedBy=operator      (non-identifying)
  JobExecution #502 = COMPLETED
~~~

If the ItemReader/Step is designed to be restartable and persists checkpoints properly, the second attempt can resume from the previous state. **Sharing a JobInstance does not automatically guarantee exactly-once** for external APIs or non-transactional side effects. Business locks, idempotency keys, and retry policies are still required.

With Spring Boot's CLI runner, on restart you must **pass again both the identifying and any needed non-identifying parameters**; do not expect the runner to automatically copy all non-identifying params from the previous run.

### 6.2. Re-running a Completed Period

If the report for `2026-11-23` is already `COMPLETED`, calling the same Job name and identifying params is not the default way to republish the report. If the business genuinely requires a new edition, add a **meaningful identifying parameter**, such as `reportVersion=2`, or design an explicit rerun workflow. Do not silently inject a random `run.id`, as that breaks business version tracking.

## 7. Boundary Between Task Arguments and JobParameters

When running a Task–Batch integrated application, there are two parameter sets to distinguish:

| Data | Who Receives It? | Where Is It Stored? |
| --- | --- | --- |
| Raw Java process arguments | Spring Boot / Spring Cloud Task | `TASK_EXECUTION_PARAMS` (strings passed to the Task) |
| `spring.batch.job.name` | Spring Boot property selecting the auto-run Job | Configuration source, and possibly in task arguments when passed via CLI |
| `JobParameters` | Spring Batch `JobLauncher` | `BATCH_JOB_EXECUTION_PARAMS` |
| Checkpoint information | Spring Batch Step/Job | `BATCH_STEP_EXECUTION_CONTEXT`, `BATCH_JOB_EXECUTION_CONTEXT` |
| Business state | Import/report logic | Business tables or dedicated results store |

In **Approach A**, non-option `businessDate=...` arguments are converted to JobParameters by the startup runner. In **Approach B**, `--business-date=...` only becomes a JobParameter when **Java code explicitly maps it** via `JobParametersBuilder`.

Do not confuse `TaskExecution ID` with `JobExecution ID`. One Task run can link to one or more JobExecutions; the IDs belong to different repositories and are not guaranteed to be equal.

### 7.1. Associating TaskExecution with JobExecution

When **`spring-cloud-task-batch`** is present and the `TaskBatchExecutionListener` linking mechanism is properly configured, Spring Cloud Task records the relationship between TaskExecution and Batch JobExecution. The default schema includes the **`TASK_TASK_BATCH`** table with two columns:

- `TASK_EXECUTION_ID`.
- `JOB_EXECUTION_ID`.

You can query it for investigation:

~~~sql
SELECT t.TASK_EXECUTION_ID,
       t.TASK_NAME,
       l.JOB_EXECUTION_ID,
       i.JOB_NAME,
       e.STATUS
FROM TASK_EXECUTION t
JOIN TASK_TASK_BATCH l
  ON l.TASK_EXECUTION_ID = t.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION e
  ON e.JOB_EXECUTION_ID = l.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE i
  ON i.JOB_INSTANCE_ID = e.JOB_INSTANCE_ID
WHERE t.TASK_EXECUTION_ID = :task_execution_id;
~~~

`:task_execution_id` is a named parameter for JDBC/JPA clients; when running directly in a SQL console, substitute a supported placeholder syntax. This query assumes **TaskRepository and JobRepository reside in the same queryable DB/schema**; if they use two different DataSources, query each store separately and correlate IDs at the application or management-tool layer.

`TaskExplorer.getJobExecutionIdsByTaskExecutionId(id)` also retrieves the list of associated JobExecution IDs when linking is active.

### 7.2. Querying Parameters in JobRepository

In the Spring Batch 5.x schema, you can inspect Job parameters:

~~~sql
SELECT e.JOB_EXECUTION_ID,
       i.JOB_NAME,
       e.STATUS,
       p.PARAMETER_NAME,
       p.PARAMETER_VALUE,
       p.PARAMETER_TYPE,
       p.IDENTIFYING
FROM BATCH_JOB_EXECUTION e
JOIN BATCH_JOB_INSTANCE i
  ON i.JOB_INSTANCE_ID = e.JOB_INSTANCE_ID
LEFT JOIN BATCH_JOB_EXECUTION_PARAMS p
  ON p.JOB_EXECUTION_ID = e.JOB_EXECUTION_ID
WHERE e.JOB_EXECUTION_ID = :job_execution_id;
~~~

Column layouts differ across Spring Batch generations; **verify the DDL for your exact version**. If the query returns multiple rows, that is normally because one JobExecution has multiple JobParameters.

## 8. Selecting a Job for Scheduled or On-Demand Launches

Spring Cloud Task does not schedule jobs by date itself. An external CronJob, scheduler, or launcher API can select the Job and supply the specific data period:

~~~text
Scheduled orchestrator:
    Job name = dailyReportJob
    businessDate = 2026-11-23

On-demand import request:
    Job name = importOrdersJob
    businessDate = 2026-11-23
    sourceId = partner-A
~~~

Two common deployment patterns:

**One JAR, multiple Jobs, Spring Boot auto-run:** each schedule passes `--spring.batch.job.name=<name>` and `key=value` JobParameters.

**One JAR, programmatic dispatch:** each schedule passes `--job=<name>` and application options, then an `ApplicationRunner` builds JobParameters and calls `JobLauncher`.

In both approaches, the orchestrator must pass a **concrete** business date. Avoid ambiguous parameters like `businessDate=today` when restarts might occur, since the wall-clock date at retry time may differ. Define the timezone when computing the report date, then pass an immutable ISO `yyyy-MM-dd` value for that period.

If the application is multi-tenant, decide whether `tenantId` alters JobInstance identity; in most cases, reports for different tenants need to be identified separately.

## 9. Error Handling and Spring Cloud Task Exit Codes

`JobExecution.getStatus()` can be `COMPLETED`, `FAILED`, `STOPPED`, or an intermediate status. Do not assume a `JobLauncher.run()` call that does not throw an exception means the Batch Job succeeded: with a synchronous launcher, **`JobExecution` can return with status `FAILED`** when an error occurs inside a Step.

By default, a Spring Boot process running a Batch Job can **exit with code `0`** even when the Batch Job has `BatchStatus.FAILED`. When using compatible Spring Cloud Task integration with Batch auto-run, configure:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

to reflect a Job failure as a non-zero Task exit code. With a custom launcher, **explicitly inspect `JobExecution` status** and signal errors appropriately to the Task/scheduler.

| Scenario | Outcome to Verify |
| --- | --- |
| Selected Job not found | Fail fast, log valid Job names, do not fall back to another Job |
| Required JobParameter missing | Reject before processing or use a `JobParametersValidator` |
| Same JobInstance already running | Handle `JobExecutionAlreadyRunningException` per retry policy |
| JobInstance already `COMPLETED` | Do not silently spawn a new instance via random `run.id` |
| Job fails mid-Step | Check `JobExecution.status`, error and checkpoint, Task exit code |
| `JobLauncher` runs asynchronously | Wait until terminal status before the finite Task exits |
| Task killed externally | Inspect Pod/Job status, JobRepository, and TaskRepository; final metadata may be missing |

**Runner note:** `ApplicationRunner` and `CommandLineRunner` have execution ordering. When combining auto-run with custom business runners, clarify which runner parses parameters, which launches the Job, and whether they interact. Never add another runner calling `JobLauncher` if the startup runner is enabled and already performs the same work.

## 10. Security and Reliability When Passing JobParameters

Both Task arguments and Batch JobParameters can be **persisted** in the database and appear in logs. Never pass passwords, tokens, connection strings with secrets, or sensitive personal data via CLI/JobParameters.

Instead of:

~~~bash
# Avoid: token may be persisted in Batch/Task metadata.
java -jar batch-task.jar --spring.batch.job.name=importOrdersJob \
  sourceId=partner-A apiToken=SECRET_VALUE
~~~

use:

~~~bash
java -jar batch-task.jar --spring.batch.job.name=importOrdersJob \
  sourceId=partner-A credentialRef=partner-a-service
~~~

`credentialRef` is merely a **non-secret reference key** to an access-controlled secret store; the processing step retrieves the actual credential over a secure channel. If the reference key itself is sensitive, do not record it in public metadata/logs.

Recommended operational safeguards:

- **Validation:** Job name is allowlisted, `businessDate` parses cleanly, `sourceId` matches expected format and length limits.
- **Idempotency:** write target data using unique constraints or explicit business keys; JobInstance aids restarts but does not eliminate all side effects automatically.
- **Database permissions:** Task/Batch accounts have only necessary privileges on their schemas; manage DDL via migrations.
- **Reconciliation:** log `TaskExecution ID`, `JobExecution ID`, job name, non-sensitive identifying params, read/write/reject counts, and failure reasons.
- **Retention:** keep metadata long enough for restarts and investigations; do not purge Batch JobInstance history still needed for recovery.
- **Concurrency:** locking by Task name (if single-instance is enabled) differs from Spring Batch's JobInstance uniqueness and business locks; test with multiple Pods.

## 11. Practical Verification Scenarios

You can verify these behaviors using a test database initialized with Task and Batch schemas matching your library versions.

| Test | Action | Expected Result |
| --- | --- | --- |
| **A. Select import Job** | Pass `--spring.batch.job.name=importOrdersJob` | Only the import Job auto-launches |
| **B. Select report Job** | Pass `--spring.batch.job.name=dailyReportJob` | Only the report Job auto-launches |
| **C. Missing parameter** | Omit `sourceId` for the import Job | Does not silently import wrong data; Job fails clearly |
| **D. Wrong prefix** | Pass `--businessDate=2026-11-23` in auto-run mode | No JobParameter created by default mechanism; observe and fix syntax |
| **E. Re-run FAILED Job** | Keep identifying params, change `requestedBy` | New JobExecution under the same JobInstance if Job is restartable |
| **F. Re-run COMPLETED Job** | Keep identifying params | JobRepository rejects re-running the same instance |
| **G. Change business period** | Change `businessDate` | Creates a new JobInstance |
| **H. Disable auto-run** | `spring.batch.job.enabled=false`, use dispatcher | Only the custom launcher runs the Job |
| **I. Batch failure** | Intentionally fail a Step | Scheduler receives non-zero exit code via config / error handling |
| **J. Traceability** | Query `TASK_TASK_BATCH` and Batch repository | Finds the JobExecution linked to TaskExecution when linking listener is active |

For test E, a genuinely restartable Step with reliable checkpointing is required. Do not infer restart capability merely from passing the same JobParameters again.

### Exercise: Data Import and Report Publishing System

A system has two Jobs:

- `importOrdersJob` imports orders from each `sourceId` by `businessDate`.
- `dailyReportJob` aggregates reports by `tenantId` and `businessDate`.

Complete the following:

1. Identify each Job's identifying JobParameters and appropriate non-identifying attributes.
2. Use `spring.batch.job.name` to craft two separate startup-run invocations.
3. Use `ApplicationRunner` and `JobLauncher` to implement the same Job selection, but with `spring.batch.job.enabled=false`.
4. Add `@StepScope` to read `businessDate` inside a Step and validate the value.
5. Simulate a mid-run failure in `importOrdersJob`. Re-run with the same identifying params and explain why a persistent `JobRepository` is required.
6. Try intentionally adding `run.id=timestamp` on each retry. Observe the new JobInstance and explain why proper restart capability can be lost.
7. Link `JobExecution` with `TaskExecution`, inspect the final status, and confirm the launcher translates a failed Job into an appropriate exit code.

**Pass criteria:** clearly distinguish `TaskExecution`, `Job`, `JobInstance`, `JobExecution`, and `JobParameters`; explain the difference between **`--spring.batch.job.name`** and **`businessDate=...`** in auto-run mode, as well as the effect of identifying parameters on restarts.

## 12. Summary

1. When an application contains multiple Batch Jobs, **select the Job explicitly** via `spring.batch.job.name` (Boot auto-run) or custom Job-selection logic with `JobLauncher` (explicit launch).
2. With Spring Boot auto-run, **`--property=value` is application configuration**, whereas **`key=value` without `--`** is the default command-line way to pass Batch JobParameters.
3. When calling `JobLauncher` manually, set `spring.batch.job.enabled=false` and convert application options into `JobParameters` yourself.
4. **`JobInstance = Job name + identifying JobParameters`**. Keep identifying params identical to restart a failed JobInstance; changing them creates a new instance.
5. Completed Jobs generally **cannot be re-run with the exact same identifying params**. Publishing a new business revision requires a meaningful identifying parameter, not a random `run.id` to bypass controls.
6. Spring Cloud Task and Spring Batch have **repositories with distinct roles**. `TaskExecution` and `JobExecution` can be linked via `TaskBatchExecutionListener`/`TASK_TASK_BATCH`.
7. Always verify **Batch Job status and Task exit code**, especially when using an asynchronous launcher or when a default runner does not propagate Batch failures.

### Official References

- [Spring Boot — Running Spring Batch Jobs on Startup](https://docs.spring.io/spring-boot/reference/io/spring-batch.html)
- [Spring Boot — Batch Applications / Running From the Command Line](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Cloud Task — Batch Integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Batch — Domain Language: JobInstance and JobParameters](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html)
