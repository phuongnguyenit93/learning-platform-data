
# Registering an Acceptor and Starting an RSocket Server

## Objectives

After this lesson, you will be able to explain the role of `SocketAcceptor`, convert Spring handlers into an acceptor using `RSocketMessageHandler`, start an RSocket server over TCP, and manage the server lifecycle.

The examples use Java 17+, Spring Framework 7.0.10, and RSocket Java 1.1.5. Spring Framework 6.2 shares the same core API model for this section. Align Spring versions according to your project's BOM.

## 1. From Connection to Acceptor

RSocket is a binary protocol for bidirectional, asynchronous communication over a single connection. It can run over TCP or WebSocket and supports Request-Response, Request-Stream, Channel, and Fire-and-Forget interaction models. Once a connection is established, both sides can send requests; therefore RSocket uses the concepts of requester and responder instead of fixed client/server roles.

When a peer connects to the server, it sends a `SETUP` frame containing connection setup information such as the data and metadata MIME types. The server uses a `SocketAcceptor` to handle the connection setup step and create an `RSocket` responder for that connection.

Each component has a distinct role:

- `RSocketServer`: configures and binds the server to a transport.
- `SocketAcceptor`: accepts each new connection, reads `SETUP` information, and returns an `RSocket` responder.
- `RSocket`: handles requests over the connection, such as Request-Response or Request-Stream.
- `RSocketMessageHandler`: the Spring Messaging bridge; detects `@Controller` beans, maps `@MessageMapping` and `@ConnectMapping`, and provides a `SocketAcceptor` via `responder()`.
- `RSocketRequester`: the request-sending API. It is not an acceptor and is not responsible for binding the server.

In a Spring application, we usually do not need to write a protocol-level `RSocket` class ourselves. We declare Spring handlers, obtain the acceptor from `RSocketMessageHandler`, and pass that acceptor to `RSocketServer`.

The initialization flow looks like:

```text
@Controller + @MessageMapping
          |
          v
RSocketMessageHandler
          |
          | responder()
          v
SocketAcceptor
          |
          | RSocketServer.create(acceptor)
          v
RSocketServer
          |
          | bind(TcpServerTransport)
          v
Listening CloseableChannel
```

## 2. Declaring Dependencies

The Maven example below uses the Spring Framework BOM to keep Spring modules on the same version. The two RSocket artifacts required for a TCP server are `rsocket-core` and `rsocket-transport-netty`.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.0.10</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-messaging</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-core</artifactId>
        <version>1.1.5</version>
    </dependency>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-transport-netty</artifactId>
        <version>1.1.5</version>
    </dependency>
</dependencies>
```

Meaning of the dependencies:

- `spring-context` provides ApplicationContext and configuration via `@Configuration` and `@Bean`.
- `spring-messaging` provides `RSocketMessageHandler`, `RSocketStrategies`, `@MessageMapping`, and related messaging APIs.
- `spring-web` provides `PathPatternRouteMatcher` along with additional codecs when encoding/decoding complex data types is needed.
- `rsocket-core` provides `RSocketServer`, `SocketAcceptor`, and protocol abstractions.
- `rsocket-transport-netty` provides TCP/WebSocket transports based on Reactor Netty.

The example below only sends `String`, so it can use the basic codecs provided out of the box by `RSocketStrategies`. If sending objects such as DTOs, add the corresponding JSON or CBOR codecs and configure compatible encoders/decoders on both sides.

## 3. Creating a Responder with Spring Messaging

A server-side handler is a bean annotated with `@Controller`. Each `@MessageMapping` method handles an RSocket route. The following example receives a name and returns a greeting:

```java
package example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @MessageMapping("greeting")
    public Mono<String> greet(@Payload String name) {
        return Mono.just("Hello, " + name);
    }
}
```

The `greeting` route is routing metadata for an RSocket request, not an HTTP URL. The method accepts one payload and returns a `Mono`, so Spring handles this call as a Request-Response interaction.

Spring finds `@Controller` beans and registers methods annotated with `@MessageMapping` or `@ConnectMapping` when initializing `RSocketMessageHandler`. This handler dispatches requests to the appropriate method call while using codecs in `RSocketStrategies` to convert payloads.

## 4. Registering the Acceptor and Starting the TCP Server

The complete example below registers the controller, creates `RSocketMessageHandler`, retrieves the `SocketAcceptor` via `handler.responder()`, and binds the server to `localhost:7000`.

```java
package example.rsocket;

import java.time.Duration;

import io.rsocket.CloseableChannel;
import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketServerApplication {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    RSocketMessageHandler rsocketMessageHandler(RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setDefaultDataMimeType(MimeTypeUtils.TEXT_PLAIN);
        return handler;
    }

    @Bean
    GreetingController greetingController() {
        return new GreetingController();
    }

    @Bean(destroyMethod = "dispose")
    CloseableChannel rsocketServer(RSocketMessageHandler handler) {
        SocketAcceptor acceptor = handler.responder();

        CloseableChannel server = RSocketServer.create(acceptor)
                .bind(TcpServerTransport.create("localhost", 7000))
                .block(Duration.ofSeconds(10));

        if (server == null) {
            throw new IllegalStateException("RSocket server did not bind");
        }
        return server;
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(RSocketServerApplication.class);

        context.registerShutdownHook();

        CloseableChannel server = context.getBean(CloseableChannel.class);
        System.out.println("RSocket server listening at tcp://localhost:7000");

        server.onClose().block();
    }
}
```

In this example, `GreetingController` is a Spring bean registered via a `@Bean` method. If the controller resides in a component-scanned package, `@ComponentScan` can be used instead of an explicit bean registration method.

### Step-by-Step Explanation

**Step 1 — Create `RSocketStrategies`.**

`RSocketStrategies` groups configuration for encoders, decoders, metadata extractors, reactive adapters, and the route matcher. `PathPatternRouteMatcher` is the option recommended by Spring when `spring-web` is present; it supports hierarchical routes and uses a dot as the default separator, such as `inventory.item.find`.

**Step 2 — Create `RSocketMessageHandler`.**

Call `setRSocketStrategies(strategies)` so the handler uses the same codecs and route matcher. `setDefaultDataMimeType(MimeTypeUtils.TEXT_PLAIN)` sets the default MIME type for data when the `SETUP` frame does not specify a MIME type. For `String` payloads, `text/plain` is an appropriate choice.

**Step 3 — Convert the handler into an acceptor.**

Calling `handler.responder()` returns a `SocketAcceptor` capable of creating a responder for each new connection. This acceptor uses Spring's annotation infrastructure to dispatch routes to handler methods.

**Step 4 — Create and bind the server.**

`RSocketServer.create(acceptor)` creates the server configuration with the registered acceptor. `bind(TcpServerTransport.create("localhost", 7000))` selects the TCP transport and listening address. `bind` returns a `Mono<CloseableChannel>`; call `block` during startup to actually perform the bind and obtain the running channel.

**Step 5 — Manage the lifecycle.**

`CloseableChannel` represents the bound server. The bean declares `destroyMethod = "dispose"` so Spring closes the channel when the ApplicationContext stops. `registerShutdownHook()` registers closing the context on JVM shutdown, and `server.onClose().block()` keeps the process waiting until the server closes.

Do not call `block()` inside a reactive handler or event loop. In this example, `block` is only used on the startup thread and the main thread of the standalone application.

## 5. Sending a Request to Test the Server

You can use `RSocketRequester` to send a request to the `greeting` route. The requester establishes the connection when the first request is executed; calling `tcp` only prepares the requester.

```java
package example.rsocket;

import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

public class RSocketClientDemo {

    public static void main(String[] args) {
        RSocketRequester requester = RSocketRequester.builder()
                .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
                .tcp("localhost", 7000);

        try {
            String response = requester.route("greeting")
                    .data("Mai")
                    .retrieveMono(String.class)
                    .block(Duration.ofSeconds(5));

            System.out.println(response);
        }
        finally {
            requester.dispose();
        }
    }
}
```

Output:

```text
Hello, Mai
```

Client and server must agree on how data and metadata are encoded/decoded. This example uses `text/plain` and `String` on both sides. If one side sends JSON while the other only configures codecs for text, the request may fail during decoding even though the TCP connection succeeded.

## 6. Customizing the Acceptor at the RSocket Level

When not using `@MessageMapping`, an application can supply its own `SocketAcceptor`. Fundamentally, an acceptor receives connection setup info and an `RSocket` for sending requests back to the peer, then returns a `Mono<RSocket>` containing the responder for that connection.

```java
SocketAcceptor acceptor = (setupPayload, sendingRSocket) ->
        Mono.just(customResponder);

CloseableChannel server = RSocketServer.create(acceptor)
        .bind(TcpServerTransport.create("localhost", 7001))
        .block(Duration.ofSeconds(10));
```

In this snippet, `customResponder` is an application-created instance implementing `io.rsocket.RSocket`. That class must implement the interactions the server wishes to support, such as `requestResponse`, `requestStream`, `requestChannel`, or `fireAndForget`. Unimplemented interactions use RSocket's default behavior, typically returning an unsupported error.

Writing a custom implementation is appropriate when low-level protocol control is required or when integrating a non-annotation-based responder. For standard Spring Messaging applications, `RSocketMessageHandler.responder()` avoids having to manually manage route mapping and handler invocation.

## 7. Using Spring Boot Instead of Manual Binding

If the application already uses Spring Boot, the `spring-boot-starter-rsocket` starter auto-configures the Spring Messaging infrastructure, creates `RSocketMessageHandler`, and starts the RSocket server according to configuration. Standalone TCP server example:

```properties
spring.rsocket.server.port=9898
```

For a WebFlux application wanting to expose RSocket over WebSocket, you can configure:

```properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
```

When using Spring Boot auto-configuration, you only need to declare `@Controller` handlers and transport configuration. Do not create an additional bean that manually binds to the same port, as doing so may result in an address-already-in-use error.

## 8. Common Errors and How to Handle Them

| Symptom | Common cause | How to check |
|---|---|---|
| Server fails to start, reporting address/port already in use | Another process is already bound to the same address and port | Change the port or stop the process occupying the port |
| Client connects but route is not found | Route in `requester.route(...)` does not match `@MessageMapping` | Compare exact route name, hierarchical dots, and pattern |
| Unable to decode payload | Incompatible MIME type or encoder/decoder between the two sides | Check MIME type in `SETUP` and `RSocketStrategies` configuration |
| Handler is not invoked | Controller is not registered in ApplicationContext or missing annotation | Confirm the bean has `@Controller` and the method has `@MessageMapping` |
| Server runs but does not shut down cleanly | `CloseableChannel` is not disposed when context closes | Manage the channel as a bean and declare `destroyMethod = "dispose"` |
| Server bind does not happen | Created Mono from `bind` without subscribing | Wait for result with `block` at startup or subscribe in an appropriate lifecycle hook |

Design notes:

- `SocketAcceptor` runs when opening a connection; `@MessageMapping` handles routed requests after the connection is established.
- `@ConnectMapping` handles `SETUP` and `METADATA_PUSH` frames. This method may only return `void` or `Mono<Void>`; if setup handling throws an error, the new connection can be rejected.
- Do not block `@ConnectMapping` handling waiting for another request via `RSocketRequester`. Setup frame processing must complete before normal requests begin.
- An RSocket route is a messaging route, not a URL. The default route matcher uses `AntPathMatcher`; `PathPatternRouteMatcher` is a more efficient option when `spring-web` is available.
- With TCP, the `localhost` address only allows local access. When deploying in a container or on a server, choose a bind interface appropriate for the network and configure connection security according to system requirements.

## 9. Summary

To start an RSocket server with Spring Framework, follow this sequence:

1. Declare responders using `@Controller`, `@MessageMapping`, and `@ConnectMapping` when needed.
2. Create `RSocketMessageHandler` and configure `RSocketStrategies`.
3. Obtain the acceptor via `RSocketMessageHandler.responder()`.
4. Pass the acceptor into `RSocketServer.create(acceptor)`.
5. Call `bind(transport)` to start the server and manage `CloseableChannel` to shut down the server properly within its lifecycle.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Java — GitHub repository](https://github.com/rsocket/rsocket-java)
- [RSocket Core — Maven Central](https://central.sonatype.com/artifact/io.rsocket/rsocket-core)
