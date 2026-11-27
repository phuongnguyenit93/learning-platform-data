# Choosing a Non-Web Application Mode When Deploying Spring Cloud Task

## 1. The problem: a finite task must terminate, not wait for HTTP requests

**Spring Cloud Task** is used to build Spring Boot applications with a **finite** runtime: data ingestion, closing numbers, catalog synchronization, reconciliation, report generation, or launching a **Spring Batch Job**. When properly configured, each run can create a `TaskExecution` in `TaskRepository` to track the task name, start/end times, exit code, and arguments.

For example, consider a `daily-close-task` application invoked by a CronJob at 02:00 to close the previous day's revenue. The desired lifecycle is:

1. The JVM starts, reads configuration, and connects the required components.
2. Spring Cloud Task records the execution in the repository.
3. `ApplicationRunner` or `CommandLineRunner` invokes the daily-close business logic.
4. Business logic completes or raises an error; the framework gets a chance to write final metadata.
5. The Spring context closes, and the process returns an exit code to the CronJob/Job controller.

None of these steps require the application to accept HTTP requests. If `spring-boot-starter-web` accidentally ends up on the classpath and Spring Boot auto-detects a web type, embedded Tomcat or another web server may start, keeping the process alive even after the runner has finished. The orchestrator would then see a Pod stuck **Running** indefinitely instead of a completed Job.

The right choice for this class of application is usually **`WebApplicationType.NONE`**, paired with an explicit completion/exit mechanism and proper management of background work.

> **Principle:** A Spring Cloud Task application does not need to become a web service just to have `main(...)`, Dependency Injection, DataSource, transactions, the Actuator library, or the ability to make outbound HTTP calls to other systems. `NONE` disables the **embedded web server**, not the entire Spring Framework or network connectivity.

## 2. Three WebApplicationType modes and choosing the right one

Spring Boot distinguishes three application modes:

| Mode | ApplicationContext / web server | Best suited for | Risk when used for finite tasks |
|---|---|---|---|
| `NONE` | Non-web context; **does not start an embedded web server** | CLI, batch, ETL, reconciliation, finite Spring Cloud Task | No HTTP endpoint for direct status queries; must rely on logs/repository/orchestrator |
| `SERVLET` | Servlet web context with an embedded web server when configured | REST APIs, dashboards, HTTP callbacks | May keep the JVM alive after the runner finishes |
| `REACTIVE` | Reactive web context with an embedded reactive web server | Reactive HTTP gateways/services | Still a long-lived server process, differing from a Job lifecycle |

Spring Boot can **infer the application type from the classpath**. When Spring MVC libraries are present, Boot typically creates a servlet web context unless instructed otherwise; when only WebFlux is present, Boot may pick reactive. Therefore, **do not rely on accidental classpath contents** to decide whether a task runs a web server.

Real-world scenarios:

- **A daily file-export task:** use `NONE`.
- **An app permanently listening on `POST /run-report`:** that is a web API; use a **separate** request-handling service to trigger a finite Job/task instead of cramming both into one process without a lifecycle plan.
- **A task calling another system's REST API:** can still use `NONE`; an outbound HTTP client does not require opening an inbound port.
- **An app with both `@RestController` and scheduled batch needs:** consider splitting into a **control-plane web service** and a **worker/task application** so each component has a clear responsibility and lifecycle.

In particular, setting `server.port=-1` is **not the same** as `spring.main.web-application-type=none`. Spring Boot documents `server.port=-1` as disabling the HTTP endpoint while **still creating a web application context**; whereas `NONE` requests a non-web context and does not launch an embedded web server. Meanwhile, `server.port=0` picks a random port and **still runs a web server**.

## 3. Execution flow of a non-web application

~~~mermaid
flowchart TD
    A["CLI / CronJob / Scheduler"] --> B["JVM starts Spring Boot"]
    B --> C["Non-web ApplicationContext"]
    C --> D["TaskRepository records run"]
    D --> E["ApplicationRunner / CommandLineRunner"]
    E --> F["Service executes business logic"]
    F --> G{"Outcome?"}
    G -- "Success" --> H["Commit output + await all required work"]
    G -- "Exception" --> I["Error propagates to lifecycle"]
    H --> J["Framework handles TaskExecution completion"]
    I --> J
    J --> K["Close context and resources"]
    K --> L["JVM returns exit code"]
    L --> M["Job controller / scheduler records outcome"]
~~~

This is a logical diagram and does not guarantee every callback and repository write occurs in one fixed order across all versions. Keep in mind:

- **Spring Cloud Task observes the application and runner lifecycle**; it does not automatically monitor arbitrary `Thread` or `CompletableFuture` instances spawned independently.
- **Spring Batch**, if used, maintains an independent `JobRepository` to track Job/Step/checkpoints; `TaskRepository` does not replace it.
- **Business data** must be committed in its proper store, not merely recorded in `TaskExecution`.
- If the JVM receives `SIGKILL` or crashes before writing completion, metadata may still lack `END_TIME`; do not infer business state from that alone.

A non-web application can still misbehave: if the runner swallows exceptions, launches background threads and returns immediately, or runs a permanent scheduler loop, it loses its **finite** nature. Thus, choosing `NONE` is an **architectural prerequisite**, not the entire lifecycle solution.

## 4. Minimal configuration: web-application-type=none

In `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task
  cloud:
    task:
      name: daily-close-task
~~~

Or `application.properties`:

~~~properties
spring.main.web-application-type=none
spring.application.name=daily-close-task
spring.cloud.task.name=daily-close-task
~~~

Note: `spring.cloud.task.name` belongs under `spring.cloud.task`, whereas `spring.main.web-application-type` belongs to **Spring Boot**. The two properties have distinct responsibilities.

It can also be specified on the command line at runtime:

~~~bash
java -jar daily-close-task.jar \
  --spring.main.web-application-type=none \
  --date=2026-11-23
~~~

Or configured at the Java API level:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class DailyCloseTaskApplication {
    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(DailyCloseTaskApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
~~~

The Java API example illustrates setting the mode and is **not a complete application class**: a real project needs `@SpringBootApplication`, runner logic, Spring Cloud Task dependencies, and a context-closing/process-exit mechanism. Do not copy this snippet alone while omitting actual task initialization.

**Best practice:** explicitly set `spring.main.web-application-type=none` in deployment configuration and avoid adding web starters unless needed. That way, even if a transitive dependency brings web classes onto the classpath, the task will not accidentally turn into a server.

## 5. Dependencies: avoiding pulling an embedded server into a task app

A typical Spring Cloud Task application usually needs:

- Spring Boot core/autoconfiguration.
- Spring Cloud Task starter, aligned with the BOM and compatible Spring Boot version.
- DataSource/driver if persisting `TaskRepository` over JDBC.
- Spring Batch when the job needs Job/Step/checkpoint semantics.
- Spring JDBC/JPA or an HTTP client depending on business logic.

Illustrative dependency snippet (Gradle Groovy DSL; versions managed by compatible Spring Boot/Spring Cloud BOMs):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // Add only if you genuinely need Spring Batch Job/Step:
    // implementation 'org.springframework.boot:spring-boot-starter-batch'
}
~~~

This is a **dependencies snippet**, not a complete build file. A project still requires plugins, versions/BOMs, repositories, and build configuration. For newer or older Spring Cloud/Boot lines, always verify artifact names and compatibility matrices before concluding.

If no HTTP endpoint is needed, **there is no default reason to include `spring-boot-starter-web`**. If a client library transitively pulls in the web stack, `WebApplicationType.NONE` still serves as the configuration guardrail preventing an embedded server from starting.

Do not rely solely on `spring.main.lazy-initialization=true` or disabling `TomcatServletWebServerFactory` as a "workaround"; those address different concerns. The cleaner and more observable choice is **`web-application-type=none`**.

## 6. Writing a finite Spring Cloud Task application with ApplicationRunner

The illustrative example uses Spring Boot, Spring Cloud Task, and a business service. The runner reads the processing date from the CLI, invokes the service, and returns only after required work completes.

~~~java
package example.task;

import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableTask
public class DailyCloseTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(DailyCloseTaskApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner closeDayRunner(CloseDayService service) {
        return args -> {
            List<String> dates = args.getOptionValues("date");

            if (dates == null || dates.size() != 1
                    || dates.get(0) == null || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                    "Required argument: --date=yyyy-MM-dd");
            }

            LocalDate businessDate = LocalDate.parse(dates.get(0));

            // Only return once business logic completes or throws an error.
            service.closeDay(businessDate);
        };
    }
}

@Service
class CloseDayService {

    private static final Logger log =
        LoggerFactory.getLogger(CloseDayService.class);

    void closeDay(LocalDate businessDate) {
        log.info("Closing business date {}", businessDate);

        // Replace with real transaction, validation, computation, and persistence.
        // If the work fails, throw an exception; do not swallow errors.

        log.info("Close-day processing completed for {}", businessDate);
    }
}
~~~

**Lifecycle meaning:**

1. Spring Boot creates the `ApplicationContext`, while `@EnableTask` enables Spring Cloud Task configuration for supported versions.
2. `ApplicationRunner` is invoked during startup and runs the finite business logic.
3. `SpringApplication.exit(context)` closes the context, collects exit codes from relevant `ExitCodeGenerator` beans, and runs resource-closing callbacks.
4. `System.exit(exitCode)` passes the exit code to the OS/container so the scheduler knows the process has terminated.

The business service in this example is intentionally an **illustrative skeleton**—do not assume reports are genuinely closed just because a log line printed. Production code must add business repositories, transactions, idempotency checks, timeouts, and tests.

### What happens when the runner throws an exception

If `service.closeDay(...)` throws an unhandled exception, `SpringApplication.run(...)` may terminate by throwing **before returning a context to the `context` variable**. In that case, the `SpringApplication.exit(context)` line after `run(...)` is not executed. Spring Boot has its own startup failure and exit-code handling; verify the actual exit code against the release you use.

Catching every exception in the runner and merely logging it is discouraged:

~~~java
try {
    service.closeDay(businessDate);
} catch (Exception exception) {
    log.error("Close day failed", exception);
    // Wrong if execution proceeds to return normally:
    // the orchestrator may observe a success exit code.
}
~~~

If the application needs specific business exit codes, apply `ExitCodeGenerator`, appropriate exceptions, or Spring Boot's exit-code mapping for your version. **An error message in logs is no substitute for the process exit code.**

## 7. Why both SpringApplication.exit and System.exit are needed

A `NONE` application can **exit on its own** when no non-daemon threads remain and the context does not keep the process alive. However, relying solely on the JVM exiting naturally can behave inconsistently once schedulers, executors, connection pools, or new libraries are added.

The two calls handle two different responsibilities:

| Call | Primary effect | What it does not guarantee alone |
|---|---|---|
| `SpringApplication.exit(context)` | Closes the Spring context and computes the exit code via Spring Boot's mechanism | That the JVM definitely terminates immediately |
| `System.exit(code)` | Requests the JVM to terminate with the code passed to the OS | That all background work/transactions have completed |
| `Runtime.getRuntime().halt(code)` | Halts the JVM while bypassing normal shutdown sequences | Cleanup, flushing, or `TaskRepository` end metadata |

For CLI tasks, the `System.exit(SpringApplication.exit(context))` pattern is usually appropriate because schedulers require an **observable exit status**. Never call `System.exit(0)` from the middle of a business service, as it can cut off transactions, listeners, futures, and teardown logic. Only place exit logic in the entrypoint layer after the runner actually finishes.

Spring Boot typically registers a JVM shutdown hook to close the context during controlled shutdowns. **`SIGKILL`, JVM crashes, `OOMKill`, or host loss do not guarantee hooks/callbacks run**, so `TaskExecution` might never be finalized. Never put the sole responsibility for recording business outcomes inside `@PreDestroy` or a shutdown hook.

## 8. Which features remain available without an HTTP endpoint?

`WebApplicationType.NONE` **does not disable** the rest of Spring Boot:

| Feature | Available in non-web mode? | Notes |
|---|---|---|
| Dependency Injection/`@Bean`/`@Service` | Yes | Normal Spring context |
| `@Transactional` with DataSource | Yes | Requires an appropriate transaction manager |
| Spring Cloud Task / `TaskRepository` | Yes | Requires matching dependencies and repository |
| Spring Batch Job/Step | Yes | Used for checkpointed work |
| Outgoing HTTP/`RestClient`/`WebClient` | Yes | Outbound calls do not need an embedded server |
| Messaging clients, object storage SDKs | Yes | Enforce timeouts and close resources |
| Logs, structured tracing, internal metrics | Yes | Export/collect via mechanisms that do not need inbound HTTP |
| `@RestController` serving requests | **No** as a web server | No active inbound endpoint |
| `/actuator/health` over HTTP | **No** in NONE mode | No web server to serve HTTP |
| `server.port` | Not the primary choice | Do not use port config as a substitute for `NONE` |

Non-web does not mean **offline**: the task can still open outbound connections to databases/APIs/brokers and still requires network policies, certificates, secrets, retries, and timeouts.

### What if an HTTP status endpoint is truly required?

If the requirement is "external callers must query `GET /health` while processing runs", consider:

- Using **an orchestrator web service** with HTTP endpoints solely responsible for receiving requests and launching the task.
- Keeping **the task worker non-web**; observe it via `TaskRepository`, Kubernetes Jobs, logs, and metrics/traces pushed to a collector.
- If the same JVM absolutely must serve HTTP, treat it explicitly as a hybrid architecture and clearly design when the server shuts down, how graceful shutdown works, and how Job status is exposed; do not treat it automatically as a standard finite task.

For short-lived batch jobs, HTTP readiness/liveness probes rarely deliver the same value as on long-running servers; overly strict probes can kill a task mid-heavy processing.

## 9. Background threads that can keep the JVM alive without a web server

Enabling `NONE` only removes the embedded web server; it **does not automatically stop every background thread**.

Example of a buggy runner:

~~~java
@Bean
ApplicationRunner badRunner(ReportService service) {
    return args -> {
        new Thread(service::generateReport, "report-thread").start();

        // Runner returns before the report actually finishes.
    };
}
~~~

With a non-daemon thread, the process may stay alive; with a daemon thread, work may be aborted mid-flight when the JVM exits. Neither provides a completion guarantee.

Background work sources that require special inspection:

- `@Async`, `TaskExecutor`, `ExecutorService`, or `CompletableFuture`.
- Continuous `@Scheduled` tasks or a scheduler that is never shut down.
- Listeners with message/broker polling loops holding open connections.
- Infinite work consumers or polling loops without a stop condition.
- Async Spring Batch `JobLauncher` or jobs remaining in `STARTING/STARTED`.
- Manually managed threads that are not joined/closed.

### Pattern for awaiting all required work

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

void processPartitions(
        List<Integer> partitions,
        Executor executor,
        PartitionService service) {

    CompletableFuture<?>[] futures = partitions.stream()
        .map(partition -> CompletableFuture.runAsync(
            () -> service.process(partition), executor))
        .toArray(CompletableFuture[]::new);

    // A failure from any partition propagates back to the caller.
    CompletableFuture.allOf(futures).join();
}
~~~

Manage executor lifecycle and pool bounds carefully. `join()` waits for futures to finish but does not enforce a deadline on its own; combine it with timeouts and cancellation per policy while avoiding threads hanging indefinitely on I/O. If `join()` throws `CompletionException`, do not swallow it and report success.

**Completion checks belong in the business/runner layer**, not in cleanup hooks or merely checking "work was submitted to the executor".

## 10. Spring Cloud Task + Spring Batch in a non-web application

Spring Batch also fits non-web processes well. A scheduled Job runner normally needs no HTTP endpoints to manage individual Steps. However, avoid **launching the Job twice**:

- Spring Boot has an auto-launch mechanism for Jobs at startup.
- The application might also call `JobLauncher` manually inside `ApplicationRunner`.
- Using both can launch the Job twice or fail because the `JobInstance` has already run/completed.

When orchestrating explicitly from the runner, configure:

~~~yaml
spring:
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
~~~

The runner parses parameters, constructs identifying `JobParameters`, invokes the Job, and **inspects the terminal `JobExecution` state** instead of assuming returning from the launcher means the Job succeeded. If `JobLauncher` is asynchronous, wait/poll until completion with a proper timeout.

When using Spring Boot auto-launch, depending on the version, Spring Cloud Task Batch may support:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

This property propagates a failed Job outcome into the task exit code via the integration mechanism. Verify dependencies/versions and test both success and failure paths.

Note: Spring Batch's `JobRepository` and Spring Cloud Task's `TaskRepository` **do not replace each other**. They may share a DataSource or reside in separate schemas, but must be configured consistently with migrations applied before the Job runs.

## 11. Configuring DataSource and TaskRepository for real deployments

Non-web only describes how the `ApplicationContext` is created. When you need to track task results **across runs and restarts**, metadata must be stored in an appropriate persistent store.

PostgreSQL configuration example using environment variables:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      name: daily-close-task
~~~

The three placeholders `${TASK_DB_URL}`, `${TASK_DB_USER}`, and `${TASK_DB_PASSWORD}` use standard Spring property placeholder syntax. At runtime, matching environment variables and database permissions must be present.

Mandatory steps for production:

1. Select compatible Spring Boot, Spring Cloud Task, and JDBC driver versions.
2. Create `TaskRepository` tables/sequences via migrations/schemas matching the exact **dialect and version**.
3. Grant the runtime account least-privilege permissions; avoid granting unnecessary DDL privileges to the task user.
4. Size connection settings, timeouts, and pool limits for the maximum concurrent tasks.
5. Verify both success and failure runs create a `TaskExecution` with expected name, start/end times, and exit code.
6. Protect credentials with Secrets/secret managers, and never log full arguments or environment variables.

If 10 Pods run concurrently and each opens a pool of 10 connections, the system can open around 100 connections from those tasks alone. Cap pool size and concurrency according to database capacity.

**Do not rely on `TaskExecution` to enforce idempotency:** every retry can generate a new ID. For daily revenue closing, enforce a unique business key such as `(tenant_id, business_date, revision)` in the target result table and check before emitting external side effects.

## 12. Packaging a non-web app into a JAR and Docker image

### Running the JAR directly

~~~bash
java -jar daily-close-task.jar --date=2026-11-23
~~~

Upon completion, inspect the **exit code** from the shell:

~~~bash
# Bash / sh after java exits:
echo $?
~~~

On PowerShell:

~~~powershell
java -jar daily-close-task.jar --date=2026-11-23
$LASTEXITCODE
~~~

By convention, a successful task returns 0; non-zero codes signal failure to the scheduler. Do not assume every exception automatically maps to a specific exit code unless configured and tested.

### Minimal Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/daily-close-task.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

The image and JAR path are illustrative; pick a Java version matching your Spring Boot release, run a build pipeline to package the JAR, scan for vulnerabilities, and configure a non-privileged user.

**Exec form for `ENTRYPOINT` matters**: the JVM receives signals directly instead of through a shell wrapper that may not forward signals. If a shell script is unavoidable, use `exec java -jar ...` as the final step and handle signals properly. Avoid `java -jar ... &` leaving the parent shell as PID 1 without waiting/exit management.

Neither `EXPOSE 8080` nor a Service/Ingress is needed just to run a non-HTTP Job. The container still needs outbound network access to the database/APIs as required.

## 13. Kubernetes Job: a better fit than a server Deployment

For finite tasks, a **Kubernetes Job** is generally a better workload type than a `Deployment`. The Job controller tracks completion and can spin up replacement Pods when needed. A `Deployment` expects long-lived replicas; when a process exits with 0, the platform tries to keep the Pod running, causing unwanted repeated runs.

One-off Job example:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-close-20261123
spec:
  backoffLimit: 2
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 45
      containers:
        - name: daily-close-task
          image: registry.example.org/finance/daily-close-task:1.0.0
          args:
            - "--date=2026-11-23"
          env:
            - name: SPRING_MAIN_WEB_APPLICATION_TYPE
              value: "none"
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: password
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              cpu: "1"
              memory: "768Mi"
~~~

The example assumes Kubernetes Secret `daily-close-db` already exists with those keys and the image can be pulled from the registry; this manifest does not create the Secret itself.

Key fields:

| Field | Meaning | Notes |
|---|---|---|
| `restartPolicy: Never` | A failed container fails the Pod; the Job can spawn a new Pod | Makes inspecting failed Pods easier |
| `backoffLimit: 2` | Limits failure retries managed by the Job controller | Each retry can create a new `TaskExecution` and repeat business side effects |
| `activeDeadlineSeconds: 1800` | Total active runtime limit for the Job | Beyond the deadline, the Job fails even if retries remain |
| `terminationGracePeriodSeconds: 45` | Window for graceful shutdown before forced kill | Does not guarantee the worker always gets a full 45 seconds |
| `ttlSecondsAfterFinished` | Cleans up the Job/Pods after completion via the TTL controller | Persist logs/metadata externally before cleanup |
| `resources.requests/limits` | Reserves and caps CPU/RAM | Size appropriately for JVM heap and native memory |

Kubernetes can launch **the same program multiple times**, and in edge cases even run overlapping Pods within a single Job. Thus, applications must enforce **idempotency and concurrency safety**; `parallelism=1` or `backoffLimit` alone do not replace business locks.

### Monitoring the Job with kubectl

~~~bash
kubectl get job daily-close-20261123
kubectl describe job daily-close-20261123
kubectl get pods -l job-name=daily-close-20261123
kubectl logs job/daily-close-20261123
~~~

Selector labels can differ across versions/controllers; check actual labels when querying. `kubectl logs job/...` usually fetches logs for the Job when supported. `TaskRepository` should still be queried for internal execution records and recorded exit codes.

## 14. Recurring schedules: CronJob while keeping the app non-web

A **Kubernetes CronJob** creates a new Job on a schedule. Each Job runs the non-web application and exits instead of keeping a 24/7 web server running.

Basic structure example:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-close
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: daily-close-task
              image: registry.example.org/finance/daily-close-task:1.0.0
              args:
                - "--mode=previous-business-day"
~~~

The illustrative manifest assumes the application understands `--mode=previous-business-day` and computes the business date using an agreed timezone. Setting `timeZone` on the CronJob **does not automatically turn every Java `LocalDate.now()` into a date in that timezone**; the runtime must still resolve the timezone/processing date explicitly.

`concurrencyPolicy: Forbid` prevents overlapping Jobs triggered by **the same CronJob**; it does not block manual runs, another CronJob, or external systems triggering the same business key. Nor does it guarantee exactly-once delivery: schedules can be missed or double-triggered under certain failure modes. Continue enforcing unique business keys and idempotency.

**Distinction:** CronJob **schedules**, Kubernetes Job **orchestrates one run**, Spring Cloud Task **records JVM task metadata**, and the business service **persists actual results**. All four layers have distinct responsibilities.

## 15. Observing an application without an HTTP port

Not having `/actuator/health` over HTTP does not mean the app is unobservable. For finite Jobs, rely on appropriate observability sources:

| Source | Question answered |
|---|---|
| Process/container exit code | Did the technical execution succeed or fail per policy? |
| Kubernetes Job/Pod status | Could a Pod be created, were there retries/OOMKills/deadlines? |
| Structured logs | `TaskExecution` ID, business key, root error, processing duration? |
| Spring Cloud `TaskRepository` | Which runs started/finished, exit code, exit message? |
| Spring Batch `JobRepository` (if present) | Which Job/Step failed, where did checkpoint/restart stop? |
| Business database/output | Were results actually committed, and are there duplicates? |
| Outbound telemetry | Were traces/metrics exported to a collector via an appropriate protocol? |

For short-lived tasks, **metrics may need to be pushed/flushed before the process exits**. Do not place all observability exclusively behind a pull-style Prometheus endpoint like `/actuator/prometheus` when no web server is running; the collector might never scrape in time.

A useful logging convention:

~~~text
task.started taskName=daily-close taskExecutionId=418 businessDate=2026-11-23
task.completed taskExecutionId=418 businessDate=2026-11-23 result=APPLIED
~~~

This is a **recommended** log format, not default output. Never print passwords, tokens, sensitive payloads, or entire argument lists to logs.

### TaskRepository state can diverge from Pod state

When a process dies after committing data but before writing `END_TIME` metadata, you may observe:

- Pod marked Failed or OOMKilled.
- `TaskExecution` missing `END_TIME`.
- Business result already fully committed.

Do not manually edit `TaskRepository` or rerun blindly. Inspect the output and idempotency keys before letting a Job retry.

## 16. Common design and configuration mistakes

| Symptom | Common cause | Remedy |
|---|---|---|
| Runner finishes but Pod stays Running | Embedded web server, scheduler, or non-daemon thread keeps JVM alive | Set `NONE`, remove unneeded web starters, manage executors/context |
| Log shows "Tomcat started on port ..." | Boot is running in `SERVLET` mode | Check classpath, active profiles, and whether `spring.main.web-application-type` took effect |
| `server.port=-1` yet web context still starts | Mode was not switched to `NONE` | Use `spring.main.web-application-type=none` |
| `@RestController` does not accept requests | Application is configured with `NONE` | Split the orchestration API into a dedicated web service |
| `/actuator/health` is unreachable | No HTTP server running | Observe via process/Job/TaskRepository or a separate control plane |
| Exit code is 0 despite business failure | Runner catches and swallows exceptions, or async work unfinished | Let errors propagate, await futures, map exit codes |
| Job shows Completed but output is missing | Background work submitted without awaiting completion | Define a clear business completion point and commit |
| Job reruns endlessly | Deployment used instead of Job, or improper restart policy | Use Kubernetes Job/CronJob and control backoff |
| `TaskRepository` has no records | Wrong DataSource/schema or JVM died too early | Check migrations, connectivity, logs, and Job status |
| Multiple `TaskExecution` rows for the same date | Scheduler/Job retried the same intent | Enforce unique business keys, idempotency, and concurrency limits |
| OOMKilled even without a web server | Heap, native memory, batch size, or concurrency too large | Reduce memory footprint, tune JVM/container limits |
| `@Scheduled` keeps the task running forever | Worker accidentally configured with an internal endless schedule | Let an external CronJob/scheduler trigger finite processes |
| Liveness probe restarts the task | Web-service health probes applied to a batch task | Use Job status and deadlines; probes must match task lifecycle |
| `SIGTERM` fails to clean up | Shell entrypoint does not forward signals or grace period expired | Use exec-form `ENTRYPOINT`, bound shutdown time |
| Date parameter shifted by timezone | Date computed using a default clock differing from the scheduler | Explicitly pass/resolve timezone, snapshot, and business date |

### Verifying no HTTP server empirically

Do not just read YAML; verify the **effective configuration at runtime**. In a test environment:

1. Run the JAR with `--spring.main.web-application-type=none`.
2. Inspect logs: verify no server startup or port-binding messages appear.
3. Verify the process is not listening on any unintended HTTP ports.
4. Confirm the runner executes its work and the process exits with the expected code.
5. Inspect `TaskExecution` after the run and verify committed business data.

Do not treat `curl localhost:8080` failing as sufficient proof on its own: the app might have bound a different port or left background threads alive; always inspect the process and active sockets.

## 17. Deployment choices by product requirement

| Requirement | Recommended architecture |
|---|---|
| Scheduled file import and exit | Non-web Spring Cloud Task + CronJob/Kubernetes Job |
| On-demand execution from UI | Orchestrator web API + non-web task launched via scheduler/SCDF/TaskLauncher |
| Multi-step processing with checkpoints | Non-web Spring Cloud Task + Spring Batch |
| Retrying after infrastructure errors | Job/CronJob with backoff + business idempotency |
| Continuous HTTP request serving | Separate web service; do not force a finite task to be a server |
| Unbounded message-processing worker | Long-lived service/consumer or specialized worker; do not mismodel as a one-off task |
| Environment already using Spring Cloud Data Flow | Register non-web task app, launch with arguments/properties/deployer, monitor executions |
| Audit trail across many runs | Persistent `TaskRepository` paired with structured logs and retention policy |
| Internal "is it alive" visibility | Process/Job status, appropriate heartbeats/metrics; HTTP liveness endpoint not necessarily required |

A task is usually deployed **non-web when its deliverable is a data outcome or completed side effect**, rather than an API endpoint serving ongoing requests.

## 18. Checklist before deploying a non-web task to production

- `spring.main.web-application-type=none` is explicitly configured and verified at runtime.
- No unnecessary web-server dependencies are pulled in; even if present, no server starts automatically.
- `ApplicationRunner`/`CommandLineRunner` defines a genuine completion point, not fire-and-forget.
- JVM exit codes accurately reflect success/failure; exceptions are never swallowed.
- Context/executor shutdown and graceful shutdown with deadlines are implemented.
- `TaskRepository` uses a DataSource/schema with applied migrations, least-privilege permissions, and bounded pooling.
- Business keys/idempotency guard against retries, backfills, or concurrent execution.
- If using Spring Batch, auto-launch vs. custom launcher is clearly chosen, and `JobExecution` is inspected.
- Containers use exec-form entrypoints; Kubernetes Job/CronJob is used instead of Deployment where appropriate.
- `backoffLimit`, `activeDeadlineSeconds`, CPU/RAM, and retention fit the workload.
- No secrets are placed in CLI arguments, `TaskExecution` args, or logs.
- An observability plan exists that does not depend on inbound HTTP endpoints.
- Tested success runs, business failures, OOM/timeouts, `SIGTERM`/`SIGKILL`, and retries.
- Verified actual business outcomes after crashes rather than trusting `TaskExecution` alone.

**Conclusion:** For finite Spring Cloud Task workloads, **`WebApplicationType.NONE` is the sensible default deployment choice** whenever the app does not serve HTTP. It removes the embedded web server, reduces the risk of inadvertently keeping the JVM alive, and aligns naturally with the Job/CronJob model. Still, **non-web alone does not guarantee clean termination**: the runner must await its work, exceptions must drive exit codes, the context must close, and business writes must be retry-safe. Combining these practices with `TaskRepository` and an orchestrator yields tasks that are observable, recoverable, and reliable in operations.

### References

- [Spring Boot — Disabling the Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — SpringApplication: Web Environment and Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Cloud Task — Reference Guide](https://docs.spring.io/spring-cloud-task/reference/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
