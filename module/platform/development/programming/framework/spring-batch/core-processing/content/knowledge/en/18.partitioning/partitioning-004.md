# PartitionHandler in Spring Batch

In Spring Batch, partitioning splits a large step into multiple independent units of work. Each unit is represented by a separate `StepExecution` and can run on a different thread or worker. `PartitionHandler` is the component responsible for executing those units of work and collecting results so the coordinating step (manager step) knows whether they have completed, failed, or are still running.

`Partitioner` defines how data is split; `StepExecutionSplitter` creates the corresponding executions; and `PartitionHandler` decides where and how those executions run. Understanding the handler's role helps you choose between running in parallel within the same JVM and remote partitioning across multiple processes/machines, while controlling concurrency, restarts, and per-partition failures.

## 1. Partitioning and the manager/worker model

Partitioning fits when a step can be divided into independent data subsets. For instance, a job needs to process one million customers. Instead of one worker processing all data, the application can split by ID ranges and assign each range to a worker step.

```text
Parent Job
    |
    v
Manager Step
    |
    +-- Partitioner defines data regions
    |
    +-- StepExecutionSplitter creates StepExecutions
    |
    v
PartitionHandler
    |
    +---- Partition 0 -> Worker Step (ID 1..250000)
    +---- Partition 1 -> Worker Step (ID 250001..500000)
    +---- Partition 2 -> Worker Step (ID 500001..750000)
    +---- Partition 3 -> Worker Step (ID 750001..1000000)
    |
    v
Manager aggregates worker results
    |
    v
Manager Step completes or fails
```

The manager step coordinates. The worker step executes the logic to read, process, and write data. Each partition has its own `StepExecution` and `ExecutionContext`, allowing the worker to receive its own data-range parameters.

Partitioning generally improves throughput when data subsets are independent, can be processed concurrently, and do not contend heavily on shared resources. It does not automatically make a sequential algorithm parallel; the data and business operations must be safely separable.

## 2. What is PartitionHandler?

`PartitionHandler` is the abstraction responsible for executing the split `StepExecution`s. It receives a `StepExecutionSplitter` along with the manager's `StepExecution`, asks the splitter to create child executions, dispatches them, and returns the collection of results.

Conceptual API contract:

```java
public interface PartitionHandler {

    Collection<StepExecution> handle(
        StepExecutionSplitter stepExecutionSplitter,
        StepExecution stepExecution
    ) throws Exception;
}
```

The two parameters play distinct roles:

- `StepExecutionSplitter` creates the `StepExecution`s for each partition based on the manager execution, partitioner, and metadata repository.
- The passed `StepExecution` is the manager step's execution, serving as the context for creating worker executions.

The handler does not decide which data belongs to which partition; that belongs to `Partitioner`. The handler focuses on how to dispatch executions and gather results. With a local handler, workers can run using a `TaskExecutor`. With remote partitioning, the handler sends requests to workers over middleware and awaits results via the integration mechanism.

## 3. Distinguishing components in partitioning

| Component | Responsibility |
| --- | --- |
| `Partitioner` | Creates a map from partition name to `ExecutionContext` containing data/ranges for the worker. |
| `StepExecutionSplitter` | Creates or restores worker `StepExecution`s based on partition metadata and restart state. |
| `PartitionHandler` | Coordinates execution of worker executions and collects results. |
| Manager step | Coordinates overall partitioning within the job flow. |
| Worker step | Executes business logic for a specific partition. |
| `JobRepository` | Stores manager execution state, worker executions, and related contexts. |

For example, `Partitioner` creates `partition0` with `minId=1`, `maxId=1000`; the handler takes the corresponding execution and runs the worker step; the worker reader pulls those two values from the step execution context to read only that partition's slice of data.

## 4. Where is PartitionHandler used?

In job configuration, the handler is attached to the manager step. Using the Spring Batch 5 builder API, it can be configured as follows:

```java
@Bean
Step managerStep(JobRepository jobRepository,
                 Partitioner customerPartitioner,
                 PartitionHandler customerPartitionHandler) {
    return new StepBuilder("managerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .partitionHandler(customerPartitionHandler)
        .build();
}
```

`partitioner("customerWorkerStep", ...)` specifies the worker step name and the partitioner component. `.partitionHandler(...)` provides the execution mechanism for worker executions.

Another configuration style uses builder convenience methods like `.step(workerStep).gridSize(...).taskExecutor(...)` when you want Spring Batch to build a local handler backed by a `TaskExecutor`. Using an explicit handler is useful when you need to customize dispatch behavior or choose a different implementation.

## 5. TaskExecutorPartitionHandler: running partitions in the same JVM

`TaskExecutorPartitionHandler` is the common implementation for running partitions using a `TaskExecutor`. Worker steps run within the same application process, typically on different threads.

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("batch-partition-");
    return executor;
}

@Bean
TaskExecutorPartitionHandler customerPartitionHandler(
        Step customerWorkerStep,
        TaskExecutor partitionTaskExecutor) {

    TaskExecutorPartitionHandler handler =
        new TaskExecutorPartitionHandler();
    handler.setStep(customerWorkerStep);
    handler.setTaskExecutor(partitionTaskExecutor);
    handler.setGridSize(4);
    return handler;
}
```

The manager step then uses `customerPartitionHandler` as in the earlier example. `TaskExecutorPartitionHandler` executes the worker step across the partition executions created by the splitter.

Advantages of running locally:

- Simple configuration, no broker or messaging middleware required.
- Easy to debug in a single process and convenient for integration tests.
- Can share bean infrastructure, datasource, and metadata repository.
- Suitable when the load can be handled on one machine and machine resources are sufficient.

The limitation is that all workers share the CPU, heap, connection pool, and resources of the same JVM/host. If you need to scale across multiple machines or isolate workers by process, remote partitioning is more appropriate.

## 6. MessageChannelPartitionHandler: remote partitioning

When workers need to run on different processes or machines, remote partitioning can be used. The manager sends partition execution requests over messaging middleware; workers receive requests, execute the step, and update results.

In the Spring Batch ecosystem, `MessageChannelPartitionHandler` is an implementation serving this model, commonly used with Spring Integration and message channels. The worker side has a component that handles `StepExecutionRequest` to run the designated step.

```text
Manager application
  Manager Step
      |
      v
  Partitioner + StepExecutionSplitter
      |
      v
  MessageChannelPartitionHandler
      |
      v
  Queue / Message Broker
      |
      +-----------------------------+
      |              |              |
      v              v              v
 Worker node 1   Worker node 2   Worker node 3
      |              |              |
      v              v              v
  Worker Step    Worker Step    Worker Step
      |              |              |
      +--------------+--------------+
                     |
                     v
          Metadata/result coordination
                     |
                     v
                Manager continues
```

Remote partitioning is suitable when you need to scale workers independently, utilize multiple machines, or deploy workers with dedicated capacities. In return, the system must manage the broker, message serialization, network errors, timeouts, worker availability, and metadata consistency.

In the standard remote model, manager and workers must access a shared metadata repository or a compatibly designed repository mechanism so worker executions are recorded and the manager can track results. Ensure schema configuration, table prefixes, and Spring Batch versions are compatible across nodes.

Remote partitioning differs from remote chunking. In remote partitioning, each worker runs an independent step on a data partition. In remote chunking, the manager typically reads and distributes chunks to workers for processing; the boundaries of work division and read/write responsibilities differ.

## 7. Creating partitions with Partitioner

`Partitioner` returns a `Map<String, ExecutionContext>`. Each key is a partition name; each value contains the data the worker needs to process its corresponding slice.

Example splitting an ID range from 1 to 10,000:

```java
public class CustomerRangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long minId = 1L;
        long maxId = 10_000L;
        long total = maxId - minId + 1;
        long targetSize = (total + gridSize - 1) / gridSize;

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);

            partitions.put("partition" + partitionNumber, context);
            start = end + 1;
            partitionNumber++;
        }

        return partitions;
    }
}
```

With `gridSize=4`, the partitioner creates four regions of roughly equal size. The example uses ranges inclusive at both endpoints (`minId` and `maxId`), so the worker query needs `BETWEEN` or an equivalent predicate.

In production, `minId` and `maxId` should come from actual data or a business snapshot, not be hard-coded. If data is empty, the partitioner needs explicit behavior, such as returning an empty map or creating a no-op partition depending on operational requirements and how the application represents an empty step.

## 8. Workers reading range from StepExecutionContext

Each worker must receive the exact range assigned by the partitioner. `@StepScope` allows creating a reader per `StepExecution` and pulling values from the step execution context via SpEL.

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            select id, name
            from customer
            where id between ? and ?
            order by id
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
        .saveState(true)
        .build();
}
```

The reader is instantiated per worker execution so each partition gets its own `minId` and `maxId`. Do not use a singleton reader with a shared mutable cursor across all partitions, as workers can overwrite each other's read positions.

The worker step can be declared like a standard chunk step:

```java
@Bean
Step customerWorkerStep(JobRepository jobRepository,
                        PlatformTransactionManager transactionManager,
                        ItemReader<Customer> customerReader,
                        ItemProcessor<Customer, CustomerSummary> processor,
                        ItemWriter<CustomerSummary> writer) {
    return new StepBuilder("customerWorkerStep", jobRepository)
        .<Customer, CustomerSummary>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Each partition runs the same worker step definition but has its own `StepExecution` and step context. Non-step-scoped beans may still be shared across workers; if they hold mutable state, ensure thread safety or move them to an appropriate scope.

## 9. Complete manager step configuration

Combining partitioner, worker step, and handler:

```java
@Bean
Partitioner customerPartitioner() {
    return new CustomerRangePartitioner();
}

@Bean
Step customerManagerStep(JobRepository jobRepository,
                          Partitioner customerPartitioner,
                          PartitionHandler customerPartitionHandler) {
    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .partitionHandler(customerPartitionHandler)
        .build();
}

@Bean
Job customerImportJob(JobRepository jobRepository,
                       Step customerManagerStep) {
    return new JobBuilder("customerImportJob", jobRepository)
        .start(customerManagerStep)
        .build();
}
```

The name `"customerWorkerStep"` in `.partitioner(...)` must match the worker step name used by the handler. Keep partition names stable so metadata and restarts can identify corresponding executions.

For simple setups, the builder API can declare the worker step, grid size, and task executor directly:

```java
@Bean
Step customerManagerStep(JobRepository jobRepository,
                         Step customerWorkerStep,
                         Partitioner customerPartitioner,
                         TaskExecutor partitionTaskExecutor) {
    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner(customerWorkerStep.getName(), customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
```

This approach lets the builder construct a local partition handler configuration from the worker step and task executor. Choose one clear configuration style; do not simultaneously attach an explicit handler and convenience settings to the same manager step.

## 10. Grid size and thread count are not the same concept

`gridSize` is a hint for the number of partitions the manager asks the partitioner to create. The number of concurrently running workers also depends on `TaskExecutor`, available threads, resource limits, and the handler implementation.

Example:

| Grid size | Thread pool size | Possible behavior |
| ---: | ---: | --- |
| 4 | 4 | Up to four partitions can run simultaneously. |
| 8 | 4 | Eight partitions created; four run first, remaining partitions wait for their turn. |
| 4 | 8 | Only four partitions created; extra threads have no partitions to run. |
| 20 | 4 | More partitions, potentially reducing slice size but adding overhead and metadata. |

Grid size does not guarantee the actual thread count. A `TaskExecutor` may use a queue, concurrency limit, or its own executor policy. With a remote handler, concurrency depends on active workers, message consumption capacity, and broker limits.

Choose the partition count based on data size, CPU cores, database connection pool, I/O speed, and worker startup time. Too many tiny partitions can increase coordination and metadata overhead without improving throughput.

## 11. Local partitioning vs. remote partitioning

| Criterion | Local with `TaskExecutorPartitionHandler` | Remote with message handler |
| --- | --- | --- |
| Worker location | Same JVM/host as manager | Can be in a different JVM or machine |
| Dispatch mechanism | Task executor/thread pool | Message channel/broker |
| Infrastructure | Spring Batch and executor | Often requires Spring Integration and middleware |
| Scalability | Limited to one host's resources | Can add worker nodes |
| Common failures | Thread contention, heap, connection pool | Network, broker, timeout, worker availability |
| Operations | Simpler | Requires observing and operating manager, broker, and workers |

Choose local partitioning when a single machine has sufficient resources and you want to increase concurrency with minimal setup. Choose remote partitioning when you need to scale workers across multiple machines, isolate resources, or deploy workers as separate groups.

Remote partitioning does not automatically make workers safer. You still need non-overlapping data splits, transaction management, idempotency, and restart handling. Messaging also introduces additional failure modes that must be handled.

## 12. PartitionHandler and remote chunking differ

Both models can use middleware to distribute work, but they divide responsibilities differently:

- **Remote partitioning:** the manager splits data into partitions and sends requests to run the worker step. Each worker reads, processes, and writes its assigned slice independently.
- **Remote chunking:** the manager typically retains the reading role and sends chunks to workers for processing/writing. Workers receive chunks rather than running a step that reads its own range.

Remote partitioning fits when each worker can independently read its data slice from a shared or identified source. Remote chunking fits when reading should stay centralized on the manager while processing/writing can be distributed.

Do not choose remote partitioning merely because `PartitionHandler` exists. Identify whether the bottleneck is in reading, processing, or writing, and choose the model matching data source ownership.

## 13. Restarts and stable partition names

Spring Batch persists a `StepExecution` for each partition. When the manager step restarts, `StepExecutionSplitter` uses stored metadata to determine which partitions need re-execution and which have already completed according to restart semantics.

Partition names and range data must be stable across reruns of the same `JobInstance`. For example, if `partition0` previously processed IDs 1..1000 but on restart is assigned IDs 500..1500, old metadata may be applied to a different data region.

Important principles:

- Use partition names that are stable and unique within a worker step.
- Build ranges from a consistent snapshot or data identifier.
- Do not arbitrarily change how data is split between the initial run and a restart.
- Worker readers must persist checkpoints in the step execution context if restarting within a partition is needed.
- Writers must tolerate reprocessing of uncommitted data.
- Verify old partition executions are no longer running before relaunching.

If source data changes continuously, establish a snapshot, watermark, or batch ID so all partitions within the same job instance process the same logical dataset.

## 14. When a partition fails

Suppose the manager creates four partitions and partition 2 fails:

```text
partition0 -> COMPLETED
partition1 -> COMPLETED
partition2 -> FAILED
partition3 -> COMPLETED
                    |
                    v
          Manager partition step FAILED
```

The manager step generally cannot treat the whole partition step as completed if one worker execution fails. Per-worker metadata helps identify which parts finished and which require investigation.

On restart, completed partitions are usually recognized via the repository and do not need to rerun under default restart behavior; failed or incomplete partitions can be re-executed. This depends on `allowStartIfComplete`, step configuration, and splitter logic. Do not rely on this assumption if the partitioner generates unstable names or ranges.

Partition transactions are independent. If partition 0 committed data and partition 2 failed, partition 0's committed data remains. Partitioning does not provide an atomic transaction spanning all workers. If business requirements demand undoing all results when one partition fails, design a staging/final commit, batch status, or compensation workflow.

## 15. Preventing duplicate and missed data

The partitioner must produce data regions that accurately cover the input set without overlapping if each item must be processed once. With ID-based partitioning, explicitly define inclusive/exclusive bounds.

Example using half-open intervals:

```sql
select id, name
from customer
where id >= :minId
  and id < :maxIdExclusive
order by id
```

Or using closed intervals inclusive at both ends:

```sql
select id, name
from customer
where id between :minId and :maxId
order by id
```

Do not mix conventions. If the previous partition ends at 1000 and the next partition starts at 1000 in a `BETWEEN` query, item 1000 will be processed twice. If the previous partition uses `< 1000` and the next uses `>= 1000`, the boundary will not overlap.

Beyond ID ranges, you can partition by date, tenant, region, hash bucket, or file list. Regardless of strategy, ensure all partitions use the same filter rules and the same data snapshot.

## 16. Transactions and shared resources

Each worker step has its own transactions. For chunk workers, each chunk of a partition has its own transaction; there is no global transaction spanning all partitions unless the application explicitly builds an appropriate distributed mechanism.

When running multiple workers concurrently, verify:

- The database connection pool is sufficient for all workers and other application operations.
- Partitions do not update the same rows in a way that causes lock contention or deadlocks.
- Readers use isolated ranges without sharing a mutable cursor.
- Writers use an appropriate transaction manager and are idempotent when retries are needed.
- Singleton processors/services do not hold per-item state unless thread-safe.
- Output files have unique names per partition or an explicit synchronized writing mechanism.
- External APIs have rate limits compatible with total concurrency.

For example, if the database pool only has 8 connections while running 20 workers, workers will wait for connections and throughput drops. Increasing grid size will not solve connection limits; it can worsen contention and timeouts.

## 17. StepScope and partition-specific state

Values in `ExecutionContext` are specific to each partition. Use `@StepScope` for readers, writers, or processors that need partition values at initialization:

```java
@Bean
@StepScope
ItemProcessor<Customer, CustomerSummary> customerProcessor(
        @Value("#{stepExecutionContext['region']}") String region) {

    return customer -> new CustomerSummary(
        customer.getId(),
        region,
        customer.getName()
    );
}
```

Do not inject `stepExecutionContext` into a singleton bean and store values in mutable fields shared across workers. `@StepScope` lets Spring create the target per step execution, giving each partition dependencies initialized with its corresponding context.

If a service is shared across workers, it should be stateless or designed to be thread-safe. Step scope does not automatically make every dependency injected into it thread-safe; underlying singleton beans can still be shared.

## 18. Limiting and coordinating concurrency

Concurrency should be bounded by the actual bottleneck, not just CPU count. A job reading and writing a database may be bound by the connection pool, I/O, or locks; an image-processing job may be bound by CPU and heap.

Ways to control concurrency:

- Set core/max pool sizes on `ThreadPoolTaskExecutor`.
- Choose a `gridSize` sufficient to create reasonably sized partitions.
- Limit the number of remote workers consuming messages.
- Configure timeouts and queues aligned with processing duration.
- Monitor active partitions, queue depth, worker latency, and connection waits.
- Avoid running multiple partitioned jobs concurrently beyond database capacity.

If partitions are unevenly sized, some workers finish early while the slowest worker keeps the manager step running. Consider splitting by estimated record count or processing cost rather than evenly splitting IDs when per-record cost varies.

## 19. Testing Partitioner and PartitionHandler

Separate testing of data splitting from testing of execution.

### Unit tests for Partitioner

Verify:

- Number of partitions created for a given grid size and input data.
- Ranges do not overlap.
- No gaps exist between partitions.
- Total covered items match the input set.
- Empty data, single item, and fewer items than grid size cases.
- Invalid grid sizes are handled explicitly.

For example, with IDs 1..10 and grid size 3, verify that the ranges cover all 10 IDs without duplicates. Do not check only the map size.

### Integration tests for local handler

Use `TaskExecutorPartitionHandler` with a worker step that records processed IDs. Run the manager job using `JobLauncherTestUtils`, then verify:

- All partition executions are created.
- Every item belongs to exactly one partition.
- Worker executions have expected statuses.
- Total `readCount`/`writeCount` matches the dataset.
- The job/manager step completes when all workers succeed.

### Testing failures and restarts

Make one partition fail deterministically, verify the manager step/job fails, and verify metadata records the corresponding partition. Then restart the same `JobInstance`, checking that completed partitions do not rerun unexpectedly and the failed partition resumes from its appropriate checkpoint.

With remote partitioning, also test message serialization, worker unavailability, timeouts, message retries/redelivery, and cases where a worker finishes but the reply is lost. Consumers/workers must handle duplicate messages safely.

## 20. Monitoring and diagnosing PartitionHandler

When a manager step is slow or fails, inspect both the manager execution and each worker `StepExecution`:

- Number of partitions created and number currently active.
- Start/end times of each worker.
- `BatchStatus`, `ExitStatus`, and failure exceptions.
- `readCount`, `writeCount`, skip count, commit count, and rollback count.
- Grid size, executor pool size, and actual thread/worker count.
- Connection pool waits, database locks, CPU, heap, and queue depth.
- Which partition runs unusually long or has skewed volume.

For remote handlers, include message ID, queue/topic, send/receive timestamps, redelivery count, and worker ID. Log the parent job execution ID, manager step execution ID, and worker step execution ID to trace relationships.

Do not look solely at manager step status. The manager may fail because of a single worker; inspect child executions to learn which partition failed and where its last checkpoint lies.

## 21. Common mistakes when using PartitionHandler

**Confusing Partitioner with PartitionHandler:** the partitioner splits data and creates contexts; the handler orchestrates execution of those runs. Changing concurrency does not necessarily require rewriting the partitioner.

**Assuming grid size equals thread count:** grid size is the requested partition count; actual concurrency is governed by the executor or worker pool.

**Using a singleton reader with shared state:** partitions can overwrite each other's cursors. Use a step-scoped reader and separate ranges in context.

**Overlapping or missing partition ranges:** inconsistent inclusive/exclusive conventions. Test partitioner coverage and non-overlap.

**Partition names changing across restarts:** old metadata may bind to a different data region. Keep names and ranges stable for the same job instance.

**Scaling workers past the connection pool:** multiple threads wait on the database, lowering throughput and increasing timeouts. Align concurrency with resources.

**Assuming all partitions commit atomically:** each worker/chunk has its own transaction. Successful partitions still retain committed data if another partition fails.

**Not handling duplicate messages in remote mode:** brokers can redeliver. Workers and writes must be idempotent.

**Not distinguishing remote partitioning from remote chunking:** the two models split read/dispatch responsibilities differently. Choose based on where reading should occur.

## 22. Choosing PartitionHandler in production

First, determine whether data can be split into independent subsets and whether a stable partitioning key exists. Design the `Partitioner` so regions cover the input, do not overlap, and are reproducible on restart. Place boundaries and required identifiers into each partition's `ExecutionContext`.

If workers run on the same machine, start with `TaskExecutorPartitionHandler` and a bounded thread pool. Measure throughput, database connection usage, lock waits, heap, and per-partition durations before increasing grid size. If you need to scale across multiple processes/machines, evaluate remote partitioning with message channels, a broker, a shared metadata repository, and worker monitoring.

Keep the worker step stateless at the singleton level or use `@StepScope` for components needing partition-specific data. Ensure writers have proper transactions/idempotency, reader checkpoints are persisted accurately, and partition names are stable. Test single-worker failures, restarts, and message redelivery before deploying to production.

`PartitionHandler` is the execution point of the partitioning model: it takes worker executions created by the splitter and runs them according to a local or remote strategy. Combined properly with a partitioner, worker step, grid size, and metadata repository, the application can cleanly distribute batch work, scale concurrency under control, and recover individual partitions after failures.
