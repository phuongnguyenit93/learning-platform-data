# Reading `TaskExecution` and `Throwable` in Spring Cloud Task Listeners

## 1. Objective and Real-World Problem

A **Spring Cloud Task** application runs for a finite duration to import data, export reports, reconcile records, or launch a Spring Batch Job. Each run can be represented by a **`TaskExecution`** and stored in **`TaskRepository`**. When a task fails, operators need to know which run failed, why it failed, how far results were persisted, and whether it can be safely retried.

Suppose a CronJob runs a reconciliation task:

~~~bash
java -jar payment-reconcile-task.jar --date=2026-11-23
~~~

If the database temporarily drops its connection, **`TaskExecutionListener`** can receive the failure callback, inspect `TaskExecution` to obtain the execution ID, task name, and start time, and inspect **`Throwable`** to classify the cause. The listener can also populate a short completion description in `exitMessage` before final metadata is written to the repository.

Distinguish three kinds of information: **`TaskExecution` describes the application execution**; **`Throwable` describes the actual Java error**; **business data** (such as reconciled transactions) lives in its own results store. Listeners provide lifecycle observability; they do not guarantee transactions, retries, or saving full business outputs.

## 2. The Three Callbacks and Lifecycle Sequence

The `org.springframework.cloud.task.listener.TaskExecutionListener` interface defines three methods:

~~~java
public interface TaskExecutionListener {
    void onTaskStartup(TaskExecution taskExecution);
    void onTaskEnd(TaskExecution taskExecution);
    void onTaskFailed(TaskExecution taskExecution, Throwable throwable);
}
~~~

| Callback | Received Data | Role |
|---|---|---|
| `onTaskStartup` | `TaskExecution` | Observes the task during startup; logs identifiers, metrics, and context |
| `onTaskFailed` | `TaskExecution` and **`Throwable`** | Analyzes unhandled exceptions, tags error categories, sets exit messages |
| `onTaskEnd` | `TaskExecution` | Observes the task as it finishes; can adjust `exitMessage` before the repository is updated with final status |

The sequence on the normal branch is **startup → end**. When a task fails due to an unhandled exception and the lifecycle mechanism is still active, the sequence is **startup → failed → end**. `onTaskFailed` arrives before `onTaskEnd`.

~~~mermaid
sequenceDiagram
    participant O as CLI / Scheduler
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant B as Business Service
    participant R as TaskRepository
    O->>T: Launch application
    T->>L: onTaskStartup(TaskExecution)
    T->>R: Write initial metadata
    T->>B: Runner invokes business logic
    alt Business logic completes
        B-->>T: Complete
    else Unhandled exception
        B-->>T: Throw exception
        T->>L: onTaskFailed(TaskExecution, Throwable)
    end
    T->>L: onTaskEnd(TaskExecution)
    T->>R: Update completion metadata
    T-->>O: Return result/exit code
~~~

This is a **conceptual** diagram. The Spring Cloud Task reference documentation varies across some versions/Javadocs regarding the exact timing of `onTaskStartup` relative to writing the initial record. Therefore, do not assume the record is already committed and readable from another connection inside `onTaskStartup`. `onTaskEnd` is called **before** `TaskRepository`'s final update step, so status fields inside the callback are not yet definitive proof of committed state either.

Spring Cloud Task records a run once the application context bootstraps far enough for task infrastructure to initialize; failures occurring earlier than that may produce no `TaskExecution`. When the JVM suffers a `SIGKILL`, crash, or power loss, end callbacks and metadata persistence are **not guaranteed**.

## 3. Reading `TaskExecution`: Field-by-Field Meaning

`TaskExecution` belongs to the `org.springframework.cloud.task.repository` package. Commonly used getters:

| Getter | Return Type | Meaning |
|---|---|---|
| `getExecutionId()` | `long` | Unique ID of the run; use as the correlation key |
| `getTaskName()` | `String` | Task application name determined by the task-name resolver |
| `getStartTime()` | `LocalDateTime` | Timestamp when the task started |
| `getEndTime()` | `LocalDateTime` | Timestamp when it ended; may be unset at startup |
| `getExitCode()` | `Integer` | Expected/recorded exit code; may be `null` until finalized |
| `getExitMessage()` | `String` | Completion message, which can be set by a listener |
| `getErrorMessage()` | `String` | Error details recorded by the framework; may contain a stack trace |
| `getArguments()` | `List<String>` | Command-line arguments passed to the application |
| `getExternalExecutionId()` | `String` | ID from an external system if configured |
| `getParentExecutionId()` | `Long` | ID of the parent execution, if any |

Example:

~~~java
long executionId = taskExecution.getExecutionId();
String taskName = taskExecution.getTaskName();
var startedAt = taskExecution.getStartTime();
Integer exitCode = taskExecution.getExitCode();

log.info(
    "task.lifecycle id={} name={} startedAt={} exitCode={}",
    executionId, taskName, startedAt, exitCode
);
~~~

To check the exit code, handle a potentially `null` `Integer`:

~~~java
boolean success = Integer.valueOf(0)
    .equals(taskExecution.getExitCode());
~~~

Do not write `taskExecution.getExitCode() == 0` if there is any risk of unboxing `null`. Likewise, do not unconditionally read `getEndTime()` and compute duration inside `onTaskStartup`.

**`getArguments()` may contain passwords, tokens, or sensitive data.** Avoid logging all arguments verbatim; if you need the processing date, parse a non-sensitive option at the runner layer and attach context through controlled mechanisms.

## 4. Reading `Throwable` to Find the Root Cause

Only the `onTaskFailed` callback receives **`Throwable`** directly:

~~~java
@Override
public void onTaskFailed(
        TaskExecution taskExecution,
        Throwable throwable) {
    String type = throwable.getClass().getName();
    String message = throwable.getMessage();
    Throwable cause = throwable.getCause();
}
~~~

`Throwable` is the superclass of both `Exception` and `Error`, allowing you to inspect:

- `getClass().getName()`: the exception or error type.
- `getMessage()`: the message, which may be `null` and may contain sensitive data.
- `getCause()`: the direct underlying cause when exceptions are wrapped across layers.
- `getSuppressed()`: suppressed exceptions, such as during resource closing.
- `getStackTrace()`: failure location, for use in internal access-controlled logging systems.

Example cause chain:

~~~text
CompletionException
  └── IllegalStateException: import failed
       └── SQLTransientConnectionException: database unavailable
~~~

You can walk to the root cause without parsing stack-trace text:

~~~java
private static Throwable rootCause(Throwable original) {
    Throwable current = original;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

When the root cause is `SQLTransientConnectionException`, that is a signal to **evaluate** a retry. You still cannot conclude "retrying is always safe," because business logic might have partially committed before the error. Idempotency, checkpoints, or reconciliation matching are required depending on your requirements.

### Distinguishing `Throwable` from `errorMessage`

`Throwable` is the actual live Java error object available at callback time, whereas `TaskExecution.getErrorMessage()` is the string persisted (or prepared for persistence) in metadata by the framework. The `errorMessage` field may not yet be populated at callback time, may be length-truncated, or may reflect a formatted stack trace. Thus, inside `onTaskFailed`, prefer **`Throwable` to classify errors**; when querying past runs via the repository, use `errorMessage` as supporting evidence.

Never put raw `throwable.getMessage()`, stack traces, or `getArguments()` into `exitMessage`, dashboards, or unrestricted logs; those values can leak SQL queries, paths, tokens, or personal data.

## 5. Example Implementation of `TaskExecutionListener`

The following example logs task name, ID, start time, root error type, and sets a concise `exitMessage`. The bean is registered with `@Component`.

~~~java
package example.task;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener implements TaskExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(AuditTaskListener.class);

    @Override
    public void onTaskStartup(TaskExecution execution) {
        log.info(
            "task.started executionId={} taskName={} startTime={}",
            execution.getExecutionId(),
            execution.getTaskName(),
            execution.getStartTime()
        );
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable throwable) {

        Throwable cause = rootCause(throwable);
        String rootType = cause.getClass().getSimpleName();

        // Do not log the original message without a data-masking policy.
        log.error(
            "task.failed executionId={} name={} rootType={}",
            execution.getExecutionId(),
            execution.getTaskName(),
            rootType
        );

        execution.setExitMessage("FAILED: " + rootType);
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        log.info(
            "task.ending executionId={} exitCode={}",
            execution.getExecutionId(),
            execution.getExitCode()
        );

        // Preserve the message already set in onTaskFailed.
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("Task execution ended");
        }
    }

    private static Throwable rootCause(Throwable original) {
        Throwable current = original;
        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

**Design choices explained:**

1. Read the `TaskExecution` object passed directly by the framework rather than querying the repository again inside the callback.
2. Attach `executionId` to logs to distinguish multiple runs sharing the same `taskName`.
3. On failure, extract the root cause type from `Throwable` and set a short `exitMessage` containing no business data or stack trace.
4. `onTaskEnd` avoids overwriting an error message that was already set; it only populates the message if still null.
5. Never arbitrarily alter `exitCode` inside a callback; exit codes and exception-mapping policies should be handled intentionally at the application/framework layer.

This listener only provides observation. If `RevenueService` or `ImportService` submits `@Async` work to an executor and the runner returns immediately, the listener **does not automatically know** whether all futures completed. The runner must await and inspect errors from mandatory tasks before finishing.

## 6. Registering via Annotations Instead of the Interface

Spring Cloud Task supports a concise annotation-based style:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedTaskObserver {

    private static final Logger log =
        LoggerFactory.getLogger(AnnotatedTaskObserver.class);

    @BeforeTask
    public void before(TaskExecution execution) {
        log.info("Before task {}", execution.getExecutionId());
    }

    @FailedTask
    public void failed(
            TaskExecution execution, Throwable throwable) {
        log.warn("Task {} failed: {}",
            execution.getExecutionId(),
            throwable.getClass().getSimpleName());
        execution.setExitMessage("FAILED");
    }

    @AfterTask
    public void after(TaskExecution execution) {
        log.info("After task {}", execution.getExecutionId());
    }
}
~~~

| Interface | Corresponding Annotation |
|---|---|
| `onTaskStartup(TaskExecution)` | `@BeforeTask` |
| `onTaskFailed(TaskExecution, Throwable)` | `@FailedTask` |
| `onTaskEnd(TaskExecution)` | `@AfterTask` |

Both styles can be used in the same application for distinct responsibilities, but avoid accidentally registering **two listeners emitting the same metrics/logs** for the same purpose. Do not depend on implicit ordering among independent listener beans. Spring Cloud Task annotations are also **different** from Spring Batch annotations like `@BeforeStep` and `@AfterStep`.

## 7. `ExitMessage`, `ErrorMessage`, and `ExitCode`

| Field | Purpose | Example |
|---|---|---|
| `exitMessage` | Summary message settable in a listener | `FAILED: SQLTransientConnectionException` |
| `errorMessage` | Error description saved by the framework; may contain a stack trace | `... SQLException ...` |
| `exitCode` | Run exit code determined by framework/application mechanisms | `0` or `1` |

Spring Cloud Task documentation specifies the **precedence order when listeners set `exitMessage`**:

1. Values set in `onTaskEnd` take highest precedence.
2. Next are values set in `onTaskFailed`.
3. Finally values set in `onTaskStartup`.

Consequently, if `onTaskFailed` sets `FAILED` while `onTaskEnd` unconditionally sets `SUCCESS`, metadata can be overwritten with a misleading message. If exit messages should reflect business outcomes, establish a consistent rule and never assume "entering `onTaskEnd` means success."

`exitMessage` does not replace exit codes or business status. When specific error codes are required, Spring Boot provides mechanisms such as `ExitCodeExceptionMapper` and `ExitCodeGenerator` depending on version and exception handling. Align these outcomes with your orchestrator instead of treating an `exitMessage` string as the sole basis for retries.

## 8. Why Is `onTaskFailed` Sometimes Not Called?

Spring Cloud Task only invokes `onTaskFailed` for errors **observable by the task lifecycle**. If a runner swallows an exception and returns normally, the failure callback may never appear.

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner unsafeRunner(ReportService service) {
    return args -> {
        try {
            service.exportAll();
        } catch (Exception ex) {
            // Only logs and returns:
            // the framework may treat the runner as successful.
            System.err.println(ex.getClass().getSimpleName());
        }
    };
}
~~~

A better approach:

~~~java
@Bean
ApplicationRunner safeRunner(ReportService service) {
    return args -> {
        // Let the business error propagate to the task execution flow.
        service.exportAll();
    };
}
~~~

If you need to attach correlation-ID logs, catch and **rethrow the exception**; never hide the error and expect a listener to infer failure from a log line.

In particular, with `CompletableFuture`, `@Async`, and `TaskExecutor`, dispatching work to another thread and returning early can cause the task to be finalized as successful. Await completion, inspect exceptions inside futures, and enforce bounded timeouts. If restart recovery is required, add durable state persistence outside JVM memory.

## 9. When a Listener Itself Throws an Exception

This is a critical operational pitfall. Suppose `onTaskFailed` calls a network alerting system; if the alerting API times out and throws an error, the listener can trigger a **secondary exception** while the framework is trying to record the original failure.

Spring Cloud Task documentation notes that when a listener callback throws an exception, invocation of remaining listeners for that event type may stop. Exceptions in `onTaskStartup` have specific exit-code rules; exceptions in `onTaskFailed` or `onTaskEnd` should not be assumed to always become exit code `1`. Nor does `ExitCodeExceptionMapper` necessarily handle exceptions thrown by listeners themselves the same way as business exceptions.

Pattern to avoid:

~~~java
@Override
public void onTaskFailed(
        TaskExecution execution, Throwable throwable) {
    externalAlertService.send(throwable); // I/O may hang or fail.
}
~~~

Fault-tolerant pattern for non-mandatory monitoring:

~~~java
@Override
public void onTaskFailed(
        TaskExecution execution, Throwable throwable) {
    try {
        metrics.recordFailure(
            execution.getTaskName(),
            throwable.getClass().getSimpleName()
        );
    } catch (RuntimeException monitoringError) {
        log.warn("Cannot record metric for task {}",
            execution.getExecutionId());
    }
    execution.setExitMessage("FAILED");
}
~~~

`metrics` is an application-provided monitoring service, not a built-in API on `TaskExecutionListener`. If auditing must be durable, persist audit records at the business layer within a transaction or outbox with its own retry mechanism. Listener callbacks are ill-suited for executing long network transactions when the process needs to terminate.

## 10. Querying Persisted `TaskExecution` Records

After a run finishes, use `TaskRepository` or query metadata to confirm committed fields. SQL example with default table names:

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
ORDER BY TASK_EXECUTION_ID DESC;
~~~

If the project customizes `table-prefix` or schema, adjust table names accordingly. Do not assume default table names when the system uses custom migrations and configuration.

~~~mermaid
flowchart TD
    L["TaskExecutionListener"] --> A["Log: executionId, taskName, errorType"]
    L --> R["TaskRepository: status and exitMessage"]
    B["Business Service"] --> D["Business results/checkpoint store"]
    O["CronJob/API/orchestrator"] --> X["Exit code and process status"]
    A --> I["Incident analysis"]
    R --> I
    D --> I
    X --> I
~~~

**Do not infer solely from `END_TIME IS NULL` that a task definitely failed:** the task may still be running, hung, or dead before updating metadata. Cross-check container/JVM state, logs, and business data before deciding to re-run.

If processing has already written business data and the JVM is killed before `TaskRepository` finalizes the run, business data may be complete while metadata remains incomplete. On retry, use idempotency keys and check business state to avoid duplicating outcomes.

## 11. Spring Cloud Task Listeners vs. Spring Batch Listeners

In an application that uses Spring Batch, distinguish:

| Component | Tracked Unit | Listener / Inspection Store |
|---|---|---|
| Spring Cloud Task | One **application** run | `TaskExecutionListener`, `TaskRepository` |
| Spring Batch | One **job** run and each step | `JobExecutionListener`, `StepExecutionListener`, `JobRepository` |
| Business domain | Transactions, files, reports, messages | Business services and tables/stores |

`TaskExecutionListener.onTaskFailed(TaskExecution, Throwable)` reports failure at the application-run level. It does not replace analyzing `JobExecution` and step-level exceptions in Spring Batch.

A Batch job can fail without the runner throwing an exception if the application does not inspect `JobExecution` status; in that case, the application-level task may be recorded as successful. You must explicitly design how job outcomes map to task outcomes.

## 12. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Listener is not invoked | Bean not registered/scanned; Spring Cloud Task not enabled/configured properly | Check dependencies, `@Component`/`@Bean`, and bootstrap process |
| Exception occurs but `onTaskFailed` does not run | Runner swallowed the error or error occurred in an unawaited future | Propagate errors to the runner; await and inspect futures |
| `getExitCode()` is `null` | Final code not yet set | Handle nullable values and query repository after execution |
| `getEndTime()` is empty at startup | Run has not ended yet | Only compute duration when both timestamps are present |
| `getErrorMessage()` is empty in failure callback | Metadata not populated yet or callback runs earlier | Read `Throwable` directly |
| `exitMessage` set on failure disappears | Overwritten by `onTaskEnd` or another listener | Review ordering and conditional setter logic |
| Logs leak secrets | Logging raw arguments/exceptions | Mask secrets; log only identifiers and error types |
| DB metadata differs from listener logs | Callback ran before commit, repository error, or crash | Cross-check repository, process state, and business data |
| Task exits 0 despite missing report | Async work unfinished; business criteria unchecked | Await completion and propagate errors outward |
| Callback error hides original failure details | Listener called an external API and threw an exception | Separate critical auditing, bound I/O, and catch auxiliary errors |

## 13. Lab: Verifying Both Success and Failure Branches

Create a sample task with Spring Cloud Task, a datasource, and version-appropriate metadata schema, along with the `AuditTaskListener` above. The runner accepts `--mode`:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DemoTaskConfiguration {

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            var modes = args.getOptionValues("mode");
            if (modes == null || modes.size() != 1) {
                throw new IllegalArgumentException(
                    "Use --mode=success or --mode=fail");
            }

            switch (modes.get(0)) {
                case "success" -> System.out.println("Completed");
                case "fail" -> throw new IllegalStateException(
                    "Simulated failure");
                default -> throw new IllegalArgumentException(
                    "Unsupported mode");
            }
        };
    }
}
~~~

Run in sequence:

~~~bash
java -jar demo-task.jar --mode=success
java -jar demo-task.jar --mode=fail
~~~

Expected observations:

1. The success branch runs `onTaskStartup` and `onTaskEnd`, with no `onTaskFailed`.
2. The failure branch runs `onTaskStartup`, `onTaskFailed`, and then `onTaskEnd` when the application handles the error through the normal lifecycle.
3. `executionId` differs between the two runs.
4. `Throwable` on the failure branch reveals `IllegalStateException` (or a wrapper class depending on execution path).
5. After each run, query `TaskRepository` to verify `exitCode`, `exitMessage`, and end timestamp.
6. Try catching and swallowing the exception in the runner to observe why the failure callback may not run.

When testing `SIGTERM`, `SIGKILL`, or an unreachable database, never assume every listener or metadata write always executes. That is an inherent limit of a finite-lived process.

## 14. Conclusion and Checklist

For a **Spring Cloud Task** application that needs to track failures and task outcomes in a database:

- Use `TaskExecution` to obtain **execution ID, name, timestamps, exit code, and messages**; always handle potentially `null` fields.
- Use `Throwable` in `onTaskFailed` to read **error type, cause chain, and stack trace when needed**.
- Set concise, safe `exitMessage` values; avoid overwriting failure messages in `onTaskEnd`.
- Let business exceptions propagate out of runners and await mandatory asynchronous tasks.
- Keep listeners lightweight, avoiding unbounded I/O or secondary errors that mask root causes.
- Cross-check listener logs, `TaskRepository` metadata, business outputs, and orchestrator status.
- Design retries and idempotency, since end callbacks may not run when the JVM is killed.

**`TaskExecutionListener` is the lifecycle observation and error-interpretation hook; `TaskRepository` is where execution metadata is stored.** Using both mechanisms properly alongside explicit exception handling and business result persistence enables safe operation of scheduled and on-demand tasks.

### References

- [Spring Cloud Task — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — `TaskExecution` API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
- [Spring Cloud Task — `TaskExecutionListener` API](https://docs.spring.io/spring-cloud-task/docs/2.3.4/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
