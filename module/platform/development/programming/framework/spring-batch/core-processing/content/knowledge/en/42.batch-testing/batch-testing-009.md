# Asserting `StepExecution` Counts in Spring Batch

## 1. Why Should You Inspect `StepExecution` Counters?

In Spring Batch, a `Step` can finish with `COMPLETED` status while its processing outcome is still wrong from a business perspective. For example, a job importing 100 records succeeds yet writes only 90 records; the remaining 10 records might have been intentionally filtered, skipped due to errors, or bypassed from the expected processing flow. Checking only `BatchStatus.COMPLETED` cannot distinguish those scenarios.

`StepExecution` stores information for **a single execution of a Step**, including status, timestamps, exceptions, and multiple counters. In batch testing, *asserting counts* means comparing those counters against expected outcomes from a known test dataset.

After this lesson, you will be able to:

- Distinguish `readCount`, `writeCount`, `filterCount`, the `skipCount` variants, `commitCount`, and `rollbackCount`.
- Run a Step in a test using `spring-batch-test` and retrieve the exact `StepExecution` to inspect.
- Write assertions for normal flows, filtering flows, and *fault-tolerant* flows.
- Explain why count comparisons can be misleading when a Step involves retries, rollbacks, restarts, or partitions.

## 2. `StepExecution` and the Meaning of Each Count

Each time a `Step` runs, Spring Batch records a corresponding `StepExecution` object. Two runs of the same Step name create two distinct `StepExecution` instances. Therefore, a count must always be interpreted within **the scope of the execution** you are asserting.

Commonly used properties:

| Method | Meaning in an Item-Processing Step | When to Assert? |
| --- | --- | --- |
| `getReadCount()` | Number of items successfully read by the reader and passed into processing; not the number of rows existing in the data source. | Confirming the number of items ingested from the test dataset. |
| `getWriteCount()` | Number of items Spring Batch counts as written through the writer. | Confirming the output volume recorded by the Step. |
| `getFilterCount()` | Number of items excluded because `ItemProcessor` returned `null`. | Confirming data filtering rules operate as intended. |
| `getReadSkipCount()` | Number of read errors permitted to be skipped by the skip policy. | Testing malformed source data or a skippable reader. |
| `getProcessSkipCount()` | Number of items whose processor errors were skipped. | Testing transformation or data validation errors. |
| `getWriteSkipCount()` | Number of items whose writer errors were skipped. | Testing write failures when configuration permits skipping. |
| `getSkipCount()` | Total skips: read skips + process skips + write skips. | Checking total skips and cross-checking individual categories. |
| `getCommitCount()` | Number of transaction commits recorded by the Step. | When testing transaction/chunk behavior with controlled configuration. |
| `getRollbackCount()` | Number of rollbacks recorded by the Step. | When testing rollback/retry or transaction error handling. |

Beyond counts, properties to read alongside them are `getStatus()` (`BatchStatus`), `getExitStatus()` (`ExitStatus`), and `getFailureExceptions()`.

### How Does Item Flow Update Counts?

```text
                    ItemReader
                        |
           read succeeds: readCount + 1
                        |
                        v
                  ItemProcessor
                        |
           +------------+-------------+
           |            |             |
      returns null  returns item  skippable error
           |            |             |
   filterCount + 1      |     processSkipCount + 1
                        v
                    ItemWriter
                        |
           write succeeds: writeCount
                        |
                  transaction commit

  Skippable reader error --> readSkipCount + 1
  Skippable writer error --> writeSkipCount + 1
```

The diagram above describes the simple case. In chunk processing, the writer receives a **chunk of multiple items**, not necessarily one call per item. When retries or rollbacks occur, items may be reprocessed; therefore, do not derive exact counts solely from how many times reader/processor/writer methods were invoked.

### `filter` vs. `skip`

These two concepts are easily confused:

- **Filter** is a normal exclusion of an item: `ItemProcessor#process` returns `null`. `filterCount` increments, it is not treated as an error, and it does not increment `skipCount`.
- **Skip** is error handling under a declared policy: an exception of a skippable type occurs in the reader, processor, or writer. The counter for that failure stage increments accordingly.

For example, read 6 items: `A`, `B`, `IGNORE`, `C`, `BROKEN`, `D`. The processor filters out `IGNORE`, while `BROKEN` throws a skippable exception; the remaining items are written successfully. In a single run with no unexpected retries or rollbacks, we expect:

| Count | Expected | Explanation |
| --- | ---: | --- |
| `readCount` | 6 | All six items were successfully read by the reader. |
| `filterCount` | 1 | `IGNORE` was filtered out. |
| `processSkipCount` | 1 | `BROKEN` threw an error in the processor and was skipped. |
| `writeCount` | 4 | `A`, `B`, `C`, `D` were written. |
| `readSkipCount` | 0 | No skippable errors occurred in the reader. |
| `writeSkipCount` | 0 | No skippable errors occurred in the writer. |
| `skipCount` | 1 | Only one process skip occurred. |

In this case, the valid reconciliation formula is:

```text
readCount = writeCount + filterCount + processSkipCount
        6 =          4 +           1 +                1
```

**Do not treat this formula as an invariant for every Step.** Read skips, write skips, retries, rollbacks, restarts, duplicate data, or special writer flows can render simple arithmetic invalid. Establish expectations based on each actual scenario.

## 3. Setting Up Step Testing with `spring-batch-test`

The example below uses **Spring Batch 5.x, Spring Boot 3.x, JUnit 5, and AssertJ**. This style fits when the project already configures a `Job` containing a Step named `importCustomersStep` and has stable test data.

With Maven, the project typically needs the following test dependencies (Spring Batch versions should be managed by the Spring Boot BOM):

```xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

`@SpringBatchTest` provides batch testing utilities, including `JobLauncherTestUtils`. `@SpringBootTest` initializes the application context containing the Job, Step, `JobRepository`, transaction manager, and related beans. For a Spring Boot application, disable automatic job execution in tests so the test itself decides when to launch:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersStepTest {
    // Assertion examples are in the next section.
}
```

The test needs an available `Job` and `Step` in the context. If **multiple Jobs** exist, explicitly configure the target Job on `JobLauncherTestUtils` (for example, inject the Job with `@Qualifier` and call `jobLauncherTestUtils.setJob(job)` before launching). Repository/schema configuration and input data should use an independent test environment so they do not depend on real data.

## 4. Running the Step and Asserting Basic Counts

Suppose `importCustomersStep` is designed to read six records as in the table from Section 2. The processor returns `null` for `IGNORE`; an exception for `BROKEN` is configured as skippable; the writer persists the four valid items. Example integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void shouldAssertStepExecutionCounts() throws Exception {
        // Test data prepared separately: A, B, IGNORE, C, BROKEN, D.
        JobParameters parameters = new JobParametersBuilder()
                .addLong("test.run.id", System.nanoTime())
                .toJobParameters();

        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
                "importCustomersStep", parameters);

        StepExecution stepExecution = jobExecution.getStepExecutions().stream()
                .filter(step -> "importCustomersStep".equals(step.getStepName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "StepExecution for importCustomersStep not found"));

        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        assertThat(stepExecution.getReadCount()).isEqualTo(6);
        assertThat(stepExecution.getFilterCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteCount()).isEqualTo(4);

        assertThat(stepExecution.getReadSkipCount()).isZero();
        assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteSkipCount()).isZero();
        assertThat(stepExecution.getSkipCount()).isEqualTo(1);
    }
}
```

Conditions required for the test to genuinely reflect the scenario:

1. The reader must read the exact dataset prepared for each launch. For stateful readers such as `ListItemReader`, create a fresh instance for each execution (for instance, declare the reader `@StepScope`) or reset its data properly.
2. The processor must filter `IGNORE` by returning `null`; the error for `BROKEN` must belong to a skippable type and stay within `skipLimit`.
3. The writer must write the four valid items. When testing a real writer, also assert the contents of the destination table/file/target, since `writeCount` alone does not prove every external side effect is accurate.
4. `test.run.id` creates a parameter identifying the run to prevent the repository from treating it as a previously completed `JobInstance`. For repeated tests, a UUID or a distinct test identifier also works.

If **whole-Job** behavior is what matters, use `jobLauncherTestUtils.launchJob(parameters)` and extract the corresponding Step from `JobExecution`. If you only want to run a specifically named Step, `launchStep(...)` is more concise; remember that launching a Step directly does not thoroughly test step transitions or the original Job's job listeners.

### Retrieving the Exact `StepExecution`

A `JobExecution` can contain multiple `StepExecution` instances. Never assume the first element in `getStepExecutions()` is the Step you want to check:

```java
StepExecution stepExecution = jobExecution.getStepExecutions().stream()
        .filter(s -> "importCustomersStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();
```

For tests requiring the Step to execute only once, assert that condition first:

```java
assertThat(jobExecution.getStepExecutions())
        .filteredOn(s -> s.getStepName().equals("importCustomersStep"))
        .hasSize(1);
```

If a Step runs multiple times or the job uses partitioning, select or aggregate the executions appropriate for your test goal instead of arbitrarily calling `findFirst()`.

## 5. Common Assertion Scenarios

### 5.1. No Filtering, No Skipping

Reader returns 12 items, processor transforms all 12, and writer receives all 12 items:

```java
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(12);
assertThat(stepExecution.getWriteCount()).isEqualTo(12);
assertThat(stepExecution.getFilterCount()).isZero();
assertThat(stepExecution.getSkipCount()).isZero();
```

This is the standard *happy path*. If `readCount = 12` while `writeCount = 10`, two items may have been filtered; therefore, asserting `filterCount == 0` helps pinpoint discrepancies faster than checking only total output.

### 5.2. Filtering Valid Items by Business Rules

For example, the Step reads eight transactions, two transactions fail a business condition and are filtered via `return null`, and the remaining six transactions are written:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(8);
assertThat(stepExecution.getFilterCount()).isEqualTo(2);
assertThat(stepExecution.getWriteCount()).isEqualTo(6);
assertThat(stepExecution.getSkipCount()).isZero();
```

Here, excluding two transactions is the expected outcome. If the test mistakenly asserted `writeCount == readCount`, the test would fail on business expectations even when the processing code is right.

### 5.3. Skipping Errors in the Processor

For a processor error to count as a skip, the Step must configure fault tolerance, for example:

```java
new StepBuilder("importCustomersStep", jobRepository)
        .<String, Customer>chunk(3, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(2)
        .build();
```

In the configuration snippet above, `InvalidCustomerException` is an application-defined business exception; `customerReader`, `customerProcessor`, and `customerWriter` are the application's corresponding beans. With one item throwing `InvalidCustomerException` in the processor and one item filtered as in the earlier example:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(6);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(4);
assertThat(stepExecution.getSkipCount()).isEqualTo(1);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

`skipLimit(2)` means up to two errors of skippable types may be skipped. Exceeding the limit can cause the Step to fail. An over-limit test should verify `FAILED` status and the error cause rather than assuming counts still follow the addition formula from a successful scenario.

### 5.4. Distinguishing Read Errors from Write Errors

Each skip counter tells you where the error occurred:

```java
assertThat(stepExecution.getReadSkipCount()).isEqualTo(expectedReadSkips);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(expectedProcessSkips);
assertThat(stepExecution.getWriteSkipCount()).isEqualTo(expectedWriteSkips);

assertThat(stepExecution.getSkipCount()).isEqualTo(
        expectedReadSkips + expectedProcessSkips + expectedWriteSkips);
```

Checking only `getSkipCount() == 2` does not tell the test whether those two errors came from the reader, processor, or writer. When business logic has specific expectations about invalid record types, assert each individual counter to preserve diagnostic clarity.

For read errors, an item that fails to be read usually does **not** contribute to `readCount`; a skipped read error is reflected in `readSkipCount`. Thus, do not assume `readCount` equals the physical line count in a file when the file contains malformed lines.

### 5.5. `commitCount` and `rollbackCount`

Suppose a Step processes with chunk size 5. In a smooth run, you might predict the transaction count, but **do not mechanically apply** the formula `ceil(readCount / chunkSize)` to `commitCount`. End-of-data check transactions, framework internals, errors, restarts, and Step configuration can all affect the count.

For a test that only needs to ensure at least one transaction succeeded with no rollbacks:

```java
assertThat(stepExecution.getCommitCount()).isPositive();
assertThat(stepExecution.getRollbackCount()).isZero();
```

Assert exact `commitCount` or `rollbackCount` values only when that is **the exact behavior under test**, the environment is deterministic, and the test controls error injection, retries, and transaction boundaries. A rollback is not synonymous with a skip: an error can trigger a rollback and then succeed on retry, or ultimately be skipped according to the Step's policy.

## 6. Inspecting Status Alongside Counts

A single counter does not tell you whether a Step succeeded or failed. `BatchStatus` indicates execution status (`COMPLETED`, `FAILED`, `STOPPED`, etc.), while `ExitStatus` indicates the exit result used for flow branching or custom outcomes.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;

assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
assertThat(stepExecution.getFailureExceptions()).isEmpty();
```

Do not always hardcode `ExitStatus.COMPLETED`: an application may use a custom `ExitStatus` such as `COMPLETED_WITH_SKIPS`. In that case, assert the exact application contract. Likewise, a Step can be `COMPLETED` even with `skipCount > 0`, provided skipping is allowed and within the limit.

For failure scenarios, such as an unskippable error:

```java
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(stepExecution.getFailureExceptions()).isNotEmpty();
```

You can add count assertions at failure time if the goal is checking processing progress prior to the error. Base them on the configured Step semantics, because a rolled-back chunk can affect recorded metrics.

## 7. Unit Testing with `MetaDataInstanceFactory`

Not every test needs to run an entire Step. If you want to test a listener, formatter, or service **that accepts `StepExecution` as input**, `spring-batch-test` provides `MetaDataInstanceFactory` to create metadata objects for unit tests:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.assertj.core.api.Assertions.assertThat;

class StepExecutionMetadataTest {

    @Test
    void shouldExposePreparedCounts() {
        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
        stepExecution.setReadCount(10);
        stepExecution.setFilterCount(2);
        stepExecution.setWriteCount(8);

        assertThat(stepExecution.getReadCount()).isEqualTo(10);
        assertThat(stepExecution.getFilterCount()).isEqualTo(2);
        assertThat(stepExecution.getWriteCount()).isEqualTo(8);
    }
}
```

The snippet above illustrates **initializing mock metadata**; setting values yourself and asserting those same values does not prove reader/processor/writer logic works. In real usage, pass the prepared `stepExecution` into **the logic under test** (for example, a service generating a summary message) and assert that logic's output. To verify counts produced by real batch processing, launch the Step/Job as in Section 4.

## 8. Common Causes of Incorrect Assertions

### Unstable Input Data

If a test uses a table containing leftover rows from a prior run, the number of items actually read can spike unexpectedly. Use deterministic fixtures, clean data after tests, or use an isolated database; also clarify whether the reader paginates, filters in SQL, or drops items in the processor. Records excluded directly in a query do **not** increment `filterCount`, as they never reach the processor.

### Stateful Readers Between Runs

A reused `ListItemReader` or cursor-based reader may fail to reread the dataset from the beginning. When testing a Step multiple times, create a fresh reader per `StepExecution` (usually via `@StepScope`) or configure lifecycle management properly. Misconfiguration causes `readCount` to be lower than expected even with no business error.

### Retries and Rollbacks

An item failing on the first attempt may be retried and succeed later. Processor/writer invocation counts can exceed the final number of written items. Similarly, a rollback can cause a chunk to re-execute; therefore, do not infer `readCount` from mock method call counts, or `writeCount` from writer invocation counts, when testing fault tolerance.

### Restarts and Different Executions

When a Job restarts, the `StepExecution` of the prior run and the subsequent run are distinct objects. To inspect item counts **for a single run**, take counts from that exact execution. To verify the cumulative result across a restart, carefully determine which metrics accumulate so you do not double-count items written before the restart; in many cases, checking actual output data is more meaningful than summing counts alone.

### Partitioning and Parallel Steps

In a partitioned Step, each worker partition can have its own `StepExecution`, while the manager Step holds aggregated info. Do not blindly sum all `StepExecution` records, as you risk double-counting manager and worker metrics. If summing by partition, select the exact set of worker executions and align with the aggregation mechanism of your specific configuration. With multi-threaded Steps, processing order is also not guaranteed, so prefer asserting counts and final output contents over item ordering.

### Counts Do Not Replace Output Verification

`writeCount == 100` only indicates that the framework recorded 100 items passed through the writer successfully per its contract. It does not guarantee columns were mapped accurately, values are right, no duplicate IDs exist, or external systems durably persisted all changes. For critical Steps, verify **both counts and target data state**.

## 9. Reusable Assertion Patterns

When multiple tests share the same verification policy, group assertions into a clear helper:

```java
import org.springframework.batch.core.StepExecution;

import static org.assertj.core.api.Assertions.assertThat;

final class StepCountAssertions {

    private StepCountAssertions() {}

    static void assertCounts(
            StepExecution step,
            int read,
            int written,
            int filtered,
            int readSkipped,
            int processSkipped,
            int writeSkipped) {

        assertThat(step.getReadCount()).as("readCount").isEqualTo(read);
        assertThat(step.getWriteCount()).as("writeCount").isEqualTo(written);
        assertThat(step.getFilterCount()).as("filterCount").isEqualTo(filtered);
        assertThat(step.getReadSkipCount()).as("readSkipCount").isEqualTo(readSkipped);
        assertThat(step.getProcessSkipCount()).as("processSkipCount")
                .isEqualTo(processSkipped);
        assertThat(step.getWriteSkipCount()).as("writeSkipCount")
                .isEqualTo(writeSkipped);
        assertThat(step.getSkipCount()).as("total skipCount")
                .isEqualTo(readSkipped + processSkipped + writeSkipped);
    }
}
```

In the six-item scenario test above:

```java
StepCountAssertions.assertCounts(stepExecution, 6, 4, 1, 0, 1, 0);
```

The `as(...)` labels make assertion failure messages pinpoint which count was wrong. Still, name tests after business behavior, such as `shouldFilterInactiveCustomersAndSkipMalformedRecord`, so readers understand **why** each value is expected rather than seeing only a list of numbers.

## 10. Choosing the Right Assertions for Your Test Goal

| Goal | Primary Assertions | Additional Checks to Perform |
| --- | --- | --- |
| Import all valid data | `readCount`, `writeCount`, `filterCount == 0`, `skipCount == 0` | Records actually persisted. |
| Filter data by condition | `filterCount`, `writeCount`, `readCount` | Contents of retained and excluded items. |
| Allow skipping faulty records | `readSkipCount` / `processSkipCount` / `writeSkipCount`, status | Exception types and valid data still processed. |
| Exceed skip limit | `BatchStatus.FAILED`, failure exceptions | Transaction changes rolled back / committed. |
| Test transactions | `commitCount`, `rollbackCount` under controlled scenarios | Data state after commit/rollback. |
| Test restart or partitioning | Exact `StepExecution` of the run/partition | Final cumulative outcome without double-counting. |

The core principle is to **assert both the processing outcome and how that outcome was reached**. Use `BatchStatus` to confirm the Step terminated as expected, use `StepExecution` counts to detect misfiltered or mis-skipped items, and inspect output data to prove the business requirements were fulfilled accurately.
