# Handler Path Registration and Handshake Configuration

Spring WebFlux provides a reactive WebSocket API for building bidirectional connections between client and server. A WebSocket connection begins with an HTTP handshake: the client sends an HTTP GET with Upgrade, Connection, Sec-WebSocket-Key, and Sec-WebSocket-Version headers; the server validates the request and upgrades the connection. When the handshake succeeds, the server returns status 101 Switching Protocols, and both sides exchange messages over the same connection.

In WebFlux, WebSocket endpoints are not registered with controller annotations like regular REST routes. The application creates a WebSocketHandler instance, maps a URL to the handler using a HandlerMapping (commonly SimpleUrlHandlerMapping), and then WebSocketHandlerAdapter forwards the handshake request to WebSocketService. By default, WebSocketService uses HandshakeWebSocketService, which invokes the RequestUpgradeStrategy corresponding to the running server engine.

This lesson focuses on path registration, HandlerMapping ordering, handshake configuration, subprotocols, Origin/CORS, session attributes, frame limits, and how to test a WebSocket endpoint with a reactive client.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the HTTP Upgrade flow and status 101 of the WebSocket handshake.
2. Create a WebSocketHandler that processes inbound and outbound messages reactively.
3. Register multiple URLs using SimpleUrlHandlerMapping.
4. Choose an order so WebSocket mappings are evaluated before annotated controller mappings.
5. Understand the roles of WebSocketHandlerAdapter and WebSocketService.
6. Configure HandshakeWebSocketService via WebFluxConfigurer.
7. Select RequestUpgradeStrategy for Reactor Netty, Tomcat, or Jetty.
8. Negotiate subprotocols using WebSocketHandler.getSubProtocols().
9. Control Origin using CorsConfigurationSource or CORS mappings.
10. Transfer selected WebSession attributes into WebSocketSession.
11. Limit frame size and understand ping/pong and compression.
12. Protect the handshake with authentication, authorization, and an origin allowlist.
13. Test handshake, subprotocol negotiation, message echo, and origin rejection.

## 2. How Does the WebSocket Handshake Work?

WebSocket uses HTTP to initiate a connection. The client sends a GET request with special headers:

~~~http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1
Origin: https://app.example.test
~~~

Meaning of the headers:

| Header | Role |
| --- | --- |
| Upgrade | Requests switching the protocol to websocket |
| Connection | Indicates that Upgrade is a hop-by-hop connection option |
| Sec-WebSocket-Key | Client-generated nonce for the server to verify the handshake |
| Sec-WebSocket-Version | WebSocket protocol version, typically 13 |
| Sec-WebSocket-Protocol | Subprotocols the client wants to negotiate |
| Origin | Origin of the page initiating the connection, important for browser clients |

If the handshake is valid, the server returns a response like:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
Sec-WebSocket-Protocol: chat.v1
~~~

Status 101 indicates the connection has been upgraded. From this point on, both sides send WebSocket frames over the open connection; it is no longer a sequence of regular HTTP requests and responses.

The handshake can fail if the method/headers/version are invalid, the origin is rejected, authentication fails, the endpoint does not exist, or the server engine cannot upgrade the connection.

## 3. WebFlux WebSocket Server Components

A WebFlux endpoint typically consists of four components:

| Component | Responsibility |
| --- | --- |
| WebSocketHandler | Processes messages within a session |
| HandlerMapping | Maps URLs to WebSocketHandler |
| WebSocketHandlerAdapter | Connects the handler to DispatcherHandler |
| WebSocketService | Handles the handshake and invokes the upgrade strategy |

Request flow:

~~~text
HTTP GET /ws/echo
       |
       v
DispatcherHandler
       |
       v
SimpleUrlHandlerMapping
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
WebSocketHandler.handle(session)
       |
       v
WebSocket messages
~~~

In applications using WebFlux Java configuration (including the WebFlux configuration provided by Spring Boot), WebSocketHandlerAdapter is registered automatically. The application only needs to map WebSocketHandler to a URL. If not using WebFlux configuration, you must declare the adapter manually.

There is no need to add @EnableWebFlux just to register a WebSocket handler in Spring Boot. Implement WebFluxConfigurer to customize configuration while preserving Boot's auto-configuration.

## 4. Creating a WebSocketHandler

The WebSocketHandler interface has one method:

~~~java
Mono<Void> handle(WebSocketSession session);
~~~

The Mono<Void> publisher represents the session handling lifecycle. A session has two main streams:

| API | Description |
| --- | --- |
| session.receive() | Flux<WebSocketMessage> containing messages sent by the client |
| session.send(Publisher<WebSocketMessage>) | Sends messages produced by the server |
| session.close() | Closes the WebSocket session |
| session.getHandshakeInfo() | Handshake details: URI, headers, principal, subprotocol, and attributes |
| session.getAttributes() | Attributes attached to the session |

The handler must combine inbound and outbound into a single reactive flow and return the publisher representing the work. Do not subscribe manually to receive or send; WebFlux must control subscription, cancellation, and session closure.

### 4.1. Text Echo Handler

The following example receives text messages and sends them back prefixed with echo:

~~~java
final class EchoWebSocketHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(message ->
                session.textMessage(
                    "echo: " + message.getPayloadAsText()
                )
            );

        return session.send(replies);
    }
}
~~~

This handler assumes the client sends text messages. If the endpoint must accept binary messages, check the message type and handle binary payloads separately.

The flow above preserves backpressure: the server only produces output based on the inbound publisher and downstream demand. When the client closes the connection, receive completes; send also completes and the Mono<Void> finishes.

### 4.2. Combining Independent Input and Output

A handler can receive data and send another data source:

~~~java
@Override
public Mono<Void> handle(WebSocketSession session) {
    Mono<Void> input = session.receive()
        .concatMap(message -> processIncoming(message))
        .then();

    Flux<String> notifications = notificationSource();

    Mono<Void> output = session.send(
        notifications.map(session::textMessage)
    );

    return input.and(output);
}
~~~

This is an illustrative pattern; processIncoming and notificationSource are application business APIs. The and operator combines the lifecycles of both streams. When one stream completes, the combined publisher terminates and the other stream is cancelled according to the operator's semantics.

Do not use block or subscribe inside the handler. If you must call a database/network, prefer reactive APIs; if there are blocking operations, offload them to an appropriate scheduler and manage concurrency limits.

## 5. Registering Paths with SimpleUrlHandlerMapping

WebFlux uses HandlerMapping to look up handlers by URL. The common approach is creating a map from path to WebSocketHandler:

~~~java
@Configuration
class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(EchoWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        int order = -1; // before annotated controller mappings

        return new SimpleUrlHandlerMapping(handlers, order);
    }

    @Bean
    EchoWebSocketHandler echoWebSocketHandler() {
        return new EchoWebSocketHandler();
    }
}
~~~

SimpleUrlHandlerMapping accepts a URL map and an order. Multiple endpoints can be registered:

~~~java
Map<String, WebSocketHandler> handlers = new HashMap<>();
handlers.put("/ws/chat", chatHandler);
handlers.put("/ws/notifications", notificationHandler);
handlers.put("/ws/echo", echoHandler);

return new SimpleUrlHandlerMapping(handlers, -1);
~~~

### 5.1. Why Is Order Usually -1?

Spring WebFlux has multiple HandlerMappings. Annotated controller mappings also resolve URLs for methods annotated with @GetMapping, @PostMapping, and related annotations.

WebSocket mappings are typically given order -1 so they are evaluated before annotated controller mappings. If two mappings could match the same path, the order can determine which handler receives the request.

Do not place two different handlers on the same URL without clear precedence rules. Reserve distinct prefixes such as /ws/** for WebSocket endpoints and /api/** for REST endpoints so routing remains clear.

### 5.2. URL Patterns

SimpleUrlHandlerMapping supports URL patterns. For example:

~~~java
handlers.put("/ws/**", chatHandler);
~~~

Use a broad pattern only when a single handler can genuinely serve every path underneath. If different handlers are needed per tenant, room, or feature, use multiple specific patterns or a single handler that reads the path/handshake metadata and enforces permissions.

Registering a route does not mean the endpoint is protected. Every path still needs appropriate authentication, authorization, and origin checks.

## 6. WebSocketHandlerAdapter and WebFlux Configuration

WebSocketHandlerAdapter is the HandlerAdapter for handlers of type WebSocketHandler. In applications using WebFlux configuration, the adapter is declared automatically.

If not using WebFlux configuration, you can declare it manually:

~~~java
@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter() {
    return new WebSocketHandlerAdapter();
}
~~~

If a custom WebSocketService is needed, the adapter has a constructor accepting the service:

~~~java
@Bean
WebSocketHandlerAdapter webSocketHandlerAdapter(
        WebSocketService webSocketService) {
    return new WebSocketHandlerAdapter(webSocketService);
}
~~~

Do not create a second adapter when WebFlux configuration has already registered the default adapter. Instead, override WebFluxConfigurer.getWebSocketService() to supply a customized service.

## 7. HandshakeWebSocketService

WebSocketHandlerAdapter delegates the handshake to WebSocketService. By default, WebFlux uses HandshakeWebSocketService.

This service performs basic handshake checks and then calls the RequestUpgradeStrategy matching the current server engine. Supported servers can include Reactor Netty, Tomcat, and Jetty; the exact list depends on the Spring Framework version.

HandshakeWebSocketService has a default constructor that auto-detects the strategy from the classpath:

~~~java
HandshakeWebSocketService service =
    new HandshakeWebSocketService();
~~~

Or pass a specific strategy:

~~~java
HandshakeWebSocketService service =
    new HandshakeWebSocketService(requestUpgradeStrategy);
~~~

### 7.1. Customizing via WebFluxConfigurer

When using WebFlux Java configuration, override getWebSocketService():

~~~java
@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        HandshakeWebSocketService service =
            new HandshakeWebSocketService();

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}
~~~

This example keeps the auto-detected strategy and only configures copying session attributes. It does not create a new adapter.

### 7.2. Session Attribute Predicate

A WebSocket handshake can use a previously existing WebSession. HandshakeWebSocketService lets you select keys from WebSession to copy into WebSocketSession attributes:

~~~java
service.setSessionAttributePredicate(
    name -> name.startsWith("ws.")
);
~~~

If WebSession has keys ws.userId and ws.tenantId, the predicate above allows them to be copied into WebSocketSession attributes. Other keys are not copied.

This mechanism only transfers attributes. It does not authenticate the user, automatically establish tenant context, or replace authorization. The application must place those values into WebSession from an authenticated source prior to the handshake.

## 8. RequestUpgradeStrategy and Server Engine Configuration

RequestUpgradeStrategy is the abstraction Spring uses to perform the HTTP-to-WebSocket upgrade on a specific server engine.

- ReactorNettyRequestUpgradeStrategy is for Reactor Netty.
- TomcatRequestUpgradeStrategy is for Tomcat.
- JettyRequestUpgradeStrategy is for Jetty.

Options differ across servers. Only configure the strategy for the engine the application actually runs.

### 8.1. Reactor Netty Example: Frame Payload Limit

Reactor Netty allows creating the strategy with WebsocketServerSpec.Builder:

~~~java
ReactorNettyRequestUpgradeStrategy strategy =
    new ReactorNettyRequestUpgradeStrategy(
        () -> WebsocketServerSpec.builder()
            .maxFramePayloadLength(128 * 1024)
    );

HandshakeWebSocketService service =
    new HandshakeWebSocketService(strategy);
~~~

This example sets the per-frame payload limit to 128 KiB. This is a frame limit, not a limit on the total data a session can exchange. If a message is larger, the client may need to split the data into multiple frames or the application needs an appropriate limit.

The Reactor Netty builder also has options related to ping handling and compression. Enable compression only when needed and after evaluating CPU/memory costs as well as security risks of compressed data.

### 8.2. Tomcat Example: Idle Timeout

If the application runs on Tomcat and you want to customize the idle timeout, Spring provides an example:

~~~java
TomcatRequestUpgradeStrategy strategy =
    new TomcatRequestUpgradeStrategy();

strategy.setMaxSessionIdleTimeout(60_000L);

HandshakeWebSocketService service =
    new HandshakeWebSocketService(strategy);
~~~

The value 60,000 ms corresponds to 60 seconds. This example is specific to Tomcat; do not use this API when the server is Reactor Netty.

### 8.3. Integrating Strategy into WebFluxConfigurer

With Reactor Netty, you can combine frame limits and a session attribute predicate:

~~~java
@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Override
    public WebSocketService getWebSocketService() {
        ReactorNettyRequestUpgradeStrategy strategy =
            new ReactorNettyRequestUpgradeStrategy(
                () -> WebsocketServerSpec.builder()
                    .maxFramePayloadLength(128 * 1024)
            );

        HandshakeWebSocketService service =
            new HandshakeWebSocketService(strategy);

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}
~~~

This configuration is intended for an application actually running Reactor Netty. If switching to Tomcat or Jetty, choose the corresponding RequestUpgradeStrategy.

## 9. Subprotocol Negotiation

The WebSocket protocol lets both sides negotiate a subprotocol via the Sec-WebSocket-Protocol header.

The client can send:

~~~http
Sec-WebSocket-Protocol: chat.v1, chat.v2
~~~

The handler declares the protocols the server supports using:

~~~java
@Override
public List<String> getSubProtocols() {
    return List.of("chat.v1", "chat.v2");
}
~~~

Spring selects a matching protocol from those proposed by the client and supported by the server. The chosen protocol can be read via:

~~~java
String protocol =
    session.getHandshakeInfo().getSubProtocol();
~~~

A subprotocol defines the application-level message contract, such as JSON chat format, STOMP, or a custom business protocol. It does not replace WebSocket framing and is not a compression extension.

If the application requires a mandatory subprotocol, inspect the negotiation result and reject the session if no matching protocol is present. Do not assume every client sends this header.

## 10. Controlling Origin and CORS

Browsers send the Origin header during the WebSocket handshake. The server must decide which origins are allowed to connect.

In WebFlux, the direct way is to have WebSocketHandler implement CorsConfigurationSource:

~~~java
final class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    EchoWebSocketHandler() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        config.setAllowedMethods(List.of("GET"));
        this.corsConfiguration = config;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return this.corsConfiguration;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()
                ))
        );
    }
}
~~~

Only the origin https://app.example.test is allowed under this configuration. In production, use an exact allowlist of origins; do not enable wildcards merely to fix connection errors.

### 10.1. Configuring CORS by URL Pattern

If you do not want the handler to implement CorsConfigurationSource, you can set CORS mappings on SimpleUrlHandlerMapping:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(
    List.of("https://app.example.test")
);
cors.setAllowedMethods(List.of("GET"));

Map<String, CorsConfiguration> corsMap = new HashMap<>();
corsMap.put("/ws/**", cors);

SimpleUrlHandlerMapping mapping =
    new SimpleUrlHandlerMapping(handlers, -1);

mapping.setCorsConfigurations(corsMap);
~~~

If both the handler and the mapping provide CORS configurations, Spring combines them according to CorsConfiguration.combine rules. Avoid unintended overlapping configurations.

### 10.2. Origin Is Not Authentication

Origin validation primarily protects browser clients from an unauthorized page opening a connection to your endpoint. Non-browser clients can send any arbitrary Origin header.

Therefore:

- Authenticate the principal using Spring Security or an equivalent mechanism.
- Verify the principal is authorized to access the requested room, tenant, or resource.
- Use an origin allowlist for browsers.
- Do not treat Origin as proof of user identity.
- Do not put sensitive tokens in query strings because URLs can appear in logs or proxy history.
- If using cookie/session authentication, account for cross-site WebSocket hijacking risks and appropriate cookie policies.

## 11. Authentication and Authorization at the Handshake

The handshake is an HTTP GET before the protocol is upgraded. Spring Security WebFlux can protect the path just like a regular HTTP endpoint.

Illustrative security configuration example:

~~~java
@Bean
SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/ws/**").authenticated()
            .anyExchange().permitAll()
        )
        .build();
}
~~~

Actual configuration also depends on the authentication mechanism, CSRF policy, and other endpoints. After the handshake, the handler must still check permissions on every sensitive operation, such as subscribing to a room or sending messages to another tenant.

A successful handshake does not mean the user is allowed to perform every action on the session. Authorization may need to be re-checked whenever a message carries a room ID or resource ID.

## 12. Client Sending Subprotocol and Opening a Connection

Spring WebFlux provides the WebSocketClient abstraction. With Reactor Netty:

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();

URI uri = URI.create("ws://localhost:8080/ws/echo");

client.execute(uri, session ->
    session.send(Mono.just(session.textMessage("hello")))
        .then(
            session.receive()
                .take(1)
                .doOnNext(message ->
                    System.out.println(message.getPayloadAsText())
                )
                .then()
        )
);
~~~

This snippet sends one text message and reads one response. In real applications, compose send/receive according to the session lifecycle and subscribe at the calling layer. Do not call block on the event loop.

If handshake headers such as Origin or Sec-WebSocket-Protocol must be sent, use the execute overload accepting HttpHeaders:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.set("Origin", "https://app.example.test");
headers.set("Sec-WebSocket-Protocol", "chat.v1");

client.execute(uri, headers, session ->
    session.receive().then()
);
~~~

The client must offer a subprotocol supported by the server. Once the handshake succeeds, the client can inspect session.getHandshakeInfo().getSubProtocol().

## 13. Runnable Java 17 Example with Spring Boot WebFlux

This example uses Java 17, Spring Boot 3.3.5, and Reactor Netty. It registers the /ws/echo endpoint, accepts only the configured origin, negotiates the chat.v1 subprotocol, and bounds frame payloads.

### 13.1. Project Structure

~~~text
webflux-websocket-demo/
├── build.gradle
├── src/main/java/demo/WebSocketApplication.java
└── src/test/java/demo/WebSocketIntegrationTest.java
~~~

### 13.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 13.3. WebSocketApplication.java

~~~java
package demo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;
import org.springframework.web.reactive.socket.server.WebSocketService;
import org.springframework.web.reactive.socket.server.support.HandshakeWebSocketService;
import org.springframework.web.reactive.socket.server.upgrade.ReactorNettyRequestUpgradeStrategy;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;
import reactor.netty.http.server.WebsocketServerSpec;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}

@Configuration
class WebSocketConfig implements WebFluxConfigurer {

    @Bean
    EchoWebSocketHandler echoWebSocketHandler() {
        return new EchoWebSocketHandler();
    }

    @Bean
    HandlerMapping webSocketMapping(
            EchoWebSocketHandler handler) {

        Map<String, WebSocketHandler> handlers = new HashMap<>();
        handlers.put("/ws/echo", handler);

        return new SimpleUrlHandlerMapping(handlers, -1);
    }

    @Override
    public WebSocketService getWebSocketService() {
        ReactorNettyRequestUpgradeStrategy strategy =
            new ReactorNettyRequestUpgradeStrategy(
                () -> WebsocketServerSpec.builder()
                    .maxFramePayloadLength(128 * 1024)
            );

        HandshakeWebSocketService service =
            new HandshakeWebSocketService(strategy);

        service.setSessionAttributePredicate(
            name -> name.startsWith("ws.")
        );

        return service;
    }
}

final class EchoWebSocketHandler
        implements WebSocketHandler, CorsConfigurationSource {

    private final CorsConfiguration corsConfiguration;

    EchoWebSocketHandler() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        config.setAllowedMethods(List.of("GET"));
        this.corsConfiguration = config;
    }

    @Override
    public CorsConfiguration getCorsConfiguration(
            ServerWebExchange exchange) {
        return this.corsConfiguration;
    }

    @Override
    public List<String> getSubProtocols() {
        return List.of("chat.v1");
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.send(
            session.receive()
                .map(message -> session.textMessage(
                    "echo: " + message.getPayloadAsText()
                ))
        );
    }
}
~~~

Supporting types are declared package-private in the same file to keep the example concise. In a real project, separate handlers, configs, and DTOs into distinct files.

### 13.4. WebSocketIntegrationTest.java

~~~java
package demo;

import java.net.URI;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;

import org.springframework.web.reactive.socket.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WebSocketIntegrationTest {

    @LocalServerPort
    int port;

    private final WebSocketClient client =
        new ReactorNettyWebSocketClient();

    private URI endpoint() {
        return URI.create(
            "ws://localhost:" + port + "/ws/echo"
        );
    }

    @Test
    void handshakeNegotiatesProtocolAndEchoesMessage() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("Origin", "https://app.example.test");
        headers.set("Sec-WebSocket-Protocol", "chat.v1");

        AtomicReference<String> protocol = new AtomicReference<>();
        AtomicReference<String> reply = new AtomicReference<>();

        client.execute(endpoint(), headers, session -> {
            protocol.set(
                session.getHandshakeInfo().getSubProtocol()
            );

            Mono<Void> send = session.send(
                Mono.just(session.textMessage("ping"))
            );

            Mono<Void> receive = session.receive()
                .take(1)
                .doOnNext(message ->
                    reply.set(message.getPayloadAsText())
                )
                .then();

            return Mono.when(send, receive);
        }).block(Duration.ofSeconds(5));

        assertEquals("chat.v1", protocol.get());
        assertEquals("echo: ping", reply.get());
    }

    @Test
    void handshakeRejectsUnlistedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("Origin", "https://evil.example.test");
        headers.set("Sec-WebSocket-Protocol", "chat.v1");

        StepVerifier.create(
            client.execute(endpoint(), headers, session ->
                session.receive().then()
            )
        )
        .expectError()
        .verify(Duration.ofSeconds(5));
    }
}
~~~

The first test verifies that the handshake succeeds, the subprotocol is selected, and the server echoes the message. The second test verifies that an origin outside the allowlist is rejected. Because transports may wrap handshake errors in different exceptions, simply assert that the publisher terminates with an error rather than depending on one specific exception implementation.

### 13.5. Running the Tests

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The example uses a random server port, requires no manual server startup, and makes no external service calls.

## 14. Operating WebSocket Endpoints

WebSocket is a long-lived connection. After the handshake, a connection can remain open for minutes or hours. Therefore, configuring routes and handshakes is only the first step.

### 14.1. Reverse Proxies and Load Balancers

If the application runs behind Nginx, an ingress, or a load balancer, the proxy must forward WebSocket Upgrade and Connection headers properly. Verify:

- The proxy supports HTTP Upgrade to the upstream.
- Idle timeouts are long enough for the workload.
- The load balancer does not close connections before the heartbeat interval.
- Sticky sessions are used only when the architecture truly requires session affinity.
- TLS termination and forwarded headers are configured properly.
- Autoscaling/draining handles open WebSocket connections cleanly.

### 14.2. Heartbeat and Ping/Pong

Ping/pong helps detect unresponsive connections and keeps network paths alive through certain proxies. Reactor Netty can automatically reply with pong to ping frames under default configuration; the application only needs to handle pings directly if proxying or custom protocol logic requires it.

Application-layer heartbeats differ from protocol ping/pong. If sending text heartbeats, both sides must agree on the message format and frequency.

### 14.3. Message Limits and Backpressure

Set an appropriate frame payload limit to prevent clients from sending oversized frames. Beyond frame limits, the application should bound logical message sizes after reassembling fragments, messages per second, connections per user/tenant, outbound queues when clients read slowly, session-closing policies on protocol violations, and per-message processing timeouts.

Do not use an unbounded queue to buffer messages for slow clients. When downstream is slow, apply backpressure or an explicit drop/reject policy.

### 14.4. Closing Sessions Properly

When either side completes the inbound stream, the handler should finish the reactive flow and let the framework close the session according to its lifecycle. If the application needs to close with a specific code/reason, use session.close(CloseStatus) per the API and protocol policy.

Do not store WebSocketSession instances in a static map without cleanup. If a connection registry is needed, tie add/remove to the lifecycle, handle disconnect/error/cancel, and bound entry counts.

### 14.5. Observability

Track at least:

- Number of open connections.
- Handshake successes/failures by endpoint and reason.
- Messages received/sent and their sizes.
- Sessions closed by client, server, or timeout.
- Average and percentile session lifetimes.
- Outbound queues, message processing latency, and error rates.
- Connections per tenant/user where privacy permits.

Do not log full messages that may contain tokens or personal data. Use correlation IDs and log filtered metadata.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Registering WebSocketHandler with @GetMapping | Handler is not mapped as a WebSocket endpoint | Use SimpleUrlHandlerMapping |
| Forgetting WebSocketHandlerAdapter when not using WebFlux config | DispatcherHandler does not know how to invoke WebSocketHandler | Register the adapter manually |
| Creating a second adapter in Spring Boot | Duplicate config beans or confusing lifecycle | Use the adapter provided by WebFlux config |
| Setting mapping order after annotated controllers | Routes may be claimed by another handler mapping first | Set an appropriate order, typically -1 |
| Mapping multiple handlers to the same URL | Routing outcome depends on mapping order | Use distinct paths or clear precedence rules |
| Returning Mono.empty immediately from handle | Session closes right after handshake | Combine receive/send into a session-lived publisher |
| Subscribing manually to receive | Loses lifecycle control and error propagation | Return the publisher from handle |
| Not handling client disconnect | Business tasks keep running unnecessarily | Propagate cancellation and clean up |
| Not negotiating subprotocol | Client and server may use incompatible message formats | Implement getSubProtocols and check handshake result |
| Trusting Origin as authentication | Non-browser clients can spoof the header | Use real authentication and authorization |
| Allowing all origins | Any website can open connections from a browser | Allowlist specific origins |
| Using sessionAttributePredicate as authorization | Attributes are copied but do not prove permissions | Verify principal and policy before allowing actions |
| Raising frame limits without bounds | Clients can send huge frames causing memory pressure | Set frame/message quotas per requirements |
| Enabling compression without evaluation | Increases CPU/memory and compression-related data risks | Enable only when needed and evaluated |
| Not configuring proxy Upgrade | Handshake fails behind reverse proxy | Forward Upgrade/Connection and tune timeouts |
| Storing sessions in a map without cleanup | Leaks sessions and memory | Remove entries on complete/error/cancel |
| Not testing origin and subprotocol | Handshake bugs surface only on deploy | Test success, rejected origin, and protocol negotiation |
| Using a REST request/response mindset for WebSocket | Fails to manage long-lived connections and backpressure | Design a dual-stream lifecycle |

## 16. Deployment Checklist

Before shipping a WebSocket endpoint to production, check:

1. **Handler:** Does WebSocketHandler return a Mono<Void> representing the full session?
2. **Inbound/outbound:** Are receive and send composed with the proper lifecycle?
3. **Route:** Does SimpleUrlHandlerMapping register the right path?
4. **Order:** Is the mapping evaluated before annotated controllers when needed?
5. **Adapter:** Does WebFlux config provide WebSocketHandlerAdapter?
6. **Handshake service:** Is a custom WebSocketService or RequestUpgradeStrategy needed?
7. **Server engine:** Does the strategy match the running Reactor Netty, Tomcat, or Jetty server?
8. **Subprotocol:** Do client and server agree on the negotiated protocol?
9. **Origin:** Are browser origins allowlisted?
10. **Authentication:** Is the handshake protected with a valid principal?
11. **Authorization:** Is the user authorized to access the room/tenant/resource after the handshake?
12. **Session attributes:** Are only necessary and verified attributes copied?
13. **Frame/message limits:** Are message sizes and rates bounded?
14. **Backpressure:** Can a slow client cause queues to grow unbounded?
15. **Proxy:** Are Upgrade headers, TLS, and idle timeouts configured correctly?
16. **Lifecycle:** Do disconnect, error, cancellation, and server shutdown clean up resources?
17. **Observability:** Are connection, handshake, message, and close-reason metrics tracked?
18. **Tests:** Are handshake success, subprotocol, origin rejection, and echo messages tested?

**Key Takeaway:** WebFlux registers a WebSocket endpoint by mapping WebSocketHandler to a URL via SimpleUrlHandlerMapping. WebSocketHandlerAdapter passes the handler to WebSocketService; HandshakeWebSocketService validates the handshake and invokes the server engine's RequestUpgradeStrategy. Use WebFluxConfigurer.getWebSocketService() to customize the handshake service, getSubProtocols() for subprotocols, CorsConfigurationSource for origins, and a predicate for session attributes. A successful handshake only opens the connection; authentication, authorization, backpressure, message limits, and cleanup must still be designed for the entire session lifecycle.

## References

- Spring Framework — WebFlux WebSocket: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework — WebFlux Configuration and WebSocketService: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebSocketHandler API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketHandler.html
- Spring Framework — HandshakeWebSocketService API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/server/support/HandshakeWebSocketService.html
- Spring Framework — ReactorNettyRequestUpgradeStrategy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/server/upgrade/ReactorNettyRequestUpgradeStrategy.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- Reactor Netty — WebsocketServerSpec API: https://projectreactor.io/docs/netty/release/api/reactor/netty/http/server/WebsocketServerSpec.html
