# Synchronous HTTP with send() and Asynchronous sendAsync() with CompletableFuture in Java 17

Java 11 and later provide HttpClient in the java.net.http package to send HTTP requests. In Java 17, there are two main ways to invoke it:

- **send()** sends a synchronous request: the calling thread waits until a response is received or an error occurs.
- **sendAsync()** sends an asynchronous request: the method immediately returns a CompletableFuture<HttpResponse<T>> so the program can handle the result upon completion.

Both approaches share the same HttpClient, HttpRequest, HttpResponse, and BodyHandler. The key difference lies in **how execution flow and result handling are controlled**. Choose send() when the current thread can wait and sequential logic is easier to follow; choose sendAsync() when coordinating multiple requests, avoiding blocking the calling thread, or combining results with CompletableFuture.

sendAsync does not automatically make an entire program faster. It changes how waiting and task completion are managed. You still need to define timeouts, executors, error handling, concurrency limits, and how the response body is consumed.

## 1. HttpClient in Java 17

HttpClient is the modern HTTP API built into the JDK since Java 11. The client can configure the version, redirects, proxy, authenticator, connect timeout, and executor.

Creating a client:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

What these settings mean:

- connectTimeout limits the time to establish a connection. This is not an overall per-request timeout.
- followRedirects decides how the client handles redirects. NORMAL follows standard redirect rules; NEVER disables redirects; ALWAYS permits all redirects per API policy.
- version is the preferred HTTP version. The client may negotiate or use a different version depending on server capabilities and configuration.

You can create a simple client:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

Reuse one HttpClient across multiple requests rather than creating a new one per call. The client manages connections and can reuse them; constantly creating clients loses pooling benefits and adds overhead.

## 2. Creating an HttpRequest

HttpRequest describes the request to send: URI, method, headers, body, and timeout.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/users/42"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

A POST request with a body:

~~~java
String json = """
        {"name":"Lan","active":true}
        """;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/users"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(json))
        .build();
~~~

BodyPublisher produces request content. Some commonly used publishers:

| BodyPublisher | When appropriate |
| --- | --- |
| noBody() | Requests with no body |
| ofString(text) | Sending text or already-serialized JSON |
| ofByteArray(bytes) | Sending a byte array |
| ofFile(path) | Sending file contents |
| ofInputStream(supplier) | Supplying a stream on demand; requires proper opening and reading management |

Do not set Content-Length manually unless needed; BodyPublisher supplies body metadata to the client. The Content-Type header describes the content format and does not automatically serialize Java objects to JSON. The application must use a JSON library or chosen serialization mechanism to produce the string or bytes.

## 3. Sending Synchronously with send()

send() sends the request and waits for the response. Example:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class SyncHttpExample {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Body: " + response.body());
    }
}
~~~

send() returns only after the response has been processed according to the BodyHandler. While waiting, the calling thread cannot continue executing statements after send().

This method can throw:

- IOException if an I/O error or request/response processing error occurs.
- InterruptedException if the waiting thread is interrupted.

HTTP statuses such as 404 or 500 still produce a normal HttpResponse. They do not automatically turn into an IOException just because the status indicates an error. The application must check response.statusCode() per the API contract.

### Handling InterruptedException

When a method cannot declare InterruptedException and must propagate the error upward, restore the interrupt status before rethrowing:

~~~java
try {
    HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    return response.body();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP request was interrupted", ex);
}
~~~

Never catch InterruptedException and ignore it. An interrupt is an execution control signal; clearing that signal can prevent task-management layers from stopping work properly.

## 4. Sending Asynchronously with sendAsync()

sendAsync() initiates the request and returns a CompletableFuture as soon as the call is set up. The HTTP result becomes available when the future completes:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());
~~~

Return type:

~~~java
CompletableFuture<HttpResponse<T>>
~~~

Where T is the body type chosen by the BodyHandler, such as String, byte[], Path, or InputStream.

Example:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        future.thenAccept(response -> {
            System.out.println("Status: " + response.statusCode());
            System.out.println("Body: " + response.body());
        }).exceptionally(error -> {
            System.err.println("Request failed: " + error);
            return null;
        });

        // Do not call join/get here if the goal is to let the current thread continue.
    }
}
~~~

In a server or desktop application with an event loop or task lifecycle manager, there is no need to block a thread solely to wait for the future. When the example program is a short main method, the JVM may exit after main finishes if no remaining activity keeps the process alive; real examples should run inside an application with an appropriate lifecycle or wait intentionally at the coordination layer.

### sendAsync does not guarantee callbacks always run on a specific thread

sendAsync does not require every stage callback to execute on the thread that called sendAsync. For CompletableFuture methods without the Async suffix such as thenApply or thenAccept, the action may run on the thread completing the future or the thread registering the stage if the future is already complete. Methods with the Async suffix use CompletableFuture's default executor or an explicitly passed executor.

Therefore:

- Do not assume thenApply always runs on the main thread.
- Do not place blocking or CPU-heavy work inside non-Async callbacks if you cannot control the execution thread.
- Use thenApplyAsync(..., executor) or thenAcceptAsync(..., executor) when you need to specify where callbacks run.

## 5. Comparing send() and sendAsync()

| Criterion | send() | sendAsync() |
| --- | --- | --- |
| Return type | HttpResponse<T> | CompletableFuture<HttpResponse<T>> |
| Calling thread | Waits for result | Returns a future for deferred processing |
| I/O errors | Throws IOException directly | Future completes exceptionally |
| Interrupts | Throws InterruptedException | No direct InterruptedException from the call; can cancel future or manage timeouts |
| Combining multiple requests | Usually requires manual thread management or sequential calls | Can use allOf, thenCombine, thenCompose |
| Simple sequential logic | Easy to read | Introduces the future abstraction |
| Asynchronous workflows | Blocks calling thread | Does not block calling thread while waiting for response |
| HTTP 4xx/5xx results | Returns HttpResponse | Future completes normally with HttpResponse |

Do not choose sendAsync simply because it seems "newer". If a command-line tool calls one API and needs the result immediately, send() can be simpler. If a server needs to coordinate multiple independent requests or avoid blocking request-handling threads, sendAsync can be a better fit.

## 6. Processing Results with CompletableFuture

CompletableFuture represents a result that may not yet be available. When the result completes, subsequent processing stages can be chained.

### thenApply: transforming the result

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body);
~~~

thenApply takes the result of the previous stage and returns a new value. In the example, the type is transformed from CompletableFuture<HttpResponse<String>> into CompletableFuture<String>.

### thenAccept: consuming the result without producing a new value

~~~java
CompletableFuture<Void> logged =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenAccept(response ->
                        System.out.println(response.statusCode()));
~~~

thenAccept fits when you only need to perform an action with the result.

### thenRun: running an action without receiving the result

~~~java
CompletableFuture<Void> finished =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding())
                .thenRun(() -> System.out.println("Request completed"));
~~~

thenRun only cares that the previous stage completed normally and does not take the response as a parameter.

### thenCompose: chaining another asynchronous operation

Suppose the first request fetches a user ID and the second request fetches user details. Avoid creating nested CompletableFutures:

~~~java
CompletableFuture<CompletableFuture<User>> nested =
        client.sendAsync(idRequest, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> fetchUserAsync(response.body()));
~~~

Use thenCompose to flatten it:

~~~java
CompletableFuture<User> userFuture =
        client.sendAsync(idRequest, HttpResponse.BodyHandlers.ofString())
                .thenCompose(response ->
                        fetchUserAsync(response.body()));
~~~

thenCompose is useful when the next step also returns a CompletionStage/CompletableFuture.

### thenCombine: combining two independent tasks

If two requests do not depend on each other, they can run concurrently and have their results combined:

~~~java
CompletableFuture<User> userFuture = fetchUserAsync("42");
CompletableFuture<List<Order>> ordersFuture = fetchOrdersAsync("42");

CompletableFuture<UserDashboard> dashboardFuture =
        userFuture.thenCombine(
                ordersFuture,
                UserDashboard::new);
~~~

thenCombine waits for both stages to complete normally and then invokes the combining function.

## 7. Sending Multiple Independent Requests and Waiting for All with allOf()

Example fetching information from multiple endpoints:

~~~java
List<URI> uris = List.of(
        URI.create("https://example.com/a"),
        URI.create("https://example.com/b"),
        URI.create("https://example.com/c"));

List<CompletableFuture<HttpResponse<String>>> futures =
        uris.stream()
                .map(uri -> HttpRequest.newBuilder(uri).GET().build())
                .map(req -> client.sendAsync(
                        req,
                        HttpResponse.BodyHandlers.ofString()))
                .toList();

CompletableFuture<Void> all =
        CompletableFuture.allOf(
                futures.toArray(CompletableFuture[]::new));

CompletableFuture<List<HttpResponse<String>>> responses =
        all.thenApply(ignored ->
                futures.stream()
                        .map(CompletableFuture::join)
                        .toList());
~~~

allOf returns a CompletableFuture<Void> that completes when all input futures complete. Once `all` completes normally, you can join each future to extract its result without further waiting.

Notes:

- If one input future completes exceptionally, allOf also completes exceptionally once all input futures have completed.
- allOf does not return a list of results by itself; keep the list of futures and collect results afterward.
- If there are many requests, bound concurrency according to service capacity, connection pool, and rate limits. Spawning hundreds of thousands of futures simultaneously can put pressure on memory and the system.
- Do not call join() before allOf when aiming for parallel execution, because joining each element sequentially can force the coordinator thread to wait unnecessarily.

### allOf does not bound concurrency automatically

If the request list is very large, you can process in batches or use a mechanism to cap in-flight tasks. Simple batching example:

~~~java
static CompletableFuture<Void> sendInBatches(
        HttpClient client,
        List<URI> uris,
        int batchSize) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    CompletableFuture<Void> chain = CompletableFuture.completedFuture(null);

    for (int start = 0; start < uris.size(); start += batchSize) {
        int from = start;
        int to = Math.min(start + batchSize, uris.size());

        chain = chain.thenCompose(ignored -> {
            List<CompletableFuture<HttpResponse<Void>>> batch =
                    uris.subList(from, to).stream()
                            .map(uri -> HttpRequest.newBuilder(uri).GET().build())
                            .map(request -> client.sendAsync(
                                    request,
                                    HttpResponse.BodyHandlers.discarding()))
                            .toList();

            return CompletableFuture.allOf(
                    batch.toArray(CompletableFuture[]::new));
        });
    }

    return chain;
}
~~~

The next batch begins only after the current batch finishes. This is a simple way to limit concurrency; it can reduce throughput if one slow request holds up the entire batch. High-load systems may need a semaphore, bounded queue, or rate limiter for smoother throttling.

## 8. Error Handling in sendAsync

Errors when sending asynchronous requests typically cause the future to complete exceptionally. Common error-handling operations:

| API | Purpose |
| --- | --- |
| exceptionally(fn) | Convert an error into a fallback value or rethrow an error |
| handle(fn) | Handle both normal results and errors |
| whenComplete(fn) | Observe the result or error for logging or cleanup; not primarily for transforming the result |
| exceptionallyCompose(fn) | On error, chain another asynchronous stage (Java 12+) |

### exceptionally

~~~java
CompletableFuture<String> body =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body)
                .exceptionally(error -> {
                    logFailure(error);
                    return "Fallback content";
                });
~~~

exceptionally turns an error into a normal result if the callback returns a fallback. After this stage, the future can complete normally with the fallback content.

If you do not want to swallow the error, rethrow it:

~~~java
.exceptionally(error -> {
    throw new CompletionException(error);
});
~~~

### handle

~~~java
CompletableFuture<String> outcome =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .handle((response, error) -> {
                    if (error != null) {
                        return "Transport error: " + error.getMessage();
                    }
                    return "HTTP " + response.statusCode();
                });
~~~

handle is called when the previous stage completes either normally or exceptionally. If error is non-null, response is typically null.

### whenComplete

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .whenComplete((response, error) -> {
                    if (error != null) {
                        logFailure(error);
                    } else {
                        logStatus(response.statusCode());
                    }
                });
~~~

whenComplete is suitable for observation and logging. If the whenComplete callback throws an exception, the returned stage can complete exceptionally. Avoid long blocking operations inside this callback.

### Exceptions are often wrapped

When retrieving results with join(), pipeline errors are usually wrapped in CompletionException. With get(), errors can appear as ExecutionException; get() can also throw InterruptedException.

~~~java
try {
    HttpResponse<String> response = future.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    // Handle the actual cause.
}
~~~

Do not just log CompletionException and ignore its cause. Distinguish network errors, timeouts, body handler errors, cancellation, and business callback errors.

## 9. HTTP Error Statuses Do Not Mean an Exceptional Future

This is an important distinction when working with HttpClient:

- Connection, DNS, timeout, or I/O errors can cause the future to complete exceptionally.
- The server returning HTTP 404, 429, or 500 is still a valid HTTP response at the protocol level. The future usually completes normally and response.statusCode() holds that code.

Therefore, you must check the status:

~~~java
CompletableFuture<String> body =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new CompletionException(
                                new IllegalStateException("Unexpected HTTP status: " + status));
                    }
                    return response.body();
                });
~~~

You can create a custom exception type containing status, headers, and response body so upper layers can handle retries or display messages. Do not automatically retry every 4xx/5xx status: retry policy depends on HTTP method, idempotency, status code, Retry-After, and the API contract.

### Separating transport errors and application errors

One organization pattern:

1. Transport layer sends the request and receives HttpResponse.
2. HTTP adapter checks the status and maps error responses to exceptions or appropriate result types.
3. Application layer handles errors according to business rules.

This separation keeps code from confusing "cannot reach the server" with "the server replied that the resource does not exist."

## 10. Connection and Per-Request Timeouts

Two timeouts should be distinguished:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
~~~

- connectTimeout applies to establishing a connection if a new connection is needed.
- HttpRequest.timeout limits the duration for the request; if the response does not arrive within the specified time, the operation may fail with HttpTimeoutException.

With send(), HttpTimeoutException is a form of IOException. With sendAsync(), the future completes exceptionally and the cause may be wrapped in CompletionException when using stages or join().

### Timeouts on CompletableFuture

Java 9 and later provide orTimeout and completeOnTimeout:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .orTimeout(5, TimeUnit.SECONDS);
~~~

orTimeout completes the future exceptionally with TimeoutException if the elapsed time exceeds the limit.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .completeOnTimeout(fallbackResponse, 5, TimeUnit.SECONDS);
~~~

completeOnTimeout completes the future normally with a fallback value on timeout.

Do not confuse a CompletableFuture timeout with reliably cancelling the underlying HTTP request. orTimeout and completeOnTimeout affect the future they are called on; they do not by themselves guarantee that the server stopped processing or that the request was not sent. When you need to bound the request, configure HttpRequest.timeout and define an explicit cancellation policy.

## 11. Cancellation and Its Limits

You can request cancellation of a future:

~~~java
boolean cancelled = future.cancel(true);
~~~

For a future returned by sendAsync, cancelling can ask HttpClient to cancel the corresponding exchange. However:

- It does not guarantee the request has not been sent.
- It does not guarantee the server has stopped processing.
- It does not undo side effects the server has already performed.
- It does not replace timeouts, idempotency, or business-level cancellation mechanisms.

If a request is a POST that creates a transaction, client timeout or cancel does not prove the transaction was not created. To retry safely, design an idempotency key or a transaction-status query mechanism.

Cancellation in CompletableFuture is a form of exceptional completion; dependent stages typically observe the failure via CompletionException/CancellationException as specified by the API. When designing a pipeline, determine which stage is responsible for cleaning up resources and reporting the cancelled state.

## 12. BodyHandler and Reading the Response Body

BodyHandler decides how HttpClient receives and provides the body. Choosing the right handler affects memory usage and resource management.

| BodyHandler | Body type | Suitable for |
| --- | --- | --- |
| ofString() | String | Small or medium JSON/text |
| ofByteArray() | byte[] | Moderately sized binary payloads |
| ofFile(path) | Path | Downloading files to disk |
| discarding() | Void | Only need status/headers, ignore body |
| ofInputStream() | InputStream | Streaming the body; caller must close the stream |
| ofLines() | Stream<String> | Line-by-line text body; must manage stream lifecycle |

### Downloading a file with sendAsync

~~~java
Path destination = Path.of("download.bin");

CompletableFuture<HttpResponse<Path>> download =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofFile(destination));
~~~

BodyHandler.ofFile writes the body to the target file. Explicitly decide the policy when the file already exists and handle file-writing errors. For important data, you can download to a temporary file, verify it, and move it atomically if supported by the filesystem.

### ofInputStream requires closing the stream

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    try (InputStream body = response.body()) {
        body.transferTo(OutputStream.nullOutputStream());
    } catch (IOException ex) {
        throw new CompletionException(ex);
    }
});
~~~

The response may complete as soon as the InputStream is ready to read, while reading the body continues afterward. You must close the stream after use to release resources. If body processing takes a long time, consider where the callback runs and avoid blocking shared executors.

### Only needing status/headers

~~~java
CompletableFuture<HttpResponse<Void>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
~~~

discarding() ignores the body, making it suitable for requests where the application only cares about status/headers or does not need to download content.

## 13. Choosing an Executor for Continuation Work

HttpClient.Builder can accept an executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);

HttpClient client = HttpClient.newBuilder()
        .executor(executor)
        .build();
~~~

The executor configured on HttpClient is used for asynchronous tasks and dependent tasks according to the client API contract. If you manage an executor yourself, ensure an appropriate shutdown policy aligned with the application lifecycle; do not create a new pool per request.

For CompletableFuture, methods with the Async suffix allow passing a specific executor:

~~~java
CompletableFuture<String> parsed =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApplyAsync(
                        response -> parseLargeJson(response.body()),
                        executor);
~~~

This separates HTTP I/O from CPU-heavy processing. However, if the executor has too few threads or an unbounded queue, the workload can stall or grow memory excessively. Size threads and queues according to real load.

Do not use the common pool for long blocking work if it could starve other tasks. For blocking work, use a dedicated bounded executor and manage backpressure.

### Shutting down executors according to lifecycle

If the application creates an executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);
try {
    // Use HttpClient and tasks.
} finally {
    executor.shutdown();
}
~~~

In long-lived applications, the executor is typically managed by dependency injection or the application lifecycle. Do not shut down the executor immediately after dispatching requests if asynchronous tasks still depend on it.

## 14. Sending a POST Request and Handling Results Asynchronously

A fuller example:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class PostAsyncExample {

    static CompletableFuture<String> createUser(
            HttpClient client,
            String json) {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new CompletionException(
                                new IllegalStateException(
                                        "Create user failed with HTTP " + status
                                                + ": " + response.body()));
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        String json = "{\"name\":\"Lan\"}";

        CompletableFuture<String> result =
                createUser(client, json);

        result.whenComplete((body, error) -> {
            if (error != null) {
                System.err.println("Create failed: " + error);
            } else {
                System.out.println("Created: " + body);
            }
        });
    }
}
~~~

This is an illustrative example; the example.com endpoint is not a real user-creation API. Real applications need actual endpoints, authentication, serialization, retry policies, and proper response handling.

## 15. Testing Code That Makes HTTP Calls

Unit tests should not depend directly on a public Internet service. Approaches:

- Use a local mock server to test requests, headers, bodies, statuses, timeouts, and connection errors.
- Inject HttpClient or an adapter interface via constructor so it can be replaced in tests.
- Use a controllable Clock/timeout if logic involves deadlines.
- Separate HttpResponse handling from network invocation so you can test with fake responses.

### Testing status-handling logic independently

~~~java
static String requireSuccess(HttpResponse<String> response) {
    int status = response.statusCode();
    if (status < 200 || status >= 300) {
        throw new IllegalStateException("HTTP " + status);
    }
    return response.body();
}
~~~

This function can be tested without sending a request:

~~~java
// You can use Mockito or a simple test HttpResponse implementation.
// Verify statuses 200, 404, and 500 per contract.
~~~

### Testing exceptional futures

You can use CompletableFuture.failedFuture (Java 9+) to test error-handling logic in higher layers:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IOException("Connection refused"));

CompletableFuture<String> handled =
        failed.exceptionally(error -> "fallback");
~~~

This does not replace integration tests for HttpClient, but it helps test CompletableFuture pipelines without relying on the network.

### Testing timeouts and cancellation

Timeouts and cancellation depend on real schedulers and I/O; tests should use a mock server or local server with controllable latency. Avoid arbitrary long sleeps and avoid public Internet endpoints due to unstable network timings.

## 16. Common Pitfalls

| Mistake | Cause | Fix |
| --- | --- | --- |
| Calling sendAsync then immediately calling join | Turns the calling thread back into a synchronous wait | Only join at the layer that truly needs the result; compose stages when possible |
| Assuming 404/500 makes the future exceptional | Confusing HTTP statuses with transport errors | Check response.statusCode() |
| Forgetting to handle exceptions in the pipeline | Futures can complete exceptionally | Use handle/exceptionally/whenComplete appropriately |
| Using thenApply for heavy blocking work | Callback may run on the thread completing the future | Use thenApplyAsync with a suitable executor |
| Calling allOf and expecting a list of responses | allOf only returns CompletableFuture<Void> | Keep the list of futures and collect results after all complete |
| Sending thousands of requests at once | Unbounded concurrency and memory | Batch, semaphore, or bounded executor |
| Using orTimeout and assuming the request stopped | Future timeout does not guarantee server cancellation | Configure HttpRequest.timeout and design cancellation/idempotency |
| Retrying POST immediately after timeout | Server may have already applied side effects | Use an idempotency key and query status |
| Not closing InputStream from BodyHandlers.ofInputStream | Resource leak | Use try-with-resources |
| Creating an HttpClient per request | Loses connection reuse | Reuse the client |
| Using an unbounded executor for blocking tasks | Queue/threads can grow without bound | Bounded executor and backpressure |
| Catching InterruptedException and ignoring it | Interrupt signal is lost | Restore interrupt flag or propagate |
| Assuming sendAsync runs callbacks on main thread | Stage execution thread depends on stage type/executor | Specify an executor for callbacks requiring control |
| Passing a Java object directly to BodyPublisher | BodyPublisher accepts bytes/text/stream, not raw objects | Serialize with an appropriate library |

## 17. When to Choose send vs. sendAsync?

| Scenario | Suggested choice |
| --- | --- |
| Single request in a CLI needing an immediate result | send() |
| Small batch with simple sequential processing | send() may suffice |
| Server needing not to block coordinator threads during network wait | sendAsync() |
| Multiple independent requests that can run concurrently | sendAsync() + allOf/appropriate collector |
| Subsequent request depends on the previous response | sendAsync() + thenCompose() |
| Two independent sources need to be combined | sendAsync() + thenCombine() |
| Large body needing streaming or file writing | Pick an appropriate BodyHandler; sendAsync can help coordinate |
| Blocking work or needs a dedicated executor | Manage executors explicitly; consider another API if appropriate |
| Needs simple flow, easy debugging, and no concurrency gain | send() |

## 18. Complete Example: Two Parallel Requests Combined

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class CombineRequests {

    static CompletableFuture<String> getBody(
            HttpClient client,
            URI uri) {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "text/plain")
                .GET()
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new CompletionException(
                                new IllegalStateException(
                                        "HTTP " + response.statusCode()));
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        CompletableFuture<String> first =
                getBody(client, URI.create("https://example.com"));
        CompletableFuture<String> second =
                getBody(client, URI.create("https://example.org"));

        CompletableFuture<String> combined =
                first.thenCombine(second,
                        (a, b) -> "First length=" + a.length()
                                + ", second length=" + b.length());

        combined.whenComplete((value, error) -> {
            if (error != null) {
                System.err.println("At least one request failed: " + error);
            } else {
                System.out.println(value);
            }
        });
    }
}
~~~

The example requires importing java.util.concurrent.CompletionException. The two requests are initiated independently before combining, so they can make progress concurrently. When one request has a transport failure or its status is converted into an exception, `combined` also completes exceptionally.

In real applications, consider overall time limits, concurrency limits, and whether bodies can be large. It is unnecessary to load an entire body into a String if you only need metadata or a file.

## 19. Workflow for Designing an Asynchronous HTTP Call

When building an API client:

1. **Reuse HttpClient** with appropriate connection, redirect, proxy, and executor settings.
2. **Build HttpRequest** with explicit URI, method, headers, body publisher, and timeout.
3. **Choose BodyHandler** based on body size and how the body is used.
4. **Call send() or sendAsync()** depending on thread-blocking and task-coordination needs.
5. **Check status code** because HTTP 4xx/5xx are not automatically exceptional errors.
6. **Compose CompletableFutures** using thenApply, thenCompose, thenCombine, or allOf when dependencies match.
7. **Handle errors and cancellation** in a place with clear ownership; distinguish transport errors, timeouts, status errors, and business errors.
8. **Bound concurrency** when there are many requests, and manage executors according to the application lifecycle.
9. **Test with a mock/local server**, especially for timeouts, error statuses, large bodies, and cancellation.

send() and sendAsync() both send HTTP requests via HttpClient, yet serve two different ways of organizing execution flow. send() fits sequential logic that needs a result immediately; sendAsync() paired with CompletableFuture fits when continuing work while waiting on the network, combining multiple requests, or building asynchronous pipelines. Good design must manage response bodies, statuses, timeouts, errors, cancellation, and concurrency rather than merely swapping send() for sendAsync().
