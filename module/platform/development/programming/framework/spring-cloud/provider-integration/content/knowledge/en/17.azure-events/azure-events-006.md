# Throttling Receive Rates and Replaying Events

An Event Hubs consumer can read data faster than a database, internal API, or analytics system can process it. When that happens, events pile up in local buffers, memory grows, processing latency stretches out, or downstream systems get overloaded. Conversely, when a consumer was stopped or a read model needs to be rebuilt, the engineering team must re-read part or all of the historical events. These two needs are directly connected: **throttling receive/processing rates** keeps the system keeping up with load in normal operations; **controlled replay** recovers and reprocesses data without causing unintended side effects.

This lesson belongs to the **Azure Events** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services through the corresponding Spring Cloud libraries; covering identity and permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. In this lesson, the focus is on Azure Event Hubs, the Azure SDK for Java, and Spring Cloud Azure consumer configuration.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **prefetch**, batch receive, concurrency limits, rate limits, backpressure, and throttling.
- Explain why adding more consumer instances does not always increase throughput.
- Tune **prefetchCount**, **maxBatchSize**, **maxWaitTime**, and downstream processing speeds.
- Design consumers that never create unbounded internal queues and never checkpoint un-durably-processed events.
- Separate service throttling from consumers intentionally slowing down to protect downstream systems.
- Replay from earliest, latest, timestamp, offset, or sequence number within the retention window.
- Use a dedicated consumer group for replay without altering the progress of production consumers.
- Use Event Hubs Capture or archives when re-reading data that has aged out of retention.
- Integrate EventProcessorClient, EventHubConsumerClient, or the Spring Cloud Stream binder with Spring Boot.
- Build tests for backpressure, checkpoints, duplicates, replays, throttling, and cost.

## 2. Distinguishing Rate Control, Backpressure, and Throttling

These concepts are often used interchangeably, yet they act at different points:

| Concept | Meaning | Example in Event Hubs |
|---|---|---|
| **Prefetch** | Number of events requested ahead of time and buffered locally | Consumer keeps events ready in memory to reduce round-trips |
| **Batch receive** | Grouping multiple events into one callback invocation | Processing 100 events from the same partition in one batch |
| **Concurrency limit** | Maximum number of tasks running concurrently | At most 12 concurrent DB write operations |
| **Rate limit** | Maximum number of operations over a time window | No more than 200 API calls/second |
| **Backpressure** | When downstream is slow, slowing upstream or pausing further data requests | A slow callback stops the processor from pulling more events from that partition |
| **Throttling** | The service rejects or limits requests due to capacity/quota/policy limits | Event Hubs returns transient errors when a namespace is overloaded |

**prefetchCount** is not an events/second cap. It controls how many events are pre-buffered per partition. A consumer can prefetch 200 events and still process 2,000 events/second if downstream is fast enough; or it may process only 10 events/second if the handler is slow.

**Backpressure** is a flow-protection mechanism: if the callback does not finish, EventProcessorClient stops pushing more events to that callback and stops requesting more events from that partition at the normal pace. **Rate limit** is an explicit rate policy enforced by the application. **Throttling** can come from Event Hubs or a downstream service and must be diagnosed using specific metrics/errors.

## 3. Event Flow Path and Control Points

~~~mermaid
flowchart LR
    P["Producer"] --> EH["Event Hubs partition"]
    EH --> PF["Prefetch buffer"]
    PF --> BA["Batch / callback"]
    BA --> RL["Rate + concurrency control"]
    RL --> DB["Database / downstream API"]
    DB --> CP["Checkpoint store"]
    CP --> NEXT["Read next events"]
    RL -. "Slow downstream" .-> BP["Backpressure"]
    BP -. "Slow receive rate" .-> PF
~~~

Applications can control load at multiple layers:

1. **Receive buffer:** limit prefetched events per partition.
2. **Batching:** choose event count and wait time for batch assembly.
3. **Callback:** process sequentially or under bounded concurrency.
4. **Downstream:** bound connection pools, request rates, bulkheads, and timeouts.
5. **Checkpointing:** persist progress at a suitable batch/interval, avoiding excessive writes.
6. **Replay:** rate-limit re-reads so they do not spike load on target systems.

No single parameter solves every problem. Increasing batch size can lower overhead while raising latency and memory; lowering prefetch can shrink heap usage while reducing throughput; adding consumer instances can raise DB load or trigger rebalancing.

## 4. How Event Hubs Receives and Distributes Events

Event Hubs is an event stream divided into partitions. Consumers read by offset within a consumer group; EventProcessorClient manages partition ownership and checkpoints. Event Hubs does not use a per-event lock/complete model like Service Bus.

Key implications:

- Events are stored in partitions in append order; ordering is meaningful only within each partition.
- Multiple consumer groups can read the same stream independently.
- Instances in the same consumer group share partitions; a single partition cannot be split across multiple concurrent owners to increase parallelism within the same group.
- EventProcessorClient delivers events to callbacks; a slow callback slows down processing for that partition.
- The prefetch buffer lives in process memory; restarts can cause uncheckpointed events to be re-read.
- Checkpoints record processed reading positions, not exactly-once business confirmations.

Therefore, receive throttling must be designed alongside checkpointing and idempotency. If the application slows callbacks to protect the database, lag may rise, yet data remains safely in retention. If checkpoints advance past unprocessed events, backpressure cannot rescue skipped data.

## 5. Tuning prefetchCount

### 5.1. How Does Prefetch Work?

The Azure SDK for Java allows configuring **prefetchCount** on `EventProcessorClientBuilder`. The default value currently documented by the SDK is **500 events per partition**. When the receive link has credit, Event Hubs can proactively send that many events; the client places them in a local buffer so the callback has work immediately without waiting for another network round-trip.

- Prefetch too low: the client must request credit frequently, increasing round-trips/ACKs and potentially reducing throughput.
- Prefetch too high: many events sit in memory awaiting processing, increasing heap usage, GC pressure, and OOM risk.
- Large payloads or slow handlers: start with a smaller prefetch.
- Small payloads, steady streams, and fast handlers: you can test a higher prefetch if heap headroom permits.

Prefetch applies **per partition**, not as one global total across the application.

### 5.2. Estimating Memory

Suppose an instance owns 12 partitions and **prefetchCount = 500**:

\[
12 \times 500 = 6,000 \text{ maximum buffered events per configuration}
\]

If the average payload is around 8 KiB, raw payload data alone equals roughly 46.9 MiB. Actual heap consumption will be higher due to object metadata, byte arrays, headers, collections, runtime structures, and other buffers. This is a memory load estimate, not an exact heap limit.

If an instance owns many partitions or event sizes vary widely, measure heap at peak load. Never choose **prefetchCount** based solely on events/second.

### 5.3. Configuring in EventProcessorClient

Direct SDK configuration example in Spring Boot:

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .prefetchCount(200)
                .processEvent(eventContext ->
                        handler.process(eventContext.getEventData()))
                .processError(error ->
                        logger.warn("Event processor error",
                                error.getThrowable()))
                .buildEventProcessorClient();
    }
}
~~~

The value **200** is an illustrative starting point, not a universal recommendation. In production, externalize it per environment and measure heap, callback duration, consumer lag, and throughput before adjusting. Never create a new client per request; use one bean tied to the application lifecycle.

## 6. Batch Receive and processEventBatch

### 6.1. When Should You Use Batching?

**processEvent** invokes the callback once per event. This is straightforward and fits low or moderate loads. For high-volume streams, continuous per-event callback overhead can reduce performance. **processEventBatch** receives multiple events in a single callback, lowering overhead and fitting downstream systems that support batch writes.

Two key parameters:

- **maxBatchSize:** desired maximum number of events in a batch.
- **maxWaitTime:** maximum time to wait while assembling a batch before invoking the callback with available events; a batch may be smaller than `maxBatchSize`.

Larger batches can increase throughput and reduce overhead, yet they also increase wait times, memory usage, and the number of events that may replay if a batch fails.

### 6.2. Choosing Batch Size Based on Latency and Payload

| Scenario | Starting Approach |
|---|---|
| Small events, steady traffic, DB supports bulk inserts | Try larger batches and measure throughput |
| Large events, CPU-heavy processing | Small batches to control heap usage |
| Sparse traffic, low latency required | Small batches and short maxWaitTime |
| Downstream enforces request limits | Size batches to match what the API/DB supports |
| One bad event can fail the whole batch | Use manual checkpoints, deduplication, and per-event quarantine |

Do not set a long **maxWaitTime** just to fill `maxBatchSize` if SLOs require low-latency processing. Under low traffic, waiting for a full batch can inflate latency even when the system is not overloaded.

### 6.3. Batch Callback Example with EventProcessorClient

**EventBatchContext** provides the list of events for one partition and a method to update the checkpoint to the last event in the batch. Only checkpoint when every event in the batch has been durably processed or quarantined per policy.

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import java.time.Duration;
import java.util.List;

EventProcessorClient processor = new EventProcessorClientBuilder()
        .consumerGroup("orders-replay")
        .credential(namespace, eventHubName, credential)
        .checkpointStore(new BlobCheckpointStore(checkpointContainer))
        .prefetchCount(200)
        .processEventBatch(batchContext -> {
            List<EventData> events = batchContext.getEvents();
            if (events.isEmpty()) {
                return;
            }

            for (EventData event : events) {
                // Each event must be processed idempotently and committed durably.
                handler.processAndCommit(event);
            }

            // Only checkpoint the last event in the batch after the entire batch is safe.
            batchContext.updateCheckpoint();
        }, 100, Duration.ofSeconds(1))
        .processError(error ->
                logger.warn("Event processor error",
                        error.getThrowable()))
        .buildEventProcessorClient();
~~~

This snippet is a structural example; **namespace**, **eventHubName**, **credential**, **checkpointContainer**, **handler**, and **logger** are configured dependencies. In Spring Boot, declare the processor as a bean and manage **start()**/**stop()** with the lifecycle rather than creating a local processor inside a request method.

If event #80 fails after the first 79 events committed, the callback should not checkpoint the batch. When the batch is re-read, the first 79 events will reappear; the inbox/unique event ID must prevent duplicate side effects. If the failing event is a poison event, only checkpoint past it after durably quarantining it and policy permits continuing.

## 7. Backpressure Inside Callbacks

EventProcessorClient invokes callbacks per partition. A slow callback slows down pushing more events to the application and slows down requesting subsequent events from that partition. This is a natural form of backpressure.

### 7.1. Safe Ways to Apply Backpressure

- Process synchronously inside the callback when work duration is predictable and matches throughput targets.
- Bound concurrent DB/API operations using a bulkhead or semaphore.
- Size connection pools proportionally to total partitions and instances.
- If handing work off to another worker, only checkpoint after writing the job to a **durable queue** or transaction/outbox; never checkpoint merely because it was pushed onto an in-memory queue.
- Bound internal queue sizes; when full, block the callback or fail per policy rather than maintaining an unbounded queue.
- Use batch writes when downstream supports them and can preserve required atomicity.

### 7.2. Avoiding Unbounded Internal Queues

~~~mermaid
flowchart TD
    EH["Event Hubs"] --> CB["Processor callback"]
    CB --> Q{"Bounded queue has space?"}
    Q -->|Yes| W["Worker / database"]
    Q -->|No| BP["Block or slow down"]
    W --> COMMIT["Commit side effect"]
    COMMIT --> CP["Checkpoint"]
    BP -. "Do not checkpoint" .-> CB
~~~

If a callback pushes events onto an unbounded RAM queue and checkpoints immediately, the application can ingest events faster than it processes them, growing heap until OOM. If the process crashes, events that were checkpointed yet still sitting only in RAM are lost to business processing.

An internal handoff is only safe to checkpoint right away when enqueuing creates a durable commitment, such as inserting into a work/outbox table inside a transaction or publishing to another durable broker with proper acknowledgment.

### 7.3. Concurrency Limits vs. Rate Limits

A semaphore/bulkhead limits how many tasks run concurrently. It does not limit operations per second. If a request finishes in 5 ms, 10 permits can still allow very high throughput. A rate limiter caps calls per time window; both mechanisms often need to work together.

When using a per-pod rate limiter, total rate can reach rate/pod multiplied by replica count. To enforce a deployment-wide cap, divide quota across replicas or use a distributed limiter. Also clarify whether the rate cap applies per partition, per tenant, or across the whole service.

## 8. Limiting Downstream Processing Rates

Example: Event Hubs receives an average of 1,000 events/second, yet the database only handles 700 events/second steadily. Without throttling, backlog grows by roughly 300 events/second. After 5 minutes, backlog can grow by about 90,000 events, not counting bursts and retries.

Tools you can use:
- **Rate limiter:** caps API calls or DB writes per second/minute.
- **Bulkhead:** limits concurrent tasks so threads/connections are not exhausted.
- **Timeouts:** prevents waiting on downstream indefinitely.
- **Batch writes:** reduces per-event overhead.
- **Adaptive concurrency:** lowers concurrency when latency/errors climb and restores it once healthy.
- **Producer throttling:** where possible, signals overload or throttles upstream producers.

Do not spin-retry when a rate limiter rejects, as that amplifies load. If the callback cannot process an event yet, leave it uncheckpointed and apply backpressure or persist it durably for deferred processing.

### 8.1. Combining RateLimiter and Bulkhead

The example below illustrates combining Resilience4j at the service layer; rate/timeout settings are illustrative and must be tuned to your SLOs:

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.ratelimiter.RateLimiter;
import org.springframework.stereotype.Service;

@Service
class DownstreamEventWriter {
    private final RateLimiter rateLimiter;
    private final Bulkhead bulkhead;
    private final DatabaseWriter databaseWriter;

    DownstreamEventWriter(
            RateLimiter rateLimiter,
            Bulkhead bulkhead,
            DatabaseWriter databaseWriter) {
        this.rateLimiter = rateLimiter;
        this.bulkhead = bulkhead;
        this.databaseWriter = databaseWriter;
    }

    void write(EventRecord record) {
        if (!rateLimiter.acquirePermission()) {
            throw new IllegalStateException("Downstream rate limit reached");
        }

        Runnable write = Bulkhead.decorateRunnable(
                bulkhead,
                () -> databaseWriter.writeIdempotently(record));

        write.run();
    }
}
~~~

This example limits rate and concurrency within a single instance. If **write** throws an exception, the handler must not checkpoint the event as if it succeeded. Define which exceptions are retryable, which must be quarantined, and how to handle indeterminate commit outcomes. Never use a local per-instance limiter to claim you enforced a global rate limit across replicas.

## 9. Throttling via the Spring Cloud Stream Event Hubs Binder

The Spring Cloud Azure Stream Event Hubs binder provides consumer properties to tune prefetch, batching, checkpointing, and initial partition position.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consume-in-0:
          consumer:
            batch-mode: true
    eventhubs:
      bindings:
        consume-in-0:
          consumer:
            prefetch-count: 200
            batch:
              max-size: 100
              max-wait-time: 1s
            checkpoint:
              mode: MANUAL
~~~

Meaning:
- **batch-mode: true:** function receives payloads as a list of events.
- **prefetch-count:** number of events proactively received and locally queued per partition.
- **batch.max-size:** desired maximum batch size.
- **batch.max-wait-time:** wait duration to assemble a batch.
- **checkpoint.mode: MANUAL:** application invokes Checkpointer explicitly after durable processing.

Property names and behaviors must match your Spring Cloud Azure BOM. **BATCH** checkpoint mode is an automatic binder mechanism; if you must guarantee business transactions committed before checkpointing, choose **MANUAL** and invoke Checkpointer after the service transaction completes. Never assume **batch-mode** automatically implies database-safe checkpointing.

### 9.1. Consumer Function Receiving Batches

~~~java
import com.azure.spring.messaging.AzureHeaders;
import com.azure.spring.messaging.checkpoint.Checkpointer;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import java.util.List;
import java.util.function.Consumer;

@Bean
Consumer<Message<List<String>>> consume(OrderService orderService) {
    return message -> {
        List<String> events = message.getPayload();

        // Process and commit the entire batch in an appropriate transaction.
        orderService.processBatchIdempotently(events);

        Checkpointer checkpointer = message.getHeaders()
                .get(AzureHeaders.CHECKPOINTER, Checkpointer.class);

        if (checkpointer == null) {
            throw new IllegalStateException(
                    "Manual checkpoint header is missing");
        }

        checkpointer.success().block();
    };
}
~~~

This is an illustrative skeleton; verify payload/header types and batch checkpointing mechanics against your binder version. If a batch contains a failing event, never call success for the entire batch unless each failing event has been durably quarantined and policy allows continuing. In reactive apps, compose the publisher rather than calling **block()** on an event loop.

## 10. When Should You Slow Down Receiving?

Not all consumer lag calls for slowing down receiving. If handlers are fast and downstream has spare capacity, lowering prefetch too far can hurt throughput.

| Symptom | Possible Cause | Priority Action |
|---|---|---|
| Heap growing, frequent GC, OOM | High prefetch, large events, unbounded internal queue | Lower prefetch, bound buffers, measure payloads |
| DB connection pool exhausted | Concurrency exceeds DB capacity | Bulkhead, pool sizing, batch writes |
| High event processing latency | Slow handler or slow external API | Trace steps, set timeouts, rate limit |
| Consumer lag rising while CPU is low | Waiting on DB/network, unowned partitions, or blocked callbacks | Check downstream, ownership, networking |
| Increasing Event Hubs throttling | Namespace capacity/quota or traffic bursts | Check metrics, smooth bursts, evaluate capacity |
| One partition lags, others normal | Hot partition or unusually heavy events | Check key distribution and per-partition lag |
| Checkpoint age growing though handler processed events | Slow checkpoint store or infrequent checkpoints | Inspect Blob, tune checkpoint interval |
| Duplicates spike after deploy | Replays due to checkpoints/rebalancing | Verify checkpointing and idempotency |

Distinguish Event Hubs errors from database/HTTP API errors. If downstream is rejecting requests, raising throughput or adding consumers can worsen the outage. If consumer lag rises due to missing partition ownership or a stopped processor, lowering prefetch will not fix the root cause.

## 11. Throttling and Retries

### 11.1. Error Classification

- **Transient service/network errors:** the SDK has retry policies for certain temporary errors.
- **Quota/capacity throttling:** the service limits requests; inspect namespace metrics, SKU/capacity, and utilization.
- **Authentication/authorization:** invalid credentials or missing roles; do not retry infinitely.
- **Invalid event/schema:** malformed data; fix or quarantine.
- **Downstream throttling:** database/API limits requests; throttle at the consumer and respect downstream retry guidance.

The Azure SDK for Java surfaces many Event Hubs errors via AMQP exceptions. Inspect **isTransient**, error conditions, and error context rather than just message text. SDK retry policies do not replace business rate limiters.

### 11.2. Avoiding Retry Storms

If the SDK retries 3 times, the service layer retries 3 times, and a job scheduler also retries 3 times, a single event can trigger many downstream calls. Total attempts can multiply across retry layers. Designate one primary retry owner, cap attempts, and set an overall deadline.

When a timeout occurs after writing to the DB or sending an event, the outcome may be indeterminate. Keep event IDs stable and check inbox/idempotency records before repeating side effects. Never checkpoint an event just because a retry started.

## 12. Checkpointing and Rate Control

Checkpoints incur network cost because every write to the Blob checkpoint store is an HTTP operation. Checkpointing after every single event can significantly cut throughput. Checkpointing too rarely widens the replay window when a process crashes.

| Strategy | Advantage | Trade-off |
|---|---|---|
| Every event | Minimal replayed events | Many Blob writes, lower throughput |
| Every N events | Fewer checkpoint operations | May re-read a slice of already-processed events |
| Time-based | Bounds replay window by duration | Replayed event count varies with traffic |
| After batch commit | Ties progress to durable batches | Must ensure checkpoints never jump past incomplete events |

With batch callbacks, a checkpoint records only the position of the last event in the batch. If an event mid-batch fails, the whole batch may be re-read; dedup/inbox must handle earlier events that already committed. When processing asynchronously, only checkpoint up to a contiguous position where all preceding events have completed or been durably quarantined.

The checkpoint store is not an event archive. It neither holds payloads nor extends retention.

## 13. What Is Replay and When Is It Needed?

**Replay** means re-reading historical events from an earlier position to recover, verify, or rebuild results. Common scenarios:

- A consumer was down while data remained inside retention.
- A handler had a bug and needs to reprocess events after a fix.
- A projection/read model must be rebuilt from source events.
- A new consumer such as fraud detection or analytics needs to run over historical data.
- A time window needs reconciliation after an incident.
- Long-term archives need to be read after data aged out of Event Hubs retention.

Replay differs from **resume**:
- Resume continues from the existing checkpoint.
- Replay deliberately starts from earliest, an earlier timestamp, offset, or sequence number.
- A new consumer group has independent reading progress; it does not reset the production group's checkpoint.

## 14. Choosing a Replay Starting Position

`EventPosition` can express:
- **earliest():** earliest event still in retention.
- **latest():** new events enqueued after reading begins.
- **fromEnqueuedTime(Instant):** events from a specific enqueue timestamp.
- **fromOffset(String):** position by offset.
- **fromSequenceNumber(long, boolean):** position by sequence number with inclusive/exclusive flag.

Offsets and sequence numbers belong to individual partitions; when replaying an entire event hub, apply appropriate positions per partition. Enqueue timestamps help filter by time, yet do not replace aggregate versions or business order.

### 14.1. Initial Position Only Applies When No Checkpoint Exists

EventProcessorClient prioritizes the saved checkpoint for a consumer group/partition. **initialPartitionEventPosition** is used only when no checkpoint exists yet for that partition. Consequently, safe replays usually use a **separate consumer group** and separate logical checkpoint store, then set an explicit initial position.

Do not change initial position in the config of a consumer group that already has checkpoints and expect the processor to rewind automatically. Likewise, never delete production checkpoints to replay without stopping all processors and having a reconciliation plan.

## 15. Replaying with EventProcessorClient and a Dedicated Consumer Group

Example creating a processor for a replay run. The consumer group and checkpoint store must be dedicated to replay; **replayFrom** is the starting timestamp determined by business requirements.

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventPosition;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.messaging.eventhubs.models.EventBatchContext;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

EventProcessorClient replayProcessor = new EventProcessorClientBuilder()
        .consumerGroup("orders-replay")
        .credential(namespace, eventHubName, credential)
        .checkpointStore(new BlobCheckpointStore(replayCheckpointContainer))
        .initialPartitionEventPosition(
                partitionId -> EventPosition.fromEnqueuedTime(replayFrom))
        .prefetchCount(100)
        .processEventBatch(batch -> {
            List<EventData> events = batch.getEvents();
            if (events.isEmpty()) {
                return;
            }

            for (EventData event : events) {
                replayHandler.processIdempotently(event);
            }

            batch.updateCheckpoint();
        }, 50, Duration.ofSeconds(2))
        .processError(error ->
                logger.warn("Replay processor error",
                        error.getThrowable()))
        .buildEventProcessorClient();
~~~

This is a structural example; **namespace**, **eventHubName**, **credential**, **replayCheckpointContainer**, **replayHandler**, and **logger** are configured dependencies. Run the processor with a time-bounded, rate-limited lifecycle. Once replay finishes, stop the processor and save run metrics for reconciliation.

Notes:
- If the replay group/checkpoint store already has checkpoints, initial position does not overwrite old checkpoints.
- If a batch fails midway, do not call **updateCheckpoint**; earlier events may be re-read.
- Preserve original event IDs and enforce idempotency at the target.
- Never replay multiple parallel copies producing the same business side effect without deduplication.
- Replays can increase outgoing throughput, Blob checkpoint operations, DB writes, and network costs.

## 16. Replaying a Single Partition with EventHubConsumerClient

When you need to read one partition or a small range for investigation, `EventHubConsumerClient` lets you specify the partition, maximum event count, starting position, and wait duration:

~~~java
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubConsumerClient;
import com.azure.messaging.eventhubs.EventPosition;
import com.azure.messaging.eventhubs.models.PartitionEvent;
import com.azure.core.util.IterableStream;
import java.time.Duration;

try (EventHubConsumerClient consumer = new EventHubClientBuilder()
        .credential(namespace, eventHubName, credential)
        .consumerGroup(replayConsumerGroup)
        .prefetchCount(100)
        .buildConsumerClient()) {

    IterableStream<PartitionEvent> events =
            consumer.receiveFromPartition(
                    partitionId,
                    100,
                    EventPosition.fromEnqueuedTime(replayFrom),
                    Duration.ofSeconds(5));

    for (PartitionEvent partitionEvent : events) {
        replayHandler.inspect(partitionEvent.getData());
    }
}
~~~

This works well for bounded one-off reads or diagnostic tools. `EventHubConsumerClient` is a low-level consumer: the application must manage partitions, subsequent positions, durable checkpoints, and recovery itself. It does not balance ownership across partitions like `EventProcessorClient`.

If you need to replay all partitions over a long period or across multiple instances, `EventProcessorClient` with a dedicated consumer group is usually a better fit.

## 17. Replaying from Event Hubs Capture When Retention Is Insufficient

Event Hubs retains events only for the SKU/configured retention period. If a consumer is down longer than that, old offsets may no longer have readable data. **Event Hubs Capture** can write the stream to Azure Blob Storage or Data Lake Storage per partition, typically in Avro format.

Archive replay workflow:
1. Identify the time range and partitions requiring recovery.
2. Read the corresponding Capture files from Blob/ADLS.
3. Decode Avro and validate schemas/metadata.
4. Feed events into a dedicated replay pipeline or write to a new destination.
5. Preserve original event IDs, attach a replay run ID, and throttle processing rate.
6. Reconcile counts of read events, succeeded events, duplicates, and failed events.

Capture is a configured archival mechanism; it does not expose an API for `EventProcessorClient` to read directly from the archive as though events were still in partitions. To reprocess an archive, you need a consumer/pipeline that reads Avro files and sends data to the right destination.

Archiving also incurs storage, transaction, data transfer, and batch-processing costs. Capture files need separate retention/lifecycle policies and environment-isolated read permissions.

## 18. Business-Safe Replay and Idempotency

A technically successful replay does not mean business side effects are allowed to execute again. For example:
- Rebuilding a projection can write into a new projection table.
- Recomputing analytics can write into a separate dataset.
- Sending emails, charging payments, or calling partner APIs may be forbidden to repeat.
- Previously processed events may be skipped by inbox/dedup if using the same consumer identity.

Before replaying, define the **target goal**:
- Rebuild read model: use a new table/schema or a new consumer identity.
- Reconcile data: run comparison/reconciliation logic rather than blindly re-triggering side effects.
- Retry failed events: replay only quarantined events while keeping original event IDs.
- Re-run business actions: requires idempotency keys and business approval.

Dedup tables typically use the `(consumer_name, event_id)` key. When rebuilding a projection, `consumer_name` or the dedup table must distinguish the replay target so it does not skip every event already processed by the old projection. Conversely, never rename a consumer just to bypass dedup when the goal is to resend payments/emails; that requires an explicit business workflow.

## 19. Monitoring Lag, Buffers, and Replays

Monitor at least:

| Metric | Meaning | How to Use |
|---|---|---|
| Prefetch count | Events buffered per partition | Choose alongside heap and payload size |
| Batch size / wait time | Event count and batch assembly wait | Balance throughput and latency |
| Callback duration | Time spent processing event/batch | Spot handlers slowing down partitions |
| Consumer lag | Distance between consumer position and stream tail | Determine whether consumers are keeping up |
| Oldest event age | Age of unprocessed events | Compare against SLOs and retention |
| Heap / GC | Memory usage and garbage collection pressure | Spot oversized prefetch or queues |
| Downstream latency/errors | DB/API response time and failures | Tune rate/concurrency limits |
| Checkpoint age/failures | Progress saved to Blob | Detect slow or failing checkpoint stores |
| Throttled requests | Requests limited by the service | Distinguish service capacity from downstream |
| Replay throughput | Re-read rate | Prevent replays from overloading production |
| Duplicates suppressed | Duplicate events dropped | Evaluate replay/rebalance and idempotency |

Where possible, measure lag per partition. A hot partition can lag heavily even while total hub throughput looks healthy. During replays, tag logs/metrics with **replayRunId**, consumer group, and target to separate replay traffic from live traffic.

## 20. Testing Throttling and Replay

Use dedicated test Event Hubs, consumer groups, checkpoint containers, and test databases. Never reset production checkpoints or intentionally trigger throttling on live namespaces to test.

| Scenario | How to Test | Expected Result |
|---|---|---|
| Small/large prefetch | Run the same load with varying prefetch values | Measure throughput, heap, and latency |
| Batch size | Test batches of 10/50/100 events | Pick throughput/latency sweet spot |
| Batch wait | Test high and low traffic | Low traffic does not wait overly long |
| Slow handler | Increase DB/API latency in tests | Lag grows predictably without unbounded heap growth |
| Downstream rate limit | Cap requests/sec of simulated DB/API | Callback backpressure engages without retry storms |
| Full internal queue | Use a small bounded queue | Un-durably-saved events are never checkpointed |
| Checkpoint failure | Temporarily deny test Blob permissions | Events may replay; dedup prevents duplicate side effects |
| Timestamp replay | New consumer group reads from a timestamp | Reads exact range still in retention |
| Offset/sequence replay | Specify position per partition | Resumes from the desired position |
| Existing checkpoint | Create a checkpoint, then change initial position | Processor resumes from checkpoint without resetting |
| Capture archive | Read Avro files in test storage | Replay events counted and reconciled |
| Poison event | Send invalid payload | Durably quarantined or halted per policy |
| Duplicate side effects | Resend same event ID | Inbox/idempotency prevents duplicate side effects |
| Replay load | Ramp replay speed gradually | Database and network stay un-overloaded |
| Multi-instance | Scale consumers in same group | Stable ownership/rebalancing, lag monitored |

Load tests must record event size, ingress rate, processing rate, batch size, prefetch, heap, CPU, DB latency, checkpoint frequency, and cost. Changing one knob without holding input load constant makes results hard to compare.

## 21. Common Operational Scenarios

### Scenario A: Heap Grows Under High Traffic

A consumer owns many partitions, prefetch is 500 per partition, event payloads are large, and the handler writes slowly to the DB. Step down prefetch gradually, measure post-GC heap, inspect partitions per instance, and remove any unbounded internal queues. Then evaluate batch size to balance overhead.

### Scenario B: Consumer Lag Rises Despite Low CPU

Callbacks may be waiting on DB/APIs, connection pools may be exhausted, network to the Blob checkpoint store may be slow, or one partition may have a hot key. Check callback duration, DB pool wait times, checkpoint age, and per-partition lag before adding pods.

### Scenario C: Increasing Batch Size Worsens User Latency

Batches wait too long to fill or `maxWaitTime` is too large. Shorten wait time, consider smaller batch sizes, or use `processEvent` for low-volume traffic. Measure end-to-end p95/p99 latency rather than throughput alone.

### Scenario D: Replay Overloads the Database

Replays share capacity and downstream dependencies with live consumers. Create a separate replay consumer group, cap rate/concurrency, use a read replica or separate target if appropriate, run off-peak, and watch live backlogs. Never raise prefetch to speed up replay when the database is already overloaded.

### Scenario E: Replay Does Not Read from Earliest Despite Config Changes

The consumer group already has checkpoints. Initial position only applies when no checkpoint exists. Use a new consumer group for replay, or follow the checkpoint-reset runbook after stopping all processors and assessing impact.

### Scenario F: Target Replay Data Aged Out of Retention

Event Hubs no longer holds old offsets. Check Event Hubs Capture, archives, or other storage sources. If no archive exists, document the unrecoverable data gap and follow business recovery procedures; deleted events cannot be restored merely by changing checkpoints.

## 22. Pre-Production Checklist

- **Prefetch:** sized by event size, partitions per instance, heap, and throughput.
- **Batching:** max size/wait time meet latency goals and downstream batch limits.
- **Backpressure:** slow callbacks are controlled; no unbounded RAM queues.
- **Rate/concurrency:** bounded to downstream capacity; global caps explicitly designed across replicas.
- **Checkpointing:** only after durable side effects/quarantine; frequency balances Blob cost and replay window.
- **Idempotency:** stable event IDs, inbox/unique constraints, and guards for non-DB side effects.
- **Replay:** separate consumer group, explicit initial position, throttled replay speed, and defined target.
- **Retention/archive:** retention window understood; Capture/ADLS archives meet long-term replay needs.
- **Observability:** per-partition lag, oldest event age, heap/latency, callback duration, checkpoint age, throttling, and replay run IDs.
- **Security:** separate Managed Identity/RBAC for Event Hubs and Blob; archives encrypted and access-controlled.
- **Testing:** tested slow handlers, checkpoint failures, duplicates, replays, retention expiry, and downstream throttling.
- **Operations:** runbooks for stopping replays, throttling consumers, handling poison events, and data reconciliation.

## 23. Summary

Event Hubs throttling requires coordinating **prefetch, batching, callback duration, concurrency, rate limits, backpressure, and checkpoints**. Prefetch controls local event buffering; batching cuts overhead; slow callbacks create natural backpressure; rate limiters/bulkheads protect downstream systems. No parameter replaces idempotency and timely checkpointing.

Replays should use a **separate consumer group**, select positions by earliest/latest/time/offset/sequence, and rate-limit reprocessing. If data has expired past retention, use Event Hubs Capture or archives; checkpoints cannot recover purged events. When integrating Spring Boot, measure lag/heap/latency per partition, preserve original event IDs, isolate replay targets from production side effects, and test thoroughly on dedicated resources.

## References

- Azure SDK for Java — Troubleshoot Event Hubs performance: https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-messaging-event-hubs-performance
- Azure SDK for Java — Troubleshoot EventProcessorClient: https://learn.microsoft.com/en-us/azure/developer/java/sdk/troubleshooting-messaging-event-hubs-processor
- Azure SDK for Java — EventProcessorClientBuilder API: https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventhubs.eventprocessorclientbuilder?view=azure-java-stable
- Azure SDK for Java — EventHubConsumerClient API: https://learn.microsoft.com/en-us/java/api/com.azure.messaging.eventhubs.eventhubconsumerclient?view=azure-java-stable
- Spring Cloud Azure — Event Hubs binder reference: https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html
- Azure Event Hubs — Capture overview: https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-capture-overview
- Azure Event Hubs — FAQ and retention: https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-faq
