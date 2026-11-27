# Choosing Spring Integration for Message-Driven Integration Flows

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot applications connect to managed services from AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries, SDKs, and connectors. When a business workflow needs to receive events from a queue, call external APIs, transform payloads, route conditionally, aggregate multiple results, or send messages to another system, the integration quickly becomes a multi-step processing pipeline.

**Spring Integration** provides a message-driven programming model to describe such flows using messages, channels, endpoints, transformers, routers, filters, splitters, aggregators, and gateways. Instead of having business services call each SDK directly, applications can place integration steps into a flow with clear boundaries. Input/output adapters handle communication with external systems; intermediate handlers process data and coordinate orchestration.

Spring Integration is particularly useful when an application needs to **orchestrate integration flows inside a single Spring process**. For example: receiving a ReservationConfirmed event from SQS, validating the schema, enriching data from a profile service, routing by tenant, and forwarding the information to another queue or partner API. Flows can use synchronous or asynchronous channels, manage retry/error channels, and combine multiple transports.

Spring Integration does not replace every messaging platform. When the primary goal is building event-driven microservices with cross-service message contracts and the ability to swap binders between Kafka/RabbitMQ/cloud brokers, **Spring Cloud Stream** is often a better fit. When only a single simple SDK call is needed in a use case, calling the SDK directly can be clearer. This lesson focuses on choosing the right tool and designing resilient flows.

After this lesson, you will be able to:

1. Distinguish between Spring Integration, Spring Cloud Stream, and calling SDKs directly.
2. Identify messages, headers, channels, endpoints, adapters, and gateways.
3. Design flows using the Java DSL with transformers, filters, routers, and service activators.
4. Connect flows to managed queues/topics/object storage/APIs on AWS, Azure, and Google Cloud.
5. Choose appropriate channel semantics, concurrency, transaction boundaries, and backpressure.
6. Handle errors, retries, dead-lettering, idempotency, and the transactional outbox.
7. Test flows using mocks, test channels, broker emulators, and cloud staging.
8. Monitor throughput, latency, backlog, retries, and errors per endpoint.

> **Scope:** Spring Integration is a message-oriented integration framework within a Spring application. Cloud adapters depend on specific modules, versions, and services. Do not assume a Spring Cloud starter provides out-of-the-box adapters for every service or operation; when a suitable adapter is missing, you can write a small bridge using the provider SDK in a dedicated endpoint.

## 2. Choosing Spring Integration, Spring Cloud Stream, or Direct SDK?

### 2.1. Start from the Shape of the Problem

All three options can coexist in one system, yet each solves a different problem:

| Need | Typically Suitable Choice | Reason |
| --- | --- | --- |
| Multi-step orchestration inside one application: transform, filter, route, split, aggregate, call APIs | **Spring Integration** | Rich flow, channel, and endpoint model |
| Building producer/consumer microservices exchanging events over a broker, wanting a binder abstraction | **Spring Cloud Stream** | Function-based model, binder and destination abstractions |
| A use case making one simple cloud API call with no intermediate flow | **Direct SDK** | Fewer layers, easy to read and debug |
| Polling a data source, enriching, transforming, and writing to multiple destinations | **Spring Integration** | Built-in inbound/outbound adapters and routing |
| Continuous event stream processing with Kafka Streams semantics or windowed/stateful streams | **Kafka Streams / dedicated stream platform** | Deep stream processing semantics |
| Orchestrating long-running workflows spanning hours/days needing durable state and compensation | **Workflow engine / managed workflow** | State and progress are durably persisted across process restarts |

Do not pick a framework merely because an integration *can* be written with it. Identify where orchestration is needed, which transports must be supported, delivery guarantees, latency, throughput, ordering, retries, and who owns the schema.

### 2.2. Spring Integration vs. Spring Cloud Stream

| Criterion | Spring Integration | Spring Cloud Stream |
| --- | --- | --- |
| Focus | Integration flows inside an application | Message-driven microservices via binders |
| Model | MessageChannel, endpoint, IntegrationFlow | Function/Consumer/Supplier and bindings |
| Orchestration | Router, transformer, filter, splitter, aggregator, gateway | Message processing in functions; binder handles transport binding |
| Broker | Endpoint-specific adapters/connectors | Binders for Kafka, RabbitMQ, and some managed brokers |
| Connecting multiple systems in one process | Very well suited | Possible, but not the primary focus |
| Transport abstraction | Per specific adapter | Destination/binder abstraction |
| Advanced features | Channels, pollers, endpoint lifecycle, control bus, error channels | Consumer groups, partitioning, binder-specific capabilities |

Spring Cloud Stream may use Spring Integration under the hood for certain parts of its implementation, yet the two frameworks have different APIs and target use cases. You can use Stream for boundaries between microservices and Integration for a complex internal flow, provided responsibilities are clearly separated so two layers do not manage retries/acks in confusing ways.

### 2.3. Decision Tree

~~~mermaid
flowchart TD
    A["Need to communicate with external systems?"] -->|No| B["Use standard service/domain code"]
    A -->|Yes| C{"Just a single simple SDK call?"}
    C -->|Yes| D["Call SDK directly via a small adapter"]
    C -->|No| E{"Primary focus is producer/consumer microservices via a broker?"}
    E -->|Yes| F["Consider Spring Cloud Stream"]
    E -->|No| G{"Multiple integration steps requiring orchestration?"}
    G -->|Yes| H["Spring Integration flow"]
    G -->|No| I["Choose the simplest adapter/SDK"]
~~~

Re-evaluate the decision when a flow starts accumulating significant business logic. An integration flow should coordinate messages and invoke application services; complex domain rules still belong in the domain/application layer. Do not turn a long IntegrationFlow into a container for all business logic.

### 2.4. Questions Before Choosing

- Is the input source a queue, topic, webhook, file/object storage, database polling, or HTTP?
- Is the output going to one or multiple systems? Is fan-out or content-based routing needed?
- Must messages be processed synchronously on the request thread or asynchronously?
- When the broker/destination is unavailable, where are messages held?
- Is ordering required across the whole queue, per partition, per tenant, or per aggregate ID?
- Can consumers receive duplicates? Where does the idempotency key live?
- Is a synchronous transaction needed between the broker and database, or should outbox/inbox be used?
- Who manages schema, versioning, retention, replay, and dead-lettering?

## 3. Core Components of Spring Integration

### 3.1. Messages and Headers

Spring Integration passes data as `Message<T>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<ReservationConfirmed> message =
        MessageBuilder.withPayload(event)
                .setHeader("tenantId", event.tenantId())
                .setHeader("correlationId", correlationId)
                .setHeader("eventType", "ReservationConfirmed")
                .build();
~~~

A message consists of:

- **Payload:** the primary data, such as a Java object, JSON string, byte array, or file reference.
- **Headers:** metadata used for routing, correlation, replies, content type, timestamps, and transport adapters.

Do not place secrets, access tokens, or sensitive data into headers. Headers can be logged, copied to transports, or displayed in traces. Carry only necessary metadata; tenant identity must be authenticated at the boundary, not trusted from arbitrary client-sent headers.

### 3.2. MessageChannel

Channels govern how messages move from producers to consumers. Common channels include:

| Channel | Core Semantics | When to Use |
| --- | --- | --- |
| `DirectChannel` | Invokes subscribers on the sender's thread, typically load-balancing across subscribers | Simple flows needing synchronous call stacks and transaction context |
| `PublishSubscribeChannel` | Broadcasts messages to multiple subscribers | In-application fan-out |
| `QueueChannel` | Stores messages in an internal queue; consumers receive later | Decoupling producer/consumer and buffering in-process |
| `ExecutorChannel` | Dispatches processing via a task executor | Separating threads, adding bounded concurrency |
| `PriorityChannel` | Internal queue with priority ordering | Prioritizing work within the process scope |

`QueueChannel` is an internal queue of the application process, not SQS, Service Bus, Pub/Sub, or Kafka. When the process stops, messages in an internal queue can be lost unless a persistent message store is configured. Do not use in-memory channels in place of a durable broker.

### 3.3. Endpoints and Handlers

Endpoints connect channels to actions:

- **Service activator:** invokes a method/service to process a payload.
- **Transformer:** alters the payload or headers.
- **Filter:** decides whether a message proceeds.
- **Router:** selects a destination channel conditionally.
- **Splitter:** splits one message into multiple messages.
- **Aggregator:** combines related messages into one result.
- **Bridge:** connects two channels.
- **Inbound adapter:** receives data from an external system and feeds it into the flow.
- **Outbound adapter:** sends messages out to an external system.
- **Gateway:** provides an interface for request/reply or command/reply calls from application code.

Adapters are typically unidirectional; gateways typically provide request/reply interaction. Choose the right endpoint type to express semantics and timeouts clearly.

### 3.4. IntegrationFlow and Java DSL

The Java DSL allows declaring flows with a builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ReservationFlowConfiguration {

    @Bean
    IntegrationFlow reservationFlow(ReservationHandler handler) {
        return IntegrationFlow.from("reservation.input")
                .transform(String.class, String::trim)
                .filter(String.class, payload -> !payload.isBlank())
                .transform(String.class, payload ->
                        new ReservationCommand(payload))
                .handle(handler, "process")
                .get();
    }
}
~~~

`IntegrationFlow.from("reservation.input")` receives messages from the channel with that name. Subsequent endpoints chain into a pipeline. `handle(handler, "process")` invokes the handler's method; the handler can return a result for the flow to continue or return `void` to end it.

A good flow should be clearly named after its use case, split into subflows when branches become complex, and keep business logic inside independently testable services.

### 3.5. Dependencies and Version Compatibility

With Spring Boot, the baseline starters are typically:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The starter brings Spring Integration core into the application; the test module provides utilities for testing flows/endpoints. Rely on Spring Boot's dependency management to keep Spring Framework, Spring Integration, and Spring Integration Test compatible. Do not override individual Integration module versions without checking the release train. Cloud connectors are separate dependencies chosen per provider/service and version in use; do not add every connector to the classpath just in case.

## 4. Building an Integration Flow Step by Step

### 4.1. Declaring Message Channels

Channels can be declared as beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class IntegrationChannelConfiguration {

    @Bean("reservation.input")
    MessageChannel reservationInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel reservationWorkQueue() {
        return new QueueChannel(500);
    }
}
~~~

With `DirectChannel`, the subscriber executes on the sending thread. If the handler fails, the exception can propagate back to the caller. With `QueueChannel`, the producer puts messages into a buffer; the consumer must poll or subscribe appropriately. A bounded-capacity queue prevents unbounded in-process buffer growth, though when full, `send()` may block or fail depending on timeout/configuration.

### 4.2. Transformer and Filter

Transformer converts the payload:

~~~java
@Bean
IntegrationFlow normalizeReservationFlow() {
    return IntegrationFlow.from("reservation.raw")
            .transform(String.class, String::trim)
            .transform(String.class, String::toUpperCase)
            .channel("reservation.normalized")
            .get();
}
~~~

Filter drops messages that do not meet a condition:

~~~java
@Bean
IntegrationFlow validReservationFlow() {
    return IntegrationFlow.from("reservation.normalized")
            .filter(String.class, payload -> payload.startsWith("RES-"),
                    spec -> spec.discardChannel("reservation.invalid"))
            .channel("reservation.valid")
            .get();
}
~~~

A discard channel is useful for routing rejected messages into an audit or quarantine flow. Do not silently drop messages when they represent data errors that must be handled.

### 4.3. Content-Based Router

Router sends messages to different channels:

~~~java
@Bean
IntegrationFlow routeReservationFlow() {
    return IntegrationFlow.from("reservation.valid")
            .route(String.class,
                    payload -> payload.startsWith("RES-VIP")
                            ? "reservation.priority"
                            : "reservation.standard")
            .get();
}
~~~

In production, route on validated domain/header attributes against a fixed list of destination channels. Configure a default route or error path for unrecognized values; do not dynamically create unbounded channels from external input.

### 4.4. Splitter and Aggregator

Splitter breaks a batch into multiple messages:

~~~java
@Bean
IntegrationFlow splitImportFlow() {
    return IntegrationFlow.from("reservation.batch")
            .split()
            .channel("reservation.item")
            .get();
}
~~~

Aggregator combines results sharing a correlation key:

~~~java
@Bean
IntegrationFlow aggregateReservationFlow() {
    return IntegrationFlow.from("reservation.result")
            .aggregate(spec -> spec
                    .correlationStrategy(message ->
                            message.getHeaders().get("batchId"))
                    .releaseStrategy(group ->
                            group.size() >= 3))
            .channel("reservation.batch.completed")
            .get();
}
~~~

This example only illustrates the principle. A production aggregator needs a release strategy based on expected result count, timeout/expiry, group capacity, partial results, and handling of late-arriving messages. If a group never satisfies the release condition, messages can hold state in memory/store indefinitely. Configure a message group store, discard/reaper, and persistence appropriate to the flow's criticality.

### 4.5. Service Activator and Application Service

Handlers should invoke use cases/services:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ReservationHandler {

    private final ReservationApplicationService applicationService;

    public ReservationHandler(
            ReservationApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    public void process(ReservationCommand command) {
        applicationService.process(command);
    }
}
~~~

For this example, the command can be a simple record:

~~~java
public record ReservationCommand(String reservationId) {
}
~~~

Do not place all business validation, pricing, authorization, or transaction orchestration inside the handler. The integration layer translates protocols/messages into commands; the application service executes the use case according to system rules.

## 5. Gateways and Request/Reply

### 5.1. When to Use a Messaging Gateway?

A gateway lets application code invoke a flow via an interface:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "reservation.command")
public interface ReservationCommandGateway {

    @Gateway(requestChannel = "reservation.command")
    ReservationResult confirm(ReservationCommand command);
}
~~~

Flow handling the command and returning a response:

~~~java
@Bean
IntegrationFlow reservationCommandFlow(
        ReservationApplicationService applicationService) {
    return IntegrationFlow.from("reservation.command")
            .handle(ReservationCommand.class,
                    (command, headers) -> applicationService.confirm(command))
            .get();
}
~~~

Gateways fit request/reply interactions with a deadline. If the flow traverses an asynchronous broker, do not keep an HTTP request open waiting indefinitely for a reply message. Use a correlation ID and callbacks/futures, or return `202 Accepted` with an operation ID if the work is long-running.

### 5.2. Timeouts and Reply Channels

Request/reply requires defining:

- How long to wait for a response.
- Correlation ID to match replies with requests.
- Behavior on timeout: cancel, return pending status, or re-query.
- Reply channel and correlation state cleanup.
- What happens if a reply arrives after timeout.

A timeout does not prove processing on the remote system failed. The request may have been processed while the response was delayed or lost. If the caller retries, the command needs an idempotency key.

## 6. Connecting Managed Cloud Services

### 6.1. Three Layers in a Cloud Integration Flow

A cloud-connected flow should separate three layers:

1. **Transport adapter:** receives/sends messages via SQS, SNS, EventBridge, Azure Service Bus, Event Hubs, Google Pub/Sub, or other APIs.
2. **Integration flow:** transforms, validates envelopes, routes, enriches, retries, and maps errors.
3. **Application/domain service:** executes business logic and persistence.

Cloud adapters must manage authentication, Region/endpoints, acknowledgment, visibility/lock duration, batch size, and provider-specific errors. The flow should not assume all brokers share identical delivery, ordering, or settlement semantics.

### 6.2. AWS: SQS/SNS/EventBridge

For AWS, you can use the appropriate AWSpring module, a Spring Integration AWS adapter if supported by the project version, or a small bridge built with AWS SDK v2. For example, an inbound queue adapter should forward messages to a channel after handling message receipt/ack per the listener contract.

Simple bridge pattern:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
public class CloudMessageBridge {

    private final MessageChannel reservationInput;

    public CloudMessageBridge(
            @Qualifier("reservation.input") MessageChannel reservationInput) {
        this.reservationInput = reservationInput;
    }

    public void accept(String body, String providerMessageId) {
        reservationInput.send(
                MessageBuilder.withPayload(body)
                        .setHeader("providerMessageId", providerMessageId)
                        .setHeader("sourceSystem", "aws-sqs")
                        .build());
    }
}
~~~

The concrete listener/adapter calls `accept()` after receiving a message. Message ack/deletion must follow the adapter's acknowledgment mode: do not delete the message before the flow reaches a state considered successful. If the bridge simply calls `send()` on a DirectChannel, downstream processing runs synchronously on the same call stack; if the channel is asynchronous, a mechanism is needed to confirm after durable processing rather than acknowledging immediately upon in-memory enqueueing.

For outbound calls, a handler can call `SqsClient.sendMessage`, `SnsClient.publish`, or `EventBridgeClient.putEvents`. When sending an EventBridge batch, inspect every entry result; HTTP 200 does not mean every event was accepted.

### 6.3. Azure: Service Bus and Event Hubs

Azure Service Bus provides queue/topic subscriptions and settlement actions such as complete, abandon, defer, and dead-letter; lock duration and lock renewal affect long-running message processing. Event Hubs is an event streaming platform with partition/offset semantics, better suited for high-volume stream ingestion than standard command queues.

Use Azure Spring integration or Spring Integration adapters if the version in use supports the required operations. When bridging via the Azure SDK, keep `ServiceBusReceivedMessageContext` or receiver settlement in the transport adapter and only complete the message once the flow succeeds according to policy. Do not complete a message immediately after sending to an in-memory internal channel if that channel can lose messages on process crash.

### 6.4. Google Cloud: Pub/Sub

Google Cloud Pub/Sub features subscriptions, acknowledgment deadlines, lease extension, retry policies, and dead-letter topics. Ordering is only guaranteed when ordering is enabled and ordering key/region semantics are respected. Use Spring Cloud GCP Pub/Sub integration or a compatible adapter for your project version; when using the Google Cloud client directly, bridge payloads and metadata into Spring Messages.

Acks must align with durable processing outcomes. If a consumer acks before the DB transaction commits, a crash can lose the message. If it acks after commit but the ack response is lost, the message may be redelivered; idempotency remains mandatory.

### 6.5. Comparing Broker Semantics

| Aspect | Amazon SQS | Azure Service Bus | Google Pub/Sub |
| --- | --- | --- | --- |
| Receiving mechanism | Receive + visibility timeout | Receive + message lock | Pull/push subscription + ack deadline |
| Completion | Delete message / adapter acknowledgment | Complete/settle message | Acknowledge |
| Retry/redelivery | Visibility timeout and redrive policy | Abandon/lock expiry and delivery count | Nack/ack deadline expiry and retry policy |
| Dead-letter | DLQ via redrive policy | Dead-letter queue | Dead-letter topic when configured |
| Ordering | FIFO queue per message group | Session/order semantics per entity | Ordering key when enabled |
| Duplicates | May redeliver | May redeliver | May redeliver |
| Limits | Per queue type/Region/quota | Per tier/entity/quota | Per quota/ordering configuration |

Exact names and settings vary by SDK/adapter. Always check documentation for the version and entity type in use. Do not assume Spring adapters automatically behave identically for acks, retries, ordering, and DLQs.

## 7. Choosing Channels, Concurrency, and Transaction Boundaries

### 7.1. Synchronous or Asynchronous?

The channel directly shapes the execution model:

- `DirectChannel` invokes subscribers on the sending thread. Handler errors can propagate to the caller; thread-local transactions normally remain active on the call stack.
- `ExecutorChannel` hands processing off to an executor. Thread context is not fully propagated automatically; an open transaction on the sender thread does not automatically span work on the receiver thread.
- `QueueChannel` holds messages in an internal buffer, decoupling send and receive times. Queues require a consumer/poller and a capacity limit.
- `PublishSubscribeChannel` fans out to multiple subscribers. If subscribers process in parallel or independently, one branch failing does not mean other branches roll back.

Choose synchronous flows when an immediate response is needed, load is light, and dependencies are stable. Choose asynchronous flows when decoupling producers/consumers, bounded buffering, or background processing is required. For critical work that must survive restarts, store messages in a broker or database before passing through internal channels.

### 7.2. Pollers and Inbound Polling

Some sources do not push messages and must be polled on a schedule. Spring Integration supports pollers for inbound adapters and pollable channels:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean
IntegrationFlow scheduledImportFlow(ExternalRecordSource source) {
    return IntegrationFlow
            .from(source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(10))
                                    .maxMessagesPerPoll(20)))
            .handle("importHandler", "process")
            .get();
}
~~~

This example illustrates a poller at the Integration DSL level; real adapters must supply a compatible source and appropriate error handling. `maxMessagesPerPoll` caps the number of messages fetched per poll, not the system's total message count.

Poll interval, batch size, and concurrency should be tuned to source quotas, latency, and downstream throughput. Polling too fast generates unnecessary requests; polling too slowly increases wait times and backlogs. For rate-limited APIs, add backoff when throttled and avoid having multiple replicas poll the same source without work partitioning.

### 7.3. Backpressure and Bounded Concurrency

Do not allow flows to spawn unbounded tasks or queues. Set limits:

- Queue capacity or broker prefetch/receive batch size.
- Executor core/max pool size and bounded task queue.
- In-flight message count per partition/tenant.
- Timeouts for downstream APIs.
- Dedicated bulkheads for slow dependencies.
- Admission control or pause/resume when backlog crosses thresholds.

If the intake rate exceeds the processing rate for an extended period, adding threads merely shifts the bottleneck into exhausted connections, memory, or downstream quotas. Monitor queue depth, active/rejected executor tasks, and consumer lag to decide when to scale or throttle intake.

### 7.4. Transaction Boundaries Do Not Automatically Cross Every Channel

`DirectChannel` normally stays on the same thread; however, a transaction only covers resources managed by the transaction manager. Sending a message to a cloud broker and writing to a database do not automatically form a distributed transaction just because they reside in the same IntegrationFlow.

Across asynchronous channels, executors, or broker boundaries, do not rely on the producer's thread-local transaction. Define the transaction in the handler/service where database operations occur; commit before acknowledging the broker per adapter semantics. When an event must be emitted alongside a DB commit, use the transactional outbox rather than assuming one transaction spans both systems.

## 8. Error Handling, Retries, and Dead-Lettering

### 8.1. Error Channels

Spring Integration can route errors raised in a flow to an error channel. For message-driven endpoints, errors can be wrapped in an `ErrorMessage` carrying a `MessagingException` with the failed message/endpoint.

A dedicated error flow can be configured:

~~~java
@Bean
IntegrationFlow reservationErrorFlow(ReservationErrorHandler errorHandler) {
    return IntegrationFlow.from("errorChannel")
            .handle(errorHandler, "handle")
            .get();
}
~~~

This example illustrates having a dedicated handler; in real applications, default error channels, executors, and endpoint scopes must be verified. Do not assume every exception from a broker listener automatically arrives on the same error channel: an adapter may have its own error handler, callbacks, or require exceptions to propagate for the broker to redeliver.

Error handlers should classify failures:

- Permanent validation/schema errors: quarantine or dead-letter, do not retry repeatedly.
- Permission/configuration errors: alert and stop retrying quickly.
- Throttling/network/service unavailable: bounded retry with backoff and jitter.
- Transient database failures: retry per transaction policy and deadline.
- Programming bugs: preserve stack trace/correlation ID, alert, and move the message to investigation state.

### 8.2. Bounded Retries

Spring Integration supports retry advice on endpoints via Spring Retry or the version-appropriate retry mechanism. Conceptual configuration example:

~~~java
@Bean
IntegrationFlow publishReservationFlow(
        ReservationPublisher publisher) {
    return IntegrationFlow.from("reservation.to.publish")
            .handle(publisher, "publish",
                    endpoint -> endpoint.advice(retryAdvice()))
            .get();
}
~~~

`retryAdvice()` must be configured with an appropriate retry policy, backoff, exception classifier, and recovery callback. Do not copy a single policy across every endpoint: API validation, permissions, throttling, and timeouts have different retryability characteristics.

Practical rules:

1. Retry only transient errors.
2. Cap attempts and total retry duration.
3. Use exponential backoff with jitter.
4. Respect `Retry-After` or provider throttling guidance when present.
5. Do not retry simultaneously in the SDK, Integration advice, and broker without accounting for total attempts.
6. After exhausting retries, record the state and move to dead-letter/review.

### 8.3. SDK Retries vs. Broker Retries

Multiple retry layers can exist: SDK HTTP retries, Integration endpoint retries, and broker redelivery. If each layer tries 3 times, a single message can trigger far more requests than expected. Assign clear responsibility for which layer retries which failures:

| Layer | Appropriate Responsibility |
| --- | --- |
| SDK client | Retry transient transport/service errors per API policy |
| Integration endpoint | Retry handler processing errors when the operation is safe to repeat |
| Broker | Redeliver when consumer fails to ack/complete or visibility/lock expires |
| Outbox worker | Retry publishing after the DB has durably recorded the event |
| Consumer inbox | Deduplicate and prevent repeated side effects |

Record per-layer attempt counts in metrics/logs to investigate retry storms.

### 8.4. Dead-Lettering and Quarantine

A DLQ holds messages that exceeded the retry policy or were rejected by rules. Quarantine can be a separate queue, database table, or access-restricted object storage.

Each dead-letter record should include:

- Message ID and business event ID.
- Source broker/queue/subscription and receipt timestamp.
- Error category/code and failing endpoint.
- Attempt count, correlation ID, and trace ID.
- Payload or encrypted payload pointer, per retention policy.
- Reprocessing status, actor/automation executing it, and outcome.

Do not blindly replay an entire DLQ into production. Fix the root cause first, verify schema/version compatibility, throttle replay rate, and ensure consumers are idempotent.

## 9. Idempotency, Ordering, and Transactional Outbox

### 9.1. Why Assume Messages Can Be Redelivered?

Most popular managed brokers provide at-least-once delivery under standard configurations. A consumer can receive the same message again when:

- Processing completes but the process crashes before ack/complete.
- The ack response is lost on the network.
- Lock/visibility/ack deadline expires while the handler is still running.
- The broker redelivers after a transient failure.
- The producer retries on timeout without knowing whether the first send was accepted.

Therefore, do not rely on a broker-assigned message ID as an exactly-once business guarantee. You need a stable producer-generated business event ID, such as `eventId`, `commandId`, or `reservationId + eventVersion`.

### 9.2. Consumer Inbox / Deduplication

An inbox table with a unique constraint prevents business side effects from executing twice:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(120) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Within the same transaction as the business update, the consumer inserts the event ID:

~~~java
@Transactional
public void handle(ReservationConfirmed event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
            "billing-consumer", event.eventId());

    if (!firstDelivery) {
        return;
    }

    billingService.createChargeIntent(event.reservationId());
}
~~~

`insertIfAbsent` must rely on the unique constraint and return false when the key already exists. Do not implement a check-then-insert pattern using two separate queries because two concurrent consumers can both observe the key as absent. If a side effect calls an external system, the DB transaction does not cover that API; pass an idempotency key to the target API or write an outbox command for separate processing.

Acknowledge the message after the transaction commits successfully. If the ack fails after commit, the message may be redelivered, but the inbox prevents reprocessing.

### 9.3. Ordering Is a Property of the Broker and Key

Spring Integration does not create global ordering for all messages on its own. Ordering depends on the broker, partition/session/message group, and concurrency:

- SQS FIFO uses message group IDs to preserve order within a group; different groups can be processed in parallel.
- Azure Service Bus uses sessions to group messages by session ID and process them in order within a session.
- Pub/Sub ordering requires enabling ordering and supplying an ordering key subject to service constraints.
- Kafka orders per partition; the key determines which partition a message enters.

If business logic requires ordering per reservation, tenant, or aggregate, use the corresponding stable key. Also cap concurrency per key/partition and define how to handle late messages or retries that alter completion order.

### 9.4. Transactional Outbox for Producers

When a transaction updates a database and also needs to emit an event, do not arbitrarily call the broker before or after commit. Two failure windows exist:

- Publish before DB commit: the event may be sent while the DB transaction rolls back.
- DB commit before publish: the process may crash and the event is never sent.

The outbox records the business change and the event in the same DB transaction:

~~~sql
CREATE TABLE outbox_event (
    event_id      VARCHAR(120) PRIMARY KEY,
    aggregate_id  VARCHAR(120) NOT NULL,
    event_type    VARCHAR(160) NOT NULL,
    payload       JSONB NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL,
    published_at  TIMESTAMPTZ NULL,
    attempts      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_unpublished
    ON outbox_event (occurred_at)
    WHERE published_at IS NULL;
~~~

The DDL above uses PostgreSQL `JSONB` and `TIMESTAMPTZ` types; for another engine, adapt the data types and partial index syntax to that database.

In the application service:

~~~java
@Transactional
public void confirm(String reservationId) {
    Reservation reservation = reservationRepository.confirm(reservationId);

    ReservationConfirmed event = eventFactory.from(reservation);
    outboxRepository.insert(event.eventId(), reservation.id(),
            "ReservationConfirmed", serialize(event), event.occurredAt());
}
~~~

A worker reads the outbox and sends events through an Integration flow or outbound adapter. Claim rows using a short lease or lock; do not hold a transaction/row lock while waiting on cloud broker calls. Once the broker confirms publishing, mark `published_at`. If the worker crashes after publishing but before updating, the event may be sent again; the consumer inbox handles duplicates.

The outbox recovers publishing intent after a DB commit; it does not make the broker exactly-once. With multiple workers, use `FOR UPDATE SKIP LOCKED` or a timed lease, along with a mechanism to reclaim records held by a dead worker.

### 9.5. Do Not Confuse Ack with Business Commit

The transport adapter should complete/delete/ack a message after durable downstream processing. With a synchronous flow over DirectChannel, the adapter can catch exceptions from handlers and choose not to ack. With an asynchronous flow, a successful `send()` may only mean the message entered an internal queue; it does not prove the DB commit or side effects finished.

If you need to decouple the transport listener from an async flow, move the message into a durable internal broker or persist it to an inbox/work table before acknowledging the source. If you only enqueue in memory and ack, a process crash will lose the message.

## 10. Schemas, Payloads, and Security

### 10.1. Envelopes and Versioning

Standardize an envelope for cross-system messages:

~~~json
{
  "eventId": "evt-01J...",
  "eventType": "ReservationConfirmed",
  "schemaVersion": 2,
  "occurredAt": "2026-11-24T10:00:00Z",
  "producer": "reservation-service",
  "correlationId": "corr-...",
  "tenantId": "tenant-a",
  "data": {
    "reservationId": "res-1001",
    "propertyId": "property-21"
  }
}
~~~

An envelope helps consumers route and check versions before parsing business payloads. Do not use Java class names as cross-service schema contracts. Use JSON Schema, Avro, or Protobuf and manage compatibility according to organizational processes.

When adding fields, prefer backward-compatible changes. When changing field types, semantics, or requiredness, increment the schema version and plan producer/consumer rollouts in compatible order.

### 10.2. Small Payloads, Large Object References

Brokers impose message size limits per service and tier. Do not send large files or entire documents inside messages unnecessarily. Upload objects to S3/Blob/GCS and send a controlled locator, checksum, content type, and version/generation. Consumers fetch objects using workload identity with least privilege.

A locator is not authorization. Consumers must verify tenant mappings and bucket/container allow-lists before accessing objects; do not trust URIs supplied arbitrarily by external producers if the producer is unauthenticated.

### 10.3. Identity and Least Privilege

Each adapter needs only permissions for its operations:

- AWS producer: permission to publish to the specific SNS topic, EventBridge bus, or target queue.
- AWS consumer: permission to receive/delete/change visibility on the specific SQS queue; no queue management permissions needed.
- Azure producer/consumer: appropriate role on the specific Service Bus namespace/entity.
- Google Pub/Sub publisher/subscriber: publish or subscribe role on the specific topic/subscription.

Prefer workload identity: IAM roles, Azure Managed Identity/Workload Identity, or Google Workload Identity/Application Default Credentials. Never embed client secrets, service account keys, SAS tokens, or cloud access keys in payloads/headers/application source.

### 10.4. Tenant Boundaries and Header Spoofing Prevention

Do not take tenant ID from a message header as the sole authorization source. Authenticate the producer, verify claims/tenant mappings at the boundary, and attach the verified tenant context to the message. For multi-tenant queues/topics, decide on partitioning:

- Dedicated queues/topics per tenant or tenant group.
- Shared broker entity with tenant keys and application-level authorization.
- Partition/session/ordering keys by tenant when isolation/ordering is required.

Logs and metrics should not create unbounded cardinality from tenant IDs or message IDs. Mask or hash identifiers where appropriate; do not log payloads containing PII/payment data.

## 11. Testing Spring Integration Flows

### 11.1. Testing Flows with Internal Channels

You can test flows without a cloud broker using test channels. First, declare a pollable output channel so tests can receive messages:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
class ReservationTestFlowConfiguration {

    @Bean("reservation.test.output")
    QueueChannel reservationOutput() {
        return new QueueChannel(10);
    }

    @Bean("reservation.test.input")
    MessageChannel reservationTestInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow normalizeForTestFlow() {
        return IntegrationFlow.from("reservation.test.input")
                .transform(String.class, String::trim)
                .channel("reservation.test.output")
                .get();
    }
}
~~~

In the Spring context integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(ReservationTestFlowConfiguration.class)
class ReservationFlowTest {

    @Autowired
    @Qualifier("reservation.test.input")
    MessageChannel input;

    @Autowired
    @Qualifier("reservation.test.output")
    PollableChannel output;

    @Test
    void trimsIncomingPayload() {
        input.send(MessageBuilder.withPayload("  RES-1001  ").build());

        Message<?> result = output.receive(1000);

        assertThat(result).isNotNull();
        assertThat(result.getPayload()).isEqualTo("RES-1001");
    }
}
~~~

This test verifies actual flow wiring and transformations without a broker. Channel names in tests must match the declared channel beans/DSL flows. If a flow has multiple branches, add tests for each route, discard path, and error path.

### 11.2. Testing Endpoints with Mocks

Mock SDK clients or provider adapters to verify:

- Payload and header mapping are correct.
- Router selects the right channel.
- Filter discards invalid messages.
- Exceptions are classified accurately.
- Partial failures are handled per entry.
- Ack occurs only after the handler/transaction completes.
- Retries are bounded and permanent errors are not retried.
- Duplicate event IDs do not cause a second side effect.

Separate application service unit tests from IntegrationFlow wiring tests. Mocking broker APIs does not prove the real broker shares identical lock/visibility/ack semantics.

### 11.3. Broker Emulators and Contract Tests

LocalStack can support some AWS APIs such as SQS/SNS/EventBridge. Azure Service Bus and Google Pub/Sub offer emulators or local environments suited for certain use cases. Check the limits of each emulator: IAM, policies, ordering, DLQs, retries, and quotas may not behave identically to the real cloud.

Contract/staging tests should verify:

1. Workload identity is granted the right permissions.
2. Adapters receive the expected message envelope and metadata.
3. Ack/complete/delete executes after commit per policy.
4. Retry/redelivery and DLQs behave as expected.
5. Ordering/partitioning/sessions are configured properly.
6. Consumers deduplicate when the same event ID is resent.
7. Metrics and tracing maintain correlation across transport boundaries.

Do not run load tests or throttling experiments in production without a budget, concurrency caps, and a stop plan.

## 12. Observability and Operations

### 12.1. Tracing a Message Across a Flow

Every message should carry a correlation ID or trace context to link:

- Receipt from broker/API.
- Passing through transformers/routers/filters.
- Calling business services/databases.
- Publishing to the next broker or API.
- Ack/complete or dead-lettering.

Spring Integration can integrate with Micrometer Observation/metrics depending on the version. Verify actual instrumentation and propagate trace context through broker headers using the standard in use. Do not generate a fresh trace ID at each endpoint if you need to follow a single business operation.

### 12.2. Metrics to Monitor

| Metric | Meaning |
| --- | --- |
| Messages received/sent | Inbound/outbound throughput |
| Processing duration p50/p95/p99 | Latency per endpoint/use case |
| Queue depth / consumer lag | Whether backlog is growing or shrinking |
| In-flight / active handlers | Number of messages currently being processed |
| Retry count / redelivery count | Failing dependencies or overly aggressive policies |
| DLQ depth / oldest message age | Stuck messages needing investigation |
| Handler error rate by category | Distinguishing validation, permission, throttling, timeouts |
| Executor active/rejected tasks | Concurrency or internal queue saturation |

Do not watch total error counts alone. A queue with normal throughput but rising oldest message age can indicate consumers falling behind or a stuck partition.

### 12.3. Safe Logging and Runbooks

Logs should contain event ID, correlation ID, endpoint/flow name, broker entity, attempt count, duration, and error category. Do not log credentials, SAS/presigned URLs, sensitive raw payloads, or all message headers.

Runbooks should answer:

- When backlog rises, reduce receive concurrency or scale up workers?
- When throttled, where is publish rate limited?
- When the DLQ grows, how to inspect sample messages and classify errors?
- Who is authorized to replay and how is replay monitored?
- How to handle incompatible schema versions?
- How to pause/resume endpoints during a dependency outage?
- How to confirm zero message loss after deployment/restart?

## 13. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Message received multiple times | Ack failed, lock/visibility expired, or consumer crashed | Inbox/idempotency; tune lock/visibility and processing time |
| Message lost after restart | Acked after enqueueing to an in-memory channel | Persist before acking or keep flow synchronous through commit |
| Backlog steadily growing | Producer faster than consumer, slow downstream, or low concurrency | Monitor lag/latency, scale with bounds, and apply backpressure |
| Retry storm | SDK, Integration, and broker all retrying the same failure | Assign retry responsibility by layer, cap attempts, and add jitter |
| DLQ growing | Schema errors, permissions, poison messages, or target unavailable | Classify errors, fix root cause, replay with controls |
| Out-of-order messages | Multiple consumers/threads, wrong partition/session key | Choose ordering key and cap concurrency per group |
| Tenant processes wrong data | Trusting producer-sent tenant header | Authenticate identity and verify tenant mapping at boundary |
| Flow blocked | Synchronous handler calling slow API or thread pool exhausted | Timeouts, bulkheads, bounded executors, and intentional async boundaries |
| Aggregator holds messages too long | Release strategy unmet or missing timeout | Configure group timeout, reaper, capacity, and persistent store |
| Gateway times out but remote processed it | Reply delayed/lost after command executed | Idempotency key and queryable operation status |

## 14. Production Readiness Checklist

1. **Tool choice:** confirmed Spring Integration solves flow orchestration; would Stream/SDK/workflow engine fit better?
2. **Boundaries:** transport adapters, integration flows, and application/domain services have clear responsibilities.
3. **Message contract:** envelope, schema version, event ID, correlation ID, and tenant context are defined.
4. **Channel semantics:** sync/async, buffering, capacity, executors, and transaction context are well understood.
5. **Broker semantics:** ack, visibility/lock, ordering, redelivery, retention, and DLQ are configured per provider.
6. **Error policy:** permanent vs. transient errors distinguished, bounded retries, and documented quarantine procedures.
7. **Idempotency:** consumer inbox/deduplication protects side effects.
8. **Consistency:** outbox used when DB commits must accompany publish intent.
9. **Security:** workload identity and least privilege; no secrets in messages/headers/logs.
10. **Backpressure:** bounded queues, concurrency, timeouts, and rate limits.
11. **Testing:** unit, flow wiring, emulator, and staging contract tests.
12. **Operations:** metrics, tracing, alerts, DLQ replay, and runbooks.

## 15. Practice Exercises

1. For a use case receiving ReservationConfirmed from SQS, enriching data, and publishing to EventBridge, diagram the flow and delineate transport adapter, IntegrationFlow, and application service.
2. Write an IntegrationFlow using transformer, filter, router, and service activator; test each branch using QueueChannel.
3. Compare DirectChannel, QueueChannel, ExecutorChannel, and PublishSubscribeChannel across threading, buffering, failure propagation, and durability.
4. Refactor a direct-SDK call use case into a small adapter; identify when a flow needs enough endpoints for Spring Integration to add value.
5. Design a request/reply gateway with timeout, correlation ID, and handling for late-arriving replies.
6. Write a bridge for one provider broker; explain the exact point at which the message is acked/completed/deleted.
7. Design retry policies for throttling, timeouts, schema validation, and access denied; avoid multiplying attempts across layers.
8. Create an inbox table so the same event ID never triggers a side effect twice.
9. Add a transactional outbox for a use case writing to a database and emitting events; simulate a crash after publishing but before marking published.
10. Compare SQS, Azure Service Bus, and Pub/Sub on ack, redelivery, ordering, DLQ, and identity; show which parts of the flow can be shared and which are provider-specific.

**Completion criteria:** learners can select Spring Integration for appropriate message flow orchestration problems, build Java DSL flows with clear channels/endpoints, connect at least one cloud broker via an adapter, handle ack/retry/DLQ/idempotency with proper semantics, and test the flow end-to-end.

## References

- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): messages, channels, endpoints, Java DSL, error handling, and adapters.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): declaring IntegrationFlow in Java.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel types and semantics.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply and gateways.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): error channels and exception flows.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): binders, functional model, consumer groups, and partitioning.
- [Spring Cloud AWS Reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): AWS integration by version.
- [Azure Spring documentation](https://learn.microsoft.com/azure/developer/java/spring-framework/): Spring integration with Azure services.
- [Google Cloud Spring documentation](https://cloud.google.com/java/docs/spring): Spring integration with Google Cloud.
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): dual-write and duplicate delivery.
