# WebSocket and Bidirectional Communication over a Long-Lived Connection

## 1. What Problem Does WebSocket Solve?

WebSocket is a protocol that allows a client and a server to exchange data in both directions over a single, long-lived TCP connection. Once the connection is established, either side can proactively send messages without creating a new HTTP request for each exchange.

With ordinary HTTP request/response, the client sends a request and the server returns a response. If the server has new data after the response has ended, the client has to send another request, poll, or use a streaming technique. WebSocket suits applications that need fast, frequent updates and that have a data flow going from the client to the server as well as from the server to the client.

Some use cases:

- Chat, online collaboration, and user presence.
- Price boards, dashboards, order tracking, or near-real-time task status.
- Multiplayer games and interactive applications.
- Device control or monitoring that needs continuous feedback.
- User interfaces that need to receive a notification as soon as the server has a new event.

WebSocket is not the default choice for every API. If the client only needs to read data occasionally, REST, Server-Sent Events, or polling may be easier to operate. A long-lived connection also holds a socket, memory, and state on the server for as long as the client stays connected.

## 2. The HTTP Upgrade Handshake and the Connection Lifecycle

WebSocket starts with an HTTP request that carries headers requesting a protocol upgrade:

~~~http
GET /ws/echo HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: <random-key>
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

If the server accepts, it returns HTTP 101 Switching Protocols along with headers confirming the WebSocket handshake. After that, the TCP connection is kept open and both sides exchange WebSocket frames over the same socket.

~~~text
Browser / Java client                  Spring application
        |                                      |
        |------ HTTP Upgrade request --------->|
        |<----- 101 Switching Protocols -------|
        |                                      |
        |<========= WebSocket connection =====>|
        |                                      |
        |------ Text / Binary message -------->|
        |<----- Text / Binary message ---------|
        |------ Text / Binary message -------->|
        |<----- Server push -------------------|
        |                                      |
        |------ Close frame ------------------>|
        |<----- Close frame -------------------|
        |                                      |
        |---------- TCP socket closed ---------|
~~~

Common states:

1. **CONNECTING:** the client is performing the handshake.
2. **OPEN:** the handshake succeeded; both sides can send and receive messages.
3. **CLOSING:** one side has started the WebSocket closing handshake.
4. **CLOSED:** the connection has been closed or could not be established.

The handshake happens only at the initial connection. Subsequent messages are not independent HTTP requests and are not routed by an HTTP method such as GET/POST.

### 2.1. Frames and Messages

WebSocket defines the following main frame types:

- **Text:** UTF-8 text data; typically JSON or a text protocol such as STOMP.
- **Binary:** binary data such as protobuf, images, or application data depending on the format.
- **Ping/Pong:** control frames for checking the connection and for keepalive.
- **Close:** starts or answers the connection-closing procedure.

A message can be split into multiple frames (fragmentation). WebSocket libraries usually assemble the frames into a complete message before passing it to the handler. Applications should set a message size limit and should not assume the payload can be arbitrarily large.

Ping/Pong belongs to the protocol layer; it is not a business message. The browser WebSocket API does not provide a JavaScript function to send a control Ping yourself; the runtime handles control frames according to the protocol. If the application needs a business-level heartbeat, it can define its own message or use the STOMP heartbeat.

### 2.2. WebSocket Does Not Define Business Structure

WebSocket only defines how frames are transmitted; it does not specify what the message content means. The client and server must agree on a payload format, for example:

~~~json
{
  "type": "order-status",
  "messageId": "m-1042",
  "sentAt": "2026-11-07T10:00:00Z",
  "payload": {
    "orderId": "O-1001",
    "status": "SHIPPED"
  }
}
~~~

The application needs to define on its own:

- The valid message types and the payload schema.
- How to authenticate, authorize, and validate data.
- Correlation ID, message ID, and sequence number if needed.
- Rules for retry, duplicates, acknowledgment, and handling malformed messages.
- The protocol version when the client and server are deployed independently.

Do not treat the successful sending of a WebSocket frame as proof that, at the business level, the receiving side has processed or stored the data successfully.

## 3. WebSocket in Spring Framework

Spring Framework supports WebSocket on the Servlet stack through the `spring-websocket` module. There are two common programming approaches:

| Approach | When it fits | Main components |
|---|---|---|
| Raw WebSocket | The application defines its own message format and routing | `WebSocketHandler`, `TextWebSocketHandler`, `WebSocketSession` |
| STOMP over WebSocket | Need publish/subscribe, destinations, controllers, and a broker | `@EnableWebSocketMessageBroker`, `@MessageMapping`, `SimpMessagingTemplate` |

Both approaches use WebSocket as the transport. STOMP is an application-layer protocol that runs on top of WebSocket, providing message structure, commands, destinations, and subscriptions.

The Spring WebSocket Servlet stack and Spring WebFlux WebSocket are two different APIs. WebFlux uses the reactive Mono/Flux style; the examples in this lesson use Spring WebSocket on the Servlet stack with Java 17 and Spring Framework 6.2.

## 4. Raw WebSocket with WebSocketHandler

Spring provides the `WebSocketHandler` interface. For text messages, you usually extend `TextWebSocketHandler`; for binary messages, use `BinaryWebSocketHandler`.

A handler receives the following main callbacks:

| Callback | When |
|---|---|
| `afterConnectionEstablished(session)` | The handshake succeeded and the session is open |
| `handleMessage(session, message)` | A message is received from the client |
| `handleTransportError(session, exception)` | A transport error or a processing error at the WebSocket layer |
| `afterConnectionClosed(session, status)` | The connection has closed |
| `supportsPartialMessages()` | Indicates whether the handler handles fragmented messages piece by piece |

Example of an echo handler:

~~~java
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        String payload = message.getPayload();
        session.sendMessage(new TextMessage("echo:" + payload));
    }
}
~~~

`WebSocketSession` represents a specific connection. It provides the session ID, URI, handshake headers, attributes, Principal, local/remote addresses, the open/closed state, and the method for sending messages.

A handler is usually a Spring singleton bean. Do not store data belonging to one client in a single field shared by all clients. If you need to manage multiple sessions, use a thread-safe collection keyed by session ID and remove the session when the connection closes.

## 5. Registering Endpoints with @EnableWebSocket

Spring lets you map a handler to a URL using `@EnableWebSocket` and `WebSocketConfigurer`.

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler echoHandler;

    public WebSocketConfiguration(EchoHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins("https://app.example.com");
    }
}

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        session.sendMessage(
            new TextMessage("echo:" + message.getPayload())
        );
    }
}
~~~

The application needs to run in an HTTP Servlet environment that supports WebSocket, for example Tomcat, Jetty, or Undertow compatible with the Spring version. The WebSocket configuration must be registered in the web application context that handles the handshake.

`@EnableWebSocketMessageBroker` is not needed if you only use a raw handler. That annotation is for configuring the STOMP message broker, covered in a later section.

### 5.1. HandshakeInterceptor and Session Attributes

`HandshakeInterceptor` runs before and after the HTTP handshake. It can:

- Reject the connection if the request does not meet the conditions.
- Read information from the already-authenticated request.
- Put necessary values into the attributes of the `WebSocketSession`.
- Record metadata for logging or connection tracking.

Example of using a built-in interceptor to copy HTTP session attributes:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new HttpSessionHandshakeInterceptor())
        .setAllowedOrigins("https://app.example.com");
~~~

The attributes are passed into `WebSocketSession.getAttributes()`. If you need deeper handshake customization, you can implement `HandshakeInterceptor` or provide a `DefaultHandshakeHandler`.

`HandshakeInterceptor` does not replace authentication. It only checks the request and passes metadata; authentication should be performed by Spring Security or an appropriate HTTP authentication mechanism before the connection is upgraded.

## 6. A Browser Client Using the WebSocket API

Browsers have a standard WebSocket API:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws/echo");

socket.addEventListener("open", () => {
    console.log("connected");
    socket.send("hello from browser");
});

socket.addEventListener("message", (event) => {
    console.log("server:", event.data);
});

socket.addEventListener("error", () => {
    console.error("websocket error");
});

socket.addEventListener("close", (event) => {
    console.log("closed:", event.code, event.reason, event.wasClean);
});
~~~

A few points to note:

- Use `wss://` when the web page is served over HTTPS.
- Only call `send()` after `readyState === WebSocket.OPEN`.
- The payload can be a string, Blob, or ArrayBuffer depending on the format.
- The `message` event receives data from the server; the server can send a message at any time while the socket is open.
- The browser API has no built-in backpressure. The application needs to limit its send rate and avoid queuing unbounded data on the client side.

If the client needs to reconnect on its own, use exponential backoff with jitter, limit the number of attempts or the retry time, and restore subscriptions/state after reconnecting. Do not reconnect continuously at very short intervals when the server is failing.

## 7. Sending Messages from the Server to the Client

An important benefit of WebSocket is that the server can proactively send messages after the handshake, without waiting for a new request. For example, the server sends progress updates, notifications, or the results of background processing.

A handler can store sessions by ID:

~~~java
public class NotificationHandler extends TextWebSocketHandler {

    private final Map<String, WebSocketSession> sessions =
        new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        WebSocketSession safeSession =
            new ConcurrentWebSocketSessionDecorator(
                session, 10_000, 512 * 1024
            );

        sessions.put(session.getId(), safeSession);
    }

    public void notifyClient(String sessionId, String text)
            throws IOException {

        WebSocketSession session = sessions.get(sessionId);
        if (session != null && session.isOpen()) {
            session.sendMessage(new TextMessage(text));
        }
    }

    @Override
    public void afterConnectionClosed(
            WebSocketSession session,
            CloseStatus status) {

        sessions.remove(session.getId());
    }
}
~~~

In a real application, you also need to handle send errors, remove the session on a transport error, determine which users are allowed to receive a notification, and limit the number of sessions. You can use the `Principal` from the `WebSocketSession` to associate a connection with an authenticated user.

Do not send a notification to every session just because you know the session ID. The session ID is a transport identifier, not an authorization mechanism.

## 8. Synchronization When Multiple Threads Send

A standard WebSocket session does not allow multiple threads to write concurrently. If multiple threads call `sendMessage()` on the same session, frames may be corrupted or sending may be unsafe.

When using a raw `WebSocketHandler`, serialize the send operations. Spring provides `ConcurrentWebSocketSessionDecorator` to wrap a session, lock the send operation, and manage time/buffer limits.

~~~java
WebSocketSession safeSession =
    new ConcurrentWebSocketSessionDecorator(
        session,
        10_000,       // send time limit, milliseconds
        512 * 1024    // maximum buffered bytes
    );
~~~

If sending is slower than the rate at which messages are produced, the buffer will grow. Set finite limits and decide how to handle a slow client: reduce the update frequency, merge into the latest state, drop unimportant messages, or close the session when a threshold is exceeded.

Spring's STOMP message broker configuration already handles serializing sends to each session. However, you still need to configure the send time limit and the send buffer size limit to prevent one slow client from accumulating memory.

## 9. STOMP over WebSocket

WebSocket transmits text/binary frames but does not specify the meaning of the payload. STOMP adds commands and destinations so that clients can send, subscribe, and receive messages following a messaging model.

Common STOMP commands:

- `CONNECT`: starts a STOMP session.
- `CONNECTED`: the server acknowledges the STOMP connection.
- `SEND`: sends a message to a destination.
- `SUBSCRIBE`: registers to receive messages from a destination.
- `MESSAGE`: the server sends a message to a subscriber.
- `UNSUBSCRIBE`: cancels a subscription.
- `DISCONNECT`: ends the STOMP session.

A STOMP frame has a command, headers, and a body. Therefore, the application does not need to design all of the routing, subscription, and broadcast rules itself as with raw WebSocket.

### 9.1. Configuring the STOMP Endpoint

Use `@EnableWebSocketMessageBroker`:

~~~java
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

Meaning:

- The client connects over WebSocket to the `/ws` endpoint.
- Messages whose destination begins with `/app` are routed to `@MessageMapping` methods.
- Messages whose destination begins with `/topic` or `/queue` are routed to the simple broker for delivery to subscribers.

With the built-in simple broker, `/topic` and `/queue` are just prefix conventions chosen by the application; they do not automatically carry special semantics at the WebSocket layer. An external broker may define different destinations and semantics.

### 9.2. A Controller That Receives and Broadcasts Messages

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

The client sends to `/app/chat.send`. Spring calls the `send` method, then broadcasts the result to `/topic/chat`. Clients that have subscribed to this destination will receive the message.

If you need to send from a service or a background task, use `SimpMessagingTemplate`:

~~~java
@Service
public class NotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishStatus(OrderStatus status) {
        messagingTemplate.convertAndSend("/topic/orders", status);
    }
}
~~~

You can send to a specific user using a user destination, for example `/user/queue/notifications`. Spring maps this destination to the authenticated user's sessions.

### 9.3. A Browser Client with STOMP.js

STOMP.js is a JavaScript library commonly used for STOMP over WebSocket:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        client.subscribe("/topic/chat", (frame) => {
            console.log("chat:", frame.body);
        });

        client.publish({
            destination: "/app/chat.send",
            body: JSON.stringify({ text: "hello" })
        });
    },

    onStompError: (frame) => {
        console.error("broker error:", frame.headers["message"]);
    }
});

client.activate();
~~~

After a reconnect, the STOMP client needs to subscribe again in `onConnect`. If you use a token or custom authentication, design the handshake/CONNECT interceptor according to the server's authentication mechanism; do not send credentials in the URL query string, because URLs may appear in access logs, proxy logs, or telemetry.

## 10. Simple Broker and External Broker Relay

Spring provides a simple broker that keeps subscriptions and broadcasts messages in the memory of a single application instance. It suits small applications, demos, or cases that do not need an independent broker.

The simple broker has these limitations:

- Subscription state lives in the process's memory.
- It does not automatically share subscriptions across multiple Spring instances.
- It does not provide the full storage, durability, or advanced routing features of a message broker.
- Restarting an instance may lose the current subscription state.

When you need to scale across multiple application instances or use the capabilities of a dedicated broker, configure the STOMP broker relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("web-client")
            .setClientPasscode("replace-with-secret");
}
~~~

The broker relay maintains TCP connections to the broker. There is a system connection for messages from the server application and separate connections acting on behalf of the WebSocket clients. You need to configure credentials, TLS/network policy, connection quotas, and destination permissions according to the broker.

Do not embed real passwords in source code. Use a secret manager or a secure environment configuration.

## 11. SockJS When WebSocket Is Unavailable

Some proxies, firewalls, or load balancers do not forward the `Upgrade` header, or close long-lived connections that have no traffic. SockJS provides an emulation mechanism: it tries WebSocket first, then falls back to HTTP streaming or long polling when needed.

A raw handler can enable SockJS:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .withSockJS();
~~~

With a STOMP endpoint:

~~~java
registry.addEndpoint("/ws")
        .withSockJS();
~~~

The client uses `sockjs-client` instead of using the browser WebSocket API directly. SockJS provides an API close to WebSocket but may use multiple HTTP requests for the streaming/polling transports.

Points to note:

- SockJS does not turn HTTP polling into a real TCP WebSocket connection; it emulates the communication semantics.
- HTTP streaming and polling create additional requests and overhead and require different proxy configuration.
- If the application depends on cookie sessions or sticky sessions, check how the load balancer routes SockJS requests.
- SockJS has a default heartbeat so that proxies do not treat an idle connection as dead; it can be configured as needed.
- Enable the fallback only when the client/proxy environment actually needs it.

## 12. Authentication, Origin, and Authorization

A WebSocket connection still needs authentication and authorization. A successful handshake does not mean the client is allowed to send every message or subscribe to every destination.

Important principles:

1. **Use TLS:** production browsers should connect using `wss://`; this protects both the data and the cookie/token in transit.
2. **Check Origin:** Spring WebSocket by default accepts only same-origin. If the frontend is on a different origin, declare a specific allowlist with `setAllowedOrigins(...)`.
3. **Origin is not authentication:** a non-browser client can set the Origin header itself. You must still authenticate identity and authorize.
4. **Leverage HTTP authentication:** with STOMP, Spring can associate the Principal authenticated at the HTTP handshake with the WebSocket/STOMP session.
5. **Do not trust a user ID from the payload:** use the session's `Principal` to identify the sender; a client must not be able to declare the identity of someone else.
6. **Authorize by message type and destination:** check both SEND and SUBSCRIBE. A client may be allowed to subscribe to `/topic/notifications` but not allowed to publish directly to a system destination.
7. **Protect against CSWSH/CSRF:** if you use cookie-based authentication, check the Origin and configure Spring Security appropriately. With Spring Security STOMP, CONNECT usually needs a CSRF token.
8. **Limit data:** check the schema, length, message rate, and access rights before executing business logic.

For token authentication at STOMP CONNECT, you can register a `ChannelInterceptor` on the inbound channel to authenticate the header and attach the `Principal` using `StompHeaderAccessor.setUser(...)`. The authentication interceptor configuration must run before Spring Security's authorization interceptor.

Raw WebSocket has no STOMP inbound channel. With a raw handler, perform authorization directly in the handler/service and use a trusted Principal or session attributes.

## 13. Heartbeat, Timeout, and Closing the Connection

A WebSocket connection is long-lived, so network state needs to be managed:

- TCP may be cut without the application being notified immediately.
- A reverse proxy may close an idle connection after a period of time.
- The server or browser may sleep, switch networks, or lose connectivity.
- A client may close the tab without sending a final business message.

Commonly used mechanisms:

- **WebSocket Ping/Pong:** protocol-level control frames to check the peer and keep the connection alive.
- **STOMP heartbeat:** the client and server negotiate a heartbeat interval for when there are no messages.
- **SockJS heartbeat:** helps keep the HTTP fallback from being treated as idle by proxies.
- **Application heartbeat:** a business message if the application needs to measure status or synchronize progress.

Set appropriate timeouts at the WebSocket container, reverse proxy, load balancer, and client. A proxy timeout shorter than the heartbeat can cause the connection to be closed even though the application is still working.

When closing the connection, both sides perform a closing handshake. Some common status codes:

| Code | Meaning |
|---|---|
| `1000` | Normal closure |
| `1001` | Endpoint is going away, for example a server shutdown |
| `1002` | Protocol error |
| `1003` | Unsupported type of data received |
| `1008` | Policy violation |
| `1009` | Message too big |
| `1011` | Internal server error |

Do not send the codes reserved for internal states such as `1005` or `1006` in a Close frame. They are used to represent the absence of a close status or an abnormal closure.

## 14. Message Limits, Buffers, and Slow Clients

A slow client may receive data more slowly than the rate at which the server produces messages. If the server keeps adding messages to an unbounded queue, memory grows until it affects the whole system.

You need to configure:

- The maximum size of text and binary messages.
- The input buffer and idle timeout of the WebSocket container.
- The send timeout and the limit on buffered bytes.
- The number of concurrent connections and the message rate limit.
- A bounded queue for asynchronous send tasks.
- A policy for closing the session or dropping messages when the client cannot keep up.

With a raw Spring handler, `ConcurrentWebSocketSessionDecorator` helps synchronize sends and limit time/buffer. With STOMP, configuring `WebSocketTransportRegistration` lets you set `setMessageSizeLimit`, `setSendTimeLimit`, and `setSendBufferSizeLimit`.

Do not keep the entire event history in session memory. If a client needs old data after a reconnect, store the state/events in a database or broker and provide a resynchronization mechanism through a dedicated API.

## 15. Scaling Multiple Instances and Reverse Proxies

WebSocket is a long-lived TCP connection, so each connected client is usually tied to one application instance for the lifetime of the socket. When running multiple instances:

- The load balancer must support WebSocket Upgrade and keep long-lived connections.
- The proxy needs to forward the `Upgrade` and `Connection` headers.
- The proxy's idle timeout must be compatible with the heartbeat.
- Sticky sessions may be necessary for local state or SockJS HTTP transports.
- Broadcasting across instances needs a shared broker or pub/sub.
- When an instance restarts, clients must reconnect and restore subscriptions/state.

With raw WebSocket, a session map in one JVM only sees the sessions of that instance. If one instance needs to send a message to a client connected to another instance, there must be routing/a broker or an inter-instance event distribution layer.

With STOMP, an external broker relay lets multiple Spring instances share broker destinations. However, you need to design connection quotas, routing, failover, authorization, and observability separately.

## 16. A Java 17+ Example Testing TextWebSocketHandler

This example tests the callback logic of a Spring handler using a fake WebSocketSession that records the messages sent. It does not open a TCP socket or perform an HTTP Upgrade; the endpoint registration and the browser client were illustrated in the earlier sections.

**Project structure**

~~~text
websocket-handler-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          WebSocketHandlerDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>websocket-handler-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-websocket</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/WebSocketHandlerDemo.java**

~~~java
package demo;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.security.Principal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketExtension;
import org.springframework.web.socket.WebSocketMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class WebSocketHandlerDemo {

    public static void main(String[] args) throws Exception {
        RecordingSession session = new RecordingSession();
        EchoHandler handler = new EchoHandler();

        handler.afterConnectionEstablished(session);
        handler.handleMessage(session, new TextMessage("hello"));
        handler.handleMessage(session, new TextMessage("spring"));

        System.out.println("messagesSent=" + session.messages().size());
        System.out.println(
            "firstReply=" + ((TextMessage) session.messages().get(0)).getPayload()
        );
        System.out.println(
            "secondReply=" + ((TextMessage) session.messages().get(1)).getPayload()
        );

        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
    }

    static class EchoHandler extends TextWebSocketHandler {

        @Override
        protected void handleTextMessage(
                WebSocketSession session,
                TextMessage message) throws IOException {

            String payload = message.getPayload().trim();
            if (!payload.isEmpty()) {
                session.sendMessage(new TextMessage("echo:" + payload));
            }
        }
    }

    static class RecordingSession implements WebSocketSession {
        private final List<WebSocketMessage<?>> messages = new ArrayList<>();
        private final Map<String, Object> attributes = new HashMap<>();
        private boolean open = true;
        private int textMessageSizeLimit = 64 * 1024;
        private int binaryMessageSizeLimit = 64 * 1024;

        @Override public String getId() { return "demo-session"; }
        @Override public URI getUri() {
            return URI.create("ws://localhost/echo");
        }
        @Override public HttpHeaders getHandshakeHeaders() {
            return new HttpHeaders();
        }
        @Override public Map<String, Object> getAttributes() {
            return attributes;
        }
        @Override public Principal getPrincipal() { return null; }
        @Override public InetSocketAddress getLocalAddress() { return null; }
        @Override public InetSocketAddress getRemoteAddress() { return null; }
        @Override public String getAcceptedProtocol() { return null; }
        @Override public List<WebSocketExtension> getExtensions() {
            return List.of();
        }

        @Override
        public void sendMessage(WebSocketMessage<?> message) {
            if (!open) {
                throw new IllegalStateException("Session is closed");
            }
            messages.add(message);
        }

        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
        @Override public void close(CloseStatus status) { open = false; }

        @Override
        public int getTextMessageSizeLimit() {
            return textMessageSizeLimit;
        }

        @Override
        public void setTextMessageSizeLimit(int messageSizeLimit) {
            this.textMessageSizeLimit = messageSizeLimit;
        }

        @Override
        public int getBinaryMessageSizeLimit() {
            return binaryMessageSizeLimit;
        }

        @Override
        public void setBinaryMessageSizeLimit(int messageSizeLimit) {
            this.binaryMessageSizeLimit = messageSizeLimit;
        }

        List<WebSocketMessage<?>> messages() {
            return List.copyOf(messages);
        }
    }
}
~~~

Run from the `websocket-handler-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebSocketHandlerDemo
~~~

**Output printed by the program**

~~~text
messagesSent=2
firstReply=echo:hello
secondReply=echo:spring
~~~

The result shows that `TextWebSocketHandler` receives two TextMessages and sends back two TextMessages. The test focuses on the handler callbacks; you additionally need integration tests on a Servlet container and a real WebSocket client to confirm the handshake, proxy, and transport of the deployment environment.

## 17. Common Mistakes

1. **Using WebSocket for every endpoint:** polling or REST may be simpler if updates do not need to be continuous.
2. **Forgetting HTTP Upgrade at the reverse proxy:** the client receives 400/404/502 or the handshake fails even though the handler has been registered.
3. **Confusing raw WebSocket with STOMP:** a raw handler defines its own message protocol; STOMP provides commands, destinations, and subscriptions.
4. **Not checking readyState:** the client calls send before the connection is open or after it has closed.
5. **Sending concurrently on the same session:** you need to serialize sends or use ConcurrentWebSocketSessionDecorator.
6. **Not removing the session on close:** the map holds a stale reference and causes a memory leak.
7. **Relying only on Origin for authentication:** Origin can be forged by a non-browser client; authentication is still needed.
8. **Allowing every origin:** configure a clear allowlist per environment.
9. **Not limiting message size:** large payloads can consume memory and CPU.
10. **Not handling slow clients:** the send buffer keeps growing if there is no limit and timeout.
11. **Having no appropriate heartbeat/timeout:** proxies may close idle connections, or the server may detect a disconnect too late.
12. **Assuming the simple broker is shared across multiple nodes:** the simple broker lives in instance memory; use a broker relay when you need inter-instance distribution.
13. **Not restoring subscriptions after a reconnect:** the STOMP client needs to subscribe again after the connection is re-established.
14. **Trusting identity data in the payload:** take the identity from the authenticated Principal.
15. **Not distinguishing successful sending from successful processing:** if you need business-level acknowledgment, define a separate message/response protocol.

## 18. Pre-Production Checklist

- The WebSocket endpoint has been registered in the Spring context that handles the HTTP handshake.
- The client and server agree on a raw message schema or a STOMP subprotocol.
- TLS, authentication, the Origin allowlist, and authorization have been configured.
- Message size, send buffer, idle timeout, and connection quota have limits.
- Sends to the same session are serialized.
- Slow clients have a clear buffer/drop/close policy.
- Reconnect has backoff and restores subscriptions/state.
- The reverse proxy and load balancer forward Upgrade and support long-lived connections.
- Multiple application instances have an appropriate broker/pub-sub or routing.
- There are metrics for the number of open sessions, handshake failures, transport errors, send timeouts, message rate, and reconnects.
- There are integration tests with the exact servlet container, proxy, and broker that will be used in production.

## 19. Conclusion

WebSocket provides a bidirectional, full-duplex communication channel over a single long-lived TCP connection. HTTP takes part only in the handshake step; after the server returns 101 Switching Protocols, both sides exchange text or binary messages over the same connection until it is closed.

In Spring Framework, a raw `WebSocketHandler` fits when the application wants to define its own message protocol. STOMP over WebSocket fits when you need destinations, publish/subscribe, controllers, and a broker. SockJS provides a fallback when WebSocket is blocked by a proxy or the network environment.

A reliable WebSocket system needs to manage the session lifecycle, send synchronization, authentication, buffer limits, heartbeat, reconnect, and scale-out. Test not only the handler but also the handshake, proxy, and broker in an environment close to production.

## 20. References

- [Spring Framework 6.2 — WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html)
- [Spring Framework 6.2 — WebSocket API](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — SockJS Fallback](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — STOMP Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html)
- [Spring Framework 6.2 — STOMP WebSocket Transport](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/server-config.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)