# Faulty Data for Skip Testing in Spring Batch

## 1. Purpose of faulty data in skip testing

In Spring Batch, **skip** allows a Step to bypass items encountering errors classified as acceptable, continue processing remaining items, and record the skipped counts. This mechanism is typically configured in chunk-oriented processing via `faultTolerant()`, `skip(...)` or `skipPolicy(...)`, along with a `skipLimit(...)` threshold.

When testing skip behavior, what matters is not simply creating a few "broken" rows, but designing **controlled error fixtures**: knowing precisely which row must fail, which phase raises the error, which exception is thrown, how many valid items are written, and whether the job should end **`COMPLETED`** or **`FAILED`**.

For example, an order-import job reading CSV can hit three categories of faulty data:

- `quantity = abc`: cannot be parsed as an integer while reading CSV; this is a **read** error.
- `quantity = 0`: parses cleanly yet violates a business rule; this is a **process** error if the processor validates quantity.
- `order_id` collides with a unique key in the target table: reads and processes fine, yet cannot be written; this is a **write** error.

All three cases can lead to a skip, yet each requires **different fixtures, configuration, observability, and expectations**. Overly broad configuration like `skip(Exception.class)` lets tests "pass" by silently skipping system failures that ought to fail the job.

Flow to understand:

~~~text
CSV / database / message
        |
        v
      Reader  --- parse/read error -----> read skip
        |
        v
     Processor --- business error ------> process skip
        |
        v
      Writer  --- skippable write error -> write skip
        |
        v
     Valid output

          Allowed skips
                   |
                   v
      Add to Step's skip limit
                   |
          <= skipLimit ? 
             /       \
           Yes        No
            |          |
         Continue   Step FAILED
~~~

**Skip is not filter.** If `ItemProcessor.process(item)` intentionally returns `null`, the item is **filtered** and increments `filterCount`, not `processSkipCount`. Only when the processor throws an exception configured as skippable is the item counted as a process skip.

## 2. Faulty data scenarios to prepare

| Phase | Faulty data/trigger behavior | Common or custom exception | Counter to observe |
|---|---|---|---|
| Read | Non-numeric string in numeric column: `quantity=abc` | `FlatFileParseException` when line mapping error is wrapped by `FlatFileItemReader` | `readSkipCount` |
| Read | Missing required column, invalid column count | `FlatFileParseException` when tokenizer/mapper strict mode is enabled | `readSkipCount` |
| Process | Zero or negative quantity | Custom `InvalidOrderException` defined by the application | `processSkipCount` |
| Process | Customer code outside allowlist | Specific business validation exception | `processSkipCount` |
| Write | Duplicate key on DB insert | `DuplicateKeyException` or suitably translated DB exception | `writeSkipCount` if skip is enabled |
| Write | Business-tolerable constraint violation | `DataIntegrityViolationException` or specific system exception | `writeSkipCount` if skip is enabled |
| Filter | Order intentionally excluded by status | Processor returns `null` | `filterCount`, **not skip** |
| System error | DB disconnect, filesystem failure, missing config | Specific operational exception | Should typically retry with limit or FAIL |

Actual exception types depend on the reader, mapper, JDBC driver, and library version. **Tests must verify the real exception emitted**, rather than assuming every malformed CSV row becomes the same exception or every JDBC error becomes `DuplicateKeyException`.

### Properties of a good fixture

1. **Deterministic:** given the same input and test setup, the same item fails in the same phase.
2. **Expected labels:** clearly note which items are valid, parse failures, business failures, or write failures.
3. **Isolated error causes:** each item carries one primary error per test so results do not depend on check ordering.
4. **Includes valid data:** the job must continue and write valid items after skipping bad ones.
5. **Includes boundary cases:** equal to `skipLimit` and exceeding `skipLimit`.
6. **Includes output baseline:** verify the exact set of written keys and values, not just job status.
7. **Repeatable:** clean test data, use unique JobInstance parameters, and avoid depending on prior run order.

Use synthetic data; never put real customer records, tokens, or sensitive content into error fixtures or skip logs.

## 3. Sample CSV dataset for read skip and process skip

Suppose `importOrdersJob` reads a CSV file, maps rows to `RawOrder`, checks `quantity > 0` and `unitPrice > 0`, computes total amount, and writes each valid order into table `processed_order`.

File `orders-with-skips.csv`:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O002,C002,abc,7.00
O003,C003,0,25.00
O004,C004,1,11.50
O005,C005,3,4.00
~~~

Row-by-row explanation:

| `orderId` | Data | Expected outcome |
|---|---|---|
| O001 | Valid quantity and unit price | Written to output, `totalAmount=20.00` |
| O002 | `quantity=abc` unparseable | Read skip |
| O003 | `quantity=0` parses but invalid | Process skip |
| O004 | Valid | Written to output, `totalAmount=11.50` |
| O005 | Valid | Written to output, `totalAmount=12.00` |

With a reader successfully reading four items, a processor that does not filter, and each valid item producing one output, we expect:

| Metric | Expected value | Meaning |
|---|---:|---|
| Data lines in file excluding header | 5 | Physical input |
| `readCount` | 4 | O001, O003, O004, O005 read successfully |
| `readSkipCount` | 1 | O002 |
| `processSkipCount` | 1 | O003 |
| `writeSkipCount` | 0 | Writer hit no errors |
| `filterCount` | 0 | Processor never returned `null` |
| `writeCount` | 3 | O001, O004, O005 |
| `BatchStatus` with `skipLimit(2)` | `COMPLETED` | Two skips allowed |

The output key set must be **O001, O004, O005**, with a combined `totalAmount` of **43.50** (meaningful only when all share the same currency). A test checking only `writeCount=3` can still miss writing the wrong orders or wrong amounts.

**Note on `readCount`:** this counts items successfully read by the framework, not necessarily physical data lines minus header. When parsing a line fails, it may be counted toward read skips instead of `readCount`.

## 4. Configuring a Step to skip the right errors

The examples below follow Spring Batch 5+ style with `JobRepository` and `PlatformTransactionManager`. The application needs Spring Batch infrastructure, `JdbcTemplate`, and the target table configured; snippets focus on reading faulty data and skipping.

### 4.1. Data types and business exception

~~~java
import java.math.BigDecimal;

record RawOrder(
        String orderId,
        String customerId,
        int quantity,
        BigDecimal unitPrice) {
}

record ProcessedOrder(
        String orderId,
        int quantity,
        BigDecimal totalAmount) {
}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}
~~~

`InvalidOrderException` is an application-specific exception. Throw it only for data violations permitted to be skipped under business policy.

### 4.2. Reader producing observable parse errors

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("orderId", "customerId", "quantity", "unitPrice");
    tokenizer.setStrict(true);

    DefaultLineMapper<RawOrder> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fields -> new RawOrder(
            fields.readString("orderId"),
            fields.readString("customerId"),
            fields.readInt("quantity"),
            fields.readBigDecimal("unitPrice")));

    FlatFileItemReader<RawOrder> reader = new FlatFileItemReader<>();
    reader.setName("orderReader");
    reader.setResource(new FileSystemResource(inputFile));
    reader.setLinesToSkip(1);
    reader.setLineMapper(lineMapper);
    return reader;
}
~~~

On row O002, `fields.readInt("quantity")` cannot convert `abc` into an `int`. When `FlatFileItemReader` invokes the line mapper, the line-mapping failure is wrapped in `FlatFileParseException`; the skip configuration can recognize and skip that line.

`setStrict(true)` on the tokenizer enforces token counts against the schema; it **does not automatically verify header column names** because `linesToSkip(1)` simply discards the first line. Testing an invalid header requires dedicated header validation.

### 4.3. Processor raising business errors and DB writer

~~~java
import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
public ItemProcessor<RawOrder, ProcessedOrder> orderProcessor() {
    return raw -> {
        if (raw.quantity() <= 0) {
            throw new InvalidOrderException(
                    "Invalid quantity for orderId=" + raw.orderId());
        }
        if (raw.unitPrice() == null
                || raw.unitPrice().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException(
                    "Invalid unitPrice for orderId=" + raw.orderId());
        }

        BigDecimal total = raw.unitPrice()
                .multiply(BigDecimal.valueOf(raw.quantity()));
        return new ProcessedOrder(raw.orderId(), raw.quantity(), total);
    };
}

@Bean
public ItemWriter<ProcessedOrder> orderWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> {
        for (ProcessedOrder order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO processed_order
                        (order_id, quantity, total_amount)
                    VALUES (?, ?, ?)
                    """,
                    order.orderId(),
                    order.quantity(),
                    order.totalAmount());
        }
    };
}
~~~

Sample SQL schema for the test environment:

~~~sql
CREATE TABLE processed_order (
    order_id VARCHAR(50) PRIMARY KEY,
    quantity INTEGER NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL
);
~~~

This writer uses `JdbcTemplate` and participates in the chunk transaction when datasource and transaction manager are configured consistently. In real applications, add `batchId`, appropriate business key management, and idempotency rules to prevent duplicate writes on restart.

### 4.4. Step and Job with skipLimit

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ProcessedOrder>chunk(2, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(2)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

`skipLimit(2)` allows at most **two skips in this Step**, summing read, process, and write skips together. It is **not a separate limit per phase**. When a third skippable error occurs, the Step fails because the limit is exceeded. Limits on another Step do not carry over into this Step.

A job can still finish with status `COMPLETED` despite valid skips. Therefore, downstream systems should also monitor skip counters and data-quality policies instead of equating `COMPLETED` with "zero bad records".

## 5. Writing integration tests with fixed faulty data

A useful skip test must run an **actual Step or Job**, pass a fixture file, and assert across three layers: **execution status**, **counters**, and **actual output**. The example below illustrates JUnit 5, Spring Batch Test, and a Spring Boot app loading the Job configuration from section 4.

The test environment needs:

- The `spring-batch-test` dependency and Spring Boot/JUnit test libraries.
- A test database with Spring Batch metadata tables and the `processed_order` table above.
- Batch auto-execution disabled at context startup, such as `spring.batch.job.enabled=false`, so the test explicitly controls launching.
- A single matching Job for `JobLauncherTestUtils` to auto-detect, or explicit Job assignment on the utility.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderSkipIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @TempDir
    Path workDir;

    @BeforeEach
    void clearOutput() {
        // Clean the table in the dedicated DB for this test suite.
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void skipsOneReadErrorAndOneProcessError() throws Exception {
        String csv = """
                orderId,customerId,quantity,unitPrice
                O001,C001,2,10.00
                O002,C002,abc,7.00
                O003,C003,0,25.00
                O004,C004,1,11.50
                O005,C005,3,4.00
                """;

        JobExecution execution = launchWithCsv(csv);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(4L, step.getReadCount());
        assertEquals(1L, step.getReadSkipCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(0L, step.getFilterCount());
        assertEquals(3L, step.getWriteCount());

        List<String> actualIds = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);
        assertEquals(List.of("O001", "O004", "O005"), actualIds);
    }

    private JobExecution launchWithCsv(String content) throws Exception {
        Path file = workDir.resolve("orders.csv");
        Files.writeString(file, content, StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", file.toAbsolutePath().toString())
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(parameters);
    }
}
~~~

The test uses `@TempDir` to avoid sharing input files across tests and a distinct `testRun` parameter to create an isolated JobInstance. `DELETE FROM processed_order` is appropriate only for an **isolated test database**, never for shared environments or production.

For thorough data verification, add assertions on `total_amount` using `BigDecimal` and verify `O002` and `O003` are absent. If the job has multiple Steps, select the `StepExecution` by name `importOrdersStep` instead of taking the first element.

## 6. Boundary testing skipLimit: at threshold and over threshold

With `skipLimit(2)`:

| Fixture | Skippable errors | Expectation |
|---|---:|---|
| No errors | 0 | `COMPLETED`, all valid items written |
| 1 row with bad numeric type | 1 | `COMPLETED`, `readSkipCount=1` |
| 1 bad numeric row + 1 row with quantity 0 | 2 | `COMPLETED`, total skips equal to 2 |
| Above 2 errors + 1 negative unit price | 3 | `FAILED` for exceeding `skipLimit` |
| 1 non-skippable error | Could even be the very first error | `FAILED` immediately, even with remaining `skipLimit` |

Example **over-threshold** fixture:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O002,C002,abc,7.00
O003,C003,0,25.00
O004,C004,1,11.50
O005,C005,2,-4.00
O006,C006,3,4.00
~~~

O002 triggers a read skip, while O003 and O005 trigger process skips: three skippable errors in total, whereas the Step permits two. **The Step must end `FAILED`**. Because an earlier chunk may already have committed before the third error, do not blindly assert that all DB output is empty when a job ends `FAILED`.

You can add a test in the same integration test class:

~~~java
@Test
void failsWhenSkipLimitIsExceeded() throws Exception {
    String csv = """
            orderId,customerId,quantity,unitPrice
            O001,C001,2,10.00
            O002,C002,abc,7.00
            O003,C003,0,25.00
            O004,C004,1,11.50
            O005,C005,2,-4.00
            O006,C006,3,4.00
            """;

    JobExecution execution = launchWithCsv(csv);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    StepExecution step = execution.getStepExecutions()
            .iterator().next();
    assertEquals(BatchStatus.FAILED, step.getStatus());
    // Do not publish output from the failed run.
}
~~~

If the job includes a downstream Step checking output, a `READY` marker, or a publication status record, assert that **no success publication signal exists** when the import Step is `FAILED`.

## 7. Creating dedicated faulty data for write skips

Write skips are harder to test than read/process skips because the writer may operate on multiple items within the same chunk. Many JDBC writers throw errors during batch execution; the framework must isolate the offending item and may retry writing items one by one during error handling. Thus, write-skip tests need database and transaction behavior close to real deployment.

### 7.1. Duplicate-key fixture

Seed the test DB before launching:

~~~sql
INSERT INTO processed_order(order_id, quantity, total_amount)
VALUES ('O004', 1, 11.50);
~~~

Input file:

~~~csv
orderId,customerId,quantity,unitPrice
O001,C001,2,10.00
O004,C004,1,11.50
O005,C005,3,4.00
~~~

When the writer `INSERT`s into `processed_order`, O004 violates the primary key. With the right driver/dialect and Spring JDBC translation, this error maps to `DuplicateKeyException`. **The configuration in section 4 does not permit write skips**, so under that default configuration this attempt must fail the Step (`FAILED`).

To intentionally allow skipping duplicates, use a dedicated test/policy configuration approved by business rules, for example adding:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(org.springframework.dao.DuplicateKeyException.class)
.skipLimit(2)
~~~

This snippet replaces the `faultTolerant()` block in the Step; **do not chain a second `faultTolerant()` call**. If the actual driver raises `DataIntegrityViolationException` or another exception, identify the real exception type and build a targeted policy; avoid `skip(Exception.class)`.

In write-skip tests, verify `writeSkipCount`, the final output set, and key uniqueness. Since O004 already existed in the table beforehand, the final table will still contain O004; therefore **do not rely on `COUNT(*)` over the whole table to conclude how many items the writer inserted in this run**. Distinguish pre-seeded rows from newly written rows using `batchId`, audit columns, or a separate expected baseline.

### 7.2. Writer rollback considerations

When the writer shares the Step's transaction, a write failure typically triggers a chunk rollback before the framework applies its retry/skip policy. If a writer calls an external API, writes to a non-transactional file, or manages its own separate transaction, operations that succeeded before the error **are not guaranteed to roll back**. A non-idempotent writer can create duplicates while the framework attempts to isolate the failing item.

Therefore:

- For DB write errors, use a real test database or an integration environment with realistic transaction behavior.
- If write skips are enabled, verify idempotency, unique keys, and final data after rollback/retry.
- Do not use a naive `List.add(item)` mock writer to conclude that the production writer's rollback/skip handling is safe.
- If a DB error is transient (deadlock, dropped connection), consider bounded retry instead of treating the record as bad data.

## 8. Distinguishing skip, retry, filter, and fail in test design

| Mechanism | When to use | Data/behavior to test | Metrics or outcome |
|---|---|---|---|
| Skip | Permanently bad record allowed to be dropped | Invalid numbers, permitted parse errors | `readSkipCount`, `processSkipCount`, or `writeSkipCount` |
| Retry | Transient error that may succeed on re-attempt | Simulated timeout, temporarily unavailable service | Attempt count, success after retry, or FAILED/recover per policy |
| Filter | Intentionally excluding an item from the writer, not an error | Order with status excluded by business rule | `filterCount` |
| Fail | Error making results untrustworthy or disallowed from skipping | Misconfiguration, missing file, severe infra failure | `StepExecution.status=FAILED` |

Example processor filtering orders with `status=CANCELLED`:

~~~java
return raw -> {
    if ("CANCELLED".equals(raw.status())) {
        return null; // Filter: not a process skip
    }
    if (raw.quantity() <= 0) {
        throw new InvalidOrderException("Invalid quantity");
    }
    return convert(raw);
};
~~~

This example assumes a `RawOrder` model with an extra `status` field and a `convert` helper; it illustrates the distinction and is **not a drop-in replacement for the record in section 4**.

When combining retry followed by skip—for example, a writer error skipped **only after exhausting retries**—tests should verify both attempt counts and the final result. Skip counts reflect only that an item was skipped; they do not reveal how many retries happened first.

**Do not treat every writer exception as bad data.** A `SQLException` from a lost connection, a network timeout, or missing permissions is an operational signal; skipping items en masse can make a job report `COMPLETED` while losing large amounts of data.

## 9. Using SkipListener to gather evidence

To know which items were skipped and why, Spring Batch provides `SkipListener<T, S>`:

~~~java
import org.springframework.batch.core.SkipListener;

class OrderSkipLogger implements SkipListener<RawOrder, ProcessedOrder> {

    @Override
    public void onSkipInRead(Throwable error) {
        // No RawOrder yet because reading/parsing failed.
        // With FlatFileParseException, line number and safe error details
        // can be extracted.
    }

    @Override
    public void onSkipInProcess(RawOrder item, Throwable error) {
        // Log orderId, reason code, exception class.
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable error) {
        // Log orderId and write failure reason.
    }
}
~~~

Attach the listener to the fault-tolerant Step via `.listener(orderSkipLogger)` or an appropriate listener bean. For read skips, no domain item exists to extract a business key; line number details from `FlatFileParseException` are often more useful.

In real systems, store structured audit records:

~~~text
jobExecutionId = 12034
stepName       = importOrdersStep
inputFile      = orders-with-skips.csv
phase          = PROCESS
lineOrItemKey  = O003
reasonCode     = INVALID_QUANTITY
exceptionType  = InvalidOrderException
action         = SKIPPED
~~~

For read skips, the key can be the line number or record index rather than `orderId`. Avoid logging raw input lines if they contain personal or confidential data. When writing audit entries outside the transaction, account for rollbacks and callback re-invocations during error recovery to avoid duplicate events or false reports.

## 10. Reusable faulty data matrix

A dedicated fixture set per scenario keeps tests fast and root causes obvious:

| Test file/case | How the error is triggered | Expected result |
|---|---|---|
| `all-valid.csv` | All records valid | Zero skips; full output |
| `bad-integer.csv` | `quantity=abc` | Read skip if exception is permitted |
| `missing-column.csv` | Missing `unitPrice` | Read skip with strict tokenizer |
| `bad-decimal.csv` | `unitPrice=12x` | Read skip |
| `zero-quantity.csv` | `quantity=0` | Process skip |
| `negative-price.csv` | `unitPrice=-1.00` | Process skip |
| `one-bad-after-good.csv` | Faulty row placed after several valid rows | Job does not lose valid processed data |
| `one-good-after-bad.csv` | Valid row immediately follows a faulty row | Reader/processor continues cleanly |
| `exact-skip-limit.csv` | Exactly N skippable errors | Job `COMPLETED` with `skipLimit(N)` |
| `over-skip-limit.csv` | N+1 skippable errors | Job `FAILED` |
| `non-skippable.csv` | Exception outside policy | Job `FAILED` immediately |
| `duplicate-key.csv` | Input collides with key already in test DB | Write skip if configured, otherwise `FAILED` |
| `filtered.csv` | Record matches filter condition | Increments `filterCount`, not skip |
| `header-only.csv` | No data rows | No spurious skips; verify policy allows empty output |

Include at least one fixture with **two errors in different phases** to prove the skip limit is shared. Individual error files isolate failures quickly, while a mixed file verifies real behavior when multiple error types occur within the same Step.

### Testing errors at chunk boundaries

With `chunk(2)`, place faulty items:

- At the **start of the file** and just before the first commit.
- At the **end of a chunk** to observe handling right as writing starts.
- At the **start of the next chunk**, after the prior chunk has committed.
- **Consecutively**, ensuring the iterator/reader does not accidentally skip extra valid records.
- Near **EOF**, verifying no phantom items or duplicated trailing items occur.

Do not assert exact processor/writer invocation counts when fault-tolerant processing may replay items after rollback; standard Step counters and **final output** are more reliable signals.

## 11. Designing restart tests with skippable data

A restart test should model two stages:

1. Run first with a fixed fixture that skips allowable data errors, but induce a **non-skippable** error later so the job ends `FAILED` after some chunks commit.
2. Remove the operational failure cause cleanly (for example, the mocked service recovers) and restart the **same JobInstance** via Spring Batch's restart mechanism; do not modify the input fixture between runs if the reader relies on file-position checkpoints.
3. Verify the restarted run produces the exact expected final output, no duplicate keys, and skip/audit states matching the design.

Distinguish `JobInstance` from `JobExecution`: restarting the same `JobInstance` normally creates a new `JobExecution`. Never pass new identifying parameters just to call it a restart; doing so creates a brand-new `JobInstance` and defeats checkpoint verification.

For input files, data **must remain immutable** within the same `JobInstance` when using read-position checkpoints. Adding, inserting, or deleting lines between attempts can shift the recovery offset onto a different record. Use a new fixture/version and a new `JobInstance` whenever processing a modified source.

For writers targeting non-transactional external systems, tests must verify possible **at-least-once effects**, not just total skip counts. Design idempotent writers or deduplication keys before trusting restart outcomes.

## 12. Common pitfalls when creating faulty data for skips

**Faulty data does not reach the intended phase.** For example, setting `quantity=abc` to test process skip causes the reader to fail first. Fix: use `quantity=0` to pass parsing and fail in the processor.

**Only faulty items, no valid items afterward.** The test verifies skipping but never proves the job keeps processing. Fix: place valid items both before and after faulty items.

**Failing to distinguish headers from data rows.** `linesToSkip(1)` discards the header without validating header contents. Fix: add explicit schema/header validation when required by contract.

**Using `skip(Exception.class)` in tests.** This can accidentally swallow system errors and give false confidence in fault tolerance. Fix: restrict to specific exceptions and add a non-skippable test case.

**Mistaking skip limit for N per error type.** Within one Step, read/process/write skips share a single total limit. Fix: test mixed multi-phase errors.

**Using `filterCount` to assert skips.** Returning `null` from a processor is not an exception. Fix: inspect `processSkipCount` instead.

**Asserting only `COMPLETED` status.** A job can complete even while skipping bad records, potentially exceeding business quality thresholds if configured permissively. Fix: assert counters, output keys, values, and business thresholds.

**Assuming write skips always roll back cleanly everywhere.** Files, APIs, and writers managing separate transactions may retain side effects. Fix: verify transaction boundaries and idempotency.

**Re-running a fixture with identical identifying parameters on a `COMPLETED` JobInstance.** Spring Batch rejects re-running a completed instance instead of executing the test. Fix: use unique identifying `JobParameters` for independent runs; keep identifying parameters unchanged only when genuinely testing restart.

**Using production data in tests.** Sensitive data can leak into fixtures, exception messages, or CI reports. Fix: generate synthetic data with fake IDs, amounts, and customers.

## 13. How to evaluate a faulty-data skip test

A test is valuable when it clearly answers these questions via assertions or observable evidence:

1. **Which item failed and why?** Item key, error category, and triggering phase must be known upfront.
2. **Which exception was actually thrown?** Do the reader/processor/writer throw the type handled by the policy?
3. **Did the policy behave properly?** Listed errors were skipped; unlisted errors failed the job.
4. **Are the counters accurate?** Read/process/write skips and filters are not confused.
5. **Is the output set accurate?** Valid items were written accurately; faulty items caused no corrupt or duplicate data.
6. **Is the skip threshold accurate?** At the limit it continues; over the limit it ends `FAILED`.
7. **Is the job safe to operate?** Output from a failed run is never published prematurely; restarts never duplicate data.

In Spring Batch, **faulty data for skip testing is part of the fault-tolerance test contract**. Clear fixtures, tightly scoped exceptions, boundary checks around skip limits, and reconciled outputs together prove that a job skips only permitted records, continues processing good data, and fails whenever data quality or operational conditions can no longer be guaranteed.
