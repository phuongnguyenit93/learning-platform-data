# `@BeforeTask`, `@AfterTask`, and `@FailedTask`

## 1. Lesson Objectives

A **Spring Cloud Task** application performs work with a finite runtime: importing data, synchronizing information, exporting a report, or processing a request, and then exiting. Beyond business logic, the application typically needs logging, duration measurement, outcome descriptions, and error reporting for safe operations.

Spring Cloud Task provides **execution lifecycle listeners** to place those hooks at the exact right moments. There are two ways to register a listener: implementing the `TaskExecutionListener` interface or using annotations on methods of a Spring bean:

- **`@BeforeTask`**: runs when the task starts, before persisting start metadata to `TaskRepository`.
- **`@AfterTask`**: runs when the task completes, before updating the final status in `TaskRepository`.
- **`@FailedTask`**: runs when the task raises an unhandled exception, before `@AfterTask` callbacks are invoked.

This lesson belongs to the **Listener** section of the `SPRING_CLOUD_TASK` module and focuses on these three annotations, how to use `TaskExecution` and `Throwable`, proper error handling, and observing results through the database.

After this lesson, you will be able to write your own listeners to capture lifecycle events, distinguish callbacks for successful vs. failed runs, set appropriate `exitMessage` values, prevent listeners from distorting business outcomes, and integrate monitoring when tasks run on a schedule or on demand.

## 2. Where Do Listeners Sit in the Spring Cloud Task Lifecycle?

**`TaskExecution`** represents **a single execution** of a Spring Cloud Task application. **`TaskRepository`** persists that information, typically including ID, task name, start time, end time, exit code, error details, and arguments. Each run of the JAR gets its own `TaskExecution`, even under the same task name.

Spring Cloud Task initializes tracking before `ApplicationRunner` and `CommandLineRunner` beans execute. Listener annotations are triggered along this lifecycle:

| Annotation | Corresponding `TaskExecutionListener` Method | When Is It Called? | Parameters |
| --- | --- | --- | --- |
| `@BeforeTask` | `onTaskStartup(TaskExecution)` | Before persisting the initial `TaskExecution` to the repository | `TaskExecution` |
| `@FailedTask` | `onTaskFailed(TaskExecution, Throwable)` | When an unhandled error occurs; before the end callback | `TaskExecution`, `Throwable` |
| `@AfterTask` | `onTaskEnd(TaskExecution)` | Before updating the final `TaskExecution` state in the repository | `TaskExecution` |

Two common flows:

```mermaid
flowchart TD
    A[Spring Boot initializes application] --> B[@BeforeTask]
    B --> C[TaskRepository saves initial record]
    C --> D[ApplicationRunner / CommandLineRunner runs]
    D --> E{How does the work finish?}
    E -->|Success| G[@AfterTask]
    E -->|Unhandled exception| F[@FailedTask]
    F --> G
    G --> H[TaskRepository updates final status]
    H --> I[TaskExecution lifecycle completes]
```

A crucial point to remember: **`@AfterTask` does not mean "success."** It is a completion callback, so it can also run after the `@FailedTask` branch. To handle errors specifically, use `@FailedTask`. If you need the official outcome after the repository update, query the record **after the task has finished**—do not assume the final data is already written while `@AfterTask` is executing.

These are listeners for the **task application lifecycle**, not per-SQL-statement, per-thread, or per-Spring-Batch-step listeners. When combined with Spring Batch, `TaskExecutionListener` tracks the Spring Cloud Task run, whereas Spring Batch listeners track jobs/steps within their own scope.

## 3. Declaring Annotations and Method Signatures

The three annotations reside in this package:

```java
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
```

Callback parameter type:

```java
import org.springframework.cloud.task.repository.TaskExecution;
```

A Spring bean containing the three methods can be declared as follows:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("[BEFORE] task=" + execution.getTaskName());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable throwable) {
        System.err.println("[FAILED] task=" + execution.getTaskName()
                + ", errorType=" + throwable.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("[AFTER] task=" + execution.getTaskName());
    }
}
```

**Why `@Component`?** A listener must belong to a **Spring-managed bean** discovered by the application; you cannot simply instantiate `new AuditTaskListener()` and expect the framework to invoke its methods automatically. The annotations apply to **methods**, not the class as a whole.

The `@FailedTask` signature takes an additional `Throwable` to receive the failure cause. `@BeforeTask` and `@AfterTask` methods take `TaskExecution`. All three methods return `void`, fitting their role as lifecycle event handlers.

## 4. Building a Complete Sample Application

The following example builds a task running a simulated data-import step that can either succeed or intentionally throw an exception. The listener prints messages at each milestone and sets an `exitMessage` on failure.

The example uses **JDK 17**, **Spring Boot 3.4.5**, **Spring Cloud 2024.0.2**, and file-based H2. These are matching-generation versions for learning purposes; if you use another version, choose the Spring Cloud release train compatible with your Spring Boot version.

### 4.1. Project Structure

```text
task-listener-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/tasklistener/
    │   ├── TaskListenerApplication.java
    │   ├── ImportRunner.java
    │   └── AuditTaskListener.java
    └── resources/
        └── application.yml
```

### 4.2. Configuring `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>task-listener-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2024.0.2</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-task</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-cloud-starter-task` provides the Task infrastructure and listener annotations; `spring-boot-starter-jdbc` connects metadata to the database; H2 lets you observe the history across multiple runs.

### 4.3. Configuring the DataSource and Task

Create `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: task-listener-demo
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./data/listenerdb;DB_CLOSE_ON_EXIT=FALSE
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: task-listener-demo
      initialize-enabled: true
      closecontext-enabled: true
```

`web-application-type: none` disables the web server because this is a finite application. File-based H2 retains metadata after the process terminates; the `./data/listenerdb` path is resolved from the directory where the command is run. `initialize-enabled: true` is convenient for creating demo tables. For production environments, use a durable database, manage schemas with migrations, and set `initialize-enabled` to `false`.

### 4.4. Spring Boot Application Class

Create `TaskListenerApplication.java`:

```java
package com.example.tasklistener;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class TaskListenerApplication {

    public static void main(String[] args) {
        SpringApplication.run(TaskListenerApplication.class, args);
    }
}
```

### 4.5. Runner Executing the Finite Workload

Create `ImportRunner.java`:

```java
package com.example.tasklistener;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        System.out.println("[RUN] Starting data import");

        try {
            Thread.sleep(500);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        }

        if (args.containsOption("fail")) {
            throw new IllegalStateException("Simulated data import failure");
        }

        System.out.println("[RUN] Data import completed");
    }
}
```

Normally, the runner finishes after completing its business logic. In the failure example, the exception is not caught and swallowed, allowing Spring Boot to report runner failure and Spring Cloud Task to record an unsuccessful execution.

**Key point:** A listener only *observes the lifecycle*. It cannot automatically tell that a business operation failed if the runner catches every error and returns normally.

### 4.6. Listener with the Three Annotations

Create `AuditTaskListener.java`:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("[BEFORE] " + execution.getTaskName());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable cause) {
        System.err.println("[FAILED] " + execution.getTaskName()
                + " - " + cause.getClass().getSimpleName());

        // Concise message, containing no secrets or stack trace.
        execution.setExitMessage(
                "Import failed: " + cause.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("[AFTER] " + execution.getTaskName());

        // Do not overwrite exitMessage here: preserve the error message
        // set by @FailedTask if the run failed.
    }
}
```

This listener records only essential details and sets a concise `exitMessage` on failure. Remember that `@AfterTask` runs **before** the repository is updated with the final state, so do not write code assuming `getEndTime()` or `getExitCode()` at callback time already reflects the final database record.

## 5. Running and Observing the Callback Order

In the project directory, create the data directory and package the application:

```bash
mkdir -p data
mvn clean package
```

On PowerShell, you can create the directory with `New-Item -ItemType Directory -Force data`.

### 5.1. Successful Run

```bash
java -jar target/task-listener-demo-0.0.1-SNAPSHOT.jar
```

Log lines emitted by the example along the success flow:

```text
[BEFORE] task-listener-demo
[RUN] Starting data import
[RUN] Data import completed
[AFTER] task-listener-demo
```

Standard Spring Boot logs may appear interleaved. `@FailedTask` is **not** called on this branch because no unhandled error occurred.

### 5.2. Failed Run

```bash
java -jar target/task-listener-demo-0.0.1-SNAPSHOT.jar --fail
```

Business and listener log lines to observe:

```text
[BEFORE] task-listener-demo
[RUN] Starting data import
[FAILED] task-listener-demo - IllegalStateException
[AFTER] task-listener-demo
```

In practice, Spring Boot will also log the error stack trace and the process may return a non-zero exit code. Line ordering between `stdout` and `stderr` might not strictly match callback order when a terminal or log collector merges both streams; to verify order accurately, use the same logger across callbacks.

`@FailedTask` is called due to the **unhandled exception** and runs before `@AfterTask`. Consequently, `Import failed: IllegalStateException` can be persisted into the execution's final metadata.

### 5.3. Verifying Results via `TaskRepository`

After the JAR exits, use the H2 console or a JDBC client to connect to the same database at `jdbc:h2:file:./data/listenerdb`, user `sa`, empty password. If opening a SQL client from a different directory, use the absolute file path to avoid connecting to the wrong H2 database.

```sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
```

Expected meaningful results:

| Run | Callbacks Triggered | Fields Verified |
| --- | --- | --- |
| Success | `@BeforeTask` → `@AfterTask` | Success exit code, end timestamp populated. |
| Failure with `--fail` | `@BeforeTask` → `@FailedTask` → `@AfterTask` | Error exit code, `ERROR_MESSAGE` populated; `EXIT_MESSAGE` contains the listener's message. |

`EXIT_MESSAGE` is a summary message actively set by the application or listener. `ERROR_MESSAGE` typically holds exception information captured by Spring Cloud Task. `EXIT_CODE` indicates the termination status. These three fields serve different purposes; never substitute seeing a message string for checking the exit code.

## 6. Setting `exitMessage` and Override Rules

Spring Cloud Task allows calling `TaskExecution.setExitMessage(String)` inside listener events. This is an appropriate place to add an operator-friendly summary, such as processed record count or a business error code.

```java
@AfterTask
public void after(TaskExecution execution) {
    execution.setExitMessage("Processing finished");
}
```

The snippet above is valid per the API, but **should not be used verbatim if you already set an error message in `@FailedTask`**: the end callback runs after the failure callback, so `"Processing finished"` can overwrite helpful failure details.

Spring Cloud Task documentation defines the precedence order among listeners when multiple modify `exitMessage`:

| Precedence | Callback | Meaning |
| --- | --- | --- |
| Highest | `@AfterTask` / `onTaskEnd` | A value set here can override values from earlier phases. |
| Medium | `@FailedTask` / `onTaskFailed` | Can override a message set at startup when an error occurs. |
| Lowest | `@BeforeTask` / `onTaskStartup` | The initial message is retained only if later callbacks do not alter it. |

Practical example: `@FailedTask` sets `"IMPORT_FAILED"`, and if `@AfterTask` leaves `exitMessage` untouched, the error message is preserved. If `@AfterTask` unconditionally sets `"DONE"`, it can accidentally hide the error information.

**Never use `exitMessage` to alter success/failure logic.** To ensure the orchestrator knows about an error, let the business exception propagate properly or use Spring Boot's exit code mechanism. A `"FAILED"` note in metadata does not necessarily make `EXIT_CODE` non-zero.

Never store passwords, tokens, personal data, or full stack traces in `exitMessage`. Task metadata may be read by multiple operational tools over a long period.

## 7. Handling Exceptions Inside Listeners

Listeners participate in the lifecycle management flow; they can also cause failures if they call external APIs, connect to monitoring systems, or execute code that throws exceptions.

Spring Cloud Task documentation notes that when a listener throws an exception, **the remaining listeners for that same event may not be invoked**. Exit code calculation also depends on the event and how the framework resolves exceptions. Specifically, an error in `onTaskStartup` can cause the task to terminate with exit code `1`; exceptions in `onTaskEnd` or `onTaskFailed` follow different exit code rules, and `ExitCodeExceptionMapper` is not a reliable way to override the exit code caused by a listener error itself.

Therefore, keep listeners **short, stable, and resource-bounded**:

1. Log and emit only essential metrics; avoid long-running work or critical business processing directly inside callbacks.
2. When sending metrics or audits to an external service, configure explicit timeouts so task shutdown cannot hang.
3. If a metrics system failure **should not** change the business outcome, catch the exception locally, log a safe warning, and continue.
4. If an action is a mandatory condition for considering the job complete, place it in a **runner or business service** where errors can be handled and propagated transparently.
5. Avoid letting `@AfterTask` clear or overwrite a business failure's `exitMessage`.

Example of logging with auxiliary error handling:

```java
@AfterTask
public void after(TaskExecution execution) {
    try {
        monitoringService.recordTaskFinished(execution.getTaskName());
    } catch (RuntimeException monitoringError) {
        // Warn only, because a metrics system failure is not a data import failure.
        System.err.println("Failed to send completion metric: "
                + monitoringError.getClass().getSimpleName());
    }
}
```

`monitoringService` is a hypothetical service injected into the Spring bean; this snippet only illustrates the auxiliary error-handling principle and is not complete code meant to replace `AuditTaskListener` directly.

**Special case:** If the application is forcibly killed, the host loses power, or the JVM fails to finish the Spring lifecycle, there is no guarantee `@FailedTask` or `@AfterTask` will run. Production operations must combine `TaskRepository`, process status, scheduler state, and logs rather than relying solely on listeners.

## 8. Annotation Listeners vs. Implementing the Interface

The three annotations offer convenient syntax when you only need to attach behavior to a few methods on a Spring bean. For a shared listener, you can implement the `TaskExecutionListener` interface:

```java
package com.example.tasklistener;

import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class InterfaceTaskListener implements TaskExecutionListener {

    @Override
    public void onTaskStartup(TaskExecution execution) {
        System.out.println("Startup: " + execution.getTaskName());
    }

    @Override
    public void onTaskFailed(TaskExecution execution, Throwable cause) {
        System.err.println("Failed: " + cause.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        System.out.println("End: " + execution.getTaskName());
    }
}
```

This is an **alternative approach**—do not register it alongside the example `AuditTaskListener` if you only want each event logged once. Both approaches rely on the exact same lifecycle points.

| Criterion | Annotations on a Bean | Implementing `TaskExecutionListener` |
| --- | --- | --- |
| Declaration | `@BeforeTask`, `@FailedTask`, `@AfterTask` on methods | Override the three interface methods |
| When appropriate | Bean only needs one or a few callbacks | Dedicated class responsible for the full task lifecycle |
| Parameters | `TaskExecution`, plus `Throwable` for failure | Defined by the interface signatures |
| Registration | Spring bean scanned for annotations | Spring bean implementing the interface |
| Business impact | Should be limited to monitoring, audit, outcome messages | Should follow the exact same principle |

## 9. Listeners in Asynchronous Processing and Spring Batch

### 9.1. Asynchronous Work

If an `ApplicationRunner` calls `CompletableFuture.runAsync(...)` and **returns immediately**, Spring Cloud Task may complete its lifecycle while worker threads are still running. In that case, `@AfterTask` can fire **before subtasks complete**, causing logs and metadata to misrepresent the business outcome.

To ensure reliable task status:

- The runner must wait for all mandatory subtasks to finish, for example with `CompletableFuture.allOf(...).get(...)` or `Future.get()`.
- Handle timeouts, cancel remaining work when appropriate, and **propagate errors** from workers back to the runner.
- Listeners should only run observational logic after the runner has ensured completion; never use listeners as a place to "wait for left-behind futures."

### 9.2. When a Task Runs a Spring Batch Job

An application can combine **Spring Cloud Task** and **Spring Batch**:

| Level | Data and Listeners |
| --- | --- |
| Whole application | `TaskExecution` in `TaskRepository`, along with Spring Cloud Task listeners |
| Data-processing job | `JobExecution`, `JobRepository`, and Spring Batch's `JobExecutionListener` |
| Specific processing step | `StepExecution`, `StepExecutionListener`, and Spring Batch read/process/write listeners |

`@BeforeTask` and `@AfterTask` do not replace `beforeJob` or `afterStep`. If `JobLauncher` runs asynchronously, the runner must wait until the job genuinely finishes if `TaskExecution` is meant to span the Batch outcome. When a Batch job fails, do not assume the error automatically triggers the application's `@FailedTask` callback: that depends on how the launcher, runner, and business code translate Batch status into an exception or exit code.

## 10. Safe Operations and Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `@BeforeTask` is never called | Class is not a Spring bean, wrong scan package, or Task not configured | Verify `@Component`, component scan package, `@EnableTask`, and dependencies. |
| `@FailedTask` does not run despite error logs | Runner caught the exception and returned normally | Let critical errors propagate or manage exit codes appropriately. |
| `@AfterTask` appears on failed runs | It is an **end** callback, not a success-only callback | Move error logic to `@FailedTask`; do not equate `After` with `Success`. |
| Error message disappears from `EXIT_MESSAGE` | `@AfterTask` overwrote the message set by `@FailedTask` | Only set an end message when truly needed, preserving existing error messages. |
| End metadata not visible in DB inside `@AfterTask` | Callback runs before the repository updates final status | Query after the task finishes. |
| Metrics listener causes the task to hang | Calling an external service without a timeout | Keep operations brief with timeouts and explicit auxiliary error policies. |
| No `@FailedTask` when pod is killed | Process did not go through normal Spring lifecycle | Combine container monitoring, scheduler status, logs, and DB checks. |
| Single event logged twice | Two listeners registered doing the same work | Check bean count and separate responsibilities across listeners. |
| Task reports success even though a worker failed | Runner did not await or inspect errors from a future | Wait for subtasks and propagate errors before returning. |

For scheduled tasks via `cron`, Kubernetes `Job`/`CronJob`, or an orchestrator, listeners add structured logs and traceable metadata. However, Spring Cloud Task **does not schedule runs itself**; it only tracks a single application run. Persist `TaskExecution` in a durable database, configure sensible timeouts, and implement retry/idempotency policies in business logic.

To correlate logs across runs, use the `TaskExecution` ID once assigned and stable. In `@BeforeTask`, the framework is **before saving the start record**, so do not assume the ID or final metadata fields are already populated. When running multiple instances, avoid using static fields to accumulate lifecycle state across runs.

## 11. Self-Check and Practice

### Exercise 1: Observe Both Lifecycle Branches

1. Run the example with no arguments and note the sequence `BEFORE → RUN → AFTER`.
2. Run again with `--fail` and confirm `FAILED` appears before `AFTER`.
3. Query `TASK_EXECUTION` and compare `EXIT_CODE`, `EXIT_MESSAGE`, and `ERROR_MESSAGE` between the two runs.

### Exercise 2: Control the Exit Message

Add `execution.setExitMessage("DONE")` inside `@AfterTask` and run with `--fail`. Observe how the error message set by `@FailedTask` is affected. Then fix it so the error message is preserved.

### Exercise 3: Design a Production-Ready Listener

Suppose an order-import task needs duration metrics, failure notifications, and persistence of the succeeded record count. Clearly divide which work belongs in the runner/business service vs. callbacks, what belongs in `exitMessage`, and how to handle failures in the external monitoring service.

### Review Questions

1. Does `@BeforeTask` run before or after the initial `TaskExecution` is saved to the repository?
2. Why does `@AfterTask` not mean the task succeeded?
3. How does `@FailedTask`'s signature differ from `@BeforeTask` and `@AfterTask`?
4. What happens if a runner catches an error without rethrowing it?
5. Why can `@AfterTask` erase an `exitMessage` set in `@FailedTask`?
6. Why should long or untimed I/O operations be avoided inside listeners?
7. When combining with Spring Batch, why doesn't `@AfterTask` replace `JobExecutionListener`?

**Key takeaway:** `@BeforeTask` observes startup, `@FailedTask` receives unhandled errors, and `@AfterTask` observes completion **regardless of success or failure**. Use listeners for monitoring and execution messages, while keeping business logic and success/failure decisions explicit in the task's execution flow.

## References

- [Spring Cloud Task 3.2 — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/3.2/features.html): callback points, exception handling in listeners, and `exitMessage` precedence.
- [Spring Cloud Task — `FailedTask` Annotation API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/annotation/FailedTask.html): syntax and callback signature accepting `TaskExecution` and `Throwable`.
