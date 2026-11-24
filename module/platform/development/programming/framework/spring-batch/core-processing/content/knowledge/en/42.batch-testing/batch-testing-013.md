# Testing Listeners in Spring Batch

## 1. How Should Listeners Be Tested?

In Spring Batch, **listeners** are where applications execute work at lifecycle milestones of a `Job`, `Step`, `Chunk`, and individual items: logging, collecting metrics, flagging invalid records, sending notifications, or adjusting `ExitStatus`. A listener method working when called directly is not enough to guarantee it is **registered with the job/step**, invoked by Spring Batch **at the right time**, and behaves properly under **retries, skips, rollbacks, failures, or restarts**.

For example, consider a job importing three strings `["A", "BAD", "C"]`, where the processor throws an error on `"BAD"` and the step permits skipping one item. We must distinguish:

- `ItemProcessListener.onProcessError`: invoked when the processor throws an error; an error might be retried, so this error callback **does not guarantee the item is ultimately skipped**.
- `SkipListener.onSkipInProcess`: invoked when the system decides to actually skip item `"BAD"`.
- `StepExecutionListener.afterStep`: receives `StepExecution` to read `processSkipCount` or adjust `ExitStatus`.
- `ChunkListener.afterChunk`: runs after the chunk commits; `ItemWriteListener.afterWrite` runs before commit, so do not equate "afterWrite was called" with "data was committed."

A sound testing strategy consists of three layers:

| Testing Layer | How It Runs | What It Proves |
|---|---|---|
| **Unit test** | Instantiate the listener and `StepExecution` / `JobExecution` objects, call callbacks directly | Business rules, success/failure branches, `ExecutionContext` updates, return values |
| **Step integration test** | Run a real step via `spring-batch-test`, intentionally injecting reader/processor/writer errors | Listener is registered and invoked by the framework on the right events; `skipCount`, `writeCount`, output data match |
| **Job integration test** | Run the full job via `JobLauncherTestUtils.launchJob` | `JobExecutionListener`, multi-step flow, final status, and external system effects |

**Version scope:** The Java imports and examples below target **Spring Batch 5.2.x, Spring Boot 3.x, Java 17+, JUnit Jupiter (JUnit 5)**. In Spring Batch 5, write callbacks accept `Chunk<? extends T>`, not the `List<T>` signature from older Spring Batch examples. Spring Batch 6 reorganized several packages and test utilities (such as `JobOperatorTestUtils`), so verify your project's API version before copying imports verbatim.

## 2. Selecting the Right Callback to Test

| Listener | Representative Callbacks | Test Scenarios to Include |
|---|---|---|
| `JobExecutionListener` | `beforeJob`, `afterJob` | Job succeeds, job fails; notifications/statuses recorded properly |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Preparing `ExecutionContext`, counting skips, returning conditional `ExitStatus` |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Chunk commits successfully; rollback; not treating error callbacks as commits |
| `ItemReadListener<T>` | `beforeRead`, `afterRead`, `onReadError` | Successful read, read error, end of input (reader returns `null`) |
| `ItemProcessListener<I,O>` | `beforeProcess`, `afterProcess`, `onProcessError` | Normal processing, filtered item (processor returns `null`), exception |
| `ItemWriteListener<O>` | `beforeWrite`, `afterWrite`, `onWriteError` | Successful write; writer throws error; retry repeats callbacks |
| `SkipListener<I,O>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Errors genuinely skipped at each stage; not confused with errors recovered by retry |

Simplified diagram for a successful chunk:

```text
beforeStep
  beforeChunk             (transaction started)
    beforeRead -> afterRead
    beforeProcess -> afterProcess
    ...                   (repeats per item)
    beforeWrite -> afterWrite
    onSkipInX              (if any items were skipped)
  COMMIT
  afterChunk              (after commit)
afterStep
```

When a chunk rolls back, the framework may invoke `afterChunkError`, then retry/scan items according to fault-tolerance configuration. Therefore, **never write tests assuming every listener callback fires exactly once** across all execution paths. Verify behavior based on listener type, retry/skip config, commit counts, and final data.

## 3. Preparing the Test Environment

In a Spring Boot project using Maven, include batch runtime, Spring Batch Test, and JUnit 5 libraries. Example dependencies (versions managed by the Spring Boot BOM):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.batch</groupId>
        <artifactId>spring-batch-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

For Gradle projects, declare the corresponding dependencies with `implementation` and `testImplementation`/`testRuntimeOnly`. H2 is simply a convenient choice for integration tests; if a job relies on PostgreSQL-, SQL Server-, or Oracle-specific behavior, add tests against that exact database engine.

Two key utilities in `spring-batch-test` on the 5.x line:

- `MetaDataInstanceFactory` creates mock `JobExecution` / `StepExecution` objects with valid metadata for unit tests without running a job.
- `@SpringBatchTest` supports the test context and provides `JobLauncherTestUtils` / `JobRepositoryTestUtils`. `launchStep("stepName")` runs a single step; `launchJob(...)` runs the entire job. If the context has multiple `Job` beans, specify the target job on `JobLauncherTestUtils`.

Avoid using `@SpringBootTest` for every unit test, as loading the full Spring context is slow and can obscure bugs in the listener itself.

## 4. Unit Testing `StepExecutionListener`: Logic and `ExitStatus`

Suppose the business requirement is to mark in `ExecutionContext` that the step started; if the step completes successfully but had skipped items, return exit code `COMPLETED_WITH_SKIPS`. For a failed step or zero skips, leave the exit code unchanged.

**Production code — `ImportStepListener.java`:**

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext()
                .putString("import.listener.started", "yes");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED_WITH_SKIPS");
        }
        return null; // Keep existing ExitStatus.
    }
}
```

**Unit test — `ImportStepListenerTest.java`:**

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class ImportStepListenerTest {

    private ImportStepListener listener;
    private StepExecution stepExecution;

    @BeforeEach
    void setUp() {
        listener = new ImportStepListener();
        stepExecution = MetaDataInstanceFactory.createStepExecution();
    }

    @Test
    void beforeStep_shouldSetContextMarker() {
        listener.beforeStep(stepExecution);

        assertEquals(
                "yes",
                stepExecution.getExecutionContext()
                        .getString("import.listener.started")
        );
    }

    @Test
    void afterStep_shouldReturnCustomExitStatus_whenCompletedWithSkips() {
        stepExecution.setStatus(BatchStatus.COMPLETED);
        stepExecution.setProcessSkipCount(2);

        ExitStatus result = listener.afterStep(stepExecution);

        assertNotNull(result);
        assertEquals("COMPLETED_WITH_SKIPS", result.getExitCode());
    }

    @Test
    void afterStep_shouldNotHideFailure() {
        stepExecution.setStatus(BatchStatus.FAILED);
        stepExecution.setProcessSkipCount(2);

        assertNull(listener.afterStep(stepExecution));
    }

    @Test
    void afterStep_shouldKeepNormalCompletion_whenNoSkips() {
        stepExecution.setStatus(BatchStatus.COMPLETED);

        assertNull(listener.afterStep(stepExecution));
    }
}
```

These cases are valuable because they verify **inputs and output states**, rather than merely confirming the method "did not throw an exception." `StepExecution.getSkipCount()` aggregates skips across read/process/write; use `setProcessSkipCount(...)` to simulate one component of that total.

Distinguish two concepts:

- `BatchStatus` describes framework-managed execution status, such as `COMPLETED` or `FAILED`.
- `ExitStatus` is the exit code usable to decide the job's next branch (e.g., `.on("COMPLETED_WITH_SKIPS")`).

Returning `null` from `afterStep` means contributing no override exit status. Spring Batch combines the `ExitStatus` returned by the listener with the step's exit status; do not assume a callback can arbitrarily turn a `FAILED` step into `COMPLETED`. A unit test calling `afterStep` directly only verifies the return value; **verifying real flow transitions requires running the step/job in an integration test**.

## 5. Unit Testing Error and Skip Callbacks

An application may collect rejected record IDs for reporting. The listener should simply record the `onSkipInProcess` event; deciding whether a record gets skipped belongs to the step configuration.

**Production code — `RejectedItemListener.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.batch.core.SkipListener;

public class RejectedItemListener implements SkipListener<String, String> {

    private final List<String> rejectedIds = new ArrayList<>();

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        rejectedIds.add(item);
    }

    public List<String> rejectedIds() {
        return List.copyOf(rejectedIds);
    }
}
```

**Unit test:**

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class RejectedItemListenerTest {

    @Test
    void onSkipInProcess_shouldRecordRejectedItem() {
        RejectedItemListener listener = new RejectedItemListener();

        listener.onSkipInProcess(
                "customer-42",
                new IllegalArgumentException("Invalid email")
        );

        assertEquals(List.of("customer-42"), listener.rejectedIds());
    }
}
```

This test verifies **the callback's logic**, but **does not prove the callback only fires when a skip occurs**, because we invoked the method directly. To distinguish an error recovered by retry from an error genuinely skipped, run a fault-tolerant step as shown in the next section.

One design note: `ArrayList` in the example works for unit tests or a fresh listener created per execution. For a singleton listener shared across concurrent jobs/steps, do not store per-run state in a field like this; prefer `ExecutionContext`, execution-scoped storage, or a recording mechanism keyed safely by `jobExecutionId`/`stepExecutionId`.

## 6. Integration Test: Verifying Spring Batch Actually Invokes the Listener

The example below builds a step reading three strings `"ok", "bad", "end"`. The processor intentionally throws `IllegalArgumentException` on `"bad"`; the step permits one skip. We simultaneously verify **step status**, **item counts**, and **invoked callback**.

This is a self-contained test class illustrating full listener registration. It uses Spring Boot 3.x, Spring Batch 5.x, and H2 on the `test` classpath:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = SkipListenerIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class SkipListenerIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private TrackingSkipListener trackingSkipListener;

    @BeforeEach
    void resetListener() {
        trackingSkipListener.clear();
    }

    @Test
    void launchStep_shouldInvokeSkipListenerForRejectedItem()
            throws Exception {

        JobExecution jobExecution =
                jobLauncherTestUtils.launchStep("importStep");

        StepExecution stepExecution = jobExecution
                .getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(3L, stepExecution.getReadCount());
        assertEquals(2L, stepExecution.getWriteCount());
        assertEquals(1L, stepExecution.getProcessSkipCount());
        assertEquals(List.of("bad"), trackingSkipListener.skipped());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        TrackingSkipListener trackingSkipListener() {
            return new TrackingSkipListener();
        }

        @Bean
        ItemReader<String> reader() {
            return new ListItemReader<>(List.of("ok", "bad", "end"));
        }

        @Bean
        Step importStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                ItemReader<String> reader,
                TrackingSkipListener listener) {

            return new StepBuilder("importStep", jobRepository)
                    .<String, String>chunk(2, transactionManager)
                    .reader(reader)
                    .processor(item -> {
                        if ("bad".equals(item)) {
                            throw new IllegalArgumentException("Rejected");
                        }
                        return item.toUpperCase();
                    })
                    .writer(chunk -> { /* Mock writer */ })
                    .faultTolerant()
                    .skip(IllegalArgumentException.class)
                    .skipLimit(1)
                    .listener(listener)
                    .build();
        }

        @Bean
        Job importJob(JobRepository jobRepository, Step importStep) {
            return new JobBuilder("importJob", jobRepository)
                    .start(importStep)
                    .build();
        }
    }

    static class TrackingSkipListener
            implements SkipListener<String, String> {

        private final List<String> skipped = new ArrayList<>();

        @Override
        public void onSkipInProcess(String item, Throwable error) {
            skipped.add(item);
        }

        List<String> skipped() {
            return List.copyOf(skipped);
        }

        void clear() {
            skipped.clear();
        }
    }
}
```

Because the test above launches the step only once, a `ListItemReader` created as a configuration bean suffices for illustration. In a test suite executing multiple launches against the same `ApplicationContext`, create a fresh reader per execution (usually a `@StepScope` bean) or reset the context, because `ListItemReader` holds read-position state.

**Why are these assertions meaningful?**

1. `BatchStatus.COMPLETED` shows that one bad item does not fail the step when `skipLimit(1)` permits it.
2. `readCount=3`, `writeCount=2`, and `processSkipCount=1` confirm real batch processing rather than merely "an event was recorded."
3. The list `["bad"]` confirms the data passed to `SkipListener` matches the rejected item.
4. `.listener(listener)` is wired in step config: if registration were omitted, the test would see `processSkipCount=1` yet an empty `skipped()`, catching the wiring bug.

In a real application, replace the mock writer with one writing to a test table or inspectable store. Then also assert that **no bad item appears in output** and **only valid items were committed**.

### Testing an Error When Skip Limit Is Zero

To verify the listener **is not called** when an error causes the step to fail, create a variant configured with `skipLimit(0)` (or an exception excluded from `.skip(...)`). Expectations:

```text
Step BatchStatus      = FAILED
processSkipCount      = 0
TrackingSkipListener  = did not record "bad"
failureExceptions     = contains failure cause
```

This clearly distinguishes "an exception was thrown" from "an item was skipped." If retry is enabled, also test failing on the first attempt and succeeding on the next: `onProcessError` may be called, whereas `SkipListener` must not report a completed skip.

## 7. Testing Annotation-Based Listeners

Spring Batch allows writing callbacks via annotations on a plain Java object:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.annotation.AfterStep;
import org.springframework.batch.core.annotation.BeforeStep;

public class AnnotatedAuditListener {

    @BeforeStep
    public void markStart(StepExecution stepExecution) {
        stepExecution.getExecutionContext().put("audit.started", true);
    }

    @AfterStep
    public void markEnd(StepExecution stepExecution) {
        stepExecution.getExecutionContext().put("audit.finished", true);
    }
}
```

Register the object with the step builder:

```java
new StepBuilder("myStep", jobRepository)
    .<String, String>chunk(10, transactionManager)
    .reader(reader)
    .writer(writer)
    .listener(new AnnotatedAuditListener())
    .build();
```

A unit test calling `markStart(...)` and `markEnd(...)` directly **does not test whether Spring Batch detects the annotations**. Use `launchStep("myStep")` to confirm both `audit.started` and `audit.finished` keys in `StepExecution.getExecutionContext()` are `true`.

Similarly, a class annotated with `@BeforeJob` / `@AfterJob` must be registered on the **job** and tested via `launchJob(...)`. `launchStep(...)` creates a separate wrapper job to run the step, so do not use it to verify that the original job's listeners were invoked.

## 8. Failure Cases to Simulate Intentionally

### 8.1. Listener Throws an Exception

Make a callback such as `beforeStep` or `beforeChunk` throw `IllegalStateException`. Run the real step and assert `BatchStatus.FAILED` along with the recorded error cause. This tests operational behavior: an exception in a listener can abort the step.

Specifically, `StepExecutionListener.afterStep` has special behavior per API contract: exceptions from this callback are logged by the framework and do not automatically alter the step's exit status. Therefore, do not assume every callback behaves identically as "throwing an exception fails the job"; check each callback's contract and test the real execution path.

### 8.2. Retry Differs from Skip

Suppose a writer fails on the first write attempt yet succeeds on retry:

- `onWriteError` may be called even though `writeCount` ultimately increments.
- `onSkipInWrite` is meaningful only when an item is actually decided to be skipped.
- Do not hardcode exact `beforeWrite`/`onWriteError` invocation counts if changing retry/rollback policies can alter attempt counts. Verify business conditions: output data, `writeSkipCount`, and appropriate callback history.

### 8.3. Commit and Rollback Timing

| Callback | Relationship to Transaction | Test Expectation |
|---|---|---|
| `beforeChunk` | Inside transaction, before reading items | Record chunk start |
| `afterWrite` | After writer call, **before commit** | Do not yet conclude data committed |
| `afterChunk` | After chunk commits successfully, outside transaction | Chunk-level success event |
| `afterChunkError` | After chunk is marked for rollback; callback invoked after rollback | Record error, do not count as success |
| `onSkipInRead/Process/Write` | Framework defers skip notification until the right point before commit | Inspect only genuinely skipped items |

If an error callback must persist an audit record even when the main transaction rolls back, consider a separate transaction such as `PROPAGATION_REQUIRES_NEW` and **test against a real transactional database**; tests with mocks alone cannot prove commit boundaries.

### 8.4. Re-Execution and Data Isolation

With retries/restarts, a listener can encounter the same business key across different executions. Test design should distinguish `JobInstance`, `JobExecution`, and `StepExecution`. For external effects like emails, messages, or HTTP requests, test duplicate-prevention / idempotency mechanisms keyed by an appropriate business key, because database rollbacks do not undo external calls.

## 9. Testing `@StepScope` and Runtime Data

When a listener or a component it calls relies on `jobParameters`, `StepExecution`, or `ExecutionContext`, tests may need to construct a step environment:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;

class StepContextTest {

    @Test
    void shouldReadValueFromStepContext() throws Exception {
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution();

        stepExecution.getExecutionContext().putString(
                "source.file", "input.csv"
        );

        String actual = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> stepExecution.getExecutionContext()
                        .getString("source.file")
        );

        assertEquals("input.csv", actual);
    }
}
```

This snippet illustrates opening a simulated step scope. It **does not itself test a `@StepScope` proxy** because the lambda reads `StepExecution` directly; to test an actual bean using late binding, fetch the `@StepScope` bean from the Spring test context inside this scope and assert the value the bean receives.

In addition to `StepScopeTestUtils`, `@SpringBatchTest` includes `StepScopeTestExecutionListener` to supply `StepExecution` for tests using Spring TestContext. When there is no need to test scope or container wiring, direct unit tests are usually shorter and easier to diagnose.

## 10. Writing Assertions Against Event Contracts

Strong assertions generally check **observable outcomes**:

- **Step listener:** `ExecutionContext` after `beforeStep`, `ExitStatus` code after `afterStep`; if job branching occurs, assert whether the next step ran.
- **Job listener:** `JobExecution` status and notifications/audit records persisted accurately for success/failure; test via `launchJob`.
- **Chunk listener:** never equate `afterWrite` with commit; verify `afterChunk` in success cases and `afterChunkError` on rollback.
- **Item listener:** item passed to callback, right exception type, list of items processed or saved to target.
- **Skip listener:** `readSkipCount`, `processSkipCount`, `writeSkipCount`, and items actually skipped; avoid using `on*Error` as a substitute for skip verification.

Avoid these anti-patterns:

| Anti-Pattern | Why It Produces Unreliable Tests | Improvement |
|---|---|---|
| Calling callback directly and concluding listener is registered | Misses `.listener(...)` wiring bugs | Add an integration test running the step/job |
| Asserting exact single invocation for every callback under retry | Rollback/retry can re-invoke processing callbacks | Verify final outcomes and event types |
| Using `Thread.sleep(...)` to wait for listeners | Slow and flaky tests | Run job synchronously or wait via explicit synchronization conditions |
| Sharing one mutable listener bean across parallel tests | Data leaks from other tests or jobs | Instantiate fresh, reset intentionally, or key state by execution |
| Mocking only the database and claiming transaction committed | Mocks do not execute transactions | Test with a transactional DB and verify final data |
| Reusing `JobParameters` for repeated launches of a `COMPLETED` job | Spring Batch may block re-running the same `JobInstance` | Generate unique identifying parameters per execution or clean test metadata |

## 11. Practice Exercise

Design a job importing an order list with four lines: `O-1` valid, `O-2` missing customer ID, `O-3` valid, and `O-4` hitting a temporary writer error. Add:

1. `ItemProcessListener` recording `O-2`'s exception.
2. `SkipListener` recording `O-2` if the step allows skipping.
3. `ItemWriteListener` recording `O-4`'s temporary error; configure one retry so the writer succeeds on the second attempt.
4. `StepExecutionListener` returning exit code `COMPLETED_WITH_SKIPS` when the step succeeds with skips.
5. Unit tests checking each listener's rules and an integration test verifying `processSkipCount=1`, `writeSkipCount=0`, the expected exit code, and exactly three valid orders in the destination store.

While testing, explain why the writer error callback **is not equivalent** to `onSkipInWrite`. Then switch the policy to disallow skipping and observe how statuses and listeners change. This exercise tests both isolated logic and how listeners coordinate with fault-tolerance policies.

## 12. Reference Documentation

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, step-scope testing.
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): callbacks, invocation timing, and transaction relationships.
- [Spring Batch 5.2 — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): distinguishing `BatchStatus`, `ExitStatus`, and job branch selection.
- [Spring Batch 5.2 API — SkipListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html) and [ChunkListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/ChunkListener.html): method signatures and callback notes.
- For Spring Batch 6, refer to the [current testing documentation](https://docs.spring.io/spring-batch/reference/testing.html) before changing imports or utilities.
