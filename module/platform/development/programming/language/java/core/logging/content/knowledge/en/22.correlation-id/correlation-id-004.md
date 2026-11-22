# Propagating Correlation ID over HTTP in Java

## 1. Lesson Objectives

When an HTTP request traverses multiple services, each service typically has its own Logger, threads, process, and log storage. For example, a payment operation might follow this path:

~~~text
Browser / mobile client
       |
       v
API Gateway
       |
       v
Order Service --------> Inventory Service
       |
       v
Payment Service
~~~

If Order Service logs **"payment failed"** while Payment Service logs **"gateway timeout"**, how do you know both events belong to the same request? One solution is a **Correlation ID**: an identifier carried across related HTTP requests and recorded in each service's logs. During investigation, searching for records with the same ID narrows down the scope.

**Propagating over HTTP** means defining how to **receive**, **validate**, **generate when missing**, **forward**, and **return** a correlation ID via HTTP headers, while attaching this ID to the logging context where needed.

This lesson belongs to the **Correlation ID** group of **Java Core Logging**. The content focuses on propagating IDs over HTTP, rather than becoming a complete guide to authentication, distributed tracing, or idempotency.

By the end of this lesson, you will be able to:

- Distinguish **Correlation ID** from **request ID**, **trace ID**, **span ID**, and **Idempotency-Key**.
- Choose an HTTP header contract such as **X-Correlation-ID** and understand the **case-insensitivity** of header names.
- Handle missing, empty, malformed, oversized, or multi-valued headers.
- Decide whether to keep an incoming ID or generate a new ID at a **trust boundary**.
- Forward the ID to outbound HTTP requests, including when a service calls multiple dependencies.
- Include the ID in responses and logs; understand when CORS configuration is needed so JavaScript clients can read response headers.
- Write a standalone **Java 17** example using **HttpServer**, **HttpClient**, and JUL Logger; inspect verified stdout/stderr output.
- Manage scoping and propagate logging context across executors/async boundaries without leaking IDs between requests.
- Design tests to verify propagation, validation, and troubleshooting across API gateways, services, and downstream dependencies.
- Avoid using a correlation ID as a credential, business key, or mechanism to guarantee single-execution semantics.

## 2. What is a Correlation ID?

A **Correlation ID** is an identifier used to **link related events within a processing flow**. It does not have to be a UUID, but it needs an agreed-upon format and length, sufficient collision resistance for its scope, and no sensitive data.

Example:

~~~text
Correlation ID: demo-42

gateway  | cid=demo-42 event=http.request.received
order    | cid=demo-42 event=order.accepted
payment  | cid=demo-42 event=payment.timeout
gateway  | cid=demo-42 event=http.request.failed status=502
~~~

Searching by **cid=demo-42** surfaces the related records. However, sharing the same ID only indicates that they **share the same correlation context**; it does not by itself prove causality, data accuracy, or absolute uniqueness.

### 2.1. One ID can cross multiple HTTP hops

Simple pattern:

~~~text
HTTP client
    |
    | X-Correlation-ID: demo-42
    v
Gateway
    |
    | X-Correlation-ID: demo-42
    v
Checkout Service
    |
    | X-Correlation-ID: demo-42
    v
Payment Service
~~~

At each hop, the application reads the ID and:
1. Logs it safely under a **consistent field name**.
2. Forwards the accepted ID downstream.
3. Does not generate a new ID for each internal call if end-to-end linkage is desired.

For multi-step workflows, keeping the same correlation ID does not mean every operation is **the same HTTP request**. The gateway has its request, checkout has another, and payment has another; they simply share the same correlation context.

### 2.2. Correlation ID is not business data

Do not use a correlation ID to:
- Authenticate access or determine what a user is permitted to do.
- Act as a session token, CSRF token, access token, or secret.
- Confirm that an amount has been paid.
- Serve as the unique key of an order or business transaction.
- Guarantee that retried requests do not create duplicate operations.

The ID serves **observability and troubleshooting**, not business contracts.

## 3. Choosing an HTTP Header and Defining the Contract

A system can use a custom header, for example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Correlation-ID: demo-42
~~~

This is an illustrative HTTP request; the **example.test** domain is only an example, not the address of the Java demo below.

**X-Correlation-ID is a common system-chosen name, not a mandatory HTTP or W3C Trace Context standard.** Other names like **X-Request-ID** are also common. Within an organization, what matters is **choosing one official name**, defining each component's responsibility, and using that name consistently.

### 3.1. HTTP header names are case-insensitive

According to HTTP Semantics (RFC 9110), **field/header names are case-insensitive**. For example:

~~~text
X-Correlation-ID
x-correlation-id
X-CORRELATION-ID
~~~

all represent the same header name at the protocol level. Do not write code that compares header names with a case-sensitive match on raw request text when the framework already provides header structures.

In Java 17:
- **HttpRequest.Builder.header("X-Correlation-ID", id)** sets the header on an outbound request.
- **HttpHeaders.firstValue("X-Correlation-ID")** retrieves the first value if present.
- **HttpExchange.getRequestHeaders().get("X-Correlation-ID")** accesses values from HttpServer Headers.

These header APIs handle header names according to HTTP semantics; the demo intentionally sends lowercase **x-correlation-id** and retrieves it in uppercase on the server to verify this.

### 3.2. Defining the value contract

You should not accept an unbounded string from a client and write it straight into logs. A contract might specify:

| Attribute | Example rule |
| --- | --- |
| Header name | X-Correlation-ID |
| Type | ASCII String |
| Length | 1–64 characters |
| Charset | A–Z, a–z, 0–9, period, underscore, hyphen |
| First character | Letter or digit |
| Value count | Accept exactly one value |
| Missing/invalid | Generate a new ID or return an error, per policy |
| New value | Server-generated UUID version 4 |
| Outbound | Forward the accepted ID |
| Response | May echo the ID to aid investigation |
| Logging | Standard field key such as correlation_id |

**This is an illustrative policy, not a mandatory RFC.** Another system might accept only canonical UUIDs, use a dedicated trace ID, or distinguish IDs issued by a trusted gateway from IDs arriving from the Internet.

### 3.3. Why restrict characters?

Clients might send values containing newlines, control characters, unusual Unicode, or long strings. If those values are inserted directly into log text:
- A value with newlines can forge log lines (**log injection**).
- Extremely long strings inflate log/storage costs.
- Control characters break parsers or viewers.
- Client-supplied metadata can be mistaken for trusted information.

Always **validate before logging and forwarding**. Do not log the raw invalid incoming ID just for "debugging"; if you need telemetry on bad input, log a controlled event code and reason.

## 4. Inbound Flow: Receive, Validate, Generate When Missing

At the HTTP inbound boundary, a practical algorithm:

~~~text
Receive HTTP request
       |
       v
Read X-Correlation-ID
       |
       v
Exactly one valid value?
  +----+----------------+
  | Yes                 | No
  v                     v
Keep value         Generate new ID
  |                     |
  +----------+----------+
             |
             v
Accepted Correlation ID
             |
             +--> Attach to log context
             +--> Forward to HTTP outbound
             +--> Optionally return in response header
             |
             v
End of request: clean up logging context
~~~

### 4.1. Missing header

If the client did not send a correlation ID, the server/gateway can generate a new ID so that subsequent logs for the request share a common key.

Example:

~~~java
String correlationId = UUID.randomUUID().toString();
~~~

This is an illustrative Java snippet that requires importing java.util.UUID and placing it in an appropriate method. UUIDv4 is a common choice for a new ID; **it is not a security secret**. When a UUID has no business meaning, it cannot be used to authenticate anything.

### 4.2. Empty, malformed, or oversized header

Examples of values to reject under the policy in section 3:

~~~text
X-Correlation-ID:
X-Correlation-ID: bad value
X-Correlation-ID: includes/unsafe/path
X-Correlation-ID: [very long string exceeding limit]
~~~

There are at least two valid strategies depending on the contract:
- **Generate-and-continue:** replace with a new ID, continue processing, and optionally log a warning for the invalid input.
- **Reject request:** return **400 Bad Request** if the API contract requires the client to send a valid ID.

In the demo, we choose **generate-and-continue** so the HTTP flow does not depend on the client sending the header. In an API that requires a gateway-issued correlation ID, a different policy can be chosen.

### 4.3. Multiple values with the same header name

According to RFC 9110, field lines with the same name may be combined depending on the field's semantics. For a custom correlation ID defined as **a single token**, a multi-value list or a combined value containing a comma should be treated as invalid unless the contract explicitly specifies otherwise.

Example:

~~~http
X-Correlation-ID: a
X-Correlation-ID: b
~~~

Do not arbitrarily pick the first value. Proxies, frameworks, or HTTP stacks may combine them differently. The demo enforces a **single-element list** rule, then applies the regex; if there are multiple elements, it generates a new ID. If a proxy combines them into **a, b**, the value containing a comma will also fail the regex.

**Important:** Unit tests for a two-element list do not fully replace integration tests through a real proxy; test how your proxy and server framework handle duplicate header fields.

### 4.4. Trust boundary matters more than header name

A client-supplied ID is **untrusted input**. Even if it passes the regex, a client could choose **demo-42** intentionally to collide with another request's ID. This does not grant the client access to logs, but it can **pollute correlation** if the system treats client-supplied IDs as an absolute source of truth.

Depending on your risk model:
- The gateway can **always generate a new internal correlation ID** and store the external ID in a separate, controlled field.
- For trusted clients, the gateway may keep a valid incoming ID.
- Before calling a public external API, you may **strip or replace** internal correlation IDs to avoid leaking metadata.
- Do not use an incoming ID as a rate-limit identity, security principal, or transaction deduplication key.

Write a clear contract specifying who may generate, keep, replace, and receive the ID at each boundary.

## 5. Outbound: Forwarding the ID to Downstream HTTP Requests

After the gateway accepts the ID **demo-42**, an internal call can use:

~~~java
HttpRequest outbound = HttpRequest.newBuilder(downstreamUri)
        .header("X-Correlation-ID", correlationId)
        .GET()
        .build();
~~~

This is an illustrative snippet inside a method that already has **downstreamUri** and **correlationId**, requiring java.net.http.HttpRequest. It builds a new request and sets the header with the current ID, **without generating a different ID at the outbound hop**.

### 5.1. Keep the same ID or generate a child ID?

For **a cross-service correlation ID**, you typically keep it unchanged as it flows:
- Gateway → order service;
- order service → payment service;
- order service → inventory service;
- retries belonging to the same request-level operation when unified analysis is needed.

If you want to distinguish individual attempts, add **attempt_id**, **retry_count**, or **span_id** rather than changing the main correlation ID on each attempt.

Example:

~~~text
correlation_id=demo-42 attempt=1 event=payment.requested
correlation_id=demo-42 attempt=2 event=payment.requested
correlation_id=demo-42 attempt=2 event=payment.completed
~~~

Depending on the contract, a background job or event triggered after a request may also carry **causation_id** or **parent_correlation_id** instead of keeping one ID forever across multi-day operations. The goal is to link the right scope, not create an unbounded log group.

### 5.2. Do not blindly forward all headers

Do not take all headers from an inbound request and copy them indiscriminately to every outbound request. Doing so can accidentally leak cookies, Authorization, PII, secrets, or hop-by-hop/proxy headers.

Instead, **allowlist** only the headers that are necessary and permitted to forward, including the validated correlation ID. Authorization and tracing contexts have their own policies. **A correlation ID is not a credential**, but its exposure level should still be considered.

### 5.3. Common HTTP clients

In Java 17, the example uses **java.net.http.HttpClient**. Real-world frameworks may use:
- Spring RestClient/RestTemplate/WebClient depending on framework version;
- Apache HttpClient;
- OkHttp;
- JAX-RS Client;
- Feign or a custom-wrapped HTTP client.

The common pattern is to set the header in a **client interceptor/filter/request builder**. Centralizing this reduces the risk of an endpoint forgetting to forward the ID, but the interceptor must read **the current request's context**, never a static variable holding the last ID.

### 5.4. Outbound timeouts and errors

When calling downstream, timeouts or IOExceptions must also be logged with the **current correlation ID**. If the client times out before downstream responds, downstream may still be processing; the shared ID helps investigate both sides.

Never assume **"timeout means downstream did nothing"**. For operations with side effects like payments, retries require separate idempotency semantics; the correlation ID is only for finding logs.

## 6. Response Header: Helping Callers Find Related Logs

After processing, the API can return:

~~~http
HTTP/1.1 200 OK
X-Correlation-ID: demo-42
Content-Type: text/plain; charset=UTF-8

downstream-ok
~~~

This allows the client or support team to record the correlation ID when reporting an error instead of searching logs by an approximate timestamp.

An HTTP 500/502 response can also include the corresponding ID if the server is still able to construct a response. However:
- If the socket is closed or a reverse proxy generates an error before the request reaches the app, the app cannot guarantee the ID is in the response header.
- Do not expose risky secrets or internal identifiers in public responses; only return an opaque ID per policy.
- Do not treat the presence of the ID in a response as proof that the request succeeded.

### 6.1. Reading the response header in a Java client

~~~java
String id = response.headers()
        .firstValue("X-Correlation-ID")
        .orElse("missing");
~~~

This snippet assumes an existing **response** variable of type HttpResponse. Java's HttpHeaders.firstValue returns an Optional; orElse provides a fallback display value when the header is absent. **Do not assume every downstream echoes the header**, unless your system contract defines it.

### 6.2. Browser CORS: when can JavaScript clients read the header?

For **cross-origin fetch** requests, a custom response header such as **X-Correlation-ID** is normally not readable by JavaScript unless the server exposes it via CORS.

When policy permits, the response can declare:

~~~http
Access-Control-Expose-Headers: X-Correlation-ID
~~~

If browser JavaScript needs to **send a custom X-Correlation-ID request header** cross-origin, CORS preflight may also require **Access-Control-Allow-Headers: X-Correlation-ID** along with appropriate Allow-Origin/Methods/Credentials settings.

**Do not add wildcard CORS indiscriminately**; expose and allow only the origins and headers that are permitted. Having CORS headers does not replace validation or trust boundaries for the correlation ID. CORS applies to the browser security model, not standard Java HttpClients.

## 7. Attaching the ID to Logs Without Leaking Across Requests

Passing headers only solves **network propagation**. For logs emitted inside each service to display the ID, the logging code needs context.

A pattern using SLF4J MDC:

~~~java
String previous = MDC.get("correlationId");
MDC.put("correlationId", acceptedId);
try {
    service.handleRequest();
} finally {
    if (previous == null) MDC.remove("correlationId");
    else MDC.put("correlationId", previous);
}
~~~

This is **illustrative application code using SLF4J**, not a standalone program; the referenced variables and objects must be defined. The idea:
1. Obtain **acceptedId** after validating the incoming header.
2. Put it in MDC before business logic logs anything.
3. In the Layout/Encoder, output the **correlationId** MDC field.
4. Restore the previous value or remove the key in `finally`.

In Logback PatternLayout, for example:

~~~text
%level|cid=%X{correlationId:-none}|%logger|%msg%n
~~~

Log4j2 has a similar mechanism via **ThreadContext** and PatternLayout. In JUL, you can use a custom Formatter/LogRecord or a self-managed logging context depending on the design. The main demo uses JUL and **embeds the validated ID in the message** so it has no dependencies outside the JDK; for production services, structured logging/MDC is easier to query.

### 7.1. Never use a mutable static variable for the current correlation ID

Broken design:

~~~java
static String currentCorrelationId;
~~~

If two requests run concurrently and write to the variable, the ID will be overwritten and logs will be mixed. Use:
- Request-scoped context;
- MDC/ThreadContext bound to the appropriate scope;
- or pass an explicit context object through method arguments.

**ThreadLocal does not automatically propagate across all threads.** When switching to ExecutorService/CompletableFuture/reactive execution, capture and restore context at the proper boundaries; thread pools reuse threads for other requests.

### 7.2. Cleaning up MDC in finally is required for correctness

A request can throw an exception, time out, be canceled, or return early. Without cleanup, the next worker thread task may log with the previous request's ID.

Responsible pattern:
- Set the ID in an HTTP filter/interceptor.
- Use try/finally, including error paths.
- Restore the previous context if scopes can nest.
- Capture + restore when handing work off to a worker thread.
- Do not clear the entire framework context if you only own one key.

### 7.3. Structured logging is a better choice for analysis

Compare:

~~~text
INFO request completed cid=demo-42 status=200
~~~

with a JSON event:

~~~json
{
  "event": "http.request.completed",
  "level": "INFO",
  "service": "gateway",
  "correlation_id": "demo-42",
  "status_code": 200
}
~~~

A backend with an explicit **correlation_id** schema field supports exact-match filtering without relying on text parsers. If your backend only stores raw messages, you can still search strings, but prefer consistently typed and named fields when building dashboards or tracing links.

**Do not automatically dump sensitive IDs or all headers into MDC.** Keep the context small, allowlisted, and cleaned up with the lifecycle.

## 8. Complete Java 17 Example: Two HTTP Servers and One Client

The following example uses:
- **com.sun.net.httpserver.HttpServer** from the **jdk.httpserver** module;
- **java.net.http.HttpClient** from Java 11+ (included in Java 17);
- **java.util.logging.Logger/ConsoleHandler** to print logs to stderr;
- **UUID.randomUUID()** for new IDs;
- **Pattern** for format validation;
- two HTTP servers bound only to **127.0.0.1**, each using **port 0** so the OS picks an available port.

**No Maven or external libraries are needed.** Everything lives in a single **CorrelationHttpDemo.java** file with a complete `main()`.

### 8.1. Test diagram

~~~text
main() Java HttpClient
  |
  | GET /gateway
  | x-correlation-id: demo-42
  v
HttpServer gateway (127.0.0.1, random port)
  | validate -> accepts demo-42
  | LOG: cid=demo-42 event=gateway.received
  |
  | GET /downstream
  | X-Correlation-ID: demo-42
  v
HttpServer downstream (127.0.0.1, random port)
  | validate -> accepts demo-42
  | LOG: cid=demo-42 event=downstream.received
  | response: X-Correlation-ID: demo-42
  v
Gateway verifies downstream response header
  | LOG: cid=demo-42 event=gateway.completed
  | response: X-Correlation-ID: demo-42
  v
main() prints status/header/body
~~~

Because HTTP header names are case-insensitive, the client sending **x-correlation-id** and the server reading **X-Correlation-ID** works as expected.

### 8.2. Source file CorrelationHttpDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.regex.Pattern;

public final class CorrelationHttpDemo {
    private static final String HEADER = "X-Correlation-ID";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Logger GATEWAY = Logger.getLogger("gateway");
    private static final Logger DOWNSTREAM = Logger.getLogger("downstream");

    public static void main(String[] args) throws Exception {
        configure(GATEWAY);
        configure(DOWNSTREAM);

        HttpServer downstream = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        downstream.createContext("/downstream", exchange -> {
            String id = selectId(exchange.getRequestHeaders().get(HEADER));
            DOWNSTREAM.info("cid=" + id + " event=downstream.received");
            respond(exchange, 200, id, "downstream-ok");
        });

        HttpServer gateway = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3)).build();
        URI downstreamUrl = URI.create("http://127.0.0.1:"
                + downstream.getAddress().getPort() + "/downstream");
        gateway.createContext("/gateway", exchange -> {
            String id = selectId(exchange.getRequestHeaders().get(HEADER));
            GATEWAY.info("cid=" + id + " event=gateway.received");
            try {
                HttpRequest outgoing = HttpRequest.newBuilder(downstreamUrl)
                        .timeout(Duration.ofSeconds(3))
                        .header(HEADER, id)
                        .GET().build();
                HttpResponse<String> upstream = client.send(outgoing,
                        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
                if (!id.equals(upstream.headers().firstValue(HEADER).orElse(""))) {
                    throw new IOException("Downstream correlation mismatch");
                }
                GATEWAY.info("cid=" + id + " event=gateway.completed");
                respond(exchange, upstream.statusCode(), id, upstream.body());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                GATEWAY.warning("cid=" + id + " event=gateway.interrupted");
                respond(exchange, 502, id, "gateway-error");
            } catch (IOException ex) {
                GATEWAY.warning("cid=" + id + " event=gateway.upstream_failed");
                respond(exchange, 502, id, "gateway-error");
            }
        });

        try {
            downstream.start();
            gateway.start();
            URI gatewayUrl = URI.create("http://127.0.0.1:"
                    + gateway.getAddress().getPort() + "/gateway");
            HttpRequest request = HttpRequest.newBuilder(gatewayUrl)
                    .header("x-correlation-id", "demo-42")
                    .timeout(Duration.ofSeconds(3))
                    .GET().build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("response.status=" + response.statusCode());
            System.out.println("response.header="
                    + response.headers().firstValue(HEADER).orElse("missing"));
            System.out.println("response.body=" + response.body());
            System.out.println("missing.generatedUUID="
                    + isUuid(selectId(null)));
            System.out.println("invalid.generatedUUID="
                    + isUuid(selectId(List.of("bad value"))));
            System.out.println("duplicates.generatedUUID="
                    + isUuid(selectId(List.of("a", "b"))));
        } finally {
            gateway.stop(0);
            downstream.stop(0);
        }
    }

    private static String selectId(List<String> values) {
        return values != null && values.size() == 1
                && SAFE_ID.matcher(values.get(0)).matches()
                ? values.get(0) : UUID.randomUUID().toString();
    }

    private static boolean isUuid(String id) {
        try {
            UUID uuid = UUID.fromString(id);
            return uuid.version() == 4 && uuid.toString().equals(id);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static void respond(HttpExchange exchange, int status,
                                String id, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(HEADER, id);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void configure(Logger logger) {
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override public String format(LogRecord record) {
                return record.getLevel().getName() + "|"
                        + record.getLoggerName() + "|"
                        + record.getMessage() + System.lineSeparator();
            }
        });
        logger.addHandler(console);
    }
}
~~~

### 8.3. Compiling and running

Save the source in **CorrelationHttpDemo.java** in any writable directory. Run with JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 CorrelationHttpDemo.java
java --add-modules jdk.httpserver CorrelationHttpDemo
~~~

Depending on the module/classpath environment, **--add-modules jdk.httpserver** explicitly includes the server module in the run command. The example was compiled with **javac --release 17** and run successfully in a Java JVM that includes this module.

**Do not put Java 17's HttpClient in try-with-resources.** In Java 17, HttpClient does not implement AutoCloseable; the example uses HttpClient normally and manages the two HttpServers with **try/finally** to stop them. Newer JDK versions may have different HttpClient lifecycle management, so when learning Java 17, follow this version's API.

### 8.4. Verified Stdout

~~~text
response.status=200
response.header=demo-42
response.body=downstream-ok
missing.generatedUUID=true
invalid.generatedUUID=true
duplicates.generatedUUID=true
~~~

In the demo, the randomly generated UUID values are not printed directly; the program only checks that they match canonical UUIDv4 format and prints **true**. This keeps the stdout output **deterministic** and independent of random IDs.

### 8.5. Verified Stderr

**JUL ConsoleHandler writes to System.err**, not System.out. With the demo's Formatter, stderr is:

~~~text
INFO|gateway|cid=demo-42 event=gateway.received
INFO|downstream|cid=demo-42 event=downstream.received
INFO|gateway|cid=demo-42 event=gateway.completed
~~~

If your IDE merges stdout and stderr into a single console, the display order between the two streams may interleave. This is not evidence of broken propagation; separate the streams and inspect logging events by ID, timestamp, and execution model.

### 8.6. Why does the demo accept a lowercase header?

HttpClient sends:

~~~java
.header("x-correlation-id", "demo-42")
~~~

While the gateway calls:

~~~java
exchange.getRequestHeaders().get("X-Correlation-ID")
~~~

Both names are treated by the HTTP headers API as the same field name per HTTP's case-insensitivity rule. Normalizing the header name does not alter the ID **value**; the demo preserves **demo-42** across hops.

### 8.7. Why does downstream also validate?

Downstream receives requests from the gateway, but a real endpoint might be called from multiple sources or pass through proxies. Therefore, downstream can still validate incoming values. Within a **trusted service-to-service network**, policy may accept the gateway's ID if valid. To prevent spoofing or enforce different rules at a boundary, add trust controls rather than relying on regex alone.

In the demo, both gateway and downstream apply the same policy, so downstream keeps **demo-42**. The gateway also checks the header in the upstream response: if downstream returns a different ID, the demo treats it as a mismatch and handles it as a gateway error.

### 8.8. Meaning of the three UUID check lines

- **missing.generatedUUID=true**: when the header is absent, `selectId(null)` generates a UUIDv4.
- **invalid.generatedUUID=true**: a string containing spaces like **"bad value"** fails the regex, so a UUIDv4 is generated.
- **duplicates.generatedUUID=true**: a two-value list **["a","b"]** is treated as ambiguous, so a UUIDv4 is generated.

These are **unit-like checks for `selectId`** placed in `main`; the real HTTP request test only exercises the valid header case. For production protection behind a proxy, add integration tests that actually send missing/invalid/duplicate headers and verify how the framework canonicalizes headers.

## 9. Analyzing Decisions in the Example

### 9.1. Why bind to 127.0.0.1?

The demo is only for local testing. **127.0.0.1** is not a public address, so it does not expose an experimental HTTP service to others on the network. When running a production server, binding, TLS, authentication, concurrency, and resource limits must be managed by an appropriate framework and infrastructure.

### 9.2. Why use port 0?

A fixed port like 8080 might already be in use by another application. **new InetSocketAddress("127.0.0.1", 0)** asks the OS to assign an available port when HttpServer binds; the code then reads **getAddress().getPort()** to construct the URI. This makes the demo easy to run repeatedly on a developer machine.

### 9.3. Why choose a 64-character regex limit?

~~~java
Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
~~~

This pattern accepts only 1–64 safe ASCII characters under our learning policy:
- First character is a letter or digit.
- 0–63 subsequent characters are letters, digits, periods, underscores, or hyphens.
- Rejects spaces, commas, newlines, slashes, and empty strings.

It **does not prove the ID is unique, trusted, or belongs to a user**. A regex is only **format validation**. When a boundary must distinguish trusted IDs from client-provided IDs, add a dedicated trust policy.

### 9.4. Why do both servers use the same correlation ID?

The gateway receives the initial request, validates the ID, and sets it on the outbound HttpRequest. Downstream reads that exact ID, logs it, and echoes it in the response. The gateway verifies the echo and returns the ID to the caller. This mechanism lets you filter logs across services with a single string **demo-42**.

If the gateway generated a different ID for outbound calls, the two sides could split into two correlation groups. If you genuinely need separate IDs for sub-operations, use **parent ID**, **span ID**, or **attempt ID** in your schema instead of silently replacing the original ID.

### 9.5. Why catch InterruptedException separately?

`HttpClient.send` can throw **InterruptedException**. When caught, the example calls **Thread.currentThread().interrupt()** to restore the interrupt flag, logs a warning, and attempts to return 502. This is a notable best practice when blocking operations can be canceled. In a production server, cancellation and response lifecycle handling should match the framework.

### 9.6. Limitations of the learning code

This example is not a production reverse proxy:
- No TLS, authentication, authorization, or rate limiting.
- No retries, circuit breaker, backpressure, or dedicated thread pool.
- Only supports one GET endpoint and a fixed text body.
- No structured JSON logger or MDC; the ID is concatenated into the message after validation.
- No validation of downstream HTTP status/body beyond checking the correlation header.
- No CORS policy or centralized middleware for attaching IDs.
- Catching IO/interrupt errors is illustrative only; it does not cover all runtime errors, shutdown, or cases where the response has already started streaming.
- Logs from containers/proxies before the request reaches the application may be missing.
- No encryption or secret management for the ID because a correlation ID **is not a credential**.

For real deployments, use an HTTP framework and client interceptors/filters with well-designed lifecycle, observability, timeout, and security policies.

## 10. Building Middleware/Filters for Real Applications

Do not copy-paste header reading and forwarding logic into every controller ad hoc. A maintainable approach is to place it in middleware.

### 10.1. Inbound filter

Responsibilities:
1. Read the header under the agreed name.
2. Validate count/format/trust.
3. Accept or generate a new ID.
4. Store it in the request context and logging context.
5. Invoke the application handler.
6. Return the ID in the response when policy permits.
7. Clean up the logging context in `finally`.

Conceptual code:

~~~java
String id = resolveCorrelationId(requestHeaders);
String previous = MDC.get("correlationId");
MDC.put("correlationId", id);
try {
    responseHeaders.set("X-Correlation-ID", id);
    nextHandler();
} finally {
    if (previous == null) MDC.remove("correlationId");
    else MDC.put("correlationId", previous);
}
~~~

This is **integration pseudocode**: `requestHeaders`, `responseHeaders`, `nextHandler`, and the MDC adapter must be replaced with your actual framework APIs. This snippet does not run standalone, unlike the complete demo in section 8.

If a request is handed off to an async callback after the filter returns, the middleware must manage propagation and response lifecycle according to the framework, rather than leaving a ThreadLocal on the current thread until another callback finishes.

### 10.2. Outbound client interceptor

Responsibilities:
1. Retrieve the accepted ID from the request context (never trust a global variable).
2. Validate or normalize if the context was constructed from other data.
3. Attach the header to the outbound request.
4. Do not overwrite the ID when a higher-level workflow has already defined a different parent/child context.
5. Do not forward the header outside the trust domain if policy forbids it.

Example logic:

~~~java
String id = requestContext.correlationId();
HttpRequest outgoing = HttpRequest.newBuilder(targetUri)
        .header("X-Correlation-ID", id)
        .GET().build();
~~~

This is an illustrative snippet: `requestContext`/`targetUri` are provided by the application, not a standalone class. A real interceptor may run across multiple threads or handle concurrent requests; never store `id` in mutable state on a singleton interceptor.

### 10.3. Gateway and reverse proxy

When a reverse proxy sits in front of the application, decide:
- Does the proxy **keep the incoming ID** or **generate a new ID**?
- Does the proxy forward the ID upstream as a header?
- Could the header be stripped or renamed across hops?
- Do proxy-generated 4xx/5xx responses include the ID?
- If both proxy and app can generate IDs, which is the **authoritative source**?
- Does the system span CDNs/load balancers across multiple trust zones?

Usually, there should be one official point that accepts/generates the ID at the first managed boundary, and downstream services preserve it per contract. However, the exact choice must align with security and integration requirements.

## 11. How Correlation ID, traceparent, and Idempotency Keys Differ

These concepts are easily confused, especially in microservices applications.

| Value | Primary purpose | Notes |
| --- | --- | --- |
| **Correlation ID** | Group logs/events of a processing flow | Can be a custom HTTP header |
| **Request ID** | Identify a specific HTTP request/boundary | May differ across hops |
| **W3C trace-id** | Identify a distributed trace | Part of the W3C Trace Context standard |
| **W3C parent-id/span ID** | Track an operation/span in a trace graph | Not an arbitrary correlation ID |
| **Idempotency-Key** | Let the backend recognize retries of the same operation per contract | Does not replace authentication or transaction management |
| **Business ID** | Identify an order, payment, invoice, etc. | Has its own business lifecycle |

### 11.1. W3C Trace Context

W3C standardizes the **traceparent** and **tracestate** headers for distributed tracing. Example **traceparent**:

~~~http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
~~~

It consists of version, trace-id, parent-id, and trace-flags. You should not replace this entire header with **X-Correlation-ID: demo-42** and expect a tracing system to understand it. A system can **use both** X-Correlation-ID and traceparent simultaneously, or use trace-id as the correlation key in logs when tracing is already integrated into the architecture.

If you have OpenTelemetry instrumentation, prefer the tracing framework's standard context propagation. Do not manually craft or modify traceparent arbitrarily: when a new span is created, parent/span semantics must follow the standard rather than copying the exact string across every operation.

### 11.2. Correlation ID and Idempotency-Key

In an API that supports idempotency, **Idempotency-Key** helps recognize a **repeated attempt of the same operation** to avoid creating duplicate side effects, subject to backend retention and policy. Correlation ID only helps link logs.

Example of a client retrying a payment:

~~~text
Attempt 1: correlation_id=demo-42; idempotency_key=pay-777
Attempt 2: correlation_id=demo-42; idempotency_key=pay-777
~~~

Using the same correlation ID helps find the retry logs, but **only a backend with proper idempotency mechanisms decides whether to execute the operation again**. Do not use correlation ID directly as an idempotency key unless the contract specifies it; they may have different scopes and lifetimes.

### 11.3. Baggage is not an arbitrary data store

Tracing systems may use W3C Baggage to propagate key–value context across service boundaries. Because baggage can be forwarded to many downstream services, only store data that is safe to share and keep its size bounded; never put tokens or PII into baggage or custom correlation headers.

## 12. Real-World HTTP Cases Requiring Clear Decisions

### 12.1. Retries

Keep the **correlation ID** across attempts of the same logical operation when unified analysis is desired. Log the attempt number as well:

~~~text
cid=demo-42 attempt=1 event=downstream.timeout
cid=demo-42 attempt=2 event=downstream.success
~~~

Do not generate a new ID for each retry without recording the relationship; that makes investigation harder. If you need a per-attempt ID, put it in a separate field.

### 12.2. Parallel fan-out

A service might call payment and inventory simultaneously:

~~~text
checkout
  | cid=demo-42
  +--> payment   (cid=demo-42)
  +--> inventory (cid=demo-42)
~~~

Both outbound calls must receive the accepted ID. With Java **CompletableFuture** or ExecutorService, do not read the main request's MDC from a worker thread unless context has been propagated. Instead, pass **id** explicitly as a task parameter or use a context-aware wrapper.

### 12.3. Background tasks after the HTTP response

If a request triggers a job that runs for several minutes, decide whether the job uses:
- The same correlation ID to support end-to-end lookup;
- or a new `jobId` plus `parent_correlation_id` to avoid creating an overly large correlation group.

Base this decision on business semantics and observability needs. If work moves through a message queue, HTTP headers naturally **do not travel with the message**; map the ID to message headers/attributes according to your messaging contract.

### 12.4. Redirects

When an HTTP client automatically follows redirects, check your header forwarding policy and trust domains. Do not assume custom correlation IDs or credential headers should be forwarded to every host in a redirect chain. If a redirect points to an untrusted domain, prevent leaking internal context.

### 12.5. HTTP proxies or service meshes

Proxies can add/remove headers, merge duplicate fields, or generate error responses. When upstream and downstream logs show different IDs, check:
- Did the client set the header before sending the request?
- Did the gateway rename or strip it?
- Did the reverse proxy generate a different ID?
- Is the app reading the right header name?
- Did downstream regenerate it due to a validation failure?
- Was the response header written by the app or the proxy?
- Was the ID pulled from a wrong-thread request context?

### 12.6. HTTP/2 and case-insensitive header semantics

HTTP header names are semantically case-insensitive; different HTTP versions have different wire representations. **Never use header casing to carry business information.** Code should handle the same field name consistently through standard framework/HTTP APIs rather than parsing raw header lines.

## 13. Security, Privacy, and Preventing Log Injection

Correlation IDs are often treated as debugging metadata, yet they remain data that can be **controlled by the client**.

### 13.1. Never log raw untrusted headers

Wrong:

~~~java
LOG.info("received cid=" + rawClientHeader);
~~~

This is an illustrative snippet with variables `LOG` and `rawClientHeader`. If the raw value contains newlines or control characters, the output can forge log records; if it is too long, it can flood logs.

Better:

~~~text
1. Read inbound header
2. Validate length, character set, duplicates and trust policy
3. Accept or generate safe ID
4. Log accepted ID
5. Propagate accepted ID to allowed destinations
~~~

If you want to know when clients send bad IDs, log **event=correlation.invalid reason=bad_format**, without logging raw data that might contain malicious content.

### 13.2. Do not embed sensitive information in the ID

Avoid generating correlation IDs like:

~~~text
user-email@example.test-order-42
phone-xxxx-xxxx
access_token_....
~~~

A correlation ID should be an **opaque identifier**. If an ID contains a user ID or tenant information, review privacy policies, access controls, and retention. In particular, never use passwords, access tokens, refresh tokens, cookies, OTPs, or private keys.

### 13.3. Client-controlled IDs have no security authority

Even a client-supplied UUIDv4 does not prove the client owns that ID. Therefore:
- Do not use a correlation ID to bypass authentication.
- Do not allow an internal log-search API to query solely by ID without authorization.
- Do not return sensitive data just because the caller knows the ID.
- Do not use a client-supplied ID as an access-control principal.
- Do not assume the same ID means all requests came from the same user.

### 13.4. Header value size and resource budgets

Systems should bound overall HTTP headers and individual custom fields at the infrastructure layer. If an ID is too long, policy should reject it or generate a new one. Do not pack hundreds of metadata fields into a single header or expand header buffers indefinitely just for debugging.

### 13.5. Log retention and exposure

A correlation ID may appear in:
- Application logs;
- proxy/access logs;
- tracing links;
- customer-facing response headers;
- support tickets.

It can help correlate data across systems. Thus, retention and access still require clear policies; do not expose internal log-search tools to everyone solely by correlation ID.

## 14. Testing: Proving Propagation Works

Useful tests should cover **input**, **forwarding**, **response**, and **logging**.

| Scenario | Expectation |
| --- | --- |
| Valid incoming ID | Gateway keeps ID; downstream and response use the same ID |
| Lowercase header name | Server still reads it |
| Missing header | Gateway generates a new ID per policy |
| Empty or whitespace header | Raw value is not written to logs |
| Oversized header | Rejected or replaced with a new ID per contract |
| Two header values | Does not arbitrarily pick one value |
| Gateway → downstream | Outbound header contains accepted ID |
| Downstream returns different ID | Detection and clear error policy |
| Downstream timeout | Warning/error log still includes correlation ID |
| Concurrent requests | No ID mixing between two requests |
| Async task | Context propagates/cleans up as needed |
| CORS browser | Custom response header exposed only when policy permits |
| Proxy-generated error response | Observe proxy ID and correlation path |
| Retry | Attempts carry correlation ID and appropriate attempt metadata |
| External API boundary | Internal IDs not forwarded when policy forbids |

### 14.1. An end-to-end HTTP request test

In the Java 17 demo, the first test sends:

~~~text
x-correlation-id: demo-42
~~~

Then verifies:
- Response status is 200;
- Response header is demo-42;
- Body is downstream-ok;
- Both **gateway** and **downstream** log `cid=demo-42`;
- No other ID appears in logging events for this flow.

This is a real test over localhost HTTP, not just calling a function with a String.

### 14.2. Testing generation/validation

The demo's test suite calls **selectId** directly with `null`, **"bad value"**, and a two-element list to verify the new ID is a UUIDv4. For real applications, add HTTP tests that send:
- Missing header;
- Actual duplicate headers;
- Oversized header;
- Invalid characters;
- A proxy forwarding/merging headers;
- Header replacement by the gateway.

**Separate unit tests from integration tests:** unit tests verify the algorithm; integration tests verify the HTTP stack and real intermediaries.

### 14.3. Testing concurrency

Run multiple concurrent requests, each with a different ID. Verify that no log from request A carries request B's ID. If using MDC, verify cleanup on the same worker thread after request A finishes and another task begins.

### 14.4. Testing error paths

Do not test only status 200. Test errors:
- Invalid input 400;
- Unauthorized 401/403;
- Downstream timeout 502/504 per policy;
- Internal exception 500;
- Cancellation/interruption.

Any response generated by the application should follow a clear correlation ID policy; if a proxy generates a response before the application, that part is the proxy's responsibility.

## 15. Common Mistakes When Propagating Over HTTP

### Mistake 1 — Only attaching the ID to inbound logs

The gateway reads and logs the header, but the outbound HttpClient does not set the header. Downstream lacks the correlation ID, so logs cannot be linked.

**Fix:** set the header on every outbound request, ideally via a tested client interceptor or wrapper.

### Mistake 2 — Generating a new ID at every service

Each service generates a UUID even when the incoming ID is valid. Every hop ends up with a different correlation group.

**Fix:** define trust boundaries; keep the accepted ID internally and only regenerate when the contract requires it.

### Mistake 3 — Trusting every value from the Internet

The server logs the raw header value; a client sends newlines, control characters, or an oversized string.

**Fix:** validate format/length and apply untrusted-input policies before logging or forwarding.

### Mistake 4 — Picking the first value of a duplicate header

A client sends two `X-Correlation-ID` headers, and the server picks `firstValue` without a contract, creating ambiguous correlation.

**Fix:** require exactly one value; treat duplicates or comma-joined values as invalid if policy allows only a single token.

### Mistake 5 — Mismatched header names across services

Gateway sets **X-Correlation-ID**, while Payment Service reads **X-Request-ID**, causing it to generate a new ID.

**Fix:** standardize the contract, consider boundary mapping, and test hop-to-hop.

### Mistake 6 — Not echoing the ID to the client

The client encounters an error but has no ID to report to support.

**Fix:** include an appropriate response header when security/privacy policies allow; for cross-origin browsers, expose the header via CORS.

### Mistake 7 — Logging the ID in messages but losing it in async tasks

The request thread has context, but tasks running in an ExecutorService have no context or retain an old ID.

**Fix:** pass the ID explicitly or capture/restore MDC per framework; cleanup is mandatory.

### Mistake 8 — Using correlation ID as Idempotency-Key

Retries share the same ID, so the backend assumes they belong to a single transaction.

**Fix:** design separate idempotency with storage/expiration/semantics; correlation ID carries no transaction guarantee.

### Mistake 9 — Confusing it with traceparent

A service sets `X-Correlation-ID` and expects distributed tracing to show spans and parent relationships.

**Fix:** instrument proper W3C/OpenTelemetry tracing when traces are needed; keep correlation ID as supplementary metadata if useful.

### Mistake 10 — Leaking internal IDs to external services

An HTTP client automatically forwards all inbound headers, accidentally sending correlation metadata and credentials to untrusted hosts.

**Fix:** allowlist headers per trust boundary, and control redirects and outbound destinations.

### Mistake 11 — Assuming the header is present in every error response

A gateway or proxy may return 502 before the app processes the request; the app cannot attach an ID to that response.

**Fix:** define tracing/logging at the ingress/proxy layer and response policies at each boundary.

### Mistake 12 — Not verifying the logging backend

MDC has the ID, but PatternLayout does not output the field, or service logs are dropped by a collector.

**Fix:** test actual output from producer to storage; check levels/filters/schemas, sampling, and ingestion health.

## 16. Extended Exercises

### Exercise A — Missing header over HTTP

Modify `HttpRequest` in `main` so it does not set `X-Correlation-ID`. Instead of only testing `selectId(null)`, send a real request through the gateway and verify the response returns a UUIDv4 and both gateway/downstream logs have **the same UUID**. Note that the random value changes across runs; do not hardcode a specific UUID in stdout assertions.

### Exercise B — Malformed header

Send a value containing spaces if the HTTP client allows it. Verify the gateway applies the regenerate policy and downstream uses the accepted ID. For control characters, many HTTP clients reject them at the builder; test rejection at the appropriate unit layer.

### Exercise C — Duplicate headers

Try an HTTP client/proxy sending multiple field lines with the same name and observe how the server/framework surfaces the values. Do not assume it always returns a two-element `List` when a proxy might join values with a comma.

### Exercise D — Add a per-hop request ID

Keep `correlationId=demo-42` across gateway and downstream, but generate a separate **request_id** at each hop. Log both `correlation_id` and `request_id`, then try grouping by each field.

### Exercise E — Propagate to two downstreams

Add an Inventory Server. Have the gateway call Payment and Inventory in parallel. Ensure both receive the accepted ID. If using `CompletableFuture`, pass the ID via task parameters or context propagation with cleanup.

### Exercise F — Timeout

Make downstream respond slower than the request timeout. Observe the gateway warning; verify the log still carries the correlation ID even when no response is received. Think about why you should not automatically retry a POST with side effects without an idempotency contract.

### Exercise G — CORS response

Simulate a cross-origin browser calling the API. When permitted, add appropriate `Access-Control-Expose-Headers` and `Access-Control-Allow-Headers`. Verify JavaScript can read the response header without creating an unrestricted open CORS policy.

### Exercise H — W3C traceparent

Use a tracing library to create spans and propagate `traceparent`. Keep custom `X-Correlation-ID` as a secondary field. Compare `trace-id`, `span-id`, and `correlation-id` in logs without manually modifying `traceparent` via arbitrary string concatenation.

### Exercise I — Logging security

Create ID values containing newlines, commas, invalid characters, and oversized strings. Write unit tests for `selectId`. Verify raw input never appears in logs and is never forwarded.

### Exercise J — Production design

Write a checklist for a large HTTP application: ingress proxy, inbound filter, outbound client interceptor, MDC lifecycle, retries, async tasks, CORS, log collector, retention, and security boundaries. Distinguish which components generate IDs and which only preserve/forward them.

## 17. Check-Your-Understanding Questions and Answers

**1. Where is a Correlation ID typically placed when propagating over HTTP?**  
In an HTTP request header agreed upon across services, such as `X-Correlation-ID`; the response may echo the ID when policy permits.

**2. Is X-Correlation-ID a mandatory standard HTTP header?**  
No. It is a convention/custom header that requires a consistent contract.

**3. Are HTTP header names case-sensitive?**  
No. Header names are matched case-insensitively per HTTP Semantics.

**4. What should be done if the header is missing?**  
It depends on the contract: usually generate a new safe ID at the boundary, or reject if the API requires an upstream-provided ID.

**5. Why validate the header value before logging?**  
To bound size, prevent control characters/log injection, avoid ambiguous values, and protect trust boundaries.

**6. Once the gateway accepts a valid ID, which ID should downstream receive?**  
The same accepted correlation ID if end-to-end linkage is desired; separate IDs for attempts/spans are recorded in other fields.

**7. If a request has 3 retries, does it need 3 correlation IDs?**  
Usually one shared correlation ID plus attempt metadata, unless the contract specifies otherwise.

**8. Does a Correlation ID prevent duplicate payment processing?**  
No. A defined idempotency mechanism is required; do not rely on correlation ID.

**9. Does X-Correlation-ID alone create a distributed trace?**  
No. W3C Trace Context uses `traceparent`/`tracestate` along with instrumentation/span propagation.

**10. Does Java HttpClient automatically forward inbound headers when building an outbound request?**  
No. Your code or interceptor must explicitly select and set permitted headers.

**11. Why return the ID in the response?**  
It helps clients/support link failed requests to logs; only do so when privacy/security policies permit.

**12. Can browser JavaScript read any custom cross-origin response header?**  
Not by default. CORS `Access-Control-Expose-Headers` is required for permitted custom headers.

**13. Why must MDC be cleaned up in finally?**  
To prevent a reused thread from carrying the previous request's ID into another request.

**14. Why not use `static String currentCorrelationId`?**  
Because concurrent requests can overwrite it, corrupting log correlation.

**15. In the demo, where do the three stderr logs come from?**  
One `gateway.received`, one `downstream.received`, and one `gateway.completed`; all with `cid=demo-42`.

**16. Why does stdout print three `generatedUUID=true` values instead of printing the actual UUIDs?**  
Because UUIDs are randomly generated. Checking the condition keeps stdout deterministic without guessing a random ID.

**17. In Java 17, can HttpClient be used in try-with-resources?**  
No. Java 17's `HttpClient` does not implement `AutoCloseable`; manage the HTTP servers' lifecycles with `finally` as shown in the demo.

**18. Does an identical correlation ID prove two events belong to the same user?**  
No. IDs can be client-supplied, collide, or span multiple steps; authentication/security context is a separate mechanism.

## 18. Official References

- IETF RFC 9110 — HTTP Semantics, field names, and duplicated field values: https://www.rfc-editor.org/rfc/rfc9110.html
- W3C Trace Context — traceparent/tracestate: https://www.w3.org/TR/trace-context/
- Java SE 17 — HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 — HttpRequest: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- Java SE 17 — HttpHeaders: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html
- Java SE 17 — HttpServer: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Java SE 17 — UUID: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html
- SLF4J MDC API: https://www.slf4j.org/api/org/slf4j/MDC.html
- OpenTelemetry Context Propagation: https://opentelemetry.io/docs/concepts/context-propagation/

When applying these concepts, verify your Java/framework versions, API gateway policies, custom header names, and active tracing contracts. The **X-Correlation-ID** example with regex/UUIDv4 in this lesson is **an illustrative policy**, not the only HTTP standard.

## 19. Core Takeaways

**Propagating a Correlation ID over HTTP** is a cross-service contract consisting of **reading the incoming header → validation/trust decision → accepting or generating an ID → attaching to logs → forwarding to outbound requests → optionally echoing in the response → cleaning up context**.

For best results, keep header names and schemas consistent, never forward unvalidated client data, never use the ID for authorization/idempotency, do not forget async context propagation, and do not confuse a custom correlation ID with W3C `traceparent`. The executed Java 17 example demonstrates that both gateway and downstream preserve **demo-42**, the response returns the same ID, missing/invalid/duplicate cases are tested separately, and logs from both HTTP services can be queried using a single correlation key.
