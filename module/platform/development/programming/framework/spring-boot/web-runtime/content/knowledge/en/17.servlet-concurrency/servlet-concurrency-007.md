# Async Timeouts, Task Cancellation, and Handling Client Disconnects in Servlet/Spring MVC

In the **Servlet stack**, an HTTP request can start long-running work and return its result asynchronously. When doing so, the request-receiving thread can return to the Servlet container while the response remains open. However, **request timeout**, **background task cancellation**, and **client connection close** are three distinct events. Conflating them leads to leaked tasks, resources held too long, writes after the response has completed, or inaccurate HTTP status codes.

This article explains the Servlet async lifecycle, how to configure timeouts and cleanup in Spring MVC, the limits of cancellation via `Future.cancel(true)`, and strategies for handling client disconnects. The examples target **Java 17+**, **Spring Boot 3.x**, and **Spring MVC on a Servlet container**; do not assume Spring MVC has automatic cancellation like a reactive stream.

## 1. How does async work in Servlet?

### 1.1. Synchronous vs. asynchronous requests

**Synchronous:** the Servlet thread receives the request → invokes processing (which may block on I/O or sleep) → writes the response → finishes; that thread is occupied for the entire processing duration.

**Servlet async:** the Servlet thread receives the request → enables async and exits the filter/servlet chain → the container keeps the request/response in async state while returning the receiving thread to the pool → work runs on an executor or the result arrives from another system → the Servlet container performs an **ASYNC dispatch** so Spring MVC finalizes the response.

At the lower-level Servlet API, `request.startAsync()` returns an `AsyncContext`, after which you can call `dispatch()` or `complete()`. Servlets/filters must support async (`asyncSupported` and appropriate dispatcher types). Spring MVC normally manages this mechanism for you when a controller returns:

- `Callable<T>`: Spring MVC submits the work to an `AsyncTaskExecutor`. You can use `WebAsyncTask<T>` to select timeout/executor and register callbacks.
- `DeferredResult<T>`: the controller returns a “result holder”; an external actor calls `setResult` or `setErrorResult` later.
- `ResponseBodyEmitter`, `SseEmitter`, `StreamingResponseBody`: used for streams and multi-push data; network writes follow different rules from a single value.

**Async does not mean non-blocking on every thread.** If code inside a `Callable`/worker still calls JDBC or `Thread.sleep`, the worker thread still blocks. The immediate benefit is releasing the request-receiving thread back to the container early, not gaining unlimited resources.

### 1.2. States to distinguish

```text
HTTP request arrives
      |
      v
Controller returns DeferredResult / Callable
      |
      v
Servlet async starts; initial request thread is released
      |
      +---- worker completes ------> setResult / setErrorResult
      |                                    |
      |                                    v
      |                               ASYNC dispatch -> response -> complete
      |
      +---- async timeout ----------> onTimeout -> try setting error response
      |                                    |
      |                                    +-> request stopping worker -> complete
      |
      +---- container sees error ----> onError / error handling -> complete
      |
      +---- client closes socket ----> may NOT be detected immediately
                                           |
                                  fails on later write/flush or timeout
```

Once the container completes the async request, there is no longer a valid response for the application to “write more to.” A task still running afterward may finish internal work, yet you cannot assume its late result can still be sent to the client.

## 2. Timeouts: there are multiple clocks, not just one

| Timeout type | Who controls it | Key consequence |
| --- | --- | --- |
| **Client timeout** | Browser, `curl`, SDK, mobile app | The client may stop waiting and close the connection; the server may still be running. |
| **Gateway/proxy/load balancer timeout** | Reverse proxy/API gateway | The proxy may close the connection or return `504 Gateway Timeout` when waiting on upstream too long; the backend app may not know immediately. |
| **Servlet async timeout** | Servlet container/Spring MVC | The request in async mode times out; callbacks/interceptors fire. Does not automatically guarantee the worker stops. |
| **Task/dependency deadline** | Application code, outbound HTTP client, JDBC driver, queue client | Bounds how long the actual work is permitted to run; must be configured separately from HTTP response timeouts. |

Example: the client waits only **2 seconds**, the gateway waits **4 seconds**, Spring MVC async timeout is **5 seconds**, and the database query timeout is **30 seconds**. The client may have given up at second 2 while the backend continues holding a worker and a database connection. Therefore you must **design end-to-end deadlines**, with bounds on dependencies and proper execution cancellation.

### 2.1. Configuring timeouts in Spring Boot/MVC

In `application.yml`:

```yaml
spring:
  mvc:
    async:
      request-timeout: 5s
```

`spring.mvc.async.request-timeout` is the default wait time for **Spring MVC async requests**. If unconfigured, the actual default depends on the Servlet container. `5s` uses Spring Boot's `Duration` syntax; other supported duration units work too. Do not treat this setting as a timeout for synchronous requests, JDBC queries, outbound HTTP calls, or queued tasks.

You can override per request:

```java
// Illustrative snippet inside a Spring MVC controller.
DeferredResult<String> deferred = new DeferredResult<>(2_000L); // 2 seconds
// ... return deferred and set the result from another component
```

With `Callable<T>`, use `WebAsyncTask<T>` to specify timeout and callbacks:

```java
// Illustrative snippet; "service" is an application-provided service.
WebAsyncTask<String> response = new WebAsyncTask<>(2_000L, () -> service.load());
response.onTimeout(() -> "fallback on timeout");
response.onCompletion(() -> service.cleanup());
return response;
```

The `WebAsyncTask` snippet demonstrates the API rather than a standalone class; it requires a controller, a matching return type, and a real service. In production, **do not** return a success-looking fallback string when timing out should report failure: use `ResponseEntity` or exception handling to reflect failure.

If managing Servlet async manually via `AsyncContext`, you have `setTimeout(long milliseconds)` and `AsyncListener.onTimeout(...)`; calling `dispatch()`/`complete()`, handling errors, and managing response writes belong to your code. When already using Spring MVC `DeferredResult`, avoid mixing in low-level lifecycle calls that cause double completion.

### 2.2. HTTP status on timeout

- Spring MVC handles default timeouts via `AsyncRequestTimeoutException` and returns a server error (typically `503 Service Unavailable` depending on configuration/handlers). You can explicitly return a clear status and body via `onTimeout`.
- `503` makes sense when the server temporarily cannot complete the request. `504 Gateway Timeout` is typically emitted by a **gateway/proxy** when upstream is slow; do not use `504` for every internal task timeout merely because its name includes “timeout.”
- `408 Request Timeout` pertains to the server not receiving the full request from the client within the wait window, which is **different** from the server taking too long to process an async request.
- If the client has closed the connection, the server may be **unable to send any status at all**. Do not assume an error JSON response will always be delivered when a timeout occurs.

## 3. Task cancellation: timeout is not a “kill” button

An expired request does **not** mean the task stopped. There are three distinct state layers:

1. **Response/request lifecycle:** can an HTTP result still be returned, or has it timed out/completed?
2. **Work on the executor:** is it still running, finished, signaled to cancel, or stuck in non-interruptible work?
3. **External side effects:** has it sent an email, written to the database, published a message, called a third-party system, or committed a transaction?

For example, when a search request times out, you may want to cancel the query; however, if it was a **committed order-creation** request, cancelling the thread does not roll back a completed transaction. Never infer “client disconnected → business work definitely didn't happen.”

### 3.1. What does `Future.cancel(true)` actually do?

For tasks submitted via `ExecutorService.submit(...)`, `Future.cancel(true)` marks a cancellation attempt and may **interrupt** the running thread. Java has no safe mechanism to forcibly terminate arbitrary running code:

- `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await`, and many blocking APIs throw `InterruptedException`. The task should exit cleanly and restore the interrupt flag via `Thread.currentThread().interrupt()` when catching the exception.
- CPU loops should poll `Thread.currentThread().isInterrupted()` and exit when requested.
- I/O, JDBC, native calls, RPCs, and external SDKs may ignore or delay interrupts. You need separate library/dependency-level timeouts and sometimes dedicated cancel APIs.
- Returning `true` from `cancel(true)` or `isCancelled()` **does not prove** all side effects stopped. It reflects the `Future`'s state.
- `CompletableFuture.cancel(true)` also **does not** guarantee interrupting a running thread the way `ExecutorService`'s `FutureTask` can. Do not switch code from `Future` to `CompletableFuture` and assume workers get interrupted.

The following standalone Java 17 program demonstrates requesting cancellation of a waiting task:

File `CancellationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<?> job = executor.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            System.out.println("cancel requested = " + job.cancel(true));
            System.out.println("future cancelled = " + job.isCancelled());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Run:

```bash
javac CancellationDemo.java
java CancellationDemo
```

Stdout (since `neverReleased` is never released and `started.await()` guarantees the task has started):

```text
cancel requested = true
future cancelled = true
```

The example shows the cancel signal was accepted; in real tasks you must still verify that handler code exits promptly on interrupt and releases resources cleanly.

### 3.2. Designing idempotent cleanup

A request can receive a **result**, a **timeout**, and a **network error** almost simultaneously. Therefore:

- Use a single decision point for the response result (`DeferredResult.setResult`/`setErrorResult` returns a boolean telling whether the result was accepted). Never write the HTTP response twice.
- Use `onCompletion` for final idempotent cleanup—such as canceling an unfinished task, closing subscriptions, and removing map entries. This callback fires on success, timeout, or error; by itself it **does not prove** the client disconnected.
- Use `onTimeout` to pick a fallback/status and request canceling unneeded work.
- Use `onError` to record observed errors and request cancellation; an async error can have many causes, so never automatically label it “client went away.”
- Do not swallow `InterruptedException` and carry on as if nothing happened. Never hold a reference to `HttpServletResponse` so a worker tries writing a body after async completion.

## 4. Spring Boot 3.x example: timeout, Future cancellation, and cleanup

The example comprises **two complete Java files** in a Java 17 Spring Boot project with `spring-boot-starter-web`. A dedicated pool illustrates workers; cancellation here is best-effort. In production, configure a **bounded pool + queue executor with rejection policies and load observability** instead of `Executors.newFixedThreadPool` (which uses an unbounded queue).

File `src/main/java/demo/async/AsyncDemoApplication.java`:

```java
package demo.async;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

File `src/main/java/demo/async/AsyncWorkController.java`:

```java
package demo.async;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import jakarta.annotation.PreDestroy;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class AsyncWorkController {
    private final ExecutorService workers = Executors.newFixedThreadPool(4);

    public record Payload(String state, String detail) {}

    @GetMapping("/job")
    public DeferredResult<ResponseEntity<Payload>> job(
            @RequestParam(defaultValue = "30") int units) {

        if (units < 0 || units > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "units must be between 0 and 100");
        }

        // Limit this endpoint's HTTP async lifecycle to 1.5 seconds.
        DeferredResult<ResponseEntity<Payload>> deferred =
                new DeferredResult<>(1_500L);

        Future<?> running = workers.submit(() -> {
            try {
                // Simulate 100 ms/step; InterruptedException lets it exit.
                for (int i = 0; i < units; i++) {
                    Thread.sleep(100L);
                }
                deferred.setResult(ResponseEntity.ok(
                        new Payload("completed", "units=" + units)));
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } catch (RuntimeException failure) {
                deferred.setErrorResult(failure);
            }
        });

        deferred.onTimeout(() -> {
            // If the result has not been decided yet, return a timeout response.
            deferred.setErrorResult(
                    ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                            .body(new Payload(
                                    "timed_out", "async request exceeded 1500 ms")));
            // Request task cancellation; worker code must cooperate with interrupts.
            running.cancel(true);
        });

        // Container observed an async error: request stopping work.
        deferred.onError(error -> running.cancel(true));

        // End-of-request cleanup: safe even if the task already finished.
        deferred.onCompletion(() -> running.cancel(true));

        return deferred;
    }

    @PreDestroy
    public void shutdownWorkerPool() {
        workers.shutdownNow();
    }
}
```

**Why does this example work well?**

1. The controller returns `DeferredResult` promptly, letting the Servlet container keep the response open in async mode. `workers.submit` runs the simulated work on a separate pool.
2. With `units=2`, the worker normally finishes in about 200 ms, calls `setResult`, and the client receives `200 OK` with JSON `{"state":"completed","detail":"units=2"}`.
3. With `units=30`, the worker would take roughly 3 seconds, exceeding the 1.5-second async timeout. The `onTimeout` callback tries setting `503 Service Unavailable` with JSON `{"state":"timed_out","detail":"async request exceeded 1500 ms"}` and calls `running.cancel(true)`. The task in `Thread.sleep` receives the interrupt and exits.
4. When the request finishes, `onCompletion` also runs, and calling cancel repeatedly on a finished `Future` is harmless; do not treat this callback as a client-disconnect notification.
5. If the result wins the race against the timeout, a late `setErrorResult` call will not be accepted and will not alter the decided response. In production, check the boolean returned by `setResult`/`setErrorResult` when tracking “late result” metrics and unifying cleanup.

**Limitations of the example:** Because `Thread.sleep` responds promptly to interrupts, the task stops quickly. A JDBC or REST call to an external system might not react similarly; configure dependency-specific timeouts and cancellation. The example omits authentication, tracing, queue bounds, rate limiting, and durable storage.

Add the dependency to an existing Boot Gradle project if not already present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Run the project with its wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Once started, run these commands (Bash syntax):

```bash
# Completes fast, expect HTTP 200 and state=completed
curl -i 'http://localhost:8080/demo/job?units=2'

# Exceeds Spring MVC timeout, expect HTTP 503 and state=timed_out
curl -i 'http://localhost:8080/demo/job?units=30'

# Invalid input, expect HTTP 400
curl -i 'http://localhost:8080/demo/job?units=-1'

# Client waits at most 0.2 seconds then aborts
curl --max-time 0.2 -i 'http://localhost:8080/demo/job?units=30'
```

These statuses are **expected results under normal test conditions**, not exact guarantees on callback timing given scheduling and machine load. The final command may report `curl: (28) Operation timed out` on the **client**, which does not prove the Servlet immediately received a disconnect notice or that the worker stopped instantaneously. Measure those two events separately.

### 4.1. How do Callable, WebAsyncTask, and DeferredResult differ here?

- `Callable`: fits when computing the result runs on MVC's executor; easy to use, though policy-driven cancellation requires careful management of executors/tasks/lifecycles.
- `WebAsyncTask`: wraps `Callable` with timeout, executor, and callbacks; callbacks supply a fallback/response value, yet **do not automatically guarantee canceling running work**.
- `DeferredResult`: fits when results are pushed from an external task, listener, message broker, or callback. The application can retain the `Future` or cancellation token and tie the HTTP request lifecycle to the task.
- `SseEmitter`/streaming: produces multiple writes; if the client vanishes, write failures or heartbeats help detect it, though not necessarily instantaneously.

If choosing `Callable` or streaming in production, review `WebMvcConfigurer.configureAsyncSupport` to supply an appropriate `AsyncTaskExecutor`. MVC's default executor should not be assumed suitable for sustained load; bound and monitor resources.

## 5. Client disconnects: a major limitation of Servlet

**The Servlet API provides no standard event guaranteed to notify immediately when a client closes its socket.** While the backend is processing without writing anything yet, a caller closing a browser tab or aborting `curl` does not necessarily notify the server right away. You cannot register a callback and expect detection within a few milliseconds.

What happens in practice:

- Client closes connection **before any response data**: the server keeps computing and only discovers the error later during write/flush or via timeout.
- Client closes connection **during streaming**: the next write may throw an `IOException` such as broken pipe or connection reset by peer; the exact message depends on container/OS/proxy.
- Client closes connection **after the server committed side effects**: nobody is waiting for the response, yet the transaction may already have succeeded; there is no automatic “rollback on HTTP disconnect.”
- Proxy buffering or half-open connections: the application may observe the disconnect late, and the absence of an error must never be treated as proof the client is still present.

### 5.1. What do `onError` and `onCompletion` tell you?

- `DeferredResult.onError(Consumer<Throwable>)` runs when the async request encounters a container-recognized error. You can clean up or set an error result **if the response is still available**; it is not an isolated disconnect callback or a guarantee when the socket closes.
- `DeferredResult.onCompletion(Runnable)` runs when the async lifecycle ends for **any reason**, including success, timeout, or network error. Use it for cleanup; **never log every invocation as “client aborted.”**
- `onTimeout` runs when the container actually handles an async timeout. Do not treat it as proof that the client went away.
- For streaming, if `ResponseBodyEmitter.send(...)` throws `IOException` due to remote disconnect, **let the Servlet container/Spring MVC handle the error notification**; per Spring MVC docs, the application should not additionally call `emitter.complete()` or `emitter.completeWithError()` inside that `IOException` branch because the container fires the error notification and Spring handles the final dispatch.

There is no standard HTTP status **499** defined by RFCs for this case; `499 Client Closed Request` appears in logs of proxies like Nginx to indicate the client closed the connection. Never configure `499` as a standard response expecting to send it to an already-gone client.

### 5.2. Heartbeats for SSE/long-lived streaming

For `text/event-stream` connections, the server can periodically send an SSE **comment heartbeat** (for example a line starting with `:`) to probe writes and detect dead connections sooner. When a write fails, clean up the associated task/subscription; when `SseEmitter.send` throws `IOException`, let Spring/container handle the async error as described above.

Heartbeats do not guarantee instant detection: proxies can buffer, networks can stall, and not every write fails immediately on a dead socket. Choose an interval matching proxy idle timeouts, network load, and product goals. For protocols needing bidirectional liveness signals, WebSocket ping/pong or dedicated messaging may fit better.

## 6. Deciding whether to cancel business work when an HTTP request ends

**Case A — read/compute request serving only the waiting caller:** e.g. CPU-heavy search or temporary rendering. On timeout or detected disconnect, signal cancellation, stop downstream fetches when possible, release resources, and prevent sending late results.

**Case B — request creating durable work:** e.g. creating an invoice, queuing an email, or a user-triggered report export. Once `202 Accepted` and a job ID are returned, closing a browser tab **should not automatically cancel the job** unless explicitly defined by the API. Provide dedicated authenticated status/cancel endpoints, persist job state, and handle cancellation idempotently.

**Case C — irreversible side effects:** canceling a future after database commit or after a third-party system accepted a command does not undo it. Use business state machines, idempotency keys, transactions/compensation where needed, and result lookup if the client retries.

| Situation | Response if still sendable | Backend action |
| --- | --- | --- |
| Work finishes before deadline | `200`/`201` per business rules | Send result, clean up handles. |
| Async request times out; work only serves this response | `503`/API-contract error | `onTimeout` requests task cancellation, enforce downstream timeouts, clean up. |
| Worker fails unexpectedly | Appropriate `5xx` if response uncommitted | Log root cause, avoid leaking details, clean up. |
| Client closed the connection | May be **unable to return a status** | Best-effort detection, stop unnecessary work, do not write late body. |
| Durable job accepted | `202` at acceptance time | Continue processing independently; provide status/cancel endpoints if needed. |

## 7. Testing and observing tricky scenarios

Do not test only the happy path. At minimum test:

1. **Fast completion:** task ends before timeout; body/status are right; `onCompletion` runs; the future no longer occupies a worker.
2. **Async timeout:** task runs long; error status/body are consistent; cancel callback fires; active task count drops when the task supports interrupts.
3. **Completion vs. timeout race:** run repeatedly near the deadline boundary; **only one** result is accepted, no double response write, no leaked tasks.
4. **Non-interruptible dependency:** simulate a blocking library; prove request timeout **does not** automatically reclaim resources; verify dependency-level timeout and cancellation.
5. **Client abort:** use `curl --max-time` or actively close TCP; observe real errors/cleanup with a production-like Servlet container and proxy. **Do not assert that a disconnect callback fires immediately**, as the API makes no such guarantee.
6. **Streaming disconnect:** send heartbeats, disconnect the client, and verify the stream-producing task stops once the failure is detected; do not invoke `completeWithError` again after `IOException` from `send`.
7. **Business side effects:** verify a canceled request does not cause retries to duplicate orders or emails.

With Spring MVC `MockMvc`, testing async results generally follows `request().asyncStarted()` then `asyncDispatch(mvcResult)` to verify the response. However, **`MockMvc` is no substitute** for timeout/network-disconnect tests on a real Servlet container, because sockets, container timers, and proxies are not fully modeled.

Useful metrics/logs: HTTP duration, open async request count, timeout count, executor `active/queue/rejected`, cancel request count, tasks actually stopping after cancel, stream write errors, dependency latency, and tasks still running after response completion. Carry request/correlation IDs into worker threads when needed, but never put full URLs, arbitrary client IDs, or exception text into metric labels causing cardinality explosion.

## 8. Common mistakes and checklist

**Mistakes:**
- Configuring only `spring.mvc.async.request-timeout` and believing JDBC/HTTP clients/workers will automatically expire: **wrong**, layer timeouts are independent.
- Treating `Future.cancel(true)` like `kill -9`: it is only a best-effort cancellation signal and cannot undo committed side effects.
- Always marking `onCompletion` as “client disconnected”: this callback also runs on normal completion.
- Returning `200` after an async timeout or using `504` for every slow local computation: status codes should reflect the responsible layer and cause.
- Writing directly to `HttpServletResponse` after `DeferredResult` has completed: can corrupt responses or fail writes.
- Calling `completeWithError` after `SseEmitter.send` throws `IOException`: duplicates error handling already managed by Spring/container.
- Using unbounded pools/queues for all async requests: the receiving thread returns, yet workers and memory can still exhaust.
- Treating a user leaving a page as a request to cancel a durable job: can drop critical work.

**Design checklist:**

- [ ] Distinguished client, proxy, Servlet async, and dependency timeouts; chose intentional deadlines.
- [ ] Decided whether business work may be canceled or must complete even if the connection closes.
- [ ] Used `onTimeout`, `onError`, and `onCompletion` for their proper purposes, handling races idempotently.
- [ ] Tasks support interrupts/cancellation tokens; dependencies have dedicated timeouts and cleanup.
- [ ] Never write responses after completion or connection failure; return consistent HTTP status/body when possible.
- [ ] Bounded executor pools/queues; added metrics for pending, rejected, or post-timeout tasks.
- [ ] Added real-server integration tests for client aborts, proxy timeouts, and stream heartbeats.

**Conclusion:** Servlet async returns HTTP request-handling threads to the container, but it does not make background work vanish. **Timeouts end the request's wait window; cancellation requests stopping the work; disconnects are network states that may be detected late.** Sound design coordinates these three lifecycles with downstream timeouts, idempotent cleanup, and clear business contracts.

### References

- Spring Framework — [Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `DeferredResult`, `Callable`, `WebAsyncTask`, error handling, disconnects, and configuration.
- Spring Framework — [DeferredResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html): contract for `onTimeout`, `onError`, `onCompletion`, and `setResult`.
- Spring Boot — [Common Application Properties](https://docs.spring.io/spring-boot/reference/appendix/application-properties/index.html): `spring.mvc.async.request-timeout`.
- Spring Framework — [MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): testing `asyncStarted`/`asyncDispatch`.
