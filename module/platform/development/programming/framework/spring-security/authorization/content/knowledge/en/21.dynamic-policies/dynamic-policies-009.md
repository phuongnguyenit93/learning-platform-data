# Policy Versioning, Canary Rollouts, and Rollback Plans in Spring Security

## 1. Why is editing an authorization rule riskier than editing a UI button?

Suppose a document management system enforces **policy v1**: a document owner can SHARE if they hold the `document:share` functional authority. The security team wants to roll out **policy v2**: the same condition, plus the SHARE operation requires valid strong authentication (MFA/step-up) evidence.

If you replace all of v1 with v2 immediately, several things can go wrong:

- Legitimate users get blocked from SHARE because the step-up flow is not ready yet.
- Service A runs policy v2 while Service B still runs v1.
- A syntactically valid policy reads the wrong tenant or resource attribute.
- Caches keep serving a v1 `ALLOW` decision after v2 tightened permissions.
- A configuration error defaults to allow when a policy cannot be found.
- Rolling back to v1 allows SHARE without MFA again, inadvertently **reintroducing a security vulnerability**.
- The policy changed while database schemas, event consumers, or resource services are not yet compatible.

Therefore, changing a policy is not just editing an expression in `@PreAuthorize`. You need **immutable artifacts, approvals, active revisions, canary cohorts, live decision observability, revocation capability, and guarded rollback procedures**.

Goals of this lesson:

1. Understand how **policy version**, authorization data version, and application deployment version differ.
2. Design safe **policy release** storage, review, and activation.
3. Apply **shadow/dry-run**, **canary**, and **phased rollouts** without confusing preview with enforcement.
4. Integrate a **policy dispatcher** with Spring Security method/request authorization.
5. Design **rollbacks**, emergency denials, policy/data freshness, caching, and failure audits.
6. Build a permission-difference test matrix and run a Java 17+ demo with deterministic stdout.

**Supreme principle:** never trade accurate authorization checks for rollout convenience. An old policy version is a valid fallback only when **it still satisfies mandatory security conditions and data freshness budgets**.

## 2. Versions that must never be conflated

| Version | What does it represent? | Example | Why it matters |
| --- | --- | --- | --- |
| **Policy revision** | Contents of the grant/deny rule set | `document-policy@v2` | Identifies exact logic being applied |
| **Policy artifact digest** | Hash of the published artifact contents | SHA-256 of bundle | Detects wrong version or tampering |
| **Release/activation revision** | Who uses which policy, starting when | `release-2026-11-A` | Same policy can be active for different cohorts |
| **Policy schema version** | Input attribute contract and structure | `schemaVersion=3` | Prevents evaluator from misreading fields |
| **Application version** | Running Java service build | `app-4.9.1` | Determines policy compatibility |
| **Membership/ACL data version** | State of roles, grants, owners, tenants | `membershipEpoch=128` | Permissions change even when policy code stays unchanged |
| **Decision ID / audit ID** | One specific authorization evaluation | `decision-7f...` | Investigates exact caller, rule, and outcome |

A Git commit ID **can** be part of a policy revision, yet does not prove that release is active in production. Conversely, policy v2 may already be published while only 5% of tenants run v2 and 95% still use v1.

**Example:**

```text
Code application:       app-4.9.1
Supported policy schema: 3
Approved artifacts:    doc-policy@v1, doc-policy@v2
Release routing:
  tenant-a -> doc-policy@v1
  tenant-b -> doc-policy@v2
  tenant-c -> doc-policy@v1
ACL data for tenant-b: membershipEpoch=128
```

A READ decision for Bob can flip from ALLOW to DENY when Bob is removed from tenant B, even if `doc-policy@v2` **never changed**. Always separate **policy deployment** from **revoking permissions in dynamic data**.

### Versions must have explicit scope

Not every resource type must share one global version:

- `document-read-policy@v4`.
- `invoice-approval-policy@v7`.
- `tenant-membership-policy@v3`.
- `share-link-policy@v2`.

Yet you should not scatter arbitrary uncoordinated versions that make it impossible to tell which policy governed a request. A **policy bundle/release manifest** can pin the required set of versions and activate only after verifying compatibility.

## 3. Policy-as-code and immutable artifacts

Policy changes should follow a security-controlled software lifecycle:

```text
Author proposes change
       |
       v
Code review + security review
       |
       v
Static/schema checks + unit tests + differential tests
       |
       v
Build immutable artifact/bundle
       |
       v
Digest/signature/attestation (if required by architecture)
       |
       v
Approved release manifest
       |
       v
Shadow / canary / phased rollout
       |
       v
Monitor results and verify at PEP
```

**Immutable artifact** means once `doc-policy@v2` is published, its contents are never edited in-place. To change rules, create `v3` or an approved hotfix. If the same name `v2` points to two different contents, logs, caches, and rollbacks become irreproducible.

A policy release should contain at least:

| Field | Purpose |
| --- | --- |
| `policyId` | Policy name, e.g., `document-access` |
| `revision` | Immutable version |
| `artifactDigest` | Exact content identifier |
| `schemaVersion` | Attribute/resource contract |
| `approvedBy` and `approvedAt` | Approval audit |
| `releaseId` | Routing/activation version |
| `baselineRevision` | Version active before rollout |
| `candidateRevision` | Version being tested |
| `cohortDefinition` | Group of tenants/subjects/services targeted |
| `rolloutStage` | SHADOW, CANARY, GENERAL, or HOLD |
| `requiredGuardrails` | Invariants that must never be bypassed |
| `rollbackTarget` | Version permitted to revert to on incident |

### Example release manifest

```json
{
  "releaseId": "doc-release-2026-11-05-r2",
  "policyId": "document-access",
  "schemaVersion": 3,
  "baselineRevision": "v1",
  "candidateRevision": "v2",
  "candidateDigest": "sha256:example-digest-from-reviewed-build",
  "stage": "CANARY",
  "cohort": {
    "type": "TENANT_ALLOWLIST",
    "tenantIds": ["tenant-canary"]
  },
  "guardrails": {
    "denyCrossTenant": true,
    "denyDeletedResource": true,
    "requireAuthenticatedSubject": true
  }
}
```

This is **design-illustrative JSON**, not a Spring Security or Open Policy Agent schema. `candidateDigest` is a placeholder string, **not a real hash**; in production, digests must be computed from the artifact and verified. Canary tenant lists must be controlled by release governance—**never** read from a client-declared header.

**Never** let requests send `policyVersion=v1` to pick a more lenient version. Policy routing is a **trusted control-plane** decision, not a caller authorization option.

## 4. Policy Decision Point and Policy Enforcement Point

In an authorization architecture:

- **PAP (Policy Administration Point):** authors, approves, and publishes policies.
- **PDP (Policy Decision Point):** evaluates rules and returns decisions.
- **PIP (Policy Information Point):** fetches actor, tenant membership, resource owner, ACL, and context.
- **PEP (Policy Enforcement Point):** actually allows or blocks requests/methods/DB mutations.

In a Spring Security application:

```text
HTTP Request / Service Method
          |
          v
PEP: AuthorizationFilter or method interceptor
          |
          v
Version Router (trusted release configuration)
          |
          +--> Baseline PDP: doc-policy@v1
          |
          +--> Candidate PDP: doc-policy@v2
          |
          v
Authoritative Decision: ALLOW | DENY
          |
          v
PEP enforces result, not just logging
          |
          v
Service + repository with tenant/resource scope
```

The PDP can be an in-JVM Java bean or an external service. **A returned decision does not enforce itself**: if a controller still queries the repository and returns data when the PDP says DENY, the entire authorization pipeline fails.

Shadow/candidate evaluations are predictive only and **must never** alter the authoritative decision while in SHADOW stage.

## 5. Decision contracts must stay stable across versions

An evaluation includes all components:

```text
subject  = authenticated principal + verified tenant role
resource = Document 42, tenant A, owner Alice, status DRAFT
action   = SHARE
context  = server time, authentication assurance, workflow state
```

If v2 adds an `mfaConfirmed` attribute yet an older app omits it, the evaluator can encounter null. Define explicitly:

- New **mandatory** fields require a new schema version or compatible rollout.
- Missing fields must **DENY** any rule requiring them—never silently default to true.
- Unknown enums/actions must be refused or rejected per contract; never coerce unknown into READ.
- `null`/`abstain` engine outputs must never be interpreted as ALLOW.
- Attribute provenance must be verified; e.g., MFA cannot come from a client-sent `X-MFA: yes`.

An internal result might look like:

```json
{
  "effect": "DENY",
  "reasonCode": "STEP_UP_REQUIRED",
  "policyId": "document-access",
  "policyRevision": "v2",
  "releaseId": "doc-release-2026-11-05-r2",
  "evaluatedAt": "2026-11-05T09:00:00Z"
}
```

This is an example DTO, not default Spring Security output. `reasonCode` is useful for audits and metrics; **never expose internal owner/tenant/ACL details in responses** if the caller is unauthorized to know the resource exists.

### Safety invariants enforced outside individual versions

Certain conditions should hold across every policy version:

```text
Trusted authentication
AND Verified tenant membership
AND Real resource belongs to matching tenant
AND Account/resource not locked/deleted by mandatory policy
AND Valid action
AND Approved policy artifact + within freshness budget
AND Active version's rule permits the action
```

A candidate must never return ALLOW when invariants are violated, even due to a rule bug. Enforce these at the PEP, shared domain layer, database queries/RLS, or across multiple layers.

**Rolling back to an older version must never disable a guardrail imposed by an emergency security decision.** If a security bug was fixed in v2, v1 may **no longer be a safe** rollback target even if v1 previously ran stably.

## 6. Classifying changes before rollout

Not every change carries the same risk.

| Change | Example | Risks to monitor |
| --- | --- | --- |
| **Tightening** | Adding MFA requirement for SHARE | False denials for valid users, business disruption |
| **Relaxation** | Letting EDITOR read more sensitive docs | Data leaks if scope/tenant is wrong |
| **Correction** | Fixing a role mapping in one tenant | May flip both ALLOW and DENY |
| **Refactor** | Replacing SpEL with a Java bean keeping same logic | Regressions or changed precedence |
| **Attribute source change** | Moving permissions from JWT claims to DB | Sync lag, stale caches, availability |
| **New action/resource** | Adding `invoice:export` | Default permissions and new endpoints |
| **Emergency revoke** | Blocking a compromised user/tenant | Needs rapid effect without waiting for normal canary |

**Risk-based principle:** permission relaxations require stricter review gates and anti-privilege-escalation test evidence; permission tightenings require business-impact testing and valid recovery paths. Never use a slow phased rollout for an emergency access block if delay creates an unacceptable exposure window.

## 7. How does shadow evaluation (dry-run) work?

During SHADOW:

1. The PEP receives the request and verifies subject/resource normally.
2. **Policy v1 makes the real decision**, which the PEP enforces.
3. **Policy v2 runs alongside** on the same verified attribute set solely to record its outcome.
4. The system compares the two decisions and aggregates deltas.
5. v2's outcome **must never** grant extra access or block users while the stage is SHADOW.

```text
                       One verified request
                              |
                 +------------+-------------+
                 |                          |
                 v                          v
          Baseline policy v1          Candidate policy v2
                 |                          |
                 v                          v
         Real ALLOW / DENY         Simulated ALLOW / DENY
                 |                          |
                 v                          |
           PEP enforce                 Audit/compare only
                 |                          |
                 +------------+-------------+
                              |
                     Decision delta metrics
```

### Comparison matrix for v1 and v2

| v1 (enforced) | v2 (shadow) | How to interpret |
| --- | --- | --- |
| ALLOW | ALLOW | No outcome difference |
| ALLOW | DENY | Candidate **tightens**; check for false denials |
| DENY | ALLOW | Candidate **relaxes**; prioritize reviewing data-leak risk |
| DENY | DENY | Same outcome though reason may differ |
| Error/unknown | Any | Never use shadow as a granting path |
| Any | Error/unknown | Candidate not ready; must fix before canary |

**Note:** a `DENY→ALLOW` decision in shadow **does not prove** the user actually viewed data; v1 still blocked it. Conversely, an `ALLOW→DENY` shows the candidate would break a currently permitted request once activated.

### Shadow must have zero side effects

- Never write ACLs, mutate resource state, or send emails.
- Never trigger real approval workflows.
- Never increment billing quotas/usage counters as a real request.
- Never let the candidate pollute caches serving the baseline.
- Store redacted audit/delta metrics with rate limits and restricted access controls.

If the PDP queries a PIP/DB, shadow runs can increase load. Use sampling, timeouts, bulk attributes, or dedicated test infrastructure as needed. Never let a candidate failure fail the real request while the authoritative baseline is healthy, unless mandatory safety conditions themselves demand halting.

### Conditions to trust shadow results

Shadow is meaningful only if baseline and candidate receive **the exact same subject/resource/action/context snapshot**, or differences are explicitly recorded. If baseline reads owner before an update while candidate reads owner after another transaction, deltas may reflect data churn rather than rule differences.

Record policy version, input schema version, decision outcome, reason code, and timestamp; never log raw JWTs or document contents.

## 8. Canary: activating a version for a stable cohort

In CANARY stage, policy v2 is genuinely enforced by the PEP for a **limited cohort**, while everyone outside the cohort continues on v1.

```text
Authenticated request
       |
       v
Verified tenant + trusted release routing
       |
       +-- tenant in canary cohort -----> v2 (enforced)
       |
       +-- other tenants -------------> v1 (enforced)
```

Canary differs from shadow in one crucial way: **v2 has real enforcement impact** on ALLOW/DENY outcomes for the selected group.

### How to select the cohort?

Valid strategies:

- **Internal allowlist:** test tenants or opted-in customers only.
- **Stable hash:** a percentage of tenants selected by deterministic hashing of tenant ID with a managed salt/algorithm.
- **By environment/region:** sandbox, staging, or a single controlled production region.
- **By action:** enable v2 for READ only before SHARE/DELETE.
- **By user group:** internal staff, low-risk tenants, verified canary opt-ins.

Crucially, cohorts must be selected from **server-verified data**. Never let users pass `?usePolicy=v1` or `X-Canary: false` to opt out of v2.

### Stable cohorts instead of per-request randomness

Wrong:

```java
boolean useCandidate = Math.random() < 0.05;
```

If Alice sends two consecutive requests and each lands randomly on a different policy, permissions flicker between allow and deny; across two services in one transaction, it creates inconsistent behavior.

Better:

```text
cohortId = verifiedTenantId
bucket = stableHash("release-r2", cohortId) mod 10000
useCandidate = bucket < rolloutBasisPoints
```

This is a **conceptual algorithm**. Across multiple languages/microservices, standardize the hash algorithm, encoding, salt, version, and test vectors. Never assume Java's `String.hashCode()` matches a Go/Node service's hash.

If stability is needed **across the whole release lifecycle**, define percentage increases carefully: e.g., ramping 1% → 5% → 25% with the same salt/hash keeps previously selected tenants inside the cohort. Changing the seed mid-ramp reshuffles canary membership unpredictably.

### Never canary on a client-chosen ID

When a tenant selector comes from the URL, **verify membership before routing policy**. If a client can supply another tenant ID to force policy v1, canary routing becomes a bypass mechanism.

For cross-tenant objects, the PEP must still block at the tenant boundary **even if** the candidate accidentally returns allow.

## 9. A phased rollout plan

A practical flow might look like:

| Stage | Enforced policy | Gate criteria to advance |
| --- | --- | --- |
| **DRAFT** | v1 | Author v2; schema, lint, unit tests |
| **REVIEWED** | v1 | Security review, approval, digest, compatibility |
| **SHADOW** | v1; v2 compared | No unexplained dangerous deltas |
| **CANARY 1%** | v2 for small cohort | Negative and business-impact tests pass; PEP monitored |
| **CANARY 5%** | v2 for larger cohort | Metrics stable, zero cross-tenant leaks |
| **RAMP 25% → 50%** | v2 for more tenants | SLOs, deny rates, latency, PDP/DB errors within bounds |
| **GENERAL** | v2 nearly/fully live | Confirmed all PEPs report active target version |
| **CLEANUP** | v2 | After soak period, retire v1 only under an explicit plan |

These percentages are **examples**, not mandatory standards. For emergency blocks or critical-risk policies, phased rollouts may be **inappropriate**; apply an emergency deny layer rapidly and measure propagation.

### Approval gates and ownership

Define clearly:

- Who can author and edit rules.
- Who can approve releases.
- Who can raise canary percentages.
- Who can roll back or trigger emergency stops.
- Who monitors dashboards and assesses impact.
- Who reconciles security incidents.
- Whether four-eyes approval or break-glass procedures are required.

Never let the same application API caller request a resource while also picking the policy version or editing rollout config. **Control plane and data plane privileges must be separated.**

## 10. What to measure during shadow/canary?

Do not watch HTTP 5xx alone. A buggy policy can over-grant permissions **without throwing errors**.

Useful metrics:

| Group | Metric/observation | Rationale |
| --- | --- | --- |
| Correctness | `ALLOW→DENY` delta | Measures tightening impact |
| Correctness | `DENY→ALLOW` delta | Prioritizes catching unintended privilege expansion |
| Authorization | Deny rate by action/tenant cohort | Spots regressions without hiding behind aggregates |
| Security | Cross-tenant attempts DENIED | Verifies invariant |
| Availability | PDP unavailable/timeout/invalid revision | Prevents fail-open |
| Performance | Authorization latency p50/p95/p99 | Checks whether new policy incurs excessive I/O |
| Data freshness | Policy/data age, activation lag | Verifies revocation SLA |
| Consistency | Share of PEPs reporting expected active revision | Detects rollouts stuck before reaching all nodes |
| Business | Blocked share/export actions, support tickets | Catches false denials |
| Audit | Decision version and reason codes | Enables evidence-based investigations |

### Count the right denominator

For example, out of 100 canary requests, v2 denies 40, yet 39 were already denied by v1—the real change is small. Conversely, 1 `DENY→ALLOW` on sensitive data export can be far worse than 100 `ALLOW→DENY` flips on a low-risk UI action.

Group by **resource type, action, tenant, client, and policy version**, with bounded-cardinality labels. Never put raw `subjectId`/`documentId` into metric labels where cardinality explodes or data leaks. Use access-controlled security audits for detailed forensics.

### An example stop threshold

```text
STOP if:
  at least 1 DENY->ALLOW on cross-tenant invariant
  OR new permission lacks approval
  OR candidate version cannot be verified
  OR PDP freshness exceeds budget
  OR error rate/latency exceeds approved SLO threshold
```

These thresholds are an **example operational policy**. Define who receives alerts, who has authority to halt, and whether the stop tool works even when the main system is degraded.

## 11. Integrating with Spring Security: technical boundaries

Spring Security provides `authorizeHttpRequests`, `@PreAuthorize`, and `AuthorizationManager<T>`. It **does not ship** a universal built-in canary/rollback API for every application. Version routing, policy stores, and approval workflows must be managed by the application or your organization's policy platform.

### AuthorizationManager and Spring Security versions

Javadocs vary across versions:

- In Spring Security 6.5, `AuthorizationManager<T>` still has `check(Supplier<Authentication>, T)` (deprecated) and default `authorize(...)`, alongside `AuthorizationDecision`/`AuthorizationResult`.
- In 7.x versions, `authorize(...)` is the primary method; nullability annotations/APIs evolve.
- `AuthorizationDecision` can represent allow/deny results in corresponding integrations.

**Never** copy a class overriding `check` from a 6.x example assuming it compiles unchanged in every 7.x release. Check Javadocs for your locked dependencies, run compile tests, and pin runtime compatibility in your release manifest.

### @PreAuthorize with a versioned policy bean

This integration style is straightforward to test when policies run in-JVM:

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
        "hasAuthority('document:share') and " +
        "@documentPolicyFacade.canShare(authentication, #id)"
    )
    public ShareResult share(
            @P("id") Long id, ShareRequest request) {
        // Runs only if policy granted access.
        // Re-check data/writes at transaction boundary when needed.
        return shareCommand.execute(id, request);
    }
}
```

This is a **component fragment**: `DocumentRepository`, `ShareResult`, `ShareRequest`, `shareCommand`, and bean `documentPolicyFacade` are application components to implement. It illustrates placing a PEP at the service layer, **not a standalone file**.

A facade might work as follows:

```java
public boolean canShare(Authentication authentication, Long id) {
    VerifiedActor actor = actors.fromAuthentication(authentication);
    DocumentFacts doc = facts.findVisibleDocument(
        actor.verifiedTenantId(), id
    );
    if (doc == null) {
        return false;
    }

    ReleaseSnapshot release = releaseRegistry.currentFor(
        "document-access", actor.verifiedTenantId()
    );
    if (!release.isVerifiedAndFresh()) {
        return false;
    }

    PolicyDecision enforced = policies.evaluate(
        release.activePolicyRevision(),
        actor, doc, Action.SHARE, serverContext.now()
    );

    shadowComparison.compareAsyncWithoutEffects(
        release, actor, doc, Action.SHARE, enforced
    );

    return enforced.allowed();
}
```

This is **Java-style pseudocode**, not standalone compilable: `VerifiedActor`, `DocumentFacts`, `ReleaseSnapshot`, `policies`, `serverContext`, and `shadowComparison` are custom domain APIs. Shadow comparison is optional, must never alter the enforced result, and must never waive mandatory PEP constraints.

**Important:** `canShare` must obtain tenant and subject from verified Authentication/membership—never calling `releaseRegistry.currentFor(...)` with an arbitrary client-declared tenant ID. `facts` must load the real document and verify tenant/owner/ACL; trusting client JSON exposes both baseline and candidate to exploitation.

### Data-scoped enforcement is still required

Even though `@PreAuthorize` blocks before the method body, a resource can change owner/status or SHARE permission can be revoked between check and execution. For sensitive mutations, use transactions/conditional updates with tenant/resource/authorization constraints, optimistic locks, or suitable synchronization.

`@PostAuthorize` is **not** sufficient to protect writes because side effects may already commit before post-checking. Never think rolling back a *policy version* rolls back *database transactions* or already-sent emails/events.

### Should beans be split by version?

A clean pattern:

```java
public interface DocumentPolicy {
    PolicyDecision decide(
        VerifiedActor actor,
        DocumentFacts document,
        Action action,
        VerifiedContext context
    );
}

public final class DocumentPolicyV1 implements DocumentPolicy { /* ... */ }
public final class DocumentPolicyV2 implements DocumentPolicy { /* ... */ }
```

This is a structural outline: `PolicyDecision`, `VerifiedActor`, `DocumentFacts`, `Action`, and `VerifiedContext` are application types. The version router picks the implementation from **signed/verified** release config, never from request parameters.

Keeping two versioned beans side by side in the same JVM eases shadow and canary testing, though you must account for memory/CPU cost. With external PDPs, policy versions can live in separate bundles; provenance, audit, and rollback requirements stay identical.

## 12. Policy versions must not break tenant, action, or object scope

Risky example:

```java
if (useCandidate) {
    return request.hasAuthority("document:read");
}
return oldPolicy.canRead(authentication, documentId);
```

This candidate drops owner, tenant, ACL, and resource status checks: during the canary, any user holding the functional authority can read anyone else's documents.

Safer design:

```text
mandatoryBoundary(actor, document, action)
    AND
selectApprovedVersion(release, verifiedTenant)
        .decide(actor, document, action, verifiedContext)
```

Every version must still pass through **mandatory invariants**. If policy v2 fixes a cross-tenant bug, never let v1 keep serving other tenants' production traffic under a "1% canary": deploy a mandatory deny/hotfix layer ahead of all policies or roll out globally under an emergency SLA.

**This does not mean duplicating every mandatory check in every layer**, yet the architecture needs a trustworthy enforcement point tested across versions that cannot be disabled by the release router.

## 13. Atomic activation: who is running which version?

A release config source might store:

```text
policy_id       = document-access
release_id      = release-42
baseline        = v1
candidate       = v2
stage           = CANARY
cohort_revision = allowlist-r3
activation_epoch= 105
effective_at    = 2026-11-05T10:00:00Z
```

When transitioning stage from CANARY to GENERAL, the system must guarantee:

- Control-plane config updates have **appropriate consistency**, never leaving half-updated records.
- PEPs use **one consistent release snapshot** per decision; never reading v2's stage paired with v1's digest.
- The v2 artifact is ready and verified **before** the activation pointer switches to it.
- Every PEP can report its **active revision and epoch**.
- During propagation, out-of-sync nodes are tracked and handled per SLA.
- Policy config cannot be modified by ordinary application callers.

A common pattern creates an **immutable release object** and updates a **pointer/epoch** conditionally (CAS/transaction). This enables faster rollbacks than editing multiple rule rows directly. Yet across multiple services/nodes with caches, updating a DB pointer **does not guarantee** all PEPs switched immediately.

### In-flight requests when a release changes

```text
T1: starts check with release epoch 105 (v1)
T2: activates release epoch 106 (v2)
T1: continues a write operation
```

If business rules require the new policy to take effect before T1 commits, add epoch/transaction re-checks or write guards; never assume switching the pointer halts in-flight requests automatically.

For ordinary reads, per-decision snapshots are typically acceptable; for financial approvals or sensitive ACL changes, define **effective policy timing** and DB consistency explicitly.

## 14. Rollback means reverting to a **permitted** version, not blindly back to v1

Suppose candidate v2 has a bug blocking Alice from SHARING her document even after MFA. You might want to revert to v1 immediately. Yet v1 did not require MFA, whereas MFA was just mandated to mitigate an incident. **Rolling straight back to v1 could reopen the vulnerability**, so it is not always permitted.

Distinguish:

| Incident type | Appropriate response |
| --- | --- |
| Candidate over-tightened wrongly; baseline still meets guardrails | Switch active pointer back to approved baseline |
| Candidate relaxed permissions causing data exposure | Halt candidate, apply emergency deny, assess impact, and revoke leaked data/tokens |
| Baseline also contains the newly patched vulnerability | Never roll back blindly to baseline; ship a safe hotfix/guardrail |
| Candidate artifact fails verification | Do not activate; keep verified revision within freshness budget or deny |
| Data schema migrated incompatibly with baseline | Roll back only with a compatibility plan; never let old code misread new schema |
| External PDP fails | Fail closed per budget; use last-known-good *only if still valid*, never default ALLOW |
| Some nodes not yet updated | Isolate/throttle traffic or reject requests failing minimum revision |

### Rollback playbook

1. Identify the incident and **blast radius**: actions, cohorts, tenants, policy versions, involved PEPs.
2. **Stop the ramp:** halt canary increases, disable candidate in unaffected cohorts if possible.
3. **Immediately protect** over-permissive paths: apply deny overlays or safe isolation.
4. Identify an approved rollback target that **still satisfies current guardrails**.
5. Conditionally update the release pointer/epoch; never edit immutable artifacts.
6. Confirm all PEPs report the new revision/epoch within the propagation budget.
7. Flush/invalidate decision caches and policy caches by revision/cohort so stale ALLOWs cannot linger.
8. Test with real requests/identities inside the canary, outside the canary, and on sensitive actions.
9. Audit **side effects that already occurred**: exported documents, created shares, committed approvals; policy rollback does not undo them.
10. Record audits, notify owners, and prepare v3/new guardrails.

### Kill switches also require authorization and auditing

A "disable candidate" button can disrupt business flows yet is often needed in incidents. Operators allowed to use it need dedicated privileges (e.g., `POLICY_RELEASE_ADMIN`), proper verification, and full auditing. Never expose kill switches directly on user-facing resource APIs.

**Note:** a "kill switch" setting `permitAll()` to stop errors is a **flawed design**. Emergencies should maintain or tighten denials on affected paths, or fail safely when decisions cannot be made.

## 15. Freshness, caching, and operating when the control plane is down

There are multiple cache layers:

- **Policy artifact cache:** verified code/AST/bundles for a version.
- **Release routing cache:** which revision each tenant/cohort uses.
- **Authorization data cache:** memberships, ACLs, owners, share grants.
- **Decision cache:** ALLOW/DENY outcomes for subject-resource-action-context.
- **Response cache:** actual payloads returned after authorization.

Switching v1 → v2 requires evaluating all five, not just clearing one cache.

### Minimal decision cache key

A key like `canRead:document42` is unsafe because it omits the subject. You may need:

```text
subjectId
| verifiedTenantId
| resourceType
| resourceId
| action
| releaseId
| policyRevision
| membershipOrAclVersion
| relevantContextVersion
```

You do not always encode every raw field directly; namespacing/hashing and conditional invalidation work too. However, **all permission-affecting dimensions must be represented** or re-checked at runtime.

### Last-known-good does not always mean safe

Suppose the PDP holds a verified `doc-policy@v1`, yet v1 **allows** Bob to read after Bob was revoked in the membership store. If the PIP cannot refresh permissions for 30 minutes, continuing to use v1 does not guarantee correctness.

OWASP recommends defining a **freshness budget** for policies and security-relevant data. When data/bundles expire or are missing, deny **affected operations** instead of falling back to ALLOW. "Last-known-good" is valid only when the artifact is **verified** and freshness/guardrail conditions **remain satisfied**.

A baseline rule:

```text
if artifact invalid / unapproved / unsupported:
    DENY affected operation

if required membership/ACL/revocation data stale beyond budget:
    DENY affected operation

if verified policy and data fresh enough:
    evaluate current approved revision
```

This is conceptual logic; a system may return 503 instead of 403 on dependency outages, yet **never grant access** just to hide availability errors.

### Invalidation and propagation

- Push invalidation events or poll revisions/epochs with bounded intervals.
- Use compare-and-swap/monotonic epochs; reject stale updates overwriting newer releases.
- At startup, PEPs serve protected operations only after valid versions and mandatory data load.
- If the control plane disconnects, PEPs may use verified policies still within freshness if allowed by design.
- If emergency blocks require taking effect within seconds, never use multi-minute cache TTLs.
- Measure **effective revision at the PEP**, not only "publish succeeded" at the PAP.

## 16. Schema and protocol compatibility across Java services

A new candidate may require different attributes:

```json
{
  "subject": {
    "id": "alice",
    "tenantId": "tenant-a",
    "strongAuthentication": true
  },
  "resource": {
    "type": "Document",
    "id": 42,
    "tenantId": "tenant-a",
    "status": "DRAFT"
  },
  "action": "SHARE",
  "context": {
    "evaluatedAt": "2026-11-05T09:00:00Z"
  }
}
```

This attribute payload is **PEP/PIP-verified data** in the sample architecture, not client-submitted JSON able to grant permissions.

If an older service only sends `subject.id` and `resource.id`, a candidate requiring `strongAuthentication` hits missing data. You must:

1. Define `schemaVersion` and required fields.
2. Upgrade producers/PEPs to supply attributes before activating the policy.
3. Default missing required attributes to **DENY**.
4. Test backward/forward compatibility.
5. Keep v1 available at runtime until rollback targets are confirmed.
6. When DB migrations cannot roll back, prepare a **forward fix** instead of forcing old code onto an incompatible schema.

### Policy version and app version must be checked at startup

You can record:

```text
policy-v1 compatible with schema 2..3
policy-v2 requires schema 3
app-4.9 supports schema 2
app-4.10 supports schema 3
```

In this scenario, never enable v2 for app-4.9. At startup/activation, verify policy/schema compatibility and deny unsupported protected operations rather than reading missing fields as true.

## 17. Standalone Java 17: reproducible shadow, canary, and rollback

The following program **uses no Spring Security, database, or server**. It models policies v1 and v2; v2 adds strong authentication for owner SHARE. A **server-configured** canary tenant list picks which requests run under v2. Shadow runs v2 yet **never alters** baseline enforcement. Finally, the router rolls back the canary cohort.

The demo intentionally illustrates that **rolling back from v2 to v1 relaxes the MFA requirement again**; production may do this only if v1 remains an approved rollback target under current security policy.

Save to `PolicyReleaseDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class PolicyReleaseDemo {
    enum Action { READ, SHARE }

    record Subject(
        String id, String tenant, boolean active,
        boolean strongAuth, Set<Action> abilities) {}

    record Document(
        long id, String tenant, String owner, boolean deleted) {}

    record Decision(
        boolean allowed, String reason, String revision) {

        String label() {
            return (allowed ? "ALLOW" : "DENY")
                + "/" + reason + "@" + revision;
        }
    }

    static Decision decide(
            String revision, Subject subject,
            Document document, Action action) {

        if (!"v1".equals(revision) && !"v2".equals(revision)) {
            return new Decision(false, "UNKNOWN_POLICY", revision);
        }
        if (subject == null || document == null || action == null) {
            return new Decision(false, "INVALID_INPUT", revision);
        }
        if (!subject.active() || document.deleted()) {
            return new Decision(false, "INACTIVE", revision);
        }
        if (!subject.tenant().equals(document.tenant())) {
            return new Decision(false, "TENANT_MISMATCH", revision);
        }
        if (!subject.abilities().contains(action)) {
            return new Decision(false, "MISSING_ACTION", revision);
        }
        if (!subject.id().equals(document.owner())) {
            return new Decision(false, "NOT_OWNER", revision);
        }

        // v2 tightens rule for SHARE; all mandatory checks remain.
        if ("v2".equals(revision)
                && action == Action.SHARE
                && !subject.strongAuth()) {
            return new Decision(false, "STEP_UP_REQUIRED", revision);
        }

        return new Decision(true, "OWNER", revision);
    }

    static class ReleaseRouter {
        private final String baseline = "v1";
        private final String candidate = "v2";
        private final Set<String> canaryTenants;

        ReleaseRouter(Set<String> selectedTenants) {
            this.canaryTenants = new HashSet<>(selectedTenants);
        }

        String activeFor(String verifiedTenant) {
            return canaryTenants.contains(verifiedTenant)
                ? candidate : baseline;
        }

        Decision enforce(
                Subject subject, Document document, Action action) {
            return decide(
                activeFor(subject.tenant()), subject, document, action);
        }

        // Dry-run, never alters enforce() outcome.
        Decision shadowCandidate(
                Subject subject, Document document, Action action) {
            return decide(candidate, subject, document, action);
        }

        void rollbackCanary() {
            canaryTenants.clear();
        }
    }

    public static void main(String[] args) {
        ReleaseRouter router =
            new ReleaseRouter(Set.of("tenant-canary"));

        Subject aliceA = new Subject(
            "alice", "tenant-a", true, false,
            Set.of(Action.READ, Action.SHARE));
        Subject aliceCanary = new Subject(
            "alice", "tenant-canary", true, false,
            Set.of(Action.READ, Action.SHARE));
        Subject aliceStrong = new Subject(
            "alice", "tenant-canary", true, true,
            Set.of(Action.READ, Action.SHARE));
        Subject bobCanary = new Subject(
            "bob", "tenant-canary", true, true,
            Set.of(Action.READ, Action.SHARE));

        Document docA =
            new Document(42, "tenant-a", "alice", false);
        Document docCanary =
            new Document(43, "tenant-canary", "alice", false);

        System.out.println("A active: "
            + router.activeFor(aliceA.tenant()));
        System.out.println("A SHARE: "
            + router.enforce(aliceA, docA, Action.SHARE).label());
        System.out.println("Canary active: "
            + router.activeFor(aliceCanary.tenant()));
        System.out.println("Canary SHARE: "
            + router.enforce(
                aliceCanary, docCanary, Action.SHARE).label());
        System.out.println("Canary READ: "
            + router.enforce(
                aliceCanary, docCanary, Action.READ).label());

        // Shadow comparison, does not interfere with enforcement.
        System.out.println("Shadow baseline SHARE: "
            + decide("v1", aliceCanary, docCanary,
                Action.SHARE).label());
        System.out.println("Shadow candidate SHARE: "
            + router.shadowCandidate(
                aliceCanary, docCanary, Action.SHARE).label());

        System.out.println("Canary SHARE after MFA: "
            + router.enforce(
                aliceStrong, docCanary, Action.SHARE).label());
        System.out.println("Wrong tenant: "
            + decide("v2", aliceA, docCanary,
                Action.READ).label());
        System.out.println("Not owner: "
            + router.enforce(
                bobCanary, docCanary, Action.SHARE).label());

        router.rollbackCanary();
        System.out.println("After rollback: "
            + router.enforce(
                aliceCanary, docCanary, Action.SHARE).label());
        System.out.println("Unknown revision: "
            + decide("v99", aliceCanary, docCanary,
                Action.READ).label());
    }
}
```

Compile/run with JDK 17+:

```bash
javac PolicyReleaseDemo.java
java PolicyReleaseDemo
```

Exact stdout:

```text
A active: v1
A SHARE: ALLOW/OWNER@v1
Canary active: v2
Canary SHARE: DENY/STEP_UP_REQUIRED@v2
Canary READ: ALLOW/OWNER@v2
Shadow baseline SHARE: ALLOW/OWNER@v1
Shadow candidate SHARE: DENY/STEP_UP_REQUIRED@v2
Canary SHARE after MFA: ALLOW/OWNER@v2
Wrong tenant: DENY/TENANT_MISMATCH@v2
Not owner: DENY/NOT_OWNER@v2
After rollback: ALLOW/OWNER@v1
Unknown revision: DENY/UNKNOWN_POLICY@v99
```

**Explanation:**

- Regular tenants stay on v1 and owners can SHARE.
- The canary tenant runs v2 and SHARE is denied without strong MFA; READ is unaffected.
- Shadow shows v1 ALLOW versus v2 DENY; in real SHADOW mode only v1 is enforced.
- With MFA → v2 permits SHARE; cross-tenant or non-owner → deny.
- After rollback, the canary returns to v1 and non-MFA SHARE ALLOWs again. **This shows why rollback targets must be approved**, never assuming rollback is always safe.
- Unknown revisions default to DENY.

**Demo limitations:** the allowlist resides in memory, and `strongAuth`/tenants/abilities are trusted fixtures created by the program. There is no JWT verification, distributed rollout, digests, policy signatures, databases, transactions, audit events, cache invalidation, or concurrency. In production, the release router accepts only verified tenants; policies preserve active guardrails, and rollbacks require authorization control-plane approval.

## 18. Mandatory tests before rollout

### 18.1. Unit tests: policy stays within intended bounds

Build a decision table by subject, tenant, resource, action, and context:

| Case | v1 | Expected v2 | Meaning |
| --- | --- | --- | --- |
| Owner SHARE, no MFA | ALLOW | DENY | Intentional tightening |
| Owner SHARE, valid MFA | ALLOW | ALLOW | Does not block eligible users |
| Owner READ | ALLOW | ALLOW | Preserves read workflows |
| Non-owner SHARE | DENY | DENY | No privilege expansion |
| Cross-tenant READ | DENY | DENY | Safety invariant |
| Resource deleted | DENY | DENY | Safety invariant |
| Account suspended | DENY | DENY | Safety invariant |
| Unknown action/schema | DENY | DENY | Default deny |
| Unverified policy artifact | DENY | DENY | Never run untrusted revisions |
| Revoked membership | DENY | DENY | Permission data still respected |

This is a **decision table for the v1/v2 example**; not every system grants owners READ/SHARE this way.

### 18.2. Differential tests: one intentional change, not ten accidental ones

Run v1/v2 on identical fixtures and compute:

```text
delta = compare(
    baselineDecision(subject, resource, action, context),
    candidateDecision(subject, resource, action, context)
)
```

Classify deltas as expected or unexpected. Unexpected relaxations (v1 DENY, v2 ALLOW) must block canary release unless explicitly approved and covered by anti-IDOR/cross-tenant tests.

Never compare only overall ALLOW rates. Break down by action, resource class, tenant boundary, sensitive data, and role. A 1-in-1,000 change on `DELETE_INVOICE` can be far more dangerous than 100 changes on a harmless UI button.

### 18.3. Integration tests: verify outcomes right at the PEP

Testing `PolicyEngine.evaluate(...)` alone is insufficient. Verify:

- `@EnableMethodSecurity` is genuinely active.
- Calls pass through Spring beans/proxies; self-invocation does not bypass.
- `SecurityFilterChain` matches the right routes.
- `AuthorizationManager` denies properly with no data leaked in responses.
- Services/repositories perform zero side effects on DENY.
- Tenant/owner/ACL come from the DB, not declared inputs.
- Shadow never enforces candidate outcomes.
- Canary enforces the candidate **only** for verified cohorts.
- Rollback restores the right revision and invalidates caches.
- Jobs/queues/batches/exports are also guarded by PEPs/domain policies.
- DB role/share revocations take effect within SLA.
- Multi-version applications never misread schema attributes.

A Spring MVC test fragment might look like:

```java
mockMvc.perform(post("/api/documents/{id}/share", 42L)
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:share"))))
    .andExpect(status().isForbidden());
```

This is a **fragment**, requiring `MockMvc`, static imports, security test dependencies, authentication assurance fixtures, DB/share policies, and matching HTTP mappings. If v2 requires MFA and the fixture lacks it, 403 is expected; with real OAuth2/JWT, build principals carrying genuine assurance claims rather than relying solely on `@WithMockUser`. Crucially, assert that share grant creation **did not occur** when policy denies.

### 18.4. Failure-injection and rollout/rollback drills

| Simulated fault | Safety outcome to prove |
| --- | --- |
| Candidate bundle digest mismatch | Never activated |
| Candidate schema incompatible with app | Never activated / protected action blocked |
| Control plane unresponsive at startup | Never self-grants without valid policy |
| PDP dies after running | Uses verified/fresh policy per budget or denies |
| Membership/ACL data too stale | Denies affected operations |
| One PEP stays on v1 after rollout | Detected/isolated while mandatory guardrails hold |
| Permission revoked while cache is warm | Zero stale ALLOWs past SLA |
| Candidate v2 accidentally relaxes READ | Stop ramp, deny, investigate data exposure |
| Rollback pointer flips while cache still holds candidate | Never mixes revisions and outcomes |
| Rollback target schema-incompatible | Block rollback, execute forward fix |
| Request started before revoke/release | Follows designed transaction consistency |
| Release config edited via user API | Rejected; independent control-plane RBAC |
| Replaying an old release epoch | Rejects stale config below min revision |
| Rollback after emergency fix | Never reintroduces the patched vulnerability |

### 18.5. Concurrency tests

- Two operators change release stage simultaneously → CAS/version prevents lost updates.
- Two nodes read manifests at different epochs → measure propagation bounds and handling.
- One request calls two services → verify per-request/release snapshot consistency when required.
- Membership revoked between pre-check and DB update → test transactions/conditional mutations.
- Candidate threshold changes from 5% to 25% → existing canary tenants stay in cohort under stable bucketing.
- Rollback while a job is running → define execution conditions and idempotency.
- Repeated rollback clicks → never increment epochs into weird policy-less states.

## 19. Incident response plan: a concrete scenario

**Scenario:** a v2 rollout adds READ access for an internal document category. After canary reaches 5%, metrics detect unexpected `DENY→ALLOW` flips for a non-owner tenant.

Respond in order:

1. **Halt the rollout** and do not raise the threshold from 5% to 25%.
2. **Determine scope:** policy revision, release epoch, actions, cohorts, active PEPs.
3. **Mitigate risk immediately** via emergency deny or isolating affected endpoints/tenants rather than waiting for full root-cause analysis to plug the leak.
4. **Revert to an approved safe revision** if the baseline truly remains safe and compatible; otherwise issue a restrictive hotfix.
5. **Verify at the PEP** that cross-tenant/non-owner requests are denied, rather than trusting PAP dashboards alone.
6. **Revoke grants/tokens/exports** issued under the bad policy where possible; check presigned URLs or data that left the system.
7. **Reconcile audits** to identify who actually read or modified unauthorized resources.
8. **Write regression tests** for the exact failing actor/resource/action/context tuple.
9. **Review root cause:** missing tenant input, broken OR rule, tenant-less cache key, version mismatch, or missing approval.
10. **Ship a new fix** through the pipeline with added guardrails/tests rather than editing immutable v2 in place.

**Crucial practical point:** rollback governs **future** access decisions; it cannot retrieve a downloaded file or auto-delete records created under a bad grant. Incident response must address data impact, not merely turn dashboards green again.

## 20. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Versioning only the Java app, not policies | Unknown which rule granted access | Separate policy revision + digest + release epoch |
| Editing v2 in place | Audits/rollbacks irreproducible | Immutable artifacts, create new v3/hotfix |
| Letting clients pick `?policy=v1` | Bypasses candidate/guardrails | Trusted release router |
| Assuming publish success means all PEPs are active | Inconsistent decisions | Measure effective revision at PEPs |
| Returning candidate v2 results during shadow | Shadow accidentally becomes enforcement | Keep baseline authoritative |
| Shadow causing real side effects | Data/quotas/notifications mutated | Pure evaluation, side-effect isolation |
| Randomizing policy per request | Access flickers unpredictably | Stable cohorts/release snapshots |
| Canarying by unverified tenant header | Clients pick lenient paths | Verify tenant membership before routing |
| Comparing overall DENY rates only | Misses sensitive DENY→ALLOW bugs | Differential metrics by action/resource |
| Skipping schema compatibility checks | Missing attributes read as true | Validate schemas, fail closed |
| Testing only the policy bean | PEP/service bypasses go unseen | Integration tests through Spring security/proxies/DB |
| Returning `permitAll` when PDP fails | Fail-open | Safe deny/5xx per budget |
| Treating last-known-good as always safe | Revoked data/caches still allow | Freshness checks for both policies and data |
| Decision caches lacking versions | Reuses v1 ALLOW after v2 denies | Versioned cache keys/invalidations by revision & ACL epoch |
| Canarying a relaxing policy without mandatory tenant checks | Cohort data leaks | Shared guardrails, BOLA tests |
| Rolling back to a revision with a patched flaw | Reintroduces vulnerability | Approved safe rollback targets/hotfixes |
| Thinking policy rollback reverts past SQL writes | Data remains modified | Incident response and compensating actions |
| Sharing release privileges with user APIs | Control-plane escalation | Separate RBAC/approvals/audits |
| Omitting versions in audit events | Hard to investigate incidents | Log policy/release/epoch/decision |
| Logging raw JWTs or full resources | Sensitive data exposure | Redaction, data minimization |
| Letting old PEPs run past freshness budgets | Unauthorized access post-revocation | Propagation SLOs, quarantine/deny |
| Skipping async/queue/export routes | Call paths bypass new policy | Service/data-layer policies |
| Placing `@PostAuthorize` after writes thinking deny rolls back data | Side effects may have committed | Pre-authorization and scoped mutations |
| Monitoring availability without correctness | Bad ALLOWs emit zero 5xx | Security outcome/delta metrics |

## 21. Checklist for releasing a dynamic policy change

Before promoting a candidate policy to production:

1. **Are immutable policy ID/revision clear?** Is there a reproducible build source and digest?
2. **Is the impact tightening or relaxing?** Are risks classified per resource/action?
3. **Where do subject/resource/context come from?** Can clients spoof any attribute?
4. **Are tenant/owner/account-status invariants still protected?**
5. **Is the schema version compatible with all running apps/PEPs?**
6. **Are approvals and ownership complete?**
7. **Is shadow strictly observational?** Zero impact on enforced outcomes or side effects.
8. **Have all `DENY→ALLOW` deltas been reviewed?** Especially READ/EXPORT/DELETE/SHARE.
9. **Are canary cohorts selected deterministically from verified IDs?**
10. **Is there a 1% → 5% → ... ramp plan and explicit stop criteria?**
11. **Do metrics track `policyRevision`/`releaseEpoch` at the PEP?**
12. **Have data freshness/ACL membership/revocation budgets been measured?**
13. **Are caches invalidated when versions/ACLs/roles change?**
14. **Does the rollback target still satisfy current security guardrails?**
15. **Does the control plane enforce CAS/audits/RBAC?**
16. **How are in-flight requests/transactions handled across switches?**
17. **Do database writes enforce tenant/resource/permission constraints?**
18. **Do async, queue, export, storage, and admin flows share the same policy?**
19. **Have failure-injection tests covered lost PDPs, invalid bundles, and stale data?**
20. **Is there an incident playbook if data was accessed or altered?**

**Conclusion:** Good dynamic policy governance needs more than a "turn on v2" switch. It requires **immutable, verifiable policy artifacts**, **trusted release routing**, **zero-impact shadow runs**, **stable canaries**, **PEP-level decision monitoring**, **cache/data freshness**, and **rollbacks restricted to still-safe revisions**. Spring Security supplies the enforcement infrastructure via `AuthorizationManager` and method/HTTP security; the application must manage policies, versions, rollouts, and incident response as part of its security architecture.

## References

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, `Authentication`, and allow/deny mechanics.
- [Spring Security API — AuthorizationManager (7.x)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): `authorize(...)` signature and decision contract.
- [Spring Security API — AuthorizationManager (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): distinguishing `check(...)` and `authorize(...)`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and policy beans.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): HTTP PEPs and `AuthorizationManager<RequestAuthorizationContext>`.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, per-request checks.
- [OWASP — Authorization Policy and Data Distribution Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Policy_And_Data_Distribution_Cheat_Sheet.html): versioned policies, rollouts, freshness, revocation, last-known-good, fail closed.
- [OWASP — Authorization Patterns Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Patterns_Cheat_Sheet.html): PEP/PDP/PIP/PAP and trust boundaries.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level authorization required across every version.
