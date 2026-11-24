# Auto-Configuration Back-Off Conditions with `@EnableBatchProcessing` or Custom Configuration

## 1. The Problem in a Spring Boot Integration Application

A service receiving partner data via HTTP/SFTP, processing it in batches, and writing to PostgreSQL needs progress tracking, transactions, retries, and crash resumption. Spring Batch provides `Job`, `Step`, `JobRepository`, and `JobLauncher` for batch execution; Spring Boot adds auto-configuration to minimize boilerplate infrastructure beans.

A common mistake is adding `@EnableBatchProcessing` to a `@Configuration` class thinking the annotation is required to "enable Batch." Afterward, the Job stops running at application startup, `BATCH_*` tables are never created, or the app complains about missing `DataSource`/`transactionManager`. This is **intentional behavior**: Spring Boot stops auto-configuring Batch when it detects the application opted into configuring Spring Batch infrastructure manually.

This lesson focuses on **Spring Boot 3.x and Spring Batch 5.x (Java 17+)**: conditions that prevent auto-configuration from activating, consequences of using `@EnableBatchProcessing` or extending `DefaultBatchConfiguration`, how to transition from Boot auto-configuration to manual infrastructure management, and how to verify behavior. Spring Boot 4.x / Spring Batch 6.x introduce repository changes—consult the exact version's docs before applying them.

## 2. Who Creates Spring Batch Infrastructure?

Spring Batch defines the core infrastructure: `JobRepository` saves Job/Step metadata and status, `JobExplorer` reads history, `JobLauncher` starts Jobs with `JobParameters`, and `ItemReader`/`ItemProcessor`/`ItemWriter` process data in chunks.

Spring Boot can conditionally register Batch infrastructure, initialize JDBC metadata tables, and create `JobLauncherApplicationRunner` to run Jobs at startup. Yet `@EnableBatchProcessing` is a mechanism for **Spring Batch itself to create infrastructure**, not an annotation telling Boot to auto-configure more.

| Item | Let Boot Auto-Configure | Use `@EnableBatchProcessing`/`DefaultBatchConfiguration` |
| --- | --- | --- |
| Create `JobRepository`, `JobLauncher`, `JobExplorer` | Boot selects infrastructure based on dependencies and existing beans | Spring Batch configures per application settings |
| Choose metadata source | Can use Boot mechanisms like `@BatchDataSource` | Specify `dataSourceRef` and `transactionManagerRef` or override getters |
| Initialize `BATCH_*` tables | Handled by Boot's schema initializer | Application manages schemas or migrations itself |
| Run Job at startup | Boot can create `JobLauncherApplicationRunner` | Must create a custom trigger/runner if auto-run is desired |
| Control transactions, table prefix | Boot properties and extension points | Configured directly via Spring Batch |

Never mix both configuration paths simultaneously, as doing so can collide on `jobRepository`/`jobLauncher` bean names or wire transaction managers with unpredictable behavior.

## 3. Activation and Back-Off Conditions in Spring Boot 3.x

In Spring Boot 3.x, `BatchAutoConfiguration` can be understood through its class-level conditions (simplified below for explanation—not code to copy into your app):

~~~java
@ConditionalOnClass({
    JobLauncher.class,
    DataSource.class,
    DatabasePopulator.class
})
@ConditionalOnBean({
    DataSource.class,
    PlatformTransactionManager.class
})
@ConditionalOnMissingBean(
    value = DefaultBatchConfiguration.class,
    annotation = EnableBatchProcessing.class
)
class BatchAutoConfiguration {
    // Sub-configurations and beans provided by Spring Boot.
}
~~~

These conditions convey three rules:

1. **Classpath:** Spring Batch, JDBC, and required classes must be present.
2. **Precondition beans:** Boot 3.x requires an appropriate `DataSource` and `PlatformTransactionManager`.
3. **No manual configurator:** if a bean of type `DefaultBatchConfiguration` **or** a configuration annotated with `@EnableBatchProcessing` exists, `@ConditionalOnMissingBean` fails to match and `BatchAutoConfiguration` **backs off**.

~~~mermaid
flowchart TD
    A["Boot evaluates BatchAutoConfiguration"] --> B{"Required classes and precondition beans present?"}
    B -->|No| C["Batch auto-config does not activate"]
    B -->|Yes| D{"@EnableBatchProcessing or DefaultBatchConfiguration present?"}
    D -->|Yes| E["Boot backs off Batch configuration"]
    D -->|No| F["Boot applies auto-config if sub-conditions match"]
    E --> G["App manages repository, schema, triggers"]
    F --> H["Boot provides Batch configuration conveniences"]
~~~

**Distinguish two causes:** missing `DataSource` or transaction manager is a *failed precondition*, whereas `@EnableBatchProcessing`/`DefaultBatchConfiguration` is a *back-off condition* because the app took over configuration. Both produce similar symptoms yet require opposite fixes.

### Comparing Easily Confused Actions

| Action | Does `BatchAutoConfiguration` Back Off Because of This? | Explanation |
| --- | --- | --- |
| Adding `@EnableBatchProcessing` to a `@Configuration` class | **Yes** | Signals the app configures Batch manually |
| Configuration class extending `DefaultBatchConfiguration` | **Yes** | Programmatic alternative to the annotation |
| Declaring only `@Bean Job` and `@Bean Step` | **No** | Boot can still auto-configure infrastructure |
| Setting `spring.batch.job.enabled=false` | **No** | Only disables Boot's automatic Job launch at startup |
| Setting `spring.batch.jdbc.initialize-schema=never` | **No** | Only disables Boot's Batch schema initialization |
| Defining a custom `DataSource` or `PlatformTransactionManager` | **Not automatically** | May affect bean preconditions and source selection |
| Defining a custom `JobRepository` without picking one full strategy | **Not automatically** | Must check conditions and avoid overlapping infrastructure |

Crucial rule: **"Stopping Jobs from running at startup" is not "disabling Boot Batch auto-configuration."** Never add `@EnableBatchProcessing` just to stop a Job from running at startup.

## 4. When to Keep Spring Boot Auto-Configuration

An app using a single database for Batch metadata and wanting Boot defaults can use:

~~~kotlin
// build.gradle.kts — Spring Boot 3.x
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-batch")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

~~~yaml
# application.yml — development environment example
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/integration
    username: integration_app
    password: ${DB_PASSWORD}
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true
~~~

`initialize-schema: always` lets Boot create the Batch schema on the configured database. In production, use Flyway/Liquibase or controlled migrations and typically set `initialize-schema: never`; never re-initialize schemas carelessly on every deploy.

When Boot auto-configures, a single `Job` bean exists, and the runner is enabled, Boot normally launches the Job at startup. With multiple Jobs, select one specifically via `spring.batch.job.name` or design version-appropriate custom triggers.

If you only want to register the Job and wait for an API, scheduler, or external orchestration trigger:

~~~yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Boot can still create `JobRepository`/`JobLauncher` when preconditions hold. `spring.batch.job.enabled=false` **does not cause Boot to back off**, and `JobLauncher` can still be injected to launch on demand.

If an app has two `DataSource`s and only needs Batch metadata in a separate source, consider Boot's `@BatchDataSource` mechanism before opting into full manual infrastructure management.

## 5. Manual Configuration Option A: `@EnableBatchProcessing`

When you need explicit control over the metadata source and transaction manager, configure Spring Batch 5.x with the annotation:

~~~java
// ManualBatchInfrastructure.java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager",
    tablePrefix = "BATCH_"
)
public class ManualBatchInfrastructure {

    // A DataSource bean named batchDataSource must be provided by the app.
    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource") DataSource ds) {
        return new DataSourceTransactionManager(ds);
    }
}
~~~

`batchDataSource` is an existing bean declared in the app's connection/environment config. `dataSourceRef` and `transactionManagerRef` are **bean names**, not `application.yml` keys. This matters when a service uses one database for Batch metadata and another for business data.

A minimal Job/Step using the Spring Batch 5.x API:

~~~java
// PartnerImportJobConfiguration.java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PartnerImportJobConfiguration {

    @Bean
    Job importPartnerData(JobRepository repository, Step importPartnerStep) {
        return new JobBuilder("importPartnerData", repository)
                .start(importPartnerStep)
                .build();
    }

    @Bean
    Step importPartnerStep(
            JobRepository repository,
            @Qualifier("batchTransactionManager")
            PlatformTransactionManager transactionManager) {
        return new StepBuilder("importPartnerStep", repository)
                .tasklet((contribution, context) -> {
                    // Wiring illustration. Replace with real data-processing adapter.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

This is a wiring illustration, not a complete import application. For large datasets, use chunk-oriented processing and design `ItemReader`, `ItemProcessor`, `ItemWriter`, retry/skip caps, commit intervals, and restart strategies.

In manual mode, **Spring Boot is no longer responsible for initializing `BATCH_*` tables or creating the default Batch startup runner**. You must handle both.

## 6. Manual Configuration Option B: Extending `DefaultBatchConfiguration`

`DefaultBatchConfiguration` provides Spring Batch infrastructure via a Java base class with overridable getters. In Spring Batch 5.x:

~~~java
// ExplicitBatchConfiguration.java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.support.DefaultBatchConfiguration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ExplicitBatchConfiguration extends DefaultBatchConfiguration {

    private final DataSource metadataDataSource;
    private final PlatformTransactionManager metadataTransactionManager;

    public ExplicitBatchConfiguration(
            @Qualifier("batchDataSource") DataSource metadataDataSource,
            @Qualifier("batchTransactionManager")
            PlatformTransactionManager metadataTransactionManager) {
        this.metadataDataSource = metadataDataSource;
        this.metadataTransactionManager = metadataTransactionManager;
    }

    @Override
    protected DataSource getDataSource() {
        return metadataDataSource;
    }

    @Override
    protected PlatformTransactionManager getTransactionManager() {
        return metadataTransactionManager;
    }

    @Override
    protected String getTablePrefix() {
        return "BATCH_";
    }
}
~~~

This is an **alternative** to `ManualBatchInfrastructure` in Section 5—do not enable both simultaneously. The app must provide `batchDataSource` and `batchTransactionManager` beans. Never add `@EnableBatchProcessing` onto a class extending `DefaultBatchConfiguration`, because the two paths can conflict on bean definitions.

Starting in Spring Boot 4.x/Spring Batch 6.x, Batch infrastructure and repository choices (in-memory, JDBC, etc.) change. Do not assume Spring Batch 5.x JDBC configuration templates copy over unchanged to newer major versions.

## 7. Practical Consequences When Boot Backs Off

### 7.1. Metadata Schema Must Be Managed Explicitly

Spring Batch stores state in tables such as:

~~~text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_STEP_EXECUTION
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION_CONTEXT
~~~

Database-specific sequences/ID-generator tables also exist. Obtain **the SQL schema matching your Spring Batch version and database engine** instead of hand-creating tables from the names listed above.

Once `@EnableBatchProcessing` is added, simply setting:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: always
~~~

will **not guarantee** Boot creates the tables because Boot's Batch schema initializer backed off. Run Flyway/Liquibase or dedicated migrations before Jobs access the repository, and manage DDL permissions, deploy ordering, and backup/restore.

### 7.2. Custom Job Trigger Mechanism Required

Without Boot's startup runner, Jobs must be invoked via `JobLauncher`, a scheduler, an authorized endpoint, CLI, or orchestration. To launch a Job intentionally on startup under a custom flag:

~~~java
// ManualJobStartupConfiguration.java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManualJobStartupConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.batch",
        name = "run-on-startup",
        havingValue = "true"
    )
    ApplicationRunner runImport(
            JobLauncher launcher,
            @Qualifier("importPartnerData") Job importJob) {
        return args -> launcher.run(importJob,
                new JobParametersBuilder()
                        .addString("partner", "partner-a")
                        .addString("businessDate", "2026-11-21")
                        .toJobParameters());
    }
}
~~~

~~~yaml
app:
  batch:
    run-on-startup: false
~~~

`businessDate` is only an example. In production, parameters must originate from validated business requests. Spring Batch identifies `JobInstance` by **Job name + identifying JobParameters**: once an instance is `COMPLETED`, re-running the same parameters may be rejected. Never attach a random timestamp to every retry just to "make it run," because that spawns a new instance and risks duplicating partner data processing.

### 7.3. Do Not Confuse `JobRepository` Transactions with System-Wide Transactions

The transaction manager for `JobRepository` governs Batch metadata; Steps also have their own transaction manager. In a flow that reads files, updates a DB, and publishes to Kafka, a JDBC rollback **does not automatically revoke** sent messages or completed HTTP calls. Design idempotency keys, checkpoints, bounded retries/backoff, outboxes, or compensation where needed.

Metadata enables Job restarts and Step tracking, yet never guarantees exactly-once across HTTP, databases, caches, and brokers. This is crucial in Spring Boot Integration: validate data contracts and transaction boundaries at every adapter.

## 8. Diagnosing Configuration Errors

Run Boot with `--debug` to view the **Condition Evaluation Report**, or query `/actuator/conditions` if Actuator is enabled with proper access controls. Locate `BatchAutoConfiguration`, then verify:

1. `@ConditionalOnClass`: are the matching Batch/JDBC classes on the classpath?
2. `@ConditionalOnBean`: are appropriate `DataSource` and `PlatformTransactionManager` beans present?
3. `@ConditionalOnMissingBean`: did an `@EnableBatchProcessing` annotation or `DefaultBatchConfiguration` bean cause the condition to fail?
4. If `JobLauncherApplicationRunner` is missing, did all auto-configuration back off, was `spring.batch.job.enabled=false` set, or was a custom runner declared?

Seeing `JobRepository` or `JobLauncher` in the ApplicationContext **does not prove Boot auto-configured them**: manual Spring Batch configuration creates those beans too. Inspect bean origins, the condition report, schemas, and actual Job runs.

| Symptom | Root Cause to Verify | Resolution |
| --- | --- | --- |
| Job stops auto-running after adding annotation | Boot no longer creates `JobLauncherApplicationRunner` | Remove annotation if manual config isn't needed, or build a custom trigger |
| Missing `BATCH_JOB_INSTANCE` table error | Boot schema initializer did not run | Apply migrations matching DB and version |
| Missing `dataSource`/`transactionManager` error | Spring Batch 5.x looks for default bean names | Use `dataSourceRef`/`transactionManagerRef` or override getters |
| Duplicate `jobRepository`/`jobLauncher` beans | Multiple Batch infrastructure registration paths | Pick one strategy; check component scanning and bean definitions |
| Job duplicates work on retry/restart | JobParameters do not reflect work unit; adapters lack idempotency | Standardize parameters; enforce dedup at adapters and JobInstance |
| Config breaks after Boot upgrade | APIs and repository models changed | Read version release notes before adjusting config |

### Behavior Verification Scenario

Against a test database and minimal Job, compare three runs:

1. **Only starter and `@Bean Job`:** Boot auto-configures when preconditions match; verify Job runner, metadata tables, and execution statuses.
2. **Add `@EnableBatchProcessing`:** observe `BatchAutoConfiguration` back off; verify migrations create schemas and a custom runner launches the exact Job.
3. **Remove annotation, set `spring.batch.job.enabled=false`:** verify Boot infrastructure still exists while the Job does not auto-launch.

In production systems, proceed to test mid-Step failures, Job restarts, metadata vs. business data transactions, broker event retries, and zero duplicate writes.

## 9. Selection Rules and Self-Check Questions

| Goal | Recommended Choice |
| --- | --- |
| Run Jobs with standard setup | Keep Boot auto-configuration; do not add `@EnableBatchProcessing` out of habit |
| Prevent Jobs from running at startup | Keep auto-configuration and set `spring.batch.job.enabled=false` |
| Store metadata in a separate DataSource while keeping Boot conveniences | Check `@BatchDataSource` and DataSource selection rules for your version |
| Fully override repository/transactions/prefixes in Java config | Pick `@EnableBatchProcessing` **or** `DefaultBatchConfiguration` |
| Non-DB integration flows requiring retries and restarts | Combine Batch metadata with idempotency, transactions, outboxes, and monitoring |

**Self-check:**

1. **Is `@EnableBatchProcessing` required after adding `spring-boot-starter-batch`?** No, if Boot's auto-configuration preconditions are satisfied.
2. **What disables only startup Job auto-run?** `spring.batch.job.enabled=false`.
3. **Why does `spring.batch.jdbc.initialize-schema=always` stop creating tables after switching to manual config?** Because Boot's Batch schema initialization backed off along with auto-configuration.
4. **Should you extend `DefaultBatchConfiguration` and also add `@EnableBatchProcessing`?** No, they are mutually exclusive alternatives.
5. **Does having `JobLauncher` in the context prove auto-configuration is active?** No, manual configuration registers that bean as well.

First clarify **who owns creating Batch infrastructure, initializing metadata, and triggering Jobs**. If the application claims configuration ownership, it must assume all of those responsibilities; if you only want to change when Jobs run, keep Spring Boot's default auto-configuration.

## References

- [Spring Boot 3.5 — Batch Applications](https://docs.spring.io/spring-boot/3.5/how-to/batch.html).
- [Spring Boot 3.5 — BatchAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/batch/BatchAutoConfiguration.html).
- [Spring Batch 5.2 — EnableBatchProcessing API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/configuration/annotation/EnableBatchProcessing.html).
- [Spring Batch 5.2 — DefaultBatchConfiguration API](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/configuration/support/DefaultBatchConfiguration.html).
- [Spring Boot 4.0 — Spring Batch](https://docs.spring.io/spring-boot/4.0/reference/io/spring-batch.html) (for upgrade comparison).
