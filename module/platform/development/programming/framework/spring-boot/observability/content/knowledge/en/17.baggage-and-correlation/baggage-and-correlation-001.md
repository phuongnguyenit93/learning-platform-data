# What Is Baggage? Context Propagation and Log Correlation in Spring Boot

An order creation request starts at `order-service`, calls `inventory-service`, and then proceeds to `payment-service`. The Trace ID helps services recognize spans belonging to the same trace, but sometimes the operations team also needs certain contextual information throughout the journey, such as the processing channel `web` or `batch`, a normalized region code, or a business flow type. **Baggage** is a mechanism for carrying those contextual key-value pairs across service boundaries so downstream components can use them when configured.

In the **SPRING_BOOT_OBSERVABILITY** module, baggage should be understood alongside Micrometer Observation, metrics, logs, and distributed tracing. Trace context identifies and connects spans; baggage carries a small amount of additional context; span attributes describe a single span; MDC helps bring correlation fields into logs. They are related, but they do not replace one another. Baggage propagation must also strictly control sensitive data, header size, allowlists, and cardinality.

This lesson belongs to the **Baggage and Correlation** chapter and focuses on the foundational concept of **what baggage is**, how W3C Baggage is propagated, Spring Boot/Micrometer Tracing integration, log correlation, testing, and troubleshooting incidents in production environments.

## Learning Objectives

After this lesson, you will be able to:

1. Explain baggage and distinguish it from trace ID, span ID, span attributes, MDC, and metric labels.
2. Describe how baggage is encoded into the HTTP `baggage` header according to W3C Baggage.
3. Configure which baggage fields are allowed to propagate and which fields are included in logging correlation.
4. Create and read baggage in a Spring Boot application using Micrometer Tracing.
5. Test propagation between two services, including across HTTP clients/servers or executors.
6. Design allowlists, size limits, lifetimes, and safe data policies.
7. Know when to use baggage, span attributes, logs, or metrics to answer an operational question.

## 1. What Is Baggage?

**Baggage** is a set of **key-value** pairs attached to a trace context that can be propagated across process/service boundaries. Components receiving the context can read baggage to enrich processing, logs, or spans by design.

Example of an order flow:

~~~text
order-service
  traceId = 4bf92f3577b34da6a3ce929d0e0e4736
  baggage:
    orders.channel = web
    deployment.region = ap-southeast
        |
        | HTTP request + trace context + baggage
        v
inventory-service
  reads orders.channel = web
        |
        | HTTP request + trace context + baggage
        v
payment-service
  reads orders.channel = web
~~~

Two services can use the same baggage value while processing a trace. However, **baggage is not automatically written to logs, metrics, or every span**. Explicit configuration or code is required for each purpose. If the receiving service lacks a corresponding baggage propagator/accessor, or if the field is not on the allowlist, the value may not arrive.

### 1.1. Why Do We Need Baggage?

Some small pieces of contextual information can be useful across multiple services:

| Example key | Example value | Purpose |
| --- | --- | --- |
| `orders.channel` | `web` or `batch` | Distinguish the processing flow type |
| `deployment.region` | `ap-southeast` | Identify the normalized region |
| `experiment.variant` | `control` or `treatment` | Support analysis of an approved experiment |
| `tenant.tier` | `standard` or `premium` | Group policies when permitted |
| `workflow.name` | `order-create` | Business flow context with a finite set of values |

These examples should only be propagated when downstream truly needs them. Do not use baggage as a store for request data, payloads, or long-lived business state.

### 1.2. Baggage Is Not a Trace ID

**Trace ID** is the identifier of a trace. It helps the backend find all spans belonging to the same trace. **Baggage** is additional data that can be propagated alongside the trace context. The Trace ID is usually generated and managed by the tracing system; baggage is usually set by code or policy.

Example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: orders.channel=web,tenant.tier=standard
~~~

The two headers serve different roles:

- `traceparent` contains the version, trace ID, parent ID, and trace flags to link spans.
- `baggage` carries key-value pairs allowed to be propagated downstream.

If there is only baggage without a trace context, the system can still read the baggage information, but it cannot build the parent-child span tree from it alone. Conversely, a trace can work completely fine without baggage.

## 2. Baggage, Span Attributes, MDC, and Metric Labels

These are four concepts that are very easy to confuse:

| Concept | Where it lives | Purpose | Automatically propagated across services? |
| --- | --- | --- | --- |
| **Trace context** | Tracer context, usually serialized as `traceparent` | Link spans | Yes, when the propagator and HTTP/messaging instrumentation are active |
| **Baggage** | Context attached to the trace, serialized as `baggage` | Propagate selected contextual key-values | Yes, when the field is configured/allowed and the propagator is active |
| **Span attributes** | Metadata of a single span | Describe a specific operation | Not by default; only when code/propagation explicitly adds them |
| **MDC/log correlation** | Logging context of the current execution | Record trace/span ID or correlation fields in logs | Not guaranteed automatically; depends on logging integration and context propagation |
| **Metric labels** | Identity of a time series | Group aggregated data | Not propagated with the trace; attached by instrumentation/registry |

For example: `orders.channel=web` can be set as baggage so downstream services can read it. If you want to search by it in the trace backend, code can copy it to a span attribute. If you want it to appear in logs, configure correlation fields/MDC. If you want to include it in metrics, evaluate whether it has a low, bounded, and stable set of values.

**Do not copy all baggage everywhere.** Each destination has different requirements and risks. A baggage field that is safe to propagate internally is not necessarily a good metric label or allowed to be emitted into logs.

### 2.1. Baggage Does Not Replace Span Attributes

Baggage expresses context that multiple services may need to read; span attributes describe a single span. Baggage added after a span has started does not necessarily appear on that span. To put metadata into a trace, attach the attribute to the appropriate span or use suitable instrumentation/conventions.

### 2.2. Baggage Does Not Replace MDC

MDC is a logging mechanism for attaching values to log events. Some integrations can automatically add trace ID/span ID to MDC, and Spring Boot can map configured correlation fields from baggage. If logging occurs outside an active context, or if async context is lost, MDC may miss the expected values.

### 2.3. Baggage Is Not a Metric Label

A baggage field with many distinct values such as request ID, customer ID, or email is not suitable to become a metric label. It can cause the number of time series to grow with traffic and leak sensitive data. Metrics should use a small set of values such as `orders.channel=web|batch`; querying a specific request should rely on trace ID/log correlation and permitted data.

## 3. W3C Baggage and HTTP Propagation

W3C Baggage defines how to serialize a list of key-value pairs into the HTTP `baggage` header. An example:

~~~http
baggage: orders.channel=web,tenant.tier=standard
~~~

When a service receives the header and makes a downstream request with propagation, allowed baggage fields can continue appearing in the next request. This is a **propagation** mechanism, not an automatic mechanism for sending data to the trace backend.

### 3.1. Three-Service Example

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Payment as payment-service
    Client->>Order: POST /orders
    Note over Order: Create trace context
    Order->>Order: Attach baggage orders.channel=web
    Order->>Inventory: HTTP + traceparent + baggage
    Note over Inventory: Extract context and read baggage
    Inventory->>Payment: HTTP + traceparent + baggage
    Note over Payment: Read orders.channel=web
    Payment-->>Inventory: Result
    Inventory-->>Order: Result
    Order-->>Client: Response
~~~

In the example, if both the HTTP client and server are instrumented and the W3C propagator is used, trace context and baggage can flow across services. If one service strips headers or uses a different propagator without conversion, the propagation chain can break.

### 3.2. Multiple Values and Encoding

W3C Baggage supports a list of members with its own syntax, including rules for characters, encoding, and optional metadata. Simple examples are usually enough for illustration:

~~~http
baggage: orders.channel=web,experiment.variant=treatment
~~~

In real environments, **do not manually concatenate header strings using arbitrary string addition**. Use the tracing stack's baggage/propagator API to handle encoding, escaping, multiple headers, and size limits properly.

A baggage value may be encoded when passing over HTTP; therefore, do not assume the received string is always byte-for-byte identical to the original string. Check the parsed value in the receiving service.

### 3.3. Baggage Is Not Trusted Data

Headers sent by clients can be forged. A service should not trust `tenant.tier=premium` merely because it appears in baggage. If information affects permissions, pricing, tenant isolation, or security decisions, it must be verified from an authoritative source; baggage is only a vehicle for carrying context.

In particular, do not use baggage as a mechanism for passing authorization, session, or security principal data. Do not allow external requests to arbitrarily specify keys/values and propagate them across the entire system.

## 4. Spring Boot and Micrometer Tracing

Spring Boot integrates Micrometer Observation and Micrometer Tracing. With an appropriate tracing bridge, an application can access the tracer/baggage API and use Spring Boot properties to specify which fields are propagated or correlated.

Illustrative dependencies with Spring Boot 3.x and the OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Dependency versions should follow the project's BOM. The properties below are based on Spring Boot 3.x configuration groups; verify them against your exact application version when upgrading.

### 4.1. Selecting Baggage Fields to Propagate

Example `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
    baggage:
      remote-fields:
        - orders.channel
        - deployment.region
      correlation:
        fields:
          - orders.channel
          - deployment.region
~~~

Explanation:

- `management.tracing.baggage.remote-fields` declares the baggage fields allowed to be sent across service boundaries according to your Spring Boot version's support.
- `management.tracing.baggage.correlation.fields` declares the baggage fields to include in logging correlation/MDC according to the integration configuration.
- `sampling.probability` is an example sampling probability; **trace sampling does not determine whether baggage can be read in code**, though it can affect exported span data.

The two lists serve two different purposes: **remote propagation** and **log correlation**. Adding a field only to the remote list does not mean it automatically appears in logs. Adding it only to correlation fields does not mean it will be sent to the next service.

Do not propagate every field just because the framework allows it. Keep the allowlist small, stable, owned, and backed by a clear operational reason.

### 4.2. Accessing Baggage via the Micrometer Tracer API

With Micrometer Tracing, you can create baggage within the scope of an operation:

~~~java
package com.example.orders.tracing;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class OrderChannelService {
    private final Tracer tracer;

    public OrderChannelService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void processWebOrder() {
        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("orders.channel", "web")) {
            processOrder();
        }
    }

    private void processOrder() {
        // Call appropriately instrumented beans/dependencies.
    }
}
~~~

`createBaggageInScope` creates baggage in the current scope, and the scope closes upon exiting `try-with-resources`. This prevents context values from leaking into subsequent operations when threads are reused.

This is an example of the Micrometer Tracing API; how baggage is propagated depends on the bridge, propagator, and `remote-fields` configuration. If the exact API differs in your version, rely on the contract of the Micrometer Tracing version managed by Spring Boot.

### 4.3. Reading Baggage in a Downstream Service

When the receiving service has extracted baggage into the context and the application has an appropriate tracer, you can read the current value:

~~~java
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;

public String currentChannel(Tracer tracer) {
    Baggage baggage = tracer.getBaggage("orders.channel");
    return baggage == null ? "unknown" : baggage.get();
}
~~~

This snippet illustrates reading current baggage; check the return type/API on your project's Micrometer Tracing version. **Do not use baggage values to grant permissions** or replace authentication. If the field is absent, handle fallback explicitly instead of assuming the value always exists.

### 4.4. Using @ConfigurationProperties for Business Allowlists

Beyond the framework's propagation list, the application should manage which fields are allowed to be created at the business layer. Example:

~~~java
package com.example.orders.tracing;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.Set;

@ConfigurationProperties(prefix = "app.observability.baggage")
public record BaggagePolicy(Set<String> allowedChannels) {
    public BaggagePolicy {
        allowedChannels = allowedChannels == null
                ? Set.of("web", "batch")
                : Set.copyOf(allowedChannels);
    }
}
~~~

This example only illustrates a channel value policy; register configuration properties according to your application's approach (e.g., `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`). Do not put arbitrary key/value names from requests into baggage.

## 5. Baggage Scope, Threads, and Async Processing

Baggage is usually tied to the current tracing context. If a request is processed synchronously, the scope can be used across nested calls. When switching threads, executors, or reactive contexts, you must ensure the context is propagated and restored properly.

### 5.1. Avoiding Baggage Leaks on Thread Reuse

Unsafe lifecycle example:

~~~java
// Wrong idea: setting context without ensuring the scope is closed.
tracer.createBaggageInScope("orders.channel", "web");
executor.execute(this::processOrder);
~~~

Thread pools reuse threads. If the scope is not closed or the context is not restored, a subsequent operation may see values from the previous operation. Use `try-with-resources` and framework-supported context propagation mechanisms.

### 5.2. ContextPropagatingTaskDecorator

With Spring Framework 6.1+ and Micrometer Context Propagation, a Spring executor can use `ContextPropagatingTaskDecorator` when the necessary context accessors are registered:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerConfiguration {
    @Bean
    ThreadPoolTaskExecutor baggageAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

The decorator helps capture/restore supported context across tasks. Do not assume it automatically propagates every type of custom state; verify the actual tracer, baggage accessor, Spring version, and executor.

### 5.3. Reactor and Messaging

Reactor has its own execution context and can switch threads. Use context propagation mechanisms suited to Spring/Reactor rather than relying directly on thread-locals. With Kafka/RabbitMQ, producer/consumer instrumentation or message headers need to support injecting/extracting trace context and baggage.

A batch consumer may process multiple messages arriving from multiple traces. A single baggage context cannot always represent every message in a batch; clearly define which context to select, whether to process each message individually, or whether to use span links. Do not arbitrarily mix baggage from one message into another.

## 6. Baggage and Log Correlation

A practical benefit of baggage is carrying selected allowed context downstream, then bringing it into log correlation to make log filtering easier. However, trace ID/span ID remain the primary identifiers for opening a specific trace; baggage is supplementary information.

Example structured log:

~~~text
2026-11-22T09:15:10Z INFO service=inventory-service
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=00f067aa0ba902b7 orders.channel=web event=reservation_started
~~~

In Spring Boot, logging integration can put trace ID/span ID into MDC/patterns. Baggage correlation fields can add configured fields. The final format depends on the logging framework and pattern/layout.

### 6.1. Correlation in Logging Patterns

Example with a Logback pattern:

~~~yaml
logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-},channel=%X{orders.channel:-}]"
~~~

This is an illustrative pattern. Baggage keys in MDC may be normalized differently depending on the integration; inspect a real log event to confirm the exact MDC key name. Do not blindly put baggage values into patterns indiscriminately, as this could log sensitive data.

### 6.2. Trace ID and Baggage Solve Two Different Query Patterns

| Need | Appropriate data |
| --- | --- |
| Open the trace of an exact request | Trace ID |
| Identify a specific span inside a trace | Span ID |
| Filter logs for the operation being processed | Trace/span ID and allowed log fields |
| Group web/batch flows across services | Normalized baggage field, if needed |
| Analyze request counts by channel | Low-cardinality metric label |
| Find a request by order ID | Protected log/tracing search; do not use a metric label |

Do not use baggage as a unique lookup key if a single value can apply to thousands of requests. Baggage is shared context, not guaranteed to be unique.

## 7. Baggage, Cardinality, and Security

Baggage can be serialized into HTTP headers and transmitted through multiple services, proxies, gateways, and logs. Putting a field into baggage can widen the data exposure surface. Therefore, **allowlists and limits** are required.

| Data | Assessment | Action |
| --- | --- | --- |
| `orders.channel=web` | Low set of values, non-sensitive in the example | Can allow if downstream needs it |
| `deployment.region=ap-southeast` | Normalized value | Can allow per policy |
| `experiment.variant=treatment` | Analytical context | Propagate only when approved |
| Customer email | Personal data | Do not propagate by default |
| Access token/cookie/password | Authentication secrets | Never put in baggage |
| Raw order ID/request ID | Many values, potentially identifying | Restrict; do not propagate widely by default |
| Request/response body | Large, may contain sensitive data | Do not propagate in baggage |
| Security role/tenant privilege from client | Can be forged | Do not use as basis for authorization |

### 7.1. Baggage Can Increase Header Size

HTTP headers have limits at clients, proxies, load balancers, and servers. If you add too many key-value pairs or very long values, requests may exceed limits and be rejected (e.g., HTTP 431 or gateway errors depending on infrastructure).

Best practices:

1. Keep the number of fields small; use only when downstream truly needs them.
2. Set limits on key/value length and total baggage size.
3. Do not transmit bodies, large JSON, or item lists.
4. Avoid duplicating the same data across multiple headers.
5. Check behavior when gateways strip or truncate headers; do not assume every proxy preserves all metadata.

### 7.2. Trust Boundaries and Header Injection

An external client can send on its own:

~~~http
baggage: tenant.tier=premium,orders.channel=internal
~~~

If the backend trusts these values to change pricing, permissions, or returned data, the system can be abused. At the trust boundary:

- Accept only baggage fields that are genuinely allowed.
- Strip or overwrite client-supplied fields if they are untrusted.
- Re-determine values from an authoritative source.
- Do not propagate uncontrolled headers verbatim.
- Do not use baggage in place of authentication, authorization, or tenant isolation.

**Baggage is untrusted metadata for security decisions**, unless independently verified under a trusted contract.

### 7.3. Cardinality and Cost

Baggage does not directly create time series. However, if every service copies baggage values into span attributes, logs, or metric labels, costs can rise:

- High-cardinality span attributes increase trace storage and indexing costs.
- Copying baggage into MDC increases log volume and data exposure risk.
- Putting baggage into metric labels can generate large numbers of series.

For example, `orders.channel=web|batch` has a small value set; `request.id` can change on every request. If you need to query a specific request, use trace ID or log correlation instead of metric labels. There is no need to send request ID via baggage just to recreate a trace ID.

## 8. When to Use Baggage and When Not To

| Requirement | Usually appropriate choice | Why |
| --- | --- | --- |
| Link spans belonging to the same request | Trace context | This is the purpose of trace/span IDs |
| Propagate normalized channel downstream | Baggage | Multiple services may need to read the same context |
| Describe an error of a single span | Span event/status/attributes | Metadata belonging to a specific operation |
| Record trace ID in logs | Logging correlation/MDC | Helps find traces from logs |
| Compute request rate by channel | Low-cardinality metric label | Can be aggregated and alerted on |
| Transmit authentication tokens | Dedicated security protocol/header | Baggage is not a channel for secrets |
| Transmit entire request body | Do not use baggage | Too large and sensitive data risk |
| Carry business state across multiple days | Database/event/message payload per contract | Baggage is non-durable and trace-bound |

A useful rule: only put a value into baggage if it is **small, stable, needed downstream, safe across trust boundaries, and valid for the lifetime of the trace**. If the question pertains only to a single span, a span attribute may be more suitable. If aggregate statistics are needed, use metrics.

## 9. Testing Baggage and Correlation

Testing should be divided into three layers: creating/reading baggage in-process, propagation over HTTP, and log correlation. Testing a baggage API alone does not prove headers were transmitted or MDC was configured.

### 9.1. Baggage Scope Integration Test

With a real tracing implementation configured in tests, you can verify scope behavior:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class BaggageScopeTest {
    @Autowired
    private Tracer tracer;

    @Test
    void restoresBaggageAfterScopeCloses() {
        Baggage before = tracer.getBaggage("orders.channel");
        String previous = before == null ? null : before.get();

        try (BaggageInScope ignored =
                     tracer.createBaggageInScope("orders.channel", "web")) {
            assertEquals("web", tracer.getBaggage("orders.channel").get());
        }

        Baggage after = tracer.getBaggage("orders.channel");
        assertEquals(previous, after == null ? null : after.get());
    }
}
~~~

This is an **integration test that requires tracing auto-configuration and an appropriate exporter/tracer bean in the test context**. It verifies that closing the scope restores the previous baggage value (or leaves no value if none existed before). You can configure an appropriate in-memory/no-op exporter to avoid depending on an external Collector; the test's goal is context lifecycle, not testing OTLP export.

### 9.2. Testing Propagation over HTTP

An integration test with two services or a test server should:

1. Create a parent trace in the sending service.
2. Create the baggage field `orders.channel=web` within the active scope.
3. Send the request using a tracing-instrumented HTTP client.
4. On the receiving server, check that `traceparent` and `baggage` appear according to the allowlist.
5. Read baggage via the tracing context API on the receiving side; do not just compare raw headers.
6. Verify a consistent trace ID and correct parent span ID if HTTP tracing is configured.
7. Verify that fields outside the allowlist are not propagated.

Avoid hard-coding span IDs since they are typically generated randomly. Assertions should check ID relationships and parsed baggage values.

### 9.3. Testing Log Correlation

To verify MDC:

- Create an active span/baggage in the test logging context.
- Emit a log event.
- Capture the event via an appender or logging test facility.
- Check that trace ID/span ID and configured correlation fields are present.
- Close the scope and verify the next event does not carry the stale context.
- Verify logs do not contain tokens, emails, or non-allowlisted fields.

### 9.4. Testing Async Propagation

Run a task on an executor that reuses threads:

1. The first request creates baggage `orders.channel=web` and submits a task.
2. The task reads the correct value when context propagation is configured.
3. The scope closes after the task.
4. The next task has no baggage if none was passed.
5. Run an additional test without the decorator to demonstrate the context-loss bug.

This catches both failures: **failing to propagate context** and **leaking context to other tasks**.

## 10. Troubleshooting: Baggage Does Not Reach Downstream or Does Not Appear in Logs

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Downstream service does not see field | Field is not in remote allowlist | Check `management.tracing.baggage.remote-fields` |
| `baggage` header does not appear | No active context, different propagator, or uninstrumented HTTP client | Check tracer and client/server instrumentation |
| Header is present but API reads null | Field parsing/extraction not performed or key name mismatch | Check receiving context and how baggage is read |
| Logs lack baggage field | Correlation fields not configured or MDC integration inactive | Check `management.tracing.baggage.correlation.fields` and log pattern |
| Logs have trace ID but no baggage | Trace correlation works, baggage correlation does not | Verify the two separate configurations |
| Baggage lost when running `@Async` | Context not captured/restored | Check `TaskDecorator`/context propagation |
| Baggage disappears at a gateway | Proxy/ingress strips or limits headers | Check network path and header limits |
| Client-sent field trusted downstream | Trust boundary lacks filtering/verification | Strip/overwrite field, verify data source |
| HTTP 431 / header too large | Too much baggage or values too long | Reduce allowlist, length, and total payload |
| Metrics cardinality increases | Baggage copied into metric labels | Fix instrumentation, use low-cardinality tags |
| Traces missing even though baggage arrives | Sampling/exporter/Collector issue | Check tracing pipeline separately |
| Baggage on one span but not another | Span attributes are not inherited from baggage | Explicitly attach attributes on needed spans |

### 10.1. Diagnosing in Order

1. **At creation:** does code create baggage within an active scope?
2. **In context:** can the tracer read the value right after creation?
3. **Outbound:** is the remote field allowlisted and injected by the propagator?
4. **Over the network:** do proxies/gateways preserve the header?
5. **Inbound:** does the server extract baggage with the matching propagator?
6. **In logs:** is the correlation field mapped into MDC/layout?
7. **At the trace backend:** if a span attribute is needed, does code/handler attach the attribute to the right span?

Do not use the presence of the `baggage` header to conclude that the trace exporter succeeded. Exporting spans is a separate pipeline.

## 11. Production Checklist

| Criterion | Required evidence |
| --- | --- |
| Each baggage field has a clear purpose | Downstream truly needs to read the field |
| Small remote allowlist | Propagated fields explicitly configured |
| Separate correlation allowlist | Only approved fields are logged |
| Normalized values | No arbitrary client strings accepted |
| Trust boundaries handled | Strip/overwrite and verify external data |
| No secrets/PII | Security review and log/header tests |
| Reasonable header size | Limits on key/value/total baggage |
| Thread/reactive context tested | Tests for async, executor, or Reactor |
| No dynamic baggage in metrics | Low metric label cardinality |
| Span attributes attached intentionally | Do not expect baggage to become attributes automatically |
| Exporter and propagation separated | Tests for both trace context and OTLP export |
| Log correlation does not leak context | Tests for scope closing and thread reuse |
| Documentation/API versions verified | Configuration matches active Spring Boot/Micrometer version |

## 12. Hands-On Exercise: Propagating Channel and Correlating Logs Across Two Services

**Scenario:** `order-service` receives requests from web or batch, then calls `inventory-service`. The operations team wants to filter logs by channel without putting order ID or personal data into metrics.

**Tasks:**

1. Install Actuator and Micrometer Tracing with an appropriate bridge; ensure HTTP client/server are instrumented.
2. Configure `management.tracing.baggage.remote-fields` to allow only `orders.channel` and `deployment.region`; configure correlation fields separately.
3. Verify incoming code normalizes channel to `web` or `batch` rather than taking raw client headers.
4. Use `tracer.createBaggageInScope("orders.channel", channel)` during processing and close the scope with `try-with-resources`.
5. Send an HTTP request from `order-service` to `inventory-service`, verifying `baggage` and `traceparent` are propagated per contract.
6. In `inventory-service`, read the baggage value and write a log containing the allowed correlation field.
7. Verify logs contain trace ID/span ID and channel, but no tokens, emails, request bodies, or order IDs.
8. Add a test case where the client sends `orders.channel=internal`; prove the application does not trust raw external baggage.
9. Run tasks on an executor with and without context propagation, verifying baggage reaches the right task and does not leak to subsequent tasks.
10. Verify `orders.channel` does not become a metric label if the value set or policy is unsuitable; design a dedicated metric only with a finite value set when analytical need exists.

**Expected deliverables:** allowlist configuration, code creating/reading baggage, cross-service trace, correlated logs, unit/integration tests, and notes on trust boundaries, header size, and async propagation.

## 13. Key Takeaways

**Baggage is contextual key-value data that can be propagated with the trace context** so downstream services can use it when needed. It differs from `traceparent` (identifying/linking spans), span attributes (describing a span), MDC (log context), and metric labels (grouping time series).

In Spring Boot/Micrometer Tracing, only propagate baggage using an **allowlist**, enforce size limits, and normalize values. Never include secrets, PII, or data clients can forge for security decisions. Only put fields into logs or span attributes intentionally; do not turn baggage into high-cardinality metric labels.

For reliable correlation, verify **baggage creation, propagation, extraction, MDC/logging, async context propagation, and tracing export** separately. Metrics show system-wide trends, trace IDs open a request's trace, baggage adds controlled context, and logs preserve events for investigation.

**References:**

- [W3C — Baggage](https://www.w3.org/TR/baggage/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/observability.html)
