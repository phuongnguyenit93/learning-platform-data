# Designing Checks by Subject, Resource, Action, and Context in Spring Security

## 1. The problem: same user, same feature, yet the outcome can differ

In small applications, authorization often starts with `hasRole("ADMIN")` or `hasAuthority("document:read")`. That rule is useful, but it is not enough for scenarios like:

- Alice has permission to edit documents **she owns**, but cannot edit Bob's private documents.
- Alice has the EDITOR role in tenant A, yet is only a VIEWER in tenant B.
- Bob is granted read access to Document 42 **until 10:00**, but cannot download the original file.
- An invoice approver must belong to the finance department, cannot approve their own invoice, and can only approve when the invoice is in `PENDING` state.
- An administrator can perform a sensitive operation only when multi-factor authentication has been verified under the current policy.
- A customer cannot view data when their account is locked, even if their login token has not expired.

Therefore, an access decision needs more information than just a role name:

```text
allow = policy(subject, resource, action, context)
```

Where:

- **Subject:** who or which actor is requesting the operation.
- **Resource:** the exact object that will be read/written.
- **Action:** which permission is being requested, e.g., READ, EDIT, DELETE, APPROVE.
- **Context:** relevant conditions at evaluation time: tenant, account status, workflow, time, authentication type, sharing relationship, execution environment, etc.

That is how to design a **dynamic policy**: permissions are not computed solely from a static role string, but from trusted attributes/relationships/state **at the time the operation is performed**.

The goal of this lesson is to design a checking mechanism that is **testable, explainable, auditable, updatable, and consistently enforced** with Spring Security, avoiding both IDOR/BOLA vulnerabilities and scattered authorization conditions across controllers.

## 2. Distinguishing Authentication, Authorization, and decision data

| Question | Mechanism | Example |
| --- | --- | --- |
| Who is calling? | Authentication | Verified JWT with subject Alice |
| Permitted to use the feature? | Coarse authorization | Alice has `document:read` |
| Permitted on this object? | Resource authorization | Document 42 belongs to a tenant Alice is allowed in |
| Allowed to perform this action in the current state? | Contextual policy | Document is not archived, grant is still valid |
| If allowed, what data can be returned? | Data/property authorization | Return only allowed fields, do not leak private notes |

In Spring Security, `Authentication` resides in `SecurityContext`; `GrantedAuthority` represents the granted authorities. `AuthorizationManager<T>` evaluates permissions on a protected object/context, such as an HTTP request or method invocation. `AuthenticationManager` is an API for **authentication** and is not a tool to decide ACLs for Document 42 on its own.

An authenticated principal is **not automatically** allowed to read every object. A user with `ROLE_EDITOR` is also **not automatically** allowed to edit objects across all tenants, workflows, and data classifications.

### Two layers of checks should work together

```text
HTTP / SecurityFilterChain
  -> request must be authenticated or have coarse authority
         |
         v
Application service
  -> check subject + resource + action + context
         |
         v
Repository / database
  -> query/mutation scoped by tenant, owner, ACL
         |
         v
Response DTO / side effects
  -> expose only permitted data
```

The request layer blocks access early; the service/domain layer protects non-HTTP call paths; the data layer provides **defense in depth** and reduces check-then-use risks. Never rely on merely hiding buttons in the frontend.

## 3. Subject: use verified identity, never client-declared identity

**Subject** should be modeled with the necessary verified attributes:

| Attribute | Example | Notes |
| --- | --- | --- |
| `subjectId` | `u-1001` | Stable internal ID, avoid using display name |
| `issuer` | Trusted IdP/issuer | Needed when multiple identity providers have overlapping subjects |
| `authorities` | `document:read`, `invoice:approve` | May be global or tenant-scoped; scope must be known |
| `tenantMemberships` | Alice is EDITOR in A, VIEWER in B | Read from a trusted source or claims with a clear lifecycle |
| `accountStatus` | ACTIVE/SUSPENDED | Can change after the token was issued |
| `authenticationStrength` | Password, MFA/WebAuthn | Used for step-up/risk policies when actually needed |
| `delegation` | Service acting-on-behalf-of user | Must verify scope and delegator |

**Do not** take `request.userId`, `X-User-Id`, an email in JSON, or a role from a form as the subject. Those are mutable input data.

With JWT, `sub`, `iss`, and `aud` are only trustworthy after the Resource Server has verified the token according to appropriate issuer/signature/audience/expiry configuration. `Authentication.getName()` can be customized per principal type; if using multiple issuers, namespace or map to an internal ID so two subjects from two issuers never collide on the same string value.

### User and service principal

Do not assume every subject is a human. A worker, scheduled job, API client, or service account must also have a clear identity and scope. If a worker generates a report on Alice's behalf, you must decide whether it:

1. Uses **the service principal's own approved permissions**?
2. Uses Alice's **delegated permission** with expiration and resource limits?
3. Needs to re-check Alice's membership when the job executes?

The answer is part of business policy, and must not be inferred as full privileges simply because "there is no HTTP session".

## 4. Resource: verify the real object, do not trust client-sent attributes

**Resource** can be a database entity, object storage key, invoice, project, file, task, message, search record, or creation action.

Example attributes of `Document`:

```text
Resource:
  type: Document
  id: 42
  tenantId: tenant-a
  ownerSubjectId: alice
  projectId: 10
  classification: INTERNAL
  status: ACTIVE
  deleted: false
  version: 7
```

These fields should come from a **trusted server source**. If the client sends:

```json
{"documentId":42,"ownerSubjectId":"alice","tenantId":"tenant-a"}
```

then `ownerSubjectId` and `tenantId` must not be used as evidence to grant access. Only the ID is a **lookup request**; the server must fetch the real document and inspect tenant/owner from the database or controlled storage.

### IDOR/BOLA

A user with `document:read` sending someone else's ID is the classic case. References can appear in path, query, body, form, GraphQL, or batch IDs. Hard-to-guess UUIDs **do not replace** authorization checks once an ID is exposed.

For list/search/export, authorization must apply to **the entire returned dataset**, not only object detail endpoints. Querying everything and filtering after pagination can leak object counts, waste resources, and produce wrong totals.

### When the resource does not exist yet

For `POST /projects/10/documents`, the document has no ID yet. The right rule is to check **CREATE_DOCUMENT on Project 10** along with tenant, status, quota, and subject permissions before creating it. Do not default `hasPermission(null, "CREATE")` to allow.

## 5. Action: do not use a single "can access" flag for every operation

A resource typically has distinct actions:

| Action | Example condition |
| --- | --- |
| `READ` | Owner or valid READ share |
| `EDIT` | Has edit permission, document still editable, allowed fields |
| `DELETE` | Owner or admin in matching tenant, not under legal hold |
| `APPROVE` | Eligible approver, not the creator, workflow PENDING |
| `SHARE` | Has share permission, cannot grant beyond own permissions |
| `EXPORT` | Has export permission and complies with classification |
| `CREATE` | Has permission within an existing project/collection |
| `TRANSFER_OWNER` | Has admin permission and valid recipient |

**READ ≠ EDIT ≠ DELETE ≠ SHARE ≠ EXPORT.** Never use `canRead` in place of `canDelete` just because both target Document 42. A user may read an invoice without having permission to bulk-export or approve that invoice.

The system should standardize action names (an enum or typed object), avoiding arbitrary string concatenation from the client used as SpEL expressions. If domain-custom actions are needed, define a clear contract rather than collapsing everything into `"access"`.

## 6. Context: point-in-time and environmental conditions

**Context** differs from resource state: it describes additional information that can change authorization from call to call. For example:

- Selected tenant/workspace **with verified membership**.
- Server time: grant from `validFrom` to `expiresAt`.
- Authentication strength: MFA/step-up completed under trusted criteria.
- Is the account suspended, is the membership active?
- Is the project locked, is the invoice at the PENDING step?
- IP address/network zone/device posture if backed by a trusted verification source.
- Operation characteristics: bulk export, amount/limit, risk level, record count.
- Whether delegation/impersonation has been approved.
- Policy/config version and feature rollout state.

### Trustworthiness of context

Not all context fields share the same level of trust:

| Context | Appropriate source | Pitfall |
| --- | --- | --- |
| `now` | Server/DB `Clock` | Do not rely on `Date.now()` from the browser |
| `tenantId` | Request selector **with verified membership** | `X-Tenant-Id` does not prove permission by itself |
| MFA | Authentication verified by IdP/AS with valid assurance claims | Client-sent `X-MFA-Complete: true` header |
| `document.status` | Database with appropriate transaction/locking | Trusting client-declared status=PENDING in JSON |
| Source IP | Securely configured proxy/trust chain | Trusting arbitrary `X-Forwarded-For` |
| Environment/feature flag | Controlled server/remote configuration | User tampering with authorization flags |
| Share expiry/revoke | Trusted grant store | Non-expired JWT ≠ non-expired share |

If an important condition **cannot be verified** (timeout, missing context, invalid tenant), default to **DENY** or return a safe infrastructure error instead of granting access. **Fail closed** does not mean swallowing every DB error into 403/404 and losing observability; connectivity failures must be distinguished from permission denials.

### Immutable context per request/transaction

A request should have a verified `VerifiedContext` used consistently. Never place the active tenant in a static mutable field or an uncleaned `ThreadLocal`: a thread pool can leak tenant A's context into tenant B's request.

Some policies require a transaction-scoped snapshot; when state changes between check and mutation, add protection via conditional SQL, optimistic locking, or appropriate transaction isolation.

## 7. RBAC, ABAC, ReBAC, and combined policies

| Model | Decision based on | Example |
| --- | --- | --- |
| **RBAC** | Subject's roles | `ROLE_AUDITOR` is allowed to access the audit screen |
| **ABAC** | Attributes of subject, resource, action, environment | READ if tenant matches, classification fits, grant not expired |
| **ReBAC** | Relationship between subject and resource | Alice is owner, Bob is member of the project containing the document |
| **Policy-based** | Rule set combining multiple sources and precedence | Tenant boundary AND business state AND (owner OR share) |

A real-world system often combines them:

```text
ALLOW READ if
  subject.active
  AND subject.hasFunctionAuthority("document:read")
  AND resource.tenant == verifiedTenant
  AND resource.active
  AND (
        resource.owner == subject.id
        OR activeAclOrShareGrant(subject, resource, READ, now)
      )
```

ABAC does not require a separate "policy engine". A typed Java bean with unit tests and clear repository scoping can be a solid dynamic policy. With large rule counts, multiple systems/languages, or policy approvals by separate teams, you can extract a Policy Decision Point, provided you understand the trade-offs in latency, caching, versioning, and dependency failures.

### Deny rules and precedence

Avoid letting multiple OR-ed allow paths accidentally bypass mandatory invariants. For example, **tenant boundary** and **account suspended** must be checked before the owner/share branches:

```text
DENY if account suspended
DENY if tenant not allowed
DENY if resource locked by policy
ALLOW if owner and matching action
ALLOW if share grant still valid and matching action
DENY if no ALLOW branch matched
```

In code, this can be written as an AND condition combined with an OR group, rather than relying on scattered `if` ordering. If the system has conflicting grant/deny rules, define precedence explicitly (deny-overrides, explicit priority, first applicable, etc.). **Do not assume every engine, Spring ACL, and `AuthorizationManager` shares the same global deny-overrides rule.**

## 8. PEP, PDP, PIP, and PAP: separating enforcement from decision

A large dynamic policy system typically uses these conceptual roles:

- **PEP — Policy Enforcement Point:** where requests, methods, or data mutations are **blocked/allowed to execute**.
- **PDP — Policy Decision Point:** where subject-resource-action-context is **evaluated** to produce a decision.
- **PIP — Policy Information Point:** where attributes/relationships/trusted resource state are retrieved.
- **PAP — Policy Administration Point:** where policies are administered, reviewed, versioned, and published.

In Spring Security:

```text
                    HTTP / method call
                           |
                           v
                PEP (Filter / interceptor)
                           |
                           v
              PDP (AuthorizationManager
                   or policy bean)
                     /         \
                    v           v
             PIP: subject    PIP: resource
             + membership    + ACL + state
                    \           /
                     v         v
                   PolicyDecision
                 /               \
               GRANT             DENY
                 |                 |
                 v                 v
             repository        access denied
             scoped query      / HTTP policy
```

A policy Java bean can act as the PDP and query repositories as PIPs without needing a separate network service. If the PDP is an external service, you must design PEP/PDP authentication, minimal request attributes, timeouts, retries, circuit breakers, and **default deny when the PDP cannot verify permissions**. Never let a stale cached decision extend a revoked grant.

### A Decision should not be just a String

An internal model might contain:

```text
Decision {
  effect: ALLOW | DENY
  policyVersion: "doc-policy-7"
  reasonCode: "NOT_OWNER_OR_SHARED"
  evaluatedAt: Instant
  obligations: ["AUDIT_ACCESS"]
}
```

This is an **application-designed illustrative structure**, not a default Spring Security DTO. `reasonCode` can be used for internal auditing, but do not expose owner/tenant/private policy details in an HTTP response to someone unauthorized to know the resource exists.

**Obligations** such as audit logging, watermarking, step-up MFA, or export limits must be **enforced by the PEP**; returning an obligations array that the service ignores means the policy is not actually enforced.

## 9. Spring Security AuthorizationManager<T>: decision context

Modern Spring Security uses `AuthorizationManager<T>` across HTTP, methods, and other integrations. Conceptual contract:

```java
AuthorizationResult authorize(
    Supplier<? extends Authentication> authentication,
    T secureObject
);
```

The actual signature depends on the version, with nullability annotations and specific generic types; since Spring Security 6.4, `authorize` returns `AuthorizationResult`, whereas some earlier docs/versions used `check(...)` returning `AuthorizationDecision`. When writing an application, consult the **Javadoc of the resolved version** rather than copying a simplified signature as a standalone file.

`T` can be:

- `RequestAuthorizationContext` for Servlet HTTP requests: request, method, matcher variables.
- `MethodInvocation` for method calls: method and arguments.
- A custom context/domain object in other policies.

A manager can return **allow**, **deny**, or `null` when abstaining under the API contract. For sensitive protection points, design it to return an explicit DENY when data is missing; do not use `null` as an implicit allow path without understanding how manager aggregators handle abstentions.

### Custom AuthorizationManager for HTTP

Example of a Spring bean managing document URLs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class DocumentHttpSecurityConfig {

    @Bean
    SecurityFilterChain documentChain(
            HttpSecurity http,
            DocumentAccessPolicy policy) throws Exception {

        AuthorizationManager<RequestAuthorizationContext> checkRead =
            (authenticationSupplier, context) -> {

                var authentication = authenticationSupplier.get();
                String idText = context.getVariables().get("documentId");
                Long id;

                try {
                    id = Long.valueOf(idText);
                } catch (NumberFormatException ex) {
                    return new AuthorizationDecision(false);
                }

                boolean allowed = policy.canRead(authentication, id);
                return new AuthorizationDecision(allowed);
            };

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                org.springframework.http.HttpMethod.GET,
                "/api/documents/{documentId}"
            ).access(checkRead)
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

This is a **config component**; `DocumentAccessPolicy` is an application-implemented domain bean, requiring Spring Security dependencies and real authentication configuration. Use path variable matchers compatible with the configured matcher type. `Long.valueOf(null)` throws `NumberFormatException`, so that branch denies. For syntactically invalid path IDs, the controller may also apply HTTP 400/404; do not assume the authorization manager controls all error mapping.

**Limitation:** a request-level manager only sees the request and ID; the policy must read the real Document with tenant/owner/ACL from the server. If the service is also called from batch jobs or another controller, you must **enforce at the service/domain layer** rather than relying solely on a URL matcher.

### Method-level authorization is often closer to the resource

`@EnableMethodSecurity` enables `@PreAuthorize` on Spring-managed methods:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

Service:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentAccessPolicy.canRead(authentication, #documentId)"
    )
    public DocumentView read(@P("documentId") Long documentId) {
        Document doc = documents
            .findById(documentId)
            .orElseThrow();

        return new DocumentView(doc.getId(), doc.getTitle());
    }

    public record DocumentView(Long id, String title) {}
}
```

This is an **application component**, requiring `Document`, a repository, and the `documentAccessPolicy` bean. `@P` provides parameter names to SpEL. **This example only shows how to wire the policy**, not the optimal production data query: a broad `findById` after a pre-check can introduce a race/TOCTOU. For tenant-sensitive data, prefer querying by tenant/owner/ACL scope or re-checking inside a transaction.

In Spring AOP proxy mode, `this.read(...)` called within the same class can bypass the interceptor. `@EnableMethodSecurity` is not enabled automatically merely by adding `spring-boot-starter-security`. Services should be designed with defense in depth so changing call paths does not drop policy enforcement.

## 10. Building a clear subject-resource-action-context Java policy API

Instead of passing dozens of parameters into every method, you can define an **immutable data model**. For example:

```java
public enum DocumentAction {
    READ, EDIT, DELETE, SHARE
}

public record VerifiedSubject(
    String subjectId,
    String tenantId,
    java.util.Set<String> authorities,
    boolean active
) {}

public record ResourceFacts(
    long documentId,
    String tenantId,
    String ownerSubjectId,
    String status,
    boolean deleted
) {}

public record DecisionContext(
    java.time.Instant evaluatedAt,
    boolean mfaConfirmed
) {}
```

These are **application types**, not Spring Security classes. In a real deployment:

- `VerifiedSubject` is built only from verified principal/tenant membership, never bound directly from JSON.
- `ResourceFacts` is fetched only from the database/trusted domain service.
- `DecisionContext` uses the server `Clock` and verified MFA evidence, never a client-declared boolean.
- Enums can be used for status and authorities to reduce typo bugs.
- Under concurrent requests, immutable objects prevent tenant/context mutation mid-flight.

Policy function:

```java
public boolean can(
        VerifiedSubject subject,
        ResourceFacts resource,
        DocumentAction action,
        DecisionContext context) {

    if (subject == null || resource == null
            || action == null || context == null) {
        return false;
    }
    if (!subject.active() || resource.deleted()) {
        return false;
    }
    if (!subject.tenantId().equals(resource.tenantId())) {
        return false;
    }

    String authority = switch (action) {
        case READ -> "document:read";
        case EDIT -> "document:edit";
        case DELETE -> "document:delete";
        case SHARE -> "document:share";
    };

    if (!subject.authorities().contains(authority)) {
        return false;
    }
    if ("ARCHIVED".equals(resource.status())
            && action != DocumentAction.READ) {
        return false;
    }

    boolean owner = subject.subjectId()
        .equals(resource.ownerSubjectId());

    if (action == DocumentAction.DELETE && !context.mfaConfirmed()) {
        return false;
    }

    return owner;
}
```

**This is a skeleton** allowing only the owner to perform actions and is an illustrative policy without share grants/ACLs yet. A later section adds shared relationships and a runnable test. The aim is to highlight **global deny conditions placed before allow paths**. Never write `if (owner) return true` before checking tenant, suspended account, or workflow locks.

### Using repositories as a Policy Information Point

A practical policy bean might fetch data like this:

```java
public boolean canRead(Authentication auth, Long documentId) {
    VerifiedSubject subject = subjects.fromTrustedAuthentication(auth);
    if (subject == null || documentId == null || documentId <= 0) {
        return false;
    }
    if (!subject.authorities().contains("document:read")) {
        return false;
    }

    var document = documents
        .findByIdAndTenantIdAndDeletedFalse(
            documentId, subject.tenantId())
        .orElse(null);

    if (document == null) {
        return false;
    }

    if (subject.subjectId().equals(document.getOwnerSubjectId())) {
        return true;
    }

    return grants.hasActiveReadGrant(
        documentId, subject.tenantId(),
        subject.subjectId(), clock.instant());
}
```

**Illustrative fragment**: `subjects`, `documents`, `grants`, and `clock` are application beans to implement. `hasActiveReadGrant` must verify the exact object ID, tenant, recipient, permission, `validFrom <= now < expiresAt`, revocation, and other business rules. Never use an unverified client-supplied grant row.

With HTTP tenant selection, `subjects.fromTrustedAuthentication` must know the tenant verified via a service, or be passed an independent `VerifiedTenantScope`. `Authentication.getName()` does not always match the real subjectId; multiple issuers require namespacing/identity mapping.

### Do not turn context into permission on its own

A corporate IP, business hours, or completed MFA can be **additional requirements**, but they do not prove ownership/ACL of Document 42. Authorization must combine:

```text
validPrincipal
AND verifiedTenant
AND hasActionPermission
AND resourceInTenant
AND resourceBusinessStateAllows
AND (owner OR activeShareGrant)
AND requiredContextChecks
```

If you skip all object-level authorization just because the user is on VPN, dynamic policy turns into an IDOR vulnerability.

## 11. When is an out-of-JVM policy engine needed?

With only a few services, typed Java rules and tests are usually easiest to verify. A centralized policy/engine can be useful when:

- Multiple microservices must enforce the same policy.
- Rules change frequently and need approvals, audit, rollback, and policy versions.
- ReBAC needs to express multiple levels of projects, folders, teams, and groups.
- Multiple metadata/identity sources must be combined in a controlled way.
- Policy-as-code, dry-run, shadow evaluation, and differential tests are required.

However, a networked engine carries costs:

| Aspect | Design question |
| --- | --- |
| Latency | How many PDP calls does each API need? Are batch decisions supported? |
| Availability | If the PDP does not respond, fail closed with DENY or return 503? |
| Consistency | How quickly must a revoked permission take effect? |
| Attributes | Does the PEP send resource facts or does the PDP fetch them? Who verifies them? |
| Policy version | Which version is logged and tested? |
| Cache | Does the cache key include subject, tenant, action, resource, and context version? |
| Data minimization | Is sensitive personal information being sent to the PDP? |
| Obligations | Who ensures audit, MFA step-up, and watermarking actually happen? |

**Never** send an entire JPA entity or raw JWT to the PDP out of convenience; send minimal attributes signed/fetched from trusted sources without leaking secrets into logs.

### Grouping decisions: allOf, anyOf, and precedence

An example policy can be decomposed:

```text
mandatory =
  authenticated
  AND account active
  AND verified tenant
  AND resource not deleted

resourcePermission =
  owner OR active share OR explicit approved administrator

ALLOW =
  mandatory
  AND action authority
  AND resourcePermission
  AND action-specific context
```

Mandatory predicates must not be mixed into an `OR` group. If an admin bypass branch is permitted, it also requires tenant scoping and business conditions by design. When both explicit deny and grant exist, do not arbitrarily let any grant override a deny without a defined combining algorithm.

## 12. Dynamic policies, time, and state

Permissions can change without the user logging out:

- Admin revokes a role.
- User is removed from a tenant.
- Document changes owner, is archived, soft-deleted, or classified.
- Share grant expires.
- Invoice transitions from PENDING to APPROVED.
- Account is suspended.
- MFA status/assurance is no longer sufficient for a sensitive operation.

Yesterday's `ALLOW` decision is not valid forever. Applications should check the required data **at the time of the operation**, unless a well-designed consistent cache/snapshot model is in place.

### Time: half-open intervals

Temporary grants should use `[validFrom, expiresAt)`:

```java
boolean valid = !now.isBefore(validFrom)
    && now.isBefore(expiresAt)
    && revokedAt == null;
```

Exactly at `expiresAt`, access must be denied. Inject a `Clock` for testing to avoid real sleeps in unit tests. If the database and JVM have clock skew, choose a canonical time source and SLA; an access token's `JWT exp` does not equal a resource-sharing grant's lifetime.

### Race/TOCTOU

```text
T1: check canEdit(alice, doc42) => ALLOW
T2: admin revokes access / changes tenant or owner
T1: repository.save(doc42) continues
```

A standalone `@PreAuthorize` can run **before** the method's transaction advice. Therefore, if data consistency at update time is required:

- Read and check authorization conditions within the same transaction.
- Use `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ? AND status = ?`, combined with version/ACL conditions where appropriate.
- Use optimistic/pessimistic locking according to sensitivity and cost.
- Establish ordering between revocation commits and in-flight operations.
- Check the affected row count; if 0, do not assume success.

Never claim `@Transactional` automatically eliminates all races; under `READ_COMMITTED`, membership and state can still change between separate queries.

## 13. Data-scoped queries matter just as much as policy beans

Even when a policy service checks the object, the repository should also enforce tenant/owner/ACL scope when accessing sensitive data.

Example SELECT:

```sql
SELECT id, title, status
FROM documents
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND deleted = FALSE;
```

If the policy only allows the owner:

```sql
SELECT id, title
FROM documents
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE;
```

For an EDIT operation:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :requested_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND status = 'DRAFT'
  AND deleted = FALSE;
```

The SQL above is a **logical pattern**, not a default Spring schema; for shares/ACLs, express the full policy in the query or use appropriate transactions/locking. `:verified_tenant` and `:authenticated_subject` must come from the server, not raw headers/bodies.

### RLS, Hibernate filters, and bypass paths

PostgreSQL Row-Level Security can add a DB protection layer; however, if the application sets the tenant context from unverified input, RLS merely enforces that **wrong** tenant. The request-executing role must not have `BYPASSRLS`, and connection pools must ensure tenant context does not leak across requests.

Hibernate filters/tenant resolvers do not automatically protect every native SQL query, bulk query, file storage path, search index, or external service. All read/write/export paths need appropriate boundaries.

### Returned data and property-level authorization

Being allowed to READ Document 42 does not mean seeing `privateNotes`, `legalHold`, or API tokens attached to the document. DTOs should only expose fields permitted by policy; when needed, split `READ_PUBLIC_FIELDS` and `READ_CONFIDENTIAL_FIELDS` permissions. For updates, never bind raw JSON directly onto an entity and persist fields like `ownerId`, `tenantId`, or `approvedBy`.

## 14. Standalone runnable Java 17 test: multi-dimensional policy

The following program uses **plain Java**, without Spring Security or a database. It simulates how a single policy takes subject–resource–action–context; it does not use `Thread.sleep` and produces deterministic stdout. Authentication and tenant membership behave as trusted fixture data **in the demo**, not as a production authentication mechanism.

Create `ContextualAuthorizationDemo.java`:

```java
import java.time.Instant;
import java.util.Map;
import java.util.Set;

public class ContextualAuthorizationDemo {

    enum Action { READ, EDIT, DELETE, SHARE }

    record Subject(
        String id, String tenant, Set<Action> actions, boolean active
    ) {}

    record Resource(
        long id, String tenant, String owner, boolean archived,
        boolean deleted
    ) {}

    record Share(
        long resourceId, String grantee, Action action,
        Instant from, Instant until, boolean revoked
    ) {}

    record Context(
        Instant now, boolean strongAuthentication
    ) {}

    static boolean hasActiveShare(
            Subject subject, Resource resource,
            Action action, Context context, Share share) {

        return share != null
            && share.resourceId() == resource.id()
            && share.grantee().equals(subject.id())
            && share.action() == action
            && !share.revoked()
            && !context.now().isBefore(share.from())
            && context.now().isBefore(share.until());
    }

    static boolean can(
            Subject subject, Resource resource,
            Action action, Context context, Share share) {

        if (subject == null || resource == null
                || action == null || context == null
                || !subject.active() || resource.deleted()) {
            return false;
        }

        // Mandatory boundary: tenant + action capability.
        if (!subject.tenant().equals(resource.tenant())
                || !subject.actions().contains(action)) {
            return false;
        }

        // Archived resources cannot be modified or shared.
        if (resource.archived() && action != Action.READ) {
            return false;
        }

        // DELETE requires stronger authentication for everyone.
        if (action == Action.DELETE
                && !context.strongAuthentication()) {
            return false;
        }

        boolean isOwner = subject.id().equals(resource.owner());
        boolean shared = hasActiveShare(
            subject, resource, action, context, share);

        return isOwner || shared;
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-05T09:00:00Z");
        Context normal = new Context(start.plusSeconds(60), false);
        Context strong = new Context(start.plusSeconds(60), true);

        Subject alice = new Subject(
            "alice", "tenant-a", Set.of(Action.READ,
                Action.EDIT, Action.DELETE, Action.SHARE), true);
        Subject bob = new Subject(
            "bob", "tenant-a", Set.of(Action.READ, Action.EDIT), true);
        Subject carol = new Subject(
            "carol", "tenant-b", Set.of(Action.READ), true);
        Subject blocked = new Subject(
            "alice", "tenant-a", Set.of(Action.READ), false);

        Resource doc42 = new Resource(
            42, "tenant-a", "alice", false, false);
        Resource archived = new Resource(
            50, "tenant-a", "alice", true, false);

        Share bobRead = new Share(
            42, "bob", Action.READ,
            start, start.plusSeconds(300), false);

        System.out.println("Owner read: "
            + can(alice, doc42, Action.READ, normal, null));
        System.out.println("Shared read: "
            + can(bob, doc42, Action.READ, normal, bobRead));
        System.out.println("Shared edit denied: "
            + can(bob, doc42, Action.EDIT, normal, bobRead));
        System.out.println("Cross tenant denied: "
            + can(carol, doc42, Action.READ, normal, bobRead));
        System.out.println("Delete without MFA: "
            + can(alice, doc42, Action.DELETE, normal, null));
        System.out.println("Delete with MFA: "
            + can(alice, doc42, Action.DELETE, strong, null));
        System.out.println("Archived edit: "
            + can(alice, archived, Action.EDIT, strong, null));
        System.out.println("Inactive owner: "
            + can(blocked, doc42, Action.READ, normal, null));
        System.out.println("Share at expiry: "
            + can(bob, doc42, Action.READ,
                new Context(start.plusSeconds(300), false), bobRead));
        System.out.println("Share revoked: "
            + can(bob, doc42, Action.READ, normal,
                new Share(42, "bob", Action.READ,
                    start, start.plusSeconds(300), true)));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ContextualAuthorizationDemo.java
java ContextualAuthorizationDemo
```

Exact stdout:

```text
Owner read: true
Shared read: true
Shared edit denied: false
Cross tenant denied: false
Delete without MFA: false
Delete with MFA: true
Archived edit: false
Inactive owner: false
Share at expiry: false
Share revoked: false
```

**Explanation of each condition group:**

- Alice is the owner so she can READ, and can DELETE only when strong authentication context is server-verified.
- Bob can READ via a grant matching resource ID, action, recipient, and time; a READ grant does not confer EDIT.
- Carol does not belong to the document's tenant, so she is denied before any share path.
- Archived documents do not accept EDIT.
- Inactive accounts are denied even when they are the owner.
- Exactly at `until`, the grant expires because `now < until` is enforced; revoked grants also cannot grant access.

**Limitation:** the demo does not verify real JWT, MFA, Membership, or ACLs; `Subject`/`Share` are built from fixtures. `Set.of(...)` is program-controlled grant data. In a real application, these objects must be constructed from trusted sources and the result must be enforced in repositories/transactions/HTTP enforcement. Do not use the demo as a production policy without additional business conditions.

## 15. Thinking with decision tables to avoid conflicting rules

Instead of just writing one long expression, build a decision table. Suppose the Document policy:

| Subject | Resource | Action | Context | Expected |
| --- | --- | --- | --- | --- |
| Alice owner | Document 42 same tenant | READ | Active | ALLOW |
| Alice owner | Document 42 same tenant | DELETE | Not strongly authenticated | DENY |
| Alice owner | Document 42 same tenant | DELETE | MFA verified | ALLOW if no other block |
| Bob recipient | Document 42 same tenant | READ | Grant active | ALLOW |
| Bob recipient | Document 42 same tenant | EDIT | Only has READ share | DENY |
| Bob recipient | Document 42 same tenant | READ | Grant expired | DENY |
| Bob recipient | Document 42 same tenant | READ | Grant revoked | DENY |
| Carol | Document 42 different tenant | READ | Has general authority | DENY |
| Alice suspended | Document 42 as owner | READ | Account inactive | DENY |
| Alice owner | Archived document | EDIT | Has EDIT authority | DENY |
| Anonymous | Document 42 | READ | Not authenticated | DENY |
| Unauthorized service principal | Document 42 | EXPORT | Background job | DENY |

Mandatory conditions can be tested as **invariants**:

```text
For every subject, resource, action, context:
  if subject inactive -> DENY
  if resource deleted -> DENY
  if tenant not verified -> DENY
  if action not authorized -> DENY
  if no owner/share/ACL relationship -> DENY
```

A good regression test also mutates **a single dimension** of the input: changing only the tenant, only the ID, only the action, or only the time. If the policy is written properly, the outcome must flip at the documented boundaries.

## 16. Testing real Spring Security through the interceptor

Unit testing a policy bean directly is necessary, yet **does not prove** Spring Security is actually invoking it. The policy might be right while:

- `@EnableMethodSecurity` is not enabled.
- The service was instantiated with `new`, not as a Spring bean.
- An internal `this.method()` call bypasses the AOP proxy.
- A new endpoint calls the repository directly and skips the service.
- `@PreAuthorize` uses the wrong SpEL parameter name, or uses a global role from another tenant.
- The `SecurityFilterChain` matcher does not match the actual route.
- Request-level policy blocks GET while PUT/DELETE uses another path.

Use `@SpringBootTest`/`MockMvc` or HTTP integration tests and `spring-security-test` to verify:

1. Authentication mapping matches production: JWT subject/issuer, custom principal, authorities.
2. The policy bean is invoked with the right ID/resource/action.
3. Tenant membership comes from the server, not an unverified header.
4. Deny prevents service method execution and side effects when expected.
5. The repository does not return data outside the tenant or object scope.
6. Correct 401/403/404 status codes per API contract.
7. Expired/revoked share grants take effect even with a warm cache and when requests hit another node.
8. Writes are genuinely rejected in the transaction, rather than returning 403 after data has already been mutated.

Example test fragment for an API whose policy hides out-of-scope resources:

```java
mockMvc.perform(get("/api/documents/{id}", 42L)
        .with(user("bob").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().isNotFound());
```

This is a **fragment**, requiring the `MockMvc` bean, static imports, user/tenant fixtures, and corresponding policy implementation. If Bob has a READ share, the expectation must be 200; fixtures must control grants so results are reliable. `@WithMockUser`/`user(...)` also does not automatically reproduce every production JWT/issuer/MFA mapping.

### Testing infrastructure failures

Put the membership/ACL repository into a timeout state and verify:

- It must not ALLOW.
- It must not return data.
- Internal logs identify the dependency failure.
- HTTP can return an appropriate 5xx/503 instead of turning every outage into "not found".
- No stale positive cache exceeds the revocation SLA.
- No "fallback = owner by default" when resource facts are missing.

**Fail closed** means not granting access when it cannot be proven, not swallowing errors and calling the system secure.

## 17. Performance, batch decisions, and caching

Dynamic policies often look up:

- Membership/roles.
- Resource/owner/tenant.
- ACL/share grants.
- Status/feature flags.
- Account state/MFA assurance.

If a list has 500 documents and the application calls the policy 500 times, fetching resources + grants separately each time, it can create **N+1 queries**.

Ways to improve:

1. Filter and paginate **in SQL by scope** before fetching data.
2. Bulk-fetch facts/relationships/ACLs for a verified set of IDs.
3. Batch requests to the PDP if the engine supports batching.
4. Cache low-churn reference data with invalidation; avoid caching ALLOW for too long when permissions are volatile.
5. Separate coarse action checks from resource checks to reject clearly invalid requests early.
6. Monitor decision counts, deny rates, query latency, p95/p99, and source errors, **without logging tokens/secrets**.

### Cache keys must include every decision dimension

A key like `canRead:document42` is **wrong** if users Bob and Alice share it. At minimum, consider:

```text
subjectId | tenantId | resourceType | resourceId | action
| policyVersion | relevantSubjectOrAclVersion | relevantContextBucket
```

If time is a condition, a cached ALLOW must **expire no later than the grant expiry**, and mid-term revocation requires invalidation/online checks. You cannot promise 1-second revocation if a cache keeps a GRANT result for 15 minutes without checking the source of truth.

For sensitive environments, caching **resource facts** and re-evaluating the policy from trusted sources may be safer than caching booleans. Test whenever role, owner, tenant, account status, or document classification changes.

### Caching and data leaks from other layers

Tenant/principal cache key separation is also needed at:

- HTTP/CDN responses.
- Search indexes and pagination counts.
- Object storage/presigned URLs.
- Export results, email attachments, background reports.
- Frontend query state when switching tenants.

A correct policy in the controller helps nothing if the CDN serves tenant A's cached data to tenant B.

## 18. Dynamic policy governance and rollout

When rules change without redeploying, the attack surface shifts to **who is allowed to edit policies**.

Reliable workflow:

1. Author policies in a repository with access control and auditing.
2. Require review by authorized personnel; do not let ordinary users submit arbitrary JSON policies.
3. Validate syntax and schema of attributes/actions.
4. Run regression tests with a representative decision table.
5. Verify **negative tests**: cross-tenant, missing role, revoked, expired, mismatched resource.
6. Run shadow evaluation to compare the old policy against the candidate where appropriate; **shadow must never replace enforcement**.
7. Roll out by version/canary with rollback capability.
8. Log policy version and internal reason code for reconciliation.
9. Invalidate caches and policy bundles after publish or revocation.
10. Set "deny by default" for unknown actions/resource types.

**Never** let an admin UI accept a raw SpEL expression from user input and evaluate it as server code. Dynamic policies should be rule data with a controlled schema/DSL, or reviewed code/configuration. A SpEL string supplied by an untrusted party can become an unintended expression execution risk.

### Policy version and auditing

An audit event should record enough data to explain the decision:

```text
requestId: req-123
subject: u-1001
tenant: tenant-a
resource: Document/42
action: EDIT
decision: DENY
reasonCode: ARCHIVED_RESOURCE
policyVersion: doc-policy-8
evaluatedAt: 2026-11-05T09:00:00Z
```

Contents are illustrative only. Logs must comply with privacy/retention rules and never contain access tokens, passwords, full content, or sensitive claims. Never return internal reasons like "owner is Bob, tenant is Finance" in responses to users unauthorized to know the document exists.

### Should DENY reasons be disclosed?

For users authorized to know an object exists, the UI can display "Cannot edit an archived document". For users outside the tenant or unaware whether an object exists, the API can return a neutral `404 Not Found` for both nonexistent and hidden resources. **Do not** default every deny to 404; HTTP policy must be consistent and distinct from domain decisions.

## 19. Common mistakes and how to fix them

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Using only `hasRole('USER')` | Ignores resource/tenant/action | Add subject–resource–action–context checks |
| Trusting owner/tenant from request JSON | Client spoofs attributes to gain access | Load resource facts from the server |
| Using tenant A's admin role in tenant B | Privilege escalation | Tenant-scoped memberships and rights |
| Treating client-sent MFA header as trusted | Step-up bypass | Use authenticated assurance from the auth system |
| Using browser time for expiry | User can alter system clock | Server `Instant` and injected `Clock` |
| Placing owner allow before tenant/global deny | Owner bypasses tenant/status/account lock | Check invariants before allow branches |
| Using `READ` for EDIT/EXPORT/SHARE as well | Overly broad permissions | Action enum and dedicated policies |
| Resource ID matches but type differs | Cross-type ID collision | Explicit type + ID + tenant identity |
| Returning JPA entities directly | Leaks properties/relations | DTO allowlist/field authorization |
| Using `@PreAuthorize` then unscoped update | Race/TOCTOU | Conditional DB mutation, transaction/versioning |
| Using `@PostAuthorize` to protect writes | Side effects may commit before deny | Pre-check and scoped mutation |
| Testing method annotations with Java `new Service()` | Bypasses Spring proxy | Integration test through Spring beans |
| Treating `Authentication.isAuthenticated()` as enough against anonymous | Anonymous tokens may require trust resolver | Check principal and authentication trust properly |
| Using `null`/abstain as implicit permit | Unclear policy when rules are missing | Explicit DENY/default deny |
| Caching ALLOW without subject/action/tenant | Cross-user data leak | Full-scope cache keys or re-check |
| Caching beyond share expiry | Grants expired access | TTL capped at expiry and revocation invalidation |
| Swallowing DB timeout into ALLOW | Fail open | Return safe error, never grant access |
| Swallowing every exception into 404 | Hard to debug, breaks availability/error contract | Separate denials from dependency failures |
| Accepting arbitrary SpEL/policy scripts from client | Injection/unsafe execution | Structured DSL/allowlist, policy review |
| Testing only positive/happy paths | Misses IDOR and privilege escalation | Four-dimensional negative test matrix |
| Enabling RBAC while skipping query scoping | Other tenants' resources still read/written | Repository/DB enforcement |
| Returning permitAll when remote PDP fails | Allows access when policy system is down | Fail closed, circuit breaker, and 5xx when needed |
| Forgetting background jobs/exports | Bypasses HTTP policy | Service/domain authorization and trusted service identity |

## 20. Project adoption checklist

Before taking a dynamic policy to production, be able to answer:

1. **Subject:** where does identity come from, and is it verified and namespaced by issuer when needed?
2. **Tenant:** have tenant membership and status been verified, and are roles properly scoped?
3. **Resource:** which database provides facts/owner/status/tenant, and are exact object ID/type read?
4. **Action:** do actions have a typed enum and distinct policies?
5. **Context:** which trusted sources supply time, MFA, IP, device, and request risk?
6. **Precedence:** how do global deny and local allow combine, and is default deny explicit?
7. **Create:** when a resource has no ID yet, how are permissions checked on the parent/collection?
8. **Consistency:** is there TOCTOU risk between policy check and mutation, and what transaction/lock/version is needed?
9. **Database:** do all SELECT/UPDATE/DELETE/list/count/export queries enforce tenant/ACL scope?
10. **Spring:** do `SecurityFilterChain`, `@EnableMethodSecurity`, proxies, and request matchers actually work?
11. **Dynamic updates:** who can edit policies, and how are versioning/review/canary/rollback handled?
12. **PDP availability:** if the policy service disconnects, does it still fail closed?
13. **Caching:** do keys include subject/tenant/resource/action/context/version, and do revocations/expirations take effect?
14. **Observability:** are decisions, sources, and policy versions audited without leaking sensitive data?
15. **HTTP contract:** are 401/403/404 mapped intentionally, avoiding existence oracles?
16. **Tests:** is there a positive/negative matrix covering all four dimensions?
17. **Concurrency:** are role/share revocations and concurrent updates tested?
18. **Non-HTTP:** do workers/async/queues/microservices have appropriate identities and policies?
19. **Sensitive fields:** are response DTOs, field-level updates, and exports properly restricted?
20. **Security review:** have policy bypasses, default allow, and cross-tenant admin risks been checked?

**Conclusion:** Effective dynamic policy design does not begin with a long expression inside `@PreAuthorize`, but with **a clear subject–resource–action–context decision model**. Verify the source of every attribute, separate mandatory conditions from allow branches, default to deny, enforce at both service and database layers, manage changes by version, and test across permission/resource/time variations. Spring Security provides `AuthorizationManager`, HTTP authorization, and method security; the application must build a **trustworthy domain policy consistent** with business data.

## Official references

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `Authentication`, `GrantedAuthority`, `AuthorizationManager`, decision/abstain, and interception structure.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, `RequestAuthorizationContext`, and custom request access managers.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, proxy/AOP, and customization.
- [Spring Security API — AuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`/`verify` contract in the current version.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, and per-request checks.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level checks and scoped resource queries.
- [OWASP API Security Top 10 — API1:2023 BOLA](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): protecting the exact resource ID.
- [NIST SP 800-162 — ABAC](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): attribute-based access control model, subject/object/action/environment, and policy.
