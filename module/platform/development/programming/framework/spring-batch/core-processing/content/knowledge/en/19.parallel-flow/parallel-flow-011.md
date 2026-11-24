# When to Use the Scaling Module Instead of Core Flow

Spring Batch offers several ways to run work in parallel. For independent Steps within the same Job, you can use **core flow** and the split operator to run multiple flows concurrently. When processing needs to be distributed across multiple processes or multiple hosts, you can use the integration patterns in **Spring Batch Integration**, often referred to in this context as the scaling module.

The two approaches solve two different problems. Core flow orchestrates execution branches inside a single Spring Batch application. Spring Batch Integration adds communication mechanisms via message channels or middleware so the manager and workers can run separately. Choose the integration module when scaling requirements exceed a single JVM or when remote chunking/remote partitioning models are needed; do not add the module just to run two independent Steps in parallel.

## 1. How do core flow and the scaling module differ?

Spring Batch Core provides the foundational abstractions for building Jobs, Steps, Flows, chunk processing, partitioning, and in-application concurrency. Core flow can use split to run multiple flows in parallel via TaskExecutor.

Spring Batch Integration is an add-on module connecting Spring Batch with Spring Integration. It supports work distribution patterns over message channels, such as remote chunking and remote partitioning. Workers can run in separate processes or on separate machines, depending on messaging and infrastructure deployment.

| Criterion | Core flow | Spring Batch Integration |
| --- | --- | --- |
| Primary goal | Orchestrate Steps/flows inside one Job | Distribute work between manager and workers via messaging |
| Execution scope | Usually within the same application/JVM | Can span multiple processes or nodes |
| Coordination mechanism | Flow transitions, split, and TaskExecutor | Message channels, adapters, and middleware |
| Common patterns | Parallel flow, local multi-threading, local partitioning | Remote chunking, remote partitioning |
| Operational complexity | Lower when all components live in one application | Higher due to managing messages, workers, and communication |
| Suitable cases | Independent branches or scaling within one JVM | Horizontal scaling and load distribution across multiple nodes |

Important distinction: Spring Batch Integration does not replace Spring Batch Core. The integration module builds on Core abstractions and adds ways to connect a manager with remote workers.

## 2. When core flow is enough

Core flow is suitable when tasks can run inside the same application and no message broker is needed to distribute processing.

For example, a Job needs to produce three independent datasets after validating input:

- Compute total revenue.
- Update customer metrics.
- Generate reconciliation data.

The three branches do not depend on each other's outputs, so they can run in parallel and wait for completion before running the aggregation Step.

~~~text
                 +--> calculateRevenueFlow --+
                 |                           |
validateInput ---+--> updateCustomerFlow -----+--> summarizeStep
                 |                           |
                 +--> reconcileFlow ----------+
~~~

Example core flow configuration with Spring Batch 5:

~~~java
@Bean
public Job reportingJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step calculateRevenueStep,
        Step updateCustomerStep,
        Step reconcileStep,
        Step summarizeStep,
        TaskExecutor taskExecutor) {

    return new JobBuilder("reportingJob", jobRepository)
            .start(validateInputStep)
            .split(taskExecutor)
            .add(
                    new FlowBuilder<SimpleFlow>("revenueFlow")
                            .start(calculateRevenueStep)
                            .build(),
                    new FlowBuilder<SimpleFlow>("customerFlow")
                            .start(updateCustomerStep)
                            .build(),
                    new FlowBuilder<SimpleFlow>("reconcileFlow")
                            .start(reconcileStep)
                            .build())
            .next(summarizeStep)
            .end()
            .build();
}
~~~

In this example, validateInputStep is the first step of the Job. Then three flows run concurrently via TaskExecutor. The Job moves to summarizeStep only after the split branches complete.

Core flow is especially suitable when:

- Steps are independent and only need to run concurrently.
- Data can be shared through the database or shared resources.
- All workers can run inside the same application.
- Processing load stays within one node's CPU, memory, connection pool, and I/O limits.
- Operations teams prefer deploying and monitoring a single application rather than adding a broker and worker services.

### Split is not data partitioning

Split runs multiple independent flows in parallel. It does not automatically split items from a single reader into multiple data ranges.

If you need to split a table into multiple ID ranges for multiple workers to process, consider partitioning. Spring Batch Core already includes Partitioner and a local PartitionHandler to perform partitioning within the same application. Only consider messaging integration when remote workers are required.

## 3. Scaling options already available in Spring Batch Core

Before adding the integration module, determine whether one of Core's built-in mechanisms already solves the problem.

| Core mechanism | How it scales | Suitable when |
| --- | --- | --- |
| Parallel flow with split | Runs independent flows/Steps concurrently | Multiple branches of work have no mutual dependencies |
| Multi-threaded Step | Multiple threads collaborate on processing one Step as configured | Work inside a Step can run concurrently and components are concurrency-safe |
| Local partitioning | Splits data into partitions, runs worker Steps in the same JVM | One Step needs to divide data into multiple independent ranges |
| Sequential chunk Step | Improves performance by tuning reader, processor, writer, and chunk size | Concurrency is not needed yet or bottlenecks can be tuned locally |

Example of local partitioning:

~~~java
@Bean
public Step managerStep(
        JobRepository jobRepository,
        Step workerStep,
        Partitioner partitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

This is still a Spring Batch Core capability. If eight workers can run in the same JVM and the database has capacity to serve them, there is no need for remote partitioning merely to achieve concurrency.

## 4. When should you use Spring Batch Integration?

Consider Spring Batch Integration when the problem requires load distribution or separating manager/worker lifecycles across processes:

- One node lacks enough CPU, memory, or I/O for the data volume.
- Multiple workers can be deployed across multiple hosts or containers.
- You want to scale workers independently from the manager.
- Workers can receive work via message channels or a broker.
- You want to leverage existing messaging infrastructure in the system.
- You want to decouple where data is read from where data is processed/written.
- You need to process multiple independent partitions across different nodes.

For example, the manager reads a large dataset while per-item processing is CPU-intensive. You can send chunks to workers for parallel processing. Or the manager splits data by tenant, date, or key range and dispatches each partition to a worker that reads and writes data for that range itself.

The integration module does not automatically make a Job faster. It provides communication and distribution mechanisms. Performance improves only when workers have sufficient resources, work is parallelizable, bottlenecks are distributed, and messaging overhead does not outweigh processing gains.

## 5. Remote chunking: manager reads, workers process chunks

Remote chunking fits when the manager can read data and send chunks to workers via messaging. Workers receive chunks, process them, and write results.

~~~text
Manager process
    |
    +-- ItemReader
    |
    +-- create chunks
    |
    v
Request channel / message broker
    |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
Worker A            Worker B            Worker C
    |                  |                  |
    +-- Processor      +-- Processor      +-- Processor
    +-- Writer         +-- Writer         +-- Writer
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                Reply / completion
                       |
                       v
                 Manager Step
~~~

In this model:

- The manager owns the ItemReader and builds chunks.
- The manager sends chunks over a message channel.
- Workers receive chunks and run the assigned processing, typically processor and writer.
- Results or completion signals are returned so the manager can track progress.

Remote chunking fits when:

- Reading data on the manager is not the main bottleneck.
- Processor or writer is the most resource-intensive stage.
- Chunks can be serialized and sent across middleware.
- Workers can process chunks independently.
- The system tolerates message delivery semantics and has retry/deduplication handling.

Key limitation: the reader still runs on the manager. If reading data is the bottleneck, adding more workers will not significantly increase read throughput. In that case, remote partitioning or a read-splitting strategy may be a better fit.

## 6. Remote partitioning: manager splits ranges, workers read directly

Remote partitioning fits when data can be divided into independent partitions. The manager builds an ExecutionContext per partition and sends worker Step execution requests. Workers receive their range and read, process, and write data themselves.

~~~text
Manager process
    |
    v
Partitioner
    |
    +--> partition 0: ID 1-100000
    +--> partition 1: ID 100001-200000
    +--> partition 2: ID 200001-300000
    |
    v
Messaging / broker
    |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
Worker A            Worker B            Worker C
    |                  |                  |
  Reader             Reader             Reader
    |                  |                  |
  Processor          Processor          Processor
    |                  |                  |
  Writer             Writer             Writer
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                Worker Step status
                       |
                       v
                 Manager Step
~~~

Remote partitioning fits when:

- The data source can be divided into independent ranges.
- Reader, processor, and writer all need to scale.
- Workers can access the corresponding data source or resources.
- Partitions can be stably identified and reconstructed.
- JobRepository can be shared or configured properly to track worker StepExecutions.

For example, partitioning by ID range lets each worker query the database with its own range predicate. Ensure ranges do not overlap and source data stays stable during the run.

## 7. Choosing remote chunking or remote partitioning?

Both patterns use messaging to distribute work, but place data-reading responsibility in different locations:

| Criterion | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Reader | Manager reads data | Each worker reads its own range |
| Unit dispatched | Chunk of items | Partition metadata/Step execution request |
| Worker executes | Processes and writes chunks | Runs worker Step for the partition |
| When appropriate | Processor/writer is the bottleneck | Need to scale both reading and processing by data slice |
| Main requirement | Chunks are transportable and workers process independently | Partitioner creates stable ranges, workers can access source |
| Potential remaining bottleneck | Manager reader and message dispatch channel | Shared database or data source |

Neither pattern is universally faster. Choose based on where time is spent, how data is accessed, and how work can be split.

## 8. Integration module dependencies and configuration

When remote chunking or remote partitioning is needed, manager and worker applications need the Spring Batch Integration dependency compatible with their Spring Batch Core version.

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-integration</artifactId>
</dependency>
~~~

If the project uses Spring Boot dependency management, let the BOM manage compatible versions. If managing versions manually, align spring-batch-integration with spring-batch-core and compatible Spring Integration versions. Do not mix mismatched versions arbitrarily.

The integration module uses Spring Integration components such as message channels, messaging adapters, and endpoints to connect manager and workers. Exact configuration details depend on the Spring Batch version, broker, and deployment model. Builders/adapters for remote chunking and remote partitioning have evolved across API generations, so consult documentation matching your project's exact version.

Do not add spring-batch-integration just to call split() or use a TaskExecutor inside a Step. Those capabilities belong to Spring Batch Core.

## 9. Remote deployment architecture

When manager and workers run in separate processes, clearly define each side's responsibilities and resources.

### Manager

The manager is typically responsible for:

- Initializing the Job and orchestrating flows.
- Reading data and sending chunks in remote chunking.
- Or generating partitions and sending worker requests in remote partitioning.
- Monitoring results, timeouts, and execution statuses.
- Coordinating restarts based on metadata.

### Worker

Workers are typically responsible for:

- Receiving messages or partition requests.
- Initializing appropriate processing components.
- Running processor/writer or the entire worker Step.
- Committing data under the worker's transaction.
- Sending results or updating status for manager tracking.

### Middleware

The message broker or transport must support:

- Routing requests to workers.
- Dispatching messages according to processing capacity.
- Durability or message persistence matching requirements.
- Acknowledgements, redelivery, and retries.
- Backpressure or bounding in-flight/queued messages.
- Observability of queue depth, delivery counts, and consumer health.

Remote workers do not automatically have access to beans or objects in the manager's JVM. Data sent over the wire must use serializable message formats; never pass connections, EntityManagers, resource handles, or in-memory-only objects directly.

## 10. Choosing based on the actual bottleneck

Before switching to the scaling module, measure the system to locate what limits throughput:

| Bottleneck | Approach to consider |
| --- | --- |
| Independent Steps waiting on each other needlessly | Core flow with split |
| One sequential Step with light processor, database has headroom | Try core concurrency/local partitioning |
| CPU-bound processor, fast-enough reader | Remote chunking or local multi-threading |
| Reader/database query is the bottleneck | Remote partitioning if source is splittable; optimize queries/indexes first |
| Writer constrained by database | Optimize batch writes, transactions, and schema; adding workers may worsen the bottleneck |
| Single node lacks resources | Remote partitioning/chunking to distribute across nodes |
| Multiple workers contending on one table | Redesign partition boundaries and access patterns before scaling |

Do not jump to remote execution solely because item counts are high. A Job reading 20 million rows that mostly waits on one slow query may simply need query tuning or key-based partitioning. If serialization and message transport overhead are high, remote chunking can even be slower than local processing.

## 11. Transactions and message delivery

When manager and workers communicate through a broker, a message can be redelivered if a consumer fails, an acknowledgement is lost, or the broker redelivers after a timeout. Therefore, never assume a message is processed exactly once.

Key principles:

- Design idempotent processors/writers.
- Attach stable message IDs or partition IDs to requests.
- Persist processing state to recognize already-completed messages.
- Define whether acknowledgement occurs before or after worker data commits.
- Never assume the manager's transaction spans worker transactions in other processes.
- Use outbox/inbox or transaction coordination when guarantees across database and broker are needed.

In remote chunking, the manager may send a chunk and miss the reply because the worker finished processing and then lost connectivity. On message retry, a worker can receive the same chunk again. Writers must recognize already-processed chunks/messages or use unique business keys to avoid duplicate writes.

In remote partitioning, a worker may have already committed several chunks of a partition before its process stopped. On restart, the worker must restore its StepExecution checkpoint and resume the exact range. Partition names, ExecutionContexts, and input snapshots must remain stable.

## 12. Failures, retries, and restarts in distributed models

Adding middleware introduces new operational failure modes:

- Workers fail to start or stop mid-run.
- Messages sit in queues too long.
- A request is sent but the reply is lost.
- The broker becomes temporarily unavailable.
- A worker finishes processing before the manager updates the result.
- A partition is re-dispatched after a timeout.

Distinguish item-level business errors from transport errors and worker errors:

| Error type | Typically appropriate handling |
| --- | --- |
| Invalid item data | Skip/reject per Step policy |
| Temporarily unavailable database | Bounded retries with backoff |
| Worker disconnected | Messaging redelivery/retry with idempotency |
| Non-deserializable message | Quarantine or DLQ, alert operations |
| Worker configuration error | Stop and fix configuration |
| Partition exceeds expected duration | Investigate worker, queries, locks, and resources; never retry endlessly |

JobRepository remains a critical source for tracking JobExecution and StepExecution. With remote partitioning, configure workers to update StepExecution status via metadata mechanisms observable by the manager. With remote chunking, track both manager-side Step progress and message/worker processing state per design.

Restarts do not automatically undo side effects already performed on workers. Verify committed data before re-dispatching chunks or partitions.

## 13. Backpressure and concurrency limits

Horizontal scaling does not mean more workers are always better. If the manager dispatches messages faster than workers process them, queues grow continuously, latency rises, and queued payloads consume memory or storage.

Limits to design:

- Active worker count.
- Maximum queued or in-flight messages.
- Chunk size and message payload size.
- Database connections per worker.
- Broker consumer concurrency limits.
- Manager read and dispatch rate.
- Mean and tail-percentile worker processing times.

For example, if the manager dispatches 500 chunks/minute while all workers combined handle only 300 chunks/minute, backlog grows by 200 chunks every minute. Adding workers can help if CPU/database still has headroom; if the database is saturated, adding workers only intensifies contention.

Monitor queue depth, oldest message age, worker throughput, error rates, database connection usage, and partition durations before scaling concurrency up or down.

## 14. Serialization and message size

Remote chunking sends item data across the transport. Items or chunks must therefore have serializable representations on both ends.

Notes:

- Use stable DTO/message contracts; do not send objects attached to a persistence context.
- Avoid oversized payloads; pass business keys or references if workers can fetch the data.
- Ensure manager and workers use compatible contract versions.
- Have a message versioning strategy for rolling deployments.
- Do not put secrets or sensitive data into messages unnecessarily.
- Configure safe serialization and authenticate message senders.

Remote partitioning typically transmits small partition metadata rather than full items. Workers use keys in ExecutionContext to read data themselves. This reduces network traffic, though workers must be able to reach the data source and have appropriate reader logic.

## 15. Deployment and security

Moving from local to remote adds infrastructure to manage:

- A broker or message transport with suitable availability and capacity.
- Networking between manager, workers, and database.
- Authentication and authorization for channels/queues.
- Encryption in transit and at rest where required.
- Worker deployment, health checks, and graceful shutdown.
- Message contract version management.
- Logging with correlation IDs linking manager requests to worker results.
- Alerts when queue backlogs, worker failures, or partition timeouts cross thresholds.

Workers should only accept authorized work types and scopes. Never trust a message solely because it arrived from a broker; authenticate producers, validate inputs, and restrict resource permissions under least privilege.

## 16. Migration path from core flow to the scaling module

You do not need to convert an entire Job to a remote model all at once. Proceed step by step:

1. Measure each Step's duration and identify the bottleneck.
2. Optimize queries, batch writes, chunk sizes, and resource usage.
3. Use split if independent Steps need to run in parallel.
4. Use multi-threaded Steps or local partitioning if scaling within one JVM suffices.
5. Define worker boundaries and data that can travel over messages.
6. Choose remote chunking if the manager reads and workers process/write; choose remote partitioning if workers must read their own ranges.
7. Add spring-batch-integration with a compatible version.
8. Set up the broker, message channels, worker deployments, and observability.
9. Test duplicate delivery, worker crashes, broker outages, and restarts.
10. Measure end-to-end throughput and compare against the local baseline before scaling further.

Every step needs metrics proving real benefit. Remote architectures carry operational, network, and serialization overhead; keep them only when scaling gains meet system requirements.

## 17. Cases where you should not use the scaling module

Do not pick Spring Batch Integration merely because:

- You want to run two independent Steps in parallel inside one Job.
- You want more threads within the same JVM.
- You have not measured bottlenecks or tuned queries yet.
- Data cannot be serialized or lacks a stable message contract.
- No broker/worker infrastructure exists to operate it.
- Work is too small, so messaging cost exceeds processing cost.
- Writers or business logic are unsafe under message redelivery.
- Workers update a shared resource already suffering lock contention.

In these cases, core flow, local partitioning, or sequential Step tuning is usually easier to operate and control.

## 18. Common mistakes

### Using split to shard items from the same reader

Split runs independent flows. To distribute one dataset across multiple workers, use partitioning instead of expecting split to slice items automatically.

### Adding spring-batch-integration for a local flow

Split and TaskExecutor belong to Core. Add the integration module only when messaging/remote patterns are needed.

### Using remote chunking while the reader remains the bottleneck

The manager still reads all data. If read speed caps throughput, consider remote partitioning or optimizing the reader.

### Using remote partitioning with overlapping partitions

Workers may read and write the same records. Define non-overlapping ranges, stable sort keys, and an input snapshot.

### Adding workers without checking the database

More workers can exhaust the connection pool, increase lock contention, and lower overall throughput.

### Assuming messages are processed exactly once

Brokers can redeliver on errors or timeouts. Use idempotency keys, inbox/outbox, and unique constraints.

### Failing to control oversized messages

Large chunk payloads increase network, serialization, and memory overhead. Design lean DTOs or pass data references.

### Not monitoring workers and queues

Looking only at manager status is not enough to diagnose backlogs or failed workers. Monitor queue depth, delivery counts, and each worker execution.

## 19. How to decide

Before choosing core flow or the scaling module, answer:

1. Is the work to parallelize multiple independent Steps or slices of the same dataset?
2. Can it scale within one JVM or does it require multiple processes/nodes?
3. Does the bottleneck lie in the reader, processor, writer, database, or external resources?
4. If using remote chunking, can the manager keep up with reading and dispatching chunks?
5. If using remote partitioning, can data be split into stable, non-overlapping ranges?
6. Can workers reach the required databases/files/services?
7. Do you have a broker and the operational capacity for message delivery, retries, DLQ, and backpressure?
8. Can messages/partitions be reprocessed safely?
9. How are metadata, checkpoints, and Job restarts managed?
10. Do end-to-end throughput benchmarks prove remote scaling beats local execution?

If Steps only need to run concurrently within the same application, use core flow. If one Step needs to split data inside the same JVM, use local partitioning or Core concurrency mechanisms. Only when work must be dispatched to separate worker processes over messaging is Spring Batch Integration the right choice.

## Conclusion

Core flow suits orchestrating independent Steps or flows running in parallel inside the same application. Spring Batch Core also already provides multi-threaded Steps and local partitioning for many single-JVM scaling needs. Use Spring Batch Integration when work must be distributed via message channels or a broker to separate worker processes/nodes. Remote chunking fits when the manager reads and workers process/write chunks; remote partitioning fits when workers must read their own data ranges. Base the decision on bottlenecks, data boundaries, broker operability, and restart/idempotency requirements—not merely on item counts.
