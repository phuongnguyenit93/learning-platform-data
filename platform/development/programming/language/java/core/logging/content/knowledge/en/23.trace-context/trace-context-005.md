# Cross-Service Propagation in Java Core Logging

## 1. Why Propagate Trace Context Across Services?

A request often passes through multiple components: API Gateway → Service A → Service B → queue → Worker. If each component only logs a timestamp and a message, correlating log lines belonging to the same request becomes difficult, especially when many requests are processed concurrently.

**Cross-service propagation** is the process of **extracting tracing context from an incoming request, binding that context to the current execution, and passing the necessary fields to the next outbound call**. This allows logs across services to be filtered by a single end-to-end identifier.

For example, a single payment call might produce the following logs:

~~~text
api-gateway traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=route
order-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=create-order
payment-service traceId=4bf92f3577b34da6a3ce929d0e0e4736 action=authorize
~~~

All three lines belong to the same trace even though they appear in three different services. Sharing a trace ID does **not** automatically create distributed tracing: to see parent–child relationships and the duration of each operation, you need **spans** and a corresponding trace collection system.

The goal of this lesson is to understand the semantics of these identifiers, learn how to propagate context across network and execution thread boundaries, and write correlatable logs without leaking data.

## 2. Common Identifiers

| Component | Meaning | Scope and Notes |
| --- | --- | --- |
| **Correlation ID / Request ID** | Application-level ID used to group logs of a request or business workflow | Often passed via a custom header such as X-Correlation-ID; **not a span tracing standard** |
| **Trace ID** | Shared identifier for an entire distributed trace | Remains stable as it passes through services within the same trace |
| **Span ID** | Identifier of a single unit of work within a trace | Each span has its own ID; a span in a downstream service is usually different from the span in the upstream service |
| **Parent Span ID** | Links the current span to the span that created it | Forms the dependency tree between operations |
| **Trace flags** | Control bits, where the least significant bit represents the sampled flag | Do not assume that sampled=0 means there is no trace ID |
| **Baggage** | A set of attributes that can propagate across service boundaries | Only use information allowed to be propagated; never put tokens, passwords, or sensitive data here |
| **MDC (Mapped Diagnostic Context)** | Key–value store used for log formatting within a processing thread | Local to the logger; it is not automatically propagated over HTTP or message brokers |

A system can have both a traceId to link spans and a correlationId to tag a business workflow. You should not assume these two values must be equal: a correlationId can outlive a single trace, for example an order spanning multiple independent jobs.

## 3. Flow Within a Service

A common workflow when receiving an HTTP request:

1. **Extract:** read traceparent/tracestate (or a correlation ID header per internal contract), validating syntax and data limits.
2. **Establish:** restore a valid parent context, creating a new span for the current work if using a tracer; if no valid context exists, start a new context.
3. **Activate:** bind the context to the execution scope so the logger can retrieve traceId/spanId/correlationId.
4. **Log:** include the identifier fields in structured logs or MDC patterns, enabling cross-service search.
5. **Inject:** when making an HTTP/gRPC call or publishing a message, place the **current** context into the outbound call's carrier.
6. **Cleanup:** end the scope, restoring the previous context or clearing MDC/ThreadLocal in a finally block to prevent leaking data to the next request.

~~~text
Client
  |
  | traceparent / X-Correlation-ID
  v
Service A: EXTRACT -> ACTIVATE -> LOG
  |
  | INJECT into HTTP headers
  v
Service B: EXTRACT -> ACTIVATE -> LOG
  |
  | INJECT into message headers
  v
Worker:    EXTRACT -> ACTIVATE -> LOG -> CLEANUP
~~~

**Key rule:** a valid trace passing through multiple services preserves the **trace ID**, while each service can create a **new span ID**. Meanwhile, a manual correlation ID can be copied verbatim; you should not refer to that copying as automatic span creation.

## 4. The W3C Trace Context Standard

To enable interoperability across frameworks and languages, W3C defines two key HTTP headers:

- **traceparent:** contains version, trace-id, parent-id, and trace-flags.
- **tracestate:** carries vendor-specific tracing state; only propagate when appropriate for the context and standard.

Valid example of traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Structure of version 00:

~~~text
00 - 4bf92f3577b34da6a3ce929d0e0e4736 - 00f067aa0ba902b7 - 01
|                 |                         |           |
version     trace-id (16 bytes)        parent-id    flags
             32 hex digits              16 hex      2 hex
~~~

The trace ID and parent ID must not be all zeros; all fields must match the exact length and format of the supported version. A value of 01 in trace-flags has the sampled bit enabled; 00 means the sampled bit is disabled. The header sent **from A to B** represents the span acting as the parent for the next operation; when B creates a new server span, B's span ID will differ from the parent ID in the header.

Upon receiving a valid traceparent, a tracer typically **continues the trace ID** and creates a new span for the current task. When missing or invalid, the system starts a new trace according to policy. Do not manually assemble a traceparent string by modifying a few characters if your application already uses OpenTelemetry/Micrometer Tracing: let the propagator and tracer handle versioning, sampling flags, and state.

**Baggage** is a related but separate standard; it is not part of the four fields of traceparent. Certain attributes may traverse multiple systems and be observed by recipients, so you should restrict the allowlist, size, and trust boundaries.

## 5. Java 17 Example: Correlation ID Across Two HTTP Services

The example below uses only the JDK, running two HTTP servers on localhost to illustrate the mechanism of **receive → store in thread scope → attach header to the next call → log → clear scope**. This demonstrates passing a **custom X-Correlation-ID**, **not** a full W3C spans implementation.

Create a file named **CorrelationAcrossServices.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

public class CorrelationAcrossServices {
    private static final String HEADER = "X-Correlation-ID";
    private static final ThreadLocal<String> CURRENT_ID = new ThreadLocal<>();
    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static String acceptOrCreate(String candidate) {
        if (candidate != null && VALID_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }

    private static void log(String service, String event) {
        System.out.println(service + " correlationId=" + CURRENT_ID.get()
                + " | " + event);
    }

    private static void reply(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        HttpClient client = HttpClient.newHttpClient();

        HttpServer serviceB = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        serviceB.setExecutor(pool);
        serviceB.createContext("/work", exchange -> {
            CURRENT_ID.set(acceptOrCreate(
                    exchange.getRequestHeaders().getFirst(HEADER)));
            try {
                log("B", "xu ly /work");
                reply(exchange, 200, "OK");
            } finally {
                CURRENT_ID.remove();
            }
        });
        serviceB.start();
        int portB = serviceB.getAddress().getPort();

        HttpServer serviceA = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        serviceA.setExecutor(pool);
        serviceA.createContext("/start", exchange -> {
            String id = acceptOrCreate(
                    exchange.getRequestHeaders().getFirst(HEADER));
            CURRENT_ID.set(id);
            try {
                log("A", "nhan /start");

                HttpRequest downstream = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + portB + "/work"))
                        .header(HEADER, id)
                        .GET()
                        .build();

                int code;
                String body;
                try {
                    HttpResponse<String> response = client.send(
                            downstream,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
                    code = response.statusCode();
                    body = response.body();
                    log("A", "B tra " + code);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    code = 503;
                    body = "interrupted";
                    log("A", "loi: interrupted");
                } catch (IOException e) {
                    code = 502;
                    body = "bad gateway";
                    log("A", "loi khi goi B");
                }
                reply(exchange, code, body);
            } finally {
                CURRENT_ID.remove();
            }
        });
        serviceA.start();

        try {
            int portA = serviceA.getAddress().getPort();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + portA + "/start"))
                    .header(HEADER, "demo-req-42")
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("CLIENT HTTP " + response.statusCode()
                    + " body=" + response.body());
        } finally {
            serviceA.stop(0);
            serviceB.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac --add-modules jdk.httpserver CorrelationAcrossServices.java
java --add-modules jdk.httpserver CorrelationAcrossServices
~~~

Expected output when both services return HTTP 200:

~~~text
A correlationId=demo-req-42 | nhan /start
B correlationId=demo-req-42 | xu ly /work
A correlationId=demo-req-42 | B tra 200
CLIENT HTTP 200 body=OK
~~~

Explanation:

- **Client** sets the X-Correlation-ID header to demo-req-42.
- **A** receives and validates the header, stores the ID in the ThreadLocal of A's serving thread, and attaches that same ID to the HTTP request sent to B.
- **B** extracts the incoming header and binds it to the ThreadLocal of B's serving thread; thus both services share the same correlationId in their logs.
- At the end of each handler, finally calls CURRENT_ID.remove(). Because thread pools reuse threads, cleaning up the context is mandatory.
- If the header is missing or fails the validation regex, the service generates a UUID. This is a simplified example to illustrate propagation; production systems also need policies for validating/normalizing ID sources, header sizes, multi-value handling, and error rates.

**Common pitfall:** ThreadLocal in A does **not** travel across the network to B. It is the **HTTP header** value that bridges them. If you omit .header(HEADER, id) on the A → B request, B will generate a new ID and the log chain will be broken.

This synchronous example uses a blocking HttpClient for clarity; asynchronous HTTP clients or servers require context propagation mechanisms suited to their executors, callbacks, or frameworks.

## 6. Integrating Context with Loggers and MDC

In Java applications using SLF4J/Logback, you should put correlationId or traceId into **MDC** and configure a pattern or JSON encoder to include that field in every log line. The code below **requires the SLF4J library** and is an integration snippet, not a standalone JDK program:

~~~java
import org.slf4j.MDC;

void handleRequest(String correlationId) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
        // Logs within this scope can read MDC["correlationId"].
        processRequest();
    }
}
~~~

Example of a Logback pattern fragment:

~~~text
%d{ISO8601} %-5level trace=%X{traceId} correlation=%X{correlationId} %logger - %msg%n
~~~

Field names in MDC must match the configuration of your tracing library and encoder. If you use Micrometer Tracing or OpenTelemetry with built-in log correlation, check their specific configuration to avoid manually overwriting traceId/spanId already managed by the framework.

When handling errors, **log the exception with its stack trace** while keeping the active context intact; there is no need to duplicate the entire request/response payload just to locate a trace. For multi-service systems, JSON-formatted logs with consistent keys such as timestamp, service, level, traceId, spanId, correlationId, and message enable reliable querying.

## 7. When Work Switches Threads: Executor, CompletableFuture, Reactive

MDC is typically backed by ThreadLocal. A task that switches to another thread via Executor, CompletableFuture, callbacks, or message listeners **does not automatically inherit** the current context. Preserving fields in HTTP headers is necessary but not sufficient for asynchronous tasks running *inside* a service.

For the ThreadLocal example above, the minimal approach for a task submitted to an Executor is **capture before submit, activate inside the task, restore when done**:

~~~java
String capturedId = CURRENT_ID.get();
executor.execute(() -> {
    String previousId = CURRENT_ID.get();
    try {
        if (capturedId == null) {
            CURRENT_ID.remove();
        } else {
            CURRENT_ID.set(capturedId);
        }
        doWork();
    } finally {
        if (previousId == null) {
            CURRENT_ID.remove();
        } else {
            CURRENT_ID.set(previousId);
        }
    }
});
~~~

This snippet illustrates propagating an application-managed ThreadLocal; it does **not** copy the full OpenTelemetry Context or MDC map. In production applications, prefer context propagation provided by your tracing SDK/framework or task decorators to carry the right fields and manage scopes properly. Do not use InheritableThreadLocal as a general solution for thread pools because worker threads are long-lived and reused.

With **Spring WebFlux/Reactor**, processing pipelines can switch threads between operators: do not rely solely on manual ThreadLocal propagation. Use Reactor Context and the context propagation integration appropriate for your deployed Reactor/Micrometer/OpenTelemetry versions.

## 8. Across HTTP, gRPC, and Queues

| Boundary | Where to Propagate | What the Receiver Must Do |
| --- | --- | --- |
| HTTP REST | traceparent, tracestate headers; or X-Correlation-ID if using an internal contract | Extract/validate, create appropriate scope/span, log, and inject into downstream calls |
| gRPC | Request metadata | Use a compatible propagator/interceptor to propagate context along calls |
| Kafka/RabbitMQ | Message headers/properties | Producer injects on publish; consumer extracts for **each message**, processes, then closes scope |
| Scheduled job | Job metadata or explicitly stored workflow identifier | Create a new trace if no parent exists; explicitly record the relationship with the job/correlation ID |
| Retry or DLQ routing | Processing attempt metadata and retry information | Preserve necessary business identifiers; create a new processing span to avoid mixing logs across attempts |

For example, with a message broker: if Service A publishes an order-created event, inject the context into the message **headers**, rather than assuming the JSON body itself carries trace context. When a worker consumes multiple messages sequentially on the same thread, close the context of the previous message before processing the next one. For delayed processing or long-lived asynchronous events, you can use **span links** to express causal relationships instead of forcing every task to be a direct child; choosing between a parent or a link depends on your tracing model and business contract.

## 9. Trust Boundaries, Security, and Operations

1. **Never treat inbound traceId/correlationId as proof of identity.** Clients can send arbitrary headers. Authentication and authorization must always remain independent of tracing.
2. **Validate structure and enforce length limits** on self-managed IDs; never log raw arbitrary headers directly, as this risks log injection, storage bloat, and skewed search results.
3. **Never pass sensitive data through baggage or logs.** Tokens, passwords, card details, personal data, and unfiltered request bodies do not belong in trace context.
4. **Enforce policies at trust boundaries.** Gateways can strip or reinitialize context from untrusted sources according to policy, and allow only an approved set of baggage keys to pass through.
5. **Preserve error boundaries.** Timeouts, cancellations, or retries must close the old scope properly; never let MDC from a previous request linger on a subsequent worker task.
6. **Do not confuse sampling with log correlation.** The sampled flag controls trace sampling decisions; actual log correlation and span storage also depend on SDK configuration, exporters, and the log pipeline.
7. **Ensure consistent field names.** If A logs trace_id while B logs traceId, normalize them in the logger or collector so a single query finds both.
8. **Monitor overhead.** Avoid putting high-cardinality attributes or large payloads into metric labels; trace IDs belong in logs and traces, not in aggregated metric labels.

## 10. Common Pitfalls and How to Spot Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Logs in A have the ID, logs in B are missing it | Client A did not inject the header or B did not extract it | Inspect HTTP/message interceptors on both sides and compare sample headers |
| Each service has a different traceId | Starting a new root trace at every hop or dropping parent context | Restore incoming context before starting a new span |
| Two different requests share the same MDC | Failing to clear/restore ThreadLocal in a thread pool | Close the scope in finally / try-with-resources |
| Logs inside CompletableFuture lose the ID | Task runs on a different executor thread | Capture/activate/restore using a supported propagation mechanism |
| TraceId is present but there is no span tree | Only copying a correlation ID or tracer/exporter is not configured | Distinguish log correlation from distributed tracing and verify instrumentations |
| Trace breaks when passing through a broker | Producer does not inject or consumer does not extract message headers | Instrument producer/consumer separately and verify each message |
| Log queries return unexpected data | Trusting arbitrary headers or inconsistent field naming | Validate inputs, enforce trust policies, and standardize log structure |

## 11. How to Test Propagation

An effective test suite should cover:

- **Happy path:** send a valid ID from the client, call A → B → worker; verify that all logs for the request share the same correlationId/traceId and that trace span IDs have valid relationships if using a tracer.
- **Missing or malformed headers:** verify that the system creates a new context without breaking the request; test boundary policies for untrusted sources.
- **Concurrency:** run multiple requests in parallel with different IDs; check for logs with mixed-up IDs across threads.
- **Async/retry/timeout:** switch executors, trigger retries, and cancel requests; verify that context binds to the right attempt and is cleaned up afterward.
- **Messaging:** test producer/consumer flows, multi-message batches, and DLQ paths; never assume thread-local state remains valid from a previous message.
- **Observability:** take a trace ID from a log and query it in the downstream service; if a tracing backend is available, inspect the span tree and log–trace correlation.

**Key takeaway:** context only crosses service boundaries when it is **serialized/injected into the protocol** and **extracted/activated** on the receiving end. MDC or ThreadLocal only binds IDs within the local execution scope. For full distributed tracing, you need a proper tracer/propagator alongside log correlation.