# thenApply, thenCompose, and Chaining Dependent Steps

## Lesson Objectives

In Java 17+, `HttpClient.sendAsync(...)` returns a `CompletableFuture<HttpResponse<T>>`. Instead of blocking a thread to obtain the HTTP result before performing the next task, we can **chain dependent steps** into an asynchronous pipeline. Two transformations that appear constantly in practice are **`thenApply`** (transforming a value that is already available) and **`thenCompose`** (using the previous result to **initiate and await** another asynchronous task).

After this lesson, you will be able to:

- Explain `CompletableFuture<T>` / `CompletionStage<T>` and the difference between **registering a step** and **blocking to wait for a result**.
- Use `thenApply(Function<T,U>)` to transform `HttpResponse<String>` into a body, parse an ID, apply data rules, or build a display result.
- Use `thenCompose(Function<T,CompletionStage<U>>)` to chain a second HTTP request **only when** the first response has the required data.
- Distinguish `CompletableFuture<U>` from `CompletableFuture<CompletableFuture<U>>` and why `thenApply` can create **nested futures**.
- Distinguish **sequential dependent chains** from **independent requests running in parallel**; know when to use `thenCombine` or `allOf`.
- Handle HTTP status, network errors, parse errors, exception propagation, fallback, and logging at the right point; do not assume 4xx/5xx causes `sendAsync` to complete exceptionally.
- Understand `thenApplyAsync`/`thenComposeAsync`, executors, the risk of blocking callback threads, how to use timeouts, and the limits of cancellation.
- Run **two standalone Java 17+ examples**: one real loopback HTTP example and one pure `CompletableFuture` example illustrating type differences.

**Scope:** Asynchronous HTTP with `java.net.http.HttpClient` and `java.util.concurrent.CompletableFuture` in Java 17; examples do not access the Internet. This lesson covers **dependency relationships between steps**; do not treat `thenCompose` as a parallel execution command or an implicit replacement for timeout handling/resource cleanup.

## 1. Why Do We Need an Asynchronous Pipeline?

Suppose we want to fetch the name of a resource when the client only knows a username:

1. `GET /users/alice` returns a resource ID, for example `42`.
2. We must have that ID before calling `GET /items/42`.
3. Upon receiving the resource name, convert it to a display format (for example, uppercase).

These are **two dependent requests**: the second request cannot have a complete URI before the first request returns the ID. A synchronous approach can call `client.send(...)` twice, but the executing thread will **wait on I/O** at each call.

How to chain the steps:

~~~text
sendAsync(GET /users/alice)
          │
          ▼
CompletableFuture<HttpResponse<String>>
          │ thenApply: check HTTP status, get body
          ▼
CompletableFuture<String>     ───── "42"
          │ thenApply: Integer.parseInt
          ▼
CompletableFuture<Integer>    ───── 42
          │ thenCompose: use 42 to build GET /items/42 + sendAsync
          ▼
CompletableFuture<String>     ───── "Java NIO"
          │ thenApply: toUpperCase
          ▼
CompletableFuture<String>     ───── "JAVA NIO"
          │
          ▼
Only join()/get() at the boundary where the result is needed
~~~

**Do not wait inside each callback:** `sendAsync` initiates an HTTP exchange and returns a future. Calling `thenApply`/`thenCompose` **attaches** an action to the processing graph; normally the caller does not have to wait for the request to finish to continue building the pipeline. Once the HTTP exchange completes, dependent stages are triggered according to contract.

`CompletableFuture` is both a `Future` (can wait for a result) and a `CompletionStage` (can chain subsequent work). Therefore, if you only think of it as `Future.get()`, you miss the ability to express non-blocking data processing flows in intermediate segments.

**Note:** Not every callback runs on a separate thread; methods without the `Async` suffix do not promise to create a new worker. Thread execution details will be explained in the executor section.

## 2. `thenApply`: Transforming Value T into U

Java 17 signature:

~~~java
<U> CompletableFuture<U> thenApply(
    Function<? super T, ? extends U> function);
~~~

Condition: the previous stage **completes normally**. When it does, the function receives **value T** of the previous stage, computes a **value U**, and the new stage completes with U.

Type diagram:

~~~text
CompletableFuture<T>
     .thenApply(T -> U)
                │
                ▼
        CompletableFuture<U>
~~~

The following example is a Java 17 snippet (requires importing `java.util.concurrent.CompletableFuture`):

~~~java
CompletableFuture<String> text =
    CompletableFuture.completedFuture("42");

CompletableFuture<Integer> id = text.thenApply(Integer::parseInt);
CompletableFuture<String> label =
    id.thenApply(number -> "Item ID: " + number);

// id.join()    == 42
// label.join() == "Item ID: 42"
~~~

We can chain multiple `thenApply` calls to **parse**, **validate**, **map**, and **format**. `thenApply` is best suited for operations that **already have enough data** and return a regular value, without needing another asynchronous task.

With HTTP:

~~~java
CompletableFuture<String> bodyStage = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    });
~~~

The snippet above assumes `client` is an `HttpClient`, `request` is a built `HttpRequest`, and `java.net.http.*`, `java.util.concurrent.*` are imported. `sendAsync` returns `CompletableFuture<HttpResponse<String>>`, and `thenApply` takes the response and transforms it into `CompletableFuture<String>`.

**Why check status?** Receiving an `HttpResponse` with HTTP `404` or `500` is usually **not** a network execution error. The future can complete normally with `statusCode() == 404`; the application must interpret the status and decide whether to throw an error or enter a fallback.

### `thenApply` Does Not Mean More Asynchronous

`thenApply` describes the **execution condition** (when the previous stage completes normally) and **value transformation**, and does not itself commit to running the callback on a different executor. If inside the callback you call `Thread.sleep`, `Future.get`, synchronous `client.send`, or a long CPU task, you risk slowing down the thread executing that completion.

Use `thenApply` for fast/non-blocking processing. For CPU-heavy work, proactively offload to an executor; use `thenApplyAsync(fn, executor)` if policy requires a dedicated pool.

## 3. `thenCompose`: Returning a Next Stage and Flattening

Java 17 signature:

~~~java
<U> CompletableFuture<U> thenCompose(
    Function<? super T, ? extends CompletionStage<U>> function);
~~~

The mapper receives **T**, but **returns a `CompletionStage<U>`**, not an already-available U. The stage returned by `thenCompose` will complete with the **value/error** of the new stage returned by the mapper (when the corresponding completion conditions are satisfied).

Type diagram:

~~~text
CompletableFuture<T>
    .thenCompose(T -> CompletionStage<U>)
                │
                ▼
        CompletableFuture<U>
~~~

Example:

~~~java
CompletableFuture<Integer> userId =
    CompletableFuture.completedFuture(42);

CompletableFuture<String> title = userId.thenCompose(
    id -> CompletableFuture.supplyAsync(
        () -> "Title for " + id));

// title has type CompletableFuture<String>, not a nested future.
~~~

This is an illustrative snippet requiring `import java.util.concurrent.CompletableFuture`; `supplyAsync` only simulates an asynchronous task and does not call HTTP itself. In this lesson, the mapper's actual task is typically `client.sendAsync(nextRequest, handler)`.

**Timing relationship:** `thenCompose` does not initiate the second request before the previous stage completes normally and the mapper executes. It helps express dependencies clearly and avoids having to wait with `join()` inside the callback.

### Chaining Two Dependent HTTP Requests

~~~java
CompletableFuture<Integer> idFuture = client.sendAsync(
        lookupRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException("Lookup failed");
        }
        return Integer.parseInt(response.body());
    });

CompletableFuture<String> titleFuture = idFuture.thenCompose(
    id -> {
        HttpRequest second = HttpRequest.newBuilder(
                trustedBase.resolve("/items/" + id))
            .GET().build();
        return client.sendAsync(
                second, HttpResponse.BodyHandlers.ofString())
            .thenApply(response -> {
                if (response.statusCode() != 200) {
                    throw new IllegalStateException("Item failed");
                }
                return response.body();
            });
    });
~~~

This is a **snippet**, requiring prior declarations of `client`, `lookupRequest`, `trustedBase`, and imports of `java.net.http.*`, `java.util.concurrent.*`. The complete program in a later section can compile and run standalone.

In the example:
- `idFuture` completes normally with `42` → the `thenCompose` mapper builds the URI `/items/42` and **initiates the second request**.
- The second request may take I/O time, but **does not** force the thread calling `thenCompose` to wait synchronously on `client.send`.
- If the first request fails (network, HTTP status converted to an exception by the mapper, invalid parse), the mapper does not run and the second request **is not initiated by this branch**.
- If the second request encounters an error, `titleFuture` completes exceptionally according to the dependency; do not automatically turn errors into an empty string.

**Do not use untrusted data as an arbitrary URL:** if the first server returns an arbitrary URL and the code calls `URI.create(value)` to fetch immediately, there is a risk of SSRF/crossing trust boundaries. The demo only parses a numeric ID and constructs a path under the **same trusted loopback base**. In real systems, validate IDs, path encoding, host/redirect policies, and credential scope.

## 4. The Nested Future Trap with `thenApply`

An error that compiles but produces an unintended type:

~~~java
CompletableFuture<Integer> id =
    CompletableFuture.completedFuture(42);

// mapper returns CompletableFuture<String>:
CompletableFuture<CompletableFuture<String>> nested =
    id.thenApply(n -> CompletableFuture.completedFuture(
        "item-" + n));
~~~

The result of `thenApply` is **U**, which in this case is itself `CompletableFuture<String>`. So the outer type is `CompletableFuture<CompletableFuture<String>>`. `nested.join()` only gives an **inner future**, not yet a `String`.

The right fix:

~~~java
CompletableFuture<String> flat =
    id.thenCompose(n -> CompletableFuture.completedFuture(
        "item-" + n));
~~~

`flat.join()` is already a `String` because `thenCompose` flattens one layer of stage. Similarly with HTTP:

~~~java
// Syntactically valid but has a nested future:
CompletableFuture<CompletableFuture<HttpResponse<String>>> nested =
    id.thenApply(n -> client.sendAsync(
        requestFor(n), HttpResponse.BodyHandlers.ofString()));

// Has a single future directly representing the second request's result:
CompletableFuture<HttpResponse<String>> flat =
    id.thenCompose(n -> client.sendAsync(
        requestFor(n), HttpResponse.BodyHandlers.ofString()));
~~~

The two HTTP snippets assume `client` and the method `requestFor(int)` are already declared; they are used to **compare signatures**, not as standalone programs. In a real pipeline, the `flat` type makes it easier to attach `thenApply(HttpResponse::body)`, `exceptionally`, and timeouts.

**Do not "fix" it by doing `thenApply(n -> client.sendAsync(...).join())`**. That approach blocks the thread executing the callback until the second HTTP request finishes, losing the asynchronous benefit of the pipeline. Use `thenCompose` to return the stage instead of waiting for the stage.

## 5. Standalone Example A: Verifying Nested/Flattened Types

Save the complete file as **`ApplyComposeTypesDemo.java`**:

~~~java
import java.util.concurrent.CompletableFuture;

public class ApplyComposeTypesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
            CompletableFuture.completedFuture(7);

        CompletableFuture<CompletableFuture<String>> nested =
            source.thenApply(n ->
                CompletableFuture.completedFuture("item-" + n));

        CompletableFuture<String> flat =
            source.thenCompose(n ->
                CompletableFuture.completedFuture("item-" + n));

        System.out.println("nested: " + nested.join().join());
        System.out.println("flat: " + flat.join());
    }
}
~~~

Compile with Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 ApplyComposeTypesDemo.java
java ApplyComposeTypesDemo
~~~

Verified stdout:

~~~text
nested: item-7
flat: item-7
~~~

The two lines are identical **in value**, but the statements retrieving the value differ: `nested.join().join()` requires two joins because of two future layers, whereas `flat.join()` only needs one. This is purely a type demonstration; both inner futures are already completed, so **do not use it to benchmark asynchronous speed**.

## 6. Standalone Example B: Loopback HTTP with Two Dependent Requests

Now let's apply `thenApply` + `thenCompose` in **a complete Java 17+ program**, without Internet dependency.

Demo protocol:
- `GET /users/alice` → HTTP `200`, body `42`.
- Use `42` to build `GET /items/42` → HTTP `200`, body `Java NIO`.
- Next `thenApply` converts the title to `JAVA NIO`.
- `GET /missing` → HTTP `404`. The `bodyIfOk` helper will throw `IllegalStateException` and `exceptionally` returns the string `fallback`.

The server uses `com.sun.net.httpserver.HttpServer` from the `jdk.httpserver` module, bound to **loopback `127.0.0.1`** with dynamic port `0`; the client uses `java.net.http.HttpClient`. Both live in the **same JVM**. For deterministic output, the program **does not print thread execution order**, only printing data after the futures complete.

Save the complete file as **`DependentHttpDemo.java`**:

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
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class DependentHttpDemo {
    static void reply(HttpExchange ex, int status, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type",
            "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = ex.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        try {
            String path = ex.getRequestURI().getRawPath();
            if (!"GET".equals(ex.getRequestMethod())) {
                reply(ex, 405, "only GET");
            } else if ("/users/alice".equals(path)) {
                reply(ex, 200, "42");
            } else if ("/items/42".equals(path)) {
                reply(ex, 200, "Java NIO");
            } else {
                reply(ex, 404, "missing");
            }
        } finally {
            ex.close();
        }
    }

    static String bodyIfOk(HttpResponse<String> response) {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", DependentHttpDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();

            HttpRequest lookup = HttpRequest.newBuilder(
                    base.resolve("/users/alice"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();

            CompletableFuture<Integer> idStage = client.sendAsync(
                    lookup, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(DependentHttpDemo::bodyIfOk)
                .thenApply(Integer::parseInt);

            CompletableFuture<String> titleStage = idStage.thenCompose(
                id -> {
                    HttpRequest request = HttpRequest.newBuilder(
                            base.resolve("/items/" + id))
                        .timeout(Duration.ofSeconds(3))
                        .GET().build();
                    return client.sendAsync(
                            request, HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8))
                        .thenApply(DependentHttpDemo::bodyIfOk);
                });

            CompletableFuture<String> formattedStage = titleStage.thenApply(
                title -> title.toUpperCase(Locale.ROOT));

            System.out.println("id: " + idStage.join());
            System.out.println("title: " + titleStage.join());
            System.out.println("formatted: " + formattedStage.join());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            CompletableFuture<String> fallback = client.sendAsync(
                    missing, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
                .thenApply(DependentHttpDemo::bodyIfOk)
                .exceptionally(error -> "fallback");

            System.out.println("missing: " + fallback.join());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Compile and Run

Use JDK 17 or newer:

~~~bash
javac --release 17 -encoding UTF-8 DependentHttpDemo.java
java DependentHttpDemo
~~~

Stdout verified by compiling with `--release 17` and running a real HTTP server/client over TCP loopback:

~~~text
id: 42
title: Java NIO
formatted: JAVA NIO
missing: fallback
~~~

**Why is the port not printed?** The server binds port `0` so the OS chooses an available port; the client retrieves it via `server.getAddress().getPort()`. The actual port changes, but the printed pipeline results do not depend on the port number.

### Step-by-Step Program Analysis

1. **`HttpServer`:** routes `/users/alice` and `/items/42` return a `text/plain; charset=utf-8` payload. Unknown routes return 404, and other methods return 405. This is a demonstration server; there is no database, login, or JSON parser.
2. **`HttpClient`:** a single client is created outside the pipeline and reused for all requests, with a connect timeout and preferred HTTP/1.1. Do not create a new client inside each callback.
3. **`idStage`:** `sendAsync` returns `CompletableFuture<HttpResponse<String>>`; `thenApply(bodyIfOk)` throws an exception if the response is not 200; `thenApply(Integer::parseInt)` converts the string `"42"` into `int 42`.
4. **`titleStage`:** `idStage.thenCompose(id -> ...)` only builds the `/items/42` request after having the ID. The mapper returns **the future of the second `sendAsync`**, already mapped to `String`. `thenCompose` flattens it into `CompletableFuture<String>`.
5. **`formattedStage`:** `thenApply` is a pure data transformation: `Java NIO` becomes `JAVA NIO`, without issuing another HTTP request.
6. **`join()`:** is only called **after the stages have been created** and at the boundary to print results. It can block the `main` thread; the pipeline does not use `join` inside callbacks.
7. **`fallback`:** HTTP `404` can still return a successful `HttpResponse` at the transport layer; `bodyIfOk` throws `IllegalStateException`, the stage transitions to exceptional, and `exceptionally` recovers the string `fallback`.
8. **Resource cleanup:** `try/finally` stops the HTTP server after both chains have been awaited on the normal path. In real systems, any still-pending futures must also be managed when an error causes `main` to exit early; the demo is not a production lifecycle manager.

### Why Does `idStage.join()` Appear Before `titleStage.join()` and Still Stay Asynchronous?

Because `titleStage` and `formattedStage` **were already declared/registered before** `join` appeared. When the first request returns the ID, the second HTTP request is triggered automatically by the dependency. The final `join` calls only exist so the console demo waits for results before the process exits.

If you wrote `idStage.join()` **between** fetching the ID and creating `titleStage`, the caller would wait in the middle and lose the benefit of pipeline composition. A better approach for asynchronous applications is to return `CompletableFuture<String>` to the caller, rather than calling `join` immediately inside a service method.

## 7. Type-Flow: Tracking Data Types to Avoid Mistakes

Write down the type of each stage explicitly:

| Expression | Return Type |
|---|---|
| `client.sendAsync(req, BodyHandlers.ofString())` | `CompletableFuture<HttpResponse<String>>` |
| `.thenApply(HttpResponse::body)` | `CompletableFuture<String>` |
| `.thenApply(Integer::parseInt)` | `CompletableFuture<Integer>` |
| `.thenApply(id -> client.sendAsync(...))` | `CompletableFuture<CompletableFuture<HttpResponse<String>>>` |
| `.thenCompose(id -> client.sendAsync(...))` | `CompletableFuture<HttpResponse<String>>` |
| `.thenCompose(id -> client.sendAsync(...).thenApply(HttpResponse::body))` | `CompletableFuture<String>` |
| `.thenApply(s -> s.toUpperCase(Locale.ROOT))` on a string stage | `CompletableFuture<String>` |
| `.thenAccept(System.out::println)` | `CompletableFuture<Void>` |
| `.thenRun(() -> metric.increment())` | `CompletableFuture<Void>` |

`thenApply` is a **map** operation on a value; `thenCompose` is analogous to **flatMap** with an asynchronous data source. Do not choose based merely on "which method sounds more async"; look at **the type the lambda returns**.

Decision question:

> Does my lambda return an already-available **U**, or does it return a **CompletionStage<U>** that I have to wait for?

- Returns U → `thenApply`.
- Returns `CompletionStage<U>` → `thenCompose`.
- Only need a side action and no new value → `thenAccept` or `thenRun`, while managing side effects and exceptions.
- Need to coordinate **two independent results** → `thenCombine`/`allOf` (different from sequential dependency problems).

## 8. Chaining Dependent Steps Does Not Mean Running in Parallel

Two dependent requests:

~~~text
t0: GET /users/alice starts
t1: User response completes, parse ID = 42
t2: GET /items/42 starts
t3: Item response completes, format title

        Request #1 ────────┐
                           └── Request #2 ─────────┐
                                                   └─ Format
~~~

Because the second request **depends on the first request's ID**, you cannot have both requests running concurrently from the start and still preserve correct semantics.

Conversely, if you need to fetch `/settings` and `/profile` without mutual dependency, initiate both futures and use `thenCombine`:

~~~java
CompletableFuture<String> settings = client.sendAsync(
        settingsRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body);

CompletableFuture<String> profile = client.sendAsync(
        profileRequest, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body);

CompletableFuture<String> combined = settings.thenCombine(
    profile, (a, b) -> "settings=" + a + ", profile=" + b);
~~~

This is a snippet requiring `client`, `settingsRequest`, `profileRequest`, and imports of `java.net.http.*` / `java.util.concurrent.*`. The two `sendAsync` calls are initiated **independently**, so they **can overlap** during HTTP execution, though actual concurrency depends on client/server/connection limits. `thenCombine` runs after **both** complete normally.

`CompletableFuture.allOf(f1, f2, ...)` also waits for a group of futures to complete, but **returns `CompletableFuture<Void>`**, without automatically collecting a result list or guaranteeing that every task succeeds. When you need the values, access the component futures after `allOf` and manage exceptions/cancellation.

If request B's data needs result A, **do not use `allOf` to pretend parallelism**; express the dependency with `thenCompose`.

## 9. Error Propagation Across Steps

A stage can end:
- **Normally:** with a result value, including `null` if the API allows it.
- **Exceptionally:** network error, exception in mapper, body subscriber, parse error, or cancellation.
- **Cancelled:** the future is cancelled per `CompletableFuture` semantics; cancellation is also treated as a special form of completion with an exception.

For the chain:

~~~text
HTTP 1 -> validate status -> parse ID -> HTTP 2 -> validate -> format
                │
                ├── HTTP status error converted to exception by app
                │
                └── parse / network error
                         │
                         ▼
                Subsequent success-only steps are skipped
                         │
                         ▼
                    exceptionally / handle
~~~

**Rule:** `thenApply` and `thenCompose` only run their callbacks when the previous stage **completes normally**. If the previous stage completed exceptionally, the dependent stage normally also completes exceptionally and the success mapper is not called. If the mapper's lambda itself throws an exception, the **returned stage** completes exceptionally.

### 9.1. HTTP Status Is Not an Exception by Default

With `sendAsync(request, BodyHandlers.ofString())`:
- HTTP `200`: the future completes normally with `HttpResponse`, as expected.
- HTTP `404`: the future **can also complete normally** with `HttpResponse` and `statusCode() == 404`.
- Connection/DNS/I/O timeout errors: the future can complete exceptionally.

Therefore, this snippet is easy to get wrong:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
    .thenApply(HttpResponse::body)
    .exceptionally(error -> "not found");
~~~

If the server returns 404 **normally**, the `exceptionally` branch **does not necessarily run**. The snippet above will read the 404 body and treat it as successful data. Status must be checked in a mapper:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() == 404) {
            throw new IllegalStateException("Not found");
        }
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    })
    .exceptionally(error -> "fallback");
~~~

This is a snippet requiring `client` and `request`. In a real API, use an **exception type or error model** to distinguish statuses 404, 401, 429, 500, parse errors, and transport errors. Blindly falling back on every exception can mask security errors or cause users to see misleading data.

### 9.2. `exceptionally`, `handle`, and `whenComplete`

| API | When does it run? | Can it change the final value? | Common use |
|---|---|---|---|
| `exceptionally(ex -> fallback)` | When the previous stage is exceptional | Yes, returns **the same type T** to recover | Intentional fallback |
| `handle((value, error) -> result)` | When the stage completes normally **or** exceptionally | Yes, can change to type U | General transformation of both branches |
| `whenComplete((value, error) -> {...})` | When the stage completes in either state | Normally keeps the original result/exception; throwing in the callback can affect it | Logging/metrics/tracing |
| `thenApply(value ->...)` | When the previous stage completes normally | Yes, returns U | Transforming successful data |
| `thenCompose(value -> stage)` | When the previous stage completes normally | Yes, combines with the new stage | Dependent asynchronous step |

Example:

~~~java
CompletableFuture<String> pipeline = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
    .thenApply(response -> {
        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                "HTTP " + response.statusCode());
        }
        return response.body();
    })
    .whenComplete((body, error) -> {
        if (error != null) {
            System.err.println("HTTP pipeline failed");
        }
    })
    .exceptionally(error -> "unavailable");
~~~

This snippet uses logging without URI/token/response body. Here `whenComplete` is an observation side effect, and `exceptionally` is a recovery step; you do not need both simultaneously unless required.

**Placement trap:** if you place `exceptionally(error -> "42")` **before** `thenCompose`, the second step could be triggered with the fallback ID even though the first request failed. If you only want a fallback **after the entire pipeline fails**, attach `exceptionally` at the end. Where catch/recovery sits in the graph is part of business semantics.

### 9.3. Differences Between `join` and `get`

- `future.join()` returns the value or throws `CompletionException` (unchecked) for exceptional completion; cancellation may throw `CancellationException`.
- `future.get()` returns the value or throws `ExecutionException` (checked), `InterruptedException`; the `get(timeout, unit)` overload also throws `TimeoutException`.
- `join` can **block the calling thread**, even though the pipeline was initiated non-blocking. Do not call `join()` inside a lambda to wait for the next HTTP call — use `thenCompose`.
- When handling errors, you may need to inspect `getCause()` instead of displaying an unclassified `CompletionException` chain; do not log sensitive content from requests/bodies.

## 10. Threads and the `Async` Suffix

API names can be misleading: `thenCompose` without the `Async` suffix still **chains an asynchronous task** if the lambda returns `sendAsync`. `Async` in the method name primarily governs **how the callback is scheduled**, not the map/flatMap semantics.

| Method | Role | Executor Selection |
|---|---|---|
| `thenApply(fn)` | Map T → U, no forced offload | Callback may run on the thread completing the stage or another caller per CF rules |
| `thenApplyAsync(fn)` | Map T → U with async scheduling | The stage's default async execution facility, usually the ForkJoin common pool for default `CompletableFuture` |
| `thenApplyAsync(fn, executor)` | Map T → U on the specified executor | Application manages executor and capacity |
| `thenCompose(fn)` | Flat-map T → CompletionStage<U> | Mapper may run inline while the stage completes |
| `thenComposeAsync(fn)` | Flat-map with asynchronously scheduled mapper | Default async execution facility |
| `thenComposeAsync(fn, executor)` | Flat-map with mapper running on the specified executor | Application chooses pool; HTTP exchange is still managed by HttpClient |

**Do not rely on thread names/thread IDs** of callbacks in functional tests. For non-async dependent stages, Java does not guarantee always running on a specific thread; the callback may run on the thread completing the stage or another thread interacting with completion. Even when `thenApplyAsync` uses a custom executor, once the lambda returns, subsequent completion has its own scheduling per the implementation.

### When Is a Dedicated Executor Needed?

Tasks like small JSON parsing and ID conversion can usually use regular `thenApply`. If the parse/normalize step is genuinely CPU-heavy, use a bounded CPU pool:

~~~java
ExecutorService cpu = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<String> parsed =
        responseStage.thenApplyAsync(
            response -> expensiveParse(response.body()), cpu);
    String result = parsed.join();
    // Process result in the application.
} finally {
    cpu.shutdown();
}
~~~

This is a **snippet** requiring `import java.util.concurrent.*`, assuming `responseStage` is `CompletableFuture<HttpResponse<String>>` and `expensiveParse` is defined by the application. Do not place `cpu.shutdown()` before tasks needing the CPU pool finish; avoid executors with unbounded task queues under high load. In production, also manage active tasks, queue bounds, rejection, and deadlines.

Do not use `thenApplyAsync` just to "turn HTTP into async": `sendAsync` already initiates asynchronous I/O. Adding unnecessary thread hops can increase context-switching overhead and latency.

**Be careful with the default common pool:** long blocking tasks in the common pool can slow down many parts of the application. Do not run `client.send(...)` or arbitrary `Thread.sleep` inside common-pool callbacks; for dependent HTTP requests, use `thenCompose` and `sendAsync`.

## 11. Per-Request Timeout vs. Whole-Pipeline Timeout

In the real example, each request is configured with `HttpRequest.Builder.timeout(Duration.ofSeconds(3))`. If there are two dependent requests:

~~~text
Request #1: takes up to its own timeout
                       │
                       ▼
Request #2: takes up to its own timeout
                       │
                       ▼
Entire pipeline: can take longer than a single timeout
~~~

**Do not infer** that "setting a 3-second timeout on each request means the whole chain finishes within 3 seconds." If request 1 takes nearly 3 seconds and request 2 takes nearly 3 seconds, the total time can exceed 3 seconds, not counting parsing, queueing, callbacks, and scheduling.

### `orTimeout` and `completeOnTimeout` (Java 17)

~~~java
CompletableFuture<String> result =
    dependentPipeline.orTimeout(5, TimeUnit.SECONDS);
~~~

`orTimeout` completes the future with `TimeoutException` when the specified time elapses without completion; **it returns the same CompletableFuture itself** (it does not create a separate child future). `completeOnTimeout(fallback, timeout, unit)` also acts on the target future itself, but completes normally with `fallback` if the deadline arrives first.

**Very important:** marking a future as timed out **is not automatically proof that the HTTP exchange has stopped or that the server has not processed the request**. Cancellation and network operation lifecycles must be managed by policy; cancellation in `HttpClient` is best effort.

If you want an **end-to-end** deadline across multiple requests, compute a shared deadline from `System.nanoTime()` and pass the remaining budget to each request when appropriate; then combine with a pipeline timeout at the boundary. Also account for retries/backoff, not just the two HTTP requests.

### Timeout vs. Cancel

- Request timeout: limits response time via `HttpRequest.timeout`, which can lead to `HttpTimeoutException`.
- `CompletableFuture.orTimeout`: transitions the future's state when not yet finished.
- `future.cancel(true)`: requests cancellation of the stage; in default `HttpClient`, cancellation-supporting futures may attempt to cancel the HTTP exchange. There is no guarantee on when cancellation takes effect; downstream may already have received the request.
- If a dependent future is cancelled, **do not assume** all upstream/downstream stages stop immediately; it depends on future type, stage structure, and implementation.

**Do not use timeout as a transaction rollback mechanism.** If the second request is a POST creating an order, timing out does not prove the order was not created.

## 12. Resource Issues and HTTP Body Correctness

`HttpResponse.BodyHandlers.ofString()` in the demo converts the body into a `String`. When the stage completes normally, the application already has the returned string to parse and does not need to hold an unread `InputStream`.

With `BodyHandlers.ofInputStream()`, the HTTP future can complete and return `HttpResponse<InputStream>` **before the body is fully read by the application**. If you only use `thenApply(HttpResponse::body)` to obtain the stream and do not close it, connections/resources can be held:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
    client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    try (InputStream stream = response.body()) {
        // Read within payload limits; or close when no longer needed.
    } catch (IOException error) {
        // Log/recover appropriately for the application context.
    }
});
~~~

This is a snippet requiring `import java.io.*`, `java.net.http.*`, `java.util.concurrent.*`, assuming `client` and `request` exist. **The actual read/parse logic is not written** in the snippet because it depends on the protocol; the goal is to show that the stream must be closed.

If the chain can complete exceptionally **after the stream has been created**, ensure something is responsible for the corresponding cleanup. `BodyHandlers.ofLines()` has a `Stream<String>` that must be closed when unused; `ofPublisher()` requires a subscriber that requests data/cancels according to proper semantics.

**HTTP status and untrusted data:** body length, charset, JSON schema, and URLs from responses must all be validated. A `thenApply(Integer::parseInt)` will throw if the body is not numeric, which should not be masked with a default fallback `0` if the next request will use that ID to update a critical resource.

## 13. Chaining Callbacks Properly to Avoid Hard-to-Control Side Effects

### 13.1. Do Not Build a Request Before Having the ID

Dependency mistake:

~~~java
// Do not have ID from request #1 yet, but already trying to build request #2.
HttpRequest request2 = HttpRequest.newBuilder(
    URI.create("https://api.example.org/items/" + unknownId))
    .GET().build();
~~~

This is **intentionally wrong code**; `unknownId` does not exist and it is not a runnable program. In real code, construct the second URI **inside the `thenCompose` mapper**, after the ID has been parsed/validated.

### 13.2. Do Not Confuse Side Actions with Result Transformation

`thenAccept` receives a value but returns `CompletableFuture<Void>`. If you later want to keep using the result for a dependent request, do not put `thenAccept(System.out::println)` in the middle and then try to get the ID back:

~~~java
CompletableFuture<Void> logged =
    idStage.thenAccept(id -> System.out.println(id));
// logged does not carry Integer for thenCompose to build a request from id.
~~~

This is a snippet assuming `idStage` is `CompletableFuture<Integer>`. If you want to observe while keeping the result, use `whenComplete((id, error) -> ...)` (with appropriate logging) or attach a separate `thenAccept` **branch** so you do not lose the type of the main pipeline.

### 13.3. Do Not Count Requests by Callback Count

A stage can have multiple dependent branches. If you call `idStage.thenCompose(...)` **twice** with two lambdas that send HTTP, when the ID is ready both lambdas can initiate **two HTTP requests**. An immutable stage does not mean downstream side effects happen only once across the entire graph.

Example:

~~~java
CompletableFuture<String> a =
    idStage.thenCompose(id -> sendDetails(id));

CompletableFuture<String> b =
    idStage.thenCompose(id -> sendDetails(id));
~~~

This is an **illustrative-only** snippet; `sendDetails(int)` is a method the application must write. If you want two consumers to share **the same second-request result**, create a single `detailsStage` and attach multiple dependent stages to it:

~~~java
CompletableFuture<String> detailsStage =
    idStage.thenCompose(id -> sendDetails(id));

CompletableFuture<Integer> lengthStage =
    detailsStage.thenApply(String::length);
CompletableFuture<String> upperStage =
    detailsStage.thenApply(String::toUpperCase);
~~~

Both snippets require an existing `idStage`; production code must account for Unicode encoding/Locale when uppercasing. **Control the number of HTTP exchanges** by where `sendAsync` is created, not by the number of `thenApply` calls.

### 13.4. Limiting Side Effects and Concurrent State

In real systems:
- Do not mutate unsynchronized `ArrayList` / `HashMap` from multiple callbacks on different threads.
- Use immutable DTOs when possible; if shared state is needed, use concurrent collections, atomic operations, or an owner-thread model.
- Limit in-flight requests; do not create thousands of `thenCompose` chains when users send unbounded bursts.
- Log with trace ID/correlation ID, but redact `Authorization`, cookies, tokens, and sensitive data in URLs.
- Do not perform heavy parsing directly on HTTP completion threads; separate onto a CPU executor if metrics prove it is needed.

## 14. Quick API Decision Table

| Problem | Suggested API | Result |
|---|---|---|
| Convert `HttpResponse<String>` to `String body` | `thenApply(HttpResponse::body)` | Body future |
| Parse body text into ID | `thenApply(Integer::parseInt)` | ID future |
| Only issue next HTTP after having ID | `thenCompose(id -> client.sendAsync(...))` | New response future, unnested |
| CPU-heavy data mapping on a dedicated pool | `thenApplyAsync(fn, cpuExecutor)` | Result future on specified executor |
| Run mapper async on a dedicated pool | `thenComposeAsync(fn, executor)` | Future of the returned stage's result |
| Two independent requests, need both | `thenCombine` | Combined result future |
| Wait for a group of requests and collect results manually | `allOf` + read component futures | Future signaling group completion |
| Only log final result, keep type | `whenComplete` | New stage preserving original result/exception on normal path |
| Return fallback for classified errors | `exceptionally` or `handle` | Recovered future |
| Stop waiting for a pipeline after a deadline | `orTimeout` + cleanup/cancel policy | Timed-out future, no guarantee HTTP rolled back |
| Need a value at a sync boundary | `join`/`get` | Blocks caller; use intentionally |

There is no single composition operator that fits every request. **Dependency shape** decides: map a value, flat-map another stage, or combine multiple independent stages.

## 15. Common Mistakes and How to Fix Them

| Mistake | Problem | Fix |
|---|---|---|
| Calling `sendAsync` in `thenApply` and expecting `HttpResponse` | Creates `CompletableFuture<CompletableFuture<HttpResponse>>` | Use `thenCompose` |
| Calling `join` inside a mapper before the second request | Blocks the completion thread | Return `CompletionStage` from the mapper |
| Treating `thenCompose` as automatic parallel execution | Second request depends on the prior stage | Distinguish dependency from `thenCombine` |
| Assuming `thenApply` always runs on a separate worker | Non-Async methods do not guarantee a thread | Keep callbacks fast; use `thenApplyAsync` when needed |
| Using `thenApplyAsync` just to make `send` async | `client.send(...)` still blocks the worker | Use `client.sendAsync(...)` |
| Not checking `response.statusCode()` | 404/500 can still be a normal HTTP result | Validate status before parsing |
| Using `exceptionally` for all errors to return ID=0 | Hides network/auth/parse errors, causes wrong requests | Classify errors and fail closed when needed |
| Placing fallback mid-pipeline and accidentally issuing the second request | Success stages after fallback run again | Place recovery per business semantics |
| Thinking `join` does not block because the source is a future | `join` waits until completion | Only join at boundaries where truly needed |
| Putting `thenAccept` mid-chain while wanting to keep using ID | Returns `CompletableFuture<Void>` | Use `thenApply` or keep `idStage` |
| Two `thenCompose` branches calling HTTP and assuming 1 request | Each lambda can create its own exchange | Share a single result stage |
| Reading a response stream without closing it | Holds network resources/connections | Try-with-resources / cancel |
| Setting a 3s timeout per request and thinking the whole chain ≤3s | Request durations add up | Global deadline/budget + per-request timeout |
| Thinking `orTimeout` means the server hasn't processed a POST | Timeout only changes future state | Idempotency/reconciliation/cancellation |
| Taking a URL from a response and calling `sendAsync` directly | SSRF/credential leak risk | Whitelist hosts, validate path/redirects |
| Using the common pool for unbounded CPU/blocking work | Thread starvation, high latency | Bounded executor, fast callbacks |
| Creating a new HTTP client per stage | Loses resource reuse | Reuse an appropriate `HttpClient` |
| Not checking `Integer.parseInt` exceptions | Invalid strings make the chain exceptional | Validate data/exception policy |
| Assuming `allOf` returns a list of responses | `allOf` returns `CompletableFuture<Void>` | Read each future afterward |
| Swallowing `CompletionException` while debugging | Loses root cause | Classify causes and log with control |

## 16. Practice Exercises

1. Write the return type of `client.sendAsync(req, BodyHandlers.ofString())`, then chain `thenApply(HttpResponse::body)`. What is the type of the final stage?
2. If `CompletableFuture<Integer> id` calls `id.thenApply(n -> client.sendAsync(requestFor(n), handler))`, what is the result type? How do you fix it to become `CompletableFuture<HttpResponse<String>>`?
3. In the pipeline `lookup → parse ID → fetch details`, which steps are `thenApply` and which is `thenCompose`?
4. When the first HTTP request returns `404`, does `sendAsync` automatically put an exception into the future? When will the `thenCompose` mapper be skipped?
5. A parse `Integer.parseInt("oops")` throws an error. Will the second request in `thenCompose` be initiated by that branch?
6. Why should you not write `thenCompose(id -> client.sendAsync(...).join())`? Besides blocking, how does that syntax violate the return type signature?
7. Two requests `/settings` and `/profile` are independent. Should you use `thenCompose` or `thenCombine` to combine results? Why?
8. Does `thenApplyAsync(fn)` guarantee the callback runs on the same HTTP thread that just completed the stage? Does `thenApply(fn)` guarantee running on a separate thread?
9. When CPU-heavy parsing is needed, how do you use a dedicated executor? Who is responsible for shutting down the executor?
10. Why is `join` at the end of a console demo acceptable, while `join` inside an HTTP callback is usually a trap?
11. If `exceptionally(error -> "42")` is placed right after lookup, what will the next `thenCompose` step do when lookup fails?
12. A `BodyHandlers.ofInputStream()` returns a response stream and the pipeline does not close it. Why is that a resource leak even though the future has completed?
13. Two requests each have a 3-second timeout; is the whole chain bounded to 3 seconds?
14. Does `CompletableFuture.orTimeout` automatically send a "cancel request" to the server and roll back business state?
15. In the runnable demo, what HTTP code does `/missing` return? Why is stdout `missing: fallback`?
16. Distinguish `thenAccept`, `whenComplete`, and `thenApply` when you want to both log and preserve the result to create a dependent request.
17. An `idStage` has two `thenCompose` calls, each lambda calling `sendAsync`. How many HTTP requests can be issued? If you only want one, how do you redesign it?
18. Why must you not use an absolute URI returned by the first response to send the second request without validation?
19. What type does `CompletableFuture.allOf(a,b)` return, and how do you retrieve data from `a` and `b` after `allOf` completes?
20. Add a final `thenApply` step to `titleStage` to return `"Item: JAVA NIO"`. Why does this step not need a third HTTP request?

**Answer hints:**
(1) `CompletableFuture<HttpResponse<String>>` then `CompletableFuture<String>`; (2) nested future, fix with `thenCompose`; (3) parse/format use `thenApply`, dependent HTTP uses `thenCompose`; (4) not by default, the app must throw on unacceptable status; (5) no; (6) `join` returns a value instead of `CompletionStage` and blocks the thread; (7) `thenCombine` because the two requests are independent; (8) no, the two APIs have different scheduling policies; (9) `thenApplyAsync(fn, cpuExecutor)`, the application manages the pool; (10) demo boundary intentionally waits, callbacks should not block; (11) the second step can run with the fallback ID; (12) the stream is holding network delivery; (13) no; (14) no; (15) 404 is converted into an exception by the helper and then `exceptionally` recovers; (16) `thenApply` maps, `thenAccept` does not keep the value, `whenComplete` observes; (17) potentially two requests, share a single `detailsStage`; (18) SSRF/credential scope; (19) `CompletableFuture<Void>`, retrieve results from the component futures; (20) it only processes an already-available string.

## 17. Summary

- **`thenApply` = map** value `T → U` when the previous stage completes normally.
- **`thenCompose` = flatMap** value `T → CompletionStage<U>`, creating a dependent async chain without `join` mid-way; avoids nested futures.
- **`HttpClient.sendAsync` + CompletableFuture** helps write HTTP workflows without blocking threads at intermediate steps, though the caller can still block if it insists on `join`.
- **Check HTTP status:** HTTP 4xx/5xx does not by default make the future exceptional; application validation must be explicit.
- **Distinguish dependency and parallelism:** dependent chains use `thenCompose`, independent requests use `thenCombine`/`allOf`.
- **Exception/callback placement determines semantics:** placing a fallback before or after `thenCompose` can change whether the second request is issued.
- **Async thread policy and resources:** avoid uncontrolled heavy/blocking callbacks; handle executors, streaming bodies, timeouts/cancellation, and valid URI access permissions.
- **Two tested Java 17 examples:** `nested` vs. `flat` types, and a loopback HTTP pipeline with real responses, status 404/fallback.

### References

- [Oracle Java SE 17 — CompletableFuture: thenApply, thenCompose, completion policies, orTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 17 — CompletionStage and result types of composition methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 17 — HttpClient.sendAsync and cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 17 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java SE 17 — HttpServer for loopback examples](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
