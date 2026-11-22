# Lab: Testing Synchronous, Asynchronous, Cookie, and Request Cancellation in HttpClient

Java 17+ includes the standard HTTP client `java.net.http.HttpClient`. An `HttpClient` can make **synchronous** HTTP calls using `send()`, **asynchronous** calls using `sendAsync()`, use `CookieManager` to manage cookies, and attempt to cancel a pending HTTP exchange via `CompletableFuture.cancel(true)`. To distinguish API behavior from network variability, this lab creates an **in-process loopback server** to experiment with and verify each case.

This exercise belongs to **Networking Labs** and covers four objectives:

1. Call `HttpClient.send()` on an endpoint that returns `200 PONG`, read the status/body correctly, and distinguish an HTTP status error from an I/O exception.
2. Send **two asynchronous requests concurrently** using `sendAsync()`, using `CompletableFuture.allOf()` and two `CountDownLatch` instances to verify that both server-side handlers have entered the waiting state **before** receiving the signal to proceed.
3. Attach a `CookieManager` to a specific `HttpClient`; verify that `Set-Cookie` is stored, `Cookie` is sent for the matching `Path`, not sent outside that scope, absent on a client without a cookie handler, and rejected when using `CookiePolicy.ACCEPT_NONE`.
4. Call `cancel(true)` while a request is still pending but **the server has already started processing**; observe the Future state and demonstrate that client cancellation **does not equate to rolling back server work**.

The hands-on section uses a single **`HttpClientLab.java`** file runnable on Java 17+, requiring no Maven, Gradle, JUnit, Internet access, or third-party libraries. The code was **compiled with `javac --release 17` and run three consecutive times on JDK 24**, with the exact output recorded in this article. The document also covers timeouts, exceptions, cancellation races, cookie scope, isolation, and risks when using these APIs in production.

## 1. Classes and Modules to Know

| Component | Module/package | Purpose |
| --- | --- | --- |
| `HttpClient` | `java.net.http` | Client that reuses connections/pools and executes HTTP requests |
| `HttpRequest` | `java.net.http` | Request URI, method, headers, body, and timeout |
| `HttpResponse<T>` | `java.net.http` | Status, headers, body, and response metadata |
| `HttpResponse.BodyHandlers` | `java.net.http` | Chooses how to consume the body: String, byte[], InputStream, file, Publisher |
| `CompletableFuture<T>` | `java.util.concurrent` | Represents an asynchronous result, composes stages, waits, times out, cancels |
| `CookieManager` | `java.net` | Policy for accepting cookies and storing/sending them via CookieStore |
| `CookiePolicy` | `java.net` | Examples: ACCEPT_ORIGINAL_SERVER, ACCEPT_NONE |
| `HttpCookie` / `CookieStore` | `java.net` | Cookie attributes and stored cookies |
| `CountDownLatch` | `java.util.concurrent` | Synchronizes test steps without relying on Thread.sleep |
| `HttpServer` | `jdk.httpserver` | Embedded HTTP/1.1 server for creating test fixtures |

Check JDK and modules:

~~~bash
java --version
java --describe-module java.net.http
java --describe-module jdk.httpserver
~~~

These two modules are distinct: `java.net.http` serves as the HTTP/WebSocket **client**; `jdk.httpserver` provides an embedded HTTP/HTTPS **server**. This lab uses both for end-to-end testing over loopback.

## 2. Comparing send() and sendAsync() Without Guesswork

| Aspect | `send(request, handler)` | `sendAsync(request, handler)` |
| --- | --- | --- |
| Return type | `HttpResponse<T>` | `CompletableFuture<HttpResponse<T>>` |
| Calling thread | Blocks until the response is processed according to the BodyHandler | Receives the Future immediately; HTTP proceeds asynchronously |
| Getting String body | `response.body()` after send returns | `future.get()/join()` succeeds, then `body()` |
| I/O errors | `IOException`, `InterruptedException` | Future completes exceptionally; `get()`/`join()` throws the appropriate wrapper |
| Running multiple requests | Executed sequentially if send is called on the same thread | Can create multiple Futures before waiting |
| Cookie state | Uses the HttpClient's CookieHandler | Uses the same HttpClient cookie mechanism |
| Cancellation | Thread interrupt causes the default client to attempt cancelling the exchange | `cancel(true)` on a cancelable HTTP Future attempts to cancel the exchange |
| Response streaming | Depends on BodyHandler; not every body is already consumed | Also depends on BodyHandler; Future completion does not guarantee the stream has reached EOF |

**An asynchronous API does not automatically make the server faster.** It allows the calling thread to continue doing other work while I/O is in progress. If code immediately calls `sendAsync(request).join()` with no other work to do, the thread still blocks until the result arrives.

~~~text
Synchronous:
  main --> send() -------- [waiting for response] --------> HttpResponse<String>

Asynchronous:
  main --> sendAsync() --> CompletableFuture ------> stage processing
             |
             +-- HTTP work continues in the background
             +-- main can initiate other requests

Two asynchronous requests:
  sendAsync(A) -> futureA ---+
                            +--> allOf(A,B).get(...)
  sendAsync(B) -> futureB ---+
~~~

When using `BodyHandlers.ofString(StandardCharsets.UTF_8)`, the Future succeeds after the handler has collected the text body into a String. If switched to `BodyHandlers.ofInputStream()` or `ofPublisher()`, the Future can complete **before the body is finished being read**. This lab uses `ofString` so each scenario yields a complete result, but in real deployments you must bound body size; `ofString` can consume large amounts of RAM for unbounded responses.

### Synchronous Calls and Status Checks

~~~java
// Java 17+ snippet, request and client already created.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

if (response.statusCode() == 200) {
    System.out.println(response.body());
} else {
    System.out.println("Unexpected HTTP status: "
            + response.statusCode());
}
~~~

An HTTP 404/500 **does not cause `send()` to throw an IOException by default**: an error HTTP response can still be received successfully at the transport layer. Check the status, headers, and body according to your business protocol. Conversely, a connect failure, timeout, or TCP reset is typically an I/O error, and there may be no HttpResponse to read.

## 3. Using a Loopback Server for Real Testing

Calling a public API can run into DNS, proxies, TLS, CAPTCHAs, rate limits, redirects, and changing cookie policies. To **reproducibly** test cancellation and concurrency behavior, you need to control the server yourself.

~~~java
// Java 17+ snippet, not a standalone program.
InetAddress loopback = InetAddress.getByAddress(
        new byte[]{127, 0, 0, 1});

HttpServer server = HttpServer.create(
        new InetSocketAddress(loopback, 0), 32);
ExecutorService workers = Executors.newFixedThreadPool(8);

server.createContext("/ping", exchange -> {
    // Send 200 and body PONG.
});
server.setExecutor(workers);
server.start();

int actualPort = server.getAddress().getPort();
~~~

- Bind `127.0.0.1`: accessible only on the local machine/test network namespace. Do not bind `0.0.0.0` for this lab.
- Port `0`: the operating system picks an ephemeral free port, avoiding collisions with ports already in use.
- `backlog=32` is not a limit of 32 concurrent requests; it relates to the TCP accept queue.
- An eight-thread executor allows both handlers to wait on the gate simultaneously without exhausting the worker pool.
- Every latch has a 5s timeout and is released in `finally` to prevent tests from hanging indefinitely.

The contexts:

| Path | Response | Used to test |
| --- | --- | --- |
| `/ping` | `200 PONG` | send() |
| `/async/one` | `200 ONE` after gate opens | sendAsync A |
| `/async/two` | `200 TWO` after gate opens | sendAsync B |
| `/cookie/set` | `Set-Cookie: labToken=abc123; Path=/cookie; HttpOnly` | cookie acceptance/storage |
| `/cookie/check` | body true/false based on Cookie header | cookie sent on matching path |
| `/outside` | body true/false based on Cookie header | cookie not sent outside path |
| `/cancel` | Waits on gate then attempts to return TOO_LATE | client cancellation while server is already working |

The lab uses plaintext HTTP over loopback with a **dummy token**; do not use this for production authentication. When handling real session cookies, HTTPS and appropriate security attributes/checks are required.

## 4. Creating HttpClient and Configuring Cookies

~~~java
// Java 17+ snippet.
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(3))
        .cookieHandler(jar)
        .build();
~~~

Meaning:

- `HttpClient.newBuilder().build()` creates a client reusable across many requests; a built HttpClient object is immutable in its configuration.
- `CookieManager(null, policy)` uses the default **in-memory** `CookieStore`, suitable for the lab; state in the store still mutates as responses arrive.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` is a JDK cookie policy that restricts which cookie origins are accepted.
- `cookieHandler(jar)` attaches the store/policy to a **specific client**. If you create a client **without** configuring a CookieHandler, you should not assume it automatically shares browser session cookies.
- `version(HTTP_1_1)` selects the HTTP/1.1 preference for the embedded JDK server experiment. Outside the lab, a version preference does not give a client HTTP/2 if the server does not support it.
- `connectTimeout(3s)` only governs opening a **new connection**. It does not guarantee that the entire request/body finishes within three seconds.
- `HttpRequest.Builder.timeout(Duration)` is set per request to bound the HTTP exchange per API contract.

**Java 17 does not have HttpClient.close()/shutdown()/AutoCloseable**. Do not write `try (HttpClient client = HttpClient.newHttpClient())` in code compiled with `--release 17`; those lifecycle APIs were introduced in Java 21. In Java 17, you must still handle streaming bodies, cancel outstanding requests when needed, and shut down **application-owned executors** separately.

### Avoid the Global Cookie Jar When Isolation Is Needed

`CookieHandler.setDefault(...)` alters the process-wide default for APIs that use the global handler, making tests prone to leaking state. With HttpClient, the builder is more explicit. Two separately created HttpClients **that share the same CookieManager object** can share cookies; create a separate cookie jar per user/test identity if isolation is the goal.

## 5. Sending Two Asynchronous Requests and Confirming Overlap

A weak test calls `sendAsync` twice and observes two responses. That does not necessarily prove concurrent execution, because request B might only start after A has finished if the code calls `join` in the wrong place.

This lab places a `CountDownLatch(2)` on the server side and a gate to let the handlers proceed:

~~~text
Client                                       Server (8 worker threads)

sendAsync(/async/one) --------------------> handler one
                                             BOTH_ASYNC.countDown() [1 remaining]
                                             RELEASE_ASYNC.await(...)

sendAsync(/async/two) --------------------> handler two
                                             BOTH_ASYNC.countDown() [0 remaining]
                                             RELEASE_ASYNC.await(...)

BOTH_ASYNC.await(5s) => true
RELEASE_ASYNC.countDown() ----------------> both handlers proceed
                                             one returns ONE, two returns TWO

CompletableFuture.allOf(one,two).get(5s)
=> both HttpResponse<String> completed
~~~

What proves overlap is `asyncBothReachedServer=true`: **both handlers entered the gate before being released**. It does not rely on an estimated `Thread.sleep`. With only a single server worker, the first handler could occupy the thread and prevent the second handler from starting, causing the gate to time out; this is why an adequately sized pool must be configured.

~~~java
// Java 17+ snippet; client, base, get(...), and latches already exist.
CompletableFuture<HttpResponse<String>> one =
        client.sendAsync(get(base, "/async/one"),
                HttpResponse.BodyHandlers.ofString(UTF8));

CompletableFuture<HttpResponse<String>> two =
        client.sendAsync(get(base, "/async/two"),
                HttpResponse.BodyHandlers.ofString(UTF8));

boolean bothReached = BOTH_ASYNC.await(5, TimeUnit.SECONDS);
RELEASE_ASYNC.countDown();
if (!bothReached) {
    throw new IllegalStateException("Requests did not overlap");
}
CompletableFuture.allOf(one, two).get(5, TimeUnit.SECONDS);
System.out.println(one.join().body());
System.out.println(two.join().body());
~~~

`CompletableFuture.allOf()` returns `CompletableFuture<Void>`, not a `List<HttpResponse>`. You still retrieve the result from each Future after completion. If one HTTP request fails, `allOf.get()` may throw `ExecutionException`; it **does not automatically cancel the other request**.

### Anti-pattern: Disguised Sequential Submission

~~~java
// Anti-pattern: request B is not created while waiting for request A.
String a = client.sendAsync(reqA, handler).join().body();
String b = client.sendAsync(reqB, handler).join().body();
~~~

Fix this by creating **both futures first**, then waiting on the combined results. When post-HTTP processing (parsing JSON, writing to a DB) runs in a separate stage, you must wait on the corresponding **processing futures** rather than just the response futures if the test requirement is end-to-end business completion.

## 6. CookieManager: Storing, Sending on Matching Path, Rejecting, and Isolating

When the server sends a response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: labToken=abc123; Path=/cookie; HttpOnly
Content-Type: text/plain; charset=UTF-8

COOKIE_SET
~~~

This is an example illustrating the key headers, **not a verbatim capture of every wire byte**. The CookieHandler in HttpClient can receive `Set-Cookie`, store the cookie according to its policy/store, and attach `Cookie` to subsequent requests if host/path/flags match.

Testing requires **two request round-trips**:

1. `GET /cookie/set` receives `Set-Cookie`.
2. `GET /cookie/check` verifies that the server actually sees `Cookie: labToken=abc123`.

Checking `CookieStore.getCookies()` alone is not enough: a cookie can be stored yet not sent due to Path, Domain, Secure, or expiry. This lab verifies both the store and the header received by the server.

| Scenario | Expected result |
| --- | --- |
| Jar ACCEPT_ORIGINAL_SERVER after /cookie/set | Cookie is present in the store |
| Same client calls /cookie/check | Cookie sent: path starts with /cookie/ |
| Same client calls /outside | labToken not sent due to Path=/cookie |
| New HttpClient without cookie handler | Does not send cookie from the old jar |
| New CookieManager ACCEPT_NONE | Does not store/send cookie from Set-Cookie |

~~~java
// Java 17+ snippet.
CookieManager rejectingJar = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);

HttpClient rejectingClient = HttpClient.newBuilder()
        .cookieHandler(rejectingJar)
        .build();
~~~

`CookieManager` has a `CookieStore` whose lifetime is managed by the application. By default this is an in-memory store; do not assume cookies survive a process restart. Two identities sharing a jar risk sharing sessions; use a separate cookie jar per user and do not log cookie values.

### Cookie Attributes and Security

| Attribute | Meaning | Practical note |
| --- | --- | --- |
| `Path=/cookie` | URL path scope where cookie is sent | Not a security boundary replacing authorization |
| `Domain` | Host/domain scope | Host-only and domain cookies differ |
| `Max-Age/Expires` | Cookie lifetime | Cookies can expire and do not live forever |
| `Secure` | Sent only in secure connection contexts per cookie policy | Lab uses loopback HTTP so Secure is not set |
| `HttpOnly` | Restricts access from browser JavaScript | Does **not** prevent a Java HTTP client from sending a valid cookie |
| `SameSite` | Browser cross-site behavior | Java CookieManager is **not a browser** and does not automatically enforce full browser CSRF semantics |

Do not confuse Path restriction with authorization. HTTPS, appropriate Secure/HttpOnly cookies, server-side session validation, session rotation, and CSRF protection remain necessary for user-facing systems. `CookiePolicy.ACCEPT_ALL` may be useful in special cases, but should not be chosen as the default for untrusted applications without a risk assessment.

## 7. Request Cancellation: Cancelling a Future Does Not Roll Back the Server

This is the trickiest point. According to the Java 17 Javadoc, the default HttpClient returns cancelable Futures. Calling `cancel(true)` on an **incomplete** HTTP Future causes the implementation to **attempt** to cancel the exchange and reclaim resources. There is no guarantee about when cancellation takes effect:

- HTTP/1.1 may abruptly close the TCP connection.
- HTTP/2 may reset the stream and sometimes the connection.
- The server may still have received the request, be actively working on it, or **have already committed a side effect**.
- Cancel is not a server-side transaction rollback protocol.

The lab deliberately has the server perform a simulated side effect before cancelling:

~~~text
Client                                       Server

sendAsync(GET /cancel) -------------------> handler enters /cancel
                                            SERVER_EFFECT.set(true)
                                            CANCEL_ENTERED.countDown()
                                            waits on RELEASE_CANCEL

CANCEL_ENTERED.await(5s) => true
SERVER_EFFECT.get()       => true
slow.cancel(true)
    |
    +-- Future reports exceptional/cancellation
    +-- Does not assert server rolled back

RELEASE_CANCEL.countDown() --------------> server attempts to reply TOO_LATE
                                            (socket may already be closed)
                                            CANCEL_FINISHED.countDown()

Client checks:
  serverEffectBeforeCancel=true
  cancelAccepted=true
  cancelFutureExceptional=true
  cancelOutcomeHasCancellation=true
  cancelHandlerFinished=true
~~~

Specifically, `SERVER_EFFECT.set(true)` executes **before** `CANCEL_ENTERED.countDown()`. Only after the client awaits the latch and sees true does it call `cancel(true)`. Thus, the statement "the server already performed the effect before cancel" is grounded in synchronization ordering, not scheduling luck.

### Why Can join() After Cancel Throw CompletionException?

With a plain `CompletableFuture`, cancellation is described as exceptional completion with `CancellationException`. However, the default Java HTTP client returns Futures that have internal dependent stages. In JDK 24 testing, `slow.cancel(true)` returned true while `slow.join()` threw **`CompletionException` wrapping `CancellationException`**. In a direct test, `slow.isCancelled()` even returned false despite `cancel(true)` returning true, because the Future represented the failure via a wrapper.

Therefore, **do not write tests that catch only CancellationException directly and assume every implementation behaves identically**:

~~~java
// Java 17+ snippet; slow is a cancelable HttpClient future.
boolean accepted = slow.cancel(true);
boolean cancellationObserved;
try {
    slow.join();
    cancellationObserved = false;
} catch (CancellationException e) {
    cancellationObserved = true;
} catch (CompletionException e) {
    cancellationObserved = hasCancellation(e); // Walk the cause chain.
}
~~~

The `hasCancellation(Throwable)` helper in the full program walks `Throwable.getCause()` looking for `CancellationException`. Note two things:

1. `cancel(true)` returning true is the outcome of the Future call; it does **not** mean the TCP packet never went out or that the server's side effect was undone.
2. `isDone()/isCompletedExceptionally()/isCancelled()` are **Future states**, not proof of server rollback. Do not use `isCancelled()` alone to prove a business transaction was stopped.

### Cancelling POST/PUT/PATCH in Production

Suppose a client sends a payment request and loses the response or cancels after the server already received it. Retrying without an **idempotency key** can create two transactions. You need a transaction status API, correlation IDs, deduplication, a transaction rollback policy, and logging/auditing. Do not retry blindly just because a Future completed exceptionally.

## 8. Complete Java 17+ Program: HttpClientLab.java

This file uses a loopback server and latches to establish deterministic test ordering. Every test performs real HTTP over a socket; it does not mock `HttpResponse` objects. This is a **self-contained** program requiring no additional project classes.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class HttpClientLab {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final CountDownLatch BOTH_ASYNC =
            new CountDownLatch(2);
    private static final CountDownLatch RELEASE_ASYNC =
            new CountDownLatch(1);
    private static final CountDownLatch CANCEL_ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch RELEASE_CANCEL =
            new CountDownLatch(1);
    private static final CountDownLatch CANCEL_FINISHED =
            new CountDownLatch(1);
    private static final AtomicBoolean SERVER_EFFECT =
            new AtomicBoolean(false);

    private static void reply(
            HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(UTF8);
        try (exchange) {
            try (InputStream in = exchange.getRequestBody()) {
                in.transferTo(OutputStream.nullOutputStream());
            }
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static void gated(
            HttpExchange exchange, String answer)
            throws IOException {
        BOTH_ASYNC.countDown();
        try {
            if (!RELEASE_ASYNC.await(5, TimeUnit.SECONDS)) {
                reply(exchange, 503, "GATE_TIMEOUT");
            } else {
                reply(exchange, 200, answer);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            reply(exchange, 503, "INTERRUPTED");
        }
    }

    private static void cancelHandler(HttpExchange exchange) {
        // Server side effect already occurred BEFORE client cancels.
        SERVER_EFFECT.set(true);
        CANCEL_ENTERED.countDown();

        try {
            if (RELEASE_CANCEL.await(5, TimeUnit.SECONDS)) {
                reply(exchange, 200, "TOO_LATE");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (IOException e) {
            // Client may close the HTTP/1.1 connection on cancel.
        } finally {
            exchange.close();
            CANCEL_FINISHED.countDown();
        }
    }

    private static void checkCookie(HttpExchange exchange)
            throws IOException {
        String cookie = exchange.getRequestHeaders()
                .getFirst("Cookie");
        boolean present = cookie != null
                && cookie.contains("labToken=abc123");
        reply(exchange, 200, Boolean.toString(present));
    }

    private static HttpRequest get(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(10))
                .GET().build();
    }

    private static HttpResponse<String> send(
            HttpClient client, HttpRequest request)
            throws IOException, InterruptedException {
        return client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));
    }

    private static boolean hasCancellation(Throwable failure) {
        for (Throwable e = failure; e != null; e = e.getCause()) {
            if (e instanceof CancellationException) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 32);
        ExecutorService workers =
                Executors.newFixedThreadPool(8);

        server.createContext("/ping",
                exchange -> reply(exchange, 200, "PONG"));
        server.createContext("/async/one",
                exchange -> gated(exchange, "ONE"));
        server.createContext("/async/two",
                exchange -> gated(exchange, "TWO"));
        server.createContext("/cookie/set", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "labToken=abc123; Path=/cookie; HttpOnly");
            reply(exchange, 200, "COOKIE_SET");
        });
        server.createContext("/cookie/check",
                HttpClientLab::checkCookie);
        server.createContext("/outside",
                HttpClientLab::checkCookie);
        server.createContext("/cancel",
                HttpClientLab::cancelHandler);
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            CookieManager jar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .cookieHandler(jar)
                    .build();

            // 1. Blocking send.
            HttpResponse<String> sync =
                    send(client, get(base, "/ping"));
            System.out.println("syncStatus=" + sync.statusCode());
            System.out.println("syncBody=" + sync.body());

            // 2. Two async requests, gated at the server.
            CompletableFuture<HttpResponse<String>> one =
                    client.sendAsync(
                            get(base, "/async/one"),
                            HttpResponse.BodyHandlers.ofString(UTF8));
            CompletableFuture<HttpResponse<String>> two =
                    client.sendAsync(
                            get(base, "/async/two"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            boolean bothReached = BOTH_ASYNC.await(
                    5, TimeUnit.SECONDS);
            RELEASE_ASYNC.countDown();
            if (!bothReached) {
                throw new IllegalStateException(
                        "Async handlers did not overlap");
            }
            CompletableFuture.allOf(one, two)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("asyncBothReachedServer=" + bothReached);
            System.out.println("asyncOne=" + one.join().body());
            System.out.println("asyncTwo=" + two.join().body());

            // 3. CookieManager accepts/stores/sends on matching Path.
            HttpResponse<String> cookieSet =
                    send(client, get(base, "/cookie/set"));
            boolean stored = jar.getCookieStore().getCookies()
                    .stream().map(HttpCookie::getName)
                    .anyMatch("labToken"::equals);
            boolean matchingPath = Boolean.parseBoolean(
                    send(client, get(base, "/cookie/check")).body());
            boolean outsidePath = Boolean.parseBoolean(
                    send(client, get(base, "/outside")).body());

            HttpClient noCookies = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            boolean withoutHandler = Boolean.parseBoolean(
                    send(noCookies, get(base, "/cookie/check")).body());

            CookieManager rejectingJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_NONE);
            HttpClient rejectingClient = HttpClient.newBuilder()
                    .cookieHandler(rejectingJar)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            send(rejectingClient, get(base, "/cookie/set"));
            boolean rejected = rejectingJar.getCookieStore()
                    .getCookies().isEmpty()
                    && !Boolean.parseBoolean(
                            send(rejectingClient,
                                    get(base, "/cookie/check")).body());

            System.out.println("cookieSetStatus="
                    + cookieSet.statusCode());
            System.out.println("cookieStored=" + stored);
            System.out.println("cookieOnMatchingPath=" + matchingPath);
            System.out.println("cookieOutsidePathAbsent="
                    + !outsidePath);
            System.out.println("cookieWithoutHandlerAbsent="
                    + !withoutHandler);
            System.out.println("cookieRejectedByPolicy="
                    + rejected);

            // 4. Cancel after server has entered the handler.
            CompletableFuture<HttpResponse<String>> slow =
                    client.sendAsync(
                            get(base, "/cancel"),
                            HttpResponse.BodyHandlers.ofString(UTF8));
            boolean entered = CANCEL_ENTERED.await(
                    5, TimeUnit.SECONDS);
            if (!entered) {
                throw new IllegalStateException(
                        "Cancel endpoint not reached");
            }
            boolean sideEffect = SERVER_EFFECT.get();
            boolean accepted = slow.cancel(true);
            boolean cancelledInCause;

            try {
                slow.join();
                cancelledInCause = false;
            } catch (CancellationException e) {
                cancelledInCause = true;
            } catch (CompletionException e) {
                cancelledInCause = hasCancellation(e);
            }

            RELEASE_CANCEL.countDown();
            boolean handlerFinished = CANCEL_FINISHED.await(
                    5, TimeUnit.SECONDS);

            System.out.println("cancelHandlerReached=" + entered);
            System.out.println("serverEffectBeforeCancel="
                    + sideEffect);
            System.out.println("cancelAccepted=" + accepted);
            System.out.println("cancelFutureDone=" + slow.isDone());
            System.out.println("cancelFutureExceptional="
                    + slow.isCompletedExceptionally());
            System.out.println("cancelOutcomeHasCancellation="
                    + cancelledInCause);
            System.out.println("cancelHandlerFinished="
                    + handlerFinished);
        } finally {
            RELEASE_ASYNC.countDown();
            RELEASE_CANCEL.countDown();
            server.stop(0);
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

### How to Compile and Run on Java 17+

~~~bash
javac --release 17 HttpClientLab.java
java HttpClientLab
~~~

In an application using `module-info.java`, you need `requires java.net.http; requires jdk.httpserver;`. A standard classpath program on a full JDK resolves both modules automatically. The file name must match `public class HttpClientLab`.

### Stdout Verified Three Times on JDK 24

~~~text
syncStatus=200
syncBody=PONG
asyncBothReachedServer=true
asyncOne=ONE
asyncTwo=TWO
cookieSetStatus=200
cookieStored=true
cookieOnMatchingPath=true
cookieOutsidePathAbsent=true
cookieWithoutHandlerAbsent=true
cookieRejectedByPolicy=true
cancelHandlerReached=true
serverEffectBeforeCancel=true
cancelAccepted=true
cancelFutureDone=true
cancelFutureExceptional=true
cancelOutcomeHasCancellation=true
cancelHandlerFinished=true
~~~

All 18 lines above were observed across **three consecutive runs** over loopback with code compiled via `javac --release 17`. These are **environment-specific test results**, not a guarantee of identical cancellation scheduling or connection cleanup across every JDK, provider, or OS. A socket-constrained environment or heavy system load can cause timeouts, IOExceptions, or different race conditions.

### Why Doesn't the Code Print "Future.isCancelled() Guaranteed True"?

In a separate verification run, the HttpClient Future produced `cancel(true)==true`, `isDone()==true`, `isCompletedExceptionally()==true`, yet `isCancelled()==false`, and `join()` threw `CompletionException` with a cause chain containing `CancellationException`. That is why we check the **cancellation outcome** rather than binding to a single exception type or boolean across all HTTP implementations.

### Verifying Output Meaning by Case

- The two lines `syncStatus=200` and `syncBody=PONG`: prove the blocking HTTP request completed validly.
- `asyncBothReachedServer=true`, `asyncOne=ONE`, `asyncTwo=TWO`: prove both handlers entered the server before the gate opened and both responses were received.
- The six cookie lines: prove the server issued the cookie, the jar received it, sent it on the matching path, did not send it outside the path, a client without a jar did not share it, and the ACCEPT_NONE policy rejected it.
- The seven cancel lines: the server executed the simulated effect before cancel; the client marked the Future as exceptional/cancelled, and the server handler finished once the gate opened. No line claims the server side effect was rolled back.

## 9. Rules for Using CompletableFuture Correctly in Async Tests

`CompletableFuture` offers several ways to wait and compose:

| API | Purpose | Note |
| --- | --- | --- |
| `future.get()` | Waits, returns result or throws checked exceptions | Can block indefinitely without a deadline |
| `future.get(timeout, unit)` | Bounds how long the calling thread waits | Timeout **does not automatically cancel** the HTTP exchange |
| `future.join()` | Waits, uses unchecked CompletionException | May throw CancellationException directly |
| `thenApply()` | Transforms the result on success | Callback may run on the thread completing the stage |
| `thenCompose()` | Chains another asynchronous stage | Suitable for dependent HTTP/request-processing pipelines |
| `whenComplete()` | Observes success/failure | Does not swallow or suppress errors |
| `exceptionally()` | Recovers/falls back on error | Must not silently swallow critical transaction errors |
| `allOf(a,b)` | Waits for multiple futures to finish | Does not collect results or auto-cancel other futures |
| `orTimeout(d,unit)` | Completes Future exceptionally on timeout | Does not equate to cancelling network I/O |
| `cancel(true)` | Attempts to cancel HTTP exchange on a cancelable HttpClient future | Best-effort; does not roll back the server |

Safe callback handling example:

~~~java
// Snippet: future is already a CompletableFuture<HttpResponse<String>>.
CompletableFuture<String> bodyFuture =
        future.thenApply(HttpResponse::body);

bodyFuture.whenComplete((body, failure) -> {
    if (failure != null) {
        reportFailure(failure); // Application-defined helper.
    } else {
        recordBody(body);       // Application-defined helper.
    }
});
~~~

Do not perform long-blocking DB work inside a callback without considering the executor/thread pool; `thenApply/whenComplete` can run on the completion thread or the caller thread. If offloading is needed, use `thenApplyAsync(..., boundedExecutor)` and **manage the executor's lifecycle separately**.

## 10. Timeout Differs from Cancellation, and Both Differ from Server Rollback

Distinguish clearly:

| Mechanism | Boundary | What it does NOT guarantee |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Establishing a new connection | Not a total request deadline |
| `HttpRequest.Builder.timeout(Duration)` | HTTP exchange per request contract | Does not prove the server did not process on timeout |
| `future.get(2,SECONDS)` | Calling thread waits at most 2s | HTTP may still be running |
| `future.orTimeout(2,SECONDS)` | Future fails exceptionally if unfinished | Network is not necessarily cancelled |
| `future.cancel(true)` | Best-effort attempt to cancel exchange | Server may have already received and committed |
| `Thread.interrupt()` during `send()` | Interrupts blocking call; default client tries to cancel | Does not guarantee peer abort/rollback |
| `InputStream.close()` | Closes a streaming response body | Does not undo a request already sent |

~~~java
// Java 17+ snippet: explicitly decide to cancel when wait times out.
try {
    HttpResponse<String> response =
            future.get(2, TimeUnit.SECONDS);
    handleResponse(response);
} catch (TimeoutException e) {
    future.cancel(true);
    recordTimeout(e);
}
~~~

`handleResponse/recordTimeout` are application helpers. `get(timeout)` throwing `TimeoutException` only means the **waiting thread** did not receive a result in time; it does not mean the request failed on the server. `orTimeout` is a completion-stage timeout and likewise does not replace a server transaction. If the body is consumed as an `InputStream`, you also need a deadline/cleanup **while reading the body**, not only when the response Future completes.

If a handler sends a POST request to create an order and the Future is cancelled, the server may still have created the order. You need an **idempotency key**, a status-query endpoint, correlation IDs, and an appropriate retry policy.

## 11. Why Cancelling a Future in a Stage Chain Can Be Misleading

A single request can spawn multiple units of work:

~~~text
HttpClient.sendAsync(req)
     |
     +--> responseFuture
                 |
                 +--> thenApply(parseJson) --> parseFuture
                 |
                 +--> thenCompose(saveDb)  --> processingFuture
~~~

Cancelling `processingFuture` does not mean you directly cancelled the HTTP exchange or rolled back the DB operation. Cancelling `responseFuture` after data has been sent does not erase server side effects. When shutting down a service, you must track **root futures, dependent futures, and body streams**; cancellation, retry, and cleanup must follow ownership.

An anti-pattern:

~~~java
// Do not use this pattern for payment operations with side effects.
CompletableFuture<HttpResponse<String>> pay =
        client.sendAsync(paymentRequest,
                HttpResponse.BodyHandlers.ofString());

pay.cancel(true);
retryWithoutIdempotencyKey(); // Risk of duplicate payment/transaction.
~~~

This is a snippet illustrating a design flaw; `retryWithoutIdempotencyKey()` is a hypothetical helper. For POST/PUT/PATCH, you must understand the API semantics and transaction state before retrying.

## 12. Negative Tests and Edge Cases to Add

The main program demonstrates four requirement groups. When building a real test suite, expand with the following cases (the cases in the table are **test recommendations**, not claims of what ran in stdout):

| Case | How to execute | Contract expectation |
| --- | --- | --- |
| HTTP 404 | GET a nonexistent path | Receive HttpResponse with status 404 when transport succeeds |
| Method 405 | Handler checks GET/POST, returns 405 | `send` still returns HttpResponse with status=405 |
| Async 503 | A handler returns 503 | Future may complete normally with a 503 response |
| Connection drop | Server closes socket abruptly | Future completes exceptionally / IOException |
| Connect timeout | Point to an appropriate IP/port to simulate timeout | Classify `HttpConnectTimeoutException` when it genuinely occurs |
| Request timeout | Handler holds response past the request deadline | Times out per API, does not assume server rollback |
| Gate never opened | Hold server latch until the 5s timeout | Handler returns error response or client times out |
| Cookie expired | Set-Cookie with Max-Age=0 | Cookie is no longer sent per policy |
| Cookie Domain/Path mismatch | Vary cookie attributes | Cookie is sent according to scope, not to every URI |
| Secure cookie over HTTP | Set Secure but send http:// request | Cookie is not transmitted over plaintext per policy |
| Shared cookie jar | Two HttpClients point to the same CookieManager | Cookies can be shared |
| Separate cookie jars | Each client has its own CookieManager | No state leakage between clients |
| Cancel before server starts | Cancel immediately after sendAsync | Valid race; server may or may not have received it |
| Cancel after side effect | Gate in the same order as the lab | Side effect that already occurred still persists |
| Cancel after Future succeeds | Call cancel on an already completed Future | Does not cancel the completed result |
| Cancel with streaming BodyHandler | Read part of InputStream then close | Must clean up body; do not treat response as complete |
| 1-worker thread pool | Use 1 thread for two gated handlers | Risk of test starvation/deadlock |
| Concurrent stress | Many requests with a bounded queue | Manage deadlines, resources, and errors |

**Do not write tests asserting that the server must throw an IOException after cancel.** Connection closure and error timing on the server depend on transport/OS/JDK; what you can prove is that the server entered the handler before cancellation, and the client Future has the appropriate cancellation/exceptional outcome.

## 13. Moving from Stdout to Assertions

The program uses readable booleans for teaching. When integrating into CI, convert conditions into assertions so tests **genuinely fail** when expected behavior is not met.

~~~java
// Java 17+ snippet: add to the same class if desired.
private static void require(boolean condition, String label) {
    if (!condition) {
        throw new AssertionError(label);
    }
}

// Usage after obtaining the variables from the program:
require(sync.statusCode() == 200, "Sync status");
require("PONG".equals(sync.body()), "Sync body");
require(bothReached, "Async handlers did not overlap");
require(stored && matchingPath && !outsidePath,
        "Cookie path behavior");
require(!withoutHandler && rejected,
        "Cookie isolation and reject policy");
require(entered && sideEffect,
        "Server acted before cancellation");
require(accepted && cancelledInCause,
        "Cancellation outcome");
require(handlerFinished, "Server-side cleanup");
~~~

This is a supplementary snippet (not a new standalone class); when using it, place it where the variables are in scope. With multi-test JUnit 5 suites, avoid sharing static mutable `CountDownLatch` instances across tests: each test/setup should create its own server, latches, and `CookieManager`. Use port 0 and `finally` cleanup to avoid leaking threads/connections.

### Why Is the Server Request Body Drained?

The `reply()` helper reads the request body before returning the response, then closes streams via `try-with-resources`. In the lab, GET bodies are empty and all requests are controlled; on a public server, you should not blindly `transferTo(nullOutputStream())` unboundedly on untrusted requests. You need byte limits, read deadlines, slow-client protection, and 413 responses if payloads are too large. The demo server is loopback-only, not a public HTTP service.

### Why Must Gates Be Released in finally?

If a test throws an exception before releasing a latch, a waiting handler can hold a worker thread until it times out. The main program always calls:

~~~java
RELEASE_ASYNC.countDown();
RELEASE_CANCEL.countDown();
server.stop(0);
workers.shutdownNow();
workers.awaitTermination(5, TimeUnit.SECONDS);
~~~

This is a `finally` snippet, not a standalone runnable block. It bounds the **test server's** resources. `shutdownNow()` is only an attempt to interrupt worker threads; it must not be interpreted as all server work having completed transactionally.

## 14. Common Errors When Running the Lab

| Symptom | Cause | Fix |
| --- | --- | --- |
| GUI/event loop freezes | Calling `send()` on an interactive thread | Move I/O to a worker or use `sendAsync` |
| Two `sendAsync` calls not concurrent | Creating Future 2 after joining Future 1 | Create both before waiting |
| Gate timeout | Server pool too small, request failed/slow network | Sufficient worker threads, clear timeouts, and `finally` release |
| `CompletableFuture.join()` throws wrapper | Underlying request failed or was cancelled | Inspect `CompletionException`/cause chain |
| 503 response treated as success | Checking only that the Future succeeded | Check `statusCode` and business schema |
| Cookie missing | No CookieHandler attached or Path/Domain/Secure mismatch | Configure jar and inspect Set-Cookie/headers |
| CookieStore has cookie but server does not see it | Request is outside cookie scope | Check Path/Domain/Secure and expiry |
| Cookies leak across tests | Sharing a single CookieManager | Create a fresh jar per test/identity |
| Misunderstood `HttpOnly` | Assuming Java client will not send HttpOnly cookies | HttpOnly primarily restricts browser JS |
| Misunderstood `SameSite` | Treating CookieManager like a browser | Test browsers and CSRF separately |
| Cancel true but server still processes | Best-effort; request already reached server | Idempotency/status API and dedicated business logic |
| `isCancelled()==false` after cancel | HTTP Future completed exceptionally via a wrapper | Check `isCompletedExceptionally` and exception cause |
| `get` times out but request still runs | `get(timeout)` does not cancel HTTP | Cancel explicitly and clean up body/resources |
| Closing stream too early | `BodyHandler.ofInputStream` not yet at EOF | Read to completion or close per policy, report partial |
| Java 17 reports HttpClient not AutoCloseable | Using Java 21 API | Do not use try-with-resources on HttpClient on Java 17 |
| JVM stays alive after test | Executor/handler latch not released | Release in `finally`, stop server, shut down executor |
| GET 404 makes app throw IllegalStateException | Application policy explicitly checks status | Distinguish HTTP status from transport exceptions |
| Cancelling POST then retrying creates duplicates | Server committed before cancel | Idempotency key, correlation ID |
| Unstable tests over the Internet | Changing DNS/rate limits/proxies | Loopback server with deterministic fixtures |

## 15. Security and Reliability in Real-World Applications

This is a **Java client experiment**, not a production cookie authentication system. When applying to real systems:

- **Always use HTTPS** for tokens/session cookies and keep certificate/hostname verification enabled. Never use an accept-all `TrustManager` to "fix" TLS errors.
- **Cookie scope/ownership:** give each user/test its own jar when isolation is needed; control Path/Domain/Expires/Max-Age/Secure/HttpOnly, while still enforcing authorization on the server.
- **Browser vs Java client:** `CookieManager` does not automatically enforce full browser SameSite, CORS/CSRF, and privacy policies.
- **Do not log session tokens** or raw Authorization/Cookie headers. Correlation IDs and route templates are more useful for logging/metrics.
- **Bound pending requests:** limit concurrency, thread pools, queues, deadlines, and byte sizes; handle errors and cancellation according to ownership.
- **Consistent retry policy:** distinguish idempotent GETs from requests with side effects; do not infer rollback from Future cancellation.
- **Body cleanup:** with `ofInputStream/ofPublisher/ofLines`, consume fully or close/cancel properly. Future completion does not automatically consume the body for streaming handlers.
- **Lifecycle:** reuse a long-lived HttpClient when appropriate, manage CookieManager/stores separately, shut down application-owned executors, and resolve outstanding Futures.
- **Accurate observability:** log HTTP status, latency, cancellation attempts, outcome/cause, and server requestId; do not report "the server did nothing" merely because the client received no response.
- **Realistic testing:** add cases for timeouts, redirects, proxies, TLS, expired cookies, cancellation races, and lost responses in integration tests.

## 16. Self-Check Questions

**Question 1.** What is the main difference between `send` and `sendAsync`?  
**Answer:** `send` blocks the calling thread and returns `HttpResponse`; `sendAsync` returns a `CompletableFuture` immediately, allowing multiple requests to be composed.

**Question 2.** Does creating two Futures first and calling `allOf` prove the HTTP handlers ran concurrently?  
**Answer:** It does not by itself prove overlap on the server; the lab uses a `CountDownLatch` in both handlers to confirm it.

**Question 3.** Why is a multi-threaded server pool needed in the gate test?  
**Answer:** With only one handler thread, the first handler waits on the gate and prevents the second handler from starting, causing starvation/test timeout.

**Question 4.** Does `CompletableFuture.allOf(a,b)` return two `HttpResponse` objects?  
**Answer:** No, it returns `CompletableFuture<Void>`; retrieve `a.join()/b.join()` after completion.

**Question 5.** Does HTTP 404 force `send()` to throw an `IOException`?  
**Answer:** No. HTTP status and network errors are two different layers; inspect `statusCode`.

**Question 6.** How do you attach cookie management to a Java `HttpClient`?  
**Answer:** Use `HttpClient.Builder.cookieHandler(CookieManager)` before building.

**Question 7.** What does `CookiePolicy.ACCEPT_NONE` do?  
**Answer:** It rejects cookies sent by the server; in the lab the store remains empty and subsequent requests do not send `labToken`.

**Question 8.** Once `Set-Cookie` is received, is it guaranteed the server will receive the cookie back?  
**Answer:** No. You must send a subsequent request and verify the server receives the `Cookie` header according to path/policy.

**Question 9.** Does `Path=/cookie` protect a cookie from every script/endpoint on the same origin?  
**Answer:** No. `Path` is an HTTP cookie sending scope, not an authorization boundary.

**Question 10.** Do two `HttpClient` instances using the same `CookieManager` isolate cookies?  
**Answer:** No; they intentionally share the same mutable jar and can share cookies.

**Question 11.** Does `HttpOnly` forbid Java's `CookieManager` from sending a cookie?  
**Answer:** No. `HttpOnly` primarily prevents browser JavaScript from accessing the cookie; it does not replace TLS or authorization.

**Question 12.** Does Java's `CookieManager` guarantee browser `SameSite` behavior?  
**Answer:** Do not assume so; test browsers and design your CSRF policy separately.

**Question 13.** Does `cancel(true)` prove the request never reached the server?  
**Answer:** No. Cancel is an attempt; the request may already have been sent or the server may have completed a side effect.

**Question 14.** Why does the lab set `SERVER_EFFECT` before `CANCEL_ENTERED.countDown`?  
**Answer:** So the client is guaranteed the server already performed the simulated effect before calling cancel, via latch synchronization ordering.

**Question 15.** After cancel, what exceptions can `join()` throw?  
**Answer:** `CancellationException` directly or `CompletionException` with a `CancellationException` cause (observed on JDK 24).

**Question 16.** Does `slow.isCancelled()==false` prove the HTTP request was not cancelled?  
**Answer:** No. An HTTP Future may complete exceptionally via a wrapper; check the outcome/cause and remember cancellation does not roll back the server.

**Question 17.** Does a `future.get(2,SECONDS)` timeout automatically cancel the HTTP request?  
**Answer:** No. It only limits how long the thread waits.

**Question 18.** Does `BodyHandlers.ofInputStream()` Future completion mean the entire body has been read?  
**Answer:** No. You must read the stream to EOF or close/cancel it according to policy.

**Question 19.** Is Java 17 `HttpClient` `AutoCloseable`?  
**Answer:** No; `HttpClient` gained `close`/`shutdown` in Java 21. Java 17 still requires cleaning up bodies/executors.

**Question 20.** Why is cancelling a payment POST and retrying without a key error-prone?  
**Answer:** The server may have already committed the transaction; retrying can create duplicate transactions, so idempotency/status checks are needed.

**Question 21.** Why must gates be counted down in `finally`?  
**Answer:** To release waiting handlers if a test fails, avoiding holding worker threads until timeout.

**Question 22.** How do you test async timeouts without depending on fixed scheduling?  
**Answer:** Use a gate/latch on the server, bounded deadlines, and outcome classification; do not use `Thread.sleep` as the sole proof.

## 17. Official References

- Oracle Java SE 17 — `HttpClient`, send/sendAsync/cancel notes: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpClient.Builder`, cookieHandler/connectTimeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Oracle Java SE 17 — `HttpRequest.Builder`, timeout/URI/method: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Oracle Java SE 17 — `HttpResponse`, BodyHandlers, status/body: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `CompletableFuture`, allOf/get/join/cancel/orTimeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 17 — `CookieManager`, cookie policy/store: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html
- Oracle Java SE 17 — `CookiePolicy` ACCEPT_NONE/ACCEPT_ORIGINAL_SERVER: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html
- Oracle Java SE 17 — `CookieStore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html
- Oracle Java SE 17 — `HttpCookie` attributes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html
- Oracle Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 17 — `HttpServer` fixture: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 — `HttpExchange` request/response streams/headers: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html