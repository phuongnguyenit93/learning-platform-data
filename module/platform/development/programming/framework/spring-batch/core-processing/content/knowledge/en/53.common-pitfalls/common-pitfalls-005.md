# Writer Producing Duplicate Output in Spring Batch

In Spring Batch, a subtle bug is **the writer producing duplicate output**: the same business record appears twice in the target table, a CSV file contains repeated rows, or an external API receives the same request multiple times. Sometimes `JobExecution` still finishes with `BatchStatus.COMPLETED`, because Spring Batch only knows the writer executed the configured calls; the framework cannot infer your domain's unique key or the rule that "each transaction must be written only once".

This pitfall is especially common when batches involve **chunk transactions, retries, restarts, file-appending writers, overlapping job runs, or side effects outside the transaction**. In the **Common Pitfalls** chapter of **Spring Batch Core Processing**, the goal is to distinguish root causes, gather evidence, and design **idempotent** writers (handling repeated requests without duplicating business effects).

```text
           Source data
                |
                v
           ItemReader
                |
                v
           ItemProcessor
                |
                v
            ItemWriter
          /      |      \
         v       v       v
       JDBC     File    API / Message
         |       |       |
         +-------+-------+
                 |
           Duplicate output?
                 |
       +---------+----------+
       |         |          |
   Duplicate   Retry /    Overlapping job/
     input     restart    output path
```

**Rule:** do not fix the bug by deleting duplicate rows after the job finishes without first determining why they were created. A "cleanup after the fact" approach can mask transaction bugs, delete genuinely valid rows, or erase an effect already confirmed by an external system.

## 1. What Counts as Duplicate Output?

Two records with identical columns are not always a business duplicate. You must define the **unique unit of output** (*business identity*).

Example of a payment import job:

```text
Input:
  paymentId=P001, amount=100.00
  paymentId=P002, amount=200.00

Expected output:
  P001,100.00
  P002,200.00

Actual output:
  P001,100.00
  P002,200.00
  P001,100.00   <-- duplicate if each paymentId may only be written once
```

In other domains, `paymentId=P001` may appear across multiple **versions** or **data periods**. Then the unique key is not just `paymentId`, but perhaps `(tenantId, sourceVersion, paymentId)` or `(businessDate, paymentId)`. If you define the key too narrowly, you may accidentally drop records that should be kept; if too broadly (especially adding a per-execution UUID), you may fail to detect duplicated data.

Distinguish the forms of duplicates:

| Form | Symptom | Question to answer |
| --- | --- | --- |
| Duplicates already in **input** | Same source key appears multiple times | Did the reader read the source accurately while the source itself contains duplicates? |
| Duplicates from **processor** | One item expands into multiple outputs, or mapping drops the key | Does processing logic intentionally emit multiple rows? |
| Duplicates from **writer** | One item causes the writer to write multiple times | Does the writer have an unintended loop/call or faulty buffering? |
| Duplicates during **retry** | An operation re-executes within the same `StepExecution` | Did the previous attempt produce a side effect before failing? |
| Duplicates during **restart** | First execution fails; subsequent execution re-writes existing data | Do `ExecutionContext` and transaction/writer state match? |
| Duplicates from **rerun/new JobInstance** | Same processing period re-runs from scratch | Did `JobParameters` create a new instance? |
| Duplicates from **concurrency** | Two threads/partitions/nodes write the same record | Do partitioning or keys/constraints prevent overlap? |
| Duplicates from **file append/overwrite** | File has repeated blocks of data, often after the second run | In what mode does the writer open an existing output file? |

Before choosing a solution, agree on whether the duplicate in question refers to **two identical physical lines**, **two transactions sharing a business key**, or **two intentional reprocessing events**. Auditing may need to retain attempts, yet the target system must not necessarily apply business effects multiple times.

## 2. Why Can Chunk Transactions Lead to Duplicate Writes?

Spring Batch typically performs chunk-oriented processing:

```text
BEGIN TRANSACTION
  read items 1..N
  process items 1..N
  writer.write(chunk)
  update ExecutionContext/checkpoint
COMMIT
```

If the reader, writer, `JobRepository`, and target data use an appropriate transaction manager, a failure **before commit** usually rolls back database changes within the transaction. On restart, uncommitted items can be reprocessed; that is the right behavior. Trouble arises when **a writer action succeeded yet does not roll back with the transaction**.

```text
Chunk 1: P001, P002
  writer sends P001 to external API ---> API returns 200, transaction created
  writer sends P002 to external API ---> timeout
  SQL chunk transaction rolls back

Retry attempt:
  writer re-sends P001 ------------> API creates transaction a second time!
  writer re-sends P002 ------------> API returns 200
```

A database `rollback` **does not revoke** a transaction created by an external API. Likewise, writing files, sending emails, or publishing messages do not automatically join the chunk's JDBC transaction. That is precisely why writers need an idempotency contract at external side-effect boundaries.

### 2.1. Retry Differs from Restart, and Both Differ from Rerun

- **Retry**: a failing operation is retried within the same processing run, typically inside one `StepExecution`, per the fault-tolerant policy. If the writer triggers side effects before failing, retry can duplicate effects.
- **Restart**: a `FAILED`/`STOPPED` `JobInstance` continues via a new `JobExecution`, relying on saved metadata and checkpoints. Uncommitted items may be re-read/re-written.
- **Rerun from scratch**: launching a new `JobInstance`, usually by changing identifying `JobParameters` or creating a new period/version. If both instances write to the same target without idempotency, duplicates can occur.

Each case requires knowing **what was committed**, **what read position to restore**, and **which business key prevents applying the effect twice**.

## 3. Roles of `JobInstance`, `JobParameters`, and `ExecutionContext`

In Spring Batch:

```text
Job Name + identifying JobParameters
                 |
                 v
            JobInstance
                 |
        +--------+---------+
        |                  |
  JobExecution #1     JobExecution #2
       FAILED             COMPLETED (restart)
```

For example, one instance per period:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "feed-v3")
    .toJobParameters();
```

By default, these parameters are identifying. Upon failure, restarting the same instance allows Spring Batch to use the persisted `ExecutionContext`. If every call adds an identifying UUID:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("sourceVersion", "feed-v3")
    .addString("attemptId", UUID.randomUUID().toString())
    .toJobParameters();
```

then each launch is a **different JobInstance**, not a restart. The reader's restart mechanism cannot automatically know that these two instances should share a checkpoint. This is a common source of duplicates when applications use `RunIdIncrementer` or timestamps to "dodge" `JobInstanceAlreadyCompleteException`.

### 3.1. `ExecutionContext` Is a Checkpoint, Not a Deduplication Lock

`ItemStream` defines `open(ExecutionContext)`, `update(ExecutionContext)`, and `close()`. A restartable reader such as `FlatFileItemReader` can store the read position; a restartable writer such as `FlatFileItemWriter` can store file state. When a chunk commits successfully, the framework persists the context for recovery.

Checkpoints help **reduce the volume of data that must be reprocessed**, but do not replace unique keys at the target. If a process is killed right after an external system accepted an operation yet before Batch state committed, `ExecutionContext` cannot tell whether the external system accepted that side effect.

### 3.2. Configurations That Accidentally Break Checkpoints

Changes to watch closely:

- `.saveState(false)` on readers/writers that need restart can lose the ability to resume at the right position.
- Changing `.name(...)` of an `ItemStream` between executions can change the state key in context.
- Wrapping an `ItemStream` inside a delegate without delegating/registering `open/update/close` prevents the framework from saving state as expected.
- Changing output file paths or source files per `JobExecution` instead of keeping identity stable per instance.
- Changing query ordering or source data between restarts can make offsets/sort keys point to different records.
- Unstable partitioning causes an input range to be processed by multiple workers across runs.

**Do not directly edit `BATCH_*` tables to force a restart position.** Metadata is owned by Spring Batch; manual edits easily desynchronize counters/context from actual output.

## 4. Cause 1: `FlatFileItemWriter` Appends to an Old File

A common symptom is a CSV report after the second run containing the same header and all data rows from the first run:

```text
orders.csv after run 1:
  id,status
  A001,PAID
  A002,NEW

orders.csv after run 2:
  id,status
  A001,PAID
  A002,NEW
  id,status
  A001,PAID
  A002,NEW
```

The cause may be that the writer was configured with **append**, the output path is shared across runs, or the writer opens the file in append mode outside the `ItemStream` mechanism. Do not merely delete the duplicate header: the data rows underneath were duplicated too.

### 4.1. Distinguishing a New Run from a Restart

With `FlatFileItemWriter`, options such as `appendAllowed`, `shouldDeleteIfExists`, and `saveState` affect how the writer opens files. Spring Batch has specific logic when the writer **is restarted with a valid execution context**; do not equate file-opening behavior on restart with that of a brand-new instance.

| Situation | Expectation | Duplicate risk |
| --- | --- | --- |
| New instance, new output | Creates output file for the new period/version | Low if filename is distinct and does not merge old output |
| New instance, colliding output path | Explicit reject/replace/version policy | Improper append or replace creates duplicates or loses output |
| Restarting failed instance with partial file | Reopens the same output, restores reader and writer positions | Improper delete/append can lose data or duplicate a chunk |
| Two executions writing the same output concurrently | Mutual exclusion or isolated outputs | Two writers may interleave lines, duplicate, or corrupt the file |

### 4.2. File Writer with a Path Determined by Data Period

Spring Batch 5.x example:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemWriter<String> ordersWriter(
        @Value("#{jobParameters['outputPath']}") String outputPath) {

    return new FlatFileItemWriterBuilder<String>()
        .name("ordersWriter")
        .resource(new FileSystemResource(outputPath))
        .encoding(StandardCharsets.UTF_8.name())
        .lineAggregator(line -> line)
        .saveState(true)
        .build();
}
```

This pattern keeps the writer name stable and uses state for restart. **It does not by itself guarantee idempotency**: if `outputPath` is passed carelessly, two different instances can still point to the same file. In a real application, derive the path from `businessDate` and a validated output version under a service-managed output root. Never take arbitrary paths from untrusted input and let the writer write freely to the filesystem.

### 4.3. Safer File Strategy: Staging → Verify → Publish

```text
JobInstance output:
  staging/2026-11-16/orders-v3.part
             |
        writer writes, checkpoint/restart
             |
     job COMPLETED + content verification
             |
             v
  published/2026-11-16/orders-v3.csv
```

The `.part` file is used exclusively by the active job; consumers never read it as final output. After the job succeeds, verify row counts/checksums and then publish under control. If an intentional re-export occurs, issue a new **output version** or an approved replace policy instead of appending to the official file.

`Files.move(..., ATOMIC_MOVE)` can help publish atomically on filesystems that support it, though it is not guaranteed across volumes or on object storage. If the target is S3/MinIO, use object versions/manifests and a dedicated confirmation workflow.

### 4.4. File Already Exists Before the Job Starts

If the final output already exists, determine whether it belongs to:

1. **An acknowledged result**: never blindly append or overwrite.
2. **A temporary file of the same instance needing restart**: preserve the file and writer state; do not delete it merely because it exists.
3. **Orphaned junk or output from another identity**: investigate/clean within the proper scope, avoiding deleting another instance's files.

Configuring `shouldDeleteIfExists(true)` can fit a **new instance**, but carries serious risk if used as an arbitrary delete outside the restart lifecycle. Understand `FlatFileItemWriter`'s contract and test both fresh starts and real restarts.

## 5. Cause 2: JDBC Writer `INSERT` Repeats the Same Business Key

Example writer inserting into a table without a unique constraint:

```sql
CREATE TABLE order_result (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_order_id VARCHAR(50) NOT NULL,
    amount NUMERIC(18,2) NOT NULL
);
```

If every write generates a new `id`, the same `source_order_id=A001` can appear twice while the database considers both rows valid. Spring Batch's `commitCount` and `writeCount` cannot detect that a uniqueness rule was violated.

### 5.1. Building a Unique Key from Business Semantics

If a source order must be stored at most once per `sourceVersion`:

```sql
CREATE TABLE order_result (
    source_version VARCHAR(80) NOT NULL,
    source_order_id VARCHAR(50) NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (source_version, source_order_id)
);
```

This key lets the database block duplicates even if a scheduler unexpectedly runs two jobs or the writer is invoked again. However, key selection is a business decision: if every update to the same order must be retained as history, include `eventVersion` or a stable event ID rather than applying an overly narrow unique constraint that drops valid data.

### 5.2. Using Idempotent Upsert When the Contract Allows

**PostgreSQL** example:

```sql
INSERT INTO order_result(source_version, source_order_id, amount)
VALUES (:sourceVersion, :sourceOrderId, :amount)
ON CONFLICT (source_version, source_order_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

This is PostgreSQL syntax and must not be copied verbatim to Oracle, SQL Server, or MySQL. `DO UPDATE` means recalculating the same key will **overwrite the existing amount**. Use this only when the application guarantees deterministic results for the same source/version or has an explicit update rule. If modifying already acknowledged results is forbidden, consider `DO NOTHING` combined with payload/checksum verification so a matching key with different content is not silently ignored.

### 5.3. Example `JdbcBatchItemWriter` Using a Business Key

Spring Batch 5.x:

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

record OrderOutput(String sourceVersion, String sourceOrderId,
                   java.math.BigDecimal amount) {}

@Bean
JdbcBatchItemWriter<OrderOutput> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderOutput>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO order_result
                (source_version, source_order_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT (source_version, source_order_id)
            DO UPDATE SET amount = EXCLUDED.amount
            """)
        .itemPreparedStatementSetter((item, ps) -> {
            ps.setString(1, item.sourceVersion());
            ps.setString(2, item.sourceOrderId());
            ps.setBigDecimal(3, item.amount());
        })
        .build();
}
```

`JdbcBatchItemWriter` sends statements via JDBC batching within the step's configured transaction. **A JDBC writer is not idempotent by default** just because the class name contains "Batch". Database constraints and `INSERT`/`UPSERT` SQL determine behavior when receiving the same item again.

### 5.4. Why Should You Not Rely on `SELECT` Then `INSERT` as the Only Deduplication Check?

```text
Job A: SELECT WHERE source_order_id='A001' → not found
Job B: SELECT WHERE source_order_id='A001' → not found
Job A: INSERT A001
Job B: INSERT A001  --> duplicate if there is no UNIQUE constraint
```

This is a *check-then-act* race condition. An application-level check can be helpful, but you still need an atomic unique constraint/upsert in the database or an equivalent synchronization mechanism. Business keys must also include tenant/period/version when needed; avoid a global key that does not reflect the data.

## 6. Cause 3: Writer Calls an API or Publishes a Message Multiple Times

Sending HTTP requests, publishing messages, sending emails, or writing object storage usually occurs **outside Spring Batch's JDBC transaction**. A timeout **does not prove the operation did not execute**: the server may have received, processed, and committed it while only the response was lost.

```text
Batch Client                    Target System
     |                               |
     | POST create(P001)             |
     |------------------------------>|
     |                               | P001 created successfully
     |          (response lost)      |
     |<---------- X                  |
     |
     | Retry POST create(P001)       |
     |------------------------------>| create P001 again?
```

### 6.1. Idempotency Key Stable Across Retries and Restarts

Instead of generating a new request ID per attempt, compute the key from the **business request**:

```java
String idempotencyKey = "payment:"
    + sourceVersion + ":" + paymentId;
```

If the API supports idempotency keys, send the same key in the header per the API contract (e.g., `Idempotency-Key`) across attempts of the same operation. The target system should store the key and return the previous result or reject duplicates according to explicit rules.

**Never use** `jobExecutionId`, `UUID.randomUUID()`, or the current timestamp as a **per-attempt** idempotency key when those attempts represent the same payment. Values that change across retries/restarts defeat deduplication.

In some protocols, keys are retained only for a limited window; understand the target system's retention. For monetary or high-value operations, add server-side status reconciliation, audit events, and a procedure for ambiguous responses.

### 6.2. Transactional Outbox

If the batch writes to a database and emits events to a message broker, you can use a *transactional outbox*:

```text
BEGIN TRANSACTION
  UPSERT order_result(A001)
  INSERT outbox_event(eventId=order-result:feed-v3:A001, payload=...)
COMMIT

Publisher reads outbox:
  sends event to broker
  marks sent / retries on failure

Consumer:
  records processed eventId
  ignores redelivery of the same event
```

An outbox reduces the risk of committing the database while losing the event; however, the publisher can still send **duplicates** after a timeout. Therefore, event IDs must stay stable and consumers still need deduplication/inbox or idempotent updates. This design achieves eventual correctness even over *at-least-once delivery* infrastructure; do not claim "end-to-end exactly-once" based solely on a framework.

## 7. Cause 4: Same Job Triggered Multiple Times

`@Scheduled` schedules, Quartz, Kubernetes CronJobs, CLIs, or operations APIs can trigger the same job within a short window. If each trigger source supplies different identifying parameters, Spring Batch may treat them as **distinct valid `JobInstance`s**, even though they process the same data period.

```text
02:00 Scheduler on Node A -> JobInstance (businessDate=11/16, runId=1)
02:00 Scheduler on Node B -> JobInstance (businessDate=11/16, runId=2)

Both read Nov 16 input
Both write to orders-2026-11-16.csv or the same target table
```

When an application has multiple instances, `@Scheduled` typically runs on **every instance** without a separate coordinator. `JobRepository` recognizes executions of the same instance, yet **does not exclude concurrent runs of different instances**.

### Control Strategies

- Identify `JobInstance` by **stable data period/input set**, never randomizing identifying parameters just so every launch succeeds.
- Use a cluster-aware scheduler/distributed lock or a single coordinating trigger when each period may only have one launcher.
- Place unique constraints or idempotency at the **output** as a final safeguard, since any lock mechanism has process-crash/timeout edge cases.
- Isolate output by period and version; never allow two instances to open the same target file concurrently.
- If work is partitioned, give each partition non-overlapping ranges and a reproducible name/identity on restart.

Calling `JobExplorer.findRunningJobExecutions(jobName)` helps monitoring, yet **"check no job running" then launch** consists of two operations and still races across nodes. Do not treat a plain status check as a distributed lock.

## 8. Cause 5: Reader Emits the Same Item Multiple Times

Signs of duplicates at the writer can originate from the **reader**, not the writer:

- A SQL `JOIN` on a one-to-many relationship accidentally multiplies rows.
- Paging without deterministic ordering or with a non-unique sort key.
- Dataset mutated while paging with `OFFSET`.
- Two partitions scanning overlapping ID ranges or the same file.
- A multi-threaded step sharing a non-thread-safe stateful reader.
- The source file already contains duplicate lines, or the same file is picked up multiple times from an input folder.
- Retry/restart re-reads an uncommitted chunk while the writer is not idempotent.

Example query that can multiply data:

```sql
SELECT o.order_id, o.total
FROM orders o
JOIN order_tags t ON t.order_id = o.order_id;
```

If an order has three tags, the query result can contain three rows for the same `order_id`. If the writer only cares about orders, output will contain duplicates even though each writer call matches the input it received.

Instead of reflexively adding `DISTINCT`, clarify whether tags need aggregation per order. Consider `EXISTS`, `GROUP BY`, intentionally deduplicated source queries, or fixing the data model. **Do not use writer-side deduplication to hide a broken JOIN** when result counts carry business meaning.

### 8.1. Paging Readers and Sort Keys

With `JdbcPagingItemReader`, sort keys should be stable and uniquely distinguish items; use a unique `id` column or a deterministic composite key. Querying with only `ORDER BY created_at` when multiple rows share the same timestamp can make pages unstable.

`pageSize` and `fetchSize` tune read performance, while `chunk size` sets the commit interval; they **are not deduplication mechanisms**. When data mutates during a job run, use snapshots or watermarks/input locks instead of relying solely on changing page size.

### 8.2. Parallel Execution and Partitions

```text
partition A: order_id 1..1000
partition B: order_id 1001..2000

Correct: two disjoint sets.

Wrong:
partition A: order_id 1..1500
partition B: order_id 1000..2000
                 ^^^^^^^^^
                 overlapping data 1000..1500
```

A solid system keeps the partition plan **stable per job instance**, with separate checkpoints per worker step and unique keys at the output. Merely adding a `TaskExecutor` to a step using a stateful reader does not make the reader thread-safe or restart-safe; in some situations, `SynchronizedItemStreamReader` synchronizes reads yet **does not guarantee** accurate checkpoints if chunks commit out of order.

## 9. Evidence-Based Duplicate Investigation Workflow

When duplicate rows are discovered, investigate in an order that isolates the fault instead of toggling writer flags at random.

### Step 1: Confirm the Definition of Duplicate

Identify the business key and source period:

```sql
-- Example target table with source_version and source_order_id.
SELECT source_version, source_order_id, COUNT(*) AS total
FROM order_result
GROUP BY source_version, source_order_id
HAVING COUNT(*) > 1
ORDER BY total DESC, source_version, source_order_id;
```

If the table already has a unique key on those two columns, this query cannot find duplicates under that definition. When users still report duplicates, check whether they are viewing a different downstream table, an exported file, a view with a multiplying JOIN, or a genuinely different business key definition.

### Step 2: Inspect `JobExecution`s for the Same Period

With the Spring Batch 5.x schema, a read-only query is often useful:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.START_TIME,
    je.END_TIME,
    je.STATUS,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Cross-check identifying parameters in `BATCH_JOB_EXECUTION_PARAMS` to find executions sharing the same `businessDate`/`sourceVersion`. If there are two different `JobInstance`s with the same business key, check `runId`, UUIDs, or overlapping schedules. The metadata schema can vary across Spring Batch major versions; always check your application's DDL version before running custom SQL.

### Step 3: Inspect Step Counters and Failure Timing

```sql
SELECT
    JOB_EXECUTION_ID,
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :job_execution_id
ORDER BY STEP_EXECUTION_ID;
```

Counters are evidence of framework activity, yet **do not equal the number of unique business records in the output**. `WRITE_COUNT=1000` does not prove the database has 1,000 new rows: `UPSERT` may update existing rows, a file writer may have appended, and an API may have received the same event twice. With retries, processor/writer invocations also do not necessarily map 1:1 to committed items.

### Step 4: Inspect Checkpoints and Data Sources

- Does the reader implement `ItemStream`/`saveState(true)` with a stable name?
- Was the **same JobInstance**'s `ExecutionContext` used on restart?
- Did the input file have the same checksum/object version across both runs?
- Did the SQL reader have a stable sort key/partition range without row multiplication from a JOIN?
- Did a chunk roll back while the writer still produced an external side effect?

If an exported file repeats an entire block of records, check file creation timestamps, append mode, executions sharing the output path, and duplicate headers. If the database only repeats records near a checkpoint, inspect retry/restart and transactions. If duplicates appear scattered across the entire input, inspect the source data, JOINs, and partitioning.

### Step 5: Reconcile Effects at the Target

For JDBC, inspect transactions/unique keys and insert timestamps. For APIs, inspect `idempotencyKey`/request IDs and actual server responses. For messages, inspect event IDs and consumer history. For files, compare checksums or identify repeated byte/line blocks. **Never conclude an API did not execute a request merely because the client received a timeout**.

## 10. Integration Test Example: Restart Without Duplicates Using H2

This section illustrates a **Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter integration test**. The step reads four payments from a file and writes to H2 with chunk size 2. The first run intentionally throws an exception in the chunk containing `P003`, after the first chunk has committed. The second run uses **the same identifying JobParameters** to restart. The final result must contain exactly four keys with no duplicates.

### 10.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

### 10.2. Complete Test

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = DuplicateOutputRestartTest.TestBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class DuplicateOutputRestartTest {

    record Payment(String id, int amount) {}

    @Autowired JobLauncherTestUtils jobLauncherTestUtils;
    @Autowired JdbcTemplate jdbcTemplate;
    @Autowired AtomicBoolean failOnce;

    @BeforeEach
    void prepareDatabase() {
        jdbcTemplate.execute("""
            CREATE TABLE IF NOT EXISTS payment_result (
                id VARCHAR(30) PRIMARY KEY,
                amount INTEGER NOT NULL
            )
            """);
        jdbcTemplate.update("DELETE FROM payment_result");
        failOnce.set(true);
    }

    @Test
    void restartReusesCheckpointAndProducesNoDuplicate(@TempDir Path dir)
            throws Exception {
        Path input = dir.resolve("payments.csv");
        Files.writeString(input, """
            id,amount
            P001,100
            P002,200
            P003,300
            P004,400
            """, StandardCharsets.UTF_8);

        String sourceVersion = "fixture-" + UUID.randomUUID();
        JobParameters parameters = new JobParametersBuilder()
            .addString("sourceVersion", sourceVersion) // identifying
            .addString("inputPath", input.toAbsolutePath().toString(), false)
            .toJobParameters();

        // Chunk #1 (P001, P002) commits, chunk #2 intentionally fails.
        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(jdbcTemplate.queryForList(
            "SELECT id FROM payment_result ORDER BY id", String.class))
            .containsExactly("P001", "P002");

        // Same identifying parameters: this is a restart of the old JobInstance.
        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(restarted.getJobInstance().getId())
            .isEqualTo(first.getJobInstance().getId());
        assertThat(restarted.getId()).isNotEqualTo(first.getId());

        List<String> ids = jdbcTemplate.queryForList(
            "SELECT id FROM payment_result ORDER BY id", String.class);
        assertThat(ids).containsExactly("P001", "P002", "P003", "P004");

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM payment_result", Integer.class);
        assertThat(count).isEqualTo(4);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApplication {

        @Bean
        AtomicBoolean failOnce() {
            // Only used to inject a controlled failure in the test.
            return new AtomicBoolean(true);
        }

        @Bean
        Job importPaymentsJob(JobRepository repository,
                              @Qualifier("importPaymentsStep") Step step) {
            return new JobBuilder("importPaymentsJob", repository)
                .start(step)
                .build();
        }

        @Bean
        @StepScope
        FlatFileItemReader<Payment> paymentReader(
                @Value("#{jobParameters['inputPath']}") String inputPath) {

            return new FlatFileItemReaderBuilder<Payment>()
                .name("paymentReader")
                .resource(new FileSystemResource(inputPath))
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fields -> new Payment(
                    fields.readString("id"), fields.readInt("amount")))
                .saveState(true)
                .build();
        }

        @Bean
        ItemWriter<Payment> paymentWriter(JdbcTemplate jdbc,
                                          AtomicBoolean failOnce) {
            return chunk -> {
                // Second chunk fails BEFORE writing data.
                boolean containsP003 = chunk.getItems().stream()
                    .anyMatch(payment -> payment.id().equals("P003"));
                if (containsP003 && failOnce.compareAndSet(true, false)) {
                    throw new IllegalStateException("Injected writer failure");
                }

                for (Payment payment : chunk) {
                    // H2 MERGE used specifically in the integration test.
                    jdbc.update("""
                        MERGE INTO payment_result (id, amount)
                        KEY (id) VALUES (?, ?)
                        """, payment.id(), payment.amount());
                }
            };
        }

        @Bean
        Step importPaymentsStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                @Qualifier("paymentReader") FlatFileItemReader<Payment> reader,
                @Qualifier("paymentWriter") ItemWriter<Payment> writer) {

            return new StepBuilder("importPaymentsStep", repository)
                .<Payment, Payment>chunk(2, transactionManager)
                .reader(reader)
                .writer(writer)
                .build();
        }
    }
}
```

In this example:

1. The reader is `FlatFileItemReader` with a stable name and `.saveState(true)`, so the framework can save state after the first chunk commits.
2. The writer intentionally throws **before writing `P003`**, ensuring the first part committed and the remainder did not on the test datasource. `AtomicBoolean` is only a failure-injection tool in one test; never use such global state in production.
3. H2 uses `MERGE INTO ... KEY(id)` to update by unique key. Production PostgreSQL needs different SQL, such as `INSERT ... ON CONFLICT`, as shown earlier.
4. The restart uses the exact identifying parameters. Non-identifying `inputPath` remains identical across both runs; `sourceVersion` is randomly generated **once for the entire test scenario**, not changed on restart.
5. Assertions check both metadata (`FAILED` then `COMPLETED`, same `JobInstance`) and committed data at the target. Checking only `COMPLETED` fails to prove the writer prevents duplicates.

This test illustrates a writer failure inside **the same database transaction**. It does not prove the behavior of non-transactional APIs or file writers; those scenarios require dedicated tests, including timeouts after the target accepted a side effect.

### 10.3. Additional Test for Overlapping Job Runs

After a successful run, intentionally test running **a new JobInstance** with the same `sourceVersion` and input in a test environment. If output has a unique key and proper upsert, final row count remains four. However, the test must also check payload, record acknowledgment behavior, and external system call counts, because having the same row after upsert does not prove every side effect avoided repetition.

For file writers, test:

- Fresh run to a non-existent path.
- Fresh run when the file already contains data, following reject/replace/version policy.
- Failure after several chunks, restarting the same instance and same file.
- File contains the header exactly once; every business key appears strictly per rules.
- Whether two competing scheduled runs targeting the same output path are blocked or isolated.

## 11. Fixes by Output Type

| Writer type | Preferred solution | What not to assume |
| --- | --- | --- |
| JDBC `INSERT` | Unique constraint by business key; idempotent SQL/upsert; proper transactions | `JdbcBatchItemWriter` deduplicates automatically |
| JPA writer | Proper entity ID/unique key, explicit flush/transaction, business merge | ORM automatically prevents duplicate records if IDs are generated anew |
| Flat file | Stable path per instance, `ItemStream` state, staging/versioned publish | `appendAllowed(true)` is always safe for restart and rerun |
| S3/object storage | Stable key/version, manifest publish, conditional write/object check as appropriate | Upload timeout means the object was not created |
| HTTP API | Stable idempotency key, status query on unknown outcome, bounded retry | Retrying POST is always harmless |
| Message broker | Fixed event ID, transactional outbox, consumer inbox/dedup | A message is delivered exactly once across all failures |
| Multi-thread/partition | Non-overlapping input ranges, isolated state, output constraints | Synchronizing `read()` alone guarantees accurate restart |

In all cases, distinguish two responsibilities: **preventing new duplicates** via technical design, and **remediating existing duplicates** via controlled reconciliation/recovery. Never run bulk delete commands based on conditions unconfirmed with the data owner.

## 12. Common Mistakes When Fixing Duplicates

### 12.1. "Adding `DISTINCT` to Every Query Fixes It"

`DISTINCT` can eliminate physically identical rows in one query, but it cannot prevent two API calls or two database inserts at different times. It can also accidentally merge two legitimate transactions that share the same amount and timestamp. Use it only when input logic genuinely requires a unique set and selection keys are confirmed.

### 12.2. "Disable Retry to Eliminate Duplicates"

Disabling retries may reduce attempts, yet causes more batch failures and does not solve reruns or restarts. A real-world system must still survive process crashes or scheduler re-dispatches. **Idempotency at the point of effect** is the necessary safeguard.

### 12.3. "`JobRepository` Will Prevent Every Overlapping Job"

The repository manages state per `JobInstance`. If job names or identifying parameters differ, two instances can write to the same output concurrently. Furthermore, schedules across multiple nodes require separate coordination. Do not treat `JobRepository` as a general distributed lock for all output resources.

### 12.4. "As Long as `writeCount` Equals Input Count, Everything Is Fine"

`writeCount` measures items passed to the writer and reported as written per step execution. With upserts, the count of **new** rows at the target may be smaller. If the writer calls an external API, the writer may report completion while the target system holds a different state. Reconcile by business key against actual output.

### 12.5. "After Restart, Delete the Old File and Write From Scratch"

Deleting a partial file for a writer with a checkpoint while keeping the reader's offset causes the file to **lose the already committed portion**. Conversely, keeping the old file and reading from the beginning easily creates duplicates. If you want to rerun from scratch, design a separate workflow with input/output versioning rather than calling it a normal restart.

### 12.6. "Use `INSERT IGNORE` to Swallow All Errors"

Some dialects offer conflict-ignoring syntax, yet that can hide **payload differences** or data errors needing review. Idempotent does not mean "silently ignore". When the same business key arrives with different content, define a policy: reject, flag conflict, audit, or update version according to the business contract.

## 13. Monitoring and Alerting on Duplicates

To catch bugs early, observe **runs**, **business keys**, and **acknowledged output** together:

| Signal | Meaning |
| --- | --- |
| Two different `JobInstance`s with same `businessDate/sourceVersion` | Scheduler/rerun may be creating duplicate work |
| Two concurrent executions writing one output path | Risk of interleaved/duplicated file lines |
| Rising unique constraint violations | Writer receiving existing keys again, or duplicate input/partitions |
| Many `ON CONFLICT`/upserts relative to new items | Source or retry/rerun needs investigation, though not always an error |
| Sharp spike in retry/rollback counts | Infrastructure issues causing replay and non-transactional side effects |
| Same idempotency key sent repeatedly | Retries/redeliveries occurring; check actual target outcome |
| Input count mismatches output business key count | Missing, filtered, skipped, or duplicated items; reconcile across pipeline |
| Repeated file headers/data blocks | Appending or publishing the same file multiple times |

A structured log template:

```text
event=batch.output.write
jobName=importOrdersJob
jobInstanceId=221
jobExecutionId=845
stepExecutionId=1082
businessDate=2026-11-16
sourceVersion=feed-v3
outputAlias=orders-result
writeMode=UPSERT
```

Do not put full sensitive payloads, passwords, tokens, or presigned URLs in logs. For observability backends like Micrometer/Prometheus, avoid using `orderId`, `paymentId`, and `jobExecutionId` as metric labels due to high cardinality. Detailed IDs belong in authorized audit/logs; metrics only need job name, outcome category, or error category.

### Period Reconciliation

In a 1-input-to-1-output pipeline (with no filtering, skipping, or item aggregation), you can expect:

```text
Unique input business keys
        =
Unique output business keys
```

However, in real pipelines, processors may filter, one item may generate multiple outputs, or writers may aggregate. Therefore, reconciliation rules must follow the **business contract** rather than imposing a 1:1 formula on every job. In particular, summing `readCount` across multiple executions in a restart chain can double-count items read during rolled-back chunks; it is not the unique source record count.

## 14. Handling Duplicates Already Present in Production

When duplicates are found in results currently consumed by users, handling must both restore data correctness and preserve forensic evidence.

1. **Stop further generation:** pause related triggers or block result publishing if permitted; do not blindly delete live data.
2. **Determine business identity:** is the same `paymentId` truly a duplicate or distinct versions/events?
3. **Preserve evidence:** `JobParameters`, `JobExecution`/`StepExecution`, logs, source manifests/checksums, SQL keys, output file versions, and API request IDs.
4. **Analyze the failure boundary:** duplication from input, writer, retry/restart, schedule/concurrency, or downstream consumer.
5. **Design the fix:** unique constraints, output versioning, idempotency keys, stable checkpoints, scheduler locks, or reader/partition fixes.
6. **Re-test with failure injection:** fail mid-chunk, timeout after side effect, restart the same instance, and rerun per period to prove non-recurrence.
7. **Clean up legacy data under control:** export proposed remediation list, assess impact, and modify/delete only under a data-owner-approved workflow with auditing and rollback capability.

For monetary data, deleting a "duplicate row" in a database does not undo a payment already recorded by a partner. You need a business compensation/reconciliation workflow per the target system's rules; never treat a SQL `DELETE` as reversing an external side effect.

## 15. Choosing a Duplicate-Prevention Measure

```text
Detect duplicate output
           |
           v
Does input source already have the same business key?
    |                     |
   Yes                   No
    |                     |
    v                     v
Define dedup/          Multiple JobInstances /
validation rule        triggers for same period?
                          |             |
                         Yes            No
                          |             |
                          v             v
                    Fix params/      Duplicates happen
                    scheduler/lock   around rollback/retry?
                                         |            |
                                        Yes           No
                                         |            |
                                         v            v
                                  Check txns,     Check JOINs,
                                  idempotency,    file append,
                                  checkpoints     partitions, writer
                                         \            /
                                          v          v
                                    Add output constraints
                                    + fail/restart tests
```

**Conclusion:** a writer producing duplicate output is not always a single-line bug inside `write()`. It can stem from source data, transaction boundaries, `JobParameters`, `ExecutionContext`, how files are opened, retry logic, or multiple executions mutating a shared resource. The durable fix is **defining business keys, enforcing idempotency at the destination, keeping checkpoints sound, and testing with real mid-chunk failures**. Then normal runs, restarts, and intentional reruns all yield accountable results.

## References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunking, transactions, and commit mechanics.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close` contract and `ExecutionContext` for restart.
- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): `FlatFileItemWriter`, file state, and writer configuration.
- [Spring Batch Reference — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): `JdbcBatchItemWriter`, paging/cursors, and JDBC.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retries in fault-tolerant steps.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobParameters`, `JobExecution`, and restart.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): support for testing jobs, steps, and failure/restart.
