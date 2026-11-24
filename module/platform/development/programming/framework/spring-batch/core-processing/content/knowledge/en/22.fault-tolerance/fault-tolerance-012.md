# Testing multiple error types

In Spring Batch, a Job can encounter multiple types of errors across different phases: reading data, processing items, writing results, accessing the database, calling external services, or recovering after an application stop. Each error type may require a different handling strategy. Some errors must fail the Step immediately; transient errors should be retried; data errors may be skipped; some errors must roll back the transaction; and some errors surface only upon restart.

Testing fault tolerance must verify both sides: the application reacts properly to errors, and data remains consistent after errors. Asserting only that the Job returns `COMPLETED` or `FAILED` is insufficient. You need to inspect exceptions, retry counts, skip counts, listeners, transactions, committed data, and restart state.

## 1. Identifying the error groups to test

Before writing tests, list errors by where they originate and the expected outcome.

| Origin | Example errors | Behavior typically needing verification |
|---|---|---|
| `ItemReader` | Malformed CSV line, parse error, data source temporarily unreachable | Skip permitted data errors; retry transient errors if appropriate; stop on unrecoverable errors |
| `ItemProcessor` | Validation failure, missing reference data, timeout calling service | Skip permitted business errors; retry transient dependency errors; never skip programming bugs |
| `ItemWriter` | Constraint violation, deadlock, database unavailable | Roll back chunk when needed; retry deadlocks; skip failing write items if business rules allow |
| Transaction | Deadlock, lock timeout, commit failure | Transaction rolls back properly; retries execute in an appropriate transaction |
| External service | HTTP 429, 5xx, timeout, invalid response | Timeout, retry/backoff, error classification, and idempotency |
| Restart | Process stops after several chunks commit | Restore checkpoint; no duplicate or missing data |
| Skip policy | Skips exceed threshold, non-skippable exception | Step fails and metadata accurately reflects error counts |

Do not lump all errors into one `Exception` category. An invalid data error and a lost database connection carry very different operational meanings.

## 2. Fault tolerance testing strategy

A good test suite progresses from small components to the full Step or Job:

1. **Unit test reader/processor/writer:** verify data mapping, exceptions, and business rules.
2. **Step integration test:** run the real Step with test reader, processor, writer, and transaction manager to verify skip, retry, rollback, and counters.
3. **Job integration test:** run the entire Job to verify flow, Step statuses, and restarts.
4. **Dependency integration test:** use a test database or stub HTTP server to test communication failures, timeouts, and real transactions.
5. **Failure/restart test:** intentionally fail the Job mid-run and relaunch the same `JobInstance`.

Tests should trigger deterministic errors with pre-defined expected outcomes. Avoid relying on random failures such as dropping a real database connection or waiting for long timeouts on every test run.

## 3. Setting up Spring Batch Test

Spring Batch provides the `spring-batch-test` module with utilities to run Jobs/Steps in tests and inspect metadata.

For Spring Boot projects, add the test dependency matching your Spring Batch version. With Gradle, declare per your project's dependency management, for example:

```groovy
testImplementation("org.springframework.batch:spring-batch-test")
testImplementation("org.springframework.boot:spring-boot-starter-test")
testRuntimeOnly("com.h2database:h2")
```

If not using Spring Boot, declare compatible JUnit, Spring Test, Spring Batch Test, and test database dependencies.

Example test structure:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class ImportJobFaultToleranceTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JobRepositoryTestUtils jobRepositoryTestUtils;

    @AfterEach
    void cleanUp() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
```

`@SpringBatchTest` registers Spring Batch test support components, including `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and scope-supporting listeners. Provide the Job/Step and `JobRepository` in the test application context. Use a dedicated test database to avoid deleting or altering metadata from other environments.

`JobLauncherTestUtils` can run an entire Job or a specific Step. For example:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(jobParameters);

JobExecution stepExecution = jobLauncherTestUtils.launchStep(
        "importOrdersStep", jobParameters);
```

Check method names and overloads against your project's `spring-batch-test` version. If the test context contains multiple Jobs, explicitly configure which Job `JobLauncherTestUtils` should run.

## 4. Verifying Job and Step status

After launching, inspect the final status and `StepExecution` metadata:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertEquals(ExitStatus.COMPLETED, execution.getExitStatus());

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(10, stepExecution.getReadCount());
```

For error tests, you may expect `BatchStatus.FAILED` and inspect `ExitStatus` or recorded exceptions. Do not assert only the Job status; retrieve the specific `StepExecution` to see where the failure occurred.

Common counters to verify:

- `readCount`: number of items read by the reader.
- `writeCount`: number of items written by the writer per Step metadata.
- `filterCount`: number of items intentionally filtered by the processor returning `null`.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: skip counts per phase.
- `rollbackCount`: number of rollbacks recorded.
- `commitCount`: number of commits recorded.
- `skipCount`: total skips in the Step.

Counter meanings can be affected by retry, buffering, and reader/writer types. Combine counters with actual database records or output files to verify business outcomes.

## 5. Testing read errors

The reader can fail while parsing files, converting types, reading a database, or fetching data from an API. Separate skippable data errors from source/infrastructure errors that require stopping or retrying.

### Testing skipped file parse errors

With `FlatFileItemReader`, create a test resource containing one valid line and one malformed line. Configure the reader with strict parsing so the bad line throws `FlatFileParseException`, then configure the Step to allow skipping that exception type.

Example Step configuration:

```java
return new StepBuilder("readFileStep", jobRepository)
        .<CustomerInput, Customer>chunk(10, transactionManager)
        .reader(fileReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(2)
        .listener(skipListener)
        .build();
```

Tests must verify:

- The Step completes when the number of bad lines stays within the limit.
- `readSkipCount` increments by the number of skipped lines.
- Valid lines are still written.
- `SkipListener.onSkipInRead()` is invoked.
- The bad line does not produce a spurious item in the output.

For unrecoverable reader errors, such as a closed database connection, do not automatically skip them like parse errors. Configure retry for transient errors or let the Step fail if the source is no longer available.

### Testing a reader throwing scripted exceptions

A simulated reader helps inject errors deterministically on a specific read call:

```java
public class FailingOnceReader implements ItemReader<String> {

    private final AtomicBoolean fail = new AtomicBoolean(true);
    private int index;

    private final List<String> values = List.of("A", "B", "C");

    @Override
    public String read() {
        if (index == 1 && fail.compareAndSet(true, false)) {
            throw new TransientDataAccessResourceException(
                    "Temporary source failure");
        }

        if (index >= values.size()) {
            return null;
        }

        return values.get(index++);
    }
}
```

This is an illustrative test double; how index advances and position restores must match the behavior under test. For stateful readers, implement `ItemStream` or use a dedicated test reader to verify checkpoints accurately. Tests must prove the error is retried/skipped per policy without losing the next item.

## 6. Testing errors in ItemProcessor

Processors often raise validation errors, missing reference data errors, or service call failures. You can use a real processor with a mocked service to produce controlled exceptions.

Processor example:

```java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    private final CustomerValidationService validationService;

    public CustomerProcessor(CustomerValidationService validationService) {
        this.validationService = validationService;
    }

    @Override
    public Customer process(CustomerInput item) {
        validationService.validate(item);
        return new Customer(item.customerId(), item.name());
    }
}
```

In tests, configure the mock to throw an exception for a specific business key:

```java
doThrow(new InvalidCustomerException("Invalid customer"))
        .when(validationService)
        .validate(argThat(item -> item.customerId().equals("C-002")));
```

If `InvalidCustomerException` is configured as skippable, tests should verify:

- `processSkipCount` increments accurately.
- Item `C-002` does not appear in the output.
- Valid items before and after it are still written.
- `SkipListener.onSkipInProcess()` receives the exact item and exception.
- The Job fails only if total skips exceed the limit or an unhandled error occurs.

If the processor returns `null` for an item, that is filtering. Tests should confirm `filterCount` increases while skip count does not. Distinguishing these two cases prevents misjudging data quality.

## 7. Testing errors in ItemWriter

The writer receives a chunk of multiple items, so write errors can affect the entire group. Test at least three scenarios:

1. Writer throws an exception before writing any item.
2. Writer writes partially and then throws an exception.
3. Writer encounters a transient error on the first attempt and succeeds on retry.

Example writer simulating a single failure:

```java
public class FailingOnceWriter implements ItemWriter<Order> {

    private final AtomicBoolean fail = new AtomicBoolean(true);
    private final List<Order> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Order> chunk) {
        if (fail.compareAndSet(true, false)) {
            throw new TransientDataAccessException("Temporary write failure") {};
        }

        written.addAll(chunk.getItems());
    }

    public List<Order> getWritten() {
        return List.copyOf(written);
    }
}
```

This writer illustrates intentionally throwing an error once. An in-memory list does not roll back with database transactions, so do not use it to prove transaction atomicity. When testing real rollback, use a test database and a transaction-participating writer.

### Testing rollback when the writer writes partially

An integration test can configure a writer to insert into an H2 table and throw an exception mid-chunk. After the Step fails, query the database to confirm inserts belonging to the uncommitted transaction were rolled back.

Tests should distinguish:

- Records from previously committed chunks must remain.
- Records from the failing chunk must roll back if the exception requires rollback.
- If retry succeeds, the chunk is written strictly once.
- If skip is configured for a failing write item, only valid items are persisted per policy.

For writers using HTTP APIs, email, or the filesystem, database transactions cannot automatically roll back external side effects. Mock dependencies to verify idempotency keys or use an outbox in a separate integration test.

## 8. Testing retry and retry limits

Retry suits transient errors such as deadlocks, lock acquisition failures, or service timeouts likely to clear on their own. Tests should verify both successful retry and retry exhaustion.

Configuration example:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

A successful retry test should use a stubbed dependency that throws errors on initial calls and returns a result on a subsequent call. Mockito can be used:

```java
when(exchangeService.lookup("C-100"))
        .thenThrow(new TransientDataAccessException("Temporary") {})
        .thenReturn(new CustomerProfile("C-100", "ACTIVE"));
```

After running the Step, verify the Job completes and the dependency was retried per policy. Avoid hard-coding an exact call count in tests without verifying how your Spring Batch version counts `retryLimit`; rely on the API contract and actual configuration.

A retry-exhausted test configures the dependency to always throw an exception. Verify the Step fails, the final error is captured in metadata, and no invalid output data exists.

### Testing backoff

When using backoff, avoid making tests sleep for many seconds unnecessarily. Configure tiny intervals in tests or use a stubbed policy to verify the policy is attached to the Step. Integration tests should check attempt counts and final status; measuring real elapsed wall-clock time should be reserved for tests specifically verifying scheduler/backoff integration.

## 9. Testing skip and skip limits

For skip, include three test groups:

- Skippable exception with total skips within the limit.
- Non-skippable exception.
- Total skips exceeding the limit.

Configuration example:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
```

A test with two failing items should confirm the Step completes, `skipCount` equals 2, and valid items are written. A test with three failing items should confirm the Step fails due to exceeding the limit. Skip limit applies cumulatively across read, process, and write, so test across multiple phases in the same Step to verify the combined skip total.

A separate test should throw an exception not declared as skippable. The Step must fail immediately per policy, even if previous skip counts are still below the limit.

### Verifying SkipListener

Mock the listener or dead-letter persistence service to confirm the corresponding callbacks:

```java
verify(skipListener).onSkipInProcess(
        argThat(item -> item.customerId().equals("C-002")),
        isA(InvalidCustomerException.class));
```

For read skips, the callback receives only the exception because the reader may not have created an item yet. For write skips, the callback receives the output item. Do not use `ItemProcessListener.onProcessError()` as a substitute for verifying final skips, because an error may be retried and succeed.

## 10. Testing rollback and noRollback

`noRollback()` changes rollback classification for an exception type. This is a sensitive configuration because it can retain changes already made inside the transaction.

Example:

```java
.faultTolerant()
.skip(ValidationException.class)
.skipLimit(10)
.noRollback(ValidationException.class)
```

Tests should compare two configurations:

1. Default writer exception causes the transaction to roll back.
2. Exception declared as no-rollback is skipped per policy.

In tests, use a test database and query data after the Step finishes to confirm precisely which records committed. Specifically, build a writer capable of throwing an exception after partial writes to demonstrate that no-rollback can leave partial writes behind if misconfigured.

Use no-rollback only for exceptions thrown in situations guaranteed to have no changes needing undo, such as validating an entire chunk before the writer begins writing. Never use no-rollback for deadlocks or database connection failures.

## 11. Testing external service errors

If the processor or writer calls a REST API, test each response category:

| Response | Common handling | What to assert |
|---|---|---|
| HTTP 400/422 from invalid data | Business error; skippable if allowed | Item is skipped or Step fails per policy |
| HTTP 401/403 | Configuration/authentication error | Step fails without infinite retries |
| HTTP 429 | Respect quota/`Retry-After`, bounded retry | Call counts and backoff behave appropriately |
| HTTP 5xx | Retryable | Succeeds after retry or fails when limit exhausted |
| Connect/read timeout | Retryable if operation is safe | Timeout is enforced and retries are bounded |
| Invalid response schema | Data contract error | Classified explicitly; not treated as a transient network error |

Use an HTTP stub server or mock client to return each response. Never depend on production APIs in unit tests.

If a request triggers side effects, such as creating a transaction or submitting a payment order, tests must verify that the exact same idempotency key is sent across retries. A timeout does not prove the server did not execute the operation; the server may have committed while the response was lost.

## 12. Testing restart after failure

Restart is one of the most important fault-tolerance tests. Simulate a scenario where several chunks commit, a subsequent chunk fails, and the Job is relaunched with the exact same identifying `JobParameters`.

A typical scenario:

```text
Initial run:
  Chunk 1 -> commit
  Chunk 2 -> commit
  Chunk 3 -> exception -> rollback
  Job -> FAILED

Restart same JobInstance:
  Restore saved checkpoint
  Chunks 1 and 2 are not re-written
  Continue unfinished work
  Job -> COMPLETED
```

For reliable restart tests:

1. Use a reader supporting `ItemStream` and `saveState`.
2. Use a persistent `JobRepository` across both launches.
3. Use identical identifying `JobParameters` for the restart.
4. Inject an intentional error in a chunk after prior chunks have committed.
5. Verify the first run is `FAILED` and data from committed chunks remains present.
6. Relaunch the `JobInstance` and verify the Step resumes from the checkpoint.
7. Verify final results have no missing or duplicate items.

Example test skeleton:

```java
@Test
void restartsFailedJobFromSavedCheckpoint() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputVersion", "fixture-v1")
            .toJobParameters();

    JobExecution first = jobLauncherTestUtils.launchJob(parameters);
    assertEquals(BatchStatus.FAILED, first.getStatus());

    JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
    assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

    assertEquals(expectedIds, outputRepository.findAllIds());
}
```

This example assumes the test fixture fails exactly once and preserves `JobRepository`, input, and output database between launches. Do not generate a new identifying parameter for the restart; adding a fresh timestamp or UUID causes Spring Batch to create a different `JobInstance` and run as a brand-new job.

## 13. Testing multiple errors in the same Job

A real Job can encounter errors across multiple phases. You can build a test matrix to verify each error type and outcome:

| Scenario | Configuration | Expected outcome |
|---|---|---|
| Malformed file line | Skip parse exception, within limit | Bad line skipped; valid lines written |
| Item validation fails | Skip validation exception | Process skip count increments; listener records item |
| One-time database deadlock | Retry deadlock exception | Transaction retried; chunk commits on success |
| Persistent database failure | Bounded retry | Step fails after retries exhausted |
| Failing items exceed skip limit | Skip policy and small limit | Step fails when threshold exceeded |
| Writer throws after partial write | Default rollback | No partial writes remain in rolled-back transaction |
| Writer validation with no-rollback | Specific skip + noRollback | Item handled per policy; verify no unintended changes |
| App stops after chunk commit | Reader saves checkpoint | Restart continues without duplicate writes |
| External service times out after server processed | Idempotency key | Retry creates no duplicate side effects |

You do not have to cram every error into a single test. Small scenario-focused tests make failure causes easier to diagnose. Afterward, add a few end-to-end integration tests to verify how policies interact together.

## 14. Using test doubles for controlled fault injection

Commonly used techniques:

- **Mockito:** configure mocks to throw exceptions on the first call, return a result afterward, or always fail.
- **Fault-injecting reader/processor/writer:** custom test components that throw errors on a chosen item or invocation.
- **Test database:** trigger constraint violations, lock conflicts, or transaction rollbacks on a test database.
- **HTTP stub server:** simulate 429, 5xx, timeouts, and malformed responses.
- **Barriers/latches:** synchronize threads in concurrency tests to reproduce contention deterministically.

Fault injection points should be driven by explicit test fixtures or business keys. Avoid relying on long `Thread.sleep()` calls or random probabilities, as tests become slow and flaky.

## 15. Testing listeners and metadata

Listeners are also part of fault tolerance and must be tested:

- `SkipListener` records items only when they are actually skipped.
- `RetryListener` or retry observability records accurate attempts if used by the application.
- `ChunkListener.afterChunk()` reflects only successfully committed chunks; `afterChunkError()` reflects chunk rollbacks.
- `StepExecutionListener.afterStep()` records the final Step outcome.
- Read/write/filter/skip/rollback counters accurately match the scenario.

If a listener writes audit records to a database, check transaction boundaries. An audit record in the same transaction can roll back with the chunk; an HTTP or message broker call does not automatically join the database transaction.

Avoid asserting log text via brittle full-string matching when unnecessary. Prefer verifying callbacks, metadata, and persisted audit records.

## 16. Testing concurrency and race conditions

If a Step uses multi-threading, partitioning, or split flows, verify:

- Shared processors, writers, listeners, and services are thread-safe.
- Partitions have non-overlapping data ranges.
- Writers do not create duplicates on retry or rerun.
- Skip counters and audit records are not overwritten.
- Connection pools and executors have adequate resource limits.
- When one worker fails, other workers and the Job finish in the expected state.

Concurrency tests should coordinate ordering via latches/barriers rather than relying on scheduler timing. When testing deadlocks, the test database should support locking/isolation close to the production environment; H2 does not simulate all locking behaviors of PostgreSQL, MySQL, Oracle, or SQL Server.

## 17. Testing retry performance and stability

Fault tolerance can make Jobs run longer due to retries, backoff, and skip isolation. For large Jobs, measure:

- Total Job duration and per-Step duration.
- Retry counts per item/chunk.
- Total backoff wait time.
- Skip rate per phase.
- Transaction duration, rollback count, and lock waits.
- Throughput without errors vs. under controlled error rates.
- Restart recovery time after failure.

Performance tests should use representative data and an environment configured close to production. Do not use unit tests to claim real throughput. You can create a workload with a controlled error rate to measure the impact of retry and skip.

## 18. Common mistakes when testing fault tolerance

**Asserting only JobStatus:** A Job may end `COMPLETED` while skipping many items. Inspect counters and output data.

**Mocking exceptions without running the Step:** Unit tests verify processor logic, but cannot test Spring Batch rollback, skip limits, listeners, or metadata.

**Using a mock writer to conclude transaction rollback:** In-memory collections do not roll back with database transactions. Use a test database to verify commit/rollback.

**Creating new JobParameters when testing restart:** The Job can become a new `JobInstance` and fail to test restarting the old instance.

**Not preserving JobRepository across both launches:** Metadata and checkpoints are not restored as in production.

**Using `sleep()` to test retry/backoff:** Tests easily become slow and flaky. Use controllable policies/test doubles.

**Not testing exceeding skip limit:** Skip configurations may permit more errors than intended without detection.

**Not checking writer partial writes:** Incorrect no-rollback or retry can leave incomplete data behind.

**Assuming HTTP rolls back with the database:** External side effects need idempotency or an outbox; database rollback does not undo requests already processed by another system.

**Using H2 alone to draw conclusions about production deadlocks:** Locking behavior and `SQLState` depend on the database and driver. Run integration tests against the target database when correctness relies on locking.

## Conclusion

Testing multiple error types in Spring Batch must cover the reader, processor, writer, transactions, external services, and restarts. Use `spring-batch-test` to run real Jobs/Steps and inspect `BatchStatus`, `ExitStatus`, counters, listeners, and committed data. Inject deterministic errors using test doubles, mocked services, HTTP stubs, and test databases; separately verify successful retry, retry exhaustion, skips within limit, exceeding skip limit, non-skippable exceptions, rollback, and no-rollback. For restarts, preserve `JobRepository` and identifying `JobParameters`, verifying checkpoints and outputs with zero duplicate or missing items. A strong test suite proves not only that the Job reacts properly to errors, but also that data and state afterward still satisfy business requirements.
