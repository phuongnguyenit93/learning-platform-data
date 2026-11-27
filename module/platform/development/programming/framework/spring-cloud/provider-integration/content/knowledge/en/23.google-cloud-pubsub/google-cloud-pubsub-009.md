# Choosing Spring Integration vs. Spring Cloud Stream based on requirements

## Lesson Objectives

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module practices integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries. When using Google Cloud Pub/Sub, a Spring application can integrate at several abstraction levels: calling `PubSubTemplate` directly, wiring Spring Integration `MessageChannel`s via channel adapters, or using the Spring Cloud Stream binder to write producers/consumers in a functional model.

This lesson helps you pick the right integration approach based on message-flow complexity and required control:

- **Spring Integration:** builds processing flows with channels, endpoints, routers, transformers, and error channels; controls ACK/NACK per message.
- **Spring Cloud Stream:** declares `Supplier`, `Function`, and `Consumer` beans bound to destinations; suits event-driven microservices aiming to minimize broker-specific configuration.
- **Pub/Sub template/client:** used when you need specialized APIs, direct topic/subscription operations, or control over behavior not exposed by higher abstractions.

After this lesson, you will be able to:

1. Add the right dependencies and BOM for Spring Integration or the Stream binder.
2. Create inbound/outbound Pub/Sub channel adapters.
3. Distinguish streaming pull from a synchronous pollable message source.
4. Choose `AckMode.AUTO`, `AUTO_ACK`, or `MANUAL` and handle error channels properly.
5. Map/filter headers, ordering keys, and publish callbacks.
6. Write functional `Consumer`/`Function` beans and configure Stream bindings, destinations, and groups.
7. Manage topics/subscriptions automatically or provision them via infrastructure.
8. Understand the binder's partitioning and exactly-once limitations.
9. Test and operate message flows with retries, DLQs, metrics, and graceful shutdown.

## 1. Choosing the right abstraction

### 1.1. Three main integration paths

Spring Framework on Google Cloud offers three ways to use Pub/Sub in Spring applications:

| Integration path | Core components | Strengths | When to choose |
| --- | --- | --- | --- |
| Pub/Sub template/client | `PubSubTemplate`, Java Pub/Sub client | Direct control over publish, pull, ack/nack, and resource management | Need specialized APIs, fine-grained ACK logic, provisioning, or low-level control |
| Spring Integration | `PubSubInboundChannelAdapter`, `PubSubMessageSource`, `PubSubMessageHandler` | Connects Pub/Sub to `MessageChannel` and Enterprise Integration Patterns | Flows with routers, filters, transformers, aggregators, error channels, or multi-step integration |
| Spring Cloud Stream binder | `spring-cloud-gcp-pubsub-stream-binder` | Functional programming model, bindings, and consumer groups | Producer/consumer microservices focusing on event contracts and destinations |

These modules can coexist in one system, but pick a single abstraction as the main receive path per subscription. Never create two independent consumers reading the same subscription merely because the app includes both Integration adapters and the Stream binder.

### 1.2. Distinguishing channel adapters and the binder

Spring Integration channel adapters bridge an application `MessageChannel` with a Pub/Sub topic or subscription. The application declares channels and adapters, then wires endpoints such as `@ServiceActivator`, `@Transformer`, `@Filter`, or routers.

The Spring Cloud Stream binder creates bindings between application functions and destinations. For instance, a `Consumer<OrderCreated>` bean binds to a subscription via an input binding; a `Function<OrderCreated, OrderAccepted>` bean has both input and output bindings.

The Pub/Sub binder is built on top of the Spring Integration channel adapters themselves. Therefore, it inherits many adapter semantics such as ACK modes, while exposing higher-level configuration through binding properties.

### 1.3. Key differences to know before choosing

| Requirement | Spring Integration | Spring Cloud Stream binder |
| --- | --- | --- |
| Multi-step processing and routing | Strong; declarative channels/endpoints | Can compose functions, though less flexible for complex flows |
| Original message and ACK control | Exposes `GcpPubSubHeaders.ORIGINAL_MESSAGE` and `AckMode` | Supports binder ACK modes; check headers/APIs for your binder version |
| Producer publish callbacks | `PubSubMessageHandler` provides success/failure callbacks | Producer is async by default; property enables sync send |
| Consumer groups | Determined by Pub/Sub subscription | Declared via `spring.cloud.stream.bindings.*.group` |
| Auto-create topics/subscriptions | Can provision separately with `PubSubAdmin`/IaC | Binder supports auto-creating resources, enabled by default |
| Stream partitioning | Not a binder partitioning abstraction | Pub/Sub binder does not currently support Spring Cloud Stream partitioning |
| Exactly-once ACK responses | Streaming adapter exposes only basic ack/nack handle | Spring Cloud GCP does not expose `AckReplyConsumerWithResponse` needed for exactly-once ACK responses |

Do not choose the Stream binder solely because you want functional beans. If exactly-once delivery requires reading `AckResponse` from the Java client, use the Java Pub/Sub API directly; Google documentation notes Spring Cloud GCP does not expose `AckReplyConsumerWithResponse`.

## 2. Dependencies and baseline configuration

### 2.1. Spring Integration channel adapters

With Maven, use the Spring Framework on Google Cloud BOM to align starter and Pub/Sub library versions:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
</dependencies>
```

Replace `${spring-cloud-gcp.version}` with a BOM version compatible with your application's Spring Boot and Spring Framework versions. Do not pin `spring-integration-core` or `google-cloud-pubsub` independently of the BOM without an explicit compatibility reason.

Gradle:

```kotlin
dependencies {
    implementation(platform("com.google.cloud:spring-cloud-gcp-dependencies:$springCloudGcpVersion"))
    implementation("com.google.cloud:spring-cloud-gcp-starter-pubsub")
    implementation("org.springframework.integration:spring-integration-core")
}
```

### 2.2. Spring Cloud Stream Pub/Sub binder

If the application uses functional bindings, add the binder:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-pubsub-stream-binder</artifactId>
</dependency>
```

Gradle:

```kotlin
dependencies {
    implementation("com.google.cloud:spring-cloud-gcp-pubsub-stream-binder")
}
```

The binder uses Spring Integration adapters underneath. Use the Spring Framework on Google Cloud BOM to manage binder and starter versions, while ensuring Spring Cloud Stream matches the chosen BOM version.

### 2.3. Project and credentials configuration

Example baseline configuration:

```yaml
spring:
  cloud:
    gcp:
      project-id: acme-commerce-dev
```

Locally, use Application Default Credentials via `gcloud auth application-default login`. On Google Cloud, prefer workload-attached service accounts or Workload Identity. The runtime principal needs properly scoped Pub/Sub permissions: topic publish, subscription consume, or resource management depending on role.

Never put service account JSON keys into source control or `application.yml`. If the application does not create topics/subscriptions itself, do not grant Pub/Sub admin permissions to the runtime just to run the adapter.

## 3. Spring Integration inbound: Streaming Pull

### 3.1. `PubSubInboundChannelAdapter`

`PubSubInboundChannelAdapter` uses Streaming Pull to receive messages continuously from a subscription, converts each Pub/Sub message into a Spring `Message`, and sends it to the configured channel. By default the payload is `byte[]`; set `payloadType` so `PubSubTemplate`'s converter converts it to a DTO or `String`.

Example declaring a channel and inbound adapter:

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import com.google.cloud.spring.pubsub.integration.AckMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class PubSubInboundConfiguration {

    @Bean
    public MessageChannel ordersInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public PubSubInboundChannelAdapter ordersInboundAdapter(
            MessageChannel ordersInputChannel,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
        adapter.setOutputChannel(ordersInputChannel);
        adapter.setPayloadType(String.class);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
```

`DirectChannel` dispatches messages to a single subscriber handler point-to-point. Use `PublishSubscribeChannel` when intentionally broadcasting one message to multiple handlers within the same application; carefully design ACK semantics if one handler succeeds while another fails.

### 3.2. Processing messages and manual ACKs

In `MANUAL` mode, the adapter does not automatically ACK/NACK. It attaches `BasicAcknowledgeablePubsubMessage` in the `GcpPubSubHeaders.ORIGINAL_MESSAGE` header:

```java
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler {
    private final OrderService orderService;

    public OrderMessageHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "ordersInputChannel")
    public void handle(Message<String> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            orderService.processAndCommit(message.getPayload());
            CompletableFuture<Void> ackResult = original.ack();
            ackResult.whenComplete((unused, error) -> {
                if (error != null) {
                    // Record ACK failure; message may be redelivered.
                }
            });
        } catch (Exception processingError) {
            original.nack();
        }
    }
}
```

`processAndCommit()` must finish the database transaction before calling `ack()`. `ack()`/`nack()` return futures; if the ACK request fails or its outcome is uncertain, the message may be redelivered. Consumers must be idempotent on the business event ID.

### 3.3. Three acknowledgment modes

The inbound adapter supports three modes:

| Mode | Success flow | Error flow without error handler | Error handler finishes normally |
| --- | --- | --- | --- |
| `AUTO` (default) | ACK | NACK, immediate redelivery | ACK |
| `AUTO_ACK` | ACK | Neither ACK nor NACK; waits for deadline/lease | ACK |
| `MANUAL` | No automatic action | No automatic action | No automatic action |

Common pitfall: under `AUTO` and `AUTO_ACK`, the adapter treats the flow as successful if an error handler catches the exception and returns normally. Thus, a failing message can be ACKed after an error handler merely logs it. To preserve default error behavior (NACK in `AUTO`, no-op in `AUTO_ACK`), the error handler must rethrow the exception to the adapter.

Pick the mode matching your needs:

- `AUTO`: simple when exceptions propagate cleanly and you want ACK after the full flow succeeds.
- `AUTO_ACK`: useful when you intentionally want failing messages left unacked to wait out deadlines/leases rather than NACKing immediately.
- `MANUAL`: used when ACK/NACK decisions follow transactions, quarantine persistence, or durable handoffs.

### 3.4. Error channel

You can attach an error channel to the adapter:

```java
@Bean
public PubSubInboundChannelAdapter ordersInboundAdapter(
        MessageChannel ordersInputChannel,
        PubSubTemplate pubSubTemplate) {
    PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
    adapter.setOutputChannel(ordersInputChannel);
    adapter.setAckMode(AckMode.AUTO);
    adapter.setErrorChannelName("ordersErrors");
    return adapter;
}
```

An error handler can retrieve the original message from the failed message:

```java
@ServiceActivator(inputChannel = "ordersErrors")
public void handleError(Message<MessagingException> errorMessage) {
    Message<?> failedMessage = errorMessage.getPayload().getFailedMessage();
    BasicAcknowledgeablePubsubMessage original =
            failedMessage.getHeaders().get(
                    GcpPubSubHeaders.ORIGINAL_MESSAGE,
                    BasicAcknowledgeablePubsubMessage.class);

    // ACK only if durably saved to quarantine.
    // To let AUTO mode NACK on exception, rethrow the error to the adapter.
    original.nack();
}
```

This example explicitly calls NACK. If the error handler completes normally, the adapter no longer sees the flow as failed for default error handling. Avoid mixing manual ACK/NACK with auto-mode assumptions on the same message.

## 4. Spring Integration outbound: Publishing to a topic

### 4.1. `PubSubMessageHandler`

The outbound channel adapter uses `PubSubMessageHandler`. It consumes a Spring `Message` from a channel, converts the payload to bytes via `PubSubTemplate`'s `PubSubMessageConverter`, and publishes to a topic:

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class PubSubOutboundConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "ordersOutputChannel")
    public MessageHandler ordersPublisher(PubSubTemplate pubSubTemplate) {
        PubSubMessageHandler handler =
                new PubSubMessageHandler(pubSubTemplate, "orders-events");

        handler.setSuccessCallback((messageId, originalMessage) -> {
            // Record publish success metric and messageId.
        });
        handler.setFailureCallback((cause, originalMessage) -> {
            // Record publish failure metric and correlation ID.
        });
        return handler;
    }
}
```

`PubSubMessageHandler` publishes asynchronously by default. The success callback receives the Pub/Sub-assigned message ID; the failure callback receives the cause and original message. Never treat sending to the internal channel as proof the broker received the message.

### 4.2. Sending messages via a channel or Messaging Gateway

A `MessageChannel` can be injected into a service to send messages:

```java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final MessageChannel ordersOutputChannel;

    public OrderEventPublisher(MessageChannel ordersOutputChannel) {
        this.ordersOutputChannel = ordersOutputChannel;
    }

    public void publish(OrderCreated event) {
        ordersOutputChannel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventType", "OrderCreated")
                        .setHeader("eventId", event.eventId())
                        .build()
        );
    }
}
```

Here `send()` delivers to the internal Spring channel. The actual publish runs inside `PubSubMessageHandler`; monitor success/failure callbacks to observe broker results. If business logic requires durable publish retries across process crashes, use a transactional outbox rather than holding messages solely in memory.

### 4.3. Selecting topics via headers or SpEL

By default, the handler publishes to the topic passed to its constructor. You can override it with `GcpPubSubHeaders.TOPIC`:

```java
Message<?> message = MessageBuilder.withPayload(event)
        .setHeader(GcpPubSubHeaders.TOPIC, "priority-orders")
        .build();
ordersOutputChannel.send(message);
```

Or configure a topic expression:

```java
PubSubMessageHandler handler =
        new PubSubMessageHandler(pubSubTemplate, "default-orders");
handler.setTopicExpressionString("headers['targetTopic']");
```

When selecting destinations from headers, validate the value before sending. Never let untrusted messages freely dictate target topics, which could cause publishing to unintended resources.

### 4.4. Synchronous publishing when propagating errors to callers

The outbound handler publishes asynchronously by default. If you need sends to await completion or configure a timeout, use the `PubSubMessageHandler` API supported by your library version. Never block main HTTP threads without a timeout; for high-reliability business flows, an outbox is usually preferable to holding request threads waiting on Pub/Sub.

## 5. Pollable source: Synchronous Pull

### 5.1. When to use `PubSubMessageSource`?

`PubSubInboundChannelAdapter` uses Streaming Pull and typically delivers strong throughput for continuous workloads. However, clients can cache many messages; when a large batch of small, slow-to-process messages arrives, one subscriber may hoard most messages in its cache while other subscribers sit idle.

`PubSubMessageSource` uses synchronous pull paired with a Spring Integration poller. It can distribute work more evenly under cache-imbalance conditions. It is not faster for every workload: synchronous pull fits controlled polling cadences or balanced batch distribution, whereas Streaming Pull fits continuous, high-throughput streams.

### 5.2. Configuring a pollable source

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubMessageSource;
import com.google.cloud.spring.pubsub.support.AcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;

@Configuration
public class PubSubPollingConfiguration {

    @Bean
    @InboundChannelAdapter(
            channel = "ordersInputChannel",
            poller = @Poller(fixedDelay = "250"))
    public MessageSource<Object> ordersMessageSource(PubSubTemplate pubSubTemplate) {
        PubSubMessageSource source =
                new PubSubMessageSource(pubSubTemplate, "orders-sub");
        source.setAckMode(AckMode.MANUAL);
        source.setPayloadType(String.class);
        source.setBlockOnPull(true);
        source.setMaxFetchSize(50);
        return source;
    }
}
```

Key points:

- By default, synchronous pull returns immediately if no messages are waiting; `setBlockOnPull(true)` waits for at least one message.
- By default, each pull fetches one message; `setMaxFetchSize()` sets the maximum messages per poll.
- `setAckMode(MANUAL)` delegates ACK/NACK control to the downstream handler.
- Tune poller delay and fetch size to target latency, throughput, and processing capacity.

### 5.3. ACKing messages from a pollable source

With synchronous pull, the `GcpPubSubHeaders.ORIGINAL_MESSAGE` header holds an `AcknowledgeablePubsubMessage`, exposing the ack ID and subscription name:

```java
@ServiceActivator(inputChannel = "ordersInputChannel")
public void handlePolledOrder(
        Message<String> message,
        @Header(GcpPubSubHeaders.ORIGINAL_MESSAGE)
        AcknowledgeablePubsubMessage original) {

    try {
        orderService.processAndCommit(message.getPayload());
        original.ack();
    } catch (Exception error) {
        original.nack();
    }
}
```

The Streaming Pull adapter supplies `BasicAcknowledgeablePubsubMessage`, which supports ACK/NACK without exposing the ack ID for deferred handling. The synchronous pull source supplies `AcknowledgeablePubsubMessage`, which includes the ack ID. Never store an ack ID for use after the message deadline has expired or after redelivery; an old delivery's ack ID may no longer be valid.

## 6. Header mapping, converters, and ordering keys

### 6.1. Headers from Pub/Sub to Spring Messages

By default, inbound adapters map Pub/Sub message attributes to Spring headers. Payloads are converted by `PubSubTemplate`'s `PubSubMessageConverter`; the adapter payload defaults to `byte[]`, changeable to `String` or a DTO via `setPayloadType()`.

System headers such as `GcpPubSubHeaders.ORIGINAL_MESSAGE` are attached by the adapter so handlers can ACK/NACK. Do not strip this header when flows use manual acknowledgment.

### 6.2. Headers from Spring Messages to Pub/Sub

Outbound adapters map Spring headers to string-valued Pub/Sub attributes, excluding internal headers such as `id`, `timestamp`, acknowledgment headers, and ordering keys. Because Pub/Sub attributes are string values, serialize complex types explicitly instead of assuming header objects retain their Java types.

### 6.3. Ordering keys

`GcpPubSubHeaders.ORDERING_KEY` maps automatically to `PubsubMessage.orderingKey` and is omitted from ordinary attributes:

```java
Message<OrderCreated> message = MessageBuilder.withPayload(event)
        .setHeader(GcpPubSubHeaders.ORDERING_KEY, event.orderId())
        .setHeader("eventId", event.eventId())
        .build();
ordersOutputChannel.send(message);
```

When publishing messages with ordering keys, enable ordering in publisher configuration:

```yaml
spring:
  cloud:
    gcp:
      pubsub:
        publisher:
          enable-message-ordering: true
```

Ordering keys should be stable with healthy cardinality. If multiple messages sharing a key must execute sequentially, downstream handlers must also preserve order; setting the header alone does not serialize database side effects.

### 6.4. Filtering headers with `PubSubHeaderMapper`

You can customize which headers are mapped:

```java
PubSubHeaderMapper mapper = new PubSubHeaderMapper();
mapper.setOutboundHeaderPatterns("!authorization", "!internal_*", "*");
ordersPublisher.setHeaderMapper(mapper);
```

Patterns are evaluated in order of declaration; earlier patterns take precedence. This example excludes `authorization` and `internal_*` headers before allowing all remaining ones. Never publish access tokens, session IDs, or secrets in Pub/Sub attributes.

### 6.5. Do not confuse header mapping with payload conversion

Header mappers handle metadata; message converters handle payload bytes and target types. If a DTO fails deserialization, check `PubSubMessageConverter`, `payloadType`, content type, and schema version. If headers disappear, check `PubSubHeaderMapper` or the Stream binder's `allowedHeaders`.

## 7. Spring Cloud Stream Pub/Sub binder

### 7.1. Functional programming model

Since Spring Cloud Stream 3, the functional model supports `Supplier`, `Function`, and `Consumer` beans:

- `Supplier<T>` emits messages to an output binding.
- `Consumer<T>` receives messages from an input binding.
- `Function<T, R>` consumes input and emits results to an output binding.

Consumer example:

```java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Consumer<OrderCreated> processOrder(OrderService orderService) {
        return orderService::processIdempotently;
    }
}
```

For a `Consumer<OrderCreated>` bean named `processOrder`, the default input binding name is `processOrder-in-0`.

Processor example:

```java
@Bean
public Function<OrderCreated, OrderAccepted> acceptOrder(OrderService orderService) {
    return orderService::accept;
}
```

This `Function` has input binding `acceptOrder-in-0` and output binding `acceptOrder-out-0`.

### 7.2. Configuring destinations and consumer groups

Example `application.yml` for a consumer:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-worker
          content-type: application/json
      gcp:
        pubsub:
          bindings:
            processOrder-in-0:
              consumer:
                auto-create-resources: false
                ack-mode: AUTO
                subscription-name: orders-sub
```

Meaning:

- `destination: orders` is the Pub/Sub topic.
- `group: order-worker` creates a durable consumer group; the binder maps it to a subscription tied to the topic and group.
- `content-type: application/json` configures Stream content-type conversion for the DTO.
- `auto-create-resources: false` expects the topic/subscription to be pre-provisioned by IaC or admin tooling.
- `ack-mode: AUTO` ACKs when the flow succeeds and NACKs when errors propagate cleanly back to the adapter.

Binding names follow `<functionName>-in-<index>` or `<functionName>-out-<index>`. When a function has multiple inputs or outputs, indices distinguish each port.

### 7.3. Producer and Function outputs

For a `Function` with both input and output:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          group: order-worker
          content-type: application/json
        acceptOrder-out-0:
          destination: accepted-orders
          content-type: application/json
      gcp:
        pubsub:
          bindings:
            acceptOrder-in-0:
              consumer:
                auto-create-resources: false
                ack-mode: AUTO
                subscription-name: orders-sub
            acceptOrder-out-0:
              producer:
                auto-create-resources: false
                sync: false
```

The binder's producer publishes asynchronously by default. Set `sync: true` when publish errors must propagate back to the caller per binder semantics; still configure proper timeouts and retries.

### 7.4. Consumer groups determine subscriptions

In Pub/Sub, each subscription receives an independent copy of messages. A Spring Cloud Stream group maps to a subscription:

| Configuration | Behavior |
| --- | --- |
| Same `destination`, same `group` across multiple instances | Instances share one subscription; Pub/Sub distributes messages across them |
| Same `destination`, different groups | Each group gets its own subscription and receives a full copy of messages |
| No `group` declared | Binder creates an anonymous subscription, cleaned up on binder shutdown |

For production workloads, always declare a stable group name so subscriptions survive restarts and scaling. Never use anonymous subscriptions if backlog must persist while all instances are stopped.

### 7.5. Auto-creating resources

The Pub/Sub binder can auto-create missing topics and subscriptions; `auto-create-resources` is enabled by default. When enabled, `destination` becomes the topic name. For consumers with a group, the subscription is typically named `<topic>.<group>` unless a custom subscription name is set.

In production, prefer provisioning topics and subscriptions via Terraform or infrastructure pipelines, then set `auto-create-resources: false`. This lets teams review IAM, retention, retry policies, DLQs, ordering, and exactly-once settings before deploying apps.

If letting the binder auto-create resources, ensure the runtime principal holds creation permissions. Never grant broad administrative permissions just for app startup; pre-create resources in deployment pipelines instead.

### 7.6. Binder ACK modes

The binder provides the same three modes as the inbound channel adapter:

| Mode | Behavior |
| --- | --- |
| `AUTO` (default) | ACKs on success; NACKs when an exception propagates |
| `AUTO_ACK` | ACKs on success; on error does not immediately NACK, letting deadline/redelivery handle it |
| `MANUAL` | Application owns ACK/NACK calls |

In `MANUAL` mode, the application must retain message headers and extract the original message handle per the binder version's API. If a function accepts only a bare DTO (`Consumer<OrderCreated>`), business code has no `Message<?>` to read headers. When manual ACKs are needed, accept `Message<OrderCreated>` and verify `GcpPubSubHeaders.ORIGINAL_MESSAGE` is forwarded to the consumer in your binder version. If specific ACK responses or exactly-once delivery tracking is required, the binder does not expose `AckReplyConsumerWithResponse`; use the Java Pub/Sub client directly.

### 7.7. Header allowlists

The binder provides `allowedHeaders` for producers and consumers. Only listed headers pass through the binder:

```yaml
spring:
  cloud:
    gcp:
      pubsub:
        bindings:
          processOrder-in-0:
            consumer:
              allowed-headers: eventId,eventType,schemaVersion
          acceptOrder-out-0:
            producer:
              allowed-headers: eventId,eventType,schemaVersion
```

Header allowlists keep contracts explicit and prevent leaking internal metadata. Never put authorization tokens, cookies, or sensitive data into message headers.

### 7.8. Partitioning limitations

The Spring Cloud Stream Pub/Sub binder does not currently support Spring Cloud Stream partitioning. Pub/Sub offers ordering keys at the broker level, but ordering keys are not synonymous with Stream binder partitioning; they have distinct semantics and configurations.

If you need key-based partitioned processing at the Stream level, evaluate a binder that supports partitioning or build custom routing using ordering keys and consumer logic on Pub/Sub. Never enable `partitioned: true` assuming the Pub/Sub binder creates Kafka-style partition routing.

## 8. Retries, error handling, and dead-letter flows

### 8.1. Distinguishing framework retries from Pub/Sub retries

Two independent retry layers exist:

| Layer | Mechanism | Goal |
| --- | --- | --- |
| Spring Integration/Stream | Retry handler, error channel, `maxAttempts`, consumer backoff | Retry in-process before declaring the handler failed |
| Pub/Sub subscription | NACK or ack deadline expiration, retry policy, dead-letter topic | Redeliver from the broker when the subscriber does not ACK |

For instance, Spring Cloud Stream can re-invoke a function several times within a single delivery. If it still fails and the exception propagates to the inbound adapter in `AUTO` mode, the adapter NACKs the message, and Pub/Sub continues redelivering per the subscription's retry policy. Thus, a single message can be processed multiple times both within one delivery and across multiple deliveries.

Never configure unbounded retries at both layers. Keep in-process retries tightly bounded, then let Pub/Sub retry/backoff and DLQs isolate persistent failures.

### 8.2. Spring Integration error channels

Error channels support logging, error classification, or quarantining. Understand their ACK semantics carefully:

- With `AckMode.AUTO`, exceptions reaching the adapter trigger NACK; if an error handler catches the error and returns normally, the adapter may ACK.
- With `AckMode.AUTO_ACK`, exceptions do not trigger an immediate NACK; if the error handler finishes normally, the adapter may ACK.
- With `AckMode.MANUAL`, the error handler must explicitly decide ACK vs. NACK.

If you quarantine the message and want to retire it, ACK after durable persistence. If you want Pub/Sub to retry or forward to a DLQ, NACK or rethrow the exception per your chosen mode. Never merely log an exception and return if the message still needs reprocessing.

### 8.3. Configuring DLQs on the subscription

Dead-letter topics are a property of the Pub/Sub subscription. Provision them outside the application via Terraform or `gcloud`:

```bash
gcloud pubsub subscriptions update orders-sub \
  --dead-letter-topic=orders-dlq \
  --max-delivery-attempts=8 \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

The Pub/Sub service agent requires `roles/pubsub.publisher` on the DLQ topic and `roles/pubsub.subscriber` on the source subscription. Create a separate subscription on the DLQ topic to read and investigate failing messages. Never rely on an in-JVM error channel as a durable DLQ if processes can restart or lose state.

### 8.4. Preventing duplicates and enforcing idempotency

Spring Integration and the Stream binder do not alter Pub/Sub's at-least-once delivery. Consumers should use stable event IDs and a transactional inbox to protect side effects:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Inside a single transaction, insert the event ID and apply business updates. If the insert conflicts, the event was already processed; skip side effects and ACK the current delivery. Never substitute Pub/Sub's message ID for a business event ID because two publishes of the same event can receive different message IDs.

## 9. Resource management, health, and lifecycle

### 9.1. Provisioning topics and subscriptions

Two options exist:

| Approach | Advantage | Caveat |
| --- | --- | --- |
| Binder auto-create | Fast local/dev startup, minimal initial config | Runtime needs creation permissions; subscriptions may follow group/anonymous conventions |
| IaC / `PubSubAdmin` | Enables reviewing IAM, retention, retries, DLQs, ordering, and exactly-once | Requires provisioning pipeline before consumer deployment |

For production, IaC provisioning is usually easier to govern. Applications receive only publish/subscribe rights on exact resources. If using `PubSubAdmin` in code, handle `ALREADY_EXISTS` and avoid multiple concurrent instances running with broad admin privileges.

### 9.2. Subscriber health indicators

Spring Framework on Google Cloud includes a `pubsub-subscriber` health indicator. With `PubSubInboundChannelAdapter`, wire in the auto-configured `HealthTrackerRegistry`:

```java
@Bean
public PubSubInboundChannelAdapter ordersInboundAdapter(
        MessageChannel ordersInputChannel,
        PubSubTemplate pubSubTemplate,
        HealthTrackerRegistry healthTrackerRegistry) {

    PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
    adapter.setOutputChannel(ordersInputChannel);
    adapter.setAckMode(AckMode.MANUAL);
    adapter.setHealthTrackerRegistry(healthTrackerRegistry);
    return adapter;
}
```

Expose Spring Boot Actuator health endpoints per application policy and secure management routes. Health indicators report subscriber client state; they do not replace Pub/Sub backlog, oldest unacked age, or DLQ dashboards.

### 9.3. Graceful shutdown

`PubSubInboundChannelAdapter` is a Spring lifecycle endpoint; Spring manages start/stop as the application context starts or closes. Never spawn new subscribers inside per-request or per-message callbacks. During shutdown:

1. Stop accepting new work per the adapter lifecycle.
2. Let in-flight handlers finish within the graceful shutdown window.
3. ACK messages whose business work committed.
4. Leave incomplete messages unacked so Pub/Sub redelivers after deadline/lease expiration.
5. Rely on idempotency when new instances reprocess redelivered messages.

With the binder, let Spring Cloud Stream manage binding lifecycles and never delete production subscriptions inside application shutdown hooks.

## 10. Testing Integration and Stream binder flows

### 10.1. Unit testing business handlers

Separate business services from adapters/binders to test:

- Valid payloads update business state and commit.
- Duplicate event IDs trigger no second side effect.
- Transient dependency errors propagate for retry.
- Permanent schema errors route to quarantine or DLQ per policy.
- Error handlers never ACK before durable persistence succeeds.

### 10.2. Testing channel adapters

Mock `OrderService` and `BasicAcknowledgeablePubsubMessage` to verify:

- `MANUAL` + success: handler calls `ack()` after business commit.
- `MANUAL` + error: handler calls `nack()`, or quarantines then ACKs per policy.
- `AUTO` + propagated exception: adapter NACKs.
- `AUTO` + error handler swallows exception: adapter may ACK; this test catches misconfigurations.
- `AUTO_ACK` + exception: does not NACK immediately; message awaits redelivery on deadline.

### 10.3. Using the Pub/Sub emulator

Start the emulator:

```bash
gcloud beta emulators pubsub start \
  --project=local-pubsub \
  --host-port=127.0.0.1:8085
```

Configure the application:

```yaml
spring:
  cloud:
    gcp:
      project-id: local-pubsub
      pubsub:
        emulator-host: 127.0.0.1:8085
```

Tests can create topics/subscriptions, publish, consume via inbound adapters or the binder, and verify payload conversion, headers, ack/nack, and idempotency. The emulator does not replace testing IAM, quotas, retry timing, DLQ forwarding, exactly-once, or ordering against real Pub/Sub.

### 10.4. Testing the binder with functional bindings

In a test profile:

1. Point `spring.cloud.function.definition` to the function under test.
2. Configure isolated test destinations and groups.
3. Point `emulator-host` at the emulator to avoid touching production projects.
4. Create fixture topics/subscriptions or enable auto-create solely in tests.
5. Publish events and assert the consumer receives the right DTOs.
6. Verify retry/ACK behavior for your pinned binder version.
7. Clean up test resources afterward.

Never use anonymous-subscription tests to verify production group durability; test with a stable group name.

### 10.5. Cloud sandbox tests

In a sandbox project, verify:

- Runtime service accounts hold only required publish/subscribe roles.
- Topics and subscriptions are provisioned properly.
- DLQ service agent IAM permissions are complete.
- `AUTO`, `AUTO_ACK`, and `MANUAL` behave as expected.
- Restarts/scale-outs do not spawn unexpected subscriptions.
- Consumer groups load-balance across instances while distinct groups receive independent copies.
- `PubSubMessageHandler` success/failure callbacks fire accurately.
- Ordering keys and header mappings propagate properly.

## 11. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Inbound adapter receives no messages | Wrong subscription, missing IAM, or subscriber not started | Check resource names, runtime roles, and lifecycle |
| Payload arrives as `byte[]` instead of DTO | `payloadType` unset or incompatible converter | Configure `setPayloadType()` and `PubSubMessageConverter` |
| Failing messages get ACKed | Error handler catches exceptions and returns normally under `AUTO`/`AUTO_ACK` | Propagate exceptions or use `MANUAL` for explicit ACK/NACK |
| Continuous message redeliveries | NACKs, exceptions, or expired ack deadlines | Inspect retry policy, DLQ, ack extension, and business bugs |
| `ORIGINAL_MESSAGE` header is null | Header filtered out or handler binds wrong message type | Check adapter, header mapper, and `allowedHeaders` |
| Channel send succeeds but topic stays empty | Sending to internal channel is not broker publish; wrong topic/IAM | Inspect callbacks, topic name, and publisher permissions |
| Stream binder creates unexpected subscriptions | Missing `group` causes anonymous subscription creation | Set a stable `group` and disable auto-create in production with IaC |
| Every instance receives duplicate messages | Instances use distinct groups or anonymous subscriptions | Share the same `group` name across instances of one consumer |
| Separate groups miss independent copies | Confused `group` with instance ID | Create a distinct subscription/group per business domain needing a copy |
| Binder lacks partitioned consumer support | Pub/Sub binder does not support Stream partitioning | Use ordering keys or select a binder supporting partitioning |
| Cannot observe `AckResponse.SUCCESSFUL` | Spring GCP wrappers do not expose `AckReplyConsumerWithResponse` | Use the Java Pub/Sub client directly if exactly-once ACK responses are needed |
| Business headers vanish | `allowedHeaders` or header mapper strips them | Update allowlist/header patterns and test the contract |

### 11.1. Diagnostic checklist

1. Verify actual topics and subscriptions in Google Cloud.
2. Check IAM bindings for the runtime service account.
3. Check `AckMode` or binder `consumer.ack-mode`.
4. Check whether error channels swallow exceptions.
5. Check `payloadType`, converters, and header mappers.
6. Verify `group` and subscription names.
7. Check Pub/Sub backlog, oldest unacked age, expired ack deadlines, and DLQs.
8. Verify active BOM, binder, and Integration adapter versions.

## 12. Choosing a solution by requirements

### 12.1. Decision matrix

| Requirement | Recommended option | Rationale |
| --- | --- | --- |
| Simple consumer processing one DTO | `PubSubTemplate.subscribe()` or Stream `Consumer<T>` | Minimal boilerplate, business-focused code |
| Flow with routers/filters/transformers/error channels | Spring Integration | Built-in Enterprise Integration Patterns and channel composition |
| Publishing from multiple services via channels | `PubSubMessageHandler` | Outbound adapter with publish callbacks |
| Cadenced polling or batch fetching | `PubSubMessageSource` | Controls poll intervals, blocking, and fetch sizes |
| Multiple microservices using functional bindings | Spring Cloud Stream binder | Decouples function code from destinations and consumer groups |
| Requires exactly-once ACK responses | Direct Java Pub/Sub client | Spring Cloud GCP does not expose `AckReplyConsumerWithResponse` |
| Requires Spring Cloud Stream partitioning | A binder supporting partitioning | Pub/Sub binder currently lacks Stream partitioning |
| Requires pre-deployment review of IAM, retention, DLQ, ordering | IaC + adapter/binder with auto-create off | Separates provisioning from runtime |

### 12.2. Selection principles

- Start with the smallest abstraction that satisfies current requirements.
- Use Spring Integration when orchestrating multi-step message flows.
- Use the Stream binder when standardizing producers/consumers around functions and groups.
- Use the direct Java client when Pub/Sub features are not exposed by wrappers.
- Never mix multiple consumer abstractions on the same subscription.
- Regardless of abstraction, always maintain idempotency, schema contracts, retry policies, DLQs, and observability.

## 13. Comprehensive hands-on exercise

An e-commerce system has topic `orders` and subscription `orders-sub`. The `order-worker` service consumes `OrderCreated`, checks inventory, saves the order in a database, and emits `OrderAccepted`. A separate flow records audit events to topic `order-audit`.

### Part A — Spring Integration

1. Add the Pub/Sub starter and `spring-integration-core` via a compatible BOM.
2. Create a `PubSubInboundChannelAdapter` using Streaming Pull.
3. Set `payloadType` to a DTO or `String` via a converter.
4. Use `AckMode.MANUAL` and ACK only after the transaction commits.
5. NACK transient dependency failures; quarantine permanent schema errors.
6. Wire an error channel and verify behavior when handlers propagate vs. swallow exceptions.
7. Create an outbound `PubSubMessageHandler` targeting `order-audit`.
8. Add success/failure callbacks and map `eventId` and `eventType` headers.
9. Experiment with `GcpPubSubHeaders.ORDERING_KEY` keyed by `orderId` if business order matters.
10. Compare Streaming Pull against `PubSubMessageSource` when publishing batches of small, slow-to-process messages.

### Part B — Spring Cloud Stream

1. Add `spring-cloud-gcp-pubsub-stream-binder`.
2. Write a `Function<OrderCreated, OrderAccepted>`.
3. Bind `acceptOrder-in-0` to destination `orders` with group `order-worker`.
4. Bind `acceptOrder-out-0` to destination `accepted-orders`.
5. Pre-provision topics/subscriptions with IaC and set `auto-create-resources: false`.
6. Test `AUTO`, `AUTO_ACK`, and `MANUAL` in a sandbox.
7. Run two instances sharing the same group and observe load sharing.
8. Add a second group and verify it receives an independent copy.
9. Omit the group to observe anonymous subscription creation and binder-shutdown cleanup.
10. Verify the binder lacks partitioning support and describe how ordering keys address per-key ordering instead.

### Evaluation matrix

| Scenario | Expected outcome |
| --- | --- |
| Adapter receives valid message | Payload converts to expected DTO and handler succeeds |
| Transaction succeeds | ACK runs only after commit |
| Dependency error | NACK/retry follows configured policy |
| Error handler swallows exception in AUTO | Test detects the message may get ACKed |
| Publish via outbound adapter | Success/failure callbacks receive outcome |
| Business headers | Only allowlisted headers are published |
| Same Stream group, multiple instances | Messages load-balance within the shared subscription |
| Different groups | Each group receives an independent copy |
| No group | Anonymous subscription created/cleaned up per binder behavior |
| Pub/Sub partitioning | Stream partitioning kept off since binder does not support it |
| Duplicate event | Inbox/idempotency blocks duplicate side effects |

### Completion criteria

- Explains differences between Spring Integration adapters and the Stream binder.
- Runs inbound/outbound adapters against an emulator or sandbox.
- Chooses appropriate ACK modes and handles error-channel semantics properly.
- Configures functional bindings, destinations, and stable consumer groups.
- Controls resource creation and IAM safely.
- Tests retries, duplicates, header mapping, and graceful shutdown.
- Identifies partitioning and exactly-once ACK response limitations.

## 14. Comparison with AWS and Azure

| Integration need | Google Cloud Pub/Sub | AWS | Azure |
| --- | --- | --- | --- |
| Spring Integration | Pub/Sub channel adapters in Spring Framework on Google Cloud | Spring Integration AWS adapters for SQS/SNS/S3 and supported services | Spring Integration adapters for Azure Service Bus/Storage depending on module |
| Spring Cloud Stream | Dedicated Pub/Sub binder built on channel adapters | Binder for Kinesis; SQS/SNS commonly use matching adapters/connectors | Binders for Azure Event Hubs/Service Bus depending on project and version |
| Consumer groups | Pub/Sub subscription; Stream group maps to subscription | SQS queue consumers or Kinesis shard/consumer semantics | Service Bus subscriptions/sessions or Event Hubs consumer groups |
| ACK | Pub/Sub ACK/NACK via message wrapper | SQS `DeleteMessage` or visibility timeout; Kinesis checkpoints | Service Bus `Complete`/`Abandon`; Event Hubs checkpoints |
| Partitioning/ordering | Pub/Sub ordering keys; Stream binder lacks partitioning | Kinesis shards/partition keys; SQS FIFO MessageGroupId | Event Hubs partition keys; Service Bus SessionId |
| Retry/DLQ | Subscription retry policy and dead-letter topic | SQS redrive policy/DLQ or service retry strategies | Service Bus DLQ or Event Hubs checkpoint/retry strategies |

Adapters and binders do not unify broker semantics across providers. When migrating clouds, remap destinations, groups/subscriptions, ACKs, retries, DLQs, ordering, and partitioning to the target service. Never assume a `consumer group` in Spring Cloud Stream behaves identically across every binder.

## Summary

Spring Integration and Spring Cloud Stream both connect Spring Boot to Google Cloud Pub/Sub, at different abstraction levels. Spring Integration uses `PubSubInboundChannelAdapter`, `PubSubMessageSource`, and `PubSubMessageHandler` with `MessageChannel`s to support routing, error channels, pollable sources, header mapping, and ACK modes. The Spring Cloud Stream binder uses `Supplier`/`Function`/`Consumer`, destinations, and consumer groups for functional event-driven microservices.

With Integration, understand `AUTO`, `AUTO_ACK`, and `MANUAL`—notably, an error handler returning normally can cause adapters to ACK failed messages. With the Stream binder, declare stable groups for durable subscriptions, govern resource auto-creation carefully, and remember the Pub/Sub binder does not support Stream partitioning. When exact `AckResponse` tracking for exactly-once delivery is required, use the Java Pub/Sub client directly because Spring Cloud GCP does not expose `AckReplyConsumerWithResponse`.

Whichever path you choose, consumers still need idempotency, commit-before-ACK discipline, bounded retries, durable DLQs, header/schema contracts, and monitoring. Choose abstractions for processing requirements and required control—not merely for fewer lines of code.

## References

- [Spring Framework on Google Cloud — Spring Integration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html) — inbound/outbound channel adapters, pollable sources, ACK modes, error handling, and header mapping.
- [Spring Framework on Google Cloud — Spring Cloud Stream binder](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html) — Pub/Sub binder, binding configuration, consumer groups, resource creation, and functional model.
- [Google Cloud — Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring) — choosing the Pub/Sub starter, Spring Integration adapters, and Stream binder; exactly-once ACK response limitation.
- [Spring Framework on Google Cloud — Pub/Sub API](https://googleapis.dev/java/spring-cloud-gcp/latest/index.html) — `PubSubInboundChannelAdapter`, `PubSubMessageSource`, `PubSubMessageHandler`, and supporting APIs.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — `<functionName>-in-0` and `<functionName>-out-0` conventions.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group, and consumer/producer properties.
- [Spring Cloud Stream — Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) — consumer group semantics and competing consumers.
- [Spring Guides — Messaging with Google Cloud Pub/Sub](https://github.com/spring-guides/gs-messaging-gcp-pubsub) — examples of Spring Integration inbound/outbound channel adapters.
