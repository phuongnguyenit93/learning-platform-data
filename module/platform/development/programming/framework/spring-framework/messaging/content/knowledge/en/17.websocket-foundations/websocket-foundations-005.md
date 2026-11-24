# Registering Endpoints and Configuring the Handshake

## Objectives

In Spring Framework, a WebSocket endpoint is the URL a client uses to start a WebSocket connection. Spring maps that URL to a WebSocketHandler, runs the HTTP handshake steps, checks the origin of access, negotiates a sub-protocol if any, and then upgrades the connection into a bidirectional WebSocket session.

Spring supports two commonly seen configuration styles:

- **Raw WebSocket:** uses @EnableWebSocket, WebSocketConfigurer, WebSocketHandlerRegistry, and WebSocketHandler. The application defines the message structure and the handling itself.
- **STOMP over WebSocket:** uses @EnableWebSocketMessageBroker, WebSocketMessageBrokerConfigurer, and StompEndpointRegistry. STOMP adds commands, destinations, subscriptions, and message routing.

This lesson focuses on endpoint registration and the handshake; it also points out the boundary between raw WebSocket and STOMP so you can choose the right API.

After this lesson, you can:

- Register one or more WebSocket endpoints with Java configuration.
- Map an endpoint URL to a TextWebSocketHandler or BinaryWebSocketHandler.
- Describe the steps of the HTTP Upgrade and the 101 Switching Protocols response.
- Use a HandshakeInterceptor to inspect the request and pass attributes to the WebSocket session.
- Configure DefaultHandshakeHandler, allowed origins, and the sub-protocol.
- Distinguish an endpoint URL from a STOMP destination.
- Enable the SockJS fallback when needed.
- Handle authentication, access rights, session lifecycle, concurrency, and message limits.
- Build a runnable Spring Boot Java 17+ application with an echo endpoint.

## 1. What Is a WebSocket Endpoint?

WebSocket creates a long-lived, bidirectional (full-duplex) connection between the client and the server over one TCP connection. The client and server can proactively send messages after the connection is established; each message does not need to create a new HTTP request.

A WebSocket endpoint is the URL used for the initial connection, for example:

~~~text
ws://localhost:8080/ws/echo
wss://api.example.com/ws/echo
~~~

- ws:// is WebSocket without encryption at the transport layer.
- wss:// is WebSocket running over TLS, suitable for production.
- The path /ws/echo is mapped by Spring to a specific handler.

The WebSocket protocol only specifies how text/binary frames are framed and how the connection is controlled. It does not specify the structure of the business content. The client and server must agree on a message format, for example plain text, a JSON envelope, or a sub-protocol such as STOMP.

### The Endpoint URL Differs from the Message Destination

With raw WebSocket, there is usually one URL for connecting. After the handshake, messages continue to flow over that same session; the application defines how to classify and route the content itself.

With STOMP over WebSocket, there are two layers of addressing:

- The endpoint URL, for example /ws: used to open the WebSocket connection and start the STOMP session.
- The STOMP destination, for example /app/orders, /topic/prices: used to route STOMP frames after the connection has been opened.

Do not register a STOMP destination in WebSocketHandlerRegistry. It is not a handshake URL.

## 2. Raw WebSocket and STOMP Use Two Different Sets of Configuration

| Purpose | Raw WebSocket | STOMP over WebSocket |
|---|---|---|
| Enabling infrastructure | @EnableWebSocket | @EnableWebSocketMessageBroker |
| Configuration callback | WebSocketConfigurer | WebSocketMessageBrokerConfigurer |
| Registry | WebSocketHandlerRegistry | StompEndpointRegistry |
| Registration | registerWebSocketHandlers(...) | registerStompEndpoints(...) |
| Handling object | WebSocketHandler | STOMP message handler, controller, or broker |
| Message routing | Defined by the application | Based on STOMP commands and destinations |
| Example URL | /ws/echo | /ws |
| Example routing | JSON with a type field | /app/chat, /topic/room-1 |

If you only need to exchange custom text/binary frames, raw WebSocket is simpler. If you need publish/subscribe, routing, acknowledgement, and request/reply following an existing protocol, STOMP is usually more suitable.

Do not enable both sets of configuration for the same endpoint expecting them to merge automatically. Choose one clear handling model for each path.

## 3. Registering a Raw Endpoint with @EnableWebSocket

Spring provides the @EnableWebSocket annotation to enable the WebSocket infrastructure in a Spring MVC application.

A configuration class implements WebSocketConfigurer and overrides:

~~~java
void registerWebSocketHandlers(WebSocketHandlerRegistry registry);
~~~

Minimal example:

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public WebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo");
    }
}
~~~

The components:

- @Configuration: registers the class as Spring configuration.
- @EnableWebSocket: enables WebSocket request handling.
- WebSocketConfigurer: the callback for the application to register handlers.
- WebSocketHandlerRegistry: where you declare the URL and the corresponding handler.
- addHandler(handler, path): maps a handler to one or more paths.

A handler should be declared as a Spring bean so that you can inject the necessary services, repositories, or security components. In the example above, Spring injects EchoWebSocketHandler through the constructor.

### Registering Multiple Endpoints

One registry can map multiple handlers:

~~~java
@Override
public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
    registry.addHandler(chatHandler, "/ws/chat");
    registry.addHandler(notificationHandler, "/ws/notifications");
    registry.addHandler(binaryHandler, "/ws/files");
}
~~~

Each path needs a clear purpose and handler. An endpoint is a handshake URL; it does not automatically create a queue, topic, or broker destination.

### A Handler Can Use Multiple Paths

A handler can be mapped to multiple URLs:

~~~java
registry.addHandler(echoHandler, "/ws/echo", "/ws/echo-v2");
~~~

If two mappings conflict, the request may not be dispatched as intended. Use clear paths and avoid registering two handlers for the same URL.

## 4. Choosing the Right WebSocketHandler

Spring provides the WebSocketHandler interface and convenient base classes:

| Type | Use when |
|---|---|
| WebSocketHandler | You need to handle all kinds of WebSocket messages and lifecycle callbacks yourself. |
| TextWebSocketHandler | The application exchanges text, JSON, or a text protocol. |
| BinaryWebSocketHandler | The application exchanges binary data. |
| AbstractWebSocketHandler | You want to extend a base class and override only the callbacks you need. |

Example of a text handler:

~~~java
@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        session.sendMessage(new TextMessage(
                "echo:" + message.getPayload()
        ));
    }
}
~~~

TextWebSocketHandler calls handleTextMessage when it receives a text frame. If the application needs to receive binary frames, use BinaryWebSocketHandler or implement WebSocketHandler directly. Do not treat every message as a String.

### Callbacks in the Session Lifecycle

A handler may be interested in these callbacks:

- afterConnectionEstablished(session): the handshake succeeded and the session is opened.
- handleMessage(session, message): receives a message; the base class can dispatch to the text/binary callbacks.
- handleTextMessage(session, message): handles a text frame.
- handleBinaryMessage(session, message): handles a binary frame.
- handleTransportError(session, exception): handles a transport error.
- afterConnectionClosed(session, status): the session has closed.
- supportsPartialMessages(): declares whether the handler supports message fragments.

A handler typically uses session.getId(), session.getPrincipal(), session.getAttributes(), and session.getUri() to access session information.

### A Handler Bean Is Usually a Singleton

A handler registered as a Spring bean is usually shared among many WebSocket sessions. Do not store one client's own data in a shared mutable field.

If you need to store per-client state:

- Use WebSocketSession.getAttributes() for data tied to the session.
- Use a thread-safe registry keyed by session ID and remove the entry when afterConnectionClosed is called.
- Use PerConnectionWebSocketHandler if you need one handler instance per connection.

Do not hold a session collection indefinitely. When a client disconnects, you must release the related state and subscriptions.

## 5. How Does the HTTP WebSocket Handshake Work?

A WebSocket connection starts with an HTTP request. The client asks the server to upgrade the protocol from HTTP to WebSocket using the Upgrade headers.

Illustrative request:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: http://localhost:3000
~~~

Important headers:

| Header | Role |
|---|---|
| Upgrade: websocket | Requests switching the protocol to WebSocket. |
| Connection: Upgrade | Indicates the request is asking to upgrade the connection. |
| Sec-WebSocket-Key | A nonce generated by the client for the server to confirm the handshake. |
| Sec-WebSocket-Version | The WebSocket protocol version the client requests. |
| Origin | The origin of the browser page initiating the connection; used for origin validation. |
| Sec-WebSocket-Protocol | The list of sub-protocols the client wants to negotiate, if any. |

If the handshake is valid, the server returns status 101 Switching Protocols along with headers such as Upgrade, Connection, and Sec-WebSocket-Accept. If a sub-protocol is selected, the server also returns Sec-WebSocket-Protocol.

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

After the 101 response, the TCP connection remains open and is used to send/receive WebSocket frames. Subsequent messages are not independent HTTP requests.

### The Processing Chain in Spring

~~~mermaid
sequenceDiagram
    participant C as WebSocket Client
    participant M as Spring Handler Mapping
    participant I as HandshakeInterceptor
    participant H as HandshakeHandler
    participant W as WebSocketHandler

    C->>M: HTTP GET /ws/echo + Upgrade
    M->>I: beforeHandshake()
    I-->>M: true / false
    M->>H: doHandshake()
    H->>H: Validate headers, Origin, protocol
    H-->>C: 101 Switching Protocols
    H->>W: Create WebSocket session
    I->>I: afterHandshake()
    C->>W: WebSocket frames
    W-->>C: WebSocket frames
~~~

At the implementation level, Spring maps the handshake URL to a handler, runs the interceptors before the handshake, uses the handshake handler to check/negotiate, and relies on a server-specific upgrade strategy to perform the protocol upgrade. When the connection succeeds, Spring creates a WebSocketSession for the handler.

## 6. HandshakeInterceptor

HandshakeInterceptor lets you run logic before and after the handshake.

The interface is in the package:

~~~java
org.springframework.web.socket.server.HandshakeInterceptor
~~~

There are two methods:

~~~java
boolean beforeHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Map<String, Object> attributes
) throws Exception;

void afterHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Exception exception
);
~~~

### beforeHandshake

Called before Spring performs the protocol upgrade. It can:

- Check headers or request information.
- Check the authenticated Principal.
- Reject the handshake by returning false.
- Put necessary data into the attributes for the handler to use after the session is created.

Example of an interceptor that attaches the username from the Principal:

~~~java
public class UserHandshakeInterceptor implements HandshakeInterceptor {

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();

        if (principal != null) {
            attributes.put("username", principal.getName());
        }

        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler handler,
            Exception exception) {
        // Record the handshake result if needed.
    }
}
~~~

If you want to require a logged-in user, the interceptor can return false when there is no Principal. However, you should perform HTTP authentication through the Spring Security filter chain before the handshake and use the interceptor for additional checks.

The attributes added to the map are copied into WebSocketSession.getAttributes(). The handler can read:

~~~java
Object username = session.getAttributes().get("username");
~~~

Do not put passwords, access tokens, or long-lived secrets into session attributes just for convenient access. Only pass the information needed for the connection lifecycle.

### afterHandshake

Called after the handshake completes or fails. The exception parameter indicates the handshake error if any; the response contains the status/headers reflecting the result.

This method is typically used for logging, metrics, or cleaning up temporary data created during the handshake. It is not a callback for handling WebSocket messages.

### Registering the Interceptor

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new UserHandshakeInterceptor());
~~~

You can register multiple interceptors. If an interceptor returns false, the handshake chain is stopped and the handler does not open a session.

### HttpSessionHandshakeInterceptor

Spring has a built-in HttpSessionHandshakeInterceptor. It transfers the configured HTTP session attributes to the WebSocket session attributes.

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .addInterceptors(new HttpSessionHandshakeInterceptor());
~~~

This approach is useful when the application uses cookie-based HTTP sessions and needs some session data in the handler. Only copy the necessary data; do not treat copying an attribute as a mechanism for granting access to every message.

## 7. HandshakeHandler and DefaultHandshakeHandler

HandshakeHandler is the contract responsible for performing the handshake. The default implementation is DefaultHandshakeHandler.

It handles steps such as:

- Checking the required headers of the WebSocket handshake.
- Confirming the Origin according to the configuration.
- Negotiating the sub-protocol and WebSocket extensions.
- Determining the user for the WebSocket session.
- Delegating the upgrade operation to a RequestUpgradeStrategy appropriate for the server runtime.

In most applications, the default handshake handler is enough. Only configure a custom handler when you need to change the negotiation logic, determine a special Principal, or customize the server-specific upgrade strategy.

You can attach your own handler:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setHandshakeHandler(new DefaultHandshakeHandler());
~~~

The snippet above uses the default implementation explicitly. If you do not call setHandshakeHandler, Spring also uses the default handshake handler.

### Sub-protocol Negotiation

A WebSocket frame only contains text or binary. A sub-protocol determines the meaning and format of the frames. STOMP is an example.

The client can send:

~~~http
Sec-WebSocket-Protocol: v12.stomp
~~~

The server should only choose a protocol that both sides support. DefaultHandshakeHandler can negotiate the protocol based on the protocols the handler supports or a configured list of protocols.

Illustrative example:

~~~java
DefaultHandshakeHandler handshakeHandler = new DefaultHandshakeHandler();
handshakeHandler.setSupportedProtocols("v12.stomp");

registry.addHandler(stompAwareHandler, "/ws")
        .setHandshakeHandler(handshakeHandler);
~~~

With Spring STOMP support, the framework already provides a handler that supports STOMP; you usually do not need to create a DefaultHandshakeHandler yourself just to enable STOMP.

### RequestUpgradeStrategy

After the handshake is accepted, Spring needs to upgrade the HTTP connection using the server runtime's API. RequestUpgradeStrategy abstracts away the container-dependent part.

If running on a special server engine or version, you can pass an appropriate strategy into DefaultHandshakeHandler. With a typical Tomcat/Jetty/Jakarta WebSocket runtime, prefer the default configuration and only change the strategy when there is a specific deployment requirement.

## 8. Allowed Origins and Protecting the Handshake

By default, Spring WebSocket accepts only same-origin requests. If the frontend is on a different origin, you must explicitly declare the allowed origins.

Example:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
~~~

You can use multiple origins:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
        );
~~~

Or use a pattern:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

Notes:

- An Origin consists of the scheme, host, and port when present.
- Only add origins that are genuinely allowed to connect.
- Do not enable a wildcard for production without a clear reason.
- The origin check mainly protects browser clients. A non-browser client can set the Origin header itself, so Origin is not an authentication mechanism.
- Configuring origins for WebSocket/SockJS does not replace authentication and authorization at the application layer.

### Authentication and Authorization

The handshake is an HTTP request, so you can use the existing HTTP authentication mechanism. If the user has been authenticated by Spring Security, the Principal can be associated with the WebSocket session.

The principles:

1. Protect the handshake path with Spring Security.
2. Use cookies/an HTTP session or an authentication mechanism appropriate to the client.
3. Check permissions for each important operation/message after the connection is open.
4. Do not treat Origin as the user's identity.
5. Use wss:// when deploying over an untrusted network.
6. When a user logs out or has permissions revoked, close the related sessions according to the application policy.

A WebSocket connection can persist long after the HTTP handshake. Therefore, permissions may change while the session is open; the application needs an appropriate policy for updating/closing sessions.

## 9. SockJS Fallback

Not every client or proxy environment supports native WebSocket well. Spring supports SockJS to provide a fallback transport over HTTP when WebSocket is unavailable.

Registering the endpoint:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .withSockJS();
~~~

The client must use a corresponding SockJS client. Do not use the native JavaScript new WebSocket(...) to connect to an endpoint with SockJS enabled as though it were a plain WebSocket endpoint.

SockJS can choose a transport suitable for the browser/server, for example WebSocket, HTTP streaming, or long polling. Therefore, a SockJS endpoint has additional internal transport URLs under the registered path.

### When Should You Enable SockJS?

- The application needs to support older environments or proxies that block WebSocket.
- The client library already integrates SockJS.
- There is a requirement for an HTTP transport fallback.

If the system only supports modern browsers and the infrastructure allows WebSocket, native WebSocket is usually simpler.

When allowed origins are restricted, some fallback transports that cannot check the Origin, such as iframe-based transports, will be disabled. You need to test the actual transports if you enable SockJS.

## 10. Registering a STOMP Endpoint

If the application uses STOMP, configure the endpoint through StompEndpointRegistry, not through WebSocketHandlerRegistry.

Example:

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
    public void configureMessageBroker(MessageBrokerRegistry config) {
        config.setApplicationDestinationPrefixes("/app");
        config.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

In the configuration above:

- /ws is the endpoint URL for the handshake.
- /app is the prefix for messages the client sends to the application handler.
- /topic and /queue are the destination prefixes handled by the simple broker.
- The STOMP client negotiates the sub-protocol v12.stomp or a supported STOMP version.

The client opens a WebSocket to ws://host/ws, and then sends STOMP frames such as CONNECT, SUBSCRIBE, and SEND. The destinations in the frames are not endpoint URLs.

### SockJS with STOMP

You can enable SockJS on a STOMP endpoint:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
~~~

In that case, the client must use a STOMP client combined with a SockJS client. The handshake and fallback are managed by the STOMP WebSocket infrastructure.

### Handshake Interceptor for STOMP

STOMP endpoint registration also supports a handshake interceptor and a handshake handler. This lets you reuse the logic for Origin, HTTP session, Principal, and handshake attributes described above.

However, the interceptor only runs during the HTTP handshake. If you need to inspect STOMP CONNECT, SUBSCRIBE, or SEND frames, use the inbound channel interceptor mechanism of the STOMP messaging infrastructure.

## 11. Configuring Message Limits and the Server Container

A WebSocket connection can hold a lot of data in memory. You need to configure the message size limit and an idle timeout appropriate to the application.

With a Jakarta WebSocket server, Spring provides ServletServerContainerFactoryBean:

~~~java
@Bean
ServletServerContainerFactoryBean webSocketContainer() {
    ServletServerContainerFactoryBean container =
            new ServletServerContainerFactoryBean();

    container.setMaxTextMessageBufferSize(16 * 1024);
    container.setMaxBinaryMessageBufferSize(16 * 1024);

    return container;
}
~~~

The limits above are an example of 16 KiB for the text/binary buffers; choose values according to the actual payload. The container runtime may have its own additional limits.

For Jetty or another server engine, you can configure an appropriate request upgrade strategy to set the buffer size, idle timeout, and runtime parameters.

With STOMP, there are also separate transport-level properties such as the message size limit and the wait time for the first message. Do not confuse the limits of the WebSocket server container with the limits of the STOMP message transport.

## 12. Sending Messages Safely with Multiple Threads

A standard WebSocket session does not allow multiple threads to send messages concurrently on the same session. If a handler sends directly from multiple threads, you need to serialize the send operations.

Spring provides ConcurrentWebSocketSessionDecorator to wrap a session and limit concurrent sending:

~~~java
WebSocketSession safeSession =
        new ConcurrentWebSocketSessionDecorator(
                session,
                10_000,
                512 * 1024
        );
~~~

The parameters are the send-time limit and the send-buffer-size limit. Choose according to latency and the expected message size.

The decorator does not replace backpressure design. If a client reads slowly, the buffer can fill up; the application needs a clear policy such as limiting the queue, dropping old messages, or closing the session.

Do not broadcast concurrently to many sessions by calling sendMessage asynchronously on the same session without an appropriate synchronization mechanism.

## 13. Reverse Proxy and Deployment

If the application runs behind nginx, a load balancer, or an API gateway, the proxy must forward the WebSocket Upgrade request.

You need to check:

- The proxy forwards the Upgrade and Connection headers.
- The proxy's idle timeout is greater than the expected connection time, or there is a heartbeat.
- TLS termination and the wss:// scheme are configured correctly.
- Sticky sessions if the application keeps WebSocket sessions in memory and runs multiple instances without an appropriate routing layer.
- Health checks do not treat an open WebSocket session as an ordinary HTTP request.
- During deploy/restart, clients have a reconnect and resubscribe mechanism.

A WebSocket connection is a long-lived connection. Horizontal scaling needs to account for the number of sessions per instance, session memory, broadcasting between instances, and reconnecting after a node is replaced.

## 14. A Runnable Java 17+ Example: Registering an Echo Endpoint

The example uses Spring Boot 4.1.2, Spring MVC WebSocket, and embedded Tomcat. An endpoint /ws/echo receives a text message and returns the content with the prefix echo:.

### Project Structure

~~~text
spring-websocket-handshake-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          WebSocketDemoApplication.java
          EchoWebSocketHandler.java
          WebSocketConfiguration.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-websocket-handshake-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

### application.properties

~~~properties
server.port=8080
~~~

### WebSocketDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketDemoApplication.class, args);
    }
}
~~~

### EchoWebSocketHandler.java

~~~java
package demo;

import java.io.IOException;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        String payload = message.getPayload();
        session.sendMessage(new TextMessage("echo:" + payload));
    }
}
~~~

### WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.server.support.HttpSessionHandshakeInterceptor;
import org.springframework.web.socket.server.support.DefaultHandshakeHandler;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler echoHandler;

    public WebSocketConfiguration(EchoWebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .addInterceptors(new HttpSessionHandshakeInterceptor())
                .setAllowedOrigins(
                        "http://localhost:3000",
                        "http://127.0.0.1:3000"
                )
                .setHandshakeHandler(new DefaultHandshakeHandler());
    }
}
~~~

Run from the project directory with Java 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

The server starts at:

~~~text
http://localhost:8080
~~~

Open a frontend page at http://localhost:3000, and then run the following JavaScript in the browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
    socket.send("hello");
});

socket.addEventListener("message", event => {
    console.log(event.data);
});
~~~

Result in the browser console:

~~~text
echo:hello
~~~

This JavaScript snippet needs to run from a page whose origin is in the allowlist, for example http://localhost:3000. If run from a different origin, Spring rejects the handshake according to the current configuration.

### The Flow of the Example

1. Spring Boot starts the embedded Tomcat and the Spring application context.
2. @EnableWebSocket enables the WebSocket infrastructure.
3. WebSocketConfigurer registers EchoWebSocketHandler at /ws/echo.
4. The client sends an HTTP Upgrade request to that URL.
5. HttpSessionHandshakeInterceptor transfers the appropriate HTTP session attributes to the WebSocket session.
6. The Origin is checked against the allowlist.
7. DefaultHandshakeHandler handles the handshake and the server upgrades the connection.
8. The client sends the text frame hello.
9. TextWebSocketHandler.handleTextMessage receives the payload and sends back echo:hello.
10. When the client closes the socket, the WebSocket session is closed and the corresponding lifecycle callback is called.

This example uses raw WebSocket, not STOMP. The message is plain text and the application defines the response prefix itself.

## 15. Testing the Handshake and Endpoint

When testing, separate the handshake from message handling:

### Handshake

- The correct URL path.
- The request has valid Upgrade/Connection headers.
- The WebSocket version is supported by the server.
- The Origin is in the allowlist.
- The user is authenticated if the endpoint requires login.
- The sub-protocol is negotiated correctly, if any.
- The proxy forwards the Upgrade request.

### Message Handling

- A text frame reaches the correct TextWebSocketHandler.
- A binary frame is handled or rejected properly.
- A payload larger than the limit is handled according to policy.
- Transport errors and the close callback release the session state.
- Many clients connecting concurrently do not leak state.
- Concurrent sends are serialized as the WebSocket session requires.

### STOMP Testing

If the endpoint uses STOMP, also check:

- The client sends CONNECT with the appropriate sub-protocol.
- SUBSCRIBE to the correct destination.
- A SEND to the application prefix is routed to the controller.
- The broker prefix is handled by the simple broker or the external broker relay.
- Authentication/authorization is applied to STOMP frames, not just the handshake.

## 16. Common Mistakes

| Symptom | Common cause | How to handle |
|---|---|---|
| HTTP 404 when opening the WebSocket | The URL is not registered or the context path is wrong | Check addHandler and the client URL |
| HTTP 400 or handshake failure | Missing Upgrade header, wrong version, or the server does not support upgrade | Check the request, the servlet container, and the proxy |
| Origin rejected | The frontend origin is not in the allowlist | Add the exact scheme/host/port needed |
| Browser connects same-origin but fails cross-origin | Only same-origin is allowed by default | Configure setAllowedOrigins or a specific pattern |
| Handshake succeeds but messages are not handled | The handler is the wrong message type or the protocol does not match | Check the Text/Binary handler and the sub-protocol |
| Client expects STOMP but the server uses raw WebSocket | Mistakenly used @EnableWebSocket instead of the message broker config | Switch to @EnableWebSocketMessageBroker and register a STOMP endpoint |
| A SockJS client cannot connect to a raw endpoint | The client/server do not agree on the SockJS fallback | Use native WebSocket or enable withSockJS together with a SockJS client |
| Multiple threads sending on the same session cause errors | A WebSocket session does not support concurrent send | Use ConcurrentWebSocketSessionDecorator or serialize sends |
| Session state keeps growing | State is not removed on disconnect | Clean up in afterConnectionClosed |
| Connection is closed by the proxy after a period of time | Idle timeout or the proxy does not support WebSocket Upgrade | Configure the proxy timeout, heartbeat, and reconnect |
| Origin allowlist is set but unknown clients still try to connect | Origin is not authentication | Protect the handshake with Spring Security and check permissions |
| Connection closed on a large payload | The buffer/message limit is too small | Adjust the limits and limit payloads at the application layer |

## 17. Deployment Checklist

- [ ] Choose raw WebSocket or STOMP before configuring the endpoint.
- [ ] For raw WebSocket, use @EnableWebSocket and WebSocketConfigurer.
- [ ] Register each path with WebSocketHandlerRegistry.addHandler.
- [ ] Choose TextWebSocketHandler or BinaryWebSocketHandler according to the payload type.
- [ ] Use HandshakeInterceptor for checking/collecting data at handshake time.
- [ ] Use DefaultHandshakeHandler unless there is a requirement for custom negotiation/upgrade.
- [ ] Configure specific allowed origins for the frontend.
- [ ] Authenticate the HTTP handshake and authorize operations after connecting.
- [ ] Do not treat Origin as an identity or an authentication mechanism.
- [ ] Use wss:// in the production environment.
- [ ] Only enable SockJS when a fallback is needed and the client uses SockJS.
- [ ] If using STOMP, register with StompEndpointRegistry; distinguish the endpoint URL from the STOMP destination.
- [ ] Limit message size, idle time, and the number of connections.
- [ ] Synchronize sending on the same WebSocketSession.
- [ ] Remove session state on disconnect.
- [ ] Check the reverse proxy, reconnect, timeout, and horizontal scaling.

## Key Takeaways

- @EnableWebSocket + WebSocketConfigurer + WebSocketHandlerRegistry are used to register a raw WebSocket handler.
- addHandler(handler, path) maps a handshake URL to a WebSocketHandler.
- The handshake starts with an HTTP Upgrade; success returns 101 Switching Protocols.
- HandshakeInterceptor.beforeHandshake can reject the request or put attributes into the WebSocket session; afterHandshake is called after the handshake result.
- DefaultHandshakeHandler checks the handshake, Origin, and sub-protocol and delegates the protocol upgrade to the server strategy.
- Spring accepts only same-origin by default; cross-origin needs a specific allowlist.
- Origin validation does not replace authentication or authorization.
- withSockJS enables the fallback transport; the client must also use SockJS.
- STOMP uses @EnableWebSocketMessageBroker, WebSocketMessageBrokerConfigurer, and StompEndpointRegistry.
- The endpoint URL is used to open the connection; the STOMP destination is used to route messages after the connection has been opened.
- A WebSocket session needs cleanup, payload limits, and send synchronization when there are multiple threads.

## Official Documentation

- [Spring Framework 7.0.10 Reference: WebSocket API](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/server.html)
- [Spring Framework 7.0.10 Reference: WebSocket Overview](https://docs.spring.io/spring-framework/reference/7.0/web/websocket.html)
- [Spring Framework 7.0.10 Reference: STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp.html)
- [Spring Framework 7.0.10 Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/enable.html)
- [Spring Framework Javadoc: WebSocketConfigurer](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketConfigurer.html)
- [Spring Framework Javadoc: WebSocketHandlerRegistry](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketHandlerRegistry.html)
- [Spring Framework Javadoc: HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html)
- [Spring Framework Javadoc: DefaultHandshakeHandler](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/web/socket/server/support/DefaultHandshakeHandler.html)
- [Spring Boot 4.1.2 Reference: WebSockets](https://docs.spring.io/spring-boot/reference/messaging/websockets.html)
- [Jakarta WebSocket Specification](https://jakarta.ee/specifications/websocket/2.2/)
