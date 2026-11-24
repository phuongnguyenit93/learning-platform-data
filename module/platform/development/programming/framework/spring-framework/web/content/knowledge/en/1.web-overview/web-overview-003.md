# The `spring-web`, `spring-webmvc`, `spring-webflux`, and `spring-websocket` Modules

## 1. The big picture

In Spring Framework, "web" is not just one way of building applications. There is a shared HTTP communication support layer, two server-side HTTP processing models, and APIs for bidirectional communication over WebSocket.

| Artifact | Primary responsibility | Representative APIs/components | Best suited when |
| --- | --- | --- | --- |
| `org.springframework:spring-web` | HTTP infrastructure and shared web features | `HttpHeaders`, `HttpEntity`, `ResponseEntity`, `MediaType`, `RestClient`, HTTP message converters | Using HTTP abstractions, making synchronous REST calls, serving as the base for web frameworks |
| `org.springframework:spring-webmvc` | Web/REST framework on the **Servlet stack** | `DispatcherServlet`, `@Controller`, `@RestController`, `HandlerMapping`, `ViewResolver` | CRUD REST, web apps using Servlets and many blocking libraries |
| `org.springframework:spring-webflux` | **Reactive** web/REST framework, plus reactive HTTP client | `DispatcherHandler`, `Mono`, `Flux`, `RouterFunction`, `WebClient` | Non-blocking I/O, streaming, reactive data flows |
| `org.springframework:spring-websocket` | WebSocket and STOMP messaging on the **Servlet stack** | `WebSocketHandler`, `TextWebSocketHandler`, `@EnableWebSocket`, `@EnableWebSocketMessageBroker` | Chat, real-time notifications, bidirectional communication in Servlet apps |

**Not four peer choices:** `spring-web` is the foundation; `spring-webmvc` and `spring-webflux` are two different HTTP web frameworks; `spring-websocket` adds WebSocket for the Servlet stack. WebFlux also has its own **reactive WebSocket API**. An application can include multiple artifacts, but the mere presence of a dependency does not determine which server type is running.

```text
                      Spring Framework
                            |
                      spring-web
                HTTP foundation, codecs,
                 synchronous HTTP client
                            |
                 +----------+-----------+
                 |                      |
            spring-webmvc          spring-webflux
          Servlet / HTTP MVC      Reactive / HTTP
          DispatcherServlet       DispatcherHandler
                 |                      |
           spring-websocket      Reactive WebSocket API
          WebSocket + STOMP      in spring-webflux
```

The diagram depicts the **roles** of the modules, not a complete transitive dependency graph. In practice, higher-level modules may pull in foundational libraries through dependency management.

## 2. `spring-web`: the shared HTTP foundation

This module provides objects and mechanisms for working with HTTP, for example:

- `HttpHeaders`: holds headers such as `Content-Type`, `Accept`, and `Authorization`.
- `HttpMethod`, `HttpStatusCode`, `MediaType`: HTTP methods, status codes, and media types.
- `HttpEntity<T>`: body + headers; `ResponseEntity<T>` adds HTTP status and is commonly used as a controller return type.
- `HttpMessageConverter`: reads/writes HTTP bodies in supported formats, such as JSON when appropriate libraries and configuration are present.
- `RestClient`: **synchronous** fluent HTTP client; `RestTemplate` is an older synchronous HTTP client still seen in legacy codebases.
- Underlying HTTP abstractions, codecs, and integration classes used by many other parts of Spring web.

Example calling an external API with `RestClient`:

```java
import org.springframework.web.client.RestClient;

public class BookClient {
    private final RestClient client =
            RestClient.create("https://api.example.com");

    public String findBook(String id) {
        return client.get()
                .uri("/books/{id}", id)
                .retrieve()
                .body(String.class);
    }
}
```

This is an **illustrative class**, not a standalone program, and `api.example.com` is only a placeholder address. `body(String.class)` in synchronous usage fetches the result before the method returns; timeouts, HTTP error handling, and load limits must be configured per application requirements.

**Important distinction:** `RestClient` is an **HTTP client**. Having `spring-web` alone does not mean the application has configured `DispatcherServlet`, `DispatcherHandler`, an HTTP server, or REST controllers.

## 3. `spring-webmvc`: Spring MVC on the Servlet stack

### 3.1. Front controller and request path

Spring MVC is built on the Jakarta Servlet API, typically running inside a Servlet container (Tomcat, Jetty…). The central request dispatcher is `DispatcherServlet` following the *front controller* pattern. The framework routes an HTTP request to the matching controller, converts parameters into Java values, executes logic, and produces a response.

```text
HTTP client
    |
Servlet container and Filter chain
    |
DispatcherServlet
    |
HandlerMapping -> HandlerAdapter -> Controller method
    |
Business service / repository
    |
HTTP message conversion or view rendering
    |
HTTP response
```

Common annotations include `@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam`, `@RequestBody`, and `@ExceptionHandler`. For REST APIs, `@RestController` typically returns data in the response body; for page-rendering apps, `@Controller` can return a view name for `ViewResolver` to handle.

REST controller example:

```java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/hello/{name}")
    public Greeting hello(@PathVariable String name) {
        return new Greeting("Hello, " + name);
    }

    public record Greeting(String message) {}
}
```

When an MVC application has a configured server and JSON converter, calling `GET /hello/Lan` returns the body:

```json
{"message":"Hello, Lan"}
```

This is a **Spring-managed class**, not a standalone application runnable via `javac`/`java`; it requires an application context, component scanning or bean declarations, servlet configuration, and an HTTP runtime. In Spring Boot, starters and auto-configuration usually handle most of this setup.

### 3.2. Blocking and asynchronous in MVC

In the common Servlet model, a container-assigned thread executes the controller. If code calls blocking JDBC or a blocking HTTP client, the thread usually waits for the I/O operation to complete. This is **not inherently a bug**: with JPA/JDBC and synchronous libraries, MVC is an understandable and popular choice.

You should not conclude MVC is "synchronous only": Servlet async and types like `Callable`, `DeferredResult`, or streaming mechanisms can enable asynchronous processing at certain stages. However, the application still uses the **Servlet stack and DispatcherServlet**; these APIs do not automatically turn the server into WebFlux.

## 4. `spring-webflux`: Spring WebFlux on the reactive stack

### 4.1. Reactive and non-blocking model

WebFlux was added by Spring in version 5.0. It is a web framework with **non-blocking** infrastructure, Reactive Streams, and backpressure support. It uses `DispatcherHandler` as its dispatcher and **does not use `DispatcherServlet` as WebFlux's HTTP dispatcher**.

WebFlux can run on Reactor Netty or Servlet container environments with suitable non-blocking integration. Therefore, **WebFlux does not necessarily mean Netty**.

WebFlux supports two endpoint styles:

1. **Annotated controllers:** `@RestController`, `@GetMapping`… sharing annotation names with MVC.
2. **Functional endpoints:** declaring routes via `RouterFunction` and `HandlerFunction`.

WebFlux uses Project Reactor in many APIs:

- `Mono<T>` represents a publisher that can emit **0 or 1** element and then complete or error.
- `Flux<T>` represents a publisher that can emit **0 to many** elements and then complete or error.
- `map`, `flatMap`, `filter`, `onErrorResume`… allow describing transformation and handling steps.
- Backpressure in Reactive Streams describes a consumer's ability to request the amount of data it needs; it does not mean every backend resource automatically throttles load perfectly.

A WebFlux endpoint:

```java
package example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello/{name}")
    public Mono<Greeting> hello(@PathVariable String name) {
        return Mono.just(new Greeting("Hello, " + name));
    }

    public record Greeting(String message) {}
}
```

A `GET /hello/Lan` request in a properly configured WebFlux application still returns an equivalent JSON object as the MVC example. **The important difference is the HTTP runtime and how the result is processed**, not the annotation names.

`Mono.just(...)` in the example creates a publisher from an already available value; it **does not demonstrate real non-blocking I/O**. WebFlux's benefits become clearer when requests combine WebClient, reactive database drivers, or genuinely asynchronous data streams.

### 4.2. `WebClient`: reactive client in WebFlux

`WebClient` is an HTTP client using a reactive API. Example:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class BookClient {
    private final WebClient client =
            WebClient.create("https://api.example.com");

    public Mono<String> findBook(String id) {
        return client.get()
                .uri("/books/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

`findBook` returns `Mono<String>` so callers can continue composing asynchronous operations. The HTTP request requires an appropriate HTTP connector, a real endpoint, and a subscriber; in WebFlux, the framework subscribes when a controller returns a matching publisher. This is also an **illustrative class** without a standalone runnable program.

**An MVC application can use `WebClient`** to call other services while the server still runs MVC. Adding `spring-webflux` to get `WebClient` does not automatically switch the server dispatcher to `DispatcherHandler`.

### 4.3. Practical benefits and limitations

WebFlux is valuable when a system handles heavy I/O using **truly non-blocking** libraries, needs streaming, or composes reactive event chains. If a WebFlux controller calls `Thread.sleep(...)`, blocking JDBC, or a synchronous HTTP client directly on the event loop, threads can be held and degrade responsiveness for other requests.

When using blocking code is unavoidable, Reactor provides schedulers like `Schedulers.boundedElastic()` to isolate blocking work off sensitive threads. That is a compatibility measure and **does not turn a blocking driver into a reactive driver**. For systems dominated by synchronous JPA/JDBC, MVC is usually easier to design and operate; WebFlux is not faster by default for every workload.

## 5. `spring-websocket`: bidirectional connections on the Servlet stack

### 5.1. Distinguishing HTTP, WebSocket, and STOMP

Standard HTTP follows a request/response model. WebSocket starts with an HTTP protocol-upgrade handshake and, when successful, maintains a bidirectional connection. Both client and server can proactively send text or binary messages.

- **HTTP/REST:** suited for queries, resource updates, and CRUD.
- **SSE (Server-Sent Events):** suited for the server continuously pushing **one-way** data to the browser.
- **WebSocket:** suited for frequent two-way interaction over a long-lived connection.
- **STOMP:** an application-layer messaging protocol with destinations and commands such as `SEND`/`SUBSCRIBE`; it can run **over WebSocket**, but WebSocket **does not require** STOMP.

`spring-websocket` provides WebSocket APIs for the Servlet stack, such as `WebSocketHandler` and `TextWebSocketHandler`. With Spring messaging, Spring also supports STOMP broker relays, a simple broker, and annotation-based message handling.

### 5.2. Low-level WebSocket handler example

The example below is a **configuration class** for a Servlet/Spring MVC application that already has a server and required dependencies:

```java
package example.socket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(new EchoHandler(), "/ws/echo");
    }

    static class EchoHandler extends TextWebSocketHandler {
        @Override
        protected void handleTextMessage(WebSocketSession session,
                                         TextMessage message) throws Exception {
            session.sendMessage(
                    new TextMessage("echo:" + message.getPayload())
            );
        }
    }
}
```

A JavaScript client in the browser can send a test message:

```javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");
socket.addEventListener("open", () => socket.send("hello"));
socket.addEventListener("message", event => console.log(event.data));
```

If the app runs on port 8080 and the WebSocket handshake succeeds, the received output is `echo:hello`. The example only demonstrates the mechanism; production deployments must handle connection closing, network errors, message limits, Origin checks, authentication, authorization, and session operations. `ws://` suits unencrypted local testing; secured connections use `wss://`.

### 5.3. STOMP and pub/sub

Spring supports STOMP over WebSocket via `spring-websocket` together with `spring-messaging`. Example *simple broker* configuration:

```java
package example.socket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
```

In this setup, `/ws` is the STOMP-over-WebSocket connection endpoint; messages sent to destinations prefixed with `/app` are routed to appropriately defined `@MessageMapping` handlers; the simple broker serves subscriptions on `/topic`. The class above **does not yet include a message controller** and does not generate broadcast messages on its own. The simple broker suits basic scenarios and should not be treated as a replacement for all reliability/persistence/scaling features of a dedicated message broker. When needed, a broker relay can be configured. **SockJS is optional**, not a mandatory requirement for WebSocket or STOMP.

### 5.4. WebSocket in WebFlux is a different API

WebFlux provides reactive WebSocket through `org.springframework.web.reactive.socket.WebSocketHandler` and `org.springframework.web.reactive.socket.WebSocketSession`. These are **types in different packages** from the Servlet stack's `org.springframework.web.socket.WebSocketHandler` and `WebSocketSession`. Therefore, the `TextWebSocketHandler` example above **does not translate verbatim to WebFlux**. For pure WebFlux applications, use WebFlux's reactive WebSocket handlers.

## 6. Choosing modules by requirement

| Requirement | What to choose? | Explanation |
| --- | --- | --- |
| CRUD REST API, JDBC/JPA, mostly synchronous code | `spring-webmvc` | Servlet MVC aligns well with many blocking libraries |
| Streaming/reactive server, heavy non-blocking I/O | `spring-webflux` | Runtime and pipeline support Reactive Streams |
| Synchronous HTTP calls | `spring-web` and `RestClient` | Synchronous client; no web server required |
| Reactive HTTP calls from MVC or WebFlux | `spring-webflux` and `WebClient` | Reactive client independent of server type |
| Bidirectional chat in an MVC app | `spring-websocket` | WebSocket or STOMP handlers on Servlet |
| WebSocket in a WebFlux app | WebSocket API of `spring-webflux` | Reactive handler/session on the same stack |

Modules do not solve an entire system with a single dependency. Security, request validation, persistence, logging, backpressure at other boundaries, session coordination, and deployment must be designed separately.

## 7. Declaring dependencies properly

If using plain Spring Framework with consistently managed artifact versions (such as a BOM), the library coordinates are:

```groovy
dependencies {
    implementation 'org.springframework:spring-web'        // HTTP foundation
    implementation 'org.springframework:spring-webmvc'     // Servlet MVC
    implementation 'org.springframework:spring-webflux'    // WebFlux/WebClient
    implementation 'org.springframework:spring-websocket'  // Servlet WebSocket
}
```

This is an **identification catalog**, not a configuration requiring all four to be installed. Select only the modules you need; higher-level modules may pull in `spring-web` transitively. With plain Framework, the application must set up its own server/runtime, context, appropriate codecs, and supporting configuration. STOMP messaging additionally uses `spring-messaging`.

When using **Spring Boot 3.x**, starters help manage many dependencies and auto-configuration. Three **separate** options:

```groovy
// 1. REST server on Spring MVC:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

```groovy
// 2. REST server on Spring WebFlux:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

```groovy
// 3. MVC + WebSocket/STOMP:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
```

Starter names can change across Spring Boot generations; check documentation for your project's **actual version**. In Boot 3.x, if both MVC and WebFlux starters are present, Boot usually selects **MVC as the web application type**. A common reason to keep both is an MVC server using `WebClient`. Do not conclude the server uses `DispatcherHandler` simply because `spring-webflux` is on the classpath.

For a minimal Spring Boot 3.x application, you can use the following entry point together with the MVC or WebFlux controller shown earlier; this is a separate file in a parent package of `example.mvc` or `example.reactive` so component scanning finds the controller:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

To **run one of the HTTP examples**: create a Spring Boot 3.x project with Java 17+ and a Gradle plugin/BOM matching the Boot version, pick **one web starter** from the first two options, place `Application.java` and `GreetingController.java` in their respective packages, and run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). With the server typically on `localhost:8080`, run:

```bash
curl http://localhost:8080/hello/Lan
```

Expected body (unless altered by other configuration): `{"message":"Hello, Lan"}`. The WebSocket part only runs when choosing an MVC app with the WebSocket dependency and the handler configuration in section 5; standard `curl` is not a WebSocket client.

## 8. Common misconceptions

1. **"`@RestController` means it is Spring MVC."** False: both MVC and WebFlux support annotated controllers. You must inspect the web stack/runtime.
2. **"`spring-web` alone is enough to build a REST server."** False: the foundational module does not mean a web server and dispatcher have been configured.
3. **"WebFlux is always faster than MVC."** False: benefits depend on workload characteristics and how much genuinely non-blocking I/O is involved.
4. **"WebFlux requires Netty."** False: WebFlux has integration mechanisms with Servlet containers that support non-blocking I/O.
5. **"Returning `Mono` makes every task non-blocking."** False: blocking JDBC or `Thread.sleep` still blocks if called inside the pipeline.
6. **"MVC cannot use `WebClient`."** False: MVC can call WebClient from its HTTP client layer.
7. **"Having `spring-websocket` replaces `spring-webmvc`."** False: WebSocket adds a bidirectional connection protocol; it does not replace REST dispatching.
8. **"WebSocket equals STOMP."** False: WebSocket is a bidirectional transport; STOMP provides optional messaging semantics.
9. **"HTTP CORS configuration automatically protects all of WebSocket."** False: you must examine Origin/handshake checks and authentication/authorization for the protocol/stack used.
10. **"Having both MVC and WebFlux dependencies runs both server stacks in parallel."** False: you must check the actual web application type, server, and dispatcher.

## 9. Practice exercises

**Scenario A:** A sales system uses synchronous JPA, JSON CRUD, and occasionally calls a shipping API. A reasonable starting point: **Spring MVC + RestClient**. **WebClient in MVC** can be used if a specific async integration need proves beneficial.

**Scenario B:** A job status board only receives updates from the server. Compare **SSE** and **WebSocket**. If the browser needs to send frequent interactive actions, WebSocket fits better; if only receiving a unidirectional event stream, SSE can be simpler.

**Scenario C:** A WebFlux controller returns `Mono<Order>` but calls blocking JDBC inside `map(...)`. Explain why Mono does not automatically eliminate blocking, which thread risks being occupied, and solutions using a reactive driver or offloading blocking work from the event loop.

**Self-check:**

- How does `DispatcherServlet` differ from `DispatcherHandler`? — The former is the core of MVC/Servlet; the latter is the core of WebFlux/reactive.
- How does `RestClient` differ from `WebClient`? — Synchronous REST client versus reactive/non-blocking HTTP client.
- Does WebFlux always need `spring-websocket` to do WebSocket? — No; WebFlux has its own reactive WebSocket API.

## 10. Further reading from official documentation

- Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Reactive Core and `spring-web` foundations: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Servlet WebSocket API: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
- STOMP: https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html

**Key takeaway:** `spring-web` is the HTTP foundation; `spring-webmvc` implements the Servlet/MVC web server; `spring-webflux` is the reactive web framework and provides WebClient; `spring-websocket` serves WebSocket/STOMP on Servlet, while WebFlux has its own reactive WebSocket API.
