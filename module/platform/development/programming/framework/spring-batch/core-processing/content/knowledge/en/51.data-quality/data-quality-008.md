# Data Type and Format Validation in Spring Batch Core Processing

A batch job can read an entire file and report `COMPLETED` while producing wrong output data: date `2026-02-30` silently rolled into another date, `1,234` misread as a decimal or grouped number, identifier `000123` losing leading zeros, or prices rounded without the provider knowing. **Data type and format validation** verifies that input data conforms to the type, syntax, precision, and representation contract before converting it into business objects.

In Spring Batch, you must decide **where to validate** along `ItemReader → ItemProcessor → ItemWriter`, which errors fail the job, which errors are skippable, how to track invalid records, and how to keep outcomes consistent across restarts. This article explains those choices through a CSV order-import example, using **Spring Batch 5.2.x, Spring Framework 6.x, and Java 17** as the baseline for Java examples.

## 1. Distinguishing Three Validation Levels

| Level | What Is Checked? | Example Failures | Suitable Location |
| --- | --- | --- | --- |
| **Structure / schema** | Encoding, header, column count, order, delimiter, schema version | Missing `quantity` column, a CSV line with 5 fields instead of 4 | Preflight, `LineTokenizer`, `ItemReader` |
| **Data type / format** | Can text values parse accurately into Java types under a published format? | `quantity=three`, `businessDate=2026-02-30`, `unitPrice=12.345` | `FieldSetMapper` or `ItemProcessor` |
| **Domain / semantic** | Do properly typed values satisfy business rules? | `quantity=0`, order already exists, date outside processing period | `ItemProcessor`, business validator, database constraints |

For instance, `2026-11-15` is a valid date in type and format yet may be the wrong business period if the job only accepts `2026-11-14`. Conversely, `2026-02-30` is a non-existent calendar value; you should not wait for the business layer to catch it.

An easily controlled design:

```text
File / API / Database
       |
       v
Preflight: encoding, header, schema, data source
       |
       v
ItemReader + LineTokenizer
       | structural error --> read error
       v
RawOrderRow (String fields)
       |
       v
ItemProcessor: strict parsing and format validation
       | type conversion error --> process error
       v
TypedOrderRow (LocalDate, int, BigDecimal)
       |
       v
Domain validation / reconciliation
       | business rule error --> fail, skip, or filter per policy
       v
ItemWriter + database constraints
       |
       v
Committed data
```

Not every application needs three separate Java layers. For simple formats, `FieldSetMapper` can convert types directly in the reader. However, keeping raw strings until the processor cleanly separates **file structure errors** from **invalid value errors**, simplifies unit testing, and supports code-based data quality reporting.

## 2. Starting with a Data Contract

Suppose a source provides CSV:

```csv
orderId,businessDate,quantity,unitPrice
ORD-000101,2026-11-15,2,45.50
ORD-000102,2026-11-15,5,10.00
ORD-000103,2026-11-15,1,99.99
```

Contract for the example:

| Field | Target Type | Accepted Format | Additional Rules |
| --- | --- | --- | --- |
| `orderId` | `String` | `ORD-` followed by exactly 6 ASCII digits | Do not strip whitespace or alter casing |
| `businessDate` | `LocalDate` | ISO `uuuu-MM-dd`, e.g., `2026-11-15` | Must exist on the calendar; valid year/month/day |
| `quantity` | `int` | ASCII digits only, no sign or grouping separator | 1 to 999,999; disallow `03` |
| `unitPrice` | `BigDecimal` | Decimal point, 0–2 fractional digits, no grouping separator | Greater than 0; up to 8 integer digits |

Beyond columns, the contract must also specify **UTF-8**, comma delimiter, quoted-field rules, mandatory header, schema version, `null` representation, blank lines, column ordering, and business date definition. Decisions like accepting `45.5` and normalizing to `45.50` versus requiring literal `45.50` must be settled before coding.

When receiving multi-country data, avoid guessing number formats via `Locale.getDefault()`. `1.234,56` might represent one thousand two hundred thirty-four point five six in one locale, yet violates the monetary format chosen above. Likewise, an identifier like `00123` should usually remain a `String`; converting it to `int` drops leading zeros.

## 3. Choosing Semantically Right Java Types

| Data | Usually Suitable Type | Common Mistake |
| --- | --- | --- |
| Business date without time | `LocalDate` | Attaching unnecessary timezone, shifting dates |
| Timestamp representing an instant | `Instant` or `OffsetDateTime` | Parsing strings missing offset and assuming UTC |
| Integer quantities | `int`/`long`/`BigInteger` by bounds | Truncating `3.5` to `3` or overflowing |
| Exact money/decimals | `BigDecimal` | `double`/`float` and unintended rounding |
| Order ID, SKU, account number | `String` or value object | Stripping leading zeros, altering format |
| Bounded status values | `enum` with explicit mapping | Accepting arbitrary text and failing too late |
| Boolean from text | `Boolean` with defined tokens | Implicitly accepting `yes`, `1`, `Y` when contract only permits `true`/`false` |

For dates, parse with a strict parser:

```java
DateTimeFormatter format = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate day = LocalDate.parse("2026-11-15", format);
```

`ResolverStyle.STRICT` rejects non-existent dates such as `2026-02-30`. In the pattern, `uuuu` is proleptic year; `yyyy` is year-of-era, which requires care under strict parsing without an era field. `DateTimeFormatter.ISO_LOCAL_DATE` is also appropriate when the contract uses ISO dates.

For money:

```java
BigDecimal price = new BigDecimal("45.50");
```

Never use `new BigDecimal(45.50)` with a `double` literal, because floating-point values may fail to represent decimal numbers accurately. Decimal scale, precision, and rounding policies should be explicitly published.

## 4. Reading CSV as Raw Strings with `FlatFileItemReader`

The example below uses `FlatFileItemReaderBuilder` and `@StepScope`. The reader only splits fields without coercing dates or numbers yet:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OrdersReaderConfig {

    public record RawOrderRow(
            String orderId,
            String businessDate,
            String quantity,
            String unitPrice) {
    }

    @Bean
    @StepScope
    public FlatFileItemReader<RawOrderRow> rawOrdersReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrderRow>()
                .name("rawOrdersReader")
                .resource(new FileSystemResource(inputFile))
                .encoding(StandardCharsets.UTF_8.name())
                .linesToSkip(1)
                .skippedLinesCallback(header -> {
                    String expected =
                            "orderId,businessDate,quantity,unitPrice";
                    if (!expected.equals(header)) {
                        throw new IllegalArgumentException(
                                "Unexpected CSV header");
                    }
                })
                .delimited()
                .delimiter(",")
                .names("orderId", "businessDate", "quantity", "unitPrice")
                .fieldSetMapper(fields -> new RawOrderRow(
                        fields.readString("orderId"),
                        fields.readString("businessDate"),
                        fields.readString("quantity"),
                        fields.readString("unitPrice")))
                .build();
    }
}
```

By returning `RawOrderRow`, a string like `unitPrice="12.345"` is neither rounded nor cast to `double` before validation runs. `DelimitedLineTokenizer` splits CSV fields; when configured strict on token count (strict by default), it reports errors on lines with missing or extra columns. `FlatFileItemReader` wraps line tokenizing/mapping failures in `FlatFileParseException`, identifying which line failed to parse.

The header callback is a **file-level check**: if the header has the wrong order or format, the reader refuses to continue as if the file were valid. `linesToSkip(1)` alone only skips the first line without verifying column names. The callback above intentionally demands an exact header match; if BOMs or multiple schema versions exist, design explicit preflight normalization/detection rather than accidentally accepting a different header.

This example reads a file chosen via `JobParameters`. In operational applications, restrict `inputFile` to authorized directories/sources, block path traversal, and record the source's checksum or version. CSV files with quoted fields containing newlines need an appropriate `RecordSeparatorPolicy`; never use `line.split(",")` to parse quoted fields manually.

## 5. Validation Processor: Strict Parsing into Typed DTOs

Define the output DTO and an exception carrying a stable reason code:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record ValidOrderRow(
        String orderId,
        LocalDate businessDate,
        int quantity,
        BigDecimal unitPrice) {
}
```

```java
public class InvalidOrderRowException extends RuntimeException {
    private final String reasonCode;

    public InvalidOrderRowException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Type conversion and format checking inside an `ItemProcessor`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;

public class OrderTypeAndFormatProcessor
        implements ItemProcessor<OrdersReaderConfig.RawOrderRow, ValidOrderRow> {

    private static final Pattern ORDER_ID =
            Pattern.compile("ORD-[0-9]{6}");
    private static final Pattern QUANTITY =
            Pattern.compile("[1-9][0-9]{0,5}");
    private static final Pattern PRICE =
            Pattern.compile("(?:0|[1-9][0-9]{0,7})(?:\\.[0-9]{1,2})?");

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public ValidOrderRow process(OrdersReaderConfig.RawOrderRow row) {
        if (row == null) {
            throw new InvalidOrderRowException("MISSING_ROW");
        }
        if (!matches(ORDER_ID, row.orderId())) {
            throw new InvalidOrderRowException("INVALID_ORDER_ID");
        }

        LocalDate date;
        try {
            date = LocalDate.parse(row.businessDate(), DATE_FORMAT);
        } catch (DateTimeParseException | NullPointerException e) {
            throw new InvalidOrderRowException("INVALID_DATE_FORMAT");
        }

        if (!matches(QUANTITY, row.quantity())) {
            throw new InvalidOrderRowException("INVALID_QUANTITY_FORMAT");
        }
        // Regex caps at 6 digits so int cannot overflow.
        int quantity = Integer.parseInt(row.quantity());

        if (!matches(PRICE, row.unitPrice())) {
            throw new InvalidOrderRowException("INVALID_PRICE_FORMAT");
        }
        BigDecimal price = new BigDecimal(row.unitPrice());
        if (price.signum() <= 0) {
            throw new InvalidOrderRowException("NON_POSITIVE_PRICE");
        }
        // Only normalize scale; do not round.
        price = price.setScale(2);

        return new ValidOrderRow(row.orderId(), date, quantity, price);
    }

    private static boolean matches(Pattern regex, String value) {
        return value != null && regex.matcher(value).matches();
    }
}
```

Key decisions in this snippet:

- `ORD-000101` is valid; `ord-000101`, `ORD-101`, and extra whitespace are rejected.
- `2026-11-15` is valid; `2026-02-30`, `2026/11/15`, and empty strings are rejected.
- `3` is valid; `0`, `-3`, `3.0`, `03`, and `three` are invalid per the sample contract.
- `45.5` is valid and normalized to `45.50`; `12.345`, `1,234.50`, `1e3`, and `-2.00` are rejected.
- `0.00` has valid numeric syntax yet fails the business rule requiring positive price.

These are **illustrative rules**, not enforced by Spring Batch itself. If a partner is permitted to send `0003` or grouping separators, update the data contract, parser, and test suite together. Avoid undocumented calls to `trim()`, `replace(",", ".")`, or case folding.

## 6. Convert Types in the Reader or the Processor?

Spring Batch provides `FieldSet.readString()`, `readInt()`, `readLong()`, `readBigDecimal()`, `readDate()`, etc., to parse right inside the mapping layer. For example:

```java
// Illustrative FieldSetMapper, with TypedInput defined by the application.
fields -> new TypedInput(
        fields.readString("orderId"),
        fields.readDate("businessDate", "yyyy-MM-dd"),
        fields.readInt("quantity"),
        fields.readBigDecimal("unitPrice"))
```

If `readInt` fails to convert `three`, the error occurs in the reader; depending on wrapping and skip policy, it can become a **read skip**. If the reader returns `RawOrderRow` and the processor rejects `three`, it becomes a **process skip** when permitted. `FieldSet.readBigDecimal()` can parse `12.345` as a technically valid decimal even though the contract permits at most two fractional digits, so extra validation is still needed.

| Scenario | Parsing in Reader Mapper | Parsing in Processor |
| --- | --- | --- |
| Missing/extra CSV columns | Read error | Still a read error because raw object cannot be built |
| `quantity=three` | Read error if mapper calls `readInt` | Process error with code `INVALID_QUANTITY_FORMAT` |
| `unitPrice=12.345` | May succeed unless scale is checked | Rejected by regex contract |
| `businessDate=2026-02-30` | Depends on mapper parser/date policy | Strict parser rejects cleanly |
| Duplicate order ID | Usually needs business logic outside reader | Well-suited to processor/service check |

Early parsing in the reader keeps code concise for stable files; parsing in the processor gives clear reason codes and lets logic be reused across input sources. **Validation placement affects `readSkipCount` vs. `processSkipCount`**, so quality dashboards must know which design the pipeline uses.

## 7. Bean Validation for Already-Typed Objects

With `jakarta.validation`, constraints can be declared on DTOs:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

public record TypedOrder(
        @NotBlank
        @Pattern(regexp = "ORD-[0-9]{6}")
        String orderId,

        @NotNull
        LocalDate businessDate,

        @Min(1)
        int quantity,

        @NotNull
        @DecimalMin("0.01")
        @Digits(integer = 8, fraction = 2)
        BigDecimal unitPrice) {
}
```

Spring Batch provides `BeanValidatingItemProcessor<T>`. It requires the Jakarta Bean Validation API and a compatible provider such as Hibernate Validator. With Spring Boot, the dependency is typically `spring-boot-starter-validation`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

```java
import org.springframework.batch.item.validator.BeanValidatingItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
BeanValidatingItemProcessor<TypedOrder> typedOrderValidator()
        throws Exception {
    BeanValidatingItemProcessor<TypedOrder> p =
            new BeanValidatingItemProcessor<>();
    p.setFilter(false);
    p.afterPropertiesSet();
    return p;
}
```

Bean Validation does not itself specify how to parse `"1.234,56"`, nor does it turn date strings into `LocalDate` using project formats. It needs an **already properly typed** object; you can chain parser and validator via `CompositeItemProcessor`.

The choice `setFilter(false)` matters: constraint violations throw `ValidationException`, which can fail or skip per policy. With `setFilter(true)`, the processor returns `null` for violating objects, incrementing `filterCount`; that is appropriate only if the business truly treats invalid records as **normal filters**. When measuring input quality, silently filtering out all failures strips skip reports of meaning.

## 8. Configuring Controlled Skip in a Chunk Step

Example Spring Batch 5.2.x configuration using the reader and validator above, with a writer supplied by the application:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrdersStepConfig {

    @Bean
    public OrderTypeAndFormatProcessor orderTypeAndFormatProcessor() {
        return new OrderTypeAndFormatProcessor();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<OrdersReaderConfig.RawOrderRow> rawOrdersReader,
            OrderTypeAndFormatProcessor orderTypeAndFormatProcessor,
            ItemWriter<ValidOrderRow> validOrdersWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrdersReaderConfig.RawOrderRow, ValidOrderRow>
                        chunk(50, transactionManager)
                .reader(rawOrdersReader)
                .processor(orderTypeAndFormatProcessor)
                .writer(validOrdersWriter)
                .faultTolerant()
                .skip(FlatFileParseException.class)
                .skip(InvalidOrderRowException.class)
                .skipLimit(20)
                .listener(new OrderQualitySkipListener())
                .build();
    }
}
```

In this setup:

1. Tokenizing/mapping errors on a CSV line can become `FlatFileParseException` in the read phase.
2. Format or type errors in `OrderTypeAndFormatProcessor` throw `InvalidOrderRowException` in the process phase.
3. Both types are skippable within a combined limit of `20` across read/process/write.
4. Infrastructure errors such as database disconnections, unreadable input resources, or exceptions outside the skip policy are **not automatically skipped**.

`validOrdersWriter` must be a real application bean, such as a JDBC writer with proper constraints and transactions. This snippet assumes `JobRepository` and `PlatformTransactionManager` are properly configured; if multiple readers/writers of the same type exist, use `@Qualifier`. A header validation failure when opening the reader is a **file-level** error and should not be treated as a single skippable parse row to continue ingesting under a wrong schema.

**`skipLimit` caps total skips**, without separate quotas for read and process. Workflows demanding strict accuracy can choose fail-fast on bad data instead of enabling skips.

## 9. Logging/Quarantining Bad Records with `SkipListener`

`SkipListener` provides dedicated callbacks when an item is actually skipped:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public class OrderQualitySkipListener
        implements SkipListener<OrdersReaderConfig.RawOrderRow, ValidOrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderQualitySkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn("batch.validation.skipped phase=read line={} type={}",
                    parseError.getLineNumber(),
                    parseError.getClass().getSimpleName());
        } else {
            log.warn("batch.validation.skipped phase=read type={}",
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInProcess(
            OrdersReaderConfig.RawOrderRow row, Throwable error) {
        if (error instanceof InvalidOrderRowException invalid) {
            log.warn(
                    "batch.validation.skipped phase=process reason={}",
                    invalid.getReasonCode());
        } else {
            log.warn("batch.validation.skipped phase=process type={}",
                    error.getClass().getSimpleName());
        }
    }

    @Override
    public void onSkipInWrite(ValidOrderRow item, Throwable error) {
        log.warn("batch.validation.skipped phase=write type={}",
                error.getClass().getSimpleName());
    }
}
```

`FlatFileParseException.getLineNumber()` reports the failing line when the reader parses; if line numbers are also needed for **processor** errors, the raw DTO or reader must retain position metadata appropriately. Processor exceptions do not automatically carry physical line numbers.

Never log raw `row`, `error.getMessage()`, or `FlatFileParseException.getInput()` if they may contain PII, tokens, or payment details. Data quality events should record **`jobExecutionId`, `stepExecutionId`, authorized source name, error code, record position, and schema version**; raw data belongs in an access-controlled quarantine area with clear retention.

Writing to quarantine may be an external side effect outside the chunk transaction. On retry/restart, events can replay; use an idempotency key to avoid duplicate error rows. Do not count `ItemReadListener.onReadError` as skipped records: retries or rollbacks can invoke error callbacks multiple times.

## 10. End-to-End Example and Expected Metrics

Suppose the file is:

```csv
orderId,businessDate,quantity,unitPrice
ORD-000101,2026-11-15,2,45.50
ORD-000102,2026-02-30,3,20.00
ORD-000103,2026-11-15,three,15.00
ORD-000104,2026-11-15,1,12.345
ORD-000105,2026-11-15,5,10.00
ORD-000106,2026-11-15,1,8.25,EXTRA
ORD-000107,2026-11-15,1,99.99
```

| Physical Line | Outcome | Classification |
| --- | --- | --- |
| 1 | Exact header; not counted as an item | Header validation |
| 2 | Written | Valid |
| 3 | Non-existent date | Process skip |
| 4 | Invalid quantity format | Process skip |
| 5 | Price has three fractional digits | Process skip |
| 6 | Written | Valid |
| 7 | Extra CSV column | Read skip |
| 8 | Written | Valid |

If the writer succeeds without rollbacks affecting final counts, expected `StepExecution` counters are:

```text
readCount          = 6
writeCount         = 3
filterCount        = 0
readSkipCount      = 1
processSkipCount   = 3
writeSkipCount     = 0
skipCount          = 4
```

When moving format parsing into the reader's mapper, some type errors shift from `processSkipCount` to `readSkipCount`. Dashboards should therefore track **total skips** and **reason codes**, while understanding where validation runs. `filterCount` is for processors returning `null`, not added to `skipCount`. A successful retry does not turn an item into a skip.

## 11. Testing Validation Logic Without a Spring Context

Because the processor is a plain Java class, it can be unit-tested quickly with JUnit Jupiter:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderTypeAndFormatProcessorTest {

    private final OrderTypeAndFormatProcessor processor =
            new OrderTypeAndFormatProcessor();

    @Test
    void acceptsStrictDateIntegerAndDecimal() throws Exception {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000101", "2026-11-15", "2", "45.5");

        ValidOrderRow actual = processor.process(input);

        assertEquals("ORD-000101", actual.orderId());
        assertEquals(LocalDate.of(2026, 11, 15), actual.businessDate());
        assertEquals(2, actual.quantity());
        assertEquals(new BigDecimal("45.50"), actual.unitPrice());
    }

    @Test
    void rejectsImpossibleCalendarDate() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000102", "2026-02-30", "1", "10.00");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_DATE_FORMAT", ex.getReasonCode());
    }

    @Test
    void rejectsPriceWithUnexpectedScale() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000103", "2026-11-15", "1", "12.345");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_PRICE_FORMAT", ex.getReasonCode());
    }

    @Test
    void rejectsNonIntegerQuantityToken() {
        var input = new OrdersReaderConfig.RawOrderRow(
                "ORD-000104", "2026-11-15", "3.0", "10.00");

        var ex = assertThrows(InvalidOrderRowException.class,
                () -> processor.process(input));

        assertEquals("INVALID_QUANTITY_FORMAT", ex.getReasonCode());
    }
}
```

Expand with `@ParameterizedTest` for edge cases:

| Field | Input | Expected per Sample Contract |
| --- | --- | --- |
| Date | `2024-02-29` | Valid (leap year) |
| Date | `2025-02-29`, `2026-13-01` | Rejected |
| Date | `15/11/2026`, `2026/11/15` | Rejected |
| Quantity | `1`, `999999` | Valid |
| Quantity | `0`, `-1`, `1000000`, `1.5` | Rejected |
| Price | `0.01`, `45.50`, `45.5` | Valid |
| Price | `0.00`, `45.555`, `1,000.00` | Rejected |
| ID | `ORD-000101` | Valid |
| ID | `ord-000101`, `ORD-101` | Rejected |

### What Should Integration Tests Add?

Unit tests only prove the processor works; they do not prove CSV tokenization, charset, headers, `@StepScope`, and skip policies are wired properly. Using real fixtures in `src/test/resources` or intentional temp files, run the step with `spring-batch-test` and verify:

- A wrong header fails the job/step fast per file policy.
- Rows with extra/missing columns go to read errors; bad prices/dates go to process errors.
- `readCount`, `writeCount`, `readSkipCount`, and `processSkipCount` match the fixture.
- The writer receives only qualifying `ValidOrderRow` instances.
- Restarts do not duplicate or drop data due to checkpoint/schema changes.

In tests running jobs with `JobRepository`, use an isolated test database; a `JobInstance` that already finished `COMPLETED` will not normally relaunch with the same identifying `JobParameters`.

## 12. File Preflight and Validating `JobParameters`

Do not wait until 80,000 records are processed to discover the entire file has the wrong delimiter, schema, or data period. Check file-level errors early:

1. Resource exists, is within an authorized path, and has a reasonable size.
2. Encoding and BOM match the contract; decoding errors have an explicit policy.
3. Header, column count, schema version, trailer/checksum match expectations.
4. `inputFile` and `businessDate` belong to an authorized period, tenant, and source.
5. File has an immutable version/checksum for faithful restarts.

Spring Batch provides `JobParametersValidator` to check parameters before the job runs:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFile is required");
        }

        String businessDate = parameters.getString("businessDate");
        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }
    }
}
```

Attach via job builder:

```java
new JobBuilder("importOrders", jobRepository)
        .validator(new ImportJobParametersValidator())
        .start(importOrdersStep)
        .build();
```

This example only shows required fields; real projects should also check date format and file access rules. `JobParametersValidator` validates **job-level inputs**, not individual CSV rows.

## 13. Controlled Format Normalization

If the system accepts multiple valid formats, define **formats by source/version**:

```text
Source A: 2026-11-15  -- ISO yyyy-MM-dd --> LocalDate
Source B: 15/11/2026  -- dd/MM/uuuu    --> LocalDate
                                            |
                                            v
                                   2026-11-15 (ISO output)
```

Never blindly try every conceivable format. When parsing numbers with a locale's `NumberFormat`, confirm the parser **consumed the entire input** without ignoring trailing garbage. If input is a timestamp rather than a date, convert to the business timezone before extracting `LocalDate`:

```java
Instant timestamp = Instant.parse("2026-11-15T23:30:00Z");
LocalDate businessDay = timestamp
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate();
```

For example, late-night UTC timestamps can belong to the next calendar day in Vietnam. For currencies, if grouping separators or alternative decimal marks are allowed, the CSV tokenizer, locale, and fractional digit rules must all align with the contract. Every normalization step such as trimming or case folding should be tested and tracked with its own metrics when assessing source quality.

## 14. Fail, Skip, Filter, and Quarantine: Choosing by Business Risk

| Error Type | Typical Appropriate Handling | Reason |
| --- | --- | --- |
| Wrong file-wide header/schema/encoding | Fail-fast | Cannot tell if columns still map properly |
| A few isolated records with bad format | Bounded skip + quarantine if policy permits | Preserves valid input while reporting bad data |
| Wrong price on a critical transaction | Fail or strictly controlled skip | Never write guessed values; avoid monetary discrepancies |
| Valid record outside ingestion scope | Intentional filter | Not a data error |
| DB/API disconnect or metadata write failure | Fail/retry by infra error category | Format skips cannot fix infrastructure outages |
| Abnormally high invalid rate | Fail quality gate | Prevent job from completing with untrustworthy results |

Beyond an absolute `skipLimit`, systems can enforce a **percentage quality gate** such as at most 1% bad records. Define the denominator explicitly: physical lines, successfully read items, or `readCount + readSkipCount`. The ratio must fit the meaning of your reader/processor, not a one-size-fits-all formula across jobs.

A minimal quarantine record might look like:

```json
{
  "jobExecutionId": 4812,
  "stepExecutionId": 9207,
  "source": "orders-2026-11-15-v1.csv",
  "recordNumber": 1234,
  "phase": "process",
  "reasonCode": "INVALID_DATE_FORMAT",
  "schemaVersion": "1"
}
```

This is an **application-defined** schema, not an auto-generated Spring Batch event. If original values must be kept for remediation, use a proper store and access controls; never dump full raw records into shared logs. The quarantine writer also needs idempotency across replays/restarts.

## 15. Monitoring Quality from `StepExecution`

Useful counters for reporting:

| Counter | Meaning |
| --- | --- |
| `readCount` | Items read successfully |
| `writeCount` | Items processed by the writer successfully |
| `filterCount` | Items for which processor returned `null` |
| `readSkipCount` | Failed items skipped in read |
| `processSkipCount` | Failed items skipped in process |
| `writeSkipCount` | Failed items skipped in write |
| `skipCount` | Sum of `readSkipCount + processSkipCount + writeSkipCount` |
| `rollbackCount` | Rollbacks recorded by the framework |

You can log a summary in `StepExecutionListener.afterStep`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class DataQualityStepListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(DataQualityStepListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "step={} status={} read={} write={} filter={} " +
                "readSkip={} processSkip={} writeSkip={} rollback={}",
                step.getStepName(), step.getStatus(),
                step.getReadCount(), step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(), step.getProcessSkipCount(),
                step.getWriteSkipCount(), step.getRollbackCount());
        return null; // Keep current ExitStatus.
    }
}
```

Register the listener in `StepBuilder` via `.listener(new DataQualityStepListener())`. History can be queried via `JobExplorer` or the `BATCH_STEP_EXECUTION` table in the JDBC repository. Counts belong to **one `StepExecution`**; on restarts there can be multiple executions, so select the right IDs to avoid mis-summing or double-counting business records.

`writeCount=0` does not itself prove the job failed because an empty file might be valid; conversely, `COMPLETED` with thousands of skips can still violate quality SLAs. Reports should combine `BatchStatus`, counters, source, schema version, business period, allowed thresholds, and expected record counts.

## 16. Restart and Reproducibility of Validation

Stateful readers like `FlatFileItemReader` can store their read position in `ExecutionContext`, allowing restarts from the saved checkpoint. If the source file is reordered or has lines added/removed between failure and restart, the checkpoint can point to a **different item**. If a modified parser/validator is deployed between runs, the same string can also produce a different outcome.

Key practices:

1. Bind inputs to a logical name and **immutable checksum/version**; verify the source stayed unchanged before restarting.
2. Version type/format contracts, with a migration process when rules change.
3. Never rely on default locale, timezone, or clock for parsing that must be reproducible.
4. Design writers to be idempotent by business key, especially when writing to APIs/queues outside the repository transaction.
5. When the goal is **restarting the same `JobInstance`**, keep identifying `JobParameters` unchanged; do not inject UUIDs/timestamps that create a new instance.

Do not rely solely on `StepExecution.writeCount` to prove target data has no duplicates: an item can be retried after rollback, and external systems can receive side effects before the checkpoint commits.

## 17. Common Pitfalls and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `2026-02-30` converted to another date | Lenient/smart date parser | Use `ResolverStyle.STRICT` and test impossible dates |
| `1.234,56` parses differently across machines | Relying on default locale | Pin format and locale in contract |
| Monetary rounding errors | Using `float`/`double` | `BigDecimal` from strings, explicit scale/rounding |
| `000123` loses leading zeros | Parsing identifiers as numbers | Keep as `String` |
| `readSkipCount` shifts during parser refactor | Moving validation from processor to reader | Report total skips and reason codes; track validation layer |
| Wrong header still gets processed | Only using `linesToSkip(1)` | Preflight/header callback to fail-fast |
| Cannot identify failing line in processor | Raw DTO lacks source/line number | Attach source metadata when tracing is needed |
| Error callbacks exceed skip count | Retries/rollbacks | Rely on `StepExecution` counters and `SkipListener` |
| CI tests produce different dates | Default timezone/locale/clock | Pin environment settings |
| Records written twice after restart | File changed or non-idempotent writer | Use checksums, checkpoints, and business keys |
| Duplicate events in quarantine | Writing outside transaction / retries | Idempotency keys and deduplication |
| Many invalid rows yet job still `COMPLETED` | Overly broad skip policy, missing quality gate | Skip/ratio thresholds, alerts, and quality checks |

## 18. References

Code examples use **Spring Batch 5.2.x**. With Spring Batch 6.x, some packages/APIs changed, so consult documentation matching your project's version; the principles of type/format validation, fail/skip, and reproducible input still apply.

- [Spring Batch 5.2 — FlatFileItemReader and flat file handling](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch 5.2 — Item processing and validating input](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-processing.html)
- [Spring Batch 5.2 — Configuring skip logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch 5.2 — Intercepting execution and SkipListener](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 API — FlatFileItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/builder/FlatFileItemReaderBuilder.html)
- [Spring Batch 5.2 API — BeanValidatingItemProcessor](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/validator/BeanValidatingItemProcessor.html)
- [Spring Batch 5.2 API — JobParametersValidator](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersValidator.html)
- [Java 17 API — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

A reliable Spring Batch pipeline requires an **explicit data contract**, structural checks before processing, type and format conversion with strict parsers, and business validation before writing. Placing validation intentionally in the reader or processor ensures accurate error metrics; choosing fail-fast, skip, or filter aligns with risk; and keeping source metadata and error codes enables investigation without exposing sensitive data. Finally, inputs, parsers, and writers must stay stable across restarts so reruns never turn the same data into a different outcome.
