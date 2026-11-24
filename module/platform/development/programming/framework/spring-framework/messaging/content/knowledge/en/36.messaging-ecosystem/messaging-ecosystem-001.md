# Spring Integration and Message-Based Integration Patterns

> Scope: Spring Integration 7.1.1, Spring Messaging, and Java 17+. This lesson explains how to compose message components into an integration flow, the roles of channels, endpoints, adapters, and gateways, along with commonly used Enterprise Integration Patterns (EIP) in Spring applications.

## 1. What problem does Spring Integration solve?

An enterprise application often has to exchange data with many systems: REST APIs, file servers, databases, email, JMS, RabbitMQ, Kafka, MQTT, or an internal service. If each place calls the next directly, business logic gets mixed with protocols, retries, data transformation, routing, and error management.

Spring Integration provides a messaging model to connect those systems using small components that can be composed into a message flow. The sender creates a message and puts it into a channel; an endpoint receives the message and processes, transforms, or routes it; adapters and gateways connect the flow to external systems.

The library implements many Enterprise Integration Patterns. Instead of manually writing polling loops, queues, routers, splitters, or correlation mechanisms for each project, you configure built-in components and focus on business rules.

A simple flow can look like this:

~~~text
File/HTTP/Broker
      |
Inbound Adapter or Gateway
      |
   MessageChannel
      |
  Transformer
      |
    Filter
      |
    Router
   /      \
Service   Service
Activator Activator
   \      /
   Reply/Outbound Gateway
      |
External system or caller
~~~

Spring Integration is not a message broker. Channels such as DirectChannel or QueueChannel usually reside in the application's memory. When durable communication across processes is needed, use an adapter/gateway to connect to an appropriate broker or storage system. An in-application channel is a connection point between components; a broker is external infrastructure for transporting and storing messages.

## 2. Three core abstractions: Message, MessageChannel, and MessageHandler

### 2.1. Message is the unit of data transmitted

Spring Messaging defines the `Message<T>` interface with two parts:

- `payload`: the main content, usually a DTO, record, string, byte array, or domain object.
- `headers`: metadata such as ID, timestamp, content type, correlation ID, reply channel, error channel, or routing information.

You can create a message using `MessageBuilder`:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001", 125000))
    .setHeader("eventType", "order.created")
    .setHeader("tenantId", "tenant-42")
    .build();
~~~

Headers are metadata and should not be used to replace business data that consumers need to store or interpret long-term. Some headers have internal meaning in Spring, such as `replyChannel` and `errorChannel`; adapters may map or strip headers when crossing external protocols.

`MessageHeaders` is an immutable structure once the message is created. The payload is not automatically immutable: if the payload is a mutable object and multiple consumers share that object, modifying its contents can cause unpredictable side effects. Immutable DTOs/records are generally more suitable.

Spring can automatically generate `id` and `timestamp` for each message instance. This is metadata for the Spring Message instance, not necessarily a durable business event ID. If you need deduplication across retries or broker redeliveries, put a separate business event ID in the payload or a designated header and ensure it is preserved across redeliveries.

### 2.2. MessageChannel decouples producer from consumer

`MessageChannel` is the point where messages are sent. The producer only needs to know the target channel, without needing to know which specific handler will receive the message. Consumers register with the channel and can be changed without forcing the producer to change.

The basic method is `send(Message<?>)`, which returns a boolean indicating whether the message was accepted for sending. Some channels support `send(message, timeout)` to limit the wait time when the channel is full or needs to synchronize with a consumer.

A channel is not necessarily a queue. A channel can dispatch synchronously to a subscriber, broadcast to multiple subscribers, or store messages for a consumer to poll later.

### 2.3. MessageHandler performs the work

`MessageHandler` receives a message and processes it. In applications, you typically do not need to implement this interface yourself. Service activators, transformers, filters, routers, splitters, and aggregators are specialized endpoints/handlers for each purpose.

An endpoint connects a handler to an input channel and can connect to an output channel. Endpoints also manage lifecycle, pollers, interceptors, and advice according to configuration.

Distinguish the three roles:

| Component | Responsibility |
|---|---|
| Message | Encapsulates payload and headers |
| MessageChannel | Transfers messages from producer to consumer |
| Endpoint/MessageHandler | Receives messages and processes or forwards them |

## 3. Types of MessageChannel and how to choose

Channel choice affects ordering, threading, buffering, backpressure, and the risk of message loss.

| Channel | How it works | When to use |
|---|---|---|
| `DirectChannel` | Point-to-point; dispatches synchronously on the sender's thread | Internal flows needing simplicity, immediate response, and potentially sharing the same transaction thread |
| `PublishSubscribeChannel` | Sends a message to all subscribers | Fan-out, updating multiple projections or multiple listeners |
| `QueueChannel` | Stores messages in a queue; consumers call `receive` or use a poller | Decoupling send and receive times, in-memory buffering |
| `PriorityChannel` | Pollable queue with priority ordering | Processing messages by priority header |
| `RendezvousChannel` | Direct handoff between sender and receiver; sender may have to wait | Synchronizing producer and consumer with a handshake mechanism |
| `ExecutorChannel` | Dispatches via an executor, usually to another thread | Decoupling processing from the sender thread and increasing concurrency |
| `FluxMessageChannel` | Reactive Streams-based channel | Flows needing integration with reactive Publishers/Subscribers |

`DirectChannel` is a common default choice in synchronous flows. If there are multiple subscribers, it selects one subscriber to process the message; it does not broadcast like `PublishSubscribeChannel`.

`PublishSubscribeChannel` has fan-out semantics. If one subscriber fails, you need to determine the error-handling policy and delivery to the remaining subscribers based on the dispatcher configuration. Do not assume that publish-subscribe automatically creates durable copies for each consumer.

`QueueChannel` decouples sender and receiver in time, but an in-memory queue is not a durable queue. If the process stops, unprocessed messages can be lost. Appropriate capacity, timeout, poller, and overflow strategies are needed.

`ExecutorChannel` creates an asynchronous boundary. Because processing can run on another thread, do not assume transactions or ThreadLocals from the sending thread are automatically propagated to the processing thread. You must manage the executor, queue, and rejection policy; do not let the backlog grow unbounded.

### 3.1. SubscribableChannel and PollableChannel

Two interface groups help identify how consumers obtain messages:

- `SubscribableChannel`: consumers register a handler; the channel pushes messages to subscribers when a message arrives.
- `PollableChannel`: consumers actively call `receive()`; a poller can be used to fetch messages on a schedule.

`DirectChannel`, `PublishSubscribeChannel`, and `ExecutorChannel` belong to the subscribable group. `QueueChannel`, `PriorityChannel`, and `RendezvousChannel` belong to the pollable group.

Do not attach a poller to a push channel such as `DirectChannel`. A poller is appropriate for a `MessageSource` or a `PollableChannel`, such as periodically checking a directory or reading a queue.

## 4. Endpoints, Channel Adapters, and Gateways

### 4.1. Message endpoint

An endpoint is the component that connects processing logic to a channel. It can invoke a service, transform a payload, filter messages, route, split messages, or aggregate results.

Common annotations:

- `@ServiceActivator`: invokes a business processing method.
- `@Transformer`: transforms a payload or message.
- `@Filter`: decides whether a message continues forward.
- `@Router`: selects target channels.
- `@Splitter`: splits one message into multiple sub-messages.
- `@Aggregator`: combines a group of messages into a result.
- `@BridgeFrom` / `@BridgeTo`: connects channels in appropriate configurations.

These endpoints can be declared via annotations, XML, or Java DSL.

### 4.2. Channel adapter: one-way integration

A channel adapter connects an external source/destination with an in-application channel in one direction:

- Inbound channel adapter reads from outside and sends messages into the flow.
- Outbound channel adapter receives messages from the flow and sends them outside.

For example: an inbound file adapter reads a CSV file and emits messages; an outbound file adapter writes payloads to files. An adapter does not require a business reply for each message.

### 4.3. Gateway: request-reply

A gateway is appropriate when the caller needs to send a request and wait for a reply. A gateway hides messaging details, allowing the application to call a Java interface like calling a normal service.

A messaging gateway can be declared with `@MessagingGateway`, with methods annotated with `@Gateway` to specify the request channel, reply channel, or timeout. An outbound gateway connects the flow to an external system in a request/reply model; an inbound gateway receives requests from an external system and sends back a reply.

Do not confuse a gateway with an adapter: an adapter mainly sends/receives one-way, whereas a gateway has a request/reply contract. A gateway also does not automatically guarantee that an external operation is atomic with the application's database transaction.

### 4.4. Messaging Bridge

A bridge forwards messages from one channel to another without changing the payload according to business logic. It is useful for connecting two flows, bridging between channels with different dispatch policies, or creating a connection point between modules.

## 5. Important Enterprise Integration Patterns

Spring Integration implements many EIPs. Each pattern solves a specific problem; do not add a pattern just because it is available in the framework.

### 5.1. Service Activator: invoking business logic

A service activator connects a Spring-managed bean to an input channel. The method receives the payload or the entire `Message<?>`; if the method returns a value, the framework can create a reply message and send it to the output channel or the request's `replyChannel`.

~~~java
@Service
public class OrderService {

    @ServiceActivator(inputChannel = "orders.toProcess")
    public OrderAccepted process(OrderCommand command) {
        return new OrderAccepted(command.orderId(), "ACCEPTED");
    }
}
~~~

In Java DSL, `.handle(...)` represents a service activator. Use a service activator for business logic such as validating orders, calling domain services, or writing data. Avoid putting too many business rules into SpEL or configuration lambdas that are hard to test.

### 5.2. Transformer: changing data format

A transformer changes the payload or message structure so the next component works with an appropriate format.

Examples:

- CSV row into `OrderCommand`.
- XML into a DTO.
- Date-time string into `Instant`.
- Normalizing field names or units of measurement.
- Adding necessary data using a content enricher.

A transformer should not decide on its own whether a message is allowed to be processed; that is the responsibility of a filter or service/domain validation.

### 5.3. Filter: allowing or blocking messages

A filter evaluates a boolean condition. If the message satisfies the condition, it moves forward; otherwise, it is dropped from the main flow. A discard channel can be configured to send rejected messages to a separate flow, such as audit or quarantine.

Filters are suitable for simple conditions such as dropping empty messages, filtering out irrelevant event types, or passing only messages with an appropriate status. Security conditions or critical invariants must still be checked at the server/domain boundary, not relying on a filter as the sole authorization mechanism.

### 5.4. Router: choosing where to process

A router selects one or more channels based on payload, headers, or routing rules. Examples:

- Orders by region are sent to that region's channel.
- Messages by event type are sent to the corresponding handler.
- High-priority commands go to a dedicated worker.

You need to define behavior when no route is found: default channel, fallback route, routing error, or quarantine. Do not let messages disappear silently when a route key is wrong.

Example of an annotation router returning a channel name:

~~~java
@Router(inputChannel = "orders.in")
public String route(OrderCommand command) {
    return switch (command.region()) {
        case "VN" -> "orders.vn";
        case "SG" -> "orders.sg";
        default -> "orders.review";
    };
}
~~~

Channel names must exist or be resolved according to configuration. Tests should cover each branch and unrecognized values.

### 5.5. Splitter and Aggregator: splitting then combining

A splitter turns one message containing multiple elements into multiple sub-messages. For example, an order batch containing multiple order lines can be split into separate messages for parallel processing.

Splitters/aggregators typically use sequence and correlation headers:

- `correlationId`: identifies sub-messages belonging to the same group.
- `sequenceNumber`: the order of the message within the group.
- `sequenceSize`: the expected number of elements in the group.

An aggregator holds messages by correlation group, then emits the result when the release strategy indicates the group meets the criteria. Criteria can be receiving enough messages, meeting a business predicate, or reaching a timeout. A message store holds group state; for applications that need recovery after restart or scaling across multiple instances, consider a persistent MessageStore and a cleanup strategy.

You must design for late, missing, duplicate, or out-of-order messages. If an aggregator waits indefinitely for a message that never arrives, the group can hold resources. Timeouts, expiry, discard/recovery, and metrics for stuck groups are needed.

### 5.6. Resequencer

A resequencer holds messages in a group and emits them in sequence number order, useful when parallel upstream processing causes results to arrive out of order. A resequencer differs from an aggregator: it reorders and emits each message individually, whereas an aggregator creates one result from the entire group.

### 5.7. Scatter-Gather

Scatter-Gather sends a request to multiple recipients and then gathers responses. For example, querying prices from multiple suppliers simultaneously and aggregating quotes. You need to define a timeout, minimum number of responses, per-recipient error handling, and completion criteria. Do not wait indefinitely for every recipient if one system may not respond.

### 5.8. Content Enricher and Claim Check

A content enricher supplements a message with additional data, such as fetching customer information from a CRM before sending an order to the fulfillment system.

Claim check stores a large payload or data that does not need to pass through every step into a storage repository, replacing it with a token/claim so a later flow step can retrieve it when needed. Access control, time-to-live, and cleanup of stored data must be managed; a claim token should not become an unrestricted public URL or access grant.

### 5.9. Wire Tap

A Wire Tap sends a copy of a message to a secondary channel for observation, auditing, or metrics without altering the main flow. Do not use a wire tap to perform mandatory business side effects without appropriate delivery guarantees. Sensitive data must be masked before being sent to log/audit flows.

## 6. Composing flows with Java DSL

Java DSL provides a fluent API to define an `IntegrationFlow` as sequential steps. Common operators:

- `from(...)`: starting point from a channel, source, or endpoint.
- `filter(...)`: drops messages that do not meet a condition.
- `transform(...)`: changes payload/message.
- `route(...)`: routes messages.
- `split(...)`: splits messages.
- `aggregate(...)`: aggregates messages.
- `handle(...)`: invokes a service activator.
- `channel(...)`: sends the result to the specified channel.
- `gateway(...)`: calls another flow in request/reply style.
- `log()` and `wireTap(...)`: observes or sends copies.

Endpoints in a Java DSL flow are by default implicitly connected by a `DirectChannel`. Channels can be explicitly specified to separate modules or connect with adapters. An `IntegrationFlow` is not an inseparable processing block; named channels can serve as entry/exit points used by other components.

### 6.1. Standalone Java 17 example

The example below creates a flow that receives order strings, drops blank strings, normalizes by trimming and uppercasing, and passes to the final handler. This is a single-process demo; it does not connect to a broker or database yet.

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-integration-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>7.1.1</version>
        </dependency>
    </dependencies>
</project>
~~~

**IntegrationDemo.java**:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;

public class IntegrationDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(FlowConfiguration.class)) {

            MessageChannel input =
                context.getBean("ordersInput", MessageChannel.class);

            input.send(new GenericMessage<>("  order-42  "));
            input.send(new GenericMessage<>("   "));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableIntegration
    static class FlowConfiguration {

        @Bean
        MessageChannel ordersInput() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow orderFlow() {
            return IntegrationFlow.from("ordersInput")
                .<String>filter(payload -> !payload.isBlank())
                .<String, String>transform(String::trim)
                .<String, String>transform(String::toUpperCase)
                .handle(System.out::println)
                .get();
        }
    }
}
~~~

Run from the directory containing `pom.xml` and `IntegrationDemo.java`.

Linux/macOS:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=cp.txt
javac -cp "$(cat cp.txt)" IntegrationDemo.java
java -cp ".:$(cat cp.txt)" IntegrationDemo
~~~

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=cp.txt"
$cp = (Get-Content .\cp.txt -Raw).Trim()
javac -cp $cp .\IntegrationDemo.java
java -cp ".;$cp" IntegrationDemo
~~~

Output:

~~~text
ORDER-42
~~~

The first message passes through the filter, is trimmed, uppercased, and printed. The second message is a whitespace string, so the filter stops it from continuing; the flow does not print a second line.

`DirectChannel` dispatches synchronously, so the handler runs on the sending thread. When a flow has slow I/O or needs asynchronous processing, consider an appropriate channel/executor and set concurrency/backlog limits rather than offloading every step to a thread pool by default.

## 7. Pollers and MessageSource

Not every data source pushes messages to the application. File systems, database queries, or some APIs need to be polled. `MessageSource<T>` creates messages when asked; a poller determines when an endpoint calls the source.

A poller can be configured by:

- fixed delay or fixed rate;
- cron;
- maximum number of messages per poll (`maxMessagesPerPoll`);
- receive timeout;
- transaction advice or error handling.

Do not poll too aggressively when the data source cannot keep up. Consider system load, processing time, message backlog, and the possibility of multiple instances polling the same source simultaneously.

When multiple instances read from a shared source, a lock/claim or partitioning mechanism is needed to avoid processing the same record/file concurrently. A poller does not automatically guarantee that a message is processed exactly once.

## 8. Error handling, retry, and dead-letter

Errors can occur in many places: payload decoding, transformers, routers, service activators, adapters, or external systems.

In Spring Integration:

- Errors in a synchronous flow such as `DirectChannel` can usually propagate back to the sending thread.
- With pollers or asynchronous processing, errors can be wrapped as an `ErrorMessage` and sent to the message's error channel or the default error channel when appropriately configured.
- Retry/recovery advice can be attached to an endpoint.
- An error flow can classify errors, record metadata, send to a dead-letter destination, or alert operations.

Do not retry all errors the same way:

- Transient errors such as timeouts or intermittent connection drops can be retried with bounded attempts and backoff.
- Data errors such as invalid schemas or missing required fields usually need quarantine/dead-lettering, not continuous retrying.
- Authorization errors should generally not become infinite retries.
- Business errors such as a cancelled order must be handled according to domain rules.

Retries can cause repeated side effects if a handler is not idempotent. For write operations, use an idempotency key, transaction, unique constraint, or inbox/outbox pattern depending on architecture. Limit retries, record attempt counts, and retain enough information for investigation without logging secrets or full sensitive payloads.

A dead-letter destination is not a trash bin. Retention policies, access controls, controlled replay, alerting, and procedures to fix data before resending are needed.

## 9. Transactions and reliability

Transactions can be attached to endpoints/pollers using transaction advice. With `DirectChannel`, steps running on the same thread can participate in a thread-bound transaction if using the same transaction manager and compatible resources.

When using `ExecutorChannel`, queues, or brokers, the processing flow can cross thread/process boundaries. Do not assume a local database transaction covers the entire message flow. Sending a message to a broker and committing a database are two separate side effects unless an appropriate integrated transaction mechanism is used.

Common strategies:

- **Transactional outbox**: write business data and an outbox record in the same transaction; a publisher reads the outbox and sends the message.
- **Idempotent consumer/inbox**: record processed messages in the same transaction as business updates.
- **Retry + backoff**: recover from transient errors with limits.
- **Compensation/Saga**: undo business work via compensating actions when an atomic distributed transaction is not possible.
- **Durable broker**: persist messages and acknowledgements according to transport semantics.

Delivery semantics must be clearly defined: at-most-once, at-least-once, or another mechanism provided by the broker/adapter. Do not claim exactly-once simply because a flow has transactions or message IDs.

## 10. Reactive Streams and Spring Integration

Spring Integration supports Reactive Streams, including channels and endpoints that work with `Publisher`. This helps connect flows with Reactor and reactive APIs.

Reactive flows have demand/backpressure; traditional channels do not automatically become reactive just because a handler returns a `Flux` or `Mono`. Choose the right reactive channel/endpoint and understand when the framework subscribes to a publisher, how errors are propagated, and the subscription lifecycle.

Do not manually call `subscribe()` inside a service activator just to run side effects and ignore the publisher. Return the publisher to the framework when the API/endpoint supports reactive return types. If a flow segment uses blocking I/O, arrange an appropriate scheduler/executor and set concurrency limits.

## 11. Observing and managing flows

When a system has many flows, you need to know which endpoints and channels messages pass through and where bottlenecks occur.

Spring Integration provides capabilities such as:

- Message history to record the components a message has traversed when enabled.
- Metrics and Micrometer instrumentation for throughput, send/receive, errors, and processing time per endpoint.
- Integration Graph to inspect components and connections.
- Logging channel adapters or wire taps to observe flows.
- JMX/management endpoints and control bus for management when configured.

Log message ID, correlation ID, event type, route, and error category. Mask personal data, tokens, and sensitive payloads. Do not enable full payload logging in production without a data protection policy.

## 12. Testing Spring Integration flows

### 12.1. Unit testing handlers

Test services/transformers/filters/routers separately as regular Java methods when logic does not depend on the framework. This is fast and helps isolate business bugs.

### 12.2. Testing flows with QueueChannel

You can use a `QueueChannel` as output in tests to send messages into the input and deterministically read replies:

~~~java
@SpringJUnitConfig(FlowTestConfiguration.class)
class OrderFlowTests {

    @Autowired
    @Qualifier("ordersInput")
    MessageChannel input;

    @Autowired
    @Qualifier("ordersOutput")
    PollableChannel output;

    @Test
    void trimsAndUppercasesOrderId() {
        input.send(new GenericMessage<>("  order-42  "));

        Message<?> result = output.receive(1000);

        assertNotNull(result);
        assertEquals("ORDER-42", result.getPayload());
    }
}
~~~

The test configuration can define `ordersInput` as a `DirectChannel`, `ordersOutput` as a `QueueChannel`, and wire the flow with `.transform(String::trim)`, `.transform(String::toUpperCase)`, and `.channel("ordersOutput")`. The queue output lets tests fetch replies via `receive(timeout)` without mocking the entire framework.

### 12.3. Spring Integration Test module

The `spring-integration-test` dependency provides `@SpringIntegrationTest`, `MockIntegrationContext`, `MockIntegration`, and `MockMessageHandler`.

Use `@SpringIntegrationTest(noAutoStartup = ...)` to prevent real inbound adapters from auto-starting in tests, such as adapters connecting to brokers, file servers, or databases. Then use `MockIntegrationContext` to replace a MessageSource or MessageHandler with a mock, and call `resetBeans()` to restore endpoints after the test.

`MockIntegration.mockMessageSource(...)` creates a test source; `MockMessageHandler` allows stubbing one-way or request-reply behavior and capturing incoming messages. These utilities help verify flows without connecting to external systems in every unit/integration test.

### 12.4. Recommended test matrix

- Valid payloads pass through the right transformers and handlers.
- Filters drop messages that do not meet conditions; the discard channel receives the right messages if configured.
- Routers select the right channel for each route key; unrecognized routes follow the fallback.
- Splitters create the expected number of sub-messages, sequences, and correlations.
- Aggregators release when enough messages arrive; timeouts/missing messages are handled.
- Gateways return proper replies or time out according to contract.
- Pollers do not process duplicates when multiple instances run concurrently.
- Handler errors are routed to the error flow or returned to the caller properly.
- Retries do not cause duplicate side effects.
- Shutdown/restart does not lose durable messages according to committed semantics.

Integration tests with a real broker/file server should run at an appropriate CI stage or with test containers. Mocks cannot prove production broker configuration for serialization, acknowledgement, reconnect, transactions, or delivery semantics.

## 13. Common design mistakes

1. **Treating channels as durable brokers.** In-memory DirectChannel and QueueChannel do not provide durability when the process stops.
2. **Using the wrong channel type.** Needing broadcast but using DirectChannel; needing buffering but using a synchronous channel.
3. **Not setting capacity or timeout.** Queues/backlogs can grow, producers can block, or messages can be rejected.
4. **Confusing adapters with gateways.** One-way adapters have no reply contract; gateways serve request/reply.
5. **Routers without fallback.** Messages with unknown route keys may fail or be dropped unexpectedly depending on configuration.
6. **Using filters as a security mechanism.** Filters do not replace authentication/authorization and domain checks.
7. **Aggregators without timeout/expiry.** Groups missing messages can retain memory/store indefinitely.
8. **Infinite retries.** Failing systems can be overloaded further and dead-letters go unhandled.
9. **Assuming transactions across executors/brokers.** Thread/process boundaries break many local transaction assumptions.
10. **Manually subscribing to reactive publishers.** The framework no longer manages lifecycle, errors, and backpressure as expected.
11. **Logging entire messages.** Can leak tokens, personal data, or sensitive business information.
12. **Testing only handlers without testing flows.** Channel mapping, poller, routing, header, or adapter bugs only surface during integration.

## 14. Process for choosing patterns for a problem

When designing a new flow, describe the data path first and then choose patterns:

1. Where does data come from and where does it go? Choose inbound/outbound adapters or gateways.
2. Does the caller need a reply? Choose a one-way adapter or a request/reply gateway.
3. Should steps run synchronously, broadcast, buffered, or asynchronously? Choose the channel.
4. Does the payload need normalization? Use a transformer.
5. Do messages need to be filtered out? Use a filter and define discard behavior.
6. Are there multiple processing destinations? Use a router and fallback.
7. Does a single message contain multiple units of work? Use a splitter; if a combined result is needed, join with an aggregator.
8. Is ordering required? Use a resequencer or transport-level partitioning/order semantics.
9. How are transient and permanent errors handled? Define retries, error flows, and dead-lettering.
10. Can messages be sent repeatedly or processes restart? Design idempotency, durable storage, and transaction boundaries.
11. What needs to be observed? Enable metrics, message history, or wire taps with data protection policies.
12. Are both logic and transport tested? Use unit, flow, and integration tests accordingly.

A good flow is a composition of steps with clear responsibilities. Each pattern should solve a specific requirement, and channels/endpoints should be chosen according to semantics of dispatch, durability, threading, transactions, and failure handling.

## References

- [Spring Integration Reference — 7.1.1](https://docs.spring.io/spring-integration/reference/index.html): official documentation on core messaging, EIP, Java DSL, adapters, gateways, and reactive support.
- [Core Messaging](https://docs.spring.io/spring-integration/reference/core.html): MessageChannel, pollers, channel adapters, and messaging bridges.
- [Message Routing](https://docs.spring.io/spring-integration/reference/message-routing.html): routers, filters, splitters, aggregators, resequencers, and scatter-gather.
- [Message Transformation](https://docs.spring.io/spring-integration/reference/message-transformation.html): transformers, content enrichers, claim checks, and codecs.
- [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): endpoints invoking Spring-managed services and reply channels.
- [Java DSL — Working With Message Flows](https://docs.spring.io/spring-integration/reference/dsl/java-flows.html): how to build IntegrationFlow and connect channels.
- [Testing support](https://docs.spring.io/spring-integration/reference/testing.html): SpringIntegrationTest, MockIntegrationContext, and integration mocks.
- [Spring Integration project](https://spring.io/projects/spring-integration): project overview, adapters, gateways, and supported patterns.
