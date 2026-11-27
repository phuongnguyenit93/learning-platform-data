# Batch Job Fails Yet Task Exit Code Still Reports Success

## 1. Symptom and Operational Impact

**Spring Cloud Task** is a foundation for building **finite-lived** Spring Boot applications: start up, accept parameters, run business logic, record a `TaskExecution` in **TaskRepository**, and terminate. Many tasks—such as CSV imports, reconciliation, and report exports—embed a **Spring Batch Job** internally, using `JobRepository` to track jobs, steps, and restart points.

An operational issue that easily causes misunderstandings:

~~~text
ERROR ... Encountered an error executing step importStep
java.lang.IllegalStateException: Simulated data processing failure
...
INFO  ... Job reconciliationJob completed with status FAILED
...
INFO  ... Task batch-exit-diagnostic completed with exit code 0
~~~

Spring Batch logs say **`FAILED`**, yet the scheduler/Kubernetes running the task may observe **success exit code `0`**. Monitoring fails to alert, the scheduler skips retries, and operators easily miss that only part of the dataset was processed.

This is **not automatically a Kubernetes or TaskRepository bug**. Per Spring Cloud Task documentation, by default Spring Boot/Batch can record a `FAILED` JobExecution **without translating that outcome into a Spring Boot application failure**. Spring Cloud Task provides the property:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

to allow **a Batch Job with `BatchStatus.FAILED` to cause the Task to return a non-zero exit code** along the supported integration path.

This lesson in the **Diagnostics** chapter shows how to recognize the cause, distinguish statuses across Batch/Task/JVM, configure error propagation, reproduce with a single-Step Job, inspect the databases, and verify behavior in a scheduler or Kubernetes.

### Objectives

After completing this lesson, you will be able to:

1. Distinguish `BatchStatus`, `ExitStatus`, `TaskExecution.EXIT_CODE`, and the **OS exit code**.
2. Explain why a `JobExecution.FAILED` does not necessarily produce an unhandled exception in `SpringApplication`.
3. Enable and verify `spring.cloud.task.batch.fail-on-job-failure` on supported versions.
4. Detect custom runners, asynchronous `JobLauncher`s, or Batch flows that skew the final status.
5. Query `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `TASK_EXECUTION`, and the link table when present.
6. Design tests and runbooks so orchestrators never record **false successes**.

## 2. Three Outcome Layers That Must Not Be Equated

| Layer | Representative | Example status | Consumer |
| --- | --- | --- | --- |
| **Spring Batch** | `JobExecution`, `StepExecution` in JobRepository | `BatchStatus.FAILED`, `ExitStatus.FAILED` | Batch runtime, JobExplorer, restart mechanism |
| **Spring Cloud Task** | `TaskExecution` in TaskRepository | `EXIT_CODE=0` or `1` | TaskExplorer, Data Flow dashboard, Task monitoring |
| **JVM and infrastructure** | Process exit code, `terminated.exitCode`, `Job condition` | `0`/non-`0`, `Complete`/`Failed` | Shell, CI, Kubernetes, scheduler |
| **Business** | Committed record count, files, messages, reconciliation | Complete/missing/duplicate data | End users and downstream systems |

Even when **every technical code is 0**, the business outcome can still be wrong if a runner swallows exceptions or Batch skips too many records. Conversely, a `FAILED` Job may have already committed 90% of its chunks; **never** assume all business data rolled back.

### Illustrative Matrix

| Scenario | Batch Job | TaskExecution | Process/Pod |
| --- | --- | --- | --- |
| Processing succeeds | `COMPLETED` | Usually `0` | Usually `0` |
| Batch fails, default behavior | `FAILED` | **May be `0`** | **May be `0`** |
| Batch fails, fail-on active | `FAILED` | Expected non-`0` | Verify against the real JAR |
| Bootstrap fails before TaskExecution created | Job may not exist yet | Task may not exist yet | Usually reports failure |
| JVM receives `SIGKILL` or OOMKilled | Metadata may be incomplete | `END_TIME` may be blank | Container fails at infra level |
| One Step fails, yet flow intentionally calls `end()` | Step `FAILED`, Job may be `COMPLETED` | May be `0` | May be `0` |

**Diagnostic rule:** before editing configuration, clarify whether "success" is being viewed from the **Batch Job**, **TaskRepository**, **process exit**, or **business outcome** perspective.

## 3. Why Does a Step Failure Not Always Fail Spring Boot?

Spring Batch manages Job execution. When a Step throws an exception, the framework typically records the error in `StepExecution` and marks `JobExecution` as `FAILED`. Depending on how the Job is launched, `JobLauncher.run(...)` **can return a failed `JobExecution`** rather than rethrowing the business exception out of the runner.

Spring Cloud Task, in turn, records metadata around the **Spring Boot lifecycle**. If the runner returns normally and no Batch error-mapping mechanism is active, Task treats the application as having completed cleanly:

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant B as Spring Boot
    participant T as TaskRepository
    participant L as Batch JobLauncher
    participant J as JobRepository

    S->>B: Launch task
    B->>T: Create TaskExecution
    B->>L: Launch reconciliationJob
    L->>J: Record JobExecution STARTED
    L->>L: Step throws exception
    L->>J: Record StepExecution/JobExecution FAILED
    L-->>B: Runner completes via default path
    B->>T: Record TaskExecution EXIT_CODE=0
    B-->>S: Process may return exit code 0
~~~

**The Batch failure path is not the Runner failure path.** If an `ApplicationRunner` itself throws an unhandled exception, Spring Boot can publish `ApplicationFailedEvent` so Cloud Task records a Task failure. Batch, however, may have handled the exception inside the Job and expressed the outcome solely on `JobExecution`.

Therefore:

- An `ERROR` log line does not determine the exit code by itself.
- `BatchStatus.FAILED` does not automatically turn into a Java exception thrown from `SpringApplication.run(...)`.
- `TaskBatchExecutionListener` **links Task and Batch** but does not imply exit-code propagation is turned on by default.
- A scheduler observing only process exit status cannot infer all Batch states stored in the database.

## 4. BatchStatus, ExitStatus, and OS Exit Codes

| Value | Type | Example | Source |
| --- | --- | --- | --- |
| `JobExecution.getStatus()` | `BatchStatus` enum | `FAILED`, `COMPLETED`, `STOPPED` | Spring Batch |
| `JobExecution.getExitStatus()` | `ExitStatus` value object | `"FAILED"`, `"COMPLETED"`, or custom | Spring Batch |
| `TaskExecution.getExitCode()` | Integer | `0`, `1` | Spring Cloud Task |
| **Process exit code** | Integer | `0`, `1`, OS/platform-recorded code | JVM/shell/Kubernetes |

`BatchStatus` reflects processing status inside Batch. `ExitStatus` holds a **string exit code** and drives Job flow transitions. **These two values can diverge due to custom Job flows.**

Example of a Job where a Step fails yet the flow ends with `end()`:

~~~java
// Illustrative flow snippet, not a complete configuration class.
.start(stepA)
.next(stepB)
.on("FAILED").end()
.from(stepB).on("*").to(stepC)
.end()
~~~

On that branch, Step B fails yet **the Job can intentionally end `COMPLETED`**. `fail-on-job-failure` inspects `BatchStatus.FAILED` at the **Job** level; so if business rules require Step B failure to fail the entire job, you must fix the **transition semantics** (e.g., `fail()` per the Batch API), not just toggle a Task property.

### Statuses Requiring Explicit Policies

- `STOPPED`: job was stopped; may require human intervention rather than treating it identically to `FAILED`.
- `UNKNOWN`: indeterminate; cannot be treated as success.
- `COMPLETED` with high skip count: succeeded per skip policy, yet may violate business SLAs.
- `FAILED`: job failed; check which data committed and how restarts should work.

## 5. Official Property: fail-on-job-failure

YAML configuration:

~~~yaml
spring:
  cloud:
    task:
      name: batch-exit-diagnostic
      batch:
        fail-on-job-failure: true
~~~

Equivalent properties format:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Per the Spring Cloud Task Reference and Configuration Properties catalog:

| Property | Documented default | Purpose |
| --- | --- | --- |
| `spring.cloud.task.batch.fail-on-job-failure` | `false` | Causes a `FAILED` Job to make the Task return a non-zero code on supported integration paths |
| `spring.cloud.task.batch.fail-on-job-failure-poll-interval` | `5000` ms | Poll interval checking whether `JobExecution` has finished when `fail-on-job-failure` is enabled |
| `spring.cloud.task.batch.listener.enabled` | `true` | Enables the integration listener linking `TaskExecution` with Batch `JobExecution` |

When `fail-on-job-failure=true` takes effect, the Task exit code is **typically `1`** per the documentation; custom `ExitCodeGenerator` beans can affect the final value. **Do not hardcode an expectation that every failure produces exact exit code 1** if the application uses custom exception mappers or runners.

### Differences Across Spring Cloud Task Generations

Current Spring Cloud Task documentation describes this mechanism using an **integrated `ApplicationRunner`**, whose order can be adjusted via `spring.cloud.task.batch.applicationRunnerOrder`. Some older docs describe `CommandLineRunner` and `commandLineRunnerOrder`.

Never copy class/runner property names from an older release into Boot 3/Cloud Task 3 or Boot 4 without checking your BOM and actual version source. This lesson uses the **common Spring Boot 3.x + Spring Batch 5.x + Spring Cloud Task 3.x API branch** for instructional examples.

**The polling interval is not an overall timeout.** It does not cancel a hung worker or terminate a Kubernetes Pod. If Batch runs asynchronously, add application/infrastructure timeouts and explicit Job-completion waiting rules.

## 6. Integration Requirements: Dependencies and Job Launching

To use Spring Batch inside a Cloud Task app, Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-task-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This snippet is **not a complete `pom.xml`**; Boot and Spring Cloud release train versions must be managed through compatible BOMs.

`spring-cloud-task-batch` provides Task–Batch integration, including `TaskBatchExecutionListener` auto-configured when conditions are met (a `Job` bean and the integration module are present). The listener traces a `JobExecution` back to its `TaskExecution` when supported by schema and version.

However, **having the listener does not mean exit mapping is enabled**. Verify further:

1. `spring.cloud.task.batch.fail-on-job-failure` is actually loaded in the running process.
2. The Job is launched **through Boot/Task's supported Batch runner**.
3. No other runner in the app manually calls `JobLauncher`, causing duplicate runs or bypassing the mapping mechanism.
4. The Job reaches **`BatchStatus.FAILED` at the Job level** when errors occur.
5. The process has no `System.exit(0)` call or shell wrapper hardcoded to return 0.

### Avoiding Running the Job Twice

If Boot/Task should auto-launch the Job, keep auto-run enabled:

~~~yaml
spring:
  batch:
    job:
      enabled: true
~~~

If you **write a custom `ApplicationRunner`** calling `JobLauncher.run(...)`, explicitly disable auto-run:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Have **only one primary launch mechanism** for a Batch Job. Combining auto-run and a custom runner for the same Job can trigger two `JobExecution`s or `JobInstanceAlreadyCompleteException` errors.

## 7. Minimal Reproduction: Single-Step Job Failure

To stay focused on the symptom, this example has **one Job and one Step**, no custom flow transitions, launched via Boot/Task auto-run.

### 7.1. Spring Boot Application

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class BatchExitDiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                BatchExitDiagnosticApplication.class, args);
    }
}
~~~

Do not create a custom `ApplicationRunner` that manually launches the Job in this example.

### 7.2. Job and Step with Toggleable Failure

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ReconciliationJobConfiguration {

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Value("${demo.fail:false}") boolean fail) {

        return new StepBuilder("importStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (fail) {
                        throw new IllegalStateException(
                                "Simulated data processing failure");
                    }

                    // Demo: no side effects outside the database.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job reconciliationJob(
            JobRepository jobRepository, Step importStep) {

        return new JobBuilder("reconciliationJob", jobRepository)
                .start(importStep)
                .build();
    }
}
~~~

`demo.fail` is a **property belonging to this demo**, not a Spring Cloud Task property. Passing `--demo.fail=true` makes the Step throw an exception; in the default single-Step Job flow, Spring Batch records `JobExecution` as `FAILED`.

### 7.3. application.yml for the PostgreSQL Lab

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://localhost:5432/task_batch_metadata
    username: task_runtime
    # Password provided securely via environment/secret.
  cloud:
    task:
      name: batch-exit-diagnostic
      initialize-enabled: false
      batch:
        fail-on-job-failure: false
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
~~~

**Prerequisites:** `TASK_*` and `BATCH_*` tables matching your exact Spring Cloud Task/Spring Batch versions have been migrated, the PostgreSQL driver is packaged in the artifact, the user has schema read/write privileges, and this database **contains no production data**.

You can practice with in-memory H2 and proper schema initialization, but H2 discards data once the JVM exits. To run post-mortem SQL queries from another process, use the PostgreSQL lab or an equivalent durable database.

## 8. Practice A: Observing False Success

Run with `fail-on-job-failure=false`:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=false
~~~

**Illustrative** log output, not verbatim fixed strings:

~~~text
ERROR ... importStep ... Simulated data processing failure
INFO  ... reconciliationJob ... status: FAILED
INFO  ... batch-exit-diagnostic ... task exit code: 0
~~~

**Expectation to verify:** `BATCH_JOB_EXECUTION.STATUS='FAILED'` while `TASK_EXECUTION.EXIT_CODE=0` can occur. On the default path, the process itself can also return `0`.

Linux/macOS:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=false
echo $?
~~~

PowerShell:

~~~powershell
java -jar batch-exit-diagnostic.jar --demo.fail=true --spring.cloud.task.batch.fail-on-job-failure=false
$LASTEXITCODE
~~~

**Do not** treat an `ERROR` log keyword as proof that the process exited non-zero. Nor should you compare a `TaskExecution` from one run against a `JobExecution` from a different run.

When re-running, Spring Batch identifies a `JobInstance` using the **job name and identifying JobParameters**. Manage parameters/inputs explicitly per test run to avoid restart errors or hitting an already-`COMPLETED` `JobInstance`.

## 9. Practice B: Enabling Batch → Task Failure Propagation

Run next against the lab metadata DB:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=true
~~~

Or configure:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

On the supported integration path, a `FAILED` Job **must mark the Task outcome as failed with a non-zero exit code**, typically `1`. Also inspect the **OS exit code**, because schedulers and Kubernetes inspect the process, not `JobRepository`.

When applying this property in production:

- Do not assume a Job failure always populates `TASK_EXECUTION.ERROR_MESSAGE`: Batch may have caught the exception and saved it in `BATCH_STEP_EXECUTION.EXIT_MESSAGE`.
- Do not check only the YAML inside the JAR while ignoring live profiles/CLI/env vars. The property might be overridden.
- Do not insert `System.exit(0)` to force-close the JVM: that hides failures.
- Do not manually edit `TASK_EXECUTION.EXIT_CODE` to "make the dashboard red"; fix the root cause.

### Also Test the Happy Path

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=false \
  --spring.cloud.task.batch.fail-on-job-failure=true
~~~

With an eligible `JobInstance`, expect Job `COMPLETED` and Task `0`. This confirms the change does not turn every run into a false failure.

## 10. SQL Queries: The Truth Across Both Repositories

### 10.1. Which Batch Job Failed?

~~~sql
SELECT
    JOB_EXECUTION_ID, JOB_INSTANCE_ID,
    STATUS, EXIT_CODE, EXIT_MESSAGE,
    START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Example:

| JOB_EXECUTION_ID | STATUS | EXIT_CODE |
| ---: | --- | --- |
| 3102 | FAILED | FAILED |
| 3101 | COMPLETED | COMPLETED |

Batch's `EXIT_CODE` is a **string** from `ExitStatus`.

### 10.2. Which Step Caused the Failure?

~~~sql
SELECT
    STEP_EXECUTION_ID, JOB_EXECUTION_ID,
    STEP_NAME, STATUS, EXIT_CODE, EXIT_MESSAGE,
    READ_COUNT, WRITE_COUNT, ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 3102
ORDER BY STEP_EXECUTION_ID;
~~~

Inspect `ROLLBACK_COUNT`, `READ_COUNT`, `WRITE_COUNT`, and the Step error. Already-`COMPLETED` Steps may have committed data before a later Step failed the Job.

### 10.3. What Exit Code Did Task Record?

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME,
    EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'batch-exit-diagnostic'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

In a false-success incident, you may see:

| TASK_EXECUTION_ID | TASK_NAME | EXIT_CODE | END_TIME |
| ---: | --- | ---: | --- |
| 5802 | batch-exit-diagnostic | 0 | Present |

Do not assume `ERROR_MESSAGE` will be non-null when a Batch Job fails: Task may not have received an `ApplicationFailedEvent` wrapping the Batch exception.

### 10.4. Official TaskExecution-to-JobExecution Link

When the application uses `spring-cloud-task-batch` with supported linking, `TASK_TASK_BATCH` stores the ID pair:

~~~sql
SELECT
    t.TASK_EXECUTION_ID,
    t.TASK_NAME,
    t.EXIT_CODE AS TASK_EXIT_CODE,
    j.JOB_EXECUTION_ID,
    j.STATUS AS BATCH_STATUS,
    j.EXIT_CODE AS BATCH_EXIT_CODE
FROM TASK_TASK_BATCH link
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = link.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = link.JOB_EXECUTION_ID
ORDER BY t.TASK_EXECUTION_ID DESC,
         j.JOB_EXECUTION_ID DESC;
~~~

**`TASK_EXECUTION_ID` is not `JOB_EXECUTION_ID`.** Never join the two tables merely because numeric IDs happen to match. If `TASK_TASK_BATCH` or links are missing, check the integration module, `TaskBatchExecutionListener`, schema, and versions; do not substitute heuristic joins when multiple Jobs/Tasks run concurrently.

### 10.5. SQL to Find Status Mismatches

~~~sql
SELECT
    t.TASK_EXECUTION_ID,
    t.TASK_NAME,
    t.EXIT_CODE AS TASK_EXIT_CODE,
    j.JOB_EXECUTION_ID,
    j.STATUS AS BATCH_STATUS
FROM TASK_TASK_BATCH link
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = link.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = link.JOB_EXECUTION_ID
WHERE j.STATUS = 'FAILED'
  AND t.EXIT_CODE = 0;
~~~

This is a **diagnostic query**; not every business policy dictates "any `FAILED` Job must fail the Task." Some best-effort Jobs are allowed to fail, provided that policy is explicitly defined and monitored.

## 11. When fail-on Is Enabled Yet Still Not Producing the Expected Outcome

Do not hastily drop `System.exit(1)` into some listener. Trace the **actual execution path**:

| Question | What to inspect |
| --- | --- |
| Was the property loaded? | Profiles, env vars, CLI args, Data Flow/Kubernetes launch properties |
| Are versions compatible? | Spring Boot/Cloud Task/Batch BOM compatibility; property and runner API generation |
| Is `spring-cloud-task-batch` present? | Runtime dependency tree and active auto-configuration |
| Did the Job actually run? | Spring Batch `Job` bean, `spring.batch.job.enabled`, job names |
| Who launched the Job? | Boot/Task integrated runner, custom `ApplicationRunner`, or async `JobLauncher` |
| Did the Job run twice? | Both Boot auto-run and a custom runner present |
| Did the Batch Job actually become `FAILED`? | `BATCH_JOB_EXECUTION.STATUS`, not just a Step `FAILED` |
| Is there custom exit code mapping? | `ExitCodeGenerator`, `ExitCodeExceptionMapper`, shell wrapper |
| Is an async worker still running? | Whether final `JobExecution` was written yet; whether a timeout exists |
| Are both metadata DBs right? | DataSources/schemas of `TaskRepository` and `JobRepository` |

Inspect the dependency tree with:

~~~bash
mvn dependency:tree
~~~

or:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

These commands are **practical troubleshooting guidance**, not part of a documentation build step.

### When a Custom JobLauncher Returns Too Early

An asynchronous `JobLauncher` can return a `JobExecution` still in `STARTING`/`STARTED`. If the runner inspects `getStatus()` immediately and returns, the Task can finish before the Job completes.

**Wait for the terminal state via `JobExplorer`/metadata with explicit timeouts and result handling.** `fail-on-job-failure`'s polling interval does not replace a business deadline or remote worker cancellation.

## 12. If You Need a Custom Runner: Map Results Synchronously Yourself

An application may need to launch Batch with custom parameters and **decide Task success itself**. In that case, disable Boot auto-run so the Job does not execute twice:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Example `ApplicationRunner` using a **synchronous** `JobLauncher`:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationRunner implements ApplicationRunner {

    private final JobLauncher jobLauncher;
    private final Job reconciliationJob;

    public ReconciliationRunner(
            JobLauncher jobLauncher, Job reconciliationJob) {
        this.jobLauncher = jobLauncher;
        this.reconciliationJob = reconciliationJob;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> dates = args.getOptionValues("businessDate");
        if (dates == null || dates.size() != 1) {
            throw new IllegalArgumentException(
                    "Required --businessDate=yyyy-MM-dd");
        }

        String businessDate =
                LocalDate.parse(dates.get(0)).toString();

        JobParameters parameters =
                new JobParametersBuilder()
                    .addString("businessDate", businessDate)
                    .toJobParameters();

        JobExecution execution =
                jobLauncher.run(reconciliationJob, parameters);

        // Valid only when JobLauncher waits for the Job to finish.
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                "Batch job not completed: id="
                + execution.getId()
                + ", status=" + execution.getStatus());
        }
    }
}
~~~

**Behavior:** if `JobExecution` ends in any status other than `COMPLETED`, the runner throws an unhandled exception. Spring Cloud Task captures the application failure path and records the failure status, provided the repository is operational.

**Constraints to remember:**

- Do not leave another automatic runner enabled for the same Job.
- If the launcher is **asynchronous**, wait for the final status by `JobExecution` ID before checking; `run(...)` returning does not mean the Job finished.
- Bind `JobParameters` to a **stable business key** so the right `JobInstance` restarts. Never append a random timestamp just to bypass `JobInstanceAlreadyCompleteException` without addressing duplicate-processing risk.
- With multiple Jobs, define a clear policy: fail-fast, aggregate all mandatory Jobs, or best-effort.
- Even a Batch-`COMPLETED` Job still requires checking business conditions (e.g., skip counts, output records).

**Do not mix this custom runner approach with an integrated runner that already launches the Job automatically.** Pick one launch path and prove it with tests.

## 13. Two-Way Testing Before Deployment

### 13.1. Mandatory Test Matrix

| Scenario | `demo.fail` | `fail-on-job-failure` | Expected Batch | Expected Task |
| --- | --- | --- | --- | --- |
| Success baseline | `false` | `false` | `COMPLETED` | `0` |
| Reproduce false success | `true` | `false` | `FAILED` | May be `0` |
| Failure mapping enabled | `true` | `true` | `FAILED` | **Non-`0`** when integration is active |
| No false failures | `false` | `true` | `COMPLETED` | `0` |
| DB bootstrap error | Any | Any | May have no `JobExecution` | May have no `TaskExecution` |
| Process-level failure | `true` | `true` | `FAILED` | Verify **OS exit code** separately |

Use an **isolated metadata DB and deliberate JobParameters** for each test to avoid picking up records from prior runs.

### 13.2. Why Tasklet Unit Tests Are Not Enough

A unit test merely invokes the tasklet and asserts an exception. It **does not prove**:

- Spring Batch created a `JobExecution` with `STATUS=FAILED`.
- Spring Cloud Task recorded a non-zero `TaskExecution.EXIT_CODE`.
- `spring-cloud-task-batch` was auto-configured.
- The JVM actually returned a non-zero exit code to the scheduler.
- Already-committed results from earlier chunks are handled safely on re-run.

You need **integration tests using real `JobRepository`/`TaskRepository`**, and when OS exit codes matter, a **process smoke test** running the packaged JAR.

### 13.3. Checking Process Exit

Linux/macOS:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=true
echo $?
~~~

PowerShell:

~~~powershell
java -jar batch-exit-diagnostic.jar --demo.fail=true --spring.cloud.task.batch.fail-on-job-failure=true
$LASTEXITCODE
~~~

The target chain when Batch must succeed is: **Batch `FAILED` → Task non-zero → OS non-zero**. If any link breaks, investigate the runner/exit-mapping mechanism rather than tweaking log messages.

**Never call `System.exit(...)` directly inside the same JVM running JUnit**, as it can terminate the entire test runner. Launch the JAR as a separate process to verify the OS exit code.

## 14. Kubernetes Jobs and Orchestrators

Kubernetes does not query `BATCH_JOB_EXECUTION`. It relies on container exit status and Job policy to determine success or failure. Example:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-exit-diagnostic-001
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch-exit-diagnostic:1.0
          args:
            - "--demo.fail=true"
            - "--spring.cloud.task.batch.fail-on-job-failure=true"
          envFrom:
            - secretRef:
                name: batch-metadata-db
~~~

This manifest is strictly for a test environment: image/Secret/schema must exist, the image must use a proper Java entrypoint, and it must never touch production data.

Inspecting:

~~~bash
kubectl get job batch-exit-diagnostic-001
kubectl describe job batch-exit-diagnostic-001
kubectl get pods -l job-name=batch-exit-diagnostic-001
kubectl logs job/batch-exit-diagnostic-001
~~~

If label selectors vary across Kubernetes versions, use the labels present on your actual Pod/Job. **Job Complete** only proves the Pod/process satisfied Job controller rules; it does not prove Batch data was processed accurately.

When Kubernetes retries are enabled:

- A new Pod can create a **new `TaskExecution` ID**.
- Spring Batch can restart the same `JobInstance` if `JobParameters` match and the previous execution failed.
- Earlier chunks may have committed; **idempotency/checkpoints** are essential.
- If an old Pod might still be alive due to an unclear timeout/sync, prevent concurrent overlap on the same work key.

**Never edit `TASK_EXECUTION.EXIT_CODE` to alter a Kubernetes Job condition.** Infrastructure relies on the process exit code; fix exit-code propagation inside the application.

## 15. Spring Cloud Data Flow and Multiple Batch Jobs

When launched via **Spring Cloud Data Flow**, `TaskExecution` and Batch `JobExecution` can appear on different views. If the Task returns `0` while the Job is `FAILED`, someone looking only at **Task status** can be misled.

Verify Data Flow points to the right **metadata DB**, has `TaskBatchExecutionListener`/link tables properly configured, and reads the actual Batch `JobExecution`. Never treat a Task–Batch link as proof that exit codes are mapped.

### One Task Running Multiple Jobs

Common policies:

| Policy | How Task outcome is determined |
| --- | --- |
| **Fail fast** | As soon as one mandatory Job fails, stop the flow and fail the Task |
| **Aggregate** | Run independent Jobs, then fail the Task if **any mandatory Job** failed |
| **Best-effort** | Secondary Jobs may fail, but emit alerts and retry separately |
| **Partial success** | Business allows partial completion, tracking unfinished portions explicitly |

A property targeting `BatchStatus.FAILED` on the supported runner path **cannot replace** an application-level aggregation policy across multiple Jobs or multiple launch triggers.

### Batch Flow Intentionally Masking a Step Failure

If a Step is `FAILED` yet the Job flow uses `end()` and reports `COMPLETED`, confirm whether that is an **intentional business rule** or a design flaw. If a Step failure must fail the entire Job, update the transition (`fail()` or equivalent for your API version) and test restart semantics before changing Task properties alone.

## 16. Common Pitfalls

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Assuming an `ERROR` log means Task exits 1 | False success when Batch handles exceptions internally | Inspect Job, Task, and OS exit code |
| Assuming `BATCH_JOB_EXECUTION.EXIT_CODE='FAILED'` means OS exit 1 | Confuses string Batch `ExitStatus` with process exit code | Check process exit code separately |
| Assuming `spring-cloud-task-batch` auto-maps failures | Default property is still `false` | Set `fail-on-job-failure=true` and test |
| Assuming `TaskBatchExecutionListener` makes Task FAIL | Listener primarily links executions | Verify runner and failure mapping |
| Assuming the property covers every custom runner | Custom runners may bypass the integrated Batch runner | Check `JobExecution` explicitly in custom runners |
| Assuming Step `FAILED` always makes Job `FAILED` | Job flow may call `end()` | Check both Step and Job status |
| Assuming non-zero Task `EXIT_CODE` guarantees Kubernetes Failed | OS process may return another code | Check Pod `terminated` exit code |
| Assuming a failed Job rolled back all data | Prior chunks may have committed | Reconcile / checkpoint / enforce idempotency |
| Assuming `END_TIME IS NULL` means process is alive | Task may have died before metadata update | Cross-check Pod/PID/logs |
| Manually editing exit code via SQL | Corrupts history without fixing root cause | Fix config/code and record audit note |
| Calling `System.exit(0)` in CLI tasks | Hides failures from scheduler | Never force a fake 0 exit |
| Adding a random timestamp on every retry | Can reprocess entire dataset | Restart using stable business keys and `JobParameters` |

## 17. Production Diagnostic Runbook

1. **Collect identifiers:** Task/Job name, `TaskExecution` ID, `JobExecution` ID, pod/process ID, work key, timestamp, and artifact version.
2. **Verify Batch:** read `BATCH_JOB_EXECUTION.STATUS`/`EXIT_CODE` and `BATCH_STEP_EXECUTION`; locate the failing step and cause.
3. **Verify Task:** read `TASK_EXECUTION.EXIT_CODE`/`END_TIME`/`ERROR_MESSAGE` on the right metadata DB.
4. **Verify process:** inspect shell exit code, Kubernetes `terminated.exitCode`/Job condition, or scheduler outcome.
5. **Verify business state:** check committed records, skip counts, sent files/messages/APIs, and idempotency readiness.
6. **Verify effective config:** `fail-on-job-failure`, Spring Boot/Cloud Task/Batch BOMs, `spring-cloud-task-batch`, DataSource/schema.
7. **Verify launch path:** default runner, custom runner, async `JobLauncher`, runner order, risk of double launch.
8. **Verify Batch flow:** did the Job truly become `FAILED`, or did a failed Step hit `end()` and turn into `COMPLETED`?
9. **Fix root cause:** enable proper mapping, fix flow transitions, await async Jobs, fix wrapper/OS exit, add timeouts/idempotency.
10. **Verify in staging:** Job status, Task exit code, process exit code, and business outputs must all match.
11. **Decide on retry:** confirm old process stopped, checkpoint/`JobInstance` are valid, and side effects won't duplicate.
12. **Add alerting:** flag Batch `FAILED` paired with Task `EXIT_CODE=0`, and persist official Task–Batch correlation.

### Verification Checklist

- [ ] Distinguish `BatchStatus`, `ExitStatus`, Task exit code, and OS exit code.
- [ ] Understand why Batch `FAILED` can still yield Task `0`.
- [ ] Know the default and purpose of `spring.cloud.task.batch.fail-on-job-failure`.
- [ ] Verify versions, `spring-cloud-task-batch`, and actual Batch execution path.
- [ ] Read `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and `TASK_EXECUTION`.
- [ ] Use `TASK_TASK_BATCH` to correlate executions when integration supports it.
- [ ] Test both succeeding and failing Jobs.
- [ ] Verify the OS process exit code outside the JUnit JVM.
- [ ] Never evaluate an asynchronous Job's outcome before completion.
- [ ] Recognize that a Step failure may not fail the Job if the flow transitions otherwise.
- [ ] Never equate a single chunk's rollback with a full-Job rollback.
- [ ] Enforce idempotency/restartability and alerting across scheduler/Kubernetes/SCDF.
- [ ] Never mask failures with `System.exit(0)` or manual SQL metadata edits.

## 18. Summary

**A failed Spring Batch Job does not automatically mean Spring Cloud Task or the JVM failed.** `JobRepository` stores `JobExecution` and `StepExecution` states; `TaskRepository` stores the Task run's exit code; and Kubernetes/schedulers observe the **process exit code**. These three layers can diverge when Batch catches exceptions into metadata without propagating them to the application lifecycle.

On the supported integration path, **`spring.cloud.task.batch.fail-on-job-failure=true`** converts `BatchStatus.FAILED` into a non-zero Task exit code. With custom Batch flows, multiple Jobs, or asynchronous `JobLauncher`s, add application-level outcome policies and separately verify the **process exit code**. Always diagnose across **Batch, Task, process, and business data**, rather than trusting a single log line or status code.

### References

- [Spring Cloud Task — Batch Job Exit Codes and TaskBatchExecutionListener](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Lifecycle and TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud — Configuration Properties: fail-on-job-failure](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
- [Spring Batch — BatchStatus, ExitStatus, and Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html)
- [Spring Batch — JobExecution, StepExecution, and Restarts](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Boot — SpringApplication and Exit Codes](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Kubernetes — Job Controller and Error Handling](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
