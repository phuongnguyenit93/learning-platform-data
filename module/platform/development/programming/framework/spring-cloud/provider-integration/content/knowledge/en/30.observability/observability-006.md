# Integrating CloudWatch, Azure Monitor, or Google Cloud Observability with the right libraries

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. When applications run in the cloud, telemetry must be delivered to the platform your operations team uses: Amazon CloudWatch, Azure Monitor/Application Insights, or Google Cloud Observability.

A Spring Boot application typically needs three signal groups:

- **Metrics:** request counts, latency, error rates, JVM, connection pools, and business metrics.
- **Traces:** a request's journey across HTTP, message brokers, storage, databases, and workers.
- **Logs:** structured events, exceptions, correlation IDs, and provider request IDs.

Spring Boot provides a common foundation via Actuator, Micrometer Observation, and Micrometer Tracing. Each cloud provider ingests telemetry differently. CloudWatch has a Micrometer registry integrated with Spring Cloud AWS for metrics; Azure Monitor provides a starter/Java agent for Application Insights; Google Cloud recommends the OpenTelemetry SDK/Java Agent with a Collector to send OTLP into Cloud Logging, Cloud Monitoring, and Cloud Trace.

After this lesson, you will be able to:

- Select the right libraries for Spring Boot and your deployment platform.
- Export metrics from Micrometer to CloudWatch.
- Collect traces, metrics, and logs for Azure Monitor/Application Insights.
- Use the OpenTelemetry Collector to ship telemetry to Google Cloud Observability.
- Configure identity, permissions, region, project, and resource attributes.
- Design actionable dashboards, alerts, and SLOs.
- Control sampling, cardinality, ingestion costs, and sensitive data.
- Test the telemetry pipeline from the application to the backend.

## 2. Choosing the right integration layer

No single library fits every signal and every cloud. Separate the in-application instrumentation layer from the exporter/collector layer that ships data.

| Layer | Responsibility | Example |
|---|---|---|
| Spring Boot Actuator | Exposes endpoints and auto-config for health/metrics | `/actuator/health`, `/actuator/metrics` |
| Micrometer | Defines Timer, Counter, Gauge, Observation | `MeterRegistry`, `ObservationRegistry` |
| Micrometer registry | Sends metrics to a backend | CloudWatch registry, OTLP registry |
| OpenTelemetry instrumentation | Creates and propagates traces/spans | Java Agent, Micrometer Tracing bridge |
| Exporter/agent | Ships telemetry out of the process | Azure Monitor Java Agent, OTLP exporter |
| Infrastructure collector/agent | Receives, enriches, batches, filters, and routes telemetry | ADOT Collector, OpenTelemetry Collector |
| Cloud observability backend | Storage, querying, dashboards, and alerts | CloudWatch, Application Insights, Cloud Monitoring |

With Spring Boot, instrument business metrics using Micrometer Observation/`MeterRegistry`. Traces can use Micrometer Tracing with the OpenTelemetry bridge or the OpenTelemetry Java Agent. Logs should be written as structured output to stdout/stderr and collected by the environment's agent/collector.

Do not attach multiple agents/exporters that instrument the same library concurrently unless intentional. For instance, enabling the Azure Monitor Java Agent alongside another OpenTelemetry Java Agent can produce duplicate spans and metrics.

## 3. Overall architecture

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Actuator + Micrometer]
    A --> C[Tracing instrumentation]
    A --> D[Structured logs]
    B --> E{Metrics export}
    C --> F[Agent / OTLP exporter]
    D --> G[stdout / log collector]
    E --> H[CloudWatch]
    E --> I[Azure Monitor]
    E --> J[OpenTelemetry Collector]
    F --> J
    G --> J
    J --> K[Google Cloud Observability]
    F --> L[ADOT / Azure Monitor agent]
    L --> H
    L --> I
~~~

This diagram illustrates available options, not that one application should ship every signal to all three clouds. In real deployments, choose target backends per environment. A collector is valuable when you need to decouple apps from backends, standardize resource attributes, batch telemetry, or fan out data to multiple destinations.

## 4. Preparing the Spring Boot foundation

Add Actuator for metrics and health instrumentation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot automatically registers many meters for JVM, process, HTTP server, and supported components. For business metrics, use `MeterRegistry` or `ObservationRegistry` instead of calling CloudWatch/Azure/Google APIs directly from business services.

Example observation for a document-processing operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class DocumentService {
    private final ObservationRegistry observations;

    public DocumentService(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void generatePreview(String documentType) {
        Observation.createNotStarted(
                        "document.preview.generate", observations)
                .lowCardinalityKeyValue("document.type", documentType)
                .observe(() -> {
                    // Read source, render preview and persist the result.
                });
    }
}
~~~

Low-cardinality key/values are used for both metrics and traces. If you need job IDs or user IDs for investigation, add them only to traces/logs per policy; never put unbounded values into metric tags.

Configure the service name and required endpoints:

~~~yaml
spring:
  application:
    name: provider-integration

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  metrics:
    tags:
      application: provider-integration
      environment: production
~~~

Expose only needed endpoints inside an administrative network. The metrics endpoint aids local diagnostics; it does not push data to the cloud without a registry/exporter.

## 5. AWS: sending Micrometer metrics to CloudWatch

### 5.1. Choosing the registry and Spring Cloud AWS

Spring Cloud AWS provides auto-configuration for Micrometer CloudWatch. In current Spring Cloud AWS 3.x/4.x lines, the registry dependency is:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-cloudwatch2</artifactId>
</dependency>
~~~

Use the Spring Cloud AWS BOM matching your project's Spring Boot and Spring Cloud AWS versions. Do not pin a separate Micrometer registry version outside dependency management. Older Spring Cloud AWS 2.x projects use different artifacts/properties; do not copy 2.x configuration into 3.x/4.x projects.

Spring Cloud AWS 3.x/4.x uses the newer configuration namespace:

~~~yaml
management:
  cloudwatch:
    metrics:
      export:
        namespace: ProviderIntegration
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
        region: ap-southeast-1
~~~

Namespace is required. Pick a dedicated namespace per application or bounded context to find metrics easily in CloudWatch. Region must be the region where CloudWatch metrics are published.

In the local profile, disable the publisher to avoid sending test metrics to AWS:

~~~yaml
spring:
  cloud:
    aws:
      cloudwatch:
        enabled: false
~~~

### 5.2. Identity and IAM permissions

The Micrometer CloudWatch registry uses the AWS SDK to call CloudWatch. Spring Cloud AWS configures region and credentials providers following the AWS SDK chain. On AWS, prefer workload-bound IAM roles:

- EC2: instance profile.
- ECS: task role.
- EKS: IAM Roles for Service Accounts (IRSA) or EKS Pod Identity.
- Lambda: execution role.

Never place static access keys/secret keys in `application.yml` or container images. Local development can use AWS profiles/SSO through the credential provider chain.

The core permission to publish metrics is `cloudwatch:PutMetricData`. Example namespace-scoped policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "cloudwatch:PutMetricData",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "ProviderIntegration"
        }
      }
    }
  ]
}
~~~

This policy only illustrates permission to write metrics into the selected namespace. Reading dashboards or alarms belongs to operator roles and should not be granted automatically to the application's runtime role.

### 5.3. Verifying published metrics

After running the application with the AWS profile:

1. Generate traffic so meters record data.
2. Open CloudWatch Metrics.
3. Select the `ProviderIntegration` namespace.
4. Inspect dimensions such as `application`, `environment`, `instance`, or configured tags.
5. Compare metric arrival time against the export step.

The CloudWatch publisher sends batches periodically rather than immediately after every request. If `step` is 1 minute, wait at least a couple of intervals before concluding export failed.

## 6. AWS: metric filtering, dimensions, and cost

Each unique combination of metric name and dimensions becomes a billable custom metric. Spring Boot auto-registers many meters for JVM, CPU, memory, and other components. Publishing all of them unchecked can raise CloudWatch costs quickly.

Use a `MeterFilter` to publish only necessary metrics:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CloudWatchMetricsConfiguration {
    @Bean
    MeterFilter cloudWatchMetricAllowList() {
        Set<String> allowed = Set.of(
                "http.server.requests",
                "jvm.memory.used",
                "jvm.gc.pause",
                "process.cpu.usage",
                "document.preview.duration",
                "document.preview.errors");

        return MeterFilter.denyUnless(
                id -> allowed.contains(id.getName()));
    }
}
~~~

Verify exact meter names from your application's registry before adding them to the allow-list. Note that a global `MeterFilter` affects all registries in the process; if you want to filter only CloudWatch, configure the filter on the CloudWatch registry/auto-configuration according to your version.

Dimensions should have small, stable value sets:

- `application`: `provider-integration`.
- `environment`: `dev`, `staging`, `production`.
- `provider`: `aws`, `azure`, `gcp`.
- `operation`: `upload`, `download`, `send_message`.
- `outcome`: `success`, `error`.

Never use request ID, trace ID, customer ID, object key, or exception message as metric dimensions. Those belong in logs/traces.

Spring Cloud AWS can use `MeterFilter` to restrict published meters. Choose an export step balancing dashboard freshness and cost; shorter steps update faster but increase publish frequency.

## 7. AWS: logs and traces via ADOT/CloudWatch

The Micrometer CloudWatch registry primarily covers metrics. To send traces and logs, use appropriate instrumentation/collectors:

- **Traces:** OpenTelemetry Java Agent or AWS Distro for OpenTelemetry (ADOT) Java Agent, sending OTLP to the ADOT Collector; the collector exports traces to AWS X-Ray.
- **Logs:** the application writes structured JSON to stdout/stderr; CloudWatch Agent, ECS log driver, FireLens, or platform pipelines ship logs to CloudWatch Logs.
- **Metrics:** Micrometer CloudWatch registry or ADOT Collector/CloudWatch EMF depending on architecture.

Illustrative startup Java Agent configuration:

~~~bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/aws-opentelemetry-agent.jar"
~~~

The agent path must point to the JAR packaged in the image/runtime. Configure exporter endpoints and resource attributes to match your deployed ADOT Collector. Do not assume adding the Micrometer CloudWatch registry automatically exports traces or logs.

On ECS/EKS, consider running the collector as a sidecar or daemon/service per platform architecture. A collector can batch, retry, enrich resource attributes, and ship telemetry without coupling applications directly to X-Ray APIs.

## 8. Azure: choosing Azure Monitor OpenTelemetry Distro or Spring starter

Azure Monitor/Application Insights can ingest metrics, traces, and logs. For Java/Spring Boot, there are two main paths:

1. **Spring Cloud Azure Starter Monitor:** integrates as a Spring Boot native application dependency using Spring Cloud Azure dependency management.
2. **Application Insights Java Agent:** attached via JVM argument to auto-instrument frameworks and libraries without altering business code.

Do not enable both the starter and the Java Agent on the same application unless you have explicitly coordinated them. Running two instrumentation mechanisms together can produce duplicate spans, metrics, or logs.

### 8.1. Spring Cloud Azure Starter Monitor

Add the dependency matching your Spring Boot version via the Spring Cloud Azure BOM:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-monitor</artifactId>
</dependency>
~~~

This starter provides Spring Boot telemetry and integrates Azure Monitor OpenTelemetry. Microsoft documents importing the OpenTelemetry BOM alongside the monitor starter; follow the exact version matrix for your chosen Spring Cloud Azure release. Do not add mismatched standalone OpenTelemetry versions when the BOM manages them.

Configure the Application Insights connection string via environment variable:

~~~bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
~~~

Never commit connection strings to Git or bake them into container images. The connection string identifies the telemetry destination; it does not replace identity and authorization when Microsoft Entra authenticated ingestion is enabled.

### 8.2. Application Insights Java Agent

With the Java Agent, add the JVM argument before `-jar`:

~~~bash
java -javaagent:/opt/azure/applicationinsights-agent.jar -jar app.jar
~~~

Set the connection string in the environment:

~~~bash
APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
~~~

The Java Agent auto-instruments HTTP servers/clients, JDBC, messaging, and many supported libraries. Check the supported instrumentation list for your agent version, since not every library or custom transport is covered.

If programmatic attachment is desired, Microsoft provides a runtime attach mechanism with specific JRE, temp-directory write permission, and call-site requirements. For production containers, the JVM argument is usually simpler to control.

## 9. Azure: Managed Identity and Microsoft Entra authentication

In production, prefer Managed Identity to authenticate telemetry sent to Application Insights rather than storing long-lived secrets.

For the Application Insights Java Agent supporting Microsoft Entra authentication:

1. Enable a system-assigned or user-assigned Managed Identity on the workload.
2. Assign the **Monitoring Metrics Publisher** role scoped to the Application Insights resource.
3. Use an Application Insights Java Agent version that supports Entra ingestion (3.2.0 or later).
4. Configure authentication per agent documentation.

Example with a system-assigned identity:

~~~bash
APPLICATIONINSIGHTS_AUTHENTICATION_STRING="Authorization=AAD"
~~~

With a user-assigned identity, include the client ID per documentation format:

~~~bash
APPLICATIONINSIGHTS_AUTHENTICATION_STRING="Authorization=AAD;ClientId=<managed-identity-client-id>"
~~~

Although the **Monitoring Metrics Publisher** role has "Metrics" in its name, it authorizes publishing telemetry—not just metrics—to Application Insights. Scope the role only to the required resource. Verify your agent version and Entra auth behavior before disabling local authentication on the resource.

In local development, use authentication methods supported for developer environments. Never put client secrets into `application.yml` just to make telemetry work.

## 10. Azure: resource attributes, sampling, and data verification

Set service name and resource attributes so Application Map distinguishes multiple services reporting to one Application Insights resource:

~~~bash
OTEL_SERVICE_NAME="document-api"
OTEL_RESOURCE_ATTRIBUTES="service.namespace=provider-integration,deployment.environment=production,service.version=1.2.0"
~~~

When multiple applications share one resource, configure cloud role name/role instance per Azure guidance so Application Map renders the topology accurately.

Sampling controls ingestion volume. Do not leave 100% tracing enabled by default in high-traffic production. Choose an appropriate sampling policy, keep sampling decisions consistent across services, and verify impact on trace completeness.

After running the application:

1. Send an HTTP request and perform a cloud operation.
2. Open Application Insights.
3. Inspect Requests, Dependencies, Exceptions, Traces, and Metrics.
4. Use Application Map to verify services and dependencies are recognized.
5. Wait a few minutes if telemetry does not appear immediately.

If Requests appear without Dependencies, inspect instrumentation for that client library. If logs appear without trace links, verify MDC/structured logging and trace correlation.

## 11. Google Cloud: choosing the OpenTelemetry Collector

Google Cloud Observability encompasses Cloud Logging, Cloud Monitoring, and Cloud Trace. Google's recommended integration pattern for many environments is:

1. Instrument the application with the OpenTelemetry SDK or Java Agent.
2. Send telemetry over OTLP to an OpenTelemetry Collector sidecar/agent.
3. The Collector receives, batches, and enriches resource attributes.
4. The Collector exports telemetry to the Google Cloud project via the Telemetry API.

This keeps the application in a vendor-neutral format. When switching backends or running multi-cloud, you can swap collectors/exporters without rewriting business code.

Google provides a Spring Boot Java sample using the OpenTelemetry Java Agent, OTLP, and Collector. For logs, the sample writes structured JSON to stdout; the collector reads logs via `filelog` receiver and ships them alongside traces/metrics to Google Cloud.

### 11.1. Attaching the OpenTelemetry Java Agent

Startup example:

~~~bash
JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar"
OTEL_SERVICE_NAME="document-api"
OTEL_RESOURCE_ATTRIBUTES="service.namespace=provider-integration,deployment.environment=production"
OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
~~~

Port 4317 typically serves OTLP/gRPC; if the Collector only exposes OTLP/HTTP, configure the corresponding endpoint/protocol, typically port 4318. The endpoint in this example is the Collector's internal service address, not a public Google Cloud URL.

The Java Agent auto-instruments supported frameworks and libraries. For custom business metrics, you can still use Micrometer Observation/`MeterRegistry` or the OpenTelemetry API and let the exporter/collector receive telemetry per your chosen architecture.

### 11.2. Structured logs and trace correlation

Write JSON logs to stdout/stderr. To link logs with traces, include fields following Cloud Logging conventions:

- `logging.googleapis.com/trace`: trace resource name.
- `logging.googleapis.com/spanId`: span ID.
- `logging.googleapis.com/trace_sampled`: `true` or `false`.

The OpenTelemetry Java Agent can populate span context in MDC. Your logging layout must map trace/span IDs into the corresponding JSON fields. If your GKE environment already collects structured logs automatically, do not install a duplicate log-collection agent.

## 12. Google Cloud: service accounts and telemetry write permissions

On production workloads, use a workload-bound service account instead of long-lived JSON keys:

- GKE: Workload Identity Federation for GKE.
- Compute Engine: VM-attached service account.
- Cloud Run: service identity of the service.
- Local development: Application Default Credentials (ADC) via developer login workflow.

Commonly required telemetry writer roles:

| Role | Permission |
|---|---|
| `roles/logging.logWriter` | Write logs to Cloud Logging |
| `roles/monitoring.metricWriter` | Write metrics to Cloud Monitoring |
| `roles/telemetry.tracesWriter` | Write traces via the Telemetry API |
| `roles/serviceusage.serviceUsageConsumer` | Use quota project when required |

Enable the required APIs if not already enabled on the project: Cloud Logging, Cloud Monitoring, Cloud Trace, and Telemetry API. Enabling APIs usually requires project admin permissions; the runtime service account only needs minimal telemetry write roles.

Never mount a service account JSON key into a production container when workload identity is available. If local development needs an ADC credentials file, keep it strictly developer-local and never commit it.

## 13. Comparing the three integration options

| Criterion | AWS CloudWatch | Azure Monitor | Google Cloud Observability |
|---|---|---|---|
| Metrics with Spring Boot | Micrometer CloudWatch registry, Spring Cloud AWS auto-config | Starter Monitor/OpenTelemetry Distro collects Micrometer metrics | OpenTelemetry SDK/Agent + Collector; can export Micrometer via OTLP |
| Traces | ADOT/OpenTelemetry to X-Ray | Azure Monitor OpenTelemetry Java Agent/Starter | OpenTelemetry Java Agent + Collector to Cloud Trace |
| Logs | JSON stdout + CloudWatch Agent/FireLens/collector | Java Agent/Starter or structured logs via agent | JSON stdout + collector/agent to Cloud Logging |
| Identity | IAM role/workload identity | Managed Identity + Microsoft Entra ID | Service account/workload identity + ADC |
| Where to view | CloudWatch Metrics, Logs, X-Ray, Application Signals | Application Insights, Azure Monitor | Metrics Explorer, Logs Explorer, Trace Explorer |
| Watch out for | Custom metrics and dimensions incur cost | Sampling, roles, and connection string | Collector, IAM roles, APIs, and resource attributes |

If you operate multi-cloud or want backend flexibility, the OpenTelemetry Collector is a valuable intermediary layer. If an application runs on a single cloud and favors idiomatic Spring integration, the provider's registry/starter can reduce configuration.

## 14. Managing configuration by profile and environment

Never enable production publishers during unit tests or local runs. Separate configuration using Spring profiles:

~~~yaml
# application.yml
spring:
  application:
    name: provider-integration

management:
  metrics:
    tags:
      application: provider-integration
~~~

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      cloudwatch:
        enabled: false
~~~

~~~yaml
# application-aws.yml
management:
  cloudwatch:
    metrics:
      export:
        namespace: ProviderIntegration
        step: 1m

spring:
  cloud:
    aws:
      cloudwatch:
        enabled: true
        region: ap-southeast-1
~~~

Azure and Google Cloud typically receive connection strings, OTLP endpoints, project IDs, and resource attributes from environment variables or deployment manifests. Never bundle all three sets of credentials into a single configuration file. Enable only the exporter matching the deployed environment.

## 15. Dashboards, alerts, and SLOs

Each backend builds dashboards differently, yet the core signals should stay consistent:

- Request throughput and error rate.
- p50/p95/p99 latency.
- JVM heap, GC pause, CPU, and thread utilization.
- Database/HTTP/cloud dependency latency.
- Queue age, backlog, and dead-letter counts if the application uses messaging.
- Business metrics such as successful document previews.

Example SLOs for a document-processing API:

- 99% of requests complete under 1 second.
- Final error rate below 0.5% over a 30-minute window.
- 99% of messages start processing within 60 seconds.

These thresholds are illustrative. Choose SLOs based on product requirements and real traffic baselines. Alerts should rely on burn rate/error budgets and sustained windows to avoid paging on brief spikes.

CloudWatch uses alarms and dashboards; Azure Monitor uses metric alerts, log alerts, and workbooks; Google Cloud uses alerting policies, dashboards, and SLO monitoring. Standardize metric, service, and operation names so the same workload can be compared across clouds.

## 16. Cardinality, sampling, security, and cost

### 16.1. Keeping cardinality low

Only use labels/tags with small value sets:

- `provider`: `aws`, `azure`, `gcp`.
- `service`: `s3`, `blob`, `pubsub`.
- `operation`: `upload`, `download`, `send_message`.
- `outcome`: `success`, `error`.
- `environment`: `dev`, `staging`, `production`.

Never use request ID, trace ID, user ID, tenant ID, object key, or exception message as metric labels. Those values belong in logs/traces.

### 16.2. Sampling and batching

Trace sampling affects how many traces are stored and must never alter business logic. Keep sampling consistent across services and verify parent-based propagation. Use collector batch processors and bounded retries/queues to absorb transient backend unavailability.

### 16.3. Protecting data

- Never log tokens, SAS URLs, access keys, private keys, or full connection strings.
- Never place sensitive payloads into span attributes or baggage.
- Restrict read access to logs/traces since telemetry may contain internal metadata.
- Use TLS for OTLP over untrusted networks.
- Use IAM/Managed Identity/service accounts with least-privilege write permissions.
- Configure retention and ingestion sampling to satisfy compliance, security, and budget requirements.

### 16.4. Controlling cost

CloudWatch bills custom metrics per metric/dimension combination; Azure Monitor bills ingestion/retention by data type and volume; Google Cloud charges based on ingestion, retention, and the Observability products used. Monitor volume, sampling, time-series counts, and log verbosity before scaling out in production.

## 17. Testing telemetry integration

Do not send production telemetry during unit tests. Decouple business metrics from backend exporters so they can be verified with an in-memory registry:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentMetricsTest {
    @Test
    void recordsPreviewSuccess() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.counter(
                "document.preview.completed",
                "provider", "azure",
                "outcome", "success")
            .increment();

        assertEquals(
                1.0,
                registry.get("document.preview.completed")
                        .tag("provider", "azure")
                        .tag("outcome", "success")
                        .counter()
                        .count());
    }
}
~~~

Integration tests should verify:

1. The application context boots with the right exporter dependency.
2. Metrics use the expected names and tags.
3. The exporter targets the right endpoint, region, namespace, or project.
4. The workload identity holds permission to write telemetry.
5. The collector receives OTLP and forwards successfully.
6. JSON logs contain service name and trace correlation fields.
7. Shutdown flushes buffered telemetry.

LocalStack can verify parts of AWS client interaction, though it does not fully validate CloudWatch ingestion/billing semantics. For Azure/Google, use test resources with scoped permissions; run a controlled smoke test and verify data in the portal.

## 18. Symptom-based troubleshooting

| Symptom | Possible cause | Fix |
|---|---|---|
| CloudWatch lacks custom metrics | Missing namespace or `PutMetricData` permission | Verify namespace, region, IAM role, and export logs |
| CloudWatch metrics appear delayed | Registry publishes per step interval | Wait a few intervals and check `step` |
| CloudWatch bill climbs rapidly | Too many meter/dimension combinations | Apply `MeterFilter`, cut tag cardinality, and drop unused meters |
| Azure Monitor receives no telemetry | Wrong connection string, role, or exporter config | Check `IngestionEndpoint`, Managed Identity, and self-diagnostics |
| Azure Application Map merges services | Cloud role name not differentiated | Configure cloud role name/role instance |
| Azure traces are duplicated | Both starter and Java Agent instrumenting | Keep only one instrumentation path |
| Google Cloud lacks metrics/traces | Wrong collector endpoint or exporter | Check OTLP port/protocol, Collector logs, and project |
| Google Cloud reports PermissionDenied | Service account missing roles | Check `logging.logWriter`, `monitoring.metricWriter`, `telemetry.tracesWriter` |
| Google Cloud logs lack trace links | JSON layout omits special trace fields | Check MDC and `logging.googleapis.com/trace`/`spanId` |
| Metrics appear but traces do not | Tracing exporter disabled or sampling dropped traces | Check agent, exporter, and sampling |
| Logs appear locally but not in backend | stdout collector/agent unconfigured | Check log driver, `filelog` receiver, or agent |
| Exporter adds load / queue grows | Slow backend or under-provisioned collector | Enable batching, bounded retries, and monitor dropped telemetry |
| Local tests write to cloud | Exporter enabled in test profile | Disable exporter in local/test and use `SimpleMeterRegistry` |

When debugging, verify step by step: does the application create meters/spans/logs; does the exporter receive them; does the identity have permissions; does the collector route properly; and does the backend ingest and store the data.

## 19. Hands-on exercises and self-check questions

**Scenario A — AWS CloudWatch:** A Spring Boot app runs on EKS. Add the Micrometer CloudWatch registry, configure namespace, region, IAM role, and a `MeterFilter` publishing only HTTP/JVM/business metrics. Verify metrics appear in CloudWatch and explain how dimensions affect cost.

**Scenario B — Azure Monitor:** An app runs on Azure App Service. Choose between Spring Cloud Azure Starter Monitor and the Application Insights Java Agent; configure connection string, Managed Identity, and the Monitoring Metrics Publisher role; verify Requests, Dependencies, and Exceptions in Application Insights.

**Scenario C — Google Cloud:** An app runs on GKE. Attach the OpenTelemetry Java Agent, point the OTLP endpoint to a Collector sidecar, configure Workload Identity and the three logs/metrics/traces writer roles; verify data in Metrics Explorer, Logs Explorer, and Trace Explorer.

**Scenario D — Multi-cloud:** The same service deploys across AWS, Azure, and GCP. Standardize `service.name`, `environment`, `operation`, `outcome`, and business metrics to compare latency/error rates without putting resource IDs in metric labels.

**Scenario E — Rising cost:** CloudWatch custom metrics spike after adding a `customerId` tag. Explain cardinality and use `MeterFilter`/low-cardinality tags to bound time series.

**Scenario F — Duplicate telemetry:** An Azure app uses both Spring Cloud Azure Starter Monitor and the Application Insights Java Agent. Show how to detect duplicate instrumentation and select a single clean path.

**Scenario G — Collector disruption:** The Collector temporarily loses connectivity to Google Cloud. Design batching, retries, queues, and shutdown flushing; state memory limits and data-loss risks if the process is killed.

### Self-check questions

1. **Does Actuator automatically push metrics to the cloud?** No; a Micrometer registry, exporter, or collector is required.
2. **Which dependency provides the CloudWatch registry in current Spring Cloud AWS?** `micrometer-registry-cloudwatch2`.
3. **What is the CloudWatch namespace property in Spring Cloud AWS 3.x/4.x?** `management.cloudwatch.metrics.export.namespace`.
4. **What is the basic AWS permission to write metrics?** `cloudwatch:PutMetricData`.
5. **Why use `MeterFilter` when publishing to CloudWatch?** To limit published meters and dimensions, reducing billable custom metrics.
6. **What Java/Spring Boot integration paths does Azure offer?** Spring Cloud Azure Starter Monitor or Application Insights Java Agent; avoid overlapping instrumentation.
7. **Which Azure role authorizes sending telemetry to Application Insights with Entra auth?** Monitoring Metrics Publisher.
8. **What export pattern does Google recommend when a collector can run?** OpenTelemetry SDK/Java Agent sending OTLP to a Collector that exports to Google Cloud.
9. **Which telemetry writer roles does Google Cloud require?** Logs Writer, Monitoring Metric Writer, and Cloud Telemetry Traces Writer.
10. **Why distinguish OTLP ports 4317 and 4318?** 4317 typically uses gRPC and 4318 uses HTTP; endpoint/protocol must match the receiver.
11. **Should request IDs be used as metric labels?** No; unique values create high cardinality.
12. **How do you verify end-to-end export?** Generate traffic, inspect app instrumentation, exporter/collector, IAM, and data in the portal/backend.

## 20. Summary

Spring Boot provides a shared instrumentation layer via Actuator, Micrometer, and OpenTelemetry. When integrating cloud backends, choose libraries according to the signals you export and deployment topology: **Spring Cloud AWS + `micrometer-registry-cloudwatch2`** for CloudWatch metrics; **Spring Cloud Azure Starter Monitor or Application Insights Java Agent** for Azure Monitor; and **OpenTelemetry Java Agent/SDK + Collector** for Google Cloud Observability.

CloudWatch requires a namespace, region, IAM `PutMetricData`, and `MeterFilter` to control custom metrics/dimensions. Azure requires an Application Insights resource, connection string, the right starter/agent, and Managed Identity with the Monitoring Metrics Publisher role for Entra-authenticated ingestion. Google Cloud requires Collector/OTLP, service account/workload identity, and the required APIs and writer roles for logs/metrics/traces.

Keep resource attribute schemas consistent, avoid high-cardinality metric labels, control sampling/ingestion, protect credentials, and test from application to backend. With a standardized architecture, operations teams can evaluate applications using the same dashboards and SLOs whether running on AWS, Azure, or Google Cloud.

### Official references

- [Spring Cloud AWS 4.1 — CloudWatch metrics](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html#cloudwatch-metrics)
- [Spring Cloud AWS 3.4 — CloudWatch metrics](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html)
- [Micrometer — CloudWatch registry](https://docs.micrometer.io/micrometer/reference/implementations/cloudwatch.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Microsoft Learn — Enable Azure Monitor OpenTelemetry for Java](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=java-native)
- [Microsoft Learn — Azure Monitor with Spring Boot](https://learn.microsoft.com/en-us/azure/azure-monitor/app/java-spring-boot)
- [Microsoft Learn — Configure Application Insights OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration)
- [Microsoft Learn — Microsoft Entra authentication for Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/azure-ad-authentication)
- [Google Cloud — Java instrumentation sample](https://docs.cloud.google.com/stackdriver/docs/instrumentation/setup/java)
- [Google Cloud — Collector-based instrumentation samples](https://docs.cloud.google.com/stackdriver/docs/instrumentation/setup/sample-overview)
- [Google Cloud — Use the Google-Built OpenTelemetry Collector](https://docs.cloud.google.com/stackdriver/docs/otlp)
