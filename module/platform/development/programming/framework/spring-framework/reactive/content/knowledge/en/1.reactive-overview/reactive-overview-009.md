# Roadmap from Reactor Chains to a Complete Reactive Application

> **Scope:** Spring Framework – Reactive | **Topic:** Overview. This lesson guides you from thinking in Reactor stream processing to a runnable Spring WebFlux API, then expands into a service with data persistence, testing, security, and operations. The main example uses Java 17+ and Spring Boot 4.0.9. Versions are pinned so the hands-on exercise is reproducible; for production systems, verify currently supported Spring Boot versions before deploying.

## 1. What Should You Be Able to Do After Finishing?

A developer completing this roadmap should be able to:
1. Read **Mono** and **Flux** chains, identifying pipeline assembly time, subscription time, where values are emitted, errors, and completion.
2. Choose the right **map**, **flatMap**, **concatMap**, **zip**, **switchIfEmpty**, **onErrorResume**, **timeout**, and **retryWhen**; understand ordering, concurrency, cold/hot sources, and backpressure.
3. Write **Spring WebFlux** HTTP endpoints returning Mono/Flux without blocking the event loop; connect WebClient and reactive data stores in the same asynchronous chain.
4. Distinguish a runnable demo from real operational choices: durable storage, transactions, resource limits, security, metrics, logs, and traces.
5. Test with **StepVerifier** and **WebTestClient**, simulating errors, subscription cancellation, timeouts, and delays.

**Destination:** an end-to-end processing path from HTTP request → controller → service → repository/WebClient → onNext/onError/onComplete signals → HTTP response, with resource management and observability.

## 2. Mental Model: From Sequential Statements to Signal Chains

In synchronous processing, each call typically waits for a result before moving on. Reactor models work with a **Publisher**; when a **Subscriber** subscribes, the Publisher can emit signals:
- **onSubscribe**: provides a Subscription; the consumer can call request(n) to signal demand.
- **onNext(value)**: a data element; a Reactive Streams-compliant publisher must not emit null.
- **onComplete**: normal completion, with no more data.
- **onError(error)**: termination with an error; after onError/onComplete, no further onNext is valid.
- **cancel**: subscriber cancels the stream, allowing upstream to release resources if supported.

**Mono<T>** represents 0 or 1 value followed by termination; **Flux<T>** represents 0 to many values. Mono.empty() means completing with no data, distinct from Mono.error(...) and distinct from a null value. Mono<Void> is used for operations where only completion matters.

A pipeline is typically **lazy**: calling map/flatMap only builds a description; execution starts upon subscription. In WebFlux, the framework subscribes to the Publisher returned by the controller. In business code, usually return the Mono/Flux intact and let the boundary layer drive subscription, rather than scattering subscribe() calls. Every subscription to a **cold publisher** can re-run the source (e.g., calling an API / saving a record); watch for side effects. A **hot publisher** can emit independently of subscribers, so latecomers may miss events; use share/replay/Sinks deliberately and design buffering policies.

**Backpressure** is the mechanism by which a subscriber reports how many elements it wants to receive. It helps coordinate streams that support demand, but does not automatically limit every hot source, queue, connection, or external system. Combine it with concurrency limits, pools, timeouts, rate limits, and buffer overflow policies.

### Processing Map

~~~text
HTTP request
    ↓
WebFlux controller returns Mono/Flux
    ↓
Service: validate input + compose Publishers
    ↓
Reactive repository / WebClient / event stream
    ↓
onNext, onComplete, or onError
    ↓
HTTP codec writes JSON/SSE and handles cancellation on client disconnect
~~~

The major benefit of non-blocking I/O is that a small number of threads can serve many requests waiting on I/O. That does not mean every task becomes faster: heavy CPU work, synchronous JDBC/JPA, blocking file reads, or a blocking SDK can still stall the event loop if placed in the wrong spot. An application with light, synchronous DB access may fit Spring MVC much better. Choose WebFlux when asynchronous I/O flows, streaming, and load management are genuine needs.

## 3. Master Reactor Chains Before Writing HTTP

### 3.1. What Does Each Operator Do?

| Operator | When to Use | Points to Remember |
| --- | --- | --- |
| map | Synchronously transform each value | Transform function should not return a Publisher and must not return null. |
| flatMap | Call a function returning an async Mono/Flux, allowing interleaved work | Output order may change; bound concurrency if upstream has many elements. |
| concatMap | Subscribe to Publishers sequentially, preserving order | Predictable, though it can reduce throughput. |
| flatMapSequential | Run multiple tasks concurrently while emitting in source order | May buffer heavily if earlier elements arrive slowly. |
| filter / distinct | Select data and remove duplicates | For large datasets, distinct keeps tracking state, so bound inputs. |
| collectList | Collect Flux into Mono<List<T>> | Waits for completion and holds everything in RAM; avoid on infinite streams. |
| zip / zipWith | Combine sources that emit elements | An empty source can make the result empty and cancel other sources. |
| switchIfEmpty | Handle the branch where Mono/Flux emits no value | Use Mono.defer(...) if the fallback has work/side effects to defer. |
| onErrorResume | Recover with a fallback Publisher | Do not turn every error into fake success or hide critical failures. |
| timeout | Cap wait time exceeding budget | Define deadlines per hop and for the overall request. |
| retryWhen | Conditional retries | Retry only transient errors; consider idempotency, backoff, and jitter. |
| doOnNext/doOnError/doFinally | Observe signals, cleanup/metrics | Do not use them as business data transformation steps. |

**Chain example:** the input is names that are trimmed, deduplicated, and normalized; this code is a Java fragment placed inside a method with Reactor and java.util.Locale imports.

~~~java
Flux<String> names = Flux.just("  an ", "binh", "an", "  ");
Mono<List<String>> normalized = names
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .distinct()
    .map(s -> s.toUpperCase(Locale.ROOT))
    .collectList();

// Only explicitly wait in a CLI program or test:
System.out.println(normalized.block());
~~~

**Stdout:** [AN, BINH]. **Do not put block() in a WebFlux controller.** The Flux source here is finite, so collectList is appropriate; for an infinite event stream, bound it or return the Flux directly.

### 3.2. Distinguishing map and flatMap

~~~java
Mono<String> userId = Mono.just("u-7");

// Processing function directly creates a string.
Mono<String> label = userId.map(id -> "User " + id);

// Processing function returns an asynchronous Publisher.
Mono<String> profile = userId.flatMap(id -> fetchProfile(id));
~~~

In the example, fetchProfile(String) **represents a real application method returning Mono<String>**, not a built-in Reactor function; this fragment illustrates types, not a standalone program. Using map with fetchProfile would produce Mono<Mono<String>>, which is usually unintended.

### 3.3. Controlling Order and Concurrency

~~~java
Flux<String> ids = Flux.just("u1", "u2", "u3");
Flux<String> sequential = ids.concatMap(this::loadUser);
Flux<String> concurrent = ids.flatMap(this::loadUser, 4);
~~~

Assume loadUser(String) returns Mono<String>. concatMap preserves order and processes only one inner source at a time; flatMap allows multiple operations concurrently, capped at 4 in the example, without guaranteeing output order. Do not pick an excessively large concurrency number merely because throughput rises on a dev machine.

### 3.4. Threads and Schedulers

Reactor does not automatically create threads for each operator. **subscribeOn(scheduler)** affects the subscribe path and upstream source; commonly placed near blocking I/O sources. **publishOn(scheduler)** switches the execution context for downstream operators. Do not switch schedulers frequently without a measured reason.

~~~java
Mono<String> fromLegacyLibrary = Mono
    .fromCallable(() -> legacyBlockingRead())
    .subscribeOn(Schedulers.boundedElastic());
~~~

In the example, legacyBlockingRead() is an existing blocking call in the system. This is a **temporary bridge**, not something that makes a blocking library non-blocking. Schedulers.boundedElastic() has worker and queue limits; monitor it as load grows. Do not use Schedulers.parallel() for blocking I/O. Avoid block(), blockFirst(), Thread.sleep(), and blocking JDBC directly on the Netty event loop.

### 3.5. Errors Are Terminal Signals

~~~java
Mono<String> result = remoteCall()
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, ex -> Mono.just("cached"));
~~~

This fragment requires remoteCall() returning Mono<String> and the corresponding imports. The fallback is valid only if cached data is acceptable under business rules. WebClient timeouts, HTTP errors, and domain errors should be classified separately; onErrorResume does not revive the errored publisher to emit further items, instead switching to a replacement Publisher. Retry can **re-subscribe** to the source, meaning side effects replay if not idempotent.

## 4. Learning Roadmap and Completion Milestones

| Stage | Core Competency | Practice Exercise | Completion Criteria |
| --- | --- | --- | --- |
| 1. Reactor basics | Signals, Mono, Flux, lazy, cold/hot | Transform a list with map/filter/collectList | Can explain signals and execution timing. |
| 2. Pipeline composition | flatMap/concatMap/zip, empty/error | Compose 2 simulated I/O tasks, choose fallback | Tests cover success, empty, and error; knows when order changes. |
| 3. Resources | Schedulers, backpressure, cancel, timeout | Wrap a blocking call with boundedElastic; bound concurrency | Event loop never locked; cancel/timeout behave as expected. |
| 4. WebFlux HTTP | Annotated controllers or functional routes, JSON codec, HTTP status | Build GET/POST/PATCH APIs using Mono/Flux | Can run curl and test 201/400/404. |
| 5. Reactive integration | WebClient, reactive repositories, transactions | Connect external service and DB via R2DBC | No manual subscribe, no JDBC on event loop, sensible retry handling. |
| 6. Operations | Testing, security, metrics, tracing, capacity | Measure latency, load, and failure modes | Dashboards, alerts, timeout budgets, security, and rollout procedure in place. |

The roadmap does not require migrating a stable Spring MVC application to WebFlux. Each stage should include a practical load/latency measurement and a test before scaling further.

## 5. Runnable Sample Project: Reactive Tasks API

This project stores tasks in memory so learners can run it immediately without a database. It is **a complete WebFlux application aimed at learning HTTP → service → Reactor → JSON → test**, though data is lost on restart and does not yet meet real product durability requirements. The next step replaces the service/repository layer with R2DBC while keeping the HTTP contract.

**Requirements:** JDK 17+, Maven 3.6.3+, and port 8080 free. Uses Spring Boot 4.0.9 (Spring Framework 7); Boot manages compatible Reactor versions, so do not pin a different reactor-core version outside the BOM.

Structure:

~~~text
reactive-tasks/
├── pom.xml
├── src/main/java/com/example/reactivetasks/
│   ├── ReactiveTasksApplication.java
│   ├── Task.java
│   ├── CreateTaskRequest.java
│   ├── TaskService.java
│   └── TaskController.java
└── src/test/java/com/example/reactivetasks/
    └── TaskControllerTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-tasks</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
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

The Spring Boot WebFlux starter brings WebFlux, Reactor Netty, JSON codecs, and Reactor onto the classpath. The WebFlux Test starter provides WebFlux testing infrastructure along with Reactor Test in this sample configuration.

### 5.2. Entry Point

**src/main/java/com/example/reactivetasks/ReactiveTasksApplication.java**

~~~java
package com.example.reactivetasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTasksApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTasksApplication.class, args);
    }
}
~~~

### 5.3. Data Types

**src/main/java/com/example/reactivetasks/Task.java**

~~~java
package com.example.reactivetasks;

public record Task(long id, String title, boolean done) {}
~~~

**src/main/java/com/example/reactivetasks/CreateTaskRequest.java**

~~~java
package com.example.reactivetasks;

public record CreateTaskRequest(String title) {}
~~~

Java records are concise immutable types for JSON data exchange. For real public contracts, separate DTOs from persistence entities and add structured validation.

### 5.4. Service: Lazy Publisher Creation and Key-Safe Updates

**src/main/java/com/example/reactivetasks/TaskService.java**

~~~java
package com.example.reactivetasks;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class TaskService {
    private final ConcurrentMap<Long, Task> tasks = new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong();

    public Mono<Task> create(CreateTaskRequest request) {
        return Mono.defer(() -> {
            if (request == null || request.title() == null ||
                    request.title().isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title must not be blank"));
            }
            Task task = new Task(
                ids.incrementAndGet(), request.title().trim(), false);
            tasks.put(task.id(), task);
            return Mono.just(task);
        });
    }

    public Mono<Task> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(tasks.get(id)));
    }

    public Flux<Task> findAll() {
        return Flux.defer(() ->
            Flux.fromIterable(new ArrayList<>(tasks.values()))
                .sort(Comparator.comparingLong(Task::id)));
    }

    public Mono<Task> complete(long id) {
        return Mono.defer(() ->
            Mono.justOrEmpty(tasks.computeIfPresent(id, (key, old) ->
                new Task(old.id(), old.title(), true))));
    }
}
~~~

- **Mono.defer** delays creating/modifying data until subscription. Re-subscribing to the Mono from create() can repeat the creation; do not blindly retry POSTs.
- **ConcurrentHashMap.computeIfPresent** updates the same key atomically on the map, avoiding separate read-then-write in the demo. **AtomicLong** issues sequential IDs within a single process.
- **findAll()** snapshots and sorts the entire dataset in RAM; use only for small datasets. In real systems, push pagination/sorting down to the database.
- Return Mono.empty() when the ID is missing so the HTTP layer decides 404, rather than coupling HTTP status into repositories. In this sample the service uses ResponseStatusException for input errors to keep file count low; larger systems should separate domain exceptions and error mapping.

### 5.5. Controller: Framework Manages the Subscription

**src/main/java/com/example/reactivetasks/TaskController.java**

~~~java
package com.example.reactivetasks;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<Task>> create(
            @RequestBody Mono<CreateTaskRequest> body) {
        return body.flatMap(service::create)
            .map(task -> ResponseEntity
                .created(URI.create("/api/tasks/" + task.id()))
                .body(task));
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<Task> get(@PathVariable long id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "task not found")));
    }

    @PatchMapping("/{id}/complete")
    public Mono<Task> complete(@PathVariable long id) {
        return service.complete(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "task not found")));
    }
}
~~~

The controller does not call subscribe(), block(), or CompletableFuture.join(). WebFlux subscribes to the Publisher when processing the request, passes results through the JSON encoder, and handles HTTP 201/400/404. @RequestBody Mono<CreateTaskRequest> reads the body reactively; for missing/malformed JSON requests, WebFlux handles input errors. For real APIs, standardize error payloads using Problem Details, field validation, and correlation IDs.

### 5.6. Run and Test HTTP

In the directory containing pom.xml:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

In another terminal (e.g., using curl on Linux/macOS, or curl.exe on Windows):

~~~bash
curl -i -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Learn Reactor"}'
curl http://localhost:8080/api/tasks/1
curl -X PATCH http://localhost:8080/api/tasks/1/complete
curl http://localhost:8080/api/tasks
curl -i http://localhost:8080/api/tasks/999
~~~

Starting with empty memory, POST returns **201 Created**, Location: /api/tasks/1, and body:

~~~json
{"id":1,"title":"Learn Reactor","done":false}
~~~

GET /api/tasks/1 returns that record; PATCH /api/tasks/1/complete returns the same id/title with done=true; GET on the collection returns a JSON array of existing tasks. GET /api/tasks/999 returns **404 Not Found**; empty or whitespace-only title errors return **400 Bad Request**. Headers, error messages, and additional error fields may vary depending on Spring configuration; do not assume a fixed error JSON structure.

## 6. Testing: From Signals to HTTP

**src/test/java/com/example/reactivetasks/TaskControllerTest.java**

~~~java
package com.example.reactivetasks;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class TaskControllerTest {

    @Test
    void serviceEmitsOneCreatedTask() {
        TaskService service = new TaskService();

        StepVerifier.create(service.create(
                new CreateTaskRequest("Learn Reactor")))
            .assertNext(task -> {
                assertEquals(1L, task.id());
                assertEquals("Learn Reactor", task.title());
                assertFalse(task.done());
            })
            .verifyComplete();
    }

    @Test
    void httpCreatesAndReadsTask() {
        WebTestClient client = WebTestClient
            .bindToController(new TaskController(new TaskService()))
            .build();

        client.post().uri("/api/tasks")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateTaskRequest("Learn Reactor"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .valueMatches("Location", "/api/tasks/[0-9]+")
            .expectBody()
            .jsonPath("$.title").isEqualTo("Learn Reactor");

        client.get().uri("/api/tasks/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.done").isEqualTo(false);

        client.get().uri("/api/tasks/999")
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

**StepVerifier** checks onNext and onComplete along with order; if a chain errors you can use expectErrorMatches(...), or if it simply completes empty use verifyComplete() without expectNext. **WebTestClient.bindToController(...)** tests the HTTP layer in memory without opening port 8080. When integrating repositories, add @SpringBootTest with a real database or Testcontainers to test transactions, migrations, and queries; use mocks at the unit level when appropriate.

Important scenarios for a production test suite: 400 on bad input, 404 on missing records, 401/403 on authorization, 5xx downstream failures, timeouts, client cancellation, concurrent update race conditions, backpressure demand, concurrency limits, and transaction rollbacks. Use StepVerifier.withVirtualTime for timer/delay streams to avoid waiting in real time; create the Publisher inside the withVirtualTime supplier so VirtualTimeScheduler applies properly.

## 7. Integrating WebClient While Keeping the Flow Non-Blocking

**WebClient** replaces blocking with RestTemplate or calling .block() in a controller when an asynchronous HTTP client is needed. The following fragment can live in a bean injected with WebClient.Builder; assume the task API at localhost:8080 is running:

~~~java
WebClient client = builder.baseUrl("http://localhost:8080").build();

Mono<Task> task = client.get()
    .uri("/api/tasks/{id}", 1)
    .retrieve()
    .bodyToMono(Task.class)
    .timeout(Duration.ofSeconds(2));
~~~

The builder and Task references in this fragment come from the existing app; the code illustrates usage inside a method, not a standalone Java file. By default retrieve() turns HTTP 4xx/5xx into errors; if detailed mapping is needed, add onStatus(...) or use exchangeToMono(...) while consuming/releasing the body properly. Configure base URLs, connection pools, connect/read timeouts, TLS, authentication, proxies, and response size limits per environment. **Do not call block() to extract results**; instead, flatMap results into the service's Mono/Flux chains.

When combining multiple sources:
- Independent sources that must all yield values: use Mono.zip(a, b) if both sources can run concurrently. Handle the case where one Mono is empty before zipping.
- Need to call API B based on output A: use a.flatMap(this::callB).
- Many IDs: use Flux.fromIterable(ids).flatMap(this::callRemote, 8) to bound concurrency; if order must be preserved, use concatMap or flatMapSequential.
- When retrying, retry only errors identified as transient, with bounded attempts, exponential backoff, and an overall time budget; POST/PATCH need idempotency keys or duplicate-write protection.
- If an external service is slow, apply appropriate bulkheads/rate limits/circuit breakers and protect request budgets; automatic unbounded retries amplify incidents.

## 8. Moving from In-Memory to Reactive Persistence

The InMemory TaskService pattern is a starting point; to turn it into a real service, extract a **TaskRepository** port and replace the map with a database backed by a reactive driver. With PostgreSQL, you can choose **Spring Data R2DBC** alongside the R2DBC PostgreSQL driver:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

This is an **extension** to the pom.xml above; these two dependencies alone do not create a database or migrations. Supply ConnectionFactory/R2DBC URL from secure configuration, create schemas via migrations, and switch Task from an HTTP DTO to an entity annotated with @Table/@Id. Example interface:

~~~java
interface TaskRepository
        extends ReactiveCrudRepository<TaskEntity, Long> {
    Flux<TaskEntity> findByDone(boolean done);
}
~~~

In this fragment, TaskEntity is the persistence entity of the real application; you must define it and import org.springframework.data.repository.reactive.ReactiveCrudRepository and reactor.core.publisher.Flux. The service will invoke repository.save(...), findById(...), and findAll() returning Mono/Flux directly, map entity → DTO, and handle business consistency. Do not reuse the example's Task record directly as an entity just because the name matches; identity, migrations, unique constraints, time types, and audit fields need explicit design.

**Reactive transactions:** use @Transactional on methods returning a Publisher with an appropriate ReactiveTransactionManager, or TransactionalOperator to wrap multiple related write steps; transactions run in **Reactor Context**, not relying on ThreadLocal like synchronous transactions. Do not mix synchronous JDBC/JPA with R2DBC inside the same reactive transaction and assume rollback spans both. For cross-service operations, use outbox/idempotency/compensation rather than assuming automatic distributed transactions.

**Pagination and streaming:** do not return entire unbounded tables or call collectList() on large datasets. Enforce page sizes, stable sort keys, and cursor/keyset pagination when appropriate; watch JSON size limits, buffers, and cancel/timeout handling on client disconnect. Measure connection pool pressure and active queries, because non-blocking does not give a database unlimited connections.

## 9. Errors, Validation, Security, and Operations

### 9.1. Defining the Error Contract

Standardize HTTP codes by category: **400** invalid input, **401** unauthenticated, **403** forbidden, **404** not found, **409** version/unique key conflict, **429** rate limit exceeded, **5xx** system/dependency error. Domain errors should be mapped centrally via @RestControllerAdvice or WebExceptionHandler; never leak stack traces, tokens, or secret queries in responses. Use optimistic locking/versioning or unique constraints for update contention, especially when migrating from a map to a DB.

Validate required fields, lengths, formats, and valid values right at the API boundary; with Bean Validation, add the validation starter and jakarta.validation annotations. Using Mono<T> does not automatically enable validation; choose placement and activation matching your controller model.

### 9.2. Reactive Security

Use Spring Security with WebFlux support, configure **SecurityWebFilterChain**, authenticate via OAuth2/JWT/sessions as required by the architecture, authorize endpoints and resources, and enforce CSRF protection when using browser cookies/sessions. Propagate security context and traces through Reactor Context via framework mechanisms rather than relying on ThreadLocal/Servlet Filters. Configure TLS and manage secrets outside source code. For SSE/WebSocket, check both initial connection authentication and per-session/per-event limits.

### 9.3. Observability and Resource Management

Enable Actuator health/readiness/liveness, and metrics for error rates, p50/p95/p99 latency, in-flight requests, event-loop blocking, connection pools, queues, and timeouts. Connect Micrometer tracing/OpenTelemetry when cross-service observability is needed; log with correlation IDs and avoid logging sensitive data. Align timeouts across HTTP clients, DB, end-to-end boundaries, and load balancers. Measure the impact of flatMap concurrency, buffers, payload sizes, and upstream limits under concurrent load; check throughput, memory, CPU, GC, and connection counts together.

A non-blocking pipeline can still overload when:
- A hot source emits faster than downstream, building huge buffers or dropping events.
- flatMap issues too many concurrent I/O requests at once, exhausting pools/DB.
- collectList/sort/groupBy accumulates large state or never completes.
- Offloading to boundedElastic dumps all blocking work into its queue.
- Cancellation, timeouts, and resource cleanup are ignored.
- Unbounded retries amplify an incident.

For genuine streaming data such as events, evaluate **Server-Sent Events (SSE)** or WebSocket; specify lifecycle, reconnect behavior, event IDs, replay, acceptable data loss, and hop-by-hop backpressure. Do not assume any arbitrary Flux automatically becomes an efficient stream if an HTTP consumer or proxy is buffering.

## 10. Common Mistakes to Self-Diagnose

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Controller returns Mono yet requests still stall | Blocking JDBC/SDK or heavy CPU work on the event loop | Use reactive drivers or temporarily isolate blocking on boundedElastic; profile it. |
| Data written twice | Re-subscribing/retrying a cold publisher with side effects | Keep one intentional subscription flow; design writes for idempotency. |
| List returns out of order | flatMap emits in completion order | Use concatMap/flatMapSequential when order is part of the contract. |
| Missing ID does not return 404 | Mono.empty() passes through HTTP boundary unmapped | switchIfEmpty to an appropriate domain error/ResponseStatusException. |
| Data loss or growing RAM while streaming | Hot source, unbounded buffer, collectList | Configure backpressure, buffer limits, pagination, or direct streaming. |
| Test hangs forever | Infinite publisher or missing terminal signal | Check take/timeout/cancel; use StepVerifier with explicit expectations. |
| Security/trace context lost | Relied on ThreadLocal across scheduler switches | Use Reactor Context and official context-propagation integrations. |
| Retries overload DB/remote service | Retrying all errors without backoff/budget | Target transient errors, bound retries, add backoff+jitter and circuit breakers. |
| Production incidents hard to trace | Missing metrics/traces and request budgets | Add instrumentation, correlation IDs, SLOs, and thresholded alerts. |

## 11. Checklist for Completing a Reactive Service

**Code discipline:** All business APIs return Mono/Flux; no subscribe()/block()/Thread.sleep() in request paths; distinguish error/empty; bound flatMap concurrency; explicit cancellation and timeouts. Test every signal branch with StepVerifier.

**HTTP:** Clear REST contracts, consistent statuses and JSON; WebTestClient covering success/4xx/5xx; authentication and authorization; validation; error responses do not leak secrets; CORS/CSRF aligned with architecture.

**Integration:** Reused WebClient with measured connection pools and timeouts; DB uses R2DBC/reactive drivers or clearly isolated remaining blocking parts; migrations and transactions tested; idempotency for writes and controlled retries.

**Production readiness:** health/readiness, metrics/tracing/logging, graceful shutdown, externalized config/secrets, load tests, payload/stream/concurrency limits, dashboards and alerts, rollback plan. Measure before and after with identical workloads; the goal is load resilience and stability, not using Mono/Flux everywhere.

## 12. Further Learning Resources

1. Spring WebFlux reference: https://docs.spring.io/spring-framework/reference/web/webflux.html — HTTP handling mechanics, annotated and functional endpoints.
2. Reactor reference: https://projectreactor.io/docs/core/release/reference/ — operators, backpressure, schedulers, errors, and testing.
3. Spring Boot reactive web: https://docs.spring.io/spring-boot/reference/web/reactive.html — auto-configuration and deployment.
4. Spring Boot 4.0.9 system requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html — Java and build tools.
5. Spring Data R2DBC repositories: https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html — reactive data repositories.

**Hands-on path:** get the Tasks API sample running → add validation and error formatting → replace the in-memory service with R2DBC + migrations → integrate a WebClient → add timeouts/idempotent retries → write StepVerifier/WebTestClient/Testcontainers tests → load-test, enable security/observability, and verify readiness before rollout. Each step must keep existing tests passing and add tests for new behavior.