# HTTP Keep-Alive: Distinguishing a Connection from a Request in Spring Boot

## Objectives

After this lesson, you will be able to distinguish **a network connection** from **an HTTP request**, explain how HTTP keep-alive reuses connections, recognize the differences across HTTP/1.1, HTTP/2, and HTTP/3, and observe that behavior in a Spring Boot application running on a Servlet container.

Core idea: **one connection can serve multiple HTTP requests; each request still has its own method, path, headers, body, processing lifecycle, and response**. An open connection does not mean a request is still running.

## 1. How Is a Connection Different from a Request?

- **A connection** is the transport channel between two endpoints over a network hop. For typical HTTP/1.1 and HTTP/2, it is a TCP connection; HTTPS adds TLS to protect the data. A connection is established, may sit idle, get reused, and eventually close.
- **An HTTP request** is a logical message sent by the client: a method like `GET`/`POST`, target/path, headers, and an optional body. The server handles one request and builds a response for it; the request ends once the associated exchange completes.
- **An HTTP response** has a status, headers, and an optional body. Response boundaries must be accurately delimited so subsequent bytes on the same connection can belong to the next response/request.
- **An HTTP session** (e.g., `HttpSession`, `JSESSIONID` cookie) is application-level user session state; a session can span multiple requests **and multiple connections**. It is not a TCP connection.

| Criterion | Network connection | HTTP request |
| --- | --- | --- |
| Unit | TCP connection (HTTP/1.1, HTTP/2) or QUIC connection (HTTP/3) | HTTP message carrying method, target, headers, body |
| Lifecycle | From establishment to close; can sit idle between uses | From sending/receiving the request until processing/exchange completes |
| Cardinality | One connection can serve many requests | Each request is a separate logical interaction |
| Spring MVC state | Managed by server/connector, not synonymous with one controller invocation | Each dispatch to a handler has its own request/response context |
| Holds user identity? | Not inherently tied to a login session | Authentication/session is determined by per-request rules |

For example, a client calls `GET /products/1` and then `GET /products/2`. Those are **two separate requests** even if both travel over **the same TCP connection**.

## 2. What Does HTTP Keep-Alive Solve?

In HTTP/1.1, a **persistent connection**, commonly called *HTTP keep-alive*, allows keeping the connection open after one request/response pair so subsequent pairs can reuse it.

Without connection reuse:

```text
TCP/TLS setup -> GET /a -> response /a -> close connection
TCP/TLS setup -> GET /b -> response /b -> close connection
```

With connection reuse:

```text
TCP/TLS setup
    |
    +-> GET /a -> response /a
    |
    +-> GET /b -> response /b
    |
    +-> idle for a period -> close when needed
```

By reusing connections, clients and servers avoid repeated TCP/TLS handshakes, reducing latency and socket creation overhead when sending multiple requests to the same endpoint. **Two GETs are still two requests and two responses**, not merged into one request. Each transfer still incurs transmission and processing time.

Keeping a connection does not mean keeping it forever: the server, client, proxy, or load balancer may close it due to idle timeouts, request-count limits, process lifecycle, maintenance, or network errors.

## 3. Key Rules in HTTP/1.1

1. **HTTP/1.1 defaults to persistent connections** when both sides support them and messages are properly delimited. You do not need to send `Connection: keep-alive` on every request to enable this behavior.
2. The `Connection: close` header indicates that the sender intends to close the connection after completing the current message. Therefore, **never assume the next request will always reuse the connection**.
3. `Connection: keep-alive` and the `Keep-Alive` header (if present) are *hop-by-hop*; timeout/max values advertised by one server are not an end-to-end promise across intermediaries. Nor does `Keep-Alive` mean periodic heartbeat packets are being sent.
4. In HTTP/1.0, connections are not persistent by default; supporting implementations may negotiate keep-alive explicitly. Do not extrapolate HTTP/1.1 defaults to HTTP/1.0.
5. To reuse an HTTP/1.1 connection, both sides must know where each message ends. Depending on the case, framing uses `Content-Length`, `Transfer-Encoding: chunked`, or status/method-specific rules; closing the connection can also mark the end for certain responses. If a client abandons reading a response body or framing breaks, the connection cannot be safely reused.

For example, two responses with separate bodies cannot be treated as a single body stream merely because they share a socket. The HTTP parser determines message boundaries, while the application receives each request independently.

**Keep-alive is not HTTP pipelining.** In HTTP/1.1, the common pattern is sending one request and receiving its response before reusing the connection for the next request. HTTP/1.1 pipelining allowed sending multiple requests before earlier responses completed, yet responses still had to return in order; real-world support is limited due to complexity and head-of-line blocking. Do not confuse pipelining with HTTP/2 multiplexing.

## 4. How Do HTTP/2 and HTTP/3 Use Connections?

| Protocol | Underlying connection | Multiple requests per connection | Key difference |
| --- | --- | --- | --- |
| HTTP/1.1 | TCP; HTTPS adds TLS | Yes, typically reused sequentially | No independent stream multiplexing like HTTP/2 |
| HTTP/2 | TCP + TLS in common HTTPS deployments | Yes, **multiple streams can run concurrently** | Each request/response belongs to its own stream sharing the connection |
| HTTP/3 | QUIC over UDP with integrated TLS | Yes, multiple QUIC streams | Does not use TCP; streams are more independent under packet loss |

In HTTP/2, one TCP connection can carry multiple concurrent requests/responses on separate streams. In HTTP/3, connection reuse still exists, built atop QUIC. Consequently, the accurate phrasing is that **multiple HTTP requests can share a protocol connection**, rather than claiming HTTP always runs over a single TCP socket.

The `Connection` header and other HTTP/1.1 connection-specific headers are not used to control connections in HTTP/2/HTTP/3. Also avoid conflating HTTP keep-alive with **TCP keepalive** (TCP-layer probes to detect dead peers), HTTP/2 **PING** frames, or login session state.

## 5. Connection to the Spring Boot Web Runtime

In a Spring Boot MVC app using `spring-boot-starter-web` and embedded Tomcat:

- **Tomcat / HTTP connector** accepts and manages connections, parsing bytes into HTTP requests. Spring MVC receives the parsed request, selects the handler/controller, runs filters/interceptors, and generates the response.
- **Reusing a connection does not mean reusing the same `HttpServletRequest`, transaction, security context, or worker thread.** Request-scoped data applies per request. Never store per-request data in shared fields of a singleton controller.
- Multiple requests from one client may be served by different worker threads. Conversely, a pooled worker thread serves requests from different connections over time. Never use a thread ID as a connection ID.
- Keep-alive / idle timeout / max reuse settings depend on the web server, version, and infrastructure. With embedded Tomcat, check both connector settings and any reverse proxy in front; never assume changing a controller alone controls connection behavior.
- WebFlux / Reactor Netty applications use a different execution model from Servlet MVC, yet **a request remains the HTTP unit of interaction** and connections can still be reused.

When behind Nginx / an API gateway / a load balancer:

```text
Browser -- connection A --> Proxy -- connection B --> Spring Boot
                         Proxy -- connection C --> Spring Boot
```

Connection A does not necessarily map one-to-one to B or C. The proxy may pool upstream connections and reuse them across multiple requests, even from different clients. Thus, the address/port observed by Servlet is typically the **direct peer of the proxy → app hop**; it does not prove the browser's own connection was reused.

An open connection also **does not mean the user is still logged in**. Cookies, sessions, tokens, and authorization checks belong to per-request handling; never grant access on the assumption that "this is the same old socket."

## 6. Hands-On: Observing Two Requests in Spring Boot

Create a Spring Boot **3.x, Java 17+** project with the `spring-boot-starter-web` dependency (Servlet/Tomcat). Place the following class in `src/main/java/com/example/demo/KeepAliveDemoApplication.java`. This is a complete startup class inside a Spring Boot project with that dependency; it is not a standalone program compiled with plain JDK `javac`.

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class KeepAliveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeepAliveDemoApplication.class, args);
    }

    @GetMapping("/probe")
    public Probe probe(HttpServletRequest request) {
        return new Probe(
            UUID.randomUUID().toString(),
            request.getRemoteAddr() + ":" + request.getRemotePort(),
            request.getProtocol()
        );
    }

    public record Probe(String requestId, String remoteEndpoint, String protocol) {}
}
```

Run the Maven app (or the equivalent Gradle command):

```bash
mvn spring-boot:run
```

In **a single curl command**, send two URLs to the server over HTTP/1.1:

```bash
curl --http1.1 -v http://localhost:8080/probe http://localhost:8080/probe
```

Observe the **two JSON responses**:

- `requestId` is a fresh UUID per request, so the two values differ.
- `remoteEndpoint` is the TCP source address and port **observed by the server**. Over direct localhost, if curl reuses the TCP connection, this value is usually identical in both responses.
- `protocol` shows the protocol reported by the Servlet container, typically `HTTP/1.1` in this test.
- Verbose `curl -v` output can show that the connection is being reused; exact wording varies by curl version. Because UUIDs and ephemeral ports vary, there is **no fixed stdout** to copy verbatim.

Compare by requesting connection closure:

```bash
curl --http1.1 -v -H "Connection: close" http://localhost:8080/probe http://localhost:8080/probe
```

When the server honors the close request after the response, curl must open a new connection for the second URL. Both `requestId` values still differ in either case; what changes is **whether the connection is reused**.

**Interpretation caveat:** an identical `remoteEndpoint` is a useful hint in a simple experiment, **not a globally guaranteed connection identifier**. Ephemeral ports can be reused over time; proxies/NAT alter visibility; timeouts or server policies can cause two requests in the first command to still use two connections. Running `curl` as two separate processes/commands gives each process its own connection pool, so it will not reuse the previous process's socket.

## 7. Performance and Operational Impact

**Benefits:** reduces repeated TCP connection setups and TLS handshakes, especially when a client makes sequential requests; HTTP client connection pools and proxies routinely leverage this.

**Costs and limits:** every open connection consumes sockets, file descriptors, memory, and state on servers, proxies, and clients. Large numbers of long-lived idle connections require sensible timeouts and limits. Keep-alive **does not make controllers faster by itself**, does not eliminate database latency, and does not guarantee a connection survives until the next request.

When investigating a Spring Boot application, distinguish:

- **Request count:** the logical load the app handles; monitor request rate, response time, and status/errors.
- **Open/idle connection count:** transport resources of connectors, proxies, and client pools; can be larger or smaller than active request count.
- **Concurrent requests:** depends on protocol, thread pool / event loop, configuration, and app processing; cannot be inferred directly from socket count alone.
- **Active HTTP sessions:** application state units independent of request and connection counts.

If clients frequently open new sockets, check `Connection: close`, full consumption of response bodies, server/proxy idle timeouts, connection pool limits, and negotiated HTTP version. When a pooled connection fails because the peer closed it, apply timeouts/retries appropriate to the operation type; **never automatically re-send a side-effecting POST without knowing whether the first attempt succeeded**.

## 8. Common Misconceptions

**"One TCP connection carries exactly one HTTP request."** False for persistent connections. HTTP/1.1 can reuse sequentially; HTTP/2 can multiplex multiple streams.

**"Keep-alive means the request has not finished."** False. The previous request may have completed and its response been fully read while the connection sits idle waiting for a new request.

**"Adding `Connection: keep-alive` guarantees the socket stays open forever."** False. HTTP/1.1 is typically persistent by default, yet either party can close per policy or on error. This header does not control behavior end-to-end across all proxies.

**"Two requests on the same connection share the same user/session/transaction/thread."** False. Connections belong to transport; sessions, authentication, request scope, and transactions have their own mechanisms.

**"Keeping a connection open is how all HTTP versions send concurrent requests."** False. Distinguish sequential reuse in HTTP/1.1 from multiplexing in HTTP/2 and HTTP/3.

## 9. Self-Check

1. A browser sends three sequential `GET` requests over one HTTP/1.1 connection. How many requests are there? **Three**; the number of connections used can be **one**.
2. `GET /a` has returned its full body and the socket remains open. Is the request still alive? **No**; only the connection remains ready for reuse.
3. Two requests have the same `remoteEndpoint` yet different `requestId` values in the demo. What does this indicate? **They likely shared a server-observed connection**, while each request remains separate; proxy effects and port reuse must be ruled out before asserting certainty.
4. In HTTP/2, do two concurrent requests require two TCP connections? **Not necessarily**; they can be two streams on the same connection.
5. Does closing a keep-alive connection automatically destroy `HttpSession`? **No**; session lifecycle is governed by session mechanisms, timeouts, and the application.

**Takeaway:** *A connection is a reusable transport channel; a request is an independent message and unit of processing.* This distinction is fundamental to understanding keep-alive, connection pooling, HTTP/2 multiplexing, and Spring Boot web server behavior.