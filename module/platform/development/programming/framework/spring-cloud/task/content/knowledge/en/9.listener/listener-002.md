# onTaskStartup, onTaskEnd, and onTaskFailed

## 1. Why Does Spring Cloud Task Need Listeners?

**Spring Cloud Task** is used to build Spring Boot applications with a **finite runtime**: start up, execute a task, record the execution result into **TaskRepository**, and shut down. For example, each day a system exports a report, imports a data file, or reconciles transactions for a given date parameter.

In the **Listener** chapter, we need to observe **key lifecycle moments** without inserting the same boilerplate check into every `ApplicationRunner` or `CommandLineRunner`. Spring Cloud Task provides the **`TaskExecutionListener`** interface with three methods:

- **`onTaskStartup(TaskExecution)`:** called when the task lifecycle begins.
- **`onTaskEnd(TaskExecution)`:** called when the task reaches the completion phase, **for both success and failure** on framework-handled paths.
- **`onTaskFailed(TaskExecution, Throwable)`:** called when the framework catches an **unhandled** error during task execution.

A listener is suitable for **writing logs tagged with an execution ID, providing concise audit information, updating an exit message, or emitting metrics**. It does not replace business logic, schedulers, retry mechanisms, or business data transactions.

**Expected lesson outcome:** you will be able to write a Java listener, predict callback ordering for success and failure cases, correlate logs with `TASK_EXECUTION` records, and avoid common operational pitfalls when a listener throws an exception or overwrites failure details.

## 2. How Do the Three Callbacks Differ?

| Callback | Timing and Condition | Parameters | Common Usage |
| --- | --- | --- | --- |
| `onTaskStartup` | Once Spring Cloud Task has a `TaskExecution` object for the run, before runner business processing | `TaskExecution` | Log execution ID, task name, and start time; prepare observability context |
| `onTaskEnd` | Before the framework updates the final run state in the repository; invoked on both normal completion and framework-handled errors | `TaskExecution` | Log completion, measure duration, set exit message if appropriate |
| `onTaskFailed` | When an unhandled exception causes the task to fail; invoked **before `onTaskEnd`** | `TaskExecution` and `Throwable` | Log error type and stack trace, attach failure message and metrics |

**Note on `onTaskStartup` timing:** the *Features* reference documentation for some versions states that this callback runs before persisting `TaskExecution`, whereas the **TaskExecutionListener 3.0.4 Javadoc** states that it is invoked **after the record has been saved**, matching `TaskLifecycleListener` in the corresponding source code. If your application relies precisely on when the transaction commits or when the ID appears, verify the code and test **on your project's exact version**. Regardless of version, do not build business logic assuming the listener and the database commit belong to the same transaction.

### 2.1. Success Flow

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant R as Runner
    participant DB as TaskRepository

    B->>T: Initialize task lifecycle
    T->>DB: Create / start TaskExecution
    T->>L: onTaskStartup(execution)
    T->>R: Run business logic
    R-->>T: Normal completion
    T->>L: onTaskEnd(execution)
    T->>DB: Update END_TIME, EXIT_CODE, and messages
    Note over T,DB: onTaskFailed is not called on the normal success path
~~~

The key order is: **startup → runner → end → final status update**. If runners merely launch asynchronous work and return immediately, the listener may log completion **before the background work has actually finished**.

### 2.2. Unhandled Error Flow

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant R as Runner
    participant DB as TaskRepository

    T->>DB: Create / start TaskExecution
    T->>L: onTaskStartup(execution)
    T->>R: Run business logic
    R--xT: Unhandled exception
    T->>L: onTaskFailed(execution, throwable)
    T->>L: onTaskEnd(execution)
    T->>DB: Save final result and error message
~~~

**Do not treat `onTaskEnd` as synonymous with "success."** On failure, this callback can still run after `onTaskFailed`. Also never assume callbacks will run if the JVM receives **kill -9**, loses power, runs out of memory, or Spring Boot fails too early to set up the lifecycle.

## 3. What Does `TaskExecution` Contain Inside a Callback?

The **`TaskExecution`** object holds metadata for **one specific run**:

| Property | Meaning and Notes |
| --- | --- |
| `getExecutionId()` | ID used to correlate logs with the TaskRepository record; each run has its own ID |
| `getTaskName()` | Task name, which can repeat across runs |
| `getStartTime()` | Start timestamp recorded by the framework |
| `getEndTime()` | End timestamp set during the lifecycle; not guaranteed to be committed to the database yet inside the callback |
| `getExitCode()` | Status code determined by the framework; interpret according to context and version |
| `getExitMessage()`, `setExitMessage(...)` | Outcome description that a listener can supplement |
| `getErrorMessage()` | Error details captured by the framework; does not replace full logs/stack traces |
| `getArguments()` | Execution arguments; may contain sensitive data, so do not log the raw list carelessly |

**Execution ID** is the technical identifier of each run, while the **business key** (such as a reconciliation date) is the business identifier. If you re-run a task for the same date, the repository can still generate a new execution ID. A listener only observes; it **does not automatically prevent duplicate processing**.

In current versions, the framework may pass a **copy of `TaskExecution`** to listeners and then collect supported changes such as `exitMessage` into the final result. Therefore, do not treat the received object as an entity whose arbitrary fields you can mutate and expect the repository to persist automatically. Use the official API and verify behavior on your target version.

## 4. Creating a Listener with the `TaskExecutionListener` Interface

To clearly learn the three callbacks, the most direct way is to implement **`org.springframework.cloud.task.listener.TaskExecutionListener`** and register that class as a Spring bean.

### 4.1. Sample Configuration

Example `application.yml` for a CLI application that does not start a web server:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-import-task

logging:
  level:
    root: INFO
~~~

To inspect history after the process exits, you need to configure a **persistent DataSource and the Spring Cloud Task schema matching** your library version. The YAML above only configures the lifecycle and task name without providing a database connection; when practicing, add a DataSource for your environment and never commit passwords or secrets into source code.

### 4.2. Full Three-Method Listener

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class TaskAuditListener implements TaskExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditListener.class);

    @Override
    public void onTaskStartup(TaskExecution task) {
        log.info("TASK_START executionId={} name={} startedAt={}",
                task.getExecutionId(),
                task.getTaskName(),
                task.getStartTime());
    }

    @Override
    public void onTaskFailed(TaskExecution task, Throwable error) {
        log.error("TASK_FAILED executionId={} errorType={}",
                task.getExecutionId(),
                error.getClass().getSimpleName(),
                error);

        // Exit message should be concise and contain no secret data.
        task.setExitMessage("FAILED: " + error.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution task) {
        log.info("TASK_END executionId={} exitCode={} endedAt={}",
                task.getExecutionId(),
                task.getExitCode(),
                task.getEndTime());

        // Do not overwrite an error message already set by onTaskFailed.
        if (task.getExitCode() != null
                && task.getExitCode() == 0
                && task.getExitMessage() == null) {
            task.setExitMessage("COMPLETED");
        }
    }
}
~~~

**Why implement it this way?**

- `@Component` allows Spring to discover the listener during component scanning; the framework picks up all registered `TaskExecutionListener` beans.
- `onTaskStartup` logs the ID and name to tie log lines together for a single run.
- `onTaskFailed` preserves the original exception in the logs while setting a concise exit message. Never put full stack traces containing secrets into the message.
- `onTaskEnd` runs on every framework-handled completion path, so it sets `exitMessage` **conditionally**: it only writes `"COMPLETED"` when the exit code indicates normal completion and no error message is already present.
- The listener **does not call `System.exit(...)`**, does not manually modify `TaskRepository`, does not spawn background jobs, and does not throw exceptions just to signal an alert.

In some API versions, all three methods on the interface have default implementations, so you can override only the callback you need. Implementing all three above makes the relationship between the three phases clear.

### 4.3. Runner Demonstrating Success and Failure

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyImportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyImportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DailyImportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner importRunner() {
        return args -> {
            List<String> dates = args.getOptionValues("businessDate");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                        "Must pass --businessDate=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            log.info("IMPORT_BEGIN businessDate={}", date);

            if (args.containsOption("fail")) {
                throw new IllegalStateException("Simulated import failure");
            }

            // Replace with real synchronous data import processing.
            log.info("IMPORT_DONE businessDate={}", date);
        };
    }
}
~~~

The Java imports and bean structure in the two snippets above follow patterns compatible with modern Spring Boot/Spring Cloud Task releases; align your BOM/dependencies with your project version. Reaching `IMPORT_DONE` only proves the runner executed that branch in the example; it does not replace verifying actual results in the business database.

## 5. Practicing Log Inspection Across Two Runs

Suppose you package the code into `daily-import-task.jar`, have prepared the `TaskRepository` schema, and run:

~~~bash
java -jar daily-import-task.jar --businessDate=2026-11-23
~~~

An **illustrative** log sequence:

~~~text
2026-11-24 09:00:00 INFO ... TASK_START executionId=41 name=daily-import-task startedAt=...
2026-11-24 09:00:00 INFO ... IMPORT_BEGIN businessDate=2026-11-23
2026-11-24 09:00:01 INFO ... IMPORT_DONE businessDate=2026-11-23
2026-11-24 09:00:01 INFO ... TASK_END executionId=41 exitCode=0 endedAt=...
~~~

The `executionId=41` field in the example is used consistently to find logs and records for the same run. Do not assume the first run always gets ID `1`; multiple applications or processes may share the same repository.

Run the failure scenario:

~~~bash
java -jar daily-import-task.jar --businessDate=2026-11-24 --fail
~~~

Illustrative logs:

~~~text
2026-11-24 09:10:00 INFO  ... TASK_START executionId=42 name=daily-import-task startedAt=...
2026-11-24 09:10:00 INFO  ... IMPORT_BEGIN businessDate=2026-11-24
2026-11-24 09:10:00 ERROR ... TASK_FAILED executionId=42 errorType=IllegalStateException
java.lang.IllegalStateException: Simulated import failure
    at ...DailyImportTaskApplication...
2026-11-24 09:10:00 INFO  ... TASK_END executionId=42 exitCode=1 endedAt=...
~~~

The unhandled error propagates out of the runner, so the lifecycle failure path invokes **`onTaskFailed` and then `onTaskEnd`**. The exact exit code and error formatting depend on Spring Boot version and configuration; `exitCode=1` in the log is an **illustrative result**, not a universal constant.

The prefixes `TASK_START`, `TASK_FAILED`, `TASK_END`, and `IMPORT_BEGIN` are **written by our example code**; they are not fixed log strings emitted by Spring Cloud Task across every project.

### Why Inspect `TaskRepository` as Well?

With the default schema, you can query:

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME,
    EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Then correlate by the execution ID from the logs:

~~~sql
SELECT TASK_EXECUTION_ID, EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 42;
~~~

For the failed run, `EXIT_MESSAGE` may contain `FAILED: IllegalStateException` set by the listener; `ERROR_MESSAGE` recorded by the framework may contain additional exception details. **Only after the lifecycle finishes and the metadata transaction commits** can an external reader observe the full final state. If you query immediately inside `onTaskEnd`, the repository may **not yet contain the final data**, because the callback runs before the completion update.

## 6. Another Option: `@BeforeTask`, `@AfterTask`, and `@FailedTask` Annotations

Instead of implementing the interface, Spring Cloud Task supports annotating methods on a bean:

| Interface Callback | Corresponding Annotation |
| --- | --- |
| `onTaskStartup(TaskExecution)` | `@BeforeTask` |
| `onTaskEnd(TaskExecution)` | `@AfterTask` |
| `onTaskFailed(TaskExecution, Throwable)` | `@FailedTask` |

Example:

~~~java
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedTaskAudit {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("Starting execution " + execution.getExecutionId());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable error) {
        System.err.println(
                "Failed execution " + execution.getExecutionId()
                + ": " + error.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("Ending execution " + execution.getExecutionId());
    }
}
~~~

In production applications, prefer a logger over `System.out` and `System.err`; the snippet above is kept brief to highlight the mapping between annotations and callbacks. Both mechanisms **hook into the Spring Cloud Task lifecycle**, so avoid registering the same logic under both forms and accidentally emitting logs/metrics twice.

**Do not confuse `@AfterTask` with `@PreDestroy`.** `@AfterTask` is a task execution lifecycle callback invoked before the repository updates the final status; `@PreDestroy` is a bean cleanup callback when the `ApplicationContext` closes, which can occur at a different time.

## 7. Exit Message: Precedence Rules When Multiple Callbacks Set It

`TaskExecution.setExitMessage(...)` is a Spring Cloud Task-supported way to supplement outcome details. According to the framework documentation, if multiple callbacks set an exit message, the precedence order is:

1. **`onTaskEnd`** has the highest precedence.
2. Followed by **`onTaskFailed`**.
3. Finally **`onTaskStartup`**.

Example of a failing task:

~~~java
@Override
public void onTaskStartup(TaskExecution task) {
    task.setExitMessage("STARTED");
}

@Override
public void onTaskFailed(TaskExecution task, Throwable error) {
    task.setExitMessage("FAILED");
}

@Override
public void onTaskEnd(TaskExecution task) {
    task.setExitMessage("DONE");
}
~~~

When all three callbacks run, the final persisted message can be **`DONE`**, misleading readers even though the task failed. Therefore, you **should not** unconditionally set `DONE` in `onTaskEnd`. Two safer options exist: only set a success message if the exit code indicates success and no failure message is already set, or use neutral messages that will not cause operators to draw the wrong conclusion.

The exit message is purely **descriptive metadata**. It does not change whether business data was committed successfully. If you need to control exit codes or error mapping, follow Spring Boot/Spring Cloud Task's exit code mechanism and test on your target version.

## 8. What Happens If a Listener Itself Throws an Exception?

**A listener is part of the task lifecycle.** An exception from a listener can cause the application to fail or affect final status recording. According to Spring Cloud Task documentation:

- When a listener handler throws an exception, execution of other listeners for **the same callback type** stops at that point.
- Other callback phases still attempt to run along the corresponding lifecycle path; ordering and completion depend on initialization state.
- An error in `onTaskStartup` typically causes the task to record a failure exit code (`1` in the default scenario).
- For errors in `onTaskEnd` or `onTaskFailed`, the exit code follows the exit code calculation mechanism determined by the framework and failure event; do not expect an `ExitCodeExceptionMapper` to always fix the exit code when a listener fails.

Error-prone example to avoid:

~~~java
@Override
public void onTaskEnd(TaskExecution task) {
    notificationClient.sendBlocking(task.getExecutionId());
    // If the notification service fails, the listener may throw an exception,
    // further complicating the status of an already completed task.
}
~~~

If notification is a **mandatory business side effect**, place it in a runner or workflow with explicit retry, timeout, and idempotency policies; then failures properly govern task completion. If it is solely for **observability**, the listener should execute quickly and avoid depending on an unreliable external service.

A metrics-collecting listener can handle its own metric emission errors and log a controlled warning; however, unconditionally swallowing all exceptions is also inappropriate if metrics are a strict audit obligation. Draw a clear boundary between **observability side effects permitted to fail** and **mandatory business success conditions**.

## 9. Edge Cases Requiring Special Attention

### 9.1. Exceptions Caught and Ignored

If a runner catches an exception and **does not rethrow it**:

~~~java
try {
    importData();
} catch (Exception ex) {
    log.error("Import failed", ex);
    // Neither rethrows nor marks the result as failed.
}
~~~

Spring Boot may treat the runner as having completed normally, so **`onTaskFailed` will not necessarily be called**. `onTaskEnd` may still run and the repository may record a successful status. When the business requirement is "fail if incomplete data is imported," propagate the error signal properly (e.g., rethrow the exception or use an appropriate exit code mechanism).

### 9.2. Runner Starts Async Work and Returns

~~~java
@Bean
ApplicationRunner riskyRunner(ImportService service) {
    return args -> service.startAsync();
}
~~~

If `startAsync()` launches background work and returns immediately, the lifecycle can end before data processing finishes. Then `onTaskEnd` reports completion early, even if the background job later fails. For finite tasks, **wait for the real result** before the runner returns, or split the work into two separate processes with independent state tracking.

For example, if the API returns a `CompletableFuture` representing the entire job:

~~~java
@Bean
ApplicationRunner awaitedRunner(ImportService service) {
    return args -> service.startAsync().join();
}
~~~

Production runs still need timeouts and cancellation/recovery policies. A bare `join()` is insufficient if the future does not represent the entire workload.

### 9.3. Process Killed or Initialization Fails Too Early

When a process receives `SIGKILL`, gets OOM-killed, or fails before the lifecycle is established, **not all callbacks may run** or no completion metadata record may exist. Do not rely on `onTaskEnd` as the sole mechanism to release business locks, issue refunds, or guarantee a "finished" event.

Operational design requires timeouts, heartbeats or pod/process monitoring, inspecting actual data state, and a cleanup procedure for records whose `END_TIME` remains empty.

### 9.4. Multiple Listeners in the Same Application

The framework can pick up multiple `TaskExecutionListener` beans and annotated methods. If one handler throws an exception, other handlers in the same phase may not run. Therefore:

- Avoid scattering mandatory business conditions across multiple listeners with implicit ordering dependencies.
- Keep each listener focused on a clear responsibility and avoid overwriting another listener's message carelessly.
- If strict order is required, verify ordering conventions and behavior in your exact version; even better, design multiple listeners to be order-independent.
- Logs must include the execution ID, not just the task name, because multiple processes can run concurrently.

### 9.5. Spring Batch Inside Spring Cloud Task

When a task launches **Spring Batch**, separate the two lifecycles:

- `TaskExecutionListener` reflects **the task application run**.
- Spring Batch's `JobExecutionListener` and `StepExecutionListener` reflect **the job or step**.

An asynchronously launched Batch job may still be running when the task's runner returns. In that situation, Spring Cloud Task's `onTaskEnd` does not prove the Batch job succeeded. Wait for the job result or manage job state independently via `JobRepository`/`JobExplorer`.

## 10. Decision Matrix: Which Callback to Use?

| Need | Suitable Callback | Reason |
| --- | --- | --- |
| Attach execution ID to initial run logs | `onTaskStartup` | Has the `TaskExecution` object identifying the run |
| Record every run that reaches the termination phase | `onTaskEnd` | Covers both success paths and many failure paths |
| Log stack trace when runner throws an unhandled exception | `onTaskFailed` | Provides the original `Throwable` for root-cause analysis |
| Record a concise failure exit message | `onTaskFailed` | Preserves the failure cause in the message |
| Record a success message | `onTaskEnd`, **conditionally** | Avoids overwriting messages from the failed phase |
| Release bean resources when Spring context shuts down | `@PreDestroy` or lifecycle bean | This is context-shutdown responsibility, distinct from task callbacks |
| Execute critical business transactions | **Runner/business service** | Ensures failures affect task outcome and trigger proper retries |
| Track Spring Batch chunks or steps | **Batch listeners** | Observes at the right job/step granularity |

## 11. Self-Verification Lab

Using the Java code presented above, perform the following in a learning environment:

1. Configure a `TaskRepository` backed by a persistent database and verify the `TASK_EXECUTION` table exists.
2. Run **successfully** with `--businessDate=2026-11-23`; note the execution ID.
3. Locate the three events in the logs: `TASK_START`, `IMPORT_DONE`, and `TASK_END`; `TASK_FAILED` should not appear.
4. Run a **failure** case with `--fail`; confirm the sequence `TASK_START → TASK_FAILED → TASK_END` and that the original exception appears in the logs.
5. Query both execution IDs in `TASK_EXECUTION`; compare `EXIT_CODE`, `EXIT_MESSAGE`, `ERROR_MESSAGE`, and `END_TIME`.
6. Temporarily set an unconditional `exitMessage` in `onTaskEnd` **in a test environment only**; observe how error details can be hidden, then restore the safe conditional check.
7. Try having the runner catch and ignore an exception; observe that the failed callback may not run. Restore proper error propagation.
8. If testing multiple listeners, isolate the test from real business logic and observe behavior when one callback throws an exception.

**Completion Checklist:**

- [ ] Confirmed the listener is registered by Spring and receives the right `TaskExecution`.
- [ ] Startup/end/failed logs include the run's execution ID.
- [ ] Never treat `onTaskEnd` as proof of success without checking the exit code.
- [ ] On failure, `onTaskFailed` runs before `onTaskEnd` along the normal lifecycle path.
- [ ] Failure exit messages are not overwritten by the end callback.
- [ ] Results read from `TaskRepository` are checked **after the update has committed**.
- [ ] Listeners perform no long blocking work and store no secrets in logs/messages.
- [ ] Separate operational handling exists for abruptly killed processes and re-runs with identical parameters.

## 12. Key Takeaways

The three methods `onTaskStartup`, `onTaskFailed`, and `onTaskEnd` extend the **Spring Cloud Task** lifecycle for each execution. The most important sequence is **startup → end** on normal completion and **startup → failed → end** when an unhandled error is captured by the framework.

Use listeners for observability, lightweight auditing, and supplementary metadata; leave business processing to runners/services, metadata persistence to `TaskRepository`, history queries to `TaskExplorer`, and run timing to schedulers. With Spring Batch, use Batch listeners to observe jobs and steps. This separation lets you track task status and outcomes in the database while keeping error codes, messages, and recovery mechanisms clear.

### References

- [Spring Cloud Task — Task Execution Listener (Features)](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/features.html)
- [TaskExecutionListener — Javadoc 3.0.4](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
- [TaskLifecycleListener — source code](https://github.com/spring-cloud/spring-cloud-task/blob/main/spring-cloud-task-core/src/main/java/org/springframework/cloud/task/listener/TaskLifecycleListener.java)
