# Range partitioning

**Range partitioning** splits data into multiple non-overlapping value intervals based on an ordered key, then assigns each interval to a worker Step for independent processing. In Spring Batch, this approach is commonly used when processing large database datasets across multiple parallel partitions.

For example, an orders table has IDs from 1 to 1,000,000. It can be split into four intervals:

| Partition | ID Range |
|---|---:|
| partition0 | 1–250,000 |
| partition1 | 250,001–500,000 |
| partition2 | 500,001–750,000 |
| partition3 | 750,001–1,000,000 |

Each worker reads only data belonging to its assigned interval. When intervals are designed properly, each record belongs to at most one partition and the entire target dataset is covered.

Range partitioning helps distribute processing load, utilize multiple threads or machines, and track per-partition progress separately. Effectiveness depends on the partitioning key, interval-splitting method, data distribution, and database resources.

## 1. Range partitioning in Spring Batch

Spring Batch supports partitioning through three components:

- **Partitioner** creates partitions and provides a dedicated ExecutionContext for each partition.
- **Partition manager Step** coordinates creating and running worker Steps.
- **Worker Step** performs work on its assigned data range.

~~~text
                  Manager Step
                       |
                       v
              Partitioner.partition()
                       |
          +------------+------------+
          |            |            |
          v            v            v
      Context 0    Context 1    Context 2
          |            |            |
          v            v            v
      Worker 0     Worker 1     Worker 2
      ID 1-100     ID 101-200   ID 201-300
          |            |            |
          v            v            v
       Result       Result       Result
          +------------+------------+
                       |
                       v
              Manager Step completes
~~~

In range partitioning, Partitioner typically queries the minimum and maximum key values, divides the key domain into intervals, and stores lower and upper bounds in ExecutionContext.

The Worker Step reads these values to restrict its query. Because each partition has its own StepExecution and Step ExecutionContext, workers can save checkpoints and restart independently.

## 2. When should range partitioning be used?

Range partitioning fits when:

- Data has a clearly ordered key, usually an incrementing ID or business date.
- Each partition can be represented by lower and upper bounds.
- Workers can process each interval without depending on results from other workers.
- The data source is large enough to split into multiple parts.
- The database can serve key-range queries efficiently.

Examples:

- Processing orders by ID.
- Recalculating transaction statuses by date.
- Exporting customer data by key range.
- Reconciling records by ordered account number or transaction code.
- Migrating historical data by date intervals.

Range partitioning is not always the best choice. If data lacks a suitable ordered key, key distribution is severely skewed, or each record requires results from another partition, this approach may be unbalanced or complicate processing.

## 3. Choosing the partitioning key

The partitioning key determines how data is split and how workers query it.

A good key typically has these traits:

- Comparable and deterministically sortable.
- Appropriately indexed for range queries.
- Populated for most records requiring processing.
- Distributed well enough to create partitions with relatively balanced workloads.
- Does not change arbitrarily while the Job is running or restarting.

Common keys are numeric IDs, timestamps, or business dates. For data with duplicate keys, add a unique tie-breaker key if the partitioning algorithm relies on record order.

If the key can be null, explicitly decide whether those records belong to a separate partition or are handled in another Step. Do not let WHERE clauses accidentally drop them.

### Splitting by key range differs from splitting evenly by record count

Suppose IDs have the values:

~~~text
1, 2, 3, 4, 5, 900000, 900001, 900002, 900003
~~~

If the numeric domain from 1 to 900003 is split in half, the first partition holds 5 records while the second holds 4. In this example the result is still fairly balanced, but when data clusters in one region, two intervals can have vastly different record counts.

Splitting the value domain evenly does not equate to splitting the workload evenly. If balancing by row count is required, use data statistics, percentiles, key milestones obtained from a query, or a pre-built partition coordination table.

## 4. Defining non-overlapping, gap-free boundaries

The most important requirement is that partitions cover the exact target dataset.

There are two common ways to represent intervals:

- **Closed interval**: both start and end are included, e.g. [1, 100].
- **Half-open interval**: includes the lower bound, excludes the upper bound, e.g. [1, 101).

Half-open intervals are convenient when chaining intervals because the previous interval's upper bound is the next interval's lower bound. Closed intervals are also easy to use with SQL queries using BETWEEN predicates.

Example using closed intervals:

~~~sql
SELECT id, status
FROM orders
WHERE id >= :fromId
  AND id <= :toId
ORDER BY id
~~~

Intervals:

~~~text
[1, 100]
[101, 200]
[201, 300]
~~~

No ID falls into two intervals simultaneously, and every ID in the domain 1–300 is covered.

When using BETWEEN, remember both ends are inclusive. Writing two partitions as BETWEEN 1 AND 100 and BETWEEN 100 AND 200 causes ID 100 to be processed twice.

With bounded numeric types like long, avoid computing the next bound using addition that could overflow. Use BigInteger when computing boundaries or design half-open intervals with upper-bound checks. The code example below uses BigInteger to split the ID domain safely and then stores inclusive bounds as long.

## 5. Partitioner creates ExecutionContext for each interval

Partitioner contract:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Each entry in the map represents a partition:

- Key is the partition name, e.g. partition0.
- Value is ExecutionContext holding data the worker needs, e.g. fromId and toId.

Example Partitioner fetching minimum and maximum IDs from a repository:

~~~java
public class OrderRangePartitioner implements Partitioner {

    private static final BigInteger ONE = BigInteger.ONE;

    private final OrderRepository repository;

    public OrderRangePartitioner(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException(
                    "gridSize must be positive");
        }

        Long minId = repository.findMinId();
        Long maxId = repository.findMaxId();

        if (minId == null || maxId == null) {
            return Collections.emptyMap();
        }

        if (minId > maxId) {
            throw new IllegalStateException("Invalid ID range");
        }

        BigInteger min = BigInteger.valueOf(minId);
        BigInteger max = BigInteger.valueOf(maxId);
        BigInteger total = max.subtract(min).add(ONE);

        int partitionCount = total.min(
                BigInteger.valueOf(gridSize)).intValueExact();

        Map<String, ExecutionContext> result =
                new LinkedHashMap<>();

        BigInteger count = BigInteger.valueOf(partitionCount);

        for (int i = 0; i < partitionCount; i++) {
            BigInteger from = min.add(
                    total.multiply(BigInteger.valueOf(i))
                            .divide(count));

            BigInteger toExclusive = min.add(
                    total.multiply(BigInteger.valueOf(i + 1))
                            .divide(count));

            BigInteger toInclusive = toExclusive.subtract(ONE);

            ExecutionContext context = new ExecutionContext();
            context.putLong("fromId", from.longValueExact());
            context.putLong("toId", toInclusive.longValueExact());

            result.put("partition" + i, context);
        }

        return result;
    }
}
~~~

This snippet splits the inclusive integer ID domain from minId to maxId into at most gridSize intervals. BigInteger avoids overflow when computing total domain length and intermediate boundaries. Because every final boundary still lies within the input long domain, longValueExact() converts safely.

When the source is empty, the example returns an empty map so no workers are created. Applications must explicitly define business behavior when there are no records: whether the manager Step completes with no partitions, or an empty partition is created to record an outcome. Choose a consistent policy and test it.

### Why are stable partition names needed?

Partition names are used to identify worker executions in metadata. Using stable names like partition0, partition1 helps Spring Batch correlate executions and restarts.

Do not generate names based on random UUIDs each time the partitioner is called if you want to restart failed partitions. Changing names makes matching against old executions difficult.

## 6. Using ExecutionContext to pass bounds to workers

After Partitioner creates contexts, Spring Batch creates a StepExecution for each partition and attaches the corresponding context.

For example, one partition has:

~~~text
partition1
  fromId = 250001
  toId   = 500000
~~~

The Worker Step can retrieve these values using StepScope and late binding:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return new JdbcCursorItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, status
                FROM orders
                WHERE id >= ?
                  AND id <= ?
                ORDER BY id
                """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, fromId);
                statement.setLong(2, toId);
            })
            .rowMapper((rs, rowNum) ->
                    new OrderInput(
                            rs.getLong("id"),
                            rs.getString("status")))
            .saveState(true)
            .build();
}
~~~

**@StepScope** is required so the reader is created within each worker's StepExecution scope. As each partition runs, fromId and toId are resolved from the corresponding Step ExecutionContext.

If the reader were a singleton created before partitions begin, it could not receive separate bounds per worker and could cause partitions to share a data range.

The reader needs a stable name and saveState(true) to persist per-worker checkpoints for restart. Each worker has its own StepExecution/ExecutionContext, so the same reader name in a StepScope bean still stores state per partition.

## 7. Configuring worker Step and manager Step

The Worker Step contains the data-processing logic for one partition. It does not need to know how the manager created all partitions; it simply reads its assigned range.

~~~java
@Bean
public Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<OrderInput, ProcessedOrder>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

The Manager Step uses Partitioner and worker Step:

~~~java
@Bean
public Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner("orderWorkerStep", orderRangePartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
~~~

In this example:

- orderWorkerStep is the processing logic for each partition.
- orderRangePartitioner generates the ID ranges.
- gridSize(4) requests creating up to four partitions in this design.
- taskExecutor allows the manager to run workers using multiple threads in the same process.

The Manager Step coordinates workers and aggregates their completion statuses. One failing worker can cause the manager Step to fail; other workers may have already completed and persisted their own statuses.

## 8. Configuring TaskExecutor for parallel partitions

ThreadPoolTaskExecutor can be used to run workers in the same JVM:

~~~java
@Bean
public TaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("orders-partition-");
    return executor;
}
~~~

In Spring, ThreadPoolTaskExecutor is managed as a bean and its lifecycle is governed by the container.

Distinguish between:

- **gridSize** controls the number of partitions requested from Partitioner/manager.
- **Pool size** limits how many workers can run concurrently.
- **Chunk size** of the worker controls how many items are in each transaction chunk within a partition.

These three settings have different effects. For example, gridSize of 8 with a 4-thread pool generally executes at most 4 workers concurrently; remaining partitions wait for their turn.

Increasing worker count does not always increase throughput. The database can be overwhelmed by concurrent queries, the connection pool can be exhausted, or writers can contend on locks. Size workers to the capacity of source and target systems.

## 9. How does range partitioning differ from chunk processing?

Chunks and partitions address two different levels of work division:

| Concept | Splits by | Goal |
|---|---|---|
| Chunk processing | Group of items inside one StepExecution | Batch commit/rollback |
| Range partitioning | Data range assigned to independent StepExecutions | Run multiple data subsets in parallel |
| Grid size | Number of partitions created/requested | Distribute work across workers |
| Chunk size | Number of items in one worker chunk | Control transactions and working set |

A partition worker can still use chunk processing. For example, with four partitions each handling 250,000 IDs and a worker chunk size of 500, each worker reads its range in 500-item chunks and commits each chunk separately.

~~~text
Manager
  |
  +--> Partition 0: ID 1-250000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 1: ID 250001-500000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 2: ID 500001-750000
  |       +--> Chunk 1
  |       +--> Chunk 2
  |       +--> ...
  |
  +--> Partition 3: ID 750001-1000000
          +--> Chunk 1
          +--> Chunk 2
          +--> ...
~~~

Partitioning increases parallel processing capacity. Chunk size still governs commit frequency within each worker.

## 10. Range partitioning needs indexed queries

If workers execute the query:

~~~sql
SELECT id, status
FROM orders
WHERE id >= ?
  AND id <= ?
ORDER BY id
~~~

the id column should have an appropriate index, typically a primary key or an index optimized by the database for range predicates and sorting.

Without an index, every worker may perform a full table scan to find its range. When multiple partitions scan simultaneously, total database load can spike instead of reducing runtime.

Check the execution plan against realistic data volumes. If queries include extra predicates such as status or business_date, a composite index whose column order matches both filtering and sorting may be needed.

Also avoid wrapping key columns in functions inside WHERE clauses if it prevents the database from using an index range scan, unless a matching functional index exists.

## 11. Data distribution and unbalanced partitions

Range partitioning divides by key domain. If data distribution is skewed, workers can receive vastly different amounts of data.

Example:

~~~text
ID 1 - 100000       : 800,000 records
ID 100001 - 200000 : 100,000 records
ID 200001 - 300000 :  50,000 records
ID 300001 - 400000 :  50,000 records
~~~

If each partition covers 100,000 ID units, the first worker runs significantly longer. Other workers finish early and resources are underutilized.

Ways to improve:

- Use statistics or histograms to determine split points.
- Choose boundaries by record-count percentiles.
- Create a coordination table containing start_key/end_key for each partition.
- Split by date or business group if distribution is better.
- Measure runtime and row counts per partition to adjust future runs.

When balancing by row count is necessary, key milestones can be fetched via ranking queries or window functions, then intervals formed from those milestones. Ensure milestones are unique or have a tie-breaker so duplicate key groups are not split improperly.

## 12. Handling missing IDs and empty intervals

IDs do not need to be contiguous for range partitioning to work.

For example, data has IDs:

~~~text
10, 11, 19, 100, 105, 900
~~~

Intervals [10, 100] and [101, 900] still cover all data. A numeric interval may contain many values without records; that does not cause errors as long as the query returns existing records accurately.

However, if IDs are very sparse or concentrated, some partitions may have zero records. Empty workers finish quickly, yet still consume initialization, metadata, and thread-scheduling overhead.

If data volume is smaller than gridSize, cap partitionCount by key domain length or record count. Capping by key domain length will not eliminate all empty partitions when keys have wide gaps; avoiding those requires relying on actual statistics or key milestones that contain data.

## 13. Data changing while partitions are running

Suppose Partitioner queries minId=1 and maxId=1,000,000 and builds four intervals. While workers are processing, another system inserts record ID=1,000,001.

The new record falls outside the generated ranges and may not be processed in the current Job. If records are deleted or change status, some workers may read fewer rows than expected.

For consistent results, define the Job's dataset:

- Capture a watermark or upper bound at start time.
- Filter by business date or period.
- Use an appropriate snapshot or isolation level if consistent reads are required.
- Put snapshot ID, processing date, or watermark into JobParameters if it identifies the unit of work.
- Avoid mutating source data in ways that shift range membership while the Job runs.

A common strategy is fetching minId and maxId at start time, storing them in metadata or Job ExecutionContext, and building partitions from those locked values. On restart, reuse that run's ranges rather than recomputing against newer data if doing so would change the dataset.

## 14. Partition restarts

Each partition has its own StepExecution and ExecutionContext. Therefore, Spring Batch can track which partitions completed, which failed, and each worker's reader checkpoint.

~~~text
orderManagerStep
   |
   +--> partition0: COMPLETED
   |       separate checkpoint
   |
   +--> partition1: FAILED
   |       checkpoint after chunk 12
   |
   +--> partition2: COMPLETED
   |       separate checkpoint
   |
   +--> partition3: COMPLETED
           separate checkpoint
~~~

When restarting the JobInstance:

- Completed partitions are typically skipped.
- Failed partitions can be restarted from the worker's checkpoint.
- Readers must support ItemStream and save state.
- JobRepository must persist metadata durably.
- Partition names and data ranges must stay stable across runs.

If gridSize, interval-splitting algorithm, or input data changes between the initial run and restart, new partitions may no longer correspond to old StepExecutions. Keep partitioning configuration consistent for the same JobInstance or design an explicit migration/restart strategy.

If the source changes, restarting from an old checkpoint may no longer reflect the same dataset. Use snapshots or watermarks to define a stable processing scope.

## 15. Partition context and StepScope

ExecutionContexts created by Partitioner are attached to worker StepExecutions. To use those values, readers, processors, or writers usually require StepScope.

Example processor reading a partition-specific processing mode:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, ProcessedOrder> orderProcessor(
        @Value("#{stepExecutionContext['region']}") String region) {

    return order -> processForRegion(order, region);
}
~~~

Partition values can include:

- fromId and toId.
- fromDate and toDate.
- region or tenant.
- partition input file name.
- batch code or snapshot ID.

Do not store the entire list of partition items in ExecutionContext. Context should hold small configuration and checkpoint information, not large data payloads.

If multiple partitions share a mutable singleton bean, they can overwrite each other's state. Use StepScope for components holding partition-specific state and avoid sharing non-thread-safe mutable objects.

## 16. Range partitioning and remote partitioning

Range partitioning describes **how data is split**, while local or remote partitioning describes **where workers run**.

- **Local partitioning**: manager runs worker Steps in the same JVM, typically via TaskExecutor.
- **Remote partitioning**: manager dispatches worker requests over messaging middleware or a distribution mechanism; workers run on different processes/machines.

Both approaches can use ExecutionContext holding ID or date bounds. Workers receive the context and process their assigned range.

With remote partitioning, also consider:

- Serialization of ExecutionContext and messages.
- Retry handling when a worker disconnects.
- Partition identification and duplicate-processing prevention.
- Observability of worker statuses across multiple processes.
- A shared or properly configured JobRepository and metadata store.

Do not mistake using multiple threads in TaskExecutor for remote partitioning. TaskExecutor runs workers inside the same process; remote partitioning requires a mechanism to transport work between manager and workers across different processes.

## 17. Monitoring each partition

When a Job has multiple partitions, checking only the manager Step status is insufficient. Monitor each worker StepExecution.

Useful details:

| Information | Purpose |
|---|---|
| Partition name | Identify which worker |
| StepExecution ID | Query a specific run |
| fromId / toId | Know the assigned data range |
| BatchStatus | Know whether worker is running, completed, or failed |
| readCount / writeCount | Measure read and written data volume |
| commitCount / rollbackCount | Observe worker transactions |
| startTime / endTime | Compare execution durations |
| failureExceptions | Investigate worker errors |

If one partition runs much longer than others, examine data distribution, execution plans, lock contention, writer speed, and auxiliary queries inside the processor.

Logging the partition name alongside the JobExecution ID helps correlate errors with the exact data range. Do not log generic messages like "partition failed" without partition name and execution ID.

## 18. Common mistakes when implementing range partitioning

### Overlapping intervals

Using BETWEEN where the previous partition's upper bound equals the next partition's lower bound causes some records to be processed twice. Use closed intervals with exact next bounds or half-open intervals.

### Gaps between intervals

Incorrect boundary arithmetic, inconsistent rounding, or forgetting records at the max bound can leave data unprocessed. Test the entire domain with values on both sides of every boundary.

### Splitting evenly by ID count with uneven record counts

Skewed data distribution causes one worker to run longer. Use statistics or percentile-based key milestones when balancing is needed.

### Reader ignoring partition context

If a worker queries the full table instead of filtering by fromId/toId, all partitions may read the same data and create duplicate results.

### Reader missing StepScope

A singleton reader may receive one shared set of bounds or retain shared state. Instantiate readers per StepExecution using StepScope when partition values are required.

### Confusing gridSize with chunk size

gridSize is the number of partitions; chunk size is the number of items per worker transaction. Adjusting one does not replace the other.

### Scaling workers past database capacity

Many concurrent queries can exhaust the connection pool, increase locks, or slow down the database. Scale concurrency according to source and target capacity.

### Restarting with different boundaries than the first run

If partition layout changes, old checkpoints may no longer match the data range. Keep configuration and source snapshots stable for the same JobInstance.

### New data falling outside the watermark

Records inserted after Partitioner determines maxId may belong to no partition. Explicitly define the Job's snapshot or watermark.

## 19. Testing Partitioner

Test Partitioner in isolation before running the full Job.

Important test cases:

- gridSize equals 1.
- gridSize greater than values in the domain.
- Empty data.
- Single ID only.
- minId equals maxId.
- Negative IDs or domain spanning negative and positive numbers.
- Very large ID domain near long limits.
- Sparse data with many gaps.
- All partition bounds contiguous without overlaps.
- Stable partition names.

Example verifying generated intervals:

~~~java
@Test
void createsAdjacentNonOverlappingRanges() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.findMinId()).thenReturn(1L);
    when(repository.findMaxId()).thenReturn(100L);

    OrderRangePartitioner partitioner =
            new OrderRangePartitioner(repository);

    Map<String, ExecutionContext> partitions =
            partitioner.partition(4);

    assertEquals(4, partitions.size());

    long expectedFrom = 1L;

    for (ExecutionContext context : partitions.values()) {
        long from = context.getLong("fromId");
        long to = context.getLong("toId");

        assertEquals(expectedFrom, from);
        assertTrue(to >= from);

        expectedFrom = to + 1;
    }

    assertEquals(101L, expectedFrom);
}
~~~

This test assumes the 1–100 domain and 4 partitions. It verifies intervals are contiguous, non-overlapping, and cover through maxId. When maxId is Long.MAX_VALUE, do not use `to + 1` in the assertion; use BigInteger or check the final bound separately.

In addition to Partitioner unit tests, run Step integration tests with data right on the bounds: minId, maxId, and values immediately before and after every boundary. Aggregate IDs read across all partitions and assert no missing or duplicate records.

## 20. Range partitioning design workflow

When building a Job using range partitioning, follow this order:

1. Choose a partitioning key with stable ordering and an appropriate index.
2. Define the Job's dataset using business date, snapshot, or watermark.
3. Query min/max or statistics to determine bounds.
4. Write Partitioner to create ExecutionContexts with explicit bounds.
5. Choose inclusive or half-open convention and apply it consistently in SQL.
6. Create Worker Step reading bounds from Step ExecutionContext via StepScope.
7. Use queries with range predicates and a deterministic ORDER BY.
8. Configure Manager Step, gridSize, and TaskExecutor according to system capacity.
9. Persist per-worker checkpoints to support restarts.
10. Test boundaries, empty data, sparse data, and restart scenarios.
11. Monitor status, row counts, and duration of each partition.
12. Keep partition names, source snapshot, and splitting algorithm stable for the same JobInstance.

Range partitioning works well when workers receive clear, independent ranges of reasonable volume. Partitioner sets boundaries, ExecutionContext passes the range, Worker Step executes queries, and chunk processing manages transactions inside each worker. With non-overlapping boundaries, stable source data, and appropriate concurrency, Spring Batch can process large datasets in parallel while tracking and restarting each partition in a controlled way.
