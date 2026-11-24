# Input Validation to Prevent Injection in Spring Batch

## 1. Why is batch processing still vulnerable to injection?

Spring Batch typically runs server-side without web forms and often consumes data from "internal" systems. That **does not mean inputs are trustworthy**. A job can read partner-supplied CSV files, staging tables populated by another system, API payloads, message queues, filenames passed via `JobParameters`, or operator-supplied configuration.

If input data is concatenated directly into **SQL statements, file paths, expressions, OS commands, or outputs consumed by other applications**, values meant to be pure data can be interpreted as **control instructions**.

Example:

```text
Scheduler / REST / Operator
             |
             v
      JobParameters -------------+
             |                  |
             v                  v
File / API / Queue          Dynamic config
             |                  |
             v                  v
         ItemReader         SQL / Path / URL
             |
             v
        ItemProcessor
             |
             v
         ItemWriter
             |
             v
     Database / CSV / API
```

A flaw in SQL construction inside a reader or writer can impact millions of records. An unchecked `inputFile` parameter can let a job read files outside the inbox directory. A field name concatenated into `ORDER BY` can make queries run with unintended structure. A value starting with `=` in an exported CSV file can be interpreted as a formula by spreadsheet applications.

**Input validation to prevent injection** in Spring Batch has two distinct yet complementary goals:

1. **Enforce the data contract**: types, formats, lengths, ranges, allowed values, and authorization.
2. **Use safe APIs where data crosses into another language**: SQL parameter binding, identifier allowlists, filesystem path confinement, avoiding shells, and context-appropriate output encoding.

Validation **does not replace** prepared statements. Prepared statements **do not replace** business validation. Both are required.

### Example of unsafe input

Suppose `orderId` comes from a CSV:

```text
O-101
O'BRIEN
x' OR '1'='1
```

An `orderId` containing a single quote may be completely valid under a partner contract. Simply "stripping all quotes" to avoid SQL injection corrupts valid data while failing to address concatenation risks elsewhere. The right approach is **binding the value as a SQL parameter** while also validating format if business rules enforce an ID pattern.

## 2. Identifying trust boundaries in Spring Batch

| Input source | Examples | Risks to watch | Controls |
|---|---|---|---|
| `JobParameters` | `businessDate`, `inputKey`, `tenant` | Path traversal, selecting wrong dataset, dynamic table/column names in SQL | Validate before job runs, allowlists |
| CSV/TSV | `orderId`, `amount`, free-text notes | SQL injection if concatenated into queries, oversized fields, CSV formula injection on export | Parse, schema validate, bind SQL, encode per output context |
| Staging database | Values written by upstream systems | Second-order injection when read and used to build dynamic SQL | Treat as untrusted data, re-bind |
| API / messages | `sourceUrl`, `eventId`, filters | SSRF, replay, injection into queries or shells | Fixed target endpoints, schema validation, idempotency |
| XML / JSON | Nested fields, element counts, entities | XML external entity (XXE), parser/resource exhaustion | Hardened parsers, depth/size limits |
| File path / object key | `../../...`, lookalike filenames | Read/write outside allowed zone, symlink escape | Accept logical keys only, canonical paths, least-privilege access |
| Column/table/sort names | `sortBy=createdAt` | Cannot bind SQL identifiers as values | Map allowlists to hardcoded constants |
| OS process arguments | Filenames/arbitrary flags | Shell/argument injection | Avoid shells, fixed executables/options, validate arguments |

**Trust boundary principle:** Files in a company bucket, records arriving over an authenticated queue, or parameters from a scheduler can still be malformed, out of sync, or malicious. Every input crossing into a higher-privilege execution step needs appropriate controls.

## 3. Control pipeline: parse → validate → normalize → bind → encode

A secure pipeline can be structured as:

```text
Raw input
   |
   v
Parse strictly with size bounds
   |
   v
Validate required fields, types, lengths, domains
   |
   v
Normalize fields permitted to be normalized
   |
   v
Business rules / authorization / idempotency
   |
   v
Bind via parameterized APIs or select structures from allowlists
   |
   v
Encode for exact output context if exporting to another format
```

Each step serves a distinct purpose:

- **Parse**: convert raw bytes/text into structured types; syntax errors must be caught.
- **Validate**: reject values violating the contract, such as `amount=-99` or malformed `businessDate`.
- **Normalize**: standardize values where business rules allow, e.g., trimming leading/trailing whitespace on customer codes.
- **Authorize**: verify whether the job/source/tenant is permitted to access that dataset.
- **Bind**: pass values into SQL via placeholders instead of string concatenation.
- **Encode output**: when emitting to HTML, CSVs opened in spreadsheets, or other formats, encode for the *destination* context.

Never build one generic "sanitize all dangerous characters" helper for SQL, paths, HTML, and CSV alike. Each target language has different parsing rules.

## 4. Validating `JobParameters` before job execution

`JobParameters` are an especially dangerous entry point if a job accepts parameters like `inputFile`, `schema`, `table`, `where`, or `command`. These values may arrive from REST endpoints, schedulers, CLIs, or ops tools.

Suppose `importPayments` accepts only:

- `businessDate`: ISO-8601 date, e.g., `2025-05-12`.
- `inputKey`: **single filename**, Latin letters, digits, underscores/hyphens, `.csv` extension; no path separators.
- `sourceSystem`: one of `PARTNER_A` or `PARTNER_B`.

### 4.1. Centralized validator for job parameters

Spring Batch provides `JobParametersValidator` to validate parameters before the job starts processing.

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportJobParametersValidator
        implements JobParametersValidator {

    private static final Pattern INPUT_KEY = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.csv"
    );

    private static final Set<String> ALLOWED_SOURCES =
            Set.of("PARTNER_A", "PARTNER_B");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "Job parameters are required");
        }

        String businessDate = parameters.getString("businessDate");
        String inputKey = parameters.getString("inputKey");
        String sourceSystem = parameters.getString("sourceSystem");

        if (businessDate == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must be an ISO date");
        }

        if (inputKey == null
                || !INPUT_KEY.matcher(inputKey).matches()) {
            throw new JobParametersInvalidException(
                    "inputKey must be a simple .csv file name");
        }

        if (!ALLOWED_SOURCES.contains(sourceSystem)) {
            throw new JobParametersInvalidException(
                    "sourceSystem is not allowed");
        }
    }
}
```

**Important note:** `matcher(...).matches()` matches the **entire** value. Using `find()` to match a substring could allow a path whose suffix looks valid to slip through.

The pattern above is an example contract; it **does not allow Unicode in filenames** and caps the name at 80 characters before `.csv`. Tailor these rules to real requirements. If the application accepts object keys containing folders, design matching allowlists/canonicalization instead of loosely relaxing the pattern.

Do not validate date strings solely with regex `\d{4}-\d{2}-\d{2}`: strings shaped like dates can still be invalid calendar dates. `LocalDate.parse(...)` checks calendar validity too.

### 4.2. Registering the validator on the job

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job importPaymentsJob(
        JobRepository repository,
        Step importPaymentsStep) {

    return new JobBuilder("importPaymentsJob", repository)
            .validator(new ImportJobParametersValidator())
            .start(importPaymentsStep)
            .build();
}
```

When parameters are invalid, the job is rejected at validation time instead of letting readers or writers perform side effects. The job-launching API layer should still validate requests and check access rights before calling `JobLauncher`; the job validator is an extra defense layer, **not a replacement for authorization**.

### 4.3. Validate early without arbitrarily mutating identity

`JobParameters` can serve as identifying parameters defining `JobInstance`. Never swap `businessDate` or rename the file on every retry/restart using `LocalDate.now()` or an arbitrary string: doing so turns a restart into a brand-new job instance that re-reads data unexpectedly.

Best practice is locking `businessDate`, `inputKey`, and `sourceSystem` at launch; subsequent restarts reuse the exact identifying parameters.

## 5. SQL injection: **always bind SQL values**

One of the most common injection points in batch jobs is a reader building a query from a CSV field or `JobParameters`.

### 5.1. Bad example: concatenating strings into a query

```java
// DO NOT USE
String sql = "SELECT id, amount FROM payments "
        + "WHERE external_id = '" + externalId + "'";

jdbcTemplate.query(sql, rowMapper);
```

If `externalId` contains a quote or other SQL syntax, it alters the **statement structure**. Consequences range from query failures to altered filter conditions. Never assume a batch job is safe just because queries are built server-side: parameter sources can still be untrusted.

### 5.2. Correct example with `NamedParameterJdbcTemplate`

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public record PaymentLookup(
        long id,
        String externalId,
        BigDecimal amount
) {
}

public final class PaymentLookupRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public PaymentLookupRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<PaymentLookup> findByExternalId(String externalId) {
        String sql = """
                SELECT id, external_id, amount
                  FROM payments
                 WHERE external_id = :externalId
                """;

        MapSqlParameterSource parameters =
                new MapSqlParameterSource()
                        .addValue("externalId", externalId);

        return jdbc.query(
                sql,
                parameters,
                (rs, rowNum) -> new PaymentLookup(
                        rs.getLong("id"),
                        rs.getString("external_id"),
                        rs.getBigDecimal("amount"))
        );
    }
}
```

`:externalId` is a placeholder for a **value**, not a SQL fragment. The driver treats the supplied value strictly as data even if it contains quotes or SQL-like syntax.

With plain `JdbcTemplate`, use `?` placeholders:

```java
String sql = "UPDATE payments SET status = ? WHERE external_id = ?";

jdbcTemplate.update(sql, "VERIFIED", externalId);
```

**Never replace placeholders with manual string escaping**, such as `replace("'", "''")` or stripping `;`. Manual escaping easily misses encoding, SQL context, and driver edge cases. Parameter binding APIs are the primary defense.

### 5.3. Valid values can contain special characters

For instance, customer name `O'Brien` is valid data. Prepared statements pass this string cleanly as a value. When business rules permit apostrophes, you do not need to strip them just to prevent SQL injection.

Again, distinguish:

- **Validation** decides which names/codes are valid per contract.
- **Parameter binding** prevents values from altering query structure.

### 5.4. Bind parameters in JPA/JPQL too

```java
var query = entityManager.createQuery(
        """
        select p
          from PaymentEntity p
         where p.externalId = :externalId
        """,
        PaymentEntity.class
);

query.setParameter("externalId", externalId);
List<PaymentEntity> result = query.getResultList();
```

Do not migrate risk from JDBC into JPQL by concatenating `externalId` directly into the query string. Even with an ORM, the rule holds: **input values must be parameters**.

### 5.5. `LIKE` and wildcards

Binding prevents SQL injection, yet does not automatically satisfy `LIKE` search semantics. Characters `%` and `_` act as wildcards in SQL `LIKE` across many databases. When searching for a *literal string*, escape wildcards per database rules, specify an `ESCAPE` clause, and **still bind the parameter**.

That is a **query semantics** issue, not a flaw allowing SQL injection in prepared statements.

## 6. Parameter binding does not work for table names, columns, or `ORDER BY`

SQL placeholders pass **values**, not SQL identifiers or structural keywords.

Example that does not behave as intended:

```sql
SELECT id, amount FROM payments ORDER BY :columnName
```

In many databases, `:columnName` is treated as a **constant literal**, not a column identifier for sorting. To let operators choose sorting, **map from an allowlist to hardcoded column names**.

### 6.1. Allowlist enum for sort columns

```java
public enum PaymentSortColumn {

    ID("id"),
    CREATED_AT("created_at"),
    AMOUNT("amount");

    private final String sqlName;

    PaymentSortColumn(String sqlName) {
        this.sqlName = sqlName;
    }

    public String sqlName() {
        return sqlName;
    }

    public static PaymentSortColumn fromInput(String raw) {
        return switch (raw) {
            case "id" -> ID;
            case "createdAt" -> CREATED_AT;
            case "amount" -> AMOUNT;
            default -> throw new IllegalArgumentException(
                    "Unsupported sort column");
        };
    }
}
```

Building the query:

```java
PaymentSortColumn sort = PaymentSortColumn.fromInput(requestedSort);
String direction = switch (requestedDirection) {
    case "asc" -> "ASC";
    case "desc" -> "DESC";
    default -> throw new IllegalArgumentException(
            "Unsupported sort direction");
};

String sql = """
        SELECT id, external_id, amount
          FROM payments
         WHERE source_system = :sourceSystem
        ORDER BY
        """ + sort.sqlName() + " " + direction;

MapSqlParameterSource args = new MapSqlParameterSource()
        .addValue("sourceSystem", sourceSystem);

jdbc.query(sql, args, paymentRowMapper);
```

Here, the substrings appended to SQL come exclusively from **hardcoded constants via enum/switch**. User-supplied strings are never concatenated directly.

In batch jobs, avoid free-form `tableName` or `whereClause` parameters in `JobParameters` altogether. If multiple target tables exist, map a logical destination key to an application-managed fixed table list and verify access permissions.

### 6.2. Dynamic tenant or schema selection

If a job takes a `tenantId` parameter, never do this:

```java
// DO NOT USE:
String sql = "SELECT * FROM " + tenantId + ".payments";
```

Instead of turning `tenantId` directly into a schema name:

- Select a pre-configured datasource/schema for the authorized tenant.
- Map the tenant key to a fixed allowlisted set of identifiers.
- Use row-level tenant filtering with a bound parameter if architecture permits.
- Enforce authorization: is the user/job allowed to access that tenant?

**Allowlisting schema names and authorizing tenant access are separate checks.** A valid allowlisted value does not prove the caller has permission to read that tenant's data.

## 7. `JdbcBatchItemWriter`: fixed SQL, bound parameters

In Spring Batch, `JdbcBatchItemWriter` writes batches of items using parameterized SQL instead of constructing a new SQL string per item.

### 7.1. Validated DTO

```java
import java.math.BigDecimal;

public record ValidatedPayment(
        String externalId,
        BigDecimal amount,
        String currency
) {
}
```

### 7.2. Safe writer

```java
import javax.sql.DataSource;

import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<ValidatedPayment> paymentWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ValidatedPayment>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO staged_payments (
                    external_id,
                    amount,
                    currency
                ) VALUES (
                    :externalId,
                    :amount,
                    :currency
                )
                """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("externalId", item.externalId())
                            .addValue("amount", item.amount())
                            .addValue("currency", item.currency()))
            .build();
}
```

`JdbcBatchItemWriter` uses fixed SQL and passes each item's fields through Spring JDBC parameters. Even if `externalId` contains special characters, it remains data. This is far safer than concatenating `"INSERT ... VALUES ('" + value + "')"` inside a loop.

Add matching database constraints, such as `UNIQUE(source_system, external_id)` if that is the business key. Prepared statements **do not automatically prevent duplicate rows, wrong types, oversized values, or cross-tenant writes**; those require dedicated validation and database constraints.

## 8. Validating each item's contents in `ItemProcessor`

Raw data should be parsed into an input representation and validated at an explicit boundary. For CSV files, the reader can parse fields as strings and the processor can validate types and business rules before passing items to the writer.

### 8.1. Raw DTO and validation exception

```java
public record RawPayment(
        String externalId,
        String amountText,
        String currency
) {
}
```

```java
public final class InvalidPaymentException
        extends RuntimeException {

    public InvalidPaymentException(String message) {
        super(message);
    }
}
```

### 8.2. Processor checking format, length, and range

```java
import java.math.BigDecimal;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;

public final class ValidatePaymentProcessor
        implements ItemProcessor<RawPayment, ValidatedPayment> {

    private static final Pattern EXTERNAL_ID =
            Pattern.compile("P-[A-Z0-9]{1,40}");

    private static final Set<String> CURRENCIES =
            Set.of("VND", "USD");

    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000000000.00");

    @Override
    public ValidatedPayment process(RawPayment raw) {
        if (raw == null) {
            throw new InvalidPaymentException("Missing row");
        }

        String id = requireText(raw.externalId(), "externalId");
        String amountText = requireText(
                raw.amountText(), "amount");
        String currency = requireText(
                raw.currency(), "currency");

        if (!EXTERNAL_ID.matcher(id).matches()) {
            throw new InvalidPaymentException(
                    "Invalid externalId format");
        }

        if (!CURRENCIES.contains(currency)) {
            throw new InvalidPaymentException(
                    "Unsupported currency");
        }

        if (amountText.length() > 40) {
            throw new InvalidPaymentException(
                    "Amount text is too long");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(amountText);
        } catch (NumberFormatException ex) {
            throw new InvalidPaymentException(
                    "Amount is not numeric");
        }

        if (amount.scale() > 2
                || amount.signum() <= 0
                || amount.compareTo(MAX_AMOUNT) > 0) {
            throw new InvalidPaymentException(
                    "Amount is out of allowed range");
        }

        return new ValidatedPayment(id, amount, currency);
    }

    private static String requireText(
            String raw, String fieldName) {

        if (raw == null) {
            throw new InvalidPaymentException(
                    fieldName + " is required");
        }

        String value = raw.strip();

        if (value.isEmpty()) {
            throw new InvalidPaymentException(
                    fieldName + " is blank");
        }

        return value;
    }
}
```

**This example's contract is deliberate:** payment IDs accept only `P-` plus uppercase alphanumeric characters, amounts allow at most two decimal places, and currencies belong to an allowed set. This is an **illustrative contract**, not a universal rule for all payment systems. If real data permits IDs with apostrophes, Vietnamese characters, or other symbols, adapt validation to business rules **and still bind SQL**.

Never rely solely on "filtering out all quotes" or "blocking the word SELECT" to prevent injection: attackers find alternative encodings, while legitimate data gets corrupted.

### 8.3. Should parsing happen in the reader or processor?

Two valid designs exist:

- **Reader parses types immediately**: a malformed amount raises `FlatFileParseException` and is classified as a reader error.
- **Reader returns a Raw DTO, processor validates**: `InvalidPaymentException` happens during processing and can be managed/audited under `processSkipCount`.

Choose based on error-classification goals and the data contract. **Do not try to force every error into a read skip.** What matters is that invalid data never reaches the writer, and the system can explain why an item was rejected.

### 8.4. Bean Validation

For complex DTOs, Jakarta Bean Validation (`jakarta.validation`) provides annotations like `@NotBlank`, `@Size`, `@Pattern`, and `@Positive`. In Spring Boot 3, the namespace is `jakarta.validation` (unlike `javax.validation` in older releases).

Example:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record PartnerReference(
        @NotBlank
        @Size(max = 64)
        @Pattern(regexp = "[A-Za-z0-9_-]+")
        String partnerCode
) {
}
```

Annotations **do not execute automatically just because a record is created**. Integrate a `Validator` into the pipeline or invoke it explicitly—for example via Spring Batch's `BeanValidatingItemProcessor` when using the appropriate module/dependencies, or a custom processor calling `jakarta.validation.Validator.validate(...)` and handling violations.

Bean Validation checks an item's data contract; it also **does not replace** PreparedStatement when writing to the database.

## 9. Path traversal: never let `JobParameters` pick arbitrary files

A file-reading job may accept `inputFile` externally. If the application joins it directly to a base directory:

```java
// DO NOT USE:
Path file = Path.of("/srv/batch/inbox", inputFile);
Files.readString(file);
```

Values like `../secrets/config.txt` can escape the inbound directory. On some systems, symlinks inside the inbox can also point elsewhere.

### 9.1. Prefer logical keys and allowlisted filenames

Instead of allowing absolute paths, accept only an `inputKey` such as `partner-a-20250512.csv`. The application determines the actual directory.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.regex.Pattern;

public final class InputFileResolver {

    private static final Pattern SIMPLE_NAME = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9_-]{0,79}\\.csv"
    );

    private final Path allowedRoot;

    public InputFileResolver(Path root) throws IOException {
        this.allowedRoot = root.toRealPath();
    }

    public Path resolve(String inputKey) throws IOException {
        if (inputKey == null
                || !SIMPLE_NAME.matcher(inputKey).matches()) {
            throw new IllegalArgumentException(
                    "Invalid input file key");
        }

        Path requested = allowedRoot.resolve(inputKey).normalize();

        if (!requested.startsWith(allowedRoot)) {
            throw new SecurityException(
                    "Path escapes allowed input directory");
        }

        // By default toRealPath follows symlinks.
        Path actual = requested.toRealPath();

        if (!actual.startsWith(allowedRoot)
                || !Files.isRegularFile(actual)) {
            throw new SecurityException(
                    "Input is outside allowed files");
        }

        return actual;
    }
}
```

Example:

```text
inputKey=partner-a-20250512.csv  -> valid if file exists inside root
inputKey=../../secret.txt        -> rejected
inputKey=/etc/passwd             -> rejected
inputKey=subdir/file.csv         -> rejected under single-filename policy
```

`Path.startsWith(Path)` compares **path components**, unlike raw string checks like `file.toString().startsWith("/srv/batch")`, which can mistakenly accept sibling directories sharing a prefix.

**Security limitation:** Checking `toRealPath()` and opening the file afterward can still face a race condition if an attacker can replace a symlink or directory contents between the two operations. Under that threat model, lock down input directory permissions, restrict writes/renames, or use secure directory-handle open APIs where supported. Canonicalization is a defense layer, not a substitute for OS permissions.

### 9.2. Combining with `FlatFileItemReader`

```java
import java.io.IOException;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<RawPayment> paymentReader(
        @Value("#{jobParameters['inputKey']}") String inputKey,
        InputFileResolver resolver) throws IOException {

    return new FlatFileItemReaderBuilder<RawPayment>()
            .name("paymentReader")
            .resource(new FileSystemResource(
                    resolver.resolve(inputKey)))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("external_id", "amount", "currency")
            .fieldSetMapper(fields -> new RawPayment(
                    fields.readString("external_id"),
                    fields.readString("amount"),
                    fields.readString("currency")))
            .build();
}
```

`strict(true)` ensures missing or unreadable files raise errors rather than silently acting as empty sources. `@StepScope` injects execution parameters when the reader is created. However, **SpEL in `@Value` performs no security validation for you**; `InputFileResolver.resolve(...)` must still validate inputs.

If the file could be overwritten between restarts, line-number checkpoints would point into different data. Keep files/versions/checksums immutable per `JobInstance`.

### 9.3. Bounding file size and line counts

A safe path does not guarantee safe file contents. A huge file, a tens-of-megabytes single line, or a multi-million-character field can exhaust memory/CPU.

Define:

- Maximum file size before processing.
- Maximum line length, column count, and per-field length.
- Permitted schema/header and encoding.
- Maximum record count or ingestion timeout per SLA.
- Action on limit breach: fail or quarantine—never silently truncate and write corrupted data.

Apply these bounds **as close to the source as possible**. `chunk(100)` bounds items per transaction chunk, **not** individual item size or total file size.

## 10. Output injection: CSV formula injection

Even when **SQL is properly bound**, another issue can occur: a job exports CSV data for operators to open in Excel, LibreOffice, or another spreadsheet tool.

Suppose a `customerNote` field from an external system begins with a formula character:

```csv
order_id,customer_note
O-101,"=1+1"
```

When opened in a spreadsheet application, the value may be evaluated as a **formula** rather than plain text. Certain formulas can pose risks depending on the application and security settings.

**CSV formula injection differs from SQL injection**: valid CSV quoting merely encloses the field and does not force spreadsheet programs to treat the cell content as literal text.

Remediation depends on the contract:

1. When exporting XLSX, prefer **writing cells with an explicit text cell type** rather than formula strings.
2. For CSVs intended for spreadsheet viewing, apply a policy to escape/neutralize values that could be interpreted as formulas.
3. Check leading `=`, `+`, `-`, `@`, as well as leading whitespace/control characters; spreadsheet software differs in behavior.
4. Test with the exact spreadsheet software and version recipients use; **no single naive CSV escaping trick works identically across all tools/import modes**.
5. For machine-to-machine data exchange files, do not prepend single quotes to values if doing so alters the receiving system's data contract. Separate human-facing export formats/channels when needed.

This illustrates the principle: **a string safe to store in a database is not automatically safe everywhere it is displayed or executed**.

## 11. URLs, shells, and other injection surfaces

### 11.1. SSRF if a job accepts arbitrary URLs

A job downloading files from a `sourceUrl` passed via API can be abused to call internal addresses or services reachable by the job server.

**Do not do this:**

```java
// sourceUrl comes from JobParameters unchecked:
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create(sourceUrl))
        .GET()
        .build();
```

A safer model accepts only `sourceSystem=PARTNER_A` and **picks a pre-configured endpoint** for that partner. If dynamic URLs are genuinely required, validate scheme, hostname, port, redirects, resolved DNS/destination IPs, and enforce network egress controls. Prefix checks like `url.startsWith("https://trusted")` are insufficient.

### 11.2. Command injection

If a job invokes an external tool to convert file formats, never build a shell command string from input:

```java
// DO NOT USE:
String command = "converter --input " + inputKey;
Runtime.getRuntime().exec(command);
```

Prefer Java APIs or, when an external binary is needed, avoid the shell and use `ProcessBuilder` with separated executable/arguments, **while still validating arguments** to block option injection and verifying real paths:

```java
ProcessBuilder builder = new ProcessBuilder(
        "/usr/local/bin/converter",
        "--input",
        validatedAbsolutePath.toString(),
        "--output",
        validatedOutputPath.toString()
);
```

The snippet above only shows separating arguments and **is not sufficient on its own**: the executable must be application-controlled; `validatedAbsolutePath` and `validatedOutputPath` must reside inside approved zones; any dynamic options also need allowlists; and the process needs timeouts and minimal OS permissions.

### 11.3. XML External Entity (XXE)

If a batch job uses an XML reader, prevent the parser from fetching unauthorized external entities or DTDs. For example, with StAX:

```java
import javax.xml.stream.XMLInputFactory;

XMLInputFactory factory = XMLInputFactory.newFactory();

factory.setProperty(
        XMLInputFactory.SUPPORT_DTD,
        false
);

factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        false
);
```

When using `StaxEventItemReader` or another XML parser, verify that **the actual parser used** by the reader receives this hardened configuration rather than creating a factory that sits unused. Beyond XXE, configure depth limits, document size limits, and protections against resource exhaustion.

### 11.4. Expression and template injection

Spring Batch uses SpEL on step-scoped/job-scoped beans, for example:

```java
@Value("#{jobParameters['businessDate']}")
String businessDate
```

Here, the expression is a **static string written by the developer** that merely reads a parameter value. Never take received values and **construct a new expression** to evaluate as code.

Avoid designs that "read an `expression` string from CSV/`jobParameters` and run it through an expression engine" unless you have a tightly constrained sandbox and a clear requirement. In most batch ingestion jobs, mapping a logical rule key to application-defined predicates is much safer.

## 12. Error handling: skip, fail, or quarantine?

In Spring Batch, not every invalid datum should halt an entire job, **yet security violations should never be silently skipped**.

| Error | Suggested policy |
|---|---|
| A row has an invalid amount type where business rules permit skipping | Bounded process skip with auditing |
| Malformed order ID | Quarantine or skip per quality threshold |
| `inputKey` attempts accessing outside allowed root | Reject job during parameter validation / reader init; audit |
| Parameter selects unauthorized tenant | Reject launch; process no data |
| CSV header mismatches expected schema | Fail fast or quarantine entire file |
| Widespread data errors exceeding threshold | Fail step; never silently mark `COMPLETED` with missing data |
| Database throws SQL or unique constraint error outside policy | Classify explicitly; never blanket `skip(Exception.class)` |
| Payload contains special characters permitted by valid contract | Accept, using proper binding/output encoding |

### 12.1. Controlled skips for business validation errors

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importPaymentsStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawPayment> paymentReader,
        ItemProcessor<RawPayment, ValidatedPayment> validator,
        ItemWriter<ValidatedPayment> paymentWriter) {

    return new StepBuilder("importPaymentsStep", repository)
            .<RawPayment, ValidatedPayment>chunk(
                    100, transactionManager)
            .reader(paymentReader)
            .processor(validator)
            .writer(paymentWriter)
            .faultTolerant()
            .skip(InvalidPaymentException.class)
            .skipLimit(10)
            .build();
}
```

This example skips only the **explicitly classified** `InvalidPaymentException`, not all `RuntimeException`s or SQL exceptions. `skipLimit(10)` is the step's total skip cap across skippable errors, not a per-type cap.

When data is too critical to tolerate missing records, disable skips and fail the step. Payment systems may require stricter validation than shown here.

### 12.2. Auditing without leaking data

A good log record:

```text
event=batch.input.rejected
jobName=importPaymentsJob
jobExecutionId=501
sourceSystem=PARTNER_A
inputKey=partner-a-20250512.csv
sourceLine=47
errorCode=INVALID_AMOUNT
action=QUARANTINED
```

Never log raw tokens, passwords, raw HTTP headers, full connection strings, or complete external payloads. With untrusted inputs, also prevent **log injection** via newline/control characters and avoid exploding cardinality in metric tags.

Store failing data samples in an authorized, encrypted quarantine store with a retention policy rather than dumping sensitive payloads into application logs.

## 13. Authorization, least privilege, and tenant isolation

Validation is necessary, yet still does not replace access control.

A request with `businessDate=2025-05-12` may be syntactically valid while the caller lacks permission to run another partner's import job. An `inputKey` matching the allowlist could point to a well-formed file owned by another tenant.

Required layers:

1. **Caller authorization**: endpoints/consoles allow only authorized roles to launch/restart/stop jobs.
2. **Source authorization**: caller/job is cleared to select that `sourceSystem`, `inputKey`, or tenant.
3. **Database least privilege**: JDBC accounts can read/write only required tables, without schema create/drop rights.
4. **Filesystem least privilege**: process can read only the proper inbox and write to isolated outputs; cannot read out-of-scope secrets.
5. **Network egress policy**: workers reach only required endpoints.
6. **Secret handling**: credentials come from secret managers/secure config, never stuffed into `JobParameters` for display convenience.

These controls **contain blast radius** if one validation check has a bug. SQL parameter binding alone cannot protect against reading the wrong tenant when authorization is missing.

## 14. Testing input validation and injection defenses

Security tests must cover both **valid inputs with special characters** and **deliberately out-of-contract inputs**. Never assert that a regex blocks single quotes and conclude SQL injection is solved.

### 14.1. Unit testing `JobParametersValidator`

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportJobParametersValidatorTest {

    private final ImportJobParametersValidator validator =
            new ImportJobParametersValidator();

    private JobParameters parameters(
            String businessDate,
            String inputKey,
            String sourceSystem) {

        return new JobParametersBuilder()
                .addString("businessDate", businessDate)
                .addString("inputKey", inputKey)
                .addString("sourceSystem", sourceSystem)
                .toJobParameters();
    }

    @Test
    void acceptsValidParameters() {
        assertDoesNotThrow(() -> validator.validate(
                parameters(
                        "2025-05-12",
                        "partner-a-20250512.csv",
                        "PARTNER_A")
        ));
    }

    @Test
    void rejectsParentDirectoryTraversal() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-05-12",
                                "../secret.csv",
                                "PARTNER_A"))
        );
    }

    @Test
    void rejectsInvalidCalendarDate() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-02-30",
                                "orders.csv",
                                "PARTNER_A"))
        );
    }

    @Test
    void rejectsUnsupportedSource() {
        assertThrows(
                JobParametersInvalidException.class,
                () -> validator.validate(
                        parameters(
                                "2025-05-12",
                                "orders.csv",
                                "UNKNOWN"))
        );
    }
}
```

Running this test needs no database or job execution. It verifies the parameter contract, not how the OS handles symlinks or the database handles SQL.

### 14.2. Unit testing the processor with bad inputs

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class ValidatePaymentProcessorTest {

    private final ValidatePaymentProcessor processor =
            new ValidatePaymentProcessor();

    @Test
    void acceptsValidPayment() throws Exception {
        ValidatedPayment actual = processor.process(
                new RawPayment("P-101", "125000.00", "VND"));

        assertEquals("P-101", actual.externalId());
        assertEquals(new BigDecimal("125000.00"), actual.amount());
    }

    @Test
    void rejectsUnexpectedIdStructure() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment(
                                "P-101' OR '1'='1",
                                "125000",
                                "VND"))
        );
    }

    @Test
    void rejectsInvalidAmount() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment("P-101", "not-a-number", "VND"))
        );
    }

    @Test
    void rejectsOversizedAmountText() {
        assertThrows(
                InvalidPaymentException.class,
                () -> processor.process(
                        new RawPayment(
                                "P-101",
                                "9".repeat(1000),
                                "VND"))
        );
    }
}
```

Here, an ID with quotes is rejected by the **`P-[A-Z0-9]{1,40}` contract**, not because SQL parameter binding cannot handle quotes. When IDs must allow valid apostrophes, tests should confirm the writer passes them via parameter binding without altering SQL structure.

### 14.3. Integration test proving SQL values do not become query conditions

A Spring Boot test with `@JdbcTest` can pass SQL-like text into a **bound parameter** and verify it is treated strictly as a literal value.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@JdbcTest
class ParameterizedQuerySecurityTest {

    @Autowired
    NamedParameterJdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        jdbc.getJdbcTemplate().execute(
                "DROP TABLE IF EXISTS test_customers");

        jdbc.getJdbcTemplate().execute("""
                CREATE TABLE test_customers (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(128) NOT NULL
                )
                """);

        jdbc.getJdbcTemplate().update(
                "INSERT INTO test_customers(id, name) VALUES (?, ?)",
                1L,
                "Alice");
    }

    @Test
    void suspiciousTextMustBeTreatedAsOneValue() {
        String untrustedName = "x' OR '1'='1";

        Integer count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM test_customers
                 WHERE name = :name
                """,
                Map.of("name", untrustedName),
                Integer.class
        );

        // Does not match all rows via input-supplied syntax.
        assertEquals(0, count);

        Integer stillOneRow = jdbc.getJdbcTemplate()
                .queryForObject(
                        "SELECT COUNT(*) FROM test_customers",
                        Integer.class);

        assertEquals(1, stillOneRow);
    }
}
```

This test uses the embedded database configured by Spring Boot `@JdbcTest` (e.g., H2 on the test classpath). It tests that specific query with parameter binding; it does not substitute for security testing **every other query** in the application.

### 14.4. Testing path resolver with `@TempDir`

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class InputFileResolverTest {

    @TempDir
    Path tempDirectory;

    @Test
    void acceptsFileInsideAllowedRoot() throws Exception {
        Path file = tempDirectory.resolve("orders.csv");
        Files.writeString(file, "external_id,amount,currency\n");

        InputFileResolver resolver =
                new InputFileResolver(tempDirectory);

        assertEquals(file.toRealPath(), resolver.resolve("orders.csv"));
    }

    @Test
    void rejectsTraversalBeforeOpeningFile() throws Exception {
        InputFileResolver resolver =
                new InputFileResolver(tempDirectory);

        assertThrows(
                IllegalArgumentException.class,
                () -> resolver.resolve("../other.csv")
        );
    }
}
```

Symlink escapes should have dedicated tests on operating systems supporting symlink creation and permissions. Do not force every CI runner to create symlinks when restricted; still verify that behavior in suitable integration/security tests.

### 14.5. What should the test dataset include?

| Case | Example | Goal |
|---|---|---|
| Valid input | `P-101`, `125000.00` | Does not break normal data |
| Valid special characters | Name `O'Brien` | Does not corrupt data just for having quotes |
| SQL-like text | `x' OR '1'='1` | Parameter binding, never treated as SQL |
| Disallowed column name | `sortBy=arbitraryColumn` | Rejected by allowlist |
| Path traversal | `../secret.csv` | Never opens files outside root |
| Absolute path | `/etc/passwd` | Rejected in input key |
| Oversized file / long line | Input exceeding quota | Fails safely without resource exhaustion |
| Unauthorized source/tenant | `PARTNER_B` from unauthorized caller | Authorization |
| Invalid amount | `NaN`, negative, too long | Validation |
| Spreadsheet formula | Field starting with `=` | Output CSV/XLSX handled per policy |
| XML with external entity | DTD/entity from untrusted source | Parser loads no external resources |
| Retry/restart | Rerunning same file/version | No unintended replayed side effects |

Separate test tiers: **unit tests** for validators/processors; **integration tests** for JDBC and filesystem; **job/step tests** for wiring, skip limits, transactions, and restarts. A single regex unit test does not prove an entire pipeline is secure.

## 15. Monitoring and responding to suspicious inputs

Automated batch jobs rarely have human operators watching every record. Build operational signals so abnormal data changes are never hidden.

### Useful metrics

| Metric | Meaning |
|---|---|
| `input_validation_rejections_total` | Items rejected for schema/contract violations |
| `batch_job_launch_rejected_total` | Launch requests denied for parameters/permissions |
| `input_path_validation_failure_total` | Detected unauthorized input keys/paths |
| `batch_process_skip_total` | Items skipped in processor |
| `input_quarantine_records_total` | Records routed for separate inspection |
| `batch_step_failed_total` | Failed steps, including widespread format errors |
| `source_schema_mismatch_total` | Files/events failing expected schema |

These metric names are application-defined examples, **not default Spring Batch meter names**. Combine them with `StepExecution.readSkipCount`, `processSkipCount`, `writeSkipCount`, and `BatchStatus` to monitor data quality.

Never attach raw payloads, customer IDs, path values, or exception messages as metric labels; they have high cardinality and can leak data. Use low-cardinality labels like `jobName`, `sourceSystem`, and `errorCode`.

### When an attack or widespread bad data is detected

- Halt publishing business results if safety/quality thresholds fail.
- Record `jobExecutionId`, file ID/version, and origin source.
- Quarantine data while limiting sensitive details in logs.
- Check whether other jobs consume the same data or were mis-triggered.
- Inspect committed DB changes and rollback/restart options.
- Fix root causes at the boundary and add regression tests before rerunning.
- Never raise `skipLimit` or disable validation just to turn a `FAILED` job into `COMPLETED`.

## 16. Anti-patterns and replacements

| Anti-pattern | Problem | Replacement |
|---|---|---|
| Concatenating `orderId` directly into SQL | SQL injection, breaks on quotes | `PreparedStatement` / `NamedParameterJdbcTemplate` |
| Escaping only `'` | Fails across SQL contexts | Parameter binding |
| `ORDER BY ` + user input | Cannot bind identifiers | Enum/allowlist identifiers |
| Picking table/schema names from unchecked `JobParameters` | Reads/writes wrong zones | Map logical keys to fixed config + authorization |
| `Path.of(root, inputKey)` directly | Path traversal/symlink escape | Logical keys, canonicalization, OS permissions |
| Using `String.startsWith` for path checks | Vulnerable to sibling prefix confusion | `Path.startsWith(Path)` and real paths |
| Fetching arbitrary URLs in readers | SSRF, internal system access | Map endpoints by source key |
| Calling shells with concatenated args | Command injection | Avoid shells, allowlist executables/options |
| Evaluating expressions from file contents | Expression injection | Fixed rule-key mappings |
| Letting XML parsers load external entities | XXE and unintended resource reads | Disable DTD/external entities on the active parser |
| Assuming PreparedStatement validates data quality | SQL is safe yet amounts can be negative/wrong | Validation and DB constraints |
| `skip(Exception.class)` to avoid job failure | Masks security/infra errors | Skip explicitly classified errors with caps |
| Printing raw dangerous payloads in logs | Data leaks, log injection | Log controlled codes, IDs, and line numbers |
| Writing CSVs without considering spreadsheet viewers | Spreadsheet formula injection | Output encoding/cell types per destination |
| Testing only happy-path data | Boundary bugs remain | Test malformed, oversized, path, and replay inputs |
| Using `LocalDate.now()` on restart | Shifts dataset between runs | Business date in `JobParameters` |
| Running jobs with over-privileged DB accounts | Magnifies impact if exploited | Least-privilege DB user |
| Validating in only one place | Other entry points bypass checks | Boundary validation + safe sink APIs + DB constraints |

## 17. Hands-on exercise: building a secure import pipeline

Build a `secureImportPayments` job importing partner CSVs by business date. Files contain `external_id`, `amount`, `currency`, and `note`, persisted into `staged_payments`.

Requirements:

1. Define `JobParameters` with `businessDate`, `inputKey`, and `sourceSystem`. Validate at job start: valid calendar date, simple `.csv` filename, and allowed source.
2. Configure `InputFileResolver` allowing readers to open files only inside an app-configured inbox root. Reject `../`, absolute paths, and escaping symlinks.
3. Have the reader bound file size, verify schema/header, and parse each line into `RawPayment`.
4. Have the processor validate ID, amount, currency, and note length, clearly deciding which errors quarantine vs. fail the job.
5. Have the writer use `JdbcBatchItemWriter` and named parameters, never concatenating input fields into SQL.
6. If sorting is supported, allow only `id`, `createdAt`, or `amount` via an allowlist enum. Never accept raw `ORDER BY` or `WHERE` from job parameters.
7. Add a unique constraint on the business key and verify restarts/retries create no duplicate transactions.
8. Write unit tests for input key, business date, source, amount, and processor—testing both valid special characters and SQL-like syntax.
9. Write a JDBC integration test proving payloads containing `' OR '1'='1` remain bound values without altering query results.
10. Generate a user-facing CSV output with a `note` field starting with a formula character and verify destination-appropriate output encoding.
11. Add metrics by `errorCode` and sanitized logs stripped of sensitive data.
12. Verify a caller belonging to partner A cannot launch a job reading partner B's file even if partner B's `sourceSystem` is schema-valid.

**Review question:** If input is validated by a regex disallowing single quotes, can you drop PreparedStatement and concatenate SQL strings?

**Answer:** **No.** Regex expresses only part of a data contract and can change or be bypassed in another code path. Any untrusted value entering SQL must still pass through parameter binding. When SQL structure itself must vary (such as column names), use an allowlist of hardcoded application-defined structures.

## 18. References

- [Spring Batch Reference — Job Parameters Validator](https://docs.spring.io/spring-batch/reference/job/configuring.html): validating `JobParameters` before execution.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): roles of `ItemReader`, `ItemProcessor`, `ItemWriter`, and transactions.
- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): filtering or validating items in processors.
- [Spring Batch Reference — Database Item Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter` and JDBC persistence.
- [Spring Framework Reference — JDBC Parameter Binding](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `NamedParameterJdbcTemplate`, and binding.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): prepared statements, identifier allowlists, and least privilege.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): risks of input-controlled file paths.
- [OWASP — CSV Injection](https://owasp.org/www-community/attacks/CSV_Injection): spreadsheet formula injection during data export.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): controlling external URLs/endpoints.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): hardening XML parsers against XXE.
- [Java SE — Path API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `normalize`, `toRealPath`, `startsWith`, and path handling.
