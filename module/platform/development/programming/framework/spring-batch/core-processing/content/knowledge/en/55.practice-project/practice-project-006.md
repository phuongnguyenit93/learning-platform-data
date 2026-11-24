# Practice Project: Handling Skipped Invalid Data with Reporting in Spring Batch

## 1. Context and Expected Outcomes

A data import job cannot always be allowed to halt because of **one** bad CSV row. For instance, a supplier sends 100,000 orders at the end of the day: 99,990 rows are valid, a few rows have negative amounts, and a few rows spell the amount in words. If the entire job is aborted over a few non-critical records, the system delays updating valid data. Conversely, if bad rows are "simply ignored" without recording errors, data will silently go missing and become hard to reconcile.

The lesson **Handling Skipped Invalid Data with Reporting** is a practice project under *Spring Batch Core Processing → Practice Projects*. We will implement a runnable and testable pipeline:

- Accept a finalized order CSV file with an immutable identifier.
- Read each line using `FlatFileItemReader`, attaching the line number to the item.
- Distinguish **read/parse errors** from **business validation errors**.
- Skip only allowed exceptions, up to a bounded total skip limit.
- Write valid items to the database using `JdbcBatchItemWriter`.
- Record each skip event into the **`batch_rejects`** table within the same database transaction as the chunk.
- When the import step succeeds, generate a text report containing read/write/skip statistics and the list of rejected lines.
- If the skip limit is exceeded, the job must become **`FAILED`**; do not try to generate a report claiming the import succeeded.
- Test exact record counts, skip counts, reports, and restart scenarios.

Examples use **Java 17, Spring Boot 3.x, Spring Batch 5.2.x, H2, and JUnit Jupiter**. In Spring Batch 6.x, APIs or packages of some components may change; check the documentation for your exact version before applying.

### After This Lesson, You Will Be Able To

1. Understand the differences among `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `filterCount`.
2. Use `.faultTolerant().skip(...).skipLimit(...)` safely.
3. Use `SkipListener` to collect error information without storing sensitive payloads.
4. Design reports based on `StepExecution` and committed reject data.
5. Explain why filesystem reports and `JobRepository` commits do not share a transaction.
6. Build restart/reconciliation strategies that neither duplicate reports nor lose error information.
7. Distinguish skippable data errors from infrastructure, transaction, or mandatory-stop errors.

---

## 2. Project Business Requirements

### 2.1. Input File

Each file represents a finalized snapshot with its own ID such as `orders-2026-11-15-v1`. CSV format:

```csv
order_id,customer_id,amount,currency
101,1001,120.50,USD
102,1002,-5.00,USD
103,1003,not_number,USD
104,1004,50.00,USD
105,1005,0.00,USD
106,1006,80.75,USD
107,1007,25.00,VND
108,1008,10.00,USD
```

Physical line numbers start at 1. Line 1 is the header, and the next eight lines are data:

| Line | order_id | Condition | Action |
|---:|---:|---|---|
| 2 | 101 | Valid | Write to target table |
| 3 | 102 | `amount=-5.00`, non-positive | Skip in processor |
| 4 | 103 | `amount=not_number`, unparseable | Skip in reader |
| 5 | 104 | Valid | Write to target table |
| 6 | 105 | `amount=0.00`, non-positive | Skip in processor |
| 7 | 106 | Valid | Write to target table |
| 8 | 107 | Valid | Write to target table |
| 9 | 108 | Valid | Write to target table |

**Expected:** 5 valid records, 3 skipped records.

### 2.2. Validation Rules

A valid row must satisfy:

- `order_id > 0`.
- `customer_id > 0`.
- `amount > 0`.
- `currency` is in the allowed list: `USD` or `VND`.

In this project, numeric conversion errors are detected in the **reader** and mapped to `FlatFileParseException`. Business rule errors are detected in the **processor** and mapped to `InvalidOrderException`.

If the reader cannot read the whole file, the database is unreachable, or the writer cannot write data, the job **must not** skip those errors under the project policy.

### 2.3. Skip Policy

- `skipLimit=3`: at most three failed items total across allowed exception types.
- Allowed errors: `FlatFileParseException` during line parsing and `InvalidOrderException` during business validation.
- Do not skip JDBC writer errors, connection drops, wrong database schemas, or unexpected exceptions.
- If a fourth error item of an allowed type is encountered, the step must fail for exceeding the threshold.
- Only errors that successfully pass through the skip mechanism are recorded as **committed rejects**.
- When the import step is `COMPLETED`, generate a report for the corresponding snapshot.
- If the import is `FAILED`, retain metadata and committed reject events for investigation; do not publish a misleading success report.

### 2.4. Required Report

A simple report file:

```text
SPRING BATCH IMPORT QUALITY REPORT
fileId=orders-2026-11-15-v1
importStatus=COMPLETED
readCount=7
writeCount=5
filterCount=0
readSkipCount=1
processSkipCount=2
writeSkipCount=0
totalSkipCount=3
persistedRejectCount=3

lineNumber,orderId,stage,errorCode,errorClass
3,102,PROCESS,NON_POSITIVE_AMOUNT,InvalidOrderException
4,,READ,PARSE_ERROR,FlatFileParseException
6,105,PROCESS,NON_POSITIVE_AMOUNT,InvalidOrderException
```

Because a parse-error line **does not produce a `RawOrder`**, `orderId` on a `READ` event may be unknown; do not manually parse and extract an ID from input already marked invalid. The report still identifies the physical line so it can be reconciled against the original file retained under security policy.

In the example, `readCount=7` because Spring Batch only counts items the reader successfully read; the parse-error line is counted separately in `readSkipCount=1`. Two items that failed validation were still returned by the reader, so they belong to `readCount` even though they were not written by the writer.

---

## 3. Application Architecture

```text
Immutable CSV / JobParameters
     │ fileId, inputFile
     ▼
FlatFileItemReader<RawOrder>
     │
     ├── Parse exception ──────┐
     │                         │
     ▼                         │
OrderValidationProcessor       │
     │                         │
     ├── InvalidOrderException ┤
     │                         │
     ▼                         ▼
JdbcBatchItemWriter       SkipListener
     │                         │
     ▼                         ▼
imported_orders           batch_rejects
     │                         │
     └────────────┬────────────┘
                  │
          same JDBC DataSource
          same chunk transaction
                  │
                  ▼
          Step importOrdersStep
          read / write / skip counts
                  │
             COMPLETED?
           ┌──────┴───────┐
           │              │
          Yes             No
           │              └──► Job FAILED;
           ▼                    metadata and committed
      reportStep                rejects remain queryable
           │
           ▼
  *.report.txt (publish atomic)
           │
           ▼
      Job COMPLETED
```

**Why not write rejects directly to a CSV file inside `SkipListener`?** Because callbacks may execute within an active committing transaction; filesystem writes do not automatically roll back with the database. If the DB rolls back after the reject file already appended a line, the report will contain "skipped errors" from a chunk that never committed. Persisting rejects to a table in the same transaction first, then exporting the report after the import step finishes, keeps consistency manageable.

### 3.1. Transaction Boundaries

In the demo, `imported_orders`, `batch_rejects`, and Spring Batch metadata use the **same H2 `DataSource` and transaction manager**. Reject data is written via `JdbcTemplate`, so it participates in the active Spring-managed transaction when sharing the same `DataSource`.

If a production deployment uses database A for `JobRepository` and database B for business output, or uses an API/file/object storage to write rejects, **never assume atomic commits across those systems**. You then need a transactional outbox, staging with idempotency keys, reconciliation, or a distributed transaction mechanism if truly needed and supported.

---

## 4. Project Structure

A reference structure:

```text
batch-quality-demo/
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/com/example/batch/
│   │   │   ├── BatchQualityApplication.java
│   │   │   └── quality/
│   │   │       ├── RawOrder.java
│   │   │       ├── ValidatedOrder.java
│   │   │       ├── InvalidOrderException.java
│   │   │       ├── OrderValidationProcessor.java
│   │   │       ├── OrderRejectSkipListener.java
│   │   │       ├── RejectReportTasklet.java
│   │   │       └── OrderQualityJobConfiguration.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── schema.sql
│   │       └── input/orders-demo.csv
│   └── test/
│       └── java/com/example/batch/
│           └── OrderQualityJobIT.java
└── build/reports/batch-quality/  (generated on run)
```

In practice, the input file is an external resource (SFTP, object storage, shared storage) passed via `JobParameters`. Files under `resources` are only for learning and test fixtures.

### 4.1. Gradle Dependencies

When a project already uses Spring Boot dependency management compatible with Spring Batch 5.2:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.4'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The plugin version in the example illustrates a Boot 3.x branch. When creating a real project, choose a supported, compatible set of versions; if dependency management resolves a Spring Batch version other than 5.2, check the Javadoc of the APIs used. Never arbitrarily mix Spring Batch 6.x with Boot 3.x.

### 4.2. Entry Point

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchQualityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchQualityApplication.class, args);
    }
}
```

The `@SpringBootApplication` annotation scans configurations in the `com.example.batch.quality` subpackage.

### 4.3. application.yml

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:quality;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
    driver-class-name: org.h2.Driver

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always

app:
  batch:
    report-directory: "./build/reports/batch-quality"
```

Explanation:

- `spring.batch.job.enabled=false` prevents auto-running the job at startup; the demo/test explicitly calls `JobLauncher`.
- The Spring Batch metadata schema is initialized for the H2 demo.
- `schema.sql` creates the two business/reject tables.
- In-memory H2 is only suitable for demos/tests; restarting after a JVM crash leaves **no DB state**, so production needs persistent metadata and business databases.
- The report directory is configured; it should be a path in an access-controlled, non-public location.
- Auto-schema creation settings are convenient for demos, not a production migration policy.

### 4.4. schema.sql

```sql
CREATE TABLE IF NOT EXISTS imported_orders (
    file_id      VARCHAR(100) NOT NULL,
    order_id     BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    amount       DECIMAL(18, 2) NOT NULL,
    currency     VARCHAR(3) NOT NULL,
    PRIMARY KEY (file_id, order_id)
);

CREATE TABLE IF NOT EXISTS batch_rejects (
    file_id      VARCHAR(100) NOT NULL,
    line_number  INTEGER NOT NULL,
    order_id     BIGINT,
    stage        VARCHAR(20) NOT NULL,
    error_code   VARCHAR(50) NOT NULL,
    error_class  VARCHAR(100) NOT NULL,
    PRIMARY KEY (file_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_batch_rejects_file
    ON batch_rejects (file_id);
```

`PRIMARY KEY (file_id, line_number)` prevents a single row of the same snapshot from getting multiple reject records even if the listener is invoked again during a retry/restart. `PRIMARY KEY (file_id, order_id)` on output prevents two valid rows from the same file and order ID from being written as two records.

Note: if there are two valid CSV rows with duplicate `order_id`, the writer will hit a database constraint error; **the demo intentionally does not skip writer errors**. To treat duplicate inputs as skippable data errors, build a dedicated validation/dedup stage before the writer or define a business policy and test it, rather than blindly adding `.skip(DuplicateKeyException.class)`.

The `MERGE INTO ... KEY(...)` SQL used in the listener below is **H2** syntax. If switching to PostgreSQL, MySQL, or Oracle, replace it with the corresponding UPSERT while preserving unique constraints and idempotency semantics.

---

## 5. Models and Exception Types

### 5.1. RawOrder.java

```java
package com.example.batch.quality;

import java.math.BigDecimal;

public record RawOrder(
        int lineNumber,
        long orderId,
        long customerId,
        BigDecimal amount,
        String currency) {
}
```

`lineNumber` is not a field in the CSV, but the physical line number received by `LineMapper` from Spring Batch. That way, when the processor detects an error, we still know which line the item came from.

### 5.2. ValidatedOrder.java

```java
package com.example.batch.quality;

import java.math.BigDecimal;

public record ValidatedOrder(
        int lineNumber,
        long orderId,
        long customerId,
        BigDecimal amount,
        String currency) {
}
```

Separating `RawOrder` and `ValidatedOrder` distinguishes an item that was **parsed but not yet business-validated** from an item that **passed validation**. In larger projects, this can map to another entity/DTO; the key point is that the writer must not receive items violating the contract.

### 5.3. InvalidOrderException.java

```java
package com.example.batch.quality;

public class InvalidOrderException extends RuntimeException {

    private final String code;

    public InvalidOrderException(String code) {
        super(code);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Using stable error codes such as `NON_POSITIVE_AMOUNT`, `INVALID_CUSTOMER_ID`, and `UNSUPPORTED_CURRENCY` makes reporting, aggregation, and reconciliation easier than dumping entire exception messages into a file.

This exception represents **an item violating a rule**. It must not be used to hide system errors such as a `NullPointerException` in the processor, a database timeout, or an algorithm bug.

---

## 6. Reader: Parsing CSV and Preserving Line Numbers

A standard `FlatFileItemReader` can be configured with `.delimited().names(...)`. However, to report line numbers when the processor detects an error, we must preserve `lineNumber` in the model. The `LineMapper<T>` interface receives both the line string and the physical line number.

Placed in `OrderQualityJobConfiguration.java`:

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> rawOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "inputFile JobParameter is required");
    }

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer(",");
    tokenizer.setNames(
            "order_id", "customer_id", "amount", "currency");
    tokenizer.setStrict(true);

    LineMapper<RawOrder> lineMapper = (line, lineNumber) -> {
        FieldSet fs = tokenizer.tokenize(line);

        return new RawOrder(
                lineNumber,
                fs.readLong("order_id"),
                fs.readLong("customer_id"),
                fs.readBigDecimal("amount"),
                fs.readString("currency"));
    };

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("rawOrderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .lineMapper(lineMapper)
            .build();
}
```

Key imports:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.LineMapper;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
```

### 6.1. How Do Parse Errors Happen?

When `fs.readBigDecimal("amount")` encounters `not_number`, mapping fails to produce a `RawOrder`. `FlatFileItemReader` wraps the error in `FlatFileParseException` along with the line number and raw input. We allow skipping **this exact error type**, so the reader can advance to the next line.

**Do not log `FlatFileParseException.getInput()` when the file contains PII/secrets.** Although the API provides raw input for diagnostics, the demo report stores only the line number and error code. When viewing original data is needed, authorized personnel can access the securely stored file version.

### 6.2. CSVs with Commas Inside Quoted Fields

`DelimitedLineTokenizer` handles many common CSV scenarios, yet real data may include quoted newlines, BOMs, alternate encodings, or other specifications. If a file has multi-line physical records, `lineNumber` from the reader may reflect a logical line marker per `RecordSeparatorPolicy`; clearly define what counts as a "failed line" in the report.

For complex contracts, use an appropriate parser/record separator and add tests for quoted commas, escaped quotes, multi-line records, headers, and encoding. Never replace it with `String.split(",")` just to save a few lines of code.

### 6.3. Why strict(true)?

`strict(true)` causes a missing required input file to fail when opening the reader. That is a **dataset-level** error, not a single bad data row allowed to be skipped.

`strict(false)` could treat a missing file as an empty source; for a mandatory data-import job, that could let the job finish `COMPLETED` with zero records, masking a file-delivery failure.

### 6.4. Files Must Be Immutable on Restart

A stateful reader saves its read position in a checkpoint. If the file is edited, or lines are inserted/deleted before the checkpoint and then restarted, the same `lineNumber` may point to a different record.

In real projects, store:

```text
fileId           = orders-2026-11-15-v1
fileVersion      = version-id-from-storage
inputSha256      = ...
expectedRows     = ...
businessDate     = 2026-11-15
schemaVersion    = 1
```

Process only files that are `READY` and unchanged. File-level validation must run before import; never treat `FlatFileParseException` as a substitute for checksums/manifests.

---

## 7. Processor: Validation Distinguished from Filtering

Create `OrderValidationProcessor.java`:

```java
package com.example.batch.quality;

import java.util.Set;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component
public class OrderValidationProcessor
        implements ItemProcessor<RawOrder, ValidatedOrder> {

    private static final Set<String> ALLOWED_CURRENCIES =
            Set.of("USD", "VND");

    @Override
    public ValidatedOrder process(RawOrder item) {

        if (item.orderId() <= 0) {
            throw new InvalidOrderException("INVALID_ORDER_ID");
        }

        if (item.customerId() <= 0) {
            throw new InvalidOrderException("INVALID_CUSTOMER_ID");
        }

        if (item.amount() == null
                || item.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "NON_POSITIVE_AMOUNT");
        }

        if (!ALLOWED_CURRENCIES.contains(item.currency())) {
            throw new InvalidOrderException(
                    "UNSUPPORTED_CURRENCY");
        }

        return new ValidatedOrder(
                item.lineNumber(),
                item.orderId(),
                item.customerId(),
                item.amount(),
                item.currency());
    }
}
```

The processor intentionally **throws a targeted exception** for bad data. There is a critical distinction:

| Behavior in ItemProcessor | Spring Batch Interpretation | Counter |
|---|---|---|
| Returns valid item | Proceed to writer | May increment `writeCount` after commit |
| Returns `null` | **Filter**, not treated as an error | `filterCount` |
| Throws `InvalidOrderException` configured for skip | **Skip** after fault tolerance accepts | `processSkipCount` |
| Throws non-skippable exception | Step fails or retries per policy | Does not increment `skipCount` for non-skippable errors |
| Throws retryable exception | Retry per configuration; may succeed or exhaust retries | Retry attempts are distinct from `skipCount` |

**Why not return `null` for negative amounts?** Because per the project requirements, invalid data must have **line-by-line error reporting**. Returning `null` causes Spring Batch to treat it as a normal filter; `SkipListener.onSkipInProcess` is not invoked to record a reject.

Filtering is appropriate when exclusion is normal business logic and should not be treated as an error—for instance, skipping orders in a status that does not require reporting. If filtered items still need tracking, use a separate mechanism rather than the skip report.

---

## 8. Writer: Writing Only Valid Items

Example `JdbcBatchItemWriter` inserting `ValidatedOrder` into `imported_orders`:

```java
@Bean
JdbcBatchItemWriter<ValidatedOrder> validOrderWriter(
        DataSource dataSource,
        @Value("#{null}") Object ignored) {

    return new JdbcBatchItemWriterBuilder<ValidatedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_orders
                    (file_id, order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?, ?)
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                // fileId is designed to be immutable per job run.
                // See the @StepScope writer version directly below.
                throw new UnsupportedOperationException(
                        "Use step-scoped writer configuration");
            })
            .build();
}
```

**In the project, use the real version below** (instead of the skeleton illustration above) to receive `fileId` from `JobParameters`. Do not declare two beans with the same name.

```java
@Bean
@StepScope
JdbcBatchItemWriter<ValidatedOrder> validOrderWriter(
        DataSource dataSource,
        @Value("#{jobParameters['fileId']}") String fileId) {

    validateFileId(fileId);

    return new JdbcBatchItemWriterBuilder<ValidatedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_orders
                    (file_id, order_id, customer_id, amount, currency)
                VALUES (?, ?, ?, ?, ?)
                """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setString(1, fileId);
                ps.setLong(2, item.orderId());
                ps.setLong(3, item.customerId());
                ps.setBigDecimal(4, item.amount());
                ps.setString(5, item.currency());
            })
            .build();
}
```

Required imports:

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
```

File ID validation method:

```java
private static void validateFileId(String fileId) {
    if (fileId == null
            || !fileId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
        throw new IllegalArgumentException(
                "Invalid fileId JobParameter");
    }
}
```

For production, extract this validation into a shared utility or value object used by the reader, listener, and reporter. `fileId` is a system-assigned logical ID, not an arbitrary user-supplied file path.

**Writer error policy in the demo:** errors such as DB connection loss, duplicate keys, constraint violations, or schema errors are **not** marked skippable. Skipping writer errors requires dedicated design because a writer can send a JDBC batch or affect external systems; a single failure in `write(Chunk)` does not automatically tell which item can be safely skipped.

---

## 9. SkipListener: Persisting Rejects to the Database

### 9.1. Why Use SkipListener?

Spring Batch provides callbacks:

- `onSkipInRead(Throwable t)`: item could not be read/parsed and was skipped.
- `onSkipInProcess(I item, Throwable t)`: item was read successfully, failed in the processor, and was skipped.
- `onSkipInWrite(O item, Throwable t)`: item failed in the writer and was skipped per policy.

`SkipListener` is invoked after the framework determines an error **is genuinely a skip**, unlike on every failed retry attempt. For a chunk-oriented step, Spring Batch attempts to guarantee that the skip callback for an item is called once and **right before the transaction commits**. That lets a callback persist rejects via JDBC in the same transaction committed/rolled back with the chunk's data.

Note that "once" here is a framework contract within a single item/transaction execution, **not system-wide exactly-once across crashes, restarts, or remote side effects**. Thus the reject table should still have a unique key and idempotent UPSERT.

### 9.2. OrderRejectSkipListener.java

```java
package com.example.batch.quality;

import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.jdbc.core.JdbcTemplate;

public class OrderRejectSkipListener
        implements SkipListener<RawOrder, ValidatedOrder> {

    private final JdbcTemplate jdbc;
    private final String fileId;

    public OrderRejectSkipListener(
            JdbcTemplate jdbc, String fileId) {
        this.jdbc = jdbc;
        this.fileId = fileId;
    }

    @Override
    public void onSkipInRead(Throwable error) {
        if (!(error instanceof FlatFileParseException parse)) {
            // Per demo config, read skip is only for parse errors.
            throw new IllegalStateException(
                    "Unexpected read skip type", error);
        }

        persist(
                parse.getLineNumber(),
                null,
                "READ",
                "PARSE_ERROR",
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            RawOrder item, Throwable error) {

        String code =
                error instanceof InvalidOrderException invalid
                    ? invalid.code()
                    : "UNKNOWN_PROCESS_ERROR";

        persist(
                item.lineNumber(),
                item.orderId(),
                "PROCESS",
                code,
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(
            ValidatedOrder item, Throwable error) {

        // The project does not configure skipping write errors.
        // If the policy changes, define item-level
        // idempotency and side-effect state before persisting.
        throw new IllegalStateException(
                "Write skip is not supported by this project", error);
    }

    private void persist(
            int lineNumber,
            Long orderId,
            String stage,
            String errorCode,
            String errorClass) {

        // MERGE ... KEY(...) is H2 syntax for the demo.
        // Write via JdbcTemplate to participate in the Spring transaction
        // when sharing the same DataSource/transactionManager with the step.
        jdbc.update("""
                MERGE INTO batch_rejects (
                    file_id, line_number, order_id,
                    stage, error_code, error_class
                )
                KEY (file_id, line_number)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                fileId,
                lineNumber,
                orderId,
                stage,
                errorCode,
                errorClass);
    }
}
```

Step-scoped listener bean:

```java
@Bean
@StepScope
OrderRejectSkipListener rejectSkipListener(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['fileId']}") String fileId) {

    validateFileId(fileId);

    return new OrderRejectSkipListener(
            jdbcTemplate, fileId);
}
```

**Explanation:**

- `onSkipInRead` receives the exception without an item; `FlatFileParseException.getLineNumber()` is the key to report the failing line.
- `onSkipInProcess` receives `RawOrder`, so it knows both the line number and order ID.
- Never write raw CSV lines or exception messages that might contain sensitive data.
- Persist only controlled `stage`, `errorCode`, and `errorClass` values.
- `MERGE` ensures repeated writes with the same `(fileId, lineNumber)` do not create extra records.
- The step-scoped bean receives the exact `fileId` for the run, avoiding mutable singleton fields colliding across concurrent jobs.
- `batch_rejects` must live in the required same datasource/transaction; if moved to another system, re-evaluate atomicity.
- Errors from `JdbcTemplate.update` itself inside the listener **must not be swallowed**. If a required reject cannot be persisted, it is better to fail than silently skip without a trace.

### 9.3. Why Not Record Raw Input?

`FlatFileParseException.getInput()` may return the full line containing names, emails, account numbers, or identifying data. A report sent broadly via internal email/chat could become a data leak.

The demo report uses file ID and line number so authorized staff can look up the original record in the securely stored snapshot. If business rules require storing raw rejected payloads, enforce encryption, access control, retention, auditing, and masking per data policy.

### 9.4. Reporting During Retries and Rollbacks

Suppose processing item 103 fails twice under retry and then succeeds on the third attempt. It is **not a skipped item**, so no reject record is created. If a skip happens in the last chunk and the transaction rolls back, rejects written in that same transaction also roll back.

With only `.skip(...)` and no `.retry(...)`, the project's two error types are handled directly as skips. With transient errors later, clearly distinguish retry attempts, eventual skips, and permanent failures.

---

## 10. Exact Step Configuration

In `OrderQualityJobConfiguration.java`, declare the import step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> rawOrderReader,
        OrderValidationProcessor orderValidationProcessor,
        JdbcBatchItemWriter<ValidatedOrder> validOrderWriter,
        OrderRejectSkipListener rejectSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ValidatedOrder>chunk(
                    3, transactionManager)
            .reader(rawOrderReader)
            .processor(orderValidationProcessor)
            .writer(validOrderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(3)
            .listener(rejectSkipListener)
            .build();
}
```

Imports:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.transaction.PlatformTransactionManager;
```

### 10.1. Why Chunk Size = 3?

Purely to observe multiple commits on the eight-row fixture. Chunk size **does not** determine the skip limit. In production, benchmark chunk size based on throughput, DB transactions, memory, and rollback cost.

### 10.2. Are Skip Limits Cumulative?

Yes. `skipLimit(3)` is the total limit across read/process/write skips for the **`StepExecution`**, not three errors per phase.

```text
readSkipCount    = 1
processSkipCount = 2
writeSkipCount   = 0
-----------------------
totalSkipCount   = 3
```

A fourth error of an allowed type exceeds the limit and causes the step to fail. If a file has 100 format errors and `skipLimit` is only 3, the job **will not** silently ignore all 100 errors.

### 10.3. Do Not Configure skip(Exception.class)

Wrong:

```java
.faultTolerant()
.skip(Exception.class)
.skipLimit(1000000)
```

This configuration easily hides DB errors, unexpected parser errors, misconfigurations, programming bugs, and resource failures. The project only allows skipping `FlatFileParseException` and `InvalidOrderException`.

For workflows with severe errors that must never be skipped even if they inherit from a broad superclass, Spring Batch also offers `noSkip(...)`. It is still best to declare an explicit whitelist and write tests for each error category.

### 10.4. Distinguishing Skip, Retry, and Filter

| Mechanism | When to Use | Behavior |
|---|---|---|
| Filter | Item is outside business scope, completely normal | Processor returns `null`; increments `filterCount` |
| Skip | Item data is invalid yet allowed to be dropped and reported | Exception is whitelisted; increments skip count |
| Retry | Transient recoverable error | Re-attempts within limit; may succeed or fail/skip |
| Fail | Exceeds threshold, non-skippable, or system error | Step/job stops with failed status |
| Quarantine | Error record needs later remediation or re-ingestion | Stores item ID/data with controls and status |

An item that succeeds on retry must not appear in the rejected items report. A normally filtered item must not be treated as a reject, unless business rules call for auditing filters via a separate channel.

---

## 11. Generating the Report After Import Succeeds

### 11.1. Why Use a Separate Step?

Generating the report directly inside `SkipListener` is prone to inconsistencies. The project's approach:

1. `importOrdersStep` processes and commits chunks, writing to both the target table and the reject table.
2. If import is `COMPLETED`, run `reportStep`.
3. `reportStep` pulls counters from the import step's metadata, reads reject rows from the database, reconciles total skips against reject counts, and writes a temporary file.
4. Only after the file is complete is it moved to the official report name.
5. If the report step fails, the job becomes `FAILED` even though the import finished; restarting the same `JobInstance` can re-run the report part without re-running the already-`COMPLETED` import step.

This policy makes the **report a mandatory output** of the job, not merely a best-effort log.

### 11.2. Report Format

The text report contains a `key=value` summary and a CSV list of rejected lines at the bottom, as in Section 2.4. Data in rejected lines is whitelisted to exclude raw PII. The report file name derives from a validated `fileId`:

```text
build/reports/batch-quality/orders-2026-11-15-v1.report.txt
```

Never insert arbitrary path values from `JobParameters` into the report file name, avoiding path traversal or overwriting system files.

### 11.3. RejectReportTasklet.java

```java
package com.example.batch.quality;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.jdbc.core.JdbcTemplate;

public class RejectReportTasklet implements Tasklet {

    private final JobExplorer explorer;
    private final JdbcTemplate jdbc;
    private final Path reportRoot;
    private final String fileId;

    public RejectReportTasklet(
            JobExplorer explorer,
            JdbcTemplate jdbc,
            Path reportRoot,
            String fileId) {

        this.explorer = Objects.requireNonNull(explorer);
        this.jdbc = Objects.requireNonNull(jdbc);
        this.reportRoot = Objects.requireNonNull(reportRoot);
        this.fileId = Objects.requireNonNull(fileId);

        if (!fileId.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,99}")) {
            throw new IllegalArgumentException("Invalid fileId");
        }
    }

    public record RejectedLine(
            int lineNumber,
            Long orderId,
            String stage,
            String errorCode,
            String errorClass) {}

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        JobInstance jobInstance = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution()
                .getJobInstance();

        // Do not read only the current JobExecution:
        // reportStep may restart after importStep already
        // COMPLETED in a previous JobExecution.
        StepExecution importStep = explorer
                .getJobExecutions(jobInstance)
                .stream()
                .flatMap(job -> job.getStepExecutions().stream())
                .filter(step ->
                        step.getStepName().equals("importOrdersStep"))
                .filter(step ->
                        step.getStatus() == BatchStatus.COMPLETED)
                .max(Comparator.comparing(
                        step -> step.getId() == null
                                ? -1L : step.getId()))
                .orElseThrow(() -> new IllegalStateException(
                        "No completed importOrdersStep for jobInstance"));

        List<RejectedLine> rejects = jdbc.query("""
                SELECT line_number, order_id, stage,
                       error_code, error_class
                FROM batch_rejects
                WHERE file_id = ?
                ORDER BY line_number
                """,
                (rs, n) -> new RejectedLine(
                        rs.getInt("line_number"),
                        rs.getObject("order_id", Long.class),
                        rs.getString("stage"),
                        rs.getString("error_code"),
                        rs.getString("error_class")),
                fileId);

        if (rejects.size() != importStep.getSkipCount()) {
            throw new IllegalStateException(
                    "Reject count does not match StepExecution skipCount");
        }

        StringBuilder report = new StringBuilder(2048);
        report.append("SPRING BATCH IMPORT QUALITY REPORT\n");
        report.append("fileId=").append(fileId).append('\n');
        report.append("generatedAtUtc=")
                .append(Instant.now()).append('\n');
        report.append("importStatus=")
                .append(importStep.getStatus()).append('\n');
        report.append("readCount=")
                .append(importStep.getReadCount()).append('\n');
        report.append("writeCount=")
                .append(importStep.getWriteCount()).append('\n');
        report.append("filterCount=")
                .append(importStep.getFilterCount()).append('\n');
        report.append("readSkipCount=")
                .append(importStep.getReadSkipCount()).append('\n');
        report.append("processSkipCount=")
                .append(importStep.getProcessSkipCount()).append('\n');
        report.append("writeSkipCount=")
                .append(importStep.getWriteSkipCount()).append('\n');
        report.append("totalSkipCount=")
                .append(importStep.getSkipCount()).append('\n');
        report.append("persistedRejectCount=")
                .append(rejects.size()).append("\n\n");

        report.append(
                "lineNumber,orderId,stage,errorCode,errorClass\n");
        for (RejectedLine reject : rejects) {
            // Stage/code/class strings are application-generated;
            // do not write raw input/messages into the report file.
            report.append(reject.lineNumber()).append(',');
            if (reject.orderId() != null) {
                report.append(reject.orderId());
            }
            report.append(',')
                    .append(reject.stage()).append(',')
                    .append(reject.errorCode()).append(',')
                    .append(reject.errorClass()).append('\n');
        }

        Path directory = reportRoot.toAbsolutePath().normalize();
        Files.createDirectories(directory);

        Path target =
                directory.resolve(fileId + ".report.txt").normalize();

        // fileId is whitelisted; still verify it does not escape root.
        if (!target.getParent().equals(directory)) {
            throw new IOException("Report path escapes root");
        }

        Path temporary = Files.createTempFile(
                directory, ".quality-report-", ".tmp");

        try {
            Files.writeString(
                    temporary,
                    report.toString(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            // Demo targets a filesystem supporting atomic move.
            // If unsupported, fail to avoid publishing a half-written file.
            Files.move(temporary, target,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }

        return RepeatStatus.FINISHED;
    }
}
```

### 11.4. Boundaries of the Report Step

- `ATOMIC_MOVE` prevents consumers from reading a partially written file **if the filesystem truly supports it**. Behavior when the target exists varies by provider/filesystem; production should verify atomic replacement or use immutable report objects + manifests.
- The report file resides outside the database transaction. If publishing the file succeeds yet `reportStep`'s metadata commit fails, restarting may overwrite the report. Regenerating **the same file name** manages idempotency for the demo report, whereas externally distributed reports need manifest/version/conditional publishing.
- `generatedAtUtc` changes when a report is regenerated. If byte-identical reports are required, take the timestamp from a persistently stored milestone instead of `Instant.now()`, or version the report.
- With a very large skip limit, `StringBuilder` holds the entire report in memory; production should stream each reject row with a `BufferedWriter` instead of loading everything into a list. The demo uses `skipLimit=3`, keeping the report bounded.
- If the filesystem does not support atomic move, the tasklet fails; never silently fall back to non-atomic publishing when atomicity is a business requirement.
- If the report step finishes yet notifications (email/messages) fail, notifications also need idempotency or an outbox; do not re-launch the entire import by default.

### 11.5. Report Step Bean

```java
@Bean
@StepScope
RejectReportTasklet rejectReportTasklet(
        JobExplorer explorer,
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['fileId']}") String fileId,
        @Value("${app.batch.report-directory}")
                String reportDirectory) {

    return new RejectReportTasklet(
            explorer,
            jdbcTemplate,
            Path.of(reportDirectory),
            fileId);
}

@Bean
Step reportStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        RejectReportTasklet rejectReportTasklet) {

    return new StepBuilder("reportStep", repository)
            .tasklet(rejectReportTasklet, transactionManager)
            .build();
}
```

Imports:

```java
import java.nio.file.Path;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.jdbc.core.JdbcTemplate;
```

### 11.6. What If Import Fails Before Reporting?

With the default sequential flow, `reportStep` **does not run** when `importOrdersStep` is `FAILED`. This is an explicit decision: **do not publish a completion report for a failed import**.

However, we still retain:

- `JobExecution`/`StepExecution` metadata, status, and exit description.
- Records in `batch_rejects` already committed in earlier chunks.
- Valid records already committed to `imported_orders` before the failure.

A runbook can run queries to assemble a separate **incident report**. If always generating a report file even on failure is required, design a conditional flow with a dedicated reporting step and ensure the **final job status remains `FAILED`**; never accidentally turn a failure into `COMPLETED` just because the reporting step succeeded. This responsibility can also be moved to an independent reporting workflow reading `JobExplorer` and committed reject data.

---

## 12. Assembling the Job: Import Then Report

In `OrderQualityJobConfiguration.java`:

```java
@Bean
Job ordersQualityJob(
        JobRepository repository,
        Step importOrdersStep,
        Step reportStep) {

    return new JobBuilder("ordersQualityJob", repository)
            .start(importOrdersStep)
            .next(reportStep)
            .build();
}
```

The beans were presented section by section. Top of the configuration file:

```java
package com.example.batch.quality;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.LineMapper;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class OrderQualityJobConfiguration {
    // Place the @Bean methods from sections 6, 8, 9, 10, 11, and 12 here.
    // Use ONLY ONE version of each bean.
}
```

### 12.1. Execution Lifecycle

```text
Start ordersQualityJob
          │
          ▼
    importOrdersStep
          │
    ┌─────┴──────┐
    │            │
 COMPLETED      FAILED
    │            │
    ▼            ▼
 reportStep     Stop Job
    │          status FAILED
 ┌──┴─────┐
 │        │
COMPLETED FAILED
 │        │
 ▼        ▼
Job       Job
COMPLETED FAILED
```

On restarting the same `JobInstance`, a step already `COMPLETED` in the repository is normally **skipped** unless configured to re-run. Thus, if the report step fails after the import succeeds, restarting may only need to run the report step. In this project, the reporter reads import metadata from previous `JobExecution`s of the same `JobInstance` to support that case.

---

## 13. Running with the CSV Fixture

### 13.1. JobParameters

To invoke the job manually from a controller, command runner, or integration test:

```java
JobParameters params = new JobParametersBuilder()
        .addString(
                "fileId",
                "orders-2026-11-15-v1",
                true)
        .addString(
                "inputFile",
                "/data/ready/orders-2026-11-15-v1.csv",
                false)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(ordersQualityJob, params);
```

Meaning:

- `fileId` is an identifying parameter: one logical snapshot corresponds to one `JobInstance`.
- `inputFile` is a controlled read location; it is non-identifying in the demo.
- In production, `fileId` must be tied to an immutable object version and checksum; never allow one `fileId` to point to different content on restart.
- Never add a random timestamp as an identifying parameter just to "force a re-run": that creates a different `JobInstance` and bypasses the restart history of the old snapshot.

For exercises wanting to re-run with a new input set, issue a new `fileId` or reset the test environment via an approved procedure. If an instance is already `COMPLETED`, calling it again with the same identifying parameters is normally rejected with `JobInstanceAlreadyCompleteException`.

### 13.2. Expected Results

After the job is `COMPLETED`:

```sql
SELECT file_id, order_id, customer_id, amount, currency
FROM imported_orders
WHERE file_id = 'orders-2026-11-15-v1'
ORDER BY order_id;
```

Logical results:

| order_id | customer_id | amount | currency |
|---:|---:|---:|---|
| 101 | 1001 | 120.50 | USD |
| 104 | 1004 | 50.00 | USD |
| 106 | 1006 | 80.75 | USD |
| 107 | 1007 | 25.00 | VND |
| 108 | 1008 | 10.00 | USD |

Query rejects:

```sql
SELECT file_id, line_number, order_id, stage, error_code
FROM batch_rejects
WHERE file_id = 'orders-2026-11-15-v1'
ORDER BY line_number;
```

Logical results:

| line_number | order_id | stage | error_code |
|---:|---:|---|---|
| 3 | 102 | PROCESS | NON_POSITIVE_AMOUNT |
| 4 | null | READ | PARSE_ERROR |
| 6 | 105 | PROCESS | NON_POSITIVE_AMOUNT |

The `StepExecution` of `importOrdersStep` will show:

```text
readCount        = 7
writeCount       = 5
filterCount      = 0
readSkipCount    = 1
processSkipCount = 2
writeSkipCount   = 0
skipCount        = 3
BatchStatus      = COMPLETED
```

These numbers hold for **the fixture with no other errors and no additional retries/skips**. Never derive `readCount` for every project as "line count minus errors," because readers can skip comments/headers, filter, apply custom record separation, or use other reading logic.

### 13.3. Guarding Report Accuracy

The report step reconciles `rejects.size()` against `importStep.getSkipCount()`. If the two numbers differ, the tasklet fails instead of publishing an inconsistent report. This catches cases where the listener failed to persist rejects, a wrong `fileId` was used, reject data was tampered with, or transaction configuration was wrong.

A production version can also reconcile:

```text
expectedDataRows =
    successfulReadItems
  + readParseRejectedItems
  + record types ignored per contract (comments/headers...)

successfulReadItems =
    writeCount
  + processSkipCount
  + filterCount
  + item types not written per design
```

Depending on retries, writer skips, multiple outputs, and custom processors, the reconciliation formula must be defined accurately for each job. Never turn an illustrative formula into a universal Spring Batch invariant.

---

## 14. Integration Testing with spring-batch-test

### 14.1. Why Test the Whole Job?

Unit testing `OrderValidationProcessor` alone confirms negative amounts throw an exception, yet does not prove Spring Batch:

- Caught `FlatFileParseException` during the read phase.
- Invoked `onSkipInRead` with the right line number.
- Skipped exactly three times across the whole `StepExecution`.
- Committed valid records and rejects in the same transaction.
- Ran `reportStep` after import completed.
- Failed the job when exceeding `skipLimit`.
- Preserved metadata and restart semantics.

`spring-batch-test` provides `@SpringBatchTest` and `JobLauncherTestUtils` to run tests against a real `JobRepository`.

### 14.2. Integration Test Example

```java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(
        classes = BatchQualityApplication.class)
class OrderQualityJobIT {

    @Autowired
    JobLauncherTestUtils jobs;

    @Autowired
    JdbcTemplate jdbc;

    @TempDir
    Path temporaryDirectory;

    @Test
    void skipsThreeInvalidRowsAndWritesReport() throws Exception {

        String fileId = "test-" + UUID.randomUUID();

        Path csv = temporaryDirectory.resolve("orders.csv");
        Files.writeString(csv, """
                order_id,customer_id,amount,currency
                101,1001,120.50,USD
                102,1002,-5.00,USD
                103,1003,not_number,USD
                104,1004,50.00,USD
                105,1005,0.00,USD
                106,1006,80.75,USD
                107,1007,25.00,VND
                108,1008,10.00,USD
                """, StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("fileId", fileId, true)
                .addString("inputFile", csv.toString(), false)
                .toJobParameters();

        JobExecution execution = jobs.launchJob(params);

        assertEquals(
                BatchStatus.COMPLETED, execution.getStatus());

        StepExecution importStep = execution
                .getStepExecutions()
                .stream()
                .filter(s -> s.getStepName()
                        .equals("importOrdersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(7L, importStep.getReadCount());
        assertEquals(5L, importStep.getWriteCount());
        assertEquals(0L, importStep.getFilterCount());

        assertEquals(1L, importStep.getReadSkipCount());
        assertEquals(2L, importStep.getProcessSkipCount());
        assertEquals(0L, importStep.getWriteSkipCount());
        assertEquals(3L, importStep.getSkipCount());

        Long imported = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM imported_orders
                WHERE file_id = ?
                """,
                Long.class, fileId);

        Long rejected = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM batch_rejects
                WHERE file_id = ?
                """,
                Long.class, fileId);

        assertEquals(5L, imported);
        assertEquals(3L, rejected);

        Path report = Path.of(
                "build/reports/batch-quality",
                fileId + ".report.txt");

        String content = Files.readString(
                report, StandardCharsets.UTF_8);

        assertTrue(content.contains("writeCount=5"));
        assertTrue(content.contains("totalSkipCount=3"));
        assertTrue(content.contains(
                "4,,READ,PARSE_ERROR,FlatFileParseException"));
    }
}
```

**Test environment notes:**

- `@SpringBatchTest` creates test utilities; so `JobLauncherTestUtils` knows which job to run, the demo context has only one primary job. If multiple jobs exist, select the specific job in setup.
- `spring.batch.job.enabled=false` prevents the job from auto-running when the application context starts.
- The report path in the assertion matches `app.batch.report-directory` from the demo YAML. In real CI, use a separate report directory per test (such as via dynamic properties) to avoid collisions when running in parallel.
- `fileId` differs per test so unique keys/`JobInstance`s do not collide across test runs.
- The lesson illustrates tests rather than results already executed in this environment.

### 14.3. Testing Exceeding the Skip Limit

Add a fourth business-invalid row, for example:

```csv
109,1009,-1.00,USD
```

Expected:

- The import step becomes `FAILED` due to too many skippable errors.
- The job becomes `FAILED`.
- `reportStep` does not run under the default sequential flow.
- Reject rows already committed in earlier chunks may still exist; do not assume all four errors exist in the reject table.
- Valid records in chunks committed prior to failure may also remain in the target table.
- Metadata reflects that the skip limit was exceeded; the runbook must handle the invalid file version.

**Do not hard-assert that reject count equals 4 when the job is `FAILED`.** The limit-exceeding event can cause the chunk to roll back; errors committed in previous chunks are the reliable source of truth in `batch_rejects`.

### 14.4. Testing a Non-Skippable Writer Exception

Intentionally create two valid rows sharing the same `order_id` in one file, or use a writer throwing `DataIntegrityViolationException`. Because the policy only allows skipping parse/business validation errors, expect:

- Job `FAILED`.
- No "pretend-skipped" `WRITE` reject event.
- No success report published.
- Serious DB errors are not ignored just to obtain a completed status.

In production, a duplicate business key may be considered a handleable data error; in that case, define duplicate handling **before the writer** or build an idempotent writer with clear rules, rather than treating every database constraint error as skippable.

---

## 15. Unit Testing the Processor and Listener

### 15.1. Processor

```java
class OrderValidationProcessorTest {

    private final OrderValidationProcessor processor =
            new OrderValidationProcessor();

    @Test
    void rejectsNonPositiveAmount() {
        RawOrder input = new RawOrder(
                3, 102L, 1002L,
                new BigDecimal("-5.00"), "USD");

        InvalidOrderException error = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals("NON_POSITIVE_AMOUNT", error.code());
    }

    @Test
    void rejectsUnknownCurrency() {
        RawOrder input = new RawOrder(
                5, 104L, 1004L,
                new BigDecimal("10.00"), "XXX");

        assertEquals(
                "UNSUPPORTED_CURRENCY",
                assertThrows(
                        InvalidOrderException.class,
                        () -> processor.process(input)).code());
    }

    @Test
    void acceptsValidOrder() throws Exception {
        RawOrder input = new RawOrder(
                2, 101L, 1001L,
                new BigDecimal("120.50"), "USD");

        ValidatedOrder output = processor.process(input);

        assertEquals(101L, output.orderId());
        assertEquals(2, output.lineNumber());
    }
}
```

Key imports come from JUnit Jupiter, `BigDecimal`, and models in the same package. These tests guarantee business validation, yet do not replace integration tests for the skip limit.

### 15.2. Listener

You can mock `JdbcTemplate` and call `onSkipInProcess` with `RawOrder`, asserting that the SQL is called with the right `fileId` and `lineNumber`. For `onSkipInRead`, create a mock `FlatFileParseException` with a line number and verify the report payload never pulls directly from `getInput()`.

Test with a real database to confirm `MERGE` works and reject writes participate in the transaction. Mockito only proves the code calls an API, not atomicity.

### 15.3. Transaction Rollback Test

An integration test can make the writer fail in a chunk that already had a skip callback. After rollback, verify reject records belonging to that chunk were not persisted when the shared transaction rolled back. Then re-run with the error fixed and verify no duplicate reject rows are produced.

Understand chunk boundaries and skip-callback timing for the Spring Batch version under test. Never write tests assuming `SkipListener` is invoked at the exact moment the first exception is thrown.

---

## 16. Restart and Idempotency

### 16.1. Completed Step vs. Failed Step

In the demo flow:

- If `importOrdersStep` completes and `reportStep` fails: restarting the same `JobInstance` typically skips the already-completed import and re-runs the report. The reporter uses `JobExplorer` to query import metadata from previous `JobExecution`s of the same instance.
- If `importOrdersStep` fails due to exceeding the skip limit: you cannot simply restart with the same content and same policy expecting the job to succeed; you must fix the data or make a controlled business policy change.
- If `importOrdersStep` fails because the database is temporarily unavailable: fixing the dependency and restarting can resume from the checkpoint, depending on reader/writer state.
- If the input file changes during downtime: the reader checkpoint may no longer align, so never silently restart with a new version.

### 16.2. Unique Key for Reject Reporting

`batch_rejects` uses `(file_id, line_number)`. With an immutable file snapshot, the same line keeps the same meaning across restarts. If you keep `fileId` while altering file content, this unique key will **overwrite or mix reports from two snapshots**. Therefore, file ID/version/checksum is a mandatory contract, not merely a naming choice.

### 16.3. Unique Key for Output

`imported_orders` uses `(file_id, order_id)`. If a chunk wrote to the database yet the client missed the commit response before a crash, a restart can hit a duplicate key. Correctness requires proper transaction boundaries and writer idempotency:

- If duplicate business keys are an error, fail and investigate.
- If replaying the same record is allowed, implement an UPSERT/conditional write verifying unchanged data.
- Never blindly skip all `DuplicateKeyException`s, as that can mask two distinct records sharing an ID.
- For remote APIs or file outputs, design outboxes/atomic publishing and separate reconciliation.

### 16.4. Reports Must Also Be Idempotent

`RejectReportTasklet` writes a temporary file and atomically moves it to a `fileId`-based name. If the DB committed the import yet the report wasn't written, restarting can regenerate the report without importing data twice.

However, emailing/uploading the report to a third party might succeed and then time out on the client. Even if only one internal report file exists, the recipient could receive two notifications. Use correlation IDs, unique report versions, or an outbox to coordinate notifications.

### 16.5. Retention Policy

Do not delete the original CSV immediately after the job completes if you still need to reconcile rejected lines, audit, reprocess, or investigate. Retain:

- `fileId`/object version/checksum;
- schema version;
- `businessDate` and applied timezone;
- `JobExecution` results;
- reports and rejected lines;
- retention/cleanup period;
- who is authorized to view the original file or error report.

For personal data, reports should store only necessary metadata and enforce access control.

---

## 17. Statistics Tables and Reconciliation SQL

### 17.1. Output Records per File

```sql
SELECT file_id, COUNT(*) AS imported_count
FROM imported_orders
GROUP BY file_id
ORDER BY file_id;
```

### 17.2. Errors by Stage and Error Code

```sql
SELECT file_id, stage, error_code,
       COUNT(*) AS rejected_count
FROM batch_rejects
GROUP BY file_id, stage, error_code
ORDER BY file_id, stage, error_code;
```

For the fixture:

```text
READ    PARSE_ERROR         1
PROCESS NON_POSITIVE_AMOUNT 2
```

### 17.3. Querying Reject Events by Line

```sql
SELECT line_number, order_id, stage, error_code
FROM batch_rejects
WHERE file_id = ?
ORDER BY line_number;
```

### 17.4. Do Not Equate Every Count

Counters have different scopes:

| Metric | Meaning |
|---|---|
| `readCount` | Items returned successfully by the reader and recorded as read |
| `readSkipCount` | Read errors that were skipped |
| `processSkipCount` | Processing errors that were skipped |
| `writeSkipCount` | Write errors that were skipped |
| `filterCount` | Processor returned `null` per filter logic |
| `writeCount` | Items recorded as written by the writer |
| `rollbackCount` | Recorded rollback count |
| `commitCount` | Recorded commit count |
| `skipCount` | Sum of read/process/write skip counts |

A job with `writeCount=5` and `skipCount=3` **does not** prove the input had only eight lines if the reader also skipped headers, comments, filtered items, or applied special rules. Therefore, you need a manifest/expected count and reconciliation checks per the data contract.

### 17.5. Total Skip Rate

If KPIs require an error rate:

```text
skipRate = committedSkipCount /
           (successfulInputItems + readRejectedItems)
```

In the demo:

```text
successfulInputItems = readCount = 7
readRejectedItems    = readSkipCount = 1

skipRate = 3 / (7 + 1) = 37.5%
```

This is the error rate over total **data records attempted to be read**, which differs from the error rate over only records written by the writer. For pipelines with filtering, streaming, or multiple resources, clearly define the denominator. If the input source has a manifest count, reconcile directly against the manifest's expected count.

---

## 18. Monitoring and Alerting

### 18.1. Recommended Metrics

| Metric | Source | Purpose |
|---|---|---|
| Job status/duration | Spring Batch metadata/Micrometer | Job completed/failed and duration |
| `readSkipCount` | `StepExecution` | Parse/reader errors |
| `processSkipCount` | `StepExecution` | Business validation errors |
| `writeSkipCount` | `StepExecution` | Writer errors skipped per policy |
| `filterCount` | `StepExecution` | Items excluded by filter |
| Rejects by `errorCode` | Query `batch_rejects` | Top data-import errors |
| Report status | `JobExecution`/`reportStep` | Whether the report was published |
| Input count/checksum | Manifest/validation | Whether the file has complete data |
| Quarantine backlog | Table/ticket/workflow | Errors still awaiting remediation |
| Skip rate by partner | Custom metric (low-cardinality) | Source data quality |

Do not put per-record `fileId`/`customerId`/`orderId` into per-item metric labels, as that creates huge time-series cardinality and can leak data. Keep specific IDs in an access-controlled audit store with internal links to incidents.

### 18.2. Alert Thresholds

Example policy:

- **Warning:** `skipRate` exceeds 1% in a period, yet the job still completes.
- **Critical:** `skipRate` exceeds 5%, impacting SLAs or mandatory reports.
- **Critical:** job `FAILED` due to exceeding skip limit or writer/database errors.
- **Warning/Critical:** `reportStep` failed or report not published before deadline.
- **Critical:** manifest count and total data records do not match.

The 1% and 5% figures are illustrative only. True thresholds must come from source data quality, data type, and business commitments. For payment data, even a single skipped row may require urgent handling.

### 18.3. Safe Logging

Structured log:

```text
event=BATCH_RECORD_REJECTED
fileId=orders-2026-11-15-v1
jobExecutionId=701
step=importOrdersStep
lineNumber=4
stage=READ
errorCode=PARSE_ERROR
```

Never log raw CSV lines, credentials, account numbers, or serialized `ExecutionContext`. If debugging raw lines is needed, provide an access-controlled tool to query the original file with proper role checks and auditing.

### 18.4. Runbook When Skips Spike Unexpectedly

1. Identify `fileId`/snapshot/partner/`businessDate` and expected total records.
2. Inspect `StepExecution`, `readSkipCount`/`processSkipCount`/`writeSkipCount`.
3. Query reject events by `errorCode` and line number.
4. Check whether schema, encoding, upstream mapping, or validation policies changed.
5. If the issue is at the source, request a new file version or follow a controlled correction workflow.
6. Never delete reject rows or bump `skipLimit` just to turn the job green.
7. Reconcile output by business keys, amounts, report status, and downstream impact.
8. Record incident findings, corrections, and reprocessing if needed.

---

## 19. When Is Skipping a Record Allowed?

This is a **business decision**, not merely a Spring Batch configuration.

| Data Type | Example Error | Typical Policy Considered |
|---|---|---|
| Optional marketing import | Missing optional phone number | Skip and report |
| Statistical analytics logs | A few malformed lines | Skip with threshold and audit |
| Reference data | Unknown optional field | Filter/skip per contract |
| Payroll/tax | Wrong amount or receiving account | May fail/quarantine; requires fix and reconciliation |
| Payments/settlement | One unparseable transaction | Usually must not silently skip |
| Identity/authorization | Mismatched customer code | Risk-dependent; usually must prevent bad ingestion |
| Source DB failure | Deadlock/connection timeout | Retry/fail; do not treat as bad item data |
| Writer unique-key error | Possible duplicate from replay or real input | Analyze before deciding idempotent write/skip |

The demo allows skipping three errors to learn the framework. For data requiring 100% completeness, the design may choose `skipLimit(0)` or fail on any invalid data while generating an incident report in a separate workflow.

### 19.1. Why Not Increase `skipLimit` by a Simple Percentage?

A 1-million-row file with 1% errors means 10,000 dropped records. That figure may be huge in monetary value or customer impact. Consider simultaneously:

- Absolute limit, e.g., no more than N errors.
- Percentage limit over total rows.
- Error types with different severity levels.
- Aggregate business value of the failing records.
- Ability to remediate and reprocess within SLA.

Spring Batch's `skipLimit` caps total skipped items, not a percentage. If a percentage is needed, add a validation/policy step or custom `SkipPolicy`; avoid logic relying on a denominator unknown until the end of the file.

---

## 20. Extension: Error-Code-Based SkipPolicy

When there are many error types, `.skip(ExceptionClass.class)` can be too coarse. For example, only certain `InvalidOrderException` codes may be skipped, while `INVALID_ORDER_ID` must fail immediately.

A custom `SkipPolicy`:

```java
public final class OrderSkipPolicy implements SkipPolicy {

    private final int maximum;

    public OrderSkipPolicy(int maximum) {
        this.maximum = maximum;
    }

    @Override
    public boolean shouldSkip(
            Throwable error, long skipCount) {

        // Framework may invoke with negative skipCount when classifying.
        boolean eligible = false;

        if (error instanceof FlatFileParseException) {
            eligible = true;
        } else if (error instanceof InvalidOrderException invalid) {
            eligible = !invalid.code()
                    .equals("INVALID_ORDER_ID");
        }

        return eligible
                && (skipCount < 0 || skipCount < maximum);
    }
}
```

Usage:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy(3))
```

**Important:** When using a custom `SkipPolicy`, check the Javadoc and behavior for your Spring Batch version, especially how the framework calls `shouldSkip` with `skipCount < 0` purely to classify an exception. The policy must separate checking **skippable error type** from **skip threshold**, avoiding returning `false` during classification and altering expected behavior.

Do not combine multiple policies without understanding precedence among `skip(...)`, `noSkip(...)`, and `skipPolicy(...)`. Keep one primary policy source and test both thresholds and non-skippable errors.

### 20.1. Multiple Severity Levels

One refinement:

```text
InvalidOrderException
  ├─ UNSUPPORTED_CURRENCY  → SKIP + report
  ├─ NON_POSITIVE_AMOUNT   → SKIP + report (demo)
  ├─ INVALID_CUSTOMER_ID   → FAIL if identity data is critical
  └─ INVALID_ORDER_ID      → FAIL
```

These decisions must be approved by the business owner. Never assume every validation error is minor.

---

## 21. Extension: Retry with Timeouts and Writer Failures

### 21.1. Do Not Equate Retry with Skip

Remote API or DB timeout errors may be transient, unlike `amount=-5.00`, which will not become valid after a few retries.

Principle example:

```java
.faultTolerant()
.retry(TransientRemoteException.class)
.retryLimit(3)
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(3)
```

`TransientRemoteException` here is an exception from another integration, **not part of the current demo project**. If adding remote calls, include proper timeouts, backoff, rate limiting, and idempotency. Never retry all `RuntimeException`s.

### 21.2. Skipping in ItemWriter Is More Complex

A `JdbcBatchItemWriter` sends multiple SQL rows in a chunk. When a batch insert fails on a constraint, the framework may execute rollbacks/retries to isolate the failing item under the fault-tolerant algorithm, yet outcomes depend on transactions, drivers, business rules, and writer design.

If the writer sends emails or HTTP POSTs before an exception:

- Side effects may already have occurred.
- Local database rollback does not retract emails or HTTP calls.
- Retrying/skipping can create duplicate side effects.
- No "skip one item" mechanism guarantees exactly-once automatically.

Therefore, the demo **does not configure skipping writer errors**. If duplicate orders must be handled, pre-validate, use business unique keys, and implement an upsert/idempotent writer per contract.

### 21.3. Backoff and Retry Budgets

For transient errors, bound attempts, total elapsed time, and backoff. If each HTTP request times out after 5 seconds and retries three attempts with backoff, a single item can take over 15 seconds. With a chunk size of 1,000, holding a transaction for many minutes can degrade DB performance and miss SLAs. Separate retries into the right layer and avoid nested retry policies that multiply request counts.

---

## 22. Recommended Test Suite and Failure Scenarios

| Scenario | Expected |
|---|---|
| 100% valid file | No rejects, report `skip=0`, job `COMPLETED` |
| One unparseable amount line | `readSkipCount=1`, `READ` reject recorded |
| One negative amount line | `processSkipCount=1`, `PROCESS` reject recorded |
| Three errors, limit 3 | `COMPLETED`, `reject=3`, accurate report |
| Four errors, limit 3 | `FAILED`, no success report published |
| Missing file | `FAILED` on opening reader, not skipped |
| Empty file with header | Per contract: `read=0`; alert on empty input if abnormal |
| Duplicate order ID in writer | `FAILED` per demo policy |
| Reject table unwriteable | `FAILED`; do not continue importing silently |
| Report directory unwriteable | Import `COMPLETED`, report `FAILED`, job `FAILED` |
| Report step restarts after failure | Completed import is not re-read; report regenerated |
| File modified between restarts | Blocked via snapshot/checksum validation |
| Item succeeds on retry | No false reject created |
| Processor returns `null` | Filtered, no skip reject produced |
| CSV schema columns changed | Validation/parser fails per policy; requires file-level validation |
| File contains Unicode characters | Proper UTF-8 encoding |
| Record contains sensitive data | Report contains only allowed metadata |
| Concurrent jobs | Independent `fileId` and report targets |
| Listener re-runs on rollback | Unique key/transaction controls duplicates |
| Non-DB output side effects | Outbox/idempotency/reconciliation in place |

### 22.1. Failure at a Specific Chunk

When testing writer errors, know the chunk size and fixture ordering to predict which commits succeeded. A `FAILED` step after three chunks does not mean the target table is empty; previously committed chunks typically remain.

### 22.2. When the Report File Already Exists

If an old report was already published yet the job crashed before updating metadata, a restart may rewrite the file under the same name. Atomic overwriting in the demo provides **internal output idempotency**, yet if external consumers already downloaded the file, a new version needs dedicated publish/version/notification rules. Never silently send two reports with different content for the same `fileId`.

### 22.3. Incomplete Source Input

Before running `FlatFileItemReader`, require a ready marker/manifest or safe publishing convention. A producer still uploading can cause the batch to hit EOF early and finish with fewer rows and no parse errors. Skip reports do not automatically detect missing tails; checksums/expected record counts protect dataset integrity.

---

## 23. Performance and Operations

### 23.1. Impact of SkipListener on Throughput

Every skip in the demo executes a `MERGE` into the database. With `skipLimit=3`, overhead is tiny. If a source has millions of bad rows and tens of thousands are allowed to skip, per-item SQL increases network/transaction overhead.

Optimization paths:

- Batch rejects per chunk within the same transaction via a bounded buffer flushed at the right time.
- Use bulk inserts/UPSERTs with a unique key.
- Move quarantine to a separate table with appropriate partitioning/indexes.
- Keep report metadata small without raw payloads.
- Set skip limits based on data requirements, not performance.
- Monitor reject write latency to catch bottlenecks.

Note that `SkipListener` callbacks follow framework ordering around commits; a custom buffer must flush before commit in the right transaction and roll back safely. Never accumulate rejects in an unbounded singleton list and flush in `afterJob`.

### 23.2. Report Memory Footprint

The demo uses `List<RejectedLine>` and `StringBuilder` because `skipLimit=3`. If the limit can reach 100,000 errors, the report could consume hundreds of MiB of heap.

Production design:

```text
JdbcTemplate streaming/row callback
             │
             ▼
BufferedWriter to report.tmp
             │
             ▼
flush/close
             │
             ▼
atomic move / conditional publish
```

Apply file/report size limits, access controls, and retention; if reports must be analyzed by BI, keep rejects in the database and paginate exports instead of generating one huge file.

### 23.3. Chunk Size and Rollbacks

Small chunks checkpoint frequently, reducing records reprocessed on error, yet increase commit overhead. Large chunks reduce commits, yet rollbacks cover more items and can consume more memory.

For the practice project, chunk size 3 is easy to observe. In production, try 100/500/1000 depending on record size, measuring throughput, transaction time, GC, DB load, and restart duration. Never alter the skip limit just because you changed the chunk size.

### 23.4. Multi-Threaded or Partitioned Steps

When multiple workers run in parallel, ensure:

- Each reader has independent state or is properly synchronized.
- `fileId + lineNumber` still uniquely identifies records within each partition, or add `resourceId` if each partition has its own file.
- `SkipListener` is stateless or properly scoped; never hold unsafe mutable shared counters.
- Two workers never write to the same report target concurrently.
- Per-`StepExecution` total skip limits may not match a **job-wide** limit when partitioned; aggregate and enforce a global policy if business rules require it.

### 23.5. Reporting by Partner and Time

In multi-partner systems, you can add `partnerId` and `businessDate`, while enforcing access controls, data placement, and schema separation. Never mix rejected rows from different partners into one public report file, or construct paths from arbitrary input filenames.

---

## 24. Common Issues and Resolutions

| Symptom | Cause | Resolution |
|---|---|---|
| Bad row still fails the job | Not `faultTolerant`, exception not whitelisted | Configure skip for the right type and test |
| Job `COMPLETED` yet no reject report | Processor used `return null` so it only filtered | Throw a skippable exception if the error needs reporting |
| `readSkipCount` differs from error line count | Reader skips headers/comments or parses differently | Define line semantics and verify with fixtures |
| `SkipListener` receives no item in `onSkipInRead` | Item failed before parsing completed | Use `FlatFileParseException.getLineNumber()` |
| Raw input written to logs | Arbitrary use of `getInput()`/`toString()` | Store only line number + error code |
| Report has rejects yet DB output rolled back | Rejects written to file outside transaction | Persist rejects via JDBC in the same transaction |
| Job exceeds skip limit yet report still claims success | Flow/report does not check import status | Halt flow on `FAILED` or issue a separate incident report |
| Report step fails after import succeeds | File permissions/storage/atomic rename | Fix report storage, restart the same `JobInstance` |
| Restart reads wrong records | File changed between runs | Pin file version, checksum, and immutable snapshot |
| Valid records duplicate on restart | Non-idempotent writer or external output | Unique key, proper upsert/reconciliation |
| Skipping writer errors loses critical data | Overly broad skip, unclear JDBC side effects | Do not skip writer errors without an explicit policy |
| Every exception gets skipped | Overly broad `skip(Exception.class)` | Whitelist specific exceptions |
| Report misses a few rejects | Listener DB write failed or wrong `DataSource` | Share transaction, reconcile reject count |
| Does H2 keep data after JVM restart? | In-memory H2 is not durable | Use a persistent production DB |
| Report file has unusual name/path | Unvalidated `fileId` | Whitelist `fileId` and fix the directory |
| Slow performance with many errors | `MERGE` per skip + index/IO | Bounded bulk reject writes within the transaction |
| Same `fileId` runs multiple `JobInstance`s | Non-standard identifying params | Use business `fileId`/`snapshotId` as identity |
| Report `generatedAt` changes on restart | Uses wall-clock time in report step | Use a timestamp stored in metadata if byte-identical output is needed |

---

## 25. Extension Exercises

### Exercise 1 — Adding a Currency Error

Add the row:

```csv
109,1009,12.00,XYZ
```

Set `skipLimit=4` and inspect `processSkipCount`, the `UNSUPPORTED_CURRENCY` reject row, and the new report. Then keep `limit=3` to confirm the job ends `FAILED` at the threshold.

### Exercise 2 — Strict Failure Policy

Change the policy so `INVALID_ORDER_ID` fails the step immediately while `NON_POSITIVE_AMOUNT` is skipped. Write separate tests for both error types. Explain why both are business errors yet carry different risk levels.

### Exercise 3 — Two-File CSV Report

Generate `summary.json` and `rejects.csv` instead of a single text file. Keep the staging/atomic-publish mechanism so consumers receive **the entire report set** only after both files are complete with a manifest.

### Exercise 4 — Quarantine with Remediation Workflow

Add a `reject_resolution` table recording `fileId`, `lineNumber`, `status`, modifier, timestamp, and corrected data version. Build a separate reprocess job handling only approved fixes without silently altering the initial snapshot.

### Exercise 5 — Percentage Validation

In addition to `skipLimit=100`, add a policy failing the job if the error rate exceeds 2%. Clearly define the denominator, handle empty inputs, and decide when to check (before reporting, after reading all rows, or fail fast once evidence suffices).

### Exercise 6 — Idempotent Writer

Replace `INSERT` with a controlled UPSERT suited to the target database. If the same `fileId+orderId` has a different amount, fail or log an incident rather than silently overwriting. Test crash/restart.

### Exercise 7 — Report When Import Fails

Design a workflow generating an **incident report** after the import step fails while keeping the final Job status `FAILED`. Incident report data must distinguish persisted counters from rolled-back chunks; never publish it as a completion report.

### Exercise 8 — Running Multiple Files

Use `MultiResourceItemReader` with an immutable manifest. Add `resourceId` to the reject key because the same `lineNumber` can appear in multiple files. Test restarts without changing file order.

### Exercise 9 — Securing Sensitive Data

Suppose the CSV contains account numbers and emails. Design the report to hold only hashed/business references, error codes, and line numbers. Restrict operator permissions, set retention for source and quarantine files, and keep PII out of logs.

### Exercise 10 — Monitoring

Export skip counts by stage and total skip rate by partner. Write alerts if `skipRate` exceeds threshold or `reportStep` misses its deadline. Use low-cardinality labels.

---

## 26. References

- [Spring Batch — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): `faultTolerant`, `skip`, and `skipLimit`.
- [Spring Batch — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): distinguishing retry and skip.
- [Spring Batch — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): listeners and callbacks.
- [Spring Batch — SkipListener API 5.2](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html): `onSkipInRead`, `onSkipInProcess`, and `onSkipInWrite`.
- [Spring Batch — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): `FlatFileItemReader`, `LineMapper`, and parse errors.
- [Spring Batch — JdbcBatchItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC writer and database I/O.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transactions, commits, and chunks.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, counters.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoints and restarts.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` and `JobLauncherTestUtils`.
- [Spring Boot — JDBC / SQL Initialization](https://docs.spring.io/spring-boot/reference/data/sql.html): auto-initializing schemas in demo environments.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): JDBC transactions and boundaries across resources.

## 27. Summary

Handling skipped invalid data **is not** setting `.skip(Exception.class)` and letting the job run to the end. Good design must clearly separate **parse errors**, **business errors**, **transient errors needing retry**, and **mandatory-fail errors**; set a finite skip limit; persist rejected items with stable keys; reconcile figures from `StepExecution` and the reject store; and publish completion reports only when the import succeeds.

The project above demonstrates this practically: `FlatFileItemReader` preserves line numbers, `ItemProcessor` throws targeted exceptions, the fault-tolerant step skips only the whitelist, `SkipListener` persists rejects in the same database transaction, and a dedicated report step verifies counts and publishes the file. Adding restarts, immutable inputs, writer idempotency, alerts, and report access controls lets the pipeline ingest valid data promptly while **never hiding invalid data**, ensuring every rejected row has a reason and a follow-up path.
