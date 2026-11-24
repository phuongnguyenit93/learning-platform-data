# Building a Multi-Step Job Flow — Spring Batch Core Processing Practice Project

## 1. Problem Statement and Deliverable

An enterprise receives a daily order CSV file from a partner. The file may contain valid orders alongside missing or invalid data. The operations team needs a batch job with a **clearly staged workflow** that publishes data only after it passes quality checks, while also supporting stopping and resuming once data is corrected.

Instead of having one step do everything, we design a **multi-step job flow**:

1. **Prepare** — verify the business period and create an operational audit trail.
2. **Import** — read CSV, validate each item, and write to a staging table by chunk.
3. **Quality gate** — count invalid records, check duplicate order IDs, and decide `PASS` or `HOLD`.
4. **Publish** — if `PASS`, promote valid data from staging to the main table.
5. **Summary** — record that the batch has been published.
6. **Hold** — if `HOLD`, record the reason, stop the Job for operational remediation, and then restart at the quality gate.

This is a practice project about **job control flow**, not just reading and writing CSVs.

```text
                        orderFlowJob
                             |
                             v
                       prepareStep
                             |
                             v
                        importStep
                   (reader / processor /
                     writer per chunk)
                             |
                             v
                       qualityGateStep
                         /          \
                    PASS /            \ HOLD
                        v              v
                   publishStep       holdStep
                        |              |
                        v              v
                   summaryStep      STOPPED
                        |         restart at
                        v          qualityGateStep
                    COMPLETED
```

**Expected outcomes:**

- First run with a file whose error count is within threshold: `JobExecution` ends `COMPLETED` and valid data appears in the main table.
- Run with a stricter threshold: `JobExecution` ends `STOPPED`, without publishing data.
- After fixing erroneous staging records, **restart the exact `JobInstance`**: the quality gate re-runs and the job proceeds to publish/summary without unnecessarily re-importing the file.
- If the import step hits a genuine technical error, the job transitions to `FAILED`, ready for investigation and metadata-based restart.
- Never create a new `JobInstance` using an arbitrary timestamp to bypass restart errors.

This lesson uses **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC, H2, and JUnit 5**. This is a small-scale sample project; the production section highlights changes needed for PostgreSQL, large files, multiple workers, and formal auditing.

---

## 2. From Sequential Steps to Conditional Flows

### 2.1. `Job` and `Step` Have Distinct Roles

**`Job`** is the logical workflow definition: its steps, execution order, and branching rules.

**`Step`** is a processing unit with its own transaction, lifecycle, and metadata. A Step can be:

- **Tasklet step:** performs a single operation such as preparing, checking conditions, moving files, or updating audit records.
- **Chunk-oriented step:** loops `read → process → write` with commit boundaries per item group.
- Another technical step type supported by Spring Batch, depending on needs and version.

Each job run creates a **`JobExecution`**, containing **`StepExecution`**s. A `JobInstance` can have multiple `JobExecution`s when restarting after `FAILED` or `STOPPED`.

### 2.2. Sequential Flow

A simple job follows one linear path:

```java
return new JobBuilder("simpleJob", jobRepository)
    .start(stepA)
    .next(stepB)
    .next(stepC)
    .build();
```

If step A completes, the framework advances to B, then C. If a step fails without special transitions, the job normally fails rather than running subsequent steps.

### 2.3. Branching Flow

A real multi-step flow needs to **evaluate a step's `ExitStatus`** to decide the path:

```text
qualityGateStep
   |
   +-- ExitStatus=PASS --> publishStep --> summaryStep
   |
   +-- ExitStatus=HOLD --> holdStep ----> STOPPED
   |
   +-- technical error -> FAILED
```

In Spring Batch, **`BatchStatus`** and **`ExitStatus`** are not the same:

| Attribute | Purpose | Example |
| --- | --- | --- |
| `BatchStatus` | Lifecycle state of the step/job | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | Outcome used to build flow transitions | `COMPLETED`, `FAILED`, or custom `PASS`, `HOLD` |
| `on(...)` pattern | Matches against **exit code**, not directly `BatchStatus` | `on("PASS")`, `on("HOLD")` |
| `to(step)` | Transitions to the next step | `to(publishStep)` |
| `stopAndRestart(step)` | Stops flow with a designated restart point | `stopAndRestart(qualityGateStep)` |

A quality-gate tasklet can succeed technically (`BatchStatus` `COMPLETED`) yet set `ExitStatus` to `HOLD` because data quality is insufficient. The flow takes the `HOLD` branch and the `JobExecution` is intentionally stopped.

### 2.4. Flows Are Not Java Loops

Never use a `while(true)` loop inside a tasklet to "wait for data to be fixed" or invoke steps like Java methods. Flow transitions let Spring Batch persist metadata, show operators where the job stands, and provide restart semantics.

---

## 3. Sample Project Architecture

### 3.1. Directory Structure

Create a basic Spring Boot Gradle project:

```text
order-flow-demo/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/com/example/orderflow/
    │   │   ├── OrderFlowApplication.java
    │   │   ├── RawOrder.java
    │   │   ├── StagedOrder.java
    │   │   ├── OrderRuleProcessor.java
    │   │   ├── OrderFlowConfiguration.java
    │   │   └── DemoRunner.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── orders-demo.csv
    └── test/
        └── java/com/example/orderflow/
            └── OrderFlowIntegrationTest.java
```

Code is presented file by file. To experiment, you can place the records/classes together in the same package per the structure above.

### 3.2. Gradle Dependencies

The `build.gradle` example uses Spring Boot 3.3.x as a configuration sample compatible with Java 17/Spring Batch 5.x. In a real project, pick the Spring Boot 3.x release maintained and approved by your team.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`settings.gradle`:

```groovy
rootProject.name = 'order-flow-demo'
```

Do not add `@EnableBatchProcessing` when letting Spring Boot manage Batch auto-configuration as in this example. In some configurations, adding that annotation makes Boot's auto-configuration yield to manual Batch configuration; datasource/`JobOperator`/`JobRepository` wiring must then be reviewed.

### 3.3. `application.yml`

Use **in-memory** H2 to keep running the demo simple:

```yaml
spring:
  application:
    name: order-flow-demo

  datasource:
    url: jdbc:h2:mem:orderflow;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  sql:
    init:
      mode: always

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

logging:
  level:
    org.springframework.batch: INFO
    com.example.orderflow: INFO
```

Explanation:

- `spring.batch.job.enabled=false`: prevents Boot from auto-running all jobs at startup; we launch explicitly from the demo runner or tests.
- `spring.batch.jdbc.initialize-schema=always`: initializes `BATCH_*` metadata tables in H2 for the demo environment.
- `spring.sql.init.mode=always`: runs `schema.sql` to create business tables.
- In-memory H2 **does not retain metadata when the JVM exits**. To prove restarts across process crashes, use PostgreSQL or file-based H2 with safe schema migrations.

**Production must never enable unconditional schema initialization settings** on a database with critical Batch history. Use Flyway/Liquibase and proper schema versioning.

---

## 4. Input Data and Business Tables

### 4.1. CSV Containing Both Valid and Rejected Records

`src/main/resources/orders-demo.csv`:

```csv
orderId,customerId,amount,status
O-100,C-01,120.00,READY
O-101,C-02,50.50,READY
O-102,C-03,-9.00,READY
O-103,C-04,70.00,READY
O-104,C-05,0.00,READY
```

We have:

- **5** data rows.
- **3** valid orders: O-100, O-101, O-103.
- **2** orders failing with non-positive amounts: O-102, O-104.
- No duplicate order IDs among the valid list.

To keep the lesson focused on flow, bad records do not fail the import step: the processor turns them into a `REJECTED` record in staging. If the CSV is structurally invalid or the reader cannot open the file, the import step still becomes `FAILED`.

### 4.2. Staging Table

`schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS STG_ORDER (
    BUSINESS_DATE DATE NOT NULL,
    SOURCE_LINE INTEGER NOT NULL,
    ORDER_ID VARCHAR(64),
    CUSTOMER_ID VARCHAR(64),
    AMOUNT DECIMAL(18, 2),
    RECORD_STATUS VARCHAR(12) NOT NULL,
    REJECT_REASON VARCHAR(64),
    PRIMARY KEY (BUSINESS_DATE, SOURCE_LINE)
);
```

The `(BUSINESS_DATE, SOURCE_LINE)` key works for one file per day in the demo. It prevents a row with a blank `ORDER_ID` from failing to record a reject. In multi-file/tenant systems, expand the key to `(TENANT_ID, SOURCE_FILE_ID, SOURCE_LINE)` or an equivalent meaningful source key.

### 4.3. Main Target Table

Also in `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS PUBLISHED_ORDER (
    BUSINESS_DATE DATE NOT NULL,
    ORDER_ID VARCHAR(64) NOT NULL,
    CUSTOMER_ID VARCHAR(64) NOT NULL,
    AMOUNT DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (BUSINESS_DATE, ORDER_ID)
);
```

The business key in the demo is `(BUSINESS_DATE, ORDER_ID)`. The unique constraint prevents publishing two copies of the same order on one day. In real deployments, the key must follow the business contract: an order ID may also need tenant/source/version.

### 4.4. Flow Status Table

End of `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS FLOW_AUDIT (
    BUSINESS_DATE DATE PRIMARY KEY,
    FLOW_STATE VARCHAR(32) NOT NULL,
    NOTE VARCHAR(512)
);
```

The `FLOW_AUDIT` table is just a simple audit table for this practice project. `JobRepository` remains the source of truth for exact `JobExecution`, `StepExecution`, and checkpoint state. Never replace `BATCH_*` tables with this audit table.

### 4.5. Why Stage Before Publishing?

If writing straight into the main table during the import step, by the time the quality gate detects two invalid orders, earlier chunks may have already committed. A `FAILED` or `STOPPED` job **does not automatically roll back all chunks across the whole job**.

Staging allows:

```text
Import chunks -> COMMITTED into STG_ORDER
                          |
                          v
                    Quality gate
                          |
                  +-------+--------+
                  |                |
                PASS              HOLD
                  |                |
                  v                v
         PUBLISHED_ORDER     Do not publish
```

Thus data has been loaded for inspection without becoming published data. This is a standard pattern when a **data quality gate** is required.

---

## 5. Domain Model: Raw Input and Staged Result

### 5.1. `RawOrder.java`

```java
package com.example.orderflow;

public record RawOrder(
    int sourceLine,
    String orderId,
    String customerId,
    String amountText,
    String statusText
) {
}
```

We keep `amountText` as a `String` so the processor explicitly classifies data errors; the reader does not throw on negative or unparseable amounts.

`sourceLine` is the CSV line position, identifying the staging record even when `orderId` is missing. With a header on line 1, the first data row starts on line 2.

### 5.2. `StagedOrder.java`

```java
package com.example.orderflow;

import java.math.BigDecimal;
import java.time.LocalDate;

public record StagedOrder(
    LocalDate businessDate,
    int sourceLine,
    String orderId,
    String customerId,
    BigDecimal amount,
    String recordStatus,
    String rejectReason
) {
}
```

Two `recordStatus` values in the example:

| Status | Meaning |
| --- | --- |
| `VALID` | Order eligible for publishing |
| `REJECTED` | Order failed business rules; retains error info |

This status is a **domain status in the staging table**, not Spring Batch's `BatchStatus`.

---

## 6. Processor Classifying Data

### 6.1. `OrderRuleProcessor.java`

```java
package com.example.orderflow;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;

public final class OrderRuleProcessor
        implements ItemProcessor<RawOrder, StagedOrder> {

    private final LocalDate businessDate;

    public OrderRuleProcessor(LocalDate businessDate) {
        this.businessDate = businessDate;
    }

    @Override
    public StagedOrder process(RawOrder raw) {
        String orderId = clean(raw.orderId());
        String customerId = clean(raw.customerId());
        String status = clean(raw.statusText())
            .toUpperCase(Locale.ROOT);

        String reason = null;
        BigDecimal amount = null;

        if (orderId.isBlank()) {
            reason = "ORDER_ID_REQUIRED";
        } else if (customerId.isBlank()) {
            reason = "CUSTOMER_ID_REQUIRED";
        } else if (!"READY".equals(status)) {
            reason = "STATUS_UNSUPPORTED";
        } else {
            try {
                amount = new BigDecimal(
                    clean(raw.amountText())
                ).setScale(2, RoundingMode.UNNECESSARY);

                if (amount.signum() <= 0) {
                    reason = "AMOUNT_NON_POSITIVE";
                }
            } catch (NumberFormatException
                    | ArithmeticException exception) {
                reason = "AMOUNT_INVALID";
            }
        }

        String decision =
            reason == null ? "VALID" : "REJECTED";

        return new StagedOrder(
            businessDate,
            raw.sourceLine(),
            orderId,
            customerId,
            amount,
            decision,
            reason
        );
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }
}
```

**Design highlights:**

- Every input always produces a `StagedOrder` — even when rejected. The processor does not `return null` because the requirement calls for recording erroneous records.
- The processor does not access the database or emit side effects, so it can be re-invoked during rollbacks/restarts without causing off-transaction effects.
- `LocalDate businessDate` is passed when the step starts instead of using `LocalDate.now()` on each process call; thus re-running/restarting the next day does not alter the data period.
- `BigDecimal` is used for money; `setScale(2, RoundingMode.UNNECESSARY)` avoids silently rounding amounts with too many decimal places.
- Fixed rule codes make report aggregation and remediation straightforward.

### 6.2. Why Not Throw an Exception for the Two Negative-Amount Records?

Because the project contract is to **ingest all records into staging and let the quality gate decide**. If the processor threw an exception and `skip`ped them, bad records could drop out of the writer flow and require a separate skip listener/quarantine mechanism.

With this design, the import step can be `COMPLETED` with 5 staged rows while the gate blocks publishing. Separating the technical outcome of import from the business decision of publishing keeps the flow clear.

### 6.3. Limitations of This Example

Several production requirements are not yet in the processor:

- Currency, tenant ownership, order ID format, JSON payload, schema version.
- Duplicate IDs across the whole file (handled at the gate via an aggregate query).
- Customer reference data (requires a controlled snapshot/query).
- Effective-dated rule versions and multi-version auditing.

These are extension paths; never move cross-record business rules into a mutable `HashSet` inside the processor and assume it is safe across partitioning/restarts.

---

## 7. CSV Reader with `FlatFileItemReader`

### 7.1. Configuration in `OrderFlowConfiguration`

We declare the reader as `@StepScope` so it can read `inputFile` from `JobParameters` right when the step executes.

```java
@Bean
@StepScope
FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}")
        String inputFile,
        ResourceLoader resourceLoader) {

    DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    tokenizer.setNames(
        "orderId",
        "customerId",
        "amount",
        "status"
    );

    return new FlatFileItemReaderBuilder<RawOrder>()
        .name("orderCsvReader")
        .resource(resourceLoader.getResource(inputFile))
        .linesToSkip(1)
        .strict(true)
        .lineMapper((line, lineNumber) -> {
            FieldSet fields = tokenizer.tokenize(line);

            return new RawOrder(
                lineNumber,
                fields.readString("orderId"),
                fields.readString("customerId"),
                fields.readString("amount"),
                fields.readString("status")
            );
        })
        .build();
}
```

This is a `@Bean` method placed in the complete configuration class in Section 9; the corresponding imports appear there.

### 7.2. Stateful Reader with Checkpoints

`FlatFileItemReader` implements the `ItemStream` contract. With a stable name `orderCsvReader` and appropriate default `saveState`, Spring Batch can save the read position in `ExecutionContext` at commit boundaries.

When the import step is `FAILED` after several chunks, restarting the **same `JobInstance`** can reopen the reader at the persisted position instead of starting from line 1.

For restarts to work properly, ensure:

- The input file still exists at the same logical data source.
- File contents are not modified between executions, or explicit versioning/snapshots exist.
- The reader is properly registered for `open/update/close` lifecycle callbacks.
- `JobRepository` retains `BATCH_STEP_EXECUTION_CONTEXT` metadata.
- Identifying parameters are not replaced with a new timestamp.

### 7.3. When the Reader Hits Structural Errors

If a CSV row is missing columns or the file cannot be opened, the reader can throw an exception and the import step transitions to `FAILED` under this configuration. That is **fail-fast behavior for technical formatting errors**, whereas negative amounts are recorded as `REJECTED` by the processor.

If a project wants to skip some unparseable lines and record them in quarantine, add `faultTolerant().skip(...)`, a skip limit, and raw-line storage. Never skip all reader exceptions, as that masks missing-file/encoding/schema errors.

---

## 8. Staging Writer by Chunk

### 8.1. `JdbcBatchItemWriter`

The writer writes every `StagedOrder` into `STG_ORDER`. So the example can restart/replay safely, we use **H2**'s `MERGE INTO ... KEY (...)` rather than unconditional insert:

```java
@Bean
JdbcBatchItemWriter<StagedOrder> stagingWriter(
        DataSource dataSource) {

    String sql = """
        MERGE INTO STG_ORDER (
            BUSINESS_DATE,
            SOURCE_LINE,
            ORDER_ID,
            CUSTOMER_ID,
            AMOUNT,
            RECORD_STATUS,
            REJECT_REASON
        )
        KEY (BUSINESS_DATE, SOURCE_LINE)
        VALUES (
            :businessDate,
            :sourceLine,
            :orderId,
            :customerId,
            :amount,
            :recordStatus,
            :rejectReason
        )
        """;

    return new JdbcBatchItemWriterBuilder<StagedOrder>()
        .dataSource(dataSource)
        .sql(sql)
        .itemSqlParameterSourceProvider(item ->
            new MapSqlParameterSource()
                .addValue("businessDate",
                    java.sql.Date.valueOf(item.businessDate()))
                .addValue("sourceLine", item.sourceLine())
                .addValue("orderId", item.orderId())
                .addValue("customerId", item.customerId())
                .addValue("amount", item.amount())
                .addValue("recordStatus", item.recordStatus())
                .addValue("rejectReason", item.rejectReason()))
        .build();
}
```

**Dialect note:** The `MERGE ... KEY (...)` syntax above is for H2. In PostgreSQL, typically use `INSERT ... ON CONFLICT (...) DO UPDATE` with approved business keys and semantics. Never copy H2 syntax to PostgreSQL/Oracle without adapting it.

### 8.2. Why Is the SQL Based on `SOURCE_LINE`?

If a record has an invalid or blank order ID, we still need to store it in staging for remediation. The `SOURCE_LINE` key together with `businessDate` keeps the source record even without a valid `orderId`.

When an input file can be edited after import, row numbers may no longer identify the same record; real production systems should use **source file version + line number** or a stable external record ID. This sample assumes the file does not change within the same `JobInstance`.

### 8.3. Chunk Commit

Chunk size 2 makes behavior easy to observe:

```text
input 1, 2 -> process -> write [1, 2] -> COMMIT
input 3, 4 -> process -> write [3, 4] -> COMMIT
input 5    -> process -> write [5]    -> COMMIT
```

If the writer fails in the third chunk, the first two chunks may already have committed. Spring Batch does not roll back the entire job as if one SQL transaction wrapped all chunks.

---

## 9. Complete Multi-Step Configuration

### 9.1. `OrderFlowConfiguration.java` — Imports and Configuration

The methods below create all steps and the job. The demo beans share the H2 datasource for `JobRepository` and business data; production requires reviewing transaction managers and resource boundaries separately.

```java
package com.example.orderflow;

import java.sql.Date;
import java.time.LocalDate;

import javax.sql.DataSource;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderFlowConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}")
            String inputFile,
            ResourceLoader resourceLoader) {

        DelimitedLineTokenizer tokenizer =
            new DelimitedLineTokenizer();
        tokenizer.setNames(
            "orderId", "customerId", "amount", "status");

        return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderCsvReader")
            .resource(resourceLoader.getResource(inputFile))
            .linesToSkip(1)
            .strict(true)
            .lineMapper((line, lineNumber) -> {
                FieldSet fields = tokenizer.tokenize(line);

                return new RawOrder(
                    lineNumber,
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readString("amount"),
                    fields.readString("status"));
            })
            .build();
    }

    @Bean
    @StepScope
    OrderRuleProcessor orderRuleProcessor(
            @Value("#{jobParameters['businessDate']}")
            String businessDate) {

        return new OrderRuleProcessor(
            LocalDate.parse(businessDate));
    }

    @Bean
    JdbcBatchItemWriter<StagedOrder> stagingWriter(
            DataSource dataSource) {

        String sql = """
            MERGE INTO STG_ORDER (
                BUSINESS_DATE, SOURCE_LINE, ORDER_ID,
                CUSTOMER_ID, AMOUNT, RECORD_STATUS, REJECT_REASON
            )
            KEY (BUSINESS_DATE, SOURCE_LINE)
            VALUES (
                :businessDate, :sourceLine, :orderId,
                :customerId, :amount, :recordStatus, :rejectReason
            )
            """;

        return new JdbcBatchItemWriterBuilder<StagedOrder>()
            .dataSource(dataSource)
            .sql(sql)
            .itemSqlParameterSourceProvider(item ->
                new MapSqlParameterSource()
                    .addValue("businessDate",
                        Date.valueOf(item.businessDate()))
                    .addValue("sourceLine", item.sourceLine())
                    .addValue("orderId", item.orderId())
                    .addValue("customerId", item.customerId())
                    .addValue("amount", item.amount())
                    .addValue("recordStatus", item.recordStatus())
                    .addValue("rejectReason", item.rejectReason()))
            .build();
    }

    @Bean
    Step prepareStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("prepareStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "PREPARED",
                    "Input is ready for staging"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step importStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            OrderRuleProcessor orderRuleProcessor,
            JdbcBatchItemWriter<StagedOrder> stagingWriter) {

        return new StepBuilder("importStep", repository)
            .<RawOrder, StagedOrder>chunk(
                2, transactionManager)
            .reader(orderReader)
            .processor(orderRuleProcessor)
            .writer(stagingWriter)
            .build();
    }

    @Bean
    Step qualityGateStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("qualityGateStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);
                Date sqlDay = Date.valueOf(day);

                long total = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                    """,
                    Long.class, sqlDay);

                long rejected = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                      AND RECORD_STATUS = 'REJECTED'
                    """,
                    Long.class, sqlDay);

                long duplicateIds = jdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT ORDER_ID
                        FROM STG_ORDER
                        WHERE BUSINESS_DATE = ?
                          AND RECORD_STATUS = 'VALID'
                        GROUP BY ORDER_ID
                        HAVING COUNT(*) > 1
                    ) duplicated
                    """,
                    Long.class, sqlDay);

                Long configured =
                    contribution.getStepExecution()
                        .getJobParameters()
                        .getLong("maxRejected");

                if (configured == null || configured < 0) {
                    throw new IllegalArgumentException(
                        "maxRejected must be >= 0");
                }

                boolean pass =
                    total > 0 &&
                    rejected <= configured &&
                    duplicateIds == 0;

                String message =
                    "total=" + total
                    + ", rejected=" + rejected
                    + ", duplicateIds=" + duplicateIds
                    + ", limit=" + configured;

                contribution.setExitStatus(
                    new ExitStatus(
                        pass ? "PASS" : "HOLD",
                        message
                    )
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            // When STOPPED at HOLD, restart must re-evaluate
            // the quality gate after a data steward fixes staging.
            .allowStartIfComplete(true)
            .build();
    }

    @Bean
    Step publishStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("publishStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                // H2: set-based MERGE, without duplicating
                // business keys when re-execution is needed.
                jdbc.update("""
                    MERGE INTO PUBLISHED_ORDER (
                        BUSINESS_DATE,
                        ORDER_ID,
                        CUSTOMER_ID,
                        AMOUNT
                    )
                    KEY (BUSINESS_DATE, ORDER_ID)
                    SELECT
                        BUSINESS_DATE,
                        ORDER_ID,
                        CUSTOMER_ID,
                        AMOUNT
                    FROM STG_ORDER
                    WHERE BUSINESS_DATE = ?
                      AND RECORD_STATUS = 'VALID'
                    """,
                    Date.valueOf(day)
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step summaryStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("summaryStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "PUBLISHED",
                    "Quality gate passed; output published"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Step holdStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("holdStep", repository)
            .tasklet((contribution, context) -> {
                LocalDate day = businessDate(contribution);

                jdbc.update("""
                    MERGE INTO FLOW_AUDIT (
                        BUSINESS_DATE, FLOW_STATE, NOTE
                    ) KEY (BUSINESS_DATE)
                    VALUES (?, ?, ?)
                    """,
                    Date.valueOf(day),
                    "HOLD",
                    "Fix staging records then restart the same instance"
                );

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
    }

    private static LocalDate businessDate(
            org.springframework.batch.core.StepContribution contribution) {

        String text = contribution.getStepExecution()
            .getJobParameters()
            .getString("businessDate");

        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "businessDate is required");
        }
        return LocalDate.parse(text);
    }

    // The orderFlowJob bean is presented in Section 10.
}
```

This class holds the infrastructure/step definitions. In real code, individual steps can be split into smaller `@Configuration` classes, yet a single file helps learners see the entire flow's dependencies.

### 9.2. Why Set `allowStartIfComplete(true)` on the Quality Gate?

`qualityGateStep` technically completes even when setting `ExitStatus.HOLD`. Therefore, the step's `BatchStatus` can be `COMPLETED`. When the job is `STOPPED` and restarted, if the quality gate is not allowed to re-run, Spring Batch may skip the completed step, leaving the old result un-re-evaluated after staging is fixed.

The configuration:

```java
.allowStartIfComplete(true)
```

in the demo expresses the intent to **re-evaluate the gate on restart**. Do not set this attribute on every step by default: an already-completed step can produce unsafe side effects if re-run.

### 9.3. Why Not Use `LocalDate.now()` for `businessDate`?

A job launched on the 16th that must restart on the 17th still processes the **same period**. `businessDate` must come from identifying `JobParameters`, not current runtime clock time. Changing identifying parameters causes Spring Batch to create a new `JobInstance` without using old checkpoints or flow state.

---

## 10. Declaring the Conditional Job Flow

In the `OrderFlowConfiguration` class from Section 9, add the following `@Bean` method before the closing `}` of the class:

```java
@Bean
Job orderFlowJob(
        JobRepository repository,
        Step prepareStep,
        Step importStep,
        Step qualityGateStep,
        Step publishStep,
        Step summaryStep,
        Step holdStep) {

    return new JobBuilder("orderFlowJob", repository)
        .start(prepareStep)
        .next(importStep)
        .next(qualityGateStep)
            .on("PASS").to(publishStep)
        .from(qualityGateStep)
            .on("HOLD").to(holdStep)
        .from(holdStep)
            .on("COMPLETED")
            .stopAndRestart(qualityGateStep)
        .from(publishStep)
            .on("COMPLETED").to(summaryStep)
        .end()
        .build();
}
```

### 10.1. Explaining Each Part

```java
.start(prepareStep)
.next(importStep)
.next(qualityGateStep)
```

Defines the common order for every run: prepare → import → quality evaluation.

```java
.on("PASS").to(publishStep)
```

When the quality gate exit code is `PASS`, transition to publish.

```java
.from(qualityGateStep)
    .on("HOLD").to(holdStep)
```

Adds a branch starting **also from the quality gate** for when data fails to meet requirements.

```java
.from(holdStep)
    .on("COMPLETED")
    .stopAndRestart(qualityGateStep)
```

After the hold step records the audit, the `JobExecution` stops intentionally with **`qualityGateStep` as the restart point**. When operators fix staging data and restart the same instance, the flow can re-evaluate without re-running import from the beginning.

```java
.from(publishStep)
    .on("COMPLETED").to(summaryStep)
```

After publish succeeds, write the summary. If publish fails without a `COMPLETED` transition, the job does not proceed through summary as a success path.

```java
.end()
.build();
```

Ends the flow declaration and builds the job object.

### 10.2. `on("*")` Must Be Used Intentionally

Spring Batch supports pattern matching on exit codes, such as `on("*")` as a wildcard. However:

```java
.from(publishStep).on("*").to(summaryStep)
```

could accidentally treat an exit code other than `COMPLETED` as a reason to run the summary step. In critical pipelines, define explicit success paths and let unexpected errors fail the job, or declare dedicated error transitions.

Similarly, do not write `.on("*").end()` at a gate if it can **mask technical failures**. A `FAILED` step should lead to a failed job status, unless the business designs an explicit, safe recovery branch.

### 10.3. `.end()`, `.fail()`, and `.stopAndRestart()` Are Not Equivalent

In Spring Batch's flow builder:

| Transition | Meaning | When Appropriate |
| --- | --- | --- |
| `.end()` | Ends the flow with a completed status for that path | Valid completion path |
| `.fail()` | Ends the flow as failed | When the contract requires `JobExecution FAILED` |
| `.stopAndRestart(step)` | Stops the job with a designated step on restart | Pausing data pending remediation then resuming |
| `.to(step)` | Advances to another step | Continuing to subsequent processing |

In particular, `.end()` on a transition **does not roll back prior chunks**, and using it to end an error path can leave the Job `COMPLETED` unexpectedly. Always check the **final `BatchStatus` of `JobExecution`**, not just a step's exit code.

### 10.4. When to Use `JobExecutionDecider`?

For conditions depending on multiple steps, external systems, or complex audit results, Spring Batch provides `JobExecutionDecider` to return a `FlowExecutionStatus` and route the flow.

Illustrative example:

```java
JobExecutionDecider decider = (jobExecution, stepExecution) -> {
    String flag = jobExecution.getExecutionContext()
        .getString("approvalFlag", "PENDING");

    return new FlowExecutionStatus(
        "APPROVED".equals(flag) ? "PASS" : "HOLD"
    );
};
```

In a flow using a decider, you can declare `.next(decider)` and `.from(decider).on("PASS").to(...)` per the Spring Batch 5 DSL.

The sample project chose a **custom `ExitStatus` directly on `qualityGateStep`** because the decision originates in the inspection step itself; this avoids adding a decider solely to demonstrate a branch.

---

## 11. Application Entry Point and Running the Demo

### 11.1. `OrderFlowApplication.java`

```java
package com.example.orderflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            OrderFlowApplication.class, args);
    }
}
```

### 11.2. `DemoRunner.java`

The runner activates only when the `demo` profile is enabled, avoiding accidentally running the job during integration tests or other environments.

```java
package com.example.orderflow;

import java.util.List;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class DemoRunner {

    @Bean
    @Profile("demo")
    ApplicationRunner runDemo(
            JobLauncher launcher,
            @Qualifier("orderFlowJob") Job job) {

        return args -> {
            String date = option(
                args, "businessDate", "2026-11-16");

            String file = option(
                args, "inputFile",
                "classpath:orders-demo.csv");

            long maxRejected = Long.parseLong(
                option(args, "maxRejected", "2"));

            JobParameters parameters =
                new JobParametersBuilder()
                    .addString("businessDate", date, true)
                    .addString("inputFile", file, false)
                    .addLong("maxRejected", maxRejected, false)
                    .toJobParameters();

            JobExecution execution =
                launcher.run(job, parameters);

            System.out.println(
                "JobExecution ID=" + execution.getId()
                + ", status=" + execution.getStatus()
                + ", exitStatus=" + execution.getExitStatus()
            );
        };
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String defaultValue) {

        List<String> values = args.getOptionValues(name);

        return values == null || values.isEmpty()
            ? defaultValue
            : values.get(0);
    }
}
```

`businessDate` is an **identifying parameter**, because different business dates must be different `JobInstance`s. `inputFile` and `maxRejected` are marked non-identifying so they do not inadvertently create new identities when the same period is retried; they must still be **kept unchanged per the instance contract on restart**. In real environments, record the policy version/input checksum and never alter the source dataset after import has committed.

### 11.3. Running the PASS Path

From the project directory:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo --businessDate=2026-11-16 --maxRejected=2'
```

On Windows when using the Gradle wrapper:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=demo --businessDate=2026-11-16 --maxRejected=2"
```

With the demo file having exactly 2 rejected rows, condition:

```text
total = 5
rejected = 2
duplicateIds = 0
maxRejected = 2

=> quality gate PASS
=> publishStep
=> summaryStep
=> JobExecution COMPLETED
```

### 11.4. Running the HOLD Path

Use a different business date to create an independent instance in the demo:

```bash
./gradlew bootRun --args='--spring.profiles.active=demo --businessDate=2026-11-17 --maxRejected=1'
```

Expected:

```text
total = 5
rejected = 2
duplicateIds = 0
maxRejected = 1

=> quality gate HOLD
=> holdStep
=> JobExecution STOPPED
=> publishStep not called
```

**In-memory H2 limitation:** If you run two `bootRun` commands in two separate JVMs with the configuration above, a fresh database is created each time. To observe both instances in one persistent database across process restarts, switch to PostgreSQL or file-based H2 with proper migrations; or run both scenarios via integration tests inside the same Spring context in Section 14.

---

## 12. Inspecting Results via SQL and Batch Metadata

### 12.1. Staging Table

After the `PASS` or `HOLD` path:

```sql
SELECT
    BUSINESS_DATE,
    SOURCE_LINE,
    ORDER_ID,
    AMOUNT,
    RECORD_STATUS,
    REJECT_REASON
FROM STG_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-16'
ORDER BY SOURCE_LINE;
```

Expected:

| SOURCE_LINE | ORDER_ID | AMOUNT | RECORD_STATUS | REJECT_REASON |
| ---: | --- | ---: | --- | --- |
| 2 | O-100 | 120.00 | VALID | null |
| 3 | O-101 | 50.50 | VALID | null |
| 4 | O-102 | -9.00 | REJECTED | AMOUNT_NON_POSITIVE |
| 5 | O-103 | 70.00 | VALID | null |
| 6 | O-104 | 0.00 | REJECTED | AMOUNT_NON_POSITIVE |

`SOURCE_LINE` includes the header at line 1.

### 12.2. Published Table

For the `PASS` business date:

```sql
SELECT ORDER_ID, CUSTOMER_ID, AMOUNT
FROM PUBLISHED_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-16'
ORDER BY ORDER_ID;
```

Expected: exactly 3 records: O-100, O-101, O-103.

For the `HOLD` date (Nov 17):

```sql
SELECT COUNT(*)
FROM PUBLISHED_ORDER
WHERE BUSINESS_DATE = DATE '2026-11-17';
```

Expected: **0** because the flow did not pass through `publishStep`.

### 12.3. Audit Table

```sql
SELECT BUSINESS_DATE, FLOW_STATE, NOTE
FROM FLOW_AUDIT
ORDER BY BUSINESS_DATE;
```

A successful period has `FLOW_STATE=PUBLISHED`; a held period has `FLOW_STATE=HOLD`.

### 12.4. Spring Batch Metadata

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'orderFlowJob'
ORDER BY je.JOB_EXECUTION_ID;
```

To inspect each step's status:

```sql
SELECT
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY JOB_EXECUTION_ID, STEP_EXECUTION_ID;
```

Metadata table and column names depend on the Spring Batch schema. The queries above target the standard Spring Batch 5.x JDBC schema.

### 12.5. Distinguishing Two Important Outcomes

```text
qualityGateStep:
  BatchStatus = COMPLETED
  ExitStatus  = PASS or HOLD

JobExecution after HOLD:
  BatchStatus = STOPPED
  ExitStatus  = STOPPED / per flow
```

A step executing successfully does not necessarily make the whole job `COMPLETED`: flow transitions determine whether the job continues, stops, or fails.

---

## 13. Restarting from HOLD After Fixing Data

### 13.1. Why Not Launch a New `JobInstance`?

Suppose the job for the 17th imported into staging and stopped at the quality gate. If you add an identifying `runAt=System.currentTimeMillis()` to create a new instance, the import step may re-read the file, losing restart benefits and risking duplicate side effects.

Instead, what to do:

1. Keep the same `businessDate`/`JobInstance`.
2. Fix the verified error in `STG_ORDER`.
3. Invoke restart with the `STOPPED` execution.
4. Let `qualityGateStep` re-run and take the `PASS` branch if eligible.
5. Verify published output.

### 13.2. Fixing One Staging Row in the H2 Demo

For the 17th, there are 2 rejected rows; the allowed threshold is 1. Once the operator verifies the right value for O-102 from the source, update the corresponding record:

```sql
UPDATE STG_ORDER
SET
    AMOUNT = 90.00,
    RECORD_STATUS = 'VALID',
    REJECT_REASON = NULL
WHERE BUSINESS_DATE = DATE '2026-11-17'
  AND ORDER_ID = 'O-102'
  AND RECORD_STATUS = 'REJECTED';
```

This is an **intentional remediation example**. Never arbitrarily change `-9.00` to `90.00` in production without source evidence and approver auditing.

After fixing:

```text
total=5
rejected=1
duplicateIds=0
limit=1

=> PASS
```

### 13.3. Calling `JobOperator.restart(...)`

In Spring Batch 5.x, when `JobOperator` is configured with `JobRepository`, `JobExplorer`, and an appropriate job registry:

```java
Long restartedExecutionId =
    jobOperator.restart(stoppedExecutionId);
```

`stoppedExecutionId` is a **`JobExecution` ID**, not a `JobInstance` ID. The returned value is the new execution ID in the same `JobInstance` if restart conditions are met.

For a job using `stopAndRestart(qualityGateStep)`, the framework saves the flow continuation point; `qualityGateStep` also has `allowStartIfComplete(true)` to re-evaluate after staging data is fixed.

### 13.4. Why Does the Import Step Not Re-Run?

On the first run, `importStep` already `COMPLETED` and committed staging data. After `STOPPED`, the flow restarts from the quality gate per configuration. Import is not part of what needs re-running.

If the import step previously `FAILED` due to a bad file, there is no `HOLD` transition; the job enters the normal error/restart path, and the **import step** must resume from its checkpoint if feasible. Those are two different recovery types.

### 13.5. Reading Status After Restart

```java
JobExecution restarted =
    jobExplorer.getJobExecution(restartedExecutionId);

if (restarted != null) {
    System.out.println(restarted.getStatus());
    System.out.println(restarted.getJobInstance().getId());
}
```

When `JobLauncher` has an asynchronous executor, the returned ID does not mean execution has finished. Poll/track until terminal status before asserting `COMPLETED`.

---

## 14. Integration Testing PASS, HOLD, and Restart

A multi-step flow practice project needs to test **real execution paths**, not only processor unit tests.

### 14.1. Test Configuration

With `spring.batch.job.enabled=false` and in-memory H2 in `application.yml`, integration tests can use `@SpringBootTest` and `@SpringBatchTest`.

`src/test/java/com/example/orderflow/OrderFlowIntegrationTest.java`:

```java
package com.example.orderflow;

import java.sql.Date;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class OrderFlowIntegrationTest {

    @Autowired
    JobLauncher launcher;

    @Autowired
    JobExplorer explorer;

    @Autowired
    @Qualifier("orderFlowJob")
    Job job;

    @Autowired
    JdbcTemplate jdbc;

    private static JobParameters params(
            String date, long maxRejected) {

        return new JobParametersBuilder()
            .addString("businessDate", date, true)
            .addString("inputFile",
                "classpath:orders-demo.csv", false)
            .addLong("maxRejected", maxRejected, false)
            .toJobParameters();
    }

    @Test
    void passPublishesOnlyValidRows() throws Exception {
        JobExecution execution =
            launcher.run(job, params("2026-11-16", 2L));

        assertEquals(
            BatchStatus.COMPLETED,
            execution.getStatus());

        assertEquals(5L, count(
            "STG_ORDER", "2026-11-16"));

        assertEquals(3L, count(
            "PUBLISHED_ORDER", "2026-11-16"));

        assertTrue(hasStep(
            execution, "prepareStep"));
        assertTrue(hasStep(
            execution, "importStep"));
        assertTrue(hasStep(
            execution, "qualityGateStep"));
        assertTrue(hasStep(
            execution, "publishStep"));
        assertTrue(hasStep(
            execution, "summaryStep"));
        assertFalse(hasStep(
            execution, "holdStep"));

        assertEquals("PUBLISHED",
            state("2026-11-16"));
    }

    @Test
    void holdAndRestartReevaluateGate()
            throws Exception {

        JobParameters parameters =
            params("2026-11-17", 1L);

        JobExecution first =
            launcher.run(job, parameters);

        assertEquals(
            BatchStatus.STOPPED,
            first.getStatus());

        assertEquals("HOLD",
            state("2026-11-17"));

        assertEquals(0L, count(
            "PUBLISHED_ORDER", "2026-11-17"));

        assertTrue(hasStep(
            first, "qualityGateStep"));
        assertTrue(hasStep(
            first, "holdStep"));
        assertFalse(hasStep(
            first, "publishStep"));

        // Test assumes a data steward verified the right number.
        int updated = jdbc.update("""
            UPDATE STG_ORDER
            SET AMOUNT = 90.00,
                RECORD_STATUS = 'VALID',
                REJECT_REASON = NULL
            WHERE BUSINESS_DATE = ?
              AND ORDER_ID = 'O-102'
              AND RECORD_STATUS = 'REJECTED'
            """, Date.valueOf("2026-11-17"));

        assertEquals(1, updated);

        // Use the same JobInstance; do not create an identifying timestamp.
        JobExecution restarted =
            launcher.run(job, parameters);

        assertEquals(
            BatchStatus.COMPLETED,
            restarted.getStatus());

        assertNotEquals(
            first.getId(),
            restarted.getId());

        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId());

        assertTrue(hasStep(
            restarted, "qualityGateStep"));
        assertTrue(hasStep(
            restarted, "publishStep"));
        assertTrue(hasStep(
            restarted, "summaryStep"));

        assertFalse(hasStep(
            restarted, "importStep"));

        assertEquals(4L, count(
            "PUBLISHED_ORDER", "2026-11-17"));

        assertEquals("PUBLISHED",
            state("2026-11-17"));

        JobExecution persisted =
            explorer.getJobExecution(restarted.getId());

        assertNotNull(persisted);
        assertEquals(
            BatchStatus.COMPLETED,
            persisted.getStatus());
    }

    private long count(String table, String day) {
        // 'table' is called by the test only with fixed constants;
        // never take table names from external input.
        Long count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table
                + " WHERE BUSINESS_DATE = ?",
            Long.class,
            Date.valueOf(day));

        return count == null ? 0 : count;
    }

    private String state(String day) {
        return jdbc.queryForObject("""
            SELECT FLOW_STATE
            FROM FLOW_AUDIT
            WHERE BUSINESS_DATE = ?
            """,
            String.class,
            Date.valueOf(day));
    }

    private static boolean hasStep(
            JobExecution execution,
            String stepName) {

        return execution.getStepExecutions().stream()
            .map(StepExecution::getStepName)
            .anyMatch(stepName::equals);
    }
}
```

### 14.2. Key Assertions

- With `maxRejected=2`, quality gate `PASS`es, job `COMPLETED`, only 3 rows published.
- With `maxRejected=1`, quality gate `HOLD`s, job `STOPPED`, publish is not called.
- Fix staging, restart with same parameters: **`JobInstance` ID unchanged**, new `JobExecution` ID.
- Import step is not re-run when restarting from `HOLD`; `qualityGate`, `publish`, and `summary` have corresponding executions.
- Total published for the 17th is 4 rows after one reject is remediated.
- `JobExplorer` reads persisted metadata within the same JVM.

In the test, the order of the two methods need not be fixed because they use two different business dates. If running the same test case multiple times on an unreset H2 instance, `JobInstanceAlreadyCompleteException` may appear; test fixtures should use isolated databases/context resets or dedicated business keys per test run.

### 14.3. An Important Test Assumption

The test above uses the default synchronous `JobLauncher`. If the application configures an asynchronous `TaskExecutor` for the launcher, `launcher.run(...)` may return before the job finishes. In that case, poll/wait for terminal status with a reasonable timeout instead of asserting immediately.

### 14.4. How to Test Technical Error Branches

Configure a non-existent input file:

```text
inputFile=classpath:missing.csv
```

Expected:

- `orderReader` cannot open the resource.
- `importStep` is `FAILED`.
- `qualityGateStep` and `publishStep` do not run.
- `JobExecution` is `FAILED`.
- After fixing the file and verifying the same business input logic, restart the old instance to re-read.

Never configure `.on("*").to(publishStep)` after a failing import, because incomplete staging data could then enter publishing.

---

## 15. Flow Status and Restarts: Traps to Understand

### 15.1. A `COMPLETED` Step May Not Re-Run

Spring Batch normally skips a step already `COMPLETED` when restarting the same `JobInstance`, unless `allowStartIfComplete(true)` or flow restart semantics require and permit it.

For this flow:

| Step | On First PASS | On First HOLD | After Fix and Restart |
| --- | --- | --- | --- |
| `prepareStep` | runs | runs | does not re-run |
| `importStep` | runs | runs | does not re-run |
| `qualityGateStep` | `PASS` | `HOLD` | re-runs |
| `publishStep` | runs | does not run | runs |
| `summaryStep` | runs | does not run | runs |
| `holdStep` | does not run | runs | does not run if gate `PASS`es |

Without `allowStartIfComplete(true)` on the gate, restarting after `HOLD` easily fails to perform the intended fresh evaluation.

### 15.2. `STOPPED` Differs from `FAILED`

`FAILED` typically indicates a step/job did not complete due to an exception or failure transition. `STOPPED` is a paused state that may result from an intentionally designed flow transition.

Even so, `STOPPED` is not always safe for automatic restarts. With this flow, restart only after a record has been fixed and output verified; otherwise, the quality gate still `HOLD`s and the job becomes `STOPPED` again.

### 15.3. `end()` Can Mask Failures If Used Misleadingly

Example:

```java
.from(qualityGateStep).on("HOLD").end()
```

Using a successful-completion transition for the `HOLD` path can mark `JobExecution` as `COMPLETED` even with no published data. A completed instance generally cannot be restarted normally, complicating remediation.

In this practice project, `stopAndRestart(qualityGateStep)` accurately expresses the contract "pause for data remediation and then re-evaluate."

### 15.4. Changing the Flow Between Executions

When deploying a new version, removing/renaming steps, changing flow structure, or altering `JobParameters` rules can make restarting an old instance incompatible.

Production needs:

- Keep step names and `ExecutionContext` keys stable while old jobs remain restartable.
- Have a migration/change plan for breaking changes.
- Pin flow/rule versions to business runs when needed.
- Never rename `qualityGateStep` between `HOLD` and restart without impact assessment.
- Test restarts across new versions before deploying.

---

## 16. Chunk Processing and Tasklets: Transaction Boundaries

### 16.1. Import Chunks

`importStep` uses:

```java
.<RawOrder, StagedOrder>chunk(2, transactionManager)
```

In each chunk:

1. Reader reads input.
2. Processor creates staged item.
3. Writer sends JDBC batch.
4. Transaction commits and `ExecutionContext` updates accordingly.

If the third chunk fails, the previous two chunks may have already committed. On restart, the reader uses checkpoints from `JobRepository` to resume.

### 16.2. Tasklet Steps

`prepareStep`, `qualityGateStep`, `publishStep`, `summaryStep`, and `holdStep` are all tasklet steps. They execute one unit of work and return:

```java
return RepeatStatus.FINISHED;
```

If a tasklet must repeat multiple turns, it can return `RepeatStatus.CONTINUABLE` per contract, though this lesson avoids tasklet loops to keep flow control logic simple.

### 16.3. Why Publish in a Single SQL Statement?

With small H2 demos, publish uses `MERGE ... SELECT` to promote all `VALID` rows in one step. Advantages:

- Readable code.
- Fewer round trips.
- No need to load all rows into Java.
- SQL can participate in the tasklet step's transaction if datasource/transaction manager are configured properly.

However, production with tens of millions of rows may require smaller batches, partitioning, tuned set-based SQL, transaction windows, or versioned outputs to avoid locks and timeouts. When splitting publish into multiple chunks, add explicit idempotency and gate/publish semantics.

### 16.4. Metadata and Business Datasources Can Differ

The example uses the same H2 database to reduce complexity. If `JobRepository` is on DB A and staging/published tables are on DB B, two transaction resources do not automatically commit atomically across databases. You can see:

```text
DB B: published rows COMMITTED
DB A: StepExecution/checkpoint not yet updated
Process dies
```

On restart, publish may be invoked again. Thus unique business keys/`MERGE` or reconciliation workflows remain necessary.

### 16.5. Off-Database Side Effects

If publish also sends HTTP/email/Kafka events, failing after sending can cause restarts to resend. Consider transactional outboxes, idempotency keys, or consumer-side deduplication. Multi-step flows express ordering, **without automatically providing exactly-once** across external systems.

---

## 17. JobParameters and Identifying Business Periods

### 17.1. Choosing Identifying Parameters

In the demo:

```java
.addString("businessDate", date, true)
.addString("inputFile", file, false)
.addLong("maxRejected", maxRejected, false)
```

Same day shares the same `JobInstance`; different days are independent processing periods. That is a **simplification for learning**.

In production, if there are multiple files per day or multiple tenants, `businessDate` alone is insufficient. You may need:

```java
.addString("tenantId", tenantId, true)
.addString("sourceFileId", sourceFileId, true)
.addString("businessDate", date.toString(), true)
.addString("flowVersion", flowVersion, false)
```

If `flowVersion` changes requiring the same data to be processed as a new job, consider identifying by an explicit contractual business revision rather than arbitrarily changing parameters during a restart.

### 17.2. Never Use Current Time to Always Create a New Instance

This is an anti-pattern:

```java
.addLong("runAt", System.currentTimeMillis())
```

In commonly used Spring Batch 5.x overloads, parameters may default to **`identifying=true`**. When restarting with a new timestamp, the framework creates a different `JobInstance`; `importStep`'s checkpoints and the old flow's stop/restart position are not reused.

To resume `HOLD` or `FAILED`, you must restart the **old instance** using its execution ID or the same identifying parameters per contract.

### 17.3. Non-Identifying Does Not Mean Free to Change on Restart

For an instance in `HOLD` due to `maxRejected=1`, operators must not "cheat" by restarting the same business date while raising the threshold to 10 to force publishing. `JobOperator.restart(executionId)` uses old parameters/metadata; if changing policy is genuinely required, that is a business decision needing auditing and possibly a separate reprocess flow revision.

This lesson chooses **fixing verified staging data** and then restarting the quality gate under the same policy.

---

## 18. Organizing Production Flows: Issues and Solutions

### 18.1. Running Multiple Tenants or Multiple Files

If a single day has 100 tenants, define identity as:

```text
jobName=orderFlowJob
tenantId=tenant-001
sourceFileId=orders-2026-11-16-v1
businessDate=2026-11-16
```

Staging/target tables also need tenant and source version where appropriate; prevent different tenants' jobs from overwriting the same `(businessDate, sourceLine)` key.

### 18.2. Immutable Input

If a file is edited after `importStep` completed, a flow restart from the quality gate **does not re-read** the file. That is intentional in the flow. To apply an edited file, decide to:

- Edit staging with auditing.
- Run a dedicated remediation job.
- Create a new import revision.
- Or reset/restart the pipeline via an approved workflow.

Never silently swap the file path in non-identifying parameters and expect the import step to re-read automatically.

### 18.3. Multi-Condition Quality Gate

A production gate can evaluate:

- Rejected count / total eligible.
- Error rate by rule code.
- Duplicate business keys.
- Amount sum vs. manifest file.
- Reference data completeness.
- Tenant ownership.
- SLA/data freshness thresholds.
- Data Steward approval.

It can return custom exit codes like `PASS`, `HOLD_REVIEW`, `REJECT_BATCH`. With multiple branches, use `JobExecutionDecider` or split validation steps to keep the flow maintainable.

### 18.4. Audit Is More Than a Single Status Row

The demo `FLOW_AUDIT` table stores only the final status. Production may need an append-only audit:

```text
jobInstanceId
jobExecutionId
stepName
timestamp
actor
action
policyVersion
sourceFileVersion
beforeStatus
afterStatus
reasonCode
correlationId
```

When an operator fixes a staging record, record verification/approval source rather than running ad-hoc SQL updates without history.

### 18.5. Running Steps Independently for Maintainability?

Spring Batch lets you run/test a single step, yet a step may depend on the prior step's output data. For instance, `publishStep` must not run standalone against staging that hasn't passed the gate. Production should guard invariants inside publish or via a publication-approval table, rather than trusting every caller to go through the standard Job flow.

### 18.6. Preventing Duplicates at Scheduler and API Layers

A launch request may be retried after a network timeout. Use stable identifying params, a persistent `JobRepository`, and a business request ledger/unique key if needed to decide launch/restart. Two requests with different `JobInstance`s writing to the same table can still cause contention; enforce tenant/slot ownership and writer idempotency.

---

## 19. Common Pitfalls When Building Multi-Step Job Flows

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Job does not enter `PASS` branch | `ExitStatus` does not match `on("PASS")` | Check actual `StepExecution` exit code; set custom `ExitStatus` properly |
| Gate `HOLD`s yet Job reports `COMPLETED` | Used `.end()` on `HOLD` branch | Use `stopAndRestart` or fail per contract |
| Restart `HOLD` yet gate does not re-run | Gate already `COMPLETED`, missing `allowStartIfComplete(true)` | Allow re-evaluating gate and re-test |
| Import re-runs unexpectedly | Created new `JobInstance` using timestamp | Use stable identifying params; restart existing instance |
| Data published despite gate failure | Overly broad wildcard transition or publish ran standalone | Guard branches and publish permissions |
| H2 loses data after JVM restart | Used in-memory database | Use a persistent DB for cross-process-crash recovery |
| Step bean called before `JobParameters` exist | Accessed parameter outside step scope | Use `@StepScope` or read during Tasklet execution |
| Reader fails to restore position | Lost `ItemStream`, reader name changed, or metadata lost | Preserve lifecycle/checkpoints and immutable inputs |
| Staging data duplicates on retry | Writer insert lacks business key/idempotency | Unique constraint + semantically right upsert |
| Publisher throws duplicate key after restart | Publish committed yet metadata failed to update | Set-based idempotent writes and reconciliation |
| Quality gate counts rejects wrongly | Query lacks period/tenant filter or jobs overlap | Stable business keys and complete predicates |
| Changed input file on restart yet output unchanged | Import step already `COMPLETED` and skipped | Explicit remediation/revision |
| `JobOperator.restart` cannot find Job | `JobRegistry` unregistered or misconfigured | Check `JobOperator`/registry and job definition |
| Forgot to distinguish `ExitStatus` and `BatchStatus` | Checked only Step status `COMPLETED` | Check custom exit code and job flow status |
| Flow keeps errors in staging yet still publishes | Branch fails to catch duplicates/critical rules | Add gate and publication guard |
| Using one transaction for millions of rows | Locks, log growth, timeouts | Chunk/partition or controlled versioned publishing |

### 19.1. An Ordered Debugging Approach

When the flow takes the wrong path:

1. Check job name, identifying parameters, and `JobInstance` ID.
2. Read `BATCH_JOB_EXECUTION` for the execution's `BatchStatus`/`ExitStatus`.
3. Read `BATCH_STEP_EXECUTION` in order to see which steps actually ran.
4. Check the exit code returned by `qualityGateStep`.
5. Compare `on(...)` mappings in `JobBuilder`.
6. Read staging/quality metrics and verify the job is using the right `businessDate`.
7. On restart, check whether the last execution is `STOPPED`/`FAILED` and whether another worker is still running.
8. Reconcile checkpoint metadata and output before re-running.

Never fix a flow by putting `.on("*").to(publishStep)` so it "won't get stuck," because that can turn data or infrastructure errors into bad published records.

---

## 20. Project Extension Exercises

### Exercise 1 — Adding a `REJECT_BATCH` Branch

Add a severe violation: an order belonging to another tenant. The gate must return `REJECT_BATCH` if any such violation exists. Build branch:

```text
qualityGateStep
  PASS         -> publishStep
  HOLD         -> holdStep -> STOPPED
  REJECT_BATCH -> rejectBatchStep -> FAILED
```

Requirement: do not publish; audit logs rule code and total affected records.

### Exercise 2 — Percentage Quality Gate

Replace absolute `maxRejected` with both an absolute limit and a percentage over eligible rows—for example, `rejectRate` at most 0.5% and rejected count at most 100.

Requirement: define the denominator, test boundaries exactly at the threshold and one record above it.

### Exercise 3 — Multi-File and Multi-Tenant Source Data

Extend the CSV/file manifest with `tenantId` and `sourceFileId`. Update staging/published primary keys and identifying `JobParameters`.

Requirement: two tenants on the same day do not overwrite each other's staging; restarting each tenant preserves the right `JobInstance`.

### Exercise 4 — Post-Publish Alert Branch

Add a `notificationStep` after `summaryStep` if completion notifications are needed. Use a transactional outbox or idempotency key so duplicate notifications are not sent if the job crashes after sending the message yet before updating metadata.

Requirement: test restarts and prove at most one business notification per key.

### Exercise 5 — Fail Import and Checkpoint Restart

Create a 100-record CSV with chunk size 10 and a writer simulating failure on the fourth chunk. After fixing the error, restart the same instance.

Requirement: test `importStep` resumes from its checkpoint, committed rows are not duplicated, and the gate runs only after import succeeds.

### Exercise 6 — Trying `JobExecutionDecider`

Replace the quality gate's custom exit code with a step that only computes metrics and a `JobExecutionDecider` evaluating the decision from persisted data.

Requirement: `PASS`/`HOLD` flow stays accurate without relying on a mutable in-memory singleton.

### Exercise 7 — Splitting Publish for Large Data

Convert the publish tasklet into a chunk-oriented step or partitioned set-based SQL publish; handle millions of records.

Requirement: compare commit duration, restart cost, idempotency, and transaction boundaries.

### Exercise 8 — Remediation Runbook

Write an operations runbook:

1. Query `REJECTED` records.
2. Verify accurate values from the source.
3. Update staging with auditing.
4. Check rejected count.
5. Invoke restart with the exact `JobExecution` ID.
6. Monitor until `COMPLETED`.
7. Reconcile published output.

Requirement: never use an identifying timestamp to open a new `JobInstance` instead of restarting.

---

## 21. Project Completion Checklist

A multi-step flow satisfies the practice objectives when:

- [ ] Project boots and `BATCH_*` plus staging/published/audit tables are created.
- [ ] Job has steps `prepare → import → quality gate`.
- [ ] Reader has `@StepScope` and gets `inputFile` from `JobParameters`.
- [ ] Processor classifies `VALID`/`REJECTED` with rule codes.
- [ ] Writer writes staging in chunks with duplicate-prevention keys.
- [ ] Gate checks rejected counts and duplicate business keys.
- [ ] `PASS` branch publishes only `VALID` records.
- [ ] `HOLD` branch logs audit and leaves `JobExecution` in `STOPPED`.
- [ ] Restarting the same `JobInstance` returns to `qualityGateStep` after remediation.
- [ ] Import step does not re-run unnecessarily when restarting from `HOLD`.
- [ ] Output queries and assertions exist for both branches.
- [ ] Test exists for `FAILED` path when reader/file is unavailable.
- [ ] Distinguishes `BatchStatus`, `ExitStatus`, checkpoints, and flow transitions.
- [ ] Does not add `runAt=System.currentTimeMillis()` as an identifying `JobParameter` per run.
- [ ] Production plan specifies datasources, schema migrations, idempotency, versioning, and auditing.

## 22. Architectural Summary

A **multi-step job flow** does more than make code tidy. It separates responsibilities, lets Spring Batch record stage-by-stage state, performs `ExitStatus`-driven branching, and supports restarting at the exact right place after failures or manual data intervention.

In this project:

- **Chunk step** handles checkpointed import.
- **Tasklet steps** handle preparation, evaluation, and publishing.
- **`on("PASS")` / `on("HOLD")`** decide the branch.
- **`stopAndRestart(qualityGateStep)`** enables intentional pausing and re-evaluation after remediation.
- **`allowStartIfComplete(true)`** on the quality gate is an intentional choice so the step re-runs on restart.
- **Staging and unique keys** preserve erroneous data, control publishing, and reduce duplication risks on re-runs.
- **Stable `JobParameters`** keep the entire job tied to the right logical identity of one business period.

Mastering these points lays the foundation for building multi-step pipelines with branching, gates, auditing, and resilience in production batch systems.

## 23. References

- [Spring Batch — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobBuilder`, `JobInstance`, `JobExecution`, restartability.
- [Spring Batch — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): `on`, `to`, `from`, `end`, `fail`, and `stopAndRestart`.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): reader, processor, writer, and transaction boundaries.
- [Spring Batch — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html): tasklet semantics and transactions.
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope` and `JobParameters`.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoints and restarts.
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobExplorer` and `JobOperator`.
- [Spring Batch — Testing](https://docs.spring.io/spring-batch/reference/testing.html): integration testing and `@SpringBatchTest`.
- [Spring Boot — Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): Batch auto-configuration and schemas.
- [H2 Database Documentation](https://h2database.com/html/commands.html): `MERGE INTO` and demo SQL behavior.
