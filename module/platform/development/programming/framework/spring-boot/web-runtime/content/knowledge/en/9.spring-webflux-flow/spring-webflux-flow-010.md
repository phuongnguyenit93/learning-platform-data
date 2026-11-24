# Support Boundaries for WebFlux on Servlet Servers vs. Reactor Netty

## 1. Why Understanding Support Boundaries Matters

Spring WebFlux is Spring's reactive web framework. It supports asynchronous programming, non-blocking I/O, and Reactive Streams, yet **WebFlux is not synonymous with Reactor Netty**. WebFlux can handle HTTP on Reactor Netty or on supported Servlet servers with non-blocking I/O capabilities. What stays common is the WebFlux application programming model; what differs is how adapters wire the framework to sockets, Servlet containers, and server lifecycles.

Common misconceptions include assuming Tomcat always means Spring MVC, assuming WebFlux requires Netty, assuming running WebFlux on Tomcat lets you use any Servlet `Filter` directly, and assuming swapping starters turns a synchronous MVC application into a fully reactive system.

This lesson explains those boundaries from four angles: **programming model**, **HTTP adapters**, **concurrency/I/O model**, and **deployment support across Spring Boot versions**. Hands-on examples use Java 17+ and Spring Boot 3.3.x for consistent dependencies and APIs. For Spring Boot 4.x, check that branch's documentation because supported servers, Servlet baselines, and starters have changed.

Expected outcomes:

- Describe how WebFlux on Reactor Netty differs from WebFlux on Tomcat/Jetty.
- Explain `HttpHandler`, `WebHandler`, `ServerWebExchange`, `DispatcherHandler`, and HTTP adapters.
- Distinguish WebFlux-on-Servlet from Spring MVC-on-Servlet.
- Understand limitations around Servlet APIs, Servlet Filters, WAR deployment, `WebFilter`, and `SecurityWebFilterChain` in WebFlux apps.
- Choose, switch, and verify embedded servers via dependencies, `ApplicationContext`, and live HTTP tests.
- Avoid blocking the event loop and avoid claiming end-to-end backpressure when downstream remains blocking.
- Know the mandatory tests before switching servers in production.

## 2. Three Concepts to Keep Separate

The **web framework** defines controllers/routers and the request-handling pipeline. The **HTTP runtime** accepts connections and transfers bytes over the network. The **deployment model** determines what creates and manages the process, server, and artifact.

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Programming model | Servlet web stack | Reactive web stack |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| Common request APIs | `HttpServletRequest`, `ServletRequest`, `ModelAndView` | `ServerHttpRequest`, `ServerWebExchange`, `Mono`, `Flux` |
| Framework filters | Servlet `Filter`, `HandlerInterceptor` | `WebFilter`, `WebFilterChain` |
| Web security config | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Return types | DTO, `ResponseEntity`, optional async support | `Mono`, `Flux`, `Publisher`, supported DTOs |
| Typical servers | Tomcat/Jetty | Reactor Netty; also Tomcat/Jetty via adapter |
| Blocking assumptions | Synchronous APIs allowed on container threads | Event loops must be protected from blocking |

Both frameworks can use `@RestController`, `@GetMapping`, and JSON, so **looking at annotations alone is not enough to identify the stack**. Always check starters, web application type, the actual initialized context, and the runtime handler.

Tomcat itself can serve two roles:

1. A Servlet container for Spring MVC, directly managing Servlets, Filters, and `DispatcherServlet`.
2. An HTTP server for Spring WebFlux, using Servlet non-blocking I/O through an internal bridge. Requests still flow through the WebFlux pipeline rather than becoming Spring MVC.

Conversely, Reactor Netty is not a Servlet container you can drop in to replace Tomcat for an arbitrary MVC app via a single dependency.

## 3. Shared Foundation of WebFlux: HttpHandler and WebHandler

Spring WebFlux builds an HTTP layer independent of server-specific APIs. At the low level, `org.springframework.http.server.reactive.HttpHandler` processes `ServerHttpRequest` and `ServerHttpResponse` reactively. Conceptual contract:

~~~java
Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response);
~~~

This is an illustrative API signature, not a standalone Java program. `Mono<Void>` describes asynchronous response processing. Completing a `Publisher` does not mean the framework creates one new thread per request.

One level up, `WebHandler` handles `ServerWebExchange`, which wraps request, response, attributes, session, and web-level context. `WebHttpHandlerBuilder` and `HttpWebHandlerAdapter` connect WebFlux components such as `WebFilter`s, exception handlers, and `WebHandler` into an `HttpHandler`.

In `@RestController` applications, `DispatcherHandler` handles WebFlux handler selection, parameter binding, and controller invocation. For functional endpoints, `RouterFunction` and `HandlerFunction` declare routes differently while running on the same reactive infrastructure.

Thanks to the `HttpHandler` contract, WebFlux can integrate with multiple servers without rewriting controllers when switching runtimes—provided required server features are supported and tested.

## 4. WebFlux on Reactor Netty

Reactor Netty builds on Netty and integrates Project Reactor. In the standard Spring Boot WebFlux setup, `spring-boot-starter-webflux` pulls in `spring-boot-starter-reactor-netty`, and Boot selects embedded Reactor Netty as the HTTP server.

High-level flow:

~~~text
Client TCP/HTTP
    |
    v
Netty channel pipeline / event loop
    |
    v
Reactor Netty HttpServer
    |
    v
ReactorHttpHandlerAdapter
    |
    v
Spring HttpHandler
    |
    v
WebFilter / WebHandler / DispatcherHandler
    |
    v
Controller -> Mono/Flux -> HTTP response
~~~

`ReactorHttpHandlerAdapter` bridges Reactor Netty's callbacks/APIs with Spring's `HttpHandler`. It does not require `jakarta.servlet.http.HttpServletRequest` or a Servlet container to receive requests.

Key advantages:

- Event-driven, non-blocking network I/O is the server's native design.
- Integrates cleanly with reactive chains using `WebClient`, R2DBC, and other non-blocking libraries.
- Reactor Netty provides both HTTP client and server, able to share event-loop resources in matching default configurations.
- Streaming and async work can run with relatively few threads on I/O-wait-heavy workloads.

Practical boundaries:

- Spring WebFlux still needs an application context, codecs, security, timeouts, and resource management.
- Event loops must not be stalled by synchronous JDBC, `Thread.sleep`, slow blocking file APIs, or `WebClient.block()`.
- Reactive does not guarantee lower single-request latency than MVC. Benefits mainly appear in scalability and resource efficiency under concurrent I/O waits.
- CPU-heavy tasks still consume processing time; cap concurrency and use appropriate schedulers/workers.

## 5. WebFlux on Tomcat or Jetty: The Servlet Bridge

Tomcat and Jetty are Servlet containers, yet since Servlet API 3.1 they support **asynchronous processing** and **non-blocking I/O**. WebFlux leverages those capabilities through an adapter layer instead of exposing Servlet APIs in business code.

High-level flow:

~~~text
Client TCP/HTTP
    |
    v
Tomcat / Jetty connector
    |
    v
Servlet container + Servlet non-blocking I/O
    |
    v
ServletHttpHandlerAdapter
    |
    v
Spring HttpHandler
    |
    v
WebFilter / WebHandler / DispatcherHandler
    |
    v
Controller -> Mono/Flux -> HTTP response
~~~

`ServletHttpHandlerAdapter` sits at the boundary between the Servlet API and Spring's `HttpHandler` contract. It translates Servlet non-blocking I/O request/response signals into reactive streams handled by WebFlux.

**Crucial point:** having Servlet APIs underneath does not make Servlet APIs the primary programming model for WebFlux. Inside a WebFlux handler, applications should stick to `ServerWebExchange`, `ServerHttpRequest`, `ServerHttpResponse`, `Mono`/`Flux`, `WebFilter`, and reactive components.

Spring Framework documentation advises against mapping Servlet Filters or touching Servlet APIs directly inside a WebFlux application. Mixing blocking and non-blocking I/O branches without understanding the bridge can trigger runtime issues, erase concurrency gains, or cause unexpected behavior.

### 5.1. Why Can Tomcat/Jetty Run Both MVC and WebFlux?

Tomcat and Jetty provide networking and non-blocking capabilities, while the Servlet API supports both traditional synchronous calls and non-blocking APIs. Spring MVC uses the Servlet frontend; Spring WebFlux uses a Servlet non-blocking I/O adapter that forwards requests into the reactive pipeline.

It is **Spring's processing layer** that defines framework semantics. Using Tomcat as the HTTP server does not prove `DispatcherServlet` handles requests. You can run WebFlux on Tomcat without creating any `DispatcherServlet` for reactive routes.

### 5.2. Can Servlet Filters Run?

Technically, the container has a Servlet chain and low-level infrastructure may exist there. However, when writing a WebFlux app, **do not build business middleware on Servlet Filters, `HttpServletRequest`, or `ThreadLocal` request state**. Standard WebFlux extension points are `WebFilter`, `WebExceptionHandler`, and reactive APIs.

Features like correlation IDs, request logging, authentication, authorization, rate limiting, and request mutation should align with the reactive lifecycle. For example, a legacy custom Servlet Filter relying on `ThreadLocal` can break when execution switches threads or when request/response completes asynchronously.

### 5.3. Why This Differs From Traditional WAR Deployment

These are two frequently confused concepts:

- The WebFlux framework provides an **adapter** to run on compatible Servlet containers.
- Packaging and deploying a **Spring Boot WebFlux application as a WAR** into an external container is not supported by Boot in the same way traditional Spring MVC is.

Spring Boot WebFlux apps typically package as executable JARs and Boot launches the embedded server. Spring Boot docs explicitly note that traditional WAR deployment is unsupported for WebFlux. Do not assume that just because WebFlux can run on embedded Tomcat, a Spring Boot WebFlux WAR deploys like any MVC app.

If an organization mandates an external Servlet container, evaluate deployment models and version support very carefully; the straightforward path with Boot WebFlux is a Boot-managed embedded server.

## 6. Support Matrix by Version and Server

Choices must be tied to the specific Spring Boot branch:

| Server | Spring MVC on Servlet | WebFlux in Boot 3.x | WebFlux in Boot 4.0 | WebFlux mechanism |
| --- | --- | --- | --- | --- |
| Tomcat | Yes | Yes | Yes | Servlet non-blocking I/O + adapter |
| Jetty | Yes | Yes | Yes | Servlet non-blocking I/O + adapter |
| Reactor Netty | Not a Servlet container for MVC | Yes; WebFlux default | Yes; WebFlux default | Reactor Netty API + adapter |
| Undertow | Yes in Boot 3.x | Yes in Boot 3.x | **No longer integrated as embedded Undertow** | Spring Framework 6.x uses Undertow API directly |

**Undertow note:** Spring Boot 3.3 documentation lists Undertow for both reactive and Servlet servers. For WebFlux, Spring Framework 6.x uses Undertow's API directly rather than going through Tomcat/Jetty's `ServletHttpHandlerAdapter`. Spring Boot 4.0 requires Servlet 6.1 as its baseline and removed embedded Undertow starters/support. Do not copy Undertow dependencies from Boot 3.x into Boot 4.x expecting auto-configuration to keep working.

This table describes support in the listed branches; it does not guarantee every version/JDK/HTTP feature combination behaves identically. Before upgrading, verify release notes and managed dependencies for your target Spring Boot version.

## 7. Distinguishing WebFlux From Spring MVC When Both Use Annotations

Two code snippets can look nearly identical:

~~~java
@RestController
class SampleController {
    @GetMapping("/api/hello")
    public Mono<String> hello() {
        return Mono.just("Hello");
    }
}
~~~

This snippet illustrates a controller method. Returning `Mono` does not by itself prove the active framework is WebFlux, because Spring MVC also supports some async/reactive return types. Identify the web stack by checking dependencies, web application type, and the `ApplicationContext`.

In standard Spring Boot:

- `spring-boot-starter-web` selects Servlet MVC and defaults to embedded Tomcat.
- `spring-boot-starter-webflux` selects reactive WebFlux and defaults to embedded Reactor Netty.
- If **both** starters are on the classpath, Spring Boot defaults to MVC. This setup can make sense when an MVC controller uses `WebClient`.
- You can set `spring.main.web-application-type=reactive` intentionally, though you should check for auto-configuration and dependency conflicts. Keeping a clean classpath for the intended web stack is better.

More reliable checks than looking at annotations: inspect the `ApplicationContext` class, startup logs, dependency tree, server factory bean, and route behavior in tests. Do not rely solely on thread names or seeing `reactor-netty-client` on the classpath to conclude which server is running.

## 8. WebFilter, DispatcherHandler, and Reactive Components

A WebFlux request normally follows this pipeline:

1. The server accepts bytes and parses HTTP.
2. The adapter builds `ServerHttpRequest` and `ServerHttpResponse` representing the reactive request/response.
3. `HttpHandler` delegates to the `WebHandler` chain.
4. `WebFilterChain` applies registered `WebFilter`s.
5. `DispatcherHandler` locates a handler via `HandlerMapping`.
6. `HandlerAdapter` invokes the controller or functional handler.
7. Codecs read/write request and response bodies via publishers.
8. Results are subscribed/processed along the request lifecycle and emitted to the network adapter.

Spring MVC uses `DispatcherServlet`, Servlet Filters, and Servlet APIs. WebFlux uses `DispatcherHandler`, `WebFilter`, and `ServerWebExchange`. The names echo each other, yet the objects and callbacks are not interchangeable.

Illustrative `WebFilter` adding a response header:

~~~java
@Component
class ApiHeaderFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getResponse()
                .getHeaders()
                .add("X-API-Stack", "WebFlux");
        return chain.filter(exchange);
    }
}
~~~

This snippet illustrates code inside a WebFlux application; import `Component`, `WebFilter`, `ServerWebExchange`, `WebFilterChain`, and `Mono`. The filter works for WebFlux running on Reactor Netty **and** on the Tomcat/Jetty Servlet bridge—without touching `HttpServletRequest`.

Never build authentication logic out of an arbitrary custom header as in an illustrative filter. For security, use reactive Spring Security with explicit access-control rules.

## 9. Thread Model: The Biggest Programming Boundary

### 9.1. Reactor Netty

Reactor Netty organizes event loops to receive and dispatch I/O events. Handlers may execute directly on those event-loop threads. A long blocking call holds the thread and slows down other requests sharing the same loop.

**Wrong** example:

~~~java
@GetMapping("/slow")
Mono<String> slow() {
    Thread.sleep(3000); // does not compile without handling InterruptedException
    return Mono.just("done");
}
~~~

This snippet illustrates an anti-pattern, not runnable code. Even if you handle the checked exception, sleeping 3 seconds inside a request handler ties up the processing thread. Do not put code like this in a real WebFlux app.

Another common anti-pattern:

~~~java
String body = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

`.block()` forces a reactive operation into synchronous waiting. In WebFlux request flows—especially on non-blocking threads—this can throw `IllegalStateException` or exhaust resources depending on the thread and runtime context.

### 9.2. Tomcat/Jetty Servlet Bridge

Tomcat and Jetty maintain their own pools/threads and scheduling for Servlet requests and non-blocking I/O. Running WebFlux on a Servlet container **does not mean code can block freely**. WebFlux execution still aims to be non-blocking. Blocking in handlers can exhaust threads, increase latency, or trigger adapter-specific failures.

Do not copy thread-pool numbers from Tomcat MVC directly to Reactor Netty or vice versa. Tune concurrency using metrics and workloads from the active server.

### 9.3. Escape Hatch for Unavoidable Blocking Libraries

When forced to invoke a synchronous API, isolate the work on `boundedElastic`:

~~~java
Mono<String> result = Mono.fromCallable(
        () -> blockingRepository.loadValue())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is an illustrative snippet; `blockingRepository` must be a real dependency, and `Mono` and `Schedulers` must be imported. `boundedElastic` is a **bounded** scheduler, not an unlimited resource. It prevents synchronous APIs from holding event loops, yet does not convert the dependency to non-blocking or guarantee cancelling an active blocking call.

If most of the application relies on JDBC and synchronous libraries, Spring MVC may be a simpler fit. If you want end-to-end reactivity, evaluate non-blocking drivers/clients and cap concurrency properly.

## 10. Backpressure: Where It Applies and Where It Stops

Reactive Streams defines demand-based item flow between `Publisher` and `Subscriber`; in Reactor, `Mono`/`Flux` carry these semantics. WebFlux can process streams according to demand and connect them to non-blocking I/O.

However, **backpressure does not propagate transparently across every layer**:

- With Reactor Netty, the adapter translates data into Reactive Streams; actual behavior still depends on network buffering, TCP flow control, and Netty configuration.
- With Tomcat/Jetty, the Servlet adapter must bridge non-blocking `ReadListener`/`WriteListener` with `Publisher`; bridging has overhead and specific buffering boundaries.
- If a service loads all database rows into a `List` before returning a `Flux`, upstream already buffered everything in memory with no per-record backpressure.
- If a publisher emits faster than the client or network can consume, verify buffer limits and cancellation handling.
- A reverse proxy or ingress may buffer the entire response before forwarding to the client; server-side streaming does not prove end-to-end streaming through every proxy.

Measure memory, queued data, response latency, connections, and cancellation when building SSE, streaming uploads/downloads, or long-lived responses. Never treat `Flux` as a "zero memory cost" badge.

## 11. Creating a WebFlux Project Using Default Reactor Netty

Full example for **Spring Boot 3.3.x, Java 17+**. Prerequisites: JDK 17+, compatible Gradle Wrapper, and Maven Central access. This example omits `spring-boot-starter-web` so MVC is not chosen by mistake.

Project structure:

~~~text
webflux-server-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          reactive/
            WebFluxServerApplication.java
            GreetingController.java
      resources/
        application.yml
    test/
      java/
        example/
          reactive/
            GreetingControllerTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'webflux-server-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: webflux-server-demo

server:
  port: 8080
~~~

File `src/main/java/example/reactive/WebFluxServerApplication.java`:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxServerApplication.class, args);
    }
}
~~~

File `src/main/java/example/reactive/GreetingController.java`:

~~~java
package example.reactive;

import java.time.Duration;
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/hello")
    public Mono<Map<String, String>> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just(Map.of("message", "Hello, " + name));
    }

    @GetMapping(
            value = "/api/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder()
                        .data("tick-" + index)
                        .build());
    }
}
~~~

This is a complete example Java application splitting the public main class and controller into two files. `hello` returns a `Mono` carrying a JSON DTO as a `Map`. `ticks` emits up to three Server-Sent Events containing `tick-0`, `tick-1`, and `tick-2`. `Flux.interval` schedules events via Reactor without blocking an event loop between emissions.

### 11.1. Running the Demo

On Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the server binds port 8080, call:

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Expected status is HTTP 200 and JSON body containing:

~~~json
{"message":"Hello, Lan"}
~~~

Test SSE:

~~~bash
curl -N "http://localhost:8080/api/ticks"
~~~

Roughly one second apart, the client receives events with data `tick-0`, `tick-1`, and `tick-2`, and then the stream finishes. Exact line layout, headers, and buffering depend on the client and any proxies. If testing streaming remotely, verify proxies do not buffer the stream.

### 11.2. Verifying the Default Server

With only `starter-webflux` and standard dependencies, Spring Boot 3.3 normally selects Reactor Netty. Verify with:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

and:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-reactor-netty --configuration runtimeClasspath
~~~

Then inspect startup logs to confirm the server type and port. Combined with HTTP tests, that gives far stronger evidence than guessing from `Mono` in a controller.

## 12. Running the Same WebFlux Application on Tomcat

To use Tomcat as the HTTP server for **this exact WebFlux application** on Spring Boot 3.3.x, swap dependencies in `build.gradle`:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Keep the Java files from Section 11 unchanged. `starter-webflux` still supplies WebFlux controllers, `WebFilter`s, and codecs. `starter-tomcat` supplies the HTTP server and Servlet adapter; do not add `spring-boot-starter-web` just to obtain Tomcat, because `starter-web` can make Boot select MVC.

What to verify:

1. Runtime classpath actually includes the Tomcat starter and required reactive dependencies.
2. The Reactor Netty server dependency was excluded as intended; if using `WebClient` with a Reactor Netty client, verify its client connector separately.
3. `ApplicationContext` remains a reactive web context, not an MVC web context.
4. Logs confirm Tomcat started; `GET /api/hello` returns the exact same JSON.
5. Streaming `/api/ticks`, cancellation, security, and error mapping continue working after the server change.

**This does not convert the app to Spring MVC.** The same controller returning `Mono` and the WebFlux pipeline keep running; Tomcat provides non-blocking Servlet I/O to the adapter.

## 13. Running the Same WebFlux Application on Jetty

On Spring Boot 3.3.x, follow the same pattern:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Keep `GreetingController` unchanged. After startup, verify the running server is Jetty, send the same test suite, and evaluate threads, timeouts, SSE, and connection/cancellation behavior.

Do not blindly copy `server.tomcat.*` properties to `server.jetty.*` by renaming prefixes. Shared properties like `server.port` work across both, whereas thread pools, connectors, and idle timeouts have distinct namespaces and semantics. Check the property reference for your exact Boot version before tuning.

## 14. Undertow: Example Applicable Only to Supported Branches

Spring Boot 3.3 still lists Undertow as an embedded reactive server. Unlike Tomcat and Jetty, Spring Framework 6.x uses Undertow's API directly for WebFlux rather than `ServletHttpHandlerAdapter`.

In a Boot 3.x project, illustrative dependencies:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Some Boot 3.x docs show module replacement when swapping Reactor Netty for Undertow to handle transitive dependencies; in your build, verify dependency resolution and avoid ending up with two competing web server factories.

**Spring Boot 4.0:** Undertow is no longer supported as an embedded server. When upgrading from Boot 3.x, choose Tomcat, Jetty, or Reactor Netty for your app, update dependencies and configuration, and re-run integration tests. Do not treat a Boot 3.x example as a compatibility promise for Boot 4.x.

## 15. If You Use WebClient, Does the Server Automatically Become Netty?

No. `WebClient` is an HTTP **client**, independent of the HTTP server handling inbound requests. A Spring MVC app on Tomcat can use a Reactor Netty-backed `WebClient` to call external APIs without turning its inbound server into Reactor Netty.

Likewise, a WebFlux app running on Tomcat or Jetty may still need Reactor Netty or another client connector for outbound `WebClient` calls depending on dependencies and configuration. Thus, seeing `reactor-netty` JARs on the classpath is insufficient to identify the inbound server. Check the server factory, context, and startup logs.

When multiple implementations coexist, avoid relying on unverified auto-selection. Configure transitive exclusions and dependencies deliberately and confirm which HTTP server factory Boot builds.

## 16. Testing: Verifying WebFlux Behavior Independently of the Server

### 16.1. WebTestClient at the Web Layer

`WebTestClient` sends HTTP requests to test WebFlux; it can bind directly to the application context without opening a real socket, or connect to a server running on a random port.

Web-layer tests verify:

- Routes `/api/hello` and `/api/ticks` are mapped.
- JSON body, HTTP status, content type, and mapping are correct.
- Controllers return `Mono`/`Flux` per contract.
- Validation, codecs, and exception handlers run through the WebFlux pipeline.

However, mock/bind-to-context tests do not prove a live Tomcat/Jetty/Netty listener actually accepts network connections.

### 16.2. Integration Testing Over Real HTTP

To verify the running server and actual HTTP adapter, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `WebTestClient`. File `src/test/java/example/reactive/GreetingControllerTest.java`:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void helloIsExposedOverHttp() {
        client.get()
                .uri("/api/hello?name=Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Lan");
    }

    @Test
    void missingNameUsesDefault() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, World");
    }
}
~~~

In Spring Boot 3.3.x, the annotations and APIs above fit this example. The test starts a real embedded web server on a random port, and the client sends requests to it. Re-run the exact same test suite after switching from Netty to Tomcat/Jetty to confirm HTTP contracts remain intact.

~~~bash
./gradlew test
~~~

Do not conclude full stack compatibility from two simple GET tests alone. If your application uses streaming, multipart uploads, WebSockets, TLS, or proxies, add dedicated tests for those features.

### 16.3. Testing SSE and Streaming

For SSE, test with `WebTestClient` or an HTTP client capable of incremental stream consumption:

- `Content-Type` header is `text/event-stream`.
- Exactly three events arrive in order.
- When the client cancels/disconnects, the server releases the upstream source.
- Proxies do not buffer the whole response when streaming is required.
- A slow consumer cannot cause unbounded buffer growth.

SSE works on Reactor Netty and compatible Servlet containers, though flush timing, connection lifecycle, and buffering details can differ; test over real networking and ingress before production rollout.

## 17. Differences in Request Body and Codec Handling

WebFlux uses `HttpMessageReader` and `HttpMessageWriter` beneath codecs to read and write requests/responses reactively. Parameters like `Mono<MyDto>` or `Flux<MyDto>` bind as publishers, unlike MVC controllers reading bodies through traditional `HttpMessageConverter`s.

Reading an entire body into a `List` forfeits streaming benefits. For large request bodies, account for memory buffering limits and multipart/streaming codec behavior. Spring Boot exposes codec properties such as `spring.codec.max-in-memory-size` in supported versions; always check property names for your exact Boot version.

Never confuse request `Content-Type` with response `Accept`; those two headers select codecs in opposite directions. When facing 400, 406, or 415 errors, check media types, mappings, codecs, and exception chains before suspecting the server adapter.

### 17.1. Does Switching Servers Change JSON Output?

Usually no, provided the WebFlux app, objects, codecs, and Jackson configuration stay the same. However, do not assume every header, transfer encoding, compression rule, connection behavior, or streaming flush behaves identically. Those can vary by server, connector, and proxy.

## 18. Spring Security on WebFlux-on-Servlet

When the application is WebFlux, use reactive Spring Security:

- `SecurityWebFilterChain` and `ServerHttpSecurity` for web authorization.
- `ReactiveSecurityContextHolder` to access security context reactively where appropriate.
- `WebFilter` and `ServerWebExchange` for request/response middleware.
- Reactive authentication/authorization matching `Publisher` contracts for async operations.

Servlet `SecurityFilterChain`/`HttpSecurity` belong to MVC/Servlet configuration; never treat them as the main WebFlux security configuration merely because Tomcat is the inbound server.

A legacy custom Servlet Filter might run at a low container level, yet mixing it with WebFlux is not the recommended default path. Audit the security chain and adapters carefully, because misplaced layering can bypass authentication or handle errors at the wrong stage.

Never trust raw client headers to self-authenticate tenants or users. Regardless of which server runs WebFlux, identity and permissions must come from verified authentication mechanisms.

## 19. Sessions, Request Context, and ThreadLocal

Servlet MVC apps frequently rely on request attributes and `ThreadLocal` across legacy libraries. In WebFlux, execution can continue on different threads across signals/schedulers, so `ThreadLocal` does not automatically follow the request.

Use:

- `ServerWebExchange.getAttributes()` for exchange-scoped attributes.
- WebFlux's `WebSession` API when sessions are needed.
- Reactor `Context` for data that must propagate along a reactive chain.
- Framework/library context-propagation APIs when integrating tracing or security.

Never store per-request data in static mutable fields or singleton bean fields. Never design logic assuming one thread handles the whole request just because a small test happened to observe the same thread name.

When migrating from MVC to WebFlux, audit MDC logging, security context, transaction context, and any `ThreadLocal`-based libraries. Use framework integrations rather than hand-rolling manual context copying without cleanup.

## 20. Threads, Connection Pools, and Resource Tuning

### On Reactor Netty

Reactor Netty uses event-loop resources for the server. Outbound `WebClient` instances can also use Reactor Netty resources and share them in default configurations. Monitor:

- Open connection counts, accept rates, and network errors.
- Event-loop pressure and request latency.
- Byte buffers and off-heap memory.
- CPU, GC, blocking calls, and scheduler saturation.
- Cancellation/timeouts and downstream client pools.

### On Tomcat/Jetty

The server manages connectors, thread pools, and non-blocking I/O adapters. Monitor:

- Acceptor/worker threads, request queues, and connection backlogs.
- Async request lifecycles, timeouts, and completion/cancellation.
- Downstream connection pools.
- Threads held too long by blocking APIs.
- Network buffering and client disconnects.

### Shared Boundaries

There is no universal "standard" thread count for every server. `server.tomcat.*` properties do not apply to Netty, and `server.netty.*` does not configure Tomcat. Before tuning, establish consistent baseline workloads/metrics and verify whether the bottleneck is actually the server or a downstream dependency.

## 21. Protocol and Deployment Limits to Verify

When changing runtimes, verify every feature the application depends on:

| Feature | What to verify |
| --- | --- |
| HTTP/1.1 keep-alive | Timeouts, connection reuse, max connections |
| HTTP/2 | Server dependencies, TLS/ALPN, proxy/ingress behavior |
| TLS | Termination at server vs. proxy, certificates, rotation |
| Compression | Config and supported Content-Types/sizes |
| SSE/streaming | Chunk flushing, buffering, client cancellation |
| WebSocket | Handshake/upgrade and session lifecycle |
| Multipart/uploads | Size limits, temp storage, and streaming |
| Large responses | Backpressure, memory/buffer limits |
| Forwarded headers | Trusted proxies, scheme, host, and client IP |
| Access logs | Format, request IDs, avoiding secret leaks |
| Graceful shutdown | Stop accepting new requests, drain, and timeouts |
| Health/readiness | Route traffic only when the instance is truly ready |

In Spring Boot WebFlux, properties like `server.port` and some common settings apply across servers. Server-specific options must be checked against your exact Boot version. Never treat identical property names as proof that two servers behave identically.

### 21.1. WebFlux and Reverse Proxies

An ingress may terminate TLS, compress responses, buffer chunks, or alter HTTP versions. A WebFlux streaming route may emit events every second while the client sees them arrive in bursts seconds later due to proxy buffering. When investigating, inspect the application, server adapter, network, and proxy together rather than blaming Reactor Netty or Tomcat blindly.

## 22. Common Mistakes

| Misconception | Reality | How to fix |
| --- | --- | --- |
| WebFlux only runs on Netty | WebFlux has Servlet adapters for Tomcat/Jetty | Separate web framework from HTTP server |
| Running on Tomcat means MVC | WebFlux-on-Tomcat still uses `DispatcherHandler` | Inspect `ApplicationContext` and active framework |
| Returning `Mono` proves the app is reactive | MVC can also support reactive return types | Check starters and the request pipeline |
| Having `WebClient` means the server uses Netty | `WebClient` is an HTTP client | Inspect the inbound server factory |
| Servlet Filters are standard middleware on WebFlux-on-Tomcat | WebFlux should use `WebFilter` | Migrate/audit middleware using reactive APIs |
| `ThreadLocal` works just like MVC | Reactive chains can switch threads | Use Reactor `Context` / `ServerWebExchange` |
| Netty makes every dependency non-blocking | JDBC, file I/O, and SDKs can still block | Use non-blocking drivers or isolate blocking calls |
| `Mono`/`Flux` guarantee end-to-end backpressure | Codecs, proxies, DBs, and network buffers have limits | Test streaming, cancellation, and memory |
| WebFlux on Tomcat supports WAR deployment like MVC | Traditional Boot WebFlux WAR deployment is unsupported | Use executable JARs and embedded servers |
| Undertow is available in all Boot versions | Boot 4.0 dropped embedded Undertow integration | Pick a server supported by your Boot version |
| Swapping starters needs no testing | Server adapters affect networking behavior | Test routing, bodies, streaming, TLS, security |
| Reactor Netty is always faster than Tomcat | Efficiency depends on workload and blocking | Run controlled benchmarks |
| Adding more threads always fixes bottlenecks | DB pools, CPU, or downstream may be the bottleneck | Measure actual threads, connections, and latency |

## 23. Safe Process for Choosing and Switching Servers

A clear engineering process:

1. **Identify whether the app is MVC or WebFlux.** Check runtime classpath and Spring context, not just annotation names.
2. **Identify the Boot version.** For Boot 4.x, remove Undertow from official embedded server candidates.
3. **Audit I/O dependencies:** classify JDBC, Redis, Kafka, filesystem, SDKs, and HTTP clients as blocking or non-blocking.
4. **Start from sensible defaults:** Reactor Netty for WebFlux; choose Tomcat/Jetty only with clear integration, operational, or test reasons.
5. **Swap starters cleanly:** exclude the default server when needed and add the target server; never accidentally add the MVC starter.
6. **Verify the web stack after switching:** reactive Spring application context, WebFlux route mappings, `WebFilter`s, and reactive Spring Security.
7. **Verify the server:** startup logs, dependency tree, server factory bean, and bound port.
8. **Run regression tests:** JSON request/response, statuses, errors, security, and SSE/WebSocket if used.
9. **Load-test and observe:** p50/p95/p99, connection counts, memory, CPU, threads, event loops, queues, cancellation, and timeouts.
10. **Roll out gradually:** health/readiness probes, graceful shutdown, rollback plan, and before/after metric comparisons.

Switching the **HTTP server** in a WebFlux app usually impacts controllers far less than switching the **web framework** from MVC to WebFlux. Yet both require runtime verification, especially when relying on server-specific settings.

## 24. Capstone Hands-On Exercise

**Scenario:** A team runs a reactive API with Spring WebFlux and wants to verify whether switching from Reactor Netty to Tomcat changes API semantics.

Proceed step by step:

1. Create the project from Section 11 with `starter-webflux` and default Reactor Netty.
2. Record runtime dependencies, application context type, startup logs, HTTP status/body of `/api/hello`, and `/api/ticks` behavior.
3. Add a `WebFilter` setting response header `X-API-Stack=WebFlux`; confirm the header appears.
4. Run integration tests with `WebTestClient` on a random port.
5. Switch dependencies as in Section 12 so WebFlux runs on Tomcat; keep the controller and `WebFilter` unchanged.
6. Verify the application context stays reactive while startup logs show Tomcat as the HTTP server.
7. Re-run tests for GET, JSON, SSE, `WebFilter`, error requests, and cancellation.
8. Try Jetty similarly if time permits; note starter and JDK versions.
9. If the app calls a blocking API, add a test showing saturation as concurrency rises; then offload blocking work to a bounded scheduler or switch to a reactive dependency.
10. Fill out a comparison table under identical CPU/memory limits and identical request loads.

Result table template:

| Criterion | Reactor Netty | Tomcat + Servlet bridge | Jetty + Servlet bridge |
| --- | --- | --- | --- |
| Web stack | WebFlux | WebFlux | WebFlux |
| HTTP server | Reactor Netty | Tomcat | Jetty |
| Adapter | Reactor Netty -> HttpHandler | Servlet -> HttpHandler | Servlet -> HttpHandler |
| Controller code | Unchanged | Unchanged | Unchanged |
| `WebFilter` | Works | Must test | Must test |
| JSON API | Test | Test | Test |
| SSE/cancellation | Test | Test | Test |
| Server-specific tuning | Netty | Tomcat | Jetty |

Do not fill in fabricated latency or throughput numbers. Draw conclusions only after measuring across multiple runs on the same workload, JDK, and hardware resources.

## 25. Self-Evaluation Questions

1. Why can WebFlux run on Tomcat without turning into Spring MVC?
2. What role does `HttpHandler` play in supporting multiple HTTP servers?
3. How do `ReactorHttpHandlerAdapter` and `ServletHttpHandlerAdapter` bridge two different API sets?
4. How do `WebHandler`/`DispatcherHandler` differ from `DispatcherServlet` in web stacks?
5. Why is directly using Servlet APIs discouraged inside WebFlux business handlers?
6. Which pipeline layers do `WebFilter` and Servlet `Filter` serve?
7. When can WebFlux controllers remain unchanged even when switching from Netty to Jetty?
8. When both `starter-web` and `starter-webflux` are present, why can't you infer the stack merely from `Mono` in a controller?
9. Does running WebFlux on Tomcat mean Spring Boot WebFlux supports traditional WAR deployment?
10. Why does Undertow appear in Spring Boot 3.x docs but not in Boot 4.0?
11. Why can blocking JDBC or `WebClient.block()` stall reactive request processing?
12. What is the difference between Reactive Streams backpressure and TCP/proxy buffering?
13. When is a mock `WebTestClient` sufficient, and when must you run a live HTTP server?
14. If switching servers breaks SSE while JSON GETs still pass, what should you inspect?
15. How can you tell whether a performance gain came from the server rather than the JDK or data/cache changes?
16. Why doesn't using a Netty-backed `WebClient` imply the inbound server is Reactor Netty?
17. What must be addressed when legacy Spring MVC Security relies on Servlet Filters and `ThreadLocal`?
18. Which parts of `application.properties` are portable across servers and which are server-specific?

## 26. Official References

- [Spring Framework – WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): supported servers, performance, concurrency, and Servlet boundaries.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): `HttpHandler`, `WebHandler`, and server adapters.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): switching servers, dependencies, factories, and HTTP options.
- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): configuring WebFlux applications.
- [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html): embedded server choices in Boot 4.0.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Undertow removal and version changes.
- [Spring Boot – Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): WAR deployment limitations for WebFlux.
- [Reactor Netty](https://spring.io/projects/reactor-netty/): non-blocking network model and Reactor integration.

When applying this in a real project, verify your exact Spring Boot, Spring Framework, and JDK versions and test over real networking. An HTTP server's limits depend not just on framework APIs, but also on dependencies, adapters, proxies, and how the application actually performs I/O.
