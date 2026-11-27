# Job Runner Ordering, Job Restarts, and Identifying Parameters

## 1. Three Questions to Resolve When Combining Spring Cloud Task with Spring Batch

A **Spring Cloud Task** application is typically launched on a schedule or on demand, performs a finite task, and exits. If the work involves multiple steps, chunk processing, or requires checkpoints and restarts, the application can use **Spring Batch** to execute Jobs.

When combining the two frameworks, developers must separate three concerns:

1. **Who launches the Job, and when?** Spring Boot has a built-in mechanism to auto-launch a Job at startup; the application can also use `ApplicationRunner` or `CommandLineRunner` to call `JobLauncher` itself. Combined improperly, the Job can end up launched twice.
2. **When a Job fails, is the next run a restart or a new JobInstance?** Spring Batch relies on `JobRepository` history along with `JobExecution` status and the Job's restartability to decide.
3. **Which parameters define "the same JobInstance"?** `JobParameters` carry an **identifying** flag. Changing an identifying parameter creates a different JobInstance identity; changing a non-identifying parameter does not change identity.

For example, the `daily-close-task` closes daily revenue for tenant `tenant-A` on `2026-11-23`. A CronJob runs at 02:00, but the process dies mid-way while writing files. The next day, an operator runs a backfill for the same date. With the right identifying parameters, Spring Batch recognizes the **previous JobInstance** and creates a new execution to restart from the checkpoint. If a fresh timestamp is accidentally put into an identifying parameter, Batch treats it as a **different JobInstance** and may reprocess from the start.

**Spring Cloud Task tracks the application run; Spring Batch tracks Jobs and Steps.** These two metadata layers are related, not identical.

## 2. Diagram of Execution Layers and Repositories

~~~mermaid
flowchart TB
    C["CronJob / API / CLI"] --> T["Spring Boot + Spring Cloud Task process"]
    T --> TR["TaskRepository: TaskExecution"]
    T --> R["Batch startup runner or custom runner"]
    R --> JL["JobLauncher / JobOperator"]
    JL --> JR["JobRepository"]
    JR --> JI["JobInstance = Job name + identifying parameters"]
    JI --> JE["One or more JobExecutions"]
    JE --> S["StepExecution + checkpoint"]
    S --> B["Business DB / file / external service"]
    TR -. "TaskBatchExecutionListener when integration is present" .-> JR
~~~

| Concept | Tracked Unit | ID and Function |
|---|---|---|
| `TaskExecution` (Spring Cloud Task) | A single run of the **task application** | `taskExecutionId`, start/end timestamps, process/task exit code |
| `JobInstance` (Spring Batch) | A Job with the **same name and same identifying parameter set** | Identifies a logical batch unit of work |
| `JobExecution` (Spring Batch) | One run or re-run of a `JobInstance` | Status `STARTED`, `FAILED`, `COMPLETED`, `STOPPED`, etc. |
| `StepExecution` | One execution of a Step within a JobExecution | Read/write/skip counters and Step status |
| `ExecutionContext` | Persisted state supporting restarts | Reader checkpoints, progress metrics, etc., when properly configured |
| Business outcome | Data actually processed | Requires dedicated idempotency/transactions |

A single `TaskExecution` can run one or more Jobs depending on design. A single `JobInstance` can be re-executed across multiple application launches and therefore relate to **multiple different `TaskExecution`s**. The bidirectional link between task and batch can be persisted via the `spring-cloud-task-batch` integration module.

## 3. Who Launches the Job at Spring Boot Startup?

### 3.1. Spring Boot's Automatic Job Runner

When Spring Boot auto-configures Spring Batch and finds **one `Job` bean**, the startup runner mechanism can **automatically run the Job**. In the Spring Boot 3.x and 4.x lines, the documented class is **`JobLauncherApplicationRunner`**. It participates in the startup runner sequence like other `ApplicationRunner` beans, has its own execution order, and uses Batch infrastructure to launch the Job.

With **multiple Job beans**, you must specify which Job to launch, for example:

~~~properties
spring.batch.job.name=closeDayJob
~~~

To **disable auto-launching** when the application wants to choose Jobs itself, set:

~~~properties
spring.batch.job.enabled=false
~~~

For example, in a task containing two Jobs `importCustomersJob` and `closeDayJob`, do not assume Spring Boot will automatically run both in bean declaration order. Either specify the target Job or write explicit orchestration logic.

**Version notes:**

- Spring Boot 3.x provides `JobLauncherApplicationRunner` in `org.springframework.boot.autoconfigure.batch` and integrates with Spring Batch 5.x.
- Spring Boot 4.x moves some auto-configuration packages and uses APIs matching Spring Batch 6.x; consult the exact release's Javadoc when customizing runners.
- Legacy Spring Boot 2.x docs may mention `spring.batch.job.names`, or the older `JobLauncherCommandLineRunner`. Never copy legacy properties/classes into a new project without checking.
- Adding `@EnableBatchProcessing` or extending `DefaultBatchConfiguration` can cause Spring Boot to **back off Batch auto-configuration**, including schema initialization; only use them when intentionally managing all infrastructure manually.

### 3.2. Application-Provided Custom Runner

If you need custom parameter parsing rules, input validation, dynamic Job selection, status verification, and consistent exit code handling, launch the Job from an `ApplicationRunner`. When doing so, **disable auto-launch** to avoid duplicate execution:

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: daily-close-task

  batch:
    job:
      enabled: false

  cloud:
    task:
      name: daily-close-task
~~~

Choosing between the automatic runner and a custom runner:

| Requirement | Reasonable Approach |
|---|---|
| Application has one Job and needs no complex control | Spring Boot auto-launch |
| Multiple Jobs exist, but each run executes one fixed Job | `spring.batch.job.name` |
| Need input validation, Job selection, business key computation, and `JobExecution` checks | Disable auto-launch; write a custom runner |
| Need multiple Jobs running with dependency rules | Use structured Job/Step flows, or an external orchestrator |
| Need to re-run a failed JobInstance | Preserve identifying parameters and use proper restart/`JobOperator` mechanisms |

Never enable two independent launch mechanisms just to "make sure the Job runs": if both the auto-runner and a custom runner invoke the same Job, the second call may hit `JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException`, or unintentionally create a new JobInstance.

## 4. "Job Runner Order" Covers Three Different Kinds of Ordering

It is easy to confuse **startup runner order**, **multi-Job order**, and **Step order within a Job**.

### 4.1. Order of ApplicationRunner and CommandLineRunner

Spring Boot collects `ApplicationRunner` and `CommandLineRunner` beans, sorts them by `Ordered` / `@Order`, and invokes them during startup. Lower order values take precedence and run first.

For example, to run a preflight check before Job orchestration:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PreflightRunner implements ApplicationRunner {

    @Override
    public void run(
            org.springframework.boot.ApplicationArguments args) {
        // Validate secrets, data sources, and business parameters.
        System.out.println("Preflight OK");
    }
}
~~~

If the Job-launching runner has order `20`, the check at `10` runs first. However, **never rely on default ordering** among unordered runners; and startup ordering never replaces proper transactions or dependencies inside a Job.

### 4.2. Spring Cloud Task + Batch Runner Ordering

Spring Cloud Task provides its own configuration for **propagating Job failures into the task exit code**:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

According to Spring Cloud Task documentation, when enabled, the framework replaces the default Batch startup runner with a failure-aware runner; a Job ending with `BatchStatus.FAILED` can yield a non-zero task exit code (typically defaulting to `1`, or per configured exit code mapping).

Documentation also exposes a property to configure the integrated runner's order:

~~~properties
spring.cloud.task.batch.applicationRunnerOrder=100
~~~

This is the **order of the batch-job-launching runner within the startup runner sequence**; it **does not reorder Steps** and **does not order independent Jobs across a cluster**. Exact property names and behavior depend on the Spring Cloud Task version. If you rely on ordering, inspect dependencies, configuration metadata, and startup logs of your deployed application.

For example, with a `PreflightRunner` at `@Order(10)` and the integrated runner at order `100`, preflight runs before the Job. Still, if preflight fails, let the exception propagate to startup so the Job does not proceed.

### 4.3. Step Ordering Within a Job

If the requirement is "validate first, then export data," express it in the **Job flow**:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayJobConfiguration {

    @Bean
    Job closeDayJob(
            JobRepository jobRepository,
            Step validateInputStep,
            Step calculateRevenueStep,
            Step publishResultStep) {

        return new JobBuilder("closeDayJob", jobRepository)
            .start(validateInputStep)
            .next(calculateRevenueStep)
            .next(publishResultStep)
            .build();
    }
}
~~~

The example above illustrates **Spring Batch 5 / Spring Boot 3**; the three Step beans must be implemented separately. Spring Batch coordinates Steps via flows and restart policies, while the runner simply starts the Job. When steps belong to the same workflow with checkpoints and failure conditions, defining order in the Job flow is far more reliable and testable than creating three separate startup runners.

## 5. JobInstance, JobExecution, and JobParameters

### Identity Definition

Spring Batch identifies a JobInstance by:

**`JobInstance = Job name + set of JobParameters with identifying=true`**

Example:

~~~text
Job name: closeDayJob

identifying:
  tenant = tenant-A
  businessDate = 2026-11-23
  revision = 1

non-identifying:
  traceId = trace-91
  requestedBy = operator
~~~

If `closeDayJob` is launched twice with the identifying parameters above, both runs belong to **one JobInstance** (assuming the same repository and metadata were not purged). If the first run fails and the Job allows restarts, the next run creates a **new JobExecution** for the same JobInstance.

Illustrative table:

| Invocation | Job name | Identifying parameters | Non-identifying | Relationship |
|---|---|---|---|---|
| A | `closeDayJob` | tenant=A, date=23, rev=1 | traceId=t1 | JobInstance 101, JobExecution 201 |
| B after A FAILED | `closeDayJob` | tenant=A, date=23, rev=1 | traceId=t2 | **Same** JobInstance 101, JobExecution 202 (restart) |
| C | `closeDayJob` | tenant=A, date=24, rev=1 | traceId=t3 | New JobInstance 102 |
| D | `closeDayJob` | tenant=A, date=23, rev=2 | traceId=t4 | New JobInstance 103 |
| E | `otherJob` | tenant=A, date=23, rev=1 | traceId=t5 | Separate JobInstance because Job name differs |

These are synthetic IDs illustrating relationships, not real run output.

### Are Non-Identifying Parameters Meaningless?

No. They can affect **logging, tracing, notification targets, or performance-tuning choices**, while not participating in JobInstance identity. Consequently, you **must not** let a non-identifying parameter alter **business dataset semantics** across restarts.

For example, if `sourceFile` genuinely determines the input dataset, it should normally be stabilized with an identifying parameter, fingerprint, or explicit snapshot. Treating `sourceFile` as non-identifying and swapping in a different file on restart can cause a JobInstance to resume an old checkpoint against a new input source, corrupting data.

## 6. Declaring Identifying and Non-Identifying Parameters in Java

In Spring Batch 5, `JobParametersBuilder` lets you specify the identifying flag explicitly:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", "tenant-A", true)
    .addString("businessDate", "2026-11-23", true)
    .addLong("revision", 1L, true)
    .addString("traceId", "request-8eaf", false)
    .toJobParameters();
~~~

`true` means identifying; `false` means non-identifying. In common overloads where the flag is omitted, `identifying` typically defaults to `true`. Therefore, never put `System.currentTimeMillis()`, `UUID.randomUUID()`, or `run.id` into `JobParameters` out of habit and then wonder why Batch keeps creating new JobInstances.

Wrong example when intending to restart **the same period**:

~~~java
new JobParametersBuilder()
    .addString("businessDate", "2026-11-23")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
~~~

Here `run.id` is identifying by default, so each run creates a new JobInstance, losing checkpointed restart semantics.

Replace with:

~~~java
new JobParametersBuilder()
    .addString("businessDate", "2026-11-23", true)
    .addString("tenant", "tenant-A", true)
    .addString("traceId", java.util.UUID.randomUUID().toString(), false)
    .toJobParameters();
~~~

The sample targets **Batch 5**; API packages changed in Batch 6. When adopting newer versions, verify constructors, parameter types, and `JobOperator` against that version's documentation.

### Inspecting the Flag in JobRepository

Spring Batch metadata usually stores the identifying flag in each run's parameter table. With the corresponding Spring Batch 5 schema, you can check:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :execution_id
ORDER BY PARAMETER_NAME;
~~~

If prefixes/schemas were customized, adjust table and column names to match your deployed DDL. Spring Cloud Task's **`TaskRepository`** uses a separate set of tables, such as `TASK_EXECUTION`, and does not replace Spring Batch's JobParameters metadata.

## 7. Restarting a Job vs. Creating a New JobInstance: How Do They Differ?

| Prior Status | Re-invoked with Same Name + Identifying Params | Typical Outcome |
|---|---|---|
| No existing JobInstance | Fresh start | New JobInstance and first JobExecution |
| `FAILED` | Restart allowed, repository/step state valid | **New JobExecution, same JobInstance**; eligible Steps resume from checkpoint |
| `STOPPED` | Restart allowed | New JobExecution, same JobInstance |
| `COMPLETED` | Re-invoked with same identifying parameters | Usually throws `JobInstanceAlreadyCompleteException` |
| `STARTED` and genuinely running | Concurrent invocation | Typically hits `JobExecutionAlreadyRunningException` |
| `STARTED` but JVM died abruptly | Immediate re-invocation | Repository may think job is still running; requires verified recovery procedure |
| Job configured as non-restartable | Re-invoked after FAILED | `JobRestartException` or policy rejection |
| One identifying parameter changed | Re-invoked | **New JobInstance**; does not reuse previous instance's checkpoint |

**Restart** means continuing **the same JobInstance**, potentially skipping completed Steps and restoring reader/processor/writer state from `ExecutionContext` if the Job/Step is designed to be restartable. It **does not guarantee** avoiding duplicate non-transactional side effects.

**New instance** means a distinct logical unit of work by Batch's definition: the Job initializes from scratch under a different set of identifying parameters. That is valid for a new date or new revision, but **is not a true retry** of the old period.

~~~mermaid
flowchart TD
    A["Receive request to run closeDayJob"] --> B["Build stable identifying JobParameters"]
    B --> C{"Does JobInstance with same key exist?"}
    C -- "No" --> D["New JobInstance + first JobExecution"]
    C -- "Yes" --> E{"Previous status?"}
    E -- "FAILED / STOPPED" --> F["Restart: new JobExecution, same instance"]
    E -- "COMPLETED" --> G["Do not re-run same instance"]
    E -- "Currently STARTED" --> H["Reject duplicate / verify process"]
    D --> I["JobRepository tracks step/checkpoint"]
    F --> I
    G --> J["Check business outcome, return prior result"]
    H --> K["Investigate / recover if process actually died"]
~~~

Launch-time exceptions like `JobInstanceAlreadyCompleteException` differ from a `JobExecution` that was created and then finished in `FAILED` status. You must handle both **launch failures** and **post-launch execution failures**.

## 8. Re-running with JobLauncher and JobOperator

### 8.1. Re-running with JobLauncher in Spring Batch 5

`JobLauncher.run(job, parameters)` creates or re-runs a `JobExecution` depending on the repository and `JobInstance` state. If `JobLauncher` runs synchronously, once the method returns, the caller can inspect `JobExecution.getStatus()`.

~~~java
JobExecution execution = jobLauncher.run(job, parameters);
if (execution.getStatus() != BatchStatus.COMPLETED) {
    throw new IllegalStateException(
        "Batch job ended with " + execution.getStatus());
}
~~~

Note: **a Job can fail during execution while `JobLauncher.run` still returns a `JobExecution`** instead of throwing an exception. Exceptions typically occur when the Job cannot be launched validly (such as invalid parameters or an already completed instance); hence **checking `JobExecution` status is mandatory** if the task must return a failure exit code.

If `JobLauncher` is configured **asynchronously**, `run(...)` may return while the Job is still `STARTING`/`STARTED`. In that case, the code above cannot act as a "wait for completion" check; you must poll by ID with a timeout, or use a synchronous launcher for short-lived task applications when appropriate.

### 8.2. JobOperator and Administrative Operations

`JobOperator` provides capabilities such as starting, querying, stopping, restarting, and starting the next instance. Exact APIs vary across Spring Batch lines:

- **Restart failed/stopped JobExecution**: resumes the **old JobInstance** when eligible.
- **Start next instance**: uses a `JobParametersIncrementer` to generate **new** identifying parameters to start a **new JobInstance**.
- **Stop**: requests a controlled stop while a Job is running, not an abrupt kill.
- **Recover**: in releases providing recovery APIs for crashed/stuck states, verify the process is truly dead and satisfy preconditions before recovering.

`RunIdIncrementer` or a custom `JobParametersIncrementer` is appropriate when you **genuinely want to create a new JobInstance version**. It should not be invoked blindly on every retry where the business merely wants to resume the same day.

For Spring Batch 5 applications, one way to restart after failure is re-launching with the same Job name and **same identifying parameters**, if the job configuration supports restarts. You can also use `JobOperator.restart(executionId)` per the version's API. In Spring Batch 6, several `JobLauncher`/`JobOperator` APIs were changed or deprecated; do not mix up the two signature sets.

## 9. Manual Task Configuration Launching One Job and Checking Outcomes

This section demonstrates an approach **without Spring Boot auto-launch**. With Spring Boot 3 / Spring Batch 5, we control parameter validation and Job result checking ourselves. The code assumes a `closeDayJob` bean and Spring Batch `JobRepository`/`JobLauncher` infrastructure already exist.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayRunnerConfiguration {

    @Bean
    ApplicationRunner launchCloseDayJob(
            JobLauncher jobLauncher,
            @Qualifier("closeDayJob") Job closeDayJob) {

        return args -> {
            String tenant = oneRequired(args.getOptionValues("tenant"), "tenant");
            String dateString = oneRequired(args.getOptionValues("date"), "date");
            LocalDate businessDate = LocalDate.parse(dateString);

            JobParameters params = new JobParametersBuilder()
                .addString("tenant", tenant, true)
                .addString("businessDate", businessDate.toString(), true)
                .addLong("revision", 1L, true)
                .addString("traceId", UUID.randomUUID().toString(), false)
                .toJobParameters();

            // Assumes synchronous JobLauncher (common default).
            JobExecution result = jobLauncher.run(closeDayJob, params);

            if (result.getStatus() != BatchStatus.COMPLETED) {
                throw new IllegalStateException(
                    "Job failed: " + result.getStatus()
                    + ", executionId=" + result.getId());
            }
        };
    }

    private static String oneRequired(List<String> values, String name) {
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException("Missing --" + name + "=...");
        }
        return values.get(0);
    }
}
~~~

Accompanying configuration:

~~~yaml
spring:
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
  cloud:
    task:
      name: close-day-task
~~~

Run:

~~~bash
java -jar close-day-task.jar --tenant=tenant-A --date=2026-11-23
~~~

**Why is this a sound restartable example?**

- `tenant`, `businessDate`, and `revision` are identifying, remaining stable across retries.
- `traceId` is non-identifying, so it can vary per `TaskExecution` without creating a new `JobInstance`.
- The runner completes normally only when `JobExecution` is `COMPLETED`; when the Job fails, the exception propagates through Spring Boot/Spring Cloud Task's lifecycle.
- If re-run after the `JobInstance` is already `COMPLETED`, Batch may throw `JobInstanceAlreadyCompleteException`. In an **idempotent** workflow that wants to treat "already completed earlier" as a valid outcome, explicitly **query `JobRepository` and business results** to return `ALREADY_COMPLETED` per policy rather than swallowing all exceptions.
- The example does not cover an asynchronous `JobLauncher`; if you swap in an async executor or launcher, design proper status waiting/polling.

For the JVM exit code to be read accurately by the orchestrator, ensure the task application closes its context and has an exit-code policy aligned with the runner throwing errors. Do not just call `System.out.println("failed")` and return normally.

## 10. With Auto-Runner: Task Exit Code and Job Status Can Diverge

A common mistake: a Spring Batch Job runs and transitions to `BatchStatus.FAILED`, yet the Spring Boot application sees no exception propagate out of the runner and the **process exit code remains 0** under default configuration. Spring Cloud Task may record task success at the process level even though the Batch Job failed.

With Spring Cloud Task batch integration supporting this feature, configuring:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

lets the framework reflect a `FAILED` Job as a non-zero task exit code via its corresponding mechanism. If you need **distinct exit codes per Job failure type**, check `ExitCodeGenerator` mechanisms and the exact runner API of your release, or write a controlled custom runner/mapping layer.

Especially avoid these misconceptions:

| Observed State | What Does It Prove? | What Does It NOT Prove? |
|---|---|---|
| `TaskExecution.exitCode=0` | The task app exited according to its exit-code policy | That the Batch Job necessarily `COMPLETED` |
| `JobExecution.status=COMPLETED` | Batch job finished according to its flow | That external side effects were processed exactly-once |
| `JobExecution.status=FAILED` | Batch Job had a failing step | That all business data rolled back |
| Missing `TaskExecution.endTime` | Task has not been finalized in metadata | That the process is dead (it may still be running) |
| `JobInstanceAlreadyCompleteException` | JobInstance with those identifying params already completed earlier | That this invocation ran and completed a fresh business cycle |

If both `TaskRepository` and `JobRepository` exist, monitor **both** and reconcile against business data. The framework cannot write metadata after `SIGKILL`; a Job can remain `STARTED` in the repository after the JVM has actually died.

## 11. Relationship Between TaskExecution and JobExecution

When `spring-cloud-task-batch` is integrated with an eligible Job bean, Spring Cloud Task can auto-configure **`TaskBatchExecutionListener`** to link a `JobExecution` to the `TaskExecution` that launched it. This relationship supports traceability and does not replace each framework's own metadata.

~~~mermaid
sequenceDiagram
    participant O as CronJob / CLI
    participant T as Spring Cloud Task
    participant B as Spring Batch
    participant R as Repositories
    O->>T: Launch process attempt 1
    T->>R: TaskExecution 501
    T->>B: closeDayJob / identifying key K
    B->>R: JobInstance 88, JobExecution 901
    B-->>T: FAILED
    T-->>O: Task exits per exit policy
    O->>T: Retry with same key K
    T->>R: TaskExecution 502
    T->>B: closeDayJob / identifying key K
    B->>R: Same JobInstance 88, JobExecution 902
    B-->>T: COMPLETED
    T-->>O: Task completes
~~~

A new `TaskExecution` **does not imply** a new `JobInstance`. When reconciling re-runs, use:

- `TaskRepository` to see how many times the application launched.
- `JobRepository` to see the `JobInstance`, `JobExecution`s, and `StepExecution`s.
- The integration bridge table (if configured and supported in the schema) to connect the two metadata stores.
- Business outcome tables to confirm data truly committed and prevent duplicate effects.

If a single task run executes multiple Jobs, the relationship can be **one TaskExecution → many JobExecutions**. Never assume a one-to-one mapping in queries or dashboards.

## 12. Command-Line Parameters: Distinguishing Spring Properties from JobParameters

With **auto-runner** in Spring Boot 3.x, options prefixed with `--` are treated by Spring Boot as **application properties**. Job parameters are typically passed **without `--`**:

~~~bash
java -jar batch-task.jar --spring.batch.job.name=closeDayJob tenant=tenant-A businessDate=2026-11-23
~~~

In this example:

- `--spring.batch.job.name=closeDayJob` is a startup configuration option.
- `tenant=tenant-A` and `businessDate=2026-11-23` are arguments parsed by the batch runner's converter.
- Type resolution and identifying-flag rules of **`JobParametersConverter`** depend on version and converter syntax; for strict control, use `JobParametersBuilder` inside a custom runner.

**Do not mix up** the auto-runner example above with the custom `ApplicationRunner` example in section 9: the custom runner reads `--tenant` and `--date` via `ApplicationArguments` and **constructs `JobParameters` itself**. Those are two distinct CLI patterns that must be designed consistently.

In Spring Boot 3.5, documentation requires passing **both identifying and non-identifying job parameters** again when restarting from the CLI: non-identifying parameters from the previous run are not automatically copied verbatim. Ensure non-identifying fields like tracing or runtime settings do not accidentally change processing semantics on restart.

## 13. Real-World Scenarios and How to Handle Them

### Job Completed, Then CronJob Runs Again the Same Day

If identifying parameters stay unchanged, Spring Batch refuses to create a new `JobExecution` for a `COMPLETED` `JobInstance`. If the business wants a **safe no-op backfill**, check prior results and return `ALREADY_COMPLETED` per policy while confirming business outputs exist. Never inject a random `run.id` to bypass this rule.

### Job Failed Mid-Step and Restarts

Keep the same identifying parameters. Spring Batch creates a new `JobExecution` on the same `JobInstance` if restarts are allowed, using `ExecutionContext` to restore the Step. Readers/writers must be designed to be restartable; data written outside transactions or in non-checkpointed steps still requires idempotency.

### Running Process Killed, Repository Still Shows STARTED

Do not immediately re-run just because the old process is no longer visible on the local machine. Cross-check Pods/Jobs/processes across the entire cluster, data stores, leases, and repositories. Once certain the old instance is dead, follow **the recovery procedure for your exact Spring Batch version**. Spring Batch 6 offers recovery APIs in some releases; earlier versions require different operational steps. Never mass-update `BATCH_JOB_EXECUTION.STATUS` via SQL without investigating first.

### Two Processes Launch the Same JobInstance Simultaneously

`JobRepository` enforces concurrency checks and can reject one launch with `JobExecutionAlreadyRunningException`. Still, **you must also enforce business locks/unique constraints** on output tables to protect external side effects and processes outside the same repository or outside Spring Batch.

### Request to Run a New Revision After Adjusting Figures

Intentionally create an identifying parameter `revision=2`. A new `JobInstance` is appropriate here; define how revision 2's output replaces or adjusts revision 1, and ensure business tables enforce versioning rules properly.

### Multiple Jobs Need Ordering or Dependencies

Do not rely on bean creation order or bean names. If the steps belong to one batch workflow, use Job flows/Step transitions. If they are two independent Jobs with a dependency relationship, use a dedicated orchestrator or a coordinating runner with explicit status, retry, and idempotency handling.

## 14. Diagnosing via JobRepository and TaskRepository

With the corresponding Spring Batch schema and default prefix, these SQL queries help investigate runs (adjust table/column names for your release):

~~~sql
-- List JobInstances by job name.
SELECT JOB_INSTANCE_ID, JOB_NAME, JOB_KEY
FROM BATCH_JOB_INSTANCE
WHERE JOB_NAME = 'closeDayJob'
ORDER BY JOB_INSTANCE_ID DESC;

-- Executions and statuses for a JobInstance.
SELECT JOB_EXECUTION_ID, JOB_INSTANCE_ID,
       STATUS, EXIT_CODE, START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID = :job_instance_id
ORDER BY JOB_EXECUTION_ID;

-- Identifying and non-identifying parameters.
SELECT JOB_EXECUTION_ID, PARAMETER_NAME,
       PARAMETER_VALUE, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :job_execution_id;
~~~

The Spring Batch 5 line uses a column layout like above in its familiar JDBC schema. Newer releases may change column names, repository structures, or datastore types, so verify against actual DDL. For Spring Cloud Task, separately query `TASK_EXECUTION` by `TASK_EXECUTION_ID`.

**Never infer "the Job completed business work" solely from `EXIT_CODE=COMPLETED`** if there are external DB side effects, asynchronous steps, or message retries. Always verify business outputs and downstream receivers.

## 15. Common Errors Table

| Symptom | Possible Cause | Fix |
|---|---|---|
| Job runs twice as soon as app boots | Both auto-runner and custom runner are enabled | Pick one launch mechanism; disable auto-run when launching manually |
| Two Job beans exist, wrong Job runs | Job name not specified | Set `spring.batch.job.name` or use explicit orchestration |
| Preflight runs after Job | ApplicationRunner order not configured | Set `@Order` and configure the integrated runner's order if applicable |
| Restart fails with `JobInstanceAlreadyCompleteException` | Same identifying params already completed | Return prior outcome / evaluate reprocessing instead of arbitrarily changing keys |
| Every retry reads from the beginning | Adding a new timestamp or identifying `run.id` | Keep identifying keys stable; review `JobParametersBuilder` |
| Job FAILED yet task exits 0 | Job status not propagated to task exit code by default | Enable `fail-on-job-failure` or check `JobExecution` in a custom runner |
| Job killed, repository still shows STARTED | Final status could not be written | Verify process state, perform controlled recovery |
| Restart reports instance already running | Active run exists or metadata not yet recovered | Check cluster and `JobRepository` before recovering |
| Changing non-identifying param corrupts data | Used a param affecting input data as non-identifying | Include in identifying key / pin snapshot / validate |
| TaskExecution and Batch metadata tables mismatch | Viewing two distinct repository levels | Use bridge IDs, Batch listener, reconcile business state |
| Job uses async Step yet task exits early | Launcher/runner returned before Job reached terminal state | Wait for real completion and verify `BatchStatus` |
| Cannot restart Step | Job/Step not restartable or missing checkpoint | Inspect configuration, reader/writer, and `ExecutionContext` |

## 16. Hands-on Verification Exercise

Create a Spring Cloud Task + Spring Batch application with `closeDayJob` consisting of two Steps: input validation and result writing. Use a persistent `JobRepository`, a business key of tenant/date/revision, and a business output table with a unique constraint.

1. Configure `spring.batch.job.enabled=false`, write a custom runner following section 9, and ensure a synchronous `JobLauncher`.
2. Run for `2026-11-23` while intentionally throwing an error mid-write. Observe `TaskExecution`, `JobInstance`, and `JobExecution` in `FAILED` status.
3. Re-run with the **same identifying parameters**, changing only `traceId`. Verify `JobInstance` ID stays unchanged while `JobExecution` ID changes.
4. Verify Step restart resumes accurately from the checkpoint and business outputs are not duplicated.
5. Re-run once more after `JobInstance` is `COMPLETED`. Observe `JobInstanceAlreadyCompleteException` or your wrapper's "already completed" policy.
6. Change `revision` to 2: this is a **new `JobInstance`**; verify it is not mistaken for a restart of revision 1.
7. Enable auto-runner in a separate test environment, configure `spring.batch.job.name` and `spring.cloud.task.batch.fail-on-job-failure=true` if supported; verify the orchestrator sees Job failures.
8. Launch two processes with the same `JobInstance` simultaneously to test concurrency controls; do not test only sequential runs.
9. Simulate a mid-Step crash/kill, reconciling metadata against actual running processes before performing recovery.

| What to Observe | Expected Result |
|---|---|
| First run FAILED, retry with same identifying params | Same JobInstance, additional JobExecution |
| Change non-identifying `traceId` | JobInstance unchanged |
| Change identifying `revision` | New JobInstance created |
| Re-run COMPLETED JobInstance | Does not automatically re-run the same instance |
| Batch Job FAILED | Task exit code reflects failure per configuration or custom logic |
| JVM killed | Metadata may not be finalized; reconcile before retrying |
| Business output | No duplicate writes thanks to keys, transactions, and idempotency |

## 17. Conclusion and Deployment Checklist

- **Pick one Job-launching mechanism:** automatic startup runner or custom runner; never accidentally run both.
- **Define ordering at the right layer:** `@Order` for startup runners, Spring Cloud Task's runner order property if applicable, Job flow for Steps, and an orchestrator for independent Jobs.
- **Use stable identifying `JobParameters`** so retries for the same period and tenant target the same `JobInstance`.
- **Never use a new `run.id` or identifying timestamp** for a re-run meant to resume an existing checkpoint.
- **Inspect `JobExecution` status** and map Batch failures to task/JVM outcomes; do not treat `JobLauncher.run` returning as synonymous with Job success.
- **Verify restart preconditions:** prior status, Job restartability, Step checkpoints, active process state, and `JobRepository`.
- **Keep business outcomes idempotent** across multiple `TaskExecution`s, `JobExecution`s, and external side effects.
- **Reconcile `TaskRepository`, `JobRepository`, business DB, and orchestrator** during incidents or backfills.

**Spring Cloud Task** tells you how an application run transpired; **Spring Batch** governs how a `JobInstance` is identified and restarted. Designing the right runner ordering, identifying parameters, and error-handling mechanisms keeps finite-lived tasks safe whether triggered on schedule or on demand.

### Reference Documentation

- [Spring Boot 3.5 — Batch Applications](https://docs.spring.io/spring-boot/3.5/how-to/batch.html)
- [Spring Boot — Spring Batch startup and auto-configuration](https://docs.spring.io/spring-boot/reference/io/spring-batch.html)
- [Spring Cloud Task — Spring Batch integration and exit codes](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Batch — Advanced Metadata Usage and JobOperator](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch — Metadata schema and identifying parameters](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
