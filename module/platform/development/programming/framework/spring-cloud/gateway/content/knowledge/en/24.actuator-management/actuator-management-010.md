# Authorization, Auditing, and Recovery When Route Changes Fail

## 1. Context: Changing One Route Can Break the Entire Entry Point

In a microservices architecture, **Spring Cloud Gateway** centralizes route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, TLS, and request observability. Through **Spring Boot Actuator**, operations teams can inspect active routes and, when authorized, create, delete, or refresh routes without restarting the process.

This is powerful yet carries substantial risk. Suppose route `orders-api` currently forwards:

~~~text
GET /api/orders/42
  -> Spring Cloud Gateway
  -> lb://ORDER-SERVICE
  -> GET /orders/42
~~~

An operator accidentally changes the URI to the wrong host, alters `StripPrefix`, sets an overly broad `Path=/api/**`, or references a filter not installed on one replica. The consequences can include:

- Valid APIs returning mass `404`, `502`, or `503` responses.
- Requests hitting the wrong service, potentially leaking `Authorization` headers or customer data.
- Gateway replicas holding divergent route caches, producing intermittent failures.
- An Actuator route edit returning HTTP success while asynchronous refresh fails.
- Operations teams not knowing **who changed what, or what the route looked like previously**, making rollback slow or inaccurate.

This lesson belongs to the **Actuator Management** chapter of the `SPRING_CLOUD_GATEWAY` module, covering **authorization, auditing, and recovery when route changes fail**. The goal is building a governed management workflow rather than merely memorizing a `curl` command to add/delete routes.

After this lesson, you will be able to:

1. Distinguish three layers: **Actuator endpoint access**, **HTTP exposure**, and **authentication/authorization/network access**.
2. Design **viewer, operator, approver, and automation** permissions under the least-privilege principle.
3. Capture an audit trail recording **actor, timestamp, diff, revision, approval, refresh outcome, and rollback**.
4. Understand the limits of CRUD/refresh via `/actuator/gateway`, especially across multiple Gateway replicas.
5. Handle invalid routes, accidentally deleted routes, unapplied changes, or partially applied changes.
6. Design a testable **validate → stage → publish → refresh → verify → rollback/reconcile** workflow.
7. Keep TLS, tokens, secrets, Redis, and upstreams secure when the Gateway is dynamically managed.

> **Scope:** focuses on **Spring Cloud Gateway Server WebFlux**, Spring Boot Actuator, and reactive Spring Security. Properties and code examples must be checked against your running Spring Boot/Spring Cloud release train. **Gateway Server MVC** uses a different stack; do not copy WebFlux `SecurityWebFilterChain` verbatim to MVC. This lesson is design and testing guidance, not a substitute for subsequent Content QA.

## 2. Threat Model: Route Management Endpoints Are Not Ordinary APIs

A business API like `GET /api/orders/42` returns data governed by routes, security filters, and backend authorization. By contrast, `POST /actuator/gateway/routes/{id}` can **alter the very path** that business requests traverse.

High-risk management actions:

| Action | Typical Risk | Recommended Permission Level |
| --- | --- | --- |
| List routes | Exposes upstream names, internal hosts/ports, filter names/metadata | Authenticated viewer or controlled management access |
| Inspect a single route | Exposes predicate structure, rewrites, service mappings | Viewer |
| Create route | Exposes internal services, routes to wrong host | Write-authorized operator, gated by validation |
| Delete route | Breaks access to valid APIs | Operator through change workflow |
| Refresh cache | Triggers configuration shifts; reload failures, load spikes | Authorized operator or automation |
| Modify route group | Policy mismatches across APIs | Release-authorized user, approval workflow |
| Alter auth routes | Auth bypass or credential leaks if misdesigned | Sensitive change, elevated review |

Threats do not come only from external attackers. An over-privileged CI script, an on-call engineer editing the wrong route ID, or an operator targeting the wrong environment can all cause outages. You therefore need **authorization + auditing + recovery**, designing for both prevention and failure response.

### 2.1. Safe Management Flow

~~~mermaid
flowchart TD
    U["Operator / CI-CD"] --> I["Identity / RBAC / MFA"]
    I --> CP["Route management control plane"]
    CP --> V{"Schema + policy + approval valid?"}
    V -->|No| DENY["Reject and audit denied"]
    V -->|Yes| SNAP["Capture current snapshot + revision"]
    SNAP --> SAVE["Save candidate / route definitions"]
    SAVE --> EVT["Emit refresh event to Gateway replicas"]
    EVT --> VERIFY{"Verified route applied?"}
    VERIFY -->|Yes| OK["Audit applied + monitoring"]
    VERIFY -->|No| ROLLBACK["Restore good snapshot + refresh + verify"]
    ROLLBACK --> AUD["Audit failure and rollback"]
~~~

The **control plane** and approval/rollback steps in this diagram are architectures you build or integrate with existing organizational systems; they are **not built-in features automatically provided by Gateway Actuator**.

## 3. Which Management APIs Does Gateway Actuator Expose?

Characteristic endpoints of Spring Cloud Gateway Server WebFlux:

| HTTP | Endpoint | Purpose | Recommendation |
| --- | --- | --- | --- |
| `GET` | `/actuator/gateway` | Lists available operations | Management network only |
| `GET` | `/actuator/gateway/routes` | Views effective routes | Authorized viewers |
| `GET` | `/actuator/gateway/routedefinitions` | Views definitions per implementation/version | Authorized viewers |
| `GET` | `/actuator/gateway/routes/{id}` | Views one route by ID | Authorized viewers |
| `GET` | `/actuator/gateway/globalfilters` | Views global filters | Information-controlled |
| `GET` | `/actuator/gateway/routefilters` | Views filter factories | Information-controlled |
| `POST` | `/actuator/gateway/routes/{id}` | Creates a dynamic route via writer | Write permission, validation, audit |
| `DELETE` | `/actuator/gateway/routes/{id}` | Deletes a dynamic route | Write permission, approval/rollback |
| `POST` | `/actuator/gateway/refresh` | Requests refreshing local route cache | Write permission, rate-limited |
| `POST` | `/actuator/gateway/routes` | Creates multiple routes where supported by version | Write permission, validate entire batch |

**Not every route can be deleted via Actuator.** Routes from `application.yml` or `@Bean RouteLocator` do not automatically become records editable/deletable via `RouteDefinitionWriter`. Gateway 5.x docs specify that only Actuator-managed routes can be manipulated through the corresponding API; deleting static config routes may return `404`.

Output from `GET /actuator/gateway/routes/{id}` is generally a display representation of built routes; **never feed GET output verbatim as POST JSON**. The route creation API expects predicate/filter shortcuts like `"Path=/api/orders/**"`, `"StripPrefix=1"`, or the schema documented for your version.

### 3.1. Management Privileges Do Not Equal API Usage Privileges

A user permitted to call `GET /api/orders/**` with `SCOPE_orders.read` has **no** reason to view or modify `/actuator/gateway/routes`. Conversely, a route operator may not be authorized to read customer orders.

Use **separate principals/roles/scopes** for management APIs—never reuse ordinary frontend/user permissions for route administration.

## 4. Three Mandatory Layers to Protect Gateway Actuator

### 4.1. Layer 1: Endpoint Access

In newer Spring Boot/Gateway branches, `management.endpoint.gateway.access` plays a pivotal role:

| Value | Expected Behavior | When to Use |
| --- | --- | --- |
| `none` | Denies access to the gateway Actuator endpoint | Environments needing no HTTP route management |
| `read-only` | Provides read operations only; forbids create/delete/refresh | **Recommended default when observation is needed** |
| `unrestricted` | Allows management operations supported by the endpoint | Only after network/auth/RBAC/audit are in place |

Per **current Spring Cloud Gateway documentation**, the Gateway Actuator endpoint has **access disabled by default**. For observation, grant read access and expose the endpoint accordingly. For creating, deleting, or refreshing routes, a higher access level and strict protections are required.

Older lines use `management.endpoint.gateway.enabled`. Never enable both old and new properties indiscriminately assuming precedence; configure for your exact release train.

### 4.2. Layer 2: Exposure over HTTP/JMX

Even when an endpoint has access enabled, it only appears on the HTTP surface when exposed by config:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

This is an **observation-only configuration**, not network security or universal user authorization. In Spring Boot, typically only endpoints like `health` are exposed by default; inspect the application's effective configuration.

Be careful with:

~~~yaml
# NOT RECOMMENDED on public production:
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

`*` in YAML must be quoted. Exposing all actuator endpoints can reveal `env`, `beans`, `loggers`, `heapdump`, or other sensitive capabilities depending on the app. **Never open everything just to use one Gateway endpoint.**

Beyond HTTP exposure, inspect **JMX exposure** and permissions if infrastructure can reach JMX. Locking down HTTP does not automatically govern every management transport.

### 4.3. Layer 3: Network + Authentication + Authorization

`access: unrestricted` **does not mean only admins can call it**. It merely enables available operations; who can invoke them depends on:

- Network policies, firewalls, ingress/service mesh.
- TLS/mTLS and client identity verification.
- Spring Security `SecurityWebFilterChain` or protections at a reverse proxy/control plane.
- RBAC by HTTP method, endpoint, and route ID.
- Change-approval policies and credential locking.
- Rate limiting/abuse protection on management endpoints.
- Protected audit logs.

Similarly, `read-only` blocks mutating operations via the endpoint yet can still **leak topology** if anyone can read the route list.

**All three layers are required simultaneously—never one out of three.**

## 5. Safe Default Configuration for Observation

Reference configuration for a Gateway using compatible Spring Boot 3.5/SCG WebFlux:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Expectations:

1. `GET /actuator/gateway/routes` can be served when identity and network permit.
2. `POST /actuator/gateway/refresh` is disallowed by `read-only` configuration.
3. `POST /actuator/gateway/routes/{id}` and `DELETE` are disallowed.
4. `health.show-details: never` keeps health response details minimal in this example.
5. Isolated management networking, authentication, and authorization remain required.

**Do not assume the blocked status is always 403.** Depending on which layer blocks the request, an unexposed endpoint may return `404`, a disallowed method `405`, missing token `401`, and missing scope `403`. The objective is **preventing execution**, then diagnosing by layer.

### 5.1. Separating the Management Listener from the Public Gateway

Spring Boot supports running on a dedicated management port, e.g., in a network-managed environment:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

This configuration **separates ports**—it does not isolate the Internet from internal networks by itself. In Kubernetes, if a Service/Ingress publishes port 9090 too, the endpoint remains reachable unauthorized.

Bind the management listener to an internal/loopback address matching your deployment, or expose the port strictly through an admin proxy, port-forward, and verified network policy. **Do not confuse `localhost` inside a container with the admin's workstation.** Never attach the management port to public ingress just to test a curl command.

### 5.2. When Write Operations Are Needed in Staging

Strictly in a protected management environment, you can configure:

~~~yaml
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Complete these prerequisites before enabling:

- Management port is non-public, guarded by firewall/NetworkPolicy.
- Strong authentication (management OAuth2 access tokens, mTLS, service identities, or equivalent).
- Dedicated scopes/roles separating read and write.
- Durable audit trail recording tickets, revisions, and approvals as needed.
- Tested route validation, snapshots, and rollback.
- Zero secret values in request bodies or responses.

**Never enable `unrestricted` in production first and plan to add security later.**

## 6. Least-Privilege Authorization for Route Management

### 6.1. Role-by-Operation Matrix

| Illustrative Role / Scope | Read Routes | Propose Change | Apply Change | Refresh | Rollback |
| --- | --- | --- | --- | --- | --- |
| `gateway.routes.read` | Yes | No | No | No | No |
| `gateway.routes.propose` | Yes | Yes, via control plane | No | No | No |
| `gateway.routes.approve` | Yes | Yes | Approves changes proposed by others | Not directly | Approves when needed |
| `gateway.routes.write` | Yes | Per workflow | Yes, under strict policy | Yes | Yes, via procedure |
| `gateway.routes.reconcile` | Needed data only | No | Creates no new candidates | Yes, for approved revisions | Never ad-hoc |

This is a **recommended role model**, not a built-in authority list created by Spring Cloud Gateway. Enforce it via your identity provider and control plane, applying **separation of duties** for sensitive changes.

In multi-team organizations, a single broad write role is still too permissive. An operator managing `/api/catalog/**` should not automatically edit payment or auth service routes. Implement **route-level authorization** in the control plane covering namespaces, owners, environments, target URIs, and allowed filter types.

### 6.2. HTTP Methods Alone Are Insufficient for Business Authorization

Spring Security can distinguish GET/POST/DELETE on the Actuator path. However, checking:

- Should this user edit only **catalog** routes or **orders** routes?
- Does a change widen access via `RemoveRequestHeader`?
- Is the new URI within the organization's allowlist?
- Does the change require two-person approval?
- Is a production deployment freeze active?

are **administrative business policies**, not guarantees provided solely by `.hasAuthority("SCOPE_gateway.routes.write")`.

In production, therefore, use a **control plane** enforcing granular validation/RBAC and allow only the control plane's automation identity to call Actuator write endpoints over a private network.

## 7. Reactive Spring Security Example Protecting Actuator

### 7.1. `SecurityWebFilterChain` by Path and Method

The example below illustrates separating a **management chain** from an **application API chain** when both run on WebFlux. Assumptions:

- Admins call with an OAuth2 **Bearer JWT** holding `SCOPE_gateway.routes.read` or `SCOPE_gateway.routes.write`.
- Issuer, audience, JWK, and token validation rules are properly configured.
- The management API genuinely uses the deployment's `/actuator/**` path.
- APIs are protected by **stateless** bearer tokens; browser cookies/sessions are not used as admin credentials.

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/actuator/**"))
            // Consider disabling CSRF only because this admin API uses
            // stateless Bearer tokens, not browser sessions/cookies.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/actuator/gateway/**")
                    .hasAnyAuthority(
                        "SCOPE_gateway.routes.read",
                        "SCOPE_gateway.routes.write")
                .pathMatchers(HttpMethod.POST, "/actuator/gateway/**")
                    .hasAuthority("SCOPE_gateway.routes.write")
                .pathMatchers(HttpMethod.DELETE, "/actuator/gateway/**")
                    .hasAuthority("SCOPE_gateway.routes.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Critical limitations of this example:**

1. It lacks route-ID-level business authorization; the write scope is broader than many organizations allow.
2. It omits Security/Resource Server dependencies, issuer/JWK config, `aud` validation, TLS, and management networking.
3. If `management.endpoints.web.base-path` or context path changes, matchers must be updated.
4. **When the management port creates a separate context**, verify which `SecurityWebFilterChain` beans actually apply to the management context on your exact Boot version. Never assume app-context beans protect all HTTP listeners in every topology.
5. Disabling CSRF is **strictly conditional** on truly stateless/Bearer APIs. If a management UI uses browser cookies/sessions, configure dedicated CSRF protection.
6. Defining a custom `SecurityWebFilterChain` may cause Boot to **stop applying default Actuator security rules**. Test every endpoint, not just `gateway`.
7. For opaque tokens/introspection, use `opaqueToken` Resource Server config instead of `jwt`; this example assumes JWTs.

The core takeaway is writing explicit, testable security rules—**never rely on a Java snippet to claim an endpoint is safe without testing the real listener and live requests**.

### 7.2. Why Should Actuator Never Be Exposed Through a Public Route?

If you create a Gateway route:

~~~yaml
# ANTI-PATTERN: never expose management via a route like this.
- id: expose-admin
  uri: http://localhost:9090
  predicates:
    - Path=/admin/**
  filters:
    - StripPrefix=1
~~~

you can inadvertently push CRUD/refresh onto the public data plane, creating circular interactions or misconfigurations across auth, rate limiting, and circuit breakers. Managing through a separate management network/control plane with end-to-end authorization and monitoring is far safer.

Never treat `/secret-admin` or `/actuator` path names as a security layer. Security by obscurity cannot withstand direct API probing.

## 8. Auditing: Must Answer Who, What, When, and Outcome

An **audit trail** is a verifiable sequence of records tracking the change lifecycle. Access logs only show an HTTP POST/DELETE hit Actuator; a log line like:

~~~text
POST /actuator/gateway/routes/orders-api -> 201
~~~

**is insufficient** because it records neither the approver, old snapshot, new route, per-replica refresh outcomes, nor rollback status.

### 8.1. Essential Audit Fields

| Field | Purpose |
| --- | --- |
| `changeId` | Links proposal, approval, publish, refresh, and rollback |
| `actor` | Authenticated identity (subject/service identity), never arbitrary client headers |
| `source` | CI pipeline, operator console, emergency change |
| `environment` | staging/production/region/cluster |
| `routeId` or route list | Target of the change |
| `action` | CREATE, DELETE, UPDATE, REFRESH, ROLLBACK |
| `reason` / `ticket` | Business/technical justification, change-management link |
| `approval` | Approver identity or valid automated policy |
| `beforeRevision`, `afterRevision` | Verifies ordering and prevents lost updates |
| `beforeDigest`, `afterDigest` | Canonicalized snapshot fingerprints |
| `validationResult` | Policy/schema/security/compatibility pass/fail |
| `storeResult` | Whether writing to the shared source succeeded |
| `refreshResults` | Which replicas received/applied it, and where failures occurred |
| `finalState` | APPLIED, PARTIAL, FAILED, ROLLED_BACK |
| `timestamp`, `correlationId` | Investigation and log/trace correlation |

Log only necessary details: URIs/metadata can reveal topology; raw tokens, `Authorization` headers, cookies, client secrets, and private keys must be **stripped or encrypted/redacted** per policy.

### 8.2. Sample Audit Event

~~~json
{
  "eventType": "gateway.route.change",
  "changeId": "chg-2026-0159",
  "actor": {
    "subject": "operator-023",
    "authMethod": "workload-or-admin-identity"
  },
  "environment": "production",
  "routeIds": ["dyn-orders-api"],
  "action": "UPDATE",
  "ticket": "CHG-1542",
  "approval": "approved",
  "beforeRevision": 41,
  "targetRevision": 42,
  "beforeDigest": "sha256:example-before",
  "afterDigest": "sha256:example-after",
  "validationResult": "PASS",
  "publishResult": "COMMITTED",
  "replicaResults": {
    "gateway-a": "APPLIED",
    "gateway-b": "APPLIED",
    "gateway-c": "FAILED"
  },
  "finalState": "PARTIAL",
  "recordedAt": "2026-11-24T09:20:00Z"
}
~~~

This is an **illustrative design schema**, not JSON emitted by Spring Cloud Gateway out of the box. The `sha256:example-...` values are placeholders; real systems compute digests over canonicalized route snapshots and never treat hashes as digital signatures.

**`PARTIAL` is a critical state.** An operation can commit the shared route successfully while failing to apply on every Gateway replica; audits must record the truth instead of marking `SUCCESS` as soon as Actuator returns 200.

### 8.3. Audit Logs Must Be Durable and Tamper-Resistant

Do not log audits solely to `System.out` on one pod, because a pod can be replaced mid-incident. Production should use:

- A centralized audit service or log pipeline with strict access controls.
- Append-only or immutable/WORM retention if required by compliance.
- Synchronized UTC clocks and correlation IDs.
- Retention, redaction, encryption, and audit-read access policies.
- Safeguards preventing loss of **change intent and commit records** during temporary log-pipeline outages.

When using a database/outbox, persist **the change + audit/outbox record in the same transaction** where storage architecture allows. Never assume Actuator CRUD and an external audit system form an atomic transaction automatically.

### 8.4. Is Spring Boot `auditevents` Enough?

Spring Boot Actuator exposes `/actuator/auditevents` when audit infrastructure is configured. It helps for certain security/audit events, yet **does not automatically record full before/after route diffs for every route create/delete**.

For complete route management history, **instrument the control plane or wrap write/refresh operations**. Seeing no before/after route content in `auditevents` does not mean no change occurred.

## 9. Route Change Lifecycle: From Proposal to Applied Revision

A safe change should have a lifecycle independent of the HTTP status of one management request.

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Operator / CI
    participant C as Control Plane
    participant R as Route Store
    participant B as Change Bus
    participant A as Gateway A
    participant G as Gateway B
    O->>C: Proposal + baseRevision=41
    C->>C: RBAC + approval + validate route
    C->>R: Read snapshot v41, check CAS
    R-->>C: Snapshot v41
    C->>R: Save snapshot/candidate v42
    R-->>C: Persisted
    C->>B: routes.changed(revision=42)
    B-->>A: Signal 42
    B-->>G: Signal 42
    A->>R: Read v42
    G->>R: Read v42
    A->>A: Refresh + verify effective routes
    G->>G: Refresh + verify effective routes
    A-->>C: APPLIED 42
    G-->>C: FAILED 42
    C->>C: Audit PARTIAL + activate rollback policy
~~~

**The CAS, revisioning, bus, ACK, and auto-rollback steps above are additional control layers—they do not come out of the box from an Actuator HTTP endpoint alone.**

### 9.1. Before Writing: Validate the Candidate

Every candidate `RouteDefinition` must pass these checks:

1. **Route ID:** unique, with namespace/owner, never overwriting static routes.
2. **URI scheme/host:** allowlist `lb`/HTTPS and approved domains/service IDs; reject arbitrary client-supplied hosts.
3. **Path/Host/Method predicates:** never widen unexpectedly into `/actuator`, admin paths, or other routes.
4. **Order/priority:** never hijack higher-priority routes to cause bypasses.
5. **Filter factories:** filter names exist across all running binary versions; args are valid.
6. **Headers:** never add/strip `Authorization`/`Cookie`/`Forwarded` in ways that leak credentials or break trust boundaries.
7. **Security impact:** authentication, authorization, TLS, rate limiting, retries, and circuit breakers remain intact.
8. **Cross-route conflicts:** path overlaps, duplicate IDs, orphan routes, fallback loops.
9. **Resilience:** upstream dependencies, load balancer instances, and timeouts are acceptable.
10. **Rollback plan:** prior snapshot, version, and ability to restore known-good config exist upfront.

**Never judge a route valid by JSON syntax alone.** `uri: http://169.254.169.254` is syntactically valid yet causes SSRF / cloud metadata exposure; `Path=/**` is syntactically valid yet matches far too broadly.

### 9.2. Distinguishing Change States

| State | Meaning |
| --- | --- |
| `PROPOSED` | Change requested, awaiting approval |
| `VALIDATED` | Passed schema/policy/compatibility checks |
| `APPROVED` | Holds required authority and approvals |
| `COMMITTED` | Desired definitions persisted |
| `REFRESH_REQUESTED` | Refresh signal dispatched, application not yet proved |
| `APPLIED` | Target replicas verified effective routes match revision |
| `PARTIAL` | Only a subset of replicas/routes applied successfully |
| `FAILED` | Validation, write, or refresh/apply failed |
| `ROLLBACK_REQUESTED` | Restoration of known-good snapshot initiated |
| `ROLLED_BACK` | Verified effective routes reverted to safe content |

Never jump straight from `COMMITTED → APPLIED` simply because `POST /actuator/gateway/refresh` returned `200`. That is an especially dangerous observability mistake in multi-replica clusters.

## 10. Actuator Command Examples in a Secured Staging Environment

> **Warning:** run these commands strictly inside an **authenticated management network** or isolated staging. Never copy into public shells, never omit authorization, and never run on production outside the change process. `ADMIN_TOKEN` must be supplied via a secret manager or secured identity flow; never paste real tokens into tickets or logs.

### 10.1. Target Each Replica's Exact Endpoint

~~~bash
# Hostnames are illustrative examples; not real systems.
export ADMIN_A="https://gateway-a-admin.internal.example"
export ADMIN_B="https://gateway-b-admin.internal.example"

# ADMIN_TOKEN must be supplied over a secure channel.
# Never export real secret values in docs or screenshots.
~~~

**Never use a single load-balanced public URL** for multi-replica verification/refresh: two consecutive calls might both hit A.

### 10.2. Snapshot Before Modifying

~~~bash
# Read current routes and save into a protected snapshot store.
curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes"
~~~

`GET /routes` is great for **observing effective routes**, yet its display output **is not necessarily a writable route definition you can POST back**. Recoverable snapshots must store **source-of-truth definitions** in writable format, along with revision, order, metadata, hashes/diffs, and matching policies.

If a route lives in YAML/Java DSL, edit it in the config management source and deploy/refresh properly—do not expect the Actuator writer to turn it into a dynamic route.

### 10.3. Create a Test Route

A new demo route (non-colliding ID):

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo" \
  --data '{
    "predicates": ["Path=/api/orders/**"],
    "filters": ["StripPrefix=1"],
    "uri": "lb://ORDER-SERVICE",
    "order": 0
  }'
~~~

This is the shortcut DSL described in Gateway Actuator docs. Ensure `ORDER-SERVICE` exists in the mock/registry and `Path=/api/orders/**` **does not conflict** with existing routes first. Recent Gateway docs note successful creation can return **201 Created**.

**Never POST to an already-existing ID.** Gateway 5.x docs warn this can cause duplicate internal definitions and 500 errors when querying routes. To update an Actuator-created route, versions may require deleting and recreating; that sequence is non-atomic with a gap, so production requires a dedicated control-plane/snapshot workflow.

### 10.4. Refresh A and Verify

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo"
~~~

`POST /refresh` may return **200 with an empty body**. **Do not declare success from 200 alone**, because refresh may run asynchronously and route construction can fail.

Next, verify:

- Does `GET /routes` show the expected ID/URI/order/predicates/filters?
- Does a synthetic request routed specifically to **gateway-a** hit the right path?
- Does the audit record write `APPLIED` only after actual verification?
- Are there any new 404/5xx errors or route conflicts?
- Under security policies, was the route opened too broadly?

### 10.5. B and Other Replicas

With a **shared route repository** like Redis, B can read the same definition yet keep its **old local route cache**. Refresh/verify each replica via its dedicated management endpoint or node-local event subscriber:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/refresh"

curl -fsS \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_B/actuator/gateway/routes/dyn-orders-demo"
~~~

If A uses `InMemoryRouteDefinitionRepository`, a route created on A will not appear on B simply by refreshing B. Verify the shared source rather than treating refresh as cluster data replication.

### 10.6. Delete the Route in Staging

~~~bash
curl -i -X DELETE \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/routes/dyn-orders-demo"

curl -i -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$ADMIN_A/actuator/gateway/refresh"
~~~

Deletion must be accompanied by audits and snapshots. In this exercise, delete only the `dyn-orders-demo` ID you created in staging; **never use examples to delete routes serving real users**.

## 11. Asynchronous Refresh and Differences Across Three Outcomes

### 11.1. Source Write Outcome

A route save returning success only indicates `RouteDefinitionWriter` accepted/persisted it per the repository implementation.

- **In-memory:** only that JVM holds the new definitions.
- **Redis shared repository:** replicas can read the new definitions from shared Redis.
- **Git/Config Server:** still requires config reload via the compatible mechanism.

**A successful save does not mean the Gateway is serving the route.**

### 11.2. Local Refresh Outcome

`POST /actuator/gateway/refresh` requests clearing/refreshing the cache **of the instance receiving the call**. Current Gateway docs note that errors during **asynchronous refresh** may leave existing active routes unchanged. Verify this exact behavior on your release—**it is not a durable last-known-good guarantee across all repository types**.

Requests already routed before refresh may continue using the old route until they finish. Refresh is not a transaction that “immediately switches all in-flight requests”.

### 11.3. Cluster-Wide Application Outcome

Across multiple Gateway replicas, you must:

1. Write the **desired revision** to the shared source.
2. Fan out signals (event bus/agent/control plane) to **every replica**.
3. Trigger local refresh on each node.
4. Read back effective routes and verify behavior on that node.
5. Record each node's **applied revision**.
6. Mark `APPLIED` only when required nodes have converged; otherwise mark `PARTIAL` or `FAILED`.
7. Reconcile when nodes miss events, restart, or lose store connectivity.

A single HTTP 200 does not prove a multi-node cluster has updated.

## 12. Failure Modes to Distinguish

| Failure Type | Symptoms | Possible Causes | First Response |
| --- | --- | --- | --- |
| **Unauthorized** | 401/403 on admin endpoint | Bad token/scope, CSRF, or RBAC | Never retry with old credentials; verify permissions |
| **Endpoint unavailable** | 404/405 | Gateway Actuator disabled/`read-only`/unexposed, wrong path/version | Check access/exposure/matchers |
| **Validation failed** | 4xx or control-plane rejection | Invalid predicate/filter args/URI | Do not publish candidate |
| **Route build failed** | Refresh reports/logs error | Missing custom filter, bad URI/filter config | Preserve safe state; roll back candidate |
| **Store write failed** | Redis/DB timeout/5xx | Network, auth, Redis outage | Never emit fake `COMMITTED` events |
| **Refresh event lost** | A updated, B stale | Bus/PubSub drop, node offline | Reconcile desired vs applied |
| **Mixed snapshot** | Some routes new, others old | Non-atomic per-route CRUD | Use versioned snapshots/rollback |
| **Conflicting route** | Requests take wrong route, 404/5xx | Path overlap, order, duplicate ID | Compare effective routes; halt rollout |
| **Security regression** | Sensitive endpoint lost auth | Mis-edited filter/predicate | Emergency policy block; roll back |
| **Upstream unavailable** | 502/503 after new route | `lb://` lacks instances, DNS/TLS error | Check discovery/URI; roll back if caused by change |
| **Success mismatch** | Actuator 200 yet traffic still fails | Misapplied or unrelated business fault | Synthetic test + per-node trace |
| **Audit pipeline failed** | Missing required events | Log pipeline/store outage | Flag change unconfirmed; reconcile |

**Do not lump every 5xx into “route refresh failed”.** A route can apply cleanly while the upstream is dead or its TLS certificate expired; pinpoint the failing layer and timing before rolling back.

## 13. Recovery Runbook When a Route Change Fails

### 13.1. Emergency Procedure

When a route change breaks production:

1. **Freeze further changes** to the same route/namespace so two operators do not roll back and overwrite each other.
2. **Triage blast radius:** which route IDs, regions/replicas, 4xx/5xx rates, auth impacts, or credential leaks?
3. **Preserve evidence:** current desired revision, per-node effective routes, audit change ID, and redacted error logs.
4. **Block dangerous paths immediately:** if traffic routes to unauthorized hosts, apply extra network policy/firewall/WAF/identity revocation while recovering.
5. **Fetch the last-known-good snapshot** from the protected versioned store; never hand-copy verbose GET responses into POST JSON.
6. **Apply a versioned rollback** via the control plane or approved management workflow.
7. **Refresh each node** / broadcast cluster event via the verified mechanism.
8. **Verify** route definitions, path/URI/order, authentication, and synthetic requests across nodes.
9. **Monitor stability:** 404/5xx, p95/p99 latency, upstream metrics, rate limiting, and security events.
10. **Audit the incident:** who authorized rollback, from/to revisions, success/partial/failure outcome, timeline, and lessons learned.

### 13.2. Decision Flowchart

~~~mermaid
flowchart TD
    A["Failure detected after route change"] --> B{"Security / SSRF risk?"}
    B -->|Yes| C["Emergency network/auth block; halt rollout"]
    B -->|No| D["Compare desired vs applied"]
    C --> D
    D --> E{"Failure isolated to one replica?"}
    E -->|Yes| F["Reconcile/refresh that node, test"]
    E -->|No| G["Evaluate candidate and known-good snapshot"]
    F --> H{"Node converged and traffic healthy?"}
    H -->|Yes| I["Audit recovered + monitor"]
    H -->|No| G
    G --> J["Publish new rollback revision"]
    J --> K["Refresh all affected replicas"]
    K --> L{"Verify all replicas + auth + upstream"}
    L -->|Pass| I
    L -->|Fail| M["Keep incident open; isolate node/route; escalate"]
~~~

**Never repeatedly refresh a broken route definition**: if the definition is invalid, refreshing repeatedly will never make it valid. Fix it or revert to a known-good snapshot first, then refresh.

## 14. Recovery Example: Filter Missing on `gateway-b`

**State before change:**

~~~yaml
# Illustrative route definition at revision 41.
id: dyn-orders-api
uri: lb://ORDER-SERVICE
predicates:
  - Path=/api/orders/**
filters:
  - StripPrefix=1
order: 0
~~~

An operator wants to add a custom filter `VerifyPartnerHeader` and creates revision 42. However:

- `gateway-a` already deployed the binary containing `VerifyPartnerHeaderGatewayFilterFactory`.
- `gateway-b` still runs the older binary, **lacking that factory**.
- `gateway-c` temporarily lost Redis connectivity.

Outcome:

~~~text
Desired revision: 42

gateway-a: applied 42
gateway-b: failed route conversion
gateway-c: still applied 41

Change status: PARTIAL
~~~

**Wrong response:** looking only at the Redis POST response and marking `SUCCESS`, or infinitely retrying refresh on B.

**Right response:**

1. Audit `PARTIAL` with the filter compatibility error.
2. Halt rollout, blocking new candidates on the same route from publishing.
3. Choose to roll back to the known-good content of revision 41.
4. Publish **revision 43 containing content equivalent to v41**, rather than re-emitting revision number 41 which monotonic consumers would ignore as stale.
5. A/B/C load revision 43, refresh, and verify; if C is offline, schedule reconciliation when it returns.
6. Audit `ROLLED_BACK` **only after** all target nodes take effect properly; while any node remains stale, keep status `PARTIAL`.
7. Plan deploying the filter binary across all replicas before attempting another revision.

Note: basic `RedisRouteDefinitionRepository` does not provide **versioned snapshots + monotonic rollbacks** out of the box. That architecture must be added to your control plane/repository—`POST /refresh` itself does not mint new revisions.

### 14.1. What If Only Manual Actuator CRUD Exists?

If a dynamic route was created via Actuator and your version's API requires **delete then create** to update an existing ID, an emergency procedure could be:

~~~text
1. Snapshot old definition in writable format.
2. DELETE failing route ID on the active source.
3. POST that route ID with the verified definition.
4. POST /gateway/refresh on the target node.
5. Refresh/verify remaining replicas if using a shared source.
6. Test live behavior and record audit.
~~~

**Warning:** between steps 2 and 3 the route may be absent; with caches/replicas, observed state may be inconsistent. Never claim this is an **atomic update/zero-downtime rollback**. Where strict safety is needed, use versioned snapshots, staged rollouts, or coordinated deployments.

## 15. Rollback Differs from In-Memory “Undo”

Three things must revert cleanly:

1. **Desired route definitions** in the shared repository/Git/control plane.
2. **Effective route cache** inside every Gateway JVM.
3. **State of related systems** such as ConfigMaps, service discovery, auth policies, filter binaries, and network policies.

Refreshing only local caches while desired definitions still hold the bad route lets nodes reload the fault. Editing only the shared source without refreshing leaves nodes running old routes. If a route references a custom filter removed from the binary, rolling back that definition can also fail if the snapshot is incompatible.

A **last-known-good snapshot** should include:

| Component | Contents to Store |
| --- | --- |
| Route definitions | ID, URI, predicates, filters, order, metadata |
| Revision / digest | Monotonic version or commit hash |
| Compatibility | Release train, custom filter factories, schema |
| Security policies | Non-negotiable invariants |
| Dependencies | Service registry, TLS truststore, Redis config |
| Validation report | Synthetic tests that passed |
| Rollback instructions | How to re-apply/refresh/verify per node |
| Audit references | Change ID, operator/approval, incident |

When updating **multiple related routes**, writing one route at a time can create a **mixed-version snapshot**. Consider transactional sources, versioned namespaces/active revision pointers, or staged activation. Plain Actuator CRUD does not guarantee atomicity across a set of dynamic routes.

## 16. Multiple Gateway Replicas and the Truth About Local Refresh

A `RefreshRoutesEvent` published via Spring's `ApplicationEventPublisher` affects only the **local `ApplicationContext`/JVM**. `POST /actuator/gateway/refresh` likewise affects only the **instance receiving the request**.

~~~mermaid
flowchart LR
    CP["Approved route revision 43"] --> STORE[("Shared route store")]
    CP --> BUS["Route change notification"]
    STORE --> A["Gateway A"]
    STORE --> B["Gateway B"]
    STORE --> C["Gateway C"]
    BUS --> A
    BUS --> B
    BUS --> C
    A --> ACK["Convergence monitor"]
    B --> ACK
    C --> ACK
~~~

With `InMemoryRouteDefinitionRepository`, writing a route on A does not give B the new definition; **refreshing B does not resolve differing data sources either**. `RedisRouteDefinitionRepository` provides shared definitions, yet **you still must notify and refresh each replica**.

A message bus (Redis Pub/Sub, Kafka, RabbitMQ, or Spring Cloud Bus where compatibly configured) can broadcast route-changed notices, yet **the bus delivering a message does not prove the node applied it**.

### 16.1. Desired Revision vs. Applied Revision

Example tracking table:

| Replica | Desired | Applied | Result |
| --- | ---: | ---: | --- |
| gateway-a | 43 | 43 | APPLIED |
| gateway-b | 43 | 43 | APPLIED |
| gateway-c | 43 | 42 | STALE |

Never mark the cluster **`ROLLED_BACK`** while C still serves the faulty v42 route. You may temporarily drain C out of the load balancer until reconciliation/validation succeeds, depending on impact and SLOs.

Apply time must be recorded **after the new route is built/displayed or verified**, not merely after calling local refresh.

### 16.2. Lost Events and Restarts

With Redis Pub/Sub, offline subscribers can miss messages; pair it with periodic reconciliation or a durable bus where appropriate. At startup, each node should compare desired revision against loaded route state before accepting traffic requiring new policies.

Never assume an in-memory cache acts as a **persistent last-known-good** across pod restarts. If the route source is temporarily unavailable, cold-start behavior must be load-tested/chaos-tested with clear handling policies.

## 17. Testing Authorization, Auditing, and Rollback

### 17.1. Permission Matrix

| Case | Actor / Setup | Request | Expected Outcome |
| --- | --- | --- | --- |
| A1 | No credentials | `GET /actuator/gateway/routes` | Denied management data; typically 401 |
| A2 | Reader scope | `GET /actuator/gateway/routes` | Allowed if endpoint exposed/`read-only` |
| A3 | Reader scope | `POST /actuator/gateway/refresh` | Not executed; typically 403/404/405 |
| A4 | Reader scope | `DELETE /actuator/gateway/routes/id` | Not executed; audit denied if required by policy |
| A5 | Writer scope without approval | Propose sensitive route change | Rejected by control plane |
| A6 | Writer scope + valid approval | Edit route within scope | Passes validation, audit, apply/verify |
| A7 | Writer scope | Create route to forbidden host | Rejected by validation/SSRF policy |
| A8 | Token with wrong audience/issuer | Any management call | Authentication rejected |
| A9 | `access: read-only` | POST refresh even with valid writer token | Endpoint refuses write |
| A10 | `access: unrestricted`, outside network allowlist | Admin call from Internet | Denied by network policy |

Assert exact status codes only once security/Actuator versions and network topology are fixed. On blocked endpoints, **no side effect occurring** matters far more than distinguishing 403/404/405 in a general guide.

### 17.2. Failed-Change Matrix

| Case | Situation | Assertion |
| --- | --- | --- |
| F1 | Syntactically invalid predicate | Bad route unpublished; audited `VALIDATION_FAILED` |
| F2 | Custom filter missing on one replica | `PARTIAL`/`FAILED`; failing node never ACKs applied |
| F3 | URI targeting private metadata host | Rejected before write |
| F4 | Duplicate route ID | Creates no duplicate record; audits conflict |
| F5 | Redis write timeout | Emits no false `COMMITTED` message |
| F6 | Refresh returns 200 yet cache unchanged | Applied remains at old revision |
| F7 | Bus drops event while node offline | Reconciliation restores target revision |
| F8 | Stale v42 event arrives after v43 | Consumer does not mistakenly roll back to v42 |
| F9 | Two operators edit same revision | CAS/optimistic concurrency prevents lost updates |
| F10 | Two routes must change together | Snapshot avoids unauthorized mixed-version states |
| F11 | Rollback v43 carries v41 content | All nodes resume safe behavior |
| F12 | One node still serves faulty route | Cluster is never marked `ROLLED_BACK` |
| F13 | Audit store temporarily down | Change workflow marks state unclear, never fakes success |
| F14 | In-flight request via old route | In-flight behavior is predictable and tested |
| F15 | Actuator admin token leaked | Credential revocation, network block, and incident audit exist |

### 17.3. Testing with `WebTestClient`

The snippet below is an **authorization test skeleton**, requiring an application started with Spring Security, Actuator, and test identities:

~~~java
// WebFlux Security testing pseudocode:
// clientWithoutToken.get("/actuator/gateway/routes")
//     -> expect 401 when endpoint is exposed yet requires auth.
//
// clientWithReader.get("/actuator/gateway/routes")
//     -> expect 200.
//
// clientWithReader.post("/actuator/gateway/refresh")
//     -> expect write rejected and route cache unchanged.
//
// clientWithWriter.post("/actuator/gateway/refresh")
//     -> expect request accepted if access=unrestricted,
//        then continue verifying new effective routes.
~~~

**This is not a standalone runnable Java test class**; it needs `WebTestClient`, mock JWT/opaque tokens, server ports, and proper test configs. With a separate management port, tests must hit the **management listener**, not solely the main Gateway port.

To prove refresh does not break auth, test security endpoints both before and after changes alongside live synthetic traffic through predicates and filter chains.

### 17.4. Observing Route Behavior with Synthetic Requests

After every change, test at least:

1. A valid GET request through the new route.
2. A similar path that should **not** match.
3. A request missing a token: still rejected at the security layer.
4. A request missing a scope: still 403 per policy.
5. A request with restricted headers: never leaks `Authorization` to the wrong host.
6. An `lb://` request with and without service registry instances.
7. Requests routed through each Gateway replica individually, not solely the public load balancer.
8. Routes using `RewritePath`, `StripPrefix`, rate limits, circuit breakers, or retries preserving approved behavior.

This is **business and security verification**, not just “route count went from 10 to 11”.

## 18. SLOs, Metrics, and Alerts for Route Management

Signals to collect:

| Metric / Observation | Rationale |
| --- | --- |
| `gateway_route_change_requests_total` | Count proposals/creates/deletes/refreshes by actor class/env |
| `gateway_route_change_denied_total` | Spot abuse or misconfigured policies |
| `gateway_route_validation_failures_total` | Track invalid candidates |
| `gateway_route_refresh_attempts_total` | Count local refreshes and errors |
| `gateway_route_applied_revision` | Track which nodes converged |
| `gateway_route_convergence_lag_seconds` | Alert when stale nodes exceed threshold |
| `gateway_route_rollback_total` | Count rollbacks and root causes |
| HTTP 404/5xx per route/node | Catch post-rollout regressions |
| p95/p99 latency and upstream errors | Distinguish routing errors from service errors |
| Security audit events | Monitor unauthorized management API calls |

**The `gateway_route_...` metric names above are suggested custom instrumentation**, not all built-in metrics provided out of the box by Spring Cloud Gateway/Micrometer.

Never put arbitrary raw route URIs, request IDs, access tokens, or long change descriptions into **metric labels** due to cardinality explosion and sensitivity risks. Use controlled route IDs, environments, and outcome classes as dimensions; keep audit details in protected logs.

### 18.1. Useful Alerts

- Unapproved write/refresh attempts.
- Actuator management API called from outside the network allowlist.
- Desired revision diverging from applied revision beyond SLA.
- A node reporting repeated refresh failures.
- Spikes in 404/5xx or auth failures following a change.
- URI/route count/order drifting from baseline without a change ID.
- Audit pipeline dropping data or failing writes.
- Requested rollback failing to converge within policy limits.

## 19. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Setting only `management.endpoint.gateway.access: unrestricted` | Write operations exposed without HTTP protection | Network isolation + auth + RBAC + auditing |
| Exposing `*` on public API | Exposes unnecessary actuator endpoints | Expose only required IDs |
| Using user tokens for route admin | Grants unintended privileges | Separate admin identities/scopes |
| Writing custom `SecurityWebFilterChain` and forgetting Actuator | Boot auto-security may back off | Match and test management explicitly |
| Disabling CSRF for apps using cookie logins | Increases CSRF risk | Disable only when truly stateless/Bearer |
| Trusting unverified `X-User`/IP headers in audits | Audit actor can be spoofed | Extract from verified principal and trusted proxies |
| Treating 201/200 as cluster-wide applied | Misses refresh errors and stale nodes | Per-node verify + applied ACKs |
| Calling refresh 3 times via LB | May hit the same single node all 3 times | Target each replica's management address |
| Writing route to `InMemoryRepo` then refreshing B | B still lacks the definition | Use shared store or uniform deploys |
| POSTing to an existing route ID | Can create duplicates and 500s per version | Check uniqueness; use proper update flow |
| Using GET route output as POST body | Wrong shortcut DSL schema | Snapshot definitions in writable format |
| Assuming delete-then-create is atomic | Window where route is absent | Versioned snapshots / staged rollouts |
| Rolling back only Redis without refreshing | Nodes keep serving faulty caches | Reconcile local caches and verify |
| Rolling back to a smaller revision number | Consumers ignore it as an older event | Mint a new monotonic revision holding good snapshot |
| Retrying refresh on invalid definitions | Never fixes root cause | Validate/fix/roll back candidate |
| Auditing only HTTP status access logs | Cannot tell who changed what or convergence | Audit change ID/revision/diff/approval |
| Allowing arbitrary URIs in control plane | SSRF, credential leaks, route bypasses | Allowlists, egress policies, validation |
| Assuming cache acts as persistent last-known-good across restarts | Cold start fails during store outage | Durable snapshots / recovery testing |
| Changing auth-enforcing routes without regression tests | Bypasses or locks out legitimate users | Security synthetic tests + approvals |
| Logging `Authorization` headers on management endpoints | Leaks admin credentials | Redaction, secret rotation, access control |

## 20. Capstone Lab: Changing the Orders Route and Intentionally Inducing a Failure

**Test architecture:**

- Gateway Server WebFlux running two replicas A/B.
- Both reading route definitions from a matching shared repository.
- Dedicated management network, admin JWT scopes, and Actuator writes enabled strictly in staging.
- A mock control plane recording audits and revisions.
- Mock `ORDER-SERVICE` clearly echoing the upstream target and stripped request path.

**Requirements:**

1. Configure `management.endpoint.gateway.access: read-only`; verify readers can inspect routes while POST/DELETE/refresh are blocked.
2. Switch to `unrestricted` in staging with network/auth active; verify only writers can invoke writes.
3. Snapshot route `dyn-orders-api` revision 41, storing checksum/metadata.
4. Create candidate revision 42 changing `StripPrefix` and adding a filter missing on Gateway B.
5. Pass the candidate through validation; verify whether pre-publish checks catch the filter mismatch.
6. If the test deliberately permits publishing in isolation, observe A and B diverging in state.
7. Audit `PARTIAL` with redacted error details—never mark success from HTTP 200.
8. Publish revision 43 carrying revision 41's safe content; refresh A and B.
9. Run synthetic tests for GET orders, missing-token requests, missing-scope requests, and path rewrites.
10. Confirm both A and B applied 43 before recording audit `ROLLED_BACK`.
11. Deliberately drop a notification to B; verify reconciliation catches up.
12. Produce a report covering change ID, actor, ticket, before/after diff, apply failure, recovery duration, p95 latency, and safety lessons.

### 20.1. PASS Criteria

~~~text
Preflight:
  Gateway Actuator disabled by default; explicitly read-only for observers
  Admin management access isolated and authenticated
  Writer permission separated from viewer

Route change:
  Candidate validated
  Pre-change snapshot preserved
  Audit records actor, revision, diff, approval

Failure:
  Refresh failure not reported as cluster APPLIED
  Replica mismatch detected by convergence monitor

Recovery:
  Safe snapshot restored as new revision
  Every target replica verified
  Security and upstream behavior re-tested
  Audit finalized as ROLLED_BACK
~~~

These markers are **test acceptance criteria**, not a report from a live executed deployment.

## 21. Pre-Production Checklist

- [ ] `management.endpoint.gateway.access` is set appropriately; prefer `read-only` for observation.
- [ ] `management.endpoints.web.exposure.include` lists only needed endpoints.
- [ ] Management port/network is never exposed to public APIs or arbitrary Gateway routes.
- [ ] Admin auth, TLS/mTLS, and RBAC tested against the real listener.
- [ ] Reader/proposer/approver/writer roles separated; write scopes enforce route-level policies.
- [ ] Custom `SecurityWebFilterChain` does not inadvertently unprotect other Actuator endpoints.
- [ ] CSRF policy matches cookie/session vs stateless bearer-only admin flows.
- [ ] Candidate routes validated for URI, schemes, predicates, filters, order, auth, and compatibility.
- [ ] Control plane enforces approvals, revisions/optimistic concurrency, and change freezes when needed.
- [ ] Audit trail captures verified actor, `changeId`, before/after, outcomes, and rollbacks.
- [ ] Secrets, Bearer tokens, cookies, full environment dumps, and PII are never logged.
- [ ] Recoverable snapshots stored in writable format rather than relying on raw verbose GET output.
- [ ] No blind POSTs to existing route IDs; behavior verified per Gateway version.
- [ ] Create/delete/refresh are never assumed to be atomic multi-route transactions.
- [ ] Shared repository or clear source-distribution mechanism exists for multiple replicas.
- [ ] Local refresh and per-replica apply verification work reliably.
- [ ] Bus/reconciliation handles duplicate, lost, or out-of-order events.
- [ ] HTTP 200 from refresh is never treated as proof of cluster convergence.
- [ ] New-revision rollback runbook exists rather than local cache “undo”.
- [ ] Chaos-tested Redis/bus outages, cold starts, stale nodes, and filter compatibility.
- [ ] Synthetic tests cover paths, auth, scopes, TLS, retries, rate limiting, and upstreams.
- [ ] Metrics/alerts track unauthorized changes, refresh failures, convergence lag, and 404/5xx.
- [ ] Route admin credentials rotate/revoke cleanly and audit retention is protected.

## 22. Summary and Official References

**Spring Cloud Gateway Actuator is a high-privilege control surface.** Using it safely requires combining:

1. **Endpoint access and exposure:** `management.endpoint.gateway.access` with `management.endpoints.web.exposure.include`.
2. **Authentication/authorization:** private management network, TLS, reactive Spring Security, separate read/write permissions, and an approval-gated control plane.
3. **Auditing:** verified actor, route diffs, revisions, change ID, validation, refresh outcome, and per-node apply results.
4. **Recovery:** known-good snapshots, versioned rollbacks, per-replica refreshes, effective-route checks, and synthetic security tests.

A `POST /actuator/gateway/refresh` returning 200 **does not prove every Gateway replica adopted the new config**; a successful write does not guarantee routes built and serve traffic properly. Reliability comes from a **validate → commit → notify → refresh → verify → audit → reconcile/rollback** workflow tested even when Redis, service discovery, or individual replicas fail.

These principles keep the Gateway routing microservices safely during dynamic route changes—without inadvertently breaking authentication, rate limiting, circuit breakers, retries, TLS, or observability.

### Official References

- [Spring Cloud Gateway Server WebFlux — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway 5.0 — Actuator API: create/delete, refresh, and route ID update limits](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Cloud Gateway Server WebFlux — Sharing Routes](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/sharing-routes.html).
- [Spring Boot — Actuator Endpoints: access, exposure, and security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
