# Write Responsibilities of TaskRepository and Read Responsibilities of TaskExplorer

## 1. Two Core Components of the Execution Repository

In **Spring Cloud Task**, a finite-running Spring Boot application can be launched on a schedule or on demand, process a job, and then terminate. To operate these applications, we need to know **which run started, when it ended, what arguments it received, and whether it succeeded or failed**. Spring Cloud Task stores this metadata as **`TaskExecution`**.

In the **Repository and Schema** chapter, two interfaces serve two complementary responsibilities:

- **`TaskRepository` — write side:** creates and updates the metadata of an execution. The Spring Cloud Task lifecycle calls the repository when a task starts and finishes.
- **`TaskExplorer` — read side:** queries stored metadata by ID, task name, lists, counts, or relevant relationships.

They both work with `TaskExecution` data, yet **differ in how they are used**. Business processing code normally does not need to directly `INSERT` or `UPDATE` the task tables; a monitoring application can use `TaskExplorer` to retrieve history without ever calling the write interface.

> The “read-only” nature of `TaskExplorer` is an **API scope**, not an automatic SQL permission restriction on the connection account. To make a dashboard truly read-only at the database level, grant `SELECT` privileges using an appropriate database policy.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the **metadata write** path via `TaskRepository` and the **metadata lookup** path via `TaskExplorer`.
2. Identify the key fields of `TaskExecution` and the related schema tables.
3. Look up executions by ID, name, latest run, or pagination using Java and SQL.
4. Configure the appropriate database, schema, table prefix, and transactions for both components.
5. Analyze failure scenarios, sudden process termination, incomplete metadata, and concurrent runs.
6. Distinguish the task metadata repository from Spring Batch's `JobRepository` and `JobExplorer`.

## 2. When Do Writes and Reads Occur?

Each launch of a Spring Cloud Task application typically corresponds to **a separate TaskExecution**. Suppose a `daily-import` job needs to import order data every night.

~~~mermaid
flowchart LR
    A["Scheduler / API"] --> B["Spring Boot Task Application"]
    B --> C["Spring Cloud Task Lifecycle"]
    C --> D["TaskRepository (write)"]
    D --> E[("Metadata Database")]
    E --> F["TaskExplorer (read)"]
    F --> G["Dashboard / Audit / Support"]
    B --> H[("Business Database")]
~~~

Typical flow:

1. **Context initialization:** Spring Boot starts up successfully. Before `ApplicationRunner` or `CommandLineRunner` beans run, Spring Cloud Task creates the start record via `TaskRepository`.
2. **Business processing:** the runner receives arguments and performs the finite task. This is where order data, exported files, or processing results are written to the business system.
3. **Completion:** after the runners finish or an error is recorded by the framework, Spring Cloud Task updates the completion metadata through the repository.
4. **Lookup:** operations systems use `TaskExplorer` to inspect the current run or history, even after the task JVM has exited, as long as the metadata remains stored in a persistent database.

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant R as TaskRepository
    participant DB as Database
    participant X as TaskExplorer
    participant U as Operations Tool

    T->>R: Record TaskExecution start
    R->>DB: INSERT ID, name, timestamp, arguments
    T->>T: ApplicationRunner executes business logic
    U->>X: getTaskExecution(id)
    X->>DB: SELECT by ID
    DB-->>X: Record may not have END_TIME yet
    X-->>U: Currently stored info
    T->>R: Record completion / exit code
    R->>DB: UPDATE execution result
    U->>X: getTaskExecution(id) again
    X->>DB: SELECT by ID
    DB-->>X: Newly committed metadata
    X-->>U: Completed record
~~~

**Important distinction:** `TaskRepository` does not decide *when* a task runs; that is the job of the scheduler or orchestrator. `TaskExplorer` does not re-trigger tasks and does not automatically repair failed records.

## 3. What Does TaskExecution Represent?

`TaskExecution` describes **a single physical run of a task application**, not a job definition, cron expression, or business transaction.

| Property | Meaning | How to Read It |
| --- | --- | --- |
| `executionId` | Unique ID of a single run | Used to correlate logs and metadata |
| `taskName` | Task name resolved from configuration | Multiple runs may share the same name |
| `startTime` | Timestamp when the framework recorded start | Populated when execution initialization succeeds |
| `endTime` | Recorded completion timestamp | May be empty if the task has not finished or failed to update in time |
| `exitCode` | Result code recorded upon completion | May be `null` while running; does not replace business outcomes on its own |
| `exitMessage` | Optional result note | Can be set via a task listener |
| `errorMessage` | Recorded unhandled error information | Helps analysis alongside stack traces in logs |
| `arguments` | List of command-line arguments | Sensitive information should be restricted |

For example, launching `daily-import` twice with the same argument `--businessDate=2026-11-23` can still create execution IDs `101` and `102`. These are **two separate runs**, even though both process the same business date. The framework records execution history; it **does not prevent duplicate processing by business key by default**.

In practice, it can also store an **external execution ID** or **parent execution ID** to link with the execution platform or a parent task. These fields do not replace the internal execution ID.

## 4. TaskRepository: Write Responsibilities

The Java interface `org.springframework.cloud.task.repository.TaskRepository` provides operations to **create** and **complete/update** a `TaskExecution`. In the standard flow, Spring Cloud Task invokes these operations through its lifecycle handler. Developers usually only need to configure the task, implement the business logic, and report errors properly.

| When | What Does the Write Side Do? | Observable Metadata |
| --- | --- | --- |
| Starting a run | Creates TaskExecution, assigns ID, stores name, timestamp, and arguments | `START_TIME` is present; `END_TIME` is not yet present |
| Runner processing | Does not mean the final result has been written | `EXIT_CODE` is still `NULL` or not yet updated |
| Runner completes | Stores completion time and result | `END_TIME`, `EXIT_CODE` |
| Runner fails | Records failure info if the lifecycle can handle it | Exit code, `EXIT_MESSAGE`, or `ERROR_MESSAGE` |
| JVM killed abruptly | Completion callback is not guaranteed to run in time | Metadata may get stuck in an unfinished state |

### 4.1. Why Not Write SQL Directly to Change Status?

The following statement **only illustrates an operation to avoid**:

~~~sql
-- Do not use to "fix" the outcome of a run in normal applications:
-- UPDATE TASK_EXECUTION SET EXIT_CODE = 0 WHERE TASK_EXECUTION_ID = 101;
~~~

Manually modifying `EXIT_CODE` does not make a report file appear or commit a business transaction; it can also make `END_TIME`, `ERROR_MESSAGE`, and logs contradict each other. When a task fails, address the root cause and decide whether to rerun according to policy, instead of manually turning metadata into “success”.

Spring Cloud Task supports an advanced scenario where **a TaskExecution is created before the infrastructure launches the application**, and the execution ID is passed into the process so it can update the lifecycle. Use this mechanism only when the orchestration architecture genuinely requires it, with the same metadata store and consistent ID-generation rules.

### 4.2. Adding Lifecycle Notes via Listener

Instead of issuing raw SQL, you can attach a message to the `TaskExecution` object through a listener at the proper extension point:

~~~java
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditSummaryListener {

    @AfterTask
    public void afterTask(TaskExecution execution) {
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("Task lifecycle callback finished");
        }
    }
}
~~~

This example only demonstrates how to set `exitMessage`; that message should not be interpreted as confirmation of business success. The `@AfterTask` callback is invoked **before the completion metadata is updated**. If you need to see the persisted `END_TIME`, let operations tools query after the task finishes and the repository has committed.

## 5. TaskExplorer: Read Responsibilities

The interface `org.springframework.cloud.task.repository.TaskExplorer` provides methods to query `TaskExecution` records without update operations. Representative APIs include:

| What to View? | Method |
| --- | --- |
| Record with a specific execution ID | `getTaskExecution(long executionId)` |
| List of executed task names | `getTaskNames()` |
| Total run count for a task name | `getTaskExecutionCountByTaskName(String taskName)` |
| Most recent run for a task name | `getLatestTaskExecutionForTaskName(String taskName)` |
| Paginated history by name | `findTaskExecutionsByName(String taskName, Pageable pageable)` |
| Full paginated history | `findAll(Pageable pageable)` |
| Records considered currently running | `findRunningTaskExecutions(String taskName, Pageable pageable)` |

Exact method signatures may vary across Spring Cloud Task versions, especially for pagination APIs. The next example is based on versions using Spring Data `Pageable`; check the Javadoc bundled with your project's dependency before compiling.

### 5.1. Java Example: History Reader Service

An admin service or integration test with a `TaskExplorer` bean configured for the right database can use:

~~~java
import java.util.Optional;

import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

@Service
public class TaskHistoryReader {

    private final TaskExplorer explorer;

    public TaskHistoryReader(TaskExplorer explorer) {
        this.explorer = explorer;
    }

    public Optional<TaskExecution> find(long id) {
        return Optional.ofNullable(explorer.getTaskExecution(id));
    }

    public Optional<TaskExecution> latest(String taskName) {
        return Optional.ofNullable(
                explorer.getLatestTaskExecutionForTaskName(taskName));
    }

    public Page<TaskExecution> history(String taskName, int page) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        return explorer.findTaskExecutionsByName(
                taskName, PageRequest.of(page, 20));
    }

    public long totalRuns(String taskName) {
        return explorer.getTaskExecutionCountByTaskName(taskName);
    }
}
~~~

Usage example:

~~~java
TaskExecution execution = reader.find(101L)
        .orElseThrow(() -> new IllegalArgumentException(
                "TaskExecution 101 not found"));

System.out.println("Name: " + execution.getTaskName());
System.out.println("Start: " + execution.getStartTime());
System.out.println("End: " + execution.getEndTime());
System.out.println("Exit: " + execution.getExitCode());
~~~

**How to interpret results:**

- If the ID does not exist in the repository being read, `getTaskExecution` may return `null`.
- “Latest” is based on start order, **not necessarily the most recently finished run**. Overlapping task runs may complete in a different order.
- `findRunningTaskExecutions` reflects records still considered running **in the repository**, which does not prove the actual process is still alive. A killed task can leave behind unfinished metadata.
- Paginated results are only a snapshot at query time. If another task commits right afterward, the next read may differ.

Do not build a long-running dashboard by starting a fresh in-memory H2 store and expecting to view data from task processes that have already terminated. You must have a shared persistent database for both the writing application and the reading application.

## 6. Schema: One Repository, Two Access Paths

With JDBC configuration and the standard schema, **TaskRepository writes** and **TaskExplorer reads** the execution-related tables. Default table names typically have the `TASK_` prefix.

~~~mermaid
erDiagram
    TASK_EXECUTION ||--o{ TASK_EXECUTION_PARAMS : "parameters"
    TASK_EXECUTION ||--o{ TASK_TASK_BATCH : "batch link"
    TASK_EXECUTION {
        BIGINT TASK_EXECUTION_ID PK
        VARCHAR TASK_NAME
        TIMESTAMP START_TIME
        TIMESTAMP END_TIME
        INTEGER EXIT_CODE
        VARCHAR EXIT_MESSAGE
        VARCHAR ERROR_MESSAGE
    }
    TASK_EXECUTION_PARAMS {
        BIGINT TASK_EXECUTION_ID FK
        VARCHAR TASK_PARAM
    }
    TASK_TASK_BATCH {
        BIGINT TASK_EXECUTION_ID FK
        BIGINT JOB_EXECUTION_ID
    }
~~~

This is a **conceptual** diagram; exact columns, data types, keys/indexes, and DDL depend on the database management system and framework version.

| Table or Component | Purpose |
| --- | --- |
| `TASK_EXECUTION` | Stores metadata for a single execution |
| `TASK_EXECUTION_PARAMS` | Stores the argument list, linked to the execution ID |
| `TASK_SEQ` or equivalent ID generation mechanism | Supports generating execution IDs |
| `TASK_TASK_BATCH` | Links task executions with Spring Batch job executions when integrated |
| `TASK_LOCK` | Supports single-instance locking when enabled with the required dependencies |

### 6.1. SQL Queries for Cross-Checking

During labs or incident investigations, SQL helps inspect the underlying data:

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME, EXIT_CODE,
    EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-import'
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

Look up parameters for a single run:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = 101;
~~~

If Spring Batch is used:

~~~sql
SELECT TASK_EXECUTION_ID, JOB_EXECUTION_ID
FROM TASK_TASK_BATCH
WHERE TASK_EXECUTION_ID = 101;
~~~

The ID `101` and task name are illustrative data. In application code, use `TaskExplorer` for reading instead of coupling directly to SQL structure; SQL is suitable for schema verification and operational cross-checks. If you changed the table prefix, adjust table names in manual queries accordingly.

## 7. DataSource Configuration and Schema Management

Spring Cloud Task provides default configuration via `DefaultTaskConfigurer`, including `TaskRepository`, `TaskExplorer`, and the transaction manager. When using JDBC, make sure these components access **the same metadata store**. In-memory data can be helpful for demos, but usually disappears once the process exits.

YAML example for a task using PostgreSQL:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-import
  datasource:
    url: jdbc:postgresql://localhost:5432/task_metadata
    username: task_writer
    password: TASK_DB_PASSWORD_FROM_ENV
  cloud:
    task:
      initialize-enabled: false
~~~

In this example, `TASK_DB_PASSWORD_FROM_ENV` is a **placeholder**: real applications must load passwords from secrets/environment variables and never commit passwords into the code repository. You must include the JDBC driver and a Spring Cloud Task dependency compatible with Spring Boot.

- `spring.application.name` sets the application name; the actual `TaskExecution` name also depends on `TaskNameResolver` if customized.
- `initialize-enabled: false` disables automatic table creation; only use this after the schema has been created via an appropriate migration. Disabling initialization on an empty database will cause write errors.
- `spring.cloud.task.tablePrefix` can change the table prefix, but **the schema and configuration must match**; do not change the property alone and expect the framework to alter DDL automatically.
- When **multiple DataSources** exist, you need an appropriate `TaskConfigurer` to specify the exact database/transaction manager dedicated to task metadata. Avoid situations where the repository writes to database A while the explorer reads from database B.

### 7.1. Metadata Transactions Differ from Business Transactions

Keep these scopes distinct:

| Scope | Role |
| --- | --- |
| Metadata transaction | Records the task run and updates status in the repository |
| Business transaction | Writes orders, reports, files, payments, or application data |
| Orchestration | Determines schedule, retries, timeouts, and task ordering |

These scopes are **not in a single atomic transaction by default**. For instance, a task successfully writes a file to object storage, then the JVM dies before updating `END_TIME`. `TaskExplorer` sees an unfinished record, yet the file already exists. If the scheduler automatically reruns it, the file may be generated twice.

For safe operations, implement a **business key**, **idempotency** mechanisms, a retry policy, and a way to reconcile business outcomes. Do not rely solely on `EXIT_CODE` or `END_TIME` to decide whether a job can be rerun without side effects.

### 7.2. True Read and Write Permissions

If a dashboard only needs to view history, it can be deployed as **an independent service with a read-only database account**, pointing to the real metadata store. Task applications use a write account suited to updating the tables. Sharing the `TaskExplorer` library does not automatically turn an SQL account into a read-only account.

Be mindful that CLI arguments, exit messages, and error messages can contain sensitive data. Never pass tokens, passwords, or personal data in arguments and display them verbatim on a dashboard; enforce authorization on metadata-reading APIs and configure a data retention policy.

## 8. Stale Data and Failure Scenarios

Because `TaskExplorer` only reads committed data, it may reflect **a stale state** right before the task writes its final result. If reading from a replica, replication lag may also occur.

| Read Result | Safe Interpretation | Next Verification Step |
| --- | --- | --- |
| `START_TIME` present, `END_TIME` empty | Repository has not recorded completion yet | Check pod/PID, logs, timeout, DB connection |
| `END_TIME` present and `EXIT_CODE = 0` | Framework recorded normal completion | Verify actual business outcomes |
| `END_TIME` present and non-zero exit code | Framework recorded a failure signal | Check stack trace, error message, already-committed work |
| `getTaskExecution(id)` not found | No such ID in the store being read | Check ID, DataSource, schema, table prefix |
| Multiple executions with same name/input | Multiple runs occurred | Check scheduler, retries, and business deduplication |
| Logs exist but no record | Task may have failed to bootstrap or pointed to wrong store | Check startup errors, schema, permissions, or task config |

**Note:** `END_TIME IS NULL` does **not** definitively mean the task is currently running. A process killed abruptly might not have time to update the repository. Monitoring systems must combine metadata with actual infrastructure status.

## 9. Differences from Spring Batch's JobRepository and JobExplorer

A Spring Cloud Task application can run Spring Batch, but their repositories track **different levels**:

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskRepository` writes **application runs** | `JobRepository` writes **job/step executions, checkpoints** |
| `TaskExplorer` reads **TaskExecution** | `JobExplorer` reads **JobExecution/StepExecution** |
| Focuses on process startup, completion, and exit code | Focuses on step/chunk processing, job-level restart/skip/retry |
| Identified by `TASK_EXECUTION_ID` | Identifies job executions with their own ID |

When Task-Batch integration is enabled, `TASK_TASK_BATCH` links `TASK_EXECUTION_ID` with `JOB_EXECUTION_ID`. Supporting versions also provide `TaskExplorer.getJobExecutionIdsByTaskExecutionId(...)` and `getTaskExecutionIdByJobExecutionId(...)` methods for lookup.

Do not use `TaskExplorer` to locate chunk-level checkpoints; that is the responsibility of `JobExplorer` and `JobRepository`. If a job runs asynchronously and the runner returns early, the `TaskExecution` may complete before the Batch job finishes; the application must be designed to wait and reflect the result accurately.

## 10. System Design Examples

### Scenario A — Dashboard Displaying Task History

Every night a Kubernetes CronJob runs `daily-import`, and the application writes `TaskExecution` records via `TaskRepository` into PostgreSQL. A continuously running admin dashboard uses `TaskExplorer` to paginate the latest 20 runs, displaying results and execution times.

**What to do:** connect both to the same metadata database; give the dashboard read-only privileges and authenticate its API; do not use a separate in-memory H2 database per process.

### Scenario B — Task Killed Due to OOM

The process created execution ID `57`, but was killed by the system due to out-of-memory before updating `END_TIME`. `TaskExplorer` still sees an unfinished record.

**What to do:** inspect the OOMKilled pod, logs, and already-processed business outcomes. Confirm safety before rerunning; do not manually set `EXIT_CODE = 0` via SQL.

### Scenario C — Three Runs with the Same Name

Three `daily-import` processes run around the same time. `TaskRepository` assigns separate execution IDs; `TaskExplorer` can query each ID accurately. Sharing a task name **does not prevent overlapping processing automatically**.

**What to do:** include the execution ID in logs, define business locking/idempotency rules, and enforce a concurrency-blocking policy if required.

### Scenario D — Spring Batch Running Inside a Task

Task records the application lifecycle, while Batch records jobs/steps. Operations teams look up the task execution ID, find the related job execution, and then use `JobExplorer` to investigate the failed step.

**What to do:** ensure the task lifecycle reflects job completion as required; keep the two metadata layers distinct.

## 11. Hands-on Exercise: Verifying Writes and Reads

Assume the Spring Cloud Task schema is properly initialized and `daily-import` uses a persistent database.

1. **Launch** with the business argument `--businessDate=2026-11-23`.
2. **Find the execution ID** via logs or `getLatestTaskExecutionForTaskName("daily-import")`; save the actual ID.
3. **Read via TaskExplorer** using `getTaskExecution(id)` and verify the name and start time.
4. **Check SQL** in `TASK_EXECUTION` and `TASK_EXECUTION_PARAMS` for that ID.
5. **After the process finishes**, read `getTaskExecution(id)` again, and verify the end time, exit code, and error details (if any).
6. **Run a second time with the same businessDate** and verify a new execution ID appears; check whether business side effects were duplicated.
7. **Test a controlled error** in the runner, and correlate the logs with `TaskExplorer` instead of manually editing the database.
8. **Try reading from a separate tool** and confirm it uses the exact same DataSource/schema as the writing application.

### Pre-Operations Checklist

- [ ] `TaskRepository` and `TaskExplorer` point to the **intended shared metadata store**.
- [ ] Schema, table prefix, and DDL version are compatible with the framework.
- [ ] Metadata transactions commit successfully on start/completion.
- [ ] `TaskExplorer` reads the expected execution ID after commit.
- [ ] Write and read accounts have appropriate database permissions.
- [ ] Alerts exist for overdue runs and unfinished records.
- [ ] Retries and idempotency are designed at the business layer.
- [ ] Arguments and error messages do not leak secrets into logs/dashboards.
- [ ] Metadata cleanup, backup, and indexing policies exist for expected historical volume.
- [ ] If using Spring Batch, `TaskExecution` is distinguished from `JobExecution`.

## 12. Key Takeaways

**`TaskRepository` is the write gateway for execution state; `TaskExplorer` is the lookup gateway for stored state.** Separating these two responsibilities makes tracking finite Spring Cloud Task applications clear, yet it does not replace business transactions, schedulers, logs, or actual process status.

To read accurate results, place both gateways on the **same database/schema**, understand commit timing, and handle interrupted runs that failed to update metadata in time. With Spring Batch, continue distinguishing the task repository from the job repository to diagnose failures at the right level.

### References

- [Spring Cloud Task — Features and TaskConfigurer](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/#_task_repository_schema)
- [Spring Cloud Task — TaskExplorer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
- [Spring Cloud Task — TaskRepository source](https://github.com/spring-cloud/spring-cloud-task/blob/main/spring-cloud-task-core/src/main/java/org/springframework/cloud/task/repository/TaskRepository.java)
