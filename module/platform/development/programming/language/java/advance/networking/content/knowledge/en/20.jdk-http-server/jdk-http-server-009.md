# Configuring Executor, Processing Limits, and Timed Stop

## 1. Problem and Learning Objectives

Java SE 17 provides a lightweight HTTP server in the `jdk.httpserver` module, specifically the `com.sun.net.httpserver.HttpServer` class. A server can receive HTTP requests and return JSON/text in a few lines, but when there are multiple clients, you need to decide **which thread the handler runs on**, **how much work is processed concurrently**, **what response overloaded requests receive**, and **how the server stops so that in-flight requests have a chance to complete**.

Three central APIs/concepts:
- `HttpServer.setExecutor(Executor)` selects the executor that receives HTTP processing tasks. **Must be called before `start()`**.
- `ThreadPoolExecutor`/`Semaphore` allow limiting threads, the task queue, and the number of active business operations. This must be distinguished from the listener's **TCP backlog**.
- `HttpServer.stop(int delay)` stops accepting new exchanges and **waits for existing handlers up to approximately `delay` seconds**, then closes TCP connections. `delay` is in **seconds**; it is not milliseconds, and it is not an executor shutdown command.

After this lesson, you will be able to:
1. Create and configure a JDK `HttpServer` with an executor in the correct order.
2. Explain the default executor, bounded queue, `CallerRunsPolicy`, and `RejectedExecutionException`.
3. Use `Semaphore.tryAcquire()` to return `503 Service Unavailable` when capacity is exhausted instead of blocking indefinitely.
4. Distinguish between backlog, worker count, queue depth, active business operations, request-body limit, and per-client rate limit.
5. Build a handler that closes `HttpExchange` and the response stream explicitly.
6. Explain in detail `stop(0)`, `stop(2)`, which requests get cut off, and why the same instance cannot be restarted.
7. Shut down a custom executor using `shutdown()`, `awaitTermination()`, and best-effort `shutdownNow()`.
8. Run two offline Java 17+ programs on loopback: concurrent requests/503/graceful stop and an 8-byte body limit/413.
9. Design tests with latches, timeouts, and metrics instead of guessing scheduling order.

## 2. Architecture Map: listener → executor → handler

```text
 HTTP clients
      │ TCP connections
      ▼
HttpServer listening socket
      │
      ├─ backlog: pending TCP connection indications
      │
      ▼
HTTP dispatch
      │  executor.execute(handlerTask)
      ▼
  Executor
      │
      ├─ worker thread #1 ─► HttpHandler.handle(exchange A)
      ├─ worker thread #2 ─► HttpHandler.handle(exchange B)
      └─ task queue       ─► pending tasks
                                   │
                      application admission policy
                                   │
                           Semaphore.tryAcquire()
                            ├─ permit -> business logic
                            └─ no permit -> HTTP 503
                                   │
                      sendResponseHeaders + body
                                   │
                             exchange.close()
```

**Each layer has a different responsibility.** `backlog=16` does not mean "16 handlers run simultaneously". `maximumPoolSize=2` does not mean "the server only holds at most 2 HTTP connections". `Semaphore(1)` only limits the business section that acquires a permit; it does not limit all network/HTTP parsing activities outside that section.

Each `HttpExchange` corresponds to one HTTP exchange, with a URI, method, request headers, request body, and response headers/body. A keep-alive connection can serve consecutive exchanges. Do not reuse the same `HttpExchange` for independent requests.

## 3. Essential HttpServer APIs

| API | Role | Remember |
| --- | --- | --- |
| `HttpServer.create(addr, backlog)` | Bind listener | Port `0` uses an ephemeral port in tests |
| `createContext(path, handler)` | Map a path prefix to a handler | Path matching is prefix-based; check exact URI path if needed |
| `setExecutor(executor)` | Choose where handler tasks execute | Only call **before `start()`** |
| `getExecutor()` | Return the configured executor or null | Null usually means the default implementation |
| `start()` | Start the server background thread | Cannot change the executor afterward |
| `getAddress()` | View the address/port the server bound to | Useful for tests without hardcoded ports |
| `stop(delay)` | Close listener, wait for in-flight exchanges with a bound | `delay` is a non-negative number of seconds; cannot restart instance |
| `removeContext(path)` | Stop mapping a context | Does not mean stopping the whole server |

An illustrative snippet:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 16);
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);
server.createContext("/ping", exchange -> {
    byte[] bytes = "pong".getBytes(StandardCharsets.UTF_8);
    try {
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    } finally {
        exchange.close();
    }
});
server.start();

// During shutdown:
server.stop(5);
workers.shutdown();
```

**Code snippet**, lacking imports, full error handling/await termination, and timeouts; not a standalone Java file. In particular, `Executors.newFixedThreadPool(4)` has an **unbounded task queue by factory default**, so do not treat this as a production overload-protection configuration. The two complete programs in later sections use a bounded `ThreadPoolExecutor`.

## 4. Executor Configuration Must Come Before start

According to Java 17 `HttpServer.setExecutor`: the executor must be set **before `start()`**. If the server has already started, `setExecutor(...)` throws `IllegalStateException`.

```text
HttpServer.create / bind
       ↓
createContext(...)
       ↓
create and configure Executor
       ↓
server.setExecutor(executor)
       ↓
server.start()
       ↓
multiple HttpExchanges processed
       ↓
server.stop(graceSeconds)
       ↓
executor.shutdown() + awaitTermination(...)
```

You can create contexts before or after `setExecutor`, but **before calling start**, ensure the listener, contexts, executor, and dependencies are ready.

Wrong:

```java
server.start();
server.setExecutor(Executors.newFixedThreadPool(8));
// IllegalStateException: too late to attach executor
```

If you want to change the number of workers at runtime, you must use safe dynamic configuration of the chosen executor itself (if supported) or replace the server instance via a rolling restart. Do not call `setExecutor` again to replace a running executor.

## 5. Default Executor and the Thread Used to Process Requests

If the application does not call `setExecutor`, or calls `setExecutor(null)`, the JDK HTTP server uses the **default executor**. The Java 17 documentation states that the default implementation **uses the thread created by `start()`**. Do not assume a large thread pool is available by default.

This means:
- A long-blocking handler can noticeably affect other requests when using the default.
- When you want to control throughput and concurrency, you need to provide your own executor.
- `getExecutor()==null` is not an error; it simply indicates no explicit executor was set.
- If a different server implementation/provider is used, you must check that provider's own documentation.

`Executor` only requires `execute(Runnable)`; `ExecutorService` adds `shutdown`, `awaitTermination`, and `shutdownNow` for lifecycle management.

## 6. Executor Types and Trade-offs

| Executor | Advantage | Risk |
| --- | --- | --- |
| `Runnable::run` | Simple, creates no new workers | Handler runs immediately on the submitting thread, may block the dispatcher |
| `Executors.newFixedThreadPool(n)` | Fixed worker count | Default queue is unbounded; pending work can grow very large |
| `Executors.newCachedThreadPool()` | Scales workers under load | Thread count can grow sharply with slow I/O |
| `ThreadPoolExecutor` + bounded queue | Bounds worker threads and queue | Needs a rejection policy + admission at the appropriate layer |
| Custom `Executor` | Flexible | Must ensure no HTTP tasks are lost and standard lifecycle is maintained |

An executor with 2 workers **does not** directly guarantee the system has only 2 concurrent TCP connections. The HTTP server/OS still holds connection state, input buffers, and pending requests. Therefore, a bounded design must cover **all major resources**, not just worker threads.

## 7. Bounded ThreadPoolExecutor and CallerRunsPolicy

Illustrative configuration:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(4),
        new ThreadPoolExecutor.CallerRunsPolicy());

server.setExecutor(pool); // before server.start()
```

**Code snippet**, requires imports and an already-created `server` variable.

- `corePoolSize=2`, `maximumPoolSize=2`: at most 2 worker threads managed by the pool.
- `ArrayBlockingQueue<>(4)`: at most 4 tasks waiting **in the executor queue**.
- `CallerRunsPolicy`: when the pool and queue are full, a rejected task can **run immediately on the thread calling `execute()`**, instead of being dropped. For an HTTP server, the thread calling `execute` may be the **dispatcher**.

**Important warning:** `CallerRunsPolicy` does not create a global limit that "only 2 handlers execute": a task can run **outside the workers** on the caller thread. It can also cause the dispatcher to be blocked by a slow handler, increasing latency and affecting other connections. If the executor is already shut down, this policy **drops** the rejected task without running it. This is a trade-off that must be tested, not a universally good default configuration in every environment.

## 8. Rejection Policy Does Not Automatically Produce HTTP 503

When the executor is saturated, `ThreadPoolExecutor` invokes `RejectedExecutionHandler`:

| Policy | Behavior | Risk for HTTP |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Does not guarantee an HTTP 503 is sent to the client |
| `CallerRunsPolicy` | Runs task on caller thread if executor is still active | Can block the dispatcher/accept path |
| `DiscardPolicy` | Silently drops the task | Client may wait until timeout without any response |
| `DiscardOldestPolicy` | Drops a waiting task, tries to enqueue the new task | Older requests can be lost, hard to guarantee fairness |

**Do not assign an HTTP status to executor-level rejection by guesswork.** The HTTP handler may not have been dispatched yet to have the ability to call `exchange.sendResponseHeaders(503,...)`.

Overload protection patterns need multiple layers: reverse proxy/ingress connection limits, thread/queue limits, handler-level admission control, per-tenant quotas, and request-body/time limits. To guarantee every accepted request receives a 503 when exceeding quota, you need to design sufficient capacity for the error handler or admission at a layer **before** tasks must queue in the executor.

## 9. TCP Backlog Is Not Max Request Count

`HttpServer.create(addr, 16)` takes `backlog=16`: that is the **number of pending connection indications waiting to be accepted**, managed by the OS/network stack with implementation-dependent semantics. It does not limit:
- The number of currently running `HttpHandler.handle` invocations.
- The number of tasks waiting in `ThreadPoolExecutor`.
- The number of already-accepted keep-alive connections.
- The number of requests per second.
- The size of the request body or response body.

Example binding a server to port 0:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 16);
int allocatedPort = server.getAddress().getPort();
```

This is a code snippet. Port `0` lets the OS assign an ephemeral port, helping tests avoid port conflicts; when printing test stdout, print status/path rather than the port number that changes on every run.

## 10. Semaphore Limits Active Work

A `Semaphore` has a configured number of permits. With 1 permit, only one handler can simultaneously enter the `performWork` section:

```java
Semaphore permits = new Semaphore(1);

server.createContext("/work", exchange -> {
    try {
        if (!permits.tryAcquire()) {
            respond(exchange, 503, "busy");
            return;
        }
        try {
            performWork(exchange);
        } finally {
            permits.release();
        }
    } finally {
        exchange.close();
    }
});
```

This is a **code snippet**; `respond` and `performWork` are application-defined, handling checked exceptions per the API.

`tryAcquire()` **does not block** when no permit is available: the handler can return `503 Service Unavailable` quickly. Unlike `acquire()`, which can hold a handler thread indefinitely while waiting and starve the pool. `release()` must be placed in `finally` after a successful acquire, even if processing throws an exception.

**`Semaphore(1)` only limits the protected section.** If a handler reads a 5 GiB file before calling `tryAcquire`, memory/disk/network resources can still be consumed before admission. Place the control as early as appropriate for the type of resource being protected.

## 11. 503, 429, and 413 Express Different Limits

| HTTP status | Appropriate context |
| --- | --- |
| `503 Service Unavailable` | Server is overloaded, draining, or temporarily unable to process |
| `429 Too Many Requests` | Rate limit/quota per user, tenant, API key, or client |
| `413 Content Too Large` | Request content exceeds size limit |
| `408 Request Timeout` | Server timed out while waiting for a complete request per HTTP semantics |
| `504 Gateway Timeout` | Gateway did not receive a timely response from upstream; local demos may use 504 to mark a simulated timeout, but real services must match proper role and semantics |

`503` can include a `Retry-After` header such as `Retry-After: 1` to suggest how long to wait before retrying. This is a **hint**, not a guarantee that capacity will definitely be available exactly 1 second later. Clients should limit retries/backoff, especially for requests with side effects.

**Rate limiting differs from concurrency limiting:** a semaphore controls how many tasks run at the same time; a token bucket controls how many requests pass per time interval. An ultra-fast handler can process thousands of requests/s even with `Semaphore(1)`, because the permit is released continuously.

## 12. Runnable Java 17+ Program: Bounded Executor, 503, and stop(2)

Save with the exact filename **`BoundedHttpServerDemo.java`**. The program creates a local server:
- Executor with **2 worker threads**, queue of **4 tasks**, `CallerRunsPolicy`.
- `Semaphore(1)` protecting the work section.
- Request 1 holds the permit while waiting on `CountDownLatch`. Request 2 receives 503.
- `server.stop(2)` is called from a lifecycle thread; the first request is released and returns 200.
- After stop, the application **explicitly** shuts down the executor and awaits termination.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedHttpServerDemo {
    private static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        if (code == 503) {
            exchange.getResponseHeaders().set("Retry-After", "1");
        }
        exchange.sendResponseHeaders(code, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor workers = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.CallerRunsPolicy());
        Semaphore activeRequests = new Semaphore(1);
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 16);
        server.setExecutor(workers);
        server.createContext("/work", exchange -> {
            try {
                if (!"/work".equals(exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "not-found");
                    return;
                }
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set("Allow", "GET");
                    respond(exchange, 405, "method-not-allowed");
                    return;
                }
                if (!activeRequests.tryAcquire()) {
                    respond(exchange, 503, "busy");
                    return;
                }
                try {
                    entered.countDown();
                    if (!release.await(5, TimeUnit.SECONDS)) {
                        respond(exchange, 504, "timed-out");
                    } else {
                        respond(exchange, 200, "ok");
                    }
                } finally {
                    activeRequests.release();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            } finally {
                exchange.close();
            }
        });
        server.start();
        boolean lateExecutorRejected = false;
        try {
            server.setExecutor(Runnable::run);
        } catch (IllegalStateException expected) {
            lateExecutorRejected = true;
        }
        System.out.println("late-executor-rejected=" + lateExecutorRejected);

        Thread stopper = null;
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/work");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(6)).GET().build();
            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());
            if (!entered.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Request not entered");
            }
            System.out.println("first-in-flight=" + !first.isDone());
            HttpResponse<String> busy = client.send(req,
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("overload-status=" + busy.statusCode());
            System.out.println("overload-body=" + busy.body());

            stopper = new Thread(() -> server.stop(2), "server-stopper");
            stopper.start();
            release.countDown();
            HttpResponse<String> done = first.get(5, TimeUnit.SECONDS);
            System.out.println("first-status=" + done.statusCode());
            System.out.println("first-body=" + done.body());
            stopper.join(4000);
            System.out.println("server-stopped=" + !stopper.isAlive());
        } finally {
            release.countDown();
            server.stop(0);
            if (stopper != null) stopper.join(4000);
            workers.shutdown();
            if (!workers.awaitTermination(3, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            System.out.println("executor-shutdown=" + workers.isShutdown());
        }
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac BoundedHttpServerDemo.java
java BoundedHttpServerDemo
```

Verified stdout when run with `javac --release 17`:

```text
late-executor-rejected=true
first-in-flight=true
overload-status=503
overload-body=busy
first-status=200
first-body=ok
server-stopped=true
executor-shutdown=true
```

### Reading the Output

1. `late-executor-rejected=true`: `setExecutor` after start threw `IllegalStateException`.
2. `first-in-flight=true`: the server entered the handler for request 1 but has not released the latch yet; the future is still waiting for the response.
3. `overload-status=503` and `overload-body=busy`: request 2 was dispatched while `Semaphore(1)` had no available permits and was rejected by the handler.
4. `first-status=200`, `first-body=ok`: request 1 was released and completed its response.
5. `server-stopped=true`: the thread calling `server.stop(2)` finished.
6. `executor-shutdown=true`: the example called `workers.shutdown()` separately, then waited for `awaitTermination`.

### Why Use a Latch Instead of Sleep?

You cannot guarantee request 1 will always be slower than request 2 using only `Thread.sleep(20)`. `entered.await(...)` confirms request 1 **was received by the handler and holds the permit** before sending request 2. `release.countDown()` lets request 1 finish after HTTP 503 has been observed. This latch is a **deterministic test mechanism**, not a pattern for blocking production requests for long periods.

### Why Does stop Run on Another Thread?

`HttpServer.stop(delay)` can block while waiting for handlers; it should not be called synchronously inside a handler that the server itself is waiting on to finish. The `server-stopper` thread acts as a lifecycle coordinator. The demo releases the first request so it can finish within the grace period; this is not a guarantee that all slow work finishes within 2 seconds.

## 13. stop(int delay): Exact Semantics

The Java 17 documentation describes `HttpServer.stop(int delay)`:
1. **Closes the listening socket**, preventing new HTTP exchanges from being processed.
2. **Waits** until current handlers finish **or approximately `delay` seconds have elapsed**, whichever comes first.
3. Then **closes remaining open TCP connections**; the background thread created by `start()` terminates and `stop` returns.
4. Once stopped, **the same `HttpServer` instance cannot be reused**.

`delay` is a **non-negative integer number of seconds**, not milliseconds.

```java
server.stop(0);  // no meaningful graceful window
server.stop(2);  // gives current exchanges up to about 2 SECONDS
```

These two lines are **code snippets illustrating separate choices**, not a recommendation to call them back-to-back on the same server. `stop(-1)` throws `IllegalArgumentException`. `stop(30)` **does not have to wait a full 30 seconds**; if all handlers finish early, it can return early. `stop(0)` can cut off an in-flight exchange, causing the client to see a connection reset/truncated response.

After stopping, to serve further HTTP requests you must **create a new server** and configure it; do not call `start()` again on a stopped instance.

## 14. Distinguishing Server Stop from Executor Shutdown

`server.stop(5)` closes the listener and ends the exchange lifecycle per contract. It **must not be treated as** a command to shut down an application-created pool. For `ExecutorService`:

```java
server.stop(5);
workers.shutdown();
if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
    workers.shutdownNow();
}
```

This is a **code snippet**, requiring handling for `InterruptedException`, logging, and shared-executor scenarios.

Why does this order make sense?
- If you shut down the executor before the server stops submitting HTTP tasks, the server may still submit to an already-shut-down pool; tasks will be rejected/dropped depending on the policy.
- `shutdown()` only stops accepting new tasks; it **does not interrupt** already-running tasks.
- `awaitTermination` waits for already-accepted tasks to finish within its own timeout.
- `shutdownNow()` is only a best-effort interrupt; it cannot guarantee that any arbitrary blocking I/O/DB operation will stop immediately.
- If the pool is shared with another component, determine ownership before shutting it down.

In the main example, `server.stop(0)` in `finally` is defensive cleanup, while `stop(2)` demonstrates graceful logic. In a real application, build **one clear lifecycle coordinator**; do not call stop multiple times as a way to change the deadline.

## 15. Graceful Shutdown in the Application Lifecycle

A shutdown plan for a service behind a load balancer:

```text
Receive shutdown signal
      │
      ├─ readiness=false / announce draining
      ├─ LB/proxy reduces new requests to instance
      ├─ restrict new work per app policy (503 if needed)
      ├─ stop accepting new exchanges
      │     server.stop(graceSeconds)
      ├─ wait for current exchanges to finish within grace
      ├─ close remaining open TCP connections after grace or when done
      ├─ executor.shutdown()
      ├─ executor.awaitTermination(...)
      ├─ executor.shutdownNow() if needed, best effort
      └─ close DB/HTTP clients/background workers/temp files
```

A **drain phase before stop** can reduce new requests arriving right as the listener closes. However, there is no guarantee every request will be served: the grace period is finite, and weak-network clients or downstream I/O can exceed the deadline.

A handler might send `202 Accepted` and hand work off to a **background executor**. Its exchange has already ended, so `stop(delay)` **does not automatically wait for that background job**. You must have separate lifecycle management and data durability for the queue/job.

If a handler has already committed a DB transaction but the client loses the connection before receiving 200, the client may retry and cause duplicate side effects. Design idempotency keys/transaction IDs; graceful stop does not provide exactly-once semantics.

## 16. Timeouts and Interrupts Are Not Solved by stop Alone

A handler can block on:
- Reading a request body from a very slow client.
- Calling an upstream HTTP service or database.
- Writing a response to a client that reads data slowly.
- Waiting on a lock/queue/latch.
- Accessing the filesystem.

`stop(5)` closes TCP connections after the wait window, **it does not automatically cancel every business operation** blocked on a DB/file or another executor. Use request deadlines, upstream connect/read timeouts, DB statement timeouts, max-body limits, and a cancellation policy.

When a task is interrupted:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    exchange.close();
    return;
} finally {
    releasePermitIfOwned();
}
```

This is a **code snippet**; `blockingOperation` and `releasePermitIfOwned` are hypothetical application functions. Only release a permit **that was acquired**, do not over-release. Interrupts are usually **cooperative requests**, not commands that force every network/DB operation to stop. Do not report HTTP 200 if the task was cancelled before completing business logic.

## 17. Closing HttpExchange and Response Stream

In `HttpHandler`, clear resource ownership:

```java
server.createContext("/ping", exchange -> {
    try {
        byte[] bytes = "pong".getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    } finally {
        exchange.close();
    }
});
```

This is a **code snippet** requiring imports and a `server` variable. When an error occurs before sending headers, the handler can still choose an appropriate status. If `sendResponseHeaders(200,...)` has already been called and writing the body fails midway, **you cannot change the already-sent status to 500**.

`sendResponseHeaders(code, responseLength)` has the following semantics:
- `responseLength > 0`: the application must write **the exact number of bytes** declared.
- `responseLength == 0`: enables chunked response encoding; the body can be any length determined by the handler.
- `responseLength <= -1`: the response has no body.
- `HEAD`, `204`, `304` must follow HTTP semantics by not sending an inappropriate body.

Closing output with try-with-resources ensures the response stream finishes when done. `exchange.close()` ends the exchange; do not reuse the exchange object.

## 18. Request Body Limit Is a Different Layer from Semaphore

Even if the pool only has 2 workers, a request can send a body gigabytes long. You must cap **the actual number of bytes read**, not trust that the client's `Content-Length` is always accurate. With a max of 8 bytes, read **at most 9 bytes** and then decide:

```java
final int maxBytes = 8;
byte[] body;
try (InputStream input = exchange.getRequestBody()) {
    body = input.readNBytes(maxBytes + 1);
}
if (body.length > maxBytes) {
    reply(exchange, 413, "too-large");
    return;
}
process(body);
```

This is a **code snippet**; `reply`/`process` are application-defined. For large payloads, use a streaming loop, counted bytes, and disk quotas instead of allocating a large byte array. You must check for overflow if `maxBytes` is near `Integer.MAX_VALUE`.

Stopping early without reading the entire body and closing the request stream may prevent the HTTP connection from being reused; this is a trade-off that may be necessary when rejecting oversized uploads. A client currently sending a large body may not receive the complete 413 status if the connection is closed; test with real clients.

## 19. Runnable Java 17+ Program: Body Limit and Returning 413

Save file as **`BoundedRequestBodyDemo.java`**. The server reads at most 9 bytes; a 6-byte body receives `200`, a 12-byte body receives `413`. Both server and client run on loopback, requiring no Internet.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedRequestBodyDemo {
    private static void reply(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        final int maxBodyBytes = 8;
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.CallerRunsPolicy());
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 8);
        server.setExecutor(executor);
        server.createContext("/upload", exchange -> {
            try {
                if (!"POST".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().add("Allow", "POST");
                    reply(exchange, 405, "method-not-allowed");
                    return;
                }
                byte[] body;
                try (InputStream input = exchange.getRequestBody()) {
                    body = input.readNBytes(maxBodyBytes + 1);
                }
                if (body.length > maxBodyBytes) {
                    reply(exchange, 413, "too-large");
                } else {
                    reply(exchange, 200, "accepted=" + body.length);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/upload");
            HttpClient client = HttpClient.newHttpClient();
            for (String value : new String[]{"ABCDEF", "ABCDEFGHIJKL"}) {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(5))
                        .POST(HttpRequest.BodyPublishers.ofString(value))
                        .build();
                HttpResponse<String> response = client.send(request,
                        HttpResponse.BodyHandlers.ofString());
                System.out.println("bytes=" + value.length()
                        + " status=" + response.statusCode()
                        + " body=" + response.body());
            }
        } finally {
            server.stop(1);
            executor.shutdown();
            if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Commands:

```bash
javac BoundedRequestBodyDemo.java
java BoundedRequestBodyDemo
```

Verified stdout:

```text
bytes=6 status=200 body=accepted=6
bytes=12 status=413 body=too-large
```

The request strings in the demo contain only ASCII, so `String.length()` matches the number of UTF-8 bytes. For Vietnamese or emoji, **do not** use character count from String as the max request bytes; count the actual bytes read.

**Demo limitations:** there is no overall time budget for slow clients and no authentication support; production must add protection at ingress/TLS/rate limit and must not use plaintext HTTP for sensitive data.

## 20. Observing the Executor: Metrics Differ from Atomic Conditions

Useful measurements:
- `pool.getActiveCount()`: approximate number of workers actively executing tasks.
- `pool.getPoolSize()`: pool size at the time of measurement.
- `pool.getQueue().size()`: number of waiting tasks.
- `pool.getCompletedTaskCount()`: approximate number of completed tasks.
- `permits.availablePermits()`: remaining permits for the critical section.
- Status counts for `200`/`413`/`429`/`503`, request latency, downstream timeouts, response failures.
- Connection count, backlog pressure, CPU, heap, GC, file descriptors.
- Time-to-first-byte, total exchange duration, shutdown duration.

Metric example:

```java
System.out.printf(
        "pool=%d active=%d queued=%d permits=%d%n",
        workers.getPoolSize(),
        workers.getActiveCount(),
        workers.getQueue().size(),
        activeRequests.availablePermits());
```

This is a **code snippet**, assuming `workers` and `activeRequests` are available. The results are a **snapshot**, not an atomic admission decision. Do not check `getQueue().size() < 4` and assume the next task will be enqueued: another thread can fill the queue immediately after the check.

## 21. Thread Safety of HttpHandler

With a multi-threaded executor, the same handler can process multiple `HttpExchange` instances concurrently. Therefore:
- Per-request state should be stored in local variables or a dedicated request context.
- Do not write to shared mutable fields like `currentUser`/`currentBody` in a singleton handler.
- Use `AtomicLong`, `LongAdder`, or thread-safe data structures for shared counters.
- Permit acquire/release must have a `finally` block; avoid releasing more than acquired.
- Do not share `HttpExchange` across requests or write to an already-closed exchange.
- Call downstream services with explicit timeouts and a cancellation policy.
- Avoid long synchronized locks or blocking in regions affecting multiple handlers.

Counterexample:

```java
class BadHandler implements HttpHandler {
    private String currentUser;

    public void handle(HttpExchange exchange) throws IOException {
        currentUser = exchange.getRequestHeaders().getFirst("X-User");
        // Another request may overwrite currentUser while this handler is still running.
        exchange.close();
    }
}
```

This is a **counterexample code snippet**; it lacks response logic and must not treat a self-asserted user header as a trusted identity. For authentication, use auth middleware/tokens/certs and application authorization rules.

## 22. Testing Concurrency, Overload, and Shutdown

Test matrix:

| Test | Result to verify |
| --- | --- |
| Attach executor before start | Handler tasks are dispatched |
| Attach executor after start | Throws `IllegalStateException` |
| No executor attached | Server still works; do not assume a large pool by default |
| One permit is held | Second dispatched handler can return 503 |
| Pool and queue full | Rejection policy triggers, do not assume HTTP 503 |
| CallerRunsPolicy | Risk of handler running on the dispatcher |
| `stop(2)` + handler released | Handler has a chance to finish before stop completes |
| `stop(0)` + handler running | No guarantee of a successful response |
| `stop(-1)` | `IllegalArgumentException` |
| `start` after stop | Instance cannot be reused |
| Executor still active after server stop | Executor shutdown lifecycle must be managed separately |
| Request body 6 bytes, limit 8 | 200 if handler allows |
| Request body 12 bytes, limit 8 | 413 if client receives response |
| Slow upload/download | Deadlines/bounded connections take effect |
| Many requests/sec, very fast handler | Rate limit is separate from concurrency limit |
| Backend writes DB then connection drops | Idempotency/transaction state is handled |
| HTTP handler throws exception | Exchange/permit cleaned up in finally |

**Test with a latch instead of guessing timing:** `CountDownLatch` lets the server hold request 1 in the critical section; the main thread only sends request 2 after the latch signals request 1 has entered. `Thread.sleep(20)` does not guarantee request order on slow CI machines or during JVM pauses.

## 23. Common Mistakes

1. **Confusing backlog with concurrent request count.** Backlog only manages pending TCP connections.
2. **Calling `setExecutor` after `start()`.** The API throws `IllegalStateException`.
3. **Assuming the default executor has many workers.** Incorrect per Java 17 documentation.
4. **Using `newFixedThreadPool` and thinking the queue is bounded.** The queue can grow without bound.
5. **Using CallerRunsPolicy without measuring dispatcher latency.** The caller thread may run a blocking handler.
6. **Using AbortPolicy and expecting an automatic 503.** There is no guarantee.
7. **Using `Semaphore.acquire()` to wait long in a handler.** Can tie up workers and cause starvation.
8. **Acquiring a permit without releasing in finally.** Leaked permits cause permanent false overload.
9. **Placing the permit check after reading an unbounded body.** Filtered too late, can still OOM.
10. **Trusting Content-Length absolutely.** Must limit actual bytes read.
11. **Thinking stop(2) means 2 milliseconds.** Wrong, `delay` is in seconds.
12. **Thinking stop(5) always sleeps a full 5 seconds.** Wrong, it can return early if handlers finish.
13. **Calling stop(0) while hoping all requests finish.** There is no graceful window.
14. **Trying to restart an instance after stop.** Not supported.
15. **Forgetting to shut down the executor.** Worker threads/resources can keep the process alive.
16. **Shutting down the executor before stopping the listener.** Can reject new HTTP tasks.
17. **Believing shutdownNow always terminates a DB query immediately.** Interrupt is best effort.
18. **Calling stop from a handler that stop itself is waiting on.** Risks self-wait and unnecessary delay.
19. **Forgetting to close HttpExchange/OutputStream.** Resource leaks, incomplete responses.
20. **Sending 200 before checking the body.** Cannot change to 413 after response headers are committed.
21. **Confusing rate limit and concurrency limit.** Requests/s differs from active jobs.
22. **Treating HTTP completion as background task completion.** Jobs outside the handler have their own lifecycle.
23. **Judging readiness by a single activeCount metric.** Snapshot, not overall health.
24. **Retrying POST infinitely after connection reset.** Can cause duplicate business side effects.
25. **Using the plaintext HTTP demo as a public server.** Requires TLS, auth, gateway, and hardening.

## 24. Self-Check Questions

**Question 1.** When must `setExecutor` be called?  
**Answer:** Before `start()`; calling it after start throws `IllegalStateException`.

**Question 2.** Do backlog=16 and pool=2 mean 16 requests are processed simultaneously?  
**Answer:** No; backlog is for pending TCP connections, pool is for worker tasks.

**Question 3.** Does `CallerRunsPolicy` guarantee only 2 handlers run?  
**Answer:** No; a task can run on the thread calling `executor.execute`, such as the dispatcher.

**Question 4.** Why is a bounded queue not enough to guarantee clients receive 503?  
**Answer:** Queue rejection can happen before the handler runs; the rejection handler does not own `HttpExchange` and has no guarantee of sending 503.

**Question 5.** What happens when `Semaphore.tryAcquire()` has no permit?  
**Answer:** It returns false immediately, so the handler can send 503 without blocking to wait.

**Question 6.** What does `stop(5)` mean?  
**Answer:** Stop the listener, wait for current exchange handlers to finish for up to about 5 seconds, then close TCP connections.

**Question 7.** How does `stop(0)` differ from `stop(5)`?  
**Answer:** There is no graceful wait period; in-flight exchanges may be cut off.

**Question 8.** Can you call `start` again on the same instance after `stop`?  
**Answer:** No, you must create a new `HttpServer`.

**Question 9.** Why must the executor be shut down after `stop`?  
**Answer:** An application-created executor has its own lifecycle and is not assumed to shut down automatically with `HttpServer`.

**Question 10.** With a 12-byte body and an 8-byte limit, how does `readNBytes(9)` help?  
**Answer:** It reads at most 9 bytes to detect exceeding the limit without buffering an unbounded body into memory.

**Question 11.** Is a rate limit of 100 req/s the same as a semaphore with 100 permits?  
**Answer:** No, requests per second differs from concurrent operations.

**Question 12.** If a handler returns 202 and pushes a background job, does `stop(5)` wait for the job to finish?  
**Answer:** Not automatically; the exchange has ended, and the job needs its own lifecycle.

**Question 13.** Does a client receiving a reset after sending POST prove the server did not write to the DB?  
**Answer:** No; the side effect may have already occurred before the response was cut off.

**Question 14.** Why must request/response streams be read/closed explicitly?  
**Answer:** To release resources, avoid holding connections/handlers indefinitely, and complete HTTP framing properly.

**Question 15.** Is the `workers.getActiveCount()` metric suitable as an atomic condition for accepting new requests?  
**Answer:** No. It is an approximate snapshot; use an admission primitive like a semaphore or ingress policy.

## 25. Application Checklist

**Initialization:** Bind the right interface, choose a justified backlog, create contexts, build a bounded executor and analyzed rejection policy, call `setExecutor` **before `start`**, and prepare TLS/auth/timeouts/metrics when serving beyond loopback.

**Running:** Bound request rate/active work/queue/body bytes, return 503 or 429 or 413 according to cause, do not block workers indefinitely, close `HttpExchange`, set downstream deadlines, log status/latency/queue depth, and protect sensitive data.

**Stopping:** Announce draining/readiness false when behind an LB, stop the server with `delay` in **seconds** from a lifecycle thread, understand requests may be cut off if past the deadline, shut down application-owned executors, await termination then best-effort interrupt, stop background jobs, and close separate dependencies. To run again, create a new `HttpServer`.

**Summary:** `setExecutor` decides **where handlers execute**; queue/backlog/permits decide **which layer holds or rejects work**; `stop(delay)` gives a **window to finish HTTP exchanges** then closes the listener/connections, without replacing executor shutdown or handling business side effects.

## 26. Official Documentation and References

- Oracle Java SE 17 `HttpServer` — `create`, `setExecutor`, `start`, `stop(int delay)`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 `HttpExchange` — request/response streams, `sendResponseHeaders`, `close`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- Oracle Java SE 17 `HttpHandler` — `handle(HttpExchange)`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- Oracle Java SE 17 `ThreadPoolExecutor` — sizing, queues, rejection policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 `CallerRunsPolicy` — runs task on caller thread, discards if shut down: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html
- Oracle Java SE 17 `ArrayBlockingQueue` — bounded queue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Oracle Java SE 17 `Semaphore` — `tryAcquire` and `release`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html
- Oracle Java SE 17 `ExecutorService` — `shutdown`, `awaitTermination`, `shutdownNow`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 17 `CountDownLatch` — conditional concurrency testing: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 17 `ServerSocket` — backlog semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- RFC 9110 — HTTP Semantics, 413/429/503/Retry-After: https://www.rfc-editor.org/rfc/rfc9110
