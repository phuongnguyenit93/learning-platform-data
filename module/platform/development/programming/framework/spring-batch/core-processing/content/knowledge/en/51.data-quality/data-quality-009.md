# Input Schema Versioning in Spring Batch

## 1. Why Version Input Data Schemas?

A Spring Batch job can ingest data from CSV files, JSON/NDJSON, XML, Avro, Parquet, staging databases, or batched messages exported from other systems. While the job keeps running, **input structure can evolve**: columns get added, fields get renamed, data types change, date conventions shift, or new enum values appear in a status field.

Suppose `importOrdersJob` is reading a CSV file:

```csv
# schema-version: v1
order_id,customer_id,amount
ORD-001,CUS-10,125000
ORD-002,CUS-11,320000
```

An upstream system upgrades and begins exporting:

```csv
# schema-version: v2
order_id,customer_id,amount,currency
ORD-001,CUS-10,125000,VND
ORD-002,CUS-11,320000,VND
```

If the old reader still assumes every line has exactly three fields, several outcomes can occur: the parser fails on column count, columns map into wrong fields, or the new field is silently dropped without anyone noticing. With subtler changes like renaming `amount` to `net_amount`, the job may even **succeed technically while producing wrong business results**.

**Input schema version** is a version identifier bound to a data contract understood by both sender and receiver. It lets a batch job decide whether an input is supported, choose the right parse/validate rules, map data into a unified model, and preserve an audit trail for reconciliation or reruns.

```text
Source system
    |
    +-- Input + schemaVersion + metadata / manifest
                     |
                     v
               Preflight validation
               - Identify version
               - Check contract
               - Verify file stability
                     |
             +-------+-------+
             |               |
           Valid        Unsupported / bad
             |               |
             v               v
    Versioned Reader    Reject / Quarantine
             |
             v
      Canonical model
             |
             v
      Processor / Writer / JobRepository
```

Key distinction: the **business input schema version** differs from the version of **`BATCH_*` tables** in `JobRepository` and differs from database schema migrations. All three can coexist in one application, yet each governs a separate contract.

## 2. What Does a Schema Include?

Do not treat a schema as merely a list of column names. In a data pipeline, distinguish at least three contract layers:

| Contract Layer | Content | Example Failures |
|---|---|---|
| **Physical / syntax** | Encoding, delimiter, quote/escape, column order, file header, JSON object shape, primitive types | CSV file uses `;` instead of `,`; numeric field parsed wrongly. |
| **Structural** | Required/optional fields, data types, lengths, precision, supported field set | Missing `customer_id`; `amount` changes from number to non-conforming string. |
| **Semantic** | Field meaning, unit of measure, timezone, business rules, value ranges, defaults | `amount` changes from VND to thousands of VND while keeping the same column name. |

Two files sharing the header `order_id,amount` are not necessarily compatible. If a new version changes `amount` from single currency units to thousands, the old reader may not throw an error yet write numbers off by a factor of a thousand. **Semantic changes must be captured in the contract/version**, even when structure stays unchanged.

A useful schema specification typically includes:

1. Dataset or event type name (`orders`, `customers`, `payments`).
2. Concrete `schemaVersion` (`v1`, `v2`, `2026-11`, etc.) and applicability scope.
3. Format, encoding, delimiter, and escape/quote policies.
4. Field list: name, type, required vs. optional, bounds, and defaults.
5. Business semantics: currency unit, timezone, enums, and null interpretation.
6. Changes relative to prior versions and compatibility policy.
7. Version identification method, behavior when missing, and support lifecycle.
8. Input validation rules and handling of invalid files.

## 3. Schema Evolution Example: v1, v2, and v3

Suppose a provider sends order files. The contract evolves as follows:

| Version | Structure | Rules | Status |
|---|---|---|---|
| `v1` | `order_id,customer_id,amount` | Under v1 contract, `amount` is always VND. | Supported during transition period. |
| `v2` | Adds required `currency` column | `amount` uses the unit specified by `currency`. | Recommended version. |
| `v3` | Renames `amount` to `net_amount`, adds `tax_amount` | Total amount is computed from both fields per v3 rules. | Requires new parser/mapper. |

In business processing code, we normalize all variants into one canonical model:

```java
import java.math.BigDecimal;

public record NormalizedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        String currency) {
}
```

Mapping example:

```text
Input v1: order_id=ORD-001, amount=125000
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")

Input v2: order_id=ORD-001, amount=125000, currency=VND
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")

Input v3: net_amount=120000, tax_amount=5000, currency=VND
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")
```

Summing `net_amount + tax_amount` is strictly an **illustrative business assumption**. If those two fields do not equate to the old `amount` meaning, never sum them blindly and treat them as equivalent. Normalization must come from the source's official data contract.

**Why normalize before the processor?** Processors, writers, and reconciliation logic can work against `NormalizedOrder` instead of scattering `if (v1)` and `if (v2)` branches throughout the pipeline. Schema-compatibility code is isolated at the input boundary, reducing the chance of mis-handling versions.

## 4. Backward Compatibility and Forward Compatibility

When ingesting multiple versions, state the compatibility direction clearly.

- **Backward compatible:** a **new** reader/consumer can read data written under an **old** schema.
- **Forward compatible:** an **old** reader/consumer can read data written under a **new** schema.
- **Full compatible:** both directions hold within published policy limits.

These concepts appear in many schema registry systems. Actual compatibility also depends on format, parser, defaults, unknown-field handling, and business rules; it cannot be deduced merely from "a column was added."

| Change | Typical Compatibility | What to Verify |
|---|---|---|
| Add optional field with clear default | Easy to support backward compatibility | Does the old reader ignore unknown fields? Does the new consumer have a fallback for old data? |
| Add required field without default | Usually breaks backward compatibility | Old inputs lack a value for the new field. |
| Rename/remove required field | Usually a breaking change | Is there an alias or migration layer? |
| Change `String` to numeric type | Can break compatibility | Do old values parse? How are null/empty handled? |
| Change `Long` to decimal | Depends on format and consumer | Precision, rounding, scale, and representation. |
| Add enum value | Can break old consumers | Unknown enum handling / fallback value. |
| Append CSV column at the end | Depends on parser | Strict readers may reject the new column count. |
| Reorder CSV columns | Can cause silent corruption | Does the reader map by position or header name? |
| Change timezone/unit keeping same type | Major semantic change | Needs explicit version and conversion rules. |

For example, `v2` adding `currency` is not automatically compatible with a `v1` reader. If the reader uses a strict `DelimitedLineTokenizer` expecting three columns, it fails when receiving four values. If the reader ignores the extra column while `amount` can now hold USD, it may **write the wrong currency unit** even without a parser error.

### 4.1. Version Support Policy

An engineering team might publish:

```text
Dataset: orders
Current schema: v2
Accepted inputs: v1, v2
Rejected inputs: unknown, v0, unimplemented v3
v1 deprecation date: per agreed rollout schedule
```

While `v1` remains supported, keep tests proving both `v1` and `v2` convert into the same canonical model with exact business semantics. When retiring `v1`, announce ahead of time and establish a clear migration path or explicit rejection rule. Never let a version "quietly expire" just because new code accidentally breaks parsing old files.

## 5. How to Identify Input `schemaVersion`

Version metadata can live in several places; choose one that is explicit and verifiable.

### 5.1. File Header

Example CSV with two metadata/header lines:

```csv
# schema-version: v2
order_id,customer_id,amount,currency
ORD-101,CUS-44,150000,VND
```

Pros: version travels with content; the file self-describes its contract. Cons: the first line may not follow standard CSV syntax, so the reader must skip the metadata line; BOM, whitespace, encoding, line endings, and comment markers must be explicitly specified.

Single-document JSON example:

```json
{
  "schemaVersion": "v2",
  "dataset": "orders",
  "records": [
    {"orderId": "ORD-101", "customerId": "CUS-44", "amount": 150000, "currency": "VND"}
  ]
}
```

For very large files, do not force loading the whole `records` array into memory just to read the version. Prefer **NDJSON + manifest** or an appropriate streamable envelope depending on format and reader.

### 5.2. External Manifest or Metadata

Example `orders-2026-11-16.manifest.json`:

```json
{
  "dataset": "orders",
  "schemaVersion": "v2",
  "objectKey": "staging/orders/2026-11-16/orders.csv",
  "sha256": "<sha256-hex-of-file>",
  "encoding": "UTF-8",
  "format": "CSV",
  "recordCount": 1200000
}
```

The string `<sha256-hex-of-file>` in the example is a placeholder; production requires a real digest. Manifests work well when data files cannot carry extra headers or when you need checksums, sizes, export timestamps, or multi-file delivery contracts.

Some systems store versions in object storage metadata, staging batch database rows, or a schema registry. Wherever it lives, verify **metadata matches the exact physical revision of the object** being read. For instance, the same object path could be overwritten after the job starts. Storage supporting `versionId` or immutable keys reduces the risk of reading a newer object by mistake.

### 5.3. Schema Registry and Self-Describing Formats

Avro/Protobuf and event protocols can use schema IDs/fingerprints with a schema registry; container formats like Avro Object Container File can also embed the writer schema. The batch job must identify the input's **writer schema** and the application's supported **reader schema**, then apply matching compatibility rules.

This differs from parsing a `v2` string out of CSV. With a registry, rely on formal schema IDs/resolution rather than guessing from filenames. Also plan for registry unavailability and schema caching strategies in test and production environments.

### 5.4. Do Not Guess Version from Data When an Explicit Contract Exists

Heuristics like "four columns means v2, three columns means v1" or "if filename contains `_v2` use v2" may help during transitions **only when formally agreed as a rule**, yet easily break when fields are added, headers change, rows are malformed, or filenames are renamed.

Prefer verified versions in manifests/headers/registries. If guessing is unavoidable for legacy data, isolate that logic in a dedicated, thoroughly tested detection step and **reject** whenever ambiguity remains.

## 6. Pre-Chunk Input Checking (Preflight Validation)

A batch job usually needs to distinguish **entire-file contract violations** from **isolated invalid records inside a file**.

```text
Newly received file
    |
    +-- Check source, name/object key, size, checksum
    +-- Read metadata/manifest/schema ID
    +-- Confirm version is supported
    +-- Check header, encoding, delimiter, required field types
    +-- Lock immutable input revision
    |
    +-- Fail -> reject entire file, never run writer
    |
    +-- Pass -> start reading and validating records
                 |
                 +-- Valid record -> processor/writer
                 +-- Bad record -> skip/quarantine/fail per policy
```

Key principles:

1. **Unknown schema version is a file-level failure.** Never let the reader silently fall back to a default parser and "try to see if it works."
2. **Schema mismatch is a contract failure.** With strict CSV, headers differing from the published version should be caught before writing business data.
3. **Record-level errors are a separate concern:** unparseable numbers, malformed dates, invalid enums, or blank values can follow skip/quarantine policies.
4. **Full preflight can carry I/O cost:** reading a header is cheap; computing SHA-256 on a multi-hundred-GB file requires scanning all bytes. Choose timing/hashing strategies wisely, and never assume object storage ETag is always a content SHA-256.
5. **Do not trust metadata blindly:** a manifest claiming `v2` while the file header is `v1` signals a contract violation. Enforce explicit rejection.

For pipelines where rejected records **must never appear in published data**, use `validate -> stage -> promote/publish` to check before releasing results. If whole-file atomicity is required, checking only the header and committing chunk by chunk will not suffice: early chunks would already be committed before a bad row near the end is seen.

## 7. Implementing Preflight for Two CSV Versions

This example uses **Java 17+, Spring Batch 5.x, Spring Boot 3.x, and JUnit 5**. Core Java APIs work standalone; Spring Batch classes changed packages in 6.x, so verify against your actual dependency version.

### 7.1. Defining Version and Header Policy

We accept `v1` and `v2` with exact contract headers. Here, line 1 must be `# schema-version: vN` and line 2 the CSV header.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public final class OrderSchemaPreflight {

    private static final String VERSION_PREFIX = "# schema-version: ";

    private static final Map<String, List<String>> ALLOWED_COLUMNS = Map.of(
            "v1", List.of("order_id", "customer_id", "amount"),
            "v2", List.of("order_id", "customer_id", "amount", "currency")
    );

    public record Result(String version, List<String> columns) {
    }

    public Result inspect(Path inputFile) throws IOException {
        try (BufferedReader input = Files.newBufferedReader(
                inputFile, StandardCharsets.UTF_8)) {

            String marker = input.readLine();
            if (marker == null || !marker.startsWith(VERSION_PREFIX)) {
                throw new IllegalArgumentException(
                        "Missing input schema version marker");
            }

            String version = marker.substring(VERSION_PREFIX.length()).trim();
            List<String> expectedColumns = ALLOWED_COLUMNS.get(version);
            if (expectedColumns == null) {
                throw new IllegalArgumentException(
                        "Unsupported input schema version: " + version);
            }

            String header = input.readLine();
            String expectedHeader = String.join(",", expectedColumns);
            if (!expectedHeader.equals(header)) {
                throw new IllegalArgumentException(
                        "Header mismatch for schema " + version);
            }

            return new Result(version, expectedColumns);
        }
    }
}
```

In this example, `ALLOWED_COLUMNS` defines policy manageable in code/tests. `inspect(...)` does not read millions of records; it checks metadata and header structure before the job starts reading.

**Intentional limitation of the example:** string comparison for headers only suits simple, fixed header conventions. Real CSVs may have BOMs, commas inside column names, quoting/escaping, policy-dependent whitespace, or multiline fields. When the contract allows such variants, use an RFC 4180-compliant CSV parser or equivalent tokenizer configuration. Never split data lines with `String.split(",")` when values can contain commas inside quotes.

### 7.2. Mapping Versions to a Shared Canonical Model

In Spring Batch 5.x, `FlatFileItemReader` combines `DefaultLineMapper`, `DelimitedLineTokenizer`, and `FieldSetMapper` to read CSV. Here the first two lines are metadata/header and are skipped; preflight has already verified them.

```java
import java.math.BigDecimal;

import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.core.io.FileSystemResource;

public final class OrderReaderFactory {

    public static FlatFileItemReader<NormalizedOrder> create(
            String inputPath, String schemaVersion) {

        String[] columns = switch (schemaVersion) {
            case "v1" -> new String[] {
                    "order_id", "customer_id", "amount"
            };
            case "v2" -> new String[] {
                    "order_id", "customer_id", "amount", "currency"
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported schema: " + schemaVersion);
        };

        DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
        tokenizer.setDelimiter(",");
        tokenizer.setNames(columns);
        tokenizer.setStrict(true);

        DefaultLineMapper<NormalizedOrder> lineMapper =
                new DefaultLineMapper<>();
        lineMapper.setLineTokenizer(tokenizer);
        lineMapper.setFieldSetMapper(fields -> {
            String currency = "v1".equals(schemaVersion)
                    ? "VND" // Default defined by the v1 contract.
                    : fields.readString("currency");

            return new NormalizedOrder(
                    fields.readString("order_id"),
                    fields.readString("customer_id"),
                    new BigDecimal(fields.readString("amount")),
                    currency);
        });

        FlatFileItemReader<NormalizedOrder> reader =
                new FlatFileItemReader<>();
        reader.setName("orderCsvReader");
        reader.setResource(new FileSystemResource(inputPath));
        reader.setLinesToSkip(2);
        reader.setLineMapper(lineMapper);
        reader.setStrict(true);
        reader.setSaveState(true);
        return reader;
    }
}
```

Both `v1` and `v2` yield `NormalizedOrder`. This code handles basic data types, yet **does not perform full business validation**. For example, validate `amount >= 0`, supported currency codes, and non-blank `order_id`; place those rules in a dedicated validator/processor so they can be unit-tested independently.

`reader.setSaveState(true)` allows the reader to save its position in `ExecutionContext` when managed through the `ItemStream` lifecycle. For safe restarts, the file must remain unchanged and the reader name stable across runs. If multiple readers share an `ExecutionContext`, give each a distinct `name` to avoid state key collisions.

### 7.3. Creating the Reader from `JobParameters` via `@StepScope`

Input path and schema version typically vary per job launch, so pass them via `JobParameters` and create a step-scoped reader:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
FlatFileItemReader<NormalizedOrder> orderReader(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        @Value("#{jobParameters['schemaVersion']}") String schemaVersion) {

    return OrderReaderFactory.create(inputPath, schemaVersion);
}
```

This snippet belongs inside a `@Configuration` class in a Batch-enabled application. `@StepScope` ensures `jobParameters` values resolve when the step runs, rather than when `ApplicationContext` starts up. Never instantiate a reader from an unverified `schemaVersion`: preflight must cross-check it against the actual input version.

### 7.4. Placing Preflight as a Step Preceding Ingestion

One flow organization puts `validateInputSchema` before `importOrders`. If the version is invalid, the job fails **before the writer processes the first record**.

```java
import java.nio.file.Path;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step validateInputSchemaStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        OrderSchemaPreflight preflight) {

    return new StepBuilder("validateInputSchema", repository)
            .tasklet((contribution, chunkContext) -> {
                JobParameters parameters =
                        contribution.getStepExecution().getJobParameters();

                String inputPath = parameters.getString("inputPath");
                String expectedVersion = parameters.getString("schemaVersion");

                if (inputPath == null || expectedVersion == null) {
                    throw new IllegalArgumentException(
                            "Missing inputPath or schemaVersion");
                }

                OrderSchemaPreflight.Result result =
                        preflight.inspect(Path.of(inputPath));

                if (!expectedVersion.equals(result.version())) {
                    throw new IllegalArgumentException(
                            "JobParameters schemaVersion differs from input");
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

`allowStartIfComplete(true)` is chosen **intentionally** here: when restarting a job, a previously completed validation step can re-run to confirm the version is still valid. To genuinely protect data on restart, also verify **checksum or immutable object revision**, because an unchanged header does not guarantee the rest of the file stayed identical.

To wire the flow in Spring Batch 5.x:

```java
@Bean
Job importOrdersJob(
        JobRepository repository,
        Step validateInputSchemaStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", repository)
            .start(validateInputSchemaStep)
            .next(importOrdersStep)
            .build();
}
```

Here `importOrdersStep` is a chunk-oriented step configured by the application with appropriate reader/writer. Both snippets are **illustrative configuration examples**, requiring `Job`, `JobBuilder`, `Bean` imports and matching infrastructure beans. To ensure every reader run uses the exact validated file, never derive a different path when the reader opens.

## 8. Locking Schema Version and Input Identity via `JobParameters`

Schema version also directly impacts Spring Batch **restartability**. A `JobInstance` is identified by job name and *identifying* `JobParameters`. If a job fails midway and restarts, it must know the original run's parser and data source.

Example constructing parameters at file intake/scheduler:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("inputPath", "/batch/staging/orders-2026-11-16.csv", true)
        .addString("inputRevision", "rev-00042", true)
        .addString("schemaVersion", "v2", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

`businessDate`, `inputPath`, `inputRevision`, and `schemaVersion` are **just one way to design the instance key**. In another system, an immutable `fileId` or `batchId` may serve as the primary identifying parameter, while version and checksum act as verification metadata. Choose the key according to what defines a logical unit of work, avoiding accidental creation of duplicate instances for the same data across parser versions.

For very large files, attach `sha256` or object-storage version IDs in the manifest and store a stable identifier in `JobParameters`. If putting checksums into `JobParameters`, mind column-length limits/metadata overhead and never store secrets. **A file path alone does not prove content immutability:** a file with the same name can be overwritten after a step commits partially.

### 8.1. Restarts Must Keep the Same Input Contract

```text
First run:
  JobInstance importOrdersJob / batchId=42
  schemaVersion=v2, inputRevision=rev-00042
  JobExecution #100 -> FAILED at item 80000

Restart:
  Same JobInstance / batchId=42
  schemaVersion=v2, inputRevision=rev-00042
  JobExecution #101 -> uses valid checkpoint
```

If between two runs the file is replaced with `v3` under the same filename, a reader using a `v2` checkpoint against `v3` content can corrupt or drop records. The safe policy is to **fail fast when fingerprint/revision differs**, then decide whether to launch a new ingestion batch or restore the original revision.

Never alter `schemaVersion` or add an identifying `run.id` merely to bypass `JobInstanceAlreadyCompleteException` or `JobExecutionAlreadyRunningException`. To reprocess an already completed source, define an explicit reprocessing policy with idempotency and output checks.

### 8.2. Why Checksums or Immutable Revisions Matter

An example:

```text
10:00 receive orders.csv v2, 100,000 records
10:10 job commits 60,000 records, then fails
10:15 provider overwrites orders.csv v2 with different record ordering
10:20 restart from checkpoint 60,000
```

Header and `schemaVersion` still match, yet logical position 60,001 no longer corresponds reliably to the original data. Therefore, restartable batches need **immutable input**, or must use snapshots/immutable object versions and verify revision before resuming.

A file's SHA-256 checksum is strong evidence for detecting byte changes. For huge files, recomputing checksums repeatedly costs I/O; compute on intake, store metadata from a trusted source, use locked object versions, and re-verify per policy. Do not treat every object store's ETag as a SHA-256 hash; especially with multipart uploads, ETag semantics can differ.

## 9. When Schema Doesn't Match: Fail Fast, Skip, or Quarantine?

Not all errors carry equal severity.

| Error | Example | Typical Appropriate Response |
|---|---|---|
| Unsupported version | Manifest `schemaVersion=v5`, consumer supports only v1/v2 | **Reject entire input** before running writer; report contract error. |
| Missing header or header mismatches version | Metadata says `v2`, file only has `v1` columns | Fail fast; do not auto-guess `v1` unless an official fallback policy exists. |
| Input altered between restarts | Checksum/revision mismatch | Halt and investigate; do not resume old checkpoint. |
| Single record with wrong type | `amount=ABC` in structurally valid `v2` file | Per policy: fail, bounded skip, or quarantine. |
| Single record missing required field | Blank `currency` | Usually validate/quarantine or fail once threshold exceeded. |
| New business value not yet supported | `currency=XYZ` | Reject/quarantine against allowlist; never silently substitute a default. |
| Record count mismatches manifest | Missing/duplicate data or bad manifest | Report reconciliation error; decide whether publishing is allowed. |

Spring Batch supports fault tolerance on chunk steps, e.g., `.faultTolerant().skip(...)` for classified exceptions. However, **never use skip policies to swallow whole-file schema errors**. If every record of `v3` is rejected by a `v2` parser, the job could log millions of skips, bloat logs, and finish falsely. Verify schema compatibility at the boundary before applying skip rules for individual item errors.

### 9.1. Quarantine and Auditability

Under a policy allowing bad records to be skipped, persist corresponding metadata in a store designed for rejected items:

```text
ingestion_id        : ingest-20261116-42
schema_version      : v2
source_revision     : rev-00042
record_number       : 187
error_code          : INVALID_AMOUNT
error_category      : DATA_VALIDATION
```

Do not dump full payloads containing personal data into logs. Quarantine tables/files need proper access control and retention policies. When using a listener to write quarantine rows, understand transactions and rollbacks; writing into a transaction that rolls back can lose quarantine rows. Writing outside the transaction requires idempotency to prevent duplicates on retry/restart.

### 9.2. Error-Rate Limits

Some batches allow up to N invalid records, yet that policy must apply **only after confirming the file structure matches its version**. Beyond an absolute skip limit, you may also need an error percentage or per-error-type cap—for instance, `invalidCurrencyCount > 100` must fail the job. Never let a completely wrong-schema file slip through because of `.skipLimit(Integer.MAX_VALUE)`.

## 10. Testing Schema Versioning with JUnit

### 10.1. Preflight Unit Tests

`OrderSchemaPreflight` uses core Java, so it can be tested without a Spring context or `JobRepository`. With JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OrderSchemaPreflightTest {

    @TempDir
    Path tempDir;

    private final OrderSchemaPreflight preflight = new OrderSchemaPreflight();

    @Test
    void acceptsV1Header() throws IOException {
        Path input = tempDir.resolve("orders-v1.csv");
        Files.writeString(input, """
                # schema-version: v1
                order_id,customer_id,amount
                ORD-1,CUS-1,1000
                """, StandardCharsets.UTF_8);

        OrderSchemaPreflight.Result result = preflight.inspect(input);

        assertEquals("v1", result.version());
        assertEquals(3, result.columns().size());
    }

    @Test
    void rejectsUnknownVersionBeforeProcessing() throws IOException {
        Path input = tempDir.resolve("orders-v9.csv");
        Files.writeString(input, """
                # schema-version: v9
                order_id,customer_id,amount,new_field
                ORD-1,CUS-1,1000,X
                """, StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.inspect(input));
    }

    @Test
    void rejectsHeaderMismatchEvenForKnownVersion() throws IOException {
        Path input = tempDir.resolve("bad-v2.csv");
        Files.writeString(input, """
                # schema-version: v2
                order_id,customer_id,amount
                ORD-1,CUS-1,1000
                """, StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.inspect(input));
    }
}
```

These tests verify **version and header policy**. They do not yet test every line, quote/multiline parsing, or mapping accuracy. Add reader-level tests for each supported version, covering valid records, nulls, invalid currencies, and `BigDecimal` edge cases.

### 10.2. Integration Tests with Spring Batch

An integration test should run `validateInputSchema -> importOrders` against a test database to verify:

1. Valid `v1` files run and convert to VND per contract.
2. Valid `v2` files preserve input `currency`.
3. Files with `v9` or malformed `v2` headers cause **the job to fail before the writer inserts any data**.
4. Files with valid schemas containing a badly typed row follow the skip/quarantine policy.
5. Final database state matches committed items, not merely lines read by the reader.

With Spring Batch 5.x, use `@SpringBatchTest`, `@SpringBootTest`, `@ActiveProfiles("test")`, and `JobLauncherTestUtils.launchJob(parameters)` to run the full flow. Use an isolated test datasource and prepare inputs in `@TempDir`. When passing files via `JobParameters`, pass the `@TempDir` path and use a distinct identifying key per test.

Main assertion excerpt:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputPath", inputFile.toString(), true)
        .addString("schemaVersion", "v2", true)
        .addString("batchId", "test-673-v2", true)
        .toJobParameters();

JobExecution execution = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.COMPLETED, execution.getStatus());

// Add assertions on actual output data via JDBC/Repository.
```

This is an **illustrative snippet**, assuming `inputFile`, `launcherTestUtils`, job bean, Batch `JobRepository`, test datasource, and imports are present. For unknown-version cases, assert `BatchStatus.FAILED` and verify the target table contains no new rows; avoid asserting solely on exception messages.

### 10.3. Restart Test with Unchanged Schema but Mutated File

A subtle bug occurs when a `v2` file mutates after the job commits several chunks. Recovery tests should:

```text
1. Create a v2 file with N records; capture checksum/revision.
2. Run job, trigger failure after committing several chunks.
3. Keep JobRepository and checkpoints; do not clean up metadata.
4. Alter file content while keeping the v2 header/version.
5. Attempt restart with the same identifying JobParameters.
6. Verify preflight/revision guard refuses to resume.
7. Restore original file/revision and restart; verify output has no duplicates.
```

Do not bump `schemaVersion` to v3 to create a new instance and call that a "restart": changing identifying parameters starts a new logical ingestion. True restart tests keep the same `JobInstance` and preserve metadata across runs.

## 11. When Input Is JSON, Avro, Parquet, or a Database Table

### 11.1. JSON and NDJSON

For JSON, put `schemaVersion` in an envelope or metadata manifest. A Jackson-backed batch reader can deserialize to versioned DTOs and map to the canonical model. Changes like adding fields can be tolerated if the deserializer ignores unknown properties; however, **ignoring unknown fields does not solve semantic changes**.

For NDJSON, each line is usually one JSON object. Specify whether version applies per file or per record in the manifest. Mixing multiple versions in one file should only be supported when explicitly permitted by contract; the parser must then dispatch the right mapper per record and track error counts by version.

### 11.2. Avro, Protobuf, and Schema Registries

Schema-driven formats explicitly define field numbers/names, types, defaults, and resolution rules. With a schema registry, combine registry compatibility checks with real consumer integration tests. Compatibility rules vary by format and policy (BACKWARD, FORWARD, FULL, transitive, etc.), so never infer safety from policy names alone and skip testing.

### 11.3. Parquet

Parquet embeds schema in file metadata. Pipelines can inspect the schema footer to validate columns and types before scanning full data. Still, business version contracts may include rules **that cannot be expressed in Parquet physical schemas alone**, such as currency units or business timezones; keep an explicit contract/version anyway.

### 11.4. Staging Databases

When input resides in a staging table, store `schema_version`, `source_revision`, and `ingestion_id` in a manifest/batch table. Avoid altering staging schemas in place while a job is reading. Use versioned migrations or views/adapters, and bind each ingestion batch to a snapshot stable enough for restarts.

## 12. Designing Observability and Reconciliation for Schema Versions

A large data pipeline should record per-batch ingestion audit/metadata records:

| Field | Purpose |
|---|---|
| `ingestionId` | Technical key for the ingestion run. |
| `dataset` | Data category: `orders`, `customers`, etc. |
| `schemaVersion` | Verified version, not merely what the sender claimed. |
| `inputRevision`/checksum | Identifier of processed physical content. |
| `jobInstanceId`, `jobExecutionId` | Correlation with Spring Batch metadata. |
| `receivedCount`, `validCount`, `rejectedCount`, `writtenCount` | Count reconciliation per business definitions. |
| `status`, `errorCode` | Intake and validation outcome. |
| `receivedAt`, `finishedAt` | Receipt and completion timestamps. |

Batch logs should use consistent event names:

```text
batch.input.schema.accepted dataset=orders schemaVersion=v2 ingestionId=ing-42
batch.input.schema.rejected dataset=orders schemaVersion=v9 reason=UNSUPPORTED_VERSION ingestionId=ing-43
batch.input.completed dataset=orders schemaVersion=v2 accepted=9990 rejected=10
```

These are illustrative logs; **never print full files, payloads, or `JobParameters`** as they may contain sensitive data and cause unbounded log growth. For metrics, group by dataset and a **bounded set of managed versions**; never add per-run IDs as metric tags due to high cardinality. Execution IDs belong in logs/traces.

To verify data completeness, compare manifest record counts (when trustworthy) against actual records and committed results. `StepExecution.getReadCount()`/`getWriteCount()` follow chunk-processing semantics; they do not always equal file lines or SQL rows modified. Account for filters, skips, retries, rollbacks, and writer semantics.

## 13. Changing Schemas Safely Between Two Systems

A contract-change process should follow these steps:

1. **Publish the new version:** specify exact changed fields, types, defaults, timezones, enums, and business meanings.
2. **Classify breaking vs. non-breaking:** base this on actual readers, not merely field-name diffs.
3. **Implement canonical model mappings:** v1/v2 parsers both output a well-defined normalized model.
4. **Add contract tests:** keep representative fixtures of old and new versions; test missing/unknown fields, invalid values, and reordered headers.
5. **Deploy consumers supporting the new version before producers emit new data** when the rollout requires backward compatibility.
6. **Allow a transition window:** log/metric input counts per version and schedule retirement of the old version.
7. **Pin input revisions on intake:** protect restarts, reconciliation, and reproducibility.
8. **Decommission old versions cleanly:** once confirmed producers no longer send old files and backfill paths are handled.

With multiple producers, use a schema registry or versioned contract artifacts rather than sharing an Excel sheet with no automated checks. Producers are responsible for declaring versions honestly, while consumers must still validate received files.

### 13.1. Do Not Couple Application Deployment Version to Input Version

For example, `order-batch-app 2.3.1` can read both `input schema v1` and `v2`. Bumping an application patch version does not mean the input schema changed, and the same input schema can be supported across multiple application releases. Manage both independently:

```text
Application release: 2.3.1
Supported input schemas: orders/v1, orders/v2
Canonical model version: OrderNormalized/1
Database migration: V12
```

Link them only via an explicit compatibility matrix in release notes/contract tests. This is especially important when backfilling old inputs using a newer application release months later.

## 14. Common Mistakes When Managing Input Schema Versions

| Symptom | Cause | Fix |
|---|---|---|
| v2 file rejected by v1 reader | Strict reader expects old column count/fields | Detect version first and select matching parser. |
| Job succeeds yet amounts are wrong | Field unit or meaning changed without contract change | Version semantics too; add conversion tests. |
| Unknown version still ingested | Default parser or `default` branch swallows error | Fail fast on unsupported versions. |
| Header says v2 yet content is v1 | Producer/manifest mismatch or mislabeled file | Cross-check header/manifest and validate actual types. |
| Restart reads shifted items | File overwritten after checkpoint | Use immutable input revisions/checksums and fail on change. |
| CSV misparsed when values contain commas | Using `String.split(",")` instead of quote/escape-aware parser | Use contract-compliant CSV tokenizer/parser. |
| Readers overwrite each other's checkpoints | Two readers share the same `name` in one execution context | Give each `ItemStream` a unique, stable name. |
| Errors near end of file missed | Checking only the first two lines and assuming whole file valid | Separate schema preflight from per-record validation and final reconciliation. |
| Wrong-schema file triggers millions of skips | Version error misclassified as item-level error | Reject entire file before processing; avoid unlimited skips. |
| Valid version yet new enum crashes job | Business enum not upgraded | Version allowed value sets/unknown policy and add contract tests. |
| Logs filled with payloads on bad data | Listener logs raw items/JSON/params | Log only error code, record number, and ingestion ID; use secure quarantine. |
| App upgrade breaks old backfills | Removed v1 reader or altered semantics breaking compatibility | Keep legacy adapters/fixtures during support window or migrate inputs. |
| Same object key holds different data | Producer overwrote file; object metadata unpinned | Store real object version/digest and lock source for job lifetime. |
| H2 tests pass yet production fails | Different SQL types/dialects or parser/locale | Test against real DB/formats and pin locale/timezone. |

## 15. Practice Exercises

### Exercise 1 — Supporting v1 and v2 Simultaneously

Create two CSV files following the examples in section 1. Write `OrderSchemaPreflight.inspect(...)`, create corresponding `FlatFileItemReader<NormalizedOrder>` instances, and verify both inputs map accurately. Verify `v1` uses `VND` **strictly because the v1 contract specifies it**, while `v2` reads currency from the file.

### Exercise 2 — Rejecting Unknown Versions Before Database Writes

Create a file with `# schema-version: v9` and run `validateInputSchema -> importOrders` using `@SpringBatchTest`. Verify the job fails, the import step writes zero rows, and error metadata carries an auditable error code. Also test a `v2` header missing the `currency` column.

### Exercise 3 — Bad Data Inside a Schema-Valid File

Using `v2`, add a record with `amount=ABC` or an invalid `currency`. Separate parse errors from business errors and design skip/quarantine thresholds. Ensure output contains no invalid records and `accepted + rejected` matches actual input record count.

### Exercise 4 — File Mutating Between Restarts

Run a `v2` job with `ExecutionContext` checkpoints after a few chunks, trigger a failure, reorder records in the same file path, and attempt a restart. Add checksum or immutable revision verification to detect the change and halt before resuming. Restore the exact revision and verify final output has no duplicates.

### Exercise 5 — Designing v3 Without Breaking Business Rules

Design `v3` with `net_amount`, `tax_amount`, and `currency`. Write the mapping to `NormalizedOrder` with explicit business assumptions for tax and total amount; add tests for nulls, precision, rounding, and unknown currencies. Evaluate whether `v3` is backward/forward compatible with current consumers, and propose a producer/consumer rollout plan.

## 16. Practical Principles for Real Batch Systems

A well-governed input schema pipeline typically satisfies:

1. **Versions are explicitly declared** in file headers, manifests, object metadata, or registries.
2. **Every version has a defined contract** for structure and semantics, guarded by fixtures and tests.
3. **Consumers accept only supported versions**, rejecting unknown or mismatched inputs before data processing.
4. **All versions normalize at the input boundary** before entering shared processing logic.
5. **Input and version are pinned per `JobInstance`**, especially for restarts and backfills.
6. **Contract errors are separated from per-record errors**, with clear fail, skip, or quarantine policies.
7. **Output is reconciled** by counts, business keys, and committed state rather than relying on a single `COMPLETED` log.
8. **Old versions are retired by plan**, with monitoring for stale producers and compatibility testing.
9. **Input schema, database schema, and application version are tracked independently**, avoiding confusion during operations and upgrades.

## 17. References

- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): `FlatFileItemReader`, `LineMapper`, tokenizers, strict parsing, and reader configuration.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpointing with `ExecutionContext`, `open/update/close`, and restartability.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): restart behavior and step state handling.
- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/job/running.html): passing parameters and identifying a job instance.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): distinguishing item errors from input contract violations.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): writer/reader schemas and schema resolution rules for Avro data.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): compatible message schema evolution rules in Protobuf.

