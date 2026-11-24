# StompSession, StompHeaders, and Sending Messages

In Spring Framework, a Java STOMP client uses WebSocketStompClient to establish a WebSocket connection and perform the STOMP handshake. After the server sends the CONNECTED frame, the client works with StompSession. This object provides STOMP-layer operations such as sending SEND, registering SUBSCRIBE, acknowledging with ACK, and disconnecting.

StompHeaders describes the headers of each STOMP frame. They specify destination, content type, receipt, acknowledgement mode, and application-defined metadata. When sending a Java payload, the client's message converter converts the object into wire-appropriate bytes/string.

Three outcomes must be distinguished: the send call was executed by the client, the broker confirmed the frame with RECEIPT, and the receiving application completed business processing. These are distinct milestones.

## 1. Position of the Java STOMP client in the communication flow

A Java client typically includes these components:

- **WebSocketStompClient** manages the WebSocket connection and client-side STOMP layer.
- **StompSessionHandler** receives session lifecycle events, error frames, and transport errors.
- **StompSession** represents a connected STOMP session; the client uses it to send messages, subscribe, and disconnect.
- **StompHeaders** holds headers for CONNECT, SEND, SUBSCRIBE, ACK, or related frames.
- **MessageConverter** converts payloads between Java objects and wire message content.
- **StompFrameHandler** declares the expected payload type and handles each received MESSAGE frame.

Connection and message-sending flow:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Client as WebSocketStompClient
    participant Server as Spring STOMP server
    participant Broker as Message broker

    App->>Client: connectAsync(url, handler)
    Client->>Server: WebSocket handshake
    Client->>Server: STOMP CONNECT
    Server-->>Client: STOMP CONNECTED
    Client-->>App: afterConnected(StompSession)
    App->>Client: session.subscribe(...)
    Client->>Server: SUBSCRIBE
    App->>Client: session.send(...)
    Client->>Server: SEND + headers + payload
    Server->>Broker: Route application/broker message
    Broker-->>Server: MESSAGE when matching subscription exists
    Server-->>Client: STOMP MESSAGE
    Client-->>App: StompFrameHandler.handleFrame(...)
~~~

StompSession is only ready after the STOMP handshake completes. Having an open WebSocket connection does not mean the client has received CONNECTED or already has a usable STOMP session.

## 2. Creating WebSocketStompClient

Spring provides WebSocketStompClient to combine a WebSocket client implementation with a STOMP protocol handler. The example below uses StandardWebSocketClient and a Jackson converter to send and receive JSON.

~~~java
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public final class StompClientFactory {

    private StompClientFactory() {
    }

    public static WebSocketStompClient create() {
        WebSocketStompClient client =
            new WebSocketStompClient(new StandardWebSocketClient());

        client.setMessageConverter(new MappingJackson2MessageConverter());

        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        scheduler.initialize();

        client.setTaskScheduler(scheduler);
        client.setDefaultHeartbeat(new long[] {10_000, 10_000});

        return client;
    }
}
~~~

The scheduler is used to run heartbeat tasks when heartbeats are configured. In a Spring application, manage the scheduler as a bean or via application lifecycle so it shuts down cleanly. The example uses a dedicated scheduler to clarify its role; do not create a new thread pool per message.

StandardWebSocketClient requires a Jakarta WebSocket-compatible implementation on the classpath. In other environments, a corresponding WebSocket client implementation can be used as long as it satisfies the API Spring expects.

The message converter determines how payloads are serialized and deserialized:

- MappingJackson2MessageConverter: converts Java objects and JSON.
- StringMessageConverter: converts text content.
- ByteArrayMessageConverter: converts byte[] payloads.

Both communicating sides must agree on payload format and content type. If the server sends JSON while the client declares String or an incompatible DTO, conversion or type casting may fail.

## 3. Connecting and obtaining StompSession

connectAsync connects asynchronously and returns a CompletableFuture<StompSession>. The afterConnected callback is invoked after the client receives STOMP CONNECTED.

~~~java
import java.lang.reflect.Type;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.socket.messaging.WebSocketStompClient;

public class OrderStompClient {

    private final WebSocketStompClient stompClient;

    public OrderStompClient(WebSocketStompClient stompClient) {
        this.stompClient = stompClient;
    }

    public CompletableFuture<StompSession> connect() {
        return stompClient.connectAsync(
            "ws://localhost:8080/ws",
            new StompSessionHandlerAdapter() {

                @Override
                public void afterConnected(
                        StompSession session,
                        StompHeaders connectedHeaders) {

                    System.out.println(
                        "STOMP connected, sessionId=" + session.getSessionId()
                    );

                    subscribeToOrderEvents(session);
                    sendCreateOrder(session);
                }

                @Override
                public void handleTransportError(
                        StompSession session,
                        Throwable exception) {

                    System.err.println(
                        "STOMP transport error: " + exception.getMessage()
                    );
                }
            }
        );
    }

    private void subscribeToOrderEvents(StompSession session) {
        session.subscribe(
            "/topic/order-events",
            new StompFrameHandler() {
                @Override
                public Type getPayloadType(StompHeaders headers) {
                    return OrderEvent.class;
                }

                @Override
                public void handleFrame(
                        StompHeaders headers,
                        Object payload) {

                    OrderEvent event = (OrderEvent) payload;
                    System.out.println("Received event: " + event);
                }
            }
        );
    }

    private void sendCreateOrder(StompSession session) {
        StompHeaders headers = new StompHeaders();
        headers.setDestination("/app/orders");
        headers.setContentType(MimeTypeUtils.APPLICATION_JSON);
        headers.set("x-correlation-id", UUID.randomUUID().toString());

        session.send(headers, new CreateOrder("ORD-100"));
    }

    public record CreateOrder(String orderId) {}

    public record OrderEvent(String eventId, String status) {}
}
~~~

In the example:

1. The client opens a connection to endpoint /ws.
2. The server completes the STOMP handshake and returns CONNECTED.
3. Spring invokes afterConnected with StompSession.
4. The client subscribes to /topic/order-events.
5. The client sends a command to /app/orders with a JSON payload and correlation ID.
6. Matching MESSAGE frames are delivered to StompFrameHandler.

Only send commands after the session is connected. Do not call session.send while the CompletableFuture is incomplete or before the afterConnected callback. If the handshake fails, the future may complete exceptionally; handle that error at the connect call site.

## 4. Key StompSession operations

StompSession is the API for working with the STOMP protocol after connecting. Commonly used methods:

| Method | Purpose |
|---|---|
| getSessionId() | Get the ID of the STOMP session |
| isConnected() | Check the connection state tracked by the client |
| send(destination, payload) | Send a SEND frame to a destination |
| send(headers, payload) | Send SEND with custom headers |
| subscribe(destination, handler) | Subscribe to receive MESSAGEs from a destination |
| subscribe(headers, handler) | Subscribe with custom SUBSCRIBE headers |
| unsubscribe(id) or unsubscribe(headers) | Cancel a subscription |
| acknowledge(messageId, consumed) | Send ACK/NACK according to supported acknowledgement mode |
| disconnect() | Proactively close the STOMP session |

send and subscribe are asynchronous operations along the messaging flow. Returning from the method does not mean the receiving callback has run or server/client business logic has finished.

isConnected() reflects the state known to the client at the moment of the check. A connection can drop immediately afterward, so transport error handling and reconnection are still required.

## 5. Sending messages with send

The simplest way is supplying destination and payload:

~~~java
session.send("/app/orders", new CreateOrder("ORD-100"));
~~~

Spring uses the configured message converter to convert CreateOrder into the payload on the STOMP SEND frame. The server typically routes destinations with application prefix /app to the corresponding @MessageMapping.

If header control is needed, use the overload accepting StompHeaders:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/orders");
headers.setContentType(MimeTypeUtils.APPLICATION_JSON);
headers.set("x-correlation-id", "corr-2026-001");
headers.set("x-client-version", "1.4.0");

session.send(headers, new CreateOrder("ORD-101"));
~~~

Meaningful fields:

- **destination:** target of the SEND frame; this header is required when sending a message to a destination.
- **content-type:** describes the payload format, such as application/json.
- **x-correlation-id:** application-defined header for correlating logs or tracing a request.
- **x-client-version:** metadata for observability or version compatibility if the server needs it.

Custom headers must contain string data per STOMP. The server can read headers via @Header or MessageHeaders, but must validate and check input values.

Each frame should have its own StompHeaders instance. Do not share a single mutable instance across concurrent sending threads; doing so can cause one message's headers to bleed into another.

## 6. StompHeaders and header scope

StompHeaders is the header collection of a STOMP frame. It provides convenient accessors for protocol headers such as destination, content type, receipt, subscription, and acknowledgement, while also allowing custom headers.

Commonly encountered headers:

| Header | Typical frames | Meaning |
|---|---|---|
| destination | SEND, SUBSCRIBE | Target destination or subscribed destination |
| content-type | SEND, MESSAGE | Content type of the payload |
| receipt | SEND, SUBSCRIBE, UNSUBSCRIBE | Requests the broker to return RECEIPT for the frame |
| id | SUBSCRIBE, UNSUBSCRIBE | Subscription identifier |
| ack | SUBSCRIBE | Acknowledgement mode |
| message-id | MESSAGE | Message identifier provided by the broker in supported contexts |
| subscription | MESSAGE | Subscription receiving the message |
| x-correlation-id | Application-defined | Tracks a request/event across components |

Example reading headers from a received frame:

~~~java
@Override
public void handleFrame(StompHeaders headers, Object payload) {
    String contentType = headers.getContentType() == null
        ? null
        : headers.getContentType().toString();

    String messageId = headers.getFirst("message-id");
    String correlationId = headers.getFirst("x-correlation-id");

    System.out.println("content-type=" + contentType);
    System.out.println("message-id=" + messageId);
    System.out.println("correlation-id=" + correlationId);
}
~~~

Not every frame contains all headers in the table. For instance, message-id and subscription are usually added to MESSAGE by the broker; they are not values the client arbitrarily assigns to a SEND frame to dictate routing.

Distinguish StompHeaders from HTTP handshake headers. HTTP headers are sent while opening the WebSocket connection; STOMP headers reside in CONNECT, SEND, SUBSCRIBE, or MESSAGE frames after WebSocket is open. If sending Authorization in the HTTP handshake, use the appropriate WebSocket handshake headers mechanism. If the application places a token in a STOMP CONNECT header, the server must actively validate the token via a channel interceptor; Spring does not automatically treat every custom header as an authenticated identity.

## 7. Subscribing and converting payloads to the right Java type

The client subscribes to receive messages using a logical destination:

~~~java
session.subscribe(
    "/topic/order-events",
    new StompFrameHandler() {
        @Override
        public Type getPayloadType(StompHeaders headers) {
            return OrderEvent.class;
        }

        @Override
        public void handleFrame(StompHeaders headers, Object payload) {
            OrderEvent event = (OrderEvent) payload;
            process(event);
        }
    }
);
~~~

getPayloadType tells the message converter which target type to construct. If the payload is JSON representing OrderEvent, MappingJackson2MessageConverter will attempt to create an OrderEvent object. This type must match the schema emitted by the server.

If you want raw content to handle manually, you can declare byte[]. This is useful when inspecting encoding or special formats, though DTOs are more convenient for typical applications.

SUBSCRIBE is independent of SEND. The client needs to subscribe to the proper destination before expecting to receive messages. With non-persistent topics, messages broadcast before a subscription becomes active may be missed.

## 8. Receipt: how far has the broker processed the frame?

STOMP supports the receipt header so the client can request the broker to send a RECEIPT frame when the corresponding frame has been processed according to the broker's contract.

You can request a receipt for a specific frame using StompHeaders:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/orders");
headers.setReceipt("receipt-order-100");

StompSession.Receiptable receipt =
    session.send(headers, new CreateOrder("ORD-100"));

receipt.addReceiptTask(() ->
    System.out.println("Broker returned RECEIPT")
);

receipt.addReceiptLostTask(() ->
    System.err.println("Receipt was not received in time")
);
~~~

Auto-receipt can be enabled on the session to automatically request receipts for applicable operations:

~~~java
session.setAutoReceipt(true);
~~~

Receiptable lets you register callbacks when the receipt arrives or when the timeout expires. Configure the receipt time limit on the STOMP client so lost receipts can be detected and handled.

A SEND receipt indicates the broker processed the SEND frame according to the broker's contract. It does not prove every subscriber received the MESSAGE, nor does it prove the receiving client saved data or completed side effects.

Spring's Simple Broker does not provide full advanced STOMP features such as receipts and acknowledgements. When relying on RECEIPT, verify that the broker relay and external broker actually support that feature. If the broker does not support it or connectivity drops, the receipt-lost callback may be invoked.

## 9. ACK and NACK when a subscription requires acknowledgement

A subscription can use an acknowledgement mode supported by the broker. In STOMP, common modes are auto, client, and client-individual. When using client or client-individual mode, the client can ACK after processing MESSAGE or NACK when unable to process it.

Conceptual example of ACK:

~~~java
StompHeaders subscribeHeaders = new StompHeaders();
subscribeHeaders.setDestination("/queue/jobs");
subscribeHeaders.setAck("client-individual");

session.subscribe(subscribeHeaders, new StompFrameHandler() {
    @Override
    public Type getPayloadType(StompHeaders headers) {
        return Job.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        Job job = (Job) payload;
        process(job);

        String messageId = headers.getFirst("message-id");
        if (messageId != null) {
            session.acknowledge(messageId, true);
        }
    }
});
~~~

The snippet above illustrates the processing flow; only use it when the broker and destination actually support that acknowledgement mode. ACK must be sent after the processing step the application intends to confirm has finished. If process throws an exception, do not ACK as if the task succeeded.

STOMP ACK is a protocol/broker-layer confirmation. It does not replace business-level ACKs between two applications and does not automatically create exactly-once processing. When retries can redeliver messages, consumers still need idempotency to avoid executing side effects multiple times.

## 10. Error handling and connection lifecycle

Errors can occur at multiple stages:

- **WebSocket handshake:** wrong URL, server unavailable, TLS or HTTP authentication failure.
- **STOMP CONNECT:** server rejects connection, invalid protocol version, or invalid credentials.
- **Message conversion:** payload cannot be serialized/deserialized or mismatched content type.
- **SEND/SUBSCRIBE:** unauthorized destination, invalid headers, or broker rejection.
- **Transport:** socket closed, timeout, or network loss.
- **Application callback:** code inside handleFrame throws an exception or business processing fails.

StompSessionHandlerAdapter lets you handle key callbacks such as afterConnected, handleTransportError, and handleException. Log session ID, destination, correlation ID, and error category; avoid logging tokens or sensitive payloads.

When reconnecting:

1. Mark the old session as unusable when a transport error occurs.
2. Apply bounded retries with backoff, avoiding rapid reconnect loops that overload the server.
3. Establish a new STOMP connection and wait for CONNECTED.
4. Resubscribe to necessary destinations inside afterConnected.
5. Synchronize missed data or events from durable storage.
6. Resend commands only when an idempotency key or mechanism exists to determine whether the prior command was already processed.

WebSocketStompClient provides the connection API, but the application must still design reconnect and subscription-recovery policies according to business requirements. A failed StompSession should not be used as though it self-heals.

When intentionally ending a session, call session.disconnect(). The application also needs to manage the lifecycle of WebSocketStompClient and TaskScheduler to release resources on shutdown.

## 11. Security when sending headers and messages

STOMP headers are untrusted input. A client can freely set x-correlation-id, x-client-version, or custom values; the server must not trust them by default.

- Obtain user identity from the authenticated Principal, not from a username field in the payload.
- Enforce permissions for sending to each /app destination and subscribing to /topic or /queue.
- If using a JWT in STOMP CONNECT headers, validate the token in a ChannelInterceptor before processing messages and attach a valid Principal to the session.
- Do not send broker passwords or internal secrets to browser clients.
- Do not use custom headers to bypass authorization checks.
- Limit payload sizes and validate data before processing.
- Do not log access tokens, cookies, passcodes, or unnecessary personal data.

If a broker relay requires login/passcode to connect to the broker, those are credentials between the server and the broker. Do not confuse these credentials with end-user login credentials.

## 12. Testing the Java STOMP client

A meaningful integration test should verify connecting, sending, and receiving messages:

- Client connects successfully and the afterConnected callback is invoked.
- Client subscribes to the right destination and receives DTOs of the expected type.
- SEND uses the right destination, content type, and custom headers.
- Server rejects unauthorized destinations.
- Invalid-schema payloads produce observable conversion errors.
- If the broker supports receipts, receipt callbacks run; when no receipt arrives, timeouts are handled.
- If using ACK mode, verify ACK after processing and behavior when the consumer errors.
- Disconnect and reconnect; client resubscribes and synchronizes state per contract.
- Re-sending the same command ID does not create duplicate business side effects.

Avoid using fixed Thread.sleep calls to wait for messages. Use CompletableFuture, CountDownLatch, or a timeout-bounded wait mechanism so the test finishes as soon as the expected condition occurs. A test against Simple Broker does not prove broker relay or an external broker's receipt/ACK features work.

## 13. Checklist when sending fails

- Has the connection CompletableFuture completed and has afterConnected been called?
- Is StompSession still connected according to client state?
- Does the SEND destination match the application prefix /app or broker prefixes /topic, /queue?
- Do the payload converter and content-type match the server's schema?
- Does StompHeaders include the required destination and valid custom headers?
- Did the client subscribe to the right destination before the server published?
- Are there any ERROR frames, transport errors, or conversion errors?
- Does the broker support the receipt/ACK the application expects?
- After reconnecting, did the client resubscribe and sync missed messages?
- Did the server authenticate the Principal and check permissions on the destination?

StompSession provides the API to interact with a STOMP session; StompHeaders describes metadata on each frame; the message converter handles Java payloads. When sending messages, inspect connection, destination, serialization, broker receipt, and business confirmation separately to know precisely which milestone the system has completed.