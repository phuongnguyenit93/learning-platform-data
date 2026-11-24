# Establishing, Maintaining, and Closing an RSocket Connection

## Objectives

After this lesson, you will be able to:

- Explain the lifecycle of an RSocket connection from configuration to closure.
- Create a client in Spring Framework using **RSocketRequester**.
- Configure a TCP or WebSocket server using Spring Boot.
- Send data during connection setup and handle the **SETUP** frame with **@ConnectMapping**.
- Maintain the connection with keepalive, and choose between reconnect or session resumption strategies.
- Close resources in a timely manner and identify common errors.

Examples use Java 17+, Spring Boot 3.5.x, and the Spring Framework version managed by Spring Boot. Keep Spring Boot, Spring Framework, and RSocket Java versions compatible according to your project's dependency management.

## 1. RSocket Connection Lifecycle

RSocket is a bidirectional message-exchange protocol over a byte stream connection such as TCP or WebSocket. After a connection is established, both sides can send requests; the concepts of client and server only describe the roles during connection initiation. Each side can act as a requester or a responder depending on each request.

RSocket supports four interaction models:

| Model | Meaning |
|---|---|
| Request-Response | Send one message and receive one response. |
| Request-Stream | Send one request and receive a stream of multiple elements. |
| Channel | Both sides exchange streams of data bidirectionally. |
| Fire-and-Forget | Send one message without waiting for a response payload. |

A single connection can carry multiple concurrent request streams. Therefore, it is important to distinguish the **connection lifecycle** from the **lifecycle of each individual request**. A request completing does not mean the connection has closed.

Main phases:

1. **Configuration:** the application chooses the transport, address, codecs, metadata, and keepalive policy.
2. **Transport connection:** the client opens TCP or WebSocket to the server.
3. **SETUP:** the client sends a SETUP frame containing the protocol version, MIME types, keepalive parameters, and optional setup data/metadata.
4. **Accept or reject:** the server processes SETUP. If configuration or authentication is invalid, the server can reject the connection.
5. **Data exchange:** both sides send request-response, request-stream, channel, or fire-and-forget over the same connection.
6. **Maintenance:** KEEPALIVE detects that the transport has lost connection; reconnect or resume handles interruptions according to the application policy.
7. **Closure:** the application stops accepting new work, handles in-flight requests according to its shutdown policy, and then releases the requester or server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as TCP / WebSocket
    participant S as RSocket Server
    C->>T: Open transport
    T->>S: Establish transport
    C->>S: SETUP (MIME, keepalive, setup data)
    S-->>C: Accept or reject
    C->>S: REQUEST_RESPONSE / STREAM / CHANNEL / FNF
    S-->>C: PAYLOAD or termination signal
    C-->>S: Periodic KEEPALIVE
    S-->>C: KEEPALIVE response
    C->>S: dispose() / close transport
~~~

Spring provides **RSocketRequester** to work at the application level. This class encapsulates routing, encoding, and decoding payloads. Underneath, it uses RSocket Java to manage the connection and transport.

## 2. Preparing and Starting an RSocket Server

### 2.1. Adding the Dependency

With Maven and Spring Boot, use the following starter. Spring Boot automatically manages the versions of related libraries:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

The starter provides the RSocket infrastructure and default codecs that Spring Boot can configure. If the project does not use Spring Boot, you must manually declare the appropriate Spring Messaging, RSocket Java, Reactor, and transport modules.

### 2.2. Opening a TCP Server

In the server application's `application.properties`:

~~~properties
spring.rsocket.server.port=7000
~~~

When the dependency and port are present, Spring Boot auto-configures the RSocket server along with **RSocketMessageHandler**. **@Controller** beans with **@MessageMapping** or **@ConnectMapping** are used to handle messages.

Controller example:

~~~java
package com.example.rsocketserver;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @ConnectMapping("client.connect")
    public Mono<Void> onConnect(@Payload String clientId) {
        if (clientId == null || clientId.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("clientId is required")
            );
        }

        System.out.println("Connected client: " + clientId);
        return Mono.empty();
    }

    @MessageMapping("greeting")
    public Mono<String> greeting(@Payload String name) {
        return Mono.just("Hello, " + name);
    }
}
~~~

Server startup class:

~~~java
package com.example.rsocketserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketServerApplication.class, args);
    }
}
~~~

In the example, `client.connect` is a route at the connection setup level. `greeting` is a route for a regular request. These two routes belong to different phases.

### 2.3. Using WebSocket

If you need to expose RSocket over a WebFlux WebSocket endpoint, configure:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

This integration requires a WebFlux and Reactor Netty application. A standalone TCP RSocket server and a WebSocket RSocket endpoint attached to a web server are two different deployment options; choose based on your network infrastructure and the clients that need to connect.

## 3. Creating a Client Connection with RSocketRequester

### 3.1. Creating the Requester

Spring Boot auto-configures an **RSocketRequester.Builder** bean. This builder has prototype scope because it holds configuration state; each connection configuration should use a separate instance.

~~~java
RSocketRequester requester = builder
    .tcp("localhost", 7000);
~~~

Or connect over WebSocket using an endpoint URI:

~~~java
RSocketRequester requester = builder
    .websocket(URI.create("ws://localhost:8080/rsocket"));
~~~

The WebSocket snippet requires importing `java.net.URI`.

Calling **tcp()** or **websocket()** creates a configured requester/client; it **does not necessarily open the socket immediately on that line**. The connection is established when the application makes its first request. Concurrent requests through the same requester share the connection. When the transport is lost, subsequent requests can trigger re-establishing the connection according to the client's mechanism.

Therefore, in a Spring application, it is usually best to keep a requester in a singleton service and reuse it. Avoid creating a new requester for each message or sharing a builder whose configuration has been modified across multiple connections.

### 3.2. Sending Information in SETUP

The builder allows declaring data and metadata at the connection level:

- **setupData(...)**: data payload of the SETUP frame.
- **setupRoute(...)**: route in the metadata of the SETUP frame.
- **setupMetadata(...)**: additional metadata along with its MIME type.
- **dataMimeType(...)** and **metadataMimeType(...)**: MIME types applied to data and metadata on the connection.

Example of a client sending an identifier in SETUP:

~~~java
RSocketRequester requester = builder
    .setupRoute("client.connect")
    .setupData("client-demo")
    .tcp("localhost", 7000);
~~~

The server receives the **client.connect** route using **@ConnectMapping** and reads **client-demo** via **@Payload**. Setup data is useful for initialization information such as a client identifier or capabilities. Do not send passwords, long-lived access tokens, or secret data as plain setup data; use appropriate authentication mechanisms, security metadata, and TLS.

### 3.3. Sending Requests After Connecting

Once the requester is ready, build a request with a route, data, and expected response type:

~~~java
Mono<String> response = requester
    .route("greeting")
    .data("Ada")
    .retrieveMono(String.class);
~~~

**retrieveMono** declares a single response; **retrieveFlux** is used when the server returns a stream. **send()** is suitable for fire-and-forget and returns a **Mono<Void>** confirming message dispatch, without guaranteeing that the receiving handler has finished business processing.

Reactor publishers are lazy: a request only runs when the publisher is subscribed to. In a reactive service, return **Mono** or **Flux** to the caller so the caller can coordinate execution, timeouts, and subscription cancellation. Only use **block()** at an intentional synchronous boundary, such as a command-line demo program or a non-reactive integration layer.

## 4. Complete Client Example

The service below holds a shared requester, sends an identifier in SETUP, calls the **greeting** route, and disposes the requester when Spring closes the bean.

~~~java
package com.example.rsocketclient;

import java.time.Duration;

import jakarta.annotation.PreDestroy;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingClient {

    private final RSocketRequester requester;

    public GreetingClient(RSocketRequester.Builder builder) {
        this.requester = builder
            .setupRoute("client.connect")
            .setupData("client-demo")
            .rsocketConnector(connector -> connector
                .keepAlive(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(90)
                )
            )
            .tcp("localhost", 7000);
    }

    public Mono<String> greet(String name) {
        return requester
            .route("greeting")
            .data(name)
            .retrieveMono(String.class);
    }

    @PreDestroy
    public void close() {
        requester.dispose();
    }
}
~~~

The client application can call the service on startup:

~~~java
package com.example.rsocketclient;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RSocketClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketClientApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(GreetingClient client) {
        return args -> client.greet("Ada")
            .doOnNext(System.out::println)
            .block();
    }
}
~~~

Run the server first, then run the client. With Maven Wrapper, run **mvnw.cmd spring-boot:run** in the server project directory, then run the same command in the client project directory. If both applications have configured dependencies and packages as in the example, the business output is:

~~~text
Connected client: client-demo
Hello, Ada
~~~

The line **Connected client: client-demo** appears in the server log when the client performs its first request and the SETUP frame is processed. The line **Hello, Ada** is printed on the client. Spring Boot startup logs are not included in this output.

## 5. Maintaining the Connection

### 5.1. Keepalive and Detecting Lost Transport

RSocket uses KEEPALIVE frames so both sides know the peer is still responsive. Two important parameters:

- **Interval:** the time between KEEPALIVE frames sent by the client.
- **Max lifetime:** the maximum time to wait for a KEEPALIVE response from the peer before concluding the connection is lost.

Configure via **RSocketConnector** in **RSocketRequester.Builder**:

~~~java
.rsocketConnector(connector -> connector
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    )
)
~~~

The two values above are examples only. Choose interval and max lifetime based on network latency, proxy/load balancer timeouts, client type, and sensitivity to disconnect detection. Max lifetime should be large enough to tolerate several delayed or lost heartbeats; setting it too short can cause the connection to be marked dead when the network is only temporarily slow.

KEEPALIVE helps detect an unresponsive transport. It does not prove a business route is healthy, does not replace per-request timeouts, and does not automatically recover failed business data. If you need to check service health, use an application-level health/probe request.

### 5.2. Reconnect

Reconnect creates a new connection when the old connection is lost. RSocket Java allows configuring a retry policy on the connector:

~~~java
.rsocketConnector(connector -> connector
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    )
    .reconnect(
        Retry.backoff(5, Duration.ofSeconds(1))
            .maxBackoff(Duration.ofSeconds(30))
    )
)
~~~

Requires importing **reactor.util.retry.Retry**. The example above allows up to five retry attempts, starting with a one-second delay and increasing up to a maximum of thirty seconds. This is a sample policy; limits and backoff must match load, server recovery time, and the request's time budget.

There are two retry layers to distinguish:

1. **Client connection reconnect:** determines how to re-create the connection when the transport is lost.
2. **Request retry:** determines whether to resend a failed request.

A failed request is not automatically re-executed just because the connector has a reconnect policy. To retry a request, the caller must resubscribe, typically via **retryWhen**:

~~~java
return requester
    .route("greeting")
    .data(name)
    .retrieveMono(String.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(500))
            .filter(error -> isTransientConnectionError(error))
    );
~~~

**isTransientConnectionError** is an application-defined predicate based on recoverable network errors. Do not blindly retry validation errors, business errors, or all exceptions. For commands with side effects such as creating an order or deducting funds, retry only when the API has an idempotency key or deduplication mechanism; otherwise, the first attempt may already have been executed by the server before the response was lost.

### 5.3. Session Resumption

Session resumption is a protocol mechanism to continue an RSocket session after a transport interruption, provided both sides support and configure resume. It retains the state needed to recover interrupted streams, so it consumes more memory and state management than regular reconnect.

Distinction:

| Mechanism | Behavior |
|---|---|
| Reconnect | Creates a new connection. Failed requests need a separate retry policy if you want to resend them. |
| Resume | Attempts to restore the session and resumable streams after a transport interruption. |
| Request retry | Resends an operation at the application layer; risks repeating side effects if the operation is not idempotent. |

In RSocket Java, **reconnect(Retry)** and **resume(Resume)** are mutually exclusive options; if both are configured, resume takes precedence. Only enable resume when both client and server are compatibly configured and the application genuinely needs stream continuation. If you only need to reconnect and execute new requests, reconnect is usually simpler.

### 5.4. Timeout, Backpressure, and Subscriptions

Keeping a connection open long-term does not mean every request is allowed to wait indefinitely.

- Set timeouts per operation or according to business requirements.
- With **Flux**, handle backpressure and cancel the subscription when the caller no longer needs data.
- Use **take**, **timeout**, **onErrorResume**, or appropriate operators to manage stream lifecycle.
- Do not swallow connection errors by turning every error into a default value; log and classify errors.
- Do not call **subscribe()** scattered throughout a service if you can return a publisher to the calling layer. Self-managed subscriptions make error handling, cancellation, and shutdown harder to control.

## 6. Handling Connection Events and Closing Connections

### 6.1. @ConnectMapping for SETUP

**@ConnectMapping** handles SETUP frames when a connection starts and subsequent metadata push notifications. You can restrict a handler by route such as **client.connect**; if no route is declared, the handler can match all connections/metadata pushes.

On the server, the handler must return **void** or **Mono<Void>**. When handling asynchronously with **Mono<Void>**, the connection is accepted after the publisher completes; if the publisher emits an error, the new connection can be rejected.

Do not block SETUP processing waiting for another request sent over that same connection's requester. SETUP must complete before either side starts regular requests. If the server needs to send data immediately when a client connects, decouple that sending from the SETUP handling flow and execute it asynchronously after the connection is accepted.

**Note:** **@ConnectMapping** is not a disconnect callback. It handles SETUP and METADATA_PUSH, not transport close events.

### 6.2. Observing When a Connection Closes

At the RSocket Java layer, an **RSocket** object provides **onClose()**, returning a **Mono<Void>** that terminates when the resource closes. The publisher completes normally on a normal close and emits an error on an error close. You can use this signal to clean up a client registry or release resources bound to a connection.

Conceptual example when the application holds a live RSocket object:

~~~java
rsocket.onClose()
    .doOnError(error ->
        log.warn("RSocket connection closed with error", error)
    )
    .doFinally(signal ->
        connectedClients.remove(clientId)
    )
    .subscribe();
~~~

In the illustration, **log**, **connectedClients**, and **clientId** are application-defined components. Do not assume every **RSocketRequester** returns this object. The **requester.rsocket()** method can return **null** when the requester is created via a TCP/WebSocket builder; it is only available in certain cases where the requester wraps an active RSocket. If you need low-level server-side connection lifecycle management, design the component that owns the RSocket/SocketAcceptor object to register **onClose()** explicitly.

### 6.3. Closing the Requester on the Client

**RSocketRequester** implements **Disposable**. Calling **dispose()** closes the underlying transport connection and notifies subscribers. You can check the state with **isDisposed()**.

~~~java
requester.dispose();

if (requester.isDisposed()) {
    System.out.println("Requester has been disposed");
}
~~~

In Spring, place disposal in **@PreDestroy**, as in the **GreetingClient** example. On shutdown:

1. Stop accepting new work or creating new requests.
2. Cancel or await running streams according to the application's shutdown timeout.
3. Call **requester.dispose()** to close the requester.
4. Let Spring close the ApplicationContext and remaining resources.

Do not dispose the requester after each request if multiple requests share the same connection. Doing so will close the connection that other requests still need.

### 6.4. Closing the Server

With Spring Boot, the RSocket server is managed by the ApplicationContext lifecycle. When the application stops, Spring closes the auto-configured server along with related beans.

If creating a server manually with RSocket Java, keep the **CloseableChannel** returned from the bind operation and call **dispose()** on application shutdown. Do not discard this handle if the application needs a controlled server shutdown.

## 7. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Connection refused | Server is not running, wrong host/port, or firewall blocks TCP. | Check server logs, listening port, and the address used by the client. |
| SETUP rejected | **@ConnectMapping** handler emits an error, setup route mismatch, or invalid credentials. | Check server logs and inspect setup route/data/metadata. |
| Payload cannot be decoded | Both sides use incompatible MIME types or codecs. | Check **RSocketStrategies**, encoders, decoders, and MIME types. |
| Connection closed while idle | Proxy timeout, unsuitable heartbeat, or network with long packet-loss periods. | Compare keepalive interval/max lifetime with infrastructure timeouts. |
| First request fails | Requester was only configured; actual transport opens when a request is made. | Verify the server is ready before the client sends requests. |
| Connection recovered but operation does not rerun | Reconnect does not mean request retry. | Add bounded retries for requests that can be safely retried. |
| Server processes operation twice | Retrying a request with side effects after the first response was lost. | Use an idempotency key or deduplication mechanism. |
| Resources/connections remain after shutdown | Requester was not disposed or streams were not cancelled. | Check **@PreDestroy**, subscriptions, and shutdown policy. |

## 8. Implementation Checklist

- [ ] Server opens the correct transport and port or WebSocket mapping path.
- [ ] Client and server use compatible MIME types, codecs, and metadata.
- [ ] Requester is reused for requests sharing the same lifecycle.
- [ ] Setup route/data contain only information necessary to initialize the connection.
- [ ] Keepalive matches network and proxy timeouts.
- [ ] Reconnect and request retry are configured as two separate policies.
- [ ] Requests with side effects have idempotency protection before retrying.
- [ ] **@ConnectMapping** completes quickly and does not wait for requests on the newly established connection.
- [ ] There is a path to clean up the registry/resources on connection close if the application tracks connected clients.
- [ ] Client requester is disposed on application shutdown.
- [ ] Running streams have appropriate timeouts, cancellation, and backpressure.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, SETUP, codecs, annotated responders, and ConnectMapping.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): starter, server auto-configuration, TCP/WebSocket, and requester builder.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): dispose(), isDisposed(), rsocket(), and rsocketClient().
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): keepalive, reconnect, and resume.
- [RSocket Protocol](https://rsocket.io/about/protocol/): SETUP, KEEPALIVE, request frames, and session resumption.
