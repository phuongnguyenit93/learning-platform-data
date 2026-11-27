# `OTEL_SERVICE_NAME`: Service Identity in OpenTelemetry and Spring Boot

> **Chapter:** OpenTelemetry  
> **Lesson:** `OTEL_SERVICE_NAME`  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Do We Need a Unified Service Name?

A system might consist of `api-gateway`, `order-service`, `inventory-service`, and `payment-service`. Each process emits traces, metrics, and logs. When telemetry reaches the OpenTelemetry Collector or observability backend, operators need to know **which process produced the telemetry** in order to filter, group, and compare.

In OpenTelemetry, this identity is represented primarily by the resource attribute:

~~~text
service.name = order-service
~~~

**`OTEL_SERVICE_NAME`** is the standard environment variable used to set the value of the **`service.name`** resource attribute in SDKs/autoconfigurations that support OpenTelemetry environment variables.

Example running Spring Boot:

~~~bash
OTEL_SERVICE_NAME=order-service java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
java -jar app.jar
~~~

When a compatible OpenTelemetry SDK reads the environment configuration, telemetry from that process receives this resource identity. The service name lives in the resource, not as an ad-hoc tag added to every span.

The goal of this lesson is to understand `OTEL_SERVICE_NAME`, distinguish it from `spring.application.name`, `service.namespace`, and instance identity; configure it per environment; verify the resource across traces/metrics/logs; and avoid producing multiple inconsistent names for the same service.

## 2. What Is a Resource in OpenTelemetry?

A **Resource** describes the entity generating telemetry, such as a service process, container, host, or workload. A Resource is typically shared across many spans, metrics, and log records from the same process or SDK.

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = order-service-pod-k2m4p
~~~

| Resource attribute | Meaning | Example |
| --- | --- | --- |
| `service.name` | Stable logical name of the service | `order-service` |
| `service.namespace` | Group containing the service | `commerce` |
| `service.version` | Application version | `2.4.1` |
| `deployment.environment.name` | Deployment environment | `production` |
| `service.instance.id` | Instance identifier | Pod/process ID |

`service.name` should be stable across replicas of the same service. Do not put pod IDs, random hostnames, request IDs, or build versions into `service.name`; those are separate dimensions.

~~~mermaid
flowchart TD
  A["Process Resource"] --> B["service.name: order-service"]
  A --> C["service.namespace: commerce"]
  A --> D["service.version: 2.4.1"]
  A --> E["service.instance.id: pod/process"]
  B --> F["Spans, metrics, logs"]
  C --> F
  D --> F
  E --> F
~~~

Resource helps the backend answer which service, version, and instance emitted the telemetry. If the same application runs 10 replicas, the replicas typically share `service.name`, while `service.instance.id` distinguishes individual instances.

## 3. What Does `OTEL_SERVICE_NAME` Configure?

`OTEL_SERVICE_NAME` is an environment variable for OpenTelemetry SDK configuration. When a compatible SDK/autoconfiguration reads this variable, its value is used as `service.name` in the resource.

~~~bash
OTEL_SERVICE_NAME=inventory-service
~~~

Expected Resource:

~~~text
service.name = inventory-service
~~~

Key points to remember:

- This is the logical name of the service, not the JAR name, Java class name, or endpoint URL.
- Multiple processes/containers of the same service can share the same `service.name`.
- Each instance can be identified using `service.instance.id`.
- Changing the variable usually affects telemetry emitted by processes started with the new configuration.
- This variable does not create spans, metrics, or logs on its own, nor does it replace an exporter.
- If an application uses an SDK that does not read OpenTelemetry environment variables, setting the variable may have no effect.

**Important condition:** you must know whether the process uses the OpenTelemetry Java agent, OpenTelemetry SDK autoconfiguration, or another bridge/integration. Do not assume every Spring Boot application with Micrometer automatically reads `OTEL_SERVICE_NAME`.

## 4. `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`

OpenTelemetry supports configuring resource attributes via multiple environment variables:

- `OTEL_SERVICE_NAME`: dedicated value for `service.name`.
- `OTEL_RESOURCE_ATTRIBUTES`: list of resource attributes, such as `service.namespace=commerce,service.version=2.4.1`.

Bash:

~~~bash
export OTEL_SERVICE_NAME=order-service
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
$env:OTEL_RESOURCE_ATTRIBUTES = "service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -jar app.jar
~~~

Expected Resource:

| Key | Value |
| --- | --- |
| `service.name` | `order-service` |
| `service.namespace` | `commerce` |
| `service.version` | `2.4.1` |
| `deployment.environment.name` | `production` |

According to OpenTelemetry SDK environment configuration rules, `OTEL_SERVICE_NAME` is the dedicated way to set `service.name` and takes precedence when the same attribute also appears in `OTEL_RESOURCE_ATTRIBUTES`. Avoid declaring conflicting values; use one intentional source and verify the resulting resource.

Values containing commas or special characters must be escaped according to SDK-supported syntax. Keep resource values simple and non-sensitive.

## 5. Distinguishing from `spring.application.name`

In Spring Boot, `spring.application.name` is commonly used as the application name across the Spring ecosystem and can be integrated into the service name in Micrometer/Tracing configurations.

~~~yaml
spring:
  application:
    name: order-service
~~~

These two settings belong to different configuration layers:

| Configuration | Owning Layer | Purpose |
| --- | --- | --- |
| `spring.application.name` | Spring Boot / Spring Environment | Spring application name |
| `OTEL_SERVICE_NAME` | OpenTelemetry SDK environment configuration | Sets the `service.name` resource attribute |
| `OTEL_RESOURCE_ATTRIBUTES` | OpenTelemetry SDK environment configuration | Sets resource attributes |
| `service.instance.id` | Resource/deployment configuration | Distinguishes instances |

Do not assume the two values always stay automatically synchronized in every stack. Behavior depends on the tracing implementation, bridge, exporter, and auto-configuration.

### 5.1. When Using a Micrometer Tracing Bridge

Spring Boot can use Micrometer Observation/Tracing with either the Brave or OpenTelemetry bridge. When telemetry is generated by Micrometer and its corresponding exporter, the resource is constructed by that integration/SDK. Whether `OTEL_SERVICE_NAME` takes effect depends on the actual resource configuration path.

- With the OpenTelemetry Java agent or SDK autoconfiguration, standard environment variables are processed according to SDK/agent configuration.
- With the Micrometer Tracing bridge to OpenTelemetry, verify how the OpenTelemetry SDK/resource is initialized and whether autoconfiguration reads environment variables.
- With the Brave bridge/Zipkin reporter, do not assume OpenTelemetry environment variables apply merely because the app uses Micrometer Observation.

If `spring.application.name` is `order-api` yet the backend resource shows `unknown_service:java` or another name, check the integration/resource configuration instead of renaming spans in bulk.

## 6. Setting Environment Variables per Runtime Environment

### 6.1. Linux/macOS Shell

~~~bash
export OTEL_SERVICE_NAME=order-service
java -jar target/order-service.jar
~~~

The current shell and child processes launched from it inherit the variable. Other terminals or service managers have their own environments.

### 6.2. PowerShell

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
java -jar .\target\order-service.jar
~~~

Remove the variable from the current session:

~~~powershell
Remove-Item Env:OTEL_SERVICE_NAME
~~~

Changes in the current session do not alter Windows Service configurations, running containers, or already deployed workloads.

### 6.3. Docker

~~~dockerfile
ENV OTEL_SERVICE_NAME=order-service
~~~

Or at runtime:

~~~bash
docker run --rm -e OTEL_SERVICE_NAME=order-service order-service:latest
~~~

Docker Compose:

~~~yaml
services:
  order-service:
    image: order-service:latest
    environment:
      OTEL_SERVICE_NAME: order-service
      OTEL_RESOURCE_ATTRIBUTES: service.namespace=commerce,deployment.environment.name=staging
~~~

Multiple replicas of the same service should use the same `OTEL_SERVICE_NAME`. Do not name them after the container ID; instance identity belongs in its own attribute.

### 6.4. Kubernetes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:2.4.1
          env:
            - name: OTEL_SERVICE_NAME
              value: order-service
            - name: OTEL_RESOURCE_ATTRIBUTES
              value: service.namespace=commerce,deployment.environment.name=production
~~~

This is a minimal example; real Deployments require additional operational fields. You can use the Downward API to inject pod identity into a dedicated resource attribute if supported by the SDK/integration. Do not put the pod name into `service.name`, or each pod will appear as a separate service.

## 7. Attaching `service.name` to Traces, Metrics, and Logs

`service.name` is a resource attribute. When the same OpenTelemetry Resource is used across multiple signals, the backend can group telemetry under the same service identity:

~~~text
Resource:
  service.name = order-service
  service.namespace = commerce
  service.version = 2.4.1

Trace:
  span = orders.create
  trace_id = ...

Metric:
  name = orders.processing.duration
  value = ...

Log:
  body = "order accepted"
  trace_id = ...
~~~

Signals may be exported through separate pipelines. Seeing `service.name` on a trace does not automatically prove metrics and logs use the same SDK/resource. If metrics come from Prometheus scraping, labels attached by Prometheus targets/relabeling can differ from OTLP trace resource attributes.

**Resource identity aids grouping, not correlation:** trace ID/span ID link spans and log records belonging to a single request; `service.name` identifies which service emitted the telemetry.

### 7.1. One Service, Multiple Signals

| Signal | Desired Metadata |
| --- | --- |
| Traces | Resource `service.name=order-service` |
| OTLP metrics | Resource `service.name=order-service` |
| OTLP logs | Resource `service.name=order-service` |
| Prometheus scrape | Target labels like `job`, `instance`, mappable back to service |

If pipelines have separate resource configurations, standardize naming conventions. Do not use `order-api` on traces, `orders` on metrics, and `order-service-prod` on logs if they represent the same logical service, unless there is a clear reason.

## 8. `service.name`, Namespace, Version, and Instance ID

Resource attributes form a structured identity:

~~~text
service.namespace = commerce
service.name = order-service
service.version = 2.4.1
service.instance.id = order-service-pod-7d9f
deployment.environment.name = production
~~~

A helpful mental model:

- Namespace groups services belonging to a domain.
- Name is the stable identifier of the logical service.
- Version enables comparing deployed releases.
- Instance ID distinguishes a single process/container/replica.
- Environment separates staging, production, and other environments.

| Pod | `service.namespace` | `service.name` | `service.instance.id` |
| --- | --- | --- | --- |
| `order-abc` | `commerce` | `order-service` | `order-abc` |
| `order-def` | `commerce` | `order-service` | `order-def` |
| `order-ghi` | `commerce` | `order-service` | `order-ghi` |

The backend can display one logical service with three instances. If you use pod name as `service.name`, dashboards/service maps fracture into three artificial services.

There is no single rule for generating instance IDs across every runtime. Choose an ID that stays stable over the instance's lifetime, is unique within the scope the backend needs to distinguish, and never changes between requests.

## 9. A Resource Attribute Is Neither a Span Attribute Nor a Metric Label

A common mistake is setting the service name by manually adding `service.name` to every span. With OpenTelemetry, service identity belongs at **resource scope** and should not be repeated on every span if the SDK already supplies the resource.

| Data Level | Example | Meaning |
| --- | --- | --- |
| Resource | `service.name=order-service` | Process/service emitting data |
| Span attribute | `http.request.method=POST` | Detail of a single operation |
| Metric attribute | `outcome=error` | Distinguishes metrics along a cardinality-controlled dimension |
| Log attribute | `event.action=order-created` | Metadata of a log record |

For metrics, each attribute combination can contribute to creating a series. If you use user ID or request ID as metric labels, cardinality can explode. `service.name` is a resource identity whose value set is typically small—bounded by the number of logical services—though consistent naming is still essential.

Do not manually add `service.name` to every `Observation` just to make it show up in the backend. First check the resource generated by the SDK/bridge.

## 10. Java Agent and SDK Autoconfiguration

There are several ways to introduce OpenTelemetry into a Java application. You must distinguish them because `OTEL_SERVICE_NAME` only takes effect when the corresponding configuration component reads it.

### 10.1. OpenTelemetry Java Agent

The Java agent is typically attached at JVM startup via `-javaagent`:

~~~bash
OTEL_SERVICE_NAME=order-service \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
java -javaagent:/opt/otel/opentelemetry-javaagent.jar \
     -jar target/order-service.jar
~~~

This example assumes the agent JAR exists, the Collector endpoint is reachable, and the exporter configuration matches the agent version. The agent provides autoconfiguration and instrumentation for many supported libraries.

You do not need to add a separate OpenTelemetry SDK in code just to use the agent, unless the application has specialized integration needs.

### 10.2. OpenTelemetry SDK Autoconfiguration

An application initializing the OpenTelemetry SDK can use autoconfiguration to read environment variables. When that SDK builds its resource, `OTEL_SERVICE_NAME` is applied according to SDK configuration rules.

If application code builds a custom `Resource` and attaches it to a provider, understand resource merge order and SDK configuration. Never assume environment variables always override any code-defined resource across every implementation.

### 10.3. Micrometer Tracing Bridge

Spring Boot can connect Micrometer Tracing to the OpenTelemetry bridge. Identify which auto-configuration creates `OpenTelemetry`/`SdkTracerProvider` and where `Resource` is configured. If the integration does not run OpenTelemetry SDK autoconfiguration, `OTEL_SERVICE_NAME` might not be read as expected.

**Do not run the Java agent alongside manual/framework instrumentation covering the same function unintentionally.** Two instrumentation layers can produce duplicate spans for the same HTTP request or JDBC call. When using the agent, check which libraries the agent already instruments before adding manual `Observation`s.

## 11. Verifying the Actual Service Name

Do not inspect environment variables alone and conclude the backend received the right resource. Verify telemetry after it passes through the SDK and exporter.

### 11.1. Inspecting Process Environment

Linux/macOS:

~~~bash
echo "$OTEL_SERVICE_NAME"
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME
~~~

Docker:

~~~bash
docker exec <container-name> printenv OTEL_SERVICE_NAME
~~~

This check only proves the variable exists in the process/container environment. It does not prove the SDK read it or the exporter transmitted the resource.

### 11.2. Inspecting the Collector or Backend

In a test environment, send a request to generate a trace. Open resource attributes and verify:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
~~~

If OTLP metrics/logs are enabled, verify the same resource attributes on each signal. For Prometheus, check target labels and relabeling configs; resource representation differs from OTLP.

### 11.3. Checking Default Values

When no service name is configured, some OpenTelemetry SDKs fall back to defaults like `unknown_service` or a variant including runtime/process details. This makes dashboards hard to group and should not be considered an acceptable production identity.

Set a stable name and verify after deployment. Never rely on defaults, as runtimes/SDKs may format them differently.

## 12. Naming Conventions for `service.name`

The service name is an operational identifier, so choose a stable convention and apply it consistently:

- Use clear logical names like `order-service`, `inventory-service`, `payment-service`.
- Use the exact same name across all replicas of the same service.
- Avoid embedding the environment in the service name when environment already has its own resource attribute.
- Avoid embedding the version in the service name when version already has `service.version`.
- Avoid names containing pod IDs, hostnames, request IDs, user IDs, or dynamic data.
- Define ownership and naming conventions whenever creating a new service.

| Avoid | Prefer | Reason |
| --- | --- | --- |
| `order-service-prod` | `order-service` + `environment=production` | Separates logical service from environment |
| `order-service-v2.4.1` | `order-service` + `version=2.4.1` | Easier version comparison |
| `order-service-7d9f8c` | `order-service` + instance ID | Prevents every replica from becoming a separate service |
| `/api/orders/12345` | `order-service` | Never use a route/request as service identity |

Changing a service name can split metrics/traces history into two separate buckets in the backend, affecting dashboards, alerts, and service maps.

## 13. Common Configuration Conflicts

| Source | Example | What to Verify |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | `order-service` | Does SDK autoconfiguration read this variable? |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.name=orders,service.version=2.4.1` | Are there conflicting values? |
| `spring.application.name` | `order-api` | Does the Bridge/Spring Boot mapping use this value? |
| Java agent config | Agent resource attributes | Are they loaded and merged? |
| SDK code configuration | Resource built in code | What is the merge/override order? |
| Collector processor | Resource attribute transform | Is it renamed after receipt? |

When `service.name` is not what you expect, trace from source to backend:

1. Actual process environment.
2. SDK/agent/autoconfiguration initializing the tracer.
3. Merged Resource and attribute precedence.
4. Bridge or exporter.
5. Collector processors modifying the resource.
6. Backend-specific mappings or display logic.

Do not change every source at once. Adjust one source at a time in a test environment and observe the final resource to pinpoint which source actually wins.

## 14. Risks of Misconfiguring Service Name

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Multiple services appear as `unknown_service` | SDK does not read service name or Resource unconfigured | Check agent/autoconfiguration and resource |
| Every pod becomes a separate service | Pod ID placed in `OTEL_SERVICE_NAME` | Use stable logical name; move pod identity to instance ID |
| Traces have a different name from metrics | Signals use different SDK/resource pipelines | Align resource identity and check exporters |
| `spring.application.name` is right but OTel resource is wrong | SDK/bridge ignores Spring property or another source overrides | Check mapping/effective resource |
| Env var changed yet backend unchanged | Process not restarted or service manager didn't pass env | Inspect running process environment |
| `service.name` varies by environment | Service name has `-dev`, `-prod` suffixes | Use a dedicated environment attribute |
| Span name used instead of service name | Confusing operation name with resource identity | Set resource and span name at the proper level |
| Collector shows a different name | Processor transforms/overrides resource | Inspect Collector pipeline |
| Duplicate spans from Java agent and manual instrumentation | Overlapping instrumentation | Choose one owner per boundary |

## 15. Real-World Scenario: Three Replicas of `order-service`

**Context:** `order-service` runs three replicas in Kubernetes. Initially, the team set `OTEL_SERVICE_NAME` to the pod name, causing the backend to display three separate services:

~~~text
order-service-7dd6-x1
order-service-7dd6-y2
order-service-7dd6-z3
~~~

Dashboards searching for `order-service` failed to aggregate data and the service map fractured.

### Step 1 — Unify the Logical Name

~~~yaml
- name: OTEL_SERVICE_NAME
  value: order-service
~~~

### Step 2 — Distinguish Individual Instances

~~~text
service.name = order-service
service.instance.id = order-service-7dd6-x1
~~~

Repeat for the remaining pods. The backend can group all three replicas under the same service name while still distinguishing each instance.

### Step 3 — Keep Environment and Version Separate

~~~text
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
~~~

### Step 4 — Verify All Signals

Inspect resources across traces, metrics, and logs. Service name matches, instance IDs differ, and metrics/traces/logs do not use conflicting naming conventions.

**Expected outcome:** dashboards aggregate the service accurately, allow version comparisons, and drill down to individual instances without creating fake services for each pod.

## 16. Hands-on Practice

### Exercise A — Verify the Environment Variable

1. Start an application with appropriate OpenTelemetry SDK/agent autoconfiguration.
2. Set `OTEL_SERVICE_NAME=order-service`.
3. Send a request to produce a trace.
4. Open resource attributes in the backend.
5. Verify `service.name` is `order-service`.
6. Unset the variable in the test environment and observe your SDK's fallback behavior.

### Exercise B — Compare Configuration Sources

In an isolated environment, configure:

- `OTEL_SERVICE_NAME=order-service`
- `OTEL_RESOURCE_ATTRIBUTES=service.name=orders,service.namespace=commerce`
- `spring.application.name=order-api`

Observe the resulting `service.name` and explain which source was actually read and what precedence rules apply in your stack. Never run conflicting configuration experiments in production.

### Exercise C — Multi-Instance

Run three replicas with the same `OTEL_SERVICE_NAME` and distinct instance IDs. Verify the backend aggregates the service while still allowing drill-down to each replica.

### Exercise D — Multiple Signals

Inspect traces, OTLP metrics, and logs. Compare `service.name`, `service.version`, and `service.namespace` resource attributes. If Prometheus scrapes metrics, compare target labels against OTLP resource attributes.

### Self-Check Questions

1. Which resource attribute does `OTEL_SERVICE_NAME` configure?
2. How does a Resource differ from span attributes?
3. How does `OTEL_SERVICE_NAME` differ from `OTEL_RESOURCE_ATTRIBUTES`?
4. Why shouldn't `service.name` contain a pod ID?
5. Does `spring.application.name` always automatically override `OTEL_SERVICE_NAME`?
6. When does the OpenTelemetry Java agent/SDK read environment variables?
7. Why doesn't a Micrometer Tracing configuration necessarily read every `OTEL_*` variable automatically?
8. How does `service.instance.id` differ from `service.name`?
9. Why might metrics and traces display different service names?
10. Can the Collector modify resource attributes after receiving telemetry?
11. If the backend displays `unknown_service`, which layers should be checked?
12. Why shouldn't sampling or span names be used to work around a resource identity bug?

**Completion criteria:** explain `OTEL_SERVICE_NAME` and `service.name`; distinguish resource, span attributes, and instance identity; distinguish from Spring's `application.name`; configure process/container environments; understand agent/SDK/bridge differences; verify final resources across traces/metrics/logs and resolve conflicts.

## 17. Key Takeaways

- `OTEL_SERVICE_NAME` is the OpenTelemetry environment variable used to set the `service.name` resource attribute when supported by the corresponding SDK/autoconfiguration.
- `service.name` is the stable logical name of the service; replicas of the same service share it.
- `service.instance.id`, `service.version`, `service.namespace`, and environment describe distinct dimensions; do not merge them all into the service name.
- `OTEL_RESOURCE_ATTRIBUTES` sets other resource attributes; avoid declaring a `service.name` that conflicts with `OTEL_SERVICE_NAME`.
- `spring.application.name` belongs to Spring Boot. Mapping to the OTel resource depends on the integration; do not assume every bridge reads `OTEL_SERVICE_NAME`.
- The Java agent, SDK autoconfiguration, and Micrometer bridge are different integration approaches. Identify which component actually creates the Resource before debugging.
- Resource identity can be shared across traces/metrics/logs when pipelines are configured consistently. Prometheus target labels remain a separate metadata layer.
- Verify the final resource in the backend. Seeing an environment variable inside the process does not prove the exporter sent the right value.

## References

- [OpenTelemetry — Semantic Conventions: Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [OpenTelemetry Specification — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry Java — Agent configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
