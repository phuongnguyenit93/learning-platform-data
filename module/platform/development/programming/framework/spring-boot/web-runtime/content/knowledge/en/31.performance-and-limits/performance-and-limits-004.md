# Coordinating Timeouts Across Client, Proxy, Server, and Downstream Services

> **Module:** Spring Boot – web-runtime → **Performance and Limits**. This lesson builds a coherent strategy for coordinating **timeouts** and **end-to-end deadlines** as a request travels from a browser or API client through a reverse proxy/load balancer, to Spring Boot MVC/Tomcat or WebFlux/Netty, and onward to databases and downstream HTTP services. Examples use **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x**, NGINX, and curl; all durations are illustrative values that must be calibrated to your SLOs and real system measurements.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **connect**, **TLS handshake**, **pool acquire**, **request send**, **read inactivity**, **async processing**, **keep-alive idle**, **per-attempt request timeout**, and **overall deadline**.
2. Identify who enforces each timeout: client, NGINX/ingress, Spring MVC/Tomcat, Spring WebFlux/Reactor Netty, outbound HTTP client, DB/driver, or downstream.
3. Explain accurately that NGINX `proxy_read_timeout` only bounds gaps between reads, `server.tomcat.connection-timeout` does not bound controller duration, and `spring.mvc.async.request-timeout` applies to MVC asynchronous requests.
4. Design a time budget so downstream calls terminate before the caller gives up, leaving margin to return an error response.
5. Configure a `RestClient` example with JDK `HttpClient` connect/request timeouts, and know how to configure `WebClient` with Reactor Netty plus `Mono.timeout`.
6. Distinguish HTTP statuses 408, 502, 503, and 504 from NGINX access log `499` and client-side timeouts that produce no HTTP response.
7. Understand why **a timeout does not guarantee cancellation of work** on the server, DB transaction, or downstream.
8. Coordinate retry budgets, concurrency, connection pools, cancellation, streaming/SSE, and observability.
9. Run and verify a Java 17+ Spring Boot application with a simulated fast/slow/failing downstream, identifying the error owner via curl and NGINX logs.

## 2. A Request Crosses Multiple Layers

~~~text
Browser / Mobile / API Client
       |
       | HTTP client overall timeout
       v
CDN / API Gateway / NGINX
       |
       | connect timeout to upstream
       | read/send inactivity timeout
       | total request deadline if gateway supports it separately
       v
Spring Boot HTTP server
       | Tomcat / Reactor Netty
       | request parse, queue, security, controller
       | async processing deadline (if async)
       v
Application service
       |
       | outbound HTTP RestClient / WebClient
       | connection pool -> DNS -> TCP -> TLS
       | write request -> read response
       v
Downstream REST API / Database
       |
       | query/operation/transaction timeout
       v
Response returns through each hop
~~~

Timeouts are **per-layer** policies. There is no single Spring Boot property that automatically forces every HTTP client, reverse proxy, DB query, and browser to share one deadline.

Examples of conflicting timeouts:

- Browser waits 2 s, NGINX waits 30 s, app waits on downstream 60 s: the user has already given up while threads and sockets remain held.
- NGINX waits 1 s with no upstream bytes, app sets a 3 s timeout: the gateway may emit 504 **before** the app can return an error JSON.
- Outbound client times out at 1 s and retries 5 times with backoff: total processing exceeds the API client's 3 s timeout.
- Upstream streaming emits one chunk every 1 s, NGINX `proxy_read_timeout=2s`: the stream stays alive well past 2 s because the timer measures **idle gaps between reads**, not total response duration.
- A team sets `server.tomcat.connection-timeout=2s` expecting a 2 s controller limit: that property mainly governs the **request-line receive** phase after accepting a connection, not business processing.

**Goal:** design a route-wide time budget and pick the **right type** of timeout, rather than setting every variable named "timeout" to the same number.

## 3. Timeout Vocabulary and Exact Scopes

| Timeout | Interval Measured | Typical Owner | What It Is Not |
|---|---|---|---|
| DNS resolution | Hostname lookup | Client resolver/OS/runtime | Not always included in TCP connect timeout |
| TCP connect | Establishing a new connection to peer | JDK HttpClient, Reactor Netty, proxy | Does not bound the full response body |
| TLS handshake | Waiting for handshake + certificate validation | TLS connector/HTTP client | Does not replace an application deadline |
| Pool acquire | Waiting for an idle pooled connection | HTTP connection pool, JDBC pool | Does not automatically include connect/read time |
| Request-header receive | Waiting for client to send full headers | NGINX/Tomcat | Does not bound controller execution |
| Request-body receive | Time or inactivity gaps reading an upload | NGINX/HTTP server | Not necessarily total upload duration |
| Proxy request send | Gaps between proxy writes to upstream | NGINX `proxy_send_timeout` | Not the whole request operation |
| Upstream read inactivity | Gaps between upstream reads | NGINX `proxy_read_timeout` | Not a total response deadline |
| Client response/request timeout | HTTP implementation timeout | JDK/Jackson connector/Netty | Does not automatically span multi-attempt retries |
| MVC async request | Async Servlet request lifecycle | `spring.mvc.async.request-timeout` | Does not automatically apply to synchronous `@GetMapping` |
| Keep-alive idle | Idle connection between requests | `server.tomcat.keep-alive-timeout` | Not business handler duration |
| End-to-end deadline | Total time for an operation from the caller | Client/gateway/app policy | Different from idle, connect, and keep-alive |
| DB query/transaction | A single query or transaction | Driver/DB/transaction manager | Does not replace an HTTP client deadline |

Even the same term `readTimeout` does not always mean the same thing. In Spring Framework 6.1, `JdkClientHttpRequestFactory.setReadTimeout(Duration)` sets the timeout via JDK `HttpRequest.Builder.timeout(Duration)` for the request, whereas `URLConnection.setReadTimeout` relates to waiting on network reads. **Always read the exact connector/version documentation** before translating durations.

Three questions to ask whenever reading any timeout setting: **(1) when does the timer start; (2) what resets it; (3) upon expiration, who closes the socket, cancels the task, or emits the HTTP error?**

## 4. Designing an End-to-End Time Budget

Suppose a caller requires a REST JSON response within at most **3,500 ms** from start:

| Component | Example Value | Role |
|---|---:|---|
| Browser/API client overall | 3,500 ms | User-facing upper bound |
| Gateway with **hard total request deadline** if supported | 3,200 ms | Fails before client so an HTTP error can still be shown |
| Spring application overall budget | 2,800 ms | Leaves margin for serialization/error/egress |
| Outbound call operation budget | 2,100 ms | Cuts dependency early |
| Validation, queue, serialization, network margin | ~400–700 ms depending on route | Buffer for tail latency and error delivery |

**This is a design-level time budget, not something NGINX automatically enforces for 3.2 s when you set `proxy_read_timeout=3.2s`.** That NGINX directive measures inactivity, not total duration. If the gateway lacks a hard deadline, the application must enforce an appropriate policy in code/orchestration; likewise, do not invent a non-existent Boot property expecting it to cap every synchronous MVC handler.

~~~text
t = 0 ms                                      3500 ms
Client:  |----------------------------------------|
Gateway: |-----------------------------------|     3200, if hard deadline exists
App:     |------------------------------|          2800, logical deadline
B call:  |---------------------|                   2100, maximum operation
                          ^ app still has time to handle and return an error
~~~

### Computing Along the Critical Path

A workflow calling service B then C **sequentially** takes roughly the sum of both calls plus overhead. A workflow calling B and C **in parallel** has a critical path near the slower branch plus merge/serialization, while still accounting for queues, scheduling, pool contention, and cancellation.

Sequential example:

~~~text
Read/auth/local work   <= 200ms
B attempt              <= 850ms
C attempt              <= 900ms
Serialize+send reserve <= 250ms
--------------------------------
Plan                  ~2,200ms
~~~

If B consumes its full 850 ms, C must receive **the remaining time** rather than a fresh full timeout that pushes the total past the caller's deadline. Reserving time to send a clean public error response is a practical requirement, not just arithmetic.

### An Expression to Review

~~~text
T_total ≈ T_queue + T_auth + Σ T_attempts
        + Σ T_backoffs + T_DB + T_local
        + T_serialize + T_network_egress

Requirement: T_total <= remaining caller budget
~~~

Terms running in parallel must follow the dependency graph / critical path rather than blind summation. Jitter, GC pauses, and OS scheduling can push latency past expectations; a timeout is not a millisecond-exact SLA.

## 5. NGINX: Connect, Send, and Read Differ

Example test NGINX server sitting in front of Spring Boot on port 8080:

~~~nginx
server {
    listen 8081;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;

        proxy_connect_timeout 500ms;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
    }
}
~~~

This config belongs to **NGINX**, not `application.properties`. In a Kubernetes Ingress environment, use the annotations/resources matching your ingress controller and version rather than pasting raw NGINX snippets blindly.

- `proxy_connect_timeout 500ms` bounds establishing a new connection from NGINX to the upstream HTTP server.
- `proxy_send_timeout 2s` bounds **gaps between successive writes** of the request from proxy to upstream; not total request transmit time.
- `proxy_read_timeout 2s` bounds **gaps between successive reads** of the response from upstream; not time from request start to response completion.
- `proxy_http_version 1.1` selects the version only for the proxy→upstream hop; it does not enable WebSocket or end-to-end HTTP/2.
- `X-Request-ID` can correlate logs when policy allows; the server should only trust request IDs from trusted hops rather than letting arbitrary clients forge evidence.

### If Upstream Sends Headers and Then Stalls

An upstream can send `HTTP/1.1 200 OK` and part of the body before going silent for over 2 s. At that point, the proxy **may have already committed the response** to the browser; upon timeout, it cannot always switch to a 504 JSON body. The client may observe a truncated response, EOF, or JSON parse failure. Always test timeouts **before first byte** and **between streaming chunks** as two separate cases.

### NGINX Client-Facing Timeouts

Directives `client_header_timeout`, `client_body_timeout`, `send_timeout`, and `keepalive_timeout` govern different phases:

- `client_header_timeout`: waiting to receive full request headers; may emit 408 on expiration.
- `client_body_timeout`: gap between successive reads of an upload body.
- `send_timeout`: gap while transmitting response bytes to the client per NGINX semantics.
- `keepalive_timeout`: idle connection waiting for the next request.

A large upload with continuous slow traffic can outlast a per-read timeout; enforcing total upload duration requires a dedicated policy. Choosing 2 s for REST JSON does not make it valid for SSE, video, file uploads, or long polling.

## 6. Spring Boot MVC/Tomcat: Do Not Misread Connector Timeouts

Some Boot 3.3 properties:

~~~properties
server.port=8080

# Tomcat waits for the request URI line after accepting a connection.
server.tomcat.connection-timeout=5s

# Tomcat keeps an idle connection open between HTTP requests.
server.tomcat.keep-alive-timeout=15s

# Spring MVC asynchronous request processing.
spring.mvc.async.request-timeout=2800ms
~~~

**Do not** infer a 5 s or 2.8 s synchronous controller deadline from those three lines. For example:

~~~java
// Illustrative method inside an MVC @RestController.
@GetMapping("/slow")
public String slow() throws InterruptedException {
    Thread.sleep(10000);
    return "done";
}
~~~

This controller can occupy a Servlet worker thread for 10 seconds regardless of `server.tomcat.connection-timeout=5s`. If the client or NGINX gives up at second 3, this method can keep sleeping until finished unless a real cancellation mechanism interrupts it.

### MVC Async Request Timeout

When a controller returns `Callable`, `DeferredResult`, or another MVC-supported async response, `spring.mvc.async.request-timeout` or a per-request timeout governs waiting for the **async response**:

~~~java
// Snippet inside an MVC controller:
@GetMapping("/async")
public Callable<String> work() {
    return () -> {
        Thread.sleep(3000);
        return "done";
    };
}
~~~

A Spring MVC async timeout does not guarantee the underlying Java computation or DB query is killed immediately. With `DeferredResult`, handle `onTimeout`/`onCompletion` alongside cancellation logic and executor sizing. Never dump unbounded blocking tasks onto an async executor merely to avoid tying up Servlet request threads.

### WebFlux Server

With Spring WebFlux / Reactor Netty, settings like `server.netty.idle-timeout` govern connector channel idleness, not `spring.mvc.async.request-timeout`. You can apply Reactor `timeout(Duration)` per reactive route pipeline, while testing cancellation, error signaling, and response commit behavior. Do not configure Tomcat properties expecting them to affect Netty.

## 7. Spring RestClient: Outbound Request Timeouts

Spring Framework 6.1+ provides the fluent blocking `RestClient`. You can choose JDK `HttpClient` as its transport:

~~~java
// Snippet inside @Configuration:
HttpClient javaHttp = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(250))
        .build();

JdkClientHttpRequestFactory requestFactory =
        new JdkClientHttpRequestFactory(javaHttp);

requestFactory.setReadTimeout(Duration.ofMillis(700));

RestClient client = RestClient.builder()
        .baseUrl("https://partner.example.test")
        .requestFactory(requestFactory)
        .build();
~~~

- `HttpClient.connectTimeout` governs **establishing a new connection**; it does not apply identically to an already reused connection.
- `JdkClientHttpRequestFactory.setReadTimeout(Duration)` in Spring 6.1 maps to JDK `HttpRequest.Builder.timeout(Duration)` for the request; do not interpret it as NGINX's interval read timeout.
- DNS, TLS, and pool acquisition may follow different semantics per connector.
- If a request retries, a 700 ms per-attempt timeout does not make all 3 attempts finish within 700 ms.

Other HTTP clients such as Apache HttpClient 5, Reactor Netty, or JDK `URLConnection` expose different timeout methods. Copying the same `700ms` across clients does not guarantee identical behavior.

### When Using WebClient and Reactor Netty

~~~java
// Snippet requiring Reactor Netty and Spring WebClient connector imports.
HttpClient netty = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
~~~

`responseTimeout` follows Reactor Netty HTTP client semantics and does not act as the deadline for an entire workflow containing retries, backoff, and DB work. You can add:

~~~java
// Illustrative snippet; OrderDto and id are defined by the application.
Mono<OrderDto> operation = webClient.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .bodyToMono(OrderDto.class)
        .timeout(Duration.ofMillis(900));
~~~

`Mono.timeout` starts upon subscription and times out the reactive publisher if it does not finish on time. On error, the subscription may be canceled, yet the downstream service is **not guaranteed** to halt processing or roll back transactions. With `DataBuffer` streaming and pooled memory, cancellation also requires proper cleanup per API contracts.

## 8. Runnable Example: Spring Boot 3.3, Java 17, and Fake Downstream

Lab goal: create **two HTTP hops** inside one process while issuing a real outbound HTTP request. The HTTP server remains Servlet MVC/Tomcat—WebFlux is not needed:

~~~text
curl GET /api/relay/fast|slow|error
       |
       v
Spring MVC ProxyController A :8080
       |
       | RestClient (JDK HttpClient)
       | connect 250ms, request 700ms
       v
FakeDownstream B :8080
       |
       +-- delay 100ms -> JSON 200
       +-- delay 1200ms -> slower than A's timeout
       +-- error -> 503 + internal marker
~~~

Placing fake B inside the same process keeps the lab self-contained. In production it is a separate service with proper URLs, certificates, and network policies. A timeout in A does **not** mean B's `Thread.sleep` was interrupted.

### 8.1. Structure

~~~text
timeout-budget-demo/
  pom.xml
  src/main/java/example/timeout/TimeoutBudgetDemoApplication.java
  src/main/resources/application.properties
~~~

### 8.2. Maven pom.xml

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
    <groupId>example</groupId>
    <artifactId>timeout-budget-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

No database, WebSocket, or messaging broker is included. The Spring Boot BOM manages compatible Spring Web 6.1 and Tomcat versions. `RestClient` comes with Spring Web in `starter-web`; Spring Boot configures `RestClient.Builder` for injection.

### 8.3. application.properties

~~~properties
server.port=8080

# NOT a total controller timeout:
server.tomcat.connection-timeout=5s
server.tomcat.keep-alive-timeout=15s

# Limit default Boot errors from accidentally leaking stack traces:
server.error.include-message=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

### 8.4. Complete Single Java File

Create `src/main/java/example/timeout/TimeoutBudgetDemoApplication.java`:

~~~java
package example.timeout;

import java.net.SocketTimeoutException;
import java.net.http.HttpClient;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@SpringBootApplication
public class TimeoutBudgetDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimeoutBudgetDemoApplication.class,
                args);
    }

    @Configuration
    static class ClientConfig {

        @Bean
        RestClient destinationClient(RestClient.Builder builder) {
            HttpClient jdkClient = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofMillis(250))
                    .build();

            JdkClientHttpRequestFactory factory =
                    new JdkClientHttpRequestFactory(jdkClient);

            // On JDK client, maps to request timeout:
            factory.setReadTimeout(Duration.ofMillis(700));

            return builder
                    .baseUrl("http://localhost:8080")
                    .requestFactory(factory)
                    .build();
        }
    }

    @RestController
    static class FakeDestination {

        @GetMapping("/target/delay")
        public Map<String, Object> delay(
                @RequestParam(defaultValue = "0") int ms)
                throws InterruptedException {

            if (ms < 0 || ms > 2000) {
                throw new IllegalArgumentException("Invalid delay");
            }

            Thread.sleep(ms);
            return Map.of("source", "downstream",
                          "delayMs", ms);
        }

        @GetMapping(value = "/target/error",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public ResponseEntity<String> error() {
            return ResponseEntity
                    .status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("INTERNAL_DB_HOST=db.private.lan");
        }
    }

    @RestController
    static class ApiController {
        private final RestClient client;

        ApiController(RestClient destinationClient) {
            this.client = destinationClient;
        }

        @GetMapping("/api/relay/{scenario}")
        public ResponseEntity<?> relay(
                @PathVariable String scenario) {

            String uri = switch (scenario) {
                case "fast" -> "/target/delay?ms=100";
                case "slow" -> "/target/delay?ms=1200";
                case "error" -> "/target/error";
                default -> null;
            };

            if (uri == null) {
                return problem(HttpStatus.BAD_REQUEST,
                        "Invalid test scenario.");
            }

            try {
                Map<?, ?> data = client.get()
                        .uri(uri)
                        .retrieve()
                        .onStatus(HttpStatusCode::isError,
                            (request, response) -> {
                                // Do not copy upstream error body
                                // to the client.
                                throw new UpstreamStatus(
                                    response.getStatusCode().value());
                            })
                        .body(Map.class);

                if (data == null) {
                    return problem(HttpStatus.BAD_GATEWAY,
                            "Invalid downstream service response.");
                }

                return ResponseEntity.ok(Map.of("result", data));

            } catch (UpstreamStatus ex) {
                return problem(
                    ex.code == 503
                        ? HttpStatus.SERVICE_UNAVAILABLE
                        : HttpStatus.BAD_GATEWAY,
                    "Downstream service is currently unavailable.");

            } catch (ResourceAccessException ex) {
                return isTimeout(ex)
                    ? problem(HttpStatus.GATEWAY_TIMEOUT,
                        "Downstream service responded too slowly.")
                    : problem(HttpStatus.BAD_GATEWAY,
                        "Cannot connect to downstream service.");

            } catch (RestClientException ex) {
                return problem(HttpStatus.BAD_GATEWAY,
                        "Unable to process downstream service response.");
            }
        }

        private static boolean isTimeout(Throwable ex) {
            for (Throwable cause = ex; cause != null;
                    cause = cause.getCause()) {
                if (cause instanceof HttpTimeoutException
                        || cause instanceof SocketTimeoutException) {
                    return true;
                }
            }
            return false;
        }

        private static ResponseEntity<ProblemDetail> problem(
                HttpStatus status, String detail) {
            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, detail);
            body.setTitle("Downstream service error");

            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }

        private static final class UpstreamStatus
                extends RuntimeException {
            final int code;

            UpstreamStatus(int code) {
                super("upstream status");
                this.code = code;
            }
        }
    }
}
~~~

### 8.5. Why Does This Example Hit the Core Concepts?

- `/target/delay` simulates service B with controlled response times.
- `/api/relay` acts as service A making a **real outbound HTTP call** via `RestClient`, not just calling a local Java method.
- `connectTimeout(250ms)` has nothing to do with a 250 ms Tomcat controller limit; it bounds establishing a TCP connection to B.
- `factory.setReadTimeout(700ms)` with the JDK client bounds an HTTP request; B's 1,200 ms response is normally aborted by A.
- `onStatus` throws an exception carrying only the status code when B fails; it never reads, logs, or echoes `INTERNAL_DB_HOST` to the public client. In production, large error bodies can affect connection reuse; check your HTTP client's contract and enforce size/overall limits.
- `ResourceAccessException` can wrap timeouts or other connection errors. The code walks the cause chain for `HttpTimeoutException` and `SocketTimeoutException`, though other HTTP clients use different exception types; in practice, log a sanitized failure category.
- Public errors return `ProblemDetail` with `Cache-Control: no-store`, avoiding raw exception messages in responses.
- The demo **does not yet enforce a hard total app deadline** across all controller routes—it only enforces the 700 ms outbound request timeout; keep this distinction clear rather than overclaiming the example's scope.

**Simulation limit:** downstream `Thread.sleep` can still run to completion after the caller times out. Preventing orphaned work in production requires deadline/cancellation propagation and idempotency for mutations.

### 8.6. Running on a Machine with Java 17 and Maven

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i --max-time 3 http://localhost:8080/api/relay/fast
curl -i --max-time 3 http://localhost:8080/api/relay/slow
curl -i --max-time 3 http://localhost:8080/api/relay/error
curl -i --max-time 3 http://localhost:8080/api/relay/unknown
~~~

Expected outcomes (subject to warm-up/OS jitter on busy machines):

| URL | Status | Reason |
|---|---:|---|
| `/api/relay/fast` | 200 | B responds in ~100ms < 700ms |
| `/api/relay/slow` | 504 | B sleeps 1,200ms > 700ms request timeout |
| `/api/relay/error` | 503 | B returns 503 and app maps a safe public error |
| `/api/relay/unknown` | 400 | Only declared scenarios are permitted |

Illustrative 200 body (JSON key order is not guaranteed):

~~~json
{
  "result": {
    "source": "downstream",
    "delayMs": 100
  }
}
~~~

Illustrative 504 body:

~~~json
{
  "type": "about:blank",
  "title": "Downstream service error",
  "status": 504,
  "detail": "Downstream service responded too slowly."
}
~~~

If the slow test unexpectedly fails even on the fast path because the environment is bogged down, check app startup, CPU contention, JVM warm-up, and localhost ports before re-running. Never replace 700 ms with an infinite timeout just to make a test "pass".

### 8.7. Client Timeout **Before** App Timeout

~~~bash
curl -i --max-time 0.3 http://localhost:8080/api/relay/slow
~~~

When curl waits only 300 ms, it exits with **exit code 28** before A can return HTTP 504 after the 700 ms outbound timeout. The client receives no HTTP 504 status in this case, while backend/outbound work may still be running.

Distinguish a **caller-initiated abort** from an HTTP 504 **actually emitted by the application or gateway**. To see the app's 504, curl's overall `--max-time` (3 s) must exceed the outbound timeout.

### 8.8. Testing Through NGINX If a Proxy Is Present

Using the test config from Section 5, proxying port 8081 to app port 8080:

~~~bash
curl -i --max-time 3 http://localhost:8081/api/relay/fast
curl -i --max-time 3 http://localhost:8081/api/relay/slow
~~~

With `proxy_read_timeout 2s`, the app's 504 around 700 ms is forwarded by NGINX—that is a **Spring-generated 504**. If a controller stops sending upstream bytes for more than 2 s, NGINX itself generates an **NGINX 504** while upstream may still be running; NGINX logs distinguish the two.

## 9. Timeouts Across Retry Attempts

An outbound HTTP operation may make multiple attempts:

~~~text
attempt 1: max timeout   800ms
backoff:                 200ms
attempt 2: max timeout   800ms
app overhead:            150ms
--------------------------------
approx total:           1950ms
~~~

If you only configure `per-attempt timeout=800ms` and retry 10 times, the overall operation can blow past the outer deadline by seconds. You need:

1. **Per-attempt timeout:** prevents a single HTTP exchange from hanging too long.
2. **Overall operation deadline:** caps the entire retry sequence + backoff + local processing.
3. **Retry budget:** attempts, backoff, and cost must fit inside remaining time.
4. **Idempotency:** never retry mutations blindly; a timeout can occur **after B has committed**.

### Illustrative Reactor Operator Ordering

~~~java
// Snippet; call and isRetryable are defined by the application:
Mono<ResultDto> bounded = call
    .timeout(Duration.ofMillis(700))
    .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
        .filter(this::isRetryable))
    .timeout(Duration.ofMillis(1800));
~~~

Here the inner timeout applies to each resubscription (each attempt), while the outer timeout bounds the entire retry/backoff sequence. Requires Reactor `Retry` imports and definitions for `ResultDto`/`call`/`isRetryable`; this is not a standalone Java file. With response streaming or side effects, retry semantics grow subtler—always test actual attempt counts.

Never let the gateway, service mesh, and application **all retry** unchecked: 3 retries at two layers can multiply downstream calls. Retrying 400/401/403, invalid TLS certificates, or oversized bodies is usually wrong; 429/503 may be retried selectively using a trustworthy `Retry-After`, jitter, and remaining deadline budget.

## 10. Remaining-Time Budget and Deadline Propagation

Shrink downstream timeouts by the time already spent:

~~~text
App budget:                       2800ms
Already elapsed:                   500ms
Remaining:                        2300ms
Reserve for serialize/network:     300ms
Max B operation:                  2000ms
~~~

A Java helper illustrating monotonic time:

~~~java
// Snippet placed inside a valid class, not a standalone Java file.
record Deadline(long expiresAtNanos) {
    static Deadline after(Duration limit) {
        return new Deadline(System.nanoTime()
                + limit.toNanos());
    }

    Duration remaining() {
        return Duration.ofNanos(Math.max(0L,
                expiresAtNanos - System.nanoTime()));
    }
}
~~~

`System.nanoTime()` measures elapsed monotonic time **within the same process**, not a UTC wall-clock epoch to send across machines. For short deadlines and valid durations this illustrates the concept; production code must handle validation/overflow and lifecycle.

~~~java
Duration budget = deadline.remaining()
        .minus(Duration.ofMillis(300));

if (budget.isZero() || budget.isNegative()) {
    throw new TimeoutException("Budget exhausted");
}

Duration attempt = budget.compareTo(
        Duration.ofMillis(700)) < 0
        ? budget : Duration.ofMillis(700);
~~~

Pass `attempt` into the actual HTTP client request or connector configuration rather than calculating it and leaving it unused. When performing multiple outbound calls, recompute remaining budget at each step—never reset it. For clients lacking dynamic per-request timeouts, select an appropriate request factory or whole-operation cancellation control.

### Propagating Deadlines Over HTTP

You can define an internal header contract:

~~~http
X-Request-Timeout-Ms: 1900
X-Request-ID: req-842f...
~~~

This is a **custom contract**, not a header automatically enforced by Spring Boot or NGINX. Define clear units, ranges, trusted callers, and clamp to a server-side maximum. Never let public Internet clients send huge values that give themselves infinite server timeouts. If passing absolute timestamps, account for clock skew; inside one JVM, stick to monotonic timers. Distributed tracing propagation provides visibility across hops, **not automatic deadline enforcement**.

A call B→C must pass **the remaining budget**, never copying the full initial budget A sent.

## 11. Browser Deadlines via AbortController

A JavaScript frontend can use:

~~~javascript
async function loadReport() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 3500);

  try {
    const response = await fetch("/api/report", {
      method: "GET",
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error("HTTP " + response.status);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}
~~~

When the timer fires, `fetch` rejects with `AbortError`. Newer environments also support `AbortSignal.timeout(3500)`. Aborting in the browser **does not mean** the server rolls back a DB transaction or cancels a downstream task.

With `POST /payments`, a caller timeout can occur **after the server has committed**. Clients must not unconditionally re-send the same POST payload; require idempotency keys and status reconciliation. A deadline caps how long the caller waits, not a guarantee that zero side effects occurred.

## 12. Cancellation Does Not Automatically Flow Across Hops

A sequence can unfold like this:

1. Client aborts at t=2s.
2. NGINX sees the client close the connection and records `499` in its access log.
3. The Servlet controller keeps waiting on `RestClient`.
4. HTTP client A→B may time out or cancel, while B continues processing the request.
5. B may already write to the DB or enqueue a job.
6. When A tries to return a response, the client socket is already closed: broken pipe or reset errors appear.

### MVC Synchronous

A synchronous controller calling a blocking SDK is not guaranteed to be interrupted when the client disconnects. Configure bounded outbound timeouts, DB query timeouts, bounded thread pools, and explicit task cancellation where APIs support it. Spawning ad-hoc `CompletableFuture` tasks without managing executors and cancellation can make matters worse.

### MVC Async

`DeferredResult`/`Callable` have their own async timeout lifecycle. `DeferredResult.onTimeout`/`onCompletion` can trigger cleanup, yet the underlying task must actually support cancellation/interruption. Returning an async timeout response does not automatically kill running threads or DB queries.

### WebFlux / Reactive

`Mono.timeout` triggers a cancellation signal on the reactive subscription, letting connectors close/dispose response resources. However, if operators invoke blocking code or a downstream ignores cancellation, work can continue anyway. With pooled `DataBuffer` instances, follow proper ownership/release/discard rules. Never claim "reactive always halts work instantaneously".

### Database / Transactions

Driver statement query timeouts, transaction timeouts, and DB server limits do not replace HTTP deadlines. B can commit before A loses its response; retries require idempotency and transactional reconciliation. Canceling a running query also takes time for rollback and connection cleanup.

## 13. Connection Pools and Queue Wait Time

An HTTP client has a bounded connection pool. When the pool is full, new requests wait in **pending acquire** before TCP connect/read even begins. If you only set `responseTimeout=700ms` while a request waits 2 s for a connection, the overall operation blows past its budget unless a hard total deadline covers pool waiting too.

Similarly, HikariCP has `connectionTimeout` for borrowing a DB connection; that is distinct from query execution timeout. A 1 s query timeout does not prevent a request from having already waited 3 s on DB pool acquisition.

As throughput grows, approximating Little's Law:

~~~text
L = arrival_rate × average_time_in_system

100 requests/s × 10 seconds ≈ 1000 in-flight requests
~~~

This is a steady-state approximation, not a universal prediction formula. Rising wait latency inflates in-flight requests, triggering thread exhaustion, retries, and timeout storms.

**Do not raise Tomcat threads and HTTP timeouts as a knee-jerk reaction.** First inspect worker pools, outbound connection pools, DB pools, queueing, GC, CPU, slow downstreams, and retries. Add bulkheads/concurrency limits, circuit breakers, and load shedding where appropriate.

## 14. HTTP 408, 499, 502, 503, and 504 Differ

| Signal | Likely Emitter | Common Meaning |
|---|---|---|
| `408 Request Timeout` | Receiving server/proxy | Client failed to finish sending the request in time; does not mean slow downstream |
| `499` | **NGINX access log** | Client closed connection before NGINX returned a response; not a standard HTTP status sent to clients |
| `502 Bad Gateway` | Proxy/gateway app | Invalid or missing upstream response, connection reset, protocol error, or transport error per config |
| `503 Service Unavailable` | App/proxy | Service temporarily overloaded/unavailable, or dependency unavailable per contract |
| `504 Gateway Timeout` | Proxy or gateway app | Upstream failed to respond within timeout policy; identify the owner |
| curl `exit code 28` | Caller using curl | Curl timed out locally; there may be **no HTTP status** |
| Browser `AbortError` | Browser/JS | Fetch aborted; backend may still be running |

When Spring maps an outbound JDK timeout to 504, NGINX merely forwards Spring's 504. When NGINX generates 504 due to `proxy_read_timeout` before Spring sends headers, the body may be NGINX HTML rather than the app's `ProblemDetail`. When a client aborts early, no HTTP response may be observed. Use correlation IDs and logs/traces across every hop.

HTTP `408` pertains to **receiving the request from the client**, unlike `504` when a gateway **waits on an upstream**. Avoid a blanket catch-all mapping "every timeout → HTTP 500" when more accurate HTTP semantics exist.

## 15. Safe Error Contract for Timeouts

An application-generated error response might look like:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Service temporarily slow",
  "status": 504,
  "detail": "Did not receive a timely response."
}
~~~

This is an **illustrative** application-generated JSON payload, not NGINX's default body. Internal errors must never leak raw stack traces, hostnames, database URLs, access tokens, or exception messages. For service-to-service authentication failures, an upstream 401/403 should not automatically become a 401/403 to the public caller; map per your API contract.

If a streaming body has already started sending, the response may **already be committed**; on timeout, you will not always have the chance to switch the HTTP status to 504 or send a complete `ProblemDetail`. Design streaming error protocols and cancellation handling separately.

## 16. SSE, WebSockets, and Long-Running Jobs

### SSE / Server Streaming

Server-Sent Events can keep an HTTP response open for many minutes:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

: heartbeat

event: progress
data: 20
~~~

`: heartbeat` is an SSE comment line that keeps inactivity timers alive if bytes are actually flushed through the proxy. If NGINX `proxy_read_timeout=30s`, pick a heartbeat interval shorter than 30 s per your actual config, while checking proxy buffering and client reconnects. Never apply a hard 3-second REST JSON deadline to an SSE stream intended to stay open long-term.

### WebSocket

WebSockets have their own handshake and connection lifecycle. Ping/pong frames, heartbeats, idle timeouts, max lifetime, connection limits, and auth/origin policies must match clients and proxies. Do not assume HTTP `server.tomcat.keep-alive-timeout` covers all WebSocket idle handling.

### File Upload/Download

Multi-GiB uploads/downloads can run for minutes. NGINX `client_body_timeout`/`proxy_send_timeout` are progress-interval controls; you also need total upload limits, byte quotas, temp storage cleanup, and bandwidth/concurrency policies. Never raise every API timeout to 30 minutes just to accommodate one file upload route.

### Long Jobs: Do Not Hold Synchronous Requests Indefinitely

Instead of holding an HTTP connection open for 2 minutes to build a report, design:

~~~text
POST /jobs -> 202 Accepted, returns jobId
GET /jobs/{jobId} -> status pending/running/done/failed
GET /jobs/{jobId}/result -> result once completed
~~~

`202` is only the HTTP pattern; it requires durable queues/workers/job state, idempotency, and authorization. This is usually far cleaner than stretching client, gateway, app, and downstream timeouts everywhere for inherently long work.

## 17. Retries, Circuit Breakers, and Backoff Within Budget

Retries help with transient network errors or HTTP 429/503 under proper policies, but you must account for the total:

- Each attempt has its own timeout.
- Maximum attempt count must be bounded.
- Backoff + jitter consume the overall time budget.
- App, gateway, and service mesh layers must not multiply retries independently.
- Do not retry 400/401/403 or invalid TLS certificates as transient errors.
- Do not retry non-idempotent POST/PUT mutations without an idempotency protocol.
- Circuit breakers and bulkheads shed traffic from failing dependencies; **they do not replace timeouts**.

A retry policy can honor `Retry-After` when a downstream sends a valid value, provided a huge `Retry-After` does not push the request past the caller's deadline. If remaining time leaves zero budget for another attempt, fail fast and return an error rather than retrying anyway.

## 18. Identifying Timeout Owners via Logs and Traces

To investigate a 504, you need both **proxy-side** and **app-side** telemetry. NGINX can log:

~~~nginx
log_format upstream_timing
    '$request_id status=$status '
    'rt=$request_time '
    'uct=$upstream_connect_time '
    'uht=$upstream_header_time '
    'urt=$upstream_response_time';

access_log /var/log/nginx/upstream_timing.log upstream_timing;
~~~

`$request_time` reflects NGINX-side duration per its semantics; `$upstream_connect_time`, `$upstream_header_time`, and `$upstream_response_time` capture upstream phases. When multiple upstream attempts occur, these timing variables may hold multiple values or `-`. Never guess a 504 owner from a single number without logs.

Spring Boot offers Micrometer/Actuator observations (when configured) tracking server requests and outbound HTTP client timings, exception categories, statuses, pool saturation, retries, cancellations, and DB/connection-acquire durations. Exact metric names vary by version and instrumentation; inspect the live registry rather than hardcoding unverified names.

Recommended safe structured trace fields:

~~~text
requestId=...
routeTemplate=GET /api/relay/{scenario}
service=downstream-catalog
statusFamily=5xx
outboundTimeout=true
elapsedMs=...
attempt=1
remainingBudgetMs=...
~~~

Never log raw Authorization headers, Cookies, signed URLs, PII-bearing request bodies, or upstream stack traces to public telemetry. Correlation IDs require clear trust and lifecycle policies.

### Distinguishing Statuses Across Layers

- NGINX 504 while the app runs for 5 seconds: proxy timed out early.
- Spring returns 504 after 700 ms outbound wait, NGINX forwards it: HTTP client/dependency timeout.
- Curl exit 28 at 300 ms, app logs 504 at 700 ms: caller timed out first.
- NGINX 499 usually means the client closed the connection, not proof of an app bug.
- A 502 may indicate an upstream reset or protocol failure rather than a timeout.

## 19. Fault-Injection Test Matrix

| Case | Setup | Expected Observation |
|---|---|---|
| Fast dependency | Fake downstream 100 ms | 200 before caller deadline |
| Slow dependency | Fake downstream 1,200 ms, client timeout 700 ms | App maps cleanly to 504 |
| Upstream HTTP 503 with internal marker | Fake `/target/error` | Public 503 hides internal strings |
| Fast client timeout | curl `--max-time 0.3` | Curl exit 28, do not expect HTTP 504 |
| Proxy idle read timeout | NGINX 2 s, upstream sends no bytes >2 s | Proxy 504 or truncated response depending on commit |
| Chunked response making progress | Each chunk faster than read-idle window | Can exceed 2 s overall; verify semantics |
| Slow-drip upload client | Inject gaps exceeding `client_body_timeout` | NGINX may return 408 |
| SSE heartbeat | Send within interval, disable proxy buffering properly | Stream stays alive per policy |
| WebSocket idle | Disable ping/pong or heartbeat | Connection closes per server/proxy policy |
| DB pool exhaustion | Saturate active connections | Distinguish pool acquire timeout from query timeout |
| Downstream TCP refused | Stop service B | Public 502/503 per contract, no leaks |
| Invalid TLS | Wrong SAN/chain certificate | Fails safely, never disable verification |
| Retries exceed budget | Intentional delays + backoff | Overall deadline stops retries |
| Client abort after mutation | POST commits then cuts connection | Idempotency/status reconciliation |
| Peak concurrency | Load 50/100 requests against slow B | Thread/pool/queue/cancel metrics stay stable |
| Long async task | Async controller/`DeferredResult` timeout | Cleanup callbacks and worker lifecycle |
| Proxy-generated 504 | Handler hasn't sent headers yet | Gateway identified as error owner |
| Committed response | Stream partial body then stall | EOF/truncation handling, do not promise JSON 504 |

Never assert exact `700 ± 1ms` timeouts in automated tests; scheduling, GC/JIT, network, and timer resolution cause wall-time jitter. Leave clear separation, such as 100 ms vs 1,200 ms against a 700 ms limit. Verify **status + exception category + cleanup + resource release**, not just response text.

## 20. Symptom-Based Troubleshooting

| Symptom | Likely Source | Where to Inspect |
|---|---|---|
| NGINX 504 after ~2 s, Spring runs ~5 s | Proxy read inactivity shorter than app work | NGINX logs + app traces + `proxy_read_timeout` |
| Both direct and proxied calls return 504 ~700 ms | `RestClient` outbound timeout | JDK `HttpClient` cause, downstream latency |
| Browser `AbortError` ~3 s, server logs 200 after 8 s | Browser aborted early | Client timeout, app deadline, cancellation |
| High NGINX 499s under load | Clients disconnecting while waiting | Client timeouts, retries, server queues |
| Timeouts spike after deploy | Dependencies, pools, GC, new retry policy | Compare dependency graph, metrics, traces |
| SSE drops after 60 s idle | Proxy read idle or browser/network idle | Heartbeats, buffering, proxy policy |
| Intermittent upload failures | Client-body timeout/size/slow network | Upload route policy, network gaps, quotas |
| Only POST produces duplicates after timeouts | Non-idempotent retries | Idempotency keys, durable operation status |
| 502 instead of 504 | Upstream disconnect or invalid response | Proxy error logs, TCP/TLS diagnostics |
| Query timeout 1 s yet request takes 5 s | Pool wait/transaction/serialization | DB acquire time and end-to-end spans |

**Workflow:** identify error owner → inspect timeline/traces → classify timeout semantics → measure critical path and remaining budget → fix the right layer → run load/cancel tests → monitor after rollout. Never change 10 timeouts simultaneously or you will not know which setting fixed the issue.

## 21. Anti-Patterns to Avoid

| Mistake | Why It Is Wrong | Better Approach |
|---|---|---|
| Assuming `server.tomcat.connection-timeout` limits controllers | Only covers request-line/connector phase | App/SDK operation deadlines |
| Assuming `proxy_read_timeout` is a hard total cap | Only measures inactivity between upstream reads | Gateway hard total deadline if supported |
| Client 2 s, downstream 60 s | Orphaned work and pool saturation | Outer-to-inner nested budgets |
| Each retry resets the full budget | Backoff/attempts exceed deadline | Single outer overall deadline |
| Raising every timeout to "fix 504s" | Masks bottlenecks, holds resources longer | Identify owner, measure SLOs and pools |
| Calling blocking SDKs on WebFlux event loop | Stalls reactor event loop | Reactive clients or bounded offload |
| Assuming `AbortController` rolls back DB | Cancellation does not guarantee undoing mutations | Idempotency and status queries |
| Sharing one timeout for REST and SSE | Cuts off valid long-lived streams | Route-specific idle/lifetime policies |
| Trusting custom deadline headers from the Internet | Lets callers bypass resource policies | Trusted proxies + server-side clamping |
| Logging raw exceptions/headers | Leaks secrets/PII | Sanitized `ProblemDetail` + secure telemetry |
| Testing only 200 happy paths | Misses 499/502/504/cancel behavior | Multi-layer fault injection |
| Unlimited retries at both gateway and app | Retry amplification | Single retry owner/budget |
| Enlarging thread pools when DB is exhausted | Adds queueing and pressure on the DB | Bulkheads and load shedding |
| Treating curl exit 28 as HTTP 504 | Client may never receive an HTTP status | Separate caller timeouts from server errors |

## 22. Production Rollout Checklist

1. Map client → CDN/ingress → server → DB/downstreams.
2. Inventory every timeout with a clear **definition and owner**.
3. Pick user-facing SLOs and overall client deadlines from observed latency data.
4. Confirm whether the gateway supports hard total deadlines or only connect/read/send inactivity.
5. Design app operation budgets smaller than outer deadlines, leaving response margin.
6. Set per-attempt HTTP timeouts from remaining budget; factor in retries/backoff.
7. Configure TCP connect, TLS, pool acquire, response idle, and DB query limits separately.
8. Ensure timeout classification maps properly to 408/502/503/504, and track 499 in NGINX.
9. Never use async/reactive code to ignore blocking threads or hard cancellation problems.
10. Enforce idempotency and status reconciliation for mutations when callers can time out.
11. Separate long jobs, SSE, WebSockets, and uploads from short requests with dedicated lifetime/idle/size policies.
12. Correlate traces/logs/metrics across proxy/app/downstream without leaking secrets.
13. Test proxy-generated vs app-generated 504s, client aborts, committed responses, and retry storms.
14. Monitor pools, queues, GC, CPU, p95/p99/p99.9, and timeout rates after rollout.
15. Maintain canary rollout, rollback plans, ownership, and documentation explaining every timeout value.

**Core principle:** *Every request has an end-to-end time budget; each hop needs semantically accurate timeouts; dependencies must stop before callers give up; and a timeout never guarantees completed work was undone.*

## 23. Self-Check Questions

**1. Does NGINX `proxy_read_timeout=5s` mean the response must finish within 5 s?**  
No. It bounds the gap between two consecutive upstream reads.

**2. Does `server.tomcat.connection-timeout=5s` abort a controller sleeping for 10 s?**  
No. That property is not a total controller execution deadline.

**3. Does `spring.mvc.async.request-timeout` apply to all synchronous MVC controllers?**  
No. It applies to asynchronous request processing.

**4. If the browser waits 3 s, should the downstream wait 30 s?**  
Usually no. Respect remaining budget and cancel/time out appropriately.

**5. Does TCP connect timeout cover reading the response body?**  
No. It primarily covers establishing a new connection.

**6. What mechanism does Spring 6.1's `JdkClientHttpRequestFactory.setReadTimeout(Duration)` use?**  
It configures JDK `HttpRequest.Builder.timeout(Duration)` for the request.

**7. Is NGINX `499` a standard HTTP status sent back to the client?**  
No. It is an NGINX access-log status recorded when the client closes the connection.

**8. How do HTTP `408` and `504` differ?**  
408 typically means the server timed out waiting for the client to send the request; 504 means a gateway timed out waiting on an upstream.

**9. Is curl exit code 28 proof that the app returned HTTP 504?**  
No. Curl may have timed out locally before receiving any HTTP status.

**10. Does a client timeout guarantee the DB transaction rolled back?**  
No. The server or downstream may have already committed.

**11. Will a long-lived SSE stream immediately be killed by a 2 s NGINX read timeout if it sends a heartbeat every second?**  
Not necessarily; check buffering/flushing and inactivity semantics.

**12. Does a 1 s per-attempt timeout with 3 retries have a 1 s total timeout?**  
No. You need an outer overall operation deadline.

**13. Are Hikari connection acquisition timeout and JDBC query timeout the same?**  
No. One bounds waiting for the pool; the other bounds query execution.

**14. When a client aborts a POST, should it retry immediately?**  
Not unless idempotency and transaction state are verified.

**15. Why does a proxy 504 differ from an app 504 despite having the same status?**  
Different owners and error conditions; the proxy may return HTML whereas the app returns `ProblemDetail`.

**16. Why must `System.nanoTime()` never be sent over the network as a deadline?**  
It is a process-local monotonic clock, not a shared UTC timestamp across hosts.

**17. How do you tell an NGINX 504 from a Spring 504?**  
Compare NGINX upstream timings, access/error logs, app traces/metrics, and the error payload owner.

**18. Should timeouts always equal healthy p99?**  
Not mechanically; balance false timeouts, tail latency, peak load, and user SLOs.

## 24. Official Documentation

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.tomcat.connection-timeout`, keep-alive, `spring.mvc.async.request-timeout`.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Netty and server settings.
- [Spring Framework 6.1 – JdkClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): `setReadTimeout` and JDK request timeout.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, client factories, and HTTP error handling.
- [Spring Framework – Spring MVC Async](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): `Callable`/`DeferredResult` and async timeouts.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): connector and HTTP client configuration.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pools, TCP connect, and response timeouts.
- [Project Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeout/cancellation/retry semantics.
- [NGINX – ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_connect_timeout`, `proxy_send_timeout`, `proxy_read_timeout`.
- [NGINX – ngx_http_core_module](https://nginx.org/en/docs/http/ngx_http_core_module.html): `client_header_timeout`, `client_body_timeout`, `send_timeout`.
- [NGINX – Log Module](https://nginx.org/en/docs/http/ngx_http_log_module.html): `request_time` and upstream timing logs.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP 408, 502, 503, 504.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): public error contracts.
- [MDN – AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController): browser fetch cancellation.
- [OWASP – Error Handling](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): avoiding internal leaks through error responses.