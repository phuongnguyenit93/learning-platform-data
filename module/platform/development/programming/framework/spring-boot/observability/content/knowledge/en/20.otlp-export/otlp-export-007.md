# Endpoint Fallback When Configuring OTLP in Spring Boot

## 1. Learning Objectives

A Spring Boot application can export three types of telemetry over the OpenTelemetry Protocol (OTLP): **traces**, **logs**, and **metrics**. They are often sent to the same OpenTelemetry Collector yet hit different routes. Having to repeat address, headers, and compression for each signal makes configuration drift across environments easily.

**Endpoint fallback** lets you declare a shared OTLP endpoint as the default and override it with a dedicated endpoint for traces, logs, or metrics when needed. Spring Boot uses the shared endpoint when a signal lacks its own endpoint; when exporting over HTTP, Boot automatically appends the signal's standard path. This lesson belongs to the **OTLP export** chapter of the **SPRING_BOOT_OBSERVABILITY** module, which teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, distributed tracing, context propagation, cardinality, exporters, and sampling.

After this lesson, you will be able to determine endpoint precedence order; understand the paths appended during HTTP fallback; configure common headers and signal-specific headers; explain OTLP environment variables; distinguish Spring Boot 4.x from 3.5.x; verify effective endpoints; and diagnose exporter errors.

**Version scope:** the endpoint fallback section focuses on **Spring Boot 4.0.x**. Spring Boot 3.5.x configures OTLP per signal and does not have the same common endpoint property for fallback as Boot 4. Do not copy properties between the two release lines without checking the documentation.

## 2. OTLP Signals

| Signal | Contents | Standard OTLP/HTTP Path |
| --- | --- | --- |
| Traces | Span records and trace relationships | `/v1/traces` |
| Logs | Structured log records | `/v1/logs` |
| Metrics | Metric data points | `/v1/metrics` |

One Collector can receive all three signals on the same HTTP host/port, yet each signal uses a separate route.

```mermaid
flowchart TD
    APP["Spring Boot application"]
    COMMON["Common endpoint<br/>https://collector.example:4318"]
    T["Traces exporter"]
    L["Logs exporter"]
    M["Metrics exporter"]
    TR["/v1/traces"]
    LR["/v1/logs"]
    MR["/v1/metrics"]
    COL["OpenTelemetry Collector"]
    APP --> T
    APP --> L
    APP --> M
    COMMON -. fallback .-> T
    COMMON -. fallback .-> L
    COMMON -. fallback .-> M
    T --> TR
    L --> LR
    M --> MR
    TR --> COL
    LR --> COL
    MR --> COL
```

The shared endpoint provides a **base URL** when a signal does not have its own endpoint. It does not make the signals share a single request path.

## 3. Common Endpoint and Per-Signal Endpoints

Spring Boot 4.x supports common OTLP configuration under the `management.opentelemetry.otlp.` prefix. The common endpoint is `management.opentelemetry.otlp.endpoint`.

| Signal | Signal-Specific Endpoint Property |
| --- | --- |
| Traces | `management.opentelemetry.tracing.export.otlp.endpoint` |
| Logs | `management.opentelemetry.logging.export.otlp.endpoint` |
| Metrics | `management.otlp.metrics.export.url` |

### 3.1. Precedence Rules

**If a signal-specific endpoint is set:** the exporter uses that specific endpoint verbatim; Spring Boot does not append a signal path to that URL. The common endpoint continues to act as a fallback for other signals without their own endpoint.

**If no signal-specific endpoint is set:** the exporter uses the common endpoint. When the signal exports over HTTP, Boot appends the standard path:

| Signal | Common Endpoint | Effective URL |
| --- | --- | --- |
| Traces | `https://collector.example:4318` | `https://collector.example:4318/v1/traces` |
| Logs | `https://collector.example:4318` | `https://collector.example:4318/v1/logs` |
| Metrics | `https://collector.example:4318` | `https://collector.example:4318/v1/metrics` |

Do not add a signal path to the common base URL and expect Boot to append paths properly on top of it.

### 3.2. Example: Signal-Specific Endpoint Overriding Common

The common endpoint is `https://collector.example:4318`. The traces-specific endpoint is `https://trace-gateway.example/tenant-a/v1/traces`.

Outcome:
- Traces send to the signal-specific endpoint verbatim.
- Logs fall back to `https://collector.example:4318/v1/logs`.
- Metrics fall back to `https://collector.example:4318/v1/metrics`.

This is useful when traces require a dedicated gateway/tenant while logs and metrics use a shared Collector.

## 4. Configuring the Common Endpoint in Spring Boot 4

Example `application.yml`:

```yaml
spring:
  application:
    name: checkout-service

management:
  opentelemetry:
    otlp:
      endpoint: https://otel-collector.observability.svc:4318
      compression: gzip
      headers:
        Authorization: Bearer OTLP_AUTH_TOKEN_FROM_SECRET
    resource-attributes:
      deployment.environment: production
  tracing:
    sampling:
      probability: 0.1
```

Meaning:
- `management.opentelemetry.otlp.endpoint` is the shared base endpoint.
- `compression` and `headers` apply to exports using the common configuration when a signal does not override them.
- `resource-attributes` describes the emitting service/environment; it is not an endpoint.
- Sampling probability affects which traces are kept; it does not change endpoints and does not enable/disable metrics/logs exporters.

`OTLP_AUTH_TOKEN_FROM_SECRET` is a placeholder. Inject secrets from a secret store or deployment environment; do not commit real tokens or log the `Authorization` header.

### 4.1. Overriding One Signal

Example where traces need to go through a separate gateway while logs and metrics still use the shared Collector:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example:4318
      headers:
        Authorization: Bearer OTLP_COMMON_TOKEN_FROM_SECRET
      compression: gzip
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.example/tenant-a/v1/traces
          headers:
            X-Tenant: tenant-a
```

Effective endpoints:

| Signal | Endpoint |
| --- | --- |
| Traces | `https://trace-gateway.example/tenant-a/v1/traces` |
| Logs | `https://collector.example:4318/v1/logs` |
| Metrics | `https://collector.example:4318/v1/metrics` |

Traces do not use the common endpoint because a signal-specific endpoint is defined. Logs and metrics still fall back.

## 5. Common Headers and Signal-Specific Headers

Spring Boot merges common headers with signal-specific headers. If the same key appears in both places, **the signal-specific value wins**.

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example:4318
      headers:
        Authorization: Bearer OTLP_COMMON_TOKEN
        X-Environment: production
    tracing:
      export:
        otlp:
          headers:
            Authorization: Bearer OTLP_TRACE_TOKEN
            X-Tenant: trace-team
```

Effective headers for traces:
- `Authorization` uses `OTLP_TRACE_TOKEN` because the key collides and signal-specific overrides.
- `X-Environment` remains `production` because it exists only in common.
- `X-Tenant` is `trace-team` because it exists only in tracing-specific.

Logs and metrics still use the common `Authorization` and `X-Environment` if they lack dedicated overrides. Header merging is a configuration mechanism; credentials and ingest permissions still need to be scoped per trust boundary.

## 6. Environment Variable Fallback

Spring Boot supports mapping a set of OpenTelemetry SDK environment variables to configuration properties.

| Environment variable | Scope |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Common endpoint |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Dedicated endpoint for traces |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Dedicated endpoint for logs |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Dedicated endpoint for metrics |

If both a signal-specific variable and the common variable exist:
- The signal-specific variable takes precedence and is used as the exact URL.
- The common variable serves only as a fallback when no per-signal variable is present.
- When the common endpoint is used as a fallback over HTTP, Boot appends the matching signal path.

Example:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://traces.example/otlp/v1/traces
```

Outcome:
- Traces use the dedicated URL verbatim.
- Logs fall back to `https://collector.example:4318/v1/logs`.
- Metrics fall back to `https://collector.example:4318/v1/metrics`.

If only the common endpoint is set:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

then traces over HTTP use `http://localhost:4318/v1/traces`; logs use `/v1/logs` and metrics use `/v1/metrics`.

Mapping of environment variables can be disabled with:

```yaml
management:
  opentelemetry:
    map-environment-variables: false
```

When mapping is disabled, do not rely on `OTEL_EXPORTER_OTLP_*` expecting Boot to bind them automatically into Spring properties; use application properties or another configuration mechanism.

### 6.1. Property Sources and Effective Configuration

Values can come from application YAML, profiles, container environment variables, ConfigMaps/secret stores, command-line arguments, or external config sources. Spring Boot has precedence rules across property sources; do not resolve conflicts by guessing.

Inspect the effective configuration through deployment checks, `configprops` if safely exposed, or binding tests. Do not dump secrets to logs. Remember that signal-specific OTLP environment variables are complete URLs; the common endpoint is a base URL that gets a signal path appended on HTTP fallback.

## 7. OTLP/HTTP and OTLP/gRPC

Endpoint fallback appends signal paths for **HTTP**. Identify which transport the exporter is using.

| Transport | Typical Connection | Routing |
| --- | --- | --- |
| OTLP/HTTP | HTTP(S), typically port 4318 | Uses `/v1/traces`, `/v1/logs`, `/v1/metrics` |
| OTLP/gRPC | gRPC, typically port 4317 | Uses RPC service/method; do not append HTTP paths to URL |

Do not copy an HTTP URL with a `/v1/traces` suffix to a gRPC exporter. Check the exporter's transport property and the Spring Boot docs for your exact version. Do not assume gRPC handles base URLs identically to HTTP.

If the receiver only enables OTLP/HTTP while the application uses gRPC, connection errors can occur even when the host is right. Sending HTTP to a gRPC port can also trigger protocol errors.

## 8. Distinguishing Spring Boot 3.5 and 4.x

### 8.1. Spring Boot 4.x

Boot 4 has the common endpoint property `management.opentelemetry.otlp.endpoint`. Per-signal endpoints are:
- Traces: `management.opentelemetry.tracing.export.otlp.endpoint`
- Logs: `management.opentelemetry.logging.export.otlp.endpoint`
- Metrics: `management.otlp.metrics.export.url`

The common endpoint acts as a fallback for signals without a dedicated endpoint. During HTTP fallback, Boot appends the corresponding path.

### 8.2. Spring Boot 3.5.x

Boot 3.5 uses separate properties for OTLP tracing:

```yaml
management:
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
      transport: http
      export:
        enabled: true
  tracing:
    sampling:
      probability: 0.1
```

OTLP metrics use a different group:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 1m
```

Spring Boot 3.5 does not have the same `management.opentelemetry.otlp.endpoint` common endpoint property for shared fallback as Boot 4. Do not use Boot 4 examples on a Boot 3.5 project and conclude the exporter is configured.

| Topic | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| Common OTLP endpoint fallback | No equivalent common property | `management.opentelemetry.otlp.endpoint` |
| Traces endpoint | `management.otlp.tracing.endpoint` | `management.opentelemetry.tracing.export.otlp.endpoint` |
| Metrics endpoint | `management.otlp.metrics.export.url` | `management.otlp.metrics.export.url` |
| OTLP logs | No equivalent common logs exporter model | Has logging OTLP properties |
| Common headers/compression | Configured per exporter | Has common OTLP properties and signal overrides |

Always verify the actual version from the Spring Boot BOM/runtime. Do not infer versions solely from Micrometer dependencies or module names.

## 9. Docker/Kubernetes Example

Inside a container, `localhost` points to the application container's network namespace, not necessarily the Collector. Use a service DNS reachable from the pod:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: http://otel-collector.observability.svc.cluster.local:4318
      headers:
        Authorization: Bearer OTLP_TOKEN_FROM_SECRET
      compression: gzip
```

When no signal-specific endpoints are declared, traces, logs, and metrics fall back to the same host/port with their respective paths.

If traces and logs have dedicated gateways:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-gateway.internal:4318
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.internal/team-a/v1/traces
    logging:
      export:
        otlp:
          endpoint: https://log-gateway.internal/team-a/v1/logs
```

Metrics have no dedicated endpoint so they fall back to the shared Collector. Traces and logs use separate gateways; each dedicated URL is a complete URL including its path.

## 10. Verifying the Effective Endpoint

Do not just look at YAML and assume the exporter sends to the right target. Verify in order:

1. Confirm the actual Spring Boot version from dependency management/build metadata.
2. Check which common endpoint, signal-specific endpoints, and environment variables are set.
3. Verify whether signal-specific endpoints override the common endpoint.
4. Compute the final URL: dedicated endpoints are used verbatim; common fallback appends the signal path for HTTP.
5. Confirm exporter transport matches the receiver.
6. Verify common headers and signal-specific headers merged properly.
7. Send one trace, log record, and metric sample in a test environment.
8. Check Collector access logs to see requests reaching the matching signal paths.
9. Check the Collector pipeline and backend ingest; the Collector receiving data does not mean the backend stored it.
10. Remove the dedicated endpoint in a test profile to confirm common fallback works.

| Common endpoint | Dedicated endpoint | Result |
| --- | --- | --- |
| `https://collector:4318` | None, traces HTTP | `https://collector:4318/v1/traces` |
| `https://collector:4318` | None, logs HTTP | `https://collector:4318/v1/logs` |
| `https://collector:4318` | None, metrics HTTP | `https://collector:4318/v1/metrics` |
| `https://collector:4318` | `https://trace.example/custom` | `https://trace.example/custom` |

## 11. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Traces reach the right Collector, metrics do not | Metrics exporter disabled or overridden by separate URL | Check `management.otlp.metrics.export.enabled`/`url` |
| Logs missing even though traces exist | Logging OTLP exporter or Collector logs pipeline not enabled | Check logging OTLP exporter and receiver |
| Requests hit `/v1/traces/v1/traces` | Common endpoint already included suffix and fallback appended again | Remove signal path from common base URL |
| Requests hit `/` instead of `/v1/metrics` | Signal-specific endpoint used verbatim without path | Set complete dedicated endpoint `/v1/metrics` |
| HTTP 404 | Wrong route or gateway not routing signal path | Check path and receiver |
| HTTP 415 | Wrong content type/protocol or mixed-up HTTP/gRPC port | Match transport and receiver |
| HTTP 401/403 | Wrong token/headers or insufficient ingest permissions | Check secret and header precedence |
| Common endpoint has no effect | Overridden by signal-specific property or env var | Check dedicated endpoints and property sources |
| Common header disappears | Overridden by signal-specific header with the same key | Check merge rules |
| Common URL looks right but times out | DNS, network policy, TLS, receiver, or port | Test from the actual container/pod |
| Boot 3.5 ignores common endpoint | Used Boot 4 property in a 3.5 project | Use 3.5 per-signal properties |
| Collector receives but backend is empty | Collector exporter/backend ingest error | Check pipeline and backend logs |

### 11.1. Why Shouldn't the Common Endpoint Include a Signal Path?

Suppose the common endpoint is:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example/otlp/v1/traces
```

When used as a common fallback for traces, logs, and metrics over HTTP, Boot appends each signal path to the base URL. For logs, the URL can become:

`https://collector.example/otlp/v1/traces/v1/logs`

This is typically not the logs route the gateway expects.

How to fix:
- The common endpoint should contain only the scheme, host, port, and shared base path supported by the Collector/gateway.
- If the gateway requires custom per-signal paths, configure a dedicated endpoint for each signal.
- Do not guess gateway paths; check the actual routes in the deployment environment.

## 12. Security and Operations

- Store tokens in a secret store or environment secret; do not commit tokens.
- Use TLS when sending across untrusted networks and verify certificates.
- Scope OTLP ingest permissions by service/environment/tenant.
- Use common headers for truly shared metadata; use separate credentials if ingest permissions differ.
- Do not log `Authorization` headers or full telemetry payloads in production.
- Tune timeouts, batches, queues, retries, and compression to Collector/backend capacity.
- Monitor exporter failures, dropped spans/logs/metrics, and Collector queue saturation.
- Test signal-specific paths when using gateways/reverse proxies.
- Do not leave a default `localhost` endpoint active outside environments where it genuinely points to a Collector.
- Ensure the Collector has receiving and exporting pipelines for every signal.

## 13. Self-Practice Questions

1. What is the precedence relationship between the common endpoint and a signal-specific endpoint?
2. With common endpoint `https://collector.example:4318`, which HTTP URLs do traces/logs/metrics use?
3. Why is a dedicated endpoint `https://trace.example/custom` used verbatim without appending a path?
4. When common headers have `Authorization` A and tracing-specific headers have `Authorization` B, which token do traces send?
5. How does `OTEL_EXPORTER_OTLP_ENDPOINT` differ from `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`?
6. Why does common endpoint fallback over HTTP need to append the signal path?
7. If the common endpoint already contains `/v1/traces`, what can happen to logs and metrics?
8. Why shouldn't you copy Boot 4's `management.opentelemetry.otlp.endpoint` into a Boot 3.5 project?
9. When an exporter sends to port 4317 while using HTTP transport, how might errors appear?
10. The Collector receives spans yet the backend has no traces; which pipeline should you inspect?
11. When should you use the common endpoint, and when should you override one signal?
12. How do you test endpoint fallback in a container environment?

## References

- [Spring Boot 4.0 — Observability and Common OTLP Configuration](https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/)
