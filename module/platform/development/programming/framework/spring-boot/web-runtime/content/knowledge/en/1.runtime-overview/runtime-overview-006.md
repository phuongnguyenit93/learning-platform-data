# Runtime resources: connections, threads, memory, sessions, and buffers

## 1. Why understand runtime resources?

A Spring Boot application does more than execute Controller methods. When receiving an HTTP request, the application must maintain network connections, allocate execution threads, use memory for data and objects, potentially read session state, borrow connections to databases or external services, and write data through buffers before returning a response. These resources are finite and have different lifecycles.

Most importantly, distinguish **the number of active requests** from **the number of connections, threads, DB connections, and memory consumed**. They are related but not equivalent. Raising a single limit can shift the bottleneck to another resource or overload the system faster.

Goal of this lesson: identify each resource type; understand who creates, holds, reuses, and releases it; read symptoms of resource exhaustion; set appropriate limits; and verify with measurements rather than guesswork.

## 2. Resource map within a web request

| Resource | Role | Typical lifecycle | When constrained |
| --- | --- | --- | --- |
| Inbound HTTP connection | TCP/TLS channel between client, proxy, and web server | May be kept open for multiple requests (keep-alive) | Cannot accept new connections; queued or rejected |
| Thread/worker | Executes handling code; may wait on blocking I/O in Spring MVC | Reused from a pool across many requests | Requests queue up, latency increases |
| Outbound connection | Accesses DB, Redis, other HTTP services | Typically borrowed from a pool and returned after the operation | Waiting for connections, timeouts, dependency errors |
| Memory | Java objects, payloads, sessions, caches, stacks, and native memory | Depends on object, request, or process lifecycle | Frequent GC, higher latency, OOM, or container killed |
| HTTP session | Holds state across requests from one client when needed | Lives until timeout/invalidation | Consumes memory/store, hard to scale across instances |
| Buffer | Temporarily stores data chunks for batched reads/writes | Usually short-lived, per thread or connection | Data piles up, higher memory usage, backpressure |

Example flow for a **Spring MVC + Tomcat + JDBC** application:

1. The client connects via a load balancer to Tomcat; HTTP keep-alive may reuse the socket for subsequent requests.
2. Tomcat dispatches the request to a worker. If the Controller makes synchronous JDBC calls, the worker is usually held while waiting on the DB.
3. The data access layer borrows a DB connection from HikariCP; SQL runs, results map into heap objects; when the operation/transaction scope finishes, the connection is returned to the pool.
4. When sessions apply, the request may read/update data tied to the session ID; the session has a lifecycle separate from the processing thread.
5. The framework writes the response through application, web server, and OS buffers. The worker is released once processing completes; the HTTP socket may remain open for reuse.

This is a general model, not a strict rule that one socket = one thread = one DB connection. HTTP/2 can multiplex multiple request streams over one connection; Spring MVC supports asynchronous processing; and a request may not call the DB at all.

## 3. Connections: opening, reusing, returning to the pool

### 3.1. Distinguishing three connection paths

- **Inbound HTTP connections**: from clients/load balancers to an embedded server such as Tomcat, Jetty, or Reactor Netty. Limits on connections, timeouts, and keep-alive belong to the web server layer.
- **Outbound HTTP connections**: the application calling external APIs via RestClient, WebClient, or corresponding HTTP libraries. These have their **own** pools, timeouts, and reuse policies; inbound limits do not substitute for outbound limits.
- **Data connections**: JDBC DataSource/HikariCP, Redis, message brokers, etc. Each type has its own pool or lifecycle management mechanism. An HTTP connection is not a JDBC connection.

Opening new connections incurs TCP/TLS, authentication, and OS resource costs. Pools allow connection reuse but must be bounded. If a pool is full, new operations **wait** or **time out**; infinite connections are never automatically available.

### 3.2. Key principles for JDBC/HikariCP

- Borrow connections **as late as possible** and return them **as early as possible**. With Spring Data/JPA, let the framework manage resources and transaction boundaries; when using raw JDBC, ensure `Connection`/`Statement`/`ResultSet` are closed properly. Calling `close` on a pooled proxy connection usually **returns it to the pool** rather than immediately destroying the physical socket.
- Do not place slow HTTP calls or user-wait steps inside long DB transactions unnecessarily: the connection can remain held while waiting.
- Set sensible timeouts for **acquiring connections**, **network calls**, **queries**, and **transactions**; they are distinct limits.
- Budget across **all replicas**. For example, 3 instances with max 16 JDBC connections each ⇒ up to 48 connections from this service alone, excluding admin tools and other services. The DB must handle that total.
- When Hikari reports connection exhaustion, inspect slow queries, long transactions, concurrent requests, and leaks before increasing pool size.

### 3.3. Symptoms to distinguish

**Inbound HTTP connections full**: clients struggle to establish connections and may time out directly at the proxy/web server. **Workers full**: connections are accepted, but requests wait for processing. **DB pool full**: requests have workers, yet stall waiting for a JDBC connection. All three can manifest as slow APIs; measure at the right layer.

## 4. Threads: execution resources and wait costs

### 4.1. Spring MVC/Servlet

In traditional Servlet applications, embedded Tomcat uses worker threads to execute requests. A synchronous request calling blocking JDBC or REST APIs typically occupies a worker during the wait time. The worker pool is bounded, and queues or handling behavior vary by connector, configuration, and version. Increasing max threads can raise concurrency **only when CPU, DB, memory, and downstreams still have spare capacity**.

Do not confuse:
- **Open HTTP connections** with **requests actively executing on workers**: keep-alive can hold many idle connections.
- **Busy threads** with **busy CPU**: a busy thread may simply be waiting on a socket/DB.
- **Request thread pool** with **`@Async` executors or schedulers**: they can be separate pools with their own queues and limits.

### 4.2. Spring WebFlux/Reactor Netty

WebFlux on Reactor Netty typically uses a small number of event-loop threads to serve many non-blocking connections. Blocking the event loop with blocking JDBC, `Thread.sleep`, long blocking file reads, or heavy CPU work can slow down many requests together. For unavoidable blocking work, offload to an appropriate scheduler/executor **and bound concurrency**; for reactive flows, prefer non-blocking drivers and libraries when that is the chosen architecture.

**Java 21 virtual threads** can help blocking-style Servlet applications handle more concurrent waiting tasks, but they do not increase DB capacity, nor do they replace timeouts, pools, connection limits, or memory budgets. Tomcat settings for platform worker threads may no longer apply when virtual threads are enabled; observe and verify against the actual stack.

### 4.3. A way to estimate load

Using Little's Law as an approximation in steady state:

**Average concurrent active requests ≈ requests/second × average processing time (seconds).**

For example, 120 requests/second × 0.25 seconds ≈ **30 concurrent requests in flight**. If a downstream slows to 2 seconds at the same arrival rate, the count rises to roughly **240**. This is **not** a formula to configure exactly 30 or 240 threads: latency distribution, asynchronous requests, I/O, traffic bursts, queues, and latency targets (especially p95/p99) also matter. The useful takeaway is that higher latency increases the amount of concurrent work the system must hold.

## 5. Memory: heap is only part of the picture

A Spring Boot/JVM process consumes multiple types of memory:

| Region | Examples | Key point to remember |
| --- | --- | --- |
| Java heap | DTOs, entities, JSON, collections, in-RAM sessions, caches | GC reclaims unreachable objects; objects still referenced will not be reclaimed |
| Java thread stacks | Stack frames and local variables of platform threads | Many platform threads increase off-heap memory overhead |
| Metaspace, code cache, and native runtime | Class metadata, JIT, JVM internals | Not governed by the heap `-Xmx` limit |
| Direct/native buffers and networking | Direct `ByteBuffer`, Netty/native I/O, TLS | Can grow even when the heap is not full |
| Memory used by container/process | Heap + native + stack + other allocations | Container can run out of memory before heap hits its ceiling |

For instance, `-Xmx512m` only caps the **maximum heap**; it does not mean the entire process uses only 512 MiB. When running in containers, budget for native, direct buffers, stacks, metaspace, GC, and headroom; monitor both container usage and JVM metrics.

Factors that increase memory consumption: reading large requests/responses fully into `byte[]`, fetching entire SQL result sets instead of paginating/streaming, unbounded caches, bloated sessions, retaining references in static collections, creating too many threads, or many concurrent requests each holding large buffers.

For example, 200 concurrent requests each holding a 2 MiB `byte[]` occupy roughly **400 MiB of payload**, excluding object overhead, copies, framework structures, and other memory regions. This is an illustrative calculation, not an actual heap forecast.

**Distinguishing issues**:
- Heap rising and dropping across GC cycles can be normal behavior.
- Heap after GC climbing steadily across multiple cycles can indicate retained objects, large caches/sessions, or leaks; inspect retained objects/heap dumps before concluding.
- High CPU from GC or allocation differs from high CPU from business computation.
- Container OOMKilled when heap is not full can stem from native/direct/thread stack memory or too small a container limit.

Reduce risk with pagination, streaming, body/upload size limits, bounded queues/caches, proper resource lifecycle management, and allocation profiling before adding RAM. Never use `System.gc()` as a root fix for memory leaks.

## 6. Sessions: state spanning multiple requests

HTTP itself does not require the server to store state between requests. A **Servlet HttpSession** is created when the application requests it; it does not have to exist for every request. Typically, the browser holds a session cookie (such as `JSESSIONID`) containing the **session identifier**; server-side data is stored in an appropriate session store, not entirely inside that cookie.

### 6.1. Lifecycle and architecture

1. The application creates/looks up a session when needed.
2. Subsequent requests carry the session ID; the server associates the ID with server-side state.
3. Sessions expire after inactivity or are invalidated; associated data/metadata must be freed according to store policy.
4. With multiple instances, sessions stored only in one instance's local memory break when requests route to another instance. Sticky sessions can mitigate node skew but do not replace shared state or recovery when a node is lost; Spring Session can use a centralized store when the architecture requires it.

Store **the minimum needed**: e.g., brief navigational state—do not stuff full entity graphs, large query result lists, non-serializable objects, or unnecessary sensitive data into sessions. When possible, keep API services stateless using appropriate authentication mechanisms and persist business state in dedicated data stores.

### 6.2. Security and scalability

- Enable `HttpOnly` and `Secure` cookies over HTTPS; select `SameSite` according to the actual authentication flow; regenerate/rotate session IDs upon login to protect against session fixation.
- Restrict session timeout and stored data size; define explicit logout/invalidation behavior.
- Do not treat sessions as a shared cache across all users: data scope, lifetime, replication count, and synchronization requirements differ.
- A Redis session store also has its own connections, memory, latency, and TTL: externalizing state does not eliminate resource costs.

## 7. Buffers: chunked processing to avoid holding everything in RAM

A **buffer** temporarily holds data being transferred or processed; a **cache** retains results for reuse in later requests. The two serve different purposes even though both use memory.

Common buffer locations: socket receive/send, Tomcat/Netty, request parsing, JSON serialization, JDBC fetch, file readers, response compression, and reverse proxies. **Multiple copies of data** can occur across these layers. Do not assume the framework always keeps the entire body in heap, nor assume streaming at one layer means every layer streams.

### 7.1. Standalone Java 17+ example: copying data via a fixed buffer

File **BoundedCopyDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "Hello, runtime!".getBytes(StandardCharsets.UTF_8);

        try (var input = new ByteArrayInputStream(payload);
             var output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4];
            int bytesRead;
            int totalBytes = 0;

            while ((bytesRead = input.read(buffer)) != -1) {
                output.write(buffer, 0, bytesRead);
                totalBytes += bytesRead;
            }

            System.out.println("Copied " + totalBytes + " bytes");
            System.out.println(output.toString(StandardCharsets.UTF_8));
        }
    }
}
~~~

Compile and run:

~~~bash
javac BoundedCopyDemo.java
java BoundedCopyDemo
~~~

Exact output:

~~~text
Copied 15 bytes
Hello, runtime!
~~~

**Explanation:** a 4-byte buffer is reused across multiple reads; the final data remains complete even when the last read returns fewer than 4 bytes. This is a small example illustrating the algorithm. Because `ByteArrayOutputStream` here holds **the entire output in RAM**, it is not a memory-saving streaming example for large payloads. In real applications, read from a stream source and write incrementally to a file or response output stream, enforce size limits, handle errors, and close resources properly.

### 7.2. Buffers, backpressure, and caches

If the writer writes slower than the reader reads, data accumulates: an unbounded queue or buffer can turn a slowdown into an OOM error. Strategies include: bounding buffers/queues, pausing reads when downstream is not ready (backpressure), limiting concurrent requests, enforcing timeouts, shedding excess load, and streaming results instead of collecting everything in memory.

Application caches (e.g., Spring Cache + Caffeine/Redis) should have **capacity limits, TTLs, cache keys, and invalidation policies**. Cache hits reduce downstream calls, but oversized caches or stale data introduce new problems. In Spring Boot, `@Cacheable` only works when caching is enabled, an appropriate `CacheManager`/provider is configured, and calls pass through the caching proxy/mechanism; self-invocation within the same bean may bypass the advice by default.

## 8. Controlled reference configuration

The following example applies to **Spring Boot 3.x using Spring MVC, embedded Tomcat, JDBC with HikariCP, and Actuator** (when the corresponding dependencies are present). These are **illustrative values**, not universal numbers for every application:

~~~yaml
server:
  tomcat:
    threads:
      max: 160
    max-connections: 3000
    mbeanregistry:
      enabled: true
  servlet:
    session:
      timeout: 20m

spring:
  datasource:
    hikari:
      maximum-pool-size: 16
      connection-timeout: 2000
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- **server.tomcat.threads.max**: ceiling for platform worker threads in standard Tomcat configuration; not total HTTP connections, and may not apply when virtual threads are enabled.
- **server.tomcat.max-connections**: number of connections Tomcat handles concurrently; does not indicate how many requests are actively executing Controllers.
- **server.tomcat.mbeanregistry.enabled**: enables the MBean registry so Spring Boot can collect the corresponding Tomcat metrics.
- **spring.datasource.hikari.maximum-pool-size**: maximum physical connections in the pool per instance; must be balanced against DB capacity and replica count.
- **spring.datasource.hikari.connection-timeout**: maximum wait time to acquire a connection from the pool; `2000` equals 2,000 ms in this example configuration.
- **server.servlet.session.timeout**: session inactivity expiration; not the HTTP keep-alive timeout.
- **spring.servlet.multipart.***: sets limits on multipart uploads, though it does not replace total body limits at proxies, gateways, or other ingestion points.
- **management.endpoints.web.exposure.include**: exposes selected actuator endpoints; in real environments, restrict access to management endpoints with appropriate network and security controls.

If using **WebFlux + Reactor Netty** or no JDBC, the Tomcat/Hikari settings do not govern that runtime. Identify your exact web stack, drivers, providers, and versions before tuning any property.

## 9. Measure and diagnose before optimizing

With Spring Boot Actuator and proper metrics integration, you can inspect available meters via **GET /actuator/metrics** when the endpoint is exposed. Examples of metrics/groups typically checked:

| Signal | What to read alongside it? | Diagnostic hint |
| --- | --- | --- |
| `http.server.requests`, p95/p99 latency in backend metrics | RPS, errors, routes, dependency latency | Which endpoint is slow, and when did it start increasing? |
| `tomcat.threads.busy` or Tomcat thread metrics when MBean registry is enabled | Thread limit, queue, CPU | Busy due to CPU or waiting on downstream? |
| `jdbc.connections.active` and `hikaricp.connections.*` group | Pool max/idle/pending, connection acquisition time | Slow queries, long transactions, or undersized pool? |
| `jvm.memory.used` / `jvm.memory.max`, GC metrics | Post-GC heap, allocation rate, container memory | Leak/retained objects, burst, or insufficient RAM? |
| `jvm.threads.live`, thread dump | Thread states, stack traces, deadlocks | Are many threads blocked on the same operation? |
| `jvm.buffer.*` and OS/container metrics | Direct buffer/native memory | Heap normal while RSS or container memory climbs? |
| Session/store, cache hit/miss/evictions reported by app/provider | Session count, state size, cache TTL | Unbounded state/cache or low hit rate? |

Exact meter names depend on Spring Boot, Micrometer, web stack, pool, enabled features, and registry. **Inspect the application's actual meter list** before building dashboards; do not assume every name in the table exists. `/actuator/metrics` is a diagnostic tool; for historical monitoring and alerting, export metrics to an appropriate metrics backend and keep management endpoints off public access.

Bottleneck isolation process:

1. **Isolate symptoms:** throughput (RPS), p50/p95/p99 latency, error/timeout rates, and onset time.
2. **Read resource budgets:** CPU, RSS/container memory, heap/GC, busy threads, inbound/outbound connections, DB pool active/pending, queues, and downstream latency.
3. **Correlate timestamps:** if DB pending climbs before HTTP latency climbs, examine transactions/DB; if GC rises alongside retained heap, analyze allocations or caches; if the event loop is blocked, capture thread dumps/profiling.
4. **Change one knob with a reason:** bound concurrency, fix queries/resource holding, add timeouts, stream data, or adjust resources reasonably. Then load-test and compare throughput, error rate, and p95/p99.
5. **Watch the whole system:** multiple replicas share incoming load but sum up connections to the DB, session store, cache, and downstreams.

### Three practical scenarios

**Scenario A — Slow API with low CPU.** Tomcat busy threads near the ceiling, high Hikari pending count, high DB query latency. Workers are likely waiting on the DB. Start with slow queries, locks/transactions, and connection lifetime; raising thread count may only grow the DB queue.

**Scenario B — Heap steady but container OOMKilled.** Inspect RSS, platform thread count, direct buffers, native memory, and container limit. Raising `-Xmx` can worsen RAM starvation for native memory.

**Scenario C — Adding replicas makes login sessions 'disappear'.** When sessions are stored in local memory, subsequent requests from the same client can hit another instance. Check session persistence/routing and shared-state requirements; do not mistake this for `JSESSIONID` deleting itself.

## 10. Checklist for safe runtime design

- Clearly identify **blocking Servlet vs. non-blocking WebFlux**, which server, and which client libraries are in use; never apply another stack's configuration.
- For every I/O path: know where timeouts live, when connections are borrowed/returned, connection/queue limits, and overload behavior.
- For threads/executors: know who creates them, max size, queue capacity, shutdown behavior, and rejection handling; avoid blocking the event loop.
- For memory: budget heap as well as native and container memory; cap payloads, caches, sessions, collections, and concurrent requests.
- For sessions: decide whether server-side state is truly needed; configure TTL, invalidation, secure cookies, and a multi-instance strategy.
- For buffers/caches: stream large data and bound buffers/queues; give caches eviction/TTL and rules on allowed data.
- For operations: have metrics, logs, traces, and load tests before/after changing limits; test slow downstreams, dropped connections, and traffic spikes.

**Remember:** a runtime is healthy when *every resource has a clear owner, lifecycle, bound, measurement signal, and release path*. A single request traverses multiple resources, so bottlenecks must be identified from evidence across the entire chain.

## References

- Spring Boot — Common Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Boot — Metrics and Actuator: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Caching: https://docs.spring.io/spring-boot/reference/io/caching.html