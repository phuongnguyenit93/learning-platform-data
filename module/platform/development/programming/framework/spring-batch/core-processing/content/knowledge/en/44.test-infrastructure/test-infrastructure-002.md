# Embedded Databases for Metadata in Spring Batch Testing

## 1. Why Do Spring Batch Tests Need a Metadata Database?

Spring Batch does not only read, process, and write business data. The framework also manages **metadata for each run** to answer questions such as:

- Which Job ran, and with which parameters?
- Which `JobExecution`s does this `JobInstance` already have? Did the previous run succeed, fail, or stop?
- How many times did each step run, how many items were read/written, and how many chunks were committed?
- Which checkpoint was saved in `ExecutionContext` so the reader/writer can resume on restart?
- Is it allowed to create another run with the same identifying `JobParameters`?

These answers are primarily managed by **`JobRepository`**, typically using JDBC to persist metadata tables in a relational database. `JobExplorer` provides the API to read metadata back for observation and verification.

In a test environment, we usually do not want to depend on a running PostgreSQL, Oracle, or SQL Server instance. An **embedded database** such as H2 or HSQLDB provides a lightweight SQL metadata store that starts alongside the tests and is easy to isolate and clean up.

This lesson focuses on **embedded databases for metadata** in Spring Batch test infrastructure, without confusing them with the database containing customer, invoice, or business data processed by the batch job.

### Objectives

After this lesson, you will be able to:

1. Explain the role of the metadata database in the lifecycle of `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`.
2. Set up embedded in-memory H2 with Spring Boot and the Spring Batch JDBC repository.
3. Properly initialize the metadata schema and avoid errors from missing tables, duplicate schemas, or version mismatches.
4. Run integration tests using `@SpringBatchTest` and `JobLauncherTestUtils`, then inspect metadata via `JobExplorer` or `JdbcTemplate`.
5. Isolate data between tests and between `ApplicationContext` creations.
6. Understand the limitations of H2 when testing transactions, concurrency, restart, locking, and SQL dialect differences compared to production databases.

The examples below target **Java 17+, Spring Boot 3.x, Spring Batch 5.x, JUnit 5, and Gradle Groovy DSL**. Some APIs and configuration options change across versions; when using Spring Batch 6.x, check the testing APIs for that version.

---

## 2. Distinguishing the Metadata Database from the Business Database

Imagine an order import job:

```text
                 +-------------------------+
                 |     JobLauncher         |
                 +------------+------------+
                              |
                              v
                 +-------------------------+
                 |     JobRepository       |
                 |  metadata / checkpoint  |
                 +------------+------------+
                              |
                              v
              +-------------------------------+
              | Embedded H2 (test metadata)   |
              | BATCH_JOB_INSTANCE            |
              | BATCH_JOB_EXECUTION           |
              | BATCH_STEP_EXECUTION          |
              | BATCH_*_EXECUTION_CONTEXT     |
              +-------------------------------+

               orderImportJob / orderStep
                         |
             +-----------+-----------+
             |                       |
             v                       v
     business input             business output
     CSV / API / DB             file / DB / queue
```

The **metadata database** stores information needed by Spring Batch to operate and restart. The **business database** stores the data processed by the job. Both roles can live in the same physical database or reside on separate data sources; tests must know which one they are replacing.

| Item | Metadata database | Business database |
| --- | --- | --- |
| Logical owner | `JobRepository` / Spring Batch | Application repositories, readers, writers, DAOs |
| Contents | Job instances, executions, step executions, parameters, contexts | Customers, orders, invoices, input/output data |
| Default schema | Spring Batch `BATCH_*` tables | Application-specific schema |
| Testing with H2 is useful when | Verifying job/step lifecycle, checkpoints, basic restart | Testing H2-compatible business queries and writes |
| What H2 does not guarantee | Identical locking/transactions to the production DB | Identical SQL dialect, stored procedures, indexes, data types as the production DB |

For example, a job that reads a CSV file and writes JSON output can use **a single H2 database** solely for metadata, because the business data lives in files. If a job uses PostgreSQL with vendor-specific SQL queries, you may still use H2 for **metadata** in some tests, but tests verifying business query compatibility require real PostgreSQL or Testcontainers.

### 2.1. Are "Embedded" and "In-Memory" the Same Thing?

Not quite:

- **Embedded** means the database engine runs inside the application/test process, requiring no separate database server.
- **In-memory** means the database stores its data in RAM, usually lost when the engine closes or the JVM terminates.
- H2 also has a **file mode**, which still runs embedded while persisting data to disk files.
- H2 can also run in server mode, in which case it is no longer the simple embedded setup discussed here.

For tests that need to start from a clean slate, **embedded in-memory** is a common choice. For restart tests **within the same JVM**, an in-memory database still works as long as all runs connect to **the same live database instance**. Testing restart after a full JVM shutdown requires a database that persists across processes, such as H2 file mode or a database container.

---

## 3. Metadata Tables Required by Spring Batch

The Spring Batch JDBC repository does not infer or auto-generate metadata tables from JPA entities. It relies on the framework's SQL schema.

The main tables in Spring Batch 5.x include:

| Table | What It Stores | Common Checks |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | Logical identity of a job with identifying job parameters | Do two reruns share the same `JobInstance`? |
| `BATCH_JOB_EXECUTION` | Each job execution attempt, status, start/end time, version | Execution count; `FAILED`, `COMPLETED` status |
| `BATCH_JOB_EXECUTION_PARAMS` | Parameters for each job execution | Do the actually stored parameters match on restart? |
| `BATCH_STEP_EXECUTION` | Each step run; counts, status, version | Commit/read/write/rollback counts and step run count |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-level `ExecutionContext` | Values passed between steps |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step-level `ExecutionContext` | Reader/writer checkpoints for restart |

In addition, there are corresponding sequences or ID generation mechanisms depending on the database dialect, such as `BATCH_JOB_SEQ`, `BATCH_JOB_EXECUTION_SEQ`, and `BATCH_STEP_EXECUTION_SEQ`.

### 3.1. Metadata Relationships

```text
BATCH_JOB_INSTANCE (1)
    |
    +---- (N) BATCH_JOB_EXECUTION
                 |
                 +---- (1) BATCH_JOB_EXECUTION_CONTEXT
                 |
                 +---- (N) BATCH_JOB_EXECUTION_PARAMS
                 |
                 +---- (N) BATCH_STEP_EXECUTION
                                  |
                                  +---- (1)
                                        BATCH_STEP_EXECUTION_CONTEXT
```

A `JobInstance` is identified by its job name and identifying parameters. An instance can have multiple `JobExecution`s—for example, `FAILED` on the first run and `COMPLETED` after restart. Each `JobExecution` can contain multiple `StepExecution`s. The context tables hold state saved at boundaries appropriate to the job and step lifecycle.

**Version note:** Spring Batch 5 changed the storage structure for job parameters compared to 4.x versions. Therefore, do not use Spring Batch 4 SQL schemas with a Spring Batch 5 application. When a test fails with a missing column or insert failure, the first thing to check is whether the **schema, runtime libraries, and migrations** belong to the same version.

### 3.2. The Schema Must Be Created Before the Job Runs

When Spring Batch prepares to create a `JobExecution`, `JobRepository` must read and write metadata. If the tables do not exist yet, the test can fail before any tasklet or reader is even invoked.

A typical error looks like:

```text
org.h2.jdbc.JdbcSQLSyntaxErrorException:
Table "BATCH_JOB_INSTANCE" not found
```

This is primarily a **test infrastructure** error: H2 connected successfully, but the metadata schema was not initialized, or it was initialized in a different database than the one `JobRepository` is using.

---

## 4. Choosing H2, HSQLDB, or Derby for Test Metadata

Embedded SQL engines commonly used in Java tests:

| Engine | Gradle Dependency | Highlights | Notes |
| --- | --- | --- | --- |
| H2 | `com.h2database:h2` | Fast startup, easy in-memory URL configuration, widely used with Spring Boot | SQL dialect, locking, and isolation may differ from production |
| HSQLDB | `org.hsqldb:hsqldb` | Lightweight embedded engine supporting in-memory mode | Use the matching schema script and appropriate driver |
| Apache Derby | `org.apache.derby:derby` (may also need `derbytools` depending on Java/Derby version) | Embedded database in the Java ecosystem | Compatibility matrix for Java, driver, and libraries must be verified |

To learn the metadata repository mechanics and build fast-running integration tests, the following examples use **H2**. When production uses PostgreSQL/Oracle/SQL Server and you care about locking, deadlocks, timezones, data types, transactional consistency, or SQL differences, add tests running against the actual engine via Testcontainers or an integration environment.

### When Is H2 Sufficient?

H2 is typically useful for:

- Testing wiring between `JobLauncher`, `JobRepository`, `JobExplorer`, and steps.
- Verifying that a `JobInstance` produces the expected `JobExecution`/`StepExecution`.
- Verifying that status and context are saved and read back.
- Testing restart across multiple `JobExecution`s **within the same test process**.
- Running large suites of independent tests on CI without spinning up a database server.

H2 is **not sufficient to conclude** that locking algorithms, transaction isolation, vendor SQL, and concurrency handling will behave identically to production.

---

## 5. Configuring Embedded In-Memory H2 for Spring Batch Tests

### 5.1. Minimal Dependencies

Gradle Groovy DSL example:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.0'
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    // Use H2 only for tests; production does not depend on H2.
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In a real Spring Boot project, use the plugin/BOM versions standardized for your project rather than copying the example version numbers verbatim. Spring Boot dependency management aligns compatible versions of Spring Batch, Spring JDBC, and H2.

`spring-boot-starter-batch` provides the core Spring Batch/JDBC components; `spring-batch-test` provides the test utilities; H2 provides the JDBC driver and database engine running inside the test process.

### 5.2. Simplest Configuration with Spring Boot

Create `src/test/resources/application-batch-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

Then activate the `batch-test` profile with `@ActiveProfiles("batch-test")` on your integration test.

Meaning of each setting:

- `spring.batch.job.enabled=false`: prevents Spring Boot from automatically launching all jobs as soon as the application context is ready; the test invokes the launcher intentionally.
- `spring.batch.jdbc.initialize-schema=always`: instructs Spring Boot to run the script that creates the **Spring Batch metadata schema** on the datasource detected for Batch JDBC initialization.
- `spring.datasource.generate-unique-name=true`: when Spring Boot auto-creates an embedded datasource, a distinct database name is generated per application context, reducing the risk of two test contexts accidentally sharing metadata.
- Do not set `spring.datasource.url`: if H2 is on the classpath and no other datasource configuration is present, Spring Boot can auto-provision an embedded datasource. This is the shortest path to isolated test metadata.

When using Spring Boot's standard auto-configuration, you typically **do not need** to write `@EnableBatchProcessing`, `JobRepositoryFactoryBean`, or a manual `DataSource` bean. Manually declaring infrastructure configuration can cause Boot to back off from parts of Batch auto-configuration, requiring the project to control schema initialization and wiring itself.

### 5.3. Explicit H2 URL When Intentionally Sharing a Database

A test suite may want multiple components to use the same named in-memory database:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_metadata_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
```

Here:

- `jdbc:h2:mem:batch_metadata_test` creates or attaches to a **named** H2 in-memory database inside the same JVM.
- Connections with the same URL point to the same database as long as its lifecycle permits.
- `DB_CLOSE_DELAY=-1` keeps the database alive after the last connection closes, until the JVM exits or the database is explicitly closed.
- `username=sa` and an empty password are only appropriate for local H2 testing.

**Caution:** a fixed `batch_metadata_test` name combined with `DB_CLOSE_DELAY=-1` can keep metadata alive across multiple test contexts within the same JVM. If Boot keeps running `CREATE TABLE` scripts via `initialize-schema=always`, subsequent tests may hit a "table already exists" error. When independent tests are needed, prefer unique database names or explicit context/database lifecycles; when reuse is intentional, initialize the schema exactly once.

Do not use an *unnamed* `jdbc:h2:mem:` URL for infrastructure that uses a connection pool and assume multiple connections will see the same data. In H2, an unnamed in-memory database is scoped to a single connection, which easily causes a job to create metadata on one connection while a query on another connection cannot see it.

### 5.4. Should You Set `DB_CLOSE_DELAY=-1` for Every Test?

No. If you choose `generate-unique-name=true` and let Spring Boot manage the embedded H2 datasource, you can start with the default so the lifecycle stays tied to the application context. Only add `DB_CLOSE_DELAY=-1` when you genuinely need the database to survive after the last connection closes. In exchange, you must manage distinct database names and cleanup so tests do not interfere with one another.

---

## 6. Who Creates the Metadata Schema?

There are three common strategies:

| Strategy | When Appropriate | Schema Owner |
| --- | --- | --- |
| Spring Boot Batch JDBC auto-init | Tests using embedded H2, simple schema, automatic initialization desired | `spring.batch.jdbc.initialize-schema` |
| Controlled execution of Spring Batch script | Custom infrastructure, not using default Boot Batch auto-config | `schema-h2.sql` matching the Spring Batch version |
| Flyway / Liquibase migration | Production manages schema via migrations; tests should mirror production | Application's versioned migrations |

### 6.1. Spring Boot Auto-Init

With `initialize-schema: always`, Boot runs the script matching the database platform when auto-configuration applies. For example, for H2, Spring Batch ships `org/springframework/batch/core/schema-h2.sql` inside the Spring Batch JDBC library.

Do not use auto-init and a migration that creates the same `BATCH_*` tables on the same datasource simultaneously without a conflict-avoidance strategy. One of the two mechanisms must clearly own schema creation.

### 6.2. When Using Flyway or Liquibase

When production already manages the metadata schema through migrations, integration tests can run the same migrations to test the real upgrade path:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: never

  flyway:
    enabled: true
```

The snippet above only shows **designating Flyway as the schema owner**. To work, the project must also include `flyway-core`, the proper JDBC driver, and **a migration that creates/updates the Spring Batch metadata tables**. Enabling Flyway without a migration creating `BATCH_*` will still result in missing-table errors.

With H2, production migrations sometimes contain PostgreSQL- or Oracle-specific syntax and fail to run. You can use H2-compatible test migrations to verify Batch mechanics, but you still need integration tests on the production database to prove the real migrations work in the target environment.

### 6.3. Distinguishing the Three Schema Initialization Mechanisms

- `spring.batch.jdbc.initialize-schema`: for **Spring Batch metadata**.
- `spring.sql.init.mode`: for general Spring Boot SQL scripts such as `schema.sql` and `data.sql`.
- `spring.jpa.hibernate.ddl-auto`: for JPA entities managed by Hibernate; it **does not replace** Spring Batch JDBC metadata DDL.

Setting `spring.jpa.hibernate.ddl-auto=create` is not a fix for a missing `BATCH_JOB_INSTANCE` table.

### 6.4. Multiple DataSources

For example, suppose an application has:

- `businessDataSource` connected to the invoice database.
- `batchMetadataDataSource` connected to a test H2 database used only for metadata.

In this case, explicitly configure **which datasource is for Batch**. In compatible Spring Boot versions, you can place `@BatchDataSource` on the dedicated datasource bean and configure `@Primary`/qualifiers for the remaining infrastructure. If you use `@EnableBatchProcessing` or `DefaultBatchConfiguration` manually, follow the mechanism for specifying the datasource/transaction manager of your Spring Batch version.

Two assertions worth including in a multi-datasource integration test:

1. The job runs and `BATCH_*` tables appear in the expected **metadata datasource**.
2. The business database does not unintentionally receive `BATCH_*` schema tables.

Do not assume `spring.datasource.url` is always where `JobRepository` writes metadata when the application has multiple `DataSource`s and custom configuration beans.

---

## 7. Complete Integration Test with H2 Metadata

The following example tests a simple job named `sampleImportJob`:

- The test boots Spring Boot and embedded H2.
- Spring Batch automatically initializes the JDBC repository and metadata schema.
- A tasklet writes `sample.processed=3` into the **step execution context**.
- The test calls `JobLauncherTestUtils.launchJob(...)`.
- The test reads back metadata using `JobExplorer`, confirming data was persisted and queried via the repository.
- `JdbcTemplate` queries the record count in `BATCH_JOB_EXECUTION` as an additional infrastructure check.

### 7.1. Java Code

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = EmbeddedMetadataDatabaseTest.TestApplication.class
)
@ActiveProfiles("batch-test")
class EmbeddedMetadataDatabaseTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void savesJobAndStepMetadataInEmbeddedH2() throws Exception {
        Integer before = jdbcTemplate.queryForObject(
            "select count(*) from BATCH_JOB_EXECUTION",
            Integer.class
        );

        JobParameters parameters = new JobParametersBuilder()
            .addString("run.id", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution =
            jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertNotNull(execution.getId());
        assertNotNull(execution.getJobInstance().getId());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("sampleImportStep"))
            .findFirst()
            .orElseThrow();

        assertEquals(3,
            step.getExecutionContext().getInt("sample.processed"));

        // Read back from the metadata repository, not just inspecting the object
        // returned by JobLauncher.
        JobExecution restoredJob =
            jobExplorer.getJobExecution(execution.getId());

        assertNotNull(restoredJob);
        assertEquals(execution.getId(), restoredJob.getId());
        assertEquals(BatchStatus.COMPLETED, restoredJob.getStatus());

        StepExecution restoredStep = jobExplorer.getStepExecution(
            execution.getId(),
            step.getId()
        );

        assertNotNull(restoredStep);
        assertEquals(
            3,
            restoredStep.getExecutionContext().getInt("sample.processed")
        );

        Integer after = jdbcTemplate.queryForObject(
            "select count(*) from BATCH_JOB_EXECUTION",
            Integer.class
        );

        assertNotNull(before);
        assertNotNull(after);
        assertEquals(before + 1, after);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BatchTestConfiguration.class)
    static class TestApplication {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class BatchTestConfiguration {

        @Bean
        Step sampleImportStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("sampleImportStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    contribution.getStepExecution()
                        .getExecutionContext()
                        .putInt("sample.processed", 3);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Job sampleImportJob(
                JobRepository jobRepository,
                Step sampleImportStep) {

            return new JobBuilder("sampleImportJob", jobRepository)
                .start(sampleImportStep)
                .build();
        }
    }
}
```

The test file uses the `application-batch-test.yml` configuration from Section 5.2. The test context has only one `Job` bean, so `JobLauncherTestUtils` can automatically identify the job to run. If a project contains multiple `Job` beans, explicitly set `jobLauncherTestUtils.setJob(jobUnderTest)` before calling `launchJob`.

### 7.2. Why Is This Test Meaningful?

**Verifies the repository works.** `launchJob` uses `JobLauncher` and `JobRepository` to create and update metadata. A job with `BatchStatus.COMPLETED` shows that the flow reached the completed state.

**Verifies state data was persisted.** `jobExplorer.getStepExecution(jobExecutionId, stepExecutionId)` uses the API to read metadata from the repository. Checking the `sample.processed` key on the queried result is more valuable than only reading back the original `StepExecution` object.

**Verifies the schema is in use.** `JdbcTemplate` can query `BATCH_JOB_EXECUTION`, confirming the JDBC datasource has the metadata tables. Comparing before/after counts is safer than asserting the row count equals exactly 1, because the same test context may have run another job earlier.

**Does not overclaim beyond its scope.** The test does not prove that H2 and the production database handle locking or serialization identically. It confirms that the Spring Batch JDBC pipeline and metadata APIs function under the active test configuration.

### 7.3. Why Not Put `@Transactional` on the Entire Test?

Some business integration tests annotate methods with `@Transactional` to roll back data after the test. With Spring Batch, `JobLauncher` and `JobRepository` have their own transaction boundaries; rolling back the test's transaction will not necessarily clear metadata as expected, and can even cause confusing interactions when sharing the same datasource.

If isolation is needed, prefer **a separate database per test context**, explicit data cleanup, or creating a fresh test instance, rather than relying by default on `@Transactional` on the test method to revert all metadata.

---

## 8. How to Inspect Metadata via API and SQL

### 8.1. Prefer `JobExplorer` for Spring Batch Behavior

`JobExplorer` is ideal when testing the framework's domain model:

```java
JobExecution saved = jobExplorer.getJobExecution(executionId);

assertNotNull(saved);
assertEquals(BatchStatus.COMPLETED, saved.getStatus());

StepExecution savedStep =
    jobExplorer.getStepExecution(executionId, stepExecutionId);

assertNotNull(savedStep);
assertEquals(
    3,
    savedStep.getExecutionContext().getInt("sample.processed")
);
```

You do not need to know which SQL columns store metadata, how context serialization works, or how sequence names change across upgrades.

### 8.2. Use `JdbcTemplate` When Verifying Test Database Structure

`JdbcTemplate` is suitable for infrastructure checks, counting records, or diagnostics:

```java
int instances = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_JOB_INSTANCE",
    Integer.class
);

int executions = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_JOB_EXECUTION",
    Integer.class
);

int stepExecutions = jdbcTemplate.queryForObject(
    "select count(*) from BATCH_STEP_EXECUTION",
    Integer.class
);

assertTrue(instances >= 1);
assertTrue(executions >= 1);
assertTrue(stepExecutions >= 1);
```

When testing a specific job, filter by ID or compare before/after deltas to avoid depending on unrelated records. When the schema uses a custom table prefix, update the `BATCH_*` table names accordingly.

Avoid asserting directly against raw JSON, Base64, or serialized blobs in context columns to prove business logic correctness. How Spring Batch serializes `ExecutionContext` can vary across versions or according to the configured `ExecutionContextSerializer`.

### 8.3. Checking JobInstance – JobExecution Relationships

After a job fails and restarts successfully, you typically want to assert:

- Both executions belong to **the same `JobInstance`**.
- There are two `JobExecution`s for that single instance.
- Already completed steps may be skipped on restart depending on step policy.
- The failed step reruns using the saved state.

Example assertion pattern, given two results produced by an actual restart fixture:

```java
assertEquals(
    first.getJobInstance().getId(),
    restarted.getJobInstance().getId()
);

assertNotEquals(first.getId(), restarted.getId());
assertEquals(BatchStatus.FAILED, first.getStatus());
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
```

Only an embedded database that persists metadata across two `launchJob` calls within the same JVM lets you verify this relationship.

---

## 9. Testing Restart with an Embedded Metadata Database

The key advantage of embedded JDBC metadata over a simple mock `JobRepository` is that tests can verify the lifecycle of **persisted executions**.

### 9.1. Two-Step Scenario

Suppose a job has:

```text
reportJob
   |
   v
prepareStep   -- succeeds, records COMPLETED metadata
   |
   v
publishStep   -- fails on first run
   |
   x  JobExecution #1: FAILED

Restart same JobInstance
   |
   v
prepareStep   -- typically skipped because already COMPLETED
   |
   v
publishStep   -- succeeds on second run
   |
   v
JobExecution #2: COMPLETED
```

The fixture can use an `AtomicBoolean` in the test to make `publishStep` fail exactly once. Then use **the same identifying `JobParameters`** to rerun via `JobLauncherTestUtils`.

Assertion skeleton:

```java
// reportJob: prepareStep succeeds;
// publishStep is configured by the test fixture to fail on the first attempt.
JobParameters sameParameters = new JobParametersBuilder()
    .addString("business.date", "2026-11-16")
    .toJobParameters();

failureSwitch.failNextPublish();

JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

failureSwitch.allowPublish();

JobExecution second = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.COMPLETED, second.getStatus());

assertEquals(
    first.getJobInstance().getId(),
    second.getJobInstance().getId()
);

assertNotEquals(first.getId(), second.getId());
assertEquals(1, prepareStepCounter.get());
assertEquals(2, publishStepCounter.get());
```

Here, `failureSwitch` and the two counters are fixtures that the test author wires into the tasklets. The snippet above is not a standalone runnable class without fixture definitions, but clearly illustrates **the conditions to observe**.

In a test suite that reuses a context, use a unique set of identifying parameters per scenario. On restart, reuse **that exact same parameter set**. Changing `business.date` to another value creates a new `JobInstance` and can lead to false conclusions about restart.

### 9.2. Reader/Writer Checkpoints

If a step processes in chunks and has an `ItemStream`:

```text
Execution #1:
  chunk 1 -> COMMIT -> checkpoint = 20
  chunk 2 -> COMMIT -> checkpoint = 40
  chunk 3 -> FAIL   -> not committed

H2 metadata: last saved checkpoint = 40

Execution #2 (restart same instance):
  ItemStream.open(context) receives checkpoint = 40
  continues processing from the next position
```

There are three layers to assert:

1. After the failed execution, use `JobExplorer` to read back the `StepExecution` and `ExecutionContext` and obtain the saved checkpoint.
2. On restart, record the actual checkpoint received by `ItemStream.open`; assert it equals the saved checkpoint.
3. After completion, verify business data has no missing or duplicate records and the metadata status is `COMPLETED`.

A test that only asserts an offset field on an in-memory reader object **does not prove** that data was committed to the metadata DB.

### 9.3. Restart Across Two Spring Context Creations

If both executions share a **named in-memory** H2 database, creating a second context only preserves metadata if the database instance genuinely remains alive and its lifecycle is explicitly managed. By default, embedded databases are tied to the application/test lifecycle, so do not expect a restart test across **a different JVM** to see old metadata.

If the requirement is to test restart across application shutdown/startup:

- Use H2 **file mode** in a temporary test directory with a clear lifecycle; or
- Use Testcontainers with the production database and appropriate volume/container lifetime; or
- Use a standalone integration database capable of persisting data across processes.

Using `DB_CLOSE_DELAY=-1` alone does not make in-memory H2 survive across a new JVM.

---

## 10. Test Isolation: Preventing One Test's Metadata from Affecting Another

### 10.1. Why Shared H2 Causes Flaky Tests

Metadata enforces uniqueness constraints and tight relationships among job name, parameters, instance, and execution. If two tests accidentally share H2, or a test reruns with the same parameters as a `COMPLETED` job, errors like these can occur:

```text
JobInstanceAlreadyCompleteException:
A job instance already exists and is complete
```

Or two contexts both try to initialize the schema on a shared database:

```text
JdbcSQLSyntaxErrorException:
Table "BATCH_JOB_INSTANCE" already exists
```

Or a test queries `BATCH_JOB_EXECUTION` and sees more records than expected because another test created metadata.

### 10.2. Three Levels of Isolation

| Level | Approach | Best Suited For |
| --- | --- | --- |
| Per job run | Generate unique identifying `JobParameters` | Multiple test methods sharing a Spring context and H2 |
| Per Spring test context | Use an embedded database with a unique name, e.g., `generate-unique-name=true` | Test classes with different configurations |
| Per test/process | Separate database instance or isolated test resource, cleaned up on completion | Parallel suites, complex restart tests |

One way to generate unique parameters:

```java
JobParameters unique = new JobParametersBuilder()
    .addString("test.run.id", UUID.randomUUID().toString())
    .toJobParameters();
```

However, **do not change parameters between the failed run and the restart** within the same test.

### 10.3. Do Not Clean Metadata by Deleting Arbitrary Tables

Deleting `BATCH_JOB_INSTANCE` without handling related executions and contexts can violate foreign keys. Deleting metadata tables via SQL while a job is still running can corrupt state and cause intermittent failures.

When independent tests are desired, the simplest option is usually a fresh H2 database. When a reset is genuinely required, perform ordered SQL teardown while no job is running, and manage sequences/identities and transactions carefully; otherwise, using a distinct database name or test context is less risky.

### 10.4. Do Not Overuse `@DirtiesContext`

`@DirtiesContext` forces Spring Test to recreate the context before or after a test as configured. It can solve shared bean state, but it slows down the suite and **does not automatically ensure** the old H2 database is gone if a fixed URL is combined with `DB_CLOSE_DELAY=-1`.

Prefer clean test design: unique input parameters, intentional fixture resets, and dedicated database names. Only use `@DirtiesContext` when there is a genuine bean/context lifecycle reason.

### 10.5. Parallel Tests

Tests running in parallel must not share the same:

- job name and identifying parameters when they would accidentally target the same `JobInstance`;
- global `AtomicBoolean` flags or counter fixtures that are not reset;
- fixed H2 database if each test attempts to run schema initialization;
- transaction manager or connection pool that gets shut down while another test is still using it.

If you need to test **intentional concurrent execution against the same `JobInstance`**, write a dedicated concurrency test rather than treating race conditions as accidental side effects of independent tests.

---

## 11. Common Configuration Errors and Diagnostics

### 11.1. `Table "BATCH_JOB_INSTANCE" not found`

Likely causes:

- The Spring Batch schema has not been initialized.
- `spring.batch.jdbc.initialize-schema` is still `never` or auto-init is inactive under the current configuration.
- There are multiple datasources and the schema was created on a different datasource.
- The schema script did not run or failed when the application context started.
- H2 uses an unnamed database, causing write and read connections to hit different databases.

Troubleshooting steps:

1. Check the H2 driver on the test runtime classpath and the actual datasource URL.
2. Identify which datasource `JobRepository` is using.
3. Inspect schema initialization logs and Boot Batch JDBC initializer settings.
4. Query the metadata tables with `JdbcTemplate` on **the same datasource**.
5. If infrastructure is manually configured, use migrations/scripts compatible with Spring Batch instead of expecting the default Boot initializer to run.

### 11.2. `Table already exists`

The usual cause is **re-creating the schema on an uncleaned H2 database** or having both Boot Batch auto-init and a migration create the same tables. Check `DB_CLOSE_DELAY=-1`, fixed H2 names, context caching, and duplicate initialization mechanisms.

Do not paper over this by catching and ignoring all exceptions; tests could silently read stale data and produce untrustworthy results.

### 11.3. `JobInstanceAlreadyCompleteException`

The test ran a job that was already `COMPLETED` with the same job name and identifying parameters. Generate fresh parameters for independent tests. Only keep the same parameters when **intentionally restarting a failed or stopped JobInstance that is restartable**.

### 11.4. `BadSqlGrammarException` / Column Errors in the Parameters Table

If this occurs on `BATCH_JOB_EXECUTION_PARAMS`, check whether a Spring Batch 4.x script is being used with a Spring Batch 5.x runtime. Also check custom table prefix settings, database platform, and migration version.

### 11.5. `Cannot determine embedded database driver class`

This occurs when Spring Boot has no configured JDBC URL/driver and finds no embedded driver on the test classpath. Check `testRuntimeOnly 'com.h2database:h2'` and confirm the test run is actually using the Gradle test runtime classpath.

### 11.6. Metadata Suddenly Disappears Between Two Steps

Situations to check:

- The test created a new datasource pointing to a different H2 database.
- An unnamed H2 database was opened on another connection.
- The last connection closed and the database was destroyed due to the default lifecycle.
- The test attempted a restart across another JVM while still using in-memory H2.
- A prior test or teardown cleaned the schema.

If metadata must persist within the same JVM across connections, use a named H2 database and control connection/lifecycle. If metadata must persist across JVMs, choose a persistent database.

### 11.7. `JobLauncherTestUtils` Does Not Know Which Job to Run

If there are multiple `Job` beans, `@SpringBatchTest` cannot uniquely determine the job automatically. In the test, inject the target `Job` using a qualifier and call:

```java
jobLauncherTestUtils.setJob(jobUnderTest);

JobExecution execution =
    jobLauncherTestUtils.launchJob(uniqueParameters);
```

This is a **test job selection** issue, not an H2 error.

### 11.8. Tests Pass on H2 but Fail on PostgreSQL/Oracle

Possible reasons:

- Different isolation levels when creating `JobExecution` concurrently.
- Different SQL locking or ID generation sequences.
- Different SQL dialects or data types.
- Clock skew, timezones, or timestamp precision differences.
- Incompatible production migrations.
- Different connection pool limits, deadlocks, and transaction timeouts.

H2 speeds up testing Batch logic, but it does not replace integration tests on the target database.

---

## 12. Embedded Metadata Databases and Other Test Types

Not every Spring Batch test needs H2.

| Test Goal | Needs an Embedded Metadata DB? | Suitable Tool |
| --- | --- | --- |
| Test pure Java data transformation functions | No | JUnit with input/output objects |
| Test an independent processor | No | `ItemProcessor` unit test |
| Test how a reader stores offsets in an in-memory `ExecutionContext` | Not necessarily | `ItemStream.open/update` with a simulated `ExecutionContext` |
| Test a tasklet writing a key into `StepExecution` | Not necessarily | `MetaDataInstanceFactory` in `spring-batch-test` |
| Test Job/Step wiring, repository, status after launch | Yes, if using a JDBC repository | Embedded H2 + `@SpringBatchTest` |
| Test repository-persisted metadata, in-JVM restart | Yes | H2/HSQLDB with matching schema version |
| Test production-like transactions and locking | H2 is usually insufficient | Testcontainers with the production DB |
| Test restart across JVM/process boundaries | In-memory DB is insufficient | File-backed DB or database service |

Newer Spring Batch versions offer lightweight repository options for use cases that do not need persistent restart, such as `ResourcelessJobRepository` in Spring Batch 5.2+. However, if the test's goal is to **verify JDBC metadata, execution history, or restart**, use a JDBC repository with a real database, even if embedded for testing.

### 12.1. Choosing Between `@SpringBatchTest`, `@SpringBootTest`, and Test Slices

- `@SpringBatchTest` registers batch test utilities such as `JobLauncherTestUtils` and the appropriate test execution listeners.
- `@SpringBootTest` loads the Spring Boot application context, enabling tests with datasources, auto-config, and real `Job`/`Step` beans.
- Test slice annotations like `@JdbcTest` or `@DataJpaTest` narrow the Spring context scope. They are useful when testing JDBC/JPA in isolation, but **do not load the full Batch infrastructure by default** to call `launchJob`.

You can combine `@SpringBatchTest` with `@SpringBootTest` to write full-job integration tests as shown in Section 7.

### 12.2. Metadata Tests Should Observe Both Status and Business Data

A job can record `COMPLETED` metadata while the business outcome is still wrong if a step misbehaves. Conversely, a writer might persist data while metadata fails to commit in the same transaction or errors unexpectedly.

Therefore, a well-designed integration test usually has two groups of assertions:

- **Batch metadata:** status, counts, execution context, run count, instance/execution relationships.
- **Business outcome:** record counts, ID sets, checksums, output files, or emitted events, depending on the job.

These two groups answer different questions and complement each other.

---

## 13. A Practical Workflow for Projects

When creating a test module for a new Spring Batch job, you can follow this sequence:

### Step 1 — Identify Metadata Responsibility

Determine whether the project uses:

- a single shared `DataSource` for metadata and business data; or
- two separate `DataSource`s.

Decide what tests need H2 for metadata and whether business SQL needs separate testing.

### Step 2 — Choose Database Lifecycle

For fast independent tests:

```text
H2 in-memory
  -> separate database per Spring test context
  -> initialize schema once
  -> each test uses its own identifying parameters
  -> job runs, metadata is asserted
  -> context/database is closed when the test finishes
```

For restart tests within the same JVM: use a single database instance that remains continuously alive across both the failed run and the subsequent run.

### Step 3 — Choose Exactly One Schema Owner

Choose one of:

- Spring Boot `spring.batch.jdbc.initialize-schema=always` for simple test setups.
- Explicit SQL initialization for custom Batch configurations.
- Versioned migrations if the schema is managed by Flyway/Liquibase.

### Step 4 — Build a Baseline Integration Test

Use `@SpringBatchTest` + `@SpringBootTest` to verify:

1. The job launches with unique identifying parameters.
2. `JobExecution` and `StepExecution` records are created.
3. Status and execution context are written accurately.
4. `JobExplorer` reads the metadata back.
5. SQL metadata tables are ready when infrastructure checks are needed.

### Step 5 — Add Failure and Restart Scenarios

Make a step fail at a controlled point; keep the identifying job parameters identical; assert run counts, persisted checkpoints, continuation capability, and output data.

### Step 6 — Supplement with Production-Engine Tests When Needed

If the job has strict requirements around transactions, locking, vendor SQL, or schema migrations, add integration tests using Testcontainers or an environment running a production-equivalent database.

---

## 14. Exercises

### Exercise 1 — Create H2 Metadata and Inspect Tables

Create a Spring Boot test with `spring-batch-test` and H2 dependencies. Disable job auto-run, enable Batch JDBC schema initialization, and configure a unique database name. Create a single-step job that completes and run it via `JobLauncherTestUtils`.

Requirements: assert `COMPLETED`, `BATCH_JOB_EXECUTION` count increases by 1, and `JobExplorer` reads back the `JobExecution` with the exact ID and status.

### Exercise 2 — Verify Persisted `ExecutionContext`

In a tasklet, write two keys `sample.total=15` and `sample.stage="IMPORTED"` to the step context. After the step finishes, read back the `StepExecution` using `JobExplorer` and assert both keys have the right values and types.

Extension: configure `ExecutionContextPromotionListener` to promote only `sample.total` to the job context; verify the other key is not promoted.

### Exercise 3 — Detect Test Data Collisions

Run the same job twice with the same identifying parameters after the first run is `COMPLETED`. Observe `JobInstanceAlreadyCompleteException`. Then change the parameters to unique values and confirm a different `JobInstance` is created.

Explain: why is changing parameters appropriate for **two independent tests** but inappropriate for testing **restart**?

### Exercise 4 — Testing Restart

Create a two-step job: `prepareStep` succeeds and `publishStep` fails on the first run. Rerun with the same identifying parameters after clearing the fault. Assert:

- The first run is `FAILED` and the second run is `COMPLETED`.
- Both `JobExecution`s share the same `JobInstance`.
- `prepareStep` does not reprocess under the default configuration for completed steps.
- Metadata read from `JobExplorer` matches these states.

### Exercise 5 — Separating Business and Metadata DataSources

Configure one H2 datasource for Batch metadata and another datasource for business data. Prove that `BATCH_*` resides in the metadata datasource, business data resides in its designated store, and tests can run independently.

---

## 15. Checklist Before Adding Tests to CI

- **Matching versions:** Spring Batch runtime and metadata DDL/migrations belong to the same generation.
- **Correct datasource:** `JobRepository` points to the expected test H2 database.
- **Single init owner:** either Batch auto-init or migrations are explicitly chosen.
- **Isolation:** independent tests do not accidentally reuse DB names or JobInstances.
- **Restart:** when testing restart, both runs use the same identifying parameters and the repository retains metadata.
- **Meaningful assertions:** read back metadata via `JobExplorer` rather than asserting only in-memory objects.
- **Appropriate coverage:** for complex SQL, concurrency, and transactions, include tests on the production database or an equivalent.

An embedded database is a tool for speeding up integration test feedback. Its greatest value lies in keeping **a real `JobRepository` and metadata lifecycle** active in tests: we can observe Spring Batch creating instances, recording executions, saving contexts, and deciding restarts through the framework APIs, while maintaining full control over isolation and data lifecycle.

## 16. Further Reading

- Spring Batch Reference: *Job Repository*, *Job Metadata*, *Unit Testing*, *Configuring and Running a Job*, *ExecutionContext*, *Batch Metadata Schema*.
- Spring Batch Javadoc: `JobRepository`, `JobExplorer`, `JobLauncherTestUtils`, `ExecutionContext`, `MetaDataInstanceFactory`.
- Spring Boot Reference: *Batch Applications* and *Database Initialization*.
- H2 Database Documentation: *In-Memory Databases* and JDBC URL parameters such as `DB_CLOSE_DELAY`.
- Testcontainers Documentation: integrating relational database containers with Spring Boot tests.
