# Configuring Resource Attributes for OTLP in Spring Boot

> **Chapter:** OTLP export  
> **Lesson:** Configuring resource attributes  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Does OTLP Need Resource Attributes?

A Spring Boot application can export traces, metrics, and logs via the OpenTelemetry Protocol (OTLP). When telemetry arrives at the Collector or backend, the data needs to answer the question: **who produced this data?** A span has an operation name and its own attributes, yet you still need to know which service, version, and environment it belongs to.

OpenTelemetry represents information about the telemetry-producing entity using **Resource**. A Resource is a collection of attributes attached to signals emitted by the same entity, such as a service process or workload.

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = order-service-pod-a7d2
~~~

When an exporter transfers telemetry over OTLP, the resource travels alongside the data in the OTLP structure. The Collector and backend use resource attributes to group, filter, route, index, or distinguish services.

If resources are misconfigured, multiple services may appear under default names such as unknown service, or each replica may be treated as a separate service. Dashboards, service maps, alerts, and queries then become difficult to use.

## 2. How Does Resource Differ From Span Attributes?

Resource describes **the entity emitting telemetry**. Span attributes describe **a specific operation**. Both are key-value pairs, yet their scope and lifecycle differ.

| Data Type | Scope | Example |
| --- | --- | --- |
| Resource attribute | Service/process emitting telemetry | `service.name=order-service` |
| Span attribute | A single span | `http.request.method=POST` |
| Span event attribute | An event inside a span | `exception.type=TimeoutException` |
| Metric attribute | A grouping dimension for a measurement | `outcome=success` |
| Log attribute | A single log record | `event.action=order-created` |
| Baggage | Metadata propagated across context | `region=ap-south` |

~~~mermaid
flowchart TD
  A["Resource: order-service"] --> B["Trace signal"]
  A --> C["Metrics signal"]
  A --> D["Logs signal"]
  B --> E["Span: orders.create"]
  E --> F["Span attributes: channel, result"]
  C --> G["Metric: orders.duration"]
  G --> H["Metric attributes: channel, outcome"]
  D --> I["Log record: order accepted"]
~~~

Do not manually copy `service.name` onto every span if the SDK already attaches the Resource. Do not treat a span attribute as if it will automatically become a Resource attribute. If service identity sits at the wrong level, the backend may fail to group telemetry by service as expected.

## 3. Important Resource Attributes

Commonly used attributes describing a service:

| Attribute | Meaning | Example |
| --- | --- | --- |
| `service.name` | Stable logical name of the service | `order-service` |
| `service.namespace` | Group or domain containing the service | `commerce` |
| `service.version` | Application version | `2.4.1` |
| `service.instance.id` | Identifier of a specific instance | pod name or instance ID |
| `deployment.environment.name` | Deployment environment | `production` |
| `service.role` | Not a standard universal service attribute; use only if a custom convention is defined | `api` |

Prefer current OpenTelemetry semantic conventions for attribute names and meanings. For instance, environment is commonly described by `deployment.environment.name` in newer semantic conventions; older systems may have `deployment.environment`. When migrating, verify the backend and convention version to avoid creating two keys with the same meaning.

### 3.1. `service.name` Must Be Stable

Replicas of the same logical service share the same `service.name`. Do not embed pod ID, hostname, request ID, or values changing on every deployment into the service name.

~~~text
service.name = order-service
service.instance.id = order-service-7dd7-pq8m
service.version = 2.4.1
~~~

Three replicas can share `service.name` while having distinct `service.instance.id` values. This allows the backend to aggregate by service while still drilling down into individual instances.

### 3.2. Namespace and Environment Are Separate Dimensions

`service.namespace` groups services by system domain; `deployment.environment.name` describes the environment. Example:

~~~text
service.namespace = commerce
service.name = order-service
deployment.environment.name = staging
~~~

Avoid renaming it to `order-service-staging` when the environment can be represented separately. Separating dimensions makes it easy to compare the same service between staging and production.

## 4. `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`

OpenTelemetry SDK environment configuration defines environment variables used to configure Resource:

- `OTEL_SERVICE_NAME` sets the dedicated value for `service.name`.
- `OTEL_RESOURCE_ATTRIBUTES` sets a set of resource attributes as a key-value string.
- `OTEL_RESOURCE_ATTRIBUTES` is commonly used for namespace, version, environment, and other resource metadata.

Bash:

~~~bash
export OTEL_SERVICE_NAME=order-service
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
$env:OTEL_RESOURCE_ATTRIBUTES = "service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -javaagent:C:\otel\opentelemetry-javaagent.jar -jar .\app.jar
~~~

Desired Resource:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
~~~

According to SDK environment variable rules, `OTEL_SERVICE_NAME` is the dedicated way to set `service.name` and takes precedence if `service.name` also appears in `OTEL_RESOURCE_ATTRIBUTES`. Avoid declaring two conflicting values; a single clear authoritative source is easier to operate.

`OTEL_RESOURCE_ATTRIBUTES` syntax has escaping rules. Do not append arbitrary request-derived values into this variable. Only include stable configuration metadata with no secrets.

## 5. Configuring Resource in Spring Boot

Spring Boot and Micrometer have their own configuration layers. The Spring application name is commonly declared as:

~~~yaml
spring:
  application:
    name: order-service
~~~

This name may be used in certain integrations as service identity or tracing metadata. However, do not assume `spring.application.name` and `OTEL_SERVICE_NAME` always synchronize automatically across every stack.

When using the OpenTelemetry Java agent or SDK autoconfiguration, `OTEL_*` environment variables are read by the corresponding OpenTelemetry component. When using the Micrometer Tracing bridge, verify how the SDK/resource is initialized and which properties actually affect Resource.

Example OTLP tracing configuration in Spring Boot 3.x (depending on minor version and exporter):

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

The snippet above illustrates the Spring name, sampling, and trace endpoint. It does not automatically declare all resource attributes like namespace, version, or instance ID. Resource must come from the SDK, agent, bridge, or configured resource customization.

**Principle:** establish one authoritative configuration source for `service.name` and verify the outcome in OTLP telemetry. Do not assume setting `spring.application.name` makes every exporter/SDK produce the same resource.

## 6. Resource With Micrometer Observation and Micrometer Tracing

Micrometer Observation is an abstraction describing an observed operation. Observation handlers can forward context to metrics and tracing. Resource identity belongs to the registry/tracing implementation configuration, not as a separate low-cardinality key-value on every Observation.

Example business Observation:

~~~java
Observation.createNotStarted("orders.create", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> orderService.create());
~~~

In this example:

- `orders.create` is the observation name.
- `channel=web` describes the operation and can be included in metrics/spans depending on handlers.
- `service.name` describes the service emitting telemetry and should not be manually attached repeatedly to every Observation.
- Resource is provided by the corresponding tracing SDK, bridge, or registry/exporter.

If the same application uses `PrometheusMeterRegistry` for metrics and the OTel bridge for traces, how service identity is attached may differ. Inspect the two pipelines separately and standardize naming conventions.

## 7. How OTLP Transmits Resource in the Data Model

OTLP is the telemetry transport protocol. Resource is represented in `ResourceSpans`, `ResourceMetrics`, and `ResourceLogs` structures, corresponding to traces, metrics, and logs.

~~~text
ExportTraceServiceRequest
  resource_spans[]
    resource
      attributes[]
        service.name = order-service
        service.namespace = commerce
    scope_spans[]
      spans[]
        name = orders.create
        trace_id = ...
~~~

For metrics and logs, the structure is analogous:

~~~text
ResourceMetrics
  resource
  scope_metrics
    metrics

ResourceLogs
  resource
  scope_logs
    log_records
~~~

This allows multiple spans or metric/log records sharing a resource to be grouped in a payload. Exporters can batch data by resource and instrumentation scope. Do not confuse Resource with instrumentation scope: scope describes the library/instrumentation that produced the telemetry, such as the name and version of the instrumentation library.

## 8. Example: Inspecting Resource in the Collector

The OpenTelemetry Collector can receive OTLP and display or process Resource attributes. A minimal illustrative pipeline:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      exporters: [debug]
    logs:
      receivers: [otlp]
      exporters: [debug]
~~~

This configuration illustrates a Collector version supporting the debug exporter per its matching schema. In real environments, replace `debug` with an appropriate target exporter and secure the OTLP-receiving endpoint.

When sending telemetry, debug logs can reveal Resource attributes before the Collector exports onward. This is a useful check to distinguish between:
- The application did not create the attribute.
- The exporter did not include the attribute in the payload.
- A Collector processor modified or removed the attribute.
- The backend mapped or rendered the attribute differently.

The Collector can transform Resource, yet requires explicit processor configuration and testing. Do not let multiple processors overwrite `service.name` without clear rules.

## 9. Adding or Standardizing Resource With a Collector Processor

In some architectures, the Collector is used to add deployment metadata or standardize Resource. Conceptual example using the `resource` processor:

~~~yaml
processors:
  resource:
    attributes:
      - key: deployment.environment.name
        value: production
        action: upsert
      - key: service.namespace
        value: commerce
        action: upsert

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [resource]
      exporters: [otlp]
~~~

The `resource` processor can insert, update, upsert, delete, or hash attributes according to actions supported by the version. Verify processor schema and actions against your running Collector version.

### 9.1. Where Should Resource Attributes Be Created?

There are three main options:

| Location | When Appropriate | Risk |
| --- | --- | --- |
| Application/SDK | Service knows name, version, and build metadata | Configuration may drift across replicas |
| Java agent/autoconfiguration | Want standardized environment configuration | Need to know which variables the agent reads and how resources merge |
| Collector | Want to enrich cluster/environment metadata centrally | May overwrite wrong values or obscure original source |

Prefer creating the core `service.name` identity at an authoritative source close to the application. The Collector can supplement reliable infrastructure metadata, yet must preserve semantics. If the Collector forces all telemetry into the same `service.name`, dashboards lose the ability to distinguish services.

## 10. Precedence and Resource Conflicts

Resource can be constructed from multiple sources: SDK defaults, environment variables, agent configuration, code, Spring Boot integration, and Collector processors.

Example conflict:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES="service.name=orders,service.version=2.4.1"
spring.application.name=order-api
Collector upsert service.name=commerce-api
~~~

The final result should not be guessed from a list of sources. Check the merge rules of the SDK/agent, Spring integration mapping, and processors running after the exporter.

Investigation order:

1. Actual process environment.
2. Whether the SDK/agent/autoconfiguration reads the environment.
3. Resource builders in code or framework.
4. Which resource the bridge/exporter puts into OTLP.
5. Whether Collector processors alter attributes.
6. Whether the backend has custom mapping or transformation.

Per SDK environment configuration, `OTEL_SERVICE_NAME` is the dedicated variable for `service.name` and takes precedence over the same key inside `OTEL_RESOURCE_ATTRIBUTES`. Other sources follow their own rules; do not generalize this precedence as a universal rule across Spring Boot, Collector, and backends.

## 11. Resource Identity Across Traces, Metrics, and Logs

OpenTelemetry applies the Resource model across multiple signals, yet that does not mean all pipelines in an application share the exact same Resource object.

| Signal | Potential Resource Source | How to Verify |
| --- | --- | --- |
| OTLP traces | OTel SDK / tracing bridge | Inspect `ResourceSpans` |
| OTLP metrics | OTel `MeterProvider` or registry exporter | Inspect `ResourceMetrics` |
| OTLP logs | OTel Logs SDK/bridge | Inspect `ResourceLogs` |
| Prometheus scrape | Target labels and registry conventions | Check labels at scrape endpoint |
| Regular application logs | Logging framework/agent | Check log attributes and correlation |

An application might export traces via OTLP while exporting metrics via Prometheus scrape. In that case, Prometheus labels come from the registry, target config, and relabeling; do not assume they match OTLP Resource attributes verbatim.

To unify, define logical service name, namespace, version, and environment; configure each pipeline accordingly and verify with real data. Consistent Resource is the foundation for correlating dashboards, trace search, and logs, though `traceId`/`spanId` remain necessary to link a specific request.

## 12. Kubernetes: Service Identity and Instance Metadata

In Kubernetes, a Deployment typically has multiple replicas. Resource settings should distinguish the logical service from the pod instance.

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
              value: service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
~~~

`POD_NAME` here only provides environment data; it does not automatically become `service.instance.id`. Configure the SDK/agent or resource customization to map it to the right attribute if needed. Do not append `POD_NAME` onto `OTEL_SERVICE_NAME`.

Each pod should have a distinct instance identity while sharing the service name. This supports per-replica error analysis while keeping service-level statistics intact.

## 13. Cardinality, Cost, and Data Protection

Resource attributes usually have lower cardinality than per-request values, yet some attributes like `service.instance.id` can vary per pod/rollout. Consider how the backend indexes and stores resource identity.

Do not put into Resource:

- Access tokens, passwords, secrets, or cookies.
- User IDs, emails, phone numbers, or personal data.
- Request IDs or order IDs that change on every execution.
- Request/response bodies.
- Free-form exception messages.

Resource is shared across many records, so accidentally attaching sensitive data can spread widely throughout telemetry. Only include stable operational metadata permitted by security policy.

### 13.1. Resource Cardinality Differs From Metric Cardinality

A resource with a new `service.instance.id` can create additional data groups or series depending on how the backend converts resources into labels. In Prometheus, target instance labels can also increase series counts. Do not multiply unnecessary attributes across every metric.

Fields like `service.name`, `service.namespace`, `service.version`, and environment are typically useful for grouping. Use instance ID only when distinguishing replicas is necessary and the backend can handle that volume of instance metadata.

## 14. Verifying Resource After OTLP Export

Do not stop at confirming environment variables. Inspect payloads across each stage.

### Step 1 — Check Process Environment

Linux:

~~~bash
printenv OTEL_SERVICE_NAME
printenv OTEL_RESOURCE_ATTRIBUTES
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME
$env:OTEL_RESOURCE_ATTRIBUTES
~~~

This check proves the process environment contains the variables. It does not yet prove the SDK read them or the exporter sent them.

### Step 2 — Generate Test Telemetry

Send a request that produces instrumented spans and metrics. Use a stable operation such as `orders.create` to locate it in the backend.

### Step 3 — Inspect Collector Receipt

Use the debug exporter in a test environment or Collector metrics/telemetry to verify Resource attributes upon receipt. If attributes are already missing here, check the application SDK/exporter.

### Step 4 — Inspect After Processors

If the pipeline has a resource/transform processor, observe telemetry after the processor. Compare before and after to confirm there are no unexpected overrides.

### Step 5 — Inspect the Backend

Open the trace or metric and confirm `service.name`, namespace, version, environment, and instance ID. Backends may alter display formatting or normalize keys; cross-check the OTLP payload and mapping rules.

## 15. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Backend shows `unknown_service` | SDK did not receive service name or did not create resource | Check SDK/agent configuration |
| Each pod becomes a separate service | Pod name used as `service.name` | Use shared logical name and separate instance ID |
| `OTEL_SERVICE_NAME` present in shell but resource is wrong | Service process did not inherit env or SDK does not read env | Check environment inside the process/container |
| Traces have right name, metrics have wrong name | Two pipelines have different resource configs | Standardize resource across each pipeline |
| Collector receives right name, backend shows wrong name | Downstream processor/export mapping overwrote it | Check pipeline and backend transformation |
| `service.name` has two values | Environment, code, or Collector conflict | Pick a source of truth and resolve precedence |
| Environment appears as part of service name | Environment concatenated into `service.name` | Use `deployment.environment.name` |
| Version changes fragment the service | Version concatenated into `service.name` | Use separate `service.version` |
| Span has manual `service.name` yet resource lacks it | Attribute attached at the wrong level | Fix Resource configuration |
| Instance ID is missing | Pod/process identity not mapped | Configure `service.instance.id` per runtime |
| Unusually large OTLP payload | Too many resource attributes or long values | Trim fields and bound sizes |
| Secrets present in resource | Credentials or PII placed in environment attributes | Remove, rotate secrets if needed, and check retention |

### Quick Diagnosis Workflow

1. Identify which signal is missing or has the wrong Resource.
2. Check process environment and SDK/agent.
3. Check Resource at the exporter/Collector receiver.
4. Check processors modifying attributes.
5. Check backend mapping and query filters.
6. Compare traces, metrics, and logs per pipeline.
7. Fix only the source causing the discrepancy, then send a test request to verify.

## 16. Real-World Scenario: Inconsistent Resource Identity

**Context:** `order-service` runs four replicas. OTLP traces have `service.name` as `order-service`; Prometheus metrics have `job` as `order-api`; logs record `service=orders`. Dashboards display three separate name groups for the exact same application.

### Step 1 — Map Identity Sources

Record the source producing each name:
- Traces: OTel resource from tracing SDK/agent.
- Metrics: Micrometer registry and Prometheus scrape config.
- Logs: logging pattern or log agent enrichment.

### Step 2 — Choose a Naming Convention

Set logical `service.name` to `order-service`; namespace to `commerce`; version to the image/app version; environment to `production`. Apply this convention to all pipelines that support it.

### Step 3 — Fix Each Source

- Configure tracing Resource so `service.name` is `order-service`.
- Standardize Prometheus job/relabeling so corresponding service labels do not conflict.
- Configure logging enrichment to use the same logical name.
- Keep pod identity in a separate instance label/resource.

### Step 4 — Verify the Data

Send requests to each replica. Inspect `ResourceSpans`, `ResourceMetrics` or Prometheus labels, and log attributes. Confirm unified service names, distinguishable instances, and no per-request IDs as metric labels.

**Desired outcome:** dashboards group the same service together; operators can still filter by version/instance and trace/log by request context.

## 17. Practice Exercises and Self-Check Questions

### Exercise A — Configuring Resource From Environment

Launch an application using the OpenTelemetry Java Agent or SDK autoconfiguration. Set:
- `OTEL_SERVICE_NAME=order-service`
- `OTEL_RESOURCE_ATTRIBUTES` with `service.namespace`, `service.version`, and `deployment.environment.name`.

Send requests, open the trace backend, and verify Resource attributes. Unset the variables in a test environment to observe that specific SDK's defaults.

### Exercise B — Testing Precedence

In an isolated environment, set different `service.name` values in `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, and Spring application name. Verify which source actually affects the resource in your stack. Do not assume Spring properties and OTel environment variables share one universal precedence.

### Exercise C — Collector Processor

Receive OTLP in the Collector and emit debug payloads. Add a `resource` processor to upsert the deployment environment. Compare Resource before/after the processor and explain why the Collector can alter data sent by the application.

### Exercise D — Multi-Replica

Run three replicas with the same `service.name` and different instance IDs. Confirm the backend groups one service while allowing drill-down per pod.

### Exercise E — Multiple Signals

Inspect traces, and OTLP metrics/logs if the application exports those signals; also inspect Prometheus scrape labels. Identify which pipeline creates which resources/labels and whether naming conventions match.

### Self-Check Questions

1. What does Resource describe in OpenTelemetry?
2. How does a Resource attribute differ from a span attribute in scope?
3. How do `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` differ?
4. Why shouldn't you use a pod ID as `service.name`?
5. Does `spring.application.name` always stay in sync with OTel Resource?
6. In which structures does OTLP represent Resource?
7. How does Instrumentation Scope differ from Resource?
8. What can the Collector `resource` processor do with attributes?
9. Why might Prometheus target labels differ from OTLP Resource?
10. When traces have the right name yet metrics have the wrong name, which pipeline should you inspect?
11. Which Resource attributes can increase cardinality?
12. Why shouldn't secrets, PII, or request IDs be put into Resource?
13. How do you determine whether resource is wrong at the SDK, Collector, or backend?
14. Should `service.version` and `deployment.environment.name` be concatenated into `service.name`?
15. How do you keep service identity consistent across traces, metrics, and logs?

**Completion criteria:** explain Resource and the OTLP data model; configure `service.name`, namespace, version, environment, and instance; distinguish `OTEL_SERVICE_NAME` from Spring application name; understand precedence and Collector processors; verify resource per signal; control cardinality and sensitive data.

## 18. Key Takeaways

- Resource describes the service/process emitting telemetry and is attached to OTLP traces, metrics, or logs in the corresponding signal structure.
- `service.name` is the stable logical identifier of the service; replicas of the same service share this name.
- `service.namespace`, `service.version`, `deployment.environment.name`, and `service.instance.id` are separate dimensions.
- `OTEL_SERVICE_NAME` sets `service.name` in OpenTelemetry SDK environment configuration; `OTEL_RESOURCE_ATTRIBUTES` sets additional resource attributes. Verify the SDK/agent actually reads the variables.
- `spring.application.name` belongs to Spring Boot; mapping to OTel Resource depends on integration and should not be assumed automatic.
- Resource differs from span attributes, metric attributes, instrumentation scope, baggage, and MDC.
- Collector processors can enrich or alter resource; manage the source of truth and inspect before/after processors.
- Prometheus scrape labels do not necessarily match OTLP Resource. Verify each pipeline.
- Put only stable, permitted operational metadata into Resource; avoid secrets, PII, and per-request IDs.

## References

- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry Specification — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/)
- [OpenTelemetry Specification — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [OpenTelemetry Protocol — OTLP](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry Collector — Resource Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/resourceprocessor)
- [OpenTelemetry Semantic Conventions — Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
