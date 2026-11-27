# Project Organization and Environment-Specific Configuration

## Objectives

In the **SPRING_CLOUD_TASK (Spring Cloud Task)** module, an application is typically launched to execute a finite job and then exit: exporting reports, syncing data, cleaning up resources, or triggering an on-demand workflow. Spring Cloud Task helps track the start time, end time, status, and outcome of each run in a database via `TaskRepository`.

After this lesson in the **Environment** chapter, you will be able to:

- Organize source code by responsibility so task logic stays independent of launch mechanisms and infrastructure configuration.
- Set up shared configuration and environment-specific settings for `local`, `test`, and `prod` using Spring Profiles.
- Provide a `DataSource` and prepare metadata tables for `TaskRepository` in each environment.
- Pass business parameters, manage secrets, handle failures, and verify execution outcomes.
- Prepare the application to run on a schedule or on demand, including when integrated with Spring Batch.

## 1. Characteristics of a Spring Cloud Task Project

Web applications typically serve requests continuously over a long lifetime. A Spring Cloud Task application follows a different lifecycle:

1. A scheduler, command line, or orchestration platform starts a **new process**.
2. Spring Boot loads configuration and initializes beans; Spring Cloud Task creates a `TaskExecution` record in the metadata repository once the infrastructure is ready.
3. An `ApplicationRunner` or `CommandLineRunner` performs the work.
4. The framework updates completion time, exit code, and errors in `TaskRepository`; the process terminates so an external system can decide whether and when to run it again.

An important distinction is that the **task name** (`spring.cloud.task.name`) identifies the job type, while **each run** receives its own `TASK_EXECUTION_ID`. There is no need to change the task name per date just to distinguish runs. Parameters such as processing date or batch ID should be passed and tracked separately.

Spring Cloud Task's `TaskRepository` stores task metadata. If the task uses Spring Batch, `JobRepository` is a separate metadata store holding `JobExecution` and `StepExecution` records; Spring Cloud Task can record the link between a Task run and Batch runs. Both repositories serve different purposes even if they share the same database server.

## 2. Directory Structure and Responsibilities

Consider a `daily-order-export` application that exports order data daily:

```text
daily-order-export/
├── pom.xml
├── .gitignore
├── src/
│   ├── main/
│   │   ├── java/com/example/orderexport/
│   │   │   ├── OrderExportTaskApplication.java
│   │   │   ├── task/
│   │   │   │   └── OrderExportRunner.java
│   │   │   ├── application/
│   │   │   │   └── OrderExportService.java
│   │   │   ├── domain/
│   │   │   │   └── ExportPeriod.java
│   │   │   ├── infrastructure/
│   │   │   │   └── OrderQueryRepository.java
│   │   │   └── config/
│   │   │       └── ExportProperties.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-test.yml
│   │       ├── application-prod.yml
│   │       └── db/migration/
│   └── test/
│       ├── java/com/example/orderexport/
│       └── resources/
└── deploy/
    └── cronjob.yaml
```

| Component | Responsibility |
| --- | --- |
| `OrderExportTaskApplication` | Spring Boot entry point; enables Spring Cloud Task. |
| `task/` | Reads per-run parameters, validates input, delegates to services, and lets exceptions propagate on task failure. |
| `application/` | Orchestrates business steps, manages transactions, and enforces safe reruns. |
| `domain/` | Business rules, value objects, and invariants with minimal infrastructure coupling. |
| `infrastructure/` | Accesses business databases, external APIs, files, and target services. |
| `config/` | Binds application configuration properties and defines related beans. |
| `resources/application*.yml` | Declares shared defaults and profile-specific overrides. |
| `db/migration/` | Manages schema changes with a migration tool when needed; must include a compatible way to deploy the Task schema. |
| `deploy/` | Schedule/deployment manifests, separated from Java business logic. |

This layout is a reference structure, not a mandatory framework requirement. For small tasks, several packages can be combined; for multiple independent tasks, consider splitting them into separate deployable applications so each task has its own runtime bounds, resources, and release cadence.

**Rule:** The `Runner` should handle only single-run lifecycle orchestration. Database queries, business calculations, or API integrations belong in dedicated services and adapters so they can be tested without booting the entire Task application.

## 3. Dependencies and Entry Point

In a Maven project that already declares **mutually compatible** Spring Boot and Spring Cloud BOM versions, core dependencies may look like this. Actual versions must be locked according to the release train's compatibility table—never mix Spring Boot and Spring Cloud versions arbitrarily:

```xml
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
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

`spring-cloud-starter-task` provides Spring Cloud Task integration; `spring-boot-starter-jdbc` supports `DataSource`/JDBC; H2 is used for local/test examples and PostgreSQL for production examples. If your project uses a different database, swap in the matching JDBC driver and metadata schema. You do not need `spring-boot-starter-web` for a command-line-only task.

Minimal entry point:

```java
package com.example.orderexport;

import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class OrderExportTaskApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderExportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner orderExportRunner() {
        return args -> {
            List<String> dates = args.getOptionValues("businessDate");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Exactly one --businessDate=yyyy-MM-dd parameter is required");
            }

            LocalDate businessDate = LocalDate.parse(dates.get(0));
            // Production implementation: call OrderExportService.export(businessDate).
            System.out.println("Processed business date: " + businessDate);
        };
    }
}
```

`@EnableTask` activates Spring Cloud Task's lifecycle management. `ApplicationRunner` receives per-run arguments; the example validates the presence and format of the date right at the application boundary. In a real project, replace the print statement with a call to `OrderExportService`. Throwing an exception on invalid arguments allows the framework to record a failure instead of falsely reporting completion.

**Note:** The snippet above only demonstrates lifecycle and configuration and does not perform an actual export. If multiple runners exist, explicitly control ordering and avoid unintended side effects. Never put an infinite loop, web server, or continuous scheduler inside a Task process when the requirement is to finish and exit.

## 4. Splitting Configuration with Spring Profiles

Spring Boot automatically loads `application.yml`, then overlays the file matching the active profile, such as `application-local.yml` or `application-prod.yml`. A single codebase and artifact can be deployed across multiple environments; differences mainly consist of service URLs, database connections, log levels, resource limits, and schema policies.

| Configuration Source | Should Contain | Should Not Contain |
| --- | --- | --- |
| `application.yml` | Application name, Task name, non-sensitive defaults, non-HTTP mode. | Passwords and fixed endpoints valid only in production. |
| `application-local.yml` | H2 or dev database, debug logging levels, sample schema settings. | Production credentials. |
| `application-test.yml` | Isolated database/configuration for automated tests, test values. | Live systems or customer data. |
| `application-prod.yml` | Operational settings, connection pool limits, environment variable references. | Hardcoded secret values. |
| Environment variables / secrets manager | Connection credentials, tokens, passwords, sensitive deployment parameters. | Java business logic. |
| Runtime arguments | Processing date, batch ID, profile when per-run override is needed. | Passwords that could appear in shell history, logs, or process listings. |

### 4.1. Shared Configuration — `application.yml`

```yaml
spring:
  application:
    name: daily-order-export
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-order-export

logging:
  level:
    root: INFO
    com.example.orderexport: INFO
```

`spring.main.web-application-type: none` ensures the process behaves as a command-line application. Keeping the Task name stable across runs allows execution history to be aggregated.

Never hardcode `spring.profiles.active: prod` in the shared file. The deployment environment selects the active profile via `SPRING_PROFILES_ACTIVE` or startup arguments.

### 4.2. Local Environment — `application-local.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:taskdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      initialize-enabled: true

logging:
  level:
    com.example.orderexport: DEBUG
```

In-memory H2 is convenient for quick trials; history disappears once the process and database terminate. Therefore, it only helps verify a single run and is unsuitable for long-term tracking. In some Spring Cloud Task versions, `spring.cloud.task.initialize-enabled` controls metadata table initialization. Verify the exact behavior and property name for your locked framework version, especially when switching database engines.

### 4.3. Test Environment — `application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:tasktest;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  cloud:
    task:
      initialize-enabled: true
```

Use the `test` profile when tests require a metadata store isolated from local and production. Parallel tests must use separate databases/schemas or explicit cleanup mechanisms. For PostgreSQL-specific behavior (data types, SQL syntax, locks/transactions), integration tests should run against real PostgreSQL in a test environment—such as via containers—rather than inferring compatibility from H2.

### 4.4. Production Environment — `application-prod.yml`

```yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      maximum-pool-size: ${TASK_DB_MAX_POOL_SIZE:4}
  cloud:
    task:
      initialize-enabled: false
```

This example assumes production uses PostgreSQL and the **Task metadata schema has already been deployed** through a controlled migration or DBA process. Disabling automatic table creation when multiple task instances start prevents DDL race conditions or writing to the wrong schema. `TASK_DB_URL` takes a form like `jdbc:postgresql://db-host:5432/task_metadata`; secret values must be injected from a secrets manager, Kubernetes Secret, or the orchestrator's secret mechanism.

Never share the same metadata database/schema between `test` and `prod`. If multiple Task applications share a database, standardize how metadata, schemas, or table prefixes are separated according to what your framework version supports.

## 5. Configuring `TaskRepository` and Managing Schemas

Spring Cloud Task uses a database connection to persist `TaskExecution`. With auto-configuration, a valid `DataSource` and compatible tables are the two critical prerequisites. Common metadata tables include:

| Table | Purpose |
| --- | --- |
| `TASK_EXECUTION` | Run details, task name, start/end timestamps, exit code, and error information. |
| `TASK_EXECUTION_PARAMS` | Execution parameters recorded by the Task. |
| `TASK_TASK_BATCH` | Links a Task execution to Batch job executions when integrated with Spring Batch. |

Table names may differ if custom prefixes or schemas are configured. Do not confuse these tables with business data tables such as `ORDERS` or `EXPORT_HISTORY`.

Recommended production workflow:

1. Lock compatible versions of Spring Boot, Spring Cloud Task, the JDBC driver, and the database engine; obtain the exact metadata DDL matching that version.
2. Integrate DDL/schema migrations into the deployment pipeline or DBA workflow; verify deployment ordering before releasing the Job.
3. Grant the Task runtime account only the required connection and DML privileges on metadata and business schemas; restrict schema-altering privileges when unnecessary.
4. Run a smoke test execution and verify the `TaskExecution` record, exit code, and end timestamp.
5. When upgrading libraries, review corresponding schema changes before deploying the upgraded artifact.

If database connectivity fails during startup, Spring Cloud Task may be unable to write an execution record. Therefore, monitor both **the process status reported by the orchestrator** and **the metadata in the database**. These two sources complement each other during incident diagnosis.

Example history query in the sample database (adjust schema/table names to match your deployment):

```sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-order-export'
ORDER BY TASK_EXECUTION_ID DESC;
```

A healthy run has valid start and end timestamps, a successful exit code, and verified business output. Exit code 0 alone is insufficient proof that exported data is accurate; supplement it with output or record-count checks.

## 6. Running the Application with Profiles and Parameters

Once packaged into an executable JAR, a local run can use:

```bash
java -jar target/daily-order-export.jar \
  --spring.profiles.active=local \
  --businessDate=2026-11-23
```

The JAR name is illustrative; use the actual artifact path from your build configuration. Spring Boot passes `--key=value` options to `ApplicationArguments`. In the code from section 3, `businessDate` is a required **business parameter** for each run; `spring.profiles.active` is an **infrastructure parameter** selecting the configuration profile.

In production, the orchestrator typically sets `SPRING_PROFILES_ACTIVE=prod` and `TASK_DB_*` environment variables before launching the JAR or container. You do not need to rebuild the JAR to change database URLs or secrets. Spring Boot supports multiple configuration sources with a defined precedence order; command-line arguments generally override environment variables and configuration files. Therefore, audit the arguments passed by schedulers to avoid unintentionally overriding critical profiles or endpoints.

A schedule can be defined via OS cron, Kubernetes CronJob, a task orchestration platform, or an external scheduler. The same application can also be invoked on demand through a Job/Task launcher. **Do not place `@Scheduled` inside the Task process itself just to keep it idling indefinitely**: recurrence belongs to the scheduler; each trigger should spawn an independent finite-lived run.

## 7. Parameters, Errors, and Safe Reruns

Separating infrastructure configuration from business parameters enables accurate reruns of a specific processing run. For example, `businessDate=2026-11-23` must carry the exact same meaning whether executed locally for testing or in production for reporting. If a default processing date depends on time zones, explicitly define the business time zone so developer machines and containers do not derive different dates.

Practical rules:

- **Validate early** on required parameters, date formats, data ranges, and target resources; fail before causing side effects.
- **Do not swallow exceptions**: log with context and let exceptions propagate out of the runner when an operation fails; never simulate success by merely logging an error message.
- **Design for idempotency**: rerunning the same date must not duplicate outputs. Use business keys, upserts, export status tables, transactions, and checkpoints as needed.
- **Limit concurrency**: prevent two overlapping runs for the same period when disallowed, such as combining scheduler concurrency policies with data-layer locks.
- **Distinguish retry classes**: bound retries on transient network/DB errors; data errors or invalid parameters should fail fast for operator intervention.
- **Enforce time bounds**: configure timeouts on external connections, execution time limits, and Job termination deadlines in the orchestrator.

A common mistake: the runner catches all exceptions, logs them, and returns normally. The orchestrator may then treat the process as successful and `TaskRepository` may mark the run as completed even though business logic failed. Use proper exceptions/exit codes and verify both signal layers: technical metadata and business outputs.

## 8. When a Task Integrates with Spring Batch

Spring Cloud Task fits finite-lived processes in general; Spring Batch adds `Job`, `Step`, checkpointing, and restart models for batch data processing. When an application uses both:

- Keep `TaskRepository` and `JobRepository` configurations explicit; define schemas, connections, and migrations for each metadata type.
- Distinguish **Task parameters** (startup arguments) from Spring Batch **JobParameters**; explicitly map business parameters into the job.
- Monitor both `TASK_EXECUTION` and `BATCH_JOB_EXECUTION` metadata. Task–Batch integration does not imply every Task runs a Batch Job.
- Verify the process failure policy when a Batch Job fails; application configuration must ensure the scheduler receives an appropriate failure status rather than relying on logs alone.

If Batch integration auto-launches Jobs at startup, verify the auto-start behavior for your exact Spring Boot/Batch version to avoid launching the Job twice (once automatically and once via a custom runner).

## 9. Security and Environment-Specific Operations

| Risk | Symptom | Mitigation |
| --- | --- | --- |
| Running with wrong profile | Test task writes to production database, or connects to wrong endpoint. | Select profile at the deployment layer; log datasource target and environment name on startup without exposing secrets. |
| Missing Task tables | Startup fails reporting missing metadata table or sequence. | Run compatible migrations before the Job; check schema and access permissions. |
| Secrets leaked into Git/logs | Passwords appear in YAML, command line, or stack traces. | Reference secret stores/environment variables; restrict log access and mask sensitive fields. |
| Uncontrolled duplicate runs | Multiple Jobs write duplicate data for the same date. | Use duplicate-run prevention mechanisms and idempotent design. |
| Task never exits | Pod/process lingers even after work finishes. | Inspect background threads, web server, open connections, and unclosed resources; set execution deadlines. |
| Failed run missing from DB | Database connection dropped before metadata was written. | Combine logs, process exit codes, and scheduler status. |

For containers, deployment images should be immutable, with configuration supplied at runtime. Configure appropriate CPU/memory limits, retry policies, and concurrency limits. When using Kubernetes CronJob, pay attention to `concurrencyPolicy`, `backoffLimit`, `restartPolicy`, and `activeDeadlineSeconds`. A retry typically creates a new execution, so business logic must be safe to rerun.

Metadata records and logs require retention/cleanup policies, as daily schedules can accumulate many `TaskExecution` entries. Never write sensitive data or large payloads into error messages or parameter metadata. Logs should include Task name, business date, correlation ID, status, duration, and processed record counts where appropriate—without credentials.

## 10. Suggested Practice Exercise

**Scenario:** You need to run `daily-order-export` daily at 02:00 while also allowing manual reruns for any given date.

1. Create the project structure from section 2 with a runner accepting `--businessDate=yyyy-MM-dd`. Delegate the export operation to a dedicated service.
2. Write three configurations—`local`, `test`, `prod`—keeping local/test on isolated metadata stores and loading production connections from environment variables.
3. Run locally with a valid date and with an invalid value. Observe logs, exit codes, and runner error reporting.
4. Prepare metadata migrations for the production database; verify that the application only runs once the schema is ready.
5. Simulate rerunning the same `businessDate` twice and verify no duplicate export data is produced.
6. Configure the schedule in an external scheduler; test two overlapping runs and verify the concurrency policy.
7. Cross-check business metrics against `TASK_EXECUTION` records and Job status in the orchestrator.

**Completion criteria:** A single JAR runs across multiple profiles; contains no hardcoded passwords; every run takes explicit parameters; failed runs emit failure signals; Task history is persisted to a durable metadata store in the deployed environment; and reruns do not corrupt business results.

## Key Takeaways

- Organizing a project by responsibility enables changing infrastructure and schedules without rewriting task logic.
- Spring Profiles keep one artifact across environments; environment variables/secret stores inject sensitive data at deployment time.
- `TaskRepository` depends on a database and version-matched metadata schema; production processes should never race to auto-create tables.
- For Spring Cloud Task, **completing a single run, recording status, and exiting the process** are integral parts of application design, not merely a test-time behavior.
