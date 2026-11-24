# Partition name and step execution

In Spring Batch, partitioning splits a Step's data into multiple independent subsets so they can be processed separately, often in parallel. Each subset is called a **partition**. When configuring partitioning, `Partitioner` returns a map of partition names and an `ExecutionContext` containing the input data for that partition.

Spring Batch uses this information to create a separate `StepExecution` for each partition. Therefore, two concepts must be distinguished: **partition name** is the logical name of a data subset; **StepExecution** is the runtime record representing a Step execution on that data subset. The partition name identifies the piece of work within a split, while StepExecution stores the status, timing, counters, result, and context of that execution.

## 1. How does partitioning divide a Step?

Suppose a Job needs to process 1,000,000 customers. If run sequentially by one worker, a single Step reads and writes all the data. With partitioning, the application can divide the data range into multiple non-overlapping partitions:

```text
customerImportJob
        |
        v
  managerStep (partitioned step)
        |
        +---- partition0: customerId 1 - 250000
        |
        +---- partition1: customerId 250001 - 500000
        |
        +---- partition2: customerId 500001 - 750000
        |
        +---- partition3: customerId 750001 - 1000000
                    |
                    v
          workerStep runs for each partition
```

The parent/manager Step coordinates data splitting and launches the worker executions. The worker Step is the actual processing definition, such as reading customers in an ID range, normalizing data, and writing the results.

Each partition has its own input, allowing workers to process independently. Partitions are often executed concurrently when configured with an appropriate handler and executor, though partitioning can also run sequentially if parallel processing is not enabled.

## 2. What is a partition name?

A partition name is the String key in the map returned by `Partitioner.partition(gridSize)`. This key names a piece of work in the current split.

For example:

```java
@Component
public class CustomerPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        ExecutionContext first = new ExecutionContext();
        first.putLong("minId", 1L);
        first.putLong("maxId", 250_000L);
        partitions.put("partition0", first);

        ExecutionContext second = new ExecutionContext();
        second.putLong("minId", 250_001L);
        second.putLong("maxId", 500_000L);
        partitions.put("partition1", second);

        return partitions;
    }
}
```

In this example, `partition0` and `partition1` are partition names. They describe two data subsets with distinct ID ranges. The accompanying `ExecutionContext` contains `minId` and `maxId` so the worker knows which records to process.

A partition name:

- Is a logical identifier provided by the `Partitioner`.
- Is the key of an entry in the resulting map.
- Must be unique within a split so each partition has a distinct name.
- Should be stable and reproducible when restarting the same JobInstance.
- Is not a thread name, worker machine name, Job name, or StepExecution database ID.

Names like `partition0`, `partition1`, `northRegion`, `southRegion`, or `customerRangeA` can all be used if they clearly reflect how the data is split.

## 3. What is a StepExecution in partitioning?

`StepExecution` is the metadata object representing a specific execution of a Step within a `JobExecution`. It stores information such as:

- The name of the executed Step.
- The ID of the StepExecution and its associated JobExecution.
- `BatchStatus` and `ExitStatus`.
- Start, end, and last updated timestamps.
- Read, write, filter, and skip item counts.
- Commit and rollback counts.
- Exceptions thrown during execution.
- `ExecutionContext` used to store state and checkpoints.

In partitioning, Spring Batch creates a worker `StepExecution` for each split partition. Each execution record has its own status and counters. This allows operators to know which partition has completed, which is running, and which has failed.

For example, for a worker Step named `importCustomersStep`, partition executions may be named following a convention like:

```text
importCustomersStep:partition0
importCustomersStep:partition1
importCustomersStep:partition2
importCustomersStep:partition3
```

The part after the `:` reflects the partition name. This is a common StepExecution naming convention in the default splitter; do not rely on parsing this name string to extract business data. If a worker needs the partition name, put it explicitly into the `ExecutionContext`.

## 4. Distinguishing partition name and StepExecution

The two concepts are related but not synonymous:

| Criterion | Partition name | StepExecution |
|---|---|---|
| Nature | Logical name of a data subset | Record/object of a single Step execution |
| Creation source | Key in the map returned by `Partitioner` | Created by Spring Batch when splitting JobExecution into worker executions |
| Role | Identifies the partition in the split | Tracks lifecycle and execution results of the partition |
| Data held | Just the name; input data is typically in the accompanying ExecutionContext | Status, timestamps, counters, ExitStatus, exceptions, and ExecutionContext |
| Lifecycle | Recreated when the partitioner runs for a JobInstance | Persisted in JobRepository for each execution |
| Uniqueness scope | Needs to be unique within the split map | Has its own ID in JobRepository; name may repeat in another JobExecution |

For example, `partition2` only indicates that this is the third partition by naming convention. Its `StepExecution` reveals whether that partition is `COMPLETED`, how many items it read, how many it wrote, and whether any errors occurred.

The same partition name can appear across different JobExecutions. For instance, `partition0` of the November 15 JobInstance and `partition0` of the November 16 JobInstance are two separate executions with distinct StepExecution IDs and input data.

## 5. Partitioner returns names and ExecutionContexts

The basic interface:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Each entry in the map represents one partition:

- Key is the partition name.
- Value is the `ExecutionContext` containing parameters or data range for that partition.

Example with contiguous ID ranges:

```java
@Component
public class CustomerRangePartitioner implements Partitioner {

    private final CustomerRangeService rangeService;

    public CustomerRangePartitioner(CustomerRangeService rangeService) {
        this.rangeService = rangeService;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = rangeService.findMinimumId();
        long maxId = rangeService.findMaximumId();

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        if (maxId < minId) {
            return result;
        }

        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int index = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            context.putString("partitionName", "partition" + index);

            result.put("partition" + index, context);

            start = end + 1;
            index++;
        }

        return result;
    }
}
```

This example illustrates splitting an ID range into up to roughly `gridSize` ranges of nearly equal size. In real applications, carefully handle empty datasets, large boundary values with overflow risk, and splitting when IDs have many gaps. With unevenly distributed data, splitting by ID count does not necessarily create a balanced workload; querying distribution or splitting by actual record count may be necessary.

`gridSize` is the hint/grid size passed to the partitioner and used in handler configuration. The actual number of partitions created is the number of entries returned in the map. The executor and partition handler then determine how many partitions can run concurrently.

## 6. How does the worker Step receive partition data?

When Spring Batch creates a worker StepExecution for each entry, the `ExecutionContext` data returned by the partitioner is used as the initial context of the worker execution. The worker Step can read these keys using `@StepScope` and SpEL.

Example of a worker reader that reads only customers in its assigned ID range:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .queryProvider(customerQueryProvider(dataSource))
            .parameterValues(Map.of(
                    "minId", minId,
                    "maxId", maxId))
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .build();
}
```

The query provider must filter data by `minId` and `maxId` while having a stable sort key, usually including a unique key. Corresponding SQL example:

```sql
SELECT id, full_name, email
FROM customers
WHERE id BETWEEN :minId AND :maxId
ORDER BY id ASC;
```

`@StepScope` is important because each partition has a different StepExecutionContext. If the reader were a singleton initialized once at application startup, it could not hold separate `minId` and `maxId` values for each partition.

If you need to access the partition name in the worker, you can read the `partitionName` key written into the context:

```java
@Bean
@StepScope
Tasklet processPartitionTasklet(
        @Value("#{stepExecutionContext['partitionName']}") String partitionName) {

    return (contribution, chunkContext) -> {
        log.info("Processing {}", partitionName);
        return RepeatStatus.FINISHED;
    };
}
```

## 7. Manager Step and worker Steps have separate StepExecutions

In a partitioning setup, distinguish between the coordinating Step (manager) and the work-performing Step (worker):

- **Manager Step:** the Step in the Job flow that coordinates data splitting and hands partitions to the handler.
- **Worker Step:** the Step definition run for each partition. Each partition has its own worker StepExecution.

The manager Step also has its own StepExecution. Alongside it, JobRepository stores StepExecutions for each partition. Thus, when monitoring a partitioned Step, you will see one manager execution and multiple worker executions.

High-level diagram:

```text
JobExecution
    |
    +---- managerStep StepExecution
              |
              +---- workerStep:partition0 StepExecution
              |
              +---- workerStep:partition1 StepExecution
              |
              +---- workerStep:partition2 StepExecution
              |
              +---- workerStep:partition3 StepExecution
```

The manager Step reflects the overall coordination result. Worker StepExecutions reflect the individual results of each partition. If one partition fails, that partition's error details and counters can still be inspected separately in metadata.

## 8. Configuring a partitioned Step

For example in Spring Batch 5, the manager Step uses `JobRepository`, `Partitioner`, the worker Step, and a `TaskExecutor`:

```java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerRangePartitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner("customerWorkerStep", customerRangePartitioner)
            .step(customerWorkerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}
```

The worker Step is a regular Step, such as chunk-oriented:

```java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

In this example, `partitioner("customerWorkerStep", ...)` specifies the base Step name that partitions will execute. Spring Batch creates separate StepExecutions based on the worker Step name and partition name. `gridSize(4)` requests dividing the work into a grid of about four parts; the actual count also depends on the map returned by the partitioner.

`TaskExecutor` allows the handler to execute partitions using multiple threads within the same JVM. If parallelism is not needed, an appropriate handler can be used to run sequentially. With remote partitioning, partitions are sent to worker processes via middleware; the concepts of partition name and StepExecution still play a similar role, though proper communication infrastructure and JobRepository setup are required.

## 9. How do partition names affect restart?

Spring Batch stores partition StepExecutions in the `JobRepository`. When a JobInstance is restarted, the framework can use stored metadata to determine which partitions have completed and which need to execute again.

Typically:

- Partitions that are `COMPLETED` are skipped on restart, unless the Step is configured to allow rerunning after completion.
- `FAILED` or `STOPPED` partitions can be re-executed if the Job and Step allow restart.
- Partitions with an active execution must be handled according to their actual state; do not launch a duplicate execution for one that is already running.

To match old executions against recreated partitions, partition names must be stable for the same JobInstance. If on the first run the map had `partition0` representing IDs 1–250,000, but on restart `partition0` represents IDs 1–300,000, the old metadata no longer describes the same data range.

Therefore, a partitioner should be deterministic:

1. The same identifying JobParameters must produce the same set of partition names.
2. Each partition name must represent the same range or data unit across restarts.
3. Ranges must be non-overlapping and cover the target dataset accurately.
4. Do not generate random names or attach fresh timestamps each time the partitioner is called.
5. If source data can change, pin the snapshot, batch ID, cutoff, or data boundaries in persistent JobParameters/metadata.

Stable names are necessary but not sufficient. The accompanying `ExecutionContext` and data range must also remain stable. If input data is replaced or partition boundaries shift, restarts can read duplicates or miss records.

## 10. Restart example with multiple partitions

Suppose a Job creates four partitions:

| Partition | ID Range | First Run Status |
|---|---|---|
| `partition0` | 1–250,000 | `COMPLETED` |
| `partition1` | 250,001–500,000 | `COMPLETED` |
| `partition2` | 500,001–750,000 | `FAILED` |
| `partition3` | 750,001–1,000,000 | `COMPLETED` |

When restarting the same JobInstance and the partitioner recreates the exact same names and ranges, Spring Batch can skip completed partitions and re-execute the failed partition using its metadata/checkpoint.

```text
First run:
partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED

Restart:
partition0 -> skipped
partition1 -> skipped
partition2 -> rerun/resume from checkpoint
partition3 -> skipped
```

If each partition's worker Step is chunk-oriented and its reader supports `ItemStream`, the individual checkpoint in StepExecutionContext can help the failed partition resume from the most recently committed chunk. Completed partitions do not need to be reprocessed in a normal restart flow.

If partition names or ranges are changed between runs, the framework may treat them as different StepExecutions and restart behavior will deviate from expectations. Do not rename a partition to bypass a failure state; fix the root cause and restart the proper instance.

## 11. How do partition name and ExecutionContext relate?

The partition name and ExecutionContext are returned together but have different duties:

- The partition name identifies the unit of work in the map.
- ExecutionContext holds the data needed for the worker to execute that unit of work.

For example:

```text
Key: partition-east
Context:
  regionCode = EAST
  minCustomerId = 1
  maxCustomerId = 500000

Key: partition-west
Context:
  regionCode = WEST
  minCustomerId = 500001
  maxCustomerId = 1000000
```

The worker can use both the partition name and context values. Do not put large datasets into the context; only pass ranges, reference keys, resource names, or small information required for the worker to query data.

Context keys should have clear names and data types that the JobRepository serializer can persist. Avoid storing connections, streams, service beans, or runtime objects that cannot be reliably serialized.

## 12. How to name partitions?

A good naming convention should be easy to understand, stable, and independent of execution time.

Examples of usable names:

| Splitting method | Sample partition names |
|---|---|
| By sequence number | `partition0`, `partition1`, `partition2` |
| By region | `region-north`, `region-south` |
| By tenant | `tenant-100`, `tenant-200` |
| By key range | `customer-000001-250000` |
| By fixed date/batch | `batch-20261115-part0` |

Things to avoid:

- Random UUIDs regenerated each time the partitioner runs.
- Current timestamps that change names across restarts.
- Overly long names containing entire payloads or lists of IDs.
- Names that cannot be mapped back to the data range being processed.
- Using thread names or hostnames, as a worker may execute on a different thread/node after restart.

Partition names do not need to be globally unique across all Jobs in the system. They need to distinguish partitions within a Step split and remain stable within the scope of a restartable JobInstance.

## 13. Parallel partitioning and number of StepExecutions

If the partitioner returns four entries, Spring Batch creates four corresponding worker StepExecutions. However, that does not mean all four partitions are guaranteed to run simultaneously. Actual parallelism depends on:

- `TaskExecutor` and max thread count.
- `gridSize` and `PartitionHandler` configuration.
- Actual number of partitions in the map.
- Connection pool and database resources.
- CPU, memory, and external system load.
- Worker concurrency limits in remote partitioning.

For example, if the partitioner creates 8 partitions but the executor only has 4 threads, partitions can be processed in waves with at most 4 concurrent workers. If there are only 2 partitions, configuring an 8-thread executor will not create 8 partition workers.

Each partition has its own StepExecution, but workers may share databases and services. Ensure data ranges do not overlap if workers write independently. If multiple partitions update the same aggregate record, lock contention or deadlocks can occur.

## 14. Manager Step and worker Steps can have different statuses

The manager Step tracks splitting and partition coordination; worker StepExecutions track the outcome of each partition. If a worker fails, the manager typically receives an overall unsuccessful outcome and the Step/Job may transition to `FAILED` depending on the handler and flow.

When investigating, do not only check the manager status. Query each worker StepExecution to find out which partition failed, which exception occurred, and how many items were read/written.

Example monitoring table:

| StepExecution | Partition | BatchStatus | Read count | Write count |
|---|---|---|---:|---:|
| `customerWorkerStep:partition0` | partition0 | `COMPLETED` | 250,000 | 250,000 |
| `customerWorkerStep:partition1` | partition1 | `COMPLETED` | 250,000 | 249,990 |
| `customerWorkerStep:partition2` | partition2 | `FAILED` | 120,000 | 119,800 |
| `customerWorkerStep:partition3` | partition3 | `COMPLETED` | 250,000 | 250,000 |

Numbers are illustrative only. When a processor filters items or the Step skips records, read count and write count can differ. Inspect filter counts, skip counts, exceptions, and business outcomes as well.

## 15. Common mistakes

**Confusing partition name with StepExecution ID:** partition name is a logical key created by the partitioner; StepExecution has its own ID and metadata managed by JobRepository.

**Creating unstable partition names:** random names or names that change across restarts make it difficult for the framework to match old executions to new partitions.

**Using the same name for multiple data subsets in one split:** a map cannot represent two entries with the same key; each partition needs a distinct name.

**Not passing the data range in ExecutionContext:** the worker does not know which subset to read or has to compute ranges inconsistently.

**Using ExecutionContext to store entire partition data:** context should hold small metadata and references; large data should reside in databases or files.

**Assuming gridSize equals thread count:** gridSize relates to the target number of partitions; the executor/handler determines how many workers can run concurrently.

**Assuming a partition always runs on the same thread or node:** a partition may be handed to a different worker when using an executor or remote partitioning.

**Changing partition boundaries between restarts:** can cause duplicate processing or missed items because old checkpoints no longer match the new range.

**Looking only at the manager StepExecution:** individual worker StepExecutions must be checked to identify which specific partition failed.

**Splitting overlapping data:** two workers may update the same record, causing duplicate writes, lock contention, or deadlocks.

## 16. Workflow for designing partition names and executions

When building a partitioned Step, you can follow these steps:

1. Identify an independently processable unit of data, such as an ID range, region, tenant, or file.
2. Choose a stable partition naming rule that is unique within the split and easy to trace.
3. Create an `ExecutionContext` for each partition with the required range keys or references.
4. Ensure partitions do not overlap and cover the required dataset accurately.
5. Configure the worker Step with `@StepScope` to read the individual context of each StepExecution.
6. Configure the handler/executor according to actual concurrency and resource limits.
7. Ensure JobRepository persists metadata and readers have checkpoints if restart is required.
8. Test the case where one partition fails, restart the same JobInstance, and verify completed partitions are not reprocessed unexpectedly.
9. Monitor each worker StepExecution rather than looking only at the manager status.

## Conclusion

A partition name is the logical name returned by `Partitioner` to identify each unit of work; `StepExecution` is the runtime record Spring Batch creates for each partition's worker Step, storing status, counters, exceptions, and ExecutionContext. The manager Step coordinates worker StepExecutions, while each worker receives its data range through its own context. Keep partition names unique and stable for the same JobInstance, maintain consistent partition ranges across restarts, split data without overlaps, and use StepExecution metadata to track each subset. This design makes partitioning observable, load-balanced, and safe to recover when a partition fails.
