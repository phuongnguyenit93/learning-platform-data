# @ServiceActivator as an Outbound Endpoint

## 1. Context and Learning Objectives

In Spring Integration, a **service activator** is an endpoint that receives a message from a `MessageChannel` and invokes a method or a `MessageHandler` to perform an action. When placed at the **end of an integration flow**, it typically performs an outbound action: calling a service, writing data, publishing a message to another system, or handing off to a specialized integration component.

The `@ServiceActivator` annotation connects a Java method to a channel without having to manually write a message-reading loop. It is a straightforward choice when the final logic is a business operation or a call to an application-managed client.

This lesson belongs to the **Integration Flow Creation** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module aims to connect external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practice working with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and manage message contracts, errors, and connection lifecycles.

After this lesson, learners will be able to:

- Explain the roles of `@ServiceActivator`, `inputChannel`, and `outputChannel`.
- Attach a service activator to the end of a flow created with the Java DSL.
- Design **one-way** endpoints that return no reply and distinguish them from **request–reply** endpoints.
- Build handlers that accept `Message<T>` to access both payload and headers.
- Choose between a custom `@ServiceActivator` and a built-in outbound adapter/gateway.
- Identify errors, duplicates, retries, timeouts, transactions, and limits of outbound calls.
- Write tests for the path `channel → flow → @ServiceActivator → client`.

**Scope:** this lesson focuses on using `@ServiceActivator` as an outbound endpoint. An outbound call may use HTTP, JMS, AMQP, Kafka, SFTP, or a database; connection setup and acknowledgement semantics depend on each adapter and client.

## 2. Where Does a Service Activator Sit in a Message Flow?

A one-way flow typically consists of a message source, validation/transformation steps, an output channel, and an endpoint that produces a *side effect* at the destination.

~~~mermaid
flowchart LR
    A["Inbound adapter<br/>or sending app"]
    B["orders.input<br/>MessageChannel"]
    C["Filter / Transform"]
    D["orders.outbound<br/>MessageChannel"]
    E["@ServiceActivator<br/>publish(Message<T>)"]
    F["External client"]
    G[("Target system")]
    A --> B --> C --> D --> E --> F --> G
~~~

| Component | Responsibility | Example |
| --- | --- | --- |
| `Message<?>` | Carries payload and headers across integration steps. | `PartnerOrder`, `correlationId` header. |
| `MessageChannel` | Delivers messages to consumers; controls synchronous or asynchronous execution. | `DirectChannel`, `QueueChannel`. |
| `IntegrationFlow` | Declares transform/filter/route/channel pipelines via the DSL. | `IntegrationFlow.from("orders.input")`. |
| `@ServiceActivator` | Registers a method or handler as a message-receiving endpoint. | `@ServiceActivator(inputChannel = "orders.outbound")`. |
| Client / service | Executes the final action or calls an external system. | HTTP client, `JmsTemplate`, JDBC repository. |
| Target system | Receives outbound output and defines its own acknowledgement rules. | ERP, broker, file server, database. |

`@ServiceActivator` is not restricted to the end of a flow: if the method returns a value, the message can continue through another channel or be returned to the caller. It acts as an **outbound endpoint** when placed at the end of a pipeline and the handler completes the work without forwarding a message onward.

An endpoint at the end of a flow does not automatically mean the external system **processed it successfully**. The handler may have only enqueued it locally, or the client may have sent a request without yet receiving confirmation. Therefore, clearly separate *sent*, *received*, and *business-completed*.

## 3. Basic Syntax of @ServiceActivator

### 3.1. Annotating a Spring Bean Method

~~~java
@Component
class AuditWriter {

    @ServiceActivator(inputChannel = "audit.outbound")
    public void writeAudit(Message<String> message) {
        String event = message.getPayload();
        System.out.println("Audit: " + event);
    }
}
~~~

Points to remember:

- The class containing the method must be Spring-managed, for example via `@Component` and component scanning.
- `inputChannel` specifies the channel from which the endpoint subscribes to messages.
- The parameter can be `Message<T>` to access both payload and headers; simpler handlers can declare the payload type directly.
- A `void` return type indicates the endpoint produces no reply. The handler performs a side effect without emitting a new message downstream.
- Spring Integration registers the consumer/endpoint from the annotation within the application context. Code sending messages to the channel triggers execution according to the channel type.

If the class is instantiated with `new AuditWriter()` outside the Spring context, the annotation does not turn that method into an endpoint. Likewise, a mismatched channel name prevents the flow from reaching the handler.

### 3.2. When the Method Returns an Object

A service activator can also turn an incoming message into a reply:

~~~java
@ServiceActivator(inputChannel = "validation.requests")
public ValidationResult validate(OrderCommand command) {
    return new ValidationResult(command.id(), true);
}
~~~

In this snippet, `OrderCommand` and `ValidationResult` are application-defined types. The return value is wrapped by the framework into a reply message and routed according to `outputChannel` or `replyChannel` as appropriate.

If a caller invokes synchronously through a messaging gateway, ensure the flow produces the reply the gateway expects. If the method is `void` or returns `null`, a gateway waiting for a response may block until timeout. Thus, **one-way outbound endpoints** and **request–reply endpoints** require distinct contracts.

### 3.3. Common Annotation Attributes

| Attribute | Meaning | Scenario |
| --- | --- | --- |
| `inputChannel` | Name of the channel receiving messages. | `"orders.outbound"`. |
| `outputChannel` | Channel receiving the result when the method produces a reply. | Connecting a handler to the next processing stage. |
| `requiresReply` | Requires the handler to produce a reply; useful when a reply is mandatory. | Request–reply or mandatory transformation steps. |
| `poller` | Configures periodic message polling from a `PollableChannel`. | Inbound `QueueChannel`. |
| `autoStartup` | Controls whether the endpoint starts automatically with the lifecycle. | Controlling when outbound delivery opens. |

With `DirectChannel`, the handler usually executes immediately when a message is sent to the channel and **does not need a `poller`**. With `QueueChannel`, a polling consumer must be configured to drain messages from the queue.

## 4. Complete Example: Ending a Flow with @ServiceActivator

Suppose an application receives an internal order, validates the amount, maps it to a partner DTO, and sends it to a client representing an ERP system. To keep the focus on endpoint wiring, the example client stores data in memory. In production, this client can be replaced with an HTTP, JMS, or real adapter integration.

The example uses Java 17+, Spring Boot, and Spring Integration.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

### 4.1. Application Code

Place the entire listing below in `OutboundFlowApplication.java` under package `demo.outbound`. There is only one `public` class; the remaining records and components are package-private.

~~~java
package demo.outbound;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableIntegration
public class OutboundFlowApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(OutboundFlowApplication.class, args);

        var input = context.getBean("orders.input", MessageChannel.class);
        input.send(MessageBuilder.withPayload(
                        new Order("ORD-1001", new BigDecimal("250000")))
                .setHeader("correlationId", "trace-ord-1001")
                .build());
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.outbound")
    MessageChannel ordersOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderToPartnerFlow() {
        return IntegrationFlow.from("orders.input")
                .filter(Order.class,
                        order -> order.total() != null
                                && order.total().signum() > 0,
                        endpoint -> endpoint.throwExceptionOnRejection(true))
                .transform(Order.class,
                        order -> new PartnerOrder(
                                order.id(), order.total()))
                .channel("orders.outbound")
                .get();
    }
}

record Order(String id, BigDecimal total) {}

record PartnerOrder(String id, BigDecimal total) {}

@Component
class PartnerClient {

    private final List<PartnerOrder> received =
            new CopyOnWriteArrayList<>();

    public void send(PartnerOrder order, String correlationId) {
        // Demo: simulate sending to an external system.
        received.add(order);
        System.out.println("Sent " + order.id()
                + " with correlationId=" + correlationId);
    }

    public List<PartnerOrder> received() {
        return List.copyOf(received);
    }

    public void clear() {
        received.clear();
    }
}

@Component
class OutboundOrderPublisher {

    private final PartnerClient client;

    OutboundOrderPublisher(PartnerClient client) {
        this.client = client;
    }

    @ServiceActivator(inputChannel = "orders.outbound")
    public void publish(Message<PartnerOrder> message) {
        PartnerOrder order = message.getPayload();
        String correlationId =
                (String) message.getHeaders().get("correlationId");

        client.send(order, correlationId);
    }
}
~~~

Running the Spring Boot application initializes the context, creates both channels, registers the `IntegrationFlow`, and creates the `@ServiceActivator` endpoint. `main()` sends a message with an `Order` payload into `orders.input`. On success, the console is expected to print `Sent ORD-1001...`.

This example **makes no network requests and does not confirm that an ERP received the order**. `PartnerClient` merely simulates the outbound boundary. In production, use a real client configured with authentication, timeouts, retries, monitoring, and the destination's response/ack contract.

### 4.2. Path of a Message

~~~mermaid
sequenceDiagram
    participant A as Application
    participant I as orders.input
    participant F as IntegrationFlow
    participant O as orders.outbound
    participant S as OutboundOrderPublisher
    participant P as PartnerClient
    A->>I: Message<Order> + correlationId
    I->>F: filter(Order)
    F->>F: transform(Order -> PartnerOrder)
    F->>O: Message<PartnerOrder>
    O->>S: publish(message)
    S->>P: send(partnerOrder, correlationId)
    P-->>S: method returns
    S-->>A: no reply (one-way)
~~~

With the two `DirectChannel` beans in this example, processing runs synchronously along the send call. `send(...)` returns once the subscriber finishes or an exception propagates; the boolean return value of `MessageChannel.send(...)` is not a business acknowledgement from an external system.

Key points:

1. `orderToPartnerFlow()` does not call `OutboundOrderPublisher` directly. It hands off the message through `orders.outbound`.
2. `@ServiceActivator(inputChannel = "orders.outbound")` creates a consumer for the final channel.
3. `publish(Message<PartnerOrder>)` accepts the exact payload type produced by the transformer while reading `correlationId` from headers.
4. `PartnerClient.send(...)` executes the final action. Because `publish` returns `void`, no reply is produced for the message.
5. `filter` throws an exception when the amount is invalid instead of silently dropping the message and leaving the sender without an error signal.

**Message contract:** the input is `Order(id, total)` requiring `total > 0`; the output on `orders.outbound` is `Message<PartnerOrder>` with header `correlationId`. For production code, add validation for `id`, data types, monetary limits, source system info, and an ID for duplicate prevention.

## 5. Why Is @ServiceActivator Suitable as an Outbound Terminal?

An integration flow can terminate with several types of endpoints:

| Ending Approach | Best When | Watch-outs |
| --- | --- | --- |
| `@ServiceActivator` on custom service | Calling custom logic, an existing client, or specialized business workflows. | You own mapping, error handling, timeouts, and retries for the external call. |
| Java DSL `.handle(...)` | Configuring the handler inline in the flow or delegating to an existing service bean. | Extract lengthy logic to dedicated services; be clear about reply types. |
| Built-in outbound adapter | Protocol is supported by Spring Integration and a one-way send is needed. | Configure connections, acks, retries, and serializers per protocol. |
| Built-in outbound gateway | Must receive a response from the external system and use it in the flow. | Timeouts, response mapping, and downstream errors. |

Under the hood, a built-in outbound adapter also typically uses a **message-handling endpoint** to dispatch data to a destination. The difference lies in scope: `@ServiceActivator` **wires any method or handler into a flow**, whereas specialized adapters/gateways already provide protocol-specific handling.

Do not reimplement all of SFTP, JMS, AMQP, or HTTP when a built-in adapter already fits. Still, a service activator remains valuable for business logic coordinating multiple services or custom auditing steps.

### 5.1. Comparison with Java DSL .handle(...)

Annotation form from the example:

~~~java
@ServiceActivator(inputChannel = "orders.outbound")
public void publish(Message<PartnerOrder> message) {
    client.send(message.getPayload(),
            (String) message.getHeaders().get("correlationId"));
}
~~~

An equivalent endpoint can be written in the Java DSL using a handler:

~~~java
@Bean
IntegrationFlow partnerDeliveryFlow(PartnerClient client) {
    return IntegrationFlow.from("orders.outbound")
            .handle(PartnerOrder.class, (order, headers) -> {
                client.send(order, (String) headers.get("correlationId"));
                return null; // one-way termination
            })
            .get();
}
~~~

**The two snippets are mutually exclusive alternatives.** If both are registered concurrently on the same `DirectChannel` as two independent consumers, a message may be dispatched to only one of the subscribers according to the channel's dispatching policy, rather than automatically broadcast to both. To multicast to multiple branches, use a publish–subscribe channel and design accordingly.

### 5.2. Attaching @ServiceActivator to a @Bean Returning MessageHandler

When you need to manage the handler as an explicit standalone bean, combine `@Bean` and `@ServiceActivator` on a method returning `MessageHandler`:

~~~java
@Bean
@ServiceActivator(inputChannel = "orders.outbound")
MessageHandler outboundHandler(PartnerClient client) {
    return message -> {
        PartnerOrder order = (PartnerOrder) message.getPayload();
        String trace =
                (String) message.getHeaders().get("correlationId");
        client.send(order, trace);
    };
}
~~~

This snippet illustrates an **alternative** configuration to `OutboundOrderPublisher` in section 4—do not add both simultaneously to the runnable example. Both approaches declare the input channel and a Spring-managed handler. For easier testing and less casting, annotating a typed method taking `Message<PartnerOrder>` is often more readable.

## 6. One-Way vs. Request–Reply: Choosing the Right Contract

### 6.1. One-Way Endpoints

In a **one-way** flow, the handler primarily executes a side effect:

~~~java
@ServiceActivator(inputChannel = "notifications.outbound")
public void sendNotification(Notification notification) {
    notificationService.send(notification);
}
~~~

`Notification` and `notificationService` are application-supplied types/services. If there is no reply, do not put a synchronous messaging gateway expecting a `NotificationResult` without a step that produces it.

**Note:** a method returning no value does not imply everything runs asynchronously. For example, a `DirectChannel` still executes `notificationService.send(...)` on the sender's thread, waiting until the call finishes before returning control.

### 6.2. Endpoints Returning a Reply

If the caller needs the send outcome or further downstream processing is required, the service activator can return an object:

~~~java
@ServiceActivator(inputChannel = "partner.requests")
public DeliveryResult deliver(PartnerOrder order) {
    return partnerDeliveryService.submit(order);
}
~~~

In this case, provide a valid reply path or use a request–reply gateway. You can specify `outputChannel` for the next step, or let the framework use the message's `replyChannel` where appropriate. The return value becomes the payload of a new message. For HTTP APIs with responses, an outbound gateway typically expresses this intent more clearly.

### 6.3. How Far Does "Sent Successfully" Go?

There are three distinct outcome levels:

1. **Handler invoked:** the message reached `@ServiceActivator`.
2. **Protocol handoff or acceptance:** HTTP request received a response, broker accepted the message, file was written, or database operation returned.
3. **Business completion at destination:** the partner actually processed the request; this may require callbacks, business ACKs, or reconciliation.

Do not infer level 3 from a `void` method finishing, `MessageChannel.send() == true`, or a transport-level request acceptance. The integration contract must explicitly define what acknowledgement suffices to mark completion.

## 7. Payloads, Headers, and System Boundaries

Outbound handlers are often the last place to attach metadata before data leaves the application. A typical message contract:

~~~text
Message<PartnerOrder>
  payload:
    id: "ORD-1001"
    total: 250000
  headers:
    correlationId: "trace-ord-1001"
    sourceSystem: "order-service"
    idempotencyKey: "partner-a:ORD-1001"
~~~

| Field | Purpose | Notes |
| --- | --- | --- |
| `id` | Business identifier in payload. | Partners may enforce different formats and uniqueness rules than internal systems. |
| `total` | Value to transmit. | Specify unit, currency, scale, and rounding. |
| `correlationId` | Links logs and error investigations across systems. | Normally preserved across transform/route steps. |
| `sourceSystem` | Identifies the originating system or partner. | Useful when multiple inbound adapters share one flow. |
| `idempotencyKey` | Identifies the logical operation to prevent duplicates. | The destination must recognize and enforce its semantics. |

Spring Integration headers like `replyChannel` and `errorChannel` may hold internal channel objects; **do not blindly forward all headers over HTTP/JMS/Kafka**. When leaving the system, use explicit header mappers or DTOs. Never leak internal or sensitive data externally just because it happens to sit in `MessageHeaders`.

Transformers normally preserve necessary headers when the framework builds a new message from a payload. If constructing a new `Message<?>` manually, carefully inspect correlation, tracing, error/reply, routing, and protocol-specific headers. When an outbound handler serializes a payload to JSON or a partner format, test missing fields, nulls, date/time formats, charsets, and oversized inputs.

## 8. Combining Service Activators with Inbound Adapters, Gateways, and Pollers

Because it consumes from a channel, `@ServiceActivator` is decoupled from where messages originate:

~~~mermaid
flowchart TB
    FILE["File/SFTP inbound<br/>+ poller"]
    API["HTTP inbound gateway"]
    BROKER["JMS/AMQP/Kafka<br/>inbound listener"]
    DB["JDBC inbound<br/>+ poller"]
    FLOW["Validate / Transform / Route"]
    CH["outbound channel"]
    ACT["@ServiceActivator"]
    CLIENT["HTTP / JMS / Kafka / File<br/>or database client"]
    FILE --> FLOW
    API --> FLOW
    BROKER --> FLOW
    DB --> FLOW
    FLOW --> CH --> ACT --> CLIENT
~~~

Responsibilities differ at each end:

- The inbound adapter receives messages from files/SFTP, an event broker, or a DB and decides when to acknowledge reads.
- `IntegrationFlow` normalizes payloads and routes through channels.
- The service activator invokes the client/destination; it must decide when outbound delivery counts as success, which errors to retry, and how to track external side effects.

When designing a flow that reads files and sends HTTP requests, do not permanently mark a file as processed merely because the inbound adapter emitted `Message<File>`; if the downstream HTTP call fails, you need retention, retries, or state tracking so records are not lost.

### 8.1. When the Input Channel Is a QueueChannel

`DirectChannel` dispatches immediately to a subscriber, whereas `QueueChannel` buffers messages for a consumer to pull later. A service activator reading from a queue needs an appropriate poller:

~~~java
@Bean(name = "outbound.queue")
QueueChannel outboundQueue() {
    return new QueueChannel(100);
}

@ServiceActivator(
        inputChannel = "outbound.queue",
        poller = @Poller(
                fixedDelay = "1000",
                maxMessagesPerPoll = "10"))
public void sendQueued(Message<PartnerOrder> message) {
    partnerClient.send(message.getPayload(),
            (String) message.getHeaders().get("correlationId"));
}
~~~

This snippet assumes `QueueChannel`, `@Poller`, and the `partnerClient` bean are imported/available in the enclosing class. It is an **alternative configuration**—do not plug it alongside the sample flow without adjusting the design.

A bounded queue helps prevent unbounded memory growth, but `QueueChannel` stores messages in memory by default and **does not guarantee durability across restarts**. If reliable delivery is required, evaluate a persistent message store, a broker, or an outbox with proper acknowledgement semantics.

## 9. Outbound Terminal Error Paths

Outbound operations can fail at several stages:

~~~mermaid
flowchart TD
    M["Message enters @ServiceActivator"]
    V{"Valid data?"}
    SEND["Client sends to destination"]
    R{"Destination confirms per contract?"}
    OK["Record success"]
    BAD["Business validation error"]
    RETRY["Error policy, retry / DLQ / quarantine"]
    M --> V
    V -->|"No"| BAD
    V -->|"Yes"| SEND --> R
    R -->|"Yes"| OK
    R -->|"No / uncertain"| RETRY
    BAD --> RETRY
~~~

### 9.1. Synchronous Errors

With `DirectChannel`, exceptions inside a `@ServiceActivator` method typically propagate back through the send call to the upstream caller. Examples include payload parsing failures or a client throwing an exception on the same thread. The application must decide how the sender observes that failure (HTTP status, gateway error return, poller logging, etc.).

### 9.2. Errors Across Thread Boundaries

If the flow uses an `ExecutorChannel`, `QueueChannel`, broker, or task executor, the handler may run on a different thread. In that case, exceptions do not necessarily return to the original caller; error handling may require an `errorChannel`, `ErrorMessage`, retry advice, dead-letter queues, or failed-message storage.

A poller running again after an error **does not mean** the failed message is automatically retried properly. Behavior depends on queue/source state, transactions, acknowledgements, and exception handling. Always verify with tests against the specific adapter.

### 9.3. The Hard Case: Side Effect Succeeded, Response Lost

Suppose the service activator submits an order over HTTP. The partner creates the order, but the connection drops before the application receives the response. Retrying the same request without idempotency can cause the destination to create two orders.

Common mitigations:

- Generate a stable `idempotencyKey` per **logical business operation** and pass it to the destination if supported.
- Persist outbound request state in durable storage and reconcile uncertain outcomes.
- Cap retries, apply backoff, and differentiate error classes: bad input, timeouts, rate limits, and server errors.
- Route unrecoverable cases to a dead-letter/quarantine store with sufficient metadata for inspection and controlled replay.

**`@ServiceActivator` alone provides no exactly-once guarantee.** Delivery semantics must consider source, channel, handler, and destination together.

## 10. Transaction Boundaries and Resources

Consider a synchronous flow receiving an order over `DirectChannel` and calling a JDBC service on the same thread: a Spring transaction can cover internal operations if configured properly. However, **a single database transaction does not automatically cover external HTTP or broker calls**.

If the DB commit succeeds and the outbound call fails, system state can diverge. Depending on the use case, solutions include the transactional outbox pattern, dedicated delivery state tracking, idempotent retries, sagas, or compensating actions.

In outbound handlers, watch out for:

| Scenario | Risk | Design Decision |
| --- | --- | --- |
| HTTP client timeout | Threads blocked; external outcome unknown. | Timeouts, connection pools, idempotency, and reconciliation. |
| Publishing to Kafka/JMS | Publish may be async or broker ack depends on config. | Choose delivery/ack level, serializer, error callbacks, and DLQ. |
| Writing SFTP/files | Target file might be read mid-write. | Write to temp then rename, manage permissions, and clean up. |
| Writing to DB | Duplicates, transaction rollbacks, or lock contention. | Unique constraints, transactions, and error-code-aware retries. |
| Application shutdown | In-flight messages unfinished; queued data lost. | Graceful shutdown, queue draining, and persistent state. |

Never run blocking outbound calls on scheduler or event-listener threads when destination latency is unbounded. If offloading to another thread, bound queues and concurrency, manage lifecycle, and redesign error paths accordingly.

## 11. Testing an Outbound Endpoint

Good tests verify three things: payloads are transformed accurately, the `@ServiceActivator` method is invoked via the real channel, and the client receives the expected data and metadata.

With the in-memory `PartnerClient` from section 4, you can write a Spring context test. Place it in `OutboundFlowApplicationTest.java` under package `demo.outbound`:

~~~java
package demo.outbound;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class OutboundFlowApplicationTest {

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    PartnerClient client;

    @BeforeEach
    void resetClient() {
        client.clear();
    }

    @Test
    void validOrderReachesOutboundServiceActivator() {
        var message = MessageBuilder.withPayload(
                        new Order("ORD-2001", new BigDecimal("999.00")))
                .setHeader("correlationId", "test-2001")
                .build();

        assertTrue(input.send(message));

        assertEquals(
                new PartnerOrder("ORD-2001", new BigDecimal("999.00")),
                client.received().get(0));
        assertEquals(1, client.received().size());
    }

    @Test
    void invalidOrderDoesNotReachPartnerClient() {
        var invalid = MessageBuilder.withPayload(
                new Order("ORD-2002", BigDecimal.ZERO)).build();

        assertThrows(MessageRejectedException.class,
                () -> input.send(invalid));

        assertTrue(client.received().isEmpty());
    }
}
~~~

The project needs `spring-boot-starter-test` in `test` scope. Because the test uses two `DirectChannel` beans, `send` completes synchronously before assertions run. If you replace `orders.outbound` with a queue or executor, the test must wait for results with a bounded timeout (such as a latch or await utility) instead of asserting immediately.

For real outbound integrations, expand tests to cover: timeouts, HTTP 429/5xx responses, broker disconnects, serializer errors, duplicates, and application restarts. Use mock servers, test brokers, or test databases as appropriate; assert side effects at the destination, not just that the handler was called.

### 11.1. Testing Handler-Thrown Exceptions

Add a test replacing `PartnerClient` with a fake that conditionally throws exceptions. Test assertions should answer:

1. Does the caller of `MessageChannel.send(...)` receive the exception?
2. Was the message removed from the source/queue?
3. Can the same request be reprocessed without creating duplicate side effects?
4. When a handler partially executes, what state enables reconciliation?

The answers depend on channel and source types; never conclude an entire flow is reliable based solely on a unit test calling `publish()` directly.

## 12. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `@ServiceActivator` handler is never called. | Class is not a Spring bean, wrong `inputChannel`, endpoint not started, or no messages sent. | Check component scanning, channel names, and endpoint lifecycle. |
| Sending to `DirectChannel` reports no subscribers. | No consumer registered for the channel or endpoint is stopped. | Define the service activator/flow consumer and check bean names. |
| Two handlers subscribe, yet only one runs. | `DirectChannel` dispatches to a single subscriber rather than multicasting. | Use `PublishSubscribeChannel` if fan-out is needed and handle per-branch errors. |
| Gateway times out even though outbound finished. | `void` handler produces no reply, while the gateway waits for one. | Separate one-way from request–reply; design an explicit reply path. |
| Correlation info disappears after transform. | Creating a new message manually without preserving needed headers. | Document header contracts and add end-to-end message tests. |
| Destination receives duplicate requests. | Retries or redelivery after an uncertain failure. | Idempotency keys, checkpoints, outbox, or reconciliation. |
| System slows down when partner API is slow. | Synchronous handler blocks poller or listener threads. | Timeouts, load limits, and controlled thread offloading. |
| Unit tests pass, yet production loses data. | Tests call methods directly without checking sources, acks, queues, or restarts. | Integration tests through real channels and realistic source behavior. |
| Retries cause repeated side effects. | No distinction between pre-send failures and post-send failures. | Design an outbound state machine and idempotent retries. |

## 13. Extended Practice Exercise

**Problem:** an application receives order messages from a CSV file or Kafka source, converts them to `PartnerOrder`, and sends them outbound to an ERP via a client. Design the flow with these requirements:

1. Inbound normalizes records to `Order(id, total, currency)`; records missing an ID or with non-positive amounts go to an error flow.
2. `IntegrationFlow` transforms valid messages into an ERP-ready DTO, preserving `correlationId`.
3. `@ServiceActivator(inputChannel = "erp.outbound")` invokes the ERP client with no reply to the one-way source.
4. The simulated client succeeds for some orders, times out for some, and returns data errors for the rest.
5. Design an idempotency key so timeouts/retries do not cause duplicates.
6. Persist failed messages to an inspectable store; separate data-fix errors from retryable errors.
7. When replacing `DirectChannel` with `QueueChannel`, add a poller and explain the impact on threading, timing, error propagation, and queue durability.

**Completion criteria:** write tests for the happy path, validation errors, client errors, and post-timeout retries; verify messages arrive on `erp.outbound`; and describe what point counts as business completion. Explain why a `void` method alone cannot prove the ERP completed the order.

## 14. Self-Check Questions

1. What kind of endpoint does `@ServiceActivator` define? Must it always be an outbound adapter?
2. Why does the annotation only take effect when the method belongs to a Spring bean?
3. How does `inputChannel` connect with `IntegrationFlow.channel(...)`?
4. Does a `void` terminal endpoint mean all preceding steps run asynchronously?
5. In a flow with `DirectChannel`, where can exceptions from an outbound client surface?
6. If the method returns `PartnerResult`, how does Spring Integration route the reply?
7. Why do two subscribers on the same `DirectChannel` not act as a broadcast?
8. A request was processed by the partner, yet the client timed out: how should retries avoid duplicate writes?
9. When using `QueueChannel`, what happens if there is no poller/consumer?
10. Where is the data-consistency boundary when moving from an internal database to HTTP/SFTP/JMS?

**Hints:** a service activator attaches a method/handler to a message channel; endpoints can sit mid-flow or at the end; replies require a valid reply path; side-effect outcomes cannot be inferred from internal message delivery. Outbound correctness depends on protocol acknowledgements, durable state, and deduplication rules.

## 15. Conclusion

`@ServiceActivator` is a concise way to turn a Java method into a **`MessageChannel` consumer**. At the end of an integration flow, it serves as an outbound endpoint by invoking a service or client to deliver data to another system. Use `void` for one-way operations, or return a value when the architecture genuinely has a reply path.

When integrating files, SFTP, HTTP, JMS, AMQP, Kafka, or databases, keep payload/header contracts clear, choose appropriate channels and threading, manage timeouts and retries, distinguish dispatch status from business completion, and test failures and duplicates. That is how an endpoint that looks simple on paper operates reliably across connected systems.
