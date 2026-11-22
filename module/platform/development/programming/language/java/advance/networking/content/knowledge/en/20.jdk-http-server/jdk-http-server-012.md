# Evaluating API Limitations Before Choosing a Server for an Application — JDK's HTTP Server (Java 17+)

Java 17 includes the `jdk.httpserver` module with `com.sun.net.httpserver.HttpServer` and `HttpsServer`. This is a **compact, embedded HTTP server API, useful for testing, small applications, or internal components with a clear scope and safeguards**. It allows registering an `HttpHandler` by path, reading requests with `HttpExchange`, returning responses, attaching a `Filter`, `Authenticator`, providing an `Executor`, and using TLS via `HttpsServer`.

However, **"the JDK has an HTTP server" does not mean "the JDK provides a full-featured web application server"**. Before choosing it as a public-facing service, you must evaluate actual requirements for routing, HTTP version, TLS/connection handling, concurrent requests, middleware, authentication, input limits, metrics, graceful shutdown, scalability, operations, and the team responsible for maintenance. Some features can be **self-implemented on top of the API**, but those are **costs and risks owned by the application**; they are not default out-of-the-box production features.

This Knowledge article belongs to the **JDK HTTP Server** section in **Java Advance - networking**. The goal is to build an **evidence-based decision-making** approach: when to use `HttpServer`, when you need to add a reverse proxy or another server/framework, along with how to test directly on Java 17+ to uncover two easily overlooked limitations: **literal prefix matching routing** and **the executor as a resource that requires explicit design**.

## 1. First: distinguish API, implementation, ecosystem, and responsibility

When evaluating a server, separate four layers:

1. **The API the JDK promises to provide:** `HttpServer`, `HttpsServer`, `HttpContext`, `HttpHandler`, `HttpExchange`, `Filter`, `Authenticator`, and some lifecycle operations. This is the programming contract described in the Java SE 17 Javadoc.
2. **The running implementation/provider:** `HttpServer.create(...)` obtains an implementation from `HttpServerProvider`. The default JDK implementation has specific behaviors, but details not guaranteed by the API should not be turned into business assumptions.
3. **Deployment infrastructure:** reverse proxy, ingress, load balancer, TLS termination, WAF, rate limiting, DNS, containers, service mesh, health checks, and telemetry can add capabilities **outside the Java server**.
4. **Application code you must write:** parameterized routing, authz, DTO/JSON validation, body limits, transactions, exception mapping, structured logging, graceful draining, secrets protection, tests, and upgrades.

A system with a good reverse proxy can still suffer from SQL injection or missing authorization in `HttpHandler`. Conversely, a small, purely internal service may not need a heavy framework if requirements are simple and controlled.

**An evaluation conclusion should not just be "server A is faster than server B"**. The decision must account for **the cost of owning the missing layers**, data risk level, concurrent requests, team skills, and long-term operational requirements.

## 2. What Java 17 actually has in the jdk.httpserver module

| Component | Available in JDK 17 | Role |
| --- | --- | --- |
| `HttpServer` | Yes | Bind address/port, accept HTTP connections, dispatch exchanges |
| `HttpsServer` | Yes | HTTP server with TLS via `HttpsConfigurator` and `SSLContext` |
| `HttpHandler` | Yes | Callback to handle request and response |
| `HttpContext` | Yes | Maps a **path prefix** to a handler, holds filters/authenticator |
| `HttpExchange` | Yes | Request method, URI, headers, request body stream, response body/status |
| `Filter` | Yes | Pre/post-process exchanges in a chain |
| `Authenticator`, `BasicAuthenticator` | Yes | Minimalist authentication framework; not a full RBAC/OIDC system |
| `setExecutor(Executor)` | Yes | Delegates request-handling tasks to an application-chosen executor |
| `start()` / `stop(int)` | Yes | Simple lifecycle |
| JSON model binding, database, OAuth2/OIDC, WebSocket server, HTTP/2 application API | Not features packaged as a web framework in this module | Requires application code, libraries, or another server depending on requirements |

The official package page describes a **simple high-level HTTP server API**, providing a **partial implementation** of HTTP/1.1 and HTTPS/TLS, not a claim of compatibility with all protocol variants or out-of-the-box full web application functionality.

Note that the package name `com.sun.net.httpserver` **does not make it a forbidden internal API** within this JDK module: the package is publicly exported by `jdk.httpserver`. However, it is a **JDK-specific module**, so you need to check the runtime distribution, module graph, and compatibility with the deployment environment rather than assuming every custom JRE includes `jdk.httpserver`.

## 3. Choosing by requirements: questions before writing a server

Before discussing code, write a list of measurable requirements:

- **Traffic:** expected requests/second, bursts, concurrent connections, p95/p99 latency, payload sizes, and request hold time.
- **Protocol:** only small HTTP/1.1 JSON, or do you need HTTP/2, WebSocket, server push/event streams, large streaming uploads, reverse proxy upgrade?
- **Security:** public Internet or loopback/private network, passwords/tokens, TLS/mTLS, CORS, CSRF, identity provider, audit, rate limiting, tenant isolation?
- **Resource protection:** max headers/body, request timeout, idle timeout, CPU/RAM/threads limits, queue bounds, slow clients, admission control?
- **Framework services:** routing with path variables/middleware, validation, serialization, compression, content negotiation, sessions, exception handling?
- **Observability:** structured access logs, trace propagation, metrics, health/readiness, correlation ID, error budgets, incident runbooks?
- **Lifecycle:** hot deploy/config reload, graceful shutdown, draining before stopping, zero-downtime release, compatibility when upgrading Java?
- **Ownership:** who verifies TLS configuration, filters abnormal requests, concurrency bugs, HTTP compliance, and library updates?

The evaluation result must have **PASS / FAIL / NEEDS MITIGATION** criteria along with an owner and how to test, not just an answer like "the API has this class so it is enough".

## 4. Minimalist model and responsibility boundaries

Basic processing model:

```text
Incoming TCP connection
         |
         v
HttpServer / HttpsServer
         |
         | Longest literal path prefix match
         v
HttpContext
         |
         +-- optional Authenticator
         +-- Filter chain (before/after)
         |
         v
HttpHandler.handle(HttpExchange)
         |
         +-- method / URI / request headers / request body
         +-- app validation & business logic
         +-- response status / headers / response body
         |
         v
Exchange closed / underlying connection managed by provider
```

`HttpExchange` is **a single request–response exchange**, not a Servlet request object, not a WebSocket session, and has no built-in transaction scope. `HttpHandler.handle` can read the body as bytes or process it as a stream; JSON parsing, payload validation, and mapping errors to HTTP status codes are handled by the handler code or the application layer above it.

**You can create an HTTP endpoint in a few dozen lines**; however, an endpoint operating on the public Internet requires a much larger number of concerns. You should not use **the brevity of a Hello World demo** as proof of production readiness.

## 5. Routing limitation: longest literal prefix, not a full REST router

JDK `HttpServer` finds the context with the **longest prefix matching the request path**. Matching is **literal, case-sensitive**, and does not automatically turn path strings into templates or normalize encoded forms to understand business routes.

Example:

```java
// Snippet in HttpServer setup; two handlers have already been declared.
server.createContext("/api/", apiHandler);
server.createContext("/api/admin/", adminHandler);
```

Paths:

| Request path | Selected context | What to understand |
| --- | --- | --- |
| `/api/items` | `/api/` | Normal prefix |
| `/api/admin/status` | `/api/admin/` | Longer prefix wins |
| `/api/Admin/status` | `/api/` | Case-sensitive: does not match admin |
| `/unknown` | No context | Server may return 404 |
| `/v123` when `"/v1"` is registered | `/v1` | **Unintended prefix match** |

**Important warning from Java 17 Javadoc:** context `"/foo"` can match both `"/foobar"` and `"/foo/bar"`. When defining hierarchical routes, a trailing `/` is typically used on the prefix, and you must still validate the final path inside the handler.

There is no built-in `@GetMapping("/users/{id}")` mechanism, method-aware routing, or route constraints by content type. To get a proper REST router, you must write it yourself, add a library, or choose a framework/server with proven routing semantics.

Path encoding issues require separate testing: `getRequestURI().getPath()` and `getRawPath()` have different semantics; never use naive string prefix matching as a security boundary for file paths/tenant IDs.

## 6. HTTP method and status: context does not replace application validation

`createContext("/api/", handler)` does not automatically restrict the method to GET. The handler needs to check `exchange.getRequestMethod()` and return the appropriate status when the method is unsupported:

```java
// Illustrative snippet, placed in a handler that has send(...) and imports.
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    send(exchange, 405, "Method Not Allowed");
    return;
}
```

If a `POST` is received on a GET-only route, return **405** and the appropriate `Allow` header, rather than defaulting to executing database read code. If the URI is not mapped, **404** may come from the server core; **403** and **401** according to auth/authz policy; **400** when query/body is invalid; **413** when body size policy is exceeded; **415** when content type is not accepted.

Do not build a REST API just using `getRequestURI().toString().contains(...)` or assume that prefix routing automatically attaches identity/permissions. You must validate method, path, percent encoding, query, headers, and content type according to the contract.

Handling `HEAD`/`OPTIONS`, 304/204 with no body, content negotiation, and conditional requests is part of what the application must handle or deliberately design. There should be regression tests for each method and status.

## 7. HttpExchange lifecycle: operation order is not arbitrary

According to the Java SE 17 Javadoc, the typical lifecycle is:

1. Read `getRequestMethod()`, `getRequestURI()`, and `getRequestHeaders()`.
2. Read `getRequestBody()` into a parser/stream and **close the input**; enforce maximum bytes.
3. Set response headers using `getResponseHeaders()`.
4. Call **`sendResponseHeaders(status, responseLength)`** before writing the body.
5. Call `getResponseBody()`, write the **exact format/number of bytes**, and **close the output**.
6. Ensure `HttpExchange` is terminated on error/early-return paths as well.

`HttpExchange` implements `AutoCloseable`, so you can use:

```java
// Snippet: exchange is the parameter of HttpHandler.handle.
try (exchange) {
    byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders()
            .set("Content-Type", "text/plain; charset=UTF-8");
    exchange.sendResponseHeaders(200, body.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(body);
    }
}
```

Closing the response output also closes the request input if it has not been closed yet. However, **reading the entire request body before closing** is recommended to allow reusing the TCP connection; closing while data remains may prevent the connection from being used for the next exchange.

Wrong ordering or forgetting to close can cause resource leaks, hung clients, or force the connection to close. This is an ownership problem, not just code style.

## 8. Response length: >0, 0, and -1 have different meanings

A difference that easily causes bugs when the server returns a response:

| `sendResponseHeaders(status, length)` | Java 17 Meaning | Consequence |
| --- | --- | --- |
| `length > 0` | Exactly **length bytes** | Must write the **exact** byte count; more or fewer causes IOException/abort |
| `length == 0` | Uses **chunked transfer encoding** | Does not mean "0 bytes" or "guaranteed empty body" |
| `length == -1` | Sends **no response body** | Suitable for `204 No Content` or responses without a body |

For example, if you want to return UTF-8 text, compute the length after encoding:

```java
String message = "Xin chào";
byte[] body = message.getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(200, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
```

Do not use `message.length()` because Java String length is UTF-16 code units, whereas HTTP response length is counted in **bytes**. If you write fewer than the fixed length, `OutputStream.close()` may throw `IOException`; if you write more, `write` may throw `IOException`.

Do not return `sendResponseHeaders(204, 0)` to represent "no body"; per the contract, `0` is chunked. For 204, 304, HEAD, you must consider standard HTTP semantics and API specifics. Example 2 uses `204, -1` and verifies the client reads an empty body.

## 9. Concurrency: why is the default executor so easily misunderstood?

`HttpServer.setExecutor(Executor)` must be called **before** `start()`. Java 17 Javadoc states: if not set or set to `null`, the default implementation uses the thread created by `start()` to process HTTP tasks. Therefore, **you should not assume by default that there is a thread pool serving concurrency well**.

```java
// Illustrative snippet, server already created.
ExecutorService workers = Executors.newFixedThreadPool(4);
server.setExecutor(workers);   // Before start()
server.start();                // Only then accept requests
```

A handler running `Thread.sleep()`, slow DB queries, or slow socket reads can occupy a worker and affect other requests. This is a **blocking server API**: simply increasing the number of threads may not be enough if the software lacks backpressure.

**Second trap:** `Executors.newFixedThreadPool(4)` has an **unbounded queue by factory design**. Four workers limit the number of concurrently running tasks, but thousands of remaining requests/tasks can wait in the queue and cause memory/latency pressure. Test examples use a fixed pool for simplicity; production needs **bounds on active tasks, queued tasks, and request body size**.

## 10. Backlog is not a thread pool, request queue, or rate limiter

`HttpServer.create(address, backlog)` takes the `backlog` parameter of the TCP listening socket. It represents **the number of connections waiting to be accepted** that the system can queue at the TCP layer. If the quota is exhausted, the TCP implementation may reject or ignore new connections.

```text
INCOMING CLIENTS
      |
      v
TCP listening socket backlog (connections waiting accept)
      |
      v
HttpServer accepts connections
      |
      v
Executor tasks and queue (application request handling)
      |
      v
Handler / downstream DB / response
```

These are **different** resources:

- **Backlog:** limits the accept queue at the OS, does not measure completed HTTP requests.
- **Executor pool size:** limits the number of tasks that can be processed concurrently in a fixed-type pool.
- **Executor queue:** number of waiting tasks; can be unbounded if an inappropriate factory is chosen.
- **HTTP connections:** can stay keep-alive and carry multiple exchanges over time.
- **Downstream DB pool:** is an independent quota; 100 HTTP workers does not mean the DB can handle 100 parallel queries.

`backlog <= 0` uses the system default value per Javadoc, **not** "unlimited". Tune limits via load testing and observing error rate/latency, rather than relying on a single number.

## 11. Slow clients, body streaming, and quotas you still must own

With `HttpExchange.getRequestBody()`, the request input is an `InputStream`. If a handler uses `readAllBytes()` for content from the Internet without a limit, a client can force the server to hold large amounts of memory. If a handler waits for a very slow sender, the worker can be held for a long time.

An illustrative bounded read loop:

```java
// Snippet: input is InputStream; maxBytes > 0 configured by the application.
long consumed = 0L;
byte[] buffer = new byte[8192];
int count;
while ((count = input.read(buffer)) != -1) {
    if (count > maxBytes - consumed) {
        throw new IOException("Request body too large");
    }
    consumed += count;
    // Parse/stream further into a capped sink, avoiding retaining all buffers.
}
```

This is not a standalone class. Adding a `Content-Length` check is only a preflight optimization; **it does not replace actually measured quotas** because metadata may be missing/untrusted, the request may be chunked, or the connection may be cut.

Specific requirements are needed for **max request bytes, max header sizes, connection count, input rate, idle timeout, total deadline, upload duration, response output queue, rejection policy**. Some implementations have internal settings or network properties, but **they should not be treated as a unified application API** of `HttpServer` to enforce complex per-endpoint policies. If standard knobs are missing, you need a reverse proxy with input protection or another server/framework.

## 12. Filter is built-in, but production middleware is not "free"

`HttpContext.getFilters()` allows adding a `Filter` to pre/post-process. A filter can:

- Read headers and validate a simple condition.
- Set an attribute via `exchange.setAttribute` for the handler.
- Call `chain.doFilter(exchange)` to let the request proceed.
- Reject and directly return a response **without calling the chain**.
- Measure time, attach a correlation ID, or wrap request/response streams via `setStreams`.

Example:

```java
// Snippet: placed inside Filter#doFilter(HttpExchange e, Chain chain).
String key = e.getRequestHeaders().getFirst("X-Demo-Key");
if (!"demo-key".equals(key)) {
    sendUnauthorizedAndClose(e);
    return;              // Does not run handler.
}
chain.doFilter(e);        // Allows further processing.
```

`sendUnauthorizedAndClose` is an undeclared illustrative function, **not a standalone program**. Demo 1 has a complete runnable filter version.

**Limitation:** `Filter` is a building block; it does not out-of-the-box provide authentication token systems, structured audit, retry/circuit breaker, CSRF protection, per-route security policy, API versioning, or a standardized error mapper. If writing complex filter chains yourself, you must test **execution order, exception paths, cleanup, thread safety, and attribute propagation**.

## 13. Authentication does not mean authorization

In `HttpContext` there is `setAuthenticator(Authenticator)`; Java 17 also has `BasicAuthenticator` to check HTTP Basic username/password using application-provided logic. This is a **basic authentication tool**, not full OAuth2/OIDC/SAML, JWT verification, sessions, CSRF policy, and tenant RBAC.

Separate them:

1. **Authentication:** which principal does the request belong to? Is the token/session/certificate valid?
2. **Authorization:** does that principal have permission to read/modify **the specific resource**? Check by tenant, owner, and business rules.
3. **Transport protection:** Basic credentials or bearer tokens must not be sent over public HTTP; use TLS with `HttpsServer` or a controlled TLS proxy.
4. **Input validation:** even an authenticated client can still send path traversal, invalid JSON, or oversized payloads.
5. **Audit:** who did what, operation ID, and outcome; do not log passwords/tokens.

The demo uses `X-Demo-Key: demo-key` to show the filter flow. **That is not a production authentication mechanism**: hardcoded key, no leak/replay protection, no credential lifecycle management, and no per-resource authorization.

If the system needs complex login/session/role/tenant handling, the cost of building it yourself on `HttpHandler` is usually higher than using a framework with proven middleware/auth integration.

## 14. HTTPS is available, but real TLS must be configured

`HttpsServer` is a subclass of `HttpServer` and supports HTTPS via `HttpsConfigurator` using an initialized `SSLContext`. That means the JDK **is capable of running HTTP over TLS**, not "lacking HTTPS".

Configuration flow:

```java
// Illustrative snippet; context/keyStore and imports need to be prepared.
SSLContext ssl = SSLContext.getInstance("TLS");
ssl.init(keyManagerFactory.getKeyManagers(),
         trustManagers, new SecureRandom());

HttpsServer https = HttpsServer.create(
        new InetSocketAddress("127.0.0.1", 8443), 0);
https.setHttpsConfigurator(new HttpsConfigurator(ssl));
https.createContext("/health", handler);
https.setExecutor(workers);
https.start();
```

This is **not a standalone program**; `keyManagerFactory`, `trustManagers`, `handler`, `workers` have not been created. Production requirements also include:

- Valid private key/certificate chain and hostname-matching certificate; rotate secrets/certificates.
- TLS protocol/cipher policy, truststore, mTLS client certificates when needed, and endpoint identity testing.
- Possibility of TLS termination at a reverse proxy; internal traffic behind the proxy still needs a clear threat model.
- If there are multiple hosts/domains, certificates/SNI and routing/ingress must be designed per deployment.
- Never disable TLS verification as a "quick fix" for certificates; never log secrets/private keys.

**Having HTTPS does not mean the server supports HTTP/2, ALPN policies, or a comprehensive web gateway**. Check the documentation of the exact JDK/provider and verify traffic through proxies/certs.

## 15. Protocol: basic HTTP/1.1, no built-in WebSocket server or HTTP/2 feature stack

The Java 17 package documentation describes a **partial implementation of HTTP/1.1** and HTTP over TLS. This API **does not provide contracts/application abstractions** equivalent to a full HTTP/2 server, WebSocket server framework, servlet container, or reactive nonblocking runtime.

| Requirement | Assessment with Java 17 `jdk.httpserver` |
| --- | --- |
| Basic HTTP/1.1 GET/POST | Suitable after adding handlers and validation |
| HTTPS | Has `HttpsServer`, needs `SSLContext`/certificate policy |
| HTTP/2 multiplexing/gRPC server | Not an application capability provided by this API |
| WebSocket upgrade with sessions/frames | No WebSocket server abstraction in the API |
| Server-Sent Events | Can manually stream text/chunked in HTTP, but still needs lifecycle/backpressure/timeout/proxy policies |
| Multipart upload | No automatic multipart parser/framework; add a library or build yourself with bounds |
| Static file hosting/cache/range/ETag | Programmable, not out-of-the-box like a full web server |
| Routing by regex/path variable/REST annotations | Not built-in; literal prefix context |
| Response compression/content negotiation | Must implement yourself or offload to proxy/framework |

Do not conclude "no JDK distribution can ever run HTTP/2": a provider or **another** layer may add capabilities. What is certain for **the API being evaluated** is that you should not plan a product around features that Java 17 `HttpServer` **does not promise**.

If the product requires a WebSocket/gRPC/HTTP2 server as a core feature, it is usually better to **choose a dedicated server/framework rather than recreating the protocol** from TCP/HttpExchange.

## 16. A reverse proxy helps a lot, but cannot fix handler bugs

A possible architecture:

```text
Internet users
      |
      v
Ingress / Reverse proxy / WAF
 - TLS termination
 - header/body limits
 - HTTP/2 where applicable
 - rate limit / traffic routing
 - access logs / health probes
      |
      v
Private network boundary
      |
      v
Java 17 HttpServer (bind internal address)
 - HttpContext routing
 - Filter authentication/authorization
 - bounded executor and request quotas
 - business logic and DB
```

A proxy can reduce the attack surface and add functionality. However:

- **It does not automatically guarantee** the handler is free of OOM/SQL-injection/path traversal.
- Headers like `X-Forwarded-For`/`X-Forwarded-Proto` must be trusted **only from configured proxies**; external clients can send spoofed headers.
- Proxy timeouts can cause the client to disconnect while the server is still processing; for POSTs with side effects, idempotency/status reconciliation is needed.
- Proxy rate limits may be based on account/IP; business quotas and per-tenant authorization are still needed in the application.
- If the proxy terminates TLS and connects to the app over plaintext HTTP, this should only be accepted within an approved network/security boundary.
- Any session/authn at the proxy must ensure the identity information passed to the backend **cannot be spoofed**.

Therefore, placing a proxy in front does not turn `HttpServer` itself into an enterprise server with full guarantees.

## 17. Java 17+ Example 1 — practical routing, filter, and status codes

The file **`JdkHttpServerRoutesDemo.java`** starts an `HttpServer` on **loopback 127.0.0.1** and an OS-assigned port, adding two contexts `/api/` and `/api/admin/`. The admin context has a `Filter` that rejects requests missing `X-Demo-Key`; the public route checks the GET method itself. A `java.net.http.HttpClient` client sends five requests over real HTTP to verify behavior.

```java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class JdkHttpServerRoutesDemo {
    private static void reply(HttpExchange exchange, int code,
                              String value) throws IOException {
        try (exchange) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(code, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);

        server.createContext("/api/", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                reply(exchange, 405, "METHOD");
                return;
            }
            reply(exchange, 200, "PUBLIC");
        });

        HttpContext admin = server.createContext("/api/admin/",
                exchange -> reply(exchange, 200, "ADMIN"));
        admin.getFilters().add(new Filter() {
            @Override
            public String description() {
                return "Demonstration authorization gate";
            }

            @Override
            public void doFilter(HttpExchange exchange, Chain next)
                    throws IOException {
                if (!"demo-key".equals(exchange.getRequestHeaders()
                        .getFirst("X-Demo-Key"))) {
                    reply(exchange, 401, "DENIED");
                    return;
                }
                next.doFilter(exchange);
            }
        });

        server.setExecutor(workers);
        server.start();
        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();
            HttpResponse<String> publicRoute = client.send(
                    get(URI.create(base + "/api/items")),
                    HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> blocked = client.send(
                    get(URI.create(base + "/api/admin/status")),
                    HttpResponse.BodyHandlers.ofString());
            HttpRequest allowed = HttpRequest.newBuilder(
                    URI.create(base + "/api/admin/status"))
                    .header("X-Demo-Key", "demo-key")
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> adminRoute = client.send(
                    allowed, HttpResponse.BodyHandlers.ofString());
            HttpResponse<Void> method = client.send(
                    HttpRequest.newBuilder(
                            URI.create(base + "/api/items"))
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.noBody())
                            .build(),
                    HttpResponse.BodyHandlers.discarding());
            HttpResponse<Void> missing = client.send(
                    get(URI.create(base + "/missing")),
                    HttpResponse.BodyHandlers.discarding());

            System.out.println("Public route: "
                    + publicRoute.statusCode() + "/" + publicRoute.body());
            System.out.println("Admin without key: "
                    + blocked.statusCode());
            System.out.println("Admin with key: "
                    + adminRoute.statusCode() + "/" + adminRoute.body());
            System.out.println("Method rejected: "
                    + method.statusCode());
            System.out.println("Missing route: "
                    + missing.statusCode());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Compile and run:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 JdkHttpServerRoutesDemo.java
java --add-modules jdk.httpserver JdkHttpServerRoutesDemo
```

Verified stdout:

```text
Public route: 200/PUBLIC
Admin without key: 401
Admin with key: 200/ADMIN
Method rejected: 405
Missing route: 404
```

**Exact explanation:**

1. `server.createContext("/api/", ...)` registers a context prefix, while `"/api/admin/"` is longer so it wins when a request for `/api/admin/status` arrives.
2. Request `GET /api/items` receives body `PUBLIC` and HTTP 200 from the public handler.
3. An admin request missing `X-Demo-Key` is blocked by the filter, receiving HTTP 401. The filter does not call `chain.doFilter` on the rejection path.
4. An admin request with the assumed header `demo-key` is allowed through the filter, receiving `ADMIN`. **Do not use this hardcoded key outside a demo.**
5. A POST request to the GET-only route receives **405**; the handler attaches `Allow: GET`.
6. A request matching no context is returned **404** by the HTTP server.
7. Response body is calculated in UTF-8 bytes and closed properly in try-with-resources; `server.stop(0)` and `workers.shutdownNow()` clean up the test server.
8. The entire test uses loopback only, **calling no Internet URLs**; it verifies routing/filter/status semantics, not production performance.

You can replace the demo `Filter` with a filter performing professional authn, but you must handle token validation, rotation, audit, authorization, timing leaks, rate limits, and upstream errors yourself.

## 18. Java 17+ Example 2 — two parallel workers and the /v1 prefix trap

The file **`JdkHttpServerExecutorDemo.java`** uses `CountDownLatch` to ensure two requests `/work/one` and `/work/two` **have concurrently entered two handlers** before letting them return responses. This verifies that setting a two-thread executor actually allows two tasks to be processed simultaneously.

The program also intentionally registers `createContext("/v1", ...)` (without a trailing slash), then calls `GET /v123` to prove **literal prefix matching** can match incorrectly from a REST design perspective. `GET /V1` does not match due to case-sensitivity; `GET /empty` returns 204 with no body.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class JdkHttpServerExecutorDemo {
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        try (exchange) {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    private static HttpRequest request(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(7)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        server.createContext("/work/", exchange -> {
            entered.countDown();
            boolean ready;
            try {
                ready = release.await(5, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                ready = false;
            }
            if (ready) {
                reply(exchange, "DONE");
            } else {
                try (exchange) {
                    exchange.sendResponseHeaders(503, -1);
                }
            }
        });
        server.createContext("/v1", exchange -> reply(exchange, "PREFIX"));
        server.createContext("/empty", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(204, -1);
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            CompletableFuture<HttpResponse<String>> one =
                    client.sendAsync(request(base, "/work/one"),
                            HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> two =
                    client.sendAsync(request(base, "/work/two"),
                            HttpResponse.BodyHandlers.ofString());

            boolean parallel = entered.await(5, TimeUnit.SECONDS);
            release.countDown();
            HttpResponse<String> a = one.get(6, TimeUnit.SECONDS);
            HttpResponse<String> b = two.get(6, TimeUnit.SECONDS);

            HttpResponse<String> prefix = client.send(
                    request(base, "/v123"),
                    HttpResponse.BodyHandlers.ofString());
            HttpResponse<Void> caseSensitive = client.send(
                    request(base, "/V1"),
                    HttpResponse.BodyHandlers.discarding());
            HttpResponse<String> empty = client.send(
                    request(base, "/empty"),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Parallel handlers entered: " + parallel);
            System.out.println("Work replies: "
                    + a.statusCode() + "," + b.statusCode());
            System.out.println("Literal prefix /v1 matches /v123: "
                    + "PREFIX".equals(prefix.body()));
            System.out.println("Case-sensitive route: "
                    + caseSensitive.statusCode());
            System.out.println("No-body status: "
                    + empty.statusCode() + "/" + empty.body().length());
        } finally {
            release.countDown();
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Run command:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 JdkHttpServerExecutorDemo.java
java --add-modules jdk.httpserver JdkHttpServerExecutorDemo
```

Stdout:

```text
Parallel handlers entered: true
Work replies: 200,200
Literal prefix /v1 matches /v123: true
Case-sensitive route: 404
No-body status: 204/0
```

Meaning:

1. Two client futures send two requests at the same time; the server has `Executors.newFixedThreadPool(2)`. Latch `entered.await(5,SECONDS)` only returns `true` after **both handlers have entered**, without inferring concurrency from response time.
2. `release.countDown()` releases the handlers, and both responses receive HTTP 200. This only measures correctness on loopback; it does not guarantee throughput with thousands of clients.
3. Context `"/v1"` accepts `"/v123"` as well by literal prefix definition, showing why REST path boundaries must be carefully designed.
4. `"/V1"` receives 404, because context matching is case-sensitive.
5. `204, -1` represents a no-body response; the client confirms body length is 0. **Do not use `sendResponseHeaders(204,0)` to imply no-body**, because 0 means chunked in the API.
6. `newFixedThreadPool(2)` has an unbounded default queue; this pattern is **for demo purposes only**, not production overload control.
7. The code has a `finally` block that releases the latch, calls `stop`, and cleans up the executor to avoid hanging the test.

## 19. Observability and operations: what is missing is often larger than the HTTP handler

A production web service typically needs:

| Operational item | Built-in capability with minimal API | Needs to be added |
| --- | --- | --- |
| Request/response access logging | No full structured access logs pipeline; application must design it | Method/path/status, latency, correlation, privacy redaction |
| Metrics | No per-route/SLA metrics contract like framework instrumentation | Counters/histograms, queue depth, active handlers, saturation |
| Distributed tracing | Does not automatically propagate business trace context | Trace extraction/injection, spans for DB/downstream |
| Health/readiness | Can create a context yourself | Check DB connection, dependency health, draining/readiness |
| Config/secrets | Application dependent | Environment/secret manager, validation, rotation |
| Graceful shutdown | `stop(int delay)` has basic semantics | Stop accepting traffic, wait for jobs, lower readiness, flush logs/traces |
| Load shedding | No built-in per-route business policy | Bounded queues, 429/503, rate limiting, circuit breaker |
| Security review | TLS/Auth building blocks exist | RBAC, CORS/CSRF, body quotas, validation, pentest |

For applications requiring audit/compliance, **the cost of writing/updating/hardening** these parts yourself can exceed running a server/framework that already integrates them in its ecosystem (even though frameworks also require configuration and maintenance).

A health endpoint that always returns "OK" even when the DB is down is not good readiness; readiness must reflect the real ability to receive traffic per contract. At the same time, avoid letting heavy health probes create an infinite DB query loop.

## 20. Shutdown: stop(delay) is not a full orchestration system

According to Java 17 Javadoc, `HttpServer.stop(int delay)`:

- Stops accepting new exchanges.
- Waits for currently processing handlers to finish or until the `delay` (seconds) elapses, whichever comes first.
- Then closes open TCP connections, stops the background server thread, and returns.
- **Cannot restart the same `HttpServer` object** after it has been stopped.

A controlled shutdown sequence:

```text
1. Readiness -> false; stop receiving new traffic from ingress
2. Stop creating new background work
3. Wait for in-flight requests within total deadline
4. Call server.stop(delaySeconds)
5. Shut down/await application-owned executor
6. Flush logs/traces and close DB clients/other resources
7. Exit process
```

Distinguish `stop(0)` in **loopback tests** (wanting to finish fast) from graceful drain requirements in production. Do not call `workers.shutdownNow()` when there are still operations with important side effects lacking a state-saving policy.

`stop(delay)` is not an API that supports live reload, zero-downtime deploy, traffic shifting, rolling back DB transactions, or coordinating with an orchestrator. These capabilities must be designed at the system level.

## 21. Selection table: which cases fit, which need something else?

| Scenario | Initial selection direction | Conditions |
| --- | --- | --- |
| Unit/integration test needing a real HTTP endpoint on loopback | **JDK HttpServer** is very suitable | Close server yourself; auto-assigned port; verify status/body |
| CLI tool with local health/control endpoint | **JDK HttpServer** is usually suitable | Bind 127.0.0.1, limited auth and lifecycle |
| Embedded admin API of an internal service, low traffic | **Can use JDK HttpServer** | Private network, HTTPS/proxy, quotas, logs, security review |
| Small REST API, team ready to manage HTTP concerns themselves | **Consider** | Has security/metrics/tests checklist and load testing |
| Public multi-tenant service, high concurrency, complex auth | **Prefer evaluating a dedicated framework/server** | Auth integration, middleware, limit knobs, observability, ops |
| HTTP/2/gRPC/WebSocket server as a core requirement | **Choose a stack with clear protocol support** | Do not build from `HttpExchange` as the primary solution |
| Large multipart/media uploads, requiring resumable/quotas | **Suitable server/framework or gateway** | Streaming, per-tenant quotas, disk safeguards, upload sessions |
| Microservice needing enterprise deployment/health/metrics | **Look at the full stack** | Do not look only at HTTP handler; integrate tracing, config, lifecycle |

Do not claim every product must use a heavy framework. A JDK server paired with a gateway, clear threat model, controlled deployment, and an experienced team **can** be good enough for a service with limited requirements. Conversely, if you have to write ten pieces of middleware/core protocol yourself, the "few dependencies" choice can create a **higher total cost of ownership**.

## 22. Comparing by capabilities instead of framework names

When looking for alternatives, do not rely on "fastest" marketing claims. Option groups:

- **Servlet containers:** suitable when needing the Servlet ecosystem, filters, sessions, and Java web integration standards.
- **Async/event-loop servers:** suitable for high concurrency/I/O workloads, but require proper nonblocking/backpressure design; bad callbacks can still block.
- **Application frameworks:** routing, validation, serialization, error mapping, auth integration, config/metrics, test fixtures, and many conventions; in return, added dependency/build/deployment complexity.
- **Reverse proxy + JDK handler:** when needing to keep a small service core, pushing TLS/rate limit/HTTP2 to the edge and completing security in the handler.
- **Managed platform/gateway:** shifts some responsibility to infrastructure, but does not exempt business logic/authorization/observability in code.

Common examples of names in Java are Tomcat, Jetty, Undertow, Netty, or application frameworks based on those servers. These are **candidate categories to evaluate**, not a claim that all share the same features/versions/default configurations.

A scoring matrix should use columns: **requirement, importance, native support, mitigation effort, operational owner, load-test evidence, security risk, decision**. Do not put a single benchmark in place of security/availability trade-offs.

## 23. How to load test and prove non-functional requirements

Define the workload before benchmarking:

1. **Warmup:** JVM JIT, connection establishment, caches, and DB pools should not skew p95/p99.
2. **Request mix:** small GET, JSON POST, uploads, slow DB queries, 4xx/5xx errors, and malformed data at realistic ratios.
3. **Concurrency:** increase users/connections/tasks until latency or error rate exceeds SLA.
4. **Slow client tests:** send headers/body slowly, hold keep-alive, read responses slowly to observe worker saturation.
5. **Payload caps:** test bodies without `Content-Length`, chunked, oversized, invalid UTF-8, deeply nested JSON.
6. **Lifecycle:** stop container while requests are in flight, restart, readiness drain, shutdown during DB commit.
7. **Security:** direct access bypassing proxy, X-Forwarded spoofing, cross-tenant authz, CORS/CSRF, path normalization traversal.
8. **Resource tracking:** heap, GC pauses, open FDs/sockets, thread count, executor active/queued, DB pool saturation.

**Document the results**: at N concurrent connections / RPS, p95 under X ms, p99 under Y ms, errors under Z%, memory under quota, under the described test conditions. Those N/X/Y/Z values come **from the application's SLA**, not Java defaults or universal thresholds for every service.

If another framework has higher overhead in a "hello world" test but significantly reduces the effort of self-building auth/observability/lifecycle, the overall decision may still favor the framework. Throughput benchmarks alone are not enough.

## 24. Common mistakes to avoid

1. **"Having HttpServer means the product automatically supports HTTP/2/WebSocket."** There is no such contract in Java 17 `jdk.httpserver`.
2. **"The com.sun name means it cannot be used on the JDK."** This package is officially exported from `jdk.httpserver`; distinguish it from internal APIs.
3. **"createContext("/v1") only matches /v1 exactly."** False: `/v123` can also match; use proper path boundaries.
4. **"Context automatically understands GET/POST."** No: the handler must check the method.
5. **"The default executor is a multi-worker pool."** Do not assume: Javadoc describes the default as using the thread created by `start()`.
6. **"newFixedThreadPool has a bounded queue."** False: the factory creates an unbounded queue per contract.
7. **"backlog=0 means unlimited connections."** False: uses the system default.
8. **"setExecutor after start is fine."** False: Java 17 requires setting it before `start()`.
9. **"Response length=0 means empty body."** False: selects chunked; `-1` is no body.
10. **"Having InputStream means uploads cannot cause OOM."** Calling `readAllBytes()` without a quota can still OOM.
11. **"Forgetting to close HttpExchange has no effect."** It can hold resources and hinder keep-alive.
12. **"BasicAuthenticator is enough for OAuth2/OIDC/RBAC."** No; only a building block.
13. **"HTTPS is unavailable because HttpServer is HTTP only."** `HttpsServer` exists with `SSLContext`/`HttpsConfigurator`.
14. **"Enabling a proxy means the handler does not need authz."** False: a proxy does not replace per-resource permissions in business logic.
15. **"RemoteAddress is always the user's IP."** Behind a reverse proxy it is usually the proxy; forwarded headers are not trustworthy by default.
16. **"Stop(0) is sufficient graceful drain for all production."** No: readiness/deadlines/owned resources are needed.
17. **"After stop you can restart the same object."** False per Javadoc.
18. **"Using a minimal Socket/HTTP API gives security rate limiting automatically."** No: admission/quotas must be designed.
19. **"Only need to test GET 200."** Missing auth/405/404, slow clients, malformed requests, shutdown, concurrent load.
20. **"The proxy and framework will automatically fix all bugs."** No: the application remains responsible for validation, business invariants, and idempotency.

## 25. Self-check questions

**Question 1.** Can an `HttpServer` be created from Java 17 without adding external libraries? **Yes**, when the runtime includes the `jdk.httpserver` module.

**Question 2.** Can a context `"/users"` match `"/users-old"`? **Yes**, due to longest literal prefix matching. Do not treat it as a complete REST route.

**Question 3.** Without calling `setExecutor`, can you assume the server already has an application-configured worker thread pool? **No**; Javadoc states the default uses the thread created by `start()`.

**Question 4.** Does `backlog=100` mean at most 100 concurrent HTTP requests in handlers? **No**, backlog is the queue of TCP connections waiting to be accepted.

**Question 5.** Does `sendResponseHeaders(200,0)` mean no response body is sent? **No**; 0 selects chunked. For no body, use `-1` per contract.

**Question 6.** If a user authenticates successfully with Basic, are they allowed to access another tenant's resource? **Not by default**; per-resource authorization is required.

**Question 7.** Does the JDK have an HTTPS server? **Yes**, `HttpsServer` with `HttpsConfigurator` and `SSLContext`.

**Question 8.** Can `HttpServer` be used for loopback tests serving an endpoint with a real handler? **Yes**, and it is very suitable when the scope/test is clear.

**Question 9.** Why is `newFixedThreadPool(4)` not necessarily safe during traffic bursts? **The default queue is unbounded**; admission/backpressure and an overload policy are needed.

**Question 10.** Does using a reverse proxy to terminate TLS make SQL injection in the handler disappear? **No**. Validation and parameterized SQL remain the application's responsibility.

**Question 11.** If a dedicated WebSocket server or gRPC/HTTP2 is a primary requirement, should `jdk.httpserver` be chosen by default? **No**; choose a stack with the appropriate capability/contract, rather than implementing a production protocol from a few callbacks.

**Question 12.** Before choosing a server, should you score line count or operational requirements? **Verifiable requirements** for protocol, security, throughput, p95/p99, timeouts, quotas, monitoring, lifecycle, maintenance, and integration.

## 26. Final checklist and references

Before signing off on the decision to use `jdk.httpserver`:

- [ ] Identify the use case: test, loopback internal, embedded admin API, or public multi-tenant.
- [ ] Lock down HTTP version, TLS, WebSocket/gRPC/SSE requirements; do not promise features the API does not have.
- [ ] Check literal prefix routing, path decode/case-sensitivity, and method checks.
- [ ] Design request body quota, header size/resource budgets, timeouts, and slow-client behavior.
- [ ] Set executor before start; choose bounded pool/queue/admission and overload response behavior.
- [ ] Define authn + per-resource authz, secrets, mTLS, and trusted proxy boundaries.
- [ ] If using HTTPS, have a proper `SSLContext`, cert rotation, and TLS verification plan.
- [ ] Standardize Content-Type, charset, length = UTF-8 byte count, and close `HttpExchange` properly.
- [ ] Create filter/error-mapping and log/metrics bounds; do not log credentials.
- [ ] Add health/readiness, tracing, structured access logs, and incident runbooks.
- [ ] Verify `stop(delay)`, orchestrator draining, and do not rely on restarting the same server object.
- [ ] Load test with realistic workloads; measure p95/p99, error rate, memory, queue, threads, and sockets.
- [ ] Have an owner and maintenance budget for any middleware or protocol logic that must be self-built.
- [ ] Record the decision clearly: **JDK server directly**, **JDK server + gateway**, or **dedicated framework/server**.

**Conclusion:** `HttpServer` in JDK 17 is a **useful embedded HTTP server**, not a full web framework. It provides sufficient building blocks for many small applications when risk and load are controlled, but **literal prefix routing, blocking handlers, default executor, middleware/protocol limits, security, and operations** are costs that must be examined before choosing. The right decision is one based on measurable requirements, tests, and ownership, rather than assuming "fewer dependencies = production-ready".

### Official Java SE 17 Sources

- [Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html)
- [Package com.sun.net.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html)
- [HttpServer — contexts, executor, backlog, stop](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [HttpContext — filters and authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html)
- [HttpExchange — request/response lifecycle, length and close](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html)
- [Filter — pre/post-processing](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html)
- [HttpsServer / HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html)
- [Executors.newFixedThreadPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html) and [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).
