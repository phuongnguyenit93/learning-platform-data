# Reading Permission Data with Non-Blocking APIs in Spring Security WebFlux

## 1. Problem: authorization needs to read a database or another service

In a Spring WebFlux application, deciding whether Alice may read `Document 42` rarely depends solely on authorities embedded in a JWT. The application may also need to read:

- Alice's membership in the target tenant.
- READ/EDITOR roles granted to Alice **inside that specific tenant**.
- The tenant, owner, project, and status of Document 42 from the database.
- Valid, non-revoked ACL entries or share grants.
- Permissions issued by an external authorization service.
- Account suspension state, policy version, or business conditions.

When those facts live in a database or HTTP service, permission checking becomes an I/O step. Placing `jdbcTemplate.query(...)` or `webClient...block()` inside WebFlux authorization can block event-loop threads, reducing throughput and inflating latency for other requests.

The proper approach is to **return a `Publisher`** such as `Mono<Boolean>` or `Mono<AuthorizationResult>`, use R2DBC or `WebClient` to read permissions **without blocking threads**, and let the request proceed **only after the decision arrives**.

This topic belongs to **HTTP on WebFlux**: the focus is asynchronous permission data sources and wiring them into Spring Security Reactive, not superficially wrapping blocking business logic as "async."

### Objectives

After this lesson, you can:

1. Explain how non-blocking I/O differs from running JDBC on a thread pool.
2. Read memberships, ACLs, or owners via R2DBC with `Mono`/`Flux`.
3. Integrate DB or remote policy service checks into `ReactiveAuthorizationManager`.
4. Never confuse `Mono.empty()`, `Mono.just(false)`, and `Mono.error(...)`.
5. Handle timeouts, dependency errors, cancellations, and stale caches following **fail-closed** principles.
6. Preserve identity, tenant, and resource scope throughout the Reactor chain.
7. Use `WebTestClient` and `StepVerifier` to verify both security and asynchronicity.
8. Run a standalone Java 17 example demonstrating composed asynchronous checks.

## 2. What is non-blocking, and what is not?

A simple flow:

```text
HTTP Request
   |
   v
JWT/session authentication -> Authentication
   |
   v
Reactive authorization manager
   |
   +--> read membership (R2DBC) ----+
   |                                |
   +--> read resource/owner --------+--> ALLOW/DENY
   |                                |
   +--> read grant or WebClient ----+
                                    |
                                    v
                          Allow or block service
```

**Non-blocking** means while waiting on the DB or network, Reactor/Netty worker threads are not held by a synchronous wait call. Operations are modeled as a pipeline that resumes only when the `Publisher` emits a result or error.

Key concepts:

| Mechanism | Characteristics | Suitable for WebFlux authorization? |
| --- | --- | --- |
| `Mono<Boolean>` | Emits 0 or 1 asynchronous result | Yes, when empty/error are handled properly |
| `Mono<AuthorizationResult>` | Spring Security reactive decision for matching versions | Yes |
| `Flux<Grant>` | Can emit multiple grants/records | Yes, though usually reduced to one decision |
| `ReactiveCrudRepository` / R2DBC | Database I/O over a reactive driver | Yes, when driver and operations are genuinely non-blocking |
| `WebClient` | Reactive HTTP client | Yes, as long as `block()` is never called |
| `JdbcTemplate` / JPA repository | Synchronous/blocking database I/O | Should not be called directly in reactive security pipelines |
| `RestTemplate` or blocking HTTP clients | Holds thread while waiting for response | Should not be called directly on the event loop |
| `publishOn(boundedElastic())` around JDBC | Offloads blocking to another pool | Bounded bridge workaround; **does not make JDBC non-blocking I/O** |
| `CompletableFuture.join()` / `Future.get()` | Blocks thread waiting for result | Never call inside WebFlux request/event loop |

**Distinction:** running a blocking task on `Schedulers.boundedElastic()` avoids stalling the Netty event loop, yet still consumes another thread and faces thread/queue limits. Where real reactive drivers and endpoints exist, prefer R2DBC and `WebClient`. When migrating from JPA/JDBC, explicitly plan migration, bulkheads, concurrency limits, and monitoring.

### Reactive does not automatically equal safe

The code below looks reactive yet still blocks:

```java
Mono<Boolean> allowed = Mono.just(
    permissionJdbcRepository.existsByUserAndDocument(userId, documentId)
);
```

`permissionJdbcRepository.exists...` executes **immediately when creating the `Mono`**, before subscription. `Mono.just(...)` does not turn blocking work into non-blocking work.

Another anti-pattern:

```java
boolean allowed = reactiveGrantRepository
    .existsByDocumentIdAndSubjectId(documentId, subjectId)
    .block();
```

`block()` waits synchronously and is dangerous on the Reactor event loop. On non-blocking threads, Reactor may detect it and throw an exception; elsewhere it can still exhaust threads and bottleneck under load.

## 3. Path of a protected request in WebFlux

Given an HTTP request:

```http
GET /api/tenants/tenant-a/documents/42
Authorization: Bearer <verified-access-token>
```

Logical flow:

```text
WebFilterChainProxy / SecurityWebFilterChain
               |
               v
Authentication WebFilter / JWT validation
               |
               v
authorizeExchange().pathMatchers(...).access(reactiveManager)
               |
               v
ReactiveAuthorizationManager<AuthorizationContext>
               |
               +-- Authentication from Publisher
               +-- path variable tenantId/documentId
               +-- trusted subject/tenant membership
               +-- DB facts / ACL / grant via R2DBC or WebClient
               |
               v
AuthorizationResult GRANT / DENY
               |
          +----+----+
          |         |
         GRANT     DENY
          |         |
          v         v
     Handler      Block, mapped per
     Service      security entry point
          |
          v
  Tenant-scoped data access
```

The string `tenant-a` in the URL is only the **requested tenant**, not proof Alice holds membership in tenant A. It must be checked against the authenticated subject and server-side data before querying or allowing.

**A request proceeds only after authorization completes.** Merely creating a `Mono<Boolean>` without wiring it into the pipeline—or calling `subscribe()` and ignoring the outcome—leaves the request unprotected.

## 4. Three Reactor signals: value, empty, and error

A `Mono<Boolean>` can take three forms:

```text
Mono.just(true)   -> decision to allow
Mono.just(false)  -> decision to deny
Mono.empty()      -> no value/decision
Mono.error(e)     -> error; decision could not be made
```

These signals are not equivalent.

**Safe policy at the boundary:**

- `true` → ALLOW **only** when all evidence is verified.
- `false` → DENY.
- `empty` → default DENY or carefully designed abstain rules; never convert empty into allow.
- `error` → **do not permit**; return 5xx/503 if a dependency fails, and emit internal metrics/logs.
- Timeout → **do not permit**; never bypass policy to reduce latency.

Example:

```java
Mono<Boolean> strictDecision =
    grants.hasActiveReadGrant(subjectId, documentId)
        .defaultIfEmpty(false);
```

If the repository emits no record, the result is `false`.

**Avoid:**

```java
Mono<Boolean> unsafe =
    grants.hasActiveReadGrant(subjectId, documentId)
        .onErrorReturn(true); // Forbidden: DB error opens access.
```

Also avoid `switchIfEmpty(Mono.just(true))` or `onErrorResume(e -> Mono.just(true))`. Even under high availability pressure, authorization system failures must never become an ALLOW backdoor.

### Distinguishing "not found" from "DB broken"

A repository `find...` returning `Mono.empty()` because no membership exists means permission is **unproven** → DENY. An R2DBC connection failure or remote PDP timeout is an infrastructure failure; it **also grants no access**, yet may warrant HTTP 503/5xx, alerts, circuit breakers, and bounded retries. Do not swallow every exception into 403, hiding outages and making operators think users suddenly lost permissions.

## 5. R2DBC: reading memberships/ACLs with a reactive database API

Spring Data R2DBC supports reactive repositories via `ReactiveCrudRepository<T, ID>`, `R2dbcEntityTemplate`, and `DatabaseClient`. They run atop a matching R2DBC driver, requiring the **right database driver, connection factory, transaction manager, and dependencies**.

Example schema for a system:

```text
tenant_memberships(
    tenant_id, subject_id, active, can_read_documents
)

documents(
    id, tenant_id, owner_subject_id, deleted, title
)

document_share_grants(
    document_id, tenant_id, recipient_subject_id,
    permission, valid_from, expires_at, revoked_at
)
```

This is a **conceptual schema**, not a default Spring Security schema. With Spring Data R2DBC, entities typically use `org.springframework.data.annotation.Id` and `org.springframework.data.relational.core.mapping.Table`, not JPA annotations like `jakarta.persistence.Entity`.

### Membership repository

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface TenantMembershipRepository
        extends ReactiveCrudRepository<TenantMembership, Long> {

    Mono<Boolean>
    existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
        String tenantId,
        String subjectId
    );
}
```

This is a **Spring Data R2DBC application interface**, requiring a matching `TenantMembership` entity, repository scanning, and a valid connection factory. It is non-blocking and returns `Mono<Boolean>`. In domains with multiple roles, `canReadDocuments` might be computed through joins or role mappings; the principle remains **read permission scoped to the exact tenant**.

### Repository verifying resource owner/tenant

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Boolean>
    existsByIdAndTenantIdAndOwnerSubjectIdAndDeletedFalse(
        Long documentId,
        String tenantId,
        String ownerSubjectId
    );

    Mono<Document> findByIdAndTenantIdAndDeletedFalse(
        Long documentId,
        String tenantId
    );
}
```

When policy permits only owners to READ, an `existsBy...` query avoids loading the full entity just to inspect it in Java. Either way, keep **`tenantId` and `ID`** in the same predicate to prevent BOLA/IDOR. With share grants, add a policy checking active grants; never assume a user with tenant READ can read every private document.

### Data can change dynamically

Memberships, ACLs, owners, and document states can be modified or revoked. An unexpired JWT does not guarantee those records remain as they were at token issuance. Your architecture must define `freshness`, cache invalidation, and when permissions are re-evaluated.

## 6. Reactive policy: chaining queries with `flatMap` instead of `block`

Suppose a policy **allows only owners to read**, after checking functional authority and tenant membership:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveDocumentPolicy {
    private final TenantMembershipRepository memberships;
    private final DocumentRepository documents;
    private final SubjectResolver subjects;

    public ReactiveDocumentPolicy(
            TenantMembershipRepository memberships,
            DocumentRepository documents,
            SubjectResolver subjects) {
        this.memberships = memberships;
        this.documents = documents;
        this.subjects = subjects;
    }

    public Mono<Boolean> canRead(
            Authentication authentication,
            String requestedTenantId,
            Long documentId) {

        if (authentication == null
                || requestedTenantId == null
                || requestedTenantId.isBlank()
                || documentId == null || documentId <= 0L) {
            return Mono.just(false);
        }

        // SubjectResolver is application-written and must reject anonymous callers.
        return subjects.requireVerifiedSubject(authentication)
            .filter(subject ->
                subject.active()
                && subject.authorities().contains("document:read"))
            .flatMap(subject ->
                memberships
                    .existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
                        requestedTenantId, subject.subjectId())
                    .flatMap(memberCanRead -> {
                        if (!memberCanRead) {
                            return Mono.just(false);
                        }
                        return documents
                            .existsByIdAndTenantIdAndOwnerSubjectIdAndDeletedFalse(
                                documentId, requestedTenantId,
                                subject.subjectId());
                    }))
            .defaultIfEmpty(false);
    }
}
```

**Explanation:**

- `SubjectResolver` and `VerifiedSubject` are application-implemented types. `requireVerifiedSubject(...)` must extract a stable subject/identity from a **verified** `Authentication`, rejecting anonymous callers and untrusted states, and returning `Mono<VerifiedSubject>`.
- `requestedTenantId` from the path is only a selector. The membership query verifies the subject holds READ in that tenant; WRITE in tenant A does not grant READ in B.
- `flatMap` sequences I/O: the document is queried only after membership passes.
- `defaultIfEmpty(false)` turns missing subjects or empty publishers into DENY.
- Zero `block()` or manual `subscribe()` calls.
- DB errors are not converted to `true`; errors propagate upward for safe boundary handling.
- This owner-only example omits share grants or field-level permissions; extend as the domain requires.

**This is an application component class, not a standalone runnable Java file.** It requires `SubjectResolver`, domain entities, repositories, an R2DBC driver/schema, and Spring config. In production, never bind `VerifiedSubject` from a request body; derive it from `Authentication` and real membership/trust context.

### Why never subscribe manually inside a policy?

Wrong:

```java
public boolean canReadWrong(
        String tenantId, String subjectId) {
    memberships.existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
        tenantId, subjectId
    ).subscribe(allowed -> {
        // Too late: method already returned before result arrived.
        logAuthorization(allowed);
    });
    return true; // Forbidden: fail open.
}
```

`subscribe()` spawns a separate execution stream and **does not attach the decision** to the filter chain. Because the method returns `true`, the request can proceed before the DB responds. Manual `subscribe()` can also break context, cancellation, auditing, and trigger uncontrolled side effects.

In Spring WebFlux, return the `Publisher` itself so the framework subscribes and manages lifecycle, errors, and cancellation.

## 7. Integrating with `ReactiveAuthorizationManager<AuthorizationContext>`

Spring Security WebFlux provides `ReactiveAuthorizationManager<T>`; with `authorizeExchange().access(...)`, the context is `AuthorizationContext`, holding `ServerWebExchange` and extracted path variables.

**Version-specific API note:** In Spring Security 7.0+, `ReactiveAuthorizationManager<T>` has `authorize(Mono<Authentication>, T)` returning `Mono<AuthorizationResult>` as its primary method; `AuthorizationDecision` implements `AuthorizationResult`. On 6.x branches, `check(...)` and return types can differ. **Check your project's dependencies and Javadoc** before copying this exact signature.

Spring Security **7.x** example:

```java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DocumentReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveDocumentPolicy policy;

    public DocumentReadAuthorizationManager(ReactiveDocumentPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        String tenant = context.getVariables().get("tenantId");
        String rawId = context.getVariables().get("documentId");
        Long id = parseId(rawId);

        if (tenant == null || tenant.isBlank() || id == null) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .filter(auth ->
                auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken))
            .flatMap(auth -> policy.canRead(auth, tenant, id))
            .map(granted ->
                (AuthorizationResult) new AuthorizationDecision(granted))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private static Long parseId(String value) {
        if (value == null) {
            return null;
        }
        try {
            long id = Long.parseLong(value);
            return id > 0 ? id : null;
        } catch (NumberFormatException invalid) {
            return null;
        }
    }
}
```

**Why cast inside `map`?** `AuthorizationDecision` implements `AuthorizationResult`. Under the 7.x API, the method must return `Mono<AuthorizationResult>`, and Reactor generics are invariant: `Mono<AuthorizationDecision>` is not assignable to `Mono<AuthorizationResult>`. Writing `(AuthorizationResult) new AuthorizationDecision(granted)` aligns the return type.

**Default deny:**

- Missing path variable or unparseable ID → DENY.
- No `Authentication` emitted from the `Mono` → DENY.
- Anonymous or unauthenticated → DENY.
- Repository finds no subject/membership/document → `false` → DENY.
- DB/`WebClient` error → **not ALLOW**. Without an error-mapping handler, it follows the error path; configure safe HTTP error responses and metrics.

Do not rely on `Authentication.isAuthenticated()` as the sole proof a user is logged in; `AnonymousAuthenticationToken` must be excluded, and `SubjectResolver` must verify actual principal type, issuer, and status.

### WebFlux HTTP configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHttpSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            DocumentReadAuthorizationManager documentRead) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/tenants/{tenantId}/documents/{documentId}"
                ).access(documentRead)
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This is an **illustrative Spring Security 7.x configuration class**. It needs JWT decoder/issuer/audience validation, matching controllers, and application endpoints. `anyExchange().denyAll()` denies all other undeclared routes. If the app needs health/public endpoints, add narrow rules per API contract and guard management endpoints carefully.

**Important:** `authorizeExchange` configures authorization **within a single selected chain**. If your app has multiple `SecurityWebFilterChain`s, review `securityMatcher(...)` and `@Order`; requests entering another chain will not invoke this example's custom manager. The first matching chain wins—later chains are not tried after a DENY.

### What else must still be protected?

Even when the custom READ manager allows a request, handlers and services must still use **tenant-scoped** queries. If a controller calls `documentRepository.findById(documentId)` without checking tenant, another call path or race condition can read out-of-scope data. Never treat request-level policy as the sole guard, especially with GraphQL, background jobs, SSE, and internal service calls.

## 8. Designing non-blocking data-access APIs

Not all data fits derived repository methods. For complex rules, use `DatabaseClient` with explicit SQL constraints:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public class DocumentOwnerPermissionQuery {
    private final DatabaseClient db;

    public DocumentOwnerPermissionQuery(DatabaseClient db) {
        this.db = db;
    }

    public Mono<Boolean> canOwnerRead(
            String tenantId, String subjectId, long docId) {
        return db.sql("""
                SELECT EXISTS (
                    SELECT 1
                    FROM documents d
                    JOIN tenant_memberships m
                      ON m.tenant_id = d.tenant_id
                     AND m.subject_id = :subject
                    WHERE d.id = :id
                      AND d.tenant_id = :tenant
                      AND d.owner_subject_id = :subject
                      AND d.deleted = FALSE
                      AND m.active = TRUE
                      AND m.can_read_documents = TRUE
                ) AS allowed
                """)
            .bind("id", docId)
            .bind("tenant", tenantId)
            .bind("subject", subjectId)
            .map((row, metadata) ->
                Boolean.TRUE.equals(row.get("allowed", Boolean.class)))
            .one()
            .defaultIfEmpty(false);
    }
}
```

This uses **PostgreSQL-style SQL** and Spring R2DBC `DatabaseClient`, requiring a real DB/schema configuration. Different databases/dialects vary in boolean, `EXISTS`, and alias syntax. All parameters are **bound**—never concatenate `tenantId` or subject input into SQL strings.

Advantages of a single query:

- Checks membership and owner/resource in the same SQL statement.
- Reduces I/O round trips.
- Avoids a gap between checking membership and reading the resource across two separate statements.
- Avoids loading unnecessary sensitive fields solely to make a READ decision.

**Limitation:** a single statement does not solve every race if membership is revoked in a concurrent transaction or while data is already streaming. Define point-in-time consistency and isolation levels if SLAs demand it.

### Queries with share grants

A READ policy for owners **or** grant recipients can be expressed logically as:

```sql
SELECT EXISTS (
    SELECT 1
    FROM documents d
    JOIN tenant_memberships m
      ON m.tenant_id = d.tenant_id
     AND m.subject_id = :subject
    WHERE d.id = :id
      AND d.tenant_id = :tenant
      AND d.deleted = FALSE
      AND m.active = TRUE
      AND m.can_read_documents = TRUE
      AND (
        d.owner_subject_id = :subject
        OR EXISTS (
            SELECT 1
            FROM document_share_grants g
            WHERE g.document_id = d.id
              AND g.tenant_id = d.tenant_id
              AND g.recipient_subject_id = :subject
              AND g.permission = 'READ'
              AND g.revoked_at IS NULL
              AND g.valid_from <= :now_utc
              AND g.expires_at > :now_utc
        )
      )
) AS allowed;
```

This is **logical SQL** for an app with sharing grants; it needs a matching schema, foreign keys, query plan, indexes, and resource/business-state checks. `:now_utc` comes from a well-defined server/DB clock. Grants expire right at `expires_at` thanks to `now < expires_at`.

**Do not** assume JPA entity annotations work in R2DBC, or that R2DBC makes Spring ACL's `AclService` reactive. If an ACL store exposes only blocking APIs, plan a query migration or a thread-bounded adapter.

## 9. Reading permissions from an external service via `WebClient`

Some organizations run a **remote authorization service / PDP** instead of storing all memberships/ACLs in the application database.

Flow:

```text
Spring WebFlux request
   |
   v
Reactive authorization manager
   |
   v
WebClient -> internal policy service (non-blocking)
   |
   v
ALLOW / DENY / dependency error
   |
   v
PEP enforce -> application handler
```

Example custom contract:

```json
{
  "subjectId": "u-101",
  "tenantId": "tenant-a",
  "resourceType": "Document",
  "resourceId": "42",
  "action": "READ",
  "policyVersion": "document-policy-v3"
}
```

These fields must be **constructed by the backend from trusted data**, never forwarding raw user-supplied JSON into the PDP. The remote service must authenticate the calling application (mTLS/service credentials), validate input schemas, and hold authority to decide.

### `WebClient` returns `Mono`, never `block`

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class RemotePermissionClient {

    public record CheckRequest(
        String subjectId,
        String tenantId,
        String resourceType,
        String resourceId,
        String action
    ) {}

    public record CheckResponse(
        boolean allowed,
        String policyVersion
    ) {}

    private final WebClient client;

    public RemotePermissionClient(WebClient client) {
        this.client = client;
    }

    public Mono<Boolean> canReadDocument(
            String verifiedSubject,
            String verifiedTenant,
            String documentId) {

        CheckRequest request = new CheckRequest(
            verifiedSubject, verifiedTenant,
            "Document", documentId, "READ"
        );

        return client.post()
            .uri("/internal/authorize")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(CheckResponse.class)
            .map(CheckResponse::allowed)
            .defaultIfEmpty(false)
            .timeout(Duration.ofMillis(400));
    }
}
```

This is a **Spring `WebClient` component**; running it requires a `WebClient` bean pointing to a trusted service, TLS/authentication, connect/read timeout budgets, a service registry, and an API contract. The 400 ms duration is an **operational example**, not a Spring Security constant.

**By default**, `retrieve()` turns HTTP 4xx/5xx responses into errors. `timeout(...)` also emits an error when exceeded. That is intentional: **errors must never be treated as ALLOW**. Distinguish valid denials, unauthorized PDP callers, outages, malformed responses, and audit them at the boundary—never attach `onErrorReturn(true)`.

### Trusting remote PDP results

An `{"allowed":true}` response is trustworthy only if:

- The receiving/responding service identity was authenticated.
- TLS/network trust and token audience match.
- The response matches the request's **exact subject, resource, action, and tenant**.
- The policy version/release is approved for that action.
- Data snapshot/freshness meets requirements.
- No response mix-ups occurred via cache keys or retries.
- Required fields are neither missing nor misparsed.

If API responses are cached, never key solely by `resourceId`; include subject/tenant/action/version and relevant ACL state. An ALLOW for Alice to read Document 42 must never be reused for Bob.

## 10. Timeouts, retries, and fail-closed error handling

A slow authorization dependency can stall the **entire request**, so timeouts and bulkheads are essential. Yet timeouts must fail safely.

| Situation | Decision for request | Operational action |
| --- | --- | --- |
| Active membership, valid permission, resource in tenant | ALLOW | Execute business logic |
| No membership | DENY | 403/404 per policy |
| Grant revoked/expired | DENY | Do not return data |
| Remote PDP returns explicit DENY | DENY | Audit appropriately |
| Remote PDP returns empty/unknown payload | DENY | Emit anomaly metric |
| R2DBC/remote PDP timeout | **Never ALLOW** | 503/5xx or safe DENY, alert |
| DB connection error | **Never ALLOW** | Circuit breaker / observability |
| Invalid JWT | No valid `Authentication` | Auth challenge / 401 |
| Resource outside tenant | DENY or neutral 404 | Never leak other tenant metadata |
| Unverifiable policy version | DENY | Halt rollout / incident response |

### Explicit error-handling pattern example

```java
return remotePermissions.canReadDocument(
        subjectId, tenantId, documentId)
    .defaultIfEmpty(false)
    .onErrorResume(error -> {
        authorizationMetrics.recordDependencyFailure(error);
        return Mono.error(
            new AuthorizationDependencyUnavailableException(error)
        );
    });
```

This is a **fragment**: the metrics collector and exception are application types; map the exception to HTTP 503/5xx without exposing secrets. **Never grant access** in the error branch.

If a system deliberately returns `AuthorizationDecision(false)` instead of 503, still log a distinct *DEPENDENCY_UNAVAILABLE* reason in the audit trail; avoid conflating "user lacks permission" with "system could not check."

### Bounded retries

Retries can help with transient network errors, yet must never:

- Retry indefinitely while requests wait on authorization.
- Retry 403 or explicit DENY responses from the PDP.
- Exceed the request's time budget.
- Resend credentials/attributes to untrusted hosts.
- Cause unintended mutations if the PDP endpoint is not strictly read-only.

You may use `retryWhen(Retry.backoff(...).filter(...))` with explicit **error filters** and time budgets. Never treat retries as a substitute for circuit breakers and health monitoring.

### Connection pools and backpressure

R2DBC and `WebClient` still need bounds on connections, pending requests, response sizes, and concurrency. A non-blocking `Publisher` can fire **thousands of concurrent I/O operations** under uncontrolled traffic. Monitor queue depth, pool saturation, timeouts, and decision p95/p99 latency alongside resource limits.

## 11. Reactor Context and `Authentication`: do not rely arbitrarily on `ThreadLocal`

Reactive Spring Security uses `ReactiveSecurityContextHolder` with Reactor Context. Many Servlet/JPA apps are accustomed to reading `SecurityContextHolder.getContext()` on the current thread; in WebFlux, execution can switch threads across `publishOn` or I/O callbacks.

One way to access the reactive context:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

In WebFlux Security, Spring Security usually populates the context for the request pipeline. For request-level authorization code, **prefer the `Mono<Authentication>` passed into `ReactiveAuthorizationManager` by Spring Security** instead of re-fetching it from global state.

### `contextWrite` in unit tests

```java
Mono<String> subject = ReactiveSecurityContextHolder
    .getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> result = subject.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(auth)
);
```

This is a **fragment**, requiring `auth` to be a real or test `Authentication` fixture. `contextWrite` attaches Reactor context to the subscription; it does not make Servlet `SecurityContextHolder` a reliable source.

**Mistake:** holding `activeTenant` in a static mutable field or un-cleared `ThreadLocal` and using it for R2DBC queries. Under concurrent requests/tenants, contexts can cross-contaminate. Pass an immutable `VerifiedTenantScope`/`tenantId` as an explicit parameter after verifying membership.

### Other async boundaries

If code crosses into `CompletableFuture`, custom executors, third-party callbacks, or message queues, **do not assume** Reactor context transfers automatically. Pass or restore the principal and tenant scope explicitly, and re-verify permissions when deferred work executes in case membership was revoked.

## 12. Combining multiple non-blocking permission sources: AND, OR, and short-circuiting

A policy might be:

```text
authenticated
AND account ACTIVE
AND tenant membership ACTIVE
AND document.tenant == verified tenant
AND document not deleted
AND has READ authority
AND (owner OR non-revoked/non-expired share READ grant)
```

**ANDs for mandatory conditions** must wrap the **OR of grant paths**. Never write:

```text
owner OR membership OR activeShare
```

because an owner in another tenant could cross the tenant boundary, or bare membership would be mistaken for per-document access.

### Sequential execution

```java
return memberships.canReadTenant(subject, tenant)
    .flatMap(canTenantRead -> {
        if (!canTenantRead) {
            return Mono.just(false);
        }
        return documents.findVisibleByIdAndTenant(id, tenant)
            .flatMap(doc ->
                subject.equals(doc.ownerSubjectId())
                    ? Mono.just(true)
                    : grants.hasActiveReadGrant(
                        subject, tenant, id, clock.instant()))
            .defaultIfEmpty(false);
    })
    .defaultIfEmpty(false);
```

**Fragment:** `canReadTenant`, `findVisibleByIdAndTenant`, and `hasActiveReadGrant` are application service methods; ensure they are non-blocking and scope by tenant and action. This avoids querying resources or ACLs once membership denies.

### Parallel execution when appropriate

`Mono.zip(...)` or `Mono.zipWhen(...)` can run independent queries in parallel to cut latency, yet never run grant queries early if they touch sensitive data of an **unverified** tenant. Parallelism is never an excuse to widen a trust boundary.

For example, once membership is verified, independent facts may be read concurrently; however, if data sources need a consistent transaction snapshot, running across multiple connections in parallel can **break** expected consistency. Choose the pipeline based on policy and transaction semantics, not benchmarks alone.

### Avoid `collectList` over the entire grant set

Do not write:

```java
return grants.findAllByTenantId(tenant)
    .collectList()
    .map(list -> list.stream().anyMatch(...));
```

This is an anti-pattern: loading every grant in a tenant into memory before deciding on one Document ID. Query with `existsBy...` or `DatabaseClient` using tenant/document/recipient/permission/time predicates and proper indexes. `Flux` can stream millions of rows with backpressure, yet that does not justify overly broad permission queries.

## 13. Reading permissions inside transactions and preventing TOCTOU

Example:

```text
T1: canEdit(alice, doc42) -> true
T2: admin revokes Alice's EDIT permission
T1: update Document 42
```

Non-blocking execution **does not eliminate** this race. A decision read from R2DBC before a DB update can still go stale. `@Transactional` with a reactive transaction manager does not automatically make all queries serializable under default isolation.

Safeguards:

- Place the permission check and mutation inside the same reactive transaction when required by the business.
- For updates, write SQL with `WHERE id=:id AND tenant_id=:tenant AND owner_id=:subject AND status='DRAFT'` and check the affected row count.
- Use versioning/optimistic locking or intentional row locks when permissions can be revoked concurrently.
- When ACLs live in a separate table, join/enforce the grant inside the UPDATE/transaction or choose appropriate isolation.
- Define the timing policy: must it hold at request start, statement execution, or commit?
- Never emit external side effects before the transaction commits; use outbox/after-commit patterns.

### Reactive transactions are not ThreadLocal transactions

Spring reactive transactions use Reactor context to propagate transactional resources. An example with `TransactionalOperator`:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<UpdateOutcome> updateTitle(
        String subject,
        String tenant,
        long documentId,
        String title) {

    return permissionQuery.canEdit(subject, tenant, documentId)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new org.springframework.security.access.AccessDeniedException(
                        "Document update denied"));
            }
            return documentWriteRepository
                .updateTitleIfAuthorized(
                    subject, tenant, documentId, title)
                .map(rows -> rows == 1
                    ? UpdateOutcome.UPDATED
                    : UpdateOutcome.NOT_UPDATED);
        })
        .as(transactionalOperator::transactional);
}
```

This is a **method fragment**: `transactionalOperator`, repositories, `UpdateOutcome`, and the permission model are application types. `updateTitleIfAuthorized` must enforce authorization predicates right on the write; updating by ID alone leaves pre-transaction checks vulnerable to staleness. `TransactionalOperator` must match the `ReactiveTransactionManager` for your connection factory/store. A single database transaction does not automatically cover remote PDPs, email, or object storage.

### `@PreAuthorize` in reactive method security

Spring Security also offers `@EnableReactiveMethodSecurity`; reactive methods returning `Mono`/`Flux` can be guarded with SpEL:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPermission.canRead(authentication, #tenantId, #documentId)"
)
public Mono<DocumentView> read(
        String tenantId, Long documentId) {
    // ...
}
```

**This is a fragment**, requiring a `documentPermission` bean supporting reactive decisions per your Spring Security version, `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` on matching branches, and invocation through a Spring-managed proxy. Spring Security reactive method security docs describe support for `Mono<Boolean>` from SpEL beans in AuthorizationManager mode. Never call `block()` inside the bean just to return `boolean`.

A simpler alternative is enforcing it directly in the service:

```java
return permission.canRead(authentication, tenantId, documentId)
    .flatMap(allowed -> allowed
        ? documents.findByIdAndTenantIdAndDeletedFalse(
              documentId, tenantId)
        : Mono.error(new AccessDeniedException("Forbidden")));
```

With service-level composition, ensure **every call path** goes through it and queries are tenant-scoped; never guard only one controller while letting workers or GraphQL call the repository directly.

## 14. Difference between "deny" and "not found"

In a multi-tenant API, `GET /tenants/A/documents/42` can encounter:

- User has no token → authentication failure, typically 401/challenge.
- Valid token, user lacks READ authority → typically 403.
- User does not belong to tenant A → 403 or neutral 404 per contract.
- Document 42 does not exist in A → 404.
- Document 42 belongs to tenant B → must also **not leak** B's existence; may return 404.
- Permission DB/PDP outage → 503/5xx leaking no data, **never ALLOW**.

You may choose 404 to conceal resource existence from unauthorized callers, provided you apply it consistently. Do not assume `ReactiveAuthorizationManager` automatically turns every DENY into HTTP 404; exception/status mapping must be configured to match the API contract.

Inside the policy, use distinct reason codes for auditing (e.g., `NOT_MEMBER`, `NOT_OWNER`, `REVOKED`, `DEPENDENCY_FAILURE`), while omitting owner/tenant/private resource facts from responses.

## 15. Using a blocking store temporarily: bounded migration approach

Many projects already use `JpaRepository`/`JdbcTemplate` and cannot switch immediately to R2DBC. You can **offload blocking work**:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Boolean> allowed =
    Mono.fromCallable(() ->
        blockingGrantRepository.hasReadPermission(
            subjectId, tenantId, documentId))
        .subscribeOn(Schedulers.boundedElastic());
```

This:

- Defers the blocking call until subscription.
- Schedules the work onto a scheduler built for blocking workloads.
- Avoids holding the Netty event loop directly while JDBC waits.
- **Does not turn JDBC into a non-blocking API**: a thread still waits on I/O.
- Requires pool, bulkhead, timeout, and metric configuration.

Do not overuse `boundedElastic()` to mask performance problems. If one request hits multiple blocking stores, threads/queues can still exhaust under heavy load. With JPA transactions/entity managers, evaluate context and transaction boundaries carefully; never bounce operations arbitrarily across threads inside a single persistence context.

**Never** write `Mono.just(blockingCall())`, because the blocking call executes before the `Mono` is even built. And never write `blockingRepository...block()`, because a blocking repository has no `Mono` to block on—a conceptual error.

## 16. Caching authorization decisions in reactive systems

Caching can cut DB/PDP reads, yet permissions often **change quickly**.

Distinguish:

| Cache type | Risk |
| --- | --- |
| Membership cache | Revoked user retains old permissions |
| Document facts cache | Owner/tenant/status changed |
| Share grant cache | Grant expired or was revoked |
| Remote policy decision cache | Bob receives Alice's ALLOW |
| HTTP response cache | Private document served to another user |

### Properly dimensioned cache keys

A key like `doc42:READ` is broken if it contains only documentId and action. At a minimum, include:

```text
authenticatedSubjectId
| verifiedTenantId
| resourceType
| resourceId
| action
| relevantPolicyVersion
| membershipOrAclVersion
| contextRestrictions
```

In practice, keys can use hashes/namespaces that do not expose PII. Yet **every dimension affecting the decision** must be represented or re-checked on cache reads.

For time-bounded share grants:

```text
positiveCacheTTL <= min(
    configuredTTL,
    expiresAt - currentServerInstant,
    allowedRevocationStalenessBudget
)
```

Even then, TTL alone cannot guarantee immediate revocation when a user clicks "Stop sharing"; use invalidation events, versioning, or query the source of truth. **Never** promise ≤1s revocation if positive caches live for 5 minutes without re-checking.

### Reactor `Mono.cache()` is not principal-aware

`mono.cache()` memoizes the result on the **publisher instance itself**. If a singleton service retains a `Mono<Boolean>` built for Alice and shares it with Bob, the cache can return Alice's ALLOW.

Therefore, never attach `cache()` to an authorization `Publisher` shared across subjects or requests unless keys, ownership, and expiration are designed properly. Reuse across subscriptions of a single operation can have valid uses; **never equate a `Publisher` cache with a multi-user authorization cache**.

## 17. `WebClient`: request context, cancellation, and token forwarding

When an app calls a permission service via `WebClient`, decide how to:

- Use **service credentials** for a trusted internal PDP.
- Or use **token exchange / on-behalf-of** if infrastructure requires delegated caller identity.
- Verify the audience and scope of forwarded tokens; never forward a user's bearer token to services that do not need it.
- Send subject/tenant/resource/action under an authenticated server-to-server contract.
- Configure connection timeouts and total read budgets.
- Bound response sizes and concurrent requests.
- Cancel or discard results when the client disconnects; never trigger side effects during checks.

If a browser disconnects, cancellation may propagate down the `Publisher` and remote request depending on implementation; however, **never treat cancellation as ALLOW** or assume every external side effect was rolled back. Authorization should be **read-only** and idempotent wherever possible.

### Side effects inside `doOnNext`

`doOnNext(...)` suits lightweight telemetry, not writing ACLs, changing owners, or sending notifications while merely asking `canRead`. Retried or repeated permission checks can execute side effects multiple times.

## 18. Debugging reactive chains: when does the query actually run?

In Reactor, many `Publisher`s are **cold**: assembling the pipeline does not run I/O immediately. I/O runs upon subscription.

Example:

```java
Mono<Boolean> pipeline = repository.existsById(42L)
    .doOnSubscribe(s -> log.debug("authorization query subscribed"));

return pipeline;
```

This is an illustrative fragment. With R2DBC repositories, Spring/Reactor triggers subscription when the HTTP chain needs a decision. Never call `pipeline.subscribe()` just to "warm it up" and return a different `Publisher`.

When debugging:

1. Was `ReactiveAuthorizationManager` actually invoked for the route?
2. Did `Mono<Authentication>` emit a valid `Authentication`?
3. Was `flatMap` subscribed, or did a filter short-circuit earlier?
4. Do path variables match `tenantId` and `documentId`?
5. Does the membership query use the server-confirmed tenant context?
6. On `Mono.empty()`, did the policy convert it to DENY?
7. Were R2DBC/`WebClient` exceptions swallowed into `true`?
8. Is anything blocking on the event loop?
9. Is an ALLOW from another subject cached?
10. Is `WebTestClient` running the real Spring Security `WebFilter` chain?

Logs should record request ID, verified subject (if privacy permits), tenant ID, resource type/action, decision/reason, and latency, while **never logging raw JWTs, passwords, cookies, document bodies, or sensitive SQL params**.

## 19. Standalone Java 17: simulating an asynchronous decision pipeline

The example below uses neither Spring Security nor R2DBC since those require external dependencies. It uses `CompletableFuture` to demonstrate **not unwrapping results prematurely**, chaining membership and resource checks with `thenCompose`, defaulting to deny on missing permissions, and preserving tenant boundaries.

In a real WebFlux app, replace `CompletableFuture` with `Mono` from R2DBC/`WebClient`; **never call `join()` or `get()` on the event loop**. In `main` of this standalone program, `join()` prints deterministic stdout after all tasks finish—it is not a pattern for HTTP handlers.

Save as `AsyncPermissionDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class AsyncPermissionDemo {

    record Actor(
        String subjectId,
        String tenantId,
        Set<String> authorities,
        boolean active
    ) {}

    record Document(
        long id,
        String tenantId,
        String ownerId,
        boolean deleted
    ) {}

    record Membership(
        String subjectId,
        String tenantId,
        boolean canRead
    ) {}

    private final Map<String, Membership> memberships = Map.of(
        "alice|tenant-a",
            new Membership("alice", "tenant-a", true),
        "bob|tenant-a",
            new Membership("bob", "tenant-a", true),
        "carol|tenant-b",
            new Membership("carol", "tenant-b", true)
    );

    private final Map<Long, Document> documents = Map.of(
        42L, new Document(42, "tenant-a", "alice", false),
        77L, new Document(77, "tenant-b", "carol", false),
        90L, new Document(90, "tenant-a", "alice", true)
    );

    // Simulates an async API: missing evidence -> false.
    CompletionStage<Boolean> hasMembership(Actor actor) {
        Membership member = memberships.get(
            actor.subjectId() + "|" + actor.tenantId());
        return CompletableFuture.completedFuture(
            member != null && member.canRead()
                && member.tenantId().equals(actor.tenantId()));
    }

    CompletionStage<Boolean> isVisibleOwner(Actor actor, long documentId) {
        Document doc = documents.get(documentId);
        return CompletableFuture.completedFuture(
            doc != null && !doc.deleted()
                && doc.tenantId().equals(actor.tenantId())
                && doc.ownerId().equals(actor.subjectId()));
    }

    CompletionStage<String> authorizeRead(
            Actor actor, long documentId) {
        if (actor == null || !actor.active()
                || !actor.authorities().contains("document:read")) {
            return CompletableFuture.completedFuture("DENY");
        }

        return hasMembership(actor)
            .thenCompose(isMember -> {
                if (!isMember) {
                    return CompletableFuture.completedFuture(false);
                }
                return isVisibleOwner(actor, documentId);
            })
            .thenApply(granted -> granted ? "ALLOW" : "DENY")
            .exceptionally(error -> "DENY");
    }

    public static void main(String[] args) {
        AsyncPermissionDemo demo = new AsyncPermissionDemo();

        Actor alice = new Actor(
            "alice", "tenant-a",
            Set.of("document:read"), true);
        Actor bob = new Actor(
            "bob", "tenant-a",
            Set.of("document:read"), true);
        Actor carol = new Actor(
            "carol", "tenant-b",
            Set.of("document:read"), true);
        Actor guest = new Actor(
            "guest", "tenant-a", Set.of(), true);
        Actor inactive = new Actor(
            "alice", "tenant-a",
            Set.of("document:read"), false);

        // Only main in this standalone Java program waits to print in order.
        System.out.println("Alice owns 42: "
            + demo.authorizeRead(alice, 42).toCompletableFuture().join());
        System.out.println("Bob same tenant, not owner: "
            + demo.authorizeRead(bob, 42).toCompletableFuture().join());
        System.out.println("Alice cross tenant 77: "
            + demo.authorizeRead(alice, 77).toCompletableFuture().join());
        System.out.println("Carol owns 77: "
            + demo.authorizeRead(carol, 77).toCompletableFuture().join());
        System.out.println("Alice deleted 90: "
            + demo.authorizeRead(alice, 90).toCompletableFuture().join());
        System.out.println("Guest no authority: "
            + demo.authorizeRead(guest, 42).toCompletableFuture().join());
        System.out.println("Inactive Alice: "
            + demo.authorizeRead(inactive, 42).toCompletableFuture().join());
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac AsyncPermissionDemo.java
java AsyncPermissionDemo
```

Exact stdout:

```text
Alice owns 42: ALLOW
Bob same tenant, not owner: DENY
Alice cross tenant 77: DENY
Carol owns 77: ALLOW
Alice deleted 90: DENY
Guest no authority: DENY
Inactive Alice: DENY
```

Explanation:

- Alice has the authority, tenant A membership, owns Document 42, and the document is not deleted → ALLOW.
- Bob has functional READ and belongs to the same tenant, yet does not own Document 42 and has no share grant in the model → DENY.
- Alice cannot read Document 77 in tenant B even when knowing its ID.
- Carol owns Document 77 in tenant B and holds membership, so ALLOW.
- Deleted documents, missing authority, or inactive actors are DENIED.
- `thenCompose` waits for the membership check before querying ownership. `exceptionally(...)` in the demo picks DENY to illustrate fail-closed behavior; production must log and classify infrastructure errors rather than swallowing exceptions silently.

**Specific limitation:** `CompletableFuture.completedFuture(...)` simulates an in-memory source and **does not prove a database driver is non-blocking**. To test real I/O, use R2DBC or `WebClient` with event-loop monitoring tools. The example also intentionally models **owner-only** access; when ACL/share grants exist, add those conditions accordingly.

## 20. Testing with `StepVerifier`

`StepVerifier` in `reactor-test` tests values, completion, errors, and virtual time on real pipelines.

Example unit test where policy returns deny:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveDocumentPolicy.canRead(authAlice, "tenant-b", 42L)
)
    .expectNext(false)
    .verifyComplete();
```

This is a **JUnit fragment**: it needs `authAlice`, test doubles for repositories/subject resolver, and `reactor-test`. Tests must use fixtures distinguishing tenant A/B, different owners, and exact authorities.

### Testing empty

```java
Mono<Boolean> noMembership = Mono.empty();

StepVerifier.create(noMembership.defaultIfEmpty(false))
    .expectNext(false)
    .verifyComplete();
```

### Testing error

```java
Mono<Boolean> dbFailed =
    Mono.error(new IllegalStateException("R2DBC unavailable"));

StepVerifier.create(dbFailed)
    .expectError(IllegalStateException.class)
    .verify();
```

At the policy layer, errors may propagate; at the HTTP boundary, ensure the request is **never processed as ALLOW**. Test 503/5xx or denials per your contract.

### Virtual time and timeouts

With a sample delayed source:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
    Mono.delay(Duration.ofSeconds(10))
        .map(n -> true)
        .timeout(Duration.ofSeconds(2))
)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
```

This sample tests Reactor timeouts using a virtual scheduler rather than `Thread.sleep`. For real HTTP clients and DB drivers, write separate integration tests; virtual time cannot substitute for sockets, connection pools, or real network timing tests.

### Testing that resource queries are skipped after membership denial

Use a mock/spy repository and verify `documents.exists...` is **never called** when membership returns `false`. This catches policies that read out-of-tenant resources before verifying membership, risking timing/log leaks or wasted I/O.

## 21. `WebTestClient`: testing the real filter chain

Testing `ReactiveDocumentPolicy.canRead(...)` directly is not enough. Policy logic can be right while:

- `SecurityWebFilterChain` is unregistered or its matcher misses.
- A new endpoint fails to use `access(documentRead)`.
- An earlier `permitAll` rule captures all of `/api/**`.
- A broad chain with higher `@Order` prevents the policy chain from being selected.
- Another controller calls the repository directly.
- JWT authority mapping omits `document:read`.
- Path variable `documentId` parses wrongly or `tenantId` is missing.

Use `WebTestClient` with the real Spring Security `WebFilter` chain.

### Setting up in the application context

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

public class DocumentAuthorizationIntegrationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

This is a **test class fragment**, requiring a loaded Spring test context, controllers, repositories, and `spring-security-test`. With `@SpringBootTest` running a real server, you can use an auto-configured `WebTestClient` for that web environment.

### Mocking JWTs to test authorization logic

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("document:read")))
    .get()
    .uri("/api/tenants/tenant-a/documents/42")
    .exchange()
    .expectStatus().isOk();
```

**Fragment:** the test expects 200 **only when** a real controller/handler exists, subject mapping matches, membership+owner/ACL fixtures allow it, and the mocked JWT translates into an identity `SubjectResolver` recognizes. With `mockJwt`, `Authentication`/subject may differ from internal user IDs, so set the `sub` claim accordingly.

`mockJwt()` **does not verify** real signatures, issuers, audiences, or `exp` via a decoder. Add Resource Server integration tests with real signed JWTs and decoders for that coverage.

### Testing that denied requests do not read data

When a user lacks permission, besides asserting 403/404, assert:

- No sensitive document body is returned.
- Protected downstream controller/service actions are not invoked when denied in the filter.
- No emails/events are emitted or DB rows written.
- No presigned URLs are issued.
- No cached response from another user is returned.
- No exception body leaks tenant, owner, or SQL details.

## 22. Minimum test matrix

| Actor | Requested tenant | Document | Data permission | Expected |
| --- | --- | --- | --- | --- |
| Alice | A | Doc42, Alice is owner | Active membership, READ | ALLOW |
| Bob | A | Doc42, Bob not owner | Active membership, no share | DENY |
| Carol | B | Doc42 in A | Has READ in B | DENY |
| Alice | C | Doc42 in A | No membership in C | DENY |
| Alice | A | Doc42 | Membership revoked | DENY |
| Alice | A | Doc42 | Valid authority, resource deleted | DENY |
| Guest | A | Doc42 | Unauthenticated | DENY |
| Alice | A | Doc42 | Missing `document:read` authority | DENY |
| Alice | A | Doc42 | Expired READ grant, not owner | DENY |
| Alice | A | Doc42 | Revoked grant, not owner | DENY |
| Alice | A | Doc42 | R2DBC timeout | Never ALLOW; error/5xx per policy |
| Alice | A | Doc42 | Remote PDP returns empty/malformed | Never ALLOW |
| Alice | A | Doc42 | Cached ALLOW for Bob | Never reuse Bob's data |
| Alice | A | Doc42 | Invalid JWT signature/issuer | Authentication failure |
| Alice | A | Doc42 | Two concurrent requests on one event loop | No blocking/deadlock |
| Alice | A | Doc42 | DB connection pool exhausted | Never fail-open, metrics/timeout |
| Alice | A | Doc42 | Tenant ID altered in path | Re-verify membership |
| Alice | A | Doc42 | Direct service call outside HTTP | Service/data policy not bypassed |

Test **each action**—READ/EDIT/DELETE/EXPORT—without assuming READ grants any other operation. For WRITEs, transactions and conditional updates are vital guards against races after pre-checks.

## 23. Performance and resilience under heavy load

### Cost of a decision

A multi-step pipeline:

```text
JWT parsing (local)
  -> membership query (R2DBC)
  -> document query (R2DBC)
  -> share grant query (R2DBC)
  -> remote PDP WebClient
  -> business query
```

Even when each step is non-blocking, cumulative latency can climb. Depending on policy:

1. Run coarse checks early (authentication, authorities).
2. Use a single `EXISTS` query with tenant/ACL predicates when possible.
3. Index `(tenant_id, subject_id, document_id, permission)` keys appropriately.
4. Avoid N+1 queries when listing many objects.
5. Batch PIP/PDP decisions when data allows and security semantics stay clear.
6. Measure authorization p50/p95/p99 latency, not just controller timing.
7. Bound concurrency, connection pools, and response sizes.
8. Add timeouts and circuit breakers for remote PDPs, **never failing open**.
9. Cache safely with invalidation when permissions change.
10. Regularly run load and cancellation tests with multiple users and tenants.

### One query for a batch of objects

If a UI displays 200 documents, you do not need 200 `canRead` calls executing 2–3 queries each. Write a tenant-scoped query returning **only readable documents** and paginate over the filtered set, or bulk-fetch ACLs/facts in one operation. For pagination, apply authorization filters **before computing counts and pages**.

**Risk:** loading all documents of a tenant and calling `filter` in Java after pagination can leak total counts, hurt performance, omit items on pages, and yield inconsistent counts.

### Reactive does not replace resource limits

In WebFlux, `flatMap` can unleash high concurrency. `flatMap(mapper, concurrency)`, `concatMap`, or bounded concurrency regulate batch fan-out instead of assuming "the more concurrent requests, the better." Monitor DB pools, CPU spent verifying JWTs, and remote PDP capacity.

## 24. Common mistakes and fixes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Calling `.block()` in custom authorization | Stalls event loop, drops throughput | Return `Mono<AuthorizationResult>`/`Mono<Boolean>` |
| Wrapping JDBC in `Mono.just(...)` | Blocking runs before subscribe | Use R2DBC or `fromCallable(...).subscribeOn(boundedElastic())` during migration |
| Calling `subscribe()` manually and returning `true` | Allows before permissions are read | Wire publisher into manager via `flatMap`/`map` |
| Using `subscribeOn(boundedElastic())` and calling it "non-blocking DB" | Misunderstands system capacity | Distinguish blocking offload from native R2DBC |
| Treating `Mono.empty()` as `true` | Allows despite missing permission | Apply `defaultIfEmpty(false)` at boundary |
| `onErrorReturn(true)` on PDP errors | Fail-open | Deny/5xx, audit dependency failure |
| Catching all DB errors and returning "user lacks permission" | Loses observability | Separate infrastructure errors from denials |
| Reading only `Authentication.getAuthorities()` | Ignores owner, tenant, grants | Query object/membership server-side |
| Trusting `tenantId` in URL/header | Client switches tenants freely | Verify membership before querying |
| Broad `findById` returning data | BOLA/IDOR | Tenant-scoped repositories + policies |
| Reusing READ share grant for EDIT | Privilege escalation | Action-specific permissions |
| Treating JWT TTL as ACL TTL | Revoked grants stay valid | Read current grant state or versioned cache |
| Caching `Mono<Boolean>` in a singleton without keys | Replays another user's ALLOW | Key by identity/tenant/action/resource/version or don't cache |
| Using `Flux.collectList()` for all ACLs | High memory usage, N+1 | Scoped `exists`/SQL and indexes |
| Calling remote PDP directly with `RestTemplate` | Blocking HTTP | `WebClient` with timeout |
| Forwarding raw user JWT to every service | Leaks credentials | Service-to-service auth / scoped token exchange |
| Remote policy returns ALLOW while resource/tenant mismatch | Cross-tenant access | Verify input/result context, data-scoped queries |
| Enforcing permissions only in HTTP matchers | Worker/GraphQL bypass | Policies in service/domain and DB |
| Keeping stale tenant in Reactor `ThreadLocal` | Cross-request context bleed | Immutable `VerifiedTenantScope`, controlled Reactor Context |
| Reactive `@PreAuthorize` bean calls blocking code | Stalls reactor | Return reactive result, never `block()` |
| `@PostAuthorize` on writes | Side effects already happened | Precheck + conditional mutation |
| Unit testing only with `mockJwt` and assuming signatures are verified | Missing decoder/issuer/audience tests | JWT integration tests |
| Not testing timeouts/empty/cancellation | Improper grants in failure modes | Negative and failure-injection tests |
| Skipping connection pool / event-loop tests | Fake non-blocking behavior | Load tests, metrics, BlockHound where appropriate |

## 25. Non-blocking authorization implementation checklist

1. **What is the authoritative permission source?** Membership, ACL, owner, share grant, or remote PDP?
2. **Are I/O APIs genuinely reactive?** R2DBC/`WebClient`, or thinly wrapped JDBC?
3. **Any `.block()`, `Future.get()`, or `join()` on the HTTP path?** Remove them.
4. **How is `Authentication` propagated?** `Mono` from security filter or Reactor Context, not ambiguous `ThreadLocal`s.
5. **Is `tenantId` verified against membership before use?**
6. **Is the resource fetched server-side by exact ID/type/tenant/status?**
7. **Are READ/EDIT/DELETE/EXPORT actions separated cleanly?**
8. **Does empty default to deny?** Never treat missing evidence as success.
9. **Do errors and timeouts fail closed and trigger alerts?**
10. **Does `WebClient` enforce service authentication, audience, and TLS?**
11. **Are cancellations, timeouts, pool limits, and bulkheads configured?**
12. **Do caches key on subject/tenant/resource/action/policy/version?**
13. **Do revocations and expirations take effect within SLA?**
14. **Do database queries include tenant predicates and proper indexes?**
15. **Do mutations guard against TOCTOU with proper transactions?**
16. **Are direct service paths outside HTTP protected too?**
17. **Does `ReactiveAuthorizationManager` match the target Spring Security version's API?**
18. **Have `Mono.empty`, `Mono.error`, and timeouts been tested?**
19. **Does `WebTestClient` run the real filter chain?**
20. **Have cross-tenant, role bleed, invalid JWT, stale cache, and bulk access cases been tested?**
21. **Are p95/p99 authorization latency and pool saturation monitored?**
22. **Do audit logs stay safe without exposing JWTs, secrets, or document data?**

**Conclusion:** In Spring Security WebFlux, permissions stored in databases or external services must be read and combined **in a reactive pipeline whose decision the filter chain actually awaits**. Use R2DBC, `WebClient`, `Mono`, `ReactiveAuthorizationManager`, and Reactor Context in a non-blocking manner; scope permissions by subject–tenant–resource–action; ensure empty/error outcomes **never grant access**; and test both functional paths and failure modes. Non-blocking execution improves resource efficiency—it **does not make authorization correct** if inputs, tenants, object policies, or consistency are wrong.

## Official references

- [Spring Security — Reactive Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `access(...)`, custom `ReactiveAuthorizationManager`.
- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, and `Mono<Boolean>` beans.
- [Spring Security API — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `authorize(Mono<Authentication>, T)` and `AuthorizationResult`.
- [Spring Security API — AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html): GRANT/DENY results, `isGranted`.
- [Spring Security — Reactive WebTestClient Integration](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): wiring the filter chain into `WebTestClient`.
- [Spring Security — Reactive OAuth2/JWT Test](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, distinguishing mocks from real JWT decoders.
- [Spring Data R2DBC — Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): `ReactiveCrudRepository`, query methods, and `StepVerifier`.
- [Spring Data R2DBC — Reference Guide](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): R2DBC queries, mapping, and transactions.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): `retrieve`, `bodyToMono`, and 4xx/5xx handling.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` and reactive transaction boundaries.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono`/`Flux`, schedulers, error handling, context, timeouts, and `StepVerifier`.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, and object-level authorization.
- [OWASP API Security — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): checking permissions per object ID.
