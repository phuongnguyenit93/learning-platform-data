# StompSubProtocolHandler and Converting STOMP Frames to Messages

In the Spring Framework, **StompSubProtocolHandler** is the component that connects the STOMP protocol with Spring's internal messaging system. It receives WebSocket messages from the client, decodes STOMP frames into **Message<byte[]>** objects, adds Spring metadata, and then passes the message into an internal channel. In the opposite direction, it receives Spring Messages destined for the client, encodes them into STOMP frames, and sends them over WebSocket.

It is important to understand the scope of the handler correctly: it handles the protocol and the transport boundary. It is not a message broker, it does not execute business logic by itself, and it does not by itself convert JSON into every Java object that a controller requests. Converting payload bytes into a DTO usually happens in a later step using a Spring MessageConverter.

## 1. Where does StompSubProtocolHandler sit?

When STOMP messaging is enabled in Spring with @EnableWebSocketMessageBroker, the framework registers the necessary WebSocket and messaging components. One of them is **SubProtocolWebSocketHandler**, which is responsible for choosing the protocol handler that matches the subprotocol negotiated by the client in the HTTP WebSocket handshake.

The client can send a Sec-WebSocket-Protocol header with values such as v10.stomp, v11.stomp, or v12.stomp. SubProtocolWebSocketHandler chooses the handler that supports the selected protocol. StompSubProtocolHandler supports STOMP 1.0, 1.1, and 1.2.

Main components:

- **WebSocketSession:** the WebSocket connection between one client and the server.
- **SubProtocolWebSocketHandler:** selects a handler by subprotocol and dispatches WebSocket messages.
- **StompSubProtocolHandler:** converts between WebSocket messages and STOMP frames.
- **StompDecoder / BufferingStompDecoder:** parse STOMP frames from a byte buffer and assemble incomplete data.
- **StompHeaderAccessor:** reads, normalizes, and creates STOMP/Spring message headers.
- **clientInboundChannel:** receives Spring Messages from the client to pass on to controllers or the broker.
- **clientOutboundChannel:** carries messages from the broker/application back to the client.
- **StompEncoder:** encodes a Spring Message into a STOMP frame.

~~~mermaid
flowchart TD
    C["STOMP client"] --> W["WebSocketSession"]
    W --> S["SubProtocolWebSocketHandler"]
    S --> H["StompSubProtocolHandler"]
    H --> D["BufferingStompDecoder / StompDecoder"]
    D --> M["Message<byte[]> + StompHeaderAccessor"]
    M --> I["clientInboundChannel"]
    I --> R["@MessageMapping / broker"]
    R --> O["clientOutboundChannel"]
    O --> H2["StompSubProtocolHandler"]
    H2 --> E["StompEncoder"]
    E --> W2["WebSocket text/binary message"]
    W2 --> C
~~~

In a typical application configuration, developers do not need to create a StompSubProtocolHandler themselves. Spring creates the handler and wires it to the channels, the broker, and the WebSocket endpoint. Understanding this class helps you read logs, debug the protocol, and know at which layer to extend.

## 2. Two conversion directions

StompSubProtocolHandler does work in two directions:

| Direction | Input | Output | Purpose |
|---|---|---|---|
| Inbound | WebSocket TextMessage or BinaryMessage containing STOMP bytes | Spring Message<byte[]> | Bring the client's frame into the messaging system |
| Outbound | Spring Message<byte[]> destined for a session | WebSocket TextMessage or BinaryMessage containing a STOMP frame | Send a message from the application/broker back to the client |

A STOMP frame has a command, headers, a body, and a NULL character that terminates the frame. A Spring Message has its own payload and headers. The handler converts the STOMP command/header portion into metadata that Spring understands, while keeping the native STOMP headers so that later layers can still access them.

For example, the client sends:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"orderId":"ORD-42","customer":"Ada"}^@
~~~

After decoding, Spring has a Message whose payload is a byte array containing the JSON, and equivalent metadata:

~~~text
simpMessageType = MESSAGE
simpDestination = /app/orders.create
simpSessionId = ws-session-42
simpUser = alice
nativeHeaders.content-type = application/json
nativeHeaders.destination = /app/orders.create
~~~

The simp headers are Spring's normalized metadata. The native headers keep STOMP's original headers such as destination, subscription id, ack, receipt, content-type, or content-length.

## 3. Inbound: from a WebSocket message to a STOMP frame

The main method on the client side is handleMessageFromClient. The handler receives the WebSocketSession, the WebSocketMessage, and the target MessageChannel.

### 3.1. Receiving text and binary messages

STOMP can be carried in WebSocket text or binary messages:

- With a TextMessage, the handler takes the content and converts it into a byte buffer using the WebSocket text encoding.
- With a BinaryMessage, the handler uses the payload ByteBuffer directly.
- WebSocket message types that do not suit STOMP are ignored.

Receiving a WebSocket message does not mean a complete STOMP frame has been received. A frame can be split into multiple parts when the client sends consecutive WebSocket messages.

### 3.2. The decoder is kept per session

The handler maintains one BufferingStompDecoder for each WebSocket session. This is very important because the missing data of client A must not be mistakenly combined with the data of client B.

BufferingStompDecoder uses StompDecoder to read frames. When data is incomplete, the decoder keeps the remainder and combines it with the data received the next time. When there is enough data, the decoder can return one or more Spring Message<byte[]> objects.

A single WebSocket message can contain several complete STOMP frames. Conversely, a single STOMP frame can also span multiple WebSocket messages. Therefore, you should not assume that one WebSocket message always corresponds to exactly one STOMP frame.

~~~mermaid
flowchart TD
    A["WebSocket message chunk 1"] --> B["BufferingStompDecoder"]
    C["WebSocket message chunk 2"] --> B
    D["WebSocket message chunk 3"] --> B
    B --> E{"Frame complete?"}
    E -->|No| F["Keep partial bytes"]
    F --> B
    E -->|Yes| G["StompDecoder"]
    G --> H["One or more Message<byte[]>"]
~~~

If a frame contains a content-length header, the decoder can use that length to determine how much body data it still has to wait for. If the buffer holds only part of a frame, the decoder does not yet emit that message into the channel.

### 3.3. Size limit

StompSubProtocolHandler has a default message buffer limit of **64 KB**. Because a STOMP frame can be assembled from multiple WebSocket messages, this limit applies to the size of the STOMP message after buffering.

You can raise the limit through the WebSocket transport configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(128 * 1024);
    }
}
~~~

The value above is 128 KiB. Adjust it according to the actual payload size and the limits of the reverse proxy, servlet container, or WebSocket server. Raising the limit does not mean you should allow unlimited messages; large buffers increase memory consumption when there are many concurrent sessions.

StompSubProtocolHandler also has a constant MINIMUM_WEBSOCKET_MESSAGE_SIZE equal to 16 KiB plus 256 bytes. The handler uses this minimum to support clients that split a STOMP message into WebSocket messages of about 16 KiB, with extra headroom for framing such as SockJS. When configuring the transport server, make sure the WebSocket text message limit is large enough for this requirement.

## 4. How does StompDecoder create a Message<byte[]>?

StompDecoder does not directly create OrderCreated, ChatMessage, or business DTOs. It parses the protocol structure and creates a list of Spring Messages whose payload is of type byte[].

General steps:

1. Read the command, for example SEND, SUBSCRIBE, CONNECT, or DISCONNECT.
2. Read the headers according to STOMP syntax.
3. Determine the body by content-length if present, or by the NULL character that terminates the frame.
4. Create a StompHeaderAccessor containing the command and the native headers.
5. Map the common headers to Spring metadata.
6. Create a Message<byte[]> with the payload and MessageHeaders.

StompDecoder can decode multiple frames in a single ByteBuffer. If the end of the buffer does not yet contain a full frame, the remainder is kept so that the next decode continues. Syntax errors or invalid data can raise a StompConversionException.

### 4.1. Why is the payload still byte[]?

STOMP allows a text or binary payload. At the protocol layer, keeping the body as byte[] means the handler does not have to guess the business data type and avoids unnecessary conversion.

Example JSON body:

~~~json
{"orderId":"ORD-42","customer":"Ada"}
~~~

After protocol decoding, the body is still byte[]. When the message is passed to a controller method that accepts OrderCreated, Spring uses a MessageConverter appropriate to the content-type to convert byte[] into a Java object.

These are two separate steps:

| Step | Component | Result |
|---|---|---|
| Protocol decoding | StompDecoder / StompSubProtocolHandler | STOMP frame to Message<byte[]> |
| Payload conversion | Spring MessageConverter | byte[] or String to a business DTO |

If a controller does not receive the DTO as expected, check the content-type, the registered converters, and the payload schema. Do not assume by default that the fault lies in StompSubProtocolHandler.

## 5. StompHeaderAccessor and the two groups of headers

**StompHeaderAccessor** extends SimpMessageHeaderAccessor and is used when creating a Message from a STOMP frame or when encoding a Message back into a STOMP frame.

There are two important groups of headers:

### 5.1. Spring processing headers

SimpMessageHeaderAccessor manages metadata common to Spring's messaging system:

- **simpMessageType:** the internal message type, for example MESSAGE, SUBSCRIBE, CONNECT, or DISCONNECT.
- **simpDestination:** the destination after normalization.
- **simpSessionId:** the ID of the WebSocket/STOMP session.
- **simpSessionAttributes:** the attributes attached to the session.
- **simpUser:** the client's Principal if authenticated.
- **simpHeartbeat:** the negotiated heartbeat information.

For example, a STOMP SEND is mapped to Spring's message type MESSAGE. A STOMP SUBSCRIBE becomes the message type SUBSCRIBE so that the broker or an interceptor can handle the subscription.

### 5.2. Native STOMP headers

STOMP's original headers are kept in the native header map. For example:

- destination
- id
- ack
- receipt
- content-type
- content-length
- accept-version
- heart-beat
- subscription

You can read native headers through StompHeaderAccessor:

~~~java
StompHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
        );

if (accessor != null) {
    String destination = accessor.getDestination();
    String subscriptionId = accessor.getSubscriptionId();
    String contentType = accessor.getContentType();

    String receipt = accessor.getReceipt();
}
~~~

The code above is used in a ChannelInterceptor or a component that receives a Spring Message. You need to check that the accessor exists before reading it. If the message has already gone through some processing steps, you may need to wrap the message with StompHeaderAccessor.

You should not modify native headers arbitrarily in an interceptor. Headers such as destination, subscription id, receipt, or ack carry protocol meaning and can affect routing or acknowledgement.

## 6. Attaching the session ID, Principal, and session attributes

A STOMP frame from the client does not by itself carry a trustworthy Spring session ID. The handler takes the session ID from the WebSocketSession and attaches it to the Message.

The handler also puts the WebSocket session's session attributes and Principal into SimpMessageHeaderAccessor. This lets later layers determine which connection and which user a message came from.

If the application authenticates users through the HTTP handshake, the Principal attached to the WebSocket session is used for the STOMP session. You can add authentication/authorization at the clientInboundChannel with a ChannelInterceptor or Spring Security message authorization.

When it receives the first CONNECT or STOMP, the handler creates a SessionInfo for the session and keeps the appropriate MessageChannel. It also sets up a callback so that an interceptor can change the Principal of the STOMP session in case the application has its own authentication mechanism.

Do not trust user ID headers sent by the client to determine identity. Identity must be based on the Principal authenticated by the server; SEND/SUBSCRIBE permissions must be checked at the security layer.

## 7. CONNECT, CONNECTED, and heartbeat

STOMP CONNECT or STOMP is the first frame that establishes a STOMP session over a WebSocket session that has already been created.

The handler receives the CONNECT/STOMP frame, creates the session information, attaches the user and session attributes, and then sends the Message into clientInboundChannel. The broker handles CONNECT and returns CONNECTED if it accepts.

Two application events help distinguish two milestones:

- **SessionConnectEvent:** published when the server receives a STOMP CONNECT; this is the moment the client starts requesting the creation of a STOMP session.
- **SessionConnectedEvent:** published afterwards when the broker sends a STOMP CONNECTED; at this point the STOMP session is considered fully established.

Heartbeat is declared in the heart-beat header of CONNECT and CONNECTED. The handler moves the heartbeat information into Spring metadata and handles heartbeat frames at the protocol layer. A heartbeat is not a business message sent to @MessageMapping.

Example of a listener receiving events:

~~~java
@Component
public class StompSessionEvents {

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        Message<?> message = event.getMessage();

        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        String sessionId = accessor.getSessionId();
        Principal user = accessor.getUser();

        // Record the connection request.
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        // The broker has responded with CONNECTED.
    }
}
~~~

This example illustrates reading events. In real code, you need to import the corresponding classes and handle the case where the Principal can be null.

Other events include SessionSubscribeEvent, SessionUnsubscribeEvent, and SessionDisconnectEvent. SessionDisconnectEvent can be published more than once for the same session in some situations; a listener that handles the event should be idempotent to avoid releasing resources or recording the disconnect twice.

## 8. The inbound channel and preserveReceiveOrder

After decoding and attaching metadata, the handler sends each Message into the channel chosen for the session. With ordinary STOMP messaging, this channel is clientInboundChannel.

Here, the message is forwarded according to its destination:

- A destination under the application prefix, for example /app/orders.create, is passed to a @MessageMapping method.
- A destination under the broker prefix, for example /topic/prices, is passed to the message broker.
- SUBSCRIBE and UNSUBSCRIBE are handled to manage subscriptions.
- CONNECT and DISCONNECT are handled according to the protocol lifecycle.

An important point is that clientInboundChannel is usually backed by a ThreadPoolExecutor. Therefore, multiple messages from the same session can be processed by different threads, and the order in which processing completes can differ from the order of receipt.

Since Spring Framework 6.1, StompSubProtocolHandler supports preserveReceiveOrder. You can enable it on the registry:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class OrderedStompConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);
    }
}
~~~

When enabled, messages within the same client session are sent into clientInboundChannel one message at a time to preserve the order of receipt. This option has coordination overhead and can reduce parallelism; enable it only when the business logic needs ordering.

You need to distinguish preserveReceiveOrder from preservePublishOrder. One option controls the order of messages going from the client into the application; the other controls the order of messages sent from the server out to the client.

## 9. Outbound: from a Spring Message back to a STOMP frame

In the opposite direction, the broker or the application sends a message through clientOutboundChannel. SubProtocolWebSocketHandler routes the message to the appropriate session, and then calls StompSubProtocolHandler.handleMessageToClient.

General process:

1. Determine the session ID from the Spring message header.
2. Check whether the payload is byte[] per the contract of the STOMP encoder.
3. Obtain the StompHeaderAccessor or wrap the message with an accessor.
4. Determine the STOMP command to send, for example MESSAGE, CONNECTED, RECEIPT, ERROR, or heartbeat.
5. Handle special headers according to the command and session.
6. Call StompEncoder to create the byte array of the STOMP frame.
7. Send it through the WebSocketSession.

Normally the frame is sent as a TextMessage. If the payload has the content-type application/octet-stream and a SockJS session is not used, the handler can send a BinaryMessage. This allows STOMP to carry a binary payload without forcing it into text.

StompEncoder is responsible for encoding the command, native headers, content-length when needed, and the body into the wire format. The handler decides the appropriate session and WebSocket message type.

## 10. Handling CONNECTED, DISCONNECT_ACK, HEARTBEAT, and MESSAGE

Not every outbound Spring Message already has a specific STOMP command. Some internal messages need to be converted into the corresponding STOMP command:

- **CONNECT_ACK:** the internal response from the simple broker is converted into a STOMP CONNECTED; the handler determines the accepted STOMP version and the heartbeat.
- **DISCONNECT_ACK:** if the client requested a receipt, the handler can create a RECEIPT; otherwise, it can create an ERROR reporting that the session has closed, depending on the processing flow.
- **HEARTBEAT:** is converted into a heartbeat frame.
- **MESSAGE:** is sent to the subscriber; the handler checks the subscription header and destination.
- **ERROR:** can pass through an error handler depending on the configuration.

When the broker returns CONNECTED, the handler updates the session information and publishes a SessionConnectedEvent. If there is a Principal, the handler can put the user name into the user-name header on the CONNECTED frame.

For a MESSAGE message, the subscription ID is important metadata so that the client knows which subscription the message belongs to. If the subscription header is missing, the handler logs a warning because the frame may not follow the structure that the STOMP client expects.

## 11. Protocol errors and StompSubProtocolErrorHandler

Errors can occur at many layers:

- A STOMP frame with invalid syntax or missing required parts.
- An invalid header or content-length.
- The buffer exceeds the message size limit.
- There is no valid STOMP session for the next frame.
- A channel rejects the message due to authorization or an interceptor.
- Errors in the broker or in message handling.

If no StompSubProtocolErrorHandler is configured, the default handler may send a STOMP ERROR frame and then close the WebSocket session with CloseStatus.PROTOCOL_ERROR.

StompSubProtocolHandler provides the setErrorHandler(StompSubProtocolErrorHandler) method for the protocol layer. A custom handler can create a STOMP ERROR message with sensitive information removed, or return null to prevent sending the error frame.

You need to distinguish this extension point from configureClientInboundChannel. A ChannelInterceptor is used to inspect, add metadata to, or reject a Spring Message as it enters the channel; StompSubProtocolErrorHandler decides how a protocol/message processing error is represented as a STOMP ERROR frame. For business exceptions in @MessageMapping, you should usually use @MessageExceptionHandler or the application's messaging error handling mechanism.

In an ordinary @EnableWebSocketMessageBroker configuration, Spring manages StompSubProtocolHandler internally. If you need to replace or customize the handler at a low level, use the supported infrastructure configuration mechanism in the exact Spring version you are deploying.

Do not put stack traces, SQL, broker information, or secrets into the ERROR frame sent to the client. Log the details on the server with a correlation/session ID, while the client receives a short message that contains no sensitive data.

It is also necessary to distinguish protocol errors from business errors. An error while processing in a @MessageMapping method can be handled through @MessageExceptionHandler or an error channel/broker mechanism. Not every business exception means a STOMP frame has a syntax error.

## 12. MessageHeaderInitializer and observability configuration

StompSubProtocolHandler lets you set a MessageHeaderInitializer. The initializer is applied to the headers of messages created from STOMP frames and of messages sent into the client inbound channel according to the configuration.

It can be used to standardize common metadata, for example tracing headers or internal default values. Do not use an initializer to replace authentication or authorization.

The handler also provides Stats to observe the number of CONNECT, CONNECTED, and DISCONNECT frames processed. You can read the statistics from getStats() or getStatsInfo() when you need to diagnose the session lifecycle.

Operational metrics should be combined with broker and channel metrics:

- The number of active WebSocket sessions.
- The number of successful STOMP CONNECT and CONNECTED.
- The number of DISCONNECT and sessions closed due to protocol errors.
- The number of decode errors and the number of times the message size limit is exceeded.
- The processing latency of clientInboundChannel/clientOutboundChannel.
- The number of messages rejected due to authorization or the broker.
- The outbound buffer and send time when a client reads slowly.
- The number of subscriptions and the volume of messages emitted per session.

## 13. Transport, size, and ordering configuration

A WebSocket STOMP configuration can adjust the message size, the send time, and the outbound buffer:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompTransportConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setMessageSizeLimit(128 * 1024)
                .setSendTimeLimit(15 * 1000)
                .setSendBufferSizeLimit(512 * 1024);
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);
    }
}
~~~

The example sets an inbound message limit of 128 KiB, a send time limit of 15 seconds, and an outbound buffer limit of 512 KiB. These limits need to be chosen according to the load and the capacity of the server.

If preserveReceiveOrder and preservePublishOrder are enabled, message order is preserved within each client session in the two corresponding directions. That can reduce throughput when many consecutive messages have to wait for each other. Do not enable them merely out of a desire to be "safe"; determine whether the business logic really depends on ordering.

## 14. Common mistakes

### 14.1. Thinking that StompSubProtocolHandler converts JSON into a DTO

The handler converts the frame into Message<byte[]> and normalizes the headers. DTO conversion happens afterwards through a MessageConverter.

How to handle it: check the content-type, the converter, and the parameter type of the @MessageMapping method.

### 14.2. Assuming one WebSocket message equals one STOMP frame

A client can send multiple frames in one WebSocket message or split one large frame into multiple WebSocket messages.

How to handle it: let BufferingStompDecoder manage the missing data; do not parse each WebSocket message yourself as a complete frame.

### 14.3. Ignoring native headers

STOMP headers such as subscription, ack, receipt, and content-length may be needed for protocol handling.

How to handle it: use StompHeaderAccessor to access native headers; avoid deleting or changing headers if you do not understand the impact.

### 14.4. Confusing Spring's message type with the STOMP command

A STOMP SEND is usually represented as SimpMessageType.MESSAGE. This is how Spring normalizes commands so they can share the common message infrastructure.

How to handle it: read the STOMP command through StompHeaderAccessor when you need protocol detail; read simpMessageType when you need to classify internal messages.

### 14.5. Allowing unlimited payloads

Large frames, or many sessions sending large frames at the same time, can increase memory due to buffering.

How to handle it: configure an appropriate message size limit, check the limits of the WebSocket server and the reverse proxy, and also limit the send rate.

### 14.6. Not accounting for inbound ordering

clientInboundChannel uses a thread pool, so messages from the same session can complete out of the order received.

How to handle it: enable preserveReceiveOrder when the business logic needs it; otherwise, design idempotent handlers that do not depend on implicit ordering.

### 14.7. Conflating protocol errors with business errors

A frame with a malformed structure is a protocol error; a controller throwing an exception while processing an order is a business error.

How to handle it: handle protocol errors through StompSubProtocolErrorHandler and handle controller errors through an exception handler or an appropriate messaging mechanism.

### 14.8. Handling SessionDisconnectEvent in a non-idempotent way

A session can publish multiple disconnect events in some cases.

How to handle it: when removing a session, subscription, or presence, design the operation so it can be called repeatedly without producing side effects.

## 15. Java 17 example: simulating a STOMP frame to a Spring Message

The following example simulates the core conversion of a STOMP SEND frame into an internal Message structure. It uses plain JDK to illustrate the command, native headers, Spring headers, and the byte[] payload.

This is not an implementation of StompSubProtocolHandler, StompDecoder, or Spring Message. The real handler also deals with the STOMP version, header escaping, content-length, buffering, heartbeat, session, Principal, events, and channel dispatch.

Create the file **StompFrameToMessageDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public class StompFrameToMessageDemo {

    record ParsedFrame(
            String command,
            Map<String, String> nativeHeaders,
            byte[] payload) {}

    record SpringMessage(
            Map<String, String> simpHeaders,
            Map<String, String> nativeHeaders,
            byte[] payload) {}

    static ParsedFrame decodeOneFrame(String wire) {
        String normalized = wire.replace("\r\n", "\n");
        int separator = normalized.indexOf("\n\n");

        if (separator < 0) {
            throw new IllegalArgumentException(
                    "Missing STOMP header/body separator");
        }

        String headerBlock = normalized.substring(0, separator);
        String body = normalized.substring(separator + 2);

        if (body.endsWith("\0")) {
            body = body.substring(0, body.length() - 1);
        }

        String[] lines = headerBlock.split("\n");
        String command = lines[0];
        Map<String, String> headers = new LinkedHashMap<>();

        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');

            if (colon <= 0) {
                throw new IllegalArgumentException(
                        "Invalid STOMP header: " + lines[i]);
            }

            String name = lines[i].substring(0, colon);
            String value = lines[i].substring(colon + 1);
            headers.putIfAbsent(name, value);
        }

        return new ParsedFrame(
                command,
                Map.copyOf(headers),
                body.getBytes(StandardCharsets.UTF_8)
        );
    }

    static SpringMessage toSpringMessage(
            ParsedFrame frame,
            String sessionId,
            String principalName) {

        if (!"SEND".equals(frame.command())) {
            throw new IllegalArgumentException(
                    "Demo expects a SEND frame");
        }

        Map<String, String> simpHeaders = new LinkedHashMap<>();
        simpHeaders.put("simpMessageType", "MESSAGE");
        simpHeaders.put(
                "simpDestination",
                frame.nativeHeaders().get("destination")
        );
        simpHeaders.put("simpSessionId", sessionId);
        simpHeaders.put("simpUser", principalName);

        return new SpringMessage(
                Map.copyOf(simpHeaders),
                frame.nativeHeaders(),
                frame.payload()
        );
    }

    public static void main(String[] args) {
        String frame =
                "SEND\n"
                + "destination:/app/orders.create\n"
                + "content-type:application/json\n"
                + "\n"
                + "{\"orderId\":\"ORD-42\",\"customer\":\"Ada\"}\0";

        ParsedFrame parsed = decodeOneFrame(frame);

        SpringMessage message = toSpringMessage(
                parsed,
                "ws-session-42",
                "alice"
        );

        System.out.println("STOMP command: " + parsed.command());
        System.out.println(
                "Spring message type: "
                        + message.simpHeaders().get("simpMessageType"));
        System.out.println(
                "simpDestination: "
                        + message.simpHeaders().get("simpDestination"));
        System.out.println(
                "simpSessionId: "
                        + message.simpHeaders().get("simpSessionId"));
        System.out.println(
                "simpUser: " + message.simpHeaders().get("simpUser"));
        System.out.println(
                "native content-type: "
                        + message.nativeHeaders().get("content-type"));
        System.out.println("payload type: byte[]");
        System.out.println(
                "payload: "
                        + new String(
                                message.payload(),
                                StandardCharsets.UTF_8
                        ));
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac StompFrameToMessageDemo.java
java StompFrameToMessageDemo
~~~

Result:

~~~text
STOMP command: SEND
Spring message type: MESSAGE
simpDestination: /app/orders.create
simpSessionId: ws-session-42
simpUser: alice
native content-type: application/json
payload type: byte[]
payload: {"orderId":"ORD-42","customer":"Ada"}
~~~

The example shows a SEND frame being represented as a Spring message with a destination, session, user, native headers, and a byte[] payload. The session ID and user in the example are passed in from the WebSocket session context; they are not taken from the client's JSON body.

The sample parser handles only a simple single text frame. A production parser must handle STOMP 1.1/1.2 header escaping, content-length, binary bodies, heartbeats, multiple frames in a buffer, and frames split across multiple receives. In a Spring application, let StompDecoder and StompSubProtocolHandler perform those protocol tasks.

## 16. Debugging process when a frame does not reach the controller

When a client sends SEND but the @MessageMapping method does not run, check in this order:

1. Did the WebSocket handshake succeed and select the correct subprotocol v10.stomp, v11.stomp, or v12.stomp?
2. Did the client send STOMP CONNECT/STOMP and receive CONNECTED?
3. Is the WebSocket message a text or binary payload containing a valid STOMP frame?
4. Does the frame have the required command and headers; does the body end correctly or is there a valid content-length?
5. Is BufferingStompDecoder holding an incomplete frame or reporting a message size limit exceeded error?
6. Does StompHeaderAccessor receive the correct command, destination, and content-type?
7. Is the message sent into clientInboundChannel?
8. Does the destination prefix match the configured application prefix?
9. Does a ChannelInterceptor or Spring Security reject the SEND?
10. Can the MessageConverter convert the payload into the controller's parameter type?

If the client receives an ERROR frame, check the server log and StompSubProtocolErrorHandler. If the message enters the broker but does not reach the subscriber, check the destination, the subscription ID, and the broker semantics. If the controller has run but the client does not receive a response, check clientOutboundChannel, the session ID, StompEncoder, and the WebSocket send buffer.

Do not log passcodes, tokens, or whole sensitive payloads when debugging. You can log the command, destination, session ID, message type, payload size, and correlation ID to trace the flow.

## 17. Key takeaways

StompSubProtocolHandler is the adapter between WebSocket and Spring messaging. In the inbound direction, it uses a per-session buffering decoder to convert STOMP frames into Message<byte[]> with native STOMP headers and Spring's normalized metadata. The message is sent into clientInboundChannel for controllers, the broker, and interceptors to handle.

In the outbound direction, the handler receives a Spring Message destined for a session, normalizes the STOMP command/headers, uses StompEncoder to create the frame, and then sends it through a WebSocket text or binary message. CONNECT/CONNECTED, heartbeat, lifecycle events, protocol errors, message size, and inbound ordering are all important parts of the handler's job.

When debugging, determine whether the fault lies in the WebSocket transport, STOMP decoding, header mapping, channel routing, MessageConverter, the broker, or outbound encoding. Clearly distinguishing protocol conversion from payload conversion will help you find the right layer to inspect.

## References

- [Spring Framework 6.2.17: StompSubProtocolHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolHandler.html)
- [Spring Framework: StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework: StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework: StompEncoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html)
- [Spring Framework: Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework: Ordered Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)