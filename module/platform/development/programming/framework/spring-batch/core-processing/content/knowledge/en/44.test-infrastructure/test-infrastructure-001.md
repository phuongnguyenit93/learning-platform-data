# JobRepository for Testing in Spring Batch

## 1. The Role of JobRepository in Testing

Spring Batch does not only read and write business data. Each time a Job runs, the framework also manages the identity of the processing run, execution status, errors, attempt counts, and checkpoint data. **JobRepository** is the infrastructure responsible for storing this metadata.

A Job test may finish with a success status and still miss critical bugs: losing checkpoints, initializing the wrong JobInstance, re-running an already completed Step, or treating a restart as a brand-new run. Therefore, Batch infrastructure tests must prove that metadata is **written, read back, and persisted across executions**.

Lesson objectives:

- Understand the responsibility of JobRepository compared to JobLauncher, JobOperator, and JobExplorer.
- Choose the appropriate repository for unit tests, integration tests, and restart tests.
- Create a dedicated **JDBC JobRepository** for testing, along with the Batch schema and business database.
- Use **@SpringBatchTest**, **JobRepositoryTestUtils**, and the test job-launching utility.
- Query JobInstance, JobExecution, StepExecution, and ExecutionContext after a Job runs.
- Clean up metadata safely between tests without losing history during a restart scenario.
- Understand configuration differences between Spring Batch 5.x and 6.x.

## 2. What JobRepository Stores

~~~text
JUnit Jupiter
     |
     v
@SpringBatchTest
     |
     +--> JobLauncher / JobOperator ----> Job ----> Step
     |                                      |
     |                                      v
     |                                 Business DB
     |
     +--> JobRepository ----------------> Metadata DB
     |                                      |
     |                                      +-- BATCH_JOB_INSTANCE
     |                                      +-- BATCH_JOB_EXECUTION
     |                                      +-- BATCH_JOB_EXECUTION_PARAMS
     |                                      +-- BATCH_JOB_EXECUTION_CONTEXT
     |                                      +-- BATCH_STEP_EXECUTION
     |                                      +-- BATCH_STEP_EXECUTION_CONTEXT
     |
     +--> JobExplorer ------------------> Read metadata
     |
     +--> JobRepositoryTestUtils -------> Create/delete test metadata
~~~

| Component | Meaning |
| --- | --- |
| **JobInstance** | A logical business run, identified by the Job name and identifying JobParameters. |
| **JobExecution** | A single attempt to execute a JobInstance; one instance can have multiple executions on restart. |
| **StepExecution** | The state of a Step during a single execution, including read/write, commit, rollback, and error counts. |
| **ExecutionContext** | Key/value data stored at Job or Step scope to recover state, such as a checkpointed read position. |
| **JobRepository** | API to create, update, and retrieve metadata for the objects above. |
| **JobExplorer** | API to look up Job/Step history, suitable for read-only assertions. |
| **JobRepositoryTestUtils** | A spring-batch-test utility to prepare or clean up metadata in the test database. |

For example, with the Job name **importOrders** and identifying parameter **businessDate=2026-11-16**, the first run fails and the next run restarts:

~~~text
JobInstance #25
  name = importOrders
  identifying parameter = businessDate:2026-11-16
  |
  +-- JobExecution #87: FAILED
  |     +-- validateStep: COMPLETED
  |     +-- importStep: FAILED
  |
  +-- JobExecution #88: COMPLETED
        +-- importStep: COMPLETED
~~~

The two JobExecutions have different IDs but share the same JobInstance ID. JobRepository must preserve this; if a test uses a new identifying parameter on the second execution, the framework creates a different JobInstance and the test fails to verify restartability.

**ExecutionContext must actually be persisted**, not merely live in a Java object on the heap. For instance, a JDBC cursor reader can save its checkpoint position in the Step ExecutionContext before transaction commit. After a failure, the new StepExecution uses the saved data to resume.

## 3. Which Repository Should You Use in Tests?

| Test Type | Implementation Approach | What Can It Prove? |
| --- | --- | --- |
| Unit test for processor/validator/listener | Mocks or domain fixtures via MetaDataInstanceFactory; no need to run a real Job | Local component logic. |
| Integration test for Job, execution status, restart | **JDBC JobRepository** on H2 or a test database | Persisted metadata, JobInstance/execution IDs, checkpoints, restart, Step counts. |
| Production-specific SQL, isolation, locking tests | JDBC JobRepository on PostgreSQL/MySQL/Oracle/... via Testcontainers | Behavior close to the operational database. |
| Single-run Job needing no history or restart | ResourcelessJobRepository when supported | One-off run with minimal infrastructure; not for asserting durable metadata. |

**H2 in-memory** works well for many integration tests as long as all executions within a test run against the same live database. It cannot test a restart after **the entire JVM exits** because data in RAM can disappear. To test recovery across two separate processes, use a persistent database or a database container kept alive across both startups.

An important version note:

- **Spring Batch 5.2.x with Spring Boot 3.x:** the hands-on examples below use a JDBC repository configured via Boot Batch auto-configuration and the **JobLauncherTestUtils** utility.
- **Spring Batch 6.x:** the test job-launching utility is **JobOperatorTestUtils**. In plain Spring Batch 6, **@EnableBatchProcessing** provides **ResourcelessJobRepository** by default; to use JDBC, you must configure a JDBC repository, such as **@EnableJdbcJobRepository**, or use compatible auto-configuration in the Spring Boot ecosystem. Do not assume that adding an H2 dependency automatically switches the repository to JDBC.

## 4. Building Test Infrastructure with Spring Batch 5.2 and Spring Boot 3

### 4.1. Dependencies

Gradle example using the Spring Batch version managed by the Spring Boot BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-batch-test** provides @SpringBatchTest, JobLauncherTestUtils, JobRepositoryTestUtils, MetaDataInstanceFactory, and listeners supporting StepScope/JobScope in tests.

### 4.2. Using a Dedicated Profile for Tests

Create **src/test/resources/application-batchtest.properties**:

~~~properties
# Dedicated database for tests.
spring.datasource.url=jdbc:h2:mem:batchrepo_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Initialize BATCH_* metadata tables using Boot-managed scripts.
spring.batch.jdbc.initialize-schema=always

# Do not automatically run Jobs when building the application context.
spring.batch.job.enabled=false

# Initialize test business tables.
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:batch-business-schema.sql
~~~

Create **src/test/resources/batch-business-schema.sql**:

~~~sql
CREATE TABLE test_audit (
    event_name VARCHAR(100) NOT NULL
);
~~~

The **BATCH_*** tables are managed by Spring Batch. **test_audit** is a test-specific business table and must be cleaned up manually when preparing the next test case.

The property **spring.batch.jdbc.initialize-schema=always** belongs to Spring Boot Batch auto-configuration. If you configure JobRepository with plain Spring Batch or have disabled Boot auto-configuration, you must explicitly run the proper schema script for your database and Batch version. In particular, adding **@EnableBatchProcessing** in a Boot 3 application can alter auto-configuration; this example intentionally lets Boot set up the JDBC infrastructure.

If there are multiple DataSources, explicitly designate the DataSource for metadata and the JobRepository transaction manager; do not rely on bean registration order. JobRepository can use a different metadata database than the business database, but when doing so you must thoroughly test synchronization/rollback behavior between the two sources.

### 4.3. Metadata Table Schema

Common tables in a JDBC JobRepository:

~~~text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION
BATCH_STEP_EXECUTION_CONTEXT
~~~

Depending on the database, there are also sequences or sequence-emulation tables to generate IDs. You can configure a table prefix other than **BATCH_**, provided the initialization script matches. When tables are missing, have the wrong schema version, or sequences are misconfigured, tests typically fail immediately when creating a JobExecution.

Within a single test, let this data persist **between the failed run and the restart**. Deleting metadata between the two executions erases the history and checkpoints you need to verify.

## 5. Writing a Sample Job to Verify Metadata

The sample Job has two Steps:

1. **preparationStep** inserts a row into the business table and saves a marker into the Step ExecutionContext.
2. **unstableStep** fails exactly once using an AtomicBoolean flag; the rerun succeeds.

This lets us verify that the repository preserves Step history accurately: the first Step, already completed, will not rerun on restart under the default configuration, while the second Step has two executions.

**RepositorySampleJobConfiguration.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class RepositorySampleJobConfiguration {

    @Bean
    AtomicBoolean failNextAttempt() {
        return new AtomicBoolean(true);
    }

    @Bean
    Step preparationStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("preparationStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    jdbcTemplate.update(
                        "INSERT INTO test_audit(event_name) VALUES (?)",
                        "prepared");

                    contribution.getStepExecution()
                            .getExecutionContext()
                            .putString("marker", "done");

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Step unstableStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            AtomicBoolean failNextAttempt) {

        return new StepBuilder("unstableStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (failNextAttempt.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Injected test failure");
                    }
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job repositorySampleJob(
            JobRepository jobRepository,
            @Qualifier("preparationStep") Step preparationStep,
            @Qualifier("unstableStep") Step unstableStep) {

        return new JobBuilder("repositorySampleJob", jobRepository)
                .start(preparationStep)
                .next(unstableStep)
                .build();
    }
}
~~~

AtomicBoolean is a **test fault-injection** mechanism. Do not use a similar global in-memory variable as a source of restart state in production: the JVM may shut down or the application may run across multiple instances. Recoverable state must live in an appropriate store, such as ExecutionContext or a business table.

## 6. Testing JobRepository with @SpringBatchTest

The example below declares a minimal Boot application that imports only the sample Job. This makes the test context easier to control when the main application defines many Jobs.

**JobRepositoryIntegrationTest.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@ActiveProfiles("batchtest")
@SpringBootTest(classes = JobRepositoryIntegrationTest.TestApplication.class)
class JobRepositoryIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RepositorySampleJobConfiguration.class)
    static class TestApplication {
    }

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    JobRepository jobRepository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    AtomicBoolean failNextAttempt;

    @Autowired
    @Qualifier("repositorySampleJob")
    Job job;

    @BeforeEach
    void resetState() {
        launcherTestUtils.setJob(job);
        failNextAttempt.set(true);

        // Use only on a database dedicated to testing.
        repositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM test_audit");
    }

    @Test
    void metadataIsPersistedAcrossJobRestart() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessKey", "case-576")
                .toJobParameters();

        // Execution 1: preparationStep completes, unstableStep fails.
        JobExecution first = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertNotNull(first.getId());

        JobExecution storedFirst = jobRepository.getLastJobExecution(
                "repositorySampleJob", parameters);
        assertNotNull(storedFirst);
        assertEquals(first.getId(), storedFirst.getId());

        assertEquals(1L, jobRepository.getStepExecutionCount(
                first.getJobInstance(), "preparationStep"));
        assertEquals(1L, jobRepository.getStepExecutionCount(
                first.getJobInstance(), "unstableStep"));

        // Data stored in the Step ExecutionContext is read back.
        StepExecution savedStep = jobRepository.getLastStepExecution(
                first.getJobInstance(), "preparationStep");
        assertNotNull(savedStep);
        assertEquals(BatchStatus.COMPLETED, savedStep.getStatus());
        assertEquals("done",
                savedStep.getExecutionContext().getString("marker"));

        // Execution 2 uses the exact same JobParameters as the first run.
        JobExecution restarted = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(first.getJobInstance().getInstanceId(),
                     restarted.getJobInstance().getInstanceId());

        // Already completed step does not rerun by default.
        assertEquals(1L, jobRepository.getStepExecutionCount(
                restarted.getJobInstance(), "preparationStep"));
        assertEquals(2L, jobRepository.getStepExecutionCount(
                restarted.getJobInstance(), "unstableStep"));

        // Business side effect of preparationStep occurs only once.
        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM test_audit", Integer.class);
        assertEquals(1, auditCount);

        // Repository returns the latest execution after restart.
        JobExecution storedRestart = jobRepository.getLastJobExecution(
                "repositorySampleJob", parameters);
        assertNotNull(storedRestart);
        assertEquals(restarted.getId(), storedRestart.getId());
    }
}
~~~

The test establishes four layers of evidence:

- **Status**: the first execution is FAILED and the subsequent execution is COMPLETED.
- **Identity**: JobExecution IDs differ, while the JobInstance ID is the same.
- **Step History**: preparationStep has only one StepExecution, whereas unstableStep has two.
- **Persistence**: metadata and ExecutionContext are read back from JobRepository; business data is written only once.

For a Job that is already COMPLETED, attempting to run it again with **the same identifying JobParameters** must be rejected according to the JobInstanceAlreadyComplete rule. Generating a different identifying run.id creates a new processing run, not a retry of the completed instance.

### Expected Results

| Information | After the First Run | After Restart |
| --- | --- | --- |
| JobInstance | A unique ID | Same ID retained |
| Latest JobExecution | FAILED | COMPLETED |
| JobExecution count | 1 | 2 |
| preparationStep executions | 1 | 1 |
| unstableStep executions | 1 | 2 |
| Step ExecutionContext marker | done | Still readable as done |
| test_audit row count | 1 | 1 |

## 7. JobRepositoryTestUtils and the Cleanup Lifecycle

**JobRepositoryTestUtils** helps create and delete metadata in the test repository. For example:

~~~java
// Delete JobExecutions and related metadata in the test repository.
repositoryTestUtils.removeJobExecutions();

// Create simulated executions for a test scenario.
var executions = repositoryTestUtils.createJobExecutions(2);

// Delete the exact executions just created.
repositoryTestUtils.removeJobExecutions(executions);
~~~

Calling **removeJobExecutions()** with no arguments can delete the entire Batch history managed by the repository. Only use it when you are certain the repository points to an isolated test database. It **does not clean business data**; the test_audit table, exported files, messages, or side effects outside the database must be handled separately.

Standard lifecycle:

~~~text
@BeforeEach
  1. Reset fault injection.
  2. Clean up metadata from the previous test.
  3. Clean and seed business data.
    |
    v
Test body
  - launchJob(params) -> FAILED
  - keep metadata and checkpoints intact
  - launchJob(same params) -> COMPLETED
  - assert JobRepository + data
    |
    v
End of test
  - Next test starts with an isolated state
~~~

Do not call cleanup **between the two executions of the same restart test**. Doing so can turn the second run into a fresh run from scratch, even while Job status assertions still pass.

In parallel tests, two classes sharing one H2 database and both calling removeJobExecutions can delete each other's metadata. When parallelism is desired, use separate databases/schemas, adopt an execution-ownership strategy, or disable parallel execution for integration test groups sharing a metadata store.

### How Does MetaDataInstanceFactory Differ from a JDBC Repository?

Listener unit tests sometimes only need a StepExecution to verify logic:

~~~java
StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution();

stepExecution.setReadCount(0);
// Test StepExecutionListener logic on this fixture.
~~~

This fixture does not prove that a StepExecution was saved in a JDBC JobRepository. Only tests that actually run the Job/Step and read back from the repository can verify durability, transactions, checkpoints, and restart.

## 8. Querying Metadata for Diagnostics

After running the test above, you can inspect the tables directly via SQL:

~~~sql
SELECT ji.JOB_NAME,
       ji.JOB_INSTANCE_ID,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'repositorySampleJob'
ORDER BY je.JOB_EXECUTION_ID;
~~~

You should expect two result rows with **the same JOB_INSTANCE_ID**; the first execution is FAILED and the second execution is COMPLETED.

For Steps:

~~~sql
SELECT se.JOB_EXECUTION_ID,
       se.STEP_NAME,
       se.STATUS,
       se.READ_COUNT,
       se.WRITE_COUNT,
       se.COMMIT_COUNT,
       se.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION se
ORDER BY se.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

In the sample Job using **TaskletStep**, readCount and writeCount are typically 0 because there is no chunk reader/writer. Do not use these counts as evidence of the number of rows INSERTed by a Tasklet. When using a chunk-oriented Step, these counts reflect item-level processing.

Direct SQL queries are useful during diagnostics; when writing test code, prefer JobExplorer/JobRepository so you are not tightly coupled to table names, table prefixes, and serializers across versions.

## 9. Transactions and Test Correctness

### 9.1. Do Not Put @Transactional on the Entire Integration Test

If the entire test method is wrapped in a transaction by the test framework, automatic rollback at the end of the test can make it hard to observe actual Step commits. Let Batch manage its own transactions, then verify the data and metadata after launchJob returns.

In chunk-oriented processing, Spring Batch updates checkpoints at commit boundaries according to the Step design. If the writer works with the same JDBC transaction, a failed chunk rolls back uncommitted data. If the writer sends HTTP requests, emails, or messages to external systems, those side effects may not roll back with JDBC metadata. In that case, you need idempotency, unique keys, an outbox, or reconciliation, along with tests covering those scenarios.

### 9.2. H2 Does Not Emulate All Production Behavior

Differences can include SQL syntax, sequences, large data types, transaction isolation, deadlocks, locking, and table prefix configuration. For Jobs that depend on these characteristics, use Testcontainers running the same production database engine with the appropriate metadata initialization script.

### 9.3. Avoiding Causes of False-Positive Tests

| Mistake | Consequence |
| --- | --- |
| Asserting only BatchStatus.COMPLETED | Misses non-persisted metadata or an incorrect JobInstance. |
| Calling launchJob() with no arguments when a restart is needed | The 5.x utility may add random parameters, creating a new JobInstance. |
| Adding a new run.id on the restart run | The test switches to running a different instance. |
| Deleting BATCH_* between failure and restart | Loses checkpoints and execution history. |
| Running with ResourcelessJobRepository and asserting JDBC recovery | There is no JDBC metadata to verify. |
| Sharing a DB across parallel tests | Cleanup in one test can corrupt another test's data. |
| Using in-memory H2 for a test across JVM termination | The database may vanish along with the process. |
| Confusing the business DataSource with the metadata DataSource | Inspecting the wrong database or hitting schema errors. |
| Checking only the in-memory JobExecution object returned | Misses the fact that metadata was not persisted as expected. |

## 10. Differences in Spring Batch 6.x

The principles of JobInstance, JobExecution, StepExecution, and ExecutionContext still apply. However, when migrating from Spring Batch 5.2 to 6.x, note the following:

| Item | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Job-launching test utility in spring-batch-test | JobLauncherTestUtils.launchJob(params) | JobOperatorTestUtils.startJob(params) |
| Metadata cleanup | JobRepositoryTestUtils | JobRepositoryTestUtils |
| Core domain packages | org.springframework.batch.core.Job/JobExecution/... | Subpackages such as core.job, core.step, core.job.parameters |
| Default repository with plain @EnableBatchProcessing | Matches the corresponding JDBC/Batch 5 setup | Resourceless; JDBC requires enabling/configuring a JDBC repository |
| JUnit | JUnit Jupiter is supported | JUnit Jupiter; JUnit 4 is no longer supported |

When porting examples, update imports, builders, and infrastructure configuration according to the documentation for the target version; in particular, verify that the JobRepository bean is JDBC-backed and that the metadata schema has been created. A test only meaningfully verifies persistence when it actually runs against a metadata store that stays durable over the scenario's lifecycle.

## 11. Exercises

1. **Basic persistence:** Create a single-Step Job, run it with a fixed identifying parameter, use JobRepository.getLastJobExecution to read back the ID/status, and compare with the launchJob result.
2. **Restart:** Inject a failure in the second Step, rerun with the same JobParameters, and prove that one JobInstance has two JobExecutions while the first Step does not rerun.
3. **JobInstance constraint:** After the Job is COMPLETED, try launching again with the same identifying parameters; verify that no new business processing occurs.
4. **Distinguishing metadata from business data:** Delete only the business table while keeping BATCH_*, then try rerunning the completed JobInstance. Explain why the repository still rejects it.
5. **Test isolation:** Run two tests that share a metadata database and refactor the setup so each test has its own database or schema.
6. **Production-like database:** Switch from H2 to Testcontainers with a real database, then re-verify the schema, transactions, and ExecutionContext retrieval after restart.

A solid test infrastructure for Spring Batch ensures **an isolated database**, **a persisted JobRepository**, **a controlled metadata lifecycle**, and **assertions proving data was actually saved**, giving Job, Step, and restart tests a reliable foundation.

## 12. References

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 6.x — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Infrastructure Configuration](https://docs.spring.io/spring-batch/reference/job/configuring-infrastructure.html)
- [JobRepository API, Spring Batch 5.2](https://docs.spring.io/spring-batch/docs/5.2.4/api/org/springframework/batch/core/repository/JobRepository.html)
- [JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)

