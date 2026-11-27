# Correlation IDs in Spring Boot Logs

In the **Logging** chapter of the **SPRING_BOOT_OBSERVABILITY** module, a Correlation ID is an identifier recorded alongside logs to link events belonging to a single request or workflow. When a request flows through a gateway, `orders-service`, and `payment-service`, sharing the same Correlation ID helps operations teams find related log lines even when emitted by multiple instances or services.

A Correlation ID is especially helpful when full distributed traces are unavailable—for instance, when a trace is dropped by sampling, instrumentation does not cover a library, or the logging system is the primary investigation source. This identifier is only valuable when it is generated or accepted under a clear convention, propagated across the right boundaries, placed into the logging context, and cleaned up from the thread after each request.

In the **SPRING_BOOT_OBSERVABILITY** module, log correlation works together with Micrometer Observation, metrics, and distributed tracing. It is important to distinguish **Correlation ID**, **Trace ID**, **Span ID**, and **Business ID**; they have different scopes and purposes even though they sometimes appear together in the same log event.

## 1. What Problem Does a Correlation ID Solve?

Suppose an order confirmation request passes through three services:

```text
Mobile client
    |
    v
API Gateway
    |
    v
orders-service
    |
    +----> inventory-service
    |
    +----> payment-service

Related logs all carry:
correlationId = req-7f31c8a2
```

When an on-call operator needs to investigate the transaction, they can search `correlationId=req-7f31c8a2` in the centralized logging system to see how the request was received, inventory was checked, payment was called, and the response was returned.

Without a correlation ID, finding logs often relies on timestamps, hostnames, users, or similar message text. That approach easily misses logs under high concurrency, clock skew between machines, or delayed processing steps.

A Correlation ID answers the question **"which log events belong to the same request/workflow?"** By itself, it does not provide exact causal ordering, per-step duration, or parent-child relationships. Distributed tracing answers those questions in detail using spans and context propagation.

## 2. Distinguishing Correlation ID from Trace ID, Span ID, and Business ID

| Identifier | Scope | Purpose |
| --- | --- | --- |
| Correlation ID | Application convention, typically one request or workflow | Finding related log events |
| Trace ID | One distributed trace | Linking spans across services/processes |
| Span ID | A specific span within a trace | Identifying an operation and parent-child relationships |
| Business ID | Business entity such as order/payment/customer | Looking up business lifecycle under granted permissions |
| Session ID | An interactive session | Grouping session requests if permitted by policy |

A single log can contain multiple identifiers:

```json
{
  "timestamp": "2026-11-22T10:15:02.120Z",
  "level": "INFO",
  "service": "orders-service",
  "message": "Payment authorization started",
  "correlationId": "req-7f31c8a2",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "orderId": "ord-20481"
}
```

The Correlation ID finds logs by the system's request convention; the Trace ID opens the distributed trace; the Span ID pinpoints the specific operation; the Order ID looks up the business entity. One order can go through multiple requests/retries and therefore have multiple Correlation IDs or Trace IDs.

**Do not equate Trace ID with Correlation ID by default.** A Trace ID follows the format and lifecycle of the tracing system; a Correlation ID may be generated at a gateway, received from a trusted header, or bound to a workflow per application policy. If you already have a Trace ID and only need log correlation within a distributed trace, Micrometer Tracing's logging integration may already put trace/span IDs into MDC; you do not necessarily need an extra Correlation ID with the same value.

## 3. Choosing Where to Generate a Correlation ID

A common convention:

1. A trusted internal gateway generates the Correlation ID and passes it via an agreed header.
2. The receiving service validates the header against the allowed format, length, and constraints.
3. If the header is missing or invalid, the service generates a new ID using a secure, unpredictable ID generator.
4. The service places the ID into the logging context for the duration of processing and can return it in a response header for caller/support lookup.
5. When calling downstream services, the service forwards the Correlation ID using an allowlisted header and uses the same value in related logs.

Example header:

```http
X-Correlation-ID: req-7f31c8a2
```

The header name is an application convention, not a replacement for the W3C Trace Context standard. Another name can be used if the system already has a convention; what matters is that the gateway and services share the same semantics.

### Should You Trust a Client-Supplied Correlation ID?

You should not accept any arbitrary string sent by a client without validation. External clients can send very long values, control characters, newlines, or intentionally reuse the same ID across requests to cause confusion.

A safe policy:

- Enforce a small length limit, such as 64 characters max.
- Accept only an allowlist of ASCII letters, digits, hyphens, and underscores.
- Reject or replace with a new ID if the value is invalid.
- Never use a Correlation ID as a credential, tenant authorization, or proof of identity.
- At a trust boundary, the gateway can strip headers from the Internet and generate a system-controlled ID.

A Correlation ID does not need to contain a username, email, phone number, order details, or personal data. A random value carrying no business meaning is usually better.

## 4. Putting Correlation ID into MDC in Spring MVC

In a Spring MVC servlet application, a `OncePerRequestFilter` can resolve the Correlation ID, place it into MDC before the controller runs, add it to the response, and clean up MDC in `finally`.

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationIdFilter extends OncePerRequestFilter {
    private static final String HEADER = "X-Correlation-ID";
    private static final String MDC_KEY = "correlationId";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String supplied = request.getHeader(HEADER);
        String correlationId = isValid(supplied)
                ? supplied
                : UUID.randomUUID().toString();

        String previous = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previous);
            }
        }
    }

    private boolean isValid(String value) {
        return value != null && SAFE_ID.matcher(value).matches();
    }
}
```

This is an example for **synchronous request handling on a servlet thread**. The filter saves the previous MDC value and restores it after the request finishes, rather than calling `MDC.clear()` which would wipe out other keys placed by the framework or tracing integration. This avoids losing `traceId`, `spanId`, or valid metadata from other components.

In a real application, register the filter via a bean or appropriate filter registration. Check the filter order: the filter must run before any component that needs to log the Correlation ID; if logs must also include trace/span IDs, tracing instrumentation must also have its context open at the time the log is written.

### Registering the Filter

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CorrelationLoggingConfiguration {

    @Bean
    FilterRegistrationBean<CorrelationIdFilter> correlationIdFilter() {
        FilterRegistrationBean<CorrelationIdFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new CorrelationIdFilter());
        registration.setOrder(-100);
        registration.addUrlPatterns("/*");
        return registration;
    }
}
```

The order `-100` is just an example; pick an order aligned with your application's actual filters for security, tracing, and request logging. Do not register the same filter simultaneously in multiple ways causing it to run twice unexpectedly.

## 5. Printing Correlation ID with a Logback Pattern

Once the ID is in MDC, a Logback pattern can read it with `%X{correlationId}`.

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level
                [%thread] service=orders-service
                correlationId=%X{correlationId:-}
                traceId=%X{traceId:-}
                spanId=%X{spanId:-}
                %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Example output:

```text
2026-11-22T10:15:02.120Z INFO
[http-nio-8080-exec-3] service=orders-service
correlationId=req-7f31c8a2
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
Order confirmation started
```

The MDC key names `traceId` and `spanId` depend on the logging correlation integration/version; check your Spring Boot/Micrometer Tracing runtime configuration. If the tracing bridge does not provide those keys or the log runs outside a span scope, the pattern may print empty values. Do not conclude the Correlation ID filter is broken solely because Trace ID is absent.

For structured logging, prefer emitting fields as separate JSON properties rather than concatenating them into the message. That way the logging system can filter accurately by `correlationId`, `traceId`, `spanId`, `service.name`, and `level`.

## 6. Calling Downstream Services and Preserving Correlation ID

When service A calls service B, the Correlation ID can be passed using a custom header under an internal contract:

```text
orders-service
  correlationId = req-7f31c8a2
       |
       | HTTP request
       | X-Correlation-ID: req-7f31c8a2
       v
payment-service
  correlationId = req-7f31c8a2
```

For clients auto-configured by Spring Boot, you can add an interceptor strictly for the business custom header. Example with `RestClient.Builder`:

```java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .requestInterceptor((request, body, execution) -> {
                    String id = MDC.get("correlationId");
                    if (id != null) {
                        request.getHeaders().set("X-Correlation-ID", id);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
```

This snippet reads MDC at the moment the client request executes. It suits synchronous calls in the same execution context; if the call crosses an executor/reactive pipeline, verify context has been propagated before reading.

Do not overwrite `traceparent` in this interceptor. Trace context belongs to the tracing propagator and client instrumentation. The Correlation ID header is a separate convention and does not replace W3C Trace ID, Parent Span ID, or the sampled flag.

Service B should apply the same validate/generate rules. If it receives a valid ID from a trusted internal service, it can continue using that value. If the ID is invalid, do not put the raw value into MDC or logs; generate a new ID according to policy. The gateway is typically where headers are normalized and the trust boundary sits.

## 7. MDC Does Not Automatically Propagate Across Threads

SLF4J's MDC is normally implemented using `ThreadLocal`. If a request thread submits a callback to another executor, the callback does not automatically inherit MDC values.

```java
try {
    MDC.put("correlationId", correlationId);
    CompletableFuture.runAsync(() -> {
        // Do not assume MDC is preserved on the worker thread.
        log.info("Background persistence started");
    });
} finally {
    MDC.remove("correlationId");
}
```

The callback may run after the request thread has already removed MDC; logs in the worker will lack the Correlation ID. Do not keep the request's `ThreadLocal` open just to wait for a background task.

### Using `TaskDecorator` to Capture/Restore Context

With Spring Framework supporting Micrometer Context Propagation, you can use `ContextPropagatingTaskDecorator` on an executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class LoggingTaskConfiguration {

    @Bean(name = "loggingExecutor")
    ThreadPoolTaskExecutor loggingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

The task must actually run on this executor:

```java
CompletableFuture.runAsync(
        () -> log.info("Background persistence started"),
        loggingExecutor);
```

Context propagation only works for registered and integrated context accessors. Verify that the MDC correlation key is captured/restored given your application's dependencies and versions; do not assume a task decorator automatically reads arbitrary `ThreadLocal`s.

If you only need to pass a single application-specific value, you can capture it before submission and restore it inside `try/finally` on the worker:

```java
String capturedId = MDC.get("correlationId");

executor.execute(() -> {
    String previous = MDC.get("correlationId");
    if (capturedId != null) {
        MDC.put("correlationId", capturedId);
    }
    try {
        log.info("Processing async order");
        processOrder();
    } finally {
        if (previous == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", previous);
        }
    }
});
```

This is a manual way to propagate one key; if there are multiple context values, tracing context, and baggage, using a unified context propagation mechanism is usually safer. Always restore the previous MDC so a thread pool never leaks an ID between two tasks.

## 8. Correlation IDs in Reactive and Message Processing

With WebFlux/Reactor, execution can switch threads across schedulers. `ThreadLocal`-based MDC does not automatically reflect the Reactor Context. Use the appropriate reactive instrumentation/context-propagation integration or bridge MDC at the logging boundary depending on your version; do not set MDC once at the start of a chain and assume every downstream operator runs on the same thread.

For messaging:

- Producers include the Correlation ID in a message header per the agreed contract.
- Consumers validate the header before placing it into the logging context.
- The MDC scope is opened during message handling and closed in `finally`.
- Retries/dead-letter queues should preserve a meaningful correlation convention while keeping a separate message ID to distinguish each delivery/attempt.
- W3C tracing context is injected/extracted separately by messaging instrumentation; do not replace it with Correlation ID.

A single batch can contain many messages with different Correlation IDs. Do not force one ID onto the entire batch if that loses the link to individual messages; emit appropriate batch-level and item-level log events and limit fields to avoid excessive log volume.

## 9. Correlation IDs, Cardinality, and Privacy

A Correlation ID is usually nearly unique per request. That makes it suitable for **searching in logs**, but unsuitable as a metric tag:

| Usage | Attach Correlation ID? | Reason |
| --- | --- | --- |
| Structured log field | Yes, if controlled | Fast lookup of related logs |
| HTTP response header | Possibly | Helps caller/support provide an ID for investigation |
| Internal downstream header | Possibly | Keeps logs grouped per contract |
| Metric labels | No | High cardinality, creates many time series |
| Resource attributes | No | Resources must stay stable per service/process |
| Authorization/identity | No | An ID is neither a credential nor proof of identity |

Do not embed user emails, phone numbers, access tokens, session secrets, or business data inside the ID. If the ID is client-supplied and echoed back, validate it to prevent log injection/header injection. Never log strings containing CR/LF or data capable of forging log lines.

A Correlation ID is not a secret, yet it can become a lookup key into internal data. Restrict access to the log backend, set appropriate retention, and avoid putting the ID into public URLs unless required.

## 10. Log Correlation Alongside Trace ID in Spring Boot

When Micrometer Tracing is configured, the logging integration can add Trace ID and Span ID to MDC for the active span. An application-managed Correlation ID can coexist alongside them:

```text
timestamp=2026-11-22T10:15:02.120Z
service=orders-service
level=INFO
correlationId=req-7f31c8a2
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7
message="Calling payment service"
```

When investigating:

1. Search `correlationId` to gather logs for the request/workflow.
2. Use `traceId` to open the distributed trace if the trace was sampled and exported successfully.
3. Use `spanId` to tie the log to a specific operation inside the trace.
4. Use Business ID via authorized queries to inspect business state.

A missing trace in the backend does not mean the Correlation ID is wrong. The trace may have been dropped by sampling, failed in the exporter/collector, or expired from retention. Conversely, logs sharing a Correlation ID do not prove services propagated everything properly; inspect headers and log context on each service.

## 11. Troubleshooting Missing Log Correlation

Suppose logs from two services show:

```text
orders-service correlationId=req-7f31c8a2 "Payment request started"
payment-service correlationId=req-99ab4d10 "Provider timeout"
```

Two different IDs indicate correlation was altered or the two logs do not belong to the same request. Investigate in order:

1. Confirm the two logs genuinely belong to the same call using timestamps, downstream route, and permitted business events.
2. Check whether the gateway creates or overwrites `X-Correlation-ID`.
3. Check whether the outgoing HTTP client forwards the custom header per contract.
4. Check whether the filter on `payment-service` validates and preserves valid IDs.
5. Check whether async/executor/reactive/message boundaries lose MDC/context.
6. Check filter order and cleanup to prevent stale context or duplicate filter execution.
7. Compare Trace ID/Span ID and `traceparent` separately to see if the distributed trace remains intact.
8. Check whether the logging pattern/JSON encoder reads the right MDC field in each service.

### Quick Diagnostic Table

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| Correlation ID missing on all request logs | Filter did not run or wrong order | Filter registration and URL pattern |
| Only one service has the ID | Outbound header not sent or downstream not reading it | Client interceptor, gateway, server filter |
| ID changes downstream | Header regenerated, invalid, or untrusted policy | Validation and trust boundary |
| Previous request's ID appears on next request | MDC not cleaned up/restored | `try/finally`, thread reuse |
| Async logs missing ID | Context did not cross executor | `TaskDecorator` or capture/restore |
| Trace ID present but Correlation ID missing | Tracing integration active, custom filter missing | MDC key and filter |
| Correlation ID present but Trace ID empty | No active span or trace integration disabled | Tracing bridge, scope, and sampled context |
| JSON logs cannot be filtered by ID | Encoder writes ID into message instead of field | Structured logging encoder |

## 12. Testing the Filter and MDC

An integration test should verify:

| Request input | Expectation |
| --- | --- |
| No header | Application generates a new ID and returns response header |
| Valid header | ID is preserved per policy and appears in MDC/logs |
| Overly long header | Raw value not placed in MDC; new ID generated or rejected |
| Header containing CR/LF | Rejected as invalid |
| Request throws exception | MDC is still restored in `finally` |
| Two consecutive requests on same thread | Second request's ID is unaffected by the first request |
| Downstream HTTP call | Custom header forwarded per contract |
| Executor task | ID is captured/restored and cleaned up after task |
| Logging pattern | Correlation ID, Trace ID, and Span ID in separate fields |

Do not test solely by calling `MDC.put()` in a unit test and concluding the HTTP filter works. Test through the servlet filter chain, response headers, log appender/encoder, and if possible a downstream stub.

## 13. Scenario Exercise

A request enters `orders-service` without a Correlation ID. The filter generates `req-a71c9d` and logs:

```text
orders-service correlationId=req-a71c9d traceId=aaaa... "Order started"
orders-service correlationId=req-a71c9d traceId=aaaa... "Calling payment"
payment-service  correlationId=req-b208f1 traceId=aaaa... "Payment declined"
```

The Trace ID is identical, yet the Correlation ID in `payment-service` differs.

**Questions:**

1. Can you conclude that distributed tracing propagation is broken?
2. What causes could change the Correlation ID while keeping the Trace ID identical?
3. Which component should you inspect first?
4. Should you drop Correlation ID and rely entirely on Trace ID?

**Analysis hints:**

- You cannot conclude tracing propagation is broken because the Trace ID matches; span relationships should be checked separately.
- The gateway/client interceptor may not be forwarding `X-Correlation-ID`, `payment-service`'s filter may generate a new ID when the header is missing/invalid, or a trust policy deliberately replaces IDs at the boundary.
- Inspect the outbound custom header, network/proxy behavior, validation filter, and log context in `payment-service`.
- If the workflow stays within one distributed trace and Trace ID meets log search needs, you can use trace/span IDs from the logging integration. A separate Correlation ID remains useful for workflows spanning multiple traces, queues, or systems without distributed tracing. Only keep it when it has clear semantics and propagation rules.

### Completion Checklist

| Item | Confirmation |
| --- | --- |
| Role of Correlation ID | Group logs for the same request/workflow |
| Distinguishing Trace ID/Span ID | Not used interchangeably with Correlation ID |
| ID generation source | Trust boundary and validation rules defined |
| Servlet filter | Reads/generates ID, sets MDC, returns response header |
| MDC cleanup | Restores previous value in `finally` |
| Logging pattern | Records `correlationId`, `traceId`, and `spanId` separately |
| HTTP propagation | Forwards custom header per contract without overwriting `traceparent` |
| Async/reactive/message | Proper context propagation configured |
| Cardinality/privacy | ID kept out of metric labels and sensitive data |
| Investigation | Combines logs, traces, and metrics without mixing roles |

**Remember:** A Correlation ID is a convention-based identifier for grouping logs of the same request or workflow. In Spring Boot, you can validate or generate the ID in a filter, place it in MDC during processing, emit it with Logback/JSON encoder, and forward it downstream per contract. MDC does not cross threads or reactive schedulers automatically; it requires context propagation and proper lifecycle cleanup. Correlation ID is distinct from Trace ID, Span ID, and Business ID; keep them in separate fields, and never use them as metric tags, credentials, or containers for personal data.
