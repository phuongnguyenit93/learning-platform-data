# Correlating Logs with `serviceId`, `instanceId`, and Deployment Region

## 1. Why Do Logs Need Service and Instance Identity?

In a microservices architecture, a single request may traverse a gateway, multiple services, and multiple instances running across different nodes or availability zones. When an error occurs, having only a timestamp and a message is rarely enough to determine which service, which instance, or which deployment region produced the log.

Every log record should carry the identity of the process that emitted it. At a minimum, include:

- `serviceId`: logical name of the service, typically taken from `spring.application.name`.
- `instanceId`: unique identifier of a single running replica within that service.
- `region`: broader deployment region, such as `ap-southeast-1`.
- `zone`: availability zone or smaller failure domain, such as `ap-southeast-1a`.

In Spring Cloud Service Discovery, the registry also stores `serviceId`, `instanceId`, host, port, and metadata. If logs use the same naming convention as the registry, operators can move directly from a log line to the exact instance entry, inspect registration/health status, and identify which zone is experiencing issues.

## 2. Distinguishing serviceId, instanceId, region, and zone

| Field | Example | Scope | Appropriate Source |
|---|---|---|---|
| `serviceId` | `payment-service` | Shared across all instances of a service | `spring.application.name` or registered service name |
| `instanceId` | `payment-service:pod-7f9c` | Specific to each running replica | Pod UID, configured instance ID, or guaranteed-unique hostname/port |
| `region` | `ap-southeast-1` | Broad deployment region | Environment configuration or infrastructure metadata |
| `zone` | `ap-southeast-1a` | Availability zone/failure domain | Scheduler/infrastructure config or node metadata |
| `namespace` | `payments` | Kubernetes resource scope | Kubernetes Pod metadata or runtime configuration |
| `podName` | `payment-service-7f9c8` | Current Pod name | Kubernetes Downward API |
| `environment` | `production` | Deployment environment | Deployment profile/configuration |

`serviceId` and `instanceId` are not interchangeable. Many instances belong to `payment-service`, yet each instance needs its own ID for tracing. Nor are `region` and `zone` the same field: multiple zones can reside within the same region.

Standardize field naming across the entire system. If logs use `serviceId`/`instanceId`, you can map them to corresponding OpenTelemetry Resource Attributes such as `service.name` and `service.instance.id`. In Kubernetes environments, you can add `k8s.namespace.name`, `k8s.pod.name`, and `cloud.region`/`cloud.availability_zone` when those values come from trusted sources.

## 3. Choosing Stable Identity Sources

### 3.1. Service ID

In a Spring Boot application, `spring.application.name` is usually the natural source for the service ID:

```yaml
spring:
  application:
    name: payment-service
```

Use this same value across logs, the registry, and client configuration. Some registries normalize display names—for example, Eureka typically displays app names in uppercase. In logs, pick a stable canonical form (typically the Spring config value) and map the registry's display form when cross-referencing.

### 3.2. Instance ID

`instanceId` must distinguish concurrently running instances. You can use:

- Kubernetes Pod UID if you want an ID unique across the Pod's lifetime.
- Pod name if Pod names are unique within the namespace and your logging system also records `namespace`.
- Hostname plus port if deploying on VMs/bare metal where that pair is unique.
- Platform-assigned ID when registering with Eureka/Consul.

Example configuration via environment variables:

```yaml
app:
  identity:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    region: ${DEPLOYMENT_REGION:local}
    zone: ${DEPLOYMENT_ZONE:local}
    namespace: ${POD_NAMESPACE:default}
    environment: ${DEPLOYMENT_ENV:local}
```

Do not reuse a fixed value like `payment-service-1` across all replicas. If instances share an ID, logs become indistinguishable and registries may overwrite or collide registrations depending on the implementation.

### 3.3. Region and Zone

Region and zone should come from deployment configuration or verifiable infrastructure metadata. Never infer zone from an IP address, random hostname, or Pod name. In Kubernetes, the Downward API can expose Pod name, namespace, UID, Pod IP, and node name; it does not automatically expose every Node label, including `topology.kubernetes.io/zone`.

You can pass the zone into containers via Helm values, a ConfigMap, an admission controller, or a metadata component with permission to read Node labels. If an application queries the Kubernetes API for Node labels, grant minimal RBAC permissions and handle cases where metadata is not yet present. For non-Kubernetes deployments, set region/zone via environment variables or platform configuration.

## 4. Injecting Kubernetes Identity into the Application Environment

The Kubernetes Downward API is a common way to inject Pod metadata as environment variables without calling the Kubernetes API from application code:

```yaml
spec:
  containers:
    - name: payment-service
      env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: INSTANCE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: DEPLOYMENT_REGION
          value: ap-southeast-1
        - name: DEPLOYMENT_ZONE
          value: ap-southeast-1a
        - name: DEPLOYMENT_ENV
          value: production
```

In this example, region/zone are passed from deployment configuration. If replicas can be scheduled across multiple zones, do not hardcode a single static zone for the entire Deployment; inject values according to node/placement or use a topology-aware metadata mechanism.

You can use Pod UID as `instanceId` and Pod name as a display field. Using UID prevents confusion when a new Pod is recreated with a different name or when older logs remain in storage.

## 5. Designing a Consistent Log Schema

A JSON log schema should carry service identity, instance identity, deployment region, and request context:

```json
{
  "timestamp": "2026-11-24T14:30:12.345Z",
  "level": "INFO",
  "message": "Payment request accepted",
  "serviceId": "payment-service",
  "instanceId": "7b6d4e4a-2a31-4d5c-9c8d-1a2b3c4d5e6f",
  "region": "ap-southeast-1",
  "zone": "ap-southeast-1a",
  "namespace": "payments",
  "podName": "payment-service-7f9c8",
  "environment": "production",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "requestId": "req-8f12"
}
```

Conventions:

- `serviceId`, `instanceId`, `region`, `zone`, `namespace`, and `podName` describe where the log originated.
- `traceId` and `spanId` link spans/logs belonging to the same distributed trace.
- `requestId` is an application-level request identifier if the system needs a separate business ID.
- `environment` distinguishes `dev`, `staging`, and `production`.

Do not reuse a single generic field like `service` to sometimes mean the log-producing service and other times mean the target service. Inbound logs should describe the current service; outbound logs should use separately namespaced fields such as `destination.serviceId`, `destination.instanceId`, and `destination.zone`.

## 6. Attaching Identity to MDC in Spring MVC

For Spring MVC applications running on the Servlet stack, you can use a `OncePerRequestFilter` to add instance identity to the SLF4J MDC for all logs within a request:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class ObservabilityIdentityFilter extends OncePerRequestFilter {

    private final String serviceId;
    private final String instanceId;
    private final String region;
    private final String zone;
    private final String namespace;

    public ObservabilityIdentityFilter(
            @Value("${spring.application.name:unknown}") String serviceId,
            @Value("${app.identity.instance-id:unknown}") String instanceId,
            @Value("${app.identity.region:unknown}") String region,
            @Value("${app.identity.zone:unknown}") String zone,
            @Value("${app.identity.namespace:unknown}") String namespace) {
        this.serviceId = serviceId;
        this.instanceId = instanceId;
        this.region = region;
        this.zone = zone;
        this.namespace = namespace;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        MDC.put("serviceId", serviceId);
        MDC.put("instanceId", instanceId);
        MDC.put("region", region);
        MDC.put("zone", zone);
        MDC.put("namespace", namespace);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("serviceId");
            MDC.remove("instanceId");
            MDC.remove("region");
            MDC.remove("zone");
            MDC.remove("namespace");
        }
    }
}
```

The filter reads identity from the process's local configuration, never taking `serviceId` or `instanceId` from caller-supplied headers. Clearing MDC in `finally` is critical because Servlet containers reuse threads; without cleanup, a subsequent request could mistakenly log the previous request's identity.

Example `application.yml`:

```yaml
spring:
  application:
    name: payment-service

app:
  identity:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    region: ${DEPLOYMENT_REGION:unknown}
    zone: ${DEPLOYMENT_ZONE:unknown}
    namespace: ${POD_NAMESPACE:unknown}
```

If you are not using the Servlet stack, do not copy this filter blindly; see the WebFlux and asynchronous context section below.

## 7. Formatting Logs for Easy Collector Querying

### 7.1. Console Pattern with MDC

With Logback, you can include MDC fields in the pattern. If you also want identity to appear in startup logs and background tasks that bypass HTTP filters, read the configuration properties once in `logback-spring.xml` using `springProperty`:

```xml
<configuration>
    <springProperty scope="context" name="serviceId" source="spring.application.name" defaultValue="unknown" />
    <springProperty scope="context" name="instanceId" source="app.identity.instance-id" defaultValue="unknown" />
    <springProperty scope="context" name="region" source="app.identity.region" defaultValue="unknown" />
    <springProperty scope="context" name="zone" source="app.identity.zone" defaultValue="unknown" />

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level serviceId=${serviceId} instanceId=${instanceId} region=${region} zone=${zone} namespace=%X{namespace} traceId=%X{traceId} spanId=%X{spanId} [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Identity fields read from configuration remain constant for the lifetime of the process, so they appear in startup, scheduler, and background worker logs as well. Request/trace fields still come from MDC. If you take this approach, do not also emit duplicate `serviceId`, `instanceId`, `region`, and `zone` from MDC in the same pattern. Another option is putting all identity fields into MDC via the filter shown earlier and letting the encoder read MDC; pick one approach to avoid duplicate fields.

Text patterns are easy to read during development, but log collectors must parse key/value pairs reliably. In production, JSON is usually more convenient because each attribute is an independent field, easy to filter and correlate. With a JSON encoder, configure identity fields as resource/global fields and reserve MDC for per-request context.

### 7.2. JSON Log Example

A JSON log encoder can emit MDC entries as top-level fields:

```json
{
  "timestamp": "2026-11-24T14:30:12.345Z",
  "level": "WARN",
  "logger": "com.example.payment.PaymentService",
  "message": "Inventory service call timed out",
  "serviceId": "payment-service",
  "instanceId": "payment-service-pod-7f9c8",
  "region": "ap-southeast-1",
  "zone": "ap-southeast-1a",
  "namespace": "payments",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7"
}
```

Ensure timestamps follow ISO 8601 with a timezone/UTC offset. Never concatenate all metadata into a single `message` string, as that makes it hard for collectors to filter on individual fields.

## 8. Correlating Logs with Distributed Traces

`serviceId` and `instanceId` answer where a log came from. `traceId` and `spanId` answer which request or operation it belongs to. These two sets of fields complement each other:

- A single `traceId` can traverse multiple services and instances.
- Each service creates its own span, typically with a distinct `spanId`.
- Multiple log lines within the same span can share the same trace/span IDs.
- A single instance handles many different traces over time.

In Spring Boot with Micrometer Tracing, once the appropriate bridge/exporter is configured, trace/span context is automatically placed into MDC for log patterns or JSON encoders to emit. Never overwrite `traceId`/`spanId` with a request ID or instance ID.

Basic tracing sampling configuration example:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

Sampling at `0.1` samples roughly 10% of traces according to the active sampler; tune based on traffic, cost, and diagnostic needs. If you need to retain traces for errors or special requests, use an appropriate sampling policy rather than increasing all logging unboundedly.

If the system receives `traceparent` per W3C Trace Context, instrumentation should handle extracting and propagating the context. For `X-Request-ID`, accept it only under a trust policy: validate length/format, generate a new ID if missing, and never treat arbitrary internet-supplied values as authoritative tags.

## 9. Propagating MDC Across Async and WebFlux

MDC relies on thread-local storage. When a request switches threads via `@Async`, an executor, or callbacks, MDC may not follow automatically. Use a context propagation mechanism suited to your Spring and Micrometer versions.

With Spring Framework supporting `ContextPropagatingTaskDecorator`, you can configure the executor as follows:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
public class AsyncConfiguration {

    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean
    Executor applicationTaskExecutor(TaskDecorator contextPropagatingTaskDecorator) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setTaskDecorator(contextPropagatingTaskDecorator);
        executor.setThreadNamePrefix("app-async-");
        executor.initialize();
        return executor;
    }
}
```

Context propagation must be configured and tested with the tracing/MDC accessors registered in your application. Never manually copy the entire MDC into a thread pool without clearing it afterward; thread pools reuse threads, causing stale context to leak into unrelated tasks.

With Spring WebFlux, requests can hop threads between operators. Do not rely on a Servlet `OncePerRequestFilter` or plain thread-local MDC to preserve context across a reactive chain. Use Reactor Context and Micrometer Context Propagation/automatic context propagation according to your Spring Boot version, then verify logs inside operators running on different schedulers.

## 10. Linking Logs with Registry Metadata

Log identity should match the information published by the discovery provider. You can use the following mechanisms:

| Registry/Platform | Instance Identity Source | Deployment Topology Metadata |
|---|---|---|
| Eureka | `eureka.instance.instance-id`, app name | `eureka.instance.metadata-map` can carry `region`, `zone`, or operational tags |
| Consul | Service ID and service instance ID on registration | Service metadata/tags can carry region, zone, environment |
| Kubernetes | Pod UID/name, namespace, Pod IP | Pod labels/annotations or node topology labels; zone often needs to be injected/read from Node |

Eureka example:

```yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    instance-id: ${INSTANCE_ID:${HOSTNAME:local}}
    metadata-map:
      region: ${DEPLOYMENT_REGION:unknown}
      zone: ${DEPLOYMENT_ZONE:unknown}
      environment: ${DEPLOYMENT_ENV:local}
```

If the application logs `zone=ap-southeast-1a` while the registry records `zone=ap-southeast-1b`, operational tools will draw wrong conclusions during investigations. Use a single source of configuration truth or validate consistency across environment variables, registry metadata, and log resource attributes at startup.

Registry metadata serves discovery/routing; log resource attributes serve observability queries. They may share the same values, but do not assume one automatically updates the other.

## 11. Recording Destination Service in Outbound Logs

When one service calls another, logs should distinguish caller identity from destination identity:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;

public class OutboundCallLogger {

    private static final Logger log =
            LoggerFactory.getLogger(OutboundCallLogger.class);

    public void logSelectedInstance(ServiceInstance target) {
        String destinationZone = target.getMetadata() == null
                ? "unknown"
                : target.getMetadata().getOrDefault("zone", "unknown");

        log.info(
                "Calling dependency destinationServiceId={} destinationInstanceId={} destinationHost={} destinationPort={} destinationZone={}",
                target.getServiceId(),
                target.getInstanceId(),
                target.getHost(),
                target.getPort(),
                destinationZone
        );
    }
}
```

This example shows when code already holds the chosen `ServiceInstance`. When using Spring Cloud LoadBalancer, integrate at an appropriate client/lifecycle layer to log the actually selected instance; never log the entire instance list and assume the first element is the destination. If metadata lacks `zone`, record `unknown` or omit the field rather than guessing from the hostname.

In the log schema, the caller keeps `serviceId`, `instanceId`, `region`, and `zone`; the destination uses `destinationServiceId`, `destinationInstanceId`, `destinationHost`, `destinationPort`, and `destinationZone`. This naming prevents queries from confusing the log producer with the request recipient.

## 12. Querying Logs During Investigations

When logs are emitted as JSON and collectors parse fields separately, you can filter across multiple dimensions:

| Question | Suggested Filter Condition |
|---|---|
| All logs for a service | `serviceId = "payment-service"` |
| Only one failing instance | `serviceId = "payment-service" AND instanceId = "payment-service-pod-7f9c8"` |
| Errors concentrated in one zone | `serviceId = "payment-service" AND zone = "ap-southeast-1a" AND level >= WARN` |
| Comparing two regions | `serviceId = "payment-service" AND region IN ("ap-southeast-1", "ap-southeast-2")` |
| Following one distributed request | `traceId = "4bf92f3577b34da6a3ce929d0e0e4736"` |
| By destination service | `destinationServiceId = "inventory-service" AND level >= WARN` |

Exact syntax depends on Elasticsearch, Loki, OpenSearch, Splunk, or whichever log platform you use. What matters is that fields are parsed as discrete attributes with consistent names across services.

### 12.1. Cardinality and Cost

`instanceId`, `podName`, and `traceId` have large value sets. They are ideal for filtering logs and traces, but should not be turned into metric labels/tags by default. High-cardinality metric labels can sharply increase time series counts, memory consumption, and storage costs.

For metrics, `serviceId`, `region`, `zone`, and `environment` are typically safe if their value sets are bounded. Add `instanceId` only when your backend and system scale allow it. Trace IDs and request IDs should never be metric labels.

## 13. Security and Log Data Quality

- Never log tokens, passwords, cookies, authorization headers, or unnecessary personal data.
- Never let callers dictate a process's `serviceId`, `instanceId`, `region`, or `zone` via request headers.
- Validate `X-Request-ID` if accepted externally; constrain length and character set to prevent log injection.
- Escape newlines and control characters when writing text logs; JSON encoders should serialize messages safely.
- Use `unknown` or omit the field when metadata is absent; never fabricate a placeholder such as a specific zone.
- Synchronize node clocks with NTP/chrony so timestamps are comparable across instances.
- Restrict log read access and retention according to your organization's data policy.

## 14. Implementation Checklist

- [ ] `serviceId` comes from the application name aligned with the registry.
- [ ] `instanceId` is unique among concurrently running instances.
- [ ] `region`, `zone`, `namespace`, and `environment` have explicit configuration sources.
- [ ] On Kubernetes, inject Pod UID/name/namespace via the Downward API; do not assume the Downward API automatically reads node zone labels.
- [ ] Identity fields are attached to MDC or logging resource context.
- [ ] MDC is cleared in `finally` inside Servlet filters.
- [ ] JSON logging is configured so collectors parse discrete fields.
- [ ] `traceId`/`spanId` remain managed by tracing instrumentation.
- [ ] Context propagation is verified for `@Async`, executors, and WebFlux.
- [ ] Identity is aligned across logs, Eureka/Consul metadata, and Kubernetes labels.
- [ ] Outbound logs distinguish caller identity from `destination*` fields.
- [ ] `instanceId` and `traceId` are not used as metric labels if they cause high cardinality.
- [ ] No secrets or sensitive data are written to logs or metadata.

## 15. Conclusion

To correlate logs with service discovery, each log record should carry stable identifiers for the producing service (`serviceId`), specific instance (`instanceId`), and deployment location (`region`, `zone`). In Spring Boot, take `serviceId` from `spring.application.name`, take `instanceId` and topology from config/runtime, and attach them to MDC or logging resource context so all logs share one schema.

Keep `traceId`/`spanId` separate for cross-service request correlation, distinguish caller from destination in outbound logs, propagate context properly across async/WebFlux boundaries, and keep values synchronized with registry metadata. With well-structured logs, operations teams can filter errors by service, instance, zone, or trace without guessing from hostnames or message strings.

## References

- [Spring Boot – Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Framework – Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [OpenTelemetry – Service Resource Attributes](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [Kubernetes – Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/)
- [Kubernetes – Well-known Labels, Annotations and Taints](https://kubernetes.io/docs/reference/labels-annotations-taints/)
