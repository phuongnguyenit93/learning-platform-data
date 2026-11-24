# Database Test Schema in Spring Batch

## 1. What is a database test schema?

In Spring Batch testing, a **database test schema** is the structure of database objects required by the test environment so a batch job or step can operate and tests have deterministic data. Here, schema includes tables, columns, primary keys, foreign keys, sequences or ID-generation tables, indexes, and necessary constraints. Depending on the database management system, the word *schema* can also mean a namespace, such as `batch_test` in PostgreSQL; distinguish that namespace from the set of DDL scripts creating the tables.

A batch test using JDBC typically needs **two schema groups**:

1. **Spring Batch metadata schema**: the `BATCH_*` tables used by `JobRepository` to record job instances, job executions, step executions, parameters, and `ExecutionContext`.
2. **Application business schema**: the tables holding input data, processing results, staging tables, or reconciliation tables manipulated by readers, processors, writers, or tasklets.

For example, an order-processing job may read records from `TEST_ORDER` and update `STATUS`. At the same time, Spring Batch writes run metadata to `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION`. **Having the business tables alone is not enough to run a job with a JDBC `JobRepository`**, and conversely, having the `BATCH_*` tables does not mean the reader has data to read.

```text
                   Spring Batch job
                          |
             +------------+------------+
             |                         |
     JobRepository (metadata)     Reader / Writer / Tasklet
             |                         |
    +--------v---------+       +-------v---------+
    | BATCH_JOB_*      |       | TEST_ORDER      |
    | BATCH_STEP_*     |       | TEST_PAYMENT ...|
    +------------------+       +-----------------+
      Framework schema           Business schema
```

These tables can live in the same test database or be separated into different databases/schemas when required by application configuration. In the examples below, both groups share an **H2 in-memory database**, which is sufficient for many basic integration tests.

## 2. When is a database schema needed in tests?

| Test type | Real schema needed? | Reason |
|---|---|---|
| Pure unit test for processor, validator, or business function | Usually no | Pass objects directly, mock dependencies; no repository runs. |
| Listener unit test with `MetaDataInstanceFactory` | No | Creates `StepExecution` in memory; does not use JDBC. |
| DAO/reader/writer test executing SQL queries | Business schema | Requires tables, fixture data, and SQL statements actually running. |
| Step/job execution test with JDBC `JobRepository` | Metadata schema and usually business schema | Framework must persist execution state and application code needs its tables. |
| Restart/checkpoint test after failure | Durable metadata schema across test runs | Needs to inspect `ExecutionContext`, status, and relationships between executions. |
| SQL compatibility, locking, transaction test with PostgreSQL/MySQL/Oracle | Should use the exact target database type | H2 does not fully emulate SQL syntax, locking, isolation, and ID generation mechanisms. |

Key takeaway for the **Test data** chapter: the schema defines *how test data can exist*, whereas fixtures define *the specific records present before each test*. Do not mix these two responsibilities when designing tests.

## 3. Core Spring Batch metadata tables

Spring Batch uses metadata tables to manage execution. For the Spring Batch 5.x line, the main tables are:

| Table | Stored content | Primary relationships |
|---|---|---|
| `BATCH_JOB_INSTANCE` | A logical job instance: job name, job key, ID, and version | One instance can have multiple job executions. |
| `BATCH_JOB_EXECUTION` | A single execution attempt: ID, timestamps, `BatchStatus`, `ExitStatus`, version... | References `BATCH_JOB_INSTANCE`. |
| `BATCH_JOB_EXECUTION_PARAMS` | `JobParameters`: name, type, value, and `IDENTIFYING` flag | Belongs to a job execution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-level `ExecutionContext` | Tied to a job execution. |
| `BATCH_STEP_EXECUTION` | A step execution attempt: read/write/skip/commit/rollback counts, status, timestamps... | References `BATCH_JOB_EXECUTION`. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step-level `ExecutionContext`, often holding checkpoints | Tied to a step execution. |

Logical relationships:

```text
BATCH_JOB_INSTANCE
      |
      +--< BATCH_JOB_EXECUTION
                 |
                 +--< BATCH_JOB_EXECUTION_PARAMS
                 +--- BATCH_JOB_EXECUTION_CONTEXT
                 +--< BATCH_STEP_EXECUTION
                           |
                           +--- BATCH_STEP_EXECUTION_CONTEXT
```

`BATCH_JOB_INSTANCE` represents a logical run identified by the job name and *identifying job parameters*; when re-running an instance, the repository can gain additional `JobExecution`s. `BATCH_STEP_EXECUTION` corresponds to a step execution attempt, so a step with the same name can have multiple records across runs/restarts.

For ID generation, the DDL also creates objects such as `BATCH_JOB_SEQ`, `BATCH_JOB_EXECUTION_SEQ`, and `BATCH_STEP_EXECUTION_SEQ`. Depending on the database, these are **real sequences** or **sequence-emulating tables**; do not assume every DBMS uses identical syntax.

### 3.1. Versioned metadata schema

The DDL must match the **Spring Batch version** being run. For example, Spring Batch 5.x uses the columns `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, and `IDENTIFYING` in `BATCH_JOB_EXECUTION_PARAMS`. The Spring Batch 4.x schema used an older layout with columns such as `KEY_NAME`, `TYPE_CD`, `STRING_VAL`, `LONG_VAL`, `DATE_VAL`, and `DOUBLE_VAL`.

Therefore, never grab an arbitrary `schema-*.sql` file from the Internet and apply it to a newer version. When upgrading Spring Batch, check the **migration scripts** and official upgrade guides, especially if existing job metadata must be preserved.

Database-specific DDL files are distributed with `spring-batch-core`, for example:

```text
org/springframework/batch/core/schema-h2.sql
org/springframework/batch/core/schema-postgresql.sql
org/springframework/batch/core/schema-mysql.sql
```

The configuration examples below target **Spring Boot 3.x + Spring Batch 5.x + JUnit 5**. Package/API names and configuration properties may differ in Spring Boot 4.x/Spring Batch 6.x; consult the documentation for your project's version.

## 4. Designing the test database: H2, real databases, and migrations

### 4.1. H2 in-memory

H2 is fast and well suited for tests that verify simple flows, JDBC CRUD, record counts, and batch status. The database is created when tests connect to a `jdbc:h2:mem:...` URL and lives according to the configured connection/process lifecycle.

Benefits:

- No need to start a separate database server.
- Easy to recreate the schema during Spring context startup.
- Easy to clean data between tests.

Limitations: H2's SQL syntax, data types, sequences, transaction isolation, locking, and concurrency mechanisms are **not identical** to PostgreSQL/MySQL/Oracle. A test passing on H2 is not enough to prove application SQL is production-compatible.

### 4.2. Real database via Testcontainers

For vendor-specific SQL statements, `JdbcPagingItemReader`, `JdbcBatchItemWriter`, or vendor-sensitive transaction/restart behavior, you can run PostgreSQL/MySQL in a container and create the test schema there. The database remains ephemeral, but its engine and dialect are much closer to production.

### 4.3. Schema managed by Flyway/Liquibase

If the system already uses Flyway or Liquibase, integration tests should run the **same required migrations** to build the schema. When migrations also manage the `BATCH_*` tables, disable Spring Batch's automatic schema initialization to avoid *table already exists* errors. Migration tests should verify the actual upgrade steps, not just the latest schema.

## 5. Complete example: creating a test schema with Spring Boot and H2

Suppose we need to test a batch job that updates `TEST_ORDER.STATUS` from `NEW` to `DONE`. We want Spring Batch to store metadata in this same H2 database.

### 5.1. Gradle dependencies

Groovy `build.gradle` example, with the Spring Boot BOM/plugin managing dependency versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If the application already includes Spring Boot Starter Test, keep the existing dependency rather than declaring duplicates. Ensure `spring-batch-test` matches the compatible `spring-batch-core` line.

### 5.2. Dedicated configuration for the test profile

Create `src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-test.sql
```

Meaning:

| Configuration | Role |
|---|---|
| `spring.datasource.url` | Connects to an in-memory H2 database named `batch_test`. |
| `DB_CLOSE_DELAY=-1` | Keeps the database in memory after the last connection closes, until the JVM exits. |
| `spring.batch.job.enabled=false` | Prevents jobs from auto-launching on Spring Boot startup; the test explicitly invokes the launcher. |
| `spring.batch.jdbc.initialize-schema=always` | Initializes `BATCH_*` metadata tables/sequences from the platform-specific script, even on non-embedded databases. |
| `spring.sql.init.schema-locations` | Runs DDL creating the test's **business tables**. |
| `spring.sql.init.mode=always` | Tells Boot to execute SQL initialization; useful when switching to an out-of-process test database. |

The two SQL initialization mechanisms here serve different purposes: `spring.batch.jdbc.*` is for Spring Batch metadata, while `spring.sql.init.*` is for the application-controlled business schema. In this example, the business DDL does not depend on `BATCH_*` tables, so no ordering between them needs to be specified.

**Never use `initialize-schema: always` on a production database containing real metadata.** In production, manage DDL via the application's migrations/deployment policy; enable the property above only in an isolated test profile.

### 5.3. Business DDL file

Create `src/test/resources/sql/schema-test.sql`:

```sql
CREATE TABLE TEST_ORDER (
    ID BIGINT PRIMARY KEY,
    CUSTOMER_CODE VARCHAR(40) NOT NULL,
    AMOUNT DECIMAL(12, 2) NOT NULL,
    STATUS VARCHAR(16) NOT NULL
);

CREATE INDEX IDX_TEST_ORDER_STATUS ON TEST_ORDER (STATUS);
```

This is a minimal schema to stay focused on batch behavior. In real projects, reflect the constraints that business logic relies upon: `NOT NULL`, unique keys, foreign keys, lengths, precision, indexes, and critical data types. Omitting constraints compared to production can cause tests to miss failures that only occur on a real database.

### 5.4. Separating seed data from DDL

Create `src/test/resources/sql/seed-test-order.sql`:

```sql
INSERT INTO TEST_ORDER (ID, CUSTOMER_CODE, AMOUNT, STATUS) VALUES
    (1, 'CUSTOMER-A', 150.00, 'NEW'),
    (2, 'CUSTOMER-B', 245.75, 'NEW'),
    (3, 'CUSTOMER-C', 399.00, 'HOLD');
```

Create `src/test/resources/sql/cleanup-test-order.sql`:

```sql
DELETE FROM TEST_ORDER;
```

Do not put this test-specific fixture data into `schema-test.sql`: the schema creates structure once when the context starts, whereas seed data must be recreated for each test method. With `@Sql`, each test's data is re-established at the right lifecycle point.

## 6. Sample job using the test schema

To illustrate the role of the schema, here is a minimal job using `JdbcTemplate` to update `NEW` orders. The example is compatible with the Spring Batch 5.x builder API:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderProcessingJobConfig {

    @Bean
    public Step processOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("processOrdersStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    jdbcTemplate.update("""
                            UPDATE TEST_ORDER
                            SET STATUS = 'DONE'
                            WHERE STATUS = 'NEW'
                            """);
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job processOrdersJob(
            JobRepository jobRepository,
            Step processOrdersStep) {

        return new JobBuilder("processOrdersJob", jobRepository)
                .start(processOrdersStep)
                .build();
    }
}
```

This example uses a tasklet just to observe the data; in a chunk-oriented step, the reader/processor/writer can use the exact same schema. The `JobRepository`, `PlatformTransactionManager`, and `JdbcTemplate` beans are supplied by Spring Boot/JDBC auto-configuration. In a test, you can import this configuration if it is not already within the application's component scan.

One common misconception: the `UPDATE` statement modifies **two rows** in `TEST_ORDER`, yet the tasklet's `StepExecution.getWriteCount()` does not automatically increment to 2. Spring Batch read/write counters are tied to item/chunk processing; do not infer them from the row count modified by an arbitrary SQL statement.

## 7. Integration test running the job and verifying data

Spring Batch provides `@SpringBatchTest` and `JobLauncherTestUtils` for integration testing. This test verifies both business data and metadata stored in the test database.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
@Import(OrderProcessingJobConfig.class)
@Sql(scripts = "/sql/seed-test-order.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/cleanup-test-order.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
class OrderProcessingJobIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("processOrdersJob")
    private Job processOrdersJob;

    @BeforeEach
    void setUp() {
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(processOrdersJob);
    }

    @AfterEach
    void tearDown() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void processesOnlyNewOrdersAndPersistsExecutionMetadata()
            throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addLong("run.id", 565L)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer doneCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'DONE'",
                Integer.class);
        Integer holdCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'HOLD'",
                Integer.class);

        assertEquals(2, doneCount);
        assertEquals(1, holdCount);

        Long persistedExecutions = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM BATCH_JOB_EXECUTION
                WHERE JOB_EXECUTION_ID = ?
                """,
                Long.class,
                execution.getId());

        assertEquals(1L, persistedExecutions);
    }
}
```

With a Spring Boot application having a valid `@SpringBootApplication`, `@SpringBootTest` builds the context, `@ActiveProfiles("test")` loads `application-test.yml`, and `@Import` brings the demo job into the context. If this job is already picked up by component scan, importing it again is unnecessary.

Test execution flow:

1. Spring creates the H2 datasource; the `BATCH_*` metadata tables and `TEST_ORDER` are initialized.
2. `@Sql` inserts three orders before the test method runs.
3. The test prepares `JobParameters`, then calls `JobLauncherTestUtils.launchJob(...)`.
4. `JobRepository` writes `JobExecution`/`StepExecution`; the tasklet updates the two orders with status `NEW`.
5. Assertions verify the job `COMPLETED`, the business data is correct, and the corresponding metadata record exists.
6. Cleanup removes test repository metadata and deletes the test business data.

`JobRepositoryTestUtils.removeJobExecutions()` operates on **all job executions in that repository**. Only use it when the database/repository is dedicated to tests and tests sharing a repository do not run in parallel. The test does not annotate the entire test method with `@Transactional`: when running a real batch job, step transactions must be managed according to the batch configuration; an outer test transaction can cause results that diverge from production behavior.

## 8. Inspecting metadata schema with SQL

Read queries can be helpful for identifying which jobs/steps ran. For example:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID;
```

Reading step details:

```sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Reading parameters in the Spring Batch 5.x schema:

```sql
SELECT PARAMETER_NAME, PARAMETER_TYPE, PARAMETER_VALUE, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = ?;
```

These queries are useful when debugging tests, but primary assertions should prefer public APIs (`JobExecution`, `StepExecution`, `JobRepository`) unless the goal directly concerns SQL structure. That avoids coupling tests too tightly to internal schema details that may change across upgrades.

### 8.1. Do not directly update metadata to simulate status

A common anti-pattern:

```sql
-- Do not use this to simulate a restart in ordinary tests:
UPDATE BATCH_JOB_EXECUTION SET STATUS = 'FAILED'
WHERE JOB_EXECUTION_ID = 123;
```

Batch state also involves `ExitStatus`, step executions, the version column used for optimistic locking, and `ExecutionContext`. Editing a single column directly can leave metadata inconsistent. To test restarts, intentionally induce a failure in the first step, let the framework persist the state, and then run again with the same identifying parameters to verify the outcome.

## 9. Isolating data between tests

**Test data must have a clear lifecycle.** If test A leaves behind `BATCH_JOB_EXECUTION` or `TEST_ORDER` rows, test B may fail when running in the same suite, even if it passes when run alone.

Common mechanisms:

| Mechanism | Advantage | Caveat |
|---|---|---|
| Different in-memory database per suite/class | Isolates data, avoids ID conflicts | Extra time spent creating Spring contexts and schemas. |
| `@Sql` to seed before and clean up after each test | Readable fixtures, predictable results | Cleanup must respect foreign-key order. |
| `JobRepositoryTestUtils.removeJobExecutions()` | Clears execution metadata for test independence | Clears the entire repository; use only with a dedicated test repository. |
| `@DirtiesContext` | Re-initializes the Spring context after the test | High overhead; not a default solution for every test. |
| Separate database/container per test class or group | Close to production DBMS, reduces data leakage | Requires managing container lifecycle and startup time. |

Do not `TRUNCATE BATCH_JOB_INSTANCE` before child tables. Foreign keys and ID-generation sequences/tables make deleting metadata via SQL error-prone or inconsistent across database vendors. If SQL cleanup is unavoidable, define an explicit dependency order and restrict it to an isolated test database. With multi-threaded applications or parallel test execution, a shared database combined with global cleanup is a very common cause of flaky tests.

### 9.1. `JobInstanceAlreadyCompleteException` and identifying parameters

For a JDBC `JobRepository`, the job name and `JobParameters` flagged `IDENTIFYING` determine the logical job instance. Re-running an instance that has `COMPLETED` is normally rejected with `JobInstanceAlreadyCompleteException`.

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addLong("run.id", 1L)
        .toJobParameters();
```

If two tests produce the same parameters without clearing metadata, they can collide on the same job instance. There are three main approaches: use separate databases/repositories, clean metadata after each test, or use distinct identifying parameters when each run **truly** represents a new instance. For restart tests, intentionally keep the same identifying parameters to test restart behavior; do not add a new `run.id` merely to dodge collisions.

### 9.2. Transactions and `@Sql`

`@Sql` can participate in the test's transaction, depending on `SqlConfig` and transaction manager configuration. When a real job runs, steps also have their own transactions. To keep realistic tests easy to follow, the example above does not place `@Transactional` on the test class/method and uses explicit seed/cleanup scripts. If you need to test rollback, design a dedicated scenario for a **step** or **chunk** transaction, then verify committed/rolled-back data alongside metadata after the job finishes.

## 10. When real PostgreSQL is needed: Testcontainers

If production uses PostgreSQL, tables created in H2 may fail to catch vendor-specific SQL bugs. With Spring Boot 3.1+ and Testcontainers, you can spin up an ephemeral PostgreSQL database for integration tests.

Declare dependencies (Boot BOM/Testcontainers BOM manage compatible versions):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Test skeleton example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgreSqlBatchSchemaIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void contextStartsWithDatabaseSchema() {
        // Here you can run the job and verify data as in the H2 example.
    }
}
```

With the `test-postgres` profile, do not hardcode an H2 URL. `@ServiceConnection` provides connection details from the container. If Flyway/Liquibase is not used, set `spring.batch.jdbc.initialize-schema=always` in this profile and initialize the PostgreSQL-compatible business DDL; Spring Boot will pick the metadata script matching the database platform. If `BATCH_*` tables are already managed by migrations, set `initialize-schema=never` to avoid duplicate creation.

Testcontainers requires an available Docker/container runtime. Depending on requirements, you can use one container per class or configure reuse across the suite; whenever sharing a database, design isolation alongside it. The code above illustrates database connectivity; to prove tables/schemas and the job work, add actual assertions as shown in section 7.

## 11. Migrations and customizing schema names

In projects using PostgreSQL, metadata may be organized in a dedicated schema, such as `batch_meta`, and business data in `app_data`. This separation helps with access permissions and data organization, but DDL, JDBC schema/search path, and the `JobRepository` table prefix configuration must all align.

If you change the default `BATCH_` table prefix, you must prepare matching DDL and adjust repository configuration, including ID generation. Renaming tables only in test SQL is not enough. Spring Batch's default SQL scripts do not automatically understand arbitrary custom prefixes/schemas.

A maintainable strategy:

1. Define migrations for metadata (if the application is responsible for managing it) and business tables.
2. In tests, start a clean database and run migrations just like in production.
3. Load fixtures via `@Sql`, builders, or test data factories.
4. Run the job/step and assert output data.
5. Clean up or tear down the database once the test completes.

**Do not combine two DDL owners for the same table.** For instance, if Flyway has already created `BATCH_JOB_INSTANCE`, running `spring.batch.jdbc.initialize-schema=always` at the same time can fail startup because the table already exists. The Spring Batch schema initializer fits clean test databases when no other migration tool manages metadata.

## 12. Common errors and troubleshooting

| Symptom | Possible cause | Where to check |
|---|---|---|
| `Table BATCH_JOB_INSTANCE not found` | Metadata not initialized or wrong datasource/schema | Check `spring.batch.jdbc.initialize-schema`, active profile, platform, and `JobRepository` datasource. |
| `Table TEST_ORDER not found` | Business DDL did not run | Check `spring.sql.init.schema-locations`, classpath location, and table/schema name. |
| `BATCH_JOB_SEQ`/`BATCH_STEP_EXECUTION_SEQ` does not exist | DDL missing ID-generation objects or using another database's script | Use the full schema script matching the vendor and Batch version. |
| `Table ... already exists` on startup | Schema created twice or an old database persisted | Check Flyway/Liquibase, Batch initializer, SQL initializer, and DB lifecycle. |
| `JobInstanceAlreadyCompleteException` | Re-running the same identifying parameters of a completed job | Clean up metadata or use a new job instance as intended; for restart tests keep the instance. |
| Wrong column type in `BATCH_JOB_EXECUTION_PARAMS` | Schema from a different Spring Batch version | Cross-check schema/migrations for the version in use. |
| Tests pass individually but fail across the suite | Fixture/metadata leaks between tests or conflicting cleanup | Separate databases, reset data in the proper scope, avoid sharing repositories during parallel runs. |
| Query succeeds on H2 but fails on PostgreSQL | Differences in dialect, data types, locking, or transaction semantics | Run integration tests on the target engine using Testcontainers or a real test database. |
| Job runs immediately on Spring context startup | Job auto-run is enabled | Set `spring.batch.job.enabled=false` in the test profile. |

In some cases, error messages only surface when `launchJob()` is called rather than when the context finishes initializing. Therefore, a smoke test that only checks context loading cannot replace an integration test that executes the job and asserts on data.

## 13. Principles for designing reliable database test schemas

When creating a new test suite for a Spring Batch module, explicitly determine:

1. **Test type:** Does a unit test truly need a database? If not, use plain objects or `MetaDataInstanceFactory`.
2. **Framework version:** The `BATCH_*` schema must match the application's Spring Batch 5.x/6.x version; do not pull DDL from another version.
3. **Database engine:** H2 for fast feedback loops; real PostgreSQL/MySQL/... for dialect-dependent behavior.
4. **Schema owner:** Spring Batch initializer, Spring SQL initialization, Flyway, or Liquibase? Each table should have only one owner for initialization.
5. **Initial data:** Separate DDL from seed fixtures, explicitly constraining expected rows and edge cases.
6. **Test lifecycle:** Recreate fixtures before each test; clean up data and metadata in the right test database afterward.
7. **Parallelism safety:** Do not share a single `JobRepository` if concurrent tests delete all of each other's executions.
8. **Assertions:** Check both job/step status and business data; checking only `BatchStatus.COMPLETED` is usually insufficient.
9. **Restart tests:** Induce a real failure and re-run, keeping metadata/checkpoints and identifying parameters intact; never manually edit a status column to fake a restart.

### Practice exercises

Extend the `TEST_ORDER` example:

- Add a `CHECK (AMOUNT >= 0)` constraint and write a test verifying that invalid records are rejected.
- Add a test seed containing only `HOLD` orders; verify that the job completes without modifying any rows.
- Create a job that intentionally fails after saving a checkpoint; verify the `FAILED` status in metadata, then re-launch with the same identifying parameters to observe restart according to step configuration.
- Re-run the SQL test on PostgreSQL Testcontainers and verify the corresponding DDL/transaction behavior.

Through these exercises, the schema is not just a mandatory setup step: it becomes part of the **test contract**, ensuring input data, constraints, execution metadata, and post-batch state can all be verified.

## 14. References

- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): table structure, sequences, and metadata relationships.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, step-scope testing.
- [Spring Boot Reference — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): SQL initialization, Batch schema initialization, Flyway, and Liquibase.
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, connecting databases used in tests.

