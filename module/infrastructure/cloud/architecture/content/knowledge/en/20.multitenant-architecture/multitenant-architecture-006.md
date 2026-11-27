# Onboarding, Configuring, Migrating, and Deleting Tenants

In a multi-tenant SaaS platform, a tenant is the boundary representing a customer, organization, or workspace. Each tenant can have its own users, data, configuration, service plan, resource limits, and security policies. As a platform grows, operating tenants becomes a multi-step lifecycle: onboarding new customers, validating eligibility, provisioning resources, configuring, activating, changing plans, migrating data across regions or isolation levels, suspending, and eventually deleting data per policy.

These operations touch many systems: identity, billing, control plane, databases, object storage, queues, search indexes, caches, observability, and support tooling. A process that merely creates a tenant record in a database is insufficient. If a step fails midway, the tenant can end up half-configured; if deleted mistakenly, data can be lost or remain in replicas; if migrated without clear cutover, two locations can accept writes simultaneously.

This lesson belongs to the **Multi-Tenant Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The focus is designing a tenant lifecycle that can be automated, controlled, and recovered; preserving tenant isolation throughout; and balancing reliability, security, scalability, cost, and operational effort through a Well-Architected lens.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Model the tenant lifecycle from provisioning through suspension, migration, and deletion.
2. Distinguish the control plane from the data plane and identify the system of record for tenant metadata.
3. Design onboarding with idempotency, workflow state, retries, compensation, and readiness checks.
4. Manage tenant configuration, features, quotas, secrets, and versioned changes.
5. Plan tenant migrations across shards, databases, regions, or isolation models.
6. Execute controlled cutovers, minimize downtime, prevent split-brain, and verify data integrity.
7. Design suspension, offboarding, and deletion with authorization, retention, auditing, and evidence.
8. Observe the tenant lifecycle, handle stuck tasks, reconcile resources, and optimize operational costs.

## 2. Tenants and the Tenant Lifecycle

### 2.1. A Tenant Is a Governance Entity

A tenant typically represents an organization or customer using the platform. A tenant can own:

- Tenant ID and lifecycle status.
- Domain, branding, locale, timezone, and custom settings.
- Users, groups, roles, and access policies.
- Subscription, billing account, plan, and feature entitlements.
- Data resources: databases/schemas/partitions/object prefixes.
- Quotas, rate limits, storage limits, and concurrency.
- Region, data residency, and infrastructure isolation level.
- Audits, retention, legal holds, and data deletion requests.

A tenant ID is a governance identifier and does not by itself prove the caller has access rights. Every request must still authenticate identity, resolve tenant scope from a trusted source, and verify authorization server-side.

### 2.2. Reference Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATING
    VALIDATING --> PROVISIONING: Accepted
    VALIDATING --> REJECTED: Invalid / policy fail
    PROVISIONING --> CONFIGURING
    CONFIGURING --> READY
    READY --> SUSPENDING
    SUSPENDING --> SUSPENDED
    SUSPENDED --> REACTIVATING
    REACTIVATING --> READY
    READY --> MIGRATING
    MIGRATING --> READY
    READY --> DELETION_PENDING
    SUSPENDED --> DELETION_PENDING
    DELETION_PENDING --> DELETING
    DELETING --> DELETED
    DELETING --> DELETION_BLOCKED: Legal hold / failure
    DELETION_BLOCKED --> DELETING: Cleared / retry
    REJECTED --> [*]
    DELETED --> [*]
~~~

This is an illustrative model; real systems may include extra states like `PROVISIONING_FAILED`, `MIGRATION_ROLLBACK`, `PENDING_PAYMENT`, `ARCHIVED`, or `DELETION_VERIFICATION`. What matters is that states express clear business conditions and define allowed transitions.

### 2.3. Separating Tenant State and Workflow State

Tenant metadata might report `PROVISIONING` while the workflow is at the step of creating a database, creating identity groups, or initializing storage. These are two related yet distinct layers of state:

- **Tenant lifecycle state:** the business state published by APIs and the control plane.
- **Workflow execution state:** technical progress of a single run, including tasks, retries, timeouts, and compensation.
- **Resource state:** actual state in the database, storage, identity provider, DNS, or billing.

Do not mark a tenant `READY` simply because a workflow execution ended successfully if an essential resource has not been verified. Likewise, a workflow timeout does not prove resources were not created; reconcile by resource ID and idempotency key.

## 3. Control Plane and Data Plane

### 3.1. Control Plane

The control plane manages tenants and their lifecycles: accepting requests, verifying identity and contracts; creating tenant records, plans, regions, and placements; provisioning database/schema/storage/identity resources; managing configuration, quotas, feature flags, and statuses; orchestrating migrations, suspensions, restores, and deletions; logging audits, managing operational tasks, and reconciling resources.

### 3.2. Data Plane

The data plane serves tenant business requests: authenticating requests and resolving tenant context; routing to designated databases/shards/regions; enforcing tenant isolation and authorization; reading/writing business data; and enforcing per-tenant quotas and load limits.

~~~mermaid
flowchart TB
    ADMIN[Admin / Signup API] --> CP[Control Plane]
    CP --> REG[(Tenant Registry)]
    CP --> WF[Lifecycle Workflow]
    WF --> IDP[Identity Provider]
    WF --> BILL[Billing]
    WF --> PROV[Infrastructure Provisioner]
    PROV --> DB[(Database / Shard)]
    PROV --> OBJ[(Object Storage)]
    USER[Tenant User] --> EDGE[API Gateway]
    EDGE --> DP[Data Plane]
    DP --> REG
    DP --> ROUTER[Tenant Router]
    ROUTER --> DB
    DP --> CACHE[(Cache)]
~~~

The control plane holds high privileges and can control many tenants. Strictly isolate permissions, workload identities, approvals, and audits. A bug or compromise in the control plane has a much wider impact than one affecting a single tenant.

### 3.3. Tenant Registry

The registry is the authoritative source for routing and lifecycle metadata. A reference record:

~~~json
{
  "tenantId": "tenant_7f31",
  "displayName": "Example Organization",
  "status": "READY",
  "plan": "BUSINESS",
  "region": "ap-southeast-1",
  "deploymentModel": "SHARED_DATABASE",
  "databasePlacement": {
    "clusterId": "cluster_03",
    "shardId": "shard_12"
  },
  "configVersion": 18,
  "lifecycleVersion": 6,
  "createdAt": "2026-11-18T05:00:00Z"
}
~~~

Never let clients send `databasePlacement` and trust it directly. The control plane manages placement, and the data plane reads only verified mappings. The registry can be cached to reduce latency, but placement changes, suspensions, and deletions require invalidation/versioning so requests do not keep routing to old locations.

## 4. Onboarding New Tenants

### 4.1. Steps in Onboarding

A typical onboarding flow:

1. Receive the request and generate an onboarding request ID.
2. Authenticate the requester, organization, and tenant creation permissions.
3. Check for duplicates by domain, legal entity, external customer ID, or idempotency key.
4. Validate plan, billing, region, data residency, and terms.
5. Select placement/deployment model.
6. Create the tenant record in a non-ready state.
7. Provision resources and identity boundaries.
8. Apply default configurations, quotas, features, and secret references.
9. Initialize required schemas, buckets/prefixes, encryption keys, or seed data.
10. Run readiness, tenant isolation, connectivity, and permission checks.
11. Transition to `READY`, enable login, or send a welcome notification.

~~~mermaid
flowchart TD
    START[Signup request] --> VALIDATE[Verify identity, organization, plan]
    VALIDATE --> DUP{Already exists?}
    DUP -->|Yes| RETURN[Return existing request / conflict]
    DUP -->|No| CREATE[Create tenant PENDING]
    CREATE --> PLACE[Choose region and placement]
    PLACE --> RES[Provision identity, database, storage]
    RES --> CONFIG[Apply config, quota, features]
    CONFIG --> CHECK[Readiness and isolation checks]
    CHECK -->|Pass| READY[Mark tenant READY]
    CHECK -->|Fail| RECOVER[Retry / compensate / manual review]
    RECOVER --> CONFIG
~~~

### 4.2. Idempotency During Onboarding

Signup or onboarding requests may be retried due to client timeouts, duplicate webhooks, or operators clicking submit multiple times. Never let each retry create a new tenant.

You need an `idempotencyKey` generated by the caller or control plane; unique constraints at the appropriate scope; stored request results and statuses so retries return the original outcome; provisioning steps that also use deterministic resource names/IDs for lookup and reuse; and separation between retrying the same request vs. creating a different tenant with the same domain.

Idempotency keys do not replace business-rule duplicate checks. Someone could send two different keys for the same organization; the control plane must still handle duplicate organizations/domains per policy.

### 4.3. Sequential and Parallel Provisioning

Some steps have dependencies: generate the tenant ID before creating namespaces; create keys before configuring encryption; create databases/schemas before running migrations. Independent steps such as creating identity groups and creating buckets can run in parallel as long as they stay within quotas.

Parallelism reduces onboarding time but increases the number of failure branches to handle. Define which steps can be retried, which need compensation, and the criteria for aggregating readiness.

### 4.4. Non-Ready States

A tenant becomes `READY` only after mandatory checks pass. APIs must block tenant access to the data plane while metadata is still in `PROVISIONING` or `CONFIGURING`. Return progress status, `retry-after`, or an onboarding tracking link; never return internal details like credentials or resource admin endpoints.

## 5. Tenant Configuration and Feature Entitlements

### 5.1. Configuration Categories

| Category | Example | Management Approach |
|---|---|---|
| Platform default | Default locale, baseline features | Platform-managed templates/versions |
| Plan entitlement | Max users, advanced features | Billing/entitlement service |
| Tenant override | Branding, timezone, retention preferences | Validated tenant configuration |
| Security policy | SSO required, IP allowlist, MFA | Audited policies with separate edit permissions |
| Runtime setting | Rate limits, concurrency, routing | Versioned config service/cache |
| Secret | API credentials, signing key references | Secret manager; never plaintext in registry |

### 5.2. Configuration Versioning

Every config change should record version, actor/process, timestamp, reason, and approval source. Consumers can receive `configVersion` in the tenant context or cache keys to detect stale config.

Avoid letting services read and merge multiple config files in unclear orders. Define explicit precedence, e.g., `platform defaults -> plan entitlements -> tenant overrides -> enforced security policies`.

Mandatory security policies must take precedence over tenant overrides, which must not be allowed to relax them.

### 5.3. Configuration Rollout

For changes impacting many tenants:

1. Validate schemas and policies.
2. Dry-run to identify impacted tenants.
3. Test on internal/canary tenants.
4. Roll out in batches or cohorts.
5. Monitor errors, latency, quotas, and results.
6. Halt rollout if thresholds are breached.
7. Roll back or forward-fix with audits.

Breaking configuration changes require explicit migrations. Never assume every service reads the new version at the exact same instant.

## 6. Managing Quotas and Placement

### 6.1. Per-Tenant Quotas

Quotas can apply to user/project/listing/object counts; storage bytes and file counts; API request rates and concurrency; background jobs, queue messages, and compute units; and connections, subscriptions, exports, or integrations.

Quotas must be enforced in the data plane or resource-owning service, not merely displayed in the billing portal. Distributed counters may be eventually consistent; operations requiring hard limits need atomic reservation or authoritative checks.

### 6.2. Placement

The control plane decides which region, cluster, shard, database/schema, or dedicated environment a tenant lives on based on data residency and contracts; SLOs and user latency; size/throughput and isolation level; plan/entitlements; capacity, quotas, and failure domains; and backup, restore, and DR capabilities.

Placement should be represented by a versioned, audited mapping read by the data plane via a trusted router. Never derive placement directly by hashing `tenantId` if the system needs to move tenants between shards without changing their IDs.

## 7. Suspension and Reactivation

### 7.1. When Is Suspension Used?

A tenant may be suspended due to customer request, billing issues, policy violations, security incidents, or investigations. Suspension differs from deletion: data is typically retained per contract and retention rules.

Before suspending, define the scope: block logins or block writes only; how existing tokens are revoked; whether background jobs and scheduled tasks stop; whether webhooks/integrations are paused; whether users keep export or read-only access; and how long data and backups must be retained.

### 7.2. Suspension Process

~~~mermaid
flowchart TD
    REQUEST[Authorized suspension request] --> CHECK[Validate reason and approval]
    CHECK --> MARK[Set SUSPENDING]
    MARK --> BLOCK[Block new sessions and writes]
    BLOCK --> REVOKE[Revoke credentials / disable integrations]
    REVOKE --> DRAIN[Drain or cancel background work]
    DRAIN --> VERIFY[Verify access blocked and data retained]
    VERIFY --> SUSPENDED[Set SUSPENDED]
~~~

Update the control plane state early to block new requests, then execute credential revocation, job stopping, and verification. If any step fails, keep the tenant in `SUSPENDING` or `SUSPENSION_BLOCKED`; never declare suspension complete while sessions or API keys still work unexpectedly.

### 7.3. Reactivation

Reactivation requires verifying the suspension cause is resolved, subscriptions are valid, credentials are properly re-issued, and data remains in the expected state. Never automatically restore revoked sessions/tokens. Re-provisioning integrations and running health checks may be required before transitioning to `READY`.

## 8. Tenant Migration

### 8.1. Reasons to Migrate

Tenants may need to migrate from a shared database to a dedicated database due to scale or isolation needs; from an overloaded shard to a shard with spare capacity; to another region for data residency or latency; to a new database version or storage tier; from a shared schema to a dedicated schema/database; or to a new deployment cell to reduce blast radius.

Migration is more than copying tables. It requires migrating data, indexes, constraints, objects, search projections, caches, credentials, routing metadata, scheduled jobs, integration endpoints, and related resources.

### 8.2. Migration Strategies

| Strategy | Approach | Advantages | Trade-offs |
|---|---|---|---|
| Offline/cold migration | Stop writes, copy, verify, cut over | Easier to guarantee consistency | Longer downtime, requires maintenance window |
| Snapshot + delta | Copy snapshot then apply subsequent changes | Shortens downtime | Complexity in CDC, ordering, and replay |
| Dual-write | Write simultaneously to source/target during transition | Can shrink cutover duration | Prone to data drift, needs idempotency and reconciliation |
| Blue-green | Stand up full target, verify, shift traffic | Faster routing rollback if source stays intact | Parallel resource cost; must handle write consistency |
| Tenant-by-tenant | Move one tenant/cohort at a time | Small blast radius and easy to observe | Many operational repetitions |

No migration strategy is inherently safe on its own. Choose based on acceptable downtime, write rates, data volume, CDC capability, consistency needs, and rollback feasibility.

### 8.3. Phased Migration Process

~~~mermaid
flowchart TD
    PLAN[Inventory and migration plan] --> PREP[Prepare destination]
    PREP --> SNAP[Copy snapshot]
    SNAP --> CATCH[Replicate delta changes]
    CATCH --> VERIFY[Validate counts, checksums, invariants]
    VERIFY --> READY{Within acceptance criteria?}
    READY -->|No| FIX[Fix or restart migration]
    FIX --> CATCH
    READY -->|Yes| FREEZE[Freeze writes / drain in-flight requests]
    FREEZE --> FINAL[Apply final delta and verify]
    FINAL --> ROUTE[Switch tenant placement]
    ROUTE --> SMOKE[Smoke test and monitor]
    SMOKE -->|Pass| DONE[Complete migration]
    SMOKE -->|Fail| ROLLBACK[Controlled rollback / forward recovery]
~~~

Detailed steps:

1. **Inventory:** identify all tenant-owned resources, sizes, change rates, dependencies, and owners.
2. **Prepare:** provision destination, schemas, indexes, encryption, IAM, quotas, and networking.
3. **Snapshot:** copy consistent data or use supported snapshots/backups.
4. **Delta replication:** transfer changes occurring after the snapshot via CDC/logs or migration tooling.
5. **Validation:** compare row counts, partition checksums, aggregates, constraints, and sample records.
6. **Quiesce:** block new writes or put the tenant in maintenance/read-only mode; drain in-flight requests.
7. **Final sync:** apply final deltas, confirming lag is within threshold.
8. **Cutover:** switch tenant placement/router using an explicit version or epoch.
9. **Verification:** smoke-test reads/writes, authorization, integrations, background jobs, and metrics.
10. **Cleanup:** delete the old source only after the safety retention period and rollback window close.

### 8.4. Preventing Split-Brain

During migration, a major risk is source and destination both accepting writes independently, causing two divergent histories.

Mitigations:

- Designate a single write owner at any point in time.
- Use a migration epoch/version to reject requests hitting the old placement after cutover.
- Block writes and drain in-flight requests before the final sync.
- Use idempotency keys for retryable commands.
- Use fencing tokens or routing generations so stale requests cannot write to the source after ownership shifts.
- Ensure background workers, queue consumers, and scheduled jobs also follow the new placement.

Updating the registry before all consumers update can create an inconsistent routing window. Use router services, cache versioning, epoch validation, and rollout procedures to coordinate.

### 8.5. Rollback Is Not Always Just Flipping a Route

Once the destination accepts new writes, reverting to the old source can lose post-cutover data. Before migrating, determine when rollback remains safe; whether reverse sync exists; how writes are frozen and deltas merged on rollback; criteria deciding rollback vs. forward-fix; and who has approval authority.

Keeping the old source read-only during the rollback window can help, but requires managing credentials and cost. Once new writes happen on the destination, forward recovery is usually safer than blindly flipping routes back.

## 9. Managing Configuration During Migration

Migrations often change multiple metadata values: database host/cluster, schema version, region, encryption key, cache namespace, queue topic, and endpoints. Never update individual services manually.

A migration manifest might record:

~~~json
{
  "migrationId": "mig_2026_031",
  "tenantId": "tenant_7f31",
  "from": {
    "region": "ap-southeast-1",
    "shardId": "shard_12"
  },
  "to": {
    "region": "ap-southeast-2",
    "shardId": "shard_04"
  },
  "phase": "CATCHING_UP",
  "epoch": 3,
  "startedAt": "2026-11-18T05:00:00Z"
}
~~~

The manifest is orchestration metadata; secrets and connection strings belong in a role-restricted secret manager/config service. Services read tenant placement under a single contract/version rather than inferring hosts themselves.

## 10. Deleting Tenants and Offboarding

### 10.1. Tenant Deletion Is a High-Consequence Workflow

Tenant deletion can involve data in primary databases, read replicas, and shards; object storage, file uploads, exports, and backups; caches, search indexes, analytics projections, and data lakes; queues, topics, DLQs, scheduled jobs, and workflow history; identity providers, users, groups, API keys, OAuth clients, and certificates; billing, subscriptions, invoices, and audits; third-party integrations, webhooks, and support systems.

A single `DELETE` on a tenant row in the registry does not remove all of the above. Orphaned objects, indexes, logs, or backups may still hold tenant data.

### 10.2. Distinguishing Deletion States

Use states such as `DELETION_REQUESTED`, `DELETION_PENDING`, `DELETION_BLOCKED`, `DELETING`, `DELETION_VERIFICATION`, and `DELETED`. Each state needs well-defined entry/exit conditions and an operational owner.

`DELETED` must have an exact meaning. If immutable backups persist until retention expires, explicitly state that data is isolated and scheduled to expire, if policy/contract permits. Never claim complete physical deletion while copies remain retained.

### 10.3. Offboarding Flow

~~~mermaid
flowchart TD
    REQ[Deletion request] --> AUTH[Verify authority and scope]
    AUTH --> HOLD{Legal or retention hold?}
    HOLD -->|Yes| BLOCK[DELETION_BLOCKED]
    HOLD -->|No| PEND[Deletion pending / notice period]
    PEND --> APPROVE[Approval and final confirmation]
    APPROVE --> SUSPEND[Disable access and integrations]
    SUSPEND --> EXPORT[Optional customer export]
    EXPORT --> DELETE[Delete tenant data and resources]
    DELETE --> VERIFY[Verify primary and derived stores]
    VERIFY -->|Complete| CERT[Record evidence / deletion certificate]
    CERT --> DONE[DELETED]
    VERIFY -->|Incomplete| BLOCK
~~~

The exact order depends on contracts and retention policies. Determine data exports, unpaid invoices, legal holds, mandatory audits, and backup expiration schedules upfront.

### 10.4. Authentication and Approval

Deletion requests must be verified by an authorized tenant representative or contractual process. For large tenants or wide-impact operations, require dual approval (two independent approvers) and re-confirmation via a trusted channel.

Never let a request containing just `tenantId` trigger deletion. Verify identity, tenant ownership, role, reason, approval records, and resource scope. Write immutable audits per policy.

### 10.5. Deleting Data in Replicas and Backups

- Delete/invalidate caches and search documents.
- Remove the tenant from analytics projections, data lakes, and exports per policy.
- Stop queue consumers and scheduled tasks so data is not recreated post-deletion.
- Delete objects and aborted multipart uploads.
- Revoke identities, API credentials, webhooks, and integrations.
- Define handling for backup snapshots, PITR logs, and archives.
- Prevent restoring old backups from resurrecting deleted tenants.

If a shared backup contains multiple tenants, you cannot trivially delete one tenant's data selectively from an immutable snapshot. Use retention policies, cryptographic erasure, or restore-and-purge workflows depending on architecture and legal obligations; decisions must be signed off by security/legal specialists.

### 10.6. Cryptographic Erasure

In some designs, tenant data is encrypted with a dedicated data encryption key or per-tenant envelope key. Once deletion is approved, destroying the key renders ciphertext copies unreadable provided no usable key copy remains.

This works only if the key is strictly scoped to the data slated for deletion; no key copies linger in backups, exports, caches, or logs; no sensitive plaintext data lives in other systems; and key destruction is audited and meets legal/contractual standards.

Destroying a key does not delete metadata, logs, or plaintext copies. Never cite cryptographic erasure as a blanket guarantee without auditing the full data lifecycle.

## 11. Retention, Legal Hold, and Data Export Rights

### 11.1. Retention

Retention specifies how long data is kept and for what purpose. It can differ across business data, invoices, audits, logs, backups, and telemetry. Deletion workflows must consult policy by data type and jurisdiction.

### 11.2. Legal Hold

Legal holds or investigations can block deleting certain data. When a hold applies, record exact scope, approver, and start time; lock only the necessary data; proceed with deleting non-held resources if policy allows; block transition to `DELETED` until resolved; and audit hold placement, changes, and removal.

### 11.3. Pre-Offboarding Exports

Customers may need to export data before tenant deletion or contract expiration. Exports must verify requester and permissions; specify format, scope, schema/version, and size limits; encrypt files with time-bound links and download audits; restrict support/operator access; and set retention on temporary exports to purge them after expiry.

Exports must never become a backdoor for users to pull data outside tenant scope.

## 12. Workflow Orchestration and Resilience

### 12.1. Why Are Workflows Needed?

Provisioning, migration, and deletion involve many asynchronous steps, some taking minutes or hours. Workflow engines manage state, timeouts, retries, waits, callbacks, parallel tasks, and execution history. Never hold an HTTP request or function open for an entire long-running process.

### 12.2. Idempotent Tasks

Every provision/delete operation needs a deterministic resource key. For example, a step creating a tenant bucket should not create a new bucket on every retry; before creating, check whether the resource already exists with the right owner/tenant tags.

External side effects need idempotency keys or reconciliation. A timeout does not prove an operation did not occur.

### 12.3. Retries and Compensation

Retry transient failures like network resets or throttling with bounded retries and backoff. Never retry permission, quota, invalid config, or policy errors indefinitely. Compensation fits reversible steps such as releasing reservations; however, not every data deletion can be undone.

For deletion, once data is safely deleted, workflows should not try to roll back by recreating an empty tenant. Use progress states, backup/recovery policies, and separate approvals.

### 12.4. Manual Intervention

States such as `MIGRATION_BLOCKED`, `DELETION_BLOCKED`, or `PROVISIONING_FAILED` require an owner, reason, deadline, and runbook. Operator actions require authorization, reason codes, audits, and idempotency. Never directly edit registry state to force a workflow to finish before actual resources are reconciled.

## 13. Security and Tenant Isolation Across the Lifecycle

### 13.1. Tenant Context

Tenant context should come from verified identity/tokens and control-plane mappings. Never trust caller-supplied `tenantId` headers or query parameters without verification. All data access must enforce tenant scope under fail-closed principles.

### 13.2. Isolation During Provisioning

- Attach owner/tenant tags to resources.
- Use dedicated IAM roles or per-tenant policy conditions where feasible.
- Create namespaces, schemas, databases, or keys matching the isolation model.
- Verify bucket policies, database roles, and encryption contexts.
- Never reuse secrets or credentials across tenants when isolation requires separation.
- Run isolation tests before marking a tenant `READY`.

### 13.3. Isolation During Migration

Migrations must verify both source and destination belong to the exact same tenant. Exports/imports must use scoped job identities, encrypted temp files, and short retention. Never log data contents in error or progress output.

### 13.4. Isolation During Deletion

Deleting by tenant ID must never wildcard into another tenant. Use resource inventories based on registry/ownership tags, resource-type allowlists, dry-runs, and pre-execution counts. For destructive actions, require confirmation of resource counts and verified tenant name.

## 14. Observability, Auditing, and Reconciliation

### 14.1. Lifecycle Metrics

| Group | Metric | Purpose |
|---|---|---|
| Onboarding | Requests accepted/rejected, provisioning duration | Measure activation time and errors |
| Provisioning | Resource creation success/failure, retries, orphan count | Detect half-provisioned resources |
| Configuration | Config version lag, rollout failures | Track configuration application |
| Suspension | Time to block access, remaining active sessions | Verify access lockout |
| Migration | Bytes copied, delta lag, validation mismatches, cutover duration | Measure progress and correctness |
| Deletion | Resource inventory, deletion progress, blocked age | Track deletion and retention |
| Isolation | Cross-tenant access denials/attempts, policy violations | Detect security flaws |
| Cost | Resource cost by tenant, idle resources, storage growth | Control costs |

### 14.2. Correlation and Auditing

Every lifecycle request should carry a `lifecycleRequestId` or `operationId` across workflows, resource provisioners, and logs. Audits must show who requested it, which tenant, which action, reason, approvals, before/after versions, and outcome.

Audits should never contain secrets, tokens, full database connection strings, or sensitive payloads. Audit data may require separate retention and restricted access.

### 14.3. Reconciliation

Run periodic reconciliation between the tenant registry and actual resources:

- `READY` tenants must have all mandatory databases, buckets, identities, and routing resources.
- Resources carrying a tenant tag whose tenant no longer exists in the registry must be investigated.
- `DELETED` tenants must have zero active credentials, queue consumers, or data-accessing resources left.
- Completed migrations must have consistent placement mappings with the source no longer accepting writes.
- Quotas/billing must reflect active resources.

Reconciliation needs dry-run modes, orphan-handling owners, approval before deleting unattributed resources, and audited outcomes.

## 15. Capacity, Blast Radius, and Cost

### 15.1. Shared Resources

Tenant lifecycles can generate large bursts if many tenants onboard simultaneously. Limit concurrency per region/cluster to avoid simultaneous provisioning exhausting quotas or overloading the control-plane database.

### 15.2. Dedicated Resources

Dedicated tenants may require separate databases, keys, clusters, or networks. Costs encompass not only compute/storage but also backups, monitoring, patching, DR, idle capacity, and on-call effort. Automating provisioning/deletion and standardizing templates reduce manual work.

### 15.3. Migration Capacity

Snapshot copies and delta replication consume I/O, CPU, network, and storage on both source and target. Running migrations in bulk can contend with business traffic. Limit concurrent tenant migrations; pick low-traffic windows; throttle copies and delta applies; monitor replication lag and database headroom; account for cross-zone/region transfer costs; and include pause/resume and checkpoints.

### 15.4. Deletion and Cleanup

Deletion workflows also create load: scanning objects, dropping partitions, rebuilding indexes, revoking keys, and cleaning up backup metadata. Unthrottled mass deletions can impact remaining tenants on shared infrastructure. Batch, rate-limit, and measure impact.

## 16. Runbooks for Common Scenarios

### 16.1. Stuck Onboarding

1. Look up `lifecycleRequestId` and tenant state.
2. Identify the last succeeded task and created resource IDs.
3. Check quotas, IAM, networking, billing, and provider errors.
4. Verify whether retrying the task is idempotent.
5. Resume the appropriate task or escalate to manual review; never blindly restart the entire workflow.
6. Transition to `READY` only after readiness and isolation checks.

### 16.2. Migration Lag Not Decreasing

1. Check source write rate, CDC throughput, and target apply rate.
2. Inspect connectors, partitions, networking, and quotas.
3. Reduce concurrent migrations or throttle background load.
4. Compare remaining time against the migration window.
5. Never cut over while delta lag exceeds acceptance criteria.
6. Defer migration or re-plan capacity if unable to catch up safely.

### 16.3. Failed Cutover

1. Determine whether the tenant sits on source or destination and check current epoch.
2. Freeze writes on both sides if the write owner is uncertain.
3. Inspect in-flight requests, queue consumers, and scheduled tasks.
4. Reconcile deltas and versions before deciding rollback vs. forward-fix.
5. Switch routing only when mappings and fencing tokens are consistent.
6. Run smoke tests, notify stakeholders, and record audits.

### 16.4. Blocked Deletion

1. Verify the reason: legal hold, retention, pending export, or provider error.
2. Explicitly identify which resources may be deleted and which must remain.
3. Confirm approval to lift holds if applicable.
4. Retry safe steps, resolve provider errors, or escalate to manual action.
5. Re-run inventory and mark `DELETED` only when all criteria pass.

## 17. Common Mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| Creating tenant record and immediately marking `READY` | Data plane accesses unready resources | Readiness gates and state machines |
| Non-idempotent onboarding | Retries create duplicate tenants/resources | Idempotency keys, unique constraints, deterministic resource IDs |
| Config scattered across individual services | Version drift, hard rollbacks | Versioned tenant registry/config service |
| Trusting `tenantId` from requests | Cross-tenant access | Resolve context from identity and server-side authorization |
| Migrating by copying and flipping DNS immediately | Lost deltas, split writes, or stale data | Snapshot + delta + quiesce + validation + epoch cutover |
| Forgetting background workers during migration | Jobs keep writing to old source | Update routing for APIs, workers, schedulers, and queues |
| Assuming rollback only needs a placement change | Loses data created at destination | Planned reverse sync or forward recovery |
| Deleting tenant only in the registry | Orphaned data in DB, objects, caches, queues, backups | Resource inventory and deletion verification |
| Ignoring legal holds/retention | Breaches contracts or preservation duties | Policy gates and approvals |
| Treating `DELETED` as instant disappearance of all backups | Inaccurate deletion claims | Define backup lifecycles and expiration schedules |
| No orphan resource reconciliation | Wasted cost and larger attack surface | Scheduled reconciliation and owners |
| Running unbounded concurrent lifecycle jobs | Quota exhaustion impacting other tenants | Per-region and per-cell concurrency/rate limits |

## 18. Well-Architected Evaluation

| Pillar | Question | Measures and Trade-Offs |
|---|---|---|
| **Operational Excellence** | Who owns workflows, tenant registry, runbooks, and reconciliation? | Automation, audits, lifecycle metrics; many states require solid diagnostic tooling |
| **Security** | Who can create, migrate, suspend, and delete tenants? | Least privilege, approvals, tenant scoping, secret managers, resource ownership tags |
| **Reliability** | How are retries, timeouts, partial provisioning, cutover, and deletion failures recovered? | Idempotency, checkpoints, state machines, readiness gates, reconciliation |
| **Performance Efficiency** | Do provisioning/migrations degrade the data plane? | Throttling, batching, capacity windows, placement-aware routing |
| **Cost Optimization** | Are there orphans, idle dedicated resources, or over-retained backups? | Resource inventories, lifecycle cleanup, per-tenant cost attribution |
| **Sustainability** | Are unnecessary data copies, jobs, or idle resources kept running? | Incremental migrations, sensible retention, controlled cleanup |

Lifecycle automation cuts manual toil, yet control plane permissions are extremely powerful. Enforce proportional change controls, audits, approvals, and blast-radius limits.

## 19. Applied Exercises

### Exercise A — Onboarding Retry

A signup request times out after the database and bucket were created, before the API returns a response. The client resends the same request.

**Question:** How do you avoid creating a second tenant and bucket?

**Hint:** Use an onboarding idempotency key, a stable tenant ID, deterministic resource names, verify resource ownership, and resume from the persisted lifecycle state. Never blindly re-run the whole workflow.

### Exercise B — Readiness

Identity groups are created and the database is reachable, yet the bucket policy failed to apply. The workflow reports partial success.

**Question:** Can the tenant transition to `READY`?

**Hint:** No, if the bucket policy is mandatory. Keep the tenant in `CONFIGURING`/`PROVISIONING_FAILED`, retry or manually repair, then re-run readiness and isolation checks.

### Exercise C — Dual-Writer Migration

A tenant's routing switched to the new shard, yet an old worker keeps writing to the source shard.

**Question:** What are the risks and mitigations?

**Hint:** Split-brain and lost updates when the source is left behind. Use migration epochs/fencing, drain or pause workers, designate one write owner, verify all consumers/schedulers, and reconcile deltas before cutover.

### Exercise D — Deletion and Backups

A tenant is marked `DELETED`, yet shared backup snapshots still retain the tenant's data until the 90-day retention ends.

**Question:** What status and controls must be disclosed?

**Hint:** Clearly define `DELETED` for active systems vs. backup copies; isolate backups per policy, guard restores so deleted tenants are never resurrected, document expiration schedules and evidence. Never claim all copies were physically erased immediately.

### Exercise E — Legal Hold

A tenant admin requests deletion of all data, yet part of the audit data is under legal hold.

**Question:** How should the workflow behave?

**Hint:** Authenticate the requester, scope the hold precisely, delete permitted data, transition held portions to `DELETION_BLOCKED`/retention state, preserve approvals, and proceed only after the hold is validly lifted.

### Exercise F — Cost of Orphaned Resources

A tenant was deleted, yet a bucket, queue, and encryption key remain with no logged owner.

**Question:** What needs to be added to the design?

**Hint:** Resource inventories, mandatory tenant/operation tags, deterministic names, deletion checklists, orphan reconciliation, audits, and explicit owners per resource type. Verify before deleting unattributed resources.

## 20. Pre-Operation Checklist for Tenant Lifecycle

- [ ] Tenant ID, owner, plan, region, deployment model, and system of record are defined.
- [ ] Lifecycle state machine defines valid transitions, error states, and manual intervention.
- [ ] Control plane and data plane have clear permission, network, and responsibility boundaries.
- [ ] Onboarding includes authentication, idempotency, duplicate checks, and readiness gates.
- [ ] Provisioning uses deterministic resource IDs/ownership tags and supports retries/compensation.
- [ ] Configs, entitlements, quotas, and secrets have versioning, precedence, audits, and rollouts.
- [ ] Data plane resolves tenant context from trusted identity; all queries preserve tenant scope.
- [ ] Suspension revokes sessions/tokens, halts jobs, and verifies access lockout.
- [ ] Reactivation checks root cause, subscriptions, credentials, and health.
- [ ] Migrations include inventory, snapshots, delta sync, validation, quiesce, and cutover epochs.
- [ ] One write owner is enforced across all migration phases; split-brain is prevented.
- [ ] Rollback windows, reverse sync, or forward recovery are decided upfront.
- [ ] Deletion verifies authority, legal holds, exports, retention, and approvals.
- [ ] Deletion inventory covers databases, objects, caches, search, queues, identity, logs, and backups.
- [ ] `DELETED` has an exact definition; backup expiry and restore-purge policies are documented.
- [ ] Lifecycle workflows have idempotency, retry budgets, checkpoints, timeouts, and manual recovery.
- [ ] Audits, correlation IDs, dashboards, alerts, and resource reconciliation exist.
- [ ] Provisioning, migration, and deletion enforce per-region/per-cell concurrency and rate limits.
- [ ] Resource costs are attributed to tenants/owners with orphan cleanup.
- [ ] Drills have been run for failed onboarding, failed migration, cutover rollback, suspension, and blocked deletion.

**Key takeaway:** the tenant lifecycle is a stateful governance workflow spanning multiple systems and security boundaries. Onboarding requires idempotency and readiness; configuration requires versioning and policy precedence; migration requires snapshots, deltas, validation, a single write owner, and fenced cutover; deletion requires verification, retention/legal holds, inventory, and evidence across replicas. When these stages are well-orchestrated and observable, a platform can serve multiple tenants safely, scale under control, and minimize operational risk.
