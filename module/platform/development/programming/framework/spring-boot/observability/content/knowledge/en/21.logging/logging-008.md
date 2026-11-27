# Reducing Duplicate Logs in Spring Boot

## 1. Goal and Context

In a Spring Boot application, the same error can be logged multiple times: a repository logs the exception, a service catches and logs it again, controller advice logs it once more, and the servlet container records another stack trace. One failing request therefore generates several nearly identical records. When a system spans many services and retries, log volume grows, storage costs rise, and critical signals drown in repetition.

**Duplicate logs** are log records that repeat or closely mirror one another in event, context, and content. However, two logs with similar messages are not necessarily duplicates: a single request may pass through valid distinct steps, or the same failure may be observed by two different services. The goal is to eliminate redundant records while preserving the details needed for investigation.

This lesson belongs to the **Logging** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and real-world application behavior.

After this lesson, you will be able to:
1. Identify duplicate logs caused by multi-layer exceptions, framework instrumentation, retries, or multiple appenders.
2. Choose a single owner responsible for logging the full stack trace.
3. Distinguish boundary logs from repeated logs along the same call path.
4. Design log levels, messages, and structured fields to prevent duplication.
5. Apply sampling/rate limiting to high-frequency events without hiding critical errors.
6. Combine logs with `traceId`/`spanId`, metrics, and error counters.
7. Verify log counts and retained information after refactoring.

**Baseline:** Spring Boot 3.x/4.x, Java 17+, SLF4J with default Logback unless the logging backend is replaced. Some APIs/configs depend on the logging implementation; check actual runtime dependencies and configuration.

## 2. Distinguishing Types of Repeated Logs

| Type | Example | How to identify |
| --- | --- | --- |
| Same exception across layers | Repository logs, then service/controller logs the same throwable | Same exception/cause chain, same request |
| Both caller and callee log | Client wrapper logs failure, calling service logs it again | Same failure propagating up the call stack |
| Overlapping access logs | Gateway, servlet container, and custom filter all log the request | Same method/path/status, different loggers |
| Retry logs | Each attempt logs the same timeout | Different attempt numbers; may be distinct events |
| Overlapping instrumentation | Auto-instrumentation plus custom interceptor log the same call | Same operation, two mechanisms |
| Multiple appenders | Child logger and root both log one event | One event appears twice within one process |
| Replayed message | Consumer receives message again after redelivery | Different delivery/attempt metadata |
| Repeated job/batch logs | Job summary logged across multiple sub-methods | Need to distinguish one run from separate runs |

### 2.1. Duplicate or Two Valid Events?

Compare timestamps, `traceId`/`spanId`, request/correlation ID, logger name, service/pod, thread, exception class/cause chain, attempt number, message ID, and appender.

Having two services both log a dependency failure can be useful: the caller describes an outbound dependency failure; the callee describes the internal root cause. Use correlation to link them rather than deleting one log merely because the messages look similar.

## 3. Principle: Log Once Where Enough Context Exists

For an exception thrown up the call stack, pick **one layer responsible for logging the full stack trace**. Other layers can add context, wrap the exception, convert it to a response, or update metrics or span status without re-logging the same throwable.

| Layer | Usually appropriate logging responsibility |
| --- | --- |
| Repository/DAO | Do not log every propagated exception; log only when unique internal context exists |
| Service | Add business context, throw/wrap exception; do not re-log if merely rethrowing |
| Controller/API boundary | Convert error to HTTP response; log if the boundary is the owner |
| Global exception handler | Typically logs unhandled request errors and maps responses |
| Message consumer boundary | Logs final failure, message ID/attempt/DLQ action |
| Scheduled job boundary | Logs run summary/final outcome |
| Retry component | Logs attempts at an appropriate level; avoid full stack traces on every retry |

This is a convention, not a rigid law. Ownership must be clear: which layer knows whether the exception was handled and can record the final outcome?

## 4. Avoid Logging and Rethrowing the Same Exception

A pattern that easily creates duplicates:

```java
public Order loadOrder(String id) {
    try {
        return repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));
    } catch (RuntimeException ex) {
        log.error("Cannot load order {}", id, ex);
        throw ex;
    }
}
```

If controller advice or an upper boundary also logs the exception, the stack trace appears multiple times. A service that adds no handling logic and only re-logs the error inflates volume.

Cleaner pattern:

```java
public Order loadOrder(String id) {
    return repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}
```

Global exception handler logs the error at the boundary:

```java
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

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleNotFound(OrderNotFoundException ex) {
        log.warn("Order request could not be completed: {}", ex.getMessage());

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Order not found");
        problem.setDetail("The requested order does not exist.");
        return problem;
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unhandled request failure", ex);

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Internal server error");
        problem.setDetail("The request could not be completed.");
        return problem;
    }
}
```

In this example:
- `OrderNotFoundException` is an expected business outcome, logged concisely at `WARN` instead of with a stack trace.
- Unexpected errors are logged at `ERROR` with the throwable.
- The response never returns stack traces, SQL, tokens, or internal details.
- The service does not re-log the error before letting it reach the handler.

Not every exception deserves `ERROR`. Validation, not-found, or business rejections can be `WARN`/`INFO` or measured solely with metrics per policy. If an error is completely handled and needs no investigation, a stack trace log is not always necessary.

## 5. Wrapping Exceptions Without Double Logging

When a service translates a technical exception into a business exception, preserve the cause so the boundary can log the original stack trace:

```java
public Receipt issueReceipt(String orderId) {
    try {
        return receiptGateway.issue(orderId);
    } catch (GatewayTimeoutException ex) {
        throw new ReceiptUnavailableException(
                "Receipt provider is unavailable", ex);
    }
}
```

This is wrapping, not a reason to log in both the `catch` block and the handler. The final handler can log the wrapped throwable; the stack trace still preserves the cause chain.

Avoid logging in full inside `catch` and also wrapping and throwing if the boundary will log the same error. If the `catch` block holds unique context unrecoverable higher up, consider a short log with an event code/context and agree that the boundary will not repeat the same stack trace.

## 6. Logging Responsibilities at Boundaries

An HTTP request can fail in the service layer and get mapped by a handler to `4xx`/`5xx`. A global exception handler or appropriate boundary filter is where the final response is known.

For message consumers, errors may be retried and succeed, or move to a Dead Letter Queue (DLQ). Logging an `ERROR` stack trace on every retry when processing eventually succeeds can trigger excessive error alerts on dashboards. Design around the lifecycle:
- Each attempt can emit a brief `DEBUG`/`INFO` event or increment a metric counter.
- Transient retryable failures do not necessarily warrant `ERROR`.
- Once retries are exhausted and the message moves to the DLQ, log the final failure event with message ID, attempt count, and routing decision.
- Never log sensitive message payloads.

For scheduled jobs, log start/summary/final outcome at the run level; avoid having every sub-method log the same failure when exceptions propagate up to the job runner.

## 7. Framework Logs and Custom Logs

Spring Boot and libraries may emit their own logs for requests, servers, clients, SQL, retries, or connection pools. When adding a custom log at the same boundary, check whether the two records serve different purposes or merely duplicate each other.

For access logs:
- A reverse proxy logs method, path, status, and latency.
- The servlet container/gateway may also emit access records.
- A custom filter may log request completion.

You can keep one authoritative source, or keep multiple sources when distinguishing edge latency from application processing time—provided loggers/fields remain distinct. If two sources overlap completely and add no value, disable one after assessing impact.

Do not disable framework logs via package wildcards just to shrink volume without checking consequences. Suppressing connection pool verbosity can hide leaks, timeouts, or abnormal reconnects.

### 7.1. Request/Response Body Logging

HTTP body logging easily causes duplicates and privacy risks. Avoid logging full bodies across filters, client interceptors, and controllers simultaneously. If auditing is needed, use a dedicated audit event with explicit schema, retention, and redaction. If only diagnostics are needed, log allowlisted metadata such as method, route template, status, and duration.

## 8. Logback Additivity and Duplicate Appenders

Duplicates can stem from the logger hierarchy: a child logger has its own appender while `additivity=true` causes the event to bubble up to the root logger, which also has an appender.

Example prone to duplication:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.payment" level="INFO">
    <appender-ref ref="CONSOLE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

Logger `com.example.payment` has the `CONSOLE` appender; the event also propagates to `root` and gets written by `CONSOLE` a second time.

If the child logger does not need a dedicated appender, keep the appender on `root`:

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

If a separate appender is genuinely needed, set `additivity=false` on that logger and design clear routing. Do not attach the same appender in multiple places without understanding logger hierarchy.

Spring Boot defaults to Logback if the logging starter and dependencies are unchanged. For Log4j2 or other backends, check their corresponding additivity/filter mechanics.

## 9. Structured Logging to Distinguish Events

Free-text messages make identifying duplicates harder. Structured fields let the backend group by event type, service, trace ID, operation, and outcome.

SLF4J 2 fluent API example:

```java
log.atWarn()
        .addKeyValue("event", "payment.retry_scheduled")
        .addKeyValue("provider", providerName)
        .addKeyValue("attempt", attempt)
        .addKeyValue("traceId", traceId)
        .log("Payment attempt will be retried");
```

A log event can contain:
- Stable event/eventCode.
- Service name and environment.
- `traceId`/`spanId` when tracing is active.
- Correlation/request ID if needed by the application.
- Outcome, attempt number, and dependency name from a controlled value set.
- Timestamp, level, and logger supplied by the logging framework.

Never put dynamic identifiers such as order ID, customer ID, or correlation ID into metric tags. IDs may be needed in logs for searching, subject to privacy, retention, and access controls.

When using Spring Boot structured logging, configure JSON output and inspect actual fields. Two records sharing the same event code do not automatically mean duplicates; check trace/span, attempt, and timestamp.

## 10. Sampling and Rate Limiting for High-Frequency Logs

Some repeated events are real: health checks, polling, retries, cache misses, or client connection failures. Volume can be reduced via sampling/rate limiting, chosen by event type.

### 10.1. When Is Sampling Appropriate?

Sampling fits when an event:
- Occurs at high frequency with a steady pattern.
- Carries little per-record value unless anomalous.
- Has a separate metric/counter tracking total occurrences.
- Has safeguards ensuring rare or sudden errors are not hidden.

For instance, `DEBUG` logs for each poll can keep only a sample while a metric counter tracks total poll counts.

### 10.2. Never Sample Errors Blindly

Do not apply the same sampling rate across all log levels. For failures/errors:
- Keep the first log or emit a periodic time-window summary.
- Count total occurrences with a metric counter.
- Keep samples featuring new exception types, severe statuses, or dependency state transitions.
- Record the count of suppressed events in the window.
- Include burst detection to increase verbosity if errors spike.

Log sampling is not the same as trace sampling. A trace sampler decides which traces/spans are recorded/exported; log sampling decides which log records are written. They are separate operational policies.

### 10.3. Illustrative Suppression Window

Pseudocode example for a logger suppressing repeats per event key over a time window:

```java
public final class DuplicateEventGate {
    private final ConcurrentMap<String, Long> lastLogged =
            new ConcurrentHashMap<>();
    private final long intervalMillis;

    public DuplicateEventGate(Duration interval) {
        this.intervalMillis = interval.toMillis();
    }

    public boolean shouldLog(String eventKey, long nowMillis) {
        AtomicBoolean allowed = new AtomicBoolean(false);
        lastLogged.compute(eventKey, (key, previous) -> {
            if (previous == null || nowMillis - previous >= intervalMillis) {
                allowed.set(true);
                return nowMillis;
            }
            return previous;
        });
        return allowed.get();
    }
}
```

Usage:

```java
if (gate.shouldLog("inventory.poll.timeout", clock.millis())) {
    log.warn("Inventory poll timed out; repeated events are suppressed");
} else {
    suppressedCounter.increment();
}
```

This illustrates the algorithm, not a production-ready component. In multi-instance systems, each JVM has its own map so suppression is not global. The map needs eviction/size bounds to prevent memory leaks; use monotonic time for intervals, and handle concurrency and counters properly. If global rate limiting is required, use a centralized mechanism or supporting backend/appender and weigh its cost.

## 11. Retry Logs: Recording Attempts and Final Outcome

Retries are where duplicates and valid events are easily confused. Suppose a payment call times out three times before succeeding. You can log:
- One `INFO`/`DEBUG` log per attempt if observing retry behavior is needed.
- One `WARN` log when the retry budget is nearly exhausted.
- One `ERROR` log if it ultimately fails.

Do not log the full stack trace for the same transient exception on every attempt if volume is high. Instead, record metrics for attempts, retry exhaustion, and final failures.

```java
public Receipt issueWithRetry(String orderId) {
    try {
        return retryExecutor.execute(
                () -> receiptGateway.issue(orderId));
    } catch (ReceiptProviderException ex) {
        log.error("Receipt issue failed after retries; orderRef={}",
                safeOrderReference(orderId), ex);
        throw ex;
    }
}
```

This logs at the boundary once retries are exhausted. If the retry framework already logs every attempt, adjust its level/configuration or customize the retry listener to avoid repeating full stack traces. Retain attempt visibility when it serves as essential evidence; compact fields or metrics can replace per-attempt stack traces.

## 12. Linking Duplicate Logs with Tracing and Metrics

Spring Boot/Micrometer Tracing usually populates `traceId` and `spanId` into MDC when tracing is active. Log patterns or structured logging can include them to open the matching trace.

When investigating repeated logs:
1. Group by `traceId`/`spanId`, logger, event code, and timestamp.
2. Compare exception classes/cause chains and stack traces.
3. Check whether records come from one service/pod or multiple services.
4. Inspect attempt/message delivery metadata.
5. Open the trace to determine whether spans represent one call or multiple real calls.
6. Cross-check metric counters/error rates to ensure cutting logs did not lose measurements.

Metrics should preserve total counts even when logs are sampled:
- Counters for dependency errors.
- Counters for retry attempts and exhausted retries.
- Counters for suppressed log events.
- Timers for operation latency.

Never use `traceId`/`correlationId` as metric tags because cardinality grows per request. Logs link records; traces show relationships and duration; metrics capture aggregate trends.

## 13. Testing and Verification

A logging change needs tests to confirm only redundant records were removed.

### 13.1. Boundary Unit Tests

Use a test appender or `OutputCaptureExtension` to verify:
- Services do not log a stack trace and then rethrow the same exception.
- The global exception handler emits exactly one event per failed request.
- Unexpected exceptions still retain their throwable/cause chain.
- Business rejections do not emit `ERROR` stack traces outside policy.
- Structured fields like `event`, `outcome`, and `traceId` are emitted accurately.

Do not assert line counts alone; check logger name, level, event code, and throwable.

### 13.2. Integration Tests

1. Send a successful request; verify access/application log counts match design.
2. Send a request causing a business exception; verify one boundary log per policy.
3. Send a request causing an unexpected exception; verify one full stack trace and a safe response.
4. Enable retries and trigger transient failures; verify attempt events carry distinct metadata and final failure logs only once.
5. Send concurrent requests; ensure `traceId`/MDC do not mix.
6. When using multiple appenders, verify events do not appear twice unintentionally.

### 13.3. Testing Sampling/Rate Limiting

- Generate a burst of high-volume events to verify the suppression window.
- Verify the total-occurrences metric still increments by the real event count.
- Verify the suppressed metric increments for events omitted from logs.
- Introduce a new/sudden error type and verify it is still recorded.
- Test across multiple instances if suppression must apply cluster-wide.

## 14. Troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Same stack trace appears multiple times | Multiple layers log then rethrow | Pick a boundary for full exception logging; other layers throw/wrap |
| Same event logged twice in one process | Logback additivity or duplicate appender | Inspect logger hierarchy and appender refs |
| One service logs duplicate access records | Filter and container/proxy both access-log | Pick an owner or distinguish latency per layer |
| Logs jump after enabling tracing | Custom instrumentation plus auto-instrumentation log same event | Inspect handlers/interceptors and remove duplicate instrumentation |
| Retry succeeds yet ERROR dashboard rises | Each transient attempt logs ERROR | Lower level for retryable attempts; keep final failure and counter |
| Cutting logs hides failure counts | Sampling without metric counters | Add counters and suppressed count |
| Stack trace lost after refactoring | Message logged without throwable at boundary | Log exception at the proper owner |
| Rare event disappears | Sampling or suppression window | Never sample critical events; keep first/new transitions |
| Async log carries prior request context | MDC/context not cleaned in thread pool | Propagate and restore/clear scopes properly |
| Same message across multiple retries | Missing attempt/delivery metadata | Add controlled attempt number and message identifier |
| Two services log one failure | Service boundaries not distinguished | Keep needed records, correlate via `traceId` |
| Metric series explode after change | Correlation/request ID used as metric tag | Remove dynamic tag, use bounded tags |

## 15. Production Checklist

- [ ] Identify the source of duplicates before lowering levels or disabling loggers.
- [ ] One layer logs the full stack trace for exceptions propagating along the same call path.
- [ ] Other layers add context via structured fields without re-logging the same throwable.
- [ ] Boundaries log final outcomes for HTTP requests, messages, and scheduled jobs.
- [ ] Retry attempts are distinguished from final failures.
- [ ] Framework access logs and custom access logs have clear ownership and purpose.
- [ ] Logback additivity/appender hierarchy does not emit events twice.
- [ ] Sampling/rate limiting applies only to appropriate high-volume groups.
- [ ] Critical errors and important state transitions are never blindly suppressed.
- [ ] Counters track total occurrences and suppressed events.
- [ ] Logs include `traceId`/`spanId`, event code, and service context where appropriate.
- [ ] `traceId`/`correlationId` are never placed into metric tags.
- [ ] MDC is restored/cleared when requests/tasks complete.
- [ ] Secrets, tokens, and unauthorized bodies are never logged.
- [ ] Tested for success, failure, retry, concurrency, and multiple appenders.

## 16. Practice Questions

1. Why can a service logging an exception and rethrowing it create duplicates when a global exception handler also logs?
2. Should the full stack trace be logged in the repository, service, or request boundary? When are there exceptions?
3. How do you distinguish duplicate error logs from three valid retry attempts?
4. Why can two services both log one dependency failure without being duplicates?
5. How can Logback additivity cause one event to be emitted twice?
6. When should a business exception be logged as `WARN` or tracked solely with metrics?
7. Why preserve the cause when wrapping an exception?
8. Which metrics are needed when sampling `DEBUG` logs so total occurrences aren't lost?
9. How do you avoid duplicate access logs between gateway, servlet container, and custom filter?
10. How do `traceId`/`spanId` help investigate repeated logs?
11. Why should `traceId` never be used as a metric tag?
12. Which tests prove refactoring removed redundant logs while retaining stack traces for unexpected errors?

## References

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture and Logger Additivity](https://logback.qos.ch/manual/architecture.html)
- [Logback — Filters](https://logback.qos.ch/manual/filters.html)
- [Micrometer Tracing — Logging Correlation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
