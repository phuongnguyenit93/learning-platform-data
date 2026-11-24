# The Relationship between the HTTP Handshake, WebSocket, and the Application Protocol

## 1. The Big Picture

A WebSocket connection in a Spring application typically involves three protocol layers with different responsibilities:

1. **The HTTP handshake** initiates the connection. The client sends an HTTP request asking to switch protocols; the server confirms with an appropriate response.
2. **WebSocket** maintains a bidirectional channel over the established TCP connection. The client and server can send frames back and forth without creating an HTTP request for each message.
3. **The application protocol** defines the meaning of the exchanged data. It can be STOMP, JSON following a custom convention, or another format that both sides understand.

WebSocket is a transport protocol. It specifies how to open a connection, close a connection, send text/binary frames, ping/pong, and manage data at the frame layer. It does not specify whether a message means a chat, an order update, a subscription to a topic, or a call to a business operation.

STOMP is an example of an application protocol that runs on top of WebSocket. STOMP adds commands such as CONNECT, SEND, SUBSCRIBE, MESSAGE, and DISCONNECT, along with the destination, content-type, and receipt headers and a body. Spring can decode a STOMP frame into a Spring Message, route it through a MessageChannel, invoke @MessageMapping, and send the result back to the client.

~~~mermaid
flowchart TD
    A[HTTP request: WebSocket handshake] --> B[HTTP 101 Switching Protocols]
    B --> C[WebSocket connection]
    C --> D[WebSocket text/binary frames]
    D --> E[Application protocol: STOMP or custom JSON]
    E --> F[Spring Message and headers]
    F --> G[Controller, broker or application handler]
    G --> H[Outbound application message]
    H --> I[STOMP or custom protocol encoding]
    I --> J[WebSocket frame to client]
~~~

If you understand these three layers clearly, you will know where to fix a bug: a 403 error during the handshake belongs to HTTP/security/origin; not receiving a frame belongs to the WebSocket transport; a destination that is not routed belongs to STOMP or Spring messaging; JSON that cannot be deserialized belongs to the message converter and the application format.

## 2. The HTTP Handshake: Requesting a Switch to WebSocket

### 2.1. Why Does WebSocket Start with HTTP?

In the traditional WebSocket model over HTTP/1.1, the client opens an HTTP request to a registered endpoint, for example /ws. The request carries headers asking to upgrade the connection:

~~~http
GET /ws HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: v12.stomp
Origin: http://localhost:3000
~~~

Important headers:

| Header | Role |
|---|---|
| Upgrade: websocket | Requests switching the protocol to WebSocket |
| Connection: Upgrade | Marks the connection upgrade request |
| Sec-WebSocket-Key | A random value used in the handshake verification process |
| Sec-WebSocket-Version | The WebSocket version the client supports; the common version today is 13 |
| Sec-WebSocket-Protocol | The list of subprotocols the client wants to negotiate, for example v12.stomp |
| Origin | The origin of the web page initiating the connection; the server can use it to check the origin policy |

Sec-WebSocket-Key is not a password, access token, or user credential. It takes part in computing Sec-WebSocket-Accept so that the client can confirm the server performed the handshake correctly.

### 2.2. The Server Returns 101 Switching Protocols

If the server accepts the request and both sides negotiate successfully, the HTTP/1.1 response looks like this:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: v12.stomp
~~~

HTTP status 101 indicates that the server accepts the protocol switch. Sec-WebSocket-Accept is computed from Sec-WebSocket-Key according to the rules of RFC 6455. If a subprotocol is negotiated, the server returns one value that the client proposed and the server accepts.

After this response, the TCP connection continues to be used for WebSocket. Subsequent messages travel as WebSocket frames on the same connection; they are not new HTTP GET/POSTs.

This is the classic HTTP/1.1 handshake. WebSocket over HTTP/2 can use the extended CONNECT mechanism per RFC 8441 when the client/server infrastructure supports it; you should not assume that every proxy or server supports that mechanism.

### 2.3. What Happens If the Handshake Fails?

If the endpoint does not exist, the origin is rejected, the user is not authenticated, or a proxy does not forward the Upgrade request, the server may return an HTTP error response such as 400, 403, or 404 instead of 101.

The proxies and load balancers in front of Spring must support WebSocket connections. With HTTP/1.1, they need to forward the Upgrade/Connection headers and keep the connection open long enough. If a proxy closes the connection because the idle timeout is too short, the WebSocket will be cut even though the Spring application is still running.

When deploying behind a reverse proxy, you need to check:

- Whether the proxy forwards the WebSocket upgrade request.
- Whether TLS terminates at the proxy or at the application.
- Whether the proxy has an idle timeout configured to match the heartbeat/keepalive.
- Whether the load balancer keeps a WebSocket connection on the same backend throughout the connection's lifetime.
- Whether the application handles client-side reconnect after the network or backend is interrupted.

## 3. WebSocket: A Bidirectional Transport Channel

After the handshake, WebSocket maintains a full-duplex channel. The client can send data at any time; the server can also proactively send data to the client without waiting for a new HTTP request.

WebSocket defines two types of data messages:

- **Text message** carries text data, usually UTF-8.
- **Binary message** carries binary data.

WebSocket also has control frames:

- Ping and Pong help check the connection state.
- Close is used to start or answer the closing of the connection.

A message can be split into multiple frames at the transport layer. Applications usually work with the message already reassembled by the WebSocket implementation, rather than handling the frame bytes themselves.

WebSocket does not understand whether the text content is JSON, STOMP, XML, or an arbitrary string. If the server receives a text message such as:

~~~json
{"type":"chat","text":"Hello"}
~~~

then that is just a text payload at the WebSocket layer. The application must have its own rules to parse the type, determine the destination, check permissions, and invoke the handler.

### 3.1. WebSocket Differs from HTTP Request-Response

| HTTP/REST | WebSocket |
|---|---|
| Usually one request and one response per operation | One long-lived connection carries many bidirectional messages |
| The server usually replies when it receives a request | The server can proactively send messages |
| Routing is based on the URL, method, and HTTP headers of each request | The URL is mainly used for the handshake; subsequent messages need an application protocol for routing |
| Suits independent request-response operations | Suits continuous bidirectional interaction and real-time updates |
| Each request usually ends after the response | The connection exists until one side closes it or the network is interrupted |

WebSocket does not replace every HTTP API. An application can use HTTP for login, initial data queries, and CRUD operations; then use WebSocket to receive notifications or exchange events in real time.

### 3.2. Ping/Pong and Heartbeat

WebSocket Ping/Pong are control frames at the transport layer. STOMP has its own heartbeat mechanism, negotiated via the heart-beat header of the CONNECT/CONNECTED frames.

These two mechanisms are not the same:

- WebSocket Ping/Pong checks the liveness of the WebSocket connection.
- The STOMP heartbeat helps both sides detect a halt in exchange at the STOMP layer.
- Proxies/load balancers may have their own idle timeout, so you need to configure an appropriate heartbeat and timeout.

If you use STOMP, you can enable the heartbeat on the STOMP client. Do not treat the heartbeat as a mechanism that guarantees a business message has been processed successfully; it only helps detect the state of the connection.

## 4. The Application Protocol: STOMP or a Custom Format

### 4.1. Why Is an Application Protocol Needed?

WebSocket only provides the ability to transport data. Both sides still need to agree on:

- Which type a message belongs to.
- Which destination a message is sent to.
- How the client registers to receive data.
- The structure of headers and payload.
- How to report errors, acknowledge message receipt, or end the application session.
- Version compatibility rules between the client and server.

There are two common approaches:

**Use an existing protocol**, for example STOMP. The client and server share the same commands, headers, and frame rules. Spring has ready-made decoders, encoders, message routing, a broker, and annotation support.

**Define your own protocol**, for example JSON with the fields type, destination, requestId, and payload. This approach is flexible, but the application has to implement parsing, validation, routing, error handling, versioning, authentication, and compatibility rules itself.

Do not build your own protocol if STOMP already meets the requirements. If you use custom JSON, write down the schema and test compatibility between client/server versions.

### 4.2. What Is STOMP?

STOMP (Simple Text Oriented Messaging Protocol) is a text-oriented messaging protocol. STOMP can run directly over TCP or be used as a subprotocol over WebSocket.

A STOMP frame consists of:

1. A command, for example SEND or SUBSCRIBE.
2. Header lines in key:value form.
3. A blank line separating the headers and the body.
4. A body if the command has content.
5. A NUL character that terminates the frame.

Example of a SEND frame:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"from":"Linh","text":"Hello"}<NUL>
~~~

<NUL> in the example is a notation illustrating the NUL byte that terminates the frame; it is not a character string that the client sends literally.

Some common commands:

| Command | Direction | Meaning |
|---|---|---|
| CONNECT | Client → Server | Starts a STOMP session on an already-open WebSocket connection |
| CONNECTED | Server → Client | Confirms the STOMP session is established |
| SEND | Client → Server | Sends a message to a destination |
| SUBSCRIBE | Client → Server | Registers to receive messages from a destination |
| UNSUBSCRIBE | Client → Server | Cancels a subscription |
| MESSAGE | Server → Client | Sends a message to a subscriber |
| RECEIPT | Server → Client | Acknowledges a frame when the client requests a receipt |
| ERROR | Server → Client | Reports a protocol error or a processing error |
| DISCONNECT | Client → Server | Requests ending the STOMP session |

### 4.3. Subprotocol Negotiation in the Handshake

The client can send Sec-WebSocket-Protocol to propose a subprotocol. With STOMP 1.2, a common value is v12.stomp.

Example:

~~~http
Sec-WebSocket-Protocol: v12.stomp, v11.stomp
~~~

The server chooses a supported version and returns it in the handshake response. This negotiation takes place in the HTTP handshake, before the STOMP CONNECT frame is sent.

You need to distinguish two steps:

- **WebSocket handshake**: opens the transport channel and can negotiate the subprotocol.
- **STOMP CONNECT**: starts the STOMP session on the WebSocket channel that was just opened.

A successful HTTP handshake with status 101 does not yet mean the STOMP session has connected successfully. The client still has to send CONNECT and receive CONNECTED.

## 5. The Three Protocol Layers in a STOMP over WebSocket Session

~~~mermaid
sequenceDiagram
    participant C as Browser/STOMP client
    participant S as Spring WebSocket
    participant M as Spring Messaging
    participant B as Message broker

    C->>S: HTTP GET /ws + Upgrade: websocket
    S-->>C: HTTP 101 Switching Protocols
    C->>S: WebSocket text frame containing STOMP CONNECT
    S->>M: Decode STOMP into a Spring Message
    M->>B: CONNECT / register the session
    B-->>M: STOMP CONNECTED
    M-->>S: Encode STOMP CONNECTED
    S-->>C: WebSocket frame containing CONNECTED
    C->>S: WebSocket frame containing SUBSCRIBE /topic/chat
    S->>M: STOMP SUBSCRIBE
    M->>B: Store the subscription
    C->>S: WebSocket frame containing SEND /app/chat.send
    S->>M: STOMP SEND into a Spring Message
    M->>M: Route to @MessageMapping
    M->>B: Send the result to the brokerChannel
    B-->>M: MESSAGE for the subscriber
    M-->>S: Encode STOMP MESSAGE
    S-->>C: WebSocket frame containing MESSAGE
~~~

The HTTP handshake appears only when the connection is opened. After that, STOMP frames are sent inside WebSocket messages. Spring decodes the frame into a Spring Message, routes it through the internal channels, and then encodes the result into a STOMP frame to send back.

## 6. At Which Layers Does Spring Support WebSocket?

Spring Framework provides two commonly used integration approaches.

### 6.1. The Raw WebSocket API

Use the WebSocket API directly when the application wants to define the message format and the handling on its own.

Main components:

- WebSocketHandler: the contract for handling a WebSocket session.
- TextWebSocketHandler: a utility class for handling text messages.
- BinaryWebSocketHandler: a utility class for handling binary messages.
- WebSocketSession: represents a WebSocket session that has been opened.
- WebSocketConfigurer: registers handlers and endpoint URLs.
- HandshakeInterceptor: intervenes before/after the HTTP handshake.
- DefaultHandshakeHandler: performs handshake, origin, and subprotocol negotiation.

Example of an echo handler:

~~~java
package com.example.websocket;

import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        String response = "Echo: " + message.getPayload();
        session.sendMessage(new TextMessage(response));
    }
}
~~~

Registering the handler:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfig implements WebSocketConfigurer {

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {

        registry.addHandler(new EchoHandler(), "/echo")
            .setAllowedOrigins("http://localhost:3000");
    }
}
~~~

The client connects to ws://localhost:8080/echo and sends a text message. The server returns the Echo string followed by the payload.

This is a raw WebSocket example. The handler defines the text content on its own and has no STOMP commands, destinations, or broker subscriptions by itself.

If you send messages directly through WebSocketSession from multiple threads, you need to synchronize the send operation because the WebSocket session standard does not guarantee that multiple threads can send concurrently and safely. Spring provides ConcurrentWebSocketSessionDecorator to help serialize sending.

### 6.2. STOMP over WebSocket with Spring Messaging

Use STOMP when you need message routing, subscriptions, publish/subscribe, and broker integration.

Main components:

- @EnableWebSocketMessageBroker: enables the STOMP message broker infrastructure.
- WebSocketMessageBrokerConfigurer: configures the endpoint, broker, and transport.
- StompEndpointRegistry: registers the URL the client uses for the handshake.
- MessageBrokerRegistry: configures destination prefixes and the broker.
- @MessageMapping: maps a destination to a controller method.
- @SendTo: specifies the destination to send the result to.
- SimpMessagingTemplate: sends a message from any Spring component.
- ChannelInterceptor: intercepts a Spring Message on the inbound/outbound channel.

With STOMP, Spring is responsible for converting STOMP frames into Spring Messages, routing, converting the payload, and encoding the returned message into a STOMP frame.

## 7. Distinguishing the WebSocket Endpoint from the STOMP Destination

This is an easy point to confuse when configuring Spring.

| Value | Example | Role |
|---|---|---|
| HTTP/WebSocket endpoint | /ws | The URL the client uses to open the connection and perform the handshake |
| Application destination prefix | /app | The prefix that routes a STOMP SEND to a controller |
| Broker destination | /topic/chat | The destination the client SUBSCRIBEs to and where the broker emits MESSAGE |
| @MessageMapping path | /chat.send | The business path appended after the /app prefix |

Example:

- The client opens a connection to ws://localhost:8080/ws.
- The client sends a STOMP SEND to /app/chat.send.
- Spring strips the /app prefix and maps /chat.send to @MessageMapping("/chat.send").
- The controller returns the result to /topic/chat.
- The broker emits MESSAGE to the clients that have SUBSCRIBEd to /topic/chat.

The path /app/chat.send is not an HTTP endpoint and does not perform an HTTP POST. It is a destination in a STOMP frame running inside a WebSocket connection.

## 8. Configuring the STOMP Broker in Spring

Spring Framework 6.2 can enable STOMP through the two modules spring-messaging and spring-websocket.

Basic configuration:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Explanation:

- registerStompEndpoints() registers /ws as the handshake endpoint for WebSocket/STOMP clients.
- setAllowedOrigins() allows web pages with the origin http://localhost:3000 to connect. When deploying, replace it with the actual approved origins.
- setApplicationDestinationPrefixes("/app") routes messages sent to destinations beginning with /app to @MessageMapping methods.
- enableSimpleBroker("/topic", "/queue") enables the in-memory simple broker to store subscriptions and broadcast messages.

In the built-in simple broker, /topic and /queue are mainly naming conventions to distinguish the publish/subscribe and point-to-point styles. They are not mandatory STOMP syntax. When using an external broker, check that broker's destination rules.

## 9. The Message Flow in Spring STOMP

When a client sends a STOMP frame into a WebSocket connection, Spring processes it using the following general flow:

1. The WebSocket transport receives the frame and passes the payload to the STOMP subprotocol handler.
2. The STOMP decoder converts the frame into a Spring Message consisting of headers and a payload.
3. The Message is sent to clientInboundChannel.
4. The destination prefix decides whether the message goes to @MessageMapping or to the broker.
5. If a controller handles it, the result is sent to brokerChannel.
6. The broker finds the matching subscribers.
7. The message is sent to clientOutboundChannel.
8. The STOMP encoder creates the MESSAGE frame and the WebSocket transport sends the frame to the client.

Three commonly seen internal channels:

| Channel | Direction | Responsibility |
|---|---|---|
| clientInboundChannel | Client → Spring | Passes messages received from the WebSocket client into processing |
| brokerChannel | Application → Broker | Passes messages from server code to the broker |
| clientOutboundChannel | Spring → Client | Passes messages that need to be sent to the WebSocket client |

You can configure a simple broker inside the application or use a broker relay to forward to an external STOMP broker such as RabbitMQ with the STOMP plugin or a broker that supports STOMP.

The simple broker suits small applications or demos; subscriptions are kept in the memory of each application instance. When running multiple replicas, the simple broker on one node does not automatically share subscriptions with another node.

The broker relay opens TCP connections from Spring to an external broker to manage subscriptions and broadcast. Clients still connect over WebSocket to the Spring application; the broker relay is an internal connection between the application and the message broker.

## 10. A Complete Example: Spring Boot, Java 17, and STOMP

This example creates a chat endpoint. The browser connects over WebSocket to /ws, the STOMP client subscribes to /topic/chat, sends a message to /app/chat.send, and receives the message that the server broadcasts back through the broker.

The example uses Java 17, Spring Boot 3.4.x, and Spring Framework 6.2.x. When choosing a deployment version, use a Spring Framework patch with security updates; CVE-2025-41254, related to STOMP over WebSocket, has been fixed since Spring Framework 6.2.12.

### 10.1. Project Structure

~~~text
spring-websocket-stomp-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/websocket/
        │   ├── WebSocketDemoApplication.java
        │   ├── StompWebSocketConfig.java
        │   ├── ChatController.java
        │   └── ChatMessage.java
        └── resources/
            └── application.properties
~~~

### 10.2. Maven Dependencies

Create pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.12</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-websocket-stomp-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-boot-starter-web provides the web runtime; spring-boot-starter-websocket provides the WebSocket and messaging components. Spring Boot dependency management selects compatible versions.

### 10.3. The Bootstrap Class

Create WebSocketDemoApplication.java:

~~~java
package com.example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
~~~

### 10.4. Endpoint and Broker Configuration

Create StompWebSocketConfig.java:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The origin address here assumes the frontend page runs at localhost:3000. If the frontend page is served from the same origin as Spring, you can keep the default same-origin policy instead of opening up additional origins.

### 10.5. The Chat Payload

Create ChatMessage.java:

~~~java
package com.example.websocket;

public record ChatMessage(String from, String text) {
}
~~~

A Java 17 record representing the chat payload, consisting of the sender's name and the content. Spring uses a message converter to convert the JSON body into a ChatMessage.

### 10.6. The Controller Handling STOMP SEND

Create ChatController.java:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

When it receives a STOMP SEND to /app/chat.send, Spring calls handle(). The return value is sent to /topic/chat. The broker broadcasts the message to every client that has SUBSCRIBEd to that destination.

### 10.7. Application Configuration

Create application.properties:

~~~properties
spring.application.name=spring-websocket-stomp-demo
server.port=8080
~~~

### 10.8. Running the Application

From the project directory:

~~~bash
mvn spring-boot:run
~~~

The application listens for HTTP on port 8080 and registers the WebSocket/STOMP endpoint /ws.

### 10.9. Connecting from the Browser with STOMP.js

In the JavaScript frontend, install the library:

~~~bash
npm install @stomp/stompjs
~~~

Example client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        console.log("STOMP connected");

        client.subscribe("/topic/chat", (frame) => {
            const message = JSON.parse(frame.body);
            console.log("received:", message);
        });

        client.publish({
            destination: "/app/chat.send",
            headers: {
                "content-type": "application/json"
            },
            body: JSON.stringify({
                from: "Linh",
                text: "Hello from WebSocket"
            })
        });
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers["message"]);
        console.error(frame.body);
    },

    onWebSocketError: (event) => {
        console.error("WebSocket transport error:", event);
    }
});

client.activate();
~~~

The client performs these steps:

1. Opens a WebSocket to ws://localhost:8080/ws.
2. Negotiates the STOMP subprotocol in the handshake if the client and server support it.
3. Sends a STOMP CONNECT and waits for CONNECTED.
4. In onConnect, sends a SUBSCRIBE to /topic/chat.
5. Sends a SEND to /app/chat.send with a JSON payload.
6. Receives MESSAGE from /topic/chat through the subscription callback.

If there are multiple browser tabs or multiple connected clients, each client that subscribes to /topic/chat will receive the message the controller emits to that destination.

When deploying over HTTPS, use wss:// instead of ws://. Do not use a ws:// address from an HTTPS page, because browsers usually block mixed content.

## 11. HandshakeInterceptor and HandshakeHandler

### 11.1. HandshakeInterceptor

HandshakeInterceptor allows intervention before and after the HTTP handshake.

Use cases:

- Check request information before allowing the upgrade.
- Reject the handshake by returning false from beforeHandshake().
- Transfer some HTTP session attributes to the WebSocketSession attributes.
- Record metadata for audit or correlation.

Spring provides HttpSessionHandshakeInterceptor to transfer HTTP session attributes to the WebSocket session.

Example of registering an interceptor for a raw WebSocket handler:

~~~java
registry.addHandler(new EchoHandler(), "/echo")
    .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

The attributes are stored in the WebSocketSession and can be read in subsequent message-handling steps. Only put necessary data into the session attributes; do not copy entire sensitive objects without a need.

With STOMP, the endpoint registry also supports registering a handshake interceptor:

~~~java
registry.addEndpoint("/ws")
    .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

HandshakeInterceptor runs at the HTTP handshake boundary. It is not an interceptor for each STOMP SEND or SUBSCRIBE frame.

### 11.2. DefaultHandshakeHandler

DefaultHandshakeHandler performs the handshake process. It can:

- Check the Origin.
- Negotiate the subprotocol.
- Choose an upgrade strategy appropriate for the WebSocket server engine.
- Create the WebSocket session after a successful handshake.

You only need a custom HandshakeHandler when you need to change how negotiation works or integrate your own RequestUpgradeStrategy. With a typical configuration, Spring provides a handler suited to the Servlet container itself.

## 12. HandshakeInterceptor Differs from ChannelInterceptor

These two interceptors operate at two different layers:

| Criterion | HandshakeInterceptor | ChannelInterceptor |
|---|---|---|
| When | Before/after the HTTP WebSocket handshake | When a Spring Message passes through a MessageChannel |
| Subject | The HTTP request/response and the WebSocket session's attributes | The Spring Message, headers, and channel |
| Scope | Once, when the connection is opened | Many times, for each message or frame processed |
| Can reject | Rejects the handshake before a WebSocket session exists | Can return null from preSend to block a message |
| Examples | Checking the request, transferring HTTP session attributes | Authenticating STOMP CONNECT, checking destinations, auditing SEND/SUBSCRIBE |

Example of a ChannelInterceptor that can obtain a StompHeaderAccessor to check the command:

~~~java
public class AuditChannelInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
            );

        if (accessor != null) {
            StompCommand command = accessor.getCommand();
            // Check or write an audit entry according to the command.
        }

        return message;
    }
}
~~~

To register the interceptor, use configureClientInboundChannel() in WebSocketMessageBrokerConfigurer:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new AuditChannelInterceptor());
}
~~~

This is the appropriate place to inspect STOMP frames after Spring has decoded them into Spring Messages.

## 13. Authentication and Authorization

### 13.1. Authentication at the HTTP Handshake

Many applications already have Spring Security protecting HTTP. When a browser opens a WebSocket, the handshake request usually carries the existing cookie/session. If the HTTP request has been authenticated, the Principal from HttpServletRequest can be associated by Spring with the WebSocket/SockJS session and the subsequent STOMP messages.

With this approach:

- The user logs in over HTTP.
- The browser sends the cookie/session when opening the WebSocket.
- The server authenticates the handshake request.
- Spring attaches the Principal to the WebSocket session.
- Subsequent STOMP messages carry the authenticated user's information.

This is usually the simple choice if the application already uses cookie-based sessions.

### 13.2. Token Authentication at STOMP CONNECT

The browser WebSocket API does not provide a way to freely add custom HTTP headers to the handshake request. If the application needs a bearer token instead of a cookie, it can send the token in the STOMP CONNECT headers after the WebSocket connection has been opened.

A ChannelInterceptor can:

1. Check whether the STOMP command is CONNECT.
2. Read the token from the native STOMP header.
3. Authenticate the token through the security system.
4. Create the corresponding Principal.
5. Call accessor.setUser(principal) to attach the user to the STOMP session.

Example illustrating the core part:

~~~java
if (StompCommand.CONNECT.equals(accessor.getCommand())) {
    String token = accessor.getFirstNativeHeader("Authorization");

    Authentication authentication =
        tokenAuthenticationService.authenticate(token);

    accessor.setUser(authentication);
}
~~~

tokenAuthenticationService is the application's authentication service, not a ready-made Spring API. You need to handle a missing, expired, wrongly-signed token and invalid permissions before accepting the message.

If you use Spring Security message authorization, the authentication interceptor must run before Spring Security's authorization interceptor so that the user is already attached to the message when authorization is performed.

### 13.3. STOMP login/passcode

STOMP has login and passcode headers on CONNECT. However, with STOMP over WebSocket, Spring by default relies on HTTP-level authentication and ignores/overrides the login/passcode at the STOMP level. Do not assume that merely sending login/passcode will automatically authenticate a browser client.

### 13.4. CSRF and Origin

Spring Security WebSocket supports checking the CSRF token on STOMP CONNECT when WebSocket message security is enabled. If the security configuration requires CSRF, the client needs to send the token in the way Spring Security prescribes.

By default, Spring accepts only same-origin for WebSocket and SockJS. You can configure a list of specific origins when the frontend and backend run on different origins.

Origin is a protective signal for browser clients, not proof of authentication. A non-browser client can set the Origin header itself. Always authenticate identity and authorize independently of Origin.

## 14. WebSocket/STOMP Security

A WebSocket connection usually lives longer than an HTTP request, so security needs to be designed around both the session lifecycle and each individual message.

Important principles:

- Use WSS in the production environment to encrypt data in transit.
- Authenticate at the handshake or at STOMP CONNECT according to the chosen architecture.
- Authorize SEND, SUBSCRIBE, and sensitive destinations separately.
- Do not let the client declare its own userId/role and then trust those values.
- Validate the payload, message size, content type, and schema.
- Limit the number of connections, the message rate, and the number of subscriptions per user.
- Configure specific allowed origins; do not casually open a wildcard when using cookies/sessions.
- Do not write access tokens, cookies, or sensitive payloads to logs.
- Handle session expiry, logout, and permission revocation while the WebSocket is still open.
- Configure an appropriate idle timeout, heartbeat, and buffer limits.

A client may have been authenticated at the handshake but still send a message to a destination the user has no permission for. Session authentication does not replace authorization on each message.

### 14.1. Note on Spring Versions

CVE-2025-41254 relates to STOMP over WebSocket in Spring Framework. Versions 6.2.0 through 6.2.11 are affected; the fix for the 6.2 branch starts at 6.2.12. When using Spring Framework 6.2, use a patched version and follow Spring's security advisories.

## 15. SockJS and Fallback Transports

Some proxy or enterprise network environments do not fully support WebSocket. Spring can provide the SockJS fallback.

SockJS tries to use WebSocket when possible. If not, it can use alternative HTTP transports such as streaming or long polling.

Endpoint configuration:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("http://localhost:3000")
        .withSockJS();
}
~~~

When using SockJS, the client creates a SockJS transport instead of a direct browser WebSocket, and then uses the STOMP client over that transport.

SockJS changes how data is transported when WebSocket is unavailable. It does not replace STOMP commands, destinations, or the application's message rules.

If the application only runs in an environment that already supports WebSocket reliably, there is no need to enable SockJS just because it exists. Choose based on client and network compatibility requirements.

## 16. The Simple Broker and the Broker Relay

### 16.1. The Built-in Simple Broker

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The simple broker stores subscriptions in application memory and broadcasts messages to the clients that are subscribed. It is convenient for demos, small applications, or cases that do not need a dedicated broker.

Common limitations:

- Subscriptions live in the memory of a single application instance.
- It lacks the full feature set of a dedicated message broker.
- It does not automatically share subscriptions across multiple Spring replicas.
- It does not replace queue persistence, durable subscriptions, or advanced broker-level routing.

### 16.2. The Broker Relay

When you need a full broker, Spring can relay STOMP frames to an external broker:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
        .setRelayHost("localhost")
        .setRelayPort(61613)
        .setClientLogin("client")
        .setClientPasscode("client-secret");
}
~~~

This example assumes the broker has a STOMP listener at localhost:61613 and that the login credentials are configured separately. Do not use the illustrative credentials in production.

In the broker relay architecture:

- The browser still connects over WebSocket to Spring.
- Spring receives STOMP frames from the client.
- Spring forwards destinations that belong to the broker prefix to the external STOMP broker over TCP.
- The broker manages subscriptions and broadcasts messages.
- Spring receives messages from the broker and sends them back to the browser over WebSocket.

When running multiple Spring replicas, the external broker helps the nodes share message routing and subscriptions according to the broker configuration. You need to configure relay credentials, TLS, heartbeat, virtual host, and destination permissions according to the actual broker.

## 17. Message Ordering and Concurrent Processing

WebSocket preserves frame order on one connection at the transport layer. However, after Spring decodes a frame into a message and puts it into channels running on an executor, business processing may occur on multiple threads.

If the processing order of inbound messages within the same session is a mandatory requirement, Spring has a preserve receive order option. If the publish order to the WebSocket client is a mandatory requirement, you can enable preserve publish order in MessageBrokerRegistry.

Example:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic");
    registry.setPreservePublishOrder(true);
}
~~~

This option may reduce parallelism and throughput. Enable it only when the business logic needs to keep the order; otherwise, designing idempotent handlers and processing messages independently usually scales better.

## 18. Transport Limits and Performance

A WebSocket connection is long-lived and can hold many resources on the server side. You need to configure reasonable limits:

- Max text message size.
- Max binary message size.
- Send buffer size.
- Send time limit.
- Idle timeout.
- Number of concurrent sessions.
- Number of messages/second per client.
- Heartbeat interval.

With STOMP, Spring lets you configure the WebSocket transport:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registry) {
    registry.setMessageSizeLimit(64 * 1024);
    registry.setSendBufferSizeLimit(512 * 1024);
    registry.setSendTimeLimit(15_000);
}
~~~

The numbers above are just initial examples. Choose according to the actual payload size, number of clients, latency, and memory. Do not raise limits without bound to avoid large-message errors; consider pagination, streaming, or splitting the payload if the data is too large.

If a client processes slowly, the send buffer may grow and cause memory pressure. You need a policy for limiting the buffer, timeouts, and closing slow sessions according to the system's needs.

## 19. Diagnosing Errors by Layer

| Symptom | Layer to check | How to handle |
|---|---|---|
| HTTP 404 when connecting | Endpoint/HTTP mapping | Check registerStompEndpoints or registerWebSocketHandlers |
| HTTP 403 | Authentication, authorization, or Origin | Check Spring Security, CSRF, and allowed origins |
| Not receiving HTTP 101 | Handshake/Proxy | Check Upgrade, Connection, TLS, and proxy support |
| 101 succeeds but CONNECTED is not received | STOMP protocol | Check the subprotocol, CONNECT frame, version, and broker |
| CONNECTED but SUBSCRIBE gets no data | STOMP destination/broker | Check the destination prefix, broker subscription, and subscribe permissions |
| SEND does not invoke @MessageMapping | Spring routing | Check the application prefix and the @MessageMapping path |
| Controller runs but the client does not receive | Outbound routing/broker | Check @SendTo, the broker destination, and the client subscription |
| JSON deserialization error | Message converter | Check the content-type, JSON schema, and payload |
| Connection drops after an idle period | Proxy/heartbeat/timeout | Align the heartbeat and the idle timeout |
| Client does not reconnect on its own | Client lifecycle | Configure reconnect and handle the new session state |
| Multiple clients receive duplicate data | Broker/subscription | Check the subscription id, shared subscription, and destination |

An effective way to diagnose is to determine which layer the last message got through. For example, if there is no HTTP 101, there is no need yet to check @MessageMapping; if CONNECTED has been received, then the handshake and STOMP CONNECT have completed, so check SUBSCRIBE/SEND and broker routing next.

## 20. Testing an End-to-End STOMP Session

A practical smoke test should verify, in order:

1. The browser can open /ws and receive HTTP 101.
2. The client negotiates the STOMP subprotocol.
3. The client sends CONNECT and receives CONNECTED.
4. The client SUBSCRIBEs to /topic/chat.
5. The client SENDs to /app/chat.send with content-type application/json.
6. Spring calls ChatController.handle().
7. The broker broadcasts MESSAGE to /topic/chat.
8. The client receives the correct payload.
9. The client sends DISCONNECT or closes the WebSocket.
10. The server releases the session and subscriptions according to the lifecycle.

Do not merely check that the WebSocket handshake succeeds and conclude STOMP works. Also do not merely call the controller in a unit test and assume that message routing and the broker subscription have been tested.

## 21. Common Mistakes

- **Assuming WebSocket understands JSON or STOMP on its own**: WebSocket only transports text/binary frames; the application needs a protocol that defines the content.
- **Confusing HTTP 101 with STOMP CONNECTED**: 101 opens the WebSocket; CONNECTED confirms the STOMP session.
- **Confusing /ws with /app/chat.send**: /ws is the handshake endpoint; /app/chat.send is a STOMP destination.
- **Putting destination logic into the HTTP URL after connecting**: message routing is determined by the protocol frame and the destination header.
- **Using raw WebSocket but expecting @MessageMapping to work**: @MessageMapping belongs to the STOMP messaging stack.
- **Using STOMP but not configuring the broker prefix**: SUBSCRIBE or SEND is not routed as expected.
- **Assuming /topic and /queue are mandatory keywords of every broker**: these are conventions; an external broker may have its own destination semantics.
- **Treating Origin as authentication**: Origin mainly helps protect browsers; other clients can forge this header.
- **Trusting a userId/role sent by the client**: identity and permissions must be authenticated by the server.
- **Using STOMP login/passcode without understanding Spring authentication**: Spring by default ignores those headers for STOMP over WebSocket when using HTTP-level authentication.
- **Not distinguishing HandshakeInterceptor from ChannelInterceptor**: one intervenes in the HTTP handshake, the other handles Spring Messages.
- **Casually opening allowed origins to a wildcard**: this can increase cross-site WebSocket risk.
- **Not configuring WSS in production**: data can be eavesdropped on over the network.
- **Enabling the simple broker for multiple replicas and expecting subscriptions to be shared**: the simple broker only keeps state in each instance's memory.
- **Not handling reconnect**: a WebSocket connection can be lost due to the network, a proxy, or a server restart.
- **Not limiting message size and send buffer**: a client sending a large payload or reading slowly can cause memory pressure.
- **Not testing message order**: an executor can process messages in parallel and change the completion order.

## 22. Deployment Checklist

- [ ] Identify the handshake endpoint, for example /ws.
- [ ] Determine whether the client uses raw WebSocket or STOMP.
- [ ] If using STOMP, agree on the version and Sec-WebSocket-Protocol.
- [ ] Register the endpoint through WebSocketConfigurer or StompEndpointRegistry.
- [ ] Configure destination prefixes for the application and the broker.
- [ ] Choose the simple broker or an external broker relay.
- [ ] Determine the authentication mechanism at the HTTP handshake or STOMP CONNECT.
- [ ] Authorize SEND, SUBSCRIBE, and destinations per user.
- [ ] Check Origin and CSRF according to the security policy.
- [ ] Use WSS when transmitting data over an untrusted network.
- [ ] Configure heartbeat, idle timeout, and reconnect.
- [ ] Limit message size, send buffer, and the number of connections.
- [ ] Test that the proxy/load balancer supports WebSocket.
- [ ] Test end-to-end from HTTP 101 to STOMP MESSAGE.
- [ ] If running multiple replicas, evaluate a broker relay and how subscriptions are shared.
- [ ] Use a Spring Framework version that has security fixes applied.

## 23. Summary

The HTTP handshake initiates and hands over the connection. WebSocket maintains a full-duplex channel for transmitting text/binary frames. An application protocol such as STOMP defines commands, headers, destinations, and the meaning of messages. The three layers work together but have their own lifecycles and responsibilities.

In Spring, the raw WebSocket API fits when the application wants to design its own message protocol. STOMP over WebSocket fits when you need publish/subscribe, destination routing, a broker, and Spring Messaging integration. @EnableWebSocketMessageBroker, StompEndpointRegistry, MessageBrokerRegistry, @MessageMapping, and the broker channel form the foundation of the STOMP model.

When designing, distinguish the handshake URL from the message destination, distinguish the handshake interceptor from the channel interceptor, authenticate users at the right layer, and test the whole flow from HTTP 101 to STOMP MESSAGE. Configuring these boundaries correctly makes the system easier to scale, easier to maintain, and safer.

## References

- Spring Framework 6.2 — WebSocket overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html
- Spring Framework 6.2 — WebSocket API and handshake: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring Framework 6.2 — STOMP overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html
- Spring Framework 6.2 — Enable STOMP: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html
- Spring Framework 6.2 — Flow of Messages: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — Authentication: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html
- Spring Framework 6.2 — Token Authentication: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication-token-based.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Security — CVE-2025-41254: https://spring.io/security/cve-2025-41254/
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- STOMP 1.2 Specification: https://stomp.github.io/stomp-specification-1.2.html