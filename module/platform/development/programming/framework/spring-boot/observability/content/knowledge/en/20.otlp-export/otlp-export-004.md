# OTLP HTTP Endpoints in Spring Boot Observability

In the **OTLP export** chapter of the **SPRING_BOOT_OBSERVABILITY** module, an OTLP HTTP endpoint is the HTTP address used by an OpenTelemetry exporter to send telemetry to an OpenTelemetry Collector or compatible backend. When a Spring Boot application records metrics, logs, and distributed traces, the endpoint, protocol, path, encoding, and network configuration must match the target receiver. A misconfigured endpoint can cause code to keep generating spans or measurements normally while the backend receives no data.

OTLP stands for **OpenTelemetry Protocol**. The protocol defines how traces, metrics, and logs are transmitted; it can run over gRPC or HTTP/protobuf. This lesson focuses on **OTLP over HTTP**, standard paths, how to configure Spring Boot/Micrometer and the OpenTelemetry SDK, the Collector's role, authentication/TLS, batching/retries, and end-to-end verification.

The **SPRING_BOOT_OBSERVABILITY** module covers Micrometer Observation, metrics, logs, and distributed tracing, including context propagation, tags/cardinality, exporters, and sampling. OTLP export is one link in the observability chain: instrumentation generates telemetry; the exporter sends data; the collector ingests and processes it; and the backend stores and queries it. **Setting an endpoint URL does not automatically create instrumentation, does not enable sampling, and does not turn the endpoint into historical storage.**

## 1. Where Does OTLP HTTP Fit in the Architecture?

A common deployment has a Spring Boot application sending OTLP to an internal Collector, which then routes to one or more backends:

```text
Spring Boot service
    |
    +-- Micrometer Observation / MeterRegistry --> metrics
    |
    +-- Micrometer Tracing / OpenTelemetry SDK --> traces
    |
    +-- Logging bridge / OTel Logs SDK ---------> logs
                 |
                 v
          OTLP HTTP exporter
            HTTP POST + protobuf
                 |
                 v
        OpenTelemetry Collector
          receivers / processors / exporters
                 |
        +--------+---------+
        |        |         |
        v        v         v
     Metrics   Traces     Logs
      backend  backend   backend
```

| Component | Responsibility |
| --- | --- |
| Instrumentation | Creates observations, measurements, spans, or log records |
| SDK/provider | Manages lifecycle, sampling, aggregation, and per-signal processing |
| OTLP exporter | Serializes and sends telemetry via OTLP |
| OTLP HTTP receiver | Accepts HTTP requests with the matching path/content type/protocol |
| Collector processor | Batches, filters, redacts, samples, or transforms per configuration |
| Backend exporter | Transfers data to target storage/observability systems |
| Observability backend | Stores, queries, dashboards, and alerts |

Collectors are often placed close to applications to centralize network management, authentication, routing, buffering, and telemetry processing. Exporting directly to an OTLP-capable backend is also possible; the decision depends on operational and security requirements.

## 2. The Three Signals and Standard Endpoint Paths

OTLP HTTP uses separate requests for each signal:

| Signal | Standard HTTP path | Payload |
| --- | --- | --- |
| Traces | `/v1/traces` | OTLP Trace request |
| Metrics | `/v1/metrics` | OTLP Metrics request |
| Logs | `/v1/logs` | OTLP Logs request |

Example of a Collector accepting OTLP/HTTP at host `otel-collector` and port `4318`:

```text
http://otel-collector:4318/v1/traces
http://otel-collector:4318/v1/metrics
http://otel-collector:4318/v1/logs
```

These are the standard OTLP/HTTP paths. A receiver may be configured with a different base path or proxy prefix; verify your Collector configuration. Do not confuse port `4318` (commonly used for OTLP/HTTP) with port `4317` (commonly used for OTLP/gRPC).

**OTLP HTTP does not mean sending arbitrary JSON to a REST API.** By default, OTLP/HTTP transmits protobuf payloads; JSON encoding is an optional protocol feature, so both exporter and receiver must support and be configured for it. A regular business endpoint accepting JSON is not automatically an OTLP receiver.

## 3. Protobuf, JSON, and HTTP Headers

With OTLP/HTTP, typical request headers look like:

```http
POST /v1/traces HTTP/1.1
Host: otel-collector:4318
Content-Type: application/x-protobuf
Content-Encoding: gzip
Authorization: Bearer <token>
```

- `Content-Type: application/x-protobuf`: OTLP protobuf payload. For JSON encoding, the media type is `application/json` if supported by the exporter/receiver.
- `Content-Encoding: gzip`: use only when the client actually compresses the payload and the receiver supports decompression. If not compressed, omit this header.
- `Authorization`: use only when the receiver/proxy is configured with the corresponding auth mechanism. Do not put tokens directly in source code or logs.

OTLP/HTTP has response semantics defined by the protocol. The exporter must read the status and error details to handle retries or partial success. The Collector may return success at the receiving layer while data is still dropped or fails in downstream processors/exporters; monitor Collector telemetry to confirm the full pipeline.

Do not invent a custom JSON schema and POST it to an endpoint just because the URL ends in `/v1/traces`. If writing a custom client, you must serialize a valid OTLP request envelope/protobuf or defined JSON mapping and handle responses according to the spec.

## 4. Specific Endpoints vs. Base Endpoints

Exporters may take a full signal-specific URL or a base endpoint depending on the API and environment variables:

| Configuration style | Example | Notes |
| --- | --- | --- |
| Signal-specific traces URL | `http://otel-collector:4318/v1/traces` | Complete address for the trace exporter |
| Base endpoint | `http://otel-collector:4318` | The SDK usually appends the signal path automatically when using a shared endpoint |
| Signal-specific variable | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Usually the full URL for traces |
| Generic variable | `OTEL_EXPORTER_OTLP_ENDPOINT` | Usually the base endpoint; the SDK appends the signal path by convention |

With OTLP/HTTP, the generic `OTEL_EXPORTER_OTLP_ENDPOINT` is typically a base URL; signal-specific variables such as `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, and `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` specify per-signal endpoints. Do not append `/v1/traces` a second time to a signal-specific URL.

Example:

```bash
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=orders-service
```

Or specify traces individually:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
```

Variable names, precedence, and support across SDKs/autoconfigure must be checked per version. Do not assume a Spring Boot property automatically reads every OpenTelemetry SDK environment variable if the exporter is configured via a different mechanism.

## 5. Configuring Spring Boot/Micrometer Tracing

For a Spring Boot application using Actuator and Micrometer Tracing, a reference configuration for OTLP trace export may look like this (applicable to versions supporting these properties):

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Explanation:

- `spring.application.name` is the application name; the actual resource must be verified in the backend.
- `management.tracing.sampling.probability` controls trace sampling per the corresponding Spring Boot version's auto-configuration; this does not configure metrics/logs export.
- `management.otlp.tracing.endpoint` is supported by certain Spring Boot versions for OTLP tracing. Check metadata for your exact version and the auto-configured exporter.
- The path above is a signal-specific traces URL for OTLP/HTTP. If a property or exporter expects a base endpoint, use the matching semantics instead of duplicating the path.

Example dependencies when using Micrometer Tracing with the OpenTelemetry bridge and OTLP exporter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
```

Dependency versions should be managed by the Spring Boot BOM. Do not arbitrarily mix the Brave bridge with the OpenTelemetry bridge or create a second SDK alongside auto-configuration. **Merely declaring dependencies does not prove export works**: you must verify the provider, exporter, endpoint, and Collector receiver.

## 6. Configuring OTLP HTTP for Metrics

Spring Boot Actuator/Micrometer can export metrics using the corresponding registry; not every application uses the OTLP metric exporter by default. If choosing the OpenTelemetry Metrics SDK, a standalone reference setup can create a `MeterProvider`, periodic reader, and OTLP HTTP exporter:

```java
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import java.time.Duration;

var exporter = OtlpHttpMetricExporter.builder()
        .setEndpoint("http://otel-collector:4318/v1/metrics")
        .build();

var reader = PeriodicMetricReader.builder(exporter)
        .setInterval(Duration.ofSeconds(30))
        .build();

SdkMeterProvider meterProvider = SdkMeterProvider.builder()
        .registerMetricReader(reader)
        .build();
```

This snippet illustrates the OTLP/HTTP metric exporter in the OpenTelemetry SDK; compatible dependencies/versions are required. Resource, Views, attributes, and lifecycle are omitted to focus on the endpoint. The provider must live alongside the application and close on shutdown; do not create a new provider per request.

If the application uses a Micrometer `MeterRegistry`, configure the Micrometer registry/exporter suited to your chosen backend. Do not assume a standalone OpenTelemetry `SdkMeterProvider` automatically collects all Micrometer meters.

## 7. OTLP HTTP Logs Do Not Appear Automatically When Tracing Is Enabled

Logs are an independent signal. Configuring an OTLP trace exporter does not mean logs will be forwarded to `/v1/logs`. Exporting logs via OTLP requires a logging bridge/appender or an appropriate OpenTelemetry Logs SDK setup, configuring resource and exporter, and verifying that log records are actually sent.

```text
SLF4J / Logback
       |
       +--> console/file appender (if still needed)
       |
       +--> OTel appender/bridge (if configured)
                 |
                 v
            OTel LogRecord
                 |
                 v
           OTLP HTTP exporter
                 |
                 v
              /v1/logs
                 |
                 v
          Collector -> log backend
```

Do not install duplicate bridges/appenders or forward the same log event multiple times. Preserve correlation fields like Trace ID/Span ID when context exists, but do not put credentials, cookies, request bodies, or personal data into log records. Apply filtering/redaction before export.

## 8. OTLP HTTP Receiver on the OpenTelemetry Collector

A Collector needs the OTLP HTTP receiver enabled. Minimal conceptual configuration (exact schema depends on your Collector/contrib distribution):

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

This is an example for testing the receiver with the debug exporter in a development environment. `debug` only lets you inspect data received by the Collector; production needs destination exporters, TLS/auth when appropriate, intentional processors, and resource limits. A pipeline only works when the corresponding signal has a receiver, processor, and exporter declared in `service.pipelines`.

If only the `traces` pipeline is declared, metrics and logs sent to `/v1/metrics` or `/v1/logs` will have no processing pipeline. If the Collector only enables the `grpc` protocol while the application sends HTTP, requests will not be accepted by an HTTP receiver; and vice versa.

When the Collector runs in a container, binding `0.0.0.0:4318` allows listening on the container's interfaces, but appropriate port exposure/network policies are required. Do not expose an unauthenticated OTLP port publicly to the Internet.

## 9. TLS, Authentication, and Networking

Production endpoints typically require HTTPS or mTLS and authentication according to infrastructure policies.

**TLS:** use a hostname matching the certificate SAN, and check the CA chain and expiry. Do not disable certificate verification just to "make it pass". If using a private CA, configure the trust store for the exporter/runtime.

**mTLS:** the Collector/proxy may require a client certificate. The exporter must provide the appropriate certificate/key and trust bundle; configuration details depend on the SDK/exporter.

**Authentication:** the OTLP receiver may be protected by an auth extension, gateway, or service mesh. Supply tokens/passwords via secret management or managed environments; do not commit them to repositories or print them in logs.

**Network:** from inside the application container, `localhost` refers to the current container/pod. Use the DNS/service name on the deployment's network. Check egress policies, firewalls, proxies, DNS, and port mappings.

**Multi-tenancy:** if the backend uses tenant headers or routing keys, only send headers following a protected contract. Do not take arbitrary tenant headers from user requests to route the exporter.

Having the right endpoint still fails to deliver telemetry if the TLS handshake or auth fails. Classify errors across DNS/connect, TLS, HTTP status, OTLP response, and Collector downstream export.

## 10. Batching, Timeouts, Retries, and Partial Success

OTLP exporters usually include batching and timeouts to avoid sending every single span/measurement individually.

| Parameter | Purpose | Risk If Misconfigured |
| --- | --- | --- |
| Batch size | Number of records grouped per export | Too small increases request overhead; too large increases memory/latency |
| Schedule/delay | Batch send cadence | Too long delays telemetry |
| Export timeout | Request wait limit | Too low causes false timeouts; too high holds resources longer |
| Retry/backoff | Retries transient failures | Unbounded retries can create storms |
| Queue capacity | Number of records queued for sending | Too small drops early; too large increases memory |

Not all errors should be retried equally. Connection errors, timeouts, or retryable responses may be retried per exporter policy; data/format errors or authentication failures usually require configuration fixes and should not be retried indefinitely. OTLP defines partial success semantics for certain signals/versions: an HTTP request may be partially accepted with the response carrying details on rejected records. The exporter/SDK must handle responses per the protocol.

Batching introduces latency before telemetry appears in the backend. During testing, wait long enough for an export cycle or use proper force-flush/shutdown in demos. In production, do not force-flush on every request because it defeats batching and increases overhead.

## 11. Spring Boot Service With Multiple Signals

An application can use different pipelines:

| Signal | API/instrumentation | Example export path |
| --- | --- | --- |
| Traces | Micrometer Tracing bridge or OTel Tracer | OTLP traces endpoint |
| Metrics | Micrometer `MeterRegistry` or OTel `MeterProvider` | OTLP metrics endpoint or Prometheus scrape |
| Logs | SLF4J/Logback and OTel bridge/appender | OTLP logs endpoint or log agent |

All three signals do not have to use OTLP. For instance, a system can scrape Prometheus metrics, send traces via OTLP HTTP, and use a log agent to collect stdout. What matters is:

- Knowing which signal flows through which pipeline.
- Consistent service identity/resource attributes.
- Proper trace propagation and sampling.
- Keeping metrics low-cardinality with sufficient coverage.
- Logs carrying trace/span correlation when context is available.
- Not emitting the same event through two exporters and double-counting in the backend.

## 12. Diagnosing OTLP HTTP Endpoint Issues

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| Connection refused | Collector not running, wrong port, or bind | Check receiver, container port, and network |
| DNS resolution failure | Wrong service name/namespace | Check DNS and deployment network |
| 404 Not Found | Wrong path, base-vs-signal endpoint mismatch, or receiver disabled | Check signal paths and proxy prefixes |
| 415 Unsupported Media Type | Content-Type/encoding unsupported by receiver | Check protobuf vs. JSON and exporter protocol |
| 401/403 | Token, auth policy, or permissions | Check secrets, proxy/Collector auth |
| TLS handshake/certificate error | CA, hostname, certificate/key, or TLS version | Check trust chain and SAN |
| HTTP 200 but backend is empty | Collector accepts request but downstream pipeline/exporter fails or query is wrong | Check Collector exporter errors, pipeline, and backend labels |
| Only traces have data | Metrics/log exporters or corresponding pipelines not configured | Check each of the three signals separately |
| Data arrives late | Batch interval or queue | Check periodic reader, batch, and timeout |
| Missing spans | Sampling, queue overflow, partial success, or exporter drops | Check sampled ratio, SDK/Collector dropped counters |
| Duplicate metric series | Two pipelines emit the same event or duplicate scrape | Check registry/exporter and target discovery |

### Testing With an HTTP Client

You can check TCP/HTTP reachability to the endpoint, but an empty request is not a valid OTLP payload:

```bash
curl -i http://otel-collector:4318/
```

The command above only checks connectivity/response on the root path; it does not prove `/v1/traces` received valid OTLP data. Do not use `curl` to POST random JSON to conclude the exporter works. A reliable verification sends telemetry from a real exporter or a spec-compliant OTLP client, then inspects the Collector receiver/pipeline/exporter.

## 13. End-to-End Verification Workflow

1. **Verify receiver:** the Collector enables the right OTLP HTTP protocol and port and binds to the right interface.
2. **Check paths:** traces, metrics, and logs use the right path or signal-specific endpoint expected by the SDK.
3. **Check protocol:** the exporter uses HTTP/protobuf or JSON according to matching capabilities; do not confuse gRPC with HTTP.
4. **Check network/TLS/auth:** DNS, routing, certificates, bearer/mTLS, and secret injection.
5. **Generate a traced request:** call a Spring Boot HTTP endpoint and verify server/client/business spans according to the sampling policy.
6. **Record known metric values:** increment a counter/record a histogram; verify the reader/exporter works.
7. **Emit structured logs:** verify the appender/bridge sends log records and proper correlation fields if enabled.
8. **Observe the Collector:** the receiver accepts records, processors run, and target exporters do not reject/drop.
9. **Check the backend:** verify service/resource, signal, unit, labels, and ingestion timestamp.
10. **Check shutdown/batching:** ensure final data flushes when the test process exits; manage lifecycle properly in production.

### Test Matrix

| Test | Expected Outcome |
| --- | --- |
| Send trace via real exporter | Collector receives trace request on the right path |
| Send metrics via metrics exporter | Collector has a metrics pipeline receiving records |
| Send logs via logging bridge | Collector has a logs pipeline receiving records |
| Use wrong path | Receive corresponding error, not mistaken for an instrumentation bug |
| Use HTTP when receiver enables only gRPC | Fails to connect properly; fix protocol/receiver |
| Use full signal endpoint and append path again | Wrong path; fix base vs. signal URL semantics |
| Invalid token | Auth returns error; secret is not logged |
| Collector accepts but backend exporter fails | Receiver metrics may still increment; check downstream exporter errors |
| Head sampling drops trace | Metrics may still appear even though trace is missing |
| Close demo application | Flush/close per lifecycle so the final batch is not lost |

## 14. Scenario Exercise

A team deploys Spring Boot with the endpoint:

```yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Application logs show requests succeed. The Collector records traces, but metrics and logs do not appear in the backend. The team tries changing the endpoint to a URL that appends `/v1/metrics` onto the traces path and sees no improvement.

**Questions:**

1. Why does the traces endpoint not automatically configure metrics and logs?
2. Is the new path valid?
3. Which components need to be checked to send metrics and logs over OTLP HTTP?
4. If the Collector receives traces but the backend has no data, which layers must be distinguished?

**Analysis hints:**

- The property in the example only configures the tracing exporter; metrics need a separate registry/OTel `MetricReader` and exporter, and logs need a separate OTel logging bridge/appender or SDK pipeline.
- Appending another signal path onto the traces URL is wrong. Standard metrics endpoints have their own path `/v1/metrics` and logs have `/v1/logs`.
- Identify the actual pipelines: Micrometer registry or OTel `SdkMeterProvider`; whether SLF4J/Logback has a bridge/appender; whether the Collector has `metrics`/`logs` pipelines and downstream exporters.
- Separate checks across the application exporter, OTLP receiver, Collector processors/exporters, and backend ingest/query. An HTTP receiver accepting traces does not guarantee downstream exporters succeeded.

### Completion Checklist

| Topic | Can Explain/Verify |
| --- | --- |
| OTLP over HTTP | Distinguish from OTLP/gRPC |
| Signal paths | Remember traces, metrics, and logs have separate endpoints |
| Base vs. full endpoint | Do not append duplicate paths |
| Encoding/headers | Understand protobuf, JSON, `Content-Type`, `Content-Encoding` |
| Spring Boot trace export | Verify properties/dependencies match the version |
| Metrics export | Identify Micrometer registry or OTel `MetricReader` |
| Logs export | Identify appender/bridge/SDK |
| Collector receiver/pipelines | Enable the right protocol and signals |
| TLS/auth/network | Do not expose unprotected OTLP receivers publicly |
| Batch/retry/partial success | Distinguish exporter errors from downstream rejection |
| End-to-end verification | Verify receiver, processor, exporter, and backend |

**Key takeaway:** OTLP HTTP is the standard transport for sending traces, metrics, and logs via signal-specific endpoints such as `/v1/traces`, `/v1/metrics`, and `/v1/logs`. You must match the endpoint, base-vs-full URL, protocol, encoding, TLS/auth, and Collector pipeline. Spring Boot tracing export does not automatically enable metrics/logs export; each signal needs appropriate instrumentation and exporters. Verify from the application through the receiver, processor, and exporter to the backend while monitoring batching, retries, partial success, and dropped telemetry to ensure observability truly works in production.
