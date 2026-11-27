# Baggage in MDC

A request arriving at Order Service carries customer region and sales channel information. Order Service calls Inventory Service and then Payment Service. When investigating a transaction, the operations team wants to locate logs belonging to the same trace and filter logs by region or channel. Trace ID groups spans of a journey; business metadata that needs to cross services is typically passed via **baggage**. For that metadata to appear in logs, we need to configure **correlation with MDC**.

The **Baggage in MDC** lesson belongs to the **Baggage and Correlation** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module aims at setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments. This lesson focuses on the relationship between **W3C Baggage**, **Micrometer Tracing**, and **Mapped Diagnostic Context (MDC)**.

> **Distinguish from the start:** Trace ID/Span ID identify traces and spans. Baggage carries contextual key-value pairs across service boundaries. MDC is a data area bound to the current logging context, typically emitted as fields in log patterns or JSON. Baggage **does not automatically enter MDC** in every application; appropriate correlation fields must be configured. Nor is MDC a protocol for transmitting data over HTTP.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain baggage and distinguish it from Trace ID, Span ID, span attributes, MDC, and business identifiers.
2. Read the W3C `baggage` header and understand how metadata is propagated across multiple services.
3. Configure Spring Boot/Micrometer Tracing to allow remote baggage fields and put selected baggage fields into MDC.
4. Read baggage from code using the Micrometer Tracing API and create baggage in the proper scope.
5. Understand the lifecycle of correlation fields in MDC and how log patterns/structured logging display them.
6. Control allowlists, cardinality, length, sensitive data, and trust boundaries for baggage.
7. Distinguish baggage propagation from internal context propagation across thread pools/Reactor.
8. Test baggage across HTTP clients/servers and in logs.
9. Investigate cases where baggage is in the request yet missing from MDC/log backends.

## 2. How Do Baggage, Trace Context, and MDC Differ?

| Component | What does it hold? | Purpose | Scope |
|---|---|---|---|
| **Trace context** | Trace ID, current Span ID, parent relationship, and flags | Link spans in a distributed trace | Across services via tracing propagation |
| **Baggage** | Key-value pairs like `tenant-region=apac`, `channel=mobile` | Carry contextual metadata across services | Across services when fields are allowed to propagate |
| **MDC** | Fields like `traceId`, `spanId`, `tenant-region` | Attach data to the current log event | Usually per thread/logging scope |
| **Span attributes** | Metadata of a specific span | Describe a span for trace querying | Bound to a span |
| **Metric tags** | Finite-cardinality groupings like `outcome=approved` | Aggregate measurements into time series | Per meter ID |
| **Business ID** | `orderId`, `invoiceId`, transaction reference | Identify business entities | Follows business lifecycle |

For example, a request has Trace ID `T` and baggage `tenant-region=apac`. Passing through Order and Inventory, the Trace ID stays the same if context propagates properly; baggage can travel in headers. Each service creates its own span, while loggers can place trace/span IDs along with selected baggage into MDC.

~~~mermaid
flowchart TD
    A["Inbound HTTP request"] --> B["Extract trace context + baggage"]
    B --> C["Current tracing / observation context"]
    C --> D["Baggage fields"]
    C --> E["Trace ID / Span ID"]
    D --> F["MDC correlation configuration"]
    E --> F
    F --> G["Log event"]
    C --> H["Instrumented HTTP client"]
    H --> I["Inject traceparent + allowed baggage"]
    I --> J["Downstream service"]
    G --> K["Log appender / collector"]
~~~

MDC is the presentation layer in logs; baggage is context data that can be injected into network transport protocols. Adding a key only to MDC will not send it to downstream services. Receiving baggage alone will not make the logger print the field unless correlation is configured.

## 3. What Is W3C Baggage?

W3C Baggage defines an HTTP header named `baggage`, containing key-value members and optional properties. Example:

~~~http
baggage: tenant-region=apac,channel=mobile,experiment=checkout-v2
~~~

The members above are illustrative metadata. A service can use them to pick appropriate configurations or add correlation details to logs. Baggage does not replace `traceparent`; the two headers have different purposes.

| Header | Example | Meaning |
|---|---|---|
| `traceparent` | `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` | Trace ID, parent span ID, and flags |
| `tracestate` | vendor-specific state | Interoperability metadata across tracing vendors |
| `baggage` | `tenant-region=apac,channel=mobile` | Propagated context metadata |

Baggage can be forwarded across many services; any field put into it can be seen by multiple components in the call chain. Do not treat baggage as a private area or secret channel.

### 3.1 Basic Rules When Designing Baggage

- Use stable, clearly named keys without per-request IDs.
- Keep values short and bounded; avoid stuffing large JSON or request payloads.
- Propagate only fields downstream needs; do not forward all inbound headers.
- Never put passwords, access tokens, API keys, session cookies, payment data, or unjustified PII.
- Authentication and authorization must rely on trusted security mechanisms; caller-sent baggage is not proof of permission.
- Control key count, total size, and W3C encoding alongside proxy/gateway limits.
- Treat baggage received from external boundaries as untrusted metadata.

### 3.2 Baggage Is Not Span Attributes

A baggage field can propagate across many spans and services; a span attribute describes a single specific span. They can contain the same value when instrumentation intentionally copies it, but they are not automatically the same thing.

~~~text
W3C baggage:
  tenant-region=apac

Span attributes:
  http.request.method=POST
  server.address=inventory-service

MDC:
  traceId=...
  spanId=...
  tenant-region=apac
~~~

Baggage can be an input for creating a span attribute or MDC field when configured. Copy values only when genuinely needed; avoid creating pointless duplicates across every signal.

## 4. What Is MDC and Why Is It Useful for Correlation?

MDC (Mapped Diagnostic Context) is a logging API that lets you attach key-value pairs to the current log event. With SLF4J, code typically uses `org.slf4j.MDC`; Logback provides a compatible MDC implementation.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class CheckoutLogger {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutLogger.class);

    public void process() {
        MDC.put("order-channel", "mobile");
        try {
            log.info("Processing checkout");
        } finally {
            MDC.remove("order-channel");
        }
    }
}
~~~

The log pattern or JSON encoder must be configured to emit that field. MDC does not alter the logger message, does not cross HTTP automatically, and is not durable storage. When a thread finishes or a scope closes, the field must be cleared/restored to prevent leaking to another task.

### 4.1 Trace Correlation and Baggage Correlation

Spring Boot/Micrometer Tracing can automatically put `traceId` and `spanId` into MDC when tracing is configured. Thus logs can display these two fields even if code never calls `MDC.put` manually.

For baggage fields to be added to MDC, select and configure the corresponding correlation fields. Avoid manually copying the same value into MDC if the integration already does so; this can easily create stale data or overwrite the current context.

### 4.2 How to Read a Log Line

Illustrative log example:

~~~text
2026-11-22T10:15:32Z INFO [order-service,4bf92f3577b34da6a3ce929d0e0e4736,a1b2c3d4e5f60718] [tenant-region=apac,channel=mobile] Checkout request accepted
~~~

Interpretation:

- `order-service`: service emitting the log.
- Trace ID: the full trace of the request.
- Span ID: current span active when the log was created.
- `tenant-region`, `channel`: baggage fields placed into MDC per configuration.
- Message: message emitted by the logger.

This is an illustrative format, not a fixed default pattern for every Spring Boot version. The actual log pattern/JSON provider determines field placement and names.

## 5. Configuring Spring Boot to Put Baggage into MDC

Spring Boot with Micrometer Tracing provides properties to specify remote baggage fields and correlation fields:

- `management.tracing.baggage.remote-fields`: baggage fields propagated outside the service.
- `management.tracing.baggage.correlation.fields`: baggage fields placed into MDC for correlation in logs.
- `management.tracing.baggage.local-fields`: baggage fields used only locally, not propagated remotely, when the version supports this property.

Example:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    baggage:
      remote-fields:
        - tenant-region
        - channel
      correlation:
        fields:
          - tenant-region
          - channel
~~~

This configuration means:

1. `tenant-region` and `channel` are baggage fields permitted to be sent downstream.
2. Those same fields will be placed into logging correlation/MDC via Micrometer Tracing integration.
3. `traceId` and `spanId` remain separate tracing correlation; they are not baggage fields.
4. Fields not in the list should not be automatically forwarded merely because they appear in MDC.

**Version note:** property names and binding may change across Spring Boot major versions; check the reference guide for your exact project version. Examples use YAML lists matching the current property model. Do not configure multiple styles simultaneously if they make binding confusing.

### 5.1 Log Pattern to Display MDC Fields

Spring Boot supports logging pattern properties and using MDC in Logback patterns. If you want explicit control over fields, use a matching pattern in `logback-spring.xml`:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level
                [%thread] traceId=%X{traceId:-}
                spanId=%X{spanId:-}
                tenant-region=%X{tenant-region:-}
                channel=%X{channel:-}
                %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This is a minimal Logback example; when using a custom config file, keep your application's required appenders/encoders and check Spring Boot compatibility. `%X{key:-}` reads the MDC key and displays an empty fallback when absent. If using a JSON encoder, map the corresponding fields as JSON properties.

**Do not configure correlation fields without printing them in output.** The field may exist in MDC while the log collector never sees it because the pattern/encoder omits it.

## 6. Creating and Reading Baggage with Micrometer Tracing

With Spring Boot having Micrometer Tracing and a tracer implementation, code can create scoped baggage using `Tracer`. The `createBaggageInScope(name, value)` API sets the field value for the current scope; when the scope closes, the previous state is restored.

Service example:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final Tracer tracer;

    public CheckoutService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void process(String channel) {
        String safeChannel = switch (channel) {
            case "web", "mobile", "partner" -> channel;
            default -> "other";
        };

        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("channel", safeChannel)) {
            log.info("Processing checkout");
            callInventory();
        }
    }

    private void callInventory() {
        // Call a client instrumented by Spring Boot.
    }
}
~~~

With configuration declaring `channel` as a remote field and correlation field, baggage can be propagated and appear in MDC/logs for the matching scope. Code must execute inside a tracing context with a configured tracer; without a tracing implementation, the `Tracer` bean may not exist.

Here `channel` is normalized into a small set. Do not pass arbitrary raw query parameters into baggage, because downstream may log, store, or forward them further.

### 6.1 Reading Current Baggage

The `Tracer` API allows reading baggage by key:

~~~java
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;

public String currentChannel(Tracer tracer) {
    Baggage baggage = tracer.getBaggage("channel");
    return baggage == null ? "unknown" : baggage.get();
}
~~~

Handle the missing-baggage case; do not assume every request arrives from a client supporting W3C baggage. Check the Javadoc for your active Micrometer Tracing bridge and version. Baggage values are input metadata and must be validated/normalized before influencing important logic.

### 6.2 Baggage in Code Is Not Logged Automatically

Creating or reading baggage only provides a context value. Making it appear in logs requires configuring correlation fields and logging output, or managing MDC explicitly with a clear lifecycle if there is a special reason.

Avoid simultaneously doing `createBaggageInScope`, uncleaned `MDC.put`, and another filter manually copying the same key to MDC without defining who owns the value and scope. Overlapping mechanisms can overwrite or leave stale values on worker threads.

## 7. Propagating Baggage over HTTP Downstream

For baggage to travel over HTTP, configure remote fields and use appropriate HTTP client instrumentation/tracing propagation. Spring Boot recommends using Spring-managed builders such as `RestClient.Builder` or `WebClient.Builder` when the stack is configured with Micrometer Tracing.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    public String reserve() {
        return client.post()
                .uri("/api/reservations")
                .retrieve()
                .body(String.class);
    }
}
~~~

When tracing propagation is enabled, client instrumentation can inject `traceparent` and permitted baggage fields into the HTTP request. Replace the illustrative URL with real service discovery/endpoints, timeouts, auth, and error handling.

### 7.1 Illustrative Outbound Headers

~~~http
POST /api/reservations HTTP/1.1
Host: inventory-service
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: tenant-region=apac,channel=mobile
Content-Type: application/json
~~~

- `traceparent` links the trace and specifies the sender's span context.
- `baggage` carries context metadata permitted to propagate.
- The receiving server extracts both contexts per the propagation implementation.
- The server creates a new span with its own Span ID; baggage can populate MDC per correlation config in the receiving service.

Never copy raw headers blindly from callers. Client instrumentation should inject from the current context and propagation config using validated values.

### 7.2 Why Does Baggage Not Appear in Inventory Logs?

Check in order:

1. Did Order Service create/receive the baggage field?
2. Is the field in `remote-fields` or the corresponding propagation config?
3. Is the HTTP client instrumented and injecting W3C baggage?
4. Do proxies/gateways preserve the `baggage` header or strip it per policy?
5. Does Inventory Service extract the matching propagation format?
6. Is the field in `correlation.fields` on Inventory?
7. Does the Logback pattern/JSON encoder print that MDC key?
8. Do async boundaries inside Inventory propagate context to workers?

Checking only the log pattern is not enough; baggage may not have reached the service. Conversely, the header may have arrived yet never been mapped into MDC.

## 8. Baggage and MDC Across Async Tasks

Baggage is typically accessed via the tracing context; logging correlation relies on MDC. Both can be affected when a task switches to another thread.

If an application uses Spring `TaskExecutor` and `@Async`, configuring `ContextPropagatingTaskDecorator` (Spring Framework 6.1+) or an appropriate `ContextSnapshot` restores registered context accessors. This mechanism can include tracing/logging contexts when the corresponding integrations are available.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    TaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.setThreadNamePrefix("async-");
        executor.initialize();
        return executor;
    }
}
~~~

This example requires the corresponding Spring imports and Micrometer Context Propagation in the dependency graph. The decorator only restores registered contexts; it does not automatically turn arbitrary custom ThreadLocals into baggage.

### 8.1 Never Manually Copy Baggage to MDC via Uncleaned ThreadLocals

Wrong:

~~~java
executor.execute(() -> {
    MDC.put("channel", requestChannel);
    sendInvoice();
    // Forgot to restore/clear.
});
~~~

Thread pools reuse workers; the next task may log under the previous request's channel. Use context snapshots/scopes and close scopes on every branch. If managing MDC manually, always save the prior value and restore it in `finally` rather than indiscriminately clearing framework context.

### 8.2 Long-Running Tasks and Baggage Lifetime

For jobs running after an HTTP request has completed, consider creating a new trace and linking to the producer context with a Span Link instead of holding the request scope open. Pass only baggage needed by the job, re-validate when the worker receives it, and do not assume every request metadata item remains valid hours later.

## 9. Correlation Fields and Structured Logging

MDC fields can be emitted via log patterns or JSON. JSON is often convenient for collectors since each key is a distinct field.

Illustrative log record example:

~~~json
{
  "timestamp": "2026-11-22T10:15:32.004Z",
  "level": "INFO",
  "service": "order-service",
  "message": "Checkout accepted",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "a1b2c3d4e5f60718",
  "tenant-region": "apac",
  "channel": "mobile"
}
~~~

This is not a mandatory default Spring Boot schema. Configure structured logging/encoders and verify MDC keys are emitted accurately. If your log backend renames `traceId` to `trace_id`, align queries and correlation UIs accordingly.

### 9.1 Field Names Should Be Stable

| Data | Suggested name | Notes |
|---|---|---|
| Trace ID | `traceId` or `trace_id` | One consistent name across the whole pipeline. |
| Span ID | `spanId` or `span_id` | Keep as string to preserve leading zeros. |
| Tenant region | `tenant-region` or `tenant_region` | Pick a format compatible with logging/collectors. |
| Channel | `channel` | Finite set of values. |
| Environment | `environment` | Usually service config, not mandatory baggage. |

Never store Trace ID/Span ID as integers; they are hex strings that can contain letters and leading zeros. Do not alter data types during JSON parsing.

### 9.2 Correlation in MDC Is Not Global Correlation

MDC exists only in the execution context/logging event where it is set. It does not travel over HTTP automatically; baggage/trace context is the propagation protocol. Do not expect an MDC field in Order Service to magically appear in Inventory Service without corresponding headers and extract/correlation config.

## 10. Allowlists, Security, and Cardinality

Baggage propagates to many downstream services and can appear in logs and trace pipelines. Design it as an inter-service metadata interface, not a scratchpad holding everything.

| Field | Recommendation | Reason |
|---|---|---|
| `tenant-region=apac` | Usable if validated | Short value, useful for routing/diagnostics. |
| `channel=web/mobile/partner` | Usable | Small value set, clear business meaning. |
| `experiment=checkout-v2` | Conditional | Only when downstream needs context; cap cohorts. |
| `userId` | Avoid by default | Identifier/PII, high cardinality. |
| `orderId` | Avoid by default | Nearly unique; use controlled logs/tracing when needed. |
| `authorization token` | Never | Secret credential. |
| `session-cookie` | Never | Sensitive credential. |
| `email` or `phone` | No | Personal data and high cardinality. |
| Raw request body | No | Can be very large, contains secrets/PII. |

### 10.1 Baggage Is Not an Authentication Source

Clients can send on their own:

~~~http
baggage: tenant-region=admin,role=superuser
~~~

Services must never trust that this value has been verified. External callers can craft or alter baggage. If metadata affects routing or sensitive business behavior, services must pull from trusted sources/validate at the boundary and use formal authentication/authorization.

### 10.2 Cardinality and Cost

Baggage is not directly a metric tag, yet it can be copied into span attributes, logs, or metrics. If values change per request and the backend indexes every log field, storage/search costs can still climb.

- Keep baggage keys and values short.
- Limit the remote fields allowlist.
- Do not automatically convert all baggage into span attributes/metric tags.
- Avoid dashboards/metrics keyed by unique IDs.
- Cap baggage member count and total header size per W3C, proxy, and service policies.
- Audit access permissions for logs/traces containing baggage values.

## 11. Baggage Propagation, Sampling, and Exporters

Baggage propagation and trace sampling are two separate concerns:

- Baggage can pass through headers even when the trace is not sampled for span storage.
- A sampled span does not mean all baggage fields are retained in logs/trace backends; configuration may omit them or exporters/processors may filter attributes.
- Logback can write MDC fields under a logging policy independent of trace export.
- Metrics can keep incrementing even when some traces are dropped by sampling.

If logs show `tenant-region=apac` yet the trace backend has no span, inspect sampling, exporters, and retention separately. If the trace has spans yet logs miss `tenant-region`, inspect correlation field config and log encoders. Do not tweak sampling probability to fix an MDC issue.

## 12. Testing Baggage in MDC

Test across multiple layers rather than merely checking property names in YAML.

### 12.1 Checking Properties and Local Output

1. Run Spring Boot with Micrometer Tracing and the intended logging implementation.
2. Set `management.tracing.baggage.remote-fields` to a small allowlist.
3. Set `management.tracing.baggage.correlation.fields` for keys needed in logs.
4. Call an endpoint that creates baggage inside a tracing scope.
5. Check log output for `traceId`, `spanId`, and expected baggage fields.
6. Call downstream via a Spring-managed client builder.
7. In the receiving service, verify baggage was extracted and appears in log MDC.
8. Verify worker threads do not retain stale baggage after tasks finish.

### 12.2 Checking Headers in Test Environments

~~~java
// Pseudocode for HTTP client/server test.
// Only record controlled metadata names and values in test environments.
assertThat(receivedHeaders).containsKey("traceparent");
assertThat(receivedHeaders).containsKey("baggage");
assertThat(receivedHeaders.getFirst("baggage"))
        .contains("channel=mobile");
~~~

This is pseudocode describing assertions, not a standalone runnable test class. Real tests need a mock server/client and must ensure requests run inside an active tracing scope.

### 12.3 Testing MDC Cleanup

Use a single-thread executor so the worker is reused:

1. Submit task A with baggage `channel=mobile`.
2. Inside task A, verify MDC has `channel=mobile`.
3. Finish the task and close the context scope.
4. Submit task B with no baggage.
5. Verify task B's MDC no longer contains task A's `channel=mobile`.

If task B reads the stale value, context restoration/cleanup is broken. This is an important test because such bugs often surface only under production load when executors reuse workers heavily.

## 13. Common Issues and Investigation

| Symptom | Possible cause | How to check |
|---|---|---|
| Logs have `traceId` but no baggage | Correlation fields unconfigured or baggage not created/extracted | Check `remote-fields`, `correlation.fields`, context |
| Baggage in Order but missing in Inventory | Not in remote allowlist or HTTP client did not inject | Check outbound `baggage` header/client instrumentation |
| Header reaches Inventory but MDC is empty | Receiver did not configure correlation fields, tracing did not extract | Check receiver config and runtime tracing |
| MDC has field but log does not print it | Pattern/JSON encoder does not read key | Check `%X{key}` or structured encoder |
| Wrong baggage appears on another task | ThreadLocal/MDC not cleaned up or async lacks propagation | Check `TaskDecorator`/`ContextSnapshot` and worker reuse |
| Unexpected baggage value | Caller sent untrusted metadata or value unnormalized | Validate/allowlist at boundary |
| Baggage missing from trace UI | Baggage not copied to span attributes or exporter drops fields | Check span attributes/processors |
| Trace missing while baggage/logs exist | Sampling or exporter/collector | Investigate trace pipeline separately |
| Log backend has fields but metric backend lacks them | MDC/log pipeline differs from metrics pipeline | Do not infer broken metrics exporter from logs |
| Header stripped by proxy | Gateway/header allowlist/size policy | Check proxy config and header limits |
| Value truncated or misencoded | W3C encoding or parser/collector normalization | Inspect raw header in tests |
| Metric series count spikes abnormally | Baggage copied into dynamic metric tags | Remove high-cardinality tags |

### 13.1 Playbook: Baggage Is in the HTTP Header but Missing in MDC

1. Verify the receiving service has a compatible Micrometer Tracing/tracer implementation and propagation format.
2. Verify the `baggage` header is actually extracted. Use test instrumentation or a debugger to inspect context.
3. Check `management.tracing.baggage.correlation.fields` on the receiving service. Sender config enables propagation; it does not configure MDC on the receiver.
4. Check key spelling/casing and API/implementation normalization.
5. Check the Logback pattern/JSON encoder. A field in MDC without output means logging config does not print it.
6. Check async boundaries if logs come from a worker; context propagation must work and the scope must not close before logging.

### 13.2 Playbook: Baggage Value Leaked into Logs

- Identify the origin sending the field and which services forward it.
- Remove the field from the remote allowlist if there is no valid need.
- Remove it from `correlation.fields` and logging patterns/encoders.
- Audit appenders/collectors to stop storing it in new indices.
- Apply remediation/retention policies per data governance rules.
- Add regression tests preventing sensitive fields from returning to baggage/log output.

Do not remove the field solely from one service's log pattern if downstream still forwards and logs it.

## 14. Design Mistakes to Avoid

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming MDC travels over HTTP automatically | Downstream lacks context | Use trace/baggage propagation and correlation config on receiver |
| Assuming baggage enters MDC automatically | Logs omit field | Declare correlation fields and encoder/pattern |
| Putting authorization tokens in baggage | Credentials leak across services | Never send secrets in baggage |
| Putting `orderId` in metric tags | Cardinality spikes | Use finite metric tags; look up IDs via controlled logs/traces |
| Copying all inbound baggage downstream | Forwards untrusted/unnecessary metadata | Allowlist remote fields |
| Calling `MDC.put` manually without restoring | Worker threads leak prior request data | Use scopes/`TaskDecorator`/`ContextSnapshot` and cleanup |
| Using baggage for access-control decisions | Callers spoof metadata | Authenticate/authorize via trusted security context |
| Changing sampling to fix MDC | Misses root cause | Investigate correlation fields and log pipeline |
| Turning baggage into metrics, span attributes, and logs all at once | Duplicates data and inflates cost | Copy only to needed signals |

## 15. Practice Exercises

**Exercise 1 — Distinguish signals.** An HTTP request has Trace ID `T`, Span ID `A`, and baggage `channel=mobile`. Explain which values belong to trace context, which are baggage, and which are used in MDC. Does baggage automatically appear in logs?

**Exercise 2 — Two-service configuration.** Order Service needs to send `tenant-region` and `channel` to Inventory Service; both services need to print those two fields in MDC. Write remote fields and correlation fields config in the right places. Why is receiver configuration also needed?

**Exercise 3 — Header propagation.** Inspect `traceparent` and `baggage` in an HTTP request. Why can baggage not replace `traceparent`? Why does the receiving server create a new Span ID?

**Exercise 4 — Empty MDC.** The `baggage` header arrived at the service, yet logs do not print `channel`. Outline the verification chain from extraction and correlation fields to the Logback pattern.

**Exercise 5 — Async leakage.** A task logs `channel=mobile` on a worker; the next task has no baggage, yet logs still print `mobile`. Explain ThreadLocal reuse and propose a single-thread executor test to catch the bug.

**Exercise 6 — Security.** A client sends baggage `role=admin`. Why must the service not use this field to grant privileges? Which mechanism should be used instead?

**Exercise 7 — Cardinality.** A developer wants to put `orderId` into baggage, MDC, and metric tags. Assess the risk per signal and recommend an appropriate option for investigating an order.

**Exercise 8 — Sampling.** A log record has `traceId`, `spanId`, and baggage, yet the trace UI cannot find the span. List hypotheses beyond propagation and how to verify each.

### Answer Hints

1. `T` is Trace ID, `A` is Span ID, `channel` is baggage; MDC holds fields only when configured/restored; baggage is not printed automatically.
2. Sender configures `remote-fields`; each service configures `correlation.fields` if logging is desired; receiver must extract and map fields into MDC.
3. `traceparent` identifies trace/parent span; baggage carries metadata only. The server creates a new span with its own ID and parent derived from sender context.
4. Confirm header presence, extraction, `correlation.fields`, tracing configuration, MDC scope, and log encoder.
5. Thread pools retain workers; the old scope was not restored. Run two consecutive tasks on the same worker and assert the second task does not see the stale field.
6. Caller-supplied baggage can be forged; use authentication/authorization and service policies.
7. `orderId` in baggage/logs increases index cardinality and requires data policies; strictly avoid in metric tags. Log/trace it only when genuinely needed, permitted, and controlled.
8. Sampling, unended spans, exporter/collector drops, retention, and wrong time-range/service queries.

## 16. Official References

- [W3C Baggage](https://www.w3.org/TR/baggage/): HTTP `baggage` header, member format, propagation, and limits.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, and trace context.
- [Micrometer Tracing — Baggage](https://docs.micrometer.io/tracing/reference/api.html): Tracer/Baggage API and scoped baggage management.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing configuration, baggage fields, correlation fields, and log correlation.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging patterns and logging system configuration.
- [SLF4J — MDC](https://www.slf4j.org/manual.html#mdc): Mapped Diagnostic Context API.
- [Logback — MDC](https://logback.qos.ch/manual/mdc.html): MDC semantics and context in logging.
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): ThreadLocal accessors, snapshots, and context propagation.
- [OpenTelemetry — Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/): baggage context, propagation, and data considerations.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): passing context across process boundaries.

**Key takeaway:** **Baggage carries metadata; MDC puts selected fields into logs; Trace ID/Span ID link traces and spans.** To see baggage in logs across multiple services, configure remote propagation, extract on the receiver, declare correlation fields, and ensure log encoders print the MDC keys. Keep baggage allowlisted, short, and non-sensitive; never use it for authentication, never turn dynamic IDs into metric tags, and always restore context after async tasks. When all three layers are configured properly, metrics show impact scope, logs provide details via correlation fields, and traces reveal the request's path.
