# MessagingException, MessageDeliveryException, and MessageHandlingException

In a messaging flow, errors can occur at multiple points: the producer cannot send a message into a channel, the transport cannot deliver the message to its destination, or the consumer received the message yet business processing failed. Spring uses exceptions in the messaging family to preserve the context of the error and the related message.

Three common types are **MessagingException**, **MessageDeliveryException**, and **MessageHandlingException**. They share an inheritance relationship, yet describe different failure scopes. Distinguishing them accurately helps pinpoint whether the error occurred during sending or during handling, preserve the root cause, choose sensible retries, and avoid putting failing messages into infinite loops.

## 1. Message Lifecycle and Points Where Errors Can Occur

A typical messaging flow consists of the following steps:

1. The producer builds a payload and wraps it into a Message, possibly with a message ID, correlation ID, and content type.
2. The producer sends the Message to a MessageChannel or a transport adapter.
3. The channel or transport routes and transfers the message to the receiver.
4. The consumer receives the message and invokes a handler.
5. The handler validates data, executes business logic, and records the result.
6. The infrastructure acknowledges that the message was accepted or processed according to transport semantics.

Errors can occur at each step. For instance, the channel has no subscriber, the queue is full, the executor rejects the task, the broker is unreachable, the payload cannot be decoded, or the handler throws an exception while updating the database.

~~~mermaid
flowchart LR
    P["Producer"] --> S["Send to channel"]
    S --> D["Delivery / transport"]
    D --> H["Consumer handler"]
    H --> B["Business processing"]
    S -. "send / dispatch error" .-> E["Messaging error"]
    D -. "delivery error" .-> E
    H -. "handling error" .-> E
~~~

Not every application has all of the layers above. DirectChannel can invoke the handler synchronously right on the sending thread; a broker adapter can transfer the message over the network and process it asynchronously. Therefore, classify exceptions based on the actual point of origin and the channel/adapter contract.

## 2. MessagingException: The Base Exception for Messaging Errors

**MessagingException** belongs to the **org.springframework.messaging** package. It is the base exception in Spring Messaging, inheriting from **NestedRuntimeException**. It represents an error occurring while operating on a message.

A MessagingException can contain:

- **Failed message:** the message associated with the error, if that message had been identified when the error occurred.
- **Description:** a description of the failing operation or context.
- **Cause:** the underlying exception that caused the failure, if the error originated from another exception.

Information about the failed message is very useful during investigation: you can identify the message ID, correlation ID, or payload type to locate the exact processing flow. Do not log the entire payload by default because the payload may contain personal data, tokens, or sensitive business information.

Common ways to construct the exception:

~~~java
throw new MessagingException(
        message,
        "Messaging operation failed",
        cause
);
~~~

Specific constructors may have different overloads across Spring versions. The general intent is to attach the related message, description, and root cause to the exception so the calling layer can diagnose it.

MessagingException is suitable when an error belongs to messaging activity without a more specific subtype, or when the application needs to represent a general messaging failure. If it is already known that the failure happened during delivery or handling, use the corresponding subtype for clearer information.

## 3. MessageDeliveryException: Errors Sending or Delivering a Message

**MessageDeliveryException** also belongs to the **org.springframework.messaging** package and is a subtype of MessagingException. It describes an error when a message cannot be sent or delivered according to the contract of the channel or transport in use.

Scenarios that can lead to delivery errors include:

- The channel cannot dispatch the message to subscribers as configured.
- A message send step fails or times out.
- The executor rejects the task because it is full or shutting down.
- The adapter cannot transfer the message to the transport or destination.
- An infrastructure error at the send layer prevents the message from being accepted as expected.

Illustrative example when sending through a channel with a timeout:

~~~java
boolean sent = outputChannel.send(message, 1_000);

if (!sent) {
    throw new MessageDeliveryException(
            message,
            "Message was not accepted before the send timeout"
    );
}
~~~

**MessageChannel.send(message, timeout)** returns a boolean. A value of false can indicate the message was not accepted by the channel within the wait time; not every case automatically throws MessageDeliveryException. The snippet proactively converts the false result into an exception so the calling layer has a unified error-handling path.

When a channel or adapter throws an exception itself, the exact exception type depends on the implementation. Some transport errors may be wrapped in exceptions from RabbitMQ, Kafka, JMS, or networking libraries before being translated into a messaging exception. Do not assume every broker connection error has the exact class MessageDeliveryException across all adapters.

### 3.1. Delivery Failure Does Not Mean the Message Was Definitely Lost

When send fails, determine how far the message was accepted:

- If the channel rejected it before accepting the message, the producer may still be responsible for resending.
- If the transport timed out after the broker accepted the message yet before the producer received confirmation, the outcome may be ambiguous.
- If the broker accepted the message yet the consumer has not processed it, the message may still be queued.
- If publisher confirm or acknowledgement fails, consult the specific broker's semantics to know what was confirmed.

A timeout does not always prove the broker never received the message. Blind retries can create duplicates. Therefore, messages should carry a stable ID and consumers should process idempotently whenever business rules prohibit duplicate side effects.

## 4. MessageHandlingException: Errors While Processing a Message

**MessageHandlingException** is a subtype of MessagingException describing an error that occurs while a message is being processed by a handler or endpoint.

Examples:

- The payload is invalid or missing a required field.
- The payload cannot be converted to the expected DTO.
- Business rules reject the message.
- The handler calls a database or another service and that operation fails.
- Programming errors such as NullPointerException or IllegalStateException occur inside the handler.

Example of creating an exception that preserves the message and root cause:

~~~java
public void handle(Message<OrderCreated> message) {
    try {
        orderService.createOrder(message.getPayload());
    }
    catch (InvalidOrderException ex) {
        throw new MessageHandlingException(
                message,
                "Could not process OrderCreated",
                ex
        );
    }
}
~~~

This illustrates when an application intentionally translates a business error into MessageHandlingException. In many Spring Integration flows, the framework or adapter automatically wraps exceptions from handlers and attaches the failed message; there is no need to wrap every exception mechanically.

### 4.1. Distinguishing Data Errors from Transient Errors

Not every MessageHandlingException warrants the same handling policy:

- **Data errors unfixable by retry:** missing required fields, invalid enums, or broken schema. Usually best sent to an error channel or dead-letter queue for investigation.
- **Transient errors:** temporary database disconnection, downstream service timeout, or lock contention. Can be retried with bounded attempts and backoff.
- **Business errors:** order already cancelled or state does not permit the action. This may be a valid business outcome requiring a reply or recording according to rules rather than infinite retries.
- **Programming errors:** NullPointerException or invariant violations. Log, alert, and fix the root cause; automatic retries usually just repeat the same failure.

MessageHandlingException classifies where the failure occurred; it does not itself decide whether the error is retryable. Retry policies must be based on the cause, business error category, message state, and system recoverability.

## 5. Relationship Among the Three Exceptions

You can view the relationship from general to specific:

~~~text
NestedRuntimeException
        |
MessagingException
        |----------------------|
MessageDeliveryException   MessageHandlingException
~~~

| Exception | Scope | Typical Examples |
|---|---|---|
| MessagingException | General messaging error | Message operation failed without a more specific classification |
| MessageDeliveryException | Sending or delivering a message | Channel did not accept message, dispatch or send timeout |
| MessageHandlingException | Handler processing a message | Handler failed while validating or executing business logic |

Both subtypes can carry the failed message and cause via the superclass. Which subtype an exception has does not by itself prove whether the message was persisted by a broker, received by a consumer, or processed successfully.

When catching exceptions, you can catch subtypes first to apply specific policies, then catch MessagingException to handle general errors:

~~~java
try {
    sendOrProcess(message);
}
catch (MessageDeliveryException ex) {
    handleDeliveryFailure(ex);
}
catch (MessageHandlingException ex) {
    handleHandlingFailure(ex);
}
catch (MessagingException ex) {
    handleOtherMessagingFailure(ex);
}
~~~

If you only catch MessagingException, the subtypes are still caught through inheritance, yet the application loses the opportunity to differentiate handling policies. Avoid catching RuntimeException too broadly and discarding errors without preserving the cause or failure state.

## 6. Failed Message and Cause: Preserving Enough Context to Investigate

When handling exceptions, preserve at least three pieces of information:

1. **Failed message:** which message caused the failure?
2. **Cause:** what is the underlying exception?
3. **Failure stage:** did the error occur during sending, delivery, or handling?

Example:

~~~java
catch (MessagingException ex) {
    Message<?> failedMessage = ex.getFailedMessage();

    String messageId = failedMessage == null
            ? "unknown"
            : failedMessage.getHeaders().getId().toString();

    log.error(
            "Messaging failed; messageId={}",
            messageId,
            ex
    );

    throw ex;
}
~~~

This is illustrative code; check for null safely because failed message may not be populated in every constructor or scenario. When logging, pass the exception object so the logger retains the stack trace and cause. Do not log only **ex.getMessage()**, as doing so usually loses the stack trace and root-cause details.

Practical guidelines:

- Generate a message ID or correlation ID before sending so logs can be correlated between producer and consumer.
- Preserve the cause when wrapping exceptions; do not replace the original error with a generic message lacking a cause.
- Avoid creating repeated layers of wrapping when they add no useful context.
- Avoid logging full payloads or sensitive headers.
- When moving a message to an error channel or DLQ, retain the message ID, failure stage, timestamp, and attempt count.

## 7. Where Do Synchronous and Asynchronous Errors Propagate?

How an exception reaches the caller depends on the channel and transport type.

### 7.1. Synchronous Flows

With a synchronously dispatching channel such as DirectChannel in Spring Integration, the handler can run on the thread calling send. If the handler throws an exception and no error-handling layer intercepts it, the exception can propagate back to the producer.

This lets the caller decide to roll back a transaction, return an error, or perform further handling. However, side effects outside the transaction such as sending emails or making HTTP calls are not automatically undone when the database rolls back.

### 7.2. Asynchronous Flows

With ExecutorChannel, pollers, or broker listeners, the handler may run on another thread or in another process. The producer has typically finished its call before the handling error occurs. The exception cannot automatically unwind into the original producer's stack frame.

In Spring Integration, errors in asynchronous flows can be turned into an **ErrorMessage** and sent to the configured error channel. The payload of an ErrorMessage is typically a Throwable; if it is a MessagingException, the application can retrieve the failed message via getFailedMessage().

Example of an error handler:

~~~java
@Component
public class MessagingErrorHandler {

    @ServiceActivator(inputChannel = "errorChannel")
    public void handle(ErrorMessage errorMessage) {
        Throwable error = errorMessage.getPayload();

        if (error instanceof MessagingException messagingException) {
            Message<?> failed = messagingException.getFailedMessage();
            // Record the message ID and classify the error.
        }

        // Log or route to the appropriate error-handling workflow.
    }
}
~~~

This is a Spring Integration example when an error channel and corresponding infrastructure are configured. Spring Messaging core does not automatically create a global error channel for every MessageChannel. With RabbitMQ, Kafka, or JMS, error handling also depends on the listener container, adapter, acknowledgement mode, and broker.

Do not assume every asynchronous error automatically appears on errorChannel. Verify the actual integration configuration and where the exception is thrown.

## 8. Retry, Backoff, and Dead-Letter Queues

Retry is helpful when errors are recoverable, yet infinite retries can clog queues and repeat side effects.

### 8.1. Bounded Retries

A retry policy should specify:

- Which exceptions or causes are retried.
- Maximum number of attempts.
- Wait interval between attempts.
- Exponential backoff and jitter if multiple consumers retry concurrently.
- Overall timeout and message processing deadline.
- Behavior after exhausting all attempts.

For example, a temporary connection error can be retried with backoff. Validation or invalid schema errors are rarely resolved by resending the same payload.

### 8.2. Dead-Letter Queues

After retries are exhausted or when an unrecoverable error occurs, the message can be routed to a dead-letter queue (DLQ) or equivalent quarantine area. A DLQ preserves failing messages for inspection, data repair, or controlled replay.

A DLQ does not exist automatically on every MessageChannel. It is typically a broker feature or an error-handling workflow configured in Spring Integration/adapters. Store the failure reason, attempt count, and original message so operators understand why the message was moved to the DLQ.

### 8.3. Idempotency During Retry or Redelivery

A message can be redelivered after a timeout, consumer crash, or failed acknowledgement. Consumers should use the message ID or a business key to prevent executing side effects twice.

For example, if an event requests creating an invoice, you can store the processed event ID within the same transaction as the invoice data. When the message is redelivered, the consumer checks that key and skips already-completed work.

Do not rely merely on seeing MessageDeliveryException or MessageHandlingException to decide whether a message will be resent. Combine broker state, acknowledgements, transactions, and idempotency.

## 9. Java 17 Example: Classifying Delivery and Handling Failures

The example below uses plain JDK classes to illustrate preserving failed message and cause while distinguishing send failures from handling failures. Classes prefixed with **Demo** are defined by the program itself; they only simulate the semantics of Spring's exceptions and do not replace or inherit from Spring's real classes.

Create **MessageFailureDemo.java**:

~~~java
public class MessageFailureDemo {

    record Message(String id, String payload) {}

    static class DemoMessagingException extends RuntimeException {
        private final Message failedMessage;

        DemoMessagingException(
                Message failedMessage,
                String description,
                Throwable cause) {
            super(description, cause);
            this.failedMessage = failedMessage;
        }

        Message getFailedMessage() {
            return failedMessage;
        }
    }

    static class DemoMessageDeliveryException
            extends DemoMessagingException {
        DemoMessageDeliveryException(
                Message message,
                String description,
                Throwable cause) {
            super(message, description, cause);
        }
    }

    static class DemoMessageHandlingException
            extends DemoMessagingException {
        DemoMessageHandlingException(
                Message message,
                String description,
                Throwable cause) {
            super(message, description, cause);
        }
    }

    static void send(Message message) {
        throw new DemoMessageDeliveryException(
                message,
                "Channel did not accept the message",
                new IllegalStateException("channel is full")
        );
    }

    static void handle(Message message) {
        throw new DemoMessageHandlingException(
                message,
                "Handler rejected the payload",
                new IllegalArgumentException("quantity must be positive")
        );
    }

    public static void main(String[] args) {
        Message message = new Message("msg-42", "quantity=0");

        try {
            send(message);
        } catch (DemoMessageDeliveryException ex) {
            System.out.println(
                    "Delivery failure: " + ex.getFailedMessage().id());
            System.out.println("Cause: " + ex.getCause().getMessage());
        }

        try {
            handle(message);
        } catch (DemoMessageHandlingException ex) {
            System.out.println(
                    "Handling failure: " + ex.getFailedMessage().id());
            System.out.println("Cause: " + ex.getCause().getMessage());
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac MessageFailureDemo.java
java MessageFailureDemo
~~~

Output:

~~~text
Delivery failure: msg-42
Cause: channel is full
Handling failure: msg-42
Cause: quantity must be positive
~~~

The example shows that the same message can fail at two different stages. Both exceptions retain the message ID and cause, helping the handling layer know whether to investigate the channel or the handler logic. In real Spring code, use the classes in the org.springframework.messaging package rather than creating identically named classes yourself.

## 10. Testing Exceptions and Error Handling

Test stage by stage rather than merely asserting that an exception was thrown:

- **Delivery test:** channel has no subscribers, queue is full, or executor rejects tasks; verify the producer receives the expected false/exception per contract.
- **Handling test:** handler throws validation or dependency errors; verify failed message and cause are preserved.
- **Cause test:** verify the root exception is not lost when the framework or application wraps errors.
- **Synchronous flow test:** verify whether exceptions propagate back to the caller or are handled by an error handler.
- **Asynchronous flow test:** verify ErrorMessage/error channel or adapter error handlers receive failures as configured.
- **Retry test:** verify attempt counts, backoff, and which exceptions are retried.
- **DLQ test:** verify unprocessable messages are routed to the right place and retain investigative metadata.
- **Idempotency test:** send the same message multiple times and verify business side effects occur only once.

With a broker, test acknowledgements, requeues, redelivery, publisher confirms, and dead-letter policies against the actual broker type being used. These semantics cannot be inferred from the exception class alone.

## 11. Workflow for Handling a Messaging Failure

When receiving a failure, follow this order:

1. Identify the specific exception and its package.
2. Identify the failed message, message ID, correlation ID, and point of origin.
3. Inspect the root cause and stack trace to locate infrastructure, data, or business errors.
4. Check whether the message was accepted by the channel/broker and what state the acknowledgement is in.
5. Classify whether the error is transient, permanent, or a programming bug.
6. Choose bounded retry, error channel, DLQ, or corresponding business handling.
7. Ensure the consumer is idempotent before enabling redelivery/retry.
8. Emit sufficient logs/metrics for tracking without exposing sensitive payloads.

## 12. Key Takeaways

**MessagingException** is the base exception for messaging errors and can hold the failed message along with the cause. **MessageDeliveryException** describes errors when sending or delivering a message. **MessageHandlingException** describes errors while a handler processes a message.

Classifying exceptions helps pinpoint the failure stage, yet does not by itself determine whether the message was persisted, will be retried, or was lost. Those decisions depend on the channel, transport, transactions, and acknowledgements. Preserve failed message and cause, handle errors according to recoverability, bound retries, use DLQs when appropriate, and design idempotent consumers so messaging systems remain resilient under failures.