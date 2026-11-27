# Resource Attributes in OpenTelemetry and Spring Boot

When viewing distributed traces of a Spring Boot system, operations teams need to know which service emitted a span, which deployment version, which environment, and which instance. If spans only show operation names without telemetry emitter identity, filtering by service or correlating with a rollout becomes very difficult. **Resource attributes** solve that identification need: they describe **the source producing telemetry**, such as the application, process, host, container, or workload emitting spans, metrics, or logs.

In the **SPRING_BOOT_OBSERVABILITY** module, resource attributes are part of setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. They must be designed alongside context propagation, tags/cardinality, exporters, and sampling so that when investigating errors or latency, signals can be grouped accurately by service, environment, and version.

This lesson belongs to the **OpenTelemetry** chapter and focuses on **Resource attributes**: the Resource model, service and runtime attributes, configuration via environment variables/SDK, integration with Spring Boot and Micrometer Tracing, metadata testing, data protection, and resolving mismatches across traces, metrics, and logs.

## Learning Objectives

After this lesson, you will be able to:

1. Explain Resource in OpenTelemetry and distinguish resource attributes from span attributes, baggage, instrumentation scope, and metric labels.
2. Select attributes identifying service, version, environment, and instance per Semantic Conventions.
3. Configure Resource attributes via `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, or the OpenTelemetry SDK.
4. Understand how Resource is attached to telemetry and why it is not per-request metadata.
5. Integrate Resource attributes in Spring Boot/Micrometer Tracing without creating multiple separate OpenTelemetry SDKs.
6. Inspect Resource in OTLP payloads, the Collector, and backends; handle merging/overrides when multiple sources supply attributes.
7. Control cardinality, sensitive data, and consistency across traces, metrics, and logs.

## 1. What Is a Resource?

In OpenTelemetry, a **Resource** describes the entity emitting telemetry. A Spring Boot application running in a container might have Resource attributes such as:

| Attribute | Example | Meaning |
| --- | --- | --- |
| `service.name` | `order-service` | Logical name of the service |
| `service.namespace` | `commerce` | Service group/namespace |
| `service.version` | `2.4.1` | Running application version |
| `service.instance.id` | `pod-7d9c8f-abc12` | Identifier of a specific instance |
| `deployment.environment.name` | `production` | Deployment environment |
| `host.name` | `node-03` | Hostname if collected and appropriate |
| `cloud.region` | `ap-southeast-1` | Cloud region |
| `k8s.namespace.name` | `commerce-prod` | Kubernetes namespace |
| `k8s.pod.name` | `order-service-7d9c8f-abc12` | Pod emitting telemetry |

Illustrative Resource example:

~~~text
Resource:
  service.namespace = commerce
  service.name = order-service
  service.version = 2.4.1
  service.instance.id = order-service-7d9c8f-abc12
  deployment.environment.name = production
  cloud.region = ap-southeast-1
~~~

Resource is typically attached at the `TracerProvider`, `MeterProvider`, or `LoggerProvider` level in the OpenTelemetry SDK; telemetry emitted by that provider carries the corresponding Resource information. As a result, backends can filter spans, metrics, and logs by service/instance without adding those values manually to every span.

### 1.1. Resource Answers "Who Emitted the Telemetry?"

- **Resource attributes:** which application or runtime emitted the telemetry? For example, `service.name=order-service`, `service.version=2.4.1`.
- **Span attributes:** what did this specific operation do? For example, `http.request.method=POST`, `http.route=/orders/{id}`, `db.system=postgresql`.

A single request can generate dozens of spans, yet their Resource is usually identical because they all originate from the same service instance. Span attributes vary per operation.

### 1.2. Resource Is Not Business Context

Do not place `order.id`, `customer.email`, request IDs, or individual order statuses into Resource attributes. Those values describe individual requests/transactions, not the telemetry source. They also vary per operation, breaking Resource semantics and increasing indexing/cardinality costs.

## 2. Distinguishing Resource Attributes from Other Metadata

| Type | Scope | Example | Changes Per Request? |
| --- | --- | --- | --- |
| Resource attributes | Telemetry emitter/provider | `service.name=order-service` | Usually no |
| Instrumentation scope | Library/instrumentation creating telemetry | Instrumentation name and version | Usually no |
| Span attributes | A single operation/span | `http.request.method=POST` | Can change |
| Baggage | Context propagated downstream | `orders.channel=web` | Can change |
| Metric labels/attributes | Identifying a time series or metric point | `http.response.status_code=500` | Can change, but cardinality must be bounded |
| Log fields | A single log event | `error.code=INVENTORY_TIMEOUT` | Can change |

### 2.1. Resource and Instrumentation Scope

Resource tells **which entity emitted telemetry**. Instrumentation Scope tells **which library or instrumentation generated the telemetry**. For instance, a span might be created by Spring Web, JDBC, or business instrumentation. Those spans share the `order-service` Resource while their scopes may differ.

Do not use `instrumentation.scope.name` in place of `service.name`: they answer two separate questions.

### 2.2. Resource and Span Attributes

~~~text
Resource:
  service.name = order-service
  service.version = 2.4.1

Span A:
  name = POST /orders
  http.request.method = POST
  http.route = /orders

Span B:
  name = inventory.reserve
  dependency.name = inventory
~~~

Do not duplicate `service.name` as a span attribute just so the backend can filter by service if Resource is already attached properly. However, some storage or export systems alter the structure; inspect actual Collector/backend output before writing queries.

### 2.3. Resource Is Not Baggage

Resource is generally set for the provider's lifecycle and does not vary per request. Baggage carries key-values inside trace context and can propagate over HTTP. Do not place Resource attributes into baggage to pass a service name downstream: each service should establish its own Resource identity.

For example, `service.name=order-service` belongs to `order-service`'s Resource. When calling `inventory-service`, the HTTP request continues the trace context, yet the Resource on spans emitted by `inventory-service` must be `service.name=inventory-service`.

## 3. Key Resource Attributes for Services

OpenTelemetry Semantic Conventions define standard keys so backends and tools interpret them uniformly.

### 3.1. `service.name`

`service.name` is the primary logical identifier of a service:

- Stable across replicas/instances of the same service.
- Does not change per request, user, or pod.
- Should be defined by architecture and used consistently across logs, metrics, and traces.
- Avoid overly generic names like `java-app` or `unknown_service` when the application has a clear identity.

Example: every replica of `order-service` in production uses `service.name=order-service`.

### 3.2. `service.namespace`

`service.namespace` helps group services within a domain:

~~~text
service.namespace = commerce
service.name = order-service
~~~

Combining both attributes distinguishes identically named services across different domains/systems when organizational conventions allow. This is a logical service namespace, not necessarily equal to a Kubernetes namespace.

### 3.3. `service.version`

`service.version` should represent a release version traceable to an artifact/release, such as `2.4.1`. A git SHA or build identifier can be used if the system follows clear conventions. Version should remain stable across the process lifetime. Do not generate a new version per request or dump full commit messages into Resource.

### 3.4. `service.instance.id`

`service.instance.id` distinguishes **one specific instance** among replicas sharing `service.name`. The value must be unique within the service scope per operational requirements and stable over the instance's lifetime. In Kubernetes, a pod name/UID or a platform-assigned instance identifier may fit depending on policy.

### 3.5. `deployment.environment.name`

The current Semantic Conventions attribute is `deployment.environment.name`, such as `development`, `staging`, or `production`. Older systems may use `deployment.environment`; when migrating, check the semantic convention version and backend support. Avoid emitting two inconsistent keys simultaneously without a compatibility plan.

### 3.6. Host, Container, Kubernetes, and Cloud Attributes

| Group | Example Attributes | Meaning |
| --- | --- | --- |
| Host | `host.name`, `host.id` | Machine running the process |
| Process | `process.pid`, `process.runtime.name` | OS process / JVM |
| Container | `container.id`, `container.image.name` | Container runtime |
| Kubernetes | `k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name` | Workload in cluster |
| Cloud | `cloud.provider`, `cloud.region`, `cloud.availability_zone` | Cloud infrastructure |

Not every attribute exists on every runtime. Collect them only when detectors can determine them reliably and the organization needs them. Avoid adding excessive host metadata that bloats Resource or exposes sensitive infrastructure details.

## 4. How Resource Is Created and Attached to Telemetry

~~~mermaid
flowchart TD
    Config["Environment / SDK configuration"] --> Resource["Resource attributes"]
    Detect["Resource detectors<br/>process, host, container, cloud"] --> Merge["Merge resources"]
    Resource --> Merge
    Merge --> Providers["TracerProvider / MeterProvider / LoggerProvider"]
    Providers --> Trace["Spans"]
    Providers --> Metrics["Metrics"]
    Providers --> Logs["Logs"]
    Trace --> Export["OTLP / exporter"]
    Metrics --> Export
    Logs --> Export
~~~

Resource is normally initialized alongside the provider and applied to all telemetry emitted by that provider. Some attributes come from application configuration; others come from runtime/deployment detectors. When multiple sources supply the same key, you must understand the SDK's merge/override rules and application order.

### 4.1. Resource Is Provider-Level Metadata, Not a Dynamic Scope

Do not create a new `TracerProvider` per request just to attach `service.version` or `tenant.id`. Doing so violates the model and can allocate heavy resources, duplicate exporters/thread pools, and lose shutdown control.

Resource is typically established at application startup. If an operation needs per-request metadata, consider span attributes or controlled baggage.

### 4.2. Immutability and Updating Resource

In the OpenTelemetry SDK, Resource is fundamentally immutable once the provider is configured. Changing `service.version` after a deployment normally requires a new process/provider with a new Resource, rather than mutating Resource on every span.

This aligns with immutable deployments: each release runs with its own version, while instances of the same release share `service.version`.

## 5. Configuring Resource Attributes in Spring Boot

When Spring Boot uses the Micrometer Tracing bridge to OpenTelemetry, ensure the application uses **a single unified, managed tracing infrastructure**. Illustrative dependencies for Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Keep dependency versions managed by the Spring Boot BOM. Adding the OpenTelemetry SDK or exporter does not mean Spring Boot automatically uses any arbitrary SDK beans you define manually; understand which provider/tracer auto-configuration creates.

### 5.1. Using `OTEL_SERVICE_NAME`

OpenTelemetry SDK Autoconfigure supports the environment variable:

~~~text
OTEL_SERVICE_NAME=order-service
~~~

This variable sets `service.name` when SDK autoconfigure is supported and configured in the application. It takes precedence for `service.name` over the same key in `OTEL_RESOURCE_ATTRIBUTES` under standard SDK autoconfigure rules.

### 5.2. Using `OTEL_RESOURCE_ATTRIBUTES`

Example:

~~~text
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging,service.instance.id=order-service-pod-abc12
~~~

This uses the comma-separated `key=value` syntax per OTel SDK conventions. Values must be encoded per environment variable/protocol rules if they contain special characters; avoid inserting strings containing commas or unsafe characters into values without verifying parser behavior.

In deployed environments, these variables can be set via container environment, deployment manifests, or secret/config management. Do not write different values per request.

**Important condition:** `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` are read by OpenTelemetry SDK Autoconfigure or a configuration layer supporting these standard variables. If the application configures the SDK/provider manually or uses a different auto-configuration, verify they actually take effect; do not assume they work solely because the variables are declared on the container.

### 5.3. Example `application.yml` and Deployment Env

You can keep the application name in Spring Boot:

~~~yaml
spring:
  application:
    name: order-service
~~~

And set deployment attributes via environment variables:

~~~yaml
env:
  - name: OTEL_SERVICE_NAME
    value: order-service
  - name: OTEL_RESOURCE_ATTRIBUTES
    value: service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
~~~

The `env` snippet illustrates container/Kubernetes manifest environment syntax, not root-level `application.yml` in Spring Boot. If managing configuration with Docker Compose or another platform, the declaration syntax differs while the environment variable names stay the same.

### 5.4. Do Not Confuse Resource Attributes with `management.metrics.tags`

Spring Boot's `management.metrics.tags.*` adds common tags to the metrics registry. They **do not automatically configure OpenTelemetry Resource for spans/logs**. Conversely, Resource attributes do not necessarily become metric labels in every registry/export format.

If both metrics and traces need the same service identity, configure both from a single release/deployment source and verify the actual output. Avoid editing them independently in separate places, which leads to `service.name=order-service` alongside metric tag `application=orders-api`.

## 6. Creating Resource Directly with the OpenTelemetry Java SDK

When building an application/library using the OpenTelemetry SDK directly or writing a standalone example, you can construct a Resource:

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

public class ResourceConfigurationExample {
    public static SdkTracerProvider createTracerProvider() {
        Resource serviceResource = Resource.create(
                Attributes.of(
                        AttributeKey.stringKey("service.namespace"), "commerce",
                        AttributeKey.stringKey("service.name"), "order-service",
                        AttributeKey.stringKey("service.version"), "2.4.1",
                        AttributeKey.stringKey("deployment.environment.name"), "staging"
                )
        );

        Resource resource = Resource.getDefault().merge(serviceResource);

        return SdkTracerProvider.builder()
                .setResource(resource)
                .build();
    }
}
~~~

This example demonstrates the Resource API in a **standalone OpenTelemetry SDK**. `Resource.getDefault()` supplies default attributes the SDK knows how to collect; `merge(serviceResource)` combines them with custom service attributes. With the Java SDK's merge behavior, values from the merged-in Resource can override matching keys in the original Resource.

**Do not drop this snippet mechanically into Spring Boot** if Boot/Micrometer already creates an `SdkTracerProvider`. Creating a second provider can route spans from different code paths to different exporters/resources, making traces hard to find. In a Boot application, prefer the configuration mechanism managed by auto-configuration; only configure the SDK manually when you truly own the entire tracing lifecycle.

### 6.1. Combining Detectors and Custom Resource

Resource detectors can pull details from process, host, container, Kubernetes, or cloud. Best practices:

1. Select detectors appropriate for the runtime environment.
2. Set service identity attributes using application/release-supplied configuration.
3. Merge in an intentional order, avoiding detectors overwriting `service.name` with generic defaults.
4. Inspect the final Resource before export.
5. Keep only runtime attributes genuinely needed for operations.

Do not enable all detectors just because they are available. Reading cloud/container metadata may require permissions or add traffic to metadata endpoints.

## 7. Resource Attributes Across Services and Environments

A multi-service trace can contain different Resources for each group of spans.

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

Resource: service.name=order-service
  Span: POST /orders
  Span: orders.checkout
  Span: HTTP POST inventory (CLIENT)

Resource: service.name=inventory-service
  Span: POST /reservations (SERVER)
  Span: db.query

Resource: service.name=payment-service
  Span: POST /charges (SERVER)
~~~

Trace context connects spans via trace ID and parent ID. Resource attributes identify which service emitted each span. **Do not propagate Resource from upstream to downstream**: `inventory-service` must report `service.name=inventory-service`, not `order-service`.

### 7.1. Replicas Share `service.name` While Keeping Distinct Instances

| Attribute | Pod A | Pod B | Pod C |
| --- | --- | --- | --- |
| `service.name` | `order-service` | `order-service` | `order-service` |
| `service.version` | `2.4.1` | `2.4.1` | `2.4.1` |
| `service.instance.id` | `order-pod-a` | `order-pod-b` | `order-pod-c` |
| `deployment.environment.name` | `production` | `production` | `production` |

When rolling out version `2.5.0`, new instances report `service.version=2.5.0`. Operations teams can compare errors and latency across versions and instances.

### 7.2. Service Name Is Not Hostname

`service.name` represents the logical service. `host.name`/`service.instance.id` represents the machine or running instance. If hostname is used as `service.name`, each replica may be classified by the backend as a separate service, fragmenting dashboards and trace searches.

## 8. Resource, Logs, and Metrics

Resource attributes can be semantically shared across traces, metrics, and logs if each signal pipeline supports it and is configured compatibly. However, encoding/storage representation can differ by exporter/backend.

~~~mermaid
flowchart TD
    App["Spring Boot application"] --> Resource["Resource identity<br/>service.name/version/environment"]
    Resource --> Trace["Traces / spans"]
    Resource --> Metrics["Metrics"]
    Resource --> Logs["Logs"]
    Trace --> OTLP["OTLP / Collector"]
    Metrics --> Registry["Micrometer registry / exporter"]
    Logs --> LogExport["Log pipeline"]
    OTLP --> TraceStore["Trace backend"]
    Registry --> MetricsStore["Metrics backend"]
    LogExport --> LogStore["Log backend"]
    TraceStore -. "service + time + traceId" .-> Investigation["Cross-signal investigation"]
    MetricsStore -. "service + environment" .-> Investigation
    LogStore -. "service + traceId" .-> Investigation
~~~

### 8.1. Resource Attributes and Micrometer Metrics

Micrometer metrics typically carry common tags such as `application`, `region`, and `environment`. An OpenTelemetry metrics exporter can attach Resource to metric data per the OTel model, whereas Prometheus scraping represents labels in the registry/exporter's own style. Therefore:

- Do not assume `service.name` is always exported as a Prometheus label if the registry does not configure that mapping.
- Do not attach `service.instance.id` as a label if the scrape/target system already supplies `instance`, unless strictly necessary.
- Keep metric labels few and stable; Resource identity is not a reason to add dynamic labels.
- Use a single source of deployment configuration to avoid drift in service/version/environment across signals.

### 8.2. Resource Attributes and Logs

The OpenTelemetry Logs Data Model also supports Resource. If logs are exported over OTLP with a compatible SDK/agent, Resource can group logs by `service.name` and `service.version`. If the application uses Logback/Log4j2 shipping logs through a standalone pipeline, service/environment fields must be configured in the corresponding appender/agent/collector; they are not automatically copied from OTel Resource.

### 8.3. Correlation Does Not Require Copying Resource into Every Log Line

Backends can group logs by Resource without repeating `service.name` inside the message text. For traditional file logs, structured fields or MDC may be needed to support querying. Avoid repeating bulky or inconsistent metadata in both the message and Resource.

## 9. Cardinality, Privacy, and Attributes That Should Not Be in Resource

Resource attributes generally have fewer combinations than span attributes, yet they can still multiply data groups and costs. `service.instance.id` changes per replica/rollout; that may be needed for traces, but when turned into metric labels it multiplies time series by instance count.

### 9.1. Suitable Data

| Attribute | Assessment |
| --- | --- |
| `service.name` | Essential, stable |
| `service.version` | Useful for rollout analysis |
| `deployment.environment.name` | Useful when values are standardized |
| `service.namespace` | Useful when grouping services |
| `service.instance.id` | Useful for per-instance investigation; watch metrics cardinality |
| `cloud.region` | Useful when regions are standardized |

### 9.2. Unsuitable Data

Do not place the following values into Resource attributes:

- `user.id`, `customer.email`, phone numbers, or personally identifiable information.
- `order.id`, `request.id`, `trace.id`, or IDs that change per request.
- Access tokens, cookies, passwords, API keys, or authentication material.
- Request bodies, response bodies, item lists, or SQL containing data.
- Per-request timestamps or random values generated per span.

Resource is attached to large volumes of process telemetry. A sensitive value placed into Resource can be duplicated across vast numbers of spans, metrics, or logs and retained long-term in backends.

### 9.3. Resource Attributes and Metric Cardinality

Suppose a metric has 4 `environment` values, 5 `region` values, 30 instances, and 10 routes. If every combination occurs, the number of series can reach:

\[
4 \times 5 \times 30 \times 10 = 6,000
\]

This is a simple model illustrating label combination cost. Avoid automatically turning every Resource attribute into a metric label. In particular, instance IDs and pod IDs can inflate series counts during autoscaling/rollouts.

## 10. Verifying Actual Resource Attributes

Never inspect environment variables alone and assume the backend received the right Resource. Verify from the SDK through the OTLP payload/Collector/backend.

### 10.1. Viewing in Collector Debug Output

With a Collector running the `debug` exporter in a test environment, Resource can be displayed alongside spans:

~~~text
ResourceSpans:
  Resource:
    service.name: order-service
    service.namespace: commerce
    service.version: 2.4.1
    deployment.environment.name: staging
  ScopeSpans:
    Spans:
      Span #0
        Name: POST /orders
~~~

Exact output names and formatting depend on the Collector/debug exporter version. The goal is to confirm the Resource on real spans has the expected keys and values.

### 10.2. Checking in the Trace Backend

Select an exported trace:

1. Open the root span of the entry service.
2. Verify `service.name`, `service.version`, `environment`, and `instance`.
3. Open a span belonging to a downstream service to confirm Resource switches to that service.
4. Cross-check release/version against the actual deployment.
5. Confirm there is no PII/secret or arbitrary key inside Resource.

If the backend displays only certain Resource fields, the UI may show default keys only or the backend may not index all fields. Check the OTLP payload/Collector output before concluding the SDK failed to send attributes.

### 10.3. Resource for Metrics and Logs

- Prometheus: inspect actual labels on scraped series; do not assume every Resource key becomes a label.
- OTLP metrics: inspect `ResourceMetrics` in collector/debug output.
- OTLP logs: inspect `ResourceLogs` if the logging pipeline uses OTLP.
- Logs via stdout/file: check structured fields, MDC, or the collector agent attaching service identity.

## 11. Testing Resource Configuration

Test Resource creation and export integration separately. Unit tests can validate keys/values in the SDK; integration tests validate the actual Resource exported to the Collector.

### 11.1. Unit Test with OpenTelemetry SDK Resource

~~~java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.resources.Resource;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ServiceResourceTest {
    @Test
    void containsExpectedServiceIdentity() {
        Resource resource = Resource.builder()
                .put("service.namespace", "commerce")
                .put("service.name", "order-service")
                .put("service.version", "2.4.1")
                .put("deployment.environment.name", "staging")
                .build();

        assertEquals("commerce", resource.getAttributes()
                .get(AttributeKey.stringKey("service.namespace")));
        assertEquals("order-service", resource.getAttributes()
                .get(AttributeKey.stringKey("service.name")));
        assertEquals("2.4.1", resource.getAttributes()
                .get(AttributeKey.stringKey("service.version")));
    }
}
~~~

This test verifies the `Resource` object constructed in code. It does not prove Spring Boot used that Resource or that the OTLP exporter sent it.

### 11.2. Testing Merge/Override Behavior

When configuring multiple Resource sources, write tests verifying duplicate keys merge in the expected order. For example, a detector Resource provides `service.name=unknown_service` while a custom Resource provides `service.name=order-service`; if the custom Resource is merged later and SDK semantics let the right-hand value override, the result must match the intended service name.

Do not assume source ordering is identical across every framework. Check the real provider/autoconfiguration before relying on precedence.

### 11.3. Integration Test with Collector

1. Run a service with `OTEL_SERVICE_NAME=order-service`.
2. Configure `OTEL_RESOURCE_ATTRIBUTES` including namespace, version, and environment.
3. Send a request that produces a span.
4. Receive OTLP data in a test Collector / debug exporter.
5. Assert Resource attributes appear with the expected values.
6. Boot `inventory-service` with its own name and verify its Resource is not inherited from `order-service`.
7. Cross-check logs/metrics identity with the deployment configuration.

This test verifies the real pipeline; a `Resource` object unit test cannot replace it.

## 12. Troubleshooting Resource Attributes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Backend shows `unknown_service` | Missing `service.name` or env var not read by SDK | Check `OTEL_SERVICE_NAME`, SDK autoconfigure, and Resource export |
| Every pod has a different service name | Pod/hostname assigned to `service.name` | Use stable logical service name, separate instance ID |
| Downstream shows upstream's Resource | Incorrectly copying Resource/baggage or shared service name config | Each process determines its own Resource |
| `service.version` mismatches release | Env/config out of sync with running artifact | Inject version from build/deployment metadata |
| Resource attribute missing in backend UI | Backend doesn't display/index the field or Collector transforms it | Inspect OTLP Resource before the backend |
| Mixing `deployment.environment.name` and legacy key | Multiple semantic convention/config versions | Standardize keys and migrate |
| Resource contains PII/secrets | Accidentally copied baggage/request data or unsuitable detector | Block at source, remove/rotate, assess telemetry copies |
| Metric labels spike per instance | Automatically mapping all Resource attributes to labels | Select essential tags; drop instance/pod labels if unneeded |
| Traces have right service, logs have wrong service | Log pipeline has separate identity config | Align service identity between logging appender/agent and OTel |
| `OTEL_RESOURCE_ATTRIBUTES` has no effect | SDK not using Autoconfigure or another config overrides it | Verify provider and final Resource |
| Two providers emit two different identities | Created separate SDK/provider or multiple auto-configurations | Use a single unified tracing lifecycle |

### 12.1. Layer-by-Layer Inspection Process

1. **Deployment:** do env vars/config maps have the right values inside the running container?
2. **SDK:** does the provider read standard env vars or Resource configuration?
3. **Merge:** does another detector/resource overwrite the key?
4. **Instrumentation:** which provider emits spans/metrics/logs?
5. **Exporter:** does the OTLP payload include the expected Resource?
6. **Collector:** do processors add, modify, or remove attributes?
7. **Backend/UI:** do queries and views support those fields?

Never alter span names or `traceparent` to fix a broken `service.name`. Resource identity and trace context are two separate concerns.

## 13. Production Checklist

| Criterion | Required Evidence |
| --- | --- |
| Stable `service.name` | All replicas of the same logical service share one name |
| Consistent `service.namespace` | Logical namespace per organizational convention |
| Accurate `service.version` | Matches the running release/artifact |
| `service.instance.id` distinguishes instances | Does not change per request |
| Standardized environment | `development`, `staging`, `production` under one convention |
| Runtime-appropriate detectors | No unnecessary metadata collected |
| Merge precedence verified | Unit/integration tests for duplicate keys |
| No PII/secrets | Security review and payload inspection |
| Resource not copied as baggage | Each service declares its own identity |
| Controlled metric label cardinality | Not blindly mapping all Resource keys to labels |
| Synchronized logs/traces/metrics identity | Queryable under the same service/version/environment |
| No duplicate SDK/provider | Single clearly managed lifecycle |
| Collector/backend preserve Resource | Verified payloads and queries in real environments |
| Version upgrades have regression tests | Semantic conventions and properties verified |

## 14. Hands-on Lab: Standardizing Resource for an Order System

**Context:** the system has `order-service`, `inventory-service`, and `payment-service`, deployed with multiple replicas on Kubernetes across staging and production. Dashboards currently display inconsistent service names and operations cannot filter traces by release.

**Tasks:**

1. Propose a unified Resource schema with `service.namespace`, `service.name`, `service.version`, `service.instance.id`, and `deployment.environment.name`.
2. Choose stable service names per service; do not use pod names as `service.name`.
3. Set `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` in a test environment.
4. Build a Java SDK `Resource` to inspect keys/values, then explain why a second standalone provider should not be created inside Spring Boot.
5. Run `order-service` calling `inventory-service`; verify spans share the same trace ID while keeping distinct `service.name` Resources.
6. Inspect Resource attributes in the Collector and trace backend; confirm version/environment match deployment.
7. Compare metric labels and log fields; identify which fields are not automatically copied from Resource.
8. Simulate misconfiguring `service.name` or letting the SDK fall back to `unknown_service`; build a detection and fix procedure.
9. Add tests for merge precedence and verify no `user.id`, email, token, or request ID appears in Resource.
10. Estimate cardinality impact if `service.instance.id` were added to all metric labels and explain how to constrain it.

**Expected deliverables:** a Resource schema, Spring Boot/deployment configuration, Resource unit test, OTLP integration test, multi-service trace diagram with separate Resources, and an operations checklist for version/deployment changes.

## 15. Key Takeaways

**Resource attributes describe the source emitting telemetry**: which service, which version, which instance, and which environment. `service.name` should be a stable logical name; `service.version` identifies the release; `service.instance.id` distinguishes replicas; environment/host/cloud/Kubernetes attributes add runtime context when needed.

Resource is distinct from span attributes, instrumentation scope, baggage, MDC, and metric labels. Configure Resource on the provider/SDK or via standard OpenTelemetry environment variables when supported by the SDK, check merge order, and never spin up a separate provider in Spring Boot if auto-configuration already manages the tracing lifecycle.

For consistent observability, the same deployment metadata must be reflected accurately across traces, metrics, and logs, while verifying the mapping to each signal separately. Keep Resource small, stable, and free of PII/secrets or per-request IDs; test from configuration through OTLP payloads and the backend rather than checking environment variables alone.

**References:**

- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/)
- [OpenTelemetry — Semantic Conventions: Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [OpenTelemetry — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
