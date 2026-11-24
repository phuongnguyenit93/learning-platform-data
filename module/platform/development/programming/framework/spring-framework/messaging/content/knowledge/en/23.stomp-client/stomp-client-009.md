# Distinguishing Frame Errors, Processing Errors, and Transport Errors

> Scope: Spring Framework STOMP over WebSocket and STOMP.js or Spring WebSocketStompClient clients. This lesson classifies errors by origin, observable symptoms, and handling. A server-side business error is sometimes converted into a STOMP ERROR frame, so distinguish the root cause from the error form received by the client.

## 1. Three layers to distinguish

A STOMP connection running over WebSocket has at least three layers:

1. **Transport**: the network and WebSocket connection between the client and server endpoint. Errors here include DNS, TLS, HTTP handshake, proxies, closed sockets, or lost connections.
2. **STOMP frame/protocol**: frame structure, commands, headers, body, and protocol rules. Errors can stem from malformed frames, missing required headers, incompatible versions, or the broker rejecting a command.
3. **Application processing**: Spring routes valid frames to controllers, converts payloads, validates data, and runs business logic. Errors can result from validation, business permissions, databases, or handler code.

The three layers are related, not synonymous. A business processing error can be translated by the server into a STOMP ERROR frame. Conversely, a dropped WebSocket can prevent the client from receiving an ERROR frame even though the server had an error earlier.

## 2. Frame errors and STOMP protocol errors

STOMP is a frame-based protocol. A frame consists of a command, optional headers, a blank line separating headers from an optional body depending on frame type, and a trailing NULL byte. Example SEND:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":"O-42"}^@
~~~

Common frame/protocol errors:

- Frame lacks a valid command or is missing the blank line separating headers and body.
- Malformed headers, invalid escape sequences, or improper frame termination.
- SEND missing the destination header.
- SUBSCRIBE missing destination or id, or reusing a duplicate subscription id on the same connection.
- Client and server share no common STOMP version.
- Command or header unsupported by the broker.
- Frame exceeds size limits or violates protocol rules.

Distinguish **frame syntax errors** from **broker command rejections**. A frame can be syntactically valid yet still be rejected because the destination does not exist, the account lacks SUBSCRIBE permissions, credentials are invalid, or the broker does not support a requested feature.

### ERROR frame

When a server/broker sends a STOMP ERROR frame, the frame usually has a `message` header giving a short description and a body containing further details:

~~~text
ERROR
message:Subscription denied
content-type:text/plain

The user is not authorized to subscribe to this destination.^@
~~~

Per STOMP 1.2, the server sends an ERROR frame and then closes the connection. Consequently, the client typically observes both the STOMP ERROR callback and a WebSocket close event immediately afterward. Do not look only at the close event and conclude it was a network outage; check whether the client received an ERROR frame right before it.

An ERROR frame indicates the server/broker reported an error at the STOMP layer. It does not guarantee the cause was the parser: authentication, authorization, or server-side message-processing failures can also be surfaced via ERROR frames.

### Symptoms and investigation paths

| Symptom | What to check |
|---|---|
| ERROR with message mentioning missing destination or header | Inspect command, headers, and frame sent by the client. |
| ERROR mentioning version or CONNECT | Inspect accept-version, host/vhost, and supported STOMP versions. |
| ERROR mentioning permissions or authentication | Inspect CONNECT headers, HTTP handshake auth, Principal, and SEND/SUBSCRIBE permissions. |
| ERROR mentioning destination | Inspect `/app`, `/topic`, `/queue` prefixes, destination mappings, and broker ACLs. |
| ERROR after sending a large frame | Inspect WebSocket/STOMP size limits on client, Spring, proxy, and broker. |

## 3. Application processing errors

When a client sends a valid frame to an application destination, Spring can route the message to `@MessageMapping`. Example:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders")
    public OrderResult create(OrderRequest request) {
        if (request.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }

        return orderService.create(request);
    }
}
~~~

If payload conversion fails, validation fails, or the service throws an exception, the error arises during application message processing. This is a processing error, even if the server wraps it into a STOMP-layer ERROR frame to notify the client.

### Handling exceptions with @MessageExceptionHandler

If you want to return business errors in a stable schema that clients can handle, declare `@MessageExceptionHandler` and send the error payload to a dedicated destination:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    public record OrderRequest(String orderId, int quantity) {}
    public record OrderResult(String orderId, String status) {}
    public record ApplicationError(String code, String message) {}

    @MessageMapping("/orders")
    public OrderResult create(OrderRequest request) {
        if (request.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }
        return orderService.create(request);
    }

    @MessageExceptionHandler(InvalidOrderException.class)
    @SendToUser("/queue/errors")
    public ApplicationError handleInvalidOrder(InvalidOrderException ex) {
        return new ApplicationError("INVALID_ORDER", ex.getMessage());
    }
}
~~~

This is an illustrative example; `InvalidOrderException` and `orderService` are application business components. Authenticated clients can subscribe to `/user/queue/errors` to receive structured errors.

`@MessageExceptionHandler` handles exceptions thrown by `@MessageMapping` methods in the corresponding controller. Shared handlers across controllers can be placed in `@ControllerAdvice`. Return only safe error details to clients; log stack traces and internal details on the server.

If an exception goes unhandled at the controller layer, Spring's default STOMP sub-protocol handler may generate an ERROR frame and close the WebSocket session. You can customize client-facing error generation with `StompSubProtocolErrorHandler`. Therefore, whenever you see STOMP ERROR, inspect server logs and the root exception before classifying it as a frame syntax error.

### Common processing errors

- Syntactically valid JSON missing a required business field.
- Enum, date-time, or data types incompatible with the DTO.
- `@MessageMapping` fails because business logic throws an exception.
- User is permitted to connect but unauthorized to perform a specific action.
- Database, cache, or external service unavailable.
- Client-side MESSAGE callback code throws an exception while parsing or rendering the payload.

A JSON parsing error inside a client-side callback is a client processing error. It does not automatically mean the broker sent a STOMP ERROR. Distinguish `JSON.parse` failing in your application from the client receiving a frame with command ERROR from the server.

## 4. Transport errors and WebSocket lifecycle

Transport errors occur at the connection layer beneath STOMP. Examples:

- DNS fails to resolve host or TCP connection is refused.
- Invalid TLS certificate or TLS handshake failure.
- HTTP Upgrade handshake returns 401, 403, 404, or 5xx.
- Reverse proxy, load balancer, or firewall closes the connection.
- Client network changes, laptop sleeps, flaky Wi-Fi, or server restarts.
- Heartbeat timeout indicates the peer is no longer responding within the expected interval.

At the HTTP handshake stage, STOMP CONNECT has not been sent yet, so no STOMP ERROR frame can exist for that connection attempt. Inspect the Network tab to check the WebSocket request, handshake status, TLS, and response headers. After WebSocket opens, transport errors usually surface via WebSocket error/close events or the client's transport callback.

A WebSocket `CloseEvent` includes code and reason, though browsers may not expose full root-cause details. WebSocket error events are also typically sparse. Correlate the close timestamp with server, proxy, broker, and heartbeat logs.

## 5. Identifying the three error types in STOMP.js

With `@stomp/stompjs`, the key callbacks are:

- `onStompError(frame)`: client received a STOMP ERROR frame from server/broker. Inspect `frame.headers.message` and `frame.body`.
- `onWebSocketError(event)`: underlying WebSocket emitted an error event.
- `onWebSocketClose(event)`: WebSocket closed; inspect code, reason, and wasClean if provided by the browser.
- `onHeartbeatLost()`: client did not receive a heartbeat within the expected interval.
- `onUnhandledMessage(message)`: a MESSAGE frame arrived with no matching subscription handler.
- `onUnhandledFrame(frame)`: received a frame not handled as a standard frame by the client.

Client configuration example:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://example.com/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        console.info("STOMP connected");

        client.subscribe("/user/queue/errors", frame => {
            try {
                const error = JSON.parse(frame.body);
                console.error("Application error:", error.code, error.message);
            } catch (exception) {
                console.error("Cannot parse application error payload", exception);
            }
        });
    },

    onStompError: frame => {
        console.error("STOMP ERROR:", frame.headers.message);
        console.error("Broker/server detail:", frame.body);
    },

    onWebSocketError: event => {
        console.error("WebSocket transport error:", event);
    },

    onWebSocketClose: event => {
        console.warn("WebSocket closed:", {
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean
        });
    },

    onHeartbeatLost: () => {
        console.warn("STOMP heartbeat lost");
    }
});

client.activate();
~~~

`onConnect` is invoked again after every successful STOMP connection, so registering subscriptions in this callback helps the client re-subscribe after reconnecting. If subscriptions are registered outside `onConnect`, proactively restore them when a new session is established.

`reconnectDelay` enables automatic reconnection attempts after a connection drops. Choose an appropriate delay and consider exponential backoff with jitter in systems with many clients so all clients do not reconnect simultaneously. Reconnecting only restores the connection; it does not automatically restore application state or guarantee an earlier SEND was processed.

## 6. Identifying errors in Spring WebSocketStompClient

With Spring's Java client, `StompSessionHandler` provides three distinct handling paths:

| Callback | Meaning |
|---|---|
| `handleFrame` | Receives STOMP frames from the server, including ERROR frames. |
| `handleException` | Exception while the client processes a frame, such as payload conversion failure or an exception inside `StompFrameHandler`. |
| `handleTransportError` | Low-level transport errors, such as I/O or connection lost; can also include STOMP encode/decode errors in the client transport layer. |

Example handler focused on recording ERROR frames and transport errors:

~~~java
import java.lang.reflect.Type;

import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class LoggingStompSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        // StompSessionHandlerAdapter uses String for the ERROR frame payload.
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println("STOMP ERROR: " + headers.getFirst("message"));
        System.err.println("Detail: " + payload);
    }

    @Override
    public void handleException(
            StompSession session,
            org.springframework.messaging.simp.stomp.StompCommand command,
            StompHeaders headers,
            byte[] payload,
            Throwable exception) {

        System.err.println("Client frame processing failed: " + exception.getMessage());
    }

    @Override
    public void handleTransportError(StompSession session, Throwable exception) {
        System.err.println("STOMP transport failed: " + exception.getMessage());
    }
}
~~~

The example above is for a handler tracking ERROR frames; in real applications, the payload type for subscription MESSAGEs should declare the proper DTO or be handled by separate `StompFrameHandler` instances. `handleException` is not a replacement callback for broker ERROR frames. Nor is `handleTransportError` the place to handle business errors in server controllers.

## 7. Receipt does not mean business processing succeeded

STOMP can use the `receipt` header for a client to ask the server to send a RECEIPT frame after the corresponding frame has been processed at the protocol layer:

~~~text
SEND
destination:/app/orders
receipt:send-order-42
content-type:application/json

{"orderId":"O-42"}^@
~~~

The server may respond:

~~~text
RECEIPT
receipt-id:send-order-42

^@
~~~

RECEIPT confirms the corresponding frame was processed by the server at the protocol level. It does not prove business logic finished successfully, a database transaction committed, or the final recipient read the message.

If you need to know the business outcome, design a dedicated response with a correlation/request id, such as `orderId` or `requestId`, and return a success/error payload over an application destination. Do not use RECEIPT as a substitute for business results.

## 8. Step-by-step diagnostic procedure

When the client reports "not receiving messages", check in order:

1. **Did WebSocket open?** Check HTTP Upgrade, TLS, proxies, and `CloseEvent`. If the handshake failed, fix transport/auth before STOMP.
2. **Did STOMP CONNECT receive CONNECTED?** If not, inspect ERROR frames, version negotiation, host/vhost, and credentials.
3. **Were client SEND/SUBSCRIBE frames valid?** Check command, destination, id, content-type, body, and subscription id.
4. **Was an ERROR frame received?** Record the `message` header, body, timestamp, and preceding command. Check broker logs and server logs.
5. **Was the controller invoked?** If not, check application prefix, mappings, converters, channel interceptors, and access permissions.
6. **Did the handler throw an exception?** Check validation, services, database, and `@MessageExceptionHandler`.
7. **Did the server emit MESSAGE?** Check outbound destination, broker, and subscriptions.
8. **Did the client receive MESSAGE but fail to process it?** Check subscription callback, JSON parsing, payload type, and UI code.
9. **Did heartbeats or the connection drop midway?** Correlate logs on both ends, proxy timeouts, and the reconnect timeline.

In development environments, enable selective debug logging for the STOMP client and Spring WebSocket/Messaging to see frame directions and destinations. Raw frame logs may contain payloads, tokens, or personal data; do not enable or store them in production without sensitive-data masking.

## 9. Quick classification table

| Error category | Primary symptoms | First place to check |
|---|---|---|
| Frame/protocol | STOMP ERROR, invalid command/header, rejected version or destination | Inspect raw STOMP frame, broker response, and STOMP version. |
| Application processing | Handler exception, validation, payload conversion, or business error | Inspect server logs, DTO/converter, controller, and service; return structured error if appropriate. |
| Client processing | MESSAGE received but callback or JSON parsing failed | Inspect subscription handler, payload type, and client code. |
| Transport | Handshake failure, WebSocket close/error, I/O exception, heartbeat lost | Inspect network, TLS, proxy, server availability, and reconnect. |

Multiple events can occur back-to-back. For example, a server handler throws an exception, Spring emits an ERROR frame, and then closes the WebSocket. The client sees `onStompError` followed by `onWebSocketClose`. The root cause is the server processing error; the ERROR frame is the STOMP-layer notification; WebSocket close is the transport-layer consequence.

## 10. Safe retries and recovery

Not every error should be retried the same way:

- **Frame/protocol error**: fix the frame, destination, version, or permissions. Retrying the exact same invalid frame usually just repeats the error.
- **Application validation/business error**: fix the input data or show the error to the user. Do not auto-retry when data is invalid.
- **Application transient error**: may retry if business rules permit, but require an idempotency key or request id to avoid creating duplicate transactions.
- **Transport error**: reconnect with backoff; after CONNECTED, re-register subscriptions and synchronize necessary state.
- **Uncertain SEND outcome due to connection loss**: the server may have received and processed the frame before the connection dropped. Do not blindly resend non-idempotent commands; query the request id or business state first.

If business-level single execution is required, design idempotency at the application layer and persist processing state. Neither WebSocket reconnect nor STOMP receipts natively provide exactly-once business processing.

## 11. Self-check

1. The client receives an ERROR frame with header `message: Access denied`, and then the WebSocket closes. What should you check first?
2. The client receives no ERROR frame, yet `onWebSocketClose` reports an abnormal close code. Which layer should you investigate?
3. A server `@MessageMapping` throws `InvalidOrderException`, and `@MessageExceptionHandler` returns JSON to `/user/queue/errors`. Which category of handling is this?
4. Spring's Java STOMP client fails to convert a MESSAGE body into a DTO. Which callback receives the exception?
5. Does a RECEIPT after SEND prove the order was committed in the database?
6. A STOMP.js callback receives a MESSAGE, but `JSON.parse` throws an exception. Is this a broker ERROR or a client processing error?

Answers:

1. Check CONNECT/SUBSCRIBE/SEND permissions, Principal, destination ACLs, and the ERROR frame body; this is the broker/server rejecting at the STOMP layer.
2. Investigate transport: network, TLS, proxy, server restarts, and heartbeats; also check whether an ERROR frame arrived right before closing.
3. An application processing error mapped to an application error payload.
4. `StompSessionHandler.handleException`.
5. No. RECEIPT confirms the frame was processed at the protocol layer, not that a business transaction committed.
6. A client-side processing error inside the callback, not automatically a STOMP ERROR from the broker.

## References

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html): frame structure, required headers, ERROR, RECEIPT, connection, and connection-closing rules.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping` and `@MessageExceptionHandler`.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): `StompSessionHandler`, `handleFrame`, `handleException`, `handleTransportError`, receipts, and message size limits.
- [Spring Framework — StompSessionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandler.html): callbacks for ERROR frames, frame-processing exceptions, and transport errors.
- [Spring Framework — StompSubProtocolHandler source](https://github.com/spring-projects/spring-framework/blob/main/spring-websocket/src/main/java/org/springframework/web/socket/messaging/StompSubProtocolHandler.java): server-side default error-handling and ERROR frame emission behavior.
- [STOMP.js Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): `onStompError`, `onWebSocketError`, `onWebSocketClose`, heartbeats, and reconnect.
