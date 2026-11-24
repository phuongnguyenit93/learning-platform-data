# Data Quality Reporting in Spring Batch

## 1. Objectives and Context

A Spring Batch job can finish with status `COMPLETED` while its output data still fails to meet business requirements. For example, a job importing 100,000 customers succeeds technically, yet 8% of records lack an email, 2% duplicate customer IDs, or 500 records have invalid birth dates. Looking only at `BatchStatus` and `writeCount`, operations cannot tell whether data is good enough to pass downstream.

A **data quality report** is the set of metrics, evaluated rules, evidence, and conclusions about data quality processed during a batch period. The report answers:

- How many records did the job receive, and how many were accepted, rejected, or flagged for review?
- Are records missing required fields, malformed, out of range, or duplicating keys?
- Which quality rules were applied, and at what version?
- Which source file, business date, and `JobExecution` do these numbers belong to?
- Did quality pass the threshold to publish data, or must downstream steps be blocked?
- After a job restarts, did the report avoid double-counting errors or losing record trails?

This lesson belongs to **Data quality** in **Spring Batch Core Processing**. You will build quality measurement along the Reader → Processor → Writer pipeline, store traceable results, aggregate reports, and use quality gates to control batch flow.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC, and PostgreSQL. Code snippets are separated by responsibility so they can be adapted to projects with custom configurations.

## 2. Distinguishing Technical Success from Business Quality

Spring Batch tracks execution status via `JobExecution` and `StepExecution`. However:

- `COMPLETED` means the job finished according to configured flow and rules; it does not implicitly mean "clean data."
- `FAILED` can happen due to infrastructure, exceptions, or a failed quality gate.
- `filterCount` increments when a processor returns `null`, without explaining why a record was dropped.
- `skipCount` records errors skipped under a fault-tolerant policy, not a full count of all business violations.
- `writeCount` counts items processed by the step's writer, not necessarily high-quality records published at the final target.

Examples:

| Scenario | Technical Result | Quality Result |
| --- | --- | --- |
| 10,000 records, all valid | `COMPLETED` | Pass |
| 10,000 records, 3,000 missing email but routed to quarantine | `COMPLETED` for ingestion step | May fail publish threshold |
| 10,000 records, writer hits connection error | `FAILED` | Final report may be incomplete |
| Completely empty file | May be `COMPLETED` | Pass or fail depending on empty-source policy |
| File ingests cleanly yet duplicates exceed limit | Ingestion step `COMPLETED` | Quality gate must block forwarding to target |

Therefore reports must include **two status groups**: Spring Batch execution status and data quality status, such as `PASS`, `WARN`, `FAIL`, or `NO_DATA`.

## 3. Quality Dimensions to Measure

Choose metrics based on business needs and source characteristics. A common set includes:

| Quality Dimension | Question | Example Rule |
| --- | --- | --- |
| **Completeness** | Do required fields have values? | `customerId`, `email` must not be blank |
| **Validity** | Do values match allowed type, format, and domain? | `age` is an integer from 18 to 120 |
| **Uniqueness** | Are there duplicate business keys? | No two customers share `customerId` after normalization |
| **Consistency** | Do fields or sources contradict each other? | `startDate <= endDate`; country code matches region |
| **Accuracy** | Do values match reality or trusted reference sources? | Customer ID exists in master data |
| **Timeliness** | Does data belong to the processing period and arrive on time? | Events are no later than 24 hours |
| **Integrity** | Are relationships and foreign keys valid? | Store code exists in the catalog table |
| **Conformity** | Does the file/schema match the contract? | Exact column count, header, encoding, and data types |

Not every job needs all dimensions. For CSV customer imports, **completeness, validity, and uniqueness** form a useful minimum. For financial reconciliation jobs, consistency and monetary control totals matter more than isolated format checks.

### Rules Must Be Specific and Versioned

"Valid email" is too vague. Define instead:

```text
Rule ID: EMAIL_FORMAT
Version: v2
Field: email
Condition: Non-blank and matches application-accepted email rule
Severity: ERROR
Action: REJECT_RECORD
```

An email address may be valid under a broad standard yet fail an application's simple regex. Say "valid under EMAIL_FORMAT v2," rather than claiming an illustrative regex covers the full email spec.

When rules change, record `ruleSetVersion` in the report to explain why two runs on the same data produced different outcomes.

## 4. Defining Metrics and Denominators

Metrics must use an **explicit denominator**. For an ingestion period:

- `receivedRows`: logical records actually received from the source per source definition.
- `evaluatedRows`: records evaluated and persisted with classification outcomes.
- `acceptedRows`: records satisfying mandatory rules.
- `rejectedRows`: records rejected.
- `quarantinedRows`: records held for manual inspection, if policy separates this bucket.
- `duplicateRows`: records not selected due to key duplication per defined rules.
- `missingEmailRows`: records missing a required email.

Example formulas:

```text
acceptanceRate = acceptedRows / evaluatedRows × 100%
rejectionRate  = rejectedRows / evaluatedRows × 100%
emailMissingRate = missingEmailRows / evaluatedRows × 100%

If evaluatedRows = 0:
    do not divide,
    report NO_DATA or apply empty-source policy.
```

Suppose 1,000 records are evaluated, 900 accepted, and 100 rejected; among those 100 records, 60 lack email and 50 have invalid age, with 10 breaking both rules.

```text
evaluatedRows      = 1,000
acceptedRows       = 900
rejectedRows       = 100
missingEmailRows   = 60
invalidAgeRows     = 50
totalViolationRows = 110 if counting per (record, rule)
```

**Total violations can exceed rejected records**, because one record can break multiple rules. Reports must distinguish "bad records" from "rule violations."

### Be Careful When Deriving Counts from StepExecution

`StepExecution.getReadCount()`, `getReadSkipCount()`, `getFilterCount()`, and `getWriteCount()` are useful for processing diagnostics. Never assume:

```text
sourceRows = readCount + readSkipCount
acceptedRows = writeCount
rejectedRows = filterCount + skipCount
```

holds for every job. Readers can skip headers, blank lines, or multiline records; processors can filter records for other reasons; writers can write both valid and invalid rows to staging. Retries, rollbacks, and restarts also alter interpretation. For quality reporting, **persist evaluation outcomes by business key or source row key** and aggregate from committed data.

## 5. Recommended Architecture: Evaluate, Store Evidence, Aggregate, Quality Gate

A design well-suited to Spring Batch:

```text
                CSV File / Database / API
                            |
                            v
                      ItemReader
                            |
                            v
                     Validation
                    ItemProcessor
                            |
                   QualityDecision
                    /            \
              ACCEPTED          REJECTED
                    \            /
                     v          v
                  Staging Writer
               (one row/source row,
                error codes, rule version)
                            |
                            v
                        COMMIT
                            |
                            v
                 Finalize Quality Step
                - detect duplicates
                - aggregate report
                - evaluate quality gate
                            |
                +-----------+-----------+
                |                       |
               PASS                    FAIL
                |                       |
                v                       v
          Publish to target        Block publish,
          / downstream             save report and alert
```

This design has several benefits:

1. Every record is **explicitly evaluated**; never use `processor.return null` for all errors and lose reasons.
2. Outcomes persist to staging inside the same chunk transaction.
3. Reports aggregate from committed rows, avoiding inconsistent in-memory counters across rollbacks/restarts.
4. File-wide rules like duplicate detection can evaluate after all data is loaded.
5. The quality gate decides whether the publish step runs.

Not every project needs a multi-step pipeline. Small batches can combine steps sensibly, while preserving the principle of **measuring quality from durable, reconcilable results**.

## 6. Distinguishing Expected Data Errors from Technical Exceptions

An important decision is which errors count as **quality check outcomes** versus which must fail the step or trigger fault tolerance.

| Error Type | Typical Handling | How Recorded |
| --- | --- | --- |
| Missing email, invalid age, invalid ID format | Produce `REJECTED` and list of violated rules | Staging / quality issue table |
| Duplicate customer ID in a batch | Evaluate uniqueness; flag duplicate rows | Staging table + `DUPLICATE_ID` issue |
| Unparseable per schema yet record remains identifiable | Quarantine with `MALFORMED_RECORD` | Safe source reference and record position |
| Missing file, DB disconnect, unavailable target table | Fail or retry per exception type | `JobExecution`/`StepExecution` and technical logs |
| Parser cannot identify record boundaries | Fail fast or use fault-tolerant reader/line mapper | Source error and `readSkipCount` if skipped |
| Out of staging storage space | Fail step | Do not claim full evaluation |

If `ItemProcessor` returns `null` to filter, Spring Batch increments `filterCount` without passing the record to the writer. To report **exact rejection reasons per record**, have the processor return a stateful result or use a transactionally consistent error store.

**SkipListener** helps when exceptions are skipped, yet does not replace a full quality report. Reader errors can occur before item creation; handle source position and read errors explicitly. Never add retry counts to violation counts: an item may be retried multiple times before succeeding.

## 7. Data Model for Records and Reports

Suppose a customer import job reads a CSV with three columns:

```csv
customer_id,email,age
C001,alice@example.com,28
C002,,22
C003,bob@example.com,17
C001,other@example.com,31
C004,cara@example.com,45
```

Sample rules:

- `CUSTOMER_ID_REQUIRED`: customer ID must not be blank.
- `EMAIL_REQUIRED`: email must not be blank.
- `EMAIL_FORMAT`: email must match the application's email rule.
- `AGE_RANGE`: age is an integer from 18 to 120.
- `DUPLICATE_ID`: normalized ID must not appear more than once among valid records in the same batch.

One record can have multiple error codes. Never combine them into hard-to-aggregate prose; use **stable rule codes**.

### Staging Table and Report Table

PostgreSQL DDL example:

```sql
CREATE TABLE customer_import_row (
    batch_key       VARCHAR(120) NOT NULL,
    source_line     BIGINT NOT NULL,
    customer_id     VARCHAR(100),
    email           VARCHAR(320),
    age             INTEGER,
    status          VARCHAR(20) NOT NULL,
    issue_codes     TEXT NOT NULL DEFAULT '',
    rule_version    VARCHAR(30) NOT NULL,
    PRIMARY KEY (batch_key, source_line)
);

CREATE INDEX idx_customer_import_row_status
    ON customer_import_row (batch_key, status);

CREATE INDEX idx_customer_import_row_customer
    ON customer_import_row (batch_key, customer_id);

CREATE TABLE customer_quality_report (
    batch_key       VARCHAR(120) PRIMARY KEY,
    rule_version    VARCHAR(30) NOT NULL,
    evaluated_rows  BIGINT NOT NULL,
    accepted_rows   BIGINT NOT NULL,
    rejected_rows   BIGINT NOT NULL,
    duplicate_rows  BIGINT NOT NULL,
    quality_status  VARCHAR(20) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Here `status` takes `VALID` or `REJECTED`. In real models, you can add `QUARANTINED`, `WARNING`, or store quality issues in a `customer_quality_issue(batch_key, source_line, rule_code, severity)` table.

Storing one row per `(record, rule)` pair is usually better for deep analytics because one record can break multiple rules. The `|`-delimited `issue_codes` field is just a compact choice for this example; it is suboptimal for large-scale search, analytics, and rule versioning.

**Primary key `(batch_key, source_line)` enables idempotency:** rewriting the same source row after rollback/restart updates that exact staging row without creating duplicates. `source_line` must remain stable for the corresponding source file version.

## 8. ItemReader Preserving Source Position to Explain Errors

If you read only raw strings and discard line positions, answering "which record was rejected?" becomes hard. Have the reader return raw content paired with line number.

```java
public record SourceRow(
        long lineNumber,
        String rawLine) {
}
```

Configuring `FlatFileItemReader`:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<SourceRow> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<SourceRow>()
        .name("customerQualityReader")
        .resource(new FileSystemResource(inputFile))
        .linesToSkip(1)
        .lineMapper((line, lineNumber) ->
            new SourceRow(lineNumber, line))
        .saveState(true)
        .strict(true)
        .build();
}
```

In this example, `linesToSkip(1)` skips the header; `lineNumber` is the position supplied by the line mapper. If the source has multiline CSV records, special encodings, or complex record boundaries, verify what position means in your reader/record separator. Do not assume one physical line always equals one logical record across all CSV formats.

`saveState(true)` and a stable reader name let Spring Batch checkpoint positions for restarts. Also keep source content unchanged between executions of the same `JobInstance` via file snapshots, checksums, or source versions.

## 9. ItemProcessor Evaluating Rules and Returning Quality Decisions

Expected business errors should not always turn into exceptions that fail the job. Instead, the processor can return an explicit decision:

```java
public record QualityDecision(
        long sourceLine,
        String customerId,
        String email,
        Integer age,
        String status,
        String issueCodes) {
}
```

Example processor using `DelimitedLineTokenizer` to parse three CSV columns under Spring Batch tokenization rules:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.batch.item.file.transform.FieldSet;
import org.springframework.stereotype.Component;

@Component
public class CustomerQualityProcessor
        implements ItemProcessor<SourceRow, QualityDecision> {

    private static final Pattern EMAIL_PATTERN =
        Pattern.compile("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$");

    private final DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    public CustomerQualityProcessor() {
        tokenizer.setNames("customer_id", "email", "age");
        tokenizer.setStrict(true);
    }

    @Override
    public QualityDecision process(SourceRow row) {
        List<String> issues = new ArrayList<>();

        String customerId = null;
        String email = null;
        Integer age = null;

        try {
            FieldSet fields = tokenizer.tokenize(row.rawLine());

            customerId =
                fields.readString("customer_id").trim()
                    .toUpperCase(Locale.ROOT);

            email = fields.readString("email").trim();

            String ageText = fields.readString("age").trim();

            if (customerId.isEmpty()) {
                issues.add("CUSTOMER_ID_REQUIRED");
            }
            if (email.isEmpty()) {
                issues.add("EMAIL_REQUIRED");
            } else if (!EMAIL_PATTERN.matcher(email).matches()) {
                issues.add("EMAIL_FORMAT");
            }

            try {
                age = Integer.valueOf(ageText);
                if (age < 18 || age > 120) {
                    issues.add("AGE_RANGE");
                }
            } catch (NumberFormatException ex) {
                issues.add("AGE_RANGE");
            }

        } catch (RuntimeException ex) {
            // Example: wrong column count or unreadable syntax.
            // Only turn expected parse errors into data outcomes,
            // never swallow infrastructure exceptions or programming bugs.
            issues.add("MALFORMED_RECORD");
        }

        String status = issues.isEmpty() ? "VALID" : "REJECTED";

        return new QualityDecision(
            row.lineNumber(),
            customerId,
            email,
            age,
            status,
            String.join("|", issues)
        );
    }
}
```

Key takeaways:

- `process()` **does not return `null`** for invalid records; the writer receives both valid and rejected items to persist outcomes.
- Each rule has a stable code. Reports can count by code independent of prose wording.
- Normalize `customerId` before uniqueness checks so `c001` and `C001` are treated consistently.
- The email regex is only a demo rule; in production, use a validator matching the business contract and test Unicode, quoted values, and edge-case domains.
- Column-count exceptions convert to `MALFORMED_RECORD` in this example; in real systems, catch **exact expected parse exceptions** rather than catching every `RuntimeException` and hiding bugs.
- If data contains PII, enforce security policies on staging tables. Never write raw `rawLine` into logs or error tables without proper justification and access controls.

In complex designs, split `QualityRule` into separate components returning `List<Violation(ruleCode, severity, fieldName)>`. The processor simply orchestrates rules; the report aggregator never depends on error message prose.

## 10. ItemWriter Persisting Reconcilable and Restartable Results

The writer below persists both valid and rejected rows into staging, using PostgreSQL `ON CONFLICT` so rewriting the same source row never creates duplicates.

```java
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
ItemWriter<QualityDecision> customerStagingWriter(
        JdbcTemplate jdbc,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return chunk -> {
        List<? extends QualityDecision> rows = chunk.getItems();

        jdbc.batchUpdate(
            """
            INSERT INTO customer_import_row
                (batch_key, source_line, customer_id, email,
                 age, status, issue_codes, rule_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'v1')
            ON CONFLICT (batch_key, source_line)
            DO UPDATE SET
                customer_id = EXCLUDED.customer_id,
                email = EXCLUDED.email,
                age = EXCLUDED.age,
                status = EXCLUDED.status,
                issue_codes = EXCLUDED.issue_codes,
                rule_version = EXCLUDED.rule_version
            """,
            new BatchPreparedStatementSetter() {
                @Override
                public int getBatchSize() {
                    return rows.size();
                }

                @Override
                public void setValues(
                        PreparedStatement ps,
                        int i) throws SQLException {

                    QualityDecision d = rows.get(i);

                    ps.setString(1, batchKey);
                    ps.setLong(2, d.sourceLine());
                    ps.setString(3, d.customerId());
                    ps.setString(4, d.email());

                    if (d.age() == null) {
                        ps.setNull(5, java.sql.Types.INTEGER);
                    } else {
                        ps.setInt(5, d.age());
                    }

                    ps.setString(6, d.status());
                    ps.setString(7, d.issueCodes());
                }
            }
        );
    };
}
```

The writer must share the same transaction manager and staging datasource so every chunk commits/rolls back consistently. When spanning multiple datasources or calling APIs outside the transaction, never assume quality writes and business writes are atomic.

`ON CONFLICT` supports idempotency **within a batch key and source position**. It does not solve the case where a file's content changes while keeping the same batch key; that is why you must version sources and verify checksums on restart.

In production, if full history of every state change is needed, add an append-only event table or detailed issue table. This example uses upsert to illustrate durable writes across chunks/restarts.

## 11. Finding Batch-Wide Duplicates

A per-item processor does not necessarily have enough context to decide whether an item is duplicated **across the whole file**. Using a `HashSet` in a singleton processor to remember all IDs often falls short: heap grows with record count, restarts are hard, and parallel steps break.

An alternative is checking staging after reading the whole source. Demo rule: among records **passing initial validation rules**, keep the first by `source_line`, and flag subsequent valid records sharing the same `customer_id` with `DUPLICATE_ID`.

PostgreSQL:

```sql
WITH ranked AS (
    SELECT
        batch_key,
        source_line,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY source_line
        ) AS position_in_group
    FROM customer_import_row
    WHERE batch_key = :batchKey
      AND status = 'VALID'
      AND customer_id IS NOT NULL
)
UPDATE customer_import_row AS r
SET status = 'REJECTED',
    issue_codes = CASE
        WHEN r.issue_codes = '' THEN 'DUPLICATE_ID'
        ELSE r.issue_codes || '|DUPLICATE_ID'
    END
FROM ranked AS x
WHERE r.batch_key = x.batch_key
  AND r.source_line = x.source_line
  AND x.position_in_group > 1;
```

This choice compares only records that passed initial rules. If business rules require **flagging duplicate IDs regardless of other errors**, adjust the candidate filter and support multiple violations per record; do not assume this query covers every uniqueness rule.

An important detail: if finalization reruns after duplicates were already marked `REJECTED`, those rows are excluded from the CTE by `status='VALID'`, so the query does not append `DUPLICATE_ID` twice. If you must recompute the whole report from scratch after changing rules, re-evaluate staging or use a separate issue table with transient state.

## 12. Aggregating Reports from Committed Data

After processing and flagging duplicates, aggregate via SQL instead of keeping in-memory counters:

```sql
SELECT
    COUNT(*) AS evaluated_rows,
    COUNT(*) FILTER (WHERE status = 'VALID') AS accepted_rows,
    COUNT(*) FILTER (WHERE status = 'REJECTED') AS rejected_rows,
    COUNT(*) FILTER (
        WHERE issue_codes LIKE '%DUPLICATE_ID%'
    ) AS duplicate_rows
FROM customer_import_row
WHERE batch_key = :batchKey;
```

With controlled, non-overlapping rule codes, substring matching suffices for an example. For large quality datasets, use a `quality_issue` table with one row per violation instead of relying on `LIKE`.

To display rates in reports:

```sql
SELECT
    batch_key,
    evaluated_rows,
    accepted_rows,
    rejected_rows,
    CASE
        WHEN evaluated_rows = 0 THEN NULL
        ELSE ROUND(
            accepted_rows * 100.0 / evaluated_rows,
            2
        )
    END AS acceptance_pct,
    quality_status
FROM customer_quality_report;
```

When the denominator is 0, `NULL` indicates "no meaningful percentage," distinct from a 0% rate on a dataset that had records yet zero valid ones.

### Example Report

With the CSV from earlier, assuming rules flag the second `C001` as a duplicate:

| Metric | Value |
| --- | ---: |
| Evaluated rows | 5 |
| Accepted rows | 2 |
| Rejected rows | 3 |
| Missing email | 1 |
| Invalid age | 1 |
| Duplicate customer ID | 1 |
| Acceptance rate | 40% |
| Quality gate | `FAIL` if minimum required is 98% |

Row `C002` lacks email; `C003` has age 17; the second `C001` is flagged duplicate. The first `C001` and `C004` are accepted. This illustrates a fixed rule set, not a mandatory threshold across all systems.

## 13. Generating Reports and Quality Gates in a Dedicated Step

Let the ingestion step **finish and commit staging** first, so a separate aggregation step can run in its own transaction. This preserves the report even when the quality gate fails and blocks publishing.

### Example Aggregation Tasklet

The code below uses PostgreSQL and saves the report with policy: empty source ⇒ `NO_DATA`; acceptance rate < 98% ⇒ `FAIL`; otherwise ⇒ `PASS`.

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
Tasklet summarizeQuality(
        JdbcTemplate jdbc,
        @Value("#{jobParameters['batchKey']}") String batchKey) {

    return (contribution, chunkContext) -> {
        jdbc.update(
            """
            INSERT INTO customer_quality_report (
                batch_key, rule_version, evaluated_rows,
                accepted_rows, rejected_rows, duplicate_rows,
                quality_status, generated_at
            )
            SELECT
                ?, 'v1',
                COUNT(*),
                COUNT(*) FILTER (WHERE status = 'VALID'),
                COUNT(*) FILTER (WHERE status = 'REJECTED'),
                COUNT(*) FILTER (
                    WHERE issue_codes LIKE '%DUPLICATE_ID%'
                ),
                CASE
                    WHEN COUNT(*) = 0 THEN 'NO_DATA'
                    WHEN COUNT(*) FILTER (WHERE status = 'VALID')
                         * 100.0 / COUNT(*) < 98.0 THEN 'FAIL'
                    ELSE 'PASS'
                END,
                CURRENT_TIMESTAMP
            FROM customer_import_row
            WHERE batch_key = ?
            ON CONFLICT (batch_key)
            DO UPDATE SET
                rule_version = EXCLUDED.rule_version,
                evaluated_rows = EXCLUDED.evaluated_rows,
                accepted_rows = EXCLUDED.accepted_rows,
                rejected_rows = EXCLUDED.rejected_rows,
                duplicate_rows = EXCLUDED.duplicate_rows,
                quality_status = EXCLUDED.quality_status,
                generated_at = EXCLUDED.generated_at
            """,
            batchKey, batchKey
        );

        return RepeatStatus.FINISHED;
    };
}
```

This is the aggregation step, assuming duplicate flagging already ran. To combine both operations into one step, place both the duplicate SQL and summary SQL inside one tasklet transaction so a successful execution always leaves a consistent state.

### The Quality Gate Should Control the Publish Step

One option is letting the quality report step finish cleanly even when business status is `FAIL`, then setting a custom `ExitStatus` and routing the flow so **the publish step does not run**.

Illustrative listener:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.jdbc.core.JdbcTemplate;

public class QualityGateListener implements StepExecutionListener {

    private final JdbcTemplate jdbc;
    private final String batchKey;

    public QualityGateListener(
            JdbcTemplate jdbc,
            String batchKey) {
        this.jdbc = jdbc;
        this.batchKey = batchKey;
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        String status = jdbc.queryForObject(
            """
            SELECT quality_status
            FROM customer_quality_report
            WHERE batch_key = ?
            """,
            String.class,
            batchKey
        );

        return switch (status) {
            case "PASS" -> new ExitStatus("QUALITY_PASS");
            case "NO_DATA" -> new ExitStatus("QUALITY_NO_DATA");
            default -> new ExitStatus("QUALITY_FAIL");
        };
    }
}
```

Job flow configuration can map `QUALITY_PASS` to the publish step, and `QUALITY_FAIL`/`QUALITY_NO_DATA` to termination or alerting branches. **A custom `ExitStatus` does not automatically turn `BatchStatus` into `FAILED`.** If business policy requires the job to fail technically on bad quality, configure explicit fail transitions rather than changing exit codes and assuming monitoring sees `FAILED`.

For projects with multiple report types, put quality gate thresholds into versioned rule configs instead of hardcoding 98% across every job.

## 14. Configuring Jobs and Steps in Spring Batch

A three-step structure for the example:

1. `importCustomerStep`: read lines, evaluate rules, write to staging.
2. `qualityFinalizeStep`: flag duplicates and aggregate the report.
3. `publishCustomerStep`: runs only when the quality gate passes.

Ingest step example:

```java
@Bean
Step importCustomerStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        @Qualifier("customerReader") ItemReader<SourceRow> reader,
        CustomerQualityProcessor processor,
        @Qualifier("customerStagingWriter")
            ItemWriter<QualityDecision> writer) {

    return new StepBuilder("importCustomerStep", repository)
        .<SourceRow, QualityDecision>chunk(200, tx)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

The aggregation step can use a tasklet and transaction manager:

```java
@Bean
Step qualityFinalizeStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        @Qualifier("qualityFinalizeTasklet") Tasklet tasklet) {

    return new StepBuilder("qualityFinalizeStep", repository)
        .tasklet(tasklet, tx)
        .build();
}
```

`qualityFinalizeTasklet` is an application component running two operations: executing the duplicate-detection query and then updating `customer_quality_report`. The snippets above provide the SQL logic; a complete configuration wires them together and attaches the quality-gate listener.

Job flow can be visualized as:

```text
importCustomerStep
      |
      v
qualityFinalizeStep
      |
      +-- QUALITY_PASS --> publishCustomerStep --> END
      |
      +-- QUALITY_FAIL ------------------------> STOP/FAIL per policy
      |
      +-- QUALITY_NO_DATA ---------------------> END/FAIL per policy
```

Do not publish straight from the ingest writer. If you write directly to target tables first and only later discover the source failed the quality gate, blocking publishing afterward is very hard. Staging separates **data intake** from **publishing validated data**.

## 15. Quality Thresholds and Severity Levels

A quality gate rarely relies on a single pass rate. Example:

| Rule | Severity | Threshold | Policy |
| --- | --- | --- | --- |
| Valid source header/schema | `CRITICAL` | Mandatory 100% | Fail ingest before evaluating |
| Non-blank `customer_id` | `ERROR` | 100% | Reject record or fail job per business |
| Non-blank `email` | `ERROR` | Max missing rate 1% | Gate fails if exceeded |
| Valid age | `ERROR` | Max error rate 0.5% | Gate fails if exceeded |
| Duplicate customer ID | `ERROR` | 0 duplicates | Gate fails if any duplicate |
| Inconsistent customer ID casing | `WARNING` | Per threshold | Normalize and warn |
| Abnormal drop in total records | `WARNING`/`CRITICAL` | e.g., drop > 30% vs. baseline | Investigate missing data |

Thresholds like 0.5%, 1%, or 98% are illustrative. In financial pipelines, a single duplicate may block everything. In marketing feeds, a rate of missing optional attributes may be acceptable.

A weighted composite **quality score** can aid dashboards, yet never let a high overall score mask a critical error. For example, a 99/100 score must still fail if broken foreign keys affect settlement. Check mandatory rules separately before considering composite scores.

## 16. Data Quality on Job Restarts or Reruns

Spring Batch uses `JobRepository` and `ExecutionContext` to manage restarts. In quality reporting, distinguish:

- A **JobInstance**: identifies the processing period, e.g., `batchKey=crm-2026-11-15-v1`.
- A **JobExecution**: one run attempt of that instance.
- A **source row**: physical or logical record of the source snapshot.
- A **violation**: outcome of one rule on one source row.

Do not increment a singleton counter in `ItemProcessor`:

```java
private long invalidRows;

public QualityDecision process(SourceRow row) {
    if (invalid(row)) {
        invalidRows++;
    }
    // ...
}
```

Such counters do not roll back when chunks fail, double-increment on retries, and suffer race conditions under multithreading. If the bean outlives a single `JobExecution`, values leak across runs.

Instead:

1. Give every source row a stable key `(batchKey, sourceLine)`.
2. Have the writer upsert evaluation results inside the chunk transaction.
3. Have the aggregation step recompute from committed staging.
4. Upsert reports by `batchKey` rather than accumulating across runs.
5. Keep source snapshot, mapping, and `ruleSetVersion` consistent across restarts.
6. For reprocessing with changed source/rules, create a new data version or dedicated workflow rather than pretending to restart the same snapshot.

### Choosing Identifying JobParameters

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("batchKey", "crm-2026-11-15-v1", true)
    .addString("ruleSetVersion", "v1", true)
    .addString("inputFile", "/data/snapshots/customers-20261115.csv", false)
    .toJobParameters();
```

The path can be non-identifying, yet the application must **lock the batch key's source content** via checksum or manifest version. If someone swaps the file at the same path before a restart, checkpoint offsets no longer match the original data.

If a job already `COMPLETED` and must be re-evaluated under new rules, manage reprocessing explicitly: new identifying keys, policy for overwriting/archiving old reports, and impact on already-published data.

## 17. Reports from StepExecution vs. Reports from Data

Enrich quality reports with Spring Batch metadata to separate operational efficiency from data quality:

| Information | Source | Example |
| --- | --- | --- |
| Job/Step status | `JobExecution`, `StepExecution` | `COMPLETED`, `FAILED` |
| Processing duration | Execution metadata | 120 seconds |
| Read/Write/Skip/Filter counts | `StepExecution` | `readCount=1000` |
| Accepted/rejected per business rule | Staging / `quality_issue` | `EMAIL_REQUIRED=30` |
| Source checksum, rule version | Manifest / `JobParameters` | `sha256=...`, `v1` |
| Quality report status | Quality gate | `PASS`, `WARN`, `FAIL` |
| Publish status | Downstream / target step | Published 970 records |

A `writeCount=1,000` is completely normal if the writer persisted **1,000 evaluation decision rows** into staging, even if only 970 customers were accepted. Therefore never label `writeCount` as "acceptedRows" in this design.

If reader errors were skipped, evaluated rows in staging may be fewer than attempted source reads. Include a dedicated `unparsedRows` or `readErrorRows` field with proper source tracking. Never claim "100% of source evaluated" when the parser failed to read part of the input.

## 18. Designing Report Output for Operations

A report should include these sections:

### Identifying Information

```text
reportId:      quality-crm-2026-11-15-v1
jobName:       importCustomersJob
batchKey:      crm-2026-11-15-v1
businessDate:  2026-11-15
sourceUri:     s3://bucket/snapshots/customers-20261115.csv
sourceHash:    sha256:...
ruleVersion:   v1
executionId:   2042
generatedAt:   2026-11-16T01:45:00Z
```

This is illustrative data. Store source URIs per security policies; never include signed URLs, access tokens, or credentials in reports.

### Summary Results

```text
evaluatedRows: 10000
acceptedRows:  9880
rejectedRows:  120
acceptancePct: 98.80
duplicateRows: 15
qualityStatus: FAIL
gateReasons:
  - "DUPLICATE_ID exceeded threshold 0"
```

`acceptancePct` exceeds 98%, yet the gate still `FAIL`s because duplicates must be 0. This illustrates how a critical rule vetoes the aggregate pass rate.

### Breakdown by Rule

| Rule Code | Severity | Violating Rows | Rate of Evaluated Rows | Threshold | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `EMAIL_REQUIRED` | ERROR | 60 | 0.60% | ≤1% | PASS |
| `AGE_RANGE` | ERROR | 45 | 0.45% | ≤0.5% | PASS |
| `DUPLICATE_ID` | CRITICAL | 15 | 0.15% | 0 | FAIL |

The sum of violating rows in the table may equal or exceed rejected rows depending on multi-rule violations and grouping. Always state metric definitions at the top of the report.

### Bad-Record Samples

To aid investigation, reports can include counts and a link to an access-controlled quarantine store. Avoid embedding raw emails, addresses, account numbers, or full failing CSV rows in operational alert emails. Use source row keys, error codes, and line numbers instead.

## 19. Testing Data Quality Reporting

Test at both rule level and pipeline level. **Unit tests** verify processor classification; **integration tests** verify writers, SQL aggregation, and gates across transactions, checkpoints, and final outputs.

### 19.1. Processor Unit Tests

JUnit 5 example:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CustomerQualityProcessorTest {

    private final CustomerQualityProcessor processor =
        new CustomerQualityProcessor();

    @Test
    void acceptsValidRow() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(2, "C001,alice@example.com,28")
        );

        assertEquals("VALID", result.status());
        assertEquals("", result.issueCodes());
        assertEquals("C001", result.customerId());
        assertEquals(28, result.age());
    }

    @Test
    void reportsMultipleViolationsForOneRow() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(3, "C002,,17")
        );

        assertEquals("REJECTED", result.status());
        assertTrue(result.issueCodes().contains("EMAIL_REQUIRED"));
        assertTrue(result.issueCodes().contains("AGE_RANGE"));
    }

    @Test
    void marksMalformedRecordWithoutThrowing() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(4, "C003,only-two-columns")
        );

        assertEquals("REJECTED", result.status());
        assertTrue(result.issueCodes().contains("MALFORMED_RECORD"));
    }

    @Test
    void normalizesBusinessKey() throws Exception {
        QualityDecision result = processor.process(
            new SourceRow(5, " c001 ,a@example.com,30")
        );

        assertEquals("C001", result.customerId());
    }
}
```

Unit tests verify the processor per individual source row. They **do not test duplicate detection**, because duplicates are detected after staging holds multiple rows.

### 19.2. Integration Tests with Staging and Reports

Scenarios to cover:

| Input | Expected Outcome |
| --- | --- |
| Empty or header-only file | `evaluatedRows=0`, report `NO_DATA` or configured policy |
| One valid record | `accepted=1`, `rejected=0` |
| Record missing email | `EMAIL_REQUIRED`, rejected |
| Record with invalid age | `AGE_RANGE`, rejected |
| One record breaking two rules | One rejected row, two violations |
| Two matching IDs after normalization | First kept; second flagged `DUPLICATE_ID` per policy |
| Record counts just below/at/above chunk size | No dropped/duplicated chunk-boundary records |
| Writer failure before commit | No rolled-back staging rows persist |
| Restart after mid-file failure | No duplicated staging; aggregate report accurate |
| Re-running finalize step | Duplicates not double-counted; report upserted |
| Critical rule exceeds threshold | Report `FAIL`; publish step does not run |
| Quality gate right on boundary | Outcome matches explicit `<` vs. `<=` rule |
| Source file altered before restart | Blocked or checksum error raised; stale checkpoint rejected |
| Multiple partitions/workers | Exact total rows; staging keys remain unique |

When testing PostgreSQL-specific SQL such as `ON CONFLICT` and `FILTER (WHERE ...)`, use a PostgreSQL-compatible test environment such as a test container database. Never assume all SQL behaves identically on H2.

### 19.3. Testing the Quality Gate with Concrete Numbers

Example gate accepting when acceptance rate is **at least 98%** and duplicates equal 0:

| evaluated | accepted | duplicate | Verdict |
| ---: | ---: | ---: | --- |
| 100 | 98 | 0 | `PASS` |
| 100 | 97 | 0 | `FAIL` |
| 100 | 100 | 1 | `FAIL` |
| 0 | 0 | 0 | `NO_DATA` |
| 10,000 | 9,800 | 0 | `PASS` |

Test the `NO_DATA` path explicitly, because division by zero can crash or produce false conclusions if code defaults empty sources to 100%.

## 20. Monitoring, Alerting, and Trends Over Time

A single run's report shows quality for that period. To catch gradual degradation, store period history and trend:

- Acceptance rate by date/source/tenant.
- Violating record counts by rule code and rule version.
- Duplicate rate, missing rate, and completely unparseable rows.
- Received source volume versus prior-period baselines.
- Periods with `FAIL` or `NO_DATA` quality gates.
- Latency from data receipt to report generation.
- Discrepancies between source count, evaluated rows, and published records.

If acceptance rate suddenly drops from 99.9% to 85%, distinguish real data drift from deploying a new rule version. Always include rule set and schema versions in reports.

### Alert Classification

- **Info:** report ready, quality passed.
- **Warning:** a metric approached a threshold without blocking publish.
- **Critical:** schema failure, missing mandatory data, or quality gate failed per policy.
- **Technical error:** failed to produce report because job `FAILED`, writer failed, or metadata is inconsistent.

Do not send thousands of emails per bad record; send one per-period summary notification with a link to an access-controlled investigation area. Metrics should use moderate-cardinality labels like job, source, rule, and status; avoid per-record UUIDs as labels.

## 21. Common Mistakes

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Treating `BatchStatus.COMPLETED` as "data passed" | Misses business errors | Dedicated quality gate |
| Summing `filterCount` and `skipCount` as rejected without definition | Wrong metrics, missing causes | Persist decisions and violations per source row |
| Error counter in a singleton processor | Breaks on retries, rollbacks, restarts, or multithreading | Aggregate from committed staging |
| Using one exception for both data and infra errors | Unnecessary job failures or hidden technical outages | Classify clearly |
| Loading entire source into memory to find duplicates | Heap growth, poor restart/parallelism | Check uniqueness in staging/database |
| Omitting rule version | Hard to compare reports across days | Store version in reports and sources |
| Counting duplicates twice after restart | Append writes instead of upsert | Key by `batchKey + sourceLine`, idempotent ops |
| Treating sample email regex as universal standard | Rejects valid data | Define validation contract and tests |
| Confusing violating records with violation counts | Total errors can exceed row count | Use an issue table or two distinct metrics |
| Counting header-only files as 100% valid | Zero denominator | `NO_DATA` policy |
| Measuring only source data before publish | Misses losses/duplicates during target writes | Reconcile counts and keys at the target |
| Report fails after data already published | Gate runs too late | Stage first, publish after gate |
| Putting full personal data in alert logs/emails | Security risk | Keep only keys/error codes; secure quarantine tables |
| Silently changing quality gate thresholds | Unexplained quality shifts | Version threshold configs |
| Modifying source file on restart | Checkpoints point to wrong data | Snapshots + checksums |
| High composite score hides critical failure | Reports "PASS" despite severe bug | Enforce mandatory checks separately |
| Report SQL aggregates across wrong executions | Numbers detached from a single source period | Stable batch keys and clear scoping |

## 22. Practice Exercise

Build `importCustomersJob` with an ingest step, a quality-finalize step, and a publish step:

1. Read a CSV file containing `customer_id`, `email`, and `age`.
2. Implement at least four rules: required ID, required email, age 18–120, and unique customer ID after normalization.
3. Every record must receive `VALID` or `REJECTED`; rejected rows store violation codes.
4. Staging table must have a unique key on batch key and source row to support restarts.
5. Report must include evaluated/accepted/rejected rows, per-rule violation counts, and acceptance rate.
6. Gate allows publishing only if acceptance rate ≥ 98% and duplicates equal 0. Empty sources must have a distinct conclusion.
7. Simulate a mid-chunk writer failure and restart. Final report and staging data must not duplicate.
8. Change one rule, bump `ruleSetVersion`, and compare two evaluations over the same source snapshot via an explicit reprocess flow.
9. Reconcile published records against the report's `accepted` count and verify zero duplicate keys at the target.

Expected deliverables include a per-period report file or record, a violation list traceable by source row key, and a test matrix proving the quality gate works at boundary thresholds.

## 23. Summary

**Data quality reporting** in Spring Batch must be built from **explicit business rules, traceable evaluation records, and committed results**, rather than reading `StepExecution` counters alone to guess whether data passed. Spring Batch provides Readers, Processors, Writers, Step/Job metadata, and restart mechanics; the application supplies violation models, staging, aggregation, and quality gates to separate technical completion from business quality.

A strong design defines exact denominators, records rule/version and source snapshots, handles multi-rule violations per record, prevents double-counting across retries/restarts, and blocks publishing on critical breaches. Combining per-period reports with trend monitoring lets operations catch data defects early, investigate root causes, and forward only trustworthy data downstream.
