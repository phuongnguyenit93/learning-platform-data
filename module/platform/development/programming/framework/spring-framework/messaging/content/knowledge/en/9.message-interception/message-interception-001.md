# MessageHandler and the Responsibility of Processing a Message

> Goal: understand Spring Messaging's `MessageHandler` contract, distinguish handlers from channels and endpoints, know how to read payload/headers, validate data, handle errors, and design handlers that are safe under retries or concurrent processing.

## 1. What Is MessageHandler?

`MessageHandler` is the core Spring Messaging interface representing a component that receives and processes messages. It defines a single method:

```java
void handleMessage(Message<?> message) throws MessagingException;
```

The handler receives a `Message<?>` consisting of a payload and headers, performs the appropriate work, and either completes or throws an exception if it cannot process the message. The interface does not prescribe whether the message comes from a queue, topic, HTTP, or an internal channel; the source and dispatching mechanism are determined by the channel, endpoint, or adapter.

A handler is typically responsible for one clear processing step, such as updating an order status, validating an event, calling an application service, or forwarding validated data. A handler should not take on an entire business workflow, manage broker connections, or re-implement retry mechanisms itself.

## 2. Distinguishing Message, Channel, Endpoint, and Handler

These four components work together, yet each has a distinct role:

| Component | Responsibility |
|---|---|
| `Message<T>` | Carries the payload and headers of a single data transmission |
| `MessageChannel` | Provides the send point for messages and the dispatch or receive contract |
| Endpoint | Connects a handler to a channel, poller, or transport |
| `MessageHandler` | Executes work when receiving a message |

Typical processing flow in Spring Integration:

```text
Producer / Inbound Adapter
          |
          v
     MessageChannel
          |
          v
   Endpoint / Dispatcher
          |
          v
     MessageHandler
          |
          v
 Application Service / Domain
```

The channel decides which subscriber receives the message or stores it for polling. The endpoint connects the channel to the handler and may add parameter conversion, transactions, advice, or error handling. The handler focuses on processing the message content.

A `DirectChannel` typically dispatches to a single selected subscriber on the sending thread. A `PublishSubscribeChannel` can send the same message to multiple subscribers. A `QueueChannel` stores messages in a buffer for consumers to poll. Therefore, a handler should not assume that every channel has the same distribution model, ordering, or invocation timing.

## 3. Reading Payload and Headers

The payload is the primary data to process. Headers contain metadata such as message ID, timestamp, correlation ID, content type, reply channel, or routing information. A handler can accept the full message when it needs to inspect both parts.

Example:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;
import org.springframework.stereotype.Component;

record OrderCreated(String orderId, int itemCount) {}

@Component
class OrderCreatedMessageHandler implements MessageHandler {
    private final OrderApplicationService orderService;

    OrderCreatedMessageHandler(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        Object payload = message.getPayload();

        if (!(payload instanceof OrderCreated event)) {
            throw new MessagingException(message,
                    "Expected an OrderCreated payload");
        }

        if (event.orderId() == null || event.orderId().isBlank()) {
            throw new MessagingException(message,
                    "Order ID must not be blank");
        }

        orderService.process(event);
    }
}
```

This example illustrates a handler; `OrderApplicationService` is a business service provided by the application. The handler checks the payload type and minimal data before calling the service. In a real application, validation may be extracted into a validator or performed at the application/domain layer depending on the rules.

When metadata is needed, the handler can read from `message.getHeaders()`. For example, `MessageHeaders.ID` identifies the message, `MessageHeaders.TIMESTAMP` records when the message was created, and `MessageHeaders.CONTENT_TYPE` describes the content type. Custom headers such as `correlationId` or `tenantId` must be agreed upon between producer and consumer.

Do not treat a header as trustworthy business data just because it is present in the message. If a header affects tenant selection, access control, or sensitive routing, validate the sender source and check the value at a trust boundary. Avoid putting secrets or unnecessary personal data into headers.

## 4. Implementing MessageHandler Directly

Implementing `MessageHandler` is appropriate when direct control over the message object is needed, such as when processing metadata, building an adapter, or writing a low-level handler.

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessagingException;

class AuditMessageHandler implements MessageHandler {
    private final AuditService auditService;

    AuditMessageHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handleMessage(Message<?> message) throws MessagingException {
        try {
            auditService.record(
                    message.getHeaders().getId(),
                    message.getPayload()
            );
        } catch (RuntimeException ex) {
            throw new MessagingException(message,
                    "Could not record message audit", ex);
        }
    }
}
```

The example preserves the failing message inside `MessagingException` so infrastructure or an error handler can trace it. Only wrap an exception when adding context is needed; preserve the original `cause` so the stack trace and true root cause are not lost.

Do not catch `Exception` or `Throwable` and ignore it. If a handler logs an error and still returns normally, the infrastructure may treat the message as successfully processed and acknowledge it, even though the business work did not complete. For unrecoverable errors, throw an appropriate exception so the endpoint or adapter can apply the configured error policy.

## 5. Using Service Activator in Spring Integration

In many applications, there is no need to implement `MessageHandler` yourself. Spring Integration can turn a regular Java method into a message handler via `@ServiceActivator`.

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class OrdersServiceActivator {
    private final OrderApplicationService orderService;

    OrdersServiceActivator(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "orders.created")
    public void handle(OrderCreated event) {
        orderService.process(event);
    }
}
```

Spring Integration creates an endpoint for the method and connects it to the `orders.created` channel. The framework can convert the payload into the `OrderCreated` parameter if the message and converter/configuration match. The method can accept `Message<OrderCreated>` if it needs both payload and headers, or accept specific headers using the `@Header` annotation.

Example of receiving both payload and correlation ID:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@ServiceActivator(inputChannel = "orders.created")
public void handle(
        @Payload OrderCreated event,
        @Header("correlationId") String correlationId) {
    orderService.process(event, correlationId);
}
```

These are illustrative snippets; the application needs Spring Integration, the corresponding channel bean, and endpoint configuration. If a required header is missing or cannot be converted, the invocation may fail before entering the method body.

### Handlers That Return a Result

A method used as a service activator can return an object or a message. When a result is returned, the endpoint can create a reply message and send it to the configured output channel or reply channel. At the interface level, `MessageHandler.handleMessage` returns `void`; the reply model is managed by the endpoint/gateway and reply channel.

If the method produces no result (`void` or `null`), no reply payload is emitted from the service activator. Configure an explicit output channel if the flow needs to forward the result to the next step.

## 6. Responsibilities of a Good Handler

A handler should perform a single step with a clear purpose and keep a stable input/output contract:

1. **Validate the message:** confirm the payload has the required type and data; check required headers.
2. **Apply rules at the right layer:** invoke an application service or domain logic rather than cramming all business logic into the handler.
3. **Preserve context:** forward correlation ID, message ID, or necessary metadata to logs and downstream calls.
4. **Manage results:** if a reply is needed, produce a typed result and let the endpoint/gateway route it according to the contract.
5. **Report errors properly:** do not swallow exceptions; distinguish expected business errors from technical errors.
6. **Ensure safety under repeated execution:** handle duplicates or redeliveries according to an idempotency policy.
7. **Maintain observability:** emit structured logs and required metrics without exposing sensitive payloads.

A handler should avoid responsibilities outside its processing step, such as managing broker connection lifecycles, polling queues itself, deciding infinite retries itself, or holding per-message mutable state in fields of a singleton bean.

## 7. Exceptions and Error-Handling Flow

`MessageHandler.handleMessage` can throw `MessagingException`. How exceptions are observed depends on the channel and endpoint:

- With `DirectChannel`, the handler typically runs on the sending thread; exceptions may propagate back to the producer/caller.
- With an executor or asynchronous endpoint, the sender may have already finished before the handler fails; an error handler or error channel is needed to receive the failure.
- With a broker adapter, transactions, acknowledgements, retries, requeues, or dead-lettering depend on the adapter and broker configuration.

Do not assume every exception is automatically routed to an `errorChannel`. Determine which endpoint emits the error, which error channel is configured, and whether the handler error is rethrown or forwarded.

### Business Errors vs. Technical Errors

Not every unsuccessful outcome should be an exception:

| Situation | Usually Appropriate Handling |
|---|---|
| Order is ineligible according to business rules | Return a typed rejection result or emit a corresponding business event |
| Malformed payload or missing required field | Report validation/conversion error and apply a reject or dead-letter policy |
| Database temporarily loses connection | Throw an exception for bounded retry if the operation is safe |
| Handler encounters a programming bug | Make the error observable, fix the root cause, and avoid infinite retries |

If the handler has written to the database but has not acknowledged the message yet, the message may be redelivered. Therefore, the handler must coordinate transactions and acknowledgements properly with the transport while ensuring the operation is safe to repeat.

## 8. Idempotency and Duplicate Message Handling

A broker may redeliver a message when a consumer disconnects, fails to acknowledge in time, or encounters an error. A handler being invoked multiple times with the same message is a scenario that must be anticipated.

Idempotency means that processing the same request repeatedly produces no additional side effects beyond the desired outcome. Common techniques include:

- Using a stable message ID or command ID to identify the processing attempt.
- Recording processed message markers along with results in the database.
- Using a unique constraint or business key to prevent duplicate records.
- Performing the duplicate check and state update within the same appropriate transaction.
- For external side effects such as payments, using an idempotency key supported by the provider if available.

Do not store only a `processed=true` flag separately from the business update if the two operations can fail independently. Otherwise, the system could mark a message as processed without recording the result, or vice versa.

## 9. Concurrency and Thread Safety

Spring beans are usually singleton-scoped. A singleton handler can be invoked concurrently by multiple threads depending on the channel, executor, listener container, and concurrency settings.

Therefore:

- Avoid storing per-message temporary data in mutable instance fields.
- Use local variables for state belonging to a single invocation.
- If state must be shared, use proper synchronization or thread-safe structures; better yet, store business state in a service/database.
- Do not assume completion order equals receipt order if the endpoint processes in parallel.
- Set concurrency limits based on CPU, connection pools, the broker, and downstream services.

Thread-bound transactions do not automatically propagate to another executor thread. If a transaction is needed, place the transaction boundary inside the handler/service executing on the processing thread and configure the corresponding transaction manager.

## 10. Testing MessageHandler

A handler can be unit-tested by constructing a message and invoking `handleMessage` directly. Tests should focus on the handler's contract:

- Valid payloads invoke the application service exactly once.
- Wrong payload types or missing data are rejected according to the contract.
- Required headers are read and passed correctly.
- Exceptions from the service preserve the cause and failing message.
- Duplicate messages do not cause repeated side effects when idempotency is required.

Example of constructing a message in a test:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated("ORD-100", 2))
        .setHeader("correlationId", "corr-100")
        .build();

handler.handleMessage(message);
```

This snippet illustrates preparing input for a unit test; `handler` is an instance created with fake or mock dependencies. In addition to unit tests, write integration tests to verify channel dispatch, endpoints, converters, error flows, and real adapters.

## 11. Common Pitfalls

- **Confusing a handler with a channel:** a handler processes messages; a channel delivers messages to subscribers or buffers them for polling.
- **Putting all business logic inside `handleMessage`:** makes the handler hard to test and reuse; delegate to an application/domain service.
- **Casting every payload without checking:** wrong message types can cause `ClassCastException`; validate the input contract.
- **Ignoring important headers:** losing correlation ID or tenant context makes tracing difficult and can affect routing.
- **Swallowing exceptions and returning normally:** infrastructure may acknowledge the message even though processing failed.
- **Assuming `send` returning means the handler finished:** with asynchronous dispatch, `send` may only confirm acceptance of the work.
- **Failing to design for idempotency:** redelivery can create duplicate orders, payments, or notifications.
- **Storing per-message state in a singleton handler:** multiple threads can overwrite each other's data.
- **Assuming all errors go to `errorChannel`:** error routing depends on the endpoint and specific configuration.
- **Using a handler to poll the broker:** receiving from the transport belongs to the adapter/container; the handler only processes messages delivered to it.

## 12. Handler Implementation Workflow

1. Identify the message type, payload type, required headers, and validity conditions.
2. Identify which channel and endpoint dispatch messages to the handler.
3. Write a small handler that prefers invoking an application service via constructor injection.
4. Distinguish normal business outcomes from technical exceptions.
5. Define the reply contract if the flow needs a return result.
6. Design idempotency, transactions, acknowledgements, and retries appropriate for the transport.
7. Ensure the handler is thread-safe under actual concurrency.
8. Write unit tests for the handler contract and integration tests for channel/endpoint/error flows.
9. Monitor message counts processed, processing duration, errors, retries, and duplicates.

## 13. Conclusion

`MessageHandler` is the execution point where work happens when a message is dispatched to a consumer. It receives a `Message<?>`, reads its payload and headers, performs a single step with clear responsibility, and either completes or throws `MessagingException` on failure.

Spring Integration can wire a handler using an endpoint such as `@ServiceActivator`, while the channel determines how messages are dispatched or buffered. A good handler validates the input contract, delegates business logic to the appropriate service, handles errors transparently, remains safe under concurrent execution, and stays idempotent when messages are redelivered.