# End-to-end path from network connection to business logic and response

## 1. Understanding the scope

When a user sends an HTTP request to a Spring Boot application, the method in `@RestController` is not invoked directly from the network. The request must travel through the connection layer, HTTP server, cross-cutting application layers, and Spring's routing layer before reaching business logic. The result is then converted into an HTTP response and sent back to the client.

Within the **Spring Boot - web-runtime** module, two common deployment models should be distinguished:

- **Spring MVC (Servlet stack):** typically runs on embedded Tomcat, and can also use Jetty or a compatible Servlet server. `DispatcherServlet` is the request dispatch point in Spring MVC.
- **Spring WebFlux (reactive stack):** typically runs on Reactor Netty, though it can also operate on supported Servlet servers. `DispatcherHandler` handles dispatching at the WebFlux layer.

Both stacks share many logical steps (route → handler → service → response generation), but their HTTP processing interfaces and execution models differ. Sections 2–5 follow the Servlet/MVC flow as the primary example; Section 6 contrasts WebFlux.

## 2. Diagram of one request/response round trip

```text
Client (browser, mobile app, curl, another service)
    │  HTTP request: method + URL + headers + body (if any)
    ▼
DNS / TCP connection / TLS when needed
    │  May pass through reverse proxy / load balancer / API gateway
    ▼
Embedded HTTP server (e.g., Tomcat)
    │  Accepts, parses HTTP, and creates request/response objects
    ▼
Servlet Filter chain
    │  Logging, CORS, security... if configured
    │  Can intercept and return a response right here
    ▼
DispatcherServlet
    │  HandlerMapping finds route, HandlerAdapter invokes handler
    │  Resolves arguments, converts types, reads body, validates when applicable
    ▼
Controller (@RestController)
    ▼
Service (business rules)
    │
    ├── Repository / database (if needed)
    └── API, cache, message broker... (if needed)
    │
    ▼
Return value / business error
    ▼
Spring MVC processes result
    │  Determines status + headers; serializes JSON, renders view...
    ▼
Servlet Filter chain finishes → HTTP server sends bytes
    ▼
Intermediate proxy (if any) → Client receives HTTP response
```

The diagram represents the **logical processing order**; it does not mean every request always opens a new TCP connection, always passes through a proxy, always accesses a database, or necessarily holds a single thread. HTTP keep-alive reuses connections; HTTP/2 can multiplex multiple streams over a single connection.

## 3. What is already in place before a request arrives?

When `SpringApplication.run(...)` is called, Spring Boot creates the `ApplicationContext`, loads beans/configurations, auto-configures the web infrastructure based on dependencies and settings, starts the embedded web server, and registers the required filters, dispatchers, and mappings. For instance, `spring-boot-starter-web` typically activates Spring MVC and default Tomcat; the application registers routes from `@RequestMapping`, `@GetMapping`, etc.

By the time the server is ready to accept requests, controllers and services are usually already instantiated by Spring as beans with dependencies injected. The route `GET /api/orders/{id}` is not constructed on the fly for each user call: Spring already knows the mapping and uses it to look up the handler at runtime.

Settings such as `server.port`, context path, TLS, and proxy ports determine where requests enter. If TLS terminates at a reverse proxy, Tomcat may receive internal HTTP even though the public URL is HTTPS; do not assume every request arrives directly at the embedded server.

## 4. Detailed steps in Spring MVC / Servlet

### Step 1 — Client forms the request and establishes transport

The client prepares the method (GET/POST/...), path, query string, headers, and body as required. DNS may resolve the hostname; the client opens or reuses a connection and performs a TLS handshake if needed. A proxy/gateway may terminate TLS, inspect, or forward the request. **TCP/TLS handles transport; HTTP describes the request and response.**

Example request from client:

```http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

### Step 2 — HTTP server accepts the request

Tomcat receives the bytes, parses the request line, headers, and body, sets up `HttpServletRequest`/`HttpServletResponse` objects, and runs the Servlet processing pipeline. In typical synchronous processing, an active request executes on a container worker thread. This **does not mean** every open connection always occupies a thread or that async mechanisms keep the exact same model.

If a request cannot be parsed or is rejected at the server/proxy layer (e.g., protocol error, size limit exceeded), it can terminate **before any controller runs**.

### Step 3 — Filter chain runs before the dispatcher

Servlet `Filter` (often implemented via `OncePerRequestFilter` when needed) can measure timing, record correlation IDs, enforce CORS, wrap the request, modify headers, or control access. If Spring Security is present, `FilterChainProxy` coordinates security filters to authenticate/authorize before letting the request proceed.

A filter calls `chain.doFilter(request, response)` to forward the request; it can also terminate the request with a response, such as 401/403, without invoking the controller. Code **before** `chain.doFilter` runs ahead of downstream filters/dispatcher; code **after** this call typically runs on the way back. Actual ordering depends on filter configuration and dispatch type (REQUEST/ASYNC/ERROR).

### Step 4 — `DispatcherServlet` selects the handler

`DispatcherServlet` is Spring MVC's front controller. It relies on `HandlerMapping` to find the handler matching the HTTP method and path; then `HandlerAdapter` prepares and executes the handler invocation. For example, `GET /api/orders/42` matches `@GetMapping("/{id}")` on a controller with prefix `/api/orders`.

Spring uses argument resolvers to bind `@PathVariable`, `@RequestParam`, `@RequestHeader`; reads `@RequestBody` via `HttpMessageConverter`; performs type conversion; and triggers validation if configured/annotated (e.g., `@Valid`). Binding/validation errors can produce an HTTP 400 before the controller method body executes.

`HandlerInterceptor`, if registered, can run `preHandle` before the handler, `postHandle` after successful execution, and `afterCompletion` upon completion. Interceptors operate inside the Spring MVC flow rather than as Servlet Filters; callback ordering has exceptions during async processing or errors.

### Step 5 — Controller coordinates business logic

The controller receives bound data and calls the constructor-injected service. The service applies business rules and may call repositories, databases, caches, or other systems. When `@Transactional` is used, transaction boundaries typically sit at the service layer; transactions only take effect when a transaction manager is configured and the method is properly proxied/applied.

Keeping controllers focused on HTTP protocol, binding, and response selection while placing business rules in services improves testability and reuse. Not every request needs a database.

### Step 6 — Spring builds the HTTP response

A controller can return `ResponseEntity<T>` (controlling status, headers, body), a DTO object from `@RestController`, a `String`, a view name, or a streaming response, depending on the endpoint type. For JSON DTOs in Spring MVC, an appropriate `HttpMessageConverter` (commonly using Jackson) converts Java objects to JSON according to content negotiation, serializer configuration, and headers.

The result becomes **HTTP status + headers + body bytes**, such as 200, `Content-Type: application/json`, and JSON. Spring does not send raw Java objects over the wire. When using `@Controller` returning a view name, it may go through view resolution/rendering instead of JSON serialization.

### Step 7 — Exceptions and error flow

Exceptions can occur in filters, argument binding, controllers, services, or response serialization. In Spring MVC, `HandlerExceptionResolver` and `@ExceptionHandler`/`@RestControllerAdvice` can map application errors into appropriate status codes and bodies. Unhandled errors can fall back to the container/Spring Boot default error handling. Errors thrown by filters before the dispatcher may require separate handling; do not assume every error reaches `@RestControllerAdvice`.

Common error paths:

- No matching route/handler found: typically **404 Not Found**.
- Path variable type mismatch, malformed JSON, or failed validation: typically **400 Bad Request**.
- Rejected by the security layer: can be **401 Unauthorized** (unauthenticated) or **403 Forbidden** (insufficient permissions), depending on configuration.
- Unhandled error: typically **500 Internal Server Error**.

These are **typical examples**, not rigid rules for every app: exception handlers, proxies, security, and configurations can alter statuses and bodies. Once response headers have been sent (response committed), you cannot arbitrarily change the status as you could before the response began; this is especially important with streaming.

### Step 8 — Pipeline completion and sending the response

Post-processing callbacks of interceptors/filters run according to each layer's rules; the server writes status, headers, and body to the connection (possibly chunked/streaming), any proxy forwards it, and the client reads the response and processes JSON/HTML/files. Tracking end-to-end latency must include network and proxy delays, not just service execution time.

## 5. Runnable Spring Boot MVC example with Java 17+

The example below intentionally uses dummy data to clearly show the **HTTP → controller → service → JSON** path without requiring a database. Create a Gradle project with the structure:

```text
web-runtime-demo/
├── build.gradle
└── src/main/java/com/example/webruntime/WebRuntimeApplication.java
```

Contents of `build.gradle` (Spring Boot 3.3.x, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.7'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Contents of `src/main/java/com/example/webruntime/WebRuntimeApplication.java`:

```java
package com.example.webruntime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class WebRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> find(@PathVariable long id) {
        OrderView result = orderService.findById(id);
        return ResponseEntity.ok(result);
    }
}

@Service
class OrderService {
    public OrderView findById(long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "id must be greater than 0");
        }
        return new OrderView(id, "CONFIRMED");
    }
}

record OrderView(long id, String status) {}
```

Run from the `web-runtime-demo` directory using a Gradle version compatible with Spring Boot 3.3 and JDK 17+:

```bash
gradle bootRun
```

If the project has a Gradle wrapper, use `./gradlew bootRun` on macOS/Linux or `.\gradlew.bat bootRun` on Windows PowerShell. Once the server has started, test calling:

```bash
curl -s http://localhost:8080/api/orders/42
```

Expected JSON body (one line, independent of startup logs):

```json
{"id":42,"status":"CONFIRMED"}
```

In the successful HTTP response, the status is **200** and `Content-Type` is typically `application/json`. The value `42` is converted from the path to `long`; `OrderController.find` calls `OrderService.findById`; the service creates `OrderView`; Spring MVC/Jackson converts the record to JSON. The controller neither opens sockets nor manually constructs HTTP strings.

Try `/api/orders/0`: the service throws `ResponseStatusException` with **400 Bad Request**. Try `/api/orders/abc`: converting `String → long` fails during binding, also typically **400**, and the service never runs. The error response body depends on Spring Boot configuration, so do not assume a fixed error JSON structure. This example does not add Spring Security, so it does not trigger the default authentication step of `spring-boot-starter-security`.

## 6. Where does the path change if using WebFlux?

| Aspect | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Common server | Tomcat (embedded by default with web starter) | Reactor Netty (common with webflux starter) |
| Request model | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange`, `ServerHttpRequest` / `ServerHttpResponse` |
| Common interception layer | Servlet `Filter`; Spring Security filter chain if present | `WebFilter`; reactive security WebFilter chain if present |
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Handler selection & invocation | `HandlerMapping`, `HandlerAdapter` | Reactive `HandlerMapping`, `HandlerAdapter` |
| HTTP result | `HandlerMethodReturnValueHandler`, `HttpMessageConverter`, view resolver | `HandlerResultHandler`, `HttpMessageWriter`, reactive view handling |
| Execution model | Worker threads for synchronous Servlet processing, with async support | Non-blocking I/O, reactive streams and event-loop/scheduler execution |

WebFlux follows this general path:

```text
Client → HTTP server (usually Reactor Netty)
       → HttpWebHandlerAdapter / WebFilter
       → DispatcherHandler → mapping/adapter
       → controller or functional handler
       → service returning Publisher (e.g., Mono/Flux)
       → HandlerResultHandler / HttpMessageWriter
       → HTTP response
```

`Mono<T>` typically represents at most one result; `Flux<T>` can represent multiple elements. Reactor coordinates subscription and emitting data/error/completion signals; the response is written as the data stream is processed. Do not place long blocking calls (such as synchronous JDBC or `Thread.sleep`) directly on Netty event-loop threads: doing so stalls many other requests. If calling a blocking API is unavoidable, offload the work to an appropriate scheduler or use reactive APIs/drivers. Likewise, do not assume WebFlux is automatically faster than MVC across every workload.

The `@RestController` annotation and the controller → service pattern can look identical in both stacks; **the selected HTTP libraries and execution model determine the actual pipeline**. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present in a Spring Boot app, the default usually prioritizes the Servlet/MVC application type unless explicitly configured otherwise.

## 7. How to observe and isolate issues when requests misbehave

Work from the outside in, following the pipeline:

1. **Cannot connect:** check URL, DNS, port, TLS, proxy, and whether the server is listening.
2. **Response received but controller does not run:** check reverse proxy, HTTP method/path, filters/security, 404, 401/403, and binding errors.
3. **Controller executes but result is wrong/slow:** trace bound parameters, service, transactions, DB/API calls, and I/O time.
4. **Service returns correctly but client receives wrong output:** check `ResponseEntity`, serializer, content negotiation, response headers, exception handlers, and streaming/proxy behavior.
5. **Slow only under load:** observe thread pools/connection pools in MVC, event-loop blocking in WebFlux, database pools, queues, and timeouts.

You can propagate a request ID or trace ID across proxy → filter → controller → service, logging durations at each stage. In real applications, metrics/traces (for example via Micrometer/Actuator when configured) help pinpoint which stage consumes time; controller logs alone do not measure the entire request.

## 8. Misconceptions to avoid

- **"The network calls the controller method directly":** the HTTP server must accept the request and the framework must route/bind it first.
- **"Every request enters the service":** filters, security, route mapping, or binding can terminate the request beforehand.
- **"Java objects are returned directly over HTTP":** the framework must encode them into body bytes and determine status and headers.
- **"Filter = Interceptor":** Servlet Filters sit outside `DispatcherServlet`; MVC Interceptors participate in Spring MVC's handler execution.
- **"One request always equals one connection and one thread":** keep-alive, HTTP/2, servlet async, and WebFlux make that assumption untrue in general.
- **"WebFlux is always non-blocking even when calling blocking code":** placing blocking operations on the event loop still causes stalls.
- **"Any error is guaranteed to be caught by `@RestControllerAdvice`":** errors can occur in proxies/filters/servers or after the response is already committed.

**Remember:** an HTTP request travels through **network → server → middleware → dispatcher/routing → controller → service → result processing → server/network → client**. When debugging, determine which stage the request stopped at before hunting for bugs in business logic.