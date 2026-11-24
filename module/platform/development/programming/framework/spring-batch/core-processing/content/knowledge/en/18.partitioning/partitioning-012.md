# Partitioning limitations in the core module

In Spring Batch, **partitioning** splits a large step into multiple independent data subsets. Each subset is processed by a worker step with its own `StepExecution` and `ExecutionContext`. This organization allows multiple workers to process in parallel, increasing throughput for batch jobs whose data can be safely partitioned.

Partitioning in Spring Batch Core provides abstractions for splitting work scopes, creating executions per partition, and coordinating workers. However, core does not automatically solve all challenges of distributed processing. The application must still define how data is split, ensure partitions do not overlap, manage shared resources, design restarts, and control limits of the database or target systems.

Understanding these limitations helps you select the right concurrency model and avoid expecting that simply increasing `gridSize` will automatically make batch jobs faster or run across multiple machines.

## 1. What does partitioning in Spring Batch Core do?

Partitioning breaks a step's work into smaller units. One step acts as a manager creating partitions; each partition is executed by a worker step. Worker steps can use the same step definition while receiving different `ExecutionContext`s to process separate data ranges.

For example, a job needs to process one million customers. Instead of one worker reading and updating all data, the manager can split IDs into multiple intervals:

```text
managerStep
    |
    +-- partition0: customer_id 1      - 100000
    +-- partition1: customer_id 100001 - 200000
    +-- partition2: customer_id 200001 - 300000
    +-- partition3: customer_id 300001 - 400000
    +-- ...
             |
             v
       workerStep runs on each partition
```

Each partition receives data describing its processing scope, usually stored in an `ExecutionContext`. The worker step reads that scope and performs its work using a reader, processor, writer, or tasklet.

Key abstractions include:

| Component | Role |
|---|---|
| `Partitioner` | Produces partition names and `ExecutionContext`s describing each partition's data/range. |
| Manager step | Coordinates splitting the step into multiple partitions. |
| Worker step | Performs work for one partition. |
| `StepExecutionSplitter` | Creates `StepExecution`s for partitions based on status and metadata. |
| `PartitionHandler` | Coordinates how worker steps execute, such as in the same process or via a custom distribution mechanism. |
| `JobRepository` | Stores metadata of the manager step and worker `StepExecution`s. |
| `ExecutionContext` | Holds partition-specific parameters and state needed for restart. |

Partitioning focuses on splitting and coordinating step units. It does not automatically decide business rules for splitting data; that belongs to `Partitioner` and application design.

## 2. Key limitation: Core does not split business data automatically

Spring Batch Core provides the `Partitioner` interface, but the application must implement how data is divided. For example, with a customer table, the application may split by ID range, geographic region, customer code, or hash bucket.

The interface looks like:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

`gridSize` is a hint for the desired partition count passed to the partitioner. Implementations can use this value to calculate ranges, though the actual partition count depends on application logic. Core does not verify that ranges cover all data or do not overlap.

Example partitioner splitting an ID range:

```java
@Component
public class CustomerRangePartitioner implements Partitioner {

    private final CustomerRepository repository;

    public CustomerRangePartitioner(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        long minId = repository.findMinId();
        long maxId = repository.findMaxId();

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        long total = maxId - minId + 1;
        long targetSize = (long) Math.ceil((double) total / gridSize);

        for (int i = 0; i < gridSize; i++) {
            long start = minId + i * targetSize;
            long end = Math.min(maxId, start + targetSize - 1);
            if (start > maxId) {
                break;
            }

            ExecutionContext context = new ExecutionContext();
            context.putLong("minCustomerId", start);
            context.putLong("maxCustomerId", end);
            partitions.put("customerPartition" + i, context);
        }

        return partitions;
    }
}
```

This example illustrates creating contexts. In real applications, handle empty tables, sparse IDs, data mutating while fetching min/max, and splitting strategies for load balancing. Arithmetic interval splitting does not guarantee equal record counts per partition if IDs are sparse or unevenly distributed.

### Requirements the partitioner must guarantee

- Each record requiring processing belongs to exactly one partition if business rules demand exactly-once processing.
- No records within the target scope are missed.
- Partition names remain stable between initial runs and restarts of the same unit of work.
- `ExecutionContext` holds enough information for the worker to determine its exact data range.
- Data used to build partitions is consistent with the dataset workers actually read.

If the partitioner creates overlapping ranges, multiple workers may update the same record. If gaps exist, part of the data will go unprocessed. Spring Batch persists and coordinates whatever partitions the application creates, but cannot know which business rules are correct.

## 3. Limitations of gridSize

`gridSize` is typically understood as the desired partition count or granularity requested by the manager. It does not equal a guaranteed number of concurrently running threads, nor is it a setting that automatically scales processing machines.

For example, the manager step has `gridSize(8)` while the executor only has 4 worker threads. Partitions are then processed in waves, with at most 4 tasks running concurrently per executor capacity. Conversely, if the partitioner creates only 5 partitions despite grid size 8, only 5 worker executions are created.

```text
gridSize = 8
partitioner creates 8 partitions
executor pool size = 4

Wave 1: partitions 0, 1, 2, 3 run
Wave 2: partitions 4, 5, 6, 7 run
```

The number of concurrently running workers is also bounded by:

- Thread pool size or `PartitionHandler` capacity.
- Connections available from the connection pool.
- Concurrent processing capacity of the database and target systems.
- CPU, memory, I/O, and resources of the batch host.
- Actual partition count returned by `Partitioner`.
- Concurrency limits imposed by the application or deployment platform.

Increasing `gridSize` can increase `StepExecution` count, metadata, queries, and coordination overhead. If downstream resources are already saturated, adding partitions only causes more workers to contend for the same resources and can lengthen total runtime.

## 4. Local partitioning is not automatically remote partitioning

A commonly misunderstood limitation is that partitioning in core does not automatically distribute workers across multiple machines. When configuring the manager with a normal `TaskExecutor`, partitions typically run on threads within the same JVM/process.

Example local partitioning configuration in Spring Batch 5:

```java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner("customerWorkerStep", customerPartitioner)
            .step(customerWorkerStep)
            .gridSize(8)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`partitionTaskExecutor` must be configured separately, usually as a bounded thread pool. Workers still execute within the same application and share resources provided by the application context.

If workers must run across multiple processes or machines, an appropriate transport and coordination mechanism is required. You can use remote partitioning with Spring Integration/messaging or a custom `PartitionHandler`. Sending messages, receiving replies, handling disconnected workers, ensuring delivery, and monitoring nodes constitute additional infrastructure; simply setting `gridSize` or `TaskExecutor` does not provide network distribution.

## 5. Core does not automatically load-balance across partitions

The Partitioner typically builds the partition list before workers execute. If data is unevenly divided, some workers finish quickly while one huge partition runs for a long time.

Example:

```text
Partition 0: 10,000 records  -> completes in 10 seconds
Partition 1: 10,000 records  -> completes in 11 seconds
Partition 2: 10,000 records  -> completes in 12 seconds
Partition 3: 90,000 records  -> completes in 95 seconds
```

Total time is dominated by the slowest partition plus coordination overhead. In the basic partitioning model, core does not dynamically split an active partition into smaller pieces or migrate items from a slow worker to a fast worker.

Ways to improve balance:

- Split by estimated record count rather than evenly dividing ID ranges alone.
- Use histograms or data distribution statistics to choose boundaries.
- Choose a partitioning key with relatively even distribution.
- Create more smaller partitions than workers to reduce time-skew impact, within metadata and scheduling cost limits.
- Isolate exceptionally heavy data groups into dedicated partitions.
- Measure actual duration per partition and adjust the splitting strategy in subsequent runs.

Creating too many partitions also carries overhead. Each partition generates execution metadata, requires worker setup, and may issue extra queries. Find a balanced granularity based on data size and actual processing times.

## 6. Partitioning requires independently divisible input data

Partitioning shines when ranges can be processed independently. If partition A's result depends on partition B's result, or a global processing order is required, parallel execution can alter business semantics.

For example, calculating total revenue per customer can be partitioned by customer ID if each customer belongs to only one partition. However, computing an account balance from a chronological transaction stream by splitting transactions randomly by ID can break required ordering.

Before partitioning, determine:

- Can an item be processed independently?
- Is there an ordering requirement across items?
- Could two partitions update the same aggregate or the same record?
- Is there shared data requiring locking or synchronization?
- If one partition fails, can already-committed partitions remain or must they be compensated?

If work has ordering dependencies, you may need to partition by independent business group (such as by account) and preserve ordering within each group. If independent ranges cannot be formed, partitioning may not be the right choice.

## 7. Shared resources can become bottlenecks

In local partitioning, workers run concurrently in the same JVM. Multiple workers can share singleton beans, datasources, connection pools, file systems, caches, or API clients. Not every resource is safe under concurrent access.

Common risks:

- Readers or writers holding internal state like cursors, file positions, or buffers without thread safety.
- Multiple workers writing to the same file without output partitioning.
- Multiple workers updating the same row or set of tables, causing lock contention/deadlocks.
- Connection pool lacking enough connections for running workers.
- External APIs enforcing rate limits, causing workers to wait or be throttled.
- Shared mutable caches or counters suffering race conditions.

Create resources scoped appropriately to each `StepExecution` or partition. Stateful readers/writers usually need `@StepScope` so each worker gets its own instance and parameters. However, `@StepScope` does not automatically make all internal dependencies thread-safe; injected singleton services or clients may still be shared.

Example reader receiving partition range via Step ExecutionContext:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minCustomerId']}") Long minId,
        @Value("#{stepExecutionContext['maxCustomerId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .selectClause("select id, name")
            .fromClause("from customer")
            .whereClause("where id between :minId and :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new CustomerInput(
                    rs.getLong("id"), rs.getString("name")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

In this example, each worker reads a separate ID range. Ensure `minId` and `maxId` are computed accurately and the reader is genuinely instantiated within the worker step's scope.

## 8. The database can limit scalability

Partitioning increases worker count, but it does not automatically increase database processing capacity. If all workers read from and write to the same database, the database can become a bottleneck before application CPU saturates.

Common limits:

- Connection pool lacks sufficient connections for workers.
- Each partition's query scans the same large table due to missing indexes or suboptimal filters.
- Workers update related rows, causing lock contention or deadlocks.
- Multiple partitions insert into a hot index or shared sequence/summary table.
- Database I/O, CPU, or redo/WAL log writer saturates.
- Long-running transactions hold locks and increase latency for online traffic.

Do not size the thread pool larger than database capacity just because the application host still has CPU headroom. Measure connection waits, query latency, lock waits, deadlocks, I/O, and commit times as concurrency increases.

If each partition needs a concurrent connection, the connection pool must support workers alongside other application activity. Yet raising pool size too high can overload the database with too many active sessions. Worker count and connection pool must be tuned together within database limits.

## 9. ExecutionContext should hold only small metadata

Partitioner returns an `ExecutionContext` for each partition. Context usually contains data bounds, file names, partition codes, or parameters needed for the worker to identify its work.

Example:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minCustomerId", 100001L);
context.putLong("maxCustomerId", 200000L);
context.putString("regionCode", "NORTH");
```

Do not put entire lists of thousands or millions of IDs into ExecutionContext. Context values must be persisted in JobRepository and may require serialization/deserialization. Large payloads inflate metadata size, slow down reads/writes, and strain the repository.

For large datasets, store partitioning data or ID lists in a database, file, or object storage and put a reference key in context. Never store objects that cannot be safely serialized, such as `Connection`, `ResultSet`, `InputStream`, service beans, or entity managers.

## 10. Restarts require stable partition identity

Spring Batch persists a separate `StepExecution` for each partition. When a job fails and is restarted, the framework uses metadata to identify completed partitions, failed partitions, and partitions needing re-execution.

This relies on partition names and the data they represent remaining stable. If a restart produces different partition names or shifted data boundaries, the framework may fail to map old metadata back to the original work.

Example first run:

```text
customerPartition0: ID 1      - 100000  COMPLETED
customerPartition1: ID 100001 - 200000  FAILED
customerPartition2: ID 200001 - 300000  COMPLETED
```

When restarting the same JobInstance, completed partitions can be skipped; the failed partition reruns per state and configuration. If the partitioner changed how ranges split between runs—say partition1 now covers IDs 150001-250000—the old status no longer describes the new range.

For reliable restarts:

- Use partition names with deterministic rules.
- Keep the mapping from partition name to data range identical within the same JobInstance.
- Use identifying JobParameters to pin the batch, business date, or input snapshot.
- Do not modify source files or datasets between the initial run and restart.
- Persist worker-specific checkpoints via readers/writers supporting `ItemStream`.
- Ensure writers are safe when uncommitted items are reprocessed.

`PartitionNameProvider` can be used in some cases to supply previously generated partition names without recomputing every context on restart. However, it does not replace the requirement to keep each partition's data semantics stable; the application must still ensure workers restore the exact same range.

## 11. Partitioning does not create a global transaction

Each worker step manages its own transactions for its chunks or tasklets. Partitions do not participate in a single distributed transaction by default.

For example, four partitions running concurrently:

```text
partition0: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
partition1: chunk 1 COMMIT, chunk 2 FAILED
partition2: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
partition3: chunk 1 COMMIT, chunk 2 COMMIT, COMPLETED
```

When partition1 fails, committed chunks of partition1 and committed data from other partitions do not automatically roll back. JobRepository records each worker's status so incomplete work can be restarted.

If business requirements demand all partitions succeed or no changes take effect, design a compensation strategy or staging/publish workflow. Write results to a staging area tagged by batch ID and promote/publish only after all partitions complete. Do not assume partitioning provides job-wide atomicity.

## 12. Failures and retries at the partition level

A partition can fail due to data errors, database errors, timeouts, or processor/writer exceptions. The overall manager step reflects worker outcomes per the coordination mechanism. Distinguish between:

- Retrying a single item within a chunk.
- Retrying read/write operations in a fault-tolerant step.
- Restarting a failed worker `StepExecution`.
- Restarting the entire manager step/job.

These are distinct recovery levels. Increasing retry limits in a worker will not fix a partitioner that split data incorrectly. Restarting the manager does not guarantee non-transactional side effects are undone.

Workers must log the partition name or batch reference so the failing partition can be located. During incident triage, inspect that partition's `StepExecution`, counters, exceptions, and checkpoints rather than looking only at the manager step's aggregate status.

## 13. Metadata and JobRepository limits

Each partition generates execution metadata in JobRepository. When partition counts grow large, `StepExecution` rows, status updates, and checkpoints grow too. The repository can become a bottleneck if many workers write metadata at high frequency.

Factors to weigh:

- Number of partitions per JobExecution.
- Frequency of ExecutionContext/checkpoint updates.
- Serialized context size.
- Number of workers updating metadata concurrently.
- Indexes and performance of Spring Batch metadata tables.
- Execution history retention and cleanup policy.

Do not create one partition per record when data can be grouped into larger ranges. Excessive partition counts add scheduling and metadata overhead without necessarily improving throughput.

JobRepository must be durably configured and used consistently between manager and workers. In remote partitioning, workers must see the appropriate metadata/repository so execution states are managed properly. If nodes write to isolated repositories without synchronization, tracking and restarts become unreliable.

## 14. Remote partitioning requires extra infrastructure

In remote partitioning, the manager sends partition execution requests to other worker processes via middleware or messaging. Workers receive requests, run the step, and return results. This is a distributed model, not an out-of-the-box feature obtained solely from the core partitioning API.

The application must additionally solve:

- Message transport and routing to workers.
- Serialization of requests and contexts.
- Worker registration, availability, and health checks.
- Retries when message send/receive fails.
- Handling duplicate messages or workers dying mid-flight.
- Ensuring the manager receives final outcomes.
- Shared JobRepository or compatible metadata mechanisms.
- Managing code/config version compatibility between manager and workers.
- Securing transport channels and data access.

If a worker receives a message twice, ensure the same partition does not produce duplicate business side effects. Stable partition/execution identifiers and appropriate idempotency mechanisms are required.

Remote partitioning fits when each worker reads its own data slice from the source and processes independently. If the manager reads data and dispatches chunks to workers, remote chunking may fit better. The two models differ in where reading occurs and how chunks are coordinated.

## 15. Partitioning vs. multi-threaded step and remote chunking

Spring Batch offers several ways to scale concurrency. Picking the wrong model adds complexity without resolving the real bottleneck.

| Model | Work division | Appropriate when |
|---|---|---|
| Multi-threaded step | Multiple threads participate in one step; items/chunks are coordinated per configuration. | Processing logic can run concurrently and shared readers/writers support concurrency. |
| Local partitioning | Splits into multiple `StepExecution`s, each worker receiving an isolated data range in the same process. | Data partitions independently and per-partition state/restarts are needed. |
| Remote partitioning | Manager distributes worker steps/partitions to other processes or nodes. | Scaling workers across processes/machines with messaging infrastructure in place. |
| Remote chunking | Manager reads items and sends chunks to workers for processing/writing. | Reading should stay centralized on the manager while chunks are distributed to workers. |

Partitioning generally helps when each worker can independently read its own data slice. If a single reader must read sequentially before handing items to workers, remote chunking may be a better fit.

## 16. When does partitioning fail to help?

Partitioning may be unsuitable or fail to improve performance when:

- Total data volume is small, so worker startup and metadata overhead exceed processing time.
- Work is bound by a single sequential resource that cannot be split.
- Items depend on global ordering or update the same aggregate.
- The database is already saturated and more workers only increase lock contention.
- One partition holds most of the data, leaving other workers idle.
- Readers/writers are not thread-safe and per-instance creation is too expensive.
- Data ranges cannot be deterministically reproduced across restarts.
- The job requires one atomic transaction spanning the entire dataset.

In these scenarios, optimizing SQL, indexes, chunk size, writer batching, or sequential processing can yield better results. Measure before and after changes rather than assuming concurrency always boosts throughput.

## 17. Workflow for controlled partitioning design

When implementing partitioning in the core module, follow these steps:

1. **Identify independent data units:** choose a key or business group to split by.
2. **Lock the dataset:** use a batch ID, watermark, or snapshot so workers share a stable scope.
3. **Design the partitioner:** generate names and contexts with clear, non-overlapping, gap-free bounds.
4. **Design the worker step:** scope readers/writers per partition and read parameters from Step ExecutionContext.
5. **Choose local or remote:** local when one JVM suffices; remote when extra processes/nodes and distribution infrastructure are genuinely needed.
6. **Tune grid size and executor:** start with modest concurrency, measure database and downstream systems, and adjust.
7. **Control resources:** connection pool, thread pool, files, API rate limits, and shared state.
8. **Design restarts:** keep partition names/ranges stable, enable checkpoints, and use idempotent writers.
9. **Design observability:** log partition name, batch reference, duration, counters, and exceptions.
10. **Measure performance:** compare throughput, slowest partition time, lock waits, connection waits, and metadata overhead.

Do not start with a huge partition count. Run trials at low concurrency levels, observe resources, and scale up gradually while the system retains headroom.

## 18. Common mistakes when using partitioning

| Issue | Possible cause | Remediation |
|---|---|---|
| Increasing grid size does not speed up the job | Executor, database, or target system is already the bottleneck. | Measure actual concurrency and bottlenecks before scaling up. |
| Records processed twice | Partitions have overlapping ranges or workers retry side effects. | Check partitioner bounds and use keys/idempotency for writes. |
| Records missed | Partition boundaries have gaps or the dataset mutated during splitting. | Verify full range coverage, snapshots, and watermarks. |
| One worker runs much longer | Skewed data distribution or uneven partition complexity. | Split by estimated count/volume and adjust based on metrics. |
| Restart produces different partitions than first run | Unstable partition names/ranges or mutated source data. | Keep partition identity and dataset fixed within the same JobInstance. |
| Race condition errors | Workers share non-thread-safe mutable readers/writers/caches. | Instantiate per partition, synchronize, or partition resources. |
| Database overload | Too many workers querying/updating concurrently. | Reduce concurrency, optimize queries/indexes, and size connection pool. |
| JobRepository under heavy load | Too many partitions or oversized contexts/checkpoints. | Reduce partition count, keep contexts small, and optimize metadata retention. |
| Remote worker does not update status | Messaging/responses or repository configured inconsistently. | Check transport, retries, worker health, and metadata repository. |
| One partition fails while other data commits | Each worker has its own transaction, with no global transaction. | Design restarts, staging, or business compensation. |

## 19. Key points to remember

- Partitioning splits a step into multiple worker executions, each with its own `StepExecution` and `ExecutionContext`.
- Spring Batch Core provides the coordination mechanism; the application must design business-correct data splitting.
- `gridSize` is a partition-count hint, not a guaranteed number of concurrent threads or machines.
- `TaskExecutor` typically yields local partitioning within one process; remote partitioning requires transport and additional infrastructure.
- Core does not rebalance running partitions automatically; skewed data makes the slowest partition dictate total runtime.
- Workers need independent data ranges, stable partition names, and resources sized to concurrency.
- The database, connection pool, API rate limits, CPU, I/O, and JobRepository can all constrain scalability.
- ExecutionContext should hold small, serializable metadata sufficient for workers to identify their scope.
- Partitions have independent transactions; one failing partition does not roll back committed data from other partitions.
- Restarts depend on partition identity, checkpoints, stable source data, and writers capable of safe reprocessing.
- Partitioning differs from multi-threaded steps and remote chunking; choose based on where reads happen and how work divides.
- Measure actual throughput and bottlenecks before increasing partition or worker counts.

Partitioning in Spring Batch Core is a mechanism for splitting and coordinating work, not an automatic cure for every scaling problem. To be effective, the application must split data accurately, keep workers isolated, manage shared resources, maintain stable metadata/restarts, and measure target-system limits. Only when those conditions are met does partitioning increase concurrency while keeping batch outcomes observable and recoverable.
