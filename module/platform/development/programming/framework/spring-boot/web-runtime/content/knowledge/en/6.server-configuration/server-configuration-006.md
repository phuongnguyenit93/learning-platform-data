# Connection Limits, Wait Queues, and Concurrent Request Limits

In a Spring Boot application running on the **Servlet web stack** with embedded Tomcat, three easily confused concepts are **concurrent connections**, **connection wait queues**, and **concurrently executing HTTP requests**. They are related but are not the same metric. Setting `server.tomcat.max-connections=1000` does not mean the application processes 1,000 business requests simultaneously; setting `server.tomcat.threads.max=200` also does not mean only 200 TCP sockets can exist.

As traffic grows, requests can wait in many places: browsers and reverse proxies, the operating system's connection backlog, Tomcat's connector, the request-processing executor, the database connection pool, or queues in downstream services. To configure properly, you need to know which layer a limit affects and measure the actual bottleneck.

This lesson focuses on Spring Boot 3.3.x, Tomcat NIO on the Servlet stack, and Java 21. The default values below are from **Spring Boot 3.3.x** under typical configuration, not optimal configuration recommendations for every system. For Jetty, Undertow, Reactor Netty, external Servlet containers, or custom Executors, check their specific mechanisms and properties.

## 1. Distinguishing the Types of Limits

| Concept | What It Represents | Example | Key Point to Remember |
| --- | --- | --- | --- |
| **Open TCP connections** | Network connections from clients/proxies to the server | 100 open keep-alive sockets | A connection can be idle with no request running |
| **Accepted connections** | Connections accepted and managed by the connector | Tomcat's `maxConnections` | Not the number of requests executing inside controllers |
| **Listen/accept backlog** | New connections waiting at the socket/OS when the server cannot accept more yet | `acceptCount` | A **connection** queue, not a business task queue |
| **Request processing threads** | Threads currently processing or available to process synchronous requests | `maxThreads` / `server.tomcat.threads.max` | For blocking requests, a thread is occupied for the processing duration |
| **Executor task queue** | Work handed to the executor but not yet picked up by a worker | `server.tomcat.threads.max-queue-capacity` in supported configurations | Differs from OS listen backlog; exact semantics depend on the executor |
| **In-flight HTTP requests** | Requests that have entered the system and have not yet completed | 120 requests waiting/being processed | Can exceed worker thread count with async/HTTP/2 |
| **Downstream pool capacity** | Capacity to use connections to databases, HTTP clients, or other systems | HikariCP maximumPoolSize=20 | Can be the bottleneck even when Tomcat still has free threads |

For example, Tomcat accepts 300 HTTP keep-alive connections while only 12 requests are concurrent. When requests use HTTP/1.1 sequentially over open connections, many connections occupy zero threads while waiting for the next request. Conversely, HTTP/2 allows multiple streams/requests on one connection, so active requests can outnumber connections.

**Do not use the terms connection, request, thread, and queue interchangeably** when designing limits or observing production.

## 2. Which Layers Does a Request Traverse Under Load?

~~~text
HTTP client / load generator
          |
          v
DNS / network / load balancer / API gateway
          |
          v
Tomcat listening socket
          |
          +--> OS connection backlog (acceptCount: requested size)
          |
          v
Tomcat Connector (accepted sockets <= maxConnections, per connector mechanics)
          |
          +--> I/O poller, keep-alive, parser
          |
          +--> Tomcat executor / worker threads
          |       +--> runnable task queue (if executor has a queue)
          |       +--> Servlet Filter processing
          |       +--> DispatcherServlet / Controller
          |
          v
Service / transaction / database pool / HTTP client pool
          |
          v
Database / remote API
          |
          v
HTTP response -> client
~~~

This diagram outlines potential waiting points, not an immutable internal order for all Tomcat connectors and executors. Tomcat NIO, shared executor setups, virtual threads, and async requests can change how resources are used.

When the server is busy, different situations can occur:

1. **Connection slots available but workers exhausted:** Tomcat can hold additional connections and queued work, causing latency to rise.
2. **maxConnections reached:** new connections can wait in the OS listen backlog; once the backlog overflows, clients may see timeouts or connection errors.
3. **Workers available but database pool exhausted:** requests are still received, but threads stall waiting for a JDBC connection.
4. **Gateway times out before backend:** clients see 502/504 or timeouts even if the server has not responded yet.
5. **A request performs async work:** in-flight request count and active worker count can differ substantially.

The goal of capacity planning is not merely making the system "accept many sockets", but maintaining throughput, latency, and error rates within resource bounds.

## 3. Key Properties of Spring Boot 3.3 + Tomcat

| Spring Boot Property | Spring Boot 3.3.x Default | Primary Meaning |
| --- | ---: | --- |
| `server.tomcat.threads.max` | `200` | Maximum Tomcat worker threads under the standard platform-thread model |
| `server.tomcat.threads.min-spare` | `10` | Minimum number of worker threads maintained |
| `server.tomcat.max-connections` | `8192` | Limit on connections accepted and handled concurrently by the connector |
| `server.tomcat.accept-count` | `100` | Desired OS listen backlog size when no more connections can be accepted |
| `server.tomcat.threads.max-queue-capacity` | `2147483647` | Executor runnable-task queue limit in supported setups; effective only when configured > 0 |
| `server.tomcat.connection-timeout` | Depends on effective connector setting | Time to wait for the request line after accepting a connection |
| `server.tomcat.keep-alive-timeout` | If unset, uses connection timeout | Time to wait for the next HTTP request on a keep-alive connection |
| `server.tomcat.max-keep-alive-requests` | `100` | Maximum requests on a keep-alive connection before closing per connector settings |

Reference sources: Spring Boot 3.3 Common Application Properties and Apache Tomcat 10.1 HTTP Connector Configuration (linked at the end). **Default** values can be overridden by profiles, environment variables, command-line arguments, factory customizations, and application settings.

Three primary limits to remember:

- `threads.max`: the server's worker-thread capacity for synchronous request processing.
- `max-connections`: the number of connections Tomcat accepts and manages, including idle/keep-alive connections.
- `accept-count`: the socket/OS connection wait queue size when the connector reaches a state where it cannot accept additional connections.

**Note:** Spring Boot documentation describes accept-count in terms of running out of request-processing threads, whereas Tomcat Connector documentation specifies listen backlog when `maxConnections` is reached. In operations, rely on the concrete connector/OS semantics and verify empirically; do not treat accept-count as "requests queued behind maxThreads".

## 4. `server.tomcat.threads.max`: Limiting Worker Threads

With typical synchronous Spring MVC handling, Tomcat assigns a worker thread to execute the Servlet Filter chain, DispatcherServlet, controller, and services. When a controller performs blocking JDBC, blocking remote HTTP client calls, `Thread.sleep`, or blocking file I/O, the worker can remain occupied while waiting.

~~~text
maxThreads = 8
All 8 worker threads are busy handling slow requests
            |
New request arrives
            |
No free worker available at that moment
            |
Waits / enters the connector-executor dispatch mechanism
            |
Worker frees up -> continues processing
~~~

`threads.max=8` typically limits the processing threads of the internal executor; it does not mean "only 8 clients can connect". Accepted connections are still governed by `max-connections` and NIO mechanics.

Cases to review `threads.max`:

- `tomcat.threads.busy` frequently sits near its maximum while CPU, GC, and downstream services still have headroom.
- Latency rises sharply as concurrent requests increase.
- Thread dumps show many workers held by JDBC, socket reads, or locks.
- Active threads, busy threads, and actual latency indicate workers are the bottleneck.

However, **increasing threads.max does not necessarily increase throughput**. If the database pool has only 20 connections and every request needs the database, raising workers from 100 to 500 can create 400 additional waiting threads, increasing memory use, context switching, and p99 latency.

### 4.1. min-spare Differs from max

`server.tomcat.threads.min-spare` is the minimum number of worker threads Tomcat keeps around, not a minimum concurrency guarantee or threads reserved for a single endpoint. The thread pool can grow toward `threads.max` as needed. Avoid raising min-spare near max just to "keep lots of threads ready", because threads also consume resources.

### 4.2. Shared Executors and Virtual Threads

If the connector is configured to use an external or shared `Executor`, the internal `maxThreads` property may be ignored; inspect the limit on the actual executor.

In Spring Boot 3.3 on Java 21, when `spring.threads.virtual.enabled=true` is enabled, `server.tomcat.threads.max` and `min-spare` **no longer govern request workers in the same way**. Virtual threads change how threads are used, but they do not create infinite CPU, database connections, RAM, or downstream capacity. To limit concurrent business requests, you may need separate semaphores, bulkheads, or rate limits.

## 5. `server.tomcat.max-connections`: Limiting Concurrent Connections

Tomcat NIO can manage many HTTP connections using a smaller set of worker threads. A connection may be:

- Sending or receiving a request.
- Sitting in keep-alive state waiting for the next request.
- Using HTTP/2 with multiple request streams.
- Waiting on socket events, timeouts, or responses.

`maxConnections=8192` in the Boot 3.3 default means the connector can accept and manage connections up to that limit according to Tomcat's mechanism. It **does not guarantee processing 8,192 business requests simultaneously**, nor does it mean a throughput of 8,192 requests/second.

Example:

~~~text
maxConnections = 1000
maxThreads     = 80

750 HTTP keep-alive connections open, mostly idle
35 synchronous requests actively executing

=> The connector still holds many open connections,
   while busy worker threads are only around 35.
~~~

Conversely, HTTP/2 can make a single connection carry multiple request streams. Therefore, do not deduce concurrent requests from socket count using a fixed "1 connection = 1 request" calculation.

Connection limits are affected by open file descriptors, socket buffers, kernel TCP settings, reverse proxy connection pooling, instance count, TLS, connector version, and client traffic patterns.

Do not set `max-connections` overly high just to accept more clients. If downstream systems cannot bear the load and workers are exhausted, excess connections turn into backlogs and queues that stretch wait times.

## 6. `server.tomcat.accept-count`: Listen Backlog, Not a Business Queue

The operating system provides a queue for connections waiting to be accepted by the application from a listening socket. Tomcat uses `acceptCount` to request the backlog size when the connector has reached its connection acceptance limit; the OS may adjust or not strictly obey the exact value.

Illustration:

~~~text
TCP connections arrive faster than they can be accepted
            |
            +--> Tomcat is already holding maxConnections connections
            |
            +--> OS listen backlog (acceptCount)
            |
            +--> Backlog full
                      |
                      +--> Client connect timeout
                      +--> Connection refused / reset depending on OS/network
~~~

Do not interpret `accept-count=100` as "100 requests stored in a queue behind 200 worker threads" or "100 requests guaranteed to complete". The listen backlog holds **pending connections**, subject to OS, network, and handshake behavior.

Key points:

1. The backlog is a listening-socket parameter, not a Java collection inside a controller.
2. The kernel may cap the effective size via OS settings.
3. A load balancer or reverse proxy may have its own queue before requests reach Tomcat.
4. Increasing the backlog can reduce connection failures during short bursts, but if the server remains slow over a long period, a large backlog only makes requests wait longer.
5. Overload symptoms may be client connection timeouts or refused connections; **not necessarily** HTTP 503/429 from the application.

## 7. Executor Queue Differs from OS Queue

Spring Boot 3.3 documentation includes `server.tomcat.threads.max-queue-capacity` for the thread pool's task queue. Tomcat has `maxQueueSize` for runnable tasks waiting for an executor worker. This is a queue at the **Java executor** layer, distinct from the listening socket's `acceptCount`.

| Queue | Unit Typically Waiting | Corresponding Property | Where It Lives |
| --- | --- | --- | --- |
| **OS listen backlog** | TCP connection waiting to be accepted | `server.tomcat.accept-count` | Kernel/socket |
| **Tomcat executor queue** | Runnable task waiting for a worker | `server.tomcat.threads.max-queue-capacity`, in supported cases | Executor |
| **Database connection wait queue** | Thread/task waiting to acquire a DB connection | HikariCP timeout and pool settings | Application/DataSource |
| **Gateway / load balancer queue** | HTTP request not yet forwarded to backend | Depends on gateway/proxy | Infrastructure outside JVM |
| **Business job queue** | Work to execute asynchronously | Kafka/RabbitMQ/internal queue, if designed | Business layer |

You cannot use a single `accept-count` number to describe total queueing time. A single request can wait in several different queues along its journey.

In Spring Boot 3.3, `threads.max-queue-capacity` takes effect only when the value is greater than 0 and depending on the executor implementation. If the connector uses a custom Executor or virtual threads, verify the actual behavior. Do not set a small number assuming every request above the limit will receive HTTP 429; failures can occur at the network, executor, or gateway layer.

When deciding queue limits, weigh the maximum acceptable wait time. Long queues inflate tail latency even when throughput does not improve.

## 8. Concurrency Depends on Protocol and Processing Model

### 8.1. HTTP/1.1 and Keep-Alive

HTTP/1.1 can reuse one TCP connection for multiple HTTP requests. Between active requests, a connection can wait for the next request without occupying a worker thread for the entire idle wait.

`server.tomcat.keep-alive-timeout` affects how long Tomcat waits for the next request on a connection. It differs from the maximum time a service is allowed to process a business request.

For example, 300 open keep-alive connections do not mean 300 worker threads are busy.

### 8.2. HTTP/2

HTTP/2 multiplexes multiple streams over a single TCP connection. Thus, one connection can carry many coexisting requests. Dispatch and processing still depend on the connector, executor, and application.

Do not apply the rule of thumb `maxConnections ≈ maximum concurrent requests` to HTTP/2; also check stream/concurrency limits across involved layers.

### 8.3. Async Servlets

Spring MVC supports mechanisms such as `Callable`, `DeferredResult`, `WebAsyncTask`, or streaming. When a request enters the async phase and releases the worker, the request remains in-flight without holding a Tomcat request-processing thread for the entire wait.

When using async, inspect the executor running the actual work and its limits. Moving blocking I/O onto an unbounded executor merely shifts the overload point elsewhere.

### 8.4. Virtual Threads

Java 21 virtual threads can help blocking request models utilize threads more efficiently, but total requests completed per second remain bounded by CPU, databases, external APIs, memory, and other configurations. Enabling virtual threads does not make `max-connections` or OS resources infinite.

## 9. Timeouts and Connection Reuse Affect Capacity

Beyond the three primary limits, how long connections stay alive determines how many resources remain held:

- `server.tomcat.connection-timeout`: wait time after accepting a connection to read the request URI line. This is not the "total timeout of a service/controller".
- `server.tomcat.keep-alive-timeout`: wait time for the next request on a connection; if unset, the connection timeout value is normally used.
- `server.tomcat.max-keep-alive-requests`: number of requests allowed on one connection before closing per connector policy.
- Timeouts on reverse proxies, load balancers, clients, databases, and outbound HTTP clients: independent timeouts that must be coordinated.

For instance, shortening the keep-alive timeout can reduce idle connections holding slots, while increasing TCP/TLS handshakes. Lowering connection-timeout can curb slow-sending clients, but can also fail valid clients on high-latency networks.

**Do not use connection-timeout to solve a 30-second SQL query.** That usually requires JDBC/query timeouts, transaction timeouts, downstream HTTP client timeouts, and business limits; overall request timeouts from the client/gateway viewpoint must be designed separately.

## 10. Throughput, Latency, and In-Flight Requests: Quantifying with Little's Law

One way to estimate average concurrent work in steady state is:

~~~text
L = λ × W

L = average number of in-flight requests
λ = average throughput (requests/second)
W = time a request spends in the system (seconds)
~~~

If a system completes an average of 300 requests/second with an average end-to-end processing time of 0.20 seconds:

~~~text
L = 300 × 0.20 = 60 average in-flight requests
~~~

This is an **average value**, not p99 concurrency, required worker threads, or connection limits to configure. If queueing occurs, W increases and L can increase as well without throughput increasing.

Standalone Java example runnable on JDK 17+:

**CapacityMath.java**

~~~java
import java.util.Locale;

public class CapacityMath {
    public static void main(String[] args) {
        double throughputPerSecond = 300.0;
        double averageLatencySeconds = 0.20;
        double averageInFlight = throughputPerSecond * averageLatencySeconds;

        System.out.printf(Locale.ROOT,
            "Average in-flight requests: %.0f%n", averageInFlight);
    }
}
~~~

Compile and run:

~~~bash
javac CapacityMath.java
java CapacityMath
~~~

Exact stdout:

~~~text
Average in-flight requests: 60
~~~

If at the same throughput of 300 requests/second, average latency climbs to 2 seconds due to queueing, average in-flight becomes 600, which does not mean the server is 10x more capable.

**Do not use Little's Law to directly pick `threads.max=60`**. Thread occupancy depends on the synchronous portion holding threads; bursts, timeouts, percentiles, CPU, and DB contention must also be measured.

## 11. Example Tomcat Test Configuration in Spring Boot

The configuration below is for **local machine testing**. It intentionally sets low limits to make differences observable; do not apply it verbatim to production.

**src/main/resources/application.yml**

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    threads:
      max: 8
      min-spare: 2
    max-connections: 64
    accept-count: 20
    connection-timeout: 5s
    keep-alive-timeout: 3s
~~~

Meaning:

- Tomcat caps platform worker threads at 8 for synchronous request handling.
- The connector is configured with a limit of 64 accepted connections.
- The requested listen backlog is 20; the effective value depends on the OS.
- Request line timeout and HTTP keep-alive wait time are configured separately.
- `server.address=127.0.0.1` keeps the demo listening only on IPv4 loopback, suitable for individual practice.

If you want to experiment with the executor queue, you can try adding `server.tomcat.threads.max-queue-capacity` with a positive value in a test environment, provided you understand how the executor is created and measure the right signals; avoid assuming changing queue capacity guarantees a fixed HTTP status code.

### 11.1. Minimal Runnable Gradle Project

Structure:

~~~text
tomcat-capacity-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/capacity/
    │   ├── CapacityDemoApplication.java
    │   └── CapacityController.java
    └── resources/
        └── application.yml
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tomcat-capacity-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**src/main/java/com/example/capacity/CapacityDemoApplication.java**

~~~java
package com.example.capacity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CapacityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CapacityDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/capacity/CapacityController.java**

~~~java
package com.example.capacity;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class CapacityController {

    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    @GetMapping("/work")
    public Map<String, Integer> work(
            @RequestParam(defaultValue = "200") int delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "delayMs must be 0..2000");
        }

        int active = inFlight.incrementAndGet();
        peak.accumulateAndGet(active, Math::max);

        try {
            // Intentionally occupy the worker thread to observe limits.
            // Do not use Thread.sleep to simulate production business work.
            Thread.sleep(delayMs);
            return Map.of(
                "activeAtEntry", active,
                "peakObserved", peak.get());
        } finally {
            inFlight.decrementAndGet();
        }
    }

    @GetMapping("/stats")
    public Map<String, Integer> stats() {
        return Map.of(
            "inFlight", inFlight.get(),
            "peakObserved", peak.get());
    }
}
~~~

The `AtomicInteger` fields ensure thread-safe counter updates in the demo. `inFlight` only counts executions of `work()` inside a single instance; it does **not** count all sockets, all Servlet requests, connections waiting for accept, or requests on other instances.

### 11.2. Running the Program

In the directory containing `build.gradle` with JDK 21 and a compatible Gradle version:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

If the Gradle wrapper already exists, simply run `./gradlew bootRun`. On Windows PowerShell, use `.\gradlew.bat bootRun`.

When Boot starts successfully, embedded Tomcat listens on 127.0.0.1:8080. No standalone Tomcat installation is required.

Test one request:

~~~bash
curl -i "http://127.0.0.1:8080/demo/work?delayMs=200"
~~~

The expected result is HTTP 200 and a JSON response with two fields, for example when only one request has run:

~~~json
{"activeAtEntry":1,"peakObserved":1}
~~~

Values in the response vary with concurrency and request history, so do not treat this as a fixed stdout/JSON for every run.

Inspect the demo counters:

~~~bash
curl -s "http://127.0.0.1:8080/demo/stats"
~~~

When no `work` requests are running, `inFlight` is usually 0. `peakObserved` holds the highest value observed since startup; restarting resets it.

### 11.3. Testing Concurrent Requests Locally

Bash/Linux/macOS example firing 20 nearly simultaneous requests:

~~~bash
for i in $(seq 1 20); do
  curl -s -o /dev/null "http://127.0.0.1:8080/demo/work?delayMs=1000" &
done
wait
curl -s "http://127.0.0.1:8080/demo/stats"
~~~

With `threads.max=8`, no async handling, and an intentionally blocking controller, peak synchronous `work` execution normally will not exceed the corresponding request-processing worker count. However, the exact peak and completion time depend on scheduling, keep-alive, client connections, JVM, OS, and actual configuration.

**Do not run load tests against production systems or someone else's servers.** The demo binds only loopback; the numbers 8/64/20 were chosen to make the difference between threads, connections, and backlog easy to observe.

Try varying `threads.max`, `max-connections`, and `accept-count` one at a time in a test environment, measure latency and errors again, and explain why the results change. Change only one group of variables at a time to avoid wrong conclusions.

## 12. Measuring and Observing with Actuator, Micrometer, and the OS

The controller example above shows executions inside a single method, not connector-level metrics. Observing a real application requires both server metrics and downstream metrics.

If adding Spring Boot Actuator:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

In a local environment, you can expose the metrics endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

This is an **extension** beyond the initial demo configuration; if merging into the same YAML file, merge the `server` keys to avoid duplicate root blocks. Enabling Tomcat's MBean Registry helps collect full Tomcat metrics in Spring Boot setups with the appropriate Micrometer binder.

Common metric names to look for in Spring Boot/Micrometer Tomcat include:

- `tomcat.threads.busy`: busy worker threads.
- `tomcat.threads.current`: current worker count.
- `tomcat.threads.config.max`: configured worker thread limit.
- `tomcat.connections.current`: current connection count exported by server metrics.
- HTTP server request metrics `http.server.requests`: request count, duration, broken down by status/method/URI depending on tags and instrumentation.

Available metric names and tags depend on versions and instrumentation. Call `/actuator/metrics` to list them first, then query a specific metric, for example:

~~~bash
curl -s http://127.0.0.1:8080/actuator/metrics
curl -s http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy
curl -s http://127.0.0.1:8080/actuator/metrics/http.server.requests
~~~

**Do not expose unprotected metrics on the Internet.** Production needs access authorization, network restrictions, or secure metric export to an observability backend.

When investigating multiple instances, inspect metrics per **instance/pod** alongside load-balancer aggregates. System-wide request totals do not reveal whether a single pod is overloaded.

Combine with:

| Signal | What It Tells You |
| --- | --- |
| RPS/throughput | Requests completed per time interval |
| p50/p95/p99 latency | Median and tail of the response-time distribution |
| HTTP 4xx/5xx, timeouts, connection refused | Application, gateway, or network errors |
| Tomcat busy/current/max threads | Saturation risk in the worker pool |
| Tomcat current/allowed connections | Connection occupancy, which may include idle keep-alive |
| JVM CPU, heap, GC pauses, thread dumps | CPU/memory/lock bottlenecks |
| Hikari active/idle/pending/timeout | Whether threads are waiting for database connections |
| Client pool pending, remote API latency | Whether threads are waiting on outbound HTTP |
| OS TCP backlog drops, open files | Whether socket/OS limits are the bottleneck |
| Gateway upstream connect/read timeout | Slow requests or failures before/after reaching the app |

If `tomcat.threads.busy` stays low while p99 is high, do not conclude Tomcat is completely healthy: the app may use async processing, suffer network issues at the gateway, run slow queries, or have requests blocked before entering the connector.

## 13. Combining Tomcat Limits with Database Pools and Downstream Services

Suppose:

~~~text
Tomcat threads.max     = 200
Tomcat max-connections = 1000
Hikari maximumPoolSize = 20
Each request needs 1 JDBC connection for 300 ms
~~~

If all 200 workers hit the database simultaneously, many requests will wait to acquire a connection. Raising `threads.max` to 500 does not give the database extra capacity; the queue gets longer and more requests time out waiting.

Diagnostic guide:

| Measured Bottleneck | Investigation Direction |
| --- | --- |
| Worker threads always busy, CPU still low | Inspect blocking calls and downstream capacity before raising threads |
| Hikari pending rising, active connections near max | Optimize queries/transactions, shorten connection hold time, size pool to DB capacity |
| CPU near 100%, p99 rising | Reduce overhead, optimize code, scale out; adding many threads may worsen it |
| Accepted connections near max with few requests | Check idle keep-alive, connection leaks, proxy pooling, timeouts |
| Client connect timeouts during bursts | Check maxConnections, OS listen backlog, load balancer, network, and processing speed |
| Queue grows without throughput increasing | Prioritize reducing processing time, bounding waits, load shedding, or scaling appropriately |
| Gateway 504 while app responds late | Align timeouts and reduce backend/downstream latency |

A system may need **bulkheads** to cap concurrent calls to expensive dependencies, bounded queues, and early rejection under overload. These policies are designed at the application/gateway layer; they do not appear automatically from `threads.max` or `accept-count`.

### 13.1. Rate Limit and Concurrency Limit Are Not the Same

- **Rate limit** controls request velocity over time, such as 100 requests/second per API key.
- **Concurrency limit** controls how many requests coexist at a given instant, such as at most 20 heavy transactions in progress.
- **Connection limit** controls sockets to the server, not tied directly to users or business permissions.
- **Queue limit** controls how many units are waiting at a specific layer.

An API needing abuse protection can return 429 Too Many Requests when exceeding a designed rate limit; 503 Service Unavailable can be suitable when actively shedding load due to overload. **Spring Boot/Tomcat does not automatically guarantee that exceeding accept-count or threads.max returns 429 or 503**: requests may simply wait, time out, or fail to connect before any HTTP response is produced.

## 14. How to Design and Tune Limits

An empirically grounded process:

1. **Define SLOs:** e.g., 95% of requests complete under 300 ms at 200 RPS with errors below an allowed threshold.
2. **Characterize workloads:** lightweight GETs, DB-writing POSTs, file uploads, streaming, long polling, and batch jobs have different resource profiles.
3. **Measure baseline:** throughput, p50/p95/p99, CPU, memory, Tomcat threads/connections, and database pool.
4. **Inspect client/proxy behavior:** TCP connection counts, HTTP/1.1 vs. HTTP/2, keep-alive, upstream pools, and timeouts.
5. **Find the smallest limit along the path:** worker threads, JDBC pool, CPU, outbound HTTP clients, gateway, or OS.
6. **Set sensible concurrency and queues:** bound resources to serving capacity, avoid unbounded queues; consider early rejection.
7. **Load test incrementally:** steady load, burst, soak tests, and failure tests in permitted environments.
8. **Change one parameter group at a time:** e.g., worker max, max connections, keep-alive timeout, database pool; compare before/after on p99 and errors.
9. **Test recovery after overload:** when a burst ends, do queues drain and does latency recover quickly?
10. **Document assumptions and rollback:** record Boot/Tomcat versions, infrastructure, instance count, profiles, and verified config sets.

Decision example:

~~~text
p99 rising + tomcat.threads.busy near max?
    |
    +-- Yes -> Where are workers stuck?
    |          +-- High CPU -> optimize CPU / scale
    |          +-- High JDBC pending -> optimize DB / pool / limit workload
    |          +-- Slow external API -> timeouts / bulkheads / caching
    |
    +-- No  -> Check connection occupancy,
                 proxy/network, async executor, and downstream
~~~

Do not pick `threads.max` by arbitrarily multiplying by CPU cores. For heavily I/O-bound requests, more workers than cores can make sense; for CPU-bound work, many threads may only increase context switching. Measure blocking time, per-thread resource usage, and downstream capacity.

## 15. Common Misconceptions

1. **"max-connections means max requests."** False when keep-alive, HTTP/2, queued requests, and async processing exist.
2. **"threads.max=200 means only 200 clients can connect."** False; Tomcat NIO can manage a larger number of connections.
3. **"accept-count is a queue of 100 requests behind the worker pool."** False; it is a connection backlog at the listening socket/OS layer.
4. **"Increasing queues increases throughput."** Not necessarily; queues usually only hold more work, increasing wait times and tail latency.
5. **"Increasing threads.max fixes a slow database."** It can worsen the situation by adding more requests waiting on the DB.
6. **"connection-timeout controls total controller execution time."** False; this property relates to reading the request line after accept.
7. **"Each HTTP/2 connection carries only one request."** False due to multiplexed streams.
8. **"Every in-flight request holds a worker thread continuously."** False with asynchronous Servlets and other I/O models.
9. **"Setting min-spare high increases maximum request throughput."** No; it is the minimum maintained worker count, not the maximum threshold.
10. **"Enabling virtual threads removes the need for concurrency limits."** False; CPU, databases, remote APIs, and memory remain finite.
11. **"A 502/504 definitely means Tomcat returned an error."** Not necessarily; those statuses may be generated by a reverse proxy.
12. **"Exceeding threads.max returns HTTP 429."** False; 429 requires proper rate-limiting policies and is not emitted automatically by the worker pool.
13. **"Checking only the threads.busy metric is enough."** Insufficient to see OS queues, DB pools, gateways, or idle sockets.
14. **"Use Jetty/Undertow settings the same way as Tomcat."** False; each runtime has different thread, connection, and configuration models.
15. **"Load test in production and ramp up until failure."** Dangerous and hard to reproduce; use controlled environments with agreed workloads and limits.

## 16. Operations Checklist

Before finalizing embedded server settings, answer:

- Is the actual web stack Spring MVC/Servlet, WebFlux, or an app without a web server?
- Is the actual server Tomcat, Jetty, Undertow, Reactor Netty, or an external container?
- Is it using the default Tomcat Executor, a custom Executor, or Java virtual threads?
- In which configuration sources are `threads.max`, `min-spare`, `max-connections`, and `accept-count` set, and what are their effective values?
- How do HTTP clients use keep-alive, HTTP/2, or reverse proxy pooling?
- Are metrics and alerts in place for connection/request/queue saturation?
- Do database pools, HTTP client pools, CPU, memory, and file descriptors have enough capacity for the workload?
- Are client/gateway, Servlet connector, database, and remote API timeouts consistent with SLOs?
- Does the system have appropriate admission control, rate limiting, bulkheads, or early rejection?
- Have steady-state, burst, p95/p99, error rates, and post-overload recovery been tested?
- Have configuration changes been documented, reviewed, and paired with a rollback plan?

**Core takeaway:** `threads.max`, `max-connections`, and `accept-count` bound **three different resources**. They interact with HTTP keep-alive, HTTP/2, executor queues, timeouts, and downstream capacity. A server that "accepts many connections" is not necessarily able to "process many requests"; sound configuration starts from workload, measurement, and latency requirements, and only then chooses appropriate limits.

## Reference Documentation

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): look up `server.tomcat.threads.max`, `max-connections`, `accept-count`, and timeouts.
- [Apache Tomcat 10.1 — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): `maxThreads`, `maxConnections`, `acceptCount`, `maxQueueSize`, keepAlive, and executors.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): how to configure embedded servers.
- [Spring Boot 3.3 — Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): observing requests/JVM/server via Micrometer.