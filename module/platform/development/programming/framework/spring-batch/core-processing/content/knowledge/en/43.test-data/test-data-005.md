# Faulty Data for Retry Testing in Spring Batch

When testing a batch job, valid input data only shows that the normal processing flow can complete. A batch processing system must also cope with transient failures: a downstream service briefly drops connections, the database rejects a transaction due to deadlock, a write operation times out, or an API call returns a recoverable error. To verify that a **retry** configuration works properly, tests must produce **controlled faults**, track attempt counts, and assert outcomes both after recovery and after exhausting the retry limit.

Within the **Spring Batch Core Processing** module, this article focuses on **designing faulty data for retry testing**: selecting failure scenarios, organizing fixtures, simulating failures by attempt count, running a chunk step with a retry policy, and writing deterministic assertions. Examples use Spring Batch 5.x, Spring Boot 3.x, Java 17, and JUnit 5.

## 1. Faulty data for retry differs from ordinary bad data

The first decision to make is: **can retrying the same item succeed?**

| Failure category | Sample scenario | After retrying | How to test |
| --- | --- | --- | --- |
| Transient error | Service call returns `503`, brief deadlock, flaky DB connection | Can succeed once external condition recovers | Fail for the first N attempts, then succeed |
| Prolonged transient error | Service remains unavailable across multiple attempts | Exhausts retry limit | Fail continuously, verify step/job fails or enters configured skip/recovery branch |
| Unrecoverable data error (*permanent*) | Invalid date, missing required code, business rule violation | Retrying the same data still fails | Verify error is not retried unless a data-correction policy exists |
| Error outside retryable set | An exception not registered for retry | Should not retry under current policy | Verify only one processing attempt and expected failure/skip status |
| Write failure | Timeout or deadlock in `ItemWriter` | May succeed on retry | Verify writer invocation count **and** zero duplicate output |

**A malformed CSV record does not automatically make a meaningful retry test.** If reading the same record ten times yields the exact same error, that is usually a validate/skip/fail case. Testing retry requires a fault source capable of changing state across attempts, such as an API stub that fails twice and succeeds on the third attempt.

Also distinguish three related but distinct concepts:

- **Retry:** re-attempting a failed operation during processing, potentially accompanied by a chunk transaction rollback.
- **Skip:** bypassing a faulty item under a skip policy and continuing with other data while within the skip limit.
- **Restart:** re-launching a failed or stopped `JobInstance`; the rerun is a separate `JobExecution` tied to persisted metadata and checkpoints.

A job can configure both retry and skip. When an error persists after retries are exhausted, the framework can fall back to skipping if that exception type is skippable. Hence, expecting **`FAILED` or `COMPLETED`** in a test depends on the combined retry, skip, and transaction configuration, not on the input alone.

## 2. Building scenario-based test datasets

A useful dataset must describe **which item fails, where it fails, for how many attempts, which exception is thrown, and the expected outcome**. You can draft a matrix before implementing fixtures:

| Test ID | Item | Failure stage | Fault rule | Assumed policy | Expectation |
| --- | --- | --- | --- | --- | --- |
| `OK` | `order-001` | None | 0 failures | Retry 3 attempts | `COMPLETED`, processed 1 time |
| `TEMP_ONCE` | `order-002` | Processor | Transient error on attempt 1; succeeds on 2 | Retry transient exception, max 3 attempts | `COMPLETED`, processed 2 times |
| `TEMP_TWICE` | `order-003` | Processor | Fails first 2 times; succeeds on 3 | Max 3 attempts | `COMPLETED`, processed 3 times |
| `TEMP_EXHAUSTED` | `order-004` | Processor | Always throws transient error | Max 3 attempts, no skip | `FAILED`, processed 3 times |
| `PERMANENT` | `order-005` | Processor | Validation error on first attempt | Do not retry this error, no skip | `FAILED`, processed 1 time |
| `WRITE_ONCE` | `order-006` | Writer | Writer fails first attempt, then writes | Retry write error, max 3 attempts | `COMPLETED`, output has exactly 1 item |

> In this article, **`retryLimit(3)` means at most three attempts, including the initial try**. Thus, an item that fails twice and succeeds has three processing calls; an item failing continuously hits the limit on the third attempt. Do not take a configuration value and add an extra attempt when computing expected results.

Business data and fault plans can be kept in two separate sources:

```text
src/test/resources/
└── fixtures/
    └── retry/
        ├── orders.csv
        └── fault-plan.csv
```

Contents of `orders.csv`:

```csv
order_id,customer_id,amount
order-001,c-01,100.00
order-002,c-02,250.00
order-003,c-03,180.00
order-004,c-04,420.00
order-005,c-05,0.00
order-006,c-06,310.00
```

Contents of `fault-plan.csv`, read only by tests to drive stubs or test doubles:

```csv
case_id,order_id,stage,exception_kind,fail_first_attempts
OK,order-001,PROCESS,NONE,0
TEMP_ONCE,order-002,PROCESS,TRANSIENT,1
TEMP_TWICE,order-003,PROCESS,TRANSIENT,2
TEMP_EXHAUSTED,order-004,PROCESS,TRANSIENT,999
PERMANENT,order-005,PROCESS,VALIDATION,1
WRITE_ONCE,order-006,WRITE,TRANSIENT,1
```

`fail_first_attempts=999` represents a persistent failure in a test with a small retry budget, not a request for the real program to retry 999 times. For `PERMANENT`, `amount=0.00` is merely an example value that may violate a business rule; the validation exception must come from the corresponding logic or test double.

**Do not put `case_id`, `exception_kind`, or `fail_first_attempts` into production domain models just to make real code throw errors.** Those columns belong to the *test scenario*. In tests, load them into a `FaultPlan` and use a stub/mock/test processor to inject faults per `order_id`. That way, the same input record can test both happy and failure paths without distorting business data.

## 3. Configuring a chunk step with retry

In Spring Batch 5, a chunk-oriented step configures retry using `faultTolerant()`, `retry(...)`, and `retryLimit(...)`. Example:

```java
@Bean
Step importOrderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrderStep", jobRepository)
            .<Order, Order>chunk(10, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TemporaryProcessingException.class)
            .retryLimit(3)
            .build();
}
```

This is an illustrative configuration: `Order`, `TemporaryProcessingException`, reader, processor, and writer must be defined in the corresponding application.

In this example:

1. Each chunk contains up to 10 items.
2. `TemporaryProcessingException` is retryable.
3. Total attempts for a failing operation are capped at three.
4. No `skip(...)` is configured, so an unresolved error once retries are exhausted fails the step.

When an exception is thrown in the processor or writer, the framework can roll back the chunk transaction and replay part of the pipeline. Do not assume `read()`, `process()`, and `write()` invocation counts must be equal in every situation: reader buffering, failure position, reader transactionality, and rollbacks all affect call counts.

To illustrate a test that **precisely counts processor attempts**, the next section uses a chunk size of 1, a single item, and an in-memory fault-injecting processor. This is a small, deterministic fixture dedicated to testing.

## 4. Using a programmable fault injector in tests

A fault injector should have four properties:

- Configurable target item and number of initial failures.
- Throws the exact exception type classified by the retry policy.
- Records how many times each item was processed so tests can assert it.
- Resets state before each test; attempt-counting state must survive rollback to simulate an external service recovering.

The example below lives in the test package and uses Java 17 `record`s. It has no real-time dependency, makes no network calls, and avoids `Thread.sleep()`:

```java
package com.example.batch;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.ItemProcessor;

record TestOrder(String id, BigDecimal amount) {}

class TemporaryProcessingException extends RuntimeException {
    TemporaryProcessingException(String message) {
        super(message);
    }
}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}

class FaultInjectingProcessor
        implements ItemProcessor<TestOrder, TestOrder> {

    private record Rule(int failFirstAttempts, boolean transientError) {}

    private final ConcurrentMap<String, Rule> rules =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    void reset() {
        rules.clear();
        attempts.clear();
    }

    void failFirst(String orderId, int failures, boolean transientError) {
        if (failures < 0) {
            throw new IllegalArgumentException("failures must be >= 0");
        }
        rules.put(orderId, new Rule(failures, transientError));
    }

    int attemptCount(String orderId) {
        AtomicInteger counter = attempts.get(orderId);
        return counter == null ? 0 : counter.get();
    }

    @Override
    public TestOrder process(TestOrder item) {
        int current = attempts.computeIfAbsent(
                item.id(), ignored -> new AtomicInteger()
        ).incrementAndGet();

        Rule rule = rules.get(item.id());
        if (rule != null && current <= rule.failFirstAttempts()) {
            if (rule.transientError()) {
                throw new TemporaryProcessingException(
                        "Simulated outage for " + item.id()
                        + ", attempt " + current
                );
            }
            throw new InvalidOrderException(
                    "Invalid order " + item.id()
            );
        }
        return item;
    }
}
```

Usage:

```java
faults.failFirst("order-003", 2, true);
// process(order-003) attempt 1 -> TemporaryProcessingException
// process(order-003) attempt 2 -> TemporaryProcessingException
// process(order-003) attempt 3 -> returns valid item

faults.failFirst("order-005", 1, false);
// process(order-005) attempt 1 -> InvalidOrderException
// If policy does not retry this type, there is only one attempt.
```

The `attempts` map here lives in test memory, **outside the item-processing transaction**. If you used a database row subject to transaction rollback to count failures, rolling back would erase traces of previous attempts, and the "fail twice then succeed" fixture would not work as expected. In integration tests against real services, you can use WireMock or a stateful HTTP stub that counts requests similarly.

## 5. Self-contained test job example

To focus on test data and retry, we build a test job reading just **one order** from `JobParameters`. The writer stores received items in memory. This is sufficient to verify processor errors; it must not be used to prove writer rollback against a real database.

File `src/test/java/com/example/batch/RetryFixtureJobConfig.java`:

```java
package com.example.batch;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class RetryFixtureJobConfig {

    @Bean
    FaultInjectingProcessor faultInjectingProcessor() {
        return new FaultInjectingProcessor();
    }

    static class RecordingWriter implements ItemWriter<TestOrder> {
        private final List<TestOrder> written =
                new CopyOnWriteArrayList<>();

        @Override
        public void write(Chunk<? extends TestOrder> chunk) {
            written.addAll(chunk.getItems());
        }

        void clear() {
            written.clear();
        }

        List<String> writtenIds() {
            return written.stream().map(TestOrder::id).toList();
        }
    }

    @Bean
    RecordingWriter recordingWriter() {
        return new RecordingWriter();
    }

    @Bean
    @StepScope
    ItemReader<TestOrder> testOrderReader(
            @Value("#{jobParameters['orderId']}") String orderId) {
        return new ListItemReader<>(List.of(
                new TestOrder(orderId, new BigDecimal("100.00"))
        ));
    }

    @Bean
    Step retryFixtureStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("testOrderReader") ItemReader<TestOrder> reader,
            FaultInjectingProcessor processor,
            RecordingWriter writer) {
        return new StepBuilder("retryFixtureStep", jobRepository)
                .<TestOrder, TestOrder>chunk(1, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TemporaryProcessingException.class)
                .retryLimit(3)
                .build();
    }

    @Bean
    Job retryFixtureJob(
            JobRepository jobRepository,
            @Qualifier("retryFixtureStep") Step step) {
        return new JobBuilder("retryFixtureJob", jobRepository)
                .start(step)
                .build();
    }
}
```

In the configuration above:

- `@StepScope` allows `testOrderReader` to receive `orderId` when the step runs. This value comes from the parameters of **that specific test run**.
- `FaultInjectingProcessor` lives in the test context so tests can configure fault rules before launching and read attempt counts afterward.
- `RecordingWriter` only records when the processor returns successfully. If the processor always throws, the recorded list must remain empty.
- `retry(TemporaryProcessingException.class)` selects only the transient exception family. `InvalidOrderException` is excluded from retry.
- `chunk(1, ...)` isolates a single item and makes results easy to observe. With larger chunks or multi-threading, not every simple call-count assumption in this example holds.

## 6. Writing JUnit tests to verify retry data

Basic test dependencies in a Spring Boot project using Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

The following integration test loads a compact Spring Boot test context, uses H2 for Spring Batch metadata tables, and explicitly runs the job via `JobLauncherTestUtils`. File `src/test/java/com/example/batch/RetryDataIntegrationTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

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
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBatchTest
@SpringBootTest(
        classes = RetryDataIntegrationTest.TestApp.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always",
                "spring.datasource.url=jdbc:h2:mem:retry_cases;DB_CLOSE_DELAY=-1"
        }
)
class RetryDataIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RetryFixtureJobConfig.class)
    static class TestApp {}

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private FaultInjectingProcessor faults;

    @Autowired
    private RetryFixtureJobConfig.RecordingWriter writer;

    @Autowired
    @Qualifier("retryFixtureJob")
    private Job job;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);

        // Only delete metadata in the dedicated H2 test database.
        repositoryTestUtils.removeJobExecutions();
        faults.reset();
        writer.clear();
    }

    private JobParameters params(String orderId) {
        return new JobParametersBuilder()
                .addString("orderId", orderId)
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();
    }

    @Test
    void succeedsImmediatelyWhenInputHasNoFailure() throws Exception {
        JobExecution execution = launcher.launchJob(params("order-001"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(faults.attemptCount("order-001")).isEqualTo(1);
        assertThat(writer.writtenIds()).containsExactly("order-001");
    }

    @Test
    void succeedsAfterTwoTransientFailures() throws Exception {
        faults.failFirst("order-003", 2, true);

        JobExecution execution = launcher.launchJob(params("order-003"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(faults.attemptCount("order-003")).isEqualTo(3);
        assertThat(writer.writtenIds()).containsExactly("order-003");
    }

    @Test
    void failsWhenTransientErrorExhaustsRetryLimit() throws Exception {
        faults.failFirst("order-004", 999, true);

        JobExecution execution = launcher.launchJob(params("order-004"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);
        assertThat(faults.attemptCount("order-004")).isEqualTo(3);
        assertThat(writer.writtenIds()).isEmpty();
    }

    @Test
    void doesNotRetryPermanentError() throws Exception {
        faults.failFirst("order-005", 1, false);

        JobExecution execution = launcher.launchJob(params("order-005"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);
        assertThat(faults.attemptCount("order-005")).isEqualTo(1);
        assertThat(writer.writtenIds()).isEmpty();
    }
}
```

`@SpringBatchTest` supplies utilities for launching jobs and managing test metadata. `spring.batch.job.enabled=false` keeps the job from auto-running when the context initializes. The H2 setup here is for the test environment: real databases can use migration scripts or Testcontainers to create `BATCH_*` tables instead of auto-initializing schemas.

The `params()` method generates a new `run.id` so each test runs an independent `JobInstance`. When **testing restart on the same instance**, keep identifying parameters unchanged instead of swapping `run.id`; that is a distinct scenario from intra-execution retry.

These checks deliberately observe **three dimensions**: the job's `BatchStatus`, how many times the processor was called, and which items the writer received. Asserting `COMPLETED` alone cannot tell "succeeded after retry" apart from "never failed in the first place".

## 7. Faulty data at Reader, Processor, and Writer

Where the fault occurs determines how data is prepared and what must be verified:

### 7.1. Read failures

A file containing a bad date like `2026-99-99` usually fails parsing deterministically. Using it to test validation or skip makes more sense than expecting retry to fix the data. To test *transient* read errors, simulate an API/database source timing out on the first read and then returning valid records. In that case, verify that no items are dropped or double-read after transaction rollback.

Example fixed faulty-data fixture:

```csv
order_id,created_at,amount
order-bad-01,2026-99-99,100.00
order-bad-02,,200.00
```

This group should be tested with dedicated parse/validation expectations. If project policy still retries certain reader exceptions, prove that the transient condition genuinely changes between attempts.

### 7.2. Processing failures

The processor is a convenient place to inject controlled faults. You can force a specific item to throw `TemporaryProcessingException` for the first N attempts and return a result on the next attempt. Without skip and with one item, `COMPLETED`/`FAILED` transitions are easy to observe as in the JUnit example.

For processors with real business logic, wrap the **external dependency** with a stub (such as a payment gateway or exchange-rate service) so the test still exercises the real processor. Swapping the entire processor with a test double fits best when the explicit goal is verifying **the step's retry mechanism**.

### 7.3. Write failures

Write failures also require testing **idempotency**. A service might receive a request while the client times out before getting the response: retrying resends the same request, causing duplicate writes if the receiver lacks an idempotency key.

A writer test suite should include at least:

| Scenario | Simulated fault | What to verify |
| --- | --- | --- |
| First-attempt write success | None | Exact row/record count in target |
| Transient write error then success | Timeout/deadlock on first try | Retry succeeds, target record count remains exact |
| Uncertain commit outcome | Server accepted request but client timed out | Re-sending creates no duplicate business effect |
| Persistent write failure | Exception on every attempt | Job fails/skips per policy, committed data is not left half-written |

With a JDBC writer sharing the step's transaction manager and datasource, rollback normally undoes uncommitted chunk SQL operations. With APIs, message brokers, or filesystems, database rollback **cannot automatically undo** external side effects. In tests, use data with business keys (`order_id`) and assert that each key was written or processed exactly once as required, rather than merely counting requests.

The in-memory `RecordingWriter` above does not participate in transactions; it works for faults **before the writer runs**, but cannot replace rollback/idempotency tests of a real writer.

## 8. Structuring test data so results do not depend on execution order

Retry tests can cross-contaminate easily because they involve both **`JobRepository` history** and attempt-counting state in stubs/mocks:

1. Use clear case names, item IDs, and expected outcomes; load only the items needed for each test. Mixing `PERMANENT` and `TEMP_ONCE` items in the same job can stop the job before reaching the item you meant to observe.
2. Reset fault-injector counters and target data before each test; never hold shared counters in unreset `static` fields.
3. Use a dedicated database/schema for integration tests. `JobRepositoryTestUtils.removeJobExecutions()` **deletes execution metadata**, so use it only on an isolated test repository, never on a database shared with another environment or suite.
4. For independent tests, use distinct identifying `JobParameters`. For restart tests, intentionally keep metadata from the `FAILED` run and reuse the same identifying parameters.
5. When running tests in parallel, provide isolated contexts/databases/fault state or proper synchronization. Sharing one singleton `FaultInjectingProcessor` across parallel tests corrupts attempt counts.
6. Avoid `Thread.sleep()` or real network delays to trigger a "one-time error". Stateful stubs with fixed attempt thresholds fail deterministically and reproduce cleanly on CI.

If a job configures a `backOffPolicy` with long delays, define a test configuration with very short or zero delay so tests do not drag out. Dedicated tests for the backoff mechanism itself, however, should keep controlled timing measurements and appropriate tolerances.

## 9. How to read results when a test fails

Spring Batch exposes `JobExecution`, `StepExecution`s, `ExitStatus`, and exceptions to inspect runs. Example:

```java
JobExecution execution = launcher.launchJob(params("order-004"));

System.out.println("Job status = " + execution.getStatus());
System.out.println("Exit status = " + execution.getExitStatus());

execution.getStepExecutions().forEach(step -> {
    System.out.println("Step = " + step.getStepName());
    System.out.println("Read = " + step.getReadCount());
    System.out.println("Write = " + step.getWriteCount());
    System.out.println("Rollback = " + step.getRollbackCount());
    System.out.println("Skip = " + step.getSkipCount());
});

execution.getAllFailureExceptions()
        .forEach(Throwable::printStackTrace);
```

To diagnose **actual retry counts**, inspect `faults.attemptCount(orderId)` in this example because that counter sits right at the fault injection point. `StepExecution.getReadCount()` or `getProcessSkipCount()` cannot directly stand in for attempt counts: they mean different things and are affected by commits/rollbacks, skips, and chunks.

If the job uses a `RetryListener`, it can record each retry attempt and exception so tests identify the exact exception type; avoid inferring attempt counts from generic job log lines. Additionally, HTTP/JDBC exceptions are sometimes wrapped by the framework or an application layer: retry policies must match the **actual exception type visible at the step boundary**, not just the message printed in logs.

## 10. Extension exercises

Building on the fixtures and integration test above, extend them in this order:

1. Add case `TEMP_ONCE` for `order-002`, failing once before succeeding; verify `attemptCount=2` and exactly one written item.
2. Try `retryLimit(2)` with a case that fails twice and succeeds on the third attempt. Observe why the step fails before the expected success; adjust expected attempts accordingly.
3. Add a `.skip(InvalidOrderException.class).skipLimit(1)` branch and verify how the outcome differs from the failing `PERMANENT` case. With one invalid item skipped, the step can end `COMPLETED` with a skip count of 1.
4. Replace the test processor with a real business processor backed by an API stub returning `503` twice and then `200`. Assert both business output and stub request count.
5. Test a writer against a test database with a unique constraint on `order_id`, simulating a transient error on the first write; verify after the job finishes that only one record exists without duplicate writes.
6. Produce a `FAILED` job run and **restart it with the same identifying parameters**, observing reader/step checkpoints and distinguishing restart behavior from intra-execution retry.

The essence of designing **faulty data for retry** is turning unpredictable failures into reproducible rules: **which item fails, in which operation, what kind of error, for how many attempts, and what final state the data must reach**. That enables Spring Batch tests to prove both that retry triggers when appropriate and that the system stops within limits without corrupting data.
