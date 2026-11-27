# Recording Administrative Action History Without Leaking Secrets

This lesson belongs to the **Security** chapter of the **SPRING_CLOUD_CORE** module. In a Spring Cloud system, operators can refresh configuration, change service registration status, update the Environment, broadcast refresh commands over Spring Cloud Bus, or adjust Actuator management endpoints. These operations can affect multiple service instances simultaneously, so the system must record who performed them, which action was requested, which resource was impacted, and the final outcome.

An audit trail must provide sufficient evidence for investigation and traceability, yet must never become a secondary secret store. Never record access tokens, passwords, cookies, API keys, private keys, secret configuration values, raw request payloads, or exception messages that may contain sensitive data. The safe design is emitting events under a controlled schema, placing only approved fields into audit data, persisting them in durable storage with dedicated access control, and testing that sensitive data is excluded.

Spring Boot Actuator provides an audit foundation via `AuditEventRepository` and `AuditApplicationEvent`. Spring Security can emit authentication and authorization denial events. Spring Cloud-specific administrative operations still need explicit instrumentation at the execution boundary. This lesson combines those components with examples of configuration refresh, service registry status changes, and endpoint governance.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain why administrative operations require a dedicated audit trail.
2. Distinguish audit events, application logs, traces, and metrics.
3. Design an event schema containing actor, action, resource, outcome, timestamp, and correlation ID.
4. Distinguish operations that are requested, authorized, succeeded, and failed.
5. Use `AuditEventRepository` and `AuditApplicationEvent` to record events.
6. Understand which security events Spring Boot Actuator can record automatically.
7. Audit refresh operations, service registry changes, and Environment updates.
8. Design allowlists for audit data and strip secrets before serialization.
9. Avoid recording raw HTTP headers, request bodies, query strings, and exception messages.
10. Choose durable audit storage over an in-memory repository for production.
11. Protect `/actuator/auditevents` and other management endpoints.
12. Preserve integrity, traceability, and retention limits for audit records.
13. Test audit events for success, failure, permission denial, and sensitive data exclusion.
14. Diagnose issues when an operation ran yet no audit record was saved.

## 2. Why Must Administrative Operations Be Audited?

### 2.1. A Single Operation Can Impact Many Services

In distributed environments, administrative operations often have a wide blast radius:

| Operation | Possible Impact |
| --- | --- |
| `POST /actuator/refresh` | Refreshes `@RefreshScope` beans within an instance. |
| `POST /actuator/busrefresh` | Broadcasts refresh requests to instances participating in Spring Cloud Bus. |
| `POST /actuator/env` | Modifies part of the Environment and may rebind configuration properties. |
| `POST /actuator/busenv` | Updates the Environment across multiple instances via Bus. |
| `POST /actuator/serviceregistry` | Alters the instance's current registration status. |
| Security policy changes | May grant or revoke administrative permissions. |
| Credential rotation | May affect connectivity across multiple services and external systems. |

If a misconfiguration takes down a service, technical logs may show exceptions without fully answering who initiated the change, which channel the request came through, which environment was targeted, and how many instances applied the operation.

### 2.2. Auditing Answers Different Questions from Application Logs

| Data Type | Primary Question | Example |
| --- | --- | --- |
| Audit event | Who performed which administrative action, and with what outcome? | Operator A requested a configuration refresh for orders-service; outcome succeeded. |
| Application log | How did the application process it internally? | Config listener received event and re-initialized beans. |
| Trace | Which services/components did the request traverse and how long did it take? | Admin request traversed gateway, management API, and service instance. |
| Metric | How many times did an event or activity occur? | Count of successful/failed refreshes over a time window. |

Audit events have a stable schema designed for investigation and reconciliation. Application logs can change across code versions and log levels; traces are sampled; metrics are usually aggregated and do not record individual actors. Do not substitute one data type completely for another.

### 2.3. Audit Both Intent and Outcome

An administrative operation should record at least two milestones:

1. **Requested:** the user or automation submitted the request.
2. **Completed/Failed:** the system finished execution and recorded the outcome.

You can add **Authorized/Denied** milestones when distinguishing requests blocked by policy from permitted requests. For asynchronous or Bus-driven operations, also record **Accepted/Dispatched** and per-instance **Applied** states.

~~~mermaid
sequenceDiagram
    actor Admin as Administrator
    participant API as Management endpoint
    participant Audit as Audit service
    participant Op as Spring Cloud operation
    participant Store as Durable audit store

    Admin->>API: POST management action
    API->>Audit: Record REQUESTED
    Audit->>Store: Append request event
    API->>Op: Execute operation
    alt Operation succeeds
        Op-->>API: Success result
        API->>Audit: Record SUCCEEDED
        Audit->>Store: Append completion event
        API-->>Admin: 2xx response
    else Operation fails
        Op-->>API: Failure
        API->>Audit: Record FAILED
        Audit->>Store: Append failure event
        API-->>Admin: Error response
    end
~~~

Recording an event only after returning HTTP 200 can miss accepted requests if the process crashes before completion. Recording an event only before execution does not prove the operation succeeded. Use a shared event ID or correlation ID to link milestones belonging to the same request.

## 3. Designing Audit Events

### 3.1. Fields to Include

An administrative event needs enough context to answer who, what, where, when, and what outcome.

| Field | Purpose | Example |
| --- | --- | --- |
| `eventId` | Unique identifier of the record. | UUID. |
| `timestamp` | Time the event was recorded, in UTC. | `2026-11-18T12:30:15Z`. |
| `principal` | Authenticated identity performing the operation. | `user:alice` or `service:release-bot`. |
| `actorType` | Distinguishes human users, service accounts, or automation. | `HUMAN`, `SERVICE_ACCOUNT`. |
| `type` | Stable event type for filtering and reporting. | `ADMIN_CONFIG_REFRESH_SUCCEEDED`. |
| `action` | Business-level operation name. | `CONFIG_REFRESH`. |
| `resource` | Affected resource. | `application:orders-service`. |
| `environment` | Target environment. | `production`. |
| `outcome` | Operation outcome. | `REQUESTED`, `SUCCESS`, `FAILURE`, `DENIED`. |
| `requestId` | Links the event to the originating request. | Request ID from gateway. |
| `traceId` | Links to distributed trace if available. | Trace ID generated by tracing infrastructure. |
| `source` | Originating channel. | `ACTUATOR_HTTP`, `AUTOMATION`, `BUS`. |
| `reasonCode` | Standardized reason code. | `REGISTRY_UNAVAILABLE`. |
| `changeSummary` | Summary of approved changes. | List of safe property keys. |

Spring Boot's `AuditEvent` already provides foundational fields such as timestamp, principal, type, and data. Remaining fields can live in the data map or in your audit store's dedicated schema.

### 3.2. Use Stable Event Names

Standardize event types and avoid renaming them arbitrarily per Java class:

| Event type | Meaning |
| --- | --- |
| `ADMIN_ACTION_REQUESTED` | An administrative operation was submitted to the system. |
| `ADMIN_ACTION_DENIED` | Request was denied by authorization policy. |
| `ADMIN_CONFIG_REFRESH_SUCCEEDED` | Configuration refresh completed. |
| `ADMIN_CONFIG_REFRESH_FAILED` | Configuration refresh failed. |
| `ADMIN_ENV_PROPERTY_UPDATED` | A property was updated via a management channel. |
| `ADMIN_SERVICE_STATUS_CHANGED` | Registration status was changed. |
| `ADMIN_BUS_REFRESH_DISPATCHED` | Refresh request was broadcast over Bus. |
| `ADMIN_BUS_REFRESH_APPLIED` | An instance applied the refresh. |
| `ADMIN_SECRET_ROTATION_REQUESTED` | Secret rotation workflow was requested. |
| `ADMIN_SECRET_ROTATION_COMPLETED` | Secret rotation workflow completed. |

Domain-specific event types can be added. Each type must define its actor, resource, outcome, and allowed data fields.

### 3.3. Example Safe Record

A record can look like this:

~~~json
{
  "eventId": "7c76c8b2-9a7f-4c83-9b8d-8df0f1d6d5e1",
  "timestamp": "2026-11-18T12:30:15Z",
  "principal": "user:alice",
  "type": "ADMIN_CONFIG_REFRESH_SUCCEEDED",
  "data": {
    "actorType": "HUMAN",
    "action": "CONFIG_REFRESH",
    "resource": "application:orders-service",
    "environment": "production",
    "outcome": "SUCCESS",
    "source": "ACTUATOR_HTTP",
    "requestId": "req-84c12",
    "configRevision": "git:8b7e4a1"
  }
}
~~~

The record contains only identifiers and metadata needed for investigation. It does not store configuration contents, Config Server access tokens, or newly loaded credential values.

### 3.4. Actors Must Come from Verified Identities

Obtain the actor from SecurityContext or a principal verified by the authentication provider. Never trust an arbitrary header such as `X-User` or query parameter `?user=alice` to identify the actor.

For human users, store a stable subject ID issued by the identity provider. For automation, store the authenticated client ID or service account. Never store full JWTs, access tokens, refresh tokens, session cookies, or serialized `Authentication` objects.

If a request has no direct human user, record the system identity that executed the operation, such as `service:config-controller`. Never guess or attribute an end operator without system evidence.

## 4. Critical Rule: Record Only Approved Data

### 4.1. Use Allowlists Instead of Blacklists

Blacklisting tries to detect every sensitive field name. That easily misses new fields like `clientSecretValue`, `privateKeyMaterial`, or non-standard internal names. An allowlist permits only pre-approved fields.

Example allowlist for a refresh operation:

- `action`
- `resource`
- `environment`
- `outcome`
- `requestId`
- `configRevision`
- `changedKeys` if keys are approved

Never insert raw request bodies, Environment maps, entire `@ConfigurationProperties`, or configuration objects into an event.

### 4.2. Data That Must Never Be Recorded

| Data | Handling |
| --- | --- |
| Passwords, passphrases | Never record values. |
| Access tokens, refresh tokens, bearer tokens | Never record tokens or Authorization headers. |
| Cookies, session IDs | Never record cookie/session secrets. |
| API keys, client secrets | Never record values or encrypted forms. |
| Private keys, signing keys | Never record key material. |
| Sensitive property values | Never record before/after values, even encrypted. |
| Raw request/response bodies | Never include in audit records. |
| Full query strings | Record only normalized route/action, omitting query values. |
| Unchecked exception messages | Record reason code and approved exception class. |
| Full Authentication/JWT objects | Record only principal ID and minimal metadata. |

Encrypted values are still sensitive data. Logging ciphertext does not eliminate risk; ciphertext might be decrypted elsewhere or used for correlation attacks.

### 4.3. Property Keys Also Require Review

Property names are generally safer than values, yet not always harmless. Keys can reveal internal service names, topology, vendors, or security functions. Store only allowlisted keys, or record change categories such as `PAYMENT_PROVIDER_SETTINGS` instead of exact property names.

When auditing credential rotation, record `credentialRotation=true` and the general credential category. Do not record secret references if Vault/secret store paths themselves are considered sensitive in your organization.

### 4.4. Do Not Use Simple Hashes Instead of Stripping Secrets

Hashes of passwords or tokens can enable guessing if values have low entropy or come from a bounded space. In audit trails, storing digests of secrets is usually unnecessary. If integrity verification is required, use signatures or HMAC with separately managed keys applied strictly to records already stripped of secrets.

## 5. Spring Boot Actuator Audit Framework

### 5.1. AuditEvent and AuditEventRepository

Spring Boot Actuator provides `AuditEvent` to represent an audit event. An event holds timestamp, principal, type, and data. `AuditEventRepository` is the abstraction for writing and querying events.

Core methods:

~~~java
import java.time.Instant;
import java.util.List;

public interface AuditEventRepository {

    void add(AuditEvent event);

    List<AuditEvent> find(
            String principal,
            Instant after,
            String type
    );
}
~~~

- `add(event)` writes an audit record.
- `find(principal, after, type)` queries records by principal, start time, and event type.
- Filter parameters may be null for broader queries.

Applications can inject the repository to write events directly. Alternatively, publish `AuditApplicationEvent` via Spring's `ApplicationEventPublisher`; audit infrastructure receives the event and forwards it to the repository.

### 5.2. InMemoryAuditEventRepository Is Suitable Only for Development

Spring Boot provides `InMemoryAuditEventRepository` for convenient testing. Because data resides in process memory, it is lost upon application restart and is unsuitable for production audit trails requiring durable traceability.

In production, provide an `AuditEventRepository` implementation writing to durable storage such as a dedicated audit database, secured log pipeline, or append-only storage system. Repository design must satisfy retention, querying by principal/type/time, and independent access control.

### 5.3. AuditApplicationEvent for Custom Events

Example publishing an event with principal, type, and data map:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.audit.listener.AuditApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class AdminAuditPublisher {

    private final ApplicationEventPublisher eventPublisher;

    public AdminAuditPublisher(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void record(
            String principal,
            String eventType,
            String action,
            String resource,
            String outcome,
            String requestId) {

        Map<String, Object> safeData = Map.of(
                "action", action,
                "resource", resource,
                "outcome", outcome,
                "requestId", requestId
        );

        eventPublisher.publishEvent(
                new AuditApplicationEvent(principal, eventType, safeData)
        );
    }
}
~~~

This example puts only selected fields into the map. Never pass request objects, Environment, credentials, or exception messages into `safeData`.

`AuditApplicationEvent` wraps an `AuditEvent` and publishes it through Spring's event mechanism. A repository must be configured to receive and persist events. If the application injects the repository and calls `add()` directly, apply the exact same allowlist and schema.

### 5.4. Recording the Actor from SecurityContext

A helper can extract the principal name from Authentication:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public final class AuditPrincipal {

    private AuditPrincipal() {
    }

    public static String currentActor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return "anonymous";
        }

        return authentication.getName();
    }
}
~~~

Read only `getName()`. Never call `toString()` on Authentication, and never serialize credentials or the entire principal object. For service-to-service calls, ensure Authentication represents the verified service account.

## 6. Security Events Spring Boot Can Record Automatically

### 6.1. Enabling Audit Infrastructure

When Spring Security is present, Spring Boot Actuator can emit audit events for:
- Authentication success.
- Authentication failure.
- Authorization denial.

To enable the audit framework, provide an `AuditEventRepository` bean. Once the repository exists, audit listeners store security events into it.

Development configuration example:

~~~java
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.context.annotation.Bean;

@Bean
AuditEventRepository auditEventRepository() {
    return new InMemoryAuditEventRepository();
}
~~~

This configuration is strictly for development/testing. Replace it with a durable repository in production.

### 6.2. Customizing Authentication and Authorization Audit Listeners

Spring Boot provides `AbstractAuthenticationAuditListener` and `AbstractAuthorizationAuditListener` to customize how security events are converted into audit records. You can extend these listeners to adjust event types or metadata while still enforcing an allowlist.

Never record credential data in failure events. For instance, a `BadCredentialsException` is no reason to store the password the user entered or the login request body.

### 6.3. Spring Security Authentication Events

Spring Security provides `AuthenticationSuccessEvent` and `AuthenticationFailureEvent` subclasses. To handle them directly, configure an appropriate `AuthenticationEventPublisher` and listen with `@EventListener`.

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEventPublisher) {

    return new DefaultAuthenticationEventPublisher(applicationEventPublisher);
}
~~~

Listeners can translate these events into audit events containing principal, authentication type, and outcome. Avoid storing tokens, passwords, credentials, or the full Authentication object.

### 6.4. Authorization Denied Events

Spring Security provides `AuthorizationDeniedEvent` when an authorization decision is denied. An `AuthorizationEventPublisher` is required to publish corresponding events.

Authorization granted events can produce high volume and are not emitted by default in several current Spring Security configurations. Enable them only with clear justification—for example, logging only sensitive administrative permissions rather than every routine authorization decision.

### 6.5. Security Events Do Not Replace Administrative Operation Audits

Authentication success only proves a user authenticated. Authorization denial only proves a request was rejected. Neither proves a refresh command or registry update executed successfully.

For example, an admin logs in successfully and sends POST `/actuator/refresh`. The audit trail needs at least:
- Authentication success event.
- Refresh requested event.
- Refresh outcome event.
- Potentially an access denied event if permissions did not allow it.

Link related events using a request ID or trace ID wherever possible.

## 7. Auditing Spring Cloud Administrative Operations

### 7.1. Configuration Refresh

Spring Cloud Context provides `/actuator/refresh` to refresh context/configuration and invalidate `@RefreshScope` beans. When a refresh can alter application behavior, record actor, application/service ID, environment, config revision, and outcome.

Never record the entire Environment or refreshed property values. When tracking what changed, store only allowlisted property keys or a change-set ID verifiable against the secure config repository.

A service/facade can record events before and after the operation:

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Service;

@Service
public class ConfigurationRefreshService {

    private final RefreshScope refreshScope;
    private final AdminAuditPublisher audit;

    public ConfigurationRefreshService(
            RefreshScope refreshScope,
            AdminAuditPublisher audit) {
        this.refreshScope = refreshScope;
        this.audit = audit;
    }

    public void refresh(
            String actor,
            String application,
            String requestId) {

        audit.record(
                actor,
                "ADMIN_CONFIG_REFRESH_REQUESTED",
                "CONFIG_REFRESH",
                "application:" + application,
                "REQUESTED",
                requestId
        );

        try {
            refreshScope.refreshAll();

            audit.record(
                    actor,
                    "ADMIN_CONFIG_REFRESH_SUCCEEDED",
                    "CONFIG_REFRESH",
                    "application:" + application,
                    "SUCCESS",
                    requestId
            );
        }
        catch (RuntimeException exception) {
            audit.record(
                    actor,
                    "ADMIN_CONFIG_REFRESH_FAILED",
                    "CONFIG_REFRESH",
                    "application:" + application,
                    "FAILURE",
                    requestId
            );
            throw exception;
        }
    }
}
~~~

This example illustrates an application-managed operation service. If using the built-in Actuator endpoint directly, add instrumentation at the HTTP boundary or an equivalent extension mechanism to record requests and outcomes. Do not assume the endpoint emits custom audit events on its own for every refresh.

### 7.2. Changing ServiceRegistry Status

Spring Cloud Commons provides `/actuator/serviceregistry`. GET reads current registration status; POST sends JSON containing a `status` field requesting the provider to change status. Valid values depend on the provider; Eureka typically supports `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`.

Audit events should record:
- Actor and request source.
- Target service ID/instance ID.
- Previous status if readable.
- Requested new status.
- Provider-returned outcome.
- Request ID.

Service status is not a secret, so recording the status value is fine. However, never serialize the entire Registration object since metadata can contain addresses, environment details, or unnecessary internal data.

### 7.3. Updating the Environment via /actuator/env

Spring Cloud Context allows POST `/actuator/env` to update the Environment and rebind configuration properties. This endpoint must be explicitly enabled with `management.endpoint.env.post.enabled=true`; updatable property keys can be restricted with `management.endpoint.env.post.valid-keys-regex`.

Example restricted configuration:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(app\\.feature\\.[a-zA-Z0-9.-]+\\.enabled)$"
~~~

The regex permits only a well-defined group of feature flag properties. Tailor it to your application's actual keys and test rejected keys.

When auditing, record the allowed key and outcome. Never record the request's `value` field, because the same endpoint could update passwords, tokens, endpoint credentials, or secret references. Never log raw JSON bodies.

### 7.4. Spring Cloud Bus Refresh and Bus Environment

`/actuator/busrefresh` broadcasts refreshes to instances over Spring Cloud Bus. `/actuator/busenv` can update key/value pairs across multiple instances. For distributed operations:
- Record an event where the command originates.
- Record a dispatch event when the message is successfully published.
- When rollout verification is needed, record applied/failure events on each instance.
- Use a shared correlation ID or command ID to link results.
- Never record values sent via busenv; record only safe keys or a change-set ID.

A "dispatch succeeded" event proves only that the message was sent to the Bus under its contract. It does not prove every instance applied the change. Separate dispatched and applied states in the audit schema.

## 8. Capturing Events at the Execution Boundary

### 8.1. Prefer Auditing Inside the Service Executing the Action

When the application uses a dedicated service/facade to perform administrative actions, record audits inside that service. This captures:
- Intent prior to execution.
- Actual outcome after execution.
- Normalized resource ID.
- Reason code on failure.
- Applied change-set ID or version.

This is the right place to distinguish a business-level operation success from an HTTP request merely returning a response.

### 8.2. When Using Built-in Actuator Endpoints

If built-in endpoints cannot be replaced with a custom facade, you can record HTTP metadata in a filter/interceptor at the management boundary:
- Track only state-changing methods such as POST.
- Match routes against an allowlist of management endpoints.
- Obtain the actor from SecurityContext.
- Record request ID, normalized route, and timestamp.
- After request completion, record the HTTP outcome.
- Never read/serialize bodies and never log headers/query values.

In the Servlet stack, use a filter; in WebFlux, use the corresponding WebFilter. Filters observe only requests/responses. If an operation executes asynchronously or returns accepted before completion, emit events from the operation handler or consumer to confirm the final outcome.

### 8.3. Distinguishing HTTP Status from Business Outcome

HTTP 2xx may mean a command was accepted or dispatched, not necessarily that all side effects completed. HTTP 4xx can reflect validation or authorization failures; HTTP 5xx can occur after part of an operation already ran.

Record both business outcome and normalized HTTP status where appropriate. Never infer that an HTTP status code is complete proof of system-wide state.

## 9. Preventing Leaks via Logs and Traces

### 9.1. Common Leak Sources

| Source | Risk |
| --- | --- |
| HTTP access logs | Recording URL queries with tokens or POST bodies. |
| Request/response logging filters | Recording Authorization, Cookie, or configuration payloads. |
| Exception logging | Exception messages containing credentialed URIs or property values. |
| Configuration client debug logs | Printing property sources or configuration data. |
| Trace baggage | Propagating secrets in tags/baggage across multiple services. |
| Audit data map | Developer passing raw request or configuration objects into the map. |
| Service metadata | Registration metadata containing unnecessary internal details. |

Securing the audit stream while letting access logs or tracing systems capture the same secrets is still a leak. Redaction policies must apply at every layer that collects data.

### 9.2. Do Not Log Sensitive Headers

Never put these headers into audit data or general logs:
- `Authorization`.
- `Cookie` and `Set-Cookie`.
- API key headers.
- Custom session or credential headers.
- Headers containing sensitive user data unless strictly needed for investigation.

To record client identity, pull the authenticated client ID from the security context instead of copying tokens from headers.

### 9.3. Do Not Log Query Strings or Raw Bodies

A URL like `/actuator/env?token=...` can leak secrets via access logs. Recording the normalized route template `/actuator/env` and HTTP method is enough for audit events.

Request bodies to `/actuator/env` or `/actuator/busenv` can contain configuration values. Do not use a body-caching filter to serialize entire requests into audits. If a change summary is needed, parse at the operation layer and extract only allowlisted keys.

### 9.4. Sanitization Must Happen Before Serialization

Do not rely on masking data in dashboards after raw events are already written to a database. Filter data before constructing `AuditEvent` or before the repository persists the record.

An allowlist policy should:
1. Identify the event type.
2. Select valid fields for that event type.
3. Validate data types and lengths.
4. Normalize strings, strip control characters, and enforce size limits.
5. Drop any fields outside the schema.
6. Only then serialize and persist.

Never pass arbitrary objects into the audit map. Use dedicated DTOs/schemas per operation type when structured data is complex.

## 10. Durable Audit Storage

### 10.1. Production Repositories

`AuditEventRepository` only defines the add/find contract; durable storage is supplied by the application. A production repository can convert events into immutable records and append them to an audit store:

~~~java
public final class PersistentAuditEventRepository
        implements AuditEventRepository {

    private final AuditRecordStore store;

    public PersistentAuditEventRepository(AuditRecordStore store) {
        this.store = store;
    }

    @Override
    public void add(AuditEvent event) {
        AuditRecord record = AuditRecord.fromAllowlistedEvent(event);
        store.append(record);
    }

    @Override
    public List<AuditEvent> find(
            String principal,
            Instant after,
            String type) {

        return store.find(principal, after, type)
                .stream()
                .map(AuditRecord::toAuditEvent)
                .toList();
    }
}
~~~

`AuditRecordStore` and `AuditRecord` in this example are application-defined abstractions, not built-in Spring Boot classes. The key point is converting via an allowlist before writing to the store.

### 10.2. Append-Only Semantics and Access Control

Audit records should be appended, preventing business applications from modifying or deleting existing records. Consider:
- Separating the audit store from the business database.
- Using an append-only identity for the audit-writing service.
- Granting dedicated read access to investigation/audit teams.
- Restricting delete/update permissions at the storage layer.
- Enabling encryption at rest and controlled backups.
- Using immutable/WORM storage or tamper-evident mechanisms when compliance requires them.
- Auditing read/export operations on audit data when data is sensitive.
- Never storing signing keys or HMAC keys alongside the records they protect.

Hash chains or digital signatures help detect tampering, yet cannot protect records if an attacker has permissions to modify both data and keys. Separation of duties and key management are prerequisites.

### 10.3. Retention and Privacy

Do not retain audit data indefinitely unless policy requires it. Define:
- Retention periods per event type.
- Controlled archival and purge workflows.
- Role-based read access.
- Handling of personal identifiers under privacy policies.
- Preserving investigability when user accounts are deleted or renamed.

Prefer stable subject IDs and store only minimal necessary personal data. Never record emails, phone numbers, or IP addresses without a clear purpose and policy.

### 10.4. Time Synchronization and Correlation

Use UTC timestamps and synchronize clocks across services/hosts. Store request IDs or command IDs to correlate events across instances. When using trace IDs, ensure tracing contexts contain no secrets and IDs remain intact across hops.

## 11. Ensuring Audit Records Are Not Lost

### 11.1. Recording Before and After Operations

For critical operations, record the request event before execution and the outcome event upon completion. If the audit store is unavailable, define an explicit policy:
- For high-risk privileged actions, fail closed and refuse execution if durable intent cannot be recorded.
- For lower-risk operations, allow execution while raising alerts and retrying audit persistence.
- Never silently drop events when the repository errors.

The fail-closed vs. fail-open decision must be based on impact and operational requirements rather than one blanket rule for all operations.

### 11.2. Outbox or Message Queues

If an operation updates an internal database and requires atomic auditing with that change, consider a transactional outbox: write the business change and audit/outbox row in the same transaction, then relay to the audit store.

If the operation calls a remote registry or publishes a Bus message, no automatic distributed transaction spans all systems. Record the command/request event first, then record outcome or reconciliation events afterward. Use idempotency keys to avoid duplicate records on retry.

### 11.3. Idempotency and Duplicate Events

Message retries or request retries can generate multiple events. Each operation should carry a request/command ID; each event carries its own event ID. Repositories or consumers can use the event ID to prevent duplicate inserts while preserving distinct requested, dispatched, and applied milestones.

Never discard two events simply because principal, action, and timestamp are close; they may be two distinct legitimate operations.

## 12. Protecting Management and Audit Endpoints

### 12.1. Exposure Is Not Authorization

Spring Boot Actuator exposes only the HTTP health endpoint by default in typical configurations. Other endpoints must be explicitly exposed. Adding an endpoint to the exposure list does not grant access to the right admins automatically; Spring Security, management networks, and access policies are still required.

Example exposing only health and audit events:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,auditevents"
~~~

The default path of the audit endpoint is `/actuator/auditevents`. This endpoint requires an `AuditEventRepository` bean.

### 12.2. Only Audit Readers Should Read Audit Events

`auditevents` can return principals, action types, timestamps, and data. This is sensitive information because it reveals who did what in the system. Grant GET only to appropriate audit reader/incident responder roles; never open the endpoint to regular users or the public Internet.

State-changing endpoints such as `refresh`, `env`, `serviceregistry`, and `busrefresh` require separate write permissions. Do not combine audit read permissions with configuration write permissions without justification.

### 12.3. Example SecurityFilterChain for Actuator

General example with Spring Security:

~~~java
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ManagementSecurityConfiguration {

    @Bean
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("auditevents"))
                    .hasRole("AUDIT_READER")
                .requestMatchers(EndpointRequest.to(
                        "refresh", "env", "serviceregistry", "busrefresh", "busenv"))
                    .hasRole("PLATFORM_ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

The actor helper earlier illustrated the Servlet stack, where SecurityContext is typically bound to the request thread. In WebFlux, read Authentication from the reactive security context inside the Reactor chain; never rely on ThreadLocal SecurityContextHolder in reactive code.

This example illustrates a policy for Servlet management endpoints. The `EndpointRequest` import package changed across Spring Boot generations; use the package matching your application's BOM. For WebFlux, configure an equivalent reactive security chain.

With browser sessions, account for CSRF protection on POST operations. For machine-to-machine management APIs, use short-lived/managed credentials, TLS, and network restrictions; never disable CSRF broadly just to make POST endpoints work.

### 12.4. Isolating the Management Network

Where architecture permits:
- Use a separate management port.
- Permit access only from the management network or control plane.
- Never route actuator write endpoints through public ingress.
- Use firewalls/network policies to restrict sources.
- Protect JMX as well if endpoints are exposed over JMX.
- Verify reverse proxies do not inadvertently forward internal endpoints.

## 13. Querying Audit Events

### 13.1. Querying the Endpoint

When a repository bean exists and the endpoint is exposed, you can query:

~~~bash
curl --request GET \
  "http://localhost:8080/actuator/auditevents?principal=user%3Aalice&type=ADMIN_CONFIG_REFRESH_SUCCEEDED"
~~~

The endpoint supports principal, after, and type filters. Example querying events after a UTC timestamp:

~~~text
GET /actuator/auditevents?after=2026-11-18T12:00:00Z&type=ADMIN_SERVICE_STATUS_CHANGED
~~~

The response returns a list of events with timestamp, principal, type, and data. Exact shape depends on Spring Boot version and recorded event schema.

### 13.2. Querying via Repository

If an investigation service is permitted to use the repository directly:

~~~java
List<AuditEvent> events = auditEventRepository.find(
        "user:alice",
        Instant.parse("2026-11-18T12:00:00Z"),
        "ADMIN_CONFIG_REFRESH_SUCCEEDED"
);
~~~

Limit result counts and paginate at the storage layer when the store holds many records. Never load the entire audit history into memory per query.

### 13.3. Controlling Reads and Exports

Reading audit data is itself a sensitive action. Consider auditing:
- Who queried audit events.
- Who exported a time range.
- Who downloaded data out of the system.
- Reason or related incident ticket if required by procedure.

Avoid creating an infinite loop by logging every audit-read event into the exact same query stream; separate audit access logs or use an appropriate pipeline.

## 14. Testing the Audit Trail

### 14.1. Testing Successful Events

When a refresh operation succeeds, verify:
- A REQUESTED event is recorded.
- A SUCCEEDED event is recorded.
- Principal matches Authentication.
- Resource/application is accurate.
- Request ID links the two events.
- No config values or credentials appear in data.

### 14.2. Testing Failures

Simulate the refresh/registry provider throwing an exception. Verify a FAILED event carries a standardized reason code. Never assert or persist raw exception messages if they might contain URLs, tokens, or property values.

### 14.3. Testing Denied Actions

Send a request with a principal lacking administrative roles. Verify:
- Security returns 401/403 per authentication state.
- An authorization-denied audit event is recorded if listeners/repository are configured.
- No SUCCEEDED event is recorded.
- No operation side effects occur.

### 14.4. Testing That Secrets Never Appear

Use a synthetic secret sentinel value in tests:

~~~java
@Test
void auditEventDoesNotContainSecretValue() {
    String secretSentinel = "TEST-ONLY-SECRET-DO-NOT-STORE";

    adminService.updateConfiguration(
            "user:alice",
            "orders-service",
            secretSentinel
    );

    AuditEvent event = recordingRepository.lastEvent();

    assertThat(event.getData())
            .doesNotContainKey("password")
            .doesNotContainKey("token")
            .doesNotContainKey("secret")
            .doesNotContainValue(secretSentinel);
}
~~~

If multiple events are emitted, inspect every recorded event and serialized output. Also search for the sentinel in application logs, HTTP access logs, and trace attributes during test runs.

### 14.5. Testing Repositories and Endpoints

| Test | What to Verify |
| --- | --- |
| Repository add/find | Writes and queries by principal, after, and type. |
| Repository restart | Records survive process restarts. |
| Endpoint exposure | `/actuator/auditevents` is accessible only when exposed. |
| Endpoint authorization | Audit readers can read; regular users are denied. |
| Admin write authorization | Only appropriate admin roles can POST. |
| Refresh success/failure | Both request and outcome events exist. |
| Registry status change | Records new status and target instance without serializing Registration. |
| Bus refresh | Records dispatch and applied results by command ID. |
| Secret redaction | Sentinel never appears in audits, logs, traces, or unintended responses. |
| Audit store unavailable | Fail-closed/fail-open behavior matches policy. |

## 15. Common Pitfalls and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/actuator/auditevents` returns 404. | Missing AuditEventRepository or endpoint not exposed. | Provide repository bean and add `auditevents` to exposure list. |
| Endpoint exists but no events appear. | Security audit listeners disabled or custom events not published. | Check Spring Security publisher, repository, and event publisher. |
| Only authentication events appear, no admin actions. | Application does not emit events for refresh/env/registry operations. | Instrument operation service or management boundary. |
| Audit records lost after restart. | Using InMemoryAuditEventRepository. | Switch to a durable repository in production. |
| Principal is anonymous. | Request lacked valid Authentication or actor read from wrong context. | Check authentication chain and service account identity. |
| Event contains raw token or password. | Developer put raw request/authentication/config object into data map. | Enforce allowlist schema, strip fields, and test with sentinels. |
| FAILED event lacks clear cause. | Recorded outcome without a safe reason code. | Map exceptions to standardized error codes. |
| Exception message leaks secrets. | Stored raw message/stack trace in audit data. | Record only approved exception classes and reason codes. |
| Refresh succeeded but audit shows only REQUESTED. | Process stopped before completion write or repository errored. | Use durable events/outbox, retries, and reconciliation. |
| Bus refresh dispatch succeeded yet instances did not update. | Confused accepted/dispatched with applied. | Emit per-phase events linked by correlation ID. |
| Cannot query older events. | In-memory repository, short retention, or wrong UTC/type query. | Check storage, retention, and query filters. |
| Audit endpoint leaks data to regular users. | Missing authorization or public management port. | Restrict roles, network, and exposure. |
| Duplicate audit events. | Retries created multiple requests/events without idempotency key. | Use event IDs and command IDs to distinguish/deduplicate properly. |
| Unknown which automation performed an action. | Recorded generic system actor. | Assign distinct client IDs/service accounts per automation. |
| Audit record shows spoofed IP. | Trusted client X-Forwarded-For directly. | Accept forwarded headers only from configured trusted proxies. |
| Logs/traces still contain secrets though audits are clean. | Redaction applied only to audit publisher. | Apply redaction policies to access logs, tracing, and exception logging. |

## 16. Operational Principles

1. **Record verifiable actors.** Use authenticated principals or service accounts.
2. **Separate request from outcome.** Never equate accepting a request with completing the operation.
3. **Use a stable schema.** Standardize event types, actions, resources, and outcomes.
4. **Store only allowlisted data.** Never serialize request, Authentication, Environment, or Registration objects.
5. **Do not store encrypted secrets.** Ciphertext is still sensitive data.
6. **Record safe reason codes.** Keep exception messages and raw stack traces out of audit records.
7. **Use durable repositories.** In-memory is strictly for development/testing.
8. **Enforce append-only and separate access.** Business applications must never edit or delete audit history.
9. **Correlate multi-instance events.** Use request IDs, command IDs, or trace IDs.
10. **Distinguish dispatched from applied.** Especially for Spring Cloud Bus.
11. **Protect audit endpoints.** Grant read access only to required roles.
12. **Protect management write endpoints.** Use RBAC, TLS, management networks, and strict policies.
13. **Test redaction.** Use secret sentinels and search across every logging channel.
14. **Set intentional retention.** Keep long enough for investigations while respecting privacy.
15. **Define behavior when the audit store fails.** Choose fail-closed or fail-open based on risk.
16. **Verify against your version.** API packages and Actuator/Security settings may vary across Spring Boot/Spring Security releases.

## 17. Completion Checklist

- [ ] Can explain how audit trails differ from application logs, traces, and metrics.
- [ ] Identified Spring Cloud administrative operations requiring auditing.
- [ ] Designed an event schema with event ID, timestamp, principal, type, resource, outcome, and request ID.
- [ ] Separately recorded requested, denied, succeeded, and failed states.
- [ ] Used AuditEventRepository and AuditApplicationEvent.
- [ ] Understood InMemoryAuditEventRepository is suitable only for development/testing.
- [ ] Provided a durable production repository.
- [ ] Recorded authentication and authorization-denied security events.
- [ ] Created custom events for refresh, env, service registry, and bus operations.
- [ ] Recorded only allowlisted property keys or change-sets.
- [ ] Excluded tokens, passwords, cookies, private keys, and raw configuration values.
- [ ] Excluded raw request bodies, Authorization headers, query strings, and exception messages.
- [ ] Protected /actuator/auditevents with a dedicated role.
- [ ] Protected management write endpoints with least privilege and network restrictions.
- [ ] Established retention, append-only, backup, and integrity policies.
- [ ] Included correlation IDs for distributed operations.
- [ ] Tested success, failure, denied, persistence, and secret redaction cases.
- [ ] Defined behavior when the audit store is unavailable.

**Official Documentation to Cross-Check Against Project Versions:**

- [Spring Boot – Auditing](https://docs.spring.io/spring-boot/reference/actuator/auditing.html): AuditEventRepository, InMemoryAuditEventRepository, security audit listeners, and custom AuditApplicationEvent.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): auditevents endpoint, exposure, access control, and securing management endpoints.
- [Spring Boot – AuditEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEvent.html): principal, timestamp, type, and data.
- [Spring Boot – AuditEventRepository API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html): add/find contract.
- [Spring Boot – AuditApplicationEvent API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/audit/listener/AuditApplicationEvent.html): publishing audit events via ApplicationEventPublisher.
- [Spring Security – Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): AuthenticationSuccessEvent, AuthenticationFailureEvent, and AuthenticationEventPublisher.
- [Spring Security – Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): AuthorizationDeniedEvent and publishing authorization events.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): ServiceRegistry, auto-registration, and the serviceregistry Actuator endpoint.
- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): refresh, env, restart, and management endpoints.
- [Spring Cloud Bus – Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html): busrefresh and busenv.

An audit trail is trustworthy only when events accurately reflect operations, data is filtered before storage, and the audit store is independently secured. Exercise administrative operations in test environments, verify both requests and outcomes across multiple instances, and prove through tests that secret sentinels never appear in any audit record.
