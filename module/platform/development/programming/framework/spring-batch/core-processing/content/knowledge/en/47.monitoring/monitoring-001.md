# Counting `read`, `write`, `filter`, and `skip` When Monitoring Spring Batch

A batch job with a `COMPLETED` status is not enough to confirm that data was processed as expected. A job ingesting 10,000 records may complete while writing only 9,400 records because 500 records did not meet business conditions and 100 records were skipped due to permitted errors. To evaluate the actual outcome, Spring Batch stores **item processing counters** in `StepExecution`: successful reads (`read`), successful writes (`write`), business-filtered items (`filter`), and error-skipped items (`skip`).

This article focuses on those four counter groups within the **Monitoring** scope of *Spring Batch Core Processing*: the exact meaning of each counter, how Spring Batch updates them, how to read them from Java and the database, how to monitor them while a job is running, and common pitfalls when handling retry, rollback, or restart.

## 1. Item Flow and Where Counters Originate

In a typical chunk-oriented step:

```text
                 ItemReader.read()
                         |
            +------------+-------------+
            |                          |
      Returns item               Throws error
            |                          |
            v                          v
       readCount++               Skippable?
            |                          |
            v                          +-- Yes --> readSkipCount++
   ItemProcessor.process()             |
            |                          +-- No  --> Step FAILED
       +----+-------------+
       |                  |
       v                  v
  Returns null       Returns item         Throws error
       |                  |                  |
       v                  |                  +-- Skippable --> processSkipCount++
 filterCount++            |                  +-- No        --> Step FAILED
       |                  v
 Not sent to writer  ItemWriter.write(chunk)
                          |
                    +-----+----------+
                    |                |
                    v                v
              Write succeeds    Write fails
                    |                |
                    v                +-- Valid skippable item --> writeSkipCount++
               writeCount            +-- Unrecoverable          --> Step FAILED
```

The diagram is a conceptual model of the **accepted** outcome after the transaction/chunk mechanism. In practice, the writer receives **the entire chunk** and may retry or rollback; in that case, the number of `read`, `process`, and `write` calls does not necessarily equal the final counters in `StepExecution`. Calling `ItemReader.read()` and returning `null` to signal end of data **does not** increment `readCount`.

The unit of a counter is the **item processed by the framework**, not necessarily a text line, database row, method invocation count, or physical record updated. For example, an `ItemWriter` might call a stored procedure that modifies multiple database rows for a single item; `writeCount` is still counted according to the number of items the writer successfully processed under the step's model.

## 2. The Four Counter Groups of `StepExecution`

| Counter / getter | Practical meaning | When to pay attention |
| --- | --- | --- |
| `readCount` — `getReadCount()` | Number of items **successfully** read from `ItemReader` | Excludes reads returning `null` to signal end of data; skipped read errors have their own counter |
| `writeCount` — `getWriteCount()` | Number of items successfully processed by the writer across chunks accepted by the framework | Not identical to the number of `ItemWriter.write(...)` calls or the number of SQL rows actually changed |
| `filterCount` — `getFilterCount()` | Number of items excluded from the write flow by `ItemProcessor` **returning `null`** | A normal processing decision, not an error |
| `readSkipCount` — `getReadSkipCount()` | Number of read errors accepted by the skip policy | For example, a malformed input line causing the reader to throw a skippable exception |
| `processSkipCount` — `getProcessSkipCount()` | Number of items skipped due to an exception during processing | Different from the processor returning `null` |
| `writeSkipCount` — `getWriteSkipCount()` | Number of items skipped due to an error during writing | Because the writer processes chunks, it may need to rollback and retry item-by-item to identify the failing item |
| `skipCount` — `getSkipCount()` | **Sum** of the three skip types above | `readSkipCount + processSkipCount + writeSkipCount`; **does not** include `filterCount` |

These getters are on `org.springframework.batch.core.StepExecution` in Spring Batch 5.x. Other related fields worth checking are `getCommitCount()`, `getRollbackCount()`, `getStatus()`, and `getExitStatus()`. They help explain why counters in a given run may differ from expectations.

**Do not add `filterCount` to `skipCount`.** The two represent different decisions:

- **Filter**: a valid record that the application decides not to send to the writer, such as a canceled order or a transaction outside the reconciliation period.
- **Skip**: encountering an error evaluated as skippable under the fault tolerance policy, such as a malformed CSV line or an item violating a validation rule that may be discarded.

Spring Batch only increments a skip counter when an error is **handled by the skip mechanism**. An exception that is retried and then succeeds does not automatically become a skip; a severe exception that causes the step to become `FAILED` is also not automatically recorded as a skipped item.

## 3. Concrete Calculation Example

Suppose a step reads a file containing 10 business lines; 2 lines have formatting errors right in the reader, and 8 lines are read successfully. Out of those 8 lines, the processor filters 1 canceled order and skips 1 invalid-data order due to an error; the writer encounters a skippable error on 1 item; the remaining 5 items are written successfully.

| Metric | Value | Explanation |
| --- | ---: | --- |
| Business lines in file | 10 | Physical observations from the example's data source |
| `readCount` | 8 | Reader successfully returned 8 items |
| `readSkipCount` | 2 | Two reads failed and were allowed to be skipped |
| `filterCount` | 1 | Processor returned `null` for one valid item |
| `processSkipCount` | 1 | One item threw a skippable exception during processing |
| `writeSkipCount` | 1 | One item failed during writing and was skipped |
| `writeCount` | 5 | Five items were written successfully |
| `skipCount` | 4 | `2 + 1 + 1`, excluding filter |

For this **simple example where one input item maps to at most one output item**, with no retry/rollback affecting the final result, we have:

```text
10 source lines = 8 successful reads + 2 readSkip

8 successful reads = 1 filter + 1 processSkip + 1 writeSkip + 5 write

skipCount = readSkipCount + processSkipCount + writeSkipCount
          = 2 + 1 + 1 = 4
```

The first two equalities are only meant to **illustrate this specific one-to-one scenario**, not as a universal invariant for every step. A step with an aggregating writer, a reader reading from multiple sources, a stateful processor, transaction rollbacks, or job restarts can make this addition fail to describe all business records accurately. The equality for `skipCount` is the definition of total skips at the step level.

## 4. Where Does Spring Batch Update Counters?

In chunk-oriented processing, Spring Batch uses `StepContribution` to collect the results of a processing segment and merges them into `StepExecution` when the chunk succeeds. `StepExecution` is persisted periodically by `JobRepository`, typically tied to transaction/commit boundaries. Therefore, the counters in the repository represent **recorded processing outcomes**, rather than a counter incremented every time business code is invoked.

```text
     StepExecution (step total)
           ^
           | apply / update per chunk
           |
     StepContribution (current chunk result)
           ^
           |
   read / process / filter / write / skip
           |
           v
   Transaction commit or rollback
```

In standard steps driven by `TaskletStep` and the chunk machinery, the framework computes the counters automatically. You do not need to call `stepExecution.setReadCount(...)` or `setWriteCount(...)` manually just to track normal `ItemReader`/`ItemWriter` activity.

Points that affect interpretation:

1. **Chunk commit:** `readCount` and `writeCount` observed while a step is running may not fully reflect the current chunk because counters must be synchronized and saved to the repository.
2. **Rollback:** a failed write attempt may require reprocessing the chunk or individual items. Final counters must not be interpreted as the number of times writer methods were called.
3. **Retry:** an item retried multiple times before succeeding may contribute only one item to the outcome; do not use `onProcessError`/`onWriteError` callbacks to infer `skipCount`.
4. **Skip:** an exception matching the skip policy increments one of the three skip counters. A non-skippable error can stop the step and leave a `FAILED` status.
5. **Restart:** a `JobInstance` can have multiple `JobExecution` instances, and each rerun creates a corresponding `StepExecution` when the step executes. You must pick the right execution to read counters.

## 5. Reading Metrics Directly from `StepExecution`

In Spring Batch 5.x, the getter APIs can be used in tests, listeners, internal services, or after receiving a `JobExecution` from the launcher:

```java
import org.springframework.batch.core.StepExecution;

public record StepCounts(
        long read,
        long write,
        long filter,
        long readSkip,
        long processSkip,
        long writeSkip,
        long totalSkip,
        long commits,
        long rollbacks) {

    public static StepCounts from(StepExecution step) {
        return new StepCounts(
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

`record` requires Java 16+; Spring Batch 5.x is commonly used with Java 17. If a project uses an older Java version on an older Spring Batch branch, it can be replaced with a regular class.

To retrieve step metrics after a job runs:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

public void printStepCounts(JobExecution execution) {
    for (StepExecution step : execution.getStepExecutions()) {
        StepCounts counts = StepCounts.from(step);
        System.out.printf(
                "jobExecution=%s step=%s status=%s read=%d write=%d " +
                "filter=%d skip=%d [read=%d process=%d write=%d]%n",
                execution.getId(),
                step.getStepName(),
                step.getStatus(),
                counts.read(),
                counts.write(),
                counts.filter(),
                counts.totalSkip(),
                counts.readSkip(),
                counts.processSkip(),
                counts.writeSkip());
    }
}
```

`JobExecution.getStepExecutions()` returns the collection of `StepExecution` instances attached to **the job execution under consideration**. Do not assume every job has only one step; when there are multiple steps, metrics are labeled by `stepName` to avoid confusion.

## 6. Logging Counters with `StepExecutionListener`

If you want a log line when a step finishes (whether it succeeds or fails), `StepExecutionListener.afterStep(...)` is a convenient place to obtain a summary from `StepExecution`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepCountsLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepCountsLoggingListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "step={} jobExecution={} batchStatus={} exitStatus={} " +
                "read={} write={} filter={} " +
                "readSkip={} processSkip={} writeSkip={} totalSkip={} " +
                "commit={} rollback={}",
                step.getStepName(),
                step.getJobExecutionId(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());

        // Do not request changing the ExitStatus already decided by the framework.
        return null;
    }
}
```

`afterStep` can return an `ExitStatus` to participate in adjusting the exit status; returning `null` means contributing no new status. This listener only observes data and does not modify the counters itself.

Attach the listener when configuring the step:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> orderReader,
                      ItemProcessor<Order, ProcessedOrder> orderProcessor,
                      ItemWriter<ProcessedOrder> orderWriter) {
    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener(new StepCountsLoggingListener())
            .build();
}
```

This configuration snippet illustrates attaching a listener in **Spring Batch 5.x**, assuming the `Order` and `ProcessedOrder` types and the reader/processor/writer beans are already defined by the application. The required imports are `org.springframework.batch.core.Step`, `org.springframework.batch.core.job.builder` is not used here, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.item.ItemReader`, `ItemProcessor`, `ItemWriter`, along with `org.springframework.transaction.PlatformTransactionManager`. Across multiple steps, the same listener can be reused as long as it holds no internal mutable state.

**When should you log in `afterStep`?** When you want a summary record for every `StepExecution`, including `FAILED` runs. When you want real-time rates, you need an additional mechanism to read metadata or monitor during execution; do not turn `afterStep` into a live counter because this callback is only invoked at the end of the step.

## 7. Full Example: Filtering One Item and Skipping One Item

The following example demonstrates **Spring Batch 5.2.x**, assuming the application context already has an appropriate `JobRepository` and `PlatformTransactionManager`. The reader supplies six strings; the processor handles three cases:

- `FILTER`: the processor returns `null`, incrementing `filterCount`.
- `SKIP`: the processor throws `IllegalArgumentException`, configured as a skippable exception, incrementing `processSkipCount`.
- Remaining strings: the processor converts them to lowercase and passes them to the writer.

```java
import java.util.List;
import java.util.Locale;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MonitoringStepConfig {

    // Create a dedicated reader for each step execution.
    @Bean
    @StepScope
    public ItemReader<String> monitoredReader() {
        return new ListItemReader<>(List.of(
                "OK-1", "FILTER", "OK-2", "SKIP", "OK-3", "OK-4"));
    }

    @Bean
    public Step monitorStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("monitoredReader") ItemReader<String> reader) {

        ItemProcessor<String, String> processor = item -> {
            if ("FILTER".equals(item)) {
                return null; // Business filtering, not a skip.
            }
            if ("SKIP".equals(item)) {
                throw new IllegalArgumentException("Invalid item");
            }
            return item.toLowerCase(Locale.ROOT);
        };

        ItemWriter<String> writer = chunk -> {
            for (String item : chunk) {
                System.out.println("Written: " + item);
            }
        };

        return new StepBuilder("monitorStep", jobRepository)
                .<String, String>chunk(3, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .skip(IllegalArgumentException.class)
                .skipLimit(2)
                .listener(new StepCountsLoggingListener())
                .build();
    }
}
```

Logical data flow diagram:

```text
Reader (6 items read successfully)
  OK-1   -> processor -> ok-1  -> writer
  FILTER -> processor -> null  -> filter
  OK-2   -> processor -> ok-2  -> writer
  SKIP   -> processor -> skippable exception
  OK-3   -> processor -> ok-3  -> writer
  OK-4   -> processor -> ok-4  -> writer

Expected (step COMPLETED):
  readCount        = 6
  writeCount       = 4
  filterCount      = 1
  readSkipCount    = 0
  processSkipCount = 1
  writeSkipCount   = 0
  skipCount        = 1
```

`ListItemReader` is only used for illustrative data. In real systems, read errors can arise from `FlatFileItemReader`, `JdbcCursorItemReader`, or other data sources. The writer in the example prints to the console; when using a database or external API, ensure transactions and idempotency mechanisms are compatible with retry/restart. `@StepScope` creates a separate reader per step execution, avoiding reusing a read position left over from a previous execution.

### Assertion via `JobLauncherTestUtils`

In a Spring Boot application with a valid Batch configuration, you can use `spring-batch-test` to execute a single step by name and verify counters directly from the returned `JobExecution`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MonitorStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Test
    void countsReadWriteFilterAndSkip() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testCase", "countsReadWriteFilterAndSkip")
                .toJobParameters();

        // The context must contain a Step bean named "monitorStep".
        JobExecution jobExecution = launcher.launchStep("monitorStep", parameters);

        StepExecution step = jobExecution.getStepExecutions().stream()
                .filter(s -> s.getStepName().equals("monitorStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(6L, step.getReadCount());
        assertEquals(4L, step.getWriteCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(1L, step.getSkipCount());
    }
}
```

The test assumes `MonitoringStepConfig`, a test datasource/repository, and Spring Batch configuration are loaded into the context. If `JobRepository` retains metadata of a `COMPLETED` job with the same identifying parameters from a previous run, you must isolate/clean the test repository or choose an instance preparation mechanism suited to the test's purpose. Do not use random parameters to mask restart bugs or job identity tests.

## 8. When Is It `filter` and When Is It `skip`?

Consider a job moving orders from raw data to a sales table:

| Scenario | Behavior to consider | Counter |
| --- | --- | --- |
| Canceled order, policy requires not writing | Processor returns `null` | `filterCount` increments |
| Order outside the data period | Processor returns `null` | `filterCount` increments |
| Malformed CSV line allowed to be ignored by policy | Reader throws a skippable exception | `readSkipCount` increments |
| Invalid product code, business rules allow ignoring | Processor throws an exception covered by skip policy | `processSkipCount` increments |
| Writer cannot write an item, error covered by skip policy | Writer error handled via fault tolerance | `writeSkipCount` increments |
| Database unreachable, error not covered by policy | Step fails, requires investigation/restart | Must not be assumed to be a skip |
| Writer fails transiently but retry succeeds | Retried and committed successfully | Not counted as a skip just because an exception occurred |

**Rule:** `return null` is intentional item filtering; `throw` reports an error. `skip` only occurs when the step is configured with `faultTolerant()` and the exception matches the appropriate `skip(...)` or `skipPolicy(...)`. Do not use skip for every error just to force a job to reach `COMPLETED`; especially in financial workflows, skipping can hide critical data loss.

Example of configuring a skip limit in **Spring Batch 5.x**:

```java
new StepBuilder("importStep", jobRepository)
        .<Input, Output>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(RecoverableRecordException.class)
        .skipLimit(10)
        .build();
```

`Input`, `Output`, and `RecoverableRecordException` are application-defined types. With `skipLimit(10)`, the total number of skips across all three phases (read/process/write) can reach at most 10; the next skippable error will fail the step. This is a **total skip** limit, not a separate quota of 10 per phase. `filterCount` does not consume the skip quota.

## 9. Using `SkipListener` to Find Causes, Not to Replace System Counters

Counters tell you **how many** items were skipped; operations often also need to know **why**. `SkipListener` provides callbacks across the three phases:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class InvalidRecordListener implements SkipListener<String, String> {

    private static final Logger log =
            LoggerFactory.getLogger(InvalidRecordListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Skipped while reading: {}", error.toString());
    }

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        log.warn("Skipped while processing item={}: {}", item, error.toString());
    }

    @Override
    public void onSkipInWrite(String item, Throwable error) {
        log.warn("Skipped while writing item={}: {}", item, error.toString());
    }
}
```

Attach it with `.listener(new InvalidRecordListener())` on the appropriate step builder. In the read phase, the reader may not have been able to produce an item, so the callback only receives the error cause; in process and write, the callback also receives the item. When logging, do not write full sensitive record data into the monitoring system.

`ItemReadListener.onReadError`, `ItemProcessListener.onProcessError`, and `ItemWriteListener.onWriteError` are signals that **an error occurred**, not confirmation that an item was skipped: the error might be retried successfully or fail the step. `SkipListener` is better suited for logging items that were actually skipped. Even so, the authoritative source of metrics remains `StepExecution` and `JobRepository` metadata; avoid incrementing an `AtomicLong` in each error callback and calling it `skipCount`, because retry/rollback can make callback counts differ from committed skip counts.

## 10. Viewing Counters After Execution from `JobExplorer`

In an operational application, a monitoring service can read step history from `JobExplorer` using the job execution ID without keeping the original objects in memory:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class BatchStepMonitor {

    private final JobExplorer jobExplorer;

    public BatchStepMonitor(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepCounts> countsOfJobExecution(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId: " + executionId);
        }

        return execution.getStepExecutions().stream()
                .map(StepCounts::from)
                .toList();
    }

    public StepExecution findStep(long jobExecutionId, long stepExecutionId) {
        StepExecution step = jobExplorer.getStepExecution(
                jobExecutionId, stepExecutionId);
        if (step == null) {
            throw new IllegalArgumentException("Unknown step execution");
        }
        return step;
    }
}
```

The example code uses Spring Batch 5.x APIs and Java 17. In practice, the DTO returned to a dashboard should also include `jobExecutionId`, `stepExecutionId`, `stepName`, `BatchStatus`, `ExitStatus`, and the update timestamp so operators know **which run** the counters belong to. `getJobExecution(...)` can return `null` if the ID does not exist.

During execution, `JobExplorer` results reflect **the snapshot saved by the repository** up to query time; the current chunk may not yet be committed, so metrics have some lag. Polling frequency should match chunk size, execution duration, database load, and dashboard requirements.

## 11. Querying the `BATCH_STEP_EXECUTION` Metadata Table Directly

With a JDBC-backed `JobRepository` and the default Batch schema, counters typically reside in the `BATCH_STEP_EXECUTION` table:

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    (READ_SKIP_COUNT + PROCESS_SKIP_COUNT + WRITE_SKIP_COUNT) AS TOTAL_SKIP,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`:jobExecutionId` is a named-parameter placeholder (for example when using `NamedParameterJdbcTemplate`); when running directly in a SQL client, replace it with the actual ID using the syntax supported by the tool. If the system changes the default table prefix or uses a different repository type, adjust the query accordingly.

**Note:** job metadata is critical operational data for restarts and status tracking. Do not update `READ_COUNT`, `WRITE_COUNT`, or `*_SKIP_COUNT` columns directly via SQL to "fix reports." Manual changes can corrupt execution history, hide errors, and hinder investigations.

When a job has multiple steps, display each row by **`JOB_EXECUTION_ID` + `STEP_EXECUTION_ID`**. `STEP_NAME` can be identical across different runs, so it is not sufficient as a unique key for monitoring data.

## 12. Counters and Micrometer: Two Different Types of Metrics

Spring Batch integrates with Micrometer and provides metrics prefixed with `spring.batch`, for example:

| Provided metric | Metric type | What is measured? |
| --- | --- | --- |
| `spring.batch.job` | Timer | Job execution duration |
| `spring.batch.step` | Timer | Step execution duration |
| `spring.batch.item.read` | Timer | Time taken to perform item read operations |
| `spring.batch.item.process` | Timer | Time taken to process items |
| `spring.batch.chunk.write` | Timer | Time taken to write chunks |

These timers are useful for performance analysis, but they are **not equivalent** to `StepExecution.readCount`, `writeCount`, `filterCount`, and `skipCount`. For instance, the sample count of `spring.batch.chunk.write` reflects the number of measured chunk write operations, not the number of items successfully written. A single chunk write might contain 100 items or be retried after an error.

To surface item statistics on a Prometheus/Grafana dashboard or another reporting system, clarify your goal:

- **Exact per-execution reporting:** retrieve counters from `StepExecution` or `JobExplorer`, accompanied by ID/status/timestamp; publish snapshots on chunk commit or step completion according to operational design.
- **Near real-time performance tracking:** use the framework's Micrometer timers for duration and approximate throughput, combined with metadata polling at controlled intervals.
- **Skip root-cause analysis:** use `SkipListener` to record minimal information about the error, error code, and record type; do not use callback counts as persistent total skips.

If emitting custom metrics, pay attention to tag **cardinality**. Putting `jobExecutionId`, item UUIDs, or user information into tags on every time series can cause the number of series to explode rapidly. You can store detailed IDs in logs or an event store while aggregating metrics by job/step name and outcome type.

## 13. Reading Metrics Across Errors, Retry, Rollback, and Restart

### Retry Is Different from Skip

```text
Item X -> writer attempt 1: timeout
       -> retry attempt 2: succeeds
       -> writeCount increments for the successfully written item
       -> writeSkipCount does not increment because the timeout recovered
```

For item Y with an unrecoverable error accepted by the skip policy, `writeSkipCount` increments only when the framework decides to skip it. Do not take the error count from `ItemWriteListener.onWriteError` to infer the number of skipped items.

### Rollback Can Cause Callbacks to Run Multiple Times

If a chunk fails to write, Spring Batch may rollback and reprocess items, especially to isolate which item is skippable. `getRollbackCount()` is a signal to inspect when processing logs show more calls than the final item count. The number of `process()` or `write()` calls alone does not prove an item was committed.

### Restart Creates Distinct `StepExecution` Instances

For example, a `JobInstance` processing by business date has two executions:

| Execution | Step status | `readCount` | `writeCount` | Explanation |
| --- | --- | ---: | ---: | --- |
| `JobExecution 101` | `FAILED` | 500 | 450 | Step failed after the already-processed chunks |
| `JobExecution 102` | `COMPLETED` | 550 | 545 | Restart resumed from the saved state |

Do not conclude that the job read exactly 1,050 **unique** records or wrote 995 **unique** records simply by summing the two rows. Depending on the reader, checkpoint, transaction, and writer behavior, some items may have been retried; business validation may need to reconcile by output data keys. If the goal is per-run statistics, keep metrics separate for each `JobExecution`; if the goal is total completed business records, you need an aggregation rule compatible with your application's restart/idempotency semantics.

### Not Every Step Has Item Counters

A tasklet that only calls an API or runs an aggregate SQL query can finish its work with `readCount = writeCount = filterCount = skipCount = 0`, because it does not process through the standard `ItemReader` → `ItemProcessor` → `ItemWriter` cycle. For specialized tasklets, the number of business objects updated should be measured via application-specific metrics, logs, or reports; do not assign incorrect meaning to default item counters.

## 14. Misleading Situations When Monitoring

| Symptom | Common cause | Recommended action |
| --- | --- | --- |
| `readCount > writeCount` despite no errors | Processor filtered some items | Check `filterCount` before concluding data loss |
| `skipCount = 0` while logs show exceptions | Errors were retried successfully or failed the step; no items were skipped | Distinguish error callbacks, retry, failure, and skip policy |
| `readSkipCount > 0` while `readCount` excludes failed lines | `readCount` only counts successfully read items | Read the two counters separately; do not treat `readCount` as total physical lines |
| `writeCount` differs from DB rows changed | One writer item may write multiple rows, batch, or upsert | Use separate business metrics if you need to count database rows |
| Live counters appear frozen | Chunk has not committed yet or repository snapshot has not updated | Observe commit timing, `lastUpdated`, chunk duration, and polling interval |
| Same item appears multiple times in logs | Retry/rollback re-invoked reader/processor/writer | Use `StepExecution` for summaries; design idempotent writers |
| High `skipCount` yet step is still `COMPLETED` | Policy allowed skipping those errors within the limit | Evaluate data quality thresholds independently from batch status |
| Total counters across multiple steps double-count | An item flows through multiple different steps | Report per step or clearly define the meaning of the aggregation |
| After restart, read/write totals jump unexpectedly | Multiple `JobExecution`/`StepExecution` records exist | Tie counters to execution IDs and cross-check checkpoints |
| Dashboard shows only Micrometer timers | Framework metrics measure duration rather than exporting every counter as successful record counts | Pull counters from metadata or emit separate custom statistics |

When configuring alerts, evaluate **step status, skip counts, filter ratio, written item count, rollback count, and expected input volume** together. A `COMPLETED` job with `writeCount=0` can be a valid outcome when there is no data, or it can indicate a reader/filter misconfiguration; business context is required to distinguish them.

## 15. Documentation and Version Scope

The code examples in this article primarily target **Spring Batch 5.2.x**, Spring Framework 6.x, and Java 17. The item counter getters remain core concepts in Spring Batch 6, though some packages and step/chunk configuration signatures have changed; verify the API of your project's exact version before copying imports.

- [Spring Batch 5.2 Reference — Domain: `StepExecution`](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch 5.2 API — `StepExecution`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecution.html)
- [Spring Batch 5.2 API — `StepContribution`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepContribution.html)
- [Spring Batch 5.2 Reference — Chunk-oriented processing](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 Reference — Skip logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch 5.2 Reference — Intercepting step execution and listeners](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 API — `JobExplorer`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)
- [Spring Batch 5.2 Reference — Monitoring and metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)

When monitoring a Spring Batch step, read `readCount`, `writeCount`, `filterCount`, and the three skip types from **the same `StepExecution`**, together with execution status and IDs. `filter` indicates data excluded under normal rules, whereas `skip` reflects errors accepted under fault tolerance policies; retry, rollback, and restart determine how the numbers must be interpreted. Use `afterStep` for summary logging, `JobExplorer` or SQL metadata for historical counts, and Micrometer for performance observability. Separating these three layers lets dashboards reflect both **processing volume** and **processing quality** without confusing method invocation counts with recorded batch outcomes.
