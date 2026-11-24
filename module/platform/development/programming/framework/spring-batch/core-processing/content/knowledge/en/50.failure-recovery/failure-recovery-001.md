# Reader Failures in Spring Batch: Detection, Retry, Skip, and Safe Recovery

## 1. When Is an ItemReader Considered to Have Failed?

In Spring Batch, an **ItemReader** is responsible for supplying input items one at a time to a step. In a chunk-oriented step, the framework repeatedly calls `read()` until the reader returns an item, throws an exception, or returns `null` to signal the end of data.

The basic contract:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Three outcomes have distinct meanings:

| `read()` Outcome | How Spring Batch Interprets It | Typical Action |
|---|---|---|
| Returns an item | Read succeeded | Passed to processor (if any), then writer |
| Returns `null` | **End of input** | Ends the read loop once the corresponding chunk is processed |
| Throws an exception | **Read failure** | Applies retry/skip/fail according to the fault-tolerance policy |

**A reader returning `null` is not an error.** A record that does not meet business criteria yet is still read successfully should typically be filtered in `ItemProcessor` by returning `null`; that is a *filter*, not a *read skip*. Conversely, file read errors, line parsing errors, query timeouts, lost database connections, or decoding errors can occur in the reader.

For example, consider a file:

```csv
order_id,amount
A-101,120000
A-102,INVALID_AMOUNT
A-103,50000
```

If the reader uses `FieldSet.readBigDecimal("amount")`, the third line can cause a mapping error. With `FlatFileItemReader`, errors from the line mapper are typically wrapped in `FlatFileParseException` along with the line number and input content. The next decision is whether to **skip the malformed line**, **retry the read**, or **stop the step**.

### What Does a Read Failure Affect?

An unhandled error can transition `StepExecution` to `FAILED`, causing the job to fail along the current flow. With a fault-tolerant configuration, the framework can retry or skip to continue execution. Regardless of the path chosen, recovery also depends on the reader's state, transactions, and checkpoints.

```text
ItemReader.read()
    |
    +--- item ----------------------> process --> write
    |
    +--- null ----------------------> end of input
    |
    +--- exception
            |
            v
      Fault-tolerance policy
            |
            +--- retry --> re-invoke read when appropriate
            +--- skip  --> record read skip, continue
            +--- fail  --> Step FAILED
```

**Version scope:** The main Java snippets use Spring Batch **5.2.x**, Spring Boot **3.x**, Java **17+**, and JUnit Jupiter. Spring Batch 6 changed several packages and step configuration styles; when using 6.x, cross-check the exact API for that version. Retry/skip/checkpoint concepts still must be understood according to the contract of the specific reader.

## 2. Classifying Reader Errors Before Choosing a Handling Strategy

Not every reader exception can be recovered using a single blanket policy.

| Error Category | Practical Example | Typically Appropriate Handling |
|---|---|---|
| **Invalid single record data** | A CSV row with wrong column count, `amount=ABC` | Bounded skip; store the bad row for correction |
| **Missing or misconfigured input source** | File does not exist, wrong bucket/path, permission denied | Fail fast, fix configuration or supply the source |
| **Transient infrastructure error** | Database deadlock, brief connection drop, HTTP 503 | Bounded retry with backoff, if the reader maintains state safely |
| **Widespread source corruption** | Wrong encoding across the whole file, changed CSV schema | Fail or block at validation step; do not mass-skip |
| **Reader cannot determine next position** | Cursor lost state, paging lacks a stable sort key | Stop and restore state; do not blindly retry |
| **Transactional source** | Reading messages from a queue rolled back with the transaction | Configure reader/transaction appropriately, check redelivery |
| **Application logic bug** | `NullPointerException` in a custom mapper | Usually fail to fix the code; do not configure `skip(Exception.class)` by default |

Three questions when designing a policy:

1. **Is the error repeatable?** A string `"ABC"` that cannot parse as a number will not fix itself on retry; a network timeout might clear.
2. **Has the reader advanced past the bad data?** If an exception always happens at the same position without the cursor advancing, skipping may hit the exact same error repeatedly.
3. **Is losing a single record acceptable?** A financial transaction file may require stopping completely, whereas catalog data might tolerate a small percentage of malformed rows.

Rule of thumb: **skip isolated data errors; retry transient recoverable errors; fail when integrity or read progress cannot be guaranteed**.

## 3. Fault Tolerance: Default Behavior and Enabling `faultTolerant()`

A standard chunk-oriented step **does not automatically skip all read exceptions**. If a reader throws an unhandled error, the step can fail.

Example of a step that reads data and writes it:

```java
@Bean
Step importStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("importStep", repository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

If the reader encounters `FlatFileParseException`, there is no policy in the configuration above allowing it to continue. `OrderRow` is simply a business DTO type in this example.

When the requirement allows skipping up to 10 malformed CSV lines, configure it explicitly:

```java
import org.springframework.batch.item.file.FlatFileParseException;

return new StepBuilder("importStep", repository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
```

`skipLimit(10)` is the **total skip limit for the step** across read/process/write phases, not 10 separate skips for the reader alone. For example, if there are already 6 read skips and 4 process skips, one additional skip can cause the step to exceed the limit and fail.

Do not configure a blanket:

```java
.skip(Exception.class)
```

without understanding the consequences: this can mask connection errors, programming bugs, wholesale source corruption, or errors that must never be skipped. Instead, select specific exceptions and use `.noSkip(...)` or a `SkipPolicy` as needed when multiple error types exist.

### 3.1. Differences Between Skip, Filter, and Retry

| Behavior | Triggered By | Related Counter |
|---|---|---|
| **Read skip** | Reader throws a skippable exception | `readSkipCount` |
| **Process skip** | Processor throws a skippable exception | `processSkipCount` |
| **Write skip** | Writer throws a skippable exception | `writeSkipCount` |
| **Filter** | Processor returns `null` for a valid item that was read | `filterCount` |
| **Retry** | Re-attempts an error per policy | May trigger multiple error callbacks; not synonymous with skip |

`StepExecution.getReadCount()` reflects **successfully read items**. A line that throws an error and is skipped typically does **not** increment the read count as a successful item; the skip is reflected in `readSkipCount`. Counters should be read together with actual output data.

## 4. Practical Example: A CSV with a Malformed Line

Let us build a reader for an order file. Valid rows have `order_id` as a string and `amount` as a decimal number. If a row has a malformed `amount`, the step is allowed to skip it in a controlled manner.

### 4.1. Data DTO

```java
import java.math.BigDecimal;

public record OrderRow(
        String orderId,
        BigDecimal amount
) {
}
```

### 4.2. Configuring `FlatFileItemReader` from `JobParameters`

```java
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemReader<OrderRow> ordersCsvReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("ordersCsvReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1) // Skip the CSV header line
            .delimited()
            .delimiter(",")
            .names("order_id", "amount")
            .fieldSetMapper(fieldSet -> new OrderRow(
                    fieldSet.readString("order_id"),
                    fieldSet.readBigDecimal("amount")))
            .build();
}
```

**Why use `@StepScope`?** Each step run needs its own reader and read state, and `inputFile` is resolved from the `JobParameters` of the actual execution. Data rerun with the same parameters can be recovered via checkpoint if the source and configuration remain unchanged.

**Why `strict(true)`?** This is a fail-fast choice if the required resource does not exist. Using `strict(false)` casually can cause a missing file to be treated as empty input and the job to finish "successfully" without reading any data.

If the CSV contains quoted commas, complex escaping, or multiple record types, configure the tokenizer/line mapping accordingly. This example uses a simple format and does not replace a full RFC-compliant CSV parser for all variants.

### 4.3. Configuring the Step to Allow Skipping Parse Errors

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> ordersCsvReader,
        ItemWriter<OrderRow> orderWriter,
        ReadErrorLogger readErrorLogger,
        ReadSkipAudit readSkipAudit) {

    return new StepBuilder("importOrdersStep", repository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(ordersCsvReader)
            .writer(orderWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skipLimit(10)
            .listener(readErrorLogger)
            .listener(readSkipAudit)
            .build();
}
```

`orderWriter` is a business writer declared separately, such as `JdbcBatchItemWriter<OrderRow>`. The two listeners `ReadErrorLogger` and `ReadSkipAudit` are defined right below.

A **skipped** parse error does not mean all prior updates roll back. When a reader exception is configured to be skipped, Spring Batch typically does not roll back the transaction solely for that read error; overall behavior still depends on the data source and other errors in the chunk. The transactional reader section examines an important exception to this.

## 5. Distinguishing `onReadError` from `onSkipInRead`

Two callbacks are very easy to confuse:

- `ItemReadListener.onReadError(Exception)`: called when a read operation encounters an exception. It can be invoked for an error that eventually succeeds on retry or for an error that fails the step.
- `SkipListener.onSkipInRead(Throwable)`: called when a read error is actually **skipped** according to the skip policy.

The same error can trigger a read-error callback **without a skip**, for instance when the reader retries and succeeds. Therefore, use `onReadError` to observe failed read attempts, and use `onSkipInRead` to record records excluded from the processing pipeline.

### 5.1. Logging Read Errors

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ItemReadListener;

public final class ReadErrorLogger
        implements ItemReadListener<OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ReadErrorLogger.class);

    @Override
    public void onReadError(Exception exception) {
        log.warn(
                "Reader failed: type={}, message={}",
                exception.getClass().getSimpleName(),
                exception.getMessage()
        );
    }
}
```

Do not log the entire file or full sensitive data in `onReadError`. With retries, a network incident can emit many log lines; use metric counters, appropriate log levels, and correlation IDs to avoid log spam.

### 5.2. Auditing Skipped Lines

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.item.file.FlatFileParseException;

public final class ReadSkipAudit
        implements SkipListener<OrderRow, OrderRow> {

    private static final Logger log =
            LoggerFactory.getLogger(ReadSkipAudit.class);

    @Override
    public void onSkipInRead(Throwable error) {
        if (error instanceof FlatFileParseException parseError) {
            log.warn(
                    "Skipped CSV line={}, reason={}",
                    parseError.getLineNumber(),
                    parseError.getCause() == null
                            ? parseError.getMessage()
                            : parseError.getCause().getMessage()
            );
            return;
        }

        log.warn(
                "Skipped read failure: type={}",
                error.getClass().getSimpleName()
        );
    }
}
```

`FlatFileParseException` exposes `getLineNumber()` and `getInput()`. `getInput()` contains the raw line and may carry personal, account, or sensitive data: only store it in a controlled quarantine store if genuinely needed, and avoid printing it broadly into logs.

**Important point:** `SkipListener.onSkipInRead` receives a `Throwable`, not the item directly, because reading failed before constructing a valid item. If you want to audit a malformed line, the reader/exception must provide enough identifiers (such as line number and file name). Do not guess business IDs from an exception that does not carry that data.

The listener examples above are registered via `.listener(readErrorLogger)` and `.listener(readSkipAudit)` on `StepBuilder` so Spring Batch actually invokes the callbacks. Calling the two methods directly in a unit test only checks callback logic, not wiring.

### 5.3. Storing Bad Records in Quarantine

For enterprise requirements, a separate storage location is advisable:

```text
source_file     = orders-20250512.csv
source_line     = 3
error_category  = PARSE_ERROR
error_message   = Invalid amount
job_execution   = 501
record_checksum = SHA-256 of the relevant content
```

Transaction note: skip callbacks can occur near the chunk commit boundary. If the audit record is written in the same transaction, a rollback can lose the audit; if written to an independent store, retries can create duplicates. Choose the transaction boundary and a business idempotency key, such as `sourceFileChecksum + lineNumber + errorCategory`.

## 6. Retrying Reader Errors: When Is It Actually Useful?

Retry is appropriate for errors **likely to resolve on their own**, such as an external service returning 503 or a transient database connection failure. For a CSV parse error that deterministically fails on the same string, retrying only wastes time.

Example of selective retry configuration:

```java
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("readFromDatabaseStep", repository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(databaseReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

This is an example of a **retry policy**, not a guarantee that every JDBC reader can recover after losing a connection. If the read cursor is lost, retrying may repeat the exact same exception or skew the read position; verify `databaseReader`'s contract before enabling retry.

### 6.1. Retry Limit and Skip Limit Are Two Different Thresholds

| Setting | Purpose |
|---|---|
| `retry(SomeException.class)` | Selects exceptions eligible for retry |
| `retryLimit(3)` | Caps attempts under the retry policy |
| `skip(OtherException.class)` | Selects exceptions eligible to be skipped |
| `skipLimit(10)` | Caps total skips across the step |
| `noRetry(...)` / `noSkip(...)` | Excludes ineligible exceptions |

In a configuration with both retry and skip, execution order, callback invocation counts, and counters depend on error type, phase, and transaction state. Do not write tests assuming **one callback invocation per exception** when fault tolerance allows multiple attempts.

### 6.2. Backoff to Avoid Tight Retry Loops

Retries should not hammer an API or DB in a tight loop. When using Spring Retry and an appropriate policy in the step configuration, you can add backoff:

```java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backoff = new FixedBackOffPolicy();
backoff.setBackOffPeriod(200L); // example: 200 ms

return new StepBuilder("remoteReaderStep", repository)
        .<OrderRow, OrderRow>chunk(50, transactionManager)
        .reader(remoteReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientReadException.class)
        .retryLimit(3)
        .backOffPolicy(backoff)
        .build();
```

`TransientReadException` is a hypothetical application exception; declare the class and map network/HTTP failures to that exception. The backoff value must reflect service characteristics, timeout budgets, and retry limits; **200 ms is only an example**.

Be careful with reader retries: `read()` must have clear semantics around data position. If it increments an offset before throwing an exception, the next retry attempt may **no longer read the same item**. If it does not advance the offset and the exception is deterministic, it may keep failing on the same record.

### 6.3. Designing a Retryable Reader

For a custom reader calling a paginated API, verify:

- Is the pagination cursor saved only after the page has been safely processed?
- Does a request failing before returning data leave the cursor unchanged?
- Does the server guarantee the same cursor returns the same page during retry?
- Can retries introduce duplicates when the API is unstable?
- When receiving multiple items in one page, how does the checkpoint describe each item's position?

If the API cannot guarantee consistent re-reads, stage the data into an immutable staging area first and have Spring Batch process that staging source. This can be far more reliable than retrying over a continuously mutating stream.

## 7. Why Not Every Read Exception Can Be Safely Skipped

Skippability depends on how the reader advances through the source.

### 7.1. Reader Already Advanced to the Next Line

`FlatFileItemReader` can fetch a raw line, and then the line mapper throws `FlatFileParseException`. The reader has identified the bad line, and on the next read it can move to the following line. When policy permits, skipping a malformed line is well-defined.

```text
Line 1: header           -> skipped
Line 2: A-101,120000     -> valid item
Line 3: A-102,INVALID    -> FlatFileParseException -> skip
Line 4: A-103,50000      -> valid item
```

### 7.2. Reader Repeatedly Fails at the Same Position

A poorly written custom reader:

```java
public OrderRow read() {
    String raw = lines.get(index);    // index not yet incremented
    return parse(raw);                 // fails on this raw line
}
```

If `parse(raw)` throws an exception before `index` is updated, the next call hits the same line again. Configuring skip does not automatically fix a reader's progress contract; it can exhaust the entire skip limit without advancing a single record.

A simpler version with clearer operation ordering:

```java
public OrderRow read() {
    if (index >= lines.size()) {
        return null;
    }

    String raw = lines.get(index++);
    return parse(raw);
}
```

However, **incrementing the index before parsing** only solves a simple in-memory reader case. For restartable readers, the offset must be checkpointed and restored properly. For transactional queues, the cursor must obey transaction semantics. Do not apply a naive index-increment trick across all sources.

### 7.3. Reader Fetches Data Then Loses Connection

Suppose a JDBC cursor fetches several rows and then loses its connection. Enabling `skip(SQLException.class)` may cause the step to swallow an infrastructure failure without knowing which records were or were not read. In that case, **failing and restarting from a reliable checkpoint** is usually safer than skipping.

## 8. Transactions and Rollback When an Error Occurs in the Reader

Spring Batch chunk processing typically wraps read–process–write inside a transaction, but **the transaction contract of the read source** can differ.

According to Spring Batch 5.2 documentation, when skip is configured, an exception from `ItemReader` generally **does not roll back** the step's transaction solely for that read error. In contrast, an exception in `ItemWriter` normally triggers a rollback by default. This significantly impacts counters and audit writes.

### 8.1. Non-Transactional Reader

For example, reading a CSV file:

- Reading a line cannot "roll back a file pointer" the way database rows roll back.
- Spring Batch can buffer already-read items for reprocessing when a chunk rolls back.
- `FlatFileItemReader` implements `ItemStream`, allowing state to be persisted for restart via `ExecutionContext`.

If a chunk has 99 valid items and one malformed line is skipped, the step can continue building the chunk and commit the valid data. Results should be verified via counters and actual output tables.

### 8.2. Reader Pulling Items from a Transactional Queue

With JMS or a truly transactional source, rollback can return the message to the queue. Spring Batch provides an option:

```java
return new StepBuilder("transactionalQueueStep", repository)
        .<OrderMessage, OrderMessage>chunk(20, transactionManager)
        .reader(transactionalQueueReader)
        .writer(orderWriter)
        .readerIsTransactionalQueue()
        .build();
```

`readerIsTransactionalQueue()` tells the step that the reader is backed by a transactional source; the step does not buffer items the way it does for a standard forward-only reader, because on rollback the source can redeliver the message.

**Use this only when the source and transaction genuinely have those semantics.** Enabling it casually for file or API readers can alter retry/rollback behavior unexpectedly. With queues, you must also design redelivery counts, dead-letter queues, and idempotency so poisoned messages do not loop forever.

### 8.3. Readers with Side Effects

An ideal `ItemReader` primarily reads data. If a custom reader both fetches an item and deletes a record from a queue, acknowledges via HTTP, or updates a status table, an error anywhere can cause **data loss** or **duplicate reads**.

Example:

```text
1. Reader receives order-101
2. Reader calls API to mark order-101 as processed
3. Processor/Writer fails, DB transaction rolls back
4. Restart: API no longer returns order-101
```

For safe recovery, avoid non-rollbackable side effects in the reader or move them to a write/ack step with clear semantics. If unavoidable, use transactional inbox/outbox or idempotency and reconciliation mechanisms.

## 9. ItemStream and Checkpoints: The Foundation for Restart After Read Failure

Spring Batch persists batch progress via `ExecutionContext`. Many readers support `ItemStream` with three methods:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Roles:

- `open(...)`: initializes the reader, restoring its position if a suitable checkpoint exists.
- `update(...)`: writes the reader's state into `ExecutionContext` when the framework updates checkpoints.
- `close()`: closes resources.

`FlatFileItemReader` implements state persistence and uses `name` to key entries in the execution context. If a reader fails to save its position or the source changes between executions, restarting can read duplicates or miss records.

### 9.1. Saving State with FlatFileItemReader

```java
return new FlatFileItemReaderBuilder<OrderRow>()
        .name("ordersCsvReader")
        .resource(new FileSystemResource(inputFile))
        .saveState(true)
        .strict(true)
        .linesToSkip(1)
        .delimited()
        .names("order_id", "amount")
        .fieldSetMapper(fieldSet -> new OrderRow(
                fieldSet.readString("order_id"),
                fieldSet.readBigDecimal("amount")))
        .build();
```

`saveState(true)` explicitly expresses the intent to support restarts. A stable, distinct reader name prevents state-key collisions when multiple readers operate in the same execution context.

**Key point:** A checkpoint is not a snapshot of the entire file. If an operator replaces the source file after a step fails, the same line number can point to a completely different record upon restart.

To prevent drift:

1. Lock down `inputFile` and identifying parameters at launch.
2. Keep input data immutable or versioned (object storage versions, file checksums).
3. If the file changes, consider creating a new `JobInstance` with a clear reprocessing procedure rather than blindly restarting.
4. Ensure the writer is idempotent; data committed before the failure must not be written twice.
5. Verify that the reader is always reopened via `ItemStream.open(...)` and properly managed by the framework.

### 9.2. Saving State in a Custom Reader

If a custom reader is required, build it with explicit state management rather than storing offsets only in an in-memory field.

Compact example of a reader over a fixed list supporting restart via an index:

```java
import java.util.List;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class IndexedReader<T> implements ItemStreamReader<T> {

    private final List<T> items;
    private final String stateKey;
    private int index;

    public IndexedReader(List<T> items, String stateKey) {
        this.items = List.copyOf(items);
        this.stateKey = stateKey;
    }

    @Override
    public void open(ExecutionContext context) {
        index = context.containsKey(stateKey)
                ? context.getInt(stateKey)
                : 0;
    }

    @Override
    public T read() {
        return index < items.size() ? items.get(index++) : null;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(stateKey, index);
    }

    @Override
    public void close() {
        // No resources to close in this example.
    }
}
```

This is a basic example illustrating `open/update/close`, **not a reader meant for concurrent/multi-threaded sharing**. The input list must keep the same ordering across restarts; do not use this pattern on continuously mutating data and expect checkpoint offsets to remain valid.

### 9.3. JDBC Readers Need Stable Ordering

With `JdbcPagingItemReader`, configure a stable sort key—ideally unique—so paging and restarts do not drop records when query ordering shifts. With `JdbcCursorItemReader`, evaluate how the driver/cursor recovers after connection failures and the cost of re-reading up to the checkpoint.

Even with a checkpointed reader, database mutations while the job runs can shift offsets/pages away from the original record set. Mitigations include snapshots, a fixed business cutoff, monotonically increasing ID queries, or an immutable staging table.

## 10. Reader Failures Across Different Lifecycle Phases

Read failures do not happen only inside `read()`. Errors can also occur when opening or closing the reader.

| Phase | Callback / Method | Example Errors | Strategy |
|---|---|---|---|
| Initialization | `ItemStream.open(...)` | Missing file, bad credentials, cannot open cursor | Fail fast; fix resource/credentials |
| Reading | `ItemReader.read()` | Parse error, timeout, lost connection | Skip/retry/fail based on root cause |
| Checkpoint update | `ItemStream.update(...)` | Cannot persist state, internal exception | Fail; protect metadata and consistency |
| Closing | `ItemStream.close()` | Failed to close resource | Log, release resources, inspect final status |

An exception in `open()` **does not necessarily** pass through `skip(FlatFileParseException.class)` intended for item-read errors, nor can `onSkipInRead` be used to assume a missing file was safely skipped. For example, `strict(true)` makes a missing file fail immediately on open; that is the desired behavior when the input source is mandatory.

### 10.1. "Nothing Was Read" Errors vs. an Empty File

Two scenarios can both produce `writeCount=0` yet carry completely different meanings:

```text
Case A: reader opens the file successfully, file only contains a header
       -> read() returns null, step may be COMPLETED, 0 items

Case B: reader fails to open the file
       -> open() throws an error, step FAILED
```

If business rules prohibit a day with zero orders, add a validation step to distinguish "no data today" from "empty file caused by a broken upstream pipeline." Setting `strict` only verifies that the resource exists, not that its content has records.

## 11. Tracking Reader Failures via StepExecution and Listeners

When investigating, inspect at least the following counters:

```java
StepExecution step = ...;

System.out.println("status=" + step.getStatus());
System.out.println("readCount=" + step.getReadCount());
System.out.println("readSkipCount=" + step.getReadSkipCount());
System.out.println("processSkipCount=" + step.getProcessSkipCount());
System.out.println("writeSkipCount=" + step.getWriteSkipCount());
System.out.println("rollbackCount=" + step.getRollbackCount());
System.out.println("failureExceptions=" + step.getFailureExceptions());
```

A hypothetical example:

```text
Input lines      = 1001 (including 1 header)
Valid records    = 997
Malformed records= 3

readCount        = 997
readSkipCount    = 3
writeCount       = 997
status           = COMPLETED
```

The numbers above only make sense when the reader processed 1,000 data lines, the writer had no other errors or filters, and the skip limit allowed 3 malformed lines. If the data is critical enough that losing 3 orders is unacceptable, `COMPLETED` with skips still fails business requirements; enforce a quality threshold or fail the job via a custom rule.

### 11.1. Reading from JobRepository

`JobExplorer` lets you query `JobExecution` and `StepExecution` by ID to review statuses and counters after a job finishes:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public void printReaderFailureStats(
        JobExplorer explorer, long jobExecutionId) {

    JobExecution execution =
            explorer.getJobExecution(jobExecutionId);

    if (execution == null) {
        throw new IllegalArgumentException(
                "Unknown jobExecutionId " + jobExecutionId);
    }

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "step=%s status=%s read=%d readSkips=%d%n",
                step.getStepName(),
                step.getStatus(),
                step.getReadCount(),
                step.getReadSkipCount()
        );
    }
}
```

Metadata supports reconciliation after processing finishes. For a running step, counters may only be persisted at checkpoint boundaries and might not immediately reflect the latest item.

### 11.2. Metrics and Alerts

A reader-monitoring dashboard might include:

- `readSkipCount` per step execution, and the ratio `readSkipCount/(readCount + readSkipCount)` when the numbers are meaningful to compare.
- `rollbackCount` to detect transactions reprocessing repeatedly.
- Read-step duration or an item-read Timer if Micrometer instrumentation is enabled for the version.
- Parse error counts by type, source file, and schema version.
- Number of `FAILED` jobs/steps and restart counts.
- Number of records sent to quarantine and number fixed/reprocessed.

Do not place `lineNumber`, `jobExecutionId`, customer names, or raw exception messages into Prometheus labels: cardinality can explode and leak sensitive data. Those values belong in access-controlled logs and audit stores.

## 12. Unit Testing Readers and Deterministic Errors

A unit test should show clear reader behavior without needing a datasource or job context.

### 12.1. Testing Parse Failures with a Fixed Input Source

For example, build a `FlatFileItemReader` from in-memory data and call `open` and `read` directly.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.ByteArrayResource;

class FlatFileReaderFailureTest {

    @Test
    void malformedAmountShouldRaiseParseException() throws Exception {
        String csv = """
                order_id,amount
                A-101,120000
                A-102,INVALID_AMOUNT
                """;

        FlatFileItemReader<OrderRow> reader =
                new FlatFileItemReaderBuilder<OrderRow>()
                        .name("ordersTestReader")
                        .resource(new ByteArrayResource(
                                csv.getBytes(StandardCharsets.UTF_8)))
                        .linesToSkip(1)
                        .delimited()
                        .names("order_id", "amount")
                        .fieldSetMapper(fields -> new OrderRow(
                                fields.readString("order_id"),
                                fields.readBigDecimal("amount")))
                        .build();

        reader.open(new ExecutionContext());
        try {
            OrderRow first = reader.read();

            assertEquals("A-101", first.orderId());
            assertEquals(new BigDecimal("120000"), first.amount());

            FlatFileParseException exception = assertThrows(
                    FlatFileParseException.class,
                    reader::read
            );

            assertEquals(3, exception.getLineNumber());
        } finally {
            reader.close();
        }
    }
}
```

This unit test confirms that the reader maps data and throws an exception containing line details. It does **not yet prove Spring Batch will skip it**: skip/retry belong to a fault-tolerant step, so an integration test running the actual step is required.

### 12.2. Why Not Just Mock ItemReader?

If you only mock:

```java
when(reader.read()).thenThrow(new IllegalArgumentException("bad"));
```

you do not know whether the real reader advances its cursor, closes files, persists checkpoints, or throws the right exception type on malformed data. Mocks are useful when testing step orchestration in isolation, but real reading and parsing must be verified using the production reader against meaningful fixtures.

## 13. Integration Test: Verifying Reader Error Skips in Spring Batch

The example below creates a standalone job with data `"ok"`, `"BAD"`, and `"end"`. The illustrative reader reads three lines from a `ByteArrayResource`; the mapper intentionally throws on `"BAD"`. We simultaneously verify:

- The step ends as `COMPLETED`.
- Two valid items are read and written.
- One error is counted in `readSkipCount`.
- `ItemReadListener.onReadError` and `SkipListener.onSkipInRead` are invoked by the framework.
- The writer receives only valid items.

Test dependencies require `spring-boot-starter-batch`, `spring-batch-test`, `spring-boot-starter-test`, and H2 on the test classpath.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ItemReadListener;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = ReaderFailureIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class ReaderFailureIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    RecordedOutput output;

    @Autowired
    ReadErrorCounter readErrors;

    @Autowired
    ReadSkipCounter readSkips;

    @Test
    void malformedLineShouldBeSkippedAndValidRowsWritten()
            throws Exception {

        JobExecution execution = launcher.launchStep("readFailureStep");

        StepExecution step = execution.getStepExecutions()
                .iterator().next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(2L, step.getReadCount());
        assertEquals(1L, step.getReadSkipCount());
        assertEquals(2L, step.getWriteCount());

        assertEquals(List.of("ok", "end"), output.values);
        assertEquals(1, readSkips.count.get());
        assertEquals("BAD", readSkips.badInput);
        assertTrue(readErrors.count.get() >= 1);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        @StepScope
        FlatFileItemReader<String> inputReader() {
            String input = "ok\nBAD\nend\n";

            return new FlatFileItemReaderBuilder<String>()
                    .name("readFailureTestReader")
                    .resource(new ByteArrayResource(
                            input.getBytes(StandardCharsets.UTF_8)))
                    .lineMapper((line, number) -> {
                        if ("BAD".equals(line)) {
                            throw new IllegalArgumentException(
                                    "Malformed record");
                        }
                        return line;
                    })
                    .build();
        }

        @Bean
        RecordedOutput recordedOutput() {
            return new RecordedOutput();
        }

        @Bean
        ReadErrorCounter readErrorCounter() {
            return new ReadErrorCounter();
        }

        @Bean
        ReadSkipCounter readSkipCounter() {
            return new ReadSkipCounter();
        }

        @Bean
        Step readFailureStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                FlatFileItemReader<String> inputReader,
                RecordedOutput output,
                ReadErrorCounter readErrors,
                ReadSkipCounter readSkips) {

            return new StepBuilder("readFailureStep", repository)
                    .<String, String>chunk(2, transactionManager)
                    .reader(inputReader)
                    .writer(chunk -> chunk.forEach(output.values::add))
                    .faultTolerant()
                    .skip(FlatFileParseException.class)
                    .skipLimit(1)
                    .listener(readErrors)
                    .listener(readSkips)
                    .build();
        }

        @Bean
        Job readerFailureJob(
                JobRepository repository,
                Step readFailureStep) {

            return new JobBuilder("readerFailureJob", repository)
                    .start(readFailureStep)
                    .build();
        }
    }

    static class RecordedOutput {
        final List<String> values = new CopyOnWriteArrayList<>();
    }

    static class ReadErrorCounter implements ItemReadListener<String> {
        final AtomicInteger count = new AtomicInteger();

        @Override
        public void onReadError(Exception error) {
            count.incrementAndGet();
        }
    }

    static class ReadSkipCounter
            implements SkipListener<String, String> {

        final AtomicInteger count = new AtomicInteger();
        volatile String badInput;

        @Override
        public void onSkipInRead(Throwable error) {
            count.incrementAndGet();

            if (error instanceof FlatFileParseException parseError) {
                badInput = parseError.getInput();
            }
        }
    }
}
```

In this example, one parse error can be skipped by the framework because `skipLimit(1)` and `FlatFileParseException` are permitted. The test runs once on the created context and does not require parallel execution. If expanding to multiple tests on the same context, reset sinks/counters per run and use distinct job parameters or clean metadata to avoid collisions.

`@StepScope` gives each step execution its own reader and cursor. The `RecordedOutput` writer here is only an in-memory sink to show which items reached the writer; it **does not prove database transactions**. To assert commits/rollbacks, swap in a JDBC writer and query the result table in a test database.

### 13.1. Without Skip Configured

Omitting `.faultTolerant().skip(...).skipLimit(...)` or configuring `skipLimit(0)`:

```text
Data: "ok", "BAD", "end"
Read failure: FlatFileParseException at "BAD"

Expected:
  BatchStatus       = FAILED
  readSkipCount     = 0
  failureExceptions = contains parse error cause
  "end"             = not processed in that failed execution
```

Do not assert rigidly whether the in-memory writer output still contains `"ok"` if chunk size or transaction boundaries change, because an in-memory sink does not roll back. With a transactional database, inspect data committed **before** the failing chunk and verify the exact rollback boundary.

### 13.2. Exceeding the Skip Limit

If the input has two `BAD` lines and `skipLimit(1)`, the step can skip the first error but fails when the allowed threshold is exceeded. This is an important test to prevent the system from silently treating an almost completely corrupted file as a success.

## 14. Testing a Stateful Retryable Reader

A different requirement from parse skips: the reader calls an external service, hits a transient failure on the first attempt, and returns the item on the next attempt.

A fake reader pattern usable in unit tests:

```java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.ItemReader;

public final class FlakyReader implements ItemReader<String> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public String read() throws IOException {
        if (attempts.incrementAndGet() == 1) {
            throw new IOException("Temporary network failure");
        }
        return "ORDER-101";
    }

    public int attempts() {
        return attempts.get();
    }
}
```

**The pattern above only illustrates a single transient failure**; it cannot be used for a full step because after succeeding it keeps returning `"ORDER-101"` instead of `null`, causing infinite duplicate reads. In an integration test, use a finite reader with states `notStarted → failedOnce → delivered → EOF`, and persist checkpoints properly.

Test cases should prove:

- The first read throws a retryable error.
- The retry read returns the item with **the same business meaning**.
- `readSkipCount=0` if the item is eventually read.
- `onReadError` may fire, but **no `onSkipInRead`**.
- Output is not written twice upon retry.

For real HTTP clients or databases, use a fake server/driver or mock the external source to inject controlled faults. Do not rely on random network errors or `Thread.sleep(...)` timeouts in tests.

## 15. Recovery Scenario When a Step Has FAILED

Suppose a job reads a 1-million-line file, commits 500,000 lines, and then loses file access permissions.

A recovery procedure can be:

1. **Identify the actual error.** Check `StepExecution.failureExceptions`, reader logs, and status in `JobRepository`. Distinguish data parse errors, deleted file errors, and network errors.
2. **Verify committed data.** Check counters and target tables. `readCount` is the number of items read, not proof that every one of those items committed to the business database.
3. **Keep the input unchanged on restart.** Restore the exact file/version, checksum, and identifying `JobParameters`.
4. **Fix the root cause.** Restore permissions, database connectivity, path, or resource; do not bump the skip limit to mask the root cause.
5. **Assess checkpoints.** Does the reader implement `ItemStream` with valid state? Is the writer idempotent/transactional?
6. **Restart the same `JobInstance`** when appropriate. Spring Batch creates a new `JobExecution` and uses the step's checkpoint to resume the unprocessed portion.
7. **Reconcile results.** Compare source line counts, output row counts, skipped lines, and duplicate items; do not rely solely on `BatchStatus.COMPLETED`.

### 15.1. Restart vs. Launching a New Job

```text
JobInstance: importOrders + businessDate=2025-05-12
    |
    +-- JobExecution 501: FAILED
    |       StepExecution 1001: FAILED
    |       checkpoint: written up to the appropriate position
    |
    +-- JobExecution 509: COMPLETED (restart)
            StepExecution 1020: COMPLETED
            restored from the previous checkpoint
```

If you change the identifying parameter `businessDate` or add a new identifying `run.id`, you can create **a different JobInstance**. In that case the reader may start over from the beginning, causing duplicate data if the writer is not built for deduplication.

Do not directly edit `BATCH_STEP_EXECUTION` or execution context rows to "nudge the read position past a bad line" without a controlled recovery procedure; doing so can lose data or break restart consistency.

## 16. Design Mistakes That Make Reader Failures Dangerous

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Using `skip(Exception.class)` for all errors | Masks system errors and corrupted data | Choose skippable exceptions by contract |
| Configuring skip for a missing file | Job may misinterpret missing input as no data | `strict(true)` and fail fast |
| Retrying parse errors endlessly | Wastes time, step makes no progress | Bounded skip or fail |
| Retrying a reader that advanced cursor without retaining the item | Drops data | Design read progress and retry state clearly |
| Reader does not implement `ItemStream` yet requires restart | Restart reads at wrong position or from start | Save checkpoints via `ExecutionContext` |
| Swapping source file between fail and restart | Old offset is no longer valid | Source immutability/versioning/checksum |
| Reader has out-of-transaction side effects | Rollback still loses data | Separate side effects, use inbox/outbox/idempotency |
| Using `readerIsTransactionalQueue()` for every reader | Changes buffering/retry semantics | Enable only for suitable transactional sources |
| Looking only at `readCount` and ignoring `readSkipCount` | Unaware that input records were skipped | Monitor counters and audits |
| Logging raw malformed lines with sensitive data | Data leak | Redact, controlled quarantine |
| Treating `onReadError` as "record was skipped" | Overcounts when retry succeeds | Use `onSkipInRead` and skip counters |
| Testing solely with a mocked reader | Misses parser/offset/checkpoint bugs | Test real reader with fixtures |
| Writing items to an in-memory list and assuming rollback is verified | List does not roll back with DB transaction | Integration test with real transaction/database |
| Using `Thread.sleep` to wait for network errors | Slow, flaky tests | Fake server/clock/latch or simulated faults |
| Not checking skipped item counts before releasing output | Downstream may assume incomplete data is complete | Set quality gates per business rules |

## 17. Practice Exercises

Build a job `importCustomerCsv` accepting `inputFile` and `businessDate` from `JobParameters`. The file has a header and 1,000 rows, including rows missing email, rows with malformed birth dates, one row with bad encoding, and valid rows.

Requirements:

1. Write `FlatFileItemReader<CustomerRow>` with a stable reader name, `@StepScope`, `strict(true)`, and `saveState(true)`.
2. Design the `FieldSetMapper`/validator to distinguish parse errors (reader) from business validation errors on successfully read items (processor).
3. Allow skipping at most 5 malformed parse lines; do not skip missing-file or database-access errors.
4. Create `ItemReadListener` and `SkipListener`; audit line number, file version, and error category with a deduplication key.
5. Write a unit test with a fixed fixture: one valid line, one malformed line, and one subsequent valid line.
6. Write an integration test verifying `readCount`, `readSkipCount`, `writeCount`, and target table contents.
7. Add a test with 6 malformed lines to prove the step fails when exceeding `skipLimit(5)`.
8. Simulate an I/O error in the reader at a checkpoint. Keep the file unchanged and restart; verify no duplicate reads or missed committed records.
9. Replace the source file with a different version before restarting and explain why the checkpoint is no longer reliable.
10. Add a reader calling an HTTP service with transient errors; configure bounded retry with backoff and ensure the cursor is not modified unless a response is successfully received.
11. Test the header-only file and missing-file cases. Determine the expected status for each case.
12. Distinguish skipping a malformed CSV line from filtering a valid underage customer: which counter should increment in each case?

**Review question:** A reader throws `FlatFileParseException` on line 25. After configuring `skip(FlatFileParseException.class)` and `skipLimit(10)`, can you immediately conclude the job will continue safely?

**Answer:** Not yet. You must ensure the reader actually advances past the bad line, skipping is permitted by business rules, error counts stay within limits, checkpoints and the writer preserve consistency, and remaining lines are still processed correctly. Skip configuration is only **one part** of a recovery strategy.

## 18. References

- [Spring Batch 5.2 — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html): skip policy, skip limit, and `FlatFileParseException` example.
- [Spring Batch 5.2 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html): retry exceptions and retry limit.
- [Spring Batch 5.2 — Controlling Rollback](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/controlling-rollback.html): rollback on skip and transactional readers.
- [Spring Batch 5.2 — Item Stream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): `open`, `update`, `close`, and `ExecutionContext`.
- [Spring Batch 5.2 — Flat Files](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/flat-files/file-item-reader.html): `FlatFileItemReader`, line mapper, and `FlatFileParseException`.
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): `ItemReadListener` and `SkipListener`.
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, and testing steps/jobs.
- [Spring Batch 5.2 API — StepExecution](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): read/skip counters and failure exceptions.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, and restart semantics.
