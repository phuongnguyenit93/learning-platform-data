# Logging Exceptions with Proper Context in Spring Boot

> **Chapter:** Logging  
> **Lesson:** Logging Exceptions with Proper Context  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Is a Standalone Stack Trace Not Enough?

When a request fails, logs may contain a long stack trace while on-call operators still cannot answer basic questions:

- Which request, message, or scheduled job did the error occur in?
- Which service and instance produced the log?
- Which trace contains the corresponding span?
- Which route/operation was the request handling?
- Where was the exception thrown, where was it caught, and was it rethrown?
- Is this a technical failure, an expected business outcome, or a handled retry?

**Logging exceptions with proper context** means recording an exception alongside the metadata needed to identify the activity that caused the failure while preserving diagnostic details. A useful log record usually includes timestamp, severity, logger, message, exception type/stack trace, service identity, and correlation context such as trace ID/span ID when available.

~~~mermaid
flowchart TD
  A["Request / message / scheduled task"] --> B["Context created or extracted"]
  B --> C["Business operation"]
  C --> D{"Exception occurred?"}
  D -->|No| E["Log appropriate outcome"]
  D -->|Yes| F["Identify where exception is handled"]
  F --> G["Log once at the appropriate boundary"]
  G --> H["Preserve exception object and stack trace"]
  G --> I["Attach traceId / spanId / operation"]
  H --> J["Log backend"]
  I --> J
  J --> K["Investigate alongside traces and metrics"]
~~~

Logging with proper context does not mean dumping all request headers or entire objects. Log only enough data to pinpoint the error, comply with security policy, and keep cardinality reasonable.

## 2. Exception, Error Event, and Log Record Are Three Different Concepts

A Java exception is an object representing an abnormal condition in the execution flow. A log record is an event record emitted by the application. In tracing, an exception can be recorded as an event on a span or mark the span with an error status via an Observation/tracing handler.

| Component | Purpose | Example |
| --- | --- | --- |
| Exception object | Represents the error and runtime call stack | `java.net.SocketTimeoutException` |
| Log record | Records information for operators to search | Inventory request timed out |
| Stack trace | Shows the call chain leading to the error | Service -> client -> socket |
| Span event | Attaches an exception event to a span | `exception.type`, `exception.message` |
| Span status | Expresses operation outcome in the tracing model | `ERROR` |
| Trace/span context | Links log and span to the request | `traceId`, `spanId` |

One exception can produce a log, a span event, or both. Having a stack trace in a log does not automatically mark the span as `ERROR`; calling `Observation.error(ex)` does not automatically emit an application log either.

Your design should be consistent: decide where logs are written, where errors are reported to Observation, and where exceptions are propagated to callers. Do not let every layer catch the same exception and re-log the full stack trace.

## 3. Logging Exceptions Properly with SLF4J

Spring Boot uses a logging facade and a backend configured by dependencies/runtime. With SLF4J, logger methods have overloads accepting an exception object. Pass the exception as the final `Throwable` argument so the backend records the stack trace.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private static final Logger log =
            LoggerFactory.getLogger(InventoryService.class);

    public void reserve(String sku) {
        try {
            callInventory(sku);
        } catch (RuntimeException ex) {
            log.error("Inventory reservation failed for sku={}", sku, ex);
            throw ex;
        }
    }

    private void callInventory(String sku) {
        // Call inventory system.
    }
}
~~~

In this example, SLF4J receives the message template, the `sku` value, and the exception. The backend can render the message along with the stack trace. The exception is still rethrown so the caller decides the response or retry behavior.

### 3.1. Pass the `Throwable`, Not Only the Exception Message

Correct example:

~~~java
log.error("Payment authorization failed for orderId={}", orderId, ex);
~~~

Example that loses the stack trace:

~~~java
log.error("Payment authorization failed: {}", ex.getMessage());
~~~

The second line only logs a text message; it does not pass the `Throwable` to the logger. When root-cause investigation is needed, prefer the overload taking the exception object. If a specific policy forbids logging stack traces, make that intentional and ensure replacement diagnostic details are sufficient.

### 3.2. Use Parameterized Logging

Do not concatenate strings manually when the logger supports placeholders:

~~~java
// Recommended
log.warn("Request failed for customerRef={}", customerRef, ex);

// Avoid unless pre-computation is needed
log.warn("Request failed for customerRef=" + customerRef, ex);
~~~

Parameterized logging lets the backend control formatting and avoids string building when the log level is disabled. However, still validate values before logging so sensitive data is not leaked.

## 4. Where to Catch Exceptions and Where to Log?

A practical rule: **catch to handle; log at the boundary responsible for recording the failure event**. Not every `catch` block needs to log.

~~~mermaid
flowchart TD
  A["Database / HTTP client"] --> B["Repository / adapter"]
  B --> C["Business service"]
  C --> D["Controller / message listener"]
  D --> E["Exception handler / boundary"]
  B -. "only propagate if not handled" .-> C
  C -. "propagate or translate to domain result" .-> D
  D --> F["HTTP response / message retry / dead letter"]
~~~

Examples:

- A repository hits a DB error and rethrows the exception: usually no need to log the stack trace in the repository if the service/boundary will log the same error.
- A service catches an exception to perform a successful fallback: log at an appropriate level if the fallback affects operations; logging a stack trace on every fallback is not always necessary.
- A controller or global exception handler converts an error into an HTTP response: usually the right place to log unhandled errors from lower layers if no equivalent log exists yet.
- A message listener decides whether to retry or dead-letter: this boundary should record the attempt and outcome, avoiding having every consumer/helper log the same exception.

### 4.1. One Exception, One Full Log at the Boundary

~~~java
public Order createOrder(CreateOrderCommand command) {
    try {
        return orderGateway.create(command);
    } catch (InventoryUnavailableException ex) {
        // Translate into an appropriate business error/response.
        throw ex;
    }
}
~~~

If a method simply propagates the exception as above, logging the stack trace can belong to the web/message-layer exception handler. If a service executes a fallback, emit a structured event stating the fallback was activated; log the full exception only when it adds diagnostic value and has not already been logged elsewhere.

Do not apply a "log on every catch" rule. Catching might exist solely for cleanup, rollback, exception translation, or retry execution.

## 5. Preserving the Original Cause When Wrapping Exceptions

When converting a technical exception into an exception at another abstraction layer, preserve the original cause:

~~~java
try {
    paymentClient.authorize(request);
} catch (SocketTimeoutException ex) {
    throw new PaymentGatewayException(
            "Payment gateway did not respond in time", ex);
}
~~~

A constructor accepting a cause keeps the root-cause chain visible in the stack trace. Avoid constructing a new exception that drops the cause:

~~~java
// Bad: loses the link to the original cause.
throw new PaymentGatewayException("Payment gateway timeout");
~~~

When translating exceptions, choose an exception type reflecting the current layer's abstraction. Do not embed raw partner response bodies/tokens into the exception message if they might contain sensitive data.

### 5.1. Do Not Log and Unnecessarily Wrap into a New Exception

~~~java
try {
    return client.fetch();
} catch (RuntimeException ex) {
    log.error("Fetch failed", ex);
    throw new ServiceUnavailableException("Fetch failed", ex);
}
~~~

If the global handler also logs the stack trace of `ServiceUnavailableException`, the same failure appears twice. Choose the boundary responsible for full logging; lower layers can translate the exception and preserve the cause without logging it again.

## 6. Keeping Trace Context in Logs

In distributed tracing, Trace ID identifies the trace and Span ID identifies the specific operation within the trace. When the logging integration supports correlation, these values can be placed into MDC or an equivalent context so they appear on log records.

Illustrative log example:

~~~text
2026-11-22 10:15:21.104 ERROR [order-service,traceId=4bf9...,spanId=00f0...] Inventory reservation failed
java.net.SocketTimeoutException: Read timed out
    at ...
~~~

A trace can contain many spans; logs emitted during a span should carry the current span's ID. Trace ID finds the entire distributed trace, while Span ID identifies the operation that emitted the log.

**Never generate a new trace ID inside a `catch` block** just to attach it to a log. Use the active context managed by the tracing integration. If there is no active trace, leave the field empty/absent or use a separate correlation ID with a clear source; never fabricate values to fill logs.

### 6.1. Logback Pattern and MDC

Spring Boot supports correlation IDs via tracing integration and an appropriate logging pattern. With Logback, an illustrative pattern can contain MDC keys:

~~~xml
<configuration>
    <property name="CONSOLE_LOG_PATTERN"
              value="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId:-} spanId=%X{spanId:-} %logger{36} - %msg%n%ex"/>
</configuration>
~~~

This is an example pattern, not a complete configuration meant to replace all Spring Boot defaults. MDC keys and how the integration sets them vary by bridge/version. Before customizing patterns, inspect the current console/file output; avoid accidentally dropping colors, correlation fields, or the default throwable converter.

### 6.2. Correlation Fields Beyond Trace IDs

Approved baggage fields can be included in logging correlation, such as region or workflow version. Only add fields with operational value, bounded cardinality, and no sensitive content. Never put emails, tokens, cookies, or entire request headers into MDC.

## 7. Spring Boot and Global Exception Handlers

In Spring MVC, a global exception handler can convert exceptions into consistent HTTP responses. It can also be a suitable boundary for logging unhandled exceptions.

~~~java
package example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(InventoryUnavailableException.class)
    public ProblemDetail handleInventoryUnavailable(
            InventoryUnavailableException ex) {

        log.error("Request failed because inventory is unavailable", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Inventory temporarily unavailable");
        problem.setDetail("Please retry the operation later.");
        return problem;
    }
}
~~~

Responses returned to clients should contain only safe, helpful details. Never return stack traces, database messages, internal hostnames, tokens, or raw exception messages in production.

If the exception was already logged with a stack trace by an earlier service/interceptor, the handler should not repeat the stack trace. It can log a short outcome or increment an appropriate counter. Establish clear, consistent ownership across exception categories.

### 7.1. Distinguishing Expected vs. Unexpected Errors

| Situation | Suggested logging |
| --- | --- |
| Invalid input validation | Usually no stack trace needed; record controlled outcome/metric if needed |
| Resource not found per contract | Can be a normal business outcome, usually no ERROR stack trace needed |
| Business rule rejects transaction | Record appropriate business outcome, do not automatically treat as technical error |
| Dependency timeout | Log WARN/ERROR depending on impact, keep exception at boundary |
| Database unavailable | Usually requires ERROR with exception and service context |
| Programmer bug/uncaught exception | ERROR with stack trace and trace context |
| Client disconnect/cancel | Can be normal behavior; avoid generating ERROR noise |

Severity depends on semantics and impact, not solely on the exception class name. An exception used for control flow is not automatically a system failure.

## 8. Combining Exception Logging with `Observation.error`

Micrometer Observation lets you report exceptions so tracing/metrics handlers can record the failure within the operation's lifecycle. Example:

~~~java
Observation observation =
        Observation.createNotStarted("orders.create", registry).start();

try (Observation.Scope scope = observation.openScope()) {
    return createOrder();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

This snippet calls `error` on the Observation before stopping it. A tracing handler can attach an exception event or mark the span according to its implementation. A metrics handler can record an appropriate outcome depending on conventions/configuration.

This **does not automatically write an application log**. If a log is needed, invoke the logger at the boundary owning log emission. One failure can simultaneously:
- be reported to Observation so the span reflects the error;
- be logged once with stack trace and trace/span context;
- be counted by a metric with a low-cardinality outcome.

The three actions serve three distinct signals; avoid mistaking one action for a replacement for all signals.

## 9. Exceptions in Async and Reactive Code

Request context can be lost when work moves to another thread. Then the exception log still has a stack trace but lacks `traceId`/`spanId` or carries another request's context if `ThreadLocal` is mishandled.

With executors/`CompletableFuture`, use the context propagation mechanism supported by Spring/Micrometer or your tracing integration. Never maintain a shared MDC map across tasks yourself.

~~~java
CompletableFuture.supplyAsync(
        () -> paymentClient.authorize(command),
        contextAwareExecutor
).whenComplete((result, error) -> {
    if (error != null) {
        Throwable cause = unwrap(error);
        log.error("Asynchronous payment authorization failed", cause);
    }
});
~~~

This example assumes `contextAwareExecutor` is configured to capture/restore the necessary context and `log` is a class field. The `unwrap` helper must preserve causes when stripping `CompletionException`/`ExecutionException` wrappers. Do not use the default common pool assuming MDC/trace context will propagate automatically.

### 9.1. Reactor and WebFlux

In reactive flows, context is tied to the subscription and Reactor Context rather than always to the current thread. Use instrumentation/context propagation compatible with your versions of Spring Boot, Reactor, and Micrometer.

~~~java
return paymentClient.authorize(command)
    .doOnError(ex ->
        log.error("Reactive payment authorization failed", ex));
~~~

This operator is only an illustrative hook; the logging callback must execute inside a context integrated with tracing. Verify using trace IDs in logs from real callbacks. Avoid falling back to raw `ThreadLocal` or manually calling `subscribe` inside a controller to "preserve" exceptions.

### 9.2. Unwrapping Exception Wrappers Carefully

Async frameworks may wrap causes in `CompletionException` or `ExecutionException`. When logging, you can extract the root cause for classification, but do not strip every wrapper if it helps explain where an async boundary transferred the error.

~~~java
private Throwable unwrap(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
~~~

If you log the root cause, ensure the stack trace and context still remain sufficient to understand the asynchronous path. Avoid arbitrarily unwrapping domain-meaningful exceptions.

## 10. Exceptions in Message Listeners and Scheduled Jobs

Not every activity starts from an HTTP request. Message consumers and scheduled jobs also need proper correlation context.

### 10.1. Message Listeners

Consumer logs should include an approved message key/opaque event ID, destination, consumer operation, attempt, and trace context if the producer propagated context in message headers.

~~~java
try {
    process(event);
} catch (RuntimeException ex) {
    log.error(
        "Message processing failed destination={} attempt={}",
        destination, attempt, ex);
    throw ex;
}
~~~

If the framework retries automatically and invokes the listener repeatedly, logging each attempt at an appropriate level can help, but a full stack trace every time creates noise. You can log the first attempt with details, subsequent attempts with attempt/outcome, and a final `ERROR` when the message moves to dead-letter per policy.

Never log the entire message payload. Select normalized event types and technical IDs.

### 10.2. Scheduled Jobs

Scheduled tasks have no natural HTTP trace context. Create an Observation/span for the job or run, adding stable metadata like job name and run outcome. Exception logs can then carry the job span's context.

~~~java
@Scheduled(fixedDelayString = "PT5M")
public void refreshCatalog() {
    try {
        refreshService.refresh();
    } catch (RuntimeException ex) {
        log.error("Catalog refresh job failed", ex);
        throw ex;
    }
}
~~~

This example assumes `log` is declared in the class. If the scheduler swallows exceptions or the framework continues to the next run, track run status using metrics and logs. Never make each run ID a metric label.

## 11. Logging Severity and Detail Level

Log levels should reflect impact and required action:

| Level | When to use | Example |
| --- | --- | --- |
| TRACE | Very detailed info during temporary debugging | Internal execution flow details |
| DEBUG | Diagnostics not needed routinely | Retry decision in tests |
| INFO | Normal operational events | Job completed, fallback handled |
| WARN | Recoverable issue or needing attention | One retry failed but request continues |
| ERROR | Operation failed and needs investigation | Dependency timeout caused request failure |

Do not use `ERROR` for every business rejection or every `4xx`; that makes log error rates meaningless. Do not downgrade critical errors to `DEBUG` just to cut noise. Choose levels based on semantics and alerting policy.

### 11.1. Do Not Log Stack Traces on Every Retry

A request retrying three times can emit three nearly identical stack traces even though only one overall operation eventually failed. You can:
- Emit `DEBUG`/`WARN` on each retry with attempt, dependency, and delay.
- Emit one full `ERROR` at the boundary when the retry policy is exhausted.
- Record metrics for retry count and final failure.
- Keep trace spans per attempt if tracing policy needs per-attempt visibility.

This keeps logs searchable and lowers cost while retaining diagnostic data.

## 12. Sensitive Data and Safety When Logging Exceptions

Exception messages and stack traces can contain:
- SQL with literal values or table/schema names.
- URLs with query parameters.
- Headers/bodies from dependencies.
- File paths, usernames, hostnames, or infrastructure details.
- Tokens, passwords, or customer data embedded in messages by libraries.

Before logging, evaluate exception types/messages and any attached context values. Never put secrets into message templates, MDC, baggage, or span attributes.

### 12.1. Log Minimized Reference Data

~~~java
log.error(
    "Order fulfillment failed orderRef={} dependency={}",
    safeOrderReference,
    "inventory",
    ex);
~~~

`safeOrderReference` must be an opaque ID permitted for logging that contains no directly identifiable personal information. If no ID is needed for investigation, omit the field. Never log full DTOs via `toString()`.

### 12.2. Preventing Log Injection

User inputs can contain newlines or control characters that spoof multi-line log entries. Use structured logging/encoders that escape values, and validate or sanitize inputs per policy. Never concatenate raw user input into a log message.

### 12.3. Access Control and Retention

Logs containing stack traces can be more sensitive than ordinary logs. Restrict read permissions, encrypt in transit and at rest per policy, enforce appropriate retention, and avoid leaving `DEBUG`/`TRACE` enabled broadly in production for extended periods without impact review.

## 13. Structured Logging for Exceptions

Structured logging stores separate fields instead of an unstructured string. Backends can filter by severity, service, exception type, trace ID, or operation.

Illustrative JSON example:

~~~json
{
  "timestamp": "2026-11-22T10:15:21.104Z",
  "level": "ERROR",
  "service.name": "order-service",
  "event.name": "inventory.reservation.failed",
  "message": "Inventory reservation failed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "exception.type": "java.net.SocketTimeoutException",
  "exception.message": "Read timed out"
}
~~~

This is an illustrative schema; actual field names depend on the logging encoder, OpenTelemetry Logs bridge, and backend. OpenTelemetry semantic conventions define how to represent exception/log attributes per convention version.

Do not construct JSON via manual string concatenation. Use an encoder or logging API with structured fields so escaping and data types are accurate. Stack traces can be emitted as a dedicated field or throwable section.

## 14. Linking Logs with Traces and Metrics

When a request fails, an effective investigation workflow usually starts with metrics, moves to traces, and then reaches detailed logs.

~~~mermaid
flowchart TD
  A["Metrics: error rate / latency rises"] --> B["Select service, route, and time window"]
  B --> C["Find a sampled trace"]
  C --> D["Open span with error status/event"]
  D --> E["Grab traceId and spanId"]
  E --> F["Query matching log records"]
  F --> G["Read exception stack and message"]
  G --> H["Cross-check dependency, version, and instance"]
~~~

- **Metrics:** reveal trends and blast radius.
- **Traces:** show which services the request traversed and which operation was slow/errored.
- **Logs:** provide event and exception details at a specific moment.
- **Trace ID/span ID:** connect logs and spans when context propagation/correlation works.

Sampling may leave a failing request without a stored trace in the backend while logs and metrics still exist. Therefore, never require a trace to exist before logging an error. Even when a trace is unsampled, logs should still carry service/operation/time and other permitted correlation IDs.

Never use trace ID as a metric label; high cardinality rapidly multiplies time series. Use exemplars or backend-supported linking mechanisms to navigate from metrics to traces.

## 15. Anti-Patterns: Exception Logging Mistakes That Hurt Investigation

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Logging only `ex.getMessage()` | Loses stack trace and cause chain | Pass `Throwable` to logger |
| Catching, logging, and rethrowing at every layer | One failure produces multiple stack traces | Choose a boundary to log in full |
| Creating a new exception without preserving cause | Loses error origin | Pass cause into constructor |
| Logging raw request/response bodies | Leaks PII/secrets, bloats volume | Log allowlisted metadata |
| Generating a fake trace ID inside `catch` | Log mismatches real trace | Use current tracing context |
| Logging every business rejection as ERROR | Noise and broken semantics | Pick level/outcome by business semantics |
| Logging stack traces on every retry | Hard to read, high cost | Log compact attempts, ERROR when retries exhaust |
| Using `Throwable.toString()` as a stack trace | Missing call stack | Log the exception object |
| Logging in async without context | Cannot tie log back to request | Enable proper context propagation |
| Logging both in service and in global handler | Duplicate records | Define clear ownership |
| Putting per-request IDs into metric labels | Cardinality explosion | Use controlled trace/log attributes |

### Checklist Before Adding a Log

1. Who owns this log record?
2. Is the exception propagated, or is it handled/fallen back?
3. Has a stack trace already been logged in another layer?
4. Are active trace context and correlation fields present?
5. Could the message/attributes leak sensitive data?
6. Does the level accurately reflect the outcome?
7. Does the log include necessary service, operation, dependency, and instance metadata?
8. Will retries create duplicate logs?

## 16. Real-World Scenario: Inventory Timeout Across Three Services

**Scenario:** a client calls `api-gateway`, gateway calls `order-service`, and `order-service` calls `inventory-service`. Metrics show order-creation p95 rising and fallback rates climbing. Some requests eventually fail due to timeouts.

### Step 1 — Metrics Narrow the Scope

Dashboards show rising latency in `order-service` and the inventory client. Counters track timeouts/fallbacks along low-cardinality dimensions such as service, operation, and outcome.

### Step 2 — Trace Reveals the Path

A sampled trace might display:

~~~text
api-gateway: POST /orders
  order-service: orders.create
    inventory-service client: reserve
~~~

`order-service`'s client span takes long and ends in error. If an inventory server span exists, compare under the same trace ID to see whether time was spent in network, queue, or server processing.

### Step 3 — Log the Exception at the Boundary

`OrderService` catches the error only when a fallback policy applies or translation is needed:

~~~java
try {
    inventoryClient.reserve(command);
} catch (SocketTimeoutException ex) {
    log.warn(
        "Inventory reservation timed out; fallback will be used dependency={}",
        "inventory",
        ex);
    return reserveUsingFallback(command);
}
~~~

If the fallback succeeds and this is an operational condition to monitor, a `WARN` log with a stack trace can be reasonable during investigation. Long term, you can log a concise event per fallback and keep stack traces at a controlled rate or condition. Observation should be notified of the error or outcome per your defined semantics; do not mark the whole operation failed if the fallback produces a contractually valid success.

### Step 4 — Do Not Repeat the Same Error Across Every Layer

If the controller/global handler receives an unhandled exception, the handler logs the full `ERROR` with trace context. If the service already logged the fallback, do not emit another `ERROR` stack trace for the same timeout.

### Step 5 — Verify After Changes

After tuning pool/timeouts or fixing the dependency, watch p95, error/fallback counters, trace waterfalls, and logs. Verify `traceId`/`spanId` appear on logs for the right operations and no duplicate stack traces remain.

**Lesson:** exception logging is useful when it clarifies who handled the error, which operation was affected, which context links the trace, and what the final outcome was.

## 17. Lab Exercises and Self-Check Questions

### Exercise A — Message Logging vs. `Throwable`

Create a service that intentionally throws `IOException`. Log once with only `ex.getMessage()`, and once passing the exception object. Compare backend output, stack trace, cause chain, and searchability.

### Exercise B — Controlling Log Ownership

Build Controller -> Service -> Client. Have Client throw a timeout. Try catching/rethrowing across multiple layers. Redesign so only one boundary logs the full stack trace while other layers translate or propagate without duplicate logs.

### Exercise C — Logging with Trace Context

Send an HTTP request with Observation/tracing enabled. Throw an exception in the service and log in the exception handler. Verify the log contains `traceId`/`spanId` and locate the corresponding trace if sampled.

### Exercise D — Async Context

Run a `CompletableFuture` using a custom executor. Inspect MDC and trace context before/after the callback. Enable proper context propagation, then verify the callback log carries the right `traceId`/`spanId`. Run concurrent requests to catch context leakage.

### Exercise E — Security and Severity

Trigger an error whose message includes a URL/query or simulated sensitive input. Design the log so it includes only permitted dependency, operation, opaque reference, and exception type. Classify `INFO`/`WARN`/`ERROR` for validation failures, business rejections, retries, and technical errors.

### Self-Check Questions

1. Why is logging `ex.getMessage()` usually insufficient for investigation?
2. How does SLF4J accept a `Throwable` to print a stack trace?
3. Which `catch` blocks should log and which should simply propagate?
4. When wrapping an exception, why preserve the cause?
5. How do exception logs differ from `Observation.error(ex)`?
6. How do Trace ID and Span ID help locate logs?
7. Why should you never generate a Trace ID inside a `catch` block?
8. Why can MDC be lost during async execution?
9. How does WebFlux/Reactor context differ from `ThreadLocal`?
10. Why avoid logging stack traces on every retry?
11. When should a business rejection not be logged as `ERROR`?
12. How do you prevent duplicate logs between a service and a global exception handler?
13. Which data should be stripped from exception messages and MDC?
14. How does trace sampling affect log searchability?
15. How do you use metrics, traces, and logs together to investigate cross-service timeouts?

**Completion criteria:** log `Throwable` properly; pick the right logging boundary; preserve cause chains; attach service/operation/trace context; handle async; distinguish exception logs from span errors; avoid duplicate logs, PII, and high-cardinality metrics; verify through a real HTTP flow.

## 18. Takeaways

- Pass the exception object to the logger when a stack trace is needed; logging only the exception message drops the call stack.
- Catch to handle; log in full only at the chosen boundary. Avoid logging the same stack trace at every layer before rethrowing.
- When wrapping exceptions, keep the original cause so the root-cause chain is not lost.
- Log records, span exception events, and span status are distinct signals. `Observation.error(ex)` does not emit an application log automatically.
- Use `traceId`/`spanId` from the current context to correlate logs with distributed traces; never fabricate IDs.
- Async and reactive execution require proper context propagation; do not rely on default `ThreadLocal`/MDC across arbitrary threads.
- Choose severity by outcome and impact. Business rejections/validations are not automatically system errors.
- Never write secrets, PII, request bodies, or raw headers into messages, MDC, baggage, or span attributes.
- Metrics quantify trends; traces show paths; logs hold exception details. Trace sampling is not a reason to skip necessary error logs.
- Test log ownership, context, duplicate records, and security along real execution paths.

## References

- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [SLF4J Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture and Configuration](https://logback.qos.ch/manual/configuration.html)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Semantic Conventions — Exceptions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
