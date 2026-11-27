# Configuring Exporters via Environment Variables

In the **Production Operations** chapter of the `SPRING_BOOT_OBSERVABILITY` module, this lesson covers how to configure Spring Boot exporters using environment variables. The goal is to deploy the same application across multiple environments without packaging collector endpoints, credentials, export intervals, or sampling rates into the source code. This approach supports setting up observability with Micrometer Observation, metrics, logs, and distributed tracing, while allowing telemetry destinations to change per runtime environment.

Spring Boot binds environment variables into `Environment` through relaxed binding. Properties can be placed in `application.yml`, profile-specific configuration files, environment variables, or other configuration sources. The application must include the corresponding dependencies and auto-configuration for an exporter to work; setting an environment variable alone does not install a registry or tracing bridge.

## 1. Distinguishing Exporter Types and Data Transport Models

Exporters transfer telemetry from the application to a collection system. Before configuring them, identify the signal type, protocol, and data transfer model:

| Signal | Common Setup | Destination | Operational Characteristics |
| --- | --- | --- | --- |
| Metrics | Micrometer OTLP registry | OpenTelemetry Collector or OTLP backend | The application actively pushes data on a schedule. |
| Metrics | Micrometer Prometheus registry | Prometheus server scraping the Actuator endpoint | Prometheus actively pulls data from the application. |
| Traces | Micrometer Tracing with OTLP exporter | OpenTelemetry Collector or tracing backend | Spans are sent according to exporter and sampling configuration. |
| Logs | Logging appender, agent, or log collector | OpenTelemetry Collector or log platform | Usually a separate logging pipeline; not exported by default through the metrics exporter. |

The two common metrics models have opposite transfer directions. OTLP is typically push-based: the application sends data to the collector. Prometheus is typically pull-based: the Prometheus server calls the application's `/actuator/prometheus` endpoint. Therefore, you do not configure a push URL for the Prometheus registry the way you do for OTLP.

For OTLP over HTTP, an OpenTelemetry Collector typically receives metrics at `/v1/metrics` and traces at `/v1/traces`, commonly on the OTLP HTTP port `4318`. The actual port and path depend on the collector's receiver configuration. Confirm that the application and collector agree on protocol, host, port, path, TLS, and authentication.

## 2. How Spring Boot Maps Property Names to Environment Variables

Spring Boot applies the following rules to convert property names to environment variables:

1. Replace dots (`.`) with underscores (`_`).
2. Remove hyphens (`-`).
3. Convert the entire name to uppercase.

Examples:

| Property | Environment variable |
| --- | --- |
| `management.otlp.metrics.export.url` | `MANAGEMENT_OTLP_METRICS_EXPORT_URL` |
| `management.otlp.metrics.export.step` | `MANAGEMENT_OTLP_METRICS_EXPORT_STEP` |
| `management.otlp.tracing.endpoint` | `MANAGEMENT_OTLP_TRACING_ENDPOINT` |
| `management.tracing.sampling.probability` | `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` |
| `management.endpoints.web.exposure.include` | `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` |
| `spring.application.name` | `SPRING_APPLICATION_NAME` |

Environment variable values are always passed as strings; Spring Boot binds them to target types such as booleans, numbers, or durations. For example, `30s` is a 30-second duration, and `0.1` is a decimal number. For values containing commas, spaces, or special characters, pay attention to quoting rules in the shell, Docker Compose, or YAML manifests.

## 3. Configuring the OTLP Metrics Exporter

The application needs the corresponding Micrometer OTLP registry on the classpath along with exporter configuration. In Spring Boot versions that support OTLP metrics configuration, commonly used properties include:

| Property | Environment variable | Meaning |
| --- | --- | --- |
| `management.otlp.metrics.export.url` | `MANAGEMENT_OTLP_METRICS_EXPORT_URL` | URL receiving OTLP metrics. For OTLP/HTTP, this usually ends with `/v1/metrics`. |
| `management.otlp.metrics.export.step` | `MANAGEMENT_OTLP_METRICS_EXPORT_STEP` | Metrics export interval, such as `30s` or `1m`. |
| `management.otlp.metrics.export.connect-timeout` | `MANAGEMENT_OTLP_METRICS_EXPORT_CONNECT_TIMEOUT` | Connection establishment timeout. |
| `management.otlp.metrics.export.read-timeout` | `MANAGEMENT_OTLP_METRICS_EXPORT_READ_TIMEOUT` | Response read timeout. |

Example running the application on Linux or macOS:

```bash
export SPRING_PROFILES_ACTIVE=prod
export SPRING_APPLICATION_NAME=orders-api
export MANAGEMENT_OTLP_METRICS_EXPORT_URL=http://otel-collector:4318/v1/metrics
export MANAGEMENT_OTLP_METRICS_EXPORT_STEP=30s
export MANAGEMENT_OTLP_METRICS_EXPORT_CONNECT_TIMEOUT=2s
export MANAGEMENT_OTLP_METRICS_EXPORT_READ_TIMEOUT=10s

java -jar app.jar
```

`otel-collector` in the example is a hostname resolvable from the application's network, such as a service name in Docker Compose or Kubernetes. When running locally, you can replace it with `localhost` if the collector actually runs in the same network namespace. Inside a container, `localhost` points to the application container itself; it does not automatically point to another collector container.

The export interval is an operational trade-off. A shorter interval delivers data to the backend faster but increases send frequency and overhead; a longer interval reduces send frequency but delays data arrival. Weigh traffic volume, acceptable latency, backend limits, and investigation needs. Exact property names can vary across Spring Boot and Micrometer versions; use the properties supported by the version you are running.

## 4. Configuring the OTLP Tracing Exporter and Sampling

Tracing requires a compatible tracing bridge and OTLP exporter. Once dependencies and auto-configuration are in place, you can configure the span export endpoint and sampling with environment variables:

```bash
export MANAGEMENT_OTLP_TRACING_ENDPOINT=http://otel-collector:4318/v1/traces
export MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.10
```

Corresponding properties:

| Property | Environment variable | Meaning |
| --- | --- | --- |
| `management.otlp.tracing.endpoint` | `MANAGEMENT_OTLP_TRACING_ENDPOINT` | Endpoint receiving OTLP traces. |
| `management.tracing.sampling.probability` | `MANAGEMENT_TRACING_SAMPLING_PROBABILITY` | Fraction of traces selected for recording, from `0.0` to `1.0`. |

A sampling probability of `0.10` means the sampler selects roughly 10% of traces according to the active sampling policy. This is a trace-level decision; it does not reduce metrics collection rates in the same way. Increasing sampling can improve visibility into rare requests, but also increases network traffic, ingest cost, and storage usage. For production, choose a rate based on traffic, investigation requirements, and telemetry budget; consider tail sampling at the collector if decisions need to depend on the completed trace outcome.

For tracing to be useful in cross-service investigations, context propagation must be preserved across HTTP clients, messaging, and asynchronous execution boundaries. A working exporter endpoint does not mean propagation is right or that every request has a stored trace. Sampling, instrumentation, and backend span ingestion all affect whether a trace can be found.

## 5. Declaring Resource Attributes and Headers

Telemetry needs consistent service identification to distinguish data across applications, environments, and deployment versions. Common attributes include `service.name`, `service.namespace`, `service.version`, and `deployment.environment`. Exact values and how resource attributes bind depend on the exporter and the Spring Boot/Micrometer version.

For map configurations or nested structures, avoid guessing environment variable names for every map key. You can use `SPRING_APPLICATION_JSON` to pass the property structure explicitly. Illustrative example configuring resource attributes for OTLP metrics:

```bash
export SPRING_APPLICATION_JSON='{"management":{"otlp":{"metrics":{"export":{"resource-attributes":{"service.name":"orders-api","deployment.environment":"production","service.namespace":"commerce"}}}}}}'
```

Verify that this map property is supported by the exporter version in use and binds to the expected type. If the application already receives service identity from a shared configuration or OpenTelemetry resource, avoid declaring conflicting values between metrics and traces. A service appearing under different names across two signals makes dashboards and correlated queries harder to use.

Some collectors or backends require headers for authentication, such as a bearer token. Because headers are a map, passing them via environment variables depends on map-key binding rules. You can declare the map in Spring configuration and inject the secret via a placeholder:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${OTLP_EXPORT_TOKEN}"
    tracing:
      headers:
        Authorization: "Bearer ${OTLP_EXPORT_TOKEN}"
```

Then supply `OTLP_EXPORT_TOKEN` from a secret manager, Kubernetes Secret, or platform secret mechanism. Header properties apply only when the exporter and Spring Boot version support them. Never put raw tokens into Docker images, Git, public manifests, command lines, or startup logs. Also ensure TLS is used when transmitting credentials over the network.

## 6. Configuration in Docker Compose

In Docker Compose, environment variables can be declared on the application service:

```yaml
services:
  orders-api:
    image: example/orders-api:1.0.0
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      SPRING_APPLICATION_NAME: "orders-api"
      MANAGEMENT_OTLP_METRICS_EXPORT_URL: "http://otel-collector:4318/v1/metrics"
      MANAGEMENT_OTLP_METRICS_EXPORT_STEP: "30s"
      MANAGEMENT_OTLP_TRACING_ENDPOINT: "http://otel-collector:4318/v1/traces"
      MANAGEMENT_TRACING_SAMPLING_PROBABILITY: "0.10"
    depends_on:
      - otel-collector

  otel-collector:
    image: otel/opentelemetry-collector:latest
```

This snippet illustrates the application-side connection settings; the collector still needs receiver, processor, and exporter configuration matching the backend. `depends_on` controls basic container startup ordering and does not guarantee the collector is ready to accept telemetry. The application needs appropriate retry or export error handling when the collector is not yet ready.

Avoid pinning the `latest` tag in production. Pin tested image versions and manage upgrades deliberately. If tokens are required, store them in Docker secrets or the deployment platform's secret store rather than placing real values in a committed Compose file.

## 7. Configuration in Kubernetes

In Kubernetes, environment variables typically come from a `ConfigMap` for non-sensitive settings and a `Secret` for credentials. Abbreviated Deployment example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: example/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: SPRING_APPLICATION_NAME
              value: "orders-api"
            - name: MANAGEMENT_OTLP_METRICS_EXPORT_URL
              value: "http://otel-collector.observability.svc:4318/v1/metrics"
            - name: MANAGEMENT_OTLP_METRICS_EXPORT_STEP
              value: "30s"
            - name: MANAGEMENT_OTLP_TRACING_ENDPOINT
              value: "http://otel-collector.observability.svc:4318/v1/traces"
            - name: MANAGEMENT_TRACING_SAMPLING_PROBABILITY
              value: "0.10"
            - name: OTLP_EXPORT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: otel-export-credentials
                  key: token
```

In this example, `OTLP_EXPORT_TOKEN` is pulled from a Secret; header settings in `application.yml` can reference this variable as shown earlier. The DNS name `otel-collector.observability.svc` is only an example and should be replaced with the actual service name and namespace. NetworkPolicy, service ports, TLS, and authentication must allow connectivity from the application workload to the collector.

Updating environment variables in a Pod template causes Kubernetes to create new Pods during a rollout. After updating, check the rollout and the logs of the new Pods. If a Secret is mounted as a volume, the application may need a reload or restart mechanism depending on how configuration is read; do not assume every secret change automatically updates the running configuration.

## 8. Configuring the Prometheus Exporter for Scraping

If using Prometheus instead of OTLP for metrics, add the corresponding Prometheus registry to the application and expose the `prometheus` endpoint over the web. Example configuration via environment variables:

```bash
export MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE=health,prometheus
```

The Prometheus server then scrapes a URL such as:

```text
http://orders-api:8080/actuator/prometheus
```

The endpoint must be exposed, the service must be reachable from Prometheus, and access must be protected according to the environment's network security model. Do not expose all Actuator endpoints just so Prometheus can scrape metrics. If remote write to a central backend is needed, configure remote write on the Prometheus server; the Spring Boot application continues to serve the scrape endpoint.

Avoid enabling multiple registries or exporters simultaneously just because it is possible. Each export path increases traffic, configuration surface, and the risk of duplicate data. Choose a model aligned with your telemetry architecture: Prometheus scrape, OTLP push, or an intentional combination of both.

## 9. Logs Are a Separate Pipeline

Metrics exporters and tracing exporters do not automatically export logs. Spring Boot can populate trace IDs and span IDs into the logging context when tracing is integrated; the application still needs a pipeline to collect and ship logs to storage. Common deployment patterns include:

- An agent or collector reading container stdout/stderr and forwarding logs.
- A logging appender integrated with OpenTelemetry or the corresponding log backend.
- The Kubernetes logging platform or centralized log aggregation infrastructure.

Standardize timestamps, service identity, and trace correlation fields in logs. Do not log access tokens, passwords, personal data, or sensitive payloads. When investigating a request, you can use the trace ID in logs to open the corresponding trace; metrics provide overall trends while logs provide specific events.

## 10. Configuration Precedence and Per-Environment Management

Spring Boot combines multiple property sources. In typical operations, environment variables can override values in configuration files; `SPRING_APPLICATION_JSON`, system properties, and command-line arguments can take even higher precedence depending on the source. Therefore, when an effective value differs from `application.yml`, inspect all loaded configuration sources.

A maintainable organization approach is:

- Keep non-sensitive defaults in `application.yml`.
- Use profiles such as `prod` to select environment-appropriate configuration groups.
- Supply endpoints, export intervals, and sampling rates via workload environment variables.
- Supply tokens and credentials via a secret manager or Secrets, referencing them with placeholders or config trees.
- Keep service identity consistent across metrics, traces, and logs; change only environment-specific properties when deploying to another environment.

For instance, the same image can run in staging and production with different collector endpoints and sampling rates. There is no need to rebuild the image just to change an exporter address. Still, manage configuration changes as part of a release: review, deploy, monitor for export errors, and keep a rollback plan.

## 11. Verifying Exporters After Deployment

Do not conclude an exporter is working merely because the application started successfully. Verify layer by layer.

**Step 1 — Verify runtime configuration.** Confirm that the profile, endpoints, metrics interval, and sampling rate are supplied properly to the Pod or container. Avoid exposing management endpoints like `/actuator/env` just for checking; if used in a protected environment, restrict access and never share secret values.

**Step 2 — Verify connectivity to the collector.** From the workload's network, confirm the hostname resolves, the port is open, and the TLS handshake succeeds. Check NetworkPolicy, service selectors, port mappings, proxies, and certificates if using HTTPS.

**Step 3 — Check for exporter errors.** Read application and collector logs around export intervals. Look for timeouts, connection refused errors, DNS failures, HTTP 401/403 responses, invalid payloads, or disabled receivers. Do not print tokens or authorization headers into diagnostic output.

**Step 4 — Check metrics at the source.** If using the Prometheus registry, call the scrape endpoint:

```bash
curl -i http://localhost:8080/actuator/prometheus
```

If using OTLP, `/actuator/prometheus` is only useful if the application also includes the Prometheus registry. The OTLP exporter sends data periodically to the collector; inspect collector receiver/exporter logs or metrics to confirm data arrives.

**Step 5 — Verify traces.** Generate a test request with trace context or let the application generate traces as configured. Search for the trace in the backend by service name and time range. If traces do not appear, check sampling probability, tracing bridge, OTLP endpoint, propagation, and the collector pipeline.

**Step 6 — Verify signal correlation.** Pick a request and confirm that service name, environment, timestamp, and trace ID correlate between logs and traces. Compare route/status metrics around the request timestamp. Note that sampling can cause a request to lack a trace in the backend even when metrics and logs are present.

## 12. Common Configuration Errors

| Symptom | Possible Cause | Troubleshooting |
| --- | --- | --- |
| Metrics or traces do not appear | Missing registry, tracing bridge, or exporter dependency; auto-configuration not triggered. | Check dependencies and auto-configuration conditions for your exact Spring Boot version. |
| `Connection refused` | Collector is not running, wrong port, or receiver is not listening on the right interface. | Check collector status, receiver config, and service port. |
| `UnknownHostException` or DNS failure | Wrong hostname or workload is on a different network/service discovery scope. | Check DNS from inside the container/Pod and verify the service name. |
| HTTP `401` or `403` | Token missing, expired, or lacks ingest permissions. | Check secret, headers, audience/scope, and backend policies. |
| HTTP `404` | Wrong path, e.g., missing `/v1/metrics` or `/v1/traces`, or receiver uses a different route. | Compare the OTLP/HTTP endpoint against the collector receiver configuration. |
| Export timeout | Slow network, overloaded collector, low timeout, or unresponsive backend. | Check latency, queues, retries, collector resources, and timeouts. |
| Metrics arrive but traces do not | Tracing bridge/exporter not configured, low sampling, or collector trace pipeline missing. | Check sampling, tracing endpoint, and trace receiver/processor/exporter. |
| Traces arrive but log correlation is missing | Logging pattern does not include trace/span ID from MDC, or log pipeline drops fields. | Check logging integration, format, and log collector parsers. |
| Data is split into multiple services | Inconsistent `service.name` or resource attributes. | Standardize service identity across signals and environments. |
| Metrics cardinality grows rapidly | Tags contain IDs or high-variance values. | Use route templates and bounded tag value sets; move request identifiers to logs/traces. |

An HTTP GET to an OTLP endpoint is not a valid export test because receivers typically expect OTLP POST requests. Verify using exporter logs, collector logs/metrics, or the telemetry backend. Likewise, an Actuator endpoint returning 200 only proves that the endpoint responds, not that the collector received data.

## 13. Operational Checklist

- [ ] Verified compatible exporter dependencies and Spring Boot/Micrometer versions.
- [ ] Used proper environment variable names following relaxed binding.
- [ ] Verified OTLP URL, protocol, port, and `/v1/metrics` or `/v1/traces` path.
- [ ] Selected metrics interval and sampling rate aligned with traffic and cost.
- [ ] Kept service identity consistent across metrics, traces, and logs.
- [ ] Supplied credentials via a secret manager or platform secret mechanism.
- [ ] Confirmed workloads can resolve DNS and connect to the collector.
- [ ] Inspected exporter and collector logs after deployment.
- [ ] Confirmed data actually appears in the telemetry backend.
- [ ] Restricted exposed Actuator endpoints and secured management endpoints.

When configuring exporters via environment variables, a single application image can be deployed across environments with distinct endpoints, export intervals, sampling rates, and credentials. Verification must span end-to-end from bound properties, network connectivity, exporter, and collector through to the backend. When metrics, traces, and logs share a service identity and correlate via timestamps and trace context, operations teams can investigate production latency and errors using consistent signals.
