# Identifying the Layer Responsible for Handling or Forwarding Errors in Spring Messaging

When a message fails, the first important question is **at which layer the error occurred and how far the message got**. Spring has many layers participating in the message flow: transport, protocol, channels, data conversion, routing, business handlers, and broker. Each layer has its own observation scope and response capabilities.

There is no single exception handler that automatically handles every error type in every Spring Messaging application. Handling must be placed at the right boundary: business errors in the business handler, routing errors at the messaging layer, STOMP errors in the sub-protocol handler, socket errors at the WebSocket layer, while errors in a Spring Integration flow can be routed through `errorChannel`.

## 1. Viewing the Message Flow to Find the Right Layer

For a Spring Messaging application, the general path can be pictured as follows:

```text
Client / Producer
      |
      v
Transport: TCP / WebSocket
      |
      v
Protocol: STOMP / RSocket / ...
      |
      v
Message decoding, conversion, header mapping, destination routing
      |
      v
MessageChannel / dispatcher
      |
      v
@MessageMapping / MessageHandler
      |
      v
Application service / database / external API
      |
      v
Reply channel / broker / outbound transport
      |
      v
Client / Subscriber
```

The actual flow may differ by transport and protocol. For example, STOMP has inbound, broker, and outbound channels; RSocket uses interaction models and reactive publishers. The diagram above is a division of responsibilities for investigating errors, not a fixed pipeline present in every application.

| Layer | Example errors | Component that should handle first |
| --- | --- | --- |
| Transport | Socket closed, write timeout, WebSocket handshake failure | WebSocket server, TCP client/server, or transport adapter |
| Protocol | Malformed STOMP frame, frame handling error, RSocket setup failure | STOMP sub-protocol handler or RSocket protocol/connection handler |
| Messaging infrastructure | Destination not found, no subscribers, dispatch failure | Destination resolver, channel, or message dispatcher |
| Conversion and binding | Payload cannot be converted to DTO, invalid header/argument | Message converter, argument resolver, or validation boundary |
| Handler and business | Business rule rejects command, service or database throws exception | `@MessageMapping` handler or application service |
| Broker/relay | Broker rejects message, relay loses connection | Broker/relay integration and error-forwarding layer to the client |

Practical rule: **the layer that detects the error is responsible for classifying it and preserving context; the layer that owns business policy decides retry, fallback, or returning an error; the protocol layer is responsible for translating the error into a form the peer understands**.

## 2. Exceptions in Spring Messaging That Help Identify Error Types

The `org.springframework.messaging` package provides the base exception `MessagingException` for messaging-related errors. This exception can retain the offending message via `getFailedMessage()`, along with the root cause in the cause chain.

| Exception | Meaning | Investigation direction |
| --- | --- | --- |
| `MessagingException` | General messaging-related error | Inspect the failed message, cause, and stack trace to find the deepest layer where the error originated |
| `MessageDeliveryException` | Error while transferring or delivering a message | Check channel, subscribers, dispatcher, destination, and consumer state |
| `MessageHandlingException` | Error while a handler is processing a message | Check the `MessageHandler`, controller, or invoked components |
| `MessageConversionException` | Unable to convert message/payload | Check content type, converter, data types, and payload structure |
| `DestinationResolutionException` | Unable to resolve destination | Check destination header, prefix, routes, and broker/controller configuration |
| `MethodArgumentResolutionException` | Unable to resolve a handler method parameter | Check `@Payload`, `@Header`, parameter types, converter, and validation |

Exception types are clues for narrowing down the area, not a substitute for reading the cause chain. A database error may be wrapped in `MessageHandlingException`; an outbound send error may surface as `MessageDeliveryException`. Always inspect `getCause()` or `getMostSpecificCause()` to find the root cause.

Example of reading context from a `MessagingException`: 

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

void logMessagingFailure(MessagingException ex) {
    Message<?> failed = ex.getFailedMessage();

    if (failed != null) {
        Object destination = failed.getHeaders().get("simpDestination");
        Object messageId = failed.getHeaders().getId();
        logger.error("Message failed: id={}, destination={}",
                messageId, destination, ex);
    } else {
        logger.error("Messaging failed before a Message was available", ex);
    }
}
```

This is an illustrative logging snippet; the destination header depends on the protocol. With STOMP, you can use `StompHeaderAccessor` or `SimpMessageHeaderAccessor` to read typed headers. With RSocket, the route is typically mapped to metadata/headers according to the `MetadataExtractor` configuration.

When logging, prioritize message id, destination/route, session or connection id, correlation id, exception type, and root cause. Do not log the entire payload if it contains tokens, personal data, or confidential information.

## 3. Distinguishing Message Delivery Errors from Message Handling Errors

This is a useful distinction when reading stack traces:

- **Delivery failure** occurs when the framework cannot deliver the message to its intended recipient. Check the channel, subscribers, destination, broker, and send timing.
- **Handling failure** occurs after a handler has received the message, but processing fails. Check the controller, service, converter/argument binding, and dependencies called by the handler.

For example: the client sends to `/app/orders.create`, but the destination is not configured to reach the controller. That is a routing or dispatch issue. If `OrderController.create()` has already run and `OrderService` throws `InventoryUnavailableException`, that is an error in the handler/business layer. Both situations may appear as a messaging error on the calling side, yet their recovery strategies are completely different.

With synchronous channels, errors can propagate back to the thread calling `send()`. With asynchronous channels or brokers, the producer may have already finished sending before the consumer processes the message. In that case, the producer cannot catch consumer errors with a regular `try/catch`; asynchronous feedback mechanisms such as an error flow, reply, acknowledgement, broker retry, or the platform's dead-letter policy are needed.

## 4. Handling Errors in STOMP over WebSocket

Spring STOMP uses multiple channels with distinct roles:

| Channel | Direction and role |
| --- | --- |
| `clientInboundChannel` | Messages from the WebSocket client entering the Spring application |
| `brokerChannel` | Messages from server-side code sent to the message broker |
| `clientOutboundChannel` | Messages from the broker/application sent out to the WebSocket client |

Typically, destinations starting with `/app` are routed to `@MessageMapping` methods; `/topic` and `/queue` destinations are handled by the broker. When a controller returns a result, the message is passed through `brokerChannel`, the broker finds subscribers, and sends to `clientOutboundChannel`.

### 4.1. Exceptions from `@MessageMapping`: Using `@MessageExceptionHandler`

When a `@MessageMapping` method throws an exception during message handling, the annotated controller layer is the right place to translate the exception into a business response. Spring supports `@MessageExceptionHandler` with parameter types and return values similar to `@MessageMapping`.

- Place `@MessageExceptionHandler` inside the same `@Controller` to handle errors for that controller.
- Place handlers in a `@ControllerAdvice` class if they need to apply across multiple controllers.
- Return a stable error DTO so the client can handle by error code; do not send stack traces or internal details externally.
- Use `@SendToUser` if the error response is intended only for the sender of the message.

```java
@Controller
public class OrderMessageController {

    private final OrderService orderService;

    public OrderMessageController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.create")
    public OrderAccepted create(@Payload CreateOrder command) {
        return orderService.create(command);
    }

    @MessageExceptionHandler(OrderRejectedException.class)
    @SendToUser("/queue/errors")
    public ClientError handleOrderRejected(OrderRejectedException ex) {
        return new ClientError("ORDER_REJECTED", ex.getSafeMessage());
    }
}
```

The classes `OrderService`, `CreateOrder`, `OrderAccepted`, `OrderRejectedException`, and `ClientError` are application-defined types. This snippet illustrates the handling boundary: business errors are translated into a client-facing notification. Do not return `ex.getMessage()` directly if the message could contain SQL, table names, internal paths, or sensitive data; use a safe message or a standardized error code.

`@MessageExceptionHandler` handles exceptions inside annotated message handlers. It is not a catch-all handler for WebSocket handshake errors, STOMP frame-parsing errors, broker relay errors, or any errors occurring before the controller is called.

### 4.2. STOMP Protocol Errors or Sub-Protocol Message Processing Errors

For errors arising when Spring processes STOMP messages from a client, or when an error message is sent from the server/broker to the client, you can customize `StompSubProtocolErrorHandler` via `StompEndpointRegistry.setErrorHandler(...)`.

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setErrorHandler(new SafeStompErrorHandler());
    }
}

public class SafeStompErrorHandler extends StompSubProtocolErrorHandler {
    // Override handleClientMessageProcessingError(...)
    // and/or handleErrorMessageToClient(...) to build a safe STOMP ERROR frame
    // or return null when the application intentionally suppresses that frame.
}
```

`SafeStompErrorHandler` is an application-custom class; the overrides should build a STOMP message matching the client contract. Two primary extension points:

- `handleClientMessageProcessingError(clientMessage, ex)`: handles errors when processing messages from the client. `clientMessage` may be `null` if the error happened before the message could be parsed.
- `handleErrorMessageToClient(errorMessage)`: handles error messages from the server side before sending to the client, such as relay errors or errors sent back by the broker.

STOMP requires the server to close the connection after sending an `ERROR` frame. If you want to keep the connection open and send notifications to another destination, the handler can return `null` to suppress the `ERROR` frame, and the application can then proactively send a notification through the broker, such as to a user destination. Do this only when the error can be safely represented and the session is still usable.

### 4.3. WebSocket Transport Errors

Errors at the WebSocket layer differ from errors in `@MessageMapping` methods. Examples: frame read/write errors, closed socket, or unhandled exceptions in `WebSocketHandler`. Spring provides `ExceptionWebSocketHandlerDecorator`; in standard WebSocket configurations, this decorator catches unhandled exceptions from `WebSocketHandler` methods and closes the session with status `1011` (server error).

Because the connection may already be broken, do not assume a STOMP error message can be sent to the client. Log with the session id and cause, release resources, and let the client reconnect according to the application's policy.

### 4.4. Broker or Broker Relay Failures

When using an external broker such as RabbitMQ or ActiveMQ, Spring relays messages over TCP to the broker and receives messages from the broker to forward down to clients. If the broker rejects a publish, loses connection, or sends an error message, the error belongs to the broker/relay path. A business controller's `@MessageExceptionHandler` is not the place to cover this error. Use broker/relay monitoring and `StompSubProtocolErrorHandler` to control how error messages are delivered to clients.

## 5. Handling Errors in RSocket

RSocket has the interaction models `Request-Response`, `Request-Stream`, `Channel`, and `Fire-and-Forget`. Either side can act as requester or responder. In Spring, `@MessageMapping` handles requests; `@ConnectMapping` handles connection-level events such as `SETUP` and `METADATA_PUSH`.

- Errors in `@ConnectMapping` while handling a new connection cause the connection to be rejected. This is the connection establishment boundary.
- Errors in a request are handled at the responder/request handler. Methods can return `Mono` or `Flux`; therefore asynchronous errors must be handled within the reactive chain.
- When calling `RSocketRequester`, handle error signals on the `Mono`/`Flux` returned by `retrieveMono`, `retrieveFlux`, or the corresponding API.
- `Fire-and-Forget` only confirms sending the message; completion of `send()` does not confirm the remote handler processed the message. If the business logic needs to know the processing outcome, choose request-response or design a dedicated acknowledgement.

Example of mapping service errors in a reactive handler:

```java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(OrderCommand command) {
        return orderService.create(command)
                .onErrorMap(InventoryUnavailableException.class,
                        ex -> new OrderServiceUnavailableException(
                                "Order service is temporarily unavailable", ex));
    }
}
```

This snippet is an example for a Spring RSocket responder; business types are application-defined. `onErrorMap` preserves the failure nature while translating the exception to a meaningful type at the service boundary. If using `onErrorResume` to return a fallback like `Mono.just(...)`, that response becomes a successful outcome; do so only when the API contract explicitly defines a fallback state.

For reactive errors, a `try/catch` around the call creating a `Mono` normally does not catch exceptions thrown later when the publisher is subscribed. Use `onErrorMap`, `onErrorResume`, or `doOnError` at the right position in the pipeline. `doOnError` is suitable for observation/logging; it does not recover or replace the error.

## 6. Spring Integration Has Its Own errorChannel

Do not confuse Spring Integration mechanisms with `spring-messaging` core. Spring Integration adds an error-handling flow based on message channels:

- Exceptions from an asynchronous task can be wrapped into an `ErrorMessage` and sent to a channel.
- If the original message has an `errorChannel` header, the error is sent to that channel; otherwise, Spring Integration uses the global channel bean named `errorChannel`.
- With `DirectChannel`, the handler runs on the same thread that sent the message, so exceptions can propagate back to the caller. With `ExecutorChannel` or `QueueChannel`, the producer may have already moved on; errors must be handled asynchronously through an error flow.

Example of configuring an error channel in Spring Integration:

```java
@Bean
PublishSubscribeChannel errorChannel() {
    return new PublishSubscribeChannel();
}
```

This configuration belongs to Spring Integration and is only useful when the application's flow actually uses that module's error publishing mechanism. An application using only `MessageChannel`, `MessageHandler`, or STOMP in Spring Framework does not automatically have a global `errorChannel` handling all exceptions.

## 7. Deciding Between Retry, Fallback, or Forwarding the Error

Not every exception should be retried. Choose a policy based on the nature of the error and where the result can be observed:

| Error type | Usually appropriate action | Reason |
| --- | --- | --- |
| Malformed payload, missing field, binding error | Return fixable validation/conversion error; do not auto-retry | Resending the same payload usually fails again |
| Business error such as out of stock or invalid state | Return business error code; client decides next step | Not a transient infrastructure error |
| Timeout or transient network error | Bounded retry with backoff if operation is safe | Depends on whether the service recovers |
| Broker/consumer temporarily unavailable | Use retry/acknowledgement per broker or integration flow capabilities | Producer may no longer hold the original call stack |
| Message has no route/handler | Fix configuration or return clear destination error | Retrying cannot fix a wrong route |
| Unknown error or programming bug | Record full context, alert, and route to operations handling | Infinite retry can overload the system |

When retrying a command with side effects, an idempotency key or duplicate-prevention mechanism is required. A timeout does not prove the operation was not executed: the server may have committed data while the response was lost on the way back. Uncontrolled retries can create duplicate orders or payments.

When forwarding errors to the client, return a stable error contract containing an error code, safe message, and correlation id. Internal logs keep the cause chain, stack trace, and necessary failed message metadata. Do not turn an exception into a success response merely to hide errors from the client.

## 8. Process for Investigating a Message Error

1. **Identify the protocol and transport.** Is the application using STOMP/WebSocket, RSocket, or Spring Integration channels? Did the error occur during connect, frame parsing, routing, handler execution, or sending the response?
2. **Find the last point that ran successfully.** Use logs keyed by connection/session id, message id, destination/route, and correlation id. Check whether the controller was invoked yet.
3. **Read the outermost exception and cause chain.** Note the `MessagingException`, `MessageDeliveryException`, `MessageHandlingException`, or specialized exception type; locate the root cause and failed message.
4. **Determine synchronous vs. asynchronous.** If on the same thread, the caller may receive the exception directly. If across an executor, queue, broker, or reactive publisher, an error flow or asynchronous signal is needed.
5. **Choose the right handler.** STOMP controller business errors use `@MessageExceptionHandler`; STOMP sub-protocol errors use `StompSubProtocolErrorHandler`; WebSocket transport errors are handled at the WebSocket layer; RSocket errors are handled at the reactive request/connection boundary; Spring Integration async flows use `errorChannel`.
6. **Check response capability.** Is the session/connection still open? Does the message have a reply channel or requester waiting for a response? With Fire-and-Forget, the sender has no default application acknowledgement.
7. **Select a recovery policy.** Bounded retry for transient errors and idempotent operations; return business errors for fixable mistakes; route failed messages to the appropriate operational flow if handled asynchronously.
8. **Verify with an intentional failure case.** Confirm the client receives the expected contract, the connection is kept/closed per protocol rules, errors are not swallowed, and no duplicate side effects occur on retry.

## 9. Common Design Mistakes

- Putting all handling into one `@MessageExceptionHandler` and expecting it to also catch frame-parsing, broker, or socket errors.
- Using `catch (Exception)` and returning an empty response, preventing the client from distinguishing success from failure.
- Logging only the exception without storing message id, destination/route, or correlation id, making it impossible to trace errors across services.
- Retrying all errors identically, including validation, authorization, or non-idempotent commands.
- Assuming that sending to a channel or calling `send()` means the consumer processed successfully.
- Using Spring Integration's `errorChannel` as if it were a default global feature of every Spring Messaging application.
- Sending raw stack traces, SQL, or internal details back to the client.

## 10. Key Takeaways

- `MessagingException` is the root of many messaging errors and can hold `failedMessage`.
- `MessageDeliveryException` suggests a message delivery error; `MessageHandlingException` suggests an error inside a handler.
- STOMP: `@MessageExceptionHandler` is for errors from `@MessageMapping`; `StompSubProtocolErrorHandler` is for errors at the sub-protocol boundary and errors sent to the client.
- WebSocket transport has its own exception handling mechanism; sessions may be closed rather than receiving an error message.
- RSocket: distinguish connection errors (`@ConnectMapping`) from request errors (`@MessageMapping`), and handle asynchronous errors inside `Mono`/`Flux`.
- Spring Integration `errorChannel` is the Integration module's error flow, especially important for asynchronous tasks.
- Retry, fallback, and error responses are application policies; choose based on root cause, protocol semantics, and idempotency capabilities.

## References

- [Spring Framework Reference — Flow of Messages (STOMP)](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Annotated Controllers and `@MessageExceptionHandler`](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework API — `MessagingException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessagingException.html)
- [Spring Framework API — `MessageDeliveryException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
- [Spring Framework API — `MessageHandlingException`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHandlingException.html)
- [Spring Framework API — `StompSubProtocolErrorHandler`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Spring Framework API — `StompEndpointRegistry.setErrorHandler`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Spring Framework Reference — WebSockets](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html)