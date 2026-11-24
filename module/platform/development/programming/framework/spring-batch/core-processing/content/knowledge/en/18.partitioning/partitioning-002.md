# Partitioner creates ExecutionContext for each partition in Spring Batch

In Spring Batch, partitioning splits a large Step into multiple independent data subsets to be processed by multiple worker Steps. Each subset is called a **partition**. For a worker to know which data subset it must process, Spring Batch needs a separate input description for each partition.

The component responsible for creating those descriptions is the **Partitioner**. Each time it is called, the Partitioner returns a map consisting of a partition name and a corresponding **ExecutionContext**. The ExecutionContext holds values such as ID ranges, business dates, tenant codes, file names, or partitioning keys. Spring Batch uses each context to create a separate StepExecution for the worker.

This lesson explains the Partitioner contract, how to create a stable partition map, how to place data into ExecutionContext, how workers read context using StepScope, as well as how to design data boundaries, restarts, and testing to avoid missing or duplicating items.

## 1. What is the Partitioner's job?

A partitioned Step has two roles:

- **Manager Step:** coordinates, splits work into partitions, and launches worker Steps.
- **Worker Step:** performs data processing within the scope of one partition.

The Partitioner only describes how the work is divided. It does not directly read and process all items, nor does it create threads itself. Spring Batch uses the Partitioner's result to create a separate StepExecution for each partition and hands them to the partition execution mechanism.

For example, a table has 1,000,000 customers. Instead of one worker reading the entire table, the application can split IDs into four ranges:

| Partition | ID Range | Data the worker processes |
|---|---:|---|
| partition0 | 1–250000 | Customers with ID from 1 to 250000 |
| partition1 | 250001–500000 | Customers with ID from 250001 to 500000 |
| partition2 | 500001–750000 | Customers with ID from 500001 to 750000 |
| partition3 | 750001–1000000 | Customers with ID from 750001 to 1000000 |

Each worker receives an ExecutionContext containing its corresponding ID range. The worker uses these values to query its exact portion of data.

~~~mermaid
flowchart TD
    A["Manager Step"] --> B["Partitioner.partition(gridSize)"]
    B --> C["Map: partition0 -> ExecutionContext"]
    B --> D["Map: partition1 -> ExecutionContext"]
    B --> E["Map: partition2 -> ExecutionContext"]
    B --> F["Map: partition3 -> ExecutionContext"]
    C --> G["Worker StepExecution 0"]
    D --> H["Worker StepExecution 1"]
    E --> I["Worker StepExecution 2"]
    F --> J["Worker StepExecution 3"]
~~~

Each partition has its own context and StepExecution. Consequently, workers can run independently, maintain separate states, and be restarted according to Spring Batch metadata.

## 2. The Partitioner contract

Spring Batch defines the Partitioner interface:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

The method takes gridSize and returns a map:

- Key is the partition name.
- Value is the ExecutionContext containing input data for that partition.

Example result:

~~~java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxId", 250L);

partitions.put("partition0", first);
~~~

When Spring Batch creates a worker StepExecution, it uses the partition name to identify the execution and places the corresponding ExecutionContext into the worker's scope.

### What role does the partition name play?

The partition name must be unique within a split and should be stable across reruns of the same JobInstance. Names are typically readable values such as:

- partition0
- partition1
- region_APAC
- tenant_001
- file_20261115_01

Partition names help identify StepExecutions, inspect status in JobRepository, read logs, and track which worker failed.

Do not generate random names using UUID each time the Partitioner is called if you want restarts to recognize previous partitions. A new name can cause Spring Batch to treat it as a different partition.

### The map must fully describe the work

Each ExecutionContext should contain enough information for the worker to determine its exact data subset. For example, if the worker needs to read by ID range, the context must contain both the lower and upper bounds.

Do not pass only a generic value and let workers guess their own ranges. Data-splitting logic should be centralized in the Partitioner so completeness, non-overlapping coverage, and reproducibility on restart can be verified.

## 3. Partition ExecutionContext

ExecutionContext is a key-value storage area that Spring Batch attaches to an execution. In partitioning, each partition has its own ExecutionContext.

Example:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 250L);
context.putString("region", "APAC");
context.putString("sourceBatchId", "BATCH-20261115");
~~~

The worker can read these keys:

- minId: smallest ID belonging to the partition.
- maxId: largest ID belonging to the partition.
- region: area to process.
- sourceBatchId: source data batch identifier.

### ExecutionContext is not JobParameters

The two data types have different scopes:

| Storage location | Scope | Example |
|---|---|---|
| JobParameters | Input identifying or configuring a JobInstance | businessDate, sourceBatchId |
| JobExecutionContext | Data shared across Steps within a JobExecution | work directory path, aggregate info |
| StepExecutionContext | State specific to one StepExecution, including a worker partition | minId, maxId, partition-specific file |

In partitioning, the data created by the Partitioner is placed into each worker's StepExecutionContext. This is why the worker can read stepExecutionContext to obtain its own data range.

Do not place minId and maxId for all partitions into a shared JobExecutionContext for workers to read together. Workers need separate values that do not overwrite one another.

### Values in context must be persistable

ExecutionContext is persisted in JobRepository to support status tracking and restarts. Therefore, store only small, stable, serializable values, such as:

- String.
- Long, Integer, Double, or Boolean.
- Dates/times or data types supported by the configured serializer.
- Small data structures that can be safely serialized.

Do not put objects such as JDBC Connection, ResultSet, InputStream, file handles, threads, Spring beans, or non-serializable objects into ExecutionContext. Store resource identifiers, such as a path or ID, and let the worker open the resource at runtime.

## 4. Writing a RangePartitioner to split data by ID

A common strategy is splitting a table by ID range. For example, data has IDs from 1 to 1,000 and you want to create four partitions.

Each partition receives two bounds:

- minId: lower bound, inclusive.
- maxId: upper bound, inclusive.

The worker queries with the condition:

~~~sql
WHERE id >= :minId
  AND id <= :maxId
~~~

Ranges must be contiguous and non-overlapping. Example:

~~~text
partition0: [1, 250]
partition1: [251, 500]
partition2: [501, 750]
partition3: [751, 1000]
~~~

A practical implementation can use BigInteger to calculate range sizes without overflowing when the ID domain is wide:

~~~java
public class RangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public RangePartitioner(long minId, long maxId) {
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException(
                "gridSize must be greater than 0"
            );
        }

        if (minId > maxId) {
            return Map.of();
        }

        BigInteger min = BigInteger.valueOf(minId);
        BigInteger max = BigInteger.valueOf(maxId);
        BigInteger total = max.subtract(min).add(BigInteger.ONE);
        BigInteger divisor = BigInteger.valueOf(gridSize);

        BigInteger targetSize = total
            .add(divisor)
            .subtract(BigInteger.ONE)
            .divide(divisor);

        Map<String, ExecutionContext> result =
            new LinkedHashMap<>();

        for (int i = 0; i < gridSize; i++) {
            BigInteger start = min.add(
                targetSize.multiply(BigInteger.valueOf(i))
            );

            if (start.compareTo(max) > 0) {
                break;
            }

            BigInteger end = start
                .add(targetSize)
                .subtract(BigInteger.ONE)
                .min(max);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start.longValueExact());
            context.putLong("maxId", end.longValueExact());

            result.put("partition" + i, context);
        }

        return result;
    }
}
~~~

In this example:

- If gridSize equals 4, the Partitioner creates up to four partitions.
- If the number of records is less than gridSize, only the necessary number of partitions is created.
- Ranges are divided sequentially.
- The upper bound of the previous partition is one unit less than the lower bound of the next partition.
- Each context contains exact boundary values for the worker.

Using BigInteger prevents overflow when calculating the total number of IDs and range size. longValueExact() ensures the values placed into ExecutionContext remain within the long domain.

### Why use LinkedHashMap?

LinkedHashMap preserves insertion order of the partitions. Ordering is not required for data to be split correctly, but it makes logs, debugging, and testing easier to read.

Partition names must still be stable. Do not rely on map iteration order to drive different business logic.

## 5. Fetching minId and maxId from the database

In real applications, the data range can be determined from the source table:

~~~sql
SELECT MIN(customer_id), MAX(customer_id)
FROM customer_source
WHERE batch_id = :batchId
~~~

JdbcTemplate can be used to fetch the values:

~~~java
public RangePartitioner createPartitioner(
        JdbcTemplate jdbcTemplate,
        String batchId) {

    Long minId = jdbcTemplate.queryForObject(
        """
        SELECT MIN(customer_id)
        FROM customer_source
        WHERE batch_id = ?
        """,
        Long.class,
        batchId
    );

    Long maxId = jdbcTemplate.queryForObject(
        """
        SELECT MAX(customer_id)
        FROM customer_source
        WHERE batch_id = ?
        """,
        Long.class,
        batchId
    );

    if (minId == null || maxId == null) {
        return new RangePartitioner(1L, 0L);
    }

    return new RangePartitioner(minId, maxId);
}
~~~

This example illustrates determining the bounds. In Spring Batch configuration, the Partitioner is typically registered as a bean and receives required dependencies via constructor or factory method.

### Query scopes must be consistent

The filter criteria used to find min/max must match the source filter criteria used by workers. If the Partitioner computes min/max across the entire table while workers only read one batch, ranges may be wider than needed. If the Partitioner filters by batch while workers do not filter by the same batch ID, workers may read the wrong data.

Align the criteria:

- batch ID or business date.
- record status eligible for processing.
- tenant or region.
- soft-delete condition or active flag.
- data snapshot or version.

Common criteria can live in JobParameters or ExecutionContext and then be used by workers alongside the ID range.

## 6. Handling an empty source

When the table has no matching records, MIN and MAX typically return null. Do not convert null to 0 and create a dummy range if ID 0 could be a valid value.

There are two common design approaches:

**Approach 1: handle NO_DATA before the partition Step.**

A validation Step checks the count or min/max. If there is no data, the flow branches to NO_DATA or ends according to business rules. The partition Step only runs when data exists.

**Approach 2: intentionally create an empty partition.**

If you still want a worker to run to record a 0-item result, create a context with an empty=true flag. The worker reads that flag and finishes without querying the source.

Example context:

~~~java
ExecutionContext context = new ExecutionContext();
context.putBoolean("empty", true);

Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
partitions.put("partition0", context);
~~~

The worker checks this flag before creating or using the reader. This approach provides a StepExecution and metrics for the empty-source case.

Do not return an arbitrary range like 0 to 0 if that could accidentally read a real record.

## 7. Passing partition data to workers using StepScope

Each partition's ExecutionContext is attached to the worker's StepExecution. A `@StepScope` bean can retrieve values using SpEL.

Example reader querying by ID range:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer_source
            WHERE batch_id = ?
              AND customer_id >= ?
              AND customer_id <= ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps -> {
            ps.setString(1, batchId);
            ps.setLong(2, minId);
            ps.setLong(3, maxId);
        })
        .rowMapper((rs, rowNum) -> new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .saveState(true)
        .build();
}
~~~

In this example:

- minId and maxId come from the partition's StepExecutionContext.
- batchId comes from the Job's shared JobParameters.
- @StepScope defers creating the reader until the worker StepExecution exists.
- The reader only queries records belonging to the batch and the partition's ID range.

Without StepScope, Spring may create the reader too early, before StepExecutionContext exists to inject values. Late binding will then fail to work as intended.

### Using context in a processor or writer

Other worker beans can also receive partition values via StepScope. For example, a writer can record the partition name in an audit column:

~~~java
@Bean
@StepScope
ItemWriter<Customer> customerWriter(
        CustomerRepository repository,
        @Value("#{stepExecutionContext['partitionName']}")
        String partitionName) {

    return chunk -> {
        for (Customer customer : chunk.getItems()) {
            repository.saveProcessed(
                customer,
                partitionName
            );
        }
    };
}
~~~

To use partitionName, put that key into ExecutionContext when creating partitions:

~~~java
context.putString("partitionName", "partition" + i);
~~~

The partition name can also be derived from the StepExecution name. Storing a dedicated key gives the worker direct access, but ensure it always stays consistent with the map key.

## 8. Configuring the manager Step and worker Step

The worker Step is the Step that performs chunk processing. The manager Step is the partitioned Step that coordinates workers.

Worker example:

~~~java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, ProcessedCustomer> customerProcessor,
        ItemWriter<ProcessedCustomer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
        .<Customer, ProcessedCustomer>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
~~~

Manager configuration:

~~~java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
~~~

gridSize(4) instructs the Partitioner to target four partitions. If the Partitioner returns fewer than four partitions due to a small source, the number of workers created corresponds to the returned map.

taskExecutor(...) enables the manager to dispatch workers using a TaskExecutor. How many workers run concurrently also depends on executor limits, database resources, and system configuration.

### Configuring TaskExecutor

Example using a thread pool:

~~~java
@Bean
ThreadPoolTaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor =
        new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("batch-partition-");

    return executor;
}
~~~

Spring manages the TaskExecutor bean lifecycle. Choose a pool size aligned with the number of partitions, connection pool, CPU, and database capacity.

Grid size does not equate to thread count. For example, with 12 partitions and a pool size of 4, at most four workers can run concurrently; the remaining partitions execute as threads become available.

## 9. Defining the Partitioner as a Spring bean

A Partitioner can be registered directly:

~~~java
@Bean
@StepScope
Partitioner customerPartitioner(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new CustomerRangePartitioner(
        jdbcTemplate,
        batchId
    );
}
~~~

If the Partitioner needs to read JobParameters, @StepScope or an appropriate late-binding approach matching when the manager Step runs can be used. However, the Partitioner is called during the manager's partition preparation; ensure runtime values are available in the right scope.

A clean way to organize this is to define a Partitioner bean with a dependency on a range-fetching service, where the service receives the batch ID from JobParameters within the manager Step scope.

Example using a Partitioner with known bounds:

~~~java
@Bean
@StepScope
Partitioner customerPartitioner(
        @Value("#{jobParameters['minId']}") Long minId,
        @Value("#{jobParameters['maxId']}") Long maxId) {

    return new RangePartitioner(minId, maxId);
}
~~~

When late binding is needed, the bean can be declared with @StepScope so JobParameters values are injected once the manager StepExecution exists. Avoid creating a singleton bean whose constructor receives runtime JobParameters.

## 10. Naming partitions and persisting context stably

Partition names and ExecutionContext contents affect restarts. Spring Batch stores each partition's StepExecution in JobRepository. For example, a worker execution name may be formed from the worker Step name plus the partition name, such as customerWorkerStep:partition0.

For stable restarts:

- Generate deterministic partition names.
- Use the same splitting rules for the same JobInstance.
- Keep identifying JobParameters unchanged.
- Keep the semantics of keys in ExecutionContext unchanged.
- Do not change grid size or partitioning strategy between a run and its restart if doing so alters the partition list.
- Keep the source dataset stable or define an explicit snapshot.

If the first run creates partition0 through partition3, but on restart partition0 through partition7 are created with different boundaries, old metadata no longer maps properly to the new data plan. This can cause missed or duplicated data processing.

### Versioning the partition plan

For critical systems, a version or plan code can be stored in ExecutionContext:

~~~java
context.putString("partitionPlanVersion", "v1");
context.putString("batchId", batchId);
context.putLong("minId", start);
context.putLong("maxId", end);
~~~

The worker can check the version and batch ID to ensure the context matches the data being processed.

If the partitioning strategy changes, create a new JobInstance via appropriate identifying JobParameters or design an explicit metadata migration. Do not change the meaning of context keys while an old JobInstance may still be restarted.

## 11. ExecutionContext and worker restarts

Each worker StepExecution has its own ExecutionContext. Readers, writers, or other components can store that specific partition's checkpoint in the same context.

Example:

~~~text
customerWorkerStep:partition0
  minId = 1
  maxId = 250
  reader.current.count = 120

customerWorkerStep:partition1
  minId = 251
  maxId = 500
  reader.current.count = 250
~~~

This is a conceptual illustration. Exact checkpoint key names depend on the reader and configuration.

When partition0 completes but partition1 fails:

- Partition0, already COMPLETED, typically does not need to rerun when restarting the same JobInstance.
- Partition1 can be restarted according to Step status and policy.
- Partition2 and partition3 are handled according to their actual statuses.
- The worker restores the partition range from ExecutionContext and the read position from the reader's checkpoint.

### Do not overwrite context on restart

Do not create a different ExecutionContext with a new range for a partition that already has metadata. If the Partitioner produces inconsistent ranges, the reader may restore its old position while querying the new range, causing missed or duplicated data.

Treat the partition plan as part of the JobInstance contract. The same identifying parameters must produce the same partition names and the same data boundaries.

## 12. Splitting data without overlaps or gaps

A correct Partitioner must guarantee the entire target dataset is completely partitioned.

With inclusive ranges, each partition has the condition:

~~~sql
customer_id >= :minId
AND customer_id <= :maxId
~~~

If the previous partition has maxId 250, the next partition must start at 251. Never allow two partitions to share ID 250 or skip ID 251.

Incorrect split example:

~~~text
partition0: [1, 250]
partition1: [250, 500]   -- ID 250 is processed twice
~~~

Gap example:

~~~text
partition0: [1, 250]
partition1: [252, 500]   -- ID 251 is missed
~~~

Correct example:

~~~text
partition0: [1, 250]
partition1: [251, 500]
~~~

### Non-contiguous IDs

Range partitioning does not require IDs to be contiguous. If a table has IDs 1, 3, 100, and 900, ranges can still cover all records accurately if queries use boundary predicates. Some partitions may have fewer items or be empty.

If data distribution is skewed, splitting by arithmetic range can create unbalanced partitions. For example, most IDs cluster around 1–1000 while larger IDs are very sparse. In that case, consider splitting by record count, histograms, or a more suitable partitioning key.

### Other partitioning strategies

| Strategy | Values in ExecutionContext | Appropriate when |
|---|---|---|
| ID Range | minId, maxId | Ordered key exists |
| Business date | fromDate, toDate | Time-partitioned data |
| Tenant | tenantId | Each tenant is an independent processing unit |
| Region | regionCode | Data split by geographic region |
| File | resourcePath, fileName | Each file is one partition |
| Hash bucket | bucketNumber, bucketCount | Stable hash-based distribution |

Regardless of strategy, each partition must clearly describe its data scope and must not overlap unintentionally.

## 13. Partitioning by date or tenant

Splitting is not always by ID. Example date partitioning:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("fromDate", "2026-11-01");
context.putString("toDate", "2026-11-07");
context.putString("batchId", batchId);

partitions.put("week_2026_11_01", context);
~~~

The worker reads keys using StepScope:

~~~java
@Bean
@StepScope
ItemReader<TransactionRecord> transactionReader(
        @Value("#{stepExecutionContext['fromDate']}") String fromDate,
        @Value("#{stepExecutionContext['toDate']}") String toDate,
        @Value("#{jobParameters['batchId']}") String batchId) {
    // Create a reader that only reads the partition's date range.
}
~~~

With tenant partitioning:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("tenantId", tenantId);
context.putString("batchId", batchId);

partitions.put("tenant_" + tenantId, context);
~~~

The worker only reads data for its assigned tenant. Clearly define whether a tenant can be split into multiple partitions or is always a dedicated partition.

Do not put a huge tenant list into a single key if you can create one partition per tenant. Conversely, if there are tens of thousands of tiny tenants, one partition per tenant can create too many StepExecutions. Tenants can be grouped into batches with small, serializable lists stored in context.

## 14. Source data changing while partitions run

If the Partitioner fetches MIN/MAX at start time while data continues to change, workers may read newly added records or miss records depending on query predicates.

Example:

1. Partitioner determines maxId is 1000.
2. Another process inserts record ID 1001.
3. Workers only read up to 1000.
4. Record 1001 does not belong to the current partition plan.

This may be correct if the Job only processes a snapshot as of plan creation time. If all new records must be processed, a clearer scope mechanism is needed.

Some ways to control this:

- Use a fixed batch ID to close the input set.
- Store an upper bound or watermark at Job start.
- Use snapshot isolation or an appropriate database snapshot mechanism.
- Disallow modifications to the partitioning key during processing.
- Record a timestamp or version of the partition plan.
- Route late-arriving data into the next batch.

Do not let each worker query its own MIN/MAX at runtime. If the source changes between workers, ranges may no longer belong to a coherent plan.

## 15. Handling unbalanced partitions

Range partitioning by min/max can produce ranges of equal arithmetic size, yet the number of records in each range can differ dramatically.

Example:

| Partition | ID Range | Actual record count |
|---|---:|---:|
| partition0 | 1–250000 | 200000 |
| partition1 | 250001–500000 | 180000 |
| partition2 | 500001–750000 | 15000 |
| partition3 | 750001–1000000 | 5000 |

The first two partitions run much longer. Total Job duration is then dominated by the slowest worker.

Some options:

- Split by quantiles or key histograms.
- Use more smaller partitions than threads so the scheduler distributes work gradually.
- Split by batch IDs or tenants of comparable volume.
- Use hash buckets for even distribution if queries support it.
- Track duration and item counts per partition.

Do not increase gridSize indefinitely. Too many partitions create extra metadata, StepExecutions, queries, and coordination overhead. Measure actual throughput and limit database load.

## 16. Partitioning and concurrency

Partitioning allows workers to run independently, potentially concurrently if the manager Step uses a suitable TaskExecutor or handler.

Ensure:

- Each partition processes an isolated data range.
- The writer can handle concurrent writes.
- The database has enough connections and resources.
- Target tables have appropriate indexes and constraints.
- Non-thread-safe mutable state is not shared across workers.
- Partition output files have distinct names to avoid overwriting each other.

If multiple workers write to the same table, the database must still handle contention, unique constraints, and deadlocks. Partitioning increases parallelism but does not eliminate write conflicts by itself.

### Separate output file names per partition

If workers write files, place the partition name in context and create separate files:

~~~java
Path output = outputDirectory.resolve(
    "customers-" + partitionName + ".csv"
);
~~~

After all workers complete, another Step can merge files or publish a manifest. Do not let multiple workers write to a single ordinary file if the writer does not support concurrent synchronized writes.

## 17. JobRepository stores metadata for each partition

When the manager Step creates worker executions, Spring Batch persists partition state in JobRepository. Each worker has its own StepExecution, including:

- Step name and execution ID.
- BatchStatus and ExitStatus.
- Start time, end time.
- Read, write, filter, and skip counts.
- Partition's ExecutionContext and checkpoints.
- Error details if the worker fails.

This lets operators see which worker completed, which failed, and which data range was assigned to that worker.

The StepExecution name is typically built from the worker Step name plus the partition name. Example:

~~~text
customerWorkerStep:partition0
customerWorkerStep:partition1
customerWorkerStep:partition2
customerWorkerStep:partition3
~~~

The exact name depends on configuration and the splitter mechanism, though clear partition naming makes lookup easier.

Do not delete or overwrite partition metadata while the Job may still need restarting. ExecutionContext is a critical part of processing state.

## 18. Testing the Partitioner in isolation

A Partitioner is a Java class that can be tested directly without launching a Job. Verify partition count, names, context values, ranges, and completeness.

Example:

~~~java
@Test
void createsNonOverlappingRanges() {
    RangePartitioner partitioner =
        new RangePartitioner(1L, 10L);

    Map<String, ExecutionContext> partitions =
        partitioner.partition(3);

    assertEquals(3, partitions.size());

    assertEquals(
        1L,
        partitions.get("partition0").getLong("minId")
    );
    assertEquals(
        4L,
        partitions.get("partition0").getLong("maxId")
    );

    assertEquals(
        5L,
        partitions.get("partition1").getLong("minId")
    );
    assertEquals(
        8L,
        partitions.get("partition1").getLong("maxId")
    );

    assertEquals(
        9L,
        partitions.get("partition2").getLong("minId")
    );
    assertEquals(
        10L,
        partitions.get("partition2").getLong("maxId")
    );
}
~~~

With minId 1, maxId 10, and gridSize 3, the target size is 4, so the ranges are [1,4], [5,8], and [9,10].

### Cases to test

| Input | What to verify |
|---|---|
| gridSize is 0 or negative | Rejected |
| minId equals maxId | Creates one partition with one ID |
| minId greater than maxId | Empty source behavior per design |
| Total IDs divisible by gridSize | Balanced ranges |
| Total IDs not divisible | Last partition is smaller |
| Total IDs less than gridSize | No unintended empty ranges created |
| Bounds near Long.MIN_VALUE or Long.MAX_VALUE | No integer overflow |
| Called again with same input | Produces same names and contexts |
| Two adjacent partitions | No overlap, no gap |

Verify by merging intervals and asserting:

- The first lower bound equals minId.
- The final upper bound equals maxId.
- For two consecutive partitions, the previous partition's maxId plus one equals the next partition's minId.
- No partition has minId greater than maxId.
- Partition names are unique.

## 19. Testing that workers receive the right ExecutionContext

Beyond Partitioner unit tests, integration tests are needed to ensure Spring Batch passes contexts to workers.

A test can:

1. Create a Partitioner returning two distinct contexts.
2. Configure a worker Step with a @StepScope reader.
3. Have the reader receive minId and maxId via stepExecutionContext.
4. Run the manager Step.
5. Verify each worker queries the right data range.
6. Inspect each partition's StepExecution in JobRepository.
7. Verify total output equals source data with no duplicate records.

A test reader can record injected ranges. Do not just check that the Partitioner returns the right map; verify StepScope wiring and that workers actually read the right contexts.

### Testing partition restart

Create a scenario where one partition completes and one partition fails. Then restart the same JobInstance:

- COMPLETED partitions do not rerun outside policy.
- The failed partition reruns.
- Partition context is properly restored.
- The reader resumes from that partition's checkpoint.
- Final results have no missing or duplicated data.

## 20. Common implementation mistakes

### Sharing a single ExecutionContext across all partitions

If the same context object is placed under multiple keys, values can be mutated and contaminate state across workers. Create a new ExecutionContext for each partition.

### Random partition names

Unstable names make it difficult for restarts to recognize old StepExecutions. Use deterministic names derived from index, tenant, region, or file key.

### Not storing enough data in context

If a worker needs batch ID, range, or data version and context lacks it, the worker must guess or re-query inconsistently. Put all required information in context or use shared JobParameters explicitly.

### Putting non-serializable objects into ExecutionContext

Connections, streams, or beans must not be stored in context. Store only small, serializable data.

### Not using StepScope for late binding

A singleton bean created before partition StepExecutions exist cannot receive values from stepExecutionContext. Use @StepScope for readers, writers, or beans needing partition data at runtime.

### Overlapping or gapped ranges

Inconsistent inclusive/exclusive bounds can cause a record to be processed twice or never processed. Define explicit boundary rules and test all intervals.

### Computing ranges independently in each worker

Each worker fetching min/max at different times can yield an inconsistent plan if the source changes. Compute the partition plan once at the manager and pass contexts to workers.

### Changing gridSize on restart

Partition count and boundaries may change and no longer match old metadata. Keep the partition plan stable for the same JobInstance or create a new JobInstance when changing strategies.

### Assuming gridSize equals thread count

gridSize is the target number of partitions; actual concurrency depends on TaskExecutor or PartitionHandler. Configure both based on system resources.

### Unbalanced data splits

Equal-width ranges do not guarantee equal record counts. Monitor actual volume and choose an appropriate strategy.

## 21. Workflow for building a Partitioner

When implementing partitioning, you can follow this sequence:

1. **Identify the dataset:** determine batch ID, date, tenant, or source criteria.
2. **Choose a splitting strategy:** range, tenant, region, file, or hash bucket.
3. **Create the partition plan:** compute each partition's name and range at the manager.
4. **Create separate ExecutionContexts:** store keys workers need for each partition.
5. **Preserve determinism:** the same JobInstance must recreate the same partition names and boundaries.
6. **Configure the worker Step:** use @StepScope to receive context via late binding.
7. **Configure the manager Step:** attach Partitioner, worker Step, gridSize, and executor.
8. **Protect the data:** ensure ranges do not overlap, leave no gaps, and the source is stable.
9. **Design restarts:** preserve checkpoints and context per worker.
10. **Test:** verify partition map, context wiring, concurrency, and restarts.

## 22. Key takeaways

- Partitioner implements partition(int gridSize) and returns Map<String, ExecutionContext>.
- Each key is a unique partition name; each value is that partition's dedicated ExecutionContext.
- Spring Batch uses contexts to create a StepExecution for each worker.
- A partition's ExecutionContext belongs to StepExecution scope, distinct from JobParameters and JobExecutionContext.
- Store small, stable, serializable values such as ranges, batch ID, tenant, or file path.
- Workers use @StepScope and stepExecutionContext to receive runtime data.
- Manager Step is configured with partitioner(...).step(...).gridSize(...).taskExecutor(...).
- gridSize is the target partition count, not necessarily the number of concurrently running workers.
- Partition plans should be deterministic, non-overlapping, and cover the dataset accurately.
- Keep partition names and boundaries stable for the same JobInstance so restarts work accurately.
- Control changing source data, skewed distributions, and concurrency.
- Test both the Partitioner in isolation and workers receiving context, processing data, and restarting.

A well-designed Partitioner turns a large job into small, named slices with independent state. When each ExecutionContext accurately describes a worker's share of data, Spring Batch can distribute parallel processing, track progress, and recover each partition consistently.

