# Documenting Job Assumptions and Limits in Spring Batch

## 1. Why Must a Batch Job Explicitly Document Assumptions and Limits?

A Spring Batch job is more than an `ItemReader → ItemProcessor → ItemWriter` chain. It also enforces an **operational and data contract**: where inputs come from, which cases the job is authorized to process, what defines success, whether it can restart, and what volume the system can handle.

Many batch incidents do not stem from Java syntax bugs. They come from **implicit assumptions** that were never written down:

- "The file always arrives before 01:00."
- "Each order ID appears only once."
- "The reader will read in the exact same order after a restart."
- "Two instances of the job will never run concurrently."
- "A successful writer database commit means the external API succeeded."
- "Volume will never exceed 100,000 records."
- "If one bad row is dropped, the job can still count as successful."

When an assumption breaks, the job can create duplicates, drop transactions, breach SLAs, or complete with untrustworthy outputs.

**Documenting job assumptions and limits** turns implicit conditions into artifacts that can be read, debated, verified, and monitored. This is a vital design decision in **Spring Batch Core Processing**, not box-ticking README paperwork.

### Quick Example

Suppose `importPartnerOrders` imports orders from a partner file nightly at 02:00.

A weak documentation line:

> Job imports orders fast, without duplicates, and supports restart.

A far more valuable specification:

| Type | Specific Content | How to Verify |
|---|---|---|
| Assumption | Every import has an immutable `inputVersion` | Verify object version/checksum before and after restart |
| Assumption | `externalOrderId` is unique within each `sourceSystem` | Duplicate report and unique constraint |
| Limit | File max 500 MiB and 2 million rows | Preflight validation; reject inputs exceeding limits |
| Guarantee | Valid data commits in chunks and is restartable | Integration test failing mid-writer and restarting |
| Limit | Does not support two executions processing the same input version concurrently | Orchestration lock and duplicate-launch test |
| SLA | 95% of runs under standard load finish within 30 minutes | Duration metric by workload |
| Reaction | On checksum mismatch, job ends `FAILED` and publishes nothing | Test modifying input between runs |

These numbers are **illustrative only**, not universal thresholds set by Spring Batch. Real systems must base them on infrastructure capacity and business rules.

## 2. Distinguishing Assumptions, Constraints, Invariants, and Design Decisions

These terms are related, not synonymous.

| Concept | Meaning | Example |
|---|---|---|
| **Assumption** | Something expected to hold true for the design to work | "Source API returns stable results for the same snapshot token." |
| **Constraint / Limit** | A boundary the system must respect or never exceed | "A single file is at most 500 MiB." |
| **Invariant** | A property that must always hold in every valid execution | "No two committed transactions share the same business key." |
| **Decision** | Implementation approach chosen among alternatives | "Use a staging snapshot and JDBC writer rather than reading live API." |
| **Risk** | What can happen if an assumption fails or constraint is breached | "If API paging shifts ordering, restarts may skip items." |
| **Guarantee** | What the system promises to deliver within defined scope/conditions | "Within the same DB transaction, chunk writes roll back if the writer throws." |

Example:

```text
Assumption:
  Source returns stable data per inputVersion.

Constraint:
  inputVersion must be present and immutable on restart.

Decision:
  Reader reads exclusively from staging by inputVersion.

Invariant:
  Each (sourceSystem, externalOrderId) is written at most once.

Risk:
  If staging mutates after a checkpoint, cursor may point to wrong item.

Mitigation:
  Immutable staging + checksum + unique constraint.

Verification:
  Test restart when sourceVersion changes -> must fail.
```

Do not lump everything into a single "notes" list. Classifying items tells operators what to **monitor**, what to **reject at input**, and what to **verify with tests**.

### 2.1. An "Assumption" Is Not Proof

Writing down an assumption does not make it true. For instance, "the partner only sends each file once" does not guarantee zero duplicates. Ask:

- Who signed off on this assumption?
- Is there partner documentation or an SLA backing it?
- Can it be checked automatically in code?
- If the assumption fails, should the job fail, skip, quarantine, or proceed?
- Is monitoring in place to detect assumption violations?

For conditions directly tied to data integrity, **turn assumptions into executable checks**, or add safeguards that do not depend on the assumption holding.

## 3. Running Example: `dailyPartnerSettlement` Job

We will use a hypothetical job to illustrate documenting and enforcing a contract.

**Problem:** Every night, the business receives partner transactions, validates, normalizes, and writes reconciliation results to PostgreSQL.

```text
Scheduler / Operator
        |
        v
JobParameters:
  businessDate
  sourceSystem
  inputVersion
        |
        v
Step 1: validateInputManifest
        |
        v
Step 2: loadTransactions
  ItemReader -> ItemProcessor -> JdbcBatchItemWriter
        |
        v
Step 3: reconcileTotals
        |
        v
Step 4: markResultReady
        |
        v
Report/Downstream system
```

Such a job requires more than step definitions. From the design phase, answer:

1. **Input identity:** which exact dataset does a run represent?
2. **Freshness:** by what time must the source be ready?
3. **Schema:** which fields, types, and version are mandatory?
4. **Volume:** how many records, file size, expected rate?
5. **Data quality:** how many errors at most may be skipped?
6. **Transactions:** commit boundaries and out-of-transaction side effects?
7. **Restart:** which checkpoints apply and is the input immutable?
8. **Concurrency:** can runs execute in parallel for the same date and source?
9. **Result semantics:** under what conditions may `DataReady` be emitted?
10. **Observability:** which metrics and alerts must be monitored?

This constitutes a **job contract**. Version it alongside the code and update it whenever the design changes.

## 4. Documenting Business Scope: What Does the Job Do and Not Do?

First, documentation must state **scope and boundaries**.

Example:

```markdown
## Job contract: dailyPartnerSettlement

In scope:
- Read transactions for a given businessDate and sourceSystem.
- Validate schema and business keys.
- Write valid transactions into staging/ledger per policy.
- Reconcile record counts and monetary totals.
- Emit readiness signal only after reconciliation passes.

Out of scope:
- Auto-repairing records missing a transaction ID.
- Guessing duplicate transactions without sourceTransactionId.
- Sending bank payouts within the same DB transaction.
- Falling back to the "latest" file if the specified inputVersion is missing.
```

Explicitly documenting **out of scope** is just as useful as listing core features. It stops operators from assuming restarting a job will auto-heal corrupt source data, or thinking the job already disbursed funds when it only wrote staging rows.

### 4.1. Defining "Success"

A Spring Batch job has `BatchStatus` and `ExitStatus`. Yet framework-level `COMPLETED` does not automatically prove data satisfies every business requirement.

A strong contract states:

- Ingestion step completed.
- Zero unhandled critical data errors.
- Source record count = accepted records + rejected records across defined buckets.
- Monetary totals and control numbers reconcile cleanly.
- Data is committed to target tables.
- `DataReady` signal emits only after all conditions are verified.

If a transaction was skipped under `skipLimit` yet stayed within technical limits, decide explicitly: **may the job finish `COMPLETED`, or must the quality gate fail it?**

This is a business decision—never assume `skipLimit(10)` means "okay to lose 10 financial transactions."

## 5. Documenting the Input Contract: Source, Schema, and Immutability

A common design mistake is writing "job reads CSV" without defining which CSV, which version, which encoding, or how headers are handled.

Example input contract table:

| Attribute | Example Value | Condition to Verify |
|---|---|---|
| Source | Object storage staging | Read only from authorized prefix |
| `sourceSystem` | `PARTNER_A`, `PARTNER_B` | Allowlist |
| `businessDate` | ISO `yyyy-MM-dd` | Valid date in business timezone |
| `inputVersion` | Immutable object version/checksum | Unchanged across run and restarts |
| Format | UTF-8 CSV | Header matches schema |
| Schema version | `v2` | Reject other versions or migrate explicitly |
| Required fields | `sourceTransactionId`, `amount`, `currency` | Must not be missing |
| Amount | Decimal, max 2 decimal places | Business min/max bounds |
| Record ordering | Do not rely on file order unless guaranteed | Reader/restart must enforce deterministic ordering |
| Duplicate key | `(sourceSystem, sourceTransactionId)` | Same key must never create two transactions |
| Input retention | e.g., 30 days | Long enough to cover restart/reconciliation SLAs |

Replace the "Example Value" column with values signed off by the source system owner. Specific fields vary per partner contract.

### 5.1. File Name Is Not File Identity

The name `transactions.csv` may be reused daily. If a reader checkpoints at row 400,000 and the file is overwritten, restarting can drop or misread records.

Pin a stable identifier, such as:

```text
sourceSystem = PARTNER_A
businessDate = 2025-05-12
inputVersion = sha256:abc123...
```

In production, `inputVersion` must genuinely bind to source content, such as a checksum or object-store version ID. Simply passing a string in `JobParameters` without verifying the underlying file **does not create immutability**.

### 5.2. Database Sources Need Snapshot Semantics Too

Reading a database page by page without a deterministic `ORDER BY` can drop or duplicate records when data mutates. Document:

- Which rows belong to a run: `created_at <= cutoff`, a `snapshotId`, or a materialized ID list?
- Is the sort key unique and stable?
- Is appropriate transaction isolation/snapshot in place?
- Can the source be updated while the job reads?
- If mutations happen between pages, does the job fail or reconcile?

A limit like "read at most 500,000 rows" does not replace specifying **which exact 500,000 rows are read**.

## 6. Documenting `JobInstance` Identity and Restart Parameters

Spring Batch distinguishes:

- **`Job`**: processing flow definition.
- **`JobInstance`**: logical work unit identified by job name and **identifying `JobParameters`**.
- **`JobExecution`**: one run attempt of a job instance; restart creates a new execution.
- **`StepExecution`**: single step execution holding status/counters and `ExecutionContext`.

Example parameter contract:

| Parameter | Identifying? | Meaning |
|---|---|---|
| `businessDate` | Yes | Business date being reconciled |
| `sourceSystem` | Yes | Partner identifier |
| `inputVersion` | Yes | Immutable input version |
| `requestedBy` | No | Operator audit trail |
| `requestReason` | No | Operational reason |
| `traceId` | No | Log correlation ID |

Example constructing parameters for a job instance:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2025-05-12", true)
        .addString("sourceSystem", "PARTNER_A", true)
        .addString("inputVersion", "object-version-871", true)
        .addString("requestedBy", "ops-console", false)
        .toJobParameters();
```

**Constraint to document:** "Identical `businessDate + sourceSystem + inputVersion` maps to the same `JobInstance`. Never mint a new identifying `run.id` to rerun a `FAILED` or `STOPPED` execution that ought to be restarted."

To intentionally reprocess a corrected file, issue a new `inputVersion` or a dedicated reprocessing workflow with overwrite/reconciliation rules. Never tweak parameters casually just to bypass `JobInstanceAlreadyCompleteException`.

### 6.1. Idempotency Keys Differ from `JobExecution` IDs

Never use `jobExecutionId` as the business transaction unique key when deduplicating across restarts. `jobExecutionId` changes on every new execution. Business keys like `(sourceSystem, sourceTransactionId)` express true transaction uniqueness.

**Documentation should state both key types:** keys identifying the job instance and keys deduplicating business writes.

## 7. Time: Timezones, Cutoffs, and SLAs

A line like "job runs daily at 01:00" leaves many questions unanswered:

- 01:00 in which timezone?
- Is `businessDate` the scheduler's date or the data's date?
- If the scheduler runs late past midnight into the next day, which date applies?
- Is the cutoff window inclusive or exclusive?
- On Daylight Saving Time (DST) transitions, how long is the window?
- On a restart on a later day, is the cutoff recomputed?

Example contract:

```text
Scheduler timezone: Asia/Ho_Chi_Minh
Schedule: 01:00 daily
Business date: passed explicitly via JobParameters
Data window: [businessDate 00:00, nextDate 00:00)
End boundary: exclusive
Restart: preserve businessDate and inputVersion
SLA: complete before 03:00 for load within design bounds
```

Half-open intervals `[startInclusive, endExclusive)` cleanly stitch consecutive days together without double-counting boundary records.

### 7.1. Never Read Wall-Clock Time per Item

Avoid:

```java
// Easily causes a job crossing midnight to compute two different cutoffs:
LocalDate businessDate = LocalDate.now();
```

Read `businessDate` from `JobParameters` and compute boundaries once in the business timezone:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate date = LocalDate.parse(businessDateText);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        date.atStartOfDay(zone).toInstant();

Instant endExclusive =
        date.plusDays(1).atStartOfDay(zone).toInstant();
```

If data uses another timezone, change `zone` per business contract. Never manually add/subtract a fixed hour offset where DST can apply; `atStartOfDay(zone)` and `plusDays(1)` handle offset shifts per timezone rules.

**Assumption:** source data includes valid timezone/offset info and is normalized before window comparisons. If inputs carry naive local timestamps without timezones, document an explicit interpretation rule rather than guessing from server default timezone.

## 8. Data Limits: Volume, Size, and Load Profile

Every job should document its **capacity envelope**—the load range designed and tested.

| Factor | Example Limit | What Happens If Exceeded? |
|---|---|---|
| Files / input versions | One version per job instance | Reject out-of-contract request |
| File size | Max 500 MiB | Fail preflight / quarantine |
| Record count | Max 2,000,000 | Refuse import if manifest exceeds cap |
| Single record size | Max 32 KiB | Reject/quarantine record or file per policy |
| Business key length | Max 120 characters | Validation error |
| Active transactions | Bounded by DB pool and concurrency | Throttle or reject launch |
| Completion time | 30-minute SLO at standard load | Alert if exceeded; never fake status |
| Source retention | At least 30 days | Enforce retention and recovery window |

These figures are **not Spring Batch defaults**. Base them on benchmarks, storage/database limits, and actual SLAs.

### 8.1. Hard Limits vs. Soft Limits

- **Hard limit:** exceeding it cannot be processed safely or is disallowed. E.g., a file larger than the scanner/parser can handle; reject/fail before writing.
- **Soft limit / SLO:** exceeding it triggers alerts or re-scheduling, not necessarily immediate failure. E.g., a job normally taking 30 minutes runs 35 minutes due to elevated volume.
- **Resource budget:** connection, heap, CPU, and I/O quotas allocated to the job; throttle or gracefully halt when breached.

Never equate "30-minute SLO" with "SIGKILL the JVM at minute 30." Forced kills can leave `JobRepository` un-updated, lose checkpoints, and require manual recovery.

### 8.2. Minimum Throughput

To process 1,200,000 items within 40 minutes, minimum end-to-end throughput is roughly:

```text
1,200,000 / (40 × 60) = 500 items/second
```

This is theoretical math before subtracting preflight, file download, reconciliation, startup, and flushing. Real benchmarks need headroom for bursty load and transient errors.

Documentation should specify the **reference workload**:

```text
Reference workload:
- 1,200,000 records
- average row 420 bytes
- 1% invalid records (if policy permits)
- PostgreSQL staging, production-like indexes
- 4 batch workers
- 30-minute target for full job
```

Never claim a job "meets SLA" just because it ran fast on 1,000 records in H2. Small tests prove logic, not capacity.

## 9. Memory Limits, Chunk Size, and Transactions

Spring Batch processes in chunks to bound in-memory item count at any instant and define standard transaction boundaries.

Configuration example:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

Step loadTransactionsStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawTransaction> reader,
        ItemProcessor<RawTransaction, ValidTransaction> processor,
        ItemWriter<ValidTransaction> writer) {

    return new StepBuilder("loadTransactionsStep", repository)
            .<RawTransaction, ValidTransaction>chunk(
                    200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`RawTransaction` and `ValidTransaction` are illustrative domain types. `chunk(200, transactionManager)` sets the **commit interval in read items**, not a cap on file size, JDBC batch size, or worker count.

### 9.1. Documenting Assumptions for Chunk Size

Decision example:

```text
Decision: chunk size = 200

Assumptions:
- Each item is smaller than 32 KiB.
- Reader advances sequentially over an immutable snapshot.
- Writer shares the step's transaction manager.
- 200 items do not cause excessive lock hold times.

Constraints:
- Finite timeouts configured for all DB operations.
- Failing chunk must never partially auto-commit on a separate connection.

Verification:
- Benchmark at 50, 200, 500.
- Integration test failing writer on last item of chunk.
- Verify rollback and restart cause zero lost or duplicate records.
```

An item-size limit does not guarantee heap sufficiency: reader buffers, JPA persistence contexts, caches, thread stacks, and temporary objects also occupy RAM. Measure real memory instead of multiplying `chunkSize × averageRowSize` and assuming that is total heap.

### 9.2. What Does the Transaction Actually Cover?

With `DataSourceTransactionManager` or a matching manager, a JDBC writer using the same datasource joins the step's transaction. However, HTTP API calls, emails, or object-store writes do not roll back when the DB transaction rolls back.

**Assumption to convert into an explicit constraint:** "Chunk atomicity applies only to operations participating in the same transaction; external side effects require idempotency/outbox."

If a job writes to two distinct databases, do not claim "all-or-nothing" merely because each datasource has its own transaction manager. Pick a coordinated transaction model or design eventual consistency and reconciliation.

## 10. Retry, Skip, and Rollback: Fault-Tolerance Limits

Spring Batch supports `faultTolerant()`, `retry(...)`, `retryLimit(...)`, `skip(...)`, and `skipLimit(...)`. Yet a generic set of parameters does not capture full business policy.

Hypothetical example:

| Error Type | Retry | Skip | Expected Outcome |
|---|---|---|---|
| Transient DB timeout | Yes, max 3 times | No | Succeed or step `FAILED` |
| CSV row with bad encoding | No | Yes if policy allows, capped at limit | Quarantine / quality gate |
| Missing transaction ID | No | No if transaction is mandatory | Step `FAILED` |
| Identical duplicate payload | No | Can deduplicate as filter/DB conflict | Audit duplicate |
| Same ID with conflicting amount | No | Never silently drop | Quarantine or `FAILED` |
| Input file version changed | No | No | Fail fast; never restart on new source |
| Source file missing | No | No | Fail before writing |

`skipLimit` is the step's total skip budget across allowed phases, not a separate cap per phase. `retryLimit` is the framework retry cap; it does not mean network errors can recover if the reader/cursor cannot re-read consistently.

### 10.1. Fault-Tolerant Step Example

```java
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("loadTransactionsStep", repository)
        .<RawTransaction, ValidTransaction>chunk(
                200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(FlatFileParseException.class)
        .skipLimit(5)
        .build();
```

This is a **policy example**, not guidance that every financial job should tolerate skipping 5 transactions. In a reconciliation system, policy may require failing the whole run if any line is unreadable. Technical policies must be signed off by data owners.

Never write `.skip(Exception.class)` just to make a job "look stable": it can hide misconfigurations, security breaches, infrastructure outages, and bugs.

### 10.2. Documenting Retry Limits

A thorough decision does not merely say "retry 3 times"; it records:

- Which exact exceptions count as transient.
- Whether backoff is used and with what intervals.
- Timeout per API/DB call.
- Whether max retries apply per **item, chunk, or remote request**.
- Upon final exhaustion, whether skipping is permitted or failing is mandatory.
- Whether side effects are idempotent if an earlier request actually succeeded before its response dropped.

This is vital for APIs: a client timeout never proves the server did not process the request. When retrying a transaction-creating `POST`, use an idempotency key or status lookup protocol.

## 11. Restartability: Document Both Preconditions and Limits

Saying "the job supports restart" is not enough. Document **where it restarts from, on what data, and which conditions make restarting unsafe**.

### 11.1. Three Questions Before Claiming Restartability

1. **Does the reader checkpoint?** Do `FlatFileItemReader`, `JdbcPagingItemReader`, or custom `ItemStreamReader` save position and stable ordering?
2. **Is the input immutable?** Do file/object versions, API snapshots, or staging data remain untouched?
3. **Is the writer idempotent?** Will items committed in prior chunks duplicate on retry/restart?

Illustrative restart contract:

```text
Restart policy:
- Restart only FAILED or STOPPED JobExecutions when permitted by framework.
- Same JobInstance: preserve identifying JobParameters.
- inputVersion unchanged.
- Reader restores cursor from StepExecutionContext.
- Database writer enforces uniqueness via business key.
- External notifications decoupled via outbox.
- On source checksum mismatch, reject restart.
- On incompatible serialized ExecutionContext, fail fast.
- If source retention expired, follow new reprocess procedure.
```

### 11.2. `ExecutionContext` Has Clear Scope

**StepExecution context** fits reader checkpoints like `nextIndex`, `lastId`, and `pageToken`. **JobExecution context** is typically used to pass small cross-step data, such as a verified output path.

`ExecutionContext` must store small, serializable data essential for restarts. Never store millions of records or non-serializable objects just to avoid re-reading the source.

If a delegate reader implements `ItemStream` without having its `open/update/close` lifecycle registered on the step, checkpoints will not persist. For delegates nested inside composites/wrappers, you may need `.stream(delegate)`.

### 11.3. `FAILED` Status Does Not Prove All Data Rolled Back

A multi-chunk job:

```text
Chunk 1: COMMIT 200 records
Chunk 2: COMMIT 200 records
Chunk 3: writer error -> ROLLBACK
JobExecution: FAILED
```

Those 400 records from the first two chunks remain persisted. Restarts must resume cleanly—never assume the database is empty just because the job ended `FAILED`. Nor can you infer exact committed row counts solely from `readCount` or `writeCount` if the writer deduplicates, upserts, or filters.

## 12. Concurrency: Can the Job Run in Parallel?

A dangerous assumption is "the scheduler only triggers once per day." In reality, you may encounter:

- Two scheduler instances active during failover.
- An operator clicking rerun while the old job is still running.
- Two files for the same business date arriving close together.
- A worker appearing hung, causing a monitor to spawn another worker.
- Parallel steps or partitioned steps writing to the same table.

Document an explicit **concurrency contract**:

| Level | Design Question | Example Decision |
|---|---|---|
| Single `JobInstance` | Can two executions run concurrently? | No; let framework/repository reject and alert |
| Same business date, different input version | Can they process in parallel? | No if writing to the same final snapshot; requires orchestration lock |
| Different business dates | Can they process in parallel? | Yes if data keys do not overlap |
| Single step | Are reader/writer thread-safe? | Never share stateful readers across threads |
| Partitioning | Do data slices overlap? | Split by disjoint ID ranges or stable hash keys |
| Database | Are connection/lock budgets sufficient? | Cap worker count and size pools accordingly |

Never expect `ConcurrentHashMap` or an in-JVM lock to coordinate two separate application processes. When concurrency touches data uniqueness, enforce database constraints, durable orchestration locks, or equivalent mechanisms.

### 12.1. Bounding Workers Does Not Guarantee Ordering

With multiple partitions, partition completion order is non-deterministic. A "first record wins" rule can produce different winners across runs.

When selecting the latest update, use `sourceVersion`, `eventTime`, and a deterministic tie-breaker rather than thread execution order. When aggregating data, design associative/commutative aggregations or explicit ordering coordination.

## 13. Data Quality: Output Acceptance Criteria

Assuming "source data is clean" rarely survives production. Write a **quality control table**:

| Condition | Example Threshold | Action |
|---|---|---|
| Missing `sourceTransactionId` | 0 | Fail import |
| Negative amount when prohibited by contract | 0 | Fail / quarantine |
| Malformed row not representing a critical transaction | Max 5 | Audit + quality gate |
| Duplicate with identical key and payload | Allowed dedup | Count extra occurrences |
| Duplicate with same key but differing amount | 0 | Fail / quarantine |
| Source-to-target amount total variance | 0 | Do not emit `DataReady` |
| Record count mismatch | 0 (after accounting for excluded buckets) | Fail reconciliation |
| Unsupported schema version | 0 | Reject input |

Example thresholds must be approved by data owners. Never simply set `skipLimit(10)` without accounting for skipped items in reconciliation.

### 13.1. Reconciliation Equation Must Be Explicit

Illustrative equation over mutually exclusive buckets:

```text
totalInputRows
  = acceptedUniqueRows
  + exactDuplicateExtraRows
  + invalidRows
  + conflictingDuplicateRows
```

This equation holds only when duplicates are counted by **extra occurrences** and every input row lands in exactly one bucket. If counting distinct duplicate groups or picking one winner in conflict groups, adjust the equation accordingly.

**Never treat `StepExecution.writeCount` as newly inserted DB rows** when the writer uses `INSERT ... ON CONFLICT DO NOTHING` or when one item triggers multiple writes.

### 13.2. Quality Gate as an Explicit Step

An operable pipeline layout:

```text
validateInputManifest
        |
        v
loadTransactions
        |
        v
reconcileTotals
        |
   +----+----+
   |         |
  PASS      FAIL
   |         |
   v         v
markReady   Job FAILED / quarantine
```

If reconciliation detects a totals mismatch, that step must fail or return an exit status routed per flow policy. Never emit a "data ready" completion event simply because the ingestion step reached `COMPLETED`.

## 14. Security and Compliance Are Also Job Limits

An "internal-only" job may run under a high-privilege service account reading sensitive data. Thus the job contract should specify:

- Who is authorized to launch, restart, or stop?
- Who is authorized to specify `sourceSystem`, `tenantId`, or file versions?
- Which database privileges does the job's DB user hold?
- Which file/object storage paths are allowed for reads?
- Which fields must never be logged or stored in `ExecutionContext`?
- Do outputs with personal data require encryption, retention limits, or auditing?
- Which outbound APIs may be called?
- How does the job respond to unexpected schemas or suspicious paths?

### 14.1. `JobParameters` Is Not a Secrets Channel

`JobParameters` are persisted in batch metadata and often visible in operational UIs. Never pass access tokens, passwords, or private keys in them.

Pass a non-sensitive reference key and fetch credentials from a secret manager or secure application configuration. Likewise, `ExecutionContext` is not the place for connections, passwords, or live client objects.

### 14.2. Safe Data Boundaries

If filenames are caller-supplied, validate and confine them to an approved filesystem root; if SQL uses values from CSVs, always use parameter binding. Never use assumptions like "filenames are always valid" or "partners never send special characters" to skip parameter binding and authorization.

## 15. Observability: Which Assumptions Must Be Measured?

A condition written in docs without runtime verification silently rots as systems evolve.

Pair assumptions with concrete signals:

| Assumption / Limit | Metric or Check |
|---|---|
| File arrives before 01:00 | `input_arrival_lag_seconds` |
| Input stays under 2M records | Manifest `recordCount`, `input_rows_total` |
| Job finishes within SLO | `spring.batch.job` duration and workload threshold |
| Steps do not hang | `spring.batch.step.active` or active elapsed time |
| Source immutable on restart | Checksum/version comparison |
| Duplicates within threshold | `duplicate_extra_rows_total` |
| Monetary variance equals 0 | Reconciliation result |
| Zero unauthorized skips | `StepExecution` read/process/write skip counters |
| DB retries stay bounded | Retry metrics/logs by exception class |
| At most one "ready" output per day | Unique business key on output event |
| Zero cross-tenant writes | Authorization tests and audit logs |

Metrics like `input_arrival_lag_seconds` and `duplicate_extra_rows_total` are **application-defined metrics**, not emitted automatically by Spring Batch. Verify actual Spring Batch/Micrometer meters for your project's version and config.

Never use `jobExecutionId`, `sourceTransactionId`, or raw error messages as Prometheus tags due to high cardinality and data-leak risks. Keep detailed IDs in access-controlled logs and traces.

### 15.1. Document How Dashboards Interpret Numbers

Documentation should clarify:

- Is duration measured per `JobExecution` or summed across steps?
- How is elapsed time computed for in-flight steps with null `endTime`?
- Are `FAILED`/`STOPPED` runs included in statistics?
- Are sample sizes large enough for percentiles to be meaningful?
- If a process crashes leaving `JobRepository` in `STARTED`, how is liveness verified?

Never sum parallel step durations and claim that equals job wall-clock duration—parallel steps overlap in time.

## 16. From Docs to Code: Validating Input Assumptions

Turn critical assumptions into **hard checks** in code. In Spring Batch 5.2, `JobParametersValidator` is the right extension point to validate parameters before the job runs.

### 16.1. Validator for Core Parameters

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class SettlementJobParametersValidator
        implements JobParametersValidator {

    private static final Set<String> ALLOWED_SOURCES =
            Set.of("PARTNER_A", "PARTNER_B");

    private static final Pattern INPUT_VERSION =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "Missing JobParameters");
        }

        String businessDate = parameters.getString("businessDate");
        String source = parameters.getString("sourceSystem");
        String version = parameters.getString("inputVersion");

        if (businessDate == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must be a valid ISO date");
        }

        if (!ALLOWED_SOURCES.contains(source)) {
            throw new JobParametersInvalidException(
                    "sourceSystem is not supported");
        }

        if (version == null
                || !INPUT_VERSION.matcher(version).matches()) {
            throw new JobParametersInvalidException(
                    "inputVersion is invalid");
        }
    }
}
```

This validation checks **format and allowlist**, not:

- That the input version actually exists.
- That the version's contents are immutable.
- That the caller is authorized for that source.
- That the file matches the schema.
- That the manifest matches actual row counts and totals.

Verify those in API authorization or the preflight step. Never treat a passing regex as proof that the entire input dataset is safe.

### 16.2. Registering the Validator on `JobBuilder`

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job dailyPartnerSettlement(
        JobRepository repository,
        Step validateInputManifest,
        Step loadTransactions,
        Step reconcileTotals,
        Step markResultReady) {

    return new JobBuilder("dailyPartnerSettlement", repository)
            .validator(new SettlementJobParametersValidator())
            .start(validateInputManifest)
            .next(loadTransactions)
            .next(reconcileTotals)
            .next(markResultReady)
            .build();
}
```

The four steps are assumed to be defined separately. This configures a **linear flow**: if a step fails without an explicit recovery transition, the job stops rather than advancing as normal.

Placing `markResultReady` after `reconcileTotals` makes clear that "job finished reading the file" is not the same as "data is ready for downstream."

## 17. Preflight Step: Checking Limits Before Writing Data

A limit like "max 2 million records" is only helpful if enforced before starting an expensive import.

Suppose the system stores a manifest keyed by `inputVersion`:

```java
public record InputManifest(
        String inputVersion,
        String schemaVersion,
        long byteSize,
        long recordCount,
        String checksum
) {
}
```

A manifest validation policy:

```java
public final class InputManifestPolicy {

    public static final long MAX_FILE_BYTES =
            500L * 1024L * 1024L;

    public static final long MAX_RECORDS = 2_000_000L;

    public void validate(
            InputManifest manifest,
            String expectedVersion) {

        if (manifest == null) {
            throw new IllegalStateException("Input manifest missing");
        }

        if (!expectedVersion.equals(manifest.inputVersion())) {
            throw new IllegalStateException(
                    "Input version does not match parameters");
        }

        if (!"v2".equals(manifest.schemaVersion())) {
            throw new IllegalStateException(
                    "Unsupported schema version");
        }

        if (manifest.byteSize() < 0
                || manifest.byteSize() > MAX_FILE_BYTES) {
            throw new IllegalStateException(
                    "Input exceeds allowed byte size");
        }

        if (manifest.recordCount() < 0
                || manifest.recordCount() > MAX_RECORDS) {
            throw new IllegalStateException(
                    "Input exceeds allowed record count");
        }

        if (manifest.checksum() == null
                || manifest.checksum().isBlank()) {
            throw new IllegalStateException(
                    "Input checksum is missing");
        }
    }
}
```

This is a **sample policy**, not built into Spring Batch. Note: a manifest carrying a checksum does not prove the checksum matches actual file bytes; verify against a trusted digest when opening the input.

### 17.1. Preflight Tasklet

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public final class ValidateInputManifestTasklet
        implements Tasklet {

    private final InputManifestRepository repository;
    private final InputManifestPolicy policy;
    private final String inputVersion;

    public ValidateInputManifestTasklet(
            InputManifestRepository repository,
            InputManifestPolicy policy,
            String inputVersion) {

        this.repository = repository;
        this.policy = policy;
        this.inputVersion = inputVersion;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext context) {

        InputManifest manifest =
                repository.findRequired(inputVersion);

        policy.validate(manifest, inputVersion);

        return RepeatStatus.FINISHED;
    }
}
```

`InputManifestRepository` is an assumed domain interface providing `findRequired(String)`; implement it for your storage layer. On an invalid manifest, the tasklet throws and fails preflight before the ingestion step starts.

Never put row-count checks solely at the end of the job and burn resources importing a 100 GB file when the design only supports 500 MiB. Beyond preflight, enforce streaming caps if source metadata is untrusted or mutable.

## 18. Resource Limits and Backpressure

A job is not "stable" merely because it sets `chunk(200)` if it spawns 100 workers each holding multiple connections.

Operational limits might include:

```text
Maximum concurrent executions per source: 1
Maximum worker threads: 4
JDBC pool max connections reserved/shared: per configuration
Database statement timeout: finite
HTTP request timeout: finite
Retry max attempts: per policy
Memory budget: within container limits
Output publishing: blocked before reconciliation
```

Never set hard limits arbitrarily without measuring. A job with the same record count but 10x wider rows or a slower API writer can blow past memory and time budgets.

### 18.1. What Should Happen When Capacity Is Exceeded?

Several options exist—document your choice explicitly:

- **Reject before launch** when breaching a hard limit.
- **Queue with backpressure** if orchestration supports it; never launch hundreds of concurrent executions.
- **Throttle concurrency** when the database or API is the bottleneck.
- **Partition safely** when inputs split cleanly and workers have capacity headroom.
- **Stop cooperatively** when operations decide to halt; `JobOperator.stop` signals stop rather than killing threads instantly.
- **Fail and raise an incident** if the job cannot finish within accepted data/consistency bounds.

Never manually flip status to `STOPPED` or `COMPLETED` in metadata just to "hit SLA." Status must reflect actual framework and data reality.

## 19. Documenting External Dependencies

A job may rely on multiple external systems:

| Dependency | Assumed Condition | Limit / Action |
|---|---|---|
| Object storage | File version exists and reads consistently | Timeouts and checksum; fail if source mutates |
| PostgreSQL | DB has pool capacity and proper transactions | Bounded retry for transient faults |
| Message broker | Delivery may duplicate | Idempotent consumers |
| FX rate API | Single rate snapshot per business date | Pin rate version before import |
| Secret manager | Credentials valid during runtime | Refresh per client policy; never store secrets in context |
| Scheduler | May redeliver or overlap triggers | Job instance identity and orchestration locks |
| Monitoring | Metric endpoint may be temporarily down | Never make business transactions depend on metric emission |

One especially crucial assumption: **"API call timed out on client" does not prove the API failed to process the request.** If a writer calls a payment service or sends side-effecting commands, enforce idempotency keys or explicit reconciliation. Spring Batch checkpoints track progress only within the job's transactional/infrastructure boundaries.

## 20. Recording Decisions in ADRs Instead of Code Comments Alone

An **Architecture Decision Record (ADR)** is a concise document explaining why a design choice was made, in what context, and under what constraints. For batch jobs, an ADR typically covers:

1. ID, title, date, and decision status.
2. Business and system context.
3. Assumptions and supporting evidence.
4. Technical, SLA, and data constraints.
5. Options considered.
6. Decision and rationale.
7. Consequences, trade-offs, and residual risks.
8. Verification plan.
9. Review triggers.
10. Owner and links to tests/monitoring.

### 20.1. Reusable ADR Template

```markdown
# ADR-BATCH-001 — <Decision Title>

Status: Proposed / Accepted / Superseded
Owner: <Responsible Team>
Date: <YYYY-MM-DD>
Job: <jobName>
Related requirements: <link>

## Context
Business problem, input characteristics, and SLAs.

## Assumptions
| ID | Assumption | Evidence | Owner | Verification Method |
|----|------------|----------|-------|---------------------|

## Constraints and invariants
| ID | Condition | Limit / Definition | Action on Violation |
|----|-----------|--------------------|---------------------|

## Options considered
- A: ...
- B: ...

## Decision
Chose option ... because ...

## Consequences
- Pros ...
- Cons ...
- Risks ...

## Validation
- Unit tests ...
- Integration tests ...
- Load tests ...
- Monitoring ...

## Review triggers
- Schema or source changes
- Data exceeds limits
- DB/driver/framework upgrade
- SLA or retry contract changes
```

An ADR does not need to be long. What matters is that **verifiable decisions and change triggers are governed**, rather than scattered across hard-to-find code comments.

### 20.2. Filled-In Sample ADR: Choosing a Staging Snapshot

```markdown
# ADR-BATCH-017 — Reading Immutable Input Versions

Status: Accepted
Job: dailyPartnerSettlement
Owner: Batch Platform + Finance Data
Decision date: 2025-05-12

## Context
Partners may re-send files and jobs may become FAILED mid-run.
Jobs must restart without duplicating or dropping transactions.

## Assumptions
- Every inputVersion points to exact immutable content.
- Storage retains versions at least through the committed recovery window.
- sourceTransactionId is unique within sourceSystem.

## Constraints
- Never read "latest file" during a restart.
- On checksum/version mismatch: fail fast.
- Writer enforces uniqueness by business key.
- Never call payout APIs inside the staging ingestion transaction.

## Options considered
A. Read latest file directly: simple, but content can mutate.
B. Pin object version + checksum: adds preflight, stabilizes restarts.
C. Query live API each time: coupled to paging and upstream churn.

## Decision
Choose B. JobParameters pins inputVersion; reader verifies source.
Step ExecutionContext stores only cursor/checkpoint.

## Consequences
- Incurs versioned storage cost.
- Enables exact reprocessing of any pinned snapshot.
- Must raise error if a version was purged prematurely.

## Validation
- Restart test with identical source: zero omissions or duplicates.
- Mutated-source test: must block continuation.
- Verify storage retention and checksums.
- Dashboard alert on inputVersion unavailable.

## Review triggers
- Storage changes versioning semantics.
- Data volume exceeds snapshot retention capacity.
- Concurrency increases or partitioning strategy changes.
```

All figures and dates in this template are illustrative. In real projects, link ADRs to owners, code versions, tests, and live metrics so future engineers can verify them.

## 21. Assumption Register: Track Ownership and Review Triggers

For critical jobs, one ADR may not suffice to track dozens of evolving assumptions. Maintain an **assumption register**:

| ID | Assumption | Impact If Wrong | Proof Method | Owner | Status |
|---|---|---|---|---|---|
| A-01 | Source snapshot is immutable | Critical | Version + checksum tests | Data Platform | Verified |
| A-02 | `sourceTransactionId` is never reused | Critical | Partner contract + duplicate report | Partner Ops | Needs confirmation |
| A-03 | File ≤ 500 MiB | High | Historical p99 + hard preflight | Batch Team | Verified |
| A-04 | DB pool suffices for 4 workers | Medium | Load test + pool metrics | Infra | Measuring |
| A-05 | Data arrives before 01:00 | Medium | Arrival-time monitoring | Partner Ops | Unstable |

While `A-02` remains **unverified**, do not claim zero-duplicate guarantees. Add a unique constraint as defense-in-depth and explicitly document the residual risk.

### 21.1. Useful Tracking Statuses

- **Proposed:** stated, not yet backed by evidence.
- **Verified:** backed by evidence or passing tests.
- **Violated:** runtime monitoring observed the condition no longer holds.
- **Deprecated:** no longer applicable.
- **Replaced:** superseded by another rule or design.

These are **project-defined assumption governance states**, not Spring Batch `BatchStatus` values.

## 22. Turning Limits into Acceptance Tests

Documentation is trustworthy only when it answers "what proved this?" Include at least three test layers.

### 22.1. Unit Tests for Validators and Policies

Example testing input-size limits:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class InputManifestPolicyTest {

    private final InputManifestPolicy policy =
            new InputManifestPolicy();

    @Test
    void acceptsManifestInsideLimits() {
        InputManifest manifest = new InputManifest(
                "version-1",
                "v2",
                100_000L,
                2_000L,
                "checksum-abc"
        );

        assertDoesNotThrow(() ->
                policy.validate(manifest, "version-1"));
    }

    @Test
    void rejectsExcessiveRecordCount() {
        InputManifest manifest = new InputManifest(
                "version-1",
                "v2",
                100_000L,
                2_000_001L,
                "checksum-abc"
        );

        assertThrows(
                IllegalStateException.class,
                () -> policy.validate(manifest, "version-1")
        );
    }

    @Test
    void rejectsChangedInputVersion() {
        InputManifest manifest = new InputManifest(
                "version-2",
                "v2",
                100_000L,
                2_000L,
                "checksum-abc"
        );

        assertThrows(
                IllegalStateException.class,
                () -> policy.validate(manifest, "version-1")
        );
    }
}
```

This test verifies only **the policy method**. It does not prove the real file matches the checksum or that Spring Batch executes preflight before the writer.

### 22.2. Integration Tests with a Real Job

Use `spring-batch-test`, `@SpringBatchTest`, and `JobLauncherTestUtils` to verify:

- Validator rejects invalid job parameters.
- Preflight fails before any data-writing step runs.
- Reader/writer use the pinned `inputVersion`.
- When the writer fails after two chunks, only committed chunks persist.
- Restarting the same `JobInstance` resumes from the exact checkpoint.
- After restart, business keys are unique and reconciliation passes.
- Downstream steps are skipped when the quality gate fails.
- Issuing stop mid-run ends in an observed state without assuming instant termination.

A test using an in-memory list writer **does not prove JDBC rollback**; for critical consistency, run integration tests against a datasource and transaction manager matching production.

### 22.3. Performance and Failure-Injection Tests

Verify capacity assumptions on representative workloads. Example matrix:

| Test Case | Goal | Results to Record |
|---|---|---|
| 100,000 records | Small baseline | Job/step duration, CPU, heap |
| 1,200,000 records | Reference load | SLA, throughput, lock waits |
| 2,000,000 records | Max accepted limit | No OOM, no DB breakdown |
| 2,000,001 records | Over hard limit | Rejected before import |
| DB timeout | Recovery | Bounded retry, then fail or complete |
| File swapped mid-restart | Data integrity | Refuses to resume on altered version |
| Broker redelivery | Idempotency | Zero duplicate side effects |
| Two schedulers launch together | Concurrency | Zero duplicate writes or wrong instance runs |
| Worker killed | Recovery | Metadata inspected and recovered safely |

Never mark "pass" without running it. Documentation should include **evidence links, environment, test date, commit/version, and measured numbers**. A benchmark on a tiny test instance never proves production will hit the same throughput.

## 23. Runbook: Which Limits Must Operators Know?

Alongside design docs, maintain a concise **runbook** for when assumptions break.

Example:

```text
Job: dailyPartnerSettlement

When input file missing:
  - Do not switch to the latest file automatically.
  - Verify sourceSystem, businessDate, inputVersion.
  - Contact upstream/source owner.
  - Relaunch only with an approved version.

When input exceeds MAX_RECORDS:
  - Do not raise the production limit immediately.
  - Inspect actual volume, schema, and DB capacity.
  - Benchmark/review capacity before changing limits.

When job FAILED after some chunks:
  - Inspect StepExecution and ExecutionContext.
  - Verify committed data by business key.
  - Restart only if inputVersion remains unchanged.

When reconciliation mismatches:
  - Do not emit DataReady.
  - Collect manifest, read/write/skip counts, and DB aggregates.
  - Quarantine or handle per data-quality policy.

When job STARTED too long:
  - Check worker liveness and I/O wait times.
  - JobOperator.stop is a cooperative stop, not a kill.
  - Never manually edit metadata to STOPPED just to silence alerts.
```

Runbooks should also list **dashboard URLs**, where to find `jobExecutionId`, how to pull logs, and incident owners. Never store passwords or tokens inside runbooks.

## 24. When Must Assumptions and Limits Be Updated?

Events that routinely require revisiting the job contract:

- Upstream changes schema, encoding, paging, or duplicate policy.
- Data volume grows past the benchmarked envelope.
- Business shifts from daily batch to near-real-time.
- Adding parallelism/partitioning or changing worker counts.
- Changing database, JDBC driver, transaction manager, or connection pool.
- Adding external API side effects to a writer.
- Upgrading Spring Batch/Spring Boot in ways that alter checkpoint serializers/APIs.
- Changing file/source retention or access permissions.
- Changing SLAs, business-date rules, or timezones.
- Any incident involving lost/duplicate data, crashes, or stuck metadata.

Keep the job contract in **version control**. When updating a constraint, review validation code, tests, alerts, dashboards, runbooks, and restart conditions together. Never update a limit on a wiki while leaving old code in place—nor change code without notifying operations.

### 24.1. Decision Review Flow

```text
New requirement / incident
          |
          v
Identify assumption or limit
          |
          v
Assess data integrity + risk
          |
          v
Evaluate alternatives
          |
          v
Update ADR/job contract
          |
          v
Implement guardrails and tests
          |
          v
Benchmark / failure test
          |
          v
Approve & deploy
          |
          v
Monitor assumption in production
```

When input relies on a partner contract, engineering owners should not unilaterally decide on behalf of business/data owners that a skipped row is acceptable. Data quality authority and technical deployment authority often sit with different teams.

## 25. Common Anti-Patterns

| Anti-Pattern | Why It Is Dangerous | Alternative |
|---|---|---|
| "Job supports large files" | "Large" is unmeasured | Benchmarked rows/bytes/workload envelope |
| "Data is always clean" | Skips schema/quality validation | Input contract and quality gate |
| "No duplicates because partner promised" | Retries and schedulers can redeliver | Business key + unique constraint + audit |
| "Restartable because it uses Spring Batch" | Reader may not checkpoint or input mutates | `ItemStream`, immutable source, restart tests |
| "`FAILED` means nothing was written" | Prior chunks already committed | Reconcile transactions and checkpoints |
| "Exactly once" for HTTP calls in writer | DB rollback never rolls back HTTP | Outbox / idempotency / reconciliation |
| Using a new `run.id` on every error | Creates new `JobInstance`, drops checkpoints | Restart right instance or intentional reprocess |
| Treating `writeCount` as DB row inserts | Upserts/dedup may insert fewer rows | Check affected rows / reconciliation |
| Omitting timezone/cutoff | Runs crossing midnight pick wrong date | Explicit business date and interval |
| "Kill process on timeout" | Metadata stays un-updated | Graceful stop and recovery runbook |
| Raising `chunkSize`/threads unmeasured | Locks, memory, and DB pools saturate | Load test and capacity envelope |
| Blanket `skip(Exception.class)` | Hides data, security, and infra errors | Exception-specific fault policy |
| Testing only the happy path | Misses restart/overlap bugs | Fault injection and concurrency tests |
| Assumptions without owners | Nobody verifies when upstream changes | Assumption register + review triggers |
| Limits documented only in a wiki | Code still accepts oversized inputs | Runtime guards + tests + alerts |
| Missing out-of-scope section | Users assume job handles undesigned work | Explicit goals and exclusions |
| Hand-editing SQL/metadata to "keep going" | Risks lost or duplicate data | Controlled recovery procedures |
| Putting secrets in `JobParameters`/`ExecutionContext` | Long-lived metadata is broadly viewable | Secret manager + least privilege |

## 26. Practice Exercise: Creating a Job Contract and ADR

You are tasked with designing `importDailyTransactions`, processing CSVs from three partners up to 3 million rows/day, writing to PostgreSQL, and triggering reporting once verified.

Complete the following:

1. Write a **job contract** stating goals, out-of-scope, inputs, outputs, and `DataReady` criteria.
2. List at least 10 assumptions categorized across data/schema, time, transactions, restart, concurrency, external dependencies, and security.
3. For each assumption, document existing evidence, owner, impact if wrong, and detection mechanism.
4. Select identifying `JobParameters` and explain why `jobExecutionId` is unsuitable as a business idempotency key.
5. Specify the capacity envelope: file size, row count, item size, concurrency, DB pool, and target duration. Distinguish hard limits from SLOs.
6. Choose an initial chunk size and describe how benchmarks will confirm it rather than guessing from defaults.
7. Design a preflight step validating manifest, source version, schema, and volume caps before writing data.
8. Define a retry/skip policy: which errors retry, which may skip, which fail the whole job, and why.
9. Write a restart contract covering checkpoints, input immutability, and writer idempotency; simulate failure after three chunks.
10. Design reconciliation: how must total inputs, accepted, rejected, duplicates, and monetary sums relate?
11. Define rules for handling two schedulers launching the same business date concurrently.
12. Write an ADR choosing between reading a live API directly vs. pinning an immutable staging snapshot; state residual risks.
13. Write at least three policy unit tests, three transaction/restart integration tests, and three load/failure scenarios.
14. Build a table of unverified assumptions and propose measurement/evidence plans prior to deployment.
15. Write a runbook for oversized inputs, checksum mismatches, and mid-chunk worker kills.
16. Define review triggers when upstream changes schemas, volume doubles, or the app upgrades Spring Batch.

**Review question:** If a job has run smoothly for six months at 100,000 rows/day, can you document "job supports up to 2 million rows" without measuring?

**Answer:** **No.** Six months at 100,000 rows is only evidence within the observed range. A 2-million-row limit must be proven across representative workloads, databases, memory, concurrency, and failure/restart tests. Until measured, record it as an **unverified assumption/target**, not a guaranteed capability.

## 27. References

- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `Job`, `JobInstance`, `JobExecution`, `StepExecution`, and statuses.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobParametersValidator`, restartability, and job definitions.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): commit intervals, transactions, and reader/processor/writer loops.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `ExecutionContext` and checkpoints.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): exception-based retry selection.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip policies and skip limits.
- [Spring Batch Reference — Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html): rollback boundaries in chunks.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): duration and observability metrics.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test` and step/job testing.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction scope and data integration.
- [AWS Prescriptive Guidance — ADR Process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html): documenting and governing architecture decision records.
