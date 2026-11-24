# Classifying Connection, Protocol, Conversion, and Business Errors

## Objectives

A messaging system can accept a connection successfully yet still fail when reading a frame, decoding a payload, locating a handler, or executing business logic. Each error appears at a different stage and requires a different recovery approach. If you lump everything into a single `catch Exception` branch and retry, the application may infinitely loop over a malformed message, create duplicate transactions, or hide the real root cause.

This lesson establishes a classification of errors into four groups: **connection, protocol, conversion, and business**. At the same time, it explains error types in Spring Messaging, appropriate handling locations, retry policies, idempotency, and testing approaches.

After this lesson, you will be able to:

- Identify whether an error occurs at the transport, protocol, conversion, or business layer.
- Distinguish transient errors from permanent errors and errors with an unknown processing outcome.
- Understand the roles of MessagingException, MessageDeliveryException, MessageHandlingException, MessageConversionException, and ErrorMessage.
- Use @MessageExceptionHandler to map exceptions from a message handler into an application response.
- Design bounded retries, backoff, idempotency, and dead-letter handling.
- Log, measure, and test errors without exposing sensitive data.

## 1. Looking at Errors Along a Message's Path

Spring Messaging provides the Message, MessageChannel, and MessageHandler abstractions along with protocol-specific adapters. A message typically passes through several layers before completion:

~~~text
Producer / Client
       |
       v
Transport: TCP, WebSocket, ...
       |
       v
Protocol: RSocket, STOMP, ...
       |
       v
Spring Message: headers + payload
       |
       v
Conversion / argument binding / validation
       |
       v
Destination or route matching
       |
       v
Message handler
       |
       v
Business service / database / external API
       |
       v
Response, broker delivery or acknowledgement
~~~

An error should be classified by **origin point** and **processing state at the time of the error**. These two questions help determine whether resending is possible.

| Error group | Stage | Typical examples |
|---|---|---|
| Connection | Establishing or maintaining the transport/session | Connection refused, socket reset, TLS handshake failure, connect timeout |
| Protocol | Reading and validating a frame or protocol message | Malformed frame, incompatible version, rejected SETUP, invalid route or command |
| Conversion | Converting payload/headers into the data types required by the handler | Invalid JSON, mismatched MIME type, unable to convert String to enum, missing required header |
| Business | Executing application rules after the message has been understood | Order already canceled, insufficient balance, state transition not allowed |
| Delivery and handling | Moving a message across channels, handlers, brokers, and clients | Handler error, overloaded consumer, wait timeout, unacknowledged send outcome |

The first four groups are the focus of this lesson. The delivery and handling group is cross-cutting: it can appear alongside connection, protocol, or business errors. For example, a handler throwing an exception is a handling error; the underlying root cause may be a database timeout or a violated business rule.

An important principle: **errors that occur before the handler runs cannot be fixed by adding a try/catch inside the handler body**. They must be handled at the exact layer where the error originated.

## 2. Connection Errors (connection / transport)

### 2.1. Nature

Connection errors occur when the two endpoints have not established or can no longer maintain the communication channel. Common causes include:

- Wrong host or port, unresolvable DNS, or server not started.
- Firewall, proxy, or load balancer blocking the connection.
- TCP refused, reset, or closed unexpectedly.
- Invalid TLS certificate, hostname mismatch, or incompatible TLS configuration between the two sides.
- WebSocket handshake failure or closed session.
- Keepalive/heartbeat detecting that the peer is no longer responding.
- Server overloaded, out of connection slots, or out of network resources.

At this layer, the application has usually not yet received a complete message to dispatch to @MessageMapping. Therefore, errors may appear as transport, Reactor, or client library exceptions; there is no single Spring Messaging exception type representing all connection errors.

### 2.2. Distinguishing Transport Connection from Protocol Setup

Opening a TCP socket does not mean the messaging session is ready.

With RSocket, the client first opens a transport such as TCP or WebSocket, and then sends a SETUP frame to negotiate connection parameters. The server may reject SETUP. In this case, the transport has been opened, but the RSocket session was not established successfully.

With STOMP over WebSocket, the WebSocket handshake and STOMP CONNECT are two separate stages. WebSocket may connect successfully, yet the STOMP session still fails due to authentication, version, or CONNECT headers.

Distinguishing these two stages helps locate the right logs and the right configuration to fix:

| Observation | What to check |
|---|---|
| Unable to open socket | DNS, port, firewall, server process, TLS, and proxy |
| WebSocket handshake rejected | HTTP endpoint, origin, authentication, TLS, and upgrade configuration |
| TCP/WebSocket opened but RSocket SETUP failed | MIME types, SETUP parameters, authentication, and compatibility |
| WebSocket opened but STOMP CONNECT failed | STOMP version, login/token, heartbeat, and CONNECT headers |
| Running session disconnected | Network stability, keepalive, server restart, idle timeout, and resource limits |

### 2.3. Recovery

Connection errors can be transient, though not always. A connection reset may recover once the network stabilizes; a wrong certificate or wrong port will continue failing until the configuration is fixed.

An appropriate policy typically includes:

1. Use finite connect timeouts and request timeouts so resources are not held indefinitely.
2. Reconnect with exponential backoff and jitter.
3. Bound the number of attempts and total recovery time.
4. Use a circuit breaker or concurrency limit if a dependency is persistently unavailable.
5. Resend a command only when idempotency is in place or you are certain the previous request was not processed.
6. Monitor open connections, reconnect counts, session setup duration, and disconnect rates.

RSocket has a protocol-level session resumption mechanism to handle connection loss. This mechanism must be configured and maintain appropriate state; you should not assume every RSocket client, transport, or Spring configuration resumes automatically. When using STOMP/WebSocket, reconnect and resubscribe also need to be designed on the client; after reconnecting, previous subscriptions may need to be recreated.

### 2.4. Request Outcome May Be Unknown

Suppose a client sends an order creation command. The server writes the order to the database, but the connection drops before the response reaches the client. The client only sees a timeout or disconnect, yet the order may already have been created.

This is an **unknown outcome**, which is not synonymous with the server not having executed the request. Resending immediately may create a second order. Use a messageId or idempotency key so the server recognizes duplicate requests, then returns the stored result or rejects the duplicate according to the application contract.

## 3. Protocol Errors (protocol)

### 3.1. Nature

Protocol errors occur when the two sides cannot understand or do not accept the structure or rules of messages on the wire. For example:

- A frame is missing required parts, has an invalid length, or has a malformed structure.
- Client and server do not agree on the protocol version.
- Invalid STOMP command or header.
- RSocket SETUP rejected or a frame inconsistent with the session state.
- Metadata or MIME type not supported under the protocol contract.
- Destination/route does not exist or is not permitted by routing rules.
- Client uses an interaction model or frame type unsupported by the peer.

Not every route error is a protocol error. If the frame is valid but no handler matches the route, it may be an application routing error. If the frame is malformed or violates the protocol, the error belongs to the protocol layer. Rely on the error location and the adapter's response type to tell them apart.

### 3.2. Characteristics of Protocol Errors

Protocol errors usually do not go away on their own when resending the exact same frame. They typically resolve only when one side fixes its configuration or data:

- Version mismatch requires aligning versions or implementing backward compatibility.
- Malformed frames require fixing the producer/client.
- Unsupported MIME type requires adding a codec or updating the contract.
- Rejected SETUP requires fixing parameters, authentication, or policy.
- Wrong destination requires fixing the route or mapping configuration.

With RSocket, errors are transmitted through the protocol's ERROR mechanism; the error code and error scope indicate whether the issue pertains to a request or a connection. With STOMP, errors at the sub-protocol layer may be represented by a STOMP ERROR frame or result in closing the session depending on the situation and adapter.

Spring WebSocket provides **StompSubProtocolErrorHandler** to customize error handling at the STOMP sub-protocol layer. This is the adapter's protocol handling point, distinct from @MessageExceptionHandler in a controller. Do not use a business handler to handle malformed frames when the controller has not even been invoked.

### 3.3. Recovery

- Log the protocol, version, command/frame type, and session state at the time of the error.
- Verify the contract between producer and consumer: destination, required headers, MIME type, metadata, and version.
- Close or discard sessions that are no longer in a valid state if required by the protocol.
- Update clients/servers according to a backward-compatibility strategy.
- Do not infinitely retry a malformed frame or a misconfiguration.
- If multiple versions must be supported, test compatibility using a client/server matrix rather than checking only the two latest versions.

Note: authentication errors during SETUP or STOMP CONNECT occur at the session establishment stage. Even though the message may appear as a protocol rejection, the root cause may still be an expired credential or a policy denial. Classify by both the originating layer and the cause so the responsible team fixes the right place.

## 4. Conversion Errors (conversion / binding)

### 4.1. Nature

Conversion errors occur when a message has reached the Spring layer, but its payload or headers cannot be converted into the data types required by the handler.

Examples:

- Client sends JSON with a missing brace or invalid value.
- JSON sends the quantity field as a string while the DTO expects a number.
- Client sends a MIME type different from the codecs supported by the server.
- An enum or date has a format that differs from the contract.
- A required header such as tenantId is missing.
- A header value is present but cannot be converted to the parameter type.
- The payload decodes successfully but fails validation.

Spring Messaging provides helpful exceptions to identify this error group:

- **MessageConversionException**: converting the payload/message failed.
- **MethodArgumentResolutionException**: Spring cannot resolve or bind a parameter of the message handler.
- **MethodArgumentNotValidException**: data fails parameter validation when validation is enabled.
- **MessageHandlingException**: an error raised during message handling; it may wrap a deeper cause.

These exception types aid quick classification, but do not replace reading the cause chain. An exception may be wrapped in multiple layers before reaching logs or the caller.

### 4.2. Distinguishing Conversion from Business Validation

These two error types are often confused:

| Case | Classification |
|---|---|
| JSON cannot be parsed | Conversion |
| quantity is the string "many" while the DTO requires int | Conversion or type binding |
| quantity is a negative number but already parsed as int | Validation or business, depending on rules |
| tenantId is missing from a required header | Argument binding |
| tenantId is present, but the sender lacks permission to access that tenant | Authorization/business policy |
| Order is structurally valid but already in a state that disallows cancellation | Business |

Conversion answers the question: "Can the data be represented as the type the handler needs?" Business answers: "The data is valid in type, but is this action allowed or executable under domain rules?"

### 4.3. Recovery

- Check the MIME type/content type and codecs on both sides.
- Use explicit schemas or DTOs, avoiding abrupt field type changes.
- Return input errors with stable error codes and indicate the offending field when possible.
- Run validation before calling business services.
- Do not retry the exact same malformed payload: if the data does not change, the outcome will not change either.
- For broker-based systems, route unprocessable messages to a dead-letter queue or quarantine area according to broker/adapter policy, along with error metadata and protected original message data.
- Retain sample data needed for investigation according to security policy; do not log tokens or sensitive payloads.

If the error stems from an out-of-sync schema between producer and consumer, fix the contract or implement a schema evolution strategy. Do not silently ignore required fields or replace every invalid value with a default, as that can produce wrong business data undetected.

## 5. Business Errors (business / domain)

### 5.1. Nature

Business errors arise after a message has been recognized, decoded, and converted into application objects. The data may be completely valid syntactically, yet the action is disallowed by domain state or policy.

Examples:

- Insufficient balance to complete a payment.
- Order has already been canceled and cannot proceed to shipping.
- User lacks permission to perform the operation.
- Product is out of stock at processing time.
- A request duplicates the current state.
- An invalid state transition according to the state machine.

Distinguish expected business errors from unexpected system errors. "Insufficient balance" may be a normal business outcome; a database connection reset is an infrastructure error. Do not turn every business rejection into a system exception or log it at ERROR level as an operational incident.

### 5.2. Choosing How to Represent Errors

There are two common options:

**Business result with a rejection status**

Use when rejection is a normal outcome that the client needs to handle:

~~~java
public record PaymentResult(
        boolean accepted,
        String code,
        String message) {
}

public PaymentResult authorize(PaymentCommand command) {
    if (!accountHasEnoughBalance(command)) {
        return new PaymentResult(
                false,
                "INSUFFICIENT_BALANCE",
                "The account does not have enough balance");
    }

    return new PaymentResult(true, "APPROVED", "Payment approved");
}
~~~

This is an illustrative business method assuming the account-checking helpers are already implemented. The client reads `accepted` and `code` to decide how to display the result or request another action.

**Business exception mapped to a response**

Use when the processing flow uses exceptions for rejection cases and the adapter supports a message exception handler:

~~~java
public record MessagingError(
        String code,
        String message) {
}

@Controller
public class PaymentMessageController {

    @MessageMapping("payments.authorize")
    public Mono<PaymentResult> authorize(
            @Payload PaymentCommand command) {
        return paymentService.authorize(command);
    }

    @MessageExceptionHandler(PaymentRejectedException.class)
    public MessagingError handlePaymentRejected(
            PaymentRejectedException exception) {
        return new MessagingError(
                "PAYMENT_REJECTED",
                "The payment cannot be approved");
    }
}
~~~

This is an example controller structure; PaymentCommand, PaymentResult, PaymentRejectedException, and paymentService are application-specific types/beans. The returned message is intentionally limited to client-safe content. Do not send stack traces, SQL, table names, credentials, or internal details in error responses.

**@MessageExceptionHandler** handles exceptions thrown from @MessageMapping methods within the corresponding controller scope. Shared handlers can be organized using @ControllerAdvice in adapters that support it. This mechanism cannot catch DNS, TLS, socket, frame-parsing, or any errors that occur before the message handler is invoked. How the adapter turns the return value into a concrete response depends on the protocol in use.

### 5.3. Should Business Errors Be Retried?

Deterministic rejections such as insufficient balance, invalid state, or permission denied are normally not retried. Retrying the same command under the same conditions only adds load and repeats the same outcome.

Some state-dependent errors may be transient, such as lock contention or a temporarily unavailable business dependency. In those cases, you must clearly define retry conditions, deadlines, attempt limits, and idempotency. Do not assume every exception from a business service is transient.

## 6. Exceptions and ErrorMessage in Spring Messaging

### 6.1. MessagingException

**MessagingException** is the base class for messaging-related errors in Spring. When a message is associated with the failure, the exception can hold a reference to the failed message via getFailedMessage().

Notable subclasses include:

| Exception | Meaning |
|---|---|
| MessagingException | General messaging-related error |
| MessageDeliveryException | Error while delivering a message |
| MessageHandlingException | Error while handling a message |
| MessageConversionException | Failed to convert message/payload |
| MethodArgumentResolutionException | Failed to resolve a handler parameter |
| DestinationResolutionException | Failed to resolve a destination |

Do not classify based solely on exception name. For instance, MessageHandlingException may wrap a database timeout, a business error, or a bug in the handler. Always inspect the cause, failed message, and execution stage.

### 6.2. ErrorMessage

**ErrorMessage** in the org.springframework.messaging.support package is a GenericMessage with a Throwable payload. The payload is often a MessagingException; when possible, it holds failedMessage. ErrorMessage can also hold originalMessage to compare the message at the time the error was created with the message as transformed prior to failure.

This is useful in a pipeline with an error-handling flow: the system can route the exception and related message to an error-handling component to record it or place it in an investigation queue.

However, ErrorMessage by itself does not create a global error channel for all transports. How ErrorMessage is created, routed, and consumed depends on the underlying messaging infrastructure. Spring Integration has its own error channel model; do not confuse Spring Integration features with the core contract of Spring Framework Messaging.

## 7. Choosing a Recovery Strategy by Error Type

The following table is a starting point for building a policy. In practice, combine the error type with whether the command can be safely repeated and the delivery state.

| Error type | Possibly transient? | Primary action | Retry same message? |
|---|---|---|---|
| Connection | Yes, e.g., socket reset or server restart | Reconnect with backoff, check health and session | Only if the request is safely repeatable or known not to have been processed |
| Protocol | Usually not with the same frame/config | Fix version, frame, route, metadata, or configuration | Do not retry as-is |
| Conversion | Usually not with the same payload/schema | Fix codec/schema/data; quarantine or dead-letter | Do not retry as-is |
| Business | Usually a deterministic rejection; occasionally state-dependent | Return domain error with a stable code or wait for state change | Only when an explicit transient rule applies |
| Delivery/timeout | Possibly; outcome may be unknown | Check status, deduplicate, and verify delivery | Only with idempotency or a status-verification mechanism |

### 7.1. Exponential Backoff and Jitter

When many clients retry immediately after a server disconnect, all of them may reconnect at once and create a massive load spike. Exponential backoff increases the wait interval with the attempt number; jitter adds random variation to spread out retry attempts.

A policy should specify:

- Maximum number of retries.
- Initial wait time and maximum cap.
- Jitter.
- Total request deadline.
- Exception categories allowed to retry.
- Immediate stop condition when an error is permanent.
- Maximum retries at each layer to avoid stacked retries.

Do not let the client retry 5 times, the gateway retry 5 times, and the broker retry another 5 times without a shared budget. A single request could be multiplied into a huge number of executions.

### 7.2. Filtered Retry Example with Reactor

RSocketRequester returns reactive types such as Mono or Flux. Reactor provides retryWhen to retry according to a policy. The following example retries only when the application's classifier identifies the error as a transient transport-layer failure:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<OrderResult> response = requester
        .route("orders.create")
        .data(command)
        .retrieveMono(OrderResult.class)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2))
                        .filter(this::isKnownTransientTransportFailure));
~~~

This snippet sits inside a bean/service that already has `requester`, `command`, and the `isKnownTransientTransportFailure` method. The classifier must inspect the entire cause chain because transport exceptions may be wrapped by higher-level layers. It should only match errors already identified as recoverable; do not return true for every RuntimeException or every MessagingException.

The retry operator resubscribes to the publisher. That alone does not prove the previous request never reached the server, nor does it guarantee a new connection will always be created. Connection lifecycle, reconnect, and session resumption depend on client, connector, and transport configuration. For commands with side effects, add idempotency before enabling retry.

### 7.3. Timeout Does Not Imply Rollback

Timeouts can happen at several places:

- Connect timeout: unable to establish transport/session within the allowed time.
- Request timeout: no response received within the deadline.
- Processing timeout: handler or dependency took too long to execute.
- Idle timeout: session had no activity for a period of time.
- Broker/consumer timeout: message not acknowledged or consumer unresponsive.

When the client times out, the server may already have completed the business operation. Canceling a subscription or closing a connection does not automatically roll back a committed transaction. Therefore, timeouts must be paired with an idempotency key, processing state, and the ability to query the outcome when the client does not know whether the request succeeded.

## 8. Idempotency, Duplicates, and Dead-Letter Handling

### 8.1. Why Is Idempotency Needed?

In distributed systems, a message can be resent when the producer does not receive an acknowledgement, the consumer restarts, or the broker redelivers after a timeout. This behavior can happen depending on the delivery semantics of the broker and adapter.

If a handler performs a non-idempotent operation, such as debiting funds or creating an order, duplicate processing can cause duplicate side effects.

A common design pattern:

1. The producer generates a unique idempotency key for a business intent.
2. The consumer checks the key in a store with a unique constraint.
3. If the key is already completed, return the stored result.
4. If not present, execute the business logic and store the result along with the processing status in an appropriate transaction.
5. If an error occurs, record the processing status so a subsequent delivery does not create duplicate side effects.

Do not rely solely on an in-memory cache because a cache can be lost on application restart or when a message is processed by a different instance.

### 8.2. Retry Queues and Dead-Letter Queues

With brokers that support them, messages needing retry can be separated from unprocessable messages:

- Retry queue/topic: the message waits for a period before being reprocessed.
- Dead-letter queue (DLQ): messages that have exceeded the attempt limit or are determined to be automatically unprocessable.
- Quarantine: a storage area for messages requiring manual investigation or data repair before replay.

Spring Framework Messaging provides the Message and exception abstractions, but does not enforce a single DLQ, retry queue, or acknowledgement mechanism across all transports. Those capabilities belong to specific brokers and adapters, such as Spring for Apache Kafka, Spring AMQP, or Spring Integration.

When sending a message to a DLQ, store messageId, correlationId, destination/route, error type, attempt count, timestamp, and schema version. The original payload may contain sensitive data; restrict access permissions and retention duration.

### 8.3. Distinguishing Send Success from Processing Success

A send call accepted by a local MessageChannel does not by itself prove the remote consumer completed the business operation. Similarly, a broker receipt or protocol acknowledgement may confirm a delivery stage without guaranteeing that the business transaction has committed.

If the client needs to know the business operation completed, design a response, receipt, or status queryable by idempotency key. With RSocket Fire-and-Forget, the client does not receive a business response like Request-Response; choose the appropriate interaction model if result confirmation is required.

## 9. Observing and Recording Errors

A useful error log needs enough information to reconstruct the processing flow, without unconditionally logging the entire payload.

Fields to consider:

- errorCategory: CONNECTION, PROTOCOL, CONVERSION, BUSINESS, or DELIVERY.
- exceptionClass and rootCause.
- messageId and correlationId.
- destination or RSocket route / STOMP destination.
- sessionId or connectionId if provided by the adapter.
- protocol and protocolVersion.
- retryAttempt, maxAttempts, and wait duration.
- processingStage and elapsedTime.
- deliveryState if known: not received, received, processed, acknowledged, or unknown.

Use low-cardinality metrics: error counts by category, reconnect rates, timeouts, conversion failures, business rejections, retry exhaustion, and DLQ counts. Do not use unbounded values like messageId, userId, or sessionId as metric labels.

Distributed tracing helps connect producer, gateway, broker, and consumer. Propagate correlationId across the message flow, but do not treat correlationId as authentication information.

Do not log access tokens, session cookies, passwords, payment data, or personal payloads. If payloads must be retained for investigation, enforce clear masking, access control, and retention policies.

## 10. Testing Errors and Recovery

A messaging test that only exercises the happy path is insufficient. Separate tests should cover each layer:

| Scenario | What to verify |
|---|---|
| Server not listening on port | Client receives a connection error; retry is bounded and logged with the right category |
| Socket disconnected mid-request | Client receives an uncertain status; command does not produce duplicate side effects on retry |
| RSocket SETUP or STOMP CONNECT rejected | Error is classified as setup/protocol/authentication according to cause |
| Malformed protocol frame or header | Business handler is not invoked; malformed frame is not retried infinitely |
| Invalid JSON or unsupported MIME type | Conversion failure is recorded; message is handled under reject/quarantine policy |
| Missing required header or wrong type | Argument binding fails clearly; business service is not called |
| Business rule rejection | Client receives a stable business error code; no automatic retry |
| Database timeout inside handler | Root cause is preserved; retry only when operation and transaction are safe |
| Consumer processes duplicate messageId | Side effect occurs only once per idempotency contract |
| Response slower than request deadline | Timeout does not cause the client to falsely conclude the business work definitely never ran |
| Stream canceled or demand lost | Resources are released and cancellation/backpressure behavior matches the contract |

You can test with mock servers, local test transports, broker test containers, or fault injection. Verify logs/metrics, client responses, service invocation counts, and committed data. Do not merely assert that an exception was thrown.

## 11. Practical Diagnostic Workflow

When encountering a messaging error, follow this sequence:

1. **Did the message reach the transport?** Check DNS, socket, TLS, handshake, and session.
2. **Did the protocol accept the message?** Check frame, version, command, route/destination, SETUP/CONNECT, and protocol error code.
3. **Did Spring construct the Message and bind parameters?** Check converter, MIME type, headers, DTO, validation, and argument resolver.
4. **Was the handler invoked?** If not, look for routing or binding errors. If yes, check the exception and root cause inside the service.
5. **Did the business operation commit?** Check transactions, messageId, idempotency record, and queryable results.
6. **What acknowledgement did the client or broker receive?** Distinguish local send, broker receipt, protocol response, and business completion.
7. **Should it be retried?** Decide only after knowing whether the error is transient/permanent and the state of side effects.

This workflow avoids fixing the wrong layer. For example, if JSON parsing fails before the handler runs, adding retries to the business service will not solve it. If the client times out after the database has committed, retrying without idempotency can cause duplicate transactions.

## 12. Key Takeaways

- **Connection error** means the transport or session could not be established/maintained. Recover with bounded reconnects; check request status before resending.
- **Protocol error** means the two sides do not agree on frame interpretation or protocol rules. Fix the contract, version, or configuration; do not retry as-is.
- **Conversion error** means payload/headers could not be bound into required data types. Fix the codec/schema/data; permanent bad messages should be rejected or quarantined.
- **Business error** means the request was understood but the domain does not permit the action. Return a business result with a stable code or map the exception to a safe response.
- **MessagingException** is the messaging error abstraction; MessageDeliveryException, MessageHandlingException, and specialized exceptions help pinpoint the stage, though you must read the root cause.
- **ErrorMessage** carries a Throwable alongside the related message when an error-handling flow uses it; it does not create a global error channel by itself.
- **Retry requires idempotency** because a timeout or disconnect does not prove side effects did not happen.
- **Spring Messaging does not define a universal retry/DLQ policy**; delivery guarantees and acknowledgement mechanisms depend on the transport, broker, and adapter.

Classifying errors properly helps pick the right handling point, reduce wasteful retries, avoid duplicate processing, and preserve the evidence needed to investigate incidents.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Annotated Controllers and @MessageExceptionHandler](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [MessagingException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessagingException.html)
- [MessageDeliveryException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
- [MessageHandlingException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHandlingException.html)
- [MessageConversionException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html)
- [ErrorMessage — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
- [MessageExceptionHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html)
- [StompSubProtocolErrorHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
