# Input Channel of a Service Activator

In the **SPRING_INTEGRATION_CORE** module, chapter **Service activator**, this lesson explains how to connect a service to a message flow through an input channel. Choosing the channel directly affects how the endpoint receives messages, the execution thread, waiting behavior, work distribution, and error paths.

After this lesson, you will be able to:

- Identify the input channel of a service activator in annotations and Java DSL.
- Distinguish between subscription-based and polling-based mechanisms.
- Select a channel based on the need for synchronous invocation, work buffering, or event broadcasting.
- Configure a poller when the input is a `QueueChannel`.
- Test input paths, results, and errors without relying on fixed sleep durations.

## 1. The Input Channel Is the Endpoint's Message Receiving Point

A service activator connects a Spring-managed object to the messaging system. The input channel supplies messages to the endpoint; the handler inside the endpoint turns the message into a business method invocation. The return value can then be sent out to the message flow. See [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html).

~~~mermaid
flowchart LR
    P["Producer or gateway"] -->|"send(Message)"| C["Input channel"]
    C --> E["Consumer endpoint"]
    E --> H["Service activator handler"]
    H --> S["Business method"]
    S -->|"If result produced"| O["Output channel or replyChannel"]
~~~

Example with an order confirmation request:

~~~text
OrderCommand
    -> orderInput
    -> service activator
    -> OrderService.confirm(...)
    -> confirmations
~~~

Here:

| Component | Responsibility |
| --- | --- |
| Producer | Creates messages and sends them to `orderInput` |
| `orderInput` | Provides the delivery or message-buffering mechanism |
| Consumer endpoint | Connects the channel to the handler and manages consumption |
| Handler | Maps the message to a call to `confirm(...)` |
| `OrderService` | Executes the order confirmation business logic |
| `confirmations` | Receives the result returned by the service |

The input channel name is a messaging destination name in the `ApplicationContext`, not a URL and not a Java method name.

The word "input" is relative: the same channel can be the output of a router in the preceding step and the input of a service activator in the next step. Therefore, when reading a flow, identify both the component sending to the channel and the endpoint consuming it.

## 2. Channel Type Determines How the Endpoint Receives Messages

`MessageChannel` provides the `send(...)` operation. Two important interfaces for the receiving side are:

- `SubscribableChannel`: manages handlers registered to receive messages via `subscribe(...)`.
- `PollableChannel`: provides `receive(...)` so the consumer side can actively pull messages.

These are two different contracts; not every channel can be read using `receive()`. See [MessageChannel interfaces](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

Spring Integration organizes consumer endpoints accordingly:

| Input channel | Consumption mechanism | Typical endpoint |
| --- | --- | --- |
| `SubscribableChannel` | Registers handler; channel dispatches when a message arrives | `EventDrivenConsumer` |
| `PollableChannel` | Schedules polling for messages and then invokes the handler | `PollingConsumer` |

With a subscribable channel, the endpoint does not need a poller just to receive messages. With a pollable channel, a scheduling mechanism is required for receiving. That mechanism belongs to the endpoint; the business service stays focused on its handler method. See [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

Keep two questions separate:

1. Does the endpoint receive messages via subscription or polling?
2. Which thread does the handler execute on?

Subscribing does not imply running on the producer's thread. For instance, an `ExecutorChannel` is subscribable yet hands work off to an executor.

## 3. Complete Example with DirectChannel and Annotations

The example below uses Java 17 or later to declare `record` types. The application requires the `spring-integration-core` dependency; tests require JUnit Jupiter. Spring and Spring Integration versions should be managed consistently via your project's dependency configuration.

This is a plain Java configuration that can be initialized with `AnnotationConfigApplicationContext`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.handler.annotation.Header;

@Configuration
@EnableIntegration
public class OrderInputConfiguration {

    public record OrderCommand(String orderId, int quantity) {
    }

    @Bean
    public DirectChannel orderInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel confirmations() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    public static class OrderService {

        @ServiceActivator(
                inputChannel = "orderInput",
                outputChannel = "confirmations")
        public String confirm(
                OrderCommand command,
                @Header(value = "tenantId", required = false)
                String tenantId) {

            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be greater than 0");
            }

            return "CONFIRMED:" + command.orderId();
        }
    }
}
~~~

`@EnableIntegration` registers the infrastructure that processes endpoints. `OrderService` is created as a Spring bean via `@Bean`, so the annotation on its method is processed. If you simply instantiate `new OrderService()` and keep it outside the Spring context, no endpoint will automatically register with the channel. Payload and header reception is described in [Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html).

The producer sends to the channel as follows:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

try (var context =
        new AnnotationConfigApplicationContext(
                OrderInputConfiguration.class)) {

    var input = context.getBean("orderInput", DirectChannel.class);
    var output = context.getBean("confirmations", QueueChannel.class);

    Message<?> request = MessageBuilder
            .withPayload(
                    new OrderInputConfiguration.OrderCommand(
                            "OD-001", 2))
            .setHeader("tenantId", "tenant-a")
            .build();

    boolean sent = input.send(request);
    Message<?> reply = output.receive(0);

    System.out.println(sent);               // true
    System.out.println(reply.getPayload()); // CONFIRMED:OD-001
}
~~~

The snippet above is client code inside a method or a test.

### 3.1. Execution Path Through DirectChannel

With this configuration, the call path is:

~~~text
Producer thread
    -> orderInput.send(message)
    -> service activator handler
    -> OrderService.confirm(...)
    -> confirmations.send(reply)
    -> send(message) returns
~~~

`DirectChannel` invokes a single subscriber on the sending thread. In the example, when `send(...)` returns normally, `confirm(...)` has already completed and the reply has already been placed into `confirmations`. If the method throws an error, the send call can receive an exception. See [DirectChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html).

This also reveals a practical consequence: if `confirm(...)` calls an external service that takes two seconds, the producer can be blocked for that duration. The timeout parameter on the channel send operation does not impose a two-second deadline on the running business logic.

### 3.2. Input Channel and Output Channel Have Independent Roles

In the example, the input is a `DirectChannel` while the output is a `QueueChannel`. The endpoint consumes `orderInput`, so it needs no poller; `confirmations` is read directly by the client code.

If you add another endpoint to automatically consume `confirmations`, that new endpoint will need a poller because its own input is a `QueueChannel`.

The service returning a `String` does not turn `send(...)` into a method that returns the business result. `send(...)` still returns a `boolean`; the reply travels through a channel. If no output channel is configured, the service activator can use the request's `replyChannel` header. A gateway is the right choice when calling code wants to receive the result through a method contract. See [Service Activator reply mechanism](https://docs.spring.io/spring-integration/reference/service-activator.html).

## 4. Switching Input to QueueChannel: Adding a Buffer and Poller

Suppose a new requirement is to accept a batch of orders and process them in the background. You can replace the `orderInput` bean in the previous example with:

~~~java
@Bean
public QueueChannel orderInput() {
    return new QueueChannel(100);
}
~~~

At the same time, replace the annotation on `confirm(...)` with:

~~~java
import org.springframework.integration.annotation.Poller;

@ServiceActivator(
        inputChannel = "orderInput",
        outputChannel = "confirmations",
        poller = @Poller(
                fixedDelay = "100",
                maxMessagesPerPoll = "5",
                receiveTimeout = "0"))
public String confirm(
        OrderCommand command,
        @Header(value = "tenantId", required = false)
        String tenantId) {

    if (command.quantity() <= 0) {
        throw new IllegalArgumentException(
                "quantity must be greater than 0");
    }

    return "CONFIRMED:" + command.orderId();
}
~~~

These are replacements inside `OrderInputConfiguration`, not additional beans or endpoints. Producer code must also retrieve the bean as a `QueueChannel` or `MessageChannel` instead of `DirectChannel`.

### 4.1. What Changes When Sending a Message?

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as orderInput: QueueChannel
    participant W as PollingConsumer
    participant S as OrderService
    participant O as confirmations
    P->>Q: send(message)
    Q-->>P: true if enqueued
    Note over P,Q: Producer can continue its work
    W->>Q: receive(...)
    Q-->>W: message
    W->>S: confirm(command)
    S-->>W: result
    W->>O: send(reply)
~~~

`QueueChannel` uses a queue with configurable capacity. With `new QueueChannel(100)`, 100 is the maximum number of messages waiting in the queue, not the number of worker threads. You can inspect `getQueueSize()` and `getRemainingCapacity()` to monitor pending work. See [QueueChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

In a typical polling configuration, the producer enqueues while the consumer processes on a thread from the poller infrastructure. `send(...)` returning `true` does not prove the order has been confirmed; you must receive the reply or a separate outcome event.

### 4.2. Understanding Poller Parameters Accurately

| Parameter | Meaning in the example |
| --- | --- |
| `fixedDelay = "100"` | Waits 100 ms after the previous poll completes, in a configuration that does not hand off polls to a separate executor |
| `maxMessagesPerPoll = "5"` | Limits the number of messages consumed in one poll cycle |
| `receiveTimeout = "0"` | Does not wait further when a receive attempt sees an empty queue |

`maxMessagesPerPoll` does not configure the number of workers and does not guarantee fixed throughput. `receiveTimeout` bounds how long to wait for a message at the input, not the runtime of `confirm(...)`. See [Poller API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

In the example, five messages does not mean five messages run concurrently. With a single consumer and no additional executor, they are processed sequentially within the poll cycle.

Sample calculation: suppose each message takes 40 ms, the queue always has work available, and each cycle processes all five messages. One cycle takes roughly 200 ms, followed by a 100 ms delay. The estimated throughput is `5 / 0.3 ≈ 16.7 messages/second`, excluding infrastructure overhead. This is an estimate from the example's assumptions, not a framework performance guarantee.

### 4.3. Full Queue and Send Timeout

Producers should explicitly decide how to react when space runs out:

~~~java
boolean accepted = input.send(request, 200);

if (!accepted) {
    throw new IllegalStateException(
            "Could not enqueue request within timeout");
}
~~~

With a bounded queue, the timeout above allows waiting up to 200 ms for free space. Sending without a timeout can block indefinitely when the queue is full. Aside from a `false` return value, calling code must still handle exceptions thrown during sending. See [QueueChannel behavior](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

For an HTTP producer, that decision might translate into a temporary rejection response. For an internal job, it might lead to an application-designed retry mechanism. Setting a larger capacity only extends buffering room; it does not make the service process faster.

### 4.4. The Poller Lives on the Consumer Endpoint

A `QueueChannel` does not spawn a background task on its own. The endpoint consuming the queue needs its own poller or a global default poller.

The global default poller is a `PollerMetadata` configuration named `PollerMetadata.DEFAULT_POLLER`. It is used for polling endpoints that do not declare their own poller within the same context. In this learning example, declaring the poller directly on the service activator makes the full relationship between queue and consumer visible. See [Global Default Poller](https://docs.spring.io/spring-integration/reference/endpoint.html#global-default-poller).

Do not add a poller to a service activator whose input is a `DirectChannel` expecting it to automatically become asynchronous. Choose the channel and execution model that match the requirement.

## 5. Same Idea Using Java DSL

Java DSL describes a flow as a chain of operations. When the input is an existing channel, `IntegrationFlow.from(...)` defines the entry point; `.handle(...)` here creates the service activator step.

The following example is a standalone configuration. Each implementation approach should be tested in its own context; do not register multiple examples at once and accidentally create unintended consumers.

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class DslOrderConfiguration {

    public record OrderCommand(String orderId, int quantity) {
    }

    @Bean
    public QueueChannel dslOrderInput() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel dslConfirmations() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel dslOrderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public PlainOrderService plainOrderService() {
        return new PlainOrderService();
    }

    @Bean
    public IntegrationFlow queuedOrderFlow(
            PlainOrderService plainOrderService) {

        return IntegrationFlow.from("dslOrderInput")
                .handle(
                        plainOrderService,
                        "confirm",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(
                                                Duration.ofMillis(100))
                                        .maxMessagesPerPoll(5)
                                        .receiveTimeout(0)
                                        .errorChannel("dslOrderErrors")))
                .channel("dslConfirmations")
                .get();
    }

    public static class PlainOrderService {

        public String confirm(OrderCommand command) {
            if (command.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be greater than 0");
            }

            return "CONFIRMED:" + command.orderId();
        }
    }
}
~~~

In this configuration:

- `dslOrderInput` is the queue the producer sends into.
- The poller is attached to the `.handle(...)` endpoint because that endpoint consumes the queue.
- `dslConfirmations` receives successful results.
- `dslOrderErrors` receives errors published by the poller's error handling when the request does not specify another error channel.
- `PlainOrderService.confirm(...)` is a regular Java method.

`Pollers` provides builders for configuring endpoint pollers in the DSL. See [Java DSL Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html) and [Pollers API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

If you switch this flow to a `DirectChannel` input, replace the channel bean and remove the `endpoint.poller(...)` configuration. Do not just rename the Java variable: the referenced bean type is what determines the consumption model.

Do not leave `@ServiceActivator(inputChannel = "...")` on the same method if you are using the DSL to create the endpoint in its place. Each endpoint declaration can result in a separate consumer.

## 6. Choosing an Input Channel by Desired Behavior

| Channel | Receiving mode | Typical processing thread | Best fit |
| --- | --- | --- | --- |
| `DirectChannel` | Subscribe | Producer thread | Single synchronous processing step |
| `ExecutorChannel` | Subscribe | Executor thread | Handing off work to an executor |
| `QueueChannel` | Poll | Consumer/poller thread | Buffering work, controlling pull pace |
| `PublishSubscribeChannel` | Subscribe | Producer or executor thread depending on config | Broadcasting events to multiple subscribers |

### 6.1. ExecutorChannel: Handing Off via an Executor

`ExecutorChannel` dispatches using an `Executor`, typically allowing the producer to proceed before the handler finishes. It does not need a poller. Switching threads also means transactions bound to the producer thread do not automatically accompany the handler call. See [ExecutorChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/ExecutorChannel.html).

When choosing this type, define the pool size, executor queue, and task rejection policy. When the executor is overloaded, the send operation can still fail. If you use a synchronous executor or caller-runs policy, you cannot assume the handler always runs on a different thread.

This is a reasonable fit for "hand off tasks to a pool upon receipt", whereas a queue with a poller additionally expresses active pulling and pacing of work.

### 6.2. One Selected Consumer or Multiple Subscribers?

`DirectChannel` and `QueueChannel` have point-to-point semantics. If two service activators share the same input, do not expect both to process every message. With `DirectChannel`, the dispatcher selects a handler; failover can try another handler when one fails. Thus, point-to-point is not an exactly-once business processing guarantee either. See [channel dispatching and failover](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

If the requirement is to notify multiple places, `PublishSubscribeChannel` delivers to subscribers. Without a configured executor, it invokes subscribers on the sending thread; with an executor, it dispatches work via that executor. See [PublishSubscribeChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/PublishSubscribeChannel.html).

Design example:

~~~text
orderCommands: point-to-point
    -> one consumer confirms the order

orderConfirmedEvents: publish-subscribe
    -> subscriber sends email
    -> subscriber updates report
~~~

Broadcasting does not automatically guarantee all subscribers finish when one branch fails. If each branch needs independent error handling and retries, represent those branches explicitly with separate channels in the design.

## 7. Message Contract at the Input Channel

The input channel determines delivery mechanics; the business method still needs matching payload and headers.

Method example:

~~~java
public String confirm(
        OrderCommand command,
        @Header("tenantId") String tenantId) {
    // Business processing.
    return "CONFIRMED:" + command.orderId();
}
~~~

In this signature, `tenantId` is a required header. If you want to allow a missing header as in the first configuration example, use `required = false`.

If an external source sends a JSON string, putting that string into `orderInput` does not implicitly prove it will be converted to `OrderCommand` according to the business contract. Configure conversion explicitly and test with realistic input data. Parameter mapping mechanics are described in [ServiceActivator API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/ServiceActivator.html).

A flow can be arranged as follows:

~~~text
JSON from adapter
    -> transformer creates OrderCommand
    -> filter checks acceptance criteria
    -> router selects flow by order type
    -> orderInput
    -> service activator invokes business logic
~~~

If the preceding step is an aggregator, determine whether the grouped payload is a single order, a list of orders, or a composite object. For example, a `List<OrderCommand>` payload requires a matching method or a transformation step before reaching a handler expecting `OrderCommand`.

In multi-tenant flows, document the contract clearly: payload type, tenant header, request ID for correlation, and business key for duplicate detection. This allows producers and services to evolve independently while staying aligned on the input.

## 8. Error and Transaction Boundaries

### 8.1. Synchronous Send via DirectChannel

With `DirectChannel` in the annotation example, errors raised during processing can propagate back to the `send(...)` caller, usually wrapped in a Spring Messaging exception. Merely attaching an `errorChannel` header does not automatically redirect every error from a direct send to that channel.

### 8.2. Consuming a Queue on a Poller Thread

In a queue flow, the producer may have already returned from the send call before a business error occurs. When using the polling infrastructure's default error mechanism, errors are published as an `ErrorMessage`. The `errorChannel` header on the request takes precedence; if absent, the system uses the error handler's default error channel.

The DSL above sets the poller's default to `dslOrderErrors`. The application must consume that channel to log or handle errors; tests can read it directly with `receive(timeout)`. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

### 8.3. Queues Do Not Automatically Provide Durability or Redelivery

`new QueueChannel(100)` stores messages in memory. It does not automatically become a durable queue across application restarts. When durability is required, choose an appropriate message store or messaging infrastructure. See [storage of queue-based channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

For the in-memory queue in the example, do not assume a message already taken out will automatically return to the queue if `confirm(...)` fails. Error paths, retries, and redelivery behavior must be designed explicitly. A retry can also repeat side effects executed before the failure occurred; the business logic should have an idempotency key such as `orderId`.

A `DirectChannel` stays on the same thread, so it can preserve the caller's transaction when resources and transaction managers are configured appropriately. When moving to an executor or poller, do not assume a transaction bound to the caller's thread propagates to the consumer. If a transaction is needed around a poll cycle, configure it at the polling boundary. See [channel transactions](https://docs.spring.io/spring-integration/reference/channel/implementations.html) and [Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html).

## 9. Testing the Service Activator's Input Path

The following tests use the two standalone configurations presented above. These are illustrative snippets for your project's test suite; they do not require calling HTTP adapters or a broker.

### 9.1. DirectChannel: Result Appears Within the Same Send Call

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class DirectOrderInputTest {

    @Test
    void shouldInvokeServiceAndProduceReply() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        OrderInputConfiguration.class)) {

            var input =
                    context.getBean("orderInput", DirectChannel.class);
            var output =
                    context.getBean("confirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new OrderInputConfiguration.OrderCommand(
                                    "OD-001", 2))
                    .setHeader("tenantId", "tenant-a")
                    .build();

            assertTrue(input.send(request));

            var reply = output.receive(0);
            assertNotNull(reply);
            assertEquals("CONFIRMED:OD-001", reply.getPayload());
        }
    }

    @Test
    void shouldPropagateFailureToSender() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        OrderInputConfiguration.class)) {

            var input =
                    context.getBean("orderInput", DirectChannel.class);
            var output =
                    context.getBean("confirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new OrderInputConfiguration.OrderCommand(
                                    "OD-INVALID", 0))
                    .build();

            assertThrows(
                    MessagingException.class,
                    () -> input.send(request));

            assertNull(output.receive(0));
        }
    }
}
~~~

`receive(0)` is appropriate here because the processing path to the output has not switched threads. The second test verifies both that the caller receives the error and that no successful reply is emitted.

### 9.2. QueueChannel: Waiting for Results and Checking ErrorMessage

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class QueuedOrderInputTest {

    @Test
    void shouldProcessQueuedCommand() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        DslOrderConfiguration.class)) {

            var input =
                    context.getBean("dslOrderInput", QueueChannel.class);
            var output =
                    context.getBean("dslConfirmations", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new DslOrderConfiguration.OrderCommand(
                                    "OD-002", 3))
                    .build();

            assertTrue(input.send(request, 200));

            var reply = output.receive(3000);
            assertNotNull(reply);
            assertEquals("CONFIRMED:OD-002", reply.getPayload());
        }
    }

    @Test
    void shouldPublishFailureFromPoller() {
        try (var context =
                new AnnotationConfigApplicationContext(
                        DslOrderConfiguration.class)) {

            var input =
                    context.getBean("dslOrderInput", QueueChannel.class);
            var output =
                    context.getBean("dslConfirmations", QueueChannel.class);
            var errors =
                    context.getBean("dslOrderErrors", QueueChannel.class);

            var request = MessageBuilder
                    .withPayload(
                            new DslOrderConfiguration.OrderCommand(
                                    "OD-INVALID", 0))
                    .build();

            assertTrue(input.send(request, 200));

            var error = assertInstanceOf(
                    ErrorMessage.class,
                    errors.receive(3000));

            var failure = assertInstanceOf(
                    MessagingException.class,
                    error.getPayload());

            assertNotNull(failure.getFailedMessage());
            assertEquals(
                    request.getPayload(),
                    failure.getFailedMessage().getPayload());

            assertNull(output.receive(0));
        }
    }
}
~~~

The 3000 ms timeout is a wait bound for the test, not a processing-time SLA for the application. In high-load environments, pick an appropriate timeout. Waiting for a message on a channel allows the test to proceed as soon as the result arrives, instead of always sleeping for a fixed duration.

To additionally test buffer behavior, you can use a `QueueChannel(1)` with no consumer: the first send with timeout 0 succeeds, and the second send with timeout 0 fails. That verifies acceptance behavior; business outcomes must still be tested through the actual endpoint.

## 10. Diagnosing Input Channel Configuration Issues

| Symptom | What to check | How to resolve |
| --- | --- | --- |
| Sending to `DirectChannel` reports no subscribers | Whether the endpoint was created and started; whether the producer uses the same channel instance | Check the service bean, Integration infrastructure, channel name, and endpoint lifecycle |
| Queue has messages but service does not run | Whether a poller exists, is running, and has a valid schedule | Declare a dedicated poller or default poller; check initialization errors |
| Producer waits a long time | Slow direct handler, full queue, or overloaded executor | Measure processing time and backlog; check capacity and timeouts |
| Two handlers do not both receive every message | Channel has point-to-point semantics | Use publish-subscribe or split branches when broadcasting events |
| `send()` succeeds but business logic fails | Input uses a queue or executor | Observe reply/error channels with a correlation ID |
| After switching to a queue, errors no longer reach the caller | Consumer runs across a handoff boundary | Consume `ErrorMessage` and design failure handling |
| Handler parameter mismatch | Payload or header violates the contract | Check transformers, actual payload type, and required headers |
| Service returns a result but flow fails at reply step | Missing reply destination or full output | Check output channel, `replyChannel`, and downstream consumers |

With `@ServiceActivator`, an input channel name that does not yet exist can be automatically registered by the framework as a `DirectChannel`. Because of this, a typo does not necessarily show up as a "bean not found" error; the endpoint may simply be listening on a different channel than the producer. Explicitly declaring channels and testing the real send path helps catch this early. See [ServiceActivator.inputChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/ServiceActivator.html#inputChannel()).

## 11. Applying This to an Order Processing Flow

Suppose a system receives orders in batches and needs to confirm each order:

1. An adapter brings external data into the system as a `Message`.
2. A transformer produces an `OrderCommand` payload with a clear contract.
3. A filter drops unaccepted requests; a router selects processing groups when needed.
4. `orderInput` is a queue with a capacity sized for the allowed buffering level.
5. The service activator pulls messages via a poller and invokes the confirmation service.
6. Successful results go to the results channel; failures go to the error-handling branch.
7. If multiple results need to be grouped per batch, an aggregator is placed downstream with its own correlation and release strategy.

When choosing the input for step 5, record three concrete decisions: whether the producer needs to wait for processing to finish, how much work is allowed to queue up, and how the system acknowledges failures. Those decisions guide choosing the right channel, configuring the endpoint, and writing tests closely aligned with business requirements.
