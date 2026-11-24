# ErrorMessage and Representing Errors as Messages

> Goal: understand how Spring represents errors using `ErrorMessage`, read the exception and failing message, route errors through an error channel, distinguish technical errors from business outcomes, and design safe error handling in messaging flows.

## 1. Why Represent Errors as Messages?

In a synchronous Java call, errors are typically propagated via exceptions on the call stack. The caller can catch the exception, decide to roll back, return an error result, or propagate the error to a higher layer.

In a messaging flow, producer and consumer may run at different times. The consumer may process a message after the producer has already finished the initial request; therefore, errors cannot always be thrown back onto the producer's thread. The system needs a way to deliver error information to a component responsible for observing, retrying, recording, or handling further processing.

Spring Messaging represents errors with `ErrorMessage`. This is a type of `Message` whose payload is a `Throwable` (an exception or error) and which can hold a reference to the original message associated with the failure. An error message can be sent to an error channel for another handler to process.

Three activities should be distinguished:

- **Producing the error:** a component throws an exception when processing fails.
- **Representing and routing the error:** the infrastructure creates an `ErrorMessage` and sends it to the appropriate error channel.
- **Recovery decision:** an error handler, retry policy, or dead-letter mechanism decides to log, retry, forward, alert, or terminate processing.

`ErrorMessage` solves carrying error information. By itself, it does not retry, roll back a database, send emails, or guarantee that the message is durably stored.

## 2. Structure of ErrorMessage

In Spring Framework, `org.springframework.messaging.support.ErrorMessage` is a message specialized for errors. Its important components:

- **Payload:** a `Throwable` object, usually an exception describing the error that occurred.
- **Original message:** the initial message related to the error, if available. Accessible via `getOriginalMessage()`.
- **Headers:** metadata of the error message, such as ID and timestamp provided by the messaging infrastructure; custom headers can support correlation and observability.

Example of creating an error message from a known error:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

Message<?> failedMessage = obtainFailedMessage();
Throwable cause = new IllegalStateException("Inventory service is unavailable");

MessagingException failure = new MessagingException(
        failedMessage,
        "Could not process order message",
        cause
);

ErrorMessage errorMessage = new ErrorMessage(failure, failedMessage);
Throwable errorPayload = errorMessage.getPayload();
Message<?> originalMessage = errorMessage.getOriginalMessage();
```

This is an illustrative snippet in which `obtainFailedMessage()` represents a previously received message. Real applications usually let Spring Integration or an adapter create the error message according to the endpoint's error handling strategy; you do not need to manually instantiate `ErrorMessage` for every exception.

The name `ErrorMessage` can be confused with `java.lang.Error`. `ErrorMessage` is a Spring message type; its payload has type `Throwable`. You should not catch every `Throwable` just to convert it into a message and continue running, because severe JVM errors such as `OutOfMemoryError` are typically not recoverable business errors.

## 3. MessagingException and the Failing Message

`MessagingException` is the base exception in Spring Messaging for describing errors related to a message. It can hold the failing message via `getFailedMessage()` and the root cause via `getCause()`.

Some specialized exceptions commonly seen in the Spring Messaging/Integration ecosystem:

| Exception | Common situation |
|---|---|
| `MessagingException` | General error related to processing or sending a message |
| `MessageHandlingException` | Handler received the message but processing failed |
| `MessageDeliveryException` | Unable to send or deliver the message to the destination |
| `MessageTransformationException` | Unable to transform the payload or message as required |
| `MessageConversionException` | Data conversion between the payload and target type failed |

Specific exceptions help categorize where the error originated. When handling errors, preserve the cause chain to find the real root cause instead of recording only the outermost message.

Example of reading error information:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

void inspect(ErrorMessage errorMessage) {
    Throwable payload = errorMessage.getPayload();
    Message<?> original = errorMessage.getOriginalMessage();

    if (payload instanceof MessagingException messagingException) {
        Message<?> failed = messagingException.getFailedMessage();
        Throwable rootCause = messagingException.getCause();
        // Record failed, original, and rootCause according to the logging policy.
    }
}
```

`originalMessage` and `failedMessage` can be the same, yet you should not assume they are always identical. In a flow with transformers or enrichers, the initial message and the message at the failing step may differ. Keeping both pieces of information helps identify the input data and the state at the point of failure.

## 4. Error Channels in Spring Integration

Spring Integration uses message channels to route both business messages and error messages. An error channel is where `ErrorMessage` instances are sent for a dedicated handler to process.

When asynchronous processing infrastructure detects an exception, the error handling mechanism can create an `ErrorMessage` and publish it to an error channel. A global channel is commonly named `errorChannel`; a specific endpoint or message can also be configured to use a dedicated error channel. The exact mechanism depends on the endpoint type, poller, adapter, and error handling configuration.

Example of a handler listening on the default error channel in a Spring Integration application with the corresponding infrastructure enabled:

```java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
class GlobalMessagingErrorHandler {
    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable cause = errorMessage.getPayload();
        // Classify, log in a controlled manner, and raise alerts if needed.
    }
}
```

The handler above only receives error messages routed into the channel. Declaring a method listening on `errorChannel` does not automatically catch every exception in the entire JVM. You must verify that the failing endpoint is connected to that channel and that no separate configuration overrides it.

### A dedicated error channel for a flow

An order processing flow may need a different error policy from an email flow. For example, payment failures require alerts and reconciliation; email sending failures can retry more slowly. You can create a dedicated channel:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration
class OrdersErrorConfiguration {
    @Bean
    MessageChannel ordersErrorChannel() {
        return new DirectChannel();
    }
}
```

This channel only creates a message receiving point in the application. The endpoint must be configured to publish errors to `ordersErrorChannel`; if no producer sends to it, handlers subscribed to the channel will not receive errors. You can configure the error channel on the endpoint, poller, or via headers according to the integration setup in use.

`DirectChannel` invokes subscribers on the sending thread. If you need to distribute to multiple subscribers or process asynchronously, choose an appropriate channel type and executor, and clearly understand how subscriber exceptions are propagated back.

## 5. Synchronous Errors vs. Asynchronous Errors

How an error reaches its handler depends on the execution flow:

| Situation | How the error is typically observed |
|---|---|
| Synchronous method call | Exception propagates back up the call stack to the caller if uncaught |
| Sending through `DirectChannel` | Handler runs on the sending thread; exception may propagate back to the sender |
| Poller or asynchronous executor | No original request call stack to return the error to; error handler/channel may receive `ErrorMessage` |
| Message-driven adapter | Adapter/container and transaction, acknowledgement, and error handler configuration determine whether the error is rethrown, sent to an error channel, or handled by the broker |
| Consumer in another process | Producer cannot receive a Java exception from the consumer; requires a reply, error event, status, or dedicated dead-letter mechanism |

This is why you should not assume every exception automatically appears on `errorChannel`. With synchronous calls, the caller typically receives the exception directly. With asynchronous processing, errors need an independent observation path. With a broker in another process, a consumer error is an outcome on the consumer side and must be communicated back if the business process needs to know.

## 6. Creating and Handling ErrorMessage in a Flow

A flow can create an error message from an exception and send it to an error channel. The following example illustrates application-level error handling:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

void publishProcessingFailure(
        Message<?> failedMessage,
        Throwable cause,
        MessageChannel errorChannel) {

    MessagingException failure = new MessagingException(
            failedMessage,
            "Order processing failed",
            cause
    );

    ErrorMessage errorMessage = new ErrorMessage(failure, failedMessage);
    errorChannel.send(errorMessage);
}
```

The snippet above illustrates manual error packaging and sending. In real applications, consider Spring Integration's built-in error handling before publishing manually, to avoid duplicate sends or breaking transaction semantics. The return value of `send` reflects whether the channel accepted the message according to the channel's contract; it does not prove the error has been resolved.

An error handler should perform intentional steps:

1. Extract the exception from the payload and identify the root cause.
2. Retrieve `failedMessage` and `originalMessage` if present.
3. Classify whether it is a transient error, data error, configuration error, business error, or unrecoverable error.
4. Decide to retry, reject, move to dead-letter, raise an alert, or record for manual handling.
5. Log correlation/message IDs so it can be traced across logs and metrics.

Avoid letting an error handler rethrow the same error in a way that loops endlessly back into that same error channel. If the error-handling handler itself fails, have a fallback such as rate-limited logging, a metric, or another operational mechanism.

## 7. ErrorMessage Is Not Synonymous with a Business Error Response

Not every unsuccessful situation is a technical exception. For example, a customer entering an expired discount code is a predictable business outcome; an unreachable payment service is a technical error.

| Outcome type | Example | Appropriate representation |
|---|---|---|
| Technical error | Timeout calling database or broker | Exception; may be wrapped as `ErrorMessage` in an error flow |
| Business rejection | Insufficient stock, canceled order, expired coupon | Explicitly typed result or reply, e.g., `ReservationRejected` |
| Recorded failure event | Payment declined by provider | Business event such as `PaymentDeclined`, if it is a recorded fact |
| Message unprocessable after retries | Corrupted payload or schema violation | Dead-letter message or quarantine workflow per broker policy |

Do not use exceptions for every normal business branch. If insufficient stock is a valid business outcome, returning a typed result helps the consumer handle it clearly. Conversely, do not turn a connection failure or programming bug into a "succeeded-but-failed" reply that hides incidents.

## 8. How ErrorMessage, Error Channel, and Dead-Letter Queue Differ

- **ErrorMessage:** a Spring message object whose payload is `Throwable`, optionally carrying the message related to the failure.
- **Error channel:** a routing path inside a Spring application to deliver error messages to a handler.
- **Dead-letter queue (DLQ):** a broker or messaging platform resource that holds unprocessable messages according to retry/reject/expiry policies.
- **Error event:** a business or operational contract emitted to announce that a failure occurred; the payload is typically a DTO with a stable schema.

An error channel is usually part of an in-process flow. It does not inherently provide broker durability and does not replace a DLQ. A DLQ retains messages for investigation or replay depending on the platform; `ErrorMessage` contains a Java exception and should not by default be serialized directly to cross into another system.

If errors need to be communicated across services, design a payload independent of internal exception classes, for example:

```java
import java.time.Instant;

record ProcessingFailedEvent(
        String eventId,
        String correlationId,
        String messageId,
        String operation,
        String errorCode,
        String safeDescription,
        Instant occurredAt
) {}
```

This DTO can be serialized according to an agreed schema. Do not include stack traces, passwords, access tokens, or sensitive data in the event. Distinguish internal diagnostic information from information safe to share with other consumers.

## 9. Retry, Acknowledgement, and Safe Idempotency

`ErrorMessage` does not decide retries by itself. Retrying depends on where the error occurred and the mechanism in use:

- With synchronous calls, the caller can retry if the error is recoverable and the operation is safe to repeat.
- With Spring Integration, retries can be configured via advice or the endpoint/poller's error handling mechanism.
- With brokers, acknowledgement, reject, requeue, visibility timeout, or offset commit determine whether the message is redelivered; exact names and behavior depend on the technology.
- After a finite number of retries, the message can be moved to a DLQ or quarantine area for manual handling.

Design idempotent consumers so that a redelivered message does not create duplicate side effects. You can store the processed message ID or business key alongside the result within an appropriate transaction. Only retry transient errors such as brief connection drops; schema errors, invalid data, or business rule violations typically require fixing the data or separate handling.

If the consumer writes to a database before acknowledging the message, understand whether the database transaction and broker acknowledgement actually coordinate. Do not assume a single database transaction covers broker processing. For high consistency requirements, design an outbox/inbox or appropriate deduplication mechanism.

## 10. Observability and Security When Handling Errors

Error handlers need to provide enough data for investigation without leaking information:

- Record message ID, correlation ID, destination, handler, timestamp, and delivery attempt count.
- Preserve the cause chain and exception type; avoid logging only a generic message like "processing failed".
- Log a redacted payload or only necessary identifiers; avoid logging the entire payload if it contains personal data or secrets.
- Set length limits on stack traces and descriptions to avoid oversized logs.
- Use metrics for error counts by type, retry count, DLQ depth, and age of oldest message.
- Trigger alerts based on thresholds and trends rather than sending a separate alert for every routine retry.

An error message can contain both the original payload and the exception. Therefore, the error channel is also a data boundary requiring access control and retention policies.

## 11. Common Mistakes

- **Thinking `ErrorMessage` handles exceptions by itself:** it only wraps the error; an error handler or another mechanism is needed to decide the next step.
- **Assuming every exception reaches `errorChannel`:** synchronous errors may propagate straight to the caller; asynchronous errors depend on endpoint and configuration.
- **Confusing `ErrorMessage` with a DLQ:** a Spring error message is not automatically persisted durably on a broker.
- **Ignoring the failing message:** logging only the stack trace without keeping the message ID or failed message makes investigation difficult.
- **Reading only `getOriginalMessage()` and ignoring `getFailedMessage()`:** in a flow with transformers, the two messages may differ.
- **Infinite retries:** can block consumers and cause queues to grow continuously.
- **Retrying unrecoverable business errors:** creates load and repetitive logs without resolving the root cause.
- **Throwing an exception from an error handler without a fallback:** can create an error loop or lose the original context.
- **Directly serializing Java exceptions over a broker:** couples the contract to internal classes, library versions, and sensitive data in stack traces.
- **Treating broker acknowledgement as successful business processing:** acknowledgement only carries meaning according to the configured protocol and acknowledgement timing.

## 12. Process for Designing an Error Flow

1. Identify where errors originate: sender, channel, transformer, handler, adapter, or broker.
2. Determine whether the flow is synchronous or asynchronous and where exceptions can be observed.
3. Preserve `Throwable`, `failedMessage`, `originalMessage`, and correlation ID when available.
4. Classify technical errors, business errors, transient errors, and unrecoverable errors.
5. Choose an in-app error channel, typed error reply, error event, or DLQ depending on the scope needed to communicate the information.
6. Set bounded retries, backoff, idempotency, and appropriate acknowledgement rules.
7. Emit controlled logs/metrics and provide a way to investigate or replay messages.
8. Test the happy path, synchronous errors, asynchronous errors, timeouts, redelivery, and failures of the error handler itself.

## 13. Conclusion

`ErrorMessage` is Spring's abstraction for representing an error as a message: the payload carries `Throwable`, while the original message and headers help link the error to the data that caused it. In Spring Integration, an error channel lets asynchronous errors be routed to a dedicated handler.

Separate throwing exceptions, packaging and routing errors, and then deciding whether to retry or dead-letter. Use business replies for predictable business outcomes, use error flows for technical errors, and use error events with a stable schema when errors must be communicated across service boundaries. This design keeps errors observable, enables controlled recovery, and prevents confusing delivery acknowledgements with business outcomes.