# Trace ID and Span ID in MDC with Spring Boot

When a request passes through controllers, services, repositories, and HTTP clients, logs are emitted across multiple layers and services. Without linking information on log events, operators have to match timestamps or messages to stitch together events from the same request. **Trace ID** links spans within a trace; **Span ID** identifies the specific operation emitting the log. **MDC (Mapped Diagnostic Context)** lets the logging framework attach both values to log events without passing IDs through every method.

In the **SPRING_BOOT_OBSERVABILITY** module, MDC bridges distributed tracing with logs alongside Micrometer Observation, metrics, baggage, exporters, and sampling. This lesson belongs to the **Logging** chapter and focuses on **Trace ID and Span ID in MDC**: how Spring Boot/Micrometer Tracing provides correlation fields, how Logback renders them, context lifecycle, async/thread propagation, structured logs, security, and testing.

## Learning Objectives

After this lesson, you will be able to:
1. Distinguish Trace ID, Span ID, Parent Span ID, and MDC.
2. Explain why log events should contain both trace ID and span ID.
3. Configure Spring Boot/Micrometer Tracing so correlation IDs appear in logs.
4. Customize the Logback pattern or structured JSON logging.
5. Understand MDC scope and the risks when thread pools reuse threads.
6. Propagate context across executors, `@Async`, Reactor, and messaging.
7. Test correlation fields and post-scope cleanup.
8. Investigate requests by pivoting from logs to the trace backend.

## 1. Trace ID and Span ID

An order-creation request may traverse `order-service`, `inventory-service`, and `payment-service`. Each request flow has one **Trace ID**; each operation has its own **Span ID**.

| ID | Meaning | Scope |
| --- | --- | --- |
| Trace ID | Identifies the entire trace | Shared across spans in the trace |
| Span ID | Identifies a single operation | Differs across spans |
| Parent Span ID | Identifies the immediate parent span | Builds parent-child relationships |
| MDC `traceId` | Correlation value read by logging framework | Current context |
| MDC `spanId` | Active span when logging | Changes when a child span is active |

Example:

~~~text
2026-11-22 10:15:31.201 INFO [traceId=4bf92f... spanId=00f067...] OrderController - Request received
2026-11-22 10:15:31.207 INFO [traceId=4bf92f... spanId=8a31c2...] OrderService - Validating order
2026-11-22 10:15:31.229 WARN [traceId=4bf92f... spanId=1f42ad...] InventoryClient - Inventory response is slow
~~~

Lines with the same trace ID belong to one trace; span ID indicates the operation emitting the log. Trace ID is used to look up the trace; Span ID locates the specific span. A custom Correlation ID in a legacy system is not automatically a Trace ID. Never overwrite Trace ID with an order ID/customer ID.

## 2. What Is MDC?

**Mapped Diagnostic Context (MDC)** is a logging API for attaching key-value pairs to the current log event. With SLF4J, applications typically use `org.slf4j.MDC`; Logback provides the implementation when its binding is used.

~~~java
import org.slf4j.MDC;

MDC.put("request.channel", "web");
try {
    log.info("Processing order");
} finally {
    MDC.remove("request.channel");
}
~~~

A Logback pattern reads values via `%X{key}`. In Spring Boot with Micrometer Tracing, the logging integration can automatically manage trace/span IDs in MDC while a span is active. In that case, you do not need to call `MDC.put` in every controller/service.

MDC does not create traces, start spans, propagate trace context over HTTP, or export OTLP. It supplies key-value pairs to the logger when a log event is created. Tracing instrumentation manages the Trace/Span context; the logging integration reads that context and places correlation fields into MDC or the log event.

### 2.1. MDC and `ThreadLocal`

Many logging implementations store MDC per thread. This is convenient for synchronous processing, yet has limitations with reused thread pools, `@Async`/Executors, Reactor thread switches, callbacks/event loops, messaging, and batch workers. If context is not captured/restored, MDC can be lost on a new thread or retain stale values if cleanup fails.

## 3. Spring Boot / Micrometer Tracing MDC Integration

Spring Boot integrates Micrometer Observation and Micrometer Tracing. With an appropriate bridge, the active span context can populate trace ID/span ID for logging correlation.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Keep versions aligned with the Spring Boot BOM; do not mix incompatible Micrometer/OpenTelemetry versions manually.

### 3.1. Tracing Configuration

~~~yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

In production, the OTLP endpoint must point to a Collector reachable by the process/container. Sampling probability configures head-based sampling; it controls which traces are recorded/exported rather than whether MDC is populated once a span is active.

### 3.2. Logging Correlation

Compatible Spring Boot/Micrometer Tracing setups can add correlation IDs to the default logging pattern or support `logging.pattern.correlation`. Illustrative example:

~~~yaml
logging:
  pattern:
    correlation: "[traceId=%X{traceId:-},spanId=%X{spanId:-}] "
~~~

Supported properties and patterns may vary by Spring Boot version. Check the documentation for your version and inspect actual log events. If the default pattern already includes trace/span fields, avoid adding them again so IDs are not duplicated.

### 3.3. Logback Pattern

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [traceId=%X{traceId:-} spanId=%X{spanId:-}] [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This example uses the `traceId` and `spanId` MDC keys commonly supplied by the integration. If the logging bridge uses different key names, adjust to match the actual MDC map. Avoid duplicate pattern configuration.

### 3.4. When There Is No Active Span

A log event can occur before tracing context is created, after a span closes, or inside a background task with no trace attached. In those cases, `traceId`/`spanId` may be empty or fall back to a dash. That is valid behavior. Never generate a random UUID and log it as a real trace; the backend will have no matching trace.

## 4. Correlation Flow

~~~mermaid
sequenceDiagram
    participant Client
    participant Filter as Spring Web tracing
    participant Service as OrderService
    participant MDC
    participant Logger
    Client->>Filter: HTTP request + trace context
    Note over Filter: Extract/create context and server span
    Filter->>MDC: Correlation integration sets traceId/spanId
    Filter->>Service: Invoke controller/service
    Service->>MDC: logger.info(...)
    MDC-->>Logger: Attach correlation fields
    Service-->>Filter: Complete processing
    Note over Filter: Span scope ends, context restored
~~~

HTTP instrumentation extracts trace context from the request or starts a new root trace. While the span is active, the logging integration supplies correlation IDs to log events. When the span ends, context must be restored/cleared following its lifecycle. Without instrumentation or an active span, logs will not automatically carry a trace ID.

## 5. Logging in Code

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderApplicationService.class);

    public void createOrder() {
        log.info("Starting order creation");
        validateOrder();
        log.info("Order creation completed");
    }

    private void validateOrder() {
        log.debug("Validating order input");
    }
}
~~~

Logger calls do not need to accept `traceId`/`spanId`. The logging integration reads the active correlation context. Only log business identifiers after assessing data sensitivity; prefer event codes or pseudonymized identifiers where appropriate.

### 5.1. Structured Logging

~~~json
{
  "timestamp": "2026-11-22T10:15:31.201Z",
  "level": "INFO",
  "service": "order-service",
  "message": "Order validation completed",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "event": "order_validation_completed"
}
~~~

This is an illustrative schema. Actual field names depend on the encoder/appender, Spring Boot structured logging, and collector. Align `traceId`/`trace_id` and `spanId`/`span_id` naming with the backend. JSON does not guarantee correlation on its own; verify values come from the active context.

## 6. Parent-Child Spans and Span ID in MDC

Trace ID remains constant within the same trace; Span ID changes with the current span.

~~~text
Trace ID: 4bf92f...
order-service
  SERVER span A: spanId=1111
    log: request received
    INTERNAL span B: spanId=2222
      log: validating order
      CLIENT span C: spanId=3333
        log: calling inventory
inventory-service
  SERVER span D: spanId=4444, parentSpanId=3333
    log: reserving stock
~~~

MDC correlation should reflect the active span at the moment of the log event. When tracing scope enters a child span, the logging bridge updates the current span ID. When the child scope ends, the parent context is restored. Do not read trace/span ID once at the beginning of a request and copy it into an object reused for every log.

## 7. MDC Lifecycle and Cleanup

For code that adds custom MDC fields, always use `try`/`finally`:

~~~java
import org.slf4j.MDC;

public void processWithLocalContext(String channel) {
    MDC.put("orders.channel", channel);
    try {
        log.info("Processing order");
    } finally {
        MDC.remove("orders.channel");
    }
}
~~~

If you need to restore a prior value, save the previous value first and restore it in `finally`. Never manually mutate `traceId`/`spanId` in MDC when the tracing integration manages them. Never store MDC in a static field, mutable singleton map, or global variable.

## 8. Async and Context Propagation

MDC is typically thread-bound. When `@Async` or an executor hands work off to another thread, MDC is not automatically guaranteed to be copied. Tracing context must also be captured/restored using the appropriate mechanism.

~~~text
HTTP thread A:
  traceId = T1
  spanId  = S1
  submit task

Worker thread B:
  task runs
  MDC may be empty if context was not captured
~~~

With Spring Framework 6.1+ and Micrometer Context Propagation, `ContextPropagatingTaskDecorator` captures and restores registered context accessors:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

The decorator does not automatically turn every `ThreadLocal` into propagatable context. Corresponding tracing/MDC accessors must be registered and properly configured.

For `@Async`, configure `@EnableAsync` and the executor bean. Reactor has its own execution context; use Micrometer Context Propagation and the Reactor integration suited to your version. Kafka/RabbitMQ require injecting/extracting context via message headers. Consumers must restore context after processing so a worker does not carry IDs from the previous message.

## 9. Linking Logs to the Trace Backend

When a log event has a Trace ID:
1. Search logs by `traceId` and event/error code.
2. Open the trace backend and look up the corresponding trace.
3. Inspect the span matching `spanId` to identify the operation that logged it.
4. Check parent/child spans, latency, status, and dependency attributes.
5. Return to logs by Trace ID to inspect related events.

~~~mermaid
flowchart LR
    Log["Log event<br/>traceId + spanId"] --> Query["Search trace ID"]
    Query --> Trace["Trace backend"]
    Trace --> Span["Locate span ID"]
    Span --> Parents["Inspect parent/child spans"]
    Parents --> Logs["Search related logs"]
    Logs --> Diagnose["Diagnose request"]
~~~

A log carrying a trace ID without a matching trace in the backend can happen when head sampling drops the trace, the exporter errors out, the Collector/backend drops it, or retention/time range excludes it. MDC proves the logging integration saw the context at log time; it does not prove the trace was exported and stored.

## 10. Security and Data in MDC

| Data | Policy | Principle |
| --- | --- | --- |
| `traceId` | Yes when active | Find trace; never use as metric label |
| `spanId` | Yes when active | Locate specific span |
| `service.name` | Optional | Stable, standardized value |
| `orders.channel` | Consider | Approved field, finite value set |
| `user.email` | Not by default | PII |
| Authorization/cookie | Never | Secret, strictly never log |
| Request/response body | Not by default | May contain PII/payment data |
| `order.id`/`customer.id` | Strictly evaluate | Can identify users and raise cardinality |

Do not put trace IDs into metric labels because every trace produces a new value, exploding time series. If the backend supports exemplars, use exemplars to connect metric samples to traces. Do not copy every baggage entry into MDC/JSON because baggage can hold caller-controlled values, PII, or oversized strings. Enforce access control, retention, masking/redaction, and auditing.

## 11. Testing Trace/Span Correlation in MDC

You should test that the tracing context creates IDs, MDC receives them, the logger writes them, and the context is cleaned up.

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class TraceMdcIntegrationTest {
    @Autowired
    Tracer tracer;

    @Test
    void exposesTraceAndSpanIdsWhileSpanIsActive() {
        Span span = tracer.nextSpan().name("test-operation");
        try (Tracer.SpanInScope scope = tracer.withSpan(span.start())) {
            assertNotNull(MDC.get("traceId"));
            assertNotNull(MDC.get("spanId"));
        } finally {
            span.end();
        }
    }
}
~~~

This is an integration test requiring tracing auto-configuration and logging correlation integration in the test context. MDC key names must be verified against your implementation/version. Add tests with a Logback appender to capture events, verify fields in output, and confirm cleanup once the scope closes. Create parent/child spans to verify identical Trace ID, distinct Span IDs, and parent restoration.

### 11.1. Testing Async Cleanup

Use a single-worker executor to force thread reuse:
1. Task A runs inside span A and logs IDs.
2. Task A finishes, scope closes.
3. Task B without context must not carry A's IDs.
4. Task C with span C logs C's IDs.
5. Repeat to catch leaks or races.

## 12. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Logs lack `traceId`/`spanId` | No active span or logging integration inactive | Check tracing bridge, instrumentation, and MDC |
| Only `traceId` present, `spanId` missing | Wrong pattern/key mapping or no current span | Inspect MDC map and active scope |
| All logs share the same `spanId` | Statically copied ID or MDC not updated per child scope | Check integration, remove manual MDC management |
| `spanId` empty in async | Context not captured/restored | Configure executor/context propagation |
| Logs carry previous request's `traceId` | `ThreadLocal`/MDC not cleaned up | Check scope close, `finally`, and thread reuse |
| `traceId` present but backend empty | Sampling drop or export/backend error | Check sampling, exporter, Collector |
| Trace exists but log query misses it | Encoder omits MDC field or collector drops field | Inspect JSON and logs pipeline |
| IDs appear twice | Both default pattern and custom pattern add correlation | Keep only one configuration |
| Wrong Trace ID across services | Propagation/context extraction error | Check `traceparent` and HTTP instrumentation |
| IDs lost in Reactor | Context not propagated across reactive chain | Check Reactor/Micrometer integration |
| Logs expose baggage/PII | Correlation map too broad | Allowlist, redaction, and incident review |

Diagnostic workflow: verify the request has a server span; check the current span inside scope; inspect the MDC map before the logger call; inspect the event after the encoder/appender; verify async context propagation and cleanup; look up the Trace ID in the backend; finally check whether the log collector preserves the fields. Never generate a fake UUID for `traceId` to mask a propagation bug.

## 13. Production Checklist

| Criterion | Required evidence |
| --- | --- |
| Tracing configured | Spring Boot Actuator, Micrometer Tracing bridge, and tracer active |
| Trace/span IDs in logs | Actual log events carry correlation fields |
| Consistent MDC keys | `traceId`/`spanId` match backend query schema |
| No fake IDs | IDs originate from active tracing context |
| Correct parent/child context | Logged `spanId` switches properly when child scope is active |
| Proper scope cleanup | No stale context remains once scope closes |
| Async propagation tested | Executor/Reactor/messaging have context integration |
| Separate JSON fields | Backend parses `traceId`/`spanId` |
| Log security | No tokens, cookies, PII, or payloads |
| Metric cardinality controlled | Trace ID/Span ID excluded from metric labels |
| Sampling/export monitored | Awareness that traces may drop even when logs carry IDs |
| Access/retention policy | Authorization and retention limits in place |

## 14. Lab Exercise: Investigating an Error from Log to Trace

**Scenario:** users report slow order creation. Logs from `order-service` and `inventory-service` arrive at the log backend; traces go to an OTLP Collector. Operations wants to jump from a log line straight to the exact span and view the full trace.

**Tasks:**
1. Add Actuator and the OpenTelemetry Micrometer Tracing bridge per the BOM.
2. Configure HTTP server/client instrumentation and the OTLP exporter to Collector.
3. Verify Logback correlation includes both `traceId` and `spanId`.
4. Create a custom Observation `orders.checkout` and call `inventory-service` via an instrumented HTTP client.
5. Emit logs in the controller, business service, and client call; verify a shared Trace ID and Span ID matching the current span.
6. Use structured JSON or a pattern to output `traceId`/`spanId` as separate fields.
7. Start a child span and verify `spanId` changes in logs; after the child scope ends, the parent `spanId` is restored.
8. Offload a task to an executor, configure context propagation, and verify MDC on the worker.
9. Run a subsequent task on the same thread with no context; confirm no IDs from the prior task remain.
10. Query log events by Trace ID, open the trace backend, and locate the span by Span ID.
11. Lower sampling to observe a case where logs have a trace ID but the trace is not stored; explain why.
12. Verify logs contain no tokens, emails, or raw request bodies, and Trace ID does not appear in metric labels.

**Expected deliverables:** correlation logging configuration, sample log events with trace/span IDs, multi-span trace across both services, MDC scope/async cleanup tests, and a log-to-trace runbook.

## 15. Takeaways

**Trace ID** links spans in a trace; **Span ID** identifies a specific operation. **MDC** enables the logging framework to attach both values to each log event. In Spring Boot, Micrometer Tracing and its logging integration manage correlation fields according to the active span, while Logback/structured logging controls how they are emitted.

MDC does not create traces and does not replace W3C propagation or OTLP export. Scopes must be restored when spans end; async, executors, and Reactor require proper context propagation to avoid losing or leaking IDs across requests. Use Trace ID to pivot from logs to the trace backend and Span ID to locate the operation; protect logs with allowlists, redaction, and retention, and never use IDs as metric labels.

**References:**
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [SLF4J — MDC](https://www.slf4j.org/manual.html#mdc)
- [Logback — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
