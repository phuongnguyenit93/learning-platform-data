# management.opentelemetry

In the **SPRING_BOOT_OBSERVABILITY** module, Spring Boot combines Micrometer Observation, metrics, logs, and distributed tracing to help development teams observe application behavior. The `management.opentelemetry` configuration namespace is part of Spring Boot Actuator's OpenTelemetry integration. It controls several Boot-managed OpenTelemetry behaviors, including enabling/disabling support, resource attributes, mapping a subset of environment variables, and shared OTLP configuration in supported versions.

The key point is that this namespace **is not a master switch that automatically exports all telemetry**. Traces, logs, and metrics still have separate pipelines, dependencies, and auto-configuration levels. Spring Boot uses Micrometer for metrics and Observation/Tracing for traces; the OpenTelemetry Logs SDK has its own configuration; and bridging log events from SLF4J/Logback into OpenTelemetry is another integration boundary. This lesson explains how to read and use `management.opentelemetry` accurately, avoiding wrong endpoint setups or expecting one signal to export just because another signal works.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify the role of the `management.opentelemetry` namespace in Spring Boot Actuator.
2. Distinguish basic OpenTelemetry support, Micrometer Tracing, the OpenTelemetry Logs SDK, and Micrometer metrics.
3. Configure resource attributes such as `service.name`, `service.version`, and `deployment.environment`.
4. Set OTLP endpoints, headers, and compression at shared and per-signal levels.
5. Understand precedence among common properties, signal-specific properties, and environment variables.
6. Distinguish OTLP/HTTP from OTLP/gRPC and understand how signal paths are constructed.
7. Know when Boot auto-configures trace export and when separate configuration is needed for logs/metrics.
8. Inspect the impact of `enabled`, custom `Resource` beans, and `map-environment-variables`.
9. Protect credentials, limit payloads, and monitor export status.
10. Diagnose cases where traces exist without logs/metrics or where service identity is wrong.

## 2. Where Does the `management.opentelemetry` Namespace Sit?

Spring Boot Actuator provides OpenTelemetry support integrated with the application context. In supported versions, Boot can create an `OpenTelemetry` bean and a `Resource` bean; SDK providers such as `SdkTracerProvider`, `SdkLoggerProvider`, `ContextPropagators`, or `SdkMeterProvider`, if registered in the application context, can be wired into the Boot-managed `OpenTelemetry` instance.

Primary property groups:

| Property Group | Role |
| --- | --- |
| `management.opentelemetry.enabled` | Enables/disables Spring Boot's OpenTelemetry support. |
| `management.opentelemetry.resource-attributes` | Declares resource attributes for telemetry. |
| `management.opentelemetry.map-environment-variables` | Controls mapping a subset of OpenTelemetry SDK environment variables to Spring Boot properties. |
| `management.opentelemetry.otlp` | Shared OTLP settings such as endpoint, headers, and compression in supported versions. |
| `management.opentelemetry.tracing` | Configures samplers, export, and limits related to traces. |
| `management.opentelemetry.logging` | Configures export and limits for OpenTelemetry logs in supported versions. |

~~~mermaid
flowchart TB
    Config["application.yml / environment"]
    Config --> Manage["Spring Boot Actuator"]
    Manage --> OTEL["OpenTelemetry bean"]
    Manage --> Resource["Resource attributes"]
    OTEL --> Trace["SdkTracerProvider / Micrometer Tracing"]
    OTEL --> Logs["SdkLoggerProvider / OTel Logs"]
    OTEL --> Metrics["SdkMeterProvider if app uses it directly"]
    Trace --> TraceExport["OTLP traces exporter"]
    Logs --> LogExport["OTLP logs exporter"]
    Metrics --> MetricExport["OTLP metrics exporter"]
    TraceExport --> Collector["OTLP Collector"]
    LogExport --> Collector
    MetricExport --> Collector
~~~

The diagram illustrates components that can participate alongside the `OpenTelemetry` instance. It does not mean Spring Boot always auto-creates all three SDK providers or exports all three signals automatically. Read the exact version and actual auto-configuration setup.

## 3. Check Your Version Before Using Properties

Namespaces and auto-configuration scope differ across Spring Boot release lines. Spring Boot 4.2 documentation describes shared OTLP configuration under `management.opentelemetry.otlp`, signal-specific properties for tracing/logging, and OTLP logging auto-configuration. Spring Boot 3.5 documentation describes basic OpenTelemetry support and resource attributes, yet does not present the same common OTLP property set and logging auto-configuration as the 4.2 documentation.

Therefore:

- Do not assume every property in this lesson exists in Spring Boot 3.x.
- With Boot 3.5, check the Application Properties Appendix and reference for the exact minor version; some OpenTelemetry features have narrower scope.
- With Boot 4.x, check the documentation for the exact minor release because property names/defaults can change.
- If a property fails to bind, inspect configuration metadata and startup logs rather than guessing.
- Do not add exporters/dependencies merely because you saw a property in documentation for another version.

Official documentation to reference:
- Spring Boot Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot 3.5 Observability: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- Spring Boot Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/

## 4. Enabling/Disabling OpenTelemetry Support

In supported versions, the `enabled` property controls Boot's OpenTelemetry integration:

~~~yaml
management:
  opentelemetry:
    enabled: true
~~~

It can be disabled:

~~~yaml
management:
  opentelemetry:
    enabled: false
~~~

When set to `false`, related OpenTelemetry components may use no-op implementations as described for that Boot version; context propagators may still continue working. This **does not mean all application metrics are disabled**, because Spring Boot uses Micrometer as its primary metrics choice. The Micrometer registry can still collect/export metrics through its own pipeline.

Do not use `enabled=false` as a substitute for disabling OTLP logs or traces individually. If you only want to stop sending one signal, configure that specific signal's export setting. After changing it, verify the metrics endpoint, traces, and logs separately.

## 5. Configuring Resource Attributes

Resource describes the telemetry emission source, such as service name, version, environment, and namespace. It is used to group logs/traces/metrics by service or deployment context.

~~~yaml
spring:
  application:
    name: order-api

management:
  opentelemetry:
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
      service.namespace: commerce
~~~

This is an example. In real systems, service name/version/environment should come from deployment configuration or build metadata.

Principles:
- `service.name` must be stable and identical across signals of the same service.
- `service.version` is useful when comparing before/after a release.
- `deployment.environment` or namespace helps separate production, staging, and development.
- Do not put request ID, order ID, email, or user ID into Resource; those values change per request and cause resource group explosions.
- Resource attributes describe the process/service; span/log attributes describe a single operation or event.

### Precedence Between Properties and Environment

Spring Boot documentation states that the auto-configured `Resource` is merged with `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME`; attributes configured via `management.opentelemetry.resource-attributes` take higher precedence than those environment variables.

Example environment:

~~~text
OTEL_SERVICE_NAME=order-api-default
OTEL_RESOURCE_ATTRIBUTES=service.version=2.3.0,deployment.environment=staging
~~~

If configured in a file:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.version: "2.3.1"
      deployment.environment: production
~~~

Values declared in Spring Boot properties win on conflict according to the merge rules. Verify the actual `Resource` in the exporter/backend because this merge applies to Boot's auto-configured `Resource`.

**If the application defines its own `Resource` bean**, the auto-configured merge flow described above will no longer apply the same way. When creating a custom `Resource` bean, the application is responsible for merging the needed attributes itself, including service identity and environment metadata.

## 6. Shared OTLP Configuration

In Spring Boot versions with common OTLP configuration, you can declare a shared endpoint, headers, and compression across signals:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otlp.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer REPLACE_WITH_SECRET
~~~

Meaning:
- `endpoint` is the shared base endpoint of OTLP exporters.
- `compression` configures payload compression if supported by the exporter/signal.
- `headers` carries metadata needed for the exporter to authenticate or route.
- Credentials come from a secret manager/environment injection; do not commit real tokens into the repository.

Each signal's exporter may require its own endpoint, transport, or credentials.

### Common vs. Signal-Specific Properties

Signal-specific properties take higher precedence than common values when set:

| Signal | Illustrative Dedicated Endpoint |
| --- | --- |
| Traces | `management.opentelemetry.tracing.export.otlp.endpoint` |
| Logs | `management.opentelemetry.logging.export.otlp.endpoint` |
| Metrics | `management.otlp.metrics.export.url` |

For headers, per-signal headers are merged with common headers; the signal-specific value wins on key collisions.

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer COMMON_SECRET
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.example.com:4318
    logging:
      export:
        otlp:
          endpoint: https://logs-gateway.example.com:4318
~~~

In this example, traces and logs go to separate gateways; the common endpoint serves as fallback for signals without an explicit endpoint. Do not use this example if your Spring Boot minor version lacks the corresponding logging export namespace.

## 7. Common Endpoint, Signal Paths, and OTLP Transport

When the common endpoint is used as a fallback and the signal exports over HTTP, Spring Boot appends the signal-specific path:

| Signal | HTTP Path |
| --- | --- |
| Traces | `/v1/traces` |
| Logs | `/v1/logs` |
| Metrics | `/v1/metrics` |

For example, with common endpoint `https://collector.example.com:4318`, the final HTTP URLs can be:
- `https://collector.example.com:4318/v1/traces`
- `https://collector.example.com:4318/v1/logs`
- `https://collector.example.com:4318/v1/metrics`

When a signal-specific endpoint is set, it is used according to that property's own rules; do not assume a common path is appended to every specified endpoint.

### HTTP and gRPC Differ

| Property | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Common port | 4318 | 4317 |
| Signal path | `/v1/traces`, `/v1/logs`, `/v1/metrics` | RPC services, does not use HTTP signal URL paths as above |
| Protocol | HTTP/protobuf | gRPC |
| Testing | HTTP status/receiver logs | gRPC status/connectivity/receiver logs |

Ports are common defaults and can be changed in the Collector. Ensure exporter transport matches the receiver. Do not change 4318 to 4317 in an HTTP endpoint expecting the client to switch to gRPC automatically.

## 8. Environment Variables and `map-environment-variables`

Spring Boot supports mapping a subset of OpenTelemetry SDK environment variables to configuration properties at startup. The `map-environment-variables` property controls this behavior in supported versions:

~~~yaml
management:
  opentelemetry:
    map-environment-variables: true
~~~

Mapping can be disabled:

~~~yaml
management:
  opentelemetry:
    map-environment-variables: false
~~~

When mapping is active, signal-specific environment variables take precedence over generic variables. When the generic endpoint is used as fallback, Spring Boot appends the signal path for HTTP export. Unsupported environment variables do not automatically take effect simply by starting with `OTEL_`.

Example:

~~~text
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example.com:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://trace-gateway.example.com:4318/custom-traces
OTEL_SERVICE_NAME=order-api
OTEL_RESOURCE_ATTRIBUTES=service.version=2.3.1,deployment.environment=production
~~~

For a variable in the supported subset, Spring Boot maps it to a property at startup. A generic endpoint acting as fallback for traces can construct the `/v1/traces` URL; a signal-specific endpoint is used as explicitly configured.

### Not All OpenTelemetry SDK Environment Variables Are Supported

Spring Boot documentation explicitly lists support for only a subset. If you need every environment variable understood by the OpenTelemetry SDK, the docs note that you can provide a custom `OpenTelemetry` bean via SDK autoconfigure; however, doing so shifts ownership of OpenTelemetry auto-configuration away from Spring Boot and may break built-in observability integrations.

Therefore:
1. Check the mapping list in the documentation for your exact version.
2. Enable mapping only when you want Spring Boot to apply the supported variable subset.
3. If a variable is unsupported, do not assume Boot will read it.
4. Replace Boot auto-configuration with OpenTelemetry SDK autoconfigure only when explicitly required and affected features have been tested.

## 9. Traces: Relationship With Micrometer Tracing

Spring Boot integrates OpenTelemetry tracing through Micrometer Tracing. With Micrometer Tracing and matching dependencies/configuration, Boot can configure `SdkTracerProvider` and export traces over OTLP. Common properties live under the tracing export namespace within `management.opentelemetry` in supported versions.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: https://collector.example.com:4318
          transport: http
          timeout: 10s
          compression: gzip
          headers:
            Authorization: Bearer TRACE_SECRET
~~~

Verify property names, timeout units, and valid transport values per version. Do not combine this configuration with a custom exporter bean and an agent simultaneously unless intentional; multiple SDKs/exporters can cause duplicate spans or split pipelines.

Related export settings include:
- schedule delay/batch size/queue size control batching and memory pressure.
- export timeout bounds how long the exporter waits.
- attribute/event/link limits bound span sizes.
- SSL bundles or trust/client certificates configure TLS/mTLS as managed by the application.

Sampling probability is not endpoint configuration. Changing sampling and changing export transport solve two different problems.

## 10. Logs: Not Synonymous With Trace Export

The OpenTelemetry Logs SDK has `SdkLoggerProvider` and an OTLP logs exporter. In Spring Boot versions supporting logging auto-configuration, Boot can configure `SdkLoggerProvider` and the OTLP logging exporter via logging export properties.

~~~yaml
management:
  opentelemetry:
    logging:
      export:
        otlp:
          endpoint: https://logs.example.com:4318
          transport: http
          compression: gzip
          timeout: 10s
~~~

However, **having `SdkLoggerProvider` does not automatically mean SLF4J/Logback log statements are bridged into the provider**. Spring Boot does not provide that bridge out of the box per current documentation. You need a compatible logging bridge/appender or code emitting logs via the OpenTelemetry Logs API.

Distinguish clearly:
- Trace correlation puts trace ID/span ID into log context to help find logs related to a trace.
- OTLP logs export transfers log records to the Collector.
- A pipeline with correlation does not necessarily have OTLP logs export.
- A pipeline with an OTLP log exporter is not necessarily receiving SLF4J events.

Do not use the tracing endpoint property to assume the logs endpoint is configured.

## 11. Metrics: Spring Boot Chooses Micrometer

In Spring Boot, metrics primarily flow through Micrometer rather than OpenTelemetry `SdkMeterProvider`. Therefore, configuration under `management.opentelemetry` does not replace Micrometer registry configuration.

Example using OTLP `MeterRegistry`:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: https://collector.example.com:4318/v1/metrics
        step: 30s
        enabled: true
        compression: gzip
~~~

Exact properties must match the registry/dependency and Boot version. This is the Micrometer metrics pipeline. If a dependency uses OpenTelemetry `MeterProvider` directly, configure the corresponding SDK/exporter and wire `MeterProvider` into that dependency; do not assume metrics from OTel `MeterProvider` are exported alongside the Micrometer registry.

Resource attributes configured in Boot may be used by some OTLP metrics integrations, yet Micrometer's OTLP registry has its own rules. Inspect the actual payload to confirm service identity and dimensions.

## 12. Sample Configuration Across All Three Signals

The example below shows how to structure configuration for a Spring Boot version supporting a common OTLP endpoint and signal-specific logging/tracing properties. Matching dependencies must be added for each pipeline.

~~~yaml
spring:
  application:
    name: order-api

management:
  opentelemetry:
    enabled: true
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
      service.namespace: commerce
    otlp:
      endpoint: https://collector.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer OTLP_SECRET
    tracing:
      export:
        otlp:
          transport: http
          timeout: 10s
    logging:
      export:
        otlp:
          transport: http
          timeout: 10s
  tracing:
    sampling:
      probability: 0.1
  otlp:
    metrics:
      export:
        url: https://collector.example.com:4318/v1/metrics
        step: 30s
        enabled: true
~~~

This configuration illustrates:
- Shared resource metadata to identify the service.
- Common OTLP endpoint/headers/compression for signal exporters supporting common properties.
- Traces with separate sampling and Micrometer Tracing integration.
- Logs with a separate logging pipeline; an appropriate log event forwarding path is still required.
- Metrics exported via the Micrometer OTLP registry using registry settings.

Do not copy YAML verbatim across all Spring Boot versions. Compare your project's property metadata against version docs, verify dependencies, and confirm which exporter beans are actually instantiated.

## 13. Endpoint and Header Security

OTLP exporters typically send telemetry over the network. Settings that must be addressed:

- Use HTTPS/TLS when exporting over untrusted networks.
- Use mTLS if the platform requires client certificates.
- Store tokens/API keys in a secret manager or environment injection; never commit real values.
- Restrict telemetry read/write permissions at the Collector and backend.
- Do not log headers containing `Authorization` when debugging exporters.
- Use internal endpoints and network policies when the Collector is cluster-local.
- Rotate credentials and verify whether exporters reload secrets/certificates.

Example using a placeholder:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otlp.internal.example
      headers:
        Authorization: Bearer REPLACE_WITH_SECRET
~~~

Do not put bearer tokens into URLs, span attributes, baggage, or log messages. Do not enable plaintext just to temporarily bypass certificate errors without understanding trust boundaries.

### Common Headers vs. Dedicated Headers

Common headers can serve multiple signals. Signal-specific headers can add or override a colliding key. This is helpful when traces and logs traverse gateways with different credentials, yet it poses a risk if a token is accidentally sent to the wrong endpoint.

When splitting endpoints, review which `Authorization` header goes to each target, TLS certificates/hostnames, proxy/gateway forwarding, and header value logging.

## 14. Troubleshooting: Properties Declared but Exporter Does Not Send

| Symptom | Possible Cause | Investigation Direction |
| --- | --- | --- |
| `management.opentelemetry` has no effect | Spring Boot version lacks that property or wrong YAML indentation. | Check version reference/configuration metadata and startup logs. |
| Wrong `service.name` resource | Environment variable merge or custom `Resource` bean replaced auto-configured Resource. | Inspect `Resource` bean/payload and precedence. |
| Traces exist but logs are empty | OTel logs pipeline not configured, missing bridge/appender, or Collector not receiving logs. | Check logging exporter, appender/bridge, and logs receiver. |
| Metrics exist but traces do not | Micrometer registry works, yet missing Micrometer Tracing bridge/exporter or sampler drops traces. | Check tracing dependencies, sampling, and trace pipeline. |
| Traces exist but metrics do not | Missing Micrometer registry exporter or registry not enabled. | Check dependencies and metrics export properties. |
| HTTP endpoint returns 404/415 | Wrong path or content type/transport. | Check OTLP HTTP `/v1/{signal}` and receiver protocol. |
| Port 4317/4318 connection error | Transport and listener mismatch, wrong DNS/host. | Check OTLP/gRPC vs. OTLP/HTTP, listener, and network. |
| Common endpoint does not construct expected path | Signal-specific endpoint is set or transport is not HTTP. | Check precedence and each exporter's effective endpoint. |
| Environment variable does not apply | Variable not in Boot's mapped subset or mapping is disabled. | Check `map-environment-variables` and version-specific support list. |
| Export 401/403 | Wrong/expired token, wrong header key, or missing ingest permissions. | Check credentials in secret store and gateway policy. |
| Export timeouts/queue full | Slow Collector/backend or misconfigured exporter batch/timeout. | Measure exporter errors, queues, backend capacity, and batch settings. |
| Backend splits one service into multiple groups | Inconsistent `service.name`/version/environment. | Standardize Resource attributes across replicas/releases. |

A property binding successfully does not prove the Collector receives data. Inspect each boundary: application provider → processor/exporter → network → Collector receiver → pipeline processor → backend ingestion/indexing.

## 15. Runbook for Verifying `management.opentelemetry`

1. **Confirm version:** get the actual Spring Boot version from build/dependency reports; open reference docs for that exact minor version.
2. **Check property binding:** inspect warnings for unknown/unbound properties and verify YAML indentation.
3. **Inspect beans:** identify which `OpenTelemetry`, `Resource`, `SdkTracerProvider`, `SdkLoggerProvider`, and exporters/registries actually exist.
4. **Inspect resource:** check `service.name`, `service.version`, and environment in payloads/backend.
5. **Check effective endpoints:** determine whether common or signal-specific endpoints are used; for HTTP, check the final path.
6. **Verify transport:** confirm HTTP exporters target HTTP receivers or gRPC targets gRPC receivers.
7. **Test each signal:** trace, log, and metric have separate pipelines; generate clear samples for each type.
8. **Check Collector:** receivers, pipelines, exporters, authentication, and dropped/refused counters.
9. **Check backend:** ingestion/index latency, retention, tenant routing, and query time range.
10. **Verify security:** credentials come from a secret store and never appear in logs/traces.

When only one signal fails, fix the configuration of that exact signal. Do not increase sampling or instantiate a second SDK just to work around an endpoint error.

## 16. Self-Check Exercises

### Exercise 1 — Common Endpoint

You configure the common OTLP endpoint as `https://collector.example.com:4318` and the exporter uses HTTP. Traces have no signal-specific endpoint. Which path will be used?

**Answer:** With common endpoint fallback over HTTP, Spring Boot appends the signal path; traces use `/v1/traces`. Logs and metrics use their corresponding paths if those signals' pipelines/exporters are enabled.

### Exercise 2 — Does a Signal-Specific Endpoint Take Precedence?

Both the common endpoint and `tracing.export.otlp.endpoint` are set. Which address does the traces exporter use?

**Answer:** The signal-specific endpoint takes precedence when set. The common endpoint serves as fallback for signals without their own endpoint.

### Exercise 3 — Traces Exist, Logs Do Not

The application sends traces successfully to the Collector, yet logs do not appear. Is adding just the trace exporter dependency enough?

**Answer:** No. Logs need the OpenTelemetry Logs SDK/exporter or corresponding logging pipeline, a Collector logs receiver, and a path integrating log events from the logging framework if the log source is SLF4J/Logback.

### Exercise 4 — Micrometer Metrics

The application has a Micrometer `MeterRegistry`. Does disabling OpenTelemetry support guarantee metrics collection stops?

**Answer:** No. Spring Boot uses Micrometer for metrics; metrics can continue operating via their own registry even when OpenTelemetry SDK support is disabled.

### Exercise 5 — Custom `Resource` Bean

After adding a custom `Resource` bean, `service.name` is no longer merged as before. What is the likely cause?

**Answer:** Defining a custom `Resource` bean alters Spring Boot's auto-configured `Resource` merge mechanism. The application must merge the resource attributes it wants to preserve itself.

### Exercise 6 — Environment Variable Has No Effect

You set an `OTEL_*` environment variable yet the property does not change. What should you check first?

**Answer:** Spring Boot maps only a subset of environment variables; check the version-specific supported list and `map-environment-variables`. Not every OpenTelemetry SDK variable is mapped automatically.

## 17. Deployment Checklist

- [ ] Identified Spring Boot version and checked docs for the exact minor release.
- [ ] Understood `management.opentelemetry` is OpenTelemetry integration config, not an auto-export switch for all signals.
- [ ] Set `enabled` intentionally; not used as a replacement for per-signal export properties.
- [ ] Resource attributes have consistent `service.name`/version/environment.
- [ ] No request/user/customer IDs placed into Resource.
- [ ] Aware that a custom `Resource` bean changes default merge behavior.
- [ ] Shared OTLP endpoint/headers/compression used intentionally.
- [ ] Precedence verified for signal-specific endpoints/headers.
- [ ] HTTP paths `/v1/traces`, `/v1/logs`, `/v1/metrics` and OTLP/gRPC transport are not confused.
- [ ] Relied on environment variables only when included in Boot's supported subset.
- [ ] Micrometer Tracing configured for trace export.
- [ ] Logs have appropriate SDK/exporter and logging bridge/appender when needed.
- [ ] Metrics exported via Micrometer registry or explicitly wired SDK pipeline.
- [ ] TLS/auth and secrets managed via an appropriate platform mechanism.
- [ ] Collector has receivers/pipelines/exporters for each signal.
- [ ] Evidence exists of backend ingest and querying for logs/traces/metrics.
- [ ] Monitoring covers timeouts, queues, retries, dropped records, and backend capacity.

**Key takeaway:** `management.opentelemetry` helps Spring Boot configure OpenTelemetry integration aspects such as resource, shared OTLP settings, and signal-specific properties in supported versions. Always confirm version, precedence, and the separate pipelines of traces, logs, and metrics. Micrometer Tracing integrates tracing; Micrometer is Spring Boot's primary metrics path; and logs need an OpenTelemetry Logs pipeline and appropriate bridge. Only verifying data from the application to the Collector/backend proves export actually works.
