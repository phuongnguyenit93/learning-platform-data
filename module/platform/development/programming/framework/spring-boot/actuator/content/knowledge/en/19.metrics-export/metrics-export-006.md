# Managing Ingestion Endpoints, Credentials, and Export Intervals

## 1. From In-Application Measurements to Data in the Monitoring System

An application may already be recording request counts, processing latencies, and JVM memory, yet the monitoring system still shows no data. **Recording measurements** and **getting those measurements exported out** are two separate concerns.

In Spring Boot Actuator, Micrometer provides the instrumentation model. A **meter** is an object representing a measurement, such as a counter; a **registry** is the component that manages meters and integrates with a monitoring system. This article focuses on three operational questions:

- **Where does it go?** The destination address must match the target system, protocol, port, and path.
- **How is it authorized?** The caller needs credentials matching what the receiver expects.
- **How often is it sent or collected?** The cadence must fit observability needs and system load.

First determine **which party actively opens the connection**:

| Model | Active Initiator | Address to Manage | Where Interval Is Configured |
| --- | --- | --- | --- |
| Push data, e.g., Micrometer OTLP | Application sends metrics to the receiver | URL of the collector or metrics ingestion service | Exporter configuration inside the application |
| Pull data, e.g., Prometheus scrape | Prometheus calls the application to read metrics | Application address and metrics exposition path | Prometheus scrape job configuration |

OTLP stands for OpenTelemetry Protocol, a protocol for exchanging observability telemetry. An OpenTelemetry Collector can receive data from the application and forward it to a storage backend.

```text
Push:
Application -> Micrometer OTLP -> collector -> storage backend

Pull:
Prometheus -> GET application endpoint -> metrics data
```

In the push model, the "ingestion endpoint" lives on the collector side. In the pull model, the endpoint inside the application **serves data to the scraper**. Mixing up connection direction causes the address, credentials, and interval setting to all be configured in the wrong place.

Spring Boot supports the corresponding registries and provides the Prometheus endpoint when appropriate configuration conditions are met. See [Spring Boot 3.3 metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 2. Preparing the Registry Before Configuring the Address

The Gradle snippets below are additions to an application **already using Spring Boot 3.3.x and Boot's dependency management**; they are not complete standalone build files. Use JDK 21 for the learning environment in this article.

If choosing OTLP:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-otlp'
}
```

If choosing Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}
```

The application needs a web starter if you want to use Actuator endpoints over HTTP. By contrast, **OTLP push does not require exposing HTTP Actuator endpoints**.

Do not manually pick a Micrometer version different from Boot's dependency set just to copy a newer example. Options from current library releases might not exist in the branch being studied.

Having the registry on the classpath is a prerequisite for Boot to auto-configure the exporter. Adding a URL key to YAML alone does not replace the dependency. If you intentionally enable multiple registries, the application can export to multiple destinations; in that case you must manage each export path and its associated cost.

## 3. Configuring the Right OTLP Ingestion Address

### 3.1. Reading a URL Component by Component

Example address:

```text
https://metrics-gateway.example.net:443/v1/metrics
|-----| |-------------------------| |-| |---------|
 scheme             host           port    path
```

The domain above only illustrates structure; replace it with the actual receiver before running.

Verify:

1. **Scheme:** does the receiver use HTTP or HTTPS?
2. **Host:** can the application process resolve and reach this hostname?
3. **Port:** which protocol does that port serve?
4. **Path:** does that path actually accept metrics?
5. **Network scope:** is this address valid from the application host or only from an administrator's workstation?

With Micrometer's default OTLP export path in the 1.13.x branch, data is sent via HTTP POST with protobuf payloads. A common OTLP/HTTP metrics URL is `http://localhost:4318/v1/metrics`. Do not use a dashboard UI URL or `/actuator/metrics` as the OTLP ingestion address. The HTTP sending behavior is shown in [OtlpMeterRegistry 1.13.15 source](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpMeterRegistry.java).

Port 4317 is typically used for OTLP/gRPC, while 4318 is typically used for OTLP/HTTP. These are default ports in the [OTLP specification](https://opentelemetry.io/docs/specs/otlp/); the receiver's actual contract is what decides. Changing the port number in the URL does not turn an HTTP sender into a gRPC sender.

When declaring `management.otlp.metrics.export.url`, provide the **full metrics ingestion URL** required by the receiver. Do not assume every configuration mechanism automatically appends `/v1/metrics`.

### 3.2. Baseline OTLP Configuration

In `application.yml`:

```yaml
management:
  otlp:
    metrics:
      export:
        enabled: true
        url: "${METRICS_OTLP_URL}"
        headers:
          Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
        step: 30s
        connect-timeout: 2s
        read-timeout: 5s
```

This configuration is for a **receiver requiring a Bearer token**. The variable names `METRICS_OTLP_URL` and `METRICS_OTLP_TOKEN` are application conventions referenced via Spring placeholders; they are not mandatory standard OTLP variables.

| Property under `management.otlp.metrics.export` | Role |
| --- | --- |
| `enabled` | Enables or disables this export path |
| `url` | Metrics ingestion destination |
| `headers` | HTTP headers required by the receiver |
| `step` | Export interval |
| `connect-timeout` | Timeout for establishing the connection |
| `read-timeout` | Timeout for reading the response |

The Boot 3.3 branch provides these properties; the defaults for `step`, `connect-timeout`, and `read-timeout` are `1m`, `1s`, and `10s` respectively. The two timeouts are not a guarantee on total completion time for an entire export cycle. Cross-check the [Boot 3.3 property appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.3. Avoiding Namespace Confusion

In Boot 3.3:

```properties
management.otlp.metrics.export.url=https://metrics-gateway.example.net/v1/metrics
```

differs from:

```properties
management.otlp.tracing.endpoint=https://trace-gateway.example.net/v1/traces
```

One property configures metrics; the other configures tracing. Changing tracing alone does not change the metrics export destination. Likewise, do not copy the `management.metrics.export...` prefix from older Boot examples assuming all keys still bind the same way in Boot 3.3.

### 3.4. Understanding localhost Correctly

`localhost` is always interpreted from the environment of the **connecting process**:

- Application running directly on the host machine: `localhost` is that machine itself.
- Application running inside a container: `localhost` is the application container.
- Prometheus running inside a container: target `localhost:8080` points to the Prometheus container, unless special network configuration is in place.

If the application and Collector are two separate services on the same container network, the address might be `http://otel-collector:4318/v1/metrics`, provided `otel-collector` is the real service name and the receiver is enabled. Successfully reaching an address from a browser on your laptop does not prove the containerized application can reach it.

## 4. Managing Credentials Along the Connection Direction

### 4.1. Distinguishing Two Identity Pairs

In the push path:

```text
Application -- credentials A --> collector
Collector   -- credentials B --> storage backend
```

Token A and token B may differ. Granting permission to send to the collector does not implicitly grant permission to query dashboards or send directly to the storage service.

In the pull path:

```text
Prometheus -- credentials --> application metrics endpoint
```

Credentials are configured on the Prometheus side and verified by the application or a security gateway in front of it. A token used for outbound OTLP does not protect an inbound Actuator endpoint.

### 4.2. Headers Must Follow the Receiver's Contract

A Bearer token is just one mechanism. If the receiver requires an API key in a different header, the configuration must reflect that exact contract, for example:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          X-API-Key: "${METRICS_API_KEY}"
```

This snippet is an **alternative for the headers section**, not an instruction to send all authentication types simultaneously. Do not prepend `Bearer` to an API key if the receiver expects a raw value. For Basic auth, mTLS, or OAuth2 requiring dynamic token acquisition, use an appropriate integration; a static header string will not acquire and renew tokens on its own.

HTTPS protects data in transit and verifies the server against trust configuration. Having a token does not turn plain HTTP into an encrypted channel. Conversely, using HTTPS does not automatically grant permission to write metrics.

### 4.3. Separating Regular Configuration from Secrets

URLs and intervals can live in deployment configuration. Tokens should be supplied via runtime secret mechanisms, such as secret mounts or environment variables injected by the deployment platform.

With placeholders that have no default values:

```yaml
url: "${METRICS_OTLP_URL}"
headers:
  Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
```

an environment enabling the exporter must supply the required values. Do not use a fallback dummy token "just so it runs" when configuration is missing. If an environment does not need metrics export, disable the export path via its own configuration and omit unnecessary authentication settings.

Another option is a config tree:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${metrics.otlp.token}"
```

In this Linux/container example, the platform mounts `/run/secrets/metrics.otlp.token`; the file's content is the token. The configuration contains no token. This replaces the token-injection mechanism and must be merged into a complete OTLP configuration. Do not mark the import as `optional:` if a missing secret directory should be caught immediately. Config trees and placeholders are documented in [Boot 3.3 Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Do not place tokens in URLs, metric tags, or configuration-inspection logs. Tags travel along with time series and may be retained long-term. Do not expose configuration endpoints publicly just to check whether a token bound properly.

### 4.4. Rotating and Revoking Tokens

A token rotation can follow this sequence:

1. Create a new token with metrics-ingestion permissions scoped to the target environment.
2. Update the secret read by the instances.
3. Restart or perform a rolling deployment of instances if the application lacks a verified reload mechanism.
4. Verify sending from each instance with the new token.
5. Revoke the old token after confirming no instance is still using it.

Updating a value in a secret store does not guarantee a running exporter immediately adopts the new value. Standard Boot configuration is read at application startup; dynamic updates must be explicitly designed and verified.

If the receiver does not allow two tokens to coexist, account for a brief interruption instead of assuming zero-loss rotation is always possible.

## 5. Choosing Export Intervals Without Confusing Them with Recording Intervals

### 5.1. Step Controls Periodic Publishing

With OTLP, `step: 30s` instructs the registry to export on a 30-second cycle. It does not mean:

- The application only records events once every 30 seconds.
- Each business HTTP request immediately triggers an OTLP HTTP request.
- Dashboards are guaranteed to update every 30 seconds on the dot.
- The collector must retain data for exactly 30 seconds.

Meters receive measurements as the application executes. The export schedule pushes aggregated representations of those measurements externally. For a gauge, the value observed at measurement/export time is not the full history of fluctuations between intervals; shortening the interval can provide more observation points but cannot reconstruct data that was never recorded.

OTLP also has cumulative or windowed-delta representations, commonly called `cumulative` and `delta`. The export step and this representation are related but are not the same setting. Do not assume every counter resets after every send; nor should you switch temporality without verifying receiver compatibility.

Defaults and step determination in the Micrometer 1.13 branch are shown in [OtlpConfig 1.13.15](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.15/implementations/micrometer-registry-otlp/src/main/java/io/micrometer/registry/otlp/OtlpConfig.java).

### 5.2. Observed Latency Has Multiple Components

You can think of it as:

```text
Approximate observed latency =
waiting for the next export/scrape
+ network transfer and data processing
+ storage backend ingestion delay
+ dashboard query/refresh interval
```

This is a reasoning model, not a latency-guarantee formula. Reducing `step` from 60s to 10s will have little effect if the dashboard only refreshes every few minutes.

When testing a change, wait through several complete cycles and check actual data timestamps. Do not conclude something is broken merely because data does not appear the instant the application starts.

### 5.3. Estimating Load Before Shortening the Interval

Assuming one instance sends one batch per interval and ignoring retries:

```text
Sends per minute ≈ number of instances × 60 / step_in_seconds
```

With 400 instances:

| Assumed Interval | Estimated Sends/Minute |
| --- | ---: |
| 60s | 400 |
| 30s | 800 |
| 5s | 4,800 |

This calculation illustrates a single-batch assumption; in reality a single publish may split into multiple requests if the meter count is high. Time series counts, histograms, tag counts, and payload sizes also affect traffic and cost. Shortening the interval does not solve excessive tag combinations.

A sensible approach is to start from incident-detection requirements, check the resolution supported by the storage backend, test with an instance count close to production, and measure cost before and after changes. There is no single optimal value for every application.

### 5.4. Timeouts and Send Errors

`connect-timeout` and `read-timeout` bound the network-wait phases; they do not replace `step`. Setting a very short interval while sends are frequently slow can prevent the export schedule from keeping up as expected.

Do not treat an in-process registry as a durable queue. When network errors occur or the receiver rejects requests, expect export errors and data gaps. Do not infer that every failed batch will be persisted to disk and retried completely. If higher outage resilience is required, consider an intermediate collector with explicitly configured buffering and retry capabilities.

## 6. Managing Across Environments and Multiple Instances

A deployment configuration matrix should clearly separate these values:

| Component | Development Environment | Production Environment |
| --- | --- | --- |
| Destination | Test collector reachable from where the app runs | Managed destination for the live environment |
| Credentials | Test identity | Identity scoped to send permissions for that environment |
| Interval | Convenient for experimentation | Evaluated for latency and load |
| Data identity | Test service/environment name | Appropriate service, environment, and instance identifiers |
| Config changes | Controlled restarts | Phased rollout and verification |

Do not send test data into the same data namespace as production merely because both environments share the same application name. Check destination and identifying metadata against the real system; tags or resource attributes exist to distinguish sources, not to carry secrets or user identifiers.

For multi-instance applications:

- Push paths need verification that every instance can connect and is authorized.
- Pull paths need discovery/target configuration to scrape every instance. Scraping a load-balanced address can alternate across different processes and distort time series interpretation.
- When changing intervals, know which instances received the new configuration; do not judge from a single pod or a single startup log line.

Boot supports many configuration sources. A value in YAML can be overridden by a higher-precedence source. When configuration appears to "have no effect," check active profiles, environment variables, startup arguments, and external config sources; collect only non-sensitive values needed for diagnostics.

## 7. With Prometheus, Set Address and Interval on the Scraper Side

### 7.1. Application Serving Data

With the Prometheus dependency and an HTTP application, application configuration might be:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
```

This example permits publishing the endpoint via exposure settings; **it does not define authentication**. If the application uses Spring Security, cross-check existing endpoint protection rules. If there is a proxy in front, the proxy and application must agree on paths and access permissions. In production, only monitoring components should be allowed to read it.

The common default path is `/actuator/prometheus`, though custom port, context path, and base path settings can change the actual URL. See [Boot 3.3 endpoint exposure and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 7.2. Prometheus Calling the Application

The `prometheus.yml` example below assumes:

- `orders-mgmt.internal:9443` is a real HTTPS address reachable from the Prometheus process.
- The endpoint is protected by a Bearer token at the application or gateway.
- The token file and CA certificate are mounted in the Prometheus environment.

```yaml
scrape_configs:
  - job_name: "orders"
    scheme: https
    metrics_path: /actuator/prometheus
    scrape_interval: 30s
    scrape_timeout: 5s
    authorization:
      type: Bearer
      credentials_file: /run/secrets/orders-scrape-token
    tls_config:
      ca_file: /etc/prometheus/certs/internal-ca.pem
    static_configs:
      - targets:
          - "orders-mgmt.internal:9443"
```

You must substitute real addresses and files for your environment; this snippet does not provision DNS, certificates, or a token verifier. The `orders-scrape-token` file contains only the token; Prometheus adds the authentication scheme based on `type`.

If the server uses Basic auth, replace the `authorization` block with the corresponding mechanism:

```yaml
basic_auth:
  username: metrics_reader
  password_file: /run/secrets/orders-scrape-password
```

Do not configure conflicting authentication mechanisms simultaneously for the same job. `scrape_timeout` must not exceed `scrape_interval`. These address, timeout, authentication, and TLS fields are documented in [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

`management.prometheus.metrics.export.step` does not control when Prometheus opens connections to scrape. To change scrape frequency, change `scrape_interval` in Prometheus. Also distinguish this from `evaluation_interval` used for rule evaluation schedules, and Pushgateway which has its own push path.

After editing `prometheus.yml`, validate and reload configuration using Prometheus's operational mechanism. Simply editing the file does not prove the running process picked up the changes.

## 8. Layer-by-Layer Verification

Do not start with "is the number on the dashboard yet?" Trace the data path step by step.

### 8.1. Checking That Measurements Exist in the Application

For local diagnostics, you can temporarily allow the `metrics` endpoint in a controlled test environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
```

Assuming the application serves HTTP locally on port 8080, run the following command in PowerShell with `curl.exe`:

```powershell
curl.exe --fail --silent --show-error http://localhost:8080/actuator/metrics/jvm.memory.used
```

If the endpoint is secured, use the configured authentication method; the example does not intentionally disable security. A successful response must return data for the `jvm.memory.used` meter. Values and tags depend on the JVM, so there is no fixed JSON output identical across every run.

This evidence only confirms the application holds measurements and the diagnostic endpoint responds. It does not confirm the OTLP exporter has connected successfully.

### 8.2. Verifying the OTLP Push Path

Execute from the actual application runtime environment:

1. Confirm the OTLP registry is on the runtime classpath and the export path is enabled.
2. Inspect the effective non-sensitive URL: scheme, host, port, path; check DNS and network connectivity.
3. Check trusted certificate configuration and receiver authentication requirements.
4. Wait several intervals; inspect application export errors and ingestion status at the Collector or receiver.
5. Check the storage backend for time series matching the service, environment, instance, and time window.

Do not use an HTTP GET to `/v1/metrics` as a final proof. The OTLP ingestion path requires the right method and payload; GET may be rejected even when a valid exporter succeeds. Conversely, an HTTP 200 from a web page on the same host does not prove metrics ingestion works.

An accepted response at the collector only proves that ingestion tier processed the request per its contract. If the collector forwards downstream, you must also verify forwarding and stored data.

### 8.3. Verifying the Prometheus Pull Path

1. Confirm the endpoint returns metrics exposition format, not an HTML login page.
2. Check the corresponding target in Prometheus and its latest scrape error.
3. Query `up{job="orders"}` to view scrape status; a value of 1 indicates a successful target scrape, not a guarantee that every business metric is accurate.
4. Query an expected metric and cross-check the `instance` label and timestamps.
5. Change `scrape_interval`, reload configuration, and observe the new sample spacing.

One target succeeding when multiple instances exist is insufficient evidence that the entire application is being collected.

## 9. Diagnosing Failures by Symptom

| Symptom | Check First | Conclusion to Avoid |
| --- | --- | --- |
| Cannot resolve host | DNS from the caller's environment | Wrong token |
| Connection refused | Is the receiver running and listening on that port? | Just increasing read-timeout will fix it |
| Connection timed out | Route, firewall, network policy, receiver load | Shortening step is the solution |
| TLS certificate error | CA, hostname, expiration, system clock | Disable TLS verification in production |
| HTTP 401 | Auth scheme, missing/expired/wrong token | Meter was never created |
| HTTP 403 | Identity permissions, scopes, or gateway policy | Just changing the URL |
| HTTP 404 | Path, proxy route, endpoint exposure | Registry definitely isn't working |
| HTTP 405 or 415 | Method, protocol, payload format | Host does not exist |
| HTTP 429 | Receiver rate limits, frequency, and total load | Send faster to compensate |
| HTTP 5xx | Receiver and forwarding pipeline health | Business application is definitely broken |
| App starts cleanly but no external data | Exporter, export logs, receiver, and storage backend | Clean startup equals successful export |
| Data arrives but appears delayed | Export/scrape interval, processing queues, ingest, and dashboard | Only a single step knob controls latency |

HTTP status codes can be returned by a proxy or gateway; identify which component generated the response before drawing conclusions. A metrics export failure usually needs to be handled independently from business serving status. Do not assume the standard health endpoint reflects metrics-export health.

## 10. Controlled Practice

In a test environment, pick one export path and record before/after evidence for three changes:

1. **Address:** use a valid URL, then deliberately change the path to one that does not accept metrics. Observe the error, restore the URL, and confirm new data appears.
2. **Authentication:** when the receiver requires authentication, test invalid credentials and then restore the valid secret. Distinguish authentication rejection from authorization rejection; do not print tokens in reports.
3. **Interval:** change OTLP step from 30s to 10s, or change Prometheus scrape_interval from 30s to 10s. Apply the configuration via the proper mechanism and observe several intervals.

For push, use receipt timestamps at the Collector; for pull, use Prometheus scrape samples. Do not count dashboard redraws to infer the number of metric transmissions.

After each change, proceed to the next test only after restoring a working configuration. Compare: connection errors, authentication results, sample spacing, transmission counts, and data arriving at storage.

Test your ability to explain:

- Why can an application reach the Collector from a laptop yet fail inside a container?
- Why does changing `management.otlp.tracing.endpoint` not fix a metrics-sending error?
- Why do permissions and TLS still need checking even when a token is present?
- To have Prometheus scrape every 10 seconds, which process's configuration must change?
- Why might lowering the export interval not make a dashboard refresh any faster?
- What evidence is needed before concluding that metrics export works across all instances?

A complete setup aligns **the right address, the right identity, an appropriate interval, and end-to-end data proof**. Manage them per environment and verify after every change.
