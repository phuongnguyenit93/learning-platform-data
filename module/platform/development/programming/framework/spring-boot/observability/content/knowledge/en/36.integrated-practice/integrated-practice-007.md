# Adding Baggage and MDC Correlation

In a Spring Boot system with multiple services, `traceId` links spans belonging to the same request and `spanId` identifies the operation being recorded. However, when investigating a business flow, operations teams sometimes need a small amount of extra context such as customer tier, processing channel, or flow category to read logs and follow requests more easily. Distributed tracing provides **baggage** to carry these key-value pairs across service boundaries; logging uses **Mapped Diagnostic Context (MDC)** to automatically attach current context to each log event.

With Spring Boot, Micrometer Observation and Micrometer Tracing can combine baggage propagation with MDC correlation. This practice exercise builds a checkout flow: the service receives validated request classification information, sets baggage within the processing scope, propagates baggage to a downstream service, and puts baggage fields along with trace ID/span ID into logs. The examples use Spring Boot 3 with Micrometer Tracing; verify dependencies and configuration against your actual application version.

## 1. Distinguishing Trace Context, Baggage, and MDC

These three concepts are related but serve different responsibilities:

| Component | Contents | Scope and Purpose |
| --- | --- | --- |
| Trace context | Trace ID, current span ID, parent relationship, and sampling flags | Link operations within the same distributed trace |
| Baggage | Key-value pairs propagated alongside trace context | Carry small business context across services, e.g., `tenant-tier=premium` |
| MDC | Key-value map attached to log events in the current execution context | Let each log line carry trace ID, span ID, or correlation fields |

For example, a request might carry two W3C headers:

```http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: tenant-tier=premium,channel=web
```

`traceparent` carries information to continue the trace. `baggage` carries allowed supplementary attributes. Instrumented HTTP clients/servers inject and extract context according to the configured propagation format. Applications should not manually assemble or modify `traceparent` and `baggage` headers in business code.

MDC is a logging context local to the current process. MDC does not automatically propagate across HTTP or message brokers. Baggage can be propagated across instrumented transports; correlation configuration allows selected baggage fields to appear in MDC. Therefore, baggage supports sharing context between services, while MDC surfaces that context in each service's logs.

Nor does `traceId` always replace a business correlation ID. A business workflow spanning multiple requests, messages, or retries can produce multiple distinct traces. When you need to stitch those activities together, use a separately managed business correlation ID and propagate it via message metadata or policy-governed baggage. Do not invent extra IDs if the current trace ID already answers the investigative question.

## 2. Declaring Baggage to Propagate and Expose in MDC

Spring Boot provides Micrometer Tracing properties to declare which baggage fields should be propagated from one service to another and which fields should be added to MDC.

Example `application.yml`:

```yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
        - channel
      correlation:
        fields:
          - tenant-tier
          - channel

logging:
  pattern:
    level: "%5p [${spring.application.name:},trace=%X{traceId:-},span=%X{spanId:-},tenantTier=%X{tenant-tier:-},channel=%X{channel:-}]"
```

Configuration breakdown:

- `remote-fields` declares baggage fields allowed to cross process boundaries via Micrometer Tracing's propagation mechanism.
- `correlation.fields` declares baggage fields to populate into MDC so the logging backend can display them.
- `logging.pattern.level` adds `traceId`, `spanId`, and MDC keys to the level/prefix section of the Logback pattern.

Spring Boot usually populates `traceId` and `spanId` into MDC automatically when Micrometer Tracing is enabled and logging integration is active. Adding `tenant-tier` or `channel` to MDC requires configuring the corresponding correlation fields. If using Log4j2 or a custom logging encoder, MDC rendering follows that system's pattern/encoder.

Declare only fields that are truly needed. Every field in baggage can be sent across multiple services and increases HTTP header size, so do not put entire request payloads into baggage.

## 3. Creating Scoped Baggage with Micrometer Tracing

Do not take raw headers straight from clients and push them unmodified into baggage. Baggage can be forwarded to downstream services, so the application must validate, normalize, and restrict values at the trust boundary.

For example, the gateway or authentication layer has determined whether the request belongs to `standard` or `premium`. The controller sets `tenant-tier` baggage within the request scope:

```java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final Tracer tracer;
    private final CheckoutService checkoutService;

    public CheckoutController(
            Tracer tracer,
            CheckoutService checkoutService) {
        this.tracer = tracer;
        this.checkoutService = checkoutService;
    }

    @PostMapping("/checkout")
    public ResponseEntity<CheckoutResult> checkout(
            @RequestHeader(name = "X-Tenant-Tier", required = false)
            String requestedTier,
            @RequestBody CheckoutCommand command) {

        String tenantTier = "premium".equals(requestedTier)
                ? "premium"
                : "standard";

        try (BaggageInScope baggage = tracer.createBaggageInScope(
                "tenant-tier", tenantTier)) {
            CheckoutResult result = checkoutService.checkout(command);
            return ResponseEntity.ok(result);
        }
    }
}
```

`createBaggageInScope` sets the value in the current context and returns a scope that must be closed. `try-with-resources` ensures the scope is restored even if the service throws an exception. Instrumented calls made inside the scope can continue using this baggage. The example assumes `X-Tenant-Tier` is already protected by the gateway; in a real system, derive the tier from authentication results or server-side data rather than trusting an arbitrary header from the Internet.

If you also need `channel`, you can create another baggage scope or build a helper managing multiple fields. Keep the key list fixed and values within a finite domain such as `web`, `mobile`, or `partner`.

### Do Not Hold a Baggage Scope Longer Than the Operation

A baggage scope must have a clear lifecycle. Closing the scope after processing finishes prevents context from leaking into the next request when the thread is reused. Do not store `BaggageInScope` in a singleton field, do not keep a scope in a shared object, and do not close a scope before a synchronous operation needing it finishes.

The example above uses Spring MVC with synchronous calls. With WebFlux or methods returning `Mono`/`Flux`, do not wrap publisher creation in `try-with-resources` and close the scope immediately when the publisher is returned; subscription may occur later. Use Reactor Context and a context propagation mechanism compatible with your Spring Boot/Micrometer version so the scope stays active during reactive execution.

## 4. Observing Baggage and MDC in Logs

Suppose `CheckoutService` calls an instrumented payment client:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final PaymentClient paymentClient;

    public CheckoutService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public CheckoutResult checkout(CheckoutCommand command) {
        log.info("Starting checkout");
        PaymentResult payment = paymentClient.authorize(command);
        log.info("Payment authorization completed");
        return CheckoutResult.from(payment);
    }
}
```

When tracing and logging integration are active, logs may look like:

```text
INFO [checkout,trace=4bf92f3577b34da6a3ce929d0e0e4736,span=00f067aa0ba902b7,tenantTier=premium,channel=web] Starting checkout
INFO [checkout,trace=4bf92f3577b34da6a3ce929d0e0e4736,span=00f067aa0ba902b7,tenantTier=premium,channel=web] Payment authorization completed
```

Two log events can share the same trace ID and span ID if written within the same active span. When the payment call creates a client span, logs written during that span's execution can carry the span ID corresponding to the client operation. Logs in the payment service will have the same trace ID but a span ID belonging to that service. Thus, you can find all logs for a trace by trace ID, then narrow down to an operation by span ID.

If logs lack `traceId` or `spanId`, check the tracing bridge, sampling, instrumentation, and logging pattern. If trace ID is present but `tenant-tier` is missing, check that baggage was created in the right scope, the field is listed in `correlation.fields`, and the logging pattern uses the exact MDC key name.

## 5. Propagating Baggage Through HTTP Clients and Downstream Services

Baggage is only transmitted when propagation is configured and HTTP clients/servers participate in instrumentation. In Spring Boot, use clients instrumented by Micrometer Tracing or configure an appropriate observation convention/interceptor for your client. Do not blindly copy all inbound headers to outbound requests, as this can forward untrusted headers or sensitive data.

Overall flow:

```text
Client
  |
  | HTTP request
  v
Checkout API
  | creates server span
  | sets baggage tenant-tier=premium
  |
  | instrumented HTTP client
  | injects trace context + baggage
  v
Payment API
  | extracts trace context + baggage
  | creates child server span
  | baggage appears in MDC if correlation is configured
  v
Payment service
```

To verify propagation, send a request across both services and verify:

1. The trace backend shows the same trace ID in checkout and payment.
2. The payment server span is a descendant of the matching client span in the checkout trace.
3. Declared baggage fields are received in the payment service.
4. Logs in both services include the trace ID; logs include baggage fields if that service enabled correlation fields.
5. After the request completes, baggage does not erroneously appear in an independent request running next on the same worker thread.

If an HTTP client creates spans but does not inject baggage, check the propagation type and instrumentation of that specific client. Custom HTTP libraries or custom interceptors may require dedicated Observation/Tracing integration.

## 6. Preserving Context Across Executors and Asynchronous Processing

MDC and several tracing mechanisms rely on thread-local context. When handing work off to a thread pool, the new thread does not automatically inherit the calling thread's context. Without context propagation, logs in background tasks can lose trace ID, span ID, and baggage; in the worst case, manual ThreadLocal code can even leave stale values behind from previous tasks.

With Spring Framework 6.1 and later, you can use `ContextPropagatingTaskDecorator` on application-managed executors:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
```

Ensure `@Async` tasks or submitted tasks actually use this executor. For older Spring Framework versions, use a context propagation solution compatible with your Micrometer/Spring version and test on the real executor. Do not manually copy the entire MDC map into a thread pool and leave it behind after the task ends.

With Reactor, context is tied to the subscription rather than pinned to a single thread. Use Reactor Context integration and Micrometer Context Propagation suitable for your version; do not assume an `MDC.put` at the start of a pipeline persists across every scheduler. Test `publishOn`, `subscribeOn`, retries, and async callbacks because they can switch execution threads.

## 7. When Is a Separate Business Correlation ID Needed?

A trace ID is usually sufficient to group logs for a single distributed request. However, a workflow may span queues, batch jobs, or multiple independent requests. For example, an order is created in an initial request, paid via a message minutes later, and finalized by another consumer. These parts may have separate traces while still belonging to the same business process.

In such cases, you can generate a business `correlationId` with a stable format, controlled at a trusted service, and pass it in message metadata or allowlisted baggage. Each service places this ID into MDC so logs can be queried across the workflow. Do not use this ID as a metric tag.

If you must derive a correlation ID from an HTTP header, accept values only from a trusted gateway or strictly validate the format; otherwise, generate a new ID at the trust boundary. Limit length and characters to avoid log injection or malformed headers. Example simple MDC helper in a servlet filter:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class CorrelationIdFilter extends OncePerRequestFilter {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        // Assume a trusted gateway overwrote this header before forwarding.
        String candidate = request.getHeader("X-Correlation-ID");
        String correlationId = candidate != null
                && SAFE_ID.matcher(candidate).matches()
                ? candidate
                : UUID.randomUUID().toString();

        response.setHeader("X-Correlation-ID", correlationId);
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", correlationId)) {
            filterChain.doFilter(request, response);
        }
    }
}
```

This example illustrates MDC for a synchronous servlet request. The regex in the code only checks format and length, not sender authenticity; only use the candidate when a trusted gateway has authenticated and overwritten the header. If the application receives traffic directly from the Internet, generate a new ID instead of trusting a client-provided `X-Correlation-ID`. If the correlation ID must cross async boundaries or other services, explicitly propagate it via message metadata or baggage and set it in MDC again at the receiving process. `MDC` by itself does not transmit IDs over the network or across thread pools. Keep a dedicated filter only when there is a clear workflow use case; if the trace ID already suffices, adding another correlation ID only complicates logs.

## 8. Protecting Baggage and MDC from Unsafe Data

Because baggage is sent across services, it can expose data more broadly than intended. MDC is often written to centralized logs accessed by many people and tools. Apply these rules:

- Only propagate fields listed in the `remote-fields` allowlist.
- Never put access tokens, session cookies, passwords, API keys, emails, phone numbers, or personal data into baggage.
- Never use baggage as an authentication, authorization, or identity-proof mechanism. Receiving services must authenticate requests using dedicated security mechanisms.
- Treat inbound external baggage as untrusted data; validate, normalize, and bound values before using them in logic or logs.
- Keep the number of fields and value sizes small to avoid exceeding proxy/server header limits.
- Do not put high-cardinality baggage into metric tags. Use bounded values like `tenant-tier` instead of tenant ID if you only need grouping.
- Avoid writing baggage to MDC if the field does not need to appear in logs. Every correlation field can increase the size of every log event.
- Verify log masking, access controls, retention, and data deletion procedures per organizational policy.

In particular, never log the entire `baggage` header. Only log selected, validated fields with a clear operational purpose.

## 9. Testing Baggage Propagation and MDC Correlation

Testing should verify behavior across service boundaries and thread boundaries, not merely assert a single log line in a controller.

An integration test suite can include:

| Scenario | Expected Result |
| --- | --- |
| Valid request with tier `premium` | Baggage `tenant-tier=premium` is created in scope and appears in logs |
| Request with unsupported tier | Value is normalized to `standard`; arbitrary strings are not propagated |
| Calling payment via instrumented HTTP client | Payment receives the same trace context and allowlisted baggage |
| Logs in downstream service | Include trace ID/span ID; baggage fields appear if correlation is enabled |
| Service throws an exception | Scope is closed; subsequent requests do not receive stale baggage |
| Task runs via executor | Context is propagated if executor has a context propagation decorator |
| Request without tracing context | Application handles per tracing config; logs must not contain fake trace IDs or stale baggage |
| Baggage contains overly long or invalid value | Value is rejected or normalized at the trust boundary |

For business behavior tests, you can use `MockMvc` to send requests with different tiers and check log capture or a spy service to confirm baggage is in scope. Full propagation testing requires two applications or a test setup with instrumented HTTP server/client; mocking `Tracer` alone does not prove headers are injected/extracted properly.

When verifying logs, do not just look for `traceId` on one line. Check that the same trace ID appears in both services, span IDs change per operation, baggage exists only within the configured scope, and any business correlation ID (if used) is preserved across the required workflow.

## 10. Common Issues and Troubleshooting

| Symptom | Possible Causes | Resolution |
| --- | --- | --- |
| Logs have trace ID but no baggage | Missing `correlation.fields`, wrong key name, or baggage not set in scope | Check configuration, field names, and where the scope is created |
| Baggage exists in first service but is lost downstream | Missing `remote-fields`, uninstrumented HTTP client, or mismatched propagation format | Check remote fields, client/server instrumentation, and propagation type |
| Baggage leaks into the next request | Scope not closed or manual ThreadLocal handling is faulty | Use `BaggageInScope` with try-with-resources and check async boundaries |
| Logs in async task lack trace ID | Context not propagated to the executor | Configure context propagation on the executor and test real tasks |
| Baggage header too large | Too many fields or overly long values | Trim the allowlist, cap sizes, and only transmit essential data |
| Logs contain client-supplied values | Blindly trusting inbound baggage or correlation headers | Authenticate origin, validate, and normalize at the gateway/edge service |
| Multiple disparate IDs make querying difficult | Mixing trace ID, request ID, and business correlation ID without conventions | Define each ID's role, keep only what is needed, and standardize MDC names |

## 11. Deployment Checklist

- [ ] Micrometer Tracing and HTTP client/server instrumentation are enabled for the right version.
- [ ] Baggage fields to propagate are declared in `management.tracing.baggage.remote-fields`.
- [ ] Baggage fields needed in logs are declared in `management.tracing.baggage.correlation.fields`.
- [ ] Log pattern displays `traceId`, `spanId`, and required MDC keys.
- [ ] Baggage is created in a clearly bounded scope and closed after the operation.
- [ ] Inbound baggage is validated/normalized and contains no secrets or personal data.
- [ ] Downstream HTTP clients/servers continue the same trace context and receive the allowlisted baggage.
- [ ] Executors and Reactor pipelines have proper context propagation configured.
- [ ] Business correlation IDs are added only when trace IDs are insufficient for multi-request/message workflows.
- [ ] Neither baggage nor correlation IDs are used as high-cardinality metric tags.
- [ ] Integration tests verify propagation, MDC, and absence of context leaks across requests.

When baggage and MDC are combined properly, operations teams can see selected business context in logs across multiple services and link every log event to its corresponding distributed trace. Micrometer Tracing manages scopes and propagation, Spring Boot configures which fields to propagate and correlate, and MDC serves log events solely within the current process. Keep baggage small, controlled, and clearly scoped so correlation aids investigation without exposing data or adding unnecessary overhead.
