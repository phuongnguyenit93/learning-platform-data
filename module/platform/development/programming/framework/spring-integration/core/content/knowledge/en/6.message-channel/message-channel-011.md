# Channels as Component Decoupling Points

In the **Message channel** chapter of the **SPRING_INTEGRATION_CORE** module, a channel serves as the communication boundary between components of a message flow. The producer sends a `Message` to a channel; the receiving endpoint continues processing without the producer needing to call the consumer's implementation class directly.

This boundary enables composing transformer, filter, router, service activator, or aggregator steps into a modifiable flow. To design it properly, distinguish decoupling dependencies between components from decoupling execution timing, execution threads, and transactions.

After this lesson, you will be able to:

- Explain which dependencies a channel removes and which contracts remain.
- Decouple producers from consumers using a meaningfully named channel.
- Build a Java DSL example with independently testable components.
- Evaluate the impact of switching from synchronous processing to queue-based processing.
- Identify design mistakes that leave two components tightly coupled despite using messages.

## 1. From Direct Calls to a Message Boundary

Suppose an application receives an order-preparation request. With direct calls, the intake component might hold a reference to the processing service:

~~~java
public final class OrderSubmission {
    private final OrderPreparationService preparation;

    public OrderSubmission(OrderPreparationService preparation) {
        this.preparation = preparation;
    }

    public PreparedOrder submit(PrepareOrder command) {
        return preparation.prepare(command);
    }
}
~~~

This design works well when the call-and-return relationship is simple. However, if the intake component also directly calls fraud checks, logging, and notifications, it ends up knowing many details about how the workflow is organized.

With a channel, the producer hands a message to an entry point:

~~~mermaid
flowchart LR
    P["Producer: receive request"] --> C["Channel: orders.prepare"]
    C --> E["Endpoint: transformer"]
    E --> S["POJO: prepare order"]
    E --> O["Channel: orders.prepared"]
~~~

The producer knows where to send and the meaning of the message. Integration configuration decides which endpoint receives it, which service to invoke, and where to send the result. This applies the channel-based flow composition supported by Spring Integration. [Integration Flows Composition Documentation](https://docs.spring.io/spring-integration/reference/dsl/integration-flows-composition.html).

For example, you can swap the order-preparation service or add a validation step before calling the service without adding a dependency on the new service inside the producer. Such changes must still preserve the channel's input contract.

Channels are appropriate when this boundary serves a concrete integration need. If you merely need to call an internal calculation helper, an ordinary Java method call remains the clearer choice.

## 2. Message, Channel, and Endpoint Have Distinct Roles

| Component | Responsibility | Example in This Lesson |
| --- | --- | --- |
| Producer | Creates and sends messages | `OrderPublisher` |
| Message | Carries payload and metadata | `PrepareOrder` along with `requestId` |
| Channel | Provides the handoff point | `orders.prepare` |
| Endpoint | Connects a channel to a processing activity | Endpoint created by `.transform(...)` |
| Business POJO | Performs data processing | `OrderPreparationService` |
| Flow configuration | Wires components together | `OrderFlowConfig` |

`MessageChannel` provides `send(...)` methods. `SubscribableChannel` adds handler subscription; `PollableChannel` adds `receive(...)`. Thus, a producer may depend only on `MessageChannel`, whereas a component actively pulling messages needs `PollableChannel`. [Channel Interfaces Documentation](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

A transformation such as normalizing a customer code belongs to a transformer or a POJO invoked by a transformer. Choosing a processing branch based on content belongs to a router. Conditions for accepting or discarding messages belong to a filter. Channels provide the boundaries where those activities connect.

This division lets you read a flow with two questions:

1. Which boundary is the message at?
2. Which component is responsible for processing at that boundary?

Do not place all business rules inside a channel interceptor merely because the interceptor can inspect messages. That hides business behavior from the flow structure.

## 3. Which Dependencies Can a Channel Decouple?

### 3.1. Dependency on a Concrete Receiver

If a producer holds `OrderPreparationService`, it knows the receiver under a method-call model. If a producer holds `MessageChannel`, Spring configuration connects the send point to the receiving side.

Changing the consumer implementation class may affect only configuration and the consumer. The producer still sends the same request type.

### 3.2. Dependency on Workflow Composition

Behind a channel, you can insert a transformer, filter, or router before the existing consumer. The producer does not have to decide the invocation order of each step.

However, if a new step discards certain requests or alters error reporting, behavior observed from the producer can change. Separating configuration does not exempt you from evaluating the contract.

### 3.3. Dependency on Timing and Resources

A direct-dispatch channel may still force the producer to wait on the consumer. A queue can allow sending now and processing later within capacity limits. An executor can move work onto worker threads.

These are separate execution decisions that should be chosen based on the boundary's needs.

| Dependency Type | How Can a Channel Help? | What Still Must Be Agreed Upon |
| --- | --- | --- |
| Receiver object | Producer does not hold a concrete consumer | Channel name or reference |
| Workflow structure | Configuration determines downstream steps | Meaning of inputs and outputs |
| Data | Message packages payload and headers | Schema, data types, units |
| Timing | A queue can be introduced | Capacity, latency, and timeouts |
| Execution thread | An executor can be used | Errors, ordering, and context |
| Deployment | Adapters can be placed at system boundaries | Protocol, serialization, reliability |

An in-memory channel inside an application does not by itself create a connection between two processes. If you split producer and consumer into two independently deployed services, you still need transport infrastructure, adapters, and matching data contracts.

## 4. A Channel Contract Must Be Clearer Than a Bean Name

Suppose the producer sends to `orders.prepare`. A useful contract should answer the following questions.

| Item | Illustrative Convention |
| --- | --- |
| Purpose | Request to prepare order data |
| Payload | `PrepareOrder` |
| Required fields | `orderId`, `customerCode`, `total` |
| Data rules | Non-blank codes, `total > 0` |
| Required headers | `requestId` of type `String`, `schemaVersion` of type `Integer` |
| Communication model | One request processed by one business flow |
| Output | `PreparedOrder` message on `orders.prepared` |
| Meaning of success | Data was prepared and delivered to the result channel in the synchronous example |
| External side effects | Example does not write to a database or call a payment system |

The names and conventions above are the example's design. In a real project, pick names matching the domain language and document their meanings.

### 4.1. Payload Is Still a Form of Coupling

Using messages does not eliminate data coupling. If the producer sends `String` while the consumer expects `PrepareOrder`, or both use monetary amounts with different units, the boundary still breaks.

For flows within the same application, Java records are a simple contract choice. When crossing a network, you also need representation rules, schema versioning, and compatibility across both sides.

Avoid putting JPA entities attached to a persistence context, HTTP requests, or service beans into payloads for consumers to call back into. Send the data the receiving side needs to fulfill its agreed responsibility.

### 4.2. Headers Are Also Part of the Contract

`requestId` in this lesson is an application-defined header linking steps of the same request. It does not inherently carry deduplication semantics. If used as an idempotency key, you must also define uniqueness scope, retention window, and behavior upon redelivery.

`schemaVersion` is likewise only metadata if no component validates it. Attaching the value `1` does not create a version-management mechanism on its own.

### 4.3. Do Not Share Arbitrarily Mutable State

`Message` wraps payload and headers together; not being able to swap the payload reference on a message does not make the payload object itself deeply immutable. Header values can also be mutable objects. [Message Documentation](https://docs.spring.io/spring-integration/reference/message.html).

Therefore, for payloads containing `List` or `Map`, consider making defensive copies and restricting mutability. If multiple branches see the same mutable object, mutations in one branch can make another branch unpredictable.

The two records in this example contain only `String` and `BigDecimal`, avoiding shared mutable object issues within the illustrative data model.

## 5. Choosing a Channel Also Chooses Part of the Behavior

The options below serve different boundaries:

| Channel | Primary Delivery Style | Design Implications to Note |
| --- | --- | --- |
| `DirectChannel` | Invokes handler on sending thread | Decouples components, yet producer still waits for direct processing |
| `QueueChannel` | Stores messages for receiver to pull | Buffered; requires a consumer to pull messages |
| `ExecutorChannel` | Hands work off to an executor | Requires designing workers, work queues, and rejection handling |
| `PublishSubscribeChannel` | Dispatches to subscribers | Fits scenarios where multiple receivers need the same notification |

`DirectChannel` dispatches to one subscriber per normal processing attempt. `ExecutorChannel` uses an executor for dispatch. Neither provides a single transaction model spanning sender and receiver. [DirectChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html), [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

`QueueChannel` has point-to-point semantics; each message is pulled from the queue by one consumer. `PublishSubscribeChannel` dispatches messages to registered handlers. [Message Channel Implementations Documentation](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

For example, "prepare an order" is normally work requiring one responsible flow. "Order has been prepared" may be an event observed by multiple parties. Clarify this distinction before wiring additional consumers.

Subscribing two consumers to one `DirectChannel` so one saves the order and the other sends an email will not create a workflow guaranteed to execute both steps. If you want sequential execution, chain two endpoints in order. If you want multiple parties to receive the same notification, design an appropriate event-broadcast point.

## 6. Complete Example: Producer Knows Only the Send Point

The example uses Java records and Java DSL with `IntegrationFlow.from(...)`, suitable for Spring Integration 6 and later. The project requires `org.springframework.integration:spring-integration-core`; the test section below requires JUnit Jupiter. Use versions aligned with your project's BOM or dependency configuration.

Each code block with a public class name is placed in a Java file of the same name under package `example.channels`.

Illustrative flow:

~~~text
OrderPublisher
    -> orders.prepare (DirectChannel)
    -> transformer calls OrderPreparationService
    -> orders.prepared (QueueChannel, capacity = 10)
    -> Demo or test pulls the result
~~~

The result queue is the example's observation point. It is not yet a durable event-publishing mechanism for a production system.

### 6.1. Defining Data at the Boundary

File `OrderContracts.java`:

~~~java
package example.channels;

import java.math.BigDecimal;

public final class OrderContracts {

    private OrderContracts() {
    }

    public record PrepareOrder(
            String orderId,
            String customerCode,
            BigDecimal total) {
    }

    public record PreparedOrder(
            String orderId,
            String normalizedCustomerCode,
            BigDecimal total) {
    }
}
~~~

`PrepareOrder` expresses the request; `PreparedOrder` expresses the preparation result. Neither type carries references to consumers or processing infrastructure.

### 6.2. Keeping Business Logic in a POJO

File `OrderPreparationService.java`:

~~~java
package example.channels;

import java.util.Locale;
import java.util.Objects;

import example.channels.OrderContracts.PrepareOrder;
import example.channels.OrderContracts.PreparedOrder;

public final class OrderPreparationService {

    public PreparedOrder prepare(PrepareOrder command) {
        Objects.requireNonNull(command, "command");

        if (command.orderId() == null
                || command.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        if (command.customerCode() == null
                || command.customerCode().isBlank()) {
            throw new IllegalArgumentException("customerCode is required");
        }

        if (command.total() == null
                || command.total().signum() <= 0) {
            throw new IllegalArgumentException("total must be positive");
        }

        return new PreparedOrder(
                command.orderId(),
                command.customerCode().trim().toUpperCase(Locale.ROOT),
                command.total());
    }
}
~~~

This POJO knows only request data and result data. It can be called and tested like an ordinary Java object.

The code-normalization rule in the example is an illustrative business assumption. Do not automatically apply uppercase normalization to every kind of code in a project.

### 6.3. Producer Sends Messages Without Holding the Consumer

File `OrderPublisher.java`:

~~~java
package example.channels;

import java.util.Objects;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import example.channels.OrderContracts.PrepareOrder;

public final class OrderPublisher {

    private final MessageChannel output;

    public OrderPublisher(MessageChannel output) {
        this.output = Objects.requireNonNull(output, "output");
    }

    public void publish(PrepareOrder command, String requestId) {
        Objects.requireNonNull(command, "command");
        Objects.requireNonNull(requestId, "requestId");

        if (requestId.isBlank()) {
            throw new IllegalArgumentException("requestId is required");
        }

        Message<PrepareOrder> message = MessageBuilder
                .withPayload(command)
                .setHeader("requestId", requestId)
                .setHeader("schemaVersion", 1)
                .build();

        boolean sent = output.send(message, 250);

        if (!sent) {
            throw new IllegalStateException(
                    "Could not send order preparation request");
        }
    }
}
~~~

`OrderPublisher` neither imports nor holds `OrderPreparationService`. It knows how to construct a message matching the contract and how to handle the channel returning `false`.

`send(...)` can also throw exceptions. Therefore, the `if (!sent)` branch does not replace designing caller-side error handling. The timeout value uses milliseconds. [MessageChannel Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html).

In the example, `250` is not a deadline for completing all business logic. With `DirectChannel`, the handler still runs inside the send call; send timeout does not automatically interrupt the handler after 250 ms.

### 6.4. Configuration Handles Wiring Components Together

File `OrderFlowConfig.java`:

~~~java
package example.channels;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;

@Configuration
@EnableIntegration
public class OrderFlowConfig {

    @Bean(name = "orders.prepare")
    public MessageChannel orderPreparationRequests() {
        return new DirectChannel();
    }

    @Bean(name = "orders.prepared")
    public PollableChannel preparedOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public OrderPreparationService preparationService() {
        return new OrderPreparationService();
    }

    @Bean
    public OrderPublisher orderPublisher(
            @Qualifier("orders.prepare") MessageChannel requests) {
        return new OrderPublisher(requests);
    }

    @Bean
    public IntegrationFlow prepareOrderFlow(
            @Qualifier("orders.prepare") MessageChannel requests,
            @Qualifier("orders.prepared") PollableChannel results,
            OrderPreparationService preparation) {

        return IntegrationFlow.from(requests)
                .transform(PrepareOrder.class, preparation::prepare)
                .channel(results)
                .get();
    }
}
~~~

Here, `@Qualifier` selects the right channel when the application context has multiple beans of the same type. The named channel is declared explicitly because it is the boundary used by other components.

The Spring configuration knows both the send point and the processing component; that is necessary to wire the flow. Component decoupling is evaluated at the producer and consumer, not by requiring the configuration layer to be "unaware" of the components it connects.

### 6.5. Sending a Request and Reading the Result

File `Demo.java`:

~~~java
package example.channels;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;

public final class Demo {

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowConfig.class)) {

            OrderPublisher publisher =
                    context.getBean(OrderPublisher.class);

            PollableChannel results =
                    context.getBean("orders.prepared", PollableChannel.class);

            publisher.publish(
                    new PrepareOrder(
                            "ORD-101",
                            "  customer-a  ",
                            new BigDecimal("125000")),
                    "REQ-101");

            Message<?> result = results.receive(1_000);

            if (result == null) {
                throw new IllegalStateException("No prepared order received");
            }

            System.out.println(result.getPayload());
            System.out.println(result.getHeaders().get("requestId"));
        }
    }
}
~~~

Expected output contains `orderId=ORD-101`, `normalizedCustomerCode=CUSTOMER-A`, amount `125000`, and header `requestId=REQ-101`.

A typical transformer wraps the result payload into an output message and preserves application headers via the framework's message-handling mechanism. If you later construct a new message manually inside a component, verify which headers must be forwarded.

### 6.6. Where Is the Decoupling Point?

In this example:

- The producer depends on `MessageChannel` and `PrepareOrder`.
- The processing POJO depends on `PrepareOrder` and `PreparedOrder`.
- The integration configuration knows which channels connect to the transformer.
- The result-reading component knows `orders.prepared` and the result contract.

You can change how data is prepared inside the POJO without editing the producer. You can also replace the producer with an inbound adapter as long as the adapter produces messages satisfying the contract.

Producer and POJO still share the data contract. When changing the meaning of `total` or the payload type, both sides must be evaluated.

## 7. Swapping in QueueChannel: Changing Boundary Behavior

Suppose order preparation becomes slow. You want to accept a burst of requests and process them afterward.

Merely changing the `orders.prepare` bean to `QueueChannel` forces the receiving side to pull messages using a polling model. If you keep the endpoint without an appropriate local or default poller, the configuration does not match the new channel's consumption model.

In `OrderFlowConfig`, replace the input bean with:

~~~java
@Bean(name = "orders.prepare")
public PollableChannel orderPreparationRequests() {
    return new QueueChannel(100);
}
~~~

Then replace the `prepareOrderFlow` method with the following variant; add imports `java.time.Duration` and `org.springframework.integration.dsl.Pollers`:

~~~java
@Bean
public IntegrationFlow prepareOrderFlow(
        @Qualifier("orders.prepare") PollableChannel requests,
        @Qualifier("orders.prepared") PollableChannel results,
        OrderPreparationService preparation) {

    return IntegrationFlow.from(requests)
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(Duration.ofMillis(100))
                            .maxMessagesPerPoll(10)))
            .transform(PrepareOrder.class, preparation::prepare)
            .channel(results)
            .get();
}
~~~

This is an alternative version of the previous flow. Do not register two methods with the same bean name or keep both consumers if you only want a single order-preparation flow.

The bridge is an endpoint that receives from the queue using a poller and forwards to the transformation step. Configuring `maxMessagesPerPoll(10)` limits how many messages are taken in a single poll; it does not create ten concurrent workers. Java DSL provides `Pollers` to configure polling endpoints. [Pollers Documentation](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html).

The producer is still injected via `MessageChannel`, so `OrderPublisher` does not need to change. However, operational characteristics have changed:

| Aspect | DirectChannel Version | QueueChannel + Poller Version |
| --- | --- | --- |
| When the producer can return | After the direct processing chain returns or fails | After the message is placed into the queue |
| When business logic runs | On the sending thread | When the poller pulls the message |
| What `send() == true` tells you | Sent successfully through the direct processing path | Accepted by the queue |
| Slow consumer | Send duration increases | Messages can accumulate |
| Consumer fails | Errors can propagate back to the sender | Must monitor polling task errors |
| Business completion | Reasoned along the specific synchronous flow | Requires an explicit result, status, or notification |

A bounded queue can force the sender to block when full. Default `QueueChannel` stores messages in memory; surviving crashes requires configuring appropriate storage. Spring recommends setting an explicit capacity to prevent unbounded queue growth. [QueueChannel Configuration Documentation](https://docs.spring.io/spring-integration/reference/channel/configuration.html).

In the example, both the input queue and result queue are bounded. If nobody reads results, the result queue can fill up and block the output send step. Therefore, adding buffers must be paired with designing consumers for every output.

## 8. Separating Threads Requires Re-examining Transactions and Context

`DirectChannel` lets the sender and handler run on the same thread. If a valid transaction already encloses the call, operations participating in that transaction can be affected by the handler's outcome. The channel does not open a transaction on its own or automatically roll back all resources together. [DirectChannel Documentation](https://docs.spring.io/spring-integration/reference/6.3/channel/implementations.html).

With `ExecutorChannel`, the executor typically runs the handler on another thread. Do not rely on a transaction bound to the calling thread propagating automatically to the worker. Executor policies can also cause the sender to block or run the work on the sending thread in certain situations. [ExecutorChannel Documentation](https://docs.spring.io/spring-integration/reference/7.0/channel/implementations.html).

For example, consider the workflow:

~~~text
1. Record order status in the database.
2. Send payment request across an asynchronous boundary.
3. Worker executes the payment request.
~~~

If step 1 commits but the application stops before the message is safely persisted, step 3 may never occur. If step 3 calls the external service successfully and the worker crashes before updating status, a retry can create duplicate effects.

Based on concrete business requirements, the development team must decide how to persist messages, track state, deduplicate, or use an outbox. Swapping channels does not solve those problems on its own.

Data such as trace info or tenant info must also be propagated intentionally when crossing threads. Do not assume values in the producer's `ThreadLocal` will be present in the consumer.

## 9. Errors Belong to the Decoupling Point's Contract

### 9.1. On a Synchronous Processing Path

In the `DirectChannel` version, if `OrderPreparationService` detects an invalid total, the exception can propagate back from the `publish(...)` call, typically wrapped in a messaging exception.

Thus, the caller can catch errors immediately during the send call. However, whether side effects executed before the failure point are rolled back still depends on transactions and resource types.

### 9.2. On an Asynchronous Processing Path

In the queue version, the producer may have already returned success before the POJO runs. An exception thrown while the poller is processing cannot automatically unwind into the finished Java call stack of the producer.

Spring Integration has a mechanism to emit an `ErrorMessage` for framework-managed tasks. The error handler uses the `errorChannel` header when present, or the configured global error channel. Errors from a poller also have the scheduling task's error-handling path. [Error Handling Documentation](https://docs.spring.io/spring-integration/reference/error-handling.html).

For an asynchronous boundary, define:

- Where unprocessed failed requests are recorded.
- An identifier correlating the error with the original request.
- Which errors are retryable and the retry limit.
- Where requests that still cannot be processed after retries are routed.
- How the caller learns the final status if business rules require it.

An error log aids diagnosis but does not create a recovery workflow on its own. Likewise, the name `errorChannel` does not guarantee durable error storage or automatic redelivery.

If the application pulls messages manually with `receive(...)` and invokes the POJO outside a framework endpoint, the application must handle exceptions in that code itself.

## 10. Gateways Can Further Hide the Messaging API from Callers

In the main example, `OrderPublisher` uses `MessageChannel` and `MessageBuilder` directly. You can place this boundary behind a gateway interface so business code calls a plain Java method.

Alternative interface example for the intake side:

~~~java
package example.channels;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

import example.channels.OrderContracts.PrepareOrder;

@MessagingGateway(defaultRequestChannel = "orders.prepare")
public interface OrderGateway {

    void submit(
            PrepareOrder command,
            @Header("requestId") String requestId,
            @Header("schemaVersion") int schemaVersion);
}
~~~

To let the framework register this annotated interface, enable `@IntegrationComponentScan` in the appropriate configuration, for example:

~~~java
@IntegrationComponentScan(basePackageClasses = OrderGateway.class)
~~~

That annotation belongs to the `org.springframework.integration.annotation` package; add it to the example's `@EnableIntegration` configuration class.

Business code injects `OrderGateway` and calls `submit(command, requestId, 1)`. The gateway proxy builds the message and sends it to the configured channel. A gateway is the framework's way of hiding messaging APIs behind an application interface. [Messaging Gateways Documentation](https://docs.spring.io/spring-integration/reference/gateway.html).

A `void` return type expresses not waiting for a reply value through the method contract. With a `DirectChannel` path, the call still executes the handler synchronously.

If you change the gateway to return `PreparedOrder`, you must design a matching request-reply path. The `orders.prepared` queue in the example is an output read separately; do not merely change the return type and assume the gateway pulls results from that queue automatically.

## 11. Testing the Decoupling Point Without Running All Components Together

Useful tests at a channel boundary should prove that the producer constructs the expected message and that configuration wires the processing flow properly.

The examples below use JUnit Jupiter. They are illustrative code for a project with compatible dependencies.

### 11.1. Testing the Producer with a Substitute Channel

You do not need to start the consumer to verify whether the producer honors the contract.

~~~java
package example.channels;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import example.channels.OrderContracts.PrepareOrder;

import static org.junit.jupiter.api.Assertions.*;

class OrderPublisherTest {

    @Test
    void publishesTheAgreedPayloadAndHeaders() {
        QueueChannel capture = new QueueChannel(1);
        OrderPublisher publisher = new OrderPublisher(capture);

        PrepareOrder command = new PrepareOrder(
                "ORD-201",
                "customer-b",
                new BigDecimal("50000"));

        publisher.publish(command, "REQ-201");

        Message<?> message = capture.receive(0);

        assertNotNull(message);
        assertEquals(command, message.getPayload());
        assertEquals("REQ-201", message.getHeaders().get("requestId"));
        assertEquals(1, message.getHeaders().get("schemaVersion"));
        assertNull(capture.receive(0));
    }

    @Test
    void reportsWhenTheBoundaryCannotAcceptAnotherMessage() {
        QueueChannel capture = new QueueChannel(1);
        OrderPublisher publisher = new OrderPublisher(capture);

        PrepareOrder command = new PrepareOrder(
                "ORD-202",
                "customer-c",
                new BigDecimal("60000"));

        publisher.publish(command, "REQ-202");

        assertThrows(
                IllegalStateException.class,
                () -> publisher.publish(command, "REQ-203"));
    }
}
~~~

The first test uses a queue as a message-capturing sink. It proves the producer does not need the real handler class to fulfill its responsibility.

The second test deterministically fills the queue to verify the failed-send branch. It does not prove behavior when a consumer throws an exception; that is a separate scenario.

### 11.2. Testing the Flow Wiring Configuration

~~~java
package example.channels;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

import example.channels.OrderContracts.PrepareOrder;
import example.channels.OrderContracts.PreparedOrder;

import static org.junit.jupiter.api.Assertions.*;

class OrderFlowTest {

    @Test
    void connectsThePublisherToPreparationAndResult() {
        try (var context =
                new AnnotationConfigApplicationContext(OrderFlowConfig.class)) {

            OrderPublisher publisher =
                    context.getBean(OrderPublisher.class);

            PollableChannel results =
                    context.getBean("orders.prepared", PollableChannel.class);

            publisher.publish(
                    new PrepareOrder(
                            "ORD-301",
                            "  customer-d  ",
                            new BigDecimal("99000")),
                    "REQ-301");

            Message<?> message = results.receive(1_000);

            assertNotNull(message);

            PreparedOrder result =
                    assertInstanceOf(PreparedOrder.class, message.getPayload());

            assertEquals("ORD-301", result.orderId());
            assertEquals("CUSTOMER-D", result.normalizedCustomerCode());
            assertEquals(new BigDecimal("99000"), result.total());
            assertEquals("REQ-301", message.getHeaders().get("requestId"));
            assertEquals(1, message.getHeaders().get("schemaVersion"));
        }
    }
}
~~~

The test retrieves the result with an explicit timeout. It verifies bean names, endpoint wiring, transformations, and metadata crossing the boundary.

If switched to the queue variant, this test can still await the result within a timeout, but should add asynchronous error-handling cases matching the chosen error mechanism.

### 11.3. Conclusions These Tests Do Not Provide

The tests above do not prove:

- Messages survive an application restart.
- Completion order when multiple workers run concurrently.
- Consumers avoid duplicate side effects after retries.
- Throughput or latency meets operational requirements.
- All headers are compatible when sent through a broker.

Add such checks only when the real boundary has those requirements. Replacing the consumer with a test double is sufficient to verify a simple producer contract.

## 12. Organizing Boundaries to Keep Flows Maintainable

### 12.1. Name by Business Meaning

Names such as `orders.prepare`, `orders.prepared`, and `orders.rejected` express intent better than `channel1` or `toServiceB`.

If a producer must rename a channel whenever a consumer renames its class, the channel name reflects implementation details too closely.

Clear names also help operators understand metrics and logs. However, a name containing the word "prepared" does not prove the order was durably saved; that meaning must live in the contract.

### 12.2. Expose Only Channels That Need Reuse

You do not need to name and expose every internal connection created by the DSL. Identify which boundaries are genuinely used by other modules, gateways, adapters, or tests.

A module can expose one input channel and one result contract while keeping transformer and endpoint details private inside its configuration.

### 12.3. Keep Flow Wiring Out of Business POJOs

If `OrderPreparationService` injects `FraudChannel`, picks channel names based on consumer classes, and awaits results via its own mechanism, the POJO begins taking on integration orchestration.

When splitting branches or merging results is needed, consider expressing them with routers, internal gateways, or aggregators in integration configuration. Concrete decisions must follow flow requirements.

### 12.4. Observe What You Actually Need to Know

At an intake boundary, successful send counts reflect message delivery under the channel's semantics. To measure business completion, observe a point carrying the corresponding completion meaning.

With queues, you may need to track queued message counts, wait times, consumption rates, and error counts. With executors, observe workers and rejected tasks. These metrics distinguish processing errors from boundary overload.

## 13. Common Misconceptions

| Misconception | Understanding to Adjust |
| --- | --- |
| Having a channel makes every step asynchronous | Inspect the actual implementation and endpoint |
| Because the producer does not know the consumer, no coupling remains | Both sides still share data and behavioral contracts |
| `send() == true` means the order is complete | Clarify which boundary success applies to |
| Send timeout is business timeout | Send timeout does not automatically bound all handlers |
| Swapping `DirectChannel` for a queue is enough | Also address pollers, capacity, error paths, and completion tracking |
| Multiple subscribers on any channel all receive every message | Distinguish work distribution from event broadcasting |
| Having a queue implies durable storage | Configure an explicit persistence mechanism |
| Queues always preserve business completion order | Pull order differs from completion order under parallel processing |
| Adding retries guarantees no lost or duplicate effects | Evaluate failure points, persistence, and idempotency |
| Every exception automatically goes to `errorChannel` | Account for synchronous paths, framework tasks, and error settings |

When a seemingly simple "channel swap" changes transactions, errors, or latency, update the contract and tests for that exact change.

## 14. Reinforcement Exercises

Perform each step in a learning project with Spring Integration:

1. Create the example classes and test the producer using a message-capturing queue.
2. Run the `DirectChannel` flow and verify the payload and `requestId` at the output.
3. Log the current thread inside the producer and POJO to observe execution.
4. Replace the input with a bounded queue and add a poller as shown in the variant.
5. Observe the difference between when the producer returns and when the result becomes available.
6. Send a request with `total <= 0`; compare how errors are observed across the two variants.
7. Stop consuming results, send multiple requests, and analyze the impact of a full output queue.
8. Rewrite the channel contract in clear sentences covering acceptance, completion, and errors.

Questions to answer for yourself after practicing:

- If you replace `OrderPreparationService` with another implementation while preserving the contract, what does the producer need to change?
- If you move the consumer to a separate service, besides the channel name, what pieces are still missing?
- If you add an email sender, do you want sequential execution or broadcasting one event to multiple parties?
- If the producer already returned but the consumer fails, who is responsible for knowing and recovering the request?
- Which data are you using to prove an order has completed processing?

Being able to answer these questions clearly shows you have defined component communication boundaries along with data and operational responsibilities at each boundary.
