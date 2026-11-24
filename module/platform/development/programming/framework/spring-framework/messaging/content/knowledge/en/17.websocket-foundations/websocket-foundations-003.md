# Plain WebSocketHandler and the High-Level Messaging Model in Spring

## 1. WebSocket Is a Bidirectional Transport Channel, Not a Business Protocol

WebSocket creates a full-duplex, bidirectional connection between the client and the server over one TCP connection. The process starts with an HTTP handshake carrying an Upgrade header; after the server returns 101 Switching Protocols, both sides continue to send and receive frames on the same connection.

WebSocket only specifies how frames are transmitted. It does not specify what the content of a frame means, who the recipient is, whether a message is a command or an event, how to register for notifications, or how to acknowledge processing. The client and server must agree on those rules.

Spring Framework provides two main programming levels:

- **Plain WebSocketHandler:** works directly with WebSocketSession and WebSocketMessage. The application defines the payload format, message types, routing, subscriptions, errors, and session state itself.
- **High-level messaging model:** typically uses STOMP as a sub-protocol on top of WebSocket. Spring decodes the STOMP frame into a Message with headers and a payload, routes it through a MessageChannel, maps it to @MessageMapping, and uses a broker to manage subscriptions, publishing, and broadcasting.

Both models use the WebSocket transport but provide different levels of abstraction. Choose the model based on your needs for routing and messaging semantics, not merely on whether the application needs a real-time connection.

## 2. A Quick Comparison of the Two Models

| Criterion | Plain WebSocketHandler | High-level messaging with STOMP |
| --- | --- | --- |
| Unit of processing | WebSocketMessage: text, binary, ping/pong | A Spring Message consisting of a payload and headers, created from a STOMP frame |
| Server entry point | A handler mapped to a WebSocket URL | A STOMP endpoint and the message broker infrastructure |
| Routing | The application designs and implements it | Destination prefix, @MessageMapping, and the broker |
| Publish/subscribe | Manage the session and subscription lists yourself | The client sends SUBSCRIBE; the broker manages subscriptions |
| Sending to clients | Call WebSocketSession.sendMessage | SimpMessagingTemplate or the return value of @MessageMapping |
| Application protocol | Define your own envelope and conventions | STOMP has CONNECT, SEND, SUBSCRIBE, MESSAGE, DISCONNECT |
| Acknowledgment, heartbeat | Design your own or use a custom protocol | Has a STOMP structure; the level of support depends on the broker |
| Level of control | High, suits specialized protocols | High in terms of messaging semantics, but following the STOMP/Spring model |

A plain WebSocketHandler fits when the client-server protocol has already been defined separately, the payload has a special structure, or you need to handle frames at a low level. STOMP fits when the application needs publish/subscribe, destination routing, controller methods, user destinations, and message broker integration.

## 3. How Does a Plain WebSocketHandler Work?

The WebSocketHandler interface receives callbacks following the connection lifecycle:

- afterConnectionEstablished: called when the handshake succeeds and the session is open.
- handleMessage: receives a WebSocketMessage from the client.
- handleTransportError: reports a transport error.
- afterConnectionClosed: called when the connection closes.
- supportsPartialMessages: indicates whether the handler handles messages split into multiple parts.

In practice, you usually extend AbstractWebSocketHandler, TextWebSocketHandler, or BinaryWebSocketHandler instead of implementing all the methods yourself.

### 3.1. TextWebSocketHandler

TextWebSocketHandler is a utility class for applications that handle text frames. It provides the handleTextMessage callback to receive a TextMessage together with the WebSocketSession.

~~~java
import java.io.IOException;

import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.stereotype.Component;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String reply = "echo: " + message.getPayload();

        if (session.isOpen()) {
            session.sendMessage(new TextMessage(reply));
        }
    }
}
~~~

The handler receives the text payload and sends back a text frame. This is an example of a transport-level echo; it has no destination, subscription, or message broker yet.

If the application needs a binary payload, extend BinaryWebSocketHandler or handle the appropriate WebSocketMessage. Do not assume every client sends text JSON; you need to agree on the frame type and the message size limit.

### 3.2. Registering a Handler to a URL

Use @EnableWebSocket and WebSocketConfigurer to map the handler to an endpoint:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public RawWebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/raw")
                .setAllowedOrigins("https://app.example.com");
    }
}
~~~

The client performs a WebSocket handshake to the URL /ws/raw. After a successful connection, all application frames are passed to EchoWebSocketHandler.

In a real application, replace the example origin with the allowed frontend domain. Do not open a wildcard origin without a reason and corresponding security control. The WebSocket handshake still needs user authentication and an origin check according to the application's policy.

Spring WebSocket is not required to run together with Spring MVC. In a Servlet stack application, handlers are usually registered through WebSocketConfigurer; other HTTP environments can integrate a WebSocketHandler through WebSocketHttpRequestHandler.

`EchoWebSocketHandler` is marked `@Component`; make sure the handler's package is within the component scan so that the constructor injection of `RawWebSocketConfiguration` works.

## 4. WebSocketSession and Connection State

WebSocketSession represents a specific connection. Commonly used information:

| API | Purpose |
| --- | --- |
| getId() | Gets the session ID |
| getUri() | Gets the connection URI |
| getPrincipal() | Gets the authenticated user, if any |
| getAttributes() | Reads the attributes attached during the handshake |
| isOpen() | Checks whether the connection is still open |
| sendMessage(message) | Sends a text or binary message |
| close(status) | Closes the connection with a CloseStatus |
| setTextMessageSizeLimit(...) | Sets the text message size limit |
| setBinaryMessageSizeLimit(...) | Sets the binary message size limit |

You can use a HandshakeInterceptor to check or add attributes before and after the handshake. For example, HttpSessionHandshakeInterceptor transfers some attributes from the HTTP session to the WebSocketSession attributes.

Do not store the state of every connection in a mutable field of a singleton handler without synchronization. If you need to manage sessions, you can use a thread-safe registry keyed by session ID, store user and subscription information, and then delete the data in afterConnectionClosed.

Example of lifecycle management:

~~~java
@Override
public void afterConnectionEstablished(WebSocketSession session) {
    sessions.put(session.getId(), session);
}

@Override
public void afterConnectionClosed(
        WebSocketSession session,
        CloseStatus status) {

    sessions.remove(session.getId());
}
~~~

The code assumes sessions is a thread-safe registry declared and managed separately. You also need to handle the case where the handshake succeeds but the client disconnects right afterward, transport errors, timeouts, and application shutdown.

## 5. Concurrent Sending and Session Limits

A standard WebSocket session does not allow multiple threads to call send concurrently. If one thread processes a message and a scheduled task sends to the same session at the same time, the calls to sendMessage need to be serialized.

Spring provides ConcurrentWebSocketSessionDecorator to wrap a WebSocketSession. The decorator ensures only one thread sends at a time; other sends can be buffered while the current send completes. If the buffer limit or the send time limit is exceeded, the session may be closed according to the overflow strategy.

~~~java
WebSocketSession safeSession =
    new ConcurrentWebSocketSessionDecorator(
        session,
        10_000,
        512 * 1024
    );

safeSession.sendMessage(new TextMessage("notification"));
~~~

In the example, 10,000 is the send time limit in milliseconds and 512 KiB is the buffer limit. Choose limits according to the client's capability and the actual payload size; do not increase the buffer without bound, because a slow client can cause the server to consume memory.

If you use STOMP messaging support, Spring also has a mechanism for handling session send concurrency. Even so, the application still needs to control the volume of messages emitted, the consumption rate, and the behavior when the client cannot read fast enough.

## 6. What the Application Must Build Itself with a Plain Handler

A plain WebSocketHandler only provides callbacks and the session API. To have a complete messaging system, the application must design the following additional components itself:

1. **Message envelope:** a JSON convention or binary schema, for example type, id, timestamp, payload, and correlationId.
2. **Routing:** determine which message is a command, event, response, or notification and forward it to the corresponding service.
3. **Subscription:** store which session is registered for which event type or channel.
4. **Broadcast:** choose the matching sessions and send the message to each session.
5. **User routing:** map an authenticated user to one or more open sessions.
6. **Heartbeat and timeout:** detect a dead connection or a client that no longer responds.
7. **Error protocol:** agree on error codes, error messages, and the behavior for closing the connection.
8. **Backpressure:** limit the send queue, message size, and emission rate.
9. **Reconnect and resubscribe:** handle a client reconnecting after the network is interrupted.
10. **Authorization:** check whether the user has permission to send commands or register to receive data.

Example of an envelope defined by the application itself:

~~~json
{
  "type": "chat.send",
  "id": "msg-1024",
  "correlationId": "request-81",
  "payload": {
    "room": "engineering",
    "text": "Hello"
  }
}
~~~

The server must parse the envelope, validate the type and payload, check access rights to the room, and then choose the session that receives the result. The WebSocket protocol does not understand the type, room, or correlationId fields on its own.

## 7. Spring's High-Level Messaging Model

When using STOMP over WebSocket, Spring adds a messaging layer between the frame and the business code.

The foundational abstractions in spring-messaging:

- **Message:** represents a message consisting of a payload and headers.
- **MessageHandler:** the contract for handling a message.
- **MessageChannel:** the contract for sending a message, which decouples the producer from the consumer.
- **SubscribableChannel:** a MessageChannel with registered MessageHandlers.
- **ExecutorSubscribableChannel:** a SubscribableChannel that uses an Executor to dispatch messages.

When a client sends a STOMP frame, Spring decodes the frame into a Spring Message and passes it through clientInboundChannel. The destination prefix decides whether the message goes to a controller or the broker.

The high-level messaging model lets the application focus on the payload and the business logic. Spring handles destination mapping, calling controllers, managing subscriptions, and sending messages back to the WebSocket session.

## 8. What Is STOMP and How Does STOMP Run on WebSocket?

STOMP is a text-oriented, frame-based messaging protocol. It defines common commands such as:

| Command | Purpose |
| --- | --- |
| CONNECT | Starts a STOMP session |
| CONNECTED | The server confirms the STOMP session |
| SEND | Sends a message to a destination |
| SUBSCRIBE | Registers to receive messages from a destination |
| UNSUBSCRIBE | Cancels a subscription |
| MESSAGE | The broker sends a message to a subscriber |
| RECEIPT | Acknowledges a frame when the broker supports it |
| ACK / NACK | Acknowledges or rejects a message when the broker supports it |
| DISCONNECT | Closes the STOMP session |

A STOMP frame has a command, headers, a blank separator line, and a body. Example of a client sending:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"text":"Hello"}
^@
~~~

A subscriber registers:

~~~text
SUBSCRIBE
id:chat-sub-1
destination:/topic/chat

^@
~~~

WebSocket is the transport; STOMP is the messaging protocol that sits on top of it. A WebSocket connection can carry STOMP frames after the client and server negotiate the sub-protocol in the handshake. If you do not use STOMP, the client and server must agree on frame conventions themselves, as in the plain WebSocketHandler section.

## 9. Configuring the STOMP Endpoint in Spring

Use @EnableWebSocketMessageBroker and WebSocketMessageBrokerConfigurer:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The two kinds of destination prefix have different roles:

- /app: messages sent to this prefix are routed to the @MessageMapping methods in controllers.
- /topic and /queue: messages sent to these prefixes are passed to the broker for delivery to the matching subscriptions.

With the built-in simple broker, /topic and /queue are just naming conventions to distinguish pub-sub from point-to-point; they have no mandatory special meaning in the STOMP specification. When using an external broker, check that broker's destination rules.

## 10. The Message Flow through the Controller and the Broker

Suppose the client connects to /ws, subscribes to /topic/chat, and sends a message to /app/chat.send.

~~~mermaid
flowchart TD
    C[WebSocket client] -->|STOMP CONNECT / SEND / SUBSCRIBE| I[WebSocket + STOMP decoder]
    I --> IN[clientInboundChannel]
    IN -->|/app/**| CTRL[@MessageMapping controller]
    IN -->|/topic/** or /queue/**| B[Message broker]
    CTRL -->|return value or SimpMessagingTemplate| BC[brokerChannel]
    BC --> B
    B --> OUT[clientOutboundChannel]
    OUT --> E[STOMP encoder]
    E -->|MESSAGE frame| C
~~~

The specific steps:

1. The client connects to the handshake URL /ws.
2. The client sends a STOMP CONNECT; the server returns CONNECTED.
3. The client sends a SUBSCRIBE to /topic/chat. The broker stores the subscription for that session.
4. The client sends a SEND to /app/chat.send.
5. Spring converts the frame into a Message and puts it into clientInboundChannel.
6. The /app prefix causes the message to be routed to the @MessageMapping method after the prefix is removed.
7. The controller processes the payload and returns a result or sends a message through SimpMessagingTemplate.
8. The message is passed through brokerChannel to the broker.
9. The broker finds the matching subscriptions and sends the MESSAGE frame through clientOutboundChannel to each WebSocket session.

The three channels commonly mentioned:

| Channel | Direction and purpose |
| --- | --- |
| clientInboundChannel | Receives Spring Messages decoded from the WebSocket client |
| brokerChannel | Sends messages from server-side code to the broker |
| clientOutboundChannel | Sends messages from the broker back to the WebSocket client |

## 11. Handling Messages with @MessageMapping

A controller handles destinations belonging to the application prefix with @MessageMapping:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        return message;
    }
}

record ChatMessage(String sender, String text) {
}
~~~

If the client sends to /app/chat.send, Spring calls the send method. The return value is converted into a Spring Message and sent to /topic/chat thanks to @SendTo.

In a real application, take the sender's identity from the authenticated Principal instead of trusting the sender field sent by the client. The controller should validate the payload, limit the content length, and check the right to join the room before broadcasting.

You can use @MessageExceptionHandler to convert business errors into an appropriate response or configure error handling at the messaging layer. Do not send stack traces or sensitive information to the client.

## 12. Sending Messages from a Service with SimpMessagingTemplate

Not every message originates from @MessageMapping. A service, scheduled task, or HTTP controller can also send to the broker:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(String text) {
        messagingTemplate.convertAndSend(
            "/topic/notifications",
            new Notification(text)
        );
    }
}

public record Notification(String text) {
}
~~~

convertAndSend converts the payload into a Spring Message and sends it into brokerChannel. The broker distributes the message to the clients that have subscribed to the corresponding destination.

To send privately to a user, you can use convertAndSendToUser with a user name authenticated by Spring Security and a user destination, for example /queue/notifications. Do not take the user name from the client payload and treat it as a trusted identity.

## 13. Simple Broker and External STOMP Broker Relay

Spring can use the built-in broker or forward to an external STOMP broker.

| Criterion | Simple broker | Broker relay |
| --- | --- | --- |
| Deployment | In-memory inside the Spring application | Spring forwards frames to an external STOMP broker |
| Subscription | Stored in the memory of the application instance | Managed by the external broker |
| STOMP features | Supports only a subset of commands | Depends on the broker, usually more complete |
| Clustering | Not suitable for sharing subscriptions across multiple nodes | Can use a broker cluster depending on the product |
| Operations | Easy to configure for development and testing | Requires installing, securing, monitoring, and operating the broker |
| Scale | Suits small loads or simple applications | Suits large message distribution needs and multiple nodes |

The simple broker does not fully support features such as ACK and RECEIPT and is not suitable for clustering. When you need a full broker, you can configure a relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue");
}
~~~

The broker relay maintains a TCP connection to the external STOMP broker, forwards messages from Spring up to the broker, and forwards messages from the broker down to the WebSocket clients. The application must configure the host, port, credentials, virtual host, heartbeat, and connection recovery appropriate to the specific broker.

Do not confuse the STOMP broker relay with Spring sending JMS messages. This is a STOMP integration over TCP; to use RabbitMQ or ActiveMQ, you need to enable the corresponding STOMP plugin/protocol endpoint on the broker.

## 14. SockJS Fallback and Client Compatibility

Some network environments or browsers may not support WebSocket properly. Spring can enable the SockJS fallback on the STOMP endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS();
}
~~~

SockJS emulates the WebSocket API and can use alternative transports such as XHR streaming or long polling when WebSocket is unavailable. The client must use a SockJS client together with a compatible STOMP client.

If all modern clients support WebSocket and the infrastructure allows Upgrade, you can use WebSocket directly to reduce the fallback transport layer. SockJS does not replace STOMP; one provides a fallback transport, the other provides a messaging protocol.

## 15. Handshake, Authentication, and Authorization

WebSocket starts with an HTTP handshake, so the application needs to handle authentication and origin from the moment of connection.

- Use Spring Security or the existing HTTP authentication mechanism to determine the Principal.
- Restrict allowed origins to trusted frontend domains.
- Use a HandshakeInterceptor when you need to transfer HTTP session attributes into the WebSocketSession.
- With STOMP, check SEND and SUBSCRIBE permissions per destination on the inbound channel.
- Do not trust a user ID, role, or tenant ID that the client sends itself in the JSON payload or STOMP header.
- Limit message size, number of connections, send rate, and number of subscriptions per user.
- Use WSS in the production environment to encrypt traffic.
- Close the session when the token expires or access rights are revoked according to the system's policy.

In Spring STOMP support, the login/passcode in STOMP CONNECT is not an alternative source of user authentication to HTTP authentication; that information may be ignored or overridden depending on the server configuration. Rely on the authenticated Principal and configure Spring Security message authorization.

## 16. Observability, Errors, and the Session Lifecycle

With a raw handler, the callbacks afterConnectionEstablished, handleTransportError, and afterConnectionClosed are the main points for logging and managing session state. You should log the session ID, the authenticated user ID, the close status, and the error type, but avoid logging sensitive payloads.

With STOMP, Spring publishes application events related to connecting, subscribing, and disconnecting, such as SessionConnectEvent, SessionConnectedEvent, SessionSubscribeEvent, and SessionDisconnectEvent. You can use listeners for those events to update presence, connection counts, or clean up state.

Operational notes:

- A user can open multiple tabs, meaning multiple WebSocket sessions at the same time.
- A client can lose the network without sending DISCONNECT; heartbeat and timeout are needed to clean up sessions.
- A server restart drops the current connections; clients need to reconnect and subscribe again.
- The broker relay needs to monitor the connection to the broker and the bidirectional heartbeat.
- A slow client can cause the outbound buffer to grow; set limits and a session-closing policy.
- Do not assume that a message sent successfully means the client has read or finished processing the payload.
- For important messages, you need acknowledgement or to store the business state at an appropriate application/broker layer.

## 17. Preserving Message Order

Spring uses executor-backed channels for some of the paths that send to clients. If many messages are published quickly, the tasks can run on multiple threads and the order in which the client receives them does not necessarily match the publish order.

If the application needs to preserve the publish order for each WebSocket session, you can configure:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

This configuration can reduce throughput because messages going to the same session are processed more sequentially. Enable it only when the business logic really depends on order. If you need ordering per room or aggregate, consider partitioning by a business key.

## 18. Choosing a Raw Handler or STOMP Messaging

Choose a plain WebSocketHandler when:

- The client and server use a specialized protocol that has been clearly defined.
- You need direct control over binary frames or your own envelope.
- You do not need broker destinations, standard subscriptions, or controller mapping.
- The development team is ready to build the session registry, routing, backpressure, and lifecycle itself.

Choose STOMP messaging when:

- Many clients need to subscribe/publish to destinations.
- You need to route messages into @MessageMapping controllers.
- You want to use SimpMessagingTemplate from a service or an HTTP controller.
- You need user destinations and a broker relay.
- You want to rely on Spring's Message, MessageChannel, and MessageHandler abstractions.

Do not choose a raw handler merely because the current payload is JSON; STOMP can also carry a JSON body. Conversely, you do not need to use STOMP if the application only needs its own request/event protocol and already has an appropriate routing mechanism.

## 19. Common Mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Handshake returns 404 | The endpoint is not mapped or the client URL is wrong | Check addHandler/addEndpoint and the context path |
| Handshake rejected | The origin is not in the allow-list or authentication failed | Check allowed origins and the security filter |
| WebSocket connects but @MessageMapping does not run | The client sends SEND with the wrong destination prefix or lacks a STOMP frame | Check CONNECT, SEND, and the /app prefix |
| Client does not receive the broadcast | Did not SUBSCRIBE to the right destination or the broker prefix is wrong | Check SUBSCRIBE and /topic, /queue |
| Sending directly through the session causes a concurrent send error | Multiple threads send on the same WebSocketSession | Serialize sends or use ConcurrentWebSocketSessionDecorator |
| The session registry grows forever | No cleanup when the connection closes or on a transport error | Handle afterConnectionClosed and connection errors |
| Simple broker does not work across multiple nodes | Subscriptions are only kept in each instance's memory | Use a broker relay or a shared broker solution |
| Client receives messages out of order | The outbound channel processes on multiple threads | Consider setPreservePublishOrder(true) |
| Client sends an oversized payload | No message-size limit set | Limit text/binary size and validate the payload |
| Client forges the user or tenant | Trusting identifying data in the payload/header sent by the client | Use the Principal and server-side authorization |
| Connection dropped when the proxy is idle | The proxy/load balancer does not keep the connection or there is no heartbeat | Configure an appropriate proxy timeout and heartbeat |
| Server sends a message but the client has not processed it | Sending a frame is not a business acknowledgement | Design an ACK/receipt or a separate processing status if needed |

## 20. Production Deployment Checklist

- [ ] Clearly choose a raw WebSocket protocol or STOMP messaging.
- [ ] Declare the endpoint and the URL mapping accurately.
- [ ] Authenticate the handshake and restrict allowed origins.
- [ ] Define the message schema, version, and payload limits.
- [ ] If using a raw handler, build routing, subscriptions, a session registry, and cleanup.
- [ ] Serialize sends on the same WebSocketSession.
- [ ] If using STOMP, clearly configure the application prefix and the broker destination prefix.
- [ ] Choose the simple broker or an external broker relay according to clustering requirements and STOMP features.
- [ ] Configure authorization for SEND and SUBSCRIBE.
- [ ] Configure heartbeat, reconnect, and resubscribe.
- [ ] Set limits on the outbound buffer and message size.
- [ ] Test multiple tabs, slow clients, network loss, server restart, and broker restart.
- [ ] Monitor the number of sessions, subscriptions, outbound queue, send latency, error rate, and reconnects.

## 21. References

- [Spring Framework 7.0 — WebSockets overview](https://docs.spring.io/spring-framework/reference/7.0/web/websocket.html)
- [Spring Framework 7.0 — WebSocket API and WebSocketHandler](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0 — Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework 7.0 — Flow of Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/message-flow.html)
- [Spring Framework 7.0 — Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 7.0 — External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0 — Sending Messages](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-send.html)
- [Spring Framework 7.0 — ConcurrentWebSocketSessionDecorator API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/handler/ConcurrentWebSocketSessionDecorator.html)
- [Spring Framework 7.0 — WebSocketHandler API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/WebSocketHandler.html)
- [Spring Framework 7.0 — WebSocketSession API](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
