# Partition context and metadata

In Spring Batch, partitioning splits a large Step into multiple independent worker StepExecutions. Each worker processes a slice of data, such as an ID range, a group of files, or a set of tenants. For each worker to know its assigned work and resume after failure, Spring Batch attaches a separate ExecutionContext to each partition and persists that context along with StepExecution metadata in JobRepository.

Distinguish three kinds of information: Job input data resides in JobParameters; partitioning parameters and per-worker checkpoints reside in Step ExecutionContext; execution status, timing, and outcome metadata reside in JobRepository. Understanding this relationship helps split work without overlaps, observe individual workers, and restart incomplete partitions accurately.

## 1. Partitioning creates multiple worker StepExecutions

A partitioned Step usually has a coordinating manager Step and a processing worker Step. The manager defines partitions, creates corresponding StepExecutions, and hands them to the handler. Each partition has a stable name and its own ExecutionContext.

Example Job processing orders by ID range:

~~~text
importOrdersJob
      |
      v
managerStep
      |
      | creates partitions
      |
      +------------------------------+
      |              |               |
      v              v               v
worker:partition0 worker:partition1 worker:partition2
  ID 1..1000        ID 1001..2000     ID 2001..3000
      |              |               |
      v              v               v
  StepExecution   StepExecution   StepExecution
  + context       + context       + context
~~~

Each worker is a separate StepExecution. It has its own status, counters, start/end times, and ExecutionContext. Therefore, partitioning not only splits data; it creates execution units with dedicated metadata for tracking and restarts.

gridSize is the target number of partitions the manager requests to create. How many workers actually run concurrently also depends on the handler and executor. For instance, 8 partitions can be created while only 4 threads are allowed to run simultaneously.

## 2. Partitioner creates partition contexts

The Partitioner interface accepts grid size and returns a map from partition name to ExecutionContext:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Each map entry represents one unit of work. The key is the partition name; the value is the context containing parameters needed for the worker to process the right range.

Example contexts for three partitions:

~~~java
Map<String, ExecutionContext> partitions = new HashMap<>();

ExecutionContext first = new ExecutionContext();
first.putLong("minId", 1L);
first.putLong("maxIdExclusive", 1001L);
partitions.put("partition0", first);

ExecutionContext second = new ExecutionContext();
second.putLong("minId", 1001L);
second.putLong("maxIdExclusive", 2001L);
partitions.put("partition1", second);

ExecutionContext third = new ExecutionContext();
third.putLong("minId", 2001L);
third.putLong("maxIdExclusive", 3001L);
partitions.put("partition2", third);
~~~

These contexts serve as inputs to worker StepExecutions. Workers can use minId and maxIdExclusive to build isolated queries.

Prefer half-open intervals [minId, maxIdExclusive): the start value is included, while the end value is excluded. This convention lets consecutive intervals chain without boundary overlaps:

- Partition 0: id >= 1 AND id < 1001.
- Partition 1: id >= 1001 AND id < 2001.
- Partition 2: id >= 2001 AND id < 3001.

If using intervals inclusive on both ends, be extra careful when computing bounds to avoid processing duplicates or missing records.

## 3. Building an ID-range Partitioner

The following example illustrates splitting a contiguous ID domain into roughly equal-sized intervals. In real applications, min/max should be fetched from the data source or an explicit snapshot.

~~~java
public class CustomerRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxIdExclusive;

    public CustomerRangePartitioner(
            long minId,
            long maxIdExclusive) {
        if (minId > maxIdExclusive) {
            throw new IllegalArgumentException("Invalid ID range");
        }
        this.minId = minId;
        this.maxIdExclusive = maxIdExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException(
                    "gridSize must be positive");
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        long total = maxIdExclusive - minId;
        if (total == 0) {
            return result;
        }

        long targetSize = (total + gridSize - 1) / gridSize;
        long start = minId;
        int index = 0;

        while (start < maxIdExclusive) {
            long end = Math.min(start + targetSize, maxIdExclusive);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxIdExclusive", end);

            result.put("partition" + index, context);
            start = end;
            index++;
        }

        return result;
    }
}
~~~

This example demonstrates a known ID domain with calculations fitting within long limits. For production data, handle overflow when computing totals, target sizes, or bounds; and explicitly define behavior for empty sources, sparse IDs, or large gaps.

Splitting by min/max does not guarantee each partition has the same number of records if IDs are non-contiguous. When data distribution is skewed, one partition can be much heavier than others. You can split by sequence numbers, hashes, tenants, dates, or data distribution queries for better workload balance.

## 4. Injecting partition context into the worker Step

The Worker Step can use @StepScope and stepExecutionContext expressions to receive partition parameters.

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .sql("""
                select id, name, email
                from customer
                where id >= ? and id < ?
                order by id
                """)
            .preparedStatementSetter(statement -> {
                statement.setLong(1, minId);
                statement.setLong(2, maxIdExclusive);
            })
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email")))
            .saveState(true)
            .build();
}
~~~

@StepScope defers reader creation until the worker StepExecution exists. Spring can then resolve values from that specific partition's Step ExecutionContext.

Do not create a singleton reader holding mutable min/max and swap values before each partition. Multiple workers may run concurrently and overwrite each other's ranges. Scope by StepExecution so each worker gets its own reader and parameters.

## 5. Configuring manager Step and worker Step

A partitioned Step configuration consists of a worker Step, a Partitioner, and a manager Step. In Spring Batch 5, Java configuration looks like this:

~~~java
@Bean
Step customerWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("customerWorkerStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .writer(customerWriter)
            .build();
}

@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
            .partitioner(
                    "customerWorkerStep",
                    customerPartitioner)
            .step(customerWorkerStep)
            .gridSize(4)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

The Manager Step uses the partitioner to create worker executions. TaskExecutor controls concurrency in local partitioning. Here, grid size is 4; the executor should have a pool configured appropriately for allowed concurrent workers and database resources.

Worker Step name and partition names should be stable. Spring Batch uses execution and partition identifiers to link metadata across runs. Arbitrarily renaming Steps or partitions can prevent restarts from restoring the right old executions.

## 6. Partition context and Step ExecutionContext

The context returned by Partitioner initializes the partition's StepExecution context. While the worker runs, components like readers and writers can add checkpoints to that same Step context via the ItemStream lifecycle.

For example, a worker's context may contain:

~~~text
partition0 Step ExecutionContext
  minId = 1
  maxIdExclusive = 1001
  customerReader.currentPage = 3
  customerReader.lastId = 742
  orderWriter.lastCommittedId = 742
~~~

The keys minId and maxIdExclusive identify the partition's share of work. The keys currentPage, lastId, and lastCommittedId can be runtime state updated by reader/writer for failure recovery.

Namespace keys to prevent collisions between partition parameters and component state. For example, use partition.minId, customerReader.lastId, and customerWriter.lastId.

Do not confuse the context created by Partitioner with Job ExecutionContext. Partition context belongs to the worker StepExecution. Each partition has its own copy; one worker updating its context does not automatically alter another worker's context.

## 7. Job context is not a mutable shared area for partitions

Job ExecutionContext belongs to JobExecution and has a scope shared across Steps in the Job. Meanwhile, partitions can run concurrently.

If multiple workers write the same key into Job context, updates can overwrite each other or yield non-deterministic results depending on completion order. Job context is not a concurrent map for workers to use as a data-exchange channel.

Follow these principles:

- Job-wide input data belongs in JobParameters or Job context if it is shared runtime metadata.
- Partition-specific parameters belong in that partition's Step ExecutionContext.
- Reader/writer checkpoints belong in the worker's Step context.
- Aggregate results across partitions should be computed via an aggregation mechanism or stored in a synchronized data store.

For example, if each partition counts processed records, do not have all workers update jobExecutionContext['processedCount']. Use StepExecution counters, an aggregator, or a partition-keyed result table and aggregate afterward.

## 8. Partition metadata is stored in JobRepository

JobRepository stores metadata for JobInstance, JobExecution, StepExecution, and ExecutionContext. In a JDBC repository, common tables include:

| Metadata | Common JDBC table |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| StepExecution | BATCH_STEP_EXECUTION |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Table names may vary by table prefix and Spring Batch version schema. Worker StepExecution rows are linked to JobExecution and have their own ExecutionContexts.

Metadata generally allows querying:

- Which JobExecution launched the manager Step.
- Which partitions were created.
- Which worker StepExecutions are running, completed, failed, or stopped.
- Each worker's read/write/skip/commit/rollback counters.
- Which checkpoints are stored in each worker's context.

Do not create custom metadata tables just to track partition status when JobRepository already manages that information. If detailed business outcomes must be persisted, use business or audit tables—do not alter BATCH_* schemas to stuff arbitrary data.

## 9. Serialization of partition context

ExecutionContext is serialized by JobRepository before persistence. Therefore, values placed into context by Partitioner must be supported by the active serializer.

Typically suitable values:

- Long or Integer for IDs and bounds.
- String for tenant codes, file names, or versions.
- Boolean for processing flags.
- Small values with stable structure that restore cleanly.

Example:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("partition.minId", 1L);
context.putLong("partition.maxIdExclusive", 1001L);
context.putString("partition.sourceVersion", "snapshot-42");
~~~

Avoid putting into context:

- Lists of thousands of entities.
- File contents or large payloads.
- JDBC Connections, streams, threads, or executors.
- JPA entity graphs or objects depending on unstable classes.
- Passwords, tokens, private keys, or credentials.

For large data, store it in a database, file, or object storage and pass an ID or reference in context. Serialization is not encryption; anyone with read access to metadata can inspect persisted values depending on format and access controls.

## 10. Individual checkpoints and per-partition restart

A key benefit of partitioning is that each worker has independent state. If one partition fails, other completed partitions can retain their completed status. When restarting the same JobInstance, Spring Batch uses old metadata to determine which workers need to resume.

Example:

~~~text
First JobExecution
  partition0 -> COMPLETED
  partition1 -> FAILED
  partition2 -> COMPLETED
  partition3 -> COMPLETED

Restart same JobInstance
  partition0 -> keep completed result
  partition1 -> restart from saved checkpoint
  partition2 -> keep completed result
  partition3 -> keep completed result
~~~

For this mechanism to work properly:

- Keep JobInstance identifying JobParameters unchanged.
- Keep manager Step, worker Step, and partition names stable.
- Keep key semantics in partition context unchanged.
- Readers/writers must support ItemStream if checkpoints need restoring.
- Source data must have stable ordering or a stable snapshot.
- Writers must be idempotent or participate in transactions to prevent duplicate writes on retry/restart.

If grid size or the partitioning algorithm changes between the initial run and restart, check how old partitions are recognized and handled. Do not generate new partition names for the same data range when the goal is to restart old executions.

## 11. PartitionNameProvider and stable partition names

In some cases, recomputing partitions is expensive—such as querying an external system for a list of files or tenants. PartitionNameProvider is an extension point allowing you to supply partition names when the framework needs them, especially helpful during restart flows when names were already created previously.

The critical requirement is that the name list must be stable and correspond to previously created partitions. If names change, Spring Batch cannot match current partitions to old StepExecution metadata.

Use PartitionNameProvider only when partition names can be determined without recomputing the entire context. If data ranges or sources change, store a version or snapshot identifier to ensure old contexts remain meaningful.

## 12. Aggregating results from workers

After workers finish, the manager must aggregate statuses and counters of child StepExecutions. Spring Batch uses the StepExecutionAggregator mechanism for this purpose.

Information typically aggregated:

- Overall status of the manager Step.
- Read, write, filter, and skip counts.
- Commit and rollback counts.
- ExitStatus and worker errors.
- Timing or operational information to surface.

Aggregating statuses/counters does not mean merging every key from worker ExecutionContexts into Job context. If each partition has its own lastId or outputFile, there is no single value to merge automatically.

If aggregated business outcomes are needed, define explicit rules. For example, total order count is the sum of counters; output file list is a collection of per-partition references; failure status takes the highest severity per Job rules.

Do not let multiple workers overwrite the same Job context key as a substitute for an aggregator.

## 13. Remote partitioning and shared metadata

In local partitioning, manager and workers run in the same application on different threads. In remote partitioning, the manager sends work to workers running in other processes or nodes through middleware such as a message broker.

General model:

~~~text
Manager application
  Partitioner
      |
      v
  JobRepository <-------------------------+
      |                                   |
      v                                   |
  StepExecution requests                  |
      |                                   |
      v                                   |
  Message broker                          |
      |                                   |
      +--------------+--------------------+
                     |
              Worker application
                     |
                     v
              JobRepository
                     |
                     v
           Worker StepExecution
                     |
                     v
             Step ExecutionContext
~~~

In remote partitioning, the metadata repository must be shared or configured in a supporting architecture so manager and workers see the same executions. Orchestration messages identify which execution to run; workers use corresponding metadata to load the StepExecution and partition context.

Ensure:

- Manager and workers share an appropriate JobRepository.
- Both sides have identical Job/Step definitions and compatible versions.
- Workers have access to data for their assigned partitions.
- Partition names and StepExecution IDs remain stable.
- Worker transaction managers properly manage business resources.
- Failed message sends, dead workers, or redelivered messages can be recovered.

Remote partitioning differs from remote chunking. Partitioning sends independent StepExecution units to workers; remote chunking typically has a manager read data and send chunks to workers to process/write. The two models differ in reader placement, metadata, and work boundaries.

## 14. Partition context vs. JobParameters

JobParameters describe a Job run request and help identify the JobInstance when marked identifying. Partition context describes the specific range a single worker must process.

Example:

~~~text
JobParameters
  businessDate = 2026-11-15
  tenantGroup = enterprise

partition0 Step ExecutionContext
  minId = 1
  maxIdExclusive = 1001

partition1 Step ExecutionContext
  minId = 1001
  maxIdExclusive = 2001
~~~

Both workers share the Job's businessDate and tenantGroup, yet each worker has its own ID interval. There is no need to create a new JobInstance per partition; partitions are StepExecutions belonging to the same JobExecution.

If a parameter changes the data scope of the entire Job, it should usually be an identifying JobParameter. If it only describes one worker's slice created by Partitioner, place it in the partition's Step context.

## 15. Monitoring partitions via JobExplorer

JobExplorer provides a read API over metadata stored in JobRepository. It can inspect JobExecutions, StepExecutions, and each worker's status.

Useful operational details:

- JobExecution ID and JobInstance ID.
- Manager Step name.
- Worker Step name and partition name.
- BatchStatus and ExitStatus of each worker.
- Read/write/skip counts.
- Start time, end time, and runtime duration.
- Saved ExecutionContext, if permissions and query APIs allow.

A dashboard can display each partition as a row:

| Partition | Range | Status | Read | Write |
|---|---|---|---:|---:|
| partition0 | ID 1–1000 | COMPLETED | 1000 | 998 |
| partition1 | ID 1001–2000 | FAILED | 430 | 420 |
| partition2 | ID 2001–3000 | COMPLETED | 1000 | 1000 |
| partition3 | ID 3001–4000 | COMPLETED | 1000 | 997 |

Ranges and figures in the table are illustrative only. In practice, read data from persisted metadata and contexts; do not infer status from logs or counts of sent messages.

Do not directly query or mutate BATCH_* tables to control workers. Use JobExplorer for reading and JobRepository/framework APIs for managing executions.

## 16. Common mistakes when designing partition context

**Sharing one Job context across all workers.** Concurrent workers can overwrite each other. Place isolated ranges in each partition's Step context.

**Unstable partition names.** Restarts cannot match new workers to old metadata. Use deterministic names and keep conventions consistent across deployments.

**Overlapping or gapped data intervals.** Records get processed twice or missed. Use explicit boundary rules and test coverage.

**Mutating source data between restarts.** Old checkpoints may no longer correspond to the same record set. Use snapshots, watermarks, or source versions.

**Storing large objects in context.** Metadata bloats and becomes hard to serialize. Store only scalars or references.

**Omitting Step scope.** Workers may receive wrong parameters or share reader state. Instantiate stateful components per StepExecution.

**Confusing aggregation with context promotion.** Aggregators combine execution statuses/counters; promotion promotes selected keys from Step context to Job context. The two serve different purposes.

**Not sharing the repository in remote partitioning.** Manager and workers cannot see the same metadata, leading to un-updated executions.

**Assuming gridSize equals concurrency.** Grid size sets the target partition count; executor/handler determines actual concurrency.

## 17. Security and metadata lifecycle

Partition context often holds business keys, IDs, tenants, file paths, or source versions. Store only data necessary for workers to execute and restart.

Do not put secrets into context. If a worker needs credentials, use a secret manager and store non-sensitive references. Restrict read access to JobRepository because anyone able to read metadata can see partition parameters and checkpoints.

Partition metadata can persist long after a Job completes to support audits and restart policies. Establish appropriate retention/cleanup, but do not delete contexts of running or restartable executions. Follow Spring Batch's official cleanup procedures and organizational retention policies.

## 18. Testing partition context and metadata

Test the partitioner, worker Step, and restarts at both component and integration levels.

### Unit tests for Partitioner

Verify:

- Valid grid sizes are handled properly.
- Partition names are stable and unique.
- Ranges do not overlap.
- Union of ranges covers the entire data domain.
- Empty source yields empty result per policy.
- Start/end bounds do not drop or duplicate records.

For example, with ID domain 1 to 3000, three partitions should cover [1,1001), [1001,2001), and [2001,3001).

### Integration tests with JobRepository

Run a partitioned Job and verify:

1. Manager creates the right number of worker StepExecutions.
2. Each worker receives its exact partition context.
3. Worker Step contexts are stored separately.
4. Counters and statuses of each worker are updated.
5. Manager receives appropriate aggregation results.
6. A failing worker can restart from its checkpoint.
7. Completed partitions are not rerun unintentionally.
8. Job context is not overwritten by concurrent workers.

For remote partitioning, also test message redelivery, a worker stopping mid-run, temporary metadata repository unavailability, and a worker rerunning the same StepExecution.

## 19. Partition context design workflow

When building a partitioned Step, follow this sequence:

1. Identify the partitioning unit: ID range, tenant, file, date, or data group.
2. Pick deterministic partition names unique within the Step.
3. Build ExecutionContexts holding only parameters needed by workers.
4. Use Step scope so workers read the right StepExecution context.
5. Let readers/writers persist individual checkpoints in Step context.
6. Use JobRepository to persist metadata and track each worker.
7. Use an aggregator for statuses/counters; use a separate mechanism for business results requiring merging.
8. Ensure source data and partitioning logic remain stable across restarts.
9. For remote partitioning, configure manager and workers to see an appropriate shared metadata repository.
10. Test ranges, concurrency, rollbacks, restarts, and message redelivery.

Partition context is the data contract between manager and worker. JobRepository turns that contract into durable metadata attached to each StepExecution. When each partition has an isolated context, stable name, proper checkpoints, and explicitly versioned source data, Spring Batch can coordinate multiple workers, track partial progress, and restart exact incomplete partitions.

