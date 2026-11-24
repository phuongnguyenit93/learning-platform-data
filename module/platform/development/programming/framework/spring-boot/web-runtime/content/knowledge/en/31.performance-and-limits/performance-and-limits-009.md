# Controlling Load from Slow Clients or Long-Lived Connections in Spring Boot

## 1. The Problem: Few Requests Can Still Exhaust the System

Learners usually measure server load in **requests/second** (RPS). In reality, a client sending very few requests can still hold resources for a long time: opening a TCP connection without finishing HTTP headers, uploading a body at a trickle, reading a response drop by drop, or keeping an SSE/WebSocket/long-poll connection open for hours.

Example:

~~~text
Client A: 1 request, finishes in 20 ms
Client B: opens TCP, sends headers in tiny slow fragments
Client C: POST 50 MB but sends only ~100 bytes/sec
Client D: GET /download but reads at 1 KB/sec
Client E: holds /events SSE open for 1 hour
                      |
                      v
         Reverse proxy / HTTP server
              | sockets, buffers
              | workers, event loops
              | request/response state
              v
           Spring Boot
              | executor + database connections
              | queued tasks + publisher subscriptions
              | heap/direct memory + file handles
~~~

Even if each client sends just one request, **concurrent connection count, connection lifetime, and per-request retained resources** can starve healthy clients. One well-known abuse vector is **Slowloris**: sending HTTP request headers extremely slowly to occupy connection slots. Variants include slow uploads, slow reads, or "legitimate but immortal" connections.

**The goal is not to close every long connection.** SSE, video/file streaming, large uploads over mobile networks, and WebSockets are legitimate needs. You need *per-phase* limits, overall resource budgets, and distinct policies per route type.

This lesson uses Spring Boot 3.3.x, Java 17+, the Servlet stack (Tomcat/Jetty/Undertow), and the reactive stack (Reactor Netty/WebFlux). Timeout and limit values below are **lab learning examples**, not safe production defaults for every workload.

## 2. Classifying Slow Clients and Why Each Differs

| Type | Behavior | Resources Held / Symptoms | Primary Control Layer |
| --- | --- | --- | --- |
| **Idle connection** | TCP open without sending a request or awaiting the next keep-alive request | Sockets, file descriptors, protocol state | Listener/connector idle/keep-alive timeout, connection cap |
| **Slow request headers** | Trickles request line/headers slowly | HTTP parser, connection slots, header memory | Edge client-header timeout, header size limit, connector timeout |
| **Slow request body** | POST/PUT trickling small byte chunks over a long time | Sockets, body buffers, parser, temp disk, workers | Body-read timeout/absolute deadline, max body size, proxy buffering |
| **Slow response reader** | Server builds response fast, client reads slowly | TCP send buffers, blocked writes, queued data, memory | Write timeout, bounded response buffers, proxy buffering or fail closed |
| **Long-running handler** | Business logic, DB, or downstream runs long | Worker threads, DB connections, futures | Business deadlines, cancellation, concurrency gates, DB/client timeouts |
| **Long-lived stream** | Legitimate SSE/WebSocket/long-poll | Sockets, subscriptions, publishers, per-client queues | Active stream quotas, heartbeats, TTL/re-auth, slow-consumer policies |
| **Reconnect storm** | Thousands of clients reconnecting after deploy or outage | Handshakes, authentication, CPU, allocations | Connection/rate limits, jitter, backoff, draining |
| **HTTP/2 multiplexing** | Multiple streams/requests over one TCP connection | Concurrent streams + per-stream state | H2 stream limits, route concurrency, memory budgets |

**Never equate** connection idle timeout with in-progress request duration: HTTP/1.1 `keepAliveTimeout` typically measures how long to wait for the **next** request on a connection whose previous request finished; it is not a deadline for an active download, nor a cap on reading a full upload body.

**Never equate** request timeout with read idle timeout: a client can drip one byte just before the idle timeout expires, keeping the request alive indefinitely. To stop body trickling, enforce an **absolute deadline, minimum read rate, total size cap**, or edge resource limits. A single "idle timeout" never bounds total duration.

## 3. Resources That Exhaust Before CPU Hits 100%

~~~text
OPEN SOCKETS ------> File descriptors / kernel memory
REQUEST PARSERS ---> Header buffers / memory
HTTP/1 worker -----> Servlet threads / executor queue
SLOW RESPONSE -----> Socket send buffer / blocked write
UPLOAD BODY -------> Heap, direct memory, temp files, disk
DB WORK -----------> JDBC pool / transactions / row locks
STREAMS -----------> Subscribers, schedulers, buffers, topic slots
METRICS/LOGS ------> Label cardinality, queues, file I/O
~~~

This explains why a system at low CPU can time out on every new request: 200 platform threads stuck writing to slow readers, a 30-connection DB pool held across long transactions, or exhausted file descriptors hitting `ulimit`. **The fix is never simply bumping `maxThreads` to 2,000.** That merely shifts the bottleneck to memory, the DB, or pod stability, worsening tail latency.

### An Approximate Capacity Model

By Little's Law for a stable system:

\[
L = \lambda W
\]

Where:

- `L`: average concurrent requests in the system.
- `λ`: requests/second.
- `W`: average time a request occupies the system, in seconds.

For example, 100 requests/second finishing in 0.1 s on average keeps ~10 active requests. At the same rate, if each request holds resources for 10 s, you hold ~**1,000** concurrent requests. This is a mathematical illustration, **not** a guarantee under bursts, queues, or slow clients; tail behavior is even harsher.

With 10,000 SSE connections sending just 1 message every 30 s, new-request RPS looks tiny, yet the server still needs sockets, TLS state, subscriptions, memory, and network capacity for all 10,000.

## 4. Five Defensive Layers Working Together

~~~text
Internet
   |
   | 1. Edge/CDN/WAF:
   |    TLS, header/body timeouts, client rates, concurrent connections
   v
Reverse proxy / load balancer
   |
   | 2. Proxy:
   |    request buffering, response buffering, upstream timeouts
   v
Spring embedded server
   |
   | 3. Connector:
   |    max connections, keep-alive, parser/header/body limits
   v
Spring Security + Controller
   |
   | 4. Application:
   |    per-user quotas, concurrency limits, 429/503, deadlines
   v
Service / DB / brokers
      5. Downstream:
         pool limits, timeouts/circuit breakers, bounded queues,
         cancellation, telemetry, graceful shutdown
~~~

No single layer replaces the others:

- Proxies cap client request rates, yet **do not know** which order belongs to which tenant.
- Connectors bound sockets, yet do not know which routes legitimately stream for an hour.
- The app can cap active SSE streams, yet **cannot see** a client trickling partial headers before parsing completes.
- DB pools cap SQL connections, yet cannot stop sockets from piling up.
- Downstream circuit breakers do not stop slow readers draining a file already in RAM.

Design around **bounded resources + per-phase timeouts + explicit overload responses + observability**.

## 5. Timeout Types and Their Effective Scopes

| Timeout / Deadline | Starts When | On Expiration | Does Not Necessarily Control |
| --- | --- | --- | --- |
| TLS handshake | TLS connection starts | Closes handshake/socket | App request processing time |
| Request-line/header timeout | TCP accepted / reading headers | Closes connection if headers incomplete | Total response duration |
| Request-body read idle timeout | Reading body bytes | Closes if no new bytes arrive for too long | A client dripping 1 byte steadily forever |
| Absolute body deadline | Body reception starts | Cancels even if bytes keep arriving | Response streaming after body finishes |
| HTTP keep-alive timeout | Waiting for next HTTP request | Closes idle persistent connection | Currently executing HTTP request |
| App work deadline | Business operation starts | Fails/cancels per policy | Automatic network/TCP receive timeout |
| Downstream client timeout | Calling DB/HTTP/broker | Fails/times out at dependency | Slow client reading our response |
| Response write idle timeout | Server writing response to client | Closes when client stops reading/progressing | Total lifetime of an SSE stream sending heartbeats |
| Stream absolute TTL | Connection/subscription opens | Closes stream per policy, forces re-auth/resume | Active connection count if no quota exists |
| Proxy upstream read timeout | Reading response from Spring | Gateway closes if Spring sends nothing between reads | Client trickling headers slowly to the edge |
| Queue wait timeout | Task enters executor queue | Rejects/fails if no slot frees up | Socket connection cap |

**NGINX note:** `proxy_read_timeout` bounds the gap **between two reads from upstream**, not total request duration; `send_timeout` bounds gaps between writes to the client. Hence an SSE stream sending heartbeats stays alive indefinitely even with `proxy_read_timeout=60s` whenever heartbeats arrive more frequently.

## 6. Tomcat: Connection Limits, Worker Threads, and Keep-Alive

Spring Boot `spring-boot-starter-web` defaults to embedded Tomcat. Spring Boot 3.3 exposes these properties:

~~~properties
server.port=8080

# Values below are ONLY for lab load experiments.
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.threads.max=20
server.tomcat.threads.min-spare=4

# 10s waiting for the request line after accept; NOT total request deadline.
server.tomcat.connection-timeout=10s

# Only waits for the NEXT HTTP request after the previous one completes.
server.tomcat.keep-alive-timeout=10s
server.tomcat.max-keep-alive-requests=50

# Cap HTTP headers and multipart bodies per use case.
server.max-http-request-header-size=8KB
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
~~~

**Read each property accurately:**

- `server.tomcat.max-connections`: maximum connections accepted and processed concurrently by the connector; Tomcat NIO manages socket acceptance/queueing. **Not** a requests/second limit.
- `server.tomcat.accept-count`: requested backlog length once connector capacity fills; the OS may adjust or ignore the exact number. When full, clients get TCP connection refused or timeouts rather than guaranteed HTTP 503.
- `server.tomcat.threads.max`: max platform worker threads in traditional thread-pool mode; **not equal to `maxConnections`**. An idle keep-alive socket waiting for the next request holds a connection without holding a request worker thread continuously.
- `server.tomcat.connection-timeout`: time to wait after accepting a connection for the request URI line to arrive; Tomcat has separate socket/read behaviors. **Does not create a total response deadline.**
- `server.tomcat.keep-alive-timeout`: wait time for the next request. Setting `-1` disables this timeout and is easily misused.
- `server.tomcat.max-keep-alive-requests`: max HTTP requests served on one persistent connection before closing; neither connection limit nor stream lifetime.
- `server.max-http-request-header-size`: prevents huge headers from bloating parser buffers; does not stop slow body trickles.
- Multipart limits: cap multipart byte sizes rather than upload duration or transfer rate; non-multipart requests need separate edge/app size limits.

**Virtual threads note:** on Java 21+ with Spring Boot virtual threads enabled, several `server.tomcat.threads.*` properties stop acting like platform-thread caps. This lab uses Java 17 without virtual threads. Virtual threads also **do not cap sockets or DB connections**, so concurrency quotas remain essential.

### 6.1. Tomcat Upload Body Timeouts

Tomcat's connector offers advanced options `disableUploadTimeout` and `connectionUploadTimeout`. In Tomcat 10.1, `disableUploadTimeout=true` by default, meaning no separate upload timeout applies and regular connector timeout rules govern. If you enable a distinct upload timeout, configure the connector explicitly and test it—never claim `server.tomcat.connection-timeout=10s` guarantees "every upload finishes within 10 seconds".

On slow mobile links, overly aggressive upload timeouts break legitimate users; overly loose ones widen DoS exposure. Combine **body size caps**, **minimum rate / absolute deadlines** at the reverse proxy when fighting trickles, and **concurrent upload limits** into the backend.

### 6.2. Threads and Queues Are Not a Complete Overload Policy

If all 20 worker threads are busy, bumping `accept-count` from 20 to 5,000 merely makes more clients wait: p99 spikes, retries multiply, and memory/connection pressure climbs. Add **admission control** in the app ahead of DB-heavy work and fail fast with 429 or 503 under overload.

**Never assume `max-connections=100` returns HTTP 503 to the 101st client.** TCP backlogs and socket acceptance operate at the transport layer; HTTP statuses cannot be produced before a request is read and dispatched.

## 7. Jetty: Connection Idle, Max Connections, and Thread Pool

When replacing Tomcat with `spring-boot-starter-jetty` (excluding `starter-tomcat`), Spring Boot 3.3 provides:

~~~properties
# ONLY for apps actually running embedded Jetty.
server.jetty.connection-idle-timeout=20s
server.jetty.max-connections=100
server.jetty.threads.max=40
server.jetty.threads.min=4
server.jetty.threads.idle-timeout=60s
server.jetty.threads.max-queue-capacity=100
server.max-http-request-header-size=8KB
~~~

- `server.jetty.connection-idle-timeout`: connection idle timeout; **not** a total deadline for a business task.
- `server.jetty.max-connections`: maximum connections Jetty accepts and handles simultaneously. In Boot 3.3 it defaults to `-1` (no Jetty-level cap); coordinate with proxy, OS, and worker budgets.
- `server.jetty.threads.max`: max threads in Jetty's thread pool; neither TCP client count nor unlimited free tasks.
- `server.jetty.threads.max-queue-capacity`: caps the thread pool queue, preventing unbounded worker queueing without replacing per-route admission control.
- `server.jetty.threads.idle-timeout`: **thread idle** timeout, distinct from `connection-idle-timeout`. It governs reclaiming idle pool threads, not disconnecting idle clients.

Jetty also involves selectors, acceptors, HTTP/2, and connection factories; deep tuning requires profiling on Boot-compatible Jetty versions. Never paste Tomcat `server.tomcat.max-connections` into a Jetty app expecting it to work.

**Warning:** configuring an overly short queue in a lab can starve Jetty of workers for internal tasks; monitor health, liveness, and error logs, sizing from Jetty's concurrency model rather than guessing.

## 8. Undertow: I/O Threads, Worker Threads, and `no-request-timeout`

With `spring-boot-starter-undertow` (Tomcat excluded), Spring Boot 3.3 offers:

~~~properties
# ONLY for embedded Undertow.
server.undertow.no-request-timeout=20s
server.undertow.threads.io=2
server.undertow.threads.worker=16
server.max-http-request-header-size=8KB
server.undertow.max-http-post-size=6MB
~~~

Distinctions:

- `server.undertow.no-request-timeout` bounds how long a **connection sits idle without processing a request** before closing. It does not require an active upload or download to finish in 20 seconds.
- `server.undertow.threads.io` runs latency-sensitive selector/I/O work; **never block them** with DB/JDBC calls or heavy CPU tasks.
- `server.undertow.threads.worker` sets worker threads Undertow uses for dispatched blocking work; not a socket connection quota.
- `server.undertow.max-http-post-size` caps POST bodies per Undertow semantics; Boot 3.3 defaults to `-1B` (unlimited at this setting), so production needs explicit upload and proxy size caps.
- `server.undertow.options.server.*` and `server.undertow.options.socket.*` map to advanced Undertow/XNIO options. Only use keys verified in documentation; avoid guessing an undocumented `server.undertow.read-timeout` property in Boot 3.3.

Undertow uses event-driven I/O. Blocking Servlet handlers dispatch onto worker threads, yet neither I/O threads nor N concurrent long-polls are free in memory or threads. Monitor I/O loop latency, worker queues, and active connections when tuning.

## 9. Reactor Netty: Channel Idle and Read/Response Timeouts

When only `spring-boot-starter-webflux` is present, Spring Boot 3.3 normally selects Reactor Netty. Boot 3.3 properties:

~~~properties
server.port=8082

# Only applies if the actual HTTP server is Reactor Netty.
server.netty.idle-timeout=30s
server.netty.connection-timeout=10s
server.netty.max-keep-alive-requests=100
server.netty.max-initial-line-length=4KB
server.max-http-request-header-size=8KB
~~~

Meanings:

- `server.netty.idle-timeout`: idle timeout on a **Netty channel**; Boot documents the default as **infinite** when unset. It is neither a total request deadline nor a minimum byte rate.
- `server.netty.connection-timeout`: Netty channel/connection timeout; **never treat it as a promise that body uploads or responses finish within 10 seconds**.
- `server.netty.max-keep-alive-requests`: max requests per persistent connection; defaults to unlimited.
- `server.netty.max-initial-line-length` and `server.max-http-request-header-size`: bound parser allocations and headers. Boot notes header-cap semantics differ across servers—Netty applies limits per individual header rather than summing request line + all headers like Tomcat.

**Important:** an SSE response emitting regular heartbeats can remain open indefinitely despite `server.netty.idle-timeout`. To enforce a **max stream lifetime**, set explicit deadlines at the route, broker, or application lifecycle layer; channel idle timeouts are not business TTLs.

### 9.1. Programmatic Netty Server Tuning

Example config class for **WebFlux + Netty**:

~~~java
package demo.reactive;

import java.time.Duration;
import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NettyIdleConfig {
    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
            nettyServerCustomizer() {
        return factory -> factory.addServerCustomizers(
                server -> server.idleTimeout(Duration.ofSeconds(30)));
    }
}
~~~

`NettyReactiveWebServerFactory` lets you customize Reactor Netty's `HttpServer`. This configures idle timeout via `HttpServer.idleTimeout`. **Do not set conflicting values in both properties and programmatic customizers** expecting both to apply; test the final runtime behavior. This remains only an idle/channel policy—it does not bound stream counts, bytes/sec, or business duration.

### 9.2. Reactor Netty Does Not Automatically Cure Unbounded Hot Publishers

WebFlux provides non-blocking I/O and Reactive Streams backpressure, yet if a source emits faster than clients consume (e.g., 10,000 events/s over SSE to mobile devices), you must check:

- Is the `Flux` source cold or hot? A hot `Sinks.Many` or broker stream needs an explicit overflow policy.
- Are per-client buffers bounded? Unbounded `onBackpressureBuffer` risks OOM.
- Can you **drop/coalesce to latest state**, or must every event be durably persisted?
- On downstream cancellation, does the subscription free DB/broker consumers and connections?
- Is CPU-heavy or legacy blocking I/O running on the Reactor event loop? Use reactive drivers or offload blocking calls safely.
- Are concurrent stream quotas per tenant/user/node and memory budgets enforced?

**Reactive backpressure does not guarantee exactly-once delivery, replace bandwidth budgets, or automatically bound memory for every publisher.**

## 10. Reverse Proxy NGINX: Stop Slow Clients Early

Common architecture:

~~~text
Internet clients
      |
      v
NGINX / ingress / CDN
      | client_header_timeout
      | client_body_timeout
      | send_timeout
      | keepalive_timeout
      | limit_conn / limit_req
      |
      | proxy_request_buffering
      | proxy_buffering
      | proxy_connect/read/send_timeout
      v
Spring Boot
~~~

Benefit: the proxy absorbs and filters slow clients **before they tie up backend application resources**. Still, the proxy has finite sockets, temp disk, worker connections, and cache memory—never treat it as an infinite buffer.

### 10.1. NGINX Snippet with Per-Phase Limits

This is an **example snippet inside `nginx.conf`** targeting a Spring upstream on `127.0.0.1:8080`. Never alter production proxies without verifying network topology, CDNs, ingress layers, and legitimate user behavior:

~~~nginx
http {
    # Per-IP limits: production requires trusted real-ip configuration.
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;
    limit_req_zone $binary_remote_addr zone=req_per_ip:10m rate=10r/s;

    # Slow headers are handled before routing to the app.
    client_header_timeout 10s;
    client_body_timeout 15s;
    keepalive_timeout 20s;
    send_timeout 20s;

    server {
        listen 8088;

        location /api/ {
            proxy_pass http://127.0.0.1:8080;
            proxy_connect_timeout 5s;
            proxy_send_timeout 20s;
            proxy_read_timeout 30s;

            # Buffer client body at the proxy before sending upstream.
            proxy_request_buffering on;
            # Buffer normal responses to isolate slow readers somewhat.
            proxy_buffering on;

            limit_conn conn_per_ip 4;
            limit_conn_status 429;
            limit_req zone=req_per_ip burst=15 nodelay;
            limit_req_status 429;
        }

        location /events {
            proxy_pass http://127.0.0.1:8080;
            proxy_read_timeout 75s;
            proxy_buffering off;

            # Long-lived streams get a separate budget.
            limit_conn conn_per_ip 2;
            limit_conn_status 429;
        }
    }
}
~~~

**Critical details:**

- `client_header_timeout`: bounds reading request headers. Distinct from upload body timeout and keep-alive.
- `client_body_timeout`: measures the wait **between two consecutive body reads**, not a total body deadline. A client trickling bytes steadily at a glacial pace can bypass an idle-based timeout.
- `send_timeout`: interval between successive response writes to the client; catches stalled readers, not total transfer duration.
- `proxy_connect_timeout`: time to establish a connection to the Spring upstream.
- `proxy_send_timeout`: gap between successive request writes to upstream.
- `proxy_read_timeout`: gap **between successive reads from upstream** (NGINX defaults to 60 s), not a total handler deadline.
- `proxy_request_buffering on`: proxy receives the full request body before forwarding to Spring, isolating slow uploads from the app **while shifting temp-disk and edge-memory pressure to the proxy**. When turned off, Spring sees slow trickle uploads directly and needs its own bounds.
- `proxy_buffering on`: proxy reads upstream responses faster than slow clients and buffers in memory/temp files, freeing app writers sooner at the cost of proxy memory/disk.
- `proxy_buffering off` for SSE delivers events immediately without waiting to fill a buffer, exposing the backend more directly to slow clients.
- `limit_conn` limits connections/requests per key only **after headers have been read**, so it does not stop byte-by-byte partial headers. Pair it with `client_header_timeout`.
- `limit_req` limits **request arrival rate**, not long-lived active stream count; `limit_conn` and app per-user quotas govern active streams.

**NGINX HTTP/2 & HTTP/3 nuance:** under `limit_conn`, each concurrent HTTP/2 or HTTP/3 request counts as a connection in the module's accounting even when sharing one underlying TCP/QUIC socket. Never assume "one socket = one stream".

### 10.2. Choosing Proxy Buffering by Route Type

| Route | Request Buffering | Response Buffering | Explanation |
| --- | --- | --- | --- |
| Short JSON API | Usually on | Usually on | Shields upstream from slow clients; prevents unbounded queueing |
| Large upload | Buffered with disk quotas or controlled streaming | Usually not central | Enforce file size, content length, disk quotas, upload slots/timeouts |
| File download | Not central | On or streaming per size/latency/memory | Guard against slow readers and full temp disks |
| SSE | Small GET body | **Off** response buffering | Flush events and heartbeats promptly |
| WebSocket | Distinct from HTTP response buffering | Dedicated upgrade/tunnel config | Ping/pong, idle/reconnect, quotas, handshake |

Cutting too aggressively breaks legitimate users on weak connections; leaving timeouts too loose invites resource starvation. Define SLOs for valid users, measure p95/p99 upload/read latencies, and tune per endpoint.

### 10.3. Per-IP Limits Are Not Per-User Limits

NATs and corporate proxies put thousands of users behind one IP. Pure `limit_conn perip 2` blocks valid users. Conversely, attackers distribute IPs or spoof `X-Forwarded-For` headers.

Better design:
1. At the edge: apply IP/ASN/bot/rate controls across a clear trust boundary, configuring real-IP extraction only from **trusted proxies**.
2. In Spring after authentication: enforce **per-user, per-tenant, per-API-key, and per-route** quotas.
3. In infrastructure: cap connections/streams per pod and cluster-wide so one node never hotspots.
4. When rejecting: return appropriate statuses and `Retry-After`, count rejections, and never log credentials.

## 11. Admission Control: Fail Fast Instead of Queueing Forever

Three independent decisions:

1. **Rate limiting:** how many requests are permitted over a time window? Stops bursts and abuse.
2. **Concurrency limiting:** how many requests or streams may **run simultaneously**? Protects long-held resources.
3. **Resource/budget limiting:** how many bytes, seconds, CPU, DB connections, or queue slots may a request consume?

A client opening 1 SSE stream every 60 minutes **never trips a rate limit**, yet a million such clients exhaust sockets. A single 5 GB download stays under RPS limits while requiring byte, duration, and concurrency budgets. Dropping `@RateLimiter` onto a controller is never enough by itself.

### 11.1. 429 or 503?

- **429 Too Many Requests**: best when a specific **client or tenant exceeds its rate/quota**.
- **503 Service Unavailable**: best when the **server itself is out of capacity** and temporarily refuses work.
- **413 Content Too Large**: when payload size exceeds limits.
- **408 Request Timeout**: when the server did not receive the complete request in time—though many proxies/servers simply close TCP or return another status rather than guaranteeing 408.
- **504 Gateway Timeout**: typically emitted by a reverse proxy/gateway waiting too long on an upstream.

Pair `Retry-After` with 429/503 to suggest retry timing, alongside **exponential backoff + jitter** and client retry budgets; never auto-retry non-idempotent POSTs without idempotency keys/contracts. Rejected streams should also back off before reconnecting.

### 11.2. Bounded Queues

An unbounded queue converts overload into unbounded waiting. For `ThreadPoolExecutor` or async tasks:

~~~text
Max active = 20
Queue = 40
Beyond capacity --> Reject fast
~~~

Size queues to latency SLOs. `ThreadPoolExecutor` needs a bounded queue and observable rejection policy; with Spring's `ThreadPoolTaskExecutor`, remember `queueCapacity` vs `maxPoolSize` semantics: **until the queue fills, the pool does not grow to `maxPoolSize`**.

**Never block request threads in unbounded `semaphore.acquire()`**: that turns a concurrency gate into a stalled thread queue. Use `tryAcquire()` (or `tryAcquire` with a tiny SLO-aligned timeout) and fail fast with HTTP 429/503 when no slot is free.

## 12. Project A: Servlet MVC + Bounding Active SSE via `Semaphore`

This example provides a **runnable Java 17+ Spring Boot project**:

- `GET /health` responds immediately.
- `GET /work` simulates 200 ms of work, max 2 concurrent requests. Excess receives **503**.
- `GET /events` streams 5 SSE ticks then `done`, max 2 concurrent streams. Stream completion, timeout, or disconnect must **release the permit exactly once**.
- Uses a tiny shared thread pool to show real resource cost; avoid blocking `send` schedulers for huge stream counts in production.

### 12.1. Structure

~~~text
slow-client-mvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/slowmvc/SlowMvcApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/slowmvc/SlowMvcTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'slow-client-mvc'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
server.tomcat.max-connections=100
server.tomcat.accept-count=20
server.tomcat.threads.max=20
server.tomcat.connection-timeout=10s
server.tomcat.keep-alive-timeout=10s
spring.mvc.async.request-timeout=20s
server.max-http-request-header-size=8KB
~~~

Connection settings are illustrative; SSE sets its own 15-second timeout so a 5-second stream completes comfortably. Tomcat `max-connections` is distinct from the app's SSE permit cap.

### 12.2. Full Java Source

`src/main/java/demo/slowmvc/SlowMvcApplication.java`:

~~~java
package demo.slowmvc;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@SpringBootApplication
public class SlowMvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowMvcApplication.class, args);
    }

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService streamScheduler() {
        return Executors.newScheduledThreadPool(2);
    }
}

@RestController
class SlowMvcController {
    private final ScheduledExecutorService scheduler;

    // Two separate budgets: CPU/business work vs long-lived streams.
    private final Semaphore workSlots = new Semaphore(2, true);
    private final Semaphore streamSlots = new Semaphore(2, true);

    SlowMvcController(ScheduledExecutorService scheduler) {
        this.scheduler = scheduler;
    }

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/work")
    Map<String, String> work() throws InterruptedException {
        if (!workSlots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "work is busy");
        }
        try {
            Thread.sleep(200); // Lab simulation only.
            return Map.of("status", "done");
        } finally {
            workSlots.release();
        }
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter events() {
        if (!streamSlots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "too many active SSE streams");
        }

        SseEmitter emitter = new SseEmitter(15_000L);
        AtomicInteger counter = new AtomicInteger();
        AtomicBoolean cleaned = new AtomicBoolean(false);
        AtomicReference<ScheduledFuture<?>> taskRef =
                new AtomicReference<>();

        Runnable cleanup = () -> {
            if (cleaned.compareAndSet(false, true)) {
                ScheduledFuture<?> task = taskRef.get();
                if (task != null) {
                    task.cancel(false);
                }
                streamSlots.release();
            }
        };

        emitter.onCompletion(cleanup);
        emitter.onTimeout(cleanup);
        emitter.onError(error -> cleanup.run());

        Runnable publish = () -> {
            int n = counter.incrementAndGet();
            try {
                emitter.send(SseEmitter.event()
                        .id("mvc-" + n)
                        .name("tick")
                        .data(Map.of("sequence", n)));

                if (n >= 5) {
                    emitter.send(SseEmitter.event()
                            .name("done").data("finished"));
                    emitter.complete();
                    cleanup.run();
                }
            } catch (IOException disconnected) {
                // Servlet container/Spring handles async write errors.
                // Stop publisher; do not call completeWithError on IOException.
                cleanup.run();
            } catch (RuntimeException unexpected) {
                cleanup.run();
                emitter.completeWithError(unexpected);
            }
        };

        try {
            ScheduledFuture<?> task = scheduler.scheduleAtFixedRate(
                    publish, 1, 1, TimeUnit.SECONDS);
            taskRef.set(task);
        } catch (RuntimeException schedulingFailed) {
            cleanup.run();
            throw schedulingFailed;
        }

        return emitter;
    }
}
~~~

### 12.3. Why Does This Example Separate Two Load Types Properly?

- `workSlots.tryAcquire()` provides **non-blocking admission** for synchronous work. When full, HTTP 503 fails fast. `finally` releases even on errors or `InterruptedException`, preventing permit leaks. Because `/work` is synchronous, `try/finally` matches the business work lifetime.
- `streamSlots.tryAcquire()` bounds **SSE subscriptions** on the node, independent of `maxConnections=100` so normal requests retain headroom.
- `SseEmitter(15_000L)` sets the **Servlet async timeout**. If a client lingers too long, `onTimeout` cleans up the producer and permit, though exact timeout firing follows container async lifecycle timing.
- `onCompletion`, `onTimeout`, and `onError` may run on different threads; `AtomicBoolean` guarantees **exactly-once release**, never inflating semaphore permits past the initial count.
- `IOException` on write does not call `completeWithError` redundantly; Spring docs explain that the container manages async error notifications when clients disconnect mid-write.
- `ScheduledExecutorService` is a shared Spring-managed bean shut down with the context—**never spawn a new executor per client**.
- `emitter.send` in MVC can **block** when receivers read slowly. The lab caps at 2 streams; production needs bounded write workers, slow-write budgets per client, and bounded event queues rather than a tiny scheduler across thousands of streams.
- Once the server emits `done`, it calls `complete()`. Browser `EventSource` clients must call `close()` upon receiving `done`, otherwise `EventSource` automatically reconnects after stream completion.
- In this example, streams emit dummy non-personalized data. Production must authenticate users/tenants before issuing permits or emitting events, and re-check authorization on long-lived streams.

**Intentional lab limitation:** this semaphore is per-process; 4 Spring nodes yield 8 total SSE slots without a global quota. Nor does it protect TCP accept or slow partial HTTP headers/bodies—that belongs to connectors and proxies.

### 12.4. Starting and Observing

With a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Without a wrapper, generate one or run `gradle bootRun` with a compatible Gradle version. Once running:

~~~bash
curl -i http://localhost:8080/health
~~~

Expected HTTP 200 body:

~~~json
{"status":"ok"}
~~~

~~~bash
curl -i http://localhost:8080/work
~~~

When a slot is free, HTTP 200:

~~~json
{"status":"done"}
~~~

When more than 2 `/work` requests overlap concurrently, excess requests get **503**. Exact status counts in concurrent shell bursts depend on OS/network scheduling—never promise exact counts without synchronizing start times.

### 12.5. SSE and Active Stream Limits

Open **three terminals** within a couple of seconds:

Terminal 1:

~~~bash
curl -N -i http://localhost:8080/events
~~~

Terminal 2:

~~~bash
curl -N -i http://localhost:8080/events
~~~

Terminal 3 (while the first two streams are still alive):

~~~bash
curl -N -i http://localhost:8080/events
~~~

The first two streams receive HTTP 200 `text/event-stream` emitting one event per second:

~~~text
id:mvc-1
event:tick
data:{"sequence":1}

id:mvc-2
event:tick
data:{"sequence":2}

...
event:done
data:finished

~~~

Whitespace formatting around colons/serialization depends on codecs/framework; the **logical** event sequence is 5 ticks and 1 `done`. The third request receives **503** while both permits are held. After ~5 seconds, the first two streams finish and new requests succeed again.

Press `Ctrl+C` to close a stream early. The server may not detect the disconnect immediately because Servlet streaming typically notices on the next write; once `IOException`/callback fires, `cleanup` releases the permit. **Never assert millisecond-instant release after `Ctrl+C` across every OS and proxy.**

### 12.6. Simulating a Slow Response Reader

To simulate a slow reader with cURL:

~~~bash
curl --limit-rate 512 --max-time 5 -o /dev/null \
  http://localhost:8080/events
~~~

`--limit-rate 512` throttles cURL's receive rate; `--max-time 5` cuts off after ~5 s. Because this lab's SSE payload is tiny, it **probably won't** fill the TCP send buffer or block `send`; observing blocked writes/queue growth requires larger streamed bodies.

Never simulate Slowloris with thousands of sockets against targets you do not own. Keep all trickle testing strictly on **localhost or owner-approved staging** with small client counts and short runs.

## 13. MVC Tests: HTTP 200, `asyncStarted`, and Over-Quota Behavior

In the MVC project, create `src/test/java/demo/slowmvc/SlowMvcTest.java`:

~~~java
package demo.slowmvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SlowMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void healthIsResponsive() throws Exception {
        mvc.perform(get("/health"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"ok\"}"));
    }

    @Test
    void eventsBeginAsyncProcessing() throws Exception {
        mvc.perform(get("/events").accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.slowmvc.SlowMvcTest
~~~

These basic checks do not measure throughput or slow readers. To test the 2-stream quota deterministically, use a real HTTP integration test that holds **two open, subscribed SSE streams**, confirms both are registered, sends a third request expecting 503, and then cancels to verify capacity recovers. Firing 3 sequential requests can flake if earlier streams finish first.

**`MockMvc` does not replace network tests:** header/body trickling, proxy buffering, TCP flow control, disconnects, and keep-alive timeouts must be tested against a real HTTP server.

## 14. Project B: WebFlux Reactor Netty with a `WebFilter` Capping Active Responses

WebFlux uses **non-blocking I/O**, yet an open SSE stream still consumes an active HTTP response/subscription and needs a quota.

This example uses a **`WebFilter`** to cap concurrent SSE responses at **2**. The key lesson is releasing the permit in `Mono<Void>.doFinally(...)` when the response **completes, errors, or cancels**, rather than releasing right after the controller returns `Flux`. Releasing too early is a classic bug when porting Servlet `try/finally` patterns to reactive code.

### 14.1. Structure

~~~text
slow-client-reactive/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/reactive/SlowReactiveApplication.java
    │   ├── java/demo/reactive/StreamLimitWebFilter.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/reactive/SlowReactiveTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'slow-client-reactive'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8082
server.netty.idle-timeout=30s
server.netty.max-keep-alive-requests=100
server.max-http-request-header-size=8KB
~~~

### 14.2. Reactive HTTP Controller

`src/main/java/demo/reactive/SlowReactiveApplication.java`:

~~~java
package demo.reactive;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class SlowReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(SlowReactiveApplication.class, args);
    }
}

record Tick(long sequence, String state) { }

@RestController
class ReactiveStreamController {

    @GetMapping("/health")
    Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<Tick>> events() {
        Flux<ServerSentEvent<Tick>> ticks =
                Flux.interval(Duration.ofSeconds(1))
                        .take(5)
                        .map(index -> {
                            long n = index + 1;
                            return ServerSentEvent
                                    .<Tick>builder(
                                            new Tick(n, "running"))
                                    .id("flux-" + n)
                                    .event("tick")
                                    .build();
                        });

        return ticks.concatWith(Mono.just(
                ServerSentEvent.<Tick>builder(
                        new Tick(0, "finished"))
                        .event("done")
                        .build()));
    }
}
~~~

`Flux.interval` creates a per-subscription publisher without calling `Thread.sleep` or `block()` on Netty event loops. `take(5)` bounds the event count and `done` ends the finite stream. This is purely illustrative and does not implement `Last-Event-ID` replay on reconnect.

### 14.3. `WebFilter` Enforcing Active-Stream Quotas

`src/main/java/demo/reactive/StreamLimitWebFilter.java`:

~~~java
package demo.reactive;

import java.util.concurrent.Semaphore;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class StreamLimitWebFilter implements WebFilter {

    private final Semaphore permits = new Semaphore(2, true);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

        if (!"/events".equals(path)) {
            return chain.filter(exchange);
        }

        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                exchange.getResponse()
                        .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
                exchange.getResponse().getHeaders()
                        .set(HttpHeaders.RETRY_AFTER, "3");
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange)
                    .doFinally(signal -> permits.release());
        });
    }
}
~~~

Explanation:

1. `WebFilter` is WebFlux's reactive filter, distinct from Servlet `OncePerRequestFilter`.
2. `/health` passes straight through without taking a stream permit.
3. `Mono.defer` acquires a permit **only when the HTTP chain is subscribed**, preventing eager side effects during assembly.
4. When both permits are taken, the server returns HTTP **503** with `Retry-After: 3` without starting the stream.
5. Once granted, `chain.filter(exchange)` completes only when the **response pipeline** finishes; `doFinally` runs on completion, error, or cancellation to release the permit.
6. `Semaphore` is a **single-instance** quota; multi-pod deployments require gateway or distributed per-user quotas.
7. This pipeline does not yet enforce bytes/sec quotas, event-backlog limits, or tenant authorization—add those in real systems.

**`WebFilter` warning:** in real apps with authentication filters and multiple stream routes, enforce quotas **after resolving a trusted principal**, or separate anonymous edge quotas from per-user quotas. Never trust client-supplied `X-User-Id` headers. Path-based filtering here is strictly illustrative.

### 14.4. Running the Test

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Open two connections:

~~~bash
curl -N -i http://localhost:8082/events
~~~

Opening a third request before the first two complete returns 503 with `Retry-After: 3`. Once a client disconnects or a stream completes, `doFinally` releases capacity.

**Pressing `Ctrl+C` does not guarantee same-millisecond server detection:** cancellation propagates across TCP/HTTP lifecycles. Test over reasonable intervals and watch active stream/memory gauges rather than timing from your keystroke.

### 14.5. WebFlux Streams Have Backpressure, Yet Still Need Bounded Sources

`Flux.interval` emits at a fixed cadence. In production, when downstream lags, backpressure/cancellation applies, while hot broker streams or tick schedulers can have different overflow semantics. Never assume WebFlux safely buffers millions of events in RAM.

For latest-state notifications, use a **coalescing/latest** policy. For zero-loss transactions, persist events durably and resync/replay by ID—never attach `onBackpressureDrop` carelessly and lose business data.

## 15. WebFlux Tests: Verifying Endpoints and Lifecycle

Create `src/test/java/demo/reactive/SlowReactiveTest.java`:

~~~java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SlowReactiveTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthWorks() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void streamingProducesNamedEvents() {
        var response = client.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<
                        ServerSentEvent<Tick>>() { });

        StepVerifier.create(response.getResponseBody().take(1))
                .expectNextMatches(event ->
                        "tick".equals(event.event())
                        && "flux-1".equals(event.id())
                        && event.data() != null
                        && event.data().sequence() == 1)
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.reactive.SlowReactiveTest
~~~

`take(1)` avoids waiting for the whole stream and propagates cancellation upstream. This tests the WebFlux HTTP pipeline, **not slow headers, slow bodies, or slow readers**. Those require proxy/network tests plus synchronized concurrent active-stream quota tests.

## 16. Why Can't a Single `try/finally` Filter Guard Every Async Request?

With a synchronous endpoint:

~~~java
try {
    return doWork();
} finally {
    permits.release();
}
~~~

execution scope and resource lifetime coincide.

With Servlet async:

~~~java
SseEmitter emitter = new SseEmitter();
return emitter;
~~~

The controller **returns immediately** while the response remains alive. Releasing the permit inside a controller `finally` leaves the socket and subscription open while reporting free quota. Attackers could open unlimited streams despite the "semaphore".

With reactive endpoints:

~~~java
Flux<String> stream = createStream();
return stream;
~~~

Constructing a `Flux` merely defines a pipeline—it **does not mean subscription or response completion has happened**. Tie acquire/release to subscription and response lifecycle via `Mono.defer`, `Flux.using`, `doFinally`, or a properly scoped `WebFilter`.

For Servlet `SseEmitter`, use `onCompletion`, `onTimeout`, `onError`, and idempotent cleanup. For reactive return types inside MVC, Spring docs emphasize **response writes remain blocking on the async executor** even when the source is a `Flux`; do not project WebFlux non-blocking expectations onto MVC.

## 17. When Responses Stall: Producers, Queues, and the Write Path

### 17.1. The Slow Reader Problem

~~~text
Producer: 1000 messages/s
        |
        v
Bounded/unbounded queue?
        |
        v
HTTP response writer
        |
        v
TCP send buffer
        |
        v
Client reads 10 messages/s
~~~

Without producer throttling, hundreds of thousands of items accumulate within minutes. Even when sockets burn no CPU, heap/direct buffers or blocked worker threads climb. Pick the policy matching your domain semantics:

- **Latest-state feeds:** coalesce, throttle, sample, or drop superseded snapshots safely.
- **Critical events:** durable event store + cursor, client reconnect/replay, idempotent handlers; never drop silently.
- **Large downloads:** stream files with zero-copy/backpressure support where valid, bounding file handles and response buffers.
- **Uploads:** body sizes + read deadlines + temp-disk quotas + checksums/abort cleanup.
- **Stuck clients:** close connections with reason metrics/logs; never build unbounded retry queues.

### 17.2. Blocking Writes in Spring MVC

`SseEmitter.send` / `ResponseBodyEmitter.send` can block the sending worker when a client reads slowly. Servlet async frees the initial controller thread, **without making subsequent writes non-blocking**. Use a bounded scheduler/executor, cap concurrent streams, avoid holding shared locks while writing to multiple subscribers, and close emitters on send errors.

### 17.3. Reactive Sources and Cancellation

WebFlux/Netty supports non-blocking I/O and Reactor demand/cancellation. Still:
- A hot producer ignoring demand forces buffering, dropping, or failing.
- Unbounded `Flux.onBackpressureBuffer` risks OOM.
- `Flux.onBackpressureLatest` drops intermediate events—use only when semantics allow.
- Closing an HTTP socket may not immediately halt broker message processing unless custom subscriptions handle dispose/cancel.
- Never call `Thread.sleep` or `block()` on reactive event loops.
- `DataBuffer` can wrap pooled Netty `ByteBuf`; custom error/discard paths must release buffers properly to avoid direct memory leaks.

Backpressure is a **pipeline coordination mechanism**, not a per-client SLA or a substitute for hard limits.

## 18. HTTP/2, HTTP/3, WebSocket, SSE, and Long-Polling Need Separate Quotas

### HTTP/1.1 Keep-Alive

One TCP socket serves multiple sequential requests. `max-keep-alive-requests` does not cap a long-lived SSE request, and `keep-alive-timeout` normally counts idle time awaiting the next request.

### HTTP/2 Multiplexing

One TCP socket carries many concurrent streams. **TCP connection limits alone cannot stop** a single client from opening numerous HTTP/2 streams, request headers, and per-stream buffers. Enforce server/proxy HTTP/2 `max-concurrent-streams` limits and per-route application quotas, testing your real deployment. Never assume HTTP/1.1 properties share identical semantics under HTTP/2.

### HTTP/3 / QUIC

Uses UDP/QUIC with stream-level controls differing from TCP. An NGINX/CDN edge may terminate HTTP/3 and proxy HTTP/1.1 to Spring. Enforce limits on **both the client-facing protocol and upstream protocol**, together with quotas in Spring.

### SSE

Browsers reconnect using `retry` / `Last-Event-ID`, without automatic durable replay on the server. Servers need:
- Per-user/tenant connection quotas.
- Heartbeats shorter than proxy idle timeouts to keep healthy streams open and detect dead clients.
- Absolute stream lifetimes or re-authorization when sessions expire/revoke.
- Bounded event queues and cancellation cleanup.
- Jittered reconnects and replay/idempotency where continuity matters.

**Heartbeats do not replace absolute TTLs:** sending a comment every 20 s resets idle timers; enforcing a 1-hour maximum requires an application-level deadline.

### WebSocket

Connections stay open very long; manage ping/pong frames, session caps, message size limits, inbound/outbound queues, send-time limits, heartbeats, and slow-reader disconnects. After HTTP upgrade, ordinary HTTP request timeouts rarely apply cleanly—manage limits at the WebSocket/messaging layer.

### Long-Polling

Requests may hang open for 20–60 s awaiting an event before completing and immediately reopening. Bound concurrent waiting requests, clean up promises on disconnect, and apply jittered retries—RPS rate limiters alone are insufficient.

## 19. Business Deadlines and Downstream Resource Limits

A client may read responses promptly while hitting an endpoint running a 60-second DB query. That is long-running server work rather than a slow reader, yet it still consumes capacity.

Separate:
- **HTTP request deadline:** total time the app allocates to receive and handle a request per contract.
- **DB query timeout:** prevents runaway SQL.
- **HTTP client timeouts:** connect, read, response, and pool acquire—distinct from inbound server timeouts.
- **Thread/worker concurrency:** caps parallel execution.
- **Cancellation propagation:** attempt to cancel downstream tasks on client disconnect, without assuming DB transactions automatically roll back when a browser tab closes.
- **Idempotency:** if a client times out while the server completes a POST, retries must rely on idempotency keys or business deduplication.

For instance, `CompletableFuture.orTimeout` completes the future exceptionally **without guaranteeing the underlying thread or DB call stops**. Reactor `timeout(Duration)` cancels the subscription, yet blocking or non-cancellable sources keep running. Propagate deadlines into downstream drivers and verify empirically.

An HTTP 504 from a gateway **does not prove** Spring aborted the transaction. Design explicit cancellation, transaction boundaries, and idempotent retries.

## 20. Connection Quotas by User/Tenant Instead of Spoofable IP

Suppose an app serves SSE dashboards. Limiting "2 streams per client IP" wrongly blocks employees sharing corporate NAT. Conversely, a leaked API key can open streams across many IPs.

After authentication, key quotas by:

~~~text
tenantId + userId + streamType

Example:
  tenant-42:user-7:notifications → max 2
  tenant-42:user-7:reports       → max 1
  tenant-42:*:all-streams        → max 500
  node:*:all-streams             → max 2000
~~~

This is an **illustrative policy**, not recommended production numbers. Consider:

1. Which routes are genuinely long-lived.
2. Whether users open multiple browser tabs or devices.
3. Whether fast reconnects overlap before old connections finish releasing.
4. Whether large tenants need dedicated quotas or weighted fairness.
5. Whether you need a distributed limiter (Redis/gateway/broker) or if per-node quotas suffice.
6. If a node crashes holding distributed permits, do leases/TTLs auto-expire them?
7. Can clients spoof `userId`, or is the quota key derived from the authenticated principal?
8. When permissions are revoked, are active streams closed or re-authorized promptly?
9. Are 429/503s tracked and do clients use backoff with jitter?

**Never hold distributed locks tied to TCP connections without TTL/lease recovery**; a node crash would leak quota permanently. Often per-node caps + gateway rate limits + distributed user quotas work well when backed by fault testing.

## 21. Observability: Measure Saturation Instead of Just Reading p95 Latency

Signals to track:

| Signal | What It Detects |
| --- | --- |
| Open/active HTTP connections | Socket and file descriptor pressure |
| Active requests, concurrent streams | Long-lived request occupancy |
| Busy workers / queued tasks / rejections | Servlet, JDBC, and async pool saturation |
| Event-loop latency | Blocked Netty/Undertow I/O threads |
| Heap/direct memory, GC, pooled buffers | Per-client buffer backlogs and leaks |
| HTTP duration p50/p95/p99 | Tail latency (separate short APIs from streams) |
| Read/write timeout counts | Slow bodies and stalled responses |
| Client disconnect/cancel counts | Slow readers, flaky mobile networks, deploys |
| 429/503/408/413/502/504 by route/layer | Which limit or timeout is firing |
| DB pool active/idle/pending | Downstream resource contention |
| SSE active subscriptions / backlog / replays | Hot-publisher pressure and reconnect storms |
| Load balancer pending/current requests | Edge queue and capacity overload |
| Per-tenant quota rejections | Fairness and quota sizing |

Spring Boot Actuator/Micrometer provides `http.server.requests` and runtime metrics via enabled binders. For Tomcat, many `tomcat.*` metrics require:

~~~properties
server.tomcat.mbeanregistry.enabled=true
~~~

plus proper Actuator/Micrometer setup. `http.server.requests` does not count idle TCP connections or attach per-user labels automatically. **Never add `userId`, `sessionId`, or raw URLs to metric tags**—it explodes cardinality and leaks PII. Use route templates, status, server instance, outcome, and sensible buckets.

### Separate SLOs for Streaming

A healthy 1-hour SSE connection has a 1-hour duration **by design**. Mixing it into GET JSON p99 makes dashboards scream "API is slow" when nothing is wrong. Define distinct SLOs:
- Short HTTP requests: p95/p99 latency and error rates.
- SSE/WebSockets: active connections, time-to-first-event, reconnect rate, canceled streams, event delivery lag.
- Uploads: bytes/sec, time to first byte, completion/abort ratios, oversized rejections.
- Downloads: throughput, stalled writes, canceled transfers.

Access logs normally write on request completion, so open streams will not appear there yet—monitor live gauges instead.

## 22. Testing Slow Clients: Safe, Controlled, and Targeted

Run tests strictly on **localhost or authorized staging**, with small client counts and short durations. Never launch Slowloris-style socket floods at external targets.

### 22.1. Test Sequence

1. Baseline: cURL `/health` latency and status when idle.
2. Open two SSE streams; verify a third gets 503 while `/health` stays 200.
3. Close one SSE early; verify quota frees up and a new stream succeeds.
4. Hold an SSE until timeout; verify cleanup, threads, and connection counts.
5. Run cURL `--limit-rate` and `--max-time` to simulate slow reading; measure writer/buffer impact if applicable.
6. Trickle a **valid** large upload into a size-capped staging route; verify actual 413/408/close behavior across proxy and server without assuming identical statuses everywhere.
7. Test through the public NGINX/ingress route, not only Spring's direct port.
8. Kill one pod/instance while streams are open; verify jittered reconnects, backlog, and CPU.
9. Verify short API p95 stays within SLO alongside active valid streams.
10. Verify logs/metrics distinguish quota rejections, timeouts, and client aborts without leaking secrets.

### 22.2. cURL Slow-Reader Demo

~~~bash
curl -N -i --limit-rate 512 --max-time 5 \
  http://localhost:8080/events
~~~

This is a **lightweight** test—unlikely to fill TCP send buffers given the tiny SSE sample. It verifies slow-reading behavior, not full Slowloris resistance. Testing slow responses thoroughly requires larger payloads while monitoring memory/threads under strict bounds.

### 22.3. cURL Concurrent Requests (Illustrative)

On Linux/macOS with `xargs`:

~~~bash
seq 1 12 | xargs -P 12 -I {} \
  curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/work
~~~

Because `/work` takes ~200 ms per accepted request across 2 slots, concurrent load yields a mix of 200s and 503s. **Exact status counts vary** with OS scheduling, networking, and `xargs` process startup. Never use a single burst result to claim immunity against slow-header attacks.

### 22.4. Identifying Which Layer Emitted an Error

| Outcome | Likely Source |
| --- | --- |
| HTTP 429 | App per-user quota or NGINX `limit_conn`/`limit_req` configured to 429 |
| HTTP 503 | App semaphore exhausted; NGINX also defaults to 503 on connection limits unless overridden |
| HTTP 408 | HTTP server/proxy request timeout when it emits an HTTP error response |
| HTTP 413 | Body/request size limit exceeded |
| HTTP 502/504 | Gateway could not connect or timed out waiting on upstream; Spring may not have responded |
| TCP reset / EOF | Connection closed before forming an HTTP response; status may be absent |
| HTTP 200 then stream cuts off | Mid-response disconnect/timeout; HTTP status cannot change after headers commit |

Never "fix" every error by raising timeouts. Loosening timeouts helps slow legitimate clients yet lets attackers hold resources longer. Match policy to error cause, backend capacity, and route semantics.

## 23. Common Anti-Patterns

| Anti-Pattern | Consequence | Replace With |
| --- | --- | --- |
| Setting `keepAliveTimeout=10s` thinking it stops slow uploads | Active requests stay open anyway | Edge body-read/deadline/size/rate limits |
| Raising `maxConnections` indefinitely | Socket/heap/FD exhaustion | Capacity modeling + quotas + monitoring |
| Raising `threads.max` while DB pool stays at 10 | Threads just pile up waiting on DB | Bounded concurrency and downstream budgets |
| Blocking `Semaphore.acquire()` on request threads | Ties up threads, worsens overload | `tryAcquire` + fast rejection |
| Releasing permit in controller `finally` for SSE/`Flux` | Stream remains open while quota looks empty | Lifecycle callbacks or reactive `doFinally` |
| Spawning a thread per SSE user | Exhausts threads at scale | Shared bounded executor or reactive streams |
| Unbounded `Flux.onBackpressureBuffer()` | OOM under slow readers | Bounded queues + explicit overflow policy |
| Dropping business events without replay | Data loss, stale state | Durable log/cursor and resync |
| Disabling all timeouts so "SSE never drops" | Resources held forever | Heartbeats + quotas + absolute TTL + reconnect |
| IP-only quotas behind NAT | False positives blocking valid users | Edge IP controls + authenticated user/tenant quotas |
| Trusting raw `X-Forwarded-For` for quotas | Attackers spoof headers | Trusted gateway stripping/overwriting headers |
| Missing jitter after mass disconnect | Reconnect storms | Exponential backoff + jitter |
| Unbounded response buffers for slow readers | Memory/disk pressure | Bounded buffers/temp disk + disconnect slow clients |
| Assuming 504 rolled back the DB transaction | Duplicate side effects on retry | Deadline/cancellation propagation + idempotency |
| Mixing SSE duration into HTTP JSON p99 | Skewed latency dashboards | Stream-specific SLOs |
| Testing with `MockMvc` and claiming Slowloris immunity | Skips TCP parser/proxy/slow readers | Authorized staging network tests |

## 24. Production Readiness Checklist

1. Is the actual embedded server Tomcat, Jetty, Undertow, or Reactor Netty? Verify dependencies.
2. Do edge/proxies enforce header/body timeouts, connection caps, and slow-reader protection?
3. Are *idle-between-operations* timeouts clearly separated from *absolute duration* deadlines?
4. Is `keep-alive-timeout` cleanly distinguished from request processing timeouts?
5. Have Tomcat `maxConnections`/`acceptCount`/`threads` or Jetty/Undertow/Netty configs been load-tested?
6. Are request header/body sizes, multipart limits, and temp disk quotas enforced?
7. Are request queues, executor queues, and outbound connection pools bounded?
8. Do CPU/DB-heavy operations have admission control, timeouts, cancellation, and 429/503 policies?
9. Do SSE/WebSocket/long-poll routes enforce per-node/user/tenant quotas and disconnect cleanup?
10. Do streaming producers enforce bounded buffers, backpressure, and replay semantics?
11. Do reconnects use backoff + jitter with safe resume/resync?
12. Are TLS/HTTP2/H3 limits and proxy-hop timeouts aligned consistently?
13. Are CORS, authn, and authz enforced on long-lived streams including permission revocation?
14. Are open sockets, FDs, busy threads, Netty event loops, direct memory, and DB pools monitored?
15. Have slow bodies, slow reads, and long streams been tested on staging via the **public route**, not only localhost?
16. Do logs and metrics distinguish gateway timeouts from origin timeouts?
17. Are credential/PII leaks in logs, `X-Forwarded-*` trust boundaries, and metric cardinality guarded?
18. Are rolling deploys, connection draining, idle-stream cleanup, and load shedding planned?
19. Does capacity planning account for bursts and p99 rather than average RPS alone?
20. Are all timeout and capacity values calibrated to product SLOs and real measurements rather than lab defaults?

## 25. Self-Check Exercises

**1.** A client holds a keep-alive connection open without sending a new request. What does `keepAliveTimeout` control?

**Answer:** It bounds how long to wait for the **next** HTTP request on a persistent connection before closing it. It does not set a deadline on an active download.

**2.** Why can Slowloris overwhelm a server even with very low RPS per IP?

**Answer:** It ties up connections and HTTP parser state by trickling headers slowly without completing many HTTP requests.

**3.** Does `client_body_timeout=10s` in NGINX cap total upload duration at 10 seconds?

**Answer:** No. It bounds the idle gap between body reads. A client sending steadily at a tiny rate bypasses it; combine with total deadlines, size caps, or minimum rate limits where supported.

**4.** Does Tomcat `max-connections=100` guarantee the 101st request receives HTTP 503?

**Answer:** No. OS socket backlogs can time out or refuse connections; HTTP 503 is only returned once a request is read and processed enough to send an HTTP response.

**5.** Does `server.undertow.no-request-timeout` limit the total duration of an active file download?

**Answer:** No. It targets idle connections **not processing a request**; response write policies and stream lifetimes must be handled separately.

**6.** Once a Spring MVC controller returns an `SseEmitter`, can it immediately release the stream semaphore?

**Answer:** No. The HTTP response remains open; release idempotently via `onCompletion`, `onTimeout`, `onError`, and disconnect cleanup.

**7.** Does Spring WebFlux `Flux` guarantee a hot producer never triggers OOM when a browser reads slowly?

**Answer:** No. Backpressure requires producer cooperation; hot sources and unbounded buffers still overflow. Use bounded policies matched to event semantics.

**8.** Is NGINX `limit_req` enough to stop one user from opening hundreds of SSE streams?

**Answer:** No. `limit_req` limits request initiation rate; long-lived streams require `limit_conn`, per-user active quotas, and HTTP/2 stream budgets.

**9.** An SSE stream sends a heartbeat every 20 s with `proxy_read_timeout=60s`. Will the stream auto-close after 60 s?

**Answer:** Not necessarily. The proxy reads bytes regularly before the idle window expires, resetting the timer. To cap total lifetime, enforce an application-level stream TTL with reconnect/re-auth.

**10.** The gateway returns 504 after 30 s. Has the SQL transaction in Spring definitely stopped?

**Answer:** No. A gateway timeout does not automatically cancel DB transactions. Coordinate deadlines, cancellation, and idempotency.

**11.** Does enabling Java 21 virtual threads eliminate socket or DB pool starvation?

**Answer:** No. Virtual threads change task execution scheduling, not FD or DB connection limits; application quotas remain crucial.

**12.** Why separate short HTTP latency metrics from SSE stream durations?

**Answer:** Long streams are long by design; mixing them into JSON API p99 distorts alerts. Track active streams, event lag, and reconnects separately.

## 26. Official References

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): Tomcat `maxConnections`, threads, `acceptCount`, connection/keep-alive timeouts; Jetty idle/connection limits; Undertow `no-request-timeout`, workers; Netty idle/keep-alive.
- [Spring Boot 3.3 – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html): async executors, bounded queues, virtual threads, and MVC async integration.
- [Apache Tomcat 10.1 – HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html): `connectionTimeout`, `keepAliveTimeout`, `maxConnections`, `acceptCount`, `maxKeepAliveRequests`, upload timeouts.
- [Spring Framework – MVC Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `SseEmitter`, blocking writes, lifecycle callbacks, disconnect handling, async executors.
- [Spring Framework – WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): non-blocking I/O, Reactive Streams backpressure, `DataBuffer`/codec behavior.
- [Reactor Netty – HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): idle timeouts and server-side read/request timeouts per Reactor Netty version.
- [NGINX – HTTP Proxy Module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_request_buffering`, `proxy_buffering`, `proxy_read`/`send`/`connect_timeout`.
- [NGINX – HTTP Core Module](https://nginx.org/en/docs/http/ngx_http_core_module.html): `client_header_timeout`, `client_body_timeout`, `send_timeout`, `keepalive_timeout`.
- [NGINX – Connection Limiting](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html): `limit_conn_zone`, `limit_conn`, HTTP/2/3 behavior, and header-read prerequisites.
- [Spring Boot 3.3 – Actuator Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html): `http.server.requests`, Tomcat metrics, and monitoring.
- [Reactor Core – Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): lifecycle, cancellation, and backpressure operators.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP framing, connections, and message processing.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexing, concurrent streams, and flow control.

**Remember:** never try to "stop slow clients" with a single timeout or by adding threads. Combine **per-phase timeouts, socket/stream/worker/queue caps, streaming backpressure, identity-based quotas, edge proxy protection, and live observation of open requests**. Healthy clients get served within budget; excessively slow clients are rejected or closed cleanly without taking down the rest of the system.