# Partitioning splits data into multiple step executions

Partitioning in Spring Batch splits input data into multiple independent subsets and then runs the same worker step definition for each subset. Each subset creates its own `StepExecution` with its own `ExecutionContext`, allowing the subsets to be processed concurrently or distributed across multiple processes.

Instead of a single step reading all the data, partitioning creates a coordinating step (manager/master) and multiple executions of a worker step. The manager determines the partitions; each worker receives its assigned data range, processes it, and persists its own state in the `JobRepository`.

## 1. What is partitioning?

Partitioning is a way to split a workload into non-overlapping subsets so that multiple worker step executions can process them independently. For example, a job importing one million orders can split by ID range into eight partitions. Each worker only reads and writes data belonging to its assigned range.

```text
Job: importOrders
       |
       v
Manager step
       |
       +-- creates partition0: orderId 1..125000
       +-- creates partition1: orderId 125001..250000
       +-- creates partition2: orderId 250001..375000
       +-- ...
       +-- creates partition7: orderId 875001..1000000
       |
       v
Worker StepExecutions
       |
       +-- worker partition0
       +-- worker partition1
       +-- worker partition2
       +-- ...
       +-- worker partition7
```

Each partition is a unit of data described by a name and an `ExecutionContext`. The worker step uses that context to know which range to process. Workers can run in parallel if the `PartitionHandler` and executor configuration allow it.

## 2. Manager step and worker step

A partitioning configuration typically has two roles:

| Component | Responsibility |
|---|---|
| Manager/master step | Calls the `Partitioner`, creates the partitions, and coordinates worker execution |
| Worker step | Processes the data of a single partition using a tasklet or chunk-oriented processing |
| `PartitionHandler` | Launches worker executions, either locally or via a distributed mechanism |
| `JobRepository` | Stores metadata for the manager, each worker `StepExecution`, and the corresponding context |

The worker step is a step definition reused for each partition. Spring Batch creates a separate `StepExecution` for each partition, so each worker has an independent status, counters, and `ExecutionContext`.

The manager does not need to process individual items itself. It is responsible for splitting the work and tracking worker results. The workers execute the logic to read, process, and write data.

## 3. Partitioner creates the data subsets

`Partitioner` is the interface that describes how data is split. The `partition(int gridSize)` method returns a map in which the key is the partition name and the value is the `ExecutionContext` containing the data needed by the worker.

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

For example, a job processes orders with contiguous IDs from 1 to 1,000,000. The partitioner divides the ID range into a number of subsets based on `gridSize`:

```java
public class OrderRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public OrderRangePartitioner(long minId, long maxId) {
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        if (maxId < minId) {
            return result;
        }

        long total = maxId - minId + 1;
        int partitionCount = (int) Math.min((long) gridSize, total);
        long baseSize = total / partitionCount;
        long remainder = total % partitionCount;
        long nextStart = minId;

        for (int i = 0; i < partitionCount; i++) {
            long size = baseSize + (i < remainder ? 1 : 0);
            long end = nextStart + size - 1;

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", nextStart);
            context.putLong("maxId", end);

            result.put("partition" + i, context);
            nextStart = end + 1;
        }

        return result;
    }
}
```

With a range from 1 to 1,000 and `gridSize = 4`, the result is four nearly equal ranges. If the total number of IDs is not evenly divisible by the number of partitions, the remainder is distributed by adding one extra ID to the first partitions.

| Partition | minId | maxId |
|---|---:|---:|
| `partition0` | 1 | 250 |
| `partition1` | 251 | 500 |
| `partition2` | 501 | 750 |
| `partition3` | 751 | 1000 |

The example assumes a valid ID domain with no overflow when calculating the range length. With real data, validate `minId`, `maxId`, the record count, and the empty-source case before creating partitions.

## 4. Ensuring partitions are complete and non-overlapping

The quality of partitioning depends directly on the splitting algorithm. Partitions should satisfy three properties:

1. **Non-overlapping:** an item must not belong to two partitions at the same time unless duplicate processing is intentional.
2. **Complete coverage:** every item within the target range must belong to some partition.
3. **Relatively balanced:** each partition should have a comparable workload to avoid one worker dragging out the entire job.

With a contiguous numeric range, you can split by min/max ID. However, IDs in a database often have gaps; splitting a numeric range evenly does not necessarily mean splitting the record count evenly. One partition may contain far less data than another if the ID distribution is skewed.

Other splitting approaches may be more suitable depending on the data:

- Splitting by primary key or business key ranges.
- Splitting by date/month or time intervals.
- Splitting by tenant, region, or customer group.
- Splitting by key hash/modulo if the groups can be queried independently.
- Splitting by a pre-prepared list of shards or work items.

The worker's query condition must match the partitioner's rules exactly. If the partitioner creates inclusive ranges `[minId, maxId]`, the reader must use a corresponding condition such as `id >= ? AND id <= ?`. Avoid using inclusive bounds on both adjacent partitions, as that will process records twice.

## 5. Passing partition data via ExecutionContext

`Partitioner` does not pass Java arguments directly into a worker method. It places the necessary data into each partition's `ExecutionContext`. Spring Batch stores the context alongside metadata and provides it to the corresponding worker `StepExecution`.

For example, each context can contain:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 250L);
context.putString("region", "north");
```

The worker can read values from the step execution context using `@StepScope` and SpEL. Stored values should be small, serializable, and sufficient to identify the processing range. Do not store connections, open readers, service beans, or runtime resources in the context.

## 6. Configuring the worker step in Spring Batch 5

The worker step can be a chunk-oriented step. The reader is created per `StepExecution` so that each partition has its own query range.

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionedOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
        .name("partitionedOrderReader")
        .dataSource(dataSource)
        .sql("""
            SELECT ORDER_ID, CUSTOMER_ID, TOTAL
            FROM ORDERS
            WHERE ORDER_ID >= ? AND ORDER_ID <= ?
            ORDER BY ORDER_ID
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
```

`@StepScope` causes the reader to be created per step execution. As a result, each partition receives its own `minId` and `maxId` instead of sharing a reader with mutable state across workers. The reader can save its read state to support restart; the reader name must be stable, and each worker's context is managed separately.

Declaring the worker step:

```java
@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionedOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorker", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(partitionedOrderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
}
```

Workers use the same step definition for all partitions. The difference in data comes from the step execution context, without needing to create a separate step bean for each range.

## 7. Configuring the manager step and running in parallel

The manager step connects the partitioner to the worker step. For local partitioning, a `TaskExecutor` can be used to run workers on multiple threads within the same application.

```java
@Bean
Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManager", jobRepository)
        .partitioner(orderWorkerStep.getName(), orderRangePartitioner)
        .step(orderWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
```

The job can start with the manager step:

```java
@Bean
Job partitionedOrderImportJob(
        JobRepository jobRepository,
        Step orderManagerStep) {

    return new JobBuilder("partitionedOrderImportJob", jobRepository)
        .start(orderManagerStep)
        .build();
}
```

In the configuration above, `gridSize(4)` requests creating approximately four partitions when the data is large enough. The executor determines how many workers actually run concurrently. If there are eight partitions but the thread pool only has four threads, the workers will execute across multiple batches.

A dedicated executor can be configured with a thread limit:

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setThreadNamePrefix("order-partition-");
    executor.initialize();
    return executor;
}
```

Do not set the thread count higher than the capacity of the database or target system. Increasing the number of partitions does not automatically make a job faster if workers contend on the same table, connection pool, or external service.

## 8. Grid size does not mean thread count

`gridSize` is a hint to the partitioner for the number of subsets to create. The number of concurrently running workers depends on the `PartitionHandler`, executor, system resources, and deployment configuration.

For example:

| Grid size | Thread pool size | Typical behavior |
|---:|---:|---|
| 4 | 4 | Up to four workers run concurrently |
| 8 | 4 | Creates eight partitions, executed in waves |
| 4 | 8 | Only up to four partitions exist to run; extra threads do not create more work |
| 8 | 8 | Up to eight workers can run concurrently if resources allow |

Actual values also depend on the specific `PartitionHandler` and executor. Distinguish between the number of partitions created and the number of threads that can process simultaneously.

## 9. Partitioning and StepExecution

Each partition creates a separate worker `StepExecution`. In metadata, these executions have names formed from the worker step name and the partition name, for example `orderWorker:partition0`.

```text
JobExecution #42
  +-- orderManager
        +-- orderWorker:partition0  -> COMPLETED
        +-- orderWorker:partition1  -> COMPLETED
        +-- orderWorker:partition2  -> FAILED
        +-- orderWorker:partition3  -> COMPLETED
```

Each worker execution has its own read/write/skip counters, status, and `ExecutionContext`. This makes it possible to track which partition completed, which partition failed, and each worker's checkpoint.

The manager step aggregates the worker results. If a worker fails, the manager/job may terminate as failed depending on the partition handler and flow behavior. Other workers may have already completed and committed their data; partitioning does not create a single transaction spanning all partitions.

## 10. Restarting a partitioned step

When a job is restarted, Spring Batch uses metadata in the `JobRepository` to identify previous worker executions. Completed partitions usually do not need to run again; failed or incomplete partitions can be relaunched according to restart rules.

For example:

```text
Execution #1
  partition0 -> COMPLETED
  partition1 -> COMPLETED
  partition2 -> FAILED
  partition3 -> COMPLETED

Restart same JobInstance
  partition0 -> skipped because already completed
  partition1 -> skipped because already completed
  partition2 -> rerun from the worker's checkpoint
  partition3 -> skipped because already completed
```

To restart properly, the partitioner must recreate partitions with names and ranges corresponding to the previous run. Do not generate random partition names or arbitrarily change ranges across restarts of the same JobInstance.

For example, if on the first run `partition2` processed IDs 501–750, but on a restart of the same JobInstance that name is assigned IDs 600–850, old metadata may be applied to the wrong data range. Keep the splitting rules stable with respect to JobParameters and the run's data snapshot.

## 11. Data changing during partitioning

Splitting data by min/max ID or by time needs to account for new data being inserted or modified while the job is running.

Suppose the partitioner queries `MAX(ORDER_ID)` as 1,000 and creates ranges up to ID 1,000. While workers are running, the online application inserts ID 1,001. The new record does not belong to any partition of the current job. This may be the intended behavior if the job processes a snapshot as of start time; if new data also needs to be processed, a watermark or a subsequent run is required.

Ways to control this:

- Capture the `maxId` or watermark at start time and use it consistently across all partitions.
- Use snapshot isolation or an appropriate snapshot mechanism if consistent point-in-time data is required.
- Pass the watermark in JobParameters or JobExecutionContext so restarts use the same boundary.
- Ensure data within the range is not deleted or modified in a way that invalidates processing semantics while the job runs.
- Schedule a follow-up run to process data arriving after the watermark.

Partitioning only splits the execution scope; it does not automatically create a consistent snapshot of the source data.

## 12. Load balancing and choosing a splitting strategy

Splitting into an equal number of IDs does not necessarily split processing time evenly. One range might contain larger records, more relations, or more external operations than others.

When the workload is skewed, fast workers finish early and wait for the slowest partition. Total job duration is dominated by the heaviest partition.

Balancing strategies:

1. Split by estimated record count instead of ID width alone.
2. Use histograms or distribution statistics to choose range boundaries.
3. Split by business groups with comparable processing cost.
4. Increase the number of partitions relative to the thread count so the executor has smaller work units, if the worker creation overhead is acceptable.
5. Monitor the duration of each `StepExecution` and tune the algorithm for future runs.

Do not create too many tiny partitions if each worker incurs significant overhead in metadata, connections, and resource initialization.

## 13. Local partitioning and remote partitioning

Partitioning can run workers on the same JVM or distribute workers across other processes/nodes.

| Model | How it works | When appropriate |
|---|---|---|
| Local partitioning | Manager uses a `TaskExecutor` to run the worker step on threads within the same application | When you want to utilize multiple cores on a single node and share application resources |
| Remote partitioning | Manager sends worker requests over middleware/message channels; workers run on different processes or nodes | When horizontal scaling is needed to distribute the workload across multiple machines |

With remote partitioning, each partition's `ExecutionContext` is sent along with the execution request over the messaging mechanism. Workers need the corresponding job/step configuration and access to the required resources. `JobRepository` must be configured so the manager and workers coordinate metadata according to the deployment topology.

Remote partitioning differs from remote chunking. In remote partitioning, the manager splits the data and the worker executes the entire worker step for its assigned partition. In remote chunking, the manager typically reads and sends chunks to workers for processing/writing under a different model.

## 14. Distinguishing partitioning from multi-threaded step and split flow

All three mechanisms can run in parallel, but they divide work at different levels:

| Mechanism | Unit of parallelism | Characteristics |
|---|---|---|
| Partitioning | A data subset assigned to a worker `StepExecution` | Each worker has its own context and state |
| Multi-threaded step | Item/chunk processing iterations within a single step | May share some step components; requires thread safety considerations |
| `split()` flow | Independent flows or steps | Parallelizes different workflow branches |

Partitioning is suitable when independent data slices can be defined, such as by ID range or tenant. A multi-threaded step is suitable when a single step can process items in parallel according to its configuration and supporting components. `split()` is suitable when distinct business branches can execute independently.

## 15. Thread safety and resources inside workers

Each partition has its own `StepExecution`, but that does not automatically guarantee every bean used by the worker has a separate instance. Spring singleton beans can still be shared across workers.

Important considerations:

- Use `@StepScope` for readers/writers that hold state or need to receive partition-specific values.
- Do not share a reader holding a cursor or mutable state across partitions.
- Shared processors must be thread-safe or stateless.
- Writers must handle concurrent writes, including unique constraints and update ordering.
- The connection pool needs sufficient capacity for concurrent workers plus other application connections.
- Limit the executor so it does not overload the database, file system, or external APIs.

If two partitions write to the same record, race conditions or deadlocks can occur. Design the partitioner so writes do not conflict, or use appropriate locking/transactions/unique constraints.

## 16. Transactions and errors across partitions

Each worker step processes chunks using its own transactions via the worker's transaction manager. Chunks committed in one partition do not automatically roll back simply because another partition fails.

```text
partition0: chunk A -> COMMIT -> chunk B -> COMMIT
partition1: chunk A -> COMMIT -> chunk B -> FAILED
partition2: chunk A -> COMMIT -> chunk B -> COMMIT

Result: partition1 failed; completed commits in partition0 and partition2 remain.
```

Because workers are independent, a job can end in a failed state even though part of the data has already been successfully written. Restarts must rely on metadata and per-worker checkpoints; writers also need idempotency if they perform operations outside the transaction.

Do not assume partitioning provides an atomic commit across the entire dataset. If business requirements demand all-or-nothing across multiple partitions, a separate transaction or staging/publish design is needed—for example, writing to a staging table and running an atomic publish step after all partitions complete.

## 17. Handling empty partitions and uneven data

When the source has no data, the partitioner may create no partitions. The application should clearly define the desired behavior: complete the job with an empty result, record a no-data status, or report a business error.

For ranges with no records due to ID gaps, the worker can still run and complete with a read count of 0. Creating too many empty ranges increases metadata and worker initialization costs without providing any benefit.

You can check the record count before creating partitions, cap the partition count so it does not exceed the estimated workload, and avoid creating empty partitions if the splitting algorithm allows. Test the empty-source case specifically, as how the manager handles an empty partition map must match your specific version and configuration.

## 18. Common mistakes in partitioning

| Mistake | Consequence | How to handle |
|---|---|---|
| Overlapping ranges | An item is processed multiple times | Test inclusive/exclusive bounds and query predicates |
| Unassigned gaps in data | Some items are missed | Ensure partitions cover the entire target range |
| Using ID ranges with skewed data distribution | One worker runs significantly longer than others | Split using statistics or estimated record counts |
| Using a singleton reader with a cursor | Workers may share state and read incorrect data | Create a `@StepScope` reader for each execution |
| Large `gridSize` with too small an executor | Many partitions wait, or the system suffers unnecessary overhead | Tune grid size and pool according to resources |
| Partition names/ranges change on restart | Old metadata/checkpoints may attach to the wrong range | Keep names and splitting rules stable for the same JobInstance |
| Assuming all partitions roll back together | Committed partition data persists when another partition fails | Design for restart, idempotency, or staging/publish |
| Not bounding connection pool and worker count | Connection exhaustion or database overload | Set concurrency according to system capacity |
| Storing runtime objects in `ExecutionContext` | Metadata cannot be serialized | Store only keys, ranges, and small checkpoint data |

## 19. Testing the partitioner and workers

Partitioning should be tested at both the splitting algorithm level and step integration level.

Checks for `Partitioner`:

1. Total number of partitions does not exceed `gridSize` per the design rules.
2. Ranges do not overlap.
3. The union of ranges covers the entire data range accurately.
4. No gaps exist at boundaries between two partitions.
5. Remainder is distributed correctly when the total number of items is not evenly divisible.
6. Invalid `gridSize`, empty ranges, and a single item are handled properly.

Integration checks:

- Each worker only reads data belonging to its partition context.
- Total items written equals valid items in the range, with no duplicates or missing records.
- Workers actually execute concurrently within executor limits if parallelism is required.
- When a partition fails, metadata accurately records each worker's status.
- Restarting the same JobInstance skips completed partitions and resumes those that need rerunning.
- Reader state and checkpoints are properly restored after restart.

## 20. Design workflow for a partitioned job

You can implement in this sequence:

1. Identify the target dataset and a key that can split it into independent subsets.
2. Choose a partitioning strategy, ensuring non-overlapping and complete coverage.
3. Define a snapshot/watermark so source data remains stable throughout the run.
4. Write a `Partitioner` that produces stable names and a small `ExecutionContext` for each subset.
5. Write a worker step using `@StepScope` to read its assigned range.
6. Configure the manager step, `PartitionHandler`, `gridSize`, and executor.
7. Ensure worker readers/writers are safe with concurrency and transactions.
8. Test the splitting logic, performance, single-partition failure, and restart.
9. Monitor duration, read/write counts, and status of each `StepExecution` in production.

## Conclusion

Partitioning divides a workload into multiple independent subsets and creates a worker `StepExecution` for each partition. `Partitioner` describes the range via `ExecutionContext`; the manager step coordinates the worker steps; `JobRepository` stores individual statuses and checkpoints to track or restart each subset.

For accurate and efficient partitioning, subsets must be non-overlapping, cover the required data, have relatively balanced workloads, and maintain stable names/ranges on restart. Use `@StepScope` for components depending on partition context, size the executor to capacity, and remember that worker transactions are independent: committed partitions do not automatically roll back when another partition fails.
