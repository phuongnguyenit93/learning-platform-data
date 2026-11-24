# Monitoring Commit Count in Spring Batch

## 1. Why Monitor Commit Count?

A Spring Batch Job can process millions of records and run for minutes or hours. When a Job is in the **STARTED** state, operators need to know whether the Steps are actually making progress, waiting on I/O, hitting transaction errors, or stuck. Looking at the Job status alone is not enough to explain processing progress.

**Commit count** is the counter of transaction commits recorded by Spring Batch within the scope of **one StepExecution**. It is accessed via the **StepExecution.getCommitCount()** method. For chunk-oriented Steps, this counter typically increments when chunk processing cycles are successfully committed. It is very useful for observing checkpoints, transaction cadence, and the difference between a Step processing normally and a Step making no progress.

Example dashboard display:

~~~text
Job         : importOrdersJob
Step        : importOrdersStep
Status      : STARTED
Read count  : 12 500
Write count : 12 400
Filter count:    100
Commit count:     25
Rollback   :      0
~~~

The illustrative figures above show that the Step has read and written data, and transactions have been committed. However, **commitCount = 25 does not mean the Step wrote exactly 25 items**, nor does it prove the target system has all 12,400 business-correct records. Commit count is an **operational metric** that must be viewed alongside read/write/skip counts, Step status, elapsed time, and actual results.

After this article, you will be able to:

- Explain **commitCount** and distinguish it from **writeCount** and **rollbackCount**.
- Read commit count through **StepExecution**, **JobExplorer**, and metadata tables.
- Log progress per chunk, emit metrics with **Micrometer**, and design dashboards.
- Recognize limitations when a Step involves retry, rollback, tasklet, restart, or partitioning.
- Design tests and alerts based on actual behavior rather than incorrect formulas.

## 2. Which StepExecution Does Commit Count Belong To?

Spring Batch has three related concepts:

~~~text
JobInstance
  |
  +-- JobExecution #1
  |      |
  |      +-- StepExecution #101
  |              readCount, writeCount, commitCount, rollbackCount...
  |
  +-- JobExecution #2 (restart)
         |
         +-- StepExecution #102
                 readCount, writeCount, commitCount, rollbackCount...
~~~

**JobInstance** is identified by the Job name and identifying JobParameters. **JobExecution** is a single attempt to run that Job. **StepExecution** records a specific execution of a Step.

A Step re-run after failure typically receives a new StepExecution. Therefore:

- The commit count of StepExecution #101 indicates the number of commits recorded in execution #101.
- The commit count of StepExecution #102 indicates the number of commits in the corresponding restart attempt.
- Do not treat the count of the most recent StepExecution as the total count of the entire JobInstance.
- When reconciling the number of business items completed across multiple restarts, inspect the output data and checkpoints instead of merely summing commit counts.

Spring Batch provides the following methods:

~~~java
StepExecution step = ...;

int commits = step.getCommitCount();
int rollbacks = step.getRollbackCount();
long reads = step.getReadCount();
long writes = step.getWriteCount();

BatchStatus status = step.getStatus();
ExitStatus exit = step.getExitStatus();
~~~

Counts to monitor together:

| Property | Meaning | Monitoring role |
| --- | --- | --- |
| **getCommitCount()** | Number of transaction commits recorded by the Step | Observe commit/checkpoint cadence |
| **getRollbackCount()** | Number of rollbacks recorded by the Step | Detect aborted transactions, retries, and errors |
| **getReadCount()** | Number of items read successfully | Measure input reading progress |
| **getWriteCount()** | Number of items the Step counts as written | Measure output volume |
| **getFilterCount()** | Number of items filtered because the processor returned null | Distinguish business filtering from errors |
| **getSkipCount()** | Total number of skipped items/errors | Observe invalid data accepted as skippable |
| **getStatus()** | STARTING, STARTED, COMPLETED, FAILED,... | Determine execution state |
| **getExitStatus()** | Step completion result, which can be customized by the application | Determine the logical outcome of the Step |

Do not build a commit count chart that cannot be traced back to **job name**, **step name**, **JobExecution ID**, and **StepExecution ID**. Two StepExecutions of the same Step can have different counts because they belong to different runs.

## 3. When Does Commit Count Occur?

Consider a Step processing with **chunk size = 4**:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(4, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

A typical chunk processing cycle:

~~~text
       START TRANSACTION
               |
          ItemReader
               |
         ItemProcessor
               |
          ItemWriter
               |
       Update checkpoint,
       status, and metadata
               |
             COMMIT
               |
       Continue to next chunk
~~~

In this model, each chunk that is processed and committed successfully contributes to the Step's transaction progress. Step metadata and **ExecutionContext** are updated according to the framework's checkpoint mechanism.

**Chunk size is not commit count.** Chunk size limits the number of items grouped in one processing cycle; commit count tracks the transaction commits recorded by the Step. To understand the difference, consider ten items:

~~~text
Input: 1 2 3 4 5 6 7 8 9 10
Chunk size: 4

Data chunk 1: 1 2 3 4  -> commit
Data chunk 2: 5 6 7 8  -> commit
Data chunk 3: 9 10     -> commit
Reader end / EOF
~~~

We can describe **three data groups** processed, but you must not assume every Step in every version will have **getCommitCount() == 3**. The framework may execute a final cycle to confirm end of input; different Step types and readers also have different transaction lifecycles.

The formula:

~~~text
ceil(numberOfItems / chunkSize)
~~~

is an estimate of **the number of chunks containing data** in a simple case, **not an invariant contract for commitCount**. When testing or alerting, rely on actual Step behavior rather than deriving rigidly from the item count.

### A Step Can Commit Without Writing Items

For example, the processor filters all items by returning null. **writeCount** may be 0 while the Step still goes through transactions and checkpoints. A Tasklet Step can run update commands, checks, or system operations without using an ItemReader/ItemWriter, while transactions are still committed.

Therefore, **commitCount > 0 does not imply writeCount > 0**.

### A Step Can Read Items Before Committing

If the processor is slow or the writer is waiting on a database lock, the reader may have read many items while the current chunk transaction has not yet committed. If an error occurs and the transaction rolls back, operations belonging to the uncommitted chunk may need to be reprocessed on retry or restart.

Therefore, **an increasing readCount or invoked methods do not mean every item has been committed**.

## 4. Reading Commit Count Alongside Rollback, Retry, and Skip

When a chunk encounters an exception, Spring Batch may roll back the transaction. If retry is configured, the Step may retry the same item/chunk; if skip is configured, it may skip the failing item to continue. These events cause the counters to behave differently.

| Observation | Likely cause | What else to inspect |
| --- | --- | --- |
| Commits rising, rollbacks flat | Transactions committing normally | Read/write throughput, chunk duration |
| Both commits and rollbacks rising | Errors retried or handled successfully after rollback | Exception types, retry policy, skip count |
| Reads rising while commits stay unchanged | Processing a large chunk or slow writer | Logs, database state, wait times |
| Rollbacks rising fast with few commits | Transaction, data, or write-target issues | Constraints, deadlocks, timeouts, failure exceptions |
| Commits stalled while Step stays STARTED | May be waiting on I/O, long chunk processing, or hung | Last update, thread dump, connection pool |
| Step COMPLETED with low commits | Low input volume, heavy filtering, or tasklet Step | Read/write counts and Step type |

A rollback **does not necessarily** lead to **BatchStatus.FAILED**: the error may be retried successfully. Conversely, a **FAILED** Step may have already committed many chunks before the final failure occurred.

Example:

~~~text
Chunk 1: committed successfully
Chunk 2: transient error -> rollback
Chunk 2: retry succeeded -> commit
Chunk 3: committed successfully
Step: COMPLETED
~~~

In this scenario, **rollbackCount > 0** yet the Step still completes. Commit count helps observe completed transactions; rollback count helps spot processing that had to be retried. The number of processor/writer invocations in a retry scenario can exceed the number of items actually written after commit.

### Commit Count Does Not Measure Every Application Commit

A service might open a separate transaction with **REQUIRES_NEW**, a listener might call the database outside the chunk transaction, or a writer might send messages to a system that does not share the transaction manager. **StepExecution.commitCount** is not a system-wide commit count and does not guarantee that all external side effects have been committed.

Especially with APIs, queues, or files outside the transaction, monitor acknowledgment status, idempotency keys, and target data; do not use commitCount to claim that business outcomes are durable across all systems.

## 5. Logging Commit Count at the End of a Step

The simplest way to log the total commits of each StepExecution is by using a **StepExecutionListener**.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CommitCountAuditListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(CommitCountAuditListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
                "batch step completed: job={}, step={}, stepExecutionId={}, " +
                "status={}, commits={}, rollbacks={}, reads={}, writes={}, " +
                "filtered={}, skipped={}",
                step.getJobExecution().getJobInstance().getJobName(),
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getCommitCount(),
                step.getRollbackCount(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount()
        );

        return null; // Keep the existing ExitStatus unchanged.
    }
}
~~~

Register the listener on the Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer,
        CommitCountAuditListener auditListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(auditListener)
            .build();
}
~~~

The listener reads the counts after the Step finishes under its normal lifecycle. Because **afterStep** may not run if the JVM is killed, the container stops abruptly, or the process crashes, this log is **not the sole durable audit source**. JobRepository metadata must be retained so it can be queried after an incident.

Do not modify commit count from a listener:

~~~java
// Do not manually alter counts managed by Spring Batch.
stepExecution.setCommitCount(stepExecution.getCommitCount() + 1);
~~~

Counters are managed by the framework per transaction. Monitoring listeners should only **read and emit information**, avoiding metadata tampering that corrupts metrics.

## 6. Logging Commit Progress While the Step Is Running

For Steps running for hours, logging only in **afterStep** is too late. **ChunkListener.afterChunk** allows observation after a chunk is processed and its transaction finishes successfully according to the chunk lifecycle.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class CommitProgressListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(CommitProgressListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        int commits = step.getCommitCount();

        // Reduce log volume for Jobs with many thousands of chunks.
        if (commits > 0 && commits % 20 == 0) {
            log.info(
                    "batch progress: step={}, executionId={}, " +
                    "commits={}, rollbacks={}, reads={}, writes={}",
                    step.getStepName(),
                    step.getId(),
                    commits,
                    step.getRollbackCount(),
                    step.getReadCount(),
                    step.getWriteCount());
        }
    }
}
~~~

Register it with the Step:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(progressListener)
        .build();
~~~

The value 20 is just an example sampling policy. Short Jobs may log every chunk, while large Jobs need reduced log frequency or metrics.

Spring Batch also provides the **afterChunkError** callback for diagnostics when a chunk fails. Log the exception along with **jobExecutionId**, **stepExecutionId**, rollback count, and relevant transaction details. However, the callback timing and the metadata persistence timing can differ; do not use an immediate log line to conclude that all transaction changes are fully durable.

### Caution with Multiple Concurrent StepExecutions

Do not keep a shared progress counter in a singleton field like **lastCommitCount** if multiple JobExecutions can run concurrently. A StepExecution from Job A can overwrite Job B's snapshot. If progress caching is needed, the key must uniquely identify the StepExecution and have a cache eviction policy; for consolidated monitoring, prefer **JobExplorer/JobRepository** as the source of metadata.

## 7. Querying Commit Count with JobExplorer

In production, dashboards often run in a separate process or lack direct access to the running StepExecution object. **JobExplorer** is the interface for reading persisted Spring Batch metadata.

~~~java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchCommitQueryService {

    private final JobExplorer jobExplorer;

    public BatchCommitQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<StepCommitSnapshot> getCommitCounts(long jobExecutionId) {
        JobExecution jobExecution =
                jobExplorer.getJobExecution(jobExecutionId);

        if (jobExecution == null) {
            throw new IllegalArgumentException(
                    "Unknown jobExecutionId=" + jobExecutionId);
        }

        return jobExecution.getStepExecutions().stream()
                .map(step -> new StepCommitSnapshot(
                        step.getId(),
                        step.getStepName(),
                        step.getStatus().name(),
                        step.getCommitCount(),
                        step.getRollbackCount(),
                        step.getReadCount(),
                        step.getWriteCount()))
                .toList();
    }

    public record StepCommitSnapshot(
            Long stepExecutionId,
            String stepName,
            String status,
            int commits,
            int rollbacks,
            long reads,
            long writes) {
    }
}
~~~

Applications can invoke this service from an internal REST endpoint or a polling task. Keep two caveats in mind:

**First, snapshots are not a real-time event stream.** JobExplorer reads metadata already written to JobRepository. While a Step is processing a chunk and has not yet reached a checkpoint, the commit count in the repository may not have incremented yet.

**Second, you must re-query.** A JobExecution or StepExecution fetched in a previous read does not automatically synchronize subsequent database changes into the in-memory object. If the dashboard refreshes every 30 seconds, query the repository again.

Example:

~~~text
09:00:00  commitCount = 10
09:00:30  commitCount = 10   <- next chunk is still processing
09:01:00  commitCount = 11   <- chunk committed
09:01:30  commitCount = 14
~~~

Periods where commitCount remains flat can be completely normal if chunks are large, the writer calls a slow service, or the database is processing transactions. An alert should be based on the Step's normal duration and other indicators.

## 8. Querying BATCH_STEP_EXECUTION with SQL

Spring Batch stores StepExecution metadata in the **BATCH_STEP_EXECUTION** table inside JobRepository. In the Spring Batch 5.x schema, common columns are:

- **STEP_EXECUTION_ID**, **JOB_EXECUTION_ID**, **STEP_NAME**
- **STATUS**, **EXIT_CODE**, **EXIT_MESSAGE**
- **COMMIT_COUNT**, **ROLLBACK_COUNT**
- **READ_COUNT**, **WRITE_COUNT**, **FILTER_COUNT**
- **READ_SKIP_COUNT**, **PROCESS_SKIP_COUNT**, **WRITE_SKIP_COUNT**
- **LAST_UPDATED**

Illustrative SQL:

~~~sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.FILTER_COUNT,
    se.LAST_UPDATED
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY se.STEP_EXECUTION_ID DESC;
~~~

You can build an admin page for the most recent executions:

| JobExecution | StepExecution | Status | Commit | Rollback | Read | Write |
| ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 2508 | 4712 | COMPLETED | 31 | 0 | 12,000 | 12,000 |
| 2507 | 4711 | FAILED | 8 | 2 | 3,500 | 3,000 |
| 2506 | 4710 | COMPLETED | 16 | 0 | 6,000 | 6,000 |

*Values are purely illustrative to show how to interpret them, not a fixed formula for chunk size.*

Operational guidelines:

- Use a **read-only** database account to query metadata tables if supported.
- Filter by Job name, time window, and row limits when querying large repositories.
- Never edit **COMMIT_COUNT** directly to "fix" a dashboard.
- Do not assume **LAST_UPDATED** is always the exact timestamp of the latest business commit; it is the metadata update timestamp.
- If instances run across multiple nodes, the dashboard must query the correct shared JobRepository.
- If multiple independent schemas/repositories exist, clearly define the scope of each data source.

SQL queries are useful for dashboards or production investigations, while **JobExplorer** is more appropriate when working through the official Spring Batch API.

## 9. Exporting Commit Count to Micrometer

Spring Boot Actuator and Micrometer help collect operational metrics. Depending on the version, Spring Batch may already export metrics related to Steps, chunks, or items; check built-in metric names before adding custom ones.

One option is to create a **Counter** for the commit count recorded by StepExecution when **afterStep** runs. Example:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class CommitMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;

    public CommitMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        String jobName = step.getJobExecution()
                .getJobInstance()
                .getJobName();

        Counter.builder("app.batch.step.commits")
                .description("Commits of completed StepExecutions")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "status", step.getStatus().name())
                .register(registry)
                .increment(step.getCommitCount());

        Counter.builder("app.batch.step.rollbacks")
                .description("Rollbacks of completed StepExecutions")
                .tags(
                        "job", jobName,
                        "step", step.getStepName(),
                        "status", step.getStatus().name())
                .register(registry)
                .increment(step.getRollbackCount());

        return null;
    }
}
~~~

Register the listener on the Step to monitor:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, OrderOutput>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener(commitMetricsListener)
        .build();
~~~

**Understanding the metric is crucial:** The Counter in this example only increments **when the StepExecution finishes and afterStep is invoked**. It represents the total commits reported by callbacks over the process lifetime, **not the live commit count of a currently running Step**.

Limitations:

1. If the process dies before the callback runs, the metric may miss commits already saved in JobRepository.
2. If the process restarts, in-memory Counters typically reset to zero; the observability system must handle counter resets.
3. If a Step restarts, callbacks from each StepExecution may add to the Counter; that is a per-execution transaction statistic, not the unique item count of a JobInstance.
4. If the application has multiple instances, each instance holds its own Counter; to plot the service total, aggregate series across all instances.
5. Avoid updating the same Counter in **afterChunk** and also adding the entire **getCommitCount()** in **afterStep**, as that double-counts.

If a dashboard requires **live per-chunk** visibility, you can emit delta metrics from a ChunkListener or periodically pull JobExplorer snapshots; each metric must have a consistent interpretation.

### Avoid High-Cardinality Labels

Labels such as **jobExecutionId**, **stepExecutionId**, **UUID**, **customerId**, or random file paths create a new time series every time a Job runs. The number of series can grow rapidly and exhaust Prometheus resources.

Prefer:

~~~text
job    = "importOrdersJob"
step   = "importOrdersStep"
status = "COMPLETED"
~~~

Use **JobExecution ID** and **StepExecution ID** in logs or metadata queries to trace specific runs. Metrics are suited for aggregated trends by Job/Step; do not attach every business ID to every metric.

## 10. Visualizing Commit Count on a Dashboard

A useful dashboard does not contain only a single **commitCount** box. Place related metric groups side by side:

| Panel | Metrics | Question to answer |
| --- | --- | --- |
| Status | Job/Step status, start time, duration | Has the Job finished or is it still running? |
| Progress | readCount, writeCount, filterCount | How many items have been ingested and written? |
| Transactions | commitCount, rollbackCount | Are transactions committing? |
| Quality | read/process/write skip counts | How many errors were skipped? |
| Performance | items/sec, commits/min, chunk duration | Is processing speed degrading? |
| Metadata | last update, time since last checkpoint | Is the snapshot fresh or stale? |
| Business | actual row count in target table, checksum, or total amount | Does the output match expected data? |

### Measuring Commits/Second

Suppose the Micrometer metric **app.batch.step.commits** is exported by the Prometheus registry as **app_batch_step_commits_total**. A PromQL expression could be:

~~~promql
sum by (job, step) (
  rate(app_batch_step_commits_total[5m])
)
~~~

The result is the **average commits/second** over a 5-minute window based on the Counter. To display commits/minute, multiply by 60. The actual metric name depends on exporter configuration and naming conventions.

Because the example Counter only updates in **afterStep**, the graph will show spikes when Steps finish, **not the exact moment each chunk commits**. For very long Jobs, use snapshots or metrics emitted during Step execution if live progress visualization is needed.

### Calculating Rate from Snapshots

For a running StepExecution, suppose the dashboard polls data over time:

~~~text
Time         commitCount   readCount   writeCount
09:00:00         10          5000        5000
09:00:30         12          6000        6000
09:01:00         14          7000        7000
09:01:30         14          7000        7000
09:02:00         17          8500        8500
~~~

Rate over an interval:

~~~text
commits/sec = delta(commitCount) / delta(seconds)
reads/sec   = delta(readCount) / delta(seconds)
writes/sec  = delta(writeCount) / delta(seconds)
~~~

At 09:01:30, flat counts may be due to a slow-processing chunk. Do not alert immediately based on a single 30-second sample. Combine normal chunk duration and system state.

**Do not use writeCount / commitCount to deduce exact chunk size.** Filtering, skipping, end-of-input transactions, retries, and different Step types can alter this ratio.

## 11. Alerting Based on Commit Count

### 11.1. Stalled Step

A reference rule:

~~~text
If Step is STARTED
and commitCount has not increased for N minutes
and Step duration exceeds the normally observed threshold
then trigger an investigation alert.
~~~

The value **N** must be grounded in actual runs. A Step with a 15-minute chunk should not be flagged as stuck just because commitCount did not change for 3 minutes.

Supporting signals include:

- The **LAST_UPDATED** timestamp in metadata.
- Thread state and logs of reader/processor/writer.
- Connection pool, database lock waits, and transaction duration.
- Read/write rate and timestamp of the most recently completed chunk.
- JobStatus/StepStatus and SLA thresholds.

### 11.2. Abnormal Rollbacks

**rollbackCount** rising rapidly while commitCount barely moves may indicate constraint violations, deadlocks, timeouts, or repeated retries. You can use a ratio to observe trends:

~~~text
rollbackRatio = rollbackCount / max(1, rollbackCount + commitCount)
~~~

This is only a **reference indicator**, not a standard error rate defined by Spring Batch. Cross-check exceptions and retry policies, since rollbacks are expected in certain fault-tolerance scenarios.

### 11.3. Missed SLA

For example, a closing Job runs at 01:00 and must finish before 02:00. The most valuable alert is **no successful JobExecution for the target business period**, or target data not meeting reconciliation criteria.

Commit count helps explain progress at the moment an SLA is missed, but **many commits does not mean the Job is COMPLETED**. A Step can successfully commit hundreds of chunks and then fail at the end.

## 12. Restarts and Aggregating Counts

Suppose a Job processes a large file, fails after several chunks, and is restarted:

~~~text
JobInstance: importOrdersJob(businessDate=2026-11-15)

JobExecution #1: FAILED
  StepExecution #41
  commitCount   = 5
  writeCount    = 2500
  rollbackCount = 1

JobExecution #2: COMPLETED
  StepExecution #42
  commitCount   = 7
  writeCount    = 3000
  rollbackCount = 0
~~~

These values are illustrative assumptions.

When monitoring:

- Read **StepExecution #41** for progress and errors of the first run.
- Read **StepExecution #42** for progress of the restart run.
- Check target tables/files for the **final business result**.

If you want to report **total transaction commits recorded by the Step across executions**, you can aggregate counts from the relevant StepExecutions after clearly defining the scope and avoiding double-counting data already rolled up by an aggregator.

If you want to report **unique orders imported**, rely on business keys, checkpoints, and actual output. Summing commit counts across restarts does not replace final record counts.

In particular, **different StepExecutions can have different commitCounts even when the Step name is identical**; do not cache progress solely by step name when multiple JobExecutions exist.

## 13. Commit Count in Special Processing Modes

### 13.1. Tasklet Step

A Tasklet can validate files, update statuses, or run SQL without going through an ItemReader/ItemWriter. In that case **readCount/writeCount** may be 0, while **commitCount** still reflects transactions recorded by the Step. Do not apply chunk-size formulas to Tasklets.

### 13.2. Multi-threaded Step

When configuring a Step to use multiple worker threads in a framework-supported manner, chunk completion order and commit timing may no longer be linear with item position. Commit count remains useful for observing transactions, but it cannot be assumed to represent a contiguous offset in the input file.

### 13.3. Partitioned Step

A partitioned Step can have multiple worker StepExecutions and one manager StepExecution:

~~~text
importOrders.manager
  +-- importOrders:partition0
  +-- importOrders:partition1
  +-- importOrders:partition2
~~~

The manager can aggregate counts via **StepExecutionAggregator**. If you sum both the manager and the workers, the dashboard will **double-count**. When per-partition stats are needed, select worker executions; when a summary is needed, read the metadata provided by the aggregator or sum one consistent set.

### 13.4. Writer Calling External Systems

In remote chunking, or when APIs/queues/files sit outside the Step's transaction, commit count does not guarantee that remote side effects occurred exactly once. A request may succeed while the Step crashes before the checkpoint; on restart, the request may be resent.

Also check acknowledgments from the target, outbox patterns, transaction boundaries, and idempotency keys. Do not rely on commit count alone to claim exactly-once guarantees.

## 14. Testing Commit Count

### 14.1. Integration Test for a Successful Step

Example using **Spring Boot 3.x, Spring Batch 5.x, JUnit 5, AssertJ, and spring-batch-test**. Assume the context already contains a Job with **importOrdersStep**, fixture data has exactly seven items, and the writer writes all seven items.

~~~java
import java.util.UUID;

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

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersCommitMonitoringTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void shouldRecordCommitProgress() throws Exception {
        // Reader is prepared to return exactly 7 items.
        JobParameters parameters = new JobParametersBuilder()
                .addString("caseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchStep("importOrdersStep", parameters);

        StepExecution step = execution.getStepExecutions().stream()
                .filter(s -> "importOrdersStep".equals(s.getStepName()))
                .findFirst()
                .orElseThrow();

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(step.getReadCount()).isEqualTo(7);
        assertThat(step.getWriteCount()).isEqualTo(7);
        assertThat(step.getSkipCount()).isZero();
        assertThat(step.getRollbackCount()).isZero();

        // Do not deduce the exact commit count solely from chunk size.
        assertThat(step.getCommitCount()).isPositive();
    }
}
~~~

Test data should be isolated using caseId or a dedicated database. If the context contains multiple Jobs, configure **JobLauncherTestUtils** for the target Job. If the launcher is asynchronous, wait for completion before checking counts.

Do not mechanically assert **commitCount == ceil(7 / chunkSize)** without verifying Step semantics under the actual configuration. Only assert an exact commit count when transaction boundaries are the primary subject of the test and the test controls the scenario, framework version, and inputs.

### 14.2. Unit Testing Monitoring Logic

**MetaDataInstanceFactory** in spring-batch-test helps create mock StepExecutions for services or listeners that need to read counts:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

StepExecution step = MetaDataInstanceFactory.createStepExecution();
step.setCommitCount(6);
step.setRollbackCount(1);
step.setReadCount(120);
step.setWriteCount(118);

// Pass step into the monitor service or listener under test.
// Assert the DTO, log event, or metric produced by that logic.
~~~

Manually calling **setCommitCount(6)** and then asserting the getter **does not prove Spring Batch committed six transactions**. It is only a fixture for testing how your application displays or processes metadata. To verify actual counts produced by the framework, run the Step/Job in an integration test.

### 14.3. Testing Rollback/Retry

For a **faultTolerant()** Step, you can inject a deterministic error in the processor or writer to verify monitoring callbacks:

- The first processing attempt raises an error causing the transaction to roll back.
- Retry or skip occurs as configured.
- The Step finishes with the expected BatchStatus.
- Logs/metrics contain the appropriate commit count and rollback count.
- Output data is correct after errors and retries.

To verify JDBC rollback behavior, the test needs a real writer and an appropriate transaction manager. A mock that does not participate in transactions will not represent all database behaviors.

## 15. Common Misinterpretations

### Commit Count Does Not Increase While Read Count Changes

The Step may be in the middle of an uncommitted chunk. Check transaction state and processing logs before alerting. When a chunk reads and processes a large number of items, the interval without commits may exceed the polling interval.

### Commit Count Increases Without New Rows in Target Table

All items may have been filtered, the writer may perform updates instead of inserts, or checkpoint transactions occurred without writing items. If the writer sends data to an external system, check acknowledgments from that system.

### Commit Count Is Smaller Than Expected Chunk Count

Check how the Step terminated, rollbacks, retries, EOF, skips, tasklet behavior, and input data. Commit count is the actual metadata of StepExecution; do not force it to match a generic formula.

### Dashboard Loses Metrics When the Application Restarts

In-memory Micrometer Counters can reset with the process. Query **JobRepository** for durable snapshots and use monitoring tools that handle counter resets; do not rely solely on JVM-resident Counters.

### Restarts Cause Unexpected Spikes on Charts

Each restart creates a new StepExecution with its own commit count. Distinguish total commits per execution from unique output per business period. Also avoid double-counting manager/workers when partitioning is used.

### Logs and SQL Display Different Counts

This can result from different snapshot timestamps, metadata not yet updated at a checkpoint, or viewing the wrong execution. Include **jobExecutionId** and **stepExecutionId** in logs to cross-reference accurately with metadata tables.

### Metrics Have Too Many Series

Do not attach UUID, customer ID, file path, or jobExecutionId to aggregated metric labels. Use them in logs/tracing or metadata queries; keep metrics focused on stable labels such as job, step, and status.

## 16. Production Workflow for Monitoring Commit Count

An operational rollout process may include these steps:

1. **Identify critical Jobs** and business SLA thresholds.
2. **Read authoritative metadata** from JobRepository: status, commitCount, rollbackCount, read/write/filter/skip counts, and update timestamps.
3. **Add progress logging** in ChunkListener for long-running Jobs, and summary logging in StepExecutionListener.
4. **Export aggregated metrics** with Micrometer if a multi-instance dashboard is needed; clearly define whether metrics update per chunk or after Step completion.
5. **Configure context-aware alerts**: commits stalled too long, high rollbacks, Step exceeding SLA, or no successful run for the processing period.
6. **Reconcile actual output** using record counts, checksums, or business rules.
7. **Test fault scenarios**: slow writer, retry, rollback, restart, partitioning, and crash.
8. **Maintain history and retention** in JobRepository so failures can be investigated without overloading the monitoring system.

Example monitoring screen:

~~~text
Job         : dailyImportJob
BusinessDate: 2026-11-15
Execution   : 2608
Status      : STARTED

Step        : importOrdersStep
StepExec ID : 4712

READ        WRITE       FILTER     SKIP
12 500      12 400      100        0

COMMIT      ROLLBACK    LAST UPDATED
25          0           01:42:18 UTC

Business result: waiting for Step completion to reconcile.
~~~

**An increasing commit count** is a useful signal that the Step has recorded successful transactions. However, **batch correctness** also depends on the final status, rollback and skip handling, checkpoints/restarts, and the actual business data written. When monitored alongside all those signals, commit count becomes a practical gauge for spotting stalled Steps early and explaining processing progress.

