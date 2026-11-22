# close, shutdown, shutdownNow, awaitTermination, and Version Differences

## Lesson Objectives

In `java.net.http.HttpClient`, once a client is built with `build()`, it is not merely an immutable configuration; it also manages resources for serving requests such as **HTTP/1.1 and HTTP/2 connections**, processing threads, and asynchronous tasks. Therefore, it is necessary to distinguish between **finishing processing a single request** and **terminating the lifecycle of the entire client**.

This is a common point of confusion when learning Java networking: **Java 17 does not have** the lifecycle management methods `HttpClient.close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, and `isTerminated()`. **Starting in Java 21**, this group of methods was added to `HttpClient`, along with the ability to use `try-with-resources` via `AutoCloseable`. You cannot copy code using `client.close()` from JDK 21 documentation into a project compiled with `--release 17` and expect it to work.

After this lesson, you will be able to:

- Accurately tabulate the **available/unavailable APIs** between Java 11–20 (especially Java 17) and Java 21+.
- Explain the differences between `close()` (orderly close and **wait**), `shutdown()` (initiates an orderly shutdown but **does not wait**), `shutdownNow()` (attempts to stop quickly, with no guarantee of immediacy), `awaitTermination(Duration)` (bounded wait), and `isTerminated()` (reads state).
- Understand the states **accepting requests → shutting down → terminated**, and the point at which new requests are no longer accepted.
- Manage response bodies of type `String`, `InputStream`, `Stream<String>`, or `Publisher` so that graceful shutdown does not get stuck.
- Apply the **bounded graceful shutdown** pattern, optionally followed by `shutdownNow()` as a mitigation step, without claiming that all tasks have stopped.
- Distinguish stopping the **HTTP client** from stopping a **user-supplied ExecutorService**, closing the server's socket, or canceling `CompletableFuture` instances.
- Run **two standalone programs**: one **Java 17**-compatible program, and one **Java 21+** program using the full new API; verified on loopback without needing the Internet.

## 1. Two API Versions: Where Do Java 17 and Java 21 Differ?

`HttpClient` was standardized in `java.net.http` starting in **Java 11**. In Java 17, the class is an abstract class created via `HttpClient.newHttpClient()` or `HttpClient.newBuilder().build()`, providing `send` and `sendAsync`, but it **does not yet** declare `AutoCloseable` or the new lifecycle methods.

In **Java 21**, `HttpClient` implements `AutoCloseable` and adds five related methods:

| Method / behavior | Java 11–20, including Java 17 | Java 21+ | Purpose |
|---|---|---|---|
| `send(...)`, `sendAsync(...)` | Yes | Yes | Send synchronous/asynchronous requests |
| `HttpClient.newBuilder().build()` | Yes | Yes | Create a reusable client |
| `close()` on `HttpClient` | **No** | **Yes** | Orderly shutdown, waits until the client is terminated |
| `shutdown()` | **No** | **Yes** | Initiates orderly shutdown, returns without waiting for existing requests |
| `shutdownNow()` | **No** | **Yes** | Attempts to initiate immediate shutdown |
| `awaitTermination(Duration)` | **No** | **Yes** | Waits for remaining operations to complete after shutdown |
| `isTerminated()` | **No** | **Yes** | Checks whether all operations have completed after shutdown |
| `try (HttpClient c = ...)` | **Invalid** in Java 17 | **Valid** from Java 21 | Automatically calls `close()` when exiting the block |

**Do not** conflate `HttpClient` with `ExecutorService`. Both types have several methods with the same names (`shutdown`, `shutdownNow`, `awaitTermination`), but they are two different APIs with different parameters as well. For `HttpClient`, `awaitTermination` takes **`java.time.Duration`**; for `ExecutorService`, the traditional method takes **`long timeout, TimeUnit unit`**.

The reason you need to determine the version by the **compiler/release target**, not just the JVM runtime: if your machine runs JDK 24 but your project uses `javac --release 17`, you still **cannot** compile a call to `HttpClient.shutdown()` because the Java 17 API does not declare it. Conversely, code compiled using the Java 21 API should not be run on a Java 17 JVM.

### Example of an Error When Confusing Versions

~~~java
// Invalid with Java 17's HttpClient API:
try (HttpClient client = HttpClient.newHttpClient()) {
    client.shutdown();
    client.awaitTermination(Duration.ofSeconds(2));
}
~~~

This is an **example intentionally designed not to compile on JDK 17** to illustrate the difference. Besides importing `java.net.http.HttpClient` and `java.time.Duration`, the code also requires a **Java 21+** compilation environment to have those symbols. Separate runnable programs for Java 17 and 21 are provided later.

## 2. Why Does an HttpClient Have a Lifecycle?

At the API level, `HttpClient` after `build()` is **immutable in configuration** (preferred version, redirect policy, proxy, TLS context, etc.), but sending requests requires **stateful runtime resources**:

- **Connection pool / keep-alive:** the client may keep usable connections for reuse instead of opening a new TCP/TLS connection for every request.
- **HTTP/2 multiplexing:** a single TCP/TLS connection can serve multiple HTTP streams. It does not mean "once one response finishes, close the socket."
- **Asynchronous work:** `sendAsync` has futures, callbacks, body subscribers, and network operations that may still be running.
- **Response streaming:** the user may have already received `HttpResponse<InputStream>` without having read all bytes yet; body processing is not yet complete.
- **WebSocket / protocol sessions:** the application may use continuous communication resources that require their own lifecycle rules.

Therefore, **the completion of a single request is not necessarily the end of all client activity**. The `HttpClient` implementation may reuse connections, release resources when idle, or continue processing background tasks. Repeatedly creating short-lived clients per request often reduces reuse capability, increases connections, and makes resource control harder.

Common recommendation: **create one client for a group of trusted configurations/reasonable policies and reuse it across multiple requests**. If the application needs separate TLS/proxy/cookie policies, you can create different clients and manage each client's lifecycle according to the JDK version.

### "Immutable" Does Not Mean No Shutdown Needed

`HttpClient` has no public setters to modify the client after building, but:
- `send`/`sendAsync` still create operations;
- the connection pool and network activities still change over time;
- body publishers/subscribers and custom executors have separate lifecycles;
- close/shutdown decides **not to accept new requests and to finish ongoing work**.

Do not assume "since the client is immutable, Java automatically frees everything as soon as the response is returned," especially when the response is processed as a stream that the caller has not closed.

## 3. Java 21+ Lifecycle States

Simple diagram:

~~~text
     HttpClient.newBuilder().build()
                    │
                    ▼
        ACTIVE / accepts new requests
                    │
          shutdown() or close()
                    │
                    ▼
    SHUTTING DOWN / rejects new requests
       │            │
       │            └─ existing requests and response body
       │               processing are allowed to complete per orderly policy
       │
       ├─ awaitTermination(Duration) → wait / timeout / interrupt
       │
       ├─ shutdownNow() → attempts early interruption of running operations
       │                  (best effort, not guaranteed immediate)
       │
       ▼
             TERMINATED
        isTerminated() == true
~~~

**Key distinction:** `shutdown()` **does not wait**, `awaitTermination(...)` **does not initiate shutdown**, `close()` **both initiates an orderly shutdown and waits**, while `shutdownNow()` is a request for a faster stop with no guarantee of immediate clean cancellation.

According to the Java 21 contract, `isTerminated()` can only return `true` after a call to `shutdown()` or `shutdownNow()`. A client with no requests that **has not** been shut down is still **not considered terminated** just because it is idle.

There is no method to restore a shut-down client back to the ACTIVE state. If you want to send new requests after stopping, create another `HttpClient` and configure its policy again.

### Concise Behavior Table

| API (Java 21+) | Blocks on call? | Previously submitted requests? | New requests? | Guarantee |
|---|---|---|---|---|
| `shutdown()` | **No** | Allowed to complete per orderly shutdown | No longer accepted | Starts the process |
| `awaitTermination(Duration d)` | Waits up to `d` when `d > 0` | Observes termination progress | Does not decide; requires shutdown first | `true` if terminated, `false` if timed out |
| `shutdownNow()` | **Does not wait for completion** | May be interrupted/canceled, but not guaranteed | No longer accepted | **Best effort** to terminate early |
| `close()` | **May wait a long time** | Attempts to wait for completion | No longer accepted | Waits until terminated per contract |
| `isTerminated()` | No | No effect | No effect | Reads state, does not trigger shutdown |

**Be careful with the word "graceful":** graceful shutdown does not guarantee that requests will always succeed, nor does it complete all downstream business work. It allows in-progress operations to complete where possible. Network failures, timeouts, and publisher/subscriber errors can still cause requests to fail.

## 4. `shutdown()`: Orderly, Yet Returns Immediately

In JDK 21:

~~~java
client.shutdown();
// Do not submit any more new requests to this client.
// Already-submitted requests may still be executing.
~~~

The snippet above assumes `client` is a JDK 21+ `HttpClient`. `shutdown()`:
1. **Initiates** an orderly shutdown procedure.
2. Stops accepting new requests submitted via `send` or `sendAsync`.
3. Allows previously submitted requests to continue the operations needed to complete — including waiting for the body to be delivered to the consumer.
4. **Does not wait** for them to complete before returning. If you want to wait, call `awaitTermination(Duration)` or `close()`.

Calling `shutdown()` again when the client is already shutting down has no additional effect according to the Javadoc. However, "not waiting" does not mean "already closed": immediately after the call, `isTerminated()` may still be `false`.

### When New Requests Are Rejected

In a multithreaded system, you must **stop the producer** from generating requests and define the shutdown point. If one thread calls `sendAsync()` at the same time another thread calls `shutdown()`, the ordering of those two events determines whether the request is accepted or rejected. Do not rely on operations submitted after shutdown being "queued until the client reopens": there is no reopen step.

**Do not depend on the exact exception type** when submitting a new request to a shut-down client: application code should ensure no further submissions occur per policy and handle failures appropriately, rather than writing logic that assumes a single exception message across all implementations.

## 5. `awaitTermination(Duration)` and `isTerminated()`: Observing Termination

Java 21 contract:

~~~java
client.shutdown();
boolean finished = client.awaitTermination(Duration.ofSeconds(3));

if (finished) {
    System.out.println("HTTP client terminated");
} else {
    System.out.println("Still terminating after 3s");
}
~~~

This is a Java 21+ snippet; it requires importing `java.time.Duration` and assumes `client` has already been built. `awaitTermination` returns:
- `true` when the client terminates within the wait duration;
- `false` when the wait duration elapses before termination;
- throws `InterruptedException` if the waiting thread is interrupted.

**`Duration.ZERO` or a negative duration:** the method **does not wait** and only checks the status at that moment. Do not use `awaitTermination(Duration.ZERO)` as a "wait forever" command; it behaves quite differently from some other timeout APIs.

**The timeout value is not a hard deadline for shutdown:** `awaitTermination(Duration.ofSeconds(3))` limits **that wait call**, not forcing all network/body work to stop on its own at the three-second mark. After receiving `false`, old tasks may still be running and require a follow-up handling policy.

`isTerminated()` is a way to query the instantaneous state:

~~~java
client.shutdown();
System.out.println(client.isTerminated()); // true or false depending on timing.
~~~

Do not write a unit test asserting `isTerminated() == true` **immediately** after `shutdown()` while async work is still in flight. Only assert it more reliably after `awaitTermination(...)` returns `true` on a compliant implementation.

### Handling Interrupts Properly

When `awaitTermination` is interrupted, the application must decide to stop quickly, report an error, or propagate the interrupt to the caller. Pattern for preserving the interrupt signal:

~~~java
try {
    boolean finished = client.awaitTermination(Duration.ofSeconds(3));
    if (!finished) {
        client.shutdownNow();
    }
} catch (InterruptedException ex) {
    client.shutdownNow(); // Best-effort early termination, not a guarantee.
    Thread.currentThread().interrupt();
    throw ex;
}
~~~

The snippet above is for Java 21+, inside a method declaring `throws InterruptedException` or handled appropriately. After catching, restore the interrupt flag and rethrow the exception; do not swallow the interrupt to keep waiting indefinitely.

## 6. `shutdownNow()`: Best Effort, Not "Kill Everything"

Java 21's `HttpClient.shutdownNow()` **attempts** to initiate an immediate shutdown. According to the API, the implementation *may attempt to interrupt* running operations; the behavior of operations when interrupted is not fully guaranteed. There is no guarantee that:

- All sockets close immediately before `shutdownNow()` returns.
- All `CompletableFuture` instances complete or complete exceptionally within a fixed deadline.
- All blocked `send()` calls are unblocked immediately.
- The server **has not** received/executed the sent request.
- All external resources such as a user-supplied executor or application file/network streams are automatically cleaned up.

Therefore, do not use `shutdownNow()` as a rollback mechanism for a POST request that has already started: the server may have already created the transaction before the client canceled. For non-idempotent requests, you need an idempotency key or a server-side state verification mechanism.

**Regarding subclasses:** `HttpClient` is an abstract class. The JDK's default implementation overrides the new lifecycle methods on a **best-effort** basis. According to the *Implementation Requirements* section of Java 21, if a subclass does not override `shutdownNow()`, the default base implementation simply calls `shutdown()`; therefore, never assume "every `HttpClient` implementation will actually interrupt."

### Graceful First, Immediate If Past Deadline

A Java 21+ handling block that is usually more sensible than calling `close()` unconditionally:

~~~java
client.shutdown();
boolean done;
try {
    done = client.awaitTermination(Duration.ofSeconds(5));
} catch (InterruptedException ex) {
    client.shutdownNow();
    Thread.currentThread().interrupt();
    throw ex;
}

if (!done) {
    client.shutdownNow();
    // If time remains, you can awaitTermination one more time.
    // Do not assume the call above guarantees an immediate stop.
}
~~~

This is a snippet requiring `java.time.Duration` and an existing `client`. In practice, you must stop submitting new requests, manage futures/streams, and define a separate completion deadline before shutting down.

**When a second `awaitTermination` also returns false:** record that shutdown has not completed; do not turn that into a conclusion that "everything is closed" just because `shutdownNow()` was called.

## 7. `close()`: Orderly Shutdown **and Wait**

Java 21 adds `AutoCloseable` to `HttpClient`. Thus, you can write:

~~~java
try (HttpClient client = HttpClient.newHttpClient()) {
    // Send requests and consume/close response bodies.
} // Automatically calls client.close().
~~~

This is a **Java 21+ pattern** and does not compile on JDK 17.

`close()`:
1. Initiates an orderly shutdown if the client has not already been shut down.
2. Waits for the remaining operations required for submitted requests to complete, reaching the terminated state.
3. Accepts no new requests after shutdown has been requested.
4. If interrupted while waiting, `close()` **may** call `shutdownNow()` to attempt to stop operations and then continue waiting; before returning, the interrupt status is restored per the documentation.
5. If the client is already terminated, calling `close()` again has no significant effect.

**Important:** `close()` **has no timeout parameter**, so it is **not suitable for enforcing a hard deadline** when other code still holds an uncleaned-up response stream/subscription. Even if `shutdownNow()` is requested from another thread, there is no guarantee that operations will finish immediately.

### Comparison Example

~~~java
// Java 21+:
client.shutdown();                  // Starts closing, does not wait.
client.awaitTermination(Duration.ofSeconds(2)); // Waits up to 2 seconds.
client.shutdownNow();               // Attempts to close faster, does not wait.

// Contrast with:
client.close(); // Orderly shutdown and WAITS until terminated.
~~~

The statements above are only a **semantics comparison**, not an instruction to call all four sequentially on the same client. In an application, choose **one lifecycle policy**: scoped `try-with-resources`, or bounded graceful shutdown with force fallback. Do not use a pointless chain of calls just to "be sure it's closed."

## 8. Two Tested Java 17 and Java 21+ Examples

The following two **standalone** programs both create an `HttpServer` on loopback `127.0.0.1` with dynamic port `0`, then use `HttpClient` to call `GET /ping` and receive `PONG`. The goal is to test the **different lifecycle APIs**, not to demonstrate a production HTTP server.

- **Example A:** compiled with `--release 17`; intentionally **does not use** `HttpClient.close/shutdown`.
- **Example B:** compiled with `--release 21`; uses `try-with-resources`, `shutdown`, `awaitTermination`, `shutdownNow`, and `isTerminated`.

They were compiled and run using a modern JDK with `javac --release 17` / `--release 21` to verify **API compatibility**. Running the actual bytecode on a JVM of the corresponding version still requires an environment with the appropriate JDK/modules. No external domain names or TLS certificates are needed.

### 8.1. Example A — Java 17 Compatible

Save in full as **`HttpClient17Demo.java`**:

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

public class HttpClient17Demo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] bytes = "PONG".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/ping");
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("Java 17 status: " + response.statusCode());
            System.out.println("Java 17 body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile/run commands with **JDK 17**:

~~~bash
javac -encoding UTF-8 HttpClient17Demo.java
java HttpClient17Demo
~~~

When checking **Java 17 API compatibility** using a newer JDK compiler:

~~~bash
javac --release 17 -encoding UTF-8 HttpClient17Demo.java
java HttpClient17Demo
~~~

Stdout on a successful test run:

~~~text
Java 17 status: 200
Java 17 body: PONG
~~~

**Explanation:**
- `HttpClient` in JDK 17 creates a client and uses `send` normally.
- `BodyHandlers.ofString` consumes the response body into a `String`; it leaves no open `InputStream` for the application to read manually.
- There is no `client.close()`, `client.shutdown()`, or `client.awaitTermination(Duration)` in Java 17 code. When the process exits, the OS reclaims process resources; in a long-running service, manage the number of clients and the request/stream lifecycle rather than creating new clients unboundedly.
- `server.stop(0)` closes **the lesson's HTTP server listener**, which is completely different from a lifecycle call on `HttpClient`.
- The demo code uses unencrypted HTTP on loopback to test the API; sensitive production endpoints require HTTPS/TLS and appropriate authentication policies.

### 8.2. Example B — Java 21+ and the Lifecycle Methods

Save in full as **`HttpClientLifecycle21Demo.java`**:

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

public class HttpClientLifecycle21Demo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
            InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ping", exchange -> {
            byte[] bytes = "PONG".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/ping");
            HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3)).GET().build();

            // close() is automatically called when exiting the block.
            try (HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1).build()) {
                HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                System.out.println("close example: "
                    + response.statusCode() + " " + response.body());
            }
            System.out.println("close returned");

            HttpClient graceful = HttpClient.newHttpClient();
            graceful.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            graceful.shutdown();
            boolean finished =
                graceful.awaitTermination(Duration.ofSeconds(3));
            System.out.println("graceful terminated: " + finished
                + " / " + graceful.isTerminated());
            if (!finished) {
                graceful.shutdownNow();
            }

            HttpClient forced = HttpClient.newHttpClient();
            forced.shutdownNow();
            boolean stopped =
                forced.awaitTermination(Duration.ofSeconds(3));
            System.out.println("forced terminated: " + stopped
                + " / " + forced.isTerminated());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Use **JDK 21 or later**:

~~~bash
javac -encoding UTF-8 HttpClientLifecycle21Demo.java
java HttpClientLifecycle21Demo
~~~

If using a newer compiler but wanting to check the Java 21 API surface:

~~~bash
javac --release 21 -encoding UTF-8 HttpClientLifecycle21Demo.java
java HttpClientLifecycle21Demo
~~~

Measured stdout on a modern JDK (with no pending streams/tasks during shutdown):

~~~text
close example: 200 PONG
close returned
graceful terminated: true / true
forced terminated: true / true
~~~

**Why does the code intentionally have three clients?**
1. **Client in `try-with-resources`:** sends a GET, completes the response body with `ofString`, and then `close()` is called when exiting scope. The line `close returned` only appears after closing has returned.
2. **Graceful client:** completes the request first, calls `shutdown()`, `awaitTermination(3s)`, and prints the results of `finished` and `isTerminated()`. In the test there is no pending work, so both are `true`.
3. **Forced client:** has not submitted any requests, calls `shutdownNow()`, and then waits. In the test it finishes successfully; **this does not prove** that `shutdownNow` always stops in-flight requests within 3 seconds.

**Do not treat the two `true / true` lines as guaranteed output for a busy server or a hung custom publisher.** On different machines or at different times, `awaitTermination` may return `false`; the code illustrates the need for a timeout-handling policy. This is an easily reproducible example when there is no pending work, not a cancellation stress test.

### Do Not Mix Java 21 Code into Java 17

Even though both examples use the same `HttpClient` class, `HttpClientLifecycle21Demo` relies on methods marked **Since: 21**. If a project sets `maven.compiler.release=17` or a Gradle Java 17 toolchain, the compiler must report an error if you copy `shutdown()`/`close()` into older code. The fix is to **manage the lifecycle in a JDK 17-compatible way** or **upgrade the project version in a controlled manner**, rather than using reflection to blindly call a method that might not exist.

## 9. Why Can `close()` or Orderly Shutdown Get Stuck on the Response Body?

This is a particularly important warning in the **Implementation Note on closing the HttpClient** of the Java 21 Javadoc.

Different `BodyHandlers` return body types with different consumption contracts:

| Response BodyHandler | Returned body | When is reading the body truly finished? | What needs to be done |
|---|---|---|---|
| `BodyHandlers.ofString()` | `String` | Normally `HttpResponse` only completes once bytes have been collected/decoded | No open stream that the caller must close |
| `BodyHandlers.ofByteArray()` | `byte[]` | Bytes are collected into an array before the body completes | Bound data size to avoid memory bloat |
| `BodyHandlers.discarding()` | `Void` | Response content is discarded by the handler | Useful when the body is genuinely not needed |
| `BodyHandlers.ofInputStream()` | `InputStream` | The body may still be waiting to be read **after `send` returns the response** | Read to EOF or `close()` the stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | The stream may not be fully consumed yet | Consume/`close()` the stream |
| `BodyHandlers.ofPublisher()` | Reactive publisher | Still depends on subscriber, demand requests, and cancellation | Subscriber must consume/cancel per the rules |
| Custom `BodySubscriber` | Depends on body type | May be waiting for downstream request/cancel | Handle subscription and cleanup |

If the application calls `client.close()` while an `HttpResponse<InputStream>` is open and **has neither been read nor closed**, the client may have to wait for operations that cannot complete. Similarly, a subscriber that neither sends demand nor cancels can **stall orderly shutdown**.

### Reading Streams Properly

For Java 21+ or Java 17, consuming an `ofInputStream` body should use `try-with-resources`:

~~~java
HttpResponse<InputStream> response = client.send(
    request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream in = response.body()) {
    in.transferTo(OutputStream.nullOutputStream());
} // Stream is closed before shutting down the client.
~~~

This is a **snippet** requiring imports for `java.io.InputStream`, `java.io.OutputStream`, and `java.net.http.HttpResponse`; `client` and `request` are already created. `transferTo` here only illustrates full consumption; in production you need **byte limits**, timeouts, and proper content/streaming handling to avoid reading untrusted data without bounds.

**If the body is not needed:** choose `BodyHandlers.discarding()`. If the stream needs chunk-by-chunk processing, proactively `close()` it in `finally` when it cannot be read to completion. Closing early may prevent the underlying HTTP/1.1 connection from being reused, which is still better than abandoning the stream.

**With `ofLines()`:** close the stream when it is no longer needed; do not let a lazy pipeline hold resources after receiving `HttpResponse`.

**With `ofPublisher()`:** follow the `Flow.Subscription.request(n)`, `cancel()`, and completion/error handling protocol. Merely obtaining a publisher and leaving it untouched can keep operations pending. Avoid subscribers that block indefinitely or never request data.

### Do Not Confuse a Completed Future with All Bytes Being Processed

A `sendAsync(request, BodyHandlers.ofInputStream())` call can complete its future with an `HttpResponse<InputStream>` **before all response bytes have been read by the caller**. `future.join()` only indicates that the `HttpResponse` per the `BodyHandler` is ready; it does not automatically drain or close the stream.

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = future.join();
try (InputStream in = response.body()) {
    // Consume/limit data or close the stream when not needed.
}
~~~

This is a Java 17+ snippet requiring imports for `java.util.concurrent.CompletableFuture`, `java.io.InputStream`, and `java.net.http.HttpResponse`; other variables are already created. In a real system, handle `CompletionException` and enforce a deadline before waiting on `join`, because `join()` has no timeout of its own.

## 10. `sendAsync`, Cancellation, and Incomplete Tasks

`sendAsync(...)` returns a `CompletableFuture<HttpResponse<T>>`. If the result is no longer needed, the application can request cancellation:

~~~java
CompletableFuture<HttpResponse<String>> pending =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

boolean requested = pending.cancel(true);
~~~

This is a Java 17+ snippet, not a standalone program. The JDK documentation states that `cancel(true)` on the future may attempt to cancel the HTTP exchange to release resources early, but:
- There is no guarantee on when cancellation actually takes effect.
- With HTTP/1.1, it may close the connection abruptly.
- With HTTP/2, it may reset the stream or occasionally close the connection.
- The request may already have reached the server and already produced business side effects.
- `cancel` does not replace cleaning up a stream that was already returned earlier.

**Business correctness:** a canceled `POST /payments` does not mean the server did not deduct funds. When retrying, you need an idempotency key and a reconciliation/server-state check mechanism. How you shut down the client is a resource policy, not a distributed transaction rollback.

### Cancel Futures Before or After Shutdown?

In systems, typically:
1. Stop creating new requests.
2. Wait a period of time for in-flight operations to complete per policy.
3. Cancel futures that are no longer needed per the application deadline; close/cancel body streams/subscriptions.
4. For Java 21+, call `shutdown()` and `awaitTermination`; if not completed, consider `shutdownNow()`.
5. Record operations that are still pending and protect the application shutdown process.

There is no "one-size-fits-all" order. Some services need to prioritize completing transactions, while others need to exit quickly. The key is not to call `shutdownNow()` and then claim "all requests were rolled back."

## 11. A Custom ExecutorService Is Not the HttpClient Lifecycle

An `HttpClient` can be built with a custom executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
    .executor(executor)
    .build();
~~~

This is a Java 17+ snippet with imports `java.util.concurrent.*` and `java.net.http.HttpClient`.

**Two different objects own different resources:**
- `client.shutdown()` (Java 21+ only) controls **HttpClient operations**.
- `executor.shutdown()` is an **ExecutorService** API and controls **accepting tasks into the executor**, not closing the HTTP client.
- The fact that `HttpClient` stops after requests does not automatically guarantee that all application tasks running in the user-supplied executor have finished and that the application's executor has been shut down.
- In Java 17, you can still call `executor.shutdown()`, but **do not** infer that this is equivalent to Java 21's `HttpClient.close()`.

Reasonable lifecycle order when the application owns the executor:
1. Stop producers from sending requests.
2. Ensure streams/futures that need to complete or be canceled are handled per policy.
3. **Java 21+**: shut down the client and wait (with a timeout) if needed.
4. After HTTP work that still needs the executor has been handled, shut down the **application-owned executor** separately and wait using the `ExecutorService.awaitTermination(long, TimeUnit)` API.
5. If any step does not finish, log/measure the state and handle interrupts per policy; do not assume everything closed cleanly.

If you shut down the custom executor too early while `sendAsync` still depends on it, remaining HTTP tasks may be rejected or stall, making it harder for the client to terminate. That is why it is necessary to clearly separate the owner of the client from the owner of the executor.

### Do Not Confuse with the Server Lifecycle

`com.sun.net.httpserver.HttpServer.stop(int delay)` is an API for stopping the **HTTP server**, not `HttpClient.shutdown()`. A demo program may run both a server and a client; when stopping, you must manage the two resource groups separately. In production applications there are also database pools, other thread pools, and message consumers, all with their own shutdown policies.

## 12. Choosing a Shutdown Policy by Scenario

| Scenario | Typical choice |
|---|---|
| Short-lived tool, Java 21+, all bodies already read | `try (HttpClient c = ...)` so `close()` runs automatically |
| Long-running service, many requests | Create/reuse client per configuration; stop when the service shuts down |
| Service needing graceful shutdown for at most a few seconds, Java 21+ | `shutdown()` then `awaitTermination(Duration)`; if timed out, consider `shutdownNow()` and monitor |
| Long-lived response streaming | Proactively close/cancel streams/subscriptions; do not let `close()` wait unboundedly |
| App using Java 17 | Do not call Java 21 APIs; reuse client, set timeouts, cancel futures, close body streams, manage custom executor and process lifecycle |
| Need to cancel application CPU tasks | Manage `ExecutorService` separately; do not treat `HttpClient.shutdownNow()` as a method to cancel CPU tasks |
| POST already sent but future was canceled | Do not auto-retry unconditionally; verify business state/idempotency |
| Using a custom subclass of `HttpClient` | Read the lifecycle contract/overrides; default base methods have minimal semantics |
| Only want to know if the client has stopped | Java 21+: `isTerminated()`; not a command to initiate shutdown |
| Want a non-blocking poll | Java 21+: `awaitTermination(Duration.ZERO)`, should be called after shutdown |

### Why Does `close()` Not Replace a Bounded Deadline?

Consider:

~~~text
T0  client.send(..., ofInputStream()) returns HttpResponse<InputStream>
T1  application has not read or closed the InputStream
T2  another thread calls client.close()
T3  close() waits for remaining operations
T4  stream is not consumed/canceled → close may wait for a very long time
~~~

In architectures that require fast stopping, do not let the shutdown path **depend unboundedly** on a stream that the application does not manage. Set request deadlines, explicit resource cleanup, and timeouts/grace periods; use `shutdown/awaitTermination/shutdownNow` to observe and react when deadlines are exceeded, while understanding the limits of best-effort cancellation.

## 13. Common Mistakes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Calling `HttpClient.close()` on JDK 17 | Method does not exist in the Java 17 API | Java 17 code must use a compatible lifecycle; upgrade JDK if needed |
| Thinking `HttpClient` has always been `AutoCloseable` since Java 11 | Only added in Java 21 | Explicitly note the minimum Java version when writing examples |
| Thinking `shutdown()` waits for all requests to finish | The method returns immediately after initiating shutdown | Use `awaitTermination` or `close` if you need to wait |
| Thinking `awaitTermination` calls `shutdown` automatically | It only waits/checks state | Call `shutdown` first |
| Thinking `awaitTermination(Duration.ZERO)` waits forever | A non-positive Duration is an instantaneous check | Use a positive Duration for waiting |
| Thinking `shutdownNow()` guarantees all requests stop immediately | The API is best effort only | Monitor state, use timeouts, cancel, and clean up |
| Thinking `close()` always returns quickly | It may wait for unfinished body work | Drain/close response streams; use a policy with a deadline |
| Thinking `isTerminated()==false` when idle is a bug | Without shutdown it cannot be true | Distinguish between idle and terminated |
| Using `BodyHandlers.ofInputStream` and abandoning the body | Keeps response delivery pending | Consume/close the stream |
| Using `ofPublisher` without the subscriber requesting/canceling | Reactive backpressure leaves the stream hanging | Control the subscription and cancel |
| Calling `future.cancel(true)` and claiming the server did not process the POST | Cancellation does not roll back server state | Idempotency/reconciliation |
| Stopping a user-supplied executor before HTTP work finishes | Async tasks may be rejected/hard to terminate | Define shutdown order by ownership |
| Shutting down `HttpServer` and assuming the client is closed | Two different objects | Clean up each resource |
| Creating a new client for every request | Loses connection pooling/reuse | Reuse clients sharing the same policy |
| `try-with-resources` on Java 21 while forgetting streaming bodies | `close` may wait unexpectedly | Ensure body lifecycle completes before leaving scope |
| Treating the demo's `forced terminated=true` output as a guarantee | The demo had no pending tasks | Test overload/cancellation separately |
| Compiling with JDK 24 and assuming the code runs on Java 17 | Need `--release 17` to lock the API | Check the project's target version |
| Using `ExecutorService.awaitTermination(3, SECONDS)` for `HttpClient` | Different method signature | Use `HttpClient.awaitTermination(Duration)` on Java 21+ |

## 14. Testing Important Scenarios

Do not only run a program that always succeeds; to verify a shutdown policy, design tests with **clear stopping conditions**:

1. **No pending requests:** create a Java 21+ client, call `shutdown()` then `awaitTermination(positive duration)`; it usually finishes quickly.
2. **One submitted and completed request:** call `send` with `BodyHandlers.ofString`, then `shutdown`; `awaitTermination` can return `true` quickly, as in the demo.
3. **In-flight async request:** a loopback server uses a `CountDownLatch` to control when the body is returned; `shutdown` does not block, and `awaitTermination(short duration)` can return `false`. Release the latch, wait again, and verify `true` within a reasonable time.
4. **Cancel async future:** call `cancel(true)` after the server has received the request, and inspect client and server logs; do not assert that the request was not processed.
5. **Unconsumed `InputStream`:** receive `HttpResponse<InputStream>` and do not read it; test graceful shutdown with a dedicated timeout, then close the stream and wait again. Use a test-wide deadline to avoid hanging CI.
6. **Test `ofPublisher` with no demand:** verify that the consumer must request/cancel; do not turn an unbounded `close()` into a hanging test.
7. **Custom executor:** submit requests with an application-owned executor; stop the client then stop the executor in the right order; track active tasks.
8. **Java 17 compile gate:** compile `HttpClient17Demo.java` with `--release 17` successfully; attempting to call `client.close()` in Java 17 source must be rejected by the compiler.
9. **Java 21 compile gate:** compile `HttpClientLifecycle21Demo.java` with `--release 21`; run on JVM 21+.
10. **Already-shut-down client:** try submitting a new request after shutdown and verify it is rejected; do not depend on a specific exception message.
11. **Interrupting an awaiting thread:** interrupt the waiter, handle `InterruptedException` per policy, and preserve the interrupt flag.
12. **HTTP/1.1 vs HTTP/2:** verify that cancellation behavior can affect sockets/streams differently; do not hard-code assertions like "always closes exactly one connection."

For timing tests, avoid `Thread.sleep` to "guess" that a request is running; use synchronization points like `CountDownLatch` and test timeouts. `shutdownNow()` is only a best-effort request, so do not assert that every OS/network/thread resource stops within a few milliseconds.

## 15. Self-Check Exercises

1. A project sets `--release 17`. Does `try (HttpClient client = HttpClient.newHttpClient())` compile? Why?
2. Starting from which Java version does `HttpClient` support `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, and `isTerminated()`?
3. After `client.shutdown()`, are already-submitted requests automatically canceled immediately? Does this call wait for response bodies to finish?
4. To wait at most 5 seconds after graceful shutdown, which method do you call? If it returns `false`, what does that mean?
5. Does `client.awaitTermination(Duration.ZERO)` wait forever or perform an instantaneous check?
6. Why is `isTerminated()` of a client with no requests still not `true` if `shutdown` has not been called?
7. State the fundamental difference between `close()` and `shutdownNow()` regarding waiting and stopping goals.
8. A response from `BodyHandlers.ofInputStream()` has already returned `HttpResponse`. Why can `client.close()` still wait?
9. When using `ofLines()` and `ofPublisher()`, what cleanup/demand responsibilities does the user have?
10. If `sendAsync` has `cancel(true)` called on it, can you conclude that a POST was not executed by the server?
11. If an `HttpClient` uses an `ExecutorService` created by the application, does `client.shutdown()` automatically shut down all of the application's thread pools?
12. When `awaitTermination` is interrupted, how should it be handled so the interrupt signal is not lost?
13. In the Java 21 example, why does `forced terminated: true / true` not prove that all active requests can be stopped within 3 seconds?
14. Does `HttpClient.close()` have a timeout parameter? If you want an observable shutdown deadline, which combination of methods should you use?
15. Distinguish between `HttpClient.awaitTermination(Duration)` and `ExecutorService.awaitTermination(long, TimeUnit)`.
16. Why can you build one `HttpClient` and reuse it across multiple requests instead of building a new one each time?
17. If the application still holds an `InputStream` returned from a response, what should the app do with the stream before closing the client during shutdown?
18. Why does Java 17 lacking `close()` not mean you can ignore timeouts and resource cleanup?

**Answer Key:**
(1) No, Java 17 `HttpClient` does not implement `AutoCloseable`; (2) Java 21; (3) no, orderly shutdown lets prior requests finish and `shutdown` does not wait; (4) `awaitTermination(Duration.ofSeconds(5))`, `false` means not yet terminated before the timeout; (5) instantaneous check; (6) shutdown must be called first; (7) `close` is orderly + waits, `shutdownNow` is a best-effort quick stop without waiting; (8) an unconsumed/unclosed body still requires network work; (9) close the stream or request/cancel the subscription per contract; (10) no; (11) no, the executor must be managed separately; (12) handle it and restore the interrupt/propagate; (13) the demo had no pending work; (14) no, use `shutdown + awaitTermination + shutdownNow` per policy; (15) different APIs and signatures; (16) connection/resource reuse; (17) read to completion/close/cancel; (18) Java 17 still requires managing streams, futures, timeouts, and application lifecycle.

## 16. Key Takeaways

- **JDK version is a hard boundary:** Java 17 does not have `HttpClient` lifecycle methods; **Java 21+** introduces `close/shutdown/shutdownNow/awaitTermination/isTerminated` and `AutoCloseable`.
- **`shutdown()`** initiates orderly shutdown and returns immediately; **`awaitTermination(Duration)`** performs a bounded wait; **`isTerminated()`** only observes state; **`close()`** is orderly and waits until terminated; **`shutdownNow()`** attempts to stop quickly without guaranteeing tasks are finished.
- **Body lifecycle determines whether shutdown makes progress:** unread/unclosed/uncanceled streams or publishers can keep requests pending, causing `close()` to wait.
- **Manage by owner:** the HTTP client, user-supplied executor, HTTP server, and request futures are distinct; each must have its own cleanup order.
- **Do not treat cancel as rollback:** a request may have already reached the server. Retrying operations with side effects must follow idempotency/reconciliation rules.
- **Use version-appropriate examples:** Java 17 must not call Java 21 APIs; Java 21 can use `try-with-resources` and bounded graceful shutdown.
- **Verify empirically with deadlines:** overload, interrupts, body streaming, and slow downstream consumers need dedicated tests; simple demo outputs do not represent all scenarios.

### References

- [Oracle Java SE 17 — HttpClient (without the lifecycle APIs from 21)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 21 — HttpClient (close/shutdown/shutdownNow/awaitTermination/isTerminated)](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 21 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 21 — ExecutorService (distinguishing shutdown APIs)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Inside Java — AutoCloseable HttpClient, technical article on the APIs added in JDK 21](https://inside.java/2023/12/10/sip092/)
