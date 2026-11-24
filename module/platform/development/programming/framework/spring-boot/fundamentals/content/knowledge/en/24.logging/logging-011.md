# Sensitive Data, Request Context, and What Should Be Logged

Logging helps answer critical questions when operating a Spring Boot application: which request failed, which component processed it, at which step the failure began, how long it took, and which conditions caused the system to misbehave. However, logs can also become an information leak if an application records raw HTTP headers, request bodies, access tokens, passwords, customer data, or exceptions containing secrets.

A good logging system must balance three goals:

1. **Having enough diagnostic context** without needing to reproduce every failure in production.
2. **Minimizing sensitive data stored** in logs and centralized logging platforms.
3. **Correlating log lines belonging to the same request or workflow** without logging the entire payload of that request.

In Spring Boot, common tools include SLF4J/Logback, `Logger`, MDC (*Mapped Diagnostic Context*), request/correlation IDs, distributed tracing, and structured log collection systems. This lesson moves from data selection principles to Java examples, HTTP filters, async execution, exception logging, and practicing safe log policy design.

> Guiding principle: **log events, states, outcome codes, and necessary correlation identifiers; never use logs as a copy of requests, responses, or business data.**

## 1. Logs are operational data, not a warehouse for everything

Consider this request:

```text
POST /api/orders
Authorization: Bearer <access-token>
Cookie: SESSION=<session-id>
Content-Type: application/json

{
  "customerEmail": "alice@example.test",
  "deliveryAddress": "123 Example Street",
  "cardNumber": "<payment-card-data>",
  "items": [
    {"sku": "SKU-101", "quantity": 2}
  ]
}
```

To investigate why order creation failed, an engineer usually only needs to know:

```text
event=order.create.failed
requestId=7d2c9e64-...
route=/api/orders
method=POST
status=503
orderRef=ord_83f1
failureCode=INVENTORY_UNAVAILABLE
durationMs=217
```

That information locates the exact request, the failing step, and processing duration. It does not need access tokens, cookies, delivery addresses, card numbers, or the entire payload.

### 1.1. Why do sensitive logs pose risks?

A single log line can travel through many places:

```text
Spring Boot service
       |
       v
Console / log file
       |
       v
Log agent / collector
       |
       v
Centralized logging platform
       |
       +--> Dashboard / search
       +--> Alert
       +--> Export / backup
       +--> Incident attachment
```

Who can view logs may differ from who has access to business data. Logs are frequently copied, retained longer, and searched more broadly than database rows. A secret that lands in logs is very hard to revoke once it has propagated across multiple systems.

Therefore, log design must start from **deciding what data is permitted to be logged**, not merely picking a `log.info(...)` call.

## 2. Classify data before logging

Data can be categorized by purpose and risk level.

| Category | Examples | Principle |
| --- | --- | --- |
| Operational info | Event name, error code, status code, duration, service name | Usually should log |
| Correlation context | Request ID, trace ID, span ID, operation ID | Log under control; not secret, yet avoid misuse |
| Internal identifiers | Order reference, job ID, account reference | Log only when needed; prefer IDs without direct identifying data |
| Personal data | Email, phone number, name, IP, address, device | Restrict; log only when purpose truly requires it |
| Sensitive business data | Exact amounts, records, transaction details, health data | Avoid logging raw values; requires dedicated evaluation |
| Authentication credentials | Passwords, access tokens, refresh tokens, API keys, session cookies, OTPs | Never log values |
| System keys & secrets | Private keys, environment secrets, connection strings with passwords | Never log values |
| Payment data | Card numbers, security codes, sensitive payment details | Never log raw data |

Exact classification depends on product, internal policy, and applicable regulations. The table above is a starting point for a safe logging policy in Spring Boot applications.

### 2.1. Personal data is not just names and emails

The following values can identify or link back to an individual in certain contexts:

- IP addresses and device addresses.
- Account IDs or customer IDs if linkable to user profiles.
- URL paths containing personal identifiers.
- User-Agent when combined with other data.
- Trace IDs or request IDs if linkable to user records.
- Text typed by users into search boxes.

Thus, "do not log passwords" is necessary, yet insufficient. You must also evaluate **indirect identifiers and data-linking risks**.

### 2.2. Rule against logging secrets

Do not log:

```java
log.info("Login password: {}", password);
log.debug("Authorization: {}", authorizationHeader);
log.info("Session cookie: {}", sessionCookie);
log.error("API key used: {}", apiKey);
```

Replace with structured events:

```java
log.info(
        "auth.login.succeeded authMethod={} requestId={}",
        authMethod,
        requestId
);
```

```java
log.warn(
        "auth.login.failed failureCode={} requestId={}",
        "INVALID_CREDENTIALS",
        requestId
);
```

When needing to know why login failed, use a **standardized reason code** rather than logging user-entered values.

### 2.3. Do not assume partially masked data is always harmless

For example:

```text
email=a***@example.test
phone=***1234
```

contains less data than the full value, yet can still be personal data or allow inference when combined with other sources.

If there is no need to correlate emails or phone numbers, it is best **not to log even masked values**.

## 3. Select log data based on operational questions

A useful log line should help answer at least one question:

- Which action just occurred?
- Which component executed it?
- Did it succeed or fail?
- What is the operationally meaningful error code?
- Which request/job/trace does the failure belong to?
- Which external dependency had trouble?
- How long did processing take?
- Is a specific corrective action needed?

If a field helps answer none of these questions, consider omitting it.

### 3.1. Fields to consider

| Field | Example | Value |
| --- | --- | --- |
| `timestamp` | Time in UTC | Determines sequence |
| `level` | INFO, WARN, ERROR | Severity |
| `service` | `order-api` | Application name |
| `environment` | `staging` | Runtime environment |
| `event` | `order.submit.failed` | Stable event type |
| `requestId` | Server-issued UUID | Correlates logs of one request |
| `traceId`, `spanId` | IDs from tracing system | Correlates across services |
| `route` | `/api/orders/{id}` | Route template, avoiding dynamic path values |
| `method` | POST | HTTP method |
| `status` | 503 | HTTP outcome |
| `durationMs` | 217 | Processing duration |
| `failureCode` | `DEPENDENCY_TIMEOUT` | Error grouping |
| `dependency` | `inventory-service` | Affected dependency |
| `operationRef` | Internal operation ID | Task cross-reference |

Not every log line must contain every field. Log only what is meaningful for that event.

### 3.2. Use stable error codes instead of free-form prose

Less useful:

```text
Unable to finish because Alice ordered product X and ...
```

More useful:

```text
event=order.submit.failed
failureCode=INVENTORY_TIMEOUT
dependency=inventory-service
durationMs=800
```

Stable error codes facilitate searching, aggregation, and alerting. Never embed emails, account numbers, or payloads inside error codes.

### 3.3. Do not turn logs into unbounded metric labels

Values like request ID, order ID, or customer ID have very high cardinality. They are valuable for **searching logs**, yet placing them directly into metric labels can cause cardinality explosions.

Example suitable metric label:

```text
http.requests{route="/api/orders/{id}",status="503"}
```

Instead of:

```text
http.requests{path="/api/orders/ord_83f1",requestId="..."}
```

Logs, metrics, and traces serve distinct roles. Do not force every piece of information into every system.

## 4. Which log level is appropriate?

Spring Boot typically uses SLF4J with a logging implementation such as Logback. Common log levels:

| Level | Practical meaning | Example |
| --- | --- | --- |
| TRACE | Very low-level detail for specialized investigation | Non-sensitive internal steps |
| DEBUG | Diagnostic information for developers | Processing steps or config choices |
| INFO | Notable normal operational events | Application startup, job completion |
| WARN | Abnormal yet recoverable condition | Dependency timeout retried successfully |
| ERROR | Failure needing attention or preventing completion | Failed data write, unavailable dependency |

### 4.1. Do not log every request at ERROR

An HTTP `400` caused by invalid client input is not automatically a system failure. It may warrant INFO or DEBUG with a safe failure code, or simply aggregated metrics.

An unexpected HTTP `500` usually warrants ERROR with controlled exception details.

Avoid rigid rules such as:

```text
4xx = WARN for every request
5xx = ERROR for every request
```

Evaluate the nature of the failure, frequency, and how the system handles it.

### 4.2. Use WARN for handled/recovered errors

For instance, calling a partner service times out on the first attempt yet succeeds on retry:

```java
log.warn(
        "partner.request.retry dependency={} attempt={} reasonCode={}",
        "pricing-service",
        1,
        "TIMEOUT"
);
```

When it ultimately succeeds, do not emit a burst of ERRORs that mislead operators into thinking the entire operation failed.

### 4.3. Avoid duplicate exception logs

An exception can pass through repository, service, controller, and `@ControllerAdvice`.

If every layer calls `log.error(..., exception)`, logs fill with multiple identical stack traces for one failure.

Usually designate **one boundary responsible for logging full failure details**, while other layers enrich context with failure codes or rethrow as appropriate.

## 5. Writing logs with SLF4J in Spring Boot

Do not use `System.out.println(...)` as the main operational logging mechanism. It lacks log levels, standard metadata, and centralized configurability comparable to a logging framework.

Example:

```java
package com.example.orders.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String operationRef) {
        log.info(
                "order.submit.started operationRef={}",
                operationRef
        );

        // Order processing

        log.info(
                "order.submit.completed operationRef={}",
                operationRef
        );
    }
}
```

The example assumes `operationRef` is an internal reference designed to appear in logs, containing no email or secrets.

### 5.1. Use placeholders instead of string concatenation

Prefer:

```java
log.debug(
        "inventory.lookup.completed itemCount={} durationMs={}",
        itemCount,
        elapsedMs
);
```

Avoid:

```java
log.debug(
        "inventory.lookup.completed itemCount=" + itemCount +
        " durationMs=" + elapsedMs
);
```

SLF4J supports parameterized messages so formatting can be deferred when the corresponding log level is off. Still, passed objects must be chosen safely: placeholders **do not strip sensitive data automatically**.

### 5.2. Do not carelessly invoke `toString()` on data-carrying objects

Risk:

```java
log.debug("CreateOrderRequest: {}", request);
```

If `CreateOrderRequest.toString()` or `record.toString()` includes names, addresses, emails, tokens, or card numbers, those values can enter logs.

Replace with:

```java
log.debug(
        "order.create.validated itemCount={} paymentType={}",
        request.items().size(),
        paymentTypeCode
);
```

`paymentTypeCode` should be a controlled set of values like `CARD`, `BANK_TRANSFER`, `WALLET`, not account numbers or card details.

## 6. Why shouldn't raw HTTP requests and responses be logged?

HTTP requests can contain:

- `Authorization` or `Proxy-Authorization` headers.
- `Cookie`, session IDs, and anti-CSRF tokens.
- Query parameters containing password-reset tokens or invite codes.
- Path parameters containing emails, phone numbers, or account numbers.
- Request bodies containing personal details, addresses, documents, or chat content.
- Multipart uploads and user files.

Responses can also contain:

- New session cookies in `Set-Cookie`.
- Access tokens, refresh tokens.
- Personal profile lookup results.
- Business data not meant for log viewers.

Therefore, the following are unsuitable for production:

```java
log.info("Headers: {}", request.getHeaderNames());
log.info("Query string: {}", request.getQueryString());
log.info("Authorization: {}", request.getHeader("Authorization"));
log.debug("Body: {}", rawRequestBody);
log.debug("Response: {}", rawResponseBody);
```

Even when header names themselves hold no secret values, dumping all headers encourages future changes that log dangerous data. Design a **field allowlist** instead of dumping by default.

### 6.1. URLs can contain personal data

Do not log raw URLs like:

```text
/api/users/alice@example.test/orders?reset_token=...
```

Log the route template instead:

```text
/api/users/{userId}/orders
```

along with status code, duration, and correlation ID.

**Route template** differs from **request URI**:

| Value | Example | Risk |
| --- | --- | --- |
| Actual request URI | `/api/users/alice@example.test/orders` | Contains dynamic data |
| Route template | `/api/users/{userId}/orders` | More stable, leaks far less data |

### 6.2. Request body logging is not a good default

Sometimes developers turn on body logging to debug serialization. Yet a body can be huge, contain secrets, or carry data governed by strict retention rules.

If you truly must record certain body details, extract only **approved fields** for a defined purpose. Example:

```text
event=upload.validated
fileCount=3
declaredContentType=application/pdf
```

Never log file contents, multipart bytes, or raw JSON simply to "debug easily".

### 6.3. Be cautious with `ContentCachingRequestWrapper`

Spring Web offers wrappers that cache request/response contents so they can be read again during processing. Having a wrapper **does not mean the content is safe to write into logs**.

Beyond privacy, body caching increases memory consumption and has size limits. If you enable request/response body logging for debugging, bound the scope, size, duration, and permitted fields; keep it off in production unless under dedicated controlled requirements.

## 7. What is request context?

An HTTP request typically traverses multiple layers:

```text
API Gateway
     |
     v
Spring MVC Filter
     |
     v
Controller
     |
     v
OrderService
     |
     v
Repository / HTTP client
     |
     v
Dependency
```

If each layer writes a few log lines, you need a way to link them. **Request context** is the set of metadata serving that correlation, not a full copy of the request.

Common fields to consider:

```text
requestId
traceId
spanId
route
operation
service
environment
```

Depending on the system, `tenantRef`, `jobRef`, or minimized user references may be added, with strict control over purpose and scope.

### 7.1. Correlation ID and request ID

A `requestId` is an identifier attached to a single request. Example:

```text
requestId=7d2c9e64-8d74-46f1-9d2d-50c6d049e84e
```

Logs within the same request can carry this value:

```text
INFO  requestId=7d2c9e64... event=http.request.received route=/api/orders
INFO  requestId=7d2c9e64... event=order.validated itemCount=2
WARN  requestId=7d2c9e64... event=inventory.retry attempt=1
INFO  requestId=7d2c9e64... event=http.request.completed status=201 durationMs=173
```

In multi-service systems, correlation can use IDs created by tracing. Do not invent multiple conflicting request IDs if a reliable tracing mechanism already exists.

### 7.2. IDs are not proof of authentication

If a client sends the header:

```text
X-Request-ID: some-value
```

that value is still **untrusted input**. Never treat a request ID as proof that a user is logged in, authorized, or part of a valid transaction.

A request ID should serve only correlation and search support.

## 8. MDC: bringing context into logs on the same thread

SLF4J provides `MDC` (*Mapped Diagnostic Context*) to store key–value pairs bound to the logging execution context.

Example:

```java
import org.slf4j.MDC;

MDC.put("requestId", "7d2c9e64-...");

try {
    log.info("order.validation.started");
} finally {
    MDC.remove("requestId");
}
```

If the logging pattern or JSON encoder is configured to emit MDC, logs written inside this block can include `requestId`.

### 8.1. MDC does not automatically modify every log line

Simply calling:

```java
MDC.put("requestId", requestId);
```

is not enough to guarantee the value is printed. You must also configure logging output to read MDC, or use an encoder supporting MDC fields.

Example Logback pattern:

```properties
logging.pattern.level=%5p [requestId:%X{requestId:-}]
```

This illustrates customizing the level pattern using Spring Boot's logging mechanism with Logback. Placeholder syntax can depend on logging system/version; when deploying, verify actual log output.

### 8.2. Why must MDC be cleared?

In servlet applications, threads in a thread pool are **reused** across different requests.

If request A sets:

```text
requestId=A
```

and fails to clear it, request B handled on the same thread may accidentally carry A's ID.

Consequences:

- Logs from two requests get mixed together.
- Error investigation becomes misleading.
- Metadata from a prior request can leak into a later request's logs.

Therefore, any code populating MDC must use `try/finally` or an equivalent cleanup mechanism.

### 8.3. Put only permitted fields into MDC

Avoid:

```java
MDC.put("email", customerEmail);
MDC.put("authorization", bearerToken);
MDC.put("requestBody", rawJson);
```

MDC is typically emitted automatically on many log statements. Putting a sensitive field into MDC can spread it across **every log line** in that flow.

A well-generated and controlled request ID is far more appropriate than emails or session tokens.

## 9. Full example: generating a request ID in a Servlet filter

In Spring Boot 3.x with Spring MVC/Servlet and Jakarta Servlet API, you can build a `OncePerRequestFilter`.

Goals:

1. Generate a request ID containing no user data.
2. Put the ID into MDC so services can emit correlated logs.
3. Return the ID to the client to assist support tickets.
4. Log a safe HTTP request summary.
5. Remove the ID from MDC upon completion.

```java
package com.example.orders.logging;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        long startedAt = System.nanoTime();

        MDC.put("requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            chain.doFilter(request, response);
        } finally {
            Object pattern = request.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
            );

            String route =
                    pattern instanceof String
                            ? (String) pattern
                            : "unmatched";

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt
            );

            log.info(
                    "http.request.completed method={} route={} status={} durationMs={}",
                    request.getMethod(),
                    route,
                    response.getStatus(),
                    durationMs
            );

            MDC.remove("requestId");
        }
    }
}
```

This example intentionally **does not log** `getRequestURI()`, query strings, headers, bodies, cookies, or user identities.

### 9.1. Why use a server-generated UUID?

The code above **does not trust a request ID sent by the client**. A server-generated UUID prevents clients from injecting strings with newlines, personal info, or noise into logs.

If your system already has a trusted gateway generating correlation IDs, you can accept that ID under a well-defined contract, provided you validate source, format, length limits, and propagation rules.

Do not blindly take:

```java
String id = request.getHeader("X-Request-ID");
MDC.put("requestId", id);
```

assuming the ID is always safe.

### 9.2. Why log the route template instead of the actual URL?

Spring MVC can store the matched handler pattern in a request attribute:

```java
HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
```

For example, route `/api/orders/{orderId}` is stable and reveals less data than URI `/api/orders/abc123`.

When there is no MVC mapping (e.g., requests rejected before reaching a handler), the example uses a fixed value `unmatched` rather than logging the user-submitted path.

### 9.3. Notes on exceptions and asynchronous Servlet processing

This is an introductory example, not a full-featured access-log framework:

- An exception unhandled by the web container can make the status read in the filter differ from the final status after error dispatch.
- Servlet async processing can return control from the filter before the response actually finishes.
- Error dispatches, filter ordering, and nested dispatches can complicate logging **one exact final completion record**.

For systems using async Servlet, streaming, or needing exact response completion timing, add an `AsyncListener`, Spring MVC interceptor, or appropriate instrumentation layer. Do not treat filter `finally` as absolute proof that the client received the complete response.

### 9.4. What if MDC already contains `requestId`?

The simple example always overwrites and removes one key. In systems with multiple filter layers or frameworks managing MDC, one filter could accidentally overwrite a value set by other infrastructure.

When integrating, assign a single component as owner of the request ID. If you must temporarily override an existing value, save the previous value and restore it in `finally` rather than removing blindly:

```java
String previous = MDC.get("requestId");
MDC.put("requestId", requestId);

try {
    // Process
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

## 10. Trace ID and span ID in multi-service systems

A request ID created inside a single service helps local log searches. When a request traverses multiple services, you need to correlate steps across different processes:

```text
Client
  |
  v
Gateway                traceId = T, spanId = S1
  |
  v
Order Service          traceId = T, spanId = S2
  |
  +------> Inventory Service  traceId = T, spanId = S3
  |
  +------> Payment Service    traceId = T, spanId = S4
```

In distributed tracing:

- **Trace ID** identifies the entire trace of a processing flow.
- **Span ID** identifies a specific span within that trace.
- **Parent span** expresses relationships across call steps.

When tracing infrastructure is properly integrated, logs across services can carry trace/span IDs for cross-system diagnostics without logging request bodies.

### 10.1. Micrometer Tracing and Spring Boot

Many modern Spring Boot release lines integrate observability through Micrometer and can use Micrometer Tracing with OpenTelemetry or Brave bridges depending on dependencies and versions.

When tracing is enabled and logging is configured properly, trace/span context can appear in log patterns or structured logging fields.

**Do not invent an independent set of request ID, trace ID, and span ID without design.** First check which IDs your observability infrastructure already generates and propagates.

### 10.2. How is trace context propagated?

Tracing systems typically use propagation headers conforming to appropriate standards, such as W3C Trace Context:

```text
traceparent: ...
```

Tracing instrumentation handles creating, extracting, and forwarding context across HTTP clients, servers, and messaging integrations.

Adding your own `X-Request-ID` header does not automatically turn it into a distributed trace. Design explicit propagation or use tracing infrastructure.

### 10.3. Trace IDs are not secrets either

Trace IDs are useful for correlation, yet **must not be used to prove access permissions**. Someone knowing a trace ID must not automatically be allowed to view sensitive trace data without authorization.

Also, a trace spanning multiple services can reflect user behavior, so viewing and storing trace data still requires access control, retention, and appropriate policies.

## 11. MDC and asynchronous processing

A common pitfall: MDC is bound to the logging implementation's thread context. When handing work off to another executor, context **does not automatically propagate to the new thread by default**.

Example:

```java
MDC.put("requestId", requestId);

executor.execute(() -> {
    log.info("background.task.started");
});
```

Logs from the background thread may lack `requestId`.

This breaks correlation across steps and can even cause confusion if a pooled thread still holds stale MDC left by uncleaned code.

### 11.1. Controlled MDC propagation with TaskDecorator

Example Spring `ThreadPoolTaskExecutor`:

```java
package com.example.orders.logging;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class LoggingExecutorConfiguration {

    @Bean("contextAwareExecutor")
    public ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("order-worker-");

        executor.setTaskDecorator(task -> {
            Map<String, String> captured =
                    MDC.getCopyOfContextMap();

            return () -> {
                Map<String, String> previous =
                        MDC.getCopyOfContextMap();

                try {
                    if (captured == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(captured);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        MDC.clear();
                    } else {
                        MDC.setContextMap(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

`TaskDecorator` captures a copy of MDC when the task is decorated, installs it on the executing thread, and restores the prior context when the task finishes.

### 11.2. Using with `@Async`

When enabling async method execution:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

A service can select the executor:

```java
@Service
public class ReceiptService {

    private static final Logger log =
            LoggerFactory.getLogger(ReceiptService.class);

    @Async("contextAwareExecutor")
    public CompletableFuture<Void> sendReceipt(String operationRef) {
        log.info(
                "receipt.send.started operationRef={}",
                operationRef
        );

        // Work to send receipt

        return CompletableFuture.completedFuture(null);
    }
}
```

The example assumes the method is invoked externally through the async proxy—not via self-invocation—and the executor is configured as above.

### 11.3. Propagate only permitted fields

Copying the entire MDC to background threads can also copy sensitive data if someone previously put it into MDC. Thus, the most important defense is **never placing secrets or unnecessary PII into MDC in the first place**.

Systems with strict protection requirements may propagate only allowlisted fields, such as `traceId`, `spanId`, or `requestId`, instead of copying every key–value pair.

### 11.4. When a task outlives the request

A background task may run for minutes after the HTTP request finishes. Request ID can remain a useful correlation reference, yet the task should have its own **dedicated job ID** to track its lifecycle:

```text
requestId=R1 jobId=J45 event=job.created
jobId=J45 event=job.started
jobId=J45 event=job.completed
```

Do not retain full user information in background tasks merely to keep logging it. Pass minimal context and data actually needed for business processing, with separate authorization and lifecycle.

## 12. WebFlux and Reactor Context

In Spring WebFlux or reactive systems, a single request can hop across many threads with no fixed thread boundary. Do not rely on Servlet-style thread-local MDC as the default solution for an entire reactive pipeline.

Reactor provides **Reactor Context** to carry data along a reactive subscription; modern tracing stacks can integrate context propagation mechanisms.

Illustrative example:

```java
Mono<String> operation =
        Mono.deferContextual(contextView -> {
            String requestId = contextView.get("requestId");
            return Mono.just("request=" + requestId);
        });

return operation.contextWrite(
        context -> context.put("requestId", requestId)
);
```

This illustrates carrying context inside Reactor. To make `requestId` appear automatically in logs, you still need a bridge connecting Reactor Context to the logging context or appropriate tracing instrumentation.

Do not simply call `MDC.put(...)` at the start of a reactive chain expecting every operator and asynchronous boundary to preserve that value.

## 13. How to log exceptions so they are both useful and safe?

An exception carries:

- Error type.
- Message.
- Cause chain.
- Stack trace.
- Sometimes request data, SQL, endpoints, or sensitive values placed into the message by a library.

For production debugging, stack traces can be very helpful. Yet do not log every exception at every layer.

### 13.1. Example using a failure code

```java
try {
    inventoryClient.reserve(operationRef);
} catch (InventoryTimeoutException ex) {
    log.warn(
            "inventory.reserve.retryable_failure operationRef={} failureCode={}",
            operationRef,
            "INVENTORY_TIMEOUT"
    );
    throw ex;
}
```

If a higher layer is responsible for logging the stack trace once, this layer can log only the failure code—or nothing—and let the exception propagate.

### 13.2. Log stack traces at an appropriate boundary

Example at an error handling boundary:

```java
log.error(
        "order.submit.failed operationRef={} failureCode={}",
        operationRef,
        "UNEXPECTED_FAILURE",
        exception
);
```

The final argument is the exception so the logging framework can record the stack trace.

**Important note:** stack traces and exception messages are not automatically safe. An HTTP or database library may embed request values, SQL parameters, or URLs containing secrets into exceptions. For errors carrying such risks, apply sanitization policies or log error codes/stacks only in appropriately access-controlled channels.

### 13.3. Do not log exceptions via full-request `toString()`

Avoid:

```java
log.error(
        "Failed request={} error={}",
        createOrderRequest,
        exception.getMessage()
);
```

`createOrderRequest` can contain personal data, and `exception.getMessage()` can contain uncontrolled data.

Better:

```java
log.error(
        "order.create.failed operationRef={} failureCode={}",
        operationRef,
        "PERSISTENCE_FAILURE"
);
```

When a stack trace is needed, use a controlled internal logging path after evaluating what data may appear in the cause chain.

## 14. Error handling example in Spring MVC

A `@RestControllerAdvice` can standardize HTTP responses and log errors at the API boundary.

```java
package com.example.orders.web;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InvalidOrderException.class)
    public ResponseEntity<ApiError> invalidOrder(
            InvalidOrderException ex) {

        log.info(
                "order.request.rejected failureCode={} requestId={}",
                "INVALID_ORDER",
                MDC.get("requestId")
        );

        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INVALID_ORDER",
                        MDC.get("requestId")
                )
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(Exception ex) {

        log.error(
                "http.request.unexpected_failure failureCode={} requestId={}",
                "INTERNAL_ERROR",
                MDC.get("requestId")
        );

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(
                        new ApiError(
                                "INTERNAL_ERROR",
                                MDC.get("requestId")
                        )
                );
    }

    public record ApiError(String code, String requestId) {
    }
}
```

The example assumes `InvalidOrderException` is an application-defined business class. The handler intentionally omits `ex.getMessage()` from the response and returns no stack trace to clients.

### 14.1. When should the stack trace be logged?

If `unexpected(...)` is the sole place logging unexpected errors, consider passing the exception as the final argument for internal logs **after verifying the exception chain contains no disallowed secrets**.

Do not treat stack traces as an immutable default for every exception type. For client validation errors, an error code usually suffices.

### 14.2. Logs and responses have different audiences

Clients usually need:

```json
{
  "code": "INTERNAL_ERROR",
  "requestId": "7d2c9e64-..."
}
```

Operators also need info about the dependency and failing step. However, **neither side needs passwords, tokens, or raw request contents just to see an error code**.

## 15. Structured logging: structured data

Traditional logs are usually a single line of text:

```text
INFO order.submit.completed operationRef=ord_83f1 durationMs=217
```

Structured logging represents logs as records with explicit fields. An illustrative JSON example:

```json
{
  "timestamp": "2026-01-01T09:30:15Z",
  "level": "INFO",
  "service": "order-api",
  "event": "order.submit.completed",
  "requestId": "7d2c9e64-...",
  "route": "/api/orders",
  "status": 201,
  "durationMs": 217
}
```

This is mock data illustrating structure, not a mandatory Spring Boot schema.

### 15.1. Benefits of structured logging

- Easy filtering by `event`, `status`, or `requestId`.
- Easy to build dashboards and alerts.
- Avoids fragile regex parsing on text.
- More consistent cross-service querying with field naming conventions.
- Easier to enforce field control policies at the encoder/collector layer.

### 15.2. Structured does not mean safe

JSON can also leak data:

```json
{
  "event": "auth.login",
  "authorization": "<secret>",
  "password": "<secret>"
}
```

Switching from plain text to JSON does not automatically erase sensitive content. **Field allowlisting and data minimization principles still matter most**.

### 15.3. Support in modern Spring Boot

Recent Spring Boot versions include built-in structured logging support, with lines from Spring Boot 3.4 onward supporting properties such as:

```properties
logging.structured.format.console=ecs
```

or other supported format choices depending on version. Older Spring Boot lines can use Logback encoders and custom configuration.

Check the documentation of your project's version before using a specific property. This lesson does not depend on choosing ECS, Logstash JSON, or a custom format: **which fields enter logs and how they are protected is a shared responsibility**.

### 15.4. Designing a controlled schema

Standardize on clear fields:

```text
event
requestId
traceId
spanId
route
status
durationMs
failureCode
dependency
operationRef
```

Avoid vague fields:

```text
data
payload
everything
userInfo
object
```

When a field lacks a clear definition, it easily becomes a dumping ground for excess data.

## 16. Masking, redaction, and allowlisting

Three concepts commonly used to reduce sensitive data in logs:

- **Allowlist:** permit only a defined set of fields to be logged.
- **Redaction:** remove or replace disallowed data with a safe placeholder.
- **Masking:** obscure part of the data to reduce direct readability.

### 16.1. Allowlists are usually safer than blacklists

Suppose a DTO is:

```java
public record LoginRequest(
        String username,
        String password,
        String otp,
        String deviceId
) {
}
```

Blacklisting requires remembering to strip every sensitive field. If tomorrow the DTO adds `refreshToken`, a developer may forget to update the filter.

Allowlisting logs only the fields truly needed:

```java
log.info(
        "auth.login.attempted authMethod={} requestId={}",
        "PASSWORD_AND_OTP",
        requestId
);
```

No user input field is logged verbatim.

### 16.2. Redaction at the source

Prefer omitting secrets **before constructing the log event**:

```java
log.info(
        "partner.request.completed dependency={} status={} durationMs={}",
        "payment-partner",
        statusCode,
        elapsedMs
);
```

Instead of:

```java
log.info(
        "partner.response.body={}",
        redact(responseBody)
);
```

Trying to redact entire bodies is hard to keep accurate when schemas evolve, bodies nest, or unusual structures appear. If you do not need the body content, **do not read/write it into logs**.

### 16.3. Masking does not replace access control

Even masked logs still require:

- Role-based access permissions.
- Retention policies.
- Encryption in transit and at rest if required by the system.
- Export and sharing controls.
- Incident response processes when mislogged data is discovered.

A partially masked email can still be linked to an individual. Masking reduces risk; it does not make data anonymous.

### 16.4. When correlating a sensitive value is necessary

If you genuinely need to correlate events by a sensitive identifier, generate an **internal reference** that does not reveal the raw data directly.

In cases needing a stable, non-reversible correlation value, consider HMAC with a securely managed key. Avoid plain unsalted hashes on small or guessable domains like emails or phone numbers because they are vulnerable to dictionary guessing.

This is a security and key-management design decision, not something to improvise just to replace a single log line.

## 17. Preventing log injection and log pollution

A request can carry client-controlled strings. If written raw into plain-text logs, newlines or control characters can make one message look like multiple separate log lines.

Example to avoid:

```java
log.info("User-agent={}", request.getHeader("User-Agent"));
```

Client-supplied input can be very long or contain special characters. SLF4J placeholders parameterize values; **they do not automatically sanitize strings**.

### 17.1. Ways to reduce risk

- Do not log raw headers unless needed.
- For client fields that must be logged, enforce length limits and character allowlists.
- Use structured logging encoders with proper escaping.
- Log fields under explicit names and defined schemas.
- Never allow users to control log levels, event names, or log field names.

### 17.2. If accepting `X-Request-ID` is mandatory

One approach is validating format before accepting:

```java
private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

private static String correlationId(String incoming) {
    if (incoming != null &&
            SAFE_ID.matcher(incoming).matches()) {
        return incoming;
    }

    return UUID.randomUUID().toString();
}
```

The example requires importing `java.util.regex.Pattern` and `java.util.UUID`.

However, character validation **does not authenticate the header's origin**. If the system should only accept IDs issued by a trusted gateway, add trust-boundary rules and matching network configuration.

## 18. Access logs, application logs, and audit logs

These three log types serve three distinct purposes.

| Log type | Goal | Typical suitable data |
| --- | --- | --- |
| Access log | Observing HTTP traffic | Route/method/status/latency, request correlation |
| Application log | Diagnosing processing flows and errors | Event, failure code, dependency, operation ID |
| Security audit log | Recording security events needing traceability | Action, outcome, controlled principal reference, timestamp |

### 18.1. Access logs should not record every header

Embedded Tomcat has access logging configuration depending on Spring Boot version:

```properties
server.tomcat.accesslog.enabled=true
```

To use it safely, design an appropriate access-log pattern and log destination. Some access-log patterns log raw request paths, queries, headers, or cookies if configured that way.

Thus, **enabling access logs does not automatically produce minimized access logs**. In environments where URLs carry personal data, inspect the actual pattern or emit access summaries from an HTTP instrumentation layer capable of capturing route templates.

### 18.2. Application logs do not replace an audit trail

A permission-change event may need to be recorded as a structured audit event:

```text
event=role.assignment.changed
actorRef=usr_73a1
targetRef=usr_83c4
roleCode=REPORT_VIEWER
result=SUCCESS
```

These reference codes can still constitute personal data depending on linkability. Apply appropriate access and storage policies.

Do not use `log.info("User X did Y")` as the sole mechanism for all audit requirements. Critical audit trails may require dedicated integrity, retention, access permissions, and queryability.

### 18.3. Do not store passwords in audit logs

Even security events requiring high traceability never need raw passwords, OTPs, or access tokens.

Record **the action and outcome**, not the secret used to perform the action.

## 19. DEBUG/TRACE configurations requiring caution

Some developers enable:

```properties
logging.level.root=DEBUG
```

or:

```properties
logging.level.org.springframework=TRACE
```

to investigate bugs. The more verbose the level, the more metadata libraries can record, including information that should not persist long-term.

### 19.1. Debug SQL and bind parameters

ORM/JDBC libraries have mechanisms to log SQL statements and parameter bindings at DEBUG/TRACE depending on version.

Example query:

```sql
select * from customer where email = ?
```

Even when SQL uses placeholders, a logger tracing bind parameters can write the actual email value.

Do not enable parameter-binding logging in production without evaluating what data can appear. When investigating slow queries, prefer safer metrics, query shapes, and aggregated summaries.

### 19.2. Spring Security and HTTP clients

Debug logging in security filters or HTTP clients can reveal request details, endpoints, and headers depending on logger/version.

Before enabling:

1. Identify the exact logger/package needing debug.
2. Evaluate log output in a controlled environment.
3. Set an expiration time and an owner responsible for disabling it.
4. Do not log tokens, cookies, or raw bodies.
5. Verify where logs are stored and who has read access.

### 19.3. Do not log the entire `Environment`

Spring Boot's `Environment` can contain connection passwords, resolved secret placeholders, and many other properties.

Do not do:

```java
log.info("Environment: {}", environment);
```

or loop over all property sources printing values. When diagnosing, read only individual **non-sensitive** properties.

## 20. Field names and data must stay consistently controlled

A good logging schema has predictable meaning:

```text
event=payment.authorize.failed
failureCode=PROVIDER_TIMEOUT
dependency=payment-gateway
durationMs=700
```

Avoid:

```text
message=Error calling payment
data={...}
debugValue={...}
```

### 20.1. Choose structured event names

One convention:

```text
<domain>.<action>.<outcome>
```

Examples:

```text
order.create.started
order.create.completed
order.create.failed
payment.authorize.failed
inventory.reserve.retry
auth.login.rejected
```

Not every system must follow this exact syntax, yet event names should be consistent across services.

### 20.2. Separate operation ID and request ID

One request can trigger multiple jobs/tasks:

```text
requestId=R1 operationRef=O1 event=order.created
requestId=R1 jobRef=J1 event=receipt.job.created
jobRef=J1 event=receipt.job.completed
```

Request ID describes the HTTP lifecycle; `jobRef` describes the job lifecycle. If a job runs after the request, it can still be correlated without keeping raw request payloads in logs.

### 20.3. Recording execution duration

To measure duration inside Java, use a monotonic clock:

```java
long start = System.nanoTime();

try {
    callPartner();
} finally {
    long durationMs =
            TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - start
            );

    log.info(
            "partner.call.finished dependency={} durationMs={}",
            "pricing-service",
            durationMs
    );
}
```

The example requires importing `java.util.concurrent.TimeUnit`.

`System.nanoTime()` fits measuring elapsed time; do not use it as a display timestamp. Log timestamps are supplied by the logging framework, and system clocks should be synchronized per operational policy.

## 21. Reducing log volume and avoiding excessive cost

Logging every element in a large list can generate millions of lines:

```java
for (Item item : items) {
    log.info("Processing item {}", item);
}
```

If `item.toString()` contains sensitive data, the risk is even greater.

### 21.1. Use summary logs

Instead:

```java
log.info(
        "batch.completed jobRef={} processed={} failed={} durationMs={}",
        jobRef,
        processedCount,
        failedCount,
        durationMs
);
```

When needing to investigate a specific failing item, log a non-sensitive reference along with the error code rather than dumping the whole item.

### 21.2. Sampling for high-frequency logs

An endpoint called tens of thousands of times per minute does not necessarily need INFO logs for every successful step. Use metrics for aggregations, trace sampling for analysis, and selective logs for errors.

However, **never blindly sample mandatory audit or security events**. Each data category has its own purpose and retention rules.

### 21.3. Rate limiting for repeated errors

When a dependency loses connectivity, thousands of requests can generate the same exception stack trace. Consider throttling repeated logs, aggregating failure counters, and alerting on metrics.

A single log entry with a correlation ID is enough to analyze an example, while metrics show the scale of impact.

## 22. Retention, access, and protecting logs

No single retention period fits every system. Retention duration should be based on operational goals, data necessity, log category, and applicable regulations.

Operational questions to answer:

- Who can view application logs, access logs, and audit logs?
- How long are logs kept, where, and in which replicas/copies?
- Is data encrypted in transit and at rest?
- Which third-party systems receive logs?
- Are there controls to delete/restrict log exports and copies?
- When a secret is spotted in logs, who owns remediation?
- Are production logs kept separate from dev/test environments?

### 22.1. Do not use "only SREs read logs" as an excuse to log secrets

Centralized logging platforms still face risks of accidental access, accidental sharing, or data exports during incident triage.

**Never writing secrets into logs in the first place** is far safer than logging them and relying solely on access controls.

### 22.2. When a secret leaks into logs

Execute an appropriate incident response process:

1. Stop the application from continuing to emit the sensitive log line.
2. Assess the secret type and where the logs were copied.
3. Revoke/rotate the credential if it can be misused.
4. Restrict access and handle log copies per organizational procedures.
5. Add controls to prevent recurrence.

Deleting one line from a dashboard is rarely enough if the data already flowed through collectors, archives, or other exports.

## 23. Putting it together: logging an order placement request

Suppose `POST /api/orders` calls the inventory service and saves an order. A sensible logging policy divides the milestones:

```text
HTTP request received
       |
       v
Request ID generated / trace context received
       |
       v
Validate input
       |
       +--> Invalid -> log failureCode=VALIDATION_FAILED
       |
       v
Reserve inventory
       |
       +--> Timeout -> log dependency + retry attempt
       |
       v
Persist order
       |
       +--> Failure -> log sanitized errorCode
       |
       v
HTTP response
       |
       v
Log method, route template, status, duration
```

### 23.1. Permitted fields in the example

```text
requestId
traceId
event
operationRef
itemCount
failureCode
dependency
attempt
method
route
status
durationMs
```

Condition: `operationRef` is an identifier evaluated as safe for logs; `itemCount` is a count, not order contents.

### 23.2. Excluded data

```text
Authorization header
Session cookie
Customer email
Delivery address
Payment card details
Request body
Response body
Access token / refresh token
```

### 23.3. Example service logging by event

```java
package com.example.orders.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final InventoryClient inventory;
    private final OrderRepository repository;

    public CheckoutService(
            InventoryClient inventory,
            OrderRepository repository
    ) {
        this.inventory = inventory;
        this.repository = repository;
    }

    public void checkout(
            String operationRef,
            int itemCount
    ) {
        log.info(
                "checkout.started operationRef={} itemCount={}",
                operationRef,
                itemCount
        );

        long started = System.nanoTime();

        try {
            inventory.reserve(operationRef);
            repository.saveOperation(operationRef);

            log.info(
                    "checkout.completed operationRef={}",
                    operationRef
            );
        } catch (InventoryTimeoutException ex) {
            log.warn(
                    "checkout.failed operationRef={} failureCode={} dependency={}",
                    operationRef,
                    "INVENTORY_TIMEOUT",
                    "inventory-service"
            );
            throw ex;
        } finally {
            long durationMs =
                    TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - started
                    );

            log.debug(
                    "checkout.finished operationRef={} durationMs={}",
                    operationRef,
                    durationMs
            );
        }
    }
}
```

The example assumes the application defines `InventoryClient`, `OrderRepository`, `InventoryTimeoutException`, and imports `TimeUnit` properly. Do not use this as complete production financial transaction code; it illustrates selecting logging fields.

### 23.4. Illustrative output

```text
INFO  requestId=R-123 checkout.started operationRef=O-987 itemCount=2
WARN  requestId=R-123 checkout.failed operationRef=O-987 failureCode=INVENTORY_TIMEOUT dependency=inventory-service
INFO  requestId=R-123 http.request.completed method=POST route=/api/orders status=503 durationMs=804
```

In this example, logs contain no customer email, delivery address, payment details, or raw payload. Operators can still locate all logs by `requestId=R-123` and pinpoint the failing dependency.

## 24. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Logs are internal only, so logging passwords is fine." | Internal logs still face access, export, backup, and leak risks |
| "Using `{}` placeholders makes all data safe." | Parameterized logging does not sanitize contents automatically |
| "DEBUG is off in production, so logging tokens is fine." | DEBUG can be turned on during incidents; never include secrets at any level |
| "Only emails and names count as personal data." | IPs, device IDs, URLs, and account IDs can also enable identification |
| "Masking makes data completely anonymous." | Partially masked values can still be linked or guessed |
| "Request ID is proof of authentication." | Correlation IDs are not credentials or authorization proofs |
| "MDC automatically propagates across all threads." | Many asynchronous boundaries do not auto-propagate MDC |
| "Setting MDC once is enough." | You must clean up/restore it so context does not leak across requests |
| "Reactive apps use MDC just like Servlet filters." | Reactor Context and context propagation require different handling |
| "Logging raw URIs helps debug better than route templates." | Raw URIs can expose emails, tokens, and dynamic identifiers |
| "Structured JSON logging protects PII automatically." | JSON only changes format, not field-selection policy |
| "Logging full exception messages is always safe." | Exceptions can contain SQL params, URLs, tokens, or input |
| "Access logs cannot contain secrets." | Access-log patterns can capture URLs, queries, cookies, or headers |
| "INFO is suitable for every item in a batch." | Easily causes huge log volume; summarize or sample instead |
| "A request is done when the filter `finally` runs." | Async Servlets and error dispatches may need other instrumentation |

## 25. Hands-on exercises

### Exercise 1 — Design a field policy

A login API accepts username, password, OTP, and device ID.

Propose:

- Events that should be logged.
- Failure codes that can be used.
- Safe request context.
- Fields that must never be logged.
- Appropriate log levels for login success, failure, and system errors.

Explain why username or device ID do not belong in logs by default.

### Exercise 2 — Spot bugs in logger calls

Given:

```java
log.info("Login request: {}", loginRequest);
log.debug("Token: {}", accessToken);
log.error("Request failed: {}", request.getRequestURI());
```

Rewrite them using event names, failure codes, route templates, and request IDs. Do not log raw request bodies, tokens, or URLs with dynamic path values.

### Exercise 3 — Build a servlet correlation filter

Write a `OncePerRequestFilter` to:

1. Generate a server-side request ID.
2. Put the request ID into MDC.
3. Set response header `X-Request-ID`.
4. Clear MDC in `finally`.

Then create a controller and service that both log. Confirm log lines from a single request share the same ID.

### Exercise 4 — Observe thread reuse

Try removing `MDC.remove("requestId")` in a demo and sending multiple requests through a thread pool. Observe the risk of stale context lingering.

Once understood, restore cleanup; never leave missing cleanup in real applications.

### Exercise 5 — Context with `@Async`

Create an async service and check whether logs on the new thread have `requestId`.

Then configure a `TaskDecorator` to propagate MDC and restore context in `finally`.

Explain why copying one context field does not mean copying all user information.

### Exercise 6 — Request URI vs route template

Create an endpoint:

```text
GET /api/users/{userId}/orders
```

Send a request with a mock `userId`. Compare `request.getRequestURI()` with `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE`.

Explain why a route template is better suited for log fields and metric labels.

### Exercise 7 — Exceptions and duplicate logs

Create an exception thrown from a repository, passing through a service to `@RestControllerAdvice`.

First try logging the stack trace at all three layers. Then refactor to one primary error-logging boundary and use failure codes where needed.

Compare log line counts and how easy it is to spot the root cause.

### Exercise 8 — Structured logging

Design a JSON event for:

```text
payment.authorize.failed
```

Use only fields such as `event`, `requestId`, `failureCode`, `dependency`, `durationMs`, and a non-sensitive operation reference. Do not include card numbers, tokens, or raw responses in the JSON.

### Exercise 9 — Trace across two services

Simulate `order-service` calling `inventory-service`. Use project-supported tracing instrumentation to share the same trace ID with separate span IDs.

Search logs from both services by trace ID, then explain the difference between trace ID, span ID, and a locally generated request ID.

### Exercise 10 — Safe SQL logging

Create a query using a prepared statement or ORM filtering by a mock email. Check SQL statement logging and parameter binding logging configuration.

Explain why enabling TRACE for bind parameters can expose sensitive values even though the SQL statement uses `?`.

### Exercise 11 — Configure retention

Design separate log retention policies for application logs, access logs, and security audit logs. Specify:

- Purpose.
- Permitted fields.
- Authorized access groups.
- Retention duration requiring approval.
- Export handling and secret-leak response.

Do not share one retention policy simply because all three are named "log".

### Exercise 12 — Build a production diagnostic plan

A customer reports an error with a request ID. Describe how to:

1. Search logs by ID.
2. Inspect event/failure code/status/duration.
3. Follow the trace to dependent services.
4. Compare error metrics by route.
5. Collect enough technical info without asking the customer for passwords, OTPs, or access tokens.

## 26. Remember

**Logs must provide enough context to operate without duplicating sensitive data.** Usually log event names, failure codes, route templates, status codes, durations, and correlation IDs. Never log raw passwords, tokens, cookies, payment details, request/response bodies, or unnecessary personal data.

In Spring Boot, SLF4J/Logback and MDC help attach request context to logs; however, MDC must be cleaned up when threads are reused and propagated carefully across executors or asynchronous boundaries. With WebFlux, Reactor Context and tracing context propagation must follow the reactive model.

Request IDs help locate logs for one request; trace/span IDs correlate across services. These IDs **are not credentials** and do not replace authentication/authorization. Structured logging improves searchability yet does not strip secrets automatically.

When designing production logging, apply **field allowlisting, data minimization, single error-logging ownership, appropriate retention, and log access control**. A good log line lets operators understand what happened without reading users' private info or secrets.
