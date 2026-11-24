# Empty and Boundary Data in Spring Batch Testing

## 1. Why test empty data and boundary data?

In Spring Batch, a job typically processes large volumes of data from files, databases, or external services. Datasets with a few hundred valid records usually run smoothly yet fail to represent the most bug-prone cases: **zero records**, **only invalid records**, **record counts sitting right on chunk/page boundaries**, or **field values at exact validation limits**.

For example, an order-import job can encounter:

- A day with no orders: the source query returns 0 rows.
- A CSV file containing a header but zero data rows.
- Every record filtered out by the processor for failing business conditions.
- Exactly 100 or 101 records when configured with chunk size 100.
- An amount equal to 0, just below minimum, right at maximum, or above maximum.
- A string whose length equals the exact database column limit.
- Data containing whitespace, Unicode characters, missing fields, and `null` fields.

These situations directly affect how Spring Batch terminates the read loop, closes resources, flushes the final chunk, updates step counters, and determines job status. A good test must define **expected system behavior for each input shape**, then verify both business outcomes and Spring Batch metadata.

The goal of this lesson is to build purposeful test data, run the job in an isolated test environment, and use `StepExecution` to prove empty and boundary data are handled accurately.

## 2. Understanding "empty" accurately at each stage

Not all "zero output data" scenarios are alike.

| Situation | Reader | Processor | Writer | What to test |
| --- | --- | --- | --- | --- |
| Truly empty source | Returns `null` on first `read()` | Never called | Never called | Step completes per expected policy, produces no output |
| Source has data, all records filtered | Reads N records | Returns `null` for each record | Writes zero items | `readCount=N`, `filterCount=N`, `writeCount=0` |
| Source has malformed records | Read/mapping may throw exception | Depends on config | Depends on config | Distinguish `skip`, `retry`, and `FAILED` |
| Record has blank fields | Still returns an object if mapping succeeds | Can normalize, filter, or reject | Depends on business logic | Do not confuse blank fields with end of input |
| Missing source | May fail when opening resource | Never runs | Never runs | Distinguish missing file from 0-row file |
| Source has data, query filters all out | Returns 0 records | Never runs | Never runs | Verify query predicate and "no results" policy |

### Important convention of ItemReader

For `ItemReader<T>`, returning `null` from `read()` signals **end of input**:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Consequently, `null` cannot be emitted as a valid item from a reader under the standard contract. If a business record has an empty field, the reader should return an object—such as `new OrderRow(id, null, amount)`—and let the processor or validator decide how to handle that field. Meanwhile, `ItemProcessor.process()` returning `null` means **filter out the current item**, not end of input.

This distinction affects counters and test logic. A step that reads 10 items and filters them all still has `readCount=10`, unlike a step hitting EOF immediately with `readCount=0`.

## 3. Boundary data at the record-count level

Suppose a step uses chunk size `3`. Do not test only datasets with 9 or 12 rows. The following sizes catch common chunk-boundary bugs:

| Input item count | Test objective |
| ---: | --- |
| 0 | Empty source, terminates immediately |
| 1 | Single item, must still be written |
| 2 | Less than one full chunk |
| 3 | Exactly one chunk |
| 4 | One full chunk plus a trailing 1-item chunk |
| 6 | Exactly two chunks |
| 7 | Two full chunks plus a remainder chunk |
| Very large N | Behavior with realistic volume, resources, performance, and stability |

If all `N` items are valid without filtering/skipping/retrying and the writer works properly, the expectations are:

```text
readCount = N
filterCount = 0
writeCount = N
Output item count = N
```

**Do not assume `commitCount = ceil(N / chunkSize)`.** A chunk-oriented step may perform an extra transaction to detect EOF or behave differently depending on configuration and framework version. When testing input/output data, focus on actual items read, filtered, written, and business output.

Beyond chunk size, test boundaries of **page size**, partition item counts, per-request limits, and having the final record sit at the very end of a file/page.

## 4. Setting up the test environment

For projects using Spring Boot 3.x, Spring Batch 5.x, and JUnit 5, test dependencies can be configured as:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

In an integration test environment:

1. Use an isolated database holding Spring Batch metadata, such as H2.
2. Disable auto-running jobs at context startup via `spring.batch.job.enabled=false`.
3. Initialize metadata schema in the test database via `spring.batch.jdbc.initialize-schema=always` when appropriate.
4. Clean metadata between tests or use isolated databases so prior runs are not confused with the run under test.
5. Supply test data directly in fixtures or create fresh test files/database rows per scenario.
6. Pass deterministic `JobParameters` when launching jobs, avoiding random parameters that hinder reproducibility.

`@SpringBatchTest` provides utilities such as `JobLauncherTestUtils` and `JobRepositoryTestUtils`. If a test needs explicit control over which job runs, inject `JobLauncher` and the specific `Job`, as shown below.

## 5. Integration test example with empty data and chunk sizes

This example uses a job accepting a list of strings from a fixture. Each string is trimmed and uppercased; whitespace-only strings are filtered out. The writer records output in a collector for test assertions. Chunk size is fixed at `3` to highlight boundary values.

Crucially, the reader is created **fresh for each StepExecution** via `@StepScope`. Reusing the same `ListItemReader` after it reached the end of the list would cause subsequent tests to see fake empty input due to stale read state.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.IntStream;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(
    classes = EmptyAndBoundaryDataTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:edge_data_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class EmptyAndBoundaryDataTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("boundaryJob")
    private Job job;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private InputFixture fixture;

    @Autowired
    private OutputProbe outputProbe;

    @BeforeEach
    void resetData() {
        jobRepositoryTestUtils.removeJobExecutions();
        fixture.replace(List.of());
        outputProbe.clear();
    }

    private JobExecution launch(String testCase) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("case", testCase, true)
            .toJobParameters();

        return jobLauncher.run(job, parameters);
    }

    private StepExecution onlyStep(JobExecution execution) {
        assertEquals(1, execution.getStepExecutions().size());
        return execution.getStepExecutions().iterator().next();
    }

    @Test
    void emptySourceProducesNoOutput() throws Exception {
        fixture.replace(List.of());

        JobExecution execution = launch("empty-source");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(0, step.getReadCount());
        assertEquals(0, step.getFilterCount());
        assertEquals(0, step.getWriteCount());
        assertEquals(List.of(), outputProbe.snapshot());
        assertEquals(0, outputProbe.writeCalls());
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 1, 2, 3, 4, 6, 7})
    void worksAroundChunkBoundaries(int count) throws Exception {
        List<String> input = IntStream.range(0, count)
            .mapToObj(i -> " item-" + i + " ")
            .toList();
        List<String> expected = IntStream.range(0, count)
            .mapToObj(i -> "ITEM-" + i)
            .toList();

        fixture.replace(input);

        JobExecution execution = launch("count-" + count);
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(count, step.getReadCount());
        assertEquals(0, step.getFilterCount());
        assertEquals(count, step.getWriteCount());
        assertEquals(expected, outputProbe.snapshot());
    }

    @Test
    void sourceWithOnlyWhitespaceFiltersEveryItem() throws Exception {
        fixture.replace(List.of(" ", "", "\t"));

        JobExecution execution = launch("only-whitespace");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(3, step.getReadCount());
        assertEquals(3, step.getFilterCount());
        assertEquals(0, step.getWriteCount());
        assertEquals(List.of(), outputProbe.snapshot());
        assertEquals(0, outputProbe.writeCalls());
    }

    @Test
    void mixedItemsPreserveOnlyValidData() throws Exception {
        fixture.replace(List.of("  apple  ", " ", "banana", ""));

        JobExecution execution = launch("mixed-input");
        StepExecution step = onlyStep(execution);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(4, step.getReadCount());
        assertEquals(2, step.getFilterCount());
        assertEquals(2, step.getWriteCount());
        assertEquals(
            List.of("APPLE", "BANANA"),
            outputProbe.snapshot()
        );
    }

    // Test data replaced before each step starts.
    static class InputFixture {
        private List<String> rows = List.of();

        synchronized void replace(List<String> newRows) {
            rows = List.copyOf(newRows);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(rows);
        }
    }

    // Output records and number of ItemWriter.write invocations.
    static class OutputProbe {
        private final List<String> written = new ArrayList<>();
        private int calls;

        synchronized void capture(List<? extends String> items) {
            calls++;
            written.addAll(items);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(written);
        }

        synchronized int writeCalls() {
            return calls;
        }

        synchronized void clear() {
            written.clear();
            calls = 0;
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        InputFixture fixture() {
            return new InputFixture();
        }

        @Bean
        OutputProbe outputProbe() {
            return new OutputProbe();
        }

        @Bean
        @StepScope
        ListItemReader<String> edgeReader(InputFixture fixture) {
            return new ListItemReader<>(fixture.snapshot());
        }

        @Bean
        ItemProcessor<String, String> normalizingProcessor() {
            return item -> {
                String value = item.trim();
                return value.isEmpty()
                    ? null
                    : value.toUpperCase(Locale.ROOT);
            };
        }

        @Bean
        ItemWriter<String> capturingWriter(OutputProbe outputProbe) {
            return chunk -> outputProbe.capture(chunk.getItems());
        }

        @Bean
        Step boundaryStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                @Qualifier("edgeReader") ItemReader<String> reader,
                @Qualifier("normalizingProcessor")
                    ItemProcessor<String, String> processor,
                @Qualifier("capturingWriter") ItemWriter<String> writer) {

            return new StepBuilder("boundaryStep", jobRepository)
                .<String, String>chunk(3, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
        }

        @Bean
        Job boundaryJob(
                JobRepository jobRepository,
                @Qualifier("boundaryStep") Step step) {

            return new JobBuilder("boundaryJob", jobRepository)
                .start(step)
                .build();
        }
    }
}
```

### What the test cases verify

**Completely empty source:** `ListItemReader` returns `null` immediately, so the reader passes no items to the processor/writer. In this example, the job is designed to accept empty sources; hence `BatchStatus.COMPLETED` is valid, with all three counts equal to 0.

**Sizes around chunk boundaries:** the parameter set `{0,1,2,3,4,6,7}` proves partial chunks, exact chunks, and remainder final chunks all write the exact total item count in the exact order.

**Whitespace-only data:** the reader read 3 items, yet the processor returned `null` all 3 times. `readCount=3` and `filterCount=3` distinguish "wrote nothing because everything was filtered" from "source had no data".

**Interleaved valid and filtered items:** checks not just count but output contents, ensuring retained records stay ordered and normalized as expected.

In this example, `OutputProbe` uses memory for easy observation. When testing real jobs, verify data in the target table, output file, or emitted messages. If writing within the chunk transaction, also test rollback when the writer fails.

## 6. Empty data across source types

### 6.1. CSV or text files

Fixtures should be separated clearly:

```text
empty.csv             -> 0 bytes
header-only.csv       -> id,amount\n
blank-lines.csv       -> empty or whitespace-only lines
valid-one-row.csv     -> header + 1 record
missing-file.csv      -> non-existent path
malformed-row.csv     -> record missing column or wrong type
```

With `FlatFileItemReader`:

- **Existing empty file:** the reader reads zero items; the step can end `COMPLETED` if business accepts it.
- **Header-only file:** when configured to skip one header line, the outcome is also 0 items; verify the header is handled properly and not written as a business record.
- **Non-existent file:** with `strict=true` (default), the reader fails when opening the resource; with `strict=false`, it treats a missing source like an empty input. The intended rule must be explicit.
- **Blank lines:** depending on `RecordSeparatorPolicy`, `LineMapper`, and processing logic, blank lines may be skipped or trigger mapping errors. Never assume blank lines and EOF are the same event.
- **Final line without trailing newline:** must still be read as a valid record if its content is valid.

Example configuration emphasizing missing-file policy:

```java
FlatFileItemReader<OrderRow> reader = new FlatFileItemReaderBuilder<OrderRow>()
    .name("orderCsvReader")
    .resource(new FileSystemResource("test-data/orders.csv"))
    .linesToSkip(1)
    .delimited()
    .names("id", "amount")
    .fieldSetMapper(fieldSet -> new OrderRow(
        fieldSet.readLong("id"),
        fieldSet.readBigDecimal("amount")
    ))
    .strict(true)
    .build();
```

Test fixtures should be created in JUnit's temporary directory or loaded from managed test resources. Avoid working-directory paths tied to developer machines.

### 6.2. Database

With `JdbcCursorItemReader` or `JdbcPagingItemReader`, a query returning 0 rows is valid at the JDBC level. However, bad SQL or connection failures must be distinguished from empty query results.

A test suite should cover:

- An empty table.
- A populated table where the `WHERE` clause matches nothing.
- Exactly 1 row, exact page size, one row over page size.
- Nullable columns containing `NULL`, separate from zero rows.
- `VARCHAR`, `DECIMAL`, or date columns at schema minimum/maximum boundaries.
- For paging readers, data with an explicit, unique sort key to prevent missing or duplicated rows across pages.

When seeding fixtures via SQL, inspect both source row counts before the job and target row counts afterward. Checking only `COMPLETED` can miss accidentally filtering out the entire dataset.

### 6.3. API or message queue

External sources may return an empty list, HTTP `204 No Content`, an empty final page, network errors, or rate limits. Each case means something different. Reader/adapter tests must specify which conditions mean "no more data" versus which require retry or fail.

With paginated APIs, do not stop the read loop just because one page is empty if the API contract still provides a `nextPageToken`. Rely on the source's true termination rule.

## 7. Boundary values for individual fields

Beyond item counts, construct test data for values at business and storage limits.

For example, suppose order codes are 1 to 20 characters long, and amounts are greater than 0 and at most 10,000,000:

| Field | Test data | Expected outcome |
| --- | --- | --- |
| `orderCode` | `""` and `"   "` | Rejected or filtered per policy |
| `orderCode` | Length 1 | Valid if other constraints pass |
| `orderCode` | Length 20 | Valid at upper threshold |
| `orderCode` | Length 21 | Invalid; must not be silently truncated |
| `amount` | `null` | Invalid if required |
| `amount` | `-0.01`, `0` | Invalid |
| `amount` | `0.01` | Smallest valid value in the assumed currency |
| `amount` | `10000000.00` | Valid at upper threshold |
| `amount` | `10000000.01` | Invalid |
| Business date | Before start date, on start date, on end date, after end date | Verify inclusive versus exclusive bounds |
| Integer | `Integer.MIN_VALUE`, `0`, `Integer.MAX_VALUE` | Handle full value range and prevent overflow |

Illustrative currency validator:

```java
import java.math.BigDecimal;

static void validateAmount(BigDecimal amount) {
    BigDecimal min = new BigDecimal("0.00");
    BigDecimal max = new BigDecimal("10000000.00");

    if (amount == null ||
        amount.compareTo(min) <= 0 ||
        amount.compareTo(max) > 0) {
        throw new IllegalArgumentException("Invalid amount");
    }
}
```

Using `BigDecimal.compareTo` gives consistent numerical comparisons, avoiding `double` precision errors at thresholds. For Unicode strings, a "20-character" rule must be defined clearly: Java's `String.length()` counts UTF-16 code units, which can differ from visible code points. If business rules count code points, the validator must count accordingly.

Also test leading/trailing whitespace, newline characters, CSV delimiters, accented characters, and BOMs (if inputs may contain them). These can cause parsers to emit blank fields or wrong column counts even when the file is non-empty.

## 8. Skip limits, retry limits, and faulty-data policies

For fault-tolerant steps, count boundaries must also test **configured limits**, not just chunk size.

Example:

```java
Step step = new StepBuilder("importStep", jobRepository)
    .<OrderRow, OrderRow>chunk(10, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(IllegalArgumentException.class)
    .skipLimit(2)
    .build();
```

With `skipLimit(2)`, at most 2 skippable errors are permitted; a 3rd error of that kind in the step exceeds the skip limit and normally fails the step. The test matrix should include:

| Configured skippable error count | Expectation |
| ---: | --- |
| 0 | Succeeds, zero skips |
| 1 | Succeeds, counts 1 skip |
| 2 | Succeeds, reaches exact allowed threshold |
| 3 | Exceeds limit, step fails |

Inspect `readSkipCount`, `processSkipCount`, or `writeSkipCount` depending on where errors occur. Do not check only total `skipCount`; per-phase counts identify whether records failed during reading, processing, or writing.

**Filter differs from skip.** Returning `null` from a processor to drop a record by business rule increments `filterCount`; it does not consume `skipLimit`. If invalid records must be reported as skips, configure the corresponding processor/exception and fault-tolerance policy.

For retry, test counts just below, right at, and past the configured attempt limit, and specify which exceptions are retryable. Check target data to prevent duplicate writes if a failed attempt already caused external side effects.

## 9. Job status on empty data is a business decision

Do not automatically treat `readCount=0` as an error. There are at least three valid policies:

| Context | Appropriate policy | Key assertion |
| --- | --- | --- |
| Daily report on a day with zero transactions | Complete normally with an empty result set | `COMPLETED`, `readCount=0`, target file/table in expected state |
| File import requiring at least one order | Report data validation failure | `FAILED` or specific business exit code, no invalid target data |
| Sync job acting only when new records exist | Write nothing and complete | `COMPLETED`, writer produces no unnecessary side effects |

To distinguish "completed with no data" from "completed after processing data", a `StepExecutionListener` can set a business `ExitStatus` like `NO_DATA` and drive conditional flows. Remember that `ExitStatus` and `BatchStatus` are distinct concepts; do not assume assigning a custom exit code automatically changes batch status to `FAILED`.

For production jobs, capture this policy as explicit test requirements: whether empty data is valid, whether an empty output file is emitted, whether alerts fire, and whether the job is restartable.

## 10. Verifying metadata and business results

To catch real defects, observe both layers.

**Spring Batch layer:** obtain `JobExecution` and `StepExecution`, and check:

```java
assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions()
    .iterator()
    .next();

assertEquals(expectedReadCount, step.getReadCount());
assertEquals(expectedFilterCount, step.getFilterCount());
assertEquals(expectedWriteCount, step.getWriteCount());
```

**Business layer:** verify inserted/updated database rows, output file contents and line counts, emitted messages, or post-processing totals. Two runs with identical output counts can still differ in content, ordering, keys, or computed values.

For instance, given input `["A", "", "B"]` with an empty-string filter policy, the right outcome is not just `writeCount=2` but the exact output `["A", "B"]`. Returning `["A", "A"]` also has 2 items yet is a business bug.

Also distinguish:

- `readCount`: items successfully read by the reader and passed into processing.
- `filterCount`: items filtered out by the processor returning `null`.
- `writeCount`: items recorded as written by the writer.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: skips per stage.
- `commitCount` and `rollbackCount`: helpful for transaction analysis, yet not the sole indicator for verifying actual output item counts.

When retries, rollbacks, or non-transactional writer side effects occur, prioritize verifying final target data state. Metadata records execution flow, which alone may not prove absence of duplicates in external systems.

## 11. Common mistakes when testing empty and boundary data

| Symptom | Common cause | Remedy |
| --- | --- | --- |
| Empty-source test still sees data | Reader kept position/fixture from prior test, or job auto-ran at startup | Create fresh reader per execution, reset fixtures, disable auto-run |
| Test passes despite missing required data | Job treats EOF as normal completion | Define empty-data policy and assert `readCount=0` |
| Cannot tell all-filtered from empty source | Asserting only `writeCount=0` | Check `readCount` and `filterCount` |
| Final record dropped | Bug in final-chunk handling, paging, or flushing | Test `chunkSize-1`, `chunkSize`, `chunkSize+1` |
| Missing file treated as empty file | Reader unexpectedly using `strict=false` | Add dedicated test for non-existent path |
| Header-only file parsed as one item | Wrong `linesToSkip` or mapper setup | Create header-only fixture and assert reader returns 0 items |
| Passes standalone but fails in suite | Shared metadata and test tables | Isolate DB or clean data between tests |
| Written row count right, data wrong | Checking counts without checking contents | Assert exact records, ordering, and boundary values |
| Wrong skip-limit test | Confusing `filterCount` with `skipCount` | Verify exception type and per-phase counts |
| Amount boundary bug | Using `double` or missing `=` in comparisons | Use `BigDecimal` and test tightly on both sides of thresholds |

## 12. Practice exercise

Build a job that reads `OrderRow(orderCode, amount)`, filters blank rows, and rejects orders with `amount <= 0` or `amount > 10000000`. The writer persists valid orders to an H2 table `accepted_orders`.

Prepare at least these datasets: 0 records; 1 valid record; 2, 3, and 4 records with chunk size 3; all-filtered rows; amounts `0`, `0.01`, `10000000.00`, and `10000000.01`; plus a missing-file case if reading from files.

For each dataset, specify upfront expectations for `BatchStatus`, `readCount`, `filterCount`, `writeCount`, row count in `accepted_orders`, and exact persisted values. If skips are enabled for valid error cases, add datasets with 0, 1, 2, and 3 faulty records under `skipLimit=2`.

To increase confidence, rerun the suite repeatedly with isolated data, then change chunk size from 3 to 5. Correctness of business outcomes must never depend on which chunk the last record lands in.

## 13. Conclusion

In Spring Batch, empty data is an input state that must be explicitly defined, while boundary data exposes bugs at chunk edges, paging limits, and business rules. Effective tests distinguish **no items to read**, **items read then filtered**, **faulty items skipped**, and **items written successfully**. Checking `StepExecution` counters alongside real output catches defects that asserting `COMPLETED` alone cannot uncover.
