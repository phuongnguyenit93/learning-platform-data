# Distinguishing Synchronous, Asynchronous, Blocking, and Non-Blocking

**Context:** Spring Framework Reactive — Overview.

When handling HTTP requests, querying a database, or calling another service, there are two independent questions:

1. **Synchronous or asynchronous?** How and when does the caller receive the result?
2. **Blocking or non-blocking?** While the result is not yet ready, must the executing thread stop and wait?

These are **two different axes**. An asynchronous call can still block a thread in the background; a non-blocking call can also be a synchronous operation that immediately returns a “no data yet” status.

## 1. Separating the Two Axes

### 1.1. Synchronous vs. Asynchronous: How the Result Is Returned

- **Synchronous:** The caller makes a call and receives the result/status of that call itself before moving to the step that depends on the result. The result can be data, an error, or a “not ready” status. This concept **does not by itself say** whether the caller has to wait or not.
- **Asynchronous:** The caller initiates/registers an operation and can continue with other work before the operation completes. The result arrives later via a callback, an event, a `Future`/`CompletionStage`, or a `Mono`/`Flux` upon subscription. The recipient needs to coordinate the subsequent processing flow.

For example, `CompletableFuture.supplyAsync(...)` returns a `CompletableFuture` immediately while the work runs on an executor. However, if that work calls synchronous JDBC, the executor thread still waits for the query to finish.

**Asynchronous does not mean parallel.** A single-threaded event loop can manage many operations waiting on I/O and handle each operation's events only when ready; each callback itself still runs sequentially on that thread.

### 1.2. Blocking vs. Non-Blocking: What Does the Thread Do While Waiting?

- **Blocking:** A call holds the current thread in a waiting state until data arrives, a timeout occurs, or an error is raised. While waiting, that thread cannot process other application work. Examples include `InputStream.read()` when no bytes are available, `Thread.sleep(...)`, `Future.get()` when the task has not completed, or a synchronous JDBC query.
- **Non-blocking:** A call does not force the current thread to wait until I/O completes. It may return “not ready” immediately, or register for notification and yield the thread for other work. Examples include reading a `SocketChannel` in non-blocking mode, or sending HTTP requests with `WebClient` and handling the result with a reactive chain.

“Non-blocking” is evaluated **at a specific operation, on a specific thread**. It does not mean that the entire system has no thread ever waiting, no queues, or that tasks finish instantaneously.

## 2. The Four-Case Matrix

| | **Blocking** | **Non-blocking** |
|---|---|---|
| **Synchronous** | Calls an API and the current thread must wait for the result. Example: reading an `InputStream` / traditional JDBC. | Calls an API and immediately receives data or “not available”; the caller actively retries/registers for monitoring. Example: a single `SocketChannel.read()` call with `configureBlocking(false)`. |
| **Asynchronous** | The caller submits work to an executor and moves on; the **worker thread** is still blocked when calling synchronous I/O. Example: `CompletableFuture.supplyAsync(() -> legacyJdbcCall(), executor)`. | The caller registers I/O; an event mechanism reports the result when ready without dedicating a waiting thread per request. Example: `WebClient` using a non-blocking HTTP connector in WebFlux. |

The same program can contain multiple cells of the matrix. For instance, an HTTP request handled asynchronously that calls blocking JDBC on a separate pool is **asynchronous on the caller side, blocking on the worker side**.

### Timing Model

```text
Synchronous + blocking
caller: [call] ------ wait I/O ------ [receive data] -> next step

Synchronous + non-blocking
caller: [call] -> [receive "not ready"] -> other work / wait for event / retry

Asynchronous + blocking
caller: [submit work] -> other work ------------> [receive completion]
worker:              [call I/O] --- wait I/O ---> [completed]

Asynchronous + non-blocking
event loop: [register I/O] -> handle other requests -> [event ready]
handler:                                               [handle result]
```

The lines represent *wait points and occupied threads*, without claiming that every operating system/HTTP client always uses a fixed number of threads.

## 3. Analyzing Each Case in Java

### 3.1. Synchronous + blocking

```java
String response = legacyClient.fetch(); // Synchronous API, assumed to make a blocking I/O call
System.out.println(response);            // runs only after fetch completes
```

This snippet is **illustrative code**, assuming `legacyClient` is a blocking client. The thread calling `fetch()` must wait for I/O. If placed directly in a request handler and there are many slow requests, many request-handling threads will be occupied simultaneously while waiting.

### 3.2. Synchronous + non-blocking

```java
// channel is a connected SocketChannel; buffer has remaining space.
channel.configureBlocking(false);
int count = channel.read(buffer);

if (count > 0) {
    // Read count bytes in this call.
} else if (count == 0) {
    // No bytes read yet; the thread is not held waiting for bytes to arrive.
} else {
    // count == -1: the remote peer has closed the read stream (end of stream).
}
```

This is **partial illustrative code**; `channel` and `buffer` must be declared/initialized in a real program. The `read` call returns its result **synchronously** (byte count or status) without blocking to wait for bytes. In a real application, pair it with a `Selector`/readiness notification to be notified when reading is possible; do not use a tight `while (read(...) == 0) {}` loop because it burns CPU (busy polling).

A non-I/O example: `ConcurrentLinkedQueue.poll()` immediately returns an element or `null` if the queue is empty. That is a synchronous query style that does not block waiting for an element to appear.

### 3.3. Asynchronous + blocking

The following Java 17 snippet runs standalone. `Thread.sleep` **only simulates I/O wait time**, not an actual network/database call:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WaitingDemo {
    static String blockingCall() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return "OK";
    }

    public static void main(String[] args) {
        System.out.println("sync=" + blockingCall());

        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> job =
                    CompletableFuture.supplyAsync(WaitingDemo::blockingCall, workers);

            System.out.println("caller continues");
            System.out.println("async=" + job.join());
        } finally {
            workers.shutdown();
        }
    }
}
```

Save the file `WaitingDemo.java`, then run:

```bash
javac WaitingDemo.java
java WaitingDemo
```

Expected output:

```text
sync=OK
caller continues
async=OK
```

Execution flow:

1. The first `blockingCall()` runs synchronously, blocking the `main` thread for about 100 ms.
2. `supplyAsync` dispatches the work to `workers` and returns `job` immediately. `main` can print `caller continues`.
3. The worker thread is blocked by `sleep`. `job.join()` **can block the `main` thread itself** if the result is not yet ready.
4. When the worker finishes, `join()` returns the string `OK`. `shutdown()` stops the executor from accepting new tasks.

Therefore, “wrapped in `CompletableFuture`” only proves that **the caller receives an asynchronous handle**; it **does not turn the blocking operation inside into non-blocking**. In a real service, manage the executor, bound the thread count/queue size, and apply timeouts when calling blocking APIs.

### 3.4. Asynchronous + non-blocking

Suppose an HTTP client has a non-blocking connector. When a request is triggered, the client registers I/O and completes the call via events when the response arrives. The event-loop thread can handle multiple connections while waiting on the network. In Spring, `WebClient` with a `Mono` chain is a typical example:

```java
Mono<String> response = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(String.class);

return response; // inside a controller returning Mono<String>
```

This is **partial illustrative code**: `webClient` already has a base URL configured, `id` is an existing variable, and the enclosing method returns `Mono<String>`. `bodyToMono` describes the processing chain; I/O usually starts when the publisher is **subscribed** to. In a WebFlux controller, the framework manages the subscription and writes the HTTP response. Do not call `block()` to “extract the result” inside a reactive controller.

Note: “asynchronous” and “non-blocking” here apply to **the I/O path using an appropriate connector**. If a `map`/`flatMap` lambda calls blocking JDBC, part of the pipeline is still blocking.

## 4. How Do Spring MVC and Spring WebFlux Relate?

### 4.1. Request Model with Many Slow Calls

Suppose there are 100 requests/second, and each request waits about 200 ms for an external service. On average, roughly `100 × 0.2 = 20` requests may be waiting at a given moment (a simple steady-state estimate via Little's Law).

- In a **one-blocking-thread-per-request** model, many threads may sit idle waiting on the network. Increasing thread counts has limits due to memory and scheduling overhead.
- In an **event-loop + non-blocking I/O** model, a small number of threads can manage many connections waiting for events. The main advantage is **thread/resource utilization and load resilience** under high I/O latency, not making the network itself faster.
- If most of the time is spent on heavy CPU computation, non-blocking I/O does not make the CPU faster. The bottleneck may shift to CPU, DB pools, external service limits, or load-control capacity.

The example numbers only illustrate the number of waiting requests, **not a benchmark** proving Spring MVC needs exactly 20 threads or WebFlux needs only one thread.

### 4.2. Spring MVC

Traditional Spring MVC works with the Servlet API and typically processes a request using a server thread. Blocking APIs such as JDBC, `RestTemplate`, or synchronous clients can hold that thread until done. However, MVC **also supports asynchronous return types** (e.g., `Callable`, `DeferredResult`, and reactive types in certain integrations). Therefore, concluding “MVC = always synchronous” is wrong.

Java virtual threads can reduce the cost of many blocking tasks in some configurations, but **they do not change the blocking semantics of the API**. Measure before choosing a production execution strategy.

### 4.3. Spring WebFlux

Spring WebFlux is designed around **reactive, event-driven, non-blocking** processing. With runtimes such as Reactor Netty, event-loop workers serve many requests and should not be blocked by slow I/O. WebFlux can use annotated controllers (`@RestController`) or functional routes; what distinguishes it from MVC is the **execution model and asynchronous contract**, not just annotation syntax.

Key components:

- `Mono<T>`: a publisher with at most one element (or completing empty/with an error).
- `Flux<T>`: a publisher with 0 to many elements.
- `WebClient`: an HTTP client supporting asynchronous composition and non-blocking I/O.
- **Reactive Streams backpressure:** the consumer can request the number of elements it is ready to process. This is a data-flow throttling mechanism; it **does not mean** all I/O stops being blocking or every external source supports slowing down accordingly.
- **Scheduler:** determines where certain parts of the work execute. `Mono`/`Flux` by themselves do not mean creating new threads, and many operators run on the current signal-emitting thread.

## 5. WebFlux Controller Illustration

The following example is a complete Spring WebFlux controller class intended for **a Spring Boot project that already has the `spring-boot-starter-webflux` dependency**, and requires a `catalog-service` with a matching endpoint for requests to succeed:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ProductController {
    private final WebClient client;

    public ProductController(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    @GetMapping("/products/{id}")
    public Mono<String> getProduct(@PathVariable String id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

Execution flow:

1. WebFlux invokes `getProduct`. The controller **returns a publisher** without waiting for the HTTP response from the catalog service inside the method body.
2. When the framework subscribes, `WebClient` sends the request via an appropriate non-blocking HTTP connector.
3. While waiting, the event loop can process other events. When the response is ready, the publisher emits data or an error.
4. WebFlux translates the signal into the HTTP response of the current endpoint. If upstream fails, the error signal must be handled according to the application's error-handling policy.

**Do not assume this controller is a standalone runnable application:** it still needs a Spring Boot app, dependencies/runtime, DNS, or external service address configuration. Returning `Mono` also does not guarantee the entire pipeline is non-blocking if an internal component uses a blocking API.

A simpler example that needs no external service, illustrating an asynchronous timer:

```java
@GetMapping("/delayed")
public Mono<String> delayed() {
    return Mono.delay(java.time.Duration.ofMillis(100))
            .map(tick -> "ready");
}
```

The method snippet above belongs inside a WebFlux `@RestController`, not a standalone Java program. `Mono.delay` schedules a timed signal; it does not need to keep a request thread sleeping via `Thread.sleep(100)`.

## 6. Handling Blocking APIs Inside a Reactive Pipeline

When forced to use an existing blocking library, **isolate the blocking work on a scheduler intended for blocking**:

```java
Mono<String> result = Mono
        .fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This is an **applicable snippet** in a project that has Reactor, `legacyClient` (a blocking API), `id`, and the corresponding imports (`Mono`, `Schedulers`). Meaning:

- `fromCallable` defers invoking `fetch(id)` until subscription time; it does not run eagerly when creating the `Mono`.
- `subscribeOn(Schedulers.boundedElastic())` schedules subscription/source execution onto a scheduler suited for blocking work, avoiding holding the event-loop thread inside `fetch`.
- **`fetch` itself is still blocking** on a `boundedElastic` worker. The scheduler has capacity limits and queued work, so you must monitor load, timeouts, and downstream capacity.
- Using a genuinely non-blocking database driver/client, such as R2DBC when appropriate, is what moves toward an end-to-end non-blocking data-access path.

**Common mistakes:**

```java
// Wrong: fetch() already ran immediately on the current thread before creating Mono.
Mono<String> bad = Mono.just(legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());

// Wrong inside a WebFlux request handler: may block the event loop.
String value = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .block();
```

`Mono.just(...)` takes an **already computed** value, whereas `Mono.fromCallable(...)` takes work to execute upon subscription. `block()`/`blockFirst()`/`blockLast()` wait for the result; on Reactor threads marked as non-blocking, blocking calls may be rejected with `IllegalStateException`. In controllers, compose with `map`, `flatMap`, `zip`, and **return the publisher**.

## 7. Common Misconceptions

1. **“Async is always non-blocking.”** False: `supplyAsync` can run blocking JDBC on another pool. The caller does not wait immediately, but the worker is still held.
2. **“Non-blocking means the task completes instantly.”** False: the network and DB still have latency; only how threads handle the wait time differs.
3. **“Using `Mono` automatically creates a thread.”** False: Reactor does not automatically create a separate thread per publisher; execution scheduling depends on the source, subscription, operators, and schedulers.
4. **“Adding `subscribeOn` turns JDBC into a non-blocking driver.”** False: it only changes where the blocking part runs.
5. **“Calling `subscribe()` directly in the controller is the standard way.”** Usually false: it easily detaches processing from the HTTP lifecycle, errors, and unsubscription; return `Mono`/`Flux` so the framework manages it.
6. **“Non-blocking is always faster.”** False: the benefit depends on the share of I/O waiting, throughput, downstream systems, and coordination overhead; benchmark against real workloads.
7. **“An event loop never waits.”** Overstated: the loop may wait for the OS to emit readiness events; the key point is **not allocating a held thread per request waiting on I/O**.
8. **“Running heavy CPU work on the event loop is fine because there is no I/O.”** False: long computations keep the event-loop worker busy, delaying other requests; design proper separation for CPU-bound work.
9. **“Having backpressure means end-to-end boundedness.”** Not guaranteed: queues, producers, buffers, and external services must each have matching control mechanisms.

## 8. How to Classify a Code Snippet During Review

Do not infer solely from method names, annotations, or return types. Ask in order:

1. **What is returned to the caller immediately upon calling?** The call's data/status (usually synchronous), or a handle/publisher for a future result (asynchronous)?
2. **While data has not arrived yet, which thread is waiting?** The request/event-loop thread, another worker, or no worker dedicated solely to the I/O operation?
3. **What kind of I/O does the API actually use?** Blocking JDBC, `InputStream`, a non-blocking driver, or a reactive HTTP client? `Executor`/`Scheduler` only changes execution location.
4. **Is there any active waiting point?** `get()`, `join()`, `block()`, `sleep()`, mutex, blocking queue `take()`... Even one such point means the execution path there can block.
5. **Who completes and propagates errors/cancellation?** Is the Callback/Future/Publisher returned or composed for the framework to manage? Are timeouts, cancellation, connection limits, and backpressure in place?

### Self-Check Exercise

| Scenario | Correct Classification |
|---|---|
| `InputStream.read()` runs directly on the request thread and waits for bytes | **Synchronous + blocking** at the read call |
| Non-blocking `SocketChannel`: `read` returns 0 when no data is available | **Synchronous + non-blocking** for the read attempt |
| `CompletableFuture.supplyAsync(() -> jdbcQuery(), pool)` | **Asynchronous** to the caller, but **blocking** on the worker while JDBC runs |
| Non-blocking `WebClient` returned as a `Mono` from a WebFlux controller | Typically **asynchronous + non-blocking I/O** after subscription |
| `WebClient` inside a `.block()` call | **Blocking** at the `block()` call site, even though the HTTP layer uses non-blocking I/O |
| `Mono.fromCallable(blockingCall).subscribeOn(boundedElastic())` | Caller receives a publisher; **blocking** is offloaded to a scheduler worker |
| Plain `Flux.range(1, 3).map(x -> x * 2)` | Processed **synchronously on the subscription thread** when subscribed; no I/O to classify as blocking/non-blocking |
| `Mono.delay(Duration.ofMillis(100))` | **Asynchronous** timer, without using `Thread.sleep` to hold the request thread |

**Key takeaway:** synchronous/asynchronous is about **how the result is delivered to the caller**; blocking/non-blocking is about **how threads are used during the wait**. Spring WebFlux shines when I/O operations on the request path are predominantly **asynchronous and non-blocking**, and blocking work is identified and isolated in the right places.

## References

- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html), [Concurrency Model and Performance](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html).
- Spring Framework — [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Project Reactor — [Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
