# Routing Replies per Request

In the request/reply pattern on Kafka, a requester sends a request and waits for a corresponding response. When there are multiple concurrent requests, multiple requester instances, or multiple partitions, the responder must know where each response needs to be sent. Spring Kafka uses reply headers together with a correlation ID to perform this routing.

`ReplyingKafkaTemplate` can automatically populate reply topic and reply partition information on the request when the reply container is configured with a single topic or a single `TopicPartitionOffset`. With more complex containers, the requester must supply the reply headers. The responder-side listener reads those headers and sends the response back to the right topic/partition. The reply listener container on the requester side receives the response, matches the correlation ID, and completes the pending future. As a result, a single reply topic can serve many pending requests without the requester having to scan payloads to locate responses.

Reply routing works properly only when the requester has started the reply container, the container is subscribed/assigned to the right topic or partition to receive from, the request preserves the reply headers, and the responder sends the response according to those headers. If headers are lost, the reply topic is wrong, or the response goes to a partition the requester is not reading, the future will time out even though the responder may have completed business processing.

## 1. Components of Request/Reply Routing

A request/reply flow consists of the following components:

| Component | Role |
|---|---|
| Requester | Sends requests using `ReplyingKafkaTemplate` and awaits the future |
| Request topic | Topic holding requests sent by the requester |
| Responder listener | Receives requests, processes them, and produces responses |
| Reply topic | Topic receiving responses |
| Reply partition | Specific partition receiving responses for the corresponding requester or request |
| Correlation ID | Pairs the response with the original request's future |
| Reply listener container | Consumer container receiving responses and passing them to `ReplyingKafkaTemplate` |

General flow:

```text
Requester A
  ReplyingKafkaTemplate
  reply container reads replies partition 0
       |
       | request + REPLY_TOPIC + REPLY_PARTITION + CORRELATION_ID
       v
Kafka request topic
       |
       v
Responder @KafkaListener
       |
       | reads reply headers
       v
Reply template sends response to the right topic/partition
       |
       v
Kafka reply topic, partition 0
       |
       v
Requester A's reply container
       |
       | correlation ID matches
       v
Request future completes
```

In the example, requester A uses partition 0. If requester B uses partition 1, the responder sends B's response to partition 1. Reply containers must be configured so each requester receives the partition designated for it.

## 2. Headers Used for Reply Routing

Spring Kafka provides key headers in `KafkaHeaders`:

| Header | Meaning |
|---|---|
| `KafkaHeaders.REPLY_TOPIC` | Name of the reply topic where the responder must send the response |
| `KafkaHeaders.REPLY_PARTITION` | Target partition in the reply topic; may be omitted when routing by key/partitioner |
| `KafkaHeaders.CORRELATION_ID` | ID linking a response to a pending request |
| `KafkaHeaders.TOPIC` | Target topic of the request when sending with Spring `Message<?>` |
| `KafkaHeaders.MESSAGE_KEY` | Key of the request Kafka record |

`ReplyingKafkaTemplate` usually adds the reply topic, reply partition (when a specific partition is configured), and correlation ID automatically. Applications do not need to generate a correlation ID manually when using the default mechanism. The responder must retain request/reply headers and echo the correlation ID onto the response.

Do not confuse `KafkaHeaders.REPLY_TOPIC` with `KafkaHeaders.TOPIC`: the former indicates where to receive responses; the latter specifies where to send requests. Similarly, `KafkaHeaders.REPLY_PARTITION` is the response's partition, not the request's partition.

## 3. ReplyingKafkaTemplate and the Reply Container

`ReplyingKafkaTemplate<K, V, R>` combines a `ProducerFactory` to send requests with a listener container to receive responses. There are two common ways to configure the reply container: subscribing to a reply topic with a distinct group ID per requester (the fan-out pattern), or statically assigning a `TopicPartitionOffset` per requester (the dedicated partition pattern, without group management).

The example below uses the fan-out pattern on a single reply topic. Each requester instance must have its own group ID; every instance receives all responses, but the template only completes futures with a matching correlation ID:

```java
@Configuration
public class RequestReplyConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConsumerFactory<String, String> consumerFactory,
            @Value("${app.kafka.reply-group-id}") String replyGroupId) {

        ContainerProperties properties = new ContainerProperties("orders.replies");
        properties.setGroupId(replyGroupId);
        Properties consumerProperties = new Properties();
        consumerProperties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
        properties.setKafkaConsumerProperties(consumerProperties);
        return new ConcurrentMessageListenerContainer<>(
                consumerFactory, properties);
    }

    @Bean
    public ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String> repliesContainer) {

        var template = new ReplyingKafkaTemplate<>(producerFactory, repliesContainer);
        template.setSharedReplyTopic(true);
        return template;
    }
}
```

`app.kafka.reply-group-id` must be a unique group ID per requester instance, such as `order-reply-client-${INSTANCE_ID}`. `latest` starts new groups at the end of the log so they do not replay old replies that existed before the instance started. `setSharedReplyTopic(true)` tells the template that the reply topic is shared; responses without a pending correlation ID are logged at DEBUG instead of ERROR. This pattern creates fan-out: every response is read by every requester group, even though only one instance completes the corresponding future.

`setSharedReplyTopic(true)` has been available since Spring Kafka 2.3. If using an older version, check the corresponding API and adjust log levels for unmatched correlation ID responses as supported by that version.

The reply container must be started and receive its assignment before sending requests. You can wait using:

```java
if (!replyingKafkaTemplate.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException("Reply container has not been assigned partitions");
}
```

If a request is sent before the reply container is ready, the response may be written to the topic without the consumer receiving it in time; with offset reset set to `latest`, late-startup scenarios can cause responses written before assignment to be skipped.

## 4. How ReplyingKafkaTemplate Selects the Reply Destination

Since Spring Kafka 2.2, the template tries to infer reply headers from the reply container's configuration:

- If the container subscribes to exactly one topic, the template can auto-set `REPLY_TOPIC`; it does not automatically pick a specific partition just because the topic has multiple partitions.
- If the container is configured with exactly one `TopicPartitionOffset`, the template can auto-set both `REPLY_TOPIC` and `REPLY_PARTITION`.
- If the container listens to multiple topics, uses a pattern, or has a more complex configuration, the application must provide appropriate reply headers.

Therefore, merely calling `waitForAssignment()` does not mean the template knows a target partition. With the dedicated partition pattern, you must configure the container with one fixed `TopicPartitionOffset`. With the per-group fan-out pattern, you only need one reply topic and a separate group ID per requester.

Do not hard-code the reply partition inside the responder. The responder should use each request's headers because each request may belong to a different requester instance or partition.

## 5. Responder Reading Reply Headers and Sending Responses

With `@KafkaListener`, Spring Kafka can automatically send the listener's return value if the container factory is configured with a reply template. When using `@SendTo` without specifying a fixed topic, the framework uses the reply destination in the request's headers.

```java
@Configuration
public class OrderResponderConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            requestListenerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTemplate<String, String> replyTemplate) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.setReplyTemplate(replyTemplate);
        return factory;
    }
}
```

Listener:

```java
@Component
public class OrderQueryListener {

    @KafkaListener(
            topics = "orders.requests",
            groupId = "orders-service",
            containerFactory = "requestListenerFactory")
    @SendTo
    public OrderReply handle(OrderRequest request) {
        return orderService.find(request.orderId());
    }
}
```

With `@SendTo` without a fixed destination, Spring Kafka reads the reply topic and partition from the request headers. The reply template sends the response and the framework copies the correlation ID from the request to the response. If the reply destination header is missing, the listener cannot know where the response should go; the request/reply may fail or raise an error depending on configuration.

If you need direct control over headers or need to send multiple responses, you can accept `Message<?>`/`ConsumerRecord` and send the response via `KafkaTemplate`. When building responses manually, copy the correlation ID and set the right reply topic/partition; avoid accidentally sending the response to a fixed topic that does not match the requester.

## 6. Routing with Fixed Reply Partitions

Suppose reply topic `orders.replies` has two partitions. Requester A is configured to statically listen to partition 0, and requester B statically listens to partition 1. This is manual assignment via `TopicPartitionOffset`, not assignment managed by the consumer group coordinator.

Example creating a container for one requester instance:

```java
@Bean
public ConcurrentMessageListenerContainer<String, String> repliesContainer(
        ConsumerFactory<String, String> consumerFactory,
        @Value("${app.kafka.reply-partition}") int replyPartition) {

    ContainerProperties properties = new ContainerProperties(
            new TopicPartitionOffset("orders.replies", replyPartition));
    // Do not set group.id: the container is assigned partitions directly.
    return new ConcurrentMessageListenerContainer<>(consumerFactory, properties);
}
```

Each instance must receive a different `reply-partition`, and that partition must exist. Do not use consumer group management in this pattern; if you configure a group ID and subscribe via a group, Kafka may redistribute partitions per its assignment strategy instead of keeping fixed partitions as required.

```text
Requester A                         Requester B
reply partition = 0                reply partition = 1
      |                                   |
      | request A                         | request B
      | REPLY_PARTITION=0                 | REPLY_PARTITION=1
      +----------------+------------------+
                       v
                orders.requests
                       |
                       v
                 Responder
                 /        \
                /          \
      response A            response B
      partition 0           partition 1
          |                     |
          v                     v
    Requester A             Requester B
```

The responder sends responses according to the partition header. Each requester only consumes its statically assigned partition to receive responses for the requests it sent. This avoids having all requesters read the entire reply topic.

Partition routing only works when the reply topic has valid partitions and the requester is actually assigned that partition. If the header specifies a non-existent partition, the producer sending the response will fail. Ensure the reply topic's partition count suffices for the number of requester instances or chosen partition-sharing strategy.

## 7. Multiple Requester Instances Pattern

There are three common patterns:

| Pattern | How It Works | Pros / Trade-offs |
|---|---|---|
| Dedicated reply topic per instance | Each requester has its own topic and its reply container reads only that topic | Simple isolation; increases topic count and requires topic lifecycle management |
| Shared reply topic, dedicated partition per instance | Each requester uses `TopicPartitionOffset` to manually assign one partition; requests carry the reply partition header | Fewer topics, explicit routing; no group management and must manage partitions per instance |
| Shared reply topic, unique group ID per instance | Each group receives all responses; the template only completes futures with matching correlation IDs and ignores others | Easy to deploy; every response fans out to all instances, increasing traffic and consumer cost |

Do not share a single consumer group across all requesters if the reply topic is partitioned via normal group assignment. Kafka assigns each partition to one member of the group; a response meant for requester A can arrive at consumer B, which does not hold the matching future.

### Dedicated Partition Pattern

This is often an effective choice when the number of requester instances is bounded and partitions can be managed. Each instance creates a reply container with a single `TopicPartitionOffset`, such as instance A using partition 0 and instance B using partition 1. If the reply topic has P partitions, at most P instances can each have a dedicated partition this way. When scaling, allocate partitions and ensure no two requesters consume the same reply partition if isolation is required.

`ReplyingKafkaTemplate` detects the partition from the single `TopicPartitionOffset` configuration. Wait for `waitForAssignment()` before letting the instance accept traffic. Do not assume the partition number always equals the pod ordinal unless deployment configuration guarantees that mapping.

### Unique Group on a Shared Reply Topic Pattern

If each requester uses a unique group ID on the same reply topic, Kafka treats each group as an independent subscriber and delivers a copy of every response to each group. The template on each instance checks the correlation ID; responses without a matching future are discarded. Set `sharedReplyTopic=true` so unmatched responses are logged at DEBUG level.

This approach keeps routing simple, but multiplies the volume of data read by the number of requester instances. With N requester instances, one response may be read N times. Avoid this when reply throughput is high or there are many instances if fan-out cost is unacceptable.

## 8. Sending Requests with Message<?> and Headers

When using Spring `Message<?>`, the requester can set the topic and key via headers. `ReplyingKafkaTemplate` adds reply metadata:

```java
Message<OrderRequest> request = MessageBuilder
        .withPayload(new OrderRequest("order-42"))
        .setHeader(KafkaHeaders.TOPIC, "orders.requests")
        .setHeader(KafkaHeaders.MESSAGE_KEY, "order-42")
        .build();

RequestReplyMessageFuture<String, String, String> future =
        replyingKafkaTemplate.sendAndReceive(request);

Message<?> reply = future.get(10, TimeUnit.SECONDS);
OrderReply result = (OrderReply) reply.getPayload();
```

In the example, `KafkaHeaders.TOPIC` is the request topic and `KafkaHeaders.MESSAGE_KEY` is the request's key. Reply topic/partition/correlation ID are added by the template according to the reply container configuration. The converter configured on the template transforms the payload object into a type supported by the Kafka serializer.

If the reply container is configured with a single topic or a single `TopicPartitionOffset`, `ReplyingKafkaTemplate` can infer reply headers automatically. If the container has another configuration, the requester must explicitly set `KafkaHeaders.REPLY_TOPIC` and possibly `KafkaHeaders.REPLY_PARTITION`. These headers must be valid and correspond to a running reply container. Normally let the template manage them when container configuration permits, avoiding misconfiguration or spoofing from input messages.

## 9. Reading and Inspecting Reply Headers on the Responder

To debug routing, the responder can accept a `ConsumerRecord` and log reply headers:

```java
@KafkaListener(topics = "orders.requests", groupId = "orders-service")
public void inspectRequest(ConsumerRecord<String, String> record) {
    Header replyTopic = record.headers().lastHeader(KafkaHeaders.REPLY_TOPIC);
    Header replyPartition = record.headers().lastHeader(KafkaHeaders.REPLY_PARTITION);
    Header correlationId = record.headers().lastHeader(KafkaHeaders.CORRELATION_ID);

    log.info("request topic={}, partition={}, offset={}, replyTopic={}, replyPartitionHeaderBytes={}, correlationIdPresent={}",
            record.topic(), record.partition(), record.offset(),
            replyTopic == null ? null : new String(replyTopic.value(), StandardCharsets.UTF_8),
            replyPartition == null ? null : replyPartition.value().length,
            correlationId != null);
}
```

The partition header is byte-encoded; when parsing the integer, use the encoding/decoding specified by your Spring Kafka version. Do not assume every header is UTF-8 text. The log example above only illustrates checking presence; never use `new String(...)` to interpret numeric headers in routing logic.

`KafkaHeaders.REPLY_PARTITION` uses a 4-byte integer in big-endian byte order. You can decode it with `ByteBuffer`:

```java
private Integer decodeReplyPartition(Header header) {
    if (header == null) {
        return null;
    }
    byte[] value = header.value();
    if (value.length != Integer.BYTES) {
        throw new IllegalArgumentException("REPLY_PARTITION must be 4 bytes");
    }
    return ByteBuffer.wrap(value).getInt();
}
```

If the responder sends replies manually:

```java
void sendReply(ConsumerRecord<String, String> request, String replyJson) {
    Header replyTopicHeader = request.headers()
            .lastHeader(KafkaHeaders.REPLY_TOPIC);
    Header replyPartitionHeader = request.headers()
            .lastHeader(KafkaHeaders.REPLY_PARTITION);
    Header correlationHeader = request.headers()
            .lastHeader(KafkaHeaders.CORRELATION_ID);

    if (replyTopicHeader == null || correlationHeader == null) {
        throw new IllegalArgumentException("Request is missing reply/correlation header");
    }

    String replyTopic = new String(
            replyTopicHeader.value(), StandardCharsets.UTF_8);
    Integer partition = decodeReplyPartition(replyPartitionHeader);

    ProducerRecord<String, String> reply = new ProducerRecord<>(
            replyTopic, partition, null, request.key(), replyJson);
    reply.headers().add(
            KafkaHeaders.CORRELATION_ID,
            correlationHeader.value().clone());

    kafkaTemplate.send(reply);
}
```

`decodeReplyPartition(...)` returns `null` if the request does not specify a partition. This only fits the shared/fan-out reply topic pattern, where every requester group reads all partitions and the correlation ID picks the right future. In the dedicated partition pattern, the header is mandatory; if missing or invalid, reject the request rather than letting the producer pick a partition automatically.

In most cases, using `@SendTo` and the listener container's reply template is safer than manually building `ProducerRecord`s, because Spring handles copying the correlation ID and reply destination. Only send manually when custom routing or multiple responses are needed.

## 10. Correlation ID Guarantees Correct Response Matching

A requester can send multiple requests before receiving responses. `ReplyingKafkaTemplate` maintains a mapping from correlation ID to future. When a response returns, the template looks up the correlation ID and completes the matching future.

```text
Request A: correlationId = a1
Request B: correlationId = b2
Request C: correlationId = c3

Response B arrives first -> completes future b2
Response A arrives next  -> completes future a1
Response C arrives last  -> completes future c3
```

Responses do not need to return in request send order. The correlation ID matches responses accurately even when the responder processes concurrently or requests have varying execution times.

The responder must echo the exact correlation ID of the request. If the response lacks the ID or uses a different ID, the template cannot match the response to the corresponding future, and the request will time out. Do not generate a new correlation ID on the responder without a custom mapping rule agreed upon by both sides.

## 11. Reply Partition and Ordering

Reply partitions can preserve response order within a partition, though request/reply usually does not require responses to return in send order. Correlation IDs allow futures to complete independently.

If the business domain requires ordered responses, design the responder to process sequentially per key or partition and avoid out-of-order async completion. Sending all responses to the same reply partition does not guarantee order if the responder processes requests concurrently and finishes out of order.

When multiple requesters share a reply partition, responses may interleave. Correlation IDs still match the right futures, while record order in the partition reflects the order in which the responder appended responses rather than necessarily the original request order.

## 12. Securing Reply Destinations

The reply topic/partition is passed in request headers. If untrusted requesters can specify arbitrary reply topics, the responder risks being abused to publish to unintended topics. In multi-tenant systems or environments with external producers, never trust reply destination headers without validation.

Appropriate safeguards:

- Use an allowlist of permitted reply topics.
- Verify the partition is within topic bounds and the requester has authorized access.
- Restrict the responder's ACLs so it can only write to necessary reply topics.
- Never let requesters arbitrarily designate sensitive system topics.
- Derive per-tenant/per-instance reply topics from authenticated identities instead of accepting arbitrary strings.
- Log requester identity, reply destination, and correlation ID per security policy.

Example checking an allowlist before sending a reply:

```java
private static final Set<String> ALLOWED_REPLY_TOPICS =
        Set.of("orders.replies", "orders.replies.internal");

void validateReplyTopic(String replyTopic) {
    if (!ALLOWED_REPLY_TOPICS.contains(replyTopic)) {
        throw new SecurityException("Reply topic is not allowed: " + replyTopic);
    }
}
```

In production, the allowlist should come from managed configuration and be paired with Kafka broker ACLs. Application-level checks do not replace Kafka broker authorization.

When using automatic `@SendTo`, the framework reads the reply destination from request headers. If an allowlist is required, validate request headers before returning a result or use a custom listener/reply flow with an explicit validation step; do not assume `@SendTo` enforces a business allowlist automatically.

## 13. Timeouts and Responses Sent to the Wrong Partition

If a response is sent to a partition that the reply container is not reading, the requester will not receive it and the future will time out. Common causes:

- `REPLY_PARTITION` does not match the partition assigned to the requester.
- The reply topic does not exist yet or has too few partitions.
- The reply container was not yet assigned when the request was sent.
- The responder ignored or misparsed the reply partition header.
- The correlation ID was not copied to the response.
- The reply consumer group delivered the response to a different instance.

A timeout only indicates the requester did not receive a valid response within the wait window. It does not prove the responder never processed the request. If the requester retries after a timeout, the business action may run twice. Use a stable request ID/idempotency key at the business layer.

## 14. Handling Multiple Responses or Asynchronous Responses

One request normally expects one response. If a responder needs to emit multiple responses for a single request, `ReplyingKafkaTemplate` with a single future is not a natural streaming-response model. You can design a dedicated response topic, group responses by correlation ID, or use Kafka Streams/reactive consumers to process the result stream.

If a listener returns `CompletableFuture`/`Mono` or processes asynchronously, verify your Spring Kafka version's API and ensure the reply still carries the proper request headers. Do not return a response before business processing finishes if the result is not ready yet.

## 15. Testing Reply Routing

Test with a real broker or Testcontainers/Embedded Kafka and multiple requester instances. Unit tests checking only header parsing helpers do not prove partition assignment or consumer group routing works.

Scenarios to test:

| Scenario | Expected Outcome |
|---|---|
| One requester, one reply partition | Request receives the right response |
| Two requesters, two reply partitions | Response A goes to A, response B goes to B |
| Two concurrent requests, out-of-order responses | Correlation IDs complete the right futures |
| Missing `REPLY_TOPIC` | Responder detects invalid request; does not send arbitrary reply |
| Missing `CORRELATION_ID` | Request rejected or handled per contract; no future mismatched |
| Non-existent `REPLY_PARTITION` | Producer send fails clearly and logs |
| Reply container unassigned | `waitForAssignment()` times out and requester does not send requests |
| Multiple requesters sharing a group improperly | Test detects responses arriving at the wrong instance |
| Reply topic outside allowlist | Responder rejects routing |
| Timeout after responder processes | Retry causes no duplicate side effects thanks to idempotency |

When testing multiple requesters, verify assignments via `KafkaMessageListenerContainer`/container properties and inspect actual responses received by each instance. Do not merely verify that a response appeared on the topic, as that does not prove the right requester received it.

## 16. Common Misconceptions

| Misconception | Reality |
|---|---|
| `REPLY_TOPIC` is the request topic | It is the topic receiving responses; the request topic is configured separately |
| `REPLY_PARTITION` is the request's partition | It is the target partition for the response |
| Correlation ID routes the response to a partition | Correlation ID pairs the response with a future; reply topic/partition specify where to write |
| Any single group ID works for all requesters | A shared group splits partitions; responses can land on an instance without the future |
| On the same reply topic, all requesters get all responses | A shared consumer group distributes records rather than broadcasting to every member |
| `@SendTo` always sends to one fixed topic | `@SendTo` without a destination can use the reply destination from request headers |
| Future timeout means business logic did not run | Responder may have processed it, while the reply was lost, misrouted, or arrived late |
| Sending the response to the right partition is enough | The correlation ID must also be preserved so the template matches the right future |
| Reply headers from requesters are always trustworthy | Allowlists and ACLs are required so responders cannot be abused to publish arbitrarily |

## Pre-Deployment Checklist for Request/Reply

- Reply listener container is started and assigned before the requester sends requests.
- Reply topic/partition is chosen per an explicit single-instance, multi-instance, or fan-out strategy.
- `REPLY_TOPIC`, `REPLY_PARTITION`, and `CORRELATION_ID` are preserved across the responder.
- Responder uses a reply template or `@SendTo` properly.
- Multiple requesters do not share a group in a way that routes responses to the wrong instance.
- Reply topic has sufficient partitions and ACLs for requesters and responders.
- Correlation ID is echoed intact; never generate new IDs arbitrarily.
- Reply destination is checked against an allowlist when requesters are not fully trusted.
- Timeouts are handled as "no response received," not as proof the request never ran.
- An idempotency key protects business operations that may be retried after a timeout.
- Integration tests verify responses reach the right requester instance, not just appear on the topic.

Reply routing in Spring Kafka relies on reply topic/partition headers, while correlation IDs pair responses with pending requests. When reply containers are properly assigned, responders preserve headers, and consumer group topology is designed for multiple instances, `ReplyingKafkaTemplate` can handle concurrent requests while returning responses to the right requester. Test partition routing, timeouts, and reply destination access controls before deploying this pattern to production.

## References

- [Spring for Apache Kafka – Sending Messages and ReplyingKafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [ReplyingKafkaTemplate API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
