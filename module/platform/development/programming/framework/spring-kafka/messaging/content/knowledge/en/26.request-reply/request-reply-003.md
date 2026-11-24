# Correlation ID for Requests

## 1. Why Do Requests Need a Correlation ID?

In request-reply with Kafka, the client sends a request to a topic, and the processing service receives the request and sends a response to a reply topic. These two directions are two independent Kafka records. They can be processed asynchronously, interleaved with other requests, and arrive at the client in a different order from the order sent.

A Correlation ID is an identifier attached to a request and returned unchanged in the response. The client uses this ID to determine which response belongs to which pending request.

For example, the client sends three concurrent requests:

```text
Client
  |-- Request A (correlationId = c-101) ---->
  |-- Request B (correlationId = c-102) ---->
  |-- Request C (correlationId = c-103) ---->
                                               Request topic
                                                    |
                                                    v
                                             Processing service
                                                    |
  |<-- Reply C (correlationId = c-103) -----------|
  |<-- Reply A (correlationId = c-101) -----------|
  |<-- Reply B (correlationId = c-102) -----------|
  |
  +-- c-101 -> completes Future A
  +-- c-102 -> completes Future B
  +-- c-103 -> completes Future C
```

Responses may return in the order C, A, B. The Correlation ID allows the client to match each response with the right Future regardless of record arrival order.

## 2. Where Does the Correlation ID Live in a Kafka Record?

A Kafka record has a key, a value, and headers. With Spring Kafka request-reply, the correlation ID is typically passed in the `KafkaHeaders.CORRELATION_ID` header.

The three default request-reply headers typically used are:

| Header | Purpose |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Matches a response with the corresponding request |
| `KafkaHeaders.REPLY_TOPIC` | Tells the responder which topic to send the response to |
| `KafkaHeaders.REPLY_PARTITION` | Optional; specifies the target partition to send the response to |

The Correlation ID is metadata of the request-reply protocol. It is not the Kafka record key and does not determine the request's partition. The record key typically serves partitioning/ordering; the correlation ID serves request-response pairing.

In Kafka headers, values are stored as `byte[]`. If using strings, both sides must agree on encoding, typically UTF-8. When using `ReplyingKafkaTemplate`, Spring Kafka automatically generates a correlation ID if the request does not have one and manages the mapping between IDs and pending Futures.

## 3. Distinguishing Correlation ID, Request ID, Event ID, and Trace ID

These identifiers may hold the same value in some designs, but their meanings differ:

| Identifier | Scope | Purpose |
|---|---|---|
| Correlation ID | A request-reply pair or an interaction sequence | Matches a response with a pending request |
| Request ID | A business request | Identifies the request for logging, auditing, or reconciliation |
| Event ID | An emitted event | Deduplicates and traces events across multiple topics/services |
| Trace ID | A distributed trace | Connects spans across multiple processes and systems |
| Kafka key | Record partitioning | Selects the partition and preserves key order within a partition |

Do not use the Correlation ID as an idempotency key if the same request may be resent with a new correlation ID. When duplicate processing must be prevented, use a `requestId` or stable idempotency key in the business payload/header and store processing state on the responder.

The Correlation ID is not an authentication credential either. Do not use it to prove caller identity or access permissions; the responder must still check authorization and tenant context through its own mechanisms.

## 4. Request-Reply with ReplyingKafkaTemplate

Spring Kafka provides `ReplyingKafkaTemplate<K, V, R>` to send requests and receive responses asynchronously. This template manages correlation IDs and pending Futures, so applications do not need to build their own correlation map for standard cases.

The client needs two components:

- A `ProducerFactory` to send requests.
- A reply listener container subscribed to the reply topic to receive responses.

### Declaring the Reply Container and Template

Example using topics `orders.requests` and `orders.replies`:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    ConcurrentMessageListenerContainer<String, OrderReply> repliesContainer(
            ConcurrentKafkaListenerContainerFactory<String, OrderReply> factory) {

        var container = factory.createContainer("orders.replies");
        container.getContainerProperties().setGroupId("order-reply-client");
        container.setAutoStartup(false);
        return container;
    }

    @Bean
    ReplyingKafkaTemplate<String, OrderRequest, OrderReply> replyingKafkaTemplate(
            ProducerFactory<String, OrderRequest> producerFactory,
            ConcurrentMessageListenerContainer<String, OrderReply> repliesContainer) {

        return new ReplyingKafkaTemplate<>(producerFactory, repliesContainer);
    }
}
```

In this example, the reply container's deserializer configuration must convert values from topic `orders.replies` into `OrderReply`. The template's producer factory must serialize requests into a format the responder can read.

`ReplyingKafkaTemplate` manages the reply container's lifecycle. Configuring `autoStartup(false)` is a common pattern in template configuration examples so the template controls container startup. If managing lifecycle manually, ensure the reply container is running and assigned partitions before sending requests.

### Sending a Request and Awaiting a Response

```java
@Service
public class OrderQueryClient {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template;

    public OrderQueryClient(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template) {
        this.template = template;
    }

    public OrderReply getOrder(String orderId) throws Exception {
        var request = new OrderRequest(orderId);
        var record = new ProducerRecord<String, OrderRequest>(
                "orders.requests", orderId, request);

        RequestReplyFuture<String, OrderRequest, OrderReply> future =
                template.sendAndReceive(record, Duration.ofSeconds(8));

        // Confirm the request was sent successfully by the producer.
        future.getSendFuture().get(5, TimeUnit.SECONDS);

        // Wait for the response whose correlation ID matches the request.
        ConsumerRecord<String, OrderReply> reply =
                future.get(8, TimeUnit.SECONDS);

        return reply.value();
    }
}
```

`sendAndReceive()` returns a `RequestReplyFuture`. This Future has two parts:

- `getSendFuture()`: the result of sending the request to Kafka.
- The main Future `get(...)`: the matching response result or an exception/timeout.

If the producer fails to send the request, the reply future also completes exceptionally with the send error without waiting for the reply timeout to expire. If the request is sent successfully but the responder does not return a response, the Future finishes when the reply timeout expires.

In practice, configure timeouts according to business SLAs and handle `TimeoutException`, `ExecutionException`, and `InterruptedException` separately. Never allow request-reply calls to wait indefinitely.

## 5. Waiting for Reply Container Assignment Before Sending

If the reply container uses `auto.offset.reset=latest`, a client could send a request right as the application starts up, before the reply consumer has been assigned partitions. A very fast responder may process and send a response before the client starts reading the reply topic; that response could be missed.

Since Spring Kafka 2.8.8, `ReplyingKafkaTemplate` provides `waitForAssignment(Duration)` to wait for the reply container to become ready:

```java
@Component
public class RequestReplyStartupCheck implements ApplicationRunner {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template;

    public RequestReplyStartupCheck(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template) {
        this.template = template;
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean assigned = template.waitForAssignment(Duration.ofSeconds(10));
        if (!assigned) {
            throw new IllegalStateException("Reply container was not assigned in time");
        }
    }
}
```

Only send requests after the reply container has been assigned. When using manual partition assignment, the wait duration needs to exceed `pollTimeout` because the assignment callback only fires after the first poll.

## 6. Responder Using @KafkaListener and @SendTo

On the responder side, `@KafkaListener` receives the request and returns the response. `@SendTo` specifies where to send the response.

If `@SendTo` has no value, Spring Kafka reads the reply topic from the request's `KafkaHeaders.REPLY_TOPIC` header. This pairs naturally with `ReplyingKafkaTemplate`, because the template adds the reply topic header to the request.

```java
@Component
public class OrderQueryResponder {

    private final OrderQueryService orderQueryService;

    public OrderQueryResponder(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @KafkaListener(topics = "orders.requests", groupId = "order-query-service")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderQueryService.findOrder(request.orderId());
    }
}
```

The responder's listener container factory must have a `KafkaTemplate` in its `replyTemplate` property to send results. Spring Boot usually auto-configures this template when a suitable bean exists; if creating the factory manually, you must call `factory.setReplyTemplate(kafkaTemplate)`.

Example explicit factory declaration:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderRequest> requestListenerFactory(
        ConsumerFactory<String, OrderRequest> consumerFactory,
        KafkaTemplate<String, OrderReply> replyTemplate) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderRequest>();
    factory.setConsumerFactory(consumerFactory);
    factory.setReplyTemplate(replyTemplate);
    return factory;
}
```

Attach this factory to `@KafkaListener` via `containerFactory = "requestListenerFactory"`. The producer factory backing `replyTemplate` needs a serializer for `OrderReply`.

The Spring Kafka listener infrastructure echoes the correlation ID from the request to the response and uses the reply topic header for routing. Therefore, the client `ReplyingKafkaTemplate` can receive the response, read the correlation ID, and complete the right Future.

If using `@SendTo("orders.replies")`, the responder sends to a fixed topic. The client's reply container must subscribe to that exact topic. For request-reply with multiple client instances, the reply topic/partition must be designed so the response reaches the client that sent the request.

## 7. Reading the Correlation ID on the Responder

Normally, when a listener returns a plain payload and uses `@SendTo`, Spring Kafka echoes the correlation ID automatically. If you need to log or inspect metadata yourself, you can inject the headers as parameters:

```java
@KafkaListener(topics = "orders.requests", groupId = "order-query-service")
@SendTo
public OrderReply handle(
        OrderRequest request,
        @Header(KafkaHeaders.CORRELATION_ID) byte[] correlationId,
        @Header(KafkaHeaders.REPLY_TOPIC) byte[] replyTopic) {

    String correlation = new String(correlationId, StandardCharsets.UTF_8);
    String replyTopicName = new String(replyTopic, StandardCharsets.UTF_8);

    log.info("Handling orderId={}, correlationId={}, replyTopic={}",
            request.orderId(), correlation, replyTopicName);

    return orderQueryService.findOrder(request.orderId());
}
```

In default request-reply, `KafkaHeaders.CORRELATION_ID` and `KafkaHeaders.REPLY_TOPIC` are passed as byte headers. If using a custom header mapper or custom header name, parameter types and conversion rules may differ; align them between producer and consumer.

Do not generate a new correlation ID on the responder. The response must echo the exact correlation ID of the request. If the ID is altered, the client cannot find the matching Future and the response is treated as unmatched.

## 8. Returning Message<?> and Setting Reply Headers Manually

If a listener returns a regular payload, `@SendTo` can route automatically and echo the correlation ID. If the listener returns `Message<?>`, the application may need to set response headers.

Example:

```java
@KafkaListener(topics = "orders.requests", groupId = "order-query-service")
@SendTo
public Message<OrderReply> handle(OrderRequest request) {
    OrderReply reply = orderQueryService.findOrder(request.orderId());

    return MessageBuilder.withPayload(reply)
            .setHeader(KafkaHeaders.KEY, request.orderId())
            .build();
}
```

Since Spring Kafka 2.5, the framework can automatically populate missing reply headers: the topic is taken from `@SendTo` or the request's `KafkaHeaders.REPLY_TOPIC`; correlation ID and reply partition are echoed if present in the request. In versions older than 2.5, when returning `Message<?>`, the application must explicitly set the reply topic and correlation ID.

If sending the response manually with `KafkaTemplate` instead of returning through `@SendTo`, the application must copy the correlation ID from the request to the response and send to the right reply topic/partition. Do not rely on the listener adapter's automatic echo mechanism when publishing directly with a separate template.

## 9. The Three Request-Reply Headers and Routing

By default, `ReplyingKafkaTemplate` uses three headers:

| Header | Content | Usage |
|---|---|---|
| `KafkaHeaders.CORRELATION_ID` | Request ID | Used by the client to look up the pending Future |
| `KafkaHeaders.REPLY_TOPIC` | Reply topic name as bytes | Tells the responder which topic to send the response to |
| `KafkaHeaders.REPLY_PARTITION` | Partition number as a 4-byte big-endian integer | Responder sends the response to the partition requested by the client |

If the reply container subscribes to only one topic or one `TopicPartitionOffset`, the template can detect the reply topic/partition from the container and add the headers automatically. If the container subscribes to multiple topics or complex partition sets, the application must configure reply headers explicitly.

When using `KafkaHeaders.REPLY_PARTITION`, the reply container must be configured to read that exact partition. In some fixed-partition setups, the container must use manual partition assignment rather than Kafka group management. Do not set a reply partition arbitrarily if the client is not reading that partition.

## 10. Multiple Client Instances and Shared Reply Topics

When multiple client instances share a reply topic, you must choose a strategy so each request's response reaches the right instance.

### Dedicated Reply Topic per Instance

Example:

```text
client-1 -> request header reply topic = replies.client-1
client-2 -> request header reply topic = replies.client-2
client-3 -> request header reply topic = replies.client-3
```

Each instance reads only its own reply topic. This isolates traffic but requires per-instance topic and access permission management.

### One Shared Reply Topic, Unique Group ID per Instance

Each client instance uses a different `group.id` when reading the same reply topic. Because the groups are independent, every instance receives all responses; only the instance with the matching pending correlation ID completes its Future, while other instances ignore unmatched responses.

This approach is simpler in terms of topic count, but increases network and consumer traffic. When using a shared reply topic, you can enable `ReplyingKafkaTemplate.setSharedReplyTopic(true)` so unmatched replies are logged at DEBUG rather than ERROR level.

### Dedicated Reply Partition per Instance

You can share a topic while assigning a separate partition to each client instance via `KafkaHeaders.REPLY_PARTITION`. Each instance's reply container must be statically assigned to its corresponding partition. This avoids every instance receiving every response, at the cost of managing partition assignments.

Do not use the same group ID for all client instances when each instance needs to receive responses for its own requests. The consumer group splits partitions across members, causing responses to arrive at an instance other than the one holding the Future.

## 11. Timeouts and Late Responses

Request-reply does not guarantee the responder will always return a response. What can happen:

- The request is not processed because the consumer is stopped or lagging.
- The responder takes longer to process than the client's wait deadline.
- The responder errors out before publishing a response.
- The reply topic/partition is misconfigured.
- The response is sent, but the client's reply container is not ready yet.
- The client times out or shuts down before the response arrives.

`ReplyingKafkaTemplate` has a default reply timeout of 5 seconds; you can pass a `Duration` directly to `sendAndReceive(record, replyTimeout)` to choose a per-request timeout. When time expires, the Future completes with a timeout exception.

A client timeout does not cancel the request already written to Kafka and does not stop the responder. The responder may still finish processing and send a response afterward. A late response no longer has a pending Future to complete; the template treats it as an unexpected reply and may log it.

Therefore:

- Choose timeouts based on SLAs and p95/p99 processing times.
- Cap the number of pending requests to avoid holding too many Futures in memory.
- Handle timeouts with an explicit business status; do not assume the request was never executed.
- If the caller retries a request after a timeout, use a stable request ID/idempotency key so the responder avoids duplicating side effects.
- Track reply timeouts and late/unmatched replies.

## 12. Handling Response Errors

A response can carry either a successful result or business error information. You can represent errors in the DTO:

```java
public record OrderReply(
        String orderId,
        String status,
        String errorCode,
        String errorMessage) {

    public boolean successful() {
        return errorCode == null;
    }
}
```

If you want `ReplyingKafkaTemplate` to complete the Future exceptionally when a response has an error header, you can configure `replyErrorChecker` (since Spring Kafka 2.6.7):

```java
replyingKafkaTemplate.setReplyErrorChecker(record -> {
    Header errorHeader = record.headers().lastHeader("server-error");
    if (errorHeader == null) {
        return null;
    }
    String message = new String(errorHeader.value(), StandardCharsets.UTF_8);
    return new IllegalStateException("Responder failed: " + message);
});
```

When the checker returns an exception, the Future completes exceptionally. Agree on the header name and error format between both sides. Do not put stack traces, tokens, or sensitive data into error headers.

If the reply deserializer can fail, consider wrapping it with `ErrorHandlingDeserializer`. `ReplyingKafkaTemplate` can complete the Future exceptionally when it detects a `DeserializationException`; the client must handle `ExecutionException` and inspect its underlying cause.

## 13. Implementing a Correlation Map Manually Without ReplyingKafkaTemplate

In cases where the responder does not use Spring Kafka or uses a custom reply protocol, you can manually manage a map from correlation ID to `CompletableFuture`. This is an advanced approach; for standard Spring-to-Spring applications, `ReplyingKafkaTemplate` is less prone to lifecycle bugs.

### Sending Requests and Registering Futures Before Publishing

```java
@Component
public class ManualRequestClient {

    private final KafkaTemplate<String, OrderRequest> kafkaTemplate;
    private final ConcurrentMap<String, CompletableFuture<OrderReply>> pending =
            new ConcurrentHashMap<>();

    public ManualRequestClient(KafkaTemplate<String, OrderRequest> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<OrderReply> request(OrderRequest request) {
        String correlationId = UUID.randomUUID().toString();
        var responseFuture = new CompletableFuture<OrderReply>();

        // Register before sending to avoid a fast response arriving before the map has the entry.
        pending.put(correlationId, responseFuture);

        var record = new ProducerRecord<String, OrderRequest>(
                "orders.requests", request.orderId(), request);
        record.headers().add(new RecordHeader(
                KafkaHeaders.CORRELATION_ID,
                correlationId.getBytes(StandardCharsets.UTF_8)));
        record.headers().add(new RecordHeader(
                KafkaHeaders.REPLY_TOPIC,
                "orders.replies".getBytes(StandardCharsets.UTF_8)));

        kafkaTemplate.send(record).whenComplete((result, error) -> {
            if (error != null) {
                pending.remove(correlationId, responseFuture);
                responseFuture.completeExceptionally(error);
            }
        });

        responseFuture.orTimeout(8, TimeUnit.SECONDS)
                .whenComplete((reply, error) -> pending.remove(correlationId, responseFuture));

        return responseFuture;
    }

    @KafkaListener(topics = "orders.replies", groupId = "manual-reply-client")
    public void onReply(ConsumerRecord<String, OrderReply> record) {
        Header header = record.headers().lastHeader(KafkaHeaders.CORRELATION_ID);
        if (header == null) {
            log.warn("Reply without correlation ID: topic={}, partition={}, offset={}",
                    record.topic(), record.partition(), record.offset());
            return;
        }

        String correlationId = new String(header.value(), StandardCharsets.UTF_8);
        CompletableFuture<OrderReply> future = pending.remove(correlationId);
        if (future == null) {
            log.debug("Late or unmatched reply: correlationId={}", correlationId);
            return;
        }

        future.complete(record.value());
    }
}
```

The example illustrates important principles:

1. Use a unique ID for each pending request.
2. Register the Future in the map before publishing the request.
3. Add the correlation ID and reply topic to headers.
4. Remove the map entry on send error, timeout, or reply receipt.
5. If no Future is found, treat the response as late/unmatched rather than pairing it with another request.

The example listener using `groupId = "manual-reply-client"` assumes only a single client instance. When scaling to multiple instances, each instance needs its own group ID so all receive replies and filter via their correlation maps, or use dedicated reply partitions/topics. Sharing a group ID splits replies across instances and can deliver a response to an instance that does not hold the Future.

In production code, add shutdown handling to fail remaining pending Futures exceptionally, bound the number of pending Futures, configure a timeout scheduler, and expose metrics for map size. Do not let the map grow unbounded if the responder goes down.

## 14. Customizing the Correlation Header Name

By default, Spring Kafka uses `KafkaHeaders.CORRELATION_ID`. You can customize the header name on `ReplyingKafkaTemplate` via the `correlationHeaderName` property (along with the reply topic/partition header properties) since Spring Kafka 2.3.

This is helpful when the client communicates with a non-Spring responder or one with an existing header protocol. Since Spring Kafka 3.0, the listener container factory can also configure `correlationHeaderName` to echo custom correlation headers back on responses. Previously, the responder had to copy custom headers manually.

When customizing, both client and responder must use the exact same header name and encoding rules. Do not rename the header on one side and expect the other side to recognize it automatically.

## 15. Correlation ID and Tracing

The Correlation ID pairs request and reply in the Kafka protocol. The Trace ID helps tracing backends link spans across the client, broker-facing code, and responder. Both values can be propagated together:

```text
Request headers:
  kafka_correlationId = "c-101"
  traceparent         = "00-<trace-id>-<span-id>-01"
  request-id          = "req-9001"

Reply headers:
  kafka_correlationId = "c-101"
  traceparent         = context of the reply-handling span
  request-id          = "req-9001" (if the contract requires echoing)
```

Do not replace tracing instrumentation with a correlation ID. A correlation ID typically remains constant across a request-reply pair; trace context may create a new span for each step and should be propagated using standards like W3C Trace Context.

Do not use correlation IDs as metric labels, since each request can have a distinct ID, creating very high cardinality. Put IDs into logs or traces; metrics should use topic, listener, outcome, and exception class with bounded value sets.

## 16. Is Request-Reply Synchronous RPC?

`ReplyingKafkaTemplate` provides an API for awaiting a response, so client code can look like an RPC call. However, Kafka remains an asynchronous messaging system:

- The request is written to a log, and the responder processes it when its consumer receives it.
- The client awaits a Future, but the responder may process it after some delay.
- A client timeout does not cancel the record in Kafka.
- A client retry can create duplicate requests if the responder already processed the first one.
- A reply can arrive late or not arrive at all.

Request-reply fits operations requiring a response within a bounded time, such as short lookups or confirmations. For long workflows, multi-step processes, or operations without tight response SLAs, use event-driven workflows and emit result events instead of holding a request thread waiting for long periods.

If invoking request-reply from an HTTP controller, avoid blocking servlet threads for too long. You can return an async response or use an appropriate `CompletableFuture`/reactive boundary. Bound the number of pending requests to avoid exhausting threads and memory when the responder slows down.

## 17. Testing Correlation IDs

Integration tests should verify both header propagation and correct Future matching:

1. **One request, one reply:** verify the template adds a correlation ID, the reply carries the same ID, and the Future completes with the right payload.
2. **Multiple concurrent requests:** send multiple requests with distinct correlation IDs; intentionally return responses in reverse order and verify each Future receives its right response.
3. **Missing correlation ID:** verify the template auto-generates an ID and the listener still returns a valid reply.
4. **Custom correlation ID:** set the header before sending and verify the responder echoes the exact byte value.
5. **Wrong correlation ID:** have the responder return a different ID; verify the original Future does not mistakenly accept the response.
6. **Reply timeout:** prevent the responder from replying; verify the Future times out as configured.
7. **Late reply:** have the responder reply after timeout; verify the client does not match that reply to another request.
8. **Send failure:** stop the broker or force a producer error; verify both send future and reply future complete exceptionally.
9. **Reply container unassigned:** verify `waitForAssignment()` prevents sending requests before the consumer is ready.
10. **Multiple client instances:** test the reply topic/group/partition strategy so responses are processed only by the waiting instance.
11. **Duplicate request:** resend the same request ID and verify the responder is idempotent.
12. **Reply deserialization/error header:** verify the client receives an exception rather than hanging the Future.

In tests, use `spring-kafka-test` or Testcontainers Kafka. Capture correlation IDs, topics, partitions, offsets, and event/request IDs to verify responses are matched properly. Do not merely check that the listener was invoked; verify that the right Future receives the right response.

## 18. Common Issues

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Future times out even though responder processed it | Reply missing correlation ID or failed to echo exact ID | Check `KafkaHeaders.CORRELATION_ID` on request and reply |
| Response sent but client does not receive it | Wrong reply topic/partition header or reply container unassigned | Check `REPLY_TOPIC`, `REPLY_PARTITION`, and `waitForAssignment()` |
| Multiple clients misreceive or miss replies | Sharing the same group ID across reply consumer instances | Use dedicated reply topics, unique group IDs on a shared topic, or dedicated partitions |
| Response goes to the wrong Future | Duplicate or modified correlation ID | Use a unique ID per pending request and echo it unchanged |
| Request times out but business action still executes | Timeout does not cancel already published requests | Use a request ID/idempotency key to prevent duplicate processing on caller retry |
| Pending Futures grow continuously | Failure to clean up on timeout/send failure/shutdown | Remove map entries or rely on the template's Future lifecycle management |
| No reply when using `@SendTo` | Listener factory missing `replyTemplate` | Configure a `KafkaTemplate` in `factory.setReplyTemplate(...)` |
| Listener returns `Message<?>` but reply is unmatched | Reply message missing topic/correlation headers in older versions or manual sends | Inspect headers; since 2.5 the framework can auto-echo default headers if missing |
| Reply deserialization failure causes unclear client failure | Reply deserializer throws an exception | Use `ErrorHandlingDeserializer` and handle `ExecutionException` |
| Using correlation ID as Kafka key | Confusing routing purpose with pairing purpose | Key by aggregate; keep correlation ID in headers |

## 19. Request-Reply Design Workflow

1. Identify operations that genuinely need a response within a bounded time; long workflows should use events.
2. Choose `ReplyingKafkaTemplate` if both client and responder use Spring Kafka; only manage a map manually for specialized protocols.
3. Choose a unique correlation ID per pending request; preserve the ID on the response.
4. Determine reply topic/partition and configure the reply listener container.
5. Wait for reply container assignment before sending requests, especially when using `auto.offset.reset=latest`.
6. Configure `@KafkaListener` with `@SendTo` and an appropriate reply template.
7. Set SLA-based timeouts and handle send failures, reply timeouts, late replies, and deserialization errors.
8. Use a separate request ID/idempotency key if callers may resend requests.
9. With multiple client instances, design reply topics/groups/partitions so every response reaches the right instance.
10. Test concurrent requests, out-of-order responses, timeouts, restarts, and duplicates.

## 20. Summary

- A Correlation ID is an identifier used to pair a response with its corresponding request when multiple requests run concurrently.
- Spring Kafka uses `KafkaHeaders.CORRELATION_ID`; request-reply also uses `REPLY_TOPIC` and optionally `REPLY_PARTITION`.
- `ReplyingKafkaTemplate` manages correlation IDs and Futures automatically; `sendAndReceive()` returns a `RequestReplyFuture` with a send future and a reply future.
- `@KafkaListener` combined with `@SendTo` can send responses back to the reply topic in the request header and echo the correlation ID.
- `waitForAssignment()` since Spring Kafka 2.8.8 helps avoid sending requests before the reply consumer is ready.
- Timeouts do not cancel sent requests; late responses may no longer have a matching Future.
- Correlation ID differs from request ID, event ID, trace ID, and Kafka key; use a separate idempotency key to guard against duplicate processing.
- Multiple client instances require proper reply topic, group ID, or partition assignment design so responses return to the right instance.
- If implementing a correlation map manually, clean up entries on send errors, timeouts, replies, and shutdown.

The Correlation ID is the core element that makes request-reply work when requests are processed asynchronously and responses may arrive out of order. By combining `ReplyingKafkaTemplate`, reply topics, `@SendTo`, and explicit timeouts, Spring Kafka applications can match responses accurately and control late or lost reply cases.

## References

- [Spring Kafka Reference — Sending Messages and ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Kafka Reference — Forwarding Listener Results using @SendTo](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/annotation-send-to.html)
- [Spring Kafka API — ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
