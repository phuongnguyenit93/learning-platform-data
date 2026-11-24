# Distinguishing Using a Servlet Container from Using the Servlet API in an Application

**Module:** Spring Framework – reactive  
**Parent topic:** WebFlux processing flow

## Learning objectives

After this lesson, you can:

1. Distinguish a **Servlet container** (the HTTP runtime environment) from the **Servlet API** (the set of interfaces for programming servlet applications).
2. Explain why Spring WebFlux can run on Tomcat/Jetty as a Servlet container while controllers still use `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange`, and `WebFilter`.
3. Describe the role of the Servlet adapter in connecting Servlet non-blocking I/O to Spring's reactive `HttpHandler`.
4. Recognize code belonging to the Spring MVC/Servlet model vs code belonging to the Spring WebFlux/reactive server model; avoid confusing the two models just because both can run on Tomcat.
5. Choose suitable dependencies and configuration when running WebFlux with Reactor Netty, embedded Tomcat, or as a WAR on an external Servlet container.
6. Avoid common mistakes: injecting `HttpServletRequest` into a WebFlux controller, using a Servlet `Filter` instead of `WebFilter`, reading `HttpSession`/ThreadLocal improperly, or accidentally making Spring Boot pick MVC.

## 1. Two different concepts

"Running on a Servlet container" and "using the Servlet API in application code" describe **two different layers**.

- **Servlet container** is the runtime/server that implements the Servlet contract: accepting HTTP connections, managing the web application, deploying servlets/filters/listeners, and dispatching requests/responses. Common examples are Apache Tomcat and Eclipse Jetty.
- **Servlet API** is the set of Java/Jakarta interfaces that a servlet application can program against directly, such as `HttpServletRequest`, `HttpServletResponse`, `HttpSession`, `Filter`, and `ServletContext`.

Spring WebFlux can be **hosted by a Servlet container**. In that case, Spring's integration layer uses the Servlet API at the server boundary to connect the container to the reactive runtime. However, the HTTP handling code of a typical WebFlux application uses the **reactive WebFlux API**, rather than writing controllers like a servlet application.

> **WebFlux can run inside a Servlet container; that does not mean WebFlux controllers are built on the Servlet API.** The adapter at the integration layer may use the Servlet API internally, while the application continues working with Spring's reactive abstractions.

This is not just a difference in naming. It determines how you write controllers, filters, read the body, handle sessions, manage data streams, and integrate security.

## 2. Three architectural layers

A WebFlux application can use different runtimes:

```text
                    HTTP client
                         |
                         v
                 HTTP runtime/server
                         |
             +-----------+-----------+
             |                       |
       Reactor Netty            Tomcat / Jetty
       (no Servlet API          (Servlet container)
        needed)                        |
             |                   Servlet API
             |                         |
             |              Servlet reactive adapter
             |                         |
             +------------+------------+
                          |
                          v
                   Spring HttpHandler
                          |
                          v
                WebFlux WebHandler chain
                          |
              +-----------+-----------+
              |                       |
          WebFilter               HandlerMapping
                                      |
                                      v
                                  Controller
                                      |
                           Mono<T> / Flux<T> body
```

The diagram depicts the conceptual boundaries:

1. **HTTP runtime:** accepts connections and transfers data. Can be Reactor Netty or a Servlet container supported by Spring.
2. **Server adapter:** converts the runtime's request/response into abstractions that the Spring reactive server understands. With a Servlet container, the adapter interacts with the Servlet API and the container's non-blocking I/O mechanism.
3. **WebFlux application:** processes via `HttpHandler`, `WebFilter`, `ServerWebExchange`, controllers, and `Mono`/`Flux`.

When running with Reactor Netty, no Servlet container or Servlet API is needed to serve HTTP. When running with Tomcat, Tomcat is still a Servlet container, but WebFlux uses a reactive adapter to process requests. Controllers do not become `HttpServlet` because of this.

## 3. A Servlet container does not mean Spring MVC

Both Spring MVC and Spring WebFlux can run on Tomcat. They use different processing models.

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Application-side server model | Servlet-based | Reactive WebHandler/HttpHandler |
| Main dispatching component | `DispatcherServlet` | `DispatcherHandler` in WebFlux |
| Request abstraction | `HttpServletRequest` | `ServerHttpRequest` |
| Response abstraction | `HttpServletResponse` | `ServerHttpResponse` |
| Framework-layer filter | Servlet `Filter` / `OncePerRequestFilter` | `WebFilter` |
| Session abstraction | Usually `HttpSession` | `WebSession` |
| Body data | Servlet streams/MVC message converters | `Mono<T>`, `Flux<T>`, `Flux<DataBuffer>` |
| Return types | DTO, object, `ResponseEntity`; also supports reactive return types | DTO, `Mono<T>`, `Flux<T>`, and reactive responses |
| Common runtime | Servlet container | Reactor Netty or a Servlet container with an adapter |

**Tomcat only tells you the runtime**, which is not enough to conclude whether an application is MVC or WebFlux. You must check the dependencies, application type, handler stack, and the APIs the application code uses.

An easy point of confusion: Spring MVC can accept some reactive types such as `Mono` or `Flux` as return values and adapt them. Having a controller return `Mono<String>` **does not automatically turn an MVC application into WebFlux**. If requests still go through `DispatcherServlet` and the Servlet request lifecycle, it is still Spring MVC.

Similarly, using `WebClient` inside an MVC application does not turn the server into WebFlux. WebClient is a reactive HTTP client; the server-side programming model is decided separately.

## 4. How does WebFlux use a Servlet container?

Spring WebFlux has a central server abstraction called `HttpHandler`. A runtime-specific adapter receives the request from the server and passes it into the reactive processing chain.

When running on a Servlet container, Spring provides an adapter such as `ServletHttpHandlerAdapter`. This adapter integrates with the Servlet API, using the container's asynchronous/non-blocking I/O capabilities to connect the request and response to `HttpHandler`.

This means:

- Tomcat still accepts connections, manages sockets, deploys the web application, and provides the Servlet runtime.
- The Servlet adapter is the bridge between the container's request/response and Spring's reactive server API.
- WebFlux handles bodies and responses in terms of publishers, demand, cancellation, and reactive abstractions.
- The application does not have to write `HttpServlet` itself or call `HttpServletRequest.getInputStream()` to read the body in controllers.
- Using a Servlet container **does not automatically turn blocking operations in the application into non-blocking ones**.

### 4.1. Servlet non-blocking I/O

Reactive integration through Servlet relies on the non-blocking I/O API added in Servlet 3.1, such as callback-driven reading/writing and stream readiness state. Spring's adapter uses this mechanism to connect to the reactive pipeline instead of forcing the application to manage Servlet input/output streams itself.

When deploying Spring Boot 3, you must also consider the **Jakarta namespace and compatible container versions**. For example, a Boot 3.3.x project uses Tomcat 10.1. You cannot take an older container using `javax.servlet` and assume it is compatible with a Spring Boot 3 application using `jakarta.servlet`.

### 4.2. The adapter using the Servlet API internally does not mean the application should use it

An adapter may need Servlet types to receive callbacks from the container. That is a detail of the integration layer. A WebFlux application should still program against WebFlux's public abstractions:

- Reading the request: `ServerHttpRequest` or `ServerWebExchange`.
- Writing the response: `ServerHttpResponse` or returning a body from the controller.
- Filters: `WebFilter`.
- Session: `WebSession`.
- Authentication information: `Principal` and Spring Security reactive.
- Request-scoped metadata: exchange attributes or Reactor `Context`.

Do not pull internal Servlet objects out of the adapter to build container-dependent business logic. Doing so makes the code hard to run on Reactor Netty and reduces WebFlux portability.

## 5. Looking at code to recognize the programming model

### 5.1. WebFlux controller

```java
@RestController
public class ReactiveController {
    @GetMapping("/profile")
    public Mono<String> profile(ServerHttpRequest request) {
        String method = request.getMethodValue();
        String path = request.getPath().value();
        return Mono.just(method + " " + path);
    }
}
```

This is an **illustrative WebFlux controller snippet**. The method receives `ServerHttpRequest` and returns `Mono<String>`. The WebFlux infrastructure consumes the publisher to produce the HTTP response. The controller does not receive `HttpServletRequest` and does not need to call `subscribe()` itself.

### 5.2. Spring MVC controller using the Servlet API

```java
@RestController
public class ServletController {
    @GetMapping("/profile")
    public String profile(HttpServletRequest request) {
        return request.getMethod() + " " + request.getRequestURI();
    }
}
```

This is an **illustrative Spring MVC snippet**; it needs to import `jakarta.servlet.http.HttpServletRequest` in a Spring Boot 3 application and use the appropriate MVC stack. `HttpServletRequest` is a Servlet API. Do not copy this example directly into a WebFlux controller.

### 5.3. Comparing filters

A Servlet filter has a contract like:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

WebFlux's `WebFilter` has a reactive contract:

```java
Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain);
```

A Servlet filter runs in the Servlet filter chain; a WebFilter sits in the WebFlux WebHandler chain. Even when WebFlux is hosted by Tomcat, these two filters still have **different contracts and processing positions**. In WebFlux application logic, prefer `WebFilter`. A Servlet filter should only be added when there is an integration requirement at the Servlet container boundary and you thoroughly understand async dispatch/lifecycle.

## 6. Running WebFlux on embedded Tomcat: a Java 17+ example

This example illustrates the exact main point: the application uses **Tomcat as the server runtime**, while the controller code uses the reactive API. Uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**.

Project structure:

```text
webflux-on-tomcat/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── WebFluxTomcatApplication.java
    │   ├── RequestTraceWebFilter.java
    │   └── ApiController.java
    └── resources/
        └── application.properties
```

### 6.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-on-tomcat</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-reactor-netty</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <!-- Tomcat is the server container; WebFlux remains the application model. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
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
```

Here, we exclude the Reactor Netty starter from the WebFlux starter and add the Tomcat starter. The project does **not** add `spring-boot-starter-web`, so it does not pull in Spring MVC/DispatcherServlet just to run on Tomcat. Tomcat provides the server container; Spring Boot configures the corresponding reactive server adapter.

### 6.2. application.properties

```properties
spring.main.web-application-type=reactive
server.port=8080
```

Setting the application type explicitly keeps the example focused on a reactive web application. With a WebFlux-only dependency setup as above, Boot can usually infer the reactive type; this property helps prevent confusion when changing dependencies while learning.

### 6.3. WebFluxTomcatApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxTomcatApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxTomcatApplication.class, args);
    }
}
```

### 6.4. RequestTraceWebFilter.java

```java
package demo;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class RequestTraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();
        exchange.getAttributes().put("demo.requestId", requestId);
        exchange.getResponse().getHeaders()
                .set("X-Request-Id", requestId);

        return chain.filter(exchange)
                .doFinally(signal ->
                        System.out.println(
                                "request " + requestId + " -> " + signal));
    }
}
```

The filter uses `ServerWebExchange` and `WebFilter`. There is no `jakarta.servlet.Filter`, `HttpServletRequest`, or `HttpServletResponse` in the application code. The header is set before the chain processes the response. `doFinally` records the complete/error/cancel outcome at this publisher position.

### 6.5. ApiController.java

```java
package demo;

import java.time.Duration;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {
    public record RuntimeInfo(
            String application,
            String method,
            String path,
            String requestId) {}

    @GetMapping("/api/runtime")
    public Mono<RuntimeInfo> runtime(
            ServerHttpRequest request,
            ServerWebExchange exchange) {

        String requestId = exchange.getAttributeOrDefault(
                "demo.requestId", "missing");

        return Mono.just(new RuntimeInfo(
                "Spring WebFlux",
                request.getMethodValue(),
                request.getPath().value(),
                requestId));
    }

    @PostMapping(
            value = "/api/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(@RequestBody Mono<String> body) {
        return body.map(value -> "echo: " + value);
    }

    @GetMapping(
            value = "/api/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofMillis(500)).take(3);
    }

    @GetMapping("/api/manual-response")
    public Mono<Void> manualResponse(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.ACCEPTED);
        response.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        byte[] bytes = "written through ServerHttpResponse\n"
                .getBytes(StandardCharsets.UTF_8);
        DataBuffer buffer = response.bufferFactory().wrap(bytes);

        return response.writeWith(Mono.just(buffer));
    }
}
```

The controller uses four reactive/server-side types:

- `ServerHttpRequest` to read the method and path.
- `ServerWebExchange` to read the request attribute.
- `ServerHttpResponse` to write the response in the special endpoint.
- `Mono`/`Flux` to represent the body and streaming.

Not a single Servlet API is used directly in the controller. Tomcat is still the underlying container.

### 6.6. Trying it out

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In the startup logs, verify that the selected server is Tomcat (Tomcat startup log line), not Reactor Netty.

On Windows PowerShell use `curl.exe` to avoid the `curl` alias; on Linux/macOS you can use `curl`:

```powershell
curl.exe -i http://localhost:8080/api/runtime
curl.exe -i -X POST -H "Content-Type: text/plain" --data "hello" http://localhost:8080/api/echo
curl.exe -i http://localhost:8080/api/manual-response
curl.exe -N http://localhost:8080/api/ticks
```

**Observed results to watch for:**

1. `GET /api/runtime` returns HTTP 200, JSON with `application` set to `Spring WebFlux`, method `GET`, path `/api/runtime`, and the request ID. The `X-Request-Id` header has the same value as the request ID field.
2. `POST /api/echo` with body `hello` returns the body `echo: hello`.
3. `GET /api/manual-response` returns HTTP 202 Accepted and the body `written through ServerHttpResponse`.
4. `GET /api/ticks` emits three numeric events over time via `text/event-stream`. Use `-N` so curl does not buffer output when displaying.

Example filter log (the request ID changes each time):

```text
request <request-id> -> onComplete
request <request-id> -> onComplete
request <request-id> -> onComplete
request <request-id> -> onComplete
```

This is the shape of the log when requests complete normally; the stream may be cancelled if the client disconnects before all three events are emitted.

**Significance of the example:** Tomcat is a Servlet container and provides the Servlet environment at the server layer, yet the controller and WebFilter still use the reactive WebFlux API. Adding Tomcat does not force us to rewrite code to Spring MVC.

## 7. Deploying WebFlux as a WAR on an external Servlet container

Besides embedded Tomcat, WebFlux can be packaged as a WAR to deploy into a compatible Servlet container. This is a deployment choice; it does not change the application programming model.

### 7.1. Application initializer

With Spring Boot, the application class can extend `SpringBootServletInitializer` so the external container initializes the Spring application:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WebFluxWarApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(WebFluxWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WebFluxWarApplication.class, args);
    }
}
```

This is a **configuration snippet for WAR deployment**. Extending `SpringBootServletInitializer` is the bridge for the Servlet container to boot the Spring Boot application. The WebFlux controllers inside still receive `ServerHttpRequest`/`ServerWebExchange` and return `Mono`/`Flux`.

### 7.2. Build changes usually required

- Set Maven packaging to `war`.
- Exclude `spring-boot-starter-reactor-netty` if you want to run on a Servlet container.
- Set `spring-boot-starter-tomcat` to `provided` scope when external Tomcat provides the runtime.
- Choose a Tomcat version compatible with the application's Spring Boot/Jakarta Servlet version.
- Do not package an older Servlet API or conflicting namespace into the WAR.

Example Tomcat dependency for a WAR:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

The snippet above **replaces the embedded Tomcat dependency** in the previous example; do not keep both Tomcat declarations with different scopes. The WebFlux starter still excludes Reactor Netty as in the example. When deploying, the container must meet the Jakarta baseline required by the Boot version; for example Boot 3.3.x usually goes with Tomcat 10.1. Tomcat 9 uses the `javax.servlet` namespace and is therefore not directly compatible with Boot 3 applications using `jakarta.servlet`.

**Distinction:** `SpringBootServletInitializer` is the integration bootstrap for Servlet container deployment. The presence of this class does not mean you have to write controllers with `HttpServletRequest`.

## 8. When is the Servlet API genuinely needed in code?

Some applications need to integrate legacy libraries or components originally designed specifically for the Servlet API. Before bringing them into WebFlux, identify the boundary:

- If the component only needs to run inside a Servlet container, simply deploying WebFlux on Tomcat/Jetty may be enough; business code keeps the reactive API.
- If the library requires `HttpServletRequest`/`HttpServletResponse` or a Servlet Filter, it depends on the Servlet programming model. You need an adapter or a clear integration boundary; do not assume WebFlux controllers will supply those types.
- If the feature relies on ThreadLocal, request-bound state, or synchronous Servlet callbacks, re-evaluate it because reactive chains can switch threads and many requests can interleave.
- If the logic only needs method/header/path/body, use `ServerHttpRequest`; if it needs request/response/session/principal together, use `ServerWebExchange`.
- If the requirement is genuinely to build a traditional Servlet/MVC application, choose Spring MVC and use the Servlet API properly instead of forcing the Servlet programming model into WebFlux.

### 8.1. Can a Servlet Filter be used outside the adapter?

In a Servlet container deployment, a Servlet Filter can sit in the container's filter chain and wrap the servlet adapter. This is useful for certain integrations at the Servlet boundary, but keep in mind:

- It runs according to the Servlet filter lifecycle and can receive the Servlet request/response.
- It wraps the WebFlux adapter; it does not replace WebFilters inside the reactive chain.
- Async dispatch and non-blocking I/O operations must adhere to the Servlet container's contract.
- Do not block threads or casually read the body and expect the WebFlux decoder to still receive the same stream.
- If the concern belongs to the application's reactive HTTP logic, `WebFilter` is usually the better place and works across multiple runtimes.

Do not register the same authentication logic in both a Servlet Filter and a WebFilter without a clear design; this can lead to duplicate checks, confusing order, or differences between runtimes.

## 9. Common replacement abstractions in WebFlux

| Need in Servlet code | Commonly used WebFlux abstraction | Notes |
| --- | --- | --- |
| `HttpServletRequest` | `ServerHttpRequest` / `ServerWebExchange` | Reads request metadata and body reactively. |
| `HttpServletResponse` | `ServerHttpResponse` | Sets status/headers and writes body via a publisher. |
| `Filter` / `OncePerRequestFilter` | `WebFilter` | Returns `Mono<Void>` and composes the chain. |
| `HttpSession` | `WebSession` via `exchange.getSession()` | Reactive session API; do not block to retrieve. |
| Request attributes | `exchange.getAttributes()` | Scoped to one exchange/request. |
| ThreadLocal request context | Reactor `Context`, exchange attributes, tracing | Do not assume the same thread handles the entire pipeline. |
| Servlet async request handling | `Mono`/`Flux` + reactive server runtime | Backpressure/cancel are represented with Reactive Streams. |
| Servlet multipart parsing | WebFlux multipart reader, `Part`/`PartEvent` | Choose parsing/streaming suited to body size. |
| Servlet input/output stream | `Flux<DataBuffer>` and response write APIs | Requires understanding buffer ownership, release, and cancellation. |

Not every Servlet API has a one-to-one replacement in WebFlux. For example, `ServletContext` is an abstraction of the Servlet container; in a Spring application, many configuration/lifecycle needs belong to `ApplicationContext`, `Environment`, or bean lifecycles. Migrate according to **business intent**, rather than mechanically renaming classes.

### 9.1. Session and principal

```java
Mono<String> userName = exchange.getPrincipal()
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");

Mono<WebSession> session = exchange.getSession();
```

This is an **illustrative snippet** in a handler/filter, requiring imports for `Principal` and `WebSession`. Do not call `block()` to obtain the session or principal on the event loop. For authentication/authorization, use Spring Security reactive instead of trusting headers yourself or storing the current user in a singleton field.

### 9.2. Request context is not ThreadLocal

Synchronous Servlet applications often rely on one request being processed on one thread at a given time. A reactive pipeline may resume on another thread due to schedulers, I/O callbacks, or operators. Therefore, do not store a request ID, user ID, or transaction context in a mutable `ThreadLocal` and assume every callback reads the right request.

Use Reactor `Context` or `ServerWebExchange.getAttributes()` depending on the data's scope. Context is tied to the subscription; attributes are tied to the exchange. Both are better suited for per-request data in a reactive flow.

## 10. Dependencies and runtime choice

### 10.1. Default WebFlux usually uses Reactor Netty

`spring-boot-starter-webflux` brings in Reactor Netty by default when no server is swapped. This is the common choice for a reactive server that does not need a Servlet container. If you want to use Tomcat or Jetty, exclude the default server starter and add the corresponding server starter according to your Spring Boot version's guide.

### 10.2. Do not add spring-boot-starter-web just to get Tomcat

`spring-boot-starter-web` brings in Spring MVC and an embedded Servlet server. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot usually prefers MVC configuration when both stacks exist. In that case, the application may run on Tomcat while the **application model is MVC**, even though the WebFlux dependency is also present.

To get a WebFlux server, you usually only need `spring-boot-starter-webflux` and the appropriate server runtime. To use Tomcat, add `spring-boot-starter-tomcat` after excluding Reactor Netty as in the example.

### 10.3. Do not infer the programming model from the return type

Spring MVC can adapt some reactive return types. For example, an MVC controller can return `Mono<ResponseEntity<?>>` yet requests still flow through Servlet/MVC infrastructure. Conversely, a WebFlux controller returning an ordinary DTO is still handled reactively by WebFlux; not every method is required to return `Flux`.

Determine the stack via configuration and the server factory, not solely by the word `Mono` in a method signature.

### 10.4. Namespace version matters

Spring Boot 2 and Spring Framework 5 belong to the `javax.servlet` ecosystem; Spring Boot 3 and Spring Framework 6 use `jakarta.servlet`. Dependencies, filters, and containers must match in namespace/version. Do not mix `javax.servlet.*` classes into a Boot 3 application using `jakarta.servlet.*`; they are different packages even though type names look similar.

## 11. Non-blocking is not automatic just from running on Tomcat

A Servlet container supporting non-blocking I/O is a precondition for the adapter to integrate a reactive server. But that does not turn all application code into non-blocking code.

```java
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> jdbcTemplate.queryForObject(
            "select message from greeting where id = 1",
            String.class))
        .subscribeOn(Schedulers.boundedElastic());
}
```

This is an **illustrative snippet**: `jdbcTemplate` and imports are provided by the application. `fromCallable` defers the call and turns exceptions into error signals, while `subscribeOn(boundedElastic())` isolates the blocking operation on an appropriate scheduler. JDBC is still blocking; it cannot be called non-blocking just because the server is WebFlux/Tomcat.

Better yet, when possible, use reactive APIs such as R2DBC and WebClient. Whether running Netty or Tomcat, a blocking operation placed on an I/O-handling thread can still reduce request-serving capacity and increase latency.

## 12. Choosing the right model for the requirements

| Situation | Appropriate choice |
| --- | --- |
| New reactive application, no Servlet ecosystem needed | WebFlux + Reactor Netty. |
| WebFlux application must run on enterprise infrastructure standardized on Tomcat | WebFlux + reactive Tomcat adapter; application code still uses the WebFlux API. |
| Need to deploy a WAR into a supported Servlet container | WebFlux WAR + `SpringBootServletInitializer` and a Jakarta-compatible container. |
| Legacy application heavily dependent on `HttpServletRequest`, Servlet Filters, and HttpSession | Consider the Spring MVC/Servlet model or design a separate integration boundary. |
| Need to keep MVC controllers but want asynchronous HTTP calls | Can use WebClient; the server does not become WebFlux because of it. |
| Only need streaming/reactive return values in MVC | Evaluate MVC's reactive adapter capabilities; do not confuse with the WebFlux server stack. |

No single choice is best for every system. Look at existing integration libraries, deployment standards, streaming needs, I/O management, and operational capabilities. Do not switch to WebFlux just because you want to use a newer Tomcat; nor abandon WebFlux just because your organization standardizes on a Servlet container.

## 13. Common mistakes

| Misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| "WebFlux runs on Tomcat so controllers use `HttpServletRequest`." | Tomcat is the runtime; WebFlux controllers use reactive server abstractions. | Use `ServerHttpRequest`/`ServerWebExchange`. |
| "Having the Servlet API on the classpath means the app is running MVC." | The Servlet API may be used by the container/adapter to host WebFlux. | Check the web application type, starters, and server factory. |
| "Using `Mono` guarantees the app is WebFlux." | Spring MVC also has reactive return-type adapters. | Check whether the stack is MVC/DispatcherServlet or WebFlux/DispatcherHandler. |
| Adding `spring-boot-starter-web` just to get Tomcat | Can cause Boot to prefer MVC when both stacks are present. | Use the WebFlux starter and add the Tomcat server starter separately. |
| Using a Servlet `Filter` for all WebFlux logic | Servlet filters belong to the container chain, not the reactive WebFilter chain. | Use `WebFilter` for the application's reactive concerns. |
| Using `HttpSession` directly in a WebFlux controller | Not WebFlux's standard reactive session abstraction. | Use `WebSession` via the exchange. |
| Storing request data in ThreadLocal | Reactive flows can switch threads and interleave multiple requests. | Use Reactor Context or exchange attributes. |
| Calling `block()` to get the request body/principal | Blocks threads and breaks the reactive lifecycle. | Compose publishers with `map`/`flatMap`. |
| Reading the Servlet input stream and letting the WebFlux decoder read next | The body may already be consumed; the request body is a one-time stream. | Use codecs or an explicitly managed replay strategy. |
| Thinking Tomcat makes blocking JDBC non-blocking | The container does not change the I/O nature of the library. | Use a reactive driver or isolate blocking work. |
| Deploying a Boot 3 WAR to a container that only has javax Servlet | Incompatible namespaces. | Use a Jakarta-compatible container of the right version. |
| Assuming a Servlet container is always required for WebFlux | Reactor Netty can run WebFlux standalone. | Choose the runtime based on deployment requirements. |
| Assuming WebFlux cannot run on a Servlet container | WebFlux has Servlet adapters supporting compatible containers. | Configure the adapter/server starter for the right version. |
| Using Servlet request in a shared service to read the current request | Creates container coupling and request-thread assumptions. | Pass needed data via parameters or reactive context. |

## 14. Self-check questions

**Question 1.** How do a Servlet container and the Servlet API differ?  
**Answer:** The container is the runtime that deploys and executes web applications; the Servlet API is the set of Java/Jakarta interfaces that servlet code uses to handle requests, responses, sessions, and filters.

**Question 2.** Can WebFlux run on Tomcat?  
**Answer:** Yes. Spring provides adapters to integrate the reactive HttpHandler with compatible Servlet containers. Tomcat remains a Servlet container, while WebFlux controllers use the reactive API.

**Question 3.** If a controller receives `ServerHttpRequest`, does that mean the application does not use the Servlet API at any layer?  
**Answer:** No. When hosted on Tomcat, the adapter may use the Servlet API internally. What matters is that application code does not depend on the Servlet API as its primary programming model.

**Question 4.** Are `WebFilter` and Servlet `Filter` the same?  
**Answer:** No. They sit in two different chains and have different contracts: `WebFilter` returns `Mono<Void>`; Servlet Filter uses `doFilter` with Servlet request/response and FilterChain.

**Question 5.** If an application has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, what does Boot usually choose?  
**Answer:** When both stacks are present, Spring Boot usually prefers Spring MVC. To get a WebFlux server, do not add the MVC starter unless truly needed; select the server runtime with the appropriate dependency.

**Question 6.** Does using `Mono<String>` as a return type prove a controller is WebFlux?  
**Answer:** No. Spring MVC can also adapt reactive return types. You must inspect the entire server stack and application type.

**Question 7.** If using Tomcat with WebFlux, can you use `HttpSession` instead of `WebSession`?  
**Answer:** In the WebFlux application model, use `WebSession`. Just because the container has a Servlet session API does not mean you should pull Servlet sessions into reactive handlers.

**Question 8.** Does Tomcat's non-blocking adapter make synchronous JDBC non-blocking?  
**Answer:** No. JDBC is still blocking. Use a reactive driver or offload blocking tasks to an appropriate scheduler.

**Question 9.** Which Servlet package does Boot 3 use?  
**Answer:** `jakarta.servlet.*`. Do not mix it with `javax.servlet.*` from the older ecosystem.

## Key takeaways

- **A Servlet container is where it runs; the Servlet API is the set of interfaces for programming in the Servlet model.**
- Spring WebFlux can run on Reactor Netty or a Servlet container such as Tomcat/Jetty through an appropriate adapter.
- When WebFlux runs on Tomcat, the adapter may use the Servlet API at the integration layer; application controllers and filters should still use `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange`, and `WebFilter`.
- Running on Tomcat does not automatically turn WebFlux into Spring MVC. Conversely, using `Mono` in Spring MVC does not automatically turn MVC into WebFlux.
- To use WebFlux with Tomcat, choose the WebFlux starter and Tomcat server dependency, avoiding accidentally adding the MVC starter; verify application type and Jakarta compatibility.
- Non-blocking behavior depends on the whole pipeline. JDBC/blocking calls remain blocking even when the application runs on a reactive server.

### References

1. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive server architecture and supported runtimes.
2. [Spring Framework – Reactive Web Server API](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, server adapters, `ServerWebExchange`, and `WebFilter`.
3. [Spring Framework – ServerHttpRequest Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): the reactive server's request abstraction.
4. [Spring Framework – ServletHttpHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServletHttpHandlerAdapter.html): bridge between a Servlet container and reactive `HttpHandler`.
5. [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux and server runtime configuration.
6. [Spring Boot – Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): WAR deployment and `SpringBootServletInitializer`.
7. [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): Servlet API, async processing, and non-blocking I/O.
