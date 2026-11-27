# Recording the Source, Timestamp, and Outcome of Configuration Changes

In a Spring Cloud application, configuration can originate from many places: configuration files, environment variables, Spring Cloud Config Server, Vault, or a custom `PropertySource`. When configuration changes while the application is running, the operations team needs to answer four questions: **where did the change come from, who or what system requested it, when did the change occur, and how did each instance apply the result?**

Spring Cloud Context provides events such as `EnvironmentChangeEvent` and `RefreshScopeRefreshedEvent`; Spring Boot Actuator provides observability endpoints `env`, `configprops`, `health`, and `auditevents`. These components form a foundation for tracking changes, but they do not automatically assemble a complete audit trail. The application must add source metadata, configuration revision, requester identity, correlation ID, and processing outcomes.

This lesson belongs to the **Observability** chapter of the **SPRING_CLOUD_CORE** module. We will progress from the configuration change lifecycle, event recording, audit record design, and an example integrating `ContextRefresher` with `AuditEventRepository`, to tracking across Spring Cloud Bus, Actuator, metrics, logs, and testing.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish changes at the configuration store, changes in the `Environment`, and changes applied to beans.
- Explain the data provided by `EnvironmentChangeEvent` and `RefreshScopeRefreshedEvent`.
- Recognize metadata that default events do not supply, such as actor, source revision, and correlation ID.
- Design an audit record containing source, application, profile, instance, timestamp, and outcome.
- Record audits using `AuditEventRepository` and read them via Actuator `auditevents`.
- Use `ContextRefresher.refresh()` to obtain changed keys and orchestrate refreshes.
- Distinguish rebinding `@ConfigurationProperties` from invalidating beans in `@RefreshScope`.
- Track change propagation through Spring Cloud Bus and the Config Monitor webhook.
- Observe configuration state via `env`, `configprops`, `health`, and logs.
- Protect sensitive data in logs, audit records, and Actuator.
- Test success, failure, changed keys, and metadata using a fixed clock and fake data sources.

## 2. Three Layers of a Configuration Change

A change can exist in the configuration store without yet being loaded into the application. Similarly, the `Environment` may have received new values while the consuming bean has not yet been re-instantiated. Therefore, distinguish three layers:

| Layer | What Happened | Evidence to Record |
| --- | --- | --- |
| Configuration source | Git commit, Config Server revision, secret version, or file changed | Source, revision/label, actor, commit timestamp |
| Runtime Environment | Application loaded property sources and identified changed keys | Application, profile, instance, changed keys, event timestamp |
| Runtime component | `@ConfigurationProperties` rebound or `@RefreshScope` bean invalidated and recreated on next access | Refresh outcome, bean health, initialization error, verification timestamp |

~~~mermaid
flowchart TD
    A[Config source changes] --> B[Source audit: actor, revision, time]
    B --> C[Config Server / refresh request]
    C --> D[Each application instance loads configuration]
    D --> E[EnvironmentChangeEvent]
    E --> F[Rebind ConfigurationProperties]
    E --> G[Invalidate RefreshScope cache]
    G --> H[Next access creates scoped bean]
    F --> I[Verify effective configuration]
    H --> I
    I --> J[Audit outcome and health]
~~~

A refresh can succeed at the source layer yet fail when an instance loads the configuration. Or the `Environment` changes yet the new bean fails during initialization on the next access. Do not collapse those states into a single “config updated” label.

## 3. What Do Spring Cloud Events Record?

### 3.1. EnvironmentChangeEvent

Spring Cloud Context publishes `EnvironmentChangeEvent` when the Environment is updated and keys have changed. The event provides the set of key names via `getKeys()`.

When the event is handled, Spring Cloud performs several default actions:

- Rebinds `@ConfigurationProperties` beans in the context.
- Updates log levels for `logging.level.*` properties.

Note: `@ConfigurationProperties` beans using constructor binding, including Java records, cannot be refreshed via this rebinding mechanism. If a bean needs to change on refresh, choose a binding style and bean lifecycle suited to that requirement.

You can add an `ApplicationListener` or `@EventListener` to log, increment metrics, or emit observability notifications.

Minimal listener example:

~~~java
import java.time.Instant;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationChangeLogger {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Instant occurredAt = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=environment-change time=%s changedKeys=%s%n",
                occurredAt,
                event.getKeys());
    }
}
~~~

The listener above records when the event was created and the list of keys. It does not yet know who requested the refresh, whether the source is Git or Vault, which revision was loaded, or whether creating new beans succeeded.

### 3.2. RefreshScopeRefreshedEvent

When `RefreshScope` clears the cache of a bean or the entire scope, Spring Cloud publishes `RefreshScopeRefreshedEvent`. For a single-bean refresh, the event carries the bean name; for `refreshAll()`, the event uses a default name.

~~~java
import java.time.Instant;

import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshScopeChangeLogger {

    @EventListener
    public void onRefreshScopeRefreshed(
            RefreshScopeRefreshedEvent event) {
        System.out.printf(
                "event=refresh-scope-invalidated time=%s bean=%s%n",
                Instant.ofEpochMilli(event.getTimestamp()),
                event.getName());
    }
}
~~~

The event name easily leads readers to think the new bean has already finished being created. In reality, a refresh-scope bean is a lazy proxy: the refresh operation clears the cached target and a new target is created on the next invocation. The event proves the cache entry was invalidated; it does not by itself prove the subsequent instantiation succeeded.

Spring Cloud has `RefreshScopeHealthIndicator` to reflect errors when bean refresh or configuration rebinding fails. Combine events with health and bean initialization logs to verify the outcome.

### 3.3. Default Events Are Not a Complete Audit Record

`EnvironmentChangeEvent` mainly provides changed keys. `RefreshScopeRefreshedEvent` indicates which bean/scope was refreshed. These two events do not carry all information needed for auditing:

| Audit Field | Provided by Default Events? | How to Supplement |
| --- | --- | --- |
| Changed key list | Yes in `EnvironmentChangeEvent` | Read from `getKeys()` |
| Event timestamp | Yes via `ApplicationEvent` timestamp | Convert to UTC `Instant` |
| Actor/requester | No | Obtain from authenticated principal at control plane |
| Configuration source | Incomplete | Attach source ID, PropertySource name, or publisher |
| Revision/commit/secret version | No | Obtain from Config Server, Git, or secret manager |
| Correlation ID | No | Propagate from request/webhook/Bus message |
| Per-instance outcome | Incomplete | Record status on each client and verify health |
| Old/new values | No | Capture snapshot with allowlist and redaction if genuinely needed |

Do not infer the actor from hostname or from `event.getSource()`. An event's source is usually the context that published the event, not the identity of the person who changed the configuration.

## 4. Audit Record Model

A configuration change record should have a stable structure for querying and correlating across multiple instances.

| Field | Example | Meaning |
| --- | --- | --- |
| `eventType` | `CONFIG_REFRESH_SUCCEEDED` | Event type |
| `occurredAt` | `2026-11-18T13:20:15Z` | Timestamp recorded in UTC |
| `actor` | `deploy-bot` | Requesting user or system |
| `application` | `orders-service` | Target application |
| `instanceId` | `orders-7f9c` | Replica that processed it |
| `source` | `spring-cloud-config` | Configuration source |
| `revision` | `a41c8d2` | Commit, label, or version |
| `profiles` | `staging` | Active profiles |
| `changedKeys` | `limits.pool-size` | Keys detected as changed |
| `correlationId` | `cfg-req-8241` | Links logs/events across systems |
| `outcome` | `SUCCEEDED`, `FAILED`, `PARTIAL` | Processing result |
| `failureType` | `ConnectException` | Failure type, if any |
| `durationMs` | `438` | Execution duration |

Use UTC timestamps (`Instant`) rather than local-time strings. In distributed systems, clocks across nodes can drift; also store correlation ID and source revision to order events accurately.

### 4.1. Source and Revision Are Two Different Concepts

The `PropertySource` name indicates which source provides a property in the Environment, such as a configuration source from Config Server. It does not necessarily indicate the exact Git commit or released secret version.

If you need traceability back to a commit, the control plane must pass the revision/label from the publishing source. If you need traceability to a secret version, record the version ID returned by the secret manager. Do not synthesize a revision from client timestamps, as it does not represent the actual version at the source.

### 4.2. One Change Can Produce Different Outcomes Per Instance

Suppose Config Server releases revision `a41c8d2` to three replicas. The first replica loads and applies it successfully, the second replica cannot connect to Config Server, and the third replica loads it yet a refresh-scope bean fails during initialization.

Source-level auditing records only one release. Client-level auditing needs three separate outcomes:

| Instance | Revision | Outcome |
| --- | --- | --- |
| `orders-1` | `a41c8d2` | `SUCCEEDED` |
| `orders-2` | `a41c8d2` | `FAILED_TO_LOAD` |
| `orders-3` | `a41c8d2` | `BEAN_REINITIALIZATION_FAILED` |

Do not use a single “refresh succeeded” event at Config Server to conclude that all clients finished applying the change.

## 5. Observing Property Sources and Effective Values

Spring's `Environment` maintains a list of `PropertySource`s. Source order determines the final value when multiple sources provide the same key. Therefore, when investigating configuration, record the source name providing the key, the effective value (only for keys permitted to be logged), the active profile, and origin metadata if the property source supports it.

### 5.1. Finding the Source Providing a Key

With `ConfigurableEnvironment`, you can iterate through property sources to find the first source containing a key:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public final class PropertySourceInspector {

    private PropertySourceInspector() {
    }

    public static Map<String, String> findEffectiveSources(
            ConfigurableEnvironment environment,
            Set<String> keys) {

        Map<String, String> result = new LinkedHashMap<>();

        for (String key : keys) {
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    result.put(key, source.getName());
                    break;
                }
            }
        }

        return result;
    }
}
~~~

This is a general-purpose way to inspect the effective source. Some sources may wrap others, such as `CompositePropertySource` or composite property sources created by Spring Boot. When you need detailed origin information such as file, line, or Git source, use origin metadata supported by the implementation and revision metadata from the publishing system.

### 5.2. Do Not Dump the Entire Environment to Logs

`Environment` can contain passwords, tokens, private keys, internal URLs, or connection strings. Never dump every property source or the whole Environment to logs for “easier debugging”.

Instead:

- Record the list of changed keys.
- Record the source name and revision.
- Only capture before/after snapshots for an allowlist of non-sensitive keys.
- Redact keys whose names contain `password`, `secret`, `token`, `credential`, `private-key`, or equivalent names per policy.
- If secrets must be compared, use HMAC with a separately managed audit key; do not use unkeyed hashes for low-entropy secrets.

## 6. EnvironmentChangeEvent and ContextRefresher in the Refresh Cycle

`ContextRefresher.refresh()` executes these core steps:

1. Capture current property state.
2. Update the Environment from configuration sources according to the active implementation.
3. Compare before and after to find changed keys.
4. Publish `EnvironmentChangeEvent` with the changed key set.
5. Call `RefreshScope.refreshAll()` to invalidate targets in refresh scope.
6. Return the changed key set to the caller.

This lets a refresh-orchestrating service record start/end timestamps, source metadata, and changed keys. If refresh throws an exception after the Environment has already been updated, the result can be a partial state; audits should distinguish complete failures from failures occurring after the Environment update step.

~~~mermaid
sequenceDiagram
    participant Admin as Authenticated operator
    participant Audit as Audited refresh service
    participant Refresher as ContextRefresher
    participant Env as Environment
    participant Beans as Rebind / RefreshScope
    participant Repo as AuditEventRepository

    Admin->>Audit: refresh(source, revision, correlationId)
    Audit->>Audit: Capture actor and startedAt
    Audit->>Env: Snapshot allowlisted values
    Audit->>Refresher: refresh()
    Refresher->>Env: Reload property sources
    Refresher->>Env: Compare before and after
    Refresher->>Beans: Publish EnvironmentChangeEvent
    Refresher->>Beans: Invalidate RefreshScope
    Refresher-->>Audit: changed keys
    Audit->>Env: Snapshot effective values
    Audit->>Repo: Store success/failure and metadata
    Audit-->>Admin: Refresh result
~~~

When an application uses Config Data versus legacy bootstrap, the concrete `ContextRefresher` implementation differs. Use the bean auto-configured by Spring Cloud for the running version instead of manually constructing a refresher that does not match the application's configuration loading mechanism.

## 7. Recording Audits with AuditEventRepository

Spring Boot Actuator has the `AuditEventRepository` abstraction for storing and querying `AuditEvent`s. An `AuditEvent` has a timestamp, principal, event type, and extra data map. The `/actuator/auditevents` endpoint only activates when the application context has an `AuditEventRepository` bean.

Add the Actuator starter if the application does not have it yet:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

The starter provides audit APIs and the Actuator endpoint. The application still needs an `AuditEventRepository` implementation to store events; choose a durable implementation if history must survive restarts and span multiple replicas.

### 7.1. Designing the Refresh Orchestration Service

The example below wraps `ContextRefresher.refresh()` to record:

- Actor taken from the authenticated identity.
- Source and revision passed from the control plane.
- Correlation ID linking Config Server and client logs.
- Start and completion timestamps.
- Changed keys returned by Spring Cloud.
- Before/after snapshots for an allowlist of non-sensitive keys only.
- Pipeline outcome or errors that may occur after the Environment was updated.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Service;

@Service
public class AuditedConfigurationRefresher {

    private static final Set<String> SAFE_KEYS = Set.of(
            "feature.checkout.enabled",
            "limits.pool-size");

    private final ContextRefresher contextRefresher;
    private final AuditEventRepository auditEvents;
    private final ConfigurableEnvironment environment;
    private final Clock clock;

    public AuditedConfigurationRefresher(
            ContextRefresher contextRefresher,
            AuditEventRepository auditEvents,
            ConfigurableEnvironment environment,
            Clock clock) {
        this.contextRefresher = contextRefresher;
        this.auditEvents = auditEvents;
        this.environment = environment;
        this.clock = clock;
    }

    public Set<String> refresh(
            String actor,
            String source,
            String revision,
            String correlationId) {

        Instant requestedAt = clock.instant();
        Map<String, String> before = snapshotSafeValues();

        Set<String> changedKeys;
        Map<String, String> after;
        try {
            changedKeys = contextRefresher.refresh();
            after = snapshotSafeValues();
        }
        catch (RuntimeException exception) {
            Instant failedAt = clock.instant();
            Map<String, String> afterFailure = snapshotSafeValues();

            Map<String, Object> data = commonData(
                    source, revision, correlationId, requestedAt);
            data.put("completedAt", failedAt.toString());
            data.put("durationMs",
                    Duration.between(requestedAt, failedAt).toMillis());
            data.put("before", before);
            data.put("after", afterFailure);
            data.put("observedChangedKeys",
                    changedSafeKeys(before, afterFailure));
            data.put("outcome", "FAILED_OR_PARTIAL");
            data.put("failureType", exception.getClass().getName());

            auditEvents.add(new AuditEvent(
                    failedAt,
                    actor,
                    "CONFIG_REFRESH_PIPELINE_FAILED",
                    data));

            throw exception;
        }

        Instant completedAt = clock.instant();
        Map<String, Object> data = commonData(
                source, revision, correlationId, requestedAt);
        data.put("completedAt", completedAt.toString());
        data.put("durationMs",
                Duration.between(requestedAt, completedAt).toMillis());
        data.put("changedKeys", new TreeSet<>(changedKeys));
        data.put("before", before);
        data.put("after", after);
        data.put("effectivePropertySources",
                PropertySourceInspector.findEffectiveSources(
                        environment, changedKeys));
        data.put("outcome",
                changedKeys.isEmpty() ? "NO_CHANGE" : "PIPELINE_COMPLETED");

        auditEvents.add(new AuditEvent(
                completedAt,
                actor,
                "CONFIG_REFRESH_PIPELINE_COMPLETED",
                data));

        return changedKeys;
    }

    private Map<String, Object> commonData(
            String source,
            String revision,
            String correlationId,
            Instant requestedAt) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("source", source);
        data.put("revision", revision);
        data.put("correlationId", correlationId);
        data.put("requestedAt", requestedAt.toString());
        data.put("application",
                environment.getProperty("spring.application.name", "application"));
        data.put("instanceId",
                environment.getProperty("app.instance-id", "unknown"));
        data.put("profiles", environment.getActiveProfiles());
        return data;
    }

    private Map<String, String> snapshotSafeValues() {
        Map<String, String> values = new LinkedHashMap<>();
        for (String key : SAFE_KEYS) {
            String value = environment.getProperty(key);
            if (value != null) {
                values.put(key, value);
            }
        }
        return values;
    }

    private Set<String> changedSafeKeys(
            Map<String, String> before,
            Map<String, String> after) {
        Set<String> keys = new TreeSet<>(before.keySet());
        keys.addAll(after.keySet());
        keys.removeIf(key ->
                java.util.Objects.equals(before.get(key), after.get(key)));
        return keys;
    }
}
~~~

`PropertySourceInspector` is the utility from Section 5.1. In this example, `SAFE_KEYS` contains only properties allowed to have before/after values stored. Never expand the allowlist to the entire Environment without a classification and redaction policy.

### 7.2. Providing a Clock

Using `Clock` makes time deterministic in tests and keeps the application consistent on UTC:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditClockConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

### 7.3. Metadata Sources Must Be Trustworthy

In the example, `actor` should come from the authenticated principal, while `source` and `revision` should come from the publisher or Config Server. Do not accept these fields as unverified free-form strings from a request body. If callers can self-report actor or revision, audit logs can be falsified.

`ContextRefresher.refresh()` returns the set of changed keys, not the Git commit or user identity. That metadata must be passed from the control plane or looked up through the configuration source's API.

### 7.4. Interpreting Pipeline Results Accurately

`PIPELINE_COMPLETED` means the refresh method completed and returned the list of changed keys. It does not guarantee every lazy bean in refresh scope has been successfully recreated, because new targets are only instantiated when the bean is next accessed.

When final confirmation is needed, combine:

- Health from `RefreshScopeHealthIndicator`.
- Bean initialization logs after the first access.
- A business health check verifying the new configuration works.
- A separate audit event for the final verification state.

If an exception occurs after the Environment has already changed, record `FAILED_OR_PARTIAL` to reflect that the runtime may have absorbed part of the change. Do not simply log `FAILED` and assume the Environment remained unchanged.

### 7.5. Audit Repository in Production

`AuditEventRepository` is a storage abstraction. An in-memory implementation suits demos/tests, but loses data on process restarts and is not shared across replicas. Production should use a durable repository, such as a dedicated audit database or event store.

If auditing is a mandatory control requirement, define explicit behavior when audit persistence fails: block the refresh operation, enqueue the event to an outbox for retry, or allow refresh while raising a critical alert. Never silently ignore audit write failures.

## 8. Combining Event Listeners with Auditing

The service in the previous section records the refresh request with full metadata. Listeners add information about which runtime events were actually emitted.

~~~java
import java.time.Instant;

import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.cloud.context.scope.refresh.RefreshScopeRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationRuntimeEventListener {

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        Instant eventTime = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=environment-change eventTime=%s changedKeys=%s%n",
                eventTime,
                event.getKeys());
    }

    @EventListener
    public void onRefreshScopeInvalidated(
            RefreshScopeRefreshedEvent event) {
        Instant eventTime = Instant.ofEpochMilli(event.getTimestamp());

        System.out.printf(
                "event=refresh-scope-invalidated eventTime=%s bean=%s%n",
                eventTime,
                event.getName());
    }
}
~~~

In a real application, replace `System.out` with a structured logger or publisher sending events to an observability system. Listeners can log event timestamp, application name, instance ID, and correlation ID if context propagation is set up.

Do not assume a correlation ID automatically propagates across every `ApplicationEvent`. If a refresh is triggered from an HTTP request, webhook, or Bus message, place the correlation ID into orchestration metadata and propagate it explicitly.

### 8.1. Stitching Events into a Timeline

An easy-to-investigate timeline can include:

| Milestone | Event | Where Recorded |
| --- | --- | --- |
| T0 | Config source commit/publish | Git or Config Server audit |
| T1 | Refresh request accepted | API gateway/control plane |
| T2 | Client starts refresh | Client audit service |
| T3 | `EnvironmentChangeEvent` | Client event listener |
| T4 | `RefreshScopeRefreshedEvent` | Client event listener |
| T5 | Bean recreated/health verified | Client health/logs/audit |

All records should share the same correlation ID and source revision. You can then identify which instances have not received the revision or which ones received it yet failed to initialize beans.

## 9. Tracking Changes via Spring Cloud Config and Bus

Spring Cloud Config Client does not poll Config Server by default for changes. In multi-replica systems, you can use Spring Cloud Bus to broadcast refresh signals to relevant instances.

### 9.1. Config Monitor and Webhooks

When Config Server includes the `spring-cloud-config-monitor` dependency and Spring Cloud Bus is enabled, the `/monitor` endpoint can receive webhooks from GitHub, GitLab, Gitea, or other repository providers. Config Server parses changed paths, identifies affected applications, and sends `RefreshRemoteApplicationEvent`.

~~~mermaid
sequenceDiagram
    participant Git as Git provider
    participant Monitor as Config Server /monitor
    participant Bus as Spring Cloud Bus
    participant A as orders-service instance A
    participant B as orders-service instance B

    Git->>Monitor: Signed webhook
    Monitor->>Monitor: Validate signature and changed paths
    Monitor->>Bus: RefreshRemoteApplicationEvent
    Bus-->>A: Deliver refresh event
    Bus-->>B: Deliver refresh event
    A->>A: Reload Environment and audit result
    B->>B: Reload Environment and audit result
~~~

`RefreshRemoteApplicationEvent` is only delivered when Spring Cloud Bus is active on both Config Server and client applications. Webhooks should be verified with signatures or tokens supported by the provider. Config Server can reject requests lacking a valid secret with HTTP 403.

### 9.2. What Metadata Should Propagate Over the Bus?

Refresh events broadcast a signal; they do not replace audit records. Ensure metadata can be correlated:

- Repository provider and repository name.
- Released commit SHA or revision.
- Changed configuration files/paths.
- Target application/label/profile.
- Webhook delivery ID or correlation ID.
- Timestamp when Config Server received the webhook.

If default events do not carry all metadata required by your audit policy, save a record at Config Server before broadcasting and supply a correlation ID so clients record matching outcomes.

### 9.3. Distinguishing Broadcast from Application

Bus confirms a message was dispatched by the messaging layer, not that every replica loaded and applied the revision. Each client must record its own outcome and report status back to the central observability system. You can track:

- `RECEIVED`: instance received the refresh signal.
- `LOADING`: instance is loading configuration.
- `PIPELINE_COMPLETED`: `ContextRefresher` completed.
- `VERIFIED`: health check verified the new configuration works.
- `FAILED`: loading or applying failed.

These statuses are application audit conventions, not mandatory Spring Cloud Bus status names.

## 10. Observing via Spring Boot Actuator

Actuator provides helpful endpoints to inspect current configuration and audit events.

| Endpoint | Data | How to Use |
| --- | --- | --- |
| `/actuator/env` | Properties in Spring Environment | Check property sources and effective values |
| `/actuator/configprops` | `@ConfigurationProperties` beans | Verify bound values |
| `/actuator/health` | Application status and health contributors | Check refresh scope or business health checks |
| `/actuator/auditevents` | Audit events | Query recorded actor, event type, and metadata |
| `/actuator/refresh` | Trigger refresh | Used for legacy/runtime refresh if exposed |

### 10.1. Selective Exposure

Configuration example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - env
          - configprops
          - auditevents
          - refresh
  endpoint:
    env:
      show-values: never
~~~

Only expose the endpoints you need. In production environments, place them on a dedicated management port/network and use Spring Security to require appropriate roles. The `refresh` endpoint can alter runtime state; the `env` endpoint can read or (if POST is enabled) modify properties.

### 10.2. env and configprops Are Not Audit Logs

`/actuator/env` reflects properties in the Environment at query time. `/actuator/configprops` displays data bound into `@ConfigurationProperties`. They are useful for inspecting current state, but they do not store before/after history or which actor caused a change.

Sensitive values in `env` and `configprops` are sanitized by default. Keep this policy in production; do not enable raw values for all users just to debug.

### 10.3. auditevents Requires AuditEventRepository

The `/actuator/auditevents` endpoint requires an `AuditEventRepository` bean. The endpoint returns audit events stored by the repository. If using an in-memory repository, history is lost on process restart and is not aggregated across multiple replicas.

To query complete history, use a durable audit store and include `application`, `instanceId`, `source`, `revision`, and `correlationId` in event data. The Actuator endpoint is an observation interface; it does not automatically detect all configuration changes.

### 10.4. POST /actuator/env

Spring Cloud Context supports POSTing to `/actuator/env` to update the Environment, rebind `@ConfigurationProperties`, and update log levels. This endpoint is only enabled when `management.endpoint.env.post.enabled=true` is configured, and valid keys should also be restricted using `management.endpoint.env.post.valid-keys-regex`.

If enabling this endpoint, control write permissions, restrict allowed keys, and audit requests. If audits are only recorded in a service wrapper calling `ContextRefresher`, direct updates via the `env` endpoint could bypass that wrapper. Choose a single fully observable update path or add listeners/auditing to every write path.

## 11. Protecting Audits and Configuration Data

Audit logs are typically retained longer than regular application logs. If raw configuration values are logged, the audit store can become a credential leak vector.

### 11.1. Record Only What Is Needed

Prefer recording:

- Changed key names.
- Source name or publisher.
- Revision/label/version.
- Actor, application, profile, instance, and correlation ID.
- Outcome, failure type, and duration.

Only record before/after values for approved non-sensitive keys. For secrets, record the secret version ID or rotation state; never record the secret value.

### 11.2. Authorization and Endpoint Protection

- Only authorized operators or deployment identities may trigger refresh.
- Verify webhook signatures before Config Server emits refresh signals.
- Protect `refresh`, `env`, `configprops`, and `auditevents` with appropriate roles.
- Do not expose all Actuator endpoints publicly without necessity.
- Use TLS between the control plane, Config Server, and clients.
- Restrict retention and access permissions on the audit store.

### 11.3. Audit Integrity

If audits serve change-control compliance, prevent unauthorized modification or deletion. You can use append-only storage, dedicated database permissions, an event store, or forward logs to a centralized system with retention policies. Also record the authenticated actor and correlation ID to investigate sequences of actions.

An audit record does not prove a value was applied successfully. It only proves the system recorded a specific state. Cross-reference audit events with each instance's health and runtime state.

## 12. Logs, Metrics, and Tracing

Audit events store business/control history. Logs provide technical context, metrics show trends, and tracing links requests or refresh operations across services.

### 12.1. Structured Logs

A log record should have stable fields:

~~~json
{
  "event": "config.refresh.completed",
  "timestamp": "2026-11-18T13:20:15Z",
  "application": "orders-service",
  "instanceId": "orders-7f9c",
  "source": "spring-cloud-config",
  "revision": "a41c8d2",
  "correlationId": "cfg-req-8241",
  "changedKeyCount": 2,
  "outcome": "PIPELINE_COMPLETED",
  "durationMs": 438
}
~~~

This is an illustrative log structure. Do not put secret values or entire property maps into the record.

### 12.2. Low-Cardinality Metrics

You can track metrics such as:

| Metric | Meaning |
| --- | --- |
| `config.refresh.requests` | Number of refresh requests |
| `config.refresh.completed` | Number of completed pipelines |
| `config.refresh.failed` | Number of failed pipelines |
| `config.refresh.duration` | Refresh processing duration |
| `config.refresh.changed.keys` | Number of changed keys per refresh |
| `config.refresh.verification.failed` | Number of failed health/verification checks |

Metric tags should only use small, stable value sets such as application, environment, or outcome. Never use actor ID, commit SHA, correlation ID, or individual property names as metric tags, as that causes very high cardinality. Those detailed values belong in audits/logs/traces.

### 12.3. Correlation ID Across Components

A correlation ID should be generated where the change request is received or taken from a verified webhook delivery ID. Propagate it through:

1. API gateway/control plane.
2. Config Server and webhook monitor.
3. Spring Cloud Bus message or refresh request.
4. Client audit service and event listeners.
5. Logs/traces and health verification results.

If an instance does not receive the correlation ID, you can still correlate via revision, application, and time window, though investigations will be less precise.

## 13. Testing Configuration Change Recording

Audit services should be tested with a fake configuration source, a fixed clock, and a mocked repository. You do not need to run Config Server or a message broker to verify audit record creation logic.

### 13.1. Testing a Successful Refresh

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import org.mockito.ArgumentCaptor;

class AuditedConfigurationRefresherTests {

    @Test
    void recordsSourceRevisionChangedKeysAndBeforeAfterValues() {
        ContextRefresher refresher = mock(ContextRefresher.class);
        AuditEventRepository auditEvents = mock(AuditEventRepository.class);
        MockEnvironment environment = new MockEnvironment();
        environment.setProperty("spring.application.name", "orders-service");
        environment.setActiveProfiles("staging");
        environment.setProperty("feature.checkout.enabled", "false");
        environment.setProperty("limits.pool-size", "8");

        when(refresher.refresh()).thenAnswer(invocation -> {
            environment.setProperty("feature.checkout.enabled", "true");
            environment.setProperty("limits.pool-size", "12");
            return Set.of(
                    "feature.checkout.enabled",
                    "limits.pool-size");
        });

        Instant fixedTime = Instant.parse("2026-11-18T13:20:15Z");
        Clock clock = Clock.fixed(fixedTime, ZoneOffset.UTC);

        AuditedConfigurationRefresher service =
                new AuditedConfigurationRefresher(
                        refresher, auditEvents, environment, clock);

        Set<String> changedKeys = service.refresh(
                "deploy-bot",
                "spring-cloud-config",
                "a41c8d2",
                "cfg-req-8241");

        assertThat(changedKeys)
                .containsExactlyInAnyOrder(
                        "feature.checkout.enabled",
                        "limits.pool-size");

        ArgumentCaptor<AuditEvent> captor =
                ArgumentCaptor.forClass(AuditEvent.class);
        verify(auditEvents).add(captor.capture());

        AuditEvent event = captor.getValue();
        assertThat(event.getType())
                .isEqualTo("CONFIG_REFRESH_PIPELINE_COMPLETED");
        assertThat(event.getPrincipal()).isEqualTo("deploy-bot");
        assertThat(event.getTimestamp()).isEqualTo(fixedTime);
        assertThat(event.getData())
                .containsEntry("source", "spring-cloud-config")
                .containsEntry("revision", "a41c8d2")
                .containsEntry("correlationId", "cfg-req-8241")
                .containsEntry("outcome", "PIPELINE_COMPLETED");
        assertThat((java.util.Map<?, ?>) event.getData().get("before"))
                .containsEntry("feature.checkout.enabled", "false");
        assertThat((java.util.Map<?, ?>) event.getData().get("after"))
                .containsEntry("feature.checkout.enabled", "true");
    }
}
~~~

This test verifies actor, source, revision, correlation ID, timestamp, changed keys, and before/after snapshots. A fixed clock keeps assertions independent of when the test actually runs.

### 13.2. Testing a Failed or Partial Refresh

Add a test to the same class:

~~~java
@Test
void recordsFailureWhenRefreshThrows() {
    ContextRefresher refresher = mock(ContextRefresher.class);
    AuditEventRepository auditEvents = mock(AuditEventRepository.class);
    MockEnvironment environment = new MockEnvironment();
    environment.setProperty("spring.application.name", "orders-service");

    when(refresher.refresh())
            .thenThrow(new IllegalStateException("controlled refresh failure"));

    Clock clock = Clock.fixed(
            Instant.parse("2026-11-18T13:20:15Z"),
            ZoneOffset.UTC);

    AuditedConfigurationRefresher service =
            new AuditedConfigurationRefresher(
                    refresher, auditEvents, environment, clock);

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> service.refresh(
                    "deploy-bot",
                    "spring-cloud-config",
                    "a41c8d2",
                    "cfg-req-8242"))
            .isInstanceOf(IllegalStateException.class);

    ArgumentCaptor<AuditEvent> captor =
            ArgumentCaptor.forClass(AuditEvent.class);
    verify(auditEvents).add(captor.capture());

    assertThat(captor.getValue().getType())
            .isEqualTo("CONFIG_REFRESH_PIPELINE_FAILED");
    assertThat(captor.getValue().getData())
            .containsEntry("outcome", "FAILED_OR_PARTIAL")
            .containsEntry(
                    "failureType",
                    IllegalStateException.class.getName());
}
~~~

The failure test verifies that the service records an audit event and rethrows the exception to the caller. In a deeper integration test, mutate the Environment before throwing the exception to test the `FAILED_OR_PARTIAL` state and observed changed keys list.

### 13.3. Testing Events and Health

Beyond the service wrapper, test listeners with `EnvironmentChangeEvent` and `RefreshScopeRefreshedEvent` to verify keys and bean names are recorded. Use a test context containing a `@RefreshScope` bean, change a property, trigger refresh, then access the bean to confirm the new target is actually instantiated.

If the application has health indicators, also test:

- Refresh scope is healthy after the bean recreates successfully.
- Refresh scope turns `DOWN` when the new bean fails to initialize or rebind.
- The audit pipeline can complete while the subsequent health verification step fails.

## 14. Troubleshooting

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `EnvironmentChangeEvent` fires without an actor | Default events do not carry a principal | Record actor at control plane and propagate correlation ID |
| Changed keys are empty | Revision did not change, source did not reload, or effective values stayed identical | Check source revision and property source ordering |
| Property source name does not show Git commit | Source name only identifies the source, not revision | Record commit SHA/label separately from Config Server |
| Environment changed yet bean did not change | Bean was not rebound or is not in refresh scope | Check `@ConfigurationProperties`, `@RefreshScope`, and constructor-binding limitations |
| `RefreshScopeRefreshedEvent` fires yet new bean fails | Event only reports cache invalidation | Check next access, bean initialization logs, and refresh health |
| `/auditevents` has no data | Missing `AuditEventRepository` or repository is not storing events | Check bean, implementation, and exposure configuration |
| Audits lost after restart | Using an in-memory repository | Switch to a durable audit store |
| Some replicas did not refresh | Bus inactive on server/client, or message never reached instance | Check broker, Bus health, destination, and correlation ID |
| Webhook did not trigger refresh | Wrong secret/signature or Config Monitor not enabled | Check webhook validation and `spring-cloud-config-monitor` dependency |
| `/env` or `/configprops` shows only `******` | Sanitization is active | This is the data-protection default; do not enable raw values for everyone |
| Refresh happened yet audit service recorded nothing | Another update path bypassed the wrapper | Control `/refresh`, POST `/env`, and other triggers |
| Duplicate audit events | Multiple triggers or retried refreshes | Use event ID/correlation ID and idempotent handling in the audit store |

### 14.1. Change Investigation Workflow

1. Locate the source revision and actor in Git/configuration control plane.
2. Locate the webhook or refresh request by correlation ID.
3. Identify the target application, profile, and instances.
4. Check whether clients received the refresh signal.
5. Check `EnvironmentChangeEvent` and changed keys.
6. Check which property source is providing the key.
7. Check whether `@ConfigurationProperties` rebound and refresh scope was invalidated.
8. Check new bean instantiation and refresh health.
9. Cross-reference audit events, logs, metrics, and verification results.

## 15. Practice Exercises

### Exercise 1 — Recording Environment Change Events

Write a listener for `EnvironmentChangeEvent`. Log the UTC timestamp and changed keys without logging property values.

### Exercise 2 — Distinguishing Invalidation from Recreation

Create a `@RefreshScope` bean, trigger a refresh, and observe `RefreshScopeRefreshedEvent`. Verify the new bean is only created when the proxy is next invoked.

### Exercise 3 — Auditing a Refresh

Build `AuditedConfigurationRefresher` using `ContextRefresher`, `AuditEventRepository`, and `Clock.fixed`. Record actor, source, revision, correlation ID, and changed keys.

### Exercise 4 — Recording Partial Outcomes

Simulate the Environment changing while a refresh-scope bean fails during initialization. Distinguish pipeline completion from health verification and record an appropriate audit status.

### Exercise 5 — Propagating to Multiple Replicas

Set up Config Monitor and Spring Cloud Bus in a test environment. Send a simulated webhook, verify clients receive the event, and record per-instance outcomes.

### Exercise 6 — Protecting Data

Add a secret property to a configuration source. Verify that logs/audits record only the key and source metadata, never the secret value.

**Completion criteria:** you can trace a change from the configuration source down to each instance, know which keys changed, when events were processed, whether the refresh pipeline completed, and whether beans/health were verified.

## 16. Summary

Spring Cloud Context publishes `EnvironmentChangeEvent` with changed keys and `RefreshScopeRefreshedEvent` when refresh scope caches are invalidated. These events are helpful runtime signals, but they do not carry complete actor, source revision, correlation ID, or bean verification results.

For complete traceability, combine auditing at the publishing source with auditing on each client. An orchestration service can wrap `ContextRefresher.refresh()`, take safe before/after snapshots, record `AuditEvent`s via `AuditEventRepository`, and separate pipeline completion from health verification. Spring Cloud Bus broadcasts refresh signals; Config Monitor receives webhooks and must validate signatures. Actuator `env`, `configprops`, `health`, and `auditevents` assist in inspecting current state and stored history.

Audits should record only metadata and allowlisted values. Never dump the Environment or secrets into logs. In multi-replica systems, store outcomes separately per application/instance and link all records using source revision and correlation ID.

## References

- [Spring Cloud Commons 5.0.4 — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebinding, refresh scope, health indicators, and refresh endpoints.
- [Spring Cloud Config 5.0.6 — Push Notifications and Spring Cloud Bus](https://docs.spring.io/spring-cloud-config/reference/server/push-notifications-and-bus.html): Config Monitor, webhooks, `RefreshRemoteApplicationEvent`, and webhook signature validation.
- [Spring Boot 4.1.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`, `configprops`, `auditevents`, endpoint security, and sanitization.
- [AuditEventRepository API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html): contract for storing and querying audit events.
- [AuditEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEvent.html): timestamp, principal, event type, and event data.
- [ContextRefresher source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/refresh/ContextRefresher.java): how Environment refreshes, computing changed keys, publishing `EnvironmentChangeEvent`, and refreshing scope.
- [EnvironmentChangeEvent source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/environment/EnvironmentChangeEvent.java): key set data provided by the event.
- [RefreshScope source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/context/scope/refresh/RefreshScope.java): when `RefreshScopeRefreshedEvent` is published upon cache invalidation.

Verify behavior against your actual Spring Cloud release train and Spring Boot version. Config Data, legacy bootstrap, Bus, and Actuator can differ across release generations.
