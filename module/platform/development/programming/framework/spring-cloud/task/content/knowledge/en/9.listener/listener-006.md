# Setting `exitMessage` and Update Precedence Order

In **Spring Cloud Task**, a task with a finite runtime is represented by `TaskExecution`. In addition to start time, end time, and exit code, each execution has an **`exitMessage`** attribute to briefly describe the outcome or completion context. When an application imports data, generates reports, or performs system maintenance, this field helps operators quickly read the status of a run without scanning the entire log.

This lesson belongs to the **Listener** chapter and focuses on three questions: how to set `exitMessage` through listeners, why multiple callbacks might update the same message, and **which value gets saved last in `TaskRepository`**. The content uses the `TaskExecutionListener` mechanism and the `@BeforeTask`, `@FailedTask`, and `@AfterTask` annotations, while distinguishing `exitMessage` from `exitCode` and `errorMessage`.

## 1. What Is `exitMessage` Used For?

Suppose a nightly order-file processing task runs. It might terminate with one of these outcomes:

- `IMPORTED; source=orders-2026-11-23; accepted=980; rejected=20`.
- `FAILED; phase=VALIDATION; reason=UNSUPPORTED_HEADER`.
- `SKIPPED; reason=SOURCE_ALREADY_IMPORTED`.

Structured, concise messages like these identify **the business outcome of a single run**, while detailed reconciliation figures and import source history should still live in dedicated business tables or monitoring systems.

In the `TaskExecution` model:

| Attribute | Content | Usage |
| --- | --- | --- |
| `exitMessage` | String set by the application or listener | Explains the outcome, skip reason, or high-level business failure |
| `exitCode` | Exit code, usually `0` on success and non-zero on failure | Used by orchestrators to decide success/failure and retries |
| `errorMessage` | Exception details when a task fails, possibly including a stack trace | Technical error diagnosis; requires access control |
| `taskName` and `executionId` | Task type and execution identifier | Looking up the exact run |
| `arguments` | Application arguments passed at startup | Cross-checking source, data period, or execution mode |

**`exitMessage` does not determine `exitCode`.** Calling `taskExecution.setExitMessage("SUCCESS")` will not make a process succeed if an exception still occurs. Conversely, a message containing `FAILED` does not automatically turn an exit code from `0` into `1`.

Spring Cloud Task typically persists the final message into the **`TASK_EXECUTION.EXIT_MESSAGE`** column of `TaskRepository`. According to the official reference schema, this column has type **`VARCHAR(2500)`**; actual length depends on the database version and deployed DDL. Therefore, write only a concise summary string—never stuff large JSON, stack traces, or sensitive data into it.

## 2. Listener Lifecycle Related to `exitMessage`

`TaskExecutionListener` provides three callbacks:

1. **`onTaskStartup(TaskExecution)`**: called when the Task begins, before the main runner processing.
2. **`onTaskFailed(TaskExecution, Throwable)`**: called when an unhandled error occurs in the task.
3. **`onTaskEnd(TaskExecution)`**: called when the Task ends, before the final result is updated in `TaskRepository`.

You can use either the interface or the corresponding annotations:

| Interface Method | Corresponding Annotation | Role When Writing Messages |
| --- | --- | --- |
| `onTaskStartup` | `@BeforeTask` | Set an initial fallback message, e.g., `STARTED` |
| `onTaskFailed` | `@FailedTask` | Record a concise, categorized failure cause |
| `onTaskEnd` | `@AfterTask` | Record a summary message; can override previously set messages |

Startup and end callbacks relate to creating/updating `TaskExecution`; exact ordering between creating the initial record and the startup callback must be verified for your version. **Do not assume `STARTED` is already visible in the database immediately when `onTaskStartup` runs.** The value of interest in this lesson is `EXIT_MESSAGE` on **`TaskExecution` after the final update completes**.

~~~mermaid
flowchart TD
    A["Start Spring Boot + Spring Cloud Task"] --> B["onTaskStartup / @BeforeTask"]
    B --> C["ApplicationRunner / CommandLineRunner runs business logic"]
    C --> D{"Unhandled error thrown?"}
    D -- "No" --> F["onTaskEnd / @AfterTask"]
    D -- "Yes" --> E["onTaskFailed / @FailedTask"]
    E --> F
    F --> G[("TaskRepository updates TaskExecution<br/>EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE")]
~~~

In a normal error flow, **`onTaskFailed` runs before `onTaskEnd`**. Therefore, if both set `exitMessage`, you must understand the override rules so failure information is not lost.

## 3. The Most Important Rule: Update Precedence Order

Spring Cloud Task defines the precedence of `exitMessage` from **highest to lowest**:

```text
onTaskEnd     (@AfterTask)     : priority 1 — highest
onTaskFailed  (@FailedTask)    : priority 2
onTaskStartup (@BeforeTask)    : priority 3 — lowest
```

This is a **precedence order for the persisted message**, not an error-classification rule. During a failed run, `onTaskFailed` receives the exception first, and then `onTaskEnd` still has a final chance to update `exitMessage`.

### 3.1. Scenario Matrix

Suppose each callback sets the following values:

- Startup: `STARTED`.
- Failed: `FAILED: CSV_INVALID`.
- End: `FINISHED`.

| Condition | Startup Writes | Failed Writes | End Writes | Saved `exitMessage` |
| --- | --- | --- | --- | --- |
| Success, only startup writes | `STARTED` | Not called | Unchanged | `STARTED` |
| Success, end writes | `STARTED` | Not called | `FINISHED` | **`FINISHED`** |
| Failure, end does not change | `STARTED` | `FAILED: CSV_INVALID` | Unchanged | **`FAILED: CSV_INVALID`** |
| Failure, end also writes | `STARTED` | `FAILED: CSV_INVALID` | `FINISHED` | **`FINISHED`** |
| Only failed writes on failure | Unchanged | `FAILED: CSV_INVALID` | Unchanged | **`FAILED: CSV_INVALID`** |
| No callback sets a message | Unchanged | Unchanged | Unchanged | No custom message |

**Common mistake:** `@FailedTask` records `FAILED: CSV_INVALID`, but `@AfterTask` unconditionally sets `FINISHED`. Operators reading `EXIT_MESSAGE` will only see `FINISHED`, even though the exit code and `ERROR_MESSAGE` still indicate the task failed.

### 3.2. Override Rules and `null` Values

In how `TaskLifecycleListener` manages the Spring Cloud Task lifecycle, listeners receive a `TaskExecution` to update. After callbacks execute, the framework takes the new `exitMessage` to update the managed `TaskExecution`; a **non-`null`** value can replace an earlier value.

This leads to two practical notes:

- **Do not call `setExitMessage`** in `onTaskEnd` if you want to keep the message set by an earlier callback.
- Do not pass `setExitMessage("")` to mean "no change": an empty string is still a non-null string and can **overwrite the message with blank**. When no update is needed, leave the existing value untouched.

The precedence rule applies across the **three lifecycle phases**. If **multiple listeners write `exitMessage` in the same phase**, the final value depends on the invocation order of listeners in your version and configuration. Do not design around an implicit order among multiple beans; designate **one clear owner for the final outcome message**, or coordinate explicitly and test callback order.

## 4. Example 1: Setting Messages with `TaskExecutionListener`

Suppose an `invoice-report-task` application generates daily invoice reports. We want:

- `onTaskStartup`: set a fallback `STARTED` message.
- `onTaskFailed`: describe the failure by **exception type**, without writing sensitive data content.
- `onTaskEnd`: change to `COMPLETED` only when there is no failure indicator; on the error branch, **preserve the failure message**.

~~~java
package example.task;

import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class ExitSummaryListener implements TaskExecutionListener {

    @Override
    public void onTaskStartup(TaskExecution execution) {
        execution.setExitMessage("STARTED");
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable failure) {
        // Do not put failure.getMessage() or stack traces into
        // exitMessage because they may contain sensitive information.
        execution.setExitMessage(
                "FAILED; errorType=" + failure.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        String existing = execution.getExitMessage();

        // @AfterTask still runs after @FailedTask, so we must
        // avoid overwriting the error message that was just set.
        if (existing != null && existing.startsWith("FAILED;")) {
            return;
        }

        Integer code = execution.getExitCode();
        if (Integer.valueOf(0).equals(code)) {
            execution.setExitMessage("COMPLETED; exitCode=0");
        } else {
            // Do not label as SUCCESS when the exit code is an error or unknown.
            execution.setExitMessage("ENDED; exitCode=" + code);
        }
    }
}
~~~

This is **a Spring bean**, so the callbacks are discovered by the framework through `TaskExecutionListener`. In a real application, you need `spring-cloud-starter-task`, an appropriate `DataSource`/`TaskRepository` if you want persistent metadata, and a runner executing the work. You do not call `onTaskStartup`, `onTaskFailed`, or `onTaskEnd` manually from business code.

Minimal configuration example for a task using PostgreSQL with the schema already created:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
~~~

The `TASK_DB_*` variables come from environment/secret stores; metadata tables must be created using the DDL matching your deployed Spring Cloud Task version. This is not runnable standalone without supplying dependencies, a runner, and a database.

### 4.1. Success Scenario

Suppose the runner receives `--date=2026-11-23`, generates the report, and returns normally:

~~~text
onTaskStartup: exitMessage = STARTED
runner: report generated successfully
onTaskEnd:     exitMessage = COMPLETED; exitCode=0
TaskRepository.EXIT_MESSAGE = COMPLETED; exitCode=0
~~~

`COMPLETED` describes **the completion status of the run**, not proof that the report table was properly published to users. Business results still need verification in the report destination.

### 4.2. Failure Scenario

Suppose the runner throws `IllegalArgumentException` due to an invalid report date:

~~~text
onTaskStartup: exitMessage = STARTED
runner: throws IllegalArgumentException
onTaskFailed:  exitMessage = FAILED; errorType=IllegalArgumentException
onTaskEnd:     preserved because the message already starts with FAILED;
TaskRepository.EXIT_MESSAGE =
    FAILED; errorType=IllegalArgumentException
~~~

**The failure value is preserved because we deliberately skipped overwriting it in `onTaskEnd`**, not because Spring Cloud Task skips `onTaskEnd` after an error.

### 4.3. Non-Exception Failure Case

A task can intentionally emit a non-zero exit code without throwing an unhandled exception. In that case, `onTaskFailed` might not be called. The `onTaskEnd` branch in the example sets `ENDED; exitCode=...` to avoid a false "success" message. Depending on business needs, you can record a more detailed outcome when the exit code source is known.

## 5. Example 2: Using `@BeforeTask`, `@FailedTask`, and `@AfterTask` Annotations

Implementing the interface is not mandatory. Spring Cloud Task supports annotations on bean methods:

~~~java
package example.task;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedExitMessages {

    @BeforeTask
    public void before(TaskExecution execution) {
        execution.setExitMessage("STARTED");
    }

    @FailedTask
    public void failed(
            TaskExecution execution, Throwable cause) {
        execution.setExitMessage(
                "FAILED; errorType=" + cause.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        // Only illustrates how to preserve the value from @FailedTask.
        String current = execution.getExitMessage();
        if (current != null && current.startsWith("FAILED;")) {
            return;
        }
        if (Integer.valueOf(0).equals(execution.getExitCode())) {
            execution.setExitMessage("COMPLETED");
        }
    }
}
~~~

**Choose only one of the two listener registration styles for the lab.** If you register both `ExitSummaryListener` from the previous section and `AnnotatedExitMessages` in the same application, both will write to the same `TaskExecution`. You must clearly resolve who owns `exitMessage` to avoid results depending on bean/callback order.

The `@FailedTask` annotation also receives `Throwable` so you can classify the error; avoid outputting `Throwable.getMessage()` verbatim unless its contents are sanitized. Exceptions may contain emails, internal paths, connection strings, or slices of input data.

## 6. Designing Business-Friendly Exit Messages

### 6.1. Message Conventions

A good message typically answers **what ran, what happened, and where to trace it**. You can use a short, fixed `key=value` format:

~~~text
COMPLETED; operation=import; sourceId=abc-20261123; accepted=980; rejected=20
FAILED; operation=report; reason=INVALID_DATE; reportDate=2026-11-23
SKIPPED; operation=cleanup; reason=NO_ELIGIBLE_ROWS; cutoff=2026-10-01
~~~

You do not need to cram every detail into one line. For large reports, store only a safe `reportId` or `artifactId`; for data imports, store `sourceId` and valid/rejected counts. Avoid generic `"Task done"` messages that prevent readers from telling what the task actually did.

| Case | Where to Set `exitMessage`? | Suggestion |
| --- | --- | --- |
| Import succeeded | `onTaskEnd`, once summary counts are available | `IMPORTED; sourceId=...; accepted=...` |
| File read error | `onTaskFailed` | `FAILED; reason=INPUT_UNREADABLE` |
| Transient connection error | `onTaskFailed` | `FAILED; reason=DEPENDENCY_UNAVAILABLE` |
| Report already exists | `onTaskEnd` or via supplied business status | `SKIPPED; reason=ALREADY_GENERATED` |
| Cleanup found no eligible rows | `onTaskEnd` | `COMPLETED; deleted=0` |
| Input configuration check | `onTaskStartup` sets fallback only | `STARTED`; final result should come after runner |

If you need to pass record counts, checksums, or report IDs from the runner to a listener, pass them through **a bean holding per-run summary state** or a clear internal result mechanism. In a standard Spring Cloud Task application, each process executes one run and exits; in complex setups, still avoid sharing mutable state across concurrent runs.

### 6.2. Example: Sharing Results from Runner to Listener

The snippet below is a **design pattern**, not a built-in feature of `TaskRepository`. The `RunSummary` bean belongs to the current process; the runner records counts, and the listener reads them to format `exitMessage`.

~~~java
@Component
public class RunSummary {
    private long accepted;
    private long rejected;

    public void record(long accepted, long rejected) {
        this.accepted = accepted;
        this.rejected = rejected;
    }

    public String asExitMessage() {
        return "IMPORTED; accepted=" + accepted
                + "; rejected=" + rejected;
    }
}

@Component
public class ImportSummaryListener {

    private final RunSummary summary;

    public ImportSummaryListener(RunSummary summary) {
        this.summary = summary;
    }

    @AfterTask
    public void after(TaskExecution execution) {
        if (Integer.valueOf(0).equals(execution.getExitCode())) {
            execution.setExitMessage(summary.asExitMessage());
        }
        // Do not overwrite the error message if the execution already failed.
    }
}
~~~

This example assumes `RunSummary` is instantiated **once per Task process** and updated by the runner before completion. In applications with asynchronous processing, await all subtasks and ensure memory/result visibility before the listener executes. Otherwise, the message may contain incomplete counts.

A production application must also distinguish cases where the runner **skipped processing** because data was already finalized; do not automatically label the message `IMPORTED` just because the exit code is `0` if no import occurred.

## 7. When Is `exitMessage` Persisted to the Database?

In a normal Task run, the framework opens `TaskExecution` at the start of the lifecycle and updates completion fields when the task finishes. `onTaskEnd` runs **before the final result update**. Therefore, calling:

~~~java
taskExecution.setExitMessage("COMPLETED; rows=980");
~~~

inside the callback mutates the `TaskExecution` object received by the listener. Spring Cloud Task aggregates callback outcomes and passes `exitMessage` to `TaskRepository` upon completion.

Expected data after termination can be verified with the following SQL query using named parameters in an application:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = :execution_id;
~~~

`:execution_id` is a data-access layer placeholder, not literal SQL syntax supported directly across all tools. If a custom `table-prefix` or schema is configured, adjust the table name accordingly.

| Observation in `TaskRepository` | Interpretation |
| --- | --- |
| `EXIT_CODE=0`, `EXIT_MESSAGE=COMPLETED...` | Process exited with success code; continue checking business outputs if needed |
| `EXIT_CODE<>0`, `EXIT_MESSAGE=FAILED...` | Failure recorded with concise description; use logs and `ERROR_MESSAGE` to diagnose |
| `EXIT_MESSAGE=FINISHED` despite task failure | Suspect `onTaskEnd` overwrote the content set by `onTaskFailed` |
| `EXIT_MESSAGE` empty/`NULL` | No custom message set, callback did not run, or persistence failed |
| `END_TIME` remains empty for too long | Process may still be running or died before updating; inspect container/launcher |

Do not treat `EXIT_MESSAGE` as a real-time time-series log. In the default model, it is an **execution summary field**, primarily meaningful after `TaskRepository` finishes updating. If you need minute-by-minute live progress, use structured logs, a business progress table, or a metrics system.

### Distinguishing `exitMessage` from Spring Batch Status

In a task integrated with **Spring Batch**, `JobExecution.exitStatus.exitDescription` belongs to Batch's **`JobRepository`** metadata, whereas `TaskExecution.exitMessage` belongs to Spring Cloud Task's **`TaskRepository`**. The two values do not synchronize automatically. If a Batch Job fails while the Task process still exits with `0`, merely setting `exitMessage` to `FAILED` will not tell the scheduler the process failed. You must configure a mechanism to translate Batch Job failures into an appropriate exit code (for example, `spring.cloud.task.batch.fail-on-job-failure` when supported by your version and Batch integration), or explicitly propagate the failure by design.

## 8. Exceptions in Listeners and Their Impact on Outcomes

Listeners are part of the Task termination sequence. If a callback itself throws an exception, remaining listeners **in that same callback phase** may stop executing. The framework has logic to record listener errors and determine exit codes, yet listener exceptions should never be used routinely as a way to craft business messages.

According to the Spring Cloud Task guide:

- If an exception occurs in `onTaskStartup`, startup can fail and the resulting exit code is handled as `1`.
- If an exception occurs in `onTaskFailed` or `onTaskEnd`, the exit code follows the framework's exit-code calculation mechanism (including `ExitCodeEvent` or `ExitCodeGenerator` where applicable).
- When an exception originates **inside a listener callback**, do not expect `ExitCodeExceptionMapper` to customize the exit code the way it does for ordinary business exceptions.

This leads to a core principle: **callbacks setting `exitMessage` must be brief, stable, and minimally dependent on external systems**. Never make slow API calls, write large payloads, or wait on non-essential services inside `onTaskEnd` just to build a description string; failure of that operation itself can complicate the final state.

If the message summarizes business data, business logic should persist status and metrics beforehand. The listener merely formats existing results, avoiding a "second source of truth."

## 9. Security and Data Limits

### 9.1. Never Put Sensitive Data in `exitMessage`

Avoid:

~~~text
FAILED; dbPassword=secret123
FAILED; customerEmail=person@example.com; rawRecord=...
FAILED; jdbcUrl=jdbc:...; token=...
~~~

Replace with:

~~~text
FAILED; reason=DB_UNAVAILABLE; incidentRef=INC-20261124-001
FAILED; reason=INPUT_VALIDATION; sourceId=orders-20261123
~~~

Operators can use non-sensitive **incidentRef**, **sourceId**, or **reportId** values to query access-controlled detail systems. Never copy raw `Throwable.getMessage()` into `EXIT_MESSAGE` unless guaranteed sanitized.

### 9.2. Preventing Field Overflow and Hard-to-Query Messages

The reference schema defines `EXIT_MESSAGE` as `VARCHAR(2500)`. Because database engines and versions vary, enforce an **application limit well below the DB limit** (such as a few hundred characters) and define a stable set of reason codes.

If you need to record thousands of CSV row errors, write the details to a results table or a managed error file, and let `exitMessage` hold a summary:

~~~text
FAILED; reason=ROW_VALIDATION; rejected=147; errorReportId=err-20261124-01
~~~

This separation avoids repository write failures right at shutdown caused by oversized messages. Never use `exitMessage` to pass payloads to another task or as a data key.

## 10. Common Mistakes and How to Fix Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Failed yet `EXIT_MESSAGE=FINISHED` | `@AfterTask` overwrote unconditionally | Set success messages only when confirmed successful; preserve error messages |
| `STARTED` message remains after task succeeded | Only startup wrote a message | Populate the completion message at end |
| `EXIT_CODE=0` yet message says `FAILED` | Listener set the string without reflecting failure in exit code | Redesign success/failure rules; check exception paths and batch exit behavior |
| `EXIT_MESSAGE` field is blank | No listener set a message or it was overwritten with blank | Check bean/annotation registration, callback order, and `setExitMessage("")` |
| Multiple listeners produce shifting results after refactoring | Multiple callbacks own the message in one phase | Consolidate into a single summary listener; test whenever using multiple listeners |
| End callback throws an exception | Unnecessary I/O or unsafe formatting | Keep callbacks lean, compute data earlier, use safe string formatting |
| `exitMessage` truncated or DB throws length error | String exceeds schema limit | Record only a summary and link an ID to detailed data |
| No `TaskExecution` record found | `ApplicationContext` failed to initialize or repository misconfigured | Check startup logs, `DataSource`, migrations, and environment |
| After Task dies, `END_TIME` remains empty | Process was killed before the final callback | Use Job/Pod status and timeouts to detect; never expect listeners to always run |

## 11. Scenarios to Verify Precedence Order

After registering **one** listener following section 4 or 5, run these verifications against a test database.

**Scenario A — success:**

1. The runner receives valid input and completes normally.
2. `onTaskStartup` sets `STARTED`; `onTaskEnd` sets `COMPLETED`.
3. Query `TASK_EXECUTION` to confirm `EXIT_CODE=0` and `EXIT_MESSAGE=COMPLETED...`.

**Scenario B — failure:**

1. The runner throws `IllegalArgumentException` due to invalid parameters.
2. `onTaskFailed` sets `FAILED; errorType=IllegalArgumentException`.
3. `onTaskEnd` preserves the message.
4. Query the repository to observe the error message, non-zero exit code, and `ERROR_MESSAGE` if the framework recorded the exception.

**Scenario C — intentional override:**

1. In a test environment, change `onTaskEnd` to unconditionally call `execution.setExitMessage("FINISHED")`.
2. Re-run the failure scenario.
3. Confirm `EXIT_MESSAGE=FINISHED` while `EXIT_CODE` still indicates failure; then restore the message-preserving logic.

**Scenario D — multiple listeners:**

1. Register two listeners that both write a message in `onTaskEnd`.
2. Observe which callback writes last in your current version.
3. Refactor so only one listener owns the final result message, avoiding dependency on registration order.

**Scenario E — abrupt process termination:**

1. In a test environment, kill the process while the runner is executing.
2. Inspect `TaskExecution` and orchestrator logs.
3. Explain why `onTaskEnd` and the final message may be missing and why timeouts/independent monitoring are required.

Success criterion: you **accurately predict `EXIT_MESSAGE`** for every scenario and distinguish exit messages, exit codes, and error messages without treating the message string as the sole indicator of success.

## 12. Key Takeaways

1. Set `exitMessage` via `TaskExecution#setExitMessage(String)` inside `TaskExecutionListener` or `@BeforeTask`, `@FailedTask`, and `@AfterTask`.
2. **Update precedence order:** `onTaskEnd` takes **precedence over** `onTaskFailed`, and `onTaskFailed` takes **precedence over** `onTaskStartup`.
3. `onTaskEnd` can still run after failure; if it sets a new message, the value written by `onTaskFailed` can be replaced.
4. Avoid multiple listeners owning `exitMessage`; test thoroughly if multiple callbacks are required, and never pass an empty string to mean "leave unchanged."
5. **`exitMessage`, `exitCode`, and `errorMessage` serve different roles.** A message that looks like "success" does not prove the process succeeded.
6. Keep messages short, safe, with stable reason codes and references to detailed data outside the repository.
7. Listeners should finish quickly and avoid heavy external dependencies; an abnormally terminated process may never persist final status.

### References

- [Spring Cloud Task — Features: Task Execution Listener, Exit Messages](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Javadoc: `TaskExecutionListener`](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
- [Javadoc: `TaskExecution`](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
