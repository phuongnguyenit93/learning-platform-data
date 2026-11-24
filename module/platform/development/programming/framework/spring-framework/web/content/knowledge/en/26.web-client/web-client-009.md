# Using WebClient in Spring MVC: Choosing Where to Block and Avoiding Blocking the Event Loop

## 1. Context: WebClient Is Reactive, Spring MVC Is Servlet-Based

`WebClient` is an HTTP client using a reactive API (`Mono`/`Flux`), performing HTTP I/O asynchronously and supporting non-blocking execution with a suitable connector (typically Reactor Netty). `Spring MVC` runs on the Servlet stack; synchronous controllers are normally invoked by a thread from the Servlet container's pool (such as `http-nio-8080-exec-*` on Tomcat). The Servlet stack permits controllers to call blocking APIs, though the thread remains occupied while waiting.

Thus, using WebClient in MVC is **completely valid**. The key decision is: does the current endpoint need to return a synchronous Java value, or can it return a publisher for Spring MVC to handle asynchronously?

- **Synchronous:** take a `Mono<T>` and call `block()` **once at the imperative boundary**, such as a synchronous service method invoked by an MVC controller on a servlet worker. This integrates easily with existing synchronous code, while holding one servlet thread per request waiting on upstream.
- **Asynchronous:** the MVC controller directly returns `Mono<T>`/`Mono<ResponseEntity<T>>`. Spring MVC adapts the publisher to Servlet async processing (similar to `DeferredResult`); the request does not hold a servlet worker continuously while WebClient waits on upstream.
- **Streaming:** MVC can adapt `Flux` to asynchronous response writing with an appropriate media type, though **writing out to the HTTP response on the Servlet stack remains blocking** and requires an appropriate `AsyncTaskExecutor`. Simply adding `WebClient` does not convert the entire MVC application into a WebFlux server.

What must be avoided most is calling `block()` on a Reactor event-loop (`reactor-http-nio-*`) or non-blocking scheduler. Doing so can raise `IllegalStateException` or stall I/O threads. **A non-blocking HTTP client does not automatically guarantee every part of your pipeline stays non-blocking**: your own code inside `map`, `flatMap`, or callbacks may still run on the event loop.

### Diagram of the Two Models

~~~text
A. Synchronous MVC
HTTP client --> Servlet worker --> service --> WebClient: Mono<T>
                     |                           |
                     |-- block() waits ----------|--> Reactor Netty event-loop
                     |                                (socket read/write, non-blocking)
                     <-- value T ------------------|
                     --> write MVC response

B. Asynchronous MVC
HTTP client --> Servlet worker --> controller returns Mono<T>
                     |                 |
                     |            MVC registers Servlet async
                 worker freed          |
                                      WebClient runs I/O on event-loop
                                            |
                                         result T
                                            |
                                 MVC dispatches/writes response
~~~

Calling `block()` on a servlet thread **does not make Reactor Netty perform blocking I/O**; it only makes that servlet thread wait for a signal from the publisher. This is the difference between **blocking the caller** and **blocking the event loop**.

## 2. When Is Blocking Allowed, and When Should You Return Mono?

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| MVC controller/service has a synchronous `T get(...)` contract, using JDBC/JPA or imperative code | May `block()` at the end of the call on a servlet worker | Synchronous contract; clear boundary, straightforward error handling. |
| MVC controller can return `Mono<T>` | Prefer returning the publisher directly | MVC supports Servlet async, freeing servlet threads while waiting for I/O. |
| WebFlux controller or callback running on a Reactor event loop | **Never call `block()`** | Blocks the event loop; Reactor may throw `IllegalStateException`. |
| Inside `map`/`doOnNext`/`flatMap` of a WebClient chain | Do not block directly | Callbacks may run on non-blocking threads; compose publishers instead of nested blocking. |
| Calling multiple upstream HTTP endpoints concurrently | Build the `Mono` instances, combine with `zip`/`flatMap`, then block **only if truly required** | Avoids sequential waiting; at most one block at the end for synchronous callers. |
| Reactive chain must invoke a blocking library like legacy JDBC | Offload **only that blocking step** with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` | Keeps the event loop clear; bounds blocking work on a dedicated scheduler. |
| Pure synchronous MVC app needing neither reactive nor streaming | Consider `RestClient` | Clear imperative API without building a pipeline only to block it. |

There is no mandate to choose the second approach for every application: under moderate load, with many other synchronous operations and low complexity, blocking on a servlet worker can be a practical choice. However, under high upstream latency and high concurrency, waiting servlet threads can become the bottleneck; measure throughput, active threads, queues, and timeouts before settling on an architecture.

## 3. Using WebClient at MVC's Synchronous Boundary

In a synchronous service, keep the publisher unsubscribed until the end, then block once:

~~~java
@Service
public class CustomerService {
    private final WebClient client;

    public CustomerService(WebClient.Builder builder) {
        this.client = builder.baseUrl("https://api.example.com").build();
    }

    public CustomerDto find(long id) {
        return client.get()
                .uri("/customers/{id}", id)
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .block(Duration.ofSeconds(3));
    }
}
~~~

This is an **integration snippet**, assuming `CustomerDto` is defined and the upstream exists. `block(Duration)` waits at most the specified time; if the publisher completes empty, the result can be `null`. Usually you must distinguish "empty body" from "missing resource," e.g., via `switchIfEmpty(Mono.error(...))` and an explicit 404 policy. By default, `retrieve()` turns HTTP 4xx/5xx into `WebClientResponseException` when subscribed.

The right place is **a single exit point in a synchronous service**, called from a servlet worker. Do not call `block()` inside a `map`/`flatMap` lambda and then `block()` again outside; that is nested blocking.

Example synchronous MVC controller calling the service:

~~~java
@RestController
class CustomerController {
    private final CustomerService customers;

    CustomerController(CustomerService customers) {
        this.customers = customers;
    }

    @GetMapping("/customers/{id}")
    CustomerDto get(@PathVariable long id) {
        return customers.find(id);
    }
}
~~~

When a request hits `/customers/42`, the servlet thread handling the controller waits on upstream; once done, MVC serializes `CustomerDto` to JSON. Configure timeouts to guard the wait path and handle errors consistently; if upstream is slower than the available servlet thread pool can absorb, throughput will still drop even though WebClient uses asynchronous I/O.

### Multiple HTTP Calls: Build Monos First, Wait Once

~~~java
Mono<CustomerDto> customer = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class);

Mono<OrderDto[]> orders = client.get()
        .uri("/customers/42/orders")
        .retrieve()
        .bodyToMono(OrderDto[].class);

CustomerPage result = Mono.zip(
        customer, orders,
        (c, o) -> new CustomerPage(c, List.of(o))
).block(Duration.ofSeconds(5));
~~~

Assume `OrderDto` and `CustomerPage` are defined. When `zip` is subscribed, both requests can proceed concurrently; by contrast, calling `customer.block()` followed by `orders.block()` waits sequentially. If one source errors or completes empty, `zip` follows Reactor semantics (potentially erroring or completing empty and cancelling the other source); define explicit error/empty policies.

**Do not call `block()` repeatedly on the same source `Mono` if you only want one response**: multiple `block()` calls normally create multiple subscriptions and can fire multiple HTTP requests, since WebClient publishers are cold by default.

## 4. Non-Blocking Usage: MVC Returning Mono Directly

MVC can return a `Mono` from a controller; the framework registers asynchronous processing and completes the HTTP response when the publisher emits its result:

~~~java
@RestController
class AsyncCustomerController {
    private final WebClient client;

    AsyncCustomerController(WebClient.Builder builder) {
        this.client = builder.baseUrl("https://api.example.com").build();
    }

    @GetMapping("/async-customers/{id}")
    Mono<CustomerDto> get(@PathVariable long id) {
        return client.get()
                .uri("/customers/{id}", id)
                .retrieve()
                .bodyToMono(CustomerDto.class)
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

This is still a **Spring MVC controller**, not a WebFlux handler. Callers do not call `subscribe()` themselves: Spring MVC subscribes through an adapter to manage the response lifecycle. The controller method returns promptly while the servlet request stays in async state until the response finishes, times out, or cancels.

Spring MVC also supports reactive multi-item returns, though you must choose the right media type and response-writing mode; for instance `text/event-stream` for streaming or `application/json` which normally collects items into a collection to serialize. Never assume `Flux` on an MVC server implies non-blocking socket writes.

### Composing Requests Without Blocking

~~~java
@GetMapping("/overview/{id}")
Mono<CustomerPage> overview(@PathVariable long id) {
    Mono<CustomerDto> profile = client.get()
            .uri("/customers/{id}", id)
            .retrieve()
            .bodyToMono(CustomerDto.class);

    Mono<OrderDto[]> orders = client.get()
            .uri("/customers/{id}/orders", id)
            .retrieve()
            .bodyToMono(OrderDto[].class);

    return Mono.zip(profile, orders,
            (customer, items) -> new CustomerPage(
                    customer, List.of(items)))
            .timeout(Duration.ofSeconds(5));
}
~~~

`Mono.zip` expresses parallel subscription. For dependent APIs, use `flatMap`:

~~~java
Mono<OrderDto[]> result = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .flatMap(customer -> client.get()
                .uri("/customers/{id}/orders", customer.id())
                .retrieve()
                .bodyToMono(OrderDto[].class));
~~~

Both examples assume the DTOs and `client` bean exist; they are not standalone Java files. Notably, `flatMap` returns a publisher; there is no need to `block()` to read `customer` inside the lambda.

## 5. Complete Java 17+ Demo: One MVC App, Two Endpoints

The demo runs locally without external Internet services. A Spring Boot 3.x application uses **Spring MVC with Tomcat** and WebClient calling an independent mock HTTP server running on a random JDK port. There are two APIs:

- `GET /sync`: Spring MVC controller calls `block(Duration)` on a servlet thread.
- `GET /async`: controller returns `Mono<Quote>` for Spring MVC to handle via Servlet async.

The goal is to observe two **execution boundaries**; identical JSON output does not mean both endpoints hold servlet workers identically.

### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-webclient</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot 3.x defaults to configuring a **Spring MVC web application**; the WebFlux starter supplies WebClient/Reactor Netty client and needed reactive components. This **does not automatically replace the MVC server with Netty/WebFlux**.

### `src/main/java/demo/MvcWebClientApplication.java`

~~~java
package demo;

import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class MvcWebClientApplication {

    public static void main(String[] args) throws Exception {
        HttpServer upstream = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        upstream.createContext("/quote", exchange -> {
            byte[] payload = "{\"text\":\"hello\"}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        });
        upstream.start();

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> upstream.stop(0)));

        SpringApplication app = new SpringApplication(
                MvcWebClientApplication.class);
        app.setDefaultProperties(Map.of(
                "demo.upstream-url",
                "http://127.0.0.1:" + upstream.getAddress().getPort()));
        app.run(args);
    }

    @Bean
    WebClient upstreamClient(
            WebClient.Builder builder,
            @Value("${demo.upstream-url}") String upstreamUrl) {
        return builder.baseUrl(upstreamUrl).build();
    }

    public record Quote(String text) {}

    @RestController
    static class GatewayController {
        private final WebClient client;

        GatewayController(WebClient upstreamClient) {
            this.client = upstreamClient;
        }

        @GetMapping("/sync")
        Quote sync() {
            return client.get()
                    .uri("/quote")
                    .retrieve()
                    .bodyToMono(Quote.class)
                    .block(Duration.ofSeconds(3));
        }

        @GetMapping("/async")
        Mono<Quote> async() {
            return client.get()
                    .uri("/quote")
                    .retrieve()
                    .bodyToMono(Quote.class)
                    .timeout(Duration.ofSeconds(3));
        }
    }
}
~~~

Run in the directory containing `pom.xml` (JDK 17+, Maven):

~~~bash
mvn spring-boot:run
~~~

Open another terminal:

~~~bash
curl -s http://127.0.0.1:8080/sync
curl -s http://127.0.0.1:8080/async
~~~

Both commands expect the body (one line each):

~~~json
{"text":"hello"}
~~~

For a Boot app using default port settings, the MVC server listens on `8080`; the upstream port is dynamically assigned by the OS. The mock `HttpServer` handles upstream requests independently, avoiding a loop calling back into the same MVC server. Stopping `mvn spring-boot:run` shuts down the app, and the shutdown hook stops upstream.

The JSON results are identical, while servlet worker usage differs: `sync` waits on the request-handling thread; `async` returns `Mono` so MVC registers async processing. This is a behavioral demo, **not a benchmark**; use thread profiling and load-testing tools to evaluate scalability.

## 6. Why Is Blocking on the Reactor Event Loop Dangerous?

Reactor Netty typically uses a small number of event-loop threads to handle socket events for many requests. If one of these threads waits on synchronous I/O or a long `Thread.sleep`, other connections assigned to it are delayed too. Reactor marks many non-blocking threads with the `NonBlocking` marker; calling `block()`/`blockFirst()`/`blockLast()` there is typically prevented with an exception like:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Thread names can vary by environment. Do not rely **solely** on thread names to judge safety; `Schedulers.isInNonBlockingThread()` indicates whether Reactor considers the current thread non-blocking.

### Wrong: Nested Block Inside an Operator

~~~java
Mono<CustomerPage> bad = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .map(customer -> {
            // Wrong: map may run on the Reactor Netty event-loop.
            OrderDto[] orders = client.get()
                    .uri("/customers/{id}/orders", customer.id())
                    .retrieve()
                    .bodyToMono(OrderDto[].class)
                    .block();
            return new CustomerPage(customer, List.of(orders));
        });
~~~

When executed under a subscriber, the `map` lambda can be invoked on the HTTP response event loop, so nested `block()` violates the threading model. **Right:** use `flatMap` to express the second HTTP call as a publisher:

~~~java
Mono<CustomerPage> good = client.get()
        .uri("/customers/42")
        .retrieve()
        .bodyToMono(CustomerDto.class)
        .flatMap(customer -> client.get()
                .uri("/customers/{id}/orders", customer.id())
                .retrieve()
                .bodyToMono(OrderDto[].class)
                .map(orders -> new CustomerPage(
                        customer, List.of(orders))));
~~~

### Wrong: Calling a Blocking Library Directly in the Pipeline

~~~java
Mono<String> wrong = client.get()
        .uri("/quote")
        .retrieve()
        .bodyToMono(String.class)
        .map(body -> legacyFileApi.readAndStore(body)); // Blocks the thread running map!
~~~

If code truly must call a blocking API you cannot replace, wrap **only the blocking step** with an appropriate scheduler:

~~~java
Mono<String> right = client.get()
        .uri("/quote")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(body -> Mono.fromCallable(
                    () -> legacyFileApi.readAndStore(body))
                .subscribeOn(Schedulers.boundedElastic()));
~~~

Both snippets are illustrative; import `reactor.core.scheduler.Schedulers` and provide a real `legacyFileApi`. `boundedElastic` is for bounded blocking work; it does not make a legacy API non-blocking or grant infinite throughput. If the whole pipeline is purely reactive WebClient calls, you do **not** need `subscribeOn(boundedElastic())` to "make WebClient async": WebClient already uses asynchronous I/O.

Common mistaken trick: attaching `publishOn(Schedulers.boundedElastic())` to a Mono and immediately calling `block()` outside **does not move the thread calling `block()` onto boundedElastic**. The caller thread is still blocked. Only offload when the actual blocking work resides **inside** the scheduler-managed publisher.

## 7. Timeouts, Errors, Cancellation, and Body Lifecycle

### Distinguishing Timeouts

- `block(Duration.ofSeconds(3))`: bounds how long the caller thread waits for a signal from the publisher; appropriate only at an authorized synchronous boundary. On timeout, the subscription is cancelled.
- `mono.timeout(Duration.ofSeconds(3))`: sets a limit at the reactive pipeline level; suited for MVC controllers returning `Mono`. Timeout emits an error signal and cancels upstream.
- TCP connect, response read, or pool acquire timeouts are HTTP client/connection pool settings; they are not strictly equivalent to the two timeouts above.
- Spring MVC Servlet async also has a web-MVC-level timeout; configure and map errors so no layer waits indefinitely while aligning overall timeouts with your SLA.

Do not simply raise all timeouts to cope with servlet thread exhaustion. Inspect upstream wait times, connection pools, max threads, and concurrent requests. A timeout does not guarantee the upstream completely stopped processing: client-side cancellation does not necessarily roll back server-side actions.

### Intentional Error Handling

By default, `retrieve()` emits errors on HTTP 4xx or 5xx; connection failures typically emit `WebClientRequestException`, while timeouts can produce other error types depending on the API chosen. In synchronous MVC, errors from `block()` surface on the synchronous call stack; in reactive-return MVC, errors are signals on the publisher handled by the pipeline/MVC exception infrastructure. Design `@ExceptionHandler`, response statuses, and logging cleanly instead of catching all errors and returning 200 with fake data.

Example handling upstream 404 by business rules without blocking inside a callback:

~~~java
Mono<CustomerDto> customer = client.get()
        .uri("/customers/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new CustomerNotFoundException(42)))
        .bodyToMono(CustomerDto.class);
~~~

This snippet assumes the custom exception exists. `onStatus` must return an appropriate `Mono<? extends Throwable>`. In branches handling `ClientResponse` manually via `exchangeToMono`, always read or release the response body properly; avoid keeping `ClientResponse` around after the callback ends. If a stream is cancelled mid-flight, the connection pool may have to discard the HTTP/1.1 socket rather than returning it to the pool; never claim every cancelled request reuses connections.

### Context and Transactions Across Thread Boundaries

In synchronous MVC, `ThreadLocal` values like MDC, `RequestContextHolder`, or transactions may live on the servlet worker. However, WebClient callbacks run on other threads, so they **do not automatically** carry servlet context/transactions into reactive callbacks. If tracing/security context propagation is required, use context propagation mechanisms supported by Spring/Micrometer and verify them in practice. Avoid holding a JDBC transaction open merely to wait on a slow remote HTTP call when transaction boundaries can be separated.

## 8. Common Mistakes and Fixes

1. **Calling `block()` in a WebFlux controller or WebClient callback:** switch to returning `Mono`/`Flux` and use `flatMap`/`zip`; if an unavoidable blocking library is involved, offload just that part.
2. **Calling `subscribe()` manually in an MVC controller and returning an empty result:** remove manual subscription; return the publisher so MVC manages the request and errors. `subscribe()` can detach work from the HTTP lifecycle and drop errors.
3. **Calling `block()` twice on one HTTP publisher:** creates two subscriptions that may send the request twice. Build the pipeline and subscribe/block once at the right boundary; cache only intentionally while understanding trade-offs.
4. **Calling two upstreams sequentially with `block()`:** build both `Mono`s first, combine with `zip` if independent, and block once when synchronous output is needed.
5. **Assuming WebClient makes MVC fully non-blocking:** MVC still sits on a Servlet container; rendering/writing responses can use a blocking executor depending on return type and media type.
6. **Leaving synchronous endpoints without timeout/concurrency bounds:** servlet workers can all become occupied. Set deadlines and appropriate capacity; consider returning `Mono` and monitoring metrics.
7. **Overusing `boundedElastic`:** offload only legacy blocking tasks; it is bounded and can queue.
8. **Reading status but forgetting the response body:** use `retrieve().bodyToMono(...)` or `toBodilessEntity()`; with `exchangeToMono`, complete body handling/release so the connection pool does not retain resources.
9. **Calling HTTP back into the same application in demos/heavy load:** if all servlet workers wait on internal requests that need other servlet workers, you can cause self-inflicted starvation. Separate real upstreams and bound concurrency.

## 9. Boundary Selection Checklist

Before calling WebClient from Spring MVC, ask yourself:

- **Who is calling?** Servlet workers may block; Reactor event loops may not.
- **What is the return contract?** If returning `Mono<T>` is possible, let MVC manage async; if synchronous `T` is mandatory, block once at the end on a permitted thread.
- **How many HTTP calls are there?** Combine independent publishers with `zip` to avoid sequential waits; use `flatMap` for dependent chains.
- **Is there blocking code inside callbacks?** Replace with reactive APIs or offload legacy code onto `boundedElastic`.
- **Are timeouts, error handling, cancellation, and body cleanup explicit?** Ensure requests terminate and do not hold servlet threads/connections indefinitely.
- **Can you measure bottlenecks?** Monitor busy servlet threads, async requests, Reactor Netty connection pools, response latency, and timeout errors under load.

**Principle:** In synchronous MVC, `block()` is allowed at the imperative boundary on a servlet worker at the cost of holding that thread. In asynchronous MVC, returning `Mono` is the natural choice. Inside a WebClient/reactive chain or on an event loop, keep all work non-blocking and compose publishers instead of calling `block()`.

## 10. References

- Spring Framework — WebClient Synchronous Use: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — Spring MVC Asynchronous Requests, Reactive Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Concurrency Model in Spring MVC and WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Boot — Calling REST Services / WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Framework — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
