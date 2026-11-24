# Connection Timeouts, Keep-Alive, and Server-Specific Limits

In Spring Boot, an API that runs well in a development environment can still fail when many clients keep connections open, send requests slowly, reuse sockets for a long time, or exceed the resource limits of the embedded web server. Parameters for `timeout`, `keep-alive`, and `max connections` control the connection lifecycle, yet each parameter affects a different phase. Configuration must be based on the **actual server running** (Tomcat, Jetty, Undertow, or Reactor Netty), HTTP protocol version, upstream proxies, and traffic characteristics.

This lesson explains the differences among timeout types, connection reuse mechanisms, server-level limits, how to configure them in Spring Boot 3.3.x, and verification methods for deployment. Values in the examples are starting points for testing, **not optimal default configurations for every system**.

## 1. What Phases Does an HTTP Connection Go Through?

For a typical HTTP/1.1 request:

1. The client establishes a TCP connection to the server, possibly performing a TLS handshake if using HTTPS.
2. The server accepts the socket and waits for the request line/headers.
3. The client sends the request; the server receives the body if present.
4. Spring processes the request through servlets/filters/controllers or the WebFlux processing chain.
5. The server writes the response.
6. The connection is closed or kept open for the client to send the next request.

A simplified diagram:

~~~text
Client -- TCP/TLS --> Server socket
                    |
                    +-- wait for request line / headers
                    |
                    +-- receive body, process controller
                    |
                    +-- send response
                    |
                    +-- keep-alive idle -> next request?
                                      | yes: reuse
                                      | no : close connection
~~~

These phases can have separate timers. Therefore, simply saying "30-second server timeout" is insufficient: you need to know **which timeout, when it starts counting, which event stops it, and which component enforces it**.

## 2. Distinguishing Frequently Confused Timeout Types

| Limit Type | Applied When | Practical Meaning |
|---|---|---|
| Client connect timeout | Client tries to establish a connection to the server | How long the client waits for the connection to succeed; usually lives on the HTTP client |
| Server connection/request-line timeout | Connection accepted but initial request not yet complete | Limits how long the server waits for the client to start sending the request per server rules |
| Connection idle timeout | Socket has no I/O activity per server rules | Connections idle for too long are closed |
| HTTP keep-alive timeout | After a response, server waits for the next request | Limits the idle gap between requests on a reused connection |
| Request processing timeout | Request is being processed | Limits total request or async task processing time; usually governed by framework, app, or proxy |
| Response/client read timeout | Client waits for response bytes | Usually configured on HTTP client/proxy, not synonymous with server keep-alive |
| Graceful shutdown timeout | Server is stopping | Grace period for existing work/requests to finish before closing resources |

There is no single Spring Boot property that applies to all of the timeouts above at once.

For example: `server.tomcat.connection-timeout` describes how long Tomcat waits for the **request URI line after accepting a connection**, not the total time a controller is allowed to run. `server.tomcat.keep-alive-timeout` instead controls waiting for the **next** request after the previous response finishes.

When debugging, distinguish whether a failure occurs **before the request is read**, **while the request is being processed**, or **after the response while the socket is held open**.

## 3. What Is HTTP Keep-Alive?

In HTTP/1.1, persistent connections are the default behavior unless a connection-close signal is sent. One TCP connection can carry multiple sequential request/response pairs. This reduces TCP connection setup, TLS handshake overhead, and resource allocation.

Logical protocol example:

~~~http
GET /api/products/1 HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 10

{"id":1}

GET /api/products/2 HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 10

{"id":2}
~~~

Both requests in the example can travel over the **same TCP connection** if both server and client allow reuse. The example is a protocol illustration, not code to send with a single shell command.

Points to remember:

- In HTTP/1.1, sending `Connection: keep-alive` is not required for persistent connections; most clients use persistent connections by default.
- `Connection: close` requests that the connection be closed after completing the current message.
- Headers like `Keep-Alive: timeout=...` or `Keep-Alive: max=...`, if present, are only hop-by-hop hints; clients cannot force a server to keep a socket alive indefinitely.
- HTTP/2 uses multiple streams over one connection and has different connection management rules from HTTP/1.1. Do not put the `Connection` header in HTTP/2; multiple requests sharing a TCP connection is not synonymous with sequential HTTP/1.1 requests.
- HTTP keep-alive differs from **TCP SO_KEEPALIVE**. TCP keepalive is a socket-level TCP probing mechanism to detect dead connections, not a replacement for the timeout waiting for the next HTTP request.

Keeping connections open longer benefits latency, yet also holds file descriptors, sockets, buffers, and server state. Keeping them too short causes frequent new connections; keeping them too long can exhaust resources when many clients leave connections idle.

## 4. Two Keep-Alive Limits: Time and Request Count

There are at least two independent questions:

1. **How long can a connection sit idle before closing?** — keep-alive/idle timeout.
2. **At most how many requests can a connection serve?** — max keep-alive requests.

Hypothetical example:

~~~text
timeout between two requests: 15 seconds
maximum requests per connection: 100
~~~

If the client stays silent for more than 15 seconds, the server may close the socket even if it has only handled 2 requests. If the client sends 100 requests back-to-back, the server may close the connection once the limit is reached even when idle gaps are tiny.

The request-count limit is a server-specific feature; do not assume Tomcat, Jetty, Undertow, and Reactor Netty share the same property. Read the documentation for your specific server and Spring Boot version.

## 5. Spring Boot Distinguishes Embedded Servers

Spring Boot can run multiple web servers, but properties only take effect when the corresponding server is actually used.

| Web Stack / Server | Usually Activated By | Main Configuration Namespace |
|---|---|---|
| Spring MVC + Tomcat | `spring-boot-starter-web` with default dependencies | `server.tomcat.*` |
| Spring MVC + Jetty | Using Jetty instead of Tomcat | `server.jetty.*` |
| Spring MVC + Undertow | Using Undertow instead of Tomcat | `server.undertow.*` |
| Spring WebFlux + Reactor Netty | `spring-boot-starter-webflux` with default dependencies | `server.netty.*` |

You cannot configure Tomcat by setting `server.netty.idle-timeout` if the running process actually uses Tomcat. When a project carries both Servlet and Reactive dependencies, Spring Boot normally defaults to the Servlet application type; verify the web stack from dependencies, startup logs, and the actual `WebApplicationContext` type.

All related properties should be checked per version. For example, Spring Boot 3.3.x and 4.x may share many property names while defaults, support, and underlying server behavior can differ.

## 6. Tomcat: Connection Timeout and Keep-Alive

### 6.1. Core Properties

In Spring Boot 3.3.x, Tomcat provides these key properties:

| Property | Meaning |
|---|---|
| `server.tomcat.connection-timeout` | Wait time for the request URI line after Tomcat accepts a connection |
| `server.tomcat.keep-alive-timeout` | Wait time for the next request before closing the connection |
| `server.tomcat.max-keep-alive-requests` | Limit on requests handled on a keep-alive connection |
| `server.tomcat.max-connections` | Limit on connections Tomcat accepts/handles concurrently |
| `server.tomcat.accept-count` | Incoming connection queue size once processing capacity limit is reached |
| `server.tomcat.threads.max` | Connector worker thread limit under standard thread pool configuration |
| `server.tomcat.threads.min-spare` | Minimum spare worker threads |

According to Spring Boot 3.3 configuration documentation, defaults are commonly listed as `max-keep-alive-requests=100`, `max-connections=8192`, `accept-count=100`, and `threads.max=200`. These are **version reference values**, not recommendations to set every application to those numbers.

### 6.2. Example Tomcat Configuration

In `src/main/resources/application.yml` of a Spring MVC application running Tomcat:

~~~yaml
server:
  port: 8080
  tomcat:
    connection-timeout: 10s
    keep-alive-timeout: 15s
    max-keep-alive-requests: 100
    max-connections: 2000
    accept-count: 100
    threads:
      max: 200
      min-spare: 10
~~~

Explanation:

- `connection-timeout: 10s` limits the wait for the first request line after the connection is accepted.
- `keep-alive-timeout: 15s` limits idle time waiting for the next request.
- `max-keep-alive-requests: 100` limits the number of requests per persistent connection.
- `max-connections: 2000` limits connections accepted and handled by Tomcat.
- `accept-count: 100` relates to the queue of waiting connections when the server is busy; actual effectiveness also depends on OS backlog.
- `threads.max: 200` limits worker threads in the traditional thread-pool model; it does not mean only 200 TCP connections can be opened.

This is an **illustrative example showing parameter relationships**, not load-tested; do not copy it to production without verification. When virtual threads are enabled on supported versions, some thread-pool properties like `server.tomcat.threads.max` may no longer work in the traditional way; monitor how the runtime handles requests.

### 6.3. When keep-alive-timeout Is Not Declared

With Tomcat, if `server.tomcat.keep-alive-timeout` is not set, the wait time for the next request uses the connector's connection timeout value. If set to `-1`, Tomcat applies no keep-alive timeout via this property. Avoid infinite wait times on public systems without corresponding connection policies and resource capacity.

`max-keep-alive-requests` set to `0` or `1` can disable keep-alive/pipelining per Tomcat rules; `-1` allows an unlimited number of requests with respect to this parameter. Do not confuse `max-keep-alive-requests` with `max-connections`: one counts requests **on a single socket**, while the other counts **concurrent sockets**.

## 7. Tomcat: Connection Resources, Queue, and Worker Threads

Three numbers are often conflated:

~~~text
max-connections     -> number of sockets that can be accepted/handled
threads.max         -> number of worker threads processing work
accept-count        -> incoming connection queue when overloaded
~~~

An idle keep-alive connection does not constantly hold a busy worker thread. With synchronous Servlets, an in-progress request occupies a worker thread while the controller runs. If the controller makes blocking database or HTTP service calls, the worker thread remains held while waiting for results.

Consequences:

- **Increasing max-connections** allows more sockets but can increase memory, file descriptors, and I/O load.
- **Increasing threads.max** can improve throughput for some blocking workloads, but excessive threads cause context switching, stack memory usage, and resource contention.
- **Increasing accept-count** allows more waiting connections, but may merely shift failures from connection refusals to longer wait times; it does not make controllers faster.
- **Decreasing keep-alive-timeout** reclaims idle sockets sooner but increases how often clients must open new connections.

There is no rule `max-connections = threads.max`. Measure throughput, latency, active connections, busy threads, request queues, and client outcomes together.

## 8. Jetty: Idle Timeout and Server-Specific Limits

When a Servlet application uses Jetty, corresponding properties include:

~~~yaml
server:
  jetty:
    connection-idle-timeout: 30s
    max-connections: 1500
    threads:
      max: 200
      min: 8
~~~

Meaning:

- `server.jetty.connection-idle-timeout`: connections with no activity within the timeout may be closed.
- `server.jetty.max-connections`: limits connections accepted and handled concurrently by the server; in Spring Boot 3.3 docs, the default `-1` indicates no limit imposed by this property.
- `server.jetty.threads.max` and `server.jetty.threads.min`: Jetty thread pool sizing under the standard mechanism.
- `server.jetty.threads.idle-timeout`: idle timeout for threads in the pool, **not** the HTTP connection timeout.
- `server.jetty.threads.acceptors` and `server.jetty.threads.selectors`: adjust acceptor and I/O selector threads; understand resource implications before changing.

**Common mistake:** setting `server.jetty.threads.idle-timeout=30s` and thinking HTTP connections will close after 30 seconds. That property pertains to the thread pool; to affect connections, use `server.jetty.connection-idle-timeout`.

Jetty has its own resource management and connection handling; do not apply Tomcat values assuming all limits share the same meanings and defaults.

## 9. Undertow: no-request-timeout and HTTP Limits

For Undertow, Spring Boot 3.3.x supports:

~~~yaml
server:
  undertow:
    no-request-timeout: 20s
    max-http-post-size: 10MB
    max-cookies: 200
    threads:
      io: 4
      worker: 32
~~~

In this example:

- `server.undertow.no-request-timeout`: how long a connection can sit idle without processing a request before the server closes it.
- `server.undertow.max-http-post-size`: limits HTTP POST content per Undertow behavior.
- `server.undertow.max-cookies`: limits the number of accepted cookies.
- `server.undertow.max-headers` and `server.undertow.max-parameters`: limit header and parameter counts to reduce excessive resource consumption risks.
- `server.undertow.threads.io`: number of I/O threads; do not use them for long blocking tasks.
- `server.undertow.threads.worker`: number of worker threads executing work offloaded from I/O threads.

Spring Boot also supports passing certain Undertow/XNIO options via `server.undertow.options.server.*` and `server.undertow.options.socket.*`. Cross-check option names against your exact Undertow version, as this is a low-level configuration layer without necessarily having equivalent high-level Spring Boot properties.

A `no-request-timeout` value is an idle-connection policy. It **does not guarantee** that an entire business request will be aborted if a controller runs longer than that duration.

## 10. Reactor Netty: Connection and Channel Idle

In WebFlux applications using Reactor Netty, available properties include:

~~~yaml
server:
  netty:
    connection-timeout: 10s
    idle-timeout: 30s
    max-keep-alive-requests: 100
    max-initial-line-length: 8KB
~~~

Meaning according to Spring Boot 3.3 documentation:

- `server.netty.connection-timeout`: connection timeout of the Netty channel. Understand it in the context of the running server/channel, not the same as an HTTP client's connect timeout.
- `server.netty.idle-timeout`: how long a channel can stay idle before closing; if omitted, Boot 3.3 docs note the timeout may be infinite under this setting.
- `server.netty.max-keep-alive-requests`: maximum requests per connection; if unset, unlimited by this property by default.
- `server.netty.max-initial-line-length`: limits the HTTP request initial line length, completely different from a timeout.
- `server.netty.initial-buffer-size`: initial buffer capacity for decoding HTTP requests.

WebFlux + Reactor Netty uses an event-loop model, so you cannot transfer `server.tomcat.threads.max` values directly to Netty. If a WebFlux handler performs long blocking I/O on the event loop, the system can stall even with few open connections. Offload blocking work to an appropriate scheduler or use genuinely non-blocking clients/data access.

**Distinguishing Netty server from Reactor Netty HTTP client:** timeouts when the application calls an external API using `WebClient` are usually configured on the application's HTTP client/`HttpClient`, such as connect/response timeouts. Setting `server.netty.idle-timeout` only affects the server and does not change outbound timeouts.

## 11. Header, Body, Form, and Multipart Size Limits

Beyond time and socket counts, web servers enforce input size limits to protect memory and reject abnormal requests.

| Group | Example Spring Boot 3.3 Property | Note |
|---|---|---|
| Request header | `server.max-http-request-header-size` | Each server enforces the limit differently |
| Tomcat Form POST | `server.tomcat.max-http-form-post-size` | Limits form POST content |
| Tomcat Swallow body | `server.tomcat.max-swallow-size` | Amount of request body Tomcat can drain and discard during handling |
| Jetty Form POST | `server.jetty.max-http-form-post-size` | Form limit per Jetty |
| Undertow HTTP POST | `server.undertow.max-http-post-size` | POST content limit per Undertow |
| Netty Request line | `server.netty.max-initial-line-length` | Request initial line, not body |
| Servlet Multipart | `spring.servlet.multipart.max-file-size` and `spring.servlet.multipart.max-request-size` | Limits file uploads and total multipart requests |

Example:

~~~yaml
server:
  max-http-request-header-size: 16KB

spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 10MB
~~~

`server.max-http-request-header-size` **is not applied identically by all servers**. Boot 3.3 docs note as an example: Tomcat sums the request line and all headers; Reactor Netty enforces the limit per individual header. Thus, two servers with the same `16KB` setting may accept/reject different requests.

A common mistake when a large JSON request fails is raising `server.tomcat.max-http-form-post-size`. That property is for form POSTs, not a "size limit for every JSON request". Identify the layer actually rejecting the body: proxy, server parser, multipart resolver, framework, or application logic.

## 12. Runnable Demo: Observing Connection Reuse

The following example uses Java 17+ and Spring Boot 3.3.x with `spring-boot-starter-web` (default Tomcat). Place the code in `src/main/java/com/example/demo/ServerLimitsApplication.java` of a Spring Boot project with the appropriate dependencies and build plugin:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServerLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerLimitsApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(path = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "pong\n";
    }
}
~~~

Configure `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  tomcat:
    connection-timeout: 10s
    keep-alive-timeout: 15s
    max-keep-alive-requests: 100
~~~

Run on Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Run on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

To test a client sending two HTTP/1.1 requests in **a single curl process**, run:

~~~bash
curl --http1.1 -v http://localhost:8080/ping http://localhost:8080/ping
~~~

The response body of each request is one line:

~~~text
pong
pong
~~~

When both server and client permit reuse, verbose output can show a line like `Re-using existing connection` on the second request (exact wording may vary by curl version). Running **two separate curl processes** twice does not prove socket reuse, because each process usually has its own connection pool.

To request closing after the response:

~~~bash
curl --http1.1 -v -H "Connection: close" \
  http://localhost:8080/ping http://localhost:8080/ping
~~~

Depending on your shell platform, use the appropriate line-continuation syntax. On Windows PowerShell, you can write the command on one line and use `curl.exe` to avoid older PowerShell alias confusion.

**Follow-up experiment:** change `server.tomcat.max-keep-alive-requests` to `1`, restart, and observe the second request. The expectation is that the client needs a new connection after each response; verify using verbose output and socket info, not just the `pong` body.

## 13. Testing Real Timeouts with Appropriate Methods

The `curl -v` command above is useful for observing keep-alive behavior, but insufficient for measuring every timeout.

To test **server connection timeout**, you need a client that can open a TCP socket and send the request line slowly in a controlled way. A normal HTTP request completes too quickly to trigger this limit.

To test **keep-alive idle timeout**, you must reuse the same connection and intentionally hold it idle between two requests. If the client process exits and opens a new connection, the test does not measure the old socket's timeout.

To test **max connections or accept queue**, you need a load-testing tool opening many concurrent connections while observing resources and connection failures. Running a few sequential requests does not verify concurrency limits.

To test **max-keep-alive-requests**, send many requests over a single connection and count socket creations/closures via client logs, packet captures, or server telemetry.

When running tests:
- Confirm the actual Spring Boot version and embedded server.
- Note HTTP/1.1 vs. HTTP/2 and whether TLS is used.
- Verify whether any proxy, ingress, or load balancer sits in between.
- Measure at least throughput, p95/p99 latency, connection counts, CPU, memory, threads/event loops, and error rates.
- Test after restarting to confirm configuration was actually loaded.
- Never run overload threshold tests directly on production systems without controlled safeguards.

## 14. Reverse Proxies and Load Balancers Also Have Their Own Timeouts

A request can traverse multiple hops:

~~~text
Browser / API client
         |
         v
CDN / Load Balancer  <-- client-side idle timeout
         |
         v
Ingress / Reverse Proxy  <-- upstream keep-alive, read timeout
         |
         v
Spring Boot embedded server <-- server.tomcat / server.jetty / server.netty ...
~~~

Each hop may have different connection pools, idle timeouts, and concurrent connection limits. When clients observe HTTP 502/504 or connection reset errors, the root cause is not necessarily in Spring Boot; the proxy may have closed an upstream connection or stopped waiting for the response.

For example: a reverse proxy tries to reuse an upstream connection that the server already closed due to keep-alive timeout. The client/proxy must detect stale sockets and open a new connection properly; simply raising one side's timeout will not automatically make the error vanish.

In operations, compare timeout policies across every hop, clean connection-closing behavior, HTTP versions, and retry semantics. For non-idempotent POST requests, automatic retries can create duplicate actions if no deduplication mechanism exists.

## 15. Connection Timeout Does Not Fix Long-Running Requests

If a controller queries a database for 60 seconds before returning a result, increasing `server.tomcat.keep-alive-timeout` from 15 seconds to 90 seconds **does not make the controller faster** and does not guarantee an in-progress request will be waited on for 90 seconds.

Other wait timers to distinguish:
- Database connection/statement timeouts, usually managed by the datasource or database client.
- Outbound HTTP timeouts, usually configured on `RestClient`, `RestTemplate`, `WebClient`, or the underlying HTTP client.
- Servlet async task timeouts, e.g., `spring.mvc.async.request-timeout` when using the corresponding MVC async model.
- Reverse proxy/load balancer timeouts waiting for an upstream response.
- Application-level timeout policies: cancellation, deadlines, circuit breakers, retries.

In WebFlux, do not treat `server.netty.idle-timeout` as the total deadline for a reactive pipeline. If business logic needs a 5-second limit, apply timeouts at the appropriate reactive operator/client layer and handle cancellation, resource cleanup, and error mapping.

## 16. Symptoms, Causes, and Troubleshooting Actions

| Symptom | Potentially Related To | What to Check |
|---|---|---|
| Client socket closed while idle | Keep-alive/idle timeout or proxy | Per-hop timeouts, TCP trace, connection close logs |
| Client frequently opens new TCP connections | Keep-alive disabled/too short, low max requests | HTTP version, `Connection: close`, client pooling |
| Connection refused or timeouts under heavy load | Connection limit, backlog, or OS limits | max-connections, accept-count, file descriptors, socket count |
| High latency with low CPU | Worker threads blocked on I/O, long queues | Busy threads, thread dumps, downstream latency |
| Large headers rejected | Header parser/limit at server or proxy | server.max-http-request-header-size and per-hop limits |
| Multipart upload rejected | Multipart limit, form limit, or proxy body size | spring.servlet.multipart.*, server, and proxy |
| 502/504 at ingress | Upstream reset or response read timeout | Proxy upstream logs, server logs, response times |
| WebFlux slow when handler blocks | Event loop blocked | Blocked threads, schedulers, non-blocking clients |
| Out of file descriptors / many idle connections | Long keep-alive, high socket limits | Open sockets, OS ulimit, idle timeouts |

Read timestamp-aligned logs from client, proxy, and Spring Boot to identify which component closed the connection first. A client message like "Connection reset by peer" only indicates the connection was reset; by itself it does not prove whether it was a connection timeout, keep-alive timeout, or application error.

## 17. Safe Tuning Process

1. **Verify the real runtime.** Servlet Tomcat/Jetty/Undertow or WebFlux Reactor Netty; inspect build dependencies and startup logs.
2. **Define the goal.** For example, reducing idle connections, serving more concurrent clients, avoiding oversized request header errors, or protecting uploads.
3. **Map the connection hops.** Client, proxy, ingress, load balancer, and embedded server; record timeouts at each hop.
4. **Establish a baseline.** Run representative traffic and measure connection counts, requests/second, latency, threads, event loops, memory, and errors.
5. **Change only one configuration group at a time.** Adjust the timeouts or connection limits directly tied to the issue, then re-measure.
6. **Measure trade-offs.** Short keep-alive increases handshakes, excessive worker threads raise CPU/memory, and long queues raise latency.
7. **Test boundaries.** Large request headers, slow-sending clients, idle keep-alive, high connection concurrency, and shutdown/restart.
8. **Record operational results.** Save the configuration, server version, workload, and measurements so future deployments have a comparison baseline.

If Actuator/Micrometer is enabled, you can use HTTP request and runtime metrics together with server-specific metrics when exposed. Some connection/thread metrics depend on binders and the embedded server; do not assume metric names or measurements are present in every application.

## 18. Common Configuration Mistakes

1. **Confusing client connect timeout with server connection timeout.** Client timeouts belong to the HTTP client; `server.tomcat.connection-timeout` does not govern outbound `WebClient`.
2. **Confusing keep-alive with request processing timeout.** A socket waiting for the next request is different from a slow controller execution.
3. **Using properties for the wrong server.** `server.tomcat.*` has no effect on Reactor Netty, Jetty, or Undertow.
4. **Confusing requests per connection with concurrent connections.** One socket can serve many requests over time; many sockets can sit idle simultaneously.
5. **Thinking accept-count increases throughput.** A queue only holds waiting connections; a slow system remains slow.
6. **Thinking Jetty's thread idle timeout is the socket idle timeout.** They control two different resources.
7. **Forgetting proxies.** An upstream hop may close connections before the embedded server does.
8. **Setting infinite timeouts without measuring resources.** Many idle connections still consume sockets and file descriptors.
9. **Changing header/form/upload limits without diagnosing the error.** JSON bodies, multipart uploads, and HTTP headers have separate limits.
10. **Copying "standard" numbers without benchmarking.** Appropriate values depend on traffic, CPU, memory, protocols, downstream services, and the OS.

## 19. Short Pre-Deployment Checklist

- [ ] Confirmed the exact web stack, embedded server, and Spring Boot version.
- [ ] Know which connection phase each configured timeout applies to.
- [ ] Know whether HTTP/1.1 or HTTP/2 is used, proxy hops, and per-hop timeouts.
- [ ] Distinguished keep-alive idle timeout, max keep-alive requests, max connections, accept queue, and worker threads.
- [ ] Verified header/body/form/multipart limits match the API contract.
- [ ] Tested behavior under realistic load and with slow-sending clients.
- [ ] Have observability for close/reset/timeout events and a way to roll back config if benchmarks degrade.

## 20. References

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): official reference for `server.tomcat.*`, `server.jetty.*`, `server.undertow.*`, `server.netty.*`, and HTTP limits.
- [Spring Boot 3.3 — Reference Documentation](https://docs.spring.io/spring-boot/3.3/reference/): embedded web server mechanics, configuration, and application operations.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): persistent connection mechanics and message handling in HTTP/1.1.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): stream multiplexing on HTTP/2 connections and hop-by-hop header restrictions.

**Remember:** `connection-timeout`, `keep-alive-timeout`, `idle-timeout`, `max-connections`, and `threads.max` are limits with distinct scopes. Proper configuration begins by identifying the actual server, knowing when each limit applies, and verifying behavior across the full request path.