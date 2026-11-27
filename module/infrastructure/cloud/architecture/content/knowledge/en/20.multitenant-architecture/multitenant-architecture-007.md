# Tenant Customization and Product Version Management

In a **multi-tenant SaaS** model, multiple organizations share a single product and shared infrastructure to varying degrees. Each tenant can differ in branding, workflows, service plans, enabled features, integrations, data policies, and upgrade cadence. If every difference is handled by separate code branches or dedicated application deployments per customer, development and operational costs skyrocket while consistent product behavior becomes difficult to maintain.

**Tenant customization** and **product version management** are two architectural capabilities that deliver tailored customer experiences while keeping the platform upgradable, controllable, and maintainable over the long term. Customization needs clear boundaries between configuration, extensions, and core modifications. Version management must track which application, schema, API, feature, and configuration versions apply to each tenant, along with how rollouts, compatibility, rollbacks, and end-of-support are handled.

This lesson belongs to the **Multi-Tenant Architecture** chapter of the **Cloud Architecture** track. The curriculum teaches how to design cloud applications from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. Here, the focus is enabling per-tenant differentiation without weakening data isolation, testability, or release velocity.

After this lesson, you will be able to:

- Distinguish tenant configuration, feature flags, extension points, plugins, and product forks.
- Identify which customization boundaries are safe to manage via data/configuration.
- Design tenant context, inheritance, validation, and auditing for configuration.
- Manage application, API, schema, configuration, and feature versions per tenant.
- Design cohort rollouts, canaries, progressive delivery, and rollbacks.
- Handle backward compatibility, migrations, tenant pinning, and deprecation.
- Protect tenant isolation when customizing UIs, workflows, policies, and integrations.
- Measure customization footprint, version fragmentation, cost, and operational risk.

## 1. Why Do Tenants Need Customization?

Tenants share the same product yet have different needs. An equipment rental enterprise might need a multi-level contract approval workflow; a small shop only needs automatic confirmation. Customers across countries use different languages, currencies, timezones, and document templates. Higher-tier tenants may need SSO, audit exports, or ERP integrations; basic-tier tenants do not have these capabilities.

Differences typically fall into the following categories:

| Difference Category | Example | Common Representation |
| --- | --- | --- |
| Branding/presentation | Logo, colors, domain name, email templates | Theme and branding configuration |
| Locale | Language, timezone, currency, date format | Locale settings |
| Product entitlement | User limits, tier-gated features | Plan/entitlement policy |
| Feature availability | Enabling beta features or specific modules | Feature flags / feature policies |
| Business policy | Rental limits, hold durations, approval thresholds | Policy configuration |
| Workflow | Number of approval steps, participating roles | Workflow definition/extension |
| Integration | ERP, identity provider, webhooks, payment providers | Connector configuration |
| Data retention | Record retention duration, exports, archiving | Data policy |
| Security | SSO, MFA policy, IP allowlist, role mapping | Tenant security configuration |
| Reporting | Extra fields, custom dashboards and metrics | Extensions/read models/report definitions |

Customization makes the product fit each customer better and helps fulfill contractual obligations. However, every variant creates another behavioral combination to support, test, and observe. The freer the customization, the greater the risk of misconfiguration, upgrade friction, and hard-to-explain behavior.

## 2. Distinguishing Configuration, Feature Flags, and Extensions

Not every difference requires a plugin mechanism. Choose the customization type based on the nature of the requirement.

### 2.1. Configuration

**Configuration** is data describing how an existing capability behaves within bounds supported by the product. Examples include timezone, logo, approval thresholds, or email templates selected from a safe list.

Configuration should have schemas, data types, defaults, validation, versioning, and auditing. Avoid using free-text fields to express complex rules when validation and correctness guarantees are required.

### 2.2. Feature Flags and Entitlements

**Feature flags** control toggling or switching product behaviors. Flags can target tenants, cohorts, environments, or traffic percentages.

**Entitlements** define which capabilities a tenant is authorized to use under their contract/plan, quota, or license. Flags are a behavior delivery mechanism; entitlements are product-rights decisions. Never use feature flags as a substitute for authorization or entitlement checks.

For example, the code may exist in production, yet only tenants with the `Analytics Advanced` entitlement may use it. Feature flags may hold the feature back from rollout, but both conditions must be enforced in the backend.

### 2.3. Extension Points

**Extension points** are interfaces intentionally designed by the product so customers or modules can add behavior within permitted bounds. Examples include pre-notification hooks, custom fields, webhook event subscriptions, formatters, or supported workflow steps.

Extensions need contracts, sandboxes/permissions, timeouts, versioning, and error policies. Never run arbitrary code inside core processes just to satisfy a single tenant's request.

### 2.4. Plugins and Forks

**Plugins** package extensions as modules with controlled lifecycles and interfaces. **Forks** are separate code branches of the product maintained for one customer or customer group.

Forks may be necessary in rare cases with special regulatory/infrastructure requirements, but they create high overhead for maintaining patches, merges, testing, and custom support. In shared SaaS, forks should be approved exceptions rather than a default customization mechanism.

| Mechanism | Customer Self-Configurable? | Executes New Logic? | Relative Maintenance Cost | Primary Risk |
| --- | --- | --- | --- | --- |
| Configuration | Within allowed schema | No, selects supported behavior | Low to medium | Invalid or conflicting config |
| Feature flag | Per granted policy | Does not create new logic | Low to medium | Flags multiply state combinations |
| Extension point | Within extension contract | Yes, via bounded interface | Medium to high | Errors, permissions, module compatibility |
| Plugin | Per marketplace/admin policy | Yes | High | Supply chain, versioning, isolation |
| Fork | Usually via dedicated dev team | Can alter any part | Very high | Product fragmentation and hard upgrades |

## 3. Defining Customization Boundaries

A practical rule is to customize predictable, controllable variations with configuration; open extension points only for recurring, high-value behavioral differences; and avoid giving every tenant unbounded logic branches.

### 3.1. Classifying Requirements Before Implementation

For every customer request, ask:

1. Is this a different value or a new business rule?
2. Can the difference be expressed via enums, thresholds, templates, or policies?
3. Will this difference serve multiple tenants or only one customer?
4. Does it affect transactions, security boundaries, or data ownership?
5. Does it require executing arbitrary code or calling external services?
6. Who owns the configuration and is responsible for testing it?
7. Can the tenant fall back to defaults if the configuration breaks?
8. When the product upgrades, can this variant keep working?

### 3.2. Decision Matrix

| Scenario | Preferred Design | Rationale |
| --- | --- | --- |
| Changing logo, colors, timezone | Configuration | Schema-bound values with minimal business risk |
| Enabling a module included in plan | Entitlement + feature policy | Separates product rights from rollout |
| Different approval thresholds | Policy configuration | Keeps validation logic inside domain services |
| Adding a supported standard approval step | Workflow definition | Behavior described via a versioned schema |
| Integrating an ERP with another protocol | Connector/extension point | Isolates integration logic and credentials |
| Running arbitrary scripts after every transaction | Disallow directly; design bounded events/extensions | Prevents uncontrolled execution privileges |
| Altering core booking invariants | Explicit policy-backed domain capability or approved separate product | Never let tenants override correctness arbitrarily |

Do not turn every requirement into configuration. A field like `allowNegativeBalance` may look simple yet undermines financial invariants. Core rules must be reviewed and safely enforced by domain owners.

## 4. Modeling Tenant Context

Services must know which tenant a request belongs to and which configuration applies. Tenant context is typically established at a trust boundary from verified identity, domain, API key, or token.

A conceptual context:

~~~json
{
  "tenantId": "tenant-482",
  "plan": "enterprise",
  "locale": "vi-VN",
  "timezone": "Asia/Ho_Chi_Minh",
  "configurationVersion": 12,
  "featurePolicyVersion": 5,
  "requestId": "req-9281"
}
~~~

This is an illustrative example, not a mandatory schema. Context must never be constructed by trusting a client-sent `tenantId`. The backend must verify which tenant the caller belongs to, whether the resource belongs to that tenant, and whether the user is permitted to perform the requested action.

### 4.1. Tenant Resolution

Common tenant resolution sources:

- Mapped and verified subdomain or custom domain.
- Claim inside an identity token issued by a trusted issuer.
- API key/client credential bound to a tenant.
- Context from gateway/service identity inside an internal system with clear trust boundaries.

If a request carries multiple tenant signals simultaneously, define precedence rules and consistency checks. For example, a Tenant A subdomain paired with a Tenant B token must be rejected or handled per defined flow—never silently pick one.

### 4.2. Propagating Context Between Services

As requests travel from the API gateway to other services, tenant context must propagate via a trusted mechanism—signed tokens, verified claims, or internal metadata that clients cannot spoof. Downstream services must still enforce appropriate authorization; never treat a bare `X-Tenant-ID` header as proof of permission.

Context should avoid carrying massive configs or secrets. Pass the tenant identifier, trace/request ID, and required versions/references; services fetch configs from controlled sources.

## 5. Structure and Lifecycle of Tenant Configuration

Tenant configuration needs schemas and lifecycles just like any critical product data.

A configuration record should contain:

| Attribute | Purpose |
| --- | --- |
| `tenantId` | Owning tenant |
| `configurationVersion` | Monotonic version or immutable ID |
| `schemaVersion` | Configuration schema version |
| `values` | Validated values |
| `inheritedFrom` | Source of defaults/plan/parent if any |
| `updatedBy` | Identity that performed the change |
| `updatedAt` | Timestamp of the change |
| `effectiveAt` | Timestamp when config takes effect |
| `status` | Draft, validated, active, deprecated, or rollback state |
| `changeReason` | Reason and linked ticket/approval |

### 5.1. Inheritance and Precedence

A product may have system-wide defaults, plan defaults, and tenant overrides. Define explicit precedence, for example:

**Platform default -> Product plan default -> Tenant override**

Tenant overrides must only be allowed for overridable keys. Mandatory security policies or legal limits must not be overridable by tenants.

Avoid deep, unpredictable inheritance chains. If the same key is declared in three places, admin UIs and APIs must show where the effective value comes from.

### 5.2. Versioned Configuration Example

~~~yaml
tenantId: tenant-482
configurationVersion: 12
schemaVersion: 3
locale:
  language: vi-VN
  timezone: Asia/Ho_Chi_Minh
branding:
  theme: ocean
bookingPolicy:
  approvalMode: manager
  holdDurationMinutes: 20
notifications:
  receiptTemplate: standard-v2
~~~

The example above contains no credentials. Connector secrets or SMTP/API keys belong in a secret manager and are referenced by ID rather than embedded directly in configuration documents.

### 5.3. Validation and Publishing

Configuration changes should move through defined states:

1. Draft created.
2. Validate schema, enums, ranges, and dependencies.
3. Validate policy and editor permissions.
4. Preview impact or run per-tenant validation.
5. Review/approve for sensitive changes.
6. Publish as an immutable version.
7. Tenants/services adopt the new version at `effectiveAt`.
8. Monitor errors and allow rollback to a previous version.

Never mutate an active document in place without recording versions/audits. Immutable versions help investigate why two requests for the same tenant behaved differently at two points in time.

## 6. Separating Configuration and Secrets

Ordinary configuration like locale, theme colors, or timeouts can live in a configuration service. Secrets such as API keys, client secrets, private keys, passwords, and webhook signing secrets belong in a secret manager or vault.

Principles:

- Never put secrets in source control, feature flags, logs, event payloads, or client responses.
- Configuration holds only secret references and necessary metadata.
- Scope secret access by tenant, integration, and environment.
- Enforce rotation, expiration, revocation, and auditing.
- Never return old secrets when reading back config; display only configured status.
- Separate dev/staging/production secrets.
- When a tenant is offboarded, revoke connector credentials and related tokens.

In a multi-tenant system, Tenant A's secrets must never be accessible to a runtime handling Tenant B merely because both share a worker. Secret retrieval must bind to tenant identity with server-side policy enforcement.

## 7. Managing Features and Entitlements per Tenant

A product may need three decision layers:

1. **Availability:** is the code/module deployed in this environment?
2. **Entitlement:** is the tenant allowed to use the feature under its plan/contract?
3. **Rollout flag:** has the feature been enabled for this tenant/cohort?

Permitting execution typically requires all three alongside user authorization and business conditions.

~~~mermaid
flowchart TD
    R["Feature request"] --> A{"Available in deployment?"}
    A -- "No" --> D["Feature unavailable"]
    A -- "Yes" --> E{"Tenant entitled?"}
    E -- "No" --> D
    E -- "Yes" --> F{"Rollout enabled?"}
    F -- "No" --> D
    F -- "Yes" --> U{"User authorized?"}
    U -- "No" --> X["Access denied"]
    U -- "Yes" --> O["Execute capability"]
~~~

### 7.1. Avoid Using Flags as Security Controls

Feature flags can be served from stale caches, read with delay, or misconfigured. They do not replace per-request/per-resource authorization. If a sensitive operation requires an entitlement, the backend must verify it at execution time.

### 7.2. Flag Lifecycle

Flags should have an owner, purpose, creation date, cohort, default value, tracking metrics, and planned retirement date. Temporary rollout flags should be cleaned up once features stabilize; keeping them indefinitely grows state combinations and testing burden.

## 8. Custom Workflows and Policies

Tenant-specific workflows can be modeled using definitions instead of per-customer code. For example, a booking approval workflow might include manager review, finance approval if value exceeds a threshold, and final confirmation.

A workflow definition must specify:

- Allowed states and transitions.
- Conditions/guards for each transition.
- Permitted roles or groups.
- Timeouts, escalations, and overdue actions.
- Idempotency and duplicate event handling.
- Definition version bound to each instance.
- How in-flight instances are handled when a tenant updates the workflow version.

Never let tenants configure workflows that bypass mandatory controls, self-grant permissions, or execute arbitrary code. Domain services must still guard invariants at the final write step.

### 8.1. In-Flight Workflow Versions

If a tenant upgrades a workflow from version 4 to version 5, decide whether instances started on version 4 continue on version 4 or migrate. Typically, in-flight instances pin their starting workflow version to avoid changing semantics mid-flight, while new instances use the new version. Some changes can be safely migrated, but require dedicated tooling and validation.

## 9. Product Version Management: More Than Just Application Version

In multi-tenant SaaS, "which version is a tenant on?" can refer to several distinct version dimensions.

| Version Type | Example | Impact |
| --- | --- | --- |
| Application/build version | `release 2026.11.18` | Runtime code serving requests |
| API contract version | `v1`, `v2` | Client/partner contracts |
| Database schema version | `migration 145` | Data structure |
| Tenant configuration schema | `config schema v3` | How configs are interpreted |
| Configuration version | `tenant config 12` | Effective parameter values |
| Workflow version | `approval flow v5` | Which definition new/active instances use |
| Plugin/extension version | `ERP connector 2.4` | Platform compatibility |
| Feature policy version | `rollout policy 5` | Per-tenant feature availability |

One system can run a single application build while tenants use different configuration/workflow versions. Conversely, a tenant can be pinned to an older API contract even after the backend runtime upgrades, provided compatibility layers remain supported.

### 9.1. Versions Need Owners and Sources of Truth

Every version dimension needs an authoritative store, versioning rules, compatibility policies, and traceability metadata. Never leave versions tracked solely in manual notes or filenames unlinked from running tenants/resources.

## 10. Release Trains and Cohort Rollouts

There are several ways to release versions to tenants.

| Model | How It Works | Advantages | Trade-offs |
| --- | --- | --- | --- |
| Big-bang | All tenants upgrade simultaneously | Minimal time maintaining multiple versions | Large blast radius, hard full rollback |
| Cohort/wave | Upgrade in tenant groups | Limits impact and learns from earlier waves | Must track multiple cohorts |
| Canary tenants | Small representative group upgrades first | Early bug detection | Needs careful cohort choice and metrics |
| Progressive rollout | Increase percentage/groups conditionally | Gradually reduces risk | Requires automation and observability |
| Tenant-pinned release | Tenant stays on a version for a fixed term | Supports strict change-control needs | Creates large version matrix and extends support |

Not every tenant should get unlimited version pinning. Pinning requires valid justification, an expiration date, an owner, support cost accounting, and an upgrade plan.

### 10.1. Selecting a Representative Canary Cohort

Canary cohorts should represent real system diversity: regions, plans, customization levels, data sizes, integrations, and traffic. Picking only small tenants with default configs misses problems on large tenants or complex workflows.

### 10.2. Promotion and Rollback Criteria

Before expanding a wave, check:

- Error rates and p95/p99 latency.
- Transaction correctness and reconciliation.
- Job/queue backlogs, timeouts, and retries.
- Connector/plugin errors.
- Schema migration progress.
- Customer support incidents and tenant-specific anomalies.
- Cost/compute regressions.
- Metrics segmented by cohort and customization level.

Rollbacks must be defined separately for application code, API behavior, feature flags, configuration, and schemas. Not every database migration can run backward; sometimes forward fixes or expand-contract patterns are required.

## 11. Backward Compatibility and Schema Migrations

When the platform upgrades versions, tenants may still rely on older clients, integrations, or workflows. Compatibility must be managed across runtime, APIs, configs, and schemas.

### 11.1. Expand–Migrate–Contract

A standard pattern:

1. **Expand:** add new columns/fields or endpoints compatibly.
2. **Deploy compatible code:** old and new versions operate side by side during transition.
3. **Migrate/backfill:** transform tenant data in batches with checkpoints and retries.
4. **Switch:** move tenants/consumers onto the new schema or contract.
5. **Verify:** check completeness, queries, errors, and performance.
6. **Contract:** remove old fields/APIs only once no supported consumers remain.

### 11.2. Tenant Migration State

Migration progress can be tracked per tenant:

~~~yaml
tenantId: tenant-482
fromSchemaVersion: 7
targetSchemaVersion: 8
status: IN_PROGRESS
checkpoint: batch-0042
startedAt: 2026-11-18T01:00:00Z
lastError: null
~~~

This is an illustrative example. Migrations must be idempotent or use reliable checkpoints, limit concurrency, and support resumption. Never run a massive migration simultaneously for all tenants if it overloads the database or locks shared tables.

### 11.3. Backward Compatibility Is Not Forever

Maintaining legacy APIs/configs/schemas indefinitely bloats runtime complexity. Establish support windows, deprecation notices, telemetry tracking which tenants/clients still use old versions, and time-bound exception processes.

## 12. Configuration Migration and Rollback

Configuration schemas evolve too. For example, version 2 has a single `holdDuration` field, while version 3 splits it into `minimumHold` and `maximumHold`. Define upcasters/defaults and validation to interpret older configurations.

Principles:

- Retain raw/original config versions if needed for auditing and rollback.
- Write safely repeatable migrations.
- Validate migrated configs before activating them.
- Distinguish `null`, missing, and default values.
- Never auto-assign business-impacting values without an explicit decision.
- Support previews and cohort-based migrations.
- Maintain rollback or forward-fix plans.
- Record who/which process migrated the configuration.

Never roll back an old config document if newer product code changed semantics and no longer supports it. In that case, roll back to a compatible code version first or perform a forward correction.

## 13. Extension/Plugin Lifecycle and Compatibility

If the product supports extensions or plugins, manage them as software components with their own dependencies and permissions.

An extension manifest can describe:

- Plugin ID, vendor, and version.
- Platform/API compatibility range.
- Permissions and scopes.
- Required secrets/credentials references.
- Resource/timeout/concurrency limits.
- Event subscriptions or hook points.
- Configuration schema/version.
- Signatures/provenance and approvals.
- Owner, support status, and deprecation date.

Plugins must never automatically receive rights to read every table or call every internal API. Enforce capability-based permissions, appropriate sandboxes/isolation, audits, and quotas. Failing plugins must not crash core requests; timeouts and circuit breakers must protect the host.

### 13.1. Compatibility Matrix

A platform may have to support multiple combinations:

| Platform Runtime | API Contract | Plugin | Config Schema | Status |
| --- | --- | --- | --- | --- |
| R12 | v2 | P3 | C4 | Supported |
| R12 | v1 adapter | P2 | C3 upcast | Transitional |
| R11 | v1 | P2 | C3 | Deprecated |
| R10 | v1 | P1 | C2 | End of support |

This table illustrates the mental model, not a recommendation to keep many parallel version rows alive. Larger matrices increase testing and incident diagnosis costs. Limit supported combinations and maintain retirement plans.

## 14. Data Customization and Custom Fields

Custom fields let tenants add attributes such as department codes, asset groups, or internal contract IDs. However, unrestricted field creation complicates indexing, validation, querying, exports, data governance, and schema evolution.

Define:

- Field types: string, number, date, enum, boolean, or reference.
- Validation: length, range, required, pattern, and allowed values.
- Sensitivity: public, internal, confidential, personal data.
- How much search/filter/sort is supported.
- Indexing and quotas on field counts.
- Versioning and lifecycle when fields are renamed/deprecated.
- API/export representation.
- Tenant scoping and authorization.
- Impact on analytics/warehouses.

Never use custom fields to replace core columns carrying critical invariants/queries. For example, payment status or tenant owner must be explicitly managed domain fields, never arbitrary JSON keys.

## 15. Tenant Isolation Across Every Customization Layer

A severe bug occurs when Tenant A's configuration or extension is used while handling Tenant B's request. This can happen in caches, background jobs, event consumers, plugin contexts, secret lookups, or shared workers.

Principles:

1. Resolve tenants from verified identities.
2. Attach tenant context to every relevant query, job, event, and cache key.
3. Enforce resource ownership in the backend, never relying on the UI.
4. Never trust `tenantId` from payloads without verifying source and permissions.
5. Isolate secrets and connector credentials per tenant.
6. Scope custom fields, templates, workflows, and plugin registrations by tenant.
7. Protect logs/exports from mixing tenant data.
8. Test for cross-tenant access and cache leakage.
9. Audit admins/platform operators whenever they override tenant configuration.
10. Enforce time-bound, justified, reviewed break-glass access.

### 15.1. Caching Configuration Safely

Cache keys must include tenant ID and configuration version, e.g., a conceptual key `tenant/config/12`. When publishing a new version, services can invalidate or read the new version reference. If caches use generic keys like `branding` or `policy`, another tenant could receive the wrong configuration.

Include TTLs/fallbacks and refresh strategies when the configuration service is unavailable. Never use stale configurations indefinitely for security policies or sensitive decisions.

## 16. Tenant-Specific Customization and Multi-Region Data

A tenant may be pinned to a specific region by contract or data regulation. Tenant configuration may hold the data residency region, yet residency must be enforced in provisioning, storage, backups, logging, and processing—not only in the UI.

Manage:

- Tenant region/placement policies.
- Region-specific databases/storage.
- Replication/backup boundaries.
- Encryption key locations if required.
- Service-to-service routes and egress.
- Support/operator access.
- Approved disaster recovery regions.
- Cross-region tenant migration workflows.

A feature flag cannot guarantee data residency. It is an infrastructure and data-placement property that must be controlled at the platform level.

## 17. Tenant Onboarding, Upgrades, and Offboarding

### 17.1. Onboarding

A tenant onboarding flow can include:

1. Create tenant identity and tenant record.
2. Select plan/entitlements.
3. Determine region and data placement.
4. Generate tenant configuration from default/plan templates.
5. Provision databases/schemas/resources if topology requires.
6. Configure domain, identity provider, and secret references.
7. Run validation and smoke tests.
8. Activate feature policies.
9. Record audits and notify completion through product support channels.

Onboarding must be idempotent so retries never create duplicate resources. Provisioning state must be persisted to resume after failures.

### 17.2. Upgrades

Tenant upgrades may simply switch config/feature policies, or require schema/data and plugin migrations. Check compatibility and schedule by cohort.

### 17.3. Offboarding

Offboarding must revoke user/session/API credentials, disable domains/integrations, export or delete data per contract, delete secrets, clean up resources, and verify backups/retention. Never accidentally delete shared data or another tenant's data. Audit records of offboarding actions must be retained per policy.

## 18. Operating Configuration: Audits, Drift, and Change Control

Configuration drift occurs when actual runtime state diverges from the approved version. An admin may edit directly via console; faulty automation may overwrite config; or a service with long-lived caches may keep using an old version.

Requirements:

- Record every change with actor, timestamp, before/after or diff, reason, and approval.
- Compare desired versions against effective versions actively used by services.
- Detect tenants that have not received new configs or have stuck migrations.
- Enforce RBAC separating read/edit/publish/approve permissions.
- Support staged configuration rollouts.
- Maintain immutable version history and controlled restores.
- Never log secrets inside diffs.
- Alert when configurations change outside approved pipelines/policies.

For sensitive configurations, require dual approval or structured organizational change-control workflows.

## 19. Performance and Scaling of Configuration Services

When every request must read tenant configuration, the configuration service can become a hot dependency. Choose distribution strategies carefully:

- Local in-memory caches keyed by tenant/version.
- Distributed caches to offload database reads.
- Push invalidation or events when configs publish.
- Signed/versioned snapshots for workers.
- Preloading configs for high-activity tenants.
- Shorter TTLs for sensitive policies, longer TTLs for rarely changing branding.
- Fallbacks and circuit breakers when the config store fails.

Do not cache everything uniformly. Locale/themes can tolerate longer TTLs; entitlements/security policies need stronger freshness and enforcement. Cache invalidation must handle duplicate events, late-arriving events, and worker restarts.

## 20. Measuring Customization Footprint and Product Fragmentation

A multi-tenant product must know how many variants it is currently supporting.

Useful metrics:

| Metric | Meaning |
| --- | --- |
| Active configuration versions | Number of config versions still in active use |
| Tenant version distribution | Tenant counts across runtime/API/schema versions |
| Feature flag cardinality | Flag count and active combinations |
| Customization footprint | Number of custom fields, workflows, themes, and plugins per tenant |
| Upgrade adoption | Percentage of tenants upgraded per wave |
| Unsupported version count | Tenants still on end-of-support versions |
| Migration failure/retry | Upgrade quality and progress |
| Config propagation delay | Time from publish until tenants apply it |
| Support incidents by customization | Incidents linked to each customization type |
| Cost per tenant/variant | Compute, storage, cache, and support costs |

Do not just count flags. Two independent feature flags create four combinations; ten flags create up to 1,024 theoretical combinations. You do not need to test every combination blindly, but you must manage dependencies, pairwise coverage, and critical cohorts.

## 21. End-to-End Example: Equipment Rental SaaS Platform

Suppose a platform serves three tenant segments:

- Tenant A: large enterprise needing SSO, multi-level approvals, ERP integration, and audit exports.
- Tenant B: mid-sized business using standard approval workflows and basic reporting.
- Tenant C: small shop using automated workflows and simple configuration.

### 21.1. Modeling Differences

| Capability | Tenant A | Tenant B | Tenant C |
| --- | --- | --- | --- |
| Plan | Enterprise | Business | Starter |
| Authentication | SSO + MFA policy | MFA | Password/SSO if provisioned |
| Approval | Multi-step workflow v5 | Standard workflow v3 | Policy-driven auto-approve |
| ERP integration | Connector v2.4 | Disabled | Disabled |
| Analytics | Advanced entitlement | Basic entitlement | Basic summary |
| Branding | Custom theme | Standard theme | Standard theme |
| Retention | Per approved contract | Standard policy | Standard policy |

### 21.2. Conceptual Architecture

~~~mermaid
flowchart TB
    C["Web / Mobile / Partner clients"] --> EDGE["API gateway and identity"]
    EDGE --> RES["Tenant resolver"]
    RES --> APP["Shared application services"]
    APP --> CP["Tenant configuration / entitlement service"]
    APP --> DOM["Domain services"]
    DOM --> DB[("Tenant-aware data layer")]
    APP --> EXT["Extension and connector runtime"]
    CP --> CACHE["Versioned config cache"]
    CACHE --> APP
    EXT --> ERP["Tenant-specific ERP"]
~~~

Shared application services read tenant context and the matching policy version. Domain services still guard invariants. The connector runtime scopes credentials per tenant; config caches key by tenant/version to prevent config bleed.

### 21.3. A Version Upgrade

Suppose the platform releases runtime R13, config schema C5, and workflow engine v6:

1. Run compatibility tests against all supported config schemas.
2. Deploy R13 to staging and internal cohorts.
3. Canary representative tenants across Starter, Business, and Enterprise.
4. Migrate configs from C4 to C5 in batches; validate tenants with custom workflows.
5. Roll out R13 in waves; older workflow instances keep their pinned version if policy specifies.
6. Monitor error rates, latency, migration failures, and connector health per tenant.
7. Pause the wave if thresholds breach; roll back runtime/flags or forward-fix configs per compatibility.
8. Issue deprecation notices and retire old versions on schedule.

Never assume everything rolls back in lockstep. If a schema was expanded and new data already written, rolling back the application may require compatibility adapters or forward fixes.

## 22. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Forking code per tenant | Fragmentation, costly merges and patches | Contract-bound config/extensions; forks as rare exceptions |
| Using feature flags as authorization | Tenants/users can call APIs directly | Backend verifies entitlements and permissions |
| Taking `tenantId` straight from clients | Cross-tenant access | Resolve from verified identity/domains |
| Caching config without tenant/version | Serves wrong tenant's config or stale versions | Key caches by tenant and version |
| Letting tenants customize core invariants | Inconsistent data and business rules | Domain services enforce invariants; bounded policies |
| Storing secrets in plain config | Credential leaks in logs/exports | Secret manager and references |
| Overly privileged plugins | Data leaks or host crashes | Sandboxes, scoped capabilities, quotas, audits |
| Supporting all API/schema versions forever | Bloated test and runtime matrices | Support windows and deprecation |
| Running migrations for all tenants at once | Lock/load spikes and outages | Cohorts, batches, rate limits, checkpoints |
| Not pinning in-flight workflow instances | Running processes change semantics mid-flight | Persist workflow version per instance |
| Flags without owners or removal dates | Growing state combinations and hard-to-reproduce bugs | Flag lifecycles and cleanup |
| Rolling back config incompatible with code | Runtime misinterprets old config | Compatibility matrix and forward-fix plans |
| Not tracking tenant adoption | Tenants stuck on legacy versions | Version distributions and upgrade SLOs |
| No audits on admin edits | Hard to explain config drift | Change history, approvals, and actor logs |
| Deleting tenants while forgetting secrets/exports | Active credentials and leftover data | End-to-end offboarding runbooks across all layers |

## 23. Design and Implementation Process

1. **Inventory variants:** classify branding, locale, policy, feature, workflow, integration, data, and security needs.
2. **Define tenant context:** trusted sources, identity, tenant resolution, and propagation.
3. **Choose customization mechanisms:** config, entitlements, flags, extensions, or plugins per boundary.
4. **Design config schemas:** defaults, override precedence, versioning, validation, and secret references.
5. **Protect domain invariants:** define what tenants may alter vs. what the platform enforces.
6. **Define version policies:** runtime, API, schema, config, workflow, and plugin compatibility.
7. **Design releases:** cohorts, canaries, metrics, stop conditions, and rollback/forward-fix.
8. **Design migrations:** idempotency, checkpoints, rate limits, previews, and reconciliation.
9. **Secure:** tenant isolation, least privilege, plugin sandboxing, auditing, and data residency.
10. **Operate:** caching, invalidation, drift detection, support windows, and offboarding.
11. **Measure:** adoption, config propagation, incidents, customization footprint, and costs.
12. **Review periodically:** retire unsupported flags, extensions, and versions.

## 24. Well-Architected Evaluation

| Lens | Design Questions |
| --- | --- |
| **Reliability** | Are configs/extensions versioned and rollback-safe? Are migrations idempotent? Do canaries track per-tenant errors? Do active workflows keep their versions? |
| **Security** | Is tenant context trustworthy? Are caches/secrets/plugins isolated? Are entitlements enforced server-side? Are admin overrides audited? |
| **Performance Efficiency** | Do config lookups/caches create bottlenecks? Do plugins have timeouts/quotas? Can tenant-specific queries cause noisy neighbors? |
| **Cost Optimization** | Are variants, plugins, versions, and support windows bounded? Are per-tenant/extension costs measured? |
| **Operational Excellence** | Do version catalogs, config drift checks, adoption tracking, migration progress, deprecations, and per-tenant runbooks exist? |

### Acceptance Checklist

- [ ] Tenant context is resolved from verified identity/domains and propagated securely.
- [ ] All resource queries, caches, events, jobs, and secrets are scoped by tenant.
- [ ] Configurations have schemas, defaults, precedence, validation, and immutable versions.
- [ ] Secrets live solely in a secret manager; configs hold references.
- [ ] Entitlements, feature rollouts, and authorization are cleanly separated.
- [ ] Domain services preserve critical invariants regardless of tenant policy overrides.
- [ ] Workflows/plugins have compatibility versions, least privilege, and resource limits.
- [ ] Application, API, schema, config, and plugin versions have owners and sources of truth.
- [ ] Rollouts have cohorts, canaries, metrics, and stop conditions.
- [ ] Migrations include checkpoints, idempotency, validation, and rollback/forward-fix.
- [ ] Support windows and deprecations are published and adoption is tracked.
- [ ] Config drift, admin changes, and overrides are audited.
- [ ] Data residency, retention, and offboarding propagate across all replicas/integrations.
- [ ] Cross-tenant cache/resource access has been tested.
- [ ] Customization footprint, version distribution, incidents, and costs are measurable.

## 25. Applied Exercise

An equipment rental SaaS has 500 tenants. Several customers want to change logos, languages, and currencies; 20 enterprises need multi-level approval workflows; 5 tenants want custom ERP integrations; one large tenant requests pinning the old application version for 6 months due to internal compliance certification. The platform is preparing to upgrade API v1 to v2 and config schema C3 to C4.

Design the following:

1. Classify each requirement as configuration, entitlement, feature flag, workflow extension, connector/plugin, or fork exception.
2. Tenant context model and protections against cross-tenant request/resource access.
3. Versioned config schema with inheritance, validation, and secret references.
4. Policy for managing active workflow instances when a tenant publishes a new workflow version.
5. Cohort rollout strategy for API v2, config C4, and the new runtime.
6. Conditions for allowing a tenant to pin an old version and ways to bound support cost/risk.
7. Migration from C3 to C4 with checkpoints, idempotency, previews, and rollback/forward-fix.
8. Safeguards ensuring ERP plugins cannot access other tenants' data.
9. Metrics tracking adoption, config propagation, extension errors, and active version counts.
10. Conditions under which requests to stay on an old version must be denied or moved to a separate deployment.

A sensible solution uses configuration for branding/locale, versioned workflow definitions for approvals, a connector runtime with per-tenant secrets for ERPs, and time-bound exceptions with an upgrade plan for API/runtime pinning. All commands still pass through authoritative domain services; feature flags never replace authorization, and caches must scope by tenant/version.

**Key takeaway:** tenant customization enables controlled differentiation on a single product; version management ensures those differences can be released, kept compatible, observed, and upgraded. Strong boundaries keep configuration inside validated schemas, extensions inside bounded capabilities, and invariants inside domain services. A sustainable multi-tenant SaaS always knows which version each tenant runs, which values are active, who changed them, how data is isolated, and how to upgrade or roll back safely.
