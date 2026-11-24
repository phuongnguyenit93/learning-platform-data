# Configuring JobRepository and JobLauncher in a Spring Batch Project

## 1. Project Context and Objectives

When building a Spring Batch application, two foundational components you need to understand are **`JobRepository`** and **`JobLauncher`**:

- `JobRepository` stores metadata about `JobInstance`, `JobExecution`, `StepExecution`, statuses, and checkpoints needed for restarts.
- `JobLauncher` receives a `Job` along with `JobParameters` and asks Spring Batch to launch the job through the repository.

If configured improperly, a job may run once but fail to restart, two schedulers may run concurrently and produce duplicates, metadata may vanish after an application restart, or Spring Boot may unintentionally auto-launch the job on deployment.

This practice project builds a **daily revenue aggregation application**. When triggered, the application reads the `sales_order` table and writes total revenue to `daily_sales_summary`. Both are business tables; Spring Batch uses its own metadata tables to manage execution history.

Lesson objectives:

1. Understand the roles of `JobRepository` and `JobLauncher` in the system.
2. Initialize a Spring Boot 3.x + Spring Batch 5.x + PostgreSQL project.
3. Let Spring Boot auto-configure Batch infrastructure where appropriate, avoiding duplicate bean declarations.
4. Define a `Job` and `Step` with injected `JobRepository` and `PlatformTransactionManager`.
5. Launch jobs in a controlled manner using `JobLauncher` and `JobParameters`.
6. Inspect metadata, distinguishing new runs, restarts, and duplicate requests.
7. Understand how to configure manually or use an asynchronous launcher when specific requirements arise.
8. Test repository/launcher configuration without depending on production data.

**Scope:** Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC, and PostgreSQL. Exact library versions must be compatible with the Spring Boot version your project chooses. The examples only cover environment setup and code guidance, without requiring build tools to be run while reading.

## 2. Architecture: What Does the Repository Store, and What Does the Launcher Do?

Flow when requesting a job run:

```text
                        CLI / API / Scheduler
                                 |
                                 v
                     JobLauncher.run(Job, params)
                                 |
                                 v
                      JobRepository (JDBC)
                    /           |           \
             JobInstance   JobExecution   StepExecution
                                 |
                                 v
                             Job / Step
                                 |
                         Business DataSource
                         /               \
                   sales_order     daily_sales_summary
                                 |
                                 v
                        JobExecution finishes
                       COMPLETED / FAILED
                                 |
                                 v
                   Metadata is saved for next time
```

Responsibilities:

| Component | Primary Responsibility | What It Does Not Do For You |
| --- | --- | --- |
| `JobRepository` | Persist and query execution metadata; enforce identity and state when creating executions | Does not create business tables or guarantee external non-DB APIs are exactly-once |
| `JobLauncher` | Accept launch requests; coordinate with the repository and execute the job | Does not generate accurate business dates or decide schedules itself |
| `Job` | Describe step flow and restart policy | Does not know by default which data source to process |
| `Step` | Execute tasklet or chunk processing within an appropriate transaction | Does not prevent duplicate writes to external systems by default |
| `PlatformTransactionManager` | Control transactions for steps and configured data access | Does not combine multiple datasources into a distributed transaction |
| `JobExplorer` | Read metadata for monitoring and investigation | Not a tool for arbitrarily mutating statuses |
| `JobParameters` | Hold job input controls and distinguish `JobInstance`s | Does not validate that parameters make business sense |

In short: **`JobLauncher` is the launch gateway; `JobRepository` is where official Batch history and status are stored.**

## 3. JobInstance and JobExecution Determine Launch Behavior

A `Job` can be invoked many times, but not every invocation creates a new instance.

- **`Job`**: the job definition, such as `dailySalesJob`.
- **`JobParameters`**: run parameters, which can be marked identifying or non-identifying.
- **`JobInstance`**: the job name plus identifying parameters.
- **`JobExecution`**: a single execution attempt of that instance.
- **`StepExecution`**: an execution of a step, attached to a `JobExecution`.

Example:

```text
Job: dailySalesJob
  |
  +-- JobInstance 101
  |     businessDate = 2026-11-15
  |       |
  |       +-- JobExecution 9001 : FAILED
  |       +-- JobExecution 9002 : COMPLETED (restart)
  |
  +-- JobInstance 102
        businessDate = 2026-11-16
          |
          +-- JobExecution 9003 : COMPLETED
```

Three key outcomes:

1. If no instance exists for day D, `JobLauncher` can create a new `JobInstance`.
2. If the previous execution for day D failed and the job allows restarts, launching with the same identifying parameters can create a **new `JobExecution` for the same instance**.
3. If day D's instance is already `COMPLETED`, launching again with the same identifying parameters is typically rejected with `JobInstanceAlreadyCompleteException`.

Do not add a random timestamp to identifying parameters to bypass the third case; that creates a different instance and can write duplicate data.

## 4. Practice Project Structure

Example structure of a Spring Boot application:

```text
batch-demo/
  ├── build.gradle
  └── src/
      ├── main/
      │   ├── java/com/example/batchdemo/
      │   │   ├── BatchDemoApplication.java
      │   │   ├── job/DailySalesJobConfiguration.java
      │   │   └── launch/DailySalesLaunchConfiguration.java
      │   └── resources/
      │       ├── application.yml
      │       └── db/migration/V1__create_business_tables.sql
      └── test/
          └── java/com/example/batchdemo/
              └── BatchInfrastructureTest.java
```

In this guide, Spring Boot manages the datasource, transaction manager, and Batch infrastructure. The application only defines business jobs/steps and an entry point calling the launcher.

**You do not need to manually declare `JobRepository`/`JobLauncher` beans if Boot auto-configuration already meets your needs.** Manually registering `@EnableBatchProcessing` or extending `DefaultBatchConfiguration` can cause Boot to stop auto-configuring parts of the infrastructure; switch to manual configuration only for an explicit reason.

## 5. Declaring Dependencies

For a Gradle project generated from Spring Initializr with a compatible Spring Boot 3.x version, the core dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

test {
    useJUnitPlatform()
}
```

Spring Boot manages dependency versions via the project's BOM/plugin. When starting a project, choose a supported Spring Boot 3.x version and require Java 17 or higher; avoid manually mixing incompatible Spring Batch and Spring Framework versions.

Role of each dependency:

| Dependency | Function |
| --- | --- |
| `spring-boot-starter-batch` | Spring Batch core, infrastructure, and Spring Boot integration |
| `spring-boot-starter-jdbc` | `JdbcTemplate` and JDBC data access infrastructure |
| `postgresql` | JDBC driver for PostgreSQL |
| `spring-boot-starter-test` | JUnit 5, test utilities, and Spring Boot integration |
| `spring-batch-test` | Utilities for testing jobs, steps, and metadata |
| `h2` (test) | Temporary database for simple infrastructure tests |

To manage business and metadata schema migrations in production, add Flyway or Liquibase per system standards. The example uses a business migration file; Batch metadata initialization via Boot configuration is solely for illustrating the practice environment.

## 6. Preparing PostgreSQL and Schema

The example uses a `batch_demo` database and a dedicated DB account with appropriate privileges. Create the database, grant privileges to the application account, and define the schema management mechanism.

There are **two table groups**:

1. **Spring Batch metadata:** usually prefixed with `BATCH_`.
2. **Business tables:** defined by the application, such as `sales_order` and `daily_sales_summary`.

### 6.1. Standard Metadata Tables

| Table | Role |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Stores `JobInstance` identity |
| `BATCH_JOB_EXECUTION` | Stores each `JobExecution`, timestamps, and status |
| `BATCH_JOB_EXECUTION_PARAMS` | Stores `JobParameters` attached to an execution |
| `BATCH_STEP_EXECUTION` | Stores status and counters for each `StepExecution` |
| `BATCH_JOB_EXECUTION_CONTEXT` | Stores job-level context |
| `BATCH_STEP_EXECUTION_CONTEXT` | Stores step-level checkpoint/context |
| `BATCH_*_SEQ` sequences | Issue IDs for metadata according to schema/dialect |

Column names and structures can vary across versions. In Spring Batch 5.x, the `BATCH_JOB_EXECUTION_PARAMS` structure differs from the Batch 4.x schema; pick the migration script matching your version and never mix them.

**Do not treat Batch metadata as temporary data that can be deleted arbitrarily.** Dropping the schema after every deploy causes the repository to lose history and breaks true restartability.

### 6.2. Business Schema

Example PostgreSQL migration `V1__create_business_tables.sql`:

```sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE INDEX idx_sales_order_business_date
    ON sales_order (business_date);

CREATE TABLE daily_sales_summary (
    business_date DATE PRIMARY KEY,
    total_amount NUMERIC(20, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
```

Sample data:

```sql
INSERT INTO sales_order (
    order_id, business_date, amount, status
)
VALUES
    (101, DATE '2026-11-15', 120000.00, 'PAID'),
    (102, DATE '2026-11-15',  35000.00, 'PAID'),
    (103, DATE '2026-11-15',  50000.00, 'CANCELLED'),
    (104, DATE '2026-11-16',  42000.00, 'PAID');
```

The job only sums orders with `status='PAID'` on the target date. Sample revenue for Nov 15:

```text
120000.00 + 35000.00 = 155000.00
```

If migrations are managed by Flyway, place the script in the standard migration path and enable Flyway per project configuration. In this lesson, the SQL is shown so you can clearly see which business tables must exist before executing the job.

## 7. Configuring application.yml

Practice environment example:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_demo
    username: batch_user
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  launch:
    enabled: false

logging:
  level:
    org.springframework.batch: INFO
```

Explanation:

- `spring.datasource.*`: provides the JDBC datasource for Batch metadata and business data in this shared-database example.
- `spring.batch.job.enabled=false`: **disables auto-launching jobs at application startup** via Spring Boot's `JobLauncherApplicationRunner`.
- `spring.batch.jdbc.initialize-schema=always`: instructs Boot to run the Batch metadata creation script if auto-configuration applies, intended for demos or test environments.
- `app.launch.enabled=false`: an application-defined property used to control the job launch entry point in a later section.
- `logging.level.org.springframework.batch=INFO`: logs basic Batch operational messages.

**Crucial distinction:** `spring.batch.job.enabled=false` only prevents **auto-launch at startup**; it does not disable `JobRepository`, `JobLauncher`, or manual launcher calls.

### Do Not Mechanically Leave Schema Initialization as `always` in Production

In production, manage the metadata schema with versioned migrations; typical configuration is:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: never
```

Requirement: `BATCH_*` tables and sequences must be created at the right version before the application starts. Boot's initialize script is not a universal history/schema migration tool across versions; `always` does not mean safely auto-upgrading an old schema.

Passwords should only come from a secret manager or environment variables, never committed as real passwords in YAML. For production, use a least-privilege DB account; table creation privileges should belong only to the migration process if the system requires separation.

## 8. Letting Spring Boot Configure JobRepository and JobLauncher

A minimal application class:

```java
package com.example.batchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchDemoApplication.class, args);
    }
}
```

When the classpath contains the Batch starter, a datasource, and a suitable transaction manager, Spring Boot/Spring Batch can create and configure infrastructure beans such as:

- `DataSource`.
- `PlatformTransactionManager`.
- `JobRepository`.
- `JobLauncher`.
- `JobExplorer` and other required components.

Auto-configuration depends on the version, existing beans in the context, and how Batch is enabled. For a basic configuration, **do not add `@EnableBatchProcessing` just because an older article told you to**. In Spring Boot 3.x, this annotation can make Boot's Batch auto-configuration yield to manual configuration, changing where beans are created and how schema initialization works.

### Verifying via Dependency Injection

Once the application starts successfully, you can inject directly:

```java
@Component
public class BatchInfrastructureInspector {

    private final JobRepository repository;
    private final JobLauncher launcher;

    public BatchInfrastructureInspector(
            JobRepository repository,
            JobLauncher launcher) {

        this.repository = repository;
        this.launcher = launcher;
    }
}
```

This example merely illustrates bean availability; in the main project, you do not need a separate inspector for the application to work. Use these beans directly in job configurations and launch services.

If Spring throws `NoSuchBeanDefinitionException` for the repository or launcher, check dependencies, datasource, transaction manager, auto-config conditions, and any manually declared Batch configurations.

## 9. Defining a Step with JobRepository and Transaction Manager

In Spring Batch 5.x, the new builder style accepts `JobRepository` explicitly. For tasklets, the transaction manager is passed when configuring the step.

Example creating a revenue aggregation step:

```java
package com.example.batchdemo.job;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailySalesJobConfiguration {

    @Bean("dailySalesStep")
    Step dailySalesStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("dailySalesStep", repository)
            .tasklet((contribution, chunkContext) -> {

                String dateText = chunkContext
                    .getStepContext()
                    .getStepExecution()
                    .getJobExecution()
                    .getJobParameters()
                    .getString("businessDate");

                LocalDate businessDate =
                    LocalDate.parse(dateText);

                BigDecimal total = jdbc.queryForObject(
                    """
                    SELECT COALESCE(SUM(amount), 0)
                    FROM sales_order
                    WHERE business_date = ?
                      AND status = 'PAID'
                    """,
                    BigDecimal.class,
                    Date.valueOf(businessDate)
                );

                jdbc.update(
                    """
                    INSERT INTO daily_sales_summary (
                        business_date, total_amount, updated_at
                    )
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (business_date)
                    DO UPDATE SET
                        total_amount = EXCLUDED.total_amount,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    Date.valueOf(businessDate),
                    total
                );

                return RepeatStatus.FINISHED;

            }, transactionManager)
            .build();
    }

    @Bean("dailySalesJob")
    Job dailySalesJob(
            JobRepository repository,
            @Qualifier("dailySalesStep") Step step) {

        return new JobBuilder("dailySalesJob", repository)
            .start(step)
            .build();
    }
}
```

To use the example file as-is, add the imports:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
```

**Note:** This example uses PostgreSQL `ON CONFLICT` SQL, matching the database configured earlier. For H2, Oracle, SQL Server, or MySQL, upsert syntax may differ.

### Why Does Re-running the Tasklet Not Duplicate Total Revenue?

The writer in the example **upserts by `business_date`**, rather than adding the new total onto the old total. This makes the aggregation idempotent at the target table level for the same data snapshot and calculation rules.

However:

- Upsert does not mean every side effect of the job is idempotent.
- If the source changes between two reprocessing runs, the result may change; clear source versioning and business workflows are needed.
- If the step also sends emails or calls external APIs outside the transaction, corresponding idempotency must be added.

### Where Does the Transaction Actually Apply?

In the single-datasource JDBC transaction manager example, `JdbcTemplate` operations participate in the tasklet step's transaction when using the same `DataSource`. If an exception occurs before commit, business table changes within that transaction can roll back.

The metadata repository also has its own transactions for lifecycle operations. Do not assume that all metadata transactions and all external non-DB side effects are combined into a single transaction.

If you have a separate datasource for metadata and a separate datasource for business data, configure the right transaction manager for each and design a consistency/recovery strategy; Spring Batch does not automatically provide distributed transactions across datasources.

## 10. Creating JobParameters with Stable Business Identity

For a daily job:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("attemptId", "example-request-001", false)
    .toJobParameters();
```

The `businessDate` parameter is identifying; `attemptId` is non-identifying for request tracing. You can add file/snapshot codes, tenant, or revision if they genuinely determine the logical processing period.

Do not use the following approach to "guarantee it runs every time":

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Because `run.id` can become identifying by default, each request creates a new instance even though it still processes the old date. This is not a restart and can duplicate results.

### Classifying Launch Requests

| Instance State | Same Identifying Parameters | Typical Outcome |
| --- | --- | --- |
| No instance yet | First call | Creates a new `JobInstance` and `JobExecution` |
| Has `FAILED` execution | Re-requested with same identity | Can restart into a new `JobExecution` |
| Has `STOPPED` execution | Re-requested with same identity | Can restart if configuration allows |
| Currently running | Re-requested with same identity | `JobExecutionAlreadyRunningException` |
| Instance already `COMPLETED` | Re-requested with same identity | `JobInstanceAlreadyCompleteException` |

These exceptions can occur before a new `JobExecution` is created. Therefore, if you need to audit every **launch attempt**, you must store launch requests separately outside Batch metadata or log them in the orchestration layer.

## 11. Launching the Job with ApplicationRunner

To practice without exposing a REST endpoint, we create a CLI entry point. Operators pass the business date via arguments when running the application. `ApplicationRunner` is created only when `app.launch.enabled=true`.

Example:

```java
package com.example.batchdemo.launch;

import java.time.LocalDate;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesLaunchConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(DailySalesLaunchConfiguration.class);

    @Bean
    @ConditionalOnProperty(
        prefix = "app.launch",
        name = "enabled",
        havingValue = "true"
    )
    ApplicationRunner launchDailySales(
            JobLauncher jobLauncher,
            @Qualifier("dailySalesJob") Job dailySalesJob,
            @Value("${app.launch.business-date}")
                String businessDateText) {

        return args -> {
            LocalDate date =
                LocalDate.parse(businessDateText);

            JobParameters parameters =
                new JobParametersBuilder()
                    .addString(
                        "businessDate",
                        date.toString(),
                        true
                    )
                    .addString(
                        "attemptId",
                        UUID.randomUUID().toString(),
                        false
                    )
                    .toJobParameters();

            log.info(
                "event=batch.launch.requested job={} date={}",
                dailySalesJob.getName(),
                date
            );

            JobExecution execution =
                jobLauncher.run(dailySalesJob, parameters);

            log.info(
                "event=batch.launch.returned job={} instanceId={} " +
                "executionId={} status={}",
                dailySalesJob.getName(),
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );
        };
    }
}
```

The `business-date` property is required only when launch mode is enabled. If missing or given an invalid date, Spring reports a configuration or parsing error; operators should fix the input rather than silently falling back to the current date.

### Running for a Specified Date

After preparing Postgres, tables, and sample data, example command:

```bash
java -jar batch-demo.jar \
  --app.launch.enabled=true \
  --app.launch.business-date=2026-11-15
```

This is an example of passing arguments to Spring Boot. The exact JAR file name and build process depend on the actual project.

When the launcher runs **synchronously**, `jobLauncher.run(...)` typically returns only after execution finishes; at that point the status may be `COMPLETED` or `FAILED`. When using an **asynchronous** launcher, the method can return while execution is `STARTING`/`STARTED`. Never treat a launcher call returning without throwing an exception as proof that the job succeeded.

### What Happens on a Duplicate Launch?

If called again for `2026-11-15` after the job is `COMPLETED`, the identifying parameter has not changed so Spring Batch rejects it. A new `attemptId` is non-identifying, so it does not "unlock" the old instance.

In the CLI example, the exception causes the entry point to fail. In a production API or scheduler, handle exceptions according to business outcomes (already completed, already running, cannot restart, invalid parameters, etc.) rather than always treating them as system failures.

## 12. Using JobLauncher in a Service and Classifying Exceptions

When a job is invoked via a scheduler, REST API, or orchestration service, centralize launch code in a shared service. The following pattern classifies scenarios supported by Spring Batch:

```java
import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class DailySalesLaunchService {

    private final JobLauncher launcher;
    private final Job job;

    public DailySalesLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySalesJob") Job job) {

        this.launcher = launcher;
        this.job = job;
    }

    public LaunchOutcome launch(LocalDate businessDate) {
        JobParameters params = new JobParametersBuilder()
            .addString(
                "businessDate",
                businessDate.toString(),
                true
            )
            .toJobParameters();

        try {
            JobExecution execution =
                launcher.run(job, params);

            return new LaunchOutcome(
                "ACCEPTED",
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            return new LaunchOutcome("ALREADY_COMPLETED", null);

        } catch (JobExecutionAlreadyRunningException ex) {
            return new LaunchOutcome("ALREADY_RUNNING", null);

        } catch (JobRestartException ex) {
            return new LaunchOutcome("RESTART_REJECTED", null);

        } catch (JobParametersInvalidException ex) {
            return new LaunchOutcome("INVALID_PARAMETERS", null);

        } catch (Exception ex) {
            // An infrastructure error occurred; do not assert that no
            // JobExecution was persisted to the repository.
            throw new IllegalStateException(
                "Unable to confirm launch outcome", ex
            );
        }
    }

    public record LaunchOutcome(
        String status,
        Long executionId) {
    }
}
```

The strings `ACCEPTED`, `ALREADY_COMPLETED`, and `RESTART_REJECTED` are application-defined codes; they are not `BatchStatus` values. An accepted execution can still end as `FAILED`.

For APIs, do not expose a job-launching endpoint openly on the Internet. Enforce authentication, operator authorization, rate limiting, auditing, and input source controls. The CLI example in this lesson reduces attack surface and keeps focus on Batch infrastructure.

**Avoid wrapping the entire `JobLauncher.run(...)` call in `@Transactional` carelessly.** Creating a `JobExecution` has its own transaction and isolation policy; Spring Batch may reject starting a job inside an active outer transaction, or cause unpredictable transaction interactions. If launch audits must be saved, record the request first in a short transaction, commit, and then invoke the launcher.

## 13. JobRepository Tables After Execution

After running the job, business data:

```sql
SELECT
    business_date,
    total_amount,
    updated_at
FROM daily_sales_summary
ORDER BY business_date;
```

With sample data, expected:

```text
business_date  | total_amount
---------------+-------------
2026-11-15     | 155000.00
```

To inspect metadata:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySalesJob'
ORDER BY je.JOB_EXECUTION_ID;
```

A `JobInstance` may appear in multiple rows if it was restarted. This indicates multiple `JobExecution`s belonging to the same instance, not necessarily multiple data periods.

Inspect execution parameters:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_EXECUTION_PARAMS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
ORDER BY je.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

In Batch 5.x, `PARAMETER_NAME`/`PARAMETER_TYPE`/`PARAMETER_VALUE`/`IDENTIFYING` columns form the corresponding metadata model. Do not run SQL based on Batch 5 column names against an un-upgraded Batch 4 schema.

Inspect step details:

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

In the tasklet example, `READ_COUNT` and `WRITE_COUNT` do not represent the number of `sales_order` rows processed by SQL aggregation. Those counters are primarily meaningful for chunk-oriented steps using `ItemReader`/`ItemWriter`. If you need the exact valid order count, compute it in business SQL or store a separate metric.

## 14. Using JobExplorer to Read History via Java API

For dashboards or operational tools, use the `JobExplorer` API to read metadata instead of always querying `BATCH_*` tables directly.

Example:

```java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.explore.JobExplorer;

public class BatchHistoryService {

    private final JobExplorer explorer;

    public BatchHistoryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<JobExecution> executions(
            String jobName,
            JobParameters params) {

        JobInstance instance =
            explorer.getJobInstance(jobName, params);

        if (instance == null) {
            return List.of();
        }

        return explorer.getJobExecutions(instance);
    }
}
```

When displaying history, distinguish:

- `JobInstance ID`: one logical processing period.
- `JobExecution ID`: one attempt.
- `BatchStatus`: lifecycle state.
- `ExitStatus`: result, which may carry custom business codes.
- Start/end timestamps and `StepExecution`s.
- Identifying parameters used.

Never manually edit `STATUS` in the repository via SQL to force a restart. If a process dies abruptly leaving metadata in `STARTED`, follow a verified recovery procedure, confirm the old process is no longer running, and inspect target data before restarting.

## 15. Synchronous and Asynchronous JobLauncher

Spring Batch provides the `TaskExecutorJobLauncher` implementation, which uses a `TaskExecutor` to execute jobs. Synchronous or asynchronous behavior depends on the executor the launcher uses.

### 15.1. Synchronous

If the launcher uses `SyncTaskExecutor`:

```text
Caller thread
     |
     v
JobLauncher.run()
     |
  Job steps
     |
     v
JobExecution completes
     |
     v
run() returns
```

Characteristics:

- The `run()` call occupies the calling thread for the entire processing duration.
- Simple for CLI or smoke tests.
- Unsuitable if an HTTP request would have to wait for a multi-hour job.
- Exceptions in a step are usually reflected by Spring Batch via the `JobExecution` status; by default, they are not thrown to the caller like ordinary method-call exceptions.

### 15.2. Asynchronous

If the launcher uses `ThreadPoolTaskExecutor` or an asynchronous executor:

```text
HTTP / Scheduler thread
          |
          v
    JobLauncher.run()
          |
          +----> Returns JobExecution early
          |
          +----> Worker executor
                       |
                     Runs steps
                       |
                    Job finished
```

Characteristics:

- The caller receives an execution ID and queries status later.
- Thread pool size, queue capacity, and concurrency limits must be tuned.
- Shutdown must be controlled to avoid abruptly killing running jobs.
- Never log "job succeeded" solely because `run()` returned.
- A mechanism must monitor the final outcome via `JobExecution`/`JobListener`/`JobExplorer`.

Example of **one way to manually configure a launcher** when managing Batch infrastructure explicitly:

```java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;

import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public JobLauncher createLauncher(
        JobRepository repository,
        TaskExecutor executor) throws Exception {

    TaskExecutorJobLauncher launcher =
        new TaskExecutorJobLauncher();

    launcher.setJobRepository(repository);
    launcher.setTaskExecutor(executor);
    launcher.afterPropertiesSet();

    return launcher;
}

// executor = new SyncTaskExecutor()        -> synchronous
// executor = a ThreadPoolTaskExecutor      -> asynchronous
```

This is an **illustration of launcher wiring**, not code to add to a project already using Boot auto-configuration. If you manually register a `JobLauncher` bean in an existing context, inspect auto-configuration/bean naming and ensure only the launcher each caller actually needs is present. Never create two beans with the same name or leave dependency injection ambiguous.

In production, an HTTP endpoint should return an appropriate request/execution code (such as HTTP 202 when accepted) and expose a status-check API; authentication and concurrency limits are required.

## 16. When Is Manual JobRepository Configuration Needed?

Default Boot configuration fits most cases with a single datasource and a single transaction manager. Manual configuration may be needed when:

- Batch metadata is stored in a separate database from business data.
- Multiple datasources exist and you must select the exact datasource for `JobRepository`.
- A metadata table prefix other than `BATCH_` is required.
- Isolation levels when creating `JobExecution` must be tuned to handle launch contention across multiple nodes.
- Custom serializer/transaction settings are needed for operational policies.
- The application does not use Spring Boot auto-configuration or integrates Batch into a customized Spring setup.

There are **two approaches to configuring infrastructure**; choose one and apply it consistently.

### Approach A — Spring Boot Auto-Configuration

In this practice project, simply configure the datasource and let Spring Boot create the Batch infrastructure. This is the preferred default unless you have special requirements.

**Do not place `@EnableBatchProcessing` on the application class just to "turn on Batch."** Spring Boot 3.x with the starter and a suitable datasource already auto-configures it.

### Approach B — Manual Spring Batch Infrastructure

You can use `@EnableBatchProcessing` with an explicitly chosen datasource and transaction manager:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class ManualBatchInfrastructureConfiguration {

    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource")
                DataSource batchDataSource) {

        return new DataSourceTransactionManager(batchDataSource);
    }
}
```

For the configuration above to actually work, the application must **have a `batchDataSource` bean** with a proper JDBC configuration; the example intentionally avoids creating a second datasource from arbitrary connection details. Add the `Qualifier` import:

```java
import org.springframework.beans.factory.annotation.Qualifier;
```

When using manual infrastructure, check activation conditions and schema initialization: Boot may no longer manage metadata initialization as it does under default configuration. In that case, Batch table migrations and transaction managers must be set up explicitly.

You can go further with `JobRepositoryFactoryBean`, `TaskExecutorJobLauncher`, or extending `DefaultBatchConfiguration` when custom table prefixes, isolation levels, or serializers are genuinely required. However, every choice requires reviewing bean creation and Boot interaction; **never mix multiple infrastructure configuration mechanisms simultaneously without guarding against duplicate beans**.

## 17. Multiple Datasources: Metadata and Business Data Need Not Share One DB

In enterprise applications, you may need:

```text
                   JobLauncher
                        |
                        v
               JobRepository
                        |
                 batchDataSource
                        |
              DB_A: BATCH_* tables

                       Job/Step
                        |
                   businessDataSource
                        |
           DB_B: sales_order, summary
```

This helps with privilege separation and load isolation, but affects transactions:

- The metadata repository uses DB_A's transaction manager.
- Business steps use DB_B's transaction manager.
- A transaction committed on DB_B does not automatically commit atomically with metadata on DB_A.
- On a crash at the boundary between the two, business results and metadata state may become temporarily inconsistent.

To design safely:

1. Prefer writers that are idempotent by business key.
2. Do not store critical data solely in in-memory counters.
3. Implement reconciliation by business key and `JobExecution` ID.
4. Use outbox or suitable state-transition guarantees when external systems are involved.
5. Maintain audit history and operational crash-recovery procedures.

Do not assume adding two `DataSource`s and two `TransactionManager`s is enough to get distributed transactions. If true cross-database atomicity is required, that is a separate architectural decision with its own costs and limitations.

## 18. Isolation, Locking, and Concurrent Launchers

Suppose two pods simultaneously trigger `dailySalesJob` with `businessDate=2026-11-15`:

```text
Pod A                         Pod B
  |                             |
  +-- run(job, date=D)           +-- run(job, date=D)
             \                    /
              \                  /
                Shared JobRepository
                         |
                Same JobInstance identity
                         |
          One valid execution / remaining
          requests may be rejected
```

The repository uses transactions and database mechanisms to coordinate `JobInstance`/`JobExecution` creation under concurrent requests. However, merely sharing a repository does not give the application a **scheduler leader** or distributed lock for every scenario.

Distinguish:

- **Preventing duplicate executions for the same `JobInstance`**: responsibility of the repository and metadata database.
- **Firing only a single trigger cluster-wide**: responsibility of the scheduler or a distributed lock.
- **Preventing duplicate business writes on retry/restart**: responsibility of transactions, writers, and idempotency.

Isolation configuration when creating executions can matter for high-volume launch concurrency and specific databases. Never lower isolation or disable locking just to silence a concurrency error without understanding the consequences. Verify database compatibility and load-test concurrent launch scenarios.

If a node is killed while a job is running, metadata may remain in `STARTED` and block restart requests. In that case, verify the old node is no longer running, reconcile data, and handle the stuck execution via a supported recovery procedure; never edit the `STATUS` column directly in the database just to bypass checks.

## 19. Persistent Metadata Storage and Cleanup Policy

`JobRepository` needs a database that persists across application restarts:

- For local smoke tests, in-memory H2 can be suitable.
- For staging/production environments, use PostgreSQL or an equivalent database with backups, monitoring, and migrations.
- Do not use an in-memory repository/datasource for jobs needing restart after process termination.
- Define metadata retention, backup/restore, and cleanup policies for `JobExecution` history.

When metadata grows large over months, controlled archiving/purging may be needed. Arbitrarily deleting metadata can break the `JobInstance` → `JobExecution` → `StepExecution` relationships and execution contexts.

**Never delete `JobRepository` data just to re-run a `COMPLETED` instance.** If completed data needs reprocessing, create a new `JobInstance` with an explicit business revision/version, alongside a target write strategy and audit trail.

## 20. Testing JobRepository and JobLauncher

Infrastructure tests should prove:

1. The application has `JobRepository` and `JobLauncher` beans.
2. The launcher creates a `JobInstance`/`JobExecution` for new identifying parameters.
3. Metadata can be read back from `JobRepository`/`JobExplorer`.
4. The same parameters are rejected after the job is `COMPLETED`.
5. Two different business periods create two distinct `JobInstance`s.
6. If the previous execution `FAILED` and the job supports restarts, a new execution can be created within the same instance.

To focus on infrastructure, integration tests can use H2 with a very simple tasklet job without depending on the business job's PostgreSQL `ON CONFLICT` syntax.

### 20.1. Test Configuration

Use a test profile or `@SpringBootTest` properties:

```java
@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always",
    "spring.datasource.url=jdbc:h2:mem:batch_infra_test;DB_CLOSE_DELAY=-1",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password="
})
```

H2 enables fast testing of metadata flows, but **does not replace integration tests against PostgreSQL** for business SQL, isolation, connection pooling, or how the database handles concurrency.

### 20.2. An Independent Test for Batch Infrastructure

```java
package com.example.batchdemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always",
    "spring.datasource.url=jdbc:h2:mem:batch_infra_test;DB_CLOSE_DELAY=-1",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password="
})
@Import(BatchInfrastructureTest.SmokeJobConfiguration.class)
class BatchInfrastructureTest {

    @Autowired
    private JobRepository repository;

    @Autowired
    private JobLauncher launcher;

    @Autowired
    private JobExplorer explorer;

    @Autowired
    @Qualifier("smokeJob")
    private Job smokeJob;

    @Test
    void repositoryAndLauncherWorkTogether() throws Exception {
        assertNotNull(repository);
        assertNotNull(launcher);

        JobParameters firstParams = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("requestId", "req-1", false)
            .toJobParameters();

        JobExecution first =
            launcher.run(smokeJob, firstParams);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertNotNull(first.getId());
        assertNotNull(first.getJobInstance());

        JobExecution loaded =
            explorer.getJobExecution(first.getId());

        assertNotNull(loaded);
        assertEquals(BatchStatus.COMPLETED, loaded.getStatus());

        // requestId changes, yet it is non-identifying:
        // this is still the COMPLETED JobInstance.
        JobParameters duplicateParams =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addString("requestId", "req-2", false)
                .toJobParameters();

        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> launcher.run(smokeJob, duplicateParams)
        );

        JobExecution anotherDay = launcher.run(
            smokeJob,
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters()
        );

        assertEquals(
            BatchStatus.COMPLETED,
            anotherDay.getStatus()
        );

        assertNotEquals(
            first.getJobInstance().getInstanceId(),
            anotherDay.getJobInstance().getInstanceId()
        );
    }

    @TestConfiguration
    static class SmokeJobConfiguration {

        @Bean("smokeStep")
        Step smokeStep(
                JobRepository repository,
                PlatformTransactionManager txManager) {

            return new StepBuilder("smokeStep", repository)
                .tasklet((contribution, context) ->
                    RepeatStatus.FINISHED, txManager)
                .build();
        }

        @Bean("smokeJob")
        Job smokeJob(
                JobRepository repository,
                @Qualifier("smokeStep") Step smokeStep) {

            return new JobBuilder("smokeJob", repository)
                .start(smokeStep)
                .build();
        }
    }
}
```

This test focuses on three behaviors: **creating metadata**, **rejecting re-runs of a completed instance**, and **creating a distinct instance when the business key changes**.

Isolate the database between runs/suites if other tests use the same job name and identifying parameters. In a large test suite, you can use a fresh database per test, unique `JobInstance` names, or controlled metadata cleanup utilities on the **test database**.

### 20.3. Testing Failure and Restart

An additional test should have the tasklet throw an exception on the first run and succeed on the second run with the same identifying parameters.

Expected:

```text
First launch:
  JobInstance ID = 101
  JobExecution ID = 9001
  Status = FAILED

Second launch, same identifying parameters:
  JobInstance ID = 101
  JobExecution ID = 9002
  Status = COMPLETED

Third launch, same identifying parameters:
  JobInstanceAlreadyCompleteException
```

When testing, verify that the `JobInstance` ID stays the same, the `JobExecution` ID differs, business results are not duplicated, and `StepExecution` metadata reflects the right status.

If `JobLauncher` is configured asynchronously, the test must not assert `COMPLETED` immediately after `run()`; wait for the terminal status with a timeout and proper test synchronization.

## 21. Common Configuration Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Missing `JobRepository` bean | Starter/datasource/auto-config missing or overridden | Check dependencies and auto-configuration conditions |
| Missing `JobLauncher` bean | Batch infrastructure not fully initialized | Check Batch config, repository, and transaction manager |
| Job auto-runs on app startup | Boot auto-run is enabled | Set `spring.batch.job.enabled=false` to launch explicitly |
| `BATCH_JOB_INSTANCE` table not found | Metadata schema not initialized | Create the right-version schema via migration or initialize-schema in demos |
| Error due to mismatched metadata table versions | Batch 4 script used with Batch 5 | Update schema using official migrations |
| Job finishes but cannot restart | Instance is already `COMPLETED` | Distinguish restarts from versioned reprocessing |
| Every launch creates a new instance | Timestamp/`run.id` is identifying | Use stable business keys; keep trace IDs non-identifying |
| Job rejected as already running | Active execution or stale metadata | Reconcile state, prevent duplicate triggers, follow crash recovery procedures |
| Adding `@EnableBatchProcessing` alters Boot config | Mixing auto and manual infrastructure | Pick one consistent configuration mechanism |
| Multiple `TransactionManager`s cause ambiguous injection | Manager not selected for repository/step | Use qualifiers and configure datasources explicitly |
| Metadata in DB_A and business data in DB_B diverge | No atomic cross-DB transaction | Idempotency, reconciliation, and outbox where needed |
| `JobLauncher.run()` returns while job is still running | Launcher uses an asynchronous executor | Poll/observe `JobExecution`/`JobExplorer` after launch |
| Step `FAILED` yet caller sees no exception | Failure recorded as `BatchStatus` | Inspect status/exit code, not only try/catch |
| Day D data aggregated twice | Writer not idempotent or arbitrary new instance created | Upsert/unique key and reprocessing policy |
| Tests pass on H2 but fail in production | SQL dialect/isolation differs from PostgreSQL | Run integration tests against a production-compatible DB |
| Multi-node job causes contention | Launchers submit the same identity simultaneously | Shared repository, orchestration/locks, and concurrency controls |
| Metadata lost after deploy | Temporary/in-memory database used | Use a persistent DB with migrations and backups |
| Cannot trace who launched the job | Relying only on `JobExecution` metadata | Log/audit launch attempts with source and request ID |
| DB password appears in repository/config | Secrets stored insecurely | Use a secret manager/env vars and log redaction |

## 22. Design Choices for Production

A production system needs more than a job that "just runs"; it also needs recovery, operability, and data controls.

### 22.1. Persistent Metadata Database

Use PostgreSQL or a Spring Batch-supported database with backups, migrations, and monitoring. Clearly define who has read, write, and schema-update privileges.

### 22.2. `JobInstance` Identity Rules

Choose identifying parameters by business key, such as `businessDate`, `sourceSnapshotId`, or `revision`. Never add identifying timestamps to every run by reflex.

### 22.3. Launcher and Scheduler

A multi-pod application may have multiple schedulers firing triggers. Use a shared `JobRepository` to coordinate metadata, and if you need strictly one trigger across the cluster, add leader election, Quartz, or an appropriate distributed lock.

### 22.4. Idempotent Writer and Checkpoints

Steps that write data must have transactions, unique keys, or outbox/idempotency designs for external side effects. Readers needing to persist checkpoints for restarts are critical; this lesson uses a short tasklet to focus on infrastructure.

### 22.5. Audit and Observability

Log the job name, business key, request ID, `JobInstance` ID, `JobExecution` ID, final status, elapsed time, and failure cause. Distinguish a launch attempt from a `JobExecution`: a rejected request may not create a new execution.

### 22.6. Schema Management

Place both metadata and business schemas under a migration workflow. Never use `initialize-schema=always` as a production upgrade mechanism across Spring Batch versions.

### 22.7. Resource Control

When using an async launcher or partitioning, bound thread pools, queue capacities, connection pools, memory, and concurrent job counts. Add timeouts and alerts for executions lingering abnormally long.

## 23. Extension Exercises

After completing the demo application, extend it with these tasks:

1. Create `dailySalesJob` reading revenue from `sales_order` and upserting into `daily_sales_summary`.
2. Launch day D with `JobLauncher`, recording `JobInstance` ID and `JobExecution` ID.
3. Launch the exact same day D again after the job is `COMPLETED`; observe the exception and explain why no new execution is created.
4. Change `businessDate` to D+1 and verify a different `JobInstance` is created.
5. Simulate a failure on the first run so the job is `FAILED`; fix the error and re-launch the same day, confirming a new `JobExecution` under the old instance.
6. Inspect status/exit code via `JobExplorer` and a read-only SQL query against metadata.
7. Switch the launcher to an asynchronous executor in a separate configuration and observe `STARTING`/`STARTED` before `COMPLETED`.
8. Issue two concurrent launch requests for the same identity; determine the outcome for each request and verify target data is not duplicated.
9. Try configuring metadata on a separate datasource; describe the transaction manager for the repository and for the step.
10. Write a short report on why you chose Boot auto-configuration or manual configuration for your real system.

### Results to Record

| Attempt | Business date | JobInstance ID | JobExecution ID | Outcome | Target data |
| --- | --- | --- | --- | --- | --- |
| First run for day D | D | Instance A | Execution A1 | `COMPLETED` | One summary row |
| Re-run day D | D | Instance A | No new execution | `ALREADY_COMPLETED` | Unchanged |
| Run day D+1 | D+1 | Instance B | Execution B1 | `COMPLETED` | Adds new period |
| First run fails | D2 | Instance C | Execution C1 | `FAILED` | Per transaction |
| Restart after failure | D2 | Instance C | Execution C2 | `COMPLETED` | Accurate, no duplicates |

The IDs in the table are representative names. When practicing, substitute the actual IDs from Spring Batch metadata.

## 24. Summary

In a Spring Batch project, **`JobRepository` and `JobLauncher` are two tightly coupled infrastructure components with distinct responsibilities**. The repository stores `JobInstance` identity, `JobExecution`/`StepExecution` status, and checkpoints; the launcher accepts a job with parameters, decides whether to launch based on metadata, and hands execution to an executor.

With Spring Boot 3.x and Spring Batch 5.x, the straightforward practice approach is to configure PostgreSQL, let Boot create the infrastructure, define `Job`/`Step` using builders with `JobRepository` and `PlatformTransactionManager`, and call `JobLauncher.run(...)` from a controlled entry point. When manual configuration is required, you must explicitly manage datasources, transaction managers, metadata schemas, and bean wiring.

To make the application reliable for operations, keep identifying `JobParameters` stable per business rules, distinguish restarts from new instances, monitor status through metadata, test concurrent launch scenarios, and ensure writers are idempotent. Proper configuration not only lets a job run, but makes it **safely restartable, diagnosable, and protected against duplicate writes**.
