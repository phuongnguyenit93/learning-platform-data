# Closing the Context with `spring.cloud.task.closecontextEnabled`

## 1. Why Does an Application Still Keep Running After a Task Finishes?

**Spring Cloud Task** serves Spring Boot applications with a **finite lifecycle**: they start up, perform a job, save execution metadata via **TaskRepository**, and exit. Typical examples are file-based data ingestion, end-of-day order reconciliation, or on-demand report generation.

However, **task completion** and **application shutdown** are two distinct events:

- **Work completed:** all `ApplicationRunner` and `CommandLineRunner` beans invoked by Spring Boot have finished; Spring Cloud Task can update the execution outcome in `TaskRepository`.
- **`ApplicationContext` closed:** Spring releases beans, publishes context-close events, and invokes appropriate resource-cleanup callbacks.
- **JVM process exited:** the operating system receives the exit code; this also depends on lingering threads and how the application manages its process.

In a simple task, the JVM can exit on its own once runners finish and no non-daemon threads keep the process alive. Yet in an application with executors, connections, or background services, you may see task metadata already updated while the process **keeps running**.

The **`spring.cloud.task.closecontextEnabled`** property allows Spring Cloud Task to **actively close the `ApplicationContext` when the task finishes**, keeping lifecycle management aligned with a short-lived application model. This is the focus of this lesson in the **Lifecycle** chapter.

### Lesson Objectives

After this lesson, you will be able to:

1. Explain the meaning of `spring.cloud.task.closecontextEnabled` and its default value.
2. Enable context closing via YAML, properties, or launch arguments.
3. Distinguish **`TaskExecution` completion**, **context closure**, and **JVM exit**.
4. Observe bean destruction callbacks, logs, and records in `TaskRepository`.
5. Recognize risks when work runs asynchronously, integrates Spring Batch, or leaves background threads alive.
6. Troubleshoot cases where a task completes yet the process does not terminate.

## 2. How Does the `closecontextEnabled` Property Work?

According to Spring Cloud Task documentation, when `spring.cloud.task.closecontextEnabled=true` is enabled, the framework closes the Spring `ApplicationContext` **after runners finish and task metadata is updated in `TaskRepository`**. The default value of this property in current versions is **`false`**.

| Configuration | Expected Behavior | When to Use? |
| --- | --- | --- |
| Unset or `false` | Spring Cloud Task does not **proactively** close the context right after task completion via this feature. The context may still close via shutdown hooks or application code. | Application manages its own lifecycle; need to find why a process stays alive before enabling it. |
| `true` | Spring Cloud Task requests closing the context once the execution lifecycle has finished; Spring-managed resource cleanup mechanisms get a chance to run. | Finite-running application that should close its context when runners finish and needs no persistent background activity. |

**Keep in mind:** `closecontextEnabled=false` does not mean the JVM runs forever. If no non-daemon threads remain, the JVM can exit and Spring Boot can still close the context via a shutdown hook. Conversely, `true` is **not a command forcing the JVM to exit**, does not replace `System.exit(...)`, and does not safely terminate arbitrary threads created manually by the application.

### Property Naming Forms

Spring Cloud Task documentation uses camelCase:

`spring.cloud.task.closecontextEnabled`

Spring Boot supports flexible property binding (*relaxed binding*). In YAML files, using standard kebab-case is recommended for readability:

~~~yaml
spring:
  cloud:
    task:
      closecontext-enabled: true
~~~

Both representations target the same configuration option when bound properly by Spring Boot. You can also enable it via command-line arguments:

~~~bash
java -jar demo-task.jar --spring.cloud.task.closecontextEnabled=true
~~~

Or in `application.properties`:

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

When deploying, verify that the Spring Cloud Task version is compatible with Spring Boot and that the configuration file is actually loaded by the active profile. Never assume a YAML file takes effect merely because it exists in the project directory.

## 3. Execution Order in the Task Lifecycle

The typical flow of a successful run can be visualized as follows:

~~~mermaid
sequenceDiagram
    participant P as Spring Boot Process
    participant C as ApplicationContext
    participant R as ApplicationRunner/CommandLineRunner
    participant T as Spring Cloud Task
    participant DB as TaskRepository/Database
    P->>C: Create and initialize context
    T->>DB: Record TaskExecution start
    C->>R: Invoke runners
    R->>R: Execute finite business logic
    R-->>C: Runners finish
    T->>DB: Update TaskExecution end
    alt closecontextEnabled = true
        T->>C: Request closing ApplicationContext
        C->>C: Stop beans, close managed resources
    else closecontextEnabled = false
        Note over C: Not proactively closed by this property
    end
    Note over P: JVM exits only when process termination conditions are met
~~~

Several important details:

- `TaskRepository` can create the execution record before invoking `ApplicationRunner` / `CommandLineRunner`, once the context has initialized successfully.
- Spring Cloud Task updates completion details after runners finish or when an error is captured by the framework.
- Enabling `closecontextEnabled` targets the **context closing** step once the task finishes; it does not determine business outcomes or rerun the task itself.
- Exact log line ordering from listeners depends on versions, threads, and logging configuration. Do not rely solely on a few log lines to conclude every resource closed cleanly.

If `ApplicationContext` initialization fails very early, Spring Cloud Task may **not have created a `TaskExecution` yet**. If the JVM is forcefully killed, context-closing callbacks may also fail to run completely.

## 4. Example: Enabling Automatic Context Closing for a Task

The example below assumes a compatible Spring Cloud Task dependency has been added along with a `DataSource` and matching metadata schema. We build a daily report generation job, with simplified business logic to focus on lifecycle observation.

### 4.1. `application.yml`

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-report-task
      closecontext-enabled: true

logging:
  level:
    root: INFO
~~~

`web-application-type: none` avoids starting an unnecessary HTTP server for a CLI-style task. It **does not automatically shut down executors or background threads**. For durable execution state tracking, configure a `DataSource` and prepare the corresponding `TaskRepository` schema; the abbreviated snippet above omits database passwords and URLs.

### 4.2. Spring Boot Application

~~~java
import java.time.LocalDate;
import java.util.List;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyReportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner() {
        return args -> {
            List<String> values = args.getOptionValues("reportDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Must pass --reportDate=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(values.get(0));
            log.info("REPORT_START reportDate={}", date);

            // TODO: Replace with synchronous business processing.
            log.info("REPORT_DONE reportDate={}", date);
        };
    }

    @PreDestroy
    public void onBeanDestroy() {
        log.info("SPRING_BEAN_DESTROY: preparing to release resources");
    }
}
~~~

**Example explanation:**

- `@EnableTask` enables Spring Cloud Task integration in the sample application.
- `ApplicationRunner` runs finite business work and **returns only after synchronous work is finished**.
- `@PreDestroy` sits on a Spring-managed bean, serving as a useful signal to observe Spring closing the context.
- `main` **does not call `System.exit(...)` or `SpringApplication.exit(...)`**, letting you observe the behavior of `closecontextEnabled` on its own.
- The `SPRING_BEAN_DESTROY` line shows the bean destruction callback running during context shutdown; it **does not by itself prove the JVM has exited** or that all external systems finished work.

The example uses `jakarta.annotation.PreDestroy`, suitable for modern Spring Boot generations. Projects on older generations may have different annotation packages and dependencies.

### 4.3. Running and Reading Logs

~~~bash
java -jar daily-report-task.jar --reportDate=2026-11-23
~~~

The following is only an **illustrative log** to identify milestones; timestamps, logger names, and internal lines may vary:

~~~text
INFO  ... Starting DailyReportTaskApplication
INFO  ... REPORT_START reportDate=2026-11-23
INFO  ... REPORT_DONE reportDate=2026-11-23
INFO  ... SPRING_BEAN_DESTROY: preparing to release resources
~~~

What you need to verify is that **business work finishes before bean resources are destroyed**. The `SPRING_BEAN_DESTROY` log reflects only a cleanup hook; if the work-completion log is missing, check whether the runner threw an error or returned too early.

In an application with no remaining background threads, both `true` and `false` configurations can still terminate the process and trigger `@PreDestroy` via different shutdown mechanisms. Hence, **merely seeing `@PreDestroy` does not prove the property was enabled**. Check the loaded configuration value, closing timing, and any keep-alive sources.

## 5. Checking `TaskRepository` After Context Closure

Closing the context does not delete execution records. With a persistent database and successful updates, `TaskRepository` retains the history of each run.

Example query on `TASK_EXECUTION` by task name:

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
WHERE TASK_NAME = 'daily-report-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Table and column names here follow the common Spring Cloud Task SQL schema; cross-check with your application version's schema. Illustrative result for a normal run:

| TASK_NAME | START_TIME | END_TIME | EXIT_CODE |
| --- | --- | --- | --- |
| daily-report-task | 2026-11-24 08:10:01 | 2026-11-24 08:10:02 | 0 |

This row indicates the framework recorded a finished run with exit code `0`. It **does not assert that the Spring context closed**, since context closure state is not a dedicated column in `TASK_EXECUTION`; nor does it guarantee the report file or business data is valid. Verify simultaneously across:

1. **Business logs**: is `REPORT_DONE` present and was the data actually generated accurately?
2. **Repository**: does the record have the expected end time, exit code, and error details?
3. **Application lifecycle**: did cleanup callbacks run and did the process/pod terminate or stay active?
4. **Operations system**: what process exit code and timeout behavior did the scheduler or orchestrator record?

If `END_TIME` is empty, do **not** rush to conclude the task is still running: the process might have been forcefully killed or failed to update the repository in time. Verify actual OS/container status and infrastructure logs.

## 6. Biggest Risk: Runner Returning Before Async Processing Ends

When `closecontextEnabled=true`, Spring Cloud Task can close the context right after runners **return**. If a runner merely **kicks off** a background job and exits, metadata may mark the task completed while background work is still underway.

Example of an **unsuitable** approach for tasks that must wait for work to actually finish:

~~~java
@Bean
ApplicationRunner prematureRunner(ReportService reportService) {
    return args -> {
        reportService.generateAsync();
        // Runner returns immediately while async work is still running.
    };
}
~~~

Potential impacts:

- Spring-managed executors, DataSources, or HTTP clients are closed while the job is still using them.
- Work is interrupted or partially finished even though `TaskExecution` already recorded completion.
- The task is considered successful; subsequent reruns may write duplicate data.
- Threads outside Spring's management keep the JVM alive despite the context being closed.

**Solution:** let the runner return only when all mandatory work has succeeded or definitively failed.

Example using `CompletableFuture` and awaiting before the runner returns:

~~~java
@Bean
ApplicationRunner awaitedRunner(ReportService reportService) {
    return args -> {
        CompletableFuture<Void> result =
                reportService.generateAsync();
        result.join(); // Wait for completion; async errors propagate to the runner.
    };
}
~~~

This snippet assumes `generateAsync()` returns a `CompletableFuture<Void>` accurately representing the **entire** job. If it only returns a future for the first step, calling `join()` still does not guarantee later steps finished. In production, enforce timeouts, handle cancellation, propagate errors to the caller, and guarantee retry/idempotency policies. When using `@Async`, ensure a proper executor is configured and the future reflects real completion; fire-and-forget patterns are incompatible with determining task completion.

### With Spring Batch

When a Spring Cloud Task application uses **Spring Batch**, distinguish:

- **TaskRepository** records the lifecycle of the task application.
- **JobRepository** records Spring Batch jobs, steps, processing states, and checkpoints.

If a `JobLauncher` is configured to run asynchronously, the runner can return while the Batch job is still processing. Enabling automatic context closing in that case can cause errors or interrupt unfinished work. Design the task run to **wait for the Batch job to finish** and accurately reflect job status rather than treating job submission as business completion.

## 7. Cleaning Up Resources Properly

Closing the Spring context signals Spring-managed components to go through their destruction lifecycle. Common mechanisms include:

- `@PreDestroy` on Spring-managed beans to close files, connections, or dedicated resources.
- `DisposableBean` or bean destroy methods for resource cleanup.
- `SmartLifecycle.stop()` for components whose lifecycle is controlled by the context.
- Shutdown hooks of Spring-managed executors, connection pools, clients, and libraries.

Example of a dedicated task resource:

~~~java
@Component
public class ReportFileHandle {

    private final Logger log =
            LoggerFactory.getLogger(ReportFileHandle.class);

    @PreDestroy
    void cleanup() {
        log.info("Closing report file handle");
        // Close the actual handle if this bean owns that resource.
    }
}
~~~

This example illustrates only the callback; do not use `@PreDestroy` to produce primary business outputs or perform a long critical transaction. If shutdown is cut short, cleanup code may not finish in time. Core business data must be committed **before the runner returns**.

**Closing the context does not guarantee every thread stops.** Threads created via `new Thread(...)`, executors not registered as beans, or libraries ignoring shutdown can keep the JVM alive. Meanwhile, calling `System.exit(...)` forcefully can bypass in-flight work or limit cleanup time; never use it as a quick fix for missing resource management.

## 8. Comparison with Other Ways to Terminate an Application

| Approach | Scope of Impact | Notes |
| --- | --- | --- |
| `spring.cloud.task.closecontextEnabled=true` | Instructs Spring Cloud Task to close the context when the task lifecycle completes | Suitable when runners exit after all business work finishes; does not force-stop all threads. |
| `SpringApplication.exit(context)` | Closes the passed context and computes exit code per Spring Boot | Application explicitly controls timing; avoid closing before task updates and processing finish. |
| `System.exit(code)` | Requests the JVM to exit with the specified code | Should not be called mid-business-logic; can cut across lifecycle and background work. |
| `spring.main.web-application-type=none` | Prevents Spring Boot from starting a web application | Helpful for CLI tasks, but does not close the context after the task. |
| Stopping pod/job in infrastructure | Ends process/container lifecycle per platform policy | Timeouts, signals, and graceful shutdown periods can affect repository updates. |

**You do not need to combine all of the above.** When choosing `closecontextEnabled=true`, let runners return naturally and let Spring Cloud Task handle the lifecycle. If the application needs a non-`0` OS exit code, design exception-to-exit-code mapping separately and verify it in the actual launch environment; the context-closing property does not configure exit codes.

## 9. Real-World Scenarios and Configuration Choices

### Scenario A — Scheduled report generation

The application accepts `--reportDate=yyyy-MM-dd`, queries data, creates a file, and uploads it to storage. Once all steps finish, the runner returns. **You should enable** `closecontextEnabled=true`, combine with `web-application-type=none` where appropriate, and let Kubernetes CronJob or another scheduler decide launch timing.

Add output verification, safe rerun logic, and infrastructure timeouts. The context-closing property neither creates a schedule nor retries tasks automatically.

### Scenario B — Task with an executor holding threads

A task already wrote `END_TIME` to the repository, yet the process stays alive because an executor still holds threads. **You can enable** `closecontextEnabled=true` if the executor is a Spring bean with an appropriate shutdown policy and the runner has already awaited all critical work. If threads are unmanaged by Spring, fix thread management rather than expecting this property to solve it completely.

### Scenario C — Task dispatching a background job

The runner calls an API to launch a long-running job and returns. If the task's goal is solely **dispatching the command**, the task's own business outcome must be clearly defined as "command dispatched successfully"; completion of the job in the remote system must be monitored independently. If the goal is **completing the job**, the runner must await the job result and reflect errors accurately.

### Scenario D — Web application also acting as a task

The application runs an HTTP server to serve continuous requests while also having a startup runner. Enabling `closecontextEnabled=true` can close the web context once the runner finishes, unexpectedly stopping the HTTP service. **Do not use this option on a single process meant to serve continuously**; extract finite jobs into a dedicated task application if needed.

## 10. Hands-On: Observing Both Configurations

Using the illustrative application from Section 4, run in a test environment:

**Run 1 — enable automatic context closing:**

~~~bash
java -jar daily-report-task.jar \
  --reportDate=2026-11-23 \
  --spring.cloud.task.closecontextEnabled=true
~~~

**Run 2 — disable Spring Cloud Task's automatic closing:**

~~~bash
java -jar daily-report-task.jar \
  --reportDate=2026-11-24 \
  --spring.cloud.task.closecontextEnabled=false
~~~

The two commands above illustrate shell syntax supporting line continuation with `\` (Linux/macOS). On PowerShell, put all arguments on **one line**:

~~~powershell
java -jar daily-report-task.jar --reportDate=2026-11-24 --spring.cloud.task.closecontextEnabled=false
~~~

Observe step by step:

1. Confirm the active profile and the `closecontextEnabled` value actually loaded on each run.
2. Note the `REPORT_START` and `REPORT_DONE` logs; verify business work completed.
3. Look for the `SPRING_BEAN_DESTROY` message and check whether the process terminated or threads remained alive.
4. Inspect `TASK_EXECUTION` records for each run. The two runs must have distinct IDs; in normal conditions both should have end timestamps.
5. Draw conclusions from **actual behavior and configuration**, not merely whether `@PreDestroy` appeared. For simple tasks, the difference may be subtle because the JVM shutdown hook also closes the context when set to `false`.

If you want to investigate why a process stays running, use a **Spring-managed** executor in a test environment with explicit stop and timeout handling. Never create infinite loops or unmanaged threads just to "test whether the JVM hangs."

## 11. Common Troubleshooting

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| `closecontextEnabled=true` yet JVM does not exit | Non-daemon thread still running, manually created executor, stuck shutdown callback | Take a thread dump, inspect beans/executors, timeouts, and stop signals. |
| Context closes while work is still running | Runner started async work and returned early | Await `Future`/`CompletableFuture` or true completion before the runner ends. |
| `@PreDestroy` callback not observed | Bean not Spring-managed, context killed, filtered logs, or task failed too early | Check bean lifecycle, log levels, stack traces, and how the process terminated. |
| `TaskExecution` has `END_TIME` yet business output is missing | Async processing or treating request submission as completion | Mark success only after confirming business side effects. |
| No execution record | Context failed to bootstrap, DataSource/schema error, or task not enabled | Inspect startup logs, dependencies, `@EnableTask`, database connectivity. |
| Task runs fine via CLI but fails on Kubernetes | Infrastructure sent signals, hit timeout, or terminated container early | Compare termination grace period, pod logs, exit code, and repository status. |
| HTTP service stops unexpectedly | Context-closing option enabled on a long-running web app | Split finite tasks into a separate process; review responsibility boundaries. |

### Pre-Production Checklist

- [ ] Each runner returns only after **all required work** has finished or errors have been reported.
- [ ] No untracked "fire-and-forget" jobs remain; explicit timeouts are set on Futures.
- [ ] Executors, connection pools, and background resources are Spring-managed or have explicit shutdown methods.
- [ ] Tested success, business failure, database failure, and abnormal process termination cases.
- [ ] `TaskRepository` persists metadata in an appropriate database; runs correlate with logs.
- [ ] Proper exit codes and retry rules are configured for the scheduler/orchestrator.
- [ ] If integrated with Spring Batch, job and task states are tracked according to each repository's responsibility.
- [ ] The application is a finite task, not a service required to keep its context alive continuously.
- [ ] Monitoring covers runtime duration, resources, unclosed records, and operational policies for stuck tasks.

## 12. Summary

`spring.cloud.task.closecontextEnabled=true` is a lifecycle management option tailored for **finite-running Spring Cloud Task applications**: after runners complete and execution metadata is updated, the framework proactively closes the Spring `ApplicationContext`. In YAML, you can write `spring.cloud.task.closecontext-enabled: true`; the property defaults to `false` in current versions.

Always distinguish **task completion**, **context closure**, and **JVM exit**. Safe use of this option requires that runners accurately reflect work completion, resources are properly managed, and retry mechanisms do not produce duplicate side effects. From there, you can deploy tasks on a schedule, on demand, or alongside Spring Batch while maintaining full control over execution state and database results.

### References

- [Spring Cloud Task Reference — The lifecycle of a Spring Cloud Task](https://docs.spring.io/spring-cloud-task/reference/features.html#the-lifecycle-of-a-spring-cloud-task)
- [Spring Cloud Task Reference — Closing the Context](https://docs.spring.io/spring-cloud-task/reference/features.html#closing-the-context)
- [Spring Cloud configuration properties](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
