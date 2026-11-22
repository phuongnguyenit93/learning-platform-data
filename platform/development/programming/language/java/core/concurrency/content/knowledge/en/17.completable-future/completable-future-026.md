# HTTP Request Deadlines vs. CompletableFuture Timeouts and Cancellation

## Objectives and Scope

In Java, an asynchronous HTTP call typically produces a **CompletableFuture**, but a future timing out **does not mean** the HTTP connection has stopped, and cancelling a future **does not mean** the server has stopped processing the request. This lesson distinguishes three independent decisions: **how long to wait**, **how long to bound the HTTP operation**, and **how to attempt stopping running resources**. The scope is Java 17+ with **java.net.http.HttpClient** and **java.util.concurrent.CompletableFuture**, without framework dependencies.

After this lesson, you will be able to choose timeouts at the right layer, preserve the ability to cancel the HTTP exchange when the application layer expires, interpret exceptions accurately, and design a single deadline across an entire processing chain.

## 1. Three Different Clocks

| Mechanism | Direct Effect | On Expiration / Cancellation | Does It Stop the In-Flight HTTP Call? |
| --- | --- | --- | --- |
| **HttpClient.Builder.connectTimeout(Duration)** | Time to establish a new connection | Connection failure, possibly **HttpConnectTimeoutException** | Bounds the connection phase; not the entire request |
| **HttpRequest.Builder.timeout(Duration)** | Timeout at the HTTP request execution level | Future from **sendAsync** completes exceptionally with **HttpTimeoutException** if the response does not arrive in time | HttpClient handles timeout of the exchange itself; the server may still have received/processed the request |
| **CompletableFuture.orTimeout(t, unit)** | Time for *that future* to complete | That future itself is completed exceptionally with **TimeoutException** | **Does not automatically** call cancel on the HTTP exchange |
| **CompletableFuture.completeOnTimeout(value, t, unit)** | Fallback value for that future | That future itself completes normally with **value** | **Does not automatically** stop the underlying operation |
| **future.get(t, unit)** | Time the thread calling **get** is willing to wait | The thread receives **TimeoutException** | The source future may still continue; does not auto-cancel |
| **future.cancel(true)** | Request to cancel the future | The future is cancelled, typically observing **CancellationException** | Depends on the future/source; futures from the **default HttpClient** support attempting to cancel the HTTP exchange when **cancel(true)** is called |

Key takeaway: **observation timeout** (stopping waiting for a result) is different from **transport timeout** (HTTP client enforcing a policy on the exchange), and different from **cancellation** (a request to stop, with no guarantee that the external system has stopped).

Example timeline:

~~~text
t=0 ms         t=80 ms                    t=800 ms
|--------------|--------------------------|
sendAsync()    CF layer expires           server expected to respond
    |          |
    |          +-- observer: TimeoutException
    +------------------------------------- HTTP may still be running
               |
               +-- if transport.cancel(true) is called:
                   HttpClient attempts to cancel exchange, no guarantee of server rollback
~~~

**There is no fixed precedence order** among HTTP timeout, future timeout, and cancellation: whichever event completes the future first determines the observed outcome. When deadlines are close to each other, valid outcomes may vary across runs.

## 2. Timeout of the HTTP Request Itself

Java 17 includes a standard HTTP client:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.org/resource"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> exchange =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

The snippet above is **an excerpt placed inside an appropriate method**, not a standalone Java program. The two timeouts have different meanings:

- **connectTimeout** applies to establishing a new connection; when reusing an existing connection, the connect timeout does not replace the request timeout.
- **request.timeout** sets the limit for the HTTP request. According to the Java 17 API, if the response is not received within this duration, **sendAsync** completes exceptionally with **HttpTimeoutException**. If no timeout is set, the request has no default deadline from this configuration.
- An HTTP response with status code **408**, **429**, or **504** is still an *HTTP response*; it does not automatically translate to **HttpTimeoutException**. To treat status codes as business errors, you must inspect **response.statusCode()**.
- **BodyHandlers.ofString()** buffers the body into a string before the future completes; with streaming handlers such as **ofInputStream()**, when the future completes and how the application consumes/closes the stream are two separate concerns to manage.

Do not promise that a request timeout is an absolute SLA for *everything* after HTTP: JSON decoding, business logic, executor queuing, database writes, and retries are not covered by a single request's timeout.

## 3. Timeouts and Cancellation at the CompletableFuture Layer

**orTimeout** and **completeOnTimeout** (Java 9+) **return the same CompletableFuture instance they are called on**; they do not create a new timeout wrapper. They mutate the completion state of that future:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

// Create a separate observer stage; does not mutate source's state.
CompletableFuture<String> observer =
        source.thenApply(value -> value).orTimeout(100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

If 100 ms elapses and **observer** has not completed, **observer** receives **TimeoutException**; **source** may still be incomplete. Conversely, if you call **source.orTimeout(...)**, **source** itself is marked as completed exceptionally. This can forfeit the opportunity to call **source.cancel(true)** later because `source` is already completed.

**completeOnTimeout** is used to return a fallback value:

~~~java
CompletableFuture<String> fallback =
        source.thenApply(value -> value)
              .completeOnTimeout("Data temporarily unavailable",
                      100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

A fallback value **does not confirm** that the network request has ended. It can also mask the fact that a background task is still consuming bandwidth/CPU. Only use a fallback when the business logic genuinely allows degraded results and you have an appropriate cleanup policy in place.

**get(100, MILLISECONDS)** is even narrower: it only bounds how long the calling thread waits. When **get** throws **TimeoutException**, the future may continue and complete later. Unless you intentionally interrupt or cancel the work, do not treat a **get** timeout as cancellation.

**cancel(true)** on a plain **CompletableFuture** transitions the future into a cancelled state; **mayInterruptIfRunning** itself does not cause CompletableFuture to interrupt executing threads. However, **the CompletableFuture returned by the default HttpClient from sendAsync has an additional contract**: calling **cancel(true)** while incomplete will *attempt* to cancel the HTTP exchange to release resources. Cancellation is best effort; HTTP/1.1 may close the connection, HTTP/2 may reset the stream, and the server may have already processed the request. Do not infer from **isCancelled()** that the operation on the server was rolled back.

## 4. Coordination Pattern: HTTP Deadline + Observation Deadline + Source Cancellation

When a call must obey both an HTTP timeout and the caller layer's budget, **keep a separate reference to the original HTTP future**, create an independent observer stage, and attempt to cancel the original exchange when the observer layer expires.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;

// Excerpt inside a method, assuming client and uri are already created.
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(900))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> transport =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

// thenApply creates a downstream stage; orTimeout mutates that downstream stage.
CompletableFuture<HttpResponse<String>> observed =
        transport.thenApply(Function.identity())
                 .orTimeout(1000, TimeUnit.MILLISECONDS);

observed.whenComplete((response, failure) -> {
    Throwable cause = failure;
    while (cause instanceof CompletionException && cause.getCause() != null) {
        cause = cause.getCause();
    }
    if (cause instanceof TimeoutException) {
        transport.cancel(true); // HttpClient attempts to abort the in-flight exchange.
    }
});
~~~

In the pattern above, **900 ms** is the HTTP request limit; **1000 ms** is the observer stage limit. If HTTP expires first, the failure is typically **HttpTimeoutException** propagating through the downstream stage. If the observer stage expires first (e.g., due to scheduling delays or extra stages), **TimeoutException** triggers a cancellation request on the original exchange. **You do not need to set both thresholds just "to be safe"**: choose each threshold based on the actual semantics of your system.

Note: this pattern only cancels when **observed**'s timeout is detected. If the user actively aborts the operation or the caller cancels another future, you need to wire that cancellation signal back to **transport** according to your policy. Depending on the implementation, a future derived directly from HttpClient's cancellable future may also support cancelling the exchange; keeping the **transport** handle makes the control path explicit and easy to test.

## 5. Standalone Java 17+ Program, No Internet Required

This example uses a local HTTP server from the JDK **jdk.httpserver** module. The server intentionally responds slowly, so you will observe an observer future expiring before the HTTP exchange completes, and then observe a request timeout detected by HttpClient itself.

Save the following as **HttpDeadlineDemo.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

public class HttpDeadlineDemo {
    static String causeName(Throwable error) {
        while ((error instanceof CompletionException || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error.getClass().getSimpleName();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(800);
                byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } catch (IOException ignored) {
                // Client may have abandoned the exchange.
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/slow");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();

            HttpRequest withoutDeadline = HttpRequest.newBuilder(uri).GET().build();
            CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
                    withoutDeadline, HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> observer =
                    transport.thenApply(Function.identity());
            observer.orTimeout(80, TimeUnit.MILLISECONDS);

            try {
                observer.join();
            } catch (CompletionException error) {
                System.out.println("CF observer: " + causeName(error));
            }
            System.out.println("HTTP transport still running: " + !transport.isDone());
            transport.cancel(true); // Best effort: request exchange cancellation.

            HttpRequest withDeadline = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(150))
                    .GET()
                    .build();
            try {
                client.sendAsync(withDeadline, HttpResponse.BodyHandlers.ofString()).join();
            } catch (CompletionException error) {
                System.out.println("HTTP request: " + causeName(error));
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac --add-modules jdk.httpserver HttpDeadlineDemo.java
java --add-modules jdk.httpserver HttpDeadlineDemo
~~~

Typical output in a local environment:

~~~text
CF observer: TimeoutException
HTTP transport still running: true
HTTP request: HttpTimeoutException
~~~

This simulation was compiled and run on JDK 21 (compatible with Java 17 syntax). The second line shows that **orTimeout** on the observer did not cancel **transport**; the code then explicitly calls **transport.cancel(true)**. Logged values may differ if there are environment errors or unusual scheduling; this is a mechanism verification example, not an OS timing guarantee.

## 6. Handling Exceptions Accurately

| Situation | Signal to Identify | Meaning |
| --- | --- | --- |
| Request timeout from HttpClient | **HttpTimeoutException**, or **HttpConnectTimeoutException** when connection-related | The HTTP request did not complete on time |
| Stage marked expired by **orTimeout** | **TimeoutException** | The observer stage expired; the HTTP source has not necessarily stopped |
| **get(timeout)** expired | **TimeoutException** thrown by the **get** call itself | The waiter ran out of patience; the future has not necessarily completed |
| Future cancelled | **CancellationException** | The future received a cancellation signal; does not prove rollback |
| I/O, TLS, DNS, remote disconnect errors | Errors such as **IOException**, **SSLException**, or related causes | Transport failure; do not blindly classify all of them as timeouts |
| Server returns HTTP 408/429/503/504 | **HttpResponse.statusCode()** | HTTP produced a response with a status code; requires its own business policy |

With **join()**, an asynchronous failure typically arrives wrapped in **CompletionException** whose **cause** is the root error; cancelling the future itself may throw **CancellationException** directly. With **get()**, asynchronous failures are typically wrapped in **ExecutionException**; and **get(timeout)** may throw **TimeoutException** from the wait operation itself. Therefore, classify by **cause** after unwrapping the appropriate wrappers, and **do not swallow errors** with a blanket fallback for all exception types.

Example of unwrapping the cause in a callback:

~~~java
static Throwable unwrap(Throwable error) {
    while ((error instanceof java.util.concurrent.CompletionException
            || error instanceof java.util.concurrent.ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

This is a standalone helper method that can be placed in a Java class. Check **instanceof HttpTimeoutException** before attributing a timeout **to HTTP**; a plain **TimeoutException** may only come from the CompletableFuture layer.

## 7. Designing an Overall Deadline and Avoiding Timeout Stacking

Suppose an API must respond within **1,500 ms**, but a single processing flow may involve: acquiring a connection, one or more HTTP requests, parsing the response, computation, retries, and backoff. If each step grants itself another 1,500 ms, the total duration can far exceed the initial deadline.

A sound design is to store the **absolute expiration timestamp of the entire operation** using the monotonic clock **System.nanoTime()**. Before *each* attempt, recompute the remaining time and use the minimum of the per-HTTP-attempt limit and the remaining budget.

~~~java
// Excerpt illustrating budget logic; not a complete program.
long deadlineNanos = System.nanoTime()
        + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(1500);

// Right before an HTTP attempt:
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new java.util.concurrent.TimeoutException("Overall deadline exceeded");
}
long perAttemptNanos = Math.min(
        remainingNanos,
        java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(700));

HttpRequest attemptRequest = HttpRequest.newBuilder(uri)
        .timeout(java.time.Duration.ofNanos(perAttemptNanos))
        .GET()
        .build();
~~~

**System.nanoTime()** is suitable for measuring elapsed time because it is not affected by wall-clock adjustments like **currentTimeMillis()**. The nanosecond addition pattern above assumes short, realistic budgets; for very large deadlines, watch out for **long** overflow. When scheduling retries/backoff, recheck **remainingNanos** and **do not issue a new request** if the budget is exhausted. When a request times out, do not silently retry indefinitely: enforce a retry cap, backoff, and a policy to retry only when idempotency allows.

If the UI/caller layer stops caring, you can use a dedicated cancellation signal to call **transport.cancel(true)** immediately instead of merely waiting for the deadline. That signal should be propagated explicitly across layers; completing a downstream future does not by itself prove that the entire processing chain has been cleaned up.

## 8. Practical Scenarios: Choosing the Right Mechanism

**A. The application calls a data-reading endpoint and needs to bound network activity.** Set an appropriate **HttpRequest.timeout**, and optionally **connectTimeout**. If the caller layer has an overall deadline, compute the remaining time and manage cancellation via the original handle.

**B. The UI needs to display cached data after 100 ms.** An observer stage using **completeOnTimeout(cacheValue, 100, MILLISECONDS)** can make sense when background cache refresh is **intentionally** allowed to continue. If you do not want the background request to keep running, you must have an explicit cancellation policy.

**C. The user clicks "Cancel".** If the request has not completed, call **cancel(true)** on the original HTTP future. Display a status like "cancellation requested" matching the true semantics; avoid claiming the server never received or has rolled back the transaction.

**D. Sending a POST to create an order, and the client times out.** The server may have already created the order before the client received the response. Retrying immediately can create duplicate records. Use an **idempotency key** or a status-polling mechanism per the service protocol; client-side timeouts/cancellation do not replace server-side consistency.

**E. The response may arrive early, but application processing takes a long time.** Request timeout does not cover parsing, transformation, or post-processing. Use an overall deadline for the pipeline, offload CPU-heavy work to an appropriate executor when needed, and design tasks with cancellation checkpoints if you want cooperative stopping.

## 9. Common Mistakes and How to Avoid Them

1. **Calling orTimeout directly on the original HTTP future and assuming the request stopped.** orTimeout only completes the future exceptionally. Manage the original HTTP handle and cancellation mechanism separately.
2. **Calling cancel(true) and assuming the server definitely did not process the request.** Cancellation is best effort. Operations with side effects must have idempotency or reconciliation.
3. **Using get(timeout) as an HTTP timeout.** get only limits how long the thread waits; set a request timeout or handle cancellation explicitly.
4. **Treating connectTimeout as the timeout for the entire request.** It only bounds establishing a new connection.
5. **Using completeOnTimeout to return a fake success.** Fallback values must be marked/understood as fallback data, not a verified HTTP response.
6. **Lumping all CompletionExceptions into TimeoutException.** Always unwrap the cause; it could be an I/O, DNS, TLS, processing bug, or cancellation.
7. **Issuing retries with the full timeout on every attempt.** Recompute the remaining budget from the overall deadline; prevent retries after expiration.
8. **Failing to clean up streaming bodies or downstream tasks.** With **ofInputStream()** and custom publishers/subscribers, future completion does not replace the responsibility to close or reject resource consumption properly.

## 10. Code Review Checklist

- Should the deadline bind the **HTTP request**, the **caller's wait time**, or the **entire business operation**?
- Are **connectTimeout** and **HttpRequest.timeout** configured for their distinct purposes?
- Is **orTimeout/completeOnTimeout** mutating the very future that other code needs to cancel?
- Is a handle retained to call **cancel(true)** on the in-flight request when the overall deadline or caller requests cancellation?
- After cancellation, does the code acknowledge that the server may still complete side effects?
- Are errors classified into **HttpTimeoutException**, **TimeoutException**, **CancellationException**, I/O errors, and HTTP status codes?
- Do all retries and backoffs use the **remaining time**, an attempt limit, and an appropriate idempotency mechanism?
- Are there tests for completing before the deadline, HTTP timeout, future-layer timeout, user cancellation, and races right around the deadline?

## Official References

- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): **sendAsync**, cancellable futures, and best-effort cancellation.
- [Java 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout.
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): **orTimeout**, **completeOnTimeout**, **cancel**.
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): **get(timeout)** and **cancel**.

**Core message:** **Stopping waiting** is an observation-layer decision; **HTTP expiration** is a transport-layer decision; **cancellation** is a best-effort request to reclaim work and resources. A sound design chooses each layer explicitly and measures all of them against the same business deadline when needed.
