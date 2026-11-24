# Checkpoints, ExecutionContext, and Job Restarts

## 1. Why Does a Batch Job Need Checkpoints?

In the **Spring Boot Integration** module, not every integration flow requires instant responses. Some workloads must ingest millions of CSV rows, sync data from partner APIs, reconcile transactions, rebuild read models, or transfer data between databases and brokers. These tasks can run for minutes or hours, so you must plan ahead for application shutdowns, database timeouts, malformed records, or infrastructure restarts mid-run.

For example, an `importPaymentsJob` reads a 100,000-line CSV file and writes reconciliation records to PostgreSQL in batches of 100 rows:

- If the process dies after 64,700 committed rows, we do not want to blindly re-run all 64,700 rows.
- If an error occurs while writing rows 64,701–64,800, that batch must have deterministic rollback/retry behavior.
- When the job restarts, it must know where **the same logical run** stopped, which steps already finished, and what durably saved state it can trust.

**Spring Batch** addresses this through `JobRepository`, `JobExecution`/`StepExecution` metadata, `ExecutionContext`, and transaction-aligned checkpoints. Keep in mind that **checkpoints only recover progress**; preventing duplicate side effects and maintaining consistency across two systems still require idempotency, transactions, and often a transactional outbox.

~~~mermaid
flowchart LR
    A["Immutable CSV input"] --> B["ItemReader"]
    B --> C["ItemProcessor"]
    C --> D["ItemWriter"]
    D --> E[("PostgreSQL business data")]
    F[("JobRepository metadata")] <-->|"Job/Step status + ExecutionContext"| B
    F -. "Checkpoint per committed chunk" .-> E
~~~

## 2. Understanding JobInstance, JobExecution, StepExecution, and JobRepository

These concepts are closely related yet **never interchangeable**:

| Component | Meaning | Role on Restart |
| --- | --- | --- |
| `Job` | Defines the flow of `Step`s to run. | The same job definition can process many business batches. |
| `JobParameters` | Arguments for a run; some are **identifying**, others are not. | Identifying parameters plus the job name define a `JobInstance`. |
| `JobInstance` | One **logical** execution of a job for a set of identifying parameters. | Restarts continue **the same JobInstance** when eligible. |
| `JobExecution` | One **execution attempt** of a JobInstance, with its own timestamps, status, and errors. | Each restart normally creates a new JobExecution. |
| `StepExecution` | One execution attempt of a step, holding status and read/write/skip/commit/rollback counts. | Spring Batch uses metadata to determine which steps need re-running. |
| `ExecutionContext` | Key-value map persisted by the framework for a job or step. | Stores read positions and state needed to resume. |
| `JobRepository` | Component persisting/reading batch metadata, usually via JDBC in a database. | Reference point for restart state across processes. |

**Key identification formula**:

~~~text
JobInstance = jobName + identifying JobParameters

JobInstance 1
  ├── JobExecution #101: FAILED
  │     └── StepExecution importStep #501: FAILED
  └── JobExecution #102: COMPLETED (restart)
        └── StepExecution importStep #502: COMPLETED
~~~

In Spring Batch 5.x, JDBC metadata typically resides in `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT`, and `BATCH_STEP_EXECUTION_CONTEXT`. Never edit metadata tables directly to "force" a re-run unless following an operational runbook with full awareness of consequences; use `JobLauncher`, `JobOperator`, and proper administrative tools.

### 2.1. Restart vs. Running a New JobInstance

Suppose a job uses `businessDate=2026-11-21` and `sourceId=bank-A-20261121` as identifying parameters:

- First run fails: `JobExecution #101 = FAILED`.
- Re-running with **the same job name and same identifying parameters** after resolving the error: the framework creates a new JobExecution **under the same JobInstance** and restores state.
- Changing `sourceId` or adding a new identifying parameter like `run.id=2`: creates a **different JobInstance**, normally starting from scratch rather than restarting.
- Re-launching a `COMPLETED` JobInstance is normally rejected with `JobInstanceAlreadyCompleteException`, unless step/lifecycle policies explicitly configure otherwise.

This explains why using `RunIdIncrementer` or adding a fresh timestamp to identifying parameters **on every retry** defeats resumption: the framework treats it as a brand-new batch. When processing a genuine new version of data, set a meaningful version/source ID as an identifying parameter intentionally.

## 3. How Do Checkpoints Work in Chunk-Oriented Processing?

In a chunk-oriented `Step`:

1. `ItemReader` reads items one by one.
2. `ItemProcessor` transforms/validates (returning `null` to filter).
3. `ItemWriter` writes a `Chunk` of processed items.
4. The chunk transaction commits; step metadata and `ExecutionContext` update at the configured checkpoint boundary.
5. On error before commit, changes **belonging to that transaction** roll back; on restart, the reader can resume from the previous checkpoint.

~~~mermaid
sequenceDiagram
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant DB as Database
    participant Repo as JobRepository
    Note over R,Repo: Chunk size = 100
    loop Read up to 100 items
        R->>P: read + process
    end
    P->>W: Processed chunk
    W->>DB: Write data inside transaction
    R->>Repo: ItemStream.update(ExecutionContext)
    Repo->>Repo: Save StepExecution/ExecutionContext
    Note over DB,Repo: Commit per transaction manager
    DB-->>W: Transaction commits
    Note over R,Repo: Checkpoint durable if commit succeeds
~~~

**A checkpoint does not necessarily equal the raw source line count.** `readCount`, `writeCount`, and `filterCount` can diverge, especially when processors filter records or skips/retries occur. Readers can persist **read position** (item count, page, cursor key...), while writers track written counts. With chunk size 100, checkpoints typically occur per chunk commit, though specifics depend on item streams, readers, transaction managers, and fault-tolerance policies.

### 3.1. Crash Scenarios During Chunk Processing

Suppose 10 chunks of 100 lines each have committed:

| Failure Timing | Expected Durable Data | On Restart |
| --- | --- | --- |
| After chunk 10 commits cleanly | 1,000 rows and checkpoint past chunk 10. | Resumes near row 1,001 per reader state. |
| During chunk 11, before commit | 1,000 rows; JDBC writes from chunk 11 in the transaction must roll back. | Normally re-reads chunk 11 items. |
| After an external target applied the effect, before checkpoint commit | External side effect may already have happened. | May call target again → requires idempotency. |
| `JobRepository` uses a different DB from writer transaction | Checkpoints and business data may commit out of sync. | Requires reconciliation design; never assume atomicity. |

"Normally" is intentional: exact resumption still depends on **whether the input is immutable**, whether `saveState` is enabled on the reader, when state persists, and whether changes actually share **a single transaction**.

## 4. `ExecutionContext`: State That Survives Restarts

`ExecutionContext` is a state map serialized and persisted by the framework inside `JobRepository`. There are **two independent levels**:

| Level | How to Access | When Appropriate |
| --- | --- | --- |
| **Step `ExecutionContext`** | `stepExecution.getExecutionContext()` | Cursor positions, file offsets, pages, reader/writer state specific to that step. |
| **Job `ExecutionContext`** | `jobExecution.getExecutionContext()` | Data shared across multiple steps of the same JobExecution/JobInstance, e.g., verified file ID. |

Step context normally persists with the step's checkpoints. Job context normally persists at step boundaries; **never assume writing a new value into the job context becomes durable immediately at arbitrary points inside a chunk**.

Example reading/updating a Step `ExecutionContext` value from a component with access to `StepExecution`:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

// Always use a namespaced key to avoid colliding with framework keys.
long lastCommittedPage = context.getLong("import.page", 0L);
context.putLong("import.page", lastCommittedPage + 1);
~~~

This snippet **only illustrates map operations**. Mutating context in memory does not by itself create a proper checkpoint: readers/writers must update state at the **proper callbacks/lifecycle hooks** and the framework must persist context with the transaction. Never increment page counters in a listener and use them to skip records independently of actual commits.

### 4.1. `ItemStream` Lifecycle

Stateful readers/writers typically implement `ItemStream`:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

- `open` restores state from `ExecutionContext` when the step starts or restarts.
- `update` writes the current position/state into context before checkpointing.
- `close` releases resources. **Never rely on `close` to save final progress**: a process can die without executing callbacks.

Implementations like `FlatFileItemReader` and `JdbcPagingItemReader` persist state when `saveState=true`. When using multiple readers of the same type within one step, assign **distinct state key names** so they do not overwrite each other's context.

### 4.2. What Should Not Be Stored in `ExecutionContext`

- Never store lists of millions of items, large HTTP bodies, or Java entities/sessions. Context holds **small metadata**, not business data dumps.
- Never store tokens, passwords, private keys, or sensitive data unless the metadata DB is appropriately secured.
- Never store non-serializable objects or structures tightly coupled to classes/versions that break after deployments. Prefer `String`, numbers, booleans, stable timestamp formats, and IDs.
- Never let multiple threads/partitions mutate one shared context without clear boundaries. Each `StepExecution` needs isolated state.

Upgrading application versions—changing reader names, context formats, or serializers—can make **older jobs unrestartable**. Plan metadata compatibility strategies, migrations, or cutover procedures for old batches.

## 5. Spring Boot Example: Reading CSV and Writing JDBC with Checkpoints

This example uses **Java 17+, Spring Boot 3.x, Spring Batch 5.x**, and PostgreSQL. An immutable CSV file contains:

~~~csv
operationId,orderId,amount
op-001,order-101,120000.00
op-002,order-102,350000.00
op-003,order-103,99500.00
~~~

Each row represents a transaction to insert into `payment_imports` with unique business key `operation_id`. This is **reconciliation data ingestion**; never call a payment-capture API directly inside the writer, because non-DB payment side effects require stricter retry/idempotency strategies.

Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

In a Spring Boot application using auto-configuration, you normally do not add `@EnableBatchProcessing` manually. That annotation causes Boot to back off batch auto-configuration in favor of manual configuration; use it only when genuinely needed. Ensure a database exists for **JobRepository metadata** with version-matched Batch schemas applied via migrations. Never rely on Boot auto-creating metadata tables in production.

Example `application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_db
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Here `enabled: false` prevents auto-launching jobs on startup; jobs are started cleanly by an operational scheduler/API or `JobLauncher`. `initialize-schema: never` assumes Batch metadata and business tables are created via Flyway/Liquibase. Environment variables are injected from a secret manager.

To illustrate local transactions, the example shares **the same PostgreSQL DataSource** for batch metadata and business tables with a matching transaction manager. In multi-DataSource projects, explicitly configure transaction managers and metadata storage; if both commit independently, re-evaluate restart guarantees.

### 5.1. Target Schema and Idempotency

~~~sql
CREATE TABLE payment_imports (
    operation_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    imported_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

The unique key `operation_id` prevents inserting a duplicate row if a chunk replays. If the same operation ID reappears with **different content**, the system must treat it as a contract conflict and reconcile rather than silently overwriting the recorded amount with an upsert.

### 5.2. Data Record and Stateful Reader

~~~java
package com.example.integration.batch;

import java.math.BigDecimal;

public record PaymentRow(
        String operationId,
        String orderId,
        BigDecimal amount) {}
~~~

`FlatFileItemReader` persists read position via `ItemStream`. The bean requires `@StepScope` to bind `inputFile` when the step actually runs:

~~~java
package com.example.integration.batch;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration(proxyBeanMethods = false)
class PaymentReaderConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<PaymentRow> paymentCsvReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<PaymentRow>()
                .name("paymentCsvReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("operationId", "orderId", "amount")
                .fieldSetMapper(fields -> new PaymentRow(
                        fields.readString("operationId"),
                        fields.readString("orderId"),
                        fields.readBigDecimal("amount")))
                .saveState(true)
                .strict(true)
                .build();
    }
}
~~~

Attribute meanings:

- `name("paymentCsvReader")` sets a unique name so `ExecutionContext` keys do not collide with other readers.
- `linesToSkip(1)` skips the CSV header line. File layout, delimiter, and encoding must be fixed by contract; for non-UTF-8 files, configure encoding explicitly on the builder.
- `saveState(true)` enables saving progress via `ExecutionContext` so it can reopen at the last checkpoint.
- `strict(true)` requires the resource to exist when opening, preventing missing files from masquerading as empty valid batches.
- `@StepScope` instantiates the reader per run's `JobParameters`. Step-scoped beans should never be instantiated/used outside a step context.

**The file must remain immutable throughout processing and across restarts.** Inserting, deleting, or reordering lines in the file before restarting by saved index causes the reader to skip or double-process lines. Store files under immutable paths with `sourceId`, checksum, line count, or reconciliation metadata to verify it is **the exact same input**.

### 5.3. Writer Persisting Within the Chunk Transaction

Example using `JdbcBatchItemWriter` with named parameters suitable for Java record `PaymentRow`:

~~~java
package com.example.integration.batch;

import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Configuration(proxyBeanMethods = false)
class PaymentWriterConfiguration {

    @Bean
    JdbcBatchItemWriter<PaymentRow> paymentJdbcWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<PaymentRow>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO payment_imports
                         (operation_id, order_id, amount)
                     VALUES (:operationId, :orderId, :amount)
                     ON CONFLICT (operation_id) DO NOTHING
                     """)
                .itemSqlParameterSourceProvider(item ->
                        new MapSqlParameterSource()
                                .addValue("operationId", item.operationId())
                                .addValue("orderId", item.orderId())
                                .addValue("amount", item.amount()))
                .assertUpdates(false)
                .build();
    }
}
~~~

This is **PostgreSQL** SQL: `ON CONFLICT ... DO NOTHING` ensures the same operation ID does not insert a duplicate row on replay. `MapSqlParameterSource` explicitly maps Java record accessors to SQL parameters without depending on JavaBean getters. With `assertUpdates(false)`, the writer does not treat a skipped duplicate insert as an error for affecting zero rows. Still, this is only **key-level deduplication**: before ignoring a duplicate ID, reconciliation should verify `orderId`/`amount` match the stored record, as the same operation ID with a different amount is a critical error.

In production, use staging tables, payload hash validation, or conflict-detecting queries/constraints to fail explicitly on mismatches. Chunk transactions protect records inside **the same database and transaction manager**; they do not cover emails, HTTP, or brokers unless those targets share the transaction.

### 5.4. Defining Step and Job with the Spring Batch API

~~~java
package com.example.integration.batch;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class PaymentImportJobConfiguration {

    @Bean
    Step importPaymentsStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<PaymentRow> paymentCsvReader,
            JdbcBatchItemWriter<PaymentRow> paymentJdbcWriter) {

        return new StepBuilder("importPaymentsStep", jobRepository)
                .<PaymentRow, PaymentRow>chunk(100, transactionManager)
                .reader(paymentCsvReader)
                .writer(paymentJdbcWriter)
                .build();
    }

    @Bean
    Job importPaymentsJob(
            JobRepository jobRepository,
            Step importPaymentsStep) {

        return new JobBuilder("importPaymentsJob", jobRepository)
                .start(importPaymentsStep)
                .build();
    }
}
~~~

In this example, the writer consumes `PaymentRow` directly so no processor is needed; add `.processor(...)` when validation or normalization is required. `chunk(100, transactionManager)` sets the commit boundary at up to 100 read items per chunk, with filter/skip/retry effects accounted for separately.

**Critical condition:** the injected `PlatformTransactionManager` must actually manage the JDBC resource used by the writer and match `JobRepository` configuration. If the project has multiple managers, use `@Qualifier` rather than relying on an implicit `@Primary`. Never claim metadata checkpoints and business tables commit atomically if they sit on different datasources/transaction managers.

## 6. `JobParameters`: How to Launch and Restart the Right `JobInstance`

For a daily import job, configure identifying parameters representing **the exact logical data file**:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.launch.JobLauncher;

// Snippet inside a service/scheduler injecting Job and JobLauncher.
JobParameters params = new JobParametersBuilder()
        .addString("sourceId", "bank-A-2026-11-21", true)
        .addString("inputFile", "/data/import/bank-A-2026-11-21.csv", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importPaymentsJob, params);
~~~

Both parameters here are **identifying**. If the first run fails, calling `jobLauncher.run(importPaymentsJob, params)` with the same identifying parameters lets Spring Batch locate **the same JobInstance** and create a new execution if restartable. Never generate a fresh timestamp or `run.id` on every retry.

Besides re-launching via `JobLauncher`, you can call `JobOperator.restart(executionId)` to request restarting a failed/stopped `JobExecution` when Spring Batch infrastructure is fully configured. Verify the execution status is restart-eligible before calling, and ensure no other execution of the same instance is actively running.

### 6.1. Handling Statuses and Non-Restartable Conditions

| Status / Condition | Operational Meaning |
| --- | --- |
| `FAILED` | Restartable if the job permits it and metadata/input remain valid. |
| `STOPPED` | Restartable after a clean stop, depending on step/job configuration. |
| `COMPLETED` | Normally not restartable for the same instance; intentional reprocessing requires a **new JobInstance** or redesigning the requirement. |
| `STARTED` / running | Do not start another execution of the same JobInstance merely because it is slow; verify whether the process is still active. |
| `UNKNOWN` / inconsistent metadata | Never force status via SQL; investigate and reconcile before intervening. |
| Reader does not save state (`saveState=false`) | May re-read from the start; safe only if all side effects are idempotent and dedup is designed. |

Special options: `startLimit` caps how many times a step can start, `allowStartIfComplete(true)` forces an already-completed step to run again on job restart (e.g., a pre-check step that must re-verify), whereas by default `COMPLETED` steps are skipped. These choices affect data writes, so document and test them explicitly.

## 7. Passing Data Between Steps via `ExecutionContext`

A job may consist of two steps:

1. `validateSourceStep` verifies the file checksum and line count, storing `sourceChecksum`.
2. `importPaymentsStep` runs only if the checksum matches the verified file.

If you write `sourceChecksum` only into the validation step's **Step `ExecutionContext`**, the import step **cannot read it directly** because each step has its own context. To share data across steps, you can:

- Store the value directly into the **Job `ExecutionContext`** at an appropriate boundary.
- Use `ExecutionContextPromotionListener` to promote keys from step context to job context when the step finishes with an eligible status.
- Persist important, large, or reconcilable data in a **business table** keyed by `sourceId`, storing only a small ID/checksum in context.

Example promotion listener configuration:

~~~java
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.context.annotation.Bean;

@Bean
ExecutionContextPromotionListener promoteSourceChecksum() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] { "sourceChecksum" });
    return listener;
}
~~~

This listener must be registered on **the step that produces `sourceChecksum`** (e.g., via `.listener(promoteSourceChecksum())`), and the processor/tasklet must put the key into step context before completing. Promotion occurs at step lifecycle boundaries—**never use it as a per-item checkpoint mechanism**.

If the job must restart after `validateSourceStep` completed, the job context must retain enough state for subsequent steps to proceed cleanly. Avoid passing entire parsed files through context: metadata has size limits, is hard to version, and is not a business data store.

## 8. Boundaries Where Checkpoints Can Drift from Real Data

### 8.1. Metadata and Business Data in Two Different Databases

Suppose `JobRepository` uses DB A and `ItemWriter` writes to DB B. If each database has its own transaction manager, two hazardous sequences arise:

~~~mermaid
sequenceDiagram
    participant Batch as Spring Batch
    participant Meta as DB A - JobRepository
    participant Data as DB B - Business
    Batch->>Data: Write chunk
    Data-->>Batch: Commit succeeds
    Batch->>Meta: Save checkpoint
    Note over Meta: Failure/crash before checkpoint commits
    Note over Data,Meta: On restart, already-written chunk may replay
~~~

Or a checkpoint is marked complete while the business write failed under a broken coordination scheme. Either leads to **missing or duplicated data** without reconciliation. Options:

1. Share one database and transaction manager whenever feasible so writer and checkpoint join a single local transaction.
2. Make writers **idempotent** (unique keys, conflict-checking upserts, inbox ledgers) so chunk replays remain safe.
3. When writing to multiple targets, use staging/outboxes, sagas, or reconciliation workflows. Never assume `JobRepository` coordinates XA across two databases.

### 8.2. Calling HTTP, Sending Email, or Publishing to a Broker from `ItemWriter`

~~~text
Chunk starts
  -> POST /payments at target (creates authorization)
  -> Process dies before checkpoint
  -> Restart re-reads item
  -> POST /payments again
~~~

Local DB rollback **does not undo** a created payment or sent email. This requires:

- A stable operation ID sent consistently across attempts.
- A target API supporting idempotency or status lookup by operation ID.
- `PENDING`/`UNKNOWN` states and reconciliation when timeouts follow side effects.
- An outbox when the goal is **reliably emitting events after commit**.

With Kafka/RabbitMQ brokers, acks, retries, and redeliveries can duplicate messages; use durable keys/correlation IDs and consumer deduplication. **Batch checkpoints do not create end-to-end exactly-once.**

### 8.3. Mutating Inputs Break Determinism

Static flat files restart cleanly by item index. By contrast, with paginated APIs or continuously changing DB queries:

- `OFFSET/LIMIT` over a table receiving inserts/deletes can skip or repeat items on restart.
- Paging without a deterministic `ORDER BY` returns different records per page after deploys or query-plan shifts.
- External API cursors may expire; plan snapshot re-acquisition, durable key/marker checkpoints, or safe new batches.
- Source queries should use snapshots/batch IDs, monotonic keyset pagination, or fixed time/ID windows where supported.

If correctness depends on a point-in-time snapshot, **freeze or version the source** rather than merely setting `saveState(true)`.

## 9. Retry, Skip, and Restart: Three Different Mechanisms

| Mechanism | When Used | Guarantees to Consider |
| --- | --- | --- |
| **Retry within the same `StepExecution`** | Transient errors like deadlocks or brief timeouts. | May re-invoke processor/writer; external side effects must be idempotent. |
| **Skip item** | Corrupt records permitted to be dropped per batch contract. | Must audit skipped items and define when a batch still counts as complete. |
| **Restart `JobInstance`** | Whole job failed or stopped; launches new `JobExecution` from checkpoint. | Input/metadata compatibility; committed side effects must not repeat harmfully. |

Example intentional fault-tolerance configuration:

~~~java
return new StepBuilder("importPaymentsStep", jobRepository)
        .<PaymentRow, PaymentRow>chunk(100, transactionManager)
        .reader(paymentCsvReader)
        .writer(paymentJdbcWriter)
        .faultTolerant()
        .retry(org.springframework.dao.TransientDataAccessException.class)
        .retryLimit(3)
        .skip(org.springframework.batch.item.file.FlatFileParseException.class)
        .skipLimit(5)
        .build();
~~~

This is an **illustrative variant**—do not declare it alongside another `importPaymentsStep` sharing the same bean name. Up to 5 unparseable CSV lines may be skipped, while transient JDBC errors receive bounded retries. `retryLimit` defines the framework's attempt policy, though exact behavior also depends on thrown exceptions, rollbacks, and failure phase.

Never blindly enable skips for all exceptions or all transaction errors: skipping a payment record can break reconciliation. Track `readSkipCount`, `processSkipCount`, `writeSkipCount`, failure reasons, and build a properly authorized error-file pipeline.

## 10. Parallel Execution and Its Effect on `ExecutionContext`

To increase throughput, Spring Batch supports multi-threaded steps, partitioning, remote chunking, and related orchestration patterns. However, checkpoints are no longer a simple single row index:

- **Multi-threaded step:** stateful readers/writers may not be thread-safe. Never share one `FlatFileItemReader` across threads without control; synchronized wrappers aid thread safety yet do not automatically preserve order or clean restarts when chunks commit concurrently.
- **Partitioning:** each partition gets its own `StepExecution`/`ExecutionContext`; manage partition ranges/keys and per-partition state so failed partitions restart independently. Partition names and data slices must stay stable across restarts.
- **Remote chunking:** sending items/chunks and handling acks on out-of-process workers introduces new failure boundaries; require broker acks, dedup, and idempotent writers.
- **Overlapping jobs:** two distinct JobInstances can read the same file or write the same business key if identifying parameters are wrong. Guard with business keys and policies allowing only one valid run.

Do not turn on parallelism just because checkpoints exist. Prove state, input partitioning, and write paths are concurrency-safe first.

## 11. Valuable Restart Testing

Testing only the happy path proves a job can run, not that it **recovers cleanly after failures**. Test against real metadata with a real database or Testcontainers, injecting faults right along chunk boundaries.

| Scenario | What to Verify |
| --- | --- |
| Job runs 100,000 rows cleanly | Metadata `COMPLETED`, accurate record and monetary totals, no gaps/extras. |
| Fails at row 350 with chunk size 100 | Committed chunks survive; restart re-reads uncommitted portion and finishes with exact total. |
| Crash after writer writes before checkpoint (non-DB side effect) | Idempotency/reconciliation prevents harmful duplicate effects. |
| Same `JobParameters` after `FAILED` | New `JobExecution` under same `JobInstance`; no new logical batch created. |
| `JobParameters` with new `run.id` | Creates new `JobInstance`; system must not confuse it with restart. |
| `@StepScope` binds `inputFile` properly | Reader opens that run's resource rather than retaining stale paths across executions. |
| File modified after failure | Checksum/immutable-source check catches difference; never resumes on untrusted offsets. |
| Chunk rollback on JDBC error | No half-chunk rows survive when writer and transaction share the datasource properly. |
| Processor filters or skips items | `readCount`/`writeCount`/`filterCount`/`skipCount` align; business data stays accurate. |
| Restart when prior Step already completed | Completed step skipped per config; cross-step context remains available. |
| Redeploy upgrading reader/serializer version | Legacy `ExecutionContext` remains readable, or migration/recovery path runs cleanly. |
| Restarting two partitions | Only incomplete partitions re-run; no duplicate writes across slices. |

### 11.1. Organizing Tests with Spring Batch Test

Add the Spring Batch test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Use `@SpringBatchTest`, `JobLauncherTestUtils`, and `JobRepositoryTestUtils` with `@SpringBootTest` to launch jobs/steps in tests. However, in restart tests, **never wipe `JobRepository` metadata between the `FAILED` attempt and the restart attempt**, as that erases the very state under test. Cleanup must occur before/between independent test cases on a clear schedule.

A solid restart test sequence:

1. Load an **immutable** fixture file, initialize schemas, and ensure a clean initial state.
2. Inject a controlled failure after some chunks commit; verify `JobExecution` is `FAILED`, inspect metadata, and verify committed rows.
3. Disable the failure while **keeping identifying `JobParameters` and `JobRepository` untouched**.
4. Re-run the job; assert a new `JobExecution` belongs to the same `JobInstance` and the latest `JobExecution` is `COMPLETED`.
5. Verify data **per business key** and monetary sum—not just row count; assert zero duplicates or omissions.
6. Attempt a third launch of the completed `JobInstance`: framework rejects or applies configured policy rather than silently re-running as new.

Never evaluate restarts solely by `readCount`: an idempotent DB writer might mask re-reading too many rows by silently dropping duplicates. Verify both **business correctness** and **recovery progress**.

## 12. Operations, Observability, and Protecting Metadata

A solid batch dashboard should answer:

- Which `JobInstance`s are active, and with which identifying parameters? Is any attempt stuck `STARTED` too long?
- Which Step failed, and how did `readCount`, `writeCount`, `commitCount`, `rollbackCount`, and `skipCount` evolve?
- When did checkpoints/`ExecutionContext` last update? Is a run stuck on the same item or partition?
- What are processing latency, per-minute throughput, chunk commit/rollback rates, and transaction/connection hold times?
- Are any records skipped, routed to DLQ, or awaiting manual reconciliation?
- After redeploys, can older jobs still restart under the current schema and serializer versions?

**`JobRepository` holds critical operational state**: use a durable database, backups, controlled migrations, access controls, and connection monitoring. Never use an in-memory repository for jobs promising crash resumption. Retain metadata long enough to support retries and reconciliation; when purging metadata, verify which jobs remain restart-eligible and which business records still link to old executions.

Log business keys only as needed under proper authorization; avoid dumping full PII, card numbers, tokens, passwords, or raw `ExecutionContext`. Propagate stable correlation/source IDs to trace a batch from input to DB, events, and reconciliation.

## 13. Common Misconceptions

| Misconception | Consequence | Accurate Understanding |
| --- | --- | --- |
| "Restart just means calling the same method again." | Spawns a new `JobInstance`, re-reading from start. | Restart requires the same job identity, same identifying parameters, and durable metadata. |
| "Whenever retrying, just append a timestamp." | Changes batch identity and loses checkpoints. | Preserve identifying parameters when restarting the same batch. |
| "With `ExecutionContext`, everything writes exactly once." | External APIs/emails/brokers outside transactions can be called twice. | Enforce idempotency and reconciliation outside commit boundaries. |
| "With `saveState=true`, editing the file is harmless." | Offsets point to wrong lines, missing or duplicating rows. | Inputs must be immutable/versioned or use proper cursors/checkpoints. |
| "`ExecutionContext` is one job-wide map." | Steps read wrong keys or lose state between steps. | Distinguish step context, job context, and promotion. |
| "Saving metadata is enough; writers need no transactions." | Business data and checkpoints drift out of sync. | Bind writers to the right transaction manager or design idempotency/reconciliation. |
| "Skipping one bad record doesn't hurt the batch." | Reports and balances lose records. | Skips require business contracts, metrics, and post-run auditing. |
| "Parallel steps always speed things up safely." | Reader state and chunk commits become non-deterministic. | Verify thread safety, partition boundaries, ordering, and restarts. |

## 14. Design Checklist for a Restartable Job

- [ ] Clearly defined **`JobInstance` identity** and identifying `JobParameters`; retrying the same batch never mints a new identity.
- [ ] `JobRepository` uses a durable database, version-matched schema, migrations/backups, and appropriate permissions.
- [ ] Reader supports state or safe replay; `ItemStream` is registered with a unique key name.
- [ ] Input file/API snapshot is immutable or versioned/checksummed; pagination uses stable ordering.
- [ ] `ExecutionContext` stores only small, versionable, serializable metadata.
- [ ] Chunk transaction manager matches the writer's datasource; discrepancies when metadata and data live separately are explicitly handled.
- [ ] Writers and non-DB adapters are idempotent, carrying operation/event IDs and reconciliation for timeouts/crashes after side effects.
- [ ] Retry, skip, restart, start limits, and step ordering are specified per business rules.
- [ ] Real restart tests run with metadata surviving across attempts, chunk rollbacks, altered inputs, and version upgrades.
- [ ] Monitoring tracks `FAILED`/`STOPPED`, overdue jobs, checkpoint lag, skips/rollbacks, and reconciliation totals.

In **Spring Boot Integration**, checkpoints and `ExecutionContext` tell Spring Batch **how far it got**, while `JobInstance`/`JobExecution` identify **which logical run is continuing**. Combining chunk transactions, a durable `JobRepository`, stable source data, and duplicate-safe writers lets batch jobs recover from failures while upholding real-world integration data contracts and reliability.
