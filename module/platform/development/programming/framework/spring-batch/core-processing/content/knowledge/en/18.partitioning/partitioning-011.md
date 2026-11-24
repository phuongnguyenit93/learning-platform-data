# Distinguishing partitioning from chunk processing

In Spring Batch, **chunk processing** and **partitioning** solve two different problems. Chunk processing divides data within a Step into groups of items to read, process, write, and commit per transaction. Partitioning splits a Step's work into multiple independent subsets, each executed by a worker StepExecution and potentially run in parallel.

The two mechanisms are not mutually exclusive. A Job can partition a Step across multiple workers, and each worker then processes its data in chunks. This is a common pattern to increase parallelism while keeping transaction boundaries and checkpoints at the chunk level.

## 1. What is chunk processing?

Chunk-oriented processing is a model for processing data in item groups. A Step typically has three components:

1. `ItemReader` reads items from a data source.
2. `ItemProcessor` validates, filters, or transforms each item.
3. `ItemWriter` writes the processed group of items.

When the item count reaches the commit interval, Spring Batch invokes the Writer and commits the chunk's transaction. If a chunk fails and the error triggers a rollback, changes in the current chunk's transaction are rolled back; previously committed chunks are preserved.

```text
A chunk-oriented Step
       |
       v
  ItemReader
       |
       v
 ItemProcessor
       |
       v
enough items per commit interval
       |
       v
   ItemWriter
       |
       v
    COMMIT
       |
       +----> Read next chunk
```

Example configuring a Step processing 500 items per chunk in Spring Batch 5 or later:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

In this example, `500` is the commit interval. The Step can read and process the entire dataset on a single execution thread, committing after every chunk. Chunk processing by itself does not mean data is split across multiple workers or processed in parallel.

## 2. What is partitioning?

Partitioning splits a logical Step into multiple work units called partitions. Spring Batch creates a separate `StepExecution` for each partition. One Step acts as a manager coordinating worker StepExecutions; each worker executes the same Step configuration while receiving a separate `ExecutionContext` to know which portion of data it must process.

For example, a `customer` table has IDs from 1 to 1,000,000. Data can be split into four non-overlapping intervals:

```text
Manager Step: partitionCustomersStep
       |
       +--> Worker StepExecution 0: customer_id 1       - 250000
       |
       +--> Worker StepExecution 1: customer_id 250001  - 500000
       |
       +--> Worker StepExecution 2: customer_id 500001  - 750000
       |
       +--> Worker StepExecution 3: customer_id 750001  - 1000000
```

Each worker reads only its assigned data slice. With an appropriate `TaskExecutor`, workers can run concurrently across multiple threads. In a distributed environment, the manager can send partitions to workers on other processes or machines via remote partitioning.

Partitioning is a mechanism for splitting and distributing work. It does not dictate how workers process items. A worker can be a chunk-oriented Step, a Tasklet Step, or another Step type depending on design.

## 3. The two mechanisms operate on different axes

The key point to remember is that a chunk defines the **unit of processing and commit**, while a partition defines the **unit of data splitting and work distribution**.

| Criterion | Chunk processing | Partitioning |
|---|---|---|
| Main goal | Process data in item groups and commit per transaction | Split a Step into independent parts to coordinate workers |
| Primary unit | A chunk consisting of a group of items | A partition with a worker StepExecution |
| Key components | Reader, Processor, Writer, commit interval | Partitioner, manager Step, worker Step, PartitionHandler |
| State | StepExecution and ExecutionContext of the Step | Each partition has its own StepExecution and ExecutionContext |
| Parallelism | Chunks run sequentially by default; requires separate concurrency mechanism for parallelism | Can run multiple partitions concurrently via executor or distributed workers |
| Transactions | Typically one transaction per chunk | Depends on how the worker Step processes; if the worker is a chunk Step, each chunk has its own transaction |
| Restart | Based on checkpoints and StepExecution status | Can restart based on status and ExecutionContext of each partition |
| Data division | Grouped by item count per commit | Divided by data range or key, e.g., ID, date, tenant, or file |

Because the two mechanisms complement each other, do not ask whether to choose chunking or partitioning in all cases. Use chunking alone when data volume is moderate or parallelism is unnecessary; use partitioning with chunk-oriented workers when data is large and can be divided into independent subsets.

## 4. Combining partitioning with chunk processing

A common design has a manager Step create multiple partitions, and each partition runs the same worker Step configured with chunks. Each worker receives its own data range, reads data in that range, and commits according to the commit interval.

```text
Job: customerImportJob
       |
       v
Manager Step: partitionCustomersStep
       |
       +----------------+----------------+----------------+
       |                |                |                |
       v                v                v                v
   Partition 0      Partition 1      Partition 2      Partition 3
       |                |                |                |
       v                v                v                v
   Worker Step      Worker Step      Worker Step      Worker Step
       |                |                |                |
       v                v                v                v
   Chunk 1           Chunk 1           Chunk 1           Chunk 1
   COMMIT            COMMIT            COMMIT            COMMIT
       |                |                |                |
       v                v                v                v
   Chunk 2           Chunk 2           Chunk 2           Chunk 2
   COMMIT            COMMIT            COMMIT            COMMIT
```

Suppose there are one million customers, four partitions, and a commit interval of 500. Each worker processes about 250,000 customers in 500-item chunks. If data is evenly divided, each worker has roughly 500 chunks. Partition count and items per chunk are two independent settings:

- `gridSize` or partition count determines how many work subsets exist.
- `chunk(500, transactionManager)` determines after how many items each worker commits.

Increasing `gridSize` does not automatically increase the commit interval. Changing chunk size does not automatically create more workers.

## 5. Partitioner splits data into ranges

`Partitioner` is the interface that generates `ExecutionContext`s for workers. Each entry in the map represents a partition; the key is usually the partition name and the value holds the data needed for the worker to process its assigned slice.

```java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
```

Example splitting a contiguous ID range into multiple partitions:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class CustomerRangePartitioner implements Partitioner {

    private final long minId;
    private final long maxId;

    public CustomerRangePartitioner(long minId, long maxId) {
        if (minId > maxId) {
            throw new IllegalArgumentException("minId must be <= maxId");
        }
        this.minId = minId;
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize < 1) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long totalIds = maxId - minId + 1;
        long rangeSize = (totalIds + gridSize - 1) / gridSize;
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        long start = minId;
        int partitionNumber = 0;
        while (start <= maxId) {
            long end = Math.min(start + rangeSize - 1, maxId);

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

This example splits a contiguous ID range and does not guarantee each partition has the exact same record count if the table has many ID gaps. With real data, you can partition by date interval, tenant, region code, hash key, or file list. What matters is that partitions do not overlap and cover the exact target dataset.

If the source has no data, handle the empty case explicitly before creating partitions or return an empty partition per application policy. Do not leave `minId` or `maxId` null and continue splitting ranges.

## 6. Worker Step reads data according to ExecutionContext

Each worker StepExecution has its own `ExecutionContext`. `@StepScope` can be used to late-bind partition bounds into the reader. For example, a reader using a JDBC cursor to read only customers in its assigned ID range:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.PreparedStatementSetter;

@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerPartitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    PreparedStatementSetter parameters = ps -> {
        ps.setLong(1, minId);
        ps.setLong(2, maxId);
    };

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerPartitionReader")
            .dataSource(dataSource)
            .sql("select id, name from customer "
                    + "where id >= ? and id <= ? order by id")
            .preparedStatementSetter(parameters)
            .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
            .saveState(true)
            .build();
}
```

Each worker receives a different `minId` and `maxId`, so the reader queries its own range. `@StepScope` enables values in `stepExecutionContext` to be supplied when the worker StepExecution starts. Because each partition has a StepExecution, it can have its own target reader instance with its own parameters.

In real applications, ensure the reader name is stable so metadata can persist checkpoints. The reader and data source must also be configured properly for restarts. The example above uses `JdbcCursorItemReader` to illustrate the query range; for workloads requiring paging or databases with cursor limits, `JdbcPagingItemReader` can be chosen.

## 7. Configuring manager Step and worker Step

The Worker Step can be a standard chunk-oriented Step. The Manager Step uses the partitioner to create worker StepExecutions:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class CustomerPartitionJobConfig {

    @Bean
    public Step customerWorkerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<Customer> customerPartitionReader,
            ItemProcessor<Customer, Customer> customerProcessor,
            ItemWriter<Customer> customerWriter) {

        return new StepBuilder("customerWorkerStep", jobRepository)
                .<Customer, Customer>chunk(500, transactionManager)
                .reader(customerPartitionReader)
                .processor(customerProcessor)
                .writer(customerWriter)
                .build();
    }

    @Bean
    public TaskExecutor partitionTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setThreadNamePrefix("customer-partition-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step partitionCustomersStep(
            JobRepository jobRepository,
            Step customerWorkerStep,
            Partitioner customerRangePartitioner,
            TaskExecutor partitionTaskExecutor) {

        return new StepBuilder("partitionCustomersStep", jobRepository)
                .partitioner("customerWorkerStep", customerRangePartitioner)
                .step(customerWorkerStep)
                .gridSize(4)
                .taskExecutor(partitionTaskExecutor)
                .build();
    }

    @Bean
    public Job customerImportJob(
            JobRepository jobRepository,
            Step partitionCustomersStep) {
        return new JobBuilder("customerImportJob", jobRepository)
                .start(partitionCustomersStep)
                .build();
    }
}
```

The example assumes `customerRangePartitioner`, `customerProcessor`, and `customerWriter` beans are declared. `customerPartitionReader` is the `@StepScope` bean from the previous section. `gridSize(4)` requests creating up to four partitions in this design; `ThreadPoolTaskExecutor` provides four threads to execute them concurrently.

`gridSize` and thread pool size are related configurations, not the same concept. If 8 partitions are created while the executor only has 4 threads, at most 4 workers run concurrently; remaining partitions wait until a thread is free. If the executor only has one thread, partitioning still splits data into multiple worker StepExecutions without achieving true parallelism.

## 8. How does partitioning differ from a multi-threaded Step?

Beyond partitioning, Spring Batch also supports a multi-threaded Step, where chunks can be processed across multiple threads within the same Step. Both can increase concurrency, yet they isolate state differently.

| Criterion | Multi-threaded Step | Partitioned Step |
|---|---|---|
| Work division | Chunks of the same Step execute on multiple threads | One Step is split into multiple worker StepExecutions |
| ExecutionContext | Same StepExecution manages Step state | Each partition has its own StepExecution and ExecutionContext |
| Reader | May be shared by multiple threads depending on configuration; requires thread-safety evaluation | Usually creates a dedicated `@StepScope` reader per partition |
| Data division | Requires safe concurrency and reader mechanisms to avoid contention | Partitioner explicitly assigns a data range or key per worker |
| Best suited for | Independent item logic, thread-safe components, and no need for complex data partitioning | Data divisible into independent parts or needing distributed workers |
| Tracking and restart | Tracked via shared StepExecution metadata and reader state | Can track and restart each partition via its own StepExecution |

Partitioning generally fits when data can be split cleanly, such as each worker handling an ID region or tenant group. A multi-threaded Step can be simpler if the reader, processor, and writer all support concurrency and separate data ranges are unnecessary.

## 9. Local partitioning vs. remote partitioning

Partitioning can run within a single JVM or distribute workers across multiple processes/machines:

- **Local partitioning:** manager and workers run in the same application process. `TaskExecutorPartitionHandler` typically uses an executor to run workers on different threads.
- **Remote partitioning:** manager creates partitions and sends work-description messages to workers over middleware such as a message broker. Workers in other processes execute the Step and update metadata according to a shared repository setup or designed sync mechanism.

```text
Local partitioning
  Manager Step
      |
      +--> Thread 1 / Worker 1
      +--> Thread 2 / Worker 2
      +--> Thread 3 / Worker 3

Remote partitioning
  Manager Step
      |
      v
  Message Broker
      |
      +--> Worker application A
      +--> Worker application B
      +--> Worker application C
```

Local partitioning fits when utilizing multiple cores in one application. Remote partitioning fits when scaling workers across multiple processes or machines. Remote partitioning requires additional messaging infrastructure, message handling, retries, worker observability, and network failure management; do not choose it merely to add more threads.

## 10. Restart and checkpoints in partitioning

Each partition has its own StepExecution and ExecutionContext. When a partition fails, that partition's metadata identifies what work remains. Completed partitions are typically recognized via metadata and do not need to rerun on restart, per the Step's restart policy.

Example:

```text
Manager StepExecution: partitionCustomersStep
  |
  +--> partition0: COMPLETED
  |       worker StepExecution #1
  |
  +--> partition1: COMPLETED
  |       worker StepExecution #2
  |
  +--> partition2: FAILED
  |       worker StepExecution #3
  |
  +--> partition3: COMPLETED
          worker StepExecution #4

Restart Job
  |
  +--> Completed partitions retain status
  +--> Failed partition restarts from its checkpoint
```

For reliable restarts:

1. Partition names must remain stable across reruns of the same unit of work.
2. Data ranges must be reproduced consistently; avoid changing min/max or filter criteria between the initial run and restart.
3. Readers must save state to resume from checkpoints within each partition.
4. Writers must safely handle items retried after rollback.
5. Input data needs an appropriate snapshot or watermark so new records do not alter partition boundaries between runs.

If the Partitioner recomputes ranges based on mutated source data, gaps or overlaps can occur on restart. With continuously changing data, establish a watermark or snapshot ID for the JobInstance and use it to generate stable partitions.

## 11. How to split data for effective partitioning

Not every splitting method produces balanced load. If one partition has 10,000 items while another has 2 million items, the fast worker finishes early while the heavy worker keeps running, reducing parallel efficiency.

Common splitting strategies:

| Strategy | Example | Watch out for |
|---|---|---|
| Primary key range | IDs 1–100,000, 100,001–200,000 | Simple; wide ID gaps can make item counts uneven. |
| Time interval | Each worker processes one day or one month | Suits time-series data; handle timezones and time bounds carefully. |
| By tenant or region | Each worker processes a customer group | Avoid one huge tenant skewing load. |
| By hash key | `hash(customer_id) mod N` | Can balance well; queries and checkpoints must use the same rule. |
| By file list | Each partition receives a group of files | Easy file isolation; track completed files and handle failed files. |

When choosing partition count, consider CPU cores, connection pool capacity, database load, message broker throughput, and average processing time per slice. Creating too many partitions can generate excessive connections, transactions, and metadata, degrading performance instead of improving it.

## 12. When to use chunking, when to use partitioning?

### Use chunk processing only

Choose a single chunk-oriented Step when:

- Data volume is moderate or runtime already meets the SLA.
- Sequential processing suffices.
- The data source is hard to split into independent ranges.
- Write logic requires global ordering or splitting would cause contention.
- You want simple implementation, easy debugging, and straightforward operations.

### Use partitioning combined with chunking

Choose a partitioned Step with chunk-oriented workers when:

- Data is large and divisible into non-overlapping parts.
- Parts can be processed independently.
- Readers can accept dedicated ranges via ExecutionContext.
- The database and writers withstand concurrency.
- Per-part restartability and status observability are required.

### Consider multi-threaded Step or remote partitioning

A multi-threaded Step may fit if shared components are thread-safe and separate data ranges are unnecessary. Remote partitioning fits when distributing workers across multiple processes or machines and messaging infrastructure is already available.

## 13. Transaction and performance considerations

Partitioning does not eliminate worker transaction boundaries. If a worker is a chunk Step with a commit interval of 500, each worker manages transactions per chunk. Multiple workers can open multiple concurrent transactions, so the database must handle that load.

Risks to monitor:

- **Lock contention:** partitions may update the same table or same keys; non-overlapping splits at the Reader do not guarantee conflict-free writes at the Writer.
- **Connection pool:** each worker may need its own connection; thread counts exceeding pool size force workers to wait for connections.
- **Uneven partitions:** one partition much larger than others stretches overall Step completion time.
- **Retries and idempotency:** a failing worker may re-run items in an uncommitted chunk; writers must prevent duplicate writes.
- **Memory:** each worker holds its own reader, processor, buffers, and chunks; adding workers increases heap usage.
- **External side effects:** API calls or messages sent inside a worker do not roll back with database transactions.

Benchmark across several `gridSize` and chunk size values. Measure total throughput, slowest partition duration, connection pool usage, lock waits, rollbacks, heap, and GC. Increasing concurrency helps only when both data source and write target can serve concurrent workers.

## 14. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Chunk processing means parallel processing | Chunks only define item groups and transactions; the Step can run sequentially. |
| Partitioning replaces chunk processing | Partitioning divides workers; each worker can still use chunk processing. |
| `gridSize` is the commit interval | `gridSize` relates to partition count; commit interval is configured on the worker chunk Step. |
| Having many partitions means always running concurrently | Requires an appropriate `PartitionHandler`/executor and sufficient worker capacity. |
| `@StepScope` automatically makes a reader thread-safe in a multi-threaded Step | StepScope binds a bean to a StepExecution; threads within the same StepExecution can still share the target. |
| Splitting IDs into intervals always balances item counts | ID ranges may have large gaps or varying data density. |
| One partition failing loses data from already-committed partitions | Each worker's transactions and metadata are managed separately; committed results remain. |
| Increasing partitions always makes a Job faster | Database contention, connection pool limits, overhead, and skewed partitions can slow the Job down. |

## Conclusion

Chunk processing divides data into item groups to read, process, write, and commit per transaction. Partitioning splits a Step into multiple worker StepExecutions, each receiving a data range and its own ExecutionContext to run independently or in parallel. The two mechanisms complement each other: a Job commonly partitions data into multiple slices, and each worker processes its assigned slice in chunks. When designing, choose non-overlapping partition ranges, keep chunk size appropriate, bound concurrency to database capacity, and ensure readers/writers support restarts. Getting these two layers right scales throughput while preserving clear transaction boundaries and recoverability.
