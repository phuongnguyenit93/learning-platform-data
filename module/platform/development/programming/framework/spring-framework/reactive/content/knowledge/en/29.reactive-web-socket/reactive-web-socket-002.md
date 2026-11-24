# WebSocketHandler, WebSocketSession, and HandshakeWebSocketService in Spring WebFlux

Spring WebFlux provides a reactive WebSocket API to handle long-lived bidirectional connections. Instead of creating an HTTP request and receiving a complete response, the client and server keep a connection open and exchange multiple messages in both directions. A Spring application handles each connection with a WebSocketHandler; WebSocketSession represents the active session; and HandshakeWebSocketService validates the HTTP handshake and upgrades the connection to WebSocket.

The three components have distinct responsibilities:

- WebSocketHandler contains the business logic of a session: receiving, processing, and sending messages.
- WebSocketSession provides session metadata, the inbound message stream, the outbound message stream, and connection-closing operations.
- HandshakeWebSocketService validates the handshake request and uses the RequestUpgradeStrategy matching the running server to perform the upgrade.

This lesson belongs to the **WebSocket** group, focusing on the connection lifecycle, mapping a handler to a URL, combining receive/send into a single reactive flow, the role of the handshake service, security, backpressure, close status, and testing real connections.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the difference between HTTP request-response and a WebSocket connection.
- Describe the HTTP Upgrade handshake and when a connection transitions to WebSocket.
- Write a WebSocketHandler returning Mono<Void>.
- Read messages from WebSocketSession.receive().
- Send messages using WebSocketSession.send().
- Retrieve the session ID, URI, headers, principal, attributes, and subprotocol.
- Distinguish between text, binary, ping, and pong messages.
- Combine inbound and outbound publishers without calling subscribe manually.
- Understand the roles of SimpleUrlHandlerMapping and WebSocketHandlerAdapter.
- Explain HandshakeWebSocketService and RequestUpgradeStrategy.
- Customize WebSocketService via WebFluxConfigurer.
- Handle close status, errors, cancellation, and backpressure.
- Protect the handshake with authentication, authorization, and Origin checks.
- Write a WebSocket echo application with Java 17+ and Spring Boot.
- Test the handshake and message exchange using WebSocketClient.

## 2. How Does WebSocket Differ from HTTP Request-Response?

HTTP request-response typically follows this cycle:

~~~text
Client ---- HTTP request ----> Server
Client <--- HTTP response ---- Server
End of request
~~~

WebSocket begins with an HTTP handshake. Once the handshake succeeds, the connection is upgraded and both sides can send multiple messages over the same connection:

~~~text
Client ---- HTTP Upgrade handshake ----> Server
Client <--- HTTP 101 Switching Protocols - Server

Client <========== WebSocket ===========> Server
Client -------- message A --------------> Server
Client <------- message B --------------- Server
Client -------- message C --------------> Server
                 ...
        One side closes or loses connection
~~~

Key differences:

- The connection stays open across multiple messages.
- Both the client and server can proactively send messages.
- The server does not need to wait for a new HTTP request to send subsequent data.
- A session can live for a long time, so resources, timeouts, heartbeats, and disconnects must be managed.
- After a successful upgrade, data is exchanged using WebSocket framing rather than independent HTTP responses.

WebSocket is well suited for chat, realtime dashboards, live status, multi-user collaboration, games, and applications requiring continuous two-way exchange. For server-to-client-only data, Server-Sent Events can be simpler; for regular request-response, HTTP remains more suitable.

## 3. HTTP Handshake and the Upgrade Process

Typically, the client opens an HTTP GET request with WebSocket headers. Example:

~~~http
GET /ws/echo HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

The server inspects the request and, if accepted, returns a successful upgrade response. For an HTTP/1.1 handshake:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
~~~

Afterward, both sides exchange WebSocket frames over the upgraded connection.

The handshake may carry additional information:

- Origin: the web page initiating the connection.
- Cookies or credentials: depending on the authentication model.
- Sec-WebSocket-Protocol: subprotocols the client wants to negotiate.
- Sec-WebSocket-Extensions: proposed extensions, such as compression.
- Headers for tracing or correlation if permitted by the system.

Not every GET request is a WebSocket handshake. The server must check the upgrade conditions and a valid handshake key/version. Spring WebFlux delegates validation and upgrading to WebSocketService together with RequestUpgradeStrategy.

## 4. Three Core Components and Their Responsibilities

| Component | Responsibility | When Active |
| --- | --- | --- |
| WebSocketHandler | Handles messages and logic for a session | After the handshake succeeds |
| WebSocketSession | Represents the connection, metadata, and both message streams | Throughout the session lifecycle |
| HandshakeWebSocketService | Validates the handshake and performs the upgrade via server strategy | Before the handler starts |

A request to a WebSocket endpoint passes through the main components:

~~~text
HTTP request with Upgrade: websocket
             |
             v
       HandlerMapping
             |
             v
    WebSocketHandlerAdapter
             |
             v
      WebSocketService
             |
             v
 HandshakeWebSocketService
             |
             v
    RequestUpgradeStrategy
             |
             v
      WebSocketSession
             |
             v
       WebSocketHandler
             |
             v
     receive() / send()
~~~

WebSocketHandlerAdapter is the bridge that enables WebFlux's DispatcherHandler to invoke a WebSocketHandler. The adapter delegates to WebSocketService; by default, that service is HandshakeWebSocketService. The service performs basic handshake checks and then uses the strategy corresponding to the HTTP server, such as Reactor Netty, Tomcat, or Jetty.

## 5. What Is WebSocketHandler?

WebSocketHandler is the interface representing the handling logic for a WebSocket session. Primary method:

~~~java
Mono<Void> handle(WebSocketSession session);
~~~

The method receives a WebSocketSession and returns Mono<Void>. This Publisher tells Spring when the session handling logic has completed.

A handler typically performs the following tasks:

1. Read messages from session.receive().
2. Transform or validate the payload.
3. Call asynchronous business services if needed.
4. Create response messages using session.textMessage() or session.binaryMessage().
5. Send messages via session.send().
6. Complete when the connection closes, an error occurs, or the application proactively closes the session.

Example of a handler that only receives messages and logs them:

~~~java
@Component
public class LoggingWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive()
            .doOnNext(message ->
                System.out.println(message.getPayloadAsText()))
            .then();
    }
}
~~~

In this example, the handler does not send messages. then() turns the inbound Flux into a Mono<Void> that completes when the inbound stream ends.

Do not call subscribe() inside handle(). Spring manages the subscription based on the Mono<Void> returned by the handler. If you subscribe manually and return Mono.empty(), the lifecycle may finish before the work actually completes, errors will not propagate properly, and cancellation becomes hard to manage.

## 6. What Does WebSocketSession Provide?

WebSocketSession represents an active WebSocket connection. Key APIs:

| API | Meaning |
| --- | --- |
| getId() | Session ID |
| getHandshakeInfo() | Information from the HTTP handshake that created the session |
| getAttributes() | Attributes attached to the session |
| receive() | Flux of messages arriving from client to server |
| send(publisher) | Sends a message publisher from server to client |
| textMessage(text) | Creates a text message |
| binaryMessage(factory) | Creates a binary message |
| pingMessage(factory) | Creates a ping frame |
| pongMessage(factory) | Creates a pong frame |
| close() | Closes the session with a normal close status |
| close(status) | Closes the session with a specified close status |
| closeStatus() | Reads the close status when the session ends |
| isOpen() | Checks whether the connection is open |

Some handshake details commonly needed:

- Endpoint URI.
- HTTP headers.
- Cookies.
- Authenticated Principal.
- Negotiated subprotocol.
- Server-side remote address.
- Attributes passed from the handshake.

Example reading metadata:

~~~java
public Mono<Void> handle(WebSocketSession session) {
    String sessionId = session.getId();
    URI endpoint = session.getHandshakeInfo().getUri();
    String subProtocol = session.getHandshakeInfo().getSubProtocol();

    log.info(
        "WebSocket connected: sessionId={}, endpoint={}, protocol={}",
        sessionId, endpoint, subProtocol);

    return session.receive()
        .doOnNext(message ->
            log.debug("Received message for session {}", sessionId))
        .then();
}
~~~

This snippet requires declaring a logger and importing URI. Do not log sensitive payloads merely to debug connections.

## 7. HandshakeInfo and Authentication Information

getHandshakeInfo() returns HandshakeInfo, an object containing details of the HTTP handshake that created the session.

Commonly used methods:

| API | Data Type | Meaning |
| --- | --- | --- |
| getUri() | URI | URL of the WebSocket endpoint |
| getHeaders() | HttpHeaders | HTTP headers in the handshake |
| getCookies() | MultiValueMap | Cookies from the server-side handshake request |
| getPrincipal() | Mono<Principal> | Authenticated Principal, if present |
| getSubProtocol() | String | Negotiated subprotocol |
| getRemoteAddress() | InetSocketAddress | Server-side remote address |
| getAttributes() | Map<String, Object> | Attributes populated into the session |
| getLogPrefix() | String | Prefix to aid log correlation |

getPrincipal() returns Mono<Principal> because the principal is exposed via a reactive API. If the request is unauthenticated, the publisher may complete without emitting a Principal.

Example:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.getHandshakeInfo().getPrincipal()
        .doOnNext(principal ->
            log.info(
                "Authenticated WebSocket user: {}",
                principal.getName()))
        .then(session.receive().then());
}
~~~

This only observes an existing principal. Authentication and authorization must be enforced in the HTTP security chain before allowing the upgrade. Never treat a userId sent in a query string or the first message as an authenticated identity.

## 8. The Two Streams: receive and send

WebSocketSession has two independent reactive streams:

- receive(): Flux<WebSocketMessage> for inbound data.
- send(Publisher<WebSocketMessage>): Mono<Void> for outbound data.

receive() completes when the inbound connection closes normally or emits an error if the transport encounters a failure. send() completes when the source message publisher completes and writing the messages finishes.

Echo example:

~~~java
@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

When the client sends the text message hello, the server sends back echo: hello. When the client closes the connection, receive() completes; the replies publisher also completes and send() finishes.

This is a single pipeline tying output to input, so no manual subscription is needed for receive and send.

### Asynchronous Business Processing

You can use concatMap to call a service for each message while preserving processing order:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
        .map(WebSocketMessage::getPayloadAsText)
        .concatMap(text ->
            messageService.process(text)
                .map(session::textMessage));

    return session.send(replies);
}
~~~

concatMap waits for the current message to finish processing before moving to the next one. If you use flatMap with high concurrency, multiple messages can be processed concurrently and results may return out of input order.

Choose the operator based on the business contract: whether order matters, whether concurrent processing is allowed, and what concurrency limit applies.

## 9. Combining Independent Inbound and Outbound Streams

Outbound data is not always generated directly from inbound messages. A server may both receive commands from the client and push realtime data from another publisher.

Structural example:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
        .doOnNext(message ->
            processCommand(message.getPayloadAsText()))
        .then();

    Flux<String> updates = updateService.streamUpdates();

    Mono<Void> output = session.send(
        updates.map(session::textMessage));

    return input.and(output);
}
~~~

input processes the message stream from the client. output emits updates from the service. and() combines both Mono<Void> instances; the overall flow terminates when either branch completes, and the other branch is cancelled according to the operator's semantics.

This is useful when output is a long-lived or infinite publisher that must stop immediately when the client disconnects. If you need to wait for both branches to complete, choose an operator with wait-for-both semantics and carefully check which publisher might be infinite.

Do not call subscribe() on input or output individually. Return a combined publisher so Spring manages cancellation and errors.

## 10. WebSocketMessage: text, binary, ping, and pong

WebSocketMessage represents a message/frame provided by Spring to the handler.

Common types:

- TEXT: text content, usually JSON or a string.
- BINARY: byte payload, often used for images, audio, or binary formats.
- PING: connection-check frame.
- PONG: ping response frame.

Reading text:

~~~java
session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .doOnNext(text -> log.debug("Text received: {}", text))
    .then();
~~~

Sending text:

~~~java
session.send(
    Flux.just(
        session.textMessage("connected"),
        session.textMessage("ready")));
~~~

Sending binary:

~~~java
session.send(
    Mono.just(
        session.binaryMessage(factory ->
            factory.wrap(new byte[] {1, 2, 3, 4}))));
~~~

Binary payloads use the session's DataBufferFactory. In real applications, payload size and the DataBuffer lifecycle must be managed properly.

Ping/pong can be used at the protocol or transport layer to detect dead connections. Automatic ping replies depend on the server implementation and configuration; do not assume every application handler must manually send a pong for every ping frame.

## 11. Backpressure and Safe Message Processing

WebSocket is a long-lived connection, but that does not mean the server can receive unlimited messages or send unlimited data without control.

Key principles:

- Use reactive publishers to leverage backpressure across supporting components.
- Limit the number of concurrently processed messages.
- Limit message and payload sizes.
- Do not buffer the entire message history in memory.
- Avoid blocking the event loop with synchronous I/O or heavy CPU work.
- If you must call a blocking API, switch to an appropriate scheduler and bound thread usage.
- Use concatMap if ordering must be preserved.
- Use a bounded onBackpressureBuffer if buffering is truly needed; define behavior when full.
- Do not create unbounded queues per session.

With Netty, DataBuffer instances can be pooled and reference-counted. If you retain a payload or DataBuffer across asynchronous work longer than the default lifecycle, retain it at the right time and release it when finished. The safest approach for simple text processing is to read the payload into a String immediately inside the pipeline and continue processing that String.

### Example of Bounding a Business Queue

~~~java
Flux<WebSocketMessage> replies = session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .onBackpressureBuffer(
        100,
        dropped -> log.warn("Inbound queue is full"),
        BufferOverflowStrategy.ERROR)
    .concatMap(text ->
        messageService.process(text)
            .map(session::textMessage));
~~~

This illustrates an application-side buffer limit. When the buffer is full, the ERROR policy terminates the pipeline. Choose behavior suited to your protocol: reject the message, close the session, or report an application-layer error. Do not silently drop messages if the client expects processing confirmation.

## 12. Closing Sessions and CloseStatus

WebSocketSession can close the connection with:

~~~java
return session.close();
~~~

close() uses the normal close status. You can pass a specific close status:

~~~java
return session.close(CloseStatus.POLICY_VIOLATION);
~~~

Some standard close codes:

| Code | Meaning |
| --- | --- |
| 1000 | Normal Closure |
| 1001 | Going Away |
| 1002 | Protocol Error |
| 1003 | Unsupported Data |
| 1007 | Invalid Payload Data |
| 1008 | Policy Violation |
| 1009 | Message Too Big |
| 1011 | Internal Server Error |

Codes 1005 and 1006 are reserved values describing closing conditions; do not send them as close frames from the application.

closeStatus() returns Mono<CloseStatus>. The publisher may complete empty if the connection ends without receiving a close status. Use it to observe how the session ended:

~~~java
session.closeStatus()
    .doOnNext(status ->
        log.info("Session closed with code {}", status.getCode()))
    .then();
~~~

In real handlers, logging is typically placed at the end of the lifecycle using doFinally or combined with closeStatus. Do not poll isOpen() to wait for connection closure; reactive receive/send will emit complete, error, or cancellation when the session ends.

## 13. Error Handling and Cancellation

Situations that can terminate a WebSocket session:

- The client sends a close frame.
- The server proactively calls close().
- The network drops.
- A message is invalid or exceeds limits.
- A business processing publisher emits an error.
- The server shuts down.
- The client cancels the connection.

You can observe the lifecycle:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    return session.receive()
        .doOnSubscribe(subscription ->
            log.info("Session started: {}", session.getId()))
        .doOnError(error ->
            log.warn("WebSocket failed: {}", session.getId(), error))
        .doFinally(signal ->
            log.info(
                "Session finished: {}, signal={}",
                session.getId(), signal))
        .then();
}
~~~

doFinally observes COMPLETE, ERROR, or CANCEL. This is the right place to record metrics and release resources bound to the session.

Do not convert every error into an arbitrary text message. If your application protocol defines an error message schema, emit an error message following that schema before closing. If the error is a protocol violation or invalid payload, use an appropriate close code. Once the socket is closed, no further messages can be sent.

If you maintain a session registry by user or room, remove the session when the lifecycle ends. Do not remove it only in the onError branch; normal client disconnects also require cleanup.

## 14. What Is HandshakeWebSocketService?

HandshakeWebSocketService implements WebSocketService. It handles the HTTP handshake by:

1. Receiving the ServerWebExchange and the mapped WebSocketHandler.
2. Checking whether the request is a valid WebSocket handshake.
3. Extracting necessary details from the HTTP request, such as URI, headers, cookies, principal, and attributes.
4. Selecting or using the RequestUpgradeStrategy matching the server.
5. Performing the upgrade from HTTP to WebSocket.
6. Creating the WebSocketSession and handing control over to WebSocketHandler.

HandshakeWebSocketService has a default constructor that auto-detects the appropriate RequestUpgradeStrategy from the classpath. You can pass an explicit strategy if server-specific configuration is needed.

This service does not process individual messages in the session. After the handshake and upgrade succeed, WebSocketHandler together with WebSocketSession take over bidirectional communication.

### WebSocketService and RequestUpgradeStrategy

WebSocketService is the abstraction for the handshake process. HandshakeWebSocketService is Spring WebFlux's default implementation.

RequestUpgradeStrategy is the abstraction for the server-engine-dependent connection upgrade. Servers integrate WebSocket differently; Spring provides strategies for supported servers such as Reactor Netty, Tomcat, and Jetty.

If you need to configure idle timeouts, frame sizes, or server-specific options, check the strategy corresponding to your running server. Do not apply a Tomcat strategy class to an application running on Reactor Netty.

## 15. WebSocketHandlerAdapter and URL Mapping

WebSocketHandlerAdapter enables DispatcherHandler to invoke a WebSocketHandler. The adapter receives a WebSocketService, defaulting to HandshakeWebSocketService, and delegates handshake handling to it.

In Spring WebFlux Java configuration, the adapter is registered automatically. In a Spring Boot application using WebFlux auto-configuration, you normally do not need to declare this bean manually.

You must map a URL to the handler using a HandlerMapping. A simple approach is SimpleUrlHandlerMapping:

~~~java
@Configuration
public class WebSocketMappingConfiguration {

    @Bean
    public HandlerMapping webSocketHandlerMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }
}
~~~

Order -1 places this mapping before annotated controller mappings per common Spring examples. When a request arrives at /ws/echo, WebFlux locates the WebSocketHandler and invokes WebSocketHandlerAdapter to perform the handshake.

If you do not use WebFlux Java configuration, the application must declare WebSocketHandlerAdapter manually. When using Spring Boot, keep auto-configuration intact and only add the needed WebFluxConfigurer; do not add @EnableWebFlux unless you intentionally want to replace Boot's default configuration.

## 16. Customizing HandshakeWebSocketService via WebFluxConfigurer

In some cases, you need to customize the WebSocketService used by WebSocketHandlerAdapter. WebFluxConfigurer provides getWebSocketService() to supply a custom service.

One feature of HandshakeWebSocketService is sessionAttributePredicate. This predicate selects attributes from WebSession to copy into the WebSocketSession attributes.

Example:

~~~java
@Configuration
public class WebSocketConfiguration implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> "userId".equals(name));

        return service;
    }
}
~~~

In this example, only the attribute named userId is selected to be transferred from WebSession to WebSocketSession.

This does not authenticate the user on its own and does not create userId. The attribute must be set on the server after authentication or a trusted processing step. Do not copy all WebSession attributes unnecessarily; select only the exact data the handler needs.

If you want to customize RequestUpgradeStrategy, you can construct HandshakeWebSocketService with the corresponding strategy. The strategy must match the running HTTP server. When using WebFluxConfigurer, the WebFlux configuration uses the service returned by getWebSocketService() to build the adapter.

## 17. Subprotocols and Application Protocol Negotiation

WebSocket is a bidirectional transport. Applications can define subprotocols to agree on message schemas and semantics.

For example:

- chat.v1: chat messages version 1.
- notifications.v1: realtime notifications.
- telemetry.v2: telemetry data version 2.

WebSocketHandler has a getSubProtocols() method returning the list of subprotocols supported by the handler. The client can send Sec-WebSocket-Protocol during the handshake to propose one or more protocols. The server selects a compatible protocol during the handshake.

Example of a handler supporting a subprotocol:

~~~java
@Component
public class ChatWebSocketHandler implements WebSocketHandler {

    @Override
    public List<String> getSubProtocols() {
        return List.of("chat.v1");
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        log.info(
            "Negotiated protocol: {}",
            session.getHandshakeInfo().getSubProtocol());

        return session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("chat: " + text))
            .as(session::send);
    }
}
~~~

The client needs to offer chat.v1. After the handshake, session.getHandshakeInfo().getSubProtocol() reveals the negotiated protocol; if no protocol was selected, the value may be null.

A subprotocol is part of the communication contract, not just a decorative name. Both sides must agree on message schema, versioning, error format, authentication behavior, and close semantics.

## 18. Securing WebSocket Endpoints

The handshake is an HTTP request before the connection is upgraded. Therefore, authentication and authorization can be applied at the HTTP security layer before WebSocketHandler runs.

Key principles:

- Require authentication before allowing an upgrade if the endpoint is private.
- Check which rooms, tenants, or channels the user is authorized to connect to.
- Validate Origin against an allowlist appropriate for browser clients.
- Do not treat Origin as authentication; it only indicates the website initiating the request.
- With cookie/session authentication, assess cross-site WebSocket hijacking and CSRF risks according to your application architecture.
- Use WSS in production to encrypt data in transit.
- Limit message size, send rate, and concurrent session count.
- Validate every payload; do not trust data sent by clients.
- Log the session ID, appropriate principal ID, close code, and correlation ID; avoid logging tokens or sensitive payloads.

CORS and WebSocket are not the same. A WebSocket handshake includes an Origin header, but it does not behave like a fetch request flow with standard CORS preflight. Configuring CORS for REST endpoints does not automatically prove a WebSocket endpoint is secure. Enforce Origin validation and authorization using your application's WebSocket security mechanisms.

HandshakeWebSocketService is responsible for the handshake and upgrade, not for replacing your application's security policy. If using Spring Security WebFlux, configure SecurityWebFilterChain to authenticate and authorize WebSocket paths before the request is upgraded.

## 19. Complete Java 17+ Example with Spring Boot WebFlux

This example creates a WebSocket echo endpoint at /ws/echo. The client sends a text message, and the server replies with the content prefixed by echo. The configuration uses SimpleUrlHandlerMapping and WebFluxConfigurer to customize HandshakeWebSocketService.

### Project Structure

~~~text
webflux-websocket-demo/
├── pom.xml
└── src
    ├── main/java/com/example/websocket
    │   ├── WebSocketDemoApplication.java
    │   ├── WebSocketConfiguration.java
    │   └── EchoWebSocketHandler.java
    └── test/java/com/example/websocket
        └── WebSocketEchoIntegrationTest.java
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
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-websocket-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
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

Spring Boot 3.3.5 manages compatible Spring Framework 6.1 and Reactor versions. The example uses Java 17.

### WebSocketDemoApplication.java

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

### EchoWebSocketHandler.java

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class EchoWebSocketHandler implements WebSocketHandler {

    private static final Logger log =
        LoggerFactory.getLogger(EchoWebSocketHandler.class);

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        log.info("WebSocket connected: {}", session.getId());

        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies)
            .doFinally(signal ->
                log.info(
                    "WebSocket finished: {}, signal={}",
                    session.getId(), signal));
    }
}
~~~

The handler only processes text messages. The pipeline receives text, creates a response text message, and passes the publisher to session.send(). doFinally logs when the session completes, errors, or is cancelled.

### WebSocketConfiguration.java

~~~java
package com.example.websocket;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.server.WebSocketService;
import org.springframework.web.reactive.socket.server.support.HandshakeWebSocketService;

@Configuration
public class WebSocketConfiguration implements WebFluxConfigurer {

    @Bean
    public HandlerMapping webSocketHandlerMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/echo", handler);

        SimpleUrlHandlerMapping mapping =
            new SimpleUrlHandlerMapping();

        mapping.setUrlMap(handlers);
        mapping.setOrder(-1);

        return mapping;
    }

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> "userId".equals(name));

        return service;
    }
}
~~~

The mapping registers the /ws/echo path. getWebSocketService() provides a customized HandshakeWebSocketService; the service only transfers the userId attribute from WebSession if that attribute exists. In a production application, userId must be set from server-side authentication/session logic.

Spring Boot WebFlux auto-configuration provides WebSocketHandlerAdapter. There is no need to create a second adapter in this configuration. If the application does not use WebFlux Java configuration, the adapter must be declared according to the corresponding setup.

### WebSocketEchoIntegrationTest.java

~~~java
package com.example.websocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.LocalServerPort;
import org.springframework.boot.test.context.SpringBootTest;

import org.springframework.web.reactive.socket.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketEchoIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void echoesTextMessageOverRealWebSocketConnection() {
        WebSocketClient client =
            new ReactorNettyWebSocketClient();

        AtomicReference<String> received =
            new AtomicReference<>();

        URI uri = URI.create(
            "ws://127.0.0.1:" + port + "/ws/echo");

        Mono<Void> conversation = client.execute(uri, session ->
            session.send(
                    Mono.just(session.textMessage("hello")))
                .thenMany(session.receive().take(1))
                .doOnNext(message ->
                    received.set(message.getPayloadAsText()))
                .then()
        );

        StepVerifier.create(conversation)
            .expectComplete()
            .verify(Duration.ofSeconds(5));

        assertEquals("echo: hello", received.get());
    }
}
~~~

The test starts an embedded server on a random port, uses ReactorNettyWebSocketClient to open a real connection, sends hello, and receives one message. The expected result is echo: hello.

Run the test from the directory containing pom.xml:

~~~bash
mvn -q test
~~~

If the test passes, Maven exits with code 0. This is an integration test for the handshake and message exchange, not merely a unit test of a String transformation function.

### Running the Application and Testing the Connection

Start the application:

~~~bash
mvn spring-boot:run
~~~

You can use JavaScript in the browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
  console.log("connected");
  socket.send("hello");
});

socket.addEventListener("message", event => {
  console.log("server:", event.data);
});

socket.addEventListener("close", event => {
  console.log("closed:", event.code, event.reason);
});

socket.addEventListener("error", error => {
  console.error("websocket error", error);
});
~~~

Expected message output:

~~~text
connected
server: echo: hello
~~~

The browser console is a test client. In production, the URL normally uses wss:// once HTTPS is deployed.

## 20. Testing and Troubleshooting WebSocket

A WebSocket endpoint should be tested across multiple layers:

- Handler logic: message transformation, payload validation, error handling.
- Handshake: correct URL, upgrade accepted, subprotocol negotiated.
- Session: receiving and sending messages, close status, disconnect.
- Security: unauthenticated requests rejected, unauthorized users cannot connect.
- Capacity: many concurrent sessions, large messages, high send rates.
- Lifecycle: server shutdown, client disconnect, and cleanup.

Diagnostic symptoms:

| Symptom | What to Check |
| --- | --- |
| HTTP 404 before upgrade | URL mapping and HandlerMapping order |
| HTTP 400 on handshake | Upgrade headers, key/version, and request format |
| HTTP 401/403 | Authentication, authorization, or Origin policy |
| Handshake succeeds but no messages arrive | Handler mapping, receive/send pipeline, and client events |
| Messages are lost | Publisher cancelled, handler completed early, or processing error |
| Messages arrive out of order | flatMap concurrency or multiple producers sending concurrently |
| Connection closes prematurely | Mono<Void> completed, exception, or timeout |
| Memory grows with session count | Unbounded buffering, session registry, or missing cleanup |
| Disconnects happen only in production | Proxy idle timeout, load balancer, heartbeat, or TLS |

When using a reverse proxy, enable WebSocket upgrade support and configure appropriate timeouts. A proxy may close an idle connection even though the application still holds the session. For long-lived connections, consider heartbeats or ping/pong and monitor idle timeouts at each layer.

## 21. Common Mistakes and Fixes

1. **Thinking WebSocketHandler is a regular controller.** A handler manages a long-lived session and returns Mono<Void> reflecting the session's lifecycle.
2. **Not mapping the handler to a URL.** Creating a WebSocketHandler bean is not enough; a HandlerMapping is required to route the handshake.
3. **Declaring a duplicate WebSocketHandlerAdapter.** WebFlux configuration already registers the adapter; only declare it manually when not using that configuration.
4. **Confusing HandshakeWebSocketService with the message handler.** The service performs the handshake and upgrade; WebSocketHandler processes messages after the upgrade.
5. **Calling subscribe() inside handle().** This detaches work from the Spring-managed lifecycle; return a composed publisher instead.
6. **Only calling receive() without returning the publisher.** The handler may finish before the stream is processed; return Mono<Void> from the pipeline.
7. **Calling send() concurrently multiple times on the same session.** This can cause write contention; combine outbound messages into one publisher and call send once.
8. **Not handling client disconnect.** receive() can complete or error; use doFinally to clean up session state.
9. **Using flatMap when message order is required.** Results may return out of order; use concatMap when sequential processing is needed.
10. **Using unbounded buffers.** Load spikes can exhaust memory; bound queues and define overflow behavior.
11. **Blocking the event loop.** Synchronous I/O or heavy CPU work slows down many sessions; use reactive clients or an appropriate scheduler.
12. **Not limiting payload size.** Overly large messages can increase memory usage and decoding cost; configure limits on the server strategy and check sizes at the application layer.
13. **Holding DataBuffer without proper retain/release.** This can cause use-after-release errors or memory leaks; manage the buffer lifecycle per WebFlux guidelines.
14. **Trusting userId in the query string.** Clients can forge the value; use Principal or attributes set by server-side authentication.
15. **Not validating Origin.** Cookie-authenticated WebSockets can suffer cross-site hijacking risks; use an allowlist and security policies.
16. **Using CORS instead of authentication.** CORS does not authenticate users and does not replace authorization.
17. **Not handling close codes.** Clients struggle to distinguish normal closure, policy violations, and server errors; use meaningful close statuses.
18. **Sending reserved close codes.** Do not send codes 1005 or 1006 in close frames.
19. **Missing heartbeats for idle connections.** Proxies/load balancers may close sessions; configure ping/pong or heartbeats as needed.
20. **Not testing the real handshake.** Unit testing the handler misses mapping or upgrade errors; add integration tests using WebSocketClient.

## 22. WebSocket Endpoint Design Checklist

Before releasing an endpoint, verify:

- **URL mapping:** which path maps to the handler?
- **Handshake:** does the server strategy match the running HTTP server?
- **Adapter:** is WebSocketHandlerAdapter already provided by WebFlux config?
- **Session lifecycle:** when does the handler complete?
- **Inbound:** text, binary, or both?
- **Outbound:** a single publisher or multiple sources to merge?
- **Ordering:** must messages preserve strict order?
- **Backpressure:** are queues and concurrency bounded?
- **Payload size:** what is the maximum allowed message size?
- **Error policy:** are business errors sent as messages or close frames?
- **Close status:** are close codes and reasons clear?
- **Authentication:** is the handshake authenticated before upgrade?
- **Authorization:** is the user allowed to join the room/channel/resource?
- **Origin:** is the browser origin validated?
- **Subprotocol:** do client and server agree on version and message schema?
- **Observability:** are logs, metrics, session counts, duration, and close reasons recorded?
- **Proxy:** do load balancers and reverse proxies support upgrade, idle timeouts, and heartbeats?
- **Tests:** are handshake, echo, disconnect, errors, and security tested?

## 23. Self-Check Exercises

**Exercise 1.** What object does WebSocketHandler.handle() receive and what type does it return?  
**Answer:** It receives WebSocketSession and returns Mono<Void> to represent the session processing lifetime.

**Exercise 2.** What publisher type does receive() return?  
**Answer:** Flux<WebSocketMessage> containing inbound messages.

**Exercise 3.** What does send() accept and what does it return?  
**Answer:** It accepts Publisher<WebSocketMessage> and returns Mono<Void> that completes when writing the message source finishes.

**Exercise 4.** What does WebSocketSession.getHandshakeInfo() provide?  
**Answer:** URI, headers, cookies, principal, subprotocol, remote address, and handshake attributes.

**Exercise 5.** What performs the HTTP handshake and upgrade?  
**Answer:** WebSocketService, defaulting to HandshakeWebSocketService, using the RequestUpgradeStrategy matching the server.

**Exercise 6.** What is the role of WebSocketHandlerAdapter?  
**Answer:** It enables DispatcherHandler to invoke WebSocketHandler and delegates the request to WebSocketService.

**Exercise 7.** What is SimpleUrlHandlerMapping used for?  
**Answer:** Mapping URL paths such as /ws/echo to a WebSocketHandler.

**Exercise 8.** Why should you not call subscribe() inside handle()?  
**Answer:** Because it detaches the subscription from the Spring-managed lifecycle and makes error/cancellation propagation difficult.

**Exercise 9.** When should you use concatMap instead of flatMap?  
**Answer:** When sequential processing is needed to preserve inbound message order.

**Exercise 10.** What does HandshakeWebSocketService.setSessionAttributePredicate() do?  
**Answer:** Selects attributes from WebSession to transfer into WebSocketSession attributes.

**Exercise 11.** What type does getPrincipal() return?  
**Answer:** Mono<Principal>, because the principal is provided through a reactive API.

**Exercise 12.** When a client disconnects, what should the handler do?  
**Answer:** Allow receive/send to emit terminal signals, finish the flow, and clean up resources in doFinally or the appropriate lifecycle hook.

**Exercise 13.** Where is the subprotocol read after the handshake?  
**Answer:** HandshakeInfo.getSubProtocol().

**Exercise 14.** Why is Origin validation necessary for WebSockets using cookie authentication?  
**Answer:** To reduce the risk of another website opening a connection using the user's cookies and acting on an authenticated session.

**Exercise 15.** What does HTTP status 101 mean in an HTTP/1.1 handshake?  
**Answer:** Switching Protocols; the server accepts upgrading to WebSocket.

## 24. Key Takeaways

WebSocketHandler contains session handling logic and returns Mono<Void>. WebSocketSession represents the connection, providing metadata, receive() for inbound messages, send() for outbound messages, and close() to end the session. Handlers must compose publishers into a single flow; do not subscribe manually or block.

WebSocketHandlerAdapter connects WebSocketHandler to DispatcherHandler. HandlerMapping maps URLs to handlers. By default, the adapter uses HandshakeWebSocketService to validate the HTTP handshake and invoke the server's RequestUpgradeStrategy to perform the upgrade. WebFluxConfigurer.getWebSocketService() lets you provide a customized service, such as selecting attributes from WebSession to copy into WebSocketSession.

After the upgrade, data is exchanged as WebSocket messages rather than independent HTTP responses. Control message ordering, backpressure, payload size, cancellation, close codes, and per-session resources. Protect the handshake with authentication, authorization, and an Origin policy; use subprotocols when versioning the message contract. Test both the real handshake and message exchange to verify the endpoint works end-to-end.

### References

- Spring Framework, [WebSockets in Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html).
- Spring Framework, [WebFlux Configuration – WebSocketService](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework Javadoc, [WebSocketHandler](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html).
- Spring Framework Javadoc, [WebSocketSession](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html).
- Spring Framework Javadoc, [HandshakeInfo](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/HandshakeInfo.html).
- Spring Framework Javadoc, [HandshakeWebSocketService](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html).
- Spring Framework Javadoc, [WebSocketHandlerAdapter](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/socket/server/support/WebSocketHandlerAdapter.html).
- Spring Framework, [Reactive Web Application Architecture](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- IETF, [The WebSocket Protocol – RFC 6455](https://www.rfc-editor.org/rfc/rfc6455).
