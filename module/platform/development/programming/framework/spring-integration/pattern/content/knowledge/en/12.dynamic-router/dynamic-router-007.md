# Controlling Permissions to Change Routes

## 1. The Problem: Who Is Allowed to Change a Message's Path?

An integration system processes orders across **Domestic**, **Export**, and **Manual Review** flows. Normally, orders for the Vietnam market go to the domestic team, international orders go to the export team, and orders needing risk checks go through review. During an operational change, an administrator wants to temporarily redirect a market's orders to a different processing branch **without redeploying the application**.

That is a use case for **Dynamic Router** in Enterprise Integration Patterns (EIP): rules determining destinations can be updated while the system is running. That flexibility raises a more serious question than writing a routing expression:

> If any user, producer, or arbitrary service can change a route, could they send messages through an unmonitored branch, bypass checks, or halt business processing?

**Controlling permissions to change routes** means only authorized subjects, within permitted scopes, can create, edit, activate, or restore a routing policy version. Updates must be **validated, recorded, versioned, observable, and recoverable**.

This lesson is in the **Dynamic router** chapter of the **SPRING_INTEGRATION_PATTERN** module, serving the goal of learning how to implement Enterprise Integration Patterns with Spring Integration: building loosely coupled, extensible message flows with **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing each branch. Here, route-modification permissions are the focus; we never treat an externally supplied header as permission to alter topology.

After this lesson, you will be able to distinguish the **data plane** and **control plane**, design RBAC/ABAC for route changes, constrain destinations with allowlists, perform version-controlled policy updates, separate permission errors from routing errors, and test attack or update-contention scenarios.

## 2. What Does a Dynamic Router Actually Change?

An ordinary Router reads message data and computes a **routing key**. In a Dynamic Router, the key-generation rules, mapping table, or recipient list can change over time.

For example:

| Time | Active policy | Result for `market="SG"` |
|---|---|---|
| 09:00 | Only VN/US supported | `UNSUPPORTED → orders.unmapped` |
| 09:10 | Approved policy adding SG | `EXPORT → orders.export` |
| 09:30 | Export branch incident; fallback activated | `REVIEW → orders.review` |
| 10:00 | Tested policy restored | `EXPORT → orders.export` |

Note that changing routes does not necessarily mean creating new channels/beans at runtime. A **safer and simpler** approach is keeping topology and destination channels stable, and changing only **the rules selecting among allowed routes**.

| Change type | Impact | Risk |
|---|---|---|
| Changing predicate/threshold | A group of messages may take a different branch | Bypassing review due to faulty logic |
| Changing routing key → channel table | A key's destination changes | Pointing to the wrong channel or missing consumer |
| Adding/removing a Recipient List Router recipient | Number of receivers per message changes | Dropping a mandatory branch or leaking data |
| Dynamically creating/deleting endpoints, flows, channels | Bean topology and lifecycle change | Misconfiguration, overly broad system control |

**Priority principle:** permission to change a rule does not equal permission to create arbitrary targets or skip mandatory checks. Grant only least-privilege access for the exact change type the business requires.

## 3. Separating the Data Plane and Control Plane

The **data plane** receives and routes business messages. The **control plane** accepts policy change requests, authenticates/authorizes, approves, and rolls out new route versions.

~~~mermaid
flowchart TB
    subgraph CONTROL["CONTROL PLANE — change policy"]
        USER["Route operator / admin"] --> API["Admin API / workflow"]
        API --> AUTH{"Authentication + authorization"}
        AUTH -->|"Deny"| DENY["403 / audit denied"]
        AUTH -->|"Allow"| VAL["Validate + approve"]
        VAL --> STORE["Versioned policy store"]
        STORE --> PUB["Publish approved revision"]
    end
    subgraph DATA["DATA PLANE — process events"]
        IN["Gateway / broker adapter"] --> FILTER["Contract validation"]
        FILTER --> ROUTER{"Dynamic Router<br/>read active snapshot"}
        ROUTER --> DOM["orders.domestic"]
        ROUTER --> EXP["orders.export"]
        ROUTER --> REV["orders.review"]
        ROUTER --> UNK["orders.unmapped"]
    end
    PUB -.->|"Approved versions only"| ROUTER
~~~

Two message kinds must never be conflated:

- `OrderCreated` is **data** for the Router to evaluate under the active rules.
- `RoutePolicyChange` is an **administrative command** changing the rules; only a trusted management service may apply it.

A producer sending `headers['routeKey'] = 'orders.review'` or `headers['isAdmin'] = true` **does not become an administrator**. Those values are merely producer-supplied data and cannot replace an authenticated principal and server-side authorization decisions.

Do not let route changes share a public input channel with business events without a separate authentication/authorization boundary. Separating the control plane also allows recording and restoring configurations independently of order traffic volume.

## 4. Permissions That Must Be Distinguished

Do not have only one omnipotent `ADMIN` role. A system can split permissions by function:

| Action | Reader | Operator | Approver | Route Administrator |
|---|---:|---:|---:|---:|
| View running version and change history | Yes (in scope) | Yes | Yes | Yes |
| Preview impact of a change | Yes | Yes | Yes | Yes |
| Create change proposal | No | Yes | Yes | Yes |
| Approve proposal | No | No | Yes | Per policy |
| Activate approved version | No | Per workflow | Per workflow | Yes |
| Roll back a version | No | Propose | Approve | Yes, audited |
| Change topology or sensitive channels | No | No | Not by default | Only after special controls |

This is an **illustrative matrix**, not a built-in Spring Integration role model. Enterprises may require **separation of duties**: the proposer must not be the approver, especially for payment, identity, or personal-data routes.

Beyond roles, enforce **attribute-based** policies (ABAC):

- Users may only edit policies for tenants/units they administer.
- Certain destinations are restricted to staging/test environments.
- Rules for high-risk transactions require extra approval, even when the editor holds the right role.
- Validity windows, rollout scale, and affected market counts can be bounded.
- Command permissions must derive from trusted identity, not solely from a `tenantId` in the request body.

## 5. Threat Model: What If Anyone Could Change Routes?

| Scenario | Consequence | Mitigation |
|---|---|---|
| Producer spoofs admin header | Unauthorized branch switching | Never grant mutation from data headers; enforce identity on control plane |
| API accepts arbitrary channel names | Bypasses validation, sends messages to sensitive handlers | Fixed allowlist of routing keys and destinations |
| Control Bus exposed externally | Unintended bean method calls/mutations via expressions | Never expose arbitrarily; restrict operational permissions |
| Tenant A operator edits Tenant B's policy | Data mixing or isolation breach | Resource-level authorization / tenant isolation |
| Two admins edit concurrently | Later update overwrites earlier one | Version/ETag, optimistic concurrency |
| Admin command is replayed | Old rules return or changes repeat | Command ID, version, auditing, expiration |
| New config lacks a consumer | Messages stuck or fail to send | Validate topology + canary test before activation |
| One node runs a different revision than another | Same event takes different routes | Versioned snapshots, sync, and rollout monitoring |

The most significant risk is not just **failing to deliver messages**, but **successfully delivering them to an unauthorized branch**. Therefore, a project must review security invariants, such as "every payment command must pass risk screening" and "no tenant may ever route to another tenant's data store."

## 6. Define the Change Contract Before Writing the API

Let operators submit **business intent** rather than bean-manipulation commands:

~~~json
{
  "policyId": "order-market-routing",
  "expectedVersion": 12,
  "changeId": "CHG-2026-0102",
  "reason": "Temporary export maintenance",
  "rules": {
    "VN": "DOMESTIC",
    "US": "EXPORT",
    "SG": "REVIEW"
  }
}
~~~

**Do not accept** payloads shaped like:

~~~json
{
  "expression": "T(java.lang.Runtime).getRuntime()...",
  "targetBeanName": "anySpringBean",
  "method": "invokeArbitraryOperation"
}
~~~

The second snippet is solely **an example of a request shape that must be rejected**, not syntax to execute. A route-change API should accept **a policy identifier, expected revision, structured key/value map, reason, and command ID**. Never let clients upload arbitrary SpEL, free-form bean names, Java code, or Control Bus statements.

Even when an operator is authorized to edit configs, **the set of destinations** may still be locked to `DOMESTIC`, `EXPORT`, `REVIEW`. Adding routes to a brand-new endpoint requires a separate process that verifies handlers, permissions, and data contracts.

## 7. Allowlists and Business Invariants

A sound policy checks **both syntax and semantics**. For example:

- Market keys must be normalized (uppercase), bounded in length, and non-blank.
- Route keys must belong to the published set: `DOMESTIC`, `EXPORT`, `REVIEW`.
- Never allow pointing to arbitrary channels via strings from requests.
- Never allow deleting all destinations or disabling the last-resort safe branch.
- Sensitive events must pass mandatory checks **outside the freely configurable zone**.
- Configurations must have ready target consumers, metrics, and error handling.

Pure Java validator example:

~~~java
public final class RouteRuleValidator {

    private static final Set<String> ALLOWED_ROUTES =
        Set.of("DOMESTIC", "EXPORT", "REVIEW");

    public void validate(Map<String, String> proposed) {
        if (proposed == null || proposed.isEmpty()
                || proposed.size() > 32) {
            throw new IllegalArgumentException("Invalid policy size");
        }
        for (var entry : proposed.entrySet()) {
            String market = entry.getKey();
            String route = entry.getValue();
            if (market == null
                    || !market.matches("[A-Z]{2}")
                    || !ALLOWED_ROUTES.contains(route)) {
                throw new IllegalArgumentException(
                    "Invalid market or route key");
            }
        }
    }
}
~~~

**Validation does not replace authorization.** A rule `SG → REVIEW` may be schema-valid while the current operator lacks permission to edit the SG market. Conversely, even a full Route Administrator must not insert arbitrary channel names if doing so violates technical invariants.

**Protect risk-screening paths:** if every high-value order must go through Manual Review, place the risk Filter/Router or mandatory policy **before** the region where operators can edit mappings. Market changes must never bypass this check.

## 8. Immutable Versioned Model for Runtime Policy

A simple option within **one JVM** is keeping an immutable snapshot and replacing it with an atomic operation. This is a form of dynamic routing that **updates policy data** without creating/deleting Spring beans at runtime.

~~~java
public record RouteSnapshot(
    long version,
    Map<String, String> marketToRoute
) {
    public RouteSnapshot {
        marketToRoute = Map.copyOf(marketToRoute);
    }
}

public record OrderCreated(
    String eventId,
    String market,
    long amount
) {}

public final class VersionedRoutePolicy {
    private final AtomicReference<RouteSnapshot> active =
        new AtomicReference<>(new RouteSnapshot(
            1L, Map.of(
                "VN", "DOMESTIC",
                "US", "EXPORT"
            )));

    public RouteSnapshot snapshot() {
        return active.get();
    }

    public String resolve(OrderCreated event) {
        if (event.market() == null || event.market().isBlank()) {
            return "INVALID";
        }
        String market =
            event.market().trim().toUpperCase(Locale.ROOT);
        RouteSnapshot snapshot = active.get();
        return snapshot.marketToRoute()
            .getOrDefault(market, "UNSUPPORTED");
    }

    // Call only after authentication, authorization, validation,
    // approval, and coordination with durable configuration storage.
    public boolean replaceExpectedVersion(
            long expectedVersion,
            Map<String, String> newRules) {
        RouteSnapshot old = active.get();
        if (old.version() != expectedVersion) {
            return false;
        }
        RouteSnapshot updated =
            new RouteSnapshot(old.version() + 1, newRules);
        return active.compareAndSet(old, updated);
    }
}
~~~

**Key properties:**

1. `Map.copyOf` prevents callers from mutating the map used as a snapshot (though it does not check permissions or key validity on its own).
2. `AtomicReference` ensures a single `resolve` call sees one consistent version within the same process.
3. `compareAndSet` prevents two concurrent updates from silently overwriting each other on **the same instance**; callers must treat a `false` return as a conflict.
4. `resolve()` is read-only; it causes no side effects and makes no network calls.
5. `replaceExpectedVersion()` is an **internal** operation, not an API exposed directly to users.

This is an **illustrative in-memory model**, not a complete policy management system. It **does not** provide persistence, authorization, audit logs, approvals, database transactions, or cross-instance synchronization. In production, a control plane must own those steps.

## 9. Using Dynamic Policy Inside Spring Integration Java DSL

Keep channel mappings **fixed** in the application while the key-computation function reads the active policy version:

~~~java
@Configuration
@EnableIntegration
class DynamicOrderRoutingFlow {

    @Bean
    VersionedRoutePolicy versionedRoutePolicy() {
        return new VersionedRoutePolicy();
    }

    @Bean
    IntegrationFlow routeOrders(VersionedRoutePolicy policy) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderCreated.class,
                event -> event.eventId() != null
                    && !event.eventId().isBlank(),
                f -> f.discardChannel("orders.invalid"))
            .route(OrderCreated.class, policy::resolve,
                r -> r.channelMapping("DOMESTIC", "orders.domestic")
                      .channelMapping("EXPORT", "orders.export")
                      .channelMapping("REVIEW", "orders.review")
                      .channelMapping("INVALID", "orders.invalid")
                      .channelMapping("UNSUPPORTED", "orders.unmapped")
                      .defaultOutputChannel("orders.unclassified"))
            .get();
    }
}
~~~

This example uses Java 17+ and Java DSL; imports are omitted. Real handlers/consumers must exist for each target channel. **Updating `marketToRoute` can switch the branch for subsequent messages**, but only within the keys mapped in the Java DSL. If the policy returns an unmapped key, the message follows the configured default behavior; verify fallback behavior against your exact Spring Integration version.

This is a practical choice when the requirement is "change branch-selection rules" rather than "load new beans at runtime." For the same event processed at two different times, the route may differ because the policy version changed; decide whether replays use the **historical revision** or the current policy.

## 10. Change Workflow: From Proposal to Activation

An API that merely checks roles at the entry point is not enough. The change workflow should be modeled explicitly:

~~~mermaid
flowchart TD
    REQ["Propose route change"] --> ID["Authenticate actor + tenant scope"]
    ID -->|"Unauthorized"| NO["Reject + audit denied"]
    ID -->|"Authorized"| VA["Validate schema + allowlist + invariant"]
    VA -->|"Invalid"| ERR["Reject + reason code"]
    VA -->|"Valid"| PRE["Preview / impact analysis"]
    PRE --> APPROVE{"Approval required?"}
    APPROVE -->|"Yes"| PENDING["Wait for independent approver"]
    PENDING --> ACT["Activate approved revision"]
    APPROVE -->|"No"| ACT
    ACT --> CAS{"expectedVersion still matches?"}
    CAS -->|"No"| CONFLICT["409 conflict, re-read revision"]
    CAS -->|"Yes"| SAVE["Persist revision + immutable audit"]
    SAVE --> DEPLOY["Distribute approved snapshot"]
    DEPLOY --> OBS["Canary + metrics + rollback trigger"]
~~~

In production, **persist/activate ordering and atomicity** must be clearly defined. If the DB commits while a node has not refreshed its cache, or the cache updates before auditing is written, replicas can drift. Use database transactions for source state, event/outbox to emit revisions, and reconciliation to achieve convergence step by step. A single `AtomicReference.compareAndSet` **does not solve** those distributed concerns.

Every request needs:

- Specific `policyId` and resource scope.
- `expectedVersion` to reject updates based on stale state.
- `changeId` to prevent processing the same command multiple times.
- System-authenticated actor identity; never trust client-declared `updatedBy`.
- Reason, ticket/approval reference, and before/after diff.
- Optional per requirements: activation timestamp, rollout percentage, and temporary-route TTL.

Transitioning a policy through **PENDING/APPROVED/ACTIVE/REVERTED** belongs on the control plane, never in headers mutable by ordinary business messages.

## 11. Spring Security: Roles Are Necessary, Not Sufficient

A Spring Boot application can protect route-change actions using endpoint security and **method security**. Illustrative example:

~~~java
@Configuration
@EnableMethodSecurity
class RouteMethodSecurityConfiguration {
}

@Service
class RouteAdminService {
    private final RouteAuthorization authorization;
    private final RoutePolicyRepository repository;

    RouteAdminService(RouteAuthorization authorization,
                      RoutePolicyRepository repository) {
        this.authorization = authorization;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ROUTE_POLICY_WRITE')")
    public void propose(RouteChangeRequest change,
                        Authentication actor) {
        if (!authorization.canEdit(
                actor, change.policyId(), change.tenantId())) {
            throw new AccessDeniedException(
                "No permission for requested policy scope");
        }
        // Validator and approval workflow run before activation.
        repository.saveProposal(change, actor.getName());
    }
}
~~~

`RouteAuthorization`, `RoutePolicyRepository`, and `RouteChangeRequest` here are **application-defined abstractions**, not built-in Spring Integration APIs. In real implementations, validate thoroughly before saving proposals and ensure actor details come from the **authenticated security context**. Never let clients pass arbitrary `Authentication` objects across remote APIs.

**Pay close attention to Spring proxies:** `@PreAuthorize` only takes effect when method security is enabled and calls go through the Spring-managed proxy; self-invocation via `this.propose(...)` can bypass interception. Therefore, never rely solely on annotations for critical invariants: enforce resource authorization and validation at the **true boundary** of administrative commands.

If an HTTP admin API exists, protect it with strong authentication and network restrictions; enable CSRF protection when using cookies/sessions, TLS, rate limiting, audit logging, idempotency controls, and forbid arbitrary execution directives in request bodies.

## 12. Control Bus Is Powerful: Do Not Turn It into a Public Route-Editing Endpoint

Spring Integration provides **Control Bus** to send control commands to integration components, often using expressions/messages. It is a broad operational tool capable of invoking endpoints/beans as permitted by configuration.

**Never connect Control Bus directly to user-facing HTTP/Kafka inputs**, and never treat a `role=admin` header as authorization. If clients can submit expressions to Control Bus, an authorization bug can expose many components beyond the Router.

When runtime administration is needed:

1. Use a **dedicated Admin API** with a fixed command schema, accepting no free-form SpEL.
2. Use an authenticated backend service to validate allowed changes.
3. Restrict accessible mutators and beans; prefer policy data updates over arbitrary Spring context manipulation.
4. Separate administrative paths from event-processing paths; use separate networks/identities where warranted.
5. Audit all changes, including denied attempts; monitor anomalous mutations.

Permission to **control an endpoint** is not the same as permission to **update a single business rule**. Granting access to Control Bus requires much stricter caution than updating the market-to-route table in our example.

## 13. Never Let Business Messages Carry Policy-Update Privileges

Suppose a producer sends:

~~~text
payload: OrderCreated(eventId="E-10", market="VN", amount=100)
headers:
  tenantId: tenant-B
  routeKey: orders.privileged
  changePolicy: true
  routeVersion: 9999
~~~

Those headers **do not prove** the producer has admin rights, may pick destinations, may switch tenant scopes, or may update revisions. The data plane must treat them as untrusted inputs, except metadata verified at the adapter or derived from a trusted identity.

To protect the flow:

- Restrict inbound header mappers to essential metadata only.
- Prevent producers from overwriting critical control headers or internal channel names.
- Derive `tenantId` from verified claims or authenticated message bindings, not raw headers.
- Have the Router use only `RouteSnapshot` objects approved by the control plane.
- If tenant-specific dynamic routing is needed, key mappings by `tenant + policyId` with strict authorization and data isolation.

**A valid route key can still be an unauthorized route for a given tenant.** Destination allowlists prevent route injection, but do not replace resource-level authorization.

## 14. Multi-Tenant: Route Changes Must Be Scoped

Suppose Tenant A wants VN traffic routed to REVIEW for one hour. A global `Map<market, route>` policy would affect all tenants, including Tenant B. If the product requires tenant isolation, use **scoped policy keys**, such as:

~~~text
policyKey = tenantId + ":" + policyId

tenant-A:order-market-routing → revision 24
tenant-B:order-market-routing → revision 9
~~~

Add these controls:

| Boundary | Rule |
|---|---|
| Tenant identity | Obtained from authentication source or verified data |
| Edit permission | Actor must administer the exact tenant and policy |
| Read permission | History and previews must also protect sensitive data |
| Default configuration | Explicitly define whether a global fallback applies |
| Activation scope | Affects only the target tenant; can canary on a small subset |
| Audit | Log tenant, policy ID, before/after revisions, principal, and reason |

Never treat `tenantId` in a URL/body as proof that the actor is authorized to edit that tenant. Compare it against server-verified permissions. In multi-cluster setups, revisions must also be scoped so "Tenant A version 24" is never confused with Tenant B's revision.

## 15. Update Contention and Multi-Node Consistency

Suppose two operators read policy version 12:

~~~text
Operator A: add SG → EXPORT, expectedVersion=12
Operator B: change US → REVIEW, expectedVersion=12

A writes version 13: succeeds
B writes with expectedVersion=12: must receive CONFLICT
~~~

If both commands are accepted without version checks, the second write can erase the first (**lost update**). Optimistic concurrency forces B to re-read version 13, inspect the diff, and propose version 14.

Across multiple instances:

~~~mermaid
flowchart LR
    STORE["Policy store v13"] --> EVT["Revision event"]
    EVT --> A["Instance A active v13"]
    EVT --> B["Instance B active v12"]
    EVT --> C["Instance C active v13"]
    B --> RECON["Reconcile / catch up"]
    RECON --> B2["Instance B active v13"]
~~~

**`AtomicReference` only guarantees operations within one JVM**. It does not make all instances switch versions simultaneously. Enforce appropriate consistency rules: store canonical revisions in a DB, publish numbered updates, ignore stale events, fetch full snapshots after missed events, and monitor instances still running older versions.

Two common models:

1. **Per-instance snapshot cache:** high performance; tolerates a multi-version transition window and must measure skew.
2. **Centralized routing decision:** nodes call a shared decision service/policy store to read revisions; easier consistency management, at the cost of extra latency and availability dependency.

Never claim "routes update instantaneously on every node" if the actual distribution mechanism is asynchronous. When exact cutovers are required, design barriers, draining, or version pinning for messages emitted during the transition window.

## 16. Which Version Should In-Flight Messages Follow?

An order may have passed **Filter → Transformer → Router**, with **Splitter → Aggregator → Gateway reply** still ahead. If the revision changes while the message is moving:

- **Route at decision time:** each traversal through the Router reads the current snapshot; retries of the same event may pick a different branch.
- **Pinned policy version:** record the revision in trusted context or process state; retries/replays use the exact historical rule.
- **Migration policy:** in-flight items are transitioned using controlled migration rules rather than silently applying the new policy.

For example, an invoice started validation under revision 12, then revision 13 switched branches. If a retry from the beginning takes the other branch, inconsistent side effects can occur. Define **replay/retry semantics** and preserve event IDs/correlation per contract.

**Beware of version headers:** a producer could spoof `policyVersion`. If pinning is needed, the orchestration system must set or validate the value at ingress; the routing point must verify the version is still valid and permitted within the tenant's scope.

## 17. Auditing, Approvals, and Rollback

A change history entry may need these fields:

~~~json
{
  "changeId": "CHG-2026-0102",
  "policyId": "order-market-routing",
  "tenantId": "tenant-A",
  "oldVersion": 12,
  "newVersion": 13,
  "actorId": "authenticated-principal",
  "approvalId": "APR-204",
  "reason": "Maintenance window",
  "before": {"SG": "UNSUPPORTED"},
  "after": {"SG": "REVIEW"},
  "outcome": "ACTIVATED"
}
~~~

In production, `actorId` must come from a verified session/token, and `approvalId` must reference an actual approval decision. Avoid logging payloads containing customer data or tokens. Audit logs must be tamper-resistant, retained per policy, and queryable by policy/revision/time window.

**Rollback is a newly recorded change**, never silently erasing history. For example:

~~~text
version 12: SG → UNSUPPORTED
version 13: SG → REVIEW        (temporary change)
version 14: SG → UNSUPPORTED  (rollback with reason + audit)
~~~

Rollback cannot "revert" messages already processed or side effects already committed under revision 13. If a bad route modified data, a separate remediation/compensation workflow is needed.

For high-impact rules, enforce **two-person approval, canary rollouts, auto-expiring TTLs, and automated rollback triggers** based on error rates or anomalous routing ratios.

## 18. When a Route Change Causes Errors: Fail-Safe and Recovery

An update can pass schema validation yet fail at runtime: target channel has no consumer, handler is overloaded, a dependency disconnects, or the rule version is incompatible with newer payloads.

| Failure type | Action to take |
|---|---|
| Unauthorized actor | Return 403; audit denial; do not alter active revision |
| Invalid request schema/rules | Return validation error; keep old revision |
| Stale expected version | Return conflict; do not overwrite |
| Target channel not ready | Block activation or roll back after canary |
| Consumer slow/overloaded | Apply backpressure, appropriate queues/circuit breakers |
| Router runtime exception | Error channel/exception path matching channel type |
| Partial multi-node update | Reconcile; track version skew |
| Revision causes business divergence | Audited rollback and inspect committed side effects |

**Default output channel** helps handle unmapped routing keys, **but it is neither an authorization mechanism nor a catch-all for exceptions**. Invalid rules must be rejected **before activation**, rather than allowed through on the assumption that the default branch will safely absorb failures.

Configuration errors should generally not be retried endlessly across every event. If some messages took a bad route, preserve `eventId`, `policyVersion`, and the actual decision so they can be reconciled, selectively replayed, or compensated.

## 19. Testing Permissions, Concurrency, and Routing

Test across three layers rather than just sending one message and checking the final handler:

### Unit Tests for Validator and Snapshot

~~~java
@Test
void disallowsUnknownChannelKeys() {
    RouteRuleValidator validator = new RouteRuleValidator();

    assertThrows(IllegalArgumentException.class,
        () -> validator.validate(Map.of(
            "VN", "orders.privileged")));
}

@Test
void preventsStaleVersionOverwrite() {
    VersionedRoutePolicy policy = new VersionedRoutePolicy();

    assertTrue(policy.replaceExpectedVersion(
        1L, Map.of("VN", "REVIEW", "US", "EXPORT")));
    assertFalse(policy.replaceExpectedVersion(
        1L, Map.of("VN", "DOMESTIC", "US", "REVIEW")));
    assertEquals(2L, policy.snapshot().version());
}
~~~

The second test only verifies CAS behavior on one instance; for real concurrency testing, launch two concurrent update tasks with the same `expectedVersion` and verify **only one succeeds** with no partially mutated snapshot. Never rely on `Thread.sleep` to force collisions; use latches/barriers in tests.

### Security Tests for the Control Plane

| Case | Expectation |
|---|---|
| Unauthenticated call to admin API | Denied; revision unchanged |
| Reader role attempts route edit | 403 or equivalent access denied |
| Tenant A operator edits Tenant B policy | Denied at resource scope |
| Client sends arbitrary bean/channel name | Rejected by validation |
| Client declares `isAdmin=true` in header | Has no effect on authorization |
| Caller sends SpEL/Control Bus command | No endpoint allows arbitrary execution |
| Proposer self-approves when SoD is required | Denied |
| Re-submit same `changeId` | No duplicate activation; idempotent result |
| Stale `expectedVersion` supplied | Conflict, no lost update |
| Unauthorized rollback | Denied and audited |

To prove `@PreAuthorize` works, tests must invoke the service **through the Spring proxy** inside a test context with method security enabled. Directly unit-testing `new RouteAdminService(...)` does not verify annotation interception.

### Integration Tests for Post-Activation Routing

In Spring Integration tests, replace production consumers on `orders.domestic`, `orders.export`, and `orders.review` with corresponding `QueueChannel` beans. Send messages to `orders.in` and verify which channel is chosen:

| Input | Revision | Expected outcome |
|---|---|---|
| Market VN | v1 | `orders.domestic` |
| Market SG | v1 | `orders.unmapped` |
| Market SG | v2: SG → EXPORT | `orders.export` |
| Market VN | v3: VN → REVIEW | `orders.review` |
| Blank market | Any | `orders.invalid` |
| Missing Event ID | Any | Filtered out; never routed to business branches |
| Two parallel requests | Same `expectedVersion` | One activation succeeds, one gets conflict |
| In-flight message during revision swap | Before/after activation | Matches documented consistency semantics |
| One node has not updated revision | vN/vN+1 | Version skew metric and reconciliation operate |

When branches use retries, add tests sending the same `eventId` multiple times to ensure handlers do not produce duplicate side effects. When using Splitter/Aggregator, verify `correlationId` and policy version are preserved per contract; never use retries to mask route configuration bugs.

## 20. Observability and Detecting Anomalous Changes

A route change should produce a complete traceability chain:

~~~text
Admin principal → changeId → approvalId → newVersion
     → instance activation → routing decision → handler outcome
~~~

Monitor:

| Metric / log | Meaning |
|---|---|
| Change requests by outcome | Are many changes being denied or failing validation? |
| Active revision per instance | Have all nodes converged on the same version? |
| Selected route key and destination | Is traffic shifting as expected? |
| `UNSUPPORTED` and default-route rate | Are inputs arriving that the policy does not yet cover? |
| Errors and latency per destination | Is the new revision causing overload or failures? |
| Rollback / canary abort count | Are policy changes frequently causing incidents? |
| Retry, error channel, DLQ | Are messages being reprocessed or held in failure queues? |
| Correlation/event ID in traces | Can routing decisions be linked to business outcomes? |

Never use `eventId`, dynamic `tenantId`, or unbounded raw channel names as metric tags because they cause **high cardinality** and potential data exposure. Use bounded labels; keep per-entity details in access-controlled traces/logs.

During incident investigation, look up **the revision actually applied to each message**, not merely whichever revision is active at inspection time. A message may have passed through the Router before a rollback was activated.

## 21. Hands-On Exercise: Controlled Route Changes

Build a **DynamicOrderRouter** with Spring Integration:

1. **Data plane:** `OrderCreated → Filter → Dynamic Router → Domestic/Export/Review/Unmapped`.
2. **Policy:** `VersionedRoutePolicy` with immutable snapshots, `expectedVersion`, and key allowlist.
3. **Control plane:** Admin API accepting only policy ID, scope, revision, key→route map, reason, and change ID; rejecting bean names or SpEL.
4. **Security:** readers cannot edit, operators only propose, approvers approve; Tenant A cannot modify Tenant B.
5. **Preview:** simulate at least 10 sample events before/after a revision; confirm mandatory checks are never bypassed.
6. **Activation:** update versions via CAS/optimistic concurrency; write audits and support rollback as a new revision.
7. **Capacity:** shift a percentage of traffic to REVIEW, measure queue/latency, and test automated rollback when error rates exceed a threshold.
8. **Multi-instance:** simulate one node receiving updates late; test version skew, reconciliation, and semantics for messages straddling two revisions.
9. **Testing:** unit tests for validator/CAS, security tests, routing integration tests, retry/idempotency, and correlation with Gateway/Splitter/Aggregator as needed.

**Completion criteria:** an unauthorized operator cannot change the active policy; only allowed route keys can appear; concurrent updates cannot silently overwrite each other; every revision has an audit trail; every message is explainable by its applied policy version; and rollouts/rollbacks have observable metrics.

## 22. Common Misconceptions

**"Having the ADMIN role is enough."** No. You need resource/tenant-scoped authorization, separation of duties, rule validation, and version tracking.

**"The producer header has `changePolicy=true`, so allow the update."** Wrong. Business headers cannot substitute for control-plane identity or permissions.

**"A Dynamic Router must accept arbitrary channel names to be flexible."** No. Updating a bounded key→route table typically satisfies requirements with far lower risk.

**"An immutable map means the configuration is durable."** Wrong. `Map.copyOf` and `AtomicReference` do not persist to a database, write audits, or sync across nodes.

**"One successful update means every node immediately uses the new revision."** False under asynchronous distribution. You need version-skew observability and convergence mechanisms.

**"Rollback puts all messages back into their old state."** Wrong. Messages that already passed through the new route and committed side effects need separate business remediation.

**"Default channel can substitute for authorization."** Wrong. Fallback only handles keys without a matching route; unauthorized rules must be rejected prior to activation.

**"Testing the happy path is enough."** Wrong. The most critical tests cover unauthorized changes, tenant isolation, race conditions, replays, stale revisions, and downstream consumer impacts.

## 23. Key Takeaways

**Controlling permissions to change routes** means securing the **control plane** of a Dynamic Router. A safe design requires *authentication, scoped authorization, destination allowlists, invariant validation, approvals where needed, versioning/CAS, auditing, rollback, and revision-distribution monitoring*. Business messages may only **read** a validly activated policy; producers must never turn headers into administrative commands.

In Spring Integration, you can keep the Router and channels fixed while updating **routing policy snapshots** through a controlled management service. Combined with **Filter, Transformer, Gateway, Splitter, Aggregator, retry, error channel, and correlation**, this approach lets flows adapt flexibly without sacrificing security, consistency, or testability in a distributed integration system.
