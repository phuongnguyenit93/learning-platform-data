# Pre-Batch Input Validation in Spring Batch

## 1. Why Validate Before Running a Batch?

A batch job typically processes large volumes of data: CSV files, converted Excel sheets, batched messages, API data, or staging tables from partners. If you start writing data as soon as input arrives, a simple error such as **a missing file, wrong header, wrong business date, or incomplete upload** may only be discovered after multiple chunks have already committed.

For example, the `importOrdersJob` job is expected to import orders for `2026-11-16`:

```text
input: orders_2026-11-16.csv
expected header: order_id,customer_id,amount
expected businessDate: 2026-11-16
```

However, the received file has the header `order_id,customer_name,amount`. If the reader only maps by column position without checking the contract, the job may put the customer name into the customer ID field, producing corrupt data and only failing at the writer or in later reconciliation steps.

**Pre-batch input validation** (*preflight validation*, *input admission*) is the set of checks performed **before data is accepted for business processing with side effects**. The goals are:

- Block batches that definitely cannot be processed correctly.
- Classify input errors early, with clear messages for the data provider or operator.
- Avoid reading/writing millions of records only to discover the file has the wrong structure or wrong business period.
- Create a traceable audit trail: which input was checked, which version, which rules, and what the result was.
- Enable retry, restart, and rerun to use the exact **same data snapshot**.

Preflight is one layer of **data quality**, but it does not completely replace validation in `ItemReader`, `ItemProcessor`, or the database. An input that passes preliminary checks can still contain business-invalid records in the middle of the file.

## 2. Distinguishing Preflight from Validation in the Chunk Flow

Spring Batch does not automatically validate every input contract. Each layer does a different job:

| Layer | Timing | Typical Checks | Response |
| --- | --- | --- | --- |
| **Job parameters** | When the job receives parameters | Missing `inputPath`, invalid `businessDate`, conflicting parameters | Reject the launch configuration or mark failure per the launch mechanism |
| **Preflight step** | Before the data processing step | Missing file, empty file, wrong header, checksum, schema, abnormal count | Prevent business steps from continuing |
| **Reader / parser** | When reading each record | CSV quoting errors, wrong column count, unparseable number/date | Exception, skip/fail according to policy |
| **Processor** | When processing each record | Negative amount, non-existent customer, violated business rule | Filter, skip/quarantine, fail, or conditional retry |
| **Writer / database** | When writing | Duplicate key, foreign key, constraint, concurrency | Rollback, retry, or fail according to transaction and policy |
| **Post-processing reconciliation** | After processing | Amount totals, row counts, reconciliation between two sources | Block publish, put the batch into an investigation state |

For example, a file with the right name, encoding, and header does not guarantee every row is valid. Conversely, a file containing one row with a negative amount may still be allowed if the data contract permits **quarantining invalid rows and continuing with valid ones**.

Therefore, you must clearly define **input not permitted into the batch** versus **an invalid item that can be handled locally**. Avoid using the same "invalid" label for every error, because the recovery policy for each group is very different.

## 3. Four Common Input Validation Layers

### 3.1. Source Availability and Completeness

First, you must know that the data is ready:

- The file or object exists at an authorized location.
- The file has been uploaded **completely**, not still being written.
- Read permissions and size are appropriate; the file is not empty if the contract requires data.
- Size is within resource protection limits.
- A manifest, "ready" marker, checksum, or completion signal from the sending system is present when required.
- If there are multiple files for a period, the file list is complete with no missing parts.

Merely calling `Files.exists(path)` and then starting to read does not guarantee the data is stable: the source can change between the check and when the reader opens the file. This is the **time of check vs time of use (TOCTOU)** problem.

For critical sources, you should place data into an **immutable staging location** and then validate and process that exact snapshot. The upload can write to a temporary name, verify the checksum, and then publish a manifest or rename atomically if the storage system supports it.

### 3.2. Structure and Format

Common checks include:

- Does the actual format match the filename and contract?
- Is the encoding UTF-8, UTF-8 BOM, or another allowed encoding?
- Are the header and column names exact, matching the schema version and case-sensitivity rules?
- Are the column count, delimiter, escaping, quoting, and multiline records supported by the parser?
- Are required fields present and are there no duplicate column names?
- Do data types (`BigDecimal`, dates, booleans) parse correctly?
- Are timezone, precision, decimal separator conventions, and date formats explicitly defined?

Example CSV contract:

```text
Schema version: orders-v2
Encoding: UTF-8
Header: order_id,customer_id,amount
Delimiter: comma
Date pattern: ISO-8601 if a date column is present
Amount: decimal, period decimal separator, no currency symbol
```

Do not parse real-world CSV using `line.split(",")` if data may contain commas inside quoted fields or multiline rows. Use a CSV-aware parser (such as `FlatFileItemReader` with an appropriate tokenizer, or a dedicated CSV library). The string-comparison header check example later has a narrow scope: it **only verifies a fixed contract header**, not replacing full CSV parsing.

### 3.3. Quality and Business Rules

Examples:

- `order_id` must not be blank and must not repeat if each order may only have one event.
- `amount > 0`, with currency unit and rounding following rules.
- `businessDate` falls within the selected batch period.
- `customer_id` exists or has a valid status at the cutoff time.
- Control totals in the manifest match the actual data.
- The error record rate does not exceed the acceptance threshold; zero-tolerance cases must equal 0.

Some rules require reading the entire file, joining with the database, or checking multiple sources. When data is large, scanning the whole file **before** processing can double I/O. You can choose staging + single-pass validation, or combine in-chunk validation with blocking the final publish step. The choice depends on atomicity requirements and the consequences of bad data.

### 3.4. Correct Version, Correct Period, No Duplicate Processing

A file may have valid content but **has already been processed for the same batch**. Distinguish between:

- **Duplicate source:** the same `sourceId`/checksum/manifest is resent.
- **Intentional rerun:** operations wants to reprocess a period after fixing an error.
- **Restart:** the same failed `JobInstance` resumes from a checkpoint.
- **New version:** the provider sends the same business date but a new version with different content.

You should have a stable input identifier, such as `sourceSystem + businessDate + fileVersion`, or a checksum with a clear contract. Do not rely solely on the filename to decide duplicates, because a file with the same name can have its content replaced.

## 4. Preflight Architecture for a Batch Job

```text
Producer / SFTP / Object Storage
           |
           v
    Upload to staging
           |
           v
    Manifest / ready marker
           |
           v
     JobParametersValidator
       - inputPath present?
       - businessDate valid?
       - version valid?
           |
           v
     preflightStep (Tasklet)
       - exists, readable?
       - header/schema/checksum?
       - ready, right period?
           |
           +---- INVALID --> FAILED / REJECTED + audit
           |
           v
      importDataStep
       Reader -> Processor -> Writer
           |
           v
   reconcile / quality gate
           |
           +---- FAIL --> do not publish
           |
           v
   publish / confirm completion
```

In the model above, `preflightStep` is the **first step**. If it fails, Spring Batch does not run the processing steps in the default sequential flow. Specific record validation errors are still handled in `importDataStep` under its own policy.

An important operational distinction: **JobParametersValidator** is validation of job configuration parameters; **preflightStep** is work that can be traced in `StepExecution`. A job should not put expensive I/O operations into `JobParametersValidator` if you want per-check history, metrics, and clear step status.

## 5. JobParametersValidator: Catch Parameter Errors as Early as Possible

Suppose the job requires:

| Parameter | Required | Example |
| --- | --- | --- |
| `inputPath` | Yes | `/staging/orders_2026-11-16.csv` |
| `businessDate` | Yes | `2026-11-16` |
| `schemaVersion` | Yes | `orders-v2` |
| `sourceId` | Yes | `supplier-a:2026-11-16:v2` |

A simple validator implementation with **Spring Batch 5.x**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class ImportJobParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters params)
            throws JobParametersInvalidException {

        if (params == null) {
            throw new JobParametersInvalidException(
                    "JobParameters is required");
        }

        require(params, "inputPath");
        require(params, "sourceId");

        String schemaVersion = require(params, "schemaVersion");
        if (!"orders-v2".equals(schemaVersion)) {
            throw new JobParametersInvalidException(
                    "Unsupported schemaVersion: " + schemaVersion);
        }

        String businessDate = require(params, "businessDate");
        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use ISO yyyy-MM-dd");
        }
    }

    private static String require(JobParameters params, String name)
            throws JobParametersInvalidException {
        String value = params.getString(name);
        if (value == null || value.isBlank()) {
            throw new JobParametersInvalidException(
                    "Missing required parameter: " + name);
        }
        return value;
    }
}
```

The validator above only handles conditions **that can be checked from parameters**: non-empty value, valid format, valid schema version. It does not open the file; opening and checking size/header is deferred to the preflight step afterward.

**Note:** validating `inputPath` does not stop at "non-empty". In production applications, ensure the path or object key belongs to an allowed source scope to avoid accepting arbitrary external paths to read sensitive files.

### Attaching the Validator to a Job

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step importDataStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(new ImportJobParametersValidator())
            .start(preflightStep)
            .next(importDataStep)
            .build();
}
```

In Spring Batch 5.x, `JobBuilder` comes from `org.springframework.batch.core.job.builder.JobBuilder`, `JobRepository` belongs to `org.springframework.batch.core.repository.JobRepository`, and `Step` belongs to `org.springframework.batch.core.Step`. The example assumes `preflightStep` and `importDataStep` are already defined in the Spring context.

When parameter validation fails, do not assume there will always be a failed `StepExecution`: no step has been launched yet. The observable outcome at the launcher and repository depends on the call path and how the framework manages executions; orchestration APIs should catch and report parameter errors clearly.

## 6. Preflight Step: Checking the File Before the Reader Runs

In Spring Batch, an easily observable approach is to place a `TaskletStep` at the front of the flow.

### 6.1. Writing a Source Validation Service

For example, preflight only accepts CSV files with a fixed header and size between 1 byte and 250 MB. The project runs Java 17 or higher:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Component;

@Component
public class CsvInputPreflight {

    private static final long MAX_SIZE = 250_000_000L;
    private static final String EXPECTED_HEADER =
            "order_id,customer_id,amount";

    public void validate(Path input) throws IOException {
        Path actual = input.toRealPath();

        if (!Files.isRegularFile(actual) || !Files.isReadable(actual)) {
            throw new IllegalArgumentException(
                    "Input must be a readable regular file");
        }

        long size = Files.size(actual);
        if (size == 0 || size > MAX_SIZE) {
            throw new IllegalArgumentException(
                    "Input size is outside permitted range: " + size);
        }

        try (BufferedReader reader =
                     Files.newBufferedReader(actual, StandardCharsets.UTF_8)) {
            String header = reader.readLine();

            if (header == null) {
                throw new IllegalArgumentException("Missing CSV header");
            }
            if (header.startsWith("\uFEFF")) {
                header = header.substring(1); // UTF-8 BOM
            }
            if (!EXPECTED_HEADER.equals(header)) {
                throw new IllegalArgumentException(
                        "Unexpected CSV header");
            }
        }
    }
}
```

Key points:

- `toRealPath()` surfaces missing-source errors and resolves the path/symlink to the real path; it **does not create a sandbox** or protect against changes after the check.
- `isRegularFile` excludes many non-regular-file sources, such as directories.
- The size limit helps prevent an accidentally oversized batch from exhausting resources.
- Reading the header via `BufferedReader` avoids loading the entire file into memory.
- The BOM handling snippet supports a common UTF-8 variant.
- `IOException` and `IllegalArgumentException` propagate to the step so the system can report failure.

This is a **minimal structural preflight**. It does not verify record count, quoted CSV, per-row data types, checksum, or whether an uploader is currently modifying the file. Those requirements need to be extended with the corresponding parser, manifest, and staging mechanism.

A file with a valid header that contains only the header will pass the `size > 0` condition. If the contract requires at least one record, you must verify the existence of a valid record or compare the record count in the manifest, rather than treating non-zero byte count as sufficient.

### 6.2. Attaching the Service to a Tasklet with StepScope

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

import java.nio.file.Path;

@Bean
@StepScope
Tasklet preflightTasklet(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        CsvInputPreflight preflight) {

    return (contribution, chunkContext) -> {
        preflight.validate(Path.of(inputPath));
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` is required in this example so the `inputPath` parameter is resolved **when the step runs**, rather than when Spring creates beans during application startup.

If `validate(...)` throws an exception, the Tasklet does not return `RepeatStatus.FINISHED`. The step is marked failed under the normal execution mechanism; subsequent steps via `.next(...)` will not run in the successful sequential flow. If all checks pass, the Tasklet finishes and the import step is allowed to start.

### 6.3. Defining preflightStep

```java
@Bean
Step preflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet preflightTasklet) {

    return new StepBuilder("preflightStep", jobRepository)
            .tasklet(preflightTasklet, transactionManager)
            .build();
}
```

Related imports for Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.transaction.PlatformTransactionManager;
```

The Tasklet can check checksums, schemas, manifests, or call a source-management service, but preflight should be kept **read-only** or write audits through a clear mechanism. Avoid turning a validation step into a place that silently mutates source data, because that makes it hard to determine which snapshot was validated.

## 7. When Is a Full File Scan Needed?

Preflight can be lightweight or thorough; this decision affects latency and cost.

| Check Type | Can It Be Done Quickly on Metadata/Header? | Does It Need to Read the Entire File? |
| --- | --- | --- |
| File existence / read permission | Yes | No |
| Size / name / extension | Yes | No |
| Header and schema version | Usually yes | No |
| SHA-256 checksum | No, unless a trusted checksum from storage is already available | Usually must read all bytes |
| Actual row count | No | Yes, or requires a trusted manifest/metadata |
| Every row is parseable | No | Yes |
| Duplicate business key in file | No | Yes, usually needs a key set or external index |
| Reconciliation amount totals | No | Yes |
| Cross-file referential integrity | No | Yes, or requires join/staging |

If the requirement is "no business data may be written before knowing the entire batch is valid," a full validation pass before import may be necessary. If good data can be accepted and bad data quarantined, chunk-level validation typically saves more I/O.

### 7.1. Option A: Lightweight Preflight + In-Batch Validation

Suitable when:

- Data is very large.
- Skipping or quarantining some records is acceptable.
- Output can be reconciled and conditionally published.
- Reader/processor/writer are designed to be idempotent.

Flow:

```text
Metadata/header preflight -> chunk import -> row validation
                           -> controlled skip/quarantine
                           -> reconcile -> publish if quality passes
```

### 7.2. Option B: Full Validation Before Import

Suitable when:

- Financial batches must be "all-or-nothing" at the business level.
- One invalid record means the entire batch must not be processed.
- The source has mandatory reconciliation totals.
- The cost of late error detection is very high.

Flow:

```text
Immutable staging file -> 100% validate -> result VALIDATED
                  -> import/publish or REJECTED
```

Trade-off: scanning the data twice consumes I/O and time. For large pipelines, you can read once into a **staging table** and validate on staging, then move validated data to business tables within a well-designed transaction/publish method.

## 8. Checksums, Manifests, and Input Immutability

In multi-system batch integrations, "file exists" is usually too weak. A source contract might look like:

```json
{
  "sourceId": "supplier-a:2026-11-16:v2",
  "businessDate": "2026-11-16",
  "schemaVersion": "orders-v2",
  "dataObject": "orders_2026-11-16_v2.csv",
  "recordCount": 150000,
  "sha256": "a9b8...example..."
}
```

In the example, the `sha256` field is an **abbreviated illustrative value**, not a valid checksum to put in code. With a real manifest, the checksum must have its full value and come from a trusted source.

Steps:

1. The producer uploads data to an unpublished staging area.
2. The producer computes the checksum and record count and emits a manifest/ready marker when upload completes.
3. The consumer checks access permissions, schema version, record count, checksum (when present), and business date.
4. The consumer stamps the source as **VALIDATED** by `sourceId`/checksum.
5. The import step reads the **exact data version that was validated**, rather than picking "the latest file" at runtime.

### What Does Checking the Hash Mean?

SHA-256 helps detect that the file's bytes differ from the manifest value. It does not prove the data is business-valid, and it does not by itself prove the manifest came from a trusted source. If an attacker can alter both the file and the manifest, you need authentication, access control, and an appropriate source signing/verification mechanism.

JDK example computing a checksum by streaming, avoiding loading the whole file into RAM:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.io.IOException;
import java.util.HexFormat;

public static String sha256(Path path)
        throws IOException, NoSuchAlgorithmException {

    MessageDigest digest = MessageDigest.getInstance("SHA-256");

    try (InputStream stream = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = stream.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return HexFormat.of().formatHex(digest.digest());
}
```

The checksum must be computed on the **exact byte stream** that the importer will use. If you convert encoding, decompress, or normalize the file between checking and processing, specify clearly whether the checksum applies to the original or transformed version.

### Preventing TOCTOU

```text
10:00:00 validate /inbox/orders.csv -> OK
10:00:03 producer overwrites old file
10:00:05 reader opens /inbox/orders.csv -> different content
```

Checking metadata once and opening the file later is not enough. A more reliable approach is using an object version/ETag, an immutable snapshot, or copying to a checksum-identified name with appropriate write permissions. If no snapshot exists, you must re-verify when opening the source and recognize that mere re-checking still has a race condition.

## 9. Record Validation: Handling Invalid Items Differently from an Invalid Batch

If preflight fails due to a wrong schema, you **should not import**. But in a one-million-record batch, 5 invalid customer codes may have a different handling policy.

Example rule in a processor:

```java
public ValidatedOrder process(OrderRow row) {
    if (row.amount().signum() <= 0) {
        throw new InvalidOrderDataException(
                "amount must be positive");
    }
    return new ValidatedOrder(
            row.orderId(),
            row.customerId(),
            row.amount());
}
```

With a fault-tolerant step:

```java
new StepBuilder("importDataStep", jobRepository)
        .<OrderRow, ValidatedOrder>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderDataException.class)
        .skipLimit(100)
        .build();
```

`OrderRow`, `ValidatedOrder`, and `InvalidOrderDataException` are application types; the builder example assumes the beans are fully provided. For some datasets, `skipLimit(100)` may be appropriate; for financial transactions requiring 100% completeness, the policy should fail and keep the batch in a reconciliation-required state.

**Do not turn every exception into a skip.** You must distinguish deterministic data errors (`InvalidOrderDataException`) from transient system errors (network timeout) and program bugs. `skip(Exception.class)` can let a job finish `COMPLETED` while silently losing data.

### Filtering Is Not Skipping

A processor returning `null` to drop an out-of-scope record increments `filterCount`, not `processSkipCount`. If invalid records must be reported, do not use `return null` instead of an exception/audit without an explicit rule.

## 10. Deciding Accept, Reject, or Quarantine

A quality policy must answer **whether the batch can continue** and **where bad data goes**.

| Situation | Example Decision | Output to Store |
| --- | --- | --- |
| Missing file | Reject entire batch | `sourceId`, error code `INPUT_NOT_FOUND` |
| Wrong schema version | Reject entire batch | Expected/actual version |
| Checksum mismatch | Reject, do not import | Manifest ID, received checksum |
| One row with negative amount, good data allowed to proceed | Quarantine row | Source, line number, business key, error code |
| Final amount total does not match control total | Block publish or fail quality gate | Expected total, actual total |
| Duplicate source already completed | Skip receiving batch or reject per policy | ID of already processed batch |
| Same `sourceId` but new checksum | Conflict/revision flow | Version and approval decision |

No single error threshold fits all jobs. For example:

```text
file ingestion:
  structuralErrorsAllowed: 0
  invalidRowsAllowed: 50
  invalidRowPercentageAllowed: 0.1%
  missingMandatoryReferencesAllowed: 0
```

This is an example of a **business policy**, not default Spring Batch configuration properties.

When multiple thresholds exist, apply explicit combination logic, such as **reject if invalidRows > 50 OR invalidRows / readRows > 0.001**. When `readRows=0`, a separate rule is needed; never divide by 0 and interpret it as "0% error rate".

If the decision depends on the error rate across the **entire batch**, you usually must read everything/store in staging before confirming the batch is valid. Using step-level skip-limit is a technical mechanism per item; it does not automatically replace a holistic multi-condition quality policy.

## 11. Designing a Quality Gate Before Publish

A batch can use staging to ensure only quality-passing data is published:

```text
                       input snapshot
                             |
                             v
                     preflightStep
                             |
                             v
                     loadStagingStep
                 / valid + invalid rows
                             |
                             v
                   validateStagingStep
                    / total + duplicate
                    / cross-reference
                             |
             +---------------+----------------+
             |                                |
          PASSED                            FAILED
             |                                |
             v                                v
      publishValidatedStep              quarantine/reject
             |
             v
        final output
```

A quality gate can compare:

```text
manifest.recordCount = staged.validCount + staged.invalidCount
manifest.controlTotal = staged.validAmountTotal + policy-specific adjustments
duplicateCount <= allowedDuplicateCount
invalidCount <= allowedInvalidCount
```

Reconciliation formulas must be defined by the business contract: if the source sums all rows while the job only sums valid rows, those two numbers may differ according to acceptance rules. Do not force an equality that does not match business semantics.

### Transaction Implications

If an import has already committed multiple chunks to the **final table**, detecting an error in the final step does not automatically roll back all prior chunks. To achieve the effect of "not published until quality passes," you can write to a staging table and only transition to a visible/final state when the gate succeeds. The publish process also needs transactions and an idempotent retry mechanism.

For object storage or data outside a database, "publish" can mean updating a manifest/marker so downstream consumers only consume published objects.

## 12. Restart and Rerun: May the Input Change?

In Spring Batch, a `JobInstance` is identified by the job name and **identifying JobParameters**. A failed instance can restart from a checkpoint via `JobRepository` and `ExecutionContext`.

Example:

```text
sourceId = supplier-a:2026-11-16:v2
businessDate = 2026-11-16
snapshotSha256 = <hash-of-staged-file>

JobExecution #41: preflight COMPLETED
                  importDataStep FAILED at row 3200

JobExecution #42: restart same JobInstance
                  importDataStep continues from checkpoint
```

To restart properly:

1. The source must keep the **same content and record order** if the reader recovers by position.
2. Do not delete `JobRepository`/`ExecutionContext` metadata when restart is needed.
3. `businessDate` and business-logic cutoffs must remain stable.
4. The writer must prevent duplicates if a portion of data is replayed.
5. If the file must be modified, there must be a policy for a **new version and new job instance** or a dedicated recovery mechanism.

### Does preflightStep Run Again on Restart?

By default, Spring Batch typically **skips a step that is already COMPLETED** when restarting the same instance, if the flow and configuration allow it. Thus a `preflightStep` that completed in the previous execution does not necessarily run again.

There are two strategies:

- **Immutable snapshot:** preflight verifies a locked snapshot/version; restart reads that exact snapshot, and there is no need to re-check the entire file every time.
- **Intentional revalidation:** configure `allowStartIfComplete(true)` on the preflight step if you want the step to always re-run on restart. The new validation must be compatible with checkpoints and must not inadvertently swap the source.

Builder example:

```java
new StepBuilder("preflightStep", jobRepository)
        .tasklet(preflightTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

This is a design choice, not a mandatory default. Revalidating an unversioned file can detect changes after part of the output has already been committed; that is an error to handle under a recovery policy, not by blindly deleting output and starting over from scratch.

### Distinguishing Duplicate Input from Duplicate JobInstance

Simply changing `run.id` can create a new instance, but it does not automatically make business data safe when re-run. If the same file is imported twice into an orders table, you need a unique constraint/upsert/idempotency key on the appropriate **business key**. `sourceId` can assist admission, but it does not replace uniqueness constraints in the writer.

## 13. Testing Preflight with JUnit

Infrastructure tests should include both **service unit tests** and **job flow integration tests**.

### 13.1. Unit Testing File Validation with @TempDir

JUnit Jupiter provides `@TempDir` to create a separate directory for each test. Example testing `CsvInputPreflight` above:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CsvInputPreflightTest {

    @TempDir
    Path tempDir;

    private final CsvInputPreflight preflight =
            new CsvInputPreflight();

    @Test
    void acceptsExpectedHeader() throws Exception {
        Path input = tempDir.resolve("orders.csv");
        Files.writeString(
                input,
                "order_id,customer_id,amount\nORD-1,C01,100.00\n",
                StandardCharsets.UTF_8
        );

        assertDoesNotThrow(() -> preflight.validate(input));
    }

    @Test
    void rejectsWrongHeader() throws Exception {
        Path input = tempDir.resolve("wrong-header.csv");
        Files.writeString(
                input,
                "order_id,customer_name,amount\nORD-1,Alice,100.00\n",
                StandardCharsets.UTF_8
        );

        assertThrows(IllegalArgumentException.class,
                () -> preflight.validate(input));
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        Path input = tempDir.resolve("empty.csv");
        Files.write(input, new byte[0]);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.validate(input));
    }

    @Test
    void missingFileRaisesIOException() {
        Path input = tempDir.resolve("missing.csv");
        assertThrows(java.io.IOException.class,
                () -> preflight.validate(input));
    }

    @Test
    void acceptsUtf8BomBeforeExpectedHeader() throws Exception {
        Path input = tempDir.resolve("bom.csv");
        Files.writeString(
                input,
                "\uFEFForder_id,customer_id,amount\nORD-1,C01,100.00\n",
                StandardCharsets.UTF_8
        );

        assertDoesNotThrow(() -> preflight.validate(input));
    }
}
```

These tests verify **storage and the minimal conditions** of preflight. They do not assert that every record is valid or guarantee the file cannot change after checking.

### 13.2. Unit Testing JobParametersValidator

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;

class ImportJobParametersValidatorTest {

    private final ImportJobParametersValidator validator =
            new ImportJobParametersValidator();

    @Test
    void acceptsValidParameters() {
        var params = new JobParametersBuilder()
                .addString("inputPath", "/staging/orders.csv")
                .addString("sourceId", "supplier-a:2026-11-16:v2")
                .addString("businessDate", "2026-11-16")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters();

        assertDoesNotThrow(() -> validator.validate(params));
    }

    @Test
    void rejectsInvalidBusinessDate() {
        var params = new JobParametersBuilder()
                .addString("inputPath", "/staging/orders.csv")
                .addString("sourceId", "supplier-a:2026-11-16:v2")
                .addString("businessDate", "16/11/2026")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters();

        assertThrows(JobParametersInvalidException.class,
                () -> validator.validate(params));
    }
}
```

This is a unit test of the parameter contract; it does not need to open a file or run a job. The path `/staging/orders.csv` is an illustrative value and is not accessed in the validator test.

### 13.3. Integration Test: When Preflight Fails, the Importer Must Not Write

With Spring Batch 5.x and `spring-batch-test`, configure a test job with `preflightStep` and `importDataStep`, storing output in a test database. Use `@SpringBatchTest`, `@SpringBootTest(properties = "spring.batch.job.enabled=false")`, and `JobLauncherTestUtils` to drive the run.

Scenario:

1. Create a CSV file with a wrong header.
2. Launch the job with `inputPath` pointing to that file and other valid `JobParameters`.
3. Verify `JobExecution` ends `FAILED`, and preflight has `StepExecution.FAILED`.
4. Verify `importDataStep` **did not run**, and no business records were inserted.
5. Replace with a valid file, run a new `JobInstance`, and verify the importer runs.

Example verification snippet in a configured test:

```java
JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
                .addString("inputPath", badCsv.toString())
                .addString("sourceId", "test-invalid-" + UUID.randomUUID())
                .addString("businessDate", "2026-11-16")
                .addString("schemaVersion", "orders-v2")
                .toJobParameters()
);

assertEquals(BatchStatus.FAILED, execution.getStatus());

assertTrue(
        execution.getStepExecutions().stream()
                .anyMatch(s -> s.getStepName().equals("preflightStep")
                        && s.getStatus() == BatchStatus.FAILED)
);

assertTrue(
        execution.getStepExecutions().stream()
                .noneMatch(s -> s.getStepName().equals("importDataStep"))
);

assertEquals(0, countBusinessRows());
```

This is an **illustrative excerpt**: `launcher`, `badCsv`, and `countBusinessRows()` must be declared in the test class, along with the actual job and test database. The test must isolate prior output so `countBusinessRows()` is meaningful; when using `@SpringBatchTest` and a context containing multiple jobs, remember to assign the right job to the launcher.

**Version note:** The configuration examples use Spring Batch 5.x. Spring Batch 6 changes some packages and test launch utilities (newer examples use `JobOperatorTestUtils`). Adjust imports/APIs according to the version used by the project.

### 13.4. Test Data to Include

| Code | Input | Expected Outcome |
| --- | --- | --- |
| V01 | Complete parameters, valid file | Preflight completes, importer runs |
| V02 | Missing `inputPath` | Validator rejects |
| V03 | Malformed `businessDate` | Validator rejects |
| V04 | File does not exist | Preflight fails |
| V05 | Empty file | Preflight fails |
| V06 | Wrong header | Preflight fails |
| V07 | Allowed UTF-8 BOM | Preflight passes if contract permits |
| V08 | Valid header but invalid record | Reader/processor handles per policy |
| V09 | File upload incomplete | Do not mark READY; reject or wait via orchestration |
| V10 | Checksum differs from manifest | Reject without importing |
| V11 | Same `sourceId` resent | Accept/reject per idempotency policy |
| V12 | Restart with unchanged snapshot | Resume from exact checkpoint |
| V13 | Snapshot altered between runs | Detect change, do not mix two versions |
| V14 | Control total out of balance | Block publish |

When running tests, verify the **actual output** and **StepExecution status**. `JobExecution.COMPLETED` alone does not prove the batch satisfied every quality rule.

## 14. Logging, Audit, and Monitoring for Validation

If preflight fails, a log that only records `IllegalArgumentException` will not be enough for operations. You need to know:

```text
jobName
jobExecutionId
stepName
stepExecutionId
sourceId
businessDate
schemaVersion
snapshotIdentifier / checksum
validationStage
errorCode
expectedValue (if safe)
actualValue (if safe)
```

Example structured log:

```json
{
  "event": "input_rejected",
  "jobName": "importOrdersJob",
  "stepName": "preflightStep",
  "sourceId": "supplier-a:2026-11-16:v2",
  "validationStage": "schema",
  "errorCode": "HEADER_MISMATCH",
  "schemaVersion": "orders-v2"
}
```

Do not put full payloads or sensitive paths into public logs. When logging from a multi-tenant or multi-environment system, ensure `sourceId` and parameters are logged within the appropriate access scope.

Application metrics you can define:

| Metric | Meaning |
| --- | --- |
| `batch_input_validation_total{jobName,result,reason}` | Count of preflight passes/rejects by error group |
| `batch_input_validation_duration_seconds{jobName}` | Duration of input validation |
| `batch_input_bytes{jobName}` | Size of received source |
| `batch_invalid_records_total{jobName,reason}` | Number of invalid records by bounded category |
| `batch_source_age_seconds{jobName}` | Delay from source readiness to ingestion |
| `batch_reconciliation_failed_total{jobName}` | Count of final quality gate failures |

These names are **custom metric suggestions**, not default names across all Spring Batch/Micrometer versions. Avoid labels like `sourceId`, file name, record ID, checksum, or exception message if cardinality is high; keep those in controlled logs/audits, while metrics retain only bounded label sets.

### Distinguishing Input Errors from Infrastructure Errors

`INPUT_NOT_FOUND`, `SCHEMA_MISMATCH`, and `BUSINESS_DATE_MISMATCH` usually require contacting the data source team. `DATABASE_UNAVAILABLE`, `OBJECT_STORAGE_TIMEOUT`, or misconfiguration usually require infrastructure handling. If everything is lumped into a single `FAILED` metric, on-call will not know which team to route the incident to.

It is better to classify outcomes:

```text
VALID
REJECTED_SOURCE
REJECTED_SCHEMA
REJECTED_BUSINESS_RULE
TRANSIENT_INFRASTRUCTURE_FAILURE
INTERNAL_ERROR
```

In Spring Batch, you can store the error code in `ExitStatus` or an audit store, but you must align the handling contract with the scheduler/orchestrator. Do not assume a custom exit code will automatically change `BatchStatus` as desired: `BatchStatus` and `ExitStatus` have distinct roles.

## 15. Common Mistakes

### Only Checking That the File Exists

An existing file might still be mid-write, have the wrong header, a different checksum, or belong to the wrong business period. Use a ready signal + manifest/snapshot when the contract requires integrity.

### Using the File Extension as a Format Check

The name `orders.csv` does not guarantee the content is CSV matching the schema. Check encoding, header, and parse according to the contract; for untrusted data, enforce resource limits and use an appropriate parser.

### Parsing CSV by Splitting on Commas

Valid CSV can contain quoted fields and commas inside values, such as `"ACME, Inc."`. `String.split(",")` easily splits incorrectly. Use a CSV parser that supports quoting/escaping.

### Validating One File and Processing Another

If the source changes after preflight, the validation result is no longer tied to the imported data. Use an immutable snapshot/version and bind source identity to the job.

### Putting All I/O into JobParametersValidator

The parameter validator is suited for rejecting invalid configurations. An explicit preflight step is much better for metadata, timing, failure diagnostics, and workflow management when expensive I/O or full scans are involved.

### Heavy Preflight Without Considering I/O

Reading the entire file to validate and then having the importer read it again can add significant cost. For large data, consider a single pass loading into staging followed by validate/publish, or split appropriately between upfront structural checks and in-chunk record validation.

### Treating Any Invalid Record as Reason to Reject the Whole Batch

Data policy determines fail vs. skip. If the contract allows quarantining 10 bad rows out of one million, preflight does not necessarily have to reject the whole file because of one bad record. Conversely, a financial job may need to reject the entire batch if a critical value is wrong.

### Treating Every Exception as Bad Data

An HTTP timeout or database outage is not proof that the file is invalid. Classify exceptions so the scheduler can retry transient failures, while contract-violating data is routed to a data-remediation workflow.

### Failing to Re-check on Restart

If a file can be overwritten, checkpoints from an old run are no longer valid. Lock the snapshot or revalidate in a way that does not alter the identity of the data being processed.

### Deleting JobRepository to Rerun

Spring Batch metadata stores history and checkpoints. Deleting it to "ignore errors" makes restart, audit, and duplicate prevention hard to control. Separate restart, rerun, and processing a new version.

### Only Asserting That the Job Is COMPLETED

A completed job can still contain wrongly filtered records, unreconciled skips, or mismatched amount totals. Tests must measure output quality and the final gate result, not just status.

## 16. Practice Exercises

**Exercise 1 — JobParametersValidator.** Write a validator requiring `inputPath`, `businessDate`, and `schemaVersion`. Create unit tests for missing parameters, wrong date format, and unsupported version.

**Exercise 2 — File preflight.** Write a Tasklet that checks file existence, non-empty file, and header `order_id,customer_id,amount`. Use `@TempDir` to create test files; verify preflight fails on an empty file or wrong header.

**Exercise 3 — Blocking the importer.** Create a job with `preflightStep` followed by `importDataStep`. For an invalid file, verify the importer does not run and the business table has no new rows.

**Exercise 4 — Manifest and checksum.** Create a manifest with `sourceId`, `businessDate`, `recordCount`, and SHA-256. Recompute the hash by streaming; verify a file altered by a single byte is rejected.

**Exercise 5 — Record validation policy.** Add a row with a negative amount. Compare two policies: fail the entire batch vs. bounded skip/quarantine. Document expected output, valid row count, invalid row count, and publish eligibility.

**Exercise 6 — Restart.** Have the job stop at the third chunk and then restart. Fix an immutable input snapshot, preserve `JobRepository`, and verify the writer does not duplicate data. Then try modifying the file between two runs to test the policy for rejecting altered data.

**Exercise 7 — Reconciliation.** Use staging with 100 orders where the manifest reports 100 rows but only 99 rows parse. Design a quality gate that rejects publishing and stores an error code for operations to handle.

**Exercise 8 — Monitoring.** Export metrics for total batches accepted/rejected by error group, preflight duration, and quarantined record count. Build a dashboard distinguishing partner data errors from infrastructure errors.

## 17. Conclusion

**Pre-batch input validation** is the safeguard for quality and repeatability in a Spring Batch pipeline. It starts with **JobParametersValidator** to protect the parameter contract, continues with a **preflight step** checking source/schema/manifest before importing data, and combines per-record validation with a **quality gate** before publishing.

The core point is knowing **which input was actually checked**, validating and processing the **exact same immutable snapshot**, and having clear policies for **reject, skip, quarantine, retry, restart, and rerun**. A job merely reporting `COMPLETED` when its steps finish does not guarantee data quality; the system must also reconcile counts, business values, and handling of invalid records. When those requirements are modeled clearly, input errors are caught early, easy to investigate, and far less likely to corrupt downstream data.

### References

- [Spring Batch Reference — JobParameters and JobInstance](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
