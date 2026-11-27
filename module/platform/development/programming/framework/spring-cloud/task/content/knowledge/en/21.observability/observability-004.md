# Observing ApplicationRunner and CommandLineRunner

In the **Observability** chapter of the **SPRING_CLOUD_TASK** module, simply having a short-lived application run and exit does not mean we have enough information to know **which steps it executed, how long they took, where it failed, and whether business data was committed successfully**. Especially for scheduled or on-demand tasks, monitoring data must remain valuable **after the JVM terminates**.

Spring Boot provides two common interfaces for executing work once after application startup: `ApplicationRunner` and `CommandLineRunner`. Spring Cloud Task adds `TaskExecution`, `TaskRepository`, and lifecycle callbacks to track the start and end of **the entire task process**. These two layers complement each other, yet **they are not the same**: a completed `TaskExecution` does not automatically tell you how long each runner took, how many records were processed, or whether a second runner was even invoked.

This lesson implements **structured logging, correlation IDs, execution timing with Micrometer Timer, and TaskExecutionListener**, while pointing out the limits of these observation sources when a task is killed, the repository is unavailable, or a metrics collector fails to read data in time.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `ApplicationRunner` and `CommandLineRunner` by parameter type and how Spring Boot invokes them.
- Explain execution ordering across multiple runners, behavior when a runner throws an exception, and the meaning of an uninvoked step.
- Measure **per-runner** duration with a monotonic clock (`System.nanoTime()`) and record the result into a `Micrometer Timer`.
- Emit structured logs containing `runId`, runner name, status, duration, and error code.
- Use `TaskExecutionListener` to track the **task lifecycle**, while distinguishing callbacks before/after `TaskRepository` write operations.
- Understand why in-memory metrics inside a short-lived process are not automatically collected by monitoring systems.
- Reconcile logs, metrics, `TaskExecution`, process exit codes, and business outcomes.
- Design alerts and tests for pre-context startup errors, in-runner errors, killed JVMs, and retries.

## 2. Where Do Runners Execute in the Spring Boot Lifecycle?

According to the Spring Boot documentation, beans implementing `ApplicationRunner` and `CommandLineRunner` are invoked near the end of `SpringApplication.run(...)`, **after the context is initialized** and before the `run` call returns. Spring Cloud Task creates metadata once task infrastructure is ready and updates it upon completion or failure depending on runtime conditions.

~~~mermaid
flowchart TD
    A["JVM started by launcher"] --> B["SpringApplication.run begins"]
    B --> C["Create ApplicationContext, beans, DataSource"]
    C --> D["Spring Cloud Task prepares/writes TaskExecution when possible"]
    D --> E["Runner with lower order value"]
    E --> F["Next runner if no blocking error occurred"]
    F --> G["Task lifecycle records completion when possible"]
    G --> H["Close context and exit process"]
    C -. "Early init failure" .-> I["May have no TaskExecution / runner logs"]
    E -. "Runner throws exception" .-> J["Subsequent runners may not be called"]
    F -. "JVM killed / DB lost" .-> K["Completion event may be missing"]
~~~

This diagram is an operational model for observability, not a guarantee of every internal callback order across all Spring Boot and Spring Cloud Task versions.

### 2.1. ApplicationRunner and CommandLineRunner

| Criterion | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Signature | `run(ApplicationArguments args)` | `run(String... args)` |
| Input data | `ApplicationArguments` separating options and non-options | Raw argument string array |
| Reading option `--runId=R-001` | `args.getOptionValues("runId")` | Parse strings manually or use a parser |
| When called by Spring Boot? | End of startup, before `SpringApplication.run` returns | Same phase |
| Best suited for | Tasks with `--name=value` style options | Simple jobs or raw argument processing |
| Observability | Must actively log/record metrics inside `run` | Also must actively log/record metrics inside `run` |

**The two interfaces do not create two different measurement mechanisms.** Each `run` is a block of code that can be wrapped by shared logic: start timer, log, run business work, record outcome or error, and stop timer.

### 2.2. Ordering Across Multiple Runners

When an application has multiple runner beans, Spring Boot supports `Ordered` or `@Order`. A **lower** order value has higher priority. Whenever order affects business logic, declare it explicitly instead of relying on class names, bean creation order, or component scan order.

Example:

~~~java
@Component
@Order(10)
class ImportRunner implements ApplicationRunner { /* ... */ }

@Component
@Order(20)
class SummaryRunner implements CommandLineRunner { /* ... */ }
~~~

Here `ImportRunner` is expected to run before `SummaryRunner` when both are active in the same application. If `ImportRunner.run` throws an unhandled exception, Spring Boot does not continue invoking `SummaryRunner` as if no error occurred. When building dashboards, distinguish:

- `NOT_STARTED`: never invoked; no runner execution duration measurement exists.
- `SUCCEEDED`: started and finished normally.
- `FAILED`: started but threw an exception.
- `UNKNOWN`: showed signs of starting without a finish; the JVM may have been killed or logs/telemetry lost.

These states are **custom observability conventions**, not a built-in Spring Cloud Task enum.

## 3. Four Layers of Evidence to Collect

A production system should observe at least four layers:

| Layer | Typical data | Source |
| --- | --- | --- |
| **Runner** | `runner.start`, `runner.finish`, `runner.failure`; duration, record counts | Logs, Micrometer Timers, and business metrics |
| **Spring Cloud Task** | `executionId`, `taskName`, `startTime`, `endTime`, `exitCode`, `exitMessage`, `errorMessage` | `TaskExecutionListener`, `TaskRepository` |
| **Runtime / scheduler** | Launch time, PID/Pod/Job, OOM, timeout, OS exit code | Kubernetes, SCDF, scheduler, or process supervisor |
| **Business outcome** | Written records/files, checksums, committed row counts, business keys | Business database, object storage, target system |

These layers answer **different questions**. For instance, a `runner.finish outcome=success` log shows that the runner code reached the completion branch, but does not itself guarantee the database holds valid results. Similarly, `TaskExecution` might record an error after a report was already committed if a metadata update or post-processing step failed.

Therefore you need a **correlation ID**: a `runId` generated by the scheduler or API **before launching the JVM** and passed into the application. When a request is retried, keep a stable `requestId`/business key and issue a distinct `attemptId` per attempt. `TASK_EXECUTION_ID` must not serve as a business key because it may not exist when bootstrap fails.

## 4. Designing Structured Logs for Runners

### 4.1. Fields to Include

A runner lifecycle log should provide at least:

| Field | Example | Purpose |
| --- | --- | --- |
| `event` | `runner.start` / `runner.finish` / `runner.failure` | Categorize events |
| `runId` | `run-20261124-001` | Correlate logs for an orchestrated run |
| `runner` | `import`, `summary` | Identify the code step |
| `outcome` | `success`, `failure` | Step execution outcome |
| `durationMs` | `1250` | Measured elapsed time |
| `errorCode` | `INPUT_INVALID` | Stable error grouping, avoiding fragile exception-text matching |
| `processed` / `committed` | `200` / `200` | Properly named business counts |
| `taskExecutionId` | `502` if available | Link to Spring Cloud Task record |

Example log sequence:

~~~text
event=runner.start runner=import runId=run-20261124-001
event=runner.finish runner=import outcome=success durationMs=1250 runId=run-20261124-001
event=runner.start runner=summary runId=run-20261124-001
event=runner.finish runner=summary outcome=success durationMs=47 runId=run-20261124-001
~~~

This is an illustrative example, not a mandatory Spring Boot log format. With a centralized log collector, emit JSON or fields parseable by an ingest pipeline rather than relying on fragile unstructured strings.

### 4.2. Never Log Sensitive Information

`ApplicationArguments` and `String... args` may contain tokens, passwords, or customer details if passed improperly by an operator. **Never log raw `args` by default.** Log only allowlisted fields, or use `runId` to look up details inside an access-controlled orchestrator.

Do not place `runId`, user IDs, order IDs, or transaction dates into **metric tags** if they cause unbounded cardinality growth. Those belong in logs/traces, not as labels on every time series.

## 5. Practical Example: Measuring Both Runner Types in One Task

This example uses Spring Boot 3.x, Java 17+, a compatible Spring Cloud Task version, and Micrometer. When invoked:

~~~bash
java -jar runner-observation.jar   --runId=run-20261124-001 --businessDate=2026-11-24
~~~

two runners execute in order: `ImportRunner` then `SummaryRunner`. A `--fail` flag simulates a failure in the first runner to inspect the second runner's behavior and `TaskExecution`.

### 5.1. Maven Dependencies

The project uses a Spring Boot parent/BOM and a **compatible Spring Cloud BOM release train**. Required dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
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
~~~

Add `spring-boot-maven-plugin` under `build` to produce an executable JAR. `spring-boot-starter-actuator` provides Micrometer/`MeterRegistry` infrastructure via auto-configuration; recording meters inside the JVM **does not imply** a persistent exporter is active.

### 5.2. Java: ApplicationRunner, CommandLineRunner, and Timer

Create `src/main/java/com/example/task/RunnerObservationApplication.java`:

~~~java
package com.example.task;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerObservationApplication {

    private static final Logger log =
            LoggerFactory.getLogger(RunnerObservationApplication.class);

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(RunnerObservationApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Component
    @Order(10)
    static class ImportRunner implements ApplicationRunner {
        private final MeterRegistry meters;

        ImportRunner(MeterRegistry meters) {
            this.meters = meters;
        }

        @Override
        public void run(ApplicationArguments args) throws Exception {
            String runId = requiredOption(args, "runId");

            observe("import", runId, meters, () -> {
                LocalDate businessDate = LocalDate.parse(
                        requiredOption(args, "businessDate"));

                log.info("import.business_date date={}", businessDate);

                if (args.containsOption("fail")) {
                    throw new IllegalStateException(
                            "DEMO_IMPORT_FAILURE");
                }

                // Demo: in production, invoke a transactional service.
                log.info("import.processed processedRows={}", 3);
            });
        }
    }

    @Component
    @Order(20)
    static class SummaryRunner implements CommandLineRunner {
        private final MeterRegistry meters;

        SummaryRunner(MeterRegistry meters) {
            this.meters = meters;
        }

        @Override
        public void run(String... args) throws Exception {
            // CommandLineRunner receives raw arguments and must parse them manually.
            String runId = rawOption(args, "runId");

            observe("summary", runId, meters, () -> {
                log.info("summary.completed result=READY");
            });
        }
    }

    @FunctionalInterface
    interface CheckedWork {
        void execute() throws Exception;
    }

    static void observe(
            String runnerName,
            String runId,
            MeterRegistry meters,
            CheckedWork work) throws Exception {

        long startNanos = System.nanoTime();
        String outcome = "success";

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("runId", runId)) {
            log.info("runner.start runner={}", runnerName);

            try {
                work.execute();
            } catch (Exception | Error failure) {
                outcome = "failure";
                log.error("runner.failure runner={}", runnerName, failure);
                throw failure;
            } finally {
                long elapsedNanos = System.nanoTime() - startNanos;
                long elapsedMs =
                        TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

                log.info("runner.finish runner={} outcome={} durationMs={}",
                        runnerName, outcome, elapsedMs);

                // Telemetry must never mask business errors.
                try {
                    Timer.builder("task.runner.duration")
                            .description("Execution duration per runner")
                            .tag("runner", runnerName)
                            .tag("outcome", outcome)
                            .register(meters)
                            .record(elapsedNanos, TimeUnit.NANOSECONDS);
                } catch (RuntimeException metricFailure) {
                    log.warn("runner.metric_record_failed runner={}",
                            runnerName, metricFailure);
                }
            }
        }
    }

    static String requiredOption(ApplicationArguments args,
                                 String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Must provide one --" + name + "=<value>");
        }
        return values.get(0).trim();
    }

    static String rawOption(String[] args, String name) {
        String prefix = "--" + name + "=";
        List<String> values = Arrays.stream(args)
                .filter(s -> s.startsWith(prefix))
                .map(s -> s.substring(prefix.length()))
                .toList();

        if (values.size() != 1 || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Must provide one --" + name + "=<value>");
        }
        return values.get(0).trim();
    }

    @Bean
    TaskExecutionListener taskLifecycleLogger() {
        return new TaskExecutionListener() {
            @Override
            public void onTaskStartup(TaskExecution execution) {
                log.info("task.lifecycle event=start executionId={} taskName={}",
                        execution.getExecutionId(),
                        execution.getTaskName());
            }

            @Override
            public void onTaskFailed(TaskExecution execution,
                                     Throwable cause) {
                log.error("task.lifecycle event=failure executionId={}",
                        execution.getExecutionId(), cause);
            }

            @Override
            public void onTaskEnd(TaskExecution execution) {
                log.info("task.lifecycle event=end executionId={} exitCode={}",
                        execution.getExecutionId(),
                        execution.getExitCode());
            }
        };
    }
}
~~~

The example intentionally **does not invoke `TaskRepository` inside each runner**. Spring Cloud Task manages lifecycle metadata; `observe(...)` measures the runner block. `TaskExecutionListener` simply observes milestones delivered by the framework.

**Limitation of this example:** `requiredOption` is called **before** `observe(...)` to obtain `runId`. If `--runId` is missing or malformed, the failure happens before the runner timer starts; logs and `TaskExecutionListener` (when active) can still provide context. In production, add a dedicated validation layer with metrics to catch input configuration errors.

### 5.3. Configuring application.yml

~~~yaml
spring:
  application:
    name: runner-observation
  main:
    web-application-type: none
  datasource:
    url: jdbc:h2:file:./runner-observation-db
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      name: runner-observation
      initialize-enabled: true

logging:
  pattern:
    console: '%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [runId=%X{runId:-none}] %logger{36} - %msg%n'
~~~

- `web-application-type: none` keeps the application from starting a web server just to run a finite task.
- File-based H2 (`file:`) preserves metadata after the JVM stops, unlike `jdbc:h2:mem:...`, which loses data when the process exits. When querying from an H2 client, point to the exact database file path and avoid unsupported concurrent file access.
- `initialize-enabled: true` is convenient for this lab when your Spring Cloud Task version supports the H2 schema; production should use a durable database managed with schema migrations.
- `%X{runId:-none}` reads `runId` from the runner thread's SLF4J MDC. MDC does not automatically propagate to other threads or callbacks executing in a different context.
- Micrometer holds the `Timer` inside its registry, yet the configuration above **does not export metrics outside the JVM**. Duration logs remain useful once logs are centralized.

### 5.4. Running Two Scenarios

Package and run a successful execution:

~~~bash
./mvnw clean package
java -jar target/runner-observation-0.0.1-SNAPSHOT.jar   --runId=run-20261124-001 --businessDate=2026-11-24
~~~

The JAR name is illustrative; use the actual Maven artifact produced. On Windows PowerShell, use `mvnw.cmd clean package` and run `java -jar` on a single line.

Logs will contain events similar to:

~~~text
task.lifecycle event=start executionId=101 taskName=runner-observation
runner.start runner=import
import.business_date date=2026-11-24
import.processed processedRows=3
runner.finish runner=import outcome=success durationMs=...
runner.start runner=summary
summary.completed result=READY
runner.finish runner=summary outcome=success durationMs=...
task.lifecycle event=end executionId=101 exitCode=...
~~~

`durationMs`, `executionId`, and related values depend on the actual run. In real output, `runId` is printed in the prefix of lines logged within the runner's MDC scope.

Run with an intentional failure:

~~~bash
java -jar target/runner-observation-0.0.1-SNAPSHOT.jar   --runId=run-20261124-002 --businessDate=2026-11-24 --fail
~~~

When `ImportRunner` throws an exception, expect `runner.failure runner=import`, `runner.finish outcome=failure`, and the Spring Cloud Task failure callback **if the context/repository is healthy enough to record it**. `SummaryRunner` is not invoked along the normal execution path; therefore **there is no `runner.start runner=summary`** in this failed run.

If `runner.summary.duration` has no data point, do not assume `SummaryRunner` ran instantaneously: it may **never have been called**.

## 6. TaskExecutionListener Observes the Whole Task, Not Just One Runner

Spring Cloud Task provides `TaskExecutionListener` with three callbacks:

| Callback | Timing per documentation | Important distinction |
| --- | --- | --- |
| `onTaskStartup(TaskExecution)` | **Before saving** initial metadata to the repository | A startup callback/log does not guarantee the record committed |
| `onTaskFailed(TaskExecution, Throwable)` | When the task encounters an unhandled exception, **before** the end callback | Reveals the exception cause when observable by the framework |
| `onTaskEnd(TaskExecution)` | **Before updating** final metadata in the repository | An end callback does not guarantee the final JDBC update succeeded |

The documentation also provides `@BeforeTask`, `@FailedTask`, and `@AfterTask` annotations when you prefer annotated methods over implementing the interface.

~~~java
@Component
class TaskAuditHooks {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditHooks.class);

    @BeforeTask
    public void start(TaskExecution execution) {
        log.info("task.audit.start id={}",
                execution.getExecutionId());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable error) {
        log.error("task.audit.failure id={}",
                execution.getExecutionId(), error);
    }

    @AfterTask
    public void end(TaskExecution execution) {
        log.info("task.audit.end id={}",
                execution.getExecutionId());
    }
}
~~~

This snippet illustrates an **alternative** to the listener bean in Section 5.2; do not enable both simultaneously just to log twice. When placing it in a separate file, import `Component`, `Logger`, `LoggerFactory`, `TaskExecution`, and the three annotations from the listener annotation package for your Spring Cloud Task version.

### When to Use a Listener vs. Wrapping a Runner

- **Listener:** record start/end/failure of the **overall task**, attach `executionId` when available, set short exit messages, or run lightweight auditing.
- **Runner wrapper:** measure individual **business steps**, identify which runner actually ran, and capture its exact duration.
- **Service instrumentation:** measure granular stages such as file reads, HTTP calls, database writes, and committed row counts.

Do not push slow network calls, heavy queries, or new business logic into an observability listener. A listener throwing an exception can disrupt callback chains and task outcomes; observability should operate on a **best-effort** basis without unexpectedly altering business behavior.

## 7. Measuring Time Properly and Choosing the Right Metrics

### 7.1. Why Use System.nanoTime()?

`System.nanoTime()` provides relative monotonic time for measuring **elapsed duration**; it is superior to subtracting wall-clock timestamps (`LocalDateTime.now()`) when the system clock adjusts. It is **not** a Unix timestamp for displaying start times.

Example:

~~~java
long started = System.nanoTime();
try {
    process();
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("elapsedMs={}",
            TimeUnit.NANOSECONDS.toMillis(elapsed));
}
~~~

For overall task latency, you can also measure total time seen by the scheduler from launch request to process exit. That number includes **scheduling, image pull, JVM bootstrap, and queue wait**, so it is not equivalent to an `ApplicationRunner` timer.

### 7.2. What Does a Micrometer Timer Measure?

In the example, the meter is named:

~~~text
task.runner.duration
~~~

with two low-cardinality tags:

~~~text
runner=import|summary
outcome=success|failure
~~~

`Timer` accumulates call counts and durations (and can optionally publish histograms/percentiles). When exported to Prometheus, series names may be transformed per registry conventions; do not assume the literal string `task.runner.duration` appears verbatim in Prometheus.

Recommended meter types:

| Metric type | Example | Meaning |
| --- | --- | --- |
| `Timer` | `task.runner.duration` | Per-runner execution duration |
| `Counter` | `task.runner.failures` | Failure counts, when tracked separately |
| `DistributionSummary` | `task.records.committed` | Distribution of records actually committed per attempt |
| Gauge | Active job count in a **long-lived orchestrator** | Point-in-time active status |

**Never use a Gauge inside a very short-lived task JVM** as the sole source for how many Jobs are running on the cluster. When the JVM exits, the Gauge disappears with its registry; active state must come from the scheduler or a long-lived collector.

### 7.3. Metric Tags Should Stay Bounded

Attach labels like `runner`, `outcome`, or `taskType` when their value sets are fixed and small. Avoid `runId`, `taskExecutionId`, `orderId`, user IDs, or timestamps because every run spawns a new series, causing **high cardinality** and high storage costs.

Keep granular IDs in **logs** and **trace spans**, where search tools handle them well; do not turn them into labels on every time series.

## 8. Why Short-Lived Task Metrics Are Easily Lost

A web application running for hours lets Prometheus scrape `/actuator/prometheus` periodically. By contrast, a Spring Cloud Task may run for **a few hundred milliseconds or a few seconds** and then exit. If Prometheus scrapes every 15–30 seconds, many runs will **never have a live endpoint when a scrape occurs**.

Example:

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant T as Task JVM
    participant P as Metrics collector
    S->>T: Start task 12:00:01
    T->>T: Runner records Timer 12:00:02
    T--xS: JVM exits 12:00:03
    P->>T: Scrape at 12:00:15
    Note over P,T: Task already exited; no endpoint/registry left
~~~

Even with `spring-boot-starter-actuator`:

- With `spring.main.web-application-type=none`, there is no HTTP actuator server for Prometheus to query like a web app.
- Not every metric recorded in a registry is shipped externally; without a configured exporter, data stays inside the JVM.
- A registry with a periodic publish interval may not reach its first export tick before the JVM stops.
- Abrupt process termination, early startup errors, or `SIGKILL` can prevent the exporter from flushing.

### Better Alternatives

1. **Centralized structured logs:** each runner emits start/finish/failure logs with duration; the scheduler stores exit codes. Serves as a reliable baseline for very short tasks.
2. **Properly configured push/OTLP metrics exporter:** a collector receives data before process exit; test shutdown/flush behavior, timeouts, retries, and version-specific export limits.
3. **Long-lived exporter or orchestrator:** aggregates run/failure counts and durations from Job/TaskRepository/logs rather than hoping to scrape short-lived JVMs.
4. **Pushgateway when a Prometheus architecture genuinely requires it:** plan grouping keys and delete stale metrics. Never treat Pushgateway as per-`runId` historical storage or abuse high-cardinality labels.

No export mechanism makes data **100% guaranteed** if a process is forcefully killed or loses network connectivity mid-flush. Never rely on an in-memory metric alone to prove business completion.

## 9. Observing Exceptions Without Hiding the Root Error

A common mistake is catching every exception in a runner just to log it and return normally:

~~~java
try {
    importService.execute();
} catch (Exception e) {
    log.error("Import failed", e);
    // Wrong if this error should fail the task:
    // the runner continues without reporting a failure.
}
~~~

When business logic fails, let the orchestration layer receive the failure signal properly:

~~~java
try {
    importService.execute();
} catch (Exception e) {
    log.error("Import failed; code=IMPORT_ERROR", e);
    throw e;
}
~~~

Both snippets assume `importService` and `log` are defined. If an error is legitimately recoverable and the output is verified, the service may return a controlled success result; **never swallow errors just to keep logs tidy**.

In our main example, the `observe` helper:

1. Logs `runner.start` before invoking business work.
2. On error, sets `outcome=failure`, logs the stack trace, and **rethrows**.
3. Always logs `runner.finish` in `finally` if the JVM is still running.
4. Records duration for both success and failure.
5. Wraps metric recording so telemetry errors never replace business exceptions.

**Avoid logging the exact same stack trace repeatedly at every layer** when centralized logging is in place; log an error code in the runner and the full stack trace at a chosen boundary. Multi-layer logging in this example illustrates observation sources rather than requiring duplicate stack traces in production.

## 10. Limitations When ApplicationContext Fails to Initialize

Code inside `ApplicationRunner.run` and `CommandLineRunner.run` runs **only if Spring Boot reaches the runner invocation phase**. When failure occurs earlier:

- Missing class or invalid main method: the JVM may never create a Spring context.
- Wrong profile, invalid YAML, missing secret, bean creation error: the context may fail before calling any runner.
- Cannot create `DataSource` or `TASK_EXECUTION` schema: the repository may not be ready.
- Failure instantiating a runner bean: the runner object itself is never constructed to begin measuring.

In these cases, **no `runner.start` does not prove the launcher never tried to run**. Evidence must come from **outside the application**: Kubernetes Job/Pod state, exit codes, JVM stderr/bootstrap logs, and scheduler launch records.

An early-registered Spring Boot `ApplicationFailedEvent`/listener can emit supplementary logs if the process gets far enough to fire events, yet it cannot handle a JVM that fails to boot or receives `SIGKILL`. Never promise final logs for every crash scenario.

## 11. Reconciling TaskRepository with Runner Logs

When using a durable JDBC database with a compatible Spring Cloud Task schema, query:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'runner-observation'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Combine this with logs carrying `runId` to answer:

- Which runners emitted `runner.start`?
- Which runners emitted `runner.finish`? What were each runner's outcome and duration?
- Does `TaskExecution` have `END_TIME` and `EXIT_CODE`?
- Did the container/process actually stop, and why?
- Were business results properly committed or published?

| Scenario | Runner logs | TaskRepository | Operational conclusion |
| --- | --- | --- | --- |
| Both runners finished | Two `start/finish success` pairs | Usually has `END_TIME` and success code if writable | Still verify business output |
| First runner threw exception | `import.failure`, no `summary.start` | Likely records error if infra is available | Failed; do not treat the next runner as having duration 0 |
| Early context failure | No runner logs | Record may be absent | Inspect startup and runtime logs |
| JVM killed mid-runner | `start` present, `finish` missing | `END_TIME` likely missing | UNKNOWN/FAILED per runtime; reconcile data |
| Metadata DB lost connection | Runner may finish | Record missing or final update failed | Compare runtime and output; do not infer rollback |
| Telemetry export error | Runner still runs; metric warnings appear | Reflects business and repository state | Fix exporter; do not falsify business outcome |

**Never manually edit `TASK_EXECUTION.EXIT_CODE` or `END_TIME` just to make a dashboard look "completed."** Preserve historical evidence and record reconciliation decisions in your orchestrator or a separate audit table.

## 12. Tracing: Observing a Multi-Step Run

With distributed tracing enabled, a runner can create spans for steps such as `read-source`, `transform`, and `write-target`. Traces reveal dependency chains and latencies across calls, especially when a task invokes APIs or message brokers.

Illustrative breakdown:

~~~text
requestId=REQ-017
  └─ task attempt / JVM
      ├─ import runner
      │   ├─ read-source
      │   └─ write-database
      └─ summary runner
          └─ publish-report
~~~

Keep in mind:

- `runId` in logs is a **business/orchestration correlation ID**; it does not automatically become an OpenTelemetry trace ID.
- Passing trace context from a launcher/API into a new JVM typically requires **explicit propagation configuration** (such as trace context via message headers or controlled environment variables). Never assume `traceparent` automatically flows through every launcher type.
- For short-lived tasks, the collector/exporter must **flush** before the JVM closes; spans can be lost if the process is killed.
- Sampling can be used, but avoid dropping all failed task traces if debugging requires them; match sampling rules to cost and diagnostic needs.
- Never use trace/span IDs as high-cardinality metric labels.

When tracing is not yet set up, **structured logs + runId + TaskRepository + scheduler state** remain a more reliable observability foundation than complex tracing that fails to deliver data.

## 13. Metrics and Business Outcomes Must Align

An import task might log "Processed 10,000 rows" while committing only 9,000. To prevent dashboards from reporting false success, name metrics after **what is actually measured**:

| Metric | Accurate meaning |
| --- | --- |
| `records.read` | Number of records fetched by the reader |
| `records.validated` | Number of records accepted by validation |
| `records.attempted_write` | Number of records passed to the writer |
| `records.committed` | Number of records confirmed committed |
| `records.skipped` | Number of records intentionally skipped |
| `runner.duration` | Runner code execution time, excluding scheduler wait |
| `launch_to_finish.duration` | From orchestrator launch request until runtime termination |

These names are **illustrative observability conventions**, not mandatory default Spring Cloud Task meters.

With JDBC, an unclear commit result during a connection drop is **UNKNOWN** until you re-read the business database by business key. Do not increment `records.committed` right after issuing a write without confirming commit, and do not blindly increment it again on retry if the record already existed.

When running Spring Batch, `StepExecution` provides `readCount`, `writeCount`, `skipCount`, and step status. Those are very useful, yet they do not replace target-system consistency checks or reconciling external side effects outside transactions.

## 14. Common Observability Mistakes

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Task startup logs exist, no runner logs | Context failed before runners or runner bean not registered | Check bootstrap logs, bean wiring, and `ApplicationFailedEvent` |
| Only ImportRunner logs, no SummaryRunner | First runner threw an exception or unexpected order | Inspect `@Order`, exceptions, and stack traces |
| `runner.start` present, `runner.finish` missing | JVM killed, log loss, fatal error, or still running | Check Pod/process, deadlines, OOM, and log backend |
| Duration in logs, no Prometheus metric | Registry not exported, task too short, no endpoint, late scrape | Inspect exporter config, telemetry collector, and lifetime |
| Metric series explosion | `runId`/order ID/timestamp placed in labels | Move IDs to logs/tracing and trim labels |
| `TaskExecution.END_TIME IS NULL` | Task still running or repository update failed after crash | Check scheduler/runtime and timeouts |
| `exitCode=0` yet no business output | Runner reported false success or skipped commit check | Inspect service, business keys, and writer |
| Multiple attempts share one `runId` | Scheduler retry or overlapping runs | Separate `requestId`/`attemptId` and verify idempotency |
| Logs lack `runId` in async worker | MDC is bound only to the current thread | Explicitly propagate context via executor or task decorator |
| Metrics show success yet task failed | One runner succeeded while another or shutdown failed | Compare TaskExecution and all runners |

## 15. Observability Test Plan

A test suite should cover:

1. **Success:** both runners have `start` and `finish success`; `TaskExecution` closes properly; business output is valid.
2. **First runner fails:** ImportRunner shows `failure`, SummaryRunner never starts; runtime/Task reports failure.
3. **Argument error:** missing or invalid `--runId`, `--businessDate`; observe bootstrap/Task logs and note which instrumentation never ran.
4. **Bean creation error:** simulate a bean throwing an exception during context initialization; runner metrics may be completely absent.
5. **Forced termination:** in a test, kill the JVM mid-runner; verify detection of missing logs/metadata via external monitoring sources.
6. **Metadata DB failure:** task may fail to create/update `TaskExecution`; logs/runtime must still support investigation.
7. **Slow or unreachable exporter:** runner still reflects accurate business outcomes; telemetry must not cause false failures.
8. **Multiple attempts:** same business key across distinct attempts; logs/`TaskExecution` link via `requestId` without duplicate writes.
9. **Metrics cardinality:** verify labels use bounded values only and exclude per-attempt unique IDs.
10. **Security:** zero secrets/PII in logs, metric tags, trace attributes, or broadly queryable Task metadata.

In staging, compare runner duration against total Task duration and launcher-measured duration. Differences usually stem from bootstrap, repository I/O, scheduling, telemetry export, or resource teardown. **Do not force the three numbers to match.**

## 16. Exercises and Self-Check Questions

**Question 1.** How does `ApplicationRunner` differ from `CommandLineRunner` in parameter types? If both carry `@Order`, what rule does Spring Boot use to invoke them?

**Question 2.** When `ImportRunner` fails and `SummaryRunner` is never called, why should `SummaryRunner`'s duration not be recorded as `0 ms`?

**Question 3.** Are `onTaskStartup` and `onTaskEnd` on `TaskExecutionListener` invoked before or after `TaskRepository` save/update operations? Why does this matter when analyzing logs?

**Question 4.** Why can a 2-second Spring Cloud Task record a Micrometer Timer yet leave Prometheus with nothing scraped from `/actuator/prometheus`?

**Question 5.** Should `runId`, `businessDate`, and `taskExecutionId` be attached as tags to every metric? Where do they belong instead?

**Question 6.** If `runner.finish outcome=success` appears while `TaskExecution.EXIT_CODE=1`, in what order would you investigate to find the error?

**Exercise A — Logs with runId.** Extend the example to add `requestId` and `attemptId`, documenting the relationship between a business request and multiple `TaskExecution` runs.

**Exercise B — Ordering failure test.** Swap `@Order` between the two runners and run with `--fail`; explain how changing order alters business results, log lines, and metrics.

**Exercise C — Exporting telemetry.** Pick an exporter/collector that works with short-lived tasks in a test environment. Inspect data after the JVM exits and simulate an unreachable collector. Document flush and sampling limitations.

**Exercise D — Reconciliation.** Using file-based H2 or persistent PostgreSQL, run one success and one failure. Query `TASK_EXECUTION` and reconcile it against both runners' logs and OS exit codes.

**Exercise E — Spring Batch.** Replace `ImportRunner` with launching a Spring Batch Job. Compare `TaskExecution`, `JobExecution`, `StepExecution`, and committed business counters.

## 17. Key Takeaways

- **`ApplicationRunner` and `CommandLineRunner` both run at the end of Spring Boot startup**, but accept different parameter types; use `@Order`/`Ordered` whenever sequence matters.
- **Measure runners individually** with logs and Timers to know which step started, finished, or failed; `TaskExecution` tracks **the entire task execution**.
- `TaskExecutionListener` provides `onTaskStartup`, `onTaskFailed`, and `onTaskEnd`. Callbacks running before repository writes/updates do not prove JDBC commits succeeded.
- **Structured logs with `runId`**, low-cardinality metric tags, and scheduler/runtime signals form the core observability foundation for short-lived tasks.
- **An in-JVM Micrometer registry does not guarantee metrics are exported after task exit**. Design appropriate collectors/exporters and account for flush limits on crash.
- **Missing `runner.start` or missing `TaskExecution` does not prove a task never attempted to launch**; early startup errors and crashes must be detected externally.
- Technical success must be verified against **committed business outcomes**, especially during retries, disconnects, or Spring Batch coordination.

## References

- [Spring Boot Reference — SpringApplication, ApplicationRunner, and CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html): when runners are invoked, arguments, and `@Order`.
- [Spring Cloud Task Reference — Features and Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskExecution` lifecycle and listener timing relative to `TaskRepository`.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, meter registries, and metrics export configuration.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer` API and duration measurements.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): traces/spans, context propagation, and tracing setup.

For production use, verify APIs and configuration against the **exact versions of Spring Boot, Spring Cloud Task, Micrometer, exporter, and orchestrator** in your project; log, metric, JAR, and database examples here are illustrative and do not replace integration testing.
