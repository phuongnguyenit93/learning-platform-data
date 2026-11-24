# Key partitioning

In Spring Batch, key partitioning is a technique for splitting a dataset into multiple parts based on a stable key, typically a primary key or a business key. Each part is assigned to a separate worker Step for independent processing. For example, an `orders` table can be partitioned by `order_id` into key ranges; each partition reads only the orders falling within its range.

Key partitioning is typically implemented using `Partitioner`. The partitioner creates an `ExecutionContext` for each partition, storing values such as the start key and end key. Spring Batch creates one `StepExecution` per partition and runs the same worker Step with the corresponding context. Consequently, each worker can use a `@StepScope` reader to obtain its own key range.

## 1. What problem does key partitioning solve?

A typical chunk Step reads the entire dataset in a single execution stream. For large datasets, execution time can be long and it is hard to leverage multiple independent workers. Partitioning splits the work into multiple smaller StepExecutions, each processing a subset of the data.

For example, a table has 1,000,000 orders. It can be divided by `order_id` into four regions:

```text
orders dataset
      |
      +-- Partition 0: order_id [1, 250001)
      |
      +-- Partition 1: order_id [250001, 500001)
      |
      +-- Partition 2: order_id [500001, 750001)
      |
      +-- Partition 3: order_id [750001, 1000001)
```

Each worker reads only rows within its interval. Workers can run sequentially or in parallel depending on TaskExecutor and infrastructure configuration.

Key partitioning is useful when:

- Data has a stable key and can be divided into non-overlapping ranges.
- Each item can be processed independently of items in other partitions.
- The data source supports efficient key-based queries, especially when the key is indexed.
- You want to increase throughput by processing multiple partitions concurrently.
- You need to track and restart the progress of each partition individually.

Partitioning does not make a slow query fast if the database lacks capacity. It divides work and enables concurrency; actual performance depends on indexes, query plans, database load, transactions, writers, and worker count.

## 2. How does key partitioning differ from chunk processing?

Chunk processing and partitioning address two different levels:

- **Chunk processing** divides a Step's work into chunks, each with its own transaction and commit boundary.
- **Partitioning** divides the entire input into multiple work ranges; each range is executed by a separate StepExecution. Inside each worker Step, chunk processing can still be used.

```text
Manager Step
   |
   +-- Partition A --> Worker Step A --> Chunk 1, Chunk 2, ...
   |
   +-- Partition B --> Worker Step B --> Chunk 1, Chunk 2, ...
   |
   +-- Partition C --> Worker Step C --> Chunk 1, Chunk 2, ...
```

Each worker typically uses the same Step definition while receiving a different `ExecutionContext`. Each worker has its own `StepExecution`, counters, transactions, and checkpoints. Thus, partitioning determines *which slice of data* a worker processes, whereas chunking determines *in what item groups* the worker commits.

## 3. Partitioner and ExecutionContext

The `Partitioner` interface is responsible for creating partitions:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Each entry in the map consists of:

- Map key: partition name, e.g. `orders-partition-0`.
- Value: `ExecutionContext` containing parameters specific to the partition.

For key range partitioning, the context usually holds:

| Key in ExecutionContext | Meaning |
|---|---|
| `minIdInclusive` | Start key, included in the partition. |
| `maxIdExclusive` | End key, excluded from the partition. |
| `partitionNumber` | Partition sequence number for logging or observability. |

Using half-open intervals `[minIdInclusive, maxIdExclusive)` ensures two adjacent partitions do not overlap: the preceding partition ends at `x` without including `x`, and the following partition starts at `x` and includes `x`.

Example:

```text
Partition 0: id >= 1   AND id < 101
Partition 1: id >= 101 AND id < 201
Partition 2: id >= 201 AND id < 301
```

These intervals do not overlap and have no gaps between them. Even if keys in the table have gaps, any row with a valid key still belongs to at most one partition.

## 4. Creating a key range partitioner

The following example splits the `orders` table by integer key `order_id`. The partitioner queries the minimum and maximum keys, then divides the key domain into intervals of roughly equal width.

```java
public class OrderIdRangePartitioner implements Partitioner {

    private final JdbcTemplate jdbcTemplate;

    public OrderIdRangePartitioner(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Long minId = jdbcTemplate.queryForObject(
                "select min(order_id) from orders", Long.class);
        Long maxId = jdbcTemplate.queryForObject(
                "select max(order_id) from orders", Long.class);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        if (minId == null || maxId == null) {
            ExecutionContext emptyContext = new ExecutionContext();
            emptyContext.putLong("minIdInclusive", 0L);
            emptyContext.putLong("maxIdExclusive", 0L);
            emptyContext.putInt("partitionNumber", 0);
            result.put("orders-partition-0", emptyContext);
            return result;
        }

        long maxIdExclusive = Math.addExact(maxId, 1L);
        long keyRange = Math.subtractExact(maxIdExclusive, minId);
        int partitionCount = (int) Math.min((long) gridSize, keyRange);

        long baseSize = keyRange / partitionCount;
        long remainder = keyRange % partitionCount;
        long nextStart = minId;

        for (int i = 0; i < partitionCount; i++) {
            long size = baseSize + (i < remainder ? 1 : 0);
            long endExclusive = Math.addExact(nextStart, size);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", nextStart);
            context.putLong("maxIdExclusive", endExclusive);
            context.putInt("partitionNumber", i);

            result.put("orders-partition-" + i, context);
            nextStart = endExclusive;
        }

        return result;
    }
}
```

The example assumes `order_id` is an integer key whose domain fits in `long`, `maxId + 1` does not exceed the type limit, and the entire key span does not overflow. `Math.addExact`/`subtractExact` detects overflow instead of silently producing invalid bounds. For wider key domains or different types, use an appropriate range-calculation strategy.

If the table is empty, the example creates one empty partition with range `[0, 0)` so a worker runs and reads zero items. An application can alternatively choose dedicated handling for a no-data Job, provided the flow and expected outcome are explicitly defined.

## 5. Why use half-open intervals?

Suppose data is split into three intervals:

| Partition | SQL Predicate | Property |
|---|---|---|
| A | `id >= 1 AND id < 101` | Fetches 1 through 100. |
| B | `id >= 101 AND id < 201` | Fetches 101 through 200. |
| C | `id >= 201 AND id < 301` | Fetches 201 through 300. |

Using inclusive bounds on both ends (`BETWEEN 1 AND 100`, `BETWEEN 100 AND 200`) causes key 100 to appear in two partitions. Using exclusive bounds on both ends causes boundary keys to be missed.

Half-open intervals follow a simple rule:

```sql
WHERE order_id >= :minIdInclusive
  AND order_id <  :maxIdExclusive
```

This predicate is easy to chain and test. For date/time or string keys, half-open intervals can also be used if comparison and collation are deterministically defined.

## 6. Wiring the Partitioner into the manager Step

A partitioned Step has two roles:

- **Manager Step:** creates partitions, coordinates workers, and aggregates results.
- **Worker Step:** performs the actual work on data belonging to its assigned partition.

Example manager Step configuration in Spring Batch 5:

```java
@Bean
Partitioner orderIdPartitioner(JdbcTemplate jdbcTemplate) {
    return new OrderIdRangePartitioner(jdbcTemplate);
}

@Bean
Step partitionedOrderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderIdPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("partitionedOrderManagerStep", jobRepository)
            .partitioner("orderWorkerStep", orderIdPartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`.partitioner("orderWorkerStep", orderIdPartitioner)` specifies the worker Step name and the Partitioner. `.step(orderWorkerStep)` provides the worker definition. `.gridSize(4)` requests creating around four partitions in this example; actual partitions may be fewer if the Partitioner returns fewer entries.

`gridSize` is a hint/grid size for splitting, not a guarantee that four threads run concurrently. Concurrency depends on the TaskExecutor and resource limits.

## 7. Running partitions in parallel with TaskExecutor

To run partitions concurrently within the same JVM, the manager Step can use a `TaskExecutor`:

```java
@Bean
TaskExecutor partitionTaskExecutor() {
    SimpleAsyncTaskExecutor executor =
            new SimpleAsyncTaskExecutor("orders-partition-");
    executor.setConcurrencyLimit(4);
    return executor;
}
```

In this example, the concurrency limit is four tasks. `ThreadPoolTaskExecutor` can be used to control core/max pool sizes, queue capacity, and thread naming per operational policy.

Distinguish between:

- Number of partitions created: returned by Partitioner, related to `gridSize`.
- Number of partitions running concurrently: governed by TaskExecutor and resource limits.
- Number of chunks per partition: governed by chunk size or CompletionPolicy of the worker Step.

If there are 16 partitions while the executor allows only 4 threads, partitions are processed across multiple batches. Increasing thread count does not always increase throughput; the database can become a bottleneck due to too many concurrent queries and transactions.

## 8. Worker Step receives partition keys

The Worker Step uses the partition's dedicated `ExecutionContext`. Values in context can be injected into `@StepScope` beans via SpEL:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT order_id, customer_id, amount
                    FROM orders
                    WHERE order_id >= ? AND order_id < ?
                    ORDER BY order_id
                    """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, minId);
                statement.setLong(2, maxId);
            })
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .saveState(true)
            .build();
}
```

`@StepScope` is critical here. The Worker Step is reused for multiple partitions; each StepExecution must receive the exact two key bounds for that partition. If the reader were a singleton holding `minId`/`maxId` in fields, workers could use each other's ranges by mistake.

The reader uses parameterized SQL rather than string concatenation. This avoids quoting bugs and lets the database reuse prepared statements. The `order_id` column should have an appropriate index for efficient range scans.

## 9. Declaring worker Step and Job

The Worker Step can be a regular chunk-oriented Step. It differs only in that the reader is bounded by the partition context:

```java
@Bean
Step orderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("orderWorkerStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(partitionOrderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}

@Bean
Job partitionedOrderJob(
        JobRepository jobRepository,
        Step partitionedOrderManagerStep) {

    return new JobBuilder("partitionedOrderJob", jobRepository)
            .start(partitionedOrderManagerStep)
            .build();
}
```

In this example, each partition has a worker StepExecution that processes chunks of 200 items. Ensure stateful beans are `@StepScope` or appropriately thread-safe. Writers shared across workers must support concurrent use or be scoped separately.

## 10. Types of key partitioning

Numeric key range partitioning is common, though not the only approach.

### Range partitioning

Each worker receives a key interval:

```sql
WHERE id >= :lowerBound AND id < :upperBound
```

Suitable when keys are ordered and indexed in the database. Monitor data distribution because equal key spans do not necessarily have equal row counts.

### Hash/modulo partitioning

Data can be split by key remainder:

```sql
WHERE MOD(order_id, :partitionCount) = :partitionNumber
```

Buckets generally do not overlap and can distribute fairly evenly if keys are well distributed. However, applying functions to columns can prevent the database from using normal index range scans; modulo syntax and negative-number rules depend on the database. Check the execution plan and ensure the same hash algorithm is used consistently across restarts.

### Partitioning by key list or business group

If data is divided by tenant, region, customer group, or business unit, each partition can receive a key value:

```sql
WHERE tenant_id = :tenantId
```

Suitable when business keys form natural independent groups. If the key list is very large, do not place the entire list of keys into a single ExecutionContext; store a reference to the partition list or use a bucketing strategy.

## 11. Choosing an appropriate partition key

A good key satisfies these traits:

- **Stable:** values do not change while the Job runs or during restarts.
- **Distinguishes data:** each row maps to a single partition.
- **Query-efficient:** the database can filter by the key, ideally backed by a suitable index.
- **Reasonably distributed:** avoids one partition holding nearly all data.
- **Operationally meaningful:** easy to log, monitor, and investigate by key/range.

An auto-incrementing primary key is often convenient for range partitioning, though not always balanced. If certain key intervals hold significantly more rows, the corresponding worker runs longer and keeps other workers waiting for the manager Step to finish.

Do not partition by a column that can mutate while the Job runs, such as order status, if that mutation could move a row from one partition to another. Choose an immutable key or operate against a consistent snapshot.

## 12. Load balancing and data skew

Dividing a key domain into equal-width intervals does not equate to equal row counts. For example, `order_id` spans 1 to 1,000,000, yet only 10% of older IDs still exist while 90% cluster in recent ranges. Even range splitting creates one slow worker while others finish early.

Ways to address skew:

- Use key distribution statistics or histograms to determine boundaries closer to actual row counts.
- Split by record count using window-function queries if supported by the database with an acceptable execution plan.
- Pick a business key or hash bucket with better distribution.
- Create more smaller partitions than workers so the scheduler distributes load dynamically.
- Track processing duration per partition and adjust boundaries for subsequent runs.

Smaller partitions do not automatically fix skew if partitions still vary wildly in data size. Measure row counts, reader/writer times, and commit times per worker.

## 13. Ensuring no duplicates and no missed data

The correctness of key partitioning depends on partitions forming a valid partition of the target dataset.

With range partitioning, ensure:

1. Intervals do not overlap.
2. Intervals cover the entire selected key domain.
3. Every row within the business scope falls into exactly one interval.
4. Worker query predicates use matching inclusive/exclusive bounds.
5. Boundaries do not shift unexpectedly between partition creation and worker reads.

Example checking SQL predicates for two adjacent partitions:

```sql
-- Partition A
SELECT COUNT(*)
FROM orders
WHERE order_id >= 1 AND order_id < 101;

-- Partition B
SELECT COUNT(*)
FROM orders
WHERE order_id >= 101 AND order_id < 201;
```

Do not use `BETWEEN` when preserving half-open semantics because `BETWEEN` is typically inclusive at both ends. When reconciling results, compare the sum of row counts across partitions against the source range count on the same snapshot.

## 14. Data changing while partitions are running

A key risk is source data mutating after Partitioner queries `min(id)` and `max(id)` but before workers finish reading.

Examples:

- A new row with a key greater than `maxId` is inserted after partitions are created; that row belongs to no partition in the current run.
- A row is deleted before a worker reads it; the worker will not see that row.
- A filter attribute changes between workers, so results no longer reflect a single logical snapshot.
- If partitioned by a mutable column, a row can move across ranges mid-Job.

Options:

- Capture a high-watermark (e.g., max key) at start time and specify that newer data is handled in the next run.
- Use transaction isolation or a database snapshot if a consistent dataset is needed.
- Partition by an immutable key and stable business predicates.
- Use a staging table or batch membership table to lock the set of items belonging to a run.
- Record business keys and processing state to reconcile rows inserted/deleted during the Job.

There is no single default isolation level suited to every database. Evaluate snapshot requirements, runtime duration, and impact on locks/undo/version store before choosing.

## 15. Restarting a partitioned Step

Partitioning creates dedicated metadata for each partition. The Manager Step coordinates workers and JobRepository stores StepExecutions for partitions. When a Job fails, completed partitions can typically be preserved; incomplete or failed partitions can be reprocessed according to restart policy.

For reliable restarts:

- Use stable, reproducible partition names.
- Keep boundary calculation consistent between initial run and restart.
- Store `minIdInclusive`/`maxIdExclusive` in the partition ExecutionContext.
- Ensure readers support `saveState`/`ItemStream` if mid-partition checkpoints are needed.
- Design idempotent writers or unique keys to prevent duplicate writes when a chunk reruns.
- Do not change identifying JobParameters in a way that turns a restart into a new JobInstance.

A partition can contain multiple chunks. The reader checkpoint inside a worker helps resume within a partition; partition metadata lets the manager know each worker's status. These are two distinct levels of state.

If source data or partitioning rules change between two runs, do not silently compute new boundaries for the same JobInstance. Store required snapshot/high-watermark metadata in JobParameters or ExecutionContext so restarts reproduce the original data range accurately.

## 16. Partitioning and safe concurrency

When multiple workers run in parallel, each worker has its own StepExecution, though they may share singleton beans. Watch out for:

- Stateful readers usually require `@StepScope`.
- Processors with mutable state must be instantiated separately or made thread-safe.
- Shared writers must be safe under concurrent calls from multiple threads.
- Do not store partition `minId`, `maxId` in fields of a singleton reader.
- Bound worker count according to connection pool, CPU, I/O, and database capacity.
- Avoid multiple partitions updating the same summary row or writing to a resource without concurrency support.

`gridSize` and thread count should not far exceed datasource capacity. For example, if the pool only has 5 connections for the entire application, configuring 32 workers forces most threads to wait for connections and increases contention instead of speeding up execution.

## 17. Local partitioning and remote partitioning

Key partitioning describes how data is divided; partition execution can be local or remote.

- **Local partitioning:** manager and worker Steps run in the same JVM, typically using `TaskExecutor` to run in parallel across threads.
- **Remote partitioning:** manager dispatches partition info to other worker processes via middleware or a configured communication channel. Each worker runs the Step in its own process.

In both cases, partition context must hold enough information for the worker to know its key range. Remote workers must receive and restore context via messaging; handle retries, duplicate messages, and worker failures according to deployment infrastructure.

If you only need multiple threads in one application, local partitioning is usually simpler. If you need to spread load across multiple processes or servers, remote partitioning may fit, though it requires designing message transport, availability, and observability.

## 18. Monitoring individual partitions

Each partition has its own name and StepExecution, making it possible to track:

- Partition name.
- Start and end keys.
- `BatchStatus` and `ExitStatus`.
- Start/end timestamps.
- Read/write/filter/skip counts.
- Commit/rollback counts.
- Last exception if the partition failed.

Range info in ExecutionContext is very helpful during investigations. For instance, if partition `orders-partition-2` fails, you can query that worker's exact `order_id` range rather than inspecting the whole table.

Log `partitionName`, `minIdInclusive`, `maxIdExclusive`, and JobExecution/StepExecution IDs. Avoid logging full item payloads if they contain sensitive data.

## 19. Common mistakes

### Overlapping partition ranges

If two workers both pick up a boundary key, some rows may be processed twice. Use half-open intervals `[start, end)` and verify SQL predicates.

### Gaps between ranges

If boundaries are not chained accurately, some keys may belong to no partition. Use a single cursor variable, set `nextStart = previousEndExclusive`, and test the entire domain.

### Treating gridSize as a concurrency limit

`gridSize` relates to creating partitions; TaskExecutor governs execution and concurrent task count. Configure both toward explicit goals.

### Reader without StepScope

If the reader does not receive StepExecution-specific context, multiple workers may share the same key range. Use `@StepScope` for readers accepting partition context.

### Splitting key domain evenly with skewed data

Equal-width ranges do not mean equal row counts. Use histograms, business buckets, or row-count-based boundaries when balancing is needed.

### Partition key changing mid-Job

A row may shift ranges or be missed across workers. Pick an immutable key and explicit snapshot/high-watermark.

### Spawning too many workers

Database connection pool, lock contention, and I/O can become bottlenecks. Measure throughput and increase concurrency incrementally.

### Restart generating different boundaries than the first run

If source data changes or the partitioning algorithm is unstable, the same JobInstance may process a different range. Persist snapshot metadata and ensure partition names/boundaries are reproducible.

### Writer unsafe on rerun

A partition or chunk may be rerun after failure. Use unique keys, upserts, or appropriate idempotency mechanisms.

## 20. Workflow for implementing key partitioning

When building a key-partitioned Job, follow this sequence:

1. Select a stable, data-distinguishing, indexed key.
2. Define the run's data scope, such as business date or high-watermark.
3. Choose range, hash/modulo, or business-key strategy.
4. Write Partitioner producing a map of partition name -> ExecutionContext.
5. Define non-overlapping boundaries covering the target dataset completely.
6. Build Worker Step with a `@StepScope` reader pulling keys from `stepExecutionContext`.
7. Configure Manager Step via `.partitioner(...).step(...).gridSize(...)`.
8. Choose TaskExecutor and concurrency suited to connection pool, database, and CPU.
9. Ensure reader/writer state and thread safety are properly handled.
10. Test empty partitions, sparse data, boundary keys, newly arriving data, and restarts.
11. Monitor row counts, durations, and statuses per partition to detect skew.

| Requirement | Recommended design |
|---|---|
| Split table by incrementing primary key | Range partitioning with `[min, max)` |
| Split data by tenant/region | Partition by business key |
| Evenly distributed key, fixed buckets desired | Hash/modulo partitioning |
| Workers running in parallel in one JVM | Local partitioning with TaskExecutor |
| Processing across multiple processes/machines | Remote partitioning |
| Per-region restartability | Stable partition context and checkpoint-capable worker Step |

## Conclusion

Key partitioning splits a dataset into non-overlapping parts based on a stable key. `Partitioner` produces partition names and `ExecutionContext`s holding key ranges; the manager Step assigns each part to a worker Step, where a `@StepScope` reader uses those bounds to query the right data. Range partitioning with half-open intervals `[minIdInclusive, maxIdExclusive)` helps prevent duplicates or gaps at boundaries. For efficiency and safe restarts, choose an indexed and well-distributed key, keep boundaries stable, cap concurrency within database capacity, and design readers/writers for checkpointing and idempotency.
