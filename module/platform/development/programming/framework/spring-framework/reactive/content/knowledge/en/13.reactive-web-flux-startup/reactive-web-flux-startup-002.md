# The Roles of spring-web, spring-webflux, and Reactor Netty

## 1. The big picture: three components at three different layers

When you start a Spring WebFlux application, these dependencies usually appear side by side:

- **spring-web**: Spring's common web foundation, providing HTTP abstractions, codec contracts, and many web infrastructure components; it is also the reactive foundation that WebFlux is built on.
- **spring-webflux**: Spring's reactive web framework, which defines how to receive requests, route them to handlers/controllers, read/write bodies, and return data using reactive types such as Mono/Flux.
- **Reactor Netty**: a networking library that integrates Project Reactor with Netty, providing a non-blocking HTTP client/server. Spring Boot usually chooses it as the default embedded server when using WebFlux.

~~~text
                SPRING BOOT APPLICATION
                           |
                           v
               spring-boot-starter-webflux
                           |
              +------------+-------------+
              |                          |
              v                          v
          spring-web                spring-webflux
       HTTP abstraction           Reactive web framework
       codecs / WebHandler        DispatcherHandler / handlers
              |                          |
              +------------+-------------+
                           |
                 HTTP server adapter
                           |
                           v
                    Reactor Netty
                           |
                           v
                     Netty / TCP
                           |
                           v
                       Network
~~~

This is a **conceptual diagram**, not a complete Maven dependency tree. The starter also pulls in underlying libraries and automatic configuration. Remember: **spring-web provides the web foundation and reactive contracts; spring-webflux provides the reactive web processing model; Reactor Netty performs the networking when it is chosen as the runtime**.

The three components are not interchangeable names for the same thing. Confusing the layers easily leads to adding unnecessary dependencies, misconfiguring the server, or thinking that you must use Netty to write a WebFlux controller.

## 2. spring-web: Spring's common web foundation

### 2.1. Artifact and responsibilities

Maven artifact:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-web</artifactId>
</dependency>
~~~

In a Spring Boot application, you usually **do not need to declare it separately** if you already use a suitable starter. Boot's dependency management will put a compatible version on the classpath.

spring-web is the foundation module, containing web abstractions and utilities used by other web frameworks:

- **HTTP abstraction**: request, response, header, status, media type, cookie, URI, and related types.
- **HTTP message conversion and codec contracts**: contracts for reading/writing request/response content and the supported data types.
- **WebHandler infrastructure**: the core abstraction for the non-blocking web processing path that WebFlux uses.
- **Web utilities**: URI, CORS, HTTP caching, multipart, and other common web utilities.
- **Shared annotations and contracts**: annotations such as @RequestMapping, @GetMapping, @RequestBody, @ResponseBody, and types that support controllers.
- **Client-side abstraction**: HTTP client contracts such as ClientHttpRequest, ClientHttpResponse, and ClientHttpConnector.

spring-web is **not a standalone HTTP server**. It provides abstractions and infrastructure; to accept real network connections, the application needs a suitable runtime/server or must be deployed in an existing container.

### 2.2. spring-web is not synonymous with Spring MVC

It is easy to confuse these three artifacts:

| Artifact | Role |
| --- | --- |
| **spring-web** | The common web foundation and shared abstractions |
| **spring-webmvc** | The Spring MVC framework based on the Servlet API |
| **spring-webflux** | Spring's reactive web framework |

spring-web can be used by both Spring MVC and WebFlux. spring-webmvc and spring-webflux, on the other hand, are two different web stacks that can coexist in the Spring ecosystem.

Therefore, seeing @RestController or @GetMapping is not enough to conclude whether the application is running MVC or WebFlux. You need to look at the dependencies, the application type, and the runtime.

## 3. spring-webflux: the framework that handles HTTP using the reactive model

### 3.1. Artifact and functionality

Main artifact:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
</dependency>
~~~

With Spring Boot, the usual approach is to use the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

spring-boot-starter-webflux pulls in the necessary WebFlux components and enables auto-configuration. You do not need to assemble each artifact yourself if the goal is to create a typical Boot application.

Spring WebFlux provides:

1. **Reactive request handling**: handles requests/responses with a non-blocking contract.
2. **DispatcherHandler**: dispatches requests to the appropriate handler.
3. **Annotated controllers**: use @RestController, @GetMapping, @PostMapping, and other familiar annotations.
4. **Functional endpoints**: the RouterFunction/HandlerFunction model, declaring routes and handler functions in a functional style.
5. **Reactive codecs**: read/write JSON, text, byte streams, and other content types as streams.
6. **WebClient**: a reactive HTTP client with a fluent API, returning Mono/Flux and supporting streaming.
7. **WebFilter and exception handling**: request filtering, error handling, CORS, and other web infrastructure.
8. **Reactive Streams integration**: coordinates demand/backpressure at the Publisher/Subscriber boundaries that support it.

### 3.2. Two programming styles

An **annotated controller** is close to Spring MVC:

~~~java
@RestController
class GreetingController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
~~~

A **functional endpoint** declares the route and handler explicitly:

~~~java
@Bean
RouterFunction<ServerResponse> routes(GreetingHandler handler) {
    return RouterFunctions.route()
            .GET("/hello", handler::hello)
            .build();
}
~~~

These are illustrative snippets that must be placed in a WebFlux application with beans and imports already configured. Both styles belong to spring-webflux; the choice depends on how the code is organized and on the project's needs.

### 3.3. Mono and Flux in controllers

A WebFlux controller usually returns:

- **Mono<T>** when there is at most one result or one response.
- **Flux<T>** when there are 0 to many elements, which may be emitted gradually over time.

~~~java
@GetMapping("/profile")
Mono<Profile> profile() {
    return profileService.findProfile();
}

@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Event> events() {
    return eventService.streamEvents();
}
~~~

This is an illustrative snippet with Profile, Event, and services provided by the application. WebFlux does not require the controller to call subscribe() or block() itself to get the result. The framework coordinates the subscription and writes the response according to the HTTP lifecycle. Calling block() on the event loop can stall many other requests.

## 4. Reactor Netty: the non-blocking networking layer

### 4.1. Netty, Reactor Core, and Reactor Netty

**Netty** is an asynchronous, event-driven networking framework used to build network clients/servers.

**Project Reactor Core** provides the reactive model with Mono, Flux, Scheduler, and operators.

**Reactor Netty** combines these two foundations: it provides non-blocking networking that integrates directly with Reactor types. It supports HTTP and other network protocols, and fits the event loop and stream-based data processing.

Common artifact:

~~~xml
<dependency>
    <groupId>io.projectreactor.netty</groupId>
    <artifactId>reactor-netty-http</artifactId>
</dependency>
~~~

In Spring Boot, the corresponding starter is usually spring-boot-starter-reactor-netty. When using the default WebFlux starter, Boot usually brings in Reactor Netty to provide the embedded HTTP server.

### 4.2. What does Reactor Netty do?

When chosen as the server runtime, Reactor Netty takes care of the network part:

- Opens ports and accepts TCP connections.
- Manages sockets, event loops, and non-blocking I/O.
- Handles the HTTP protocol at the transport/server layer.
- Converts network requests/responses into the abstractions that Spring WebFlux works with.
- Writes response data back to the socket; supports streaming and coordinates with reactive demand at the relevant layers.

Reactor Netty **does not decide which controller is called or which business logic runs**. Routing and request handling belong to Spring WebFlux. Netty also does not replace Reactor Core: Mono/Flux are Reactor Core types, while Reactor Netty is the networking integration with Reactor.

### 4.3. Reactor Netty can also act as an HTTP client

Not only as a server, Reactor Netty can also be a connector for WebClient:

~~~text
Service application
      |
      v
   WebClient
      |
      v
ClientHttpConnector
      |
      v
Reactor Netty HttpClient
      |
      v
Netty / Socket / TLS
      |
      v
Remote HTTP service
~~~

WebClient is the client API at the Spring layer. Reactor Netty can be the implementation that performs the underlying network I/O. WebClient also supports other HTTP client implementations, depending on the version and the configured dependencies.

## 5. Which components does an HTTP request pass through?

Suppose a client sends:

~~~http
GET /hello HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

The processing flow at a conceptual level:

1. **Reactor Netty** receives the connection and HTTP data from the socket.
2. An adapter brings the request into the Spring WebFlux abstractions.
3. **spring-web / WebFlux infrastructure** provides the HTTP request/response, filters, and codec contracts.
4. **DispatcherHandler** finds the handler through HandlerMapping.
5. The controller or functional handler performs the business logic and returns a **Mono/Flux**.
6. Spring's codecs convert the object into JSON, text, or a suitable stream.
7. The runtime server writes the response to the socket; for a Flux stream, data can be emitted piece by piece following the Publisher lifecycle.

~~~text
TCP socket
    |
    v
Reactor Netty
    |
    v
Spring HTTP adapter / HttpHandler
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--> HandlerMapping
    |
    +--> HandlerAdapter / Controller
    |           |
    |           v
    |        Mono / Flux
    |
    v
HttpMessageWriter / Codec
    |
    v
Reactor Netty response
    |
    v
TCP socket
~~~

The diagram omits many components such as security, observation, error handling, multipart, and resource management. The goal is to distinguish the **network layer**, the **HTTP infrastructure**, and the **request processing model**.

## 6. Why does WebFlux usually go together with Reactor Netty?

Spring WebFlux needs a server runtime to receive and send HTTP. Reactor Netty is a common default choice in Spring Boot because it:

- Provides non-blocking I/O and an event loop that fit the reactive model.
- Integrates with Reactor Core and WebClient.
- Has both client and server implementations.
- Can share some network resources between client and server when both use Reactor Netty and the default Boot configuration.
- Supports streaming and modern HTTP protocols.

However, **WebFlux is not locked into Reactor Netty**. The framework supports multiple runtimes, including Servlet-based servers such as Tomcat/Jetty and other options depending on the Spring Boot version. When running WebFlux on a Servlet container, WebFlux still keeps its reactive/non-blocking contract; an adapter connects the framework to the container's API.

There are two independent decisions:

- **Choose the programming model:** Spring MVC or Spring WebFlux?
- **Choose the server runtime:** Tomcat, Jetty, Reactor Netty, or another supported runtime?

Do not conclude that "using Netty means you must use WebFlux" or "using Tomcat means only MVC".

## 7. Spring MVC, WebFlux, and the case where you only need WebClient

### 7.1. Comparing the two web stacks

| Criterion | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Main artifact | spring-webmvc | spring-webflux |
| Web foundation | Servlet API | Reactive HTTP handling; runs on Netty or a Servlet runtime |
| Return type | Usually object/ResponseEntity; also supports async/reactive types | Mono/Flux are the natural types |
| I/O | The MVC model is usually blocking per request thread | Non-blocking end-to-end when all layers support it |
| Streaming | Supports streaming/async | Streaming is a core part of the reactive model |
| Use case | Traditional CRUD, blocking libraries | Lots of concurrent I/O, streaming, reactive pipelines |

**MVC is not an outdated framework.** If the application uses blocking JDBC, synchronous libraries, and moderate load, Spring MVC can be simpler and easier to operate. WebFlux is useful when you need lots of concurrent I/O, streaming, or a non-blocking ecosystem throughout.

### 7.2. Needing only WebClient does not mean you must switch the server to WebFlux

A Spring MVC application can still use **WebClient** to call other services reactively. This is a common reason why a WebFlux dependency appears in an MVC application.

With Spring Boot 3.x, if the classpath has both **spring-boot-starter-web** and **spring-boot-starter-webflux**, Boot usually auto-configures **Spring MVC** as the default application type. You can still use WebClient in that application.

If you want the server to run WebFlux when both starters are present, you can specify the application type:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

This is an illustrative configuration snippet. For a typical project, it is best to add only the starter of the chosen web stack so that the dependency tree is easy to understand.

## 8. Configuring dependencies in Spring Boot

### 8.1. WebFlux starter

Maven example with Spring Boot **3.5.5** and Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-stack-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

With the starter above, Boot manages compatible versions and automatically configures WebFlux along with the default server runtime, Reactor Netty. **You do not need to declare spring-web, spring-webflux, reactor-core, and reactor-netty-http one by one** in a typical Boot application.

The example pins version **3.5.5** for reproducibility. A new project should use a Spring Boot release approved by your organization and update it according to the dependency policy; do not arbitrarily mix versions of Spring Framework, Reactor, and Netty.

### 8.2. Viewing the actual dependencies

Run:

~~~bash
mvn dependency:tree
~~~

Or filter the artifacts you care about:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-web,org.springframework:spring-webflux,org.springframework:spring-webmvc,io.projectreactor.netty:reactor-netty-http
~~~

When reading the result:

- **spring-web** is the web foundation.
- **spring-webflux** is the reactive web stack.
- **spring-webmvc** appears if the application pulls in the MVC starter or another dependency.
- **reactor-netty-http** is the HTTP implementation of Reactor Netty.
- A dependency being present does not by itself prove that it is the server runtime; you need to look at the auto-configuration and the application type.

### 8.3. Changing the server runtime

If you want to run WebFlux on Jetty/Tomcat instead of Reactor Netty, change the server dependency following the Spring Boot guide for the exact version, remove the corresponding default starter, and add a supported server starter.

**Do not mechanically remove every dependency with the word Netty in it.** WebClient may also need an HTTP connector; if you remove Reactor Netty from the classpath, you must ensure the client has another implementation configured. Spring Boot has its own server starters and chooses the connector according to the dependencies present.

## 9. A Spring Boot WebFlux program that runs on Java 17+

The example creates two endpoints:

- **GET /hello**: returns JSON via Mono.
- **GET /ticks**: emits three Server-Sent Events via Flux.

Structure:

~~~text
webflux-stack-demo/
├── pom.xml
└── src/main/java/example/demo/
    ├── DemoApplication.java
    └── GreetingController.java
~~~

Use the pom.xml from section 8.1.

File **src/main/java/example/demo/DemoApplication.java**:

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

File **src/main/java/example/demo/GreetingController.java**:

~~~java
package example.demo;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "Hello from WebFlux"));
    }

    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(1)).take(3);
    }
}
~~~

Run in the directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Call the JSON endpoint:

~~~bash
curl -s http://localhost:8080/hello
~~~

JSON body:

~~~json
{"message":"Hello from WebFlux"}
~~~

Call the streaming endpoint:

~~~bash
curl -N http://localhost:8080/ticks
~~~

The SSE data is emitted one after another:

~~~text
data:0

data:1

data:2

~~~

The emission interval is approximately one second; the response ends after three elements.

### 9.1. Which component does what?

- **DemoApplication** starts Spring Boot and enables auto-configuration.
- **spring-web** provides the HTTP/controller abstractions and shared infrastructure.
- **spring-webflux** detects @RestController, routes requests, and manages Mono/Flux responses.
- **Reactor Core** provides Mono.just and Flux.interval/take.
- **Reactor Netty** by default accepts HTTP connections on port 8080 and sends responses out to the network in this Boot configuration.
- **Spring's codecs** convert the Map to JSON; for /ticks, WebFlux writes the elements in the SSE format.

The controller does not subscribe() or block() by itself. The framework manages the subscription according to the request lifecycle.

## 10. WebClient: distinguishing the client API from the networking implementation

A service can use WebClient:

~~~java
@Service
public class CatalogClient {
    private final WebClient client;

    public CatalogClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example")
                .build();
    }

    public Mono<Item> findItem(String id) {
        return client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
~~~

This is an illustrative service snippet that needs an Item class and Spring dependency injection. **WebClient** is a Spring API: it describes the request, headers, body, decoding, and the reactive result. It needs a **ClientHttpConnector** to perform network I/O. Reactor Netty is a common connector, but you can choose another implementation.

| Component | Role |
| --- | --- |
| WebClient | A fluent API for applications making HTTP calls |
| ExchangeFilterFunction | Client-side request/response filter |
| ClientHttpConnector | The bridge to the HTTP client implementation |
| Reactor Netty HttpClient | Performs HTTP I/O using Reactor Netty |
| Mono/Flux | Represent asynchronous results and streams |

If you use the auto-configured WebClient.Builder and Reactor Netty for both server and client, some network resources/event loops may be shared by default. If you replace the connector or create your own client, you need to manage the resource lifecycle and shutdown appropriately.

## 11. The event loop and why you must not block

Reactor Netty usually uses an **event loop** model with a relatively small number of threads compared with the number of connections it can coordinate. One event-loop thread can serve many connections. This is efficient when callbacks are processed quickly and the I/O is truly non-blocking.

If you put blocking JDBC, Thread.sleep(), Future.get(), CompletableFuture.join(), or Mono.block() on the event loop:

1. The thread is held up while waiting.
2. Other connections served by that event loop may slow down.
3. Queues and latency increase.
4. Throughput drops, and timeouts and cascading failures may appear.

For blocking libraries that you must use, isolate them sensibly:

~~~java
Mono<Result> result = Mono.fromCallable(() -> blockingRepository.find(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is an illustrative snippet with blockingRepository and Result. boundedElastic moves the blocking source to a more suitable Scheduler; it does not turn JDBC into non-blocking. Prefer a reactive driver/API if you want to keep the pipeline non-blocking throughout.

## 12. At which layer do backpressure and streaming occur?

**Reactive Streams backpressure** is the demand mechanism between a Publisher and a Subscriber. WebFlux and Reactor can coordinate demand so that downstream is not forced to receive data faster than it can consume it, at the boundaries that support it.

Distinguish between:

- **Mono/Flux** define the reactive signals at the application layer.
- **WebFlux** turns a Publisher into an HTTP response/body stream and coordinates the codecs.
- **Reactor Netty/Netty** carry data through sockets, buffers, and transport flow control.
- **TCP flow control** is not completely equivalent to request(n) in Reactive Streams.
- An external source that does not support pause/replay may still emit quickly; you need a buffer/overflow policy at a suitable adapter.

Do not assume that just because the application returns a Flux, every external source slows down by itself or memory is always bounded.

## 13. Common configuration mistakes and misunderstandings

| Misunderstanding / mistake | Consequence | Correct understanding |
| --- | --- | --- |
| Thinking spring-web is Spring MVC | Choosing the wrong dependency | spring-web is the common foundation; MVC is spring-webmvc |
| Thinking spring-webflux is Netty | Believing WebFlux only runs on Netty | WebFlux is a framework that supports multiple runtimes |
| Thinking Reactor Netty is where you write controllers | Mixing network code with business routing | Controllers/handlers belong to Spring WebFlux |
| Thinking Mono/Flux come from Reactor Netty | Confusing the libraries | Mono/Flux belong to Reactor Core |
| Adding spring-webflux and thinking Boot configures everything automatically | May lack an embedded server/convenient auto-configuration | Use spring-boot-starter-webflux for Boot applications |
| Adding both MVC and WebFlux starters without knowing the auto-config | Boot may choose MVC by default | Check the dependency tree and the application type |
| Thinking WebClient requires Reactor Netty | Locking the client into an unnecessary implementation | WebClient uses ClientHttpConnector and has many connectors |
| Calling block() on the event loop | Stalls many requests | Return Mono/Flux and avoid blocking |
| Using blocking JDBC inside map() | Blocks the reactive thread | Use a reactive driver or isolate the blocking call |
| Creating a Netty client/pool for each request | Creates many pools/threads, hard to manage | Reuse the client/resources across the application lifecycle |
| Believing WebFlux is always faster than MVC | Choosing a stack by name | Benchmark by concurrency, I/O, CPU, and dependencies |
| Thinking TCP flow control guarantees lossless business events | Events may be lost at the source/adapter | Distinguish transport, Reactive Streams, and delivery semantics |

## 14. How to choose a stack for a project

| Need | Usually suitable choice |
| --- | --- |
| Traditional CRUD, JDBC, and many blocking libraries | Spring MVC + Servlet server |
| Many concurrent connections, non-blocking APIs throughout | Spring WebFlux + a reactive runtime such as Reactor Netty |
| Streaming/SSE/WebSocket and continuously emitted data | WebFlux, choose the server/client runtime according to requirements |
| Only need asynchronous HTTP calls inside an MVC application | Can use WebClient without switching the whole server |
| Want to use Netty for the server but keep Spring handlers | WebFlux + Reactor Netty |
| Want WebFlux on existing Servlet infrastructure | WebFlux + a supported Servlet container |
| Depending on a blocking driver that cannot yet be replaced | MVC may be simpler; if using WebFlux you need to isolate blocking and measure the load |

The decision should be based on **the nature of the I/O, the number of concurrent connections, the database driver, the HTTP client, the streaming model, operational capability, and performance measurements**. Do not switch to WebFlux just to use Mono/Flux if the whole system is still blocking and there is no clear need.

## 15. Checklist for debugging dependencies and runtime

1. **Which starters are declared?** spring-boot-starter-web, spring-boot-starter-webflux, or both?
2. **What is the actual dependency tree?** Is there an unexpected spring-webmvc? Is there a server starter pulling something in?
3. **Which application type did Boot choose?** SERVLET or REACTIVE?
4. **Which server factory was auto-configured?** NettyReactiveWebServerFactory, TomcatReactiveWebServerFactory, or JettyReactiveWebServerFactory?
5. **Which WebClient connector was chosen?** Reactor Netty, JDK, Jetty, or a custom connector?
6. **Are there unnecessary multiple ConnectionProviders/EventLoopGroups?** Check the lifecycle and resource sharing.
7. **Is anything blocking on the event loop?** Check thread names, stack traces, and block detection.
8. **Does the controller return a Publisher?** Does it subscribe()/block() by itself or detach the work from the HTTP request?
9. **Does the codec support the media type/body?** Check JSON, SSE, multipart, and data types.
10. **Are the Spring/Reactor/Netty versions managed in sync?** Use Spring Boot's dependency management instead of overriding arbitrarily.

## 16. Key takeaways

- **spring-web** is the common web foundation, providing the HTTP abstractions and infrastructure that MVC/WebFlux use.
- **spring-webflux** is the reactive web framework: request routing, controllers/functional endpoints, codecs, WebClient, and Mono/Flux integration.
- **Reactor Netty** is the non-blocking networking runtime/client-server that integrates Netty with Reactor; Spring Boot usually chooses it as the default server for WebFlux.
- **Reactor Core** provides Mono/Flux and operators.
- WebFlux can run on many server runtimes; Reactor Netty is common but not mandatory.
- MVC can use WebClient; having a WebFlux dependency does not by itself prove the server is running WebFlux.
- To benefit from non-blocking, you need to keep I/O non-blocking throughout and avoid blocking the event loop.

**Official documentation:**
- [Spring Framework — WebFlux Overview and server support](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — Spring WebFlux reference](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Boot — Reactive Web Applications and auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Embedded Web Servers and replacing Reactor Netty](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — WebClient and supported HTTP clients](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Reactor Netty — Project overview](https://spring.io/projects/reactor-netty)
