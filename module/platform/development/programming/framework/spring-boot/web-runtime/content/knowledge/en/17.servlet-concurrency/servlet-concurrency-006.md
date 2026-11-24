# Configuring the Task Executor for Spring MVC Asynchronous Processing

> **Scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**, **Spring MVC running on the Servlet stack**. This article explains the Servlet async flow, `AsyncTaskExecutor`, how Spring Boot provides `applicationTaskExecutor`, how to tune pools and timeouts, how to use `WebMvcConfigurer#configureAsyncSupport`, `Callable`, `WebAsyncTask`, `DeferredResult`, streaming, task rejection handling, context propagation, load measurement, and testing. The Maven example runs on Spring Boot **3.5.0** with JDK 17.

## 1. The problem: why does MVC async need its own executor?

In synchronous Spring MVC, a request typically holds a Servlet container thread while controller and service methods execute. When a task blocks for a long time (blocking call to a slow service/DB), the Servlet worker stays busy until the request finishes.

Spring MVC supports **asynchronous request processing** per the Servlet API: a controller can return `Callable<T>`, `WebAsyncTask<T>`, or `DeferredResult<T>`. MVC then puts the request into async mode so the initial Servlet thread can exit; once the result completes later, it dispatches back to a container thread to write the HTTP response.

An important operational question follows: **which thread pool runs the blocking work, how many threads does it have, what are the queue limits, and how does the application handle timeouts or rejections?** That is the role of `AsyncTaskExecutor`.

**Do not conflate pools:**

| Component | Purpose | What not to infer |
|---|---|---|
| Servlet container thread pool | Accept/dispatch HTTP requests, run Servlet pipeline | Not automatically where Spring MVC runs `Callable` tasks |
| MVC `AsyncTaskExecutor` | Execute `Callable` / `WebAsyncTask`; support certain async streaming writes | Does not turn DB/JDBC into non-blocking I/O |
| Executor used for `DeferredResult` | Chosen by the **application** when handling events/work to complete the result | MVC does not submit your logic to a pool automatically |
| `@Async` executor | Execute methods intercepted by Spring AOP `@Async` | Not synonymous with MVC async merely because both say “async” |
| Spring scheduler | Run scheduled jobs | Not the default replacement for MVC's executor |
| Reactor Netty event loop (WebFlux) | Handle non-blocking I/O of a reactive server | Not a Servlet MVC worker pool |

Spring MVC can free the Servlet thread while waiting, yet the request/connection remains open; there is no guarantee of faster processing or unlimited throughput. When the backend calls blocking APIs, **another worker thread is still occupied** while waiting.

## 2. How does the Servlet async flow work?

### 2.1. With Callable<T>

Diagram:

~~~text
Client
  |
  v
Tomcat Servlet worker: REQUEST dispatch
  |
  v
DispatcherServlet -> Controller returns Callable<T>
  |
  +--> Spring MVC calls startAsync()
  |    and submits Callable to AsyncTaskExecutor
  |
  +--> Initial Servlet worker returns to container
  |    (HTTP response not yet complete)
  |
  v
mvc-worker-1: Callable.call() executes
  |
  +--> service, DB, remote call, result or exception
  |
  v
Async result registered with Spring MVC
  |
  v
Servlet container: ASYNC dispatch
  |
  v
DispatcherServlet handles result, converter/exception resolver
  |
  v
HTTP status + headers + body sent to client
~~~

Key points:

1. The controller is invoked on the initial HTTP pass and returns a `Callable` without waiting for `call()` to finish.
2. Spring MVC activates Servlet async processing and submits the `Callable` to `AsyncTaskExecutor`.
3. Once a result/exception is produced, the container performs an **ASYNC redispatch**; `DispatcherServlet` processes the result again.
4. The HTTP response completes through message conversion, view rendering, or exception handling.
5. Async timeouts/errors can trigger lifecycle callbacks and exception resolution.

This is not HTTP “fire-and-forget.” The client still waits for a response; the application must ensure completion or timeout.

### 2.2. With DeferredResult<T>

`DeferredResult` differs from `Callable` in that **the application decides when and where the result is supplied**:

~~~text
Controller returns DeferredResult<T>
  |
  +--> Spring MVC activates async request
  |
  +--> an app-managed event/callback/task
           |
           +--> deferredResult.setResult(value)
           +--> deferredResult.setErrorResult(exception)
  |
  v
Spring MVC ASYNC redispatch -> response
~~~

MVC **does not pull a `Callable` out of `DeferredResult` to submit to an executor**. If the app wants to run work on a thread pool, the app must submit a `Runnable`/`Callable` to a chosen executor itself. If the result comes from a Kafka callback, message broker, or another event loop, no extra blocking task may be needed.

### 2.3. With WebAsyncTask<T>

`WebAsyncTask` wraps a `Callable` while allowing a custom timeout, per-request executor, and timeout/error/completion callbacks. It fits well when a specific endpoint needs a different timeout from the global default or specific task policies.

Fragment example:

~~~java
@GetMapping("/task")
public WebAsyncTask<String> task() {
    WebAsyncTask<String> result =
            new WebAsyncTask<>(3000L, () -> "completed");

    result.onTimeout(() -> "timed-out");
    return result;
}
~~~

This snippet is a **method fragment** inside a controller, not a standalone class. `3000L` is **3,000 milliseconds**, not 3,000 seconds. Normally it returns `completed`; the timeout callback runs only if the request actually times out.

## 3. Spring Boot 3.5 auto-configures applicationTaskExecutor

In a typical Boot application, when no custom `Executor` bean triggers auto-configuration back-off, Boot auto-configures an `AsyncTaskExecutor` and registers it under the name **`applicationTaskExecutor`**.

- With **platform threads** (such as Java 17), Boot 3.5 normally creates a `ThreadPoolTaskExecutor` with sensible defaults.
- With **virtual threads** (Java **21+**, `spring.threads.virtual.enabled=true`), Boot may use a virtual-thread-based `SimpleAsyncTaskExecutor`; `spring.task.execution.pool.*` properties will no longer have the same effect.
- Boot integrates this executor with multiple features such as Spring MVC async, certain WebFlux/GraphQL/WebSocket integrations, and other tasks depending on present beans/configuration.
- Specifically for **Spring MVC**, Boot expects the integrated executor to be named **`applicationTaskExecutor`** and have type **`AsyncTaskExecutor`**.

Consequently, an arbitrary `Executor` bean may **not** be selected by Spring MVC as you expect. For instance, defining `@Bean("taskExecutor") Executor` for `@Async` does not guarantee MVC `Callable` tasks run on it.

### 3.1. Tuning the pool via application.properties with the auto-configured executor

If you let Boot manage the executor, you can configure:

~~~properties
# Used in Option A: let Boot auto-create the executor.
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=32
spring.task.execution.pool.keep-alive=30s
spring.task.execution.thread-name-prefix=mvc-worker-
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s

# Timeout for async HTTP requests in Spring MVC:
spring.mvc.async.request-timeout=5s
~~~

This is **standalone Option A**. Do not also define `@Bean("applicationTaskExecutor")` in the same project and assume the `spring.task.execution.pool.*` properties above will configure your manually created bean. Those properties primarily govern the **Boot auto-configured** executor.

Spring Boot 3.5 defaults to a core size of **8** for the platform-thread `ThreadPoolTaskExecutor`; you can tune it via properties. Do not assume default values are optimal for every workload.

**Queue nuances:**

- `core-size=4` sets the baseline core threads.
- `queue-capacity=32` keeps the queue **bounded** instead of unbounded.
- `max-size=8` only takes effect once the queue is full and the pool needs to grow past `core-size`.
- When all 8 threads are busy and the queue is full, new tasks may be rejected; do not leave the queue unbounded merely to “avoid errors,” because latency and memory can grow unchecked.
- Measure service time, arrival rate, CPU, DB pools, downstream limits, and deadlines when sizing.

A large queue lets requests sit waiting a long time before starting, potentially **timing out before business logic even runs**. Queue capacity, request timeouts, and client/proxy timeouts must be designed together.

### 3.2. With a custom Executor bean: why does Boot back off?

Spring Boot 3.5 uses conditional auto-configuration: when the application defines an `Executor` bean, Boot may **back off** instead of creating the default `AsyncTaskExecutor`.

For example, having only:

~~~java
@Bean("taskExecutor")
Executor someExecutor() {
    return Executors.newFixedThreadPool(4);
}
~~~

is a **fragment** needing imports and lifecycle cleanup; it is **not enough** to guarantee MVC async uses this executor. Moreover, `@Async` has its own executor resolution rules.

Valid options:

1. Explicitly define an **`applicationTaskExecutor` bean of type `AsyncTaskExecutor`** for MVC.
2. Use `WebMvcConfigurer#configureAsyncSupport` to set a specific executor at the Spring MVC layer.
3. If you still want Boot to auto-configure its executor despite custom `Executor` beans, consider Boot **3.5**'s **`spring.task.execution.mode=force`** property; inspect its effects carefully, as it also affects executor selection for other integrations and `@Async` when no `AsyncConfigurer` is present.
4. When multiple executors exist, use clear names and qualifiers; use `@Async("specificExecutor")` or `AsyncConfigurer` for business tasks needing isolated pools.

Do not change the executor for every framework integration just to cope with one slow endpoint. In multi-service apps, isolating pools prevents one workload from saturating everything else.

### 3.3. When to use spring.task.execution.mode=force?

Boot 3.5 can be configured with:

~~~properties
spring.task.execution.mode=force
~~~

In this mode, Boot attempts to create and prefer its auto-configured executor for integrations even if the application registers custom `Executor` beans. However, `@Async` executor selection still checks `AsyncConfigurer`; adding `@Primary` or naming a bean `taskExecutor` does not necessarily override the executor for every integration under `force` mode.

**Do not enable `force` by default** when you already have a deliberate multi-executor design; it can alter task execution across other modules. In this article, the runnable project uses **Option B: explicit bean declaration**, without `force`.

## 4. WebMvcConfigurer#configureAsyncSupport: customizing at the MVC layer

Spring Framework provides the callback:

~~~java
@Override
public void configureAsyncSupport(
        AsyncSupportConfigurer configurer) {

    configurer.setTaskExecutor(mvcAsyncExecutor);
    configurer.setDefaultTimeout(5000L);
}
~~~

This method belongs in a class that `implements WebMvcConfigurer`, with `mvcAsyncExecutor` injected beforehand.

Key APIs:

| API | Meaning |
|---|---|
| `AsyncSupportConfigurer#setTaskExecutor` | Specifies the `AsyncTaskExecutor` for MVC `Callable` and blocking writes when streaming reactive values |
| `setDefaultTimeout(long)` | Default timeout in **milliseconds** for MVC async processing |
| `registerCallableInterceptors(...)` | Adds `CallableProcessingInterceptor` to observe callable lifecycles |
| `registerDeferredResultInterceptors(...)` | Adds `DeferredResultProcessingInterceptor` for deferred requests |
| `WebAsyncTask` | Can specify per-request timeout/executor/callbacks |
| `DeferredResult(Long timeout)` | Can set a per-request timeout on a deferred request |

**Timeout precedence:** the Servlet container default may be used if no MVC timeout is set; settings on `WebAsyncTask` or `DeferredResult` can override the default for a specific request. Client, ingress, and gateway deadlines also apply.

**Do not add `@EnableWebMvc`** just to customize async support in Spring Boot. `@EnableWebMvc` causes Boot MVC auto-configuration to back off; `@Configuration` + `implements WebMvcConfigurer` suffices for additional overrides.

## 5. Complete project: a bounded AsyncTaskExecutor + 3 async endpoint styles

Project goals:

- `Callable<ReportView>` showing Spring MVC submitting work to the worker pool.
- `WebAsyncTask<ResponseEntity<ReportView>>` with its own timeout and timeout callback.
- `DeferredResult<ResponseEntity<ReportView>>` **explicitly submitted by the application** to the same executor and completed via `setResult` / `setErrorResult`.
- Bounded pool size and queue, with an observable thread prefix.
- Advice handling `TaskRejectedException` when the pool saturates.
- `MockMvc` tests using `asyncStarted()` and `asyncDispatch()`.

### 5.1. Project structure

~~~text
mvc-async-executor-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mvcasync/
    MvcAsyncApplication.java
    ExecutorConfiguration.java
    MvcAsyncConfiguration.java
    ReportService.java
    AsyncReportController.java
    AsyncErrorAdvice.java
  src/test/java/com/example/mvcasync/
    AsyncReportControllerTest.java
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-async-executor-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-web` uses Spring MVC and embedded Tomcat in its default configuration. **`spring-boot-starter-webflux` is not required** to use `Callable`, `DeferredResult`, or `WebAsyncTask`.

### 5.3. application.properties

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Demo uses Option B: declare applicationTaskExecutor in Java.
# Do not set spring.task.execution.pool.* here because they
# do not configure a manually created ThreadPoolTaskExecutor bean.
~~~

### 5.4. Entry point

`src/main/java/com/example/mvcasync/MvcAsyncApplication.java`:

~~~java
package com.example.mvcasync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcAsyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcAsyncApplication.class, args);
    }
}
~~~

### 5.5. ExecutorConfiguration: bounded pool and standard bean name

`src/main/java/com/example/mvcasync/ExecutorConfiguration.java`:

~~~java
package com.example.mvcasync;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class ExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("mvc-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);

        return executor;
    }
}
~~~

Explanation:

- **Bean name `applicationTaskExecutor`** ensures Spring Boot recognizes the executor intended for MVC async.
- Return type `ThreadPoolTaskExecutor` implements `AsyncTaskExecutor`, unlike a raw JDK `Executor` that only has `execute`.
- Core 4, max 8, queue 32 are **illustrative values**, not recommended defaults for every server.
- The thread prefix makes worker threads easy to spot in tests and logs.
- `ThreadPoolTaskExecutor` is a Spring-managed bean, initialized and closed by the container lifecycle. Do not call `initialize()` again inside the `@Bean` method when the container manages it.
- `setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(10)` express an intent to wait briefly on shutdown; they do **not** guarantee every request finishes if ingress/client/server already timed out or the process is killed.

If the system has multiple executors, verify whether `@Async`, JPA, WebSocket, bootstrap tasks, or other auto-configured integrations also use this bean. You can isolate pools for specialized workloads so one task group does not saturate the entire system.

### 5.6. MvcAsyncConfiguration: choosing the MVC pool + timeout

`src/main/java/com/example/mvcasync/MvcAsyncConfiguration.java`:

~~~java
package com.example.mvcasync;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcAsyncConfiguration implements WebMvcConfigurer {

    private final AsyncTaskExecutor executor;

    public MvcAsyncConfiguration(
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    @Override
    public void configureAsyncSupport(
            AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(executor);
        configurer.setDefaultTimeout(5_000L);
    }
}
~~~

This article deliberately **specifies the executor via both bean name and `configureAsyncSupport`** so demo behavior does not depend on bean-selection guesswork as configuration grows. In a simple Boot app, having only the `applicationTaskExecutor` bean or Boot's auto-configured executor usually suffices for MVC integration; calling `setTaskExecutor` here mainly highlights Spring MVC's extension point.

`5_000L` = 5 seconds. That is the **default request timeout**, not the timeout for every JDBC/HTTP call inside the worker thread. Set separate deadlines for downstream I/O and plan cancellation for work that is no longer needed.

### 5.7. ReportService: simulating blocking work on a worker

`src/main/java/com/example/mvcasync/ReportService.java`:

~~~java
package com.example.mvcasync;

import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public ReportView load(String id) throws InterruptedException {
        // Demo simulates a blocking dependency for 80ms.
        // Production should configure timeouts for real JDBC/HTTP clients.
        TimeUnit.MILLISECONDS.sleep(80);

        return new ReportView(
                id, Thread.currentThread().getName());
    }

    public record ReportView(
            String id, String workerThread) {
    }
}
~~~

`sleep(80)` is purely for demo observation and to create a clear async boundary; **do not** use sleep in business logic. With blocking JDBC, the worker thread remains occupied while waiting; size pools and downstream connection limits accordingly.

### 5.8. AsyncReportController: Callable, WebAsyncTask, and DeferredResult

`src/main/java/com/example/mvcasync/AsyncReportController.java`:

~~~java
package com.example.mvcasync;

import java.util.concurrent.Callable;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.context.request.async.WebAsyncTask;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/async")
public class AsyncReportController {

    private final ReportService service;
    private final AsyncTaskExecutor executor;

    public AsyncReportController(
            ReportService service,
            @Qualifier("applicationTaskExecutor")
            AsyncTaskExecutor executor) {
        this.service = service;
        this.executor = executor;
    }

    @GetMapping("/callable/{id}")
    public Callable<ReportService.ReportView> callable(
            @PathVariable String id) {

        // Controller method returns Callable immediately.
        // Spring MVC submits Callable to the configured executor automatically.
        return () -> service.load(id);
    }

    @GetMapping("/web-async-task/{id}")
    public WebAsyncTask<ResponseEntity<ReportService.ReportView>>
            webAsyncTask(@PathVariable String id) {

        WebAsyncTask<ResponseEntity<ReportService.ReportView>>
                task = new WebAsyncTask<>(
                        3_000L,
                        () -> ResponseEntity.ok(service.load(id))
                );

        task.onTimeout(() -> ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ReportService.ReportView(
                        id, "timed-out")));

        return task;
    }

    @GetMapping("/deferred/{id}")
    public DeferredResult<ResponseEntity<ReportService.ReportView>>
            deferred(@PathVariable String id) {

        DeferredResult<ResponseEntity<ReportService.ReportView>>
                result = new DeferredResult<>(3_000L);

        result.onTimeout(() -> result.setErrorResult(
                new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Async result was not produced in time")));

        // Spring MVC does NOT submit this code for DeferredResult automatically.
        // The application explicitly uses an executor of its own choosing.
        executor.execute(() -> {
            try {
                ReportService.ReportView report = service.load(id);
                result.setResult(ResponseEntity.ok(report));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                result.setErrorResult(new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Async task interrupted", ex));
            } catch (Exception ex) {
                result.setErrorResult(ex);
            }
        });

        return result;
    }
}
~~~

**Distinguishing the three branches:**

| Endpoint | Who submits the work? | Timeout |
|---|---|---|
| `/callable/{id}` | **Spring MVC** submits the returned `Callable` | Default 5 seconds from `configureAsyncSupport` |
| `/web-async-task/{id}` | MVC executes the `Callable` inside `WebAsyncTask` | Per-request timeout 3 seconds + callback |
| `/deferred/{id}` | **Application** calls `executor.execute`; later `setResult` or `setErrorResult` | Per-`DeferredResult` 3 seconds + error result |

The sample deliberately shares one executor for easy observation. In systems with mixed workloads, use a separate executor for `DeferredResult` work so it does not compete for the same pool as MVC `Callable`/streaming tasks.

**Timeout does not automatically cancel the worker:** if the request times out while a JDBC call is still blocking, the thread can continue running. Calling `DeferredResult#setResult` after completion returns `false` (it cannot replace an already-finished response). Production code needs cancellation/cooperative interruption, downstream timeouts, and proper cleanup.

### 5.9. AsyncErrorAdvice: handling task rejection at the MVC layer

`src/main/java/com/example/mvcasync/AsyncErrorAdvice.java`:

~~~java
package com.example.mvcasync;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class AsyncErrorAdvice {

    @ExceptionHandler(TaskRejectedException.class)
    public ResponseEntity<ProblemDetail> rejected(
            TaskRejectedException exception) {

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Async capacity is temporarily exhausted");
        body.setTitle("Server busy");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.RETRY_AFTER, "1")
                .body(body);
    }
}
~~~

`TaskRejectedException` occurs when the executor refuses additional tasks (for instance, both pool and queue are full). The advice catches it **when the exception flows through MVC exception handling and the response has not committed**. This does not guarantee every overload condition becomes a 503; failures at the container, network, or post-commit stage require different handling.

**Do not mechanically use `CallerRunsPolicy`** to avoid rejections: if the caller is the Servlet request thread, that policy runs blocking work directly on the Servlet worker, defeating MVC async's thread release. Prefer backpressure, capacity bounds, 503/429 per contract, and load monitoring.

## 6. Run and verify the application

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or package:

~~~bash
mvn clean package
java -jar target/mvc-async-executor-demo-1.0.0.jar
~~~

Send requests:

~~~bash
curl -i http://localhost:8080/api/async/callable/42
curl -i http://localhost:8080/api/async/web-async-task/42
curl -i http://localhost:8080/api/async/deferred/42
~~~

Under normal conditions, **each endpoint** returns HTTP **200 OK** with a two-field JSON body:

~~~json
{
  "id": "42",
  "workerThread": "mvc-worker-1"
}
~~~

The worker thread name may differ depending on request/thread creation order, such as `mvc-worker-2` or `mvc-worker-3`; only the `mvc-worker-` prefix is configured in code. Do not expect identical thread suffixes or JSON spacing/key ordering.

**Key result:** `ReportService.load` runs on an `mvc-worker-*` thread created by `ThreadPoolTaskExecutor`, rather than staying on the initial Servlet HTTP request thread. From the client's perspective, it remains a single HTTP request despite the internal async redispatch.

### 6.1. Sending multiple concurrent requests

Example sending three requests with different IDs:

~~~bash
curl "http://localhost:8080/api/async/callable/A" &
curl "http://localhost:8080/api/async/callable/B" &
curl "http://localhost:8080/api/async/callable/C" &
wait
~~~

Bash launches all three `curl` commands concurrently. Output may interleave because multiple processes write to stdout; completion order is **non-deterministic**. Use separate output files or a load-testing tool such as k6/JMeter to measure timings and throughput.

**Do not infer throughput from three curl requests**: measure CPU, p95/p99 latency, queue depth, downstream connection pools, and total concurrent requests.

## 7. MockMvc testing: asyncStarted and asyncDispatch

For controllers returning `Callable` or `DeferredResult`, `MockMvc` typically returns an `MvcResult` whose async processing **has not yet finished dispatching**. Asserting HTTP status right after `perform` checks the wrong phase.

Correct flow:

1. `perform(get(...))` and `andExpect(request().asyncStarted())`.
2. Capture `MvcResult` and optionally await `getAsyncResult(timeout)`.
3. `perform(asyncDispatch(result))` so Spring MVC processes the response once the result is ready.
4. Assert status, headers, JSON, and thread prefix.

`src/test/java/com/example/mvcasync/AsyncReportControllerTest.java`:

~~~java
package com.example.mvcasync;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncReportControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void callableRunsOnConfiguredMvcExecutor()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/callable/42"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("42"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }

    @Test
    void webAsyncTaskAlsoUsesMvcWorker()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/web-async-task/7"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("7"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }

    @Test
    void deferredResultIsCompletedByApplicationExecutor()
            throws Exception {

        MvcResult pending = mvc.perform(
                get("/api/async/deferred/9"))
            .andExpect(request().asyncStarted())
            .andReturn();

        pending.getAsyncResult(5_000L);

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("9"))
            .andExpect(jsonPath("$.workerThread",
                    startsWith("mvc-worker-")));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test suite verifies:

- Spring MVC actually starts asynchronous processing for all three types.
- Results are redispatched and return HTTP 200 per contract.
- Business work executes on threads matching the configured executor prefix rather than running synchronously in the controller.
- Tests do not depend on exact thread indices `-1` or `-2`.

**Limitations:** `MockMvc` simulates MVC dispatch inside the Spring context without opening sockets to embedded Tomcat. It does not test Servlet `asyncSupported` flags on custom filters, gateway timeouts, disconnects, thread/connection pool exhaustion, or HTTP/2 behavior. For systems with ingress/proxies or custom Servlet registrations, add `@SpringBootTest(webEnvironment = RANDOM_PORT)` + real HTTP client tests.

## 8. Setting accurate timeouts: three distinct layers

No single timeout guarantees every request stops safely. Separate:

| Layer | Example | What does it control? |
|---|---|---|
| MVC async request timeout | `spring.mvc.async.request-timeout=5s` or `setDefaultTimeout(5000)` | How long the request stays in async processing before timing out |
| Per-request timeout | `WebAsyncTask(3000L, ...)`, `DeferredResult(3000L)` | Deadline specific to that endpoint |
| Downstream operation timeout | JDBC query timeout, HTTP client connect/read/response timeout | How long the **actual task** may wait on backends |
| Proxy/client timeout | ingress, gateway, HTTP client | How long the client/edge will wait for an HTTP response |

### 8.1. Where does the timeout clock start?

Under Servlet async semantics, the timeout generally starts after the initial Servlet request thread exits and stops when the async dispatch completes. Do not treat it as an absolute stopwatch starting when the request entered earlier filters and middleware.

A `Callable` task can sit waiting in the queue until the request times out. The response-processing timeout **does not necessarily interrupt the `Callable`** or stop underlying I/O; the worker may run late after the client already received an error.

### 8.2. Timeout callbacks are not magic cancellation

Example:

~~~java
WebAsyncTask<ResponseEntity<String>> task =
        new WebAsyncTask<>(1000L, () -> slowCall());

task.onTimeout(() -> ResponseEntity
        .status(503)
        .body("Timed out"));
~~~

This is a fragment with a hypothetical `slowCall()` that needs imports; it is not the runnable project in section 5. The callback lets you return a fallback result **when Spring receives the timeout event and the response is uncommitted**, rather than guaranteeing `slowCall` stops.

If the work has critical side effects (charging money, sending email), design idempotency keys, cancellation semantics, and independent job state instead of relying solely on HTTP timeouts.

### 8.3. Return 202 Accepted when work outlives the request

If a business task runs for minutes or clients frequently disconnect, do not keep an async HTTP request open indefinitely. Instead:

1. `POST /jobs` accepts the request and returns **202 Accepted** with a job ID.
2. A backend queue/task service executes the work separately with retries/idempotency.
3. The client polls `GET /jobs/{id}` for status or subscribes to events.
4. Results are stored independently of the HTTP connection, with TTL/cleanup and authorization.

Spring MVC async fits work needing **one HTTP response after a short, bounded wait**; it does not replace message queues or job orchestration for long-running tasks.

## 9. Pool sizing: core, max, queue, and system limits

Assume `core=4`, `max=8`, `queue=32` as in the demo. `ThreadPoolTaskExecutor` uses `ThreadPoolExecutor` underneath:

1. When fewer than 4 core threads are running, the pool can create new core workers.
2. Once core threads are busy, tasks are normally queued while queue space remains.
3. Only when the queue is full and room remains below `max` does the pool create additional workers.
4. If the pool is at `max` and the queue is full, new tasks may be rejected.

This is standard queue-based `ThreadPoolExecutor` behavior, not “the pool always runs 8 threads at all times.” Configuration values must be grounded in load measurements.

### 9.1. Capacity mental model

If arrival rate is roughly `λ` requests/second and on average a task holds a worker for `W` seconds, average concurrency is roughly `L = λ × W` by Little's Law in steady state. This is an **estimation tool**, not an automatic rule for setting `maxThreads`: distribution, p99, queues, DB pools, and resource bottlenecks matter greatly.

Examples:

- 40 tasks/second × 0.1 s/task ≈ 4 concurrently executing tasks.
- If downstream slows to 1 s/task, the same arrival rate needs roughly 40 concurrent tasks to avoid queue buildup.
- Spinning up 40 threads still will not help if the DB connection pool has only 10 connections or CPU is saturated.

When arrival rate exceeds service capacity for an extended period, queues grow until limits break. Never fix that with unbounded queues; use backpressure, load shedding, jittered retries, and downstream optimization.

### 9.2. Isolating workloads and protecting resources

Consider separate executors if:

- One API has very slow blocking operations that risk starving the whole pool.
- One task group needs a specific thread context or priority.
- Long-lived streaming/file downloads compete with fast `Callable` calls.
- Heavy volumes of `@Async` business jobs or background tasks exist.

Even with separate pools, maintain a total budget for threads, DB connections, memory, and network. Multiple executors do not create more physical hardware.

### 9.3. Runtime monitoring

With `ThreadPoolTaskExecutor`, you can inspect:

- `getActiveCount()`: workers currently executing.
- `getPoolSize()` and `getCorePoolSize()`.
- `getQueueSize()`: tasks currently waiting.
- Rate of rejected submissions, HTTP 503/504, async timeouts.
- Request latency p50/p95/p99 and queue wait time.
- Downstream pool saturation / slow DB queries.

Fragment example for internal health/metrics:

~~~java
ThreadPoolTaskExecutor executor = ...;

int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queued = executor.getQueueSize();
~~~

This is a **fragment** where `executor` is an injected Spring bean; it is not a standalone class. Never expose full metrics or stack traces unprotected to the internet. Micrometer/Actuator can power dashboards when properly configured.

## 10. @Async vs. Servlet MVC asynchronous requests

Suppose a service has:

~~~java
@Async
public CompletableFuture<String> calculate() {
    return CompletableFuture.completedFuture("value");
}
~~~

`@Async` only takes effect when Spring's async method interception is enabled (typically `@EnableAsync`), the call passes through a Spring proxy, and the method/bean qualifies. Self-invocation or non-proxied calls will not be dispatched to the executor.

Meanwhile:

~~~java
@GetMapping("/callable")
public Callable<String> callable() {
    return () -> "value";
}
~~~

Spring MVC recognizes the `Callable` return value and coordinates it through Servlet async support; **`@EnableAsync` is not required**.

A method can combine models, yet you should avoid accidentally **submitting twice to two different executors** and losing observability/timeouts. `CompletableFuture.supplyAsync(...)` without an explicit executor normally runs on `ForkJoinPool.commonPool()`, **not automatically on `applicationTaskExecutor`**.

Example specifying the executor explicitly:

~~~java
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> "value", applicationTaskExecutor);
~~~

This fragment assumes `applicationTaskExecutor` is in scope. When a controller returns `CompletableFuture`, Spring MVC can adapt it as an async result, while **the code creating the future** chooses which executor runs the work.

## 11. StreamingResponseBody, SseEmitter, and reactive return types

### 11.1. StreamingResponseBody

`StreamingResponseBody` lets code write directly to the response `OutputStream` after the controller returns, useful for large downloads. Servlet output writes can still be **blocking**, so configure an appropriate executor and HTTP timeouts.

~~~java
@GetMapping("/sample-download")
public StreamingResponseBody download() {
    return outputStream -> {
        outputStream.write("demo".getBytes(
                StandardCharsets.UTF_8));
        outputStream.flush();
    };
}
~~~

This is a controller method fragment requiring imports. For real downloads, never read large files completely into the heap; stream bounded chunks, handle disconnects, and enforce authorization.

### 11.2. ResponseBodyEmitter and SseEmitter

`ResponseBodyEmitter` can be completed from an event callback; `SseEmitter` sends SSE. They are not equivalent to submitting a `Callable` to an executor. Application code still manages event generation, checking connection state, and cleaning up the emitter.

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter events() {
    SseEmitter emitter = new SseEmitter(30_000L);
    // Register the emitter with an application-managed event source.
    return emitter;
}
~~~

This illustrative fragment **does not form a complete event-emitting service** because it lacks an event source and cleanup. With streaming, writes can block and client disconnects may only be detected on write; add heartbeats for long-lived SSE designs.

### 11.3. Reactive types in Spring MVC

Spring MVC can accept `Mono<T>`, `Flux<T>`, or `CompletionStage<T>` under certain conditions via appropriate adapters. Yet it remains the **Servlet stack**—it does not convert all request/response I/O to non-blocking Reactor Netty like WebFlux. When writing streaming reactive values to the Servlet response, Spring MVC may use the executor for blocking writes.

**Do not mix** Spring MVC `DispatcherServlet` with WebFlux `DispatcherHandler` or bring `WebFluxConfigurer` configuration into an MVC problem merely because the word “async” appears.

## 12. Servlet asyncSupported and Filter dispatchers

MVC async requires the Servlet container to permit asynchronous processing. With **default Spring Boot MVC**, `DispatcherServlet` registration is already configured appropriately.

However, custom Servlet/Filter registrations can break this requirement:

- `ServletRegistrationBean` or `FilterRegistrationBean` has `asyncSupported=false`.
- A filter in the chain forbids async mode.
- A filter mapping covers only `REQUEST` when logic also needs to run on `ASYNC` dispatch.
- A filter assumes each HTTP request traverses the chain only once.

In the Servlet API:

~~~text
DispatcherType.REQUEST  -> initial pass into controller
DispatcherType.ASYNC    -> dispatch pass when async result is ready
~~~

With a custom `FilterRegistrationBean`, you may need `setAsyncSupported(true)` and `DispatcherType.ASYNC` in dispatcher types **when the filter must participate in async dispatches**. If the filter should only handle the initial request, do not blindly enable it for async dispatches and cause double logging, double response wrapping, or duplicate authentication side effects.

Filter registration fragment example:

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST, DispatcherType.ASYNC);
~~~

`registration` is a hypothetical `FilterRegistrationBean<?>`, not a runnable file. When using it, understand filter lifecycles and Spring Security configuration, as some filters manage their own async-dispatch participation.

If you see `IllegalStateException: Async support must be enabled on a servlet and for all filters involved`, inspect **Servlet/Filter registrations** before touching thread pools.

## 13. Context propagation: ThreadLocal does not move automatically to workers

A subtle bug: the initial Servlet thread holds:

- `SecurityContextHolder` with the principal.
- `MDC` with correlation IDs.
- `RequestContextHolder` with request attributes.
- `LocaleContextHolder` with the locale.

When a `Callable` executes on another worker thread, **never assume those `ThreadLocal` values stay intact**. Pools also reuse workers, so improper copying/retention can leak data across requests.

Solutions based on needs:

1. Pass **only the required immutable data** explicitly into the task, such as authenticated user ID, locale, and request correlation ID.
2. When security context is needed, use official wrappers/strategies such as `DelegatingSecurityContextAsyncTaskExecutor` matching Spring Security architecture and ensuring proper lifecycle cleanup.
3. For MDC/tracing/locale, consider Spring `TaskDecorator` and Micrometer Context Propagation with properly registered `ContextSnapshot`/`ThreadLocalAccessor`.
4. A task decorator must capture at **submission time** and reset/restore at **execution time**, preventing thread-local leaks across pooled worker reuse.
5. Async response re-dispatch may run on a Servlet worker different from both the initial thread and the async worker.

Do not pass the raw `HttpServletRequest` or ORM persistence context into a long-lived background task without controlling its lifecycle; the request may already be timed out or completed before the worker accesses it.

## 14. Exceptions, rejections, and timeouts in MVC async

### 14.1. Callable throws an exception

If `Callable#call()` throws an exception, Spring MVC captures it as the async result and resolves it via `@ExceptionHandler`/`@RestControllerAdvice` or another resolver on redispatch. Write tests for business exceptions instead of catching everything and returning 200.

### 14.2. DeferredResult#setErrorResult

With `DeferredResult`, the application can call:

~~~java
deferredResult.setErrorResult(
    new ResponseStatusException(
        HttpStatus.SERVICE_UNAVAILABLE,
        "Downstream unavailable"));
~~~

This is a fragment, not standalone runnable code; MVC processes the exception during async redispatch. Calling `setErrorResult` after the request has already completed does not produce a second response.

### 14.3. Rejection when the queue is full

An executor can throw `TaskRejectedException` when it cannot accept more tasks. With `DeferredResult` and `executor.execute(...)` inside the controller, rejection can occur **at submission time**, before the method returns `DeferredResult`.

- Do not swallow rejections and leave the request hanging indefinitely.
- Map to `503 Service Unavailable` or `429 Too Many Requests` per contract (adding `Retry-After` when appropriate).
- Never return a fake 200 for an unprocessed request.
- Combine with rate limiting, bulkheads, or circuit breakers at the application edge.
- If rejection occurs after the response commits or outside MVC resolvers, handle it appropriately at the source.

### 14.4. Timeout may not cancel the work

A request timeout does not mean a thread interruption was sent to the task. A blocking JDBC call without its own timeout can keep running. Once the response has committed (especially when streaming), you cannot arbitrarily change status or headers.

For sensitive side effects, use idempotency, cancellation, compensating actions, and job state instead of assuming HTTP timeouts roll back transactions.

## 15. Spring MVC async vs. Spring WebFlux

| Aspect | MVC async on Servlet | WebFlux reactive |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Boot default HTTP server | Embedded Tomcat | Reactor Netty |
| Typical APIs | `Callable`, `WebAsyncTask`, `DeferredResult` | `Mono`, `Flux`, reactive chains |
| Underlying protocol | Servlet async dispatch, Servlet output can block | Non-blocking I/O when using a proper reactive runtime |
| Executor for blocking work | `AsyncTaskExecutor` / application-managed pools | Scheduler or `boundedElastic` when blocking is unavoidable |
| Web configuration | `WebMvcConfigurer#configureAsyncSupport` | `WebFluxConfigurer` and reactive configuration |
| Servlet Filters | Yes | No with Reactor Netty; uses `WebFilter` |
| Thread-per-blocking-task | Can occur | Must avoid blocking event loop; offload when needed |

**Do not add the WebFlux starter just to return `Callable` from MVC**. Likewise, returning `Mono` from a Spring MVC controller does not turn the app into a WebFlux server. When both Web and WebFlux starters are present, Spring Boot typically auto-detects **Servlet MVC**.

MVC async helps when keeping an existing Servlet/JDBC/Servlet-security stack while reducing how long **initial request threads** stay occupied. WebFlux fits end-to-end reactive/non-blocking pipelines but requires compatible programming models and dependencies.

## 16. Diagnosing issues and remediation

| Symptom | Common cause | How to investigate |
|---|---|---|
| `Callable` runs on an unexpected thread | Wrong MVC executor bean name or `setTaskExecutor` not called | Check `applicationTaskExecutor` / `WebMvcConfigurer` / thread prefix |
| `@Bean("taskExecutor")` exists but MVC ignores it | Confusing `@Async` with MVC executor | Register `applicationTaskExecutor` of type `AsyncTaskExecutor` |
| `spring.task.execution.pool.*` does not change pool size | Using a custom bean instead of Boot auto-config | Check how the bean is created; tune the bean manually or drop custom bean |
| Pool `max-size` never activates | Unbounded queue | Use a bounded `queue-capacity` and load test |
| HTTP 503 or task rejected | Workers/queue full, shutdown, or slow downstream | Measure active/queued/rejected; boost throughput or shed load |
| HTTP request times out while task keeps running | Async timeout does not cancel blocking calls | Set downstream timeouts and cancellation strategies |
| `DeferredResult` never completes | `setResult`/`setErrorResult` never called, event lost | Add timeout callbacks, cleanup, and observable state |
| `IllegalStateException` async not supported | Custom filter/servlet has `asyncSupported=false` | Check registrations and dispatcher types |
| `SecurityContext`/MDC missing on worker | `ThreadLocal` does not propagate automatically | `TaskDecorator` / security context wrappers / explicit context |
| Request logs appear twice | Initial `REQUEST` + `ASYNC` redispatch | Log with request ID and dispatcher type; avoid duplicate side effects |
| `CompletableFuture` runs on common pool | Calling `supplyAsync` without passing an `Executor` | Pass the appropriate executor |
| Streaming client disconnect not noticed right away | Servlet often detects it on failed write | Heartbeats/cleanup; do not rely on preemptive disconnect detection |
| App added `@EnableWebMvc` and lost Boot defaults | Overrides Boot MVC auto-config | Remove unnecessary annotation; use `WebMvcConfigurer` |
| Test sees an empty response | Forgot `asyncDispatch(result)` in `MockMvc` | Assert `asyncStarted`, wait for result, `asyncDispatch`, then assert |
| Gateway deadline exceeded before MVC timeout | Proxy/client timeout shorter than MVC | Align end-to-end timeout budgets |
| Many async HTTP requests hold connections open | Async frees threads, not sockets/resources | Bound concurrent requests, apply backpressure and timeouts |

## 17. Pre-deployment checklist

- [ ] Confirmed the app uses **Spring MVC Servlet**, not confused with WebFlux.
- [ ] Identified all endpoints returning `Callable`, `WebAsyncTask`, `DeferredResult`, or streams.
- [ ] Confirmed MVC actually uses the intended `AsyncTaskExecutor`, not just any `Executor` bean.
- [ ] If using Boot auto-config, verified `spring.task.execution.pool.*` applies under the current version.
- [ ] If using a custom executor, configured `@Bean("applicationTaskExecutor")` with proper type and lifecycle.
- [ ] Sized core/max/queue with bounds based on load instead of copying demo numbers to production.
- [ ] Configured MVC/per-request timeouts alongside downstream/network/client deadlines.
- [ ] Implemented rejection policies and HTTP error contracts without leaving requests hanging.
- [ ] Avoided treating timeouts as automatic cancellation; added cleanup/interruption/idempotency where needed.
- [ ] Configured Servlet/Filter registrations to support async and `ASYNC` redispatch within proper scope.
- [ ] Implemented context propagation policies for security, tracing, and request-scoped data.
- [ ] Separated the `@Async` executor from MVC async workers; avoided accidental common-pool usage.
- [ ] Exposed metrics for active threads, queued tasks, rejections, timeouts, and p95/p99 latency.
- [ ] Added `MockMvc` tests with `request().asyncStarted()` and `asyncDispatch(result)`.
- [ ] Added HTTP integration/load tests against an embedded servlet server and production-like ingress.
- [ ] Bounded streaming/file-download I/O, disconnect handling, and backpressure.

## Official documentation

- [Spring Framework 6.2 — Asynchronous Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): `Callable`, `WebAsyncTask`, `DeferredResult`, streaming, Servlet async dispatch, timeouts, and configuration.
- [Spring Framework 6.2 — AsyncSupportConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/servlet/config/annotation/AsyncSupportConfigurer.html): `setTaskExecutor`, `setDefaultTimeout`, callable/deferred interceptors.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): `applicationTaskExecutor`, auto-configuration, multiple executors, and `spring.task.execution.mode=force`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.task.execution.*`, `spring.mvc.async.request-timeout`, and `spring.threads.virtual.enabled`.
- [Spring Framework 6.2 — MVC Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html): `WebMvcConfigurer` and Servlet MVC extension points.
- [Spring Framework 6.2 — Spring MVC vs WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/overview.html): Servlet async model versus non-blocking/reactive stack.

**Conclusion:** Configuring `AsyncTaskExecutor` determines **where and how** Spring MVC runs `Callable`/`WebAsyncTask` tasks and supports async writes. Spring Boot 3.5 can auto-configure `applicationTaskExecutor`, or you can declare a bean with the right name/type and use `WebMvcConfigurer#configureAsyncSupport`. `DeferredResult` alone does not spawn executor tasks: the application must supply results from callbacks or its own pools. Bounded pools, end-to-end timeouts, context propagation, rejection handling, and `asyncDispatch` tests make MVC async configuration resilient.