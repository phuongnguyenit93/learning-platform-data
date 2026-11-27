# MessageHandler and the handleMessage Contract

## Objectives

In Spring Integration, a message flow connects from a channel through an endpoint to a consumer and a handler. The endpoint manages how a handler is registered, invoked, and stopped across the application lifecycle; the consumer decides whether messages are received in an event-driven or polling manner; and `MessageHandler` defines the contract for processing a single message.

`MessageHandler` is a Spring Messaging abstraction used by Spring Integration as the execution point for many endpoint types. Its contract centers on a single method:

~~~java
void handleMessage(Message<?> message) throws MessagingException;
~~~

The method receives the full `Message`, processes it, and finishes either by returning normally or by throwing an exception. It has no return value. Therefore, when designing a handler, you need to clearly define which payloads are accepted, which headers must be preserved, how errors are propagated, and whether the result needs to produce a reply message.

## 1. Where Does MessageHandler Fit in the Message Flow?

A message flow typically takes the following form:

~~~mermaid
flowchart LR
    A[Producer] --> B[MessageChannel]
    B --> C[Endpoint]
    C --> D[Consumer]
    D --> E[MessageHandler]
    E --> F[Business logic]
    E -. reply if any .-> G[Output channel]
~~~

The components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| **MessageChannel** | Transports messages to consumers or subscribers |
| **Endpoint** | Connects the handler to the channel, applies configuration, and manages the lifecycle |
| **Consumer** | Receives messages via a subscribe or poll mechanism |
| **MessageHandler** | Executes processing on a single `Message` |
| **Reply/output channel** | Receives the result when the flow has a reply-producing step |

In Spring Integration, the endpoint typically creates and manages handler registration. For example, an event-driven endpoint registers the handler as a subscriber on a `SubscribableChannel`; a polling consumer fetches messages from a `PollableChannel` and then invokes the handler. Thanks to the endpoint, the handler does not need to manage subscriptions, polling schedules, or channel lifecycles on its own.

At a low API level, a `MessageHandler` is simply an object that can be invoked with a message. In real-world applications, you should let `IntegrationFlow` or endpoints such as a service activator manage wiring the handler into the flow.

## 2. The MessageHandler Contract

The interface resides in the `org.springframework.messaging` package:

~~~java
package org.springframework.messaging;

import org.springframework.messaging.MessagingException;

@FunctionalInterface
public interface MessageHandler {

    void handleMessage(Message<?> message) throws MessagingException;

}
~~~

Key points of the contract:

- The input is a `Message`, consisting of a payload and headers.
- The method returns `void`; the handler does not return a reply via `return`.
- Processing errors can be represented by `MessagingException` or unchecked exceptions.
- When the method completes normally, the handler invocation is considered complete.
- Retry, persistence, transactions, and error routing depend on the endpoint, channel, and surrounding flow configuration.

`Message` uses a wildcard because a handler can receive messages carrying many payload types. The handler must determine the data type its business logic accepts, then validate or convert the payload accordingly. You should not assume every message entering a channel has the same type if the channel is shared by multiple producers.

## 3. A Message Consists of Payload and Headers

`Message<T>` is the envelope containing business data and metadata:

~~~java
public interface Message<T> {

    T getPayload();

    MessageHeaders getHeaders();

}
~~~

An example of a simple message:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-1001")
        .setHeader("source", "checkout")
        .setHeader("tenantId", "tenant-a")
        .build();
~~~

In this example:

- The payload is the string `order-1001`.
- The `source` header indicates the source that emitted the message.
- The `tenantId` header provides tenant context for the processing step.

The handler can read the two parts separately:

~~~java
@Override
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();
    MessageHeaders headers = message.getHeaders();

    String source = headers.get("source", String.class);
    String tenantId = headers.get("tenantId", String.class);

    // Validate the payload and execute business logic.
}
~~~

### 3.1. Payload

The payload is the content the flow needs to process, such as an `Order`, a `String`, an event, or a DTO. The handler should validate the payload type and state at the input boundary, especially when the channel has multiple producers.

Example:

~~~java
@Override
public void handleMessage(Message<?> message) {
    Object payload = message.getPayload();

    if (!(payload instanceof Order)) {
        throw new IllegalArgumentException(
                "Expected Order payload but received: "
                        + (payload == null
                                ? "null"
                                : payload.getClass().getName()));
    }

    Order order = (Order) payload;
    orderService.process(order);
}
~~~

This is a minimal type check. In real systems, you also need to validate required fields and business rules. If the payload can be `null` according to your application's contract, handle that case before calling `getClass()` or casting.

### 3.2. Headers

Headers carry metadata that controls or describes the message: ID, timestamp, content type, correlation, sequence, reply channel, error channel, and application-specific metadata.

`MessageHeaders` provides a read-only view. Do not modify headers by treating them as a writable `Map`. When you need to change metadata or the payload, create a new message using `MessageBuilder`.

~~~java
Message<Order> enrichedMessage = MessageBuilder
        .fromMessage(originalMessage)
        .setHeader("validated", true)
        .setHeader("handlerVersion", "v2")
        .build();
~~~

Creating a new message preserves a clear boundary between the input message and the metadata-enriched message. When forwarding a message, decide which headers need to be preserved. In particular, do not arbitrarily remove or overwrite correlation, sequence, reply channel, or error channel headers because downstream components may rely on them.

The message envelope is immutable at the API level, but that does not mean the payload is always immutable. If the payload is a mutable object and multiple consumers or threads reference that same object, mutating it can create race conditions. Prefer immutable DTOs or create a copy when data transformation is needed.

## 4. Implementing MessageHandler

A handler can be implemented as a dedicated class:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

public class AuditMessageHandler implements MessageHandler {

    private final AuditService auditService;

    public AuditMessageHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handleMessage(Message<?> message) {
        auditService.record(
                message.getPayload(),
                message.getHeaders());
    }
}
~~~

Registering the handler into an `IntegrationFlow`:

~~~java
@Bean
public IntegrationFlow auditFlow(AuditMessageHandler auditHandler) {
    return IntegrationFlow.from("auditChannel")
            .handle(auditHandler)
            .get();
}
~~~

In this example, `IntegrationFlow` creates an endpoint connecting `auditChannel` to the handler. When a message arrives on the channel, the endpoint invokes `handleMessage`. The handler class focuses solely on the audit work; endpoint registration and lifecycle are managed by Spring Integration.

Because `MessageHandler` has a single abstract method, a lambda can be used for short processing logic:

~~~java
@Bean
public IntegrationFlow notificationFlow(NotificationService service) {
    MessageHandler handler = message ->
            service.send((Notification) message.getPayload());

    return IntegrationFlow.from("notificationChannel")
            .handle(handler)
            .get();
}
~~~

For processing with multiple rules, input validation, logging, and exception mapping, a dedicated class is usually easier to read and test than a long lambda.

## 5. handleMessage Does Not Return a Reply

A common point of confusion is that `handleMessage` returns `void`. A handler can write data, call an API, send a notification, or perform side effects, but the method's return value is not used to produce a reply.

If a handler needs to send a result to the next step, there are two common design approaches:

1. Use a reply-producing endpoint, such as a service activator calling a business method that returns a value.
2. Actively send a new message to an output channel from within the processing logic.

With the Java DSL, you can declare a payload transformation step that produces a resulting message as follows:

~~~java
@Bean
public IntegrationFlow normalizeOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("rawOrders")
            .<Order, NormalizedOrder>transform(orderService::normalize)
            .channel("normalizedOrders")
            .get();
}
~~~

Here, `transform` is a step that creates a new message from the function result. It differs from directly implementing `MessageHandler.handleMessage`.

Another approach is to use a service activator to invoke a reply-producing business method:

~~~java
@Bean
public IntegrationFlow enrichOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders")
            .handle(orderService, "enrich")
            .channel("enrichedOrders")
            .get();
}
~~~

The `enrich` method of `OrderService` can return a result object; the service activator endpoint is responsible for turning that result into a reply message and sending it onward in the flow. Choose the abstraction based on intent: `MessageHandler` for one-way processing, and a reply-producing handler for a processing step that produces a result.

## 6. Exception Handling in handleMessage

The interface declares `MessagingException` to represent errors related to message processing. Implementations can also throw unchecked exceptions such as `IllegalArgumentException`, `IllegalStateException`, or business exceptions extending `RuntimeException`.

Example of preserving the message and cause when wrapping a business error into a `MessagingException`:

~~~java
@Override
public void handleMessage(Message<?> message) {
    try {
        orderService.process((Order) message.getPayload());
    }
    catch (OrderRejectedException exception) {
        throw new MessagingException(
                message,
                "Cannot process rejected order",
                exception);
    }
}
~~~

When creating the exception, preserve the original cause so logs and observability tools can trace the root error. If the handler catches an exception just to log it and then returns normally, the dispatcher will treat the invocation as successful and will not be able to trigger failover automatically based on that exception.

### 6.1. How Do Errors Propagate?

The path an exception takes depends on how the channel and consumer execute:

- With `DirectChannel`, the handler is typically invoked synchronously on the thread that sent the message. The exception can propagate back to the `send()` call.
- With `ExecutorChannel`, the handler typically runs on a thread managed by a `TaskExecutor`. The sender may have already received the submit result before the handler throws an error.
- With a polling consumer, the exception occurs during the poll cycle and is handled according to the poller, transaction, and error handling configuration.
- Endpoints can combine an error channel, advice, or retry interceptor to handle errors.

`MessageHandler` does not automatically guarantee retries, dead-letter queues, or exactly-once delivery. Design the error flow at the endpoint/channel layer according to your operational requirements.

## 7. Thread Safety and Idempotency

A handler can be invoked multiple times and from multiple threads depending on the channel, executor, and consumer configuration. Therefore, treat a handler as potentially called concurrently unless the execution configuration guarantees sequentiality.

Practical guidelines:

- Avoid storing per-message data in shared mutable fields.
- If a shared cache or counter is required, choose thread-safe data structures and define their lifecycle clearly.
- Do not retain a reference to a mutable payload and mutate it after passing the message to another step.
- Do not assume a message is processed strictly once; retries, redelivery, or failover can cause the same business operation to be invoked again.
- Use a business key or idempotency key to prevent duplicate side effects.

For example, when recording a payment, the handler should check whether the transaction ID has already been processed before creating a new transaction. `handleMessage` completing normally only means the current invocation did not throw an error; it does not by itself prove that the entire system persisted the result durably or that the message will never be redelivered.

## 8. Testing the handleMessage Contract

You can test a handler in isolation by constructing a message and invoking the method directly:

~~~java
@Test
void recordsOrderWithMessageContext() {
    Message<Order> message = MessageBuilder
            .withPayload(new Order("order-1001"))
            .setHeader("tenantId", "tenant-a")
            .build();

    handler.handleMessage(message);

    verify(orderService).process(
            message.getPayload(),
            message.getHeaders());
}
~~~

Cases you should test:

| Case | What to Verify |
|---|---|
| Valid payload | Business logic is invoked with the expected payload |
| Wrong payload type | Handler rejects the input with a clear error |
| Missing required header | Rejection behavior or default value matches the rules |
| Business logic throws an error | Exception is propagated or mapped properly |
| Transformed payload | Output message has the required payload and headers |
| Concurrent invocations | Handler does not corrupt shared state |
| Repeated calls with same business key | Side effects are protected by idempotency |

Direct unit tests verify the handler's logic. To verify channel wiring, endpoints, pollers, executors, and error channels, add integration tests that bootstrap the Spring context and send messages through the flow's actual input channel.

## 9. Common Design Mistakes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Handler does not receive messages | Endpoint not created, wrong channel name, or flow not registered | Check `IntegrationFlow` and endpoint configuration |
| Payload casting fails | Producer sends a different data type than the handler expects | Validate the payload or add a `transform` step |
| Headers disappear in downstream steps | Creating a new message without copying required metadata | Use `MessageBuilder.fromMessage` and verify headers |
| Header changes have no effect | Trying to mutate `MessageHeaders` directly | Create a new message with `MessageBuilder` |
| Sender does not receive errors | Handler runs via an executor or asynchronous consumer | Check the error channel and worker logging |
| Flow produces no reply | Using a `void` handler while expecting a return value | Use a reply-producing handler or `transform` |
| Same business operation runs twice | Retry/redelivery/failover without idempotency | Use a business key and deduplication mechanism |
| Errors are swallowed | Handler catches an exception and does not rethrow it | Route errors to an error flow or throw an appropriate exception |

## 10. Checklist When Implementing a MessageHandler

Before putting a handler into a flow, determine:

1. What type is the input payload and which fields need validation?
2. Which headers must the handler read, and does it need to preserve correlation or reply metadata?
3. Is the processing one-way or does it need to produce a reply?
4. Which exceptions are thrown, and which need to be translated into business errors?
5. Does the handler run synchronously, via an executor, or inside a poller?
6. Can there be concurrent invocations or redeliveries?
7. Which unit tests and integration tests prove the processing contract?

A well-designed `MessageHandler` has clear input boundaries, handles a single testable responsibility, preserves necessary metadata, and lets errors follow the flow's designed policy. Once you understand the `handleMessage` contract, reading and building endpoints, consumers, pollers, and executors in Spring Integration becomes much more predictable.

## References

- [Spring Integration — Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Framework API — MessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [Spring Framework API — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- [Spring Framework API — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
