# Reducing Unnecessary Dependencies and Auto-Configuration

## 1. Why Is Startup Optimization Especially Important for Spring Cloud Task?

**Spring Cloud Task** is designed for Spring Boot applications with a **finite execution lifetime**: starting up, receiving parameters, performing work, updating status/results via **TaskRepository**, and terminating. The application may be triggered via command line, a Kubernetes CronJob schedule, an API, or Spring Cloud Data Flow.

For a web service that runs for days, startup overhead usually occurs only during deployment or Pod replacement. For a task that runs for a few minutes or seconds, this overhead can repeat **on every scheduled run**. If an application only needs to read a table, export a report, and exit, yet initializes a web server, JPA, a scheduler, message consumers, and unused thread pools, then startup time, memory usage, and the likelihood of configuration errors can all increase.

Illustrative example, **not default Spring measurements**:

| Component of a Run | Minimal Task | Task with Many Unused Components |
| --- | ---: | ---: |
| JVM and Spring context creation | 1.1 seconds | 4.0 seconds |
| Opening connections and writing metadata | 0.3 seconds | 0.4 seconds |
| Actual business processing | 2.0 seconds | 2.0 seconds |
| Closing resources / termination | 0.2 seconds | 0.6 seconds |
| **Illustrative total** | **3.6 seconds** | **7.0 seconds** |

Here, the business work stays constant while the total duration increases significantly. That is why the **Tuning and Upgrades** chapter needs to study how to **reduce unnecessary dependencies and auto-configuration**.

**Guiding principle:** remove components that do not serve the business logic, **without removing TaskExecution recording, error reporting, transactions, or observability** that the system needs to operate safely.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **dependencies on the classpath** and **Spring Boot auto-configuration**.
2. Identify which starters/libraries are truly needed for CLI tasks, JDBC tasks, Batch-enabled tasks, and infrastructure-integrated tasks.
3. Use Maven/Gradle to analyze the dependency graph and use `--debug` to read the auto-configuration condition evaluation report.
4. Configure an application **without a web server** and eliminate unnecessary component scans, runners, or background threads.
5. Know when you **must not** disable `SimpleTaskAutoConfiguration` or `DataSourceAutoConfiguration`.
6. Measure before/after impact via startup time, exit status, memory, connection count, and `TaskRepository` verification.
7. Upgrade BOM, Java, Boot, Cloud Task, and schemas with verification instead of blindly changing dependencies.

## 2. How Do Dependencies Differ from Auto-Configuration?

A dependency is an **artifact present on the classpath**. Auto-configuration is the Spring Boot mechanism that **creates appropriate beans when conditions are met**: presence of certain classes, properties, presence/absence of other beans, or an infrastructure resource.

~~~mermaid
flowchart TD
    A["pom.xml / build.gradle"] --> B["Runtime classpath"]
    B --> C["Spring Boot auto-configuration"]
    C --> D{"Class/bean/property conditions matched?"}
    D -->|Yes| E["Create infrastructure beans"]
    D -->|No| F["Do not apply that configuration"]
    E --> G["Context creation / connection / thread time"]
    B --> H["Artifact size + version management complexity"]
~~~

These actions have different impacts:

- **Removing a dependency:** can shrink the classpath, image/jar size, number of libraries needing CVE patches, and sometimes prevents the associated auto-configuration from matching its conditions.
- **Disabling an auto-configuration:** prevents Spring Boot from automatically creating a group of beans from classes still on the classpath; it **does not automatically remove the dependency** from the jar.
- **Disabling a feature via a property:** only changes features already defined by the library. Never guess that a property exists based solely on its name.
- **Moving beans to profile/conditional configuration:** keeps the code on the classpath but avoids instantiating those beans when running with the corresponding task profile.

**Example:** setting `spring.main.web-application-type=none` prevents Spring Boot from running with a `WebApplicationContext`/web server, but **does not automatically remove** `spring-boot-starter-web` from the dependency graph. If a task has no need for servlets or web endpoints at all, **remove the web starter** from the build rather than only turning off the web application type.

## 3. Building a Minimal CLI Task Baseline

Consider a daily report processing task: it needs Spring Boot, Spring Cloud Task, a JDBC driver connecting to the PostgreSQL metadata database, and a service that reads/writes data. It does not need an HTTP server, Spring MVC, WebFlux, Kafka, JPA, or Spring Batch when the business logic only uses JDBC directly.

### 3.1. Intentional Maven Dependencies

Example `dependencies` section of `pom.xml`, with Spring Boot and Spring Cloud BOMs already declared **in the appropriate dependency management sections**:

~~~xml
<dependencies>
    <!-- Core of a finite Spring Cloud Task application -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <!-- JDBC when the task actually accesses a database -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- PostgreSQL driver at runtime -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Only needed for the test environment -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is a **POM snippet**, not a standalone `pom.xml`: you must choose compatible Spring Boot/Cloud BOM, Java, and build plugin versions. If the task starter already pulls in a dependency transitively, Maven may unify duplicates; `dependency:tree` is what reveals the actual runtime classpath.

**Do not include the following dependencies just because "a task ought to have them":**

- `spring-boot-starter-web` or `spring-boot-starter-webflux` when there is no need to act as an HTTP server or client respectively.
- `spring-boot-starter-data-jpa` when only executing SQL with `JdbcTemplate`.
- `spring-boot-starter-batch` when the task does not have a Spring Batch `Job`/`Step`.
- `spring-cloud-stream` and broker binders when not receiving/sending messages via Spring Cloud Stream.
- `spring-integration-jdbc` just for the sake of having it; only needed for features actually used, such as single-instance locking depending on version requirements.
- Discovery clients, Config Server, Gateway, tracing exporters, cloud SDKs, and actuator endpoints without a clear operational purpose.

**Do not delete a dependency used by part of the business logic just because you do not see a direct import in code.** Spring Boot auto-configuration, SPI, JDBC drivers, and some providers are discovered via runtime reflection or service loaders; a successful build alone does not prove they are unneeded.

### 3.2. Java Application

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
public class ReportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(ReportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(ReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner(ReportService service) {
        return args -> {
            List<String> values =
                    args.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Required --businessDate=yyyy-MM-dd");
            }
            LocalDate day = LocalDate.parse(values.get(0));

            service.generate(day); // Synchronous; does not return early.
            log.info("REPORT_COMPLETED businessDate={}", day);
        };
    }
}
~~~

`ReportService` is a business Spring bean that you must implement. The code does not need `@RestController`, embedded Tomcat, or a message consumer. If `service.generate(...)` fails, let the exception propagate through the proper error mechanism; **do not swallow exceptions and report a false success**.

### 3.3. Minimal Configuration

~~~yaml
spring:
  main:
    web-application-type: none
    lazy-initialization: false
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/task_metadata
    username: task_writer
    # Password comes from an environment secret, not stored in Git.
  cloud:
    task:
      name: report-task
      initialize-enabled: false
      closecontextEnabled: true
~~~

Here:

- `web-application-type: none` asserts that this is a CLI task that does not serve HTTP.
- `lazy-initialization: false` enforces **explicit/fail-fast initialization of required beans**; do not enable lazy initialization just to make startup numbers look lower.
- `initialize-enabled: false` is appropriate when the TaskRepository schema **has already been created via migrations**. Against an empty DB, this setting can cause the application to fail due to missing tables.
- `closecontextEnabled: true` supports closing the context after the runner completes and final metadata is updated, which is useful if the application has executor/thread beans requiring cleanup. For `@SpringBootTest` tests that need to keep the context alive for assertions, this can be set to `false` in the test profile.
- The DB URL/username are illustrative only, not real credentials. Use a secret manager and grant minimal SQL privileges.

**Do not disable JDBC/DataSource when the goal is still to store TaskExecution history in a database.** A task that executes business logic but cannot write to a persistent repository can lose traceability and safe retry capability.

## 4. Inspecting the Dependency Graph Before Removing Anything

### 4.1. Maven

To see which dependency pulls in other libraries:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
mvn help:effective-pom
~~~

For example, to find out why Web MVC appears in a CLI task:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

`-Dverbose` can provide additional details about conflicted or omitted dependencies depending on the tool/plugin version. You need to inspect **the full runtime tree**, not just direct dependency declarations. If an integration starter accidentally pulls in Spring MVC, examine why it requires that starter before adding Maven `exclusions`.

### 4.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-data-jpa --configuration runtimeClasspath
~~~

On Windows, use `gradlew.bat` or the corresponding wrapper. Do not run Gradle/Maven solely to verify a Markdown file; the commands above are **practice exercises for learners**.

### 4.3. Decision Process for Removing a Dependency

~~~mermaid
flowchart TD
    A["Spot an unwanted library"] --> B["Trace the transitive dependency path"]
    B --> C{"Needed by business logic / runtime SPI?"}
    C -->|Yes| D["Keep it, verify version and config"]
    C -->|No| E["Remove direct dependency or exclude transitive branch"]
    E --> F["Build + run Task against real DB/schema"]
    F --> G{"Metadata, exit code, data correct?"}
    G -->|Yes| H["Measure startup/memory and record results"]
    G -->|No| I["Revert and investigate before further changes"]
~~~

**Priority order:** remove an unnecessary direct starter first, and only then consider transitive `exclusions`. Excluding an artifact officially relied upon by a starter without understanding why can break auto-configuration or cause runtime failures in production.

Conceptual before/after example:

~~~text
Before:
  spring-cloud-starter-task
  spring-boot-starter-jdbc
  spring-boot-starter-web       <- task does not open an HTTP server
  spring-boot-starter-data-jpa  <- only uses JdbcTemplate
  spring-cloud-starter-stream-* <- does not use a message broker

After:
  spring-cloud-starter-task
  spring-boot-starter-jdbc
  postgresql (runtime)
  spring-boot-starter-test (test)
~~~

Do not conclude that removed libraries are never needed in any application. If a task has internal endpoints, uses ORM, or publishes events through a broker, those may be genuine requirements.

## 5. Reading the Auto-Configuration Report Instead of Guessing

Spring Boot supports the **Condition Evaluation Report** to explain why an auto-configuration was or was not applied.

Run the application in a test environment:

~~~bash
java -jar target/report-task.jar \
  --debug \
  --businessDate=2026-11-23
~~~

`--debug` enables diagnostic logging, which includes the auto-configuration condition evaluation report. Some configurations can also be inspected via the **Spring Boot Actuator `conditions` endpoint** when Actuator is installed and the endpoint is enabled.

**Do not** add Actuator/a web server merely to view the condition report in a CLI task if `--debug` or startup inspection is sufficient. If using endpoints in a real environment, you must manage exposure/security; never expose diagnostic endpoints publicly.

### Reading the Report by Question

| Signal in the Report | Possible Meaning | Next Step |
| --- | --- | --- |
| `DataSourceAutoConfiguration` matched | JDBC/DataSource conditions are met | **Keep** if TaskRepository/Batch/SQL needs a DB |
| Web server auto-config matched | Web classpath and web application type allow it | Does the task need HTTP? If not, remove the web starter and set `none` |
| JPA/Hibernate auto-config matched | JPA/Hibernate and data conditions present | Does the task have entities/ORM? If not, consider removing the JPA starter |
| Batch auto-config matched | Spring Batch and matching conditions present | Does the task have a Job/Step? Is a job auto-running unexpectedly? |
| Message/Integration auto-config matched | Matching library or binding present | Are brokers, channels, or scheduled pollers used? |
| Auto-config did not match | Conditions were not met | Do not assume it is an error; it may be expected because the feature is unused |

**A single "positive match" line does not prove many expensive beans were created.** Combine it with bean counts, startup logs, external connections, and actual measurements. Conversely, a bean created by your own `@Configuration`/`@ComponentScan` can add overhead even though it does not appear in the auto-configuration report.

## 6. When Is It Safe to Disable Auto-Configuration?

Spring Boot supports excluding a specific auto-configuration via:

- The `spring.autoconfigure.exclude` property.
- `@SpringBootApplication(exclude = ...)` when the auto-config class is actually on the classpath.
- `@SpringBootApplication(excludeName = "...")` when excluding by name.

This is a **deliberate tool**, not an optimization step to apply blindly to every task. Across Spring Boot 3 and 4, packages of some auto-config classes can change: **you must look up the exact fully qualified class name for the version you are building**.

### 6.1. Be Careful with DataSourceAutoConfiguration

Syntax example (Boot 3.x line; do not copy the class import to Boot 4 if the package changed):

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

// ONLY FOR APPLICATIONS THAT TRULY DO NOT NEED A DATASOURCE.
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class NoDatabaseApplication {
}
~~~

**Do not use this to "optimize" a Spring Cloud Task that still needs to record `TaskExecution` into a JDBC TaskRepository.** Disabling default DataSource configuration can cause the application to fail or pick a different repository mechanism, violating database execution-tracking requirements.

If a task has multiple DataSources, the right approach may be explicitly configuring `TaskConfigurer`/transaction managers, **not** disabling JDBC altogether and hoping the framework finds the right database.

### 6.2. Disabling Spring Cloud Task Auto-Configuration Is a Functional Change

Spring Cloud Task documentation supports:

~~~properties
spring.cloud.task.autoconfiguration.enabled=false
~~~

Or excluding `SimpleTaskAutoConfiguration` via annotation depending on the version branch.

**However, this is not a harmless speedup trick.** If you disable Spring Cloud Task auto-configuration, the application may **no longer automatically create/record TaskExecution across the lifecycle**, causing TaskRepository, TaskExplorer, Spring Cloud Data Flow, or operations systems to lose the history they expect.

| Scenario | Should Task Auto-Config Be Disabled? |
| --- | --- |
| Application must record start/end/exit code in `TaskRepository` | **No** |
| Task is orchestrated by SCDF and needs history displayed | **No**, unless a verified replacement mechanism exists |
| You built a custom lifecycle/repository, do not need automatic behavior, and have tests confirming it | Can be considered |
| You just want startup "200 ms faster" without measuring impact | **No** |

**Important distinction:** the property `spring.cloud.task.autoconfiguration.enabled=false` disables **Task auto-configuration**; `spring.main.web-application-type=none` only changes **the web application type**. They are not equivalent.

### 6.3. Batch Auto-Run Can Be an Unwanted Side Effect

When `spring-boot-starter-batch` is present, Spring Boot can automatically launch a single `Job` if the corresponding conditions are satisfied. If the task already uses an `ApplicationRunner` to invoke `JobLauncher` manually, **letting both mechanisms run** risks launching the Batch Job twice.

This can be controlled with:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

**Only use this when the application actually launches the Job through its own mechanism.** If you expect Boot to run the Batch job automatically, setting `enabled: false` will prevent the Job from auto-launching. If the task does not use Batch at all, it is best **not to include the Batch starter**.

### 6.4. Lazy Initialization Does Not Replace Architectural Optimization

Spring Boot supports:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Lazy initialization can make **apparent startup time shorter** because some beans are created on demand, but:

- Configuration errors may only surface when business logic runs.
- Bean creation cost still exists and moves onto the execution path.
- For a CLI task where most beans are used immediately inside the runner, total time until work finishes **may not decrease**.
- Some lifecycle/listener components need to initialize at the right time, so you must verify with integration tests.

Optimize **the end-to-end task duration**, not just the "Started application" log line.

## 7. Reducing Self-Created Work in @Configuration and Component Scan

Not all startup overhead comes from starters. Many applications reuse a large root package containing web controllers, scheduled jobs, stream consumers, SDK clients, and startup-check beans.

### 7.1. Splitting Modules or Configuring by Profile

Example of separating configuration at the bean level:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("task")
class TaskOnlyConfiguration {

    @Bean
    ReportService reportService(ReportRepository repository) {
        return new ReportService(repository);
    }
}
~~~

This configuration illustrates a **design approach**, requiring actual `ReportService` and `ReportRepository` classes in the project. The `task` profile avoids instantiating beans only needed in `web` or `stream` profiles. However, **profiles do not remove libraries from the classpath**: if you want to reduce image size, split build modules or remove unused starters.

Options:

| Approach | What It Can Reduce | Limitations |
| --- | --- | --- |
| Split `task-app` module from `web-app` | Classpath, component scan, unused dependencies | Requires managing shared code and releases |
| `@Profile("task")` / `@ConditionalOnProperty` | Number of beans created in a single run | Libraries still remain inside the artifact |
| Narrow component scan packages | Out-of-scope beans/services being scanned | Can miss required beans if package layout is poor |
| `@Configuration(proxyBeanMethods=false)` where appropriate | Proxy overhead between `@Bean` methods | Does not change dependency graph; unsuitable if code invokes `@Bean` methods directly for singleton semantics |
| Remove unused listeners/schedulers/broker clients | Threads, network connections, bean initialization | May lose monitoring if a needed feature is removed by mistake |

**Do not** scatter `@ComponentScan(excludeFilters=...)` everywhere to paper over an unclear package architecture. Prefer splitting application modules by function: separate CLI task, separate HTTP service, separate batch worker.

### 7.2. Do Not Leave Background Threads Alive After the Runner Finishes

If a runner calls `ExecutorService.submit(...)` and returns without waiting for the result, Spring Cloud Task can record **early completion** even though work is still running. If the thread pool is not shut down, the JVM can also stay alive even after SpringApplication has finished.

~~~java
// Wrong example in a finite task:
@Bean
ApplicationRunner wrongRunner(ExecutorService pool) {
    return args -> {
        pool.submit(() -> doImportantWork());
        // Returns immediately: TaskExecution may end before business work finishes.
    };
}
~~~

The proper design is to wait for business results and clean up resources in a controlled manner:

~~~java
// Pseudocode: executor and shutdown are explicitly managed.
Future<?> result = pool.submit(() -> doImportantWork());
result.get(); // Waits for the result; exceptions are propagated.
~~~

Depending on the design, use a Spring-managed `ThreadPoolTaskExecutor` or an `ExecutorService` with `shutdown/awaitTermination` and a deadline. `spring.cloud.task.closecontextEnabled=true` helps close the Spring context; it **does not replace** managing custom threads created outside Spring, and does not turn unfinished background work into success.

## 8. Tuning the DataSource Without Sacrificing Metadata

Spring Cloud Task typically writes a record at start and updates it at completion. If Spring Batch or multiple business operations are used, there are even more connections/transactions.

An oversized pool across hundreds of concurrent tasks can overload the database, while an undersized pool can cause deadlocks or waiting when a task runs multiple concurrent transactions.

Example **only for controlled experimentation**:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      minimum-idle: 0
      connection-timeout: 10000
~~~

The values above are **not default recommendations for every task**. Measure concurrent connections based on the demands of TaskRepository, JobRepository, business DataSources, and worker threads. `minimum-idle=0` can reduce idle connections at the cost of connection-creation latency on first use. If a task only runs for a few seconds, connection establishment latency must also be measured.

### 8.1. DataSource Observation Questions

- Within a single task Pod, what is the peak active connection count?
- When a CronJob spawns multiple Pods, does total connection count exceed PostgreSQL limits?
- Does each task share one database, or are metadata DB and business DB separate?
- Are transaction managers/Batch repositories running in parallel?
- Is connect/TLS handshake time significant relative to business processing?
- Are there connection leaks or pools held open after the task finishes?

**The best optimization** is not always shrinking the pool size to 1; for workloads with Batch, transactions, and concurrent queries, that can increase wait time.

### 8.2. Do Not Treat In-Memory H2 as a Production Startup Optimization

Embedded H2 is useful for **unit/integration tests** and some demos. However, if tasks run on a schedule across multiple Pods and require a persistent TaskRepository, each Pod using its own in-memory H2 will not provide shared history to SCDF/the scheduler and will lose data when the process exits.

Never trade away observability, restartability, and failure diagnostics just because H2 starts faster in a small example.

## 9. Measuring Properly: Startup, End-to-End, Memory, and Outcomes

To prove a change is worth keeping, you need **before** and **after** baselines with the same workload, machine, database, image layers, and run count.

### 9.1. Metrics to Measure

| Metric | How to Read It | Why Is It Needed? |
| --- | --- | --- |
| **Wall-clock from launch to exit** | CI, scheduler, or timing commands | Includes startup, business logic, and shutdown |
| **Spring context startup** | Boot logs, `ApplicationReadyEvent.getTimeTaken()` on supported versions | Separates bootstrap from business duration |
| **TaskExecution start/end duration** | `TASK_EXECUTION.START_TIME`/`END_TIME` | Framework state, does not always include full JVM time |
| **Peak memory/RSS** | Kubernetes metrics or process monitor | Verifies real footprint reduction |
| **Container image/jar size** | Build manifest/registry/file size tools | Shows effect of removing dependencies |
| **JDBC connection count** | Pool metrics/DB monitoring | Controls DB load across many tasks |
| **Exit code and errors** | OS/Pod + `TaskRepository` | Ensures failure behavior did not change |
| **Business results** | SQL, checksums, object storage | Catches "faster because it did less work" bugs |

### 9.2. Java Startup Measurement Example

You can log Spring Boot startup time when the application publishes `ApplicationReadyEvent`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupTimingListener {

    private static final Logger log =
            LoggerFactory.getLogger(StartupTimingListener.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        if (event.getTimeTaken() != null) {
            log.info("SPRING_READY durationMs={}",
                    event.getTimeTaken().toMillis());
        }
    }
}
~~~

`ApplicationReadyEvent` is published **after runners complete**, so `getTimeTaken()` is not "pure bean creation time." It covers application startup up to the ready state per Spring Boot, which can include runner execution time. If finer breakdown is needed, use **ApplicationStartup/FlightRecorderApplicationStartup** and matching profiling tools, or place controlled custom timestamps.

### 9.3. Process-Level Measurement Examples

Linux/macOS:

~~~bash
/usr/bin/time -p java -jar target/report-task.jar \
  --businessDate=2026-11-23
~~~

Windows PowerShell:

~~~powershell
Measure-Command {
    java -jar target/report-task.jar --businessDate=2026-11-23
}
~~~

The PowerShell command above measures duration, but to check the **exit code**, you must read `$LASTEXITCODE` right after the Java command in an appropriate workflow; never treat timing numbers as proof that the task succeeded.

For a fair comparison:

1. Run warm-ups and multiple repetitions.
2. Use **the same volume** of business workload and an equivalent DB state.
3. Separate cold starts (image pull, fresh JVM, new DB connection) from warm starts.
4. Report median/p95, rather than picking the single fastest run to draw conclusions.
5. Check exit code, processed record counts, and `TaskRepository` on **every measurement**.
6. Measure scheduler/Kubernetes Pod creation wait separately, since Java dependency changes do not fix all infrastructure latency.

## 10. Verifying TaskRepository After Optimization

If after removing dependencies/auto-config the CLI still prints "Done", that is not enough to consider the optimization safe. You must prove the framework still records metadata.

### 10.1. Checking Start and End Metadata

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'report-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Expected for a successful run:

- A new `TASK_EXECUTION_ID` is created; do not hardcode the first ID.
- `START_TIME` and `END_TIME` are recorded once the lifecycle completes.
- `EXIT_CODE` matches the normal success path (usually 0).
- Business output is completely written, not just a success log line.

Expected for a failed runner:

- If TaskExecution was already created and the framework could handle the failure event, the record should reflect the error/non-zero exit code via the appropriate mechanism.
- If **ApplicationContext bootstrap fails too early**, TaskExecution existence is not guaranteed; check startup logs/OS status.
- If the process is killed with SIGKILL or OOMKilled, a final `END_TIME` may be missing.

### 10.2. TaskExplorer in Integration Tests

A Spring Boot integration test can use `TaskExplorer` to query history:

~~~java
TaskExecution latest =
        taskExplorer.getLatestTaskExecutionForTaskName("report-task");

assertThat(latest).isNotNull();
assertThat(latest.getStartTime()).isNotNull();
assertThat(latest.getEndTime()).isNotNull();
assertThat(latest.getExitCode()).isEqualTo(0);
~~~

This is an **illustrative assertion snippet** inside a test that already has `taskExplorer` and assertion libraries; real tests must initialize the Spring context and proper DataSource/schema, isolating test data so it does not pick up an execution from another run.

### 10.3. Spring Batch When Jobs/Steps Are Present

If `JobRepository`, `StepExecution`, checkpoints, and chunk/restart are needed, **you must not** remove Batch just to reduce startup. Also check its metadata:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

A failed Batch Job may need to map to the task/process exit code per the `spring.cloud.task.batch.fail-on-job-failure` setting in supported versions. This is **correctness**, not optional overhead that can be stripped out.

## 11. Version Upgrades: Lean Dependencies Still Must Be Compatible

When upgrading, many applications update just a single starter version and then hit `NoSuchMethodError`, duplicate beans, missing auto-config classes, or `relation TASK_EXECUTION does not exist`. The cause may lie in **the entire version set** rather than a single library.

### 11.1. Lock Down the Matrix Before Making Changes

| Component | What to Record |
| --- | --- |
| **Java runtime** | Java version supported by Spring Boot/Cloud Task |
| **Spring Boot BOM** | Boot version, auto-config model, classpath, and JDBC |
| **Spring Cloud release train** | BOM compatible with Boot |
| **Spring Cloud Task** | Task version, properties, and TaskRepository schema |
| **Spring Batch** | Batch version if using jobs/steps and `BATCH_*` schema |
| **JDBC driver + Database** | Driver version, server, dialect/transactions |
| **Deployer/SCDF** | If launched remotely, artifact/task metadata contract |
| **Container image + plugins** | JVM base image, AOT/native build, dependency packaging |

**Do not mix and match arbitrary Boot 3/Boot 4, Batch 5/Batch 6, and Cloud Task releases.** Pick a published compatible BOM set and verify APIs/DDL against the actual release.

### 11.2. Breaking Upgrades into Observable Steps

~~~mermaid
flowchart TD
    A["Inventory BOM, dependencies, schema"] --> B["Baseline startup + correctness measurements"]
    B --> C["Remove unused dependencies one group at a time"]
    C --> D["Check auto-config + integration tests"]
    D --> E{"PASS?"}
    E -->|No| F["Rollback the change just made"]
    E -->|Yes| G["Measure before/after"]
    G --> H["Upgrade Boot/Cloud/Task via compatible BOM"]
    H --> I["Schema migration on staging + real DB tests"]
    I --> J["Smoke test jar/Job/Kubernetes"]
    J --> K{"Results and exit code correct?"}
    K -->|No| F
    K -->|Yes| L["Deploy per plan + monitor"]
~~~

**Do not simultaneously** swap libraries, change schemas, switch from H2 to PostgreSQL, and change the launch mechanism; when something breaks, it becomes hard to tell what caused it. Always take backups and test restores before migrations, and determine whether running Jobs/Tasks are allowed to stop or restart.

### 11.3. Auto-Configuration Changes During Upgrades

An auto-config class previously excluded by name in Boot 3 may **change packages** in Boot 4 or no longer need exclusion. If `spring.autoconfigure.exclude` contains a class name that is no longer recognized as an auto-configuration, the application can fail on startup.

How to handle it:

1. Review the **Condition Evaluation Report** on the new version.
2. Inspect the dependency tree and any split/renamed modules.
3. Audit existing exclusions; remove exclusions that are no longer applicable.
4. Check custom bean overrides and `@ConditionalOnMissingBean` interactions.
5. Run integration tests for TaskRepository, runners, and exit codes.
6. Run smoke tests against a real database/schema and container image.

**Do not treat nested internal classes inside auto-configurations as a stable public API.** Spring Boot supports auto-config class names for exclusion, not guarantees on their internal structure across releases.

## 12. Common Optimization Scenarios

| Scenario | What You Should Do | What You Should Avoid |
| --- | --- | --- |
| CLI task accidentally includes Tomcat | Remove web starter if unneeded, set `web-application-type=none` | Merely disabling the HTTP port while still pulling the entire web stack |
| Task runs simple SQL but includes JPA | Check if entities/ORM are actually needed; consider JDBC | Removing Hibernate while the app still uses JPA repositories |
| Task does not use Spring Batch | Remove Batch starter/job config | Disabling Batch job auto-run while leaving unnecessary beans |
| Task uses Batch and needs restart | Keep JobRepository and Batch schema | Removing Batch to speed up startup and losing checkpoints |
| Task does not use a broker | Remove Stream/binder and related listeners | Leaving broker connections/consumers running inside a CLI task |
| Task has a thread pool keeping JVM alive | Close context/executors properly | Calling `System.exit(0)` and ignoring business status |
| Task writes metadata to PostgreSQL | Keep JDBC/driver/persistent TaskRepository | Disabling DataSource or using in-memory H2 in production |
| Task needs observable outcomes | Keep necessary logs/metrics, use intentional observation | Stripping all telemetry and losing traces when tasks fail |
| Slow startup due to DB network | Measure DNS, TLS, pool, and DB latency | Blaming everything on auto-configuration |
| Upgrade causes auto-config errors | Cross-check BOM, imports/exclusions, and Condition Report | Hardcoding old class names without checking |

## 13. Hands-On Lab: Optimizing Without Losing Correctness

### Preparation

Select a sample CLI task with a persistent JDBC `TaskRepository`, a synchronous `ApplicationRunner`, and a business result table. Perform this on a **test/staging environment**, never running benchmarks that generate real production data.

### Step A — Baseline

1. Record Boot, Cloud Task, Java, DB/driver versions, and all runtime dependencies.
2. Execute one successful run and one controlled failure run.
3. Save `TASK_EXECUTION` results, exit codes, business data, and logs.
4. Measure wall-clock time, memory, DB connection counts, and jar/image size across multiple runs.
5. Enable `--debug` in the lab to collect the Condition Evaluation Report, then turn off diagnostic logging.

### Step B — Reduce Dependencies

1. Use `dependency:tree` or Gradle `dependencyInsight` to identify unused web/JPA/Batch/Stream dependencies.
2. Remove **one small group** of dependencies or split modules.
3. Verify build and startup; re-run existing test cases.
4. Query `TASK_EXECUTION` via SQL to confirm both success and failure states are recorded.
5. Compare business results, duration, and memory.

### Step C — Non-Web Configuration and Conditional Beans

1. Set `spring.main.web-application-type=none`.
2. Narrow component scan or separate bean configuration with `@Profile("task")` where appropriate.
3. Verify no embedded web server or unexpected consumers/schedulers remain.
4. Keep `TaskRepository`, JDBC driver, listeners, and genuinely needed transaction managers.
5. If using `closecontextEnabled=true`, confirm the runner finishes its work before the context closes and the JVM exits cleanly.

### Step D — Upgrade Verification

1. On a dedicated branch, select a compatible Boot/Cloud/Task BOM.
2. Provision a staging metadata DB with the right schema version.
3. Check old auto-config exclusions and driver APIs, especially when changing Boot major generations.
4. Run H2 and PostgreSQL/Testcontainers integration tests, then process smoke tests.
5. Keep changes only when **exit code, TaskRepository, and business results** are all correct.
6. Have a binary/schema rollback plan ready, especially if legacy Batch Jobs still need to restart.

### Completion Criteria

- [ ] Clearly list all present starters and explain why each is needed.
- [ ] Capture runtime dependency tree/Condition Evaluation Report before and after.
- [ ] No web server or message consumer remains if the task does not use them.
- [ ] Task auto-configuration is not disabled when TaskExecution persistence is still required.
- [ ] JDBC/TaskRepository and persistent schema continue working after optimization.
- [ ] ApplicationRunner executes synchronously and reflects errors accurately.
- [ ] Tests cover both success and failure paths, not just a single success log line.
- [ ] Task does not hang due to thread pools after work completes.
- [ ] Startup, end-to-end duration, memory, and DB connection metrics are measured fairly.
- [ ] Lazy initialization is not used to hide unresolved startup errors.
- [ ] BOM/Java/DB version matrix and migration plan are verified.
- [ ] Spring Batch/observability are not removed if business/operations still require them.
- [ ] No secrets are logged in command-line arguments, benchmark logs, or TaskRepository.

## 14. Key Takeaways

With **Spring Cloud Task**, the most effective optimizations usually start with **simplifying the classpath and instantiated beans**: removing web/JPA/Batch/Stream starters when truly unused, setting application type to `none`, limiting component scans, and avoiding unrelated background connections/threads. Use `dependency:tree`/`dependencyInsight` and the **Condition Evaluation Report** to find root causes instead of guessing.

However, **TaskRepository, datasource, and error-reporting rules are core functionality when execution tracking is required**. Disabling `spring.cloud.task.autoconfiguration.enabled` or `DataSourceAutoConfiguration` can strip out the very mechanism the application must preserve. When upgrading, review **the full BOM, auto-config APIs, metadata schema, and database**, verify with integration/process tests, and measure duration **until actual work finishes**, not just until Spring logs "Started".

### References

- [Spring Cloud Task — Features: Disabling auto-configuration, Closing context](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Getting Started](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Spring Boot — Auto-configuration: debug report and exclusions](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — SpringApplication: WebApplicationType and lazy initialization](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Profiling and application startup](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-startup-tracking)
- [Spring Cloud — Compatibility, release trains, and Boot versions](https://spring.io/projects/spring-cloud/)
- [Spring Batch — Domain, JobRepository, and restart](https://docs.spring.io/spring-batch/reference/domain.html)
