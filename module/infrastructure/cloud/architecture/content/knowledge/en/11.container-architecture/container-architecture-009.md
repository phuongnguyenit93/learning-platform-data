# Platform Upgrades, Node Replacement, and Workload Portability

## 1. Why Design for Upgrades and Portability?

A container platform does not stand still after initial deployment. Kubernetes or the underlying container platform must be updated; worker nodes must be replaced when OS images reach end-of-life, patches are released, machine types change, or hardware fails; and workloads may need to migrate to another node pool, Availability Zone (AZ), region, or cluster. These operations impact **availability, data integrity, security, performance, cost, and operations**.

In the **CLOUD_ARCHITECTURE** module, architectures are designed from business requirements down to networking, compute, data, and deployment models, then evaluated through a **Well-Architected** lens. A strong container platform must explain both how to run applications and how to update infrastructure without losing data or breaking services.

After this lesson, you will be able to distinguish control plane upgrades, node replacement, and workload migration; build a compatibility matrix; understand `cordon`, `drain`, eviction, and PodDisruptionBudgets (PDBs); handle stateful workloads; choose rolling, surge, blue-green, or canary strategies; and create evidence-backed rollback plans.

## 2. Distinguishing Three Types of Changes

| Change | Primary Components | Goal | Typical Risks |
|---|---|---|---|
| **Platform upgrade** | API server, scheduler, controllers, etcd, or managed control plane | Patches, features, staying on supported versions | Removed APIs, version skew, incompatible CRDs/controllers |
| **Node replacement** | Worker VMs, node pools, OS images, kubelet, runtime, kernel | Replace aging nodes, update images or compute shapes | Capacity shortages, Pods unable to drain/schedule, lost local state |
| **Workload migration** | Deployments, StatefulSets, Jobs, services, volumes, secrets, networking, traffic | Move applications to another pool/cluster/zone/region | Data loss, split-brain, misrouted DNS/traffic, missing dependencies or permissions |

These three activities are related, not synonymous. Upgrading the control plane does not automatically replace all nodes; replacing nodes does not guarantee workloads are compatible with new versions; creating a new cluster does not automatically migrate PVCs, secrets, certificates, DNS, or data.

### 2.1. Illustrative Context

BookingCloud runs on Kubernetes with multi-replica stateless APIs, asynchronous workers, managed PostgreSQL outside the cluster, HTTPS ingress/load balancers, and several PVCs for stateful workloads. Business databases are not stored on worker nodes.

| Hypothetical Requirement | Design Implication |
|---|---|
| Core API targets 99.9%/month availability | Drains and rollouts must not take down all replicas simultaneously |
| Losing one node must not lose committed bookings | Business data must live in durable storage |
| Workers can migrate to new node pools | Images, configs, identities, queues, and checkpoints do not depend on old nodes |
| Ability to recover if an upgrade fails | Backups, runbooks, and recovery paths are tested beforehand |
| Small operations team | Automation, incremental changes, monitoring, and clear ownership |

These targets are hypothetical for this lesson, not actual SLAs. RTO/RPO must be defined by incident scope and measured through drills.

## 3. Checking Compatibility Before Upgrading

A cluster is a collection of components with strict compatibility relationships. Check **current versions, target versions, upgrade paths, and version skew** in your provider or platform documentation.

| Component | Verification Questions |
|---|---|
| Control plane | Are the target version and upgrade path supported? |
| Worker/kubelet | Is the kubelet version within supported version skew relative to the API server? |
| Runtime | Is the container runtime/CRI compatible with the new OS, kernel, and kubelet? |
| CNI | Are network plugins, IPAM, NetworkPolicy, eBPF, and the dataplane compatible? |
| CSI | Does the storage driver support attach/mount, snapshots, expansion, and new topology? |
| Ingress/controller | Do manifests use deprecated or removed APIs? |
| CRD/operator | Are schemas, served/storage versions, conversion webhooks, and controller versions compatible? |
| Service mesh | Do sidecars, proxies, certificate rotation, and policies still function? |
| Security/observability agents | Do DaemonSets, kernel/eBPF probes, runtime security, and log pipelines support the new OS? |
| Helm/IaC | Have charts, provider plugins, schemas, or automation changed? |

### 3.1. API Deprecations and CRDs

Before upgrading a Kubernetes minor version:

1. Inventory all API versions currently used by workloads, Helm charts, operators, and automation.
2. Check which APIs are deprecated or removed in the target version.
3. Update manifests to supported APIs and validate schemas via server-side dry-runs or equivalent tools.
4. Inspect CRDs: served versions, storage versions, conversion webhooks, and stored custom resource objects.
5. Upgrade controllers/operators in the compatibility order supported by the project/provider.
6. Monitor deprecation warnings well before the maintenance window.

Updating manifest files does not automatically migrate already-stored custom resources in etcd. If a CRD relies on conversion webhooks, verify that both webhooks and stored objects read and write cleanly across versions.

### 3.2. OS, Architecture, and Node Agents

Check OS images, kernels, CPU architectures (x86_64/ARM), runtimes, instance types, disks/networks, accelerators, labels, taints, zones, and security profiles. Application images must support the new pool's CPU architecture. GPU workloads require matching drivers/device plugins; if missing, Pods can stay Pending even when CPU and RAM are plentiful.

## 4. Upgrading the Platform Layer by Layer

The exact sequence depends on whether Kubernetes is managed or self-managed. Managed control planes are typically orchestrated by the provider with specific version-skew rules. Self-managed clusters require administering the API server, etcd, quorum, backups, and individual control-plane components. Never follow a generic sequence without verifying platform documentation.

~~~mermaid
flowchart TD
    A["Inventory versions and dependencies"] --> B["Check deprecations / compatibility"]
    B --> C["Backup and rehearse restore"]
    C --> D["Upgrade control plane along supported path"]
    D --> E["Verify APIs, CRDs, webhooks, CNI/CSI"]
    E --> F["Provision new-version node pool"]
    F --> G["Migrate workloads in batches"]
    G --> H["Soak test and monitor SLOs"]
    H --> I{"Criteria met?"}
    I -->|"No"| R["Halt rollout / recover per runbook"]
    I -->|"Yes"| J["Decommission old pool safely"]
~~~

Before starting, document pre/post control plane and node versions; permitted version skew; whether old node pools can run temporarily after the control plane changes; whether the provider supports surge upgrades or blue-green node pools; when CNI/CSI/ingress/operators/service mesh are upgraded; and recovery steps if downgrades are unsupported.

After every step, verify API discovery, node readiness, controller reconciliation, webhooks, CRDs, networking/DNS, ingress, PVC mounts, IAM/workload identity, and observability. Never wait until the very end to run smoke tests.

## 5. Replacing Nodes with a New Node Pool

Replacing nodes via **create new pool → validate → shift workloads → drain old pool → delete old pool** isolates OS/runtime risks away from nodes actively running production traffic.

~~~mermaid
flowchart TB
    subgraph OLD["Blue: old pool"]
      O1["Node old-1"]
      O2["Node old-2"]
    end
    subgraph NEW["Green: new pool"]
      N1["Node new-1"]
      N2["Node new-2"]
    end
    S["Scheduler"] --> N1
    S --> N2
    N1 --> W["Workloads"]
    N2 --> W
    N1 --> CHECK["Health / metrics / soak test"]
    N2 --> CHECK
    CHECK -->|"Criteria met"| DRAIN["Cordon + drain old pool"]
    DRAIN --> O1
    DRAIN --> O2
~~~

Steps:

1. Create the new pool via IaC/managed node groups with verified OS images, kubelet, runtime, labels, taints, security groups, and IAM.
2. Verify nodes are Ready, CNI/CSI/daemon agents are healthy, images pull cleanly, and required volumes mount.
3. Verify VM quotas, subnet IPs, Pod IPs, CPU/RAM, ephemeral storage, and surge headroom.
4. Ensure affinity rules, taints, topology spread, and node selectors allow workloads onto the new pool.
5. Shift a low-risk workload batch; monitor readiness, errors, latency, restarts, and resource pressure.
6. Cordon old nodes so the scheduler stops placing new Pods on them.
7. Drain nodes one by one in small batches respecting PDBs; verify replacement Pods become healthy.
8. Keep the new pool running through a soak period representative of production load.
9. Delete the old pool after confirming zero remaining Pods, volume attachments, or dependencies.

### 5.1. Rolling, Surge, and Autoscaling

Rolling updates replace nodes one by one or in a small percentage. Surge upgrades provision new nodes before removing old ones. Both require planning surge capacity, `maxUnavailable`, interaction with the cluster autoscaler, quotas and subnet IPs, Pod/volume topology, and temporary costs while two pools run in parallel.

### 5.2. Cordon, Drain, Eviction, and PDB

- **Cordon** marks a node unschedulable so the scheduler avoids placing new Pods there.
- **Drain** requests Pod relocation via the eviction API; certain Pods or resource types follow special handling rules.
- **Graceful termination** gives processes time to stop: handling `SIGTERM`, `preStop` hooks, stopping new traffic/tasks, and closing connections cleanly.
- **PodDisruptionBudget (PDB)** caps voluntary disruptions triggered through the eviction API according to configured budgets.

PDBs do not protect against sudden node deaths, kernel panics, zone outages, or all forced deletions. PDBs do not create replicas on their own and cannot prove an application is healthy if its readiness probe is flawed.

For example, a PDB with `minAvailable: 2` only permits eviction when enough healthy Pods remain under Kubernetes calculations. If a Deployment has two replicas and one is already `NotReady`, `drain` can block. Check replicas, readiness, topology, and PDBs before maintenance; never edit a PDB just to force a drain through without explicitly accepting the availability risk.

Illustrative commands (replace node and namespace names for your cluster):

~~~bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get pdb -A
kubectl describe pdb -n booking booking-api

# Prevent the scheduler from placing new Pods on this node
kubectl cordon worker-old-01

# Evict Pods per policy; check PDBs and DaemonSets first
kubectl drain worker-old-01 --ignore-daemonsets --delete-emptydir-data

# Verify Pods have moved and the node holds no workloads that must stay
kubectl get pods -A -o wide
~~~

The `--delete-emptydir-data` flag deletes `emptyDir` data when Pods leave the node. Use it only when that data is genuinely temporary or safely persisted elsewhere. `drain` can be rejected by a PDB; never tack on force/disable-eviction flags blindly without understanding the consequences.

## 6. Stateful Workloads: Storage, Identity, and Quorum

Migrating stateless Deployments is generally easier than migrating StatefulSets or databases because stateless Pods can be recreated from images, configs, and external data stores. Stateful workloads carry persistent identity, volumes, and consistency constraints.

### 6.1. Persistent Volumes and Topology

PVs/PVCs may be bound to a specific Availability Zone. A disk in zone A cannot be attached by default to a node in zone B unless the storage driver supports it. Verify StorageClass, CSI drivers, volume topology, access modes, attach limits, snapshot/resize support, detach/re-attach behavior after node crashes, encryption key permissions, and snapshot restoration across zones/regions.

Never delete old nodes or clusters while volumes still hold active attachments, pending snapshots, or finalizers.

### 6.2. StatefulSets, Leaders, and Quorum

StatefulSets maintain ordinals, network identities, and PVCs under strict ordering rules. When migrating, preserve bootstrap/join order; prevent two instances from holding the same identity; track quorum/leaders; check replication lag and consistency; and remove old members only after new members have joined and the cluster is healthy.

For etcd, Kafka, self-managed databases, or distributed caches, spawning new Pods outside membership protocols can trigger split-brain or loss of quorum. Consider managed services or separating state outside the cluster when appropriate.

### 6.3. Classifying Local State

| Data Type | Handling Before Drain |
|---|---|
| Regenerable cache | Acceptable to discard; plan warm-up and rate limiting |
| Per-request temporary files | Wait for completion or safely retry |
| Checkpoints/batch progress | Sync to durable storage and verify checksums/state |
| User sessions | Externalize to a session store or use appropriate stateless sessions |
| Unique business data | Never store locally; write to durable DB/object storage |

`emptyDir`, container writable layers, and local ephemeral disks can be wiped when Pods or nodes are replaced. Never leave unique data or irreplaceable checkpoints there.

## 7. Migrating Workloads Between Node Pools or Clusters

### 7.1. Prerequisites for Workload Portability

Images reside in a registry reachable by the target cluster and support its CPU architecture; config/secrets are managed outside nodes; IAM/workload identity is configured for the target environment; network policies/DNS/egress are provisioned via IaC; data sits in reachable DBs/object storage; PVCs have snapshot/replication strategies; admission policies, CRDs, ingress, service mesh, security agents, and observability are compatible; and autoscaling/affinity/topology rules do not pin workloads to the old pool.

### 7.2. Changing Node Pools vs. Changing Clusters

| Aspect | Changing Node Pool Within Cluster | Migrating to Another Cluster |
|---|---|---|
| Control plane/API | Unchanged | May differ in version and CRDs |
| Network/service discovery | Service DNS usually stays intact | CIDRs, DNS, peering, ingress, and endpoints may change |
| Identity | Can keep in-cluster configs | Must establish trust/roles for target cluster |
| Config/secrets | Existing objects can remain | Must sync from source of truth |
| Storage | PVCs can remain if topology/driver allow | May require snapshots/replication/restores |
| Traffic | Service endpoints update as Pods become Ready | Requires traffic routing/cutover, DNS, or gateway shifts |
| Rollback | Can reschedule back to the old pool | May require shifting traffic and data back |

A new cluster does not automatically inherit RBAC, network policies, CRDs, admission controllers, secrets, certificates, storage classes, ingress, and observability. Provision and validate those dependencies before moving workloads.

### 7.3. Migration Workflow to a New Cluster

~~~mermaid
flowchart TD
    S["Inventory workloads + dependencies"] --> T["Provision target cluster via IaC"]
    T --> V["Install CNI/CSI/ingress/CRDs/observability/security"]
    V --> D["Verify DNS, IAM, secrets, storage, and connectivity"]
    D --> P["Deploy target workloads without primary traffic"]
    P --> H["Smoke tests / synthetic tests / data validation"]
    H --> C{"Ready for cutover?"}
    C -->|"No"| F["Fix configuration or abort migration wave"]
    F --> P
    C -->|"Yes"| M["Shift traffic in waves"]
    M --> O["Monitor SLOs, errors, data, and backlog"]
    O --> R{"Thresholds met?"}
    R -->|"No"| RB["Roll back traffic per runbook"]
    R -->|"Yes"| X["Soak period, decommission old cluster safely"]
~~~

Cutover strategies:

- **Recreate:** deploy at target, stop source, then switch traffic; simple, but incurs downtime.
- **Rolling:** shift replicas/nodes incrementally; requires mutual compatibility and shared data sources.
- **Blue-green:** build the full target environment then switch traffic; requires parallel capacity and a data plan.
- **Canary/weighted routing:** shift a fraction of traffic first and ramp up based on metrics; must address sessions and write consistency.
- **Active-active:** both sides serve requests concurrently; requires explicit write authority, data sync, deduplication, and conflict resolution. Never assume this is safe by default for transactional databases.

### 7.4. Databases and Data Cutover

If old and new clusters share a managed database, verify schemas are compatible with both application versions; network paths, IAM, DNS, TLS, and connection pools work from the new cluster; CronJobs/consumers do not double-run; and schema migrations do not break rollbacks.

If the database itself moves, the process may involve snapshot/restore, logical replication, initial copy + incremental sync, write freeze, row count/checksum validation, and writer promotion. Define the exact moment the **authoritative source of truth** switches from old to new. Avoid letting both clusters accept independent writes unless engineered for multi-writer conflict resolution.

## 8. Rollback and Recovery

Not every platform upgrade supports downgrades. Once stored API objects, etcd schemas, or CRD objects have been updated, rolling the control plane back to an older version may be unsupported. Recovery options include halting the rollout; keeping the old pool if still compatible; shifting traffic/workloads back to the source; restoring data if migrations altered state; spinning up a new cluster on a known-good version and restoring/migrating; or rolling forward with a fix when a one-way schema/data migration has already occurred.

### 8.1. Assets to Back Up

| Asset | Protection Measures |
|---|---|
| Manifests/IaC/Helm | Version control, code review, pinned artifact versions |
| Cluster objects and CRDs | Supported backup tooling; raw YAML dumps do not replace etcd backups |
| Self-managed etcd | Snapshots per official docs, encrypted, stored outside the failure domain, and restore-tested |
| Business databases | Backups/PITR, restore tests, key access checks |
| Persistent volumes | Snapshots/replication via CSI/storage provider with consistency checks |
| Secrets/keys | Secret manager/KMS/HSM and recovery procedures; never dump into repositories |
| DNS/Ingress/Certificates | IaC/inventories, certificate automation, owners, and rollback records |

A backup that has never been restore-tested is not recovery evidence. Rehearse restores in an isolated environment and verify both data integrity and live application functionality.

### 8.2. Go / No-Go Criteria

| Criterion | Go | No-Go |
|---|---|---|
| Node readiness | Target pool Ready, agents healthy | Nodes NotReady, CNI/CSI errors |
| API health | Error rate/p95 within thresholds | Regressions exceeding thresholds or sustained degradation |
| Disruption | Within budget, PDB/quorum preserved | Missing replicas or lost quorum |
| Data | Booking consistency, volumes, and queue states valid | Duplicate/lost data or excessive replication lag |
| Security | RBAC, IAM, network policies, secret access verified | Missing permissions or unprotected exposure paths |
| Operations | Dashboards, alerts, runbooks, on-call ready | Blind spots in observability or missing owners |

When any no-go condition appears, halt the rollout per runbook; never press forward simply because most of the work is already done.

## 9. Operating Within a Change Window

**Before the change:** confirm owners/approvers/on-call; pin images/charts/plugins/versions; run compatibility scans and IaC plans; review resource replacements/destructions; verify backups, restores, quotas, and surge capacity; audit replicas, PDBs, readiness/liveness, termination grace periods, `preStop` hooks, topology spread, and stateful dependencies; coordinate CronJobs/consumers to prevent duplicate execution.

**During execution:** proceed in small batches; watch scheduler events, Pending Pods, eviction failures, volume attachments, CNI errors, and node pressure; monitor end-to-end SLIs rather than node CPU alone; ensure IaC desired state does not recreate old pools; log every transition step.

**After execution:** run soak tests covering peak/steady load; execute synthetic business transactions; verify error rates, latency, restarts, saturation, cost, and event backlogs; confirm backup/restore jobs; delete old pools/clusters only after zero remaining dependencies and after safe retention windows expire; update diagrams, inventories, ADRs, and runbooks.

## 10. Node Rotation Example for BookingCloud

Suppose the API runs 6 replicas across 3 AZs with a PDB requiring at least 4 available Pods; workers run 4 retryable replicas; the DB is a managed service outside the cluster. The current pool uses an aging OS image that must be replaced.

| Phase | Actions | Gate to Proceed |
|---|---|---|
| Prepare | Verify versions, images, plugins, quotas, IPs, and PDBs | Capacity available in target pool/zones |
| Create | Provision new pool, apply labels/taints/roles | Nodes Ready; network/storage/security agents healthy |
| Canary | Shift one API replica and one worker | Readiness, p95, errors, DB connectivity, queue processing pass |
| Expand | Gradually shift workloads to new pool | Zero regressions in topology/PDB/capacity |
| Cordon | Cordon old nodes in batches | Scheduler stops placing new Pods in old pool |
| Drain | Drain nodes one by one | Replacement Pods healthy; volumes/quorum safe |
| Soak | Run new pool under representative load | SLIs/SLOs, costs, and alerts remain stable |
| Retire | Delete old pool, update IaC/catalog | Zero remaining workloads, volumes, or dependencies |

The numbers 6 replicas, PDB 4, and 3 AZs are illustrative. A PDB does not guarantee each AZ retains a Pod unless topology rules are configured; true spreading requires topology spread/anti-affinity. If an AZ is already down before a drain, healthy Pods may fall short and the plan must adapt.

Workers can drain faster when queue leases, checkpoints, and idempotency are verified. APIs require accurate readiness, connection draining, and finishing in-flight requests before Pods terminate.

## 11. Common Design Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Upgrading the control plane before checking removed APIs | Controllers/manifests fail to create or read resources | Scan deprecations and fix beforehand |
| Assuming node replacement is harmless | Pods fail to schedule due to missing quotas/taints/IPs/storage | Provision new pool and verify capacity first |
| Draining the entire pool at once | Loses replicas or breaches disruption budgets | Drain in small batches; check PDBs/topology/SLOs |
| Thinking PDBs stop node crashes | Pods are still lost during instance/AZ outages | Separate replicas, topology, readiness, and HA design |
| Deleting nodes without checking PVs | Volumes remain attached or fail to mount | Verify PVC/PV/CSI topology and restores |
| Using local disks as the sole checkpoint | Lost progress | Use durable storage |
| Running CronJobs/consumers in both clusters | Duplicate side effects | Enforce ownership/leases/idempotency |
| Letting two clusters write to the same DB | Conflicts or split-brain | Single authoritative writer or true multi-writer design |
| Assuming downgrades always work | Control plane or stored data incompatibilities | Recover via restores or fresh clusters |
| Deleting the old cluster immediately after cutover | Loses rollback path | Enforce a soak period and retirement criteria |
| Checking only Pod Ready status | Business workflows may still be broken | Run synthetic business tests and end-to-end SLIs |

## 12. Well-Architected Evaluation

| Perspective | Review Questions | Evidence |
|---|---|---|
| **Operational Excellence** | Who coordinates upgrades, drains, and rollbacks? | Change plan, owners, runbooks, audits, drills |
| **Security** | Do new images/runtimes have patches and least privilege? | Image scans, IAM/RBAC, network policies, patch status |
| **Reliability** | Does a node/zone loss or failed upgrade preserve data and SLOs? | PDBs, topology, HA tests, backup/restore, RTO/RPO |
| **Performance Efficiency** | Do new nodes have enough CPU/memory/network/storage for peak load? | Load tests, saturation, p95/p99, backlogs |
| **Cost Optimization** | How much do surge capacity and parallel pools/clusters cost? | Cost forecasts, utilization, retirement timing |
| **Sustainability** | Are idle compute and repeated migrations avoided? | Lifecycle policies, capacity metrics, node utilization |

Managed Kubernetes reduces part of the control plane burden, yet never assumes responsibility for workload compatibility, data backups, PDBs, policies, or cutover decisions.

## 13. Practice Exercise: Cluster Upgrade and Node Pool Replacement

A system has three pools: `system-pool` running CoreDNS/CNI/CSI/ingress/observability; `api-pool` running an 8-replica stateless API; and `worker-pool` running queue workers with tasks lasting up to 20 minutes. The cluster must upgrade its Kubernetes minor version and swap its OS image. Several StatefulSet PVCs reside in zone A. The team aims to complete this within one maintenance window.

**Task 1 — Compatibility:** build a version matrix for the control plane, kubelet, runtime, CNI, CSI, ingress, CRDs, and charts. Specify the upgrade order per a provider support matrix.

**Task 2 — Node replacement:** design blue-green/rolling transitions for each pool. How do you keep DNS, networking, storage, and observability alive while rotating `system-pool`?

**Task 3 — Disruption:** propose PDBs, replicas, topology spread, and drain batches. Analyze what happens if one API replica is already `NotReady` before draining begins.

**Task 4 — Worker state:** explain how to stop polling, checkpoint long-running tasks, ack/release leases, and prevent duplicate processing when a Pod is evicted.

**Task 5 — PVCs:** why don't PVCs in zone A mount in zone B by default? Propose snapshot/restore or storage migration and consistency validation.

**Task 6 — Rollback:** define go/no-go criteria, soak duration, abort thresholds, required backups, and recovery if the control plane cannot downgrade.

**Task 7 — Well-Architected:** build an impact table across availability, security, p95 latency, surge cost, and operational capacity; propose pre-production validation tests.

### Condensed Runbook Template

~~~text
Change: Rotate api-pool from old-image to new-image
Owner: team-booking
Approver: platform-on-call

Pre-check:
  - compatibility matrix reviewed
  - quota/IP/capacity available in target zones
  - PDB/readiness/replicas healthy
  - database and persistent data backup verified
  - dashboards, alerts, rollback path ready

Execution:
  1. create new node pool
  2. validate node agents and network/storage
  3. move one canary replica
  4. verify business synthetic test and SLI
  5. cordon/drain old nodes in small batches
  6. repeat until target pool serves all workload

Abort when:
  - business error rate or latency exceeds agreed threshold
  - PDB blocks expected safe drain
  - volume/network/security agent fails
  - data inconsistency or duplicate side effect occurs

Close:
  - soak test passed
  - old pool has no dependency
  - inventory/IaC/ADR/runbook updated
~~~

Real runbooks must replace thresholds, commands, resource names, and on-call contacts to match the actual provider/cluster. A generic checklist never replaces a concrete maintenance procedure.

## 14. Pre-Approval Checklist for Upgrades or Migrations

- [ ] Control plane upgrades, node replacement, and workload migration are clearly distinguished.
- [ ] A compatibility matrix exists for Kubernetes, kubelet, runtime, OS, CNI, CSI, CRDs, and controllers.
- [ ] API deprecations, webhooks, charts/IaC, and stored resource conversions are audited.
- [ ] Backups/restores are tested; whether downgrades are supported or recovery requires a fresh cluster is confirmed.
- [ ] The new pool has quotas, IPs, capacity, zones, storage, and IAM verified.
- [ ] Pods have proper readiness/liveness probes, graceful shutdown, termination budgets, and retries.
- [ ] PDBs/topology/replicas align, with clear awareness that PDBs do not protect against involuntary disruptions.
- [ ] PVCs/PVs, volume attachments, local state, StatefulSet identities, and quorum are inventoried.
- [ ] CronJobs, consumers, and side effects enforce ownership/idempotency while two environments coexist.
- [ ] Target cluster has DNS, ingress, certificates, secrets, network policies, observability, and security agents ready.
- [ ] Canary/soak plans, SLOs, go/no-go gates, abort conditions, and rollback owners are assigned.
- [ ] Old nodes/pools/clusters are never deleted until zero dependencies remain and recovery paths are approved.
- [ ] IaC, inventories, ADRs, diagrams, and runbooks are updated.

Platform upgrades, node replacements, and workload migrations are far safer when treated as **verifiable change procedures**: understand compatibility, provision replacement capacity first, shift load under control, protect data, measure SLOs, and preserve recovery paths. That way, organizations can update their container platforms regularly without letting node lifecycles dictate data lifecycles or service continuity.
