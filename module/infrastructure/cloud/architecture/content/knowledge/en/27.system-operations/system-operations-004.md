# Platform Maintenance, Patching, and Resource Lifecycle Management

A cloud platform does not remain static after deployment. Operating systems, container base images, runtimes, database engines, network appliances, certificates, firmware, and managed services each have their own lifecycle. Providers release patches, older versions reach end of support, new vulnerabilities are disclosed, workloads grow, and resources become unsuitable. Focusing only on initial build without managing changes across the lifecycle causes systems to accumulate security risks, technical debt, excess cost, and fragile failure points.

**Platform maintenance** is the practice of keeping infrastructure and platform software in a secure, supported state that meets operational objectives. **Patching** is a subset of maintenance focused on fixing bugs or vulnerabilities in software/firmware. **Resource lifecycle management** spans planning, provisioning, configuring, operating, upgrading, scaling, shrinking, and retiring cloud resources.

This lesson belongs to the **System Operations** chapter of the **Cloud Architecture** track. The curriculum teaches how to design cloud architectures from business requirements through networking, compute, data, and deployment models, balancing reliability, security, scalability, cost, and operations. This lesson focuses on turning maintenance into a structured process with inventory, ownership, change windows, verification, rollback, and compliance evidence.

After this lesson, you will be able to:

- Design maintenance and patch management workflows aligned with risk levels.
- Build an inventory of resources, versions, owners, dependencies, and support end dates.
- Triage vulnerabilities and prioritize patches by exploitability, exposure, and business impact.
- Choose among rolling, canary, blue-green, or in-place maintenance strategies.
- Plan backups, compatibility checks, rollbacks, and recovery before making changes.
- Manage the lifecycle of compute, containers, databases, storage, networking, and managed services.
- Track capacity, cost, drift, and expired or unused resources.
- Decommission resources safely, protect data, and revoke identities/credentials.
- Measure effectiveness using coverage, patch latency, change failure rate, and lifecycle compliance.

## 1. Maintenance Is an Ongoing Activity

Maintenance does not happen only when systems break. It includes proactive activities to reduce failure probability and reactive activities when bugs or vulnerabilities emerge.

| Activity Group | Examples | Objective |
| --- | --- | --- |
| Preventive maintenance | Scheduled patching, certificate renewal, disk health checks | Prevent failures before they occur |
| Corrective maintenance | Fixing misconfigurations, replacing failed instances, patching bugs | Restore proper state |
| Adaptive maintenance | Upgrading runtimes, migrating cloud APIs, changing storage tiers | Adapt to changing environments |
| Predictive maintenance | Monitoring disk wear, capacity trends, expirations | Detect risks before thresholds breach |
| Security maintenance | Patching CVEs, rotating credentials, updating policies | Reduce attack surface |
| Lifecycle maintenance | Upgrading, resizing, retiring resources | Keep resources supported and efficient |

A strong maintenance program separates routine work from emergencies. Not every change needs the same change window or approval; however, every change requires an owner, impact assessment, evidence, and outcome verification.

## 2. Resource Inventory and Ownership

You cannot maintain what the organization does not know exists. Inventory must cover both cloud resources and the software components running on them.

Minimum information:

- Resource ID, resource type, account/project/subscription, and region.
- Environment, application/service, tenant, or associated data classification.
- Technical owner, business owner, and on-call team.
- Runtime/OS/image/firmware/engine version.
- Creation date, support end date, expiration, and lifecycle state.
- Network exposure, identities/roles, and dependencies.
- Backup/restore classification, RPO/RTO, and retention.
- Cost center, tags, and utilization.
- Maintenance policy, patch group, and change window.

### 2.1. Inventory Cannot Rely Only on Manual Tags

Combine cloud asset inventory, API discovery, configuration management databases (CMDB), Kubernetes inventory, software bills of materials (SBOM), package scanners, and IaC state. Reconciling across sources uncovers unmanaged resources or actual configurations that have drifted from declarations.

A resource lacking an explicit owner or environment should enter a triage queue—never assume it is an experimental resource safe to delete.

### 2.2. Owners and the Responsibility Model

For managed services, the provider may own hardware and part of the underlying patching, while the customer owns configuration, version options, access policies, and maintenance windows. Build a shared responsibility matrix per service; “managed” does not mean the provider manages the entire application lifecycle.

## 3. Resource Lifecycle

A cloud resource typically transitions through these states:

~~~mermaid
stateDiagram-v2
    [*] --> Planned
    Planned --> Provisioned
    Provisioned --> Active
    Active --> Maintenance
    Maintenance --> Active
    Active --> Upgrade
    Upgrade --> Active
    Active --> Deprecated
    Deprecated --> Decommissioning
    Decommissioning --> Retired
    Retired --> [*]
~~~

States require entry and exit criteria. For instance, a resource moves to Deprecated once a replacement path and end-of-support date exist; Decommissioning starts only after verifying workloads migrated and data has proper retention/exports.

Never leave resources in an indefinite “temporary” state. Inventory should surface half-provisioned, failed, orphaned, idle, and pending-retirement resources.

## 4. Lifecycle Policies by Resource Type

Each resource type requires its own cadence and criteria.

| Type | Typical Maintenance | Lifecycle Milestones |
| --- | --- | --- |
| VM/OS | Security patches, kernel updates, image refreshes | OS end-of-support, aging instance families |
| Container image | Rebuild base image, scan dependencies | Image digest, base image EOL |
| Kubernetes/node pool | Control plane/node upgrades, API deprecations | Cluster version support window |
| Database | Engine patches, minor/major upgrades, parameter reviews | Engine support end, storage growth |
| Storage | Capacity/IOPS reviews, integrity/replication checks | Volume age, tier, retention |
| Network | Firmware/config patches, route/firewall reviews | Appliance EOL, certificate expiry |
| Certificate | Renewal, chain migration, revocation | Not-after date, CA transitions |
| IAM/secret | Credential rotation, role reviews | Secret age, access owner changes |
| Managed service | Review release channels and provider notices | Mandatory upgrades/deprecations |
| Backup system | Restore drills, retention and key validation | Backup age, restore test age |

Maintenance schedules should reflect vendor support lifecycles, security advisories, workload compatibility, and business requirements. Do not force one rigid schedule across every resource type.

## 5. Patch Management Lifecycle

A patch management workflow typically includes:

1. **Discover:** locate affected assets and packages/versions.
2. **Assess:** evaluate severity, exploitability, exposure, and impact.
3. **Prioritize:** rank order based on risk and deadlines.
4. **Acquire:** obtain official patches/images/releases and verify signatures/provenance.
5. **Test:** validate in a production-equivalent environment.
6. **Plan:** define cohorts, change windows, dependencies, and rollback/recovery.
7. **Deploy:** roll out via canary/rolling/waves.
8. **Verify:** confirm running versions, service health, and business behavior.
9. **Record:** store evidence, exceptions, and completion status.
10. **Remediate gaps:** handle offline hosts, failed deployments, or off-inventory assets.

A patch is only complete when assets are genuinely running the target version, or an approved exception with a remediation date is documented. A successful deploy command is not enough if a node failed to update or workloads still run an older image.

## 6. Vulnerability Triage and Patch Prioritization

Do not prioritize solely by a single severity score. Real-world risk also depends on exploitability, exposure, required privileges, affected data, and existing mitigations.

Signals to consider:

- CVSS/severity from assessment sources.
- Known active exploitation or public exploit code.
- Whether the component is Internet-facing or internal-network only.
- Whether it is actively exploited in the real environment.
- Whether the service processes sensitive data or critical workloads.
- Presence of compensating controls such as WAF, network isolation, or disabled features.
- Whether the patch introduces breaking changes or requires a reboot.
- Blast radius if exploitation succeeds.

### 6.1. Risk-Based Prioritization

| Priority | Illustrative Signals | Response |
| --- | --- | --- |
| Emergency | Actively exploited vulnerability, exposed asset, critical impact | Trigger emergency change, isolate/mitigate, and patch on a very tight deadline |
| High | Feasible remote exploit or high privilege on critical systems | Prioritize in the nearest cycle, track coverage daily |
| Medium | Limited exploitation conditions, lower exposure | Schedule maintenance by risk and support window |
| Low | Low impact or strong controls already in place | Bundle into regular maintenance cycle, monitor advisories |

Levels and SLAs must be defined by organizational policy; these examples do not replace applicable security standards or regulatory mandates.

### 6.2. Zero-Day and Emergency Patches

When no patch is available yet, apply temporary mitigations such as disabling vulnerable features, blocking network paths, adding WAF rules, rotating credentials, or isolating workloads. Mitigations must have an owner, expiration, and plan to return to standard configuration.

When an emergency patch carries breaking-change risks, run minimum checks on critical journeys and deploy to a small cohort if time permits. If full testing cannot wait, the decision record must explicitly document accepted risks, minimum validation performed, and rollback/restore options.

## 7. Patch Policies and Exception Management

A patch policy should define:

- Scope of assets and packages to scan.
- Scan frequency and advisory feeds.
- SLAs by risk level.
- Change windows and approval paths.
- Workload groups with dedicated maintenance rules.
- Handling for offline or unpatchable hosts.
- Required evidence and retention.
- Exception/waiver workflow.
- Criteria to close exceptions.
- Escalation when overdue.

An exception should never be just a note saying “cannot patch.” It requires an owner, technical/business justification, authorized risk acceptance, compensating controls, an expiration date, and a remediation plan. Expired exceptions must automatically route to review/escalation.

## 8. Pre-Production Patch Verification

Testing must reflect real workload dependencies and behavior.

Verification layers:

- **Compatibility:** runtimes, drivers, SDKs, agents, extensions, and libraries remain compatible.
- **Functional:** core APIs and business workflows operate properly.
- **Performance:** latency, throughput, CPU/memory, and query plans do not regress beyond thresholds.
- **Security:** vulnerabilities are remediated and policies/certificates are not misconfigured.
- **Data:** migrations, backups, replicas, and transaction semantics remain safe.
- **Operational:** monitoring, logging, auto-scaling, and restarts work.
- **Recovery:** rollback or restore can execute within targets.

Not every patch requires a full regression suite; however, critical workloads and engine/kernel/network changes require testing proportional to impact.

## 9. Deployment Strategies for Maintenance

### 9.1. In-Place Maintenance

Apply changes directly on running resources, such as updating packages and rebooting a VM.

Pros include minimal temporary resources and simplicity in small environments. Trade-offs include downtime or disruption; if a patch fails, rollback can be difficult.

Best suited for workloads with spare nodes or acceptable maintenance windows.

### 9.2. Rolling Maintenance

Update instances/nodes in batches while remaining capacity continues serving traffic.

~~~mermaid
flowchart LR
    A["Healthy fleet v1"] --> B["Drain node 1"]
    B --> C["Patch node 1"]
    C --> D["Health check"]
    D --> E["Continue with next node"]
    E --> F["Fleet v2"]
~~~

Verify remaining capacity handles load while draining nodes; enforce readiness/liveness checks, disruption budgets, and caps on concurrently unavailable nodes.

### 9.3. Canary Maintenance

Update one node or small cohort and observe before expanding. Canaries should represent real workloads, regions, hardware families, and tenant mixes. Picking only the least-loaded node risks missing production bugs.

### 9.4. Blue-Green Replacement

Provision a new fleet, validate, and shift traffic; keep the old fleet during the rollback window. This avoids patching live runtimes in place but increases temporary cost and requires data/state compatibility.

### 9.5. Comparison

| Strategy | Downtime | Temporary Cost | Rollback Capability | Key Risk |
| --- | --- | --- | --- | --- |
| In-place | Possible | Low | Often harder | Serving nodes directly impacted |
| Rolling | Avoidable with enough redundancy | Moderate | Per node/cohort | Insufficient capacity while draining |
| Canary | Limited to small cohort | Moderate | Easy to halt rollout | Unrepresentative cohort |
| Blue-green | Often low with clean cutover | Higher | Fast before state diverges | Data/schema compatibility |

No strategy guarantees zero downtime if the application, database, network, or load balancer was not designed for transition.

## 10. Maintenance Windows and Change Management

Maintenance windows must balance low user impact with availability of operators and vendor support if trouble occurs.

Change records should document:

- Objective and resource scope.
- Reason, advisory/CVE, or lifecycle deadline.
- Owner and approver.
- Dependencies and tenant/region impact.
- Test plan, deployment plan, and health gates.
- Backup/restore readiness.
- Rollback/forward-fix criteria.
- Start/end times and communication plan.
- Monitored metrics and on-call responder.
- Outcomes, incidents, and evidence.

### 10.1. Normal, Standard, and Emergency Changes

- **Standard change:** repeatable, low-risk, pre-approved procedure.
- **Normal change:** requires impact assessment/review per process.
- **Emergency change:** addresses urgent vulnerabilities or incidents; requires expedited approval and post-hoc review.

Emergency does not mean skipping logs, evidence, or validation. Organizations must record decision makers and accepted risks.

### 10.2. Change Freezes

Change freezes reduce risk ahead of critical business events, but should never block emergency patches for actively exploited vulnerabilities. Policies need emergency exceptions and risk-based evaluation.

## 11. Backup and Rollback Before Maintenance

Before modifying databases, storage, OS, or control planes, verify a recoverable state exists.

Check:

- Latest backups and restore points.
- PITR/log chains where needed.
- Snapshot consistency and encryption key access.
- Database replication lag and failover readiness.
- Infrastructure configuration/versions.
- Availability of old images/artifacts for redeployment.
- Schema backward compatibility.
- Validity of secrets/certificates post-transition.
- Resumability of data migrations.

**Code rollback** does not equal data rollback. If a patch executes destructive migrations or writes data under a new schema, reverting binaries may be unsafe. Use expand–migrate–contract, compatibility layers, or forward fixes when rollback is infeasible.

## 12. OS, VM, and Compute Lifecycle

Compute resources must be updated and replaced along their support lifecycle.

### 12.1. Golden Images and Immutable Infrastructure

A golden image is a standardized, hardened image with required packages updated and tested before use. With immutable infrastructure, instead of manually patching long-lived VMs, pipelines build new images and replace instances via rolling/blue-green deployment.

Benefits:

- New instances share uniform configuration.
- Easy traceability via image digest/version.
- Reduced configuration drift.
- Easier rollback to prior artifacts when state permits.

Trade-offs include needing build/test pipelines and keeping state outside instances. Never store sole business state on ephemeral VM local disks.

### 12.2. OS End-of-Support

When an OS reaches security end-of-support, upgrade or migrate to a supported image/OS. Extended support, if offered, is only a conditional, costly bridge requiring a clear retirement deadline.

## 13. Container Images and the Software Supply Chain

Container images bundle OS packages, runtimes, application dependencies, and agents. An outdated base image can leave every downstream image vulnerable even when application code is unchanged.

Workflow should include:

1. Select base images from trusted publishers.
2. Pin digests instead of relying solely on mutable tags in production.
3. Scan OS/packages/libraries and generate SBOMs.
4. Verify signatures/provenance per policy.
5. Rebuild images whenever base images receive patches.
6. Test and publish new artifacts.
7. Roll out by cohort.
8. Confirm old pods/nodes have been replaced.
9. Retire old image digests per retention policy.

Do not scan only at build time. Runtime inventory must detect which digests containers actually run; otherwise, new images sit in the registry while workloads keep running old images.

## 14. Kubernetes and Managed Control Plane Lifecycle

Kubernetes clusters consist of multiple components requiring compatibility-aligned upgrades:

- Managed control plane version.
- Worker node images and kubelet.
- Container runtime.
- CNI/network plugins.
- CSI/storage drivers.
- Ingress/controllers/service meshes.
- CRDs and operators.
- Helm charts/application manifests.
- Deprecated API versions.

Check Kubernetes/provider version skew policies, PodDisruptionBudgets, node pool capacity, and workload compatibility on newer nodes. Upgrade control planes and node pools in provider-supported order.

Before upgrading:

- Scan API deprecations and manifests.
- Verify admission webhook/operator compatibility.
- Ensure sufficient spare capacity for draining.
- Check stateful workloads and local volumes.
- Back up cluster configuration/etcd if required by the model.
- Test upgrades in staging.
- Verify autoscalers and network/storage plugins.

## 15. Database Engine and Schema Lifecycle

Database maintenance carries high risk due to transactions and durable data.

Types of changes:

- Minor/patch engine updates.
- Major version upgrades.
- Parameter/configuration changes.
- Extension/driver upgrades.
- Schema migrations and data backfills.
- Storage/instance class changes.
- Certificate/credential rotations.

Major upgrades typically require compatibility assessments covering SQL behavior, collations, extensions, drivers, replication, and query planners. Depending on engine and managed service, dump/restore, in-place upgrades, or replication-based migrations may be needed.

### 15.1. Expand–Migrate–Contract

1. Expand the schema with compatible new fields/tables.
2. Deploy code reading/writing compatibly with both old and new schemas.
3. Backfill data in batches with checkpoints and rate limits.
4. Switch consumers/queries to the new schema.
5. Validate completeness and performance.
6. Contract by removing old schema elements once no clients rely on them.

Avoid destructive changes simultaneous with code deployments unless a verified recovery plan exists.

## 16. Storage Lifecycle and Data Retention

Storage can grow in cost, degrade in performance, or reach hardware/service end-of-life. Separate hot, warm, cold, and archive data by access patterns.

Activities:

- Monitor capacity, latency, IOPS, and throughput.
- Expand volumes before hitting limits.
- Select appropriate storage classes.
- Configure tiering lifecycle rules.
- Verify replication, durability, and checksums.
- Test backup/restore.
- Enforce retention and legal holds.
- Delete expired data per policy.
- Safely decommission volumes/object buckets.

Lifecycle tiering does not replace backups; archived data must also remain restorable and decryptable. Deleting resources requires checking snapshots, replicas, object versions, and backup retention.

## 17. Network and Certificate Lifecycle

Network resources carry distinct versions/limits/expirations: routes, firewall rules, load balancers, NAT, VPNs, gateways, DNS records, IP addresses, and certificates.

Maintenance considerations:

- Certificate/TLS expiration, renewal, and trust chains.
- Stale or overly broad firewall/security group rules.
- Route/NAT capacity and quotas.
- VPN/peering/transit gateway lifecycles.
- DNS TTLs and cutovers.
- Load balancer/ingress controller versions.
- Private endpoints and certificate trust.
- IPv4/IPv6 transitions if applicable.
- Vendor appliance firmware/end-of-support.

Network changes can sever management access or paths to KMS/identity. Maintain out-of-band/backup management access and validate routing from representative subnets/workloads.

## 18. Managed Services and Provider Changes

Managed services reduce infrastructure toil yet still have lifecycles: engine versions, parameters, API versions, maintenance events, service quotas, feature deprecations, and pricing changes.

Subscribe to service health/advisories, track end-of-support dates, and configure suitable maintenance windows. For provider-driven maintenance, understand:

- Can you choose the window or does the provider schedule it?
- Does the service fail over or restart?
- Is advance notice given and can updates be deferred?
- Will downtime or connection resets occur?
- Does the new version introduce breaking behavior?
- Which clients/drivers/extensions need verification?
- Are post-maintenance audits/events emitted?

Never assume provider maintenance is always transparent. Applications need retries, reconnects, graceful degradation, and disruption testing.

## 19. Capacity Management and Resource Right-Sizing

Resource lifecycles include ensuring adequate capacity while avoiding over-provisioning.

Monitor:

- CPU/memory utilization and throttling.
- Disk capacity, IOPS, latency, and queue depth.
- Network throughput, packet drops, and connection counts.
- Database connections, locks, cache hits, and replication lag.
- Queue depth/age and worker saturation.
- Autoscaling events and quota headroom.
- Growth rates, seasonal peaks, and forecasts.

Right-sizing should not rely solely on average utilization. Examine peaks, p95/p99, bursts, failover capacity, and maintenance headroom. In multi-zone setups, remaining zones must handle designed load when one zone is drained or lost.

## 20. Configuration Drift and Compliance

Drift is divergence between declared desired state and actual runtime state. Drift arises from console edits, ad-hoc scripts, manual hotfixes, or faulty automation.

Controls:

- Manage infrastructure via IaC and shared versioned modules.
- Detect drift periodically or via events.
- Restrict direct console/runtime change permissions.
- Record change/audit logs.
- Review and import valid changes back into the source of truth.
- Auto-remediate only low-risk, thoroughly tested rules.
- Track emergency change exceptions with expirations.
- Compare configurations against security baselines.

Never auto-revert all drift in production without understanding its cause; automation could erase a critical hotfix or cause an outage. Classify drift, identify owners, and remediate deliberately.

## 21. Resource Decommissioning

Decommissioning carries high data and security risk. A VM serving zero traffic may still retain disk snapshots, service accounts, public IPs, DNS records, or credentials.

Procedure:

1. Confirm owner and retirement reason.
2. Identify consumers/dependencies via inventory and telemetry.
3. Notify stakeholders and set an observation window.
4. Drain traffic/jobs and migrate workloads.
5. Export/back up data per retention/legal policies.
6. Verify backup/restore and data ownership.
7. Revoke identities, tokens, certificates, and secrets.
8. Remove associated DNS/routes/firewalls/public IPs/endpoints.
9. Delete compute/storage upon approval; handle snapshots/object versions.
10. Remove monitoring/alert/deployment/CI references.
11. Update inventory, CMDB, cost tags, and audits.
12. Verify no unexpected billing or access paths remain.

### 21.1. Secure Deletion

Deleting a VM does not remove data from snapshots, backups, or replicas. Follow provider retention and secure deletion semantics. For encrypted data, crypto-erasure can be effective once key scope and backup dependencies are verified.

Never delete backups under legal hold or mandatory retention. Resource offboarding must align with data governance and security.

## 22. Maintenance Automation and Orchestration

Automation can scan, open change requests, patch, reboot, verify, and update inventory—but requires safety guardrails:

- Target selection from owned inventory.
- Exclusions/approvals for critical workloads.
- Batch size and concurrency limits.
- Pre-checks for capacity/health/backups.
- Stop conditions if error rates/latency breach thresholds.
- Post-checks for versions/service health.
- Idempotent retries without repeating destructive actions.
- Audit logs and artifact versioning.
- Human approval for emergency/high-impact changes.
- Prevent concurrent maintenance on shared critical dependencies.

~~~mermaid
flowchart TD
    A["Inventory and vulnerability scan"] --> B["Risk assessment / priority"]
    B --> C["Create maintenance plan"]
    C --> D["Pre-check: health, capacity, backup"]
    D --> E["Canary patch"]
    E --> F{"Health gates pass?"}
    F -- "No" --> G["Stop / rollback or forward-fix"]
    F -- "Yes" --> H["Progressive rollout"]
    H --> I["Post-check and compliance scan"]
    I --> J["Update inventory and evidence"]
~~~

Automation must respect provider API quotas and avoid thundering herds. Group waves by region/cell/tenant, add jitter, and verify service health before advancing to the next batch.

## 23. Maintenance Metrics and SLOs

A maintenance program must be measured to understand actual coverage and bottlenecks.

| Metric | Interpretation |
| --- | --- |
| Asset inventory coverage | Percentage of discovered resources tracked in inventory |
| Patch compliance | Percentage of in-scope assets meeting baseline |
| Patch latency | Time from advisory/patch release to remediation |
| Vulnerability exposure window | Duration assets remain exposed to actionable vulnerabilities |
| Unsupported asset count | Number of resources/runtimes past end of support |
| Certificate expiry coverage | Percentage of certificates with owners, alerts, and renewals |
| Maintenance success rate | Percentage of changes completing within criteria |
| Change failure rate | Percentage of maintenance causing incidents/rollbacks |
| Mean time to remediate | Time to resolve findings |
| Drift rate | Count/share of configurations diverging from baseline |
| Orphaned resource count | Resources lacking clear owners/consumers |
| Cost of idle resources | Spend on resources delivering no value |

Do not target high patch compliance alone; track exception age and unscannable assets too. Define the denominator clearly: which assets are in scope, which are exempted, and the snapshot timestamp.

## 24. Runbooks and Post-Maintenance Reviews

A maintenance runbook should cover:

- Scope and target selection.
- Preconditions/health checks.
- Change/patch artifacts and checksums/signatures.
- Dependencies and execution order.
- Backup/rollback/recovery instructions.
- Batch sizes, concurrency, and rate limits.
- Metric dashboards and alerts.
- Stop conditions/escalation.
- Business/technical validation.
- Change closure and inventory updates.

After maintenance, review errors, actual duration, affected tenants/regions, false positives, patch failures, and automation gaps. If a change caused an outage, hold a post-incident review to fix the process rather than merely adding more approval gates.

## 25. Common Design Pitfalls

| Pitfall | Consequence | Prevention |
| --- | --- | --- |
| Incomplete inventory | Hosts/packages/credentials missed for patching | Asset discovery and multi-source reconciliation |
| Relying solely on severity | Patching in wrong order relative to exposure/business impact | Risk-based prioritization |
| Patching everything at once | Large blast radius if a patch breaks | Canaries, waves, stop conditions |
| No capacity reserve when draining nodes | Latency spikes or outages | Maintenance headroom and disruption budgets |
| Updating only the container registry | Workloads keep running stale images | Runtime digest inventory and rollout verification |
| Assuming managed services self-maintain completely | Missed client, config, version, or deprecation impacts | Shared responsibility matrix |
| Untested database migrations | Unable to roll back or data loss | Backups/PITR, expand-contract, and rehearsals |
| Rolling back binary while keeping new schema | Incompatibility and data corruption | Backward compatibility/forward-fix plans |
| Exceptions without expiration | Vulnerabilities persist indefinitely | Owners, risk acceptance, and deadlines |
| Decommissioning only compute | Secrets, disks, IPs, DNS, and snapshots linger | Offboarding checklists across the resource graph |
| Auto-reverting all drift | Erases needed hotfixes or triggers outages | Drift triage and controlled remediation |
| Ignoring certificate expirations | TLS outages when certificates expire | Inventory, automated renewal, early alerts |
| Never testing backup restores | Corrupted backups or inaccessible keys | Periodic restore drills |
| Not tracking change failure rate | Repeated maintenance-induced incidents | Post-change reviews and trend metrics |
| Leaving idle resources forever | Rising cost and larger attack surface | TTLs/tags/owners and lifecycle cleanup |

## 26. Design and Implementation Process

1. **Build inventory:** resources, software, versions, owners, regions, tenants, dependencies, and costs.
2. **Track support lifecycles:** EOL, advisories, certificate expirations, API deprecations, and provider notices.
3. **Establish policies:** patch SLAs, maintenance windows, exceptions, approvals, and emergency paths.
4. **Prioritize by risk:** exploitability, exposure, impact, data sensitivity, and blast radius.
5. **Select change strategy:** in-place, rolling, canary, blue-green, or immutable replacement.
6. **Pre-verify:** compatibility, tests, capacity, backups, keys/secrets, and dependencies.
7. **Deploy in waves:** batch sizes, concurrency, health gates, and stop conditions.
8. **Post-verify:** actual running versions, business workflows, security scans, performance, and replication.
9. **Close change:** evidence, exceptions, inventory/CMDB updates, and owner sign-off.
10. **Manage drift/capacity:** right-sizing, quotas, lifecycle tiering, and cleanup.
11. **Decommission:** migrate, export, revoke, delete, and check for residual access/data.
12. **Review:** patch latency, compliance, change failures, costs, and runbook improvements.

## 27. Well-Architected Review

| Perspective | Design Questions |
| --- | --- |
| **Reliability** | Does maintenance use canaries/rolling updates and capacity headroom? Are backups/PITR/rollbacks tested? Do rollouts halt when health gates fail? |
| **Security** | Are asset inventory and patch SLAs complete? Are credentials/certificates rotated? Are EOL assets and exceptions controlled? |
| **Performance Efficiency** | Do patches/reboots impact latency? Is remaining capacity adequate when draining nodes? Are databases/storage/networks benchmarked after upgrades? |
| **Cost Optimization** | Are idle/orphaned resources eliminated? Are storage tiers/compute right-sized? Are maintenance and temporary blue-green costs forecasted? |
| **Operational Excellence** | Are owners, runbooks, change records, drift detection, inventory, alerts, and post-maintenance evidence in place? |

### Acceptance Checklist

- [ ] Inventory covers cloud resources, runtimes, packages, certificates, secrets, and dependencies.
- [ ] Resources have owners, environments, regions, support dates, and lifecycle states.
- [ ] Patch policies and SLAs reflect risk and exposure.
- [ ] Vulnerability assessments evaluate exploitability, exposure, and business impact.
- [ ] Emergency patches have approval paths, mitigations, and post-hoc reviews.
- [ ] Artifacts/images have provenance, signatures/digests, and appropriate scans.
- [ ] Deployments use canary/rolling/waves or an approved downtime plan.
- [ ] Capacity headroom suffices when draining/rebooting a node group.
- [ ] Backups/PITR/key access and rollback/forward-fix plans are verified.
- [ ] Database, Kubernetes, network, and managed-service upgrades have compatibility plans.
- [ ] Drift has detection, owners, and remediation guardrails.
- [ ] Certificate/secret/identity expirations are inventoried and alerted.
- [ ] Decommissioning verifies dependencies, data retention, secrets, IPs, DNS, snapshots, and backups.
- [ ] Exceptions have risk owners, compensating controls, and expirations.
- [ ] Metrics measure patch coverage, patch latency, unsupported assets, and change failures.
- [ ] Runbooks, post-maintenance reviews, and restore/rollback drills are practiced.

## 28. Applied Exercise

An equipment rental platform runs across three availability zones. It operates 40 VMs on an OS nearing end-of-support, 25 containerized microservices, one Kubernetes cluster, a managed database service, and several internal certificates. The provider announces the current database engine version will reach end-of-support in 90 days. A critical vulnerability was just disclosed in the active base image; several tenants run large workloads and cannot tolerate prolonged downtime.

Design:

1. What inventory must be collected to capture all assets, versions, owners, and dependencies?
2. How do you prioritize among the zero-day/base image, OS end-of-support, and database engine EOL?
3. What strategy migrates the 40 VMs to a new OS in cohorts while preserving capacity during node drains?
4. What pipeline rebuilds/scans/signs container images and verifies runtimes actually run the new digests?
5. What plan upgrades the Kubernetes control plane, node pools, CNI/CSI, and deprecated APIs?
6. What database upgrade plan covers backup/PITR, compatibility testing, canary, or replica-based migration?
7. How will related certificates and service secrets be renewed/rotated after maintenance?
8. What are the change windows, emergency path, rollback/forward-fix criteria, and stop conditions?
9. What process decommissions old OS/images/resources, revokes credentials, and handles snapshots/backups per retention?
10. Which metrics prove patch coverage, patch latency, availability, and change failure rates meet targets?

A well-grounded approach addresses the exposed vulnerability via an emergency path first while scheduling OS/EOL transitions and database upgrades in waves. Container images are rebuilt from patched base images, provenance-checked, and rolled out by digest. Kubernetes upgrades follow version compatibility and node disruption budgets. Databases transition only after PITR, replication/restore, drivers, and application compatibility are verified; old resources retire only after traffic, data, secrets, and dependencies have migrated or been revoked per policy.

**Core takeaway:** maintenance and resource lifecycle management are integral to architecture, not post-deployment chores. Inventory and ownership reveal what needs care; risk-based patching sets priorities; canaries/rolling updates and backups limit impact; verification proves changes took effect; and safe decommissioning eliminates lingering cost, residual data, and unnecessary access.
