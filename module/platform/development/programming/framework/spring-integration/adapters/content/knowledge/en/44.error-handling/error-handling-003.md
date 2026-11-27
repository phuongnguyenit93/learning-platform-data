# ErrorMessage and MessagingException in Spring Integration

## 1. Two Core Concepts of Message-Based Error Handling

When connecting external systems through **Spring Integration**, an application typically builds a pipeline **inbound adapter/gateway → MessageChannel → transformer or service activator → outbound adapter/gateway**. Messages carry a payload and headers; the system may process synchronously on the caller's thread or asynchronously via pollers, queues, task executors, or listeners.

Errors can appear at any stage: reading files, connecting over SFTP, converting JSON, calling HTTP, receiving/sending JMS, AMQP, or Kafka, or persisting to a database. **ErrorMessage** and **MessagingException** carry failure information across processing boundaries, yet they play two distinct roles:

- **MessagingException:** a **Java exception** in the Spring Messaging hierarchy, optionally attached to the **failed Message**. It describes a failure while sending, converting, handling, or routing a message.
- **ErrorMessage:** a **Spring Message** whose payload is a **Throwable**, commonly a `MessagingException`. It is used when an error-handling mechanism **converts an exception into a message and publishes it to a MessageChannel**.

A quick way to remember:

~~~text
Exception in code                    Error event traveling over a message channel
┌─────────────────────┐              ┌────────────────────────────┐
│ MessagingException  │  --wrap-->   │ ErrorMessage               │
│  failedMessage?     │              │  payload: Throwable        │
│  cause?             │              │  originalMessage?          │
└─────────────────────┘              │  headers                   │
                                     └────────────────────────────┘
~~~

The wrap arrow is **a handling possibility**, not a step that always occurs. In a synchronous flow using `DirectChannel`, an exception may be thrown back to the caller **without generating an ErrorMessage**. Conversely, a poller or asynchronous task with an error publisher can create an `ErrorMessage` to report the failure via a channel.

### Lesson Objectives

After completing this lesson, learners can:

1. Distinguish `Message`, `Throwable`, `MessagingException`, and `ErrorMessage`.
2. Safely read **failedMessage**, **originalMessage**, headers, and the cause chain.
3. Explain when errors are thrown back to the sender and when they are published to an error channel.
4. Create/consume `ErrorMessage`, and use `MessagingException` and its subclasses properly.
5. Understand **ErrorMessageStrategy**, the `errorChannel` header, and the global error channel.
6. Classify errors in File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC without confusing exceptions with retry/ack.
7. Write tests verifying the error contract and design logging, recovery, security, and operations.

Within the **SPRING_INTEGRATION_ADAPTERS** module, the focus is how these two data types link adapters with **MessageChannel**, gateways, pollers, message contracts, and connection lifecycles. This lesson covers the general mechanics first; adapter-specific behaviors should be verified against your actual dependencies and configuration.

## 2. Distinguishing ErrorMessage, MessagingException, and Related Components

| Concept | Nature | Contains | Where Used |
|---|---|---|---|
| Message<?> | Spring Messaging message contract | Payload and headers | Communication between endpoints and channels |
| Throwable | Root of Java error hierarchy | Message, cause, stack trace | Representing Java errors |
| MessagingException | Runtime exception of Spring Messaging | Error details, cause, and optional failedMessage | Signaling message processing failures |
| MessageHandlingException | Subclass of MessagingException | Failure context while a handler processes | Service activator, transformer, handler |
| MessageDeliveryException | Subclass of MessagingException | Failure context when sending/delivering a message | Sending to channel/handler |
| MessageConversionException | Subclass of MessagingException | Invalid conversion context | Message conversion |
| ErrorMessage | Message<Throwable> | Throwable payload, headers, optional originalMessage | Channel-based error handling flows |
| ErrorMessageStrategy | How to build an ErrorMessage from Throwable and context | Error message construction logic | Error publishing component |
| ErrorMessagePublisher | Infrastructure for publishing ErrorMessage | Error destination and strategy | Recovery/error flow when configured |
| errorChannel | Conventional message channel name | Carries ErrorMessage | Error handling destination |

**Package distinction:** `MessagingException`, `MessageHandlingException`, and `MessageDeliveryException` belong to **org.springframework.messaging**; `ErrorMessage` belongs to **org.springframework.messaging.support**; while some publishing/strategy infrastructure belongs to **org.springframework.integration.support** or the corresponding package per version.

### 2.1. An Exception Is Not a Spring Message

An `IllegalStateException` thrown from a service activator is still a Java `Throwable`. It **does not automatically have headers**, does not automatically enter `errorChannel`, and does not automatically hold the message being processed. Spring Integration may wrap the exception in a `MessagingException` or convert it into an `ErrorMessage` depending on the processing point. Inspect the actual execution path rather than inferring from the exception name.

### 2.2. ErrorMessage Is a Message About an Error, Not a Copy of Business Data

If the input payload is `OrderCommand` and the handler fails, `ErrorMessage` will have a `Throwable` payload—**not OrderCommand**. To replay, retrieve business data from `failedMessage`, `originalMessage`, or a trusted recovery store; do not send `ErrorMessage` directly into an input channel expecting `OrderCommand`.

### 2.3. The Exception Might Not Be a MessagingException

The payload of `ErrorMessage` is typed as **Throwable**. It can hold a `MessagingException`, `IllegalArgumentException`, an `IOException` passed in, or another `Throwable`. Therefore:

- Do not cast every `ErrorMessage` payload to `MessagingException`;
- Use `instanceof` before calling `getFailedMessage()`;
- Do not assume `ErrorMessage` always contains `originalMessage`;
- Classify the root cause appropriately without discarding wrapper context.

## 3. MessagingException Structure

According to Spring Messaging, `MessagingException` is the base class for messaging errors and extends an **unchecked exception**. It can retain a reference to the message at the time of failure via **getFailedMessage()**; this value may be **null** if the exception was created without a message.

### 3.1. Simplified Class Hierarchy

~~~mermaid
flowchart TD
    T["Throwable / RuntimeException"]
    M["MessagingException"]
    H["MessageHandlingException"]
    D["MessageDeliveryException"]
    C["MessageConversionException"]
    R["DestinationResolutionException"]
    O["Other subclasses depending on version"]
    T --> M
    M --> H
    M --> D
    M --> C
    M --> R
    M --> O
~~~

This diagram is an abbreviated view of the exception family. Spring may add subclasses across versions and modules. A business exception or adapter library exception (HTTP client, JDBC driver, JMS API...) may sit in the **cause chain** rather than being a direct subclass.

### 3.2. Commonly Used Constructor Structure

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder
        .withPayload("order-274")
        .setHeader("correlationId", "import-274")
        .build();

MessagingException withoutMessage =
        new MessagingException("No message context");

MessagingException withMessage =
        new MessagingException(input, "Import failed",
                new IllegalStateException("Database unavailable"));

System.out.println(withoutMessage.getFailedMessage()); // May be null
System.out.println(withMessage.getFailedMessage() == input); // true
System.out.println(withMessage.getCause().getClass().getSimpleName());
~~~

Because `failedMessage` can be null, exception-handling code must not access `getHeaders()` directly without checking first. **getCause()** returns the Java cause, not the content of `failedMessage`.

### 3.3. MessageHandlingException and MessageDeliveryException

**MessageHandlingException** is commonly used when a handler encounters an error processing a message, including when the framework wraps exceptions from business logic. **MessageDeliveryException** describes a failure while delivering/sending a message. You should not decide permanent vs. transient **solely** by class: a `MessageHandlingException` can wrap a transient timeout, while a `MessageDeliveryException` might stem from a nonexistent target channel or a long-term misconfiguration.

Example:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessageDeliveryException;

MessageHandlingException handling = new MessageHandlingException(
        input, "Order validation failed",
        new IllegalArgumentException("Missing customerId"));

MessageDeliveryException delivery = new MessageDeliveryException(
        input, "Cannot deliver to outbound channel");
~~~

These examples illustrate exception types and purposes. When using another Spring Framework version, verify constructors and packages in the Javadoc matching your actual dependency.

### 3.4. Preserving Wrapper Context and Root Cause

Useful details typically reside at two levels:

| Level | Meaning | Example |
|---|---|---|
| MessagingException | Which flow/message failed? | failedMessage ID, correlation |
| Nearest cause | What did the handler or library throw? | DataAccessException |
| Root cause | Deepest technical cause when present | SQLTransientConnectionException |

Do not strip wrappers by logging only the root cause: doing so can lose `failedMessage` and the integration flow location. Conversely, logging only `MessageHandlingException` misses the real DB error. The right approach is recording **exception type, safe context, and cause chain**.

## 4. ErrorMessage Structure: Payload, Headers, and originalMessage

**ErrorMessage** extends `GenericMessage<Throwable>`. Its API exposes `getPayload()`, `getHeaders()`, and **getOriginalMessage()** (nullable). Including `originalMessage` helps preserve the input at the time the error message was constructed if data was transformed before the exception occurred.

### 4.1. Example of a Data-Transforming Flow

~~~mermaid
sequenceDiagram
    participant F as File inbound
    participant T as Transformer
    participant H as JDBC handler
    participant E as Error publisher
    participant CH as errorChannel
    F->>T: M0: File payload + headers
    T->>H: M1: OrderCommand + headers
    H-->>E: MessagingException with failedMessage=M1
    E->>CH: ErrorMessage payload=exception
    Note over E,CH: originalMessage may be M0 or the input provided by the strategy
~~~

The diagram depicts **the possibility of having originalMessage**, not a guarantee that every flow and error strategy automatically retains `M0`. If the framework only sees the input at the transformed handler point, `originalMessage` may be `M1`; if context is unavailable, this field may be null.

### 4.2. Comparing Three Different Contexts

| Value | Where It Lives | Required? | Meaning |
|---|---|---|---|
| ErrorMessage.payload | error.getPayload() | Yes, a Throwable | The published exception |
| MessagingException.failedMessage | exception.getFailedMessage() | No | Message attached to the exception at the failure point |
| ErrorMessage.originalMessage | error.getOriginalMessage() | No | Original message provided by the error builder/strategy |
| ErrorMessage.headers | error.getHeaders() | Yes | Metadata of the error message, not necessarily input headers |
| failedMessage.headers | failed.getHeaders() | Only if failedMessage exists | Metadata at the point where the message failed |
| exception.cause | throwable.getCause() | No | Deeper cause in the exception chain |

**Common pitfall:** `ErrorMessage` does not have its own `getFailedMessage()` method. To get `failedMessage`, check whether the payload is a `MessagingException`, then call **MessagingException.getFailedMessage()**. By contrast, `originalMessage` is a direct method on `ErrorMessage`.

### 4.3. Creating ErrorMessage with Constructors

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

Message<String> original = MessageBuilder
        .withPayload("raw-order-274")
        .setHeader("correlationId", "import-274")
        .build();

Message<Integer> transformed = MessageBuilder
        .withPayload(274)
        .setHeader("correlationId", "import-274")
        .build();

MessageHandlingException exception = new MessageHandlingException(
        transformed, "Could not persist order",
        new IllegalStateException("DB offline"));

ErrorMessage error = new ErrorMessage(exception, original);

System.out.println(error.getPayload() == exception);          // true
System.out.println(error.getOriginalMessage() == original);   // true
System.out.println(exception.getFailedMessage() == transformed); // true
~~~

Here the error message has **payload = exception**, the exception holds **failedMessage = transformed**, and `ErrorMessage` keeps **originalMessage = original** because the code explicitly provided it. This constructor does **not** deduce the original message from the call stack.

### 4.4. ErrorMessage Headers Do Not Replace Original Headers

A newly created `ErrorMessage` has its own metadata such as ID and timestamp. Trace/correlation data from the source message **does not necessarily** appear directly in `error.getHeaders()`. If you need correlation, check `originalMessage` or `failedMessage` and fall back to recovery context information. Do not blindly cast or log all headers because they may contain credentials, tokens, or sensitive details.

## 5. When Does an Exception Become an ErrorMessage?

This is a central question in integration systems. **The existence of errorChannel does not guarantee every exception is published.**

### 5.1. Synchronous DirectChannel

~~~text
Caller
  |
  v
DirectChannel ---> Service Activator ---> Exception
  ^                                       |
  |-------------- throw -----------------+
~~~

`DirectChannel` normally invokes handlers on the sender's thread. Uncaught exceptions in the flow can propagate back to the caller. A gateway or template may have exception-mapping mechanics per contract, but **an ErrorMessage is not created by default**.

### 5.2. Poller or Asynchronous Processing

~~~text
Scheduler/Executor --> Poller/Handler --> Exception
                                           |
                                   Error handler catches error
                                           |
                                   ErrorMessageStrategy
                                           |
                                 ErrorMessage -> Channel
~~~

In standard Spring Integration setups, tasks running via a scheduler/executor and pollers can use **MessagePublishingErrorHandler** to publish an `ErrorMessage`. When no specific error destination is configured, global **errorChannel** may be used as a fallback.

This depends on **the error strategy, task scheduler, and adapter/container**. Do not assume every error in JMS/AMQP/Kafka listeners automatically goes through the same `errorChannel` without configuration.

### 5.3. Gateways and Errors Returned to the Caller

A messaging gateway has a request/reply contract. By default, many downstream errors are **unwrapped and thrown back to the caller**. If the gateway is configured with an appropriate error flow, the error can be routed as a message and the result converted into a reply or `Throwable` returned to the caller, depending on configuration.

When a handler returns a message with a `Throwable` payload, a gateway may treat it as an error to throw back to the caller per gateway semantics. This differs from a service activator arbitrarily returning an `ErrorMessage` onto an ordinary business channel; read the specific gateway contract carefully.

### 5.4. Reference Behavior Table

| Scenario | Initial Exception | ErrorMessage Produced? | What to Verify |
|---|---|---|---|
| DirectChannel + synchronous handler | Usually goes to sender | Not automatically | Caller/advice/gateway |
| Scheduler poller + error publisher | Caught by task's handler | Can publish | Error strategy and channel |
| ExecutorChannel | Exception off sender thread | Can publish | Executor and error handler |
| QueueChannel with consumer poller | Consumer receives/processes on its own schedule | Can publish | Consumer poller policy |
| Synchronous HTTP inbound gateway | Error may throw back to request | Not automatically to global | HTTP status, response/error flow |
| JMS/AMQP inbound adapter | Has container/broker semantics | Depends on adapter/config | Ack, rollback, redelivery |
| Kafka inbound | Has container and offset | Depends on adapter/config | Commit, retry, DLT |

## 6. errorChannel and ErrorMessage Routing

### 6.1. Global Channel

Spring Integration provides a channel named **errorChannel** in typical default configurations. Per reference documentation, the default channel is a **PublishSubscribeChannel** with a **LoggingHandler** subscribed to log errors. Application configurations may replace or customize it.

When a component supports error publishing, there are usually two ways to pick an error destination:

1. **The `errorChannel` header** of the request `Message` (if supported by that component and resolvable);
2. **Global `errorChannel`** when no specific destination applies.

The header uses the standard name **MessageHeaders.ERROR_CHANNEL**. It is neither a `Throwable` nor an `ErrorMessage`. The header may hold a channel name or a reference supported by the resolver; behavior depends on the specific error-sending mechanism.

### 6.2. Example Attaching the errorChannel Header

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;

Message<String> request = MessageBuilder
        .withPayload("order-274")
        .setHeader(MessageHeaders.ERROR_CHANNEL, "orderErrors")
        .setHeader("correlationId", "import-274")
        .build();
~~~

This snippet **only attaches the header**. It does not create the `orderErrors` bean, does not automatically catch exceptions, and does not guarantee a synchronous handler will emit an `ErrorMessage`. You must create the matching channel/consumer and configure an error-publishing path that actually reads the header.

### 6.3. PublishSubscribeChannel Subscribers

~~~text
                      +--> LoggingHandler (if still configured)
ErrorMessage --> errorChannel
                      +--> Custom error observer
                      +--> Metrics/alerting observer
~~~

Multiple subscribers can receive the same `ErrorMessage`. Adding another handler may cause **duplicate error logs** if the default `LoggingHandler` remains active. If a handler performs side effects such as sending email, writing to a DB, or retrying, design explicit ownership and idempotency rather than assuming only one handler receives the message.

In Spring Integration versions, the global channel may support **requireSubscribers** configuration so messages are not silently dropped when no subscribers exist; exact behavior depends on version and application config. Do not replace the global bean solely to make reading errors convenient; a per-flow channel is usually safer when recovery needs dedicated policies.

## 7. Writing a Safe ErrorMessage Handler

### 7.1. Listening to the Error Channel with a Service Activator

The example below uses **@ServiceActivator** to register a handler for `ErrorMessage`s published to the default channel. It distinguishes the wrapper, `failedMessage`, and `originalMessage`, and avoids logging the business payload directly.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.stereotype.Component;

@Component
public class IntegrationFailureObserver {

    private static final Logger log =
            LoggerFactory.getLogger(IntegrationFailureObserver.class);

    @ServiceActivator(inputChannel = "errorChannel")
    public void onError(ErrorMessage error) {
        Throwable failure = error.getPayload();
        Message<?> failedMessage = null;

        if (failure instanceof MessagingException messagingFailure) {
            failedMessage = messagingFailure.getFailedMessage();
        }

        Message<?> original = error.getOriginalMessage();
        Message<?> contextMessage =
                failedMessage != null ? failedMessage : original;

        Object correlationId = contextMessage != null
                ? contextMessage.getHeaders().get("correlationId")
                : null;

        Throwable root = rootCause(failure);
        log.error(
                "Integration failure: type={}, rootType={}, correlationId={}, " +
                        "hasFailedMessage={}, hasOriginalMessage={}",
                failure.getClass().getSimpleName(),
                root.getClass().getSimpleName(),
                correlationId,
                failedMessage != null,
                original != null,
                failure);
    }

    private static Throwable rootCause(Throwable throwable) {
        Throwable cursor = throwable;
        for (int i = 0; i < 32 && cursor.getCause() != null; i++) {
            if (cursor.getCause() == cursor) {
                break;
            }
            cursor = cursor.getCause();
        }
        return cursor;
    }
}
~~~

**Prerequisites:** Spring Integration, component scanning, annotation endpoints, and a logging framework; the example uses Java with pattern matching for `instanceof`. The `correlationId` header name is an application convention, not a header automatically added by every adapter. In production, assess whether logging stack traces might expose sensitive information.

### 7.2. Why Fall Back from failedMessage to originalMessage?

For instance, a handler throws `IllegalStateException` directly and the error publisher does not wrap it in a `MessagingException`. In that case **getFailedMessage is unavailable**, yet `ErrorMessageStrategy` may have preserved the input under `originalMessage`. Conversely, if the exception was wrapped with `failedMessage` while the strategy did not know the initial input, `originalMessage` can be null. Falling back improves observability, **not a guarantee of recovering the entire payload**.

### 7.3. Keep Heavy Business Logic Out of Observers

An observer should typically:

- Classify exceptions and write structured logs/metrics;
- Pass a reference to a durable recovery workflow when needed;
- Avoid performing risky data writes by default;
- Avoid infinitely retrying the same error inside the error handler;
- Handle failures of the external alerting/logging system;
- Rate-limit alerts to avoid duplicate notifications.

When using `PublishSubscribeChannel`, multiple subscribers can cause multiple side effects. Recovery needs a clear policy: **who actually owns retry, quarantine, nack, or DLQ**.

### 7.4. When the Handler Does Not Receive ErrorMessage

To debug, check step-by-step:

1. Was the exception thrown from a **synchronous DirectChannel** back to the caller?
2. Does the task/executor/poller use an error publisher?
3. Did the request have an `errorChannel` header pointing to a dedicated channel?
4. Does the gateway have its own error flow or unwrap exceptions?
5. Is the handler subscribed in the right context and to the exact channel bean?
6. Does the channel type have subscribers, `requireSubscribers`, and a running state?
7. For a broker listener, did the container handle the exception before reaching the integration error publisher?

Seeing no message on `errorChannel` **does not mean there were no errors**.

## 8. ErrorMessageStrategy: How Is ErrorMessage Built from Context?

Spring Integration provides **ErrorMessageStrategy** to construct an `ErrorMessage` from a `Throwable` and an **AttributeAccessor context**. The **DefaultErrorMessageStrategy** implementation reads the input message supplied via **ErrorMessageUtils.INPUT_MESSAGE_CONTEXT_KEY** and uses it as `originalMessage` if present.

### 8.1. Purpose of Separating Strategy from Publisher

| Component | Responsibility |
|---|---|
| ErrorMessageStrategy | Decides how ErrorMessage holds Throwable, originalMessage, and metadata |
| ErrorMessagePublisher | Handles publishing the ErrorMessage per integrated mechanism |
| MessagePublishingErrorHandler | Handles task exceptions when used, publishing to the right channel |
| MessageChannel | Transports ErrorMessage to subscribers |
| Recovery handler | Chooses logging, retry, quarantine, alerting, or another action |

Separating these layers maintains a consistent error contract without forcing every endpoint into the same retry strategy.

### 8.2. Example Using DefaultErrorMessageStrategy

~~~java
import org.springframework.integration.support.DefaultErrorMessageStrategy;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

Message<String> input = MessageBuilder
        .withPayload("raw-order-274")
        .build();

Message<Integer> atFailure = MessageBuilder
        .withPayload(274)
        .build();

MessageHandlingException failure = new MessageHandlingException(
        atFailure, "Persist failed", new IllegalStateException("DB offline"));

DefaultErrorMessageStrategy strategy = new DefaultErrorMessageStrategy();
ErrorMessage result = strategy.buildErrorMessage(
        failure,
        ErrorMessageUtils.getAttributeAccessor(input, atFailure));

System.out.println(result.getOriginalMessage() == input); // true
System.out.println(((MessageHandlingException) result.getPayload())
        .getFailedMessage() == atFailure); // true
~~~

The code above demonstrates **creating an ErrorMessage with context using Spring Integration APIs**; by itself it **does not send** the message to `errorChannel`. To publish, use a component/error publisher or send the message to the target channel through an application-controlled mechanism.

### 8.3. Context Differs from Java ThreadLocal

A task can switch threads when crossing an executor or async gateway. Do not rely on business `ThreadLocal` values following an exception across all boundaries. Information needed for error processing should live in **Message headers** or an **explicitly passed context** with appropriate permissions/limits.

### 8.4. When Is a Custom Strategy Needed?

You can design a custom strategy when the system needs standardized metadata such as `flowName`, `integrationStage`, correlation ID, and recovery reference, or needs to redact sensitive data before publishing. However, customization must respect:

- The payload of `ErrorMessage` is a **Throwable**;
- `originalMessage` must reflect the actual input provided, never fabricated;
- Context may be null when an error occurs before a message exists;
- Never leak secrets or PII through the error channel or error store;
- Do not turn the error message into a channel re-carrying oversized business payloads.

## 9. Classifying Exceptions Without Losing Information

### 9.1. Wrapper and Root Cause

For example, a JDBC flow receives an `OrderCommand` and the DB is unavailable:

~~~text
MessageHandlingException
  failedMessage: OrderCommand(orderId=274)
  cause: DataAccessResourceFailureException
    cause: SQLException / connection failure
~~~

If you only log `SQLException`, operators lose which **message and endpoint** failed. If you only log `MessageHandlingException`, they miss that the DB lacked connectivity. Store both **wrapper context + deepest cause**.

### 9.2. Do Not Classify Every MessageHandlingException the Same Way

| Spring-Level Exception | Cause / Context | Actionability |
|---|---|---|
| MessageHandlingException | HTTP timeout | May retry if safe and idempotent |
| MessageHandlingException | Business validation failed | Usually do not retry verbatim |
| MessageHandlingException | Database unavailable | Can use bounded retry/backoff |
| MessageDeliveryException | Channel has no subscriber | Fix flow/config, do not just retry |
| MessageDeliveryException | Queue/channel congested | Needs backpressure/timeout/limits |
| MessageConversionException | Payload cannot convert | Fix schema/content type or quarantine |
| MessagingException without failedMessage | Pre-Message stage or created without context | Use other context, avoid null dereference |

This is a classification guide, not a rigid rule for every implementation. For instance, an HTTP timeout may have already caused a downstream side effect even though the caller received no response; retries must guard against business duplicates.

### 9.3. Retain Error Classification at Multiple Levels

An error-processing system can retain:

- **exceptionClass:** `MessageHandlingException` or `MessageDeliveryException`;
- **rootCauseClass:** `IOException`, `SQLException`, etc.;
- **errorCategory:** `INVALID_INPUT`, `TRANSIENT`, `PERMISSION`, `CONFLICT`, `UNKNOWN`;
- **stage:** `RECEIVE`, `TRANSFORM`, `VALIDATE`, `PERSIST`, `OUTBOUND_SEND`, `ACK`;
- **disposition:** `RETRYING`, `QUARANTINED`, `DEAD_LETTERED`, `REJECTED`, `MANUAL_REVIEW`;
- **attempt:** attempt count and retry budget;
- **businessKey/correlationId:** reference for lookup without sensitive data.

**Do not equate `exceptionClass` with `errorCategory`.** Mapping requires knowing data, protocol, and business contracts.

### 9.4. Multi-Layer Wrapped Errors

An error subscriber receives `ErrorMessage.payload` as a `Throwable`, yet the cause chain may contain multiple wrappers from Spring Integration, HTTP clients, drivers, or brokers. Checking only `failure.getClass()` can be insufficient. Conversely, unbounded cause traversal can loop on unusual `Throwable`s; the example in Section 7 bounds the depth.

### 9.5. Error Messages Do Not Always Contain Replayable Data

A `MessagingException` constructed from only a description string can have `failedMessage = null`. An `ErrorMessage` built solely from a `Throwable` has `originalMessage = null`. If incident recovery is mandatory, maintain a **durable recovery reference** and retain contract-compliant input before relinquishing ownership.

## 10. Message Headers and Security Boundaries

### 10.1. Correlation ID Is Not Message ID

| Value | Purpose | Characteristics |
|---|---|---|
| MessageHeaders.ID | Framework-generated identifier for a specific message | Can change when creating new messages |
| MessageHeaders.TIMESTAMP | Timestamp when message was created | Not when business work completed |
| correlationId | Links steps of a business transaction | Usually application-defined or upstream-supplied |
| errorChannel header | Selects error destination if error publisher supports it | Not proof of access authorization |
| failedMessage.headers | Metadata at point of failure | May differ from input headers |
| originalMessage.headers | Metadata of message supplied when building ErrorMessage | May be absent or stale |

Do not infer correlation by forcing different message IDs to match. When creating new messages across transformers, propagate the correlation ID intentionally.

### 10.2. Never Take the errorChannel Header Blindly from Untrusted Clients

If an external HTTP request or Kafka record is allowed to supply an arbitrary `errorChannel` value, it could try directing errors to an internal channel not meant for the caller. Restrict/strip externally supplied control headers and set error destinations only inside trusted integration flows.

### 10.3. Protecting Failed Payloads

`failedMessage` may contain:

- File contents with PII or financial data;
- HTTP bodies, tokens, or cookies;
- SQL statements or parameters containing sensitive data;
- Broker events belonging to customer tenants;
- References to large resources.

**Do not log `failedMessage.toString()` directly in production** without understanding how payloads and headers are formatted. Log IDs, error types, stage, correlation, and masked fields. Only store payload copies when recovery genuinely requires it, with encryption, authorization, and proper retention.

## 11. ErrorMessage Across Spring Integration Adapters

### 11.1. Comparison Matrix

| Adapter / Gateway | Source Exceptions | ErrorMessage Context to Retain | What Not to Assume |
|---|---|---|---|
| File inbound poller | I/O, parse, validation | File reference, filter state, correlation | File will be re-read automatically |
| SFTP inbound/outbound | SSH/session, network, permission, rename | Remote path, stage, session failure | Remote file was untouched |
| HTTP inbound gateway | Validation, handler, mapping | Request context and status mapping | Correct HTTP response from errorChannel alone |
| HTTP outbound gateway | Timeout, HTTP 4xx/5xx, conversion | Safe URI identifier, method, status, idempotency key | Timeout means server did not process |
| JMS inbound/outbound | Conversion, listener, broker | Message ID, destination, delivery attempt | ErrorMessage equals rollback |
| AMQP inbound/outbound | Consumer/producer, nack/requeue | Delivery metadata and broker disposition | Sent to DLQ just because of ErrorMessage |
| Kafka inbound/outbound | Deserialization, handler, offset, producer | Topic/partition/offset if present, event key | Offset rewound or sent to DLT |
| JDBC inbound/outbound | SQL, constraint, transaction | Row/business key, transaction outcome | DB definitely rolled back all side effects |

Each adapter has its own **connection lifecycle, acknowledgment, retry, and transaction** behavior. `ErrorMessage` is an envelope for published error events, not a universal transaction contract.

### 11.2. File and SFTP: Context May Not Yet Be a Spring Message

Errors can occur before the poller reads a file or constructs a message; then there is no `failedMessage` to inspect. If the file was picked up and the handler failed schema parsing, `failedMessage` may hold a `File` or transformed payload. You must also design **file readiness checks, AcceptOnce/persistent filters, quarantine, replay policies**, and idempotency to prevent lost or duplicate processing.

### 11.3. HTTP: Exceptions and HTTP Status Are Two Contracts

With a synchronous inbound gateway, the caller needs an appropriate HTTP response. An `ErrorMessage` sent to an async channel can aid auditing, but does not replace mapping 400/403/409/500/503 and the error body. With outbound HTTP, HTTP 4xx/5xx may be treated by the client as exceptions or responses depending on config; do not assume they are always `MessageHandlingException`.

### 11.4. JMS/AMQP: Error Details Do Not Decide Acknowledgment

The broker needs to know whether a message is acked, nacked, rejected, rolled back, or redelivered per container and transaction mode. If a handler swallows an exception after publishing `ErrorMessage`, the container may treat processing as complete. Conversely, rethrowing can trigger redelivery. Decisions must align with **DLQ and poison-message handling**.

### 11.5. Kafka: Record Position Is Crucial Context

When a failure happens in a Kafka listener, the cause may originate in the deserializer, converter, handler, or offset commit. **CommonErrorHandler/DefaultErrorHandler** and the Kafka container's DLT are separate mechanisms, not equivalent to `errorChannel`. If you need record retries or offset adjustments, check container behavior together with the adapter.

### 11.6. JDBC: Transactions Do Not Live Inside ErrorMessage

A `DataAccessException` may appear in the cause of a `MessageHandlingException`. `ErrorMessage` itself does not guarantee JDBC transaction rollback or downstream HTTP compensation. Distributed operations require transaction boundaries, outbox/inbox, idempotency, and reconciliation.

## 12. From ErrorMessage to Recovery: Do Not Confuse Observing an Error with Resolving It

### 12.1. Four Questions to Answer

When receiving an `ErrorMessage`, the handler should not immediately "retry that exact message". First determine:

1. **At which stage did the error occur?** Before receiving input, after transform, after DB write, after HTTP send, or at offset commit?
2. **Did the action already produce side effects?** An HTTP timeout may happen after the target persisted data.
3. **Is there a durable original to replay?** `failedMessage`/`originalMessage` might only be in-memory objects.
4. **Who owns retry/ack authority?** Poller, transaction advice, broker container, Kafka listener, recovery worker, or business system?

A global error observer **does not have enough information to decide every protocol**. Route to per-flow and per-adapter recovery policies.

### 12.2. Outcome States

| State | Meaning | Recommended Evidence |
|---|---|---|
| OBSERVED | Error info received | ID and exception type |
| CLASSIFIED | Determined transient/permanent/unknown | Stage, cause, resource, context |
| RETRY_SCHEDULED | Scheduled retry task exists | Retry key, attempt, due time |
| RETRY_EXHAUSTED | Stopped retrying per policy | Attempt count, reason, recovery destination |
| QUARANTINED | Bad data stored in isolation | Reference, owner, retention |
| DEAD_LETTERED | Broker/queue/topic stored message via its mechanism | DLQ/DLT reference and disposition |
| COMPENSATING | Handling side effects requiring compensation | Business transaction reference |
| RECOVERED | Business outcome reached desired state | Verified at target system |
| MANUAL_REVIEW | Indeterminate outcome or unsafe to retry | Owner, deadline, data to reconcile |

These states belong to a **custom business workflow**, not a built-in `ErrorMessage` enum.

### 12.3. Bounded Retry and Idempotency

Retries belong at the right layer: Spring Integration advice, HTTP client, broker/container, retry worker, or a dedicated flow. Do not repeat the same operation at multiple layers without calculating a **retry budget**.

For example: advice retries up to 3 times, and the Kafka listener retries up to 5 times. Total calls to the target HTTP endpoint can reach 15 (excluding client-level retries), causing overload and duplicate side effects.

Safe retry requirements typically include:

- Conditions by error category; never infinitely retry validation/authorization errors;
- Max attempts and max duration, with backoff and jitter;
- Business key/idempotency key or duplicate-check mechanism;
- Final disposition when retries are exhausted;
- Sufficient info for investigation and controlled replay.

### 12.4. ErrorMessageSendingRecoverer and Retry Advice

Spring Integration provides components for combining retry and recovery, such as **ErrorMessageSendingRecoverer**, usable in a retry advice recovery callback to publish error info after exhausting attempts. This helps when you want an `ErrorMessage` **with request context** for recovery.

However, **publishing successfully does not mean external systems rolled back**. For message-driven adapters, examine the relationship between the callback, final exception, and broker/container acknowledgment.

### 12.5. Why Should You Not "Swallow" Exceptions?

Suppose a JMS listener processes `OrderCommand` and a JDBC insert fails. The handler catches the exception, sends an `ErrorMessage`, and returns normally. If the container relies on method completion to acknowledge, the message may be acked even though the order was never saved.

If the goal is broker redelivery, explicitly design when to **propagate/rethrow** so the transaction or container recognizes failure. If the goal is saving to a durable retry store and acking the source, prove recovery persistence succeeded before acking.

## 13. Designing an Error Event Contract for Integrated Systems

Spring `ErrorMessage` has a `Throwable` payload, suited to the application runtime. To transmit error details across external queues/topics or persist them long-term, you normally need a standardized **business error event**.

### 13.1. Logical Schema Example

~~~json
{
  "eventType": "integration.message.failed",
  "eventVersion": 1,
  "flowId": "sftp-orders-import",
  "adapter": "SFTP_INBOUND",
  "stage": "PERSIST",
  "sourceMessageId": "msg-274",
  "correlationId": "batch-2026-274",
  "businessKey": "order-274",
  "exceptionClass": "MessageHandlingException",
  "rootCauseClass": "SQLTransientConnectionException",
  "category": "TRANSIENT",
  "attempt": 3,
  "disposition": "MANUAL_REVIEW",
  "recoveryReference": "quarantine/item-274",
  "occurredAt": "2026-11-23T08:15:00Z"
}
~~~

This is an **application-defined schema**, not a raw serialized `ErrorMessage`. Do not export arbitrary `Throwable` objects or full stack traces/customer payloads externally due to compatibility, security, and size concerns.

### 13.2. The Contract Must Capture Info Needed for Replay

| Component | Role | Rule |
|---|---|---|
| Business key | Business identification | Usable for dedupe/idempotency |
| Correlation ID | Trace steps in same chain | Propagate across flow when possible |
| Source reference | Points to file, topic/partition/offset, queue, or record | Do not expose references beyond access rights |
| Flow/stage | Locate failure point | Use stable, versioned names |
| Error category | Decide retry vs. quarantine | Have taxonomy and mapping |
| Retry attempt | Track retry progress | Update atomically in workflow when needed |
| Outcome | Retried, quarantined, or permanent fail? | Do not mark RECOVERED until verified |
| Data retention | When to purge event and input copy | Follow regulations and policies |

### 13.3. Do Not Treat ErrorMessage as a Durable Queue

A `PublishSubscribeChannel` typically resides in application memory and dispatches to configured subscribers. If the process stops, unpersisted `ErrorMessage`s can be lost. To guarantee post-restart error handling, design a **durable store/queue**, appropriate transactions/acks, and reconciliation.

### 13.4. Normalizing Exceptions Across API Boundaries

In an internal flow, passing a Java `Throwable` works. Across REST or external events, translate into contract-compliant error codes, controlled descriptions, request IDs, and statuses. Never expose internal class names, stack traces, or DB connection details to external callers.

## 14. Error Observability: Logs, Metrics, and Tracing

### 14.1. Traceable Logging

Logs should include `flowId`, `endpointId`, adapter, `correlationId`, `messageId`, exception type, root cause type, stage, attempt, disposition, and timestamp. If `failedMessage` exists, extract **publishable metadata** without logging the raw payload.

Example:

~~~text
level=ERROR
flow=sftp-orders-import
stage=parse-csv
correlationId=batch-274
exceptionType=MessageHandlingException
rootCauseType=IllegalArgumentException
errorCategory=INVALID_INPUT
disposition=QUARANTINED
~~~

### 14.2. Useful Metrics

| Metric | Meaning |
|---|---|
| error_messages_published_total | Count of published ErrorMessages in observed scope |
| integration_failures_total | Actual failures by flow/stage/category |
| recovery_attempts_total | Retry count |
| recovery_exhausted_total | Failures exhausting retries and needing disposition |
| error_handler_failures_total | Failures within the error handler itself |
| quarantine_backlog | Volume of unprocessable items |
| dlq_depth or dlt_lag | Backlog of dead-lettered messages |
| last_successful_poll | Detects pollers that stopped reading messages |
| processing_latency | Latency of successful and failed processing |

**Do not use `messageId`, `orderId`, or `correlationId` as metric labels** due to high cardinality. Keep them in access-controlled logs/traces, and keep metrics bounded to flow/type/status labels.

### 14.3. Tracing Across Boundaries

As a message flows File → transformer → HTTP → Kafka, code must propagate trace/correlation context properly. `ErrorMessage.originalMessage` or `failedMessage` can help inspect headers, but **there is no guarantee full span context survives** every transformation or thread boundary.

### 14.4. Zero ErrorMessages Does Not Mean a Healthy Flow

A stopped file poller or misconfigured SFTP directory with no matching files may throw zero exceptions. Metrics must track heartbeats, last successful poll, oldest message age, and backlog; relying solely on `ErrorMessage` counts misses silent failures.

## 15. Case Study: ErrorMessage When Importing Orders from SFTP

### 15.1. Hypothetical Flow

Company A receives CSV files via SFTP from Partner B. Spring Integration fetches files via a poller, a transformer creates `OrderCommand`, a service activator writes via JDBC, and HTTP outbound sends order confirmation. The result is emitted to Kafka.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound poller"]
    FILE["File / CSV"]
    CMD["OrderCommand transformer"]
    JDBC["JDBC persist"]
    HTTP["HTTP outbound"]
    KAFKA["Kafka producer"]
    EP["Error publisher / strategy"]
    ERR["errorChannel or flow-specific channel"]
    REC["Quarantine / retry / alert"]
    SFTP --> FILE --> CMD --> JDBC --> HTTP --> KAFKA
    JDBC -. "exception" .-> EP
    CMD -. "exception" .-> EP
    EP --> ERR --> REC
~~~

In practice, whether errors pass through `EP` depends on the poller/error strategy and topology. The diagram shows **a configured error path**, not a claim that every message pipeline publishes errors automatically.

### 15.2. Case A: File Cannot Be Downloaded

The poller has not yet created a `Message` when the SFTP connection times out. The error publisher receives a `Throwable` with task context; **failedMessage may be null**, and `originalMessage` may be null. Use connection logs, flow name, and safe target path to investigate. Handle with backoff retries, alerts on threshold breach, and remote/local file state checks.

### 15.3. Case B: CSV Parsing Fails

The initial message `M0` holds the `File`, and the transformer reads the CSV and encounters an invalid column. A `MessageHandlingException` may hold `failedMessage` pointing to the `File` or the transformer's message. If `ErrorMessageStrategy` knows `M0`, `originalMessage = M0`; it is not guaranteed to hold the entire file bytes.

Because schema errors are permanent, move the file to quarantine and ask the sender to fix it instead of retrying continuously. Account for the File/SFTP adapter's filter/metadata so the file is neither lost nor double-read.

### 15.4. Case C: JDBC Insert Fails

Message `M1` contains `OrderCommand`; JDBC cannot connect. `ErrorMessage.payload` may contain `MessageHandlingException`, `failedMessage = M1`, `cause = DataAccessException`. Retry may be appropriate here, but you must know which rows already committed to avoid duplicate orders. If some rows were saved, use idempotency keys or reconcile before replay.

### 15.5. Case D: HTTP Outbound Timeout

The message was written to the DB; the HTTP request went out, but the caller lost the response. An `ErrorMessage` with a timeout exception **does not prove the partner did not receive the request**. Use an idempotency key or query status to avoid confirming an order twice. If the outcome is unclear, move to `MANUAL_REVIEW` or a reconciliation workflow.

### 15.6. Case E: Kafka Publish Error

JDBC and HTTP may have succeeded, yet the Kafka producer reports an error. `ErrorMessage` cannot roll back earlier steps. You can use a transactional outbox tied to the DB to record the "intent to publish", then have a publisher retry; consumers must be idempotent for duplicate deliveries. Kafka DLT/retry policies are separate mechanisms, not automatically created from `errorChannel`.

### 15.7. Three Lessons

1. **Error layer:** `MessagingException` links errors with `failedMessage` at the point of processing.
2. **Error path:** `ErrorMessage` transports `Throwable` and context over channels when publishing is configured.
3. **Recovery:** check side effects across files, DB, HTTP, and Kafka; receiving an `ErrorMessage` alone does not prove a message was retried or resolved.

## 16. Unit Testing ErrorMessage and MessagingException Contracts

### 16.1. Testing ErrorMessage with Separate originalMessage and failedMessage

This is a standalone Spring Messaging API-level test proving two distinct message references. No file system or broker is needed.

~~~java
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class ErrorMessageContractTest {

    @Test
    void keepsOriginalAndFailedMessagesSeparate() {
        Message<String> input = MessageBuilder
                .withPayload("raw-order")
                .setHeader("correlationId", "batch-274")
                .build();

        Message<Integer> transformed = MessageBuilder
                .withPayload(274)
                .build();

        MessageHandlingException failure = new MessageHandlingException(
                transformed,
                "JDBC write failed",
                new IllegalStateException("database unavailable"));

        ErrorMessage error = new ErrorMessage(failure, input);

        assertSame(failure, error.getPayload());
        assertSame(input, error.getOriginalMessage());
        assertTrue(error.getPayload() instanceof MessagingException);
        assertSame(transformed,
                ((MessagingException) error.getPayload()).getFailedMessage());
    }
}
~~~

**Meaning:** `ErrorMessage` has `originalMessage` because the constructor was passed `input`; `MessagingException` has `failedMessage` because the constructor was passed `transformed`. This verifies the data API, **not a real error publisher or adapter**.

### 16.2. Testing Missing Context

~~~java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

class MissingErrorContextTest {

    @Test
    void allowsMissingMessageReferences() {
        MessagingException failure =
                new MessagingException("Task failed before message creation");
        ErrorMessage error = new ErrorMessage(failure);

        assertSame(failure, error.getPayload());
        assertNull(failure.getFailedMessage());
        assertNull(error.getOriginalMessage());
    }
}
~~~

**Meaning:** `null` is a normal case. Production error handlers must have fallbacks to still record stage, flow, or scheduler metadata from other sources when available.

### 16.3. Testing Strategy When Context Exists

Another test can construct `MessageHandlingException`, pass context via `ErrorMessageUtils`, and assert `getOriginalMessage()` as in Section 8. When `INPUT_MESSAGE_CONTEXT_KEY` is omitted, `DefaultErrorMessageStrategy` can create an `ErrorMessage` without `originalMessage`.

### 16.4. Scope of Unit Tests

The API tests above verify object structure but **do not** prove:

- Whether exceptions in `DirectChannel` are published or thrown;
- Whether a poller has an error handler configured;
- How JMS/AMQP/Kafka brokers ack or roll back;
- Whether business data is preserved if sending `ErrorMessage` fails;
- Whether retries duplicate database records.

Those scenarios require **integration tests** against real endpoints and configuration.

## 17. Integration Testing Adapter Error Paths

### 17.1. Case A — DirectChannel and Caller

Build a synchronous flow with a handler throwing `IllegalStateException`. Send a message via a gateway or `MessagingTemplate`. Verify the exception reaches the caller per design or is mapped by the gateway. Do not assert that global `errorChannel` always receives a message when no error publisher exists.

### 17.2. Case B — Poller Publishes ErrorMessage

Create a periodically polled inbound source whose handler throws an exception. Configure a dedicated error channel for testing, such as **QueueChannel testErrors**, and explicitly configure the endpoint/poller to use it.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;

@Configuration
class ErrorTestChannels {

    @Bean
    QueueChannel testErrors() {
        return new QueueChannel();
    }
}
~~~

In the test, after the poller runs, retrieve the `testErrors` bean and assert receipt of an `ErrorMessage`. Illustrative assertion snippet:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

// Assumes QueueChannel testErrors is injected from the Spring context.
Message<?> received = testErrors.receive(5_000);
if (!(received instanceof ErrorMessage error)) {
    throw new AssertionError("Expected ErrorMessage");
}
if (error.getPayload() == null) {
    throw new AssertionError("Expected Throwable payload");
}
~~~

**Important:** this assertion snippet is not a standalone test file; the flow, poller, and `testErrors` must be configured/injected first. Do not replace production's global `errorChannel` with a `QueueChannel` merely for test convenience.

### 17.3. Case C — Is the errorChannel Header Honored?

Create a message with `MessageHeaders.ERROR_CHANNEL` pointing to `testErrors`; use an endpoint/error publisher supporting that header and intentionally trigger an error. Verify `ErrorMessage` arrives on the expected channel. Run a similar test with a synchronous `DirectChannel` to observe that **setting the header alone does not catch exceptions**.

### 17.4. Case D — Handler Failure Inside the Error Flow Itself

Make the error channel subscriber throw an exception or simulate logging/alerting unavailability. Determine:

- Is `ErrorMessage` still delivered to other subscribers?
- Is the handler error ignored, or does it break the main flow?
- Does it create an error-handling loop?
- Can it recover without duplicating notifications?
- Does business data remain in a durable source for replay?

Answers depend on `PublishSubscribeChannel`, subscriber ordering, and dispatch/error-handling configuration.

### 17.5. Per-Adapter Test Matrix

| Adapter | Injected Fault | Assertions Beyond ErrorMessage |
|---|---|---|
| File | Invalid CSV | File state, quarantine, and replay |
| SFTP | Timeout or permission | Reconnect/backoff, remote file not mishandled |
| HTTP inbound | Invalid payload | HTTP 4xx/5xx and response contract |
| HTTP outbound | Timeout or 503 | Retry budget, idempotency, outcome |
| JMS | Handler throws | Ack/rollback, redelivery, and DLQ |
| AMQP | Poison message | Nack/requeue/DLX/DLQ |
| Kafka | Deserialize/processing failure | Container error policy, offset, and DLT |
| JDBC | DB unavailable | Transaction, row state, and duplicate prevention |

Reading an `ErrorMessage` only confirms the **error notification path**; asserting state in source/target systems demonstrates **operational semantics**.

## 18. Runbook for Investigating an ErrorMessage

### Step 1: Identify How It Arrived

Check whether `ErrorMessage` was published by a **poller**, **task executor**, **gateway error flow**, **retry recoverer**, or **adapter listener/container**. Identify the bean/endpoint, channel, timestamp, message ID, and how it chose its destination (per-message, per-endpoint, or global).

### Step 2: Read the Structure Correctly

~~~text
if ErrorMessage:
    failure = payload
    original = getOriginalMessage()  // may be null

if failure instanceof MessagingException:
    failed = failure.getFailedMessage()  // may be null
    inspect cause chain
else:
    failed = null

use metadata safely; do not log secrets
~~~

Determine whether `failedMessage`'s payload is a `File`, `byte[]`, `String`, JSON document, `OrderCommand`, JMS/Kafka record, or another type. Avoid casting based on assumptions from the first adapter; a transformer may have changed the payload.

### Step 3: Classify Cause and Impact

- Is it a permanent input error or transient infrastructure error?
- Has the message already been acked, committed, moved, or deleted?
- Which side effects did downstream HTTP/DB/Kafka already create?
- If retrying, is idempotency or deduplication in place?
- Was correlation, ownership, or recovery reference lost?

### Step 4: Choose Disposition

| Condition | Action |
|---|---|
| Transient and safe to retry | Retry with backoff/limits |
| Invalid payload | Quarantine or notify producer to fix data |
| Wrong authentication/permissions | Fix trust/credentials, avoid aggressive retries |
| Indeterminate HTTP outcome | Reconcile business state |
| Broker poison message | DLQ/DLT per container/broker policy |
| Partial side effects committed | Compensation or idempotent replay |
| Missing failedMessage/originalMessage | Trace source reference, logs, and state; do not guess |

### Step 5: Verify After Recovery

Verify how many messages were retried, which succeeded, which were quarantined, and how many records/orders remain pending or backlogged. Never close an incident solely because an error log exists or a notification handler succeeded.

## 19. Common Mistakes

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Casting every ErrorMessage.payload to MessagingException | ClassCastException in error handler | Check with instanceof |
| Calling getFailedMessage without a null check | NullPointerException | Handle missing context gracefully |
| Assuming originalMessage is always the flow's first message | Replaying wrong payload/phase | Verify strategy/context |
| Reading error.getHeaders as input headers | Wrong correlation and metadata | Inspect original/failed headers |
| Assuming every throw reaches errorChannel | Missing synchronous DirectChannel errors | Distinguish throw vs. publish |
| Adding errorChannel header and thinking you're done | No error publisher, no handler | Configure endpoint and test |
| Logging raw Throwable/failedMessage with sensitive payloads | Data or secret leaks | Masking, safe metadata, and log limits |
| Treating ErrorMessage as a durable retry message | Data loss on process restart | Durable recovery storage and proper ack |
| Sending ErrorMessage into business input | Schema mismatch, creates new errors | Replay proper business command |
| Retrying all MessageHandlingExceptions | Poison messages loop forever | Classify cause and enforce retry budget |
| Catching exception and returning success in listener | Broker may ack even if DB write failed | Design container/transaction error policy |
| Thinking ErrorMessage creates DLQ or Kafka DLT | Misunderstood delivery semantics | Configure broker/container separately |
| Logging only root cause, dropping failedMessage | Missing flow and business key info | Retain wrapper context |
| Using PublishSubscribeChannel expecting one subscriber | Duplicate logs/alerts/recovery | Separate duties and enforce idempotency |
| Not testing failures in the error handler itself | Lost visibility or duplicate alerts | Test error-of-error, add fallbacks |
| Monitoring only ErrorMessage count | Silent poller stops go unnoticed | Health checks, last-successful-poll, backlog |

## 20. ErrorMessage and MessagingException Implementation Checklist

### A. Message Contracts

- [ ] Know payload types at each stage and how Messages are transformed.
- [ ] Have a business key/correlation ID linking processing steps.
- [ ] Understand `failedMessage` and `originalMessage` can be null.
- [ ] Handle `ErrorMessage` payload as `Throwable`, without unsafe casts.
- [ ] Set the `errorChannel` header only from trusted sources.
- [ ] Avoid storing unnecessary credentials, tokens, or sensitive payloads.

### B. Error Paths

- [ ] Distinguish synchronous `DirectChannel`/gateways from pollers/async.
- [ ] Know which endpoints/error strategies actually publish `ErrorMessage`.
- [ ] Global `errorChannel` and dedicated channels have clear owners.
- [ ] Logging/alerting subscribers control duplicate handling.
- [ ] Plan for when the error handler or error channel itself fails.

### C. Recovery and Data

- [ ] Classify transient/permanent/unknown errors on solid criteria.
- [ ] Retries have limits, backoff, idempotency, and final disposition.
- [ ] File/SFTP have filters, file state, and quarantine.
- [ ] HTTP has timeouts, response mapping, and idempotency.
- [ ] JMS/AMQP/Kafka have container-level ack/offset/retry/DLQ/DLT.
- [ ] JDBC has transactions, avoiding partial commits and duplicate replays.
- [ ] Recovery state is persisted durably if needed across restarts.

### D. Testing and Operations

- [ ] Unit tests distinguish `originalMessage` and `failedMessage`.
- [ ] Tests cover missing message context.
- [ ] Tests verify `DirectChannel` throws and poller publishes `ErrorMessage`.
- [ ] Tests cover error handler self-failures.
- [ ] Tests verify side effects, ack/commit, and restarts on critical adapters.
- [ ] Metrics exist per flow/stage/type, retries exhausted, and backlog.
- [ ] Runbooks, owners, and audit trails support safe replay.

## 21. Self-Check Questions

**Question 1. What is the fundamental difference between ErrorMessage and MessagingException?**

**Answer:** `MessagingException` is a `RuntimeException` in Spring Messaging; `ErrorMessage` is a `Message` with a `Throwable` payload, often wrapping a `MessagingException`. Exceptions can be thrown directly without creating an `ErrorMessage`.

**Question 2. Does ErrorMessage have getFailedMessage() directly?**

**Answer:** No. `getFailedMessage()` belongs to `MessagingException`. Retrieve `ErrorMessage.getPayload()`, check whether it is a `MessagingException`, and then call `getFailedMessage()`.

**Question 3. When does ErrorMessage.getOriginalMessage() have a value?**

**Answer:** When the constructor or `ErrorMessageStrategy` was supplied an input message to retain. It is not guaranteed to always exist or point to the very first message of the entire flow.

**Question 4. Can you construct an ErrorMessage from an IOException without using MessagingException?**

**Answer:** Yes. `ErrorMessage` accepts any `Throwable` payload, not strictly `MessagingException`. In that case `failedMessage` cannot be retrieved from the payload unless another mechanism provides context.

**Question 5. Why can failedMessage and originalMessage differ?**

**Answer:** Input may have passed through a transformer before the handler failed. `MessagingException` records the message at the failure point, whereas `ErrorMessageStrategy` may keep the input at the exception-catching point as `originalMessage`.

**Question 6. When a DirectChannel handler throws IllegalStateException, will global errorChannel definitely receive the error?**

**Answer:** No. Synchronous paths usually throw back to the sender. Only when an explicit catch/publish mechanism is present does an `ErrorMessage` reach the channel.

**Question 7. Can the MessageHeaders.ERROR_CHANNEL header replace configuring an error publisher?**

**Answer:** No. It is destination metadata for components supporting header resolution; the header itself does not catch exceptions or create an `ErrorMessage`.

**Question 8. What channel type is global errorChannel usually?**

**Answer:** In typical default configurations, it is a `PublishSubscribeChannel` with a `LoggingHandler`; applications may customize it. Multiple subscribers can receive the same message.

**Question 9. Why must you not log the entire failedMessage unconditionally?**

**Answer:** `failedMessage` can contain files, customer data, tokens, personal info, or very large payloads. Log safe metadata, correlation ID, and error category; only store payloads with appropriate security controls.

**Question 10. Does an ErrorMessage published from a JMS listener prove the broker will redeliver the message?**

**Answer:** No. Redelivery, acknowledgment, and transactions are controlled by the listener/container and broker policy. You must test propagation/rollback and how the error handler treats exceptions.

**Question 11. If Kafka has ErrorMessage, does it already have a dead-letter topic?**

**Answer:** Not yet. A DLT requires dedicated Kafka container/recovery configuration. An `ErrorMessage` is a Spring `Message`, not a Kafka record or topic.

**Question 12. Should every MessageHandlingException be retried?**

**Answer:** No. Examine the cause, stage, and business rules. Validation errors typically require fixing data, infrastructure timeouts may retry if safe, and HTTP timeouts may have already caused side effects requiring idempotency/reconciliation.

**Question 13. Why aren't constructor-based ErrorMessage unit tests sufficient for production?**

**Answer:** They only verify the object model. Production requires verifying error publishers, destinations, polling/async behavior, broker acknowledgments, transactions, retries, and real post-failure data state.

**Question 14. If error.getOriginalMessage() is null and MessagingException.getFailedMessage() is also null, what can you do?**

**Answer:** Use flow/task metadata, logs, exception cause, source correlation, or recovery references. Never fabricate an ungrounded `failedMessage` and replay it.

**Question 15. What outcome proves an error was fully handled?**

**Answer:** Business evidence: data processed successfully, safely stored for retry, quarantined/DLQ'd per policy, or recorded for manual action with an owner. Merely seeing an `ErrorMessage` or a log line is not enough.

## 22. Conclusion and References

### Summary of Core Concepts

**MessagingException** adds **failed message context** to a Java exception. **ErrorMessage** is a **Spring Message with a Throwable payload** for transmitting error information across message channels when publishing is configured.

Three structures to remember:

~~~text
ErrorMessage
    payload: Throwable
        -> may be MessagingException
              -> failedMessage: Message<?> (nullable)
              -> cause: Throwable (nullable)
    originalMessage: Message<?> (nullable)
    headers: MessageHeaders
~~~

When reading errors, identify the **Throwable type**, **message at failure point**, **input retained by strategy**, **selected channel**, and **root cause in the cause chain**. When handling consequences, separate synchronous errors, poller/async behavior, broker acknowledgments, DB transactions, and external side effects.

Good design does not stop at catching exceptions or emitting `ErrorMessage`. It must ensure **message contracts, error classification, idempotency, bounded retries, durable recovery, safe logging, and end-to-end testing**. Across File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC adapters, `ErrorMessage` aids observability and coordination, yet **retry, rollback, ack, quarantine, and recovery must still be designed per integration type**.

### Recommended Official Documentation

- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): distinguishing sync/async exceptions, `errorChannel`, `MessagePublishingErrorHandler`, and `ErrorMessageStrategy`.
- [Spring Framework Javadoc — ErrorMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): payload API, constructors, and `originalMessage`.
- [Spring Framework Javadoc — MessagingException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html): constructors, `getFailedMessage()`, and exception hierarchy.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): exception/reply behavior and gateway error flows.

**Version note:** Examples use standard Spring Messaging/Spring Integration APIs and modern Java. Before applying to a real project, check Javadoc against your active versions of Spring Framework, Spring Integration, and Spring Boot; do not assume every adapter, gateway, or listener publishes errors identically.
