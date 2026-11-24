# Deploying Versioned Policy Changes with Verification and Rollback

> **Context:** Spring Security — Authorization, **Performance and Operations** track. This lesson walks through rolling out an **authorization policy** change into a live user-facing system: versioning, pre-activation verification, phased rollout, observing live decisions, and rolling back to an approved version when incidents occur. Examples use Java 17+ with Spring Security 6.x/7.x integration.

## 1. Why Manage the Lifecycle of Authorization Policies?

A change such as shifting from "reviewers may read reports across all owners" to "only owners may read" can affect thousands of requests. Both failure modes matter:

- **Unintended privilege widening:** user or tenant A reads/modifies/deletes B's resources; Broken Access Control risk.
- **Unintended privilege tightening:** legitimate workflows receive `403`, jobs fail, and users cannot complete tasks.
- **Inconsistency:** instance A runs the new rule while instance B still runs the old rule; the same principal and resource get conflicting outcomes.
- **Unreproducible incidents:** logs say only "denied" without showing which policy version produced the decision.
- **Slow or faulty rollback:** code changed, tokens/caches were not updated, or old rules are no longer compatible with the new schema.

The core rule is **packaging policies as immutable versioned snapshots**, verified before release and selected via an **active version pointer**. Never edit the contents of an activated version in place. Every decision should record `policyId`, `policyVersion`, action, resource type, and outcome; collect identifiers/logs strictly in compliance with data security rules.

Standard workflow:

~~~text
Propose change
    |
    v
Create new release (version + schema + digest)
    |
    v
Static validation + automated authorization matrix
    |
    v
Simulation / shadow evaluation (does not enforce new version's permissions)
    |
    v
Stage -> Canary -> Phased expansion
    |              |
    |              +-- anomalies/403s/latency spikes --> halt, rollback
    v
Cluster-wide verification + audit -> Complete
~~~

**Versioning alone does not guarantee security.** Rollback capability is only meaningful when configuration, storage, policy evaluators, live permissions, and business data are all designed to support it together.

## 2. Distinguishing the Version Types to Track

Do not lump everything under a vague "v2" label.

| Version / Component | Example | Purpose |
| --- | --- | --- |
| `policyId` | `report-read` | Identifies the rule set for one business capability |
| `policyVersion` | `2026-11-06.2` | Distinguishes **immutable policy content** |
| `schemaVersion` | `1` | Confirms parser/evaluator understands the structure |
| `digest` SHA-256 | Hash of canonical bytes | Detects tampering/mutation under the same version name |
| `applicationVersion` | `service-3.8.4` | Identifies the running Spring application code version |
| `activeVersion` | `2026-11-06.2` | Pointer to the currently enforced version |
| `rolloutId` | `rollout-20261106-a` | Correlates canary steps, metrics, and audits in one rollout |
| `policyDecisionVersion` | Value logged/traced | Answers "which rule evaluated this request?" |

Example illustrative JSON **policy bundle** (not a default Spring Security configuration):

~~~json
{
  "policyId": "report-read",
  "policyVersion": "2026-11-06.2",
  "schemaVersion": 1,
  "defaultEffect": "DENY",
  "requireAuthority": "report:read",
  "allowOwner": true,
  "allowReviewerCrossOwner": false
}
~~~

After creating the bundle, compute the SHA-256 digest over the **exact published artifact bytes**, store it in a manifest/registry, and sign per deployment mechanics. Never allow two different payloads to share the same `policyId + policyVersion`. If the same version exhibits a different hash, **refuse to load** and investigate instead of silently picking "whichever is newest."

The new version requires governance metadata: author, reviewers/approvers, ticket, timestamp, test matrix link, compatible code version, canary strategy, rollback plan, and target completion window. Store these in release records/audits; they need not all live inside the rule payload itself.

### What Scope Should One Policy Cover?

Version granularity must be tight enough for consistent rollback. When an action requires both endpoint permissions and object permissions, there are two clear options:

- **Bundle together:** one version governs all co-changing rules; activation switches the whole snapshot atomically.
- **Multiple interdependent bundles:** the release manifest must pin **the exact compatible version set** so new endpoint rules never meet stale service rules.

Either way, favor **deny by default**, evaluate against verified identity/authorities, and check owner/tenant on every resource. Never treat hiding a frontend button as server-side policy enforcement.

## 3. The "Prepare, Verify, Activate, Revert" Model

A straightforward lifecycle has these states:

~~~text
DRAFT -> VALIDATED -> STAGED -> CANARY -> ACTIVE
           |             |         |        |
           v             v         v        v
        REJECTED       ABORTED   ABORTED   SUPERSEDED
                                           (rollback to
                                            previous snapshot)
~~~

You do not need an over-engineered state machine for a small system, yet behavior must be clear:

1. **Prepare:** build the new artifact; validate schema, required fields, valid values, dependency list, and hash.
2. **Verify:** evaluate the `subject × action × resource × context` decision matrix; run positive/negative, regression, performance, and compatibility tests.
3. **Stage:** distribute the snapshot to instances without **switching the active pointer yet**.
4. **Canary:** apply the new version only to a deliberately selected cohort of requests/principals; observe decisions and impact.
5. **Activate:** swap the active pointer conditionally while checking the prior version still matches; log an audit record.
6. **Revert:** if agreed thresholds are breached, point back to the previously verified snapshot, reconcile post-rollback state, and remediate any impact that already occurred.

**Two crucial invariants:**

- **Immutable artifact:** never edit `version=2026-11-06.2` in place once staged; any edit creates a new version.
- **Conditional switch:** switch active from `v1` to `v2` only if active is still `v1`, preventing stale releases from overwriting newer ones.

Within a **single JVM**, `AtomicReference.compareAndSet` illustrates atomic version switching well. Across **multiple instances**, it **is not a cluster-wide coordination mechanism**: use a registry/config store with atomic compare-and-swap, ETag/revision, or transactions, then verify all instances observe the desired version.

## 4. Java 17: An End-to-End Standalone Example

This example illustrates report read permission checks:

- `policy-v1`: owners holding `report:read` may read; reviewers holding both `report:read` and `report:read:any` may also read reports owned by others.
- `policy-v2`: the new policy removes the cross-owner reviewer exception; only owners holding `report:read` may read.
- The candidate must pass the verification matrix before activation; if post-activation outcomes look abnormal, roll back by pointing back to the prior snapshot.

This is a **technical simulation of the policy lifecycle**, not a production policy distribution service. The program runs on JDK 17 with no Spring dependency.

Create **`PolicyRolloutDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

public final class PolicyRolloutDemo {

    record Principal(String name, Set<String> authorities) {
        Principal {
            Objects.requireNonNull(name, "name");
            authorities = Set.copyOf(authorities);
        }

        boolean has(String authority) {
            return authorities.contains(authority);
        }
    }

    record Report(long id, String owner) {
    }

    record PolicySnapshot(String version, boolean allowReviewerCrossOwner) {
        PolicySnapshot {
            if (version == null || version.isBlank()) {
                throw new IllegalArgumentException("version is required");
            }
        }
    }

    record Decision(String policyVersion, boolean allowed) {
    }

    static final class PolicyRegistry {
        private final Map<String, PolicySnapshot> versions =
                new ConcurrentHashMap<>();
        private final AtomicReference<PolicySnapshot> active;

        PolicyRegistry(PolicySnapshot initial) {
            Objects.requireNonNull(initial, "initial");
            versions.put(initial.version(), initial);
            active = new AtomicReference<>(initial);
        }

        // Create new immutable version; must not overwrite an existing version.
        void stage(PolicySnapshot candidate) {
            Objects.requireNonNull(candidate, "candidate");
            if (versions.putIfAbsent(candidate.version(), candidate) != null) {
                throw new IllegalArgumentException("duplicate version");
            }
        }

        String activeVersion() {
            return active.get().version();
        }

        PolicySnapshot activeSnapshot() {
            return active.get();
        }

        Decision decide(Principal principal, Report report) {
            // Snapshot is read exactly once for this decision.
            return evaluate(active.get(), principal, report);
        }

        Decision preview(String version, Principal principal, Report report) {
            PolicySnapshot candidate = versions.get(version);
            if (candidate == null) {
                throw new IllegalArgumentException("unknown version");
            }
            return evaluate(candidate, principal, report);
        }

        // This operation works for both promotion and rollback.
        boolean switchTo(String expectedActiveVersion, String targetVersion) {
            PolicySnapshot before = active.get();
            if (!before.version().equals(expectedActiveVersion)) {
                return false; // stale command, active has already changed
            }

            PolicySnapshot target = versions.get(targetVersion);
            if (target == null) {
                throw new IllegalArgumentException("target not staged");
            }
            return active.compareAndSet(before, target);
        }

        static Decision evaluate(PolicySnapshot policy,
                                 Principal principal, Report report) {
            boolean allowed = principal != null
                    && report != null
                    && principal.has("report:read")
                    && (principal.name().equals(report.owner())
                        || (policy.allowReviewerCrossOwner()
                            && principal.has("report:read:any")));

            return new Decision(policy.version(), allowed);
        }
    }

    private static void require(boolean condition, String description) {
        if (!condition) {
            throw new IllegalStateException(description);
        }
    }

    public static void main(String[] args) {
        PolicyRegistry registry = new PolicyRegistry(
                new PolicySnapshot("policy-v1", true));

        Principal owner = new Principal("an", Set.of("report:read"));
        Principal reviewer = new Principal("reviewer",
                Set.of("report:read", "report:read:any"));
        Principal outsider = new Principal("linh", Set.of("report:read"));
        Report own = new Report(101L, "an");
        Report another = new Report(102L, "binh");

        System.out.println("v1 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());

        registry.stage(new PolicySnapshot("policy-v2", false));

        boolean ownerAllowed = registry.preview(
                "policy-v2", owner, own).allowed();
        boolean reviewerDenied = !registry.preview(
                "policy-v2", reviewer, another).allowed();
        boolean outsiderDenied = !registry.preview(
                "policy-v2", outsider, own).allowed();

        require(ownerAllowed && reviewerDenied && outsiderDenied,
                "candidate failed authorization matrix");
        System.out.println("v2 preview: PASS");

        require(registry.switchTo("policy-v1", "policy-v2"),
                "promotion failed");
        System.out.println("promoted: " + registry.activeVersion());
        System.out.println("v2 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());

        // A command created with a stale precondition cannot overwrite the newer active version.
        boolean staleSucceeded = registry.switchTo(
                "policy-v1", "policy-v1");
        require(!staleSucceeded, "stale write unexpectedly succeeded");
        System.out.println("stale activation rejected: "
                + !staleSucceeded);

        require(registry.switchTo("policy-v2", "policy-v1"),
                "rollback failed");
        System.out.println("rolled back: " + registry.activeVersion());
        System.out.println("v1 reviewer cross-owner: "
                + registry.decide(reviewer, another).allowed());
    }
}
~~~

Run with:

~~~bash
javac --release 17 PolicyRolloutDemo.java
java PolicyRolloutDemo
~~~

**Expected stdout** (verified from program logic):

~~~text
v1 reviewer cross-owner: true
v2 preview: PASS
promoted: policy-v2
v2 reviewer cross-owner: false
stale activation rejected: true
rolled back: policy-v1
v1 reviewer cross-owner: true
~~~

What the code genuinely demonstrates:

- Previewing a staged snapshot **does not change active**.
- The same principal and resource yield different outcomes when active switches from `policy-v1` to `policy-v2`.
- `switchTo(expected, target)` uses **compare-and-set**: a command with precondition `policy-v1` is rejected once active is `policy-v2`.
- Rollback **switches the active pointer** back to an existing old snapshot without mutating source rules.
- `Decision` always carries `policyVersion`, which can be emitted to audits/metrics to reproduce decisions.

**Intentional limitations of the example:** the registry is single-JVM in-memory only; it lacks durable snapshot persistence, signatures/digests, deployer authorization, canary routing, event logs, multi-node coordination, and compatibility checks. Those belong to the operational pipeline below. Never use this example as a production policy registry in a multi-instance deployment.

**Security note on rollback:** `policy-v1` in the example is more permissive than `policy-v2`. Rolling back to `v1` is only appropriate when the prior permission scope was already vetted and widening access is approved. If `v1` itself caused a data leak, **never automatically roll back to v1**: switch to a **safer snapshot** (denying sensitive actions) or deploy a newly versioned hotfix.

## 5. Integrating Policy Versions into Spring Security

The Java example in section 4 uses nested classes so it runs from a single file. In a Spring Boot integration, move `PolicyRegistry`, `PolicySnapshot`, and the policy evaluator into appropriate Spring beans and packages. The goal is for **every request to pass through the single active policy source**.

Spring MVC example (integration snippet illustrating the pattern; assumes corresponding interfaces are implemented in your project):

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}

// A Spring-managed service, invoked through its proxy.
@Service
class ReportService {

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public Report read(long reportId) {
        return reportRepository.findById(reportId).orElseThrow();
    }
}
~~~

`#p0` is the first method parameter, independent of compile-time parameter-name retention. `reportPolicy` is a bean reading the snapshot and making the decision:

~~~java
@Component("reportPolicy")
class ReportPolicy {

    private final PolicyRegistry registry;
    private final ReportRepository reports;

    boolean canRead(Authentication authentication, long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Report report = reports.findById(id).orElse(null);
        if (report == null) {
            return false;
        }

        PolicySnapshot snapshot = registry.activeSnapshot();

        // Map GrantedAuthorities and username from Spring Authentication
        // to domain Principal, then evaluate against the pinned snapshot.
        Principal principal = toPrincipal(authentication);
        return PolicyRegistry.evaluate(snapshot, principal, report).allowed();
    }
}
~~~

This is an **architectural snippet**, not a standalone compilable file: constructor/field wiring, `toPrincipal(...)`, domain classes, and repositories must be supplied by the project. Mandatory requirements: obtain `Authentication` from Spring Security rather than a client `isAdmin` field; check resource owner/tenant server-side; and read the snapshot **once** per decision.

The HTTP layer can still use:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
            .authenticated()
        .anyRequest().denyAll()
);
~~~

Here the HTTP rule checks authentication and deny-by-default; **resource-level read rules live in the service**. You can strengthen HTTP authorization with a custom `AuthorizationManager` sharing the same policy source. Avoid duplicating two diverging rule sets across `SecurityFilterChain` and services. `@EnableMethodSecurity` is a Servlet mechanism; WebFlux applications use `@EnableReactiveMethodSecurity` and Reactor Context and must integrate accordingly.

### Pinning a Version Across an Entire Business Operation

Reading the snapshot once per check suffices for a simple example. When a request spans multiple steps (view -> approve -> DB write) and policy can change mid-flight, define consistency explicitly:

- **Pin the verified snapshot** across the transaction/use case, passing the version across trusted service boundaries.
- Or **re-evaluate** at each sensitive action against the new active version if policy requires immediate effect; since steps can see different outcomes, business handling must be designed explicitly.
- Never trust a client-supplied `X-Policy-Version` header to pick a more permissive version. Select versions via **trusted server-side routing/config**; server-emitted headers are for diagnostics only.

During emergency access revocation, rule propagation latency and stale caches/tokens can matter more than "long-pinned" consistency. Define explicit session/token revocation, TTLs, and lifetimes for cached decisions.

## 6. Pre-Activation Verification: Policies Must Pass a Test Matrix

Before flipping the active pointer, run a **representative dataset** through both the active policy and the new candidate. The suite must include positive, negative, cross-tenant, and boundary cases.

Example for `policy-v2` from section 4:

| Principal | Permission | Resource | Expected `policy-v2` | Reason |
| --- | --- | --- | --- | --- |
| `an` | `report:read` | Report 101, owner `an` | ALLOW | Right permission and right owner |
| `an` | `report:read` | Report 102, owner `binh` | DENY | No cross-owner reading |
| `reviewer` | `report:read`, `report:read:any` | Report 102 | DENY | New policy removed reviewer exception |
| `reviewer` | Only `report:read:any` | Report 102 | DENY | Lacks functional read permission |
| Unauthenticated | No authorities | Report 101 | DENY | Anonymous access disallowed |
| `linh` | `report:write` | Report 101 | DENY | Write permission does not imply read |
| `an` | `report:read` | Non-existent resource | DENY/404 | Cannot grant access to missing object |
| Other-tenant user | `report:read` | Out-of-tenant report | DENY | Multi-tenant policy must block cross-tenant access |

The last row with tenants requires extending the domain model and policy beyond the demo Java file; **do not assume it is already tested in the sample code**. Whenever real business rules depend on owner/tenant/status, add matching data and assertions.

Tests should verify **both the outcome and the policy version**: e.g., v1 allows cross-owner reviewer access while v2 denies it; if that delta is approved, tests must confirm all other cases remain unchanged. Do not assert only HTTP `200`; test data leaks, DB side effects, record counts, and active version.

### Four Verification Tiers

1. **Static validation:** JSON/YAML parses cleanly, schema matches version, required fields present, deny-by-default, no duplicate policy ID/version, valid digest/signature, no unintended wildcard widening.
2. **Automated behavior tests:** JUnit/MockMvc/WebTestClient + integration tests under real Spring Security; verify `401`/`403`, object owner, tenant, write permissions, inheritance, routes, and methods.
3. **Compatibility & regression:** policy bundle is compatible with all still-running application builds, IdP role/claim mappings, data formats, DB/cache schemas, and old/new tokens.
4. **Performance & resilience:** benchmark `AuthorizationManager`/method evaluator latency, cache hits/misses, throughput, and failure mode when the policy store is unreachable.

**Shadow evaluation:** keep deciding live requests with the active policy while running the candidate in **observe-only mode**—never use shadow outcomes to grant access or return content to clients. Tally `ALLOW -> DENY` and `DENY -> ALLOW` counts by business category and verify deltas match the changelog. Any `DENY -> ALLOW` shift must be reviewed individually as potential unintended privilege widening. Run shadow evaluations on bounded samples, protect sensitive data, and never replay side effects.

### Example Automated Test Suite for the Registry

If you move the demo Java records/classes into project code with JUnit Jupiter, you can write these assertions; this is a **test snippet** built on section 4's classes, not a second standalone file:

~~~java
@Test
void candidateDoesNotBecomeActiveUntilPromoted() {
    var registry = new PolicyRegistry(
            new PolicySnapshot("v1", true));
    registry.stage(new PolicySnapshot("v2", false));

    assertEquals("v1", registry.activeVersion());
    assertFalse(registry.preview("v2",
            new Principal("reviewer", Set.of("report:read",
                    "report:read:any")),
            new Report(102, "binh")).allowed());
}

@Test
void staleRollbackMustNotOverwriteNewerVersion() {
    var registry = new PolicyRegistry(
            new PolicySnapshot("v1", true));
    registry.stage(new PolicySnapshot("v2", false));

    assertTrue(registry.switchTo("v1", "v2"));
    assertFalse(registry.switchTo("v1", "v1"));
    assertEquals("v2", registry.activeVersion());
}
~~~

In a real project, add tests explicitly rejecting **non-existent versions**, **duplicate versions**, missing roles, anonymous callers, and cross-tenant data access. Test on real `@PreAuthorize`/Spring beans so AOP is never bypassed. Never mock the evaluator itself when the evaluator is what you are testing.

## 7. Phased Rollout: From Canary to Full Cluster

### A. Stage

Push the signed, hash-verified artifact to the trusted policy registry/config store. Retain the previous snapshot for rollback. Instances may preload the candidate without **activating it automatically**.

Verify: applications can read the new version, parse the schema, satisfy dependencies, incur zero evaluation errors, and keep the current active pointer unchanged. Record the approvers and schedule of the rollout plan.

### B. Canary

Enable the new policy first for a small intentional scope (such as internal accounts or 1% of eligible requests), **pinning cohort selection** so one user does not get two different outcomes across consecutive requests. For owner/tenant decisions, canary by deterministic tenant/user rather than random per-request sampling.

Keep a control cohort on the old version; compare allow/deny rates by **business scenario** rather than watching raw `403` totals alone. A legitimate privilege-tightening rollout can intentionally raise `403`s; distinguish *policy-intended* denials from business-breaking denials.

### C. Gradual Expansion and Full Cutover

Once canary passes, expand cohorts in approved increments, then switch 100%. At every step, verify:

- Reported policy version across every instance and every zone/region.
- No traffic routed to an unverified version.
- Decision deltas match the expected matrix; zero out-of-scope `DENY -> ALLOW` transitions.
- Error rate, latency, timeouts, fallbacks, policy evaluator load, and pressure on DB/remote PDP.
- Async jobs, caches, background consumers, and other APIs adopt the same policy after TTL expiry.

**Do not treat "wrote the active pointer" as proof the rollout is complete.** The registry pointer changed, yet nodes may lag in syncing; use `policy_active_version{service,instance,...}` metrics or equivalent reporting. While inconsistent, halt expansion/clear caches and alert. Never put arbitrary user IDs or report IDs as metric labels due to high cardinality; use privacy-protected logs/traces for per-request investigation.

## 8. Selecting Observability Signals, Stop Thresholds, and Completion Criteria

Define before deploying what will make the system **proceed**, **halt**, or **roll back**. Thresholds must fit baselines and be approved by business/SRE/security owners; there is no universal `403` or p95 threshold for all applications.

| Signal | Purpose | Warning Sign to Inspect |
| --- | --- | --- |
| `policy_active_version` per instance | Detect mixed versions | Some instances have not moved to expected version |
| `authorization_decisions_total` by version/action/outcome | Track allow/deny | Deltas outside approved change list |
| `policy_evaluation_duration` p50/p95/p99 | Track performance | Latency spikes from policy lookup/DB/remote PDP |
| `policy_evaluation_errors_total` | Detect broken evaluator | Parse errors, timeouts, exceptions, unknown versions |
| HTTP `401`/`403` by route/cohort | Detect blocked users | Abnormal spikes outside policy intent |
| Business outcome | Confirm workflows remain intact | Failing approval/payment/report-generation rates |
| Audit `policy_switch` | Root-cause investigation | Missing version, actor, timestamp, reason, revision |

**Illustrative threshold examples** (not drop-in standards): halt canary if denials **outside the approved matrix** exceed 0; or if business error rates in canary exceed control by an agreed margin. For privilege-tightening policies, planned 403 increases **are not necessarily errors**; stop conditions must target impacted legitimate subjects.

Every decision can be logged in a structured format like this (**event template**, not real production log data):

~~~json
{
  "event": "authorization_decision",
  "policyId": "report-read",
  "policyVersion": "2026-11-06.2",
  "action": "report.read",
  "resourceType": "report",
  "outcome": "DENY",
  "reasonCode": "NOT_OWNER",
  "rolloutId": "rollout-20261106-a"
}
~~~

Never log raw tokens, passwords, sensitive PII, or resource payloads. `reasonCode` must be produced by real security logic; never use raw exception messages as reason codes. To trace an incident, link decision audits with trace/request IDs per data policy.

## 9. Safe Rollback Procedure

**Policy rollback** differs from code rollback and data recovery. Switching a pointer is usually fast, yet **does not undo** data mutations already processed under the new policy.

### When to Trigger Rollback?

- Unauthorized access / unapproved `DENY -> ALLOW` appears.
- Legitimate business workflows are blocked beyond threshold.
- Policy evaluator errors occur, latency breaches SLO, candidates fail to load, or node versions diverge.
- The candidate is incompatible with running application builds or schemas.

Recommended sequence:

1. **Halt rollout and freeze promotion.** Preserve logs/traces and verify the actual active version; notify operations/security owners per incident procedure.
2. **Pick a safe target.** If the old version caused data exposure, never revert to it simply for convenience; activate a tighter snapshot or temporary protective mode instead.
3. **Execute a conditional switch** with `expectedActiveVersion`/revision so a stale rollback command cannot accidentally overwrite a newer hotfix. Record reason, actor, and target version.
4. **Sync and verify cluster-wide.** Check every node, cache, and job; avoid declaring success from the registry response alone.
5. **Re-run the smoke test matrix.** Verify allowed rights, denied rights, owner/tenant rules, HTTP paths, and affected business flows; watch metrics return to baseline.
6. **Remediate impacts that already occurred.** Policy rollback does not recall sent responses, restore deleted records, or revoke all signed URLs; investigate/audit, revoke tokens/permissions, and restore or compensate where needed.
7. **Keep the faulty version for investigation**, never edit it in place; build a newly versioned fix and pass tests/canary before retrying.

Example conditional switch after verifying `v2` is active:

~~~text
Expected active: policy-v2
Target snapshot: policy-v1
Atomic switch: compare-and-swap(policy-v2 -> policy-v1)
Postcondition: all nodes report policy-v1 and permission matrix PASSES
~~~

This is an **operational description**, not a built-in Spring Security CLI command. Spring Security does not ship a universal "rollback policy" command; each organization's registry/CI/CD/GitOps tooling must implement it.

### Rollback Constraints to Design Up Front

- **Schema/code:** if new rules depend on fields/roles/APIs only newer builds understand, old versions may fail after code/DB migrations. Use backwards-compatible schemas or roll out code first and policy second.
- **Caches/tokens:** permissions may reside in tokens, sessions, or caches; registry rollback does not automatically clear cached data. Maintain clear TTL/invalidation and revocation policies.
- **Multi-region:** regions can receive events at different times; define consistency expectations, last-applied revision reporting, timeouts, and registry-outage behavior.
- **Fail-open:** never permit all traffic on evaluator errors, unknown policy versions, or timeouts. Define vetted fail-closed/safe fallbacks.
- **External side effects:** emails sent, webhooks fired, payments settled, or files downloaded will not vanish upon policy rollback; maintain dedicated remediation runbooks.

## 10. Performance and Reliability When Reading Policies

Requests do not need to call a remote policy registry every time. Typically instances hold an **immutable snapshot** in local memory and receive updates via subscribe/poll; requests read the current active pointer. Still, several concerns must be addressed:

**Latency:** simple authority/owner checks can be very fast, whereas policies hitting a DB/remote PDP on every request affect p95/p99. Benchmark under realistic workloads, set tight timeouts, and avoid N+1 per-resource queries.

**Decision caching:** caching by role while omitting resource ID/tenant/owner can serve stale ALLOWs to the wrong target. Keys must include all permission-relevant context, **policy version**, and trusted principal/tenant, with TTLs and invalidation on permission changes. Never cache ALLOWs indefinitely.

**Consistency:** every request must tie its decision to the exact version used. When requests span multiple services, either pin a verified shared version or have each service log its own version under a clear contract.

**Reading when the registry fails:** never turn policy-fetch failures into `permitAll()`. Keep using an old snapshot **only if** explicitly approved and within its freshness bound; for emergency revocations, sensitive actions may need fail-closed behavior. Monitor `lastSuccessfulPolicyRefresh` and alert past thresholds.

**Cardinality:** metrics should carry version, action, service, and outcome groups; avoid putting per-request `userId`/`resourceId` in metric labels. Use access-controlled logs/traces for per-request debugging.

## 11. Common Deployment Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Editing "v1" in place | Impossible to audit or roll back accurately | Immutable versions, verified digests |
| Tracking version without schema/build | Different parsers misbehave | Compatibility matrix and `schemaVersion` |
| Rolling out to 100% right after unit tests | Real-data failures hit the entire system | Shadow, canary, controlled expansion |
| Rolling back without preconditions | Overwrites newer hotfixes/releases | CAS/ETag/revisions, auditing |
| Watching raw `403` totals only | Confusing intended denials with outages | Compare permission matrices and business outcomes |
| Each node picks "latest" independently | Mixed versions, inconsistent outcomes | Centralized active pointer, per-instance verification |
| Accepting client-sent role/version | Authorization bypass | Server-side trusted `Authentication` and routing |
| Cache lacks `policyVersion`/tenant | Stale ALLOWs after rule changes | Scoped keys, TTLs, and invalidation |
| Policy-fetch failure falls back to `permitAll` | Turns infra outages into vulnerabilities | Fail-closed / vetted safe fallback |
| Reverting policy while forgetting data impacts | Unaddressed side effects | Incident review, revocation, and compensation |
| Ignoring `@PreAuthorize` self-invocation | Some call paths skip enforcement | Test via Spring proxies and real entry points |
| Missing cross-tenant/IDOR tests | New version opens cross-tenant reads | Negative authorization matrix and object checks |

## 12. Deployment Checklist and Completion Criteria

### Before Rollout

- [ ] Artifact has `policyId`, `policyVersion`, `schemaVersion`, hash, and approver; version is immutable.
- [ ] Permission delta is documented (exactly which actors/actions/objects change).
- [ ] Allow/deny, owner/tenant, anonymous, write permissions, and default-deny tests all PASS.
- [ ] Shadow/diff confirms all `ALLOW -> DENY` and `DENY -> ALLOW` shifts are justified.
- [ ] Code, schemas, caches, tokens, and background jobs are compatible with both active and candidate versions.
- [ ] Safe prior snapshot exists, rollback permissions are restricted, and halt thresholds are approved.
- [ ] Metrics and dashboards break down by `policyVersion`, action, service/cohort.

### During Rollout

- [ ] Staging does not auto-activate; active version stays unchanged while checking candidate.
- [ ] Canary uses stable cohorts with a control group.
- [ ] Rollout expands only when safety guards and business KPIs PASS.
- [ ] Zero instances run unknown versions or bad digests.
- [ ] All promotions use conditional revision/CAS and emit audits.

### After Rollout or Rollback

- [ ] All instances/regions confirm the intended active version.
- [ ] Smoke test matrix PASSES against the live version.
- [ ] Denial rates, business errors, and latency stay within defined limits.
- [ ] Caches, async workers, tokens/sessions, and fallbacks verified.
- [ ] Audits capture previous/next version, actor, reason, timestamp, and outcome.
- [ ] If rolled back due to a security incident, exposed/mutated data and remediation are assessed.

## 13. Applied Exercise

Design an `invoice-approve` policy where `v1` lets managers approve invoices under a threshold and `v2` lowers the threshold while requiring matching tenant. Write a matrix of at least eight cases: anonymous, missing authority, right authority/right tenant, wrong tenant, right at threshold, over threshold, already-approved status, and repeated requests. Create an immutable candidate; run preview without touching active; simulate canary, promote with version precondition, then roll back when a valid case is denied. In your report, explain why rolling back does not automatically undo invoices already approved under the newer version.

## References

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP — Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)

**Key takeaway:** A policy change is only finished when permission decisions under the new version are verified, every instance enforces it consistently, and operations knows exactly how to halt and roll back to a safe version.