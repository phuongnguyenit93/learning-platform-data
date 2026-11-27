# Distinguishing Remote Partitioning and Remote Chunking

**Remote partitioning** and **remote chunking** are two ways to distribute **Spring Batch** work across multiple processes (manager and workers), typically communicating over middleware such as JMS or AMQP. Both help process large datasets, but **the unit sent over the wire, where data is read, and how state is managed are completely different**. Choosing the wrong architecture can overload the manager, fill queues with huge payloads, or make error recovery and restarts hard to control.

This lesson belongs to the **Remote Partitioning** chapter of the **SPRING_CLOUD_TASK** module. Spring Cloud Task is suited for running a finite application, recording `TaskExecution` in `TaskRepository`, and reporting status/exit codes to the orchestrator. Spring Batch handles **splitting work, chunk-oriented reading/writing, and storing `JobExecution` and `StepExecution` in `JobRepository`**. This lesson focuses on distinguishing remote partitioning from remote chunking, then connecting the Batch architecture to how a Spring Cloud Task launches, tracks failures, and operates safely.

After studying this lesson, you will be able to explain why an ingestion flow should split by ID range or by item chunks, identify which components the manager and workers need, select the design that matches your performance bottleneck, and anticipate the consequences when a worker fails or a message is redelivered.

## 1. Context: From One Batch Step to Multiple Workers

A chunk-oriented processing Step typically follows this flow:

~~~text
ItemReader → ItemProcessor → ItemWriter
       (loops over chunks, with transactions/checkpoints)
~~~

For example, ingesting 10 million orders: reading records from a source database, validating, normalizing, and writing them to a target database. If one process cannot finish within the operational window, we can increase parallelism by running multiple workers. Spring Batch supports several models: multi-threaded Step, parallel Step, local partitioning, remote partitioning, and remote chunking.

**Remote** means processing parts are placed in **separate processes**, often across multiple Pods/VMs—not just adding threads inside one JVM. Middleware transfers requests and results across network boundaries. New costs appear, including message transmission, serialization, timeouts, state coordination, and error handling.

| Initial criterion | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Unit of assignment | **Partition**: a data range, accompanied by `ExecutionContext` and `StepExecution` | **Chunk**: a group of items already read by the manager |
| Who reads the source data? | **Worker**: each worker has its own `ItemReader` for the Step it runs | **Manager**: a single `ItemReader` produces chunks |
| Who processes and writes? | **Worker** runs the full Step: reader, processor, writer | **Worker** processes and writes the received items |
| Primary scaling strength | Distributes both read I/O and processing/writing | Distributes heavy processing/writing when reading is fast |
| Coordination metadata | `JobRepository` holds partitioned `StepExecution` records | Manager owns Step/Job; workers receive chunk requests |
| Payload sent via broker | Usually **partition description / StepExecution ID**, small payload | **Item data in the chunk**, which can be large |
| Bottleneck risk | Skewed partitions, shared DB overload, oversized partitions | Manager reader, broker throughput, serialization |
| Do workers need shared source access? | **Yes**, must be able to read their assigned slice (directly or via object storage) | **Not necessarily**: items already arrive in the message |

Do not conclude "remote partitioning is always faster" or "remote chunking is always easier." Effectiveness depends on the ratio of **read — process — write** time, data size, partition skew, and broker/database capacity.

## 2. Remote Partitioning: Assigning a Data Region to a Remote Step

The manager uses a **`Partitioner`** to split the input space into partitions—for example, by order ID range, business date, tenant, or file list. Each partition has a stable name such as `partition0`, `partition1` and an `ExecutionContext` containing the required parameters.

Next, `PartitionStep` on the manager creates the corresponding `StepExecution` records. A `PartitionHandler` dispatches requests to workers. A worker receives the StepExecution identifier, retrieves the relevant context from the repository, looks up the configured Step, and **executes that entire Step**.

~~~mermaid
flowchart LR
  subgraph Manager["Manager / Batch Job"]
    P["Partitioner<br/>splits IDs or files"] --> PS["PartitionStep<br/>creates StepExecutions"]
    PS --> PH["PartitionHandler"]
  end
  PH --> MQ[("Broker / middleware<br/>partition requests")]
  MQ --> W1["Worker A<br/>Reader → Processor → Writer"]
  MQ --> W2["Worker B<br/>Reader → Processor → Writer"]
  MQ --> W3["Worker C<br/>Reader → Processor → Writer"]
  W1 <--> JR[("JobRepository<br/>StepExecution + Context")]
  W2 <--> JR
  W3 <--> JR
  PS <--> JR
~~~

Suppose the input has IDs in the range `[1, 1_000_000]`:

| Partition | ExecutionContext | Worker reads | Processing range |
| --- | --- | --- | --- |
| `partition0` | `minId=1, maxId=250000` | Worker A | `1 ≤ id ≤ 250000` |
| `partition1` | `minId=250001, maxId=500000` | Worker B | `250001 ≤ id ≤ 500000` |
| `partition2` | `minId=500001, maxId=750000` | Worker C | `500001 ≤ id ≤ 750000` |
| `partition3` | `minId=750001, maxId=1000000` | Available worker | `750001 ≤ id ≤ 1000000` |

**No data rows have to travel inside coordination messages.** Workers use `minId` and `maxId` directly to query the database. This reduces network payload when workers can access the data source directly.

### 2.1. Key Components

| Component | Responsibility |
| --- | --- |
| `Partitioner` | Builds the `partitionName → ExecutionContext` map from the logical dataset |
| `PartitionStep` / `StepExecutionSplitter` | Splits the work into independent stateful `StepExecution` instances |
| `PartitionHandler` | Distributes worker Step execution requests and aggregates statuses |
| `MessageChannelPartitionHandler` | An implementation using Spring Integration `MessageChannel` for remote communication |
| `StepExecutionRequestHandler` | On the worker, handles incoming requests and executes the corresponding Step |
| `JobRepository` / `JobExplorer` | Stores and queries `StepExecution`, `JobExecution`, `ExecutionContext`, and checkpoints |

**`TaskExecutorPartitionHandler`** only runs partitions on local threads, which is useful for testing partitioning logic. To distribute across separate JVMs/Pods, you need a handler capable of **sending requests over middleware**, such as `MessageChannelPartitionHandler`.

### 2.2. ID-Range Partitioner Example

This self-contained Java snippet illustrates **how to split data** using Spring Batch's `Partitioner` API:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class OrderIdRangePartitioner implements Partitioner {

    private final long firstId;
    private final long lastId;

    public OrderIdRangePartitioner(long firstId, long lastId) {
        if (firstId < 1 || lastId < firstId) {
            throw new IllegalArgumentException("Invalid ID range");
        }
        this.firstId = firstId;
        this.lastId = lastId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = lastId - firstId + 1;
        long partitionSize = total / gridSize
                + (total % gridSize == 0 ? 0 : 1);

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        long start = firstId;
        int index = 0;

        while (start <= lastId) {
            long end = Math.min(lastId, start + partitionSize - 1);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            result.put("partition" + index, context);
            start = end + 1;
            index++;
        }
        return result;
    }
}
~~~

**Invariants to preserve:** ranges must not overlap, no ID regions are skipped, and partition names remain stable across restarts. This example assumes a finite ID domain without `long` addition overflow. With skewed data, splitting evenly by **ID span** does not guarantee equal record counts; actual data volume must be considered.

A worker can use a **Step-scoped Reader** to pull the two bounds from context:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<OrderRow> orderReader(
        DataSource sourceDataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    JdbcCursorItemReader<OrderRow> reader = new JdbcCursorItemReader<>();
    reader.setName("orderRangeReader");
    reader.setDataSource(sourceDataSource);
    reader.setSql("""
        SELECT id, amount
        FROM orders
        WHERE id >= ? AND id <= ?
        ORDER BY id
        """);
    reader.setPreparedStatementSetter(ps -> {
        ps.setLong(1, minId);
        ps.setLong(2, maxId);
    });
    reader.setRowMapper((rs, rowNum) ->
            new OrderRow(rs.getLong("id"), rs.getBigDecimal("amount")));
    return reader;
}

record OrderRow(long id, BigDecimal amount) {}
~~~

This example uses **Spring Batch 5.x / Spring Boot 3.x** syntax. Key imports: `@Bean`, `@StepScope`, `@Value`, `DataSource`, `JdbcCursorItemReader`, `BigDecimal`. You still need a processor, writer, Step, transaction manager, repository config, broker, and worker handler to have a runnable system. `JdbcCursorItemReader` here reads the ID range in ascending order; in production, verify source data stability and snapshot policies if the source changes during processing.

### 2.3. Manager/Worker Configuration at the Structural Level

`PartitionStep` example using the Spring Batch 5.x Java API:

~~~java
@Bean
Step managerStep(
        JobRepository repository,
        Partitioner partitioner,
        PartitionHandler remotePartitionHandler) {

    return new StepBuilder("orderManagerStep", repository)
            .partitioner("orderWorkerStep", partitioner)
            .partitionHandler(remotePartitionHandler)
            .build();
}
~~~

`remotePartitionHandler` must be configured to send **`orderWorkerStep`** execution requests over the broker. With Spring Batch Integration, you can use `@EnableBatchIntegration` and the remote partitioning factories/builders for your **specific version**, or configure `MessageChannelPartitionHandler` directly.

The worker implements `orderWorkerStep` with its own `ItemReader`, `ItemProcessor`, and `ItemWriter`, while receiving requests via `StepExecutionRequestHandler`. The manager does not need to send all data rows inside messages, but workers must have **access to the data source** and the **appropriate metadata repository**.

## 3. Remote Chunking: Manager Reads, Workers Receive Chunks

In **remote chunking**, the manager owns the **`ItemReader`**; each time it reads `chunkSize` items, it sends **the entire chunk of read items** over middleware. Workers are consumers that receive messages, use **`ItemProcessor` and `ItemWriter`** to process and write them, and send replies so the manager can aggregate outcomes.

~~~mermaid
flowchart LR
  subgraph Manager["Manager / Batch Step"]
    R["ItemReader"] --> CP["ChunkProvider"]
    CP --> CW["ChunkMessageChannelItemWriter"]
  end
  CW --> MQ[("Broker<br/>chunk payloads")]
  MQ --> W1["Worker A<br/>Processor → Writer"]
  MQ --> W2["Worker B<br/>Processor → Writer"]
  MQ --> W3["Worker C<br/>Processor → Writer"]
  W1 --> Dest[("Target DB / service")]
  W2 --> Dest
  W3 --> Dest
  W1 -. "reply" .-> CW
  W2 -. "reply" .-> CW
  W3 -. "reply" .-> CW
~~~

For example, the manager reads 1,000,000 orders with `chunkSize=200`. It generates at most 5,000 chunk requests, each carrying up to 200 items (depending on the trailing records). The broker distributes requests to available workers; each worker never has to query the source table to figure out "which ID range was I assigned?"

### 3.1. Key Components

| Component | Responsibility |
| --- | --- |
| Manager's `ItemReader` | Reads the source in stable order, producing items |
| `ChunkProvider` | Groups items into chunks |
| `ChunkMessageChannelItemWriter` | Converts chunks into worker requests and receives/aggregates replies |
| `ChunkProcessor` on the worker | Executes `ItemProcessor`/`ItemWriter` for the received chunk |
| `ChunkProcessorChunkRequestHandler` | Translates incoming request messages into chunk processing operations |
| `MessageChannel` / JMS / AMQP | Transports requests and replies across processes |

In the standard model, a remote chunking worker is a **message consumer**, not necessarily a full Spring Batch Job/Step. Per the Spring Batch Integration guide, workers in this architecture **do not require access to the manager's `JobRepository`** or a full Job configuration; they process the payload, manage business transactions, and send appropriate replies.

### 3.2. Manager Step Skeleton

Illustrative example of the Spring Batch 5.x Step API. `outboundChunkWriter` is a `ChunkMessageChannelItemWriter` bean configured with channels and reply handling:

~~~java
@Bean
Step chunkManagerStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> outboundChunkWriter) {

    return new StepBuilder("chunkManagerStep", repository)
            .<OrderRow, OrderRow>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(outboundChunkWriter)
            .build();
}
~~~

Unlike a local Step, **this writer does not INSERT directly into the target table**; it dispatches data to workers and coordinates results. Heavy `ItemProcessor` logic and business writers live on the workers. In versions supporting Spring Batch Integration builders, you can use `RemoteChunkingManagerStepBuilderFactory` / the corresponding builder so the framework wires `ChunkMessageChannelItemWriter`, channels, and reply handling.

The manager must control chunk size, in-flight message counts awaiting replies, and timeouts. **A single `ItemReader` on the manager can still become a bottleneck**, especially when the source query is slow or items require heavy preprocessing during reads.

### 3.3. Considerations for Data-Carrying Messages

Remote chunking sends **item payloads**, so serialization is critical:

- Data types sent over the broker must have compatible formats and schema versions.
- Payloads must be size-bounded; larger chunks are not always faster.
- Avoid putting passwords, tokens, or unnecessary personal data into messages.
- Workers must authenticate message sources, restrict publish/consume permissions, and secure transport.
- When brokers/workers redeliver messages, the writer must support **idempotency**.

For data containing large binary files, it is usually better to send **immutable object references** or use partitioning so workers fetch the source directly rather than packing entire contents into a message.

## 4. Visual Comparison: What Actually Travels Across the Broker?

Suppose both approaches process 1,000,000 transactions:

~~~text
REMOTE PARTITIONING
Manager:
  partition0: minId=1,      maxId=250000
  partition1: minId=250001, maxId=500000
  partition2: minId=500001, maxId=750000
  partition3: minId=750001, maxId=1000000
  → sends 4 StepExecution requests (range description + ID)

Worker:
  → SELECTs its ID range itself
  → processes + writes in internal chunks
  → updates StepExecution/ExecutionContext


REMOTE CHUNKING
Manager:
  → SELECTs and reads items
  → splits into chunks of 200 items
  → sends ~5,000 messages containing items

Worker:
  → receives one chunk of 200 items
  → processes + writes
  → returns reply to manager
~~~

**The numbers 4 partitions and 5,000 chunks are purely illustrative.** In partitioning, `gridSize` is a hint for the number of partitions/split granularity, not a promise that there are that many physical workers. In chunking, message count depends on the actual item count and chunk size, plus retries/redeliveries on failure.

| Decision question | Remote partitioning | Remote chunking |
| --- | --- | --- |
| "Where is the Reader?" | On the worker | On the manager |
| "What does the broker carry?" | StepExecution/range references | Chunk items |
| "Who owns the start/end of the data range?" | Partitioner, StepExecution, and ExecutionContext | Manager's reader/checkpoint |
| "How does a worker know what slice to read?" | `stepExecutionContext` holds range parameters | No need to split source; items arrive in the message |
| "What happens with imbalance?" | An oversized partition can make one worker run much longer | Dispatching chunk by chunk often balances load dynamically better |
| "Network pressure?" | Low coordination payload, but each worker reads the source | Item payloads over the broker scale with item count/chunk size |
| "Scaling source reads?" | Readers can be distributed | Manager reader remains centralized |

## 5. Distinct Roles of JobRepository, StepExecution, and TaskRepository

Integrating Spring Cloud Task with Spring Batch introduces **two layers of metadata**:

~~~mermaid
flowchart TD
    L["Launcher: Cron / API / workflow"] --> T["Spring Cloud Task process"]
    T --> TR[("TaskRepository<br/>TaskExecution")]
    T --> BJ["Spring Batch JobLauncher"]
    BJ --> JR[("JobRepository<br/>JobExecution + StepExecution")]
    BJ --> M["Manager Step"]
    M --> B[("Broker")]
    B --> W["Workers"]
    W -. "updates step / sends reply" .-> JR
~~~

This diagram illustrates remote partitioning; in **remote chunking**, workers typically send replies back to the manager via the broker and **do not need** to write `StepExecution` records to the same `JobRepository` as partitioning workers do.

### 5.1. Metadata in Remote Partitioning

The manager creates a **StepExecution** per partition, with names like `workerStep:partition0`, `workerStep:partition1` within the same `JobExecution`. Each partition's `ExecutionContext` records its read range and Step checkpoints. A worker processes its assigned `StepExecution` and updates outcomes through the repository.

The manager aggregates `StepExecution` results into the manager step's status, including read/write item counts and failed partitions. When restarting the **same JobInstance** with identical identifying JobParameters, already-completed partitions are normally skipped; failed partitions can re-run under Batch restart rules as long as partition names, data ranges, and the repository remain consistent.

**Do not equate Step metadata with external exactly-once guarantees.** If a worker sends emails or calls external APIs, a failure between the external action and checkpoint commit can cause side effects to run again.

### 5.2. Metadata in Remote Chunking

The manager runs a chunk-oriented Step, owns the reader/checkpoint, and aggregates replies. Workers receive/run a **ChunkProcessor**, so there is not necessarily a separate Batch `StepExecution` per chunk. Primary Job/Step state resides on the manager and its `JobRepository`.

If a reply is lost, the manager may not know whether the worker already wrote to the target. Proper recovery therefore requires durable queues/brokers and appropriate reconciliation, retries, and idempotent writes. **A redelivered message does not prove the previous chunk was never written.**

### 5.3. Spring Cloud Task Lifecycle

Spring Cloud Task tracks **processes with a finite lifetime**. When the manager is packaged as a Task, it must wait for remote Job/Step outcomes before marking itself finished. If a runner launches work asynchronously and returns immediately, `TaskExecution` may succeed or end prematurely while workers are still running.

If workers run as **long-lived message consumers**, they behave like broker-listening services rather than naturally finite Spring Cloud Tasks. Some systems use a launcher/deployer to **spawn workers as finite processes**, which requires custom design for stop conditions, timeouts, and result reporting. **There is no `spring.cloud.task.remote-chunking=true` or `spring.cloud.task.remote-partitioning=true` property that magically turns a regular Task into either model.**

## 6. Failure Flows and Restarts: Where Do They Differ?

### 6.1. Remote Partitioning

~~~mermaid
flowchart TD
  P["Manager splits partition0..3"] --> R["Dispatch requests to workers"]
  R --> C{"StepExecution outcome?"}
  C -->|COMPLETED| S["Record partition metadata as completed"]
  C -->|FAILED| F["Job fails or follows configured flow"]
  F --> J["Restart same JobInstance"]
  J --> K["Identify completed partitions and partitions to re-run"]
  K --> R
~~~

Suppose there are 4 partitions: `partition0`, `partition1`, `partition3` complete; `partition2` fails. With a persistent repository, stable partitioning logic, and a restartable Step, Spring Batch can **re-run only the unfinished portion**. Each worker must still enforce transaction/chunk checkpoints and idempotency for any side effects.

If the `Partitioner` code changes between the first run and the restart so partition names or ranges no longer match, the system may reprocess or miss data. Anchor inputs to a version/checksum or stable snapshot; never re-partition arbitrarily when restarting the same `JobInstance`.

### 6.2. Remote Chunking

~~~mermaid
flowchart TD
  M["Manager reads and sends chunk #42"] --> Q[("Broker")]
  Q --> W["Worker writes 200 items"]
  W --> X{"Reply to manager?"}
  X -->|Yes| A["Manager updates progress / continues"]
  X -->|Lost reply| U["Uncertain whether worker finished writing"]
  U --> V["Recovery / redelivery / reconciliation"]
  V --> I["Idempotent writer and business keys"]
~~~

If a worker commits 200 items but its reply is lost, a retry mechanism may resend the chunk. Never rely on a "messages are processed only once" assumption for correctness. You must choose an appropriate broker, transaction boundaries, deduplication keys, or `UPSERT`/unique constraints at the write target.

Spring Batch documentation requires remote chunking middleware to provide **durable storage and reliable delivery to a single consumer**. Competing-consumer work queues fit better than broadcast channels that deliver the same chunk to every worker.

### 6.3. Recovery Comparison

| Question | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Can you tell which partition FAILED? | **Yes**, via each partition's `StepExecution` | **No partitions**; tracked by Step/chunk and request/reply |
| What needs to be replayed? | Execution command for a partition, with `StepExecution` and context | Sent item chunk or items re-read by the reader |
| Do workers have their own Step checkpoints? | Yes, if the Step is configured as restartable | Workers only process chunks; primary checkpoint is on the manager |
| How are duplicate writes avoided? | Batch metadata + transactions/business idempotency | Broker/reply correlation + idempotent writer |
| What if a worker loses connection? | Inspect `StepExecution` status, recover/restart the partition | Watch out for in-flight chunks and potentially lost replies |
| `JobRepository` requirement? | Workers generally need access to the shared metadata repository | Workers do not strictly need `JobRepository` |

**Scope of guarantees:** Batch metadata controls restarts and prevents re-running already `COMPLETED` Steps within a `JobInstance`, but both architectures must independently handle non-transactional data, network retries, and irreversible side effects.

## 7. When to Choose Which Model?

### 7.1. Choose Remote Partitioning When...

- Inputs **naturally split into independent regions**: per file, per tenant, per day, primary key ranges, or shards.
- Reading source data is a bottleneck and workers can read in parallel using proper indexes/snapshots.
- You want progress/failure tracking at the **per-region `StepExecution` level**.
- You want to leverage internal chunk checkpoints inside each worker Step.
- Input payloads are large; sending records through a broker wastes bandwidth and serialization CPU.

Example: 200 large files stored in object storage, each structured independently and directly downloadable by workers. The `Partitioner` creates partitions with `objectKey`/version, and workers download, parse, validate, and write results themselves. If one file fails, only its corresponding partition needs to restart under restart rules.

### 7.2. Choose Remote Chunking When...

- A single reader can read data **quickly and reliably**, while processing/writing is CPU- or I/O-intensive.
- Inputs are hard to divide cleanly into independent readable ranges.
- You want **dynamic** distribution: whichever worker is free grabs the next chunk from the broker.
- Item and chunk sizes are small enough to fit message limits and network bandwidth.
- You already have durable broker infrastructure, request/reply correlation, latency monitoring, and an idempotent writer.

Example: quickly scanning a table of product IDs, where each product then requires calling a CPU-heavy analytics service. The manager just reads and distributes chunks; workers process and persist results.

### 7.3. Evaluating Bottlenecks by Measurement

Before choosing, benchmark with representative data:

| Metric | Meaning |
| --- | --- |
| `read items/sec` at manager/worker | Is the reader the limiting factor? |
| `process ms/item` | Is processing heavier than reading? |
| `write ms/item` and DB connection count | Could workers overload the target DB? |
| Payload/chunk size and serialization time | Does remote chunking fit network/broker limits? |
| Item count skew across partitions | Will one remote partitioning worker lag far behind? |
| Queue depth, consumer lag, reply timeout | Do the broker and workers have sufficient capacity? |
| Restart duration and reprocessed row count | What is the recovery cost on failure? |

If you lack metrics, start with a **correct local Step**, test scaling workers in a controlled environment, and then decide if remote execution is warranted. Premature distribution can raise operational overhead without improving throughput.

## 8. Safe Data and Partition Design

### 8.1. Partition Names and Ranges Must Be Stable

Keys like `partition0`, `partition1`, ... correlate `StepExecution` records across restarts. When partitioning by file, use a file list with fixed identifiers/versions. When partitioning by ID range, establish a **high-water mark** when locking the dataset; avoid unexpected input mutations while workers are running.

Example partition context:

~~~text
partitionName=partition2
inputSnapshot=orders-2026-11-23-v1
minId=500001
maxId=750000
~~~

If the source mutates during execution, you need a snapshot policy, source freeze, or acceptance that newly arriving rows wait for the next run. Non-overlapping ranges keep partitions from processing the same row, but verify actual SQL filters—especially when combining conditions beyond ID.

### 8.2. Chunk Size Is Not Partition Count

`gridSize`/partition count determines the **number of logical work regions** dispatched to workers. Inside each worker partition, a Step still processes with an internal **chunk size = 100 or 500**. Remote chunking uses **chunk size** to decide how many items travel in **each message**.

~~~text
Remote partitioning:
  4 partitions × multiple internal chunks per Step

Remote chunking:
  1 manager reader/Step → many requests, each carrying one chunk
~~~

Setting `gridSize` too high creates excessive `StepExecution` records, management overhead, and metadata repository load. Setting chunk size too high creates long transactions, huge broker messages, costly retries, and delayed feedback. These two knobs act on **two different layers**.

## 9. Infrastructure, Deployment, and Security

### 9.1. Minimum Required Components

| Component | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Manager with `JobLauncher` / `JobRepository` | Required | Required |
| Broker/message transport | Required for multi-JVM remote | Required for multi-JVM remote |
| Worker with reader | Required | Typically not needed |
| Worker with processor/writer | Required | Required |
| Worker with matching JobRepository/JobExplorer | Usually required to handle StepExecution | Not required in standard model |
| Batch metadata schema | Partitioning manager and workers must coordinate consistently | Used by manager; chunking workers may not need it |
| Retries, timeouts, business idempotency | Essential | Essential |
| Job/Task launcher and monitoring | Essential | Essential |

In Spring Boot, use compatible BOM versions across Spring Batch, Spring Integration, and Spring Cloud Task. Relevant modules may include `spring-batch-integration`, `spring-integration-jms` or `spring-integration-amqp` adapters, plus JDBC drivers and required starters. Merely adding dependencies without **queues, channels, reply mappings, and worker configuration** will not establish remote processing.

### 9.2. Why Messages Must Be Protected

- Encrypt transport and authenticate workers/managers with the broker.
- Grant publish/consume permissions only to specific queues; isolate request/reply queues across environments.
- Enforce payload limits, message TTLs, and dead-letter queue policies aligned with recovery procedures.
- Exclude tokens, passwords, and unnecessary personal data from payloads and logs.
- Version serializers/schemas when managers and workers undergo rolling updates at different times.
- Ensure correlation IDs and required headers are preserved across adapters, especially on reply flows.

**Recent version note:** in the Spring Batch 6.1 guide, when using **JMS**, you must configure `DefaultJmsHeaderMapper` to preserve Spring Integration headers used for correlation/aggregation such as `correlationId`, `sequenceNumber`, and `sequenceSize`; if stripped, the manager may fail to match replies. Use an explicit allowlist only when supported by your transport/version:

~~~java
new DefaultJmsHeaderMapper(
        "correlationId", "sequenceNumber", "sequenceSize");
~~~

Do not open all headers with `"*"` unless security requirements permit it. For AMQP or other adapters, verify header mapping using their corresponding mechanisms.

### 9.3. Which Process Is Finite?

When using **Spring Cloud Task** as the manager, the `TaskExecution` represents the lifecycle of **a single Batch Job run**, completing only after the Job and workers have finished or been determined to have failed. Continuously listening worker services are commonly deployed as long-running services or managed with dedicated launch and stop policies.

Do not assume `@EnableTask` on a worker is enough to make it exit automatically once messages run out. If you want workers to be finite Tasks too, you must design policies for **processed request count, deadlines, queue draining, graceful shutdown**, and exit status reporting before process termination.

### 9.4. Ensuring Correct Exit Codes for the Scheduler

A `JobExecution` can end with `BatchStatus.FAILED` while the Java process still exits with code `0` if the application does not propagate the failure to the orchestrator. With compatible Spring Cloud Task–Batch integration, consider setting `spring.cloud.task.batch.fail-on-job-failure=true`. If invoking `JobLauncher` manually, always check Job status and throw an exception or set a non-zero exit code on failure.

Manager timeouts must account for worker execution wait times, retries, and replies; never mark a `TaskExecution` successful merely because it **finished sending messages**.

## 10. Observability and Troubleshooting

### 10.1. Metadata to Track

| Layer | Observable data |
| --- | --- |
| Spring Cloud Task | `TaskExecution ID`, Task name, runtime, `EXIT_CODE`, `EXIT_MESSAGE` |
| Spring Batch manager | `JobExecution ID`, JobInstance, manager StepExecution, final status |
| Remote partitioning | Partition name, StepExecution ID, context/range, read/write counts, per-Step errors |
| Remote chunking | Chunk request ID/correlation ID, sent/acked message counts, queue lag, reply timeouts |
| Worker | Worker ID/Pod, processing duration, read/write errors, retries/deduplication |
| Business | Business keys, total record counts, checksums, source-vs-target reconciliation |

`TASK_EXECUTION` belongs to `TaskRepository`, while `BATCH_JOB_EXECUTION` and `BATCH_STEP_EXECUTION` belong to `JobRepository`. Do not directly assume `TaskExecution ID = JobExecution ID`. When using Task–Batch integration with linking enabled, trace via `TASK_TASK_BATCH` or `TaskExplorer` APIs; if links are absent, log correlation IDs for cross-referencing.

### 10.2. Common Symptoms

| Symptom | First place to check |
| --- | --- |
| Remote partitioning runs only one worker | Actual partition count, `gridSize`, queue consumers, worker source connectivity |
| One partition runs much longer than others | Skewed data range, query indexes, hot data, transaction/chunk sizing |
| Remote partitioning worker cannot find StepExecution | `JobExplorer`/`JobRepository` config, DB/schema, Step name, request ID |
| Remote chunking manager reads fast but Job stalls | Queue backlog, dead workers, reply correlation, timeouts |
| Worker writes data but manager triggers retry | Lost reply/ack; verify idempotency and broker state |
| Duplicate data appears after restart | Missing unique constraints/idempotent writes or overlapping partition ranges |
| `JobExecution` FAILED yet Task exit code is 0 | Missing propagation of Batch failure to Task/launcher |
| Task ends while workers are still running | Asynchronous runner/`JobLauncher` not waiting for completion |
| Queue holds oversized messages | Chunk size too large, serializer pulling unnecessary object graphs |

Never treat a `StepExecution` with a null `END_TIME` as proof that the worker is still alive; it may have been killed before updating the repository. Cross-check Pod/Job/consumer status, broker state, and logs to be certain.

## 11. Decision Matrix with Real-World Scenarios

| Problem | Recommended model | Reason |
| --- | --- | --- |
| 100 independent CSV files on object storage | **Remote partitioning** | Assign per file; workers read directly and track `StepExecution` |
| One lightweight query, each item needs heavy image analysis | **Remote chunking** | Manager reads quickly; workers distribute heavy CPU work |
| Each tenant has its own table or shard | **Remote partitioning** | Each partition binds to a tenant/shard, removing centralized reader contention |
| Single very slow data source that cannot be split | Hold off on remote chunking | Manager reader remains the bottleneck; optimize the source first |
| Slow target writes, small items, fast reads | **Remote chunking** can work well | Workers share processing/write load within target DB limits |
| Data lake with heavily skewed regions | **Remote partitioning with load-balanced design** | Partition by actual data size, possibly creating more smaller regions |
| Broker enforces small payload limits, workers can reach source | **Remote partitioning** | Only range metadata travels in messages |
| Multiple processes unnecessary, one machine handles the load | **Local Step** | Avoids broker overhead, remote debugging, and operational complexity |

Neither model provides **exactly-once** guarantees by default for side effects outside transactions. For both models, design output tables with appropriate unique keys, handle replays, and establish post-failure reconciliation procedures.

## 12. Practice Exercises

An e-commerce platform has 4 million orders, each containing `orderId`, `tenantId`, and `amount`. The goal is to aggregate and normalize the data overnight. You have 4 worker Pods, PostgreSQL, RabbitMQ, and Spring Cloud Task orchestrating the manager process.

### Part A — Implementing Remote Partitioning

1. Design a `Partitioner` splitting IDs into 8 independent regions with stable partition names.
2. Put `minId` and `maxId` into `ExecutionContext`; use `@StepScope` so the worker Reader receives the exact range.
3. Use a chunk-oriented Step on the worker; persist state to a `JobRepository` accessed by both manager and workers.
4. Simulate `partition3` failing after committing several chunks; restart the **same JobInstance** and observe which `StepExecution`s re-run.
5. Prove zero omissions/duplicates via ID counts, checksums, or unique keys.

### Part B — Implementing Remote Chunking

1. Place the Reader on the manager with `chunkSize=200`, sending items over a queue.
2. Workers receive chunks, process, and write to the target; replies return to the manager with matching correlation IDs.
3. Simulate a worker committing and then losing its reply; analyze chunk redelivery risks and design an idempotent writer.
4. Scale from 2 to 4 workers; measure throughput, queue depth, message size, and database load.
5. Compare network/broker overhead against the partitioning model.

### Part C — Connecting to Spring Cloud Task

1. Launch the manager as a finite Task and record its `TaskExecution ID`.
2. Link `TaskExecution` to `JobExecution` or maintain searchable correlation IDs.
3. Intentionally fail a Step/worker; verify that a FAILED Batch Job leads to a **non-zero Task exit code**.
4. Verify that the manager **waits for worker completion**, rather than exiting right after sending messages.
5. Build a comparison table covering **dispatched unit, reader location, worker role, metadata, retry, and idempotency**.

**Passing criteria:** explain why a remote partitioning worker typically requires `JobRepository` and source read access, whereas a remote chunking worker receives items directly from the broker and may not need the manager's `JobRepository`. Identify one scenario where each model is the right choice and one retry failure that requires business-level mitigation.

## 13. Key Takeaways

1. **Remote partitioning** distributes **`StepExecution`/`ExecutionContext` representing data regions**; workers execute the full Step—reading, processing, and writing themselves.
2. **Remote chunking** distributes **chunks of items already read by the manager**; workers process/write and send replies back for manager aggregation.
3. Partitioning suits data that **splits independently and needs read I/O scaling**; chunking suits cases where **manager reads are fast and processing/writing is heavy**.
4. Remote partitioning tracks **per-partition `StepExecution`** in `JobRepository`; remote chunking centralizes Step/Job metadata on the manager and relies on accurate request/reply correlation.
5. Both models require **transaction boundaries, timeouts, retries, observability, and idempotency**. Batch and broker metadata alone do not guarantee exactly-once behavior for APIs or non-transactional targets.
6. Spring Cloud Task manages **finite runs and process outcomes**; Spring Batch manages **Jobs/Steps/partitions/chunks**. When combining them, ensure the Task never exits before the Job/workers finish.
7. Before going remote, measure **reader throughput, process/write time, payload size, partition skew, and DB/broker capacity**.

### Official References

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Batch Reference — Spring Batch Integration: Remote Chunking and Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/externalizing-execution.html)
- [Spring Cloud Task Reference — Spring Batch Integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Batch Reference 5.2 — Externalizing Batch Process Execution](https://docs.spring.io/spring-batch/reference/5.2/spring-batch-integration/externalizing-execution.html)
