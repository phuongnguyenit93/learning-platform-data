# Connection Limits, Queues, and Overload Rejection Capabilities

## 1. Objectives and Scenario

In **Spring Boot - web-runtime**, an application can receive requests faster than it can finish work. When connections, threads, queued tasks, database connections, or HTTP client connections grow beyond serving capacity, the system can slow down, time out, run out of memory, or stop accepting connections. The topic **Performance and Limits** requires designing for **controlled load handling**, not just optimizing the low-traffic case.

For example, consider an API that generates a report in two seconds per request. If 100 users call it concurrently, pushing all 100 tasks into an unbounded queue will not generate reports faster: later callers may wait many minutes and retry after their client times out. A healthy system can choose to **accept up to N running jobs, allow M short-term queued jobs, and reject excess load** with a clear response.

Four distinct capacities must be separated:

1. **Connections:** TCP sockets held by HTTP clients, load balancers, and Tomcat.
2. **Concurrency:** request threads, worker threads, database connections, and HTTP client connections.
3. **Queueing:** unprocessed requests waiting in the OS, proxy, Servlet connector, executor, or downstream pools.
4. **Overload rejection (load shedding/rejection):** requests refused because quotas or capacity are exhausted, returning HTTP 429/503, or hitting TCP timeouts/refusals before reaching HTTP.

This lesson focuses on **Spring Boot 3.3.13, embedded Tomcat 10.1, Spring MVC, and Java 17+**. The configuration values here are chosen for the lab, **not default production thresholds or universal recommendations**.

## 2. Layers of a Request: There Is No Single Queue

~~~text
Client / Load generator
        |
        v
TCP handshake and OS accept backlog
        |
        v
Ingress / API gateway / Load balancer (if present)
        |       - connection limits
        |       - per-user quotas / rate limiting
        |       - upstream timeout / retry
        v
Tomcat HTTP connector
        |       - maxConnections: connection count
        |       - maxThreads: request workers
        |       - acceptCount: requested OS listen backlog
        v
Spring Security / Spring MVC Controller
        |
        v
Application admission control
        |       - concurrent running worker tasks
        |       - bounded queue
        |       - reject when saturated
        v
Database (HikariCP) / External HTTP pool
        |       - active connections
        |       - pending acquire / timeouts
        v
HTTP response: 2xx / 4xx / 5xx if a response path still exists
~~~

If the **OS backlog is full**, a TCP client can hit connection refused or connect timeout **before Spring Security or the Controller ever runs**. In that case the application **cannot emit HTTP 503**. If a request reaches the Controller and the business pool is full, the application can actively return 503.

This is a critical boundary when observing systems: **seeing zero 503s in app logs does not prove there is no overload**. You must inspect the proxy, Tomcat, OS, and downstreams as well.

## 3. Connections Do Not Equal HTTP Requests or Threads

| Resource | Unit | Difference |
| --- | --- | --- |
| TCP connection | socket | One keep-alive connection can serve many HTTP requests over time |
| HTTP/1.1 request | request | Not every request opens a new TCP connection |
| HTTP/2 stream | stream | One connection can multiplex multiple requests concurrently |
| Tomcat worker | thread | Serves Servlet requests, not synonymous with one socket |
| Servlet async request | open request | The worker can be released while awaiting a `CompletableFuture` |
| Business executor worker | Java thread/task | Separate from Tomcat workers, with its own queue |
| Task queue | unstarted work item | Holds data in JVM RAM, requires bounded capacity |
| OS accept backlog | TCP connections awaiting accept | Does not hold Java `Runnable` objects |
| HikariCP connection | JDBC connection | Bounded by the DB and pool |
| Outbound HTTP pool | upstream connection | Has its own active/idle/pending request tracking |

For example, 120 open connections does not mean 120 requests are running. Many connections may be **idle keep-alive**. Conversely, with HTTP/2, concurrent requests can outnumber TCP connections.

Low CPU can still accompany overload when threads are **waiting on the DB, network, queues, or locks**. Raising thread count based solely on CPU utilization is an easy mistake.

## 4. Tomcat: maxThreads, maxConnections, acceptCount

### 4.1. maxThreads: Request-Processing Threads

**`server.tomcat.threads.max`** limits the request-processing threads of Tomcat's internal executor. For synchronous MVC requests, a worker typically stays busy during Controller execution, including when blocked on JDBC, file I/O, or blocking HTTP clients.

When all workers are busy, additional connections/requests may wait until a thread frees up or time out. Increasing `maxThreads` does not automatically make the database run more queries. If the connector uses a custom externally supplied executor, the internal executor thread property may no longer determine the actual count.

### 4.2. maxConnections: Accepted TCP Connections

**`server.tomcat.max-connections`** limits how many connections the connector accepts and handles at the same time. A connection can be idle, reading a request, or awaiting processing. It is **not an RPS limit**, nor the task count inside an `ExecutorService`.

### 4.3. acceptCount: OS Backlog, Not a Java Task Queue

**`server.tomcat.accept-count`** requests an OS connection queue length when Tomcat cannot accept more connections under connector limits. **The operating system may not honor the exact requested value.** When the backlog is also full, clients can receive connection refused, timeouts, or OS/network-dependent behavior.

Do not confuse `accept-count` with `queueCapacity` on `ThreadPoolTaskExecutor` or `ArrayBlockingQueue`. They belong to **two different layers**.

### 4.4. Two Easily Misunderstood Timeouts

- **`server.tomcat.connection-timeout`:** how long the connector waits for the request line after accepting a connection; not a deadline for "Controller must finish processing".
- **`server.tomcat.keep-alive-timeout`:** how long to wait for the next request on a keep-alive connection; not a business processing timeout.

A request running a 15-second SQL query can still hold its Servlet thread even with `connection-timeout` set to 5 seconds. To bound total duration, configure deadlines at the gateway, application, JDBC, and HTTP client layers.

### 4.5. Sample Tomcat Configuration

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 24
      min-spare: 4
    max-connections: 120
    accept-count: 30
    connection-timeout: 5s
    keep-alive-timeout: 10s
~~~

This sample targets Boot 3.3/Tomcat; do not reuse the exact namespace for Jetty, Undertow, or Reactor Netty. These numbers are **illustrative only**. On Java 21 with virtual threads enabled or with a different executor, platform-thread settings need reassessment; this lab uses **Java 17**.

## 5. From Java Executors to Bounded Queues

**`ThreadPoolExecutor`** accepts tasks according to this rule:

1. If worker count is below `corePoolSize`, create a worker first.
2. Once core workers exist, prefer enqueuing the task if the queue accepts it.
3. If the queue is full, grow workers up to `maximumPoolSize` when allowed.
4. When workers hit max and the queue is full, invoke `RejectedExecutionHandler`.

Surprising behavior: with **core=2, max=8, queue=100**, the third worker is **not necessarily created when the third request arrives**. The third task gets queued. With a very long queue, a large `maxPoolSize` often never kicks in as the config author expected.

### 5.1. Rejection Policies

| Policy | When Saturated | Risk |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Must catch and map to an HTTP status / domain error |
| `CallerRunsPolicy` | The submitting thread executes the task if the executor is still running | If the caller is a Servlet worker, it can stall Tomcat |
| `DiscardPolicy` | Drops the task silently | The request may never receive a result |
| `DiscardOldestPolicy` | Drops the oldest queued task to submit the new one | Loses accepted work; breaks ordering expectations |
| Custom handler | Chosen by the app | Must preserve business contracts and observability |

An HTTP endpoint needing clear responses is usually easier to manage with a **bounded queue + `AbortPolicy` + returning 503** at the admission boundary. `CallerRunsPolicy` is not always wrong, but you must know who the caller is and how long running the task directly can block that thread.

### 5.2. Why Are Unbounded Queues Dangerous?

Suppose incoming load is 1,000 tasks/second while the system only completes 100 tasks/second. The backlog grows by nearly **900 tasks per second** during sustained overload. An unbounded queue merely accumulates latency and consumes RAM; eventually users time out and retry, expanding the backlog further.

A short queue absorbs brief bursts; once capacity is exhausted, **early rejection** is usually better than accepting endlessly and killing the whole process with OOM.

### 5.3. Little's Law for Reasoning, Not Mechanical Sizing

In steady state, **L = lambda × W** where:
- L: average number of requests in the system;
- lambda: average throughput (requests/second);
- W: time a request spends in the system (seconds).

For example, at 100 requests/second with each request taking 0.2 seconds on average, there are roughly **20 in-flight requests on average**. This is **not** proof that `maxThreads=20` is enough: bursts, p99 latency, CPU vs I/O, queues, and downstream concurrency also have major impact.

## 6. HTTP 503, HTTP 429, and Connection Errors: Who Is Rejecting?

### 6.1. 503 Service Unavailable

Under HTTP semantics, **503** fits when the server is temporarily unable to serve due to **overload or maintenance**. When the application admission layer can still respond, it can return:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
Content-Type: application/json

{"status":"rejected","detail":"bounded queue is full"}
~~~

**`Retry-After: 1`** hints to the client to wait ~1 second before retrying. It **does not guarantee** capacity will be available then. Retries should use exponential backoff with jitter, bounded attempts, and an overall deadline.

### 6.2. 429 Too Many Requests

**429** fits when a specific user, API key, or tenant exceeds its **rate limit/quota**. A client sending 1,000 requests/minute against a 60 requests/minute quota is a classic 429 case. Do not treat global worker pool exhaustion for the whole system as an individual user's rate-limit error.

### 6.3. 502, 504, and Network Failures

- **502 Bad Gateway:** the gateway/proxy received an upstream error or invalid response.
- **504 Gateway Timeout:** the gateway waited for upstream past its deadline.
- **TCP refused / connect timeout:** occurs before any HTTP response, e.g., OS backlog full or network policy.
- **500:** may indicate bugs or unmapped exceptions; does not automatically mean overload.

Tracking HTTP 503 counts solely inside the application is **not enough**. Some requests may never reach the Servlet container and never appear in application logs.

### 6.4. Retry Storms and Idempotency

If 1,000 clients all receive 503 and all retry at exactly 1 second later, traffic creates a fresh spike. Use backoff with jitter and a retry budget. For order/payment-creating POSTs, enforce **idempotency keys or deduplication logic**; never retry blindly because side effects may have succeeded on the server despite an error response.

## 7. Java 17 Lab: Deterministic Rejection Behavior

This is a standalone Java program, **requiring neither Maven nor Spring**. It creates **2 workers and a queue with only 2 slots**, holds both workers using a `CountDownLatch`, submits two more tasks into the queue, and then attempts to submit a fifth task. Because state is pinned by latches, it reproduces deterministically, unlike tests relying on uncontrolled sleeps.

**File `BoundedExecutorProof.java`:**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorProof {

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable hold = () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(hold);
            pool.execute(hold);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            pool.execute(() -> {});
            pool.execute(() -> {});

            int running = pool.getActiveCount();
            int queued = pool.getQueue().size();

            boolean rejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("running=" + running);
            System.out.println("queued=" + queued);
            System.out.println("rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

**Compile and run:**

~~~bash
javac BoundedExecutorProof.java
java BoundedExecutorProof
~~~

**Exact stdout upon normal execution:**

~~~text
running=2
queued=2
rejected=true
~~~

**Explanation:** `main` waits on the `started` latch to confirm both workers entered `hold`. Since `release` has not opened yet, the workers cannot finish. The next two tasks wait inside `ArrayBlockingQueue(2)`. The fifth task cannot be accepted, so `AbortPolicy` throws `RejectedExecutionException`. The `finally` block releases the latch and shuts down cleanly, avoiding a hung process.

This is a **JVM `ThreadPoolExecutor` queue**, not the OS socket backlog or Tomcat `accept-count`.

## 8. Spring Boot MVC Lab: Active Overload Handling Returning 503

The Spring Boot lab uses **2 business workers + 2 queue slots**. Tomcat accepts HTTP requests; the Controller submits the business task to the **bounded executor**, returning a `CompletableFuture` so Spring MVC processes it via Servlet async. When the executor is full, the Controller returns **503 + `Retry-After: 1`** right at the admission boundary.

**Lab usage restriction:** run only on localhost/staging; do not apply these fixed limits to production. Tasks are simulated with `Thread.sleep`, not a real service backed by a database or upstream.

### 8.1. Directory Tree

~~~text
overload-control-demo/
├── pom.xml
├── BoundedExecutorProof.java
└── src/main/
    ├── java/com/example/overload/OverloadApplication.java
    └── resources/application.yml
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>overload-control-demo</artifactId>
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

### 8.3. application.yml

~~~yaml
server:
  port: 8080
  tomcat:
    threads:
      max: 24
      min-spare: 4
    max-connections: 120
    accept-count: 30
    connection-timeout: 5s
    keep-alive-timeout: 10s
    mbeanregistry:
      enabled: true

spring:
  mvc:
    async:
      request-timeout: 8s

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

**`server.tomcat.threads.max`** limits request workers, **`max-connections`** limits connector connections, and **`accept-count`** sets the desired OS backlog. **`spring.mvc.async.request-timeout`** governs the Servlet async response lifetime rather than replacing business/downstream timeouts. **`mbeanregistry.enabled`** enables Tomcat metrics when Actuator auto-configuration instruments them.

**Security:** `/actuator/metrics` is exposed in the lab, but in production access must be restricted via network/authentication; never treat metrics as a public API.

### 8.4. Complete Java Code

**`src/main/java/com/example/overload/OverloadApplication.java`:**

~~~java
package com.example.overload;

import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OverloadApplication {
    public static void main(String[] args) {
        SpringApplication.run(OverloadApplication.class, args);
    }
}

@Configuration
class WorkerConfig {
    @Bean(destroyMethod = "shutdown")
    ThreadPoolExecutor boundedWorker() {
        AtomicInteger workerNumber = new AtomicInteger();
        return new ThreadPoolExecutor(
            2, 2, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(2),
            job -> new Thread(
                job,
                "business-worker-" + workerNumber.incrementAndGet()
            ),
            new ThreadPoolExecutor.AbortPolicy()
        );
    }
}

record Reply(String status, long millis, String detail) {}

@RestController
class CapacityController {
    private final ThreadPoolExecutor executor;

    CapacityController(ThreadPoolExecutor boundedWorker) {
        this.executor = boundedWorker;
    }

    @GetMapping("/api/work")
    CompletableFuture<ResponseEntity<Reply>> work(
            @RequestParam(defaultValue = "1500") long ms
    ) {
        if (ms < 0 || ms > 3000) {
            return CompletableFuture.completedFuture(
                ResponseEntity.badRequest()
                    .body(new Reply("invalid", 0, "ms must be 0..3000"))
            );
        }

        try {
            return CompletableFuture.supplyAsync(() -> {
                try {
                    Thread.sleep(ms);
                    return ResponseEntity.ok(
                        new Reply("completed", ms, "ok")
                    );
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(new Reply(
                            "interrupted", 0, "worker interrupted"
                        ));
                }
            }, executor);
        } catch (RejectedExecutionException ex) {
            return CompletableFuture.completedFuture(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .header(HttpHeaders.RETRY_AFTER, "1")
                    .body(new Reply(
                        "rejected", 0, "bounded queue is full"
                    ))
            );
        }
    }

    @GetMapping("/api/capacity")
    Map<String, Object> capacity() {
        return Map.of(
            "active", executor.getActiveCount(),
            "queued", executor.getQueue().size(),
            "poolSize", executor.getPoolSize(),
            "maxPoolSize", executor.getMaximumPoolSize(),
            "queueRemaining", executor.getQueue().remainingCapacity(),
            "completed", executor.getCompletedTaskCount()
        );
    }
}
~~~

**Why does this code clearly separate the two capacity layers?**
- Tomcat can accept HTTP requests across up to 24 Servlet workers for synchronous flow; the business executor is **a separate pool** with **2 workers + 2 queued tasks**.
- **`CompletableFuture.supplyAsync`** moves the `Thread.sleep` test onto the business executor instead of blocking the request thread synchronously with `block()` inside the Controller.
- Spring MVC supports `CompletableFuture` asynchronous returns. The request still holds state/response resources and requires an async dispatch when the future completes.
- **`RejectedExecutionException`** is thrown immediately when submitting a task that cannot be accepted. The Controller catches it and returns **HTTP 503** rather than masking the error as HTTP 200 or 500.
- **`ms` outside 0..3000** returns HTTP 400 as invalid input, **not confused with overload**.
- The bean specifies **`destroyMethod="shutdown"`** so the executor shuts down when the Spring context closes.
- **`GET /api/capacity`** is a snapshot of Java executor metrics, **not a measure of TCP connections or OS backlog**.

**Do not infer from 2 workers + 2 queue slots that at most four TCP connections are allowed.** Many more sockets can exist; only tasks accepted by the executor are bounded here.

**Timeout warning:** if the client disconnects or the async request expires, the business task may keep running. `CompletableFuture` does not automatically roll back transactions or halt side effects. Production needs deadline/cancellation handling and an idempotency policy.

### 8.5. Running the Application and Verifying

Requires **JDK 17+, Maven, and port 8080 free**. From project root:

~~~bash
mvn test
mvn package
java -jar target/overload-control-demo-1.0.0.jar
~~~

Open another terminal:

~~~bash
curl -i "http://localhost:8080/api/work?ms=500"
curl -s "http://localhost:8080/api/capacity"
~~~

For a single successful request, expected HTTP status is **200** and JSON body contains:

~~~json
{"status":"completed","millis":500,"detail":"ok"}
~~~

JSON field order may vary by serializer. A request with `ms=9000` returns **HTTP 400** with:

~~~json
{"status":"invalid","millis":0,"detail":"ms must be 0..3000"}
~~~

### 8.6. Small Burst on Localhost

On Bash/Linux/macOS:

~~~bash
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  curl -sS -o /dev/null -w "%{http_code}\n" \
    "http://localhost:8080/api/work?ms=2500" &
done
wait
~~~

**Run only on localhost or authorized staging.** With only 2 business workers and 2 queue slots, under a sufficiently concurrent burst you will typically observe **some 200s and some 503s**. However, **there is no single fixed stdout set**: TCP arrival order and task completion timing vary across runs. Never promise literally "four 200s and eight 503s" for a racy HTTP burst test.

To verify **deterministic** rejection, use `BoundedExecutorProof` from Section 7. For HTTP observation, run multiple rounds and aggregate statuses, latency, active workers, and queued tasks.

### 8.7. Actuator and Custom Executor Metrics

With Actuator in `pom.xml` and Tomcat MBean registry enabled:

~~~bash
curl -s http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/api/capacity
~~~

**`/actuator/metrics`** returns the list of meters currently registered in the runtime. Exact names/tags depend on versions and auto-configuration conditions. Tomcat metrics start with **`tomcat.`** when MBean registry instrumentation is active; JVM, process, and HTTP server metrics may also appear.

The demo's **custom `ThreadPoolExecutor`** does not automatically gain full rejection counters and queue-wait histograms just because Actuator is installed. For production, instrument **active/queued/rejected/completed/queue-wait duration** explicitly and alert on rising rejections, high pending queues, or p99 SLO breaches. `/api/capacity` is only a lab snapshot.

## 9. Connection Cap Differs from Business Admission Cap

A request can be stopped at any layer:

~~~text
TCP client
    |
    +-- OS backlog full ----------> connect refused / timeout
    |
    v
Gateway
    +-- per-caller quota ---------> HTTP 429
    +-- upstream unavailable -----> 502 / 503 / 504
    |
    v
Tomcat
    +-- max connections / worker saturation
    |       -> delay, timeout, close; not guaranteed HTTP 503
    |
    v
Spring MVC Controller
    +-- invalid ms ---------------> HTTP 400
    +-- bounded task pool full ---> HTTP 503 + Retry-After
    +-- accepted and completed ---> HTTP 200
~~~

**If the Java executor is full while Tomcat still has threads**, the Controller can return a clean JSON 503. **If the TCP connection is never accepted**, it has no chance to build an HTTP response. Thus application health/metrics never replace network load-balancer telemetry.

## 10. Database Pools and HTTP Client Pools: The Next Bottleneck

For example, an app has 100 Tomcat workers while HikariCP has only 10 DB connections. Many requests can wait for a JDBC connection simultaneously, driving up tail latency and timeouts. Adding more Tomcat threads only parks more requests waiting if the database is the bottleneck.

A configuration fragment for an app with a JDBC DataSource:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 2s
~~~

**This is a fragment, not part of the lab configuration above.** The lab's `application.yml` has no database or JDBC driver. With HikariCP:
- `maximum-pool-size` is the max JDBC connections managed by the pool.
- `connection-timeout` is how long a caller waits for a pool connection before failing.
- A thread waiting to acquire a connection can still occupy a business/Servlet worker.

**Sum across replicas:** if 10 instances each allow up to 30 HikariCP connections, total demand can reach 300 DB connections. You must budget **system-wide**, not per JVM.

With **`WebClient`/Reactor Netty** or another HTTP client, there are also outbound pools, pending acquire queues, connect/response timeouts, and retries. Enlarging the pending queue only makes requests wait longer when the upstream service has no extra capacity.

### 10.1. Deadlines Must Include Queue Wait Time

A request that waits 1.5 seconds for a worker, 1.5 seconds for a DB connection, and runs SQL for 2 seconds has already spent 5 seconds **before sending a response**. If the gateway timeout is 4 seconds, the client receives 504 even as the backend finishes executing SQL. Align timeouts consistently across **gateway → app admission → downstream acquire → execution**, rather than capping only a single step.

## 11. Admission Control, Rate Limiting, Bulkheads, and Backpressure

**Admission control** decides whether to accept new work based on capacity. **Rate limiting** decides how many requests a user/API key may send over an interval. **Bulkheads** partition resource budgets so one slow upstream cannot drag down every feature.

Key techniques:
- **Bounded executor queue:** queue up to N slots; reject overflow.
- **Semaphore with `tryAcquire()`:** cap in-flight operations without forcing users into a long queue.
- **Per-tenant concurrency:** prevent a noisy neighbor from exhausting the global budget.
- **Token bucket rate limiter:** allow short bursts while enforcing a steady long-term rate.
- **Circuit breaker:** stop hammering a failing upstream; does not replace concurrency limits.
- **Load shedding:** temporarily reject lower-priority work.
- **Graceful degradation:** return permitted cached or degraded responses when downstreams weaken.
- **Autoscaling:** add instances when the bottleneck can scale horizontally; does not fix a shared DB connection cap.
- **Backoff with jitter:** prevent retry storms.

Semaphore example, **a fragment inside a service with `permits` and business method defined**:

~~~java
if (!permits.tryAcquire()) {
    throw new CapacityExceededException();
}
try {
    return runBusinessOperation();
} finally {
    permits.release();
}
~~~

This is a **fragment**. `CapacityExceededException` must be defined and mapped to HTTP 503 or an appropriate error. For async work, the permit must be released **when the future actually completes**, not immediately after submitting the task.

### 11.1. 429 and 503 Can Be Combined

A single user exceeding a 100 requests/minute quota can receive **429** even when the server still has spare capacity. Meanwhile, when many legitimate users collectively cause global saturation, the service can return **503** for requests beyond admission capacity. Combining both protects against noisy neighbors and guards shared resources.

Do not rely on IP address as the sole quota identifier in every app: NATs/proxies can put many valid users behind one IP.

## 12. Sizing Pools and Queues from Measurements

Tuning workflow:
1. Define target p95/p99 latency and **request deadline**.
2. Measure throughput, arrival bursts, and mean/tail service times.
3. Distinguish **CPU-bound** from **I/O-bound** workloads.
4. Identify the real bottleneck: Servlet threads, CPU, DB pool, outbound client pool, locks, disk, or GC.
5. Set concurrency caps according to **downstream capacity**, not just CPU core count.
6. Size queues to absorb brief bursts, **not so deep that callers are guaranteed to time out before execution**.
7. Define rejection policies (503/429) and bounded retries.
8. Run controlled load tests, observe recovery, and adjust config from observed results.

**CPU-bound:** too many threads cause context switching without making the CPU faster. **I/O-bound:** can sustain higher concurrency, yet remains bounded by connection pools and memory.

### 12.1. Difference Between Queue Time and Execution Time

If you only measure business method duration, you might see 100 ms methods while users wait 4 seconds in queues. Measure these timestamps:
- request admitted;
- task enqueued;
- task started;
- business completed;
- response completed.

Track **queue wait**, **execution duration**, and **end-to-end latency** separately. An oversized queue can keep 503s near zero while ruining p99 and client timeouts.

### 12.2. Time Budget Example

Given a 2-second client deadline, a system might allocate illustratively 0.2 s network, 0.2 s queue, 1.2 s processing, and 0.4 s reserve. This is **not a universal API config**, yet it shows why new work should not be admitted once it is certain to miss its deadline.

## 13. Reading Metrics at the Right Layer

| Layer | Key Signals | Question |
| --- | --- | --- |
| OS/TCP | connection refused, backlog overflows, open sockets | Are requests blocked before reaching HTTP? |
| Ingress | upstream errors, pending requests, 429/502/503/504 | What is the gateway limiting? |
| Tomcat | busy/total threads, connections, request latency | Are Servlet workers saturated? |
| Business executor | active, queued, rejected, completed | Is the queue hitting its cap? |
| HikariCP | active/idle/pending, connection timeouts | Waiting for JDBC connections? |
| HTTP client pool | leased, pending, connection acquire latency | Are outbound calls bottlenecked? |
| JVM | heap, GC pauses, thread count, CPU | Is the queue causing memory pressure? |
| API | 2xx, 429, 503, p95/p99, retry rate | Rejecting cleanly by policy or cascading failure? |
| Business | deadline exceeded, queue wait, error reasons | Are users getting results on time? |

**Actuator/Micrometer** measures Tomcat, JVM, and HTTP servers. Spring Boot 3.3 requires **`server.tomcat.mbeanregistry.enabled=true`** to auto-instrument Tomcat MBeans. Custom executors may need explicit meter registration for rejected counts and queue wait.

Avoid putting raw user IDs, bearer tokens, or request IDs into metric labels due to cardinality explosion and data exposure. Never expose diagnostic endpoints publicly in production.

## 14. Interpreting Behavior During Overload Tests

- **Smoke test:** a single valid request returns 200.
- **Burst test:** a simultaneous batch to observe queueing and rejection.
- **Load test:** step RPS up gradually and watch throughput/latency.
- **Stress test:** push past capacity to verify fail-fast behavior without OOM.
- **Soak test:** sustained load to catch leaks and queue drift.
- **Recovery test:** drop load back down and verify p99/queues return to normal.
- **Dependency fault test:** slow down DB/upstreams to verify bulkheads and retries.

Only test authorized systems, checking time/concurrency limits beforehand. An HTTP burst involves OS/thread scheduling, so **never promise exact 200/503 counts**. The Java latch proof demonstrates rejection deterministically.

**Passing an overload test** does not mean 100% of requests succeed. A healthy system rejects excess early, keeps queues/heap bounded, serves admitted requests within deadlines, and recovers quickly once load subsides.

## 15. Common Pitfalls

| Misconception | Why It Is Wrong | Fix |
| --- | --- | --- |
| `maxConnections=100` means 100 RPS | Connections are not requests/second | Measure throughput and service time |
| `acceptCount` is a Java task queue | It is the OS socket backlog | Inspect the executor queue separately |
| Raising `maxThreads` fixes DB timeouts | DB pool/downstream has its own limits | Measure HikariCP and DB budgets |
| Zero 503s means no overload | TCP can refuse/time out before Controller runs | Inspect proxy/OS/Tomcat |
| Low CPU means not saturated | Workers may be blocking on I/O | Check blocked threads and pool waits |
| Unbounded queues avoid dropping requests | Latency/RAM grow and clients retry | Bounded queues and load shedding |
| `CallerRunsPolicy` is always safe | Caller may be a Tomcat thread | Identify caller threads, consider `AbortPolicy` |
| `DiscardPolicy` has no errors | It silently swallows tasks | Never use if requests require responses |
| `Retry-After: 1` is a guarantee | Capacity fluctuates | Retry budgets and jitter |
| Servlet async makes JDBC non-blocking | DB still requires threads and connections | Isolate pools and cap concurrency |
| HTTP/2 one connection = one request | HTTP/2 multiplexes streams | Measure true request concurrency |
| Actuator exposes all executor metrics out of the box | Custom pools may require explicit instrumentation | Register counters/gauges |
| Adding replicas always fixes bottlenecks | Shared DB/upstreams can saturate faster | System-wide capacity budgeting |

## 16. Knowledge Check Questions

**1.** How does Tomcat `maxThreads` differ from `maxConnections`?  
**Answer:** `maxThreads` limits request-processing threads; `maxConnections` limits connections accepted/handled by the connector. They measure different resources.

**2.** Does `acceptCount=30` mean exactly 30 `Runnable` tasks waiting in Java?  
**Answer:** No, it is the requested OS accept backlog and depends on OS behavior.

**3.** Why can one TCP connection serve multiple HTTP requests?  
**Answer:** Keep-alive reuse and HTTP/2 multiplexing depending on the protocol.

**4.** In the Java demo with 2 workers + queue 2, why is the fifth task rejected?  
**Answer:** Both workers are held by the latch, both queue slots are full, and `AbortPolicy` throws `RejectedExecutionException`.

**5.** Why does `maxPoolSize=8` with `core=2` and a large queue not immediately spawn a third worker?  
**Answer:** `ThreadPoolExecutor` prefers enqueueing once core threads exist, growing toward max only when the queue rejects the task.

**6.** When the OS backlog fills up, will clients always receive HTTP 503?  
**Answer:** No; they may get connection refused or connect timeouts before an HTTP request/response occurs.

**7.** When a global business executor fills up, should you prefer 429 or 503?  
**Answer:** Usually 503 for service-wide overload; 429 is for per-caller rate limits/quotas.

**8.** Why can p99 be very high when CPU is only 15%?  
**Answer:** Threads are waiting on DB connections, locks, network, queues, or downstreams rather than executing CPU work.

**9.** What happens with `CallerRunsPolicy` if the caller is a Servlet worker?  
**Answer:** The Servlet worker executes the task itself, staying busy and potentially stalling Tomcat.

**10.** Does returning `CompletableFuture` from a Servlet Controller solve a database bottleneck?  
**Answer:** No. It enables Servlet async, yet business workers and JDBC connections remain finite.

**11.** Why can retrying 503 immediately multiple times be harmful?  
**Answer:** It creates a retry storm, piling load onto an overloaded system; use backoff, jitter, and retry budgets.

**12.** Which metrics indicate queue saturation?  
**Answer:** Active workers, queue depth/capacity, rejected counts, queue wait time, and total latency.

**13.** What signals healthy recovery once load drops?  
**Answer:** Queues drain, p95/p99 return to baseline, rejection rates fall, and memory/downstream pending return to normal.

**14.** Where does HTTP/2 make capacity planning tricky?  
**Answer:** Multiple HTTP streams/requests share a single TCP connection; connection count does not measure request concurrency.

**15.** With DB pool at 10 and Tomcat threads at 100, will adding more Tomcat threads fix timeouts?  
**Answer:** No, it may just park more requests waiting for DB connections.

## 17. Pre-Deployment Checklist

- [ ] Distinguished OS backlog, Tomcat threads/connections, app queues, and downstream pools.
- [ ] Configured bounded concurrency/queues aligned with capacity and SLOs.
- [ ] Avoided unbounded queues when wait times are uncontrolled.
- [ ] Caught and mapped rejections explicitly; separated 503 from 429 and other errors.
- [ ] Implemented retries with exponential backoff/jitter, overall deadlines, and idempotency policies.
- [ ] Aligned connect/response/queue/DB timeouts within the total request time budget.
- [ ] Added bulkheads for critical upstreams and fair per-tenant quotas where needed.
- [ ] Tracked rejected counts, active workers, queue depth, and queue wait times.
- [ ] Monitored refusals/timeouts at the OS/proxy layers, not just application 503s.
- [ ] Secured Actuator metrics and avoided logging secrets.
- [ ] Tested bursts, stress, and recovery in authorized environments.
- [ ] Budgeted capacity across all replicas, DBs, and shared upstream quotas.

## 18. Conclusion

**Connection limits, request worker limits, and processing queue limits are independent layers.** Tomcat can hold many connections with only a handful of Servlet threads; the OS has a backlog; the app may have an executor queue; and HikariCP and HTTP clients maintain their own pools. Increasing one limit does not guarantee higher throughput, and can even worsen wait times and memory pressure.

A resilient web runtime requires **admission control, bounded queues, coordinated timeouts, intentional overload rejection, bounded retries, and layer-accurate observability**. Once capacity is exhausted, failing fast with 503 (for requests that reach the application) is far safer than accepting everything and letting requests time out en masse.

## Official References

- Spring Boot 3.3 — Tomcat properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Apache Tomcat 10.1 — HTTP Connector, `maxThreads`, `maxConnections`, `acceptCount`: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Oracle Java 17 — `ThreadPoolExecutor` and rejection: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java 17 — `AbortPolicy`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html
- Spring Framework — Async Requests in MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- RFC 9110 — 503 Service Unavailable, `Retry-After`: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6585 — 429 Too Many Requests: https://www.rfc-editor.org/rfc/rfc6585#section-4