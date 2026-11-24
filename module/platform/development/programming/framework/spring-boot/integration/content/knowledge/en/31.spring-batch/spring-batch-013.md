# Distinguishing Business Data from Spring Batch Metadata

In **SPRING_BOOT_INTEGRATION** systems, Spring Boot does more than call HTTP clients, databases, caches, or message brokers—it also processes high-volume data flows: importing CSV invoices, syncing partner catalogs, reconciling payments, exporting reports, or ingesting legacy systems. **Spring Batch** organizes these workloads into **Job**s and **Step**s, tracks execution progress, manages chunk-level transactions, and resumes work after failures.

To design reliable batches, separate two classes of data with very different purposes:

- **Business data:** invoices, orders, customers, monetary amounts, reconciliation statuses, accepted or rejected records. These values are governed by **business rules and data contracts**.
- **Spring Batch metadata:** which Job ran, with which parameters, which attempt succeeded or failed, how many items a Step read/wrote, and checkpoints for resumption. These values serve **technical orchestration, monitoring, and restarts**.

Both layers often live in the same database management system—sometimes even the same database—yet **that does not give them the same owner, lifecycle, or meaning**. Spring Batch manages metadata through **`JobRepository`**; the application owns business data through its repositories, SQL writers, APIs, and consistency policies.

## 1. Running Scenario: Importing Invoices from CSV

Suppose each day the system receives an invoice file from partner A:

~~~csv
sourceInvoiceId,customerId,amountVnd
INV-001,CUS-01,125000
INV-002,CUS-02,99000
INV-003,CUS-03,325000
~~~

Job **`importInvoicesJob`** has a Step named **`invoiceImportStep`**: read each line, validate values, and insert into **`business_invoice`**. The batch processes 100-row chunks and supports restarts after failure.

~~~mermaid
flowchart TD
    SRC["Partner invoice CSV"] --> READER["ItemReader"]
    READER --> PROCESSOR["ItemProcessor: validate/normalize"]
    PROCESSOR --> WRITER["ItemWriter: write business_invoice"]
    WRITER --> DOMAIN[("Business tables: invoices and reconciliation")]
    JR["JobRepository"] <--> META[("BATCH_* metadata tables")]
    JR -. "Job/Step status, counts, checkpoint" .-> READER
    JR -. "Persist progress and errors" .-> WRITER
    DOMAIN --> API["Business APIs and reports"]
    META --> OPS["Job/Step monitoring and restarts"]
~~~

After importing 300 rows, the system may simultaneously hold:

| Storage | Illustrative Value | Question Answered |
| --- | --- | --- |
| **`business_invoice`** | INV-001, CUS-01, 125000 VND | Which invoices exist, for which customer, and for what amount? |
| **`BATCH_JOB_INSTANCE`** | `importInvoicesJob` with identifying parameter set | Which **logical unit of work** is this? |
| **`BATCH_JOB_EXECUTION`** | Execution 712, status COMPLETED | How did attempt 712 finish technically? |
| **`BATCH_STEP_EXECUTION`** | readCount=300, writeCount=300, commitCount=3 (illustrative) | How many items/chunks did the Step process? |
| **`BATCH_STEP_EXECUTION_CONTEXT`** | Reader's current position/progress | Where can the reader resume on restart? |

**The number of items handled by the writer does not necessarily equal newly created business records.** With SQL **`ON CONFLICT DO NOTHING`**, a writer might process 300 items when several already existed in the database. Hence **`writeCount`** is never a reliable proxy for revenue, new invoice counts, or approved invoices.

## 2. Who Owns and Uses Each Data Layer?

| Criterion | Business Data | Spring Batch Metadata |
| --- | --- | --- |
| Semantic owner | Domain services, business rules, and data owners | Spring Batch framework, `JobRepository` |
| Storage | Domain tables/schemas, data warehouses, external partners | Spring Batch metadata tables, typically prefixed **`BATCH_`** |
| Identifiers | `invoiceId`, `orderId`, `customerId`, `sourceBatchId` | `JobInstanceId`, `JobExecutionId`, `StepExecutionId` |
| Correctness | Invoices must be valid, non-duplicate, accurate amounts | Statuses/attempts/progress recorded accurately for orchestration |
| When Job is `FAILED` | Records from committed chunks may still exist | Records `FAILED` execution and latest checkpoint |
| When Job is `COMPLETED` | **Does not prove** all business reconciliation finished | Proves Steps terminated per configured flow and error policies |
| On re-run | May require upserts, dedup, reconciliation, data repairs | Determines whether to restart the same `JobInstance` or create a new one |
| Retention/cleanup | Follows invoice/audit retention and compliance rules | Follows execution-history retention and restart windows |
| Consumers | APIs, reports, reconciliation, peer services | `JobLauncher`, `JobExplorer`, `JobOperator`, ops dashboards |

Design rule: **business data answers "what happened in the business"; batch metadata answers "how did a Job/Step execute."** Both are related, never identical.

### 2.1. Metadata Is Not a Staging Data Store

Never put entire CSVs, lists of a million `invoiceId`s, full HTTP responses, or large domain objects into **`ExecutionContext`**. `ExecutionContext` is restart state serialized for durable persistence; bulky payloads inflate metadata writes, transaction sizes, and class-versioning risks.

When you need pending-approval datasets, staging tables, or rejection tables, create **dedicated business tables** with explicit keys, statuses, lifecycles, and access grants. `JobRepository` does not enforce data quality, invoice-key deduplication, or legally auditable approval/rejection trails.

## 3. Metadata Entities to Understand

Spring Batch models execution hierarchically:

~~~mermaid
flowchart TD
    JOB["Job: importInvoicesJob"] --> INST["JobInstance: Job name + identifying JobParameters"]
    INST --> EXEC1["JobExecution #1: FAILED"]
    INST --> EXEC2["JobExecution #2: COMPLETED (restart)"]
    EXEC1 --> STEP1["StepExecution: invoiceImportStep #1"]
    EXEC2 --> STEP2["StepExecution: invoiceImportStep #2"]
    EXEC1 --> CTX1["Job ExecutionContext"]
    EXEC2 --> CTX2["Job ExecutionContext"]
    STEP1 --> SCTX1["Step ExecutionContext: checkpoint"]
    STEP2 --> SCTX2["Step ExecutionContext: new checkpoint"]
~~~

### 3.1. `Job`, `JobInstance`, and `JobExecution`

**`Job`** defines the processing flow—e.g., ingest invoices, validate, write DB, generate report. The Job name is part of logical identity.

**`JobInstance`** identifies **one logical processing run** of a Job based on:

\[
\text{JobInstance} = (\text{jobName},\ \text{identifying JobParameters})
\]

**`JobExecution`** is **one attempt to execute** a `JobInstance`. When the first attempt fails, a restart creates a **new `JobExecution`** belonging to **the same `JobInstance`**. Once a `JobInstance` is `COMPLETED`, re-running with the same identifying parameters is normally rejected by Spring Batch rather than spawning an identical execution.

**`JobParameters`** are values supplied at launch, for instance:

- **`inputFile`**: input file path.
- **`sourceBatchId`**: partner-assigned batch identifier.
- **`requestedBy`**: user/channel initiating the run, for auditing only.

Only parameters marked **identifying** contribute to `JobInstance` identity. **`requestedBy`** can be non-identifying, since changing who clicked "run" should not turn the same batch into a new logical job.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/invoices/partner-a-2026-11-21.csv", true)
        .addString("sourceBatchId", "PARTNER-A-2026-11-21", true)
        .addString("requestedBy", "operations", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importInvoicesJob, parameters);
~~~

This uses the Spring Batch **5+** API: the trailing boolean in `addString` specifies identifying vs. non-identifying. To **restart**, pass the exact same identifying parameters for a restart-eligible `JobInstance`. Changing **`sourceBatchId`**, changing the file path, or incrementing an identifying `run.id` via **`RunIdIncrementer`** spawns a **different `JobInstance`**—a fresh logical run, **not a restart of the prior attempt**.

Never make random timestamps or fresh requestIds default identifying parameters on batch retries: doing so breaks Spring Batch's link across attempts of the same logical work. Conversely, when a genuine new batch arrives from the business, assign a fresh `sourceBatchId` to distinguish it.

### 3.2. `StepExecution` and Technical Counters

A Job can contain multiple Steps, such as **download**, **validate**, **import**, and **publishResult**. **`StepExecution`** records the status of **one Step run** along with metrics:

- **`readCount`:** items emitted by the reader for processing.
- **`filterCount`:** items filtered out by the processor.
- **`writeCount`:** items passed to the writer.
- **`readSkipCount`, `processSkipCount`, `writeSkipCount`:** items skipped under fault-tolerance policies.
- **`commitCount`, `rollbackCount`:** transaction/chunk commits and rollbacks.
- **`BatchStatus`, `ExitStatus`, `startTime`, `endTime`:** technical Step status and timing.

Even **`COMPLETED + writeCount=300`** does not prove 300 new invoices were inserted: the writer may upsert, ignore duplicates, call external APIs, or update multiple tables. Similarly, if the processor filters 20 records leaving **`readCount=300`** and **`writeCount=280`**, those 20 rows are not necessarily invalid—filtering can be a legitimate business rule.

**`BatchStatus`** is the framework-managed execution status, typically **`STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED`, `UNKNOWN`**. **`ExitStatus`** represents step/flow transition results and can be customized. Never use either status as payment status, reconciliation status, or invoice approval status.

### 3.3. `JobExecutionContext` and `StepExecutionContext`

**`ExecutionContext`** is the key-value store used by the framework or Steps to persist restart state:

| Scope | Example Data | Purpose |
| --- | --- | --- |
| **Job `ExecutionContext`** | Selected partner code, snapshot name shared across Steps | Pass durable state between Steps of a `JobInstance` when appropriate |
| **Step `ExecutionContext`** | Reader position, line count read, cursor/checkpoint | Recover an individual Step after stopping or failing |

`ExecutionContext` is **persisted durably inside metadata**, unlike transient fields in a bean's RAM. Spring Batch automatically maintains state for **`ItemStream`** components like `FlatFileItemReader` when properly registered and **`saveState`** is enabled.

Guidelines:

- Store only **small, stable state needed for restarts**: offsets, `lastProcessedKey`, snapshot names, technical workflow flags.
- Never store sensitive data (tokens, passwords, card details), large domain objects, or raw responses.
- When managing offsets manually, update them strictly at commit boundaries; wrong timing causes gaps or duplicate processing.
- Changing key names, serializer classes, or state structure across app releases can break restarts of older executions.
- Never treat **`StepExecutionContext`** as the source of truth for business state. Written and reconciled invoices must be determined from business records.

## 4. Where Does `JobRepository` Store Metadata?

With a **JDBC `JobRepository`**, Spring Batch reads/writes dedicated metadata tables. Exact names and columns depend on installed version/schema, yet the core tables are:

| Table | Contents |
| --- | --- |
| **`BATCH_JOB_INSTANCE`** | Job instance ID, job name, and job key |
| **`BATCH_JOB_EXECUTION`** | Each execution of a `JobInstance`: timestamps, status, exit result |
| **`BATCH_JOB_EXECUTION_PARAMS`** | `JobParameters` per `JobExecution` and identifying flags |
| **`BATCH_STEP_EXECUTION`** | Step executions, read/write/skip/commit/rollback counters |
| **`BATCH_JOB_EXECUTION_CONTEXT`** | Job-scoped `ExecutionContext` |
| **`BATCH_STEP_EXECUTION_CONTEXT`** | Step-scoped `ExecutionContext` |
| **`BATCH_JOB_SEQ`, `BATCH_JOB_EXECUTION_SEQ`, `BATCH_STEP_EXECUTION_SEQ`** | Database-dependent sequences/ID generators |

These tables back **`JobRepository`** and read/control APIs such as **`JobExplorer`** and **`JobOperator`**. Normally **never manually edit** metadata rows to mark success, skip Steps, or tweak `readCount`: doing so corrupts restart consistency. Use Spring Batch APIs and controlled operational procedures.

Example observation query (table/column names per standard schema):

~~~sql
SELECT ji.JOB_NAME,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE,
       je.START_TIME,
       je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importInvoicesJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
~~~

This query answers **how the Job ran**, not which invoices were accurately persisted. To inspect imported invoices, query business tables by **`sourceBatchId`** or **`importRunId`** with proper domain constraints.

### 4.1. Initializing Metadata Schema

In Spring Boot using a JDBC `JobRepository`, development environments may enable automatic schema creation:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: always  # suitable only for controlled dev/test environments
    job:
      enabled: false             # e.g., do not auto-run Job at app startup
~~~

In production, manage schema changes via **Flyway/Liquibase** or equivalent migrations using scripts **matching your exact Spring Batch version and database engine**, taking backups before upgrades. Separate DDL privileges from the runtime Job account where appropriate. Having **`BATCH_*`** tables does not create invoice tables; business schemas require their own migrations and retention policies.

If an application uses multiple DataSources/transaction managers, explicitly configure **`JobRepository`'s `DataSource`**, **`ItemWriter`'s `DataSource`**, and the Step's transaction manager. Both framework and business data using PostgreSQL **does not prove** they share a single transaction if wired to separate databases or connection managers.

## 5. Designing Business Tables and Deduplication

PostgreSQL example for invoice data:

~~~sql
CREATE TABLE business_invoice (
    id                  bigserial PRIMARY KEY,
    source_system       varchar(40) NOT NULL,
    source_invoice_id   varchar(100) NOT NULL,
    customer_id         varchar(100) NOT NULL,
    amount_vnd          numeric(18,2) NOT NULL,
    imported_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT business_invoice_amount_positive CHECK (amount_vnd > 0),
    CONSTRAINT business_invoice_source_unique
        UNIQUE (source_system, source_invoice_id)
);
~~~

**`source_system + source_invoice_id`** exemplifies a **business deduplication key**. It is completely distinct from **`JobExecutionId`**: the same invoice can appear across two files or two imports, yet re-running a Job must never create duplicate invoices. Choose dedup keys from the source contract; if `invoiceId` is unique only per partner, include `source_system`.

When users must monitor and approve import batches, add a business run table:

~~~sql
CREATE TABLE invoice_import_run (
    import_id           uuid PRIMARY KEY,
    source_batch_id     varchar(120) NOT NULL UNIQUE,
    business_status     varchar(24) NOT NULL,
    accepted_count      bigint NOT NULL DEFAULT 0,
    rejected_count      bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz
);
~~~

**`invoice_import_run.business_status`** may be **`RECEIVED`, `VALIDATING`, `WAITING_APPROVAL`, `APPROVED`, `REJECTED`, `PUBLISHED`** per product rules. This status **differs** from `BatchStatus` **`COMPLETED`/`FAILED`**. An import Job may be `COMPLETED` while the batch sits in **`WAITING_APPROVAL`**; that is not a contradiction, just two separate lifecycles.

If an existing invoice ID returns with a different monetary amount, **`ON CONFLICT DO NOTHING`** silently drops a dangerous discrepancy. Compare incoming payloads against persisted rows and write discrepancies to a reconciliation/business-error table; unique constraints stop duplicate inserts, not semantic mismatches.

## 6. Spring Batch 5+ Job/Step and Business Writer Configuration Example

The example below highlights separation of concerns: **`JobRepository`** handles metadata; **`ItemReader`/`ItemWriter`** read CSV and write the invoice table. It assumes Spring Batch JDBC metadata, a PostgreSQL DataSource, and an appropriate transaction manager are configured. Java imports are omitted for clarity and each type can live in its own file.

### 6.1. Input DTO

~~~java
public record InvoiceRow(
        String sourceInvoiceId,
        String customerId,
        BigDecimal amountVnd) {}
~~~

### 6.2. Checkpoint-Capable Reader

~~~java
@Bean
@StepScope
FlatFileItemReader<InvoiceRow> invoiceReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("sourceInvoiceId", "customerId", "amountVnd");

    DefaultLineMapper<InvoiceRow> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new InvoiceRow(
            fields.readString("sourceInvoiceId"),
            fields.readString("customerId"),
            fields.readBigDecimal("amountVnd")));

    return new FlatFileItemReaderBuilder<InvoiceRow>()
            .name("invoiceReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .lineMapper(mapper)
            .saveState(true)
            .build();
}
~~~

**`@StepScope`** instantiates the reader within a `StepExecution` context and resolves **`inputFile`** from `JobParameters` at runtime rather than application startup. The reader has a stable name and **`saveState(true)`** to persist read positions into Step `ExecutionContext` via **`ItemStream`** when properly registered with the Step.

Checkpoints remain valid only if **the input file keeps identical content** between the failed run and restart. If a partner overwrites the file under the same name, saved line counts point to the wrong lines. Use immutable file snapshots paired with `sourceBatchId`/checksums; persist checksums in a business/audit table and verify before restarting.

### 6.3. Writer Persisting `business_invoice`

~~~java
@Bean
JdbcBatchItemWriter<InvoiceRow> invoiceWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<InvoiceRow>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO business_invoice
                        (source_system, source_invoice_id, customer_id, amount_vnd)
                    VALUES
                        (:sourceSystem, :invoiceId, :customerId, :amountVnd)
                    ON CONFLICT (source_system, source_invoice_id)
                    DO NOTHING
                    """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("sourceSystem", "partner-a")
                            .addValue("invoiceId", row.sourceInvoiceId())
                            .addValue("customerId", row.customerId())
                            .addValue("amountVnd", row.amountVnd()))
            .assertUpdates(false)
            .build();
}
~~~

**`ON CONFLICT DO NOTHING`** is PostgreSQL syntax preventing duplicate rows when replaying the same `invoiceId`; **`assertUpdates(false)`** permits inserts affecting zero rows. This is a minimal deduplication-key example without reconciliation for changed invoice amounts.

### 6.4. Job and Chunk Step

~~~java
@Bean
Step invoiceImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<InvoiceRow> invoiceReader,
        JdbcBatchItemWriter<InvoiceRow> invoiceWriter) {

    return new StepBuilder("invoiceImportStep", jobRepository)
            .<InvoiceRow, InvoiceRow>chunk(100, transactionManager)
            .reader(invoiceReader)
            .processor(row -> {
                if (row.amountVnd() == null ||
                        row.amountVnd().signum() <= 0) {
                    throw new IllegalArgumentException(
                            "Invalid amount for " + row.sourceInvoiceId());
                }
                return row;
            })
            .writer(invoiceWriter)
            .build();
}

@Bean
Job importInvoicesJob(JobRepository jobRepository,
                      Step invoiceImportStep) {
    return new JobBuilder("importInvoicesJob", jobRepository)
            .start(invoiceImportStep)
            .build();
}
~~~

This code uses **`JobBuilder`** and **`StepBuilder`** taking **`JobRepository`**, matching **Spring Batch 5** conventions. With chunk size 100, the framework loops **`read → process → write`** over batches within the Step's transaction boundary. When an exception occurs without skip/retry policies, the active transaction rolls back and the Step/Job transition to FAILED; data committed by prior chunks stays intact.

To skip malformed rows or retry transient errors automatically, configure **`faultTolerant` and skip/retry policies** matching error types and thresholds, plus a business error table/log when rejection reasons must be preserved. Never catch exceptions inside a processor and silently return null: **`null` means filter**, omitting the row silently and potentially letting the Job reach COMPLETED with missing data.

> **Guarantee boundary:** when `JobRepository` and `ItemWriter` share **the exact same database/transaction manager** and enlist properly in chunk transactions, data commits and metadata checkpoints synchronize locally. If metadata sits in database A while invoices sit in database B, or the Step calls HTTP/brokers outside the transaction, no cross-system atomicity exists. Use explicit idempotency and reconciliation rather than treating checkpoints as end-to-end exactly-once guarantees.

## 7. What Happens When a Job Fails Mid-Chunks?

Suppose a file has 250 invoices and chunk size is 100:

~~~mermaid
sequenceDiagram
    participant B as Spring Batch Step
    participant DB as Business DB
    participant JR as JobRepository
    B->>DB: Chunk 1: write items 1..100
    B->>JR: Update StepExecution/ExecutionContext
    Note over DB,JR: Commit chunk 1
    B->>DB: Chunk 2: write items 101..200
    B->>JR: Update checkpoint
    Note over DB,JR: Commit chunk 2
    B->>DB: Chunk 3: write items 201..250
    Note over B: Error at item 230, chunk 3 rolls back
    B->>JR: Persist FAILED status
    Note over DB: First two chunks remain committed
    B->>JR: Restart with same identifying JobParameters
    JR-->>B: Restore reader state from checkpoint
    B->>DB: Process remaining portion with idempotent writes
~~~

When all components join transactions properly and the reader preserves stable restart state, the next run resumes from the latest durable checkpoint. **Restarts do not** necessarily reprocess the entire file, nor do all readers automatically restore position. State and execution order depend on the reader, processor, transaction manager, and whether source data stayed immutable.

| Milestone | Business Data | Metadata |
| --- | --- | --- |
| Chunks 1 and 2 commit | ~200 invoices written | `StepExecution` updates counters and checkpoint |
| Chunk 3 fails before commit | Changes in chunk 3 roll back (if writer shares transaction) | Step/Job recorded as FAILED |
| Restart same `JobInstance` | Two committed chunks are not duplicated | Creates new `JobExecution`, applies recoverable checkpoint |
| Restart succeeds | Remaining portion written; results reconciled | New `JobExecution` reaches COMPLETED |

Distinguish **SQL rollback of a single chunk** from **rolling back an entire Job**. A multi-chunk batch **is not one giant transaction wrapping all data**. Therefore, post-failure data handling is a key design decision.

### 7.1. When Checkpoints and Business Commits Diverge

If business data and `JobRepository` do not share a transaction, two gaps arise:

1. **Business data committed before checkpoint persisted:** on restart, some items may replay. Unique keys, upserts, and idempotent writers protect against duplicates.
2. **Checkpoint advanced beyond committed business data:** if architecture/configuration lets metadata commit while external business side effects did not persist, restarts can skip data. Design transactions, commit ordering, and reconciliation to prevent this window.

For HTTP or message broker side effects, even if the Step transaction rolls back, the external call **may already have succeeded**. Use business idempotency keys and, when DB updates must emit events, consider a **Transactional Outbox**. Never treat **`JobRepository`** as a distributed transaction coordinator.

## 8. Restart vs. Rerun, Retry, and Reprocess

| Action | Explanation | Constraints |
| --- | --- | --- |
| **Restart** | Re-run **the same `JobInstance`** after failure/stop, typically via a **new `JobExecution`** | Identifying `JobParameters` unchanged, Job restartable, valid status, recoverable state |
| **Rerun as new instance** | Spawn a new `JobInstance` for another batch or intentional re-run | Different identifying parameters; requires duplicate data controls |
| **In-Step Retry** | Re-attempt an item/chunk on transient failure | Fault-tolerant policy, retry limits, transaction semantics |
| **Business Reprocess** | Intentionally re-read data to correct or reconcile | Uses domain workflows and update rules; never just edit `BATCH_*` |

A **`COMPLETED` `JobInstance`** normally cannot run again with the same identifying parameters. When you genuinely must **reprocess a completed batch**, model it as a controlled business workflow: version the batch, record the reprocess reason, protect historical rows, and define which records update. Never delete metadata or flip statuses to FAILED to force Batch re-runs.

Similarly, **`RunIdIncrementer`** works well when every launch intentionally creates a fresh `JobInstance`, yet is hazardous if attached to "retry the same file." Batch then loses track of the existing `JobInstance`, leaving business idempotency solely responsible for data integrity.

## 9. Where Do Staging, Rejects, and Audits Belong?

A real ingestion pipeline often persists several datasets alongside the primary invoice table:

| Need | Where to Store | Why |
| --- | --- | --- |
| Valid invoices | **`business_invoice`** | Domain source of truth |
| Unnormalized data awaiting validation | **`invoice_staging`** or object storage | Explicit contracts, retention, and replayability |
| Malformed or rejected rows | **`invoice_reject`** with `sourceBatchId`/`lineNumber`/`reasonCode` | Enables data repair and reconciliation |
| Batch approval status | **`invoice_import_run`** | Business workflow independent of technical Job status |
| Reader/file checkpoint position | **Step `ExecutionContext`** | Supports technical restarts |
| Total read/write/skip counts and Step errors | **`BATCH_STEP_EXECUTION`** | Execution monitoring |
| External integration call traces | Dedicated business audit/outbox/integration logs | Tracks side effects and integration contracts |

**`ExecutionContext` must never store full payloads of rejected rows.** Save only a small checkpoint like `lastProcessedLine` and point rejections to a reject table. To report errors back to partners, the system needs line numbers, source identifiers, error codes, and resolution status—all business concerns rather than generic `readSkipCount` numbers.

A Job might process 1,000 lines, skip 20 lines, and report COMPLETED because `skipLimit` allowed it. Yet commercially, that batch might be **`PARTIAL_ACCEPTED`** or **`WAITING_REVIEW`**. Product outcomes must rest on domain checks and business rules, not `BatchStatus` alone.

## 10. `JobParameters` and `ExecutionContext` Do Not Replace Domain Identity

Keep three key sets distinct:

1. **`JobInstance` identity key:** `jobName` + identifying `JobParameters`, telling Batch whether to restart or create a new instance.
2. **Checkpoint key:** `ExecutionContext` data allowing readers/processors to restore technical progress.
3. **Business deduplication key:** e.g., **`(source_system, source_invoice_id)`**, preventing an invoice from duplicating across multiple batches.

Example of an existing invoice reappearing:

~~~text
Partner A sends invoice INV-001
    |
    +-- JobInstance sourceBatchId=2026-11-21 --> writes business_invoice
    |
    +-- JobInstance sourceBatchId=2026-11-22 --> sees INV-001 again
                                              |
                                              +-- Unique key resolves duplicate
~~~

Two valid `JobInstance`s can encounter the same business key. `JobRepository` does not detect that it is a duplicate invoice. Conversely, one `JobInstance` processes many invoices; never use `JobExecutionId` as a business `invoiceId`.

Especially with **paginated APIs** or **database paging readers**, checkpoints by **page/item count** drift if the source mutates while the Job runs. Prefer snapshots, stable key ordering, watermarks, or keyset pagination where the source contract supports them, and test restarts while new inserts/updates hit the source.

## 11. Choosing Database and Transaction Manager Topology

Three common layouts:

| Layout | Advantages | Limits Requiring Design |
| --- | --- | --- |
| **Same DB, same transaction manager** for metadata and business writer | Easily coordinates chunk commits and checkpoints with minimal config | Enforce schema/permission separation and contention limits; does not cover non-DB side effects |
| **Same RDBMS, separate DBs/schemas/connections** | Operational partitioning and access isolation | Not automatically in one transaction; verify datasource/manager wiring |
| **Separate metadata DB and business DB** | Administrative isolation, controlled `JobRepository` sharing | Requires dedup and reconciliation when one commits while the other fails |

With a JDBC **`JobRepository`**, Batch needs transactions to update metadata. The **Step** also needs a **`PlatformTransactionManager`** for chunks. If the two use different managers, never assume `@Transactional` on a service rolls back both together.

Another nuance when combining **Spring Batch with message brokers**: metadata persists `JobExecution`/`StepExecution` in the DB, yet **acking a RabbitMQ message** or **publishing a Kafka event** does not automatically join that transaction. Adapters need their own ack, retry, idempotency, and uncertain-outcome rules. Similarly, if an `ItemReader` calls HTTP and the source API lacks replay support, checkpoints cannot recover lost HTTP responses.

## 12. Operating Metadata Properly

### 12.1. Observation and Control APIs

| Spring Batch API | Purpose |
| --- | --- |
| **`JobLauncher`** | Launch a Job with `JobParameters` |
| **`JobRepository`** | Create and update `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` |
| **`JobExplorer`** | Read Job/Step metadata via read-only APIs |
| **`JobOperator`** | Operational controls such as start/stop/restart per supported APIs and config |

Never manually edit fields like **`STATUS`**, **`VERSION`**, **`READ_COUNT`**, or serialized `ExecutionContext` payloads to "fix" a failed Job. These columns carry interrelated invariants; manual edits trigger optimistic locking errors or resume Batch from corrupt checkpoints.

### 12.2. Retention and Upgrades

Keep metadata at least as long as **restarts**, failure investigations, or technical audits remain active. Purging execution history prematurely erases restart checkpoints and incident traceability. Conversely, retaining metadata forever bloats **`BATCH_*`** tables and slows queries and backups.

Retention policies should consider active Jobs, `FAILED` Jobs still eligible for restart, aged `COMPLETED` Jobs, foreign keys across tables, audit mandates, backup/restore alignment, and dashboard dependencies. Cleanup jobs must follow strict rules through proper mechanisms—never blindly delete `BATCH_JOB_INSTANCE` rows ahead of dependent executions.

When upgrading Spring Batch, verify both **schema migrations** and **deserialization compatibility for legacy `ExecutionContext`s**. Never rename tables, alter column types, or swap serializers without testing restartability of in-flight executions.

### 12.3. Data Security and Access Control

**`JobParameters`** and **`ExecutionContext`** persist into the metadata database. Therefore:

- Never store passwords, API keys, access tokens, or sensitive credentials inside `JobParameters`.
- Pass safe reference keys/secret references instead of embedding credentials in metadata.
- Never dump full business payloads, PII-laden exceptions, or raw file copies into `ExecutionContext`.
- Restrict metadata read/write grants to appropriate operational accounts, separating access from business reporting where needed.

## 13. Testing the Distinction Between Metadata and Business Data

Tests must inspect both **`BATCH_*`** and business tables to avoid false confidence from `COMPLETED` status alone.

| Scenario | What to Verify |
| --- | --- |
| Job imports valid file | `business_invoice` holds exact invoices; `JobExecution` and `StepExecution` finish cleanly |
| Processor filters items per rule | `filterCount` increments; business tables reflect filter rules |
| One bad row with skip enabled | Read/skip/write counts accurate; business reject record written if contract requires |
| Failure in third chunk | First two chunks preserve committed data; failing chunk rolls back when sharing tx; metadata shows FAILED |
| Restart with same identifying parameters | `JobInstance` stays unchanged, new `JobExecution` created; zero duplicate records |
| Launch same params after Job `COMPLETED` | Batch blocks re-running the completed `JobInstance` per restart rules |
| New `JobInstance` with file containing old invoice | Business unique key/upsert blocks duplicate record |
| File modified after Step `FAILED` | Blocked by checksum/snapshot policy or recognized as reprocess |
| Separate metadata and business DBs, simulated crash | Retry/reconciliation prevents gaps or duplicate side effects |
| App version upgrade between executions | Legacy `ExecutionContext` still readable or clean recovery procedure executes |

In Spring Boot, **Spring Batch Test** supports Job/Step testing and `StepExecution` assertions; **Testcontainers** provides real PostgreSQL or brokers to test true transaction boundaries. When using PostgreSQL **`ON CONFLICT`**, never test writers solely against an in-memory database with a different SQL dialect and extrapolate to production.

### Example Measurable Acceptance Criteria

Given a file of 250 valid invoices and chunk size 100:

1. After two chunks succeed, simulate a failure during chunk 3. Under shared transactions, data committed by the first two chunks stays persisted.
2. The first `JobExecution` records FAILED; steps and checkpoints are inspectable via `JobRepository`.
3. Restart with **the exact same** identifying `JobParameters` against the immutable input. Spring Batch creates a new `JobExecution` under the prior `JobInstance` and the reader resumes from checkpoint.
4. On completion, **`business_invoice` contains exactly 250 unique invoices** and the new `JobExecution` is COMPLETED; verify new business rows via domain SQL queries rather than inferring from `writeCount`.
5. Launch a **new** `JobInstance` containing already-persisted invoice INV-001: unique keys or reconciliation policies handle it cleanly without creating a second invoice.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "Job COMPLETED means all invoices are approved." | COMPLETED is a **Step execution** outcome; business approval is a separate state. |
| "`writeCount=500` means the DB just added 500 rows." | `writeCount` measures items passed to the writer, not necessarily new inserts or successful external side effects. |
| "`ExecutionContext` is where pending invoices are stored." | `ExecutionContext` holds tiny state/checkpoints; store invoices in staging/business tables. |
| "Change `run.id` to restart a failed Job." | Changing an identifying parameter creates a new `JobInstance`; restarts must preserve the old identity. |
| "Batch has checkpoints so it never writes duplicates." | Retries/restarts can replay items; unique keys/idempotent writers remain a business responsibility. |
| "`@Transactional` covers HTTP and RabbitMQ too." | Transactions cover only resources enlisted with the transaction manager; external side effects need dedicated mechanisms. |
| "Delete `BATCH_` rows for a clean re-run." | Destroys restart/audit history and corrupts metadata integrity. |
| "`JobRepository` already exists so no `import_run` business table is needed." | When users need to approve, reconcile, or track batches by business status, a dedicated domain model is required. |

## 15. Pre-Production Checklist

- [ ] Clearly separated **business tables**, **metadata tables**, staging/reject/audit stores, and ownership of each.
- [ ] `JobParameters` use stable identifying keys; **restart** vs. **new instance/reprocess** clearly defined.
- [ ] Readers implement sound checkpoint strategies over immutable or versioned/checksummed input snapshots.
- [ ] Writers enforce business keys, validation, and idempotency; never rely on `writeCount` as a domain metric.
- [ ] Step transaction manager and `JobRepository` DataSource intentionally configured; commit boundaries understood.
- [ ] HTTP/broker side effects backed by retries, idempotency or outbox/inbox, and reconciliation.
- [ ] Malformed records routed to domain reject/audit stores when needed, never stuffed into `ExecutionContext`.
- [ ] Metrics and dashboards track both **technical progress** and **business outcomes**.
- [ ] Backup, schema migration, retention, and security plans cover `BATCH_*` tables.
- [ ] Tests verify crash/restart, replay, duplicates, mutated inputs, skip/rollback, and version upgrades.

**Core principle:** **Spring Batch manages how a Job executes and recovers from failures; the application manages the meaning and correctness of the data processed by the Job.** `JobRepository` metadata is vital for restarts and operations, yet **never replaces domain models, deduplication keys, business audits, or cross-system transaction design**.

### Further Reading

- [Spring Batch Reference — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch Reference — JobParameters](https://docs.spring.io/spring-batch/reference/job/running.html)
