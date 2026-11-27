# Fixing Wrong `service.name` in Spring Boot Observability

In a multi-service Spring Boot system, the service name is the identifying attribute that groups logs, metrics, and traces under the right application. When this name is wrong or inconsistent, dashboards may split one service into multiple separate services, fragment traces, or merge data from several applications together. Investigation also becomes harder because logs and metrics no longer match the trace being inspected.

This lesson belongs to the **Troubleshooting** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; including context propagation, tags and cardinality, exporters, sampling, and correlating signals to investigate errors, latency, and application behavior in production environments. This content focuses on recognizing, tracing configuration sources, and fixing wrong service names.

## 1. Understanding the Identifying Names

Before changing configuration, distinguish between the application name in Spring Boot and the resource attributes used by the telemetry system.

| Attribute | Meaning | Example |
|---|---|---|
| `spring.application.name` | Logical name of the Spring Boot application, commonly used across application config and integrations | `orders-service` |
| `service.name` | Logical name of the service in the OpenTelemetry Resource; the backend uses it to group spans and telemetry data by service | `orders-service` |
| `service.namespace` | Namespace to distinguish services with the same name across different domains or systems | `commerce` |
| `service.instance.id` | Identifier for a running instance, such as a pod or process | `orders-service-7f9c8d6b5-x2kq4` |
| `deployment.environment.name` | Deployment environment of the service | `production` |

`service.name` describes the **logical application**, so replicas of the same service normally share the same value. Each replica can have its own `service.instance.id`. If you put a pod name, hostname, or request ID into `service.name`, the backend treats each instance as a different service and fragments the data.

`spring.application.name` and `service.name` are closely related, yet you should not assume that every library, exporter, or agent automatically maps these two attributes the same way. Spring Boot, Micrometer, the OpenTelemetry SDK, the Java agent, and the OpenTelemetry Collector can each participate at different configuration stages. Always verify the actual Resource emitted instead of only looking at one line in `application.yml`.

## 2. Symptoms of a Wrong Service Name

Common symptoms include:

- The trace backend displays `unknown_service`, `unknown_service:java`, a default name, or a name that does not match the application name.
- Traces from the same application in local, staging, and production environments unexpectedly appear under different service names.
- A single service shows up as multiple entries in the service list because each pod or deployment version emits a different name.
- Traces from two unrelated applications are grouped under the same service because both share the same name.
- Metric dashboards filtering by an `application` or `service` label find no data, even though the application is emitting metrics.
- Logs have a service field different from `service.name` on the trace, breaking log-to-trace correlation navigation.

Not every case where a metric lacks a `service.name` label is an error. With a Prometheus or Micrometer registry, the application name can be represented by a common tag like `application`; OpenTelemetry, on the other hand, represents `service.name` as a Resource attribute. These two representations belong to two different data models. When investigating, check the attribute name and location in each pipeline.

## 3. Identifying Which Signal Carries the Wrong Name

Take a specific request and cross-check all three signals. Checking the same timestamp and the same instance avoids confusion caused by differences across environments.

### 3.1. Checking Traces

Open a fresh trace generated after the most recent deployment. In the span's Resource or resource attributes section, look for:

```text
service.name
service.namespace
service.instance.id
deployment.environment.name
```

Read `service.name` at the Resource level; do not confuse it with an application-added span attribute. If spans within the same trace have different Resources, inspect SDK initialization or how the processes emit traces. For a simple service, spans created by the same process typically share the same Resource.

### 3.2. Checking Metrics

If the application has Actuator, `/actuator/metrics` allows checking registered meters. With the Prometheus registry, inspect `/actuator/prometheus` and look for the labels the system uses, such as `application`. You can configure the endpoint for inspection in a development environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Expose only the required endpoints and protect them according to the environment's access policy. Do not expose configuration or environment-variable diagnostic endpoints to the public Internet.

If metrics are sent via OTLP, check the metric's Resource attributes in the backend or Collector. Do not conclude that `service.name` is missing simply because a Prometheus series lacks a label of that exact name; the Prometheus registry may be using a different common tag.

### 3.3. Checking Logs

Find a log record emitted by the same request or instance. Check the service identifier field used by the log pipeline, such as `service`, `service_name`, or a field added by the log shipper. Also check `traceId` and `spanId` if correlation is enabled.

Spring Boot can populate trace correlation details into MDC when Micrometer Tracing is configured properly, but that does not automatically guarantee every log format includes a service field. The service name field in logs usually needs to be added by logging configuration, an encoder, or the Collector. Inspect the actual JSON log after it passes through the pipeline, since the shipper may rename or overwrite fields.

## 4. Tracing the Overriding Configuration Source

A wrong service name often comes from multiple coexisting configuration sources. Check in order from application to infrastructure:

1. **Spring Boot configuration:** check `spring.application.name`, `application-{profile}.yml` files, and profile-specific configuration variables currently active.
2. **Spring Boot OpenTelemetry configuration:** if your Spring Boot version supports `management.opentelemetry.resource-attributes`, check the Resource attributes declared there.
3. **OpenTelemetry Java agent or SDK autoconfigure:** check `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, JVM arguments, and agent startup configuration. When using OpenTelemetry SDK autoconfigure, `OTEL_SERVICE_NAME` is the dedicated variable for `service.name` and takes precedence over a `service.name` value inside `OTEL_RESOURCE_ATTRIBUTES`.
4. **Deployment environment:** check Deployments, Helm values, ConfigMaps, Secrets, and environment variables injected into the container by the platform. Make sure staging and production do not accidentally share values or fall back to defaults.
5. **OpenTelemetry Collector or gateway:** check whether any processor adds, renames, or overwrites Resource attributes. The value at the Collector can differ from what the application originally sent.
6. **Observability backend:** check normalization, grouping, or mapping rules in the backend. Some UIs may display a service name transformed from the Resource.

In Spring Boot, Actuator can help inspect loaded configuration via endpoints like `env` or `configprops`, if enabled. Only enable and access these endpoints in protected environments. When reading results, pay attention to the property source and active profiles, not just default values in config files.

## 5. Standardizing Service Names in Spring Boot

Choose one stable logical name for each service, then use that name consistently across pipelines. For example, an order-processing application can use `orders-service` across all environments.

### 5.1. Setting the Application Name

Declare the application name in Spring Boot configuration:

```yaml
spring:
  application:
    name: orders-service
```

This is a readable, reusable central configuration point. Do not put pod names, deployment version tags, or environment names into this value if they alter the service's logical identity.

### 5.2. Configuring the OpenTelemetry Resource

If your Spring Boot version provides `management.opentelemetry.resource-attributes`, you can explicitly declare Resource attributes so the service name is sent with telemetry:

```yaml
spring:
  application:
    name: orders-service

management:
  opentelemetry:
    resource-attributes:
      service.name: ${spring.application.name}
      service.namespace: commerce
      deployment.environment.name: ${APP_ENV:local}
```

Properties and automatic Resource mapping behavior can vary by Spring Boot version and how OpenTelemetry is initialized. Check the documentation for your exact running version. If this property is unsupported in your version, do not leave ineffective configuration sitting idle; use the Resource configuration mechanism supported by the deployed SDK or agent, then verify the result in the trace backend.

### 5.3. Configuring with the OpenTelemetry Java Agent or SDK Autoconfigure

In environments using the OpenTelemetry Java agent or SDK autoconfigure, you can configure via environment variables:

```bash
OTEL_SERVICE_NAME=orders-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment.name=production
```

`OTEL_SERVICE_NAME` is the direct way to set `service.name` in OpenTelemetry setups that support this environment variable. Avoid declaring two different `service.name` values in `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`, because the dedicated variable takes precedence in SDK autoconfigure. If the application relies only on Spring Boot-managed OpenTelemetry configuration without the corresponding agent or SDK autoconfigure enabled, do not assume these variables are read; verify the actual configuration mechanism.

### 5.4. Tagging Micrometer Metrics

For a Prometheus-style registry, you can add a common tag so dashboards identify the application:

```yaml
management:
  metrics:
    tags:
      application: ${spring.application.name}
```

The `application` common tag is a Micrometer metric label. It does not replace OpenTelemetry's `service.name` Resource attribute. If the same application exports metrics through multiple registries, check the actual labels in each registry and align dashboard query conventions.

### 5.5. Aligning the Service Field in Logs

If logs are emitted as JSON, configure the encoder or log shipper to add the service field from the same application name source. Choose a unified field name matching your log system's schema, such as `service.name`, and avoid letting the application, agent, and Collector write different values to the same field.

Inspect the log record after it has passed through the entire pipeline. If the backend uses `service` while traces use `service.name`, configure an explicit mapping at ingestion or query time. Do not assume the two fields are aligned just because they happen to have the same value locally.

## 6. Step-by-Step Remediation Workflow

Apply the following workflow when a wrong service name is detected:

1. **Record current values:** take one trace, one metric, and one log record; note the service name, instance, and environment on each signal.
2. **Choose the canonical name:** agree on one logical name, such as `orders-service`, plus `service.namespace` if business domains need separation.
3. **Find overriding sources:** check Spring profiles, environment variables, JVM args, Java agent, deployment manifests, and Collector processors.
4. **Fix the authoritative source:** pick one primary configuration source for `service.name`; remove or align conflicting values.
5. **Deploy a test instance:** restart the application or roll out one replica to avoid mixing old and new data during verification.
6. **Generate new requests:** do not look only at old traces, because traces retain the Resource recorded when they were created.
7. **Cross-check all three signals:** inspect the trace Resource, metric labels, and log service field. Confirm replicas share the same `service.name` while having distinct `service.instance.id` values.
8. **Check Collector and dashboards:** ensure the pipeline does not overwrite the canonical name and dashboard queries filter by the right field name.

After renaming, historical data may still appear under the old name. This is normal because trace and metric Resources were recorded when the telemetry was emitted. Evaluate the fix using new data generated after the configuration rollout.

## 7. Example: Two Replicas Shown as Two Services

Suppose `orders-service` runs two replicas. A misconfiguration sets the service name from the hostname:

```text
Replica A: service.name = orders-service-7f9c8d6b5-x2kq4
Replica B: service.name = orders-service-7f9c8d6b5-m8n7p
```

The trace backend groups the data into two services. An aggregate latency dashboard for `orders-service` might capture only one replica or have to query both names.

The proper configuration keeps the logical name stable and uses an instance ID for each replica:

```text
Replica A:
  service.name = orders-service
  service.instance.id = orders-service-7f9c8d6b5-x2kq4

Replica B:
  service.name = orders-service
  service.instance.id = orders-service-7f9c8d6b5-m8n7p
```

Then the backend groups traces under one service while still allowing per-instance analysis when tracking down a misbehaving or slow replica.

## 8. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Leaving `spring.application.name` empty | Some integrations fall back to a default or unwanted name | Set an explicit application name and verify the actual Resource |
| Changing only `spring.application.name` while an agent sets its own name | Traces still carry the old or default name | Check `OTEL_SERVICE_NAME`, SDK config, and agent settings |
| Setting `OTEL_SERVICE_NAME` differently from `service.name` in `OTEL_RESOURCE_ATTRIBUTES` | Final value differs from expectation | Align both sources or keep only one naming source |
| Using hostname/pod name as `service.name` | Each replica is grouped as a separate service | Move hostname to `service.instance.id` |
| Multiple applications sharing the same `service.name` | Data from different apps is merged together | Assign unique logical names; use `service.namespace` to partition when appropriate |
| Metrics use label `application` while traces use `service.name` | Dashboard queries may fail to match | Understand each pipeline's schema and standardize query conventions |
| Collector overwrites the Resource attribute | Backend value differs from what the app emitted | Inspect and fix Collector processors or transforms |
| Checking only old traces after fixing | Looks like the new config had no effect | Trigger new requests and inspect telemetry emitted post-deployment |

## 9. Post-Fix Verification Checklist

- [ ] `spring.application.name` has a stable value matching the agreed service name.
- [ ] New trace Resources contain the correct `service.name`.
- [ ] Replicas of the same service share the same `service.name`.
- [ ] `service.instance.id` distinguishes individual instances if the system tracks that attribute.
- [ ] Metrics have the application label appropriate for the registry and dashboard conventions.
- [ ] Log records carry the right service field after passing through the log pipeline.
- [ ] `traceId` and `spanId` are still recorded if logs need to correlate with traces.
- [ ] No environment variable, JVM argument, or Collector processor unexpectedly overrides the name.
- [ ] Dashboards and alerts query using the new name or label.

An accurate service name helps the observability system group data reliably and correlate signals consistently. When an issue occurs, trace the value from Spring Boot configuration through the SDK or agent to the Collector and backend; final confirmation must come from fresh telemetry across logs, metrics, and traces.
