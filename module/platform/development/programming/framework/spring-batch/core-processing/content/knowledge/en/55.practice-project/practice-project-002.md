# Adding a Validation and Mapping Processor in a Spring Batch Project

In a Spring Batch project, data read from CSV, a database, or an API is rarely in a form the business logic can use directly. Fields may have extra whitespace, invalid date formats, unsupported status codes, or missing required values. If raw data is passed straight from `ItemReader` to `ItemWriter`, the system ends up relying on database constraints or writer errors to surface issues; by that point, it is hard to explain which record was invalid and why.

This practice project focuses on **adding an `ItemProcessor` to validate and map data** in a Spring Batch processing flow. We build an example that imports orders from CSV into a database: the reader reads string values, the processor **normalizes -> validates -> transforms into the output model**, and the writer receives only valid records.

This lesson is presented standalone so it can be applied to an existing project or used as a practice template. The Job, class, and table names below are illustrative and do not assume a pre-existing codebase. The primary implementation targets **Java 17, Spring Boot 3.x, and Spring Batch 5.x**. When using Spring Batch 6.x, some packages and builder APIs have changed; adjust imports and configuration for your actual version.

## 1. Objectives and Expected Outputs

After this lesson, learners will be able to:

1. Define the responsibilities of `ItemReader`, `ItemProcessor`, and `ItemWriter` in a chunk-oriented Step.
2. Create a **raw input** model and a **normalized output** model instead of writing directly from CSV into a database entity.
3. Validate required fields, status codes, dates, monetary amounts, and supported value sets.
4. Map data types from `String` to `LocalDate`, `BigDecimal`, and target model fields.
5. Distinguish between **filtering via `return null`**, **skipping due to an allowed exception**, and **failing the Step** on critical errors.
6. Wire the processor into a Step, design error reporting, and inspect counters.
7. Write unit tests for the processor and integration tests for the Reader → Processor → Writer flow.
8. Recognize the impact of retries, restarts, transactions, and parallel execution on a processor.

The expected outcome is a Job that writes only **eligible orders**, maintains clear counters for filtered and failed records, and does not rely on assuming data is "always clean."

## 2. Project Processing Flow

We use the `importOrdersJob` example loading order CSVs into the `accepted_order` table:

```text
CSV file
  |
  v
FlatFileItemReader<RawOrder>
  |
  |  Data is still in string form:
  |  orderDate = "2026-11-16"
  |  amount    = "125.50"
  |  currency  = "usd"
  v
ItemProcessor<RawOrder, PreparedOrder>
  |
  +-- trim and normalize codes
  +-- validate required fields
  +-- parse dates and amounts
  +-- validate business rules
  +-- map to PreparedOrder
  |
  +-- skippable data error --------> SkipListener / error report
  |
  +-- DRAFT status ----------------> return null (filter)
  |
  v
JdbcBatchItemWriter<PreparedOrder>
  |
  v
accepted_order (PostgreSQL)
```

In a chunk Step, Spring Batch invokes:

```java
O output = processor.process(input);
```

where `I` is the item type returned by the reader and `O` is the item type received by the writer. `ItemProcessor<I, O>` does not have to keep `I == O`.

This is a key point of this practice project: the CSV data has `amount` as a `String`, whereas the writer receives only a validated `BigDecimal`; the CSV data has `order_date` as text, whereas the writer receives a `LocalDate`.

### Division of Responsibilities

| Component | Should Do | Should Avoid |
| --- | --- | --- |
| `ItemReader` | Read lines/records, split columns, create `RawOrder`, provide source location when possible. | Carrying all business rules or silently fixing invalid data. |
| `ItemProcessor` | Normalize, validate, filter by rule, map to `PreparedOrder`. | Writing to databases, calling remote services with side effects, or arbitrarily mutating shared state. |
| `ItemWriter` | Write valid items with transactions, idempotency, and constraints. | Guessing the meaning of raw data or handling all validation errors itself. |
| `SkipListener` | Record skipped items after the fault-tolerant Step decides to skip. | Treating every transient exception as a final rejected item. |

Placing validation in the processor allows testing each rule independently without opening a database connection or launching the full Job.

## 3. Defining the Sample Data Contract

### 3.1. Input CSV

Create a sample file at `src/test/resources/orders-fixture.csv`:

```csv
source_row_id,order_id,customer_code,order_date,amount,currency,order_status
r-01,ord-1001,cus-01,2026-11-16,125.50,usd,READY
r-02,ord-1002,cus-02,2026-11-16,0,USD,READY
r-03,ord-1003,cus-03,2026-11-16,45.00,eur,DRAFT
r-04,ord-1004,,2026-11-16,33.40,USD,READY
r-05,ord-1005,cus-05,2026-11-17,99.99,USD,READY
r-06,ord-1006,cus-06,2026-11-16,12.999,USD,READY
r-07,ord-1007,cus-07,2026-11-16,not-a-number,USD,READY
r-08,ord-1008,cus-08,2026-11-16,40.00,gbp,READY
r-09,ord-1009,cus-09,2026-11-16,7.50,USD,READY
```

Each row has a `source_row_id` for lookup on error. In real data, the source key must be stable per file/dataset and sufficiently unique; `r-01` in two different files is not the same occurrence.

### 3.2. Illustrative Business Rules

| Field | Rule |
| --- | --- |
| `source_row_id` | Required, used to locate the source record. |
| `order_id` | Required; trim, uppercase; allow only letters, digits, and hyphens. |
| `customer_code` | Required; trim, uppercase; allow only letters, digits, and hyphens. |
| `order_date` | ISO date `yyyy-MM-dd`, must parse into a valid `LocalDate`. |
| `amount` | Positive decimal, at most 2 decimal places, no greater than 1,000,000.00 in the corresponding currency. |
| `currency` | Only accepts `USD` or `EUR` in this exercise version; uppercase the code. |
| `order_status` | `READY` is processed; `DRAFT` is filtered; any other value is a data error. |

The USD/EUR limit and two decimal places were chosen **only for a consistent example**. If a project supports JPY, VND, or other currencies, do not enforce the same decimal places for every currency; apply currency-specific rules and the real business contract.

### 3.3. Expected Results for the Fixture

| Source row | Result | Reason |
| --- | --- | --- |
| `r-01` | Written to table | Valid, codes normalized. |
| `r-02` | Process skip | Non-positive amount. |
| `r-03` | Filter | `DRAFT` status does not need importing yet. |
| `r-04` | Process skip | Missing `customer_code`. |
| `r-05` | Written to table | Valid. |
| `r-06` | Process skip | `12.999` has more than 2 decimal places. |
| `r-07` | Process skip | `amount` cannot be parsed. |
| `r-08` | Process skip | Currency `GBP` is not in the exercise's supported set. |
| `r-09` | Written to table | Valid. |

Out of 9 total source records, **3 valid records**, **1 filtered record**, and **5 process-skipped records**. These numbers are fixture expectations for testing, not a universal threshold for every Job.

## 4. Spring Batch Dependencies and Environment

In a Gradle project with Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

If you want to try `BeanValidatingItemProcessor` with Jakarta Bean Validation in the extension section, add:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Spring Boot requires a `DataSource` and an appropriate `PlatformTransactionManager` for the Job/Step; Spring Batch requires the `JobRepository` metadata schema. Test databases should be isolated from production.

For integration tests, you can disable automatic Job launch when Spring Boot creates the context:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderImportIT {
    // Manually launch the Job after preparing the data.
}
```

The examples in this lesson use **PostgreSQL** to illustrate the target table and upsert syntax. If using H2, MySQL, or Oracle, adjust the SQL accordingly. Never automatically execute cleanup scripts against production tables to run fixtures.

## 5. Creating the Raw Input Model: `RawOrder`

You should not use a JPA entity or database model directly as the CSV reading object. An independent input model allows accepting invalid values without premature type casting.

Create `RawOrder.java`:

```java
package example.batch.orders;

public record RawOrder(
        String sourceRowId,
        String orderId,
        String customerCode,
        String orderDate,
        String amount,
        String currency,
        String orderStatus) {
}
```

At this stage, **all fields are `String`**. Therefore:

- A row with `amount=not-a-number` can still create a `RawOrder`, and the processor classifies it as `AMOUNT_INVALID_FORMAT`.
- A row with a blank `customer_code` still reaches the processor to receive a specific validation error.
- The reader is responsible only for splitting columns according to the CSV format.

This fits when you want most business data errors routed into the processor. It does not mean the reader cannot fail: structurally malformed CSV lines, missing columns, encoding errors, or unreadable resources can still cause `FlatFileParseException`/I/O errors. Read-skip policies must be designed separately.

## 6. Creating the Output Model: `PreparedOrder`

The output model represents the **contract of a validated item**:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.time.LocalDate;

public record PreparedOrder(
        String sourceRowId,
        String orderId,
        String customerCode,
        LocalDate orderDate,
        BigDecimal amount,
        String currency) {
}
```

Unlike `RawOrder`:

- `orderDate` is a `LocalDate`, no longer a string that could contain an invalid date.
- `amount` is a `BigDecimal` with controlled scale.
- `orderId`, `customerCode`, and `currency` have been normalized.
- Only items satisfying the `READY` policy are produced as output.

### Why Use `BigDecimal` Instead of `double`?

For monetary values, binary representation in `double` can introduce rounding errors. `BigDecimal` lets you control decimal arithmetic, scale, and explicit rounding rules.

Do not automatically call `setScale(2, RoundingMode.HALF_UP)` to turn `12.999` into `13.00` if the input contract requires at most two decimal places. This lesson intentionally **rejects invalid precision** instead of silently altering values.

## 7. Defining a Validation Exception with an Error Code

So that a failed record can be reported clearly, use a dedicated exception carrying a **stable error code**, rather than relying on the message of `NumberFormatException` or `DateTimeParseException`.

Create `OrderValidationException.java`:

```java
package example.batch.orders;

public final class OrderValidationException
        extends RuntimeException {

    private final String errorCode;
    private final String sourceRowId;

    public OrderValidationException(
            String errorCode,
            String sourceRowId) {

        // Message does not contain sensitive raw payload.
        super(errorCode);
        this.errorCode = errorCode;
        this.sourceRowId = sourceRowId;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getSourceRowId() {
        return sourceRowId;
    }
}
```

Example error codes:

| `errorCode` | Meaning |
| --- | --- |
| `SOURCE_ROW_ID_REQUIRED` | Missing source identifier. |
| `ORDER_STATUS_REQUIRED` | Missing order status. |
| `ORDER_STATUS_UNSUPPORTED` | Status is outside the allowed set. |
| `ORDER_ID_REQUIRED` | Missing order ID. |
| `ORDER_ID_INVALID` | Order ID contains unsupported characters. |
| `CUSTOMER_CODE_REQUIRED` | Missing customer code. |
| `CUSTOMER_CODE_INVALID` | Invalid customer code. |
| `ORDER_DATE_INVALID` | Date has an invalid format or does not exist. |
| `AMOUNT_INVALID_FORMAT` | Amount cannot be parsed. |
| `AMOUNT_TOO_MANY_DECIMALS` | Amount has more than 2 decimal places. |
| `AMOUNT_NOT_POSITIVE` | Amount is not positive. |
| `AMOUNT_OUT_OF_RANGE` | Amount exceeds business limits. |
| `CURRENCY_UNSUPPORTED` | Currency is not supported. |

An enum can be used for error codes in larger systems. For this lesson, string constants are easy to read and verify. Avoid putting full invalid CSV values into exception messages: logs and error reports must adhere to data protection principles.

## 8. Writing `OrderProcessor`: Validate and Map

Below is a pure Java processor that makes no database or HTTP calls and holds no mutable state across items.

Create `OrderProcessor.java`:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Set;

import org.springframework.batch.item.ItemProcessor;

public final class OrderProcessor
        implements ItemProcessor<RawOrder, PreparedOrder> {

    private static final Set<String> SUPPORTED_CURRENCIES =
            Set.of("USD", "EUR");

    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000.00");

    @Override
    public PreparedOrder process(RawOrder raw) {
        String sourceKey =
                required(raw.sourceRowId(),
                        "SOURCE_ROW_ID_REQUIRED", "unknown");

        String status = required(
                raw.orderStatus(),
                "ORDER_STATUS_REQUIRED",
                sourceKey).toUpperCase(Locale.ROOT);

        // Business decision: DRAFT is not yet imported into the target system.
        if ("DRAFT".equals(status)) {
            return null; // filter, not skip
        }

        if (!"READY".equals(status)) {
            throw invalid("ORDER_STATUS_UNSUPPORTED", sourceKey);
        }

        String orderId = normalizedCode(
                raw.orderId(), "ORDER_ID", sourceKey);

        String customerCode = normalizedCode(
                raw.customerCode(), "CUSTOMER_CODE", sourceKey);

        LocalDate date = parseDate(raw.orderDate(), sourceKey);
        BigDecimal amount = parseAmount(raw.amount(), sourceKey);

        String currency = required(
                raw.currency(),
                "CURRENCY_UNSUPPORTED",
                sourceKey).toUpperCase(Locale.ROOT);

        if (!SUPPORTED_CURRENCIES.contains(currency)) {
            throw invalid("CURRENCY_UNSUPPORTED", sourceKey);
        }

        return new PreparedOrder(
                sourceKey,
                orderId,
                customerCode,
                date,
                amount,
                currency
        );
    }

    private static String required(
            String raw,
            String code,
            String sourceKey) {

        if (raw == null || raw.isBlank()) {
            throw invalid(code, sourceKey);
        }

        return raw.trim();
    }

    private static String normalizedCode(
            String raw,
            String fieldName,
            String sourceKey) {

        String value = required(
                raw,
                fieldName + "_REQUIRED",
                sourceKey).toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]+")) {
            throw invalid(fieldName + "_INVALID", sourceKey);
        }

        return value;
    }

    private static LocalDate parseDate(
            String raw,
            String sourceKey) {

        String value = required(
                raw, "ORDER_DATE_INVALID", sourceKey);

        try {
            return LocalDate.parse(value); // ISO yyyy-MM-dd
        } catch (DateTimeParseException ex) {
            throw invalid("ORDER_DATE_INVALID", sourceKey);
        }
    }

    private static BigDecimal parseAmount(
            String raw,
            String sourceKey) {

        String value = required(
                raw, "AMOUNT_INVALID_FORMAT", sourceKey);

        final BigDecimal amount;
        try {
            amount = new BigDecimal(value);
        } catch (NumberFormatException ex) {
            throw invalid("AMOUNT_INVALID_FORMAT", sourceKey);
        }

        final BigDecimal normalized;
        try {
            normalized = amount.setScale(
                    2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw invalid(
                    "AMOUNT_TOO_MANY_DECIMALS", sourceKey);
        }

        if (normalized.signum() <= 0) {
            throw invalid("AMOUNT_NOT_POSITIVE", sourceKey);
        }

        if (normalized.compareTo(MAX_AMOUNT) > 0) {
            throw invalid("AMOUNT_OUT_OF_RANGE", sourceKey);
        }

        return normalized;
    }

    private static OrderValidationException invalid(
            String code, String sourceKey) {
        return new OrderValidationException(code, sourceKey);
    }
}
```

### Explaining the Processing Order

1. **Keep the source key** so that when an error occurs, we can identify which record had an issue.
2. **Check status first**: the exercise specifies that `DRAFT` is filtered, so the other fields of a `DRAFT` order do not need to be validated like a ready order.
3. **Check unsupported statuses** so we do not accidentally ingest a status without a business contract.
4. **Normalize IDs** with `trim` and `toUpperCase(Locale.ROOT)`. Using `Locale.ROOT` prevents uppercasing behavior from varying by JVM locale.
5. **Parse the date** with `LocalDate.parse` so fake dates such as `2026-02-30` are rejected.
6. **Parse the amount** with `BigDecimal` and require exact scale 2. `RoundingMode.UNNECESSARY` actively throws an error if rounding would be needed.
7. **Check the currency** against the set of codes published in the exercise.
8. **Create the new model** `PreparedOrder` only once all conditions pass.

**Validation order is a business decision.** In this example, `DRAFT` is filtered before checking amount and date. If the workflow requires detecting data quality errors on **every** row (including `DRAFT`), change the policy: validate the required fields first and filter afterward. Never silently change the order without updating expectations and tests.

### Should Data Be Auto-Fixed?

Normalizing whitespace or letter casing is an acceptable transformation if clearly defined in the business contract. By contrast:

- `12.999` to `13.00` changes a monetary value; never round arbitrarily.
- Date `11/16/2026` should not be guessed into another format if the source committed to ISO.
- Currency `GBP` should not be silently converted into `USD`.
- A missing customer code should not have a random code generated.

Basic rule: **normalize what has deterministic rules, reject what lacks a valid basis**.

## 9. `return null`, Throwing Exceptions, and Infrastructure Errors

`ItemProcessor` has three key outcomes:

```text
processor.process(rawOrder)
       |
       +-- returns PreparedOrder ---> Writer
       |
       +-- returns null -----------> Filtered item
       |
       +-- throws exception -------> Fault-tolerant policy
                                    |
                                    +-- skip allowed -> skip
                                    +-- retry allowed -> retry
                                    +-- not allowed -> fail
```

| Scenario | What Processor Should Do | Typical Related Counter |
| --- | --- | --- |
| Valid `READY` | Return `PreparedOrder` | `readCount`, then `writeCount` if written successfully. |
| `DRAFT` not ready for import | Return `null` | `filterCount`. |
| Negative amount | Throw `OrderValidationException` | `processSkipCount` if the exception is skippable. |
| Unsupported currency | Throw `OrderValidationException` | `processSkipCount` if the exception is skippable. |
| Database unreachable | Do not convert into a validation exception | Retry/fail as an infrastructure error. |
| Unexpected logic bug | Let it fail for investigation | Do not broadly skip all exceptions. |

**Do not use `return null` to hide every error.** Because filtering does not trigger a `SkipListener` event, a Job may report completion while silently dropping large amounts of data if a developer uses `null` for all errors.

Similarly, do not configure `skip(Exception.class)` just to keep the Job always `COMPLETED`. Doing so can mask writer/database errors, mapping bugs, or system failures.

## 10. Creating `FlatFileItemReader` for `RawOrder`

The reader uses column names to map CSV fields into the raw model. Because all fields are `String`, date and amount conversion happens in the processor.

```java
package example.batch.orders;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

@Configuration
public class OrderReaderConfig {

    @Bean
    @StepScope
    FlatFileItemReader<RawOrder> orderReader() {
        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("orderReader")
                .resource(
                        new ClassPathResource("orders-fixture.csv"))
                .linesToSkip(1)
                .delimited()
                .names(
                        "source_row_id",
                        "order_id",
                        "customer_code",
                        "order_date",
                        "amount",
                        "currency",
                        "order_status")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("source_row_id"),
                        fields.readString("order_id"),
                        fields.readString("customer_code"),
                        fields.readString("order_date"),
                        fields.readString("amount"),
                        fields.readString("currency"),
                        fields.readString("order_status")))
                .build();
    }
}
```

### Role of `@StepScope`

`@StepScope` is useful when the reader needs parameters from `JobParameters` or a dynamic source selected at Step execution time. In this example, the reader uses a fixed file for practice. When moving to a real environment, select input via a backend-verified **dataset ID** instead of accepting an arbitrary file path from a client.

Illustrative late-binding example:

```java
@Value("#{jobParameters['inputDatasetId']}")
String datasetId
```

A trusted service then maps `datasetId` to an allowed readable resource. Never concatenate untrusted values directly into an absolute path or remote URL.

### Errors to Handle at the Reader

- Missing file, unreadable file, or wrong encoding: can fail the Job.
- CSV row with missing/extra columns or broken quotes: can cause a parse error.
- Column names not matching the schema: should fail explicitly rather than guessing data.
- An `amount` column with string `not-a-number`: with this reader, it is still passed into `RawOrder` for the processor to classify the error.

Having the reader return raw items helps classify errors cleanly, but does not eliminate the need to validate the source schema.

## 11. Creating the Target Table and `JdbcBatchItemWriter`

Example PostgreSQL schema:

```sql
CREATE TABLE accepted_order (
    order_id       VARCHAR(64) PRIMARY KEY,
    source_row_id  VARCHAR(128) NOT NULL,
    customer_code  VARCHAR(64) NOT NULL,
    order_date     DATE NOT NULL,
    amount         NUMERIC(18, 2) NOT NULL,
    currency       VARCHAR(3) NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT accepted_order_amount_positive
        CHECK (amount > 0),
    CONSTRAINT accepted_order_currency_allowed
        CHECK (currency IN ('USD', 'EUR'))
);
```

Database constraints **add a layer of protection** rather than replacing processor validation. For instance, if a code bug bypasses the processor, the `amount > 0` constraint still protects the data. However, constraints can roll back the writer transaction, so they should not be treated as the sole data quality reporting mechanism.

The writer uses JDBC with parameter binding rather than concatenating input values directly into SQL:

```java
package example.batch.orders;

import javax.sql.DataSource;
import java.sql.Date;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration
public class OrderWriterConfig {

    @Bean
    JdbcBatchItemWriter<PreparedOrder> orderWriter(
            DataSource dataSource) {

        return new JdbcBatchItemWriterBuilder<PreparedOrder>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO accepted_order (
                        order_id, source_row_id, customer_code,
                        order_date, amount, currency)
                    VALUES (
                        :orderId, :sourceRowId, :customerCode,
                        :orderDate, :amount, :currency)
                    ON CONFLICT (order_id) DO UPDATE SET
                        source_row_id = EXCLUDED.source_row_id,
                        customer_code = EXCLUDED.customer_code,
                        order_date = EXCLUDED.order_date,
                        amount = EXCLUDED.amount,
                        currency = EXCLUDED.currency,
                        updated_at = CURRENT_TIMESTAMP
                    """)
                .itemSqlParameterSourceProvider(order ->
                        new MapSqlParameterSource()
                                .addValue("orderId", order.orderId())
                                .addValue(
                                        "sourceRowId",
                                        order.sourceRowId())
                                .addValue(
                                        "customerCode",
                                        order.customerCode())
                                .addValue(
                                        "orderDate",
                                        Date.valueOf(order.orderDate()))
                                .addValue("amount", order.amount())
                                .addValue("currency", order.currency()))
                .build();
    }
}
```

The SQL above uses PostgreSQL `ON CONFLICT` to illustrate writing an **idempotent upsert** by `order_id`. In a real project, explicitly decide what to do when re-running an existing order:

- **Keep unchanged**, if this is an immutable event.
- **Conditionally update by version**, if data updates are allowed.
- **Report a conflict**, if the new source record contradicts the committed record.
- **Upsert as in the example**, only if business rules allow overwriting.

Do not use upsert merely to "keep the Job from failing" if doing so could hide conflicting data. For practice purposes, this choice reduces duplicate errors when re-running fixtures if tests haven't cleaned tables properly, though tests still need data isolation.

### Why Does the Writer Receive `PreparedOrder`?

The writer does not need to know what `"not-a-number"` means or classify `DRAFT` status codes. If the processor returns an item, the writer can trust that *the defined rules* have been applied. Of course, the writer still needs to handle database errors, unique key constraints, timeouts, and transactions.

## 12. Wiring the Processor into the Step and Job

Create the Step and Job configuration. The reader, processor, and writer beans are injected via dependency injection.

```java
package example.batch.orders;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderImportJobConfig {

    @Bean
    OrderProcessor orderProcessor() {
        return new OrderProcessor();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            OrderProcessor orderProcessor,
            JdbcBatchItemWriter<PreparedOrder> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<RawOrder, PreparedOrder>chunk(
                        100, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .faultTolerant()
                .skip(OrderValidationException.class)
                .skipLimit(10)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

This is a **Spring Batch 5.x** configuration. In other versions, package/constructor names and Job registration may vary.

### Configuration Explanation

- `<RawOrder, PreparedOrder>chunk(...)` explicitly declares the input and output types in the pipeline.
- `reader(orderReader)` reads CSV into `RawOrder`.
- `processor(orderProcessor)` validates and maps. `DRAFT` items returning `null` are filtered.
- `writer(orderWriter)` receives only `PreparedOrder`.
- `faultTolerant()` enables the Step's fault-tolerance mechanism.
- `skip(OrderValidationException.class)` allows skipping only intentional validation errors.
- `skipLimit(10)` caps the total skips allowed in the Step.

With the 9-row fixture having 5 process skips, the Step remains within the limit. When skips exceed the threshold, the Step can fail rather than silently dropping more data.

### Is `skip(FlatFileParseException.class)` Needed?

Not necessarily. This practice project intentionally **does not** skip structurally malformed CSV read errors so as to distinguish:

- **Invalid business data** such as an invalid amount: passed into `RawOrder` and skipped in the processor.
- **Corrupted source format/schema** such as a missing critical column: prefer failing for investigation.

If business rules allow skipping individual malformed CSV lines, you can add `skip(FlatFileParseException.class)` alongside read-skip reporting rules, but verify that the reader can safely continue to the next line.

## 13. Viewing Results in `StepExecution`

After the Job finishes, `JobExecution` and `StepExecution` show the read, filter, skip, and write counts.

For the fixture in Section 3, the expected output is:

```text
Job: importOrdersJob
Status: COMPLETED

Step: importOrdersStep
readCount         = 9
writeCount        = 3
filterCount       = 1
readSkipCount     = 0
processSkipCount  = 5
writeSkipCount    = 0
skipCount         = 5
```

These numbers reflect the example's path: all 9 CSV rows were mapped by the reader to `RawOrder`; 1 row was filtered; 5 rows threw `OrderValidationException` and were skipped; 3 rows were written successfully.

### Common Misconceptions About Counters

- **`readCount`** does not necessarily equal the physical line count in a file for every reader; headers, multiline records, and read skips can affect it.
- **`filterCount`** is different from **`processSkipCount`**. Filtering is typically a valid business decision, whereas skipping is policy-based error handling.
- **`writeCount`** does not always equal `readCount` due to filtering, skipping, or flow logic.
- Under retries/rollbacks, the number of times the processor callback runs does not always equal unique item count or log line count.
- `BatchStatus.COMPLETED` does not guarantee all inputs were accepted; you must also inspect data quality and counters.

For a strict data quality pipeline, you can add a quality gate: if too many items are skipped, mark the Job as failing the criteria even if total skips remain under `skipLimit`. This threshold must be defined based on concrete row counts and business error rates.

## 14. Reporting Validation Errors via `SkipListener`

Incrementing `processSkipCount` alone is not enough if operators need to know which records were rejected. Spring Batch provides `SkipListener<I, O>` to receive events when an item is marked for skipping.

Simple example logging **error code and source key**, without logging full raw contents:

```java
package example.batch.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipLoggingListener
        implements SkipListener<RawOrder, PreparedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipLoggingListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        // READ errors may not have a RawOrder created yet.
        log.warn(
                "batch.order.skip phase=READ exceptionType={}",
                error.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(
            RawOrder raw,
            Throwable error) {

        if (error instanceof OrderValidationException validation) {
            log.warn(
                    "batch.order.skip phase=PROCESS "
                        + "sourceRowId={} errorCode={}",
                    validation.getSourceRowId(),
                    validation.getErrorCode());
        } else {
            log.warn(
                    "batch.order.skip phase=PROCESS "
                        + "sourceRowId={} exceptionType={}",
                    raw.sourceRowId(),
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInWrite(
            PreparedOrder order,
            Throwable error) {

        log.warn(
                "batch.order.skip phase=WRITE "
                    + "sourceRowId={} exceptionType={}",
                order.sourceRowId(),
                error.getClass().getSimpleName());
    }
}
```

Register the bean and attach it to the Step:

```java
@Bean
OrderSkipLoggingListener orderSkipLoggingListener() {
    return new OrderSkipLoggingListener();
}

// In the StepBuilder chain after .skipLimit(10):
.listener(orderSkipLoggingListener)
```

Simply creating a Spring bean without attaching the listener to the Step does not mean callbacks will be invoked.

### Persisting Rejected Items Long-Term

For projects that need to reprocess failed data, design a reporting table/stream containing:

```text
jobExecutionId
stepExecutionId
sourceDatasetId
sourceRowId
phase = READ | PROCESS | WRITE
errorCode
reportedAt
resolutionStatus
```

Reports can be written via JDBC from `SkipListener` using a transactionally consistent sink. In a chunk-oriented Step, skip callbacks are orchestrated by Spring Batch within fault-tolerant processing; note that rollbacks/retries or reporting to a **separate datasource** can cause reported record counts and skip counts to diverge unless deduplication is handled.

Do not make direct HTTP or email calls per failed item inside the listener if that creates non-rollbackable side effects and slows down the chunk. If notifications are needed, write an outbox record within the appropriate transaction and dispatch events in a separate worker.

### Do Not Treat Filtered Items as Rejected Items Unless Requested

`DRAFT` in this lesson is filtered and does not emit `onSkipInProcess`. If business logic needs to report `DRAFT` rows too, add a separate filtered-item recording path or change the contract from "DRAFT is invalid" to a validation exception. Keep one consistent meaning; never mix `filterCount` into `skipCount` on dashboards.

## 15. Unit Testing the Processor: Checking Rules Without Spring Context

Most validation/mapping errors should be caught by simple unit tests. Because `OrderProcessor` is a plain class, `process(...)` can be called directly without `@SpringBootTest` or a database.

JUnit Jupiter and AssertJ example:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void mapsAndNormalizesReadyOrder() {
        RawOrder raw = new RawOrder(
                " r-01 ",
                " ord-1001 ",
                " cus-01 ",
                "2026-11-16",
                " 125.50 ",
                " usd ",
                " ready ");

        PreparedOrder actual = processor.process(raw);

        assertThat(actual).isEqualTo(new PreparedOrder(
                "r-01",
                "ORD-1001",
                "CUS-01",
                LocalDate.of(2026, 11, 16),
                new BigDecimal("125.50"),
                "USD"));
    }

    @Test
    void draftOrderIsFiltered() {
        RawOrder draft = new RawOrder(
                "r-03", "ord-1003", "cus-03",
                "2026-11-16", "45.00", "EUR", "DRAFT");

        assertThat(processor.process(draft)).isNull();
    }

    @Test
    void rejectsNonPositiveAmount() {
        RawOrder raw = readyOrder("0");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("AMOUNT_NOT_POSITIVE"));
    }

    @Test
    void rejectsAmountWithExcessPrecision() {
        RawOrder raw = readyOrder("12.999");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("AMOUNT_TOO_MANY_DECIMALS"));
    }

    @Test
    void rejectsUnsupportedCurrency() {
        RawOrder raw = new RawOrder(
                "r-08", "ord-1008", "cus-08",
                "2026-11-16", "40.00", "GBP", "READY");

        assertThatThrownBy(() -> processor.process(raw))
                .isInstanceOf(OrderValidationException.class)
                .satisfies(error -> assertThat(
                        ((OrderValidationException) error)
                                .getErrorCode())
                        .isEqualTo("CURRENCY_UNSUPPORTED"));
    }

    private static RawOrder readyOrder(String amount) {
        return new RawOrder(
                "r-test", "ord-test", "cus-test",
                "2026-11-16", amount, "USD", "READY");
    }
}
```

This is a representative test suite. You can add tests for `order_date=2026-02-30`, missing customer code, unsupported status, non-numeric amount, out-of-range amount, and IDs containing invalid characters.

### Boundary Testing Is Crucial

A few values to test:

| Field | Case | Expected |
| --- | --- | --- |
| `amount` | `0.01` | Valid. |
| `amount` | `0` or `-0.01` | `AMOUNT_NOT_POSITIVE`. |
| `amount` | `1000000.00` | Valid per exercise limit. |
| `amount` | `1000000.01` | `AMOUNT_OUT_OF_RANGE`. |
| `amount` | `1.2` | Normalized to `1.20`. |
| `amount` | `1.234` | `AMOUNT_TOO_MANY_DECIMALS`. |
| `amount` | `abc` | `AMOUNT_INVALID_FORMAT`. |
| `order_date` | `2026-02-28` | Valid. |
| `order_date` | `2026-02-30` | `ORDER_DATE_INVALID`. |
| `order_status` | `draft` | Filtered after normalization. |
| `order_status` | `UNKNOWN` | `ORDER_STATUS_UNSUPPORTED`. |
| `currency` | ` usd ` | Mapped to `USD`. |
| `currency` | `gbp` | `CURRENCY_UNSUPPORTED` in this exercise. |

Use `@ParameterizedTest` for multiple input sets, while keeping critical cases readable with clear `errorCode` assertions on failure.

## 16. Integration Test: Running Reader → Processor → Writer

Unit tests only prove processor logic. Integration tests confirm that the Step configuration actually uses the processor, the skip policy is applied, Step metrics are accurate, and the writer receives the right model.

With Spring Batch 5.x, `spring-batch-test` provides `@SpringBatchTest`, `JobLauncherTestUtils`, and `JobRepositoryTestUtils`.

Example:

```java
package example.batch.orders;

import java.math.BigDecimal;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderImportIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job job;

    @BeforeEach
    void resetFixture() {
        // Delete data only in a dedicated test DB/schema.
        jdbcTemplate.update("DELETE FROM accepted_order");
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(job);
    }

    @Test
    void validatesFiltersAndWritesPreparedOrders()
            throws Exception {

        var parameters = new JobParametersBuilder()
                .addString(
                        "testRunId",
                        UUID.randomUUID().toString(),
                        true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        StepExecution step = execution.getStepExecutions().stream()
                .filter(value -> "importOrdersStep".equals(
                        value.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(step.getReadCount()).isEqualTo(9);
        assertThat(step.getWriteCount()).isEqualTo(3);
        assertThat(step.getFilterCount()).isEqualTo(1);
        assertThat(step.getReadSkipCount()).isZero();
        assertThat(step.getProcessSkipCount()).isEqualTo(5);
        assertThat(step.getWriteSkipCount()).isZero();
        assertThat(step.getSkipCount()).isEqualTo(5);

        Integer numberOfOrders = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM accepted_order",
                Integer.class);

        assertThat(numberOfOrders).isEqualTo(3);

        String customerCode = jdbcTemplate.queryForObject(
                """
                SELECT customer_code
                  FROM accepted_order
                 WHERE order_id = ?
                """,
                String.class,
                "ORD-1001");

        assertThat(customerCode).isEqualTo("CUS-01");

        BigDecimal amount = jdbcTemplate.queryForObject(
                """
                SELECT amount
                  FROM accepted_order
                 WHERE order_id = ?
                """,
                BigDecimal.class,
                "ORD-1001");

        assertThat(amount)
                .isEqualByComparingTo(new BigDecimal("125.50"));
    }
}
```

### Integration Test Prerequisites

- `src/test/resources/orders-fixture.csv` exists and contains the exact 9 described data rows.
- Spring Boot loads the Job and the reader/processor/writer beans.
- `accepted_order` and the Spring Batch metadata schema have been created in a **test** database, not production.
- `JobLauncherTestUtils` executes the Job synchronously in the test, or the test must wait for the final status if the launcher is asynchronous.
- Tests must not share a table when running in parallel without isolation, because `DELETE` in `@BeforeEach` can wipe another test's data.
- The Job does not auto-launch on context creation because `spring.batch.job.enabled=false`.
- The writer upserts by `order_id` as in the example, with no secondary DB triggers altering row counts.

If stronger isolation is needed, use a dedicated test database/schema or Testcontainers. `@Transactional` on a test method does not by default roll back transactions that Spring Batch opens and commits inside a Step.

### Assert Data, Not Just Counters

A Step can have `writeCount=3` while the writer maps customer, date, or currency incorrectly. Therefore, integration tests should query one or more target records to prove correct mapping and verify no duplicate business keys exist.

If the application does not allow upserts and the writer uses plain `INSERT`, test unique-key conflict behavior according to the real business contract.

## 17. Testing Exceeding `skipLimit` and Non-Skippable Errors

### 17.1. Exceeding the Limit

Configure `skipLimit(2)` with a file containing at least three items causing `OrderValidationException`. When Spring Batch needs to skip past the limit, the Step transitions to failure and the Job typically ends as `FAILED` per the flow.

The test should assert:

- `JobExecution.getStatus() == BatchStatus.FAILED`.
- Step metadata contains failure details.
- Chunks committed before the error **may still contain data**.
- Do not assume every record after the error was read or processed.

This prevents a "Job reports success despite massive source errors."

### 17.2. Non-Skippable Errors

Trigger a database error in the writer, such as a lost connection or missing schema. Because the Step is only configured to skip `OrderValidationException`, infrastructure errors must not be turned into a "bad order" and skipped.

**Principle:** A data error on a single item and an error rendering infrastructure unable to process are two different categories. Do not coerce all exceptions into `OrderValidationException` inside a broad `catch(Exception e)`.

### 17.3. Source Read Errors

If a CSV row is missing columns, `FlatFileParseException` may occur before the processor is invoked. That is not `processSkipCount`. Write separate tests if source data can be structurally corrupted; the policy should define when to skip read errors and when to fail the entire Job.

## 18. Advanced Mapping: Composite Processor

If validation and mapping logic grows large, you can split it into smaller processors:

```text
RawOrder
   |
   v
NormalizeProcessor
   |
   v
ValidationProcessor
   |
   v
MapToPreparedOrderProcessor
   |
   v
PreparedOrder
```

Spring Batch provides `CompositeItemProcessor` to chain delegates in order. This is an option when each stage needs reuse or independent testing.

Structural example:

```java
@Bean
CompositeItemProcessor<RawOrder, PreparedOrder>
compositeOrderProcessor(
        ItemProcessor<RawOrder, NormalizedRawOrder> normalizer,
        ItemProcessor<NormalizedRawOrder, PreparedOrder>
                validatorAndMapper) {

    var composite =
            new CompositeItemProcessor<RawOrder, PreparedOrder>();

    composite.setDelegates(
            java.util.List.of(normalizer, validatorAndMapper));

    return composite;
}
```

`NormalizedRawOrder` is an **application-defined intermediate type**; to run this example you must create that class along with the delegates. The snippet illustrates the organizational mechanism, not a direct replacement for the `OrderProcessor` implemented above.

### Notes on Using a Composite Processor

- If a delegate returns `null`, the item is filtered per the processor contract; subsequent delegates should not receive an already filtered item.
- Exceptions thrown by any delegate are handled by the Step's shared skip/retry policy.
- If a delegate holds mutable state, it is not automatically thread-safe when a Step runs multi-threaded.
- Use a composite when it makes the code clearer; for small problems, a single plain processor with helper methods is usually simpler.

## 19. Should You Use Jakarta Bean Validation?

For a model with many declarative constraints, you can use **Jakarta Bean Validation**:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.DecimalMin;

public record OrderCandidate(
        @NotBlank String orderId,
        @NotBlank String customerCode,
        @NotNull java.time.LocalDate orderDate,
        @NotNull @DecimalMin("0.01")
        java.math.BigDecimal amount) {
}
```

Spring Batch provides validator/processor support for bean checks, such as `BeanValidatingItemProcessor` or `ValidatingItemProcessor` with a matching validator, depending on the version. A flow might look like:

```text
RawOrder
   |
   v
Map to OrderCandidate with typed fields
   |
   v
Bean Validation
   |
   v
PreparedOrder
```

Bean Validation is useful for constraints like `@NotNull`, `@Size`, `@Pattern`, and `@DecimalMin`. However, it does not replace all business logic:

- Parsing dates/amounts from raw text still needs explicit handling.
- The policy that filters `DRAFT` needs a concrete decision.
- The allowed currency set may depend on the contract version.
- Some checks need snapshotted reference data.
- Duplicate/existing-order checks need transactions and idempotency at the writer/database.

If you use a validating processor configured to **filter invalid beans** instead of throwing errors, understand that it can turn invalid records into filtered items rather than skipped items. Choose a policy based on data quality reporting requirements.

## 20. Avoid Calling Remote Services Inside a Chunk Processor

A common anti-pattern:

```java
@Override
public PreparedOrder process(RawOrder raw) {
    // Example to avoid by default:
    Customer customer = remoteCustomerApi.get(raw.customerCode());
    ...
}
```

In a chunk-oriented Step, the processor is usually called inside the chunk transaction. If every item makes an HTTP call, the transaction can stay open for a long time, holding connections/locks and encountering retries/rollbacks. A remote lookup can also return different results between the initial run and a restart.

Alternatives:

1. **Prefetch reference data** in a separate stage and store a snapshot keyed by `JobInstance` or business date.
2. **Query a local/staging table** prepared before the Step runs.
3. **Use a cache with an explicit version/TTL** if data changes rarely and restart semantics allow it.
4. For remote operations with side effects, **write the intent durably to an outbox** and use a separate post-commit dispatcher.

If a remote lookup in the processor cannot be avoided, configure timeouts, bounded retries, monitor transaction duration, and test reprocessing behavior. Even then, this should not be the default approach for a problem that only needs CSV normalization/validation/mapping.

## 21. Correctness on Job Restart

A Job can fail after several chunks have committed. When restarting the same `JobInstance`, Spring Batch relies on metadata and execution context to resume according to the reader/Step's capabilities.

For the processor, key principles are:

- **Deterministic:** the same raw item and same rules version should produce the same `PreparedOrder` or same error code.
- **Stateless:** do not store counters or the current item in mutable fields of a singleton processor without explicit state management.
- **No side effects:** do not send emails, make HTTP POST calls, or update the database directly inside `process()`.
- **Versioned reference data:** if validation depends on rules that change over time, pin the version/dataset when reproducible restarts are required.
- **Contractually idempotent writer:** reprocessed chunks must not create duplicate data or corrupt state.
- **Preserve metadata:** do not delete `BATCH_JOB_EXECUTION`/`ExecutionContext` between failure and restart.

### Example of Non-Deterministic Mapping

```java
return new PreparedOrder(
    raw.sourceRowId(),
    raw.orderId(),
    raw.customerCode(),
    LocalDate.now(),   // Unstable if the date must come from source data.
    ...
);
```

A date from the current clock can change on restart. If the business requires a processing date, obtain it from the CSV or from clearly defined **identifying JobParameters** instead of calling `LocalDate.now()` per item.

Similarly, generating a new UUID inside the processor on every invocation can cause the writer to create new records on retry. Use a stable business key or generate the ID once and store it durably.

## 22. Processor Thread Safety and Performance

The `OrderProcessor` in this lesson uses immutable constants (`Set.of`, `BigDecimal`), local variables, and new result objects, making it suitable for multi-threaded invocation scenarios, assuming helper libraries used here are thread-safe.

Avoid writing:

```java
public class UnsafeProcessor
        implements ItemProcessor<RawOrder, PreparedOrder> {

    private String currentOrderId; // mutable shared state

    @Override
    public PreparedOrder process(RawOrder item) {
        currentOrderId = item.orderId();
        // Another thread may overwrite currentOrderId.
        ...
    }
}
```

When a Step uses `TaskExecutor` or partitioning, the same processor instance may be accessed by multiple threads depending on bean configuration. Keep the processor **stateless**, or use explicit, thread-safe state isolation.

### Performance

Trimming, uppercasing, date parsing, and `BigDecimal` operations are usually much cheaper than database/HTTP round-trips. However, with millions of items:

- `String.matches` regex incurs pattern compilation/matching overhead; if optimization is needed, precompile an immutable `Pattern`.
- Avoid unnecessary back-and-forth formatting and parsing.
- Do not log INFO for every valid item.
- Do not query the database per item to check duplicates if a constraint or batch lookup can be used.
- Measure throughput and GC before optimizing; never relax rules to "benchmark faster."

Increasing thread count may not help if the writer or database is the bottleneck. Before scaling a multi-threaded Step, verify that both reader and writer are thread-safe under that concurrency configuration.

## 23. Logging and Data Quality Reporting

A Job can finish `COMPLETED` even after skipping 5 out of 9 records. In production, that rate may be unacceptable.

Distinguish:

| Signal | Meaning |
| --- | --- |
| `BatchStatus` | Whether the Job/Step completed according to the execution policy. |
| `readCount` | Number of items returned successfully by the reader. |
| `filterCount` | Items excluded under valid business rules. |
| `processSkipCount` | Items skipped due to exceptions in the processor. |
| `writeCount` | Number of items written by the writer per Step statistics. |
| `errorCode` | Classifies why an item was rejected, aiding data remediation. |
| `sourceDatasetId` / `sourceRowId` | Used to reconcile against the source. |
| `jobInstanceId` / `jobExecutionId` | Links to restart history and metadata. |

An example report could be:

```json
{
  "jobName": "importOrdersJob",
  "jobExecutionId": 811,
  "dataset": "orders-fixture",
  "status": "COMPLETED",
  "readCount": 9,
  "writeCount": 3,
  "filterCount": 1,
  "readSkipCount": 0,
  "processSkipCount": 5,
  "writeSkipCount": 0,
  "totalSkipCount": 5
}
```

The numbers above are from the illustrative fixture. In production, do not use each `jobExecutionId` as a metric tag because new values are continuously generated, causing high cardinality. You can log the ID for detailed lookup while tagging metrics with `jobName`, `stepName`, `status`, and bounded error codes.

If the workflow has a quality gate, you can set a threshold on total skips and/or error rate, but you must clearly define the denominator: physical record count, successfully read items, or input count in the manifest. Never infer the physical line count of any file solely from `readCount`.

## 24. Common Mistakes When Adding a Processor

### 24.1. Forgetting to Wire the Processor into the Step

Declaring an `OrderProcessor` bean is not enough:

```java
.reader(orderReader)
// missing .processor(orderProcessor)
.writer(orderWriter)
```

If the Step has matching generic output types or uses raw types, the flow can run without applying the expected validation/mapping. Always attach `.processor(...)` and test the output data.

### 24.2. Sharing One Model for Raw and Prepared Data

If the model already has `amount: BigDecimal` at the reader, `not-a-number` fails before the processor gets a chance to classify it. This is not always wrong, but it differs from this lesson's goal of "processor validates/maps." Clearly choose which layer is responsible for parsing and error reporting.

### 24.3. Using `double` to Parse Money

This easily introduces precision errors and lacks an explicit scale policy. Prefer `BigDecimal`, and define limits and rounding/rejection rules.

### 24.4. Mutating Input in the Processor

Mutating the input object can affect retries, caching, or other components. Returning a new immutable model reduces side effects and simplifies unit testing.

### 24.5. Returning `null` for Every Error

This turns data errors into filters without incrementing `skipCount` or invoking `SkipListener`. You must properly separate "out of processing scope" from "invalid data."

### 24.6. Catching All Exceptions and Turning Them into Data Errors

For example:

```java
try {
    ...
} catch (Exception ex) {
    throw new OrderValidationException("INVALID_ORDER", sourceId);
}
```

This can hide programming bugs or infrastructure errors. Catch only clearly meaningful exceptions such as `NumberFormatException` and `DateTimeParseException` right at the parsing point.

### 24.7. Not Defining Filter/Validation Order

Should an invalid `DRAFT` record be filtered or skipped? Either can be a valid policy, but it must be decided upfront. In this lesson, `DRAFT` is filtered after validating the source key and status; the remaining fields do not need to be valid.

### 24.8. Assuming `skipLimit` Limits Each Phase Separately

By default, `skipLimit(10)` caps the total number of skips across the Step, including read/process/write. It does not grant 10 skips per phase. If you need custom rules, use a `SkipPolicy` with a clear contract.

### 24.9. Relying on Database Constraints Instead of Validation

Constraints serve as a last line of defense, but writer errors can roll back an entire chunk. The processor should catch determinable errors early, providing clear error codes and structured report data.

### 24.10. Forgetting Idempotency on Re-runs

If the writer always inserts with a new key, a restart can write duplicates. Design business keys and conflict handling properly; never generate random IDs in the processor for records that should have a stable identity.

### 24.11. Logging Full Raw Data

CSV files may contain emails, phone numbers, addresses, or PII. Log only allowed `sourceRowId` and error codes; keep raw payloads in a secured quarantine area if genuinely needed.

### 24.12. Checking Only Whether the Job `COMPLETED`

A Job can finish even after filtering or skipping large numbers of records. Processor unit tests, Step counters, rejection reports, and actual writer output in the database all need appropriate verification.

## 25. Extension Exercises: Adding New Business Rules

After running the example, complete the following tasks:

### Exercise A – Business Date Validation

The Job receives `businessDate` from `JobParameters`. Only orders with `order_date <= businessDate` are valid.

- Mark `businessDate` as an identifying parameter if it represents the unit of work.
- Use `@StepScope` or an execution-configured component to pass the date into the processor.
- Do not use `LocalDate.now()` per item.
- Add error code `ORDER_DATE_AFTER_BUSINESS_DATE`.
- Test a date equal to, before, and after the cutoff.

### Exercise B – Separating Filter and Rejection Reports

Add a `CANCELLED` status that is filtered like `DRAFT`, while aggregating counts per filter reason.

- Design business-meaningful filter counters.
- Do not invoke `onSkipInProcess` for filtered items by default.
- If audit logs must be saved, do not create non-idempotent side effects inside `process()`.
- Assert `filterCount` and `processSkipCount` independently.

### Exercise C – Duplicate Orders

Two CSV rows share the same `order_id` but have different `amount` values.

- Determine whether this is a data quality error or a valid update.
- Do not try to solve this with a mutable `Set` in a singleton processor if the Step uses concurrency or restarts.
- Consider unique constraints, staging tables, and versioned policies.
- Test both non-conflicting and conflicting data cases.

### Exercise D – Raising the Quality Threshold

Test a fixture containing 50 error records out of 100 rows with `skipLimit(10)`.

- Predict the Step status when exceeding the limit.
- Inspect data already committed in earlier chunks.
- Confirm the report contains only persistently recorded rejections.
- Add a percentage-based quality gate, with the denominator taken from the input manifest.

### Exercise E – Restart

Intentionally trigger a writer error after one or more chunks.

- Keep the same identifying `JobParameters` when restarting.
- Do not delete metadata between runs.
- Ensure the processor produces deterministic results.
- Verify there are no duplicate orders after restarting.
- Compare the `JobInstance` and two distinct `JobExecution`s in the metadata.

## 26. Project Implementation Map

A file structure can be organized as follows:

```text
src/
├── main/
│   └── java/example/batch/orders/
│       ├── RawOrder.java
│       ├── PreparedOrder.java
│       ├── OrderValidationException.java
│       ├── OrderProcessor.java
│       ├── OrderReaderConfig.java
│       ├── OrderWriterConfig.java
│       ├── OrderImportJobConfig.java
│       └── OrderSkipLoggingListener.java
└── test/
    ├── java/example/batch/orders/
    │   ├── OrderProcessorTest.java
    │   └── OrderImportIT.java
    └── resources/
        └── orders-fixture.csv
```

The classes in this structure are examples to guide organization. Real projects may split modules into `batch-domain`, `batch-infrastructure`, and `batch-application`, or use feature-based packages.

Recommended build order:

1. Finalize the CSV input contract and business statuses.
2. Create `RawOrder` and `PreparedOrder`.
3. Create the exception holding `errorCode`.
4. Write the pure processor and unit tests.
5. Create the reader mapping Strings without parsing business data too early.
6. Create the writer with parameter binding and constraints.
7. Wire the Job/Step and choose the skip policy.
8. Attach `SkipListener` for traceable data errors.
9. Run integration tests on an isolated DB, comparing counters with the target table.
10. Test boundary errors, retry/restart, and exceeding the skip limit.
11. Test larger datasets, monitoring throughput and data quality.
12. Finalize the workflow for handling/reprocessing rejected items before scheduling the Job in production.

**The complete outcome of this practice project** is not just a compilable `ItemProcessor` class. It is a pipeline with an explicit contract: which data source is read, how records are normalized, the rules for acceptance/filtering/rejection, how normalized data is written, and which metrics operators use to inspect results.

## References

- [Spring Batch Reference – Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): principles of `ItemProcessor<I, O>`, filtering, and item transformation.
- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): read, process, write, and transaction lifecycle.
- [Spring Batch Reference – Flat File Item Readers](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): configuring `FlatFileItemReader` for CSV and text sources.
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault-tolerant Step, `skipLimit`, and skippable exceptions.
- [Spring Batch Reference – Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): `SkipListener` and related listeners.
- [Spring Batch Reference – Bean Validation](https://docs.spring.io/spring-batch/reference/processor.html): validation approaches in the processing pipeline.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test`, running Jobs/Steps, and verifying results.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction and propagation principles.

