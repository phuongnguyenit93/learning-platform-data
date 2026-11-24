# Distinguishing Spring MVC, Spring WebFlux, and embedded servers

## 1. Objectives and overall picture

When building web applications with Spring Boot, it is important to distinguish between the **HTTP processing framework** and the **software that accepts HTTP connections**:

- **Spring MVC** is a Servlet-based web framework, typically using an imperative programming style (sequential method calls), well-suited for synchronous libraries such as JDBC/JPA.
- **Spring WebFlux** is a reactive web framework designed for asynchronous, non-blocking I/O, commonly using Project Reactor's `Mono<T>` and `Flux<T>` types.
- **Embedded web server** is the component that accepts network connections, reads/writes HTTP, and passes requests into the web framework. Examples: Tomcat, Jetty, Reactor Netty. It is **not** a controller framework.

Spring Boot is responsible for **auto-configuring and starting** the framework together with the corresponding server based on dependencies, configuration, and application type. A program typically runs via `java -jar` without installing an external Tomcat.

```text
Client (browser, curl, mobile app)
           |
       HTTP/TCP
           |
  Embedded HTTP server
  (Tomcat / Jetty / Reactor Netty)
           |
   +-------+-----------------------------+
   |                                     |
Servlet adapter                       Reactive HTTP adapter
   |                                     |
Spring MVC                            Spring WebFlux
DispatcherServlet                     HttpHandler / DispatcherHandler
   |                                     |
Controller -> Service                 Handler -> Mono/Flux -> Service
   |                                     |
HTTP response                         HTTP response
```

These are **two alternative application branches**, rather than a single request automatically passing through both MVC and WebFlux. The diagram is simplified to show responsibility placement; filters, security, handler mappings, and message converters/codecs also sit on the actual processing path.

## 2. Spring MVC: the Servlet-based web stack

**Spring MVC (spring-webmvc)** uses the Servlet API and typically runs on a servlet container such as Tomcat or Jetty.

Typical processing flow:

1. Tomcat/Jetty accepts the connection and forwards the HTTP request to `DispatcherServlet`.
2. `DispatcherServlet` asks `HandlerMapping` to find the controller matching the URL and HTTP method.
3. `HandlerAdapter` invokes the controller method; the controller calls services/repositories.
4. The result is converted into a body (e.g., JSON via `HttpMessageConverter`) or a view; the servlet container sends the response.

In the common synchronous processing model, a request occupies a container worker thread while the controller runs, including when synchronous JDBC or HTTP calls wait on I/O. Thread pools enable handling multiple requests, but thread count and blocking duration are resources that must be managed. **Do not absolutize this as "MVC always blocks one thread from start to finish":** Spring MVC also supports Servlet async, `Callable`, `DeferredResult`, streaming, and certain reactive return types; however, the Servlet foundation and most libraries used still follow a synchronous model.

A familiar behavioral example:

```java
@GetMapping("/users/{id}")
public UserDto getUser(@PathVariable long id) {
    // Abbreviated example: the service may use synchronous JDBC/JPA.
    return userService.findById(id);
}
```

The snippet above is a **controller illustration** and does not run standalone because `UserDto` and `userService` are not defined. It demonstrates sequential calls that are easy to read, debug, and integrate with the blocking ecosystem.

Choosing MVC is usually sensible when the application is a CRUD/business API, uses JPA/JDBC, synchronous transactions, Servlet libraries, or when the team prefers a straightforward imperative model.

## 3. Spring WebFlux: the reactive, non-blocking web stack

**Spring WebFlux (spring-webflux)** does not depend on the Servlet API to define its processing model; it can run directly on Reactor Netty or via a non-blocking adapter on Tomcat/Jetty. WebFlux uses `DispatcherHandler` (instead of `DispatcherServlet`), supporting both annotated controllers and functional endpoints (`RouterFunction`/`HandlerFunction`).

Two fundamental Reactor data types:

- `Mono<T>`: a publisher emitting **0 or 1** element (or an error and completing).
- `Flux<T>`: a publisher emitting **0 to N** elements over time (or an error and completing).

Controllers typically **return a publisher describing the work**; the runtime subscribes during request processing. Non-blocking I/O steps can resume via callbacks/signals when data is ready, instead of holding a thread waiting on the network. **Backpressure** is the mechanism by which a consumer signals data demand to a publisher under Reactive Streams; do not assume every upstream database or HTTP service automatically supports backpressure simply because your code returns a `Flux`.

Typical processing flow:

1. Reactor Netty (commonly used by default) receives requests on event-loop workers.
2. The HTTP adapter passes into WebFlux `HttpHandler`/`WebHandler` and `DispatcherHandler`.
3. The handler returns `Mono`/`Flux`; reactive operators describe processing and coordinate I/O.
4. When data/completion/error signals arrive, the runtime encodes the result and writes the HTTP response asynchronously.

The event loop must be kept unblocked. **Do not call `Thread.sleep(...)`, blocking JDBC/JPA, synchronous HTTP clients, or `.block()` directly on non-blocking processing threads**: they can stall the small number of event-loop threads and impact many requests. When calling a blocking API is unavoidable, isolate the work on an appropriate scheduler, for example:

```java
// Illustrates a method in a controller with configured dependencies:
// blockingService is a bean providing a synchronous API, not included in a standalone example.
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> blockingService.fetch())
            .subscribeOn(Schedulers.boundedElastic());
}
```

You need to import `reactor.core.publisher.Mono` and `reactor.core.scheduler.Schedulers`. `boundedElastic()` is a transitional solution to isolate blocking I/O and **does not make JDBC non-blocking**; if the data path is predominantly blocking, using MVC is usually simpler and more appropriate.

WebFlux excels for services with high concurrent I/O tasks, variable network latencies, streaming, or truly reactive component chains (such as WebClient + reactive drivers like R2DBC). It does not inherently make every request faster: adding publishers/operators incurs overhead, CPU tasks still consume CPU resources, and effectiveness must be measured via throughput, latency, memory, thread count, and real load.

## 4. Embedded server: sitting beneath the framework

An **embedded server** is a server packaged/run alongside the Spring Boot application. When the application starts, Boot creates the server, opens a TCP port (HTTP `8080` by default unless changed), registers adapters/handlers, and manages the server lifecycle. The server receives HTTP; the framework decides routing, invokes controllers, and builds responses.

| Component | Nature | Common pairing |
| --- | --- | --- |
| **Tomcat** | Servlet container and HTTP server | Spring MVC + embedded Tomcat; can also serve WebFlux via adapter |
| **Jetty** | Servlet container and HTTP server | Spring MVC + embedded Jetty; can also serve WebFlux via adapter |
| **Reactor Netty** | Non-blocking HTTP server based on Netty, not a Servlet container | Spring WebFlux + embedded Reactor Netty |
| **Spring MVC** | Servlet-based request processing framework | Runs on a servlet container, typically Tomcat |
| **Spring WebFlux** | Reactive HTTP processing framework | Runs on Reactor Netty, Tomcat, or Jetty |
| **Spring Boot** | Bootstrap, auto-configuration, dependency conventions, operations | Selects and starts the appropriate stack/server |

Therefore, **"Spring MVC = Tomcat" and "Spring WebFlux = Netty" are both imprecise statements**: those are merely the common pairings. Tomcat and Jetty can run WebFlux; Netty does not turn into a Servlet container to run MVC's DispatcherServlet.

```text
Spring MVC  -> Servlet container -> Tomcat / Jetty
Spring WebFlux -> reactive HTTP runtime -> Reactor Netty / Tomcat / Jetty
```

"Embedded" describes **how the server is packaged/operated**, not whether it is blocking or non-blocking. An MVC application can run as an executable JAR with embedded Tomcat; Spring MVC can also be deployed as a WAR onto an external servlet container. Changing the deployment model does not automatically turn MVC into WebFlux.

## 5. Comparison table to make the right decision

| Criterion | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Foundation | Servlet API | Reactive Streams, WebFlux HTTP abstraction; has adapters for Servlet servers |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| Common coding style | Imperative: returns `T`, `ResponseEntity<T>` | Reactive: returns `Mono<T>`, `Flux<T>`; also supports annotated controllers |
| Default I/O in application | Usually blocking; supports Servlet async | Designed to be non-blocking end-to-end if dependencies also support it |
| Common threading model | Request thread pool in Servlet container | Small number of event-loop workers; must not block the event loop |
| Typical data libraries | Spring Data JPA, JDBC (blocking) | R2DBC, reactive drivers, WebClient (non-blocking) |
| Default server in Boot starter | Tomcat | Reactor Netty |
| Streaming | Possible via async/SSE/streaming | `Flux` and reactive streaming are a natural fit |
| Main advantage | Easy to understand, easy to debug, compatible with blocking libraries | Scales to many concurrent I/O connections with few threads when end-to-end non-blocking |
| Trade-offs to consider | Thread pool faces pressure if I/O waits too long | Harder debugging/operator chains; blocking the event loop is dangerous |

There is no rule that "WebFlux is always better than MVC." WebFlux's advantages typically emerge when workloads involve **substantial I/O wait time** and the entire dependency chain supports reactive execution. MVC is usually a solid default for APIs using JPA and traditional business logic.

### Three stack selection scenarios

1. **Order management app with Spring Data JPA/PostgreSQL and synchronous transactions:** favor MVC because the call stack is clear and blocking repositories are the main component.
2. **API gateway aggregating multiple asynchronous HTTP APIs, long-lived connections/streaming, using WebClient and reactive persistence:** WebFlux is worth considering, followed by benchmarking with real data.
3. **CPU-bound heavy computation service:** do not pick WebFlux expecting faster execution; design concurrency limits, CPU allocation, and appropriate queues/executors in either stack.

## 6. Two runnable examples with Java 17+

The two examples are **two separate Spring Boot Maven projects**, each choosing only **one** web starter. Create the projects from https://start.spring.io/ with Maven, Java 17 or later, and the same package `com.example.demo`. For **Spring Boot 4.x**, the MVC project dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
```

For **Spring Boot 3.x**, the corresponding common MVC starter is `spring-boot-starter-web`. The WebFlux project on Boot 3.x/4.x uses:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

These dependency snippets belong inside `<dependencies>` in the `pom.xml` generated by Initializr; they are **not the entire POM**. Keep the Spring Boot parent, Maven plugin, and wrapper generated by Initializr for proper version management.

### 6.1. Project A — MVC with embedded Tomcat

Create the file `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello MVC";
    }
}
```

Run from the Maven project root directory:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell, use `.\mvnw.cmd spring-boot:run`. In another terminal, call:

```bash
curl -s http://localhost:8080/hello
```

The received HTTP response body is `Hello MVC`. With the default MVC starter, Boot starts Tomcat and places `DispatcherServlet` in the request-processing pipeline.

### 6.2. Project B — WebFlux with embedded Reactor Netty

Create a **second project** (do not swap starters while Project A is running on the same port), using the `spring-boot-starter-webflux` starter and the same Java file path in Project B:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
```

Run `./mvnw spring-boot:run` (PowerShell: `.\mvnw.cmd spring-boot:run`), then:

```bash
curl -s http://localhost:8080/hello
```

The HTTP response body is `Hello WebFlux`. Netty listens for HTTP; WebFlux executes the handler returning `Mono<String>`. With an immediate response like `Mono.just(...)`, you cannot conclude WebFlux will be faster than MVC; this example aims to distinguish **programming style and runtime**.

If you want to run **both projects simultaneously**, set `src/main/resources/application.properties` of one project to:

```properties
server.port=8081
```

Then call that project with `curl -s http://localhost:8081/hello`. Both MVC and WebFlux support configuring `server.port` when running on a Boot-managed embedded server.

### 6.3. Understanding `Flux` and streaming correctly

In the WebFlux project, you can add an endpoint to the controller class in section 6.2 (the following snippet is **an additional method only**, not a standalone Java class):

```java
@GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Long> ticks() {
    return Flux.interval(Duration.ofSeconds(1)).take(3);
}
```

Add imports `java.time.Duration`, `org.springframework.http.MediaType`, and `reactor.core.publisher.Flux`. Running `curl -N http://localhost:8080/ticks` will receive SSE events carrying values `0`, `1`, `2` over time (exact timing depends on scheduling). `Flux.interval` emits asynchronous signals; this is a small streaming example, not benchmark evidence.

## 7. How does Spring Boot choose the stack and server?

For typical web applications:

- Only MVC starter present: Boot configures a **SERVLET** web application, creates a servlet web server and `DispatcherServlet`; Tomcat is the starter's default choice.
- Only WebFlux starter present: Boot configures a **REACTIVE** web application, creates a reactive web server and the WebFlux HTTP pipeline; Reactor Netty is the starter's default choice.
- **Both MVC and WebFlux** on the classpath: Boot usually defaults to configuring **Spring MVC/Servlet**, because an MVC application may add WebClient support. **Merely having `Mono`, `Flux`, or WebClient in code does not prove the server is running WebFlux**. If you genuinely need a reactive web application, check dependencies and explicitly configure the web application type, such as `spring.main.web-application-type=reactive` in the appropriate configuration.

Server configuration option:

```properties
# Usually defaults to 8080; change when required:
server.port=8081
```

Swap servers by **excluding the default server dependency and adding the desired server dependency** (for example, excluding Tomcat and adding Jetty for MVC, or excluding Reactor Netty and adding Tomcat/Jetty for WebFlux). This changes the **server transport**, not necessarily the web framework. Use the dependency tree to verify which server is on the classpath; inspect startup logs to identify which server actually starts.

When packaging with the Maven wrapper:

```bash
./mvnw clean package
java -jar target/<built-artifact-name>.jar
```

The `java -jar` command above is a **command template**; replace `<built-artifact-name>` with the exact JAR name produced by Maven (without typing the placeholder angle brackets). On Windows, replace `./mvnw` with `.\mvnw.cmd`. An executable JAR typically contains the application along with its required dependencies/server; there is no need to install a system Tomcat just to run an MVC project with embedded Tomcat.

## 8. Common misconceptions and pitfalls

| Misconception / issue | Correct fact and how to verify |
| --- | --- |
| "MVC is Tomcat, WebFlux is Netty." | MVC/WebFlux are frameworks; Tomcat/Jetty/Netty are servers. WebFlux can also run on Tomcat/Jetty. |
| "Adding `Mono` to MVC converts the entire app to WebFlux." | MVC supports some reactive return types; the runtime may still be `DispatcherServlet`. Check the starter and application type. |
| "Reactive means every statement is automatically non-blocking." | If you use synchronous JDBC/JPA or `.block()` directly on the event loop, requests still block threads. |
| "WebFlux always achieves higher throughput." | Benchmark realistically and factor in framework overhead, I/O wait ratio, database, CPU, connection count, and memory. |
| "The embedded server is what makes an API reactive." | Embedded only describes how the server is run/packaged; reactive behavior depends on WebFlux and the full I/O chain. |
| "You must install Tomcat separately to run Spring MVC." | Embedded Tomcat inside an executable Boot JAR can run standalone; an external container is an alternative option. |
| "Both projects fail to start on `8080`." | Two processes cannot bind the same address/port; change `server.port` in one project, or stop the other project. |
| "WebFlux should call blocking APIs on the event loop for convenience." | Use non-blocking drivers; if unavoidable, isolate blocking calls onto an appropriate scheduler, measure impact, and monitor pools. |

**How to verify the runtime yourself:** inspect `pom.xml`/`build.gradle` and the dependency tree; read startup logs reporting Tomcat/Jetty/Netty; check for `DispatcherServlet` (MVC) vs. `DispatcherHandler` (WebFlux); test the endpoint with `curl`. **Do not conclude solely from `@RestController`**, as both stacks support annotation-based controllers.

## 9. Self-check questions

1. An API uses Spring Data JPA with controllers returning `UserDto`: should you start with MVC or WebFlux? **MVC**, because persistence is blocking and the imperative style fits well.
2. Does Spring WebFlux require Netty? **No**. WebFlux runs on Reactor Netty and via corresponding adapters on Tomcat/Jetty.
3. Does embedded Tomcat mean the application is always Spring MVC? **No**. Tomcat is a server/Servlet container and can also serve WebFlux.
4. Why can `Thread.sleep(3000)` inside a WebFlux handler be severe? **Because it blocks an event-loop worker**, delaying other requests sharing that thread.
5. When adding WebClient to an MVC application, does the HTTP server stack automatically become WebFlux? **No**. You can use the reactive client inside an MVC app; check the web application type Boot actually configures.
6. What are the signals for choosing WebFlux? **Many asynchronous I/O/streaming tasks, reactive dependencies end-to-end, and measured scaling needs**, not merely the "reactive" label.

## 10. Official references

- Spring Framework — [Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- Spring Framework — [WebFlux overview, servers, performance, and concurrency](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- Spring Boot — [Web applications and starters](https://docs.spring.io/spring-boot/reference/web/index.html)
- Spring Boot — [Reactive web applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- Spring Boot — [Embedded web servers](https://docs.spring.io/spring-boot/how-to/webserver.html)

**Remember:** choose **MVC or WebFlux** based on the I/O processing model and library ecosystem; choose **Tomcat, Jetty, or Reactor Netty** based on the appropriate runtime/server. Spring Boot is the layer that automatically assembles and operates those components.