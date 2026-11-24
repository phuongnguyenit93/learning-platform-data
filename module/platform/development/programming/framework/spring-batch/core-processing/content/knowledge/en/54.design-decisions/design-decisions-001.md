# Choosing Chunk vs. Tasklet in Spring Batch Design

## 1. Why Must You Choose Between Chunk and Tasklet?

When creating a step in Spring Batch, a critical decision is **how the unit of work will be managed by the framework**. The same requirement—such as "import an order file and then mark the batch as processed"—can be coded using a hand-written loop inside a tasklet or using `ItemReader`, `ItemProcessor`, and `ItemWriter` in a chunk-oriented step. Both can get the job done, but they differ significantly in **transaction boundaries, checkpointing, restartability, statistics, retry/skip, and maintenance cost**.

For example:

- Need to verify that the input file exists and has a valid header before processing: a short operation, usually suited for a **tasklet**.
- Need to read 2 million CSV rows, normalize each record, and write to a database in groups: usually suited for a **chunk**.
- Need to execute a conditional SQL `UPDATE` statement to change the status of an entire batch: a **tasklet** may suffice if execution time and transactions are under control.
- Need to copy 100,000 objects between two storage repositories, handle errors per individual object, and resume after failure: you should typically model each object as a **chunk item**, rather than writing an uncheckpointed loop inside a tasklet.

In the context of **Spring Batch Core Processing → Design Decisions**, the goal is to choose the model that fits the *business and operational behavior* of the step. Data row count is an important signal, though not the sole criterion.

## 2. Execution Models of Both Step Types

### 2.1. Chunk-oriented Step

A chunk step organizes processing into units of items:

```text
                    Job
                     |
                     v
              chunk-oriented Step
                     |
           +---------+---------+
           |                   |
       ItemReader<I>       Transaction
           |                   |
           v                   |
       ItemProcessor<I,O>      |
           |                   |
        O or null              |
           |                   |
           v                   |
       ItemWriter<O>           |
           |                   |
      commit chunk ------------+
           |
         repeat
           |
     Step COMPLETED/FAILED
```

With `chunk(100, transactionManager)`, Spring Batch attempts to collect up to 100 read items in a chunk, process them, and write them before committing the chunk's transaction. Within a chunk, the processor may return `null` to filter an item; the number of items actually passed to the writer may be smaller than the number read.

For example, given a file with 250 items, no filtering/skipping, and all operations succeeding:

```text
Chunk 1: read 1..100   -> process -> write -> COMMIT
Chunk 2: read 101..200 -> process -> write -> COMMIT
Chunk 3: read 201..250 -> process -> write -> COMMIT
```

The framework provides built-in reader/processor/writer abstractions, `readCount`, `writeCount`, `filterCount`, and `skipCount` counters, fault tolerance mechanisms, and restart support via `ItemStream`/`ExecutionContext` when components are designed properly.

**Chunk does not mean "each item is a transaction."** A chunk is the standard transaction boundary; if the writer calls an external API, the JDBC transaction does not automatically roll back side effects on that API.

### 2.2. Tasklet Step

A tasklet step runs a block of application-defined logic:

```text
                    Job
                     |
                     v
                Tasklet Step
                     |
                 execute(...)
                     |
             +-------+---------+
             |                 |
     RepeatStatus.FINISHED   RepeatStatus.CONTINUABLE
             |                 |
      complete step       call execute(...) again
```

`Tasklet.execute(StepContribution contribution, ChunkContext chunkContext)` is the callback that performs the work. It can return:

- `RepeatStatus.FINISHED`: no further calls needed; the step completes if there are no errors.
- `RepeatStatus.CONTINUABLE`: the framework may invoke the tasklet again according to the repeat policy.

In a typical `TaskletStep`, each tasklet execution runs within the transaction scope configured by the step. If the tasklet performs a very large operation in **a single execute call**, the corresponding transaction can be long-lived; if you manually split the work across multiple `CONTINUABLE` invocations, the application must manage progress, idempotency, and appropriate stopping/restarting.

**A tasklet does not have a framework-orchestrated reader/processor/writer triad.** You can write a loop inside a tasklet, but doing so makes you responsible for most of the capabilities that a chunk-oriented step provides out of the box.

## 3. Comparison Table for Decision-Making

| Criterion | Chunk-oriented step | Tasklet step |
| --- | --- | --- |
| Unit of work | A stream of items read, transformed, and written | A developer-defined action or business block |
| Programming model | `ItemReader` → `ItemProcessor` → `ItemWriter` | `Tasklet.execute(...)` |
| Transaction | Typically committed per chunk | Typically per `execute` invocation |
| Checkpoint/restart | Convenient infrastructure via `ItemStream` and stateful readers/writers | Must manually organize state if the action has multiple phases |
| Skip failing items | Built-in `skip` and `skipLimit` mechanisms | Must classify and decide on errors in custom logic |
| Retry item/operation | Supported by chunk step fault tolerance | Can use service-level retry or custom mechanisms |
| Read/write/skip metrics | Standard counters on `StepExecution` | No auto-generated item counters without item-based mechanisms |
| Large data processing | Well-suited for streaming, pagination, item-by-item | Suitable if the action is bounded or set-based at the source |
| One-off logic | Possible, but often overly structured | Concise and direct |
| File reading, parsing, transforming, writing | Very well-suited | Usually requires hand-written loop/checkpoint |
| File management/move/rename | Possible, not mandatory | Usually well-suited |
| Parallel scaling | Built-in partitioning, multi-threaded chunk, and scaling models | Must design concurrency manually if splitting into multiple units |
| Setup cost | More components | Fewer components for simple operations |
| Misdesign risks | Transaction/restart/reader state issues | Overly long loop, no checkpoint, manual retry and metrics |

From this table, a guiding rule emerges:

> **If a step processes multiple independent units, needs group commits, and requires item-level progress tracking, prefer chunk. If a step is a well-scoped action that finishes once executed, prefer tasklet.**

This rule has exceptions. A set-based SQL statement processing millions of rows may still fit a tasklet if the database executes the entire operation and the transaction/locking plan has been evaluated. Conversely, generating 20 independent report files may fit a chunk if per-file retry is needed.

## 4. Practical Decision Tree

```text
What does the step need to do?
    |
    +-- A bounded single action?
    |      |  e.g.: check manifest, create directory, mark READY
    |      +--> TASKLET
    |
    +-- Iterate over multiple elements/records?
           |
           +-- Can each element be processed, skipped, or retried individually?
           |      +--> CHUNK
           |
           +-- Need checkpoint/resume after committed chunks?
           |      +--> CHUNK
           |
           +-- Can the entire work be delegated to a single SQL/set-based statement?
                  |
                  +-- Are transaction duration and locks within acceptable limits?
                  |       +--> TASKLET may be suitable
                  |
                  +-- Transaction too large, need to split work and observe progress?
                          +--> CHUNK or split work with explicit checkpoints
```

Questions to ask when evaluating a step:

1. **Does the input have clear units?** A record, object key, message, customer, invoice, or just a "close period command"?
2. **Does each unit have its own outcome?** Do you need to skip a malformed row, retry a failed request, write to quarantine, or count items?
3. **How long can a single run take?** If it fails at 99% progress, do you need to resume rather than start over from the beginning?
4. **Where should transactions commit?** Every 100 items, per SQL statement, or after the entire batch?
5. **Does the output have side effects outside the transaction?** Sending email, calling a payment API, writing to object storage?
6. **Are there scale and concurrency expectations?** Multiple workers, partitions, remote chunking?
7. **Do you need standard read/write/skip metrics?** Or just the outcome and duration of a single action?

Once answered, the choice is usually much clearer than guessing from a step name like "import", "cleanup", or "sync".

## 5. When Tasklet Is the Right Choice

### 5.1. Preflight and Batch-Level Validation

Before importing a CSV, the job needs to verify that the file exists, is readable, conforms to the schema, and has been published by upstream. This is an input/output-bounded operation:

```text
preflightStep:
  input  = location + source version
  output = pass or failure with reason
```

There is no clear benefit to creating an `ItemReader` just to "read one file object" and pass it to a writer. A tasklet that takes the resource, validates it, and finishes is much easier to understand.

### 5.2. One-Time Infrastructure Operations

Examples:

- Checking access permissions to the source before running an import.
- Creating a staging directory if allowed by the contract.
- Checking a `_SUCCESS` marker or manifest.
- Confirming that the staging table is prepared.
- Running a narrowly scoped `UPDATE` or `DELETE` statement.
- Marking the batch `READY_FOR_PUBLISH` once reconciliation passes.

These operations can have side effects; therefore, appropriate transactions or idempotency are still required. **A simpler tasklet does not mean you can skip recovery considerations.**

### 5.3. Executing an Operation at the Source

Suppose the database already holds staging data; a single SQL statement can update the status of valid rows:

```sql
UPDATE staging_orders
SET validation_status = 'READY'
WHERE source_id = :sourceId
  AND validation_status = 'NEW';
```

A tasklet invoking this SQL statement makes sense if the operation is short enough, repeatable, and backed by proper indexes and transaction settings. There is no need to pull millions of rows from the database into Java and update them row by row just to perform a set-based operation.

However, on very large tables, the SQL statement may hold locks for a long time, generate heavy undo/redo logs, or exceed timeouts. You must evaluate the query plan, database batch size, and recoverability; sometimes splitting into units via chunk is better.

## 6. Practical Tasklet Examples in Spring Batch 5.x

The Java examples in this article use **Java 17+, Spring Batch 5.x, and Spring Framework 6 / Spring Boot 3.x**. Infrastructure beans `JobRepository`, `PlatformTransactionManager`, and `DataSource` are assumed to be configured. Spring Batch 6.x has changes in some packages/APIs, so consult the documentation for your exact version when integrating.

### 6.1. An Input-Validation Tasklet

Suppose `inputPath` is an internal path **already approved by the server** and points only to the job's staging directory:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
Tasklet validateInputTasklet(
        @Value("#{jobParameters['inputPath']}") String inputPath) {

    return (contribution, chunkContext) -> {
        Path input = Path.of(inputPath);

        if (!Files.isRegularFile(input)
                || !Files.isReadable(input)
                || Files.size(input) == 0) {
            throw new IllegalStateException(
                    "Input file is missing, empty or unreadable");
        }
        return RepeatStatus.FINISHED;
    };
}
```

This is a **minimal validation** example. In a real application, add schema/manifest checks and enforce path containment within an approved root; never accept arbitrary paths from callers to read with the service account's privileges. `isReadable()` only checks at a single point in time; handle actual open errors and use a stable source snapshot.

`@StepScope` allows the `inputPath` parameter to be resolved when the step runs; the bean does not depend on a hardcoded path captured at startup.

### 6.2. Configuring TaskletStep

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .build();
}
```

When `validateInputTasklet.execute(...)` returns `FINISHED`, the step can complete. When it throws an exception, the step typically ends as `FAILED` and a standard sequential flow does not proceed to the import step.

### 6.3. Tasklet Updating Status with Bounded SQL

Another example: after reconciliation succeeds, mark the batch as ready:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
Tasklet markReadyTasklet(
        @Value("#{jobParameters['sourceId']}") String sourceId,
        JdbcTemplate jdbcTemplate) {

    return (contribution, chunkContext) -> {
        jdbcTemplate.update("""
            UPDATE import_control
            SET state = 'READY'
            WHERE source_id = ?
              AND state = 'VALIDATED'
            """, sourceId);

        return RepeatStatus.FINISHED;
    };
}
```

This assumes the `import_control` table and `source_id` already exist, with state `VALIDATED` as the allowed transition precondition. A rerun will not duplicate the effect if the state is already `READY`, though you must clearly define what happens when the updated row count is 0: already processed, missing source, or precondition violation? You should log an audit entry or check the prior state per contract.

If using the same `DataSource` and transaction manager with `JdbcTemplate`, JDBC changes can participate in the tasklet's transaction. If the tasklet calls an HTTP API or writes a file outside the database, JDBC rollback **does not automatically undo** that effect.

## 7. When Chunk Is the Right Choice

A chunk-oriented step is especially valuable when the work involves **many items with a relatively uniform processing lifecycle** and requires one or more of the following traits:

- Streaming to avoid loading the entire dataset into memory.
- Committing in groups to avoid an overly large transaction.
- Restarting from a saved checkpoint.
- Skipping invalid records within a limit.
- Retrying transient errors in the reader/processor/writer according to a policy.
- Tracking read/write/filter/skip counts.
- Scaling via multi-threading, partitioning, or remote processing when the model permits.

Example:

```text
orders.csv (500,000 records)
       |
       v
 FlatFileItemReader<OrderRow>
       |
       v
 ItemProcessor<OrderRow, OrderRow>
       |-- validate amount
       |-- normalize business key
       |-- return null if intentionally filtered
       v
 JdbcBatchItemWriter<OrderRow>
       |
       v
    database, commit every 500 items
```

A chunk step does not strictly require a processor: if you only read and write, you can omit `ItemProcessor` and configure the reader and writer directly.

## 8. Chunk Example: Reading CSV and Writing to Database

Suppose the input is:

```csv
order_id,amount
ORD-001,100.00
ORD-002,150.50
ORD-003,75.00
```

Database:

```sql
CREATE TABLE imported_order (
    order_id VARCHAR(80) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
```

### 8.1. Model and Reader

```java
import java.math.BigDecimal;

public record OrderRow(String orderId, BigDecimal amount) {}
```

```java
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputPath']}") String inputPath) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("orderCsvReader")
            .resource(new FileSystemResource(Path.of(inputPath)))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("order_id", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

The example assumes `inputPath` has been validated against an allowed source and the input is a simple CSV with a verified header. `FlatFileItemReader` uses `ItemStream`/`ExecutionContext` to support restart when given a stable name, appropriate `saveState`, and an unchanged input source.

### 8.2. Validating and Normalizing Processor

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
ItemProcessor<OrderRow, OrderRow> orderProcessor() {
    return item -> {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new IllegalArgumentException("order_id is required");
        }
        if (item.amount() == null
                || item.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive");
        }
        return new OrderRow(
                item.orderId().strip(),
                item.amount().setScale(2, RoundingMode.HALF_UP)
        );
    };
}
```

Do not configure `skip(IllegalArgumentException.class)` across the board by default, as it can mask bugs; in production, define dedicated exceptions for invalid data and determine the policy per business rules.

### 8.3. Batch JDBC Writer

```java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<OrderRow> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderRow>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order(order_id, amount)
                VALUES (:orderId, :amount)
                """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("orderId", row.orderId())
                            .addValue("amount", row.amount()))
            .build();
}
```

`JdbcBatchItemWriter` sends multiple parameter sets in a JDBC batch to reduce database round-trip overhead. If `order_id` is duplicated, a unique constraint can cause the chunk to fail and roll back per the database/transaction policy; when re-imports are needed, add proper idempotency/upsert design rather than simply dropping the constraint.

### 8.4. Creating the Chunk Step

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderRow> orderProcessor,
        JdbcBatchItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

The value `500` is only an example, not an optimal default chunk size. Measure with actual item size, database latency, memory footprint, transaction duration, and acceptable rollback blast radius.

## 9. Combining Tasklets and Chunks in One Job

In many applications, the right choice is **using the appropriate model for each step**, rather than forcing one step type across the entire job.

```text
importOrdersJob
     |
     v
validateInputStep         Tasklet: file exists, checksum/schema
     |
     v
importOrdersStep          Chunk: read each order, validate, write to DB
     |
     v
reconcileTotalsStep       Tasklet: compare control totals
     |
     v
publishBatchStep          Tasklet: mark data ready for consumption
```

Flow configuration example:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importOrdersStep,
        Step reconcileTotalsStep,
        Step publishBatchStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
            .next(importOrdersStep)
            .next(reconcileTotalsStep)
            .next(publishBatchStep)
            .build();
}
```

`reconcileTotalsStep` and `publishBatchStep` in the example are project-defined steps whose implementations were not shown in the earlier code snippets. A sequential flow like this only advances when the preceding step satisfies the flow's success transition criteria.

A key point is not to publish data into final consumption scope **before quality gates pass**. If the import chunk has partially committed, a failure in the final reconciliation tasklet will not automatically roll back all previously committed chunks. You can import into staging and only publish once validated, or design output states like `PENDING/VALIDATED` so downstream consumers do not see incomplete batches.

## 10. Transactions: The Difference That Often Drives Architecture

### 10.1. Group Commits in Chunks

With `chunk(100)`, after 100 items are read and processed successfully, the writer writes them within the chunk's transaction and commits. If a subsequent chunk fails, data from previously committed chunks may remain.

```text
Chunk 1: 100 items -> COMMIT
Chunk 2: 100 items -> COMMIT
Chunk 3: item 251 fails -> ROLLBACK/FAILED
```

This preserves progress and reduces transaction size, but imposes a requirement for **safe restart and reprocessing**.

### 10.2. A Single Tasklet Call Can Be a Long Transaction

If a tasklet is written as:

```java
return (contribution, context) -> {
    for (OrderRow row : loadMillionRows()) {
        jdbcTemplate.update("UPDATE ...", /* parameters */);
    }
    return RepeatStatus.FINISHED;
};
```

then the entire loop may execute inside **one `execute` call and one long-lived transaction** (when the JDBC operations join the tasklet's transaction). Consequences can include long lock retention, high memory usage, expensive rollbacks, and no framework-supported item-level checkpointing. This is a sign you should switch to a chunk step or a controlled-transaction database set-based strategy.

### 10.3. Sharing a Transaction Manager Is Not Enough Across Multiple Systems

A chunk or tasklet may write to a database and send messages. A JDBC transaction does not automatically encompass an HTTP API, filesystem, or message broker. For external side effects, you need:

- An idempotency key based on a stable business key.
- An outbox or an appropriate post-commit publication pattern.
- The ability to replay without duplicating results.
- Classifying timeouts as "outcome unknown—succeeded or failed".

Choosing chunk only lets the framework manage item processing boundaries; it does not turn multiple systems into a single ACID transaction.

## 11. Restart and Checkpointing: The Most Important Factor for Long Datasets

### 11.1. Chunk and ItemStream

Stateful readers and writers can implement `ItemStream`:

```java
void open(ExecutionContext executionContext);
void update(ExecutionContext executionContext);
void close();
```

Spring Batch uses `ExecutionContext` to persist checkpoint state when needed. For example, `FlatFileItemReader` can store the read position in the file after commits, allowing restart from the right position instead of re-reading from the start.

For reliable restarts:

- Stable reader and step names.
- `saveState` configured appropriately.
- Input source unchanged between executions of the same `JobInstance`.
- `JobRepository` retained.
- Writer does not create duplicates if items are replayed.
- Processor avoids uncheckpointed mutable state or has its own save/restore mechanism.

**Not every `ItemReader` is restartable** simply because it is used in a chunk. Custom readers must honor the `ItemStream`/`ExecutionContext` contract; non-repeatable sources like message streams require dedicated strategies.

### 11.2. Tasklet and Custom Progress

Simple tasklets like checking a file or flipping a status once generally **do not need internal checkpoints**: if they fail, the whole operation can simply run again on job restart, provided the operation is safe to repeat.

If a tasklet processes thousands of units, the application must manually manage:

- Which unit has been processed so far.
- When state is committed alongside output.
- How to skip already-completed portions.
- How to handle a crash after a side effect but before writing the checkpoint.
- How to verify that the input data has not changed on restart.

If the answer is "I'll save the offset myself, retry myself, skip myself, and count items myself," that is a strong signal that **chunk already solves most of the problem**.

### 11.3. Status of Already-Completed Steps

On a restart, `COMPLETED` steps are typically skipped under default configuration, while incomplete steps can run again. This applies to both tasklet steps and chunk steps.

Example job:

```text
validateInputStep (Tasklet) COMPLETED
importOrdersStep  (Chunk)   FAILED
```

When restarting the same `JobInstance`, `validateInputStep` usually does not need to run again. If you always want to re-check read permissions or the manifest, you can consider `allowStartIfComplete(true)` for the preflight step, keeping in mind that the check result could change and should stay tied to the same input snapshot.

## 12. Retry, Skip, and Filter: Why Chunk Is More Convenient

Suppose a 100,000-row file has 10 rows with business formatting errors and the database occasionally deadlocks.

With chunk, you can configure:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderDataException.class)
        .skipLimit(20)
        .retry(TransientDatabaseException.class)
        .retryLimit(3)
        .build();
```

`InvalidOrderDataException` and `TransientDatabaseException` in the example are application-defined exceptions or adapter classifications; you must create the classes and map specific errors before using them. Do not skip or retry all `Exception` types, as that easily hides bugs or retries unrecoverable errors.

A chunk-oriented step provides:

- `filterCount` when the processor returns `null`.
- `processSkipCount` when an item is skipped in the processor.
- `readSkipCount` and `writeSkipCount` when errors are skipped in the reader/writer.
- `rollbackCount` when a transaction rolls back.
- `SkipListener` to record audits of skipped items.

With a tasklet, you can write logic to catch exceptions, retry, or write to quarantine, but `StepExecution` does not automatically generate item counters like chunk does without extra coding.

**Do not confuse retry with exactly-once.** Chunk retry can cause the processor or writer to be invoked again. For APIs or filesystems, you must ensure side effects are idempotent regardless of whether the model is chunk or tasklet.

## 13. Performance: Is Chunk Always Faster?

No. Performance depends on the operation type and I/O cost.

### 13.1. When Chunk Reduces Overhead

For JDBC inserts, a writer can send multiple items in a single batch, reducing round-trips and commit count compared to committing each item individually. For large files, streaming readers keep memory stable compared to loading the entire file into a `List`.

Chunk size too small:

- Increases transaction/commit count.
- Increases framework and database overhead.
- Reduces throughput for write operations with latency.

Chunk size too large:

- Holds many items in memory.
- Can cause long transactions and extended lock holds.
- Requires redoing more work on rollback.
- Increases commit wait times and resource pressure.

Evaluate chunk size based on throughput, transaction latency, memory, rollback/retry cost, writer speed, and downstream load capacity.

### 13.2. When Tasklet Is More Efficient

A SQL statement:

```sql
UPDATE orders
SET archive_flag = true
WHERE business_date < :cutoff
  AND archive_flag = false;
```

executed set-based by the database can be more efficient than Java reading each order and updating it one by one. However, if the number of affected rows is very large or long lock holds are unacceptable, split it into batches/tranches with an appropriate checkpoint/commit plan.

When a task only checks a file by opening a stream or invokes a stored procedure that already manages its transaction, creating a chunk step just to process a single item usually adds unnecessary complexity.

### 13.3. Operational Cost Is Also Performance

A hastily written tasklet with a big loop may save a few dozen lines of code, but it sacrifices the ability to restart after 90% progress, increasing incident recovery time. For critical batch jobs, **recovery time** is part of system performance, not just happy-path throughput.

## 14. Scaling and Concurrency

Chunk steps have built-in models to distribute work:

- Multi-threaded step with `TaskExecutor` when the reader/writer and data source properly support concurrency.
- Partitioning: dividing data into partitions, each with its own `StepExecution` and input range.
- Remote chunking or remote processing models for distributed systems, depending on architecture/version.

Enabling multi-threading is not safe by default: `FlatFileItemReader` and many stateful readers are typically not thread-safe if shared. When throughput is needed, you can split the input into separate partitions and give each worker its own independent reader.

A tasklet can also run a thread pool or split work, but then the application must manually manage work distribution, checkpointing, partial state, retry, and cancellation. If the work naturally consists of many independent items, chunk/partitioning is usually clearer.

**Warning on worker count:** increasing concurrency can cause contention, saturate the connection pool, or trigger rate limits on external APIs. Choosing chunk or tasklet does not replace capacity planning.

## 15. Logging and Monitoring per Model

| Information | Chunk-oriented step | Tasklet step |
| --- | --- | --- |
| `JobExecution` / `StepExecution` status | Yes | Yes |
| Step start/end, duration | Yes | Yes |
| `readCount` / `writeCount` | Follows item processing semantics | Usually does not reflect business record count if operations bypass reader/writer |
| `filterCount` / skip counts | Available | Not auto-generated per item |
| Chunk commit/rollback | Tracked by framework | Does not directly map to sub-task counts |
| Affected SQL record count | Query writer/DB if exact count is needed | Use row count from operation and audit |
| Retry attempts | Needs instrumentation for detailed counts | Self-instrumented in service/policy |

For example, `JdbcBatchItemWriter` receives 500 items but uses an upsert that ignores 20 duplicates; `writeCount` may still reflect the 500 items written by the framework, not the number of newly inserted database rows. For a tasklet running an `UPDATE` on 1,000 rows, `StepExecution.writeCount` does not automatically become 1,000 because there is no `ItemWriter`.

Therefore, define metrics with clear semantics:

```text
job_execution_status
step_execution_status
chunk_read_count / chunk_write_count
business_records_inserted
business_records_updated
tasklet_operation_duration
validation_failure_reason
```

These names are conceptual; actual metric names/tags exported via Micrometer/Prometheus depend on configuration and framework version. Do not use `jobExecutionId` or `stepExecutionId` as high-cardinality metric labels; keep them in logs or traces.

## 16. Design Scenarios to Consider

| Problem | Typical Reasonable Choice | Reason |
| --- | --- | --- |
| Check if input file is readable | Tasklet | A bounded preflight operation |
| Validate header, checksum before import | Tasklet | Source/batch-level check |
| Read large CSV and import each order | Chunk | Has items, commits, skip/retry, restart |
| Read table and transform each customer | Chunk | Needs record-by-record processing |
| Conditionally clear a small staging table | Tasklet | A single SQL statement with clear scope |
| Execute a set-based SQL statement updating an entire period | Tasklet conditionally | DB processes directly; must evaluate transaction/locks |
| Send 100,000 transactional emails | Chunk or dedicated queue | Many items, per-item retry, idempotency |
| Send a "period closed" notification | Tasklet | A bounded action, requires idempotency |
| Move one file after completion | Tasklet | Operation on a single resource |
| Move 50,000 independent objects | Chunk | Track/retry/checkpoint each object |
| Reconcile period total amount | Tasklet or aggregate query step | Single aggregate result if data is already staged |
| Compute totals by parsing every record and saving each result | Chunk | Data has items and needs processing control |
| Wait for a file to appear using an infinite loop | Usually delegate to scheduler/orchestrator | Avoids holding workers/transactions and hiding upstream failures |
| Call a stored procedure designed for the whole batch | Tasklet conditionally | Single operation with transaction and recovery contract |
| Fetch paginated API and write each record | Chunk if a suitable cursor/reader exists | Retry, page checkpoint, output items |
| Clean up 1,000,000 records in batches | Strategy-dependent | Set-based SQL can be fast, though chunk helps if splitting commits |

### Example 1: "Send Report"

If the requirement is **to generate one summary PDF file from queried data**, a tasklet creating the output file may suffice, though it must handle temporary files, atomic publishing, and retries. If the requirement is **to generate 100,000 separate PDF reports for individual customers**, each report is an item, so consider chunking and per-customer idempotency.

### Example 2: "Sync Data"

If syncing is a database `MERGE` statement with clear conditions, a tasklet makes sense. If syncing requires calling an API per customer, handling HTTP 429, and saving status per customer, chunk is usually more helpful. Same word "sync," different work boundaries.

### Example 3: "Delete Old Data"

A `DELETE WHERE created_at < cutoff` on a small table can run in a tasklet. For a large table with hundreds of millions of rows, you must evaluate partitioning, transaction size, indexes, and scheduling; you might choose database partition management or chunking the keys to delete. There is no rule that tasklets are only for small row counts.

## 17. Common Problematic Designs

### 17.1. Tasklet Containing a Loop That Reads, Processes, and Writes Millions of Items

```java
public RepeatStatus execute(
        StepContribution contribution, ChunkContext context) {
    while (hasNext()) {
        var item = read();
        var mapped = process(item);
        write(mapped);
    }
    return RepeatStatus.FINISHED;
}
```

This essentially reimplements chunk processing, but usually lacks checkpointing, commit intervals, skip/retry, and standard metrics. If the goal is to process a stream of items, split it into reader/processor/writer and use chunk.

### 17.2. Chunk with a Dummy Reader That Emits Only One Element

If the requirement is to delete a processed file, creating a reader that emits one item `"delete-this-file"` and a writer that deletes it will work, but makes the flow harder to read than a tasklet with a clear single action. Do not invent item abstractions just to force chunk usage at all costs.

### 17.3. Using a Tasklet to Wait for Data Forever

```java
while (!Files.exists(input)) {
    Thread.sleep(1000);
}
```

This polling pattern can hold transactions/threads for a long time, has no deadline, and causes the job to hang instead of surfacing upstream status. Use a scheduler, event-driven trigger, ready marker, and bounded retry/backoff outside transactions where appropriate.

### 17.4. Assuming a Tasklet Automatically Restarts Mid-Loop

A tasklet does not automatically know "already processed up to item 50,000." To resume, you must manage checkpointing and idempotency manually; that is one reason to use chunk for multi-item datasets.

### 17.5. Deleting Spring Batch Metadata to Rerun

When a chunk has partially committed, deleting `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION` can break restart/checkpoint logic. Tasklets that already produced side effects also risk running again. You must distinguish **restarting the same instance**, **rerunning to create a new instance**, and **reprocessing a different data version**.

### 17.6. Non-Idempotent Tasklet Operations

For example, a tasklet sends a "pay now" command and then the process crashes before metadata is marked successful. On restart, the operation may be called again. If the side effect cannot be rolled back, you need an idempotency key or appropriate transactional orchestration.

### 17.7. Using Chunk to Expect an "All-or-Nothing" Job-Wide Transaction

Chunks commit in groups. If the requirement is that final data only appears when **the entire batch meets quality standards**, use staging and a post-validation publish step. You cannot assume a `FAILED` job will roll back all previously committed chunks.

## 18. Testing the Design Decision

Model selection must be validated by failure behavior, not just happy-path execution.

### 18.1. Testing the Preflight Tasklet

For `validateInputTasklet`:

1. Create a valid file in the test directory → tasklet returns `FINISHED`.
2. Create an empty file or missing path → tasklet throws an exception.
3. Run an integration test with both the preflight step and import step → when preflight is `FAILED`, the import step does not run.
4. Rerun after the source becomes valid → verify no side effects were left behind from the failed run.

With Spring Batch 5.x, `spring-batch-test` provides `@SpringBatchTest` and `JobLauncherTestUtils` for integration tests. A tasklet can be unit tested directly by mocking `StepContribution` and `ChunkContext` if the logic only uses those two objects; if it doesn't need them, you can extract validation into a separate service for easier testing.

### 18.2. Testing Chunk with a Failure Between Two Commits

With a 250-item file and `chunk(100)`:

1. Reader reads 250 items, processor transforms, writer writes to DB.
2. Intentionally trigger a non-skippable error on item 150.
3. Verify the step fails, and inspect committed data according to the transaction policy.
4. Fix the root cause of the failure while preserving the input snapshot and `JobRepository`.
5. Restart the same `JobInstance`, verify all 250 business records exist with no duplicates and no omissions.

Do not assume the row count after the failure equals 100 in every configuration: readers/writers may have special behavior, a different transaction manager, or side effects outside the transaction. Inspect the actual database alongside `StepExecution` metadata to confirm.

### 18.3. Testing Skip and Retry in Chunk

Scenario:

```text
Input 5 items:
  A valid
  B valid
  C invalid -> skippable
  D dependency timeout on first attempt, OK on next
  E valid
```

When skip/retry policies allow, the expected business result is 4 valid items processed, `processSkipCount=1` if the error occurs in the processor, and no duplicate output from retries. Other counters depend on the implementation and transaction policy.

### 18.4. Assertion Example in an Integration Test

```java
JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
                .addString("inputPath", approvedInput.toString())
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters()
);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution importStep = execution.getStepExecutions().stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(3, importStep.getReadCount());
assertEquals(3, importStep.getWriteCount());
assertEquals(3, countImportedOrdersFromDatabase());
```

This snippet illustrates a test with pre-configured launcher, `approvedInput`, `countImportedOrdersFromDatabase()`, JUnit imports, and context. The goal is to assert both **metadata** and **actual outcomes**. When using a fixture file with a different record count or filtering logic, adjust expectations accordingly.

### 18.5. Testing Restart of a Tasklet with Side Effects

If a tasklet updates state via SQL:

- Trigger an error after the operation has committed or simulate a crash at a realistic point.
- Restart the exact instance or rerun per system policy.
- Verify the conditional update does not re-trigger unintended effects.
- If calling an external system, verify idempotency on the receiving side.

Intending a tasklet to "run only once" does not automatically guarantee exactly-once when the process crashes and distributed state is inconsistent.

## 19. Decision Template for a New Design

Before creating a step, you can fill out the following table in the design document:

| Question | Example Answer |
| --- | --- |
| What is the business operation? | Import orders from a validated CSV |
| What is the countable unit? | One order record |
| Expected quantity/volume? | 500,000 records nightly |
| How long to rerun from the start? | About 45 minutes |
| Appropriate transaction boundary? | 500 records per commit |
| Need per-item skip/retry? | Yes, for validation and transient errors |
| Need restart/checkpoint? | Yes, resume from last committed chunk |
| Does output have side effects? | JDBC insert with unique key |
| Which metrics are needed? | read, write, skip, duration, new order count |
| Conclusion | **Chunk-oriented step** |

If the answers are "validate one manifest", "no item set", "completes in under a few seconds", "safe to repeat", and "only need pass/fail", the conclusion is usually **Tasklet step**.

Record both **rationale and assumptions** rather than just a label. When data volume, SLAs, or input architecture change, this table helps the team know when to adjust from tasklet to chunk or vice versa.

## 20. Practice Exercises

**Exercise 1 — Choose the model.** Classify these requirements: verify a file's checksum; read 200,000 invoices; create a directory; delete 100,000 accounts from a list; run a SQL aggregate; send 2,000 emails. Explain in terms of transactions, item-level recovery, and restartability.

**Exercise 2 — Create a TaskletStep.** Write `validateInputStep` to verify a file is readable and non-empty. When the file is invalid, assert the step is `FAILED` and the subsequent import step does not run.

**Exercise 3 — Create a ChunkStep.** Write `FlatFileItemReader`, `ItemProcessor`, and `JdbcBatchItemWriter` to load a CSV into a table with a unique key. Run with different chunk sizes and compare throughput/commit counts.

**Exercise 4 — Test restart.** Let the first chunk commit and a subsequent chunk fail. Keep the database metadata and source intact; restart the same instance and verify there are no duplicate records.

**Exercise 5 — Retry and skip.** Add an invalid record and a transient database error. Use specific exceptions to configure skip/retry; check the output, `processSkipCount`, and job status.

**Exercise 6 — Tasklet with side effects.** Create a tasklet that transitions batch state from `VALIDATED` to `READY`. Execute the tasklet again and prove the conditional operation produces no unexpected side effects.

**Exercise 7 — Combined job.** Build the flow `preflightTasklet → importChunk → reconcileTasklet → publishTasklet`. When reconciliation fails, verify data is not yet published downstream even though the import chunk committed to staging.

**Exercise 8 — Data-driven decision.** With 1 million records, measure writer/transaction duration, rollback duration, and memory at chunk sizes 100, 500, and 1,000. Based on resource limits and recovery requirements, choose an appropriate size.

## 21. Conclusion

**Chunk** fits multi-item streams requiring streaming, group commits, skip/retry, metrics, and restart from checkpoints. **Tasklet** fits a well-scoped operation such as preflight checks, manifest validation, state marking, file movement, or executing a controlled SQL statement.

The choice is not between "powerful technology" and "simple technology," but between **two ways of partitioning and managing units of work**. A real-world job often combines both: tasklets for preparation, reconciliation, and publishing, and chunks for processing business records. When transactions, idempotency, restartability, and data state are clearly defined at each step, the design becomes easier to test, operate, and scale.

### References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference — TaskletStep](https://docs.spring.io/spring-batch/reference/step/tasklet.html)
- [Spring Batch Reference — ItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-reader.html)
- [Spring Batch Reference — ItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-writer.html)
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch Reference — ExecutionContext](https://docs.spring.io/spring-batch/reference/common-patterns.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
