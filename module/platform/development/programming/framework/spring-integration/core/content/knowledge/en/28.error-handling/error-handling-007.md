# MessagingException

## 1. Objectives and Scope

In the **Error handling** chapter of the **SPRING_INTEGRATION_CORE** module, `MessagingException` is the base exception type for describing errors related to message handling and delivery. Its notable feature is that the exception can hold both the cause and the `Message<?>` associated with the failure.

After this lesson, you will be able to:

- Distinguish the error message string, the cause, and the failed message.
- Choose constructors that preserve sufficient context when translating a business error to the messaging layer.
- Interpret subclasses such as `MessageHandlingException` and `MessageDeliveryException`.
- Trace causes through multiple wrapper layers without losing business metadata.
- Explain exception propagation paths and test failures through synchronous channels or pollers.

The examples use Java 17, Spring Framework/Spring Integration 6.x APIs, and JUnit Jupiter. Dependency versions should follow your project's compatible BOM or Spring Boot platform. This lesson focuses on the exception model and error context; retries, transactions, and error flows are mechanisms configured around it.

## 2. Where Does MessagingException Live?

Import to use:

```java
import org.springframework.messaging.MessagingException;
```

It is a class in **Spring Messaging**, used by Spring Integration across many components:

```text
Throwable
  └── Exception
       └── RuntimeException
            └── NestedRuntimeException
                 └── MessagingException
```

Because it extends `RuntimeException`, it is an unchecked exception. Methods are not required to declare `throws MessagingException`, yet callers must still understand that errors can occur when invoking an integration flow.

`MessagingException` is not an annotation, not a `MessageChannel`, and not a message sent over a channel. It is a Java exception object carrying additional messaging-related context.

The class definition and constructors are in the [MessagingException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html).

### Why Is a Plain Exception Insufficient for Context?

Suppose many orders simultaneously pass through a transformer converting money strings into `BigDecimal`. The log only shows:

```text
NumberFormatException: Character N is neither ...
```

You know a conversion failed, yet you still need to determine:

- Which message contained the invalid data?
- What is the business event ID?
- Which step did the error occur at?
- Is there an inner cause that needs separate classification?

A `MessagingException` created with a message and cause provides a structured access point to answer those questions.

## 3. Three Types of Information to Read Separately

| Component | How to access | Meaning |
| --- | --- | --- |
| Error description | `getMessage()` | Human-readable text explaining the failure |
| Direct cause | `getCause()` | Exception wrapped at the immediate inner layer |
| Failed message | `getFailedMessage()` | Message attached directly to this exception, if present |

Example:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

// Placed inside a method:
Message<String> request = MessageBuilder
    .withPayload("NOT-A-NUMBER")
    .setHeader("businessEventId", "event-1001")
    .build();

NumberFormatException cause =
    new NumberFormatException("Invalid monetary value");

MessagingException failure = new MessagingException(
    request,
    "Unable to read order amount",
    cause
);
```

In the example:

```text
failure
├── description: Unable to read order amount
├── cause: NumberFormatException
└── failedMessage
    ├── payload: "NOT-A-NUMBER"
    └── headers["businessEventId"]: "event-1001"
```

Do not cast `failure.getCause()` to a message and do not treat `failure.getFailedMessage()` as an exception.

The description is for human readers, not a stable contract for branching via substring matching. When classification is needed, rely on exception types, business error codes, or designed structured data.

### Commonly Used Constructors

| Constructor | Can hold message? | Can hold cause? |
| --- | --- | --- |
| `MessagingException(description)` | No | Does not take a cause |
| `MessagingException(description, cause)` | No | Yes |
| `MessagingException(message, description)` | Yes | Does not take a cause |
| `MessagingException(message, cause)` | Yes | Yes |
| `MessagingException(message, description, cause)` | Yes | Yes |

The class also has a constructor taking only `Message<?>`. In application code, a clear description along with the cause generally makes investigation more effective.

Choose the overload matching the information actually available at the time of failure. Do not fabricate a dummy message just to make `getFailedMessage()` always non-`null`.

## 4. failedMessage Can Be null and Does Not Automatically Search Causes

This snippet passes no message:

```java
MessagingException failure = new MessagingException(
    "Unable to initialize source reader"
);

Message<?> failed = failure.getFailedMessage(); // null
```

That can be a valid state: the source failed before producing a message, or the code only had error details.

Another easily confused case:

```java
Message<String> request = MessageBuilder
    .withPayload("ORDER-1001")
    .build();

MessagingException inner = new MessagingException(
    request,
    "Error at order processing step"
);

MessagingException outer = new MessagingException(
    "Error at orchestration layer",
    inner
);
```

Result:

```text
outer.getFailedMessage() -> null
outer.getCause()         -> inner
inner.getFailedMessage() -> request
```

The `getFailedMessage()` accessor returns the context attached to **the specific exception instance being called**. It does not automatically walk the cause chain to find a message on an inner exception.

### The Message at the Failure Point Can Differ from the Initial Input

In this flow:

```text
M0: JSON string
  -> transformer
M1: Order object
  -> handler
  -> fails
```

The exception at the handler can hold `failedMessage = M1`. Do not assume the payload can be cast to `String` just because the flow's initial input was JSON.

Similarly, when a splitter produces multiple parts, the failed message may be one of the split parts. To correlate back to the initial request, you need explicit correlation metadata or another preserved context.

Nor is `failedMessage` a deep snapshot of the payload. If the payload is a mutable object, the message reference does not automatically provide a saved state prior to mutations.

## 5. Reading the Cause Chain via NestedRuntimeException

`MessagingException` inherits helper methods from `NestedRuntimeException`:

| Method | Result |
| --- | --- |
| `getCause()` | Immediate inner cause; may be `null` |
| `getRootCause()` | Deepest cause if present; may be `null` |
| `getMostSpecificCause()` | Deepest cause, or the current exception itself if there is no cause |
| `contains(SomeException.class)` | Checks whether the current exception or its cause chain matches that type |

Example:

```java
NumberFormatException root =
    new NumberFormatException("Invalid monetary format");

IllegalArgumentException middle =
    new IllegalArgumentException("Invalid order data", root);

MessagingException failure = new MessagingException(
    request,
    "Unable to process message",
    middle
);

Throwable immediate = failure.getCause();             // middle
Throwable deepest = failure.getRootCause();           // root
Throwable mostSpecific = failure.getMostSpecificCause(); // root
boolean containsFormatError =
    failure.contains(NumberFormatException.class);    // true
```

This snippet assumes `request` is a previously constructed message. Cause-chain inspection methods do not replace reading the message on each wrapper layer.

If the exception has no cause:

```java
MessagingException failure =
    new MessagingException("Messaging error without nested cause");

failure.getRootCause();         // null
failure.getMostSpecificCause(); // failure itself
```

The method contracts are described in the [NestedRuntimeException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/NestedRuntimeException.html).

### The Deepest Cause Is Not Yet the Whole Story

A `NumberFormatException` explains the conversion error. The outer `MessageTransformationException` indicates the error occurred in a transformer role. `failedMessage` reveals which data was being transformed.

When investigating, retain all three dimensions: **processing location/role**, **cause**, and **associated message**. Recording only the deepest exception class loses the integration flow context.

## 6. Subclasses Help Identify the Role Where Failure Occurred

Part of the common inheritance hierarchy:

```text
MessagingException
├── MessageDeliveryException
├── MessageHandlingException
│   └── MessageRejectedException
├── MessageConversionException
└── MessageTransformationException
```

In the diagram, `MessageRejectedException` and `MessageTransformationException` belong to Spring Integration; the remaining listed classes belong to Spring Messaging.

| Error type | Role described | What not to assume automatically |
| --- | --- | --- |
| `MessageDeliveryException` | Error while sending/delivering a message | Does not prove the entire business flow produced no side effects |
| `MessageHandlingException` | Error while handling a message | Does not mean the error is always invalid input data |
| `MessageConversionException` | Error from a `MessageConverter` mechanism | Not synonymous with every error from a transformer |
| `MessageTransformationException` | Conversion error in an Integration transformer role | Do not assume the payload is always a JSON string |
| `MessageRejectedException` | Message rejected by a selector per component mechanism | Does not mean every discarded message must throw an exception |

Packages to distinguish:

```java
org.springframework.messaging.MessageDeliveryException
org.springframework.messaging.MessageHandlingException
org.springframework.messaging.converter.MessageConversionException

org.springframework.integration.transformer.MessageTransformationException
org.springframework.integration.MessageRejectedException
```

`MessageTransformationException` is not a subclass of `MessageConversionException`. The two types describe different abstractions even though both can appear in a data-conversion pipeline.

API documentation: [MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html), [MessageHandlingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandlingException.html), [MessageConversionException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html), [MessageTransformationException](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/MessageTransformationException.html), and [MessageRejectedException](https://docs.spring.io/spring-integration/api/org/springframework/integration/MessageRejectedException.html).

### Choosing What to Catch Based on Goal

- Catch `MessagingException` when you need a single handling point for messaging errors at a flow-invocation boundary.
- Inspect subtypes when the role where the failure occurred dictates handling behavior.
- Inspect causes or business error codes when distinguishing transient failures from data failures.
- Preserve the message and metadata to correlate the specific event.

Do not configure "retry every `MessagingException`." Number format errors, channel configuration errors, and transient connection outages require different recovery approaches.

## 7. Creating Exceptions at the Right Boundary and Preserving Causes

When writing a custom component that works directly with `Message<?>`, you can wrap errors using an appropriate subtype to keep both the message and the cause.

Example handler that only validates an amount string:

```java
import java.math.BigDecimal;

import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.MessageHandlingException;

// Inside a method:
MessageHandler validateAmount = message -> {
    Object payload = message.getPayload();

    if (!(payload instanceof String text)) {
        throw new MessageHandlingException(
            message,
            "Amount validation payload must be a String"
        );
    }

    try {
        new BigDecimal(text);
    }
    catch (NumberFormatException cause) {
        throw new MessageHandlingException(
            message,
            "Unable to validate amount",
            cause
        );
    }
};
```

This is a validation handler, not a transformer emitting `BigDecimal` to another channel. It illustrates converting a specific conversion error into a handling error with message context.

### Avoid Losing Information

The following drops both the cause and message context:

```java
catch (NumberFormatException cause) {
    throw new MessagingException(cause.getMessage());
}
```

Preserve both when available:

```java
catch (NumberFormatException cause) {
    throw new MessageHandlingException(
        message,
        "Unable to validate amount",
        cause
    );
}
```

At the same time, do not wrap with another layer at every tier just to reword the message. If a `MessagingException` already accurately describes the failed step, rethrowing it can preserve subtype and context better than replacing it with a generic exception.

When an orchestration layer genuinely needs wrapping, keep the old exception as the cause and verify what message belongs to the new layer. An outermost wrapper holding a different message from an inner layer should accurately reflect the processing boundary.

### Do Not Force the Business Layer to Depend on Messaging Just to Report Errors

A plain service can accept `Order` and throw its own business exception. The endpoint or adapter at the messaging boundary is responsible for associating that error with `Message<?>`.

Conversely, a custom `MessageHandler` that already knows the message can directly construct a `MessageHandlingException`. Choosing this boundary keeps context clear without passing `Message` through every application layer.

## 8. Complete Example: Amount-Parsing Transformer

The configuration below has two inputs:

- `directAmountRequests` is a `DirectChannel`, allowing the caller to observe synchronous errors.
- `queuedAmountRequests` is a `QueueChannel`, allowing a poller to process and report errors via a dedicated channel.

Both transformers convert `String` into `BigDecimal`. Malformed strings cause the `BigDecimal` constructor to throw `NumberFormatException`.

Create `MessagingFailureConfiguration.java`:

```java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
public class MessagingFailureConfiguration {

    @Bean
    public DirectChannel directAmountRequests() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel queuedAmountRequests() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel parsedAmounts() {
        return new QueueChannel(20);
    }

    @Bean
    public QueueChannel amountErrors() {
        return new QueueChannel(20);
    }

    @Bean
    public AmountParser amountParser() {
        return new AmountParser();
    }

    public static class AmountParser {

        @Transformer(
            inputChannel = "directAmountRequests",
            outputChannel = "parsedAmounts"
        )
        public BigDecimal parseDirect(String text) {
            return new BigDecimal(text);
        }

        @Transformer(
            inputChannel = "queuedAmountRequests",
            outputChannel = "parsedAmounts",
            poller = @Poller(
                fixedDelay = "100",
                maxMessagesPerPoll = "1",
                receiveTimeout = "0",
                errorChannel = "amountErrors"
            )
        )
        public BigDecimal parseQueued(String text) {
            return new BigDecimal(text);
        }
    }
}
```

`AmountParser` is managed by Spring via `@Bean` so its annotated methods can be processed. `@EnableIntegration` enables Integration infrastructure when running plain Spring Java Configuration.

The primary dependency is `org.springframework.integration:spring-integration-core`. The example only performs number format conversion and does not check business rules such as currency, value limits, or decimal scale.

### When Data Is Valid

```text
Message<String>("125000.50")
        |
        v
transformer
        |
        v
Message<BigDecimal>(125000.50)
        |
        v
parsedAmounts
```

### When Data Is Invalid

```text
Message<String>("NOT-A-NUMBER")
        |
        v
new BigDecimal(...)
        |
        v
NumberFormatException
        |
        v
messaging error represented by transformer infrastructure
        |
        v
failedMessage holds the associated message
```

The messaging layer may add wrappers describing a transformer or method-invocation failure. Therefore, the tests below check `contains(NumberFormatException.class)` and message context rather than hardcoding a single wrapper chain.

## 9. Where Do Synchronous Paths and Poller Paths Differ?

### 9.1. DirectChannel: Exceptions Can Return to the Caller

```text
caller -> directAmountRequests -> transformer -> fails
   ^                                             |
   └─────────── exception along call stack ──────┘
```

In this configuration, calling `send(...)` on the direct source executes the transformer on the caller thread. An error can propagate back to the send call.

You can handle it at the calling boundary:

```java
try {
    input.send(request);
}
catch (MessagingException failure) {
    Message<?> failed = failure.getFailedMessage();
    Throwable cause = failure.getMostSpecificCause();

    // Record or forward the error per the application's contract.
}
```

This snippet illustrates a catch boundary; `input` and `request` must be the channel and message being sent. If you merely log and exit the catch block, the caller may no longer know the operation failed. Define clearly whether to rethrow, return an error result, or hand off to another mechanism.

### 9.2. QueueChannel and Poller: Caller Finishes Sending Before Error Handling

```text
caller -> queuedAmountRequests -> send completes
                    |
                    v
              polling task
                    |
                    v
                transformer
                    |
                    v
              MessagingException
                    |
                    v
              ErrorMessage
                    |
                    v
                amountErrors
```

The producer only knows the queue accepted the message. An exception thrown later during poller processing cannot return into a `send(...)` call that already completed.

Standard polling infrastructure catches the error and can publish an `ErrorMessage`; the payload of the error message is a `Throwable`, typically a messaging exception retaining the failed message.

`@Poller(errorChannel = "amountErrors")` sets the default channel for the poller's error handler in the example. An `errorChannel` header on the failed message can choose a different destination when the infrastructure finds that header.

### 9.3. MessagingException and ErrorMessage Do Not Swap Roles

| Type | Role |
| --- | --- |
| `MessagingException` | Thrown in Java; can hold `failedMessage` and cause |
| `ErrorMessage` | Sent over a channel; payload is `Throwable` |
| Error channel | Destination receiving error messages for endpoint processing |

```java
MessagingException failure = new MessagingException(
    request,
    "Unable to process message"
);

ErrorMessage error = new ErrorMessage(failure);
```

This snippet creates the error message without sending it yet. `error.getPayload()` is `failure`; the business message is traced via `failure.getFailedMessage()`.

Setting an `errorChannel` header also does not automatically catch every synchronous exception. Gateways can have their own error-mapping or publishing mechanisms per configuration; do not generalize `MessageChannel.send(...)` behavior into the contract of every gateway.

See [Spring Integration Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

## 10. Deliberately Locating the Message Through a Wrapper Chain

When receiving an arbitrary `Throwable` from an error flow, the outer layer might not be a `MessagingException` or might have no `failedMessage`. If the requirement is to find the outermost message with context, you can use a helper method.

Create `FailureContexts.java`:

```java
package example.integration;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

public final class FailureContexts {

    private FailureContexts() {
    }

    public static Message<?> firstFailedMessage(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );

        Throwable current = failure;

        while (current != null && visited.add(current)) {
            if (current instanceof MessagingException messagingException) {
                Message<?> failed =
                    messagingException.getFailedMessage();

                if (failed != null) {
                    return failed;
                }
            }

            current = current.getCause();
        }

        return null;
    }
}
```

The method's contract:

- Walks from the outermost exception down the cause chain.
- Returns the first non-`null` message found.
- Returns `null` if no message context exists.
- Tracks visited objects to avoid infinite loops if a cyclic cause chain is encountered.

This is a helper defined by the lesson, not a built-in Spring method. It does not walk suppressed exceptions and does not select "the earliest system message."

If each exception layer holds a message from a different stage, the first message found may differ from the deepest cause's message. For other investigative goals, collect each context and interpret it by its corresponding processing boundary.

## 11. Testing the Exception Contract and Integration Flow

The snippets below use the same `example.integration` package as the configuration in section 8 and the helper in section 10.

### 11.1. Testing Message, Cause, and Missing Context Cases

Create `MessagingExceptionContractTest.java`:

```java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessagingExceptionContractTest {

    @Test
    void preservesProvidedMessageAndCause() {
        Message<String> request = MessageBuilder
            .withPayload("BAD-AMOUNT")
            .setHeader("businessEventId", "event-contract")
            .build();

        NumberFormatException cause =
            new NumberFormatException("Invalid format");

        MessagingException failure = new MessagingException(
            request,
            "Failed to read amount",
            cause
        );

        assertSame(request, failure.getFailedMessage());
        assertSame(cause, failure.getCause());
        assertSame(cause, failure.getRootCause());
        assertSame(cause, failure.getMostSpecificCause());
        assertTrue(failure.contains(NumberFormatException.class));
    }

    @Test
    void outerWrapperDoesNotAutomaticallyExposeInnerFailedMessage() {
        Message<String> request = MessageBuilder
            .withPayload("ORDER-1001")
            .build();

        MessageHandlingException inner =
            new MessageHandlingException(
                request,
                "Error inside handler",
                new IllegalStateException("Downstream service not ready")
            );

        MessagingException outer = new MessagingException(
            "Error at orchestration layer",
            inner
        );

        assertNull(outer.getFailedMessage());
        assertSame(request, inner.getFailedMessage());
        assertSame(
            request,
            FailureContexts.firstFailedMessage(outer)
        );
        assertTrue(outer.contains(IllegalStateException.class));
    }

    @Test
    void exceptionWithoutCauseHasNoRootCause() {
        MessagingException failure =
            new MessagingException("Error without cause");

        assertNull(failure.getFailedMessage());
        assertNull(failure.getRootCause());
        assertSame(failure, failure.getMostSpecificCause());
    }
}
```

These assertions verify the contract of objects constructed in this lesson; they do not imply that every framework component always produces the exact same subtype or number of wrapper layers.

### 11.2. Testing the Transformer with Valid and Invalid Data

Create `MessagingFailureFlowTest.java`:

```java
package example.integration;

import java.math.BigDecimal;

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

class MessagingFailureFlowTest {

    @Test
    void validAmountIsTransformed() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "directAmountRequests", MessageChannel.class);
            QueueChannel output = context.getBean(
                "parsedAmounts", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("125000.50")
                .build();

            assertTrue(input.send(request));

            Message<?> result = output.receive(0);
            assertNotNull(result);
            assertEquals(
                new BigDecimal("125000.50"),
                result.getPayload()
            );
        }
    }

    @Test
    void directFailureRetainsCauseAndBusinessContext() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "directAmountRequests", MessageChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("NOT-A-NUMBER")
                .setHeader("businessEventId", "event-direct")
                .build();

            MessagingException failure = assertThrows(
                MessagingException.class,
                () -> input.send(request)
            );

            assertTrue(failure.contains(NumberFormatException.class));

            Message<?> failed =
                FailureContexts.firstFailedMessage(failure);

            assertNotNull(failed);
            assertEquals("NOT-A-NUMBER", failed.getPayload());
            assertEquals(
                "event-direct",
                failed.getHeaders().get("businessEventId")
            );
        }
    }

    @Test
    void polledFailureIsReportedThroughErrorMessage() {
        try (var context = new AnnotationConfigApplicationContext(
                MessagingFailureConfiguration.class)) {

            MessageChannel input = context.getBean(
                "queuedAmountRequests", MessageChannel.class);
            QueueChannel errors = context.getBean(
                "amountErrors", QueueChannel.class);
            QueueChannel output = context.getBean(
                "parsedAmounts", QueueChannel.class);

            Message<String> request = MessageBuilder
                .withPayload("INVALID")
                .setHeader("businessEventId", "event-polled")
                .build();

            assertTrue(input.send(request, 1_000));

            Message<?> received = errors.receive(3_000);
            assertNotNull(received);
            assertTrue(received instanceof ErrorMessage);

            ErrorMessage error = (ErrorMessage) received;
            assertTrue(error.getPayload() instanceof MessagingException);

            MessagingException failure =
                (MessagingException) error.getPayload();

            assertTrue(failure.contains(NumberFormatException.class));

            Message<?> failed =
                FailureContexts.firstFailedMessage(failure);

            assertNotNull(failed);
            assertEquals("INVALID", failed.getPayload());
            assertEquals(
                "event-polled",
                failed.getHeaders().get("businessEventId")
            );
            assertNull(output.receive(0));
        }
    }
}
```

The success test reads with `receive(0)` because the transformer runs synchronously and already sent the output before `send(...)` returned. The polling test uses `receive(3_000)` to wait for the result from the scheduled task.

Do not use `Thread.sleep(...)` to guess when processing completes. Closing the context with `try-with-resources` stops polling resources after each test.

The tests verify the contracts that matter: valid data is transformed; invalid data preserves cause and business context; polled errors arrive on the error channel. They do not measure load capacity, retry mechanisms, transactions, or recovery after a process stops.

## 12. Using Exception Details for Diagnostics

When encountering a `MessagingException`, inspect it in this sequence:

1. Identify the operation just performed: sending a message, calling a gateway, transforming, or business handling.
2. Inspect the subtype and wrappers to understand the failure boundary.
3. Inspect the immediate cause, deepest cause, and error category for classification.
4. Locate `failedMessage` on the appropriate exception layer.
5. Extract the business key, trace ID, and processing step info.
6. Determine whether the error was returned to the caller or sent through an error flow.

Example details to retain for a failure:

```text
businessEventId = event-polled
step            = parse-amount
messagingType   = observed messaging exception class
causeType       = NumberFormatException
failedPayload   = value being converted
```

`step` is metadata supplied by the application or observability tooling; it is not a default field present on every `MessagingException`.

Some framework-generated exceptions include configuration source details, such as a bean method or XML resource. Use that information to pinpoint the endpoint, but do not build parsers tied to the wording of stack traces.

### Choose Metadata Instead of Relying on toString()

`toString()` or exception logs may display the message text and related payload. However, that string is not a versioned data structure for another application to parse.

When persisting or sending error reports, select fields such as event ID, failed step, error type, business error code, and data reference. Keep the cause for technical diagnostics and use structured data for operational workflows.

### Quick Diagnostics Table

| Symptom | What to check |
| --- | --- |
| `getFailedMessage()` is `null` | Did the constructor receive a message, or is the message on an inner cause? |
| Only `MessageHandlingException` is visible | What is the inner cause; is there a method-invocation wrapper? |
| Type error when reading failed payload | Did the message pass through a transformer/splitter before failing? |
| Business header not found | Are you reading headers from the right failed message or from the error envelope? |
| Error does not return to caller after queue send | Did work move to a poller or another thread? |
| `errorChannel` header is set yet exception is still thrown | Are you sending on a synchronous path with no error-publishing mechanism? |
| Exception caught and system reports success | Is the catch block swallowing the error or returning a default success result? |
| Logs lose the original cause | Did some layer rewrap using only `cause.getMessage()`? |
| Same error keeps reappearing | Is invalid data being retried, is the source resending, or is the error flow looping? |

## 13. MessagingException Does Not Decide Retry, Rollback, or Resubmission

The exception type provides information about the failure. The handling policy must be defined separately.

### Retries Must Consider Cause and Side Effects

In the example, sending the exact same `"NOT-A-NUMBER"` string back into the same parser will keep failing unless the data or logic changes. A blanket retry for every `MessagingException` only repeats failing work.

For connection errors, you must also know whether the operation might have completed in the external system before the connection dropped. Stable business keys and duplicate-processing prevention can matter more than merely increasing attempt counts.

`contains(SomeException.class)` helps check types in the cause chain, yet by itself is not a complete retry policy. The retry layer still needs attempt limits, backoff, recovery conditions, and a terminal state.

### An Unchecked Exception Does Not Automatically Guarantee Rollback

Transactions only take effect when configured and scoped across the right resource boundaries. A thrown `MessagingException` can trigger rollback of an enclosing transaction per active rules, but it does not automatically start a new transaction or distributed transaction.

If code catches the error and does not rethrow, the transaction boundary may not observe the failure as expected. Similarly, handing work off through a queue or executor does not automatically propagate a transaction bound to the producer thread.

### failedMessage Is Not a Requeue Mechanism

The accessor only returns a message reference held inside the exception. It does not automatically:

- Return the message to the source.
- Restore an item already removed from an in-memory queue.
- Undo a call to an external system.
- Persist data across restarts.
- Mark the event as processed or retries exhausted.

If resubmission is needed, choose the right entry point: the message at the failed step may already have been transformed and therefore no longer match the initial input channel.

In a flow with filters, transformers, routers, and aggregators, the same event ID can appear under several message shapes. `MessagingException` is most useful when you preserve the right context at the failure boundary and use business metadata to link those steps together.
