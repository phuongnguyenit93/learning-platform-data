# Push Triggers, Pull Consumers, and Polling Mechanisms

In the **Queues and Event Streams** chapter, how a function receives messages directly impacts latency, scalability, cost, and error handling. There are two common delivery models: **push**, where a component proactively invokes the consumer when data is available; and **pull**, where the consumer proactively queries the source system to retrieve data. Polling is a technique commonly used in the pull model, though it can also be performed by a platform service on behalf of application code.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications, particularly Java functions triggered by HTTP, messages, or events. In a FaaS environment, developers need to understand who is waiting for messages, who acknowledges processing, when messages are redelivered, and how to throttle consumption rates. These decisions affect state management, access permissions, retries, idempotency, cold starts, scaling, and operational costs.

## 1. What Are Push, Pull, and Polling?

An asynchronous system typically has a producer creating messages or events, a broker storing or distributing them, and a consumer performing the work. The key question is which side initiates data transfer from the broker to the consumer.

**Push delivery** is a model where the message provider proactively sends data to the consumer when data is ready for processing. The consumer typically receives an HTTP call, a callback, or a function invocation. The producer does not need to know the consumer's internal processing details; the broker or intermediary service is responsible for delivering messages according to the subscription.

**Pull consumption** is a model where the consumer proactively requests the broker to return messages or records. The consumer decides when to call, how much data to fetch, and can adjust its consumption rate based on current processing capacity.

**Polling** is a technique where the consumer periodically checks whether new data is available. A single poll may return one or more messages, or return empty if no data is available yet. Polling can use short intervals or long polling to wait for data for a period of time before returning a result.

| Model | Who initiates data delivery? | Consumer rate control | Examples |
|---|---|---|---|
| Push | Broker or delivery service calls the consumer | Primarily via concurrency, subscription limits, and processing responses | Webhooks, push subscriptions, function invocations |
| Pull | Consumer calls the broker to fetch data | Directly via poll interval, batch size, and consumer count | Kafka consumer, queue receive API |
| Polling | Technique for periodically checking data in pull | Via poll frequency and wait duration per poll | Receive message every few seconds, long polling |

Push and pull describe who initiates delivery. Polling describes repeating data-fetch requests in a pull consumer. Therefore, polling should not be viewed as a protocol completely independent of pull.

## 2. General Processing Flow

A queue flow can be represented as follows:

~~~mermaid
flowchart LR
    P[Producer] --> Q[Queue / Broker]
    Q --> D{Delivery mode}
    D -->|Push| F[Function invoked]
    D -->|Pull / Poll| C[Consumer fetches message]
    F --> W[Business processing]
    C --> W
    W --> A{Outcome}
    A -->|Success| ACK[ACK / Delete]
    A -->|Transient error| RETRY[Retry / Redeliver]
    A -->|Permanent error| DLQ[Dead-letter queue]
    ACK --> Q
    RETRY --> Q
    DLQ --> Q
~~~

Each component has distinct responsibilities:

- **Producer** creates messages following an agreed contract.
- **Queue or broker** stores messages, manages delivery timing, and may track acknowledgement state.
- **Dispatcher or event source mapping** delivers messages to the function according to configuration.
- **Consumer** executes business logic and reports the processing outcome.
- **Dead-letter queue (DLQ)** holds messages that have failed beyond the allowed attempt count or are classified as unprocessable automatically.

With streams, the broker typically stores a sequence of records with offsets or positions. Consumers track the processed position rather than deleting individual records like a standard queue.

## 3. Push Triggers in Serverless Systems

### 3.1. Direct Push via HTTP or Webhook

In the direct push model, the broker or event delivery service sends an HTTP request to the consumer's endpoint. The function can be deployed behind an API gateway or a platform-managed endpoint.

Example:

1. Order Service emits an OrderPlaced event.
2. The delivery service sends an HTTP POST to the Inventory Function's endpoint.
3. The function authenticates the source, validates the envelope, and reserves inventory.
4. The function returns a response code per the sender's contract.
5. The delivery service records success or schedules a retry per policy.

An HTTP 2xx is typically treated by the sender as successful delivery, whereas network errors or failure status codes can trigger retries. Exact rules depend on the service. The consumer must assume requests can be resent, including cases where the previous processing succeeded but the response was lost in transit.

### 3.2. Push Subscriptions

Some pub/sub systems allow registering an endpoint to receive pushes. The broker manages sending requests, retries, and timeouts. The consumer does not need to call a receive-message API itself.

Push subscriptions fit when:

- The consumer has an always-ready endpoint or the platform can invoke the function.
- You want to eliminate polling code and operating dedicated workers.
- Low delivery latency is an important requirement.
- Traffic does not exceed configured ingestion capacity.
- The system can handle duplicate requests and respond within deadlines.

The consumer needs request authentication, rate limiting, and fast processing. If business logic takes a long time, you can durably persist the message and return a success response, then process it in the background through another mechanism. Do not return success before persisting enough information to continue processing, because the broker may stop retrying immediately after that response.

### 3.3. FaaS Push Triggers and Event Source Mapping

Many FaaS platforms support connecting queues or streams to a function via an integrated trigger configuration. When messages arrive, the platform automatically invokes the function, often with a batch of messages.

From the Java code's perspective, the function is triggered as a new invocation. However, behind the scenes the platform may actually be polling the queue or stream to detect data, and then invoking the function. This is an important distinction: **a function being invoked in a push-like manner does not necessarily mean the broker is pushing messages directly to the function**.

An event source mapping typically handles several tasks:

- Reading messages or records from the source.
- Forming batches based on batch size and batching window.
- Invoking the function with the batch.
- Tracking invocation results.
- Retrying or checkpointing according to the source's mechanism.
- Scaling invocation counts based on queue depth or load.

Specific features and semantics vary across platforms. Read the exact acknowledgement, batch failure, checkpointing, concurrency, and retry mechanisms of the service you are using.

### 3.4. Advantages and Limitations of Push

Push can reduce latency because the consumer is invoked as soon as a message is ready, without waiting for the next poll cycle. It also reduces operational code because the broker or platform service manages distribution.

However, producers or brokers can send faster than the consumer can process. Without concurrency limits, a traffic spike can trigger many simultaneous function invocations, overwhelming downstream databases or APIs. Push requires backpressure mechanisms such as concurrency caps, quotas, rate limits, or buffer queues.

The consumer must also respond within the sender's timeout. If the function runs too long, the sender may time out and redeliver while the first invocation is still running. This increases the risk of duplicate processing.

## 4. Pull Consumers and Proactive Message Fetching

### 4.1. Consumers Calling Receive or Poll

In the pull model, the consumer actively sends requests to the broker. A single call can request up to a maximum number of messages, wait for a bounded duration, and return as soon as data is available or the wait time expires.

Basic flow:

1. Consumer calls receive/poll.
2. Broker returns a batch of messages or an empty list.
3. Consumer processes each message or record.
4. Upon successful processing, the consumer acknowledges the message or commits the processed position.
5. Consumer continues polling periodically or immediately after finishing the batch.

Pull lets the consumer regulate how much work it takes on. If the database slows down, the consumer can reduce batch size, scale down workers, or pause polling. This provides direct application-side backpressure.

### 4.2. Queue Pull and Acknowledgement

With queues, the broker typically retains a message until the consumer confirms processing. Confirmation can be an ACK, delete message, complete message, or equivalent operation.

Some queues use a visibility timeout or lease:

- When a message is delivered to a consumer, the broker temporarily hides it from other consumers.
- The consumer processes it during the lease window.
- If the consumer confirms success, the message is deleted or marked complete.
- If the lease expires without confirmation, the message can be redelivered.

The visibility timeout must be long enough for expected processing time, including dependency latency and data writes. If too short, the message may be delivered to a second consumer while the first is still processing. If too long, failed messages take a long time to be retried.

Some systems allow extending the visibility timeout or lease when work takes longer. Extensions must be bounded and should avoid holding messages indefinitely.

### 4.3. Stream Pull and Offsets

With event streams, records typically reside in an ordered log per partition. Consumers read from an offset and save checkpoints or commit offsets to record processed positions.

Unlike standard queues, consumers do not delete records after reading. Multiple consumer groups can read the same stream independently. Each group tracks its own offsets, so the same record can be processed by multiple groups.

| Queue | Event Stream |
|---|---|
| Messages are usually deleted or marked complete after ACK | Records are retained according to a retention policy |
| A message is usually delivered to one consumer at a time per queue mechanics | Multiple consumer groups can read the same record |
| Processing state is tied to the message or receipt | Read state is tied to offset/checkpoint |
| Retries usually cause message redelivery | Consumers can re-read by resetting or not committing offsets |
| Suited for work items that need distribution and completion | Suited for event streams needing multiple consumers or replay |

Not every broker has identical semantics. Some systems combine queue and stream features, or provide both per-message ACK and per-partition checkpoints. Always rely on the platform's specific contract.

## 5. Polling, Short Polling, and Long Polling

### 5.1. Short Polling

Short polling is when a consumer queries the broker frequently with a short wait time or no wait time at all. If no messages are available, the broker immediately returns an empty result and the consumer retries after a delay.

Example cycle:

~~~text
Poll -> No messages -> Wait 1 second
Poll -> 5 messages -> Process batch
Poll -> No messages -> Wait 1 second
Poll -> 2 messages -> Process batch
~~~

The advantages are simple implementation, predictable wait intervals, and consumer control over the cycle. The drawback is that when the queue is idle, the consumer continuously generates empty requests. If the interval is long, new messages wait longer before being picked up.

Short polling is suitable when:

- The source API does not support long polling.
- The consumer needs a fixed check interval.
- Traffic is periodic or work only needs batch processing on a schedule.
- The maximum wait latency is acceptable.

### 5.2. Long Polling

Long polling allows the consumer to ask the broker to wait for a period of time if no messages are currently available. The broker returns early as soon as messages arrive or when the wait timeout expires.

Example:

~~~text
Poll (wait up to 20 seconds)
  -> Message arrives after 3 seconds: return batch immediately
  -> No messages: return empty after 20 seconds
Next poll
~~~

Long polling reduces empty requests and usually lowers latency compared to short polling with long intervals. The consumer still initiates the call, but does not have to wake up repeatedly just to ask the broker.

Long polling does not mean the broker actively pushes to the consumer. The consumer still holds an open request waiting for a response. It also does not guarantee instant delivery; it still depends on max wait time, batch window, load, and source configuration.

### 5.3. Choosing Poll Timing

Several factors need balancing:

- Polling too frequently increases empty requests and API call costs.
- Polling too infrequently increases the time messages sit waiting.
- Long polling for too long can tie up connections or workers while waiting.
- Too many parallel pollers can put pressure on the broker.
- Poll duration must be compatible with function, HTTP client, and platform timeouts.

For a scheduled function polling a queue, ensure the wait duration plus batch processing time does not exceed the invocation timeout. If each poll only fetches a small batch, the function may be invoked repeatedly, increasing initialization, cold start, and orchestration overhead. For sources natively supported by the platform, event source mappings usually manage polling and batching more efficiently.

### 5.4. Adaptive Polling

A consumer can adjust its sleep duration based on poll results:

- Messages received: continue polling quickly after processing the batch.
- No messages: back off sleep duration up to a cap.
- Transient error: use exponential backoff and jitter.
- Broker overloaded: reduce concurrency or pause fetching messages.
- Queue growing rapidly: scale up workers within downstream resource limits.

Do not let all consumers retry on a synchronized fixed schedule. When a broker or dependency has an outage, many clients waking up and retrying together can create a traffic spike. Jitter spreads out retry timestamps.

## 6. Batch Size, Batch Window, and Processing Efficiency

Consumers often receive multiple messages in one poll or function invocation. Batch processing can reduce communication and initialization overhead, but increases wait time for the first message and affects retry scope.

**Batch size** is the maximum number of messages in a single receive call or invocation. **Batch window** is the maximum duration the system waits to gather additional messages before sending the batch to the consumer, when supported by the platform.

| Small Batch | Large Batch |
|---|---|
| Messages are processed sooner under low traffic | Reduces number of invocations or polls |
| Smaller retry scope in many mechanisms | Can increase throughput |
| Higher per-message overhead | Higher memory usage and per-batch processing time |
| Useful for heavy processing or low-latency needs | Useful for fast processing and steady traffic |

When choosing a batch size, account for:

- Average and worst-case processing time per message.
- Platform payload size or record count limits.
- Function memory.
- Invocation timeout.
- Capacity of databases and downstream APIs.
- Whole-batch vs. per-message retry policies.
- Ordering requirements.

A larger batch size does not always yield better throughput. If a single failing message causes the entire batch to retry, already-succeeded messages may be executed again. The consumer must be idempotent or the platform must support reporting per-message failures.

## 7. Acknowledgement, Deletion, and Checkpointing

### 7.1. Acknowledging After Durable Processing

A consumer should acknowledge a message only after work is complete and results are durably saved. If it ACKs before committing business data, the consumer can lose the message if the process crashes right after the ACK.

Conversely, if data is committed but the ACK is lost, the message may be redelivered. That is why consumers require idempotency.

A safe sequence is typically:

1. Validate the message and check the schema.
2. Check the deduplication key.
3. Execute business logic and write results.
4. Commit the transaction.
5. ACK or delete the message, or commit the offset per the source's mechanism.

For operations calling external services, a local transaction cannot span external side effects. Use provider-supported idempotency keys, persist step state, and design compensating actions where appropriate.

### 7.2. Partial Batch Failure

A batch may contain both successful and failed messages. If the platform only accepts a single pass/fail result for the entire batch, one failing message can cause every message to be redelivered.

Partial batch failure lets the consumer indicate which messages need retrying or should not be checkpointed. Exact mechanics depend on the platform and source type:

- With queues, you can acknowledge or delete successful messages and leave failed messages for redelivery.
- With streams, checkpoints usually correspond to a partition offset. If a record mid-batch fails, the consumer may have to re-read records from that position onward, depending on the event source mapping.
- Some platforms support a batch item failure response; others only support whole-batch success or failure.

Do not assume every FaaS provider has identical partial batch response behavior. Check the trigger configuration and required response format for your platform.

### 7.3. Poison Messages

A poison message is a message that consistently causes the consumer to fail, such as a malformed schema payload, invalid data, or an edge case triggering a software bug. If retried endlessly, it wastes resources and can block other messages—especially when a stream must preserve partition ordering.

Limit retry attempts, classify errors, and route unprocessable messages to a DLQ or error storage. With streams, you may need to record the failed offset, route the record to a quarantine stream, and allow the consumer to proceed per business policy. Do not silently drop records if doing so loses critical events.

## 8. Backpressure and Consumer Rate Control

Backpressure is the mechanism for regulating producer, broker, or consumer speed to prevent overloading a component. In serverless, functions can scale out rapidly, whereas databases or external services typically have lower connection and throughput limits.

Common control techniques:

- Cap maximum function concurrency.
- Limit messages per poll or batch.
- Limit concurrent pollers.
- Pause or throttle fetching when dependencies slow down.
- Use queues as buffers to absorb traffic bursts.
- Use token buckets or rate limiters for external APIs.
- Match consumer count to stream partition count.
- Monitor oldest message age and queue growth rate.

For example, the Inventory Function might receive 500 messages per second, while the database can only handle 100 transactions per second steadily. If the function scales to match full traffic, open connections and pending transactions can spike rapidly. Cap concurrency or fetch rate to keep load within processing capacity.

A queue can absorb traffic spikes, but it does not increase sustained consumer throughput. If the arrival rate consistently exceeds the processing rate, the backlog will grow over time. You must increase consumer capacity, optimize processing, or shed/throttle incoming load.

## 9. Retries, Visibility Timeout, Offsets, and Dead-Letter Queues

### 9.1. Queue Retries

When a message is not ACKed, the queue can redeliver it after the visibility timeout or lease expiration. Configure a maximum receive count or appropriate retry policy. After repeated failures, move the message to a DLQ if supported by the service.

Visibility timeout should exceed expected batch processing time, accounting for dependency waits and data writes. If processing may run long, extend the lease or break work into smaller steps with durable state.

### 9.2. Stream Retries and Checkpoints

With streams, consumers typically commit offsets after successful processing. Without committing, consumers may re-read records after restarts or rebalances. If offsets are committed too early, records may be skipped even though business logic did not complete.

A checkpoint should reflect the contiguous position successfully processed within each partition. Do not commit an offset higher than an incomplete record in the same partition if the application requires in-order processing.

### 9.3. Dead-Letter Queues and Quarantine

A DLQ holds messages that exceeded the retry policy or were marked unprocessable. Store the failure reason, attempt count, timestamp, source, and message identifier. For CloudEvents, preserve the original `source` and `id` for traceability.

A DLQ is not permanent storage replacing a business data store. Define retention limits, access permissions, investigation procedures, and controlled replay workflows. Before replaying, fix the root cause and verify whether the consumer can safely process older messages.

## 10. Ordering and Scalability

### 10.1. Queue Ordering

Some queues provide FIFO or ordering groups, but many standard queues do not guarantee strict ordering across multiple consumers, retries, or message visibility windows. If business logic requires per-order sequencing, use a message group key based on `orderId` or an equivalent partition key.

Preserving order usually reduces parallelism within the same group. Multiple independent groups can be processed concurrently, while messages within the same group must follow the ordering policy.

### 10.2. Stream Partitions and Consumer Groups

Streams usually divide data into multiple partitions. Each partition maintains its own record order. A consumer group assigns partitions to member consumers for parallel processing. The number of effective active consumers in a group is generally bounded by the partition count, depending on the broker.

If there are too few partitions, adding function instances does not necessarily increase throughput because one partition cannot be arbitrarily split across multiple consumers in the same group while keeping a single offset stream. If there are too many partitions, management and rebalance overhead can grow.

### 10.3. Rebalancing

When consumers join or leave a group, the broker may reassign partitions. Consumers must persist offsets properly and handle stopping fetches, finishing in-flight work, and committing checkpoints cleanly. Uncontrolled parallel processing can cause later records to be committed ahead of earlier ones.

For Java consumers, process records sequentially per partition if ordering is required. If processing in parallel, track completed offsets per partition and only commit up to the highest contiguous completed position.

## 11. Java Example: Pull Consumer for Kafka

The example below illustrates a Java consumer proactively polling Kafka. The consumer disables auto-commit, processes records in the batch, and only commits offsets after the entire batch succeeds.

~~~java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public final class OrderStreamConsumer {
    private final KafkaConsumer<String, String> consumer;
    private final OrderEventProcessor processor;

    public OrderStreamConsumer(
            KafkaConsumer<String, String> consumer,
            OrderEventProcessor processor) {
        this.consumer = consumer;
        this.processor = processor;
    }

    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                if (records.isEmpty()) {
                    continue;
                }

                try {
                    for (ConsumerRecord<String, String> record : records) {
                        processor.processIdempotently(
                                record.topic(),
                                record.partition(),
                                record.offset(),
                                record.key(),
                                record.value());
                    }

                    consumer.commitSync();
                } catch (Exception processingFailure) {
                    // Do not commit an incomplete batch.
                    // Stop the consumer so the supervisor can apply backoff or recover.
                    throw new IllegalStateException(
                            "Batch processing failed", processingFailure);
                }
            }
        } finally {
            consumer.close();
        }
    }

    public static KafkaConsumer<String, String> createConsumer() {
        Properties properties = new Properties();
        properties.put("bootstrap.servers", "localhost:9092");
        properties.put("group.id", "order-service");
        properties.put("key.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        properties.put("value.deserializer",
                "org.apache.kafka.common.serialization.StringDeserializer");
        properties.put("enable.auto.commit", "false");
        properties.put("auto.offset.reset", "earliest");

        return new KafkaConsumer<>(properties);
    }
}
~~~

Before running, the application must subscribe to a topic, such as calling `consumer.subscribe(List.of("orders"))`. Bootstrap servers, authentication, and TLS settings should come from secure deployment configuration rather than being hardcoded in production.

Key takeaways:

- `poll` proactively fetches records and also participates in maintaining group membership.
- `commitSync` runs only after the entire batch succeeds.
- If one record fails, the batch is uncommitted, so previously processed records may be re-read after the consumer restarts.
- Therefore, `processor.processIdempotently` must guard against duplicates using a business key or topic-partition-offset.
- If processing a batch takes too long, the consumer may exceed `max.poll.interval.ms` and be kicked out of the group. Choose an appropriate batch size, processing budget, and poll configuration.
- In production, handle errors, backoff, rebalances, and graceful shutdown cleanly; the example above focuses on the poll-and-commit loop.

Do not run a `KafkaConsumer` from multiple threads simultaneously. `KafkaConsumer` is not thread-safe. If parallel processing is needed, dispatch records to a worker pool while tracking completed offsets per partition and only committing when all preceding records in that partition have finished.

## 12. Java Example: Batch Message Processing in a Function

With a FaaS platform using event source mapping, a function can receive a batch of messages in a single invocation. The platform adapter converts the batch into Java types, invokes business logic, and returns results per the platform's protocol.

The following example is a vendor-agnostic illustrative model:

~~~java
import java.util.List;

public record QueueMessage(
        String messageId,
        String body,
        int receiveCount) {
}

public record BatchResult(List<String> failedMessageIds) {
}

public interface MessageProcessor {
    void processIdempotently(QueueMessage message);
}

public final class QueueBatchFunction {
    private final MessageProcessor processor;

    public QueueBatchFunction(MessageProcessor processor) {
        this.processor = processor;
    }

    public BatchResult handle(List<QueueMessage> messages) {
        List<String> failures = new java.util.ArrayList<>();

        for (QueueMessage message : messages) {
            try {
                processor.processIdempotently(message);
            } catch (Exception failure) {
                failures.add(message.messageId());
            }
        }

        return new BatchResult(List.copyOf(failures));
    }
}
~~~

`BatchResult` here illustrates the partial batch failure concept. Each platform may require a different response structure, or only support invocation-level pass/fail. The actual deployment adapter must map the `failedMessageIds` list into the exact response schema required by the platform.

If the platform does not support partial batch failure, ensure idempotent processing so whole-batch retries do not produce duplicate side effects. Never report the entire batch as successful if any message has not been durably processed.

## 13. Polling in a Scheduled Java Function

You can use a scheduler to trigger a function periodically, which then polls a queue or message-receive API. This pattern is useful when the source lacks event source mapping or when work should run in scheduled batches.

Example:

~~~java
public final class ScheduledQueuePoller {
    private final QueueClient queueClient;
    private final MessageProcessor processor;

    public ScheduledQueuePoller(
            QueueClient queueClient,
            MessageProcessor processor) {
        this.queueClient = queueClient;
        this.processor = processor;
    }

    public void runOnce() {
        var messages = queueClient.receive(
                10,
                java.time.Duration.ofSeconds(15));

        for (QueueMessage message : messages) {
            processor.processIdempotently(message);
            queueClient.acknowledge(message);
        }
    }
}
~~~

This is a pseudo-adapter: `QueueClient` represents the broker's API. In production, handle each message individually, classify errors, ACK only after the business transaction commits, and avoid skipping ACKs when a single message in the batch fails.

When using a scheduler, consider:

- Schedules may overlap if a previous invocation has not finished.
- Multiple instances may poll simultaneously if the scheduler allows concurrency.
- Use a lock or work-distribution mechanism if only one consumer is allowed to run.
- Poll wait duration must be shorter than the function timeout.
- Cap batch processing time so it does not exceed the timeout.
- If the function frequently polls empty queues, invocation and cold start costs can be high.

If the platform offers native queue integration, an event source mapping is usually preferable because the platform manages reading, batching, and invocations. Scheduled polling remains useful for integrating unsupported sources or custom processing schedules.

## 14. Security and Access Control

Push and pull have different security surfaces.

For HTTP push:

- Authenticate the identity of the service calling the endpoint.
- Verify signatures or tokens per the provider's mechanism.
- Allow only authorized sources and configured subscriptions.
- Enforce request size and rate limits.
- Protect the endpoint from unintended public access.

For pull consumers:

- Grant receive/read permissions only for the specific queue or topic.
- Grant ACK/delete or offset commit permissions only when the consumer requires them.
- Manage credentials using a secret manager or IAM role.
- Use TLS when connecting to the broker.
- Scope read permissions by topic, queue, consumer group, or tenant.

Do not grant broker admin permissions to a function whose sole job is receiving messages. Publish and consume permissions should be separated whenever business logic and platform support allow.

## 15. Latency, Cold Starts, and Cost

### 15.1. Latency

Push can eliminate polling wait times, but still incurs broker, batch window, invocation, and cold start latency. Pull can increase latency if poll intervals are long or if the consumer processes an oversized batch before polling again.

Long polling reduces empty requests while still receiving messages relatively promptly. A batch window improves message aggregation but can force the first message in a batch to wait longer.

### 15.2. Cold Starts

If every batch spins up a new function instance, cold starts can impact processing time. Larger batches can reduce total invocations, though each invocation runs longer and consumes more memory. Smaller batches may respond faster but generate more invocations.

Measure end-to-end time from when a message enters the queue until business processing completes—not just handler execution time. Useful metrics include message age, queue wait time, invocation duration, batch processing time, and retry duration.

### 15.3. Cost

Costs may include:

- Number of receive/poll calls or push invocations.
- Function invocation count and execution duration.
- Connection hold time for long polling.
- Message volume, payload size, and storage.
- Retries, dead-lettering, and replays.
- Logs, traces, and metrics.
- Broker, partition, and consumer group resources.

Short polling can generate many empty requests. Long polling usually cuts down empty calls. Push avoids polling overhead but can trigger high invocation counts during traffic spikes. Event source mappings may incur provider-specific charges or limits. Compare total cost against realistic workload profiles.

## 16. Choosing Push or Pull in Practical Scenarios

| Scenario | Model to Consider | Reason |
|---|---|---|
| Send a notification to an endpoint on an event | Push | Consumer is invoked when data is ready |
| Java worker needs to self-regulate broker read rate | Pull | Consumer controls polling, batching, and concurrency |
| Queue natively integrated with FaaS | Event source mapping | Platform manages polling and invocations |
| Stream with partitions and consumer groups | Pull | Consumers track offsets and process per partition |
| Source lacks push or native triggers | Polling | Consumer proactively checks the source |
| Uneven load needing fewer empty requests | Long polling or event source mapping | Waits for data instead of asking constantly |
| Consumer has strict downstream throughput limits | Throttled pull or push with concurrency cap | Regulates rate to protect dependencies |

No single model is optimal for every system. Weigh latency, rate control, queue vs. stream traits, platform support, retries, and cost.

## 17. Common Design Mistakes

**Polling too frequently:** The consumer generates excessive empty requests, driving up cost and broker load. Use long polling or adaptive backoff when no messages are available.

**Polling too infrequently:** Messages wait too long before pickup. Tune intervals to latency SLAs or switch to push/event source mapping.

**ACKing before writing data:** If the function fails after ACK, the message is deleted while business work remains incomplete. ACK only after results are durably persisted.

**Visibility timeout too short:** The message is redelivered while the first consumer is still processing it. Set a sufficiently long lease or renew it when needed.

**Lack of idempotency:** Retries, timeouts, or lost responses can create duplicate business effects. Use durable deduplication keys.

**Oversized batches:** Invocations may time out, exhaust memory, or widen retry blast radius. Size batches based on processing time and platform limits.

**One failing message blocking an entire batch:** Use partial batch failure where supported, or ensure idempotent consumers and a DLQ.

**Unbounded consumer scaling:** Functions open too many concurrent connections and overwhelm the database. Set concurrency caps, rate limits, and backpressure.

**Committing offsets before processing finishes:** Records can be skipped after restarts. Commit checkpoints only for contiguous, successfully processed ranges.

**Ignoring rebalances:** A consumer may lose partitions mid-processing. Save checkpoints accurately and handle shutdown/rebalances cleanly.

**Using scheduled polling without overlap guards:** Two invocations may poll simultaneously and duplicate work. Use distributed locks or concurrency limits while preserving idempotency.

**Treating event source mapping as pure push:** Under the hood, the platform may be polling a queue or stream. Know where batching, checkpointing, retries, and concurrency are configured to operate it properly.

## 18. Pre-Deployment Consumer Checklist

- [ ] Identified whether the source is a queue or stream and verified its storage semantics.
- [ ] Selected the appropriate push, pull, or event source mapping model.
- [ ] If polling, selected short vs. long polling and appropriate wait timeouts.
- [ ] Poll interval, batch size, and batch window match SLAs.
- [ ] Function timeout, HTTP client timeout, visibility timeout, or lease do not conflict.
- [ ] Consumer only ACKs/deletes after business results are durably persisted.
- [ ] For streams, offsets/checkpoints only advance across contiguous successfully processed records.
- [ ] Duplicate handling implemented via idempotency keys or source + event ID.
- [ ] Retry policy, backoff, jitter, DLQ, and replay procedures defined.
- [ ] Partial batch failure handling configured if supported by the platform.
- [ ] Concurrency caps and backpressure mechanisms are in place.
- [ ] Ordering, partition keys, consumer groups, and rebalances are accounted for.
- [ ] Receive, ACK, publish, and subscribe permissions follow least privilege.
- [ ] Metrics cover queue depth, oldest message age, empty polls, retries, DLQ count, and processing duration.
- [ ] Polling, invocation, storage, and operational costs estimated against representative load.

## Conclusion

Push enables brokers or delivery services to proactively invoke consumers when messages are ready. Pull lets consumers proactively fetch data and regulate consumption rates. Polling repeats fetch requests in a pull consumer: short polling checks quickly on an interval, while long polling waits for messages over a window to reduce empty requests. In FaaS, event source mappings can perform polling at the platform layer and invoke functions in batches.

The right choice depends on latency, throughput, backpressure needs, batching, acknowledgement or checkpointing mechanics, retries, idempotency, ordering, cold starts, and cost. Regardless of the model chosen, consumers must persist state durably, acknowledge only after successful processing, and tolerate message redelivery. These are the foundations for reliable Java functions under shifting traffic and dependency failures.
