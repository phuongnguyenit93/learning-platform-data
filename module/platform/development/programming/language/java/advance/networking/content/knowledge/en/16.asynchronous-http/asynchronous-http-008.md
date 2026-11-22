# Future Result Wait Deadline Differs from Canceling the Network Exchange

## Lesson Objectives

When calling `HttpClient.sendAsync(...)` in Java, the program receives a `CompletableFuture<HttpResponse<T>>`. If a thread waits for the result with `future.get(200, MILLISECONDS)` and encounters a `TimeoutException`, **the only certainty is that the waiting thread did not receive a result within 200 ms**. That does **not** mean the HTTP request was canceled, the TCP connection was closed, the server did not receive the data, or the business operation was not executed.

Similarly, calling `future.cancel(true)` on the future returned by Java's default HTTP client may **request cancellation of the HTTP exchange** and attempt to release resources, but **it does not guarantee that the server has not received the request or processed side effects**. By the time the client cancels, the server may have already committed the transaction and merely be generating the response.

This topic belongs to **asynchronous HTTP**, focusing on the boundaries between:

- **Caller's result wait deadline:** `Future.get(timeout)`.
- **Completion deadline of a CompletableFuture stage:** `orTimeout`, `completeOnTimeout`.
- **Deadline of the HTTP request itself:** `HttpRequest.Builder.timeout(Duration)`.
- **Deadline for establishing the TCP connection:** `HttpClient.Builder.connectTimeout(Duration)`.
- **Cancellation request action:** `CompletableFuture.cancel(true)` on the `HttpClient.sendAsync` future.
- **Actual business outcome on the server:** may **already be processed** even though the client observes a timeout/cancel/IOException.

After completing this lesson, you will be able to pinpoint which layer a timeout occurred at, whether an additional API is needed to cancel network activity, how to keep or close connections, why retrying after a timeout can cause duplicate side effects, and how to write Java 17+ code to observe all of these behaviors.

## 1. An HTTP Request Has Multiple Independent Lifecycles

Consider a client sending an order placement request to a server:

```text
Client thread                  Java HttpClient/TCP                     HTTP server
     │  sendAsync(request)            │                                  │
     ├───────────────────────────────►│                                  │
     │  CompletableFuture              ├──── POST /orders ───────────────►│
     │                                 │                                  │
     │  future.get(200ms)              │                          process/commit order
     │  ... 200ms elapsed ...          │                                  │
     │◄ TimeoutException              │                                  │
     │                                 │        response being prepared   │
     │                                 │◄──────── 201 Created ──────────┤
     │                                 │                                  │
     │  future.get(3s)                 │                                  │
     │◄ HttpResponse 201              │                                  │
```

In this diagram, **the 200 ms wait on the thread ends**, but **the HTTP exchange has not ended** at that point. The initial request can still complete normally and the future can receive a result afterward.

At a minimum, there are four states to distinguish:

| Component | Possible state when caller times out | Does it stop automatically because of `get(timeout)`? |
|---|---|---|
| Thread calling `get` | Wait deadline expired, receives `TimeoutException` | Yes: the **wait** operation ends |
| Original `CompletableFuture` | Still incomplete, or may have already completed in a race | **No** |
| HTTP request/network exchange | Sending body, waiting for headers/body, or already has a result at another layer | **No cancellation request from `get(timeout)`** |
| Server-side business operation | Not yet received, currently running, or already committed | **No** |

It must be emphasized: a timeout can occur **while the server has never received the request**, or it can occur **after the server has finished processing**. The client-side exception alone cannot determine which of the two cases happened.

### Do Not Confuse a "Future" with an "HTTP Exchange"

`Future`/`CompletableFuture` is a **handle for observing and coordinating an asynchronous result**. `HttpClient` is the component that performs the I/O operation. The two are related but not identical: changing how you wait on a future does not mean you are sending a "CANCEL" frame/packet to the server. In HTTP/1.1, there is no standard HTTP method to automatically "cancel an already-committed request" when the caller times out.

An exceptionally completed Future also **does not prove** that the server task rolled back. The request may have passed through a proxy, been processed by the server, and the response may have been lost or the client may no longer be receiving the result.

## 2. `Future.get(timeout)`: Only Limits the Thread's Wait Time

Signature:

```java
V value = future.get(longTimeout, TimeUnit.MILLISECONDS);
```

This is **illustrative syntax**, where `future` is a `Future<V>` created elsewhere.

According to Java 17 `Future.get(long, TimeUnit)`:

- If the Future completes normally within the deadline: returns the value.
- If the Future completes exceptionally: throws `ExecutionException`, with the specific cause in `getCause()`.
- If the Future has been canceled: may throw `CancellationException`.
- If the waiting thread is interrupted: throws `InterruptedException`, which does not by default mean the HTTP exchange was canceled.
- If there is no result before the deadline: throws `TimeoutException`.
- **No implicit cancel action** is specified solely because `get(timeout)` throws `TimeoutException`.

In particular, after a `TimeoutException`, you **can still keep the future reference** to observe a late result:

```java
// Illustrative snippet; future was obtained from HttpClient.sendAsync(...).
try {
    HttpResponse<String> response = future.get(200, TimeUnit.MILLISECONDS);
    handleResponse(response);
} catch (TimeoutException waitedTooLong) {
    recordCallerWaitExpired();
    // Do NOT automatically conclude that the future was canceled or the server did not process it.
    // The application can continue tracking this same future.
}
```

The snippet above is **not standalone**: `handleResponse`, `recordCallerWaitExpired`, and the variable `future` are components the application must define. In production, you must also handle interruption, `ExecutionException`, lifecycle state, and a separate request timeout.

### 2.1. Mistake: Assuming Timeout Means Cancel Was Called

Wrong:

```text
get(timeout) throws TimeoutException
    ⇒ HTTP client stopped the network    (FALSE)
    ⇒ server definitely did not commit    (FALSE)
    ⇒ sending a new POST cannot duplicate (FALSE)
```

Right:

```text
get(timeout) throws TimeoutException
    ⇒ caller's wait time has expired
    ⇒ must decide: continue observing, cancel intentionally,
       or mark the business outcome as UNKNOWN
```

If the real goal is "the caller may only wait 200 ms, but the system still wants to receive the result later," **do not call cancel** after the timeout. Keep the future in a registry, attach `whenComplete(...)`, or use another completion chain to handle the late response.

If you want to cancel the task, that is a separate decision, and you must understand that **client-side cancellation still does not undo server side effects**.

## 3. Java 17+: Proving `get(timeout)` Does Not Cancel the Request

This example creates an HTTP server on **loopback**, with no dependency on the Internet or an external server. The server receives the request, signals arrival via a `CountDownLatch`, and then **intentionally holds back the response** until the main thread allows it. The client calls `get(100ms)` while the server is not yet allowed to send. Thus we know the wait time will expire while the HTTP exchange is still alive.

**File `WaitTimeoutDoesNotCancelDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class WaitTimeoutDoesNotCancelDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch requestArrived = new CountDownLatch(1);
        CountDownLatch allowResponse = new CountDownLatch(1);
        ExecutorService serverWorker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(serverWorker);
        server.createContext("/slow", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                requestArrived.countDown();
                if (!allowResponse.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "DELIVERED".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) { out.write(body); }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/slow");
            HttpClient client = HttpClient.newHttpClient();
            CompletableFuture<HttpResponse<String>> request = client.sendAsync(
                    HttpRequest.newBuilder(uri).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            if (!requestArrived.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not receive request");
            }

            boolean timedOut = false;
            try {
                request.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }
            System.out.println("Timed wait expired: " + timedOut);
            System.out.println("Future still pending: " + !request.isDone());

            allowResponse.countDown();
            HttpResponse<String> result = request.get(3, TimeUnit.SECONDS);
            System.out.println("Later response: " + result.statusCode()
                    + " " + result.body());
        } finally {
            allowResponse.countDown();
            server.stop(0);
            serverWorker.shutdownNow();
        }
    }
}
```

Compile/run with **JDK 17 or later**:

```bash
javac --release 17 -encoding UTF-8 WaitTimeoutDoesNotCancelDemo.java
java WaitTimeoutDoesNotCancelDemo
```

**Verified stdout when run on localhost:**

```text
Timed wait expired: true
Future still pending: true
Later response: 200 DELIVERED
```

Notable points:

1. `HttpClient.sendAsync` immediately returns a `CompletableFuture<HttpResponse<String>>` while the network operation proceeds asynchronously.
2. `requestArrived.await` is a **test-specific latch**, not a special HTTP handshake. It ensures the server has seen the request before the client begins its timed wait.
3. The server is held at `allowResponse.await(...)`, so it cannot complete the response before the caller's `get(100ms)` expires.
4. `get(...)` throws `TimeoutException` and the code sets `timedOut=true`. No `future.cancel(...)` is called.
5. After the wait deadline expires, `!request.isDone()` is still true. It only reflects that **there is no final result yet** at the moment of measurement.
6. When main calls `allowResponse.countDown()`, the server returns `200 DELIVERED`; **the same original future** completes and `get(3s)` returns the response.
7. `finally` releases the latch and stops the server/executor to avoid hanging the test on an exception. Both the timeout and latch serve verification; in an overly slow environment or one blocking loopback, the test may fail with an error instead of printing all results.

**Conclusion:** a single `get(timeout)` does not make the HTTP exchange disappear. The caller can time out while the request still completes normally afterward.

## 4. `CompletableFuture.orTimeout` and `completeOnTimeout`: Stage Deadline, Not Server Rollback

Java 17 provides:

```java
CompletableFuture<T> stage = ...;
stage.orTimeout(300, TimeUnit.MILLISECONDS);
stage.completeOnTimeout(defaultValue, 300, TimeUnit.MILLISECONDS);
```

This is **illustrative syntax**, not a standalone program.

Both methods share an important point in their Javadoc: **they return `this` and can complete the very `CompletableFuture` on which they are called**.

- `orTimeout(timeout, unit)`: if the future **has not completed** before the deadline, it **completes exceptionally** with `TimeoutException`.
- `completeOnTimeout(value, timeout, unit)`: if the future has not completed, it **completes normally** with the given fallback value.
- If the future already completed before the deadline, the timeout does not overwrite that result.
- These methods **have no contract to "cancel the TCP exchange, close the socket, and roll back the server business transaction"**.

### Comparison with `get(timeout)`

| Situation | `get(100ms)` | `orTimeout(100ms)` | `completeOnTimeout(fallback,100ms)` |
|---|---|---|---|
| What does the timeout act on? | **The waiting caller thread** | **The state of the called CompletableFuture** | **The state of the called CompletableFuture** |
| Upon expiration | Throws `TimeoutException` from the `get` call | Future completes exceptionally with `TimeoutException` | Future completes normally with fallback |
| Is the original Future still pending? | Can still be pending | **No**, if `orTimeout` is called directly on the original future and the timeout wins | **No**, if called directly on the original future and the fallback wins |
| Guarantees the server did not run? | No | No | No |
| Automatically rolls back side effects? | No | No | No |
| Is it a dedicated API to cancel an HTTP network exchange? | No | No | No |

**Very error-prone:** writing

```java
// ILLUSTRATIVE: directly mutates the state of the future returned by sendAsync.
CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());
transport.orTimeout(200, TimeUnit.MILLISECONDS);
```

Here `transport.orTimeout` **modifies `transport` itself**. If the deadline wins, downstream processing steps may see an exceptional Future instead of the real response arriving late. That does not allow concluding that the network request was not sent, or that server side effects did not occur.

If you need a deadline **only for a presentation/UI layer** while still tracking the original HTTP Future, place the timeout on **a separate derived stage** such as `transport.thenApply(...)` or `transport.copy()`:

```java
// ILLUSTRATIVE: only the derived stage has its own deadline.
CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> uiView = transport
        .thenApply(HttpResponse::body)
        .orTimeout(200, TimeUnit.MILLISECONDS);
// If uiView times out, transport can still complete afterward.
```

This illustrative snippet requires `client`, `request`, and imports defined by the application.

### `completeOnTimeout` Does Not Mean Business Success

A misuse is creating a `fake HttpResponse 200` or returning "Payment successful" when the deadline expires. `completeOnTimeout` produces a **fallback of your choosing**, not server confirmation. If you want the UI to have a provisional result, choose an explicit state like `PENDING` / `UNKNOWN`, and continue tracking the real request.

A safer result type:

```java
// Illustrative idea, not a standalone class.
record ViewResult(String state, String detail) {}

CompletableFuture<ViewResult> view = transport
        .thenApply(r -> new ViewResult("CONFIRMED",
                "HTTP " + r.statusCode()))
        .completeOnTimeout(new ViewResult("UNKNOWN", "Still processing"),
                200, TimeUnit.MILLISECONDS);
```

Even a `CONFIRMED` HTTP status only confirms the response the application received; it does not automatically guarantee an external transaction has settled unless the business contract says so.

## 5. Java 17+: Timeout on Derived Stage, Original HTTP Still Runs

The following example creates a loopback HTTP server whose response is held by a latch. The client uses `sendAsync` and creates **a derived future** `display` via `network.thenApply(HttpResponse::body)`. Only `display` is given `orTimeout(100ms)`. When the deadline expires, `display` is exceptional while `network` is not finished. Releasing the latch lets `network` receive the response normally.

**File `TimeoutStageIsolationDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class TimeoutStageIsolationDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/delay", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                started.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "SERVER_OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) { out.write(body); }
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/delay");
            CompletableFuture<HttpResponse<String>> network =
                    HttpClient.newHttpClient().sendAsync(
                            HttpRequest.newBuilder(uri).GET().build(),
                            HttpResponse.BodyHandlers.ofString());

            // orTimeout modifies THIS derived future, not network.
            CompletableFuture<String> display =
                    network.thenApply(HttpResponse::body);
            display.orTimeout(100, TimeUnit.MILLISECONDS);

            if (!started.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No request at server");
            }
            boolean displayTimedOut = false;
            try {
                display.join();
            } catch (CompletionException error) {
                displayTimedOut = error.getCause() instanceof TimeoutException;
            }
            System.out.println("Derived view timed out: " + displayTimedOut);
            System.out.println("Original exchange pending: " + !network.isDone());

            release.countDown();
            HttpResponse<String> result = network.get(3, TimeUnit.SECONDS);
            System.out.println("Original result: "
                    + result.statusCode() + " " + result.body());
        } finally {
            release.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 TimeoutStageIsolationDemo.java
java TimeoutStageIsolationDemo
```

**Verified stdout:**

```text
Derived view timed out: true
Original exchange pending: true
Original result: 200 SERVER_OK
```

**Careful interpretation:**

- `network` is the original future from `HttpClient`; `display` is a derived future, created with `thenApply`. Java completes `display` with the body result if the source completes soon enough.
- `display.orTimeout(100ms)` modifies only the derived future. When the timeout wins, `display.join()` throws `CompletionException` whose `getCause()` is `TimeoutException`.
- Because the server is gated, the HTTP response has not arrived; `!network.isDone()` remains true. `network` is not automatically completed exceptionally just because the derived stage timed out.
- After release, `network.get(...)` receives `200 SERVER_OK`. The derived view is already terminally exceptional and **does not automatically change its result** when the original future completes.
- This result does not mean the HTTP client always keeps the exchange alive when any derived stage times out/cancels. If you genuinely want to stop network activity, you need an **explicit cancellation request** and corresponding lifecycle tracking.

Use this pattern for UIs, RPC gateways, or request coordinators when the viewer's deadline **differs** from the deadline of the actual HTTP task. However, there must be resource bounds for still-running requests; do not allow every UI-timed-out request to live forever.

## 6. `HttpRequest.Builder.timeout`: Timeout Belonging to the HTTP Request

Java's `HttpRequest.Builder.timeout(Duration)` creates a **timeout for the HTTP request**. If no response is received within the configured duration, `HttpClient.send(...)` can throw `HttpTimeoutException`; `HttpClient.sendAsync(...)` can complete exceptionally with `HttpTimeoutException`.

```java
// Illustrative snippet; URI and imports provided by the application.
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(java.time.Duration.ofMillis(500))
        .POST(HttpRequest.BodyPublishers.ofString("ACTION"))
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
```

Unlike `get(500ms)`:

- This is a **request deadline condition inside the HTTP client**, not merely the caller waiting at most 500 ms.
- When the request deadline triggers, the future can complete exceptionally with `HttpTimeoutException` (a subclass of `IOException`).
- Do not call this a **server-side execution deadline**. The server does not implicitly know or obey the client-side `Duration`.
- The implementation may attempt to release network resources after a request timeout, but there is no guarantee that the remote server rolls back.
- The timing of the response/body reading and `BodyHandler` overloads affect how completion is observed. With `BodyHandlers.ofInputStream()`, the response future can complete when the stream is available before the application finishes reading the body; the app remains responsible for consuming/closing the stream.

### 6.1. Connect Timeout Differs from Request Timeout

`HttpClient.Builder.connectTimeout(Duration)` sets a limit for **establishing the connection**. It does not replace `HttpRequest.Builder.timeout` and does not measure the server's total business processing time.

| Configuration/call | Applies to | Notable exception/outcome | What must not be inferred |
|---|---|---|---|
| `client.sendAsync(...)` | Async HTTP send/receive | Future with response or exceptional | `sendAsync` itself sets no caller deadline |
| `future.get(200ms)` | **Thread wait time** | `TimeoutException` | No implicit network cancel |
| `future.orTimeout(200ms)` | **State of the called future itself** | Exceptional `TimeoutException` | Does not itself prove the HTTP exchange was canceled |
| `future.completeOnTimeout(...)` | **State of the called future itself** | Fallback value | Fallback is not a server response |
| `request.timeout(200ms)` | **HTTP request lifecycle** | `HttpTimeoutException` | Does not cancel the server business operation |
| `client.connectTimeout(200ms)` | **Connection establishment** | `HttpConnectTimeoutException` on connect timeout | Does not measure server response processing |
| `future.cancel(true)` | **Request to cancel future/exchange** | `CancellationException` or related error depending on timing/implementation | Does not guarantee the server stopped, no rollback |

**Note on `get(timeout)` vs. `request.timeout`:** a program can use both—for example, a 5-second request timeout while the caller waits only 200 ms. When the caller receives `TimeoutException` after 200 ms, the HTTP request can still continue up to the 5-second policy. Conversely, if the HTTP request timeout occurs first, the caller may receive `ExecutionException(cause=HttpTimeoutException)` when using `get(...)`.

### 6.2. Classifying Errors Properly via Future

`HttpClient.sendAsync(...)` returns `CompletableFuture<HttpResponse<T>>`. On request timeout:

```java
// Illustrative snippet: future is already obtained.
try {
    HttpResponse<String> result = future.get();
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    if (cause instanceof HttpTimeoutException) {
        // HTTP request timeout per configuration.
    } else {
        // Other HTTP/network/handler error.
    }
}
```

If using `future.join()`, exceptions are typically surfaced via `CompletionException` with `getCause()`, or `CancellationException` when the future is canceled. Do not catch only `TimeoutException` from `get(timeout)` expecting to catch `HttpTimeoutException`: they are **two different exception types** at two different layers.

## 7. Java 17+: HTTP Request Timeout While the Server Already Accepted the Work

The third example has the server **record a business operation** right after reading the body, then hold the response until the client times out. The request is configured with `timeout(Duration.ofMillis(200))`. The program verifies that the client sees `HttpTimeoutException` while the server counter is already `1`.

**File `HttpRequestTimeoutVsCommitDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpRequestTimeoutVsCommitDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger accepted = new AtomicInteger();
        CountDownLatch processed = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/work", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                accepted.incrementAndGet();
                processed.countDown();
                if (!release.await(5, TimeUnit.SECONDS)) return;
                try {
                    exchange.sendResponseHeaders(204, -1);
                } catch (IOException afterClientLeft) {
                    // Client may already have ended its exchange.
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/work");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(200))
                    .POST(HttpRequest.BodyPublishers.ofString("ORDER"))
                    .build();
            CompletableFuture<HttpResponse<Void>> future =
                    HttpClient.newHttpClient().sendAsync(
                            request, HttpResponse.BodyHandlers.discarding());
            if (!processed.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server missed request");
            }

            boolean httpTimeout = false;
            try {
                future.join();
            } catch (CompletionException failed) {
                httpTimeout = failed.getCause() instanceof HttpTimeoutException;
            }
            System.out.println("HTTP request timed out: " + httpTimeout);
            System.out.println("Server accepted work: " + accepted.get());
        } finally {
            release.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 HttpRequestTimeoutVsCommitDemo.java
java HttpRequestTimeoutVsCommitDemo
```

**Verified compiled/executed stdout:**

```text
HTTP request timed out: true
Server accepted work: 1
```

**Explanation:**

1. The server reads the `ORDER` body first, increments `accepted` to 1, and signals via `processed.countDown()`.
2. The server does not send a response yet because it is waiting on the `release` latch. Even though the request arrived quickly, the response is intentionally held longer than 200 ms.
3. The deadline from `HttpRequest.Builder.timeout` triggers, so the Future completes exceptionally with cause `HttpTimeoutException`, not the `TimeoutException` of `future.get(timeout)`.
4. The server counter remains 1. **A client-side timeout event cannot automatically reverse an increment that already occurred**.
5. In the demo, the counter represents an illustrative in-memory "side effect," not a durable transaction. With a real database, rollback only happens if the server designs corresponding transaction/cancellation handling.
6. `finally` opens the latch and shuts down the server and executor. The server may fail to send the response after the client ended the exchange; that is a network error after the side effect, not proof that the side effect did not happen.

You should not build automatic retries for an "order creation" `POST` based solely on `HttpTimeoutException` occurring. The actual state is **no success confirmation from the server**, which does not equate to definite failure.

## 8. `cancel(true)` on `sendAsync`: Cancellation Is a Client-Side Attempt

The Java 17 Javadoc for `HttpClient.sendAsync(...)` specifically notes: the `CompletableFuture` returned by the default `HttpClient` supports cancellation. When calling `cancel(true)` on an **incomplete** future, the HTTP client **attempts to cancel the HTTP exchange** to release resources early; however, **there is no guarantee as to exactly when cancellation takes effect**, and the request may have already been sent to the server or processed on another thread.

At the protocol level:

- With **HTTP/1.1**, a cancel attempt may cause the **TCP connection to be closed abruptly**. The connection in use may no longer be suitable for reuse.
- With **HTTP/2**, a cancel attempt may send a stream reset signal; some situations may affect the connection. Resetting a stream **is not** a server-side transaction rollback.
- If the request or Future has already completed before that, cancellation may not change the finalized result.
- Callbacks/continuations may observe `CancellationException`, `CompletionException`, `IOException`, or another result depending on wrapper layers, timing, and HTTP library; **do not hardcode a fixed list of outcomes** as a proxy for the remote outcome.
- Calling `cancel(true)` does not know how to roll back a database, refund money, delete an order, or undo an HTTP request that the server already committed.

### 8.1. Future State and Server Side Effects Are Independent

`CompletableFuture.isDone()` only reports that the Future has completed (normally, exceptionally, or canceled). `isCancelled()` speaks about **the future's state**, not the server-side outcome. In a race between cancel and completion, you must check the **final state**, rather than relying on the fact that the client **attempted** to cancel.

Even when `cancel(true)` returns true, that is not a server acknowledgment. The `Future.cancel` documentation describes the return value as the result of the task cancellation request per contract, **not** proof that "the server did not process it."

Do not write:

```java
// ANTI-PATTERN: Do not infer business outcome from cancel.
boolean requested = future.cancel(true);
if (requested) {
    markOrderAsNeverCreated(); // Wrong: the server may have already created the order.
}
```

This is an illustrative anti-pattern; `markOrderAsNeverCreated` has no standalone definition.

### 8.2. Is `cancel(false)` Enough?

For `Future` in general, `cancel(boolean mayInterruptIfRunning)` is a **request** to cancel the task, and the boolean relates to whether to attempt interrupting a running thread. However, HTTP client implementations have their own semantics; **do not treat `cancel(false)` and `cancel(true)` as two HTTP protocol commands that are guaranteed identical or guaranteed different according to a fixed mapping**.

For Java 17's default `HttpClient`, the documentation specifically describes the attempt to cancel the HTTP exchange when calling `cancel(true)`. If the goal is to stop I/O, consult the API/documentation of the running implementation and monitor the resource lifecycle; do not deduce from the generic `CompletableFuture` API that the network connection is definitely closed.

### 8.3. Canceling a Derived Stage vs. Canceling the Original HTTP Exchange

If a UI has:

```java
CompletableFuture<HttpResponse<String>> network = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());
CompletableFuture<String> uiStage = network.thenApply(HttpResponse::body);
uiStage.cancel(true);
```

Then the meaning of cancellation can depend on **the implementation and the relationship between the original future and the derived stage**. The Java HttpClient Javadoc states that futures derived from a cancelable client future also support cancellation. Do not assume "canceling only the UI stage definitely does not affect the network," nor assume "the server has definitely stopped."

If you want a UI deadline **never to act as a network stop button**, separate a **view stage** using `orTimeout` on its own stage and **do not call cancel** on the HTTP future or derived future. Even then, you must manage still-pending requests and release resources according to a longer deadline.

## 9. Java 17+: Future Canceled, Yet Server-Side Effect Still Happened

The final example simulates a `POST /commit` operation. The server reads the request, increments a counter, signals completion via a latch, and **does not yet send a response**. The client waits until the server has definitely applied the side effect, and only then calls `future.cancel(true)`.

The intentional result: cancellation is requested on the client side, but the server-side counter is already 1. No HTTP library can "turn back time" on this counter increment.

**File `CancelDoesNotUndoWorkDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelDoesNotUndoWorkDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger committed = new AtomicInteger();
        CountDownLatch businessApplied = new CountDownLatch(1);
        CountDownLatch allowResponse = new CountDownLatch(1);
        ExecutorService worker = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(worker);
        server.createContext("/commit", exchange -> {
            try (exchange) {
                exchange.getRequestBody().readAllBytes();
                committed.incrementAndGet();
                businessApplied.countDown();
                if (!allowResponse.await(5, TimeUnit.SECONDS)) return;
                byte[] body = "DONE".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, body.length);
                    try (var out = exchange.getResponseBody()) {
                        out.write(body);
                    }
                } catch (IOException clientGone) {
                    // Cancellation might have closed the connection.
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        try {
            server.start();
            URI uri = URI.create("http://localhost:"
                    + server.getAddress().getPort() + "/commit");
            CompletableFuture<HttpResponse<String>> future =
                    HttpClient.newHttpClient().sendAsync(
                            HttpRequest.newBuilder(uri)
                                    .POST(HttpRequest.BodyPublishers.ofString("PAY"))
                                    .build(),
                            HttpResponse.BodyHandlers.ofString());
            if (!businessApplied.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not apply work");
            }
            boolean canceled = future.cancel(true);
            System.out.println("Future cancellation accepted: " + canceled);
            System.out.println("Server side effect count: " + committed.get());
        } finally {
            allowResponse.countDown();
            server.stop(0);
            worker.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CancelDoesNotUndoWorkDemo.java
java CancelDoesNotUndoWorkDemo
```

**Observed stdout on JDK 24 with `--release 17`:**

```text
Future cancellation accepted: true
Server side effect count: 1
```

**The result does not promise every environment will always return the same boolean for `cancel`**, because timing and implementation can differ. What is fixed by the test is that **the server incremented the counter before the client called cancel**. `CountDownLatch` enforces this ordering; if the request does not reach the server, the program throws an error instead of producing false evidence.

Key takeaways:

- The HTTP client **can** cancel the exchange and close the TCP connection; in the demo, the server may even hit an `IOException` when sending the response after the client has left.
- An incremented counter **does not automatically reset to zero** just because the client-side Future was canceled.
- `cancel(true)` has no contract to "delete a business command already committed by the server."
- Do not use `isCancelled` as a measure of "the server stopped." It is a future property, not a server confirmation.
- Business processing in a real application needs transactions, idempotency keys, status queries, or a protocol cancellation with its own confirmation; do not use a client-side flag to measure rollback success.

## 10. A Timeout Can Occur in Many Places: Which Exception to Read?

When real code reports a timeout, answer: **which component created the deadline?** The following exceptions are not interchangeable.

| Situation | Where observed | Typical exception/reason | Was the network canceled? |
|---|---|---|---|
| `future.get(100, MILLISECONDS)` expires | Waiting thread | `TimeoutException` directly | **Not by the get operation** |
| `future.orTimeout(100, MILLISECONDS)` expires | Called CompletableFuture | `TimeoutException` as cause of exceptional completion | No guarantee |
| `completeOnTimeout(fallback)` wins | Called CompletableFuture | Completes normally with fallback | No guarantee |
| `HttpRequest.Builder.timeout` expires | HTTP client | `HttpTimeoutException` in exceptional result | Client may end exchange; server may still process |
| `HttpClient.Builder.connectTimeout` expires | TCP/TLS connection | `HttpConnectTimeoutException` | Cannot infer what proxies/servers did or did not do without context |
| `future.cancel(true)` | Future/HTTP client | Future cancellation/error depending on timing | **Attempt**, no guarantee of timing/remote rollback |
| HTTP server timeout | Server/request handler layer | Server-defined `408`, `503`, or custom error depending on situation | Client-side future does not control everything |
| Application deadline in UI | Presenter/RPC gateway | `UNKNOWN`, `DEADLINE_EXCEEDED` per app contract | May only stop waiting while network still runs |

**Specifically:** `HttpTimeoutException` is a subclass of `IOException`. `TimeoutException` from `java.util.concurrent` is **not** a subclass of it. Handle the right layer so you do not retry for the wrong reason.

### `join()` and `get()` Wrap Errors Differently

- `future.get()` or `get(timeout)`: errors from an exceptional Future are typically wrapped in `ExecutionException`.
- `future.join()`: errors are typically wrapped in `CompletionException`.
- If the Future was actually canceled, `get/join` may throw `CancellationException`.
- Do not rely solely on parsing **String exception messages**, as they easily depend on locale and implementation; use `instanceof` and `getCause()`.

Illustrative example:

```java
// Illustrative snippet, future obtained from sendAsync.
try {
    var response = future.get(500, TimeUnit.MILLISECONDS);
    process(response);
} catch (TimeoutException waiting) {
    log("Caller ran out of waiting time");
} catch (ExecutionException completedWithError) {
    Throwable cause = completedWithError.getCause();
    if (cause instanceof HttpTimeoutException) {
        log("HTTP request timeout");
    } else {
        log("HTTP failed: " + cause);
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    log("Caller thread interrupted");
}
```

This illustrative snippet is not standalone because `process`, `log`, and `future` are app components. When a thread is interrupted, **restore the interrupt flag** if required by the framework, and decide on network/cancellation separately.

## 11. Late Results and Request State Management

A system must distinguish two concepts:

- **Caller deadline:** the waiter no longer wants to wait.
- **Exchange/business lifecycle:** the request may still exist, receive a result, and need cleanup.

### A Practical State Machine

```text
LogicalOperation
  CREATED
      │ sendAsync(...)
      ▼
  IN_FLIGHT ───────────────────────────────► COMPLETED
      │                                       (HTTP response + business contract)
      │
      ├─ callerWaitDeadline → WAIT_EXPIRED
      │                           │
      │                           ├─ late response → COMPLETED
      │                           └─ optional cancel request → CANCEL_REQUESTED
      │                                                   │
      │                                 ┌─────────────────┴──────────────┐
      │                                 ▼                                ▼
      │                           CLIENT_STOPPED                  LATE_COMPLETED
      │                           (remote outcome UNKNOWN)       (actual response)
      │
      └─ request timeout → CLIENT_TIMED_OUT
                               (remote outcome UNKNOWN)
```

An application-level operation can be observed through multiple futures: network future, UI future, audit future. **Do not treat completion of the UI future as proof that the network stopped** if the UI timeout was only on a derived stage.

### Cleanup Boundary Guidelines

1. If the caller's `get(timeout)` expires but the system still wants the result, keep `networkFuture` in a registry with a longer deadline and use `whenComplete` to record it later.
2. If the caller times out and the request is no longer valuable, consider `cancel(true)`, while still recording business state `UNKNOWN` if an authoritative response is missing.
3. If choosing not to cancel, you must bound the number of pending requests, connection pool, body memory, and registry TTL; otherwise, many UI timeouts can cause resource leaks.
4. If canceled, do not assume callbacks will never run; design terminal handling to be idempotent, clean up based on the actual outcome, and do not record side effects as rolled back without server confirmation.
5. Do not update the same application record twice when the Future callback, timeout coordinator, and retry scheduler race. Use a single terminal transition with synchronization/atomic compare-and-set.

### Can You "Retrieve" the Response After `get(timeout)`?

Yes, if the original future is still active and you still hold a reference; the first example in this lesson proved that. However, if you called `orTimeout` directly on **that same** Future and the timeout won, that Future is terminally exceptional; a late response cannot "turn" a terminal future into successful, even if the underlying network ran.

If you need both a **UI timeout** and **late results**, do not mutate the original future: use a separate derived stage for the UI and keep the original HTTP future for audit/reconciliation.

## 12. Retrying After a Timeout: A Bigger Problem Than I/O

Placing orders, making payments, transferring funds, writing data, or creating jobs are operations **with side effects**. The client may fail to receive a response because of:

- Exceeding the `get(timeout)` wait.
- Request timeout in `HttpClient`.
- Connection cut when the client cancels.
- TCP/TLS/proxy error when the server has or has not processed it.
- Response already generated by the server but lost in transit.

In these cases, **you have no right to infer "it definitely did not run."** Retrying the request can lead to executing the intent again.

```text
POST /charge, Idempotency-Key: pay-001
  │
  ├── Server commits payment
  │
  └── Response is lost / client deadline expires
          │
          └── Client retries
                POST /charge, Idempotency-Key: pay-001
                    │
                    └── Server finds the stored result and responds again
                        instead of charging another time
```

This is a **recommended business pattern**, not an automatic HTTP guarantee of exactly-once delivery. The `Idempotency-Key` header only works when **the API server publishes and explicitly implements the contract**. The server must scope the key by principal/operation, compare the payload fingerprint, register the request atomically, persist the result with a transaction or sufficiently durable mechanism, and have a retention/replay policy.

### Retry Classification

| Situation | Safe to retry immediately? | Notes |
|---|---|---|
| `GET` safe and idempotent by semantics | Possibly, within policy limits | Still need to control overload, cache, auth, backend |
| `PUT` idempotent by semantics | Possibly when server honors contract | Secondary effects like audit/metrics may repeat; understand state |
| `POST` creating order without idempotency key | **Should not auto-retry** on timeout alone | Risk of creating duplicates |
| `POST` with deduplication key/contract implemented by server | Possibly per API policy | Use **the same key** for the same intent, cap attempts |
| `get(timeout)` only expired the wait | Prefer observing original future first | Network future may complete afterward |
| Request timeout before response | Outcome unknown | Query status by ID if available; retry with dedup |
| `cancel(true)` | Outcome unknown | Do not infer rollback |
| Server app confirms cancellation before commit | Depends on dedicated protocol | Only treat as uncommitted if confirmation is reliable |

Do not auto-retry indefinitely when many requests time out: an already slow server may become further overloaded. Use attempt limits, an overall operation deadline, exponential backoff, and jitter; have circuit breaker/queue mechanisms for large systems.

### Network Cancellation Is Not Business Cancellation

To actually stop a running server job, you need a **protocol cancellation with a task identifier**, such as `POST /jobs/{id}/cancel` and a returned status. The server might be unable to cancel because the job already finished/committed; the client must accept **already completed** or **cancel rejected** outcomes. Simply closing TCP or resetting an HTTP/2 stream does not carry full business semantics.

## 13. Combining Timeout and Cancellation in `sendAsync`

An API can support both a caller deadline and an exchange cancellation request. The key is **not to confuse the two behaviors**.

### 13.1. Limiting Only UI Wait Time

```java
// Java pseudocode; not a standalone runnable class.
CompletableFuture<HttpResponse<String>> network =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> ui = network
        .thenApply(resp -> resp.statusCode() + " " + resp.body())
        .completeOnTimeout("PENDING: check status later",
                200, TimeUnit.MILLISECONDS);

network.whenComplete((resp, error) -> {
    // Record actual final state, do not trigger non-idempotent side effects.
    storeOutcome(resp, error);
});
```

This is pseudocode with `storeOutcome` undefined. `ui` can complete with a pending message while `network` still needs resource/timeout management and reconciliation.

### 13.2. Intentionally Requesting to Stop the Network Exchange

```java
// Pseudocode: request is still worth canceling on the client side.
CompletableFuture<HttpResponse<String>> network =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

if (userExplicitlyAbandonedRequest()) {
    boolean cancelRequested = network.cancel(true);
    recordClientCancellationAttempt(cancelRequested);
    markRemoteOutcomeUnknown();
}
```

This is pseudocode, not a standalone program because the condition/state-recording functions are undefined. **Do not** call `markBusinessRolledBack()` solely because `cancelRequested` is true.

### 13.3. Preventing Duplicate Callback Processing

When a timeout coordinator, completion callback, and cancel path run concurrently, you must ensure the final state for a **logical request** is recorded only once. You can use:

```text
PENDING -> SUCCEEDED
        -> FAILED
        -> TIMED_OUT_UNKNOWN
        -> CLIENT_CANCELLED_UNKNOWN

Only the transition that wins compare-and-set is allowed to notify the user.
A late response is recorded for audit/reconciliation, not silently creating 2 transactions.
```

If the status is already `TIMED_OUT_UNKNOWN` and a late `201 Created` response arrives, the application can append an adjustment/reconciliation event for business state per contract; it must not erase the timeout trace without inspection.

## 14. Common Design Mistakes

| Mistake | Why it is wrong | Right approach |
|---|---|---|
| `get(200ms)` times out → resend POST immediately | The first HTTP request may still be running | Keep/observe original future; use an idempotency contract |
| `get(timeout)` times out → assume `future.isDone()==true` | `get` timeout does not complete the future | Check the actual future; do not guess |
| `orTimeout` directly on transport future while wanting late response | `orTimeout` makes that future terminally exceptional | Use a separate derived stage if you need to keep the transport future |
| `completeOnTimeout(success)` to "hide the spinner" | Creates **false success** | Return PENDING/UNKNOWN and reconcile |
| Call `cancel(true)` and report "server rolled back" | Cancel is not a remote transaction rollback | Require confirmation via protocol/business state |
| Catch only `TimeoutException` on `get` | Misses wrapped `HttpTimeoutException` | Handle `ExecutionException.getCause()` or `CompletionException` |
| Set `connectTimeout` and treat it as total request deadline | Only governs the connect phase | Add appropriate request timeout and business deadline |
| Assume `sendAsync` always finishes reading the whole streaming body | `BodyHandler` may return a stream for caller to handle | Close/consume stream per lifecycle |
| Unbounded pending futures after UI timeouts | Memory/connection resource leak | TTL, cancellation policy, semaphores/counters |
| Fail to track late results | "Unknown" is never reconciled | `whenComplete` + request ID + server status |
| Retry with a new request ID after uncertain outcome | Server may execute twice | Use a stable logical key and dedup |
| Arbitrarily close HTTP/1.1 connection shared by other tasks | Canceling exchange can affect reuse/resources | Respect `HttpClient` ownership and cancel Javadoc |
| Run blocking `future.get()` inside a completion callback thread | Can cause starvation or deadlock | Use non-blocking `thenCompose`/`thenApply`/`whenComplete` |
| Fail to restore interrupt when catching `InterruptedException` | Loses thread stop signal | `Thread.currentThread().interrupt()` per policy |
| Assume canceling future = no more callbacks | Completion/cancellation handlers may still run | Design idempotent terminal handling and cleanup |

### A Warning About "Interrupting Threads"

`cancel(true)` does not mean "the server worker thread is interrupted." The boolean `mayInterruptIfRunning` belongs to the Future contract on the client machine; it **has no automatic path to transmit a Java thread interrupt over TCP** to another JVM/server. If the backend supports cooperative cancellation, it must implement a protocol and server-side code.

With HTTP/2, a stream reset may signal termination at the transport layer, yet still does not prove business processing did not run. Do not treat `RST_STREAM` as proof of rollback.

## 15. Practical Diagnostics: What to Log for Accurate Conclusions?

A good observability setup should log **separated by layer**:

```text
timestamp | logicalRequestId | attemptId | method | uriOrigin
          | callerWaitDeadline | requestTimeout | connectTimeout
          | futureState | cancelRequested | requestBytesSent
          | responseStatus | responseCompleted | errorCauseClass
          | serverBusinessId | serverCommitState | reconciliationOutcome
```

Do not log credentials, tokens, or sensitive payloads. `requestBytesSent` on the client can be hard to measure accurately: the network stack/HTTP client may buffer, so it must not be interpreted as bytes definitely received by the server.

When debugging an incident:

1. **Identify the root exception**: direct `TimeoutException` from `get(timeout)` or `HttpTimeoutException` in an exceptional future?
2. **Determine which deadline fired first**: caller deadline, request timeout, connect timeout, UI stage timeout, proxy/server timeout.
3. **Check whether cancel was called**: when, on the original future or a derived stage, what `cancel(true)` returned; do not assume the network stopped.
4. **Correlate request IDs** on both client and server. Did the server receive the request, start processing, commit, or send a response?
5. **Check for late responses**: was the original future still tracked, or was it completed exceptionally by `orTimeout`?
6. **Check the retry scheduler**: did it create a new request before knowing the outcome? Did it use the same idempotency key?
7. **Inspect connection behavior**: was the HTTP/1.1 TCP connection closed on cancel or closed by the server; an HTTP/2 stream reset does not mean rollback.
8. **Check resources**: pending futures, unclosed `ByteBuffer`/streams, request queues, number of outstanding exchanges, and retry storms.
9. **Record conclusions with exact certainty levels**: "caller wait expired," "HTTP request timed out," "client requested cancellation," and "server committed" are four distinct statements and each requires its own evidence.

### Symptom Matrix

| Symptom | Direct conclusion | Must not be auto-concluded |
|---|---|---|
| Caller receives `TimeoutException` from `get` | Wait time expired | HTTP request was canceled |
| `orTimeout` makes stage exceptional | Stage deadline expired | Network/exchange definitely interrupted |
| `HttpTimeoutException` | HTTP request exceeded client-configured deadline | Server definitely did not commit |
| `cancel(true)` returns true | Client requested cancel per API | Remote did not receive or rolled back |
| HTTP/1.1 FIN/RST | Connection closed/reset at TCP layer | Backend transaction did not happen |
| Server logs `COMMIT id=...` | Server recorded commit per logging contract | Client definitely saw the response |
| Client receives `201 Created` | Client has application response | All downstream side effects finished unless contract states so |
| Retry uses a different key | May be a new intent on the server | "Just resending the same request" |
| Response arrives after UI timeout | Network kept running after UI deadline | UI state updates accurately without a handler |

## 16. Thought Exercises and Review Questions

**Q1.** Call `HttpClient.sendAsync`, followed by `future.get(100, MILLISECONDS)`, and receive `TimeoutException`. Has the Future been canceled?  
**Answer:** Not by `get`. The Future may still be pending; the caller simply ran out of wait time. You must observe the future separately.

**Q2.** When the caller times out, the server has already committed the transaction but the response has not arrived. Is it safe for the client to send a second POST with a new request ID?  
**Answer:** Not safe by default. It can create duplicate side effects; you need to query status or retry under an idempotency contract with a stable ID.

**Q3.** Does `CompletableFuture.orTimeout` return a new future?  
**Answer:** No. Per Javadoc, it returns **this same future** and completes exceptionally if the deadline wins. If you want a separate stage, create a derived stage and put the timeout on it.

**Q4.** `completeOnTimeout("OK")` returns the string OK after 200 ms. Does that mean the server returned 200?  
**Answer:** No. That is a caller-defined fallback, not an HTTP response.

**Q5.** What is the difference between `TimeoutException` and `HttpTimeoutException`?  
**Answer:** `TimeoutException` from `get(timeout)` is a wait timeout at the concurrency layer; `HttpTimeoutException` is an HTTP request deadline error, a subclass of `IOException`, typically wrapped in an exceptional future.

**Q6.** Does `HttpClient.Builder.connectTimeout` replace `HttpRequest.Builder.timeout`?  
**Answer:** No. Connect timeout governs connection establishment; request timeout applies to the request lifecycle.

**Q7.** `cancel(true)` for HTTP/1.1 can close the connection. Does that guarantee the server stopped processing?  
**Answer:** No. The server may have already received/committed before the connection closed; you need a protocol cancellation with confirmation if you want to know the server stopped.

**Q8.** In HTTP/2, is resetting a stream equivalent to a database rollback?  
**Answer:** No. Resetting a stream is a transport protocol action; the business operation is an independent state on the server.

**Q9.** `Future.get()` throws `ExecutionException(cause=HttpTimeoutException)`. Is it true that the caller's `get(timeout)` expired?  
**Answer:** Not necessarily. Here, the HTTP request itself completed exceptionally; the caller may still have had wait time remaining.

**Q10.** `sendAsync` with `BodyHandlers.ofInputStream` returns a response with an `InputStream`. Can you ignore the stream without cleanup because the future is done?  
**Answer:** No. The caller must consume or close the stream per contract; Future completion does not mean the body stream is automatically freed for all handler types.

**Q11.** The UI only wants to wait 200 ms, but the backend may take 3 seconds. What design preserves late results?  
**Answer:** Put the timeout on a derived UI stage, keep the original HTTP Future in a registry with its own resource deadline, and handle late responses via `whenComplete`.

**Q12.** `cancel(true)` returns false. Can you conclude the server has not received anything?  
**Answer:** No. The Future may have already completed or cancellation may no longer be possible; the boolean return value does not prove remote state.

**Q13.** The user clicks "Cancel" after an order has already been created. Does closing the connection delete the order?  
**Answer:** No. You need a business API to cancel the order and inspect its result; sometimes the order is already in a non-cancelable state.

**Q14.** Why can putting `orTimeout` on the network future itself forfeit the ability to read a late response through that future?  
**Answer:** When the timeout wins, that future is terminally exceptional; it does not turn back into successful when the response arrives. If you want to keep the real result, do not put a completing timeout directly on the original future.

**Q15.** The thread waiting on a Future gets `InterruptedException`. Does that automatically send a cancel to the HTTP exchange?  
**Answer:** `Future.get` being interrupted does not automatically mean the HTTP exchange was canceled. You must decide on cancellation separately and restore the interrupt flag per application policy.

**Q16.** To avoid double charging when retrying due to an HTTP timeout, what elements are needed on the server side?  
**Answer:** An API contract with a stable key/ID, atomic dedup, payload fingerprint, business transaction/retention, and status querying when the outcome is unknown.

**Q17.** When `cancel` and response completion happen almost simultaneously, should the UI determine side effects from `future.isCancelled` or the server transaction status?  
**Answer:** The server-confirmed transaction status is the source of truth for the business outcome; `isCancelled` is a client-side future property.

**Q18.** If you do not cancel after a UI timeout, can you leave all pending Futures around forever?  
**Answer:** No. You need a longer network deadline, outstanding limits, stream and registry cleanup, metrics, and reconciliation.

## 17. Practical Checklist

Before using timeout/cancel in async Java HTTP:

- [ ] Identify the exact deadline type: **wait**, **CompletableFuture stage**, **HTTP request**, **connect**, or **business operation**.
- [ ] An expired `get(timeout)` **must not** be turned into a claim that the network was canceled.
- [ ] If late results are needed, keep the original `sendAsync` Future and only time out a **derived view**.
- [ ] `orTimeout`/`completeOnTimeout` **mutates the called future itself**, not creating a new stage automatically.
- [ ] Do not use a success fallback to fabricate a server result.
- [ ] For request deadlines, catch `HttpTimeoutException` properly; do not confuse it with `TimeoutException`.
- [ ] For `cancel(true)`, understand it is an **attempt** to cancel the exchange in the default HTTP client, not a guarantee of remote rollback.
- [ ] Do not rely on `cancel`, `isCancelled`, TCP FIN/RST, or HTTP/2 `RST_STREAM` as proof that business logic did not run.
- [ ] Distinguish HTTP/1.1 connection closure from HTTP/2 stream cancellation; monitor impact on reuse.
- [ ] For POST/side effects, do not retry with a new ID when the outcome is unknown; use an idempotency key per server contract.
- [ ] Reconcile server status or transaction ID if the client times out/cancels.
- [ ] Manage pending futures, request-body sources, response-body streams, connection resources, and late callbacks.
- [ ] Test with controlled server latches; do not rely on `Thread.sleep` to guess thread/network timing.
- [ ] Log `callerWaitExpired`, `httpRequestTimedOut`, `cancelRequested`, and `serverBusinessOutcome` separately.
- [ ] On interruption, handle `InterruptedException` and restore the interrupt flag per policy.
- [ ] Do not block event-loop/completion threads waiting on a Future that might need that very thread to complete.

**Core takeaway:** `Future.get(timeout)` only says **the caller's wait time expired**. `orTimeout` says **the stage hit its deadline**, `HttpRequest.timeout` says **the HTTP request exceeded the client's deadline**, and `cancel(true)` only **requests an attempt to stop the exchange**. None of them guarantees **the server has not processed it or has rolled back**. To conclude a business outcome, you need **a response/protocol acknowledgment or a server status check**.

### Official API Documentation (Java 17)

- [`java.util.concurrent.Future` — `get(timeout)` and `cancel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [`CompletableFuture` — `orTimeout`, `completeOnTimeout`, `copy`, `isDone`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [`HttpClient` — `sendAsync` and default client cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [`HttpRequest.Builder` — `timeout(Duration)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [`HttpTimeoutException` — HTTP request timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [`HttpConnectTimeoutException` — connect timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [`HttpResponse.BodyHandlers` — handling response bodies](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
