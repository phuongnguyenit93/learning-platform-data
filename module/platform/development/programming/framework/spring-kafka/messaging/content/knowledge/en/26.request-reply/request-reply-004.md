# Reply Topic and Reply Container

## 1. How Does Request-Reply Work in Kafka?

Kafka primarily supports asynchronous exchange: a producer writes a record to a topic, and a consumer processes it upon receipt without needing an immediate response back to the producer. However, some business workflows need to send a request and await a result, such as looking up order status, checking credit limits, or asking a service to compute a value.

Request-reply on Kafka simulates a question-and-answer model using two record streams:

- Requests are sent to a request topic.
- The request-handling service reads the record and publishes a response to a reply topic.
- The sender listens to the reply topic, matches the response to the original request, and returns the result to the caller.

Kafka does not automatically establish a relationship between requests and responses. The application needs a correlation ID for each request, passes that ID in the request's headers, and requires the responder to preserve that ID in the response. If the correlation ID is missing or altered by the responder, the caller cannot match the response to the pending call.

Spring Kafka provides `ReplyingKafkaTemplate` to send requests and wait for responses, along with a reply container to consume responses. On the responder side, `@KafkaListener` combined with `@SendTo` can process requests and send results back to the reply topic.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as ReplyingKafkaTemplate
    participant R as Request topic
    participant S as Responder
    participant P as Reply topic
    C->>T: sendAndReceive(request)
    T->>R: Request + correlation ID + reply destination
    S->>R: Poll request
    S->>S: Execute business logic
    S->>P: Response + correlation ID
    T->>P: Reply container receives response
    T->>T: Match correlation ID
    T-->>C: RequestReplyFuture completes
~~~

Request-reply remains asynchronous communication at the Kafka layer. `ReplyingKafkaTemplate` provides an abstraction for the caller to await a result, but the request and response are still two independent Kafka records.

## 2. Distinguishing Reply Topic and Reply Container

A **reply topic** is the Kafka topic that holds responses. The responder sends responses to this topic after processing requests. The topic must be created and configured with appropriate partitions, replication, retention, and ACLs.

A **reply container** is the consumer container dedicated to reading the reply topic. `ReplyingKafkaTemplate` accepts this container in its constructor, registers an internal listener to receive responses, and matches correlation IDs against pending requests.

| Component | Role | Example |
|---|---|---|
| Request topic | Receives requests | `order-lookup.requests` |
| Reply topic | Holds replies | `order-lookup.replies` |
| Request listener | Processes requests | `@KafkaListener` on the request topic |
| Reply container | Reads responses | `ConcurrentMessageListenerContainer` |
| Correlation ID | Matches response to request | `KafkaHeaders.CORRELATION_ID` |
| Reply destination | Tells responder where to send response | `KafkaHeaders.REPLY_TOPIC` |

The reply container is not a regular business listener. It is used by `ReplyingKafkaTemplate` to complete pending futures. Do not attach additional business listeners that might consume responses off the same container.

## 3. Headers Used in Request-Reply

Spring Kafka uses headers to carry request-reply control information:

| Header | Direction | Meaning |
|---|---|---|
| `KafkaHeaders.CORRELATION_ID` | Request and reply | ID used to match the response with the request |
| `KafkaHeaders.REPLY_TOPIC` | Request | Topic to which the responder sends the response |
| `KafkaHeaders.REPLY_PARTITION` | Request | Target partition of the response if specified |
| `KafkaHeaders.RECEIVED_KEY` | Receive | Key of the received record |
| `KafkaHeaders.RECEIVED_TOPIC` | Receive | Topic containing the record |
| `KafkaHeaders.RECEIVED_PARTITION` | Receive | Partition containing the record |

`ReplyingKafkaTemplate` generates the correlation ID and adds reply destination information to the request. A Spring Kafka responder can read these headers and send the response with the matching correlation ID.

When using a fixed `@SendTo`, the target topic is determined by the annotation. When different requests need different reply topics, the responder can use `KafkaHeaders.REPLY_TOPIC` sent in the request. Do not accept reply topics from payloads or arbitrary headers without validation; the responder should only send to topics on an allowlist that the service is permitted to write to.

Kafka headers hold byte values. With Spring `Message` or converters, how headers map depends on header mapper configuration. When using Spring Kafka request-reply, let the template and listener adapter handle framework headers. If constructing a `ProducerRecord` manually, use the exact header names and byte formats required by the API.

## 4. Configuring the Reply Container

The reply container needs a consumer factory with key/value deserializers compatible with the response type. The example below uses `String` for both key and response.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;

@Configuration
public class RequestReplyConfiguration {

    @Bean
    ConcurrentMessageListenerContainer<String, String> repliesContainer(
            ConcurrentKafkaListenerContainerFactory<String, String>
                    kafkaListenerContainerFactory) {

        var container =
            kafkaListenerContainerFactory.createContainer(
                "order-lookup.replies"
            );

        container.getContainerProperties().setGroupId(
            "order-lookup-reply-client"
        );

        return container;
    }
}
~~~

`createContainer()` creates a container dedicated to the reply topic. `setGroupId()` sets the consumer group for the reply container; this group should be chosen according to the deployment topology, especially when running multiple requester instances.

In a single-instance example, the group ID can be `order-lookup-reply-client`. When deploying multiple instances, do not let all instances share one reply consumer group if each instance must receive responses for the requests waiting on that specific instance. Multi-instance setups are explained in section 11.

The reply container must be running before requests are sent to avoid responses arriving before the consumer starts listening. Spring manages container lifecycles through the bean lifecycle; the application should only accept requests once the reply container is ready. Do not disable auto-startup unless the application explicitly starts the container at the right moment.

## 5. Declaring ReplyingKafkaTemplate

Once you have a reply container, create `ReplyingKafkaTemplate` with a producer factory and that container:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.requestreply.ReplyingKafkaTemplate;

@Configuration
public class RequestReplyTemplateConfiguration {

    @Bean
    ReplyingKafkaTemplate<String, String, String> replyingKafkaTemplate(
            ProducerFactory<String, String> producerFactory,
            ConcurrentMessageListenerContainer<String, String>
                    repliesContainer) {

        var template = new ReplyingKafkaTemplate<>(
            producerFactory,
            repliesContainer
        );

        template.setDefaultReplyTimeout(Duration.ofSeconds(8));
        return template;
    }
}
~~~

The template's generic parameters take the form `ReplyingKafkaTemplate<K, V, R>`:

- `K`: key type of the request.
- `V`: value type of the request.
- `R`: value type of the response.

The example above uses `String` for all three types. The producer factory must serialize the request; the reply container must deserialize the response. If request and response use different formats, configure the producer factory and consumer factory accordingly instead of forcing all payloads into the same type.

`setDefaultReplyTimeout(Duration)` sets the default wait duration for a response. The timeout only limits how long the caller waits; it does not cancel the request already sent into Kafka and does not stop a responder that is processing it.

## 6. Sending Requests and Receiving Responses

`ReplyingKafkaTemplate.sendAndReceive()` takes a `ProducerRecord` and returns a `RequestReplyFuture`. This future provides both the request send result and the reply result.

~~~java
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.requestreply.ReplyingKafkaTemplate;
import org.springframework.kafka.requestreply.RequestReplyFuture;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupClient {

    private final ReplyingKafkaTemplate<String, String, String> template;

    public OrderLookupClient(
            ReplyingKafkaTemplate<String, String, String> template) {
        this.template = template;
    }

    public String lookup(String orderId) throws Exception {
        var request = new ProducerRecord<>(
            "order-lookup.requests",
            orderId,
            orderId
        );

        RequestReplyFuture<String, String, String> future =
            template.sendAndReceive(request);

        SendResult<String, String> sendResult =
            future.getSendFuture().get(5, TimeUnit.SECONDS);

        var replyRecord = future.get(8, TimeUnit.SECONDS);

        log.info(
            "Request confirmed topic={} partition={} offset={}",
            sendResult.getRecordMetadata().topic(),
            sendResult.getRecordMetadata().partition(),
            sendResult.getRecordMetadata().offset()
        );

        return replyRecord.value();
    }
}
~~~

There are two results to distinguish:

- `future.getSendFuture()` completes when the producer receives the send outcome per `acks` configuration.
- `future.get()` completes when the reply container receives a response whose correlation ID matches the pending request.

A successfully sent request does not mean the responder has finished processing. Likewise, a reply timeout does not mean the request was never sent. In the example, the send wait is 5 seconds and the reply wait is 8 seconds; choose limits aligned with actual SLAs.

Do not use the request offset as the response offset, because the two records reside on different topics. If you need to log response details, read metadata from `replyRecord` or the received headers.

## 7. Responder with @KafkaListener and @SendTo

On the processing side, the listener reads the request, runs business logic, and returns the response payload. `@SendTo` specifies a fixed reply topic:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class OrderLookupResponder {

    private final OrderQueryService orderQueryService;

    public OrderLookupResponder(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @KafkaListener(
        topics = "order-lookup.requests",
        groupId = "order-lookup-responder",
        containerFactory = "requestListenerContainerFactory"
    )
    @SendTo("order-lookup.replies")
    public String handle(String orderId) {
        return orderQueryService.findStatus(orderId);
    }
}
~~~

When the listener returns a payload, Spring Kafka sends that payload to the topic in `@SendTo`. The request's correlation ID is preserved in the reply so `ReplyingKafkaTemplate` matches the response accurately.

The listener factory needs a reply template to send responses. You can attach the template to `ConcurrentKafkaListenerContainerFactory`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.KafkaTemplate;

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
        requestListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTemplate<String, String> replyTemplate) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);
    factory.setReplyTemplate(replyTemplate);
    return factory;
}
~~~

`replyTemplate` is the responder-side template used to publish responses. It needs a serializer compatible with the response type and must be configured on the container factory. `ReplyingKafkaTemplate` on the requester and `replyTemplate` on the responder serve different roles: one sends requests and waits for replies, while the other sends responses.

### Designing Error Responses

If the listener throws an exception before returning a payload, `@SendTo` does not automatically create a business-contract error response. The caller usually keeps waiting until the reply timeout, while the listener container handles the exception via its error handler.

If the caller needs to receive both business successes and business failures, define a response envelope with explicit status fields, such as `status`, `result`, and `errorCode`. The responder can catch expected business errors and return a failure envelope; infrastructure or programming errors should still go through retry/error handlers per policy. Do not send stack traces, secrets, or raw internal exception messages to the caller.

## 8. Using the Reply Topic Specified in the Request

A system may have multiple requesters or multiple request types. Instead of fixing the reply topic in `@SendTo`, the responder can send the reply to the topic in the `KafkaHeaders.REPLY_TOPIC` header.

Example listener returning a response without specifying a topic in the annotation:

~~~java
@KafkaListener(
    topics = "order-lookup.requests",
    groupId = "order-lookup-responder",
    containerFactory = "requestListenerContainerFactory"
)
@SendTo
public OrderStatusReply handle(OrderLookupRequest request) {
    return orderQueryService.lookup(request.orderId());
}
~~~

For requests created by `ReplyingKafkaTemplate`, the reply topic header is sent alongside the request. The listener adapter uses the reply template and this header information to send the response to the right topic.

If the application wants a single fixed topic for all requesters, `@SendTo("order-lookup.replies")` is easier to read and configure. If using dynamic reply topics, restrict target topics via an allowlist, grant least-privilege ACLs, and never trust values sent arbitrarily by any client.

When the annotation explicitly names a topic, that is the declared destination for the listener. Choose one clear strategy per listener, avoiding configuring a fixed topic while assuming a dynamic reply topic header will always take precedence.

## 9. Correlation ID and Response Matching

`ReplyingKafkaTemplate` tracks pending requests by correlation ID. When sending a request, the template adds the correlation header; the response must carry back that same value.

If constructing a response manually using `KafkaTemplate` instead of relying on the listener adapter's reply mechanism, copy the correlation header from the request to the response:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.header.Header;
import org.springframework.kafka.support.KafkaHeaders;

public ProducerRecord<String, OrderStatusReply> createReply(
        ConsumerRecord<String, OrderLookupRequest> request,
        OrderStatusReply reply) {

    var response = new ProducerRecord<>(
        "order-lookup.replies",
        request.key(),
        reply
    );

    Header correlationId =
        request.headers().lastHeader(KafkaHeaders.CORRELATION_ID);

    if (correlationId != null) {
        response.headers().add(
            KafkaHeaders.CORRELATION_ID,
            correlationId.value()
        );
    }

    return response;
}
~~~

If the correlation ID is not returned or is altered, the template cannot complete the matching future. The request will time out even though the responder may have finished processing and sent a response.

Correlation ID is not an event ID or business ID. A single order ID may appear in many different requests; each request needs its own correlation ID to distinguish concurrent calls.

## 10. Timeouts, Errors, and Late Responses

Request-reply must have a bounded timeout. Without a timeout, the caller could wait indefinitely when the responder stops, a reply is lost, or the correlation header is wrong.

| Scenario | Outcome on Requester | Action |
|---|---|---|
| Request fails to send | Send future fails | Handle producer error and decide whether to retry sending |
| Request sent successfully but responder does not process | Reply future times out | Check consumer lag, responder, and request topic |
| Responder processes but fails to send reply | Reply future times out | Check reply template, ACLs, and exceptions |
| Reply sent with wrong correlation ID | Matching future never completes | Check correlation headers on both sides |
| Reply arrives after timeout | Caller already stopped waiting | Template no longer has a pending request to match; response is unused by the timed-out call |
| Caller times out and sends a new request | Two requests might execute the same business operation | Use a stable request ID/idempotency key for side effects |

A requester timeout does not cancel the record in Kafka. The responder may still process it and emit a reply afterward. If the operation has side effects, retrying the request could execute the same action multiple times; an idempotency key or deduplication on the responder is required.

Pending requests are tracked by `ReplyingKafkaTemplate` in the instance's memory. If the requester restarts, the mapping between correlation IDs and pending futures is not recovered solely from the reply topic. Old responses may still exist in Kafka, but the old futures no longer exist to complete; if the business workflow requires recovery after restart, persist request IDs and pending states in durable storage and design a separate reconciliation mechanism.

`setDefaultReplyTimeout()` sets the default wait time for the template. If you need per-request timeouts, check the `sendAndReceive(record, Duration)` overload in your Spring Kafka version; API overloads may vary by version. Regardless of the approach, a bounded timeout on the caller is still required.

## 11. Multiple Requester Instances and Shared Reply Topics

When running multiple instances of the same requester service, how the reply topic is used directly affects whether responses reach the instance that is waiting.

### Dedicated Reply Topic per Instance

For example:

- Instance A listens to `order-lookup.replies.A`.
- Instance B listens to `order-lookup.replies.B`.

Each requester consumes only its own replies. This approach is easy to understand and avoids another instance taking the response, but requires managing topics, ACLs, and partitions per instance or per deployment group with a clear lifecycle. Never create a new topic per individual request.

### Using a Shared Reply Topic

Multiple instances can share a single reply topic if each instance has its own reply consumer group so every instance receives a copy of all replies. Each `ReplyingKafkaTemplate` only completes futures whose correlation ID it is tracking; replies meant for other instances are ignored.

Enable shared reply topic mode on the template:

~~~java
template.setSharedReplyTopic(true);
~~~

If multiple instances share the same consumer group on the reply topic, Kafka distributes each record to one instance in the group. A response may land on an instance that does not own the pending request; the right requester never receives its response and eventually times out.

With a shared topic, evaluate the multiplied traffic per instance: each instance receives all replies, even though only a fraction belongs to it. If instance counts or throughput are high, dedicated reply topics or a partition routing strategy may fit better.

## 12. Reply Partition and Response Routing

`KafkaHeaders.REPLY_PARTITION` lets the requester specify which partition the responder must use when sending the response. This is useful when the reply topic has multiple partitions and the requester wants to direct responses to the partition its reply container reads.

If specifying a reply partition:

- The reply topic must have the corresponding partition.
- The requester must have a consumer assignment able to read that partition.
- The responder must preserve the header and use a reply template that supports the destination partition.
- Partition routing must be tested when scaling partitions up/down or changing concurrency.

Do not specify a partition arbitrarily without defining the reply container's topology. If there is no specific routing requirement, letting the Kafka partitioner choose the partition or using a dedicated reply topic per requester is usually simpler.

## 13. Security and Operations for Reply Topics

The reply topic is part of the internal API between requester and responder. Permissions and lifecycle must be managed like any other application topic:

- The requester has write permission on the request topic and read permission on the reply topic.
- The responder has read permission on the request topic and write permission on the reply topic.
- The reply topic should only be readable by authorized requesters.
- Do not allow clients to freely specify arbitrary topics as reply destinations.
- Use TLS, ACLs, and client authentication per cluster standards.
- Choose appropriate retention so late responses do not linger longer than necessary.
- Monitor consumer lag, request timeouts, unmatched correlation IDs, and response publish failures.

Do not put secrets or sensitive data into correlation IDs. Correlation IDs frequently appear in logs and traces; use random values containing no personal information.

The reply topic needs sufficient partitions and replication factor for the load. If the reply topic uses partition routing, partition configuration must match `KafkaHeaders.REPLY_PARTITION` values. If using a shared topic, evaluate the cost of each requester instance reading all replies.

## 14. Testing Request-Reply

Test the entire path: request, responder, reply container, and correlation mapping. Mocking `ReplyingKafkaTemplate` alone does not prove that the broker, headers, and consumer container work together properly.

Cases worth testing:

- Request is sent to the right topic, key, and carries a correlation ID.
- Responder receives the request, executes business logic, and emits a response.
- Reply topic and correlation header are preserved.
- Futures complete with the right response under concurrent requests.
- Multiple requests answered out of order still match correctly by correlation ID.
- Reply timeout triggers when the responder does not respond.
- A response arriving after timeout does not mistakenly complete another request.
- Missing or wrong correlation IDs do not complete other futures.
- Shared reply topic works when each instance has its own group.
- Reply partitions route properly when used.
- Serializer, deserializer, ACL, and response publish failures are clearly observable.

Illustrative integration test demonstrating waiting for a response:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;

class OrderLookupRequestReplyTest {

    @Test
    void receivesCorrelatedReply() throws Exception {
        var request = new ProducerRecord<>(
            "order-lookup.requests",
            "ORD-1",
            "ORD-1"
        );

        var future = replyingKafkaTemplate.sendAndReceive(request);

        var reply = future.get(10, TimeUnit.SECONDS);

        assertThat(reply.value()).isEqualTo("SHIPPED");
    }
}
~~~

Tests must initialize the broker, reply container, responder listener, and template before sending requests. Use dedicated topics and groups for tests along with bounded timeouts. When testing multiple concurrent requests, verify each future receives its expected response by correlation ID rather than merely asserting total response count.

## 15. When Should You Use Request-Reply on Kafka?

Request-reply is a good fit when:

- Two services communicate over Kafka and the caller genuinely needs a returned result.
- The work completes within a bounded wait window and a reasonable timeout can be set.
- Both requester and responder can manage correlation IDs, reply topics, and response lifecycles.
- The system already runs Kafka and wants to reuse the same security, routing, and observability infrastructure.

Do not use request-reply for every interaction:

- If the caller does not need an immediate result, emitting events and processing asynchronously is usually simpler.
- If the caller needs ultra-low latency or direct interactive communication, HTTP/gRPC may fit better.
- If the work lasts several minutes, use commands/events and progress state instead of holding a request future open.
- If responses are large or involve file transfers, send metadata/references over Kafka rather than putting large payloads in replies.
- If multiple requesters have different lifecycles, design reply topics and consumer groups before implementation.

Request-reply on Kafka does not turn Kafka into synchronous RPC with exactly-once guarantees. It is an asynchronous pattern with correlation and timeouts. Responder side effects still require idempotency; responses can arrive late, requests can be reprocessed, and callers can time out before work finishes.

## 16. Implementation Checklist

- [ ] Create request topic and reply topic with appropriate partitions, replication, and retention.
- [ ] Configure `ReplyingKafkaTemplate` with a properly typed producer factory and reply container.
- [ ] Use a consumer factory/deserializer compatible with the response.
- [ ] Assign a distinct group ID to the reply container matching the requester topology.
- [ ] Ensure the reply container is running before sending requests.
- [ ] Configure bounded timeouts per request or as a default timeout.
- [ ] Use `@KafkaListener` and `@SendTo` or a reply template to publish responses.
- [ ] Preserve the correlation ID from request to response.
- [ ] Configure shared reply topics properly when multiple requester instances share one.
- [ ] Never share the same reply consumer group across multiple instances when each needs its own responses.
- [ ] Allow reply destinations only from an allowlist and grant least-privilege ACLs.
- [ ] Design idempotency on the responder when requesters retry after timeouts.
- [ ] Monitor request timeouts, reply lag, correlation mismatches, and response publish failures.
- [ ] Test request-reply against a real broker, including concurrent requests and late responses.

`ReplyingKafkaTemplate` combined with a reply container enables Spring Kafka to implement request-reply using a request topic, reply topic, and correlation ID. The responder can use `@KafkaListener` with `@SendTo` to return results. To run reliably, configure consumer groups and reply routing to match the topology, set bounded timeouts, preserve correlation IDs, and handle retried requests idempotently.
