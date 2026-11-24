# Asserting `ExecutionContext` in Spring Batch Testing

## 1. Lesson Objectives

When testing a batch job, seeing `JobExecution` or `StepExecution` with `COMPLETED` status is not enough to conclude that state data was persisted properly. A step may process successfully yet write the wrong checkpoint, save to the job context by mistake, or fail to pass results to the next step. Such bugs often surface only when a job has to restart after a failure.

**Asserting `ExecutionContext`** means writing checks confirming that execution state is created, updated, propagated, and restored according to the batch job's contract. After this lesson, you will be able to:

- Distinguish `JobExecution.getExecutionContext()` from `StepExecution.getExecutionContext()` and select the right object to assert.
- Verify key existence, data types, values, absence conditions, and changes.
- Independently test a component using `ExecutionContext`, including `ItemStream.open/update`.
- Run real jobs/steps using `spring-batch-test`, assert context after execution, and read data back from the repository.
- Verify data promotion from step context to job context, as well as checkpoints on restart.
- Avoid assertions that pass only on in-memory objects without proving that state was durably persisted.

The complete examples below use **Java 17+, JUnit Jupiter, Spring Boot 3.x, and Spring Batch 5.x**. Notes on migrating to Spring Batch 6 appear at the end of the lesson.

## 2. What Is `ExecutionContext` and Where Do You Assert It?

`org.springframework.batch.item.ExecutionContext` is a key–value store used by Spring Batch to hold state needed for a run and for restartability. Values can be read via typed APIs such as `getString`, `getInt`, `getLong`, or the general `get` API. When saved to the metadata repository, values must be compatible with the configured serialization mechanism.

A `JobExecution` and each `StepExecution` have **their own `ExecutionContext`**:

| Object to Inspect | How to Access | Lifecycle / Persistence Timing | Example Keys |
| --- | --- | --- | --- |
| Step context | `stepExecution.getExecutionContext()` | Bound to a single step run; typically synchronized to the repository at chunk checkpoints/commits and when the step finishes | `reader.offset`, `page.number`, `processed.count` |
| Job context | `jobExecution.getExecutionContext()` | Bound to a single job run, retained across steps; typically saved at step boundaries | `source.file`, `import.total` |
| Job parameters | `jobExecution.getJobParameters()` | Identifying/controlling inputs for the job; **not** `ExecutionContext` | `businessDate`, `inputPath` |

For example, the `readCustomers` step reads 120 records and writes:

```java
stepExecution.getExecutionContext().putLong("reader.offset", 120L);
```

Here, the assertion must read the **step context**:

```java
assertEquals(
    120L,
    stepExecution.getExecutionContext().getLong("reader.offset")
);
```

You cannot assume the job context also contains `reader.offset`. If a subsequent step needs this data, the application must explicitly copy it or use `ExecutionContextPromotionListener` to promote the key from step context to job context after the step completes.

### 2.1. Do Not Confuse Business State with Framework State

Spring Batch also tracks metadata such as `BatchStatus`, `ExitStatus`, `readCount`, `writeCount`, `commitCount`, and `rollbackCount`. These are useful in tests, but they do not replace asserting business keys in `ExecutionContext`.

A strong test typically answers three questions at once:

1. **Did the batch reach the expected point?** For example, `BatchStatus.COMPLETED`.
2. **Is the state data accurate?** For example, `processed.count = 120` and `reader.offset = 120`.
3. **Are values in the right scope and persisted at the right time?** For example, `import.total` appears in job context after a successful step, while the checkpoint remains in step context.

## 3. Define the Assertion Contract Before Writing Tests

Suppose we have a customer import job:

```text
customerImportJob
    |
    +-- readCustomersStep
    |      step context:
    |        reader.offset = 120
    |        processed.count = 120
    |        source.file = "customers-2026.csv"
    |
    +-- createReportStep
           reads job context:
             import.total = 120
```

The contract can be expressed in the following table:

| Moment | Scope | Condition to Assert |
| --- | --- | --- |
| Before running | Step | `reader.offset` does not exist yet, or holds the restored checkpoint value |
| After reading 120 rows | Step | `reader.offset == 120L` and `processed.count == 120L` |
| After `readCustomersStep` succeeds | Job | `import.total == 120L` if promotion is configured |
| When step fails before promotion | Job | `import.total` is not promoted outside the configured policy |
| Before continuing to read on restart | Step | Reader receives the committed checkpoint from the previous run |
| After reading back from repository | Step/Job | Keys requiring durability retain their exact values and types |

Choose stable, meaningful key names: use `reader.offset`, `import.total`, `source.file` instead of `x`, `value1`. Avoid asserting every entry in the context if the framework or other components may validly add metadata keys.

## 4. Basic Assertions with JUnit 5

`ExecutionContext` supports `containsKey`, `getString`, `getInt`, `getLong`, `getDouble`, `get`, and overloaded getters with defaults. `putString`, `putInt`, and `putLong` make expected data types explicit.

Example checking multiple conditions at once:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.*;

class ExecutionContextAssertionsTest {

    @Test
    void assertsValuesAndMissingKeys() {
        ExecutionContext context = new ExecutionContext();
        context.putString("source.file", "customers.csv");
        context.putLong("reader.offset", 120L);
        context.putInt("retry.count", 2);

        assertAll("batch checkpoint",
            () -> assertTrue(context.containsKey("source.file")),
            () -> assertEquals("customers.csv", context.getString("source.file")),
            () -> assertEquals(120L, context.getLong("reader.offset")),
            () -> assertEquals(2, context.getInt("retry.count")),
            () -> assertFalse(context.containsKey("fatal.error")),
            () -> assertEquals(0, context.getInt("missing.count", 0))
        );
    }

    @Test
    void nullRemovesTheKey() {
        ExecutionContext context = new ExecutionContext();
        context.putString("temporary.marker", "PENDING");
        context.put("temporary.marker", null);

        assertFalse(context.containsKey("temporary.marker"));
    }
}
```

**Meaning of each assertion style:**

- `containsKey("k")` checks that the key exists, even if the value read equals a default value.
- `getLong("k")` checks the value with exact type `Long`; avoid comparing numbers by converting to strings.
- `getInt("k", 0)` is suitable when the contract allows the key to be absent and treats missing as `0`.
- `assertFalse(context.containsKey("secret"))` expresses an invariant: sensitive keys or temporary markers must not remain.
- `assertAll` lets you see all related assertion failures on the same state in a single test run.

Do not use a default getter to mask a **required** key. When `reader.offset` must exist, assert `containsKey` first before asserting its value. If the key is absent, `getLong("reader.offset", 0L)` can cause the test to pass falsely when the expected value is also `0`.

### 4.1. What Does `isDirty()` Check?

`ExecutionContext` has a dirty flag to track map modifications:

```java
ExecutionContext context = new ExecutionContext();

assertFalse(context.isDirty());

context.putLong("reader.offset", 5L);
assertTrue(context.isDirty());

context.clearDirtyFlag();
assertFalse(context.isDirty());
```

This only proves the object changed since the last flag clear; it **does not prove** the transaction committed or the repository persisted successfully. Therefore, `isDirty()` is helpful when testing context-mutating logic, but a separate integration test is required when persistence is the requirement.

## 5. Unit Testing Components That Write to Step `ExecutionContext`

When logic lives in a small class, you can test it quickly without starting the full Spring context. `MetaDataInstanceFactory` in the `spring-batch-test` module pre-creates mock `StepExecution` and `JobExecution` metadata.

Example of a class recording progress after processing a batch of records:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;

public class ImportProgressRecorder {

    public void record(StepExecution stepExecution,
                       long lastCustomerId,
                       int successfulRecords) {
        ExecutionContext context = stepExecution.getExecutionContext();
        context.putLong("customer.lastId", lastCustomerId);
        context.putInt("customer.successCount", successfulRecords);
        context.putString("customer.phase", "PROCESSED");
    }
}
```

The test asserts expectations on **the StepExecution updated by real logic**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class ImportProgressRecorderTest {

    private final ImportProgressRecorder recorder =
        new ImportProgressRecorder();

    @Test
    void writesExpectedCheckpointIntoStepContext() {
        StepExecution stepExecution =
            MetaDataInstanceFactory.createStepExecution();

        recorder.record(stepExecution, 1088L, 35);

        ExecutionContext actual = stepExecution.getExecutionContext();

        assertAll("recorded progress",
            () -> assertTrue(actual.containsKey("customer.lastId")),
            () -> assertEquals(1088L, actual.getLong("customer.lastId")),
            () -> assertEquals(35, actual.getInt("customer.successCount")),
            () -> assertEquals("PROCESSED", actual.getString("customer.phase"))
        );

        assertFalse(stepExecution.getJobExecution()
                                 .getExecutionContext()
                                 .containsKey("customer.lastId"));
    }
}
```

The final assertion is particularly meaningful: it verifies that the recorder writes only to step context as designed and does not accidentally leak checkpoint state into job context.

**Limitation of this example:** `MetaDataInstanceFactory` does not perform chunk commits or database persistence. This test verifies *value-writing logic*, whereas checkpoint durability requires a real step/job test with `JobRepository`.

## 6. Asserting Checkpoints of `ItemStream.open()` and `update()`

For stateful readers/writers, Spring Batch calls `ItemStream.open(executionContext)` at initialization and `ItemStream.update(executionContext)` at checkpoints. A common bug is a component writing the right offset in `update` yet failing to read that offset in `open` on the subsequent run.

Illustrative component managing an offset:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;

public class OffsetTracker implements ItemStream {

    private long currentOffset;

    @Override
    public void open(ExecutionContext context) {
        currentOffset = context.getLong("reader.offset", 0L);
    }

    public void advance(long recordsProcessed) {
        currentOffset += recordsProcessed;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("reader.offset", currentOffset);
    }

    @Override
    public void close() {
        // No resources held in this example.
    }

    public long currentOffset() {
        return currentOffset;
    }
}
```

The test must check both directions: **restore then save**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OffsetTrackerTest {

    @Test
    void restoresAndUpdatesCheckpoint() {
        ExecutionContext previousCheckpoint = new ExecutionContext();
        previousCheckpoint.putLong("reader.offset", 100L);

        OffsetTracker tracker = new OffsetTracker();
        tracker.open(previousCheckpoint);

        assertEquals(100L, tracker.currentOffset());

        tracker.advance(20);
        tracker.update(previousCheckpoint);

        assertEquals(120L, previousCheckpoint.getLong("reader.offset"));

        OffsetTracker restartedTracker = new OffsetTracker();
        restartedTracker.open(new ExecutionContext(previousCheckpoint));

        assertEquals(120L, restartedTracker.currentOffset());
    }
}
```

`new ExecutionContext(previousCheckpoint)` here simulates passing a state snapshot to a new instance. This is still an **in-memory unit test**. To prove a real restart, you must launch a second run against the same `JobRepository` using **the same JobParameters identifying the JobInstance**.

In production, `ItemStream` must be registered with the step; if a stateful reader/writer is wrapped in a delegate or not properly managed by the framework, `open/update` callbacks may not be invoked as expected. In that situation, the unit test above still passes, while a checkpoint integration test will catch the defect.

## 7. Integration Test: Running a Job and Asserting Step/Job Context

### 7.1. Libraries and Environment

For a Spring Boot 3.x project using Gradle Groovy DSL, the relevant dependencies are typically:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-batch-test` provides `@SpringBatchTest`, `JobLauncherTestUtils`, `MetaDataInstanceFactory`, and scope utilities. In the following example, H2 is used solely for testing; a production application may use another database for its metadata repository.

### 7.2. Test Example with a Real Repository

This example builds a small job with a step that writes `import.total` and `import.phase`. A listener is configured to promote only `import.total` to the job context. The test verifies three levels: step result, job result, and data read back through `JobExplorer`.

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
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = ExecutionContextIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:batch_context_test;DB_CLOSE_DELAY=-1"
    }
)
class ExecutionContextIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void stepValueIsPromotedAndPersisted() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("test.run", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("importStep"))
            .findFirst()
            .orElseThrow();

        ExecutionContext stepContext = step.getExecutionContext();
        assertEquals(7L, stepContext.getLong("import.total"));
        assertEquals("READY", stepContext.getString("import.phase"));

        ExecutionContext jobContext = execution.getExecutionContext();
        assertEquals(7L, jobContext.getLong("import.total"));
        assertFalse(jobContext.containsKey("import.phase"));

        // Read back from JobRepository via a metadata query API.
        JobExecution restored = jobExplorer.getJobExecution(execution.getId());
        assertNotNull(restored);

        assertEquals(7L,
            restored.getExecutionContext().getLong("import.total"));

        StepExecution persistedStep = restored.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("importStep"))
            .findFirst()
            .orElseThrow();

        assertEquals(7L,
            persistedStep.getExecutionContext().getLong("import.total"));
        assertEquals("READY",
            persistedStep.getExecutionContext().getString("import.phase"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BatchTestConfig.class)
    static class TestApplication {
    }

    @TestConfiguration
    static class BatchTestConfig {

        @Bean
        ExecutionContextPromotionListener importPromotionListener() {
            ExecutionContextPromotionListener listener =
                new ExecutionContextPromotionListener();
            listener.setKeys(new String[] {"import.total"});
            return listener;
        }

        @Bean
        Step importStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ExecutionContextPromotionListener importPromotionListener) {

            return new StepBuilder("importStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    ExecutionContext context = contribution
                        .getStepExecution()
                        .getExecutionContext();

                    context.putLong("import.total", 7L);
                    context.putString("import.phase", "READY");

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .listener(importPromotionListener)
                .build();
        }

        @Bean
        Job importJob(JobRepository repository, Step importStep) {
            return new JobBuilder("importJob", repository)
                .start(importStep)
                .build();
        }
    }
}
```

**Key points when reading this test:**

- `spring.batch.job.enabled=false` stops Spring Boot from auto-running the job during test startup; the test explicitly calls `launchJob`.
- `test.run` takes a unique value per test, avoiding collisions with the `JobInstance` of an earlier run.
- `@SpringBatchTest` registers Spring Batch test utilities. When the context has only one `Job` bean, the utility may bind to it automatically; if there are multiple jobs, call `jobLauncherTestUtils.setJob(jobUnderTest)` before launching.
- Two assertions on step context verify data-writing logic; assertions on job context verify **promotion**. `import.phase` is absent from job context because it is not listed in `setKeys`.
- `jobExplorer.getJobExecution(id)` retrieves metadata from the repository. Reading it back is stronger evidence than inspecting only the in-memory `JobExecution` object returned by `launchJob`.
- The test database needs the Spring Batch schema matching your library version and a properly configured transaction manager. For applications targeting a real database, run integration tests against that same database type when specifically verifying JDBC/serializer behavior.

### 7.3. When You Only Want to Run One Step

Spring Batch 5's `JobLauncherTestUtils` lets you run a specific step:

```java
JobExecution execution = jobLauncherTestUtils.launchStep("importStep");

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions().stream()
    .filter(s -> s.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertEquals(7L, step.getExecutionContext().getLong("import.total"));
```

`launchStep` executes the step inside a test wrapper job; it does not run the full flow of the original job. Therefore, if the requirement is verifying whether the next step receives promoted data, run **the full job** or explicitly test the data handoff between steps.

## 8. Asserting `ExecutionContextPromotionListener`

When data needs to pass to a subsequent step, `ExecutionContextPromotionListener` copies configured keys from step context to job context after the step finishes. By default, the listener promotes only when **the step's exit code matches `COMPLETED`**. This condition relies on `ExitStatus`, not merely on whether the map contains the key.

You can test the listener directly without a database:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class PromotionListenerTest {

    private ExecutionContextPromotionListener listener() throws Exception {
        ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
        listener.setKeys(new String[] {"report.total"});
        listener.afterPropertiesSet();
        return listener;
    }

    @Test
    void promotesAfterSuccessfulStep() throws Exception {
        StepExecution step = MetaDataInstanceFactory.createStepExecution();
        step.getExecutionContext().putLong("report.total", 42L);
        step.setExitStatus(ExitStatus.COMPLETED);

        listener().afterStep(step);

        assertEquals(42L,
            step.getJobExecution().getExecutionContext()
                .getLong("report.total"));
    }

    @Test
    void doesNotPromoteAfterFailedStepByDefault() throws Exception {
        StepExecution step = MetaDataInstanceFactory.createStepExecution();
        step.getExecutionContext().putLong("report.total", 42L);
        step.setExitStatus(ExitStatus.FAILED);

        listener().afterStep(step);

        assertFalse(step.getJobExecution().getExecutionContext()
            .containsKey("report.total"));
    }
}
```

To promote for other exit codes as well, call `setStatuses(...)` and write tests for each business exit code. `setStrict(true)` requires declared keys to exist; when testing missing-key cases, examine both the listener's behavior and how the framework handles exceptions thrown in the `afterStep` callback.

Never assume that putting a key into step context automatically syncs it to job context. This distinction is why many `ExecutionContext` tests need a pair of assertions: **step has the value** and **job does or does not have the value according to policy**.

## 9. Asserting Inside `@StepScope` and `@JobScope`

`@StepScope` beans can receive data via Spring Expression Language:

```java
@Value("#{stepExecutionContext['tenant.id']}")
String tenantId;
```

Meanwhile, a value in job context is read via:

```java
@Value("#{jobExecutionContext['import.total']}")
Long importTotal;
```

If you test a step-scoped bean without creating a scope, you may encounter an error indicating no active step context. `StepScopeTestUtils.doInStepScope` activates the scope for a test `StepExecution`.

Example with a Spring-managed `@StepScope` bean:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;

// tenantFormatter is a @StepScope bean injected into the test.
StepExecution step = MetaDataInstanceFactory.createStepExecution();
step.getExecutionContext().putString("tenant.id", "tenant-A");

String displayName = StepScopeTestUtils.doInStepScope(
    step,
    () -> tenantFormatter.formatTenant()
);

assertEquals("TENANT-A", displayName);
```

In the example, `tenantFormatter.formatTenant()` is a business component method converting an ID into a display name. The test should assert **the output of the component using the context value**, not merely read back the key you just placed into `StepExecution`.

For `@JobScope`, use `JobScopeTestUtils` following the same principle. Before writing assertions, confirm whether the bean pulls from `stepExecutionContext`, `jobExecutionContext`, or `jobParameters`; these three sources have different contracts.

## 10. Asserting Restart: The Checkpoint Must Come from the Previous Run

A core purpose of `ExecutionContext` is supporting resumption after a batch interruption. A valuable restart test must prove that state **persisted during the failed run** is supplied back to the reader/writer on the next run.

### 10.1. Sequence of a Genuine Restart Test

1. Prepare a fixed input dataset and construct a set of `JobParameters`.
2. Run the job, let it commit one or more chunks, and then deliberately inject an error at a deterministic point.
3. Verify the first run has `BatchStatus.FAILED`; read the persisted metadata and identify the last **committed** checkpoint.
4. Remove the failure condition and re-run **the same job with the same identifying JobParameters** against the existing repository.
5. Capture the checkpoint that `ItemStream.open` actually receives on restart; assert this checkpoint matches the state saved in Step 3.
6. Assert the second run is `COMPLETED`, with no lost or duplicated business effects (e.g., exact output ID set), and that the final checkpoint reflects all processed data.

This can be visualized as:

```text
Run 1:
read 1..50  -> COMMIT -> context offset=50
read 51..75 -> FAIL   -> transaction not committed

Repository: saved checkpoint = 50
                |
                v
Run 2 (same JobInstance):
ItemStream.open(context offset=50)
continue reading from 51 -> complete
```

Offset numbers are just illustrative: when an error and rollback happen mid-chunk, compare against the **actual commit boundary**. Never grab an in-memory offset variable right before the exception and assume it is the durable checkpoint.

### 10.2. Assertion Framework for a Restart Test

In an integration test, suppose the job is configured with a checkpointable reader and a test probe recording the offset received in `open`:

```java
JobParameters sameParameters = new JobParametersBuilder()
    .addString("business.date", "2026-11-16")
    .toJobParameters();

// Configure the fixture to fail after committing one chunk.
failureSwitch.failAfterFirstCommittedChunk();

JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

JobExecution persistedFirst =
    jobExplorer.getJobExecution(first.getId());
assertNotNull(persistedFirst);

StepExecution failedStep = persistedFirst.getStepExecutions().stream()
    .filter(s -> s.getStepName().equals("readCustomersStep"))
    .findFirst()
    .orElseThrow();

long committedOffset =
    failedStep.getExecutionContext().getLong("reader.offset");

// Next run uses the same JobParameters, with simulated failure disabled.
failureSwitch.disableFailure();
checkpointProbe.reset();

JobExecution second = jobLauncherTestUtils.launchJob(sameParameters);

assertEquals(BatchStatus.COMPLETED, second.getStatus());
assertEquals(
    first.getJobInstance().getId(),
    second.getJobInstance().getId()
);
assertEquals(committedOffset, checkpointProbe.offsetSeenInOpen());

// In addition to the checkpoint, assert output data has the exact ID set,
// without duplicates from reprocessing the committed portion.
```

This is a **test skeleton for a restart fixture**: `failureSwitch` and `checkpointProbe` are application-defined test doubles. To use this pattern, wire them into the real reader/writer in the test. Without a probe, looking only at the context after the second run does not prove the reader *started* at the expected checkpoint.

Further note: a restart is valid only when the job permits restarts, the prior run ended in a restartable status, identifying parameters are unchanged, and the metadata repository still holds the data. If you change an identifying parameter to a new timestamp on the second run, the system may create a **new JobInstance**; that is a fresh run, not a restart.

## 11. Advanced Scenarios to Test

### 11.1. Were Values Actually Persisted?

Two checks have different verification strength:

```java
// Inspect in-memory object state.
assertEquals(100L, execution.getExecutionContext().getLong("count"));

// Inspect state reconstituted from the metadata repository.
JobExecution reloaded = jobExplorer.getJobExecution(execution.getId());
assertNotNull(reloaded);
assertEquals(100L,
    reloaded.getExecutionContext().getLong("count"));
```

When testing checkpoint durability, reload `StepExecution` from `JobExplorer` or execute a real restart. A test that merely modifies `ExecutionContext` with `put` and asserts on the same object bypasses serialization, transactions, and `JobRepository`.

Do not assert raw strings inside the `SHORT_CONTEXT` / `SERIALIZED_CONTEXT` columns of `BATCH_STEP_EXECUTION_CONTEXT` or `BATCH_JOB_EXECUTION_CONTEXT`: the serialization format is an infrastructure detail subject to change. Inspect via Spring Batch APIs unless the test specifically targets verifying the schema or serializer.

### 11.2. Value Types and Serialization

Prefer keys with small, clearly typed values: strings, integers, ISO-formatted timestamp strings, business identifiers. When storing custom objects is necessary, configure a compatible serializer and write an integration test verifying the object can be written and read back intact. An in-memory assertion does not guarantee the class serializes successfully.

Assertions should document the data-type contract:

```java
assertEquals(200L, context.getLong("reader.offset")); // Long
assertEquals(3, context.getInt("retry.count"));        // Integer
assertEquals("READY", context.getString("phase"));     // String
```

Do not assume `"200"` and `200L` are interchangeable values in `ExecutionContext`.

### 11.3. Chunk Retries, Skips, and Rollbacks

In a chunk with retries/rollbacks, in-memory object state may advance ahead of the committed checkpoint. Assert in order:

- `StepExecution`'s `readCount` / `writeCount` / `rollbackCount` to understand processing outcomes.
- Context after a successful chunk or after job completion, aligned with transaction boundaries.
- Context **read back from the repository** if restartability is required.
- Business data to confirm side effects are not duplicated on rerun.

If checking a key like `lastSuccessfulId`, define precisely whether "successful" means processed in the JVM, passed to the writer, or transaction-committed. Assertions are trustworthy only when that definition matches where the code updates the context.

### 11.4. Partitioning and Parallel Steps

Each partition/step execution can have its own context. Therefore, never arbitrarily pick `jobExecution.getStepExecutions().iterator().next()` when multiple steps or partitions exist. Filter by step/partition name, and identify which keys are outputs of individual partitions versus which keys are lifted to job context by an aggregator or listener. Iteration order in a `Set<StepExecution>` is not a business contract.

Example filtering for the exact step before asserting:

```java
StepExecution target = execution.getStepExecutions().stream()
    .filter(step -> step.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertEquals(7L,
    target.getExecutionContext().getLong("import.total"));
```

In parallel jobs, also account for shared data access and non-deterministic completion order; assertions should rely on final state and defined aggregation criteria.

## 12. Common Mistakes When Asserting `ExecutionContext`

| Mistake | Why the Test Is Unreliable | Fix |
| --- | --- | --- |
| Asserting only `BatchStatus.COMPLETED` | Job may complete with wrong checkpoints or business metadata | Assert specific keys and values as well |
| Reading job context for a key written only at step level | The two contexts are independent | Identify the exact scope or configure promotion |
| Using a default getter for a required key | A missing key can still return the expected value | Assert `containsKey` first |
| Calling `put` on context and asserting that same value | Only tests library getters/setters, not application logic | Invoke the recorder, reader, listener, or run a real step |
| Using `isDirty()` to claim persistence | Dirty flag only reflects object mutation | Reload from `JobExplorer` or perform a restart |
| Running restart with new `JobParameters` | Creates a new `JobInstance` instead of resuming the old one | Keep identifying parameters unchanged |
| Asserting checkpoint right before transaction rollback | That value may not have committed | Assert the checkpoint persisted via repository |
| Comparing the whole context map against a fixed map | Framework/readers may add valid metadata keys | Assert the keys belonging to your feature contract |
| Taking the first element of the `StepExecution` set | Order is undefined with multiple steps | Filter by step name or partition |
| Putting non-serializable objects into context | Unit tests pass, integration tests may fail on metadata save | Use suitable types and test real read/write persistence |

An assertion with clear failure messages speeds up debugging:

```java
String key = "reader.offset";
ExecutionContext context = step.getExecutionContext();

assertTrue(
    context.containsKey(key),
    () -> "Missing key '" + key
        + "' in step " + step.getStepName()
        + "; actual keys: " + context.toMap().keySet()
);

assertEquals(
    120L,
    context.getLong(key),
    "Wrong checkpoint in " + step.getStepName()
);
```

In Spring Batch 5.1+, `toMap()` returns a read-only view of context entries; in older versions, keys can be obtained via `entrySet()`. Do not print full context values in error logs if the context holds sensitive data.

## 13. Practice Exercises

**Exercise 1 — Unit testing contract keys.** Write an `InvoiceProgressRecorder` that writes `invoice.lastId` (Long), `invoice.successCount` (Integer), and `invoice.phase` (String) into step context. Use `MetaDataInstanceFactory` and `assertAll` to verify the right values, right scope, and one key that must remain absent.

**Exercise 2 — Promotion.** One step produces `invoice.total = 250L`; the next step needs to read that total. Configure `ExecutionContextPromotionListener` for `invoice.total`. Write tests for both `ExitStatus.COMPLETED` and `ExitStatus.FAILED`, verifying which case delivers the key to job context.

**Exercise 3 — Persistence and restart.** Create a chunk step processing 100 rows with commit interval 20, deliberately failing after at least one chunk commits. Verify the checkpoint read back from `JobExplorer`, then restart with the same identifying `JobParameters`. Record the offset seen in `ItemStream.open` and assert all 100 rows appear exactly once in the final output.

Completion criteria go beyond "green tests": **assert the right values in the right context, at the right time, and at the right testing level (in-memory, repository, or restart)**.

## 14. Version Notes and References

- The code snippets above target **Spring Batch 5.x**: `ExecutionContext` resides in `org.springframework.batch.item`; `@SpringBatchTest` provides `JobLauncherTestUtils`.
- **Spring Batch 6.x** changed several packages and test APIs. `JobLauncherTestUtils` is deprecated in favor of `JobOperatorTestUtils`; `JobExplorer` also changed in relation to `JobRepository`. When upgrading, verify imports, API signatures, and how test infrastructure is constructed for your exact version. The concepts of two contexts, checkpoints, promotion, and restart remain the foundation for designing assertions.

Official documentation:

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 — `ExecutionContext` API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ExecutionContext.html)
- [Spring Batch 5.2 — `MetaDataInstanceFactory`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [Spring Batch 5.2 — `StepScopeTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/test/StepScopeTestUtils.html)
- [Spring Batch — Common Batch Patterns / Passing Data to Future Steps](https://docs.spring.io/spring-batch/reference/common-patterns.html)
- [Spring Batch 6 — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
