# Limiting Concurrent HTTP Requests Instead of Creating Unbounded Futures in Java

**`HttpClient.sendAsync(...)` returns a `CompletableFuture<HttpResponse<T>>` as soon as the request is initiated, but it does not automatically limit the number of calls submitted by the application.** If you run a loop over hundreds of thousands of elements and create a Future for all of them before waiting for results, you can overload the client, target server, network, memory, or orchestration system.

The right approach when the number of requests is large is **bounded concurrency (in-flight limit)**: allow at most `K` HTTP operations pending at a time. Only when an operation finishes — whether with success **or** error — is a slot granted for the next request. For continuous work streams, you also need to bound the **waiting queue** and have a clear rejection/waiting policy to avoid shifting overload from the network into RAM.

This Knowledge article belongs to the **Asynchronous HTTP** topic. It focuses on limiting concurrent HTTP requests, distinguishing between a Future and an actual operation, slot allocation strategies, handling success/error/timeout/cancel, backpressure, fairness, per-host limits, and observability. Two complete Java 17+ programs will illustrate:

1. **`SemaphoreHttpDemo.java`:** the producer thread acquires a permit before calling `sendAsync`, and the callback releases the permit; 12 HTTP requests, maximum 3 outstanding, without holding a list of 12 futures.
2. **`AsyncWindowDemo.java`:** an asynchronous sliding window maintains at most 3 requests via an event dispatcher, **without blocking the producer/event-loop in `Semaphore.acquire()`** and without pre-creating futures for the entire dataset.

The examples use an in-process HTTP server bound to `127.0.0.1` and an ephemeral port; no Internet access is required and no traffic is sent to external services. Latency between responses can vary, so we only assert deterministic outputs from counters/invariants, **not relying on response completion order**.

## 1. Why Does “Async” Not Mean “Unbounded”?

Consider the following illustrative snippet (requires `client` and a collection `urls` to be declared):

~~~java
List<CompletableFuture<HttpResponse<String>>> futures =
        new ArrayList<>();

for (URI uri : urls) {
    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    futures.add(client.sendAsync(
            request, HttpResponse.BodyHandlers.ofString()));
}

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])).join();
~~~

This is an **anti-pattern for unbounded datasets**, not recommended code when the number of URLs is very large. `sendAsync` does not block until the response completes, so the loop can submit a huge number of requests before the network has a chance to finish processing them. `allOf(...).join()` only waits **after all futures have been created**; it does not reduce the number of in-flight requests.

Consequences can include:

- **Client:** spawns many HTTP connections/streams, TLS handshakes, I/O tasks, headers, body subscribers, ByteBuffers, and heap data.
- **Target server:** too many simultaneous requests cause queueing, timeouts, rate limiting, 429/503 status codes, or overload.
- **Application:** the `futures` list and lambdas hold references to requests/responses/attachments, increasing GC pressure and even causing OOM.
- **External systems:** databases, API gateways, and server downstreams can also be dragged into overload.
- **Controllability:** it is hard to know which requests are still active, when it is safe to submit more, how many have failed, and when to stop.
- **Retries:** if all requests fail at the same time and retry immediately, it easily creates a **retry storm**.

**`CompletableFuture` is a representation of a deferred result, not a resource throttle.** `CompletableFuture.allOf(...)` helps *coordinate waiting*, not *limit concurrency*. Similarly, `client.sendAsync(...)` is convenient but does not itself control the number of business requests you want in-flight.

## 2. Where Is an “In-Flight” Request Measured From and To?

Let us clearly define **the unit being bounded**:

> A logical request occupies **one slot** from right before the application submits `HttpClient.sendAsync` until the operation finishes and the result-handling callback has completed enough to release the slot.

In both examples, the body handler is `HttpResponse.BodyHandlers.ofString(UTF_8)`, so the Future completes after the response body has been collected and converted into a String. Thus, each slot covers the phase of receiving the **entire** response text.

~~~text
                     Application request #17
                             |
                     acquire one slot
                             |
                             v
                    HttpClient.sendAsync(...)
                             |
                     request in-flight
                             |
               +-------------+-------------+
               |                           |
          HTTP response                  exception
               |                           |
          inspect status                inspect cause
               |                           |
               +-------------+-------------+
                             |
                    completion handler
                             |
                      release one slot
                             |
                    admit next request
~~~

**Two points to distinguish:**

1. *In-flight logical requests* are different from **the number of TCP sockets**, HTTP/2 streams, executor threads, or Future objects ever created. One HTTP/2 connection can carry multiple requests; one logical request can encounter redirects/retries and generate additional network activity. This article limits operations at the **application layer**.
2. If you use a streaming body handler such as `BodyHandlers.ofInputStream()`, the Future may complete **before the body stream is fully read**. If you release the permit as soon as `HttpResponse<InputStream>` arrives, the limit only governs header reception/stream initialization, **not the number of active downloads**. In streaming cases, hold the slot until the consumer finishes reading/closes the stream, or use a separate accounting mechanism.

**Invariants to maintain:**

~~~text
0 <= inFlight <= MAX_IN_FLIGHT

slot acquired before submit
slot released exactly once on terminal outcome
no slot acquired --> do not submit
slot released --> admit next request
~~~

A failed operation **must still release its slot**. If the callback only releases on status 200, a 500 error or an exception can cause the system to hang indefinitely (permit leak).

## 3. Three Different Limits: Concurrency, Rate, and Queue

| Limit Type | Example | What It Controls | Does Not Replace |
| --- | --- | --- | --- |
| **Concurrency limit** | Max 3 HTTP requests in-flight | How many operations are simultaneously waiting on network/response | Long-term rate limit and backlog |
| **Rate limit** | Max 20 requests/second | Average/issuing request rate over time | Outstanding count when server responds slowly |
| **Backlog / queue bound** | Max 100 pending jobs | Number of unsubmitted jobs held in memory | Active concurrency |

A limit of 3 requests does not guarantee at most 3 requests/second: if the server responds quickly, a single second can complete many requests. Conversely, a rate limit of 20 requests/second does not guarantee few in-flight requests: when each request takes 30 seconds, many requests still accumulate.

A safe pipeline typically combines:

~~~text
Incoming work
      |
      v
[bounded backlog <= Q] -- full --> wait / reject / shed load
      |
      v
[rate limiter if remote API has RPS quota]
      |
      v
[concurrency limiter <= K]
      |
      v
   HttpClient.sendAsync(...)
      |
      v
   response or error
      |
      +-----> release K slot
      +-----> record metrics / result
~~~

Reducing request concurrency **is not enough** when a producer can stuff millions of jobs into a waiting queue. If work is durably stored in a DB/message broker, the dispatcher can load only a small batch into RAM. If it is a live stream, you can apply backpressure to upstream or return `429`/`503` when the queue is full according to SLA.

## 4. Why Is Limiting the Thread Pool Not Enough?

A common misconception is:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(3);
HttpClient client = HttpClient.newBuilder()
        .executor(pool).build();
~~~

This is an illustrative snippet and **not** a concurrency limiter for HTTP requests. `HttpClient.Builder.executor(...)` only supplies an executor for asynchronous/dependent tasks that the client runs per its contract; `sendAsync` can still be called **many times** before tasks complete. In addition:

- An HTTP request can be waiting on I/O without occupying a platform thread for the entire wait duration.
- HTTP/2 can multiplex multiple streams over a single connection.
- `newFixedThreadPool(3)` limits executor worker threads; **it does not guarantee only three network operations are outstanding**.
- The default `newFixedThreadPool` uses an **unbounded work queue**, so the queue itself can bloat if too many tasks are submitted.
- With `CompletableFuture.thenApplyAsync(...)` without specifying an executor, Java may use `ForkJoinPool.commonPool()`; this does not impose a concurrency cap on HTTP requests either.

**Solution:** enforce the limit **before submitting `sendAsync`**, or manage a window of in-flight requests. An executor can be used alongside to run callbacks/CPU tasks, but it does not replace **admission control**.

## 5. Simple Pattern: Semaphore Issuing Permits for Running Requests

`java.util.concurrent.Semaphore` maintains a count of permits. When created as:

~~~java
Semaphore permits = new Semaphore(3);
~~~

at most three threads/units of work can hold a permit simultaneously, provided **every submission path obeys** the same Semaphore.

Valid flow:

~~~text
Producer                Semaphore(3)             HttpClient
   |                         |                      |
   | acquire()               |                      |
   |------------------------>| take 1               |
   |                         |                      |
   | sendAsync() ----------------------------------> |
   |                         |                      |
   | attach completion callback                      |
   |                         |          HTTP in-flight ...
   |                         |                      |
   |                   whenComplete                  |
   |                         | <--- completed/failed |
   |                         |                      |
   | <--- callback releases  | permit returned      |
   |                         |                      |
   +----> next request (if any)                      |
~~~

Pros: very easy to understand, no complex queue management needed for a producer running on a **dedicated thread**.

Notes:
- **`acquire()` blocks the producer thread** when slots are exhausted. Do not call it directly on a UI thread, selector event loop, or a callback thread that needs to make progress to release permits.
- You can use `tryAcquire(timeout, unit)` to reject or wait with a deadline when capacity is full.
- You can configure `new Semaphore(K, true)` (fairness) if waiting order needs to be approximately FIFO; untimed `tryAcquire()` has its own fairness semantics per the Javadoc.
- A permit held by a request is **released exactly once** after the operation reaches a terminal state. If `sendAsync` throws a RuntimeException immediately at initiation, you must release the permit in the catch branch.
- If a request times out or is cancelled, **do not** arbitrarily call `release` while I/O is still genuinely running; you must define a cancellation policy and terminal state to preserve the meaning of the concurrency cap.
- The producer does not need to store **every Future**: it can hold a `CountDownLatch` for a finite batch, or counters/a streaming result sink.

## 6. Complete Example 1 — Semaphore Blocking Producer, Max 3 HTTP Requests

The program **`SemaphoreHttpDemo.java`** sends a total of **12 GET requests** to a local HTTP server. The server returns `"item-N"` with a small delay to create overlap. The client initiates requests asynchronously, while the producer calls `permits.acquire()` before each submission.

Structure:
- One `HttpClient` reused for all requests.
- One `Semaphore(3)` issuing exactly three permits for in-flight requests.
- `AtomicInteger active` tracks operations submitted whose callbacks have not yet completed; `peak` records the highest observed level.
- `whenComplete(...)` checks status/body, and in `finally` always decrements the counter, releases the permit, and counts down `CountDownLatch`.
- No 12-element `List<CompletableFuture<?>>`; Futures are not retained after registering the callback.
- If the `sendAsync` call throws synchronously, the `catch(RuntimeException)` branch still cleans up the slot.

Create the file **`SemaphoreHttpDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreHttpDemo {
    static void reply(HttpExchange exchange) throws IOException {
        try {
            Thread.sleep(60); // Only to simulate the server processing for a moment.
            String suffix = exchange.getRequestURI().getPath()
                    .substring("/item/".length());

            byte[] body = ("item-" + suffix)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        final int total = 12;
        final int limit = 3;

        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverWorkers);
        server.createContext("/item/", exchange -> {
            try {
                reply(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            int port = server.getAddress().getPort();
            Semaphore permits = new Semaphore(limit);
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();
            AtomicInteger succeeded = new AtomicInteger();
            AtomicInteger failed = new AtomicInteger();
            CountDownLatch done = new CountDownLatch(total);

            for (int id = 1; id <= total; id++) {
                // Block ONLY the producer thread if 3 requests are already in-flight.
                permits.acquire();

                int item = id;
                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);

                try {
                    HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/" + item))
                            .timeout(Duration.ofSeconds(3))
                            .GET()
                            .build();

                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                            .whenComplete((response, error) -> {
                                try {
                                    if (error == null
                                            && response.statusCode() == 200
                                            && ("item-" + item)
                                            .equals(response.body())) {
                                        succeeded.incrementAndGet();
                                    } else {
                                        failed.incrementAndGet();
                                    }
                                } finally {
                                    active.decrementAndGet();
                                    permits.release();
                                    done.countDown();
                                }
                            });

                } catch (RuntimeException e) {
                    // Only handle errors occurring when creating/submitting the request.
                    failed.incrementAndGet();
                    active.decrementAndGet();
                    permits.release();
                    done.countDown();
                }
            }

            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }

            System.out.println("Total requests: " + total);
            System.out.println("Successful: " + succeeded.get());
            System.out.println("Failed: " + failed.get());
            System.out.println("Peak <= limit: " + (peak.get() <= limit));
            System.out.println("Active after completion: " + active.get());

        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 SemaphoreHttpDemo.java
java SemaphoreHttpDemo
~~~

**Output on a normally functioning localhost environment:**

~~~text
Total requests: 12
Successful: 12
Failed: 0
Peak <= limit: true
Active after completion: 0
~~~

### What Guarantees No More Than 3?

1. `permits.acquire()` happens **before** `sendAsync`.
2. When three requests are non-terminal, `Semaphore` has 0 permits remaining, so the producer pauses at `acquire`; no fourth request is submitted.
3. The `whenComplete` callback runs whether the Future completes normally or exceptionally, so the `finally` branch releases the permit.
4. Only after the producer receives a permit back does it send another request.
5. Because there is a single producer and each request acquires/releases exactly one permit, `active` does not exceed `limit`.

**What is not guaranteed?**
- There is no guarantee that **`peak == 3`** on every machine: the network/server may finish quickly before three are outstanding.
- There is no guarantee that the HTTP server executes three handlers concurrently at all times: the server fixture has a 4-thread pool, but the scheduler may run them in a different order.
- It does not prove optimal production throughput at `K=3`.
- It does not guarantee the remote processes everything strictly once if redirects/retries occur at the protocol or application layer.
- `done.await(10, SECONDS)` is a timeout on the waiting thread; if the timeout throws an exception, the server is closed in `finally`, which should **not** be interpreted as all HTTP operations having stopped instantaneously.

**Important practical note:** This code is a **bounded producer** model and uses a thread that may block on `acquire()`. Do not put the entire submission loop inside `CompletableFuture.whenComplete(...)` of an HTTP client with limited completion threads and block on a semaphore: if callbacks get stuck waiting for permits while callbacks themselves are needed to execute and release permits, starvation/deadlock easily occurs. Example 2 solves this using an asynchronous window.

## 7. Sliding Window: Avoiding Producer Blocking and Avoiding Creating All Futures

If the thread initiating HTTP sends is an event loop, an async API, or a pipeline with multiple producers, you can use a **window scheduler**:

~~~text
Total 12 jobs, limit K=3

Initial window:
    [request 1]  [request 2]  [request 3]

request 2 completes:
    [request 1]  [request 4]  [request 3]

request 1 completes:
    [request 5]  [request 4]  [request 3]

request 4 completes:
    [request 5]  [request 6]  [request 3]

... continue until all jobs are done.

The number of Futures held to manage active HTTP
does not exceed K per the application scheduler's invariant.
~~~

**Algorithm:** Initially send up to `K` requests. Whenever a Future completes, a callback:
1. Records the result/error.
2. Decrements the in-flight counter.
3. Takes the next job from the source (if any remain) and submits it to refill one slot.
4. When the source is exhausted and in-flight equals 0, signals completion.

For state synchronization, use a **single-thread dispatcher** that owns `nextId`, `active`, and result counters. `HttpClient`'s completion callback only **enqueues a short event** to the dispatcher; it does not directly mutate counters or resubmit from multiple threads concurrently.

**Benefits:** No need for a producer to block on a semaphore; at most `K` network requests are initiated and not yet recorded as terminal. The job source can be an iterator/DB cursor; there is no need to materialize a `CompletableFuture` list as long as the number of jobs.

**Warning about continuous data sources:** The demo has exactly 12 jobs and no external backlog. In a production server, the dispatcher only solves “in-flight count”; the input queue from API/Kafka/DB must still have its own bound.

## 8. Complete Example 2 — Event Dispatcher Keeping at Most 3 Requests

The program **`AsyncWindowDemo.java`** maintains window size = 3. It differs from the Semaphore example:
- `Window.start()` only enqueues the initial run onto a single-thread executor.
- `fill()` submits more requests **only while `active < LIMIT`**.
- The `whenComplete` callback calls `events.execute(...)` so state updates always execute on the **single dispatcher thread**.
- `fill()` runs again after each completion, without holding all Futures and without using `Semaphore.acquire()`.
- One `CountDownLatch(1)` lets main wait until all are terminal; no `CountDownLatch(12)` or array of futures is required.
- A request returning an HTTP status other than 200 or a failed Future is counted as failed and still frees the slot, preventing starvation.

Create the file **`AsyncWindowDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncWindowDemo {
    static final int TOTAL = 12;
    static final int LIMIT = 3;

    static final class Window {
        final HttpClient client;
        final int port;

        // ONLY the dispatcher thread modifies the fields below.
        final ExecutorService events =
                Executors.newSingleThreadExecutor();
        final CountDownLatch finished = new CountDownLatch(1);

        int next = 1;
        int active = 0;
        int peak = 0;
        int succeeded = 0;
        int failed = 0;

        Window(HttpClient client, int port) {
            this.client = client;
            this.port = port;
        }

        void start() {
            events.execute(this::fill);
        }

        void fill() {
            while (active < LIMIT && next <= TOTAL) {
                final int id = next++;
                active++;
                peak = Math.max(peak, active);

                try {
                    HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/" + id))
                            .timeout(Duration.ofSeconds(3))
                            .GET()
                            .build();

                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                            .whenComplete((resp, error) ->
                                    events.execute(() -> {
                                        active--;
                                        if (error == null
                                                && resp.statusCode() == 200
                                                && ("item-" + id)
                                                .equals(resp.body())) {
                                            succeeded++;
                                        } else {
                                            failed++;
                                        }
                                        fill();
                                    }));

                } catch (RuntimeException ex) {
                    // If creation/submission fails synchronously, handle via
                    // the same dispatcher so active does not get stuck.
                    events.execute(() -> {
                        active--;
                        failed++;
                        fill();
                    });
                }
            }

            if (next > TOTAL && active == 0) {
                finished.countDown();
            }
        }
    }

    static void reply(HttpExchange ex) throws IOException {
        try {
            Thread.sleep(60);
            byte[] body = ("item-" + ex.getRequestURI().getPath()
                    .substring("/item/".length()))
                    .getBytes(StandardCharsets.UTF_8);
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            ex.close();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverWorkers);
        server.createContext("/item/", ex -> {
            try {
                reply(ex);
            } catch (IOException e) {
                ex.close();
            }
        });
        server.start();

        Window window = null;
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            window = new Window(client, server.getAddress().getPort());
            window.start();

            if (!window.finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }

            System.out.println("Submitted: " + (window.next - 1));
            System.out.println("Succeeded: " + window.succeeded);
            System.out.println("Failed: " + window.failed);
            System.out.println("Max active <= limit: "
                    + (window.peak <= LIMIT));
            System.out.println("Remaining active: " + window.active);

        } finally {
            if (window != null) {
                window.events.shutdownNow();
            }
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac -encoding UTF-8 AsyncWindowDemo.java
java AsyncWindowDemo
~~~

Output when the machine allows TCP loopback:

~~~text
Submitted: 12
Succeeded: 12
Failed: 0
Max active <= limit: true
Remaining active: 0
~~~

### Why Is This an “Async Sliding Window”?

- `fill()` on the dispatcher runs fast to submit up to three requests; it **does not wait on the network with `Future.get()` or `Semaphore.acquire()`**.
- When an HTTP operation completes, `whenComplete` is invoked; this callback **does not mutate state directly** but only submits the `onCompletion` logic to `events`.
- Because only the dispatcher modifies `active` and `next`, invariants can be reasoned about sequentially, avoiding races between callbacks.
- `active--` and result handling occur **before** `fill()`; a newly freed slot can be used immediately for the next item.
- `finish.countDown()` (in code `finished.countDown()`) only happens when **all 12 items have been submitted and active == 0**.
- There is no list of 12 Futures; the lifetime of incomplete Futures is tied to the HTTP client/provider and each operation's callback, while the dispatcher only keeps the required number of operations in-flight.

**Some limitations of the demo:** `events` is a dedicated executor for a single window for clarity; production may use a shared event loop or one dispatcher for multiple windows. If you stop the dispatcher while callbacks can still call `events.execute`, callbacks may receive `RejectedExecutionException`; a clear shutdown protocol, drain/cancel, timeout, and CLOSED state are needed. The example only shuts down after `finished` reaches 0 on the success path and omits complex retry/cancel control from this practice exercise.

### Comparison with Semaphore

| Criterion | Semaphore producer | Async window dispatcher |
| --- | --- | --- |
| Acquiring slot | `permits.acquire()` before `sendAsync` | `fill()` submits only when `active < LIMIT` |
| When slots exhausted | **Blocks** producer thread | Returns; completion callback triggers next request |
| State-managing thread | Producer + callbacks, using AtomicInteger/Semaphore | Single dispatcher thread owns state |
| Best suited for | Small/medium batches, dedicated producer that can wait | Async service/event loop, job sources with an iterator |
| Futures to retain | No need to hold all; handler receives completion | No need to hold all; only active window |
| Risk | Blocks event-loop if used in the wrong place | Must manage dispatcher shutdown and event ordering |

You do not need to combine both at the same time for every system. Use one consistent, observable admission-control model that fits the application lifecycle.

## 9. Bounded Micro-Batches: Simple Approach That Creates Gaps

Another approach is splitting work into **batches of size K**, sending `K` requests together, waiting for the entire batch to complete, and then moving to the next batch. **Pseudocode** example:

~~~text
for each batch of K jobs:
    futures = submit each job in batch using sendAsync
    await CompletableFuture.allOf(futures)
    handle results, successes, errors
    clear references
~~~

Pros: very simple, at most `K` in-flight, and the number of Futures held in RAM corresponds to just one batch. Cons: when one request in a batch is slow, other already-finished requests **cannot be replaced by new jobs** until the entire batch finishes. This is **batch-level head-of-line blocking**, not an HTTP bug.

A **sliding window** reuses a slot as soon as an individual completion occurs, so it generally maintains steadier concurrency when latency is uneven. For very small N, micro-batching can still be a reasonable and simple choice.

**Do not confuse:** **Building a list of all N futures and calling `allOf` once** is not micro-batching. Batches must be submitted in **size-bounded** groups, and you only move to the next group after the previous group has been processed.

## 10. Callbacks Must Release Slots on Every Terminal Path

An error pattern that hangs the system:

~~~java
// ANTI-PATTERN — does not release when response fails.
client.sendAsync(request, BodyHandlers.ofString())
        .thenAccept(response -> {
            if (response.statusCode() == 200) {
                permits.release();
            }
        });
~~~

If the Future completes exceptionally, `thenAccept` will not be called. If the HTTP status is 429, 500, or 404, the callback may run without releasing. Once `K` permits are held, all future requests may stall at admission control.

A more correct pattern:

~~~java
permits.acquire();
try {
    client.sendAsync(request, BodyHandlers.ofString())
            .whenComplete((response, error) -> {
                try {
                    if (error != null) {
                        recordFailure(error);
                    } else {
                        handleHttpStatus(response.statusCode());
                    }
                } finally {
                    permits.release();
                }
            });
} catch (RuntimeException submitFailure) {
    permits.release();
    throw submitFailure;
}
~~~

This is a **snippet** requiring `client`, `request`, `permits`, and the two business methods `recordFailure`, `handleHttpStatus` to be declared. Once `whenComplete` is attached successfully, the callback owns the release responsibility; the catch branch applies only to synchronous creation/submission failures. **Do not release a second time elsewhere** when the callback also runs.

**Good signal:** `inFlight = submitted - terminalCallbacks`, per application accounting, must always stay in the range 0..K. If `inFlight != 0` after all jobs finish, look for permit leaks, blocked callbacks, non-terminal Futures, or improper shutdown.

## 11. Why Not Block in a Callback or Event Loop?

`CompletableFuture.whenComplete(...)` does not necessarily run on a dedicated thread reserved for your work; Java may execute dependent non-async actions directly on the thread that completes the Future or the thread calling the method. Therefore:

~~~java
// DO NOT DO THIS: completion callback may block waiting for a permit.
future.whenComplete((result, error) -> {
    permits.acquireUninterruptibly();
    submitMoreWork();
});
~~~

The snippet above is an **anti-pattern**. If completion threads are occupied waiting for permits, while permit-release logic also needs completion callbacks, starvation/deadlock can result. Avoid:
- Calling long `Thread.sleep`, blocking DB queries, or heavy CPU work inside callbacks running on I/O/completion threads.
- Waiting on `join()/get()` of another Future when doing so prevents those Futures from completing.
- Calling `Semaphore.acquire()` on a thread that must not block, such as JavaFX UI or a selector/event loop.

Instead:
1. **Keep callbacks short**, only recording the terminal outcome and emitting an event to the scheduler.
2. Offload heavy business logic to an executor with bounded threads and a bounded queue.
3. Use an event-loop/actor that owns state, or careful synchronization if there are multiple producers.
4. When chaining with `thenApplyAsync/whenCompleteAsync`, **choose an appropriate executor and bounded queue**; do not assume async callbacks are automatically free.

If business work (e.g., parsing 10 MB JSON) also needs bounding, create a **separate budget for post-processing**. When you release the HTTP permit before heavy processing, HTTP concurrency remains protected, but CPU/backlog can grow; separate metrics and budgets per layer.

## 12. With Streaming Bodies, When Should the Permit Be Released?

Both examples use `BodyHandlers.ofString(UTF_8)`. With this handler, `HttpResponse<String>` already contains the body text per contract before the Future completes; holding the slot until the callback represents the response download time.

However, with:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, BodyHandlers.ofInputStream());
~~~

the Future may complete as soon as response headers arrive, while the `InputStream` still has **unread** data. If you release a permit immediately when `future.complete` happens, you can open many download streams without being bounded by the permit count.

Conceptually correct pattern (pseudocode):

~~~text
acquire download slot
sendAsync(..., ofInputStream())
when response stream becomes available:
    hand off stream to a bounded consumer executor
    consumer reads/copies with byte limits and timeout
    finally:
        close stream
        release download slot
if sendAsync failed before stream exists:
    release download slot
~~~

This is not full runnable Java code; it illustrates resource **lifetime**, not just a single API method. With `BodyHandlers.ofFile(path)`, a successful Future generally indicates the body has been written to the file, but you still must clean up partial files on error and maintain a separate disk quota. With `BodyHandlers.discarding()`, no body is retained, yet I/O still occurs, so you must still limit in-flight requests when calling APIs in bulk.

## 13. Per-Host, Per-Tenant, and System-Wide Limits

A global `Semaphore(10)` limits at most 10 HTTP jobs across the **entire application**, but a service may need to call multiple endpoint types with different SLAs:

~~~text
                     Global budget: 20
                           |
            +--------------+--------------+
            |              |              |
       Service A        Service B      Service C
       per-host 5       per-host 8     per-host 7
            |              |              |
         sendAsync       sendAsync       sendAsync
~~~

A design may use:
- **Global** concurrency limit protecting RAM, file descriptors, and overall outbound capacity.
- **Per-host/per-service** limit so a slow downstream does not consume all slots.
- **Per-tenant** limit to prevent one user from monopolizing capacity.
- **Rate limiting** per provider API quota (requests/second or token bucket).
- **Byte/body counters** separate from request count when payloads vary widely.

**Avoid deadlock when acquiring multiple permits:** Choose a consistent acquisition order, release reliably, or use a unified scheduler that grants both budgets together. Do not let thread A hold a global permit while waiting for a host permit while another operation holds a host permit and waits for global in the reverse order.

**Avoid starvation:** A fair queue or per-tenant scheduler may be necessary if a fast host continually “steals” slots from a slow host. Semaphore has a fairness option, but a single semaphore's fairness does not automatically solve all business priority/quota policies.

## 14. Choosing K Based on Latency, Throughput, and Resources

There is no single best value of `K` for all systems. You must consider:
- Average and P95/P99 request latency.
- Response size, `BodyHandler` type, and heap/disk budget.
- Remote API quota/rate-limit.
- HTTP protocol behavior, connection reuse, and HTTP/2 multiplexing.
- TLS/DNS/proxy overhead and connection/file descriptor limits.
- Downstream capacity and body-processing CPU.

An intuitive formula from **Little’s Law**, when the system is relatively stable:

\[
L \approx \lambda W
\]

Where:
- `L`: average number of in-flight requests.
- `λ`: average completed requests per second.
- `W`: average time a request spends in the system (seconds).

As an *illustrative* example, if the target is 40 requests/second and average completion time is 0.2 seconds, the average concurrent requests is around `40 × 0.2 = 8`. That is **not a mechanical recommendation to pick K=8**: P99 latency, spikes, retries, connection setup, queueing, and RAM budgets may require a different value.

**Safe tuning:**
1. Start with a conservative `K` based on API quotas and resources.
2. Measure in-flight, completion rate, queue wait time, P50/P95/P99 latency, 429/503/5xx, timeouts, heap, and CPU.
3. Increase gradually when throughput genuinely improves without abnormal error/latency spikes.
4. Decrease when you observe rate limiting, rising queue wait, errors, or load exceeding budget.
5. Adaptive concurrency can be considered, but you still need a hard upper bound and stability policy.

**A concurrency cap does not replace a circuit breaker.** When a downstream fails continuously, a circuit breaker can stop sending for a period, whereas a concurrency cap only limits the number of operations passing through.

## 15. Backpressure: Do Not Pile Pending Work into RAM

A semaphore with `acquire()` blocks the producer, but if the producer has **already** read all 1 million jobs into a `List`, you still consume that memory. Similarly, a sliding window limits in-flight requests, but it does not protect an unbounded `ConcurrentLinkedQueue` sitting in front of it.

Policies when full:

| Policy | Mechanism | Use When |
| --- | --- | --- |
| Backpressure to producer | Stop reading more jobs from upstream when slots/queue are full | Streaming iterator, batch loader, pausable message broker |
| Bounded queue | Hold at most Q job metadata items; producer waits or is rejected | Service with continuous work stream |
| Fail fast / shed load | Return 429/503 or “busy” result | API cannot wait indefinitely and must protect SLA |
| Durable queue | Persist jobs to broker/DB and read only small batches | Long-running work needing retry/recovery |
| Coalescing/dedup | Merge identical requests | Refresh/cache/polling for the same resource |

**You do not need a future for every job** just to “remember to process it.” Pending state can live in an iterator, broker, or DB table. Only when a slot is free do you create `HttpRequest` and call `sendAsync` under a controlled counter.

For schedulers with an unbounded input source, ensure the job-intake mechanism **stops or returns an error when the queue is full**. Do not create an incomplete `CompletableFuture` for each job and park millions of futures in an internal queue; that is still a form of unbounded memory growth.

## 16. Timeout, Cancellation, and Terminal Conditions

**`HttpRequest` timeout:**

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

This prevents an operation from waiting indefinitely per the request timeout policy (the failure outcome may be `HttpTimeoutException`). Also configure connect timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

**`CompletableFuture.orTimeout(...)` differs from request timeout.** It transitions the Future to exceptional completion after the deadline if not yet finished, but it should not be treated as proof that the remote stopped processing or that all network/resources were immediately freed. Similarly, `future.cancel(...)` affects Future completion/cancellation per the implementation and is not a “rollback HTTP request” protocol.

Deciding **when to release the slot** depends on semantics:
- With `sendAsync(..., BodyHandlers.ofString())` and a terminal callback, the slot represents the request until the entire response body is processed.
- With `ofInputStream`, you must include the phase where the consumer reads/closes the body.
- If cancelling requests, the app must have a clear shutdown/cancel protocol, track actual active network resources, and avoid releasing the slot too early and allowing more than K requests to actually run.
- When using retries, choose a budget strategy: keep the **same logical slot** across the entire sequence of attempts, or release the slot between attempts while placing retries into a **bounded** queue. Either way, prevent double release and retry storms.

**HTTP status is not an exceptional completion by default.** A valid 429/500 response is still an `HttpResponse<T>`; the callback receives `error == null`, so the application must inspect `statusCode()` to detect business failure. If waiting on a Future with `join()`, `CompletionException` wraps the error; with `get()`, it is `ExecutionException`. Do not swallow the root cause.

## 17. How Should Retries and Redirects Be Accounted For?

A limit of “3 logical requests” does not guarantee “exact 3 HTTP transmissions at every instant”:
- One logical request may follow a redirect from the initial URL to another URL.
- An authentication challenge may trigger an additional exchange.
- Application-level or implementation-level retries may generate extra attempts, depending on failure and policy.
- HTTP/2 can send multiple streams over one connection; HTTP/1.1 has a different connection-usage model.

With backoff:
- When a request fails with 429/503, do not retry immediately and do not bypass the quota.
- Read `Retry-After` if the service contract specifies it, and cap attempts and total deadline.
- Use an idempotency key for operations with side effects when supported by the server.
- Do not create a new Future per attempt **outside admission-control** and treat it as an independent request with no budget.

**Recommendation:** treat `K` as the budget for **application-managed logical exchanges**. Track attempts, redirects, and actual TCP/HTTP resources separately if SLA requires it. When using a retry scheduler, the backoff queue also needs bounded capacity.

## 18. Synchronous Submission Errors vs. Asynchronous Completion Errors

`sendAsync` can fail at two points:

**A. Before returning a Future**: invalid arguments or a RuntimeException thrown immediately during call setup. Since a permit was already acquired, the code must release it in `catch`.

**B. After returning a Future**: DNS, connection, TLS, timeouts, I/O, body processing, etc. cause the Future to complete exceptionally; the `whenComplete((response, error) -> ...)` callback receives `error != null`.

Checkpoints needed for both:
- Every request granted a slot has **exactly one terminal cleanup path**.
- The success branch checks HTTP status; `error == null` does not imply 2xx status.
- Callback exceptions must not skip `release`; place release inside `finally`.
- Do not release in both the callback and catch for **the same request whose callback was already attached successfully**.
- With retries or cancellation, define who owns cleanup (a request state machine, not multiple ad-hoc callbacks).

Add metrics to spot leaks:

~~~text
submitted        requests actually initiated
completed2xx     terminal HTTP status 2xx
completed4xx     terminal HTTP status 4xx
completed5xx     terminal HTTP status 5xx
failedTransport  Future exceptional / network error
inFlight         submitted - terminal callbacks
queueDepth       unsubmitted jobs (bounded by Q)
acquireWaitMs    time spent waiting for a slot
peakInFlight     active peak, must be <= K
~~~

For long-running applications, note that counters are only meaningful under a consistent business definition and measurement window. One request may have multiple redirects/attempts but one logical terminal callback.

## 19. Proper Shutdown While HTTP Requests Are Still Running

In Java 17, `HttpClient` **does not have** lifecycle methods like `close()`/`shutdown()` found in newer JDKs. Do not write `try (HttpClient client = ...)` and claim the example compiles on Java 17.

When stopping a bounded scheduler:
1. Stop accepting new jobs and mark state `CLOSING`.
2. Do not submit new requests from callbacks after shutdown begins.
3. Wait for in-flight HTTP operations to finish within a defined grace period.
4. Apply a timeout/cancel policy for remaining work, without assuming cancel immediately rolls back the network.
5. Close/terminate response streams and file downloads holding resources.
6. Only shut down the dispatcher executor **after** no callbacks remain that need to enqueue results, or after a safe handler for rejected submissions is in place.
7. Flush metrics, report failed/cancelled results, and drain the bounded queue.

In `AsyncWindowDemo`, `finished.await(...)` reaches 0 on the success path before closing the dispatcher, keeping the example concise. Production must additionally handle timeout/failure/shutdown paths: if `events.shutdownNow()` is called while HTTP completion callbacks are still calling `events.execute(...)`, those callbacks may hit `RejectedExecutionException` and work will go unaccounted. Do not simply copy the demo shutdown into a long-lived service.

## 20. Testing Concurrency Limits Without Timing Dependencies

The most useful tests verify **invariants**, not output order:

- All jobs are submitted/completed exactly once per test fixture.
- Active count always stays within `0..K`.
- Peak observed `<= K`, even when every request is slow or fails.
- HTTP 200, 404, 429, 500, and transport error branches all release slots.
- No unsubmitted queued jobs remain when all active jobs finish and the producer is closed.
- With an unbounded source, `queueDepth` does not exceed Q.
- Shutdown does not leave callbacks holding references indefinitely.
- With body streaming, slots are released only after the resource is consumed/closed as defined.
- If the producer is an event loop, test that admission control **does not block** the event-loop thread.

Ways to make tests deterministic:
1. Localhost server uses `CountDownLatch` to hold a few responses **incomplete** rather than relying on `Thread.sleep` for exact ordering.
2. Feed K jobs and verify job K+1 is not yet submitted while the initial requests have not released.
3. Intentionally return a 500 response and trigger a request timeout to verify cleanup.
4. Attach atomic counters around admission/terminal callbacks and assert `max <= K`.
5. With `ExecutorService`, simulate callbacks across multiple threads to uncover races.
6. Do not enforce `peak == K` on every run of a network test; if needed, control it with a server barrier/latch.

The two demos here use `Thread.sleep(60)` **only to make overlap easy to observe**, while stdout checks invariants and success counts; they do not assert specific timing or completion order.

## 21. Common Mistakes and Fixes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Submit N Futures then `allOf` once | N requests can be in-flight simultaneously | Sliding window, Semaphore before `sendAsync`, micro-batches |
| Assuming `sendAsync` limits requests automatically | Client or downstream overloaded | Enforce cap K and backlog Q yourself |
| Limiting only the client thread pool | Many requests can still be waiting on I/O | Limit application request operations |
| `Semaphore.acquire()` in a callback needed to release permits | Starvation/deadlock | Dedicated producer or nonblocking event dispatcher |
| Releasing only on HTTP 200 | Permit leak on 404/500/exception | `whenComplete` + `finally` for every terminal outcome |
| Releasing in both callback and catch after callback took ownership | Double release, K exceeded | Single cleanup owner, clear state machine |
| Putting an unbounded queue in front of Semaphore | OOM before requests are submitted | Bounded queue/backpressure/reject |
| Keeping a `List<Future>` of millions of jobs | Retains references/heap for long periods | Window K, streaming result sink |
| Believing K requests = K TCP connections | False with HTTP/2, keep-alive, and redirects | Distinguish logical in-flight from transports |
| Using `thenApplyAsync` with unbounded CPU work | Thread pool/queue overload | Bounded worker pool and separate budget |
| Releasing slot as soon as `ofInputStream()` future finishes | Many active response streams exceed budget | Hold slot until stream is closed/consumed |
| Omitting request timeout | Hung jobs occupy slots too long | Explicit timeout policy and cancellation/shutdown |
| Thinking timeout/cancel guarantees remote stops processing | Double-processing on retry | Idempotency key, bounded attempts |
| Immediately retrying all 500/429 responses | Retry storm | Exponential backoff + jitter + Retry-After |
| Not cleaning up when `sendAsync` throws synchronously | Permit lost, scheduler stalls | Catch releases exactly once |
| Shutting down dispatcher while callbacks still arrive | RejectedExecutionException, lost accounting | Graceful drain and CLOSED state |
| Using one global cap for unfair multi-tenant workloads | Large tenant hogs slots | Per-tenant/per-host caps and fairness |
| Logging body/secrets on HTTP errors | Sensitive data exposure | Sanitize logs, limit logged content |

## 22. Self-Check Exercises

**1.** Why does `CompletableFuture.allOf(allFutures)` not limit concurrent HTTP requests?  
**Answer:** Because all `sendAsync` calls may already have been made and many operations are running before `allOf` starts waiting. `allOf` only combines completion conditions.

**2.** Does a concurrency limit of K=3 mean at most 3 requests/second?  
**Answer:** No. K limits how many are outstanding at the same moment; rate depends on latency and completion speed.

**3.** Why not just set `HttpClient.Builder.executor(Executors.newFixedThreadPool(3))`?  
**Answer:** Limiting threads does not mean limiting in-flight HTTP operations or the queue; separate admission control is required.

**4.** Should the permit be acquired before or after `sendAsync`?  
**Answer:** **Before** submitting. Acquiring afterward can allow bursts of requests to initiate beyond K.

**5.** In which cases must `whenComplete` release the permit?  
**Answer:** All terminal outcomes: HTTP status 2xx, 4xx, 5xx, and exceptional completion. Use `finally` to ensure release.

**6.** Why not block on `Semaphore.acquire()` inside a completion callback?  
**Answer:** The callback may run on a thread needed to process completions/releases; blocking it can cause starvation/deadlock.

**7.** How does a sliding window differ from micro-batching?  
**Answer:** A sliding window refills a slot as soon as a single request completes; micro-batching typically waits for the whole group before submitting the next group.

**8.** With `BodyHandlers.ofInputStream()`, does a completed Future guarantee the entire response body has been received?  
**Answer:** No. Only headers may have arrived; you must hold the budget until the stream is consumed/closed.

**9.** When a producer has 1 million jobs but K=3, do you need to create 1 million Futures and have them wait for permits?  
**Answer:** No. Only create/send a request when a slot is free; keep remaining jobs at the source, in a bounded queue, or in a durable broker.

**10.** Can you use one global Semaphore and one per-host Semaphore?  
**Answer:** Yes, but you must acquire/release in a consistent order or use a unified scheduler to avoid deadlocks and fairness issues.

**11.** The client receives 429 in the HTTP response; is the Future exceptional by default?  
**Answer:** No. That is normally a valid response with `statusCode()==429`; you must handle retry/backoff and release the slot properly.

**12.** Does `future.cancel(true)` prove the remote has not processed the POST?  
**Answer:** No. Cancellation is a client-side signal/lifecycle action; the server may already have received and executed the request.

**13.** If a callback throws an exception before releasing, what is the consequence?  
**Answer:** Permit leak. Use `try/finally` or a terminal cleanup state machine to guarantee release exactly once.

**14.** How do you test that K is not exceeded without depending on timing?  
**Answer:** Use a controlled server/latches to hold K responses, verify request K+1 is not yet submitted, track an atomic peak, and test success/failure branches.

**15.** Why can the observed peak in-flight be 2 even when LIMIT=3?  
**Answer:** One request may finish before all three are submitted or actual concurrency is lower; the key invariant is `peak <= K`, not necessarily reaching K.

## Official Documentation and Further Reading

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` returning `CompletableFuture<HttpResponse<T>>`, client reuse, executor configuration, and HTTP requests.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout, URI, method, body publishers.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString` and streaming body handlers, differences in completion/lifetime.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `whenComplete`, `allOf`, `join/get`, exceptional completion, and cancellation.
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): permits, `acquire()`, `release()`, and fairness.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): waiting for a number of terminal events.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): running tasks, shutdown, and thread lifecycle.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): localhost HTTP server used for the two test programs.
