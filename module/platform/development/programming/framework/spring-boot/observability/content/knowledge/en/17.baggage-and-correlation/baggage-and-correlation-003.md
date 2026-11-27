# Remote Baggage Fields: Controlled Metadata Propagation Between Services

> **Chapter:** Baggage and Correlation  
> **Lesson:** Remote baggage fields  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Problem Statement: Downstream Services Need Part of the Request Context

A request flows through multiple services: `api-gateway` calls `order-service`, and `order-service` calls `inventory-service`. Each service has its own logs and traces, yet the operations team needs a few pieces of cross-cutting information for investigation, such as an operational region code, a workflow version, or a system-generated correlation key.

You can pass this information by putting it into **baggage** inside the tracing context. Baggage is a set of key–value pairs that can be injected into headers when a request crosses a process boundary, then extracted at the receiving service if both sides support the same propagation mechanism.

In Micrometer Tracing, **remote baggage fields** are baggage fields configured to be propagated across services. They differ from data that exists only on the current span or information used solely to populate a single process's MDC/logs.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as api-gateway
    participant Order as order-service
    participant Inventory as inventory-service
    Client->>Gateway: HTTP request
    Note over Gateway: Create trace context and region baggage
    Gateway->>Order: trace headers + baggage
    Note over Order: Extract context and read region
    Order->>Inventory: trace headers + baggage
    Note over Inventory: Extract field if permitted
    Inventory-->>Order: response
    Order-->>Gateway: response
    Gateway-->>Client: response
~~~

Remote baggage can be useful for correlation via technical keys, passing approved routing/partitioning attributes, retaining investigative context across multiple services, or carrying experiment/workflow version information.

Baggage is not a place to send the entire request, user details, or business payloads. Every propagated field increases header size, data-sharing scope, and security responsibility.

## 2. Distinguishing Remote Baggage, Span Attributes, Trace Context, and MDC

The following metadata types can coexist in a single trace but carry different semantics:

| Mechanism | Scope | Propagated to other services? | Example |
| --- | --- | --- | --- |
| **Trace context** | Trace/span identification and parent–child relationships | Yes, via propagator | `traceparent`, B3 headers |
| **Baggage** | Supplementary key–values attached to tracing context | Yes, if the field is configured as remote and the propagator supports it | `region=ap-south` |
| **Span attribute** | Metadata describing a specific span | Not automatically | `inventory.warehouse=wh-2` |
| **MDC/log correlation** | Context for in-process logging | Not automatically | `traceId`, `spanId`, `tenant_region` |
| **Observation low-cardinality key-value** | Metadata suited for grouping metrics | Not automatically | `channel=web` |
| **Observation high-cardinality key-value** | Metadata distinguishing individual executions, usually suited for spans | Not automatically | `order.attempt_id` |

**Remote baggage is not synonymous with a span attribute.** Attaching an attribute to a span does not automatically create headers for downstream to receive. Conversely, propagated baggage may be integrated into spans or MDC depending on the bridge/configuration, but you should not assume that mapping always happens.

Standard trace context carries identifying fields such as trace ID, parent/span ID, and sampling flags. Baggage is supplementary metadata. If you only need to link spans in a trace, trace context is sufficient; there is no need to create baggage containing the trace ID again.

## 3. What Does Remote Field Mean?

Inside an application, baggage can be created and read within the current scope. For a field to travel over the network, that field needs to be marked as a **remote field** in configuration or managed via a corresponding propagation mechanism.

Three aspects must be separated:

1. **Allowed to propagate:** the field is in the remote baggage configuration or equivalent allowlist.
2. **Injected/extracted:** the client propagator writes the field into request headers and the server propagator reads the field from headers.
3. **Used:** downstream code retrieves the value and applies it to business/observability logic according to the service's policy.

A field can exist in process A yet fail to appear in process B if remote configuration is missing, propagation formats are incompatible, headers are stripped by a proxy, or the request goes through an uninstrumented client.

~~~mermaid
flowchart LR
    A["Create baggage field in process A"] --> B{"Remote field allowed?"}
    B -->|No| C["Exists locally only"]
    B -->|Yes| D["Propagator injects into request"]
    D --> E["HTTP / messaging transport"]
    E --> F{"Downstream extracts?"}
    F -->|No| G["No baggage in process B"]
    F -->|Yes| H["Baggage field in process B"]
    H --> I["Used by code / tracing / logging"]
~~~

Remote configuration does not mean every outbound HTTP request leaves the system carrying that field automatically. Only requests going through the appropriate integration/propagator inject the header. You must also inspect intermediate gateways, load balancers, service meshes, or proxies.

## 4. Configuring Remote Baggage Fields in Spring Boot

With Spring Boot 3.x and Micrometer Tracing, configuration can declare the list of fields propagated between services:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
        - correlation-key
~~~

If certain fields need to be included in logging correlation within the current process, Spring Boot provides a separate configuration:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
      correlation:
        fields:
          - region
          - workflow-version
~~~

The two configurations have different responsibilities:

- `remote-fields`: specifies which fields may be propagated from this service to another service.
- `correlation.fields`: instructs the tracing integration to place selected fields into logging correlation/MDC according to bridge capabilities.

A field can be propagated without being placed into MDC; or it can be used solely for local correlation without needing to be sent out. Adding only `correlation.fields` does not automatically make a field remote baggage.

**Version scope:** examples target Spring Boot 3.x with auto-configured Micrometer Tracing. Check the configuration metadata of your running application version if property namespaces change. Do not infer that Brave and OpenTelemetry share identical implementation details everywhere.

## 5. Dependencies and Tracing Integration

Baggage does not work just by adding YAML. The application must have a tracing implementation/bridge, a matching propagator, and HTTP client/server instrumentation to inject/extract context.

Maven example for a Spring Boot 3.x application using Brave:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
    </dependency>
    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

This is an illustrative dependency set for tracing/Zipkin. If using the OpenTelemetry bridge and exporter, dependencies differ; do not arbitrarily combine multiple bridge implementations.

For HTTP, use clients/builders that Spring Boot can instrument. If you construct raw clients or build request headers manually, do not assume trace context and baggage are injected automatically. On the server side, the framework must be configured to extract context and establish the server span from incoming requests.

## 6. Propagation Formats: W3C Baggage and B3

Formats for transmitting trace context and baggage can differ.

### 6.1. W3C Trace Context and W3C Baggage

W3C Trace Context defines headers such as:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

W3C Baggage uses the `baggage` header to carry key–value members, for example:

~~~http
baggage: region=ap-south,workflow-version=v2
~~~

The header above is an abbreviated example and does not cover all escaping/metadata cases. Do not concatenate strings arbitrarily to build headers when dedicated propagators/APIs exist.

### 6.2. B3 Propagation

B3 typically uses the `b3` header or multi-field headers `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled`. B3 primarily describes trace context. How baggage is transmitted with Brave depends on baggage field configuration and propagation integration; do not confuse B3 trace headers with the W3C `baggage` header.

### 6.3. Both Systems Must Understand the Same Protocol

If upstream sends W3C baggage while downstream only extracts B3 trace context and does not read W3C baggage, the trace may link up, yet baggage will be absent downstream.

Conversely, using the same field name in code does not guarantee an identical wire representation. Check:

- Which propagator injects on the sending side.
- Which propagator extracts on the receiving side.
- Whether proxies/gateways allow those headers through.
- Whether the field is allowlisted on both sides.
- Whether the field is renamed, encoded, truncated, or dropped.

When integrating polyglot systems, prefer an agreed propagation standard such as W3C Trace Context/Baggage rather than relying on implementation-specific behavior.

## 7. Creating Remote Baggage with Micrometer Tracing BaggageManager

An application can manipulate baggage via Micrometer Tracing's `BaggageManager` API. For example, a service receives a validated region value from the business layer and creates baggage in the current scope:

~~~java
package example.orders;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.BaggageManager;
import org.springframework.stereotype.Service;

@Service
public class OrderRoutingService {
    private final BaggageManager baggageManager;

    public OrderRoutingService(BaggageManager baggageManager) {
        this.baggageManager = baggageManager;
    }

    public String route(String validatedRegion) {
        String region = normalizeRegion(validatedRegion);

        try (BaggageInScope ignored =
                     baggageManager.createBaggageInScope("region", region)) {
            return callInventory();
        }
    }

    private String callInventory() {
        // Call an HTTP client instrumented by Spring.
        return "inventory-accepted";
    }

    private static String normalizeRegion(String value) {
        if ("ap-south".equals(value)) return "ap-south";
        if ("eu-west".equals(value)) return "eu-west";
        return "default";
    }
}
~~~

In the example:

- `BaggageManager` is injected; do not instantiate a separate manager or tracer inside the service.
- `createBaggageInScope(...)` puts the field into current baggage for the scope's duration.
- `try-with-resources` closes the scope, restoring the previous context when the method exits.
- The value is normalized to a finite set to reduce variation and prevent callers from injecting arbitrary strings into headers.
- `callInventory()` requires an instrumented HTTP client so the propagator injects trace context and remote baggage.

The exact API behavior and whether the field is actually sent depend on bridge configuration, the remote-field allowlist, and an active context. Without a current span/trace context, creating baggage in scope does not guarantee creating a new trace or sending data to another process.

Do not store `BaggageInScope` in a singleton field or close the scope on another thread. A baggage scope is bound to an execution context; for async work, use proper context propagation mechanisms.

## 8. Reading Remote Baggage in the Receiving Service

If downstream has extracted baggage and uses a compatible tracing integration, code can read the value via `BaggageManager`:

~~~java
package example.inventory;

import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.BaggageManager;
import org.springframework.stereotype.Service;

@Service
public class InventoryPolicyService {
    private final BaggageManager baggageManager;

    public InventoryPolicyService(BaggageManager baggageManager) {
        this.baggageManager = baggageManager;
    }

    public String selectPolicy() {
        Baggage baggage = baggageManager.getBaggage("region");

        if (baggage == null) {
            return "default-policy";
        }

        String region = baggage.get();
        if ("ap-south".equals(region)) {
            return "south-policy";
        }
        if ("eu-west".equals(region)) {
            return "west-policy";
        }
        return "default-policy";
    }
}
~~~

This snippet assumes the `region` field is configured, extracted, and present in the current baggage context. When baggage is absent, the code has an explicit fallback.

**Do not use baggage as an authentication source or authorization decision-maker.** Request headers may come from external clients or be altered in transit. If `region` affects access permissions or tenancy, the server must verify it from a trusted source and only then use the verified value for critical decisions.

With untrusted input data, never take raw baggage values directly to concatenate SQL, construct file paths, choose arbitrary endpoints, or alter user privileges.

## 9. Remote Baggage and Multi-Hop Propagation

A field sent from A to B can continue propagating from B to C if B preserves the current context and the outgoing propagator is configured for that field. This does not mean every service automatically receives every field.

~~~mermaid
flowchart TD
    A["api-gateway: region=ap-south"] -->|"inject"| B["order-service: extract region"]
    B --> C{"Does B allow forwarding?"}
    C -->|Yes| D["Outgoing request injects field"]
    D --> E["inventory-service: extract field"]
    C -->|No| F["Field stops at order-service"]
~~~

A propagation chain can break due to:

- A service not declaring the remote field.
- An uninstrumented client or missing propagator.
- A gateway that forwards only an allowlist of headers and strips `baggage`.
- A messaging protocol requiring its own carrier/injector/extractor.
- Lost context across thread switches or async execution.
- Values exceeding proxy/server header limits.
- A service intentionally dropping the field because it is unneeded or forbidden to share further.

Maintain a list of which services may **receive**, which may **forward**, and which **must drop** the field. Do not let baggage spread unboundedly to unrelated systems.

## 10. Baggage with Logging Correlation/MDC

A common need is seeing certain fields in logs across multiple services. Spring Boot can configure baggage correlation fields to integrate with the logging context when the bridge supports it.

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
      correlation:
        fields:
          - region
          - workflow-version
~~~

When the tracing integration updates MDC as configured, the log pattern can display the fields:

~~~text
INFO  [order-service, traceId=..., spanId=..., region=ap-south] Starting checkout
INFO  [inventory-service, traceId=..., spanId=..., region=ap-south] Reserving stock
~~~

This is an illustrative log format; actual MDC keys and patterns depend on the logging stack/bridge. Do not assume that adding YAML alone ensures custom loggers or executors automatically preserve MDC.

Distinguish clearly:

- `traceId`/`spanId` are typically added to the correlation context by the tracing integration.
- `region`/`workflow-version` are baggage correlation fields when configured.
- MDC fields only serve in-process logging; propagating to another process still requires remote propagation.
- When threads change, MDC may not be copied without an appropriate context propagation mechanism.

MDC is not a source of business truth. If a field affects processing, code must use verified data from the business context rather than reading back from log-formatted strings.

## 11. Security: Propagate Only Truly Necessary Fields

Remote baggage can traverse multiple services, proxies, and external systems. An outbound field may appear in request headers, logs, span attributes, collector payloads, and the tracing backend. Therefore, design it as a **data-sharing interface**.

### 11.1. Do Not Send Sensitive Data

Do not put into baggage:

- Passwords, API keys, bearer tokens, session cookies, or credentials.
- Card numbers, sensitive payment data, or authentication secrets.
- Emails, phone numbers, addresses, or personally identifiable information without an approved purpose and policy.
- Request/response bodies or arbitrary exception strings.
- Internal secrets that only a single service is permitted to know.

The `baggage` header typically passes through more components than an internal span attribute. The risk surface can be larger than expected if used carelessly.

### 11.2. Allowlisting and Value Normalization

Declare remote fields strictly via an explicit allowlist. For each field, define:

| Attribute | Question to answer |
| --- | --- |
| Name | Is it stable and free of sensitive data? |
| Purpose | What does the receiving service use it for? |
| Valid values | What finite enum/restricted set is accepted? |
| Max length | What is the byte/character limit? |
| Propagation scope | Across which services is propagation permitted? |
| Retention | How long do log/trace backends retain it? |
| Owner | Which team owns versioning and deprecation? |

Normalize values before putting them into baggage. For `region`, allow only fixed values such as `ap-south`, `eu-west`, and `default`; do not take arbitrary strings directly from URLs or external headers.

### 11.3. Do Not Put High-Cardinality Values into Metrics

Baggage is metadata for context propagation; that does not make it suitable as a metric tag. A correlation key that varies per request will create high cardinality if a custom handler/meter turns it into a label.

Use metrics with low-cardinality dimensions such as region/outcome/service; use baggage/span attributes/log correlation for approved technical IDs; use audit/business stores for event data requiring durable storage.

## 12. Header Size, Limits, and Performance

Every baggage field adds bytes to headers on propagated requests. With many long keys or payload-containing values, requests can exceed header limits of clients, proxies, gateways, or servers.

Consequences can include:

- HTTP 400/431 or request-header-too-large errors.
- Proxies dropping headers or forwarding only a subset.
- Increased serialization/parsing overhead at each hop.
- Bloated log/trace data.
- Compatibility errors with external services that do not understand baggage.

There is no single header limit across all products. Every HTTP client, reverse proxy, server, and mesh has its own configurable limits. Measure actual request sizes end-to-end and keep baggage small and stable.

### 12.1. Do Not Pass Baggage via Arbitrary Strings

Do not build headers manually by string concatenation:

~~~java
// Do not do this: manually building tracing headers via string concatenation.
request.header("baggage", "region=" + region + ",user=" + userInput);
~~~

Use the tracing propagator/`BaggageManager` from the appropriate stack. The propagator handles format-compliant injection/extraction; the application is responsible for allowlisting and validating data.

### 12.2. Baggage Is Not a Large Data Store

Do not send lists of IDs, JSON payloads, or full configuration blobs in baggage. If downstream needs a business record, pass it through the request body/contract or query an appropriate datastore; baggage should contain only small metadata used across the request.

## 13. Baggage in HTTP Clients, Messaging, and Async

### 13.1. HTTP

With HTTP, tracing instrumentation typically injects trace context and baggage into the outbound carrier. On the receiving server, instrumentation extracts them before establishing the server span. Use framework-managed HTTP client builders to preserve proper instrumentation.

When calling an external service or third-party partner, audit outbound headers. Do not assume all internal baggage fields are permitted to be forwarded to third parties. You may need an outbound policy that strips sensitive baggage or forwards only specific fields.

### 13.2. Messaging

With queues/message brokers, propagation goes through message headers/properties via the messaging framework's carrier and integration. Do not mechanically apply HTTP `baggage` header assumptions to Kafka/RabbitMQ/JMS. Producers must inject; consumers must extract; messages may be processed minutes later or by another process.

If messages are retained for a long time, check retention and whether stale baggage is still valid when the consumer processes the message.

### 13.3. Async Executors and Reactor

The current thread's context does not automatically become the context of every new thread. A task submitted to an executor can lose trace/baggage if context is not captured and restored.

- Use Spring/Micrometer-supported context propagation mechanisms for executors or reactive chains.
- Do not hold `BaggageInScope` and close it on another thread.
- In Reactor, use appropriate context-aware instrumentation rather than relying purely on ThreadLocals.
- Check trace ID and baggage fields at the actual callback execution point.

When context is lost, the system may start a new trace or fragmented root spans, breaking cross-service correlation.

## 14. End-to-End Testing of Remote Baggage

A unit test of `BaggageManager` only shows that code creates/reads the field. To prove remote propagation, you must test across **two processes or two HTTP boundaries**.

### 14.1. Test Scenario

Suppose:

- `gateway-service` receives a request and sets `region=ap-south` in baggage scope.
- `order-service` receives the request and reads `region`.
- Both services use compatible tracing bridges/propagators.
- `region` is declared as a remote field per configuration.

~~~mermaid
sequenceDiagram
    participant Test
    participant Gateway as gateway-service
    participant Order as order-service
    Test->>Gateway: GET /checkout
    Gateway->>Gateway: Set baggage region=ap-south
    Gateway->>Order: HTTP request + baggage
    Order->>Order: Extract region
    Order-->>Gateway: region observed
    Gateway-->>Test: Response
~~~

### 14.2. Verification Checklist

1. Create a test request with a known allowlisted value.
2. In `gateway`, confirm baggage is in context before invoking the HTTP client.
3. Inspect the outbound request in the test environment for the matching propagation header, masking sensitive details.
4. In `order-service`, read baggage via the tracing API within the request context.
5. Verify the value is accurate and not read from an unverified arbitrary header.
6. Test removing the field from `remote-fields` or using an incompatible propagation format in tests; the field must stop appearing downstream.
7. Test an invalid value; the service must fall back or reject per policy.
8. Check log correlation if configured; compare against trace ID/span ID.
9. Verify metrics have no labels containing correlation IDs or per-request varying values.

### 14.3. Distinguishing Baggage Errors from Trace Propagation Errors

If downstream has the same `traceId` but lacks `region`, trace context propagated successfully, whereas baggage may not be configured/forwarded/extracted.

If downstream has a different trace ID, the issue likely lies in trace context propagation, sampling flags, client instrumentation, or proxy headers. Do not diagnose every case identically.

If baggage exists in the receiving process yet logs do not show the field, the issue likely lies in correlation/MDC configuration rather than remote propagation.

## 15. Common Issues and Diagnostics

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Baggage present at gateway but missing downstream | Field not declared remote, not injected/extracted, header dropped | Check `remote-fields`, propagator, and carrier |
| Trace links up but baggage is missing | Trace context works, baggage format/allowlist mismatched | Check W3C Baggage/B3 integration and remote field config |
| Baggage readable in one method but lost in callback | Context not propagated across thread/async boundary | Check executor/Reactor context propagation |
| Field propagated but missing in logs | Correlation field not declared or MDC integration inactive | Check `correlation.fields`, logging pattern |
| Logs show field but other service does not receive it | Local correlation only, not remote propagation | Check `remote-fields` and outgoing headers |
| Some services receive field, others do not | Gateway/proxy allowlist or per-service config differences | Compare request headers and per-hop configs |
| Request fails with header too large | Too many baggage fields or oversized values | Measure header size, trim allowlist, cap value length |
| Baggage holds invalid value | Directly trusting client-sent data | Validate/normalize at the trust boundary |
| Abnormal spike in metric time series | Baggage value turned into a metric tag by a custom handler | Remove high-cardinality tag from metrics |
| Field still appears after removing set code | Upstream injects value or another service propagates it | Identify field origin hop by hop |
| External service receives internal baggage | Outbound policy forwards too broadly | Block or allowlist fields at the egress boundary |

### Investigation Workflow

1. Record the field name and normalized test value.
2. Check context at the point where it is set.
3. Check the sending service's remote field configuration.
4. Inspect the propagator and actual headers before leaving the service.
5. Check whether proxies/gateways forward the header.
6. Check extraction and baggage context in the receiving service.
7. Separate logging correlation, trace context, and baggage issues.
8. Check header size, security policy, and cardinality before expanding to more services.

Do not log full baggage headers in production just to debug. You can log field presence/absence or masked/normalized values according to policy.

## 16. Real-World Scenario: Correlation Key Across Three Services

**Context.** An order flow passes through `gateway-service`, `order-service`, and `inventory-service`. When a customer reports a slow order placement, the on-call engineer needs to locate logs across services using a technical correlation key.

### Step 1 — Create a Trusted Correlation Key

Gateway generates a random ID or receives an ID from a verified internal system. Do not blindly accept `X-Correlation-ID` from external clients without validation, and never allow values containing personal data.

### Step 2 — Place into Baggage Scope

Gateway creates the `correlation-key` baggage field in the request context with an appropriate remote allowlist configuration. If the tracing context is not yet established, ensure proper instrumentation/context lifecycle before expecting propagation to work.

### Step 3 — Forward via HTTP Client

Gateway calls `order-service` using an instrumented client. The propagator adds trace context and baggage. `order-service` extracts the field and can include it in logging correlation if `correlation.fields` permits.

### Step 4 — Propagate Intentionally

`order-service` calls `inventory-service`. If policy permits the field to continue, the outgoing propagator keeps injecting it. If `inventory` does not need the correlation key, the service can drop the field at the boundary instead of spreading it unnecessarily.

### Step 5 — Investigate

The on-call engineer uses metrics to narrow down the timeframe/instance; trace ID to view the waterfall; and the correlation key to find permitted logs. Baggage does not replace trace ID and does not need to be a metric label.

**Takeaway:** a remote baggage field can preserve context across multiple processes, but only when every hop has matching configuration, instrumentation, and policy. You must govern the field's origin, sharing scope, and sensitivity.

## 17. Practice Exercises and Self-Check Questions

### Exercise A — Configure Allowlist

Create two Spring Boot services using compatible tracing integrations. Declare `region` and `workflow-version` in `management.tracing.baggage.remote-fields`. Declare `region` in `correlation.fields`.

- Invoke service A via an instrumented flow.
- Set `region=ap-south` in baggage scope.
- Call service B via an instrumented HTTP client.
- Verify B reads the field in context and log correlation displays the field as configured.

### Exercise B — Compare Three Metadata Types

For the same request, record:

- Span attribute `inventory.warehouse=wh-2`.
- Remote baggage `region=ap-south`.
- Local MDC field `debug-mode=true`.

Verify which data crosses to another process, which stays on the span only, and which affects only logs in the current process. Explain why span attributes are not automatically injected as baggage.

### Exercise C — Broken Propagation

In a test environment, configure the sending service to use one propagation format while the receiving service does not extract that matching format. Observe trace ID and baggage downstream; then align the propagators and re-verify. If the trace connects while baggage is lost, identify the specific configuration to check.

### Exercise D — Security and Header Size

Design an allowlist of at most three fields:

- `region`: one of three fixed values.
- `workflow-version`: short version string.
- `correlation-key`: length-bounded opaque ID.

Reject or drop oversized/invalid values. Confirm no tokens, emails, user IDs, or request payloads appear in headers/logs/metrics. Test a request with long baggage in a test environment to understand HTTP stack/proxy limits.

### Self-Check Questions

1. How does a remote baggage field differ from a span attribute?
2. What is the role of `management.tracing.baggage.remote-fields`?
3. Does `correlation.fields` automatically cause a field to be sent to another service?
4. When trace context connects but baggage is missing, what parts should you inspect?
5. Why are B3 trace headers not synonymous with the W3C `baggage` header?
6. What lifecycle does `BaggageManager.createBaggageInScope(...)` require?
7. Why should tokens, emails, or payloads not be placed into baggage?
8. Why should remote baggage not become a metric label?
9. Can a field be lost at a proxy even when both services have configured remote fields? Why?
10. When an async callback runs on a different thread, what must be ensured for the tracing context?
11. Why should baggage not be used as a source of authentication/authorization?
12. How do you distinguish a propagation failure from a logging correlation/MDC failure?

**Completion criteria:** ability to explain remote baggage, span attributes, trace context, and MDC; configure remote fields and correlation fields; create/read baggage with appropriate APIs; verify propagation over HTTP or messaging; and enforce header size, security, allowlist, and cardinality controls.

## 18. Key Takeaways

- **Remote baggage fields** are key–values permitted to travel with the tracing context across service boundaries; they require explicit configuration and propagator support.
- In Spring Boot 3.x, `management.tracing.baggage.remote-fields` declares propagated fields; `correlation.fields` controls placing selected fields into logging correlation according to bridge support.
- **Trace context, baggage, span attributes, and MDC are distinct layers.** A span attribute does not automatically become a header; log correlation does not automatically cross process boundaries.
- `BaggageManager` creates/reads baggage in the current context. Follow proper scope lifecycles and ensure context propagation during async work.
- W3C Baggage and B3 trace context are not the same standard. Services must agree on inject/extract formats and proxies must forward the corresponding headers.
- Baggage is a data-sharing interface: allowlist fields, normalize values, limit sizes, and never transmit credentials or sensitive payloads.
- Do not use high-cardinality baggage as metric labels; use metrics for aggregation, and traces/logs for investigating individual executions.
- Verify end-to-end at every hop. If trace IDs connect but baggage is missing, check baggage configuration/propagators separately; if baggage arrives but logs lack it, check MDC correlation.

## References

- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Tracing — Baggage](https://docs.micrometer.io/tracing/reference/api.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
