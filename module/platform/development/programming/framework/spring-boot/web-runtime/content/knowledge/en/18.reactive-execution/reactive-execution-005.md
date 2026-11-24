# Avoiding `block()` and Manual `subscribe()` in the Request-Handling Flow

## 1. Objectives and Scope

In a **Spring Boot WebFlux** application, a Controller typically returns **Mono<T>** (zero or one value) or **Flux<T>** (zero, one, or many values). Instead of making the HTTP thread wait for a result, we describe a **reactive processing pipeline** and return the Publisher to the framework.

Two design mistakes commonly break that model:

1. Calling **block()** inside a Controller, WebFilter, or callback running on the event loop to wait synchronously for data.
2. Calling **subscribe() manually** inside the request-handling path, turning part of the work into an independent branch detached from the main request.

Rule of practice: **within the WebFlux request-handling path, compose Publishers using operators and return that Publisher to Spring WebFlux; let the framework manage subscription, response writing, errors, and cancellation**. When integrating synchronous/blocking APIs is unavoidable, isolate them on an appropriate scheduler and return `Mono`/`Flux` instead of waiting with `block()`.

This lesson covers **reactive execution for HTTP requests**, specifically with Reactor and WebFlux on Reactor Netty. Spring MVC can use WebClient or return Mono via its own adaptation mechanism; do not mechanically apply Netty event-loop conclusions to every Spring MVC application.

## 2. Who Actually Executes Mono/Flux?

Publishers like Mono/Flux describe data sources and transformations; most pipelines are **lazy**: only upon subscription does the source begin running. Under Reactive Streams, data/errors/completion are exchanged via signals:

- **onSubscribe:** registers the subscriber with the source; may request data via request(n).
- **onNext:** emits a value; Mono emits at most one onNext.
- **onError:** terminates with an error; no onComplete follows.
- **onComplete:** terminates successfully; no onError follows.
- **cancel:** subscriber asks to stop processing when no further data is needed; immediate halting depends on the source and external resources.

Example standard Controller:

~~~java
@GetMapping("/products/{id}")
Mono<ProductDto> getProduct(@PathVariable String id) {
    return productService.findById(id)
            .map(ProductDto::from);
}
~~~

This is an **illustrative snippet**, assuming ProductDto and productService exist. The Controller does **not** call block() or subscribe(). Spring WebFlux receives the Mono, attaches a subscriber suitable for the HTTP response, handles signals, applies response writing, and stops/cancels when needed. Ultimate subscription belongs to the framework.

Conceptual flow:

~~~text
HTTP request
    |
    v
WebFlux invokes Controller method
    |
    v
Controller assembles and RETURNS Mono/Flux
    |
    v
WebFlux attaches Subscriber and requests data
    |
    +--> non-blocking I/O source (WebClient, reactive repository...)
    |       |
    |       +--> map / flatMap / filter / timeout / onErrorResume
    |                       |
    +<---------------------+
    |
    v
Write HTTP response, complete/error, or handle cancellation
~~~

**Composing a chain is not waiting for a value.** For example, Mono.just("A").map(String::toLowerCase) is a Publisher describing a transformation; you do not need block() to extract a value to pass to the next operator.

**Note:** some operations happen immediately when *creating* the Publisher: argument expressions to Mono.just(...) are evaluated upfront, so Mono.just(legacyDao.findById(id)) can still hit the DB synchronously **right inside the Controller**. Use Mono.defer or Mono.fromCallable when you need to defer the call until subscription.

## 3. Why Is `block()` Inside a Request Handler Dangerous?

**block()** subscribes to the Publisher and **waits** until a value, error, or completion arrives. It turns an asynchronous point into a synchronous call on whichever thread invokes block(). Variants such as blockOptional(), blockFirst(), blockLast(), toIterable(), and toStream() can cause similar waiting.

With Spring WebFlux on Reactor Netty, the number of **event-loop threads** is small and shared across many connections. If a callback holds the event loop while waiting on I/O, other requests slow down even when CPU is idle.

Reactor also detects threads marked **NonBlocking**: calling Reactor blocking APIs such as block() on them can throw **IllegalStateException**. The error message usually notes that blocking operations are unsupported on the current thread; exact thread names depend on the environment. Do not rely on that exception as a complete safeguard: blocking JDBC calls, Thread.sleep(), or CompletableFuture.join() still block without throwing Reactor's exception.

### 3.1. Wrong Example: Reading WebClient Result with `block()`

~~~java
// WRONG in a WebFlux request handler; illustrative snippet only.
@GetMapping("/profiles/{id}")
ProfileDto profile(@PathVariable String id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ProfileDto.class)
            .block();
}
~~~

Consequences:

- The Controller holds the thread until the downstream HTTP response arrives.
- On a NonBlocking event loop, block() may throw IllegalStateException.
- Increasing timeouts does not make the processing non-blocking.
- Calling block() introduces a hidden subscription point inside application code rather than letting the framework manage the chain.
- Even if running on a thread permitted to block, the app loses thread efficiency during waiting.

### 3.2. Right Way: Return `Mono` for WebFlux to Subscribe

~~~java
// RIGHT in WebFlux; assumes WebClient is injected.
@GetMapping("/profiles/{id}")
Mono<ProfileDto> profile(@PathVariable String id) {
    return webClient.get()
            .uri("/profiles/{id}", id)
            .retrieve()
            .bodyToMono(ProfileDto.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

Import java.time.Duration, reactor.core.publisher.Mono, and any used types. **This is a snippet inside a Controller that already has WebClient**, not a standalone compilable Java file. WebClient creates the HTTP publisher, and the framework subscribes when writing the response.

Set timeouts per business requirements; Mono-level timeout is one safeguard, though you should also configure connect/read timeouts on the HTTP client. With WebClient.retrieve(), 4xx/5xx statuses by default emit WebClientResponseException error signals; map errors according to your API contract rather than turning everything into 200 or returning null.

### 3.3. Do Not Relocate the Mistake While Losing Reactivity

The following **do not** solve the issue:

- **Mono.just(blockingCall())**: blockingCall() executes immediately when creating the Mono.
- **Mono.just(publisher.block())**: still blocks on the current thread before returning the Mono.
- **Mono.fromCallable(() -> publisher.block())** without switching to a proper scheduler: upon subscription, the callback can still block the event loop.
- **Mono.fromCallable(() -> legacyCall()).subscribeOn(Schedulers.parallel())**: parallel is meant for short/CPU work, not blocking I/O calls.
- **new Thread(...).start() per request**: bypasses scheduler/queue control, is hard to observe or cancel, and risks exhausting resources.
- **CompletableFuture.get()/join() or Thread.sleep() inside map/flatMap**: still blocks the thread running the callback.

If all called APIs already support non-blocking execution, **compose them directly**. If an unavoidable blocking source cannot be replaced, use the isolation pattern in Section 7.

## 4. Why Is Manual `subscribe()` in a Request Handler Also Wrong?

**subscribe() is not the same as subscribeOn().** subscribe() is a *terminal operation* that starts a new subscription. subscribeOn(scheduler) only configures where source subscription will occur **when a subscriber actually arrives**.

In WebFlux, calling subscribe() inside a Controller/Service usually spawns work **outside the Publisher returned to the HTTP framework**.

### 4.1. Wrong Example: Launching Side Effects Manually

~~~java
// WRONG: non-standalone example, assumes auditService returns Mono<Void>.
@PostMapping("/orders/{id}/confirm")
Mono<String> confirm(@PathVariable String id) {
    auditService.recordConfirmation(id).subscribe();
    return Mono.just("confirmed");
}
~~~

The API can respond **confirmed** before audit recording finishes; audit failures do not automatically become HTTP errors; request cancellation does not inherently cancel the audit branch; and if code also returns the same Publisher later, it risks **subscribing twice**, duplicating work on cold sources.

Even if subscribe() runs quickly or a synchronous source finishes immediately, this pattern fails to express "audit must succeed before confirming". **Fire-and-forget** work needs managed business mechanisms like queues/jobs/outboxes rather than manual subscribe() inside a Controller.

### 4.2. Right Way: Chain Side Effects Into the Same Pipeline

~~~java
// RIGHT: response completes only after audit succeeds.
@PostMapping("/orders/{id}/confirm")
Mono<String> confirm(@PathVariable String id) {
    return auditService.recordConfirmation(id)
            .thenReturn("confirmed");
}
~~~

**thenReturn(value)** waits for upstream to complete successfully and then emits value. If upstream errors, the chain emits an error instead of silently confirming success. If the goal is returning an empty response only after the side effect succeeds, return **Mono<Void>** via then() or directly return the service's Mono<Void>.

### 4.3. Subscribing Inside `doOnNext` Is Even More Dangerous

~~~java
// WRONG: reactive side effect becomes a detached branch.
return repository.findById(id)
        .doOnNext(user -> auditService.save(user).subscribe())
        .map(UserDto::from);
~~~

~~~java
// RIGHT: compose the audit branch into the data flow.
return repository.findById(id)
        .flatMap(user ->
                auditService.save(user)
                        .thenReturn(UserDto.from(user))
        );
~~~

Both snippets assume repository.findById returns Mono<User>, auditService.save returns Mono<Void>, and UserDto.from is a lightweight synchronous conversion. **doOnNext()** suits **fast, synchronous** logging, counters, or signal observation; it **does not await a Publisher** created inside the callback. To await async operations, use **flatMap**, **concatMap**, **then**, or **when** depending on data shape and ordering needs.

## 5. Operator Selection Table Instead of `block()` / `subscribe()`

| Goal | Common operator | Notes |
| --- | --- | --- |
| Transform a value with a fast, synchronous function | map | Never call blocking I/O inside the mapper |
| Function maps a value to another Mono/Flux | flatMap | Links the chain, lets the framework handle subscribing |
| Preserve element ordering of async tasks | concatMap | Useful when order matters; throughput may be lower |
| Wait for A to complete then run B, ignoring A's value | then(B) or thenMany(B) | If A errors, B does not run |
| Wait for A to complete then emit a fixed value | thenReturn(value) | Useful with Mono<Void> from write operations |
| Run multiple Monos and combine all results | Mono.zip(...) | With Mono.empty(), zip can terminate empty; check semantics |
| Wait for multiple tasks to finish without values | Mono.when(...) | Errors propagate to the chain; consider concurrent impact |
| Empty signal needs a fallback | defaultIfEmpty or switchIfEmpty | Use switchIfEmpty(Mono.defer(...)) when fallback must be lazy |
| Log/record metrics on signals | doOnNext, doOnError, doFinally | Calling doOnError alone does not handle/recover the error |
| Replace an error signal with another Publisher | onErrorResume | Fall back only for intended error types |
| Bound waiting time on a pipeline | timeout | Timeout issues best-effort cancellation; external rollback is not guaranteed |
| Manage resources requiring closure | using/usingWhen | Cleanup binds to success, error, and cancel per operator contract |

Example operation sequence:

~~~java
// Local example: all three service methods return Mono.
Mono<Receipt> confirm(String orderId) {
    return orderService.reserve(orderId)
            .flatMap(reservation ->
                    paymentService.charge(reservation)
                            .flatMap(payment ->
                                    auditService.save(payment)
                                            .thenReturn(new Receipt(payment.id()))
                            )
            );
}
~~~

This is an **illustrative snippet, not a standalone program**. It expresses "reserve → charge → audit → receipt" within **one subscription**. Even when composed properly, this chain **does not automatically create a distributed transaction** across services. Critical side effects require idempotency/compensation/outboxes and partial-failure handling per business rules.

## 6. Runnable Practice: WebFlux Controller Without `block()` / `subscribe()`

The sample app uses **Spring Boot 3.3.13, Java 17+, Spring WebFlux, and Reactor Netty**. It accepts a POST to generate a greeting and increment an audit counter in the same pipeline, plus a GET to inspect the counter. In-memory state keeps the focus on subscription mechanics. In production, durable audit logging needs an appropriate store/queue.

### 6.1. Project Structure

~~~text
reactive-request-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/reactive/
    │   └── ReactiveRequestDemoApplication.java
    └── test/java/com/example/reactive/
        └── AuditServiceTest.java
~~~

**pom.xml**:

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
    <artifactId>reactive-request-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

**src/main/java/com/example/reactive/ReactiveRequestDemoApplication.java**:

~~~java
package com.example.reactive;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveRequestDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveRequestDemoApplication.class, args);
    }
}

@Service
class AuditService {
    private final AtomicInteger count = new AtomicInteger();

    Mono<Void> record(String name) {
        return Mono.fromRunnable(() -> {
            count.incrementAndGet();
        }).then();
    }

    int count() {
        return count.get();
    }
}

@RestController
class GreetingController {
    private final AuditService auditService;

    GreetingController(AuditService auditService) {
        this.auditService = auditService;
    }

    @PostMapping("/api/greetings/{name}")
    Mono<String> greet(@PathVariable String name) {
        return Mono.just(name)
                .delayElement(Duration.ofMillis(100))
                .map(value -> "Hello, " + value + "!")
                .flatMap(greeting ->
                        auditService.record(name).thenReturn(greeting)
                );
    }

    @GetMapping("/api/audit-count")
    Mono<Integer> auditCount() {
        return Mono.fromSupplier(auditService::count);
    }
}
~~~

Explanation:

1. **POST** is used because recording an audit is a side effect, unsuitable for GET's safe semantics.
2. Mono.just(name) creates a value source; delayElement simulates asynchronous completion via Reactor's scheduler, **without Thread.sleep or block()**.
3. map builds the greeting text from the emitted value.
4. flatMap connects the Mono<Void> from AuditService.record with the response value via thenReturn; the framework receives **a single Mono<String>** to subscribe to.
5. AuditService.record uses Mono.fromRunnable so it **increments the counter on subscription**, rather than when calling record() alone. The AtomicInteger operation is fast and non-blocking; the in-memory counter is strictly illustrative.
6. auditCount uses Mono.fromSupplier to read the current count at subscription time. This is a state-safe GET.

### 6.2. Testing Lazy Execution with `StepVerifier`

**src/test/java/com/example/reactive/AuditServiceTest.java**:

~~~java
package com.example.reactive;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AuditServiceTest {

    @Test
    void auditRunsOnlyWhenSubscribed() {
        AuditService service = new AuditService();

        Mono<Void> pending = service.record("An");
        assertEquals(0, service.count());

        StepVerifier.create(pending)
                .verifyComplete();

        assertEquals(1, service.count());
    }
}
~~~

Run the test:

~~~bash
mvn test
~~~

Expected result: **build succeeds, one test passes**, with no AssertionError. Maven prints varying log lines across versions and machines; do not assert exact full Maven stdout. This test proves the side effect **has not run when creating the Mono**, and **runs upon subscription** via StepVerifier. Remember: each additional subscription to a cold Publisher may trigger the operation again.

### 6.3. Running HTTP End-to-End

Run inside the project directory:

~~~bash
mvn spring-boot:run
~~~

Once the app listens on default port 8080, in another terminal invoke **once**:

~~~bash
curl -s -X POST http://localhost:8080/api/greetings/An
curl -s http://localhost:8080/api/audit-count
~~~

Corresponding response bodies in a **freshly started** application instance that has received no other POST requests:

~~~text
Hello, An!
1
~~~

In PowerShell on Windows, use curl.exe if the curl alias lacks parameter support. Both responses depend on the server running, the first request succeeding, and no concurrent requests altering the counter. Sending a second POST increments the audit count to 2.

**Key takeaway:** The Controller never needs to call subscribe() to make audit logging happen; when the HTTP framework subscribes to the returned Mono, the entire pipeline executes, including record().

## 7. When a Blocking Library Is Unavoidable

Some systems still depend on **JDBC**, synchronous network SDKs, blocking file readers, or legacy code. They do not become non-blocking just by being wrapped in a Mono.

### 7.1. Wrong Way: Calling Blocking Code Before Creating the Publisher

~~~java
// WRONG: legacyDao.findById(id) runs immediately on the calling thread.
Mono<Customer> find(String id) {
    return Mono.just(legacyDao.findById(id));
}
~~~

With Mono.just, legacyDao.findById(id) evaluates **immediately**. If it takes 2 seconds, the Controller may stall the event loop for 2 seconds before returning the Mono.

### 7.2. Bounded Right Way: `fromCallable` + `boundedElastic`

~~~java
// Integration pattern inside a service with legacyDao; not a standalone program.
Mono<Customer> find(String id) {
    return Mono.fromCallable(() -> legacyDao.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Import Mono and reactor.core.scheduler.Schedulers. **Mono.fromCallable** defers the synchronous call until subscription. **subscribeOn(Schedulers.boundedElastic())** shifts source/callable execution to a worker pool suited for blocking code instead of holding the event loop. This is a **transitional workaround**; when true non-blocking APIs exist (R2DBC or genuinely async HTTP clients), use them directly.

State the limits accurately:

- boundedElastic **has caps** on workers and queued tasks; it does not provide infinite capacity.
- JDBC/SDK calls themselves remain blocking and still consume boundedElastic threads and connection pools; enforce **driver/client timeouts**, concurrency caps, and replica sizing.
- **Cancellation of a reactive chain does not guarantee immediate termination of an active blocking call**; blocking APIs may ignore interrupts. Never treat Mono timeouts as a substitute for source timeouts/cleanup.
- Never use Schedulers.parallel() or Schedulers.single() for blocking I/O.
- Never create arbitrary schedulers per request. Use managed resources and monitor queues/threads.

### 7.3. `subscribeOn` and `publishOn` Differ

- **subscribeOn(scheduler)** affects subscription and upstream request signals toward the source; typically placed **right after a blocking source** for clarity.
- **publishOn(scheduler)** changes where **signals downstream of the operator** are processed; it cannot undo blocking that already ran earlier. Use it to switch execution contexts mid-chain.
- **No operator automatically turns a blocking library into non-blocking I/O**. They only change which thread executes work.

In particular, never read "subscribe" in subscribeOn and assume it **launches** the pipeline. Without a downstream subscriber, the source still does not execute.

## 8. Designing HTTP → Service → WebClient → Repository

A pipeline can stay reactive from the Controller through downstream layers:

~~~java
// Illustrative composition; client, repository, and DTO are declared in your class.
Mono<ProfileView> getProfile(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new ProfileNotFoundException(id)))
            .flatMap(profile ->
                    externalClient.getScore(profile.externalId())
                            .map(score -> new ProfileView(profile, score))
            )
            .timeout(Duration.ofSeconds(3))
            .doOnError(error -> log.warn("Cannot get profile {}", id, error));
}
~~~

This assumes repository and externalClient use truly reactive sources. **flatMap** chains the downstream HTTP call into the same pipeline; **timeout** sets a total wait budget; **doOnError** only logs and does not swallow the failure. To customize HTTP error codes, handle them in ControllerAdvice/WebExceptionHandler or use selective onErrorMap/onErrorResume.

### 8.1. Notes on Empty Signals

Mono.empty() means **completed with no element**, which differs from null values or errors. When map is applied to Mono.empty(), the mapper **does not run**. If "not found" should yield 404, do not call blockOptional() to decide imperatively; compose with switchIfEmpty(Mono.error(...)) or transform to ResponseEntity inside the chain.

Example with a Service returning Mono<Product>:

~~~java
@GetMapping("/products/{id}")
Mono<ResponseEntity<Product>> find(@PathVariable String id) {
    return productService.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

This is an illustrative Controller snippet assuming Product and productService exist. It maps values to **200**, empty sources to **404**, while errors continue through WebFlux error handling. Neither subscribe() nor block() is used.

### 8.2. When to Use `WebClient` Over `RestTemplate`/`RestClient`?

In a **non-blocking WebFlux path**, WebClient is designed to expose results as Mono/Flux. RestTemplate/RestClient operate synchronously; calling them directly on an event loop can block. A **Spring MVC** application can appropriately use RestClient because its threading model differs; the choice depends on the web stack and system goals.

**Having Mono in signatures is not enough to guarantee end-to-end reactivity.** Always verify the actual I/O source, not just method return types.

## 9. Errors, Timeouts, Cancellation, and Request Context

### 9.1. Error Is a Signal in the Same Pipeline

~~~java
// Service example; client.fetch(id) returns Mono<Profile>.
return client.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                error -> Mono.error(
                        new IllegalStateException("Profile service timed out", error)
                ));
~~~

Import java.util.concurrent.TimeoutException. This is an **illustrative snippet**, not a standalone file. In production, translate errors to HTTP 504 or an appropriate contract via the error-handling layer; never return fake success to mask outages.

**Manual subscribe()** detaches the error branch: sub-service errors may only reach Reactor's error hook or a separate subscriber callback instead of the HTTP response. If calling subscribe() directly at a **valid imperative boundary** like an out-of-request event listener, explicitly manage **Disposable**, lifecycle, errors, and cancellation, or move to a managed job/queue mechanism.

### 9.2. Cancellation Is Not Rollback

When a client disconnects or times out, the framework can send a cancel signal to the Publisher. This normally propagates along the composed chain. However, if a service already wrote to a DB, dispatched an external HTTP request, or started a blocking task, **cancel does not guarantee undoing it**. Use idempotency keys, resource-appropriate transactions, bounded retries, and deduplication at business boundaries.

With manual subscribe() inside a request, the side branch holds its **own Disposable** and usually misses main request cancellation. That is a primary reason not to split subscriptions.

### 9.3. Reactor Context, Security, and MDC

Reactive execution can hop across threads. Never assume data stored in ThreadLocal/MDC automatically follows every callback. Reactive Spring Security and context propagation libraries integrate with Reactor Context; when implementing custom propagation, use contextWrite/deferContextual or framework-supported integrations instead of global variables or reading ThreadLocal on another thread.

Do not read HTTP request body/cookies/Principal **eagerly** outside reactive APIs when they are only available within the chain. Never spawn separate subscribe() calls expecting them to inherit request security/trace/transaction context automatically.

## 10. Two Subscriptions Can Execute the Same Operation Twice

Many Reactor Publishers are **cold**: each subscription can re-trigger the source, including DB queries or HTTP calls.

~~~java
// WRONG: assumes saveInvoice() returns Mono<Invoice>.
Mono<Invoice> save = invoiceService.saveInvoice(input);
save.subscribe();  // subscription #1
return save;        // WebFlux may create subscription #2
~~~

If a cold source has side effects, the operation may execute twice. Never claim every Mono runs twice: hot sources, cache, share, and replay have different semantics. Still, **the risk is very real**, especially for writes.

~~~java
// RIGHT: assemble the chain and return to WebFlux once.
return invoiceService.saveInvoice(input);
~~~

When you genuinely want to **share** results across multiple consumers, choose a cache/share/replay strategy intentionally based on lifecycle, memory, and consistency. Never slap Mono.cache() on to blindly patch duplicate-subscription bugs, especially on write operations.

## 11. Observing and Testing the Right Failure Modes

### 11.1. What to Watch For

| Symptom | Investigation path |
| --- | --- |
| IllegalStateException mentioning block() on reactor-http-nio or non-blocking thread | Search for block(), blockFirst(), blockLast() in Controllers, Filters, and callbacks |
| Low CPU yet rising p95/p99, few event-loop threads held long | Thread dumps, blocking JDBC/SDK calls, Thread.sleep, file I/O |
| API returns 200 before audit/notify finishes | Check for manual subscribe() or fire-and-forget branches |
| Downstream errors bypass HTTP error handler | Detached subscribe() branch, dropped onError, custom error handler |
| Same write operation executes twice | Multiple subscriptions on cold Publisher, automatic retries, duplicate requests |
| Client cancelled yet background work keeps running | Independent subscribe branch or non-cancellable source |
| BoundedElastic queue grows, latency keeps climbing | Too many blocking calls, inadequate timeouts/concurrency caps |
| Response throughput drops under rising load | Event loop starvation, pool/DB bottleneck, downstream slowdown |

To investigate, monitor request rate/latency, error rates, downstream connections, event-loop thread dumps, schedulers, pools, and request-correlated logs. Do not conclude "reactive is slow" merely because Flux/Mono appears; separate I/O sources, CPU operators, hidden blocking, and system limits.

### 11.2. Test Pipelines Instead of Calling `block()` in Production

In **unit tests**, StepVerifier acts as a controlled subscriber asserting values, errors, completion, and cancellation. It eliminates any excuse to stuff manual subscribe() or block() into business code just to "inspect results". In HTTP integration tests, use WebTestClient or curl to verify response contracts and side effects after request completion.

If a test must obtain a value synchronously at a test boundary, controlled block() on a **blocking-permitted** thread with an appropriate timeout is an acceptable test exception; what this lesson prohibits is **bringing that pattern into event-loop request handlers**. In imperative batch/CLI apps, block() may be an intentional bridge boundary; not every block() call in an entire codebase is a bug.

### 11.3. Self-Correction Exercise

Read this buggy snippet:

~~~java
@PostMapping("/send/{id}")
Mono<String> send(@PathVariable String id) {
    Mono<String> value = apiClient.get(id);
    auditService.log(id).subscribe();
    return Mono.just(value.block().toUpperCase());
}
~~~

Assume apiClient.get returns Mono<String> and auditService.log returns Mono<Void>. There are **two independent bugs**: subscribe() detaches auditing from the request; block() synchronously blocks the HTTP handling thread. Rewrite:

~~~java
@PostMapping("/send/{id}")
Mono<String> send(@PathVariable String id) {
    return apiClient.get(id)
            .flatMap(value ->
                    auditService.log(id)
                            .thenReturn(value.toUpperCase())
            );
}
~~~

When apiClient.get is empty, no value exists to forward and auditing in this example **does not run**. If auditing must run even when the source is empty, design that rule intentionally. If apiClient or audit errors, the returned Mono errors; no false HTTP success occurs. Both snippets are **Controller fragments with injected services**, not standalone compilable files.

## 12. Checklist Before Merging a WebFlux Request Handler

- **Execution path:** Controller returns Mono/Flux or an equivalent reactive type; never call block()/blockFirst()/blockLast() on the event loop.
- **Data sources:** distinguish true reactive I/O from wrapped synchronous JDBC/SDK calls; never let blocking calls run eagerly in Mono.just(...).
- **Subscription:** never call subscribe() to "trigger" work inside a Controller, WebFilter, or request-scoped service. Let the framework subscribe to the returned Publisher.
- **Side effects:** use flatMap/then/thenReturn/Mono.when to express required ordering; durable/independent writes need managed mechanisms.
- **Unavoidable blocking:** use lazy Mono.fromCallable/Mono.fromRunnable plus subscribeOn(boundedElastic), with timeouts/connection limits, memory/thread budgets, and load testing.
- **Errors:** downstream error signals propagate to the HTTP response; doOnError only observes, onErrorResume is selective; never lose errors in detached subscribe() calls.
- **Cancellation:** understand HTTP request cancellation and the non-atomicity of already-dispatched side effects; apply idempotency where needed.
- **Context:** security, trace IDs, and transaction context travel with the reactive chain; never rely blindly on ThreadLocal across scheduler hops.
- **Testing:** use StepVerifier/WebTestClient, test empty/error/timeout/cancel cases, and verify one request produces the expected single side effect.
- **Operations:** monitor p95/p99, thread dumps, scheduler/pool saturation, downstream latency; avoid masking blocking by raising thread counts infinitely.

**Remember:** **return Mono/Flux → framework subscribes** is WebFlux's default model. **block()** forces waiting on the current thread; **subscribe()** spawns a detached execution branch. The proper design is to **compose the pipeline**, offload legacy blocking only when unavoidable, and let success, errors, and cancellation all flow through the same chain.

## References

- Spring Framework — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient and retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Project Reactor — Schedulers, subscribeOn, publishOn: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — Subscription patterns, lifecycle, and cancellation: https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html
- Project Reactor — FAQ on blocking sources: https://projectreactor.io/docs/core/release/reference/faq.html