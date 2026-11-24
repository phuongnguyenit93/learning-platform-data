# Restarting partitions

In Spring Batch, partitioning splits a large Step into multiple smaller partitions. Each partition is executed as a separate `StepExecution` with its own `ExecutionContext` and status. When a Job fails and is restarted, Spring Batch can resume incomplete partitions from saved checkpoints while preserving the results of completed partitions.

Partition restart is especially valuable for Jobs processing large volumes of data, because one failing partition does not necessarily force all successfully processed data to rerun. For this mechanism to work properly, partitions must have stable names, reproducible data ranges, restart-capable worker Steps, and metadata persisted in `JobRepository`.

## 1. Partitioning creates multiple StepExecutions

A partitioned Step typically has two roles:

- **Manager/master Step:** splits data into partitions and coordinates execution.
- **Worker Step:** performs data processing for one partition, usually via chunk-oriented processing or a Tasklet.

For example, a Job importing 1,000,000 orders may split IDs into four intervals. Each interval becomes a partition and is processed by a separate worker StepExecution.

```text
JobExecution: importOrdersJob
       |
       v
Manager Step: partitionOrdersStep
       |
       +--> workerStep:partition0  (ID 1 - 250000)
       |
       +--> workerStep:partition1  (ID 250001 - 500000)
       |
       +--> workerStep:partition2  (ID 500001 - 750000)
       |
       +--> workerStep:partition3  (ID 750001 - 1000000)
```

Each worker partition has its own `StepExecution` and `ExecutionContext`. Thus, partition 0's checkpoint does not overwrite partition 1's checkpoint. This is the foundation enabling Spring Batch to track which partitions completed and which need to resume upon restart.

## 2. How does partition restart work?

Suppose a Job has four partitions. The first two partitions complete, the third partition fails mid-processing, and the fourth partition has not yet run due to an error during coordination.

```text
First run
  partition0 -> COMPLETED
  partition1 -> COMPLETED
  partition2 -> FAILED (already committed some chunks)
  partition3 -> incomplete

Restart same JobInstance
  partition0 -> keep COMPLETED result
  partition1 -> keep COMPLETED result
  partition2 -> rerun from most recently committed checkpoint
  partition3 -> executed because incomplete
```

Spring Batch uses metadata in `JobRepository` to identify partition StepExecutions. Completed partitions are typically not re-executed on a normal restart. Failed or incomplete partitions have appropriate executions created/restored and continue according to saved state.

With a chunk-oriented worker Step, checkpoints typically reside in the partition's Step `ExecutionContext`. If a partition committed four chunks and hit an error on the fifth chunk, a restart can resume from the fourth chunk's checkpoint rather than re-reading the entire partition.

Restart does not mean Spring Batch relaunches every partition from scratch. It relies on per-partition status and persisted metadata.

## 3. JobInstance must remain the same on restart

Spring Batch identifies a `JobInstance` by Job name together with JobParameters marked as identifying. A restart is a new `JobExecution` of the same JobInstance, so it must be relaunched with the same set of identifying parameters.

For example, an order import Job runs with:

```text
jobName       = importOrdersJob
businessDate  = 2026-11-15  (identifying)
sourceSystem  = ERP         (identifying)
```

When the Job fails, restart with the same `businessDate` and `sourceSystem` so Spring Batch finds the exact previous JobInstance and partition metadata.

Adding a new identifying parameter like a timestamp or a changing `run.id` on relaunch may create a new JobInstance. Spring Batch then treats it as a new logical job and partitions may run from the beginning.

Do not use a JobParametersIncrementer to restart an old run. An incrementer typically generates a new identifying parameter for the next instance; restarting requires preserving the identity of the current JobInstance.

## 4. Partition names must be stable

The partition name is essential for the framework to link partition metadata across executions. If the initial run creates names `partition0`, `partition1`, `partition2`, `partition3`, the restart must recreate the corresponding set of names.

Example stable names:

```text
orders-partition-000
orders-partition-001
orders-partition-002
orders-partition-003
```

Do not base partition names on random UUIDs or timestamps on each call to `Partitioner.partition()`. When names change, the framework cannot correlate new partitions with old `StepExecution`s and checkpoints, causing completed data to be reprocessed or metadata to go unused.

Partition names should derive from a stable identifier of the data range, such as shard index, tenant, business date, or ID interval. The worker Step name must also remain stable across deployments because StepExecution metadata is tied to the Step name.

## 5. Partitioner must reproduce consistent data ranges

`Partitioner` creates an `ExecutionContext` for each partition. Context typically contains data bounds the worker will process, such as `minId` and `maxId`.

Basic interface:

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Example partitioner splitting a fixed ID range into parts:

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
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        if (gridSize <= 0 || minId > maxId) {
            return partitions;
        }

        long totalItems = maxId - minId + 1;
        long targetSize = (totalItems + gridSize - 1) / gridSize;
        long start = minId;
        int partitionNumber = 0;

        while (start <= maxId) {
            long end = Math.min(start + targetSize - 1, maxId);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);

            String partitionName = String.format(
                    Locale.ROOT, "orders-partition-%03d", partitionNumber++
            );
            partitions.put(partitionName, context);

            start = end + 1;
        }

        return partitions;
    }
}
```

With `minId=1`, `maxId=1000`, and `gridSize=4`, the partitioner creates four contexts with nearly equal ID ranges. Each partition's name and bounds are reproduced identically if partitioner inputs do not change.

This example uses fixed bounds to illustrate the principle. In real systems, do not query `MAX(id)` from a mutating table on every restart and re-split without snapshot rules. If new records are inserted, partition count or boundaries could shift. Pin the input range using durable JobParameters, snapshots, manifests, or business metadata.

## 6. Worker reads bounds from partition ExecutionContext

Each worker Step receives the current partition's context. `@StepScope` can be used to inject those bounds into the reader:

```java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .rowMapper(rowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

The `PagingQueryProvider` query must filter by partition bounds and sort by a stable key, for example:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE order_id BETWEEN :minId AND :maxId
ORDER BY order_id
```

Each partition reads only its range. `saveState(true)` lets the reader store its read position in the partition's Step ExecutionContext so restarts resume from the committed checkpoint.

The reader name should be stable. If the reader is stateful, avoid renaming it or changing internal keys without a compatibility plan for in-flight execution metadata.

## 7. Configuring manager Step and worker Step

The Worker Step is typically a chunk-oriented Step. The Manager Step uses a partitioner to create partitions and a `PartitionHandler` to dispatch them.

Worker Step example:

```java
@Bean
public Step importOrderWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> partitionOrderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrderWorkerStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(partitionOrderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Manager Step:

```java
@Bean
public Step partitionOrdersStep(
        JobRepository jobRepository,
        Step importOrderWorkerStep,
        Partitioner orderRangePartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("partitionOrdersStep", jobRepository)
            .partitioner("importOrderWorkerStep", orderRangePartitioner)
            .step(importOrderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionTaskExecutor)
            .build();
}
```

`gridSize(4)` is a hint for the desired number of partitions to the partitioner/handler; the actual partition count depends on the map returned by `Partitioner`. `TaskExecutor` allows worker partitions to run in parallel under local partitioning. With remote partitioning, request dispatch and worker environments differ, yet per-partition metadata and checkpointing principles still apply.

In real configurations, ensure the reader bean is step-scoped to receive the right ExecutionContext per partition. If a mutable singleton reader is shared across multiple workers, partitions can overwrite state and read wrong ranges.

## 8. StepExecution and ExecutionContext for each partition

When the manager creates partitions, Spring Batch creates StepExecutions for workers. Each StepExecution has its own metadata and ExecutionContext:

```text
JobExecution
  |
  +-- Manager StepExecution: partitionOrdersStep
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-000
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-001
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-002
        |      +-- ExecutionContext: minId, maxId, reader checkpoint
        |
        +-- Worker StepExecution: importOrderWorkerStep:orders-partition-003
               +-- ExecutionContext: minId, maxId, reader checkpoint
```

Each partition's ExecutionContext holds both initial partitioning data and state updated by the reader/writer. On restart, the framework must match the partition name and restore its corresponding context.

Do not store checkpoints for all partitions in a shared singleton field. Each partition has an isolated state scope and should rely on its own StepExecution/ExecutionContext.

## 9. What happens when a partition fails?

Suppose partition 2 processes data with chunk size 100. It committed 12 chunks, then chunk 13 encounters an error:

```text
orders-partition-002
  Chunk 1..12  -> COMPLETED / committed
  Chunk 13     -> FAILED / rolled back
  Chunk 14..   -> not yet run
```

When the Job is restarted with the same JobInstance, Spring Batch uses saved metadata for partition 2. The worker can restore the reader checkpoint after chunk 12 and continue with the remaining data.

Completed partitions retain their results. Incomplete or failed partitions resume according to saved state. Thus, the full dataset does not need to rerun from scratch when metadata and readers are properly configured for restarts.

If the worker Step configures skip/retry, errors may be handled during the execution itself before the partition finishes. Only when an unrecoverable error fails the worker Step does restarting the Job give the partition a chance to resume from the latest checkpoint.

## 10. Partition restart requires stable input data

A partitioner might generate the same partition names yet still return different data ranges. In that case, the framework finds old metadata, while the new context no longer describes the same data.

For example, the initial run splits a table with IDs 1 to 1,000 into four intervals. While the Job is failed, rows are inserted/deleted or `MAX(id)` changes. Recalculating ranges on restart may yield intervals different from the first run.

To avoid this situation:

- Use identifying JobParameters to pin the date, tenant, source, or snapshot to process.
- Persist the overall range or partition manifest durably if boundaries are computed dynamically.
- Use stable partition names, independent of non-deterministic map ordering or fresh UUIDs.
- Use a unique, stable sort key in the reader.
- Avoid changing query filters or partitioning logic between the initial run and restart without migration.
- If source data mutates continuously, consider snapshots or watermarks to define the logical dataset.

Partition names and ExecutionContexts are part of restart metadata. Changing the partitioning algorithm between application versions can render old executions incompatible.

## 11. PartitionNameProvider and restoring partition names

For expensive partitioners, Spring Batch supports `PartitionNameProvider`. This interface supplies the list of partition names without constructing the full `ExecutionContext` for every partition.

Example:

```java
public class OrderRangePartitioner
        implements Partitioner, PartitionNameProvider {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        // Create names and ExecutionContexts for the partitions to be created.
        return createPartitionContexts(gridSize);
    }

    @Override
    public Set<String> getPartitionNames(int gridSize) {
        // Return the exact stable partition names.
        return createStablePartitionNames(gridSize);
    }
}
```

During restart, the framework can use the name list to match previous partitions and avoid unnecessary context recomputation for completed partitions. Returned names must match the names used in the initial run.

`PartitionNameProvider` only optimizes obtaining partition names; it does not replace `Partitioner`, store checkpoints on behalf of readers, or automatically guarantee stable data ranges. Recreating contexts for partitions that still need to run must still rely on consistent partitioning rules.

## 12. Local partitioning vs. remote partitioning on restart

Partition restart applies to both local partitioning and remote partitioning, though metadata storage infrastructure and how workers launch differ.

**Local partitioning:** the manager Step dispatches worker StepExecutions to threads in the same application, usually via `TaskExecutor`. Workers share JobRepository and resources configured in the application context.

**Remote partitioning:** the manager sends partition execution requests to other worker processes or nodes over middleware. Manager and workers must coordinate against an appropriate metadata repository so worker statuses and checkpoints are persisted and retrieved consistently. Workers need matching Step configurations and must read the right ExecutionContext for their assigned partition.

In both cases, keep worker Step names, partition names, and checkpoint keys stable. If a worker process stops, JobRepository must still hold partition metadata so restarts recognize completed portions and portions needing re-execution.

Do not confuse remote partitioning with remote chunking. Remote partitioning distributes partitions/StepExecutions to workers; remote chunking distributes chunks from a manager Step to chunk-processing workers. Restart mechanisms and tracked metadata units differ.

## 13. Transactions and idempotency in worker partitions

Reader checkpoints restore read positions, but they do not automatically guard all side effects. A worker may call APIs, send messages, or write files outside database transactions. If a side effect happened before the chunk committed, the partition may re-execute that operation on restart.

For database writes in the same transaction manager, chunk rollback reverts uncommitted changes. For non-transactional resources, use stable business keys, unique constraints, idempotency keys, outboxes, or staging workflows.

For example, if each partition writes orders to a target table, use `order_id` as a unique key with an appropriate upsert operation. When a chunk is reprocessed after rollback, the same order does not create duplicate rows.

If each partition writes a separate file, name the file by partition name or stable business key, write to a temporary file, and publish upon completion. Avoid appending to an old file without knowing precisely what was committed.

## 14. allowStartIfComplete and completed partitions

A worker Step can be configured with `allowStartIfComplete(true)`. This option lets an already-completed Step run again on an eligible restart. With partitioning, it can cause a completed partition to re-execute.

Enable this option only when business rules require rerunning completed partitions and writers are idempotent. For normal restarts, leaving completed partitions untouched is usually appropriate.

Do not enable `allowStartIfComplete` just to "be sure data is updated." If input data changed, decide whether it is a new JobInstance or an intentional rerun. Do not accidentally turn a restart into a fresh processing pass.

## 15. Common mistakes when restarting partitions

### Partition names changing between runs

New partition names do not match old metadata. The framework may fail to correlate checkpoints and create fresh executions for already-completed ranges. Use stable names based on business key or shard index.

### Partitioner recomputing ranges from changed data

A partition has the same name but different ID bounds. Workers can read duplicates or miss records. Pin the snapshot or persist a range manifest.

### Reader not saving state

The reader does not implement `ItemStream`, disables `saveState`, or is not registered as a stream. On restart, the reader starts from the beginning of the partition. Enable state and ensure `open/update/close` callbacks run.

### Renaming worker Step or reader

Old metadata is bound to the old Step name and reader keys. Renaming can make old executions incompatible. Keep names stable or plan a migration.

### Using new identifying parameters on restart

The Job creates a new JobInstance and ignores old partition metadata. Keep identifying parameters unchanged for the job you intend to resume.

### Non-idempotent side effects

A chunk or partition can be reprocessed after rollback/restart. Use transactions or idempotency to avoid duplicate writes.

### Sharing a mutable singleton reader across partitions

Multiple workers mutate the read position in one object, causing race conditions. Stateful readers must be created at Step scope or per partition execution.

## 16. Monitoring partitions in operations

When investigating a partitioned Job, do not look only at manager Step status. Inspect each worker StepExecution:

- Partition name and worker Step name.
- `BatchStatus` and `ExitStatus`.
- `startTime`, `endTime`, and runtime duration.
- `readCount`, `writeCount`, filter/skip counts.
- `commitCount` and `rollbackCount`.
- ExecutionContext containing partition bounds and reader checkpoints.
- Exception of any failed partition.

This information helps determine which partitions completed, which failed, and where the last checkpoint stands. On restart, comparing old and new StepExecutions for the same partition name confirms the framework resumed the right range.

Do not directly edit metadata in JobRepository to mark a partition completed or force a checkpoint to another position without fully understanding business data. Desynchronizing metadata from target data can cause restarts to miss or duplicate records.

## 17. Testing partition restarts

A meaningful restart test should simulate a failure in one partition after several chunks have committed:

1. Launch the Job with a fixed set of identifying JobParameters.
2. Create multiple partitions with stable names and ranges.
3. Let some partitions complete.
4. Make one partition fail after a few committed chunks.
5. Inspect metadata and checkpoints for each partition.
6. Relaunch the same JobInstance with the same identifying parameters.
7. Verify completed partitions do not rerun under default configuration.
8. Verify the failed partition resumes from its saved checkpoint.
9. Verify output data has no missing or duplicate entries.

Beyond failure cases, also test:

- Restart when a partition was not yet picked up by a worker.
- Restart when a worker was stopped mid-chunk.
- Partitioner recreating exact partition names and bounds.
- Source data mutating between initial run and restart.
- Multiple workers running in parallel without sharing mutable reader state.
- Non-transactional side effects not repeating unexpectedly.

Integration tests need a repository capable of retaining metadata across two runs. If using an in-memory repository recreated between test runs, the test cannot prove durable restart behavior across process restarts.

## 18. Partition restart design rules

For reliable partition restarts, preserve the JobInstance with stable identifying JobParameters; use stable partition names and worker Step names; reproduce identical data ranges; save reader checkpoints in each partition's ExecutionContext; and use a persistent JobRepository. For writers, ensure database changes share rollbackable transactions or external side effects are idempotent.

When a partitioned Job fails, inspect each worker StepExecution's metadata to identify completed partitions and partitions needing resumption. Partition restart relies on each partition's individual state, so one failing partition does not force completed partitions to rerun—provided partition identity, checkpoints, and source data stay consistent across executions.
