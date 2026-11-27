# Feature Flags, Dark Launches, and Release Control

## Learning Objectives

In cloud systems, deploying a software version to production does not mean immediately enabling every new capability for all users. A deployment can ship new code while its behavior remains governed by runtime configuration. This allows teams to decouple technical deployment from feature exposure, test within a narrow blast radius, reduce risk, and respond quickly when problems arise.

A **feature flag** is a mechanism that controls a software behavior branch via configuration or runtime evaluation. A **dark launch** deploys new code or processing paths into production without exposing new results to users or shifting primary handling to the new feature yet. **Release control** encompasses the processes, policies, and telemetry that decide who receives which capability, when, and under what conditions.

These techniques support progressive delivery, canary releases, experimentation, and rollbacks. However, flags do not automatically make a system safe: misconfigured targeting rules can expose features to the wrong tenant, stale flags add branching complexity, dark launches can double load or side effects, and code rollbacks may be incompatible with new schemas.

This lesson belongs to the **Software Delivery** chapter, focusing on **feature flags, dark launches, and release control**. In Cloud Architecture, releases must align with business requirements, compute, networking, data, deployment models, security, scalability, cost, and operations; decisions are evaluated through a Well-Architected lens.

After this lesson, you will be able to:

- Distinguish between deploy, release, feature enablement, and rollback.
- Explain feature flag types and flag lifecycles.
- Design safe dark launches for read paths, write paths, and background processing.
- Construct targeting rules by environment, tenant, cohort, region, or authorized user attributes.
- Execute progressive rollouts by percentage and controlled cohorts.
- Coordinate feature flags with canary, blue/green, rolling deployments, and schema migrations.
- Design kill switches, fallbacks, and rollbacks without violating business invariants.
- Measure adoption, latency, errors, conversion, resource cost, and side effects.
- Protect flag configurations with authorization, auditing, approvals, and secret handling.
- Manage flag debt, owners, expiration dates, and cleanup processes.
- Build release checklists, runbooks, and halt/expand rollout criteria.
- Evaluate the risks and costs of feature management in cloud environments.

## 1. How Does Deploy Differ from Release?

**Deploying** means placing an artifact or software configuration into a running environment. **Releasing** means making a capability available to users or downstream systems. The two moments may coincide, but they do not have to.

For example, a new Booking API version contains two pricing algorithms: legacy and new. The new code is deployed across all of production, while the `pricing_v2_enabled` flag remains off. After internal verification, the team enables the flag for employees, then 1% of tenants, and then expands gradually. If metrics degrade, disabling the flag reverts to the legacy algorithm while the artifact keeps running.

| Concept | Question | Action |
| --- | --- | --- |
| Build | Which artifact is produced? | Compile, package, sign |
| Deploy | Where does the artifact run? | Roll out workload/container/function |
| Enablement | For whom is the new behavior enabled? | Evaluate feature flag |
| Release | Can users consume the capability? | Open access by plan/cohort |
| Rollback | How do we restore prior behavior/version? | Disable flag, shift traffic, or deploy prior artifact |
| Retirement | When do we remove old code/flags? | Clean up after migration completes |

### 1.1. Why Decouple Deploy from Release?

Decoupling allows deploying code ahead of marketing or business announcements; validating runtime behavior in production with low exposure; toggling features rapidly without rebuilding images; rolling out by tenant, region, plan tier, or cohort; reducing risk for major changes; and executing phased migrations when code and data schemas require multi-version compatibility.

However, toggling a flag is still a production change. It requires authorization, auditing, validation, and a rollback plan just like a deployment.

## 2. What Is a Feature Flag?

A feature flag is a runtime decision controlling whether a code branch executes or a capability is unlocked. Flags can be stored in a config service, feature management platform, database, config file, or internal control plane.

~~~mermaid
flowchart TD
    R["Incoming request"] --> C["Resolve trusted context"]
    C --> E["Evaluate feature flag"]
    E -->|Enabled| N["New implementation"]
    E -->|Disabled| O["Existing implementation"]
    N --> M["Record outcome/metrics"]
    O --> M
    M --> RSP["Response"]
~~~

A flag typically carries a stable key/name, description and purpose, flag type and default value, owner/team, environment scope, targeting rules, start date and expiration/removal date, risk level and approval requirements, audit history, linked metrics or experiments, and fallback behavior if the flag service is unavailable.

Flags can be evaluated on the client, gateway, service, or worker. Evaluation placement determines security, latency, consistency, and logic-exposure risk.

### 2.1. Flag Types

| Flag Type | Purpose | Example | Typical Lifecycle |
| --- | --- | --- | --- |
| Release toggle | Enable/disable in-progress or rolling-out features | New booking workflow | Short to medium term |
| Experiment toggle | Split cohorts to test variants | Checkout A/B test | Bounded by experiment duration |
| Operational toggle | Control runtime operational behavior | Disable heavy exports | Can be long-lived if operational control |
| Permission/entitlement toggle | Gate capabilities by plan or role | Enterprise-only report | Long-lived; must integrate with authorization |
| Kill switch | Rapidly disable a failing capability | Disable recommendation provider | Must always remain tested |
| Migration toggle | Gradually shift to a new data store or implementation | Read from DB B | Bounded by migration duration |

Never use feature flags as a substitute for authorization. A flag can govern product availability for a cohort, but data access and sensitive actions must still be enforced server-side via independent identity and policy checks.

### 2.2. Flags Can Hold More Than Booleans

A simple flag may be on/off. Targeting systems often support multiple variants or value types: booleans, strings/enums, numbers, schema-validated JSON/objects, or multivariate experiments. The more complex the flag, the more critical contracts, validation, schema evolution, and testing become. Never turn feature management into an untyped, ungoverned dumping ground of arbitrary configs.

## 3. Designing the Feature Flag Contract

A flag must be documented so creators and operators understand what it affects.

Metadata example:

~~~yaml
key: booking.pricing.v2
type: boolean
description: Enable the new booking pricing calculation
owner: booking-platform
default: false
environments:
  development: true
  staging: true
  production: false
targeting:
  allowed_dimensions:
    - tenant_id
    - region
    - service_tier
risk: high
requires_approval: true
expires_at: 2027-03-31
rollback:
  action: disable_flag
  owner: booking-oncall
~~~

This schema is illustrative. Exact field names and enforcement capabilities depend on the feature management system. Flags may require approvals, security reviews, or change tickets before production activation.

### 3.1. Naming

Flag names should describe the capability or decision—not the author or date. For example, `booking.pricing.v2` is far better than `alex_test_new`. Namespace flags by domain or service to avoid key collisions.

### 3.2. Defaults and Failure Behavior

Define what happens when the SDK fails to fetch config:
- **Fail closed:** use `false` or legacy behavior.
- **Fail open:** allow the capability to run.
- **Last known good:** use the most recent valid cached config.
- **Static fallback:** use the default compiled or deployed with the application.

Choose based on business impact. Recommendations can fail disabled; flags must never act as security boundaries; kill switches guarding costly providers may need local fallbacks and independent operational controls.

### 3.3. Trusted Evaluation Context

Targeting can use tenant, region, or account attributes, but the context must be verified server-side. Never trust arbitrary client headers or query parameters to decide whether a user receives an Enterprise feature. Avoid putting emails, phone numbers, or sensitive data into targeting payloads when pseudonymous identifiers suffice.

## 4. What Is a Dark Launch?

A dark launch deploys a new processing path in production without letting its results become the primary user-visible behavior. The goal is to observe performance, compatibility, and outputs under real data and load before releasing.

Common patterns:
- Execute new code while discarding its output, recording only metrics.
- Shadow requests: send a duplicate copy of requests to the new system.
- Mirror traffic: copy a fraction of traffic to the new implementation.
- Shadow reads: query a new data store in parallel while returning results only from the old store.
- Background computation: precompute results without using them in responses yet.
- Dark endpoints: deploy endpoints without exposing them in public routing.

~~~mermaid
flowchart LR
    U["Production request"] --> OLD["Existing service"]
    U --> MIRROR["Traffic mirror"]
    OLD --> RESP["User response"]
    MIRROR --> NEW["New service / data path"]
    NEW --> OBS["Compare metrics/results"]
    OBS --> DEC["Release decision"]
~~~

In a dark launch, the old path remains the authoritative source of results. The new system is observed to assess parity, latency, resource utilization, and errors.

### 4.1. Dark Launching Does Not Mean Blindly Sending Requests Twice

Shadow traffic is safest for read-only or simulatable operations. If a request triggers side effects—charging payments, sending emails, creating bookings, writing ledgers, or emitting events—direct mirroring can create duplicate transactions.

Before mirroring, determine whether requests read or write, identify external side effects, assess sandbox/synthetic identities, ensure writes are blocked in the shadow path, scrub PII/secrets, bound concurrency/QPS, and define data retention. Never mirror traffic before isolation and a kill switch are in place.

### 4.2. Shadow Reads and Data Migration

When migrating from database A to database B:
1. Replicate or backfill data into B.
2. Application continues reading from A.
3. Shadow-read a subset of requests from B.
4. Compare records, nulls, ordering, filtering, latency, and consistency.
5. Fix discrepancies and repeat validation.
6. Canary-shift a group of readers to B.
7. Gradually increase traffic and observe.
8. Once evidence is sufficient, switch primary reads.
9. Retain a tested rollback window and fallback path.
10. Retire A after the window expires and data is reconciled.

Never compare HTTP status codes alone. Compare semantics: matching record sets, authorization, sorting, pagination, transaction snapshots, and data freshness.

## 5. Risks and Controls for Dark Launches

### 5.1. Unexpected Load Amplification

Mirroring 100% of traffic can nearly double workload volume. If the new system calls external dependencies or queries a shared database, a dark launch can slow down production even when its results are discarded.

Controls include low sampling rates, concurrency and queue limits, dedicated bulkheads, query timeouts and response-size caps, dropping requests past deadlines, independent kill switches, and tracking incremental compute, egress, and storage costs.

### 5.2. Data Leakage

Mirrored requests may carry PII, payment tokens, session identifiers, or internal payloads. Shadow systems require data minimization/masking, private networks and TLS, least privilege, bounded retention, avoiding raw payload logging unless necessary, access audits, and processing within compliant data-residency regions.

### 5.3. Side Effects and Consistency

Shadow paths should not emit business events or write to systems of record. Use read-only database identities, mock/sandbox providers, separate sinks for shadow outputs, correlation IDs tagging shadow traffic, interceptors blocking writes/side effects, or synthetic tenants/data.

If a shadow path must write to validate behavior, use an isolated test namespace/database or appropriate transaction rollbacks; note that rolling back a local transaction cannot undo side effects sent to external systems.

### 5.4. Fair Output Comparisons

Two implementations may read data at slightly different timestamps or under different versions/configs. Log timestamps, data versions, input hashes, request classes, and correlation IDs. Compare meaningful business fields rather than raw byte-level JSON serialization when field order or dynamic timestamps differ.

## 6. Targeting and Cohort Rollouts

Feature flags can target by environment, internal users, tenant/account, region/zone, service tier, user cohort, deterministic percentage by identity key, or capability/entitlement.

### 6.1. Percentage Rollouts Must Be Deterministic

If every request draws an independent random number, the same user may see a feature flicker on and off. Use deterministic assignment based on a chosen, protected stable key—such as hashing `tenant_id` or `user_id` combined with a flag salt. Keep cohort assignments stable throughout an experiment unless deliberately re-bucketing.

### 6.2. Tenant-Level Rollouts

In B2B SaaS, the tenant is often a better rollout unit than individual users because data, workflows, and support are managed per account. Avoid splitting users within the same tenant across old and new code paths when they share state or database schemas.

### 6.3. Rollout Ladder

| Stage | Exposure | Goal |
| --- | ---: | --- |
| Internal | Employees / test tenants | Validate functionality and supportability |
| Pilot | 1 tenant or small cohort | Validate real data and workflows |
| Canary | 1% of eligible traffic/tenants | Check errors, latency, resources |
| Early access | 5–10% | Confirm trends |
| Broad rollout | 25–50% | Evaluate capacity and business KPIs |
| General availability | 100% per eligibility | Transition to normal operations |

Percentages are illustrative. In low-traffic systems, 1% may yield too few samples; for very expensive or sensitive workloads, cap tenant count rather than request percentage.

### 6.4. Region-Based Rollouts

Regional rollouts limit blast radius, but never assume regions are fully independent. If data or control planes are global, a change can still affect multiple regions. Verify replication, keys, identities, feature config propagation, and external dependencies.

## 7. Progressive Delivery and Deployment Strategies

Feature flags manage exposure at the application behavior layer. Deployment strategies manage how artifacts land on compute. They complement each other rather than replacing one another.

| Strategy | How It Works | Role of Feature Flags |
| --- | --- | --- |
| Rolling deployment | Replaces instances/pods in batches | Keeps old behavior inactive while new code deploys |
| Blue/green | Two environments; shifts traffic between them | Controls capabilities inside a version |
| Canary deployment | Fraction of traffic hits new version | Pairs small exposure with new version |
| A/B experiment | User cohorts receive different variants | Preserves assignment and measures KPIs |
| Dark launch | Runs new code without using primary output | Enables bounded shadow paths |
| Traffic mirroring | Copies requests to new backend | Controls shadow sampling and behavior |

### 7.1. Two-Dimensional Rollouts

A release can proceed in two steps: deploy new code to part or all of the fleet with the flag off; then enable the feature flag by cohort, observe, and expand.

Alternatively, a canary deployment puts the new version on a subset of pods while a feature flag enables a small cohort on those pods. When combining both dimensions, prevent routing a feature-assigned user to a pod that does not yet have the new code.

### 7.2. Version and Flag Compatibility

During rolling deployments, old and new pods coexist temporarily. Feature configurations must be compatible with both versions, or rollouts must ensure only capable versions see the new flag. Enforce stable key/version semantics, have old code safely ignore unknown flags, roll out configs only after artifacts are ready, never enable flags before required migrations or dependencies complete, and tag telemetry with both application version and flag state.

## 8. Rollback and Kill Switches

Rollback restores the system to an acceptable state. It may involve disabling a feature flag to revert to the legacy path, shifting traffic away from a canary/green stack, rolling back the application artifact, reverting configs/schemas if supported, degrading functionality, or running compensation/reconciliation for already-executed side effects.

### 8.1. Kill Switches

A kill switch is a flag or control that rapidly disables a capability during an incident. It needs clear owners and activation permissions; must operate even if the feature config service fails; must have safe defaults/fallbacks; must be tested periodically; must leave an audit trail; must not depend on a single UI if the control plane can suffer an outage; and must define how in-flight requests and queued jobs behave.

A kill switch may require a local emergency override or cached config. Emergency overrides must still enforce authentication, auditing, and expiration.

### 8.2. Rollback Is Not Always Just Flipping a Flag Off

If new code has already written data under new schemas or semantics, flipping a flag off may not restore the old state. Use expand-migrate-contract:
1. Expand the schema so old and new versions both function.
2. Deploy code compatible with both.
3. Migrate and backfill data.
4. Shift traffic/flags.
5. Observe and verify.
6. Contract the old schema after the rollback window and approval.

Never drop columns or change semantics while old consumers remain active.

## 9. Feature Flags in Java / Spring Boot

Define an interface so the application does not couple directly to a vendor SDK:

~~~java
public interface FeatureDecisions {
    boolean enabled(String key, EvaluationContext context);
}
~~~

Construct the context from verified identity:

~~~java
public record EvaluationContext(
    String tenantId,
    String userId,
    String region,
    String serviceTier
) {}
~~~

Use the decision inside a service:

~~~java
public PricingResult calculatePrice(
        BookingRequest request,
        EvaluationContext context) {

    if (featureDecisions.enabled("booking.pricing.v2", context)) {
        return newPricingEngine.calculate(request);
    }

    return legacyPricingEngine.calculate(request);
}
~~~

This code is illustrative. Production implementations require defaults/fallbacks on config service timeouts, caching and refresh policies, tight timeouts, metrics tagged by flag key/version with bounded cardinality, unit/integration tests for each branch, server-side context verification, and consistent decisions within a single operation or transaction.

### 9.1. Do Not Call a Remote Feature Service Synchronously on Every Request Without Safeguards

SDKs typically cache configs or evaluate locally. If an application makes synchronous remote calls to a feature service on every request, that service becomes a critical dependency capable of triggering latency and failure chains. Design with caching, local evaluation, last-known-good state, and criticality-appropriate fallbacks.

### 9.2. Server-Side Enforcement

Client-side flags are useful for hiding UI elements or tailoring UX, but they are never a security control. Users can modify JavaScript or call endpoints directly. APIs must enforce entitlements and authorization independently.

## 10. Testing Feature Flags and Dark Launches

### 10.1. Flag Test Matrix

For each critical flag, test enabled, disabled, missing/default, config service unavailable, invalid/unknown values, target match/mismatch, user/tenant plan changes, mixed application versions during rolling deployments, and expired flags. You do not need to test every combinatorial permutation of dozens of flags; prioritize pairwise/risk-based testing and avoid undocumented flag interactions.

### 10.2. Dark Launch Validation

Measure output parity/difference rates, errors/timeouts, p50/p95/p99 latency, CPU/memory/DB queries/connections, queue lag/retries, egress/data scanned, side-effect counts, data classification/retention compliance, and cost deltas.

### 10.3. Experiment Correctness

For A/B tests, assignments must be deterministic; cohorts must not overlap unintentionally; the randomization unit must match the experiment; primary and guardrail metrics must be pre-registered; sample size and duration must be statistically justified; never stop early merely because interim results look favorable; check for sample ratio mismatches and instrumentation bugs; and comply with consent and privacy policies.

Feature flags used for experimentation do not replace statistical design or privacy reviews.

## 11. Telemetry and Release Health

A rollout must monitor both system health and business impact. Dashboards should segment by artifact version, flag key/state/version, cohort/region/service tier, endpoint/operation class, and release timestamp.

| Group | Metrics |
| --- | --- |
| Exposure | Eligible users/tenants, evaluated, enabled, actual exposure |
| Reliability | Error rate, timeouts, crashes, availability |
| Performance | p50/p95/p99, CPU, memory, DB latency |
| Business | Conversion, booking success, payment completion, abandonment |
| Data | Schema errors, reconciliation mismatches, duplicates |
| Background | Queue lag, job duration, retries, DLQ |
| Cost | Compute delta, query scan volume, egress, storage |
| Safety | Kill switch state, unauthorized targeting, audit failures |

### 11.1. Guardrail Metrics

Before rolling out, define stop conditions: error rate exceeding baseline, p95 latency breaching SLO, non-zero payment duplicates or reconciliation mismatches, DB CPU/connections exceeding thresholds, queue age past deadlines, significant drops in business conversion, or unexpected egress/cost spikes.

Quantify thresholds relative to baselines and traffic. A slight metric uptick may reflect seasonality or traffic mix; compare against appropriate cohorts or control groups.

### 11.2. Exposure Denominator

Flag-enabled rate does not necessarily equal actual feature adoption. Distinguish eligible, targeted, evaluated, enabled, and feature-used counts. A flag might be enabled for a tenant whose users never open the new page—yielding low adoption despite 100% enablement.

## 12. Governance: Owners, Expiration, and Flag Debt

Flags introduce extra code branches. Without cleanup, a codebase accumulates hundreds of stale flags, bloating test matrices and making behavior unpredictable.

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Approved
    Approved --> Active
    Active --> Expiring
    Expiring --> Removed
    Active --> Disabled
    Disabled --> Removed
    Approved --> Rejected
~~~

Every flag should track its owner/team, purpose/business ticket, type/risk, created/review/expiration dates, per-environment defaults, targeting rules, dependent code/schemas, rollback instructions, linked metrics/experiments, and removal PR/retirement ticket.

### 12.1. Temporary Flags Must Expire

Upon expiration, the owner decides:
- Promote: keep the new implementation and delete the flag and legacy branch.
- Roll back: disable the feature and delete unused code.
- Extend: record justification, approver, and new expiration date.
- Convert: long-lived operational controls that are genuinely needed permanently are governed like any other runtime control.

Never let temporary flags become permanent fixtures simply because everyone forgot about them.

### 12.2. Flag Debt Metrics

Track flags lacking owners, past expiration, no longer evaluated, unremoved dead code paths, excessive targeting rules, departed/transferred owners, unaudited configs, and untested rollbacks.

## 13. Security and Change Control for Flags

Feature configurations can alter production behavior without deploying a new artifact, making flag permissions equivalent to production change privileges.

Controls:
- RBAC scoped by environment and flag namespace.
- Separation of author, approver, and operator roles for high-risk flags.
- MFA/SSO for management consoles.
- Audit logs recording actor, old/new values, target, timestamp, and reason.
- Approval/change tickets for payment, security, data migration, or tenant-wide flags.
- Two-person review for kill switches or critical releases when policy requires it.
- Signed/versioned config rollouts and rollbacks.
- Rate limits on configuration updates.
- Never store secrets inside flag values.
- Tenant targeting must never override data access policies.
- Break-glass procedures with expiration and post-change review.

Do not expose the entire flag catalog to browsers if flag names, keys, or metadata leak internal capabilities. Clients should receive only evaluated decisions needed for rendering—never secrets or security conditions.

## 14. Common Mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Using flags as authorization | Clients can bypass permissions | Server-side entitlement/security checks |
| Mirroring write requests in dark launch | Duplicate payments, emails, or events | Read-only modes, sandboxes, or side-effect guards |
| Unbounded 100% mirroring | Production overload and inflated cost | Sampling, bulkheads, timeouts |
| Enabling flags before code finishes deploying | Requests hit pods that lack the flag code | Coordinate deployment and config order |
| Targeting via untrusted client headers | Exposes features/tenants improperly | Trusted server-side identity context |
| No default when flag service fails | Requests depend on control-plane uptime | Caching, fallbacks, and safe local defaults |
| Per-request random percentages | Users experience flickering behavior | Deterministic hashing on stable keys |
| Disabling flag with incompatible schema | Rollback fails | Expand-migrate-contract |
| One flag governing too many behaviors | Broad blast radius and complex testing | Split flags by capability |
| Flags without owners or expiration | Flag debt and lingering code branches | Lifecycle metadata and scheduled cleanup |
| Measuring only enabled rate | No visibility into real usage | Track eligible, evaluated, and used |
| Unaudited flag updates | Cannot investigate production changes | Immutable audit trail |

## 15. Case Study: Rolling Out Pricing v2 for a Booking Platform

### 15.1. Context

A booking platform wants to replace its pricing engine to support real-time discounts. Pricing v2 reads additional campaign data and introduces new rounding rules. Risks include mismatch between displayed and charged prices, increased latency, heavy database queries, and currency rounding discrepancies.

Requirements: do not switch pricing for all bookings simultaneously; compare v1/v2 outputs on live production traffic; never double-charge payments; roll back behavior within minutes on discrepancies; and audit which tenants/cohorts received the new pricing.

### 15.2. Phases

**Phase A — Deploy dark:** Deploy pricing v2 with the flag disabled for all tenants. Unit and integration tests run in staging. Production continues returning v1 results.

**Phase B — Shadow computation:** A small percentage of requests execute pricing v2 in read-only mode. v2 outputs are written to a shadow result store tagged with correlation IDs; users still receive v1 responses. The shadow path never calls payment providers.

**Phase C — Internal pilot:** Enable for employees and synthetic tenants. Compare pricing parity, rounding, currency handling, and latency.

**Phase D — Tenant canary:** Enable for a small approved group of tenants. Monitor booking conversion, payment completion, price mismatches, and database load.

**Phase E — Progressive rollout:** Expand cohorts in defined stages. At each stage, wait for adequate sample sizes and review guardrail metrics before advancing.

**Phase F — General release and cleanup:** Once v2 stabilizes, promote it as default, remove v1 after the compatibility window, delete the release flag, and update documentation.

~~~mermaid
flowchart LR
    D["Deploy v2, flag off"] --> S["Shadow compute"]
    S --> P["Internal pilot"]
    P --> C["Tenant canary"]
    C --> R["Progressive rollout"]
    R --> GA["General availability"]
    GA --> CLEAN["Remove flag and v1 path"]
    S -. "Mismatch / load issue" .-> STOP["Stop / disable"]
    P -. "Guardrail breach" .-> STOP
    C -. "Business or reliability issue" .-> STOP
~~~

### 15.3. Release Guardrails

- Pricing mismatches exceeding tolerance: halt rollout.
- Payment duplicates: immediate halt and reconciliation.
- API p95 breaching SLO: hold next cohort expansion.
- Database query load exceeding budget: reduce shadow sampling or disable shadow path.
- Conversion dropping past threshold: analyze cohorts and traffic mix.
- Config service unavailable: maintain last-known-good or safe default behavior.

### 15.4. Closing Evidence

Parity reports by currency and booking type; errors and latency segmented by application version and flag state; restricted-access tenant exposure list; payment ledger reconciliation; shadow workload cost delta; approval records and rollout timeline; and cleanup PR removing the flag and legacy code.

## 16. Controlled Release Workflow

1. Define business goal, owner, and blast radius.
2. Classify the change: release, experiment, operational, entitlement, or migration.
3. Choose the flag strategy and default/fallback behavior.
4. Design targeting based on verified identities.
5. Ensure version and schema compatibility.
6. Write tests for enabled, disabled, default, error, and mixed-version states.
7. Design dark launches with strict side-effect and capacity bounds.
8. Define metrics, guardrails, and stop conditions.
9. Deploy the artifact via CI/CD with provenance and approvals.
10. Enable a small cohort and observe sufficient samples.
11. Increase exposure in stages with clear decision accountability.
12. On incidents, disable the flag or roll back traffic per runbook.
13. At GA, retire the flag, delete legacy code, and update documentation.
14. Reconcile usage, cost, and audit logs if the change impacts billing or data.

A release decision record should capture release ID/artifact digest, flag key/version/config snapshot, environment/region/tenant cohort, approver/operator, start/end timestamps, rollout steps, guardrail thresholds, continue/pause/rollback decisions, incident references, evidence links, and cleanup owner/expiration.

## 17. TCO and Operational Impact

Feature management platforms centralize targeting and auditing but introduce costs:
- Vendor licensing, seats, MAUs, or request-based fees.
- Network dependencies and SDK traffic.
- Config caching and refresh overhead.
- Telemetry and event retention.
- Engineering integration and testing effort.
- Operational support, RBAC, and auditing.
- Shadow compute, duplicate queries, and storage.
- Flag cleanup and code maintenance.

Small systems can use a lightweight config service with local evaluation. Multi-tenant, multi-region platforms need stronger consistency, targeting, auditing, approvals, and SDK resilience. Never select a platform solely by flag count; measure latency, availability, propagation semantics, offline behavior, and data handling.

~~~text
Release experiment cost
  = Feature management cost
    + Shadow/canary compute
    + Additional database/network usage
    + Telemetry and storage
    + Engineering and operational effort
~~~

Key trade-offs: centralized flag services reduce duplication at the cost of a new dependency; local configs eliminate runtime dependencies but slow rapid synchronization; dark launches boost confidence while raising compute/query costs; cohort rollouts shrink blast radius while lengthening release cycles; long-lived flags aid operations while adding complexity and testing overhead.

## 18. Hands-On Exercise

A SaaS platform plans to launch Search v2. Search v2 uses a new index, queries more fields, and introduces a new ranking model. Traffic is 8,000 requests/second across 600 tenants in three regions. Some tenants hold restricted data with strict residency requirements. Search may return results stale by up to 2 minutes, but tenant authorization and filtering must remain strictly accurate.

Complete the following tasks:

1. Distinguish deploy vs. release for Search v2 and specify which flag type to use.
2. Design the feature flag contract including owner, default, environments, targeting, expiration, and rollback.
3. Choose the cohort unit (tenant, user, or request) and explain stability and isolation.
4. Design a dark launch / shadow read that avoids leaking new results and stays within capacity limits.
5. Describe how tenant filtering, data residency, and restricted data are protected in the shadow path.
6. Build a rollout ladder from internal to GA with sample and observation requirements.
7. Define guardrails for latency, errors, search relevance, DB/index load, and cost.
8. Design a kill switch if Search v2 fails or index lag grows too high.
9. Analyze compatibility between old/new application versions and index schemas.
10. Build a test matrix covering enabled, disabled, default, config service unavailable, and target mismatch.
11. Design telemetry and a methodology for comparing v1/v2 outputs against the same snapshot.
12. Calculate incremental capacity if mirroring 10% of traffic where each shadow request consumes an average of 70% of a primary request's compute.
13. Write a pause/rollback runbook and post-GA flag cleanup plan.
14. Write an ADR selecting a feature management service and the balance between centralized vs. local evaluation.

**Self-Assessment Hint:** A strong solution ensures dark launches produce zero side effects or data leaks, targeting cannot be spoofed by clients, rollouts define explicit stop conditions, rollbacks remain schema-compatible, and shadow traffic costs are bounded.

## 19. Pre-Production Checklist

- [ ] Deploy, enablement, and release are clearly separated.
- [ ] Every flag has a type, key, description, owner, purpose, and expiration date.
- [ ] Default/failure behavior aligns with business impact.
- [ ] Targeting context is derived from authenticated identities.
- [ ] Feature flags never replace authorization or entitlement enforcement.
- [ ] SDK/config caches enforce timeouts, fallbacks, and last-known-good policies.
- [ ] Dark launches trigger no unintended side effects.
- [ ] Mirrored traffic enforces sampling, concurrency, timeout, and cost guardrails.
- [ ] PII and secrets are scrubbed or protected in shadow paths and telemetry.
- [ ] Mixed application versions remain compatible with flag/config states.
- [ ] Rollouts define cohorts, stages, owners, and decision authority.
- [ ] Guardrail metrics, stop conditions, and rollback runbooks are defined.
- [ ] Kill switches are tested and properly access-controlled.
- [ ] Schema and data migrations support the rollback window.
- [ ] Audit logs capture actor, target, old/new values, reason, and timestamp.
- [ ] Flag expirations and cleanup tickets are tracked.
- [ ] Experiments define randomization, metrics, privacy compliance, and sample plans.
- [ ] Cost deltas of canary and dark launches are measured.

## 20. Well-Architected Review

| Pillar | Questions When Reviewing Feature Flags and Release Control |
| --- | --- |
| **Operational Excellence** | Do flags have owners, expiration dates, audits, rollout decisions, runbooks, and cleanup processes? |
| **Security** | Does targeting use trusted identities; do flag updates enforce RBAC/approvals; is shadow data protected? |
| **Reliability** | Are defaults/fallbacks, kill switches, canaries, rollbacks, and schema compatibility validated? |
| **Performance Efficiency** | Are evaluation latency, SDK refresh, mirror load, caching, and rollout capacity properly sized? |
| **Cost Optimization** | Are shadow compute, duplicate queries, telemetry, vendor licenses, and flag debt tracked? |
| **Sustainability** | Are stale code/flags removed, indefinite shadow runs avoided, and experimental resources minimized? |

**Conclusion:** Feature flags decouple deploying code from releasing behavior; dark launches allow observing new implementations before serving their results; release control governs who gains access, when to expand, and when to halt. All three techniques only add value when paired with contracts, trusted identities, safe fallbacks, guardrails, auditing, and lifecycle cleanup. Control shadow traffic side effects and capacity, ensure data-compatible rollbacks, and expand based on telemetry evidence and business goals in line with Well-Architected principles.
