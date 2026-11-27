# Connect Timeouts, Request Timeouts, and Error Handling in Java 17

## 1. Why Do Network Applications Need Timeouts?

A network call can become slow or never receive data because the server is overloaded, DNS fails to resolve a domain name, the network path has an outage, a firewall blocks the connection, or the peer stops responding. If a program waits indefinitely, threads can remain blocked for a long time, resources are tied up, and downstream requests suffer.

A **timeout** defines the maximum duration an operation may wait during a specific phase. In Java, distinguish:

- **Connect timeout:** limits the time to establish a network connection.
- **Read timeout:** limits the time waiting for the next piece of data while reading from a connection.
- **Request/response timeout:** limits the time waiting for a response to a request in high-level APIs like Java HttpClient.
- **Overall deadline:** the total time budget an application sets for an entire workflow, which may span multiple attempts and multiple stages.

These concepts do not substitute for one another. A TCP connection may be established quickly while the server takes a very long time to process the request; conversely, the connection itself may fail to establish from the start.

In Java 17, timeouts can be configured using APIs such as `Socket.connect`, `Socket.setSoTimeout`, `URLConnection`, and `java.net.http.HttpClient`. This lesson only uses APIs still applicable in Java 17.

## 2. Distinguishing the Phases of a Network Call

A simple HTTP call typically goes through these phases:

~~~text
Application
  |
  | 1. Hostname resolution (DNS)
  v
IP Address
  |
  | 2. Establish TCP connection
  v
TCP Connection
  |
  | 3. TLS handshake (if using HTTPS)
  v
Secure Channel
  |
  | 4. Send HTTP request
  v
Server Processing
  |
  | 5. Receive status, headers, and body
  v
Application processes response
~~~

A timeout in one phase does not necessarily cover all remaining phases:

| Timeout type | Question being bounded | Examples of errors you may encounter |
|---|---|---|
| DNS resolution | Can the hostname be resolved to an address? | `UnknownHostException` |
| Connect timeout | Can a connection to the endpoint be established within the allowed time? | `ConnectException` or API-specific timeout |
| Read timeout | Is the next chunk of data received within the allowed wait window? | `SocketTimeoutException` |
| Request timeout | Does the request receive a response within the configured deadline? | `HttpTimeoutException` |
| Overall deadline | Does the entire workflow finish before the deadline? | Application-defined deadline error |

Do not treat this table as an absolute one-to-one mapping: the exact exception type also depends on the API, operating system, TLS, DNS, and the moment the failure occurs.

## 3. Connect Timeout and Read Timeout with Socket

`Socket` is the low-level API for working with TCP connections. Two settings commonly confused are `connect timeout` and `SO_TIMEOUT`.

### 3.1. `Socket.connect(endpoint, timeout)`

The method:

~~~java
socket.connect(new InetSocketAddress(host, port), timeoutMillis);
~~~

limits the time waiting to establish a connection:

- `timeoutMillis > 0`: maximum wait time in milliseconds.
- `timeoutMillis == 0`: wait indefinitely.
- `timeoutMillis < 0`: invalid, throws `IllegalArgumentException`.

Example:

~~~java
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.io.IOException;

String host = "example.com";
int port = 443;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 3_000);
    System.out.println("Connected");
} catch (SocketTimeoutException ex) {
    System.err.println("Connection timed out: " + ex.getMessage());
} catch (IOException ex) {
    System.err.println("Connection failed: " + ex.getMessage());
}
~~~

The timeout here only controls the Socket connect operation. It does not set a limit on the total time spent reading the response or processing data after the connection succeeds.

### 3.2. `Socket.setSoTimeout(timeoutMillis)`

`setSoTimeout` configures the wait time for read operations on the socket's `InputStream`:

~~~java
socket.setSoTimeout(5_000);
int value = socket.getInputStream().read();
~~~

If no data is available to read within the wait window, the read operation throws `SocketTimeoutException`.

- `timeoutMillis > 0`: maximum wait time for a single read operation.
- `timeoutMillis == 0`: wait indefinitely on reads.
- Negative values are invalid.

Key point: `SO_TIMEOUT` is **not a total deadline for the entire response**. If the application reads multiple times and receives a small amount of data before each timeout, total reading time can exceed the configured value.

For example, a 5-second read timeout does not mean the entire file must transfer within 5 seconds. It limits how long a single blocked read call can wait.

### 3.3. Combining connect and read timeouts

~~~java
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("example.com", 80), 3_000);
    socket.setSoTimeout(5_000);

    try (InputStream input = socket.getInputStream()) {
        int firstByte = input.read();
        System.out.println(firstByte);
    }
}
~~~

Here:

- Establishing the TCP connection is limited to 3 seconds.
- Each read call can wait at most 5 seconds.
- Closing the Socket releases the connection when it is no longer used.

If a total deadline is required, the application must compute the remaining budget and adjust timeouts or cancel the operation when time expires.

### 3.4. A read timeout does not automatically close the socket

When a read operation throws `SocketTimeoutException`, the socket is not necessarily closed. The application may handle it, attempt to read again, or close the connection depending on the protocol. However, retrying a read only makes sense if the protocol state remains synchronized and no data was lost or partially processed.

Do not catch a timeout and blindly keep using the connection; you must understand the protocol and parser state before continuing.

## 4. Timeouts with URLConnection and HttpURLConnection

`URLConnection` is the legacy API for accessing resources by URL. It provides two settings:

- `setConnectTimeout(int timeout)`.
- `setReadTimeout(int timeout)`.

Both take milliseconds. A value of 0 means no wait limit; negative values are invalid.

### 4.1. Example reading HTTP with HttpURLConnection

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

URL url = new URL("https://example.com/");
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(3_000);
connection.setReadTimeout(5_000);
connection.setRequestMethod("GET");

try {
    int status = connection.getResponseCode();
    InputStream body = status >= 400
            ? connection.getErrorStream()
            : connection.getInputStream();

    if (body != null) {
        try (body) {
            String text = new String(
                    body.readAllBytes(),
                    StandardCharsets.UTF_8);
            System.out.println(text);
        }
    }
} finally {
    connection.disconnect();
}
~~~

This is a minimal example for a small text response. For large responses, read in buffered chunks rather than using `readAllBytes` to avoid loading the entire body into memory.

### 4.2. Read timeout is not total request time

`setReadTimeout` limits the wait time for reading when no data is ready. If the server trickles data such that every read receives data before the timeout expires, total processing time can be many times the timeout.

`HttpURLConnection` does not provide a general request deadline setting equivalent to `HttpRequest.Builder.timeout`. If you need to cap total duration, the application must manage deadlines, cancellation, and resource closing appropriately.

### 4.3. Distinguishing HTTP statuses from network errors

HTTP 404, 429, or 500 are **protocol-valid HTTP responses**, not automatically network exceptions. With `HttpURLConnection`, read the response code and choose `getInputStream` or `getErrorStream` based on the status.

A connection failure, timeout, or TLS error is typically reported via an exception. Do not catch only `IOException` and treat all HTTP statuses as connection errors.

## 5. Modern HttpClient in Java 17

`java.net.http.HttpClient` was standardized in Java 11 and is available in Java 17. It is usually the preferred choice for new HTTP client code because the API supports requests/responses, timeouts, redirects, synchronous, and asynchronous execution.

Two important configurations:

- `HttpClient.Builder.connectTimeout(Duration)`: limits connection establishment time.
- `HttpRequest.Builder.timeout(Duration)`: limits the time waiting for a response to a request.

Example:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/status"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.body());
~~~

### 5.1. Connect timeout

`connectTimeout` is set on `HttpClient.Builder`, not on each request builder. It is used when the client needs to establish a new connection. If a connection can be reused from the connection pool, the operation may not need a new connection, so connect timeout does not necessarily apply to that request.

If no connect timeout is configured, the client imposes no separate connection time limit at this API level.

If connection establishment exceeds the limit, you may receive `HttpConnectTimeoutException` (a subtype of `HttpTimeoutException`).

### 5.2. Request timeout

`HttpRequest.Builder.timeout(Duration)` sets the timeout for a single request:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

If no timeout is set, the API imposes no wait limit via this request timeout configuration. If the response is not received within the specified duration, the client may throw `HttpTimeoutException`.

The `Duration` must be positive; zero or negative values are invalid for a request timeout. Configure an explicit duration rather than relying on an unbounded default.

### 5.3. Request timeout and connect timeout together

Example:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(6))
        .GET()
        .build();
~~~

The two settings protect two different aspects:

- A new connection must be established within the connect timeout budget.
- The request must receive a response within the request timeout budget.

These are not two durations that always add up to a fixed 8-second deadline. They can run concurrently during the same request; whichever limit expires first determines the resulting timeout error. Applications should still enforce a separate overall deadline if they need to bound pre-/post-HTTP steps or multiple retries.

### 5.4. Streaming response bodies

With `BodyHandlers.ofString()`, `send` finishes after the body is collected into a String. With `BodyHandlers.ofInputStream()`, the response can be returned with an `InputStream` for the application to read afterward.

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Read and process body.
}
~~~

When using a streaming body, manage reading and closing the stream carefully. Do not assume the request timeout acts as a deadline for all application work performed after receiving the response object; if you need to bound body-reading or subsequent processing time, design an appropriate deadline/timeout for that stage.

## 6. Handling HttpClient Exceptions

Key exceptions:

| Exception | Common meaning | Handling guidance |
|---|---|---|
| `HttpConnectTimeoutException` | Timed out establishing a new connection | Check endpoint, network, load, and connect timeout |
| `HttpTimeoutException` | Request did not receive a response within the deadline | Check server, request timeout, and deadline |
| `ConnectException` | Connection refused or could not be established | Check host, port, service, and firewall |
| `UnknownHostException` | Hostname could not be resolved | Check DNS, hostname, and network configuration |
| `SSLException` | Error during TLS/SSL | Check certificates, trust store, hostname, and TLS settings |
| `IOException` | General I/O error | Inspect root cause and resource state |
| `InterruptedException` | Waiting thread was interrupted | Restore interrupt or propagate per contract |

`HttpConnectTimeoutException` is a subclass of `HttpTimeoutException`, so if you want to handle it separately, catch the subclass first:

~~~java
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    System.out.println(response.statusCode());
} catch (HttpConnectTimeoutException ex) {
    System.err.println("Connect timed out: " + ex.getMessage());
} catch (HttpTimeoutException ex) {
    System.err.println("Request timed out: " + ex.getMessage());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Request interrupted", ex);
} catch (IOException ex) {
    System.err.println("HTTP I/O failed: " + ex.getMessage());
}
~~~

In library or service-layer code, you may declare the method to propagate `IOException` and `InterruptedException` instead of converting every error into `IllegalStateException`. The example above simply demonstrates restoring the interrupt flag when not propagating the exception.

### 6.1. HTTP error statuses are not automatic exceptions

`HttpClient.send` returns an `HttpResponse` even when the server replies with status 400 or 500. The application must inspect it:

~~~java
int status = response.statusCode();
if (status >= 200 && status < 300) {
    // Success according to application policy.
} else {
    // Classify 4xx, 5xx, or other statuses.
}
~~~

Do not use timeout exceptions to represent all HTTP failures. A 503 response indicates the server replied; a timeout indicates the client did not receive a response within the deadline.

### 6.2. Preserving the interrupt status

`InterruptedException` signals that the thread was asked to stop waiting or cancel work. Catching and ignoring it can cause cancellation signals to be lost:

~~~java
try {
    client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

In many applications, it is better to propagate `InterruptedException` up to the caller so that layer can decide to stop the workflow. Only restore the interrupt flag when you catch the exception and do not propagate it further.

## 7. Sending Asynchronous Requests and Cancelling Work

`HttpClient.sendAsync` returns a `CompletableFuture`:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenApply(HttpResponse::statusCode)
        .thenAccept(System.out::println)
        .exceptionally(ex -> {
            System.err.println("Request failed: " + ex.getMessage());
            return null;
        });
~~~

Request timeout is still configured on `HttpRequest`. When cancellation is needed, you can call `future.cancel(true)`; cancellation is best-effort per the API and does not mean the server has definitely stopped processing the request.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

// When the workflow no longer needs the result:
future.cancel(true);
~~~

Do not use `CompletableFuture.orTimeout` as a complete replacement for `HttpRequest` timeout without understanding the consequences: completing a future via timeout is not necessarily equivalent to cancelling the underlying network exchange. Set timeouts in the HTTP API and manage cancellation according to application needs.

## 8. Overall Deadlines and Time Budgets

A workflow can consist of multiple steps:

1. Call authentication service.
2. Call data service.
3. Call payment service.
4. Retry certain steps on transient failures.

If each step is allowed to wait 10 seconds with three retries, total time can far exceed what users tolerate. Therefore, distinguish **per-operation timeouts** from the **overall workflow deadline**.

### 8.1. Using System.nanoTime to measure elapsed time

For internal deadlines, use the monotonic clock `System.nanoTime()` instead of `System.currentTimeMillis()`. Wall clocks can be adjusted by time synchronization or system settings; relative deadlines need elapsed-time measurement.

~~~java
long timeoutNanos = Duration.ofSeconds(10).toNanos();
long deadline = System.nanoTime() + timeoutNanos;

long remainingNanos = deadline - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Overall deadline exceeded");
}
~~~

In production code, avoid overflow when adding very large durations and check the remaining budget before each step. For practical short durations, computing the difference `deadline - System.nanoTime()` is a common way to calculate remaining time.

### 8.2. Passing remaining time to each request

~~~java
Duration remaining = Duration.ofNanos(remainingNanos);

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(remaining)
        .GET()
        .build();
~~~

Do not reset to a full timeout for every retry when the overall deadline is nearly exhausted. Each operation should receive only the remaining budget.

### 8.3. Not every timeout controls DNS

Hostname resolution may run via the OS or runtime resolver. Do not assume that every API's connect timeout always strictly bounds total DNS resolution time in every environment. If DNS is critical to the deadline, understand your deployment environment's resolver and networking mechanics and measure in practice.

## 9. Retrying After Timeouts and Network Errors

Timeouts are often transient errors, but **it is not always safe to retry**. The server may have received and executed the request while the response was lost or delayed. Resending a request that creates a transaction, places an order, or charges money can perform the action twice.

### 9.1. Bounded retries

A retry policy should define:

- Maximum number of attempts.
- Backoff between attempts.
- Jitter to avoid synchronized retry storms across many clients.
- Overall deadline.
- Allowlist of retryable failures.
- Idempotency rules or an idempotency key for operations with side effects.

Never retry indefinitely.

### 9.2. Exponential backoff

A form of backoff that grows with the attempt count:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Where `d0` is the initial wait duration and `dmax` is the cap. Random jitter can be added to reduce clients hammering the server at the exact same instant.

Simple illustrative example:

~~~java
static Duration backoff(int attempt) {
    long baseMillis = 200;
    long capMillis = 5_000;
    int exponent = Math.min(attempt, 10);
    long delay = Math.min(capMillis, baseMillis * (1L << exponent));
    return Duration.ofMillis(delay);
}
~~~

This snippet only computes the delay; real calling code must also verify that enough deadline remains and add appropriate jitter.

### 9.3. Which failures can be retried?

| Situation | Common decision |
|---|---|
| Connect timeout or transient connection failure | Retryable if deadline remains and endpoint may recover |
| Read/request timeout | Retry only if operation is safe or idempotency is guaranteed |
| Non-existent DNS hostname | Usually do not retry repeatedly; check configuration |
| Invalid TLS certificate | Do not retry as a transient error; fix trust/certificate |
| HTTP 400/401/403 | Usually do not retry if request or credentials have not changed |
| HTTP 429 | Respect rate limit and `Retry-After` if provided |
| HTTP 500/502/503/504 | May retry depending on operation semantics, server policy, and deadline |

These decisions are general guidelines. Application code must follow the API specification and the idempotency guarantees of each operation.

### 9.4. POST and idempotency

A POST request can produce side effects. If the client times out after sending the request, you cannot conclude the server did not process it. Before retrying:

1. Determine whether the endpoint is idempotent.
2. If supported by the server, send the same idempotency key across attempts for the same logical operation.
3. Do not generate a new key on each retry if the goal is to identify the same operation.
4. If no idempotency mechanism exists, design reconciliation or status querying before resending.

## 10. Managing Resources When Errors Occur

Timeouts do not replace the responsibility to close resources. For Sockets, readers, writers, and body streams, close them with try-with-resources or an appropriate ownership mechanism.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 2_000);
    socket.setSoTimeout(3_000);

    try (var input = socket.getInputStream()) {
        // Read data.
    }
}
~~~

With HttpURLConnection, call `disconnect()` in `finally` when finished. With Java 17's HttpClient, you neither need nor can use try-with-resources on `HttpClient` as with AutoCloseable implementations in newer Java versions; scope the client to the application lifecycle and close body streams when using streaming handlers.

Do not hold connections, streams, or blocked threads indefinitely after a failure has been detected. At the same time, avoid closing shared resources still owned by another component.

## 11. Complete Example with Java 17 HttpClient

The program below configures connect timeout and request timeout, distinguishes timeouts from HTTP statuses, and restores the interrupt flag:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class Main {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "text/html")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            int status = response.statusCode();
            if (status >= 200 && status < 300) {
                System.out.println("Success: " + status);
            } else {
                System.out.println("HTTP response: " + status);
            }
        } catch (HttpConnectTimeoutException ex) {
            System.err.println("Connect timeout: " + ex.getMessage());
        } catch (HttpTimeoutException ex) {
            System.err.println("Request timeout: " + ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.err.println("Request interrupted");
        } catch (IOException ex) {
            System.err.println("Network or I/O error: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

Actual timings depend on the network, DNS, TLS, and server. Do not treat a successful run on a particular network as proof that timeouts always trigger to the exact millisecond; timeouts are wait bounds per the API and execution environment.

## 12. Common Pitfalls

### 12.1. Setting only connect timeout

The connection may succeed, yet the server fails to return a response. Without a request/read timeout, the thread can still hang for a very long time.

**Solution:** configure both a connection timeout and a response timeout appropriate to the API being used.

### 12.2. Treating read timeout as an overall deadline

Read timeout on Socket/URLConnection usually bounds the wait time for a read operation, not the total duration of the entire response.

**Solution:** establish an overall deadline using a monotonic clock and compute the remaining time for each stage.

### 12.3. Leaving timeouts unbounded by default

Many APIs default timeout to 0 or unset, meaning wait indefinitely per the API contract.

**Solution:** set explicit values based on SLAs, user experience, and realistic processing times.

### 12.4. Catching every error and retrying

TLS errors, authentication failures, HTTP 400, or malformed requests will not be resolved by repeated retries.

**Solution:** classify exceptions and HTTP statuses, and retry only allowed transient errors.

### 12.5. Retrying requests with side effects without idempotency

A timeout does not prove the server has not executed the request.

**Solution:** use an idempotency key or verify state before resending the operation.

### 12.6. Swallowing InterruptedException

Catching and ignoring the exception loses the thread-stop signal.

**Solution:** propagate the exception or call `Thread.currentThread().interrupt()` before returning.

### 12.7. Confusing HTTP 500 with IOException

An HTTP status is a reply from the server, not always an exception.

**Solution:** inspect `response.statusCode()` or `getResponseCode()`.

### 12.8. Forgetting to close the response body stream

With streaming body handlers, failing to close the stream can retain resources or affect connection reuse.

**Solution:** use try-with-resources and respect resource ownership.

## 13. Practice Exercises

### Exercise 1 — Socket connect and read timeouts

Write a TCP client connecting to a configured host/port with a 2-second connect timeout and a 4-second read timeout. Catch `SocketTimeoutException` and `IOException` separately. Explain how the two timeouts bound two different stages.

### Exercise 2 — HttpClient timeouts

Create an `HttpClient` with a 2-second connect timeout and an `HttpRequest` with a 5-second timeout. Send a GET request to a test endpoint. Distinguish `HttpConnectTimeoutException`, `HttpTimeoutException`, and HTTP 503.

### Exercise 3 — Handling interrupts

Write a method calling `client.send`. If it catches `InterruptedException`, restore the interrupt flag and propagate or exit according to the contract. Explain why swallowing the exception is harmful.

### Exercise 4 — Overall deadline

Set an overall 10-second deadline using `System.nanoTime()`. Before each request, compute remaining time and set `HttpRequest.timeout(remaining)`. Do not start a new attempt once the budget is exhausted.

### Exercise 5 — Controlled retries

Design up to three attempts for a GET request on timeout or transient connection errors. Add capped exponential backoff and jitter. Do not retry HTTP 400/401 or TLS certificate errors. Explain why the same policy cannot be applied mechanically to a transaction-creating POST.

### Exercise 6 — Distinguishing read timeout from total duration

Simulate a server sending partial data before each read timeout interval. Explain why the client can keep reading longer than a single timeout duration if each read receives data in time. Propose an overall deadline to cap the entire process.

## 14. Completion Criteria

Learners have mastered this lesson when they can:

1. Distinguish connect timeout, read timeout, request timeout, and overall deadline.
2. Use `Socket.connect` to bound connection establishment time and `Socket.setSoTimeout` to bound read operations.
3. Configure `URLConnection`/`HttpURLConnection` with `setConnectTimeout` and `setReadTimeout`.
4. Use `HttpClient.Builder.connectTimeout` and `HttpRequest.Builder.timeout` in Java 17.
5. Explain the default unset timeout behavior and the meaning of `0` in millisecond-based APIs.
6. Distinguish network/timeout exceptions from HTTP status codes.
7. Handle `HttpConnectTimeoutException`, `HttpTimeoutException`, `IOException`, and `InterruptedException` in the right order and with the right semantics.
8. Manage cancellation, body streams, and resources after errors.
9. Design bounded retries, backoff, deadlines, and idempotency appropriately.
10. Recognize that a client-side timeout does not guarantee the server stopped processing the request.

## 15. Official Documentation

- [Java SE 17 API — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `connect`, `setSoTimeout`, and socket timeout behavior.
- [Java SE 17 API — `URLConnection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): `setConnectTimeout` and `setReadTimeout`.
- [Java SE 17 API — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): synchronous/asynchronous client and connection configuration.
- [Java SE 17 API — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration)): connection timeout.
- [Java SE 17 API — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)): request timeout.
- [Java SE 17 API — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) and [`HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): HttpClient timeout exceptions.
- [Java SE 17 API — `SocketTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): error when a socket read operation times out.

**Key takeaway:** connect timeout protects connection establishment; read timeout protects the wait window of a read operation; request timeout protects response waiting in the HTTP client; overall deadline protects the entire workflow. Proper error classification, resource closing, preserving interrupt status, and conditional retries keep network applications from hanging indefinitely or duplicating side effects.
