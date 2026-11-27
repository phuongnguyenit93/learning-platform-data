# Choosing input-channel and output-channel

## 1. Why Does Channel Selection Matter?

In Spring Integration, adapters and endpoints exchange data through `MessageChannel` beans. A message carries a **payload** containing business data and **headers** holding metadata such as correlation IDs, source information, `replyChannel`, or `errorChannel`. When building an integration flow, the sender needs to know **which channel to send to**, while the receiver needs to know **which channel to read from**.

The **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module focuses on wiring those components into a processing pipeline. In this module, a system may use inbound/outbound adapters, gateways, pollers, and `MessageChannel` to integrate files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while controlling message contracts, errors, and connection lifecycles. Configuring `input-channel` and `output-channel` accurately is the foundation for every pipeline to work.

For example, a file inbound adapter emits `Message<File>` to `files.received`. A service activator listening on `orders.validated` **will not automatically receive** messages from `files.received` simply because both live in the same application context. An intermediate endpoint must transfer messages between those two channels, or the topology must be adjusted so channel names match.

After this lesson, learners will be able to:

- Distinguish an **endpoint's input-channel** from an **endpoint's output-channel** and explain why the same channel can be the output of one component and the input of the next.
- Select appropriate channels for inbound adapters, outbound adapters, transformers, filters, service activators, bridges, and gateways.
- Declare, connect, and name channels using the Java DSL, annotations, or XML namespaces.
- Design multi-stage flows where messages preserve the right payload and headers at each step.
- Distinguish `outputChannel` from `replyChannel` in request–reply flows.
- Understand how channel types affect threading, pollers, transactions, timeouts, and load handling.
- Test channel wiring and diagnose causes of lost messages, timeouts, or uninvoked consumers.

**Rule of thumb:** "input" and "output" are defined **relative to each endpoint**, not as fixed properties of a channel. A channel sitting between two endpoints is simultaneously the **output of the upstream endpoint** and the **input of the downstream endpoint**.

## 2. The Producer → Channel → Consumer Model

~~~mermaid
flowchart LR
    SRC["Inbound adapter<br/>producer"]
    CH1["files.received<br/>MessageChannel"]
    TRANS["Transformer<br/>consumer + producer"]
    CH2["orders.validated<br/>MessageChannel"]
    HAND["Service activator<br/>consumer + producer"]
    CH3["orders.accepted<br/>MessageChannel"]
    SINK["Outbound handler<br/>consumer"]
    SRC -->|"output"| CH1
    CH1 -->|"input"| TRANS
    TRANS -->|"output"| CH2
    CH2 -->|"input"| HAND
    HAND -->|"output"| CH3
    CH3 -->|"input"| SINK
~~~

Each channel is a message handoff boundary. In the diagram:

- The inbound adapter is a **producer**: it reads external data and emits messages into a channel.
- The transformer is both a **consumer** of its input channel and a **producer** to its output channel after converting the payload.
- The service activator can purely **consume** messages to perform a side effect, or **return a value** to produce a reply and continue the flow.
- The outbound adapter is typically a **consumer**: it receives messages and dispatches data outside the system.

For example, a processing endpoint configured as:

~~~text
input-channel  = orders.validated
output-channel = orders.accepted
~~~

means the endpoint **receives** from `orders.validated` and, **if it produces a result message**, sends it to `orders.accepted`. Setting an output channel does not force a reply on its own: a `void` method or a handler returning `null` typically emits no new downstream message.

### 2.1. Channel Selection Table by Endpoint Type

| Component | Channel Used to Receive | Channel Used to Emit | Notes |
| --- | --- | --- | --- |
| Inbound adapter | No internal input channel because data comes from outside. | `channel` or equivalent attribute, e.g. `files.received`. | Polling sources require a poller. |
| Outbound adapter | `input-channel` or receiving channel. | Usually no business reply/output channel. | Acts as a one-way terminal point. |
| Transformer | `input-channel`. | `output-channel` when downstream stages follow. | Produces a new payload/message. |
| Filter | `input-channel`. | `output-channel` for accepted messages. | Can optionally configure a discard channel for rejected messages. |
| Router | `input-channel`. | Selects one or more target channels by rule. | Does not have a single fixed output in all setups. |
| Service activator | `input-channel`. | `output-channel` when a reply must continue onward. | `void` methods typically end one-way flows. |
| Bridge | `input-channel`. | `output-channel`. | Forwards messages to another channel without business changes. |
| Messaging gateway | `request-channel` or `defaultRequestChannel`. | Replies from the flow return via request `replyChannel` or configured reply channel. | Separates caller requests from replies. |

Attribute names vary across annotations, the Java DSL, and XML. What matters is understanding **message direction**, then looking up the exact endpoint attribute name in your chosen configuration style.

## 3. Channel Naming and Bean Resolution in the Spring Context

A channel is commonly registered as a bean. In Java configuration:

~~~java
@Bean(name = "orders.inbound")
MessageChannel ordersInbound() {
    return new DirectChannel();
}

@Bean(name = "orders.validated")
MessageChannel ordersValidated() {
    return new DirectChannel();
}

@Bean(name = "orders.accepted")
MessageChannel ordersAccepted() {
    return new DirectChannel();
}
~~~

The name inside `@Bean(name = "...")` is the channel name endpoints reference. `orders.inbound` is distinct from `order.inbound`, `orders.input`, or `orders.validated`. Names should reflect the **message type or processing stage** at that boundary.

| Suggested Name | Practical Meaning | Expected Payload |
| --- | --- | --- |
| `files.detected` | File adapter just detected a matching file. | `File`. |
| `orders.raw` | Unnormalized order data. | `RawOrder` or raw source content. |
| `orders.validated` | Orders that passed validation and mapping. | `ValidatedOrder`. |
| `orders.accepted` | Acceptance result awaiting the next handler. | `OrderReceipt`. |
| `payments.toBroker` | Payment command handed to a broker outbound adapter. | `PaymentEvent`. |
| `integration.errors` | Destination for error messages under configured error policy. | `ErrorMessage` or business error DTO. |

Not every channel needs to be declared as an explicit standalone bean: the Java DSL can create **implicit channels** between endpoints. However, when linking two independent flows, supporting multiple producers/consumers, or observing a specific boundary, explicitly named channels are easier to inspect and maintain.

**Do not assume same name implies same type.** Two producers sending to the same channel with `File` and `OrderEvent` payloads will break a consumer expecting one type. Channel contracts must define the payload and headers respected by both producers and consumers.

## 4. Complete Example: Choosing input-channel and output-channel with Java DSL and Annotations

Problem: an application receives `IncomingOrder` from Java code, validates it, maps it to `ValidatedOrder`, calls an approval service, and delivers `OrderReceipt` to a result-recording handler.

The flow is split across three connection points:

~~~text
orders.inbound
    → filter/transform (IntegrationFlow)
    → orders.validated
    → @ServiceActivator (returns OrderReceipt)
    → orders.accepted
    → @ServiceActivator (void, terminal)
~~~

Both `@ServiceActivator` methods live in the same application but use **different input channels**, so each handler only receives messages for its assigned stage.

### 4.1. Dependency

The example uses Java 17+, Spring Boot, and Spring Integration with Boot-managed dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

### 4.2. Configuration and Runnable Code

Place the code below in `ChannelSelectionApplication.java` under package `demo.channels`. Supporting records and components are package-private to keep the example concise in a single file.

~~~java
package demo.channels;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.MessageRejectedException;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
public class ChannelSelectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ChannelSelectionApplication.class, args);
    }

    @Bean(name = "orders.inbound")
    MessageChannel ordersInbound() {
        return new DirectChannel();
    }

    @Bean(name = "orders.validated")
    MessageChannel ordersValidated() {
        return new DirectChannel();
    }

    @Bean(name = "orders.accepted")
    MessageChannel ordersAccepted() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow validateOrderFlow() {
        return IntegrationFlow.from("orders.inbound")
                .filter(IncomingOrder.class,
                        order -> order.id() != null
                                && !order.id().isBlank()
                                && order.quantity() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(IncomingOrder.class,
                        order -> new ValidatedOrder(
                                order.id().trim(), order.quantity()))
                .channel("orders.validated")
                .get();
    }

    @Bean
    ApplicationRunner sample(
            @Qualifier("orders.inbound") MessageChannel inbound) {
        return args -> inbound.send(
                MessageBuilder.withPayload(
                                new IncomingOrder("ORD-1001", 3))
                        .setHeader("correlationId", "trace-1001")
                        .build());
    }
}

record IncomingOrder(String id, int quantity) {}

record ValidatedOrder(String id, int quantity) {}

record OrderReceipt(String orderId, String status) {}

@Component
class OrderApprovalService {

    @ServiceActivator(
            inputChannel = "orders.validated",
            outputChannel = "orders.accepted")
    public OrderReceipt approve(ValidatedOrder order) {
        return new OrderReceipt(order.id(), "ACCEPTED");
    }
}

@Component
class ReceiptSink {

    private final List<OrderReceipt> receipts =
            new CopyOnWriteArrayList<>();

    @ServiceActivator(inputChannel = "orders.accepted")
    public void capture(OrderReceipt receipt) {
        receipts.add(receipt);
        System.out.println("Receipt: " + receipt);
    }

    public List<OrderReceipt> snapshot() {
        return List.copyOf(receipts);
    }

    public void clear() {
        receipts.clear();
    }
}
~~~

`@EnableIntegration` enables Spring Integration processing in the example. `@SpringBootApplication` manages configuration and component scanning for classes in the application package. `@ServiceActivator` handlers are registered by the framework as consumers on their respective channels.

### 4.3. Inspecting Both Channel Transitions Carefully

**First transition:** the Java DSL reads from `orders.inbound`, filters and transforms, and forwards the `ValidatedOrder` payload to `orders.validated`:

~~~java
IntegrationFlow.from("orders.inbound")
        .filter(IncomingOrder.class,
                order -> order.quantity() > 0)
        .transform(IncomingOrder.class,
                order -> new ValidatedOrder(
                        order.id(), order.quantity()))
        .channel("orders.validated")
        .get();
~~~

This is an abbreviated snippet highlighting **channel direction**; in the full app above, the filter also validates `id`. `from("orders.inbound")` picks the flow's **input**. `.channel("orders.validated")` picks the **output** at the end of the transform stage. If additional processing is needed in the same flow, you can chain more DSL steps after `.channel(...)`.

**Second transition:** annotation on a Java method:

~~~java
@ServiceActivator(
        inputChannel = "orders.validated",
        outputChannel = "orders.accepted")
public OrderReceipt approve(ValidatedOrder order) {
    return new OrderReceipt(order.id(), "ACCEPTED");
}
~~~

The service activator **receives from** `orders.validated` and **sends results to** `orders.accepted`. Because the method returns `OrderReceipt`, the framework creates a result message to forward. The final handler listens on `orders.accepted` and returns `void`, terminating the one-way flow.

~~~mermaid
sequenceDiagram
    participant A as ApplicationRunner
    participant I as orders.inbound
    participant V as Java DSL validation
    participant C as orders.validated
    participant S as OrderApprovalService
    participant O as orders.accepted
    participant R as ReceiptSink
    A->>I: Message<IncomingOrder>
    I->>V: filter + transform
    V->>C: Message<ValidatedOrder>
    C->>S: approve(payload)
    S->>O: Message<OrderReceipt>
    O->>R: capture(payload)
    R-->>A: processing complete (no business reply)
~~~

**Payload contract:** `IncomingOrder(id, quantity)` on the first channel, `ValidatedOrder(id, quantity)` on the second channel, and `OrderReceipt(orderId, status)` on the final channel. Headers like `correlationId` should be preserved or explicitly mapped when needed for tracing.

**One-way send path:** `MessageChannel.send(...)` returns whether the channel handoff succeeded, not an `OrderReceipt`. If the caller expects `OrderReceipt` as a return value, build a proper request–reply contract (section 6).

## 5. input-channel and output-channel in the Java DSL

The Java DSL does not always spell out two XML attributes named `input-channel`/`output-channel`; instead it expresses them through chained method calls:

~~~java
@Bean
IntegrationFlow transferFlow() {
    return IntegrationFlow.from("transfer.requests")
            .transform(String.class, String::trim)
            .channel("transfer.normalized")
            .handle(String.class, (text, headers) -> {
                System.out.println(text);
                return null;
            })
            .get();
}
~~~

In this flow, `from("transfer.requests")` selects the input channel; `.channel("transfer.normalized")` inserts a channel boundary before the handler. The trailing `.handle(...)` endpoint becomes the consumer of `transfer.normalized`.

| Java DSL | Role | Notes |
| --- | --- | --- |
| `IntegrationFlow.from("source.channel")` | Selects the flow's source or input channel. | Channel needs a producer or adapter sending messages. |
| `.channel("next.channel")` | Routes the message to the named channel. | Channel needs an appropriate consumer. |
| `.handle(...)` | Executes a handler, either returning a result or terminating. | Returning `null` usually emits no further message. |
| `.transform(...)` | Produces a new payload for the next stage. | Ensure downstream consumers accept that type. |
| `.filter(...)` | Lets qualifying messages continue. | Request–reply flows require a clear rejection policy. |
| `.route(...)` | Picks target channels by key/rule. | Each branch needs a consuming endpoint. |
| `.bridge()` | Forwards messages to the next channel. | Used to join two channels/flows without transforming data. |

### 5.1. When Is an Explicit Channel Unnecessary?

~~~java
@Bean
IntegrationFlow compactFlow() {
    return IntegrationFlow.from("input.text")
            .transform(String.class, String::toUpperCase)
            .handle(String.class, (text, headers) -> {
                System.out.println(text);
                return null;
            })
            .get();
}
~~~

Here no intermediate named channel is declared. The DSL wires the internal endpoints automatically. When steps belong to a small self-contained flow and do not need a named boundary, this is cleaner to read.

Introduce an explicit channel only for a reason: **reuse across flows**, **changing sync/buffering semantics**, **observability**, **controlling subscribers**, or **keeping a stable interface** between modules.

### 5.2. Connecting Two Independent Flows with a Bridge

If flow A ends at `orders.validated` while flow B begins at `orders.toProcess`, add a bridge:

~~~java
@Bean
IntegrationFlow handoffFlow() {
    return IntegrationFlow.from("orders.validated")
            .bridge()
            .channel("orders.toProcess")
            .get();
}
~~~

This is a **standalone example**—do not drop it straight into section 4's application, because `orders.validated` already has a service activator subscribed. To link another flow, adjust the topology so you do not create competing consumers.

A bridge only hands off messages; if the receiving side expects a different payload type, transform/validate at that boundary first.

## 6. How Does output-channel Differ from replyChannel?

This distinction is critical when designing request–reply gateways.

- **`outputChannel`** (or `output-channel` in XML) specifies where the **current endpoint** forwards its result to the next stage. It is typically a static channel in the topology.
- **`replyChannel`** is a header on the **request message** indicating where the reply for this specific request should go. A messaging gateway can populate a temporary reply channel to correlate the response back to the waiting caller.
- **`errorChannel`** is a header/channel routing errors per configuration, especially once execution crosses onto another thread.

Example with `@MessagingGateway` invoking a flow:

~~~java
@MessagingGateway(defaultRequestChannel = "queries.input")
interface QueryGateway {
    QueryResult query(QueryRequest request);
}

@Component
class QueryHandler {

    @ServiceActivator(inputChannel = "queries.input")
    public QueryResult handle(QueryRequest request) {
        return new QueryResult(request.id(), "FOUND");
    }
}

record QueryRequest(String id) {}
record QueryResult(String id, String status) {}
~~~

This is a **standalone example**; running it requires registering the gateway interface with `@IntegrationComponentScan` and Spring context beans. When a caller invokes `query(...)`, the proxy sends the request to `queries.input` with reply routing metadata. The handler returns `QueryResult`, and the framework sends the reply back to the gateway's reply channel when no fixed output channel diverts it elsewhere.

### 6.1. What Happens If You Set a Fixed outputChannel?

Suppose the handler is changed to:

~~~java
@ServiceActivator(
        inputChannel = "queries.input",
        outputChannel = "queries.audit")
public QueryResult handle(QueryRequest request) {
    return new QueryResult(request.id(), "FOUND");
}
~~~

The handler's result is routed to `queries.audit` as configured. **Never assume the gateway will still automatically receive that result** unless downstream steps complete the reply path back to it. A gateway waiting for a reply can time out.

If you need both auditing and a reply, design proper fan-out/auditing while preserving a clear reply path, or execute auditing as a side effect without breaking the reply route. Never set `outputChannel` by name while ignoring the request–reply contract.

### 6.2. When to Use a Named Fixed Reply Channel?

Spring Integration supports configuring an explicit reply channel when replies genuinely need to route through a named channel. However, a shared reply channel serving concurrent requests requires proper correlation and consumers. For straightforward request–reply calls, letting the gateway manage its own reply path is simpler and less error-prone.

Do not forward the raw `replyChannel` header object (which may be an in-memory `MessageChannel`) over HTTP/JMS/Kafka as an arbitrary string. Protocol adapters require proper header mappers and correlation mechanisms.

## 7. Choosing Channels for Inbound and Outbound Adapters

### 7.1. Inbound Adapter: Choosing the Output Channel

An inbound adapter reads **external** data and emits messages **into Spring Integration**. With annotations:

~~~java
@Bean
@InboundChannelAdapter(
        value = "files.received",
        poller = @Poller(fixedDelay = "5000",
                         maxMessagesPerPoll = "5"))
MessageSource<File> fileSource() {
    var source = new FileReadingMessageSource();
    source.setDirectory(new File("./inbox"));
    return source;
}
~~~

This snippet requires importing `@Bean`, `@InboundChannelAdapter`, `@Poller`, `MessageSource`, `File`, and `FileReadingMessageSource`, along with the `spring-integration-file` module and the source directory. `value = "files.received"` specifies the **inbound adapter's output channel**. The polling endpoint pulls `Message<File>` from the source and sends it to that channel.

Note: this minimal snippet focuses on message direction and omits filters, accept-once, file-ready checks, and idempotency. In real file setups, guard against reading partially written files and define deduplication policies.

### 7.2. Outbound Adapter: Choosing the Input Channel

An outbound adapter/handler is a **consumer of messages from a flow**. With a one-way service activator:

~~~java
@ServiceActivator(inputChannel = "files.toArchive")
public void archive(File file) {
    fileArchiveClient.save(file);
}
~~~

`fileArchiveClient` is an application-provided dependency. The method reads from `files.toArchive` and produces no reply; do not configure an `outputChannel` on it.

With built-in JMS, Kafka, SFTP, or HTTP adapters, declaration syntax differs, yet the general direction stays **message from input channel → handler sending to external system**. When the destination returns a response needed inside the flow, prefer an **outbound gateway** over a one-way adapter.

### 7.3. Protocol Selection Table

| Scenario | Channel Needed | Other Behavior to Configure |
| --- | --- | --- |
| File/SFTP inbound polling | Adapter emits to file-intake channel. | Poller, filters, file-ready checks, remote sessions, checkpoints. |
| HTTP inbound gateway | Requests routed to the flow's request channel. | Request/response mapping, HTTP status codes, timeouts. |
| JMS/AMQP/Kafka inbound listener | Adapter/listener emits messages to processing channel. | Ack/offset handling, transactions, retries, consumer concurrency. |
| JDBC inbound polling | Message source emits records to channel. | Query selecting only new rows, transactions, watermarks, locks. |
| File/SFTP outbound adapter | Consumer reads from file-export channel. | Naming, temp write/rename, file-exists policy, permissions. |
| JMS/AMQP/Kafka outbound adapter | Consumer reads events/commands from channel. | Serializers, broker acks, delivery failures, idempotency. |
| HTTP outbound gateway | Consumer reads request from flow and produces reply. | URL, method, status codes, error mapping, response timeout. |

**A matching channel name does not replace a data contract.** For instance, `orders.toKafka` might carry serialized payloads or unserialized DTOs depending on the adapter; payload and headers must match producer and handler expectations on both sides.

## 8. Configuring input-channel and output-channel in XML Namespaces

XML namespaces express the same wiring explicitly:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="orders.raw"/>
    <int:channel id="orders.normalized"/>
    <int:channel id="orders.accepted"/>

    <!-- Receives from raw, transforms, and sends to normalized. -->
    <int:transformer
            input-channel="orders.raw"
            output-channel="orders.normalized"
            expression="payload.trim()"/>

    <!-- Service activator receives from normalized and sends reply to accepted. -->
    <bean id="orderService" class="demo.xml.OrderService"/>
    <int:service-activator
            input-channel="orders.normalized"
            output-channel="orders.accepted"
            ref="orderService"
            method="approve"/>

    <!-- Consumer of orders.accepted must be defined elsewhere. -->
</beans>
~~~

This example assumes `orders.raw` carries `String` payloads and `demo.xml.OrderService.approve(String)` returns a result object. `OrderService` must be supplied by the learner. The XML illustrates **channel wiring** only, not a complete runnable program because the terminal consumer is omitted.

For a file inbound adapter, configuration typically uses `channel="files.raw"`:

~~~xml
<int-file:inbound-channel-adapter
        id="fileInbound"
        channel="files.raw"
        directory="./inbox"
        filename-pattern="*.csv">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="5"/>
</int-file:inbound-channel-adapter>
~~~

Using this snippet requires declaring the `int-file` namespace/XSD and the `spring-integration-file` dependency. Here `channel` is the inbound adapter's **output**. Conversely, outbound adapters usually use `channel` or `input-channel` to specify the **receiving** channel depending on the schema; always check the XSD for your version.

### 8.1. Bridging Two Channels in XML

~~~xml
<int:channel id="legacy.orders"/>
<int:channel id="orders.processing"/>

<int:bridge
        input-channel="legacy.orders"
        output-channel="orders.processing"/>
~~~

The bridge transfers messages from the input channel to the output channel without business payload transformation. If `legacy.orders` is a `QueueChannel`, the bridge consumer needs an appropriate poller.

### 8.2. Avoiding Duplicate Configurations

An application can combine XML and Java DSL via `@ImportResource`, but avoid registering two competing consumers on the same `DirectChannel` or two inbound adapters polling the same source without an explicit design. Duplicate bean names can also fail context startup or override beans unexpectedly.

## 9. Choosing DirectChannel, QueueChannel, or ExecutorChannel?

Selecting input/output channels involves **channel type**, not just names. Channel type governs how messages are handed off.

| Channel Type | Behavior | Impact on Connected Endpoints |
| --- | --- | --- |
| `DirectChannel` | Sends directly to one subscriber, typically on the sender's thread. | Slow handlers block the producer; synchronous exceptions propagate to caller/poller. |
| `QueueChannel` | Buffers messages in a queue for a consumer to poll. | Consumer needs a poller; must manage capacity, durability, and retries. |
| `ExecutorChannel` | Dispatcher hands off processing to a `TaskExecutor`. | Introduces thread boundaries, executor/queue limits, and separate error paths. |
| `PublishSubscribeChannel` | Broadcasts messages to multiple subscribers as configured. | Useful for fan-out; must design per-branch error handling. |

### 9.1. DirectChannel: Simple Synchronous Pipelines

The `orders.inbound → filter → orders.validated → approve` example in section 4 uses `DirectChannel`. When `send()` runs, the consumer executes immediately on the sender's thread. If the consumer makes a 10-second HTTP call, the sender blocks for 10 seconds too.

**Never equate a successful send to `DirectChannel` with external business completion.** `MessageChannel.send` reports internal handoff; HTTP/broker/database completion requires its own contract.

### 9.2. QueueChannel: Buffering Requires a Polling Consumer

~~~java
@Bean(name = "orders.buffered")
QueueChannel ordersBuffered() {
    return new QueueChannel(100);
}

@ServiceActivator(
        inputChannel = "orders.buffered",
        poller = @Poller(
                fixedDelay = "500",
                maxMessagesPerPoll = "10"))
public void consume(ValidatedOrder order) {
    orderProcessor.process(order);
}
~~~

This snippet assumes imports for `QueueChannel`, `@Bean`, `@ServiceActivator`, `@Poller`, a `orderProcessor` bean, and `ValidatedOrder` from earlier. It is a **variant** illustrating a queue input channel—do not register it alongside the handler already consuming `orders.validated` in section 4.

A queue decouples when the producer sends from when the consumer processes. It **does not provide durability across restarts** when using the default in-memory queue. When full, send/timeout behavior must be designed explicitly.

### 9.3. ExecutorChannel: Splitting Threads Does Not Automatically Increase Reliability

With a consumer behind an `ExecutorChannel`, Spring hands execution off to the configured executor. The caller can return before the handler completes, and handler exceptions no longer unwind onto the caller's stack. Monitor executor capacity, rejections, shutdown, and error channels.

Whenever changing channel types at a flow boundary, re-test transactions, retries, and reply timeouts; never change one line of channel config while keeping synchronous assumptions intact.

### 9.4. Multiple Consumers on One Channel

`DirectChannel` normally delivers each message to **one** subscriber according to its dispatching strategy, not to all subscribers. To deliver the same event to two independent services, use `PublishSubscribeChannel` or an explicit multicast pattern. To pick one channel by currency or message type, use a router.

Adding two `@ServiceActivator(inputChannel="orders.validated")` annotations does not mean both methods receive every message. In many setups only one runs per message, causing hard-to-diagnose bugs if you misunderstand channel semantics.

## 10. When Do You Need Intermediate Channels vs. Direct Chaining?

Not every endpoint needs a separate named intermediate channel. A linear flow can stay concise:

~~~java
@Bean
IntegrationFlow simpleFlow() {
    return IntegrationFlow.from("events.in")
            .filter(Event.class, event -> event.isValid())
            .transform(Event.class, Event::toCommand)
            .handle(Command.class, (command, headers) -> {
                commandService.execute(command);
                return null;
            })
            .get();
}
~~~

This snippet is an **illustrative template** assuming `Event`, `Command`, and bean `commandService` are defined. There is no need to name a separate channel between every single step.

Add intermediate channels when:

1. **Multiple sources share one contract:** file/SFTP, HTTP, JMS, and Kafka all normalize into `OrderEvent` and send to `orders.normalized`.
2. **A stage is reused by other flows:** multiple producers push messages to a shared channel handled by one unified consumer.
3. **Processing boundaries must change:** queues or executors to avoid blocking producers or shape load.
4. **Operations and observability require it:** monitoring queue backlog, dispatch failures, starting/stopping consumers, or deploying modules independently.
5. **Topology stability matters:** keeping channel names unchanged while swapping protocol adapters.

Avoid creating channels just to multiply beans: unnecessary boundaries obscure configuration and can alter transaction and thread behavior unintentionally.

## 11. Common Mistakes When Choosing input/output Channels

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| Adapter emits messages, yet handler never runs. | Wrong channel name, stopped endpoint, or missing consumer. | Match adapter output against next endpoint's input. |
| `DirectChannel` reports no subscribers. | No handler properly registered on the channel. | Check `@ServiceActivator`, Java DSL, or XML consumers. |
| Gateway waits until timeout. | Handler produces no reply; fixed `outputChannel` diverts reply; filter drops message silently. | Trace request/reply path, check `replyChannel` and rejection policy. |
| Messages arrive at handler with wrong type. | Producer sends `File` while consumer expects `Order`. | Normalize payload/headers before the shared channel. |
| Two handlers listen to one channel, yet don't both run. | `DirectChannel` does not multicast. | Use a router or publish–subscribe as needed. |
| Switched to `QueueChannel` and messages sit forever. | Missing poller/consumer. | Register a polling endpoint for the queue channel. |
| Switched to `ExecutorChannel` and caller misses exceptions. | Handler executes on another thread. | Configure error channels, monitoring, and retries for async semantics. |
| Files/SFTP re-read after restart. | In-memory filter only; non-persistent checkpoints. | Use persistent metadata store, archiving, and idempotency. |
| Target succeeded, yet caller saw timeout. | Reply lost or arrived late, causing retries. | Reconcile via ID/idempotency key rather than retrying blindly. |
| Correlation headers lost. | Manually built new message without copying headers. | Check mappers/transformers and test across real channels. |
| Poller runs slowly despite short `fixed-delay`. | Synchronous handler holds the poller thread. | Measure execution time; tune channels, pollers, and timeouts. |
| App creates duplicate processing endpoints. | Both XML and DSL register consumers, or multiple adapters read the same source. | Check bean IDs, component scanning, and topology. |

## 12. Message Contracts at Every Channel

Choosing channels is both a **data** and **operational** decision. For example:

~~~text
Channel: orders.validated
Payload: ValidatedOrder {
    id: "ORD-1001",
    quantity: 3
}
Headers:
    correlationId: "trace-1001"
    sourceSystem: "file-import"
    idempotencyKey: "order:ORD-1001"
~~~

A contract should specify:

- **Payload type:** Java class or schema accepted by consumers, required fields, nullability, and validation rules.
- **Headers:** correlation, tracing, tenant, data source, message key; whether they must survive transformers/bridges.
- **Delivery semantics:** synchronous vs. async, queueing, and which side manages ACKs/offsets.
- **Reply semantics:** one-way vs. request–reply, where results go, and timeouts.
- **Error semantics:** where messages go on validation failures, exceptions, or downstream disconnects.
- **Idempotency:** if a source redelivers or retries after failure, can side effects execute twice?

In the Spring Integration Adapters module, multiple protocols can emit messages yet differ in headers and acknowledgement semantics. Never share one channel among producers with incompatible payload types without explicit transformation. When sending over HTTP/JMS/AMQP/Kafka, do not serialize internal Spring headers like `replyChannel` automatically; use protocol-compatible header mapping.

## 13. Errors, Threads, Transactions, and Lifecycles

### 13.1. Error Paths Must Follow Actual Topology

~~~mermaid
flowchart TD
    A["Adapter receives data"]
    B["Processor input channel"]
    C["Validate/Transform"]
    D["Output channel"]
    E["Outbound handler"]
    OK["Target confirms per contract"]
    ERROR["Error flow / retry / quarantine"]
    A --> B --> C --> D --> E --> OK
    A -. "source read error" .-> ERROR
    B -. "dispatch failure" .-> ERROR
    C -. "validation error" .-> ERROR
    E -. "timeout / target error" .-> ERROR
~~~

In synchronous flows using `DirectChannel`, downstream exceptions can propagate back to the caller or poller. With queues, executors, or listeners, errors can happen on other threads and require error channels, `ErrorMessage`, and proper recovery policies.

**Delivering a message to an output channel does not mean the external system finished.** Separate source reading, channel handoff, handler execution, and external confirmation.

### 13.2. Transactions Do Not Automatically Cross Every Channel

If a message traverses two `DirectChannel` beans on the same thread, an active Spring transaction can span eligible internal operations. Once it crosses a `QueueChannel`, `ExecutorChannel`, or broker, never assume it remains inside the same transaction. Nor can an internal DB transaction roll back an HTTP call already executed by a partner.

For side effects such as payments or order creation, use idempotency keys, unique constraints, transactional outboxes, or reconciliation workflows for uncertain outcomes. Configuring input/output channels alone never provides exactly-once delivery.

### 13.3. Lifecycle Control

Inbound adapters, pollers, listener containers, and outbound connection pools often have distinct lifecycles. When endpoints stop, channels may remain alive without consumers, or queues may accumulate waiting messages. Monitor endpoint states, inbound/outbound counts, errors, queue depths, latencies, and external connectivity.

In multi-instance deployments, every instance can poll the same file/SFTP folder or query the same DB unless locks, claims, or partitions exist. In-memory channels belong to each JVM instance and do not form a shared cross-process bus.

## 14. Testing input/output Channel Wiring

Unit tests calling `approve(...)` directly only check business logic. To verify channel names, endpoints, and payload types, boot the Spring context and **send messages into the input channel**.

For section 4's application, add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create `ChannelSelectionApplicationTest.java` in package `demo.channels`:

~~~java
package demo.channels;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class ChannelSelectionApplicationTest {

    @Autowired
    @Qualifier("orders.inbound")
    MessageChannel input;

    @Autowired
    ReceiptSink sink;

    @BeforeEach
    void clearResults() {
        sink.clear();
    }

    @Test
    void validOrderReachesAcceptedChannelAndSink() {
        boolean sent = input.send(
                MessageBuilder.withPayload(
                        new IncomingOrder("ORD-2001", 2))
                        .setHeader("correlationId", "trace-test-2001")
                        .build());

        assertTrue(sent);
        assertEquals(
                List.of(new OrderReceipt("ORD-2001", "ACCEPTED")),
                sink.snapshot());
    }

    @Test
    void invalidOrderDoesNotReachSink() {
        assertThrows(MessageRejectedException.class,
                () -> input.send(MessageBuilder.withPayload(
                        new IncomingOrder("ORD-2002", 0)).build()));

        assertTrue(sink.snapshot().isEmpty());
    }
}
~~~

Because both intermediate channels are `DirectChannel`, the flow and handlers finish synchronously before `send` returns. Thus the test can inspect `sink.snapshot()` immediately.

This test verifies **the wiring** from `orders.inbound` through `orders.validated` and `orders.accepted` to the final handler; it does not test file/SFTP/Kafka connections or external system acknowledgements. If channels are swapped for queues or executors, await results with bounded timeouts and handle concurrency.

### 14.1. Additional Tests Worth Writing

1. Send a message with an unexpected payload type to verify rejection/transformation rules.
2. Intentionally misspell a channel name in a test config to observe the missing-subscriber failure.
3. Place a message-dropping filter in a request–reply flow and verify whether callers receive an error or timeout.
4. Change `orders.validated` to a `QueueChannel`, add a consumer poller, and compare send vs. execution timestamps.
5. Simulate outbound handler timeouts/exceptions and verify where `ErrorMessage` lands, retry timing, and duplicate prevention.
6. Send concurrent requests via a messaging gateway to verify replies are never swapped across callers.

## 15. Exercise: Designing Channels for a Multi-Protocol Pipeline

**Problem:** a system receives orders from both SFTP files and JMS. Both sources must normalize into `OrderEvent`, deduplicate, call a partner API, and persist processing results to a database.

Requirements:

1. Name channels for each unnormalized source: `orders.sftp.raw` and `orders.jms.raw`.
2. Use separate transformers per source and send valid messages into a shared channel `orders.normalized`.
3. Choose the validation service's input-channel and output-channel. Invalid messages route to a dedicated error/quarantine flow.
4. Forward valid orders to `orders.toPartner`. Since the partner API returns a response, design an outbound gateway and a response channel.
5. Send acceptance results to `orders.results` and use a handler to persist to the database; define transaction responsibilities.
6. Explain whether to choose `DirectChannel`, `QueueChannel`, or `ExecutorChannel` at each boundary based on load and recovery needs.
7. Simulate the partner API creating an order while the response is lost; demonstrate how retries with an idempotency key avoid duplicate orders.
8. Write an integration test where messages with the same ID arrive from SFTP and JMS, verifying payload/header contracts, deduplication, and final state.

**Pass criteria:** no channel is accidentally left without a consumer; both sources normalize payloads before the shared channel; request–reply paths have clear reply routing; all side effects specify timeout/retry/ack rules; and the diagram accurately shows message direction and channel types at every handoff.

## 16. Self-Check Questions

1. Can a single channel be both the output of one endpoint and the input of another?
2. Why does an inbound adapter only configure an output channel with no internal input-channel?
3. If `@ServiceActivator` declares `outputChannel` yet the method returns `void`, what happens?
4. When should you use `IntegrationFlow.from(...)` versus `.channel(...)`?
5. What two distinct roles do request channels and reply paths play for `@MessagingGateway`?
6. Why can't `outputChannel` be treated as identical to the `replyChannel` header?
7. Do two `@ServiceActivator` methods reading from the same `DirectChannel` both process every message by default?
8. If you change an input channel to a `QueueChannel`, what additional component must you configure?
9. What does delivering a message to an output channel prove, and what does it not prove?
10. When a handler moves to another thread, how do error handling and transactions change?
11. How can you test channel wiring without booting real SFTP/JMS/Kafka servers?
12. Why must multiple adapters feeding one shared channel normalize payloads and headers beforehand?

**Hints:** input/output are endpoint-relative roles; gateways attach reply paths to requests; channels govern handoff semantics; testing inside a Spring context catches wiring bugs; end-to-end reliability depends on source state, target side effects, and retry strategies.

## 17. Key Takeaways

**Choosing `input-channel` and `output-channel`** defines the message path across producers, endpoints, and consumers in Spring Integration. Inbound adapters send messages into a flow's entry channel; transformers, filters, and service activators read from the upstream channel and, when producing outputs, forward to the downstream channel; outbound adapters consume messages to deliver them to targets.

For files, SFTP, HTTP, JMS, AMQP, Kafka, and databases, combine **consistent channel naming**, **explicit payload/header contracts**, **channel types suited to threading and load**, **deliberate reply/error paths**, and **real topology tests**. Properly wired channels get messages to the right component; safe execution further requires timeouts, retries, idempotency, and protocol-level business acknowledgements.
