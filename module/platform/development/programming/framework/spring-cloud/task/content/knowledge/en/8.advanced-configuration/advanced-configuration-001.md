# The spring.cloud.task Property Group and Scope of Effect

**Spring Cloud Task** helps build finite-lived Spring Boot applications: they start up, perform work, and terminate. The framework records each run using `TaskExecution` in `TaskRepository`, including start/end times, status, exit code, and launch arguments. To use it reliably in production, you need to understand **which property controls which part of the system**, rather than placing every task-related configuration under a single prefix.

In the **Advanced Configuration** chapter, this lesson groups `spring.cloud.task.*` properties by their effect: **metadata repository and schema**, **lifecycle**, **execution identity**, **concurrency limits**, **Spring Batch integration**, and **events and observability**. It also points out the Spring Boot, JDBC, and orchestrator configurations that live **outside** this namespace.

> **Version note:** Property names may appear in *kebab-case* (`table-prefix`) or *camelCase* (`tablePrefix`) thanks to Spring Boot relaxed binding. Examples use kebab-case and are based on modern Spring Cloud Task guides; check the configuration metadata, BOM, and documentation for the **exact version you are deploying** before applying them. Some properties and default values have changed across release branches.

## 1. Scope of Each Configuration Layer

~~~mermaid
flowchart TD
    A["Launcher: CronJob / scheduler / API"] --> B["Spring Boot Process"]
    B --> C["spring.application, spring.main, spring.datasource"]
    C --> D["Spring Cloud Task"]
    D --> E["spring.cloud.task.*"]
    E --> F[("TaskRepository / TaskExplorer")]
    D --> G["ApplicationRunner / CommandLineRunner"]
    G --> H["Business Logic"]
    G --> I["Spring Batch Job if present"]
    I --> J[("JobRepository")]
    D -. "Optional observability / events" .-> K["Micrometer / Spring Cloud Stream"]
~~~

| Namespace or mechanism | What part does it configure? | Example | What does it **not** do on its own? |
| --- | --- | --- | --- |
| `spring.cloud.task.*` | Lifecycle, repository, execution ID, instance limits, and Task integration | `spring.cloud.task.table-prefix` | Does not create Cron schedules, does not define business logic |
| `spring.application.*` | Spring Boot application identity metadata | `spring.application.name` | Does not automatically create data-based deduplication locks |
| `spring.datasource.*` | Database connection managed by Spring Boot | `spring.datasource.url` | Does not rename Task tables by prefix |
| `spring.sql.init.*` | General Spring Boot SQL initialization | `spring.sql.init.mode` | Does not replace Task schema/migrations across all versions |
| `spring.batch.*` | Spring Batch and Job launcher behavior | `spring.batch.job.enabled` | Does not replace `TaskRepository` |
| `spring.task.*` | Spring Boot executor/scheduler | `spring.task.scheduling.pool.size` | Not a Spring Cloud Task configuration |
| Cron, Kubernetes CronJob, Quartz, workflow engine | When/how many times the process is launched | `schedule: "0 2 * * *"` | Does not automatically record `TaskExecution` if the app does not run Task |

**Common point of confusion:** `spring.cloud.task.*` is **not** synonymous with `spring.task.*`. The names look similar, but `spring.task` in Spring Boot configures the executor/scheduler mechanism; `spring.cloud.task` configures the framework that manages **a finite run**.

A task can be triggered at exactly 2:00 AM by a CronJob and still fail to record metadata if the TaskRepository connection is not working. Conversely, setting `spring.cloud.task.single-instance-enabled=true` does not make the program automatically run at 2:00 AM; it only intervenes in **whether multiple executions with the same name are allowed to run concurrently**.

## 2. Quick Reference Table for the spring.cloud.task Group

The properties below are grouped by **practical scope of impact**:

| Group | Property | Core meaning |
| --- | --- | --- |
| **Repository/schema** | `spring.cloud.task.table-prefix` | Prefix for Task metadata tables |
| | `spring.cloud.task.initialize-enabled` | Enables/disables the Task table initialization mechanism |
| **Lifecycle** | `spring.cloud.task.closecontext-enabled` | Closes the ApplicationContext after the task finishes |
| | `spring.cloud.task.autoconfiguration.enabled` | Enables/disables Spring Cloud Task auto-configuration on supported versions |
| **Identity and relationships** | `spring.cloud.task.executionid` | Uses a pre-created TaskExecution ID |
| | `spring.cloud.task.external-execution-id` | Attaches an identifier from an external system |
| | `spring.cloud.task.parent-execution-id` | Links a child run to the parent task's TaskExecution |
| **Concurrency** | `spring.cloud.task.single-instance-enabled` | Prevents two concurrent runs with the **same task name** |
| | `spring.cloud.task.single-instance-lock-ttl` | Lock hold duration for single-instance (if supported by the version) |
| | `spring.cloud.task.single-instance-lock-check-interval` | Lock check interval (if supported by the version) |
| **Batch** | `spring.cloud.task.batch.fail-on-job-failure` | Reflects a failed Batch Job as a non-zero Task exit code |
| | `spring.cloud.task.batch.application-runner-order` | Runner order when using the Batch mechanism above |
| | `spring.cloud.task.batch.listener.enabled` | Controls Task–Batch linking in branches that provide this property |
| **Events/observability** | `spring.cloud.task.events.enabled` | Publishes Task events when an appropriate Spring Cloud Stream integration is present |
| | `spring.cloud.task.batch.events.enabled` | Publishes Batch events through the corresponding integration mechanism |
| | `spring.cloud.task.observation.enabled` | Enables observation for `ApplicationRunner` / `CommandLineRunner` on supported versions |

This table is a **configuration selection map**, not a checklist that must all be turned on together. For example, an application that only runs a single runner and writes results to PostgreSQL usually does not need Batch, Stream, or Spring Integration-based instance limits.

## 3. Repository and Schema Group

### 3.1. `spring.cloud.task.table-prefix`: Metadata Table Names

By default, Spring Cloud Task uses the `TASK_` prefix, producing names such as `TASK_EXECUTION` and `TASK_EXECUTION_PARAMS`.

~~~yaml
spring:
  cloud:
    task:
      table-prefix: TASK_
~~~

If you need to isolate a set of Task tables in a shared schema, you can configure a different prefix:

~~~properties
spring.cloud.task.table-prefix=OPS_TASK_
~~~

When configured this way, the repository expects tables with the corresponding prefix (for example, `OPS_TASK_EXECUTION`). **Changing the prefix does not automatically migrate, rename, or move data between tables**. Operators must create the exact framework DDL with the chosen prefix, update migrations, and ensure query/reporting tools point to the right tables.

A prefix change between two runs can make old history appear to "disappear" because the application is now pointing to a new set of tables. This is a structural change that requires a migration and reconciliation plan.

### 3.2. `spring.cloud.task.initialize-enabled`: Table Creation Permission

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
~~~

When set to `false`, Spring Cloud Task **does not perform the Task schema auto-creation step** at startup. This approach generally suits production environments where tables are already managed by Flyway, Liquibase, or an independent migration workflow. When initialization is enabled, Task attempts to use the mechanism and DDL supported for the target database platform.

According to the reference guide, initialization may be enabled by default; some APIs represent the configuration value as `Boolean` and `null` for compatibility with legacy properties. Therefore, in production, **explicitly setting `false` after migrations have created all required tables** gives better control than relying on assumptions about the default value.

The historical name `spring.cloud.task.initialize.enable` has been marked deprecated in the documentation; prefer `initialize-enabled` on supported branches.

**Do not confuse with** `spring.sql.init.mode`: Spring Boot's SQL initialization mechanism has its own scope. Disabling one does not guarantee the other is disabled as well. Inspect startup logs and actual migrations to verify which mechanism creates the tables.

### 3.3. Where Does the TaskRepository Database Live?

General configuration example:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      table-prefix: TASK_
      initialize-enabled: false
~~~

`spring.datasource.*` provides the DataSource; when only one suitable `DataSource` exists, Spring Cloud Task can use it for the repository. **There is no standard `spring.cloud.task.datasource.url` property to replace full multi-datasource configuration**. With multiple DataSources, use `TaskConfigurer` to select the right source and transaction manager for TaskRepository/TaskExplorer; business logic can use a separate DataSource.

In production, the database account for the task needs least-privilege permissions. The metadata database must persist across runs; using an in-memory H2 database is only suitable for demos because data can be lost when the process exits.

## 4. Lifecycle Group: When Does the Process Terminate?

### 4.1. `spring.cloud.task.closecontext-enabled`

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

When enabled, Spring Cloud Task closes the `ApplicationContext` after runners complete and the completion metadata has been updated, helping release resources. It is especially useful when beans or thread pools keep non-daemon threads alive, preventing the JVM from exiting even though business work is done.

**Important condition:** runners must **wait for asynchronous work to finish** before returning. If a runner only submits a Future and immediately returns, closing the context can interrupt ongoing work. This property does not turn asynchronous calls into synchronous ones, nor does it replace graceful shutdown procedures for business resources.

Example of proper lifecycle logic:

~~~java
@Bean
ApplicationRunner runReport(ReportService service) {
    return args -> {
        // The report generation method returns only after the output is completely written.
        service.generateAndWait();
    };
}
~~~

For an `@Scheduled` method running indefinitely inside a server process, enabling `closecontext-enabled` does not turn it into a standalone scheduled task; the deployment model needs to be reconsidered to fit a finite-lived application.

### 4.2. `spring.cloud.task.autoconfiguration.enabled`

Spring Cloud Task documentation supports disabling the framework's auto-configuration via:

~~~properties
spring.cloud.task.autoconfiguration.enabled=false
~~~

When disabled, lifecycle/repository components are no longer automatically created by default as in a standard Spring Cloud Task application. Use this only when you genuinely want to disable the Task mechanism or provide a verified custom configuration; it is **not** a temporary workaround to ignore TaskRepository connection errors. If you need to customize the repository, look into `TaskConfigurer` before disabling all auto-configuration.

### 4.3. Naming a Task

The `TaskExecution.taskName` name is typically taken from `spring.application.name` via the default `TaskNameResolver` mechanism or from a custom resolver. For example:

~~~properties
spring.application.name=invoice-report-task
~~~

Do not assume that `spring.cloud.task.name` is a standard configuration key across all versions. Use `spring.application.name` when you want a consistent application/task name, or implement `TaskNameResolver` if you need different naming rules.

The task name is critical when **single-instance** is enabled because the lock scope is the task name, not the report date or source ID.

## 5. Identity Group: TaskExecution ID, External ID, and Parent ID

### 5.1. `spring.cloud.task.executionid`: Updating a Pre-Created Run

Normally, each time the process starts, Spring Cloud Task creates a new TaskExecution and assigns a corresponding numeric ID. In advanced orchestration systems, it may be necessary to create the TaskExecution **as soon as a request is accepted**, and launch the execution process later.

Once the record has been pre-created via `TaskRepository`, pass that ID to the task:

~~~bash
java -jar invoice-report-task.jar \
  --spring.cloud.task.executionid=81042 \
  --report-date=2026-11-23
~~~

The value `81042` is an example; it must be an **ID that actually exists** in the repository the process will use, with update permissions and in the proper state. Do not make up an arbitrary number and assume the framework will create a record with that number.

### 5.2. `spring.cloud.task.external-execution-id`: Attaching a Launcher ID

A Kubernetes Job, workflow engine, or orchestration service may have its own tracking ID. Attach that ID to the TaskExecution for cross-referencing:

~~~properties
spring.cloud.task.external-execution-id=workflow-run-2026-11-24-001
~~~

This is an **external identifier** stored alongside Task metadata; it **does not replace** the TaskExecution ID managed by TaskRepository and does not automatically enforce business uniqueness rules.

### 5.3. `spring.cloud.task.parent-execution-id`: Parent–Child Relationship

If Task A launches Task B, Task B can be linked to Task A's TaskExecution ID:

~~~properties
spring.cloud.task.parent-execution-id=81040
~~~

Operators can then look up all child runs belonging to a workflow. **Parent ID** is a traceability relationship, not a guarantee that the child must succeed or roll back together with the parent; error handling across tasks is the responsibility of the orchestrator or workflow logic.

| Property | What does it point to? | Typically obtained from |
| --- | --- | --- |
| `executionid` | The **current**, pre-created TaskExecution | TaskRepository/launcher |
| `external-execution-id` | ID in an external system | CronJob, workflow run, request tracker |
| `parent-execution-id` | TaskExecution of the **parent** task | Orchestrator of related tasks |

You should not turn these IDs into a data deduplication convention. Two runs importing the same file can have two different TaskExecution IDs; **business keys and idempotency** determine whether re-writing is valid.

## 6. Concurrency Control Group

### 6.1. `spring.cloud.task.single-instance-enabled`

~~~yaml
spring:
  application:
    name: inventory-sync-task
  cloud:
    task:
      single-instance-enabled: true
~~~

When enabled, Spring Cloud Task checks whether a run with the **same task name** is already executing. If so, the new run is rejected and may return a failure exit code. By default this feature is **disabled**, because many short-lived jobs are designed to run in parallel.

The single-instance feature uses a mechanism from **Spring Integration**; the official guide requires adding the appropriate modules such as `spring-integration-core` and `spring-integration-jdbc` to your dependencies. Only flipping the flag to `true` when dependencies or locking schema are missing can cause startup failures; test against your exact database and deployment version.

**Lock scope:** the task name, not parameters like `--report-date`, `--tenant-id`, or `--source-id`.

Example:

| Run | Task name | Business parameters | When single-instance is enabled |
| --- | --- | --- | --- |
| A | `invoice-report-task` | `date=2026-11-23` | Runs |
| B, triggered while A is still running | `invoice-report-task` | `date=2026-11-24` | Blocked because of the **same name**, even though the date differs |
| C | `order-import-task` | `source=partner-a` | Not blocked just because A is running |

If the requirement is **no duplicate runs for the same tenant and date** while allowing different dates to run in parallel, use a business-key lock or unique constraint at the business layer instead of locking the entire task name.

### 6.2. Lock TTL and Check Interval

Some branches provide two additional properties:

~~~properties
spring.cloud.task.single-instance-lock-check-interval=500
spring.cloud.task.single-instance-lock-ttl=600000
~~~

In versions that expose this property group, the unit is **milliseconds**: `500` ms between checks, and `600000` ms equals 10 minutes. The lock hold duration must match the maximum runtime and dead-process recovery mechanism. Setting the TTL too short can allow another run to start while the previous one is still running; setting it too long delays recovery after a crash.

**Verify version support** before using the TTL/interval keys, as property names, defaults, and enforcement mechanisms can vary across release lines.

### 6.3. Distinguishing from Orchestrator Limits

Kubernetes CronJob has `concurrencyPolicy: Forbid` to prevent overlapping Jobs from the **same CronJob**. The `single-instance-enabled` flag restricts by the application's **Task name** when using Spring Cloud Task and a compatible repository/lock mechanism. The two scopes are independent: a Job triggered manually via an API can still appear outside the CronJob.

In a safe deployment, policies should be chosen at all three layers: orchestrator (launch schedule), Task (task name if needed), and business logic (business key/idempotency).

## 7. Spring Batch Integration Group

Spring Cloud Task manages the **process run**; Spring Batch manages **Job, Step, checkpoints, and JobRepository**. Task–Batch settings do not replace Spring Boot's `spring.batch.*` properties.

### 7.1. `spring.cloud.task.batch.fail-on-job-failure`

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

When running a Spring Batch Job inside a Task, there are cases where the Job fails yet the Spring Boot process still exits with code `0` under default launcher behavior. Enable this property so the Task integration reflects a Batch Job with `BatchStatus.FAILED` as a **non-zero exit code** (typically `1`, or according to a configured `ExitCodeGenerator`). This is critical if a CronJob/CI/workflow needs to detect failure from the **process exit code**.

This property takes effect in a **compatible Task–Batch integration setup**, when a Batch Job is actually executed; it does not cause business exceptions to be automatically retried or skipped.

### 7.2. Runner Order and JobExecution Linking

The documentation describes `spring.cloud.task.batch.application-runner-order` for adjusting the order of the specialized ApplicationRunner when `fail-on-job-failure` is enabled. If the application has multiple runners, changing the order can affect when the Batch Job runs relative to data-preparation steps.

Some branches have `spring.cloud.task.batch.listener.enabled` to control linking `JobExecution` to `TaskExecution`; on other branches, this capability also depends on the `spring-cloud-task-batch` module, auto-configuration, and listeners. Before toggling the flag, check your actual version and inspect the association table after a test run.

`spring.batch.job.enabled` or Spring Boot's job-selection startup configuration belongs to the **Batch namespace**, not `spring.cloud.task.batch.job-names` (an older property deprecated in historical branches).

### 7.3. When Should You Change Batch Properties?

| Scenario | Adjustment to consider |
| --- | --- |
| Running a multi-chunk import Job, needing JobExecution linked to Task | Task–Batch module and linking listener |
| Job fails but external workflow still sees exit code 0 | `spring.cloud.task.batch.fail-on-job-failure=true` |
| Having a data-prep runner and a Batch-launching runner | Check `application-runner-order` and launcher mechanism |
| Needing to run only one Job out of multiple Job beans | Version-appropriate Spring Batch/Spring Boot config; verify the selected Job |
| Needing to restart a Job from a checkpoint | **Spring Batch's** JobRepository, JobParameters, and restart policy, not `TaskExecution ID` |

## 8. Events, Observation, and Monitoring Group

### 8.1. `spring.cloud.task.events.enabled`

In systems with Spring Cloud Stream and an appropriate binder, Spring Cloud Task can emit Task lifecycle events over a message channel. With that integration:

~~~properties
spring.cloud.task.events.enabled=false
~~~

**disables Task event emission**. Do not misunderstand this flag as disabling writing `TaskExecution` to the database; publishing messages and persisting metadata are two separate mechanisms. The flag is only meaningful when event integration dependencies and configuration are actually in use.

### 8.2. `spring.cloud.task.batch.events.enabled`

~~~properties
spring.cloud.task.batch.events.enabled=false
~~~

In an appropriate Batch events integration, this flag disables event emission for Jobs/Steps/Chunks. Some versions support disabling `job-execution`, `step-execution`, `chunk`, `item-read`, `item-process`, `item-write`, and `skip` individually under `spring.cloud.task.batch.events.*.enabled`.

Enabling/disabling event emission **does not replace** JobRepository, TaskRepository, or Job status monitoring. If detailed observability is needed, you must design the receiving channel, retries, access control, and event retention policy.

### 8.3. `spring.cloud.task.observation.enabled`

Modern branches allow enabling observation for `ApplicationRunner` / `CommandLineRunner`:

~~~properties
spring.cloud.task.observation.enabled=true
~~~

To actually export metrics/traces, you need to configure Micrometer, Actuator, and the corresponding registry/tracing exporter. A single boolean **does not automatically create dashboards** and does not automatically attach business tags to every measurement. Keep tag cardinality under control, avoiding putting tokens, paths containing PII, or unbounded TaskExecution IDs into metric tags unless necessary.

## 9. Environment-Specific Configuration Examples

### 9.1. Basic Configuration for a One-Off Task

Suppose the `daily-report-task` application is packaged with `spring-cloud-starter-task`, a JDBC driver, and dependencies compatible with your Spring Boot version:

~~~yaml
spring:
  application:
    name: daily-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      table-prefix: TASK_
      initialize-enabled: false
      closecontext-enabled: true
~~~

**Prerequisites before running:** operators have already created the Task tables using migrations compatible with the database, schema, prefix, and library version. The `TASK_DB_*` variables are supplied by the runtime environment/secret manager; never commit passwords to files.

For an application using `ApplicationRunner`:

~~~java
@SpringBootApplication
@EnableTask
public class DailyReportTaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(DailyReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner runReport(ReportService reports) {
        return args -> {
            List<String> values = args.getOptionValues("date");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Expected one --date=yyyy-MM-dd");
            }
            LocalDate date = LocalDate.parse(values.get(0));
            reports.generate(date); // Synchronous until the report has completely finished.
        };
    }
}

interface ReportService {
    void generate(LocalDate date);
}
~~~

Corresponding imports: `java.time.LocalDate`, `java.util.List`, `ApplicationRunner`, `SpringApplication`, `SpringBootApplication`, `@EnableTask`, `@Bean`. `ReportService` is just the business contract; a real application needs a bean implementing this interface. The snippet does not schedule runs by itself.

Manual execution:

~~~bash
java -jar daily-report-task.jar --date=2026-11-23
~~~

Expected result: a TaskExecution named `daily-report-task`, an arguments list containing `--date=2026-11-23`, start/end timestamps, and the corresponding exit code. For invalid input, the runner should throw an exception so the framework/orchestrator sees a failure, instead of merely logging and returning normally.

### 9.2. Enabling Flags Only for Runs That Need Them

Example of name-based concurrency control in an environment with full Spring Integration dependencies and lock schema:

~~~bash
java -jar daily-report-task.jar \
  --date=2026-11-23 \
  --spring.cloud.task.single-instance-enabled=true
~~~

Because Spring Boot command-line arguments can be recorded in `TaskExecution.arguments`, **do not pass secrets** via `--spring.datasource.password=...` or `--token=...`. Use environment variables, a secret store, and repository permissions.

**Prefer fixed configuration via profiles/deployment** for infrastructure-level properties (schema prefix, table initialization permissions, repository datasource). Letting each invocation arbitrarily change `table-prefix` or `initialize-enabled` easily causes schema drift across runs.

### 9.3. Configuration Layers and Scope of Impact

In Spring Boot, `application.yml`, `application-{profile}.yml`, environment variables, and command-line arguments can all provide values for the same property; precedence follows the **externalized configuration** rules of your Spring Boot version. Command-line arguments usually take higher precedence than packaged config, but verify when using Config Server, Kubernetes, or a custom PropertySource.

| Placement | Example | Typical scope |
| --- | --- | --- |
| `application.yml` | `spring.cloud.task.closecontext-enabled=true` | Default for the artifact |
| `application-prod.yml` | `spring.cloud.task.initialize-enabled=false` | When the `prod` profile is active |
| Environment variable | `SPRING_CLOUD_TASK_TABLE_PREFIX=TASK_` | Process/container having that variable |
| Application argument | `--spring.cloud.task.external-execution-id=run-001` | A single launch |
| Deployment/launcher | CronJob schedule, retries, backoff | Orchestrator schedule and policy |

Properties read at **startup** are not guaranteed to update dynamically mid-run if the configuration source changes. To change behavior for the next run, update the deployment configuration and launch a new process.

## 10. Real-World Issues and Diagnostics

| Symptom | Check first | How to resolve |
| --- | --- | --- |
| No rows in `TASK_EXECUTION` | Is Task auto-configuration enabled? Did context reach the lifecycle phase? | Check datasource, schema, startup logs, and auto-configuration flags |
| "table does not exist" error | Does `table-prefix` match DDL? Is `initialize-enabled` off? | Create migrations with the right prefix, check schema/search path and DB permissions |
| Two processes with the same name run in parallel | `single-instance-enabled` defaults to false or integration is missing | Enable the proper mechanism and dependencies; inspect lock storage |
| Batch Job reports `FAILED` but launcher sees exit code 0 | `fail-on-job-failure` and integration runner | Enable the proper mechanism and test the actual exit code |
| Task does not exit after runners finish | Thread pool/bean still has non-daemon threads alive | Consider `closecontext-enabled=true`, ensure async work is awaited |
| Task loses history after restart | Using in-memory H2 or changed `table-prefix` | Use a persistent database, verify the same repository |
| Traceability cannot link to Job/K8s | Missing external/parent ID or Task–Batch link | Pass valid IDs, enable version-appropriate listener, check association table |
| No metrics or events visible | Missing Actuator/Micrometer/registry or Stream/binder | Verify dependencies, exporter, feature flags, and permissions |
| Blocked when running two different report dates | Single-instance locks by **task name** | Redesign run scope or use a business-key lock |

**Troubleshooting principle:** identify the responsible layer first. Scheduling issues belong to the orchestrator, DB connection errors usually belong to DataSource/migrations, metadata errors belong to TaskRepository, and incorrect imported data belongs to business code. Randomly toggling `spring.cloud.task.*` flags rarely fixes the root cause.

## 11. Pre-Production Configuration Checklist

- **Version:** Is the Spring Cloud Task BOM compatible with Spring Boot, Java, and Spring Batch? Do the intended keys exist in the metadata for that exact version?
- **Repository:** Do the schema and `table-prefix` match, with migrations and least-privilege SQL permissions? Is TaskExecution history retained long enough for traceability?
- **Lifecycle:** Do runners wait for async work to finish? Does the process exit with a meaningful exit code?
- **Identity:** If using `executionid`, does the pre-created record exist in the right repository? Do external ID and parent ID match the workflow?
- **Concurrency:** Do you want to lock the entire task name or only a business key? Are crash/timeout/lock-recovery handled?
- **Batch:** Does a failed Batch Job cause the launcher to detect the error? Are TaskExecution and JobExecution clearly distinguished?
- **Observability:** Are logs, metrics, events, and errors traceable without exposing sensitive data?
- **Deployment:** Are flag changes reviewed via startup logs and a dry run with safe data?

### Self-Check Exercise

Design the configuration for a `monthly-invoice-task` task that generates monthly invoices:

1. Configure TaskRepository to use PostgreSQL with the default prefix; schema is managed by migrations and must not auto-initialize when the task starts.
2. Name it so every TaskExecution of the application can be queried under `monthly-invoice-task`.
3. Ensure the task terminates the process after finishing file export and status updates.
4. Suppose the task can be triggered from both an API and a CronJob: decide whether name-based single-instance is needed or if a business `(tenant, month)` lock should be used instead.
5. If the task runs Spring Batch, configure it so a failed Batch Job results in a failure exit code.
6. When the Task is launched from a workflow that has a `workflow-run-id`, pick the property to store this ID without interfering with the internal TaskExecution ID.
7. Explain why changing `spring.cloud.task.table-prefix` does not automatically alter existing tables.

Suggested answer: use `spring.datasource.*`, `spring.cloud.task.initialize-enabled=false`, `spring.application.name`, `spring.cloud.task.closecontext-enabled=true`, choose single-instance or a business-key lock depending on scope, enable `spring.cloud.task.batch.fail-on-job-failure` if Batch integration is present, and use `spring.cloud.task.external-execution-id` for workflow traceability.

## 12. Key Takeaways

1. `spring.cloud.task.*` mainly configures **Spring Cloud Task infrastructure and lifecycle**; it does not control the scheduler or business logic.
2. `table-prefix` and `initialize-enabled` affect the **metadata schema**; `spring.datasource.*` and `TaskConfigurer` determine the repository connection.
3. `closecontext-enabled` affects **context closing**; asynchronous work must complete before runners return.
4. `executionid`, `external-execution-id`, and `parent-execution-id` serve **three distinct roles**: current run ID, external system ID, and parent task ID.
5. `single-instance-enabled` restricts overlapping runs by **task name**. Deduplicating by a business key requires its own mechanism.
6. `spring.cloud.task.batch.*`, `events.*`, and `observation.*` properties only take full effect when the proper **integration modules and dependencies** are configured.
7. For every change, verify the **version, scope of impact, default values, migration process, and how to validate it with a real run**.

### Official References

- [Spring Cloud Task — Features and Configuration](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Spring Batch Integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Spring Cloud Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html)
- [Spring Cloud — Configuration Properties (look up by version)](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
