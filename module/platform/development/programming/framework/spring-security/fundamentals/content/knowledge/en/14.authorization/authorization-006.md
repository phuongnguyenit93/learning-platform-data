# ABAC: Attribute-Based Access Control Using User, Resource, and Context Attributes

> **Focus:** how to make authorization decisions from **user attributes (subject)**, **resource/object attributes**, **action**, and **context (environment)**; and how to implement them safely in Spring Security. The main example uses standalone Java 17 to observe decisions; the Spring integration examples are illustrative configuration snippets with explicitly noted dependencies.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain ABAC (Attribute-Based Access Control) and distinguish **authentication** from **authorization**.
2. Write policies based on user, resource, action, and environment attributes; understand **Permit**, **Deny**, missing-data handling, and the **deny-by-default** principle.
3. Compare ABAC with RBAC, ACL, and ReBAC; know when to combine them rather than replacing RBAC completely.
4. Design a pipeline for loading trusted attributes, evaluating policies, and blocking access on the backend with Spring Security.
5. Test scenarios involving cross-tenant access, missing MFA, non-compliant devices, another user's resources, access hours, and permission changes.

## 2. What Is ABAC?

ABAC is an access control model in which the system decides whether a **subject** may perform an **action** on an **object/resource** under specific **contextual conditions**, by evaluating attributes against policies. This matches the framing in NIST SP 800-162.

Instead of asking only *“does this person have the EDITOR role?”*, ABAC can ask:

> “Is the user active, in the same tenant as the document, the owner or in a permitted department, MFA-verified, using a managed device; and if editing the document, is it within working hours?”

The decision depends on a **combination** of conditions; the same user may be permitted to read document A but not document B, or permitted to read today but not edit outside allowed hours.

### Four Types of Information in Policy Evaluation

| Component | Question | Example attributes |
| --- | --- | --- |
| **Subject** (user/principal) | Who is requesting? | `userId`, `tenantId`, `department`, `roles`, `accountStatus`, MFA verification status, project groups |
| **Resource/Object** | What is being accessed? | `documentId`, `ownerId`, `tenantId`, `classification`, `department`, archived/locked state |
| **Action/Operation** | What do they want to do? | `READ`, `EDIT`, `APPROVE`, `EXPORT`, `DELETE` |
| **Environment/Context** | Under what conditions does the request occur? | Server time, trusted network zone, device compliance state, risk level, login session |

**Action is also a policy input:** reading and editing the same resource usually have different requirements. Attributes do not have to be strings; they can be sets of roles, enum values, security labels, timestamps, counts, or verified relationships. The system must define the data type, source, and trustworthiness of each attribute.

A simple representation:

```text
Decision = EvaluatePolicy(subjectAttributes,
                          resourceAttributes,
                          action,
                          environmentAttributes)
         ∈ {PERMIT, DENY}
```

In larger ABAC/Policy Engine architectures, internal evaluation results may further distinguish `NotApplicable` or `Indeterminate`. However, at the enforcement point protecting a resource, **without an explicit allow decision, access must be denied**. Never turn an attribute-loading failure into granted access.

### Where Does ABAC Fit?

- **Authentication**: proves “who is calling” (session, password, bearer token, OAuth2/OIDC...); produces a trusted `Authentication`/principal.
- **Authorization**: determines which operations that principal is allowed to perform on a specific resource in the current context.
- **Enforcement**: the backend actually blocks or allows the operation, even when the UI does not show the corresponding button.

For example, a validly logged-in user accessing a document from another tenant must still receive `DENY` from ABAC. `isAuthenticated()` alone cannot protect ownership, tenant isolation, or data classification.

## 3. Comparing With RBAC, ACL, and ReBAC

| Model | Primary basis | Best suited when | Limitations to watch |
| --- | --- | --- | --- |
| **RBAC** (Role-Based) | Permissions assigned to roles like `ADMIN`, `EDITOR` | Administrative functions, stable permission groups | Roles do not by themselves describe which document belongs to which user/tenant |
| **ACL** (Access Control List) | Permission lists attached per resource for users/groups | Per-file sharing, named grants | Lists can grow large and costly to synchronize |
| **ReBAC** (Relationship-Based) | Graph relationships: “member”, “manager”, “shared by” | Collaborative systems with nested relationships | Resolving graph relationships can become complex |
| **ABAC** | Combines multiple attributes and context in policies | Multi-tenancy, data classification, compliance/dynamic context | Policies are hard to control if attribute sources, rule precedence, and tests are unclear |

Models **can be combined**: role `REPORT_READER` is an attribute of the subject in ABAC; a document can also have an ACL of shared users; a “member of owning group” relationship can be resolved by ReBAC before policy evaluation.

**Counterexample for pure RBAC:** `hasRole('MANAGER')` allows a manager in tenant A to read sensitive reports of tenant B if tenant and resource checks are missing. Object-scope checks must be combined. **Counterexample for poorly designed ABAC:** merely checking `department == finance` and allowing access to all finance reports across all tenants is equally unsafe.

## 4. Defining the Policy Before Writing Code

Suppose a multi-tenant document platform exists. A document has `ownerId`, `tenantId`, `department`, `sensitivity` (INTERNAL/CONFIDENTIAL), and `archived`. Initial policy version:

1. The user must be authenticated and the account must be active; **the user's tenant and the document's tenant must match**.
2. Archived documents cannot be read or edited through this business API.
3. The subject must be the **owner** or belong to the same `department` as the document to be considered further.
4. `CONFIDENTIAL` documents additionally require **verified MFA**, a **compliant managed device**, and the **CORPORATE network zone**.
5. The `READ` action is permitted after the conditions above pass.
6. The `EDIT` action is permitted only for the **owner**, and only during **08:00–17:59 in Asia/Ho_Chi_Minh**.
7. Missing required attributes, untrusted sources, unknown actions, or evaluation errors → **DENY**, while recording internal audit logs per policy.

This logic can be expressed in a business-readable form:

```text
PERMIT(subject, document, action, context) IF
  subject.active
  AND subject.tenantId == document.tenantId
  AND NOT document.archived
  AND (subject.userId == document.ownerId
       OR document.department IN subject.departments)
  AND (
       document.sensitivity != CONFIDENTIAL
       OR (
           subject.mfaVerified
           AND context.managedDevice
           AND context.networkZone == CORPORATE
       )
  )
  AND (
       action == READ
       OR (
           action == EDIT
           AND subject.userId == document.ownerId
           AND 08:00 <= context.localTime < 18:00
       )
  )
DENY otherwise.
```

Here “owner or same department” satisfies only **one** condition. The user is still blocked if the tenant mismatches or MFA is not met. Because the policy does not define `DELETE`, that operation is denied by default rather than inferred from `EDIT`.

### Decision Scenarios

| Subject | Resource/action/context | Decision | Reason |
| --- | --- | --- | --- |
| Alice, tenant A, owner, MFA verified | Confidential document in tenant A; read from managed device/corporate network | PERMIT | All conditions met |
| Alice, tenant A, owner | Edit the document above at 10:00 Vietnam time | PERMIT | Is owner and within working hours |
| Bob, tenant B, same department | Read confidential document in tenant A | DENY | Different tenant, regardless of department |
| Carol, tenant A, same department, no MFA | Read confidential document in tenant A | DENY | Missing MFA |
| Alice, owner, MFA verified | Read confidential from non-compliant device | DENY | Device condition not met |
| Alice, owner, MFA verified | Edit at 22:00 Vietnam time | DENY | Outside allowed hours |
| Alice | Delete document when policy only defines READ/EDIT | DENY | Action not permitted |

This is an **illustrative policy**, not a Spring Security/NIST default. Each product must confirm business rules with data owners; avoid inferring permissions intuitively.

## 5. ABAC Component Flow: PEP, PDP, PIP, PAP

```text
Client / API caller
       |
       v
Authentication -> verified principal/subject identity
       |
       v
PEP: enforcement point (controller/service/gateway)
       |  requests: subject, resource ID, action, context
       v
PIP: loads trusted attributes
       |-- user/tenant/group from identity store
       |-- owner/tenant/classification from resource database
       |-- server time, device/session state from trusted source
       v
PDP: evaluates policy -> PERMIT / DENY
       |
       v
PEP: enforces -> allow business execution or deny
       |
       +--> audit: rule/policy version, decision, timestamp, correlation ID

PAP: policy authoring/approval/version control
        -> supplies active policy to PDP
```

- **PEP** (Policy Enforcement Point): where the decision is **mandatorily enforced**; hiding a button in the frontend is never enough.
- **PDP** (Policy Decision Point): evaluates policy conditions; may be Java code or a dedicated policy engine.
- **PIP** (Policy Information Point): fetches attributes; never implicitly trusts values sent in the request.
- **PAP** (Policy Administration Point): manages policies, reviews, deploys, rolls back, and audits changes.

These are **architectural roles**, not necessarily four interfaces with matching names in Spring Security. In small projects, PEP and PDP can live in the same process. When separated into services, handle timeouts, network errors, consistency, and caching safely: **never default to Permit when the PDP/PIP is unreachable**.

### Which Attribute Sources Are Trusted?

- Subject `userId`/`tenantId`: obtained from a **verified** principal/claims or identity store with controlled mapping; JWT claims are trustworthy only after verifying signature, issuer, audience, expiry, and applicable policies.
- `resource.tenantId`/`ownerId`: loaded from the real data store by resource ID; **never accept** client-sent owner/tenant as truth.
- Time: use the server clock via `Clock`/`Instant`; if the policy uses local time, convert with an explicit `ZoneId`. Never trust a “current-time” header.
- “MFA verified”: trusted state of the session/identity provider that is sufficiently fresh as required; a frontend flag `mfa=true` provides no guarantee.
- Network/device: a managed source or trusted gateway with provenance guarantees; `X-Forwarded-For` or an IP provided directly by a client does not by itself prove location/network zone.

## 6. Complete, Standalone Runnable Java 17 Example

The following example uses only Java SE 17, without Spring Boot. It is a **small policy engine for learning**, with immutable data structures for sample values. The policy matches section 4. Save as **`AbacDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.util.Set;

public class AbacDemo {
    enum Action { READ, EDIT }
    enum Sensitivity { INTERNAL, CONFIDENTIAL }

    record Subject(
            String userId,
            String tenantId,
            Set<String> departments,
            boolean active,
            boolean mfaVerified) {}

    record Document(
            String documentId,
            String tenantId,
            String ownerId,
            String department,
            Sensitivity sensitivity,
            boolean archived) {}

    record RequestContext(
            Instant requestTime,
            String networkZone,
            boolean managedDevice) {}

    record Decision(boolean permitted, String reason) {
        static Decision permit() {
            return new Decision(true, "allowed");
        }
        static Decision deny(String reason) {
            return new Decision(false, reason);
        }
        String display() {
            return permitted ? "PERMIT" : "DENY (" + reason + ")";
        }
    }

    static Decision evaluate(
            Subject subject,
            Document document,
            Action action,
            RequestContext context) {

        // Missing critical information: fail closed.
        if (subject == null || document == null
                || action == null || context == null
                || subject.userId() == null
                || subject.tenantId() == null
                || subject.departments() == null
                || document.tenantId() == null
                || document.ownerId() == null
                || document.department() == null
                || document.sensitivity() == null
                || context.requestTime() == null
                || context.networkZone() == null) {
            return Decision.deny("missing attributes");
        }

        if (!subject.active()) {
            return Decision.deny("inactive account");
        }
        if (!subject.tenantId().equals(document.tenantId())) {
            return Decision.deny("tenant mismatch");
        }
        if (document.archived()) {
            return Decision.deny("archived document");
        }

        boolean owner = subject.userId().equals(document.ownerId());
        boolean sameDepartment =
                subject.departments().contains(document.department());

        if (!owner && !sameDepartment) {
            return Decision.deny("no matching relation");
        }

        if (document.sensitivity() == Sensitivity.CONFIDENTIAL) {
            if (!subject.mfaVerified()) {
                return Decision.deny("MFA required");
            }
            if (!context.managedDevice()) {
                return Decision.deny("managed device required");
            }
            if (!"CORPORATE".equals(context.networkZone())) {
                return Decision.deny("corporate network required");
            }
        }

        if (action == Action.EDIT) {
            if (!owner) {
                return Decision.deny("owner required for edit");
            }
            int hour = context.requestTime()
                    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                    .getHour();
            if (hour < 8 || hour >= 18) {
                return Decision.deny("outside business hours");
            }
        }

        return Decision.permit();
    }

    static void print(String label, Decision decision) {
        System.out.println(label + ": " + decision.display());
    }

    public static void main(String[] args) {
        Subject alice = new Subject(
                "alice", "tenant-a", Set.of("finance"), true, true);
        Subject bob = new Subject(
                "bob", "tenant-b", Set.of("finance"), true, true);
        Subject carol = new Subject(
                "carol", "tenant-a", Set.of("finance"), true, false);

        Document report = new Document(
                "report-7", "tenant-a", "alice", "finance",
                Sensitivity.CONFIDENTIAL, false);

        // 03:00 UTC = 10:00 in Vietnam on 2026-11-04.
        RequestContext office = new RequestContext(
                Instant.parse("2026-11-04T03:00:00Z"),
                "CORPORATE", true);
        RequestContext unmanaged = new RequestContext(
                office.requestTime(), "CORPORATE", false);
        // 15:00 UTC = 22:00 in Vietnam on the same day.
        RequestContext night = new RequestContext(
                Instant.parse("2026-11-04T15:00:00Z"),
                "CORPORATE", true);

        print("alice read", evaluate(alice, report, Action.READ, office));
        print("alice edit", evaluate(alice, report, Action.EDIT, office));
        print("bob read", evaluate(bob, report, Action.READ, office));
        print("carol read", evaluate(carol, report, Action.READ, office));
        print("alice unmanaged", evaluate(
                alice, report, Action.READ, unmanaged));
        print("alice edit at night", evaluate(
                alice, report, Action.EDIT, night));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 AbacDemo.java
java AbacDemo
```

**Exact expected stdout:**

```text
alice read: PERMIT
alice edit: PERMIT
bob read: DENY (tenant mismatch)
carol read: DENY (MFA required)
alice unmanaged: DENY (managed device required)
alice edit at night: DENY (outside business hours)
```

### Explaining the Branches

- **Alice/READ:** same tenant, is owner, document not archived, MFA verified, managed device, and acceptable network zone → Permit.
- **Alice/EDIT at 10:00:** in addition to common checks, is owner and server time converted to Vietnam time is in `[08:00,18:00)` → Permit.
- **Bob/READ:** despite same department, `tenant-b != tenant-a` → Deny. Tenant boundaries must be checked before granting access via relationships/roles.
- **Carol/READ:** same tenant and same department, yet no MFA for a confidential document → Deny.
- **Alice/READ from non-compliant device:** even as owner, missing context condition → Deny.
- **Alice/EDIT at 22:00:** valid credentials and owner, yet outside the allowed time window → Deny.

Notable detail: Java `record`s help model data, yet **do not prove attributes are genuine**. The example builds subject/context from fixed values for clear observation; in production integration, attributes must come from trusted sources. If a collection passed into a record might be mutable, consider `Set.copyOf(...)` in the constructor to prevent mutating attributes after creating a policy snapshot.

**Intentional limitation:** `Action` only includes `READ`/`EDIT`; if the business adds `EXPORT`/`DELETE`, define separate rules and test them. Do not assume EDIT privilege implies every other action.

## 7. Bringing ABAC Into Spring Security

Spring Security provides authentication mechanisms, principals, interceptors, and `AuthorizationManager` to enforce decisions. **Spring Security does not automatically know your `tenantId`, `ownerId`, `classification`, or business policy**. Your system must supply the corresponding data and logic.

### 7.1. Multi-Layer Enforcement

1. At the HTTP layer: use `authorizeHttpRequests` for Servlet or `authorizeExchange` for WebFlux to force requests onto an authenticated path.
2. At the **service/method** layer: evaluate attributes of the **real resource** and authenticated subject, because policies depend on the specific object.
3. At the query layer: apply appropriate tenant scoping and row-level constraints so data is not leaked or loaded across tenants by mistake.
4. At the update/delete business layer: check permission for the exact action and ensure evaluated attributes cannot change dangerously after the check.

Do not use frontend checks, hidden buttons, or `@PreAuthorize("isAuthenticated()")` as the **sole mechanism** protecting permissions on individual documents.

### 7.2. Servlet: @EnableMethodSecurity and @PreAuthorize

In Spring Security 6.x/7.x for Servlet applications, enable method security and invoke a policy bean from SpEL:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class DocumentService {
    private final DocumentRepository documents;

    DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
    public DocumentDetails read(String documentId) {
        return documents.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);
    }
}
```

This is an **illustrative integration snippet**, not a standalone compilable file. You must provide `DocumentRepository`, `DocumentDetails`, `DocumentNotFoundException`, the `documentPolicy` bean, corresponding Spring imports, and application configuration. Method security requires calls to pass **through a Spring-managed proxy**; an internal call `this.read(...)` usually bypasses proxy advice. Place protection boundaries on methods genuinely invoked through beans or use another suitable enforcement mechanism.

Desired contract of the policy bean:

```java
@Component("documentPolicy")
class DocumentPolicy {
    // Repository / identity adapter / trusted context injected here.

    public boolean canRead(Authentication authentication, String documentId) {
        // 1. Verify valid and authenticated principal.
        // 2. Load the real document by documentId; obtain tenant/owner/classification
        //    from the database, not from incoming parameters.
        // 3. Obtain subject attributes and context from verified sources.
        // 4. Run READ policy; return true on PERMIT, otherwise false.
        // 5. Record audit in the appropriate layer, avoiding logging tokens/credentials.
        throw new UnsupportedOperationException("Integration contract illustration");
    }
}
```

This `DocumentPolicy` snippet **only illustrates the implementation contract** and must not be used as-is: production must replace it with real policy logic similar to `evaluate` in the standalone Java example. The `throw` indicates a missing implementation, not a valid runtime response. A clean structure separates `DocumentAttributeProvider`, `SubjectMapper`, `ContextProvider`, and `AbacPolicy` for independent testing; ensure a safe **deny** on error paths before real deployment.

**Note on SpEL parameters:** parameter name `#documentId` must be discoverable (e.g., compiled with `-parameters` or using explicit parameter-name annotations). Otherwise, index references like `#p0` can be used as supported; test method security in practice. Input parameters such as `documentId` are only used to **locate the resource**. Never take `ownerId` or `tenantId` from the client as evidence to grant access.

### 7.3. Where to Place Policies Across Multiple APIs

An independent policy can be invoked from:

- `@PreAuthorize` on a service method for single operations.
- A custom `AuthorizationManager` at a boundary needing uniform enforcement.
- Business layers shared across REST requests, batch jobs, messaging, or background workflows.

For example, `GET /documents/{id}` and `POST /documents/{id}/approve` have **different actions**, so they must not share the same `canRead` condition. Checking the HTTP path upfront cannot replace reading the actual document's owner/classification.

`@PostAuthorize` can inspect `returnObject` after the service returns; it fits some read-only use cases, yet should not be used as the primary mechanism to guard operations that **already caused side effects** (write/delete/money transfer) before deciding.

### 7.4. How WebFlux/Reactive Differs from Servlet

In WebFlux, use `SecurityWebFilterChain`, `ServerHttpSecurity`, and `@EnableReactiveMethodSecurity` when method security is needed. Protected methods typically return `Mono<T>` or `Flux<T>` to compose with the Reactor Context. The PIP loads data from reactive repositories and policy evaluation must flow through the pipeline; **never call `block()` on the event loop**.

Illustrative shape (application-specific beans/domain types must be supplied):

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}

@Service
class ReactiveDocumentService {
    private final ReactiveDocumentRepository documents;

    ReactiveDocumentService(ReactiveDocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("@reactiveDocumentPolicy.canRead(authentication, #documentId)")
    public Mono<DocumentDetails> read(String documentId) {
        return documents.findById(documentId);
    }
}
```

The `reactiveDocumentPolicy.canRead` bean may return `Mono<Boolean>` when supported by the version/method security configuration, while loading document attributes via reactive publishers and returning an **explicit true/false**. For protection checks, never let an empty `Mono.empty()` from a policy be treated casually as Permit. Check the exact contract for your Spring Security version. A more reliable pattern is keeping policy logic inside the service via reactive composition and enforcing authorization at the appropriate boundary without bypassing data checks.

**Do not mix Servlet and WebFlux APIs:** `HttpSecurity`/`@EnableMethodSecurity` belong to Servlet, whereas `ServerHttpSecurity`/`@EnableReactiveMethodSecurity` are reactive.

## 8. Data, Policies, and Operational Safety

### 8.1. Missing Attributes, Data Source Failures, and Policy Conflicts

Define clearly what happens if `ownerId` is null, tenant cannot be found, attribute store times out, or data classification is unknown. For sensitive data, the right choice is **Deny** with internal cause logging; infrastructure failures may return an appropriate technical error (usually 5xx) but **must never grant access simply because evaluation failed**.

When multiple rules exist (e.g., “finance department may read” and “documents under legal hold are forbidden”), specify **precedence** or a combining algorithm such as `deny-overrides`. Hard blocking rules (tenant mismatch, account disabled, explicit deny) must never be accidentally overridden by a broad rule like `hasRole('ADMIN')`. Any “cross-tenant super admin” exception requires an explicit policy, audit, and dedicated tests.

### 8.2. Enforcing Tenant as a Data Boundary

In multi-tenant SaaS, tenant checks should be enforced across complementary layers:

```text
Authenticated tenant
      |
      +--> Query: WHERE id = :id AND tenant_id = :tenant
      |
      +--> Policy: document.tenantId == subject.tenantId
      |
      +--> Mutation: UPDATE ... WHERE id = :id AND tenant_id = :tenant
      |
      +--> Audit: documentId, tenantId, action, decision
```

This is a logical sketch; column/table names and transactions depend on the system. Filtering directly in queries reduces the risk of leaking cross-tenant resource existence. **Never** take `tenant_id` in SQL from an unverified body/header. “Not found” and “forbidden” responses may be normalized to avoid revealing resource existence, per the application's threat model.

### 8.3. Time-of-Check/Time-of-Use (TOCTOU)

If a policy reads `ownerId` at time T1 and updates the document at T2, the owner/tenant/classification may have changed. For sensitive operations, consider checking and mutating within the same transaction/SQL condition, versioning/optimistic locking, or conditional updates. Read and decide on an explicit snapshot; never assume a one-time check holds forever.

### 8.4. Caching Attributes and Changing Permissions

Caching `roles`, `groups`, `tenant memberships`, `resource classification`, or `PERMIT` reduces overhead but introduces stale-permission risks:

- A permission was revoked, yet the cache still permits.
- A resource just changed tenant/owner.
- MFA expired or a higher assurance level is required.
- A new policy version has not propagated across all instances.

Define TTL/invalidation/versioning and scope cache keys by subject, resource, action, and context. **Never** cache by `userId` alone and reuse results across all documents and all actions. For sensitive permissions, direct evaluation and eager revocation mechanisms may be needed.

### 8.5. Logging and Explainability

Useful audit fields include: `correlationId`, pseudonymized/policy-compliant `subjectId`, `resourceId`, `action`, `policyVersion`, `decision`, `reasonCode`, server timestamp, and appropriate attribute source provenance. Avoid logging raw passwords, bearer tokens, session cookies, unnecessary PII, or raw sensitive values. Audit records help explain why the same user received different decisions in two contexts.

If a policy carries “obligations” such as masking fields or requiring event logging, the PEP must **fulfill those obligations**, not merely receive a boolean and return raw data.

## 9. Systematic ABAC Testing

Do not stop at one “admin is allowed” test. Express the matrix below as policy unit tests and API integration tests:

| Case | Change from valid baseline | Expectation |
| --- | --- | --- |
| Authorized reader | All attributes valid | PERMIT |
| Subject in different tenant | Same fake owner/department, different tenant | DENY |
| Disabled user | `active=false` | DENY |
| Archived document | `archived=true` | DENY |
| Neither owner nor same department | All other conditions valid | DENY |
| Missing MFA for confidential read | `mfaVerified=false` | DENY |
| Unmanaged device | `managedDevice=false` | DENY |
| Wrong network zone | `networkZone=PUBLIC` | DENY |
| Editor who is not owner | Subject in same department, EDIT action | DENY |
| Owner editing after hours | Server time is 22:00 Vietnam time | DENY |
| Missing tenant/classification or PIP error | Undetermined attribute | DENY; handle error internally |
| High role in another tenant | Has `ADMIN`, wrong tenant | DENY unless explicit tested exception applies |
| Tenant/owner changed between check and write | Concurrent update race condition | Must not mutate out of scope |
| Revoked permission | Stale cache still holds `PERMIT` | Revocation takes effect per system requirement |
| Undefined operation | `DELETE`/`EXPORT` when policy forbids | DENY |

**Time boundaries to test:** 07:59, 08:00, 17:59, 18:00 in the exact `ZoneId`; never use browser timezone. For multiple countries, business-hours rules must come from tenant/policy configuration and handle DST where applicable.

**Properties/invariants to uphold:** “Every Permit decision has matching tenant and active account”; “No confidential resource can be read without MFA satisfied”; “EDIT only Permits if owner”. Such invariants catch bugs more effectively than checking a few isolated `if` statements.

Two-tier testing:

1. **Policy unit tests** on pure data, without starting HTTP; cover decision tables and rule precedence.
2. **Spring Security integration tests** with real principals and resource repositories: unauthenticated requests, cross-tenant documents, non-existent resources, revoked permissions, different actions; verify both the response and that the service **does not execute forbidden operations**. Test method security proxies via calls through Spring beans, not direct calls on `new` objects.

**401 and 403:** typically unauthenticated requests reach the authentication entry point (usually 401), whereas authenticated requests lacking permission reach access denied (usually 403); the exact HTTP response depends on the security mechanism and error-handling policy. An ABAC policy returns a decision, **not automatically an HTTP status code**.

## 10. Practical Workflow When Adding a New Policy

1. **Define actions and resources**: avoid vague conditions like “has system access”.
2. **Write the policy as a decision table** including Permit/Deny, rule precedence, tenant boundaries, and mandatory conditions.
3. **Specify attribute sources** for subject/resource/context, defining trustworthiness, freshness, and failure fallbacks.
4. **Decouple the engine from transport** so policies can be tested in plain Java; Spring adapters only build context and enforce decisions.
5. **Attach enforcement to every path**: HTTP, methods, batch jobs, events, updates; leave no “shortcuts” bypassing protection logic.
6. **Test negative cases** and invariants; test race conditions/caching on sensitive operations.
7. **Govern policy lifecycle**: approvers, versioning, decision audits, rollback capability, and migrations when attribute schemas change.

An important design point: complex policies belong in a clearly named component rather than dozens of long SpEL strings scattered across controllers. In Spring Security, a dedicated policy bean/`AuthorizationManager` or decision service is easier to test and maintain.

## 11. Common Mistakes

| Mistake | Risk | Right approach |
| --- | --- | --- |
| Checking only `hasRole('EDITOR')` | Role is overly broad across all resources | Combine tenant, owner, classification, action, and context |
| Taking `tenantId`/`ownerId` from request body to grant access | Caller can self-declare attributes | Load resource attributes from database, subject from verified identity |
| Blocking only the edit button in frontend | API can still be called directly | Enforce at backend/service/data boundaries |
| Not distinguishing READ/EDIT/EXPORT | One permission misused for another action | Enumerate actions and separate rules |
| Allowing access when the policy service errors | Security bypass on timeout | Fail closed, log audit, and classify errors |
| Putting `@PreAuthorize` on methods called via `this` | Spring AOP proxy usually does not intercept self-invocation | Place boundaries on bean/proxy calls or enforce inside the service |
| Caching Permit without resource/action/context | Reusing decisions for other objects or sessions | Cache by complete policy key, with invalidation and versioning |
| Using browser clock or arbitrary headers | Actors spoof time/context | Use server clock and trusted context sources |
| Skipping transactions when deciding before update | TOCTOU: attributes may change after the check | Constraints/updates inside transaction, optimistic locking if suitable |
| Using blocking queries inside reactive policy handlers | Blocks event loop, degrades throughput | Use reactive I/O, publisher composition, never `block()` |
| Assuming Spring Security knows business ABAC automatically | Does not protect specific owners/tenants at all | Define explicit policies and attribute adapters |

## 12. Self-Check

**Question 1.** With the same `MANAGER` role, why is user A not automatically allowed to view tenant B's documents?

**Answer:** A role is one attribute; the policy must still verify `subject.tenantId == resource.tenantId`. Unless a designed and monitored cross-tenant exception exists, it must Deny.

**Question 2.** A confidential document belongs to the same tenant and department, yet the subject lacks MFA. What should ABAC return?

**Answer:** Deny if the policy requires MFA for confidential documents. All Permit conditions must hold simultaneously; points do not compensate for each other.

**Question 3.** Why should `ownerId` sent by the frontend not be used when evaluating permissions?

**Answer:** The client controls request data; the true owner must be loaded from the resource on the backend.

**Question 4.** Why does a READ policy not substitute for an EDIT policy?

**Answer:** Action is an independent input. Conditions (owner, working hours, sensitive transactions) can differ; permission to read does not imply permission to edit.

**Question 5.** When the PIP fails to fetch classification, can INTERNAL be assumed to proceed?

**Answer:** No. Defaulting to a lower sensitivity can grant unauthorized access. Reject the Permit decision, report/audit the error appropriately, and fix the data source.

**Question 6.** Is `@PreAuthorize` sufficient to protect an update operation in every case?

**Answer:** Only when real invocations go through interception, the policy evaluates true attributes, and there is no race between check and mutation; additional tenant/data constraints and transaction handling are needed per business requirements.

## 13. References

- [NIST SP 800-162 — Guide to Attribute Based Access Control (ABAC)](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): definitions of subject, object, operation, environment, and policy.
- [Spring Security — Servlet Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, and method interception.
- [Spring Security — Authorize HTTP Requests (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` and URL/request boundaries.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, and reactive authorization.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring `SecurityWebFilterChain` in WebFlux.

**Key takeaway:** ABAC decides based on **who**, **which resource**, **which action**, **in which context**. A policy provides real security only when attributes are trustworthy, the backend actually blocks unauthorized actions, and any missing or uncertain case is handled fail-closed.
