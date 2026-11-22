# Asynchronous HTTP in Java: handle, exceptionally, and Finding the Root Cause Behind CompletionException

## 1. Context: Sending Asynchronous HTTP Requests, Where Do Errors Appear?

Java 17 provides `java.net.http.HttpClient.sendAsync(...)` returning `CompletableFuture<HttpResponse<T>>`. After calling `sendAsync`, the calling thread can continue working; only when the HTTP result, body, and corresponding handler complete does the future complete normally or exceptionally. You can chain `thenApply`, `thenCompose`, `handle`, `exceptionally`, and `whenComplete` steps to decode, check status, fetch fallbacks, and report errors.

A typical scenario: an application calls an API to fetch data. If the server responds validly, use the body; if the server temporarily returns **HTTP 503**, you might choose a cached copy or a “try again later” message; if there is a **TLS/certificate error**, it should not be disguised as a 503 error; if the user **cancels the task**, you must not make it “succeed” with a fallback.

~~~text
HttpClient.sendAsync(...)
         |
         v
CompletableFuture<HttpResponse<String>>
         |
         | HTTP 200/404/503 can all be normal HTTP results
         v
thenApply(response -> check status and body)
         |
         +---- normal ------> thenApply / handle / whenComplete ---> body
         |
         +---- exceptional --> handle / exceptionally / whenComplete
                                      |
                                      +-- intentional recovery ---> fallback value
                                      |
                                      +-- cannot recover ---------> exceptional future

At the result-waiting boundary:
    future.join() -> CompletionException usually wraps the cause
    future.get()  -> ExecutionException usually wraps the cause
    cancel        -> CancellationException may appear directly
~~~

**Objective:** understand exactly when `handle` and `exceptionally` run, choose between recovery or mere observation with `whenComplete`, understand `CompletionException`/`ExecutionException`, find the **root cause** to classify HTTP/network/timeout/cancellation, avoid swallowing errors, and do not automatically retry requests with side effects. This lesson is set in the context of **asynchronous HTTP** and uses **Java 17+**.

## 2. What States Can a CompletableFuture Have?

`CompletableFuture<T>` represents a **result T that may arrive in the future**. It can:

1. **Complete normally:** carry a value of type T, including `null` if the contract allows.
2. **Complete exceptionally (exceptionally completed):** carry an error cause for dependent stages to handle; success-only stages usually do not run.
3. **Be cancelled:** `cancel(...)` causes the future to complete with `CancellationException` according to the CompletableFuture mechanism. Dependent stages can also complete exceptionally, potentially showing a wrapper.

Example:

~~~java
CompletableFuture<String> good =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> bad =
        CompletableFuture.failedFuture(
                new IllegalStateException("service failed"));
~~~

This is an illustrative snippet requiring `import java.util.concurrent.CompletableFuture`; the `failedFuture` API has been available since Java 9. `good.join()` returns `"OK"`; `bad.join()` throws an error according to `join`'s wrapping rules. Here there is **no HTTP request** — it only illustrates states.

### 2.1. Which Stages Are Affected by an Upstream Error?

~~~java
CompletableFuture<String> future =
        CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad input"))
                .thenApply(s -> s.toUpperCase());
~~~

`thenApply` **does not run** because upstream has no successful value. The new future remains exceptional. This is the difference from `handle` and `exceptionally`: those two APIs can turn an error path into a new value.

If inside `thenApply` you throw a `RuntimeException` yourself, the returned stage will complete **exceptionally**, even though the upstream `sendAsync` received a successful HTTP response. Therefore, the **error source** can be the network, body handler, status-check logic, JSON parser, mapper, or recovery handler — not just the server.

### 2.2. HTTP 404/500/503 Is Not Automatically an Exceptional Completion

When `HttpClient` receives a complete HTTP response, for example:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

maintenance
~~~

`sendAsync(request, BodyHandlers.ofString())` normally still **completes normally** with an `HttpResponse<String>` having `statusCode()==503`. This is an **HTTP application response**, not a Java exception from the network.

Therefore:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .exceptionally(error -> {
          // Does NOT run automatically just because the server returns HTTP 503.
          return fallbackResponse;
      });
~~~

this snippet is not the general way to catch status 503. To handle 4xx/5xx as an **exceptional branch**, you need to convert an unacceptable status into a typed exception or use `handle` to inspect both the response and the error:

~~~java
CompletableFuture<String> checked =
        client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString())
              .thenApply(response -> {
                  if (response.statusCode() >= 400) {
                      throw new HttpStatusException(response.statusCode());
                  }
                  return response.body();
              });
~~~

This is **illustrative code**; `HttpStatusException` is a custom class that will be included in the runnable program in section 8. The rule “status >=400 is a failure” is only an example policy; in practice, 404 might be considered valid for a lookup operation, or 429/503/409 may need separate handling.

## 3. `handle`: Handling Both Success and Failure

### 3.1. Meaning and Return Type

The method `CompletionStage.handle(BiFunction<T, Throwable, U>)` creates a new stage of type `U`. The function is called when upstream completes, **regardless of success or failure**:

- Normal: `value` holds the result value; `error` is normally `null`.
- Failure: `error` is a `Throwable` describing the error; `value` is normally `null`.
- The `handle` function can return a fallback value or transform the result; the new stage will **complete normally** with the returned value.
- If the `handle` function itself throws an error, the new stage completes exceptionally with that error.

Safe pattern when there is a fallback policy:

~~~java
CompletableFuture<String> safe =
        checkedGet(client, uri)
                .handle((body, error) -> {
                    if (error == null) {
                        return body;
                    }
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return "cached-copy";
                    }
                    throw new CompletionException(cause);
                });
~~~

This is an illustrative snippet located in a class that has `checkedGet`, `root`, and `HttpStatusException` defined in section 8. The key point: **recover only permitted errors**, do not turn every kind of error into `"cached-copy"`. In a real API, the fallback may contain `stale` metadata so downstream does not confuse fresh data with old data.

### 3.2. `handle` Can Change the Data Type

Suppose upstream is `CompletableFuture<HttpResponse<String>>`; you can use `handle` to return a DTO carrying outcome information:

~~~java
record ApiResult(boolean ok, int status, String body, String errorType) {}

CompletableFuture<ApiResult> result =
        rawHttpFuture.handle((response, error) -> {
            if (error != null) {
                Throwable cause = root(error);
                return new ApiResult(
                        false, -1, "", cause.getClass().getSimpleName());
            }
            return new ApiResult(
                    response.statusCode() < 400,
                    response.statusCode(),
                    response.body(),
                    "");
        });
~~~

This is an illustrative code snippet inside a class with `rawHttpFuture` and `root`; it is not a standalone file. `handle` can convert from `HttpResponse<String>` to `ApiResult` — conversely, `exceptionally` must return a value compatible with the upstream type.

**Be careful:** in the `ApiResult` example, the error is **turned into data** (normal completion). That is appropriate if the public API returns a “success/failure” result object, but downstream `exceptionally` stages **will not see the old error**. If you still want the exception flow, you must rethrow or represent the failure state very clearly in the DTO.

### 3.3. Common Mistakes with `handle`

~~~java
// RISK: turns every error into an empty string.
.handle((body, error) -> error != null ? "" : body)

// RISK: does not check error before using body.
.handle((body, error) -> body.length())

// RISK: returns null on error while downstream expects a String.
.handle((body, error) -> error == null ? body : null)
~~~

In the first case, TLS authentication errors or user cancellations can be disguised as an empty response. The second case can create an additional `NullPointerException`, losing visibility into the original error. The third case turns a failure into a **success with null**, making downstream more prone to delayed errors.

## 4. `exceptionally`: Intervening Only When Upstream Fails

`CompletionStage.exceptionally(Function<Throwable, ? extends T>)` acts as a recovery path:

- Upstream **succeeds**: the callback does not run; the success value is forwarded.
- Upstream **fails**: the callback receives the error and is allowed to return a **fallback value T** to complete normally.
- If the callback throws an exception: the subsequent stage continues to fail.

Example:

~~~java
CompletableFuture<String> text =
        checkedGet(client, uri)
                .exceptionally(error -> {
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return "retry-later";
                    }
                    throw new CompletionException(cause);
                });
~~~

Illustrative code using helpers from section 8. When HTTP succeeds with body `"ready"`, the `exceptionally` callback does not run, and the result remains `"ready"`. If the previous stage turned HTTP 503 into `HttpStatusException`, the callback chooses the fallback `"retry-later"`.

### 4.1. `exceptionally` Is Not an Automatic `catch` for HTTP Statuses

This is an important rule worth repeating: when `sendAsync` receives an **HTTP-valid 503 response**, the original future is normally **not exceptional**. To have `exceptionally` handle HTTP statuses, you first need a `thenApply`/`thenCompose` stage to classify the status and create an error according to the application's contract.

Another implementation might not need to throw an exception for a status, for example:

~~~java
CompletableFuture<String> result =
        client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString())
              .thenApply(response ->
                      response.statusCode() == 404
                              ? "not-found"
                              : response.body());
~~~

This is how to treat **404 as a business result** if the API is designed that way. However, the illustrative snippet does not handle other 500/503 statuses — depending on the protocol, a policy must be added. There is no Java rule that **every HTTP >=400 must be a Throwable**.

### 4.2. When Should You Use `exceptionally` Instead of `handle`?

Use `exceptionally` when you **want to keep the success path untouched** and only replace **certain errors**. Use `handle` when you need to **see both value and error**, normalize into a different result type, or perform a transformation depending on both states.

Comparison:

| Situation | `handle` | `exceptionally` |
| --- | --- | --- |
| Runs when upstream succeeds | Yes | No |
| Runs when upstream fails | Yes | Yes |
| Callback inputs | `(T value, Throwable error)` | `(Throwable error)` |
| Output type | `U`, can change type | `T`, compatible with upstream |
| Return fallback on error | Yes | Yes |
| Propagate error further | Throw exception | Throw exception |
| Used only to log while preserving result | Possible but not the optimal choice | Only sees errors, easy to recover accidentally |
| Suitable for observing both paths without changing data | Usually use `whenComplete` | No |

### 4.3. Recovery Does Not Make an HTTP Request Idempotent

If a `POST` has been sent to the server and the connection drops before receiving a response, `exceptionally` may see an `IOException`. **Do not infer that the server has not processed the POST**. Resending immediately inside the callback without an idempotency key can create two transactions. Recovering by returning cached/local data is different from retrying the same side-effecting request; a separate policy is required.

## 5. `whenComplete`: Observing Both Paths Without Replacing the Result

`whenComplete(BiConsumer<T, Throwable>)` receives both `value` and `error` like `handle`, but **has no return value to act as a fallback**. It is suitable for logging, metrics, and trace cleanup:

~~~java
CompletableFuture<String> observed =
        checkedGet(client, uri)
                .whenComplete((body, error) -> {
                    if (error == null) {
                        metricsRecordSuccess();
                    } else {
                        metricsRecordFailure(root(error));
                    }
                });
~~~

This is pseudocode in an app that has `metricsRecordSuccess`/`metricsRecordFailure`. If the `whenComplete` callback runs normally, the new stage reflects **the same success or failure outcome as upstream**. If the callback itself throws while upstream succeeded, the new stage can transition to the callback's error. If upstream already failed and the callback also throws, the specification prioritizes forwarding the **upstream error** to dependent stages; however, you should still ensure logging/metrics do not throw to avoid confusing the error source.

Comparison:

~~~text
1) thenApply:      runs only when there is a successful value, can transform the value.
2) handle:         runs on both success/failure, can transform to value U, recover.
3) exceptionally:  runs only on failure, can recover to value T.
4) whenComplete:   runs on both success/failure to observe, DOES NOT recover.
~~~

**Do not use `whenComplete` to “swallow” an exception**:

~~~java
// WRONG expectation: just logging and returning normally will make the error disappear.
checkedGet(client, uri)
        .whenComplete((body, error) -> {
            if (error != null) System.err.println(error);
        });
// The returned future is still exceptional if upstream is exceptional.
~~~

If you want to handle errors after the observation step, you can chain:

~~~java
CompletableFuture<String> result =
        checkedGet(client, uri)
                .whenComplete((body, error) -> logOutcome(body, error))
                .exceptionally(error -> chooseFallback(root(error)));
~~~

The illustrative snippet uses two hypothetical application functions. Logging is in `whenComplete`, recovery is in `exceptionally`; be careful that `chooseFallback` does not accidentally hide an important error.

## 6. What Is CompletionException? Why Do We Need to Find the Root Cause?

`CompletionException` in `java.util.concurrent` is an **unchecked wrapper** that commonly appears when a stage completes exceptionally or when calling `CompletableFuture.join()`. It cannot by itself tell what failed at the HTTP endpoint. The cause worth analyzing is usually in `getCause()`, for example:

~~~text
CompletionException
  └─ HttpStatusException("HTTP 503")     <-- app throws after status-check

CompletionException
  └─ HttpTimeoutException                 <-- request exceeded timeout

CompletionException
  └─ ConnectException                     <-- failed to connect

CompletionException
  └─ SSLHandshakeException                <-- TLS handshake error

ExecutionException
  └─ CompletionException?
       └─ IllegalStateException          <-- mapper/logic error
~~~

These are **examples of cause chains you may encounter**, not a guarantee that all providers/JDKs wrap errors in exactly one level as shown in the diagram. Some network errors have additional wrappers/causes/suppressed exceptions; you should not write code that relies on an exact number of `CompletionException` layers.

### 6.1. Differences Between `join()` and `get()`

| API | On success | On failure |
| --- | --- | --- |
| `future.join()` | Returns T; does not require declaring checked exceptions | Usually throws `CompletionException` (unchecked) containing the cause |
| `future.get()` | Returns T; can wait | Throws `ExecutionException` (checked) containing the cause; `InterruptedException` when interrupted |
| `future.get(timeout, unit)` | Returns T if in time | Additionally throws `TimeoutException` (checked) if waiting exceeds the deadline |
| `future.cancel(true)` | Completes cancellation if successful | `join()/get()` on a directly cancelled future can throw `CancellationException` |

**Be careful:** `get(timeout)` timing out may **only mean the wait did not finish in time**, and does not by itself prove the HTTP request was cancelled. `join()` also **does not have a timeout of its own**. To give a request a deadline, use `HttpRequest.Builder.timeout`, or manage CompletableFuture timeouts with awareness of whether the underlying I/O is still running.

### 6.2. Unwrap Helper That Only Strips Async Mechanism Wrappers

A pragmatic approach:

~~~java
static Throwable root(Throwable problem) {
    while ((problem instanceof CompletionException
            || problem instanceof ExecutionException)
            && problem.getCause() != null) {
        problem = problem.getCause();
    }
    return problem;
}
~~~

This snippet requires importing `java.util.concurrent.CompletionException` and `ExecutionException`. It **only unwraps known async wrappers**, stopping at the first cause that is not one of those two wrappers. This strategy prioritizes **preserving meaningful errors**: an inner `IOException` or `HttpStatusException` may carry important message/cause/suppressed details and should not be stripped away.

It does not mean every Throwable should be peeled all the way down to `getCause()==null`. A business exception may wrap a technical error while itself carrying the semantics that the caller needs to handle. For example, with `PaymentRejectedException(cause=IOException)`, the “technical root cause” is not automatically more important than the payment rejection error when deciding policy.

**Do not write an uncontrolled `while (error.getCause() != null) error = error.getCause()` loop** to make recovery decisions: it can lose context, misclassify errors, and risk infinite loops in unusual custom Throwables. If you need a deeper technical root, do that in logging/diagnostics with cycle protection and while keeping the original exception.

### 6.3. Do Not Discard Stack Traces and Suppressed Exceptions When Unwrapping

A helper that returns a `Throwable` for classification **should not drop the original wrapper from logs**. You can log all of:

- **operation/request ID**, method, sanitized endpoint without sensitive data, elapsed time;
- the **wrapper** the stage received and the **unwrapped cause**;
- the **full stack trace** and `suppressed`, the exception cause chain;
- HTTP status if the server actually returned a response;
- recovery/retry policy decision.

Do not log Authorization headers, cookies, bearer tokens, sensitive bodies, or query strings containing secrets. `cause.getMessage()` may also contain URLs or infrastructure details; filter/redact when exporting to observability systems.

## 7. Creating a Custom HttpStatusException to Separate HTTP Statuses from Network Exceptions

Because HTTP 503 is a normal response at the client layer, handling it with the `exceptionally` model requires a **status validation step**:

~~~java
static final class HttpStatusException extends RuntimeException {
    final int status;

    HttpStatusException(int status) {
        super("HTTP " + status);
        this.status = status;
    }
}

static CompletableFuture<String> checkedGet(
        HttpClient client, URI uri) {

    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
            .thenApply(response -> {
                if (response.statusCode() >= 400) {
                    throw new HttpStatusException(response.statusCode());
                }
                return response.body();
            });
}
~~~

These are **methods in the context of a class**, not a standalone file. The full program in section 8 uses this exact design. If `sendAsync` completes with HTTP 503, `thenApply` runs, detects the status, and throws `HttpStatusException`, causing the **new stage** to become exceptional. An `exceptionally` attached to the **new stage** will see the error; however, attaching it directly to the original HTTP future will **not run for 503**, so distinguishing where the stage is attached is very important.

Turning 4xx/5xx into an exception is an **application convention**. Some systems prefer not to throw an exception for 404 and instead return `Optional.empty()`; some systems parse the JSON error body to create a typed error. Choose a consistent policy, limit error body size, and avoid leaking sensitive data.

## 8. Complete Java 17+ Example: HTTP 503, handle, exceptionally, join/get, and cancel

The program uses the **built-in JDK HTTP server** (`com.sun.net.httpserver.HttpServer`) running on IPv4 loopback `127.0.0.1` with a random port and two endpoints:

- `GET /ok` returns `200 OK`, body `ready`.
- `GET /busy` returns `503 Service Unavailable`, body `unavailable`.

The `HttpClient.sendAsync` client sends GET requests and builds stages in different ways. The loopback server keeps the test **independent of the Internet** and produces deterministic output. This example only simulates **HTTP status 503** and manual future cancellation; it **does not simulate network drops, TLS errors, or production retries**.

Save the following content to **HttpFailureStagesDemo.java**:

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
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class HttpFailureStagesDemo {
    static final class HttpStatusException extends RuntimeException {
        final int status;

        HttpStatusException(int status) {
            super("HTTP " + status);
            this.status = status;
        }
    }

    static Throwable root(Throwable problem) {
        while ((problem instanceof CompletionException
                || problem instanceof ExecutionException)
                && problem.getCause() != null) {
            problem = problem.getCause();
        }
        return problem;
    }

    static void send(HttpExchange exchange, int status, String body)
            throws IOException {
        try (exchange) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    static CompletableFuture<String> checkedGet(
            HttpClient client, URI uri) {

        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() >= 400) {
                        throw new HttpStatusException(response.statusCode());
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/ok",
                e -> send(e, 200, "ready"));
        server.createContext("/busy",
                e -> send(e, 503, "unavailable"));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newHttpClient();

            // HTTP status 503 is still a normal response.
            HttpRequest request = HttpRequest.newBuilder(
                    base.resolve("busy")).GET().build();
            int rawCode = client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString())
                    .join().statusCode();
            System.out.println("Raw HTTP status: " + rawCode);

            String success = checkedGet(client, base.resolve("ok"))
                    .handle((body, failure) ->
                            failure == null ? body : "unexpected")
                    .join();
            System.out.println("handle success: " + success);

            String recovered = checkedGet(
                    client, base.resolve("busy"))
                    .handle((body, failure) -> {
                        if (failure == null) return body;
                        Throwable underlying = root(failure);
                        if (underlying instanceof HttpStatusException status
                                && status.status == 503) {
                            return "cached";
                        }
                        throw new CompletionException(underlying);
                    })
                    .join();
            System.out.println("handle recovery: " + recovered);

            String fallback = checkedGet(
                    client, base.resolve("busy"))
                    .exceptionally(failure -> {
                        Throwable underlying = root(failure);
                        if (underlying instanceof HttpStatusException status
                                && status.status == 503) {
                            return "retry-later";
                        }
                        throw new CompletionException(underlying);
                    })
                    .join();
            System.out.println("exceptionally recovery: " + fallback);

            String onlyFailure = checkedGet(
                    client, base.resolve("ok"))
                    .exceptionally(failure -> "unexpected")
                    .join();
            System.out.println("exceptionally success: " + onlyFailure);

            CompletableFuture<String> broken =
                    checkedGet(client, base.resolve("busy"))
                            .thenApply(s -> s + "!");

            try {
                broken.join();
            } catch (CompletionException failure) {
                System.out.println("join: "
                        + failure.getClass().getSimpleName()
                        + " -> "
                        + root(failure).getClass().getSimpleName());
            }

            try {
                broken.get();
            } catch (ExecutionException failure) {
                System.out.println("get: "
                        + failure.getClass().getSimpleName()
                        + " -> "
                        + root(failure).getClass().getSimpleName());
            }

            String observed = checkedGet(
                    client, base.resolve("busy"))
                    .whenComplete((body, failure) -> {
                        if (failure != null) {
                            System.out.println("whenComplete saw: "
                                    + root(failure)
                                            .getClass().getSimpleName());
                        }
                    })
                    .exceptionally(failure ->
                            "fallback-after-observe")
                    .join();
            System.out.println("after observation: " + observed);

            CompletableFuture<String> cancelled =
                    new CompletableFuture<>();
            cancelled.cancel(true);
            try {
                cancelled.join();
            } catch (CancellationException failure) {
                System.out.println("cancel: "
                        + failure.getClass().getSimpleName());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run with JDK 17+ having the `jdk.httpserver` module:

~~~bash
javac -encoding UTF-8 HttpFailureStagesDemo.java
java HttpFailureStagesDemo
~~~

Output verified with JShell on Java 17:

~~~text
Raw HTTP status: 503
handle success: ready
handle recovery: cached
exceptionally recovery: retry-later
exceptionally success: ready
join: CompletionException -> HttpStatusException
get: ExecutionException -> HttpStatusException
whenComplete saw: HttpStatusException
after observation: fallback-after-observe
cancel: CancellationException
~~~

### 8.1. Line-by-Line Output Explanation

1. **`Raw HTTP status: 503`**: `sendAsync` returns a normal `HttpResponse`; code 503 by itself is not a future exception.
2. **`handle success: ready`**: HTTP 200 is converted via `thenApply` to the body; `handle` receives `error==null` and preserves `ready`.
3. **`handle recovery: cached`**: `checkedGet` throws `HttpStatusException(503)` in the status-check stage; `handle` is called on the error path, unwraps the wrapper, and returns `cached`.
4. **`exceptionally recovery: retry-later`**: the callback runs only on an exceptional stage, identifies that this is an application-classified 503, and replaces it with the fallback.
5. **`exceptionally success: ready`**: when upstream succeeds, `exceptionally` **does not run**; it does not modify the body.
6. **`join: CompletionException -> HttpStatusException`**: the error reaches the `join` boundary, where the caller sees the unchecked wrapper; the helper extracts the right business cause.
7. **`get: ExecutionException -> HttpStatusException`**: `get` uses a different checked wrapper. Even when called on the same broken future, unwrapping yields the same error type.
8. **`whenComplete saw: HttpStatusException`**: the callback observes the error but **does not recover**. The downstream `exceptionally` stage is what produces the fallback.
9. **`after observation: fallback-after-observe`**: the result of the recovery stage running after `whenComplete`.
10. **`cancel: CancellationException`**: a directly cancelled future can cause `join` to throw `CancellationException`, not necessarily going through `CompletionException`.

In the demo, `join` calls are invoked in **main** to produce deterministic stdout and teach semantics. In a production server/web event loop, **do not block I/O-serving threads** with `join`/`get` if you can continue chaining with `CompletionStage`.

### 8.2. Why Choose a Loopback Server?

`127.0.0.1` is the IPv4 loopback address; the server binds to port 0 so the OS assigns an available port. The client and server run in the **same Java process**; there is no reliance on the Internet, public DNS, or real APIs. This allows reliably verifying **HTTP status → exceptional status check → recovery** without external network variables. The code closes `HttpExchange`, stops the server in `finally`, and requires no other files or accounts.

### 8.3. What in the Demo Is Not Yet Production-Ready?

- `HttpStatusException` only holds the status, without a trace ID, response headers, or a size-bounded error body.
- `checkedGet` treats every status >=400 as exceptional per the demo policy; real applications may handle 404/409/429/503 differently.
- `"cached"` and `"retry-later"` are illustrative values, not integrated with a real cache, TTL, or metrics.
- The demo **does not handle network timeouts, TLS identity, redirects, retry/backoff, or cancellation propagation** on an active HTTP exchange.
- The demo `HttpServer` has no auth/TLS and uses loopback; do not deploy it as a production server on the Internet.

Treat the program as a test of **CompletionStage semantics**, not as an HTTP library with a complete error policy.

## 9. Which Layers Do `HttpClient.sendAsync` Errors Usually Come From?

An async HTTP pipeline has many sources of failure:

| Source | Observable sign | How it should be handled |
| --- | --- | --- |
| Unable to resolve host | `UnknownHostException` or DNS-related cause | Check URI/DNS; bounded retry if appropriate |
| Unable to connect | `ConnectException`/`IOException` | Check server, routing, port, firewall, transient conditions |
| Insecure connection/TLS | `SSLHandshakeException` or other TLS errors | **Do not bypass trust/certificate verification** to let it pass |
| Request timed out | `HttpTimeoutException`, `HttpConnectTimeoutException` | Distinguish connect timeout vs full request timeout, deadline, and policy |
| Response body decoding failed | `IOException` or BodySubscriber exception | Handle body size/encoding, verify contract |
| Mapper threw an exception | `IllegalArgumentException`, `IllegalStateException`, or custom type | Fix contract/parse/input; do not default to network retry |
| HTTP returned 4xx/5xx status | `HttpResponse.statusCode()`, **not automatically an exception** | Classify status in an application stage |
| Future cancelled | `CancellationException`, directly or in cause | Stop downstream, clean up, do not resurrect the task |
| Recovery callback threw an error | New error from handler | Preserve cause/log, define that fallback itself can fail |

Actual exception types and chains vary by JDK, provider, proxy, HTTP version, and callback position. **Do not write only `if (error instanceof ConnectException)`** and ignore that the stage may deliver a `CompletionException` wrapper around it; conversely, **do not turn every network error into “HTTP 503”** if the server never returned 503.

### 9.1. HTTP 503 and `HttpTimeoutException` Are Not the Same Thing

- **HTTP 503**: the server or an intermediary actually returned an HTTP response; there may be a `Retry-After` header. 503 itself is a status **inside HttpResponse**.
- **`HttpTimeoutException`**: the client exceeded the request deadline and may never have received an HTTP response; do not fabricate a 503 status from the exception.
- **`HttpConnectTimeoutException`**: timeout error during the connection establishment phase (a subtype of `HttpTimeoutException` in Java).
- **`TimeoutException` from `CompletableFuture.orTimeout`**: a deadline set at the future layer, not automatically synonymous with an internal HTTP timeout.

Proper classification keeps metrics and retry policies accurate. A dashboard reporting “HTTP status=503” for DNS-failed requests is wrong, because there is no response status.

### 9.2. Not All HTTP 4xx Should Be Retried

Typically:

- **400/422**: malformed request/schema; retrying the exact same request will not help.
- **401/403**: credential/authorization issue; must be resolved according to policy, not retried indefinitely.
- **404**: may be a valid business state; can use a result type instead of an exception.
- **409/412**: contention/conflict state; need to re-read state, merge, or inform the user, not just resend the same request.
- **429**: rate limit; inspect `Retry-After`/quota and backoff policy.
- **503**: temporarily unavailable; can perform bounded retries for **idempotent GET** if budget allows.

These are guidelines, not rigid rules for every API. Retries must be based on HTTP method, idempotency, deadline, and specific server behavior.

## 10. Unwrapping Wrappers and Classifying Causes Without Losing Information

A simple pattern:

~~~java
static String classify(Throwable error) {
    Throwable cause = root(error);

    if (cause instanceof CancellationException) {
        return "CANCELLED";
    }
    if (cause instanceof HttpConnectTimeoutException) {
        return "CONNECT_TIMEOUT";
    }
    if (cause instanceof HttpTimeoutException) {
        return "REQUEST_TIMEOUT";
    }
    if (cause instanceof SSLHandshakeException) {
        return "TLS_FAILURE";
    }
    if (cause instanceof HttpStatusException status) {
        return "HTTP_" + status.status;
    }
    if (cause instanceof IOException) {
        return "NETWORK_OR_IO";
    }
    return "OTHER";
}
~~~

This is **illustrative code in a class with `root` and `HttpStatusException`**, requiring imports for `java.io.IOException`, `javax.net.ssl.SSLHandshakeException`, `java.net.http.HttpTimeoutException`/`HttpConnectTimeoutException`, and `CancellationException`. **Subtype order matters**: `HttpConnectTimeoutException` must be checked before `HttpTimeoutException`. The `IOException` group is a broad umbrella; not every IO error should be retried.

### 10.1. Special Handling for Cancellation

If `cause instanceof CancellationException`, do not default to returning a cached value “as if the request succeeded” when the operation was actively cancelled by the user. For application systems, cancellation is usually a **signal to terminate the pipeline**; propagate/cancel related tasks and clean up resources according to policy.

Example:

~~~java
.exceptionally(error -> {
    Throwable cause = root(error);
    if (cause instanceof CancellationException) {
        throw (CancellationException) cause;
    }
    if (cause instanceof HttpStatusException status
            && status.status == 503) {
        return "stale-ok-by-policy";
    }
    throw new CompletionException(cause);
})
~~~

This is a fragment attached to `CompletableFuture<String>`. If the callback throws `CancellationException`, the dependent stage becomes exceptional; **it does not necessarily have `isCancelled()==true` like calling `cancel` directly on the dependent future itself**. When observing exceptions, distinguish cancel errors and how cancellation is propagated along the chain.

### 10.2. Preserving the Original Exception When Rethrowing

In a handler you can write:

~~~java
throw new CompletionException(root(error));
~~~

This creates a new failure with the cause so downstream can still classify it. Do not construct `new RuntimeException("something went wrong")` and drop the cause — that loses the old stack trace and diagnostic trail. In real applications, you should also retain the correlation ID, request ID, and original error object in logging.

**Do not catch `Throwable` and recover everything unconditionally**. A serious runtime error or logic bug should not automatically be treated as “network transient” just because it appears in an `exceptionally` callback.

## 11. `handle` or `exceptionally` in a Multi-Step Chain?

Example three-step pipeline:

~~~text
sendAsync
    |
    v
thenApply(validate HTTP status)
    |
    v
thenApply(parse body)
    |
    +--> exceptionally(recover only approved failures)
    |
    v
thenApply(consume result)
~~~

If the JSON parser fails after an HTTP 200, the exceptional stage will reach `exceptionally` just like a network failure. Therefore, the handler must not simply check “error != null -> use cache” for all errors: a JSON schema mismatch could be an implementation or contract bug and should not be hidden.

### 11.1. Where Recovery Is Placed Affects Which Cause Is Seen

~~~java
// A: only catch errors from the network/HTTP exchange at the right point.
CompletableFuture<HttpResponse<String>> raw =
        client.sendAsync(request, BodyHandlers.ofString());

// B: status mapper can create HttpStatusException.
CompletableFuture<String> validated =
        raw.thenApply(HttpResponse::body); // has not checked status yet.

// C: parsing body can throw a JSON parsing exception.
CompletableFuture<Model> parsed =
        validated.thenApply(MyParser::parse);
~~~

The above is illustrative; `MyParser` and `Model` are hypothetical classes, and the `validated` snippet has not checked status yet. **The placement of `exceptionally`** determines whether it sees parser errors: attaching it before the parser will not see parser errors; attaching it after the parser can see network, status, and parse errors. Place recovery where there is **enough information to classify without having produced side effects yet**.

### 11.2. Separating Transport Result and Business Result

A testable design separates:

- **Transport/HTTP stage:** succeeds with `HttpResponse`, or throws an exception on network/transport failure.
- **Status validation stage:** distinguishes accepted statuses from statuses defined as errors.
- **Decode stage:** converts the body into a domain object; an invalid schema is a distinct error type.
- **Recovery stage:** falls back only for errors permitted by policy.
- **Observation stage:** logs/records metrics for the final outcome, without “lying” that a fresh response was received if a cache was actually used.

You can use sealed interfaces/records `Result` carrying `source=LIVE/CACHE` and `stale` to represent fallbacks explicitly. When using `handle` to convert an error into a value, keep a marker indicating recovery for logging rather than treating it as the same kind of success as a fresh HTTP 200.

## 12. Recovering with Another Future: `exceptionallyCompose`

`exceptionally` returns a **value T**, not a `CompletableFuture<T>` to compose automatically. If the fallback must call a second API, fetch data asynchronously from a cache, or query another downstream service, you should use `exceptionallyCompose` on Java 17+ or design `handle` to return a future and then `thenCompose`.

**Non-standalone** illustration, assuming `readCacheAsync(key)` returns `CompletableFuture<String>`:

~~~java
CompletableFuture<String> result =
        checkedGet(client, uri)
                .exceptionallyCompose(error -> {
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return readCacheAsync(key);
                    }
                    return CompletableFuture.failedFuture(cause);
                });
~~~

`exceptionallyCompose` (Java 12+) creates an asynchronous continuation on the failure path and **flattens** the fallback future. With `exceptionally`, writing `return readCacheAsync(key);` will fail to type-check: the handler must return `String`, not `CompletableFuture<String>`.

**Do not call `readCacheAsync(key).join()` inside the callback** just to force a String when you can compose: doing so **blocks the thread running completion**, causing bottlenecks under high load. If the fallback itself is a blocking CPU/DB task, use a properly managed executor so you do not occupy I/O workers.

### 12.1. Pay Attention to the Callback's Executor

Callbacks without the `Async` suffix can typically run on the thread that completes the upstream stage or on the registering thread if the stage has already completed; **never assume they run on the main thread**. The `handleAsync`, `whenCompleteAsync`, and `exceptionallyAsync` variants can offload execution to an appropriate executor.

Example:

~~~java
Executor executor = Executors.newFixedThreadPool(4);
CompletableFuture<String> f = checkedGet(client, uri)
        .handleAsync((body, error) -> {
            // Moderate CPU-bound recovery work.
            return error == null ? body : "fallback";
        }, executor);
~~~

This is **illustrative code**, requiring `Executor`/`Executors` imports, and production code must **close/shutdown the executor** according to the application lifecycle. Do not create a new thread pool **per request**; use a managed pool with a bounded queue. If the fallback is slow I/O, chaining with a non-blocking future is usually more appropriate.

## 13. Timeouts in HttpClient and CompletableFuture

### 13.1. Connect Timeout and Request Timeout

`HttpClient` allows setting a connect timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

`HttpRequest.Builder` allows setting a timeout for the request:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

These snippets require importing `java.time.Duration` and HTTP types; they are not standalone programs. HTTP client timeouts can result in `HttpTimeoutException` (or `HttpConnectTimeoutException` for connect) inside an exceptional completion. **There is no HTTP status to read if the client has not received a valid response.**

### 13.2. `orTimeout` and `completeOnTimeout`

Two ways to customize a future:

~~~java
CompletableFuture<String> timed =
        checkedGet(client, uri)
                .orTimeout(2, TimeUnit.SECONDS);

CompletableFuture<String> defaulted =
        checkedGet(client, uri)
                .completeOnTimeout("fallback", 2, TimeUnit.SECONDS);
~~~

These are **different** requests in the illustration. `orTimeout` causes the future to receive a `TimeoutException` if the deadline passes; `completeOnTimeout` causes the future to complete **normally** with the fallback on timeout. Both operations **can act directly on the CompletableFuture they are called on** — do not assume they create an independent dependent stage so that others can still wait on the original request unchanged.

**Important:** a stage timeout does not guarantee that the underlying network I/O has stopped immediately; you need to manage cancellation/resources according to the `HttpClient` contract, and not issue more requests if the overall deadline has expired. If you need to cancel an in-flight HTTP exchange, check the `cancel` behavior of `sendAsync` on the JDK you are using; it may request cancellation, but does not guarantee the peer has not already received or processed the bytes.

### 13.3. `get(timeout)` Is Not `orTimeout`

~~~java
String value = future.get(2, TimeUnit.SECONDS);
~~~

If `get` throws `TimeoutException`, **the future may still be running**; only the wait call is bounded, and it does not necessarily complete the future exceptionally or cancel it. With `orTimeout`, the future is completed exceptionally at the deadline if no result is available yet. Both APIs share the word “timeout” but differ in **what they affect**.

### 13.4. Do Not Recover Timeouts Infinitely

Wrong example:

~~~text
request timeout -> exceptionally -> retry immediately
retry timeout   -> exceptionally -> retry immediately
... without max attempts or overall deadline ...
~~~

Even if a GET can be retried, there must be an **overall deadline**, a limit on attempts, backoff/jitter, checking `Retry-After` when present, respecting rate limits, and avoiding retry storms. For POST/PUT with side effects, idempotency/transaction semantics are required before replaying automatically.

## 14. Request Cancellation, Interrupts, and Cleanup

### 14.1. Cancellation Is Not Necessarily an Error That Can Fall Back

When a user leaves a screen, closes the app, or cancels a task, the future may have `cancel(true)` called on it. If every `exceptionally` branch returns a cached value, you can cause the pipeline to **display a result after the user has already cancelled**. Therefore, classify `CancellationException`, mark it as cancelled, and do not create side effects in subsequent callbacks.

`CompletableFuture.cancel(true)` transitions the future to the cancelled state if not yet done; the `mayInterruptIfRunning` flag **does not guarantee that a specific thread of the CompletableFuture will be interrupted**, because CompletableFuture does not necessarily use interrupts to control progress. When applied to `HttpClient.sendAsync`, exchange cancellation behavior also depends on implementation and timing; **you cannot conclude that data has not reached the server**.

### 14.2. When Using `get()` and Being Interrupted

~~~java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Stop/propagate according to the application's thread contract.
    throw interrupted;
}
~~~

This is a fragment placed in a method declaring `throws InterruptedException, ExecutionException` or an equivalent signature. When catching `InterruptedException`, **restore the interrupt flag** if you are not completing the task here, so upper layers know the thread was requested to stop. `join` throws unchecked wrappers for exceptional completion but does not replace interrupt management when you use blocking `get`.

### 14.3. Cleanup When Observing Failures

An application-owned connection/file/stream needs to be closed when the pipeline completes, fails, or is cancelled according to its semantics. `whenComplete` is suitable as a hook:

~~~java
CompletableFuture<String> result = checkedGet(client, uri)
        .whenComplete((body, error) -> {
            if (error != null) {
                logSafeFailure(root(error));
            }
            releaseRequestResources();
        });
~~~

This is illustrative code with application-defined `logSafeFailure`/`releaseRequestResources`. In real applications, releasing must be **idempotent** if timer/cancel/completion race with each other, and resources must not be closed before the publisher/body subscriber has actually finished using them.

## 15. Designing a Retry/Recovery Policy for Asynchronous HTTP

A solid policy usually considers **four dimensions**:

1. **Error type:** status 429/503, network transient, TLS trust error, validation bug, timeout, cancel.
2. **Method/idempotency:** GET can usually be retried; a POST that creates an order should not be retried automatically without an idempotency key.
3. **Budget:** maximum attempts, overall deadline, delay/backoff/jitter, and server `Retry-After`.
4. **User impact:** is stale fallback allowed, does cached data need a warning, or must an explicit error be reported?

Illustrative policy table example:

| Error / state | Reasonable recovery? | Notes |
| --- | --- | --- |
| GET receives HTTP 503 | Can return stale cache or perform bounded retry | Must follow cache TTL/trustworthiness |
| HTTP 429 | Can wait according to Retry-After, quota, and deadline | No retry storms |
| HTTP 404 | Can return “no data” as a result | Depends on API, not always a failure |
| HTTP 400/422 | Usually do not retry as-is | Check request/schema |
| TLS certificate verification error | **Do not** bypass verification automatically | Check trust/hostname configuration |
| DNS/ConnectException | Can perform bounded retry depending on circumstances | Do not assert what the service has already processed |
| Parse error on HTTP 200 | Usually needs to fail/alert for investigation | Do not hide every schema mismatch |
| Cancellation | Do not recover by default | Respect cancellation intent |
| Timeout after side-effecting POST | Uncertain whether server processed it | Needs idempotency/reconciliation |

**Do not unconditionally attach `exceptionally` at the end of every pipeline just to return “OK”**. When every error becomes a fake success, metrics/tracing miss incidents, users see wrong data, and the system may execute business actions repeatedly.

### 15.1. Fallback Does Not Mean Fresh Data Was Read

A good DTO can state this explicitly:

~~~java
record ReadOutcome(String value, boolean fromCache, boolean stale) {}
~~~

When falling back due to 503, return `new ReadOutcome(cachedBody, true, true)`; on a fresh HTTP 200, return `new ReadOutcome(body, false, false)`. This is an illustrative snippet without a method to fetch `cachedBody`. This representation avoids “lying” to downstream that cached data is a fresh response from the origin.

### 15.2. `Retry-After` Is Response Metadata, Not Always Present in Throwable

If you throw `HttpStatusException(status)` without keeping response headers, then by the time you reach `exceptionally` you will no longer have `Retry-After`. A production design can store **status + bounded error body + necessary headers + request ID** in a custom error. However, never retain full sensitive headers or unbounded bodies in an exception. You can choose to turn an HTTP status into a result type instead of an exception if the workflow needs rich metadata.

## 16. Testing All Branches Properly and Logging Without Losing Errors

An important test suite should cover:

- **HTTP 200**: `handle` runs with `error==null`, `exceptionally` does not run.
- **HTTP 503**: raw `sendAsync` **succeeds** with `statusCode()==503`; the status-check throws the custom exception.
- **Custom status error**: `handle`/`exceptionally` recovers only permitted codes; other codes remain exceptional.
- **`join` and `get`**: receive the expected wrappers, and the helper finds the custom error.
- **`whenComplete`**: only logs; the stage remains exceptional if there is no subsequent recovery.
- **Thrown callback**: if `handle` or `exceptionally` throws, the dependent stage fails.
- **Cancel**: receives `CancellationException`; is not turned into an “empty success”.
- **Timeout**: distinguishes request `HttpTimeoutException` from future `TimeoutException` and `get(timeout)`.
- **TLS/network failures**: not treated as HTTP 503; do not disable certificate verification.
- **Unknown JSON/body shape**: parser errors are not swallowed.
- **Concurrent requests**: do not use unsynchronized shared mutable variables to record exceptions or results of different requests.

Use a **loopback HTTP test server** or mock server to produce deterministic status codes instead of relying on public APIs that can change or unreliable networks. The example in section 8 does exactly this for the main logic branches.

### 16.1. A Small Test Case for `whenComplete`

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

CompletableFuture<String> watched =
        failed.whenComplete((v, e) -> {
            System.out.println("observed: " + root(e).getMessage());
        });

// watched still fails; watched.join() will throw.
~~~

This snippet is an example in a class that has `root`; it shows that logging and recovery are two distinct actions. If you replace `whenComplete` with `exceptionally(e -> "fallback")`, a new stage can complete normally with the String `fallback`.

## 17. Common Mistakes When Chaining Stages

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Assuming HTTP 503 automatically triggers `exceptionally` | Handler does not run because original future succeeds | Read statusCode; create a typed status failure if needed |
| Using `handle((value,error)->value)` without checking error | Turns error into normal null | Check error and rethrow if not recovering |
| `exceptionally(e -> "")` for all errors | Hides TLS/cancel/parser bugs | Classify the cause and apply a fallback policy |
| Thinking returning normally from `whenComplete` catches the error | Future remains exceptional | Use handle/exceptionally if you want to recover |
| Checking only `error instanceof HttpStatusException` | Misses the CompletionException wrapper | Unwrap in a controlled manner |
| Always unwrapping all `getCause()` down to null | Loses typed business error context | Strip only async wrappers, preserve business errors |
| Catching `Exception` from `join` and logging only the wrapper message | Unclear root cause | Log root + wrapper and stack |
| Mixing `get()` and `join()` and handling only one exception type | Misses ExecutionException/checked flow | Distinguish API boundaries |
| `handle` returning null on error | NPE in later stage, hides cause | Typed Result, valid fallback, or rethrow |
| Recovery callback throws without being monitored | New error goes unobserved | Test failure paths and attach a terminal observer |
| Calling `join()` inside a completion callback for async fallback | Blocks worker, risk of deadlock/starvation | `exceptionallyCompose`/`thenCompose` |
| `sendAsync` returns 500 yet still parsed as 200 | Confusing parser error, loses HTTP context | Validate status before parsing per contract |
| Replaying POST after TimeoutException without idempotency | Can create duplicate side effects | Retry policy / idempotency key |
| Returning cache while metrics record live 200 success | Breaks observability and hides stale data | Outcome explicitly records source and stale/fallback |
| Catching cancellation and returning a cached body | Continues work that was cancelled | Propagate CancellationException |
| Treating `get(timeout)` timeout as HTTP exchange cancelled | Request may still be running | Manage future/network lifecycle separately |
| Swallowing `InterruptedException` on `get()` | Thread loses its stop signal | Restore interrupt flag and propagate |
| Logging full bearer tokens or URLs with secrets | Data leak | Redact, log correlation ID/summary |
| Running blocking DB in `exceptionally` on I/O completion thread | Slows down other completions | Compose async or use a bounded executor |
| Reusing one `CompletableFuture` for unrelated requests | Mixes results and states | Each operation has its own future/state |

## 18. Scenario Exercises

### Exercise A — Does HTTP 500 Go Through `exceptionally`?

Code:

~~~java
client.sendAsync(request, BodyHandlers.ofString())
      .exceptionally(error -> fallbackResponse);
~~~

The server returns a valid HTTP 500 response, with no transport exception. Does `exceptionally` run?

**Answer:** usually **no**. `HttpClient` returns an `HttpResponse` with `statusCode()==500`; you must check the status or map it to a typed error before `exceptionally` handles it. Callback/body handler errors can still make the stage exceptional, but status 500 alone will not.

### Exercise B — `handle` Receiving Success

Upstream returns String `"A"`. Callback:

~~~java
.handle((value, error) -> error == null ? value + "!" : "FALLBACK")
~~~

**Answer:** `handle` runs on success too, receives `value="A"`, `error=null`, and returns `"A!"`. If `exceptionally` were used instead, the callback would not run and the result would remain `"A"`.

### Exercise C — `handle` Accidentally Hiding Errors

`CompletableFuture<String>` fails due to `SSLHandshakeException`, but the code uses `handle((body, err) -> err == null ? body : "OK")`.

**Answer:** the next stage will complete normally with `"OK"`, hiding the TLS error and making downstream think it received a good response. You must rethrow the cause or use a typed failure result; do not ignore trust/certificate failures.

### Exercise D — join vs get

A stage fails due to `HttpStatusException(503)`. Do `join()` and `get()` throw the same exception?

**Answer:** usually `join()` throws `CompletionException` (unchecked), whereas `get()` throws `ExecutionException` (checked). Unwrap those two wrappers to obtain the typed HTTP exception. For direct cancellation, `CancellationException` may appear directly.

### Exercise E — Root Cause Under Two Wrappers

A callback receives `CompletionException(ExecutionException(ConnectException))`. How is it classified?

**Answer:** the `root` helper strips both async wrappers and returns `ConnectException`. Do not treat it as HTTP status 503; if there was no response, do not invent an HTTP status code.

### Exercise F — After `whenComplete` Logs

A future fails with `IllegalArgumentException`. The `whenComplete` callback prints a log and returns normally. Does the new stage succeed?

**Answer:** no. If the callback does not throw another exception, the upstream error is still propagated to the new stage. Only `handle` or `exceptionally` can explicitly convert it to a normal value.

### Exercise G — Cancelled Request

The user clicks Cancel; a dependent stage receives a `CancellationException` cause. The current policy recovers every exception with a cached body.

**Answer:** you should respect cancellation; do not resurrect the pipeline with a cached body. Propagate the cancelled/failure state and clean up resources as designed.

### Exercise H — Timeout from `get(timeout)`

The caller uses `future.get(500, MILLISECONDS)` and receives `TimeoutException`. Is it certain that the future has ended or the HTTP request has been cancelled?

**Answer:** no. Only the **wait call** timed out; the future may complete later. Separate deadline/cancellation handling is needed, and avoid causing side effects after the user has abandoned the task.

### Exercise I — Retrying POST Can Cause Duplicates

A client POSTs to create an order, and the socket drops before receiving a response; `exceptionally` receives `IOException`. Can we be sure retrying will not create two orders?

**Answer:** no. The server may have already recorded the order before the network error. You need an idempotency key, a transaction status query, or a retry mechanism agreed upon by the API.

### Exercise J — Async Fallback Needing to Call a Second API

A chain `exceptionally(error -> backupService.fetchAsync())` does not compile because the main future has type `CompletableFuture<String>`.

**Answer:** `exceptionally` must return `String`, not `CompletableFuture<String>`. Use `exceptionallyCompose` if `backupService` returns a future, or `handle` returning a future followed by `thenCompose` to flatten it.

### Exercise K — Parser Exception

HTTP 200 returns text `"not-json"`, and `thenApply(parser::parse)` throws `JsonParsingException`. Should we keep retrying the network?

**Answer:** not automatically. This could be a contract/schema issue or a parser bug, not a transient network error. Classify the typed exception, log bounded status/body details, and respond according to policy.

### Exercise L — TimeoutException Is Not the Same as HttpTimeoutException

`future.orTimeout(...)` expires, while `HttpRequest.timeout(...)` is not enabled. What exception type might the stage see?

**Answer:** `TimeoutException` from the CompletableFuture mechanism, usually appearing through a wrapper in another stage; not necessarily `HttpTimeoutException`. Different timeout sources lead to different metrics and lifecycle handling.

## 19. Checklist for Using CompletableFuture with Asynchronous HTTP

- [ ] Distinguished **HTTP error status** (HttpResponse) from **exceptional completion** (network/callback/mapper)?
- [ ] `handle` used only when truly intending to handle both success and failure, with an explicit typed fallback?
- [ ] `exceptionally` recovers only permitted error types, not blanket-succeeding every Throwable?
- [ ] If only logging/metrics, used `whenComplete` and did not mistakenly believe it swallows errors?
- [ ] Checked the placement of `thenApply(status-check)` so status errors are converted before the recovery stage?
- [ ] Have a controlled unwrap helper for `CompletionException`/`ExecutionException` that does not strip typed root causes?
- [ ] Distinguished `join` (unchecked wrapper), `get` (checked wrapper, interrupt), and direct cancellation?
- [ ] Handled `CancellationException` and avoided executing cancelled work?
- [ ] Distinguished HTTP request timeouts, CompletableFuture timeouts, and `get(timeout)` waiting?
- [ ] If the fallback is also async, used compose instead of blocking `join()` inside a completion worker?
- [ ] Have an overall deadline, retry limits, backoff/jitter, and idempotency keys for side-effecting requests?
- [ ] Clearly defined which 404/409/429/503 statuses are valid business results and which require creating custom errors?
- [ ] Handled TLS verification errors safely, without fixing them by disabling SSL checks?
- [ ] Not swallowing exceptions from parse/mapping logic into unexpected empty/default values?
- [ ] Recorded success/live vs fallback/cache/stale so observability is not skewed?
- [ ] Logs include necessary stack traces + correlation IDs without exposing secrets?
- [ ] Resources, futures, and executors are cleaned up properly across normal/error/cancel lifecycles?
- [ ] Tested raw HTTP 503, converted status exceptions, handle success/recovery, exceptionally success/recovery, join/get, and whenComplete propagation?

**Conclusion:** For asynchronous HTTP in Java, `handle` runs for **both value and error** and can change the type; `exceptionally` runs **only when the previous stage fails** and can substitute a fallback; `whenComplete` mainly **observes the outcome** without recovering. `CompletionException`/`ExecutionException` are usually wrappers when errors pass through `CompletableFuture` — find the true inner cause to classify, but **do not discard context**. An HTTP 503 status is not automatically a Java exception; to recover by status, you must check the status in an application stage. Proper recovery is **conditional, deadline-bounded, and respectful of cancellation and HTTP semantics**, rather than returning a default for every error.

## 20. API References

- **Java 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Java 17 — CompletionStage:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Java 17 — CompletionException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html
- **Java 17 — ExecutionException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpRequest:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- **Java 17 — HttpResponse:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- **Java 17 — HttpTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- **RFC 9110 — HTTP Semantics (status codes):** https://www.rfc-editor.org/rfc/rfc9110

Status-error, fallback, and retry decisions are **application policy**; there is no single default that applies safely to all HTTP APIs. When building production systems, separate transport errors, HTTP statuses, and domain failures, test in the actual Java environment, and preserve diagnostic information from the cause chain.