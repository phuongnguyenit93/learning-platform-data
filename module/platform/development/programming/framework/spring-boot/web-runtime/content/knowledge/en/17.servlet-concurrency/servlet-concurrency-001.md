# Servlet Threading Model for Connection Acceptance and Request Processing

## 1. The problem: which threads does an HTTP request pass through?

When deploying Spring Boot running **Spring MVC on a Servlet container**, such as embedded Tomcat, three misconceptions easily arise:

1. “Every TCP connection always owns a dedicated Java thread.”
2. “The thread that accepts the connection is also the thread that runs the controller.”
3. “Simply increasing `server.tomcat.threads.max` will let the server handle unlimited concurrent requests.”

In the **typical Tomcat NIO model**, the connector has distinct responsibilities: **accepting** connections, monitoring **socket readiness**, and **executing request processing**. Those responsibilities are usually handled by different kinds of threads. A keep-alive connection can sit waiting without continuously occupying a Servlet request worker; however, a **synchronous** Servlet controller—if it waits on JDBC, an HTTP client, disk, or `Thread.sleep`—usually holds the request worker for the entire wait duration.

This article explains the concurrency layers from the TCP socket to the Spring MVC handler, clarifies connector limits, how to configure/observe Tomcat, the Servlet asynchronous processing mechanism, and the differences between `Callable`, `DeferredResult`, `@Async`, and Virtual Threads. Runnable Spring Boot 3.5.x / Java 17+ examples and tests are included to illustrate the exact thread handoffs.

**Learning objectives**

- Identify the roles of **acceptor**, **poller/selector**, **request worker/executor**, **application executor**, and **async dispatch**.
- Distinguish between the number of **TCP connections**, **HTTP requests**, **active workers**, **queued tasks**, and **open async requests**.
- Explain blocking vs. non-blocking I/O at two layers: the connector can use NIO while the Servlet controller remains blocking.
- Correctly read `maxConnections`, `acceptCount`, `maxThreads`, `minSpareThreads`, `keepAliveTimeout`, and thread-pool settings.
- Estimate required concurrency using Little's Law and understand limits imposed by CPU, I/O, DB pools, memory, and timeouts.
- See why `Callable` frees the Servlet container worker while the task still needs another executor.
- Test against real runtime behavior rather than inferring only from thread names or MockMvc tests.

**Scope:** The Spring Boot 3.x Servlet stack with Apache Tomcat 10.1 (NIO is the common configuration). Jetty, Undertow, Tomcat NIO2, and virtual-thread executors differ in details; the diagram below must not be applied mechanically to every connector.

## 2. Four concepts that must not be conflated

| Concept | Meaning | Always equal to worker thread count? |
|---|---|---|
| **TCP connection** | A socket between a peer and the server/proxy, which can persist across multiple HTTP requests | No |
| **HTTP request** | A single HTTP exchange: request line/headers/body and the corresponding response | No |
| **In-flight request** | A request that has started but has not yet completed, including waiting async requests | No |
| **Busy request worker** | A thread currently executing request-processing work in the container executor | No |

An HTTP/1.1 keep-alive connection can handle multiple requests **sequentially**. During the idle time between two requests, Tomcat NIO can continue managing the socket with the poller instead of keeping a worker running the controller. HTTP/2 can also multiplex multiple streams over a single connection; do not use the assumption 1 connection = 1 request for capacity planning.

Hypothetical example: 1,000 keep-alive connections are open, but only 20 requests at a given moment are being processed inside blocking controllers. In that case, the connection count can be much higher than the number of busy workers. Conversely, 100 async requests waiting on events from another system do not necessarily need 100 Servlet workers holding CPU continuously, yet they still consume connections, request state, memory, and other resources.

**Key takeaway:** capacity must be evaluated across multiple axes: sockets, workers, queues, database connections, upstream concurrency, memory, and latency.

## 3. The Tomcat NIO model: Acceptor → Poller → Worker

Conceptual diagram for an embedded Tomcat NIO connector:

~~~text
Client / Load balancer
        |
    TCP handshake
        |
Operating-system accept backlog (bounded, OS-dependent)
        |
     Acceptor thread(s)
        | accept socket / register endpoint
        v
    Socket wrapper / NIO channel
        |
   Poller / Selector thread(s)
        | monitor socket readiness
        | hand off socket event to executor
        v
  Container Executor / request worker threads
        |
  Coyote HTTP processor: parse HTTP request
        |
  Servlet Filter chain -> DispatcherServlet
        |
  HandlerMapping -> argument bind/validate
        |
  Spring MVC controller -> service -> DB/HTTP/file
        |
  HttpMessageConverter / view / response write
        |
 Socket keep-alive returns to monitoring / or closes connection
~~~

This is a simplified diagram; it does **not** claim that every byte is read/written on the same poller or a single worker, nor does it detail SSL handshakes, sendfile, asynchronous Servlet I/O, or HTTP/2 streams.

### 3.1. Acceptor — accepts connections, does not run business logic

The acceptor receives new sockets that the operating system allows to be accepted. Its main work involves TCP socket/connector registration; normally it **does not run Spring MVC controllers**, does not open DB transactions, and does not process business JSON.

When the connector's concurrent connection limit is reached, accept/backlog behavior changes. Some connections may wait in the OS queue, time out, or be rejected depending on load and OS policy. There is no rule that “`acceptCount` equals the exact number of requests queued in Spring MVC”: it describes a **connection** backlog level, not a queue of handler tasks.

### 3.2. Poller / Selector — receives readiness signals

The poller monitors many sockets via an NIO selector, detecting when data is available to read or when a socket is ready for the next step. Having a poller does not mean “one thread continuously reading one socket.” This is an advantage of NIO at the **connection layer**: many idle connections can be managed without requiring one blocking Java thread per socket.

NIO at the connector **does not automatically turn blocking JDBC**, `Thread.sleep()`, or a synchronous Spring MVC controller into non-blocking application code. Invoking the Servlet/controller is still typically dispatched to a worker/executor.

### 3.3. Worker / Executor — handles HTTP and invokes the Servlet

When Tomcat has a socket event/request to process, a container executor worker may:
- Parse the request line/headers and manage HTTP protocol state.
- Execute Servlet filters and security filters.
- Invoke `DispatcherServlet`, the controller, services, and synchronous libraries.
- Wait for blocking I/O results if the application uses JDBC or synchronous clients.
- Serialize the response with `HttpMessageConverter`, render a template, or write bytes.
- Finish or transition the socket state to wait for the next request.

A worker is **reused** across different requests. Do not infer that “the same user/session/connection always has the same thread name.” Request-scoped data must not be stored in a mutable field of a singleton bean, nor should thread names be used to identify clients.

### 3.4. Container executor does not mean every executor in Spring

Tomcat has workers/executors serving Servlet dispatches. In addition, an application may have:
- `applicationTaskExecutor` auto-configured by Boot.
- A dedicated `ThreadPoolTaskExecutor` for Spring MVC `Callable`.
- An `@Async` executor for application methods.
- A scheduler for `@Scheduled`.
- Executors for HTTP clients, Kafka listeners, messaging, or background jobs.

These pools can differ in thread count, queue, and lifecycle. Increasing `spring.task.execution.pool.max-size` does not necessarily increase `server.tomcat.threads.max`; increasing Tomcat workers also does not automatically increase the DB connection pool or the MVC async executor.

## 4. Timeline of a synchronous request

Suppose `GET /api/report` includes a blocking JDBC database query step:

~~~text
T0  Acceptor accepts the connection.
T1  Poller detects that the socket has a request/event.
T2  Tomcat worker W1 is dispatched to handle the request.
T3  W1 runs Filter -> DispatcherServlet -> controller.
T4  W1 calls JDBC and WAITS 250 ms.
T5  JDBC returns the result. W1 serializes the DTO and writes the response.
T6  W1 finishes its work and returns to the pool.
T7  The socket is kept alive or closed per protocol/config.
~~~

During T4, **W1 is occupied** even though the CPU may not be busy. This explains why workloads heavy in blocking I/O can exhaust busy workers before CPU reaches 100%.

A worker cannot automatically run another controller while `Thread.sleep`, `ResultSet.next()` is waiting, or `RestTemplate`/a synchronous HTTP client blocks. The NIO connector still manages other sockets, but a synchronously blocking controller needs a worker to make progress.

### 4.1. Theoretical throughput and real limits

By Little's Law in steady state:

[
L = lambda × W
]

Where:
- `L`: number of concurrent requests in a stage/system.
- `λ`: throughput (requests/second) of that stage.
- `W`: average time a request spends in the stage (seconds).

For example, 100 requests/second where each request occupies a worker for an average of 0.2 seconds will require roughly **20 busy workers** just to sustain that load. This is an estimation tool, not a recommendation to set `maxThreads=20` in production: CPU, tail latency, garbage collection, bursts, retries, downstream calls, and queueing all require headroom or reduced worker occupancy time.

You must distinguish **end-to-end response latency** from **worker occupancy time**. With Servlet async, a request may wait for 1 second while the container worker is busy for only a small fraction of that time; `L=λW` using total request `W` must not be used directly to infer the number of busy workers.

## 5. Keep-alive, HTTP/2, and the independence of connections/requests

### 5.1. HTTP/1.1 keep-alive

A connection can stay open after a response completes to serve subsequent requests. While no request is active, an idle socket does not necessarily occupy a request worker. The `keepAliveTimeout` setting determines how long to wait for the next request on a connection before closing it; it is **not** the same as a business timeout or a full controller timeout.

Tomcat also has `maxKeepAliveRequests` — the limit on the number of requests that can be served over a connection before closing it (protocol-dependent). Closing a connection does not mean the controller encountered an exception.

### 5.2. HTTP/2 multiplexing

HTTP/2 carries multiple streams/requests over a single TCP connection. One connection can generate multiple concurrent HTTP processing tasks, subject to server and client HTTP/2 stream/flow-control limits. Do not use `maxConnections` as a limit on “concurrently running requests” for HTTP/2.

### 5.3. Reverse proxies and load balancers

Tomcat may only see connections from Nginx/Ingress/Load Balancer, not directly from end users. Proxies have their own connection pools, keep-alive, buffers, timeouts, and limits. A latency spike can originate in a proxy queue or upstream connection pool even while Tomcat workers remain idle.

When debugging, place metrics at the right layer (edge/proxy, Tomcat socket/worker, Spring request, DB/client) so you do not blame the acceptor when the real bottleneck is in the database.

## 6. Tomcat limits to read line by line

Spring Boot with embedded Tomcat lets you configure many connector properties via `server.tomcat.*`. Example for a **test environment**, not a sizing recommendation for every system:

~~~properties
server.port=8080
server.tomcat.threads.max=24
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=512
server.tomcat.accept-count=64
server.tomcat.keep-alive-timeout=20s
~~~

| Property | Meaning | Do not confuse with |
|---|---|---|
| `server.tomcat.threads.max` | Maximum worker threads in Tomcat's internal pool when using a suitable platform-thread executor | Socket connections or total JVM threads |
| `server.tomcat.threads.min-spare` | Minimum spare worker threads in the internal executor | Acceptors or connections that must always stay active |
| `server.tomcat.max-connections` | Maximum connections the connector can accept and handle concurrently within the limit | Currently executing controllers or queued tasks |
| `server.tomcat.accept-count` | Connection backlog waiting when `maxConnections` is reached, subject to OS limits/adjustments | HTTP requests waiting in a Spring `TaskExecutor` |
| `server.tomcat.keep-alive-timeout` | Time to wait for the next request on an idle connection | Timeout for JDBC, services, or `Callable` |
| `server.tomcat.connection-timeout` | Time to wait for the request line after a connection is accepted, per connector settings | Business operation timeout |
| `spring.task.execution.*` | Spring Boot's task executor configuration under specific auto-configuration conditions | Tomcat acceptor/poller/worker pool |
| `spring.mvc.async.request-timeout` | Default timeout for certain async request processing paths in Spring MVC | Network keep-alive timeout |

**Note:** if the connector is configured to use a shared `Executor` instead of the internal pool, some connector thread properties may be ignored. When Java virtual threads are enabled, request execution and the effect of thread-pool properties also change. Always verify the active configuration using runtime metrics/JMX and logs.

### 6.1. Why does maxConnections not equal maxThreads?

With Tomcat NIO, many connections can stay idle/keep-alive without continuously holding a busy worker. Therefore `maxConnections` can usually be larger than `maxThreads`. However, each connection still consumes a socket/file descriptor, buffers, state, TLS metadata, and overhead. Setting `maxConnections` very high can exhaust OS file descriptors or memory.

### 6.2. acceptCount does not guarantee “requests are never dropped”

The backlog is a queue **waiting to accept/connect** at the TCP/OS layer, not an application request queue. When the backlog is full, clients may hit timeouts or connection refused, depending on kernel and network behavior. The OS may apply limits or interpret the backlog value differently from the configured number. Do not treat `accept-count=1000` as a “safe buffer for 1,000 requests in the controller.”

### 6.3. When maxThreads is reached

Once the worker pool is fully busy, socket processing tasks may queue in the executor or be rejected depending on limits/implementation; request latency rises. The NIO poller does not make CPU-bound/business work free. Meanwhile, upstream layers may continue holding sockets and waiting.

It is essential to measure **busy threads**, **executor queue**, **response time percentiles**, **timeouts/rejections**, and **downstream pool saturation**. Only increase `maxThreads` once you know the bottleneck and have corresponding CPU/memory/DB resources.

## 7. Servlet blocking vs. Tomcat NIO: two different layers

An “NIO connector” does not mean a “fully non-blocking Servlet controller.” Tomcat NIO optimizes I/O at the network layer, especially managing many sockets. However, the synchronous Servlet programming model can still block workers during operations such as:
- Blocking JDBC queries or transactions.
- Synchronous HTTP clients `RestTemplate` / `RestClient`.
- Blocking filesystem I/O.
- `Thread.sleep` or lock contention.
- Large JSON serialization causing CPU load.
- Acquiring a connection from an exhausted pool.

Similarly, “idle CPU” does not prove the server still has throughput. A thread dump may show dozens of `http-nio-*-exec-*` threads waiting on sockets/DB/locks while new requests continue queueing.

### 7.1. Servlet 3.x+ asynchronous processing

The Servlet API supports async mode, allowing a request to **temporarily leave** the filter/Servlet call stack while keeping the response open. Spring MVC integrates with this via `Callable`, `WebAsyncTask`, `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, and streaming/reactive return values.

However, “asynchronous” has multiple meanings:
- **Releasing the Servlet request worker:** the container thread is not held continuously during the wait.
- **Using another application executor:** with `Callable`, the task may still block on another thread.
- **Truly end-to-end non-blocking:** achieved only when I/O libraries and the pipeline are also non-blocking; `Callable` does not turn blocking JDBC into reactive.

Do not assume that changing `String` to `Callable<String>` reduces CPU usage or lowers total thread count. It typically just **moves the wait** from a Tomcat worker to an MVC async worker, freeing space for the container to accept other requests.

## 8. Callable timeline: returning the container worker then async dispatch

~~~text
Client sends GET /demo/callable
    |
Tomcat worker W1
    |
DispatcherServlet -> controller creates Callable
    |
Spring MVC calls startAsync() and submits Callable to AsyncTaskExecutor
    |
W1 leaves the Servlet/filter chain and returns to the Tomcat pool
    |             Response stays open
    |                      |
    |               MVC async worker A1
    |                      | runs Callable / waits for I/O
    |                      | returns result
    |                      v
    +----------- Async dispatch back to container
                           |
                      Tomcat worker W2
                           |
                   DispatcherServlet processes async result
                   Converter writes JSON, completes response
~~~

W1 and W2 **might** happen to be the same thread if the pool reuses it, but there is no guarantee. Do not tie business logic to the assumption “controller entry/exit always runs on the same thread” once async dispatch is involved. `ThreadLocal`, MDC logging, and security context require appropriate propagation mechanisms across executors/frameworks.

### 8.1. Callable vs. DeferredResult

| Mechanism | Who produces the final result | Does it inherently occupy a worker to run the work? |
|---|---|---|
| Synchronous `String` / DTO method | Controller on Tomcat worker | No extra pool needed |
| `Callable<T>` | Callable executed by Spring on `AsyncTaskExecutor` | Yes, the executor executes the Callable |
| `WebAsyncTask<T>` | Callable with per-request timeout/executor configuration | Yes, same as Callable |
| `DeferredResult<T>` | An external source decides when to call `setResult`/`setErrorResult` | Does not inherently require a dedicated thread waiting per request; depends on event source |
| `ResponseBodyEmitter` / `SseEmitter` | Event producer emits multiple chunks/events | Depends on async producer and writer; connection/response remains open |
| `@Async` method | Method runs on the executor configured by `@EnableAsync` | Yes if invoked through a Spring proxy; does not automatically trigger a Servlet async response |

**Specifically:** calling an `@Async` method from a controller and immediately calling `future.get()` on the Tomcat worker still blocks the controller, unless you return an async result recognized and managed by MVC. `@Async` also has proxy/self-invocation caveats.

### 8.2. Async timeout and cancellation

An async request has its own timeout; it is **not** the socket keep-alive timeout. A timeout can trigger an error/dispatch, but you should not assume the thread running a blocking task will stop immediately. If calling JDBC/upstream services, you still need library-specific timeouts, cancellation, and resource cleanup.

When designing with `DeferredResult`, you can register `onTimeout` and `onCompletion`, though callbacks may execute on another thread. A result might arrive after the client disconnects; late completion must be handled idempotently.

## 9. Hands-on example: a Java 17+ Spring Boot project

This project lets you observe two paths:
- `/demo/thread`: a synchronous controller running on a Tomcat worker.
- `/demo/blocking`: the worker is held for 300 ms by `Thread.sleep` (for demo purposes only).
- `/demo/callable`: the controller creates the `Callable` on a Tomcat worker, while the Callable executes on a pool prefixed `mvc-async-`.
- A `OncePerRequestFilter` logs the thread name on the initial dispatch, making the filter/container boundary visible.

**Do not use `Thread.sleep` in production request handlers** as a waiting mechanism. It is used here only to create a measurable blocking workload without external DB dependencies.

### 9.1. Maven project

`pom.xml`:

~~~xml
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
    <groupId>example</groupId>
    <artifactId>servlet-threads-demo</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Only `spring-boot-starter-web` is declared because this is a Servlet MVC application. Do not infer a reactive runtime just because another project has a `WebClient` dependency.

`src/main/resources/application.properties` (these values are for local experimentation):

~~~properties
server.port=8080
server.tomcat.threads.max=24
server.tomcat.threads.min-spare=4
server.tomcat.max-connections=512
server.tomcat.accept-count=64
management.endpoints.web.exposure.include=health,metrics
~~~

**Safety:** Actuator metrics can expose operational information. Do not expose them publicly in production; protect endpoints with security/network policy. The Tomcat limits above are test-environment settings, not optimal values to copy into production without benchmarking.

### 9.2. Standalone Java source

Create `src/main/java/example/threads/ServletThreadsApplication.java`:

~~~java
package example.threads;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.MediaType;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class ServletThreadsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletThreadsApplication.class, args);
    }

    @Bean("mvcAsyncExecutor")
    ThreadPoolTaskExecutor mvcAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("mvc-async-");
        // Spring manages the lifecycle and initializes the executor via the bean lifecycle.
        return executor;
    }

    @Bean
    WebMvcConfigurer asyncMvcConfigurer(
            @Qualifier("mvcAsyncExecutor")
            ThreadPoolTaskExecutor executor) {

        return new WebMvcConfigurer() {
            @Override
            public void configureAsyncSupport(AsyncSupportConfigurer config) {
                config.setTaskExecutor(executor);
                config.setDefaultTimeout(5000);
            }
        };
    }
}

@RestController
@RequestMapping("/demo")
class ThreadDemoController {

    @GetMapping(path = "/thread",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> thread() {
        return Map.of(
                "mode", "sync",
                "requestThread", Thread.currentThread().getName());
    }

    @GetMapping(path = "/blocking",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Map<String, String> blocking() throws InterruptedException {
        String before = Thread.currentThread().getName();
        Thread.sleep(300);
        return Map.of(
                "mode", "blocking",
                "threadBefore", before,
                "threadAfter", Thread.currentThread().getName());
    }

    @GetMapping(path = "/callable",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Callable<Map<String, String>> callable() {

        String entryThread = Thread.currentThread().getName();

        return () -> {
            Thread.sleep(300);
            return Map.of(
                    "mode", "callable",
                    "entryThread", entryThread,
                    "taskThread", Thread.currentThread().getName());
        };
    }
}

@Component
class RequestThreadFilter extends OncePerRequestFilter {

    private static final Logger LOG =
            LoggerFactory.getLogger(RequestThreadFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        String entry = Thread.currentThread().getName();
        LOG.info("begin uri={} dispatch={} thread={}",
                request.getRequestURI(), request.getDispatcherType(), entry);

        try {
            chain.doFilter(request, response);
        } finally {
            LOG.info("end uri={} asyncStarted={} thread={}",
                    request.getRequestURI(), request.isAsyncStarted(),
                    Thread.currentThread().getName());
        }
    }
}
~~~

The code has one `public class` matching the filename and package-private types in the same `example.threads` package, all scanned by `@SpringBootApplication`. `@EnableAsync` is not required for the `Callable` example because Spring MVC has its own async request support.

`RequestThreadFilter` extends `OncePerRequestFilter`. By default it may skip async redispatches, so do **not** treat a single filter log as proof that the HTTP request finished at that log entry. After the controller returns `Callable`, the initial dispatch's filter chain may exit with `asyncStarted=true`, while the response remains open for the async result.

Unused imports can be removed, such as `org.springframework.core.task.TaskExecutor`; the Java compiler does not treat unused imports as errors. If strict checkstyle is enabled, remove extra imports.

### 9.3. Run and inspect output

Requires JDK 17+, Maven, and port 8080 free:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/demo/thread
curl -s http://localhost:8080/demo/blocking
curl -s http://localhost:8080/demo/callable
~~~

Example output **shape**, without guaranteeing thread numbering:

~~~json
{"mode":"sync","requestThread":"http-nio-8080-exec-1"}
~~~

~~~json
{"mode":"blocking","threadBefore":"http-nio-8080-exec-2","threadAfter":"http-nio-8080-exec-2"}
~~~

~~~json
{"mode":"callable","entryThread":"http-nio-8080-exec-3","taskThread":"mvc-async-1"}
~~~

Actual output may use different `http-nio-8080-exec-X` names depending on the connector, prior requests, and Tomcat version. For the synchronous blocking method, code before/after `Thread.sleep` runs within a single invocation and thus on the same thread. For `Callable`, `entryThread` and `taskThread` belong to two different executors as configured in the demo; the async response is also dispatched back to a container worker for serialization, though the returned JSON only contains thread names at the two measured points.

Do not claim from this output that Tomcat has only three threads or that every HTTP connection is pinned to one thread. These are simply three independent requests observed at specific moments.

## 10. Testing within MockMvc's proper scope

Add `src/test/java/example/threads/ServletThreadsApplicationTests.java`:

~~~java
package example.threads;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ServletThreadsApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousControllerReturnsThreadInformation() throws Exception {
        mvc.perform(get("/demo/thread"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("sync"))
                .andExpect(jsonPath("$.requestThread").isNotEmpty());
    }

    @Test
    void blockingControllerUsesOneThreadWithinInvocation()
            throws Exception {

        mvc.perform(get("/demo/blocking"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("blocking"));
    }

    @Test
    void callableStartsAsyncAndUsesConfiguredTaskExecutor()
            throws Exception {

        MvcResult initial = mvc.perform(get("/demo/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(initial))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.mode").value("callable"))
                .andExpect(jsonPath("$.taskThread").isNotEmpty());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Note on what the test proves:** `MockMvc` does not run a real Tomcat connector, so the initial request thread in the test may be the test runner thread (e.g. `main`), not necessarily named `http-nio-...`. The test only verifies MVC async handling, the HTTP result, and the configured executor. To verify actual acceptor/poller/worker behavior, run the embedded application and inspect thread dumps/JMX/metrics—do not use MockMvc as evidence of socket architecture.

## 11. When to switch from synchronous to asynchronous?

### 11.1. Long-waiting, low-CPU workloads

If a request must wait for an event/message or an upstream async API, `DeferredResult` or an asynchronous return value can avoid holding a container worker for the whole wait duration. However, you need timeouts, completion/cancellation handling, limits on open requests, and a backpressure policy.

### 11.2. JDBC or HTTP client is still blocking

Moving that work to `Callable` returns the Tomcat worker to the pool, yet an MVC async worker is still held during the block. If the DB connection pool has only 10 connections, creating 500 async workers does **not** help the DB process 500 queries usefully in parallel; it just queues at another layer.

When using `Callable`, choose an executor whose worker count and queue match downstream capacity; do not use unbounded threads/queues to hide latency. An overly long queue causes request timeouts and accumulates memory.

### 11.3. CPU-intensive handlers

Offloading CPU-heavy tasks to an async executor does not reduce total CPU work. On the same machine, too many threads can cause context switching and worsen tail latency. Optimize algorithms, add caching or precomputation, or split out a worker service if appropriate.

### 11.4. Streaming/SSE

SSE keeps connections open for a long time; Servlet async can avoid holding a worker while **no events are sent**, but the response/socket stays open, requiring timeouts/heartbeats, disconnect cleanup, and stream-client limits. Writing data may still require a worker in Servlet MVC; it does not mean non-blocking WebFlux.

## 12. Distinguishing @Async from MVC asynchronous processing

`@Async` belongs to Spring task execution: when enabled with `@EnableAsync` and invoked through a Spring proxy, work can run on an executor. It does not automatically start `HttpServletRequest.startAsync()` and does not change the HTTP contract if the controller still waits for the result.

Illustrative anti-pattern (fragment):

~~~java
@GetMapping("/bad")
String bad() throws Exception {
    Future<String> future = asyncService.fetch();
    return future.get(); // Tomcat worker still BLOCKS here
}
~~~

Contrast this with:

~~~java
@GetMapping("/callable")
Callable<String> good() {
    return () -> blockingService.fetch();
}
~~~

In the second example, Spring MVC can call `startAsync()` and run the Callable on another executor. `blockingService.fetch()` still blocks that executor's thread, but it does not hold the original Servlet worker. An even better option is true asynchronous I/O if the client and business API support it, though you should not switch frameworks just to fix one endpoint without measuring the bottleneck first.

**When a service returns `CompletableFuture`** and Spring MVC handles it as an async return value, you also need to test timeouts/errors/cancellation and which executor is actually used. Do not assume that having `CompletableFuture` anywhere makes the request asynchronous.

## 13. Virtual threads: another option in Java 21+

The runnable example in section 9 uses Java 17 and **platform threads**. With **Java 21+**, Spring Boot 3.5 supports virtual threads:

~~~properties
spring.threads.virtual.enabled=true
~~~

When enabled under proper Java/runtime conditions, much blocking-style work can run on virtual threads scheduled by the JVM onto carrier platform threads, reducing the cost of holding one platform thread per waiting task. However:

- Virtual threads do not make CPU-intensive work faster; CPU cores are still required.
- They do not solve DB pool limits, remote API rate limits, socket/file handles, or memory limits.
- Certain blocking operations/pinning situations can affect throughput; measure with real workloads.
- Properties such as `server.tomcat.threads.max`/`min-spare` meant for platform-worker pools may no longer apply under Boot's virtual-thread configuration.
- Do not infer that Tomcat's acceptor/poller disappear or that all framework executors use virtual threads in the same way.
- Use JDK Flight Recorder or appropriate JDK diagnostics to locate pinned virtual threads and bottlenecks.

**Do not** enable `spring.threads.virtual.enabled=true` on Java 17 and claim the experiment is running on virtual threads. Java 21+ is a prerequisite. If the project targets Java 17, keep the platform-thread setup in the main demo so results are reproducible.

## 14. Practical observability: logs, Actuator, thread dumps, JMX

### 14.1. Stage-by-stage logs

To understand a request:
1. Log request ID, route, and method at filter entry.
2. Log `Thread.currentThread().getName()` at controller entry.
3. When using a Callable, log the thread inside the Callable and track async completion.
4. Log worker occupancy time, total request latency, and downstream wait time.
5. Never store request-specific mutable state in singleton bean fields.
6. With MDC/`ThreadLocal`, implement propagation and cleanup across executor switches; request threads may be reused for other clients.

Do not log cookies, Authorization tokens, or full request bodies containing PII. A thread name is only a debugging signal, not user identity.

### 14.2. Actuator metrics

If the project includes `spring-boot-starter-actuator` with appropriate exposure enabled:

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

The list shows which metric names are actually registered. Depending on version/connector/config, you may see metrics related to:
- Tomcat busy/current threads.
- Current/keep-alive connections.
- HTTP server requests/observations.
- JVM threads, CPU, memory, garbage collection.
- Application task executor active/pool/queue (if instrumented).

Never hardcode a metric name purely by guessing. List `/actuator/metrics`, then query the names that appear. Some Tomcat-specific metrics require the connector JMX MBean registry or an appropriate binder to be enabled. **Do not expose** Actuator metrics, `/actuator/env`, or `/actuator/beans` broadly on the Internet.

### 14.3. Thread dumps

Using the JDK:

~~~bash
jcmd <PID> Thread.print
~~~

`<PID>` is a syntax placeholder; replace it with the actual PID of the Java process when running. In the thread dump, categorize:
- Acceptor/poller threads: typically waiting on sockets/readiness.
- `http-nio-...-exec-...` or equivalent worker threads: are they blocked on DB/sockets/locks or running controllers?
- `mvc-async-...`: are they executing Callables or is the queue full?
- GC, scheduler, background, HTTP client workers: distinguish them from Servlet workers.

Do not count every `Thread.State.WAITING` as a “thread deadlock.” Pollers, idle executors, and schedulers normally wait legitimately. A deadlock requires a lock cycle or concrete evidence in the dump.

### 14.4. JMX and connection pools

JMX/Tomcat MBeans can expose executor/connector metrics, including busy threads and connections. Also monitor HikariCP active/idle/pending if using JDBC, because 50 Tomcat workers hitting a 10-connection DB pool can leave 40 workers waiting on the pool, growing request queues while CPU stays low.

Record:
- Request rate, average/p95/p99 response latency.
- Tomcat busy/current threads, connection utilization, and queue/rejections.
- Async executor active/core/max/queue, timeout/rejection counts.
- DB pool active/pending, SQL latency, and slow queries.
- Upstream client pool saturation, retries, and timeouts.
- CPU, heap/native memory, file descriptors, and GC pauses.

## 15. Bottleneck symptoms and remediation decisions

| Symptom | Hypothesis | Investigate before increasing threads |
|---|---|---|
| Low CPU, high p99 latency, Tomcat busy threads near max | Workers are blocking | Thread dumps, DB/client timeouts, locks |
| CPU near 100%, high runnable threads | CPU bottleneck | CPU profiling, GC, algorithms, and oversubscription |
| High Tomcat connections but low busy workers | Keep-alive/idle sockets or async waits | Connection timeouts, proxy pools, FDs/memory |
| 503/timeouts at proxy while Tomcat CPU is low | Queue/connection limits or proxy routing | Backlog, `maxConnections`, proxy queues, network |
| Rising async timeouts, Tomcat workers not busy | MVC async executor or remote events too slow | Async pool active/queue, timeouts, upstream |
| High Hikari pending | DB pool/SQL bottleneck | DB query plans, pool sizing, transaction duration |
| Task executor queue growing persistently | Processing capacity below arrival rate | Queue limits, rejection policy, backpressure |
| Unbounded thread count growth | New pools/unbounded tasks/threads | Thread dumps, executor beans, lifecycle |
| Clients see incomplete responses | Disconnect/stream write errors | Connection lifecycle, response committed state, and logs |

**Do not simultaneously raise** `maxThreads`, `maxConnections`, `acceptCount`, and the DB pool to huge values without experimentation. Change one variable at a time, keep the traffic profile constant, and watch throughput/p95/p99, errors, queues, and resource saturation.

## 16. Minimal benchmarking and capacity-planning workflow

1. **Choose the workload:** e.g. 90% light GETs, 10% blocking I/O, or a mix reflecting production.
2. **Measure the baseline:** request rate, p50/p95/p99, busy workers, connections, DB pool, and CPU.
3. **Increase concurrency in steps:** keep server and test data stable; do not burst straight into production.
4. **Find the knee/inflection point:** throughput stops rising while latency/errors/queues grow.
5. **Capture thread dumps at the bottleneck:** which threads block, on which driver/API/lock?
6. **Change one hypothesis:** optimize SQL, reduce remote latency, configure async, bound queues, or tune worker count reasonably.
7. **Re-run the same workload:** compare percentiles and failure rates, not just requests/sec.
8. **Verify shutdown/cancellation:** check whether tasks and async responses time out and executors clean up.

A sync request waiting 200 ms and an async request waiting 200 ms may have **similar end-to-end latency** under low load. The difference is worker occupancy and capacity to absorb load when many requests wait. To prove a benefit, measure under appropriate concurrency rather than sending a single `curl` request.

### 16.1. Queueing is not a way to increase throughput

A system that processes 100 requests/second while continuously receiving 150 requests/second will accumulate an ever-growing backlog unless there is admission control, backpressure, load shedding, or capacity scaling. Increasing the queue only delays errors and adds latency; it does not physically make the server process faster.

Designs may need:
- Pool sizes suited to the workload.
- Bounded queues and clear rejection policies.
- Rate limiting/concurrency limits at the edge.
- Timeouts and circuit breakers for downstream calls.
- Appropriate async I/O, critical-path optimization, or scaling out.

## 17. How does Spring MVC Servlet differ from Spring WebFlux?

| Aspect | Spring MVC on Tomcat Servlet | Spring WebFlux on Reactor Netty |
|---|---|---|
| Primary controller contract | Servlet request/response, typically synchronous; supports async return types | Reactive publishers and non-blocking APIs |
| Container | Tomcat/Jetty/Undertow Servlet | Reactor Netty or another reactive runtime |
| Reading/writing HTTP requests | Servlet API; NIO at connector, but application I/O can block | Reactive HTTP codecs and event-loop model |
| Blocking service calls | Typically occupy a Servlet worker; `Callable` shifts block to another pool | Must not block the event loop; blocking libraries must be isolated |
| Waiting on idle keep-alive connections | NIO socket management, does not necessarily hold a request worker | Event loop manages many sockets |
| Async request lifecycle | Servlet async start, task executor, ASYNC redispatch | Async is an inherent part of the reactive pipeline |
| Resources to measure | Workers, connections, queues, DB/client pools | Event-loop latency, blocking tasks, scheduler pools, connections |

**Do not confuse Tomcat's NIO connector with the WebFlux event-loop architecture.** Both leverage non-blocking network I/O to some degree, yet their application contracts and ways of handling blocking work differ.

A Spring Boot application containing both `spring-boot-starter-web` and `spring-boot-starter-webflux` usually selects the MVC server by default; having `WebClient` on the classpath does not prove controller requests run on a Reactor Netty event loop.

## 18. Common mistakes to avoid

1. **One connection = one worker thread:** false under NIO keep-alive, especially HTTP/2.
2. **One request always stays on one thread start to finish:** false with Servlet async/redispatch.
3. **Acceptor/poller runs Spring controllers:** incorrect for standard Tomcat NIO architecture.
4. **NIO connector means JDBC doesn't block:** false; application code can still block.
5. **maxThreads = maxConnections:** two different quantities serving different limits.
6. **acceptCount is the number of requests in the Spring queue:** it is the TCP connection backlog, influenced by the OS.
7. **Increasing maxThreads fixes all 503 errors:** DB pool, CPU, network, proxies, and memory also matter.
8. **JVM thread count equals concurrent HTTP requests:** there are also acceptors, pollers, schedulers, clients, and GC.
9. **Holding ThreadLocal state across async calls without propagation:** easily loses context or leaks data across requests.
10. **Believing Callable runs non-blocking:** a Callable can block on the secondary executor.
11. **`@Async` method plus `Future.get()` still frees the Tomcat worker:** `get()` still blocks.
12. **`DeferredResult` spawns a sleeping thread per request to wait:** results typically come from external events; no dedicated thread is needed per idle request.
13. **A single filter “end” log means the response is finished:** false when `request.isAsyncStarted()` is true.
14. **`MockMvc` returns thread name `main`, so Tomcat has no workers:** MockMvc does not run a real connector.
15. **Growing an unbounded queue to avoid rejections:** latency and resources can balloon until timeouts hit.
16. **Virtual threads make CPU tasks faster:** not guaranteed, and downstream limits still apply.
17. **Enabling virtual threads on Java 17:** requires Java 21+.
18. **Measuring average latency while ignoring p99:** tail latency and queues surface problems much earlier.
19. **Assuming a single `curl` request measures concurrency capacity:** requires a controlled load test.
20. **Forgetting to secure Actuator:** metrics/beans/env endpoints can expose infrastructure details.

## 19. Checklist before deployment or tuning

- [ ] Confirmed the active Servlet web stack, container, and connector implementation.
- [ ] Mapped the path acceptor → poller → container worker → Filter/DispatcherServlet/controller.
- [ ] Separated connection counts, in-flight requests, busy workers, and async tasks.
- [ ] Accounted for keep-alive and HTTP/2 instead of assuming a 1:1 connection-to-request ratio.
- [ ] Evaluated `maxThreads`, `maxConnections`, and `acceptCount` alongside OS limits.
- [ ] Measured blocking time in JDBC, outbound HTTP, disk, locks, and JSON serialization.
- [ ] Distinguished Tomcat executor, MVC async executor, `@Async`, and schedulers.
- [ ] If using `Callable`/`DeferredResult`, configured timeouts, bounded executors/queues, and cancellation cleanup.
- [ ] Not expecting `@Async` with `Future.get()` to make a servlet request non-blocking.
- [ ] Have protected logs/request IDs, thread dumps, and Actuator/JMX metrics.
- [ ] Have load tests identifying saturation rather than relying only on defaults.
- [ ] Checked DB pool, connection pools, CPU, and memory before increasing worker threads.
- [ ] If using Java 21 virtual threads, measured pinning and noted thread-pool settings may be ignored.
- [ ] Tested the same workload before/after tuning, checking p95/p99 and error rate.
- [ ] Did not blindly copy experimental values from this article into production.

## 20. Conclusion

The Servlet concurrency model with Tomcat NIO must be understood as **three distinct duties**: acceptors accept connections, pollers monitor socket readiness, and workers/executors execute HTTP requests and Spring MVC controllers. Many connections can sit idle without occupying workers, whereas a blocking controller still holds a worker while waiting. `Callable`/`DeferredResult` allow a Servlet request to enter an async lifecycle and release the initial worker; that alone does not make downstream blocking non-blocking or CPU free. Limits for `maxConnections`, `acceptCount`, `maxThreads`, async executors, DB pools, and resource budgets must be evaluated independently. Sound design begins by measuring request timelines, worker occupancy, queues, and latency under real load.

## References

- Apache Tomcat 10.1 — HTTP Connector (NIO, threads, connections, accept backlog): https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Spring Boot 3.5 — Common Application Properties (Tomcat thread/connectors): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework — MVC Asynchronous Requests (Callable/DeferredResult/ASYNC dispatch): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.5 — Task Execution and Scheduling (applicationTaskExecutor): https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 — Virtual Threads and SpringApplication: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Jakarta Servlet 6.0 — Specification: https://jakarta.ee/specifications/servlet/6.0/
