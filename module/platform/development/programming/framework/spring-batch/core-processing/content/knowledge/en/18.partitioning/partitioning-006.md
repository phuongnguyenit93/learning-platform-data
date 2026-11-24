# Master step coordinates partitions

In Spring Batch, partitioning splits a large Step into multiple independent units of work so they can be processed concurrently or distributed to multiple workers. The **Master Step** (also called manager Step) is responsible for coordinating those units of work. Each unit is executed by a **worker Step** with its own StepExecution and ExecutionContext.

The Master Step does not directly read and write all business data. It creates or receives the partition list, asks PartitionHandler to launch a worker for each partition, collects results, and aggregates status. The Worker Step performs the actual work such as reading, processing, and writing its assigned partition's data.

Understanding the master's role helps design scalable Jobs, track per-partition progress, handle errors, and restart in a controlled manner.

## 1. Partitioning and the Master Step's role

Suppose a Job needs to import 1,000,000 orders. If one worker processes all the data, runtime can be long. The data range can be split into multiple partitions:

~~~text
Job: importOrdersJob
        |
        v
Master Step: managerStep
        |
        +-- Partition 0: orderId 1 - 250000
        |
        +-- Partition 1: orderId 250001 - 500000
        |
        +-- Partition 2: orderId 500001 - 750000
        |
        +-- Partition 3: orderId 750001 - 1000000
                 |
                 v
          Worker Step instances
~~~

Each partition is a distinct unit of work. The worker receives the partition's metadata, reads data belonging to that range, processes it, and writes results. Workers can run sequentially, in parallel within the same JVM, or across different processes/machines depending on the PartitionHandler.

The Master Step has these main responsibilities:

- Ask Partitioner to determine the partitions to execute.
- Create or coordinate creating StepExecutions corresponding to each partition.
- Pass each partition's ExecutionContext to the worker.
- Use PartitionHandler to distribute and launch workers.
- Collect worker StepExecution results.
- Aggregate status and finish the master Step appropriately based on partition outcomes.

The Worker Step has different responsibilities:

- Receive the data range from StepExecutionContext.
- Open readers and resources for its assigned range.
- Process data using reader, processor, and writer.
- Persist its own checkpoint if components support restart.
- Return completed or failed status to the master.

The Master Step is the coordinator. The Worker Step is the data-processing unit. Both roles can share a Step definition, yet each partition has its own StepExecution.

## 2. Main components in partitioning

A partitioning configuration typically has four components:

| Component | Responsibility |
| --- | --- |
| **Master Step** | Coordinates creating and executing partitions |
| **Partitioner** | Produces partition names and ExecutionContexts containing data needed by workers |
| **Worker Step** | Performs business processing for one partition |
| **PartitionHandler** | Launches workers, distributes work, and gathers execution results |

Coordination flow:

~~~text
Master Step
    |
    v
Partitioner.partition(gridSize)
    |
    +--> partition0 + ExecutionContext
    +--> partition1 + ExecutionContext
    +--> partition2 + ExecutionContext
    |
    v
StepExecutionSplitter
    |
    v
PartitionHandler
    |
    +--> Worker Step / partition0
    +--> Worker Step / partition1
    +--> Worker Step / partition2
    |
    v
Collect StepExecution results
    |
    v
Master Step aggregates status
~~~

Spring Batch uses abstractions such as Partitioner, StepExecutionSplitter, and PartitionHandler to execute this workflow. Applications typically configure Partitioner and worker Step; StepBuilder infrastructure constructs the master Step along with an appropriate handler.

## 3. Partitioner creates work ranges

Partitioner receives grid size and returns a Map of partition names to corresponding ExecutionContexts:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Each entry in the Map represents one partition. The key is the partition name, while ExecutionContext holds information the worker needs, for example:

- Start and end keys of the data range.
- Business date or tenant ID.
- Input file name or file position.
- Partition number or sort key.
- Small parameters needed to open resources.

Example Partitioner splitting orders by ID range:

~~~java
public class OrderRangePartitioner implements Partitioner {

    private final OrderRepository orderRepository;

    public OrderRangePartitioner(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = orderRepository.findMinId();
        long maxId = orderRepository.findMaxId();

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        if (maxId < minId) {
            return partitions;
        }

        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minOrderId", start);
            context.putLong("maxOrderId", end);

            partitions.put("partition" + partitionNumber, context);

            start = end + 1;
            partitionNumber++;
        }

        return partitions;
    }
}
~~~

This example illustrates splitting a contiguous ID range into nearly equal segments. In real systems, carefully handle empty tables, large ID gaps, or arithmetic overflow risks. If IDs are non-contiguous or data distribution is skewed, splitting evenly by arithmetic range can create partitions with vastly different item counts.

Another strategy is splitting by date, tenant, hash bucket, or key groups of roughly equal size. What matters is that each partition has a clear scope and does not accidentally read data belonging to another partition.

## 4. ExecutionContext passes data from master to worker

Partitioner does not pass the entire list of items to workers. It passes information describing the processing range via ExecutionContext.

Example partitioner creating context:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minOrderId", 1L);
context.putLong("maxOrderId", 250000L);
~~~

The Worker Step can read these values using Step scope:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderReader(
        OrderRepository orderRepository,
        @Value("#{stepExecutionContext['minOrderId']}") Long minOrderId,
        @Value("#{stepExecutionContext['maxOrderId']}") Long maxOrderId) {

    return new OrderRangeReader(
            orderRepository,
            minOrderId,
            maxOrderId);
}
~~~

StepExecutionContext holds values specific to the current partition. When the worker for partition 0 runs, the reader receives partition 0's min/max; the worker for partition 1 receives a different range.

### Why is @StepScope needed?

The Worker Step may execute multiple times for multiple partitions. If the reader were created once and kept min/max in fields, workers could share one instance and overwrite each other's range data.

@StepScope defers bean creation until a specific StepExecution exists. Thus, each partition gets a reader instance initialized with its own ExecutionContext.

Components depending on partition context such as readers, processors, or writers may also need Step scope. Do not scope every bean; use it only when a bean needs access to StepExecution-bound data or requires a separate instance per StepExecution.

ExecutionContext should contain small data that can be stored in JobRepository and serialized under the active mechanism. Do not put lists of millions of IDs, connections, streams, service objects, or large payloads into context.

## 5. Configuring the Worker Step

The Worker Step is typically a chunk-oriented Step like any regular Step. The difference is that the reader or other components receive their range from StepExecutionContext.

Example:

~~~java
@Bean
public Step orderWorkerStep(
        JobRepository jobRepository,
        @Qualifier("businessTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

The worker processes 100 items per chunk within the ID range the reader receives from partition context. Each partition has its own StepExecution, so read count, write count, status, and ExecutionContext for the worker are tracked independently.

If the worker uses a stateful reader, ensure the reader implements ItemStream or uses a restart-capable implementation. Each partition must have its own checkpoint so restarting one partition does not alter another partition's progress.

## 6. Configuring the Master Step with StepBuilder

From Spring Batch 5 onward, you can configure a master Step to run partitions using TaskExecutorPartitionHandler via StepBuilder:

~~~java
@Bean
public Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner(orderWorkerStep.getName(), orderPartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

Meaning of each part:

- orderManagerStep is the master Step name stored in JobRepository.
- partitioner(...) provides the Partitioner to create ExecutionContexts.
- step(orderWorkerStep) specifies the worker Step to run for each partition.
- gridSize(4) provides the target partition scale for work splitting.
- taskExecutor(...) configures worker execution via an executor.

Grid size is an input to partition creation and handler configuration. The actual number of partitions is determined by the Map returned by Partitioner. A custom Partitioner can return fewer or more than grid size if splitting logic requires it; therefore, do not treat grid size as a hard guarantee on partition count.

### Configuring TaskExecutor

Example using ThreadPoolTaskExecutor:

~~~java
@Bean
public TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("order-partition-");
    return executor;
}
~~~

The executor above allows up to four workers to run concurrently. When Spring manages the bean, ThreadPoolTaskExecutor's lifecycle is initialized and shut down with the container. If creating an executor outside Spring, the application must manage the thread pool lifecycle.

Do not set thread count based solely on CPU count. Workers can be bottlenecked by database connections, I/O, external APIs, or locks. Concurrent worker count must stay within the capacity of dependent systems.

## 7. Placing the Master Step in the Job flow

The Master Step is declared like any Step in the Job. After all partitions are processed and results are aggregated, the Job can transition to the next Step:

~~~java
@Bean
public Job orderImportJob(
        JobRepository jobRepository,
        Step orderManagerStep,
        Step publishImportSummaryStep) {

    return new JobBuilder("orderImportJob", jobRepository)
            .start(orderManagerStep)
            .next(publishImportSummaryStep)
            .build();
}
~~~

The Job flow only moves to publishImportSummaryStep after orderManagerStep completes with an appropriate status. If a worker partition fails and the master Step finishes FAILED, the default flow will not proceed as a normal completion unless a transition handles the failure branch.

The Master Step has its own StepExecution. Worker StepExecutions are child executions linked to the same JobExecution and persisted in JobRepository.

## 8. PartitionHandler coordinates workers

PartitionHandler is the abstraction responsible for executing partitions. It receives StepExecutionSplitter and the master's StepExecution, then launches workers and returns the corresponding set of StepExecutions.

There are two common implementation approaches:

**Local partitioning:** workers run in the same JVM, typically through TaskExecutorPartitionHandler. This is a simple way to scale processing across multiple threads in one application.

**Remote partitioning:** master sends partition execution requests over middleware or message channels to other worker processes. Workers execute the Step and send results back to the master. This fits when distributing load across multiple processes or machines.

~~~text
Local partitioning

Master Step
    |
    v
TaskExecutorPartitionHandler
    |
    +--> Worker thread 1
    +--> Worker thread 2
    +--> Worker thread 3
    +--> Worker thread 4


Remote partitioning

Master Step
    |
    v
Messaging / middleware
    |
    +--> Worker process A
    +--> Worker process B
    +--> Worker process C
    |
    v
Results sent back to master
~~~

With local partitioning, partition data and beans are passed within the same application. With remote partitioning, you also need message serialization, routing, message retries, handling disconnected workers, and ensuring the metadata repository is shared or properly configured between master and workers.

Remote partitioning differs from remote chunking. In remote partitioning, each worker runs an independent Step on a data partition. In remote chunking, the manager reads and sends chunks to workers for processing/writing under a different model. Choose the right model based on where reading should occur and how work is distributed.

## 9. Master aggregates partition status

Each partition has its own StepExecution. When workers finish, results return to the handler and the master Step aggregates status.

Example:

~~~text
Master: orderManagerStep
    |
    +-- partition0: COMPLETED
    +-- partition1: COMPLETED
    +-- partition2: FAILED
    +-- partition3: COMPLETED
             |
             v
      Master Step: FAILED
~~~

If one partition fails, the master generally cannot consider the overall work complete. The Master Step can finish FAILED after the handler collects results. The Job flow then handles execution based on the master Step's status.

Do not inspect only the master status while ignoring individual worker statuses. When investigating, identify which partition failed, which partitions already committed data, and which partitions have not started.

You can query JobExecution's StepExecutions via JobExplorer to see each worker's status. A partition's StepExecution name typically combines the worker Step name and partition name, though you should use actual metadata rather than string concatenation to determine IDs.

## 10. How to split partitions evenly

Partition quality directly impacts overall Job completion time. If partitions differ significantly in volume, fast workers finish early and wait for the slowest partition.

Example splitting by ID range:

| Partition | ID Range | Actual item count |
| --- | --- | ---: |
| 0 | 1-250000 | 240000 |
| 1 | 250001-500000 | 18000 |
| 2 | 500001-750000 | 220000 |
| 3 | 750001-1000000 | 6000 |

Equal ID ranges do not guarantee equal item counts if data has gaps or skewed distributions.

Several splitting strategies:

- **Range partitioning:** split by key or time intervals. Simple and observable, but requires checking distribution.
- **Hash partitioning:** use key hashes to spread data. Can balance well if keys distribute evenly, but requires matching query predicates.
- **Tenant partitioning:** each tenant or tenant group is a partition. Fits when data boundaries align with customers.
- **Date partitioning:** split by day, month, or business period. Easy to reconcile, though periods with uneven load must be considered.
- **File partitioning:** each file or file group is a partition. Fits independent file-processing pipelines.

Measure actual item counts and processing cost per partition. If certain records are much heavier, balancing by item count may still not balance by processing time.

## 11. Restarting when a partition fails

Partitioning supports restarts thanks to per-worker StepExecution and ExecutionContext metadata. If one partition fails, the master's JobExecution can finish FAILED. When restarting the same JobInstance, Spring Batch uses metadata to determine which partitions completed and which need to rerun, depending on configuration and worker restartability.

~~~text
First run:

partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED

Restart:

partition0 -> already completed, typically skipped
partition1 -> already completed, typically skipped
partition2 -> rerun from worker checkpoint if present
partition3 -> already completed, typically skipped
~~~

For accurate restarts:

- Keep Job name and identifying JobParameters unchanged.
- Keep partition names or partition mapping rules stable.
- Ensure Partitioner recreates ranges consistent with the prior run.
- Worker readers/writers must persist checkpoints if resuming mid-partition is needed.
- Side effects must be idempotent because a failed partition may be re-executed.

If Partitioner relies on changing source data, a restart may generate different ranges than the initial run. Use an input snapshot, watermark, or explicit range parameters so splitting remains stable.

### Partitioner and stable partition names

The partition name is critical for Spring Batch to link executions and statuses. Do not generate random names on each partitioner call if the goal is restarting the same partitions.

Example stable names:

~~~text
partition0
partition1
partition2
partition3
~~~

Partition ExecutionContext must also preserve stable meaning. If partition0 previously represented order IDs 1-250000 but after a new deployment represents 500001-750000, old checkpoints could be applied to the wrong range.

When changing the partitioning algorithm or partition count across versions, establish a compatibility strategy and handle old metadata. Do not alter how data is split while restartable JobExecutions still exist without evaluating the impact.

## 12. Notes on shared data and transactions

Partitioning allows workers to process independently, but it does not automatically create distributed transactions or guarantee contention-free data access.

When designing workers:

- Each partition should have non-overlapping data ranges if writing to the same table.
- Database unique keys and constraints are still needed to protect data.
- Readers and writers should be configured with an appropriate transaction manager.
- The connection pool must be sufficient for concurrent workers without exceeding database limits.
- Avoid having multiple partitions update the same record or sequential resource.
- If metadata and business data use separate databases, understand the potential for split commits.

Each worker has its own StepExecution/chunk transactions. One partition's transaction does not automatically roll back transactions committed in another partition. If partition 2 fails after other partitions complete, committed data from successful partitions remains.

Therefore, workers must be idempotent or use business keys so restarts do not write duplicates. If business rules require either all partitions succeeding or no partition retaining results, design staging and a business-level publish/commit step; individual chunk transactions cannot provide Job-wide atomicity.

## 13. Thread safety and shared resources

With local partitioning, multiple workers can run in the same JVM. Singleton beans are shared unless given an appropriate scope. Therefore:

- Readers holding cursors or read positions usually need a separate instance per StepExecution.
- Writers with internal state must be checked for thread safety.
- Processors should not hold shared mutable state unless synchronized.
- Shared repositories/services must be safe under concurrent calls.
- Buffers, file handles, and client connections must have explicit lifecycles.

@StepScope is the usual choice for readers/processors/writers depending on StepExecutionContext. However, scope does not automatically make every collaborator thread-safe; singleton services injected into step-scoped beans can still be invoked concurrently by multiple workers.

If partitions write files, write separate files per partition and merge them after completion. Avoid multiple workers writing sequentially to a single file if the writer does not support concurrency.

## 14. Tuning grid size and concurrency

Grid size, actual partition count, and concurrent worker count are related concepts, not the same thing:

- **Grid size:** scale passed into partitioning and handler configuration.
- **Partition count:** actual number of entries Partitioner returns.
- **Concurrency:** number of workers able to run simultaneously per TaskExecutor or remote infrastructure.

For example, Partitioner might create 12 partitions while TaskExecutor allows only 4 workers concurrently. The remaining partitions wait for their turn.

~~~text
12 partitions
    |
    v
TaskExecutor: max 4 workers
    |
    +-- Batch 1: partition 0-3
    +-- Batch 2: partition 4-7
    +-- Batch 3: partition 8-11
~~~

Increasing partition count does not necessarily increase throughput if concurrent worker count stays unchanged. It can improve load balancing or create smaller restart units, but also increases metadata and coordination overhead.

Increasing worker count can increase throughput until database, network, CPU, or target systems hit limits. Monitor connection pool, lock waits, CPU, I/O, and per-partition completion time to tune accordingly.

## 15. Observing and diagnosing the Master Step

Both Master Step and worker StepExecutions are stored in JobRepository. JobExplorer can retrieve execution history and inspect each partition's status.

Example:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, read={}, write={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount());
    }
}
~~~

When investigating, check:

- Whether the Master Step started and completed.
- How many partitions Partitioner returned.
- Name and ExecutionContext of each partition.
- Which workers started, completed, or failed.
- Read/write/skip counts of each worker.
- Runtime and wait time of each partition.
- Root exception of any failed worker.
- Checkpoints and committed side effects.

If one partition runs unusually long, inspect data distribution and reader queries. If all workers are slow, the bottleneck may be the database, connection pool, or a shared system rather than the partitioning scheme.

## 16. Common mistakes

### Master Step used as Worker Step

Master coordinates partitions; workers read and write data. Do not put all data-processing logic in the master expecting PartitionHandler to split the work automatically.

### Partitioner creating overlapping ranges

Two workers reading the same record can cause duplicate writes or contention. Define explicit inclusive/exclusive boundaries and verify intervals do not intersect.

### Using a singleton reader across multiple partitions

A stateful reader can have its read position overwritten by concurrent workers. Use Step scope or an appropriate per-instance creation mechanism.

### Putting large data into ExecutionContext

ExecutionContext is metadata, not a vehicle for passing millions of items. Store only keys, ranges, and small parameters so workers query the source directly.

### Confusing grid size with concurrent worker count

Partitioner may create more partitions than threads. Check both the returned Map and TaskExecutor limits.

### Changing partition mapping on restart

Old checkpoints may be applied to new ranges. Keep partition names and mappings stable throughout the lifecycle of a restartable JobInstance.

### Assuming all partitions roll back together when one fails

Worker transactions are independent. Committed partitions retain data when another partition fails. Design idempotency or staging if Job-wide recovery is needed.

### Splitting evenly by ID with skewed load

IDs can have gaps or skewed distributions. Measure actual item counts and processing time to choose a partitioning strategy.

### Increasing concurrency beyond database capacity

Too many workers can exhaust the connection pool, increase lock contention, or overload the database. Tune thread pool and connection pool together.

### Ignoring worker errors

Master must observe each partition's outcome and the Job flow needs appropriate error transitions. Do not ignore a FAILED worker merely because other partitions succeeded.

## 17. Master/Worker partitioning design workflow

When building a partitioned Step, determine in order:

1. Is data split by key, date, tenant, file, or another business rule?
2. Does Partitioner generate non-overlapping ranges that can be reproduced reliably?
3. What values must ExecutionContext pass to workers?
4. Which readers, processors, and writers require @StepScope?
5. Which transaction manager and chunk size does the Worker Step use?
6. Is a local or remote PartitionHandler suited to deployment requirements?
7. What levels should grid size, partition count, and concurrency be set to?
8. Do workers contend on shared resources or write the same data?
9. When one partition fails, how are already-committed partitions handled?
10. Do restarts preserve JobParameters, partition names, mappings, and checkpoints?
11. Do JobExplorer and logs have enough detail to pinpoint a failing worker?
12. Is an aggregation or result-publishing Step needed after all partitions complete?

Test with realistically distributed data, trigger a controlled failure in one worker, and restart the Job to confirm completed partitions are handled properly, the failed partition recovers, and no duplicate data is created.

## Conclusion

The Master Step is the coordinator in Spring Batch partitioning. It uses Partitioner to create partitions with ExecutionContexts, uses StepExecutionSplitter and PartitionHandler to dispatch Worker Steps, and then collects and aggregates worker statuses. The Worker Step processes data within its isolated range and persists checkpoints per StepExecution. For scalable and restart-safe partitioning, maintain non-overlapping splits, stable partition names and mappings, proper Step-scoped components, concurrency within system limits, and idempotent side effects.
