# ErrorMessage

## 1. Objectives and Scope

In the **Error handling** chapter of the **SPRING_INTEGRATION_CORE** module, `ErrorMessage` is the structure used to represent an error as a message. This enables an integration flow to route errors to a dedicated channel, classify errors with a router, and hand them off to an endpoint for further processing.

After this lesson, you will be able to:

- Correctly read the payload, headers, and original message of an `ErrorMessage`.
- Distinguish between a thrown exception and the message describing that exception.
- Locate the message at the point of failure via `MessagingException.getFailedMessage()`.
- Explain when an error propagates back to the caller and when the infrastructure publishes an error message.
- Configure an error channel, test the error path, and design follow-up handling.

The examples use Java 17, Spring Framework/Spring Integration 6.x APIs, and JUnit Jupiter. Dependency versions should follow your project's compatible BOM or Spring Boot platform. `ErrorMessage` resides in Spring Messaging; Spring Integration provides the infrastructure to publish, route, and handle it within an integration flow.

## 2. ErrorMessage Is a Message with a Throwable Payload

Type to import:

```java
import org.springframework.messaging.support.ErrorMessage;
```

Conceptual model:

```text
ErrorMessage
├── payload: Throwable
│   ├── exception type and error message
│   ├── cause
│   └── failedMessage if payload is an appropriate MessagingException
├── headers: error message metadata
└── originalMessage: optional Message<?>
```

`ErrorMessage` extends `GenericMessage<Throwable>`. Therefore, it still flows through a `MessageChannel` and is consumed by endpoints just like any other message.

However, the payload content has a specific role:

```java
Throwable failure = errorMessage.getPayload();
```

It is the error object, not the order that failed to be processed. Do not cast the payload of an `ErrorMessage` to `Order` or `String` simply because the original business payload had that type.

Because the payload is declared as `Throwable`, do not cast it to `Exception` without a type check either. When analyzing an error, start from the `Throwable` contract and then inspect the concrete type and cause chain.

The structure and constructors are described in the [ErrorMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html).

### An Exception and an Error Message Are Two Different Objects

| Concept | Meaning |
| --- | --- |
| Thrown exception | Interrupts the current execution path following standard Java mechanics |
| `ErrorMessage` | A message object carrying information about an error |
| Error channel | A channel that receives error messages for handling by another endpoint |

Calling `new ErrorMessage(exception)` only creates an object. It does not automatically send it to `errorChannel`, does not log it, and does not trigger business retries.

Conversely, setting an `errorChannel` header on a message does not cause every `throw` statement in the application to be converted into a message. There must be a component that catches the error and publishes the message according to the corresponding mechanism.

A `GenericMessage<Throwable>` can also carry an exception, but it is not an instance of `ErrorMessage` and does not have this class's `originalMessage` property. When an API requires an `ErrorMessage`, preserve that exact type and contract.

## 3. Distinguishing failedMessage, originalMessage, and headers

The three places most easily confused:

| Location | Question it helps answer |
| --- | --- |
| `((MessagingException) error.getPayload()).getFailedMessage()` | Which message was attached to the exception at the point of failure? |
| `error.getOriginalMessage()` | Which message was provided as the original context when creating the error message? |
| `error.getHeaders()` | Which metadata belongs to the error message itself that is being sent? |

### failedMessage Lives on MessagingException

`MessagingException` is the base class for many messaging-related errors. An exception in this hierarchy can hold a reference to the failed `Message<?>`.

For example, `MessageHandlingException` can hold the message that the handler was processing along with the underlying business cause. However, not every `Throwable` is a `MessagingException`, and `getFailedMessage()` may also return `null`.

Basic way to read it:

```java
Throwable failure = error.getPayload();

Message<?> failedMessage = null;
if (failure instanceof MessagingException messagingException) {
    failedMessage = messagingException.getFailedMessage();
}
```

Imports:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
```

If there is another wrapper layer around it, you should inspect the `getCause()` chain rather than checking only the outermost layer. When multiple `MessagingException` instances exist in the chain, choose the context appropriate for the investigation instead of assuming they all hold the same message.

The nullable contract of `failedMessage` is documented in the [MessagingException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html).

### originalMessage Is Not Synonymous with failedMessage

Consider this flow:

```text
M0: input data
    |
    v
transformer
    |
    v
M1: transformed data
    |
    v
handler fails
```

The exception at the handler can attach `failedMessage = M1`. The error-publishing component can provide `originalMessage = M0` if it retained the M0 context.

This is useful when you want to compare the data before and after transformation. However, `originalMessage` is not always present, and it is not guaranteed to be the very first message in the entire system. It is the message provided within the scope where the error message is created.

Having a `failedMessage` on an exception does not automatically make `getOriginalMessage()` non-`null` either.

### Headers Do Not Automatically Become a Copy of the Business Message

The `id` header of the error message identifies the error message itself. It is not by default the order ID or the ID of the failed business message.

Similarly, to find `businessEventId` or `traceId`, you need to check where it was placed:

- In the headers of `failedMessage`.
- In the headers of `originalMessage`.
- Or copied/selectively placed into the headers of `ErrorMessage` by the error-publishing strategy.

Do not call `error.getHeaders().get("orderId")` assuming that every error publisher has copied business headers onto the outer envelope.

## 4. Creating an ErrorMessage with Two Different Contexts

The snippet below can be placed inside a Java method to illustrate the structure:

```java
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

// Inside a method:
Message<String> original = MessageBuilder
    .withPayload("  order-1001  ")
    .setHeader("businessEventId", "event-1001")
    .build();

Message<String> normalized = MessageBuilder
    .withPayload("ORDER-1001")
    .copyHeaders(original.getHeaders())
    .build();

MessageHandlingException failure =
    new MessageHandlingException(
        normalized,
        "Unable to process normalized order",
        new IllegalArgumentException("Invalid order status")
    );

ErrorMessage error = new ErrorMessage(
    failure,
    Map.<String, Object>of("errorCategory", "VALIDATION"),
    original
);
```

Expected values to inspect:

```text
error.payload                         -> failure
failure.failedMessage.payload         -> "ORDER-1001"
error.originalMessage.payload         -> "  order-1001  "
error.headers["errorCategory"]         -> "VALIDATION"
```

The business header `businessEventId` is present on both business messages because the code explicitly created and copied it. The example only puts `errorCategory` into the error message's headers map.

Common constructors:

| Construction | When to use |
| --- | --- |
| `new ErrorMessage(failure)` | Only the error is available |
| `new ErrorMessage(failure, originalMessage)` | An additional message is available as the original context |
| `new ErrorMessage(failure, headers, originalMessage)` | Dedicated metadata needs to be attached for the error path |

The `Throwable` argument must not be `null`. With the different overloads, use a strongly typed variable instead of passing `null` in a position that could make the overload ambiguous to the compiler.

Messages hold references to their payloads. `originalMessage` does not automatically create a deep snapshot of a mutable business object. If you need a record for long-term reconciliation, design appropriate persistent storage rather than treating a Java reference as durable storage.

## 5. When Is an Error Published as an ErrorMessage?

### Synchronous Execution Path

```text
caller thread
  -> DirectChannel
  -> handler
  -> throws exception
  -> exception propagates back to caller
```

When a caller directly invokes `send(...)` through a synchronous chain of `DirectChannel`s, a handler exception propagates back along the call stack. An `errorChannel` header does not by itself alter this mechanism.

If you want to catch the error at the calling layer and publish it as a message, that must be an explicitly designed handling step. Gateways or advices can also provide their own error-publishing mechanisms when configured.

### Polling or Asynchronous Execution Path

```text
caller -> QueueChannel -> caller continues
                |
                v
           poller task
                |
                v
             handler
                |
                v
        error handler / publisher
                |
                v
           ErrorMessage
                |
                v
          error handling channel
```

An error that occurs after the producer has finished placing the message into a queue cannot return back to a `send(...)` call that has already completed. Standard polling infrastructure can catch the exception and publish an `ErrorMessage`.

`ExecutorChannel` also creates an execution boundary when an appropriate asynchronous executor is used. An arbitrary Java thread or executor outside the Integration infrastructure does not automatically share the same error-publishing mechanism.

Differences across execution paths are explained in [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 6. Choosing the Channel to Receive Error Messages

In the standard `MessagePublishingErrorHandler` mechanism, channel selection can be pictured in the following order:

1. The `errorChannel` header of the failed message, when the exception provides that message.
2. The default error channel configured on the error handler.
3. The global `errorChannel` when using the framework default.

For a poller, `@Poller(errorChannel = "orderErrors")` sets the default channel name for the poller's error handler. It is not an unconditional directive that sends every error across the entire application to `orderErrors`.

The header can contain a reference to a `MessageChannel` or a channel name resolved by the infrastructure. When using a channel name, ensure the corresponding bean exists.

Example of setting a per-request error destination:

```java
Message<String> request = MessageBuilder
    .withPayload("ORDER-2001")
    .setHeader("businessEventId", "event-2001")
    .setErrorChannelName("requestErrors")
    .build();
```

If this message fails inside the poller from the example below, `requestErrors` takes precedence over the default `orderErrors` channel. If the source throws an error before a message exists, or the exception does not retain the necessary message, you should not assume this header can be found.

The error handler API is in the [MessagePublishingErrorHandler Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/MessagePublishingErrorHandler.html), and the poller attributes are in the [Poller Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Poller.html).

### The Global Error Channel

The Integration infrastructure creates a default `errorChannel` bean if the application has not defined one. The default channel is a `PublishSubscribeChannel` with a `LoggingHandler` subscribed to log errors.

If the application declares its own `QueueChannel` bean named `errorChannel`, it changes the delivery semantics. A queue holds messages for a consumer to read; the queue itself is not a logger.

In versions using this default mechanism, the default error channel requires subscribers to avoid silently dropping errors when no receiver is present. Therefore, you should account for endpoint shutdown or application context closing phases when designing the error path.

Do not use the global `errorChannel` as a place to "catch every Java exception." An error in a controller, a manually spawned thread, or a regular service method only goes there when wired through a corresponding mechanism.

## 7. Complete Example: Same Error, Two Execution Paths

The following configuration intentionally rejects every order. The goal is to observe the exception and the error message, so there is no real order persistence logic.

Create `ErrorMessageConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHandlingException;

@Configuration
@EnableIntegration
public class ErrorMessageConfiguration {

    @Bean
    public DirectChannel synchronousOrders() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel queuedOrders() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel orderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel requestErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @ServiceActivator(inputChannel = "synchronousOrders")
    public MessageHandler synchronousOrderHandler() {
        return ErrorMessageConfiguration::reject;
    }

    @Bean
    @ServiceActivator(
        inputChannel = "queuedOrders",
        poller = @Poller(
            fixedDelay = "100",
            maxMessagesPerPoll = "1",
            receiveTimeout = "0",
            errorChannel = "orderErrors"
        )
    )
    public MessageHandler queuedOrderHandler() {
        return ErrorMessageConfiguration::reject;
    }

    private static void reject(Message<?> message) {
        throw new MessageHandlingException(
            message,
            "Unable to process order",
            new IllegalArgumentException("Invalid order")
        );
    }
}
```

The handler explicitly creates a `MessageHandlingException` containing the message so that the example has a clear `failedMessage` contract. Framework handlers also commonly wrap business errors in appropriate messaging exceptions, though you do not need to rely on a specific wrapper chain to understand this example.

The main dependency is `org.springframework.integration:spring-integration-core`. `@EnableIntegration` allows the configuration to run using `AnnotationConfigApplicationContext` in a plain Spring Java Configuration environment.

First path:

```text
send -> synchronousOrders -> reject -> exception returned to caller
```

Second path:

```text
send -> queuedOrders -> accepted into queue
                           |
                      polling task
                           |
                         reject
                           |
                       ErrorMessage
                           |
               requestErrors or orderErrors
```

There are no business consumers on the two error channels because the test will read directly from the queues. When a real application has an automatic consumer, do not simultaneously expect a test to also receive the same message from that same queue.

## 8. Testing ErrorMessage

The tests use JUnit Jupiter and reside in the same package as the configuration above.

### 8.1. Verifying That originalMessage and failedMessage Are Independent

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

class ErrorMessageStructureTest {

    @Test
    void keepsOriginalAndFailedMessagesAsSeparateContexts() {
        Message<String> original = MessageBuilder
            .withPayload(" raw-order ")
            .setHeader("businessEventId", "event-structure")
            .build();

        Message<String> failed = MessageBuilder
            .withPayload("NORMALIZED-ORDER")
            .copyHeaders(original.getHeaders())
            .build();

        MessageHandlingException failure =
            new MessageHandlingException(
                failed,
                "Processing failed",
                new IllegalStateException("Downstream dependency not ready")
            );

        ErrorMessage error = new ErrorMessage(failure, original);

        assertSame(failure, error.getPayload());
        assertSame(original, error.getOriginalMessage());
        assertSame(failed, failure.getFailedMessage());
        assertEquals(
            "NORMALIZED-ORDER",
            failure.getFailedMessage().getPayload()
        );

        ErrorMessage withoutOriginal = new ErrorMessage(failure);

        assertNull(withoutOriginal.getOriginalMessage());
        assertSame(
            failed,
            ((MessageHandlingException) withoutOriginal.getPayload())
                .getFailedMessage()
        );
    }
}
```

The test demonstrates that merely omitting the `original` argument when creating an `ErrorMessage` leaves `getOriginalMessage()` empty, while `failedMessage` on the exception still exists.

Do not use the reference check `assertSame` to infer that business data was deep-copied. It only confirms the object instances passed to the constructor in the example.

### 8.2. Verifying Synchronous and Polled Error Paths

Create `ErrorMessageFlowTest.java`:

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ErrorMessageFlowTest {

    @Test
    void synchronousExceptionStillReturnsToCaller() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "synchronousOrders", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "requestErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-SYNC")
                .setErrorChannelName("requestErrors")
                .build();

            MessagingException failure = assertThrows(
                MessagingException.class,
                () -> input.send(request)
            );

            assertNotNull(failure.getFailedMessage());
            assertEquals(
                "ORDER-SYNC",
                failure.getFailedMessage().getPayload()
            );
            assertNull(errors.receive(0));
        }
    }

    @Test
    void polledFailureUsesConfiguredDefaultErrorChannel() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedOrders", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "orderErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-ASYNC")
                .setHeader("businessEventId", "event-async")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = errors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);

            ErrorMessage error = (ErrorMessage) received;
            assertTrue(error.getPayload() instanceof MessagingException);

            MessagingException failure =
                (MessagingException) error.getPayload();
            Message<?> failed = failure.getFailedMessage();

            assertNotNull(failed);
            assertEquals("ORDER-ASYNC", failed.getPayload());
            assertEquals(
                "event-async",
                failed.getHeaders().get("businessEventId")
            );
            assertTrue(
                failure.getCause() instanceof IllegalArgumentException
            );
        }
    }

    @Test
    void requestErrorHeaderOverridesPollerDefault() {
        try (var context = new AnnotationConfigApplicationContext(
                ErrorMessageConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedOrders", MessageChannel.class);
            QueueChannel requestErrors = context.getBean(
                "requestErrors", QueueChannel.class);
            QueueChannel defaultErrors = context.getBean(
                "orderErrors", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("ORDER-OVERRIDE")
                .setErrorChannelName("requestErrors")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = requestErrors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);
            assertNull(defaultErrors.receive(0));
        }
    }
}
```

What is verified:

- An error header does not by itself turn a synchronous call into error-message publishing.
- The poller publishes an `ErrorMessage` to the default channel when no overriding header is present.
- A per-request header can select a different channel ahead of the poller's default channel.
- Business payload and metadata can be traced back from `failedMessage`.

The tests do not require `getOriginalMessage()` to be non-`null` because that context depends on how the error is produced. They use `receive(timeout)` to wait for the message rather than using `Thread.sleep(...)` to guess when polling finishes.

Each test closes the context with `try-with-resources` to stop polling resources after the test. The three-second limit is the example's wait timeout, not an application latency SLA.

These are tests of the error-propagation contract in a minimal configuration. They do not prove retry, transactions, durability, or system load capacity.

## 9. Handling and Routing Error Messages

An error handler may need to:

1. Read the error type and cause.
2. Locate the associated business message, if present.
3. Extract event keys and metadata for reconciliation.
4. Choose a handling path: business rejection, retry evaluation, or escalation to an operator.

Do not rely solely on `failure.getMessage()` to decide behavior. Message strings can change and cannot replace exception types or business error codes.

### Reading Information According to a Clear Contract

A minimal helper method:

```java
public static Message<?> failedMessageOf(ErrorMessage error) {
    Throwable failure = error.getPayload();

    if (failure instanceof MessagingException messagingException) {
        return messagingException.getFailedMessage();
    }

    return null;
}
```

This method only checks the outermost exception layer. If the application has multiple wrapper layers, extend the cause traversal according to your actual contract.

After retrieving the message, you must still check for null values:

```java
Message<?> failed = failedMessageOf(error);
Message<?> original = error.getOriginalMessage();

Object businessEventId = null;

if (failed != null) {
    businessEventId = failed.getHeaders().get("businessEventId");
}

if (businessEventId == null && original != null) {
    businessEventId =
        original.getHeaders().get("businessEventId");
}
```

The fallback snippet above only looks up a single metadata field. It does not claim that `failed` and `original` have the same payload or can be used interchangeably to resubmit the business operation.

### Routing Based on Exception Type

`ErrorMessageExceptionTypeRouter` finds a channel matching the closest mapped cause type, including along the cause chain. This is useful when the outer layer is `MessageHandlingException` while the business cause lies inside.

Standalone configuration example:

```java
package example.integration;

import java.io.IOException;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.router.ErrorMessageExceptionTypeRouter;

@Configuration
@EnableIntegration
public class ErrorRoutingConfiguration {

    @Bean
    public DirectChannel errorEvents() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel invalidOrderErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel retryCandidates() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel unclassifiedErrors() {
        return new QueueChannel(20);
    }

    @Bean
    @ServiceActivator(inputChannel = "errorEvents")
    public ErrorMessageExceptionTypeRouter errorClassifier() {
        ErrorMessageExceptionTypeRouter router =
            new ErrorMessageExceptionTypeRouter();

        router.setChannelMapping(
            IllegalArgumentException.class.getName(),
            "invalidOrderErrors"
        );
        router.setChannelMapping(
            IOException.class.getName(),
            "retryCandidates"
        );
        router.setDefaultOutputChannelName("unclassifiedErrors");

        return router;
    }
}
```

A publisher or error-handling step must send `ErrorMessage` to `errorEvents` for the router to operate. This configuration does not automatically connect to the poller in section 7.

Diagram:

```text
ErrorMessage -> errorEvents -> router
                              ├── IllegalArgumentException -> invalidOrderErrors
                              ├── IOException              -> retryCandidates
                              └── unclassified             -> unclassifiedErrors
```

The router forwards the error message; it does not turn the payload back into an order and does not perform retries. `retryCandidates` is merely a staging channel for errors that need evaluation. Not every `IOException` is safe to retry for an operation with side effects.

Mapping selection semantics are described in the [ErrorMessageExceptionTypeRouter Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/ErrorMessageExceptionTypeRouter.html).

## 10. Error Message Creation Strategy

`ErrorMessageStrategy` separates creating the `ErrorMessage` from the error-publishing component. It receives a `Throwable` and a potentially nullable `AttributeAccessor` context.

`DefaultErrorMessageStrategy` retrieves the message from the context's `ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY` attribute when present in order to set `originalMessage`. Without this information, it creates an error message carrying only the throwable.

This is why an error with a `failedMessage` can still lack an `originalMessage`. The two pieces of data are supplied through two different mechanisms.

A custom strategy can add metadata specific to the error path itself:

```java
import java.util.Map;

import org.springframework.integration.support.ErrorMessageStrategy;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// Local variable or strategy initialization:
ErrorMessageStrategy strategy = (failure, attributes) -> {
    Message<?> original = null;

    if (attributes != null) {
        Object candidate = attributes.getAttribute(
            ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY
        );

        if (candidate instanceof Message<?> message) {
            original = message;
        }
    }

    return new ErrorMessage(
        failure,
        Map.<String, Object>of("errorOrigin", "order-flow"),
        original
    );
};
```

This snippet creates the strategy; it does not yet attach it to a publisher. To take effect, the strategy must be configured on a supporting component, such as via `setErrorMessageStrategy(...)` on an appropriate publisher.

Simply registering an `ErrorMessageStrategy` bean does not mean every error-publishing component in the application automatically uses it. Some adapters have specialized strategies to preserve extra transport context; check the adapter's contract before replacing it.

See [ErrorMessageStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/ErrorMessageStrategy.html) and [DefaultErrorMessageStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/DefaultErrorMessageStrategy.html).

## 11. ErrorMessage Does Not Automatically Provide Retry or Rollback

### Distinguishing the Steps

```text
failure
   |
   v
retry according to policy, if configured
   |
   v
attempts exhausted
   |
   v
recovery / publish ErrorMessage
   |
   v
final error handling or persist for further review
```

An `ErrorMessage` may appear immediately when the error occurs or after retries are exhausted, depending on where and how error publishing is configured. Do not infer the number of attempts solely from seeing one error message.

`ErrorMessageSendingRecoverer` is a mechanism for sending the final error as an `ErrorMessage` after retries are exhausted. You must attach the recoverer and retry advice by design; creating a standalone recoverer bean does not give every handler retry behavior. See the [ErrorMessageSendingRecoverer Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.html).

### Publishing an Error Does Not Restore the Source Message

In the `queuedOrders` example, the poller has already removed the message from the queue before the handler fails. Creating an `ErrorMessage` does not automatically put the old message back onto the queue.

If you want to resend it, you must explicitly decide:

- Whether to resend the message at the point of failure or reconstruct the initial input.
- The maximum number of attempts and the delay between attempts.
- How to prevent duplicate processing when a previous attempt already produced partial side effects.
- Where to route the error when automatic recovery is no longer possible.

If there was already a request header `errorChannel` pointing to an old path, review the header contract when replaying so you do not inadvertently loop back into the same error cycle.

### ErrorMessage Is Not a Transaction Directive

Rollback depends on the transaction manager, participating resources, and where the exception is propagated or handled. A successfully sent error message does not by itself prove that the business transaction rolled back.

Similarly, handing off work via a queue or executor does not automatically propagate a transaction bound to the producer thread to the consumer thread.

In particular, when recovery catches and handles an error, understand whether that mechanism still propagates the exception to the transaction boundary. Design around the contract of the specific transaction and advice rather than using the presence of an `ErrorMessage` as a commit/rollback signal.

### An Error Queue Is Not Yet Dead-Letter Storage

The example's `QueueChannel(20)` is an in-memory queue. It does not retain data across restarts and does not manage "reviewed" or "replayed" states on its own.

If you need to persist errors for later handling, define durable storage, the data to store, business keys, and a state-transition workflow. An error store can persist fields such as:

| Field | Purpose |
| --- | --- |
| `businessEventId` | Links to the business event and supports deduplication |
| Timestamp and failed step | Identifies the scope where the error occurred |
| Error type / error code | Classification and search |
| Attempt count | Controls the recovery policy |
| Required input data or reference to it | Supports controlled reproduction and reprocessing |
| Error handling status | Tracks whether the error has been acknowledged, is in progress, or is resolved |

Do not assume that sending the entire `Throwable` object graph along with Java messages across any transport constitutes a stable data contract. When crossing process boundaries, you typically need to map to an explicit error structure with an appropriate serializer and data schema version.

## 12. The Error-Handling Path Itself Can Fail

Because `ErrorMessage` is a message, sending and handling it can encounter issues:

- A `DirectChannel` error channel has no subscribers.
- An error queue is full and the send operation blocks or times out.
- An error-recording handler throws an exception when the database fails.
- An error consumer replays the same data without a termination condition.

An error flow invoked through a synchronous channel can run directly on the thread reporting the error. Creating an `ErrorMessage` does not automatically spawn a new thread and does not guarantee the main task is freed immediately.

Avoid configurations like:

```text
errorEvents -> error handler -> throws error -> errorEvents -> ...
```

Have a terminal endpoint and a dedicated policy for when persisting or sending the error itself fails. At the same time, preserve enough metadata to distinguish the original business error from the failure of the recording mechanism itself.

When an error-handling action has side effects, such as sending a compensation request, use business keys and appropriate deduplication workflows. Each newly published error message may have a new message ID even though it still describes the same original event.

## 13. Quick Diagnostics When Working with ErrorMessage

| Symptom | What to check |
| --- | --- |
| `errorChannel` header is set, yet caller still receives exception | Is the execution path synchronous, and is any component catching/publishing the error? |
| Cannot cast payload to `Order` | The current payload is `Throwable`; business data resides in the associated message |
| `getOriginalMessage()` returns `null` | Did the strategy or publisher receive the original context? |
| `getFailedMessage()` returns `null` | Was the exception created with a message, and are you inspecting the right wrapper? |
| Business header not found on error envelope | Is the header on `failedMessage` or `originalMessage`? |
| Error goes to a different channel than poller default | Does the failed message have an overriding `errorChannel` header? |
| Error is published but no log appears | What type is the error channel, and is there a consumer/logger attached? |
| Test does not receive error message | Is another consumer reading the same queue, or is the check running before the poller processes it? |
| Error message exists but data was not resent | Are retry/recovery configured, and where is the source data stored? |
| Error messages appear repeatedly | Is the source resending, is retry publishing multiple times, or is the error flow looping? |

When investigating, identify in order **which exception**, **which message failed**, **which component published the ErrorMessage**, and **which channel received it**. These four points help connect technical details with the business event and pinpoint the right place to fix the flow.
