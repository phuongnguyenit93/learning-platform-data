# Reading Contextual Logs for Auto-Configuration, Registration, and Reconnection

Service discovery performs many activities before the first business request is ever processed: the application reads configuration, builds instance identity, connects to the registry, registers the service, sends heartbeats or health checks, fetches the instance list, and reconnects after network interruptions. When a step fails, a log line merely saying `Connection refused` is rarely enough to tell which service was affected, which registry was targeted, which retry attempt the application is on, or what configuration was loaded.

Contextual logs connect those activities into an investigable lifecycle. Each event should carry the service name, instance ID, environment, provider, operation, before/after state, duration, and appropriate error details. This article explains how to design structured logs for auto-configuration, registration, and reconnection in Spring Cloud Service Discovery, while highlighting sensitive data to protect and ways to avoid log noise.

## 1. Why Do Discovery Logs Need Context?

A microservice can run across many replicas, multiple environments, and multiple registry endpoints. If logs only record:

```text
Registered successfully
Retrying connection
Configuration loaded
```

then operators still do not know:

- Which service registered? Which instance ID?
- Which environment, region, or zone is the instance running in?
- Is it connecting to Eureka, Consul, or ZooKeeper? Which registry target?
- Was configuration loaded from files, environment variables, or Config Server/KV?
- Is this the initial registration or a re-registration after session expiration?
- Which retry attempt is this, how long has it waited, and is the error retryable?
- Did reconnection restore the cache/registration, or did it only reopen a socket?

Useful logs must answer these questions without dumping entire configuration objects or sensitive payloads.

## 2. A Unified Log Schema

Standardize a common field set across all services in the system. Field names can follow ECS or an internal convention, as long as they remain consistent across applications and the log pipeline.

| Field | Meaning | Example |
| --- | --- | --- |
| `event.name` | Stable event name for filtering/counting | `service.registration.succeeded` |
| `service.name` | Logical service ID | `inventory-service` |
| `service.instance.id` | Unique replica ID | `inventory-10-20-1-15-8081` |
| `service.version` | Software version | `2.4.1` |
| `deployment.environment` | Deployment environment | `production` |
| `service.region` | Instance region | `ap-southeast-1` |
| `service.zone` | Zone/failure domain | `ap-southeast-1a` |
| `discovery.provider` | Discovery provider | `eureka`, `consul`, `zookeeper`, `kubernetes` |
| `registry.endpoint` | Normalized registry endpoint name | `consul-agent.internal:8500` |
| `operation.id` | ID linking steps of a lifecycle operation | `reg-7f21a9` |
| `registration.state` | Current registration state | `REGISTERING`, `REGISTERED`, `FAILED` |
| `connection.state` | Provider/client connection state | `CONNECTED`, `SUSPENDED`, `LOST` |
| `retry.attempt` | Current attempt number | `3` |
| `retry.max` | Maximum attempts per policy | `5` |
| `retry.delay.ms` | Wait time before next attempt | `2000` |
| `duration.ms` | Operation duration | `84` |
| `error.type` | Exception class or error code | `ConnectTimeoutException` |
| `trace.id`, `span.id` | Link to distributed trace if present | ID issued by tracing system |

Not every log line needs every field. However, fields identifying the service, instance, and provider should appear in important lifecycle events. `registry.endpoint` should be a DNS/alias name or normalized address; never log URLs containing usernames, passwords, tokens, or secret query parameters.

A successful JSON event might look like:

```json
{
  "@timestamp": "2026-11-24T14:30:12.418Z",
  "log.level": "INFO",
  "event.name": "service.registration.succeeded",
  "service.name": "inventory-service",
  "service.instance.id": "inventory-10-20-1-15-8081",
  "service.version": "2.4.1",
  "deployment.environment": "production",
  "discovery.provider": "consul",
  "registry.endpoint": "consul-agent.internal:8500",
  "registration.state": "REGISTERED",
  "duration.ms": 84,
  "operation.id": "reg-7f21a9"
}
```

This is an illustrative schema. You can rename fields to match your organization's logging standard, but do not let each service invent different names for the same concept.

## 3. Dividing Logs by Lifecycle Phase

A discovery lifecycle should have clear event milestones:

| Phase | Suggested Event | Information to Record |
| --- | --- | --- |
| Loading configuration | `discovery.config.loaded` | Provider, service ID, environment, config source, profile, schema version |
| Validating configuration | `discovery.config.validated` / `discovery.config.invalid` | Missing/invalid fields, without logging secret values |
| Starting connection | `registry.connection.started` | Endpoint alias, timeout, provider |
| Connection succeeded | `registry.connection.established` | Connect duration, cluster/agent alias if safe |
| Starting registration | `service.registration.started` | Service ID, instance ID, operation ID |
| Registration succeeded | `service.registration.succeeded` | Duration, provider, final state |
| Registration failed | `service.registration.failed` | Error type, retryable flag, attempt, normalized reason |
| Scheduling retry | `service.registration.retry_scheduled` | Next attempt, backoff, retry limit |
| Connection lost | `registry.connection.suspended` | Previous/new state, timestamp, cache impact |
| Reconnected | `registry.connection.reconnected` | Outage duration, whether session survived or was lost if provider reports it |
| Restoring registration | `service.registration.restored` | Instance ID, old/new operation ID, convergence duration |
| Application shutdown | `service.registration.deregistered` | Shutdown reason, drain duration, deregistration outcome |

Use stable event names so dashboards and alerts do not rely on free-form wording in log messages. Human-readable messages can evolve for clarity; `event.name` should remain stable as part of the schema.

## 4. Logging Auto-Configuration Safely

A Spring Boot application can receive configuration from many sources: `application.yml`, profiles, environment variables, command-line arguments, Config Server, Consul Config, or Kubernetes ConfigMaps/Secrets. At startup, you need to know **which configuration was selected** and **which values were validated**, without dumping the entire `Environment`.

Example discovery configuration:

```yaml
app:
  discovery:
    provider: ${DISCOVERY_PROVIDER:consul}
    service-id: ${spring.application.name}
    registry-endpoint: ${REGISTRY_ENDPOINT:consul-agent:8500}
    connect-timeout: 3s
    max-attempts: 5
    environment: ${APP_ENV:local}
```

You can bind it to `@ConfigurationProperties` and validate before creating the client:

```java
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.discovery")
public record DiscoveryProperties(
        @NotBlank String provider,
        @NotBlank String serviceId,
        @NotBlank String registryEndpoint,
        @NotNull Duration connectTimeout,
        @Min(1) @Max(10) int maxAttempts,
        @NotBlank String environment
) {}
```

Register the properties using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(DiscoveryProperties.class)`. After binding and validation, log only explicitly permitted fields:

To enforce Jakarta Validation annotations, add `spring-boot-starter-validation` if the application does not already have a validation provider on the classpath.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DiscoveryStartupLogging {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoveryStartupLogging.class);

    @Bean
    ApplicationRunner logDiscoveryConfiguration(DiscoveryProperties properties) {
        return args -> log.atInfo()
                .addKeyValue("event.name", "discovery.config.validated")
                .addKeyValue("discovery.provider", properties.provider())
                .addKeyValue("service.name", properties.serviceId())
                .addKeyValue("deployment.environment", properties.environment())
                .addKeyValue("registry.endpoint", properties.registryEndpoint())
                .addKeyValue("connect.timeout.ms", properties.connectTimeout().toMillis())
                .addKeyValue("retry.max", properties.maxAttempts())
                .log("Discovery configuration validated");
    }
}
```

This example uses the SLF4J 2 fluent logging API, commonly available in Spring Boot 3 applications. With SLF4J 1.7, use parameterized placeholder logging or MDC instead of `atInfo().addKeyValue(...)`.

Never log:

- Passwords, client secrets, bearer tokens, API keys, private keys, or raw ServiceAccount tokens.
- The entire `Environment`, an entire `@ConfigurationProperties` object, or `toString()` of objects that might hold secrets.
- URIs with user-info, tokens in query strings, or authentication headers.
- Secret contents, credentials, or user data retrieved from Config Server/KV.

If you need to prove where configuration came from, log `config.source=consul-kv` or `config.profile=production`; there is no need to print every property value. For configuration that changes at runtime, log a non-sensitive `config.revision` or version/hash to compare across replicas.

## 5. Configuring Logging in Spring Boot

Example log level configuration for discovery and provider integrations:

```yaml
logging:
  level:
    com.example.discovery: INFO
    org.springframework.cloud.client.serviceregistry: INFO
    org.springframework.cloud.netflix.eureka: INFO
    org.springframework.cloud.consul: INFO
    org.apache.curator: INFO
```

Exact logger names may vary by Spring Cloud, Eureka, Consul, or Curator version. During investigations, selectively enable `DEBUG` on the relevant packages for a short period; avoid leaving system-wide `TRACE` enabled long-term because it generates high log volume and can expose connection details.

With Spring Boot 3.4 or later, you can use built-in structured logging to emit JSON in a supported format, such as ECS:

```yaml
logging:
  structured:
    format:
      console: ecs
```

On older Spring Boot versions, configure the JSON encoder of your logging stack. Regardless of formatter, ensure `event.name`, service identity, and operation context are preserved through the log pipeline.

## 6. Logging Service Registration: Start, Success, and Failure

Service registration is a lifecycle operation, not just a single `Registered` line. Log both the start and the outcome to measure duration and distinguish connectivity errors from invalid registration data.

Example logging helper for application-managed registration operations:

```java
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RegistrationLog {

    private static final Logger log =
            LoggerFactory.getLogger(RegistrationLog.class);

    public void succeeded(
            String serviceId,
            String instanceId,
            String provider,
            String operationId,
            Duration duration) {

        log.atInfo()
                .addKeyValue("event.name", "service.registration.succeeded")
                .addKeyValue("service.name", serviceId)
                .addKeyValue("service.instance.id", instanceId)
                .addKeyValue("discovery.provider", provider)
                .addKeyValue("operation.id", operationId)
                .addKeyValue("duration.ms", duration.toMillis())
                .addKeyValue("registration.state", "REGISTERED")
                .log("Service instance registered");
    }

    public void failed(
            String serviceId,
            String instanceId,
            String provider,
            String operationId,
            int attempt,
            Throwable error) {

        log.atWarn()
                .addKeyValue("event.name", "service.registration.failed")
                .addKeyValue("service.name", serviceId)
                .addKeyValue("service.instance.id", instanceId)
                .addKeyValue("discovery.provider", provider)
                .addKeyValue("operation.id", operationId)
                .addKeyValue("retry.attempt", attempt)
                .addKeyValue("error.type", error.getClass().getSimpleName())
                .setCause(error)
                .log("Service instance registration failed");
    }
}
```

This helper is meant to wrap registration operations owned by the application. When Spring Cloud auto-registration manages the lifecycle, do not invoke registration a second time just to emit logs. Instead, observe framework logs, lifecycle events provided by your version, or attach an observer at the proper extension point.

Never log `REGISTERED` before the registry confirms the operation succeeded. If a provider only accepts registration asynchronously, distinguish `registration.requested` from `registration.confirmed`.

## 7. Writing Investigable Retry Logs

When registry connection fails, classify the error before retrying:

- **Transient:** timeouts, connection resets, leader elections, or an agent temporarily unavailable.
- **Configuration/permanent:** wrong hostname, port, scheme, token, ACL, TLS trust, or invalid service ID.
- **Capacity/throttling:** registry overloaded or temporarily rejecting requests due to rate limits.

Example contextual retry entry:

```json
{
  "event.name": "registry.connection.retry_scheduled",
  "service.name": "inventory-service",
  "service.instance.id": "inventory-10-20-1-15-8081",
  "discovery.provider": "eureka",
  "registry.endpoint": "eureka-1.internal:8761",
  "retry.attempt": 2,
  "retry.max": 5,
  "retry.delay.ms": 2000,
  "error.type": "ConnectTimeoutException",
  "error.category": "transient",
  "operation.id": "reg-7f21a9"
}
```

Log a line when scheduling a retry, including the actual attempt number and delay. Avoid logging full stack traces on every retry if the exact same error repeats continuously; log the stack trace on the first and final attempts, while logging only error type and endpoint alias on intermediate retries.

Backoff and jitter prevent many replicas from retrying at the exact same instant. Logs should reflect the computed delay after jitter is applied so operators know when the next attempt is expected.

## 8. Logging Reconnection by State Transition

Do not emit a generic `Reconnected` line for every provider without distinguishing the prior state. A general model can use states such as:

```text
STARTING -> CONNECTING -> CONNECTED
CONNECTED -> SUSPENDED -> RECONNECTING -> RECONNECTED
RECONNECTED -> RECONCILING -> READY
CONNECTED -> SESSION_LOST -> NEW_SESSION -> REGISTERING -> REGISTERED
```

These states are a general application observability model; actual event names depend on the provider. `RECONNECTED` only states that the connection returned. `READY` should only be logged after mandatory cache synchronization or re-registration steps have finished.

Example state transition log:

```java
log.atWarn()
        .addKeyValue("event.name", "registry.connection.state_changed")
        .addKeyValue("service.name", serviceId)
        .addKeyValue("service.instance.id", instanceId)
        .addKeyValue("discovery.provider", provider)
        .addKeyValue("connection.state.previous", "CONNECTED")
        .addKeyValue("connection.state.current", "SUSPENDED")
        .addKeyValue("operation.id", operationId)
        .log("Registry connection suspended");
```

When connectivity returns, log both outage duration and reconciliation results:

```json
{
  "event.name": "registry.recovery.completed",
  "service.name": "inventory-service",
  "discovery.provider": "zookeeper",
  "connection.state": "RECONNECTED",
  "session.state": "NEW_SESSION",
  "registration.state": "REGISTERED",
  "cache.state": "INITIALIZED",
  "outage.duration.ms": 12450,
  "operation.id": "recovery-b193c2"
}
```

If connectivity returns while registration has not yet succeeded, log `registry.connection.reconnected` and `service.registration.retry_scheduled` separately. Never collapse them into a misleading success message.

## 9. Provider-Specific Log Differences

Registries have different lifecycles; the shared log schema should be enriched with provider-specific fields rather than forcing every provider into identical states.

| Provider | Events to Observe | Specific Context |
| --- | --- | --- |
| Eureka | Client register, heartbeat/renew, fetch registry, status change, deregister | Application name, instance ID, server URL alias, lease/renew outcome, fetch duration |
| Consul | Agent registration, health check, catalog lookup, deregister, ACL/TLS failure | Service ID, node, check ID/status, datacenter/namespace, agent endpoint alias |
| ZooKeeper/Curator | Connected, `SUSPENDED`, `RECONNECTED`, `LOST`, session recovery, ephemeral node registration | Ensemble alias, normalized znode path, session state, retry count, cache initialization |
| Kubernetes | API discovery, list/watch, informer/cache sync, RBAC failure, endpoint update | Namespace, resource kind, API group, ServiceAccount identity (no token), resource version if appropriate |

### Eureka

When using Eureka, distinguish three activities:

1. Registering the instance with Eureka Server.
2. Sending heartbeats to renew the lease.
3. Fetching/refreshing the local registry to look up other services.

A `register succeeded` log does not prove consumers have fetched the updated registry. Logging every heartbeat at `INFO` creates noise; use metrics for heartbeat frequency and log `WARN`/`ERROR` only when renewals fail persistently or notable state transitions occur.

### Consul

With Consul, registration may be submitted to a local agent; the agent executes checks and updates catalog/health status. Therefore, distinguish `registration accepted by agent` from `health check passing`. When a check is `critical`, logs should include check ID, check type, sanitized output, and latest check timestamp; avoid logging raw output that might contain sensitive details.

### ZooKeeper and Curator

Curator emits `CONNECTED`, `SUSPENDED`, `RECONNECTED`, `LOST`, and potentially `READ_ONLY`. `SUSPENDED` means connectivity is temporarily lost and cached data may be stale; `LOST` means the session expired and ephemeral nodes tied to the old session were deleted. After `LOST`, logs must show the new session, znode re-registration, and when the cache is re-initialized.

Never log session credentials or full znode data if payloads contain sensitive metadata. Log only normalized paths/service IDs and instance IDs.

### Kubernetes

With Spring Cloud Kubernetes, `403 Forbidden` errors should log resource, API group, verb, and namespace to distinguish missing RBAC permissions from API server connectivity errors. Never log bearer tokens. When using informers, distinguish `watch connected` from `initial cache sync completed`; mark discovery data ready only after cache sync finishes.

## 10. Using MDC and Operation IDs to Correlate Log Lines

MDC (Mapped Diagnostic Context) attaches fields to logs emitted within an execution scope. Example adding service identity and operation ID during a synchronous registration operation:

```java
import org.slf4j.MDC;

public void registerWithContext(String serviceId, String instanceId,
                                String operationId) {
    try (MDC.MDCCloseable service = MDC.putCloseable("service.name", serviceId);
         MDC.MDCCloseable instance = MDC.putCloseable("service.instance.id", instanceId);
         MDC.MDCCloseable operation = MDC.putCloseable("operation.id", operationId)) {

        log.info("Starting service registration");
        performRegistration();
        log.info("Service registration completed");
    }
}
```

`MDC.putCloseable` is available in modern SLF4J. Using try-with-resources restores the prior context and prevents fields from leaking into subsequent requests/threads.

Do not treat MDC as global state. Across thread pools or async tasks, context must be propagated properly through executors. In WebFlux/Reactor, ThreadLocal-based MDC does not automatically follow every thread switch; use Micrometer Context Propagation/Observation or Reactor-integrated Micrometer Tracing instead of calling `MDC.put()` in one operator and assuming it persists in the next.

`traceId` and `spanId` link logs with distributed request traces. Registration and reconnection can happen outside requests without a trace context; in those cases, use a dedicated `operation.id` to link lifecycle steps. Never fabricate a fake trace ID and call it a business trace.

## 11. Logging Runtime Configuration Changes

Some applications refresh configuration when Config Server, Consul KV, or Kubernetes ConfigMaps change. When a change occurs, logs should record:

- `discovery.config.refresh.started` and `discovery.config.refresh.completed` events.
- Configuration source and profile/context.
- Non-sensitive revision/version/hash.
- Which property groups changed, without printing all values.
- Which clients or components must reconnect/re-register after the refresh.
- Application outcome and duration.

Example:

```json
{
  "event.name": "discovery.config.refresh.completed",
  "service.name": "inventory-service",
  "config.source": "consul-kv",
  "config.profile": "production",
  "config.revision": "cfg-2026-11-24-03",
  "changed.keys": [
    "app.discovery.connect-timeout",
    "app.discovery.max-attempts"
  ],
  "duration.ms": 42
}
```

If a refresh changes service ID, instance ID, or registry endpoint, ensure explicit validation and lifecycle transitions occur. Never silently swap endpoints while an old registration remains active; determine whether to deregister from the old endpoint, connect to the new endpoint, and re-register.

## 12. Choosing Log Levels to Avoid Noise

| Level | Use For | Example |
| --- | --- | --- |
| ERROR | Operation cannot complete after retry policy or unrecoverable config | Registration retries exhausted, invalid TLS trust, token rejected with no fallback |
| WARN | Temporary degradation or abnormal state needing attention | Registry disconnected, retry scheduled, stale cache, critical health check |
| INFO | Meaningful lifecycle milestones and completed state changes | Configuration validated, registration succeeded, reconnect/reconciliation completed, deregistered |
| DEBUG | Details for short-term troubleshooting | Endpoint selection, property source precedence, sanitized request metadata |
| TRACE | High-volume protocol or internal details | Watch events, detailed heartbeats, internal retry loops |

Do not log every heartbeat or every registry poll at `INFO`. Periodic operations should be observed via metrics such as `registry_heartbeat_total`, `registry_fetch_duration`, `registration_retry_total`, `registry_reconnect_total`, and `registry_cache_age_seconds`.

## 13. From Logs to Metrics and Traces

Logs explain a specific event; metrics show trends and frequencies; traces connect steps of a request across multiple services. These three telemetry signals complement each other.

| Question | Appropriate Telemetry |
| --- | --- |
| Which instance just failed to register and what was the error? | Logs with service/instance/operation context |
| When did the registration failure rate start rising? | Counters and alerts by provider/environment |
| How long does reconnection take on average? | Histogram of outage/recovery duration |
| Which request failed when LoadBalancer selected an instance? | Distributed trace with service ID and peer spans |
| How stale is the discovery cache right now? | Gauge of cache age/last successful refresh |
| How many retries occurred? | Counter by error category, without high-cardinality labels |

Avoid using `instance.id`, `operation.id`, or raw endpoints as metric labels because their cardinality can grow unbounded. Those granular fields belong in logs/traces; metrics should use low-cardinality labels such as `provider`, `environment`, `service name`, and `outcome`.

## 14. Investigating a Registration/Reconnect Incident

Suppose `inventory-service` occasionally disappears from the registry. Investigate in this order:

1. Search for `service.name=inventory-service` and the specific `service.instance.id`.
2. Check the `discovery.config.validated` event to inspect provider, endpoint alias, profile, and retry configuration.
3. Find the most recent `service.registration.succeeded` to identify the last successful registration.
4. Find `registry.connection.state_changed` or `registry.connection.retry_scheduled` to see when connectivity was lost.
5. Correlate `retry.attempt`, `error.type`, `duration.ms`, and endpoint alias to classify timeout, DNS, ACL, or TLS issues.
6. For Consul, also inspect health check status; for Eureka, inspect heartbeats and instance status; for ZooKeeper, check `LOST` and session recovery.
7. Find `service.registration.restored` or `registry.recovery.completed` to confirm convergence.
8. If reconnection succeeded while consumers still cannot find the instance, check cache/fetch refresh on the consumer side.

Conceptual query example in a log platform:

```text
service.name = "inventory-service"
AND event.name IN (
  "service.registration.failed",
  "registry.connection.retry_scheduled",
  "registry.connection.reconnected",
  "service.registration.restored"
)
ORDER BY @timestamp ASC
```

Exact query syntax depends on Elasticsearch, Loki, Splunk, or whichever log platform is used. What matters is a consistent field schema so timelines can be reconstructed.

## 15. Avoiding Log Storms and Protecting Data

When a registry loses connectivity, many replicas may retry simultaneously. If every retry logs a full stack trace at `ERROR`, the log pipeline can become overloaded right when diagnostics are needed most.

Measures to apply:

- Use exponential backoff with jitter and cap retry attempts.
- Log one event when transitioning from connected to degraded, rather than repeating the same state every second.
- Log attempt/delay/error category on retries while reducing repeated stack traces.
- Emit clear logs when retries succeed or the policy is exhausted.
- Apply rate limiting or sampling to high-frequency recurring events.
- Never log tokens, passwords, secrets, raw config, personal data, or full registry payloads.
- Sanitize exception messages if they might contain URLs, headers, or credentials.
- Restrict log read access because internal endpoints, topology, and instance IDs can still be sensitive.

Never drop the first state transition or the final retry with sampling. Critical lifecycle milestones must always remain traceable.

## 16. Discovery Logging Checklist

- [ ] Every key lifecycle log includes service name, instance ID, and provider.
- [ ] Environment, version, and registry endpoint alias are included where appropriate.
- [ ] Stable event names and operation IDs link related steps.
- [ ] Config logs record only allowed fields; never dump full properties or `Environment`.
- [ ] Registration logs include started/succeeded/failed and duration.
- [ ] Retries include attempt, max, delay, error type, and error category.
- [ ] Reconnects log before/after states and reconciliation outcomes.
- [ ] Re-establishing connectivity is distinguished from restored cache/registration.
- [ ] Trace/span fields are included when operating inside a traced request; operation ID links non-request lifecycle steps.
- [ ] MDC is cleaned up properly and context propagates across async/reactive boundaries.
- [ ] Periodic heartbeats/polling do not emit continuous `INFO` logs.
- [ ] Secrets, tokens, credentials, and personal data never appear in logs.
- [ ] Metrics track error rates, retries, outage duration, and cache age.
- [ ] Timeline queries have been tested for a specific instance during a reconnect scenario.

Good discovery logging does more than say an application connected or registered successfully. It shows which service and instance are acting, which configuration and provider they use, in what context the operation ran, how many retries occurred, and which components actually recovered after reconnection. When the schema is consistent, safe, and carries operation context, operations teams can reconstruct the registration lifecycle from auto-configuration all the way back to readiness.
