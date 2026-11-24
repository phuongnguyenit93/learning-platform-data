# Contrasting the Same Problem on Spring MVC and WebFlux via Observable Behavior

## 1. Goal: same API, same upstream, compare what is observed

Both Spring MVC and Spring WebFlux support building REST APIs, yet their execution models differ. Merely comparing syntax—"controller returns an object" versus "controller returns Mono"—does not prove operational differences.

This exercise uses **a single shared problem**: an API gateway querying inventory status from an HTTP upstream with roughly 300 ms latency.

- Clients call `GET /api/inventory/{id}`.
- The Spring gateway calls `GET /inventory/{id}` on a shared upstream.
- Upstream returns JSON `{"id":1,"available":true}` for valid IDs, and HTTP `404` for nonexistent IDs.
- Both the MVC gateway and WebFlux gateway return HTTP `200` + equivalent JSON or HTTP `404`.
- Run many concurrent requests and record **thread names**, in-flight request counts, p95 response latency, total time, and errors.
- Compare based on observed behavior rather than declaring one framework "always faster" from a toy benchmark.

In this lesson:

- **MVC** uses Servlet/Tomcat + `RestClient` (synchronous HTTP client).
- **WebFlux** uses Reactor Netty + `WebClient` (reactive/non-blocking HTTP client).
- **Upstream** is a standalone HTTP server written in Java SE 17; both gateways call the exact same URL so the comparison never accidentally measures two different backends.

Configurations and API names focus on **Spring Boot 3.x / Spring Framework 6.x, Java 17+**. Never generalize a single performance observation from this environment to all workloads.

## 2. What to understand before running

### 2.1. Synchronous Spring MVC

A typical MVC request:

~~~text
Client
  -> TCP/HTTP -> Tomcat servlet worker
                  |
                  -> @RestController
                  -> RestClient HTTP GET to upstream (synchronous)
                  -> servlet thread WAITS for response
                  -> receives Inventory record
                  -> Jackson serializes JSON
                  -> HTTP 200 to client
~~~

While `RestClient` awaits a response, **the calling servlet worker is occupied**. This is not a bug: it is the imperative programming model—simple and well suited to many systems using Spring MVC, JDBC/JPA, and synchronous business logic.

However, if many requests must wait on slow remote I/O, limits on servlet threads, HTTP connections, and queues can affect throughput and tail latency. Enlarging the thread pool only shifts the bottleneck if upstream or the DB is already saturated.

### 2.2. Reactive Spring WebFlux

A typical WebFlux request:

~~~text
Client
  -> Reactor Netty event-loop / WebFlux handler
                  |
                  -> @RestController returns Mono<Inventory>
                  -> WebClient HTTP GET to upstream
                  -> asynchronous subscribe; event-loop DOES NOT sit waiting 300 ms
                  -> receives HTTP response signal
                  -> Mono emits Inventory record
                  -> WebFlux/Jackson writes HTTP 200 JSON
~~~

A `Mono<T>` publisher represents **a result that may arrive later**, not a dedicated thread. Reactor Netty uses non-blocking I/O on sockets; Reactor operators may run on the event loop, another scheduler, or specific threads along the chain. **Do not assume every callback runs on a single thread**, and never call `block()` on the event loop.

Notably, Spring MVC **also supports async** via `Callable`, `DeferredResult`, `CompletionStage`, and reactive return types such as `Mono`. Thus "MVC = every request must hold a servlet worker" applies only to the **synchronous MVC** example studied here, not all of Spring MVC. MVC async uses Servlet async; WebFlux has asynchronous contracts from the ground up. On the Servlet stack, HTTP response writes can still have blocking characteristics depending on response type, unlike WebFlux's non-blocking response I/O.

### 2.3. Where do they differ, and where are they the same?

| Aspect | MVC + RestClient | WebFlux + WebClient |
| --- | --- | --- |
| External HTTP API | `GET /api/inventory/{id}` | Identical |
| 200 response | Inventory JSON | Equivalent Inventory JSON |
| HTTP upstream | Same Java HTTP server | Same Java HTTP server |
| Upstream delay | Simulated 300 ms | Simulated 300 ms |
| Handler return type | `Inventory` | `Mono<Inventory>` |
| HTTP client | Synchronous `RestClient` | Reactive `WebClient` |
| While awaiting upstream | Servlet worker blocks | No need to hold an event-loop thread waiting |
| On 404 error | Catch HTTP client exception | Map reactive error signal |
| Pressure under high concurrency | Servlet threads, pending tasks, pools | Open connections, event loops, event queues, subscribers/backpressure |
| Blocking JPA/JDBC integration | Natural | Must isolate blocking calls or pick a different model |
| Async capability | MVC supports it when explicitly designed | Built into the foundational model |

Both can deliver the same functionality and business correctness. A single benchmark does not prove WebFlux is faster in CPU, operational cost, or latency in every scenario.

## 3. Demo architecture and measurement assumptions

~~~text
                        +----------------------------+
  curl / LoadProbe ---> | MVC gateway :8081          |
                        | Tomcat + RestClient         |---+
                        +----------------------------+   |
                                                         | HTTP GET
                        +----------------------------+   | /inventory/{id}
  curl / LoadProbe ---> | WebFlux gateway :8082      |---+
                        | Reactor Netty + WebClient   |   |
                        +----------------------------+   v
                                                   +-------------------+
                                                   | Upstream :9090    |
                                                   | Java HttpServer   |
                                                   | delay ~= 300 ms   |
                                                   | 1..3 -> 200 JSON  |
                                                   | others -> 404     |
                                                   +-------------------+
~~~

Proactively avoid mistakes that make comparisons meaningless:

- Upstream **never calls back into the MVC server**, because self-calling loops can exhaust servlet workers.
- Upstream uses a fixed 64-worker pool to serve concurrent demo requests; exceeding capacity causes queuing and extra latency.
- The two gateways run in **two separate JVMs on two ports**; run only one load probe at a time so the two measurements do not contend for upstream.
- Transport is localhost. It is suitable for observing execution models, **not representative of the Internet or production**.
- `server.tomcat.threads.max=8` below is an **intentional experiment** to make thread queuing visible, not a recommended production default.
- Latency results depend on hardware, OS, JIT warmup, connection reuse, logging, memory, CPU count, clients, and background load. Record actual measured numbers instead of treating one figure as a "standard."

## 4. Shared upstream app: plain Java 17

Create `upstream/SlowInventoryServer.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public class SlowInventoryServer {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9090), 0);
        server.createContext("/inventory", SlowInventoryServer::handle);
        server.setExecutor(Executors.newFixedThreadPool(64));
        server.start();
        System.out.println("Upstream listening on 127.0.0.1:9090");
    }

    private static void handle(HttpExchange exchange) throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            exchange.getResponseHeaders().set("Allow", "GET");
            reply(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }

        String[] parts = exchange.getRequestURI().getPath().split("/");
        String id = parts.length == 3 ? parts[2] : "";

        if (!id.matches("[1-3]")) {
            reply(exchange, 404, "{\"error\":\"not_found\"}");
            return;
        }

        try {
            Thread.sleep(300); // Simulate remote I/O / a slow backend.
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            reply(exchange, 503, "{\"error\":\"interrupted\"}");
            return;
        }

        reply(exchange, 200,
                "{\"id\":" + id + ",\"available\":true}");
    }

    private static void reply(
            HttpExchange exchange, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

From `upstream/`, compile and run:

~~~bash
javac --add-modules jdk.httpserver SlowInventoryServer.java
java --add-modules jdk.httpserver SlowInventoryServer
~~~

Stdout on startup:

~~~text
Upstream listening on 127.0.0.1:9090
~~~

Verify in another terminal:

~~~bash
curl -i http://127.0.0.1:9090/inventory/1
curl -i http://127.0.0.1:9090/inventory/9
~~~

The first response has status `200`, body `{"id":1,"available":true}`, and an intentional ~300 ms delay; the second returns `404` with body `{"error":"not_found"}`. `Date`, exact elapsed time, and header order vary. If port 9090 is occupied, update the URL in upstream and both gateways together.

**Why does upstream use `Thread.sleep`?** Only to create controlled latency on **an independent server**. It does not imply WebFlux needs or should use `Thread.sleep`. When WebFlux calls the endpoint, the gateway's I/O still runs via non-blocking WebClient; the sleep occurs on the simulated upstream server.

## 5. Spring MVC gateway: synchronous RestClient

Create `mvc/` with the following layout:

~~~text
mvc/
  pom.xml
  src/main/java/demo/MvcInventoryApplication.java
  src/main/resources/application.properties
~~~

### 5.1. mvc/pom.xml

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
    <artifactId>mvc-inventory</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

This is a **Servlet MVC** app because it uses `spring-boot-starter-web`. Do not add the WebFlux starter into the MVC project just for synchronous HTTP calls; `RestClient` suffices here.

### 5.2. mvc/src/main/resources/application.properties

~~~properties
server.port=8081
server.tomcat.threads.max=8
~~~

Capping servlet threads at 8 makes it easy to observe when concurrent requests exceed capacity. This value can force 40 requests into multiple waiting waves, especially while each request holds a worker for ~300 ms.

### 5.3. mvc/src/main/java/demo/MvcInventoryApplication.java

~~~java
package demo;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcInventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcInventoryApplication.class, args);
    }

    @Bean
    RestClient upstream(RestClient.Builder builder) {
        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();
        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("http://127.0.0.1:9090")
                .requestFactory(factory)
                .build();
    }
}

record Inventory(long id, boolean available) {}

@RestController
class MvcInventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(MvcInventoryController.class);

    private final RestClient upstream;
    private final AtomicInteger active = new AtomicInteger();

    MvcInventoryController(RestClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/inventory/{id}")
    Inventory get(@PathVariable int id) {
        int now = active.incrementAndGet();
        log.info("MVC start id={} active={} thread={}",
                id, now, Thread.currentThread().getName());

        try {
            Inventory result = upstream.get()
                    .uri("/inventory/{id}", id)
                    .retrieve()
                    .body(Inventory.class);

            if (result == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY, "Empty upstream body");
            }

            return result;
        } catch (RestClientResponseException ex) {
            if (ex.getStatusCode().value() == 404) {
                throw new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Inventory not found", ex);
            }
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Upstream rejected request", ex);
        } catch (RestClientException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Upstream unavailable", ex);
        } finally {
            int left = active.decrementAndGet();
            log.info("MVC end id={} active={} thread={}",
                    id, left, Thread.currentThread().getName());
        }
    }
}
~~~

Run from `mvc/`:

~~~bash
mvn spring-boot:run
~~~

Inspect the logs. For a normal single request, start and end typically log the same Servlet worker thread name, e.g., `http-nio-8081-exec-1`, because `RestClient` executes synchronously inside the controller. Exact thread names vary by Tomcat, version, and environment; the key observation is that **one worker starts the request, waits for upstream, and finishes the request**.

`active` counts calls currently inside the controller method, **not total servlet threads in the container**. This gauge helps spot waiting requests, though confirming thread-pool saturation requires checking Tomcat metrics or thread dumps as well.

In the example above, an upstream HTTP 404 response is translated into gateway status 404. Other HTTP errors or connection failures map to 502. Client timeout config acts as a safeguard; timeouts can surface as I/O errors inside `RestClientException`, so the example **does not claim 504 mapping for every timeout**.

## 6. Spring WebFlux gateway: reactive WebClient

Create a separate `webflux/` directory:

~~~text
webflux/
  pom.xml
  src/main/java/demo/WebFluxInventoryApplication.java
  src/main/resources/application.properties
~~~

Do not mix `spring-boot-starter-web` and `spring-boot-starter-webflux` in this project: when both are present, Spring Boot normally selects an **MVC web application** by default. Keeping the two apps separate guarantees which server stack runs.

### 6.1. webflux/pom.xml

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
    <artifactId>webflux-inventory</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 6.2. webflux/src/main/resources/application.properties

~~~properties
server.port=8082
~~~

The WebFlux Reactor Netty server does not use `server.tomcat.threads.max`. Do not try to "make it fair" by applying identical thread settings: the MVC servlet pool and the Reactor Netty event-loop pool serve different roles. For serious benchmarking, measure and tune **both systems within comparable capacity/resource budgets**.

### 6.3. webflux/src/main/java/demo/WebFluxInventoryApplication.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class WebFluxInventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxInventoryApplication.class, args);
    }

    @Bean
    WebClient upstream(WebClient.Builder builder) {
        return builder.baseUrl("http://127.0.0.1:9090").build();
    }
}

record Inventory(long id, boolean available) {}

@RestController
class WebFluxInventoryController {
    private static final Logger log =
            LoggerFactory.getLogger(WebFluxInventoryController.class);

    private final WebClient upstream;
    private final AtomicInteger active = new AtomicInteger();

    WebFluxInventoryController(WebClient upstream) {
        this.upstream = upstream;
    }

    @GetMapping("/api/inventory/{id}")
    Mono<Inventory> get(@PathVariable int id) {
        return Mono.defer(() -> {
            int now = active.incrementAndGet();
            log.info("WebFlux subscribe id={} active={} thread={}",
                    id, now, Thread.currentThread().getName());

            return upstream.get()
                    .uri("/inventory/{id}", id)
                    .retrieve()
                    .bodyToMono(Inventory.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Empty upstream body")))
                    .onErrorMap(
                            WebClientResponseException.class,
                            ex -> ex.getStatusCode().value() == 404
                                    ? new ResponseStatusException(
                                            HttpStatus.NOT_FOUND,
                                            "Inventory not found", ex)
                                    : new ResponseStatusException(
                                            HttpStatus.BAD_GATEWAY,
                                            "Upstream rejected request", ex))
                    .onErrorMap(
                            WebClientRequestException.class,
                            ex -> new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Upstream unavailable", ex))
                    .timeout(Duration.ofSeconds(2))
                    .onErrorMap(
                            TimeoutException.class,
                            ex -> new ResponseStatusException(
                                    HttpStatus.GATEWAY_TIMEOUT,
                                    "Upstream response timed out", ex))
                    .doOnNext(value -> log.info(
                            "WebFlux result id={} thread={}",
                            id, Thread.currentThread().getName()))
                    .doFinally(signal -> {
                        int left = active.decrementAndGet();
                        log.info("WebFlux end id={} active={} signal={} thread={}",
                                id, left, signal,
                                Thread.currentThread().getName());
                    });
        });
    }
}
~~~

Run inside `webflux/`:

~~~bash
mvn spring-boot:run
~~~

Here **the controller calls neither `block()` nor `subscribe()`**. It returns `Mono<Inventory>`; WebFlux subscribes within the request lifecycle, serializes the value once emitted, and handles errors from the publisher.

`Mono.defer` ensures incrementing `active` and issuing the request happen **at subscription time**, not when the method builds the publisher. `doFinally` executes on completion, error, or cancellation, so the in-flight counter cleans up even when requests are cancelled.

`timeout(Duration)` is a reactive-chain timeout and does not fully replace Reactor Netty connect timeouts and connection-pool limits. The 504 status on timeout here is an illustrative policy; MVC timeout mapping above was not standardized to 504, so **treat only 200/404 and network-error 502 as equivalent contracts in the demo**, rather than concluding both stacks share identical error contracts across every failure mode.

### Note on thread logs

When logs show `reactor-http-nio-*`, callbacks are running on a Reactor Netty event loop. However, Reactor can switch threads depending on operators/schedulers; thread names are not fixed. The key observation is **zero blocking waits on handler threads** in this code. WebClient performs HTTP I/O non-blockingly while upstream sleeps for ~300 ms.

Inserting `Thread.sleep(300)` into `map` or `doOnNext` in WebFlux violates the non-blocking assumption. Calling synchronous JDBC/JPA or blocking file I/O requires isolating it onto a controlled blocking mechanism (`boundedElastic` or a dedicated thread pool) or choosing imperative Spring MVC if the system is predominantly blocking.

## 7. Symmetric testing: verifying functionality and errors

Start three processes in three terminals:

1. `SlowInventoryServer` listening on 9090.
2. `MvcInventoryApplication` listening on 8081.
3. `WebFluxInventoryApplication` listening on 8082.

Send the same request:

~~~bash
curl -i http://localhost:8081/api/inventory/1
curl -i http://localhost:8082/api/inventory/1
~~~

Both return `200 OK`, JSON `Content-Type`, and an equivalent data body:

~~~json
{"id":1,"available":true}
~~~

JSON field order, HTTP headers like `Date`/`Content-Length`/`Transfer-Encoding`, and server headers can differ; compare **data meaning, status, and contract** instead of byte-for-byte response equality.

Test a missing resource:

~~~bash
curl -i http://localhost:8081/api/inventory/9
curl -i http://localhost:8082/api/inventory/9
~~~

Both return HTTP `404` when upstream is running as configured. Spring Boot may generate different default error bodies across stacks/configurations, especially without uniform `ProblemDetail` enabled. **Matching status codes do not imply identical error-body contracts**; if frontends need a uniform body, standardize with `@RestControllerAdvice` on each stack and schema-test it.

Test stopped backend: stop `SlowInventoryServer`, then send `/api/inventory/1` to both gateways. Under the example's catch/mapping logic, **connection failures** map to `502 Bad Gateway`. When the backend runs but exceeds the timeout, MVC may map an I/O timeout to 502 whereas WebFlux returns 504 from `Mono.timeout`; that difference is explicitly noted rather than disguised as "identical semantics."

Use `curl -w` to measure single-request latency:

~~~bash
curl -s -o /dev/null -w "MVC total=%{time_total}s\n" http://localhost:8081/api/inventory/1
curl -s -o /dev/null -w "WebFlux total=%{time_total}s\n" http://localhost:8082/api/inventory/1
~~~

`/dev/null` is a Unix-like path; on Windows use an appropriate HTTP CLI/script or inspect `curl -w` without `-o /dev/null`. Single-request time with no queuing is dominated by upstream latency and does not prove either stack is faster.

## 8. LoadProbe: measuring concurrent requests in Java 17

Create standalone `probe/LoadProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class LoadProbe {
    record Result(int status, long elapsedMs) {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println(
                    "Usage: java LoadProbe <baseUrl> [requestCount]");
            System.exit(2);
        }

        String baseUrl = args[0].replaceAll("/+$", "");
        int count = args.length == 2 ? Integer.parseInt(args[1]) : 40;
        if (count < 1 || count > 2000) {
            throw new IllegalArgumentException("requestCount must be 1..2000");
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                    URI.create(baseUrl + "/api/inventory/1"))
                .GET()
                .timeout(Duration.ofSeconds(15))
                .build();

        List<CompletableFuture<Result>> pending = new ArrayList<>();
        long globalStart = System.nanoTime();

        for (int i = 0; i < count; i++) {
            long requestStart = System.nanoTime();
            CompletableFuture<Result> one = client.sendAsync(
                    request, HttpResponse.BodyHandlers.discarding())
                .handle((response, error) -> new Result(
                    error == null ? response.statusCode() : -1,
                    TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - requestStart)));
            pending.add(one);
        }

        CompletableFuture.allOf(
                pending.toArray(CompletableFuture[]::new)).join();

        long ok = pending.stream()
                .map(CompletableFuture::join)
                .filter(result -> result.status() == 200)
                .count();

        long[] latencies = pending.stream()
                .map(CompletableFuture::join)
                .mapToLong(Result::elapsedMs)
                .sorted()
                .toArray();

        int p95Index = (int) Math.ceil(count * 0.95) - 1;
        long totalMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - globalStart);

        System.out.printf(
                "requests=%d ok=%d failed=%d totalMs=%d p95Ms=%d%n",
                count, ok, count - ok, totalMs, latencies[p95Index]);
    }
}
~~~

Compile in `probe/`:

~~~bash
javac LoadProbe.java
~~~

Run **against one gateway at a time**, never concurrently:

~~~bash
java LoadProbe http://localhost:8081 40
java LoadProbe http://localhost:8082 40
~~~

The program prints a line formatted as:

~~~text
requests=<N> ok=<M> failed=<N-M> totalMs=<measured> p95Ms=<measured>
~~~

Values in `<...>` are **measured placeholders**, not fixed numeric outputs. With the demo processes healthy, most or all requests are expected to return 200; any failures should be investigated rather than ignored.

`LoadProbe` tries to launch many HTTP requests close together using `HttpClient.sendAsync(...)`. It is a learning tool, **not a full load generator with warm-up, rate control, coordinated-omission correction, or full latency distributions**. `totalMs` is elapsed time from launching requests until all complete; `p95Ms` is the empirical percentile of latencies recorded around `sendAsync`. With 40 samples, percentiles are noisy and sensitive to client scheduling; proper conclusions require multiple runs and adequate sample sizes.

## 9. Expected structural outcomes, not predicted numbers

When 40 requests all wait on a 300 ms upstream, two structural patterns are typically observed (exact behavior is not guaranteed identical on every machine):

**In MVC with Tomcat max 8 request workers:**

- If all 40 requests arrive nearly together, around 8 concurrent controller invocations appear while others wait for a worker.
- Start/end logs usually show the same servlet thread; while waiting on upstream, that thread serves no other requests.
- Controller `active` typically does not exceed the active controller request threads. It can be under 8 if client/network saturation is not reached.
- Tail latency can climb in "waves" when concurrency exceeds capacity. Wave counts and total time still depend on connection scheduling, upstream pooling, and JVM warmup.

**In WebFlux with Reactor Netty + WebClient:**

- Many subscriptions can remain open using relatively few event-loop threads; event loops do not block while awaiting upstream.
- Logged `active` can exceed the event-loop thread count because it counts **in-flight awaiting publishers**, not threads.
- Upstream wait time still exists; WebFlux does not make 300 ms network/backend latency "vanish."
- If WebClient's connection pool, upstream thread pool, CPU, queues, logging, or client saturate, p95/total time can still rise sharply.

### Why you must not use one number to declare WebFlux the winner

In this setup we **deliberately capped Tomcat at 8 workers** without imposing an equivalent resource budget on WebFlux. That demonstrates the effect of **thread-waiting models** under a specific configuration, not a fair framework-wide comparison.

To evaluate seriously:

1. Run warm-up iterations so JIT and HTTP connection reuse stabilize.
2. Measure multiple rounds and report median/p95/p99, throughput, CPU, memory/GC, connection counts, thread counts, and errors.
3. Ensure upstream does not become the bottleneck; if it does, state clearly that you are measuring upstream saturation.
4. Use identical hosts/configs and comparable CPU/memory/network limits; record Java/Spring/Netty/Tomcat versions and settings.
5. Also benchmark **MVC async using WebClient/CompletionStage**, not just blocking MVC, when high I/O wait efficiency matters.
6. Test variants with real blocking business work (JDBC/JPA), CPU-bound compute, and streaming, because "reactive = faster" is a false generalization.
7. Test timeouts, cancellation, backpressure, and error rates, not just happy paths.

For real monitoring, configure Micrometer/Actuator appropriately per app to observe `http.server.requests`, Tomcat busy threads, Reactor Netty connection pools, and scheduler metrics; exact meter/tag names depend on version and config.

## 10. Difference between blocking servlet threads and non-blocking event loops

A synchronous servlet thread waiting on RestClient:

~~~text
Tomcat-Worker-1: [controller]->[HTTP call--------waiting--------]->[JSON]
Tomcat-Worker-2: [controller]->[HTTP call--------waiting--------]->[JSON]
Tomcat-Worker-3: [controller]->[HTTP call--------waiting--------]->[JSON]
...
       in-flight requests bounded by worker pool and other resources
~~~

Many non-blocking WebFlux requests:

~~~text
reactor-http-nio-1: [accept][subscribe][socket-event][write][accept]...
reactor-http-nio-2: [accept][subscribe][socket-event][write][accept]...
         |              |               |
         +--- many upstream requests awaiting HTTP responses
              without needing one blocking worker per request
~~~

This is a logical diagram, not an exact depiction of scheduler internals. Netty runs worker event loops and networking tasks; operator chains may execute on other threads.

### Wrong: forcing WebFlux back into blocking

~~~java
@GetMapping("/bad/{id}")
Inventory wrong(@PathVariable int id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(Inventory.class)
            .block();
}
~~~

When executed on a Reactor event loop, `block()` is disallowed and can throw `IllegalStateException`. Even if blocking runs on another thread, it wastes the non-blocking model WebFlux provides.

Right:

~~~java
@GetMapping("/good/{id}")
Mono<Inventory> correct(@PathVariable int id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .bodyToMono(Inventory.class);
}
~~~

Both snippets above are integration illustrations assuming `webClient` and `Inventory`. In WebFlux, return the publisher; never call `subscribe()` manually and return from the controller before results arrive. Returning the publisher lets the framework manage status, errors, cancellation, tracing, and response lifecycle.

### Blocking code you cannot eliminate

If the business layer must invoke synchronous JDBC/JPA or a legacy blocking client inside a reactive pipeline, wrap **only** the blocking segment:

~~~java
Mono<Inventory> result = Mono.fromCallable(
                () -> legacyInventoryRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

This is a bounded interop measure; it does not make the repository reactive or allow DB queries to run unbounded. When many components are blocking, synchronous MVC often offers greater simplicity and control; **using WebFlux is not mandatory for every modern web API**.

## 11. Aligning behavior on errors, timeouts, and client cancellation

### Upstream returns 404

Both RestClient and WebClient treat HTTP 4xx/5xx as errors by default under `retrieve()` (with APIs like `body(...)` and `bodyToMono(...)` here). Both controllers map upstream 404 to gateway 404. However, default error bodies and exception handling may differ unless standardized. Tests must verify status, format, and required fields rather than relying on exception messages.

### Upstream returns 5xx

In MVC, `RestClientResponseException` is caught and mapped to gateway 502. In WebFlux, `WebClientResponseException` is mapped in `onErrorMap` to gateway 502. Both indicate the gateway could not fulfill the query due to upstream failure, without necessarily forwarding backend 500 verbatim.

### Upstream is down or network fails

In MVC, synchronous failures in `RestClientException` become 502. In WebFlux, `WebClientRequestException` is an error signal on `Mono` mapped to 502. If a real app needs retries, make them conditional with backoff and idempotency; never retry indefinitely and overload a failing upstream.

### Timeouts

Distinguish timeout types:

- MVC's JDK HTTP request factory configures connect/read timeouts. Exceptions typically surface as I/O failures, which the example maps to 502.
- WebFlux `Mono.timeout(Duration.ofSeconds(2))` emits a pipeline timeout, mapped to 504 in the example. If Netty connection acquisition or setup needs separate policies, configure them explicitly.
- Clients or proxies have their own timeouts; they can fail or close connections before the gateway responds.
- "HTTP gateway timeout" does not mean upstream stopped working. For writes, retries must account for idempotency keys.

If the **API contract requires every timeout to return 504**, add consistent timeout mappers in both apps and tests for each failure mode rather than assuming Spring defaults match.

### Client disconnects and cancellation

Spring WebFlux can propagate cancellation through reactive subscriptions; yet when a client closes a socket, how fast the server notices and whether the upstream request aborts depend on connectors and protocols—it is not always instantaneous. In synchronous MVC, a servlet thread blocked in an HTTP client does not automatically abort the remote operation just because a browser tab closed.

Never treat "cancellation = rollback" or assume "WebFlux never holds resources after a client leaves." Monitor metrics, `doFinally` cleanup, connection pools, and real timeouts.

## 12. Automating contract tests across both gateways

A straightforward option is running upstream on 9090 and both gateways, then hitting them with a real HTTP client using identical test cases:

| Test case | MVC :8081 | WebFlux :8082 | Required assertion |
| --- | --- | --- | --- |
| `GET /api/inventory/1` | 200 | 200 | JSON id=1, available=true |
| `GET /api/inventory/2` | 200 | 200 | JSON id=2, available=true |
| `GET /api/inventory/9` | 404 | 404 | Status 404, never 200 with an error body |
| Upstream 9090 stopped, call id=1 | typically 502 | typically 502 | Network failure handled, no stack trace leaked |
| Client sends HTTP POST to GET-only route | typically 405 | typically 405 | Method contract; `Allow` if returned by framework |
| Run 40 concurrent requests | mostly 200 if capacity allows | mostly 200 if capacity allows | Error count + total/p95 latency |
| Upstream slower than timeout | see MVC mapper | see WebFlux mapper | Do not claim identical status if mappers differ |

These test cases **do not require identical error bodies** when the two projects have not yet implemented a shared error-response contract. If strict equality is required, define a DTO/`ProblemDetail` and `@RestControllerAdvice` in both stacks.

A simple integration test can use JUnit 5 + Java `HttpClient` against apps on random ports, or Spring MVC `MockMvc` and WebFlux `WebTestClient` for speed; however, the "shared real upstream" behavior is observed much more clearly when **running servers on real ports with a real HTTP client**. `MockMvc` does not go through Tomcat sockets, so never use `MockMvc` timings to claim servlet thread saturation.

A plain Java test verifying 200/404 without Spring Test (assuming both gateways and upstream are already running):

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class ContractProbe {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        for (int port : new int[]{8081, 8082}) {
            check(client, port, 1, 200, "\"available\":true");
            check(client, port, 9, 404, null);
        }
        System.out.println("MVC and WebFlux HTTP contract: PASS");
    }

    static void check(HttpClient client, int port, int id,
                      int expectedStatus, String expectedFragment)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/api/inventory/" + id))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != expectedStatus) {
            throw new AssertionError(
                    "port=" + port + " id=" + id
                    + " status=" + response.statusCode());
        }

        if (expectedFragment != null
                && !response.body().contains(expectedFragment)) {
            throw new AssertionError("Unexpected body: " + response.body());
        }
    }
}
~~~

Save `probe/ContractProbe.java` and run:

~~~bash
javac ContractProbe.java
java ContractProbe
~~~

If all assertions pass, exact stdout is:

~~~text
MVC and WebFlux HTTP contract: PASS
~~~

Otherwise, the program throws `AssertionError` or a connection exception instead of printing `PASS`. This program runs on Java 17+ without code changes for either gateway.

## 13. When does MVC async change the comparison?

This is a key distinction to prevent misconceptions.

MVC can use WebClient:

~~~java
@RestController
class MvcAsyncController {
    private final WebClient client;

    MvcAsyncController(WebClient client) {
        this.client = client;
    }

    @GetMapping("/api/async-inventory/{id}")
    Mono<Inventory> inventory(@PathVariable int id) {
        return client.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
~~~

This is an integration snippet requiring a `WebClient` bean, the `spring-webflux` dependency for the client, and the DTO. **It is still Spring MVC if the app runs on the Servlet stack**, rather than automatically becoming WebFlux.

When a controller returns `Mono`, Spring MVC switches to Servlet asynchronous request handling similar to `DeferredResult`. The initial servlet worker can be released while awaiting WebClient, reducing the servlet-worker blocking seen with synchronous MVC RestClient.

However, MVC async still performs Servlet async dispatches, and when streaming reactive responses on the Servlet stack, writes can block or shift to an async executor. WebFlux handles asynchronous/non-blocking I/O deeper inside the server stack. Actual differences must be measured per workload and implementation, not inferred from controller class names.

### Four variants worth benchmarking for a fair comparison

1. Synchronous MVC + RestClient: simple imperative baseline.
2. Async MVC + WebClient returning `Mono`: separates blocking HTTP client effects from the Servlet server model.
3. WebFlux + WebClient: reactive HTTP I/O end to end.
4. MVC with Java virtual threads (if JVM/framework/config support it): enables many blocking tasks under a thread-per-request model with different cost than platform threads, yet **does not make HTTP clients or databases non-blocking**.

The Java 17 used in this demo **does not have finalized virtual threads** (standardized in Java 21). Therefore, do not turn Java 17 measurements into claims about thread costs on Java 21+.

## 14. Common measurement and operational traps

### Measuring only one request

A single request waiting 300 ms on upstream usually shows similar latency in MVC and WebFlux. Meaningful differences emerge under concurrency, thread/resource cost, and slow clients/networks. Measure from 1 → 8 → 40 → 100 requests, recording both latency and errors, while avoiding overwhelming upstream unless studying overload itself.

### Benchmarking in the same process or different workloads

If MVC queries a synchronous DB while WebFlux only awaits `Mono.delay` with no network I/O, they are **not equivalent**. In this demo both issue HTTP GETs to the exact same upstream. Still, MVC's Tomcat thread limit of 8 is an intentional constraint, so treat it as an **experiment illustrating worker limits**, not a comparison of default performance.

### Ignoring connection pools

WebClient's Reactor Netty has connection pools and limits; RestClient depends on its specific request factory/client. If sockets or pending acquisitions are capped, requests wait even when event loops are idle. Monitor active/pending connections and acquire timeouts when scaling.

### Using blocking APIs in WebFlux

A misplaced `Thread.sleep`, blocking JDBC/JPA, or `block()` on the event loop can stall many connections. Replace with reactive drivers or offload bounded blocking segments; `subscribeOn(boundedElastic)` does not change the blocking nature of the underlying I/O.

### Not handling empty reactive sequences

`Mono<Inventory>` can complete empty if upstream returns an empty body. The demo uses `switchIfEmpty(Mono.error(...))` to turn it into 502 instead of silently returning an empty response easily confused with 404 or 200 null. MVC checks `result == null` similarly.

### Misreading thread names in logs

Thread names are clues, not complete metrics. Execution can switch threads across async boundaries, `publishOn`, `subscribeOn`, or I/O callbacks. Use trace IDs/correlation IDs, metrics, and profiling to draw conclusions.

### Skipping error-path verification

Differences in 502/504 status mapping, response bodies, timeouts, and cancellation are where bugs hide when switching frameworks. Write contract tests (happy path, missing resources, timeouts, upstream 5xx, auth, validation, and cancellation) before migrating.

### Mixing both starters and running the wrong stack accidentally

A Spring Boot app containing both `spring-boot-starter-web` and `spring-boot-starter-webflux` usually auto-configures **Spring MVC**. Seeing WebClient or Mono in code does not prove the server runs WebFlux. Verify dependency trees, startup logs, application context type, and the actual embedded server.

## 15. Decision checklist for real projects

| Question | If the answer is... | Action |
| --- | --- | --- |
| Is the path waiting heavily on HTTP/database I/O? | Reactive HTTP but blocking DB | Weigh MVC async/WebClient benefits against offload costs; do not rush into WebFlux. |
| Is most existing code imperative/JPA? | Yes | MVC is usually a sensible default; keep clear contracts and monitor threads. |
| Do you need tens of thousands of open sockets/streams? | Yes, with non-blocking per-message work | WebFlux can be a strong fit, but load test fan-out, pools, and slow consumers. |
| Is the workload mainly CPU-bound? | Yes | Optimize algorithms/CPU/schedulers; reactive does not speed up CPU computation by itself. |
| Do you need backpressure/streaming? | Yes | Evaluate WebFlux and response writing, buffering, and cancellation; MVC also offers async streaming with different I/O traits. |
| Planning a migration? | Yes | Write HTTP contract tests first, test endpoint by endpoint, and measure error rates and p95/p99. |
| Worried about lost/duplicate data after timeouts? | Yes | Design retries/idempotency and persistence; never rely on transport for guarantees. |

**Conclusion:** For querying a slow upstream under the same HTTP contract, MVC + RestClient waits synchronously on a servlet worker, whereas WebFlux + WebClient represents results as `Mono` with non-blocking I/O. Only by observing thread names, in-flight requests, p95, latency, resource limits, and real errors together can you make an informed choice. When workloads are mostly blocking, MVC can be entirely the right choice; when high concurrent I/O and end-to-end reactivity are required, WebFlux is worth validating.

## 16. References

- Spring Framework — Web MVC (Servlet stack): https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework — MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — REST Clients (RestClient, WebClient): https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Spring Framework — WebClient Synchronous Use: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Spring Framework — WebClient Error Handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Reactor Core — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Spring Boot — Web Application Type and Reactive Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
