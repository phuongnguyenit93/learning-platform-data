# Dynamic Route Publishing with Validation, Auditing, and Rollback

## 1. Context and Lab Objectives

In a microservices system, **Spring Cloud Gateway (SCG)** routes are often declared statically using YAML or the Java DSL. When a new service arrives, a public path changes, traffic shifts to a new backend, or recovery is needed after an incident, operations teams have to edit configurations, redeploy, or update each Gateway instance. That approach works for some small systems, but it falls short when controlled route changes, auditing, and fast rollbacks are required.

This lab builds a **dynamic route publishing** workflow: an administrator submits a route change request, the Gateway validates input and permissions, persists the desired version, publishes the route into the runtime, writes an audit event, and can roll back to the previous version if errors appear.

We use a WebFlux Gateway in front of Catalog and Orders. Routes can be changed without restarting the application. A publish operation must prove:

- **Right actor:** the actor holds route administration permissions.
- **Right target:** upstream belongs to the approved service list.
- **Right structure:** route ID, path, method, and filters are valid.
- **Traceable:** records who changed what, when, and with what outcome.
- **Recoverable:** retains the previous version's snapshot and knows which route is currently active.
- **Synchronized:** Gateway replicas receive the same desired state and refresh their route caches together.

### Learning Objectives

After completing this lab, you can:

1. Distinguish static routes, in-memory dynamic routes, and dynamic routes backed by a durable data source.
2. Use `RouteDefinitionWriter` to save/delete `RouteDefinition` entries and emit `RefreshRoutesEvent` after changes.
3. Build an admin API with dedicated authentication/authorization for publishing operations.
4. Validate route IDs, paths, methods, service keys, URIs, and filters against an allowlist.
5. Prevent SSRF by never accepting arbitrary upstream URIs from admin requests.
6. Design release candidates, activation, audit records, and pre-update snapshots for routes.
7. Distinguish desired, applied, and observed states across multiple Gateway instances.
8. Roll back by restoring a saved snapshot and refreshing the route cache.
9. Test publishing, validation failures, refresh failures, backend outages, and rollbacks over HTTP.
10. Build a runbook and acceptance criteria for a production route change.

> **Example scope:** This lab uses **Spring Cloud Gateway Server WebFlux**. Configuration namespaces, starters, and some APIs change across Spring Cloud Gateway releases; lock down your Spring Boot/Spring Cloud BOM before deploying. Hostnames, service IDs, actors, and data in this article are lab examples. No operations were executed against a production system.

## 2. Lab Scenario and Business Requirements

Suppose the Gateway receives a public request:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: gateway.lab.example.test
~~~

Current route:

~~~text
catalog-public -> lb://catalog-service
Path=/api/catalog/**
Method=GET
StripPrefix=2
~~~

The Catalog backend receives:

~~~http
GET /items/42 HTTP/1.1
~~~

The operations team needs to switch upstream from `catalog-service` to `catalog-v2-service` in an audited release. If v2 returns errors or latency breaches thresholds, the administrator can roll back to the previous route.

### Lab Constraints

| Requirement | Design decision |
| --- | --- |
| Public route ID | `catalog-public`, stable across releases |
| Public path | `/api/catalog/**` |
| Allowed methods | `GET`, `HEAD` |
| Upstream | Selected via an allowlisted service key |
| Filters | Only `StripPrefix=2` permitted in the lab |
| Route priority | Order value set by the server, never accepted from the client |
| Route release | Create candidate, validate, activate |
| Audit | Record actor, release ID, route ID, before/after, and outcome |
| Rollback | Restore the most recent active snapshot |
| Cluster | Single source of truth, every Gateway instance refreshes the same version |

**Do not allow the admin API to accept arbitrary URIs.** If a request could pass `http://169.254.169.254`, `http://127.0.0.1`, an internal IP address, or an arbitrary hostname as upstream, the route management feature becomes an SSRF vector. Operators authorized to publish routes may only choose services approved by the platform owner.

## 3. Route Publishing Architecture

~~~mermaid
flowchart TD
    A["Operator / Release pipeline"] -->|"JWT + change request"| M["Private Route Admin API"]
    M --> S["Authentication + route-admin authorization"]
    S --> V["Validate schema, allowlist, overlap, filters"]
    V -->|"Invalid"| X["Reject + audit failure"]
    V -->|"Valid"| C["Create immutable candidate"]
    C --> R["Review / approval gate"]
    R -->|"Approved"| P["Publish desired route version"]
    P --> DB[("Durable route store + audit log")]
    P --> E["Refresh notification"]
    E --> G1["Gateway Pod A: reload + refresh"]
    E --> G2["Gateway Pod B: reload + refresh"]
    E --> G3["Gateway Pod N: reload + refresh"]
    G1 --> H["Health / route version observations"]
    G2 --> H
    G3 --> H
    H -->|"Failure / rollback request"| RB["Restore previous snapshot"]
    RB --> DB
    RB --> E
~~~

The architecture separates three kinds of data:

1. **Release candidate:** a proposed change not yet serving traffic. It carries an ID, creator, content, and validation result.
2. **Desired route state:** the approved route version persisted durably. This is the canonical source for Gateway instances to reload.
3. **Observed/applied state:** the version each Gateway instance has loaded and is actively using. It may lag behind desired state during a refresh or when a Pod encounters an error.

If you only update routes inside an `InMemoryRouteDefinitionRepository`, routes can be lost on restart and different Pods may hold diverging configurations. A small lab can use an in-memory repository to learn the API; production needs a **durable source of truth** and a mechanism to distribute changes to all replicas.

## 4. RouteDefinition and the Gateway Refresh Mechanism

Spring Cloud Gateway models routes using `RouteDefinition`. A route has:

- `id`: a stable identifier.
- `uri`: an upstream URI or service URI such as `lb://catalog-service`.
- `predicates`: request matching conditions.
- `filters`: request/response transformations.
- `order`: route priority order.
- additional metadata if required by the application.

Key APIs in Gateway Server WebFlux:

| API | Role |
| --- | --- |
| `RouteDefinitionWriter` | Saves or deletes a route definition |
| `RouteDefinitionLocator` | Reads route definitions from configuration sources/repositories |
| `RouteDefinitionRepository` | Combines reading and writing route definitions |
| `RouteDefinitionRouteLocator` | Converts a RouteDefinition into a runtime Route |
| `RefreshRoutesEvent` | Notifies the Gateway to reload routes |
| `RouteLocator` | Supplies runtime routes for request routing |

`RouteDefinitionWriter.save(...)` **must not be assumed to guarantee that every instance is already serving requests with the new route**. After saving successfully, the application needs to publish the appropriate refresh event and observe the outcome on each instance.

Conceptual API flow example:

~~~java
routeDefinitionWriter.save(Mono.just(route))
    .then(Mono.fromRunnable(() ->
        eventPublisher.publishEvent(new RefreshRoutesEvent(this))));
~~~

This suits a single application or lab. In a cluster, an in-JVM event reaches only listeners inside that JVM; it **does not automatically broadcast to other Pods**. You need an event bus/message broker, versioned polling, or a dedicated refresh coordination mechanism.

### Route Definitions Are Not Running Route Objects

`RouteDefinition` is input configuration. The Gateway converts it into a runtime `Route` and instantiates its predicates/filters. Therefore:

- Saving a route definition does not mean runtime predicates/filters compiled cleanly.
- Parsing a URI does not mean DNS, service discovery, or the backend is healthy.
- Publishing a refresh event does not mean every Pod received and applied the event.
- An admin API returning 202/200 does not replace checking observed state.

## 5. Designing the Release Lifecycle

A route release should have an explicit state machine:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Validated: validation passed
    Draft --> Rejected: validation failed
    Validated --> Approved: authorized approval
    Validated --> Rejected: approval denied
    Approved --> Publishing: activate
    Publishing --> Active: all required instances applied
    Publishing --> Degraded: one or more instances failed
    Degraded --> Active: retry / convergence
    Degraded --> RolledBack: restore previous version
    Active --> RolledBack: rollback request
    Rejected --> [*]
    RolledBack --> [*]
    Active --> [*]
~~~

### States to Distinguish

| State | Meaning | Serving traffic? |
| --- | --- | --- |
| `DRAFT` | Proposed change under editing | No |
| `VALIDATED` | Schema/policy/route conflicts passed checks | No |
| `APPROVED` | Required approvals granted | Not yet |
| `PUBLISHING` | Desired state written and refresh in progress | Depends on instance |
| `ACTIVE` | Required instances confirmed the version | Yes |
| `DEGRADED` | Not enough replicas converged or observation errors occurred | Possibly partial |
| `REJECTED` | Candidate was rejected | No |
| `ROLLED_BACK` | Restored the previous version | Previous version is served |

In this lab, we follow a streamlined flow: **create candidate → validate → approve → activate → verify → rollback**. Production may require dual-person approval, maintenance windows, canaries, change tickets, and tenant/region scoping.

## 6. Preparing the Practice Environment

### Required Components

| Component | Role | Lab example |
| --- | --- | --- |
| WebFlux Gateway | Receives requests and applies routes | Port 8080 |
| Catalog v1 | Current backend | `catalog-service` |
| Catalog v2 | Target backend after release | `catalog-v2-service` |
| Route Admin API | Creates candidates, validates, activates, rolls back | Accessible only on admin network |
| Route store | Stores candidates, desired state, and snapshots | In-memory in lab; DB in production |
| Audit store | Stores immutable change history | Append-only DB or audit platform |
| Operator client | Sends admin requests with credentials | curl/Postman/test client |

### Suggested Dependencies

The application uses compatible Spring Boot and Spring Cloud BOMs, with Gateway Server WebFlux, OAuth2 Resource Server for the admin API, and Actuator for health/metrics if needed:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Older Gateway releases may name the starter `spring-cloud-starter-gateway`. Use only the starter matching your chosen runtime. This lab does not assume one specific version; verify the Java APIs below against your project's BOM.

### Lab Topology

~~~mermaid
flowchart LR
    OP["Operator"] -->|8080 / private admin| GW["Gateway"]
    CL["Test client"] -->|8080 /api/catalog/**| GW
    GW -->|"lb://catalog-service"| V1["Catalog v1"]
    GW -->|"lb://catalog-v2-service"| V2["Catalog v2"]
    GW -->|"lb://orders-service"| ORD["Orders"]
    GW --> STORE[("Route store")]
    GW --> AUDIT[("Audit log")]
~~~

If the lab lacks service discovery, replace `lb://...` with preconfigured loopback/HTTP stub URIs. In production, `lb://` requires Spring Cloud LoadBalancer and an appropriate service instance supplier; do not assume DNS/Kubernetes Services automatically supply `ServiceInstance` objects to LoadBalancer.

## 7. Admin API Contract

The Admin API does not accept a raw `RouteDefinition` from the client. Instead, it accepts a **small command DTO**, and the server constructs the route from approved policies.

### 7.1. Endpoints in the Lab

| Method | Endpoint | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/internal/admin/route-releases` | `gateway.routes.write` | Create candidate |
| `GET` | `/internal/admin/route-releases/{releaseId}` | `gateway.routes.read` | View candidate status |
| `POST` | `/internal/admin/route-releases/{releaseId}/validate` | `gateway.routes.write` | Run validation |
| `POST` | `/internal/admin/route-releases/{releaseId}/approve` | `gateway.routes.approve` | Approve |
| `POST` | `/internal/admin/route-releases/{releaseId}/activate` | `gateway.routes.publish` | Write desired state and refresh |
| `POST` | `/internal/admin/route-releases/{releaseId}/rollback` | `gateway.routes.rollback` | Restore snapshot |
| `GET` | `/internal/admin/routes/{routeId}/status` | `gateway.routes.read` | Desired/observed version |

Separating **write**, **approve**, **publish**, and **rollback** permissions enforces separation of duties. For small systems, one role may hold multiple scopes; for sensitive systems, the candidate creator should not self-approve and self-publish their own change.

### 7.2. Request DTO

Example candidate creation:

~~~http
POST /internal/admin/route-releases HTTP/1.1
Authorization: Bearer <operator-token>
Content-Type: application/json
Idempotency-Key: change-2026-042

{
  "routeKey": "catalog-public",
  "serviceKey": "catalog-v2",
  "publicPrefix": "/api/catalog",
  "methods": ["GET", "HEAD"],
  "changeTicket": "CHG-2026-042",
  "reason": "Switch Catalog traffic to backend v2"
}
~~~

Sample response:

~~~json
{
  "releaseId": "rel-01JCATALOGV2",
  "routeKey": "catalog-public",
  "state": "DRAFT",
  "validation": "PENDING"
}
~~~

The client only picks `serviceKey` and declares policy-permitted properties. The server maps the service key to an upstream URI and applies fixed filters/order. Never accept arbitrary `uri`, `filters`, `order`, or `metadata` fields in the public DTO.

### 7.3. Idempotency and Optimistic Concurrency

A publish command may be retried by the client due to a timeout even though the Gateway already committed the desired state. You need:

- An `Idempotency-Key` or unique release ID so retrying a command does not create two releases.
- `expectedVersion`/ETag to prevent two administrators from overwriting a route concurrently.
- Mandatory `changeTicket` and `reason` for auditing.
- A release can activate only once; retries must return the existing state.
- Rollback must verify the current active version matches the version expected by the rollback command.

Without concurrency control, two changes A and B can collide: A reads version 5, B reads version 5, A publishes version 6, and B overwrites with version 7 based on the stale snapshot, silently losing A's change.

## 8. Securing the Route Admin API

The Admin API can alter traffic across the entire system, so it must be treated as a **control plane**. Never expose this endpoint to the Internet like a regular business API.

### 8.1. WebFlux Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class RouteAdminSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/internal/admin/**")
                            .hasAuthority("SCOPE_gateway.routes.write")
                        .pathMatchers("/actuator/health")
                            .permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Use only when the control plane is stateless Bearer-only.
                // If admins use browser cookies/sessions, retain proper CSRF protection.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

This is a minimal configuration for illustration. In real deployments, do not use a single `write` scope for all endpoints once read/approve/publish/rollback permissions are separated. Combine method/path matchers, reactive method security, or a policy service to enforce specific scopes.

### 8.2. Additional Protective Layers

- Place the admin listener on a management/private network or dedicated ingress.
- Validate issuer, audience, signature, expiration, and scopes of the operator token.
- Use mTLS/service identity between the release pipeline and the admin API when appropriate.
- Enforce IP/network policies, rate limits, and request size limits.
- Require change ticket, reason, release ID, and idempotency key.
- Separate creator, approver, and publisher roles when risk requires it.
- Protect Actuator route listing/refresh endpoints; they are not public admin APIs.
- Audit both succeeded and denied actions, without logging tokens or secrets.

### 8.3. Distinguishing Data Plane and Control Plane

| Control plane | Data plane |
| --- | --- |
| Creates/validates/approves routes | Matches requests and proxies traffic |
| Manages desired route versions | Uses runtime route cache |
| Auditing, rollback, rollout status | Latency/status/upstream metrics |
| Requires elevated admin privileges | Serves client/API traffic |
| Infrequent, reviewed changes | Continuous requests, latency-sensitive |

Never let a business request modify routes or pick an upstream via query parameters or headers. The data plane only reads configurations published by the control plane.

## 9. Allowlists and Validation Against SSRF

This is the most critical step before constructing a `RouteDefinition`. **Never accept free-form upstream URIs from operator requests**. An account permitted to publish routes should not be able to turn the Gateway into a proxy to arbitrary network addresses.

### 9.1. Service Key Allowlist

~~~java
import java.net.URI;
import java.util.Map;

public final class ApprovedUpstreams {

    private ApprovedUpstreams() {}

    public static final Map<String, URI> BY_KEY = Map.of(
            "catalog-v1", URI.create("lb://catalog-service"),
            "catalog-v2", URI.create("lb://catalog-v2-service"),
            "orders", URI.create("lb://orders-service")
    );
}
~~~

In production, this list should come from an owned and approved service inventory/configuration. A service key must never map to an arbitrary client-supplied host.

### 9.2. Inputs to Reject

| Input | Reason |
| --- | --- |
| `http://127.0.0.1:...` | Could access loopback/admin services |
| `http://169.254.169.254/...` | Could access cloud metadata endpoints |
| Arbitrary `http://10.x.x.x`, `172.16/12`, `192.168/16` | Could access unauthorized internal networks |
| `file:`, `jar:`, `ftp:` | Not an approved HTTP upstream service |
| URI with userinfo (`user:pass@host`) | Could leak credentials into URIs/logs |
| Client-supplied hostname | DNS rebinding/SSRF and out-of-inventory access |
| `lb://` service ID not on allowlist | Could route to an unauthorized internal service |
| Query/fragment in upstream URI | Outside the route contract and prone to semantic bugs |
| Arbitrary filter expressions | Could introduce out-of-policy behavior or widen attack surface |

The allowlist is the primary layer. Additional scheme/host/port checks help catch misconfigurations, but **do not replace an approved inventory and network egress policies**.

### 9.3. Path Validation

In this lab, only declared prefixes such as `/api/catalog` and `/api/orders` are allowed. Reject:

- Empty prefixes, prefixes not starting with `/`, or containing `//`, `..`, or control characters.
- Operator-injected wildcards (`*`, `**`, `{*path}`).
- Prefixes colliding with `/internal/admin`, `/actuator`, or management paths.
- Prefixes overlapping another route without an explicit priority policy.
- Encoded slashes/path normalization mismatching the contract.

Paths must be validated after normalizing with the exact semantics the Gateway uses; never rely on an ad-hoc `String.replace` to check for route conflicts.

## 10. Building RouteDefinition from a Validated Command

We do not deserialize a client-sent `RouteDefinition` directly. Instead, the server maps the command to a route with a fixed structure.

### 10.1. Command DTO

~~~java
import java.util.List;

public record CreateRouteReleaseRequest(
        String routeKey,
        String serviceKey,
        String publicPrefix,
        List<String> methods,
        String changeTicket,
        String reason
) {}
~~~

There are no `uri`, `filters`, `order`, or `predicateArgs` fields in the DTO. Those values are decided by the server.

### 10.2. Validator

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;
import org.springframework.web.util.pattern.PathPatternParser;

@Component
public class RouteCommandValidator {

    private static final Pattern ROUTE_KEY =
            Pattern.compile("[a-z][a-z0-9-]{2,50}");
    private static final Set<String> ROUTE_KEYS =
            Set.of("catalog-public", "orders-public");
    private static final Set<String> PREFIXES =
            Set.of("/api/catalog", "/api/orders");
    private static final Set<String> METHODS =
            Set.of("GET", "HEAD");
    private static final Set<String> SERVICE_KEYS =
            ApprovedUpstreams.BY_KEY.keySet();
    private static final Map<String, String> PREFIX_BY_ROUTE =
            Map.of(
                    "catalog-public", "/api/catalog",
                    "orders-public", "/api/orders");
    private static final Map<String, Set<String>> SERVICES_BY_ROUTE =
            Map.of(
                    "catalog-public", Set.of("catalog-v1", "catalog-v2"),
                    "orders-public", Set.of("orders"));

    public void validate(CreateRouteReleaseRequest request) {
        require(request != null, "request is required");
        require(request.routeKey() != null
                        && ROUTE_KEY.matcher(request.routeKey()).matches(),
                "invalid routeKey");
        require(ROUTE_KEYS.contains(request.routeKey()),
                "routeKey is not approved");
        require(SERVICE_KEYS.contains(request.serviceKey()),
                "serviceKey is not approved");
        require(PREFIXES.contains(request.publicPrefix()),
                "publicPrefix is not approved");
        require(request.publicPrefix().equals(
                        PREFIX_BY_ROUTE.get(request.routeKey())),
                "routeKey and publicPrefix do not match");
        require(SERVICES_BY_ROUTE.get(request.routeKey())
                        .contains(request.serviceKey()),
                "serviceKey is not approved for this routeKey");
        require(request.methods() != null
                        && !request.methods().isEmpty()
                        && METHODS.containsAll(request.methods()),
                "method is not approved");
        require(request.methods().stream().distinct().count()
                        == request.methods().size(),
                "duplicate methods are not allowed");
        require(request.changeTicket() != null
                        && request.changeTicket().matches("CHG-[A-Z0-9-]{4,40}"),
                "changeTicket is invalid");
        require(request.reason() != null
                        && !request.reason().isBlank()
                        && request.reason().length() <= 300,
                "reason is required and must be at most 300 characters");

        // Parse using the same path parser the app uses; prefix must still be allowlisted.
        PathPatternParser.defaultInstance.parse(
                request.publicPrefix() + "/**");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalArgumentException(message);
        }
    }
}
~~~

The validator above illustrates the lab's policy; it does not replace authorization checks or a route-conflict service. `PathPatternParser` verifies the pattern parses validly; the allowlist restricts which prefixes are permitted. In production, route conflict checks must consider **all existing routes**, method overlaps, host predicates, ordering, and ingress rewrites.

### 10.3. Building RouteDefinition

~~~java
import java.net.URI;
import java.util.List;

import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.filter.FilterDefinition;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.stereotype.Component;

@Component
public class RouteDefinitionFactory {

    public RouteDefinition build(CreateRouteReleaseRequest request) {
        URI upstream = ApprovedUpstreams.BY_KEY.get(request.serviceKey());

        RouteDefinition route = new RouteDefinition();
        route.setId(request.routeKey());
        route.setUri(upstream);
        route.setOrder(100);
        route.setPredicates(List.of(
                new PredicateDefinition(
                        "Path=" + request.publicPrefix() + "/**"),
                new PredicateDefinition(
                        "Method=" + String.join(",", request.methods()))
        ));
        route.setFilters(List.of(
                new FilterDefinition("StripPrefix=2")
        ));
        return route;
    }
}
~~~

For `/api/catalog/items/42`, `StripPrefix=2` rewrites the backend path to `/items/42`. The `/api/orders` prefix also has two segments; if the public prefix changes, the filter must be recalculated or configured per policy. Never let admins pick an arbitrary `StripPrefix` in the lab.

**API version note:** `PredicateDefinition`/`FilterDefinition` constructors and binding may differ across Gateway releases. Verify the compile API against your active BOM. If your release does not support the shortcut constructor, build the definition using that release's builder/config args API; never guess args and publish to production.

## 11. Persisting Candidates and Audit Records

A release candidate must retain **immutable content** once approved. If a candidate could be edited after approval without creating a new version, the audit trail could no longer prove what content was actually released.

### 11.1. Data Model

| Record | Typical fields | Rule |
| --- | --- | --- |
| `route_release` | release_id, route_key, state, created_by, created_at, change_ticket, reason | Single candidate lifecycle |
| `route_release_spec` | release_id, service_key, public_prefix, methods, spec_hash | Candidate content immutable after validation |
| `route_version` | route_key, version, route_definition_json, spec_hash, created_at | Per-version snapshot |
| `route_active_state` | route_key, active_version, desired_version, updated_at | Version-based optimistic lock |
| `route_audit_event` | event_id, actor, action, release_id, before_hash, after_hash, outcome, timestamp, correlation_id | Append-only |
| `route_instance_observation` | instance_id, desired_version, applied_version, status, observed_at, error_code | Tracks convergence |

### 11.2. Sample Audit Event

~~~json
{
  "eventId": "aud-01JCATALOG-0007",
  "actor": "operator-17",
  "action": "ROUTE_ACTIVATE",
  "routeKey": "catalog-public",
  "releaseId": "rel-01JCATALOGV2",
  "changeTicket": "CHG-2026-042",
  "beforeVersion": 12,
  "afterVersion": 13,
  "beforeHash": "sha256:8c2f...redacted-example",
  "afterHash": "sha256:0b9a...redacted-example",
  "outcome": "REQUESTED",
  "correlationId": "trace-lab-00042",
  "timestamp": "2026-11-24T08:30:00Z"
}
~~~

Audit records must never contain bearer tokens, client secrets, cookies, or full HTTP headers. Route definitions can expose internal topology details; restrict audit read permissions and redact sensitive information when displaying.

### 11.3. Write Order During Activation

In a durable system, use a transaction in the control-plane store to:

1. Verify the candidate is `APPROVED`.
2. Verify `expectedVersion` equals the current active version.
3. Save the previous version snapshot.
4. Write the new desired route version.
5. Write the `ROUTE_ACTIVATE_REQUESTED` audit event.
6. Commit the transaction.
7. Publish the refresh notification after commit.
8. Record observed state from each Gateway instance.

Do not hold a DB transaction open while waiting for all Gateway Pods to refresh. Instead, use an outbox/event pattern or a release coordinator that tracks state. If refresh fails, desired state can still be redelivered or rolled back per policy.

### 11.4. Auditing Must Also Record Failures

Actions requiring audit records:

- Candidate created, validation succeeded/failed.
- Approval granted or denied.
- Activation requested, saved successfully, refresh succeeded/failed.
- A Gateway instance reported degraded or failed to converge.
- Rollback requested, accepted/rejected, and completed.
- Admin request returned 401/403 or was rejected by policy.

The audit store should have appropriate retention, access controls, backups, and tamper-evidence. Never allow the admin API to delete audit history alongside a route.

## 12. Publishing Routes in a Single Gateway Instance

For a single-instance lab, you can use `RouteDefinitionWriter` to save routes and `RefreshRoutesEvent` to instruct the Gateway to reload routes.

### 12.1. Minimal Publish Service

~~~java
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class LocalRoutePublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;

    public LocalRoutePublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events) {
        this.writer = writer;
        this.events = events;
    }

    public Mono<Void> publish(RouteDefinition definition) {
        return writer.save(Mono.just(definition))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }

    public Mono<Void> remove(String routeId) {
        return writer.delete(Mono.just(routeId))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

This is a **local publisher for the lab**. It does not provide a transaction across the route store and audit store, does not verify that runtime routes built cleanly, and does not broadcast refreshes to other JVMs.

### 12.2. Handling Save and Refresh Failures

A reactive chain completes once `writer.save(...)` completes and event publication runs. However, publishing an event does not mean every route predicate/filter materialized cleanly. A post-refresh observation step is needed:

- Read runtime routes and confirm the expected route ID/version appears.
- Send a smoke request through the public path to a suitable backend test/health endpoint.
- Record `appliedVersion` and the per-instance result.
- On error, log a redacted failure reason and transition the release to `DEGRADED`.

Never return `ACTIVE` solely because the publisher method emitted `onComplete`.

### 12.3. When Is an In-Memory Repository Appropriate?

`InMemoryRouteDefinitionRepository` is convenient for demos and tests because route definitions live in-process. However:

- Restarting the Gateway can lose dynamic routes.
- Pod A and Pod B hold separate state.
- Publishing to Pod A does not automatically update Pod B.
- There is no durable audit/history/rollback unless persisted elsewhere.

In production, use a persistent `RouteDefinitionRepository` or a `RouteDefinitionLocator` reading from a durable source. Route activation still requires refreshing and observing state.

## 13. Building the Route Release Service and Admin Controller

We separate HTTP handling, validation, route factory, release store, auditing, and publishing so each component can be tested independently.

### 13.1. Control Plane Abstractions

~~~java
import reactor.core.publisher.Mono;

public interface RouteReleaseStore {
    Mono<RouteRelease> createDraft(
            CreateRouteReleaseRequest request,
            String actor,
            String idempotencyKey);

    Mono<RouteRelease> findById(String releaseId);

    Mono<RouteRelease> markValidated(String releaseId, String specHash);

    Mono<RouteRelease> approve(
            String releaseId, String approver, long expectedVersion);

    Mono<RouteActivation> activateAtomically(
            String releaseId, String actor, long expectedVersion);

    Mono<RouteSnapshot> findActiveSnapshot(String routeKey);

    Mono<RouteActivation> rollbackAtomically(
            String routeKey,
            String actor,
            long expectedVersion,
            String reason);
}

public interface RouteAuditStore {
    Mono<Void> append(RouteAuditEvent event);
}

public interface RouteObservationStore {
    Mono<Void> record(RouteInstanceObservation observation);
}
~~~

The `RouteRelease`, `RouteActivation`, `RouteSnapshot`, `RouteAuditEvent`, and `RouteInstanceObservation` records are data models defined by the application. The interfaces above represent the lab's contract, **not built-in Spring Cloud Gateway classes**.

### 13.2. Thin Controller

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/internal/admin/route-releases")
public class RouteReleaseController {

    private final RouteReleaseApplicationService service;

    public RouteReleaseController(RouteReleaseApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<ReleaseResponse>> create(
            @RequestBody CreateRouteReleaseRequest request,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @AuthenticationPrincipal Jwt operator) {

        return service.createCandidate(
                        request, operator.getSubject(), idempotencyKey)
                .map(response -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(response));
    }

    @PostMapping("/{releaseId}/validate")
    public Mono<ReleaseResponse> validate(
            @PathVariable String releaseId,
            @AuthenticationPrincipal Jwt operator) {
        return service.validate(releaseId, operator.getSubject());
    }

    @PostMapping("/{releaseId}/approve")
    public Mono<ReleaseResponse> approve(
            @PathVariable String releaseId,
            @RequestHeader("If-Match") String expectedVersion,
            @AuthenticationPrincipal Jwt operator) {
        return service.approve(
                releaseId, operator.getSubject(), expectedVersion);
    }

    @PostMapping("/{releaseId}/activate")
    public Mono<ReleaseResponse> activate(
            @PathVariable String releaseId,
            @RequestHeader("If-Match") String expectedVersion,
            @AuthenticationPrincipal Jwt operator) {
        return service.activate(
                releaseId, operator.getSubject(), expectedVersion);
    }
}
~~~

This is an illustrative WebFlux skeleton. `ReleaseResponse` and `RouteReleaseApplicationService` are defined by the lab. If methods accept `Jwt` as the principal, the admin API must genuinely use a JWT Resource Server; if using another authentication mechanism, extract the actor from the verified principal accordingly. Never read `actor` from the JSON request body.

### 13.3. Per-Action Authorization

The configuration in section 8 used a single scope across all of `/internal/admin/**` to keep the example short. In deployment, split permissions:

| Endpoint | Suggested authority |
| --- | --- |
| Create candidate | `SCOPE_gateway.routes.write` |
| Read release/status | `SCOPE_gateway.routes.read` |
| Approve | `SCOPE_gateway.routes.approve` |
| Activate | `SCOPE_gateway.routes.publish` |
| Rollback | `SCOPE_gateway.routes.rollback` |

Inside a single `SecurityWebFilterChain`, combine method/path matchers with authorities. Test that a user holding only `write` cannot call `activate` or `rollback`.

## 14. The create → validate → approve → activate Workflow

### 14.1. Create Candidate

1. Authenticate the operator token.
2. Verify `gateway.routes.write` permission.
3. Check `Idempotency-Key`.
4. Validate basic DTO fields and service key/path/method allowlists.
5. Generate a unique release ID and save the candidate as `DRAFT`.
6. Write the `ROUTE_CANDIDATE_CREATED` audit event.

### 14.2. Validate Candidate

Validation should check:

- DTO schema, lengths, allowed characters, and required fields.
- Service key is in the inventory/allowlist and the service is still eligible for publishing.
- Public prefix is in the path allowlist and does not collide with reserved routes.
- Predicates/filters belong to supported lists; no arbitrary expressions.
- Route ID does not conflict or reassign ownership improperly.
- Method/path overlap with existing routes.
- Upstream service has appropriate health/registration.
- Route definition parses/materializes cleanly in a test context matching the Gateway version.
- Route security, rate-limit, TLS, and observability policies are attached.

Passing validation only proves the configuration is **eligible for review**, not that the backend will necessarily be healthy at publish time.

### 14.3. Approve Candidate

Approval must record:

- Approver identity and authority.
- Candidate spec hash.
- Current version on which the candidate is based.
- Change ticket, reason, and approval timestamp.
- Publish conditions (timing, scope, canary, maintenance window).

If the spec hash changes after approval, status must revert to `DRAFT` or `VALIDATED` and require fresh approval. Never allow editing approved content in place.

### 14.4. Activate Candidate

Activation must use compare-and-set / optimistic locking:

~~~text
expectedVersion = 12
activeVersion   = 12
candidate       = approved release 13

transaction:
  assert activeVersion == expectedVersion
  save snapshot(version=12)
  write desiredVersion=13
  write audit(ROUTE_ACTIVATE_REQUESTED, before=12, after=13)
commit

publish refresh notification(version=13)
observe each Gateway instance
~~~

If the active version is already 13 or 14, a command based on `expectedVersion=12` must be rejected with a conflict (e.g., HTTP 409). The operator must read the new state and create/re-review a candidate.

## 15. Publishing Routes and Observing Across Multiple Gateway Replicas

A Gateway cluster typically runs multiple Pods. Route updates must **converge across all instances** or satisfy the published rollout policy.

### 15.1. Do Not Only Emit RefreshRoutesEvent Inside One Pod

`RefreshRoutesEvent` is an in-process application event. To distribute updates:

1. Control plane writes the desired version to a shared store.
2. Control plane writes an event to the outbox within the same transaction.
3. Publisher emits an event containing `routeKey`, `desiredVersion`, `releaseId`, and `eventId`.
4. Each Gateway Pod receives the event and loads the versioned route definition from the source of truth.
5. The Pod updates its route repository/cache and emits a local refresh event.
6. The Pod records a success/failure observation tagged with its instance ID.
7. The coordinator aggregates state and decides `ACTIVE` or `DEGRADED`.

### 15.2. Refresh Notification Payload

~~~json
{
  "eventId": "evt-01JCATALOG-00013",
  "eventType": "ROUTE_VERSION_PUBLISHED",
  "routeKey": "catalog-public",
  "releaseId": "rel-01JCATALOGV2",
  "desiredVersion": 13,
  "specHash": "sha256:0b9a...example",
  "createdAt": "2026-11-24T08:30:00Z"
}
~~~

The event does not need to carry access tokens or secrets. Receiving Pods fetch the version from the store using their own identity and verify the hash to ensure the payload was not altered.

### 15.3. Observed State

| Instance | Desired | Applied | Status | Action |
| --- | ---: | ---: | --- | --- |
| gateway-a | 13 | 13 | `APPLIED` | None needed |
| gateway-b | 13 | 13 | `APPLIED` | None needed |
| gateway-c | 13 | 12 | `REFRESH_FAILED` | Retry/reconcile |

In this example, the cluster should not yet be marked `ACTIVE` if policy requires 100% of replicas to apply. A quorum/canary policy may be used if approved, but it must clearly surface which Pods still serve the old version and how split behavior is prevented.

### 15.4. Reconciliation Matters More Than Exactly-Once Event Delivery

Message brokers can deliver duplicate, delayed, or out-of-order events. Each Pod should:

- Process events idempotently by `eventId` and `desiredVersion`.
- Ignore versions lower than the already applied version.
- If receiving version 15 while on 13, load version 15 directly if the store holds full snapshots.
- Periodically reconcile applied version against desired version.
- Retry with bounded backoff; never refresh in an uncontrolled tight loop.
- Report finite error codes without logging tokens/config secrets.

If a Pod restarts, it must load the latest desired state from the source of truth at startup rather than relying solely on events it may have missed.

## 16. Controlled Rollback

A rollback is a **new release** that restores the content of a previous snapshot. Never delete history or mutate already-published version records backward.

### 16.1. Example Version Timeline

| Version | Content | State |
| ---: | --- | --- |
| 12 | `catalog-public` → `lb://catalog-service` | Previous snapshot |
| 13 | `catalog-public` → `lb://catalog-v2-service` | Active after publish |
| 14 | Restores spec of version 12 | New rollback release |

Version 14 has a higher number than version 13, but reuses the **route specification** from version 12. Monotonic versioning makes event ordering, auditing, and reconciliation far clearer than decrementing the active version from 13 back to 12.

### 16.2. Rollback Workflow

1. An operator with `gateway.routes.rollback` sends a rollback command with a reason and `expectedVersion=13`.
2. The control plane reads active snapshot version 13 and previous known-good snapshot 12.
3. Verify the current version is still 13; if the route already moved to version 14, return conflict.
4. Create rollback release 14 containing the saved spec from version 12 and record `rollbackOfVersion=12`.
5. Write desired state version 14, audit event, and outbox in a transaction.
6. Publish refresh notification for version 14.
7. Each Gateway Pod loads version 14, refreshes, and reports applied state.
8. Run smoke tests through the public route.
9. Once convergence policy is met, mark version 14 `ACTIVE`; retain version 13 and all audit history.

### 16.3. Lab Code to Restore a Route Definition

~~~java
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionWriter;
import org.springframework.cloud.gateway.event.RefreshRoutesEvent;
import org.springframework.context.ApplicationEventPublisher;

import reactor.core.publisher.Mono;

public class RouteRollbackPublisher {

    private final RouteDefinitionWriter writer;
    private final ApplicationEventPublisher events;

    public RouteRollbackPublisher(
            RouteDefinitionWriter writer,
            ApplicationEventPublisher events) {
        this.writer = writer;
        this.events = events;
    }

    public Mono<Void> restore(RouteDefinition previousSnapshot) {
        // Snapshot must be loaded from a verified store with version/hash.
        return writer.save(Mono.just(previousSnapshot))
                .then(Mono.fromRunnable(() ->
                        events.publishEvent(new RefreshRoutesEvent(this))));
    }
}
~~~

This snippet only performs save and refresh inside **one Gateway instance**. Production must go through the release coordinator: check expected version, create a new rollback version, durably write audit/outbox, broadcast to replicas, and wait for observed state.

### 16.4. When Rollback Also Fails

Never assume an older version can always be redeployed. Possible failures:

- The old service was decommissioned or has no instances left.
- DNS/service discovery no longer resolves.
- Old TLS certificates expired.
- Database schemas changed incompatibly.
- The old backend still exists but lacks sufficient capacity.
- The route snapshot references a filter factory removed in the new Gateway build.

Therefore, releases must record both **route spec version and compatibility/dependency assumptions**. Before decommissioning an old backend, confirm the rollback window has ended and another recovery option exists.

## 17. Audit Trail and Integrity

The audit trail must answer: **who did what, on which route, based on which version, changed to what, approved by whom, and how did Gateway instances apply it?**

### 17.1. Event Model

~~~java
import java.time.Instant;

public record RouteAuditEvent(
        String eventId,
        String actor,
        String action,
        String routeKey,
        String releaseId,
        Long beforeVersion,
        Long afterVersion,
        String beforeHash,
        String afterHash,
        String outcome,
        String changeTicket,
        String correlationId,
        Instant occurredAt
) {}
~~~

### 17.2. Hashing Route Specifications

Hashing detects whether two configurations share identical content. Before hashing:

1. Serialize the route spec in a stable canonical format.
2. Sort map keys and normalize URI/method/filter representations.
3. Strip volatile fields that are not part of configuration (e.g. `createdAt`).
4. Compute SHA-256 over UTF-8 bytes.
5. Store the hash alongside the immutable snapshot.

Never hash JSON strings with arbitrary map ordering and conclude configs differ just because field order changed. Hashing **does not replace digital signatures or access control**; anyone permitted to edit both spec and hash could alter both. Protect the store/audit logs and write permissions.

### 17.3. Outbox Pattern to Prevent Losing Audit/Refresh Events

Inside the same transaction:

- Save the new route version.
- Update desired state with optimistic locking.
- Append the audit event.
- Write the outbox event to deliver to Gateway instances.

A background publisher reads the outbox and dispatches messages. Mark delivered on success; retry on error. Consumers are idempotent by event ID. This handles crashes where the DB commits successfully but the process dies before sending the refresh notification.

### 17.4. Immutable Audits and Data Protection

- Only the audit service may append; operators cannot edit or delete historical events.
- Restrict audit readers and enforce a retention policy.
- Never log Authorization headers, client secrets, refresh tokens, cookies, or raw request bodies.
- Record the actor from the verified identity, never trusting an actor field in the DTO.
- Attach change ticket and correlation ID to link with the release pipeline.
- For high compliance requirements, use append-only storage, immutable backups, or platform-managed signature/hash chains.

## 18. Canaries and Rollout Scope

Dynamic routes can be rolled out using several strategies. **Do not treat changing a URI as a canary** if all Gateway instances immediately switch to the new backend.

### 18.1. Options

| Strategy | How it works | When appropriate |
| --- | --- | --- |
| All-at-once | Update the stable route ID across all instances | Small change, well-tested backend |
| Instance canary | A subset of Gateway Pods runs the new desired version | Observing data-plane behavior per Pod |
| Weighted backend | Route splits traffic by weight across compatible backends | Tested version-specific support/configuration |
| Header cohort | Only allowlisted client/test groups with a header hit the candidate path | Controlled canary by client cohort |
| Shadow traffic | Mirrors requests to the new backend without using its response | Comparing behavior/latency while avoiding side effects |

### 18.2. Canaries Do Not Replace Route Validation

Before shifting 5% of traffic:

- Candidate must pass schema/policy validation.
- Backend v2 has adequate readiness/health and capacity.
- Authorization/TLS/headers are verified.
- Per-route-version/upstream metrics are available.
- Clear thresholds and rollback triggers exist.
- Canary traffic excludes operations with side effects unless mirrored backends are idempotent.

### 18.3. Never Publish Client-Supplied Weights

Weights are a control-plane policy, never taken from arbitrary query parameters or headers. When using weighted routing, enforce min/max bounds, total weights, an allowlisted backend set, and test the distribution. Never use random selection as an authorization mechanism.

## 19. Observability and Health Verification

After publishing, measure both **applied route config** and **whether live traffic is healthy**.

### 19.1. Suggested Metrics

| Metric | Bounded labels | Purpose |
| --- | --- | --- |
| `route_release_total` | action, outcome | Counts of create/validate/activate/rollback |
| `route_refresh_total` | instance, outcome | Refresh outcomes per Gateway Pod |
| `route_applied_version` | route_key, instance | Currently applied version |
| `route_publish_duration` | route_key, outcome | Duration from desired to observed |
| `gateway_requests` | route_id, status, upstream | Traffic and errors per route |
| `gateway_request_duration` | route_id, upstream | Latency per route/backend |
| `route_rollback_total` | route_key, reason_code | Tracks rollbacks |
| `route_validation_failure_total` | rule_code | Detects invalid candidates |

Avoid using `releaseId`, user IDs, raw paths, query strings, or arbitrary hostnames as metric labels if they cause high cardinality. Store detailed release/audit records in the event store.

### 19.2. Post-Activation Health Checks

A route is marked active when defined criteria are met:

1. Desired version is durably persisted.
2. Required Gateway instances report the applied version.
3. Route ID appears in each instance's runtime route view.
4. Smoke requests traverse the route to the right upstream.
5. Backend readiness/health meets thresholds.
6. No abnormal 401/403/404/5xx spikes appear after rollout.
7. Latency/error rates remain within thresholds during the observation window.

Do not call a backend health endpoint directly and conclude route paths/filters work properly. Smoke tests must travel through **the actual public route** with approved methods, paths, and headers.

### 19.3. Actuator and Route Diagnostics

Actuator can help inspect health/metrics and route diagnostics depending on the Gateway release/configuration. Route listing/refresh endpoints can expose backend URIs, filter configs, or allow runtime mutations. Therefore:

- Expose only strictly necessary endpoints.
- Protect them with authentication, roles, and private networking.
- Never expose route mutation endpoints to business clients.
- Do not treat Actuator endpoints as a complete audit/release workflow.
- Record versions/hashes and actors in the control plane rather than relying solely on route listings.

## 20. Testing the Publish and Rollback Workflow

A test asserting only that the admin API returns HTTP 200 is insufficient. You must test **state store, audit records, runtime routes, backend receipt of requests, and all instances**.

### 20.1. Test Layers

| Test type | Component | What to prove |
| --- | --- | --- |
| Unit test | Validator, route factory | Invalid input rejected; route definition built properly |
| Application test | Release service/store/audit | State transitions, idempotency, optimistic locking |
| Gateway integration test | `RouteDefinitionWriter` + HTTP listener | New route refreshes and matches requests |
| Admin API security test | JWT/authorities | Operators lacking permissions cannot publish/roll back |
| Multi-instance test | Multiple Gateway contexts or test nodes | Desired version converges, duplicate events cause no errors |
| Failure injection | Token store, event bus, backend | Degraded state and recovery work |
| E2E test | Operator → control plane → Gateway → backend | Full release path includes audit and rollback |

### 20.2. Unit Tests for the Validator

~~~java
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RouteCommandValidatorTest {
    private final RouteCommandValidator validator =
            new RouteCommandValidator();

    @Test
    void acceptsApprovedCatalogRoute() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                List.of("GET", "HEAD"), "CHG-2026-042",
                "Switch to catalog v2");
        assertDoesNotThrow(() -> validator.validate(request));
    }

    @Test
    void rejectsUnapprovedServiceKey() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "http://127.0.0.1:9000",
                "/api/catalog", List.of("GET"), "CHG-2026-042",
                "Invalid upstream attempt");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }

    @Test
    void rejectsAdminPathAsPublicPrefix() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/internal/admin",
                List.of("GET"), "CHG-2026-042",
                "Reserved path attempt");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }

    @Test
    void rejectsMethodOutsideAllowlist() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                List.of("DELETE"), "CHG-2026-042",
                "Method is not approved");
        assertThrows(IllegalArgumentException.class,
                () -> validator.validate(request));
    }
}
~~~

These tests only verify the allowlist in the example. When expanding policies, add tests for route overlaps, duplicate methods, path normalization, disabled services, and invalid change tickets.

### 20.3. Testing Route Definitions

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RouteDefinitionFactoryTest {
    private final RouteDefinitionFactory factory =
            new RouteDefinitionFactory();

    @Test
    void buildsApprovedCatalogRoute() {
        var request = new CreateRouteReleaseRequest(
                "catalog-public", "catalog-v2", "/api/catalog",
                java.util.List.of("GET"), "CHG-2026-042",
                "Switch backend");
        var route = factory.build(request);

        assertEquals("catalog-public", route.getId());
        assertEquals("lb://catalog-v2-service",
                route.getUri().toString());
        assertEquals(100, route.getOrder());
        assertEquals(2, route.getPredicates().size());
        assertEquals("Path", route.getPredicates().get(0).getName());
        assertEquals("Method", route.getPredicates().get(1).getName());
        assertEquals("StripPrefix", route.getFilters().get(0).getName());
    }
}
~~~

If the shortcut constructor of `PredicateDefinition`/`FilterDefinition` differs in your Gateway release, adapt the test to your BOM's actual API. Never drop assertions on URI/predicate/filter just to make tests compile.

### 20.4. Gateway Integration Test

In an integration test:

1. Start the Gateway with `RANDOM_PORT`.
2. Configure two backend HTTP stubs on random ports.
3. Call the current route and verify Catalog v1 receives the request.
4. Call `RouteDefinitionWriter.save(...)` via the lab publisher and emit a refresh event.
5. Call the same public path again and verify Catalog v2 receives the request.
6. Restore the v1 snapshot, refresh again, and verify requests return to v1.
7. Assert response status/body, request counts, and the path received by the backend.

Tests must send HTTP traffic through the real Gateway listener. Calling service methods directly does not prove the predicate/filter chain ran.

### 20.5. Security Tests for the Admin API

| Operator token | Create | Approve | Activate | Rollback |
| --- | --- | --- | --- | --- |
| No token | 401 | 401 | 401 | 401 |
| Only `routes.read` | 403 | 403 | 403 | 403 |
| Only `routes.write` | Allowed | 403 | 403 | 403 |
| `routes.approve` | Per policy | Allowed | 403 | 403 |
| `routes.publish` | Per policy | 403 | Allowed if approved | 403 |
| `routes.rollback` | Per policy | 403 | 403 | Allowed |

Using mock JWTs in tests is helpful for verifying authority mapping, but you must also have a dedicated test using a signed JWT/test issuer over HTTP to verify real signature, issuer, and audience validation.

## 21. Failure Injection and Recovery Criteria

A reliable release workflow must also handle adverse conditions.

| Failure | Expected outcome | Action |
| --- | --- | --- |
| Candidate has unknown service key | Validation fails | Audit `VALIDATION_REJECTED`, do not write desired state |
| Operator lacks publish scope | 403 | Do not call writer, audit denied |
| Two operators publish with same expected version | One wins, the other gets 409 | Reload new state and re-review |
| DB commits successfully, publisher crashes | Desired state/outbox still exists | Outbox worker redelivers event |
| Duplicate event delivery | Pod handles idempotently | No duplicate version/refresh side effects |
| Out-of-order event arrival | Pod ignores older version | Reconcile latest desired version |
| One Pod fails to refresh | Release becomes `DEGRADED` | Retry/reconcile or roll back per policy |
| Backend v2 5xx rate spikes | Route applied but traffic unhealthy | Trigger rollback threshold |
| Backend v2 DNS/service discovery fails | Smoke test fails | Do not mark release ACTIVE |
| Rollback version conflict | 409 | Read new active version and submit new rollback request |
| Audit store/outbox write fails | Do not activate if audit is mandatory | Fail closed, report control-plane error |
| Gateway restarts | Loads latest desired state on startup | Compare applied/desired after readiness |

### 21.1. Do Not Retry Publish Blindly

Publishing has side effects. If the client times out, it is unknown whether the server committed. Therefore:

1. Resend with the same `Idempotency-Key`.
2. Read release status by release ID.
3. Inspect desired version and observed state.
4. Only create a new command if the prior release was not recorded.

Never resend `POST activate` with a new ID without checking the previous command's status.

### 21.2. Rollback Triggers Must Be Metric-Driven

Lab policy example:

| Signal | Example threshold | Action |
| --- | --- | --- |
| Upstream 5xx | > 5% over 5 minutes with sufficient sample size | Mark degraded and require review/rollback |
| p95 latency | > 2x baseline over 10 minutes | Alert and evaluate rollback |
| Gateway refresh | Any instance not applied after 60 seconds | Retry/reconcile; do not mark fully active |
| Health probe | Backend v2 unhealthy 3 consecutive times | Halt rollout |

These numbers are **illustrative thresholds** and must be calibrated to traffic/SLOs. Avoid auto-rolling back on a single failed request or tiny sample sizes. For routes with side effects, evaluate data compatibility before switching backward.

## 22. Practice Commands Over HTTP

The commands below illustrate the operator workflow. Run them in a lab/private environment with a test operator token. Never record real tokens in shell history or CI logs.

### 22.1. Create Candidate

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST 'http://127.0.0.1:8080/internal/admin/route-releases' \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: change-2026-042' \
  -d '{
    "routeKey": "catalog-public",
    "serviceKey": "catalog-v2",
    "publicPrefix": "/api/catalog",
    "methods": ["GET", "HEAD"],
    "changeTicket": "CHG-2026-042",
    "reason": "Switch Catalog traffic to backend v2"
  }'
~~~

Expected response is a `DRAFT` candidate with a release ID. This is an example request, not captured command output.

### 22.2. Validate and Approve

~~~bash
RELEASE_ID='rel-01JCATALOGV2'

curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/validate" \
  -H "Authorization: Bearer $OPERATOR_TOKEN"

# Use an approver token with its dedicated scope.
curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/approve" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H 'If-Match: "12"'
~~~

### 22.3. Activate and Check Status

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST "http://127.0.0.1:8080/internal/admin/route-releases/$RELEASE_ID/activate" \
  -H "Authorization: Bearer $PUBLISH_TOKEN" \
  -H 'If-Match: "12"'

curl --silent --show-error \
  -H "Authorization: Bearer $READ_TOKEN" \
  'http://127.0.0.1:8080/internal/admin/routes/catalog-public/status'

curl --silent --show-error -i \
  'http://127.0.0.1:8080/api/catalog/items/42'
~~~

Consider the release `ACTIVE` only when desired/applied versions converge per policy and smoke requests reach the right backend.

### 22.4. Rollback

~~~bash
curl --silent --show-error --fail-with-body \
  -X POST 'http://127.0.0.1:8080/internal/admin/route-releases/rel-01JCATALOGV2/rollback' \
  -H "Authorization: Bearer $ROLLBACK_TOKEN" \
  -H 'If-Match: "13"' \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Catalog v2 error rate exceeded approved threshold"}'
~~~

The rollback endpoint in section 7 is a proposed contract; exact request bodies/headers must match the lab's controller and release service. Do not assume the controller skeleton already implements the full rollback endpoint.

## 23. Publishing and Recovery Runbook

### Before Publishing

1. Confirm change ticket, owner, and release window.
2. Check candidate spec hash and current active version.
3. Verify an independent approver if policy requires one.
4. Check upstream health, capacity, service discovery, and TLS.
5. Verify route conflicts, path rewrites, methods, security, rate limiting, and observability.
6. Confirm the previous version snapshot can be restored.
7. Confirm Gateway instances are healthy and ready to receive refresh notifications.

### During Publishing

1. Send activate with idempotency key and expected version.
2. Verify desired version and outbox event were recorded.
3. Monitor each Gateway instance: applied version, refresh status, and error codes.
4. Send smoke requests through the public route.
5. Watch 4xx/5xx rates, latency, backend hits, and saturation.
6. Mark ACTIVE only after meeting convergence/observation policies.

### When Errors Are Detected

1. Identify whether the fault is route config, Gateway refresh, service discovery, backend, or security.
2. Assess blast radius: all instances or partial, all clients or a cohort.
3. Halt rollout or reduce traffic per the approved strategy.
4. Create a rollback release from the known-good snapshot using the current expected version.
5. Monitor refresh across all replicas and run smoke tests.
6. Record audit outcome, root cause, operator, and post-rollback version.
7. Preserve the failed release for analysis; never delete audit/history.

### After Rollback

- Confirm desired/applied versions converged.
- Verify the old backend remains healthy with sufficient capacity.
- Verify client responses/statuses/latencies returned to baseline.
- Open an incident/postmortem and store evidence without secrets.
- Create a fixed candidate if migration still needs to continue.

## 24. Acceptance Matrix

| ID | Scenario | Required result |
| --- | --- | --- |
| R01 | Candidate with valid service key | Creates DRAFT |
| R02 | Candidate with loopback/metadata URI | Rejected, no route written |
| R03 | Candidate with off-allowlist service key | Validation fails |
| R04 | Candidate with `/internal/admin` path | Validation fails |
| R05 | Candidate with DELETE method | Validation fails per lab policy |
| R06 | Operator without token | 401, backend routes unaffected |
| R07 | Operator lacking write scope | 403, audit denied |
| R08 | Operator with only write calls activate | 403 |
| R09 | Candidate passes validation | Spec hash saved |
| R10 | Spec changes after approval | Approval invalidated |
| R11 | Two publishes with same expected version | One succeeds, one returns 409 |
| R12 | Idempotency key resent | No duplicate release created |
| R13 | RouteDefinition saved | Route repository holds desired definition |
| R14 | Local refresh | New runtime route loaded |
| R15 | Path request after publish | Routes to new backend |
| R16 | StripPrefix | Backend receives right path |
| R17 | Activate audit | Records actor, before/after hash, ticket, outcome |
| R18 | Pod receives duplicate event | Does not regress or duplicate version/refresh |
| R19 | One Pod refresh fails | Release transitions to DEGRADED |
| R20 | Pod restarts | Loads latest desired state |
| R21 | New backend returns 5xx above threshold | Triggers review/rollback |
| R22 | Rollback with matching expected version | Creates new version from old snapshot |
| R23 | Rollback with wrong expected version | 409, no overwrite |
| R24 | Audit/outbox store fails | Does not publish when audit is mandatory |
| R25 | After rollback | All instances and smoke tests confirm old backend |

**Pass criterion:** Each test has evidence from HTTP responses, route store, audit logs, backend stubs, or per-instance observations. Never mark PASS based solely on a `"publish success"` log line.

## 25. Assembling Components Into a Single Release Flow

The examples above are independent components. The application service must wire them in the right sequence without skipping intermediate states.

### 25.1. Create Candidate

~~~text
createCandidate(request, actor, idempotencyKey):
  require actor has gateway.routes.write
  validate request schema
  validate routeKey, serviceKey, publicPrefix, methods
  reject arbitrary URI/filter/order values
  build RouteDefinition with approved factory
  calculate canonical spec hash
  store immutable DRAFT candidate
  append ROUTE_CANDIDATE_CREATED audit event
  return release ID and state
~~~

### 25.2. Validate and Approve

~~~text
validate(releaseId, actor):
  release = store.load(releaseId)
  require release.state == DRAFT
  definition = routeFactory.build(release.spec)
  validate schema + policy + conflicts + runtime compatibility
  hash = canonicalHash(definition)
  store.markValidated(releaseId, hash)
  audit.append(ROUTE_VALIDATED, actor, releaseId, hash)

approve(releaseId, approver, expectedVersion):
  require approver has gateway.routes.approve
  require approver != creator when separation-of-duties is enabled
  store.approve(releaseId, approver, expectedVersion)
  audit.append(ROUTE_APPROVED, ...)
~~~

### 25.3. Activate and Reconcile

~~~text
activate(releaseId, actor, expectedVersion):
  require actor has gateway.routes.publish
  require release.state == APPROVED
  transaction:
    snapshot current active route
    compare active version with expectedVersion
    persist immutable new version + desired state
    append activation audit event
    append refresh event to outbox
  return PUBLISHING

outbox publisher:
  deliver event to every Gateway instance
  retry delivery; consumers are idempotent

reconciler:
  compare desiredVersion with each appliedVersion
  run smoke test and health checks
  mark ACTIVE or DEGRADED
~~~

Pseudocode clarifies responsibilities; it must not be treated as a compiled Java class. Separate store transactions from waiting on Gateway Pods to refresh so locks/connections are not held across long network operations.

### 25.4. Admin API Response Statuses

| Operation | Suggested HTTP response | Condition |
| --- | --- | --- |
| Create candidate | 201 Created | New candidate persisted |
| Duplicate idempotency key | 200/303 per contract | Returns previously created release |
| Validation error | 422 Unprocessable Content | Valid JSON payload violating policy |
| Unauthorized | 401 | Missing/invalid token |
| Forbidden | 403 | Actor lacks permission |
| Version conflict | 409 Conflict or 412 Precondition Failed | expectedVersion/If-Match no longer matches |
| Activate accepted | 202 Accepted | Desired state recorded, awaiting convergence |
| Fully active | 200 on status read | All activation conditions met |
| Rollback accepted | 202 Accepted | Rollback release created and being applied |

Never return `200 ACTIVE` immediately when only an event has been enqueued. HTTP statuses should clearly reflect whether a request was accepted or rollout completed.

## 26. Anti-Patterns to Avoid

| Anti-pattern | Risk | Alternative |
| --- | --- | --- |
| Admin sends raw `RouteDefinition` | Can set arbitrary URI/filter/order | Small DTO + server-side factory |
| Accepting upstream URL from body | SSRF, accessing metadata/loopback/internal hosts | Service key allowlist and egress policy |
| Validating only URI scheme | DNS rebinding or internal hosts can slip through | Approved service inventory, network controls |
| Writing routes only to `InMemoryRouteDefinitionRepository` | Routes lost on restart and replica drift | Durable route store/source of truth |
| Calling only `writer.save()` | Runtime cache may not refresh | Refresh event + observed-state check |
| Publishing `RefreshRoutesEvent` in one Pod only | Other Pods never receive local events | Event bus/outbox or polling/reconciliation |
| Marking ACTIVE as soon as event is sent | Does not prove instances applied it | Per-instance applied versions and smoke tests |
| Mutating old version on rollback | Loses history and hinders auditing | Create new version from old snapshot |
| Retrying POST publish with a new release ID | Can create multiple releases | Idempotency key and status lookup |
| Omitting optimistic locking | Two operators overwrite each other's changes | If-Match/expectedVersion |
| Auditing only successes | Cannot tell who attempted rejected changes | Audit validation/security/publish failures too |
| Saving audit after sending event | Process crash can lose trail | Transaction + outbox |
| Logging raw headers/tokens in audit | Leaks credentials and PII | Metadata allowlist, redaction |
| Using Actuator route endpoints as admin workflow | Lacks approval, audit, policy, and rollback | Control-plane API with lifecycle |
| Testing only route definition objects | Does not prove runtime matching/proxying | HTTP integration tests through Gateway listener |
| Canarying routes without tracking metrics | Traffic can fail undetected | Thresholds, observation windows, rollback |
| Deleting old backend right after publish | Leaves no rollback target | Maintain compatibility window and capacity |
| Letting data-plane users edit routes | Clients can alter traffic topology | Separate control plane, elevated admin privileges |

## 27. Pre-Release Checklist and Summary

### Technical Checklist

~~~text
[ ] Gateway runtime and Spring Boot/Spring Cloud BOM are locked down.
[ ] Route Admin API resides solely on a private management network.
[ ] Operator token has valid issuer, audience, signature, and scopes.
[ ] Write/approve/publish/rollback permissions are separated per policy.
[ ] Candidate DTO does not accept arbitrary URI/filter/order.
[ ] Service key and public prefix are on the allowlist.
[ ] Route ID, path, method, order, and filters passed validation.
[ ] Route conflicts/overlaps checked against the route inventory.
[ ] RouteDefinition is constructed by a server-side factory.
[ ] Desired route state and audit logs are durably persisted.
[ ] Candidate spec is immutable after approval and has a canonical hash.
[ ] Publish uses expectedVersion and idempotency key.
[ ] Refresh notification is emitted post-commit via outbox.
[ ] Each Gateway instance reports desired/applied version observations.
[ ] Pod restart loads the latest desired state.
[ ] Route smoke tests traverse the public path and hit the right backend.
[ ] Metrics use bounded route/version labels without PII/secrets.
[ ] Rollback creates a new version from the previous immutable snapshot.
[ ] Failure injection covers event retries, Pod refresh failures, and backend 5xx.
[ ] Append-only audit logs have retention, backups, and access control.
[ ] Runbook, change ticket, owner, and approver are in place.
[ ] Exit criteria for the rollback window are met before removing the old backend.
~~~

### Practice Summary

- **Dynamic routing** allows changing routes without restarting the Gateway, but runtime updates require `RouteDefinitionWriter` and a route cache refresh mechanism.
- The **control plane** handles candidate creation, validation, approval, publishing, auditing, and rollback; the **data plane** simply serves requests using published routes.
- **Validation must restrict upstreams** via a service inventory/allowlist, rejecting arbitrary URIs and free-form filter expressions. This reduces SSRF and unauthorized traffic manipulation risks.
- The **audit trail** must record actor, change ticket, before/after route/version, spec hash, outcome, and correlation ID—never tokens or secrets.
- **Cluster refresh** requires event distribution, durable desired state, per-instance observation, and reconciliation. An in-JVM `RefreshRoutesEvent` does not update other Pods automatically.
- **Rollback is a new release** restoring a known-good snapshot with optimistic locking and auditing; never delete failed version history.
- **Tests must traverse real HTTP**, verifying routes, backends, statuses, metrics, audits, and post-rollback behavior.

When the workflow is complete, operations teams can clearly answer: **who published which route, under which change ticket, which Gateway instances applied it, whether traffic is healthy, and which version can be restored**. Those are the hallmarks of a controlled dynamic route publishing process in **SPRING_CLOUD_GATEWAY**.

### Reference Documentation for Version Verification

- **Spring Cloud Gateway Reference — RouteDefinition, RouteDefinitionWriter, route refresh, and Actuator:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Cloud Gateway — Route Predicate Factories and GatewayFilter Factories:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security Reactive OAuth2 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Boot Actuator:** https://docs.spring.io/spring-boot/reference/actuator/
- **OWASP SSRF Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

The Java/YAML examples are illustrative WebFlux lab code; verify APIs against your actual BOM and run integration tests in an appropriate environment. This article does not replace STEP 6 specialist Content QA.
