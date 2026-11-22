# Request Cancellation, Interrupting Synchronous send, and the Possibility That the Server Already Processed the Request (Java 17+)

**Cancelling an HTTP request on the client does not mean the server has cancelled the business work.** When a thread calling `HttpClient.send(...)` is interrupted or when the future from `HttpClient.sendAsync(...)` has `cancel(true)` called on it, the default Java 17 HTTP client **attempts** to cancel the HTTP exchange and release resources. However, the request may **have already been sent**, and the server may **be processing** or **have already committed** even though the caller never received a response.

A `POST /orders` command may have already created an order successfully, yet the client only sees `InterruptedException`, `CancellationException`, `IOException`, or `HttpTimeoutException`. If the client misinterprets the exception as “the server has not processed it yet” and resends the POST, it can create **two orders**. This lesson belongs to **Asynchronous HTTP** in **Java Advance - networking**, focusing on the Java 17 contract and designing handling for uncertain results (*ambiguous outcome*) with retry/idempotency.

## 1. Distinguishing Four Things That Get “Cancelled”

An HTTP exchange passes through multiple layers:

```text
CALLER THREAD / TASK
        |
        | send(request) or sendAsync(request)
        v
CLIENT HTTP EXCHANGE
        |
        | DNS / connect / TLS / send headers + body
        v
NETWORK / PROXY / LOAD BALANCER
        |
        v
SERVER HTTP HANDLER
        |
        | validate -> execute -> DB commit / publish message
        v
SERVER RESPONSE
        |
        v
CLIENT READS RESPONSE -> caller observes result
```

The single word “cancel” can refer to **four different actions**:

1. **Stopping waiting on the caller side:** the thread exits `send`; the future is marked cancelled; the UI no longer shows a spinner.
2. **Attempting to cancel the HTTP exchange in the client:** the client implementation stops sending/receiving, or attempts to release network resources. There is no guarantee the action is applied immediately.
3. **Closing the TCP connection or resetting the HTTP/2 stream:** the server may receive a disconnect signal, but a transport-layer reset is not a rollback.
4. **Cancelling the business task on the server:** only happens when the server/protocol **has its own cancellation mechanism**, at the right time and with sufficient authority to stop/compensate. It cannot be automatically inferred from the three behaviors above.

**Key takeaway:** `future.isCancelled() == true` describes the state of the **local future**, not the state of the transaction on the server.

## 2. Why Does Losing a Response Make the Outcome Uncertain?

Suppose the client sends a state-mutating POST:

```text
CLIENT                                    SERVER
  |-- POST /orders ------------------------->|
  |                                          | validate
  |                                          | commit order #A
  |<-------- response lost -----X-------------|
  |
  |-- timeout / InterruptedException
  |
  |-- retry POST without key --------------->|
  |                                          | commit order #B
  |
  |                                 Two logical side effects!
```

There are at least three race windows:

- **Before the request reaches the server:** the request might not have been sent yet, but an exception on the client **does not by itself prove** that. Network I/O may have already been handed off to another thread.
- **After the server receives it, before commit:** the server may continue or stop depending on its design; the client usually does not know the exact point reached.
- **After the server commits, before the response reaches the client:** the server has succeeded, yet the client can still see a timeout, interrupt, or connection reset.

There is no atomically shared ordering between “server commit” and “client receives response”. That is a distributed systems problem, **not a Java-specific bug**.

**Do not mechanically classify “client did not receive 2xx” as “business operation FAILED”.** The accurate state may be `UNKNOWN_OUTCOME` and require reconciliation.

## 3. How Can Synchronous `send` Be Interrupted?

Java 17 API signature:

```java
// Abbreviated signature for illustration; not a standalone class.
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;
```

`send` blocks the **calling thread** while sending the request and receiving the response according to the handler. According to the Java 17 Javadoc, if the operation is interrupted, the default `HttpClient` implementation **attempts to cancel the HTTP exchange** and throws `InterruptedException`; there is **no guarantee** as to when exactly the cancellation is processed.

The Javadoc also states clearly:

- The request **may still have been sent to the server** because sending had already started asynchronously in another thread.
- The server **may have already started processing**; the side effect may even have been committed before the client received the interrupt.
- Network resources may only be released **asynchronously afterward**.
- With HTTP/1.1, attempting to cancel may cause the underlying connection to be **closed abruptly**.
- With HTTP/2, attempting to cancel may **reset the stream** or, in some situations, close the entire connection.

Therefore, `InterruptedException` is a signal about the **caller's control flow**, not proof of a server rollback.

Source: [JDK 17 HttpClient.send](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).

## 4. Restoring the Interrupt Flag and Respecting Task Lifecycle

Handling pattern in a Java service:

```java
// Illustrative snippet: client, request, processResponse already exist.
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    processResponse(response);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Do not retry POST blindly: remote result may be UNKNOWN.
    throw ex;
} catch (IOException ex) {
    // Transport failure does not mean the operation was not committed.
    throw ex;
}
```

Technical points:

- `Thread.interrupt()` is **cooperative cancellation** for a local thread, not an HTTP request sent to the server to undo a transaction.
- A blocking operation that throws `InterruptedException` usually has already cleared the flag. **Restoring it with `Thread.currentThread().interrupt()`** allows the task management layer to detect the stop request.
- Do not swallow the exception and keep sending other requests in an infinite loop.
- If the upper layer does not declare `throws InterruptedException`, map cancellation to a result/cancellation exception according to policy, without losing the interrupt flag.
- If the request has side effects, log the operation ID and `UNKNOWN_OUTCOME` instead of asserting the request did not succeed.

An `ExecutorService.shutdownNow()` can interrupt a task currently in `send`, but it also **does not** guarantee the server has stopped processing the POST. Application shutdown should have a reconciliation mechanism for operations whose outcomes are still unknown.

## 5. `sendAsync` and `CompletableFuture.cancel(true)`

Asynchronous example:

```java
// Illustrative snippet: client and request must be created beforehand.
CompletableFuture<HttpResponse<String>> original =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString());

// When policy requires stopping the exchange:
boolean markedCancelled = original.cancel(true);
```

According to Java 17 `HttpClient`, the default implementation returns a **cancelable CompletableFuture**. Calling `cancel(true)` on an uncompleted future will **attempt to cancel the exchange** to release resources early. This is different from merely updating a UI flag.

However:

1. `markedCancelled == true` only certifies that **the future was marked cancelled**, not that the server rolled back.
2. There is no guarantee as to the exact time network cancellation is performed; the server may have already received/handed off the transaction to the DB.
3. If the future has already completed, `cancel(true)` may return `false`; the result was already available or had already failed beforehand.
4. Cancelling may also cause the underlying HTTP/1.1 connection to be closed, or the HTTP/2 stream to be reset; that is not business cancellation.
5. Dependent stages of a cancelled future may complete exceptionally; do not let a late-running callback overwrite newer business state.

**Distinction from standard `CompletableFuture`:** `CompletableFuture.cancel(boolean)` in general completes the future with `CancellationException`, and the `mayInterruptIfRunning` parameter does not control computation threads. The default `HttpClient` has special behavior that **attempts to cancel the HTTP exchange when `cancel(true)` is called**; do not confuse the two contracts.

## 6. Why Not Use `cancel(false)` as an “HTTP Stop Button”?

Java 17 `HttpClient` specifically states **`cancel(true)`** for attempting to cancel the exchange. Do not infer that `cancel(false)` on an HTTP future is guaranteed to have the same effect of releasing network resources. With a standard `CompletableFuture`, whether true or false, `cancel` may only affect the future's state.

An anti-pattern:

```java
// Illustrates a thinking error: do not use the result of cancel as a business ACK.
boolean cancelled = original.cancel(true);
if (cancelled) {
    // WRONG: record in the DB that "the order was definitely not created".
}
```

If the result can produce side effects, the state after cancel can still be `UNKNOWN`, requiring a lookup by operation ID or idempotency key.

When you have both `original` and `original.thenApply(...)`, avoid losing the reference to `original`. Cancelling only a derived future does not necessarily enforce the cancellation policy across all stages/providers in a complex application. Ensure the mechanism **propagates cancellation to the original HTTP exchange** and handles the corresponding body/subscription.

## 7. HTTP/1.1 and HTTP/2: Transport-Level Cancellation, Not Business Cancellation

| Protocol | How can cancellation affect it? | What remains unproven |
| --- | --- | --- |
| HTTP/1.1 | Closes the TCP connection, stops reading/writing the exchange | That the server did not receive the POST or did not commit |
| HTTP/2 | Resets a stream; sometimes closes the connection when background I/O requires it | That the server stopped the handler or rolled back the DB |
| Both | Client future or thread stops waiting | That downstream queue/payment has been revoked |

Even when the server receives a TCP disconnect, the handler may still continue because:

- The DB transaction already committed before the socket error.
- The job was already placed into a queue for another worker to process.
- The service needs to complete a step to preserve data invariants.
- A load balancer/proxy already forwarded the request beforehand.
- The server has no mechanism to stop business work or cannot undo external side effects.

`RST_STREAM` is an HTTP/2 signal, **not a SQL `ROLLBACK` command**. If you want to cancel a long-running job, the protocol must have a dedicated cancellation endpoint and state machine.

## 8. Java 17 Runnable Demo 1 — Server Already Did Work Before Client Interrupts

The file **`InterruptedSendDemo.java`** uses the standard JDK `HttpServer` (`jdk.httpserver` module), binding `127.0.0.1` on an ephemeral port. The server reads the POST body and increments an effect counter, then **holds the response unsent** using a `CountDownLatch`. The client calls `send` on one thread, and main waits for the server to confirm it has processed **before** interrupting that thread.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
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
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptedSendDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        CountDownLatch serverReceived = new CountDownLatch(1);
        CountDownLatch releaseResponse = new CountDownLatch(1);
        AtomicInteger applied = new AtomicInteger();
        AtomicBoolean caughtInterrupt = new AtomicBoolean();
        AtomicBoolean flagRestored = new AtomicBoolean();
        AtomicReference<String> unexpected = new AtomicReference<>();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(2);
        server.setExecutor(serverWorkers);
        server.createContext("/commit", exchange -> {
            try {
                try (InputStream input = exchange.getRequestBody()) {
                    input.transferTo(OutputStream.nullOutputStream());
                }
                applied.incrementAndGet();
                serverReceived.countDown();
                try {
                    releaseResponse.await(10, TimeUnit.SECONDS);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                byte[] reply = "OK".getBytes(StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, reply.length);
                    try (OutputStream output = exchange.getResponseBody()) {
                        output.write(reply);
                    }
                } catch (java.io.IOException clientGone) {
                    // Client cancellation can break response delivery.
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/commit");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .POST(HttpRequest.BodyPublishers.ofString("buy=1"))
                    .build();
            Thread sender = new Thread(() -> {
                try {
                    client.send(request,
                            HttpResponse.BodyHandlers.ofString());
                    unexpected.set("send returned normally");
                } catch (InterruptedException ex) {
                    caughtInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    flagRestored.set(Thread.currentThread().isInterrupted());
                } catch (Exception ex) {
                    unexpected.set(ex.getClass().getSimpleName());
                }
            }, "blocking-http-sender");
            sender.start();
            if (!serverReceived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not get POST");
            }
            sender.interrupt();
            sender.join(5_000);
            if (sender.isAlive()) {
                throw new IllegalStateException("Sender did not stop");
            }
            if (unexpected.get() != null) {
                throw new IllegalStateException(unexpected.get());
            }
            System.out.println("Server received POST: true");
            System.out.println("send threw InterruptedException: "
                    + caughtInterrupt.get());
            System.out.println("Interrupt flag restored: "
                    + flagRestored.get());
            System.out.println("Server actions: " + applied.get());
        } finally {
            releaseResponse.countDown();
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 InterruptedSendDemo.java
java --add-modules jdk.httpserver InterruptedSendDemo
```

Verified stdout:

```text
Server received POST: true
send threw InterruptedException: true
Interrupt flag restored: true
Server actions: 1
```

Explanation:

1. `serverReceived.countDown()` happens **after** the server has read the request and called `applied.incrementAndGet()`; thus main does not interrupt before the server effect is recorded.
2. The server holds the response unsent via `releaseResponse.await`; the sender is blocked inside `send`.
3. `sender.interrupt()` causes `send` to throw `InterruptedException` on the default JDK HTTP client. The catch block restores the interrupt flag.
4. `Server actions: 1` proves the **server already did the work** even though the client stopped waiting. Here the effect is just an in-memory counter, **not a production DB commit**.
5. The server may see an `IOException` when trying to write the response to a cancelled connection. A response write failure **does not undo the effect that already occurred**.
6. `finally` releases the latch, stops the server, and shuts down the executor. The demo uses timeouts to avoid deadlock if the environment fails.

This is a **deliberately event-synchronized** test, not a benchmark of interrupt speed. It illustrates the dangerous-but-valid case of the Java 17 contract.

## 9. Java 17 Runnable Demo 2 — Cancel Future, Retry With Same Key, and One Effect

The file **`CancelAndRetryDemo.java`** uses `sendAsync` to send a POST with header `Idempotency-Key: demo-order-42`. The server records the key and increments the effect **the first time it sees the key**. It blocks the first response until the client has called `cancel(true)`, after which the client **explicitly retries** the same logical operation using the **same idempotency key**.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelAndRetryDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        Set<String> processedKeys = ConcurrentHashMap.newKeySet();
        AtomicInteger requests = new AtomicInteger();
        AtomicInteger effects = new AtomicInteger();
        CountDownLatch firstCommitted = new CountDownLatch(1);
        CountDownLatch releaseFirstResponse = new CountDownLatch(1);

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(4);
        server.setExecutor(serverWorkers);
        server.createContext("/orders", exchange -> {
            try {
                try (InputStream input = exchange.getRequestBody()) {
                    input.transferTo(OutputStream.nullOutputStream());
                }
                int attempt = requests.incrementAndGet();
                String key = exchange.getRequestHeaders()
                        .getFirst("Idempotency-Key");
                if (key != null && processedKeys.add(key)) {
                    effects.incrementAndGet();
                }
                if (attempt == 1) {
                    firstCommitted.countDown();
                    try {
                        releaseFirstResponse.await(
                                10, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                byte[] reply = "ORDER-OK".getBytes(
                        StandardCharsets.UTF_8);
                try {
                    exchange.sendResponseHeaders(200, reply.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(reply);
                    }
                } catch (java.io.IOException clientGone) {
                    // Cancelled clients may not read their responses.
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            String endpoint = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders";
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create(endpoint))
                    .header("Idempotency-Key", "demo-order-42")
                    .timeout(Duration.ofSeconds(15))
                    .POST(HttpRequest.BodyPublishers.ofString("item=1"))
                    .build();

            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());
            if (!firstCommitted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not commit");
            }
            boolean cancelled = first.cancel(true);
            HttpResponse<String> retry = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("First request reached server: true");
            System.out.println("Future cancelled: " + cancelled);
            System.out.println("Retry HTTP status: "
                    + retry.statusCode());
            System.out.println("Requests received: " + requests.get());
            System.out.println("Unique effects: " + effects.get());
        } finally {
            releaseFirstResponse.countDown();
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Compile and run:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 CancelAndRetryDemo.java
java --add-modules jdk.httpserver CancelAndRetryDemo
```

Verified stdout:

```text
First request reached server: true
Future cancelled: true
Retry HTTP status: 200
Requests received: 2
Unique effects: 1
```

Explanation:

1. `firstCommitted.await` ensures the server already incremented the effect **before the client cancels**. `cancel(true)` can only try to stop the exchange; it does not “erase” the work that just happened.
2. The server counted **2 HTTP requests** because the client retried once.
3. The server counted **1 logical effect** thanks to the same idempotency key. This is **server logic**, not the Java client automatically deduplicating.
4. `ConcurrentHashMap.newKeySet()` is only a demo in **a single JVM**. It is not durable across restarts, not atomically tied to a DB write, does not compare payload hashes, and does not store the result. Do not use it as a production exactly-once strategy.
5. When the first request is cancelled, the server may fail to write the response. That does not affect its ability to process the next request on another HTTP exchange.
6. `requests=2` does not mean **2 TCP connections**; the demo does not measure pooling.

This scenario demonstrates two independent mechanisms: **cancellation on the client** and **dedup/idempotency on the server**.

## 10. Outcomes Must Be Classified by Actual Evidence

| Client observes | What is known for sure? | What cannot be concluded yet? |
| --- | --- | --- |
| HTTP 2xx and valid body | The API sent a successful response per contract | Whether side effects outside the contract have completed on all replicas |
| HTTP 4xx/5xx | A response with that status was received | An operation may have committed before the response-building error |
| `InterruptedException` | Thread calling `send` was interrupted, client attempted cancel | Whether the server received/committed |
| `CancellationException` | Future cancelled | Whether the server stopped/rolled back |
| `HttpTimeoutException` | No response arrived in time per timeout contract | Remote operation may have already completed |
| `IOException`/reset | Transport encountered an error | How many steps the server executed |
| No status received, but request ID seen in server ledger | Authoritative status can be looked up via id | Should not be inferred from a single network exception |

Design domain states such as `CONFIRMED_SUCCESS`, `CONFIRMED_REJECTION`, `UNKNOWN_OUTCOME`, or `RECONCILING`. They are determined by **API semantics and the business ledger**, not merely by the Java exception type.

A server returning 500 after a DB commit **may still have produced the effect**; an error status code does not always mean a database rollback. Conversely, an HTTP 200 might only confirm that a job was **accepted**, not completed, if the protocol is an asynchronous job.

## 11. Timeouts: Connect, Request, Future Waiting, and Business Deadline

Illustrative example:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();
```

`uri` and `payload` are undeclared; this snippet is not standalone.

- **`connectTimeout`** applies when a new connection must be established; it does not control total request processing time on a reused connection.
- **`HttpRequest.timeout`** is the time limit for receiving the HTTP response per the API; when exceeded, the client may report `HttpTimeoutException`. Server side effects may still have occurred.
- **`future.get(3, TimeUnit.SECONDS)`**, upon expiration, throws `TimeoutException` to the **waiting thread**, but **does not automatically cancel** the future or network exchange.
- **`CompletableFuture.orTimeout(...)`**, per the `CompletableFuture` contract, completes the future exceptionally when time expires. Do not treat it as proof that the network stopped or the remote side rolled back; if policy requires aborting the exchange, keep a reference to the original future and decide on `original.cancel(true)` accordingly.
- **Business deadline** may span multiple attempts, queue waiting, body reading, and reconciliation. Do not reset the deadline indefinitely on every retry.

When using streaming handlers such as `ofInputStream()` or `ofPublisher()`, the body may not be fully consumed when `HttpResponse` becomes available. The deadline for **body streaming** needs its own ownership/cancellation; do not equate the timeout for waiting on the HTTP response with the completion time of the entire business pipeline.

## 12. Cancelling a Regular Future Does Not Necessarily Interrupt a Worker Thread

A commonly confused distinction:

| Call | Primary meaning |
| --- | --- |
| `thread.interrupt()` on a thread running `HttpClient.send` | `send` may throw `InterruptedException`; default client attempts to cancel the HTTP exchange |
| `sendAsync(...).cancel(true)` on a JDK HTTP client future | Future cancelled; default JDK implementation attempts to stop the exchange |
| `new CompletableFuture<>().cancel(true)` | Regular `CompletableFuture` completes with `CancellationException`; does not automatically interrupt a computation thread |
| `future.get(timeout)` | Only waits up to timeout on the caller; does not automatically cancel the exchange |
| `HttpRequest.timeout(...)` | HTTP request/response deadline per `HttpClient`, not a business rollback |

In a regular JDK `CompletableFuture`, the `mayInterruptIfRunning` parameter has no effect on interrupting threads because a completion stage structure does not own thread control the way `FutureTask` does. The default `HttpClient` implements a **more specific** contract for the HTTP exchange when `cancel(true)` is called.

Do not treat `cancel` as a promise to “kill the task on the server”. Remote tasks exist outside the caller's JVM and have an independent lifecycle.

## 13. Idempotency per RFC 9110: When Is Retrying Safer?

According to [RFC 9110 `9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2), idempotent means the intended effect of multiple requests is **semantically identical** to that of a single request.

- **GET/HEAD** are *safe methods*, and are also idempotent methods. The standard contract requires not creating new business side effects; logging/analytics may still record multiple hits.
- **PUT/DELETE** have idempotent semantics; repeating a PUT with the same representation or a DELETE on the same resource may return a different status, but the intended effect is the same.
- **POST** is not idempotent by default: two commands creating orders/payments can usually create two objects/charges.
- Idempotence is semantics **the server must uphold**. If a custom API uses GET to create a transaction or PUT to increment a counter, the client must understand the actual contract and not blindly retry.

RFC 9110 explicitly states not to automatically retry requests with non-idempotent methods unless the client knows the operation is truly idempotent or has a way to know the request was not applied. **An `IOException` does not by itself prove that condition.**

Retries must also respect quotas, total timeout, backoff + jitter, attempt counts, and rate-limit policies. Even an idempotent but heavy GET can overload the server when thousands of callers retry simultaneously.

## 14. Implementing Idempotency-Key Properly: The Server Is Where Duplicates Are Prevented

For POSTs with side effects, design the API like:

```http
POST /orders HTTP/1.1
Host: api.example
Content-Type: application/json
Idempotency-Key: operation-42

{"itemId":"P1","quantity":1}
```

Requirements for a production server:

1. **One key per logical operation.** The caller generates the key once **before the first call**; all retries keep the same key.
2. **Scope the key to the principal/tenant and endpoint/method**. Do not allow another tenant to guess/reuse a key to read responses or interfere with transactions.
3. **Bind the key to a payload fingerprint**. The same key with a different body must return an error per contract, not be applied silently.
4. **Use a durable transactional record/unique constraint** synchronized with the business write so multiple replicas, races, and restarts do not create duplicates. Do not use a separate `containsKey` followed by `put`.
5. **Store/replay the previous result** or provide a status endpoint if the first attempt succeeded but the response was lost.
6. **Define an IN_PROGRESS/PENDING state** so retries arriving while the operation is still running do not execute the effect a second time.
7. **Sufficiently long TTL/retention** for the retry window/late retries; have logic for expired keys and audit/reconciliation.

The demo using `ConcurrentHashMap.newKeySet()` only proves the concept within **a single running process**. It has no transaction isolation, durable store, payload hash, multi-node coordination, or effect rollback; it **does not achieve exactly-once in a real payment system**.

## 15. Retry Matrix by Request Type and Observed State

| Scenario | Recommended action | Conditions |
| --- | --- | --- |
| Idempotent GET/HEAD hits transient network error | Bounded retry | Only when the API is truly safe per contract, with exponential backoff and deadline |
| Versioned state-setting PUT | Conditional retry | Use the same representation/ETag/conditional headers when needed to avoid lost updates |
| Idempotent DELETE resource | Can retry per contract | 2nd status may differ; do not automatically treat 404 as a business error |
| Order-creating POST **without key** loses response | **Do not blind retry** | Return UNKNOWN, look up transaction/status first |
| POST with server-enforced idempotency key | Retry **same key** | Same payload/principal, key still valid, bounded attempts |
| POST using a one-shot body publisher | Do not resend as-is | Requires a replayable body or resumable protocol |
| User explicitly cancels operation | Do not restart immediately | May need to reconcile side effects already executed |
| Server returns HTTP 429/503 | Decide per semantics | Respect `Retry-After` and retry budget; do not multiply load indefinitely |

**Note:** Sometimes the server returns an error response after already committing, because sending the response can also fail. Therefore, the retry policy must be based on **operation identity** and authoritative state, not solely on HTTP status or Java exceptions.

## 16. If You Need Real Server Work Cancellation: You Must Have a Dedicated API

For long-running jobs, a protocol may define:

```text
POST /jobs (Idempotency-Key K)  -> 202 Accepted, jobId=J7
GET  /jobs/J7                 -> RUNNING
POST /jobs/J7/cancel          -> CANCEL_REQUESTED
GET  /jobs/J7                 -> CANCELLED or COMPLETED
```

A business-layer `cancel` command also **has races**: the job may have already committed before the cancel request reaches the server, a downstream may not support rollback, or the job may have transitioned to a non-cancellable step. The server needs to clearly document:

- At which point it can stop before side effects occur.
- Once committed, whether it returns `COMPLETED` or transitions to a **compensating action**.
- Whether the cancel endpoint is idempotent.
- What the status query guarantees about durability.
- If the user closes the client mid-way, where the job state is durably persisted.

Do not equate HTTP/2 `RST_STREAM` with `POST /jobs/J7/cancel`. One is a transport signal; the other is a business contract.

## 17. Response Streaming and Late Cancellation

An important detail: `BodyHandlers.ofInputStream()` can deliver the response object **after headers are received**, before the body has been read to EOF.

```java
// Snippet: client/request and imports are already in place.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Consume bytes with a quota/deadline, or close when stopping early.
}
```

Once `send` has returned the response, a `Thread.interrupt()` occurring **afterward** is no longer an interrupt “inside `HttpClient.send`”. It may affect a blocking `InputStream.read` operation depending on stream/implementation behavior, but the caller must still **close the body properly**.

Similarly, `ofPublisher()` returns `Flow.Publisher<List<ByteBuffer>>`; you must **subscribe/request** until a terminal event or call `Subscription.cancel()` when cancelling. Closing/cancelling the response body cleans up an exchange; it **does not undo side effects** of the request on the server.

Do not treat a completed `CompletableFuture` as proof that body download has finished. If using a streaming response, follow-up business stages must handle errors and cancellation separately.

## 18. Cancellation in a Pipeline: Keep a Reference to the Original Request

A pipeline typically has multiple futures:

```text
User request
    |
    v
sendAsync future -------------- HTTP exchange
    |
    +-- thenApply(parse)
    +-- thenCompose(store)
    +-- whenComplete(metrics)
    |
    v
Application result / UI future
```

If the user clicks “Cancel”, the application needs to decide:

- Should it call `original.cancel(true)` to **attempt to stop the HTTP exchange**?
- Should it cancel the body publisher/subscriber, timeouts, queues, and downstream tasks owned by the application?
- How will late-arriving callbacks be identified? Is there an operation generation/token to prevent overwriting newer results?
- Should it record `CANCEL_REQUESTED`/`UNKNOWN_OUTCOME` and retain the operation ID for later status queries?
- Does it need to stop showing the spinner **immediately** while still maintaining backend reconciliation?

Cancelling a UI-layer `CompletableFuture` **does not necessarily** execute all of those decisions automatically. Cancellation propagation must be an explicit design; do not confuse it with eventual rollback.

## 19. Logging, Tracing, and Data Needed to Determine the Outcome

When the client does not know whether a request succeeded, a correlation ID must exist **before the first send**:

| Field | Client | Server |
| --- | --- | --- |
| `operationId` / Idempotency-Key | Saved before send, reused on retry | Attached to transaction/ledger record |
| HTTP method, route, payload fingerprint | Log safely, do not log secrets | Validate same key with matching payload |
| Attempt number | Count retries | Distinguish attempt vs logical effect |
| Timeout/cancellation cause | Interrupted, user cancel, deadline | May only see connection reset |
| Server status | UNKNOWN / RECONCILING if no response received | Authoritative PENDING / COMMITTED / FAILED |
| Commit time/result | Fetch via status API when needed | Durable state / result cache |
| Connection/stream status | IOException, cancel, HTTP version | Socket close, aborted response write |

Do not log `Authorization` tokens, passwords, or raw payment payloads in the name of debugging cancellation. Use redaction and scoped trace IDs. In monitoring, distinguish `client_cancelled`, `client_timeout`, `unknown_outcome`, `server_committed`, `duplicate_attempt`, and `reconciled`.

If you simply count every `InterruptedException` as “server failed”, metrics will lose the exact signal for **operations that committed without the client receiving an ACK**.

## 20. Testing Races With Latches Instead of Hoping for Random Network Failures

A test suite should include cases for:

1. **Interrupt before server receives:** client task finishes/is cancelled; do not assert remote did not receive without evidence.
2. **Interrupt after server reads request, before commit:** server may choose to stop or continue per contract.
3. **Interrupt after commit, before response:** effect exists; client must not create a duplicate effect on retry.
4. **Cancel `sendAsync` after commit:** future is cancelled, but side effect still exists.
5. **Retry with same key:** multiple HTTP requests, exactly **one logical effect**.
6. **Concurrent retries with same key across multiple server nodes:** requires unique constraint/transaction, not a single-node in-memory set.
7. **Same key with different payload:** server rejects.
8. **Server restart after commit before response:** durable ledger still recognizes retry.
9. **Incomplete response body streaming:** close/cancel body without leaking resources.
10. **HTTP/1.1 and HTTP/2:** observe connection close/stream reset; do not assume identical timing.
11. **Future.get(timeout) vs cancel(true):** verify wait timeout does not automatically cancel the exchange.
12. **Executor shutdown:** catch/restore interrupt and do not retry side effects outside policy.

The two Java programs in this lesson use latches to hit the exact point “**server already processed before caller lost the result**”. No public network, proxy, or packet loss injection is needed to observe this case.

## 21. Twenty Common Mistakes

1. **“`InterruptedException` proves the POST never reached the server.”** False: Java 17 docs state the request may still have been sent.
2. **“`cancel(true)` returning true means the server rolled back.”** False: the future is cancelled; the remote outcome may already be committed.
3. **“`cancel(false)` is guaranteed to stop the exchange like `cancel(true)`.”** There is no such guarantee.
4. **“`CompletableFuture.cancel(true)` always interrupts the thread.”** False for standard `CompletableFuture`.
5. **“Disconnecting TCP will roll back the DB transaction.”** There is no general mechanism like that.
6. **“HTTP/2 `RST_STREAM` is business cancellation.”** Wrong abstraction level.
7. **“A timeout means the server hasn't done anything.”** False: it can happen after commit.
8. **“HTTP 500 always allows retrying POST.”** It may have already committed and then failed while sending the response.
9. **“Retrying POST without a key only creates one order.”** Not guaranteed; can duplicate.
10. **“Each retry uses a new Idempotency-Key.”** Loses the ability to deduplicate the logical operation.
11. **“An idempotency map in one JVM is enough for multi-node production.”** Not durable, not atomic with the DB.
12. **“Same key with a different payload is still accepted.”** Correctness/security risk; must be enforced.
13. **“`future.get(timeout)` automatically cancels the network.”** No; it only limits wait time.
14. **“`orTimeout` guarantees the remote side stops processing.”** No; future completion differs from business outcome.
15. **“Swallow `InterruptedException` and resend immediately.”** Can create double effects and ignore shutdown signals.
16. **“Cancelling every dependent future is enough for a pipeline.”** Requires explicit ownership/propagation to the source exchange and body.
17. **“The future is cancelled, so all callbacks/workers have stopped.”** Late callbacks and remote work may still arrive.
18. **“Calling `send` already returned headers, so the streaming body doesn't need closing.”** Still must consume/close/cancel.
19. **“No operation ID needed if there's already a proxy HTTP request ID.”** Needs an ID that persists across retries and ties to the business transaction.
20. **“Seeing `IOException`, choose FAILED instead of UNKNOWN.”** Only conclude failure when there is authoritative evidence.

## 22. Self-Check Questions

**Question 1.** The thread calling `send(POST)` is interrupted. Can we display “order was definitely not created”? **No**. The outcome may be indeterminate; look up status by operation ID.

**Question 2.** `sendAsync(...).cancel(true)` returns true. What does that tell us? **The future has been cancelled**; the JDK HTTP client attempts to stop the exchange, with no guarantee the server stopped.

**Question 3.** The server committed before the client timed out. What is the risk of retrying a POST without a key? **Duplicate side effects**.

**Question 4.** Why must the same `Idempotency-Key` be kept across retries? **So the server recognizes the same logical operation** and does not apply the effect twice.

**Question 5.** `future.get(2, SECONDS)` throws `TimeoutException`. Can we conclude the request was cancelled? **No.** Waiting on a future and cancelling a future are two different operations.

**Question 6.** A `PUT` is defined as idempotent; must the 2nd response be identical to the 1st? **No**; idempotence concerns the intended effect, not requiring identical status/response.

**Question 7.** An mTLS/HTTP/2 server receives a stream reset; does the database transaction automatically undo? **No**. A separate cancellation/transaction policy is required.

**Question 8.** When `send` throws `InterruptedException` and the catch block does not propagate immediately, what should be done with the interrupt flag? **Restore** it with `Thread.currentThread().interrupt()`.

**Question 9.** Can the client guarantee exactly-once for POST using only a `ConcurrentHashMap`? **No**. Server-side dedup/transaction durability is required.

**Question 10.** The user clicks “Cancel” after payment succeeded but the response was lost: what should be done? **Display a status indicating reconciliation is needed, look up the operation/payment ID, and only execute compensation if the business protocol supports it**.

## 23. Production Checklist and Conclusion

1. **Identify HTTP semantics:** whether the method is safe/idempotent or side-effecting, and the endpoint's actual contract.
2. **Assign an operation ID before the first request** for operations that may require retry/reconciliation.
3. **Do not interpret interrupt/cancel as remote rollback.** Mark `outcome=UNKNOWN` if no result was received.
4. **Restore interrupt status** when `send` throws `InterruptedException`, or propagate to the task owner.
5. **Keep the original `sendAsync` future** if `cancel(true)` is needed to attempt stopping the HTTP exchange.
6. **Separate connect timeout, request timeout, future waiting timeout, and business deadline**.
7. **Define a retry policy with idempotency semantics, backoff/jitter, retry budget, and total deadline**.
8. **Require durable/atomic idempotency on the server** with key, tenant, method, payload hash, and status/result.
9. **Provide status lookup/reconciliation** for requests that committed while the response was lost.
10. **Have a separate cancellation endpoint/compensation policy** if real business job cancellation is needed.
11. **Close response body streams/cancel subscriptions** and clean up resources after late cancellation.
12. **Instrument failure cases by operation ID** across client, server, DB, and worker queue; do not log secrets.
13. **Test races** at request receipt, commit, response send, cancel, restart, and concurrent retry points.
14. **Do not depend on specific pool/HTTP version behavior:** HTTP/1.1 close or HTTP/2 reset does not determine business state.

**Conclusion:** Interrupting `HttpClient.send` or calling `cancel(true)` on `sendAsync` may cause **the client to stop waiting and attempt to cancel the HTTP exchange**, but **the server may still have received, processed, and committed the request**. Data protection does not lie in a `cancel` call, but in **semantically sound idempotency, durable state persistence, and the ability to reconcile after uncertain outcomes**.

### Official Documentation and Standards

- [Java SE 17 — HttpClient.send / sendAsync, interruption and cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 17 — CompletableFuture.cancel / orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [RFC 9110 `9.2.2 — Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
- [Java SE 17 — HttpServer (loopback demo)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).
