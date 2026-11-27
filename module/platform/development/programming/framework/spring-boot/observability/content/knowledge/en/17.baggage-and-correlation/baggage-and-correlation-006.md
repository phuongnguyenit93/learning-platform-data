# Baggage in gRPC Metadata

In the **Baggage and Correlation** chapter of the **SPRING_BOOT_OBSERVABILITY** module, baggage consists of key–value pairs attached to a trace context to carry a small amount of metadata across service boundaries. When a Spring Boot application calls another service via **gRPC**, RPC metadata is the appropriate carrier for transmitting permitted baggage fields. This lets services share certain contexts, such as processing region or request class, when writing logs and analyzing traces.

Baggage is neither a business payload nor an authentication mechanism. Data in baggage can pass through multiple services, interceptors, proxies, and telemetry systems. Therefore, its contents must be allowlisted, size-limited, and privacy-controlled. This lesson explains transmitting baggage via **gRPC metadata**, combining Micrometer Tracing/OpenTelemetry to maintain trace context and correlation in Spring Boot observability.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish baggage, trace ID, span ID, gRPC metadata, and protobuf messages.
2. Describe how W3C Baggage is represented across metadata of a gRPC call.
3. Distinguish ASCII metadata from binary metadata suffixed with **-bin**.
4. Configure baggage fields permitted to propagate from Spring Boot/Micrometer Tracing.
5. Use OpenTelemetry gRPC instrumentation to inject/extract context on client and server.
6. Understand the role of interceptors and how to verify data on both ends.
7. Limit baggage by field count, length, cardinality, and sensitive data.
8. Diagnose lost baggage, broken traces, oversized metadata, and inconsistent log correlation.
9. Combine baggage with metrics, logs, and distributed tracing without turning baggage into a business data transport channel.

## 2. What Is Baggage?

**Baggage** is a set of key–value pairs attached to a trace context that can be propagated from one service to another. It is useful for small metadata relevant across multiple processing steps, for example:

- **region=ap-southeast-1** to support analyzing flows across regions.
- **request.class=interactive** to distinguish a traffic class with a finite set of values.
- **tenant.tier=standard** to group processing under an approved policy.

Baggage can be accessed during current processing and injected into downstream calls if the propagator is configured. The receiving system extracts baggage from a carrier, such as HTTP headers or gRPC metadata, and places the values into the next request's context.

### What Does Baggage Not Replace?

| Concept | Purpose | Example |
| --- | --- | --- |
| **Trace ID** | Identifies a distributed trace. | A trace spanning multiple spans across multiple services. |
| **Span ID** | Identifies a unit of work within a trace. | Server span handling the `ReserveStock` RPC. |
| **Baggage** | Small metadata propagated with context. | `region=ap-southeast-1`. |
| **gRPC metadata** | Carrier transmitting key–values on RPC request/response headers. | `baggage: region=ap-southeast-1`. |
| **Request message** | Business payload of the RPC. | `ReserveRequest` containing `sku` and `quantity`. |
| **Log correlation fields** | Fields aiding log search and grouping. | `traceId`, `spanId`, `tenantTier`. |

W3C Trace Context headers contain trace ID, parent span ID, and flags; they do not contain the baggage list. Baggage is carried via a separate W3C header named `baggage`. When moving to gRPC, these two concepts map to corresponding metadata entries, provided propagators and instrumentation are configured.

**Never use baggage to store authorization tokens, session cookies, or access permissions.** Baggage is not designed to authenticate callers and can be forwarded more broadly than expected.

## 3. How Is gRPC Metadata a Carrier?

gRPC metadata is a set of key–value pairs attached to an RPC call. Metadata can be sent from client to server as request metadata (headers); the server can also return metadata in response headers or trailers.

In Java gRPC, metadata is represented by the `Metadata` class. A key declares a marshaller type for its value:

~~~java
Metadata.Key<String> regionKey =
        Metadata.Key.of(
                "region",
                Metadata.ASCII_STRING_MARSHALLER);
~~~

Rules to remember:

- Metadata keys are lowercase ASCII names; do not use uppercase letters in keys.
- Keys for text values are typically ASCII metadata.
- Keys ending in `-bin` are reserved for binary data and must use the corresponding marshaller.
- Do not add a `grpc-` prefix yourself; that prefix is reserved for the protocol.
- Metadata must stay small; oversized headers can be rejected by clients, servers, proxies, or infrastructure configuration limits.
- If a field allows only one value, define how to handle keys appearing multiple times.

With W3C Baggage, the propagator serializes the baggage list into a text string per W3C Baggage rules. Thus the carrier key is ASCII `baggage`, not a separate custom key per field. Illustrative example:

~~~text
baggage: region=ap-southeast-1,request.class=interactive
~~~

This is an illustrative representation. When encoding or multiple values are involved, let the W3C propagator serialize/parse per the standard instead of concatenating strings with commas yourself.

### Flow Through gRPC

~~~mermaid
sequenceDiagram
    participant A as Spring Boot service A
    participant C as gRPC client interceptor
    participant M as gRPC Metadata
    participant S as gRPC server interceptor
    participant B as Spring Boot service B

    A->>C: Invoke RPC in trace/baggage context
    C->>M: Inject trace context and baggage
    M->>S: Send request metadata
    S->>S: Extract context from metadata
    S->>B: Run handler in restored context
    B-->>A: Return RPC result
~~~

Interceptors are a convenient integration point because they observe RPC calls on the channel/server they are attached to. A hand-written interceptor must carefully handle exceptions, cancellation, and lifecycle; using battle-tested library instrumentation is usually less error-prone.

## 4. W3C Baggage and gRPC Metadata

W3C Baggage defines a text header named `baggage`. When using OpenTelemetry propagators, baggage is serialized into a text value and placed on the carrier. In gRPC, metadata is the corresponding carrier; the `baggage` key is used to transport this string.

Example logical fields:

~~~text
region = ap-southeast-1
request.class = interactive
tenant.tier = standard
~~~

Do not create separate metadata keys for every baggage field if you want W3C Baggage compatibility. Use a single `baggage` key and let the propagator encode/decode the field list.

### Not All Metadata Is Baggage

| Metadata | Role | Should it be treated as baggage? |
| --- | --- | --- |
| `authorization` | Credentials/authentication. | No. |
| `content-type` | Message/protocol format. | No. |
| `traceparent` | W3C trace context. | No; this is trace propagation. |
| `baggage` | W3C baggage fields. | Yes. |
| `x-request-id` | Request correlation per application convention. | Not by default; this is separate metadata. |
| `tenant.tier` | Small field permitted to propagate. | Only when placed into W3C baggage per policy. |

Do not take all gRPC metadata and automatically dump it into baggage or span attributes. Doing so can copy credentials, personal data, or internal metadata to the trace backend.

## 5. Configuring Baggage in Spring Boot

Examples assume Spring Boot 3.x, Micrometer Tracing, and the OpenTelemetry bridge managed via Spring Boot dependency management. Baggage field names must be declared explicitly; do not propagate every value the application might produce.

Illustrative dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'

    implementation 'io.grpc:grpc-netty-shaded'
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'
}
~~~

gRPC and OpenTelemetry instrumentation versions must be managed consistently via a BOM/dependency management compatible with your application. Exact dependencies also depend on your project's gRPC code-generation library and Java plugin version.

Configuring baggage fields in `application.yml`:

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
        - region
        - request.class
        - tenant.tier
      correlation:
        fields:
          - region
          - request.class
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Explanation:

- `remote-fields` declares baggage fields permitted to propagate across remote boundaries per the active Micrometer Tracing/Spring Boot version.
- `correlation.fields` requests that selected fields be usable as correlation fields in logs when the corresponding integration supports it.
- `sampling.probability` governs trace sampling per configuration; baggage is managed per request context, whereas spans may be sampled out.
- The OTLP endpoint serves span export; it is not the business gRPC endpoint that the service calls.

Property names and how the bridge maps baggage must be verified against your deployed Spring Boot release. If using the Brave bridge, baggage and propagation configuration may differ; do not copy OTel configuration verbatim to another implementation without checking.

### Local Fields and Remote Fields

Some metadata is only needed inside the current service and does not need to go over the network:

- **Local baggage fields:** used in the current context without actively propagating downstream.
- **Remote baggage fields:** fields allowed to be injected into the carrier for other services.
- **Correlation fields:** fields that can be placed into the logging context/MDC to simplify log filtering.

Do not put every field into all three groups. Every field must have a clear purpose and owner. In multi-tenant systems, tenant tier can be useful, yet it must never expose customer identifiers or access permissions.

## 6. How OpenTelemetry Attaches Baggage to gRPC

A preferred approach is using **OpenTelemetry gRPC instrumentation** with the same `OpenTelemetry` instance/propagators used by the application's tracing. The instrumentation creates client/server interceptors to inject/extract context from gRPC metadata, including trace context and baggage if propagators are configured appropriately.

For OpenTelemetry gRPC instrumentation versions providing the `GrpcTelemetry` API, configuration looks like:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.ServerBuilder;

public final class GrpcTracingConfiguration {

    private final GrpcTelemetry grpcTelemetry;

    public GrpcTracingConfiguration(OpenTelemetry openTelemetry) {
        this.grpcTelemetry = GrpcTelemetry.create(openTelemetry);
    }

    public ManagedChannel createClientChannel(String host, int port) {
        return ManagedChannelBuilder
                .forAddress(host, port)
                .usePlaintext() // Use only in lab/safe test networks.
                .intercept(grpcTelemetry.newClientInterceptor())
                .build();
    }

    public Server createServer(int port,
                               io.grpc.BindableService service) {
        return ServerBuilder.forPort(port)
                .addService(service)
                .intercept(grpcTelemetry.newServerInterceptor())
                .build();
    }
}
~~~

This is an example of attaching interceptors; in real projects, manage channels/servers as Spring beans or components with clear lifecycles, shut down channels/servers on application shutdown, and configure TLS instead of `usePlaintext()` outside labs. The instrumentation API package/version must match the `opentelemetry-grpc-1.6` artifact and OpenTelemetry instrumentation BOM used by your project.

**Important:** the `OpenTelemetry` instance passed to `GrpcTelemetry.create(...)` must be the instance shared with the application's tracing pipeline, or at least share the same propagators/context configuration. Constructing a separate standalone SDK can produce traces disconnected from Micrometer Tracing running in Spring Boot.

### The Propagator Must Include W3C Baggage

For baggage to be forwarded, OpenTelemetry propagators must include the W3C Baggage propagator (typically paired with W3C Trace Context). With only the trace context propagator, `traceparent` can still be injected/extracted, but baggage fields will not be transferred.

When using a Spring Boot/Micrometer Tracing bridge, inspect the propagation configuration produced by auto-configuration alongside remote baggage fields. Do not create a competing composite propagator alongside the Boot-managed pipeline; if customization is needed, configure the exact instance used by gRPC instrumentation.

## 7. Where Is Baggage Created and Read?

Baggage can be created at the request entry point or inside a service that already has context. Example using the OpenTelemetry API directly:

~~~java
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.context.Context;

public final class RequestBaggage {

    public Context withRegion(String region) {
        Baggage baggage = Baggage.builder()
                .put("region", region)
                .put("request.class", "interactive")
                .build();

        return baggage.storeInContext(Context.current());
    }
}
~~~

The snippet above creates a new OTel context with baggage, but does not automatically make that context the current context for the entire request. In real integration code, open a scope/set context per proper lifecycle and use Micrometer Tracing/Micrometer Baggage APIs when you want application-level abstractions. Never keep a scope open across threads.

One way to read baggage from context:

~~~java
Baggage baggage = Baggage.fromContext(Context.current());
String region = baggage.getEntryValue("region");
~~~

If the value is absent, `region` may be `null`. Code must have an appropriate fallback instead of assuming every request carries this field. Baggage from remote callers is input data that must be validated/normalized before use in logic.

### Do Not Use Baggage to Replace Payloads

If an RPC needs SKU, quantity, account ID, or information required to perform business work, pass it in the protobuf request message. Baggage should contain only **cross-cutting metadata** for correlation/observability or small approved policy context.

Do not rely on baggage to decide whether a caller has access to a tenant. Authorization must rely on verified identity and trusted policies; baggage can be caller-controlled and is not proof of identity.

## 8. Placing a gRPC RPC Inside a Trace

When the gRPC client interceptor creates a client span and the server interceptor extracts context to create a server span, the trace can look like:

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER order-api: POST /orders
    └── CLIENT inventory-api: Inventory.Reserve
        └── SERVER inventory-api: Inventory.Reserve
~~~

In a proper design, baggage can be read in the server handler and appear in logs/spans if instrumentation permits. However, client and server spans alone do not prove baggage arrived; inspect metadata or baggage context at both ends.

Example of correlated logging:

~~~java
log.info("Calling inventory service with region={}", region);
~~~

If logging correlation is configured via Micrometer Tracing/MDC, trace ID/span ID can be added automatically. The `region` field appears only if placed into the log context or explicitly logged. **Baggage does not necessarily become an MDC field automatically**; configure correlation fields or the corresponding logging mechanism and verify in practice.

## 9. Verifying Baggage at Both Ends of gRPC

A useful test must verify **client sends, server receives, and context is restored**. You can test using instrumentation tests or gRPC integration tests with real client/server in a test environment.

| Checkpoint | Evidence |
| --- | --- |
| Before RPC call on client | Baggage context contains the allowlisted field. |
| Client interceptor | Request metadata contains a `baggage` entry after injection. |
| Server interceptor | W3C propagator extracts context from metadata. |
| Server handler | Reads field from current context or corresponding baggage API. |
| Logs | Contain trace correlation; baggage fields appear only if logging correlation is configured. |
| Trace backend | Client/server spans share trace ID and have baggage attributes if instrumentation/processors store them. |

In unit tests for a custom carrier adapter, you can initialize `Metadata`, inject context via the propagator, then extract and compare baggage values. Use the real propagator from the OpenTelemetry SDK to test serialization; do not write your own CSV parser for W3C Baggage since the spec has specific encoding and escaping rules.

### Example Carrier Adapter for Round-Trip Testing

The snippet below illustrates the carrier testing principle. It uses a `TextMapPropagator` configured with W3C Baggage and a `Metadata` carrier:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.Context;

public final class GrpcMetadataCarrier {

    static final TextMapSetter<Metadata> SETTER = (carrier, key, value) -> {
        Metadata.Key<String> metadataKey =
                Metadata.Key.of(
                        key.toLowerCase(java.util.Locale.ROOT),
                        Metadata.ASCII_STRING_MARSHALLER);
        carrier.put(metadataKey, value);
    };

    static final TextMapGetter<Metadata> GETTER = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(Metadata carrier) {
            return java.util.List.of("traceparent", "tracestate", "baggage");
        }

        @Override
        public String get(Metadata carrier, String key) {
            Metadata.Key<String> metadataKey =
                    Metadata.Key.of(
                            key.toLowerCase(java.util.Locale.ROOT),
                            Metadata.ASCII_STRING_MARSHALLER);
            return carrier.get(metadataKey);
        }
    };

    public static void inject(TextMapPropagator propagator,
                              Context context,
                              Metadata metadata) {
        propagator.inject(context, metadata, SETTER);
    }

    public static Context extract(TextMapPropagator propagator,
                                  Context context,
                                  Metadata metadata) {
        return propagator.extract(context, metadata, GETTER);
    }
}
~~~

This is an example carrier adapter for common W3C ASCII keys, not a complete interceptor replacing gRPC instrumentation. With custom propagators, the getter must advertise the exact list of keys the propagator supports; if binary metadata exists, use the appropriate marshaller and never pass binary fields through `ASCII_STRING_MARSHALLER`. In production, prefer library gRPC instrumentation to preserve span lifecycle, cancellation, and context propagation.

A round-trip test should build a W3C propagator (Trace Context + Baggage), put a baggage entry into context, call `inject`, then `extract` from the metadata and assert the value. With Spring Boot, verify that propagator matches the instance used by the application.

## 10. Baggage Size Limits and Safety

Baggage propagates across multiple RPCs, so each field increases request metadata size. gRPC, HTTP/2, proxies, service meshes, and servers may enforce different header/metadata limits. Oversized metadata can cause requests to be rejected or spike memory/CPU during parsing.

Apply these principles:

- **Allowlist field names:** propagate only fields with a clear purpose.
- **Limit lengths:** cap each value and total baggage; avoid fields with very long strings.
- **Limit field count:** do not turn baggage into a free-form map holding the entire request context.
- **Finite values:** prefer region, request class, or tier with small value sets; avoid arbitrary UUIDs and user IDs.
- **No secrets/PII:** tokens, cookies, emails, account numbers, and request bodies must not go into baggage by default.
- **Trust boundaries:** accept or forward fields only from identified sources; drop baggage sent by public clients.
- **Retention and access:** baggage can appear in logs and traces, so it falls under the corresponding query permission and retention policies.

There is no single safe byte limit for every deployment. Verify exact limits on your gRPC client/server, proxies, and infrastructure. Do not treat the transport's maximum ceiling as your recommended baggage budget.

## 11. Baggage, Cardinality, and Metrics

A common design mistake is using baggage as an automatic source for metric tags. Baggage can hold per-request varying values; copying every field straight into metrics can cause cardinality explosion.

| Field | Baggage? | Low-cardinality metric tag? | Notes |
| --- | --- | --- | --- |
| `region=ap-southeast-1` | Possible | Possible if regions are controlled | Add only when helpful for analysis. |
| `request.class=interactive` | Possible | Usually appropriate | Finite set of values. |
| `tenant.tier=standard` | Possible per policy | Possible if only a few tiers | Do not send tenant ID. |
| `request.id=UUID` | Only with specific correlation need | No | Use logs or trace attributes per policy. |
| `user.email=...` | No | No | Personal data. |
| `authorization=Bearer ...` | Never | Never | Authentication secret. |

With Micrometer Observation, tags are separated into low-cardinality and high-cardinality key-values. Never automatically copy all baggage into low-cardinality tags. If a baggage field is needed in metrics, map **only an allowlisted field with a finite set of values**.

Baggage also does not replace service/resource attributes. `service.name` describes the service; `region` can describe a request if it is genuinely request metadata, though avoid confusing it with the process's deployment region.

## 12. Security and Trust

gRPC metadata is caller-supplied data. Inbound baggage must be treated as **untrusted input** until validated and accepted by policy.

Example risks:

1. A client sends `tenant.tier=premium` to mislead logs or dashboards into treating the request as priority tier.
2. A long field or many fields bloat metadata and increase load.
3. Sensitive data propagates to a third-party service or tracing backend.
4. Baggage gets logged across multiple services, creating extra copies of data.
5. A high-cardinality field becomes a metric tag and inflates series count.

Mitigations:

- Authenticate gRPC callers before trusting metadata that affects policy.
- Create/overwrite baggage at gateways or trusted services when verified metadata is needed.
- Permit only registered keys, restricting value length and charset.
- Never use baggage in place of authorization, tenant isolation, or permission checks.
- Use TLS/mTLS for gRPC across networks requiring protection.
- Never log all metadata, since it may include authentication info or data not meant for logs.
- Review Collector processors and trace backends to ensure attributes are stored per policy.

A `tenant.tier` sent by a caller is not proof the caller is entitled to that tier. If a value affects business logic, obtain it from authenticated identity/claims or server-side data rather than trusting baggage directly.

## 13. Common Errors When Propagating Baggage over gRPC

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Trace ID reaches server but baggage is empty | Only Trace Context propagator enabled, missing W3C Baggage propagator, or field not in remote allowlist. | Check composite propagator, Micrometer baggage config, and `baggage` metadata. |
| Baggage in client context but missing in metadata | gRPC client interceptor not attached or different `OpenTelemetry` instance used. | Check channel builder/interceptor and shared SDK. |
| Metadata has baggage but server cannot read it | Server interceptor did not extract, wrong getter/propagator, or handler does not run in extracted context. | Check server instrumentation/context. |
| HTTP propagation works but gRPC does not | HTTP instrumented while gRPC lacks client/server instrumentation. | Attach gRPC interceptors and inspect carrier metadata. |
| gRPC returns metadata-too-large error | Too many fields or oversized values; proxy/server has smaller limits. | Reduce fields/length, do not use baggage for payloads. |
| Some fields disappear after multiple hops | Intermediate service does not propagate field or allowlists differ. | Compare `remote-fields` and propagators across services. |
| Logs lack baggage | Correlation fields unconfigured or logging context inactive. | Check MDC/correlation config; baggage does not always become a log field automatically. |
| Metrics have too many series | Baggage copied into metric tags with varying values. | Remove high-cardinality tags, map only finite fields. |
| Traces contain tokens/emails | Unfiltered baggage or metadata written to spans/logs. | Remove data source, add allowlists/filters, review retention/access. |
| Two services have different trace IDs | Trace context propagation broken even if baggage survives or vice versa. | Check `traceparent`/propagator independently from baggage. |

**Trace context and baggage can fail independently.** A request can keep the same trace ID yet lose baggage, or baggage can be forwarded by a custom interceptor while trace context splits. Check both metadata types rather than looking only at a trace ID.

## 14. End-to-End Verification Workflow

A proper test should run in a local environment or controllable integration test:

1. Configure Spring Boot and the OTel bridge/propagator to use W3C Trace Context + Baggage.
2. Declare a few remote baggage fields, such as `region` and `request.class`.
3. Create a baggage context with `region=ap-southeast-1` before calling a gRPC method.
4. Attach the gRPC client interceptor using the same `OpenTelemetry` instance as the application.
5. Attach the matching server interceptor on the RPC-receiving server.
6. In the handler, read baggage from the current OTel context and verify the exact value.
7. In the Collector/backend, confirm client/server spans link by trace ID and metadata is handled per policy.
8. Check logs for trace correlation fields; check baggage in logs only when correlation fields are configured.
9. Send a request without baggage to verify code falls back cleanly without throwing errors.
10. Send a non-allowlisted field or oversized value to verify policy rejects/drops it properly.
11. Verify metrics do not spawn series per request ID or tenant ID.
12. Record metadata sizes and gRPC errors during load testing.

### Testing the Missing-Baggage Case

Do not write code assuming `region` always exists:

~~~java
Baggage baggage = Baggage.fromContext(Context.current());
String region = baggage.getEntryValue("region");

if (region == null || region.isBlank()) {
    region = "unknown";
}
~~~

`unknown` is only an illustrative fallback for logging/diagnostics; do not use it to replace partitioning or authorization decisions. If a service does not require `region`, it is better to leave the field absent than invent a synthetic value.

## 15. Attaching Correlation to Logs and Traces

Baggage can help add request-related metadata to logs or spans when configuration permits. Example log:

~~~text
INFO inventory-service traceId=4f17c38a927d4b55a90714b02f8e6d19 spanId=3a9c31cdb4dcbd74 region=ap-southeast-1 request.class=interactive reserved stock
~~~

`traceId` and `spanId` values typically come from tracing/MDC integration. `region` and `request.class` are present only if baggage correlation is enabled or the application logs them explicitly. Do not assume all baggage fields automatically enter MDC.

Use traces to inspect parent/child spans and dependency timing; use logs to inspect specific messages; use metrics to evaluate aggregated trends. Baggage aids contextual linking across signals, but is not a statistical data source. For example, use `request.class` as a metric dimension only when its value set is finite, controlled, and analytically meaningful.

## 16. Self-Check Exercises

### Exercise 1 — Choosing the Right Metadata

A gRPC call must transmit three items: trace context, `region=ap-southeast-1`, and protobuf field `quantity=5`. Where should each go?

**Answer:** Trace context travels via metadata such as `traceparent`/`tracestate`; `region` can be W3C baggage via metadata key `baggage` if allowed; `quantity` is business data and belongs in the protobuf request message.

### Exercise 2 — Baggage Lost While Trace Remains

Service A calls B over gRPC; the backend shows the same trace ID, yet server B cannot read `region`. What should you check?

**Answer:** Check whether the W3C Baggage propagator is enabled alongside Trace Context, whether `region` is in `remote-fields`, whether client/server gRPC interceptors share the same `OpenTelemetry` context, and whether the server handler executes inside the extracted context.

### Exercise 3 — Oversized Metadata

A team puts 80 user/request fields into baggage so every service can read them. Is this an appropriate design?

**Answer:** No. Baggage is not a general-purpose payload context. Keep only small, allowlisted metadata genuinely needed across services; put business data in request messages, and dedicated investigative data in logs/traces under appropriate policy.

### Exercise 4 — Baggage and Access Control

A caller sends `tenant.tier=premium` in baggage. Should Service B grant the request access to premium features based on that field?

**Answer:** No. Baggage is caller-controllable input, not proof of entitlement. The service must verify identity/claims and policy from a trusted source.

### Exercise 5 — Is Baggage a Metric Tag?

A team wants to attach a request UUID to baggage and use that UUID as a low-cardinality metric tag. What is the problem?

**Answer:** A UUID is nearly unique per request, creating high cardinality. Never use it as a metric label. Use controlled logs or trace attributes to investigate individual requests.

### Exercise 6 — ASCII or Binary Metadata?

Is a text W3C baggage field created with `Metadata.ASCII_STRING_MARSHALLER` or `Metadata.BINARY_BYTE_MARSHALLER`?

**Answer:** W3C baggage is text, so use the ASCII metadata key `baggage`. Binary metadata uses keys suffixed with `-bin` and a byte marshaller; never use a binary marshaller for W3C text fields.

## 17. Implementation Checklist

- [ ] Distinguish trace context, baggage, custom gRPC metadata, and protobuf payloads.
- [ ] Include only allowlisted baggage fields in remote propagation.
- [ ] Enable the W3C Baggage propagator alongside Trace Context in the active `OpenTelemetry` instance.
- [ ] gRPC client/server instrumentation shares tracing context with Spring Boot.
- [ ] Transmit W3C baggage via the ASCII metadata key `baggage`; use `-bin` binary keys only when genuinely needed.
- [ ] Metadata field count and total size are capped per infrastructure limits.
- [ ] No secrets, credentials, emails, request bodies, or sensitive data in baggage.
- [ ] Inbound baggage is treated as untrusted and never used to grant permissions.
- [ ] Async/reactive execution preserves context with proper lifecycle.
- [ ] Logs include baggage correlation fields only when configured and policy-approved.
- [ ] Metrics do not copy high-cardinality baggage into labels.
- [ ] Integration tests verify client injection, server extraction, handler reading, and accurate trace parentage.
- [ ] Test missing baggage, disallowed fields, and oversized metadata cases.
- [ ] Collector/backend enforces limits, retention, and access control for span attributes.

**Key takeaway:** In gRPC, **Metadata is the carrier**, while **W3C Baggage is the context metadata format** that propagators serialize/extract. Use appropriate gRPC instrumentation and OpenTelemetry propagators to pass baggage through client/server interceptors; constrain propagated fields, size, and sensitive data. When properly combined with Micrometer Tracing, metrics, and logs, baggage helps services share correlation context without turning metadata into payloads or authentication channels.
