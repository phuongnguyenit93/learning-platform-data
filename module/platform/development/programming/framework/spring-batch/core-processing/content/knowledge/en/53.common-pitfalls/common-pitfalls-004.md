# Non-Restartable Reader When the Job Requires Restart in Spring Batch

A Spring Batch job reads millions of records, writes several chunks, and then fails because the database or target service is unavailable. An operator re-launches **the same job**, yet the reader goes back to the first record, re-reads already written data, or cannot find where it stopped. Sometimes the job does not report a clear reader error; it just hits duplicate keys, produces duplicate results, or takes forever reprocessing. The root cause may be that **`ItemReader` does not save state for restart**, even though the job itself is designed to allow restart.

This is a common pitfall in **Spring Batch Core Processing → Common Pitfalls**. Handling it properly requires understanding the difference between *a job's restartability* and *a reader's ability to restore its read position*. This document explains the `ItemStream`/`ExecutionContext` mechanism, how to spot misconfigurations, how to write a checkpointed reader, how to recover sources that do not support replay, and testing strategies to prevent duplicate reads or skipped items.

Java examples focus on **Spring Batch 5.2.x and Java 17**. Some packages/APIs are reorganized in Spring Batch 6.x; the checkpoint and consistency principles still apply.

## 1. A Restartable Job Does Not Automatically Mean a Restartable Reader

Spring Batch distinguishes the following components:

| Component | Responsibility | Question on restart |
| --- | --- | --- |
| `JobInstance` | Logical unit of work identified by job name and identifying `JobParameters` | Is this the same work that needs to finish? |
| `JobExecution` | One attempt to execute a `JobInstance` | Was the previous attempt `FAILED`, `STOPPED`, or `COMPLETED`? |
| `StepExecution` | State and outcome of executing a step | Which step needs to run again, and which already finished? |
| `JobRepository` | Stores metadata, status, counters, and execution context | Which recovery point actually committed? |
| `ItemReader` | Supplies the next item via `read()` | After re-creation, where does the reader start? |
| `ItemStream` | Opens, updates, and closes resources; saves/restores state | Can the reader restore its position after the latest commit? |
| `ItemWriter` | Writes results | If an item is re-delivered, will it duplicate business effects? |

A job may allow restart by configuration and metadata, yet Spring Batch **cannot guess the offset** of a reader that only implements `ItemReader<T>`. That interface only has `read()`; it defines no way to save position across executions.

For example:

```text
Job: importOrders
  |
  +-- JobInstance A (businessDate=2026-11-15)
        |
        +-- JobExecution 101: FAILED
        |     +-- StepExecution 201: FAILED
        |           +-- reader checkpoint: committed up to item 200
        |
        +-- JobExecution 102: restart
              +-- StepExecution 202: must resume from item 201
```

If the reader on the second run initializes a fresh `Iterator` and reads from the beginning, it will encounter item 1 instead of item 201. Two failure modes can follow: **duplicates** because items 1–200 were already written, or **improper overwrites** if the writer lacks appropriate keys/idempotency.

Additionally, when a step already `COMPLETED` in the previous run, Spring Batch normally **does not re-run that step** when restarting the same `JobInstance`, unless configured to allow re-running. The non-restartable reader bug primarily surfaces on an incomplete step that must resume.

## 2. How Is a Reader's Checkpoint Saved?

The `ItemStream` interface defines three lifecycle methods:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

In Spring Batch 5.2, the combined interface is `org.springframework.batch.item.ItemStreamReader<T>`, meaning a reader that both provides `read()` and supports `open`, `update`, and `close`.

| Method | Role | When |
| --- | --- | --- |
| `open(context)` | Opens resources and restores from the passed checkpoint | Before reading items |
| `read()` | Returns the next item or `null` at end of source | Each time the framework requests an item |
| `update(context)` | Places position/state to checkpoint into `ExecutionContext` | Before context is persisted at a commit boundary |
| `close()` | Releases file handles, cursors, connections, or other resources | When the step ends/closes the stream |

`ExecutionContext` is a key-value structure that Spring Batch can persist in `JobRepository`. Normally, state for recovering **reader position** belongs to `StepExecutionContext`, not `JobExecutionContext`; readers within the same step need **distinct keys** to avoid overwriting one another.

Simplified cycle:

```text
        Step starts / restarts
                |
                v
      ItemStream.open(stepContext)
                |
         read and process chunk
                |
                v
      ItemStream.update(stepContext)
                |
                v
     JobRepository saves checkpoint
                |
          COMMIT transaction
                |
        +-------+---------+
        |                 |
     Continue          Later FAILED
        |                 |
        v                 v
    new chunk      Create new JobExecution
                              |
                              v
                    open(committed context)
                              |
                              v
                    Read from recovery point
```

**Reading an item with `read()` does not immediately persist a checkpoint to the database.** With chunk size 100, a reader may advance through 85 items of a new chunk before the process dies prior to commit; restart will typically return to the previous committed chunk's checkpoint and reprocess those 85 items. That is the expected behavior when business data also rolls back with the transaction, or when the writer handles replay safely.

Calling `update(context)` in a pure Java test only mutates an in-memory object. In a real job, **the framework and `JobRepository`** are responsible for durably persisting context at transaction boundaries. Do not manually call a repository update on every `read()` "just to be sure"; doing so can advance the checkpoint ahead of committed data.

## 3. Identifying a Reader Without Restart Capability

Common causes:

1. The reader only implements `ItemReader<T>`, keeping an `Iterator`, page number, or index in a field without `ItemStream` to persist state.
2. The reader supports `ItemStream` but is configured with `saveState(false)`, intentionally disabling position persistence.
3. The reader has an `ItemStream` inside a wrapper/composite, but **the step does not register the delegate stream**, so the delegate's lifecycle is never invoked.
4. The reader has `@StepScope` and receives `JobParameters` but saves no checkpoint; restart creates a fresh bean and reads from the beginning.
5. The reader saves an offset, yet the data source is **unstable**: the file was replaced, SQL lacks deterministic ordering, rows were inserted/deleted, or an API stream does not allow replay.
6. The reader is shared across multiple executions or threads, causing index/checkpoint overwrites and race conditions.
7. Context keys collide, the reader's `name` was changed after deployment, or the serializer/context became incompatible.
8. `JobRepository` metadata was not committed or was lost due to a database failure, cleanup, or restore from an old backup.

Some symptoms appear only indirectly:

| Symptom | Possibility to investigate |
| --- | --- |
| Restart re-reads from the first record | No checkpoint, `saveState(false)`, or context not restored |
| Restart reports duplicate key | Reader replayed already written data or writer is not idempotent |
| Restart skips many records | Checkpoint shifted vs. new file/query; checkpoint advanced past committed data |
| Has `@StepScope` yet still re-reads | Scope creates a new bean; it **does not automatically save read position** |
| Has `ItemStreamReader` yet `update` never runs | Delegate hidden by wrapper; step did not register stream |
| Context saved, yet reader opens at index 0 | Key/name differs from prior run; `open` logic ignores context |
| Same input gives different results on restart | Source or query ordering changed |
| Multi-threaded step duplicates/misses items | Reader state is not thread-safe or checkpoint cannot express parallel progress |

Do not fix this by setting `allowStartIfComplete(true)` or adding `run.id=timestamp` without understanding the consequences. Neither option **makes a reader automatically recover its checkpoint**.

## 4. Faulty Example: Reader Keeping an `Iterator` in RAM

Here is a minimal reader that appears to work fine when a job runs once:

```java
import java.util.Iterator;
import java.util.List;
import org.springframework.batch.item.ItemReader;

public class NonRestartableOrdersReader implements ItemReader<String> {

    private final Iterator<String> iterator;

    public NonRestartableOrdersReader(List<String> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public String read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

If you create this reader with `["A", "B", "C", "D"]`, calling `read()` twice returns `A` then `B`. But if the process dies and Spring creates a new reader object, the iterator is new too and position resets to 0.

```text
JobExecution run 1:
  read A -> write A -> commit
  read B -> write B -> commit
  read C -> writer fails, step FAILED

JobExecution run 2:
  new NonRestartableOrdersReader(...)
  read A  <-- already processed earlier
  read B  <-- already processed earlier
```

The problem is not that `Iterator` is broken; the problem is that **position exists only in the memory of a single reader instance**. There is no mechanism for `JobRepository` to retrieve that position on a new run.

Some list/cursor readers used only for testing or full-rerun tasks may fit this design. However, if the requirement is to **restart accurately from the last committed chunk**, use a reader with `ItemStream` or switch to an input replay/idempotency strategy.

## 5. Fix Using a Custom `ItemStreamReader` with Checkpointing

To see the exact mechanism, let us write a reader backed by an **immutable** list that saves `nextIndex` in `ExecutionContext`. This is an educational example for a single-threaded, fixed-order source; in production, usually prefer Spring Batch's built-in readers.

```java
import java.util.List;
import java.util.Objects;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamException;
import org.springframework.batch.item.ItemStreamReader;

public final class CheckpointingListReader
        implements ItemStreamReader<String> {

    private final List<String> items;
    private final String name;
    private int nextIndex;

    public CheckpointingListReader(String name, List<String> items) {
        this.name = Objects.requireNonNull(name);
        this.items = List.copyOf(items);
    }

    private String checkpointKey() {
        return name + ".nextIndex";
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.getInt(checkpointKey(), 0);

        if (nextIndex < 0 || nextIndex > items.size()) {
            throw new ItemStreamException(
                    "Invalid reader checkpoint for " + name);
        }
    }

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(checkpointKey(), nextIndex);
    }

    @Override
    public void close() {
        // No external resources to close.
    }
}
```

Explanation:

- `nextIndex` always points to **the next item** not yet returned, avoiding confusion with the last-read index.
- `open` reads saved state; if none exists, starts at 0.
- `update` puts the checkpoint into the context that the framework persists upon chunk commit.
- `checkpointKey()` is uniquely prefixed to avoid colliding with other streams in the same step.
- `List.copyOf(items)` keeps the list structure immutable **within the current execution**; for accurate restart, the subsequent run must receive **the same data in the same order**.
- This example is safe only for **sequential reading**. If the step uses retry/rollback within a single execution, consider reader rewind capability or framework item buffering; this reader is not yet a production reader for every transaction/concurrency scenario.

### Verifying Checkpointing with JUnit

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckpointingListReaderTest {

    @Test
    void resumesFromTheLastSavedCheckpoint() throws Exception {
        List<String> source = List.of("A", "B", "C", "D");
        ExecutionContext savedContext = new ExecutionContext();

        CheckpointingListReader first =
                new CheckpointingListReader("orders", source);
        first.open(savedContext);

        assertEquals("A", first.read());
        assertEquals("B", first.read());

        // Simulate successful chunk boundary:
        first.update(savedContext);

        // Item C was read, but the next chunk has not committed:
        assertEquals("C", first.read());
        first.close();

        // Create a new reader as after crash/restart:
        CheckpointingListReader restarted =
                new CheckpointingListReader("orders", source);
        restarted.open(savedContext);

        assertEquals("C", restarted.read());
        assertEquals("D", restarted.read());
        restarted.close();
    }
}
```

This test illustrates **the logic of saving and restoring an index in `ExecutionContext`**, not a full restart test. It does not exercise `JobRepository`, simulate real transactions/databases, or verify writer idempotency. An integration test must run the job/step, inject a real failure after a committed chunk, then re-launch the same `JobInstance` and verify output.

### Custom Checkpoints More Complex Than an Index

| Data source | State that may need saving | Conditions for accurate replay |
| --- | --- | --- |
| Record-based file | Item/byte offset, resource ID, encoding | File unchanged; reader understands record separator and BOM |
| JDBC cursor | Framework-managed position or query bookmark | Data/query ordering sufficiently stable |
| JDBC paging | Sort keys, paging state, snapshot logic | Deterministic and stable sort key |
| Paginated API | Page token/cursor, resource version, intra-page position | Token still valid; endpoint returns same dataset |
| Kafka/queue | Offset/acknowledgment or durable message ID | Commit/ack policy aligned with writer and transaction |
| Multiple files | Current file, position within file, file list/version | File list and ordering reproducible |

Do not attempt to store entire file contents, objects holding open connections, or iterators inside `ExecutionContext`. Context is for **small, durable, serializable checkpoints**, not caching the entire input.

## 6. Prefer Built-in Readers with `saveState(true)`

For common sources, check whether a Spring Batch reader already supports `ItemStream` and checkpointing. For instance, `FlatFileItemReader`, `JdbcCursorItemReader`, and `JdbcPagingItemReader` have state-saving mechanisms tailored to their characteristics.

### Example `FlatFileItemReader` for Restart

```java
import java.math.BigDecimal;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class RestartableFileReaderConfig {

    public record OrderRow(String orderId, BigDecimal amount) {}

    @Bean
    @StepScope
    public FlatFileItemReader<OrderRow> ordersReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("ordersReader")
                .resource(new FileSystemResource(inputFile))
                .encoding("UTF-8")
                .strict(true)
                .linesToSkip(1) // Skip CSV header.
                .saveState(true)
                .delimited()
                .names("orderId", "amount")
                .fieldSetMapper(fields -> new OrderRow(
                        fields.readString("orderId"),
                        fields.readBigDecimal("amount")))
                .build();
    }
}
```

`saveState(true)` is the default for this builder in Spring Batch 5.2, yet writing it explicitly helps maintainers recognize that **restart from checkpoint is a requirement**. When saving state, `name("ordersReader")` supplies part of the identifier the reader uses to build keys in `ExecutionContext`.

`@StepScope` lets the reader obtain `inputFile` from `JobParameters` and scopes the bean to the step execution; **`@StepScope` does not replace `saveState` or `ItemStream`**. In a Spring Batch context with StepScope registered, Spring creates the appropriate scoped proxy.

Conditions for the example to restart properly:

1. The `inputFile` must have **the same content and record ordering** across re-runs of the same work.
2. The reader name and checkpoint keys must remain compatible across deployments; changing `name` can render old keys unreadable.
3. Metadata tables and the `JobInstance`'s `StepExecutionContext` must remain intact.
4. The step must have the reader stream registered by the framework and invoke open/close in the proper lifecycle.
5. The writer/transaction must safely handle items from an uncommitted chunk.
6. The file must still be reopenable; temporary paths deleted between runs will not support restart even if the reader saved state.

In particular, do not manually set a fixed `currentItemCount` on each run to "resume at a known line", as that easily overwrites or bypasses real checkpoints. Only use position-initialization options when they reflect an intentional processing contract.

### Specific Notes for JDBC Readers

| Reader | Restart issue | Recommendation |
| --- | --- | --- |
| `JdbcCursorItemReader` | Result set or row ordering may change between reads | SQL with deterministic order, source consistent with resume point; check `saveState` |
| `JdbcPagingItemReader` | Paging must accurately determine the resume point | Use a stable and **unique** sort key; watch out for inserted/deleted/updated rows |
| Reader scanning a continuously mutating table | Physical offset no longer matches the same business row | Snapshot/tag rows by batch ID or process indicator |
| Session-based cursor API reader | Cursor/token expires after crash | Use a durable replayable token or stage data before processing |

A `SELECT * FROM orders` without `ORDER BY` is a source of risk if the reader/checkpoint relies on row position. Even with `ORDER BY created_at`, if multiple rows share the same `created_at`, row ordering between them may be non-deterministic. With paging readers, choose a unique sort key like `(created_at, order_id)` when appropriate and ensure the source does not mutate in ways that skip rows.

## 7. When a Reader Has `ItemStream` But a Wrapper Hides Its Lifecycle

A subtle bug: a developer chooses a checkpointed `FlatFileItemReader` or `JdbcCursorItemReader`, wraps it inside another `ItemReader`, and passes only the wrapper to the step. Spring Batch automatically registers an `ItemStream` when it is the **direct** reader/writer/processor of the step. A hidden inner delegate may never have `open`, `update`, or `close` called by the framework.

Example with a simple forwarding wrapper:

```java
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemStreamReader;

// delegate is a reader that supports checkpointing.
ItemStreamReader<String> delegate = /* actual reader */;

ItemReader<String> wrapper = () -> delegate.read();
```

If you only pass `wrapper` to `StepBuilder.reader(...)`, `delegate`'s lifecycle is not guaranteed. You must **register the delegate with the step**:

```java
@Bean
Step stepWithWrappedReader(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> delegate,
        ItemWriter<String> writer) {

    ItemReader<String> wrapper = delegate::read;

    return new StepBuilder("stepWithWrappedReader", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(wrapper)
            .writer(writer)
            .stream(delegate) // Calls open/update/close for the hidden stream.
            .build();
}
```

This code lives in an application `@Configuration` class and assumes the corresponding beans and imports exist. Key imports: `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.batch.item.ItemReader`, `ItemWriter`, and `ItemStreamReader`.

Alternatively, write the wrapper to **also implement `ItemStreamReader`** and forward `open`/`update`/`close` to the delegate, making sure not to register the same stream twice. If there are multiple nested readers/writers, give each stream its own checkpoint key in `ExecutionContext`.

Also note: a wrapper hiding a delegate's `StepListener` can drop listener callbacks as well, though that is a separate issue from `ItemStream` and must be configured appropriately.

## 8. Restarting the Same `JobInstance` and `JobParameters`

A job restart is not "re-running some job with nearly identical input". It is **re-executing the same `JobInstance`** when metadata allows it.

```text
JobInstance = jobName + identifying JobParameters

Job name: importOrders
Identifying parameters:
  businessDate = 2026-11-15
  inputVersion = orders-v3-sha256-...
```

Two consecutive `JobExecution`s intended to belong to the same instance need the same job name and the same set of identifying parameters. Example of stable preparation:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputVersion", "orders-v3", true)
        .toJobParameters();

// After FAILED, reuse the exact same identifying parameters
// to re-launch the same JobInstance:
JobParameters restartParameters =
        new JobParametersBuilder(parameters).toJobParameters();
```

This example only prepares parameters; it does not execute the job. When calling `JobLauncher.run(job, restartParameters)` with an appropriate job/repository, Spring Batch applies its restart rules. `JobInstanceAlreadyCompleteException` occurs when the instance has already completed; `JobExecutionAlreadyRunningException` occurs when the framework still records a running execution; errors of this kind **must not be solved by adding a timestamp** if the goal is restart.

Distinguish commonly confused configurations:

| Configuration or action | Actual effect | Does it fix a non-restartable reader? |
| --- | --- | --- |
| `JobBuilder.preventRestart()` | Forbids restarting the job | **No**; simply accepts losing restart capability |
| `saveState(false)` on reader | Does not save reader checkpoint | **No**; usually causes the problem itself |
| `@StepScope` | Scopes bean to step and resolves runtime parameters | **No** if the reader does not save state |
| `allowStartIfComplete(true)` on step | Allows re-running a completed step on subsequent executions | **No**; can cause unintended replay |
| Changing `run.id`/UUID | Creates a new job instance if param is identifying | **No**; may reprocess from the beginning |
| `saveState(true)` + proper `name` | Enables stateful readers to save checkpoints | **Helpful**, if the source is stable and lifecycle works |
| Implementing `ItemStreamReader` | Defines custom state/recovery logic | **Helpful**, if `open/update` are correct and registered |
| Process indicator + idempotent writer | Avoids re-reading processed records without relying on offsets | **Alternative solution**, requires proper transaction design |

If a step already `COMPLETED` before the job failed in a later step, Spring Batch can skip that step on restart; do not force re-reading just to "run everything". If a step `FAILED`, merely having a checkpoint does not guarantee safe restart if the source or writer changed.

## 9. When the Source Does Not Support Replay: Use a Process Indicator

Not every source can recover by offset. For example, an HTTP endpoint that streams once or a database whose row order constantly shifts. In those cases, do not try to turn an in-RAM `nextIndex` into a reliable checkpoint.

A common strategy is a **process indicator**: the source carries durable status indicating which records have already been processed successfully. On each run, the reader selects only records where `processed=false`. Completion state then **lives in business data**, independent of the reader's physical offset.

Conceptual SQL example:

```sql
SELECT id, payload
FROM import_inbox
WHERE processed = FALSE
ORDER BY id;
```

Once an item is written successfully, the application marks it processed inside an appropriate transaction:

```sql
UPDATE import_inbox
SET processed = TRUE
WHERE id = :id
  AND processed = FALSE;
```

If the target data and `import_inbox` table reside in **the same database transaction**, the writer can write results and update the indicator together, minimizing the window where a row is "already processed yet still selectable". When using different databases/resources, design idempotency keys, outbox/inbox, or independent confirmation rules.

With this strategy, some readers are configured with `saveState(false)` **intentionally**, because position-based checkpoints become invalid as the unprocessed dataset shrinks after every commit. This is an important exception: **a reader that does not save offsets can still support business-level restart** if the overall system ensures only unprocessed items are selected and side effects can be replayed safely.

Considerations:

- The system must have a unique business key and mark completion **after** results are durably written under the chosen transaction/consistency model.
- If multiple workers read the same source, a **claim/locking** mechanism is needed to avoid processing the same row concurrently.
- Statuses like `NEW`, `PROCESSING`, `DONE`, `FAILED`, and lease timeouts may be needed for distributed sources.
- When input mutates while the job is running, define "the record set for this period" using a batch ID, timestamp/snapshot, or staging list.
- `processed=false` by itself does not solve an external API having received a request before the DB marked it done; idempotency at the target system is still required.

## 10. Multi-Threaded Steps and Limits of Position-Based Checkpoints

A reader may restart cleanly in a sequential step yet fail when multiple threads call `read()`. In a multi-threaded step, chunks can be processed and committed **out of read order**.

```text
Reader emits items: A, B, C, D, E, F

Thread 1 takes A,B,C -> slow writer
Thread 2 takes D,E,F -> commits first

A checkpoint index=6 does not prove A,B,C committed.
```

Merely locking `read()` with `synchronized` prevents two threads from reading the same slot simultaneously, but **does not guarantee checkpoints reflect all committed chunks**. Spring Batch provides `SynchronizedItemStreamReader` to wrap non-thread-safe readers; the API documentation warns that if reprocessing items is an issue, this approach can render the job non-restartable.

Options to consider:

1. **Keep a sequential-reading step** if correctness and restartability matter more than throughput.
2. **Partitioning**: split the source into independent ranges, each partition having its own reader, `StepExecution`, and checkpoint; partition keys/boundaries must stay stable.
3. **Process indicator/claim queue**: each item has durable processing state rather than sharing one sequential pointer.
4. **Idempotent writer** to absorb replayed items if failure occurs mid-way across non-transactional side effects.

Do not arbitrarily enable `saveState(true)` on a multi-threaded reader hoping it becomes safe. Some implementations recommend **disabling state saving during concurrent execution**, relying instead on a separate data strategy for restartability.

## 11. Transaction Boundaries, Skips, and Rollbacks

Accurate restart does not depend on the reader alone. After processing a chunk, Spring Batch must bring reader state and business results to a consistent point.

Suppose chunk size is 3:

```text
Committed checkpoint: nextIndex = 6

Reader reads indices 6, 7, 8
Processor processes 6, 7, 8
Writer calls external API for 6, 7, 8
   |
   +-- API accepted items 6, 7
   +-- item 8 times out
   +-- chunk rolls back / checkpoint 6 remains

Restart from index 6:
  re-sends items 6, 7, 8
```

If the writer shares a transaction with metadata, rolling back before commit normally undoes both data and checkpoint. With **external HTTP APIs, emails, files, or queues outside the transaction**, a `JobRepository` rollback cannot undo side effects that already happened. Therefore, even a restartable reader is not sufficient by itself to guarantee **exactly-once business effects**.

A few rules:

- `readCount` is the count of items successfully read as recorded by the framework, not always a file's physical offset; do not derive all checkpoints from `readCount`.
- Errors allowed by `skipPolicy` can increment `readSkipCount`, `processSkipCount`, or `writeSkipCount`; for custom readers, define whether the failing item is consumed and advances position properly.
- During retries, an item may be read/processed/written multiple times within one execution; `read()` invocations do not equal committed item counts.
- `ExecutionContext` is persisted at transaction boundaries; do not call `update` or manually persist state after every item without a matching commit mechanism.
- For non-transactional targets, use an idempotency key tied to **business identity**, not `jobExecutionId` since that ID changes on restart.

A system requiring duplicate-free output must control **reader replay**, **commit points**, and **writer side effects** together.

## 12. How to Investigate a Job That Restarts From the Beginning

Work in order instead of tweaking multiple configurations at once.

### Step 1 — Identify the Run and Instance

Record `jobName`, `jobInstanceId`, `jobExecutionId`, `stepName`, `stepExecutionId`, and identifying `JobParameters`. Confirm the subsequent run was truly a **restart of the same `JobInstance`**, not a new instance with a changed `run.id`, timestamp, or resource path.

### Step 2 — Check Which Steps Re-ran

Using `JobExplorer`, inspect the `FAILED` run and the subsequent run. Check whether the previous step was `FAILED`/`STOPPED` or `COMPLETED`; do not assume every step re-runs.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public void showExecutions(JobExplorer explorer, long jobExecutionId) {
    JobExecution job = explorer.getJobExecution(jobExecutionId);

    if (job == null) {
        throw new IllegalArgumentException("Unknown execution");
    }

    System.out.printf("job=%s instance=%s execution=%s status=%s%n",
            job.getJobInstance().getJobName(),
            job.getJobInstance().getId(),
            job.getId(),
            job.getStatus());

    for (StepExecution step : job.getStepExecutions()) {
        System.out.printf(
                "step=%s stepExecution=%s status=%s " +
                "read=%d write=%d commit=%d rollback=%d contextKeys=%s%n",
                step.getStepName(), step.getId(), step.getStatus(),
                step.getReadCount(), step.getWriteCount(),
                step.getCommitCount(), step.getRollbackCount(),
                step.getExecutionContext().keySet());
    }
}
```

This is an illustrative snippet using **Spring Batch 5.2.x**. Context keys are helpful for locating reader checkpoints, but may expose names/paths or sensitive data; print them only in authorized investigation environments. `JobExplorer` reflects persisted metadata and does not prove all non-transactional side effects committed.

### Step 3 — Check `ItemStream` and `saveState`

Verify whether the actual reader class implements `ItemStream` or `ItemStreamReader`. For built-in readers, confirm `saveState(true)` and a stable reader name. For custom readers, check the logic:

- Does `open` read the right checkpoint key?
- Does `update` save the "next item" state at commit time?
- Does `close` leave saved data intact rather than wiping the checkpoint?
- Does `read` accidentally reset the index when opening a new resource?
- Did the context key get renamed after an upgrade/configuration change?

### Step 4 — Check Wrappers/Delegates

If the real reader sits inside `CompositeItemReader` or another wrapper, check whether the step invokes `ItemStream` callbacks for **every delegate that needs state saved**. For delegates not auto-discovered, register them via `.stream(delegate)` or make the wrapper forward lifecycle calls.

### Step 5 — Check Whether Input Is Immutable

Cross-check checksums/file versions, record counts, sort key ordering, source data timestamps, and paging policies. The same `index=200` is useless if position 200 now holds a different record.

### Step 6 — Check Writer and Transactions

Reconcile items written/acknowledged by external systems against the last checkpoint. If side effects already occurred past the checkpoint, **do not auto-restart** before verifying deduplication/idempotency.

### Step 7 — Pick a Recovery Path

You may fix the reader, restore immutable input and restart, switch to a process indicator, use staging/replay, or create a **controlled new job instance** after reconciliation. The last option is not a checkpoint restart; explicitly record it as a rerun/replay.

## 13. Reading Metadata via SQL When Needed

If using a JDBC `JobRepository` and the default `BATCH_` table prefix, the following query reveals execution/step history. Read-only—do not edit metadata:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS JOB_STATUS,
    je.START_TIME AS JOB_START_TIME,
    je.END_TIME AS JOB_END_TIME,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.LAST_UPDATED
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = :jobName
ORDER BY je.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
```

`:jobName` is an illustrative named parameter; when running in a plain SQL tool, use the appropriate bind syntax. Step checkpoints normally reside in `BATCH_STEP_EXECUTION_CONTEXT`, yet **do not manually parse, edit, or delete** context rows via SQL to "move the pointer". Serializers, internal keys, and version compatibility can change. Prefer reading via `JobExplorer`/Spring Batch APIs and recovering metadata only via official operational procedures.

Key fields to cross-check:

| Metadata | Investigation meaning |
| --- | --- |
| `JOB_INSTANCE_ID` | Whether executions truly belong to the same instance |
| `JOB_EXECUTION_ID` | Whether it was a genuine restart or a new instance each time |
| `STEP_EXECUTION_ID` | Which step ran on the first vs. subsequent attempts |
| `STATUS` | `FAILED`, `STARTED`, `COMPLETED`, `STOPPED` |
| `READ_COUNT`/`WRITE_COUNT` | Volume recorded by the framework, not a sole checkpoint |
| `COMMIT_COUNT`/`ROLLBACK_COUNT` | Whether chunks committed or rolled back |
| `ExecutionContext` | What keys and positions the reader saved at commit time |
| `LAST_UPDATED` | Last metadata write time; not equivalent to a continuous heartbeat |

If status remains `STARTED` after the process died, handle the **orphaned execution** via a dedicated verification procedure; do not manually set it to `FAILED` via SQL before reconciling data.

## 14. Testing Restart at the Integration Level

A reader with passing unit tests for `open/update` can still fail in a real job: unregistered stream, mutated file, misaligned transactions, or a writer lacking idempotency.

Basic integration test scenario:

1. Create a **test-dedicated** repository/database, a fixed input source of 6 records, and a writer with a unique business key.
2. Set chunk size 2; on the first run commit records 1–2 and intentionally trigger a non-skippable error on record 3.
3. Verify the first `JobExecution` is `FAILED`, output contains exactly records 1–2, and metadata holds the committed chunk's checkpoint.
4. Remove the failure trigger **without changing identifying `JobParameters`** and without deleting context/repository.
5. Re-run the same job/instance; the reader must resume from record 3 (or replay safely per the chosen strategy).
6. Verify the new execution is `COMPLETED` and the target holds exactly 6 unique business IDs.
7. Inspect both `readCount`/`writeCount` and actual data; do not check status alone.

Conceptual assertion example:

```java
// In an integration test configured with Spring Batch and a test DB:
JobExecution first = jobLauncher.run(importOrdersJob, fixedParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

disableInjectedFailure();

JobExecution restarted = jobLauncher.run(importOrdersJob, fixedParameters);
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

// Count unique business records, do not blindly sum writeCounts:
assertEquals(6, orderRepository.count());
assertEquals(6, orderRepository.countDistinctOrderIds());
```

This is **intentional pseudocode**: `disableInjectedFailure()`, `orderRepository`, and the job/test DB setup are project components, not Spring Batch APIs. `BatchStatus` is imported from `org.springframework.batch.core.BatchStatus` in Spring Batch 5.x.

To simulate a real failure, inject the failure at a deterministic point **after at least one chunk has committed**. Throwing in the first chunk before commit can leave valid output empty, failing to verify resume capability. Tests should also verify that a fresh reader is created, `ExecutionContext` remains durable across a Spring context reload, and the source did not change.

### Edge Cases Worth Testing

| Scenario | Expectation |
| --- | --- |
| Crash before first chunk commits | Restarts from the beginning with no doubled committed side effects |
| Crash after second chunk commits | Resumes from saved checkpoint |
| Changing to `saveState(false)` | Test catches unintended replay |
| Wrapper does not register delegate | Test catches missing `open/update` callbacks |
| Reader renamed between two deployments | Test/investigation catches incompatible context keys |
| Input file modified after failure | Restart rejected or routed to dedicated replay workflow |
| Writer calls external API and times out | Idempotency key prevents duplicate side effects |
| Multi-threaded reader | No skipped/duplicated items from non-deterministic checkpoints |
| Process dies while updating metadata | Inspect status and committed checkpoints before recovery |

## 15. Remediation Procedure on a Live System

Once an incident occurs in production, the top priority is **preserving data integrity before re-running**:

```text
Detect FAILED / duplicate / reader reset
                 |
                 v
   Confirm old process fully stopped?
                 |
          +------+-------+
          |              |
         No             Yes
          |              |
   Do not restart        v
                  Inspect metadata
                  and source version
                         |
                  +------+-------+
                  |              |
          Checkpoint reliable?   No
                  |              |
                 Yes             v
                  |      Reconcile input/output,
                  v      design safe replay
           Writer idempotent
           or same transaction?
                  |
           +------+------+
           |             |
          Yes            No
           |             |
     Restart same        v
     JobInstance    Stop to reconcile
                    and mitigate duplicates
```

The runbook should record: execution ID, input checksum/version, last confirmed checkpoint, output row count by business key, reader type, `saveState` setting, replay approver, and post-recovery reconciliation results.

Strictly avoid uncontrolled "workarounds" such as:

- Adding a `run.id`/UUID on every retry to dodge `JobExecutionAlreadyRunningException` or `JobInstanceAlreadyCompleteException`.
- Deleting `BATCH_STEP_EXECUTION_CONTEXT` or manually editing `STATUS`/`VERSION` columns.
- Flipping `saveState(true)` without checking whether the source changed and whether the writer can duplicate writes.
- Treating `@StepScope` as proof that a reader has checkpointing.
- Retrying endlessly against external APIs that lack idempotency.
- Marking records processed before results are durably persisted, leading to missed items after a crash.

## 16. Comparing Design Approaches

| Approach | Best suited when | Trade-offs / risks |
| --- | --- | --- |
| Built-in `ItemStreamReader` + `saveState(true)` | File/cursor/paging with stable input | Must keep source/schema/sort order and metadata consistent |
| Custom `ItemStreamReader` | Custom source with replayable cursor/offset | You own `open/update/close`, keys, transactions, and tests |
| Process indicator | Data has durable status; avoid offset dependency | Needs claim/idempotency/transactions and record reconciliation |
| Snapshot or staged input | API/DB source mutates during execution | Costs storage/ETL, but yields a reproducible source |
| Partitioning with per-partition checkpoints | Large sources needing parallel scale | Requires stable partition design with no overlap |
| Restart from beginning with idempotent writer | Job permits full replay | Slower; must prove zero duplicate side effects |
| Disable restart (`preventRestart`) | Intentionally one-shot work with external recovery | Does not meet restart needs if business requires resuming |

Each option should be evaluated against **business goals**: must it process exactly once or can it replay? Can the original input set be reconstructed? Does the target have a unique business key or idempotency? Do metadata and target data share a transaction?

## 17. Quick Troubleshooting Summary

| Symptom | Likely cause | Approach |
| --- | --- | --- |
| Custom reader always reads from the start | Only implements `ItemReader`; index in RAM | Use `ItemStreamReader` and checkpoint in `ExecutionContext` |
| `FlatFileItemReader` does not resume from old mark | `saveState(false)` or different reader name/context | Check `saveState(true)`, `name`, and committed state |
| Has `@StepScope` yet still replays | Scope is not state persistence | Combine scope with a reader that implements `ItemStream` |
| Stream delegate never gets `open/update` | Wrapper did not register delegate | `.stream(delegate)` or forward lifecycle in wrapper |
| `JdbcPagingItemReader` duplicates/skips records | Non-unique sort key or mutating source | Unique stable sort key, snapshot/process indicator |
| Job restarts yet steps do not run at all | Steps already `COMPLETED`, skipped per restart rules | Confirm status and design intent; do not force-rerun blindly |
| Job refuses restart | `preventRestart` or repository state blocks restart | Distinguish job policy from reader capability |
| Checkpoint exists yet duplicates still appear | Previous chunk uncommitted or non-transactional writer | Idempotent writer, reconcile side effects |
| Reader breaks under parallel execution | State shared across threads; checkpoint cannot represent progress | Partitioning, process indicator, or sequential reading |
| Input API only streams once | Token/offset not durable | Staging, durable cursor, event replay, or inbox |
| Restart reads different data than before | File replaced, unstable SQL | Source version/checksum, snapshot |
| `STARTED` yet process died | Metadata never recorded terminal status | Verify liveness, use recovery runbook, avoid ad hoc SQL edits |

## 18. References

The Java examples above use **Spring Batch 5.2.x** packages, such as `org.springframework.batch.item.ItemStreamReader`, `ExecutionContext`, and `org.springframework.batch.item.file.FlatFileItemReader`. In Spring Batch 6.x, many item-infrastructure APIs reside under `org.springframework.batch.infrastructure.item`; adjust according to actual dependencies when implementing. Official links:

- [Spring Batch 5.2 — ItemStream, ExecutionContext, and restart](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html)
- [Spring Batch 5.2 — Creating custom ItemReaders](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/custom.html)
- [Spring Batch 5.2 — Registering ItemStream with a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/registering-item-streams.html)
- [Spring Batch 5.2 — Preventing State Persistence (process indicator)](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/process-indicator.html)
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html)
- [Spring Batch 5.2 — ItemReader/Writer Implementations and SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-reader-writer-implementations.html)
- [Spring Batch 5.2 API — FlatFileItemReaderBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/builder/FlatFileItemReaderBuilder.html)
- [Spring Batch 5.2 API — ItemStream](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/ItemStream.html)
- [Spring Batch 5.2 API — SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/support/SynchronizedItemStreamReader.html)

Bottom line: **a restartable job is only valuable when every stateful component has a sound recovery strategy**. For sequential readers and immutable sources, use `ItemStream` to persist checkpoints in `ExecutionContext` and let the framework manage updates alongside commits. For non-replayable sources or parallel processing, apply process indicators, staging, partitioning, and intentional idempotency. Before restarting in production, always verify **saved checkpoints**, **source data**, and **committed side effects**, because duplicate reads after restart not only slow the job down—they can corrupt business data.
