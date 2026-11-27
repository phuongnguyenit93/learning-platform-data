# Rightsizing, Scheduling, and Auto-Reclamation of Resources

## 1. Why Manage Resource Lifecycles and Sizing?

The cloud lets you provision compute, databases, disks, networks, caches, and many other services on demand. That same flexibility creates waste: resources provisioned larger than the workload needs, left running outside usage hours, or abandoned after experiments with no remaining owner. Idle resources can still incur compute, storage, IP, backup, license, data transfer, and observability costs.

**Rightsizing** adjusts resource configurations to fit the workload and service quality requirements. **Scheduling** automates starting, stopping, scaling, or shifting workloads according to known usage windows. **Auto-reclamation** automatically detects and reclaims expired or unneeded resources under defined policies.

In the **CLOUD_ARCHITECTURE** module, architectures are designed from business requirements down to networking, compute, data, and deployment models while balancing reliability, security, scalability, cost, and operations. Cost optimization is not merely shrinking machine sizes. It must preserve SLOs, protect data, maintain recoverability, and limit environmental impact from unnecessary resources.

After this lesson, you will be able to analyze utilization, saturation, latency, and demand before rightsizing; size compute/storage/databases to match workloads; design start/stop schedules accounting for environments, timezones, holidays, and exceptions; identify which resources can be stopped and which state must be retained; apply tags, owners, TTLs, budgets, and auto-reclamation; detect orphaned/idle resources; integrate cleanup with IaC, CI/CD, approvals, backups, and auditing; and evaluate cost, reliability, security, and sustainability through Well-Architected principles.

## 2. Distinguishing the Three Optimization Mechanisms

| Mechanism | Key Question | Example |
|---|---|---|
| **Rightsizing** | Is the resource too large or too small for the workload? | A 16-vCPU VM typically uses only 10% CPU and low RAM |
| **Scheduling** | When does the resource need to run? | Dev environments only need to run during working hours |
| **Auto-reclamation** | Which resources have outlived their purpose and can be reclaimed? | A preview environment for a PR closed three days ago |

These three mechanisms complement one another. Rightsizing cuts cost while workloads run; scheduling cuts unnecessary runtime; reclamation cleans up resources lacking an owner or purpose. All three must rest on inventories, telemetry, lifecycle metadata, and clear policies.

## 3. Starting with Inventory and Cost Attribution

### 3.1. Know What You Have

Before downsizing or stopping resources, compile an inventory by provider/account/project/subscription and region; resource type, SKU/size, quantity, and lifecycle state; service, environment, owner, cost center, and purpose; created time, last modified, last activity, and expiry; dependencies including networking, disks, databases, keys, backups, DNS, and workloads; data classification, retention, and deletion protection; and monthly cost, peak usage, and utilization windows.

An untagged resource is not necessarily useless; it may be foundational or provider-managed. Investigate ownership before reclaiming anything.

### 3.2. Minimum Tagging

~~~yaml
service: booking-platform
environment: dev
owner: booking-team
cost_center: product-engineering
purpose: feature-preview
created_by: ci-preview-pipeline
created_at: "2026-11-18T09:00:00Z"
expires_at: "2026-11-19T09:00:00Z"
data_class: synthetic
lifecycle: ephemeral
~~~

This is an illustrative structure; follow your organization/provider tag key conventions. Never place secrets, tokens, or PII in tags. `expires_at` is a lifecycle signal, not a blind delete command if protections or unchecked dependencies exist.

### 3.3. Cost Attribution

Tie costs to services/teams/environments rather than looking only at the total bill. Shared resources such as networking, clusters, observability, or databases can be allocated by usage, reserved capacity, or an agreed rule.

Track costs by service, environment, account, and region; resource family and pricing dimension; active vs. idle hours; successful requests, bookings, or transactions; and idle spend, unattached storage, and orphaned spend. Shared costs need transparent allocation methods to avoid optimizing in the wrong place.

## 4. Workload- and SLO-Driven Rightsizing

### 4.1. Do Not Rely Solely on Average CPU

An instance at 15% average CPU may still need its current size if memory sits near its ceiling or spikes during batch jobs; p99 latency jumps sharply past a CPU threshold; the workload needs rapid burst capacity before the autoscaler reacts; a single thread/core saturates despite low aggregate CPU; disk IOPS, network throughput, or connection pools are the bottleneck; or the instance holds a hot cache or hard-to-move state.

Conversely, months of low CPU do not prove it is safe to downsize without checking peaks, seasonality, failover, and release surges.

### 4.2. Metrics to Inspect

| Resource | Key Metrics | Things to Watch |
|---|---|---|
| VM/container CPU | Average, p95, peak, throttling, run queue | Low average CPU can mask single-core saturation |
| Memory | Working set, RSS, cache, swap, OOM | Needs headroom for spikes and runtime behavior |
| Disk | IOPS, throughput, latency, queue depth, free space | Smaller storage volumes can increase latency |
| Network | Throughput, packet drops, connection count | Instance SKUs carry different network limits |
| Database | CPU, memory, connections, IOPS, locks, replication lag | Instance size is only part of capacity |
| Cache | Memory utilization, evictions, hit rate, hot keys | Shrinking RAM can trigger evictions and origin load |
| Queue/worker | Backlog, oldest message age, processing time, concurrency | Under-scaling builds persistent backlogs |
| Load balancer | Active connections, target health, request rate | Target/connection quotas can become bottlenecks |

### 4.3. Use Percentiles and Sufficiently Long Windows

Collect data spanning daily/weekly cycles and peak hours; batch jobs and periodic reports; campaigns, seasonal peaks, or billing cycles; rolling deployments and autoscaling events; and failover or maintenance windows if data exists.

Examine p50/p95/p99, contextualized maximums, and duration above thresholds. Do not downsize based on a single low-traffic weekend day.

### 4.4. Capacity Headroom

Suppose a service requires 3,000 requests/second at peak. One instance of the current size handles 300 RPS within SLO at a 65% target utilization:

\[
N = \left\lceil \frac{3000}{300 \times 0.65} \right\rceil = 16
\]

This is an initial instance estimate. Add headroom for N+1, zone failure, rolling deployments, traffic skew, startup/warm-up time, and quotas. Rightsizing down to smaller instances may raise the required instance count; total cost does not automatically decrease.

### 4.5. Compute Rightsizing Process

1. Identify the service, owner, SLOs, and resource profile.
2. Measure utilization, saturation, latency, and throughput.
3. Pinpoint the bottleneck: CPU, memory, I/O, network, or dependency.
4. Select a smaller/larger candidate SKU or a different compute family.
5. Benchmark with a production-equivalent workload.
6. Calculate total cost: instance count × price + network/storage/licenses.
7. Deploy a canary or small subset.
8. Monitor latency, errors, throttling, and autoscaling.
9. Expand rollout or roll back.

Do not apply bulk changes across all workloads based on a single generic CPU threshold.

## 5. Container Rightsizing and Autoscaling

### 5.1. CPU/Memory Requests and Limits

In Kubernetes, distinguish requests from limits:

- Requests drive scheduler placement and resource reservation.
- Limits cap runtime consumption; CPU can be throttled when exceeding the limit.
- Exceeding the memory limit typically triggers an OOM kill.

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "1500m"
    memory: "1536Mi"
~~~

These values are examples only. Setting requests too low risks overcommitting nodes and causing contention; setting them too high leaves pods unschedulable and wastes cluster capacity. Limits set too low trigger throttling/OOMs; omitting limits can let one container disrupt neighboring workloads depending on cluster policy.

### 5.2. Using VPA/HPA and Recommendations

- HPA scales replicas based on CPU, memory, or custom/external metrics.
- VPA recommends or adjusts requests/limits depending on mode and workload state.
- Cluster autoscalers/node autoscalers add nodes when pods cannot be scheduled.
- Provider rightsizing recommendations typically rely on historical data; verify peaks and business events.

HPA alone cannot solve node quotas, IP exhaustion, or database bottlenecks. VPA updates to pod resources can trigger restarts/evictions depending on mode; verify impact and `PodDisruptionBudget` settings.

### 5.3. Autoscaling Does Not Replace Baseline Planning

Maintain minimum replicas for baseline traffic and minimum availability; warm caches/JIT and startup latency; one AZ/replica failure per targets; rolling updates; and critical background work.

If scaling from zero takes minutes while users require sub-second responses, scale-to-zero is unsuitable for that path.

## 6. Rightsizing Databases, Storage, and Networking

### 6.1. Databases

Inspect CPU, memory, and buffer/cache hit rates; connection pools and query concurrency; IOPS, throughput, and storage latency; slow queries, lock waits, and vacuum/compaction; replication lag and backup windows; and growth rates, index sizes, and free storage.

Downgrading a database tier can raise latency, lengthen connection queues, and cause backups/replication to fall behind. Test in staging with representative datasets and write mixes, including failover and restore tests.

### 6.2. Storage

Separate storage capacity from performance tier. A disk with plenty of free space can still bottleneck on low IOPS. Conversely, a large volume with no data or owner may represent pure waste.

Opportunities include resizing/retiring unattached volumes after verification; moving cold data to appropriate tiers; applying lifecycles to snapshots and object versions per retention rules; cleaning up multipart uploads and temporary files; and using compression/deduplication where semantics permit.

Never delete snapshots, backups, or objects based solely on last-access timestamps if retention policies or legal holds require keeping them.

### 6.3. Networking and Managed Services

Inspect NAT gateways, load balancers, private endpoints, cross-zone traffic, reserved public IPs, and data transfer. A NAT or load balancer carries both hourly and per-byte costs; remove one only after confirming no dependencies remain.

For managed services, downgrading tiers can affect quotas, features, failover, or SLAs. Compare features and support tiers rather than price alone.

## 7. Scheduling by Environment and Workload

Scheduling fits workloads with predictable active windows. It cuts hourly compute/resource costs when systems do not need to run.

### 7.1. Suitable Environments

| Environment/Workload | Suitable for Scheduling? | Conditions |
|---|---|---|
| Developer sandbox | Very suitable | Assigned owner, advance notice, and state preserved |
| PR preview | Suitable | TTL, synthetic data, cleanup when PR closes |
| Integration test | Suitable | Startup orchestration and defined test windows |
| Staging | Conditional | Must not disrupt releases, demos, or after-hours testing |
| Training/demo | Suitable | Scheduled sessions and fallback owner |
| Production API | Usually not via simple schedules | Must meet SLOs; use autoscaling/scale-to-zero only when architecture supports it |
| Production batch worker | Schedulable | Queue backlog, deadlines, and replay are controlled |
| DR standby | Do not stop arbitrarily | Must satisfy RTO/RPO and quotas/capacity |

### 7.2. Timezone-Aware Schedules

A schedule should specify timezone (e.g., `Asia/Ho_Chi_Minh` or `UTC`); weekdays, weekends, and holidays; start/stop timestamps and warm-up/drain windows; holiday or campaign exceptions; owners authorized to override; and stop blockers such as active deployments or critical tests.

Store absolute timestamps with timezones to avoid ambiguous local-time interpretation across daylight saving shifts or multi-region operators.

### 7.3. Dev Schedule Example

~~~yaml
environment: dev
timezone: Asia/Ho_Chi_Minh
schedule:
  weekdays:
    start: "08:00"
    stop: "20:00"
  weekends:
    mode: stopped
exceptions:
  - date: "2026-11-20"
    mode: running
    reason: "Release rehearsal"
    owner: "booking-team"
resource_policy:
  keep_database_storage: true
  stop_compute: true
  ttl_days: 14
~~~

This is an illustrative policy. A production scheduler must handle holiday calendars, exception expiry, and deployment state; keeping database storage does not mean database instances can be stopped on every engine or tier.

### 7.4. Start Sequence and Stop Sequence

On start:

1. Verify quotas and dependencies.
2. Bring up networks/private endpoints or managed dependencies if they have separate lifecycles.
3. Start required databases/caches.
4. Start compute/workers.
5. Run warm-up, health checks, and synthetic tests.
6. Open ingress or notify that the environment is ready.

On stop:

1. Stop accepting new jobs/requests.
2. Drain connections and process or requeue pending jobs.
3. Wait for active deployments/tests to finish or checkpoint state safely.
4. Flush required data and take backups if policy requires.
5. Stop compute/workers.
6. Stop managed services where supported and safe.
7. Verify ingress, schedules, and final state.

Never stop the database before workers/applications finish draining; wrong ordering can corrupt transactions or build backlogs.

## 8. TTL-Based Auto-Reclamation

### 8.1. TTL and Ownership

Ephemeral resources should carry owner/team; environment/PR/job ID; purpose; created-at and expires-at timestamps; data classification; lifecycle class; protected/shared flags; and cleanup policy.

TTL is a checkpoint to re-verify purpose and ownership, not a blind delete command. Upon expiration, automation checks dependencies, active usage, protections, and policy before deleting.

### 8.2. Auto-Reclamation Lifecycle

~~~mermaid
flowchart TD
    NEW["Resource created with owner + TTL"] --> TRACK["Inventory / lifecycle registry"]
    TRACK --> WARN["Expiry notification"]
    WARN --> CHECK{"Owner extends or resource active?"}
    CHECK -->|"Yes, approved"| EXTEND["Extend TTL with reason"]
    EXTEND --> TRACK
    CHECK -->|"No"| GUARD{"Protected / shared / data-bearing?"}
    GUARD -->|"Yes"| REVIEW["Manual review / backup / approval"]
    REVIEW -->|"Retain"| TRACK
    REVIEW -->|"Approved delete"| CLEAN["Cleanup workflow"]
    GUARD -->|"No"| CLEAN
    CLEAN --> VERIFY["Verify removal and dependencies"]
    VERIFY --> REPORT["Record result / audit"]
~~~

### 8.3. Expiry Notifications

Pre-expiry notifications let owners extend intentionally. For example, notify 24 hours before expiry, and again 1 hour prior for high-cost resources. Extensions require a reason, owner, and maximum extension cap so temporary resources are not extended indefinitely without review.

### 8.4. Orphan Detection

Orphans can include VMs/nodes with no workloads; unattached disks/volumes; expired or unowned snapshots; unassociated public IPs/load balancers; NATs/private endpoints/routes with no consumers; buckets/object prefixes for closed PRs; secrets/certificates/service accounts for deleted workloads; DNS records pointing to nonexistent endpoints; and queues/topics/subscriptions or log groups with no producers/consumers.

An inactive resource is not automatically an orphan; backups, standbys, reserved IPs, or DR resources may need to exist. Combine inventories, tags, dependency graphs, flow logs, IaC state, and owner confirmation.

## 9. Safe Reclamation Workflow

### 9.1. Classify Before Deleting

| Resource Group | Examples | Handling |
|---|---|---|
| Ephemeral compute | Preview VM, test runner | Can be deleted after TTL and drain |
| Temporary storage | Synthetic DB/schema, test objects | Back up/retain per test policy, then delete |
| Persistent data | Production DB, objects, backups | Excluded from generic cleanup |
| Shared foundation | VPC, cluster, KMS, DNS zone | Separate owner and lifecycle |
| Security identity | Roles, keys, certificates | Revoke only after verifying consumers/dependencies |
| Billing/network attachment | IPs, endpoints, NATs, LBs | Check routes/consumers and costs before releasing |

### 9.2. Dry-Run and Approvals

Cleanup workflows should generate a deletion plan first: which resources are proposed for deletion; rationale; affected dependencies; whether data, backups, legal holds, or protections exist; estimated cost savings; and whether rollback/recreation is possible.

For stateful or data-bearing resources, require policy-driven approvals/backups. Low-cost, ephemeral, synthetic resources can use auto-approval once guardrails are thoroughly tested.

### 9.3. Teardown Process

1. Identify resource ID, environment, and owner.
2. Cross-check the lifecycle registry, IaC state, and cloud inventory.
3. Check last activity, active connections, queues/jobs, and deployments.
4. Check data classification, backups, retention, legal holds, and deletion protection.
5. Drain workloads and close ingress.
6. Revoke credentials/permissions in a safe order.
7. Delete resources in dependency order.
8. Check related resources and remaining orphans.
9. Verify that billing/usage charges have stopped.
10. Write an audit report, preserving exempted resources with owner/reason.

### 9.4. Idempotency and Partial Failures

Cleanup may be interrupted partway through. Re-runs must recognize already-deleted resources and resume from current state without recreating resources or deleting unintended dependencies.

Each step should record stable resource IDs; operation status and timestamps; bounded retries for transient errors; error classifications such as not found, permission denied, dependency in use, retention lock, or quota/API throttling; and manual review for ambiguous states.

Do not treat a `destroy` exit code of 0 as sole proof; perform post-cleanup inventory verification.

## 10. Integrating Lifecycles with Infrastructure as Code

### 10.1. IaC Defines Desired State; Inventory Observes Actual State

IaC manages desired state and dependencies. Cloud inventory reflects actual resources; the lifecycle registry tracks owners/expiries; the cost system tracks spend; and telemetry captures activity. Combine all of these sources to identify candidates.

A resource absent from IaC state is not automatically safe to delete; it could be provider-managed or shared. Conversely, a resource present in state is not guaranteed to still be needed; require owner review and a change plan.

### 10.2. Ephemeral Environments

~~~text
PR opened
  -> create isolated stack
  -> attach owner, PR ID, TTL and budget tags
  -> deploy immutable application image
  -> run tests
PR closed or TTL expired
  -> verify PR/environment mapping
  -> generate destroy plan
  -> apply scoped cleanup
  -> verify no orphan
  -> record cleanup result
~~~

### 10.3. Preventing Accidental Production Destruction

- Scope cleanup roles strictly to accounts/projects/environments designated for ephemeral workloads.
- Separate state/backends or workspaces and credentials per environment.
- Reject resources missing an environment tag or carrying invalid tags.
- Block protected/shared resources via policy.
- Verify account ID, region, and resource ARN before destroying.
- Require approvals for data-bearing resources.
- Write negative tests confirming preview cleanup cannot access production.

Never rely solely on resource names containing `dev` or `test`; verify identity/scope and validated metadata.

## 11. Rightsizing and Scheduling for Production

### 11.1. Prefer Scaling Over Stopping

Production APIs generally must meet continuous SLOs. Cut costs by autoscaling replicas/nodes with demand; scaling down idle workers with empty backlogs; scheduling scale-ups ahead of predicted peaks; using scale-to-zero for functions/serverless or workers where startup latency and queue semantics allow; and deferring secondary features or batch jobs during peak hours to prioritize critical traffic.

Do not put an entire production stack on a shutdown schedule without an explicit business downtime window and failover plan.

### 11.2. Scheduled Workers and Queues

A batch worker may run only at night, yet the queue still needs retention, retries, and a DLQ. Before stopping, stop polling/accepting new messages; drain in-flight messages; commit checkpoints/offsets according to semantics; leave unprocessed messages safely in the queue; and ensure visibility timeouts do not expire while workers are still processing.

When restarting, scale based on backlog size and oldest message age rather than a fixed static schedule alone.

### 11.3. Rightsizing and N+1

Do not downsize individual replicas to the point that capacity cannot serve traffic when one instance or zone fails. Post-optimization capacity must still satisfy:

\[
\text{Remaining capacity after failure} \geq
\text{Required critical workload}
\]

If insufficient, add baseline capacity, maintain reserves, or define a business-approved degraded mode.

## 12. Cost Efficiency and Sustainability Impact

### 12.1. Measurable Cost Savings

\[
\text{Gross saving} =
(\text{Old hourly cost} - \text{New hourly cost})
\times \text{Hours}
\]

For scheduling:

\[
\text{Scheduled saving} =
\text{Hourly cost}
\times \text{Hours stopped}
\]

Net savings must subtract secondary costs: extra storage/backups, startup compute, automation overhead, data transfer, unused reserved commitments, and operational support.

### 12.2. Unit Economics

Track cost per successful booking; cost per active tenant; cost per million API requests; cost per GB stored/processed; idle compute spend; unattached storage cost; cleanup coverage; and orphaned spend.

Cost per unit must use stable denominators and genuine business outcomes; never lower unit cost by degrading quality or ignoring failed requests.

### 12.3. Sustainability

Fewer idle resources can reduce power usage and compute/storage/network footprints, though real impact depends on the data center/provider, energy mix, utilization, and allocation methods. Track resource utilization, idle hours, storage retention, data transfer, and compute efficiency instead of quoting unsubstantiated carbon numbers.

Reducing overprovisioning and redundant data typically benefits both cost and sustainability. Still, keeping necessary reliability headroom is part of sound design; never push utilization to 100% solely to optimize one cost metric.

## 13. Permissions, Exceptions, and Guardrails

### 13.1. Protected Resources

Resources that usually require protection include production databases and data-bearing storage; backup vaults, snapshots under retention, and legal holds; KMS keys and certificate authorities; shared VPCs/VNets, transit gateways, and DNS zones; identity providers and logging/audit pipelines; and DR standby resources required to stay warm.

Protections need an owner, rationale, and clear removal process; never use indefinite protection to hide unmanaged resources.

### 13.2. Time-Bounded Exceptions

~~~yaml
resource_id: staging-db-01
exception:
  type: keep-running
  reason: "Performance rehearsal"
  owner: platform-team
  approved_by: release-manager
  starts_at: "2026-11-18T18:00:00+07:00"
  expires_at: "2026-11-19T02:00:00+07:00"
~~~

Exceptions require a specific scope, expiration time, owner, and approval. After expiry, normal policy resumes unless explicitly renewed with justification.

### 13.3. Least Privilege for Automation

Cleanup/scheduler identities should only read inventory, tags, and lifecycle metadata; stop/start or delete permitted resource types and scopes; avoid reading business data when unnecessary; never delete backups, KMS keys, or shared foundations; and record audits and cleanup results.

Separate stop permissions from delete permissions; deleting data-bearing resources should require stronger approval. Never grant shared account administrator credentials to a cron job.

## 14. Dashboards, Alerts, and Runbooks

### 14.1. Dashboards

| Category | Metrics |
|---|---|
| Utilization | CPU/memory/IOPS/network p50/p95/peak |
| SLOs | Latency, error rate, availability after rightsizing |
| Idle | Idle compute hours, zero-traffic instances |
| Orphans | Unattached disks/IPs/LBs/endpoints/unowned resources |
| Lifecycle | Resources by TTL, expired, extensions, and cleanup states |
| Scheduling | Start/stop successes, skips, exceptions, and drift |
| Cost | Cost by service/env/owner, idle spend, net savings |
| Automation | Cleanup errors, retries, blocked deletions, orphan age |

### 14.2. Alerts

- Resource nearing TTL expiry without owner confirmation.
- Cleanup blocked by permission denied or dependency in use.
- Expired resource still running past grace period.
- Production resource accidentally tagged as ephemeral.
- Rightsizing pushing p95/p99 or error rate beyond SLO.
- Autoscaler unable to scale due to quota limits.
- Scheduled stop failed or scheduled start not ready on time.
- Steadily rising orphaned cost.

### 14.3. Runbooks

Runbooks should guide operators to verify account/region/resource ID and owner; identify active workloads/dependencies; check data classification, backups, and retention; inspect lifecycle state, protections, and exceptions; decide whether to stop, resize, detach, snapshot, retain, or delete; verify SLOs after rightsizing/scheduling; and verify resources, endpoints, credentials, and billing after cleanup.

## 15. Practice Exercise: Optimizing the BookingCloud Environment

BookingCloud has:

- 20 dev VMs running 24/7 while the team works weekdays from 08:00 to 20:00.
- A staging database running continuously despite being used only twice a week for release rehearsals.
- Several VMs with p95 CPU under 15%, yet p95 memory around 82%.
- 30 unattached volumes; some are staging snapshots, while others have unknown owners.
- Dozens of preview environments whose PRs are already closed yet remain provisioned.
- A production API with autoscaling that must maintain a 99.9% SLO.

Complete the following tasks:

**Task 1 — Inventory:** classify resources by owner, environment, data class, cost, and dependencies.

**Task 2 — Rightsizing:** analyze CPU/memory/IOPS/latency; determine which VMs can downsize and which must keep or increase memory.

**Task 3 — Schedule:** build a schedule for dev VMs in `Asia/Ho_Chi_Minh`; handle holidays, release rehearsals, active sessions, and warm-up.

**Task 4 — Database:** design staging DB start/stop; verify engine support, backups/restores, connection draining, and startup time.

**Task 5 — Reclamation:** establish TTL/owner/expiry for preview environments; create owner reminders, dry-runs, approvals, and cleanup workflows.

**Task 6 — Orphans:** classify the 30 unattached volumes; reclaim only volumes with verified owner/state and permissible retention.

**Task 7 — Production guardrails:** prove the scheduler cannot shut down production APIs, databases, backups, or DR standbys.

**Task 8 — Cost/sustainability:** compute gross/net savings, before/after utilization, cost per booking, and reduced idle hours.

**Task 9 — Testing:** simulate cleanup partial failures, mistagged resources, expiry extensions, and post-rightsizing SLO degradation.

### Self-Check Results Framework

| Current State | What Must Be Proven |
|---|---|
| Dev VMs running 24/7 | Schedule cuts runtime hours without dropping active sessions/dirty state |
| Underused staging DB | Safe stop/start, restore, and release rehearsals pass requirements |
| Low CPU, high memory | Rightsized to the true bottleneck resource rather than CPU alone |
| Unattached volumes | Owner, snapshot/retention, and restorability verified before deletion |
| Preview for closed PRs | Cleans up the target stack without touching shared foundations |
| Production autoscaling | Preserves min capacity and N+1/SLOs; no arbitrary shutdown schedules |

## 16. Evaluation via Well-Architected

| Lens | Review Question | Required Evidence |
|---|---|---|
| **Operational Excellence** | Who owns lifecycle policies, schedules, and cleanup? Are runbooks/rollbacks ready? | Inventory, owner tags, automation logs, cleanup reports, review cadence |
| **Security** | Does automation follow least privilege? Which resources/data are protected? | Scoped identities, approvals, audits, secret handling, and negative tests |
| **Reliability** | Does rightsizing/scheduling break SLOs, DR, or lose state? | Load tests, N+1 headroom, drain/checkpoints, backup/restore/failover tests |
| **Performance Efficiency** | Do resources match bottlenecks and peak demand? | Utilization percentiles, saturation, p95/p99, and benchmarks |
| **Cost Optimization** | Did idle spend, overprovisioning, and orphan costs truly fall? | Cost attribution, net savings, unit economics, and utilization trends |
| **Sustainability** | Was wasted compute/storage/network reduced while preserving reliability? | Idle hours, resource efficiency, retention, data transfer, and energy metrics where available |

Optimization decisions must be evidence-based and reversible. Good rightsizing lowers cost while proving SLOs hold; a good shutdown schedule proves state drains cleanly and environments come back ready on time; good cleanup proves the right resources were reclaimed while required data stayed intact.

## 17. Pre-Automation Checklist

- [ ] Resource inventory includes owner, service, environment, purpose, and cost attribution.
- [ ] Rightsizing uses utilization/saturation percentiles and workload seasonality.
- [ ] Candidate sizes were benchmarked and SLO-checked before rollout.
- [ ] Headroom covers peaks, rolling deploys, and failure domains.
- [ ] CPU, memory, disk, network, database, and queues were evaluated individually.
- [ ] Schedules declare timezone, weekdays, holidays, warm-up, and owner overrides.
- [ ] Stop sequences drain workloads, handle jobs, and preserve state.
- [ ] Production/DR/shared/data resources are shielded from generic schedulers.
- [ ] Ephemeral resources have TTLs, expiry notifications, and extension policies.
- [ ] Auto-reclamation includes dry-runs, dependency checks, protections, and risk-based approvals.
- [ ] Cleanup identity uses least privilege; account/region/resource scopes are verified.
- [ ] Partial failures, retries, and idempotency are designed in.
- [ ] Orphan detection combines inventory, IaC, dependencies, and owner confirmation.
- [ ] Backups, retention, legal holds, and encryption key lifecycles are respected.
- [ ] Post-cleanup verification confirms resources, endpoints, and charges have stopped.
- [ ] Dashboards/alerts track SLOs, idle spend, orphan age, schedules, and cleanup failures.
- [ ] Rollbacks, runbooks, and time-bounded exception reviews are in place.

Rightsizing adjusts the amount of resources needed while workloads run; scheduling adjusts when they run; auto-reclamation ends the lifecycle of resources that no longer serve a purpose. When all three mechanisms rest on inventories, telemetry, owners, TTLs, and verifiable guardrails, organizations cut waste while preserving SLOs, data, security, and cloud architecture resilience.
