# Testing Restart in Spring Batch

## 1. Lesson Objectives

In batch systems, network glitches, malformed data, temporary database unavailability, or process termination can cause a **Job** to fail after successfully processing part of the dataset. Testing only that a Job runs from start to finish with `COMPLETED` status is insufficient: the system must also **restart cleanly from the unfinished portion**, preserve already-committed work, and avoid producing duplicate data.

After this lesson, you will be able to:

- Distinguish rerunning the same **JobInstance** from creating a new JobInstance.
- Design scenarios where a Job fails intentionally and then restarts using the exact same **JobParameters**.
- Verify reader checkpoints, transaction/chunk boundaries, and output data.
- Test handling of completed steps, non-restartable jobs, and abnormal states.
- Build integration tests using `spring-batch-test`, JUnit Jupiter, and a database-backed JobRepository.

## 2. What Does Restart Actually Mean?

Spring Batch persists run metadata in the **JobRepository**. Core concepts:

| Concept | Meaning for Restart Testing |
| --- | --- |
| `Job` | Definition of the workflow, Job name, and Steps. |
| `JobInstance` | A *business-level* processing run identified by the Job name and **identifying JobParameters**. |
| `JobExecution` | A single attempt to run a JobInstance; one JobInstance can have multiple JobExecutions. |
| `StepExecution` | A single attempt to run a Step within a JobExecution. |
| `ExecutionContext` | Persisted state enabling a Step/Job to resume, such as checkpointed read positions. |
| `BatchStatus` | Execution status such as `STARTED`, `FAILED`, `STOPPED`, `COMPLETED`. |

For a Job named `importOrdersJob`, suppose the only identifying parameter is `businessDate=2026-11-16`:

~~~text
Job: importOrdersJob
JobParameters: businessDate=2026-11-16 (identifying)
        |
        v
JobInstance #42
   |
   +-- JobExecution #100 -> FAILED
   |       +-- StepExecution loadStep -> FAILED
   |
   +-- JobExecution #101 -> COMPLETED    (restart)
           +-- StepExecution loadStep -> COMPLETED
~~~

Key points to prove in a test:

1. Both calls have the **same Job name** and **the same identifying parameters**.
2. The two runs have **different JobExecution IDs**, yet the **same JobInstance ID**.
3. The first run ends as `FAILED`; the next run ends as `COMPLETED`.
4. Already committed data is not lost; uncommitted data is reprocessed; final data is accurate and free of duplicates.

**Pitfall:** `JobOperatorTestUtils.startJob()` (Spring Batch 6) or `JobLauncherTestUtils.launchJob()` (Spring Batch 5) called **without arguments** can auto-generate random parameters to launch a new JobInstance. To test restart, **pass the exact same `JobParameters` object to both runs**. Adding a new identifying `run.id` or timestamp on the second run creates a different JobInstance, not a restart.

A `COMPLETED` JobInstance normally cannot be launched again with the same identifying parameters: Spring Batch throws an error such as `JobInstanceAlreadyCompleteException`. Conversely, a `FAILED` Job can be restarted if configuration permits and metadata state remains valid.

### Statuses and Behaviors to Distinguish

| Previous Outcome | Next Run with Same Parameters | What to Test |
| --- | --- | --- |
| `FAILED` | Normally restartable | A new JobExecution is created and resumes from checkpoint. |
| `STOPPED` | Restartable once fully stopped | Do not restart while the Job is still `STOPPING`. |
| `COMPLETED` | Rejected | Must not trigger duplicate data writes. |
| `STARTING`/`STARTED` | Job is considered still running | Must not arbitrarily start a concurrent execution for the same JobInstance. |
| `ABANDONED` | Not restartable through normal mechanisms | Requires dedicated recovery procedures. |
| Job with `preventRestart()` | Rejects restart after failure | Receives `JobRestartException` or equivalent error from the caller layer. |

**Note on power loss / killed processes:** metadata may remain `STARTED` because the process died before recording `FAILED`. Never arbitrarily edit metadata status just to make a test pass. In real operations, verify the old process has stopped along with data and checkpoint consistency before transitioning the execution to a recoverable state.

## 3. What Must Be Verified at Chunk Boundaries?

Consider a Step reading five records in order `1, 2, 3, 4, 5` using `chunk(2)`, with an error injected while processing record `3`:

~~~text
Execution 1:
  read 1,2 -> write 1,2 -> COMMIT         (checkpoint after 2)
  read 3   -> processor throws exception
             -> current chunk ROLLBACK
  Job = FAILED
  committed output = [1,2]

Execution 2 (same JobParameters):
  open reader from previous checkpoint
  read 3,4 -> write 3,4 -> COMMIT
  read 5   -> write 5   -> COMMIT
  Job = COMPLETED
  final output = [1,2,3,4,5]
~~~

When the reader is a stateful `ItemStream`, the committed position is saved in `StepExecution.ExecutionContext`. Upon restart, the reader uses that position to resume at the right spot. With `JdbcCursorItemReader`, the SQL query must have a **deterministic ordering**, such as `ORDER BY id`, and `saveState(true)` enabled (which is also the reader's default). If the source data mutates between runs, a saved offset may no longer point to the same record; tests should use a stable snapshot or a key/checkpoint-based reading strategy.

Importantly, **restartability does not automatically imply exactly-once semantics** across all systems. If the writer sends emails, calls HTTP APIs, or writes to a system outside the JobRepository's transaction, partial side effects may have already occurred even if metadata did not commit. Add idempotency keys, unique constraints, upserts, outbox patterns, or reconciliation mechanisms as needed.

## 4. Preparing the Integration Test Environment

The example below illustrates **Spring Batch 6.x**, Spring Boot, JUnit Jupiter, and an H2 database within a single test context. If using Spring Batch 5.x, see the API adjustments section at the end of the lesson.

Include the dependencies matching your Spring Boot version: Spring Batch, Spring JDBC, `spring-batch-test` (test scope), `spring-boot-starter-test`, and H2 (test/runtime scope). Spring Boot manages dependency versions via its BOM. Use a **real JDBC JobRepository** to test checkpoints and metadata; a non-persistent repository cannot prove restart behavior.

In `src/test/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:restartdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
~~~

The file `src/test/resources/schema.sql` creates only business tables; Spring Batch initializes the `BATCH_*` tables separately:

~~~sql
CREATE TABLE source_item (
    id INTEGER PRIMARY KEY
);

CREATE TABLE processed_item (
    id INTEGER PRIMARY KEY
);
~~~

Disable automatic Job execution at test startup (`spring.batch.job.enabled=false`) so every execution is explicitly initiated by the test. **Do not place `@Transactional` on the entire integration test method**: the test needs to observe actual committed or rolled-back transactions per chunk. When testing restart across a JVM restart, replace in-memory H2 with a database that persists across two separate processes.

## 5. Example Job with Fault Injection Point

The configuration below has a position-saving JDBC reader, a processor that intentionally throws an error on ID `3`, and a writer persisting data via `JdbcTemplate`. On the first run, the first two records commit; once the failure flag is turned off and the job restarts, the Step resumes from record `3`.

`RestartJobConfig.java`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import javax.sql.DataSource;

import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.infrastructure.item.database.JdbcCursorItemReader;
import org.springframework.batch.infrastructure.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class RestartJobConfig {

    @Bean
    AtomicBoolean failOnThree() {
        return new AtomicBoolean(false);
    }

    @Bean
    @StepScope
    JdbcCursorItemReader<Integer> orderedReader(DataSource dataSource) {
        return new JdbcCursorItemReaderBuilder<Integer>()
                .name("orderedReader")
                .dataSource(dataSource)
                .sql("SELECT id FROM source_item ORDER BY id")
                .rowMapper((rs, rowNum) -> rs.getInt("id"))
                .saveState(true)
                .build();
    }

    @Bean
    Step loadStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  JdbcCursorItemReader<Integer> orderedReader,
                  JdbcTemplate jdbcTemplate,
                  AtomicBoolean failOnThree) {

        return new StepBuilder("loadStep", jobRepository)
                .<Integer, Integer>chunk(2)
                .transactionManager(transactionManager)
                .reader(orderedReader)
                .processor(id -> {
                    if (failOnThree.get() && id == 3) {
                        throw new IllegalStateException("Injected failure at id=3");
                    }
                    return id;
                })
                .writer(chunk -> {
                    for (Integer id : chunk.getItems()) {
                        jdbcTemplate.update(
                            "INSERT INTO processed_item(id) VALUES (?)", id);
                    }
                })
                .build();
    }

    @Bean
    Job importJob(JobRepository jobRepository, Step loadStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(loadStep)
                .build();
    }
}
~~~

Key details:

- The reader is declared `@StepScope` so each StepExecution gets a fresh reader with state restored from `ExecutionContext`. A stable reader name preserves the checkpoint key.
- `ORDER BY id` makes read order deterministic across the test dataset.
- `chunk(2)` establishes a commit boundary to verify already-written data before the failure.
- The failure occurs in the **processor** before the writer for the chunk containing `3` runs; it does not depend on flaky network errors.
- The writer shares the Step's transaction manager/data source, so rolling back a chunk rolls back its `INSERT` statements. The target table has a primary key so duplicate writes are easily caught.
- The `AtomicBoolean` flag exists solely for **fault injection in tests**, not as a production business mechanism.

## 6. Writing the Integration Test: FAILED → Restart → COMPLETED

Suppose you have a Spring Boot application configured with Batch and importing `RestartJobConfig`. The test below uses `@SpringBatchTest` to inject `JobOperatorTestUtils` and `JobRepositoryTestUtils`. If the project defines multiple Job beans, explicitly specify the target Job with `@Qualifier` and pass it to the utility.

`RestartJobIT.java` (replace `YourBatchApplication.class` with your project's application class, ensuring `RestartJobConfig` is loaded into the test context):

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.core.step.StepExecution;
import org.springframework.batch.test.JobOperatorTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(classes = YourBatchApplication.class)
class RestartJobIT {

    @Autowired
    private JobOperatorTestUtils jobTestUtils;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("importJob")
    private Job importJob;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private AtomicBoolean failOnThree;

    @BeforeEach
    void prepare() {
        jobTestUtils.setJob(importJob);
        failOnThree.set(false);

        // Clean metadata only in the test database; never delete real metadata.
        repositoryTestUtils.removeJobExecutions();

        jdbc.update("DELETE FROM processed_item");
        jdbc.update("DELETE FROM source_item");
        for (int id = 1; id <= 5; id++) {
            jdbc.update("INSERT INTO source_item(id) VALUES (?)", id);
        }
    }

    @Test
    void restartResumesAfterCommittedChunkWithoutDuplicates() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        // First execution: fail at ID=3 after chunk [1,2] commits.
        failOnThree.set(true);
        JobExecution first = jobTestUtils.startJob(params);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_item", Integer.class));

        // Restart: use the EXACT same params with persisted metadata intact.
        failOnThree.set(false);
        JobExecution restarted = jobTestUtils.startJob(params);

        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(first.getJobInstance().getInstanceId(),
                     restarted.getJobInstance().getInstanceId());

        // Business outcome must be complete with no duplicate writes.
        List<Integer> ids = jdbc.queryForList(
                "SELECT id FROM processed_item ORDER BY id", Integer.class);
        assertEquals(List.of(1, 2, 3, 4, 5), ids);

        // Restart run reads only the three uncommitted items.
        StepExecution resumedStep =
                restarted.getStepExecutions().iterator().next();
        assertEquals(BatchStatus.COMPLETED, resumedStep.getStatus());
        assertEquals(3L, resumedStep.getReadCount());
    }
}
~~~

**Why are so many assertions needed?** Checking only `restarted.getStatus() == COMPLETED` could pass even if you accidentally created a new JobInstance, re-read the entire source, or wrote duplicate data without noticing. A solid test must simultaneously prove **same instance**, **new execution**, **checkpoint usage**, and **accurate business output**.

If the project does not use Spring Boot, replace `@SpringBootTest` with `@SpringJUnitConfig` and explicitly configure `DataSource`, `JobRepository`, transaction manager, batch infrastructure, and schema; the design and assertions remain unchanged.

### Reading Metadata for Observation

Common JDBC JobRepository tables:

- `BATCH_JOB_INSTANCE`: one row per JobInstance by identifying parameter set.
- `BATCH_JOB_EXECUTION`: two separate rows for the failed run and the restart run.
- `BATCH_STEP_EXECUTION`: status, read/write counts, rollback/commit counts per StepExecution.
- `BATCH_STEP_EXECUTION_CONTEXT`: Step checkpoints and recovery state.
- `BATCH_JOB_EXECUTION_PARAMS`: JobParameters details.

Sample SQL to inspect executions in a test environment (exact column names depend on the Spring Batch schema version in use):

~~~sql
SELECT ji.JOB_NAME,
       je.JOB_INSTANCE_ID,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importJob'
ORDER BY je.JOB_EXECUTION_ID;
~~~

Expected result: **two execution IDs**, **one instance ID**, first `FAILED`, second `COMPLETED`. You can inspect `BATCH_STEP_EXECUTION` to cross-check `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, and `ROLLBACK_COUNT`; avoid hardcoding internal commit counts unless you have verified the exact Step logic and Spring Batch version.

## 7. Matrix of Restart Scenarios to Test

| Scenario | How to Trigger Condition | What to Assert |
| --- | --- | --- |
| Failure before first commit | Throw error on item `1` | No committed target data; restart processes from the start. |
| Failure after at least one commit | Throw error on item `3` with chunk size `2` | Data `1,2` preserved; restart processes `3,4,5`. |
| Error inside writer | Throw error while writing the second chunk | Failing chunk rolls back; no partial writes within that transaction. |
| Two Steps, Step A completed, Step B fails | Intentionally fail in Step B | Restart skips already `COMPLETED` Step A by default and reruns Step B. |
| `allowStartIfComplete(true)` | Set on Step A | Step A reruns on Job restart; A's data/side effects must be safe. |
| `preventRestart()` | Let Job fail then call again with same params | Framework rejects restart. |
| `startLimit(n)` | Repeatedly fail up to Step start limit | Rejected once allowed attempts are exceeded, without silently creating attempt n+1. |
| Job already `COMPLETED` | Rerun with same identifying parameters | Does not rerun and does not alter target table. |
| Change identifying parameter | Change `businessDate` | Creates a new JobInstance; must not be used as proof of restart. |
| Controlled stop | Request stop, wait for `STOPPED` | Restart only after the Step/Job has stopped cleanly. |
| Source has persistent bad record | Do not remove faulty data | Restart fails again at the same spot or follows skip/retry config; no false completion. |
| Source mutates between runs | Insert/delete rows before read position | Prove solution still identifies records to process, or state source immutability requirement. |

Strategies requiring separate tests:

- **Skip/retry:** retry reprocesses the same item within *one execution*, whereas restart creates a *new execution* after failure. Test these two behaviors separately; check skip counts, retries/rollbacks, and final output. A skippable error can leave the Job `COMPLETED`, so do not use it to simulate `FAILED` when testing restart.
- **Stateless readers:** `saveState(false)` is suitable only when design re-processes data using status flags, keys, or business conditions. If the reader starts from the beginning after restart, the writer must prevent duplicates and tests must verify that capability.
- **Completed Steps:** by default on Job restart, previously `COMPLETED` Steps are skipped. `allowStartIfComplete(true)` alters this behavior; you must test idempotency of the re-run Step.
- **Asynchronous/partitioned:** test each partition's state, do not assume deterministic processing order, and avoid non-thread-safe shared stateful readers.

## 8. Mistakes That Make Tests "False Green"

**1. Changing identifying parameters on restart.** Adding a new timestamp or `run.id` causes the framework to create a new JobInstance and run from scratch. Use the exact same JobParameters when testing restart. If you need a logging attribute without altering instance identity, add a **non-identifying** parameter and understand its effect on the application.

**2. Checking only Job status.** `COMPLETED` does not prove data is accurate, deduplicated, complete, or not rewritten. Cross-check IDs, counts, business totals, or checksums on the final data.

**3. Clearing `BATCH_*` tables between two runs.** Wipes JobInstance history and checkpoints; the second run is no longer a restart. Clean metadata only between **independent test cases**, never between two executions inside the same test.

**4. Wrapping the test in a single outer transaction.** Can hide real commits/rollbacks, causing inspected data to misrepresent Batch behavior.

**5. Depending on random errors.** Tests relying on timeouts, real networks, or external processes are prone to flakiness. Inject deterministic errors conditioned by item/step and disable the fault clearly before restarting.

**6. Using a new `run.id` to "fix" `JobInstanceAlreadyComplete`.** This is valid if business intent is launching a new batch; it does not prove restarting an old batch.

**7. Assuming checkpoints alone guarantee data accuracy.** Transactions for JobRepository and business data may differ; output files, message brokers, and external APIs may not roll back with the DB. Tests must verify side effects/idempotency and failures right after a side effect succeeds.

**8. Ignoring source data stability.** Readers using offsets, queries lacking `ORDER BY`, or sources mutating during restart can cause lost or duplicate records. Test against a clear snapshot or use a business-key checkpoint design.

**9. Restarting only in the same process and claiming crash recovery is tested.** In-JVM integration tests prove JobRepository/checkpoint logic. Crash-recovery tests require two separate processes and a persistent database, along with confirming no execution is actually still running.

## 9. Practice Exercise

From the example above, extend the Job into two Steps: `validateStep` and `loadStep`.

1. `validateStep` records a test trace when executed, then succeeds.
2. `loadStep` is configured to fail at item `3` on the first run.
3. Restart with the same `JobParameters`; verify `validateStep` does not rerun by default.
4. Set `allowStartIfComplete(true)` on `validateStep`, run the scenario with a new test JobInstance, and confirm this Step reruns when the Job restarts.
5. Try removing `ORDER BY id` to create an unordered query and reason about why checkpoint testing becomes unreliable (do not use this non-deterministic outcome as a primary assertion).
6. Switch the writer to a mock external API and add an idempotency key; simulate the API receiving the request while the Step fails before saving its checkpoint.

**Completion criteria:** tests verify statuses of both runs, JobInstance identity, which StepExecutions should or should not rerun, complete duplicate-free final data, and reliable repeatability on a clean test database.

## 10. Version Differences Notes

The example article uses **Spring Batch 6.x** APIs:

- `JobOperatorTestUtils.startJob(params)` is the recommended test utility for 6.x.
- Job/JobExecution, JobParameters, and StepExecution types reside in `org.springframework.batch.core.job.*`, `org.springframework.batch.core.job.parameters.*`, and `org.springframework.batch.core.step.*`.
- JDBC readers and writers moved to `org.springframework.batch.infrastructure.item.*`.
- Chunk declaration uses `new StepBuilder("loadStep", repository).<I, O>chunk(2).transactionManager(txManager)`.

With **Spring Batch 5.2.x**, you can use `JobLauncherTestUtils.launchJob(params)`, `new StepBuilder("loadStep", repository).<I, O>chunk(2, txManager)`, and v5 imports such as `org.springframework.batch.core.JobExecution`, `org.springframework.batch.core.JobParametersBuilder`, and `org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder`. In Spring Batch 6, `JobLauncherTestUtils` is marked deprecated in favor of `JobOperatorTestUtils`. The **business rules for restart, checkpoint verification, and output data** remain the focus of tests in both version lines.

### Official References

- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Configuring a Job / Restartability](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — The Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 6 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide)

