# Separating Policy Enforcement from Policy Decision

## 1. The problem: a right decision can still be enforced wrongly

In a Spring Security application, permission checks often begin with a very short condition:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public void updateDocument(Long documentId, String title) {
    // ...
}
~~~

This condition works for **functional permissions** if every document genuinely shares the same policy. However, a multi-tenant application with resource sharing must also check actor, tenant, owner, ACL, document status, and action. When these conditions are scattered across controllers, services, repositories, and background workers, three mistakes happen easily:

1. **Policy drift:** the read API uses one rule, the file download API uses another, and a background worker later skips the check.
2. **Enforcement gap:** a component computes DENY yet the data-write path still runs; or a missing decision defaults to ALLOW.
3. **Coupling:** every rule change requires editing multiple places, raising deployment risk and complicating audits.

One way to organize this is separating the **Policy Enforcement Point (PEP)** from the **Policy Decision Point (PDP)**. The PEP is where actions are **blocked or allowed to proceed**; the PDP is the component that **evaluates and returns a decision** based on trusted inputs, policy data, and the active policy.

For example: Alice is an EDITOR in tenant north, while Document #42 belongs to tenant south. The WRITE API's PEP must request a decision for the exact actor, tenant, action, and document; the PDP returns DENY; the PEP prevents the repository from writing even though the client knew the exact ID. A batch worker processing the same document must likewise go through valid enforcement rather than relying on an HTTP controller having checked in the past.

**This Knowledge lesson focuses on responsibilities, trust boundaries, and PEP–PDP coordination** in Spring Security, especially when policies change dynamically. It does not require every project to deploy an external policy server: separating responsibilities **architecturally** already brings value even when the PDP is a bean running in the same JVM.

## 2. PEP, PDP, PIP, and PAP: who does what?

| Component | Name | Responsibilities | Should NOT do |
|---|---|---|---|
| **PEP** | Policy Enforcement Point | Block actions, issue authorization queries, enforce ALLOW/DENY/ERROR, guard side effects | Infer that a PDP error means permitted |
| **PDP** | Policy Decision Point | Evaluate rules against inputs and policy data, return a result for a specific action/resource | Directly mutate business data on behalf of the PEP |
| **PIP** | Policy Information Point | Supply actor, tenant membership, owner, ACL, resource state, and environment attributes from trusted sources | Blindly trust client-sent owner/role without verification |
| **PAP** | Policy Administration Point | Manage authoring, review, versioning, distribution, and rollback of policies | Automatically push untested policies to production |
| **Audit/Decision log** | Supporting observability component | Record who asked for which permission, policy revision, and outcome for traceability | Log tokens/secrets or out-of-scope resource contents |

These are **architectural roles**, not necessarily four separate microservices. A small Spring application can use:
- PEP: Spring Method Security interceptor and service methods.
- PDP: a `DocumentPolicyDecisionService` bean.
- PIP: repositories querying membership/ACL and business data.
- PAP: version-controlled, reviewed, and deployed policy configuration.
- Audit: domain audits and security events/metrics.

As the system grows, you can move the PDP to an **OPA sidecar** or dedicated decision service while keeping the PEP interface intact. Choose topology based on latency, availability, reuse needs, and consistency risks—not because "microservices are always better".

## 3. End-to-end flow from request to action

~~~text
Client / HTTP / message / scheduler
               |
               v
   Authentication + trusted identity
               |
               v
     PEP: before sensitive action
               |
               +---- PolicyInput(subject, tenant, action, resource) ----+
               |                                                      |
               |                                          PDP: evaluate policy
               |                                                      |
               |                                          PIP: memberships,
               |                                               ACL, owner,
               |                                               state, clock
               |                                                      |
               +<----- ALLOW / DENY / ERROR + metadata ----------------+
               |
      +--------+-------------+
      |          |           |
    ALLOW       DENY        ERROR / unknown
      |          |           |
      v          v           v
  Scoped      Do not      Do not
  action      execute     execute
      |
      v
  Transaction / DTO / side effect
~~~

A **PDP returning ALLOW does not directly perform business mutations**. The PEP retains responsibility for deciding whether to invoke the repository, file storage, queue publisher, or external API. Conversely, the PDP is not the place that knows how to return HTTP 403, close a transaction, or halt a worker job across every protocol; that belongs to PEPs/adapters.

Do not put all business logic into an HTTP authorization filter: workers, CLIs, and direct service calls may not traverse HTTP. PEPs should sit at appropriate **execution boundaries**, typically combining a coarse HTTP gate and a resource-specific service gate.

## 4. Distinguishing "decision", "enforcement", and "explanation"

A well-designed PDP result might contain:

~~~json
{
  "effect": "DENY",
  "reasonCode": "RESOURCE_TENANT_MISMATCH",
  "policyVersion": "doc-policy-v17",
  "decisionId": "dec-8f01",
  "validUntil": null
}
~~~

This is an **illustrative application contract**, not a default Spring Security or OPA JSON response. Field purposes:
- `effect`: ALLOW or DENY, sometimes ERROR/INDETERMINATE per the chosen contract.
- `reasonCode`: supports auditing/testing; not necessarily safe to return verbatim to clients.
- `policyVersion`: identifies which rules produced the decision.
- `decisionId`: correlation ID for log lookup, not proof of permission.
- `validUntil`: window during which caching/reuse is allowed if business rules permit; null does not mean "forever".

Some systems include **obligations/advice**, such as "must mask salary column" or "must audit before download". If the PDP returns ALLOW with an obligation that the PEP cannot fulfill, the PEP **must not ignore the obligation and grant full access**.

Do not conflate statuses:
- **DENY:** policy evaluated and refused.
- **NOT_APPLICABLE/ABSTAIN:** policy did not issue a decision on that branch.
- **ERROR/INDETERMINATE:** could not evaluate due to missing input, timeout, or error.
- **ALLOW:** sufficient evidence exists under policy.

The PEP needs clear **combination/fail-closed rules**. When using Spring's `AuthorizationManager`, returning `null` can represent abstain; **never treat null as ALLOW** in an adapter where the domain requires a mandatory decision.

## 5. PEP invariant: without a verified ALLOW, no side effects

A safe PEP for private actions obeys:

~~~text
ALLOW -> may proceed, while still maintaining other guards.
DENY  -> do not invoke mutation / do not return out-of-scope data.
ERROR -> do not invoke mutation; return a controlled error.
NULL  -> do not invoke mutation; treat as insufficient proof.
TIMEOUT -> do not invoke mutation; record telemetry / circuit handling.
UNKNOWN EFFECT -> do not invoke mutation; contract violation.
~~~

Many major bugs happen when developers write:

~~~java
boolean allowed = true;
try {
    allowed = policyClient.isAllowed(...);
} catch (Exception ex) {
    log.warn("Policy service unavailable", ex);
}
if (allowed) {
    repository.deleteById(id);
}
~~~

This is a **fail-open anti-pattern**: initializing to `true` causes the action to run when the PDP fails. For sensitive data, technical exceptions should be distinguished from policy DENYs, yet **neither may lead to executing the action**.

One subtle detail: after receiving ALLOW, the PEP must still ensure the business transaction targets the exact resource, tenant scope, and action queried. Do not ask the PDP about Document #42 and use the result to update Document #57. Decisions must be **bound to the exact subject, action, resource, tenant, and validity window**.

## 6. What inputs should the PDP receive?

Modeled along permission dimensions:

| Input group | Example | Why needed? |
|---|---|---|
| Subject | issuer+sub, internal principal ID, workload identity | Avoid user/issuer confusion, prevent spoofing |
| Tenant | requested tenant with verified membership | Prevent tenant A roles from applying to tenant B |
| Action | DOCUMENT_READ / WRITE / DELETE / SHARE | Read permission does not imply delete permission |
| Resource | type, stable ID, tenant, owner, project, classification, state/version | Decide on the right object and data conditions |
| Context | server time, policy revision, delegation, device posture if needed | Dynamic policies depend on context |
| Request metadata | requestId/correlationId, source service | Tracing/audit; never turn correlation ID into permission |

Example input:

~~~json
{
  "subject": {
    "issuer": "https://idp.example",
    "id": "alice",
    "tenantRoles": ["DOCUMENT_EDITOR"]
  },
  "tenant": "north",
  "action": "DOCUMENT_WRITE",
  "resource": {
    "type": "Document",
    "id": "42",
    "tenant": "north",
    "ownerId": "bob",
    "locked": false
  },
  "environment": {
    "requestId": "req-120",
    "policyRevision": "v17"
  }
}
~~~

This is an **illustrative payload between PEP and PDP**, and must not be accepted wholesale from the client. Actor identity must come from verified authentication; tenant roles from a trusted source; resource tenant/owner/locked from the repository/trusted PIP. A client may send the resource ID and target tenant, but must never pick `ownerId` or `tenantRoles` to obtain ALLOW.

Do not send oversized domain objects or unnecessary secrets to the PDP. Apply **data minimization**: send just enough attributes to decide, under a clear schema version. If the PDP needs highly sensitive data, consider placing a PIP close to the data or querying membership via a trusted reference.

## 7. Who prepares the input: PEP, PIP, or PDP?

There are two primary models:

**Push attributes:** the PEP/service fetches actor, tenant, and resource attributes from the DB/trusted PIP and sends a complete input to the PDP.

Pros: pure PDP is easy to test and needs no access to multiple databases. Cons: the PEP must fetch the right data, which can go stale; multiple PEPs risk building inconsistent inputs.

**Pull attributes:** the PEP sends identity/resource references, and the PDP or PIP queries the necessary DB/ACL/membership data.

Pros: policy logic and data retrieval are more consistent, PEP stays simple. Cons: PDP gains extra dependencies, latency, DB access permissions, and outage modes.

**Hybrid:** the PEP sends verified fields, while the PDP queries dynamic attributes in a dedicated PIP. Many production systems use hybrid, but freshness, caching, and authorization for the PIP must be defined.

Invariant: **data sources must carry trust/provenance**. A `tenantId` copied from a request and a `tenantId` fetched from the database share the Java type `String` but have different trust levels. Do not use a name like `VerifiedTenant` as a substitute for actual verification.

## 8. Pure PDP decides; PEP does not rewrite policy

A simple domain interface free of Spring dependencies:

~~~java
public interface PolicyDecisionPoint {
    PolicyDecision decide(PolicyInput input);
}
~~~

This is an **architectural integration snippet**, with `PolicyDecision`/`PolicyInput` types defined by the application. An implementation can:
- Run an in-process Java policy.
- Use versioned configured rules.
- Call an OPA sidecar or remote PDP.
- Query a protected ACL/relationship service.
- Combine multiple policies according to documented and tested precedence.

A PEP/adapter uses it:

~~~java
PolicyDecision decision = pdp.decide(input);

if (decision == null || decision.effect() != Effect.ALLOW) {
    throw new AccessDeniedException("No usable authorization grant");
}

return documentRepository.findScopedForRead(
        input.resourceId(), input.verifiedTenant());
~~~

**Illustrative** code, not standalone: requires classes, repository, and imports. Crucially, the PDP returns a decision, the PEP verifies exact `ALLOW`, and runs a scoped query next. When the PDP fails, the PEP may distinguish 5xx from 403, yet must never return sensitive data.

Avoid "PEP trusts role names alone" while the PDP checks another owner: when policies are distributed, a **unified contract** for input/action/decision is required. Some role checks may sit in the HTTP PEP as a preliminary shield, yet the resource PDP must still receive full scope.

## 9. Integrating with Spring Security: AuthorizationManager as the bridge

Spring Security uses `AuthorizationManager<T>` to evaluate permissions for HTTP requests, method invocations, and corresponding secured objects. Components like `AuthorizationFilter` and method security interceptors can act as **PEPs**, while `AuthorizationManager` acts as the **decision adapter** to the application's PDP.

Key distinctions:
- `AuthorizationManager` is Spring Security's **decision/coordination API**, not automatically a remote PDP.
- `AuthorizationFilter` is enforcement in the HTTP chain; method interceptors enforce before/after methods.
- The same application PDP can be invoked via an `AuthorizationManager<RequestAuthorizationContext>` adapter, a method security adapter, a policy bean, or a service boundary.
- Not every security check must use `AuthorizationManager` if domain services have proper policy gates; when integrating, follow the contract of the Spring Security version in use.

Current Spring Security docs use `authorize(Supplier<Authentication>, T)` returning `AuthorizationResult` (nullable for abstain). Older versions/docs mention `check(...)` returning `AuthorizationDecision`. When writing a concrete adapter, verify against **the project's API version** rather than copying a signature from an old blog post and guessing.

Architecturally, isolating the policy engine behind a domain interface lets you upgrade Spring Security versions without rewriting every business rule.

## 10. HTTP PEP: coarse-grained protection first

Example Spring Servlet configuration:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/documents/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
~~~

This is a **Spring integration snippet**; real imports, dependencies, CSRF/session, and filter setup are required. It protects the HTTP entrypoint with authentication, yet does **not** prove which tenant Document 42 belongs to or whether the user may WRITE.

You can use `.access(customAuthorizationManager)` to invoke a custom PDP for a route, but weigh:
- Does the HTTP request carry enough resource metadata to decide? With only a path ID, the manager must query the DB.
- Will the predicate run twice—once in the filter and once in the service—adding unnecessary latency?
- Can non-HTTP entrypoints bypass it?
- Does the policy have side effects or sensitive request logging? The PDP should never mutate state on its own.
- Is there an explicit `anyRequest().denyAll()` fallback for undeclared routes?

A common design is **HTTP PEP checks authentication and coarse authorities**, **service PEP checks resource permissions via the PDP**, and the repository adds tenant/resource predicates. Defense in depth beats cramming all object ACLs into a filter lacking domain context.

## 11. Method PEP: @PreAuthorize calling a policy bean

In Spring Security Method Security, you can invoke a bean via SpEL:

~~~java
@PreAuthorize(
    "isAuthenticated() and " +
    "@documentAccess.canRead(authentication, #tenantId, #documentId)"
)
@Transactional(readOnly = true)
public DocumentView read(String tenantId, Long documentId) {
    return documentService.loadScopedDocument(tenantId, documentId);
}
~~~

This is an **integration snippet**. The `documentAccess` bean should be an adapter that:
1. Extracts the trusted subject from Authentication.
2. Verifies target tenant and membership.
3. Fetches the resource from the DB with a tenant guard.
4. Builds a canonical `PolicyInput` and calls the PDP.
5. Returns true only when the PDP decides ALLOW.
6. Never turns exceptions/null/timeouts into true.

Notes:
- Enable `@EnableMethodSecurity`.
- Annotations run on calls passing through the **Spring proxy** in proxy mode; `this.read(...)` self-calls within the bean can bypass the interceptor.
- SpEL parameter names must be discoverable via `-parameters`, `@P`, or equivalent support.
- `@PreAuthorize` runs before the method; it **does not guarantee** transactions/ACLs cannot change before mutation commit.
- `loadScopedDocument` must query with tenant/owner/ACL scope, never using the precheck result to load a different object.

A shared PDP is valuable, yet the service PEP must still maintain trusted data boundaries.

## 12. Example @Component adapter without turning the PDP into a controller

Suppose the application has `VerifiedActorResolver`, `DocumentMetadataRepository`, and `PolicyDecisionPoint`:

~~~java
@Component("documentAccess")
public class DocumentAccessGate {
    private final VerifiedActorResolver actors;
    private final DocumentMetadataRepository documents;
    private final PolicyDecisionPoint policy;

    public DocumentAccessGate(VerifiedActorResolver actors,
            DocumentMetadataRepository documents,
            PolicyDecisionPoint policy) {
        this.actors = actors;
        this.documents = documents;
        this.policy = policy;
    }

    public boolean canRead(Authentication authentication,
            String tenantId, Long documentId) {

        VerifiedActor actor =
                actors.requireMember(authentication, tenantId);

        if (documentId == null || documentId <= 0) {
            return false;
        }

        DocumentMetadata doc = documents
                .findByIdAndTenantId(documentId, actor.tenantId())
                .orElse(null);

        if (doc == null) {
            return false;
        }

        PolicyInput input = PolicyInput.forRead(actor, doc);
        PolicyDecision decision = policy.decide(input);
        return decision != null && decision.effect() == Effect.ALLOW;
    }
}
~~~

This is an **integration class pattern**; imports and project domain components are omitted, so it is not a standalone Java file. `requireMember` must genuinely verify membership and subject namespacing; `DocumentMetadata` loads resource tenant/owner/status from the DB; `PolicyInput.forRead` must build input from trusted sources.

This separates responsibilities:
- `DocumentAccessGate` is a **PDP adapter**, not a holder of all rules.
- `PolicyDecisionPoint` returns decisions according to policy.
- Spring method interceptors block the method when the condition evaluates to false.
- Repository/service then performs the scoped read.

In production, **define exception handling**. If `policy.decide` throws a technical error, do not continue the action; Spring MVC/exception mappers can return 5xx and telemetry instead of collapsing every outage into 403. A boolean adapter can return false for DENY while letting ERROR throw a distinct exception to preserve operational signals. Regardless of HTTP status mapping, data must never be returned without ALLOW.

## 13. WRITE PEPs must sit close to the mutation

A PDP call returning ALLOW is not permanent write permission. If the actor is allowed at T1 but owner/ACL changes at T2, a service writing at T3 could act on a stale decision.

~~~text
T1: PDP -> ALLOW WRITE document 42
T2: admin revokes WRITE / transfers owner / locks document
T3: repository.updateTitleById(42, "New title")
~~~

Updating by ID alone can write without authorization. For owner-only WRITE, use a **conditional update** binding current conditions:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_user_id = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Verify affected rows = 1; never treat 0 as success. `tenant`/`subject` predicates must come from trusted context, not the client body. If WRITE is granted via a share/ACL in another table, use an appropriate query/transaction/lock/version protocol; a `@Version` on Document **does not automatically** detect grant revocation in another DB.

A service PEP can:
- Use the PDP to evaluate complex rules.
- Execute writes in a transaction with guards ensuring actor/resource/action remain valid under policy.
- Commit and publish side effects only when all guards pass.
- Use outbox/idempotency if post-commit events exist.

**Never claim "we separated the PDP so TOCTOU is gone."** Separating responsibilities improves maintainability yet also introduces time/network boundaries. Concurrency must be addressed explicitly.

## 14. Dynamic policies: changing rules without editing every PEP

The strength of PEP–PDP architecture is an **independent policy lifecycle** separate from enforcement code. Examples:
- Add a condition blocking WRITE on `LEGAL_HOLD` documents.
- Restrict SHARE for tenant admins to business hours.
- Grant READ to a review group with dynamic membership.
- Require classification/clearance before export.
- Change geographic/entitlement rules per contract.

PAP manages policy versions:
1. Propose/edit policies via Git or an access-controlled admin table.
2. Require review by security owners and domain owners.
3. Static validation/type checking, unit tests, and permission matrices.
4. Deploy to a versioned/rollback-capable PDP and observe discrepancies.
5. Distribute/invalidate caches by policy revision.
6. Audit who approved, what changed, and when it took effect.
7. Roll back safely if a new policy has bugs; never fall back to `permitAll`.

The PDP should return/log the policy revision for traceability. A PEP can keep a stable interface across policy changes, yet input schemas, action names, and obligation semantics must also be versioned if they change.

Never let teams toggle policies via a UI lacking authorization checks, approvals, or auditing; a policy change can be equivalent to granting production privileges.

## 15. Local PDP, sidecar, or remote PDP?

| Model | Execution | Pros | Risks/costs |
|---|---|---|---|
| **In-process** | Java library/bean inside app | Low latency, easy transaction/context access, few network dependencies | Policy distribution must sync across instances |
| **Sidecar** | Policy engine beside service/pod | Close to PEP, reduced network hops, independent policy updates | Per-pod lifecycle/bundle/cache and memory |
| **Remote PDP** | Centralized service via HTTP/gRPC | Shared rules, centralized audit/administration | Network latency, availability, failure domains, thundering herd |
| **Hybrid** | Local PDP for simple rules, remote for complex decisions | Balances latency and policy richness | Needs clear contracts so two places never yield conflicting outcomes |

**Separating logic does not require adding a network call.** For small systems, a policy bean shared by multiple service PEPs is a solid starting point. When multiple services share policies, sidecars/remote PDPs can be considered after measuring p95/p99 and PDP outage impact.

Never design a "single point of authorization failure" without timeouts, bounded retries, circuit breakers, and safe fallbacks. A **safe** fallback can be deny/503 or a valid cached decision per contract; never permit all requests to preserve uptime.

## 16. OPA is an example of a PDP, not a Spring Security default

Open Policy Agent (OPA) is a policy engine supporting separation of policy decisions from enforcement. The application (PEP) sends structured input to OPA, OPA evaluates rules/data, and returns a result. OPA can run in-process via supported integrations, as a sidecar, or as a server; exact architecture follows the product design.

Example request to the OPA Data API:

~~~http
POST /v1/data/app/documents/allow HTTP/1.1
Content-Type: application/json

{
  "input": {
    "subject": "alice",
    "tenant": "north",
    "action": "DOCUMENT_READ",
    "resource": {
      "id": "42",
      "tenant": "north",
      "owner": "bob"
    }
  }
}
~~~

Response **if** the policy at that path is defined and evaluates to true:

~~~json
{
  "result": true
}
~~~

This illustrates the **OPA Data API contract**, not a claim that every OPA endpoint always returns a boolean. If a path/rule is undefined or no decision is produced, the Data API may return HTTP 200 **without a `result` property**. The PEP **must not treat HTTP 200 as ALLOW**. It must verify the `result` type and policy semantics; undefined/missing/wrong type → deny execution.

Example Rego rule for that decision path:

~~~rego
package app.documents

default allow := false

allow if {
    input.action == "DOCUMENT_READ"
    input.tenant == input.resource.tenant
    input.subject == input.resource.owner
}
~~~

This is a **minimal illustrative Rego rule**, not a replacement for production policies (lacks authentication proof, membership, sharing, classification). `input.subject` and `input.resource.owner` must be prepared by a trusted PEP/PIP, not copied from the client body. Check syntax/semantics against your OPA version and test negative cases.

References: [Open Policy Agent documentation](https://www.openpolicyagent.org/docs) and [OPA REST API](https://www.openpolicyagent.org/docs/rest-api).

## 17. Never let the PDP trust raw client data

A trust-boundary failure:

~~~text
Client sends:
  subject = "admin"
  tenant = "finance"
  role = "SUPER_ADMIN"
  resource.owner = "admin"

PEP forwards unchanged to PDP
PDP sees role and owner -> ALLOW
~~~

The PDP can evaluate rules **correctly on false data**. Separating PDP/PEP does not verify inputs automatically; if the PEP fails to canonicalize the actor or the PIP fails to verify the owner, an ALLOW result cannot be trusted.

Safe design:
- Authentication verifies the caller; subject key is issuer + sub or an internal principal from a trusted source.
- Target tenant has verified membership; roles are scoped to that tenant.
- Resource ID from URL is only a target; owner/tenant/classification/status must come from the DB.
- Action is mapped from server-side use cases; clients cannot pick a weak action for a strong mutation.
- Context such as time uses the server clock; device posture/gateway claims need explicit trust.
- PDP requests should be service-authenticated via mTLS/service identity and protected against replay/tampering over the network.
- Domain object ID and tenant must remain consistent between decision and use.

If the architecture lets the PDP call a PIP directly, protect the PIP against querying tenants outside the decision request's scope. A PIP should not dump an organization's entire ACL solely because the PDP asked, without technical bounds and auditing.

## 18. Resource permissions are more than roles

Roles/authorities are typically a **coarse gate**. Documents/folders/projects need owner, ACL, or relationship checks:

~~~text
ALLOW_READ =
    isAuthenticated
    AND belongsToRequestedTenant
    AND tenantRoleAllowsRead
    AND document.tenant == requestedTenant
    AND (
        subjectIsOwner
        OR activeShareReadGrant
        OR activeProjectReadMembership
    )
    AND document.isReadable
~~~

Never put the tenant check inside an OR branch such that an admin/ACL branch can cross tenants unintentionally.

With Spring ACL, `AclPermissionEvaluator` can provide per-object permission evaluation; it can serve as the PDP/PIP component while Spring method security or services act as the PEP. If policies combine many dynamic attributes (time, classification, relationships), broader PDP business rules may be needed.

Never infer that WRITE implies SHARE or DELETE. The PDP needs the exact action input, and the PEP must apply the decision only to that exact action.

## 19. Decision caching: right keys, expiration, and revocation

A reference key:

~~~text
(
  issuer,
  subjectId,
  tenantId,
  resourceType,
  resourceId,
  action,
  resourceVersion,
  policyVersion,
  aclRevision
)
~~~

This is an illustrative model. Not every rule needs every field, yet caches **must never mix actors, tenants, resources, or actions**. If a decision depends on environment time/device, keys/TTLs must reflect that too.

Questions to answer:
- What is the maximum TTL for ALLOW?
- When an ACL grant is revoked, do PEP/PDP caches receive invalidation events?
- When group membership changes, is an authz revision or cache epoch incremented?
- When a policy deploys from v17 to v18, where are old caches invalidated?
- How stale can each instance cache get when event propagation lags?
- Are short-lived DENYs cached to reduce load, and could that keep blocking a newly granted user?
- When the cache backend fails, is there a safe fallback for critical data?

**A cached ALLOW is a decision from the past.** For mutations or highly sensitive data, consider re-checking/guarding at execution time. Never promise instant revocation while tokens/decision caches stay valid for 30 minutes without a revocation mechanism.

## 20. PDP timeouts, circuit breakers, and distinguishing errors

A networked PDP can fail in multiple ways:
- Connect timeout, read timeout, DNS/TLS failure.
- HTTP 5xx or malformed response.
- Input missing fields or trust.
- Missing/undefined policy.
- Version mismatch between PEP client and PDP.
- Rate limiting/overload.
- Valid DENY returned by PDP.

**Policy DENY differs from infrastructure ERROR.** Neither executes the action, yet operations must distinguish them:
- DENY → typically 403 or 404 depending on leak policy.
- ERROR/timeout → typically 5xx/503 and alerts, never success.
- Unauthenticated → 401/challenge or redirect per auth stack.
- Missing resource within allowed scope → 404.

Timeouts must be **bounded** so requests/transactions do not hang; retries should be bounded with jitter rather than infinite loops. Circuit breakers should fail closed when the PDP is unavailable. Never enable a `permitAll` fallback when a circuit opens.

If a valid cached entry returns a decision and the business accepts cached ALLOWs during a PDP outage, strict rules for TTL, security criticality, revocation guarantees, and cache key protection are mandatory. For sensitive actions, deny/503 is usually safer than a "stale allow".

## 21. Obligations/advice: the PEP must fulfill all of them, not just check the effect

Some PDPs can return:

~~~json
{
  "effect": "ALLOW",
  "obligations": [
    {"type": "REDACT_FIELDS", "fields": ["salary", "personalId"]},
    {"type": "AUDIT_READ", "required": true}
  ]
}
~~~

This contract is **application-designed**, not a standard Spring `AuthorizationManager` response. If the PDP permits READ only when two sensitive fields are masked, a PEP returning the full DTO is an enforcement failure.

Safe approach:
1. PEP validates obligation types/schema/version.
2. ALLOW only after all mandatory obligations the PEP can enforce have been applied.
3. Projections/DTO mappers or queries must strip unauthorized fields **before serialization**.
4. Mandatory audits must be guaranteed per contract (e.g., transaction/outbox) before completing the action.
5. Unrecognized obligation → DENY/ERROR, never ignore.

The PDP should not send raw sensitive values like salary or personal IDs inside decisions; the PEP uses field lists or policy labels to build safe projections.

## 22. Logs/audits: PDP decides, PEP confirms execution

Decision logs and enforcement logs answer two different questions:

| Log | Question | Useful fields |
|---|---|---|
| PDP decision | Why did the policy decide this? | decisionId, actor, tenant, action, resource, policyVersion, effect, reasonCode |
| PEP enforcement | Was the request blocked or executed? | decisionId, endpoint/method, result, correlationId, latency, transaction outcome |
| Policy administration | Which rules changed? | editor actor, reviewer, revision, deploy time, rollback |
| PIP data provenance | Where did permission attributes come from? | membershipVersion, aclRevision, resourceVersion |

Do not log only PDP "ALLOW" and assume the mutation succeeded: the repository might fail, the transaction might roll back, or the PEP might block due to an obligation. Conversely, a PEP logging "EXECUTED" without a trusted decisionId/actor/resource is hard to investigate.

**Protect log data:** never log raw JWTs, session cookies, secret URLs, raw policy credentials, or out-of-scope document content. A correlation ID is not proof of permission.

Track PDP p50/p95/p99 latency, timeout/denial rates, cache hit rates, policy version drift, and decision-vs-enforcement mismatches. A DENY spike after a new policy rollout could be intended policy or a bug; observe across dimensions without exposing PII.

## 23. Scaling to many PEPs without creating many "allow" bypasses

When you have HTTP controllers, GraphQL, WebSockets, schedulers, message listeners, and file downloads, map every **point that can cause side effects or expose data**:

- Detail READ APIs and list/search/export.
- WRITE/DELETE services, bulk operations.
- File downloads/presigned URLs.
- Queue consumers running hours later.
- Scheduled jobs/service-to-service calls.
- Admin consoles, support tools, data migration scripts.

All of these need appropriate enforcement boundaries. They do not all have to make identical remote PDP calls, but policy semantics and trusted inputs must stay consistent.

Examples:
- HTTP PEP authenticates users and blocks coarse roles.
- Document service PEP checks tenant/resource actions with the PDP.
- Repository applies query scope `id AND tenant AND permittedObject`.
- Export workers have a workload/actor delegation contract and re-check at export time.
- Signed object-storage links get TTLs matching risk; once issued, a link's access may persist until expiry if storage lacks revocation.

**A centralized PDP cannot fix places where you forgot to place a PEP.** The most critical job is inventorying all entrypoints and side effects, ensuring every data access path goes through tested enforcement.

## 24. Standalone Java 17: PDP decides, PEP blocks and counts side effects

The following example **compiles and runs on JDK 17** without Spring. It models a simple local policy and enforcement that skips operations when the decision is DENY, the PDP returns null, or the PDP throws an error.

Create `PepPdpDemo.java`:

~~~java
import java.util.Set;

public class PepPdpDemo {

    enum Action { READ, WRITE }
    enum Effect { ALLOW, DENY, ERROR }

    record Actor(String userId, String tenant, Set<String> roles) { }
    record Resource(long id, String tenant, String ownerId,
                    boolean locked) { }
    record Grant(String tenant, long resourceId,
                 String userId, Action action) { }
    record Input(Actor actor, Resource resource, Action action) { }
    record Decision(Effect effect, String reason) { }

    @FunctionalInterface
    interface DecisionPoint {
        Decision decide(Input input);
    }

    static final class LocalPdp implements DecisionPoint {
        private final Set<Grant> grants;

        LocalPdp(Set<Grant> grants) {
            this.grants = grants;
        }

        @Override
        public Decision decide(Input input) {
            if (input == null || input.actor() == null
                    || input.resource() == null || input.action() == null) {
                return new Decision(Effect.DENY, "MISSING_INPUT");
            }

            Actor actor = input.actor();
            Resource resource = input.resource();
            Action action = input.action();

            if (actor.userId() == null || actor.tenant() == null
                    || actor.roles() == null
                    || resource.id() <= 0 || resource.tenant() == null
                    || !actor.tenant().equals(resource.tenant())) {
                return new Decision(Effect.DENY, "INVALID_SCOPE");
            }

            boolean roleAllows = actor.roles().contains("TENANT_ADMIN")
                    || (action == Action.READ
                        && actor.roles().contains("READER"))
                    || (actor.roles().contains("EDITOR"));
            if (!roleAllows) {
                return new Decision(Effect.DENY, "ROLE");
            }

            if (resource.locked() && action == Action.WRITE) {
                return new Decision(Effect.DENY, "LOCKED");
            }

            boolean owner = actor.userId().equals(resource.ownerId());
            boolean tenantAdmin = actor.roles().contains("TENANT_ADMIN");
            boolean shared = grants.contains(new Grant(
                    resource.tenant(), resource.id(),
                    actor.userId(), action));

            if (owner || tenantAdmin || shared) {
                return new Decision(Effect.ALLOW, "GRANTED");
            }
            return new Decision(Effect.DENY, "OBJECT");
        }
    }

    static final class EnforcementPoint {
        private final DecisionPoint pdp;
        private int executed;

        EnforcementPoint(DecisionPoint pdp) {
            this.pdp = pdp;
        }

        String attempt(Input input) {
            Decision decision;
            try {
                decision = pdp.decide(input);
            } catch (RuntimeException failure) {
                return "BLOCKED_ERROR";
            }

            if (decision == null || decision.effect() == null
                    || decision.effect() == Effect.ERROR) {
                return "BLOCKED_ERROR";
            }
            if (decision.effect() != Effect.ALLOW) {
                return "BLOCKED_DENY";
            }

            // Only the ALLOW branch executes the illustrative side effect.
            executed++;
            return "EXECUTED";
        }

        int executed() {
            return executed;
        }
    }

    public static void main(String[] args) {
        Actor an = new Actor("an", "north", Set.of("EDITOR"));
        Actor binh = new Actor("binh", "north", Set.of("READER"));
        Actor southAdmin = new Actor(
                "admin", "south", Set.of("TENANT_ADMIN"));

        Resource document = new Resource(42, "north", "an", false);
        Resource locked = new Resource(43, "north", "an", true);
        Set<Grant> grants =
                Set.of(new Grant("north", 42, "binh", Action.READ));

        EnforcementPoint pep = new EnforcementPoint(new LocalPdp(grants));

        System.out.println("owner-write=" + pep.attempt(
                new Input(an, document, Action.WRITE)));
        System.out.println("shared-read=" + pep.attempt(
                new Input(binh, document, Action.READ)));
        System.out.println("shared-write=" + pep.attempt(
                new Input(binh, document, Action.WRITE)));
        System.out.println("other-tenant-admin=" + pep.attempt(
                new Input(southAdmin, document, Action.READ)));
        System.out.println("locked-owner-write=" + pep.attempt(
                new Input(an, locked, Action.WRITE)));

        EnforcementPoint missing = new EnforcementPoint(input -> null);
        System.out.println("no-decision=" + missing.attempt(
                new Input(an, document, Action.READ)));

        EnforcementPoint broken = new EnforcementPoint(input -> {
            throw new IllegalStateException("PDP unavailable");
        });
        System.out.println("pdp-failure=" + broken.attempt(
                new Input(an, document, Action.READ)));

        System.out.println("executed-count=" + pep.executed());
    }
}
~~~

Compile/run:

~~~bash
javac PepPdpDemo.java
java PepPdpDemo
~~~

Exact stdout:

~~~text
owner-write=EXECUTED
shared-read=EXECUTED
shared-write=BLOCKED_DENY
other-tenant-admin=BLOCKED_DENY
locked-owner-write=BLOCKED_DENY
no-decision=BLOCKED_ERROR
pdp-failure=BLOCKED_ERROR
executed-count=2
~~~

Reading the output:
1. An is owner and EDITOR in tenant north, so WRITE is allowed.
2. Binh is only READER yet has a READ share on that exact document, so READ is allowed.
3. A READ grant does not turn into WRITE.
4. Tenant south's admin cannot cross into tenant north.
5. A locked document blocks WRITE even for the owner.
6. When the PDP returns no decision or throws an error, no side effects run.
7. The PEP increments `executed` only twice when receiving ALLOW.

**Limitations:** actors/roles/grants in the demo are hardcoded directly in code, with no JWT validation, database, transactions, caching, or concurrency. A real PEP must obtain identity and resource attributes from trusted sources, guard real DB/file/queue operations, handle exceptions, and ensure an expired ALLOW is never reused. Counting `executed` is solely an illustrative side effect.

## 25. Unit testing the PDP and integration testing the PEP are two different tasks

**PDP unit tests** verify rules against static inputs:
- Owner READ/WRITE when tenant role matches.
- Non-owner without grant → DENY.
- READ grant does not allow WRITE.
- Tenant mismatch → DENY, even for another tenant's admin.
- Resource LOCKED → WRITE DENY.
- Membership/ACL revoked or expired → DENY.
- Different subject issuer with same `sub` → permissions must not collide.
- Policy revisions A/B yield results per published rules.
- Missing inputs and invalid attributes → DENY/ERROR with clear contract.

**PEP integration tests** prove decisions are actually enforced:
- When an HTTP route or method invocation is DENY, controller/service body does not run.
- PDP timeout/exception causes zero side effects.
- PDP returning null/undefined/malformed response grants no access.
- PEP does not call `repository.update`/`delete` on DENY.
- On ALLOW, PEP operates on **the exact resource/action** verified; no ID swap.
- Out-of-scope resources are neither logged nor serialized on denial.
- `@PreAuthorize` executes through a real Spring bean proxy, not just `new` instances.
- Non-HTTP entrypoints still enforce policies.
- Mandatory obligations are executed before returning the response.
- List/count/export queries enforce proper tenant/ACL filtering.
- Transaction rollbacks or version conflicts never report false success.

In Spring, use Spring Security Test/MockMvc, method-security integration tests, and real databases via Testcontainers when concurrency/SQL matters. Default `@WithMockUser` does not provide custom JWT issuer/tenant claims; apps using custom principals must construct matching fixtures.

## 26. Contract tests between PEP and PDP

With a remote PDP, **contract tests** are needed for both serialization and policy semantics:

| Input/response | PEP expectation |
|---|---|
| `{"effect":"ALLOW"}` valid schema | Proceed subject to guards/obligations |
| `{"effect":"DENY"}` | Block action |
| HTTP 200 response missing effect/result | Block; report contract error |
| `effect="MAYBE"` | Block, do not fall back to allow |
| PDP timeout/connect failure | Block; emit telemetry |
| PDP HTTP 500 | Block, report technical error |
| Actor/resource/tenant mismatch | Reject ALLOW even if backend is misconfigured |
| Policy requires field masking | PEP enforces masking or blocks |
| Decision past TTL | Do not use to grant |
| Incompatible policy/PIP version | Block until safely resolved |
| Response for another tenant | Do not apply to this request |
| Matching decisionId but different resource | Do not reuse |
| PDP returns ALLOW for READ, request is DELETE | Must not apply |
| Cached ALLOW revoked | Do not use past revocation SLA |

Under load testing, measure PDP QPS, cache hit rates, tail latency, circuit breaker transitions, and retries. Also test prolonged PDP outages: does the system halt sensitive writes properly? Do queues back up? Are there any hidden fallbacks enabling `permitAll` on network errors?

## 27. Migrating from scattered policies to PEP–PDP

A risk-reducing roadmap:

1. **Inventory sensitive actions:** READ/WRITE/DELETE/SHARE, downloads/exports, async jobs, and admin actions.
2. **Build the current decision matrix:** who may do what on which objects, including tenant/ACL exceptions.
3. **Extract the PolicyInput/PolicyDecision contract:** actor, tenant, action, resource, effect, reason, revision, obligations.
4. **Place PEPs at service boundaries:** not just HTTP routes; standardize calling the PDP and enforcing outcomes.
5. **Move rules into a local PDP first:** verify output matches accepted behavior and fix gaps intentionally.
6. **Separate trusted/untrusted data:** verified resolvers and PIPs.
7. **Shadow evaluation if needed:** call the new PDP to log comparisons while still enforcing via the legacy path during testing; shadow only observes, never grants.
8. **Canary policy/PDP:** ramp traffic gradually, measuring mismatches, latency, errors, and deny rates.
9. **Switch primary enforcement:** one clear decision source; avoid dual paths falling back to each other and creating permits.
10. **Enable audit/cache/revisions:** policy rollback, invalidation, and runbooks for PDP outages.
11. **Test TOCTOU and side effects:** every ALLOW uses the exact resource/action, with mutations guarded at the right time.
12. **Remove duplicated scattered policies:** retain necessary defense in depth while avoiding diverging rules that conflict accidentally.

Moving a PDP to a remote service is not merely changing an endpoint URL. It adds trust boundaries, network failures, and a consistency model requiring re-threat-modeling—not an HTTP client lacking timeouts or authentication.

## 28. Common mistakes

**1. "The PDP returned ALLOW so it can write to the DB directly."** The PDP does not replace the PEP. **Fix:** the PEP gates side effects and verifies obligations.

**2. "There is already a PEP on the HTTP controller so workers don't need one."** Message listeners/schedulers have different entrypoints. **Fix:** enforce at service or worker boundaries.

**3. "HTTP 200 from the PDP means ALLOW."** An API can return 200 with an undefined result. **Fix:** validate schema and explicit effect.

**4. "When the PDP times out, let requests through so uptime isn't hurt."** That is fail-open. **Fix:** deny/503 or valid cached decisions per risk contract.

**5. "The PDP always receives the true role/owner."** Clients can spoof those fields if the PEP copies them raw. **Fix:** authentication + trusted PIP.

**6. "The editor role is enough to edit any document."** Missing tenant/owner/ACL checks. **Fix:** full action and resource scope inputs.

**7. "Separating the PDP eliminates TOCTOU."** Permissions can be revoked after the check. **Fix:** guarded operations/versioning/locking.

**8. "One cached ALLOW covers every action on the object."** READ is not WRITE/DELETE. **Fix:** cache keys include action and resource revision.

**9. "Policy changes don't need versions."** Impossible to trace bugs, roll back, or canary. **Fix:** PAP, policy revisions, and audits.

**10. "The PEP can skip unsupported obligations."** The PDP may grant access strictly conditional on masking/auditing. **Fix:** mandatory obligations must be enforced or denied.

**11. "No need to test the PEP because PDP unit tests pass."** PDP logic can be right while middleware is bypassed. **Fix:** integration tests for side effects and entrypoints.

**12. "Every policy must become a microservice."** Unnecessary network hops and failure domains. **Fix:** separate interfaces/responsibilities first, choose topology by need.

**13. "Putting Spring `@PreAuthorize` on a bean protects all calls."** Self-invocation can bypass the proxy. **Fix:** proper service boundaries and tests via Spring-managed beans.

**14. "We can reuse one ALLOW for Document #42 and #43."** Wrong decision binding. **Fix:** bind subject/tenant/action/resource and TTL to results.

## 29. PEP–PDP system design checklist

- [ ] Side effects and points where PEPs must block have been identified.
- [ ] PDP only decides; it never silently mutates business data.
- [ ] `PolicyInput` includes subject, tenant, action, resource, and required context.
- [ ] Every actor/role/tenant/resource field has trusted provenance.
- [ ] PEP executes only on a valid ALLOW matching action/resource within its validity window.
- [ ] DENY, ERROR, NULL, undefined, timeout, and contract mismatches all fail closed.
- [ ] 401/403/404/5xx statuses are mapped per API without leaking unauthorized data.
- [ ] Mandatory obligations such as masking/auditing are enforced or the request is blocked.
- [ ] Tenant-scoped role gates and object ACL/owner checks are combined properly.
- [ ] HTTP, service, message, job, and download/export paths all have corresponding enforcement.
- [ ] Spring Method Security is enabled and cannot be bypassed via proxy self-invocation.
- [ ] Query-time tenant/resource scoping protects data even after PDP ALLOW.
- [ ] WRITE/DELETE paths have guarded transactions or consistency protocols for TOCTOU.
- [ ] Cache keys include subject, tenant, resource, action, revision, and appropriate TTL.
- [ ] PAP manages policy versions, reviews, tests, rollouts, and rollbacks.
- [ ] Remote PDPs have auth, timeouts, bounded retries, circuit breakers, and monitoring.
- [ ] PDP unit tests, PEP integration tests, and PEP–PDP contract tests exist.
- [ ] Decision logs and enforcement logs have correlation without leaking secrets/unauthorized PII.

**Conclusion:** Separating **where decisions are made** (PDP) from **where actions are gated and executed** (PEP) makes dynamic policies easier to reuse, test, audit, and evolve without duplicating rules everywhere. Yet those benefits materialize only when PEPs cover every access path, PDP inputs come from trusted sources, every missing or failing decision **fails closed**, and permissions stay bound to the exact subject–tenant–action–resource at execution time. Spring Security provides the interceptors and APIs to connect this layer; protecting transactions, object data, and the policy lifecycle remains the application's design responsibility.

## References

- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): role of `AuthorizationManager` and interceptors.
- [Spring Security – AuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize`/`verify` contract and results.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, custom managers, bean-based policies, and interception.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP PEP, custom `AuthorizationManager`, and fallback policies.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): per-resource permissions.
- [Open Policy Agent – Documentation](https://www.openpolicyagent.org/docs): decoupling policy decision/enforcement and Rego.
- [Open Policy Agent – REST API](https://www.openpolicyagent.org/docs/rest-api): `POST /v1/data/...`, `input`, `result`/undefined, and decision logging.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): why per-object-ID authorization must be enforced on every API.
