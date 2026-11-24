# WebClient in MVC and Its Impact on Web Application Type Selection

## 1. Distinguishing the HTTP Client from the HTTP Server

In **Spring Boot**, `WebClient` is a **reactive HTTP client** from the Spring WebFlux module. It is used to **send requests to other services**. By contrast, Spring MVC and Spring WebFlux are two models for handling **inbound requests entering the server**. Therefore, **a Spring MVC application can use WebClient while remaining a Servlet application**.

A common scenario: a project has **spring-boot-starter-web** to run MVC, and then adds **spring-boot-starter-webflux** just to get `WebClient`. Spring Boot 3.3 **prefers Spring MVC** when both Spring MVC and WebFlux are on the classpath. The default server remains **Tomcat/DispatcherServlet**, while `WebClient` can use the **Reactor Netty HTTP client** for outbound HTTP requests.

Do not conflate three independent axes:
1. **WebApplicationType**: Does Boot select `SERVLET`, `REACTIVE`, or `NONE` for the server runtime?
2. **Outbound client**: Does the application call REST APIs using `WebClient`, `RestClient`, `RestTemplate`, or another library?
3. **Controller return type**: Synchronous DTOs, `Mono`/`Flux`, or Servlet async abstractions?

**A Controller returning `Mono` does not automatically turn MVC into WebFlux.** Spring MVC supports reactive return types via Servlet asynchronous processing. This lesson explains the framework's decision logic, two ways to use `WebClient` in MVC, when `block`/`subscribe` happen, how to handle timeouts, and how to verify everything yourself with a Java 17 application.

Example scope: **Spring Boot 3.3.13, Spring Framework 6.1.x, Spring MVC/Servlet, Spring WebFlux WebClient, Project Reactor, and Java 17+**.

## 2. Comparing Components Accurately

| Component | Responsibility | Determines server type? |
| --- | --- | --- |
| Spring MVC | Handles inbound HTTP via Servlet and `DispatcherServlet` | Yes, MVC stack |
| Spring WebFlux | Handles inbound HTTP via the reactive web stack | Yes, WebFlux stack |
| WebClient | Sends outbound HTTP requests using a reactive API | **No** |
| RestClient | Sends outbound HTTP requests using an imperative API | **No** |
| Mono<T> | Publisher emitting at most one value, or an error/completion | **No** |
| Flux<T> | Publisher emitting zero to many values, or an error/completion | **No** |
| Reactor Netty | Can run an HTTP client or an HTTP server | Depends on actual role |
| Embedded Tomcat | Default Servlet HTTP server of `starter-web` | Usually indicates an MVC server |

**Spring MVC** uses Servlet request threads while also supporting `DeferredResult`, `Callable`, `CompletionStage`, and `Mono`/`Flux` through async adapters. **Spring WebFlux** is built on Reactive Streams, featuring `DispatcherHandler` and reactive-server non-blocking I/O. Both can use `WebClient` to call other services.

### 2.1. Request Flow in MVC + WebClient

~~~text
External client
      |
      v
Tomcat Servlet HTTP server
      |
      v
Spring MVC DispatcherServlet
      |
      v
MVC Controller
      |
      +---- WebClient -> Reactor Netty HTTP client -> Service B
      |                              |
      |                              v
      |                        Mono<Response>
      |
      +---- If calling block(): Servlet worker waits for HTTP response
      |
      +---- If returning Mono: MVC uses Servlet async handling
      |
      v
HTTP response sent back to client
~~~

This diagram has **no WebFlux HTTP server**. Reactor Netty may appear solely as the `WebClient` HTTP client connector. Having reactive libraries on the classpath does not change how `DispatcherServlet` processes inbound requests.

## 3. How Spring Boot Chooses the Web Application Type with Both Starters

Spring Boot 3.3 auto-detection rules:

| Dependencies at runtime | Default choice | Typical runtime |
| --- | --- | --- |
| Only `starter-web` | **SERVLET** | MVC + Tomcat |
| Only `starter-webflux` | **REACTIVE** | WebFlux + Reactor Netty |
| **starter-web and starter-webflux** | **SERVLET** | MVC + Tomcat; WebClient available |
| No matching web stack | Usually `NONE` | Does not start an HTTP server |
| Both, but explicitly forced reactive | `REACTIVE` per configuration | Requires verifying WebFlux migration |

A commonly misunderstood point: adding `starter-webflux` to MVC to use `WebClient` is a scenario **anticipated by Spring Boot**, not a design flaw requiring removal of `starter-web`.

### 3.1. Explicitly Declaring the Web Application Type

To lock in MVC:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

To switch intentionally to a WebFlux server:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Or at bootstrap:

~~~java
// Fragment when explicitly choosing runtime type; requires imported classes.
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

**MyApplication** is an illustrative name; the fragment does not compile standalone. Do not force `reactive` just to use `WebClient`. Forcing reactive changes server request processing and may break Servlet integrations.

### 3.2. How to Verify Accurately

In a Boot MVC app, the application context is typically an implementation of **ServletWebServerApplicationContext**; in WebFlux it is **ReactiveWebServerApplicationContext**. You can also check:
- Is **DispatcherServlet** or **DispatcherHandler** handling inbound requests?
- Is the listening HTTP server Tomcat or Reactor Netty?
- Do security beans use `HttpSecurity`/`SecurityFilterChain` or `ServerHttpSecurity`/`SecurityWebFilterChain`?
- Do production or test configs force `spring.main.web-application-type` differently across environments?

Do not just look at a log line saying Reactor Netty initialized; it may belong to the outbound client.

## 4. Adding WebClient to an MVC App with Maven

In a Maven project:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**starter-web** brings in MVC/Servlet container. **starter-webflux** provides `WebClient`, Reactor, codecs, and the default Reactor Netty connector. With both present, Boot still selects MVC. You can selectively include `spring-webflux` and an HTTP connector to keep the classpath minimal, provided client runtime and codecs remain compatible.

### 4.1. Boot-Configured WebClient.Builder

Spring Boot creates a **WebClient.Builder** with appropriate framework configuration applied. The builder has prototype scope, yet it is a **mutable builder**: reusing the exact same builder object for multiple clients can leak mutations into later builds.

~~~java
// Fragment inside a service with a WebClient client field.
public PartnerClient(WebClient.Builder builder) {
    this.client = builder.baseUrl("https://partner.example.test")
            .build();
}
~~~

Prefer injecting **WebClient.Builder** instead of calling `WebClient.create()` on every request so you retain Boot customizers, codecs, resource management, and client reuse. For distinct base URLs or headers, use separate builder instances or `builder.clone()`.

### 4.2. When Does RestClient Make More Sense?

Spring Framework 6.1 introduced **RestClient**, an **imperative** fluent API. If an MVC controller only needs a simple synchronous HTTP call without reactive composition or streaming, `RestClient` can be clearer than `WebClient` + `block()`.

~~~java
// Fragment: builder has type RestClient.Builder, not WebClient.Builder.
RestClient client = builder.baseUrl("https://partner.example.test")
        .build();

Customer result = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .body(Customer.class);
~~~

**Customer** is an application-defined DTO. The fragment needs imports, an enclosing class, and the `id` variable; it is not a standalone program. `RestClient` avoids pulling reactive APIs into completely synchronous business flows unnecessarily.

## 5. Two Ways to Use WebClient from a Spring MVC Controller

### 5.1. Approach A: Waiting for the Result with block()

~~~java
// Fragment in an MVC Controller; client, Greeting, and imports exist.
@GetMapping("/sync")
Greeting sync() {
    return client.get()
            .uri("/hello")
            .retrieve()
            .bodyToMono(Greeting.class)
            .block(Duration.ofSeconds(4));
}
~~~

When running on a **Tomcat Servlet request worker**, `block()` can be used at an imperative boundary if the controller intentionally waits synchronously for one result. This is **not an absolute ban** for every MVC app.

Trade-offs:
- The Servlet thread is occupied while the upstream is slow.
- High load can exhaust the thread pool and spike tail latency.
- Sequential `block()` calls add up their wait times.
- Timeouts, error handling, and concurrency/pool limits are mandatory.
- Calling `block()` multiple times on a cold Publisher can trigger multiple HTTP requests.

**Note:** calling `block()` on a **Reactor Netty event-loop** inside a reactive pipeline is a serious bug; Reactor can throw `IllegalStateException` for blocking on a `NonBlocking` thread.

### 5.2. Approach B: Returning Mono to Spring MVC

~~~java
// Fragment in an MVC Controller; Spring MVC manages the async result.
@GetMapping("/async")
Mono<Greeting> async() {
    return client.get()
            .uri("/hello")
            .retrieve()
            .bodyToMono(Greeting.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

Spring MVC uses **ReactiveAdapterRegistry** to process single-value Publishers similarly to **DeferredResult**:
1. The controller returns `Mono`.
2. MVC registers Servlet asynchronous request processing.
3. The request thread can be returned to the container while waiting on the upstream.
4. When the `Mono` completes or errors, MVC performs an async dispatch and writes the response.
5. **The application type remains SERVLET.**

This model helps when many requests wait on HTTP I/O. Still, an MVC app returning `Mono` **does not become non-blocking end-to-end**: JDBC/JPA, Servlet filters, data binding, and response writes may still block.

### 5.3. Never Subscribe Manually and Return Immediately

~~~java
// ANTI-PATTERN for an endpoint that must return the upstream result.
@GetMapping("/wrong")
String wrong() {
    client.get().uri("/hello").retrieve()
            .bodyToMono(String.class)
            .subscribe(System.out::println);
    return "done";
}
~~~

The endpoint returns **done** before the upstream finishes. Errors, cancellation, and response lifecycle are severed from the HTTP request. For endpoints that need the result, **return Mono** and let the framework subscribe, or **block with bounds** at a synchronous boundary. True background jobs should use a durable queue/workflow with state rather than ad-hoc `subscribe()` in a controller.

### 5.4. Flux in MVC Does Not Stream Identically to WebFlux by Default

- `Mono<T>` in MVC: single value, similar to `DeferredResult`.
- `Flux<T>` with a streaming media type such as **text/event-stream** or NDJSON: MVC can use an emitter mechanism.
- `Flux<T>` with standard **application/json**: may collect elements into a list before writing the response.
- Servlet output writes can block and run on a separate thread executor when streaming.

Therefore, **returning Flux** does not prove all response writes are non-blocking. Production MVC streaming requires proper async executor and timeout tuning.

## 6. Runnable Maven Demo: Two Starters, Still an MVC Server

This hands-on lab contains an internal upstream endpoint and two proxy endpoints for comparison. The upstream lives **in the same application** only to avoid needing a separate service. This is **not a production architecture**: self-calls under load can starve the Servlet worker pool, especially with `block()`.

### 6.1. Project Structure

~~~text
mvc-webclient-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/mvcclient/
    │   └── MvcWebClientApplication.java
    └── resources/application.yml
~~~

### 6.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-webclient-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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

The two starters bring in both MVC and WebFlux libraries, yet Boot **does not** launch both Tomcat and a Reactor Netty server simultaneously under default config.

### 6.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s

demo:
  upstream-url: http://localhost:8080
~~~

The property **demo.upstream-url** is custom client configuration. **spring.mvc.async.request-timeout** governs the Servlet async request lifecycle and does not replace `WebClient` connect/response timeouts.

Do not set `spring.main.web-application-type` in the lab so you can observe Boot's default auto-selection.

### 6.4. Complete Single-File Java Code

**src/main/java/com/example/mvcclient/MvcWebClientApplication.java:**

~~~java
package com.example.mvcclient;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MvcWebClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcWebClientApplication.class, args);
    }

    public record Greeting(String message) {}
}

@Configuration
class ClientConfig {
    @Bean
    WebClient upstreamClient(WebClient.Builder builder, Environment env) {
        String url = env.getRequiredProperty("demo.upstream-url");
        return builder.baseUrl(url).build();
    }
}

@RestController
class DemoController {
    private final WebClient client;
    private final ApplicationContext context;

    DemoController(WebClient client, ApplicationContext context) {
        this.client = client;
        this.context = context;
    }

    @GetMapping(path = "/api/runtime",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String runtime() {
        return context instanceof ServletWebServerApplicationContext
                ? "SERVLET/MVC\n" : "OTHER\n";
    }

    // Mock upstream endpoint on the same MVC server.
    @GetMapping(path = "/upstream/hello/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    MvcWebClientApplication.Greeting upstream(
            @PathVariable String name
    ) {
        return new MvcWebClientApplication.Greeting("hello " + name);
    }

    private Mono<MvcWebClientApplication.Greeting> fetch(String name) {
        return client.get()
                .uri("/upstream/hello/{name}", name)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(MvcWebClientApplication.Greeting.class)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Empty upstream body")
                ))
                .timeout(Duration.ofSeconds(3));
    }

    @GetMapping(path = "/api/blocking/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    MvcWebClientApplication.Greeting blocking(
            @PathVariable String name
    ) {
        return fetch(name).block(Duration.ofSeconds(4));
    }

    @GetMapping(path = "/api/async/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<MvcWebClientApplication.Greeting> async(
            @PathVariable String name
    ) {
        return fetch(name);
    }
}
~~~

**Analysis:**
- Boot automatically selects Servlet/MVC. The code does not explicitly enable a WebFlux server.
- **WebClient.Builder** comes from Boot, and the client is built once in a `@Bean` instead of per request.
- **Environment** reads the configured upstream base URL.
- **/api/runtime** directly verifies the active application context type.
- **/upstream/hello** returns a Java 17 record, serialized to JSON by Jackson from `starter-web`.
- **fetch()** returns a lazy `Mono`; `switchIfEmpty` turns an empty body into an explicit error, and `timeout(3s)` sets a Publisher deadline.
- **/api/blocking** calls `block(Duration)` on the Servlet worker. If the upstream is slow, the worker waits.
- **/api/async** returns `Mono`; Spring MVC handles subscription and the async result.
- No manual `subscribe()` is called; error signals flow down the pipeline and can be handled by an MVC exception handler.
- In production, point the upstream URL to a separate service and never use self-calls.

Note: **fetch timeout of 3 seconds** and **block timeout of 4 seconds** do not replace connect timeout, TCP read timeout, pool acquisition timeout, or proxy timeouts. When errors occur, the demo may return the default error response; Section 9 explains status mapping.

### 6.5. Running Maven and curl

From the **mvc-webclient-demo** directory, with JDK 17+, Maven, and port 8080 free:

~~~bash
mvn package
java -jar target/mvc-webclient-demo-1.0.0.jar
~~~

Open another terminal and run:

~~~bash
curl -s http://localhost:8080/api/runtime
~~~

Expected body:

~~~text
SERVLET/MVC
~~~

~~~bash
curl -s http://localhost:8080/upstream/hello/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

~~~bash
curl -s http://localhost:8080/api/blocking/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

~~~bash
curl -s http://localhost:8080/api/async/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

Identical JSON results do not prove identical execution models. The **blocking endpoint** waits on a Servlet thread; the **async endpoint** returns `Mono` for MVC to process via the Servlet async lifecycle. On Windows PowerShell, use **curl.exe** if needed to avoid the `curl` alias syntax differences. With `curl -i`, stdout also includes HTTP headers; the output above shows the response body.

### 6.6. Verifying the Runtime with Spring Boot Test

Add the test dependency if you want automated verification:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This is a **fragment** added to `<dependencies>` in the existing `pom.xml`. Create **src/test/java/com/example/mvcclient/WebTypeTest.java**:

~~~java
package com.example.mvcclient;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebTypeTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebClient.Builder webClientBuilder;

    @Test
    void mvcWinsAndWebClientIsStillAvailable() {
        assertInstanceOf(ServletWebServerApplicationContext.class, context);
        assertNotNull(webClientBuilder);
    }
}
~~~

Run **mvn test**. If the context starts successfully, the test proves **ServletWebServerApplicationContext** is active and **WebClient.Builder is still injectable**. This test does not call the outbound `localhost:8080` URL, so it does not depend on the mock upstream port, and `RANDOM_PORT` avoids colliding with the configured server port.

**Do not** assume fixed Maven stdout; Maven logs and dependency downloads vary by environment.

## 7. What Does "Reactive WebClient" Mean When Used with MVC?

`WebClient` returns **Mono/Flux** following the Publisher model. Creating a Publisher does not necessarily fire an HTTP request immediately; with standard `WebClient`, the request begins on **subscription**.

~~~java
// Fragment illustrating an unconsumed Publisher.
Mono<Customer> customer = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .bodyToMono(Customer.class);
~~~

- **block()** subscribes and waits for the result.
- **returning Mono** in MVC lets the framework own subscription and lifecycle.
- Manual **subscribe()** inside a Controller normally severs the link to the HTTP response.
- Two subscriptions on a cold Publisher can trigger two HTTP calls.
- **map/flatMap/zip** compose the pipeline without necessarily blocking a Servlet thread.

### 7.1. Combining Two API Calls with Mono.zip

~~~java
// Fragment; Customer/Balance/CustomerView DTOs are app-defined.
Mono<Customer> customer = customerClient.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .bodyToMono(Customer.class);

Mono<Balance> balance = balanceClient.get()
        .uri("/balances/{id}", id)
        .retrieve()
        .bodyToMono(Balance.class);

Mono<CustomerView> view = Mono.zip(customer, balance)
        .map(tuple -> new CustomerView(
                tuple.getT1(),
                tuple.getT2()
        ));
~~~

Both Publishers can be subscribed to together and run HTTP requests concurrently, reducing sequential wait times. However, **Mono.zip requires values from both**; if either Publisher completes empty, the combined `Mono` may also emit nothing. You still need concurrency limits, clear error handling, and timeouts. Do not treat `zip` as a guarantee that side effects succeed atomically together.

## 8. Blocking, Event Loops, and MVC Async

### 8.1. What Happens When Blocking on the Wrong Thread?

In WebFlux/Reactive Netty code running on a `NonBlocking` event loop, calling `block()` can throw:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

This is a **sample error**; exact thread names and stack traces vary. Do not fix it by disabling checks or wrapping blocking calls directly inside `map()`. Keep the pipeline reactive using `flatMap` and returning `Mono`.

If a reactive path must invoke a legacy blocking API, offload the work to a bounded scheduler:

~~~java
// Fragment for a legacy blocking API, not a standalone program.
Mono<LegacyData> data = Mono.fromCallable(
        () -> legacyService.load(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

This **isolates blocking**; it does not make the API non-blocking. For JPA/JDBC and `ThreadLocal`-bound transactions, separately evaluate transaction boundaries, context propagation, latency, and pool capacity.

### 8.2. MVC Async Does Not Eliminate All Blocking

When MVC returns `Mono`, the Servlet thread can return to the pool while waiting. However:
- Writing responses through Servlet APIs can block.
- Async dispatch still requires a container thread to finish the request.
- JSP, file I/O, JDBC, Servlet filters, and some middleware remain blocking.
- `Flux` streaming in MVC needs a capable `AsyncTaskExecutor`; the default executor may be unsuitable for high production concurrency.
- Context propagation across thread hops does not automatically match a synchronous method call.

Therefore, measure **Tomcat threads, event-loop/client connection pools, GC, async requests, latency, and throughput**. Never conclude "performance will be better" solely from a `Mono` return signature.

### 8.3. Self-Calls in the Lab Can Severely Starve Threads

If Tomcat has very few worker threads and many requests to **/api/blocking** hold all threads waiting for **/upstream/hello** in the same process, the upstream has no threads left to respond. Even a simple self-call topology can cause starvation while the `WebClient` connector itself is healthy. Production must separate services, enforce deadlines, and never require an in-flight request to wait on the same thread-starved server.

## 9. Handling Status Codes, Errors, and Timeouts

### 9.1. retrieve() Does Not Automatically Copy Upstream Statuses

`WebClient`'s **retrieve()** treats HTTP 4xx/5xx as errors by default and typically emits **WebClientResponseException**. If an MVC controller does not map that error, the external client may receive a generic server error. Never assume an upstream 404 automatically becomes HTTP 404 from your controller.

You can customize it:

~~~java
// Fragment: HttpStatusCode and Mono must be imported.
Mono<Customer> data = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> Mono.error(
                        new IllegalStateException("Upstream unavailable")
                )
        )
        .bodyToMono(Customer.class);
~~~

This is a policy-illustration fragment without the `Customer` class. Real apps need `@RestControllerAdvice`/exception mapping aligned with the API contract: upstream 5xx may become 502/503; timeouts may become 504; upstream 404 may become 404 or a business error depending on semantics.

### 9.2. exchangeToMono for Custom Response Branches

~~~java
// Fragment controlling decoding per HTTP status.
Mono<Customer> result = client.get()
        .uri("/customers/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Customer.class);
            }
            return response.createException()
                    .flatMap(error -> Mono.error(error));
        });
~~~

**exchangeToMono** suits cases where behavior depends on status/headers. You must read or release the response body per contract to avoid resource/connection leaks. Do not carelessly switch to the legacy `exchange()` API and forget body handling.

### 9.3. Multi-Layered Timeouts

| Type | Where | Scope |
| --- | --- | --- |
| TCP connect timeout | HTTP client connector | Establishing the TCP connection |
| Response/read timeout | Reactor Netty/client connector | Waiting for HTTP response data |
| `Mono.timeout` | Reactor pipeline | Time for Publisher completion |
| `block(Duration)` | Imperative thread | How long the caller waits |
| `spring.mvc.async.request-timeout` | Spring MVC/Servlet | How long an async request is held |
| Ingress/gateway timeout | Proxy layer | How long the proxy waits for upstream |

Reactor Netty connector configuration example:

~~~java
// Fragment requiring HttpClient, ChannelOption, ReactorClientHttpConnector.
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = builder
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://api.example.test")
        .build();
~~~

**Do not treat `responseTimeout` as the total deadline across all phases**, and do not treat `Mono.timeout` as a replacement for connect timeout. Customizing the connector can change how Boot manages resources and metrics, so test pool/connection lifecycles. If a gateway returns 504 before `WebClient` times out, tune deadlines end-to-end instead of raising a single property.

### 9.4. Payload Size and Streaming

`WebClient` uses codecs with memory caps for decoding payloads. Oversized responses can throw **DataBufferLimitException**. Do not increase the buffer limit unboundedly, as concurrent requests can blow up the heap. For large files or streams, use streaming APIs, bound body sizes, and choose appropriate backpressure/memory strategies.

### 9.5. Cancellation and Retries

When a client disconnects or `Mono` times out/cancels, the subscription may cancel, yet the upstream **may already have executed side effects**. For a POST creating an order or payment, retrying can repeat the action. Retry only when the API is idempotent or protected by an idempotency key/policy. Never treat cancellation as rolling back an already-executed upstream transaction.

## 10. Outbound WebClient Security

`WebClient` opens network connections from the backend to a target. It poses security risks even when inbound controllers authenticate users.

### 10.1. SSRF from User-Controlled URLs

~~~java
// Anti-pattern: never let users freely control the full URL.
@GetMapping("/fetch")
Mono<String> unsafe(@RequestParam String url) {
    return WebClient.create()
            .get().uri(url)
            .retrieve().bodyToMono(String.class);
}
~~~

**Server-Side Request Forgery (SSRF)** risk: an attacker tricks the backend into calling internal networks, metadata services, or restricted endpoints. Use fixed/allowlisted upstream base URLs, validate paths/queries, and restrict redirects and egress by policy. Never pass user-supplied URLs as arbitrary destinations.

### 10.2. Do Not Forward All Authorization/Cookies Upstream

A client may send **Authorization**, **Cookie**, **Host**, or **X-Forwarded-*** on the inbound request. Do not forward all of them to every upstream:
- Credentials intended for service A may not be valid or safe for service B.
- Browser session cookies are not service-to-service tokens.
- Forwarding wrong headers can confuse downstream origin/identity checks.
- Logging raw headers can leak credentials.

When identity propagation is needed, use explicit token exchange/delegation policies and standard tracing context. Protect HTTPS, verify certificates/hostnames, and never build a trust-all TLS client just to silence handshake errors.

### 10.3. Context Propagation

Spring MVC relies heavily on **SecurityContextHolder, RequestContextHolder, and MDC** backed by `ThreadLocal`. Reactor callbacks running on different threads do not automatically inherit those `ThreadLocal`s. **Reactor Context differs from ThreadLocal.** Use appropriate context propagation/Observation mechanisms and test across async boundaries; never assume JPA transactions or `SecurityContext` automatically carry into every callback.

## 11. If Migrating Fully to WebFlux, What Changes?

Switching web application type is a **server stack migration**, not swapping an HTTP client.

| Area | Spring MVC/Servlet | Spring WebFlux |
| --- | --- | --- |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| Request context | `HttpServletRequest` / `HttpServletResponse` | `ServerWebExchange` / `ServerHttpRequest` |
| Web configuration | `WebMvcConfigurer` | `WebFluxConfigurer` |
| Servlet Filter | `Filter`/`OncePerRequestFilter` | `WebFilter` |
| Security | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| Multipart upload | `MultipartFile` / `jakarta.servlet.http.Part` | `FilePart` / reactive `Part` |
| Async response | `DeferredResult`, `Mono` adapter, Servlet async | Reactive server pipeline |
| Database integrations | JDBC/JPA typically blocking | Needs reactive adapter or blocking isolation |
| Outbound calls | `RestClient`/`WebClient` | `WebClient` |

If code still depends on Servlet Filters, `HttpSession`, `MultipartFile`, JSP, or blocking JPA calls on the request path, forcing `reactive` breaks prior assumptions. Audit every feature, security rule, transaction, trace, error handler, and regression test. Typically you should **remove `starter-web`** once committing to WebFlux to avoid classpath ambiguity.

A test wanting to **force WebFlux** can use:

~~~java
// Test fragment for projects genuinely targeting the reactive runtime.
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive"
)
class ReactiveAppTest {
}
~~~

This configuration makes the **test context reactive** as requested; it is not how to test an MVC + WebClient production app accurately. For MVC, verify `ServletWebServerApplicationContext` as shown in Section 6.

## 12. When to Pick MVC + WebClient, MVC + RestClient, or WebFlux?

**MVC + RestClient** usually fits imperative business code with heavy JPA/JDBC, a few synchronous HTTP calls, and no complex streaming/composition needs. Call stacks and error handling remain straightforward.

**MVC + WebClient + block** fits when WebClient is already in place, code must interoperate with imperative flows, and traffic scale does not cause network waits to exhaust threads. Bound `block` durations explicitly and measure real concurrency.

**MVC + WebClient + return Mono** fits when the app waits on considerable outbound HTTP I/O and wants to free Servlet workers while waiting without leaving the MVC ecosystem. Understand Servlet async, context propagation, blocking response writes, and `AsyncTaskExecutor`.

**WebFlux + WebClient** makes sense when end-to-end reactive processing, high I/O concurrency, and compatible data/security/integration layers are genuinely needed. Never choose it merely to use a modern HTTP client.

No single choice wins for every workload. Compare p95/p99 latency, concurrency, resource utilization, error rates, complexity, and operability using realistic load tests.

## 13. Quick Error and Diagnostics Reference

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Added `starter-webflux` yet server is still Tomcat | Boot prioritizes MVC when both starters are present | Check the context; usually intended |
| `WebClient.Builder` cannot be injected | Missing dependencies or Boot conditions | Check Maven tree and bean auto-config |
| Reactor Netty appears without a WebFlux server | Netty is the outbound client connector | Check server port and Servlet context |
| Controller returns `Mono` but still runs MVC | MVC supports reactive return types | Valid by design; no need to force reactive |
| `block()` fails on `reactor-http-nio` | Blocking on the event loop | Compose `Mono`/`Flux`, do not block |
| MVC blocking controller slows when upstream degrades | Servlet threads are held | Timeouts, concurrency limits, return `Mono`, or `RestClient` |
| Upstream returns 404, proxy API returns 500 | Unmapped `WebClientResponseException` | Add explicit domain error mapping |
| HTTP 504 before app deadline expires | Proxy timed out earlier than app | Align timeouts |
| Upstream receives duplicate HTTP calls | Cold Publisher subscribed twice | Check `block`/`subscribe`/retries |
| Response returns before upstream finishes | Manual `subscribe()` | Return `Mono` or manage background jobs separately |
| MVC `Flux` streaming still holds threads | Blocking Servlet output writes | Configure `AsyncTaskExecutor` and load-test |
| Codec `DataBufferLimitException` | Large response buffer | Stream, cap payloads, size buffers sensibly |
| Lost request/security context in callbacks | `ThreadLocal` does not auto-propagate | Configure framework context propagation |
| App forced reactive but Servlet security stopped running | Wrong `SecurityFilterChain` stack | Migrate to WebFlux security |
| Localhost self-call times out under high load | Tomcat worker pool exhausted | Remove self-call; separate upstream |

## 14. Reinforcement Questions

**1. When both `starter-web` and `starter-webflux` are present, which framework does Boot 3.3 choose by default for inbound HTTP requests?**  
Spring MVC/SERVLET, typically embedded Tomcat.

**2. Does seeing Reactor Netty in the dependency tree prove the server is Netty?**  
No. It may simply be `WebClient`'s HTTP client connector.

**3. Does `WebClient` force controllers to return `Mono`?**  
No. In MVC you can call `block()` at a synchronous boundary, provided you set timeouts and account for thread costs.

**4. Does an MVC controller returning `Mono` automatically become a WebFlux controller?**  
No. MVC uses a Servlet async adapter.

**5. Why avoid `block()` on `reactor-http-nio`?**  
It is a non-blocking event-loop thread; Reactor may forbid blocking operations or the event loop will stall.

**6. Is manually calling `subscribe()` and returning immediately safe?**  
No if the response depends on the upstream result; error handling and lifecycle become detached.

**7. For an imperative MVC app making a single REST call, what else should be considered besides WebClient?**  
`RestClient`, introduced in Spring 6.1.

**8. Does `Mono.zip` guarantee a result if one publisher completes empty?**  
No. You need explicit handling for `Mono.empty` and errors.

**9. When `WebClient.retrieve()` hits an upstream 500, does the MVC app automatically return 500 cleanly?**  
Not necessarily properly mapped. It emits `WebClientResponseException`, which should be mapped per API contract.

**10. Does flipping `spring.main.web-application-type` to `reactive` complete migrating an MVC app using Servlet filters and JPA?**  
No. Request APIs, security, data access, and the execution model must all be updated and tested.

**11. Can returning `Mono` in MVC reduce Servlet request thread waiting?**  
Yes, via Servlet async; however, response writes and other layers may still block.

**12. Why must clients never pass arbitrary URLs for WebClient to fetch?**  
Risk of SSRF and unauthorized internal network access.

## 15. Adoption Checklist

- [ ] Clarify whether the goal is an **outbound HTTP client** or **migrating the inbound HTTP server**.
- [ ] Does the project include both `starter-web` and `starter-webflux`? Understand Boot defaults to **SERVLET**.
- [ ] Verify **ServletWebServerApplicationContext** or write an integration test before drawing conclusions.
- [ ] Inject Boot's **WebClient.Builder**; build and reuse clients.
- [ ] Choose **RestClient** when the requirement is simple imperative HTTP.
- [ ] When using `WebClient` in MVC, intentionally pick **bounded `block()`** or **returning `Mono`**.
- [ ] Never call `subscribe()` manually inside request handlers that need the result.
- [ ] Never block event loops, and never mistake Servlet async for an end-to-end reactive server.
- [ ] Configure connect, response, pipeline, Servlet async, and proxy timeouts consistently.
- [ ] Implement error mapping, retry/idempotency policies, and connection pool/concurrency monitoring.
- [ ] Keep TLS verification enabled, and guard against SSRF and unsafe credential forwarding.
- [ ] If migrating to WebFlux, audit Servlet filters, security, multipart handling, JDBC/JPA, and tests.

## 16. Conclusion

**`WebClient` is a reactive HTTP client, not a toggle for web application type.** In Spring Boot 3.3, when both Spring MVC and WebFlux are present, **MVC/SERVLET is selected by default**. `WebClient` still performs outbound HTTP requests; Reactor Netty may operate on the client side while Tomcat continues serving inbound requests.

An MVC controller can **call `block()` with a time bound** at a synchronous boundary, or **return `Mono` so Spring MVC leverages Servlet async**. Never equate those two execution modes, and never treat returning `Mono` as proof of a WebFlux server. Switch to WebFlux only after evaluating the entire stack and performance goals.

## Official References

- Spring Boot 3.3 — Reactive Web Applications, MVC precedence rule with both starters: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Calling REST Services, `WebClient.Builder` and client runtime: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — Testing Spring Boot Applications, Detecting Web Application Type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MVC Asynchronous Requests and Reactive Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — `WebClient.retrieve`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — `WebClient` overview: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Project Reactor — Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/