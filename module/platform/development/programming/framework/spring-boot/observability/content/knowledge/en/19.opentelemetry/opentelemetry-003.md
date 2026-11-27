# OpenTelemetry Resource

When a Spring Boot system runs dozens of instances across multiple environments, both traces and metrics must answer: **which service, which version, which instance, and where was this telemetry emitted?** If every span had to repeat the service name, hostname, and deployment environment on its own, data would easily become inconsistent. OpenTelemetry solves this with **Resource**: a set of attributes describing the entity emitting telemetry.

This lesson **OpenTelemetry Resource** belongs to the **OpenTelemetry** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments.

> **Key idea:** Resource describes **the telemetry source** (e.g., service and instance); Span attributes describe **a specific operation**; metric attributes group **a metric series**; instrumentation scope describes **the library creating telemetry**. Choosing the right layer keeps service identity consistent across traces, metrics, and logs while avoiding repeating metadata on every span.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain what Resource is in OpenTelemetry and why it matters in multi-service/multi-instance systems.
2. Distinguish Resource attributes, Span attributes, metric attributes, and Instrumentation Scope.
3. Recognize common service attributes such as `service.name`, `service.namespace`, `service.version`, and `service.instance.id`.
4. Choose deployment, host, container, and process attributes suited to your observation goals.
5. Configure resource identity in Spring Boot and understand the roles of `spring.application.name`, `OTEL_SERVICE_NAME`, and `OTEL_RESOURCE_ATTRIBUTES`.
6. Understand how resource attributes merge and precedence rules when the same key appears in multiple sources.
7. Know when resource attributes have appropriate cardinality and when to avoid unstable identifiers.
8. Verify Resource across traces, metrics, logs, and the Collector pipeline.
9. Avoid service identity mistakes that fragment dashboards or merge unrelated applications.
10. Use Resource to correlate signals during incident investigation.

## 2. Resource in the OpenTelemetry Model

OpenTelemetry defines Resource as an immutable representation of the observed entity, expressed as Attributes. For example, a process running inside a container on Kubernetes can be described by service name, pod/container identity, hostname, OS, and process information. Resource is detected/configured independently of the exporter; the exporter receives telemetry along with its Resource instead of guessing service identity.

~~~mermaid
flowchart TD
    A["Observed entity<br/>Spring Boot service instance"] --> B["Resource"]
    B --> C["service.name"]
    B --> D["service.namespace / version"]
    B --> E["service.instance.id"]
    B --> F["deployment / host / container / process"]
    G["Instrumentation library"] --> H["Instrumentation Scope"]
    B --> I["Telemetry"]
    H --> I
    I --> J["Spans / Metrics / Logs"]
    J --> K["Exporter"]
    K --> L["Collector / observability backend"]
~~~

Resource is typically bound to its corresponding providers when the SDK/provider is created. For instance, a `TracerProvider` holds a Resource identifying the application creating spans. Metrics and logs SDKs/providers also hold Resources. The exporter can serialize Resource as resource attributes or place it in protocol metadata.

### 2.1 Which Entity Does a Resource Represent?

A practical rule of thumb:

- All instances of the same logical service share the same `service.name`.
- Each running instance needs to be operationally distinguished with an appropriate `service.instance.id`.
- Services can be grouped into a namespace or domain via `service.namespace`.
- Releases are described with `service.version` when reliable build metadata is available.
- Deployment location such as `deployment.environment.name`, `cloud.region`, `k8s.namespace.name`, or `container.id` adds context about where the service runs.

Do not assign a different `service.name` per pod/replica. If each replica claims its own `service.name`, dashboards will fragment one logical service into many separate services.

### 2.2 Resource Is Immutable

Resource is designed to be immutable once the provider is created. This ensures every span/metric/log emitted by that provider receives the same service identity throughout its lifecycle. If deployment version or instance identity changes, that is normally a new process/instance with a new Resource rather than updating Resource per request.

## 3. Resource Attributes vs. Other Metadata Layers

| Metadata Type | Question Answered | Example | Scope |
|---|---|---|---|
| **Resource attributes** | Who emitted the telemetry? | `service.name=order-service`, `deployment.environment.name=production` | Telemetry-emitting entity |
| **Instrumentation Scope** | Which library/instrumentation created the telemetry? | `scope name=io.micrometer`, `version=...` | Groups telemetry by instrumenter |
| **Span attributes** | What operation is the span performing? | `http.request.method=POST`, `db.system.name=postgresql` | Single span |
| **Span events** | What happened during the span? | `retry scheduled`, `exception event` | Point in time within a span |
| **Metric attributes** | Along which dimensions should the metric series be grouped? | `route=/orders/{id}`, `status=500` | Metric data point / time series |
| **Log attributes** | What details does the log record hold? | `message`, `severity`, `trace_id`, `span_id` | Single log record |

Example for an order request:

~~~text
Resource:
  service.name = order-service
  service.version = 2.4.1
  deployment.environment.name = production

Instrumentation scope:
  name = io.micrometer.observation
  version = ...

Span:
  name = POST /orders
  attributes:
    http.request.method = POST
    http.response.status_code = 201

Metric:
  name = http.server.request.duration
  attributes:
    http.request.method = POST
    http.route = /orders
    http.response.status_code = 201
~~~

`service.name` is not a per-request span attribute; it identifies the emitter. `http.route` describes the request/operation, not service identity. Do not mix the two layers when designing queries or filters.

### 3.1 Resource Differs from Instrumentation Scope

One service can use multiple instrumentation libraries: Spring MVC instrumentation, Micrometer Observation, JDBC instrumentation, or a client library. The Resource can be identical because all telemetry is emitted by the same service instance; Instrumentation Scope differs to indicate which library produced that telemetry.

When a backend displays a trace, you may see the same Resource across spans with different scope names. This is not the service renaming itself; it represents different instrumentation sources inside the same process.

## 4. Key Service Resource Attributes

OpenTelemetry Semantic Conventions define keys and meanings for resource attributes so backends interpret them consistently.

| Attribute | Meaning | Example | Guidance |
|---|---|---|---|
| `service.name` | Logical name of the service | `order-service` | Stable across replicas |
| `service.namespace` | Namespace grouping services | `commerce` | Separates domains/organizations |
| `service.version` | Service version | `2.4.1` or git SHA | Reflects artifact/build |
| `service.instance.id` | Identifier for a specific instance | UUID/pod identity | Distinguishes concurrent replicas |
| `deployment.environment.name` | Deployment environment | `production`, `staging`, `development`, `test` | Use well-known values when applicable |
| `service.language.name` | Implementation language | `java` | Usually set by SDK/resource provider |

### 4.1 `service.name` Must Be Stable Across Replicas

Example of three pods running Order Service:

~~~text
service.name = order-service
service.instance.id = pod-7f9a
service.instance.id = pod-8c21
service.instance.id = pod-2b40
~~~

The three instances share `service.name`, but have different instance IDs. To query the whole service, filter by `service.name`. To isolate a specific failing replica, add `service.instance.id` or Kubernetes pod attributes if collected.

Do not embed pod names or container IDs into `service.name`, as every scale event or rollout will create a new service identity.

### 4.2 `service.version` Should Reflect the Running Build

A version can be a semantic version, release tag, or commit SHA. What matters is that the value maps to the actual deployed artifact. Do not use a generic placeholder that cannot distinguish builds; during rollouts, dashboards and traces need to compare the two version groups.

If using Spring Boot build-info, the corresponding resource provider may extract build name/version from `build-info.properties` depending on the integration. If configured manually, ensure the build pipeline injects the accurate version at runtime.

### 4.3 `service.instance.id` Must Distinguish Instances

`service.instance.id` should be unique per instance of the same service namespace/name within the scope that needs differentiation. It can come from a pod UID, instance UUID, or platform-assigned identifier. Avoid using a shared hostname across containers if hostnames are not unique; also consider stability across process restarts.

### 4.4 `deployment.environment.name`

Current Semantic Conventions use the key `deployment.environment.name`; well-known values include `development`, `production`, `staging`, and `test`. Custom environments may use their own values if no well-known value applies. This attribute classifies the environment; it does not alter service identity uniqueness rules.

Do not confuse the legacy key `deployment.environment` in older docs/configs with the current semantic convention. When upgrading, check the schema/version and Collector/backend mappings before changing queries.

## 5. Infrastructure Resource Attributes

Beyond service identity, Resource can hold information about where the process runs. Enable only detectors/attributes that are genuinely useful and comply with data policies.

| Group | Example Attributes | Used For |
|---|---|---|
| Host | `host.name`, `host.arch`, `host.id` | Identifying machine/VM |
| Operating system | `os.type`, `os.description`, `os.version` | Distinguishing runtime OS |
| Process | `process.pid`, `process.executable.name`, `process.command_line` | Process troubleshooting |
| Process runtime | `process.runtime.name`, `process.runtime.version` | Tracking Java runtime |
| Container | `container.id`, `container.image.name`, `container.image.tag` | Container/deployment investigation |
| Kubernetes | `k8s.namespace.name`, `k8s.pod.name`, `k8s.deployment.name` | Grouping by workload |
| Cloud | `cloud.provider`, `cloud.region`, `cloud.availability_zone` | Region/infra analysis |

Some attributes can introduce significant cardinality when placed into metrics. For instance, `process.pid` changes on every restart; pod names change on rollouts. They are useful on trace/log resources or instance analysis, but should not necessarily be added to every metric series.

### 5.1 Auto-Detection Is Not Always Sufficient

SDKs/resource providers can detect host, OS, process, container, or service identity. However:

- Detectors depend on the SDK, runtime, permissions, and environment.
- Some detectors are disabled by default or exist only in a specific distro/agent.
- Kubernetes metadata may require deployment platform or Collector enrichment.
- Container image digest/tag is not always automatically obtainable.
- Running locally may produce different resource attributes than production.

Verify the actual Resource emitted rather than relying solely on the expected list of detectors.

## 6. Configuring Resource in Spring Boot

Spring Boot can construct a Resource for OpenTelemetry integration based on supported properties and environment variables. First, give the application a clear name:

~~~yaml
spring:
  application:
    name: order-service
~~~

Spring Boot OpenTelemetry auto-configuration can use `spring.application.name` as the default value for `service.name` if no higher-precedence value is provided. A clear name is far better than having the backend show `unknown_service:java`.

### 6.1 Configuring Service Metadata

Illustrative example of declaring resource attributes in an integration that supports it:

~~~yaml
otel:
  resource:
    attributes:
      service:
        namespace: commerce
        version: 2.4.1
      deployment:
        environment:
          name: production
~~~

Property structure depends on the integration. The OpenTelemetry Spring Boot Starter supports its own SDK configuration schema; Spring Boot Actuator's built-in OpenTelemetry auto-configuration has its own property group. Do not copy the starter's YAML into Actuator config and assume identical binding. Verify against the configuration metadata of the dependency you are using.

A common way to configure the OpenTelemetry SDK is via environment variables:

~~~bash
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
~~~

Values in `OTEL_RESOURCE_ATTRIBUTES` are comma-separated `key=value` pairs. Commas and equals signs inside keys/values must be percent-encoded per OTel rules. Do not arbitrarily append a value containing a comma because parsers may interpret it as a separate member.

### 6.2 Notes on Spring Boot Auto-Configuration

Current Spring Boot reference documentation distinguishes the Resource environment variables it supports, including `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME`. Do not assume every OpenTelemetry SDK autoconfigure environment variable takes effect when using Spring Boot's built-in OpenTelemetry auto-configuration. If you need the full SDK autoconfigure mechanism or other resource providers, follow the appropriate Spring Boot guidance and understand that providing your own `OpenTelemetry` bean can disable Boot's auto-configuration, affecting built-in observability features.

### 6.3 Identifying Which Integration Is Used

There are at least two easily confused integration styles:

- **Spring Boot Actuator + Micrometer Tracing/OpenTelemetry bridge:** Resource belongs to the tracing/metrics provider managed by Spring Boot. Use Spring Boot properties and version-matched bridge/exporter dependencies.
- **OpenTelemetry Spring Boot Starter or Java agent/autoconfigure:** Has its own schema/properties such as `otel.resource.attributes` and resource provider detectors. Do not copy starter YAML directly into Actuator configuration assuming Spring Boot binds them identically.

Before applying changes, identify which integration the app uses, which providers are created, and who owns Resource configuration.

## 7. Precedence and Merging Resource Attributes

The same resource key can originate from multiple sources: SDK defaults, environment variables, resource detectors, Spring properties, or a user-provided `Resource`. Without understanding precedence, a service can end up with the wrong name or version.

According to the OpenTelemetry Resource SDK specification, `OTEL_RESOURCE_ATTRIBUTES` is merged with a user-provided resource as a secondary resource; the user-provided `Resource` takes higher precedence on key conflicts. With Spring Boot OpenTelemetry auto-configuration, user-configured resource attributes are also applied after environment settings and can override environment values; Spring Boot additionally supplies a default `service.name` from `spring.application.name` if none is set.

| Example Source | `service.name` Value | Meaning |
|---|---|---|
| Runtime default | `unknown_service:java` | Fallback when no other name is given |
| `spring.application.name` | `order-service` | Default name from Spring configuration |
| `OTEL_SERVICE_NAME` | `checkout-api` | Service name from OTel env |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.name=legacy-api` | Resource attribute from env list |
| User-provided Spring/Resource attribute | `service.name=order-service-v2` | Can take precedence over env sources depending on integration |

This table shows possible participating sources, not a single universal precedence order across every Spring Boot major version or integration. Follow the precedence documented for your exact Spring Boot/OpenTelemetry integration. Always inspect the actual Resource at runtime.

### 7.1 `service.name` and `OTEL_SERVICE_NAME`

OpenTelemetry SDK conventions designate `OTEL_SERVICE_NAME` as the dedicated way to set the service name; it has higher precedence than `service.name` supplied via `OTEL_RESOURCE_ATTRIBUTES` in standard SDK autoconfigure. However, Spring Boot has its own resource merging/binding behavior. When using built-in OpenTelemetry auto-configuration, follow current Spring Boot documentation and test when multiple sources are present; do not mix Java agent precedence with Spring Boot starter precedence.

### 7.2 Do Not Set the Same Key in Too Many Places

If `service.name` is set in YAML, environment variables, and deployment manifests simultaneously, it is hard to tell which value wins. Pick one authoritative source per concern:

- `spring.application.name` or application config for logical identity.
- Deployment environment variables for environment-specific values.
- Build metadata for `service.version`.
- Platform metadata/detectors for instance/container/host identity.

Document which source owns each key in your deployment process and verify after rollout.

## 8. How Is Resource Attached to Telemetry?

A Resource can be bound to a provider and shared across multiple signals. In the OpenTelemetry data model, every Span/Metric/Log Record is associated with its Resource or grouped under the Resource in the export format.

~~~mermaid
flowchart TD
    R["Resource<br/>service.name=order-service<br/>service.version=2.4.1"]
    R --> T["TracerProvider"]
    R --> M["MeterProvider"]
    R --> L["LoggerProvider"]
    T --> S["Spans"]
    M --> D["Metric data"]
    L --> G["Log records"]
    S --> E["OTLP Export"]
    D --> E
    G --> E
    E --> C["Collector"]
    C --> B["Backend"]
~~~

An OTLP exporter can send different signal types over separate pipelines. The Collector can receive resource attributes, enrich them with Kubernetes or cloud metadata, filter/transform attributes, and forward them to backends.

### 8.1 Resource and Instrumentation Scope in Export

OTLP represents Resource separately from the list of spans or metric data belonging to that Resource. Some backends flatten resource fields onto the record view, while others store them as separate metadata. Instrumentation Scope is described separately to identify the library generating the telemetry.

Do not assume every backend displays Resource identically. Semantic convention attribute meanings must still remain consistent.

### 8.2 Metric Resources Affect Time Series Identity

When an exporter converts Resource attributes into labels, they can participate in distinguishing series. `service.name` and environment help group metrics by the right service. However, `service.instance.id`, pod, container, or version can multiply series counts. Consider your backend and query model before enabling every resource detector for metrics.

## 9. Resource in Spring Boot/Micrometer and OpenTelemetry

Spring Boot commonly uses Micrometer Observation as a unified instrumentation layer. When metrics or tracing handlers generate telemetry, the associated registry/provider attaches metadata according to what the implementation supports.

Important distinctions:

- **Micrometer common tags** such as `management.metrics.tags.application`: tags attached to meters/metric registries, not automatically OpenTelemetry Resource attributes.
- **OpenTelemetry Resource attributes:** identify the telemetry provider/entity, configured on the OTel SDK/provider.
- **MDC fields:** log data scoped to execution; not automatically a Resource.
- **Observation low-cardinality key-values:** metadata on an observation that handlers propagate to corresponding signals; do not automatically become Resource.

Example of common metrics tags:

~~~yaml
management:
  metrics:
    tags:
      application: order-service
      environment: production
~~~

This configuration attaches common tags to Micrometer metrics in Spring Boot; it should not be treated as the sole way to configure OTel Resource. If you need resource identity in traces or OTLP logs, configure the OTel resource through your integration's supported mechanism.

### 9.1 Why Can `service.name` Differ Between Traces and Metrics?

Possible reasons:

- OTel Resource reads `service.name` from one source, while the Micrometer common tag `application` reads from another.
- The application uses two separate registries/providers.
- The Collector transforms/renames resource attributes.
- The backend maps service identity using its own logic.
- Services have inconsistent configs or are mid-rollout.

Pick one canonical service name and map it consistently. Never change `service.name` per span or route.

## 10. Resource Identity and Cardinality

Resource attributes help distinguish services/instances, yet some keys carry many values. Cardinality impact depends on the signal and backend: a resource attribute may create distinct Resource groups for traces/logs; if flattened into metric labels, it can increase time series count.

| Attribute | Typical Cardinality | Recommendation |
|---|---|---|
| `service.name` | Low/moderate, per service | Should be present |
| `service.namespace` | Low | Useful for multi-domain organizations |
| `service.version` | Per active build | Useful for rollouts; manage retention |
| `deployment.environment.name` | Low | Use standardized values |
| `service.instance.id` | Per instance | Useful, though may increase metric series |
| `host.name` | Per host | Enable only if needed |
| `container.id` | High, changes per container | Consider signal/backend impact |
| `process.pid` | High and volatile | Helpful for debugging, not a default label on every dashboard |
| `request.id` / `trace.id` | Nearly unique per request | Do not add as a Resource attribute |
| `user.id` / `order.id` | Very high and potentially sensitive | Do not use as Resource |

Do not put request, span, order, or user IDs into Resource because Resource describes the telemetry-emitting entity, not individual requests. If `service.instance.id` changes on every request, you are using the wrong metadata layer.

### 10.1 Versions Can Create Multiple Resource Groups During Rollouts

During a rolling deployment, versions `2.4.0` and `2.4.1` may coexist temporarily. This is expected: the backend can distinguish the two versions to check whether errors began only after the rollout. Once the rollout completes, Resource groups stabilize around the active version.

Do not change `service.name` per release; use `service.version` to track releases.

## 11. Resource in Kubernetes

In Kubernetes, Resource can carry service identity alongside namespace/pod/container metadata. Example:

~~~text
service.namespace = commerce
service.name = order-service
service.version = 2.4.1
service.instance.id = 7f9a... (pod UID)
deployment.environment.name = production
k8s.namespace.name = commerce-prod
k8s.pod.name = order-service-7f9a
k8s.deployment.name = order-service
container.id = container runtime identifier
~~~

Some attributes are detected by the SDK/Collector, while others require a Kubernetes resource detector or Collector processor. Only enable detectors when the environment supplies the information and policy permits it.

### 11.1 Resource Detection in the App or the Collector?

Resource enrichment can happen in two places:

- **Application SDK:** knows process/runtime/service and some host/container data directly; convenient when exporters send telemetry straight to backends.
- **Collector:** can add Kubernetes attributes using pod IP, connection metadata, or platform APIs; centralizes configuration and avoids integrating detectors in every service.

Do not enrich the same key from two conflicting sources. Define clear precedence/override policies in the Collector and verify the post-processor output.

### 11.2 Do Not Expose Sensitive Infrastructure Metadata

Process command lines, host IDs, cloud account IDs, container image paths, or internal topology can reveal infrastructure details. Collect only necessary keys, restrict who can query the backend, and apply appropriate retention.

## 12. Verifying Resource After Running Spring Boot

Do not just read `application.yml`; inspect the telemetry actually exported.

### 12.1 Via OpenTelemetry Collector/OTLP Backend

When using OTLP, open a span or log resource in the backend and verify the keys:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = staging
service.instance.id = ...
~~~

If `service.name` is missing, check `spring.application.name`, `OTEL_SERVICE_NAME`, resource attributes, and OTel provider auto-configuration. If the value differs from expectations, inspect override sources and Collector processors.

### 12.2 Via Debug Exporter Locally

You can use a debug exporter or print the Resource from the SDK in tests. With the OpenTelemetry Java API, the idea is to inspect the Resource attached to the signal's provider/SDK. Exact APIs depend on the provider/SDK version; avoid casting a Spring Boot auto-configured bean to a specific implementation without confirming its actual type.

Illustrative pseudocode:

~~~java
// Pseudocode: retrieve Resource from the active provider/SDK.
// Exact API depends on the OpenTelemetry SDK/provider type.
Resource resource = configuredTracerProvider.getResource();
System.out.println(resource.getAttributes());
~~~

This is pseudocode, not a snippet guaranteed to copy-paste and run on every Spring Boot setup. In production, prefer inspecting Resource on exported telemetry to validate both merging and the Collector pipeline.

### 12.3 Checking `OTEL_RESOURCE_ATTRIBUTES`

Example:

~~~bash
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging"
~~~

If values contain special characters such as commas or equals signs, percent-encode them per the OTel environment variable format. Since shells and container platforms handle quotes differently, inspect the actual environment inside the running process rather than only checking manifests.

## 13. Combining Resource with Metrics, Logs, and Traces

Resource serves as the shared service identity link across signals. When querying, you can start with `service.name` and deployment environment, then pivot into the corresponding datasets.

~~~mermaid
flowchart LR
    R["Resource<br/>service.name=order-service"] --> M["Metrics<br/>request rate / latency / errors"]
    R --> T["Traces<br/>server/client spans"]
    R --> L["Logs<br/>application events"]
    M --> Q["Detect degraded service"]
    T --> Q2["Isolate span/dependency"]
    L --> Q3["Read exception/context"]
    Q --> Q4["Correlation by service/resource"]
    Q2 --> Q4
    Q3 --> Q4
~~~

Investigation example:

1. A dashboard filtered by `service.name=order-service` and `deployment.environment.name=production` shows rising HTTP p95 latency.
2. The trace backend filters by the same Resource to identify the version/instance exhibiting slow DB spans.
3. Logs sharing the same service identity show timeouts and trace correlation.
4. Comparing old vs. new `service.version` confirms errors appeared only after the rollout.
5. Inspecting `service.instance.id` checks whether the problem is isolated to a single replica.

Trace ID links a single request; Resource links telemetry by emitting entity. Do not substitute Trace ID with `service.name` or vice versa.

## 14. Common Resource Configuration Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Backend shows `unknown_service:java` | Missing `service.name` or Spring application name | Set `spring.application.name`/`OTEL_SERVICE_NAME` and check integration |
| Each pod appears as a separate service | `service.name` takes pod name/instance ID | Use shared logical name; move pod ID to `service.instance.id` or `k8s.pod.name` |
| Traces and metrics show different service names | OTel Resource and Micrometer common tags configured differently | Align canonical service identity and check Collector mappings |
| `service.version` is empty | Build-info not generated or resource not configured | Attach reliable build metadata |
| Unexpected surge of Resource groups | Changing instance/version/host attributes or misconfigured detector | Audit each attribute per signal |
| Inconsistent deployment environment | Mixing legacy/new keys or free-form values | Standardize `deployment.environment.name` |
| Resource attributes do not override as expected | Misunderstood precedence across Boot, SDK, and env | Check integration/version and test conflicting key sources |
| `OTEL_RESOURCE_ATTRIBUTES` has no effect | Spring Boot auto-config supports limited vars or syntax error | Check Boot reference, process env, and encoding |
| `service.name` appears in logs but not traces | Log MDC/common fields are not OTel Resource | Check OTel provider Resource and exporter |
| Collector alters or drops keys | Processor/filter/transform configuration | Inspect each pipeline processor |
| Metrics time series spike sharply | High-cardinality Resource attributes flattened into labels | Trim labels and select attributes per signal |
| Same `service.instance.id` across replicas | Hard-coded value shared by all instances | Use per-instance pod UID or instance UUID |
| `service.name` changes every release | Embedding version inside `service.name` | Keep `service.name` stable; put release in `service.version` |

## 15. Playbook: Wrong Service Identity After Deployment

**Scenario:** Before rollout, dashboards showed `order-service`; after rollout, `unknown_service:java` appeared and data split apart.

1. **Check application config:** Is `spring.application.name` still set?
2. **Check process environment:** Were `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` injected into the container?
3. **Identify integration:** Is it Spring Boot built-in auto-configuration, OpenTelemetry Spring Boot Starter, or Java agent?
4. **Check precedence:** Are user resource attributes/SDK configs overriding it, or is a resource provider inactive?
5. **Check Collector:** Does any processor transform/override `service.name` or split the pipeline?
6. **Compare signals:** Do traces, metrics, and logs share the same canonical service identity?
7. **Check instances:** Is `service.instance.id` distinct across replicas while `service.name` stays identical?
8. **Fix and verify:** Emit fresh telemetry and verify the Resource at the exporter/backend before modifying dashboards or alerts.

Never modify dashboards to accommodate a broken service identity when the root cause lies in Resource configuration.

## 16. Self-Check Exercises

**Exercise 1 — Metadata classification.** For a `POST /orders` request, classify `service.name`, `service.version`, `host.name`, `http.request.method`, `spanId`, and status code into Resource, `SpanContext`, or Span/metric attributes. Explain why.

**Exercise 2 — Replica identity.** Four pods run the same Order Service. How should `service.name` and `service.instance.id` relate? Why shouldn't you put the pod name into `service.name`?

**Exercise 3 — Version rollout.** A rollout runs versions `2.4.0` and `2.4.1` concurrently. Should you change `service.name` or `service.version`? What happens if each version uses a different `service.name`?

**Exercise 4 — Property precedence.** `spring.application.name` is `order-service`, `OTEL_SERVICE_NAME` is `order-api`, and a user-provided Resource sets `service.name=checkout`. Describe how to verify the final value for your exact Spring Boot/OpenTelemetry integration; why can't you assume Java agent precedence applies to every Boot setup?

**Exercise 5 — Cardinality.** There are 100 pods, each emitting 20 metrics. If `service.instance.id` is flattened into a metric label, along which dimension can series count grow? When is this value still useful?

**Exercise 6 — Spring metrics tags.** Does setting `management.metrics.tags.application=order-service` automatically create OpenTelemetry Resource `service.name`? Explain the difference between Micrometer common tags and OTel Resource.

**Exercise 7 — Collector enrichment.** When should `k8s.pod.name` be detected at the Collector rather than inside each app? What must be checked if both the app and the Collector set `service.instance.id`?

**Exercise 8 — Investigating wrong service name.** The trace backend displays `unknown_service:java`, while the log backend logs `order-service`. Outline an inspection order from Spring application name, OTel configuration, and exporter to the Collector.

### Suggested Answers

1. `service.name`/`version`/`host` belong to Resource; `spanId` belongs to `SpanContext`; method/status belong to span or metric data point attributes per instrumentation.
2. `service.name` is identical across all four pods; `service.instance.id` differs. `service.name` identifies the logical service, while instance ID differentiates replicas.
3. Keep `service.name`, update `service.version`. Changing `service.name` per release splits the service into separate groups on dashboards.
4. Check the specific version and integration, user-provided/env/default sources, then verify the actual exported Resource. Spring Boot has its own merge behavior, so Java agent precedence cannot be treated as a universal rule.
5. Series count can multiply by pod count × other metric dimensions; useful for instance-level troubleshooting, though cost must be balanced.
6. No. Those are Micrometer common tags; OTel Resource is configured on the corresponding provider/integration.
7. The Collector fits when you want centralized Kubernetes metadata without each service needing platform API access; ensure two conflicting sources do not write the same key.
8. Inspect application config/environment, SDK/provider, Resource merging, exporter, Collector processors, and separate log/trace pipelines.

## 17. Official References

- [OpenTelemetry Specification — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/): defines immutable Resource, attaching Resource to telemetry, and merging environment attributes.
- [OpenTelemetry Semantic Conventions — Resources](https://opentelemetry.io/docs/specs/semconv/resource/): service/host/container/deployment resource attributes.
- [OpenTelemetry — SDK Configuration for Java](https://opentelemetry.io/docs/languages/java/configuration/): `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, and resource providers.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Resource in OpenTelemetry, environment variables supported by Spring Boot, and auto-configuration.
- [OpenTelemetry Spring Boot Starter — SDK Configuration](https://opentelemetry.io/docs/zero-code/java/spring-boot-starter/sdk-configuration/): starter resource attributes, resource detectors, and service name precedence.
- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/): how Resource describes the telemetry-emitting entity.
- [OpenTelemetry Protocol — Common](https://opentelemetry.io/docs/specs/otlp/): Resource and telemetry structure in OTLP.
- [OpenTelemetry Semantic Conventions — Deployment](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/): `deployment.environment.name` and well-known values.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation and metrics/tracing integration in Spring.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): distinguishing Micrometer metrics and common tags in Spring Boot.

**Key takeaway:** Resource answers **"which entity emitted this telemetry?"**. Keep `service.name` stable across replicas; use `service.instance.id` to distinguish instances, `service.version` to identify releases, and `deployment.environment.name` to group environments. Do not confuse Resource with span attributes, MDC, or Micrometer common tags. In Spring Boot, determine the exact integration and precedence of resource configuration, then inspect the Resource on exported telemetry; getting this right from the start gives metrics, logs, and traces a unified service identity for cross-signal incident investigation.
