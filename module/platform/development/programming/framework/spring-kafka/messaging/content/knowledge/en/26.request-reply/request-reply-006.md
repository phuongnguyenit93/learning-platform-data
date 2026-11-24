# Declaring a Reply Template

## Lesson Objective

In the **Request-reply** chapter, this lesson walks through declaring and using `ReplyingKafkaTemplate` to send a request to Kafka and await its corresponding response. Spring Kafka combines a producer sending requests, a consumer container listening to a reply topic, and a correlation ID to match responses with original requests.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, KafkaTemplate, and @KafkaListener, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter topics, transactions, exactly-once semantics, concurrency, and testing. Request-reply is a coordination pattern between producer and consumer when an application needs a response, alongside the standard asynchronous event-driven model.

After this lesson, learners will be able to:

- Explain request-reply on Kafka and the participating components.
- Distinguish `KafkaTemplate` from `ReplyingKafkaTemplate`.
- Declare a producer factory for requests and a consumer container for replies.
- Configure the reply template and timeouts.
- Send requests with `sendAndReceive` and read responses.
- Write listeners that process requests and reply using `@SendTo`.
- Understand correlation ID, reply topic, and reply partition.
- Design consumer groups for reply topics when running multiple instances.
- Handle timeouts, send failures, late replies, and duplicates.
- Test the full request-reply flow with Kafka.

## 1. What Is Request-Reply on Kafka?

Kafka is designed primarily for asynchronous communication via topics. Producers send records without waiting for consumers to finish processing them. In some cases, an application needs to send a request and receive a corresponding result, such as:

- The Order service asking the Pricing Service for current prices.
- An API asking a worker to check credit limits and waiting for the result.
- An application looking up processing status from another service.
- A command requiring an accept or reject response.

Request-reply establishes a convention on top of Kafka:

1. The client sends a request record to the request topic.
2. The request carries reply topic metadata so the server knows where to send the response.
3. The server reads the request, executes business logic, and sends the response to the reply topic.
4. The client receives the response and uses the correlation ID to match it to the pending request.

~~~mermaid
sequenceDiagram
    participant C as Request Client
    participant R as Request Topic
    participant S as Request Service
    participant P as Reply Topic
    C->>R: Request + reply topic + correlation ID
    R->>S: @KafkaListener receives request
    S->>S: Execute business logic
    S->>P: Response + correlation ID
    P->>C: Reply container receives response
    C->>C: Match response with request
~~~

Kafka has no separate broker-level request-reply protocol. Spring Kafka builds this mechanism using topics, headers, and consumer containers.

## 2. KafkaTemplate and ReplyingKafkaTemplate

`KafkaTemplate<K,V>` is the API for sending records to Kafka. Sending returns a future to track delivery to the broker, but that future does not represent consumer processing results.

`ReplyingKafkaTemplate<K,V,R>` extends the send model by awaiting a matching reply. The three generic types mean:

- `K`: key type of requests and replies.
- `V`: value type of requests.
- `R`: value type of replies.

Example:

~~~java
ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
~~~

Where:

- Request key is `String`.
- Request payload is `OrderRequest`.
- Reply payload is `OrderReply`.

| Component | Role |
|---|---|
| KafkaTemplate | Sends records and tracks broker acknowledgment |
| ReplyingKafkaTemplate | Sends requests and awaits corresponding replies |
| Request topic | Where the server receives requests |
| Reply topic | Where the client receives responses |
| Reply listener container | Consumer container listening to the reply topic |
| Correlation ID | Pairs responses with pending requests |

Do not use `KafkaTemplate.send()` and treat the send acknowledgment as a business response. Broker acknowledgment of record receipt does not mean the service successfully processed the request.

## 3. Designing Request and Reply Payloads

Define requests and replies clearly, including a business identifier when traceability is needed.

Example:

~~~java
public record OrderRequest(
    String requestId,
    String orderId,
    String customerId
) {
}
~~~

~~~java
public record OrderReply(
    String requestId,
    boolean accepted,
    String message,
    String invoiceId
) {
}
~~~

`requestId` is a business identifier inside the payload. It is useful for logging, tracing, and idempotency. Kafka's correlation ID is transport metadata used by Spring to match replies with pending futures. The two values may coexist while serving two different purposes.

Do not rely solely on the correlation ID to prevent duplicate processing. If a request is redelivered, the server still needs idempotency keyed by request ID or command ID when business logic creates side effects.

## 4. Important Headers

Spring Kafka uses several headers for request-reply:

| Header | Meaning |
|---|---|
| `KafkaHeaders.CORRELATION_ID` | Key matching a reply with a request |
| `KafkaHeaders.REPLY_TOPIC` | Topic where the server should send the reply |
| `KafkaHeaders.REPLY_PARTITION` | Target partition for the reply if specified |
| `KafkaHeaders.RECEIVED_KEY` | Key of the received record during message conversion |
| `KafkaHeaders.RECEIVED_TOPIC` | Topic of the received record |

`ReplyingKafkaTemplate` generates a correlation ID if the request lacks the appropriate header and attaches reply destination details per template/container configuration. When the response comes back, the template uses the correlation ID to locate the pending future.

The correlation ID must be preserved from request to reply. If the server creates a new response message and drops the correlation ID header, the client cannot match the response to the original request.

Do not manually overwrite headers managed by the template without a clear reason. If the application needs its own correlation IDs, establish a convention and ensure both client and server follow it.

## 5. Declaring the Request Producer and Reply Consumer

A `ReplyingKafkaTemplate` requires two core components:

- `ProducerFactory<K,V>` to send requests.
- `GenericMessageListenerContainer<K,R>` to receive replies.

The example assumes String keys, `OrderRequest` requests, and `OrderReply` replies.

### 5.1. ProducerFactory for Requests

~~~java
@Bean
public ProducerFactory<String, OrderRequest> orderRequestProducerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );

    return new DefaultKafkaProducerFactory<>(properties);
}
~~~

This producer factory serializes request keys and request payloads. In real projects, bootstrap servers and producer properties can be bound from environment configuration; the example above shows the core properties so it is clear which serializers are used.

### 5.2. ConsumerFactory for Replies

The reply container needs a consumer factory with a value deserializer for `OrderReply`:

~~~java
@Bean
public ConsumerFactory<String, OrderReply> orderReplyConsumerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    properties.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    properties.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderReply.class.getName()
    );
    properties.put(
        JsonDeserializer.TRUSTED_PACKAGES,
        "com.example.orders"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

JSON properties must be adjusted to match your application's packages and type mapping configuration. Only add trusted packages that are strictly necessary; do not open trusted packages broadly in production environments.

### 5.3. Reply Listener Container

Create a container listening to the reply topic:

~~~java
@Bean
public ConcurrentMessageListenerContainer<String, OrderReply>
        orderRepliesContainer(
                ConcurrentKafkaListenerContainerFactory<String, OrderReply>
                        orderReplyContainerFactory,
                Environment environment) {

    ConcurrentMessageListenerContainer<String, OrderReply> container =
        orderReplyContainerFactory.createContainer("commerce.order.replies");

    String replyGroupId =
        environment.getRequiredProperty("app.kafka.reply-group-id");

    container.getContainerProperties().setGroupId(replyGroupId);
    return container;
}
~~~

The container is created from the factory dedicated to the reply payload. The group ID must be chosen according to your multi-instance deployment model; a later section explains why you should not indiscriminately share a group ID across all client instances.

The factory used here must be configured with `orderReplyConsumerFactory`. You can declare a dedicated factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderReply>
        orderReplyContainerFactory(
                ConsumerFactory<String, OrderReply> orderReplyConsumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderReply>();

    factory.setConsumerFactory(orderReplyConsumerFactory);
    return factory;
}
~~~

### 5.4. Declaring ReplyingKafkaTemplate

Once the request producer factory and reply container are defined, create the template:

~~~java
@Bean
public ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
        orderReplyingKafkaTemplate(
                ProducerFactory<String, OrderRequest> orderRequestProducerFactory,
                ConcurrentMessageListenerContainer<String, OrderReply>
                        orderRepliesContainer) {

    var template = new ReplyingKafkaTemplate<>(
        orderRequestProducerFactory,
        orderRepliesContainer
    );

    template.setDefaultReplyTimeout(Duration.ofSeconds(10));
    return template;
}
~~~

`setDefaultReplyTimeout` sets the default wait time for replies. Choose the timeout based on the request SLA and actual service processing time. Avoid setting a timeout so short that the client repeatedly errors out while the server is still processing normally.

The reply container must be started and subscribed to the reply topic before the client sends requests. In a Spring application, the container is managed by the bean lifecycle. You can verify container status in integration tests and at startup if needed.

## 6. Sending Requests and Receiving Replies

The client creates a record to send to the request topic:

~~~java
@Service
public class OrderRequestClient {

    private final ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
        replyingKafkaTemplate;

    public OrderRequestClient(
            ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
                    replyingKafkaTemplate) {
        this.replyingKafkaTemplate = replyingKafkaTemplate;
    }

    public OrderReply request(OrderRequest request) throws Exception {
        ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>(
                "commerce.order.requests",
                request.orderId(),
                request
            );

        RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(record);

        ConsumerRecord<String, OrderReply> replyRecord =
            future.get(12, TimeUnit.SECONDS);

        return replyRecord.value();
    }
}
~~~

`sendAndReceive` sends the request and returns a `RequestReplyFuture`. The future completes when the template receives a reply with a matching correlation ID or when a configured error/timeout occurs.

You can track the request send outcome separately:

~~~java
SendResult<String, OrderRequest> sendResult =
    future.getSendFuture().get(5, TimeUnit.SECONDS);
~~~

The send future indicates whether the producer successfully sent the request to the broker per acknowledgment configuration. The reply future indicates whether the response was received. These are two distinct milestones.

In production services, handle these scenarios explicitly:

- Request send failure.
- Reply not received within the wait window.
- Reply future completed exceptionally.
- Thread interrupted.
- Reply carrying a business rejection.

Do not catch all exceptions and return a fake success response. Timeouts and send errors must be surfaced clearly to the caller or translated into an appropriate business state.

## 7. Declaring the Reply Template on the Server Side

The server needs a consumer factory to read requests and a producer template to send replies.

The server-side consumer factory must deserialize the right request type:

~~~java
@Bean
public ConsumerFactory<String, OrderRequest> orderRequestConsumerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ConsumerConfig.GROUP_ID_CONFIG,
        "order-command-service"
    );
    properties.put(
        ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class
    );
    properties.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        JsonDeserializer.class
    );
    properties.put(
        JsonDeserializer.VALUE_DEFAULT_TYPE,
        OrderRequest.class.getName()
    );
    properties.put(
        JsonDeserializer.TRUSTED_PACKAGES,
        "com.example.orders"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

~~~java
@Bean
public ProducerFactory<String, OrderReply> orderReplyProducerFactory() {
    Map<String, Object> properties = new HashMap<>();

    properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
    );
    properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
    );
    properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
    );

    return new DefaultKafkaProducerFactory<>(properties);
}

@Bean
public KafkaTemplate<String, OrderReply> orderReplyKafkaTemplate(
        ProducerFactory<String, OrderReply> orderReplyProducerFactory) {
    return new KafkaTemplate<>(orderReplyProducerFactory);
}
~~~

The listener container factory needs to know which KafkaTemplate to use for sending responses:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderRequest>
        orderRequestListenerContainerFactory(
                ConsumerFactory<String, OrderRequest> orderRequestConsumerFactory,
                KafkaTemplate<String, OrderReply> orderReplyKafkaTemplate) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderRequest>();

    factory.setConsumerFactory(orderRequestConsumerFactory);
    factory.setReplyTemplate(orderReplyKafkaTemplate);
    return factory;
}
~~~

`setReplyTemplate` supplies the producer for the listener's reply mechanism. The consumer factory must deserialize requests into `OrderRequest`, while the reply template must serialize responses into `OrderReply`.

## 8. Writing a Request Listener That Replies with @SendTo

The listener processes the request and returns an object. `@SendTo` without specifying a fixed topic tells Spring Kafka to use the reply destination in the request's header.

~~~java
@Service
public class OrderRequestListener {

    private final OrderCommandService orderCommandService;

    public OrderRequestListener(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @KafkaListener(
        topics = "commerce.order.requests",
        groupId = "order-command-service",
        containerFactory = "orderRequestListenerContainerFactory"
    )
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderCommandService.handle(request);
    }
}
~~~

Execution flow:

1. ReplyingKafkaTemplate sends the request along with the reply topic and correlation ID.
2. The listener receives the request.
3. The method returns an OrderReply.
4. Spring Kafka uses the reply template to send the response to the reply topic from the header.
5. The correlation ID is preserved in the response headers so the client can match the result.

If using `@SendTo("commerce.order.replies")` with a fixed topic, responses go to that destination. This is useful when all requests return to a fixed topic, but you must ensure the client's reply container is listening to that exact topic.

### 8.1. Returning a Business Response When a Request Is Rejected

Not every rejection outcome is a technical error requiring a retry. If the request is valid but fails business rules, the server can return a response indicating the rejected status:

~~~java
@KafkaListener(
    topics = "commerce.order.requests",
    groupId = "order-command-service",
    containerFactory = "orderRequestListenerContainerFactory"
)
@SendTo
public OrderReply handle(OrderRequest request) {
    if (!orderCommandService.canAccept(request)) {
        return new OrderReply(
            request.requestId(),
            false,
            "Order cannot be accepted",
            null
        );
    }

    String invoiceId = orderCommandService.createInvoice(request);

    return new OrderReply(
        request.requestId(),
        true,
        "Accepted",
        invoiceId
    );
}
~~~

A business rejection response is still a valid reply. If the method throws an exception instead, Spring Kafka routes the error to the listener container's error handler; the client may receive no response and eventually time out unless the application defines a custom error reply convention.

## 9. Correlation ID Pairs Requests and Replies

Suppose two requests are pending concurrently:

~~~text
Request A -> correlation ID: 7f01
Request B -> correlation ID: 9c82

Reply B -> correlation ID: 9c82
Reply A -> correlation ID: 7f01
~~~

Replies can arrive out of send order. ReplyingKafkaTemplate uses the correlation ID to complete the right future, rather than relying on record position in the reply topic.

Do not match responses manually by:

- Request send order.
- Reply topic offset.
- Response arrival time.
- Record key if the key is not defined as the correlation ID.

If the server constructs a new response Message, ensure required headers are preserved or forwarded by Spring Kafka's reply mechanism. When manually creating a ProducerRecord and publishing a reply, copy the correlation ID and required metadata explicitly.

### 9.1. Using a Business Correlation ID

You can include a request ID in the payload to support auditing and idempotency. Do not confuse it with the correlation header managed by the request-reply infrastructure.

A possible convention:

- requestId: identifies the business command.
- correlationId: identifies a specific request-reply exchange.
- traceId: identifies a distributed trace across services.

The three values can differ. Recording them in logs/traces helps distinguish a retried command from a specific reply wait attempt.

## 10. Running Multiple Instances and Reply Consumer Groups

This is a critical configuration point.

Suppose two client instances both send requests and both listen to one reply topic. Each instance has its own ReplyingKafkaTemplate and an in-memory registry of pending futures.

If the two instances share one consumer group for the reply topic, Kafka splits partitions between them. The reply for request A may be delivered to instance B, while request A's future lives only on instance A. Instance B lacks the matching future and cannot complete A's request.

With a shared reply topic, each client instance usually needs its own group ID so every instance receives all reply records. Each ReplyingKafkaTemplate then completes only the futures whose correlation ID it is tracking; replies meant for other instances will not match local pending requests.

Example local configuration:

~~~yaml
app:
  kafka:
    reply-group-id: order-reply-client-local
~~~

In production, the group ID must include a unique instance/pod identifier. Do not use the same static value for all replicas when they listen to a shared reply topic.

When a reply topic is shared across multiple instances, you can configure the template to mark it as a shared reply topic if supported by your Spring Kafka version:

~~~java
template.setSharedReplyTopic(true);
~~~

This setting signals the intent to share the reply topic. It does not eliminate the need to design group IDs so each instance receives the replies it needs.

### 10.1. Reply Topic and Partitions

The reply topic should be pre-created or managed per environment topic policy. When using a specific reply partition:

- The partition must exist on the reply topic.
- The client's reply consumer container must be subscribed/assigned to that partition.
- The server must send the response to the specified partition.
- When increasing partition counts, re-evaluate routing and reply distribution.

If partition-level routing is unnecessary, you can use a shared reply topic and let the partitioner pick partitions. With multiple instances, combine that with unique consumer groups as described above.

Do not use a reply topic as long-term event storage for diverse consumers unless retention, ACLs, and schemas are designed for it. Reply topics usually have a different lifecycle and purpose from event topics.

## 11. Timeouts and Late Replies

Request-reply always needs a timeout because the server may stop, a request may fail, or a response may never arrive.

Default configuration on the template:

~~~java
template.setDefaultReplyTimeout(Duration.ofSeconds(10));
~~~

The timeout should reflect normal processing time, broker latency, and caller SLAs. You can set per-request timeouts if your API version supports the corresponding overload.

A timeout does not mean the request was canceled in Kafka. When the client stops waiting:

- The request may still sit in the topic.
- The server may still be processing it.
- Side effects may already be complete.
- A late reply may no longer have a future to match.
- The caller might resend the request and create duplicates without idempotency.

Therefore, maintain a stable request ID and duplicate-handling rules on the server. A timeout should be interpreted as "the caller did not receive a result within the allowed window," not as proof that the business operation failed.

### 11.1. Distinguishing Timeouts, Send Failures, and Business Rejections

| Outcome | Meaning | How to Handle |
|---|---|---|
| Send failure | Producer failed to send the request per acknowledgment | Report send error and consider retrying |
| Reply timeout | Reply was not received in time | Check server, lag, reply topic, and request status |
| Business rejection | Server returned a valid reply rejecting the operation | Return the rejection result to the caller |
| Processing exception | Server listener threw an exception | Handle via error handler/DLT; caller may time out |
| Late reply | Reply arrived after the future timed out | Log/observe; do not assume the caller will receive it |

### 11.2. Do Not Blindly Retry Requests After a Timeout

If the client times out and sends a new request with a different ID, the server may process both and produce duplicate side effects.

Best practices:

- Keep requestId stable when retrying the same command.
- Have the server store results by requestId if deduplication is needed.
- Define a retention period for idempotency records.
- Allow callers to query request status if needed.
- Distinguish transport retries from creating a new business command.

## 12. Server-Side Error Handling

A request listener may encounter deserialization errors, validation errors, database failures, or downstream errors.

Categorize errors:

- Invalid request: return a business rejection if deserialized and able to reply; otherwise isolate the record per policy.
- Transient error: bounded retries via the error handler.
- Unrecoverable error: DLT and alerting.
- Reply publish error: monitor producer send failures and determine whether the request can be safely reprocessed.

If the server executes side effects successfully but fails to send the reply, the request may be redelivered. Idempotency by requestId prevents repeating side effects.

Do not swallow exceptions and let the listener finish normally if a response is mandatory. The container might commit the offset while the caller only sees a timeout.

## 13. Security and Controlling the Reply Destination

The reply topic can be sent in request headers. The server must guard against clients arbitrarily requesting publishes to any topic.

Safeguards:

- Only allow replies to an approved list of topics.
- Use ACLs to restrict producer write permissions to reply topics.
- Validate the reply topic header before sending if accepting requests from multiple tenants or untrusted clients.
- Never place secrets or sensitive data in correlation IDs.
- Enforce size limits on requests/replies.
- Validate schemas and JSON deserializer trusted packages.
- Set appropriate retention and read permissions on reply topics.

In controlled internal environments, reply destinations are usually pre-configured. When accepting requests from external sources, never blindly trust the reply topic header as an arbitrary destination.

## 14. Testing Request-Reply

Integration tests should start real Kafka via EmbeddedKafka or Testcontainers and test both client and server.

Important test cases:

1. Sending a request and receiving a successful reply.
2. Reply carries the right payload and key.
3. Correlation ID is preserved and matched accurately across concurrent requests.
4. Server returns a business rejection.
5. Server does not respond and the client times out.
6. Request send fails due to broker or producer configuration.
7. Late reply arrives after timeout.
8. Server handles duplicate requests without duplicating side effects.
9. Multiple client instances share a reply topic with distinct group IDs.
10. Reply topic lacks partitions or has insufficient ACLs.
11. Server hits an error and the request goes through retry/DLT per policy.

Example checking the futures:

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
    replyingKafkaTemplate.sendAndReceive(requestRecord);

SendResult<String, OrderRequest> sendResult =
    future.getSendFuture().get(5, TimeUnit.SECONDS);

ConsumerRecord<String, OrderReply> reply =
    future.get(12, TimeUnit.SECONDS);

assertThat(sendResult.getRecordMetadata().topic())
    .isEqualTo("commerce.order.requests");
assertThat(reply.value().requestId())
    .isEqualTo(request.requestId());
~~~

In integration tests, wait for replies using futures with bounded timeouts. Never use fixed sleeps to guess when a response will appear.

## 15. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Future receives no reply | Reply container not started or subscribed to wrong topic | Check lifecycle and topic |
| Future times out | Server error, reply topic lag, or reply sent to wrong destination | Check listener, producer, and headers |
| Reply arrives but fails to match | Correlation ID lost or overwritten | Check request and reply headers |
| Some instances time out randomly | Multiple instances share the same reply consumer group | Use a distinct group ID per client instance |
| Reply fails to deserialize | Consumer factory uses wrong deserializer/type mapping | Check OrderReply deserializer |
| Server sends no response | Missing reply template or @SendTo | Configure reply template on listener factory |
| Send succeeds but caller times out | Broker accepted request but server did not process or reply | Distinguish send future from reply future |
| Request processed twice | Caller retried after timeout or Kafka redelivered | Enforce idempotency by requestId |
| Reply topic receives no records | Wrong ACL, partition, or topic configuration | Check topic and producer permissions |
| Reply arrives after timeout | Server takes longer than caller SLA | Adjust timeout and status query flow |

## 16. Checklist Before Taking Reply Template to Production

- [ ] Request and reply have clear schemas?
- [ ] Request ProducerFactory uses the right serializer?
- [ ] Reply ConsumerFactory uses the right deserializer?
- [ ] Reply container subscribes to the right topic and is started?
- [ ] ReplyingKafkaTemplate uses the right producer factory and reply container?
- [ ] Server-side listener factory has a reply template?
- [ ] Request listener has @SendTo or an equivalent reply mechanism?
- [ ] Correlation ID is preserved through the response?
- [ ] Reply topic has sufficient partitions and ACLs?
- [ ] Each client instance has an appropriate group ID when sharing a reply topic?
- [ ] Timeouts reflect SLAs and are handled explicitly?
- [ ] Timeouts are not mistaken for request cancellation?
- [ ] Server is idempotent by requestId?
- [ ] Rules exist for handling business rejections and processing exceptions?
- [ ] Send failures, reply timeouts, and late replies are monitored?
- [ ] Concurrent requests and multi-instance setups have been tested?
- [ ] Reply destination security has been verified?

## Conclusion

`ReplyingKafkaTemplate<K,V,R>` combines a request-sending producer with a consumer container listening to a reply topic. The template attaches correlation IDs and reply destination details to pair responses with pending requests. On the server side, a listener can return a payload via `@SendTo` when the listener container factory is configured with a reply template.

During implementation, declare compatible serializers/deserializers for requests and replies, start the reply container before sending requests, set SLA-based timeouts, and design group IDs properly when multiple client instances share a reply topic. Timeouts do not cancel sent requests; therefore, the server needs idempotency, while the client must distinguish send failures, reply timeouts, and business rejections. Testing correlation, late replies, duplicates, and multi-instance deployments ensures reliable request-reply operation.

