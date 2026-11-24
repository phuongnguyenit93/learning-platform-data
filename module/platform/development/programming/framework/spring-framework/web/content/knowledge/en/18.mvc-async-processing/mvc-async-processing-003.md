# Configuring TaskExecutor, Timeouts, and Resource Limits in Asynchronous Spring MVC

## 1. Lesson goals

Spring MVC on the Servlet stack can handle HTTP asynchronously: controllers return `Callable<T>`, `WebAsyncTask<T>`, or `DeferredResult<T>`; the initial Servlet request thread leaves while the result is produced later. This avoids holding a Servlet thread just to wait on a task, yet it does not make CPU, worker threads, connections, memory, queues, or downstream systems infinite.

After this lesson, you will:

- Understand the Servlet lifecycle `REQUEST → startAsync → worker/callback → ASYNC dispatch → response`.
- Distinguish `Callable`, `WebAsyncTask`, `DeferredResult`, `@Async`, and `CompletableFuture`.
- Configure `WebMvcConfigurer.configureAsyncSupport` and `AsyncSupportConfigurer`.
- Size a `ThreadPoolTaskExecutor` with `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy, and shutdown settings.
- Distinguish Servlet async timeout, per-request timeout, client/gateway timeout, and downstream HTTP/DB timeout.
- Know that a timeout **does not automatically cancel** background tasks or roll back side effects.
- Design resource limits: queues, admission control, connection pools, pending DeferredResult, SSE, backpressure, and quotas.
- Verify the final MVC async response with `MockMvc.asyncDispatch` and test real HTTP with `curl`.
- Identify overload, timeouts, disconnects, context propagation, and measure queue wait/throughput/latency.

Examples use **Java 17+, Spring Boot 3.x, Spring Framework 6.x, Jakarta Servlet**. This is the Spring MVC Servlet stack, not WebFlux. `Thread.sleep` in the demo only simulates I/O; production requires timeouts/cancellation on actual downstreams.

## 2. How does Servlet async work?

Typical flow when a controller returns `Callable`:

```text
Client
  |
  | GET /async/callable
  v
Servlet container -------------- DispatcherServlet
  |                                  |
  |  REQUEST thread                   | controller returns Callable
  |                                  | request.startAsync()
  |                                  | submits Callable -> AsyncTaskExecutor
  |  REQUEST thread returns to pool  |
  |                                  |
  |                              Worker thread
  |                                  | runs Callable, I/O/CPU
  |                                  | returns value/throws error
  |                                  v
  |                     Servlet ASYNC dispatch
  |                                  |
  |                     DispatcherServlet processes result
  |                     HttpMessageConverter writes JSON
  v
Client receives response
```

Common points of confusion:

1. **Only the initial Servlet thread returns early.** If `Callable` invokes synchronous JDBC, sleeps, waits on outbound HTTP, or reads a file, **the worker is still blocked**.
2. **The HTTP response stays open** while waiting; the corresponding TCP connection, request attributes, and buffers have a cost.
3. **The Callable result needs an async dispatch** back to the Servlet container so Spring MVC can finish processing the response.
4. Filters and interceptors have a different lifecycle after async starts; logging/cleanup must account for both REQUEST and ASYNC dispatches.
5. If the worker does not produce a result in time, the Servlet async timeout may fire; you cannot assume the Java task is cancelled at that exact moment.
6. Async does not automatically increase database or outbound HTTP connection pool capacity; adding workers may simply cause more requests to wait at a lower layer.

Spring Framework clearly describes this process in its official asynchronous requests documentation.

## 3. Spring MVC async processing models

| Return type | Where the result is produced | Suitable scenario |
| --- | --- | --- |
| Synchronous `ResponseEntity<T>` | Servlet request thread | Short, simple processing |
| `Callable<T>` | MVC `AsyncTaskExecutor` | Releasing the request thread while a callable runs other work |
| `WebAsyncTask<T>` | MVC executor or custom executor | Callable needing per-request timeout and callbacks |
| `DeferredResult<T>` | Application producer/event listener | Result arrives from an external callback/message/job |
| `CompletableFuture<T>` | Executor creating the future chosen by the app | Async pipeline with its own timeout/cancellation |
| `@Async` on a bean method | Spring async infrastructure/dedicated executor | Asynchronous work at the service layer |
| `SseEmitter`, `ResponseBodyEmitter` | MVC streaming mechanism | Sending multiple events/chunks, needs connection budgeting |

**`DeferredResult` does not automatically submit business logic to the MVC executor.** The controller registers a placeholder; an application thread/event source must call `setResult` or `setErrorResult` when the result is ready.

**`@Async` does not mean MVC async.** `@EnableAsync` and `@Async` executors have a separate configuration mechanism; `configureAsyncSupport` is the primary point to specify the executor for MVC `Callable`. Do not enable `@EnableAsync` just so controllers can return `Callable`.

If a task is already very fast, the synchronous model may be more optimal. Do not add async out of habit without measuring thread usage, I/O wait, p95/p99, and the need to keep connections open long-term.

## 4. configureAsyncSupport is the MVC configuration point

Spring MVC lets you override a `WebMvcConfigurer` callback:

```java
@Override
public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
    configurer.setTaskExecutor(mvcExecutor());
    configurer.setDefaultTimeout(2500L);
}
```

This is an **illustrative method snippet** inside a configuration class that already has `mvcExecutor()`. Complete runnable code appears later.

- `setTaskExecutor(AsyncTaskExecutor)` specifies the MVC executor for `Callable` and certain cases of blocking writes when MVC adapts streaming/reactive return types.
- `setDefaultTimeout(long)` specifies **milliseconds** as the default timeout for async requests when not overridden per return type.
- When no default timeout is set, the value depends on Servlet container/framework configuration; do not hardcode a number remembered from another version.
- With `WebAsyncTask`, you can specify a per-request timeout and executor.
- With `DeferredResult`, `ResponseBodyEmitter`, and `SseEmitter`, you can configure timeouts per object.
- `registerCallableInterceptors(...)` and `registerDeferredResultInterceptors(...)` support advanced timeout/error/completion handling.

**Scope:** Async timeout is not a full HTTP deadline: TCP connect, proxies, servlet filters, argument binding, and downstreams each have their own lifecycles. Servlet async timeout typically starts after the initial request thread finishes handling the dispatch and ends when the request is redispatched.

## 5. Choosing ThreadPoolTaskExecutor instead of an unbounded executor

`ThreadPoolTaskExecutor` is a Spring-managed wrapper around Java `ThreadPoolExecutor`, providing core/max pool sizing, queues, thread prefixes, shutdown handling, and metrics.

Initial learning example:

```text
corePoolSize = 2
maxPoolSize = 4
queueCapacity = 8
keepAliveSeconds = 30
rejection = AbortPolicy
```

Important behavior of a positive queue capacity:

1. When worker count is below core, the executor creates core workers.
2. When core workers are busy, new tasks normally **enter the queue first**.
3. Only when the queue is full does the executor expand from core to max.
4. When the pool reaches max **and** the queue is full, new tasks are rejected.

With core=2, max=4, queue=8, the theoretical capacity at saturation is **4 running tasks + 8 queued tasks**. This number is not a 12-HTTP-connection limit because each async request has already been accepted, and pending DeferredResults or other async sources do not sit in the MVC callable queue.

**Common trap:** setting max=100 with an unbounded queueCapacity causes the pool to rarely grow above core because the queue never fills. Long queues inflate tail latency, causing cascading timeouts even while CPU is idle or downstream is already saturated.

`setQueueCapacity(0)` typically creates a `SynchronousQueue` (direct handoff), allowing threads to scale up faster, though if max is insufficient it rejects quickly; benchmark instead of assuming queue=0 is always better.

## 6. Rejection policies and backpressure

Strategies from Java `ThreadPoolExecutor`:

| Policy | Behavior | Consequence for async HTTP |
| --- | --- | --- |
| `AbortPolicy` | Throws an exception when overloaded | Observable, can be mapped to 503 when appropriate |
| `CallerRunsPolicy` | Submitting thread runs the task itself | Can block the Servlet request thread, defeating the release goal |
| `DiscardPolicy` | Drops the task | Requests may hang until timeout with nobody producing a result |
| `DiscardOldestPolicy` | Drops the oldest queued task | Earlier requests lose work in ways hard to diagnose |
| Custom rejection | Rejects by quota/bulkhead | Must cover all races and error paths |

For HTTP request-response, avoid silently discarding work. `AbortPolicy` generally makes overload clearly observable, though do not assume every `TaskRejectedException` automatically turns into a clean HTTP status: it depends on where rejection happens, MVC exception resolution, and whether the response is committed.

A production approach can **reject requests before submission** based on permissions, rate/quota, pending request count, and capacity. When rejecting:
- `429 Too Many Requests` generally fits per-identity quota/rate limits.
- `503 Service Unavailable` can fit temporary server/downstream capacity issues.
- Set `Retry-After` only if there is a reliable retry policy.
- Retries must use backoff/jitter and idempotency if requests have side effects.

Do not use an infinite queue just to "avoid seeing 503s". That turns visible overload into long wait times, timeouts, memory pressure, and retry storms.

## 7. Multi-layer timeouts: who controls the clock?

Suppose an application has example thresholds:

```text
Client timeout       5 s
Gateway timeout      4 s
Servlet async        3 s
WebAsyncTask         2 s
Outbound HTTP read   1 s
DB statement         800 ms
```

These are **policy examples** only, not default values.

Layers to distinguish:

- **Client timeout:** the user/caller stopped waiting; the server request may still be running.
- **Reverse proxy/gateway timeout:** ingress stops waiting for upstream, may send 504 or close the connection; the Spring handler may not notice immediately.
- **Servlet async timeout:** the server-side request lifecycle expires; callbacks/interceptors get a chance to build a response/error.
- **WebAsyncTask timeout:** overrides timeout for a specific callable.
- **DeferredResult timeout:** time spent waiting for the callback to supply a result, not bounding external producer jobs.
- **HTTP client connect/read/response timeout:** belongs to the outbound client itself.
- **Database query/transaction timeout:** handled by the driver, pool, and transaction manager within their capabilities.
- **Queue wait:** the task has not started yet, yet the async request clock is already ticking.

**Rule:** HTTP timeouts do not automatically cancel all I/O, stop all workers, roll back transactions, or erase side effects. Even if a Java task is interrupted, drivers/network calls may not stop immediately. Critical data-writing operations need idempotency keys, transaction/uniqueness constraints, and a clear retry model.

## 8. WebAsyncTask: per-request timeout and callbacks

Example:

```java
WebAsyncTask<ResponseEntity<ResultDto>> task =
        new WebAsyncTask<>(400L, () -> {
            ResultDto result = slowService.compute();
            return ResponseEntity.ok(result);
        });

task.onTimeout(() -> ResponseEntity.status(503)
        .body(new ResultDto("timeout")));

task.onCompletion(() -> recordMetrics());
return task;
```

The code above is a **snippet** requiring corresponding beans/services and imports; complete code is in the demo application section.

- `onTimeout(Callable<V>)` returns a fallback result, such as 503 with defined JSON.
- The timeout callback runs on a container thread and **must be very fast**; do not run long DB queries or blocking network calls inside the callback.
- `onError` handles async failures per policy; do not swallow business errors into 200.
- `onCompletion` can be used for cleanup/metrics and must be idempotent and lightweight.
- If the Callable finishes before the deadline, Spring MVC uses the Callable's result to continue the ASYNC dispatch.
- If timeout happens first, the response may finish with the fallback; the Callable can still continue running.
- If the response is already committed, there is no guarantee the callback can change the status/body to a clean error JSON.

Setting a per-request 400ms timeout does not mean a `Thread.sleep(3000)` task will definitely be interrupted at 400ms. Request deadlines and worker lifecycles are two separate concepts.

## 9. DeferredResult and pending requests without using an MVC worker

Long-polling example:

```java
@GetMapping("/events/{id}")
public DeferredResult<ResponseEntity<EventDto>> waitForEvent(
        @PathVariable String id) {

    DeferredResult<ResponseEntity<EventDto>> result =
            new DeferredResult<>(1500L);

    registry.add(id, result);

    result.onTimeout(() -> {
        registry.remove(id, result);
        result.setResult(ResponseEntity.noContent().build());
    });
    result.onCompletion(() -> registry.remove(id, result));

    return result;
}
```

This is an **illustrative snippet**, not a runnable file: `EventDto` and `registry` must be supplied by the application. When an event arrives, a publisher can call `result.setResult(ResponseEntity.ok(event))`, triggering the async dispatch.

Notes:

- `setResult` returns a boolean; after timeout/completion setting a result can fail.
- `onTimeout` runs in the Servlet async lifecycle, not replacing cancellation of the producer job.
- `registry` must bound pending entries and clean up in `onCompletion`/timeout/error; never retain `DeferredResult` objects indefinitely.
- 204 in the example merely represents a **long-poll timeout with no event** under a hypothetical API contract; when representing an availability failure, 503 may be more appropriate.
- Many pending requests still hold HTTP connections, request/response state, and memory even when the worker pool is idle.
- If you submit the producer to a separate executor, that executor needs its own queue/timeout/rejection policy; MVC `setTaskExecutor` does not automatically constrain it.

## 10. Streaming, SSE, and resource limits

`SseEmitter`, `ResponseBodyEmitter`, and `StreamingResponseBody` require dedicated care:

- SSE/long polling holds an HTTP connection open for a long time; total pending sessions must be bounded per user/tenant.
- When clients are slow, buffers grow or writes block; you need backpressure, buffer caps, and drop/disconnect policies.
- Spring MVC may use workers for blocking writes, so the executor must be configured and monitored.
- The HTTP response may already be committed after sending the first chunk; if an error occurs mid-stream, you cannot simply change status to 503 and send regular JSON.
- Client disconnects can raise `IOException`; unregister subscriptions, cancel producers appropriately, and clean up.
- If sending heartbeats, pick a sensible frequency and timeout so keep-alives do not become excessive overhead.
- Do not share one undersized executor across heavy CPU tasks, long streams, and short REST requests if starvation is a risk.
- For jobs taking several minutes, returning `202 Accepted + jobId` and having the client poll status is usually better than holding an HTTP response open indefinitely.

Streaming is not free when a system has thousands of concurrent connections.

## 11. Runnable code: Spring Boot 3 + Java 17

Create a Spring Initializr Java 17+ Maven project with dependencies:
- `spring-boot-starter-web`
- `spring-boot-starter-test` (test scope)

The demo app needs no DB. It uses a dedicated executor with core=2, max=4, queue=8; MVC default async timeout 2500ms. One endpoint uses `Callable`, and another uses `WebAsyncTask` with 400ms to observe a per-request timeout.

Structure:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  MvcAsyncConfig.java
  AsyncDemoController.java
src/test/java/com/example/demo/
  AsyncDemoControllerTest.java
```

### 11.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 11.2. MvcAsyncConfig.java

```java
package com.example.demo;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcAsyncConfig implements WebMvcConfigurer {

    @Bean(name = "mvcAsyncExecutor")
    public ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mvc-async-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(mvcAsyncExecutor());
        configurer.setDefaultTimeout(2500L);
    }
}
```

`@Configuration` proxies bean methods by default, so calling `mvcAsyncExecutor()` from another method in the same configuration class retrieves the **Spring-managed singleton bean**, rather than creating a new executor per request. If switching to `@Configuration(proxyBeanMethods = false)`, do not rely on this direct method call for the singleton; inject the bean from another configuration or wire it explicitly.

This pool is an **exercise-oriented choice**, not a default suitable for every production environment. `AbortPolicy` makes rejections observable, though you need an appropriate admission/error policy if you want to return 503 by contract.

### 11.3. AsyncDemoController.java

```java
package com.example.demo;

import java.util.concurrent.Callable;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/async")
public class AsyncDemoController {

    @GetMapping("/callable")
    public Callable<WorkResponse> callable(
            @RequestParam(defaultValue = "20") long delayMs) {

        long duration = validateDelay(delayMs);

        return () -> {
            Thread.sleep(duration); // Simulate blocking work.
            return new WorkResponse(
                "done", Thread.currentThread().getName());
        };
    }

    @GetMapping("/timed")
    public WebAsyncTask<ResponseEntity<WorkResponse>> timed(
            @RequestParam(defaultValue = "20") long delayMs) {

        long duration = validateDelay(delayMs);

        WebAsyncTask<ResponseEntity<WorkResponse>> task =
                new WebAsyncTask<>(400L, () -> {
                    Thread.sleep(duration);
                    return ResponseEntity.ok(new WorkResponse(
                        "done", Thread.currentThread().getName()));
                });

        task.onTimeout(() ->
            ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new WorkResponse("timeout", "container")));

        task.onCompletion(() -> {
            // Can record lightweight, idempotent metrics/cleanup.
        });
        return task;
    }

    private long validateDelay(long delayMs) {
        if (delayMs < 0 || delayMs > 5000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "delayMs must be between 0 and 5000");
        }
        return delayMs;
    }

    public record WorkResponse(String status, String worker) {}
}
```

Analysis:

- `/async/callable` returns `Callable` so work is offloaded to the MVC executor; default timeout is 2500ms.
- `/async/timed` returns `WebAsyncTask` with a per-request 400ms timeout; the callback can produce HTTP 503 when the deadline expires.
- `delayMs` is bounded between 0 and 5000ms so the demo does not become an infinite sleep endpoint. In production do not expose such an endpoint to public clients.
- `worker` records the executing thread name. The `mvc-async-` prefix comes from the executor; the numeric suffix is not predetermined.
- `Thread.sleep` stalls the worker in the demo; real apps must bound/optimize I/O and service concurrency.
- The timeout fallback **does not guarantee** sleep stopped or side effects were cancelled; if the task keeps running, its late result will not be used as the HTTP body.
- There is no authentication/authorization in the demo; production must protect routes and not let users choose arbitrary work durations.

### 11.4. Starting the app

macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

If `server.port` is unchanged, access `localhost:8080`. The files above require the Spring Boot classpath; `javac AsyncDemoController.java` alone cannot compile without Spring dependencies.

## 12. Curling async responses and timeouts

### Success with Callable

```bash
curl -i 'http://localhost:8080/async/callable?delayMs=20'
```

Expected HTTP 200 and representative JSON:

```json
{
  "status": "done",
  "worker": "mvc-async-1"
}
```

`mvc-async-1` **is just an example**: do not hardcode thread numbers in tests. What matters is `status="done"`.

### WebAsyncTask completing before deadline

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=20'
```

When the system is unsaturated, expect HTTP 200 with `status="done"`. Total time also includes queue wait and thread scheduling; a 20ms sleep does not guarantee every HTTP request returns within 400ms on an overloaded machine.

### Per-request timeout

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=3000'
```

With a standard embedded Servlet container, HTTP usually becomes **503 Service Unavailable** with `status="timeout"` JSON from the callback. Response timing is not a hard real-time guarantee, and the worker may keep running after timeout. If a gateway cuts off earlier, the client may never see the application's JSON fallback.

### Invalid input

```bash
curl -i 'http://localhost:8080/async/timed?delayMs=-1'
```

Expect HTTP 400. If `delayMs=abc`, Spring argument conversion can produce 400 before the controller returns WebAsyncTask.

## 13. MockMvc requires asyncDispatch

For controllers returning `Callable`/`WebAsyncTask`, the first `perform` call usually only confirms the request started Servlet async. The actual HTTP result is handled on the subsequent dispatch, so `asyncDispatch(...)` must be called.

File `src/test/java/com/example/demo/AsyncDemoControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void callableReturnsOnAsyncDispatch() throws Exception {
        MvcResult first = mvc.perform(get("/async/callable")
                    .param("delayMs", "0"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("done"));
    }

    @Test
    void webAsyncTaskReturnsOnAsyncDispatch() throws Exception {
        MvcResult first = mvc.perform(get("/async/timed")
                    .param("delayMs", "0"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("done"));
    }

    @Test
    void badInputFailsBeforeAsyncStarted() throws Exception {
        mvc.perform(get("/async/timed").param("delayMs", "-1"))
            .andExpect(status().isBadRequest());
    }
}
```

Run tests:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

This is a runnable test example given the listed dependencies; **it is not claimed to have been run in the user's repository**. If Spring Security is enabled, set up proper authentication/authorization; a request blocked before MVC does not prove the async controller is broken.

**MockMvc limitations:** it does not fully simulate a real Servlet container's timeout scheduler/error dispatch/network behavior, nor does it test proxies or disconnects. To verify the 400ms timeout and HTTP 503 fallback, use an HTTP integration test with an embedded container on a real port or `curl`; results may vary under heavy load.

## 14. Standalone Java 17: bounded queue and deterministic rejection

A pure Java example showing why a bounded queue produces clear rejection. File `BoundedPoolDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // Worker is guaranteed to be busy.
            Future<?> queued = pool.submit(() -> {});

            boolean rejected = false;
            try {
                pool.submit(() -> {}); // 1 running + 1 queued
            } catch (RejectedExecutionException ex) {
                rejected = true;
            } finally {
                release.countDown();
            }

            running.get();
            queued.get();
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        System.out.println("terminated=" +
                pool.awaitTermination(1, TimeUnit.SECONDS));
    }
}
```

Compile and run with Java 17:

```bash
javac BoundedPoolDemo.java
java BoundedPoolDemo
```

Normal stdout:

```text
rejected=true
terminated=true
```

`CountDownLatch` guarantees the worker is busy before the second task is queued and the third task is rejected, without relying on guesswork like `Thread.sleep(10)`. `terminated=true` occurs when tasks finish and shutdown completes within 1 second; on an unusually stalled machine `awaitTermination` can return false, so this is not a hard real-time guarantee.

In Spring, `ThreadPoolTaskExecutor` usually translates saturation into Spring's `TaskRejectedException`, which must be handled properly at the HTTP/application layer. Do not treat `Executors.newFixedThreadPool` as a bounded queue by default without checking its implementation: that factory's queue can grow unboundedly.

## 15. Timeouts do not cancel side effects and retries need idempotency

Example scenario:

```text
T=0ms     HTTP request starts
T=50ms    Worker starts calling database/payment gateway
T=400ms   Servlet async timeout, client receives 503
T=800ms   Downstream call still processing
T=1200ms  Transaction or payment may commit
T=1400ms  Worker tries to return result, but HTTP request already completed
```

This is a **plausible scenario**, not a default Spring timeline.

Consequence: a client seeing 503 may retry while the previous operation actually succeeded. For orders/payments/data writes, you need:
- Client-generated idempotency keys following a clear contract, with results stored on the backend.
- DB unique constraints/transactions guaranteeing no duplicates are created.
- Deadline/cancellation propagation to outbound clients where supported.
- Never using an HTTP timeout as proof that a transaction rolled back.
- For long jobs, moving to **stateful job processing** returning `202 Accepted` with a job ID; clients poll status via GET.
- Never letting background jobs rely on `HttpServletRequest` remaining alive after the response.

## 16. Admission control, semaphores, and pending requests

A bounded pool limits **workers + queue**, not all pending HTTP requests, SSE connections, or `DeferredResult` registrations. Complete protection requires:

1. Gateway/container limits on total connections, in-flight requests, and request timeouts.
2. Application rate/quota limits per tenant/user and endpoint.
3. Bounded executor core/max/queue with observed rejection policies.
4. DB connection pools and HTTP client connection pools kept within budget.
5. Limits on pending `DeferredResult`/SSE sessions and cleanup.
6. CPU/memory/time budgets for parsing/streaming/response bodies.
7. Separate bulkheads for long-running exports, reports, CPU-heavy jobs, and low-latency REST endpoints.
8. Retry/backoff/circuit breakers so load does not pile onto a slow downstream.

A `Semaphore` can limit concurrency, but you must define whether permits measure **in-flight HTTP requests** or **running workers**. If you release on HTTP timeout while the worker keeps running, you reduced pending request count without reducing actual worker occupancy. If you only release in `Callable.finally` while a task was rejected before starting, a permit might never be returned or might leak differently depending on acquisition order. Semaphore logic must therefore handle success, rejection, timeout, cancellation, disconnects, and idempotent cleanup; do not treat a short `tryAcquire/finally release` block as sufficient for every case.

## 17. Servlet Filters, ASYNC dispatcher, and interceptors

For Servlet async to work:

- The Servlet and relevant filters need `asyncSupported=true` in their registration.
- Filter mappings must include `DispatcherType.ASYNC` if filter logic must run on the async dispatch.
- `OncePerRequestFilter` has `shouldNotFilterAsyncDispatch()`/`shouldNotFilterErrorDispatch()` hooks; do not assume every filter runs exactly once across the entire request.
- `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` may be called when the controller starts async instead of the usual `postHandle`/`afterCompletion` of the initial dispatch.
- When the async result is redispatched, Spring MVC/filters go through an additional lifecycle pass.
- Logs, metrics, and tracing/correlation IDs must avoid double-counting and clean up state when **the request finishes**, not just when the initial `chain.doFilter` returns.

If any Filter in the request chain does not support async, `request.startAsync()` can fail even though the controller returned `Callable`. Especially test WAR deployments on external Servlet containers: registrations and `DispatcherType` behavior can differ from embedded servers.

## 18. ThreadLocal, SecurityContext, Locale, and MDC

An async worker is a different thread. The following contexts **do not automatically propagate completely** across every executor:

- `RequestContextHolder`/Servlet request attributes.
- `LocaleContextHolder`/locale.
- SLF4J `MDC`.
- Spring Security `SecurityContextHolder`.
- Transaction/JPA persistence context.

A task should receive an immutable snapshot of required data via method parameters, such as `Locale`, correlation ID, or authenticated user ID. When propagation is needed for Spring Security/tracing/MDC, use official mechanisms with clear lifecycle/cleanup; do not copy the entire `HttpServletRequest` into a thread pool, and do not enable `InheritableThreadLocal` unconditionally since pooled threads are reused across requests.

Conceptual example:

```java
Locale selectedLocale = locale;
String correlationId = safeGeneratedCorrelationId;

return () -> reportService.prepare(
        selectedLocale, correlationId);
```

This is an illustrative snippet in a controller that has the corresponding beans/variables. Avoid taking trusted identity from self-asserted client headers. Workers must verify authorization when accessing sensitive data according to proper policy.

## 19. Capacity planning and Little's Law

Concurrent request count does not directly equal Java worker thread count. In steady state:

```text
L = λ × W

L: average number of requests in the system
λ: average throughput (requests/second)
W: average time spent in the system (seconds)
```

If an app handles 100 requests/second with 0.25 seconds mean latency, L is roughly 25 active requests, **which does not mean configuring exactly 25 worker threads**. Requests may wait in async state, queues, connections, DB, or network; peak/p99 workloads differ from the mean.

A worker pool with 4 threads where each blocking task occupies 300ms on average has a rough ceiling of around 4/0.3 ≈ 13 tasks/second before overhead. If arrivals continuously exceed sustainable throughput, the queue will fill; increasing queue from 8 to 800 only delays rejection while increasing tail latency and timeouts.

CPU-bound tasks should not use arbitrarily large thread counts; I/O-bound tasks may need higher concurrency, balanced against connection pools, memory, and downstream rate limits. Across multiple replicas, each pod has its own executor, so total concurrency scales by pod count; a shared downstream DB still has a shared limit.

## 20. Metrics and debugging overload/timeouts

| Metric | What to observe |
| --- | --- |
| `poolSize`/`activeCount` | Workers in use; is the pool hitting max? |
| `queueSize`/`queueCapacity` | Backlog and proximity to saturation |
| submitted/completed/rejected tasks | Rejection rate and throughput |
| queue wait time | How long tasks wait before running |
| execution time | How long the work actually takes |
| HTTP total latency p50/p95/p99 | Client experience including queue/dispatch/network |
| Async timeout rate | Are deadlines appropriate? |
| Pending DeferredResult/SSE | Open request registrations and connections |
| DB/HTTP client pool occupancy | Downstream bottlenecks |
| CPU, heap, GC, file descriptors | Process-wide resources |

`ThreadPoolTaskExecutor` provides getters for pool/active/queue state that can be exposed via an appropriate metrics/observability framework. Do not expose internal diagnostic endpoints publicly without authorization.

Debugging workflow:

1. Determine whether 503 comes from `WebAsyncTask.onTimeout`, executor rejection, gateway, or downstream service.
2. Compare queue wait against task execution time: is latency coming from queueing or I/O?
3. Inspect `activeCount`, `queueSize`, `maxPoolSize`, and rejections.
4. Check DB/HTTP connection pools, CPU throttling, and memory.
5. Check for tasks continuing to run after clients have timed out/disconnected.
6. Check for client retry storms; do idempotency and backoff exist?
7. Inspect Servlet REQUEST/ASYNC dispatches, filter/interceptor lifecycles, and correlation IDs.
8. Compare local, HTTP integration, and real gateway environments; MockMvc does not cover all container behavior.
9. Decide on policy fixes: fail fast, adjust workers appropriately, shrink queues, optimize downstream, or move long work to background jobs.

## 21. Common mistakes

1. **Not configuring the MVC executor** and running `Callable` under high load with unbounded concurrency.
2. **Setting a large maxPoolSize with an unbounded queue**; max does not scale up as expected.
3. **Using `CallerRunsPolicy`** while claiming Servlet threads are always released.
4. **Using `DiscardPolicy`** causing requests to hang until timeout with no result.
5. **Assuming `@EnableAsync` governs all MVC Callable processing**.
6. **Thinking `DeferredResult` creates its own worker**; it only holds a result awaiting a producer.
7. **Thinking MVC timeout automatically cancels all `@Async`/background jobs**.
8. **Treating 503 as proof that a DB transaction did not commit**.
9. **Omitting outbound HTTP/DB timeouts**; workers keep waiting long after the HTTP timeout.
10. **Omitting queue wait from the end-to-end latency budget**.
11. **Retaining pending DeferredResult or SSE handles forever**, leaking request references.
12. **Not handling the race when `setResult` runs after timeout**.
13. **Using streaming without bounding buffers/backpressure**.
14. **Running blocking I/O inside `onTimeout`/`onCompletion`** on a container thread.
15. **Misconfiguring filter `asyncSupported` and `DispatcherType.ASYNC`**.
16. **Double-counting metrics** due to REQUEST and ASYNC dispatches.
17. **Carrying raw ThreadLocal request context across a thread pool**.
18. **Using huge queues to hide overload**, increasing latency and retry storms.
19. **Catching TaskRejectedException and returning 200** or swallowing the exception.
20. **Testing without `asyncDispatch`** and thinking the test verified the body.
21. **Relying on MockMvc to verify gateway/Servlet timeouts**.
22. **Failing to separate long jobs from low-latency interactive endpoints**.
23. **Lacking per-user/tenant rate and concurrency limits**.
24. **Scaling workers past the DB connection pool** and making the system slower.
25. **Lacking bounded load tests** in staging to verify timeouts/rejections.
26. **Enabling virtual threads prematurely** and assuming DB/socket/memory limits vanish.
27. **Not cleaning up producers on client disconnect**, leaving dangling resources.
28. **Lacking graceful shutdown** while pods hold active async requests.

## 22. Production implementation checklist

### Executor

- [ ] Does Spring MVC `configureAsyncSupport` use an `AsyncTaskExecutor` with bounded capacity?
- [ ] Do core/max/queue sizes reflect the workload type and downstream bottlenecks?
- [ ] Is it understood that the queue usually fills before workers scale past core?
- [ ] Does rejection return a proper status/error contract without silently dropping?
- [ ] Are you avoiding accidental `CallerRuns` that blocks Servlet request threads?
- [ ] Are executors for streams/exports/long jobs separated if needed?
- [ ] Are active/queue/rejected metrics and alerts in place?
- [ ] Are shutdown/draining/termination budgets configured intentionally?

### Timeout

- [ ] Is the MVC default async timeout clearly defined and tested on a real container?
- [ ] Do specialized requests set proper `WebAsyncTask`/`DeferredResult` timeouts?
- [ ] Do gateway/client/downstream timeouts fit together in the latency budget?
- [ ] Are timeout/cancellation and transaction side effects designed explicitly?
- [ ] Is there an idempotency/retry policy for unsafe writes?
- [ ] Do pending DeferredResult/SSE registries have capacity limits and cleanup?
- [ ] Are callbacks non-blocking and are committed responses handled safely?

### Testing/operations

- [ ] Does MockMvc verify `asyncStarted` and `asyncDispatch`?
- [ ] Do integration tests cover timeout, rejection, and disconnect scenarios?
- [ ] Are there bounded load tests measuring queue wait, p95/p99, and recovery?
- [ ] Are Filter/Servlet `ASYNC` registrations correct?
- [ ] Are SecurityContext, Locale, MDC, and tracing prevented from leaking across threads?
- [ ] Is there an option to move long work to `202 Accepted + job status` instead of long-lived requests?

## 23. Self-check questions

**1.** Which thread does an MVC `Callable` run on?

**Answer:** Typically on the MVC `AsyncTaskExecutor` after the initial servlet request thread leaves the dispatch. The Servlet async request still keeps the response open.

**2.** Does `setTaskExecutor` automatically choose the executor for all `@Async` methods?

**Answer:** No. `@Async` is a separate mechanism; sharing an executor requires deliberate configuration.

**3.** Why might maxPoolSize=50 only have two active workers in practice?

**Answer:** If core=2 and the queue is not full, new tasks go into the queue; the pool does not expand toward max yet.

**4.** Does a WebAsyncTask timeout callback guarantee the worker has stopped?

**Answer:** No. It handles the response lifecycle and does not necessarily cancel I/O or roll back side effects.

**5.** Does DeferredResult run business work on the MVC executor by itself?

**Answer:** No. The result is supplied by an application publisher/event/job.

**6.** Why avoid DiscardPolicy by default for HTTP Callables?

**Answer:** Tasks can be silently lost, leaving HTTP requests hanging until timeout without producing a response.

**7.** What can CallerRunsPolicy do under overload?

**Answer:** Run the task on the submitting thread—which may be the Servlet thread—blocking request handling.

**8.** What is needed in tests to verify the final body of a Callable?

**Answer:** `request().asyncStarted()`, capture `MvcResult`, then `mvc.perform(asyncDispatch(result))`.

**9.** Can MockMvc alone verify a 400ms Servlet container timeout?

**Answer:** Not completely. Use HTTP integration tests against a real server, accounting for gateways and schedulers.

**10.** Why does a 503 after a payment request require idempotency?

**Answer:** The earlier work may still commit after timeout; client retries without idempotency can create duplicate transactions.

**11.** If a pool has 4 workers and queue 8, is the maximum HTTP connection count 12?

**Answer:** No. That is only the task capacity of that pool; pending async requests, DeferredResult/SSE, and connections have separate limits.

**12.** When work takes several minutes, should you keep a 5-minute WebAsyncTask or switch to a job?

**Answer:** Typically switch to a job queue with `202 Accepted` and a status endpoint to decouple job lifetime from the HTTP connection.

## 24. References

- Spring Framework 6.2 — Asynchronous Requests and `configureAsyncSupport`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — `AsyncSupportConfigurer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html
- Spring Framework — `WebAsyncTask` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/context/request/async/WebAsyncTask.html
- Spring Framework — `DeferredResult` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/web/context/request/async/DeferredResult.html
- Spring Framework — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/async-requests.html
- Spring Security — MVC Async Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Java 17 — ThreadPoolExecutor: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java 17 — ArrayBlockingQueue: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
