# Coordinating Multiple Independent Requests with allOf While Preserving Each Request's Result

## 1. The Problem and the Fan-Out / Fan-In Idea

A Java service needs to call three independent HTTP endpoints: fetching configuration, fetching a profile, and fetching an order status. If it calls `HttpClient.send(...)` sequentially or calls `sendAsync(...).join()` immediately each time, the application waits for one request to finish before starting the next. When requests **have no data dependencies on each other**, we can start all of them first and then wait for the group to complete.

The pattern consists of three steps:

1. **Fan-out:** initiate multiple requests with `HttpClient.sendAsync(...)`, storing **each `CompletableFuture<HttpResponse<T>>`** under its exact request name or ID.
2. **Barrier:** create `CompletableFuture.allOf(...)` to know **when all input futures have completed**.
3. **Fan-in:** read each stored future by ID, extract its status/body or error, and aggregate a structured result.

~~~text
                      fan-out
client ---> sendAsync(A) ---> futureA ----\
       \-> sendAsync(B) ---> futureB -----+--> allOf(A,B,C) -- barrier
       \-> sendAsync(C) ---> futureC ----/          |
                                                   v
                                   fan-in: read A, B, C by initial ID
                                                   |
                                                   v
                                        List/Map<requestId, Outcome>
~~~

**Key point: `allOf` does not hold the responses for you.** It only synchronizes the completion point. Each request needs its own future and its own identity. If one request fails, the data from the successful requests **does not vanish on its own**, but you must handle errors properly so you do not accidentally skip them.

This article uses Java 17+ and `java.net.http.HttpClient`. Both complete runnable programs create an HTTP server directly on `127.0.0.1` using `com.sun.net.httpserver.HttpServer`, without depending on the Internet or service accounts.

## 2. How Do the Return Types of sendAsync and allOf Differ?

| Method | Return type | Role |
| --- | --- | --- |
| `client.sendAsync(request, bodyHandler)` | `CompletableFuture<HttpResponse<T>>` | Carries the response of **one** HTTP request |
| `response.statusCode()` | `int` | HTTP status, including 4xx/5xx |
| `response.body()` | `T` | Body according to the chosen `BodyHandler<T>` |
| `CompletableFuture.allOf(f1,f2,...)` | `CompletableFuture<Void>` | Completes when **all input futures complete** |
| `future.join()` | `T` on success; may throw `CompletionException` | Reads the result of a future |
| `future.get()` | `T` on success; throws checked exceptions on error | Reads/waits for the result of a future |
| `future.handle((value,error)->...)` | `CompletableFuture<U>` | Normalizes **both success and error branches** |
| `future.thenApply(value->...)` | `CompletableFuture<U>` | Transforms the value when upstream succeeds |

In the case of `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)`, each future from `sendAsync` has the form `CompletableFuture<HttpResponse<String>>`. The response contains the status, headers, and String body processed by the body handler. With a **streaming** body handler such as `ofInputStream()`, the future can complete when the stream is ready even though the application still has to read/close that stream afterward.

Important API signature:

~~~java
public static CompletableFuture<Void> allOf(
        CompletableFuture<?>... cfs)
~~~

*This is an illustrative signature of `CompletableFuture.allOf` in the JDK, not a method you need to implement yourself.*

`Void` here means: the barrier **does not return a List of the child results**. When `allOf` succeeds, `join()` on the barrier evaluates to `null`; the results must be retrieved from each `f1/f2/...`. If you want a `CompletableFuture<List<T>>`, you must **build the aggregation stage yourself** from the child futures after the barrier.

## 3. Common Mistake: Joining Too Early Makes the Program Sequential

An example you **should not write** if A, B, and C are independent:

~~~java
HttpResponse<String> a =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString()).join();
HttpResponse<String> b =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString()).join();
HttpResponse<String> c =
        client.sendAsync(requestC, HttpResponse.BodyHandlers.ofString()).join();
~~~

*Illustrative snippet inside a class that already has `client` and three requests, not a standalone runnable program.*

Even though the API is named `sendAsync`, on the first line the caller thread waits for A to complete **before calling `sendAsync` for B**. The total wait time can be close to the sum of the three requests.

Start first, wait later:

~~~java
CompletableFuture<HttpResponse<String>> fa =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fb =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fc =
        client.sendAsync(requestC, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all = CompletableFuture.allOf(fa, fb, fc);
all.join();

HttpResponse<String> a = fa.join();
HttpResponse<String> b = fb.join();
HttpResponse<String> c = fc.join();
~~~

*This illustrative snippet only fits the branch where **all requests succeed**. When any input future completes exceptionally, `all.join()` may throw an exception; how to preserve both good results and errors is presented below.*

Because `fa`, `fb`, and `fc` are created before `all.join()`, the requests **can execute concurrently**, subject to HTTP client, connection pool, and server limits. `allOf` **does not initiate new requests, does not create responses, and does not perform network I/O itself**; those operations were already triggered by `sendAsync`.

## 4. Does allOf Really Wait for Every Future? What About Error States?

According to the `CompletableFuture` Javadoc:

- `allOf` completes when **all** input futures complete.
- If one or more input futures **completed exceptionally**, the `allOf` future **also completes exceptionally**.
- `allOf` **does not return results itself** from the input futures.
- `CompletableFuture.allOf()` with no elements returns a future already completed normally with `null`.
- If the array or any future element is `null`, `allOf` throws `NullPointerException`.

Example:

~~~text
A: completed normally -> HttpResponse A
B: completed exceptionally -> IOException B
C: completed normally -> HttpResponse C

allOf(A,B,C): completed exceptionally when the group completes
A: still holds response A
B: still holds exception B
C: still holds response C
~~~

**Do not assume `allOf` is fail-fast and cancels all child futures when one future fails.** The other requests can continue running and complete. When multiple requests fail, do not rely on the exception type thrown by the barrier to know **every single error**; you must inspect each future or outcome.

An ill-typed statement:

~~~java
// Intentionally fails to compile: allOf returns CompletableFuture<Void>, not List.
CompletableFuture<List<HttpResponse<String>>> results =
        CompletableFuture.allOf(fa, fb, fc);
~~~

To turn the barrier into a future carrying a list, once you know all child futures succeeded:

~~~java
CompletableFuture<List<HttpResponse<String>>> combined =
        CompletableFuture.allOf(fa, fb, fc)
                .thenApply(ignored -> List.of(
                        fa.join(), fb.join(), fc.join()));
~~~

*The two snippets above are separate illustrations: the first is **intentionally ill-typed**, and the second assumes `fa/fb/fc` are already initialized and overall error handling is in place.*

`thenApply` will **not run** if the barrier completes exceptionally. This is suitable behavior for an **all-or-nothing** requirement, but it is not enough for an application that wants to **keep all successful results when one request fails**.

## 5. Preserving the Mapping Between Request Identity and Future

When three requests complete in the order `C,A,B`, we must not assign response C to request A just because C arrived first. Some approaches:

- **Parallel-indexed lists:** keep `List<String> names` and `List<CompletableFuture<HttpResponse<String>>> futures`, then read both by the same index.
- **Named object:** create `record NamedFuture(String id, CompletableFuture<HttpResponse<String>> future)` to place the identifier and the future in the same object.
- **Map by ID:** use `Map<String, CompletableFuture<...>>` if key lookup is more convenient. If print order matters, choose `LinkedHashMap` or sort explicitly as required; do not leave it to completion order.

These two statements are different:

~~~text
Start order:     profile -> orders -> settings
Completion order: settings -> profile -> orders

Output in input order: profile -> orders -> settings
Identity of each future: unchanged throughout the exchange
~~~

Do not let callbacks from multiple futures arbitrarily `add` into the same unsynchronized `ArrayList`: races, lost data, or unstable ordering can occur. Storing futures separately and aggregating after the barrier makes the results much easier to verify.

## 6. Standalone Java 17+ Example: allOf with Three Successful HTTP Requests

The program starts an HTTP server on loopback with three endpoints: `/alpha`, `/beta`, and `/gamma`. The server uses a three-thread pool so it can handle requests concurrently. The client initiates all three `sendAsync` calls in `stream().map(...)`, then `allOf`, and only then reads the responses in `names` order.

Create the file `HttpAllOfResultsDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class HttpAllOfResultsDemo {
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        try {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        server.setExecutor(handlers);
        server.createContext("/alpha", e -> reply(e, "ALPHA"));
        server.createContext("/beta", e -> reply(e, "BETA"));
        server.createContext("/gamma", e -> reply(e, "GAMMA"));
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            List<String> names = List.of("alpha", "beta", "gamma");

            List<CompletableFuture<HttpResponse<String>>> requests =
                    names.stream().map(name -> {
                        HttpRequest request = HttpRequest.newBuilder()
                                .uri(URI.create(base + "/" + name))
                                .timeout(Duration.ofSeconds(5))
                                .GET().build();
                        return client.sendAsync(request,
                                HttpResponse.BodyHandlers.ofString(
                                        StandardCharsets.UTF_8));
                    }).toList();

            CompletableFuture<Void> all = CompletableFuture.allOf(
                    requests.toArray(CompletableFuture<?>[]::new));
            all.get(8, TimeUnit.SECONDS);

            for (int i = 0; i < names.size(); i++) {
                HttpResponse<String> response = requests.get(i).join();
                System.out.println(names.get(i) + ": HTTP "
                        + response.statusCode() + " " + response.body());
            }
            System.out.println("result count: " + requests.size());
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac HttpAllOfResultsDemo.java
java HttpAllOfResultsDemo
~~~

Stdout:

~~~text
alpha: HTTP 200 ALPHA
beta: HTTP 200 BETA
gamma: HTTP 200 GAMMA
result count: 3
~~~

### Lines Worth Understanding

1. `HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0)` creates a **local** server, with port `0` so the OS assigns an available port automatically. The example requires no external network access.
2. `names.stream().map(...)` calls `sendAsync` three times **before waiting**. Each future holds the response for its corresponding endpoint.
3. `requests.toArray(CompletableFuture<?>[]::new)` supplies the array for the `allOf` varargs and compiles on Java 17.
4. `all.get(8, TimeUnit.SECONDS)` is the **calling thread's wait limit** for the barrier. If the group completes normally, execution continues. On timeout or error, the method can throw a checked exception; the demo is not a production failure-handling pattern.
5. After the barrier completes successfully, `requests.get(i).join()` reads the already-ready `HttpResponse<String>`; `statusCode()` and `body()` are accessed individually for each request.
6. The print order is `alpha, beta, gamma` **because of the `names` list**, not because the HTTP connections executed sequentially.
7. `server.stop(0)` and `handlers.shutdownNow()` clean up the demo server. A long-lived server needs a more appropriate graceful lifecycle.

If the `gamma` response finishes before `alpha`, the result is still attached to the right name because `i` is the request index at creation time, not the completion order.

## 7. Why Catching Only the allOf Error Is Not Enough for Best-Effort

Suppose one request encounters a network `IOException`. `allOf` can complete exceptionally, so:

~~~java
CompletableFuture.allOf(fa, fb, fc).join(); // May throw.
System.out.println(fa.join().body());       // May not reach here.
~~~

*The snippet above is an example of a logic bug in an application that does not catch exceptions.*

**The successful results of `fa`/`fc` still exist**; it is just that control flow has exited the code block intended to read them.

Two ways to preserve results:

- **Approach A:** catch `CompletionException` from `allOf`, then inspect each child future because the barrier has already completed; handle successful, exceptional, and cancelled futures separately. Useful when you must keep the original future and cause for each request.
- **Approach B (usually easier to aggregate):** attach `handle` to **each request** to turn it into an `Outcome` future that does not throw on request failure. Then call `allOf` on the `Outcome` futures and collect all statuses by label.

**Important note:** `allOf` only completes normally if every future **passed into it** completes normally. `handle` can turn a request error into an `Outcome.failure` value, but if the code inside `handle` itself throws, the new future is still exceptional. The handler should be short, low-risk, and never turn an error into a fake success.

## 8. How handle, thenApply, exceptionally, and whenComplete Differ

| Method | Success branch | Error branch | Use case |
| --- | --- | --- | --- |
| `thenApply(value -> result)` | Converts value `T` to `U` | Function does not run; error propagates to next stage | Parse JSON, check status, map DTO |
| `handle((value,error) -> outcome)` | Has `value`, `error == null` | Has `error`; returns failure Outcome | **Collect both successes and errors** |
| `exceptionally(error -> fallback)` | Keeps original value | Allows a fallback of the same data type | Provide a default, but avoid masking errors |
| `whenComplete((value,error) -> ...)` | Logs/records metrics | Logs/records metrics, does not recover from error | Observability/cleanup |
| `thenCompose(value -> futureB)` | Starts an operation depending on A's result | Function does not run if A fails | Request chain A → B |
| `thenCombine(other, (a,b) -> combined)` | Produces a value from two futures | If either dependency fails, no value is produced | Combine two results |
| `anyOf(...)` | Completes when one future finishes | Can also end with an error | Wait for the earliest result, **not all of them** |

With `handle`:

~~~java
CompletableFuture<Outcome> safe =
        httpFuture.handle((response, error) -> {
            if (error != null) {
                return Outcome.failed(requestId, error);
            }
            return Outcome.ok(
                    requestId, response.statusCode(), response.body());
        });
~~~

*This is **illustrative pseudocode**: `Outcome.ok/failed`, `httpFuture`, and `requestId` are defined by the application. The full program in section 9 implements a concrete record.*

Do not use `exceptionally(error -> "")` for all errors if an empty String can be a real successful response. Instead, store the request ID, success/status, and error explicitly. `whenComplete` is suitable for logging, but it does not turn an exceptional future into a normal one. If a heavy callback runs on the completion thread, it can delay other requests; consider `thenApplyAsync`/a bounded executor for CPU-intensive processing.

## 9. Java 17+ Example: allOf Still Preserves Two Results When the Third Request Fails

In the second example:

- `/first` returns `HTTP 200` and `FIRST`.
- `/unavailable` returns `HTTP 503` and `BUSY`.
- `/third` returns `HTTP 200` and `THIRD`.

**HTTP 503 is not a Java exception by itself.** Because the example wants to demonstrate a business error after the HTTP response arrives, the code **deliberately** throws `IllegalStateException("HTTP 503")` in `thenApply` if the status is not 200. Then `handle` converts each request into an `Outcome(name, success, detail)`, whether the request succeeded or failed.

Create the file `HttpAllOfOutcomesDemo.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class HttpAllOfOutcomesDemo {
    record Outcome(String name, boolean success, String detail) {}

    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        try {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    private static CompletableFuture<Outcome> fetch(
            HttpClient client, String base, String name) {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(base + "/" + name))
                .timeout(Duration.ofSeconds(5))
                .GET().build();
        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException(
                                "HTTP " + response.statusCode());
                    }
                    return response.body();
                })
                .handle((body, error) -> {
                    if (error != null) {
                        Throwable cause = error;
                        while (cause instanceof CompletionException
                                && cause.getCause() != null) {
                            cause = cause.getCause();
                        }
                        return new Outcome(name, false,
                                "ERROR " + cause.getMessage());
                    }
                    return new Outcome(name, true, "OK " + body);
                });
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        server.setExecutor(handlers);
        server.createContext("/first", e -> reply(e, 200, "FIRST"));
        server.createContext("/unavailable", e -> reply(e, 503, "BUSY"));
        server.createContext("/third", e -> reply(e, 200, "THIRD"));
        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            List<String> names = List.of("first", "unavailable", "third");

            List<CompletableFuture<Outcome>> settled = names.stream()
                    .map(name -> fetch(client, base, name)).toList();
            CompletableFuture.allOf(
                    settled.toArray(CompletableFuture<?>[]::new))
                    .get(8, TimeUnit.SECONDS);

            List<Outcome> results = settled.stream()
                    .map(CompletableFuture::join).toList();
            for (Outcome result : results) {
                System.out.println(result.name() + ": " + result.detail());
            }
            long okCount = results.stream().filter(Outcome::success).count();
            System.out.println("success count: " + okCount);
        } finally {
            server.stop(0);
            handlers.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac HttpAllOfOutcomesDemo.java
java HttpAllOfOutcomesDemo
~~~

Stdout:

~~~text
first: OK FIRST
unavailable: ERROR HTTP 503
third: OK THIRD
success count: 2
~~~

### Why the Two Successful Results Are Not Lost

1. `names.stream()` calls `fetch` for all three names **before waiting on the barrier**.
2. `client.sendAsync(...)` returns the HTTP response; `thenApply` checks `statusCode`. HTTP 503 is converted into a stage error **by the application itself**.
3. `handle` runs whether upstream completes normally or exceptionally. It creates an `Outcome` with the `name` label and `success` flag, so every request produces a result value.
4. When a `CompletionException` wraps the error, the `while` loop unwraps the root cause to record a clear detail message. If the HTTP client hits a real network error, `handle` also receives the error and returns a failed Outcome.
5. `allOf` is called **on the list of futures that already have `handle`**, so in the demo they complete normally. A single business error no longer blocks access to the remaining Outcomes.
6. The `for` loop prints in `names` order. The number `success count: 2` is the result of **application policy**: two 200 statuses and one 503 status promoted to an error; it does not mean "the network only delivered two responses".

The demo stores `Outcome.detail` for easy printing rather than keeping the full `HttpResponse` of the 503 branch after throwing. For production error analysis, store **status, error body, cause, and latency** separately instead of a single string.

## 10. Designing an Informative Outcome to Retain Both HTTP Status and Network Errors

A production-friendly `Outcome` type can contain:

~~~text
Outcome(
    requestId,
    httpStatus = 200 / 503 / null if no HTTP response was ever received,
    body = String or null,
    error = Throwable or null,
    duration = processing duration
)
~~~

Important distinction: an **HTTP 503 response** error is different from a **TCP connect, DNS, TLS, or timeout** error. With `503`, the server did return an HTTP response, so the status and body information are still meaningful. If no response was received, only the exception/cause and wait metadata exist.

Pattern that preserves status/body whenever HTTP still returns a response:

~~~java
record Outcome(String id, Integer status, String body, Throwable error) {}

CompletableFuture<Outcome> future = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .handle((response, failure) -> {
            if (failure != null) {
                return new Outcome(requestId, null, null, failure);
            }
            return new Outcome(
                    requestId, response.statusCode(), response.body(), null);
        });
~~~

*This is an illustrative snippet inside a class that has `client`, `request`, and `requestId`; it is not a standalone runnable program. You should limit body size and avoid accidentally logging sensitive data.*

This approach does not turn HTTP 503 into a Java exception; it turns the status into retained data. The downstream business layer decides whether `status >= 500` should be retried or shown as a warning. If the client actually encounters an `IOException`, `failure != null` and there is no response.

**Bind the ID into Outcome when creating the future**, rather than relying on callback completion time to assign the ID. This is a key principle for preserving each request's result.

## 11. Distinguishing allOf from thenCompose, thenCombine, and anyOf

| Problem | Tool to consider | Notes |
| --- | --- | --- |
| Multiple **independent** requests, wait for **all of them** | `allOf` + keep futures | Fan-out/fan-in |
| Request B needs a token/ID from response A | `thenCompose` | Dependent chain; no simultaneous fan-out |
| Combine results of **two** futures into one value | `thenCombine` | Useful for two dependencies |
| Pick **one** future that completes first | `anyOf` | Does not collect results from the whole group |
| One future fails and needs a replacement value | `exceptionally` or `handle` | Do not mask errors with fake data |
| Want to log the status of each request | `whenComplete` | Observation only, does not recover from errors |
| Want a list of Outcomes for both successes and errors | `handle` per future + `allOf` | Classify results by request ID |

`allOf` is not a method that makes A/B/C run on three separate threads by itself. The HTTP client has its own asynchronous execution mechanism. `allOf` only expresses **a dependency on all input futures having completed**.

If the business requirement needs **only 2 out of 3 successful responses**, do not treat `allOf` as a quorum primitive: `allOf` waits for all three. You need a dedicated mechanism with a sufficient-result count condition, a timeout, and a cancellation policy for the remaining requests.

## 12. Per-Request Timeout vs. Barrier Timeout

The timeout layers are not equivalent:

| Configuration/operation | What does it limit? | Does it automatically cancel all child requests? |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Connection establishment time | No |
| `HttpRequest.Builder.timeout(Duration)` | Client-side HTTP request execution deadline | No, only the corresponding request |
| `all.get(8, TimeUnit.SECONDS)` | Time the calling thread **waits for the barrier** | **No** |
| `all.orTimeout(8, TimeUnit.SECONDS)` | Completes the **barrier future** itself exceptionally if overdue | No guarantee of cancelling each child |
| `child.cancel(true)` | Requests cancellation of a pending HTTP future | The HTTP client attempts to cancel the exchange; no guarantee of stopping server processing in time |

When `CompletableFuture.get(timeout)` times out, it throws `TimeoutException` without **cancelling the pending operations by default**. `CompletableFuture.orTimeout` modifies the state of the future it is called on; when called on the barrier, it does not reset the timeout of each HTTP request.

When you need a true overall deadline, decide explicitly: when time runs out, do you **return partial results**, let them continue in the background for logging, or request cancellation of each HTTP request? Even if you cancel, there is no guarantee the server has not already received and processed the request. For POSTs that create orders or transactions, you need an **idempotency key**, business-level ACK, and a careful retry policy.

In both demos, `all.get(8, TimeUnit.SECONDS)` only prevents tests from waiting indefinitely. A production version needs to catch `TimeoutException`, handle `ExecutionException`/`InterruptedException`, clean up futures/sockets, and decide how to handle already-received results.

## 13. Concurrency and Resource Limits for Large Lists

`allOf` does not limit the number of requests. If you write `ids.stream().map(id -> sendAsync(...)).toList()` for 20,000 IDs, the application can initiate a huge number of exchanges immediately. That introduces risks:

- Exhausting connections/sockets/file descriptors, saturating bandwidth, or hitting API quotas.
- `BodyHandlers.ofString` buffering too many large responses in RAM.
- Overloading the server with a sudden burst, causing HTTP 429/503 or timeouts.
- Heavy CPU work in `thenApply/handle` callbacks, affecting completion latency.
- Over-logging error payloads or sensitive response bodies.

**How to throttle:** run **bounded batches** or bounded concurrency with backpressure. For example, split the list into groups of N requests, initiate one batch, use `allOf` to collect outcomes, and only then initiate the next batch. N must be chosen based on workload/benchmarks and quotas; there is no default number that fits every system.

If using a `Semaphore`, avoid designing a task/thread that blocks just waiting for a permit for each ID; asynchronous coordination or a bounded executor/queue manages resources better. You must bound total bytes received, number of pending requests, and completion time, not just connection count.

Do not conclude that because the output prints alpha/beta/gamma, the three HTTP requests actually ran sequentially. To measure concurrency, use timestamps or measure server handling time; the example code intentionally prints **in input order** for deterministic output.

## 14. Protecting Results Against Races and Data Mutation

Several rules that make fan-in code easy to review:

1. **One request = one stable ID + one future.** Never assign results according to the order in which threads complete.
2. **Do not mutate the input collection** after creating futures, or use a record that binds the identity and the future in the same object.
3. **Do not use an unsynchronized shared mutable `ArrayList`** for callbacks from multiple futures. Aggregate from the original futures after the barrier, or choose a thread-safe structure.
4. **Classify success/error clearly:** HTTP 200, HTTP 503, IOException, timeout, and cancel are distinct states.
5. **Bound body size before accumulating too much.** HTTP 200 does not mean the payload is safe.
6. **Do not block for long in completion callbacks**; use a managed executor for heavy processing. A `handle` callback may run on the thread completing the future, not necessarily an application thread.
7. **Check `isDone()` carefully:** `true` covers normal, exceptional, and cancelled completions; it does not mean success. Use `isCompletedExceptionally()` and inspect the cause, or normalize with an Outcome.
8. **A single Throwable cannot replace full per-request logging** when multiple errors occur. Keep requestId, status, cause, and latency for each item.

## 15. Common Pitfalls and Fixes

| Pitfall | Why is it wrong? | How to fix |
| --- | --- | --- |
| `sendAsync(A).join()` before creating B | Accidentally sends sequentially | Create all futures before waiting |
| Assuming `allOf` returns a List | The barrier's result is `Void` | Keep child futures, build a separate List |
| Discarding child futures after creating allOf | Cannot access individual results | Store futures in a list/map/record |
| `all.join()` throws and skips two good results | Error aborts the aggregation flow | `handle` each future or catch and iterate |
| Believing allOf auto-cancels other requests | Javadoc makes no such guarantee | Cleanup/cancel according to policy |
| Assigning requests by whichever response finishes first | Wrong identity | Bind ID when sending |
| Synchronizing with an unprotected ArrayList | Races and corrupted data | Aggregate after the barrier |
| Treating HTTP 503 as a mandatory network error | An HTTP status is still a response | Check the status |
| `exceptionally(error -> "")` for all errors | Loses distinction from a valid empty response | Outcome carries explicit state |
| `all.get(timeout)` without handling child timeouts | Requests may still be running | Per-request timeouts/cancel |
| Launching thousands of requests unbounded | Overloads network/RAM/server | Batching, bounded concurrency |
| Buffering all large bodies with ofString | Can exhaust RAM | Limit bytes, stream/ofFile |
| Retrying the whole POST batch when one response fails | Can duplicate side effects | Business-level idempotency/ACK |
| Treating `thenCombine` like `allOf` for any N | thenCombine only pairs two and needs typed aggregation | Choose the model based on dependencies |
| Assuming an empty `allOf()` will wait | It completes normally right away | Handle empty input sets per contract |

## 16. Self-Check Questions

**Question 1.** What type does `CompletableFuture.allOf(fa,fb,fc)` return, and which responses does it contain?

*Answer:* It returns `CompletableFuture<Void>`; it contains no responses itself. You must read `fa/fb/fc` after the barrier completes or transform it into a future carrying a collection.

**Question 2.** B returns an error, while A and C succeed. `all.join()` throws an exception. Are the two results of A and C lost?

*Answer:* No. The data for A/C is still in their individual futures. The application must catch and aggregate each future or use `handle` on each future to produce an Outcome before `allOf`.

**Question 3.** Does `sendAsync(A).join()` followed by `sendAsync(B).join()` take advantage of the independence of A/B?

*Answer:* Not well. The calling thread waits for A to finish before B is initiated. You need to create futures for both first.

**Question 4.** Does an HTTP 503 response automatically make the `sendAsync` future exceptional?

*Answer:* Not solely because of status 503. A normal HTTP response can have status 503. The application must check the status itself and decide whether to treat it as a business error.

**Question 5.** Does a timeout on `all.get(3, SECONDS)` guarantee that the three HTTP requests stop?

*Answer:* No. That is the caller's wait limit; you need to cancel the child futures or let them continue according to policy, and never assume the server has not already created side effects.

**Question 6.** C finishes before A, while the initial list is A,B,C. Is it right to print C under label A because it arrived first?

*Answer:* Wrong. Identity must be bound when creating the request, and print order depends on output requirements. Results must never be assigned based on timing.

**Question 7.** How is `Outcome.failure` better than `exceptionally(error -> "")`?

*Answer:* It preserves a clear error indicator along with the ID/cause. An empty string can be a valid successful response, so using it as a fallback masks failures.

## 17. Practice Exercises

1. Run `HttpAllOfResultsDemo`, mark the line that **initiates** all three `sendAsync` calls, the **allOf barrier** line, and the lines that **read each future**. Change the order of `names` and verify the output still matches each ID.
2. Add `/delta` returning `DELTA`, add the name to the list, and verify `result count` increases from 3 to 4.
3. Run `HttpAllOfOutcomesDemo`, change `/unavailable` from 503 to 200; explain why `success count` becomes 3. Change it back to 503.
4. Write a richer Outcome containing `requestId`, `httpStatus`, `body`, `error`. Call `handle` directly on `sendAsync` to preserve the `BUSY` body of HTTP 503 as well.
5. Add a **simulated** `CompletableFuture.failedFuture(new IOException("test error"))` into a unit test group (do not treat this as a real HTTP response), and observe how raw `allOf` exceptional completion and `allOf` over Outcomes behave differently.
6. Call `CompletableFuture.allOf()` with no arguments and decide how to handle an empty input list according to the business contract.
7. Add per-request timeouts and a barrier timeout, then write a policy for cancellation, recording partial results, retries, and cleanup. Do not assume a barrier timeout has cancelled the children.
8. Split 100 requests into bounded batches, measure the in-flight count and accumulated body bytes; benchmark rather than inferring speed from log order.
9. Design a best-effort dashboard: display the successes of A/C, and the HTTP 503 of B along with its error body, duration, and cause, instead of failing the entire screen.

## Official API Documentation

- [`CompletableFuture` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `allOf`, `join`, `get`, `handle`, `thenApply`, `thenCompose`, `thenCombine`, `orTimeout`.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync`, cancelling HTTP futures and HTTP exchanges.
- [`HttpRequest` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, URI, and timeout.
- [`HttpResponse` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.html): status, headers, body, and BodyHandlers.
- [`CompletionStage` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html): handling success/error branches, combining operations.
- [`HttpServer` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local fixture for the two demo programs.
