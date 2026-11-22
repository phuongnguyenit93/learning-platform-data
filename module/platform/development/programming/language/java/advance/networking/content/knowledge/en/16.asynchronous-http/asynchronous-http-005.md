# Choosing an Executor for Continuation Work and Avoiding Blocking I/O Threads

## 1. Why can an asynchronous HTTP client still become slow or congested?

**HttpClient.sendAsync(...)** in Java returns a **CompletableFuture<HttpResponse<T>>**. The call does not require the calling thread to wait for the entire response like **send(...)**. However, that **does not guarantee that every continuation callback is non-blocking**, nor does it guarantee that they run on the thread you expect.

An application might write:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .thenApply(response -> expensiveCalculation(response.body()));
~~~

If expensiveCalculation is CPU-intensive or waits on a database, it may run directly on the thread completing a future or the thread registering the stage. That thread **may be involved in executing the HTTP client's asynchronous tasks**; if it is occupied for too long, the progress of other tasks can be affected.

**Goal of this lesson**: choose the right executor for continuation work so that **I/O progress does not have to wait for heavy business logic**, while also avoiding shifting the problem to an unbounded thread pool/queue.

A clear design:

~~~text
                         HttpClient.sendAsync(...)
                                  |
                  HTTP tasks: network, headers, body
                                  |
                     CompletableFuture<HttpResponse>
                                  |
                thenApplyAsync(transform, businessPool)
                                  |
                   Dedicated business executor
                                  |
                     CompletableFuture<Result>
                                  |
              thenCompose / handle / whenComplete ...
                                  |
               API/test boundary receiving the result
~~~

**Important note:** The API does not guarantee any specific thread name, nor does it state that all I/O executes on the threads configured via Builder.executor. You must rely on the **executor and CompletionStage contracts**, not on assumptions such as “the callback will definitely run on event loop X”.

## 2. Understanding the three places where work can run

### 2.1. The thread calling sendAsync

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());
~~~

sendAsync returns a future representing the result; the call may perform some initialization work directly on the caller thread. The response/body itself is not guaranteed to be complete when the method returns.

Do not write **future.join()** immediately after sendAsync in a request-handling/event-loop thread if the goal is non-blocking execution: join makes the caller thread **wait** for the future to complete and turns an asynchronous flow into a synchronous wait point.

### 2.2. The executor configured by HttpClient.Builder.executor(...)

~~~java
ExecutorService clientTasks = Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
        .executor(clientTasks)
        .build();
~~~

According to the Java 17 Javadoc, **Builder.executor(Executor)** sets the executor used for the **HTTP client's asynchronous and dependent tasks**. When not specified, each new HttpClient has its own default executor created by the implementation. **HttpClient.executor()** returns an Optional that may be empty if not explicitly configured; that **does not mean HttpClient lacks internal threads/executors**.

Do not assume that passing clientTasks to HttpClient will make **every** .thenApply, .thenApplyAsync lambda, or user-attached stage always run on clientTasks. The rules of **CompletableFuture** still govern where dependent stages execute.

### 2.3. Dedicated executor for continuations

~~~java
ExecutorService businessPool = Executors.newFixedThreadPool(2);

CompletableFuture<String> processed =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .thenApplyAsync(
                    response -> transform(response.body()),
                    businessPool);
~~~

This is how you **explicitly specify where transform runs**: CompletableFuture schedules the callback **on the passed-in businessPool**. It isolates heavy work from the executor used by the HTTP client for asynchronous progress.

In production, businessPool should be sized according to workload type and load control; newFixedThreadPool has a fixed number of threads, but its queue is **unbounded by default**, so the full example below uses a **ThreadPoolExecutor with a bounded queue**.

## 3. How does thenApply differ from thenApplyAsync?

Java 17 CompletableFuture defines the execution behavior of dependent stages as follows:

| API | Executor used by contract | What to keep in mind |
| --- | --- | --- |
| **thenApply(fn)** | No executor specified; the action may run on the thread completing the previous stage or the caller thread involved in completion | **Do not put heavy/blocking work here** if the running thread is uncontrolled |
| **thenAccept(fn)**, **whenComplete(fn)**, **handle(fn)** | Non-Async variants share the same affinity risk to the completing/calling thread | Callbacks with side effects can also occupy the thread |
| **thenApplyAsync(fn)** | Uses the default asynchronous execution facility of CompletableFuture | By default, this is usually **ForkJoinPool.commonPool()** for standard CompletableFuture; not the pool name from HttpClient.Builder.executor |
| **thenApplyAsync(fn, executor)** | Uses the **application-supplied Executor** | The explicit choice for business work that needs control |
| **thenCompose(fn)** | Creates a new stage and **flattens** the CompletionStage returned by fn; does not spawn a new thread on its own | Suitable for chaining a subsequent async operation if the callback is lightweight |
| **thenComposeAsync(fn, executor)** | The function creating the next stage runs on the specified executor | Useful when the next decision/preparation step is heavy |
| **whenCompleteAsync(action, executor)** | The action observing success/failure runs on the executor | Does not turn a failed result into a success |
| **handleAsync(fn, executor)** | Fn handles both result and exception on the executor | Can convert an error into a value or transform the error; design the policy clearly |

**Two common misconceptions:**

1. **thenApply does not mean it always runs on an I/O thread.** If the source stage has already completed before registration, the thread calling thenApply may run the lambda immediately; if not yet completed, a thread completing the stage may run it. Precisely because there is **no specific thread guarantee**, do not place heavy tasks here.
2. **thenApplyAsync without an executor does not mean it definitely uses HttpClient's clientTasks.** By CompletionStage/CompletableFuture rules, it uses the future's **default asynchronous execution facility**. For a standard CompletableFuture, that is usually **ForkJoinPool.commonPool()**; an implementation/subclass may have variations. To be certain, **pass an explicit executor**.

### A conceptual example of a non-async continuation

~~~java
// Java 17 snippet; the thread executing the lambda is not fixed by the API.
CompletableFuture<String> response = new CompletableFuture<>();

response.thenApply(value -> {
    // If complete() happens from an HTTP-handling thread, the lambda may
    // run on that thread; if the future is already complete, the caller may run it too.
    return value.toUpperCase(Locale.ROOT);
});
~~~

Do not try to probe threads with Thread.sleep(...) and infer behavior from thread names; the scheduler, completion timing, and implementation can vary across runs.

## 4. Choosing an executor by workload type

There is no single “universally optimal” pool configuration for every application. You need to classify the workload:

| Continuation work | Recommendation | Why |
| --- | --- | --- |
| **Pick a field, read status, small type conversion, very short calculation** | thenApply can be used if you are sure the callback is lightweight enough | Thread-switching overhead may not be worth it, though you must still remember thread affinity is unspecified |
| **Large JSON parsing, compression, hashing, scoring, CPU-intensive data processing** | **thenApplyAsync(fn, cpuExecutor)** | Does not occupy threads driving HTTP progress; CPU pool sized appropriately to core count |
| **Blocking JDBC calls or synchronous I/O libraries** | **thenApplyAsync(fn, blockingExecutor)**; bound concurrency according to the connection pool | I/O waits can be long; isolate from both the HTTP/client executor and CPU pool |
| **Calling another HTTP API via sendAsync** | **thenCompose(...)** to chain two futures, no .join() in between | Does not consume a thread waiting for the second request |
| **Very lightweight logging/telemetry** | Short thenAccept/whenComplete; if complex, use a separate executor | A slow synchronous logger can still block a thread |
| **Waiting for user, large files, or response streaming** | Streaming/backpressure approach; handle blocking on a separate worker | Does not prolong subscriber/I/O callbacks |
| **Error handling/retry and policy evaluation** | handle/exceptionally or handleAsync(..., executor) | Separates business logic and controls retry counts |

**An executor does not automatically turn a synchronous operation into an asynchronous non-blocking one**; it only moves the blocking point to another thread. If JDBC/legacy I/O operations still block, you must limit concurrent tasks, wait times, and backpressure.

### Separating the transport executor and the business executor

A multi-layered model:

~~~text
HTTP request (sendAsync)
    |
    +-- HttpClient executor: internal asynchronous/dependent tasks
    |   -> keep enough capacity for network/body progress
    |
    +-- Business CPU executor: large parsing/computation
    |   -> thread count typically balanced with CPU, bounded queue
    |
    +-- Blocking I/O executor (if any): JDBC/legacy I/O
    |   -> concurrent tasks balanced with connection pool/deadline
    |
    +-- Event loop/caller/API boundary: no join/get on the hot path
~~~

Do not assign the same **very small pool with long-blocking work** to both HttpClient tasks and business tasks; when business work exhausts all workers, the client may lose capacity to advance other asynchronous steps. Also do not turn every tiny continuation into a new thread-pool task without reason: context switching and queueing have overhead too.

## 5. Anti-patterns and how to fix them

### Anti-pattern A — blocking inside thenApply without an executor

~~~java
// BAD: dao.findById(...) is blocking JDBC.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApply(response -> dao.findById(response.body()));
~~~

**Problem:** JDBC can take hundreds of milliseconds or seconds. Because the stage has no explicit executor attached, it can hold onto the thread completing the HTTP future, reducing throughput for other tasks.

~~~java
// BETTER: dedicate a bounded pool for synchronous I/O.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApplyAsync(
            response -> dao.findById(response.body()),
            jdbcExecutor);
~~~

The variables dao, req, and jdbcExecutor are **illustrative snippets**, not a standalone file. The pool must have its lifecycle and capacity managed, not just created as an unbounded newCachedThreadPool.

### Anti-pattern B — calling sendAsync and then join inside a callback

~~~java
// BAD: using a continuation thread just to wait for the second HTTP call.
client.sendAsync(req1, HttpResponse.BodyHandlers.ofString())
      .thenApply(first -> client.sendAsync(
                buildSecondRequest(first.body()),
                HttpResponse.BodyHandlers.ofString()).join());
~~~

While join waits for the second request, a thread is held without doing useful work. If the callback runs on the executor dedicated to HttpClient, starvation risk increases.

~~~java
// BETTER: return a CompletionStage and flatten with thenCompose.
client.sendAsync(req1, HttpResponse.BodyHandlers.ofString())
      .thenCompose(first ->
            client.sendAsync(
                buildSecondRequest(first.body()),
                HttpResponse.BodyHandlers.ofString()));
~~~

**thenCompose does not have to spawn a thread**; it simply composes two already-async operations. The buildSecondRequest function should be lightweight; if heavy CPU is needed to build the request, use **thenComposeAsync(..., businessExecutor)**.

### Anti-pattern C — assuming thenApplyAsync without an executor always uses an app pool

~~~java
// No app executor supplied: default CF async facility is used.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApplyAsync(resp -> cpuHeavy(resp.body()));
~~~

Do not rely on pool guesswork. If load and latency need to be governed, call the overload with an **explicit Executor**.

### Anti-pattern D — CallerRunsPolicy on the business pool

~~~java
// Risky when the queue is full:
new ThreadPoolExecutor.CallerRunsPolicy();
~~~

When both the pool and queue are saturated, **CallerRunsPolicy** runs the task directly on the **thread calling executor.execute(...)**. For a CompletableFuture continuation, the caller may be the thread completing the HTTP future. Running a business task there **pushes heavy work back onto the I/O/completion path**, defeating the goal of thread isolation.

For a continuation-processing pool, **AbortPolicy** may be more appropriate: under overload, it **throws RejectedExecutionException**, allowing the system to observe it and apply backpressure/fail fast. However, you must handle failed futures properly and not silently ignore or drop requests. The rejection policy is a design decision, not just swapping a class name.

### Anti-pattern E — unbounded newCachedThreadPool

~~~java
// Must evaluate carefully under untrusted load / prolonged blocking.
ExecutorService pool = Executors.newCachedThreadPool();
~~~

The pool can grow its thread count in proportion to slow work, consuming memory/stack and increasing context switching. **newFixedThreadPool(n)** bounds the thread count, but its **default queue is unbounded**, which can also pile up requests indefinitely. Production systems usually need **bounds on both workers and queues**.

## 6. Runnable Java 17+ integration example: two HTTP requests and a dedicated executor

The **AsyncContinuationDemo.java** example runs completely on **127.0.0.1**:

1. Create a local HTTP server from the **jdk.httpserver** module, returning body **value-1** or **value-2**. The server uses **webServerPool** dedicated to the test fixture.
2. Create **clientTasks** with four threads and configure it via **HttpClient.Builder.executor(clientTasks)**. This is the executor serving the client's asynchronous tasks.
3. Create **businessPool** with two workers, a queue capacity of 16 tasks, and **AbortPolicy**. This is the executor handling the business stage.
4. Send **two independent requests** using **HttpClient.sendAsync**.
5. Attach **thenApplyAsync(..., businessPool)**, converting the response body to uppercase. Each callback **asserts that the thread name starts with business-**, proving the work was dispatched to the intended pool.
6. On the **main thread of the test program**, wait for both futures using **allOf(...).get(timeout)**. There is no join/get inside I/O callbacks or business stages.
7. Use finally to stop the HTTP fixture and shutdown/awaitTermination on all three executors. Print results only after verification.

This is a real integration test, not a mock of sendAsync output. No Internet or external server is required; **jdk.httpserver** is a module included in JDK 17. The example does not invoke repository software or user files.

### File AsyncContinuationDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncContinuationDemo {
    static ThreadFactory named(String prefix) {
        AtomicInteger sequence = new AtomicInteger();
        return task -> new Thread(
                task, prefix + "-" + sequence.incrementAndGet());
    }

    static CompletableFuture<String> fetch(
            HttpClient client, int port, int id,
            Executor businessPool, AtomicInteger checked) {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port +
                        "/item?id=" + id))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8))
                .thenApplyAsync(response -> {
                    if (!Thread.currentThread().getName()
                            .startsWith("business-")) {
                        throw new IllegalStateException(
                                "Continuation ran on unexpected executor");
                    }
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException("HTTP status");
                    }
                    checked.incrementAndGet();
                    return response.body()
                            .toUpperCase(Locale.ROOT);
                }, businessPool);
    }

    static void shutdown(ExecutorService pool)
            throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService webServerPool =
                Executors.newFixedThreadPool(
                        2, named("loopback-server"));
        ExecutorService clientTasks =
                Executors.newFixedThreadPool(
                        4, named("http-client"));
        ThreadPoolExecutor businessPool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(16),
                named("business"),
                new ThreadPoolExecutor.AbortPolicy());

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/item", exchange -> {
            try {
                String query =
                        exchange.getRequestURI().getRawQuery();
                if (!"id=1".equals(query) &&
                        !"id=2".equals(query)) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }

                byte[] bytes = ("value-" + query.substring(3))
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.getResponseHeaders().set(
                        "Connection", "close");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(webServerPool);

        try {
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .executor(clientTasks)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            AtomicInteger checked = new AtomicInteger();
            CompletableFuture<String> first = fetch(
                    client, server.getAddress().getPort(), 1,
                    businessPool, checked);
            CompletableFuture<String> second = fetch(
                    client, server.getAddress().getPort(), 2,
                    businessPool, checked);

            // Test program boundary, NOT an HTTP callback.
            CompletableFuture.allOf(first, second)
                    .get(10, TimeUnit.SECONDS);

            String value1 = first.join();
            String value2 = second.join();

            if (!"VALUE-1".equals(value1) ||
                    !"VALUE-2".equals(value2) ||
                    checked.get() != 2 ||
                    client.executor().orElseThrow() != clientTasks) {
                throw new AssertionError("Unexpected result");
            }

            System.out.println(
                    "Values: " + value1 + ", " + value2);
            System.out.println(
                    "Business callbacks verified: " +
                    (checked.get() == 2));
            System.out.println(
                    "Client executor configured: " +
                    client.executor().isPresent());
        } finally {
            server.stop(0);
            try {
                shutdown(businessPool);
            } finally {
                try {
                    shutdown(clientTasks);
                } finally {
                    shutdown(webServerPool);
                }
            }
        }

        if (!businessPool.isTerminated() ||
                !clientTasks.isTerminated() ||
                !webServerPool.isTerminated()) {
            throw new AssertionError("Executor leak");
        }
        System.out.println("Executor shutdown verified: true");
    }
}
~~~

### Compile and run

Create the file **AsyncContinuationDemo.java** using **JDK 17+**. Because it uses a local test server from the jdk.httpserver module, specify the module in the commands:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 AsyncContinuationDemo.java
java --add-modules jdk.httpserver AsyncContinuationDemo
~~~

**Exact stdout from a PASS run compiled with --release 17 and executed on OpenJDK 24.0.2:**

~~~text
Values: VALUE-1, VALUE-2
Business callbacks verified: true
Client executor configured: true
Executor shutdown verified: true
~~~

**Why the stdout is deterministic:** the completion order of the two HTTP requests is not guaranteed, but the program keeps separate futures for id=1 and id=2 and prints them in **id order**; it does not print actual thread names (whose sequence numbers may vary due to the scheduler). Instead, the stage asserts the **business- thread-name prefix** and increments a counter on success. The four PASS lines are printed only when both results and the corresponding checks succeed.

**Why get/join in main does not contradict the lesson:** This is the CLI test boundary that needs to wait for results to verify them. It **does not run inside an HTTP client completion thread**. After allOf.get(...) returns successfully, the subsequent two join() calls already have their results and no longer wait on the network. In a real HTTP server/event-loop, the request handler should **return a CompletionStage** or continue via callbacks instead of calling get/join immediately.

**Why the code uses HTTP/1.1:** To keep the local integration test simple, without needing HTTPS certificates or an HTTP/2 server; the goal is to verify **executor/continuation**, not to benchmark protocols. CompletableFuture rules and executor selection still apply when HttpClient handles HTTPS/HTTP2; do not infer scheduling results from the example's protocol.

**Note on the fixture:** newFixedThreadPool for the local server and client tasks keeps the demo concise; they have unbounded queues. In production, you need to measure/tune capacity and backpressure for real load. **businessPool** in the example already has a bounded queue and AbortPolicy. If you need to send thousands of requests concurrently, you must add an in-flight request limit (e.g., Semaphore) and rejection handling, rather than relying solely on queue=16.

## 7. Do not block BodyHandler, BodySubscriber, and data-processing threads

### 7.1. Body handler is invoked when response headers arrive

**HttpResponse.BodyHandler.apply(ResponseInfo)** is invoked after status/headers arrive but **before the entire body is received**. It selects a **BodySubscriber**. The BodySubscriber consumes the response bytes; the subscriber can be directly involved in advancing the HTTP pipeline.

A handler or subscriber might inadvertently perform blocking I/O inside a callback:

~~~java
// Anti-pattern illustration, DO NOT use for real response streaming.
// parseHugeBody and dao.save are heavy/blocking work.
BodyHandler<Result> handler = info -> customBodySubscriber(
        bytes -> dao.save(parseHugeBody(bytes)));
~~~

This snippet is **pseudocode**; the names Result/customBodySubscriber/dao are not built-in APIs. The idea is: if the subscriber's mapping runs for a long time, the thread used to handle delivery can be occupied. Do not arbitrarily block **onNext**, **onSubscribe**, or client mapping callbacks.

The **BodySubscribers.mapping(...) Javadoc** also warns that the mapper runs using the **client's executor** and blocking can starve the pool of threads. For a large InputStream, you should map to a Supplier/deferred object and perform the **blocking operation later** on an appropriate executor, rather than reading the entire stream directly inside the mapper. Streaming reads must be paired with closing the stream and backpressure.

### 7.2. BodyHandlers.ofString does not mean every response should live in RAM

BodyHandlers.ofString(...) buffers the body into a String before the corresponding response future completes. This is suitable for small payloads. For large downloads/long streams, choose appropriate BodyHandlers (file, InputStream, publisher) and manage their lifecycle clearly; **do not load all data into a huge String and then parse/block on a completion thread**.

Some BodyHandlers such as ofInputStream have their own future-completion and stream-ownership rules; you must **close the InputStream** after consuming it and not leak sockets/resources. Using a custom subscriber requires respecting Flow demand, cancellation, errors, and buffer limits.

### 7.3. Avoid blocking via async composition

If a continuation needs to make a second HTTP request, use **thenCompose** instead of calling join. If the next step is CPU-heavy, use **thenComposeAsync(..., businessExecutor)** to run the preparation on the pool. If the next step is blocking JDBC, switch to a JDBC executor bounded according to the JDBC pool.

**Do not conclude an operation is non-blocking just because the API name contains Async.** A lambda can still call Thread.sleep, JDBC, synchronized locks, file I/O, or wait on Future.get; if it runs on the business executor, the business executor's thread is still held. The goal is to prevent **starvation from spreading to HTTP progress**, and to design appropriate bounds for each type of work.

## 8. Bounded queues, backpressure, and rejection policies

Separating executors is the first step; if business processing runs slower than HTTP responses complete, the queue can grow continuously. The intuitive formula:

~~~text
Continuation creation rate  >  business pool processing rate
                    |
               Queue grows
                    |
   latency rises, memory held longer, possible OOM
~~~

With a two-thread pool and **ArrayBlockingQueue<>(16)**, the number of **active + queued** tasks is capped by the pool/queue capacity at submission time. But when the queue is full, you need a policy for **observable failure**.

### Rejection policies

| Policy | When pool is full | Suitability/risks |
| --- | --- | --- |
| **AbortPolicy** | Throws RejectedExecutionException | Fail-fast; caller must observe the future exception/translate overload |
| **CallerRunsPolicy** | Runs immediately on the task-submitting thread | Can slow down the producer, **but risks pulling business code back onto the HTTP completion thread** |
| **DiscardPolicy** | Silently drops the task | Dangerous with futures: they may never complete as expected |
| **DiscardOldestPolicy** | Drops the oldest queued task and retries | Easily loses requests/correlation; requires strong cancellation/telemetry policies |

For an HTTP pipeline, **AbortPolicy + in-flight limit + explicit overload error** is usually easier to control than CallerRunsPolicy when the primary goal is not blocking completion threads. However, no policy creates system-wide backpressure on its own: you must **cap in-flight requests** before calling sendAsync and release the permit when the request + business continuation finish.

### Semaphore for in-flight limiting (snippet)

~~~java
// Illustration for the request-receiving layer; permits are acquired only where
// waiting is allowed, or use tryAcquire to fail fast.
Semaphore permits = new Semaphore(50);

if (!permits.tryAcquire()) {
    // Reject/queue at the application layer per overload policy.
} else {
    client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
          .thenApplyAsync(resp -> transform(resp.body()), businessExecutor)
          .whenComplete((value, error) -> permits.release());
}
~~~

The variables request, businessExecutor, and transform are defined in the application; this is not a standalone file. The release callback must be **extremely short** and do no blocking work; **whenComplete** here only releases the permit and does not meaningfully impede I/O. If a synchronous exception occurs before creating the future, there must be a separate release branch. Do not grant unlimited permits or hold onto a permit if a callback is skipped.

**Important distinction between the two caps:** in-flight requests limit the number of live HTTP operations; the bounded executor queue limits queued business continuations. They address different parts of the pipeline, so you need both if the system is prone to overload.

## 9. Handling exceptions, timeouts, and cancellation properly

### 9.1. Observe both network failures and business failures

~~~java
// Snippet: place business logic on an explicit executor.
CompletableFuture<Result> pipeline =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .thenApplyAsync(resp -> parseAndValidate(resp),
                              businessExecutor);

pipeline.whenComplete((result, error) -> {
    if (error != null) {
        recordFailure(error); // Should be fast and non-blocking.
    }
});
~~~

The identifiers Result, parseAndValidate, and recordFailure are illustrative application code. If an HTTP/TLS/timeout error occurs before the processing stage, **thenApplyAsync does not run**, and the pipeline completes exceptionally. If the business callback throws a RuntimeException, the pipeline also fails. When intentional recovery is needed, you can use **exceptionally**, **handleAsync**, or **exceptionallyCompose** (Java 12+), but do not accidentally swallow errors and report success.

**CompletionException** typically wraps the actual cause. With **get()**, the caller receives **ExecutionException** when the future fails; with **join()**, the caller typically receives CompletionException. Log the cause/correlation ID without exposing tokens/cookies.

### 9.2. Timeouts exist at multiple layers

- **HttpClient.Builder.connectTimeout(...)**: connection establishment timeout.
- **HttpRequest.Builder.timeout(...)**: request timeout per the HttpClient contract, which can result in **HttpTimeoutException**.
- **CompletableFuture.orTimeout(...)**: completes the future exceptionally after a deadline if not yet done; **does not guarantee** that underlying I/O or background business tasks stop immediately.
- **get(timeout, unit)**: limits how long the **caller thread waits**, which does not automatically mean the request was cancelled on the server.
- **Business deadline**: typically requires a total budget covering network + parsing + database + downstream calls.

Do not use **orTimeout(5s)** and assume a CPU-heavy callback or JDBC call has been interrupted. Cancellation mechanisms on CompletableFuture and the HTTP client have their own rules; to release resources early, you must design cancellation/deadlines at each layer.

### 9.3. Do not blindly retry on every error

When an async request fails, retrying can amplify load right when the business pool or server is already overloaded. Only retry idempotent/contract-safe requests; cap attempts, apply backoff/jitter, and enforce an overall deadline. If a delay is needed, use **ScheduledExecutorService** or an appropriate scheduling mechanism, **not Thread.sleep inside a completion callback**.

### 9.4. Cleaning up executors according to the Java 17 lifecycle

In Java 17, **ExecutorService cannot be used with try-with-resources as a universal AutoCloseable**; you must call shutdown and awaitTermination. **Java 17's HttpClient is also not an AutoCloseable to wrap in try-with-resources as in newer JDK versions**. Create a reusable HttpClient and manage custom executors according to the application lifecycle.

~~~java
// Shutdown illustration; if placed in finally, ensure you still
// handle InterruptedException and clean up remaining resources.
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Pool did not terminate");
    }
}
~~~

**shutdownNow() only requests worker interruption and does not guarantee immediate termination of every block.** Do not shut down the business executor while continuations from live requests have not yet been scheduled, as those stages may be rejected. The usual sequence is to stop accepting new requests, handle/cancel in-flight ones, wait for necessary stages, and then shut down executors according to ownership.

## 10. Measuring and diagnosing thread starvation

Do not see high CPU and immediately conclude HttpClient is at fault. Gather evidence from thread dumps, timers, and queues.

| Metric / observation | Possible interpretation |
| --- | --- |
| **HTTP request latency** increases | Network, server, DNS/proxy, or insufficient client executor capacity |
| **Network response arrives quickly but business stage is slow** | Business pool saturated, queue delay, or heavy callback |
| **businessPool.getActiveCount()** stays near max for a long time | Workers are consistently busy |
| **businessPool.getQueue().size()** grows | Producer is faster than consumer; latency/memory risk |
| **businessPool.getCompletedTaskCount()** stops increasing | Tasks may be blocked, deadlocked, or making no progress |
| **RejectedExecutionException** increases | Queue/workers are full; throttling/backpressure needed |
| **Thread dump: http-client-* blocked on JDBC/lock** | Business logic is likely running on the wrong executor |
| **ForkJoinPool.commonPool-worker-* busy with business work** | Possibly a thenApplyAsync call without an explicit executor |
| **Connection leaks / rising file descriptors** | Check BodySubscriber/InputStream handling, cancellation, and response lifecycle |

**Limitations of metrics:** getActiveCount, getQueue().size, and getCompletedTaskCount are approximate snapshots in a live system; do not treat them as strict invariants at every instant. Measure p50/p95/p99 latency percentiles, in-flight count, queue wait time, throughput, and rejection rate across multiple load intervals.

### A test to detect blocking callbacks

A useful load-test scenario:

1. Use a local test server capable of returning small responses at a target concurrency level.
2. Place a time-consuming transformation callback on the business executor, ensuring the HttpClient executor does not run that callback.
3. Measure response progress, business queue, completion time, and timeouts. With proper pool isolation, a slow business callback **does not directly occupy** threads used for HTTP progress.
4. Increase load to the bounded queue threshold; verify overload is reported clearly and no requests hang indefinitely.
5. Shut down; verify thread pools terminate, in-flight drops to 0, and no resources are leaked.

Do not rely on **Thread.sleep(100)** to prove which thread runs a callback. The Java example in Section 6 checks the thread name **directly inside the stage**, providing concrete verification rather than guessing from scheduling behavior.

## 11. Project application checklist

1. Clearly distinguish the **HttpClient executor** and the **business executor**; do not merge them arbitrarily when business tasks involve blocking or heavy CPU work.
2. Remember that **non-Async thenApply/whenComplete** can run on the completing/calling thread.
3. Use **thenApplyAsync(..., explicitExecutor)** for heavy work that needs pool control.
4. Use **thenCompose** to chain APIs that already return futures instead of calling join/get in between.
5. Use **thenComposeAsync** if preparing the request/downstream stage involves heavy work.
6. Do not put blocking JDBC, heavy parsing, or sleep inside **BodyHandler/BodySubscriber mapping callbacks**.
7. Size CPU pools by core count and blocking pools by concurrency/connection limits.
8. Bound **worker threads, task queues, and in-flight HTTP requests**; have an observable overload policy.
9. Be wary of **CallerRunsPolicy** as it can push heavy work back onto completion threads.
10. Have timeouts/cancellation at each layer; do not assume get(timeout) will automatically stop background work.
11. On shutdown, wait for in-progress stages to finish and then clean up executors; Java 17 does not use try-with-resources for HttpClient.
12. Monitor thread dumps, queue wait, active count, response latency, completed tasks, rejections, and cleanup.
13. Test exceptions from both HTTP and business callbacks to ensure the pipeline propagates errors properly.
14. Do not assume async is always faster than sync; performance depends on load, pool sizing, deadlines, and backpressure.

## 12. Self-check questions

**Question 1.** Since sendAsync returns a CompletableFuture, is a thenApply callback guaranteed to run on a business pool thread?  
**Answer:** No. thenApply has no explicit executor; it may run on the completing/calling thread depending on completion timing.

**Question 2.** Does thenApplyAsync(fn) without an executor run on the pool chosen by HttpClient.Builder.executor?  
**Answer:** You cannot assume that. It uses the CompletableFuture's default asynchronous execution facility; for a standard CompletableFuture, that is usually commonPool. To choose explicitly, use thenApplyAsync(fn, businessExecutor).

**Question 3.** Why shouldn't you call dao.findById(...) directly inside thenApply of an HTTP future?  
**Answer:** Blocking DAO calls can occupy the completion thread, slowing down the progress of other asynchronous HTTP tasks. Place JDBC on an appropriate blocking executor.

**Question 4.** Is CompletableFuture.allOf(...).get(...) in the demo wrong?  
**Answer:** No, because that is the CLI test program boundary waiting for results. Avoid calling get/join inside event-loop threads or callbacks that must remain non-blocking.

**Question 5.** How does thenCompose help compared to thenApply combined with join?  
**Answer:** It flattens a CompletionStage returned by the function, chaining two async operations without holding a thread waiting for the next Future.

**Question 6.** Why can CallerRunsPolicy backfire?  
**Answer:** When the pool is full, it runs the rejected task on the submitting thread; that thread may be handling HTTP completion, causing business work to block the I/O processing path.

**Question 7.** Does newFixedThreadPool(4) automatically create a bounded queue?  
**Answer:** No. By default, newFixedThreadPool's queue is unbounded, so you must design a bounded queue/backpressure if load is high.

**Question 8.** What happens if a callback is registered with thenApplyAsync but the business executor is shut down?  
**Answer:** Scheduling may be rejected and the pipeline will fail; you must manage lifecycles to avoid shutting down before in-flight stages complete.

**Question 9.** Where does BodySubscribers.mapping run, and is it okay to do long blocking InputStream reads inside it?  
**Answer:** The mapper runs using the client executor per the JDK 17 documentation; long blocking reads can cause starvation. Move heavy reading/parsing elsewhere and close the stream.

**Question 10.** Does orTimeout(...) definitely interrupt both the HTTP request and a waiting JDBC call?  
**Answer:** No. It affects the future's state after the deadline; cancelling background activities must be designed per layer.

**Question 11.** Why does the demo have three executors?  
**Answer:** webServerPool serves the loopback HTTP fixture; clientTasks is the HttpClient executor; businessPool runs the explicit continuation. Separating them clearly shows the continuation does not rely on HttpClient threads.

**Question 12.** When should you use whenComplete instead of handle?  
**Answer:** whenComplete primarily observes the result/error and preserves the original outcome; handle can transform the outcome into a different value. For heavy callbacks, use the Async variants with an explicit executor.

## Conclusion

With Java 17 asynchronous HTTP, **sendAsync** only solves the non-blocking request-sending aspect for the caller; **continuation work still needs to be properly designed and scheduled**. A non-Async stage can run on the thread completing the request. An Async stage without an executor uses the default asynchronous facility, not a business executor by default. **thenApplyAsync(..., businessExecutor)** and **thenCompose(...)** are two key tools for preserving I/O progress while handling business logic within bounds.

To avoid merely shifting congestion from I/O threads to another queue, you need **bounded executors, in-flight limits, overload policies, deadlines, cancellation control, and cleanup**. Measure in practice rather than inferring from method names or thread counts.

### Official references

- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): executor(...) and default executor.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): sendAsync, executor(), and client lifecycle.
- [Java SE 17 — java.net.http package](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/package-summary.html): callback scheduling and dependent tasks.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): non-async/async policies, thenApplyAsync, thenCompose, completion errors.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): composition and handling.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue bounds, sizing, and rejection.
- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded task queue.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): mapping and blocking mapper caveat.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): handling response bodies.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local loopback server in integration tests.
