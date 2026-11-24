# RSocket over TCP or WebSocket and Conditions for Sharing the Web Server

## 1. Objectives and Key Points

RSocket is a binary messaging protocol layered over byte-stream transports. RSocket is neither HTTP nor WebSocket: **TCP and WebSocket are two transports that carry RSocket frames**. Spring Boot 3.3 can start a **standalone** RSocket listener or mount **RSocket-over-WebSocket on the same web server** when specific conditions are met.

Keep in mind:

- `spring.rsocket.server.port=9898`: requests a **dedicated** RSocket listener. With `transport=tcp`, that is TCP RSocket; with `transport=websocket`, that is standalone RSocket-over-WebSocket.
- `server.port=8080`: is the embedded HTTP web server port and **does not turn port 8080 into RSocket TCP**.
- To make RSocket **share the HTTP port** under Spring Boot auto-configuration, you must have **WebFlux application type `REACTIVE`**, embedded **Reactor Netty**, `transport=websocket`, `mapping-path=/rsocket`, and **no dedicated RSocket server port**.
- **Spring MVC/Servlet on Tomcat does not get RSocket mounted onto the same embedded web listener by Spring Boot's shared-port config above.** You can run a standalone RSocket listener in the same JVM or place a reverse proxy in front to share one public entry point; those are different topologies.

This lesson sits in **Extending the Web Platform**. You will learn to compare the two transports, the four interaction models, Spring Boot profiles, port binding, requester/responder, codecs, backpressure, TLS, proxies, WebFlux/MVC differences, and run a Java 17+/Spring Boot 3.3.5 example supporting both TCP and WebSocket modes.

## 2. Distinguishing Four Conceptual Layers

~~~text
Normal HTTP request-response
  Browser -- HTTP GET /http/ping --> Spring WebFlux
  Browser <-- HTTP 200 + body ------ Spring WebFlux

RSocket over TCP
  RSocketRequester == TCP connection ==> RSocket responder
                 RSocket SETUP / request frames

RSocket over WebSocket
  RSocketRequester -- HTTP upgrade --> WebFlux Reactor Netty
                      == WebSocket frames ==
                      carrying binary RSocket frames inside

STOMP over WebSocket (NOT RSocket)
  STOMP client -- WebSocket --> STOMP processor/broker
                CONNECT / SEND / SUBSCRIBE / MESSAGE
~~~

**HTTP** has methods, URLs, statuses, and headers; **WebSocket** has upgrade handshakes/frames and bidirectional transport; **RSocket** has setup, stream IDs, metadata, backpressure, and interaction models; **STOMP** is a separate messaging protocol with commands/destinations. Do not send STOMP clients or plain browser `new WebSocket(...)` text expecting Spring to handle RSocket metadata routes.

On the WebSocket transport, the HTTP path `/rsocket` is **only the handshake entry point**, not a prefix turning RSocket routes into `/rsocket/greet` or separate HTTP endpoints. Route `greet` travels inside **RSocket routing metadata** after the handshake.

## 3. RSocket's Four Interaction Models

| Interaction | Requester | Responder | Spring API |
| --- | --- | --- | --- |
| Request-response | One message | One message | `retrieveMono(Class<T>)` / `Mono<T>` |
| Fire-and-forget | One message | No business response expected | `send(): Mono<Void>` |
| Request-stream | One request | Stream of messages | `retrieveFlux(Class<T>)` / `Flux<T>` |
| Request-channel | Stream of request messages | Stream of response messages | `data(Flux<T>, T.class)` / `retrieveFlux(...)` |

### 3.1. Request-Response

~~~text
Requester                 Responder
   |-- REQUEST_RESPONSE ---->|
   |<----- PAYLOAD ----------|
~~~

Fits profile lookups, product reads, and quick computations. There is no HTTP 200 in an RSocket exchange; outcomes travel via RSocket `PAYLOAD` and errors via RSocket `ERROR` semantics.

### 3.2. Request-Stream and Backpressure

~~~text
Requester                 Responder
   |-- REQUEST_STREAM ------>|
   |<--- PAYLOAD #1 ---------|
   |-- REQUEST_N (+2) ------>|
   |<--- PAYLOAD #2 ---------|
   |<--- PAYLOAD #3 ---------|
   |<--- COMPLETE -----------|
~~~

The requester can signal **demand** for how many items it is ready to receive. RSocket sends signals like `REQUEST_N` to throttle streams across the network boundary. This distinguishes it from raw WebSocket: you do not have to invent a custom demand protocol for RSocket's interaction models. Still, backpressure **does not** automatically provide persistence, offline inboxes, durable queues, or exactly-once semantics.

### 3.3. Fire-and-Forget

The requester sends one message expecting no business response. When Spring's `send()` completes its `Mono<Void>`, it does not confirm the responder committed a database write or finished async work. When business acknowledgement is needed, choose request-response or an explicit acknowledgement mechanism.

### 3.4. Request-Channel

Both peers exchange streams within a single interaction:

~~~text
Requester -- "one" ----> Responder
Requester -- "two" ----> Responder
Requester <-- "ONE" ---- Responder
Requester <-- "TWO" ---- Responder
~~~

A channel is neither two HTTP requests nor a STOMP subscription. A Spring responder can accept `Flux<String>` and return `Flux<String>`. Streaming in both directions requires careful handling of demand, cancellation, and errors.

### 3.5. Requester and Responder Are Not Locked to Client/Server

After RSocket `SETUP`, either side can potentially initiate interactions. Thus RSocket distinguishes **requester vs. responder per interaction** rather than assuming the TCP initiator can only send requests. To accept requests from the server side, the client must register an appropriate responder; it is not active automatically just from opening a connection.

## 4. TCP Transport: A Dedicated Listener

~~~text
RSocketRequester
     |
     | TCP connect localhost:9898
     | RSocket SETUP / frames
     v
RSocket TCP server :9898

Spring HTTP web server :8080  (if present) — separate listener
~~~

Configuration:

~~~properties
server.port=8080
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=9898
~~~

- `server.port` controls the HTTP listener.
- `spring.rsocket.server.port` controls the standalone RSocket listener.
- Even though both listeners run in the **same Spring Boot process**, they use distinct addresses/ports/sockets.
- `curl http://localhost:9898` is not an RSocket client; TCP RSocket **does not** parse HTTP methods or paths.
- Do not set `spring.rsocket.server.mapping-path` trying to "mount a path" on TCP: mapping path applies only to the WebSocket transport.
- If HTTP is unnecessary, you can run a non-web Boot app with only `spring-boot-starter-rsocket` and a standalone TCP RSocket port.

TCP typically fits service-to-service communication in networks allowing raw TCP, though it requires its own firewall, TLS/mTLS, load balancing, and client health checks.

## 5. WebSocket Transport: HTTP Handshake, RSocket Frames

~~~text
RSocketRequester
  |
  | GET /rsocket HTTP/1.1
  | Upgrade: websocket
  v
Reactor Netty WebFlux :8080
  |
  | HTTP 101 Switching Protocols
  | WebSocket binary frames carrying RSocket SETUP
  | After SETUP: request-response / request-stream / channel ...
  v
Spring RSocketMessageHandler
  |
  '--> @MessageMapping("greet")
~~~

Two **independent** steps:

1. **HTTP WebSocket handshake**: the transport opens. HTTP `101` does not prove RSocket is ready.
2. **RSocket SETUP**: agrees on MIME settings, keepalive, and connection capabilities; only then do RSocket request frames, route metadata, and payloads flow.

`ws://` is cleartext WebSocket; `wss://` uses TLS. Native browser `WebSocket` **does not** know how to encode RSocket frames. Browsers need a compatible RSocket/WS library; this lab uses Spring Java `RSocketRequester` for clarity.

**HTTP/2 note:** most WebSocket examples rely on HTTP/1.1 Upgrade. WebSocket over HTTP/2 uses RFC 8441 extended CONNECT and requires end-to-end support across hops. Never assume that because a browser uses `h2` for HTML pages, every hop supports `h2` for WebSocket/RSocket.

## 6. Conditions to Mount RSocket onto the Web Server in Spring Boot 3.3

Spring Boot provides RSocket auto-configuration via `spring-boot-starter-rsocket`. Two server arrangements exist:

- **Independent RSocket server:** sets `spring.rsocket.server.port`, creating a standalone RSocket server (TCP or WebSocket transport).
- **Integrated RSocket WebSocket server:** mounts onto the Reactor Netty WebFlux web listener with dedicated settings.

For **integrated/shared-port** mode, every condition below must hold:

1. The application is genuinely `WebApplicationType.REACTIVE`/Spring WebFlux.
2. The actual embedded web server is **Reactor Netty**.
3. Both `spring-boot-starter-rsocket` and WebFlux are present.
4. `spring.rsocket.server.transport=websocket`.
5. `spring.rsocket.server.mapping-path=/rsocket` (or another valid path).
6. **Do not set `spring.rsocket.server.port`** requesting a standalone RSocket listener.
7. The web listener is running at `server.port`, and network/proxy/security allow WS upgrades on the mapping path.

Minimal configuration to share the HTTP port:

~~~properties
server.port=8080
spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket

# Do NOT set spring.rsocket.server.port.
~~~

When all conditions are satisfied:

~~~text
HTTP GET http://localhost:8080/http/ping
RSocket WS ws://localhost:8080/rsocket
      \_______________________/
            same port 8080
~~~

**Important:** Spring Boot docs specify that this integration **supports Reactor Netty only**. Tomcat/Servlet MVC supports plain WebSocket and STOMP, yet Boot does not mount RSocket WebSocket onto Tomcat's listener via this configuration. If an app includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Boot 3.3 normally selects **SERVLET**, not REACTIVE. Always verify the actual application type and web server.

## 7. Topology Selection Table

| Runtime and Configuration | HTTP Listener | RSocket | Result |
| --- | --- | --- | --- |
| WebFlux/Reactor Netty + WS + mapping-path, no RSocket port | `server.port` | WS on the same HTTP port | **Shares embedded listener** |
| WebFlux/Reactor Netty + TCP + port=9898 | `server.port` | TCP :9898 | Two listeners |
| WebFlux/Reactor Netty + WS + port=9898 | `server.port` | Standalone WS :9898 | Two listeners |
| Servlet MVC/Tomcat + TCP + port=9898 | Tomcat HTTP | TCP :9898 | Standalone RSocket, not shared |
| Servlet MVC/Tomcat + WS + mapping-path, no RSocket port | Tomcat HTTP | No Boot shared-port integration supported | Do not expect it to auto-work |
| Non-web Boot + TCP + port=9898 | No HTTP | TCP :9898 | RSocket-only process |
| WebFlux + transport=WS, missing mapping-path and port | HTTP if web starter present | Missing required RSocket listener config | Starter alone is not enough |

**Distinguish "same JVM," "same backend listener," and "same public port":** these are three different things. Two listeners inside one JVM can be unified behind one public `:443` by a reverse proxy/ingress, yet that is sharing **at the edge**, not a shared Reactor Netty embedded server.

### 7.1. Four Easily Confused Properties

| Property | Meaning | Applies To? |
| --- | --- | --- |
| `server.port` | HTTP web server port | WebFlux/MVC listener |
| `spring.rsocket.server.port` | Standalone RSocket port | TCP or independent WS |
| `spring.rsocket.server.transport` | `tcp` or `websocket` (default `tcp`) | RSocket wire transport |
| `spring.rsocket.server.mapping-path` | HTTP WebSocket upgrade path | Integrated WebFlux WS topology |

`spring.rsocket.server.address` sets the bind address for a standalone RSocket listener, separate from `server.address` for the web listener. In shared-port mode, the web listener's network binding is governed by `server.address`.

## 8. Lab: Java 17, Spring Boot 3.3.5, Running TCP and WS from the Same Code

We will create an application with three profiles:

- `tcp`: WebFlux HTTP on `127.0.0.1:8080` and **separate RSocket TCP** on `127.0.0.1:9898`.
- `ws`: WebFlux HTTP on `127.0.0.1:8080` and **shared-port RSocket WS** at `/rsocket`.
- `client`: a **non-web** Spring application using `RSocketRequester` to verify all four interaction models. The client runs in a **separate process** and opens no listener.

No database, Docker, or broker is needed. You only need Maven 3.x, JDK 17+, and the Spring dependencies managed by the Boot starter parent. The lab uses formatted text payloads for easy inspection.

### 8.1. Project Structure

~~~text
rsocket-transport-lab/
├── pom.xml
└── src/main/
    ├── java/com/example/rsocketlab/
    │   ├── RSocketTransportLabApplication.java
    │   ├── HttpProbeController.java
    │   ├── DemoRSocketController.java
    │   └── RSocketDemoClientRunner.java
    └── resources/
        ├── application.properties
        ├── application-tcp.properties
        ├── application-ws.properties
        └── application-client.properties
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>rsocket-transport-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-rsocket</artifactId>
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

`spring-boot-starter-webflux` provides the reactive web server using Reactor Netty by default; `spring-boot-starter-rsocket` provides RSocket Java, Spring messaging codecs, and requester/responder support. **Do not** add Servlet MVC `spring-boot-starter-web` to this shared-port lab project.

### 8.3. Spring Boot Main

**`src/main/java/com/example/rsocketlab/RSocketTransportLabApplication.java`:**

~~~java
package com.example.rsocketlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketTransportLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RSocketTransportLabApplication.class, args);
    }
}
~~~

### 8.4. HTTP Controller to Verify server.port

**`src/main/java/com/example/rsocketlab/HttpProbeController.java`:**

~~~java
package com.example.rsocketlab;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HttpProbeController {

    @GetMapping("/http/ping")
    public Mono<String> ping() {
        return Mono.just("HTTP OK");
    }
}
~~~

This is an **HTTP endpoint** on WebFlux, distinct from RSocket routes. It runs on web listener `server.port=8080` in both server profiles.

### 8.5. Complete RSocket Responder

**`src/main/java/com/example/rsocketlab/DemoRSocketController.java`:**

~~~java
package com.example.rsocketlab;

import java.time.Duration;
import java.util.Locale;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class DemoRSocketController {

    // Request-response: one request and one result.
    @MessageMapping("greet")
    public Mono<String> greet(String name) {
        return Mono.just("Hello, " + name + "!");
    }

    // Request-stream: emits exactly 3 items.
    @MessageMapping("ticks")
    public Flux<String> ticks(String name) {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(150))
                .map(n -> "event-" + n + ":" + name);
    }

    // Request-channel: receives Flux, returns Flux.
    @MessageMapping("upper")
    public Flux<String> upper(Flux<String> values) {
        return values.map(v -> v.toUpperCase(Locale.ROOT));
    }

    // Fire-and-forget: returns no business response.
    @MessageMapping("notify")
    public Mono<Void> notify(String message) {
        System.out.println("SERVER NOTIFY: " + message);
        return Mono.empty();
    }
}
~~~

**Explanation:**

- `@MessageMapping` here belongs to the **RSocket responder**; routes are metadata `greet`, `ticks`, `upper`, or `notify`, not HTTP GET endpoints.
- `Mono<String>` is request-response; `Flux<String>` is request-stream or channel depending on the inbound payload type.
- `Flux.range(1,3)` always produces three ordered items; `delayElements` makes streaming easy to observe.
- `notify` only prints to the console without a durable queue. A successful `send()` on the client does not guarantee the handler committed a real transaction.
- `upper` consumes a stream of request payloads and uppercases them using `Locale.ROOT`.
- The code avoids blocking DB calls, `Thread.sleep`, or `block()` inside reactive responders; real blocking work requires dedicated thread scheduling/architecture.

### 8.6. Shared Properties

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=rsocket-transport-lab
server.port=8080

# Do not set spring.rsocket.server.port in the shared file:
# each profile chooses its own topology.
~~~

### 8.7. TCP Profile: 2 Listeners

**`src/main/resources/application-tcp.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.rsocket.server.transport=tcp
spring.rsocket.server.address=127.0.0.1
spring.rsocket.server.port=9898

# TCP transport does not use mapping-path.
~~~

When running with the `tcp` profile, HTTP is on 8080 and RSocket TCP is on 9898. Never assume RSocket TCP 9898 is TLS-protected just because HTTP `server.ssl.*` is configured.

### 8.8. WebSocket Profile: Shared Port

**`src/main/resources/application-ws.properties`:**

~~~properties
server.address=127.0.0.1
server.port=8080

spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket

# MUST NOT declare spring.rsocket.server.port.
~~~

This is the standard example configuration to mount RSocket-over-WebSocket onto the Reactor Netty WebFlux server. HTTP `/http/ping` and RSocket WS `/rsocket` share port 8080.

### 8.9. Client Profile Without Opening a Web Server

**`src/main/resources/application-client.properties`:**

~~~properties
spring.main.web-application-type=none

app.client.transport=tcp
app.client.host=127.0.0.1
app.client.port=9898
app.client.ws-url=ws://127.0.0.1:8080/rsocket
~~~

`web-application-type=none` prevents the client app from starting an embedded HTTP web listener. The file omits any RSocket server port because this process is a **requester** and opens no RSocket listener. Running with profile `client` avoids port conflicts on 8080/9898.

### 8.10. Shared RSocketRequester Client for Both TCP and WS

**`src/main/java/com/example/rsocketlab/RSocketDemoClientRunner.java`:**

~~~java
package com.example.rsocketlab;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;

@Component
@Profile("client")
public class RSocketDemoClientRunner implements ApplicationRunner {

    private final RSocketRequester.Builder builder;
    private final String transport;
    private final String host;
    private final int port;
    private final URI wsUri;

    public RSocketDemoClientRunner(
            RSocketRequester.Builder builder,
            @Value("${app.client.transport:tcp}") String transport,
            @Value("${app.client.host:127.0.0.1}") String host,
            @Value("${app.client.port:9898}") int port,
            @Value("${app.client.ws-url:ws://127.0.0.1:8080/rsocket}")
            URI wsUri) {
        this.builder = builder;
        this.transport = transport;
        this.host = host;
        this.port = port;
        this.wsUri = wsUri;
    }

    @Override
    public void run(ApplicationArguments args) {
        RSocketRequester.Builder configured =
                builder.dataMimeType(MimeTypeUtils.TEXT_PLAIN);

        RSocketRequester requester;
        if ("tcp".equalsIgnoreCase(transport)) {
            requester = configured.tcp(host, port);
        } else if ("websocket".equalsIgnoreCase(transport)) {
            requester = configured.websocket(wsUri);
        } else {
            throw new IllegalArgumentException(
                    "Unsupported transport: " + transport);
        }

        String greeting = requester.route("greet")
                .data("Lan")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_RESPONSE: " + greeting);

        List<String> ticks = requester.route("ticks")
                .data("Lan")
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_STREAM: " + ticks);

        List<String> uppercase = requester.route("upper")
                .data(Flux.just("one", "two"), String.class)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(5));
        System.out.println("REQUEST_CHANNEL: " + uppercase);

        requester.route("notify")
                .data("client says hi")
                .send()
                .block(Duration.ofSeconds(5));
        System.out.println("FIRE_AND_FORGET: send completed");
    }
}
~~~

**Client code explanation:**

1. `@Profile("client")` ensures the runner runs only under the `client` profile; server profiles do not fire test requests at themselves.
2. Spring Boot auto-configures `RSocketRequester.Builder`; constructor injection supplies it to configure transport and codecs.
3. `dataMimeType(MimeTypeUtils.TEXT_PLAIN)` marks `String` payloads as `text/plain`, independent of HTTP handshake `Content-Type`.
4. `.tcp(host, port)` and `.websocket(wsUri)` are the right requester factory methods in Spring Framework 6.1. The requester can **connect lazily** upon subscription, so constructing the object alone does not verify the server is up.
5. `retrieveMono` reads one item, `retrieveFlux` reads a stream, and `.data(Flux.just(...), String.class)` sends a stream for Request-Channel.
6. `block(Duration.ofSeconds(5))` is used only in this **non-web** CLI runner; never call `block()` on a Reactor Netty WebFlux event-loop thread.
7. `send()` for Fire-and-Forget signals sending finished, not business acknowledgement.
8. The requester reuses connections via the client library; pooling, load balancing, resume, auth, or keepalive require additional configuration.

## 9. Running the Lab in TCP Mode

From the project directory:

~~~bash
mvn clean package
~~~

Open **Terminal A**:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=tcp
~~~

On Windows PowerShell you can write it on one line:

~~~powershell
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=tcp
~~~

Once running, verify HTTP from **Terminal B**:

~~~bash
curl -i http://127.0.0.1:8080/http/ping
~~~

A successful response returns HTTP 200 with exact body:

~~~text
HTTP OK
~~~

Next, run the client profile:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client
~~~

Lines printed by the runner on success:

~~~text
REQUEST_RESPONSE: Hello, Lan!
REQUEST_STREAM: [event-1:Lan, event-2:Lan, event-3:Lan]
REQUEST_CHANNEL: [ONE, TWO]
FIRE_AND_FORGET: send completed
~~~

The Spring Boot app also emits startup logs; these four lines show only the stdout **printed by the client runner**, not the entire fixed stdout. In Terminal A, the `notify` handler prints:

~~~text
SERVER NOTIFY: client says hi
~~~

Two independent connections are verified: `HTTP 8080` and `RSocket TCP 9898`. Calling `http://127.0.0.1:9898/http/ping` via curl **does not** reach the HTTP web controller.

To stop the server, press `Ctrl+C` in Terminal A. Never run two instances trying to bind ports 8080/9898 simultaneously.

## 10. Running WS Mode Sharing the HTTP Listener

Stop the TCP server and run:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=ws
~~~

The HTTP route still responds:

~~~bash
curl -i http://127.0.0.1:8080/http/ping
~~~

Switch the RSocket client to WebSocket on **the same web port 8080**:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client \
  --app.client.transport=websocket
~~~

In this project, the client's default WS URL is `ws://127.0.0.1:8080/rsocket`. Upon connecting, the four lines for request-response, request-stream, channel, and FNF **produce the exact same results** as TCP mode because the responder/business logic is identical.

**Conclusions from these results:**

- HTTP `/http/ping` and RSocket WS `/rsocket` are sharing **one embedded Reactor Netty port 8080**.
- Under the `ws` profile, **no** RSocket TCP port 9898 is opened by this config.
- The WebSocket handshake URL `/rsocket` **differs from** the RSocket route `greet`.
- No Java `@MessageMapping` rewrites were needed when changing transports.

### 10.1. Changing server.port in WS Mode

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=ws \
  --server.port=9080
~~~

Both HTTP and shared RSocket WS move to `9080`:

~~~text
http://127.0.0.1:9080/http/ping
ws://127.0.0.1:9080/rsocket
~~~

Matching client command:

~~~bash
java -jar target/rsocket-transport-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=client \
  --app.client.transport=websocket \
  --app.client.ws-url=ws://127.0.0.1:9080/rsocket
~~~

In **TCP mode**, changing `server.port` does not change `spring.rsocket.server.port` and vice versa.

### 10.2. Why Is `curl GET /rsocket` Not a Valid Test?

~~~bash
curl http://127.0.0.1:8080/rsocket
curl http://127.0.0.1:8080/greet
~~~

Both commands send ordinary HTTP GET requests; they **do not send WebSocket Upgrade, RSocket SETUP, or RSocket request frames**. An HTTP error from either GET does not prove `@MessageMapping("greet")` is broken.

The following browser snippet is also **not** an RSocket client yet:

~~~javascript
const socket = new WebSocket("ws://127.0.0.1:8080/rsocket");
socket.onopen = () => socket.send("hello");
~~~

Opening a WebSocket is not enough; plain text `"hello"` is not an RSocket frame. Browsers require a compatible RSocket-JavaScript client with proper codecs, metadata, and `SETUP`.

## 11. Equivalent YAML for the Topologies

### 11.1. Shared WS + WebFlux + Reactor Netty

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      # No dedicated RSocket port
~~~

### 11.2. Two Listeners: HTTP + TCP RSocket

~~~yaml
server:
  port: 8080

spring:
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

### 11.3. Non-Web RSocket-Only

~~~yaml
spring:
  main:
    web-application-type: none
  rsocket:
    server:
      transport: tcp
      port: 9898
~~~

For RSocket-only apps, `spring-boot-starter-rsocket` and annotated responders are the core pieces; no web server is needed. Standalone RSocket can run inside a Spring Boot application that is not a WebFlux HTTP server when auto-configuration matches.

### 11.4. Standalone RSocket-over-WebSocket

~~~properties
spring.rsocket.server.transport=websocket
spring.rsocket.server.port=9898
~~~

This is a **dedicated-port** WebSocket RSocket listener, not sharing `server.port`. Having `mapping-path` elsewhere does not turn it into an integrated listener once a standalone port is set. To verify the exact path of a standalone server, use an RSocket client/transport matching your version and server config rather than assuming WebFlux shared mode's `/rsocket`.

## 12. RSocket Route, Data, and Metadata MIME Types

An RSocket request consists of:

- **Route**: identifies the handler, e.g., `greet`, sent inside routing metadata.
- **Data payload**: business data such as `"Lan"` or a JSON record.
- **Metadata**: route, authentication, tracing, etc., per the negotiated metadata MIME type.
- **Stream ID** and frame type: supporting multiplexing and interaction semantics.

`@MessageMapping("greet")` is not HTTP `@GetMapping("/greet")`. Switching TCP to WS changes only the **transport/handshake**, not the route definition.

Spring Boot auto-configures `RSocketStrategies` with codecs; per Boot 3.3 docs, the framework can prefer CBOR, then JSON when the matching dependencies are on the classpath. For String-only demos like this lab, `MimeTypeUtils.TEXT_PLAIN` makes the codec explicit.

RSocket Request-Response snippet:

~~~java
Mono<String> result = requester.route("greet")
        .data("Lan")
        .retrieveMono(String.class);
~~~

This is a **snippet inside a method with `requester`**, not a standalone Java class. `result` is a `Mono`; the network exchange runs only when subscribed.

**Illustrative** JSON record example:

~~~java
public record ProductView(String id, String name) {}

// Send/receive once matching JSON/CBOR MIME and codecs are configured:
// Mono<ProductView> p = requester.route("product.find")
//       .data("42").retrieveMono(ProductView.class);
~~~

Do not treat the WebSocket handshake's HTTP `Content-Type` as the serialization format for RSocket messages. RSocket negotiates data/metadata MIME types via `SETUP`.

## 13. TLS for Shared WS vs. Standalone TCP Are Separate

### 13.1. Four Cases

~~~text
TCP without TLS:
  requester ===== TCP cleartext ===== :9898

TCP with TLS:
  requester ===== TLS/TCP ============ :9898

WebSocket without TLS:
  requester ===== ws:// ============== :8080/rsocket

WebSocket with TLS:
  requester ===== wss:// ============= :8443/rsocket
~~~

When RSocket WS **shares** the Reactor Netty web server, TLS for the HTTP/WSS port comes from web TLS config such as `server.ssl.*` and the embedded server certificate. With a **standalone RSocket TCP port**, TLS must be configured and verified **for the RSocket server itself**; Spring Boot 3.3 provides separate `spring.rsocket.server.ssl.*` and `spring.rsocket.server.ssl.bundle` properties.

Illustrative web TLS + shared RSocket WS config:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/etc/app/tls/web.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}

spring.rsocket.server.transport=websocket
spring.rsocket.server.mapping-path=/rsocket
~~~

This snippet assumes an existing certificate/keystore and environment secret; it is **not an immediately runnable localhost lab**. Clients connect using `wss://.../rsocket` and must verify CA/hostname. Never use trust-all certificate managers or disable TLS verification in production.

**Do not assume:** enabling `server.ssl.enabled=true` on web port 8443 automatically encrypts standalone RSocket TCP port 9898. Each listener has its own identity/trust and network policy.

### 13.2. HTTP Security and RSocket Security Are Two Layers

- The HTTP filter chain can protect HTTP endpoints and the WebSocket handshake when shared transport passes through the web server.
- RSocket `SETUP`/metadata/routes often need dedicated authentication and authorization. Spring Security provides `RSocketSecurity` and socket acceptor/payload interceptors.
- Never assume `authorizeHttpRequests()` or `authorizeExchange()` covers all RSocket frames, especially on a standalone TCP listener that bypasses HTTP completely.
- Enforce authentication at connection/setup and authorization per route, tenant, and data scope.
- WebSocket `Origin` headers help enforce browser policies, yet **are not authentication**; non-browser clients can spoof `Origin`.
- Cap message sizes, rates, concurrent streams, and validate payloads to prevent abuse.

## 14. Proxy/Ingress, One Public Port, and Two Listeners

### 14.1. NGINX WebSocket Upgrade

In a shared WS topology, a reverse proxy must forward `/rsocket` as a valid WebSocket upgrade. Core directive example:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    # Requires real ssl_certificate and ssl_certificate_key.

    location /rsocket {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

This is an **architectural snippet**, not a complete production NGINX config since certificates and security controls are omitted. Public clients call `wss://api.example.com/rsocket`, the proxy terminates TLS at the edge, and forwards the upgrade to `ws://127.0.0.1:8080/rsocket`. If policy mandates encryption between proxy and backend, configure TLS/re-encryption rather than plain HTTP.

**RSocket TCP cannot be routed by an HTTP `location` `proxy_pass` on `/rsocket`**, because it has no HTTP URL or path. Use an L4 TCP proxy/load balancer or an RSocket-aware gateway.

### 14.2. Shared Public Port vs. Shared Embedded Port

~~~text
Case A — embedded shared:
  HTTP client -----\
                    --> Reactor Netty :8080
  RSocket WS ------/       /http/ping and /rsocket

Case B — shared at public edge only:
  Client --> NGINX :443
               |--> MVC HTTP :8080
               '--> RSocket WS standalone :9898
~~~

In Case B, a browser sees only port 443, yet the backend runs two separate listeners. **Never claim Tomcat shares an embedded RSocket web port** merely because NGINX routes two upstreams behind one public endpoint.

### 14.3. Multi-Instance, Long-Lived Connections, and State

Long-lived RSocket connections stay pinned to one backend pod for their lifetime. When a pod restarts, clients must reconnect, likely landing on another replica. Session state, stream progress, in-memory subscriptions, and side effects **do not automatically move** with the connection. When durability/replay is required, design explicit offset/cursor persistence, outboxes, or protocol resumption supported by both peers.

## 15. Backpressure, Cancellation, Timeouts, and Resources

RSocket's **`REQUEST_N`/demand** regulates how many messages the requester is ready to accept. A responder returning `Flux` should honor cancellation and keep data sources non-blocking. However:

- Backpressure does not eliminate the need to cap RAM, buffers, message sizes, or slow consumers.
- Long-lived `Flux.interval`/telemetry streams need cancellation cleanup when clients disconnect.
- When a user cancels a stream, committed side effects do not automatically roll back.
- Fire-and-Forget has no business response; if you need delivery confirmation, build explicit acknowledgement.
- Timeouts span multiple layers: TCP connect, TLS handshake, WebSocket handshake, RSocket `SETUP`, per-route response, keepalive, and proxy idle timeouts.
- Client reconnect storms can overwhelm recovering servers; use backoff with jitter, attempt caps, and concurrency limits.
- Protocol-level resumption/leases exist as protocol features, **not things Boot enables out of the box** or guarantees that replay every business message.

Timeout snippet inside a reactive service:

~~~java
// Snippet in a method that already holds a requester:
Mono<String> greeting = requester.route("greet")
        .data("Lan")
        .retrieveMono(String.class)
        .timeout(Duration.ofSeconds(3));
~~~

This is not a standalone Java file. `timeout` emits an error when exceeded; production apps must map timeout errors per business contract rather than returning synthetic success fallbacks on critical operations.

**Never call `Thread.sleep`/`block()` on a Reactor Netty event loop.** In the CLI client lab, `block(Duration)` is used intentionally outside any server event loop.

## 16. Comparing RSocket with REST, SSE, Raw WebSocket, and STOMP

| Technology | Layer / Style | Strengths | When Unsuitable |
| --- | --- | --- | --- |
| HTTP REST | HTTP request-response | Huge ecosystem, cache/proxy/browser-friendly | Complex full-duplex streaming |
| SSE | HTTP server→client stream | Browser `EventSource`, one-way notifications | Needs bidirectional client→server streams |
| Raw WebSocket | WS transport with custom app protocol | Flexible text/binary, full-duplex | Want built-in RSocket routing/backpressure |
| STOMP-over-WebSocket | WS + STOMP text messaging/broker | Topic subscriptions, Spring MVC STOMP integration | Clients lack STOMP or need RSocket interaction semantics |
| **RSocket TCP** | RSocket binary/TCP | Service-to-service, four interactions, backpressure | Infra blocks raw TCP ports |
| **RSocket WebSocket** | RSocket binary/WS | Traverses WS-capable edges, WebFlux shared-port | No RSocket client library or proxy blocks upgrades |
| gRPC | Common RPC over HTTP/2 | Protobuf schemas/tooling, unary/streaming | Target clients/proxies lack HTTP/2/gRPC support |

Choose RSocket when there is a real need for **streaming, bidirectional interactions, and demand/cancellation**, supported by the client ecosystem. Never choose it merely because "WebSocket is newer than HTTP" or "RSocket must be faster than gRPC." Measure CPU, networking, latency, resource budgets, and maintainability.

## 17. Error Diagnosis Workflow

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| RSocket TCP connect refused | Port 9898 not listening, firewall, or wrong profile | Check process/listeners and `spring.rsocket.server.port` |
| HTTP 8080 works yet RSocket does not | Active web starter does not create an RSocket listener automatically | Compare profiles, transport, `mapping-path`/port |
| WS handshake 404 | Wrong `/rsocket` path, proxy rewrite, or RSocket route confused with URL | Check `mapping-path` and actual WS URL |
| WS handshake lacks HTTP 101 | Proxy fails to forward `Upgrade`, or TLS/`Origin`/auth failure | Inspect Network WS tab and reverse proxy logs |
| WS is OPEN yet RSocket request fails | Missing RSocket `SETUP`, unsupported MIME, invalid frame | Use `RSocketRequester` and check RSocket logs |
| HTTP `GET /rsocket` returns error | Plain GET is not an RSocket WS upgrade | Test with a real RSocket client |
| Route `greet` unhandled | Confused `@GetMapping` with `@MessageMapping`, wrong route metadata | Compare `requester.route` against handler |
| MVC/Tomcat lacks RSocket WS shared path | Does not meet Reactor Netty/REACTIVE conditions | Switch to WebFlux/Netty or standalone RSocket |
| Both `starter-web` and `starter-webflux` present | Boot prioritizes Servlet MVC | Inspect dependency tree and web application type |
| Set both `mapping-path` and port yet not shared | Setting RSocket port forces a standalone server | Remove RSocket port when wanting WebFlux shared mode |
| Web TLS works yet TCP RSocket is unencrypted | Separate SSL configs for the two listeners | Configure `spring.rsocket.server.ssl.*` |
| Slow stream or timeout | Demand/backpressure, upstream, Netty event loop, or proxy idle | Inspect stream metrics and all timeout layers |
| RSocket connections lost during deploy | Pod restart on long-lived connections | Implement backoff reconnect, state, and replay strategy |
| OOM under high load | Unbounded payloads, buffers, concurrent streams | Enforce resource limits, metrics, load tests |
| Client uses STOMP.js only | Confused STOMP with RSocket | Switch to an RSocket protocol client |
| FNF sent yet server never records it | Network/handler failure, no business ACK | Use request-response/receipts when confirmation matters |

### 17.1. Layer-by-Layer Debug Checklist

1. **Application**: is actual web application type `REACTIVE`/`SERVLET`/`NONE`; is the web server Netty or Tomcat?
2. **Transport**: TCP or WS, and is a dedicated RSocket port configured?
3. **Network**: are DNS/host/port, firewalls, ingress, TLS/SNI, and certificates right?
4. **Handshake**: did TCP connect, HTTP WS Upgrade 101 (if WS), and RSocket `SETUP` actually succeed?
5. **Routing**: do metadata routes match `@MessageMapping`, and are RSocket codecs compatible?
6. **Interaction**: request-response, stream, channel, or FNF? Are backpressure and cancellation handled?
7. **Production**: metrics/errors, retry storms, memory buffers, proxy idle timeouts, multi-instance behavior?

When unsure which layer failed, verify the direct local lab first, then add proxy/TLS/load-balancer layers one by one to isolate the exact break.

## 18. Common Misconceptions

1. **"RSocket over TCP is just WebSocket."** No: TCP and WebSocket are two different transports.
2. **"server.port=8080 is the RSocket port."** No: that is the web listener.
3. **"WebFlux means every RSocket automatically shares the port."** No: you also need WS transport, `mapping-path`, and no dedicated RSocket port.
4. **"Having WebSocket on Tomcat means Boot mounts RSocket WS on Tomcat."** Not under Boot's documented shared-port auto-configuration.
5. **"One process means one socket."** No: web `:8080` and RSocket TCP `:9898` can coexist in the same JVM.
6. **"Sharing public :443 means sharing an embedded server."** No: a proxy can route to separate backend listeners.
7. **"WS handshake 101 means RSocket SETUP succeeded."** No: RSocket frames happen afterward.
8. **"RSocket route `greet` is HTTP `GET /greet`."** No: it is a metadata route.
9. **"RSocket has backpressure so no messages can ever be lost."** No: persistence/replay remain separate concerns.
10. **"Fire-and-forget completing means business processing finished."** No.
11. **"`server.ssl` automatically secures a standalone RSocket TCP port."** Not automatically.
12. **"Native browser WebSocket speaks RSocket natively."** No: an RSocket protocol client is required.
13. **"`@MessageMapping` for RSocket and STOMP share one broker."** No: identical annotation name, different handlers and wire protocols.
14. **"Calling `block()` inside a reactive server is harmless."** No: it risks stalling the event loop.

## 19. Self-Check Exercises

**Question 1.** At which protocol layer do RSocket and WebSocket differ?

**Question 2.** State all conditions required for WebFlux Spring Boot 3.3 to host RSocket WS on the same HTTP listener.

**Question 3.** Why don't `server.port=8080` and `spring.rsocket.server.port=9898` share a port?

**Question 4.** How can a Spring MVC/Tomcat application expose HTTP and RSocket on one public port without claiming a shared embedded server?

**Question 5.** In the lab, how do `/http/ping`, `/rsocket`, and `greet` differ?

**Question 6.** A client calls `GET /rsocket` and receives 404/400; why isn't that enough to say the RSocket responder is broken?

**Question 7.** When the server runs with profile `ws`, does RSocket TCP port 9898 open automatically?

**Question 8.** What mechanism regulates messages in RSocket Request-Stream? Does it automatically persist messages while the client is offline?

**Question 9.** Must you configure TLS separately for a TCP RSocket port when the HTTP listener already uses HTTPS?

**Question 10.** Why can the Spring Boot `client` profile call RSocket routes without opening any listener port?

**Question 11.** Can a Request-Channel accept `Flux<String>` and return `Flux<String>`? How does that differ from raw WebSocket?

**Question 12.** Does Fire-and-Forget satisfy "report success only after DB commit"?

**Suggested answers:**

1. RSocket is a binary messaging protocol; WebSocket is a transport with handshakes and frames.
2. `WebApplicationType.REACTIVE`, embedded Reactor Netty, `starter-rsocket` + `webflux`, `transport=websocket`, `mapping-path`, no dedicated RSocket port, active web listener.
3. The two properties configure two separate listeners.
4. Put a reverse proxy/ingress in front routing the public WS path to a standalone RSocket backend, or switch the app to WebFlux/Netty.
5. `/http/ping` is an HTTP route; `/rsocket` is the WebSocket handshake path; `greet` is an RSocket metadata route.
6. Plain GET does not send WS upgrade, RSocket `SETUP`, or `REQUEST_RESPONSE`.
7. No; profile `ws` does not configure TCP 9898.
8. RSocket demand/`REQUEST_N`; it provides no automatic durable replay.
9. Yes, verify standalone RSocket SSL config independently.
10. The client profile uses `RSocketRequester` outbound and needs no inbound server port.
11. Yes, Request-Channel supports protocol-level RSocket flow control; raw WS requires building your own app-level protocol.
12. No, use Request-Response/business ACK or a durable workflow.

## 20. Practical Deployment Checklist

- [ ] Clearly choose the topology: standalone TCP, standalone WS, Netty shared WS, or edge proxy sharing.
- [ ] Verify the actual Spring Boot web application type and embedded server (Reactor Netty vs. Tomcat).
- [ ] For shared mode: `REACTIVE` + Reactor Netty + `transport=websocket` + `mapping-path` + **no RSocket port**.
- [ ] For TCP mode: dedicated RSocket port and dedicated service/network policies.
- [ ] Keep HTTP `server.port` distinct from RSocket `spring.rsocket.server.port`.
- [ ] Use an RSocket client supporting `SETUP`, metadata, codecs, routes, and interaction models.
- [ ] Enforce timeouts, backpressure, cancellation, and concurrent stream limits.
- [ ] Bound and validate payloads, frame sizes, and codecs explicitly.
- [ ] For WSS, verify TLS certificates, proxy `Upgrade`/paths, and `Origin`/auth policies.
- [ ] For TCP, configure RSocket TLS/mTLS and authorization independently rather than assuming HTTP SSL covers it.
- [ ] Do not confuse RSocket with STOMP, raw WS, or HTTP SSE.
- [ ] Add reconnect backoff with jitter to avoid reconnect storms.
- [ ] Across multiple replicas, plan state/replay/resumption and graceful shutdown.
- [ ] Track separate metrics/traces for RSocket `SETUP`/errors/routes/connections/streams and web requests.
- [ ] Test happy paths, wrong transports, wrong MIME/routes, timeouts, proxy idle limits, restarts, and unauthorized access.

## 21. References

- Spring Boot 3.3 — RSocket server auto-configuration and WebFlux shared transport: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- Spring Boot 3.3 — Common Application Properties (`spring.rsocket.server.*`, `server.*`): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Framework — RSocket protocol, four interaction models, SETUP, metadata, `@MessageMapping`, requesters: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Framework 6.1 — `RSocketRequester.Builder`, `tcp`/`websocket`: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html
- Spring Boot 3.4 — RSocket reference (for model comparison): https://docs.spring.io/spring-boot/3.4/reference/messaging/rsocket.html
- Spring Security — Reactive RSocket security: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- RSocket Protocol Specification: https://rsocket.io/about/protocol/
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/
- RFC 6455 — The WebSocket Protocol: https://www.rfc-editor.org/rfc/rfc6455
- RFC 8441 — Bootstrapping WebSockets with HTTP/2: https://www.rfc-editor.org/rfc/rfc8441