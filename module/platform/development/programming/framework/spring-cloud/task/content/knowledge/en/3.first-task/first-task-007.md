# Reading Logs and Verifying the First Execution Record

## 1. Goal of the Verification Step

Once you have successfully run your first **Spring Cloud Task** application, two independent things must be confirmed: **the business code actually executed** and **Spring Cloud Task recorded the run's lifecycle in the database**. Seeing a “Started …” line on the console is not enough to confirm the task finished; seeing a row in the database is not enough to confirm the business outcome is accurate.

In the **First Task** chapter, this lesson focuses on reading logs, identifying individual runs, querying **TaskRepository**, and inspecting parameters, exit codes, and error details. This lays the groundwork for later running tasks on a schedule or on demand, integrating with Spring Batch, and operating safely.

After this lesson, you will be able to:

- Distinguish application startup logs, business processing logs, and task lifecycle logs.
- Locate a specific run using its **task execution ID** and correlate it with a row in **TASK_EXECUTION**.
- Read **START_TIME**, **END_TIME**, **EXIT_CODE**, **EXIT_MESSAGE**, **ERROR_MESSAGE**, and input parameters.
- Recognize signs of failures, interrupted processes, or misconfigured TaskRepository setups.
- Perform a repeatable verification cycle before placing a task on a real schedule.

## 2. Model for Observing a Single Execution

Spring Cloud Task works with finite-lived Spring Boot applications: start up, perform work, and exit. When enabled and configured with an appropriate repository, the framework persists **TaskExecution** records into the database via **TaskRepository**.

~~~mermaid
sequenceDiagram
    participant O as Operator / Scheduler
    participant A as Spring Boot Application
    participant R as TaskRepository
    participant DB as Database
    O->>A: Launch with arguments
    A->>R: Start TaskExecution
    R->>DB: Store ID, task name, start time
    A->>A: Run business logic, write logs
    alt Controlled termination
        A->>R: Record completion / exit code
        R->>DB: Update execution record
    else Process terminated abruptly
        Note over A,DB: May fail to save END_TIME or final outcome
    end
    O->>DB: Query execution record, cross-check logs
~~~

Three categories of data must be distinguished:

| Source | What Question Does It Answer? | What Does It Not Prove by Itself? |
| --- | --- | --- |
| **Application logs** | Did the command start, which step is running, and where did an error occur? | A success log does not guarantee results were durably persisted. |
| **TaskRepository** | What is the run's ID, when did it start/end, and what are its exit code and error details? | Does not contain full details of every business processing step. |
| **Business data** | Were orders, files, reports, or target records updated accurately? | Does not by itself explain why a process stopped. |

**TaskRepository is not a log storage system**. It stores execution lifecycle metadata; logs still come from Spring Boot's logging framework, centralized log aggregation, or container runtime infrastructure.

## 3. Preparing a Sample Task to Observe

Suppose you have a Spring Boot application using a compatible **Spring Cloud Task** version, with the required dependencies and a DataSource pointing to a database containing the metadata schema. This example names the task **first-task** and accepts a processing date parameter.

### 3.1. Local Configuration

To experiment and inspect data **after the JVM has exited**, you can use file-based H2:

~~~yaml
# application.yml: example for learning environments
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./data/first-task-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: first-task

logging:
  level:
    root: INFO
~~~

The application must have the H2 driver on the classpath and the Spring Cloud Task schema tables matching the version in use. Whether the schema is created automatically or via migrations depends on configuration and environment; verify before running. In real systems, use a managed database and an explicit migration process.

**Note:** H2 `jdbc:h2:mem:...` is only suitable for testing within the same process; once the JVM exits, in-memory data can disappear. With file-based H2, the relative path `./data/first-task-db` is resolved from **the working directory at launch**. Using two different working directories can accidentally create two separate databases.

### 3.2. An Illustrative Runner

If your application already has a runner, simply apply the logging and correlation techniques in the following sections. The snippet below shows a simple task application that validates arguments and lets you simulate a failure:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class FirstTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(FirstTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(FirstTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner firstRunner() {
        return arguments -> {
            List<String> values = arguments.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Required parameter: --businessDate=yyyy-MM-dd");
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            log.info("BUSINESS_START businessDate={}", businessDate);

            if (arguments.containsOption("fail")) {
                throw new IllegalStateException("Simulated error for testing");
            }

            // Replace with actual business processing.
            log.info("BUSINESS_DONE businessDate={} processedCount={}",
                    businessDate, 12);
        };
    }
}
~~~

In the example above, **12 is illustrative data**, not an actual count written to a business database. In real applications, outcome logs should reflect real processed values and must never log passwords, tokens, or sensitive personal data.

To correlate logs with TaskRepository records more accurately, you can add a listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class TaskAuditLogListener implements TaskExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditLogListener.class);

    @Override
    public void onTaskStartup(TaskExecution taskExecution) {
        log.info("TASK_START executionId={} taskName={}",
                taskExecution.getExecutionId(),
                taskExecution.getTaskName());
    }

    @Override
    public void onTaskEnd(TaskExecution taskExecution) {
        log.info("TASK_END executionId={}",
                taskExecution.getExecutionId());
    }

    @Override
    public void onTaskFailed(TaskExecution taskExecution, Throwable throwable) {
        log.error("TASK_FAILED executionId={} errorType={}",
                taskExecution.getExecutionId(),
                throwable.getClass().getSimpleName(), throwable);
    }
}
~~~

The listener writes **executionId** into the logs so you can trace a specific run accurately, even when multiple runs share the same task name. If your Spring Cloud Task version has listener API differences, use the API of the exact version you are running; the correlation principle remains **one execution ID per execution run**.

## 4. First Run and Reading the Logs

Assuming you packaged the app as `first-task.jar`, launch it with a business argument:

~~~bash
java -jar first-task.jar --businessDate=2026-11-23
~~~

A log snippet might look like this (**illustrative**; actual logger names, line ordering, and IDs vary by environment):

~~~text
2026-11-24 08:00:01 INFO  ... : Starting FirstTaskApplication
2026-11-24 08:00:03 INFO  ... : TASK_START executionId=1 taskName=first-task
2026-11-24 08:00:03 INFO  ... : BUSINESS_START businessDate=2026-11-23
2026-11-24 08:00:03 INFO  ... : BUSINESS_DONE businessDate=2026-11-23 processedCount=12
2026-11-24 08:00:03 INFO  ... : TASK_END executionId=1
~~~

Reading the log chronologically:

1. **Starting …** indicates the application is initializing; this is not yet proof that business work completed.
2. **TASK_START** indicates the task was registered by the framework, along with `executionId=1` in this example.
3. **BUSINESS_START** shows the runner started processing with the parsed parameter value.
4. **BUSINESS_DONE** confirms the runner's processing branch completed according to the sample logic.
5. **TASK_END** indicates the listener's completion callback was invoked. Query the database after the process stops to confirm metadata was saved.

The lines prefixed with `TASK_START`, `BUSINESS_START`, `BUSINESS_DONE`, and `TASK_END` are **written by our sample code**, not fixed log text automatically emitted by Spring Cloud Task.

When inspecting runs, prioritize `executionId` over searching solely by `taskName` and timestamps. If two `first-task` processes run concurrently, their logs may interleave; each execution ID still identifies an independent run.

### 4.1. Cross-Checking Timestamps

Compare application startup, business start, business completion, and task end timestamps. Log timestamps may use the host timezone or logging configuration, whereas database column types and SQL client display formats may differ. **Normalize timezones before comparing**; do not jump to conclusions about abnormal latency just from two differently formatted time strings.

### 4.2. Checking the Process Exit Code

For tasks run in a terminal, script, or orchestrator, the **process** exit code matters to the launching system. By common convention, `0` indicates normal completion and non-`0` indicates failure. However, the OS exit code, the exit code stored in TaskRepository, and the business outcome must all be verified against how the application handles exceptions and configures exit codes; do not assume all three values are always identical.

For example, if the runner catches an error and only logs it without rethrowing or marking a failed outcome, the framework may treat the application as having completed normally. Therefore, an “ERROR” message in the logs **does not automatically guarantee** `EXIT_CODE` will be non-zero.

## 5. Querying Records in TaskRepository

In the standard Spring Cloud Task SQL schema, two tables are commonly used to verify the first run:

- **TASK_EXECUTION**: metadata for each task execution.
- **TASK_EXECUTION_PARAMS**: command-line parameters recorded for that execution.

Table names, columns, and query syntax may need adjustment depending on your project's schema/naming strategy or framework version. Below is an SQL example using standard column names.

### 5.1. Finding the Just-Completed Run

Open an SQL client connected to **the exact database used by the application**, then run:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'first-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Illustrative output:

| TASK_EXECUTION_ID | TASK_NAME | START_TIME | END_TIME | EXIT_CODE | EXIT_MESSAGE | ERROR_MESSAGE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | first-task | 2026-11-24 08:00:03 | 2026-11-24 08:00:03 | 0 | (empty) | (empty) |

In the illustrative scenario:

- `TASK_EXECUTION_ID = 1` matches `executionId=1` in the listener log.
- `TASK_NAME = first-task` matches the configured name.
- Both `START_TIME` and `END_TIME` are populated; the run was recorded as finished.
- `EXIT_CODE = 0` matches normal completion in the example.
- Empty `EXIT_MESSAGE` and `ERROR_MESSAGE` are not errors; they may remain unset for successful runs.

**Do not infer success solely from the presence of END_TIME.** A failed run that terminates cleanly under framework handling can also have an end time. Combine `EXIT_CODE`, error details, logs, and business outcomes.

### 5.2. Querying by Exact Execution ID

If the logs gave `executionId=1`, query a single record directly:

~~~sql
SELECT *
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 1;
~~~

The ID in the example is purely illustrative. For each new run, substitute the actual ID from the logs or queried from the table. This is far less error-prone when the system has many runs sharing the same name.

### 5.3. Checking Parameters of the Run

~~~sql
SELECT TASK_EXECUTION_ID, TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = 1;
~~~

Compare the output with the argument that was passed:

~~~text
--businessDate=2026-11-23
~~~

How values are represented in `TASK_PARAM` depends on the parameter storage mechanism of the version in use. Do not assume this table holds a `KEY`/`VALUE` column pair or infer that parameters were validated; parsing and validating parameters remains the application's responsibility.

**Security note:** command-line arguments can appear in execution history and system logs. Never pass passwords, access tokens, or sensitive data as arguments that the environment might record.

### 5.4. Comparing Multiple Runs

Each launch of a Spring Cloud Task application typically creates **a new TaskExecution record**. Re-running with the same `businessDate` produces records with different execution IDs and identical parameters. Spring Cloud Task records the history of each launch; it **does not automatically guarantee a business operation is performed only once**.

Example:

| Execution ID | Business Parameter | Exit Code | Meaning |
| --- | --- | --- | --- |
| 1 | `businessDate=2026-11-23` | 0 | First run completed normally. |
| 2 | `businessDate=2026-11-23` | 0 | Re-run for the same date; check duplicate-processing protection. |
| 3 | `businessDate=2026-11-24` | Non-0 | Possibly a failed run; inspect the specific error. |

To prevent duplicate side effects, business logic should use **business keys** (e.g., reconciliation date and target entity), data constraints, and appropriate **idempotent** logic.

## 6. Testing a Failure Scenario and Analyzing the Record

To observe an unsuccessful run, use the error-simulation branch in the runner:

~~~bash
java -jar first-task.jar --businessDate=2026-11-24 --fail
~~~

Example log:

~~~text
2026-11-24 08:10:00 INFO  ... : TASK_START executionId=2 taskName=first-task
2026-11-24 08:10:00 INFO  ... : BUSINESS_START businessDate=2026-11-24
2026-11-24 08:10:00 ERROR ... : TASK_FAILED executionId=2 errorType=IllegalStateException
java.lang.IllegalStateException: Simulated error for testing
    at ...FirstTaskApplication...
~~~

Query the record after the JVM exits:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 2;
~~~

When an error is properly captured by the framework, you will generally see metadata indicating the execution failed, such as a non-zero exit code and/or error details. **Do not rely on one exact value or error message format across all versions**. If the process stops abruptly before the framework updates the repository, the record may still lack completion details.

When determining the root cause of a failure, inspect **all three layers of information**:

1. **Stack trace in logs** to find the root exception and the failing step.
2. **TaskExecution** to identify which specific run was affected and the final persisted status.
3. **Target system** to see whether partial data was updated before the failure occurred.

For example, a file export task might finish writing the file and then fail while sending a notification. Blindly re-running the entire task based only on `EXIT_CODE` could create duplicate files. Recovery must consider business state.

## 7. Common Status Interpretation Table

| Observed Symptom | Initial Interpretation | Next Steps to Check |
| --- | --- | --- |
| Processing logs present, record exists, `END_TIME` set, and `EXIT_CODE = 0` | Framework recorded a normal completion | Verify actual business output. |
| Record exists, `END_TIME` set, and non-zero `EXIT_CODE` | Run finished but recorded a failure | Inspect `ERROR_MESSAGE`, stack trace, parameters, and processed data. |
| Record exists, but `END_TIME` is empty | Completion not recorded; may still be running or stopped abnormally | Check actual PID/pod/job status, timeouts, and system logs. |
| Startup logs present, but no record found | TaskRepository did not record the run in the database being inspected | Verify task enablement, DataSource, schema, permissions, and connection error logs. |
| Record exists, but expected logs are missing | Wrong log source, log level, or runner failed before reaching log statements | Locate execution ID, log destination, logger config, and stack trace. |
| Multiple records with the same name/inputs | Task was launched multiple times | Check scheduler, retries, manual triggers, and duplicate handling. |
| `EXIT_CODE = 0` but business result is wrong | Application may have reported success prematurely or swallowed business errors | Review success criteria, tests, and error-signaling logic. |

**Important:** `END_TIME IS NULL` does not necessarily mean the task *is still running*. When a process is killed, loses power, runs out of memory, or cannot update the database, metadata can remain stuck in an unfinished state. Always verify the actual status of the process/container.

## 8. Troubleshooting Procedure When No Record Is Found

If you just ran a task and see no data in **TASK_EXECUTION**, check in this order:

1. **Confirm the process actually launched:** look for application startup logs, runner logs, and the earliest exception.
2. **Verify Spring Cloud Task configuration:** ensure the app has the dependencies, enables task features (e.g., `@EnableTask` per your config), and actually uses `TaskRepository`.
3. **Verify the DataSource:** check whether the URL, database name, schema, username, and active profile match where your SQL client is connected.
4. **Verify the schema:** confirm **TASK_EXECUTION** and **TASK_EXECUTION_PARAMS** exist for the framework version, and the DB account has read/write permissions.
5. **Check startup write capability:** if the database was unavailable at startup, the task may fail before creating a complete record.
6. **Check the working directory for file-based H2:** `./data` when running the JAR may differ from the database location opened by your SQL client.
7. **Inspect targeted debug logs:** in test environments, temporarily increase log levels for the relevant namespace, then restore appropriate levels.

Example of enabling detailed logging in a development environment:

~~~yaml
logging:
  level:
    org.springframework.cloud.task: DEBUG
~~~

Do not enable broad `DEBUG` logging indefinitely in production: high log volume impacts storage costs and can expose unnecessary details if input logging is unrestricted.

If using PostgreSQL/MySQL or another RDBMS, check database permissions and how schemas are initialized via migrations. If you need to query while the application is still running, use an RDBMS that allows concurrent client access and confirm you are connecting to the right database; with file-based H2, file-locking rules depend on configuration and connection mode.

## 9. First-Run Self-Check Checklist

After a successful run, check off each item:

- [ ] Logs show the application started and the runner executed its work.
- [ ] An execution ID is identifiable from the listener or a TaskRepository query.
- [ ] Task name and input parameters match expectations.
- [ ] The database contains a row in **TASK_EXECUTION** for this run.
- [ ] Detailed records can be queried by the exact `TASK_EXECUTION_ID`.
- [ ] **START_TIME** is populated; for normal completions, **END_TIME** is also populated.
- [ ] **EXIT_CODE**, **EXIT_MESSAGE**, and **ERROR_MESSAGE** have been checked against the actual outcome.
- [ ] Both logs and business results have been cross-checked rather than trusting the exit code alone.
- [ ] You can locate a failed run's record and explain the root cause.
- [ ] When re-running with identical parameters, duplicate-output risks have been evaluated.

## 10. Key Takeaway

A reliable verification workflow for your **first task** is: **run the application → capture the execution ID → read logs by ID → query TaskRepository → verify business results**. Logs explain what happened step-by-step, TaskRepository holds lifecycle metadata for an execution, and business data reflects the actual impact.

Once you understand these three sources of truth, it becomes straightforward to detect failed runs, overdue runs, and duplicate runs when integrating Spring Cloud Task with schedulers, orchestrators, or Spring Batch. You also gain a solid basis for designing retries, alerts, and auditing safely instead of relying solely on a “Started” or “Completed” log line.
