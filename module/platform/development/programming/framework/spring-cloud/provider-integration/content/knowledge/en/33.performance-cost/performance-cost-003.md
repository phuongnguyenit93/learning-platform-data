# Batching, Prefetching, and Rate Control by Processing Capacity

A Spring Boot application often sends or receives many records on each cloud service call. Sending one record at a time increases round-trips, per-request overhead, and network cost; grouping too many records together can increase latency, memory, retry cost, and service pressure. Prefetching keeps messages ready before a worker needs them, but fetching ahead faster than processing capacity leaves messages sitting in memory or causes lock/visibility timeouts to expire. Therefore, batching and prefetching must be sized to actual processing capacity.

This lesson establishes an approach for choosing three pipeline bounds: **batch size** (items/bytes in a single call), **prefetch/concurrency** (work delivered to consumers and operations running concurrently), and **rate limit** (average rate allowed to the service). Each limit solves a different problem; they must coordinate with cloud service timeouts, retries, and quotas.

This lesson belongs to the **Performance and Cost** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers integrating Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries, including identity/permissions configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers. The examples below use AWS DynamoDB/SQS, Azure Cosmos DB/Service Bus, and Google Cloud Pub/Sub.

## 1. Learning outcomes

After this lesson, you will be able to:

- Distinguish between batching, prefetching, concurrency, and rate limiting.
- Choose batch thresholds by item count, total bytes, and max wait time.
- Calculate the effect of batch size on request rate, latency, and memory.
- Use the batch APIs of DynamoDB, SQS, Azure Service Bus, and Google Pub/Sub.
- Design bulk ingestion with the Azure Cosmos DB Java SDK v4.
- Configure prefetch and concurrent handlers for Service Bus/SQS/Pub/Sub.
- Handle partial success, unprocessed items, duplicate delivery, and idempotency.
- Regulate rate according to RU/s, quotas, throttling, and downstream latency.
- Test throughput, batch fill ratio, backlog age, and tail latency.

## 2. Four concepts to keep separate

| Mechanism | Controls | Goal | Example |
| --- | --- | --- | --- |
| **Batching** | Items/bytes sent in one request | Reduce round-trips and per-request overhead | DynamoDB BatchWriteItem, Pub/Sub publisher batching |
| **Prefetch** | Messages fetched ahead and held locally | Reduce wait time to receive messages | Azure Service Bus `prefetchCount` |
| **Concurrency** | Operations/handlers running simultaneously | Utilize CPU/network within downstream limits | `flatMap(..., 16)`, `maxConcurrentCalls(8)` |
| **Rate limiting** | Operations or resource units per time window | Stay within quotas/capacity | 100 requests/second or RU/s cap |

For example, batching 10 messages can reduce requests tenfold compared to sending one by one, yet sending 100 batches concurrently still puts 1,000 messages in flight. A prefetch of 100 does not mean processing 100 messages in parallel; there may only be 8 handlers. A rate limit of 50 requests/second is also not equivalent to 50 items/second if each request carries 20 items.

## 3. Why does batching improve performance?

A request to a cloud service carries fixed overhead: HTTP/AMQP framing, authentication/signing, network round-trip, scheduling, and server-side request handling. If each request carries only a single small item, fixed overhead dominates.

Suppose a request has:

- Fixed overhead (T_0 = 20) ms.
- Per-item processing cost (T_i = 1) ms.

If sent one item at a time:

**T₁ = T₀ + Tᵢ = 21 ms/item**

If 20 items are batched and processed efficiently/in parallel within one request:

**T₂₀ ≈ T₀ + 20Tᵢ = 40 ms/batch**

Fixed request cost amortizes to about 1 ms/item. This is an illustrative model; a service may process items in parallel, sequentially, or bill capacity per item. Batching does not reduce RU/operations, write capacity, or billable business messages if service pricing is per operation/message.

Common benefits:

- Fewer requests and round-trips.
- Higher throughput when network latency or request overhead is the bottleneck.
- Lower client/server CPU and scheduling overhead.
- Easier byte-bounded payload control and micro-batching.

Trade-offs:

- The first item must wait until the batch fills or the flush timer fires.
- Large batches can hit request size limits or service quotas.
- Some APIs return partial success; retrying the whole batch can create duplicates.
- Batching can increase peak memory and data retention time in memory.
- A batch is not atomic like a transaction by default.

## 4. Choosing batches by count, bytes, and time

A batch is typically dispatched when **any of three conditions** occurs:

1. Maximum item count is reached.
2. Maximum total payload bytes is reached.
3. Maximum wait time is reached.

~~~mermaid
flowchart TD
    A[Receive new item] --> B[Add to bounded batch]
    B --> C{Count limit reached?}
    C -->|Yes| F[Flush batch]
    C -->|No| D{Byte limit reached?}
    D -->|Yes| F
    D -->|No| E{Max wait reached?}
    E -->|Yes| F
    E -->|No| A
    F --> G[Send request and handle per-item results]
    G --> H[Initialize next batch]
    H --> A
~~~

| Threshold | Purpose | If set too low | If set too high |
| --- | --- | --- | --- |
| Item count | Bounds elements in a request | Small batches, little overhead savings | Higher latency and memory |
| Byte size | Keeps request under payload limits | Too many requests | Request too large or rejected |
| Max wait | Bounds time spent accumulating a batch | Batches often underfilled | First item in batch waits too long |

Do not set count alone. When messages vary in size, 100 items might be 10 KiB or several MiB. Track p50/p95/p99 payload sizes and set a byte threshold with headroom for metadata/protocol overhead.

### 4.1. Batch size and request rate

If a producer emits (R_i) items/second and batches average (B) items:

**R_request ≈ R_i / B**

For example, 2,000 items/second with an average batch of 20 items:

**R_request ≈ 2,000 / 20 = 100 requests/second**

However, a service may meter quotas per item or per byte, so a lower request rate does not mean quota consumption drops by the same ratio.

### 4.2. Max wait and latency

Timer-based batching introduces an accumulation wait. Under steady traffic and batch count (B), average wait time is roughly ((B-1)/(2R_i)) if the byte threshold is not hit first. Under sparse traffic, max wait usually governs latency. Set max wait to match your use case's SLA: analytics events can wait longer than synchronous requests expecting fast responses.

### 4.3. Do not create an unbounded batch queue

When the producer outpaces the sender, pending batches pile up. Cap pending batches/bytes; when full, block upstream, return an overload error, drop permissible data, or spill to a durable queue. Never accumulate batches unboundedly on the heap waiting for a service to recover.

## 5. Batching does not mean transaction

A batch request can contain multiple operations while the service executes each operation independently:

- **All-or-nothing transaction:** all succeed or all roll back within the supported transaction scope.
- **Partial success batch:** some items succeed and some fail; the response reports individual statuses.
- **Bulk throughput API:** the SDK groups, partitions, and executes many operations in parallel; atomicity across items is not guaranteed.

Read each API's semantics carefully. DynamoDB `BatchWriteItem` is not atomic across the batch; Azure Service Bus `ServiceBusMessageBatch` packages multiple sub-messages into an AMQP batch without turning them into a cross-service business transaction; Cosmos bulk execution differs from a single-partition-key transactional batch. If the business requires atomicity, pick a dedicated transaction API and understand its partition/transaction limits.

## 6. AWS: DynamoDB BatchWriteItem

### 6.1. Limits and semantics

`BatchWriteItem` supports up to **25 put/delete operations** and a maximum total request size of **16 MB**. Each stored item can be up to 400 KB, though its JSON wire representation can be larger. The API does not support conditional writes or update expressions; a put on an existing key overwrites the item. Each put/delete is individually atomic, but the batch as a whole is not atomic.

If some items cannot be processed due to throttling or transient errors, the response returns them in `UnprocessedItems`. Retry only the unprocessed subset with exponential backoff; do not immediately resend the entire batch. <Link url="https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html" title="AWS DynamoDB BatchWriteItem API"/>.

### 6.2. Building a batch in AWS SDK for Java 2.x

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.BatchWriteItemResponse;
import software.amazon.awssdk.services.dynamodb.model.PutRequest;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.WriteRequest;

public Map<String, List<WriteRequest>> writeBatch(
        DynamoDbClient dynamoDb,
        String tableName,
        List<Product> products) {

    List<WriteRequest> writes = new ArrayList<>();
    for (Product product : products) {
        Map<String, AttributeValue> item = new HashMap<>();
        item.put("pk", AttributeValue.fromS("PRODUCT#" + product.id()));
        item.put("name", AttributeValue.fromS(product.name()));
        item.put("price", AttributeValue.fromN(
            product.price().toPlainString()));

        writes.add(WriteRequest.builder()
            .putRequest(PutRequest.builder().item(item).build())
            .build());
    }

    if (writes.isEmpty() || writes.size() > 25) {
        throw new IllegalArgumentException("Batch must have 1-25 items");
    }

    BatchWriteItemResponse response = dynamoDb.batchWriteItem(request -> request
        .requestItems(Map.of(tableName, writes))
        .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL));

    return response.unprocessedItems();
}
~~~

This example demonstrates a batch under 25 items. Applications must also check total request bytes before sending rather than relying solely on item count. The return value is the map of unprocessed items.

### 6.3. Retrying UnprocessedItems

Pseudo-code:

~~~java
Map<String, List<WriteRequest>> pending = initialRequestItems;
int attempt = 0;

while (!pending.isEmpty() && attempt < maxAttempts) {
    BatchWriteItemResponse response =
        dynamoDb.batchWriteItem(r -> r.requestItems(pending));

    pending = response.unprocessedItems();
    if (!pending.isEmpty()) {
        sleep(exponentialBackoffWithJitter(attempt));
    }
    attempt++;
}

if (!pending.isEmpty()) {
    persistForLaterRetry(pending);
}
~~~

This is pseudocode for a worker/batch job; never use `Thread.sleep` on a WebFlux event loop. In a reactive pipeline, use a scheduler/async delay. If the retry budget is exhausted, persist pending items to a durable store or dead-letter workflow for follow-up handling.

Do not retry items that already succeeded. Retrying the whole batch can overwrite items again; for other side effects, duplicates can be even more dangerous.

## 7. AWS: SQS SendMessageBatch and ReceiveMessage

### 7.1. SendMessageBatch

SQS `SendMessageBatch` sends up to **10 messages** in one request; total payload and each individual message can be up to 1 MiB. The response contains separate `successful()` and `failed()` lists. HTTP 200 does not guarantee every entry succeeded. <Link url="https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/SqsClient.html" title="AWS SDK for Java SQS API"/>.

~~~java
import java.util.ArrayList;
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

public SendMessageBatchResponse sendBatch(
        SqsClient sqs,
        String queueUrl,
        List<String> bodies) {

    if (bodies.isEmpty() || bodies.size() > 10) {
        throw new IllegalArgumentException("SQS batch must have 1-10 messages");
    }

    List<SendMessageBatchRequestEntry> entries = new ArrayList<>();
    for (int i = 0; i < bodies.size(); i++) {
        entries.add(SendMessageBatchRequestEntry.builder()
            .id("entry-" + i)
            .messageBody(bodies.get(i))
            .build());
    }

    SendMessageBatchResponse response = sqs.sendMessageBatch(
        SendMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(entries)
            .build());

    response.failed().forEach(failure ->
        log.warn("SQS entry {} failed: {}",
            failure.id(), failure.message()));

    return response;
}
~~~

The entry ID correlates responses, not the broker's message ID. Retry individual failed entries based on error category; do not retry validation/permanent errors such as invalid message bodies.

In this example, `log` is the service's SLF4J logger. `SqsClient` should be created once as a Spring bean and injected into the service; do not instantiate a client per batch.

### 7.2. ReceiveMessage prefetching up to 10 messages

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

ReceiveMessageResponse response = sqs.receiveMessage(request -> request
    .queueUrl(queueUrl)
    .maxNumberOfMessages(10)
    .waitTimeSeconds(20)
    .visibilityTimeout(60));
~~~

Valid `maxNumberOfMessages` values range from 1 to 10; the service may return fewer than requested. Long polling reduces empty receives. The visibility timeout starts when the message is received; if a consumer holds messages in a local queue too long or takes longer than the timeout to process, messages can reappear and be processed by another consumer. Extend visibility when work needs more time and make sure to delete after processing succeeds.

### 7.3. Application-layer prefetching

The SQS SDK has no single `prefetchCount` parameter like Service Bus. Applications typically run a receive loop bounding both in-flight batches and messages in a local queue. Never call `ReceiveMessage` continuously and accumulate messages without limit.

If each batch fetches 10 messages and 4 batches are in flight, up to 40 messages can be held locally. Only increase receive loops when downstream handlers/databases have matching capacity.

After successful processing, call `DeleteMessage` with the message's receipt handle. Never delete before the business operation completes; if work needs longer than the visibility timeout, call `ChangeMessageVisibility` for controlled extension.

## 8. Azure Service Bus: batching by actual size

### 8.1. Building a ServiceBusMessageBatch

`ServiceBusMessageBatch` exposes `getMaxSizeInBytes()`, `getSizeInBytes()`, `getCount()`, and `tryAddMessage()`. The SDK determines the batch limit from the service/transport; avoid hard-coding a fixed count or assuming all messages have identical size. `tryAddMessage` returns false if the message cannot fit in the current batch. This method is not thread-safe, so only one producer thread may mutate a batch at a time. <Link url="https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusmessagebatch?view=azure-java-stable" title="ServiceBusMessageBatch API"/>.

~~~java
import java.util.List;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusMessageBatch;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public void sendMessages(
        ServiceBusSenderClient sender,
        List<ServiceBusMessage> messages) {

    ServiceBusMessageBatch batch = sender.createMessageBatch();

    for (ServiceBusMessage message : messages) {
        if (batch.tryAddMessage(message)) {
            continue;
        }

        if (batch.getCount() > 0) {
            sender.sendMessages(batch);
        }

        batch = sender.createMessageBatch();
        if (!batch.tryAddMessage(message)) {
            throw new IllegalArgumentException(
                "Message is too large to add to an empty batch");
        }
    }

    if (batch.getCount() > 0) {
        sender.sendMessages(batch);
    }
}
~~~

In production, `sender` is a long-lived Spring-managed client; do not create a sender per batch. For partition-enabled or session-enabled entities, messages in a single send must share the same partition key/session ID. If sending across different groups, build a separate batch per group.

### 8.2. Prefetch and concurrent calls

The Java SDK lets you configure `prefetchCount` and `maxConcurrentCalls` on the processor builder. Prefetch holds messages in a local buffer so handlers can pick them up immediately; `maxConcurrentCalls` bounds callbacks executing in parallel.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;
import com.azure.messaging.servicebus.ServiceBusReceiveMode;

ServiceBusProcessorClient processor = new ServiceBusClientBuilder()
    .credential(namespace, tokenCredential)
    .processor()
    .queueName(queueName)
    .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
    .disableAutoComplete()
    .prefetchCount(16)
    .maxConcurrentCalls(8)
    .processMessage(context -> {
        try {
            processBusinessMessage(context.getMessage());
            context.complete();
        } catch (RetryableException ex) {
            context.abandon();
        }
    })
    .processError(error -> log.error(
        "Service Bus receive error", error.getException()))
    .buildProcessorClient();

processor.start();
// When Spring ApplicationContext shuts down:
// processor.stop();
// processor.close();
~~~

This example allows up to 8 concurrent handlers and a prefetch buffer of 16 messages. The Java processor builder defaults to `maxConcurrentCalls=1` and `prefetchCount=0`. In `PEEK_LOCK` mode, the lock timer starts as soon as a message is prefetched. If the buffer is too large, locks can expire before a handler even starts or finishes; completion then fails, the message is redelivered, and repeated failures can send it to dead-letter. Prefetch count is also a hard cap on messages held in the local buffer; setting it lower than `maxConcurrentCalls` underutilizes handlers. <Link url="https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-prefetch" title="Azure Service Bus prefetch guidance"/>.

Start with prefetch near `maxConcurrentCalls` or a small multiple above it, then measure buffer wait times and p95/p99 processing duration. Never raise prefetch if lock duration cannot cover both wait time and processing time.

In the Java SDK, `ServiceBusProcessorClient` uses Reactor's global `boundedElastic` daemon threads to invoke handlers. If `maxConcurrentCalls` exceeds the active thread cap, actual concurrent handlers may be lower than configured; check the thread pool cap and blocking duration. For non-retryable errors, move messages to dead-letter per policy rather than abandoning in an infinite loop.

## 9. Azure Cosmos DB Java SDK v4: bulk execution

Bulk support in Cosmos Java SDK v4 accepts a reactive stream of `CosmosItemOperation` and executes bulk operations. The SDK distributes work across partitions and throughput. This is bulk execution, not a shared transactional batch across the entire stream.

~~~java
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.models.CosmosBulkOperations;
import com.azure.cosmos.models.CosmosItemOperation;
import com.azure.cosmos.models.PartitionKey;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Mono<Void> bulkUpsert(
        CosmosAsyncContainer container,
        Flux<ProductDocument> documents) {

    Flux<CosmosItemOperation> operations = documents.map(document ->
        CosmosBulkOperations.getUpsertItemOperation(
            document,
            new PartitionKey(document.tenantId())));

    return container.executeBulkOperations(operations).then();
}
~~~

This snippet returns `Mono<Void>` so callers can compose it in a WebFlux pipeline; avoid `.blockLast()` in request paths. Each document must provide a partition key matching the container.

Bulk support in Java SDK v4 does not automatically handle retries and timeouts for the whole bulk stream. The application must classify per-operation results, apply bounded retries/backoff, and enforce deadlines. Never wrap the entire stream in an unbounded retry; operations that already succeeded would be re-sent.

### 9.1. Regulating bulk by throughput

Microsoft documentation recommends throughput control and retry policies to avoid 429s at scale, rather than merely increasing batch size or concurrency. The bulk executor sample may tune micro-batches of 1–100 documents per physical partition, but that is sample configuration, not a guarantee for every workload. A single bulk call spawns many internal tasks; avoid running many large bulk calls concurrently in one process without measuring CPU/network.

Cosmos Java SDK v4 throughput control groups can bound RU consumption locally per client or coordinate across multiple clients. Some throughput control APIs are marked Beta; verify SDK version and API status before production use. When the service returns 429, honor `retry-after` and monitor RU consumption and partition hot spots. <Link url="https://learn.microsoft.com/en-us/azure/cosmos-db/throughput-control-java" title="Cosmos DB Java throughput control"/>; <Link url="https://learn.microsoft.com/en-us/azure/cosmos-db/bulk-executor-java" title="Cosmos DB Java bulk operations"/>.

Example creating a local throughput control group:

~~~java
import com.azure.cosmos.ThroughputControlGroupConfig;
import com.azure.cosmos.ThroughputControlGroupConfigBuilder;

ThroughputControlGroupConfig bulkGroup =
    new ThroughputControlGroupConfigBuilder()
        .groupName("bulkIngestion")
        .targetThroughputThreshold(0.75)
        .defaultControlGroup(true)
        .build();

container.enableLocalThroughputControlGroup(bulkGroup);
~~~

A threshold of 0.75 caps the bulk group at roughly 75% of provisioned throughput per control group semantics, leaving capacity for other requests. This API is marked `@Beta` and requires a Java SDK v4 version supporting throughput control (at least 4.13.0 for local/global mode).

### 9.2. Bulk vs. transactional batch

Cosmos transactional batch applies to a single logical partition key and guarantees atomicity within supported transaction limits. Bulk execution optimizes throughput across many operations, can span multiple partitions, and handles each operation independently. Choose transactional batch when you need single-partition atomicity; choose bulk for high-volume ingestion/upsert/delete when per-item outcomes are acceptable.

## 10. Google Cloud Pub/Sub: batching publisher

### 10.1. Three publisher thresholds

Google Cloud Pub/Sub Java `Publisher` supports `BatchingSettings`:

- `setElementCountThreshold`: maximum message count to trigger a batch.
- `setRequestByteThreshold`: total byte threshold.
- `setDelayThreshold`: maximum time to wait for a batch.

Whichever threshold is reached first triggers the publisher to send the batch. Pub/Sub enforces a hard limit of 1,000 messages or 10 MB per publish batch request. <Link url="https://docs.cloud.google.com/pubsub/docs/batch-messaging" title="Pub/Sub batch messaging"/>.

~~~java
import com.google.api.gax.batching.BatchingSettings;
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.batching.FlowController.LimitExceededBehavior;
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import org.threeten.bp.Duration;

FlowControlSettings flowControl = FlowControlSettings.newBuilder()
    .setLimitExceededBehavior(LimitExceededBehavior.Block)
    .setMaxOutstandingElementCount(500L)
    .setMaxOutstandingRequestBytes(10 * 1024 * 1024L)
    .build();

BatchingSettings batching = BatchingSettings.newBuilder()
    .setElementCountThreshold(100L)
    .setRequestByteThreshold(256 * 1024L)
    .setDelayThreshold(Duration.ofMillis(20))
    .setFlowControlSettings(flowControl)
    .build();

Publisher publisher = Publisher.newBuilder(
        TopicName.of(projectId, topicId))
    .setBatchingSettings(batching)
    .build();

ApiFuture<String> publishFuture = publisher.publish(
    PubsubMessage.newBuilder()
        .setData(ByteString.copyFromUtf8("order-created"))
        .build());
~~~

This example caps the publisher at 500 messages / 10 MiB outstanding and flushes batches at 100 messages, 256 KiB, or 20 ms. `Block` flow control makes the producer wait when exceeding the budget; options exist to fail with an exception or ignore the limit, though ignoring can allow unbounded memory growth. In Spring Boot, manage `Publisher` as a lifecycle-aware bean; track/observe publish futures to handle outcomes. On shutdown, stop accepting new publishes, wait for pending futures, then call `publisher.shutdown()` and `publisher.awaitTermination(...)`. Never block on futures with `.get()` on a WebFlux event-loop thread.

Shutdown pattern for a worker/job or lifecycle callback:

~~~java
import java.util.concurrent.TimeUnit;

void stopPublisher() throws InterruptedException {
    publisher.shutdown();
    publisher.awaitTermination(1, TimeUnit.MINUTES);
}
~~~

This wait runs only in a shutdown lifecycle or worker thread; never in a controller/request path.

### 10.2. Publish futures and partial failure

Each `publish()` call returns an individual future for that message. Track the result of every future; do not merely log that a batch was submitted. When a future fails, determine whether the error is transient or permanent before retrying. Retain message IDs for tracing; use consumer-side idempotency/deduplication when publish retries can produce duplicates.

### 10.3. Subscriber flow control

Publisher batching does not replace subscriber flow control. Subscribers cap outstanding message counts and bytes; when a threshold is hit, the client pauses pulling until messages are acked/nacked. Tune message/byte caps to memory and handler capacity; if the broker backlog grows steadily over time, scale subscribers or optimize processing instead of raising outstanding limits indefinitely.

## 11. Prefetch: higher throughput at the cost of local wait time

Prefetch helps when network round-trips between broker and consumer are the bottleneck. The consumer fetches messages ahead of time so handlers always have data ready. However, prefetch consumes lock/visibility deadlines while messages sit in the local buffer.

### 11.1. Sizing prefetch

A practical starting point:

- Determine concurrent handlers (C).
- Measure p95 processing duration (T_p).
- Measure broker message fetch latency (T_n).
- Pick a prefetch just large enough to hide network latency, usually starting near (C) or a small multiple above (C).
- Verify that the last message in the buffer still has enough lock/visibility time left to be processed.

No single prefetch ratio fits every system. For large messages or slow handlers, smaller prefetch values are safer.

### 11.2. Estimating prefetch memory

**M_prefetch ≈ P × S × K**

Where **P** is prefetch message count, **S** is p95 payload size, and **K** is the overhead/copy factor.

For example, prefetching 100 messages with 128 KiB p95 payload and an overhead factor of 2:

**M_prefetch ≈ 100 × 128 KiB × 2 = 25 MiB**

This excludes object headers, deserialization, active handlers, and other queues. Monitor both heap and direct/native memory if the SDK uses Netty.

### 11.3. Lock/visibility timeout

| Service | Clock starts when | Risk when prefetch is too high |
| --- | --- | --- |
| AWS SQS | Message is received and becomes invisible | Visibility timeout may expire before handler finishes |
| Azure Service Bus PEEK_LOCK | Message is prefetched and locked | Lock expires in buffer, causing duplicate delivery or dead-lettering |
| Google Pub/Sub | Ack deadline starts on delivery | Message must be acked or have deadline extended while processing |

Always process idempotently, because message brokers typically provide at-least-once delivery under error/redelivery conditions.

## 12. Rate limits and concurrency limits

A rate limit caps operations per time window; a concurrency limit caps operations running simultaneously. Neither replaces the other:

- Higher service latency can increase in-flight requests even at constant requests/second.
- Lower service latency can increase requests/second even at constant concurrency.
- One 100-item batch is a single request yet may consume 100 operations or many RUs.

### 12.1. Token bucket

A token bucket accumulates tokens at rate (r) with burst capacity (b). Each request/item consumes tokens; when depleted, the producer waits or is rejected. This suits bounding average rate while still allowing short bursts.

### 12.2. Bulkhead/semaphore

A semaphore caps simultaneous operations. For example, allow only 12 Cosmos bulk writes in flight even if the producer emits 5,000 documents/second. Combine with batch size and rate limits to avoid flooding a slow service.

### 12.3. Resilience4j in Spring Boot

You can use RateLimiter and Bulkhead to bound application calls:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      cosmosBulk:
        limitForPeriod: 80
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  bulkhead:
    instances:
      cosmosBulk:
        maxConcurrentCalls: 12
        maxWaitDuration: 0
~~~

This example caps logical calls at 80/second and 12 concurrent operations. If one operation is a batch of 50 documents, this limit does not equal 80 documents/second; account for batch size and RU/operation. A simple call-count RateLimiter does not replace Cosmos throughput control when items have varying RU costs.

Apply those instances to service methods via annotations (requiring the corresponding Resilience4j starters/aspects):

~~~java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;

@RateLimiter(name = "cosmosBulk")
@Bulkhead(name = "cosmosBulk", type = Bulkhead.Type.SEMAPHORE)
public Mono<Void> ingest(Flux<ProductDocument> documents) {
    return bulkUpsert(cosmosContainer, documents);
}
~~~

If the method returns `Mono`/`Flux`, use the Reactor integration compatible with your Resilience4j version. Test behavior thoroughly when rate limit/bulkhead rejects; do not let overload exceptions trigger immediate retries in the calling layer.

## 13. Adaptive pacing from service feedback

Quotas are not always fixed by request count. Cosmos DB has RU/s and partition-level throttling; SQS, Pub/Sub, and Service Bus have service/region/entity quotas; networks have their own bandwidth and latency limits.

A simple tuning loop:

1. Start with small batch size/concurrency.
2. If p95 is below SLO, there are no 429s/throttling, and queues are stable, increase concurrency gradually.
3. Upon receiving 429, RESOURCE_EXHAUSTED, server busy, or rising pending acquires, lower concurrency/batch dispatch rate.
4. Honor `Retry-After` or retry-after durations from the SDK/service.
5. Use exponential backoff + jitter and an overall retry budget.
6. Maintain hard upper caps based on memory, connections, and quotas; never scale up indefinitely just because a few requests succeeded.

For Cosmos DB, prefer RU-based throughput control over request counting alone. For Pub/Sub, publisher flow control by outstanding count/bytes bounds client memory. For Service Bus, balance `maxConcurrentCalls`, prefetch, and lock duration. For SQS, balance receive batch size, visibility timeout, worker count, and in-flight caps.

## 14. Handling partial failure and idempotency

Batches often yield mixed outcomes:

| API | Error/partial success result | Action |
| --- | --- | --- |
| DynamoDB BatchWriteItem | `UnprocessedItems` | Retry only the unprocessed subset with backoff |
| SQS SendMessageBatch | `failed()` and `successful()` | Retry individual failed entries; do not resend succeeded ones |
| Azure Service Bus send batch | Send failure at batch level | Retry batch according to send semantics and app idempotency |
| Pub/Sub Publisher | Per-message future | Inspect each message future; retry transient failures |
| Cosmos bulk execution | Per-operation result, per-item errors/429s | Retry per application policy; do not assume bulk API retries everything |

When retrying:

- Attach a stable business ID/idempotency key to each item.
- Track per-item success/failure state for long batches.
- Do not retry validation, authorization, or schema errors.
- Retry transient failures with backoff/jitter and a total time bound.
- Route persistently failing items to a dead-letter queue or durable retry store.
- Do not equate HTTP 200 with every entry succeeding.

Batching does not create exactly-once processing. Consumers must deduplicate using unique constraints, inbox/outbox tables, or idempotency records.

## 15. Preserving order and partition affinity

Batching can affect ordering:

- SQS FIFO preserves order by MessageGroupId; batch entries must be constructed with the right group and sequence.
- Pub/Sub ordering keys require publishing by key and handling errors/retries per ordering semantics; a failure on one message can affect others with the same key.
- Service Bus partitions/sessions require messages in a send batch to share the corresponding partition key or session.
- Cosmos bulk may run in parallel across multiple logical partitions; do not assume input order equals commit order.

If ordering is only needed within an aggregate/tenant, group items by key and cap per-key concurrency. If global ordering is unnecessary, avoid serializing the entire pipeline just for unneeded ordering.

## 16. Sizing batches and prefetch from measurements

### 16.1. Calculating consumer throughput

With **C** concurrent handlers, each taking an average of **T** seconds/message:

**R_c ≈ C / T**

For example, 16 handlers at 0.2 seconds per message:

**R_c ≈ 16 / 0.2 = 80 messages/second**

This is theoretical throughput before DB/network/retry overhead. If the producer emits 200 messages/second, backlog grows by ~120 messages/second; raising prefetch merely moves backlog from the broker into heap without speeding up consumers.

### 16.2. Calculating batch request rate

If a producer emits 1,000 records/second and batches average 25 records:

**R_request ≈ 1,000 / 25 = 40 requests/second**

If the service quota is 30 requests/second, slow down, raise the quota, or change the write strategy. If quotas meter RU/item, a 25-item batch still consumes RUs for every item.

### 16.3. Tracking key metrics

| Metric | Meaning |
| --- | --- |
| Batch fill ratio | Actual items / count threshold |
| Batch bytes p95/p99 | Whether requests approach byte limits |
| Batch wait time | How long items wait for flush |
| Request rate and item rate | Separates request quota from item throughput |
| In-flight batches/messages | Work currently being processed |
| Prefetch buffer depth | Messages waiting locally |
| Queue/backlog age | Age of the oldest item/message |
| Partial failure/unprocessed count | Rate of unprocessed items |
| 429/throttling/RESOURCE_EXHAUSTED | Downstream is overloaded |
| p50/p95/p99 latency | Impact on SLAs |
| Heap/direct memory | Buffer and serialization cost |

## 17. Testing batching and prefetching

Run load tests with the same data and same service tier:

1. Compare single-item sends against batches of 5, 10, 25, and 50.
2. Keep payload bytes equivalent and measure fill ratio.
3. Test max wait times of 5, 20, and 100 ms to observe latency.
4. Test prefetch values of 0, C, 2C, and 4C while holding `maxConcurrentCalls` constant.
5. Simulate a slow/throttled downstream to measure queues, retries, and memory.
6. Inject partial failures; verify only failed items are retried.
7. Stop the application while batches are unflushed or messages are unacked; verify no data loss beyond allowed semantics.

Do not measure average throughput alone. Observe p95/p99, oldest message age, lock expiry, peak memory, and duplicate rate.

## 18. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Batching by count only | Large payloads exceed request limits | Also bound total bytes |
| Batching by bytes only | Low traffic leaves items waiting too long | Add max wait |
| Batches too large | Latency, memory, and retry cost climb | Increase gradually from benchmarks |
| Retrying the entire batch | Duplicates operations that already succeeded | Retry per failed item/entry |
| Treating a batch as a transaction | Data can commit partially | Use transactional APIs when atomicity is required |
| Prefetch too high | Messages expire lock/visibility before processing | Lower prefetch and check lock duration |
| Prefetch lower than concurrency | Handlers are underutilized | Balance prefetch with `maxConcurrentCalls` |
| Raising concurrency as 429s climb | Worse throttling and retry storms | Throttle down, backoff, use throughput control |
| Rate limiting requests only | Large batches still consume heavy RUs/items | Bound by resource units/bytes |
| Ignoring publish futures | Failed messages lost or unknown outcomes | Track every future/entry |
| Missing idempotency | Duplicate deliveries cause repeated side effects | Idempotent consumers and deduplication |
| Using unbounded queues | Heap grows until OOM | Bounded queues with explicit overflow policy |

## 19. Implementation workflow

~~~mermaid
flowchart TD
    A[Measure item rate, payload, and downstream latency] --> B[Choose batch count + bytes + max wait]
    B --> C[Choose prefetch and max concurrent handlers]
    C --> D[Bound queue/in-flight bytes]
    D --> E[Set rate limits per quota/RU]
    E --> F[Design partial failure and idempotency]
    F --> G[Load test with throttling/slow consumers]
    G --> H{Do latency, backlog, and memory meet SLO?}
    H -->|No| I[Tune batch/prefetch/rate]
    I --> G
    H -->|Yes| J[Finalize metrics, alerts, and rollout]
~~~

Pre-production checklist:

1. Are batches bounded by count, bytes, and max wait?
2. Does the API return partial success or unprocessed items?
3. Are retries scoped to failed items with idempotency keys?
4. Does prefetch fit concurrency and lock/visibility deadlines?
5. Are queues/publisher outstanding items bounded by both count and bytes?
6. Are rate limiters based on real quota units?
7. Are 429s, batch fill ratio, oldest backlog age, and p99 monitored?
8. On shutdown, how are unflushed batches and unacked messages handled?

## 20. Hands-on exercises

**Exercise 1 — DynamoDB BatchWriteItem.** Write a worker writing 10,000 products in 25-item batches. Simulate unprocessed items, retry with exponential backoff, and record retry counts.

**Exercise 2 — SQS SendMessageBatch.** Send 100 messages in batches of 10. Intentionally include an invalid entry; verify the response reports partial failure and retry only the failed entry.

**Exercise 3 — Service Bus batching.** Send variable-sized messages via `tryAddMessage`. Measure count/bytes per batch and handle a message that does not fit in an empty batch.

**Exercise 4 — Service Bus prefetch.** Fix `maxConcurrentCalls` at 8 and vary prefetch across 8, 16, and 64. Observe lock expiry, local buffer depth, throughput, and duplicate deliveries.

**Exercise 5 — Cosmos bulk.** Upsert 100,000 documents via `executeBulkOperations`. Monitor RUs, 429s, and partition hot spots, and compare against a throughput control group.

**Exercise 6 — Pub/Sub publisher.** Configure batch thresholds of 100 count, 256 KiB bytes, 20 ms delay, and 10 MiB flow control. Measure batch fill ratio and publish latency.

**Exercise 7 — Rate vs. concurrency.** Hold concurrency at 16 and vary rate limit across 50/100/200 ops/second. Then hold rate at 100/second and vary concurrency across 4/8/16; explain the difference.

**Exercise 8 — Memory budget.** Calculate memory for prefetching 200 messages with 64 KiB p95 payload and an overhead factor of 2. Double the payload size and determine how byte bounds should change.

**Exercise 9 — Partial failure and duplicates.** Have a consumer re-receive a message after a timeout. Use an idempotency key to ensure the side effect is applied only once.

## 21. Key takeaways

- Batching reduces request overhead; prefetch hides network latency; concurrency controls active work; rate limiting controls average rate.
- Size batches by **count + bytes + max wait**, never by item count alone.
- DynamoDB BatchWriteItem caps at 25 operations/16 MB, is not atomic across the batch, and returns `UnprocessedItems`.
- SQS SendMessageBatch caps at 10 entries; inspect every entry even on HTTP 200. ReceiveMessage returns at most 10 messages.
- Azure Service Bus batches use `tryAddMessage` and actual SDK size limits; prefetch must be sized alongside `maxConcurrentCalls` and lock duration.
- Cosmos bulk execution consumes a reactive stream; RU throughput control and retries must be explicitly designed.
- Pub/Sub publisher batching flushes on count/bytes/time; publisher flow control caps outstanding messages and bytes.
- Excessive prefetch merely shifts backlog from broker to memory and risks lock/visibility expiration.
- Batching/async is neither atomic nor exactly-once by default; handle partial failures, retries, and idempotency per item.
- Observe batch fill ratio, p95/p99 latency, backlog age, throttling, and memory before raising batch sizes or prefetch.

## 22. References

- [Amazon DynamoDB — BatchWriteItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html)
- [AWS SDK for Java 2.x — SQS client API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/SqsClient.html)
- [AWS SDK for Java 2.x — ReceiveMessageRequest.Builder](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/model/ReceiveMessageRequest.Builder.html)
- [Azure Service Bus — Java client library](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-servicebus-readme)
- [Azure Service Bus — Prefetch messages](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-prefetch)
- [Azure Service Bus — ServiceBusProcessorClientBuilder](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusclientbuilder.servicebusprocessorclientbuilder?view=azure-java-stable)
- [Azure Cosmos DB — Bulk operations with Java SDK v4](https://learn.microsoft.com/en-us/azure/cosmos-db/bulk-executor-java)
- [Azure Cosmos DB — Java SDK throughput control groups](https://learn.microsoft.com/en-us/azure/cosmos-db/throughput-control-java)
- [Azure Cosmos DB — Migrate to Java SDK v4 bulk support](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-migrate-from-bulk-executor-library-java)
- [Google Cloud Pub/Sub — Batch messaging](https://docs.cloud.google.com/pubsub/docs/batch-messaging)
- [Google Cloud Pub/Sub — Publisher flow control](https://docs.cloud.google.com/pubsub/docs/flow-control-messages)
- [Google Cloud Pub/Sub — Publish best practices](https://docs.cloud.google.com/pubsub/docs/publish-best-practices)
- [Resilience4j — RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j — Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
