# Testing skip allowed and skip limit exceeded

In Spring Batch, `skip` lets a step continue processing when it encounters specific errors defined as skippable. For example, a malformed CSV line or a record violating a business rule can be skipped if business rules permit continuing with the remaining records.

`skipLimit` sets the limit on the total number of items allowed to be skipped in one step execution. When the skip count exceeds the limit, the step fails with `SkipLimitExceededException`. Therefore, two boundary cases must be explicitly tested:

- **Skip allowed:** the number of skipped items does not exceed the limit; the step can complete if the remaining processing succeeds.
- **Skip limit exceeded:** the number of items needing skipping exceeds the limit; the step must fail and not continue as if data were processed normally.

With `skipLimit(10)`, at most 10 skips are accepted. The 11th skip exceeds the limit. This limit applies cumulatively across read, process, and write skips in the step, not 10 times for each stage separately.

Tests must verify `StepExecution` status, `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount`, items written, and failure causes. Simply asserting that the job completed or failed is insufficient to prove the skip policy works properly.

## Skip and skipLimit in chunk processing

In a chunk-oriented step, data passes through three stages: reader, processor, and writer. Exceptions can arise at any stage.

| Stage | Skippable error example | Corresponding counter |
| --- | --- | --- |
| Read | Unparseable file line, malformed source record | `readSkipCount` |
| Process | Invalid business data, item cannot be transformed | `processSkipCount` |
| Write | An item violates a constraint or throws a write error classified as skippable | `writeSkipCount` |

Spring Batch tracks these skip types in `StepExecution`. `skipCount` is the total number of skips across stages. `skipLimit` applies to this step-wide total, not a separate quota per exception type or per chunk.

For example, if a step has `skipLimit(5)` and has already had 2 read skips and 2 process skips, only one skip remains allowed. One more write skip pushes the total past the limit and the step fails.

### Configuring the skip policy

With Spring Batch 5, you can configure skip directly on the step builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

In this example, the step allows skipping up to 10 exceptions of type `InvalidOrderException` under Spring Batch's skip rules. If an 11th skip occurs, the step fails due to exceeding the limit.

`faultTolerant()` enables fault-tolerant configuration for the chunk step, allowing skip/retry declarations. Only declare exception types that are genuinely skippable. Do not broadly use `.skip(Exception.class)` if infrastructure errors such as database disconnection or configuration errors must not be ignored.

### SkipLimit of 0

If `skipLimit` is not configured, the default value is usually 0. In that case, an exception declared with skip still allows zero skips; the first occurrence exceeds the limit and fails the step.

```java
.faultTolerant()
.skip(InvalidOrderException.class)
// No skipLimit set: defaults to 0
```

Declaring `.skip(...)` defines which error types can be classified as skippable, whereas `skipLimit` defines the maximum permitted count. Both conditions must be satisfied.

## How is the threshold calculated?

Suppose `skipLimit` is 3:

| Accumulated skips | Outcome |
| ---: | --- |
| 0 | Step continues normally |
| 1 | Allowed |
| 2 | Allowed |
| 3 | Allowed; limit reached but not exceeded |
| 4 | Limit exceeded; step fails |

Remember that **equal to the limit is still allowed**. The step only fails when the skip count exceeds the limit. With a limit of 0, the very first skip exceeds the limit.

The limit accumulates within the scope of a step execution across the step's chunks. A new chunk does not reset the skip counter to 0. If the step is restarted, the new execution has metadata and counters following Spring Batch's restart lifecycle; do not assume a restart is a simple arithmetic continuation of the old counter. Inspect each `StepExecution` and execution history when analyzing restarts.

## Testing the two boundary cases

A useful test needs to run the same step configuration with two different datasets:

1. A dataset with the exact number of failing items equal to `skipLimit`: the step must be allowed to complete.
2. A dataset with one more failing item than `skipLimit`: the step must fail.

Example setting `skipLimit(2)`:

```text
Case A: at the limit
Input:  valid-1, invalid-1, valid-2, invalid-2, valid-3
Skip:   2
Output: valid-1, valid-2, valid-3
Result: COMPLETED

Case B: over the limit
Input:  valid-1, invalid-1, invalid-2, invalid-3, valid-2
Skip:   3 needed
Limit:  2
Result: FAILED when the 3rd skip occurs
```

Set a large enough chunk size in the illustrative test so items land in one chunk to focus on the skip boundary. For production-like tests, also test errors spread across multiple chunks to confirm counters accumulate across the entire step.

## Designing fixtures for tests

For reproducible tests, input data should clearly distinguish valid items and exception-raising items. Do not rely on shared files or databases without controlling state.

Example input and output models:

```java
public record OrderInput(String orderId, boolean invalid) {
}

public record Order(String orderId) {
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Processor throwing an exception for invalid items:

```java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.invalid()) {
            throw new InvalidOrderException(
                    "Invalid order: " + input.orderId());
        }
        return new Order(input.orderId());
    }
}
```

In tests, you can use `ListItemReader` to supply deterministic data. The test writer can be a simple writer or one writing to a test database. For integration tests, use the test context's real `JobRepository` so counters and statuses are persisted just like in production runs.

## Step configuration used in integration tests

The example below selects a dataset based on the `scenario` job parameter. The reader is declared `@StepScope` to receive the run's parameter.

```java
@Bean
@StepScope
ItemReader<OrderInput> orderTestReader(
        @Value("#{jobParameters['scenario']}") String scenario) {

    List<OrderInput> items = switch (scenario) {
        case "at-limit" -> List.of(
                new OrderInput("O-1", false),
                new OrderInput("O-2", true),
                new OrderInput("O-3", false),
                new OrderInput("O-4", true),
                new OrderInput("O-5", false));
        case "over-limit" -> List.of(
                new OrderInput("O-1", false),
                new OrderInput("O-2", true),
                new OrderInput("O-3", true),
                new OrderInput("O-4", true),
                new OrderInput("O-5", false));
        default -> throw new IllegalArgumentException(
                "Unknown scenario: " + scenario);
    };

    return new ListItemReader<>(items);
}
```

Declaring processor, writer, and step:

```java
@Bean
ItemProcessor<OrderInput, Order> orderTestProcessor() {
    return new OrderProcessor();
}

@Bean
ItemWriter<Order> orderTestWriter() {
    return chunk -> {
        // Test writer: writes are verified via writeCount.
    };
}

@Bean
Step skipLimitTestStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderTestReader,
        ItemProcessor<OrderInput, Order> orderTestProcessor,
        ItemWriter<Order> orderTestWriter) {

    return new StepBuilder("skipLimitTestStep", jobRepository)
            .<OrderInput, Order>chunk(10, transactionManager)
            .reader(orderTestReader)
            .processor(orderTestProcessor)
            .writer(orderTestWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(2)
            .build();
}
```

Chunk size is 10 so the entire five-item fixture is processed in one chunk. The writer does not need to persist real business data in this example; `StepExecution.writeCount` verifies how many outputs were passed to the writer. In real projects, replace the writer with a test writer writing to a temporary table to assert exact contents.

Putting the step into a test job:

```java
@Bean
Job skipLimitTestJob(
        JobRepository jobRepository,
        Step skipLimitTestStep) {

    return new JobBuilder("skipLimitTestJob", jobRepository)
            .start(skipLimitTestStep)
            .build();
}
```

## Testing skip exactly equal to the limit

With `skipLimit(2)`, the `at-limit` fixture has two items causing `InvalidOrderException` and three valid items. The step must complete because total skips equal the limit without exceeding it.

Example using `@SpringBatchTest` and `JobLauncherTestUtils`:

```java
@SpringBootTest
@SpringBatchTest
class SkipLimitIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("skipLimitTestJob")
    private Job skipLimitTestJob;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(skipLimitTestJob);
    }

    @Test
    void completesWhenSkipCountEqualsLimit() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("scenario", "at-limit", true)
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "skipLimitTestStep", parameters);

        StepExecution stepExecution = execution.getStepExecutions()
                .stream()
                .filter(step -> step.getStepName()
                        .equals("skipLimitTestStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(2, stepExecution.getProcessSkipCount());
        assertEquals(2, stepExecution.getSkipCount());
        assertEquals(3, stepExecution.getWriteCount());
        assertEquals(5, stepExecution.getReadCount());
    }
}
```

These assertions verify:

- The step completed successfully.
- Two processor errors were skipped.
- Total skips equal 2, matching `skipLimit`.
- Three valid outputs were delivered to the writer.
- The reader read all five items.

If the application skips across multiple stages, do not assert only `processSkipCount`; check `skipCount` as well as per-stage counters.

## Testing exceeding the limit

The `over-limit` fixture has three failing items while the step permits only two skips. When the third error is classified as a skip, total skips exceed the limit and Spring Batch throws `SkipLimitExceededException`; the step must finish in `FAILED` status.

```java
@Test
void failsWhenSkipCountExceedsLimit() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("scenario", "over-limit", true)
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "skipLimitTestStep", parameters);

    StepExecution stepExecution = execution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName()
                    .equals("skipLimitTestStep"))
            .findFirst()
            .orElseThrow();

    assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
    assertTrue(stepExecution.getFailureExceptions().stream()
            .anyMatch(SkipLimitExceededException.class::isInstance));
}
```

Do not rely on a fixed `writeCount` value in an over-limit test if chunk size or item ordering changes. When the limit is exceeded while processing the current chunk, that chunk may roll back before the writer is called; earlier committed chunks may retain their outputs. What matters is verifying the step failed with `SkipLimitExceededException` and checking the actual counters.

If the exception is wrapped by another exception in your version or application integration layer, the test can walk the cause chain looking for `SkipLimitExceededException`. Inspect `failureExceptions` and step logs instead of matching only message strings.

## Testing with JobExplorer

`JobLauncherTestUtils` returns the `JobExecution` of the test run. You can read `StepExecution` directly from that object. When you need to re-query persisted metadata, use `JobExplorer`.

```java
@Autowired
private JobExplorer jobExplorer;

void assertExecutionWasPersisted(JobExecution launchedExecution) {
    JobExecution persisted = jobExplorer.getJobExecution(
            launchedExecution.getId());

    assertNotNull(persisted);
    assertEquals(
            launchedExecution.getStatus(),
            persisted.getStatus());
}
```

`JobExplorer` is useful when tests must verify metadata exists in the repository, or when inspecting an execution after the launcher returns. It also retrieves `StepExecution` instances to check counters after the step finishes.

Avoid querying the `BATCH_STEP_EXECUTION` table directly in ordinary tests when the metadata API meets your needs. Using the repository API keeps tests less coupled to internal schema details.

## Testing skips across read, process, and write

The skip limit applies to the step's total skips. Tests should demonstrate that all stages share one quota.

Example with `skipLimit(2)`:

| Stage | Skips | Accumulated total | Outcome |
| --- | ---: | ---: | --- |
| Read | 1 | 1 | Allowed |
| Process | 1 | 2 | Allowed, equals limit |
| Write | 1 | 3 | Exceeds limit; step fails |

An integration test can configure the reader, processor, and writer to throw skippable exceptions in turn. When the third write skip occurs, the step must exceed the limit even though no single stage reached two skips.

When writing writer-skip tests, understand how the writer handles chunks. The writer receives a group of items; if the writer throws an exception, Spring Batch may need to isolate the failing item via its fault-tolerant mechanism and may re-invoke the writer during scanning/rollback. Therefore, test fixture writers must behave deterministically and avoid non-transactional side effects per trial call.

## Testing skippable vs. non-skippable exceptions

Skip limit applies only after an exception is classified as skippable. An exception outside the skip policy can fail the step even when the skip count is still below the limit.

Example configuration:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.noSkip(NonRecoverableOrderException.class)
.skipLimit(10)
```

Where:

- `InvalidOrderException` is skippable while within the limit.
- `NonRecoverableOrderException` is not skippable and fails the step.
- Any exception not declared in the policy also does not automatically become skippable.

Write a dedicated test for non-skippable exceptions:

```java
@Test
void failsImmediatelyForNonSkippableException() {
    // Prepare input causing processor to throw NonRecoverableOrderException.
    // Launch step and assert FAILED even though skipCount is below limit.
}
```

This test distinguishes failing due to exceeding the limit from failing due to an unskippable exception type. Both cases can leave the step `FAILED`, yet their causes and remedies differ.

## Retry and skip limit

Retry and skip solve two different problems:

- Retry re-attempts an operation that may fail transiently, such as a deadlock or timeout.
- Skip allows bypassing an item after an exception is classified as skippable and retries (if any) did not resolve the error.

Example:

```java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Here, deadlock errors are retried per configuration; `InvalidOrderException` data errors are skippable. If an application configures the same exception type for both retry and skip, understand the precedence and classification policy of the Spring Batch version in use, and explicitly test attempt counts and when the item is skipped.

Do not add `retryCount` into `skipCount`. An item can be retried multiple times and eventually succeed, consuming zero skip limit. Conversely, an item skipped after failing can consume one skip at the stage where the failure occurred.

Listeners can also be invoked multiple times during retries. When recording finally discarded items, `SkipListener` is better suited than creating a final reject record in every error callback.

## Checking SkipListener when skip is accepted

If the application needs to save skipped records into a reject table, use `SkipListener`. Tests should confirm the listener is invoked for items actually skipped and is not invoked as a final skip decision when an item only hit a transient error and succeeded on retry.

Example listener:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedOrderRepository;

    public OrderSkipListener(
            RejectedOrderRepository rejectedOrderRepository) {
        this.rejectedOrderRepository = rejectedOrderRepository;
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable cause) {
        rejectedOrderRepository.save(
                new RejectedOrder(item.orderId(), cause.getMessage()));
    }
}
```

In the step:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(2)
.listener(orderSkipListener)
```

At-limit tests can assert the reject record count equals the number of items actually skipped. Over-limit tests must check listeners and reject records according to the step's actual transaction boundaries. Do not assume every callback or external side effect rolls back with the chunk.

If the reject repository shares the step's transactional resource, records can participate in the chunk transaction per configuration. If writing to an external system, idempotency is required to handle re-executed callbacks or chunks.

## Checking StepExecution counters

`StepExecution` provides key counters:

| Getter | Meaning |
| --- | --- |
| `getReadCount()` | Items read by the reader |
| `getWriteCount()` | Items successfully written per step metadata |
| `getReadSkipCount()` | Skips in the reader |
| `getProcessSkipCount()` | Skips in the processor |
| `getWriteSkipCount()` | Skips in the writer |
| `getSkipCount()` | Total skips in the step |
| `getFilterCount()` | Items filtered by processor returning `null` |
| `getCommitCount()` | Transaction commits recorded for the step |
| `getRollbackCount()` | Rollbacks recorded for the step |

In at-limit tests, you can assert:

```java
assertEquals(2, stepExecution.getSkipCount());
assertEquals(2, stepExecution.getProcessSkipCount());
assertEquals(0, stepExecution.getReadSkipCount());
assertEquals(0, stepExecution.getWriteSkipCount());
```

Checking each counter helps detect exceptions misclassified at the wrong layer. For instance, if a test expects a process skip yet `readSkipCount` increases, the reader may have thrown an exception before passing the item to the processor.

Do not infer filtered items from skip counts. A processor returning `null` is filtering and increments `filterCount`, not skip. Likewise, retry counts are not a kind of skip counter.

## Testing multiple chunks to confirm accumulated counters

A common mistake in tests is placing all items into one chunk and accidentally testing only one scenario. To prove the skip limit accumulates across the step, use a chunk size smaller than the item count and spread errors across multiple chunks.

Example `skipLimit(3)`, chunk size 2:

```text
Chunk 1: valid, invalid  -> processSkipCount = 1
Chunk 2: valid, invalid  -> processSkipCount = 2
Chunk 3: invalid, valid  -> processSkipCount = 3 (allowed)
Chunk 4: invalid, valid  -> 4th skip, step FAILED
```

This test confirms the limit is not reset on chunk commit. If the first and second chunks committed, their business data remains persisted when a later chunk exceeds the limit. This also helps test writer idempotency and restart behavior.

## Testing restart after skip limit exceeded

When a step exceeds its skip limit, the step fails. Restarting depends on the job's restartable setting, identifying parameters, reader state, and source data.

Restart tests should answer:

- Is the job allowed to restart?
- Can the reader resume from the committed checkpoint?
- Did the failing dataset change after addressing the root cause?
- How does skip limit apply to the new step execution under restart metadata?
- Are chunks committed prior to the failure rewritten?
- Does the writer handle items safely if reread?

Do not automatically increase `skipLimit` on restart just so the job gets past the error without a business decision. If failing data needs fixing, fix the source or handle it via a controlled reject/replay workflow. If policy changes, clearly record the configuration and application version used for that execution.

In restart tests, keep identifying parameters identical to continue the same `JobInstance`. Do not generate a new identifying `runId` on restart; doing so creates a different instance and fails to test actual restart.

## Test isolation and JobParameters

Spring Batch stores metadata in `JobRepository`. If two tests use the same job name and identifying parameters, the later test may hit `JobInstanceAlreadyCompleteException` or leftover execution state from the earlier test.

For independent tests, generate a distinct identifying parameter per run:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("scenario", "at-limit", true)
        .addString("testRunId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

For restart tests, build parameters once and reuse the exact same parameter set on the second run. Do not create a new UUID between the first run and the restart.

If using `JobRepositoryTestUtils`, you can clean up metadata created by tests:

```java
@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Cleaning metadata does not automatically delete business data, files, or reject records. Clean up that data keyed by test ID. If tests run concurrently against the same repository, do not use global cleanup that could delete another test's executions; prefer separate databases/schemas or scoped cleanup.

## Common mistakes in skip limit tests

### Thinking equal to skipLimit fails

The `N`th skip is still allowed under `skipLimit(N)`. Only the `N+1`th skip exceeds the limit. Tests need both the at-limit case and the one-over-limit case.

### Thinking skipLimit applies separately to read, process, and write

Counters sum into the step's total skips. One read skip and one process skip consume the same quota.

### Using an exception outside the skip policy

The step can fail even when the skip count is still below the limit. Check exception types and `.skip(...)`/`.noSkip(...)` settings.

### Asserting only BatchStatus

`FAILED` can result from an unskippable exception, writer error, transaction error, or limit exceedance. Check `failureExceptions`, counters, and logs to confirm the root cause.

### Not creating distinct identifying parameters per test

Stale metadata can cause tests to be affected by prior runs. Use a dedicated `testRunId` for independent tests and keep parameters identical for restart tests.

### Ignoring transactions and chunk commits

When exceeding the limit in the current chunk, that chunk may roll back, whereas previously committed chunks persist. Tests must inspect data across transaction boundaries.

### Treating retry count as skip count

Retry is a re-attempt; skip is a decision to discard an item. Check the right counters and callbacks for the test's objective.

### Testing only processor skip without reader/writer

If the application permits skips across multiple stages, test total skips accumulated across stages. For writer skips, note that the writer may be re-invoked while isolating the failing item.

## Recommended test matrix

A minimal test suite for a step with `skipLimit(2)` can include:

| Case | Input/error | Expected outcome |
| --- | --- | --- |
| No errors | 0 skips | `COMPLETED`, skip count 0 |
| Below limit | 1 skip | `COMPLETED`, skip count 1 |
| At limit | 2 skips | `COMPLETED`, skip count 2 |
| Over limit | 3 skips | `FAILED`, with `SkipLimitExceededException` |
| Non-skippable exception | 1 error outside policy | `FAILED` even though skip count is below limit |
| Multi-stage skips | Read 1 + process 1 + write 1 | Exceeds total limit of 2 |
| Retry then succeed | Transient error, then succeeds | `COMPLETED`, no skip added for that item |
| Multiple chunks | Skips spread across multiple chunks | Total skips accumulate within step |
| Restart | Step fails then reruns same instance | Checkpoints and business output accurate, no duplicates |

Not every application needs the entire matrix upfront. At-limit, over-limit, non-skippable exceptions, and test isolation form the most important foundation.

## Implementation principles

When writing tests for skip policies, align on these points:

1. Identify exactly which exceptions are skippable.
2. Set `skipLimit` per business rules and recognize the limit applies jointly to read/process/write.
3. Test skip counts equal to the limit and one above the limit.
4. Check `BatchStatus`, `ExitStatus`, and `failureExceptions`.
5. Assert per-stage counters alongside total `skipCount`.
6. Distinguish filtering, retry, and skip.
7. Test non-skippable exceptions.
8. Spread errors across multiple chunks when verifying accumulated counters.
9. Verify transaction rollback of the limit-exceeding chunk and persistence of prior committed chunks.
10. Use distinct identifying parameters for independent tests and identical parameters for restart tests.
11. Check `SkipListener` and reject output if the application stores discarded records.

`JobLauncherTestUtils` works well for running steps/jobs in integration tests; `JobExplorer` helps read persisted metadata; `JobRepositoryTestUtils` supports controlled cleanup. Use an appropriate test database and verify both batch status and business data results.

## Remember

`skip` defines which exception types can be bypassed; `skipLimit` defines the maximum total skips for a step. With `skipLimit(N)`, exactly N skips are still accepted, while the N+1th skip fails the step with `SkipLimitExceededException`. This total includes read, process, and write skips, not a separate quota per stage or per chunk. Test both boundary cases with deterministic data, check `BatchStatus`, failure exceptions, and skip counters, and distinguish skip from retry and filtering. When the limit is exceeded, the current chunk may roll back while earlier committed chunks persist; restart tests must keep identifying parameters identical and verify the writer does not produce duplicate data.
