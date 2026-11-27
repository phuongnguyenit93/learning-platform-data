# Scheduling Start/Stop and Removing Unused Resources

Compute resources frequently continue accruing charges when no user or workload needs them. A development environment may only be active during working hours; a testing machine may only be needed for a few hours; a VM spun up to investigate an incident may be forgotten after the work finishes. Without start/stop schedules and reclamation workflows, organizations pay for idle capacity, disks, IPs, snapshots, NAT, or load balancers that no longer deliver value.

Compute cost management combines two activities: **resource lifecycle scheduling** so instances run only when needed, and **removing unused resources** after verifying data, dependencies, and owners. Stopping a VM does not eliminate all charges; deleting a VM does not mean every associated disk or snapshot can be safely deleted. This lesson covers scheduling, verification, reclamation, and measuring savings while protecting resilience and operational requirements.

## 1. Why Schedule and Clean Up Resources?

Cloud makes provisioning compute fast, yet easy allocation also lets resources outlive their original need. Common situations:

- Development or test VMs running overnight and on weekends with nobody using them.
- Temporary instances spun up for benchmarks, migrations, or incident handling and never reclaimed.
- Autoscaling groups keeping minimum capacity higher than off-hours demand.
- Disks, snapshots, images, and backups retained long after workloads were deleted.
- Public IPs, load balancers, NAT gateways, or static addresses no longer attached to any service.
- Test node pools or clusters still running after projects ended.
- Resources created manually outside IaC workflows, lacking an owner or expiration date.

Start/stop scheduling reduces billable compute hours. Orphaned resource cleanup reduces storage, networking, and supporting service charges. Both activities must coordinate with work schedules, SLAs, backups, patching, and recovery workflows.

## 2. Classify Resources Before Automating

Do not apply the same policy to every resource. Classify by environment, criticality, reproducibility, and data state.

| Group | Examples | Policy Typically Considered |
|---|---|---|
| Development | Dev VMs, database sandboxes, integration environments | Stop after hours; start on schedule or on demand |
| Test/QA | Test runners, temporary staging, performance test beds | Schedule by test shifts; auto-reclaim after TTL |
| Demo/training | Lab VMs, workshop clusters, training sandboxes | Stop after sessions; delete by expiration date |
| Production stateless | Reproducible web/API workers | Autoscale with load; scale-in only per policy |
| Production stateful | Databases, file servers, nodes holding local data | Do not auto-stop without HA/backup workflows and approval |
| Batch/ephemeral | Data processing jobs, build agents, short-lived workers | Launch on event; auto-delete upon completion |
| Shared platform | NAT, load balancers, registries, logging, cluster control planes | Manage by platform owner and multi-workload dependencies |

Questions to answer for every resource:

- Who owns it and who bears the cost?
- Which workloads depend on it?
- Does it hold data that must be retained?
- Can it be recreated from an image/IaC?
- How long does it take to boot and return to service?
- Are there SLA, RTO, RPO, or maintenance window requirements?
- Is the resource bound by licenses, compliance, or retention policies?

## 3. How Stopping, Pausing, Hibernating, and Deleting Differ

Cloud providers use different terms and behaviors. Understand the actual state of each resource type.

| Action | Compute Capacity | Disks/Data | Addresses and Auxiliary Services | Recoverability |
|---|---|---|---|---|
| Stop/deallocate VM | Usually stops compute charges once properly stopped | Disks usually persist and continue billing | IPs, licenses, backups, or attached services may keep billing | Can restart, though IP or host placement may change per platform |
| Hibernate | Compute paused; memory state may be saved per service | Disks and saved-state storage continue existing | May incur state-storage and disk fees | Resumes faster than a full boot where supported |
| Scale to zero | Replica/worker count drops to 0 | Shared storage may persist | Certain endpoints and control planes keep billing | Re-provisions on demand, possibly with cold starts |
| Terminate/delete VM | Compute is deleted | Disks may be deleted or kept per policy | IPs, NICs, load balancers, and snapshots may remain | Must launch a new instance or restore from backup/image |
| Delete resource | Resource is removed | Data may be permanently lost if no copy exists | Dependencies may be affected | Recoverable only if required backups or artifacts exist |

Do not use the word "stop" as if it always means zero remaining cost. Persistent disks, snapshots, reserved capacity, static IPs, licenses, or managed services can keep billing. Verify the billing state of each service and actual invoices.

## 4. Designing Demand-Driven Start/Stop Schedules

A good schedule reflects when workloads actually need to run, includes startup buffers, and defines clear exceptions.

Examples:

| Environment | Illustrative Operating Hours | Policy |
|---|---|---|
| Developer sandbox | Monday–Friday, 08:00–19:00 | Start before work hours; stop after end of day |
| QA shared | Per booked test schedule | Run per reservation; auto-stop after grace period |
| Training lab | Per class session | Start before session; stop when finished |
| Performance test | Per benchmark window | Start only with owner present; retain result logs then stop |
| Production API | 24/7 or per SLO | Do not use hard shutdown schedules; use autoscaling and capacity policies |
| Batch worker | Per job schedule or queue | Scale to backlog; scale to 0 when idle if supported |

These schedules are illustrative only. Use the operations team's timezone and handle holidays and daylight saving if applicable. For workloads serving users across countries, one team's local schedule must not accidentally shut down a global service.

### 4.1. Startup Buffer Time

If users start work at 09:00, do not start VMs right at 09:00. Account for:

- VM provisioning or deallocated-to-running transition.
- OS boot, disk mounting, and network configuration.
- Cloud-init/startup scripts or extensions.
- Starting auxiliary databases/caches.
- Connecting to secret managers, service discovery, and dependencies.
- Health checks and readiness probes.
- Application, JIT, and cache warm-up.

Measure p50/p95 startup times and add an appropriate buffer. For environments needing instant readiness on the hour, start earlier or use a warm pool.

### 4.2. Shutdown Buffer Time

Do not stop abruptly at closing time if users, sessions, jobs, or unflushed data remain active. You can:

1. Send an upcoming-stop notification.
2. Stop accepting new workloads.
3. Drain active requests and workers.
4. Wait for jobs to finish or checkpoint.
5. Verify backups/snapshots if policy requires.
6. Stop/deallocate the instance.
7. Verify final state and record the outcome.

If users are still working, allow bounded extensions and log the owner, reason, and new expiration time.

## 5. Using Tags to Manage Schedules and Reclamation Rights

Automation needs to know which resources are eligible for auto-stop or deletion. Tags describe owner, environment, schedule, and expiration date.

Reference tag set:

| Tag | Example | Purpose |
|---|---|---|
| Environment | dev, test, staging, prod | Distinguish environments |
| Owner | team-platform | Responsible team |
| CostCenter | CC-204 | Cost allocation |
| Schedule | office-hours-vn | Map to approved schedule |
| AutoStop | true | Permit automated stopping |
| AutoDelete | false | Whether auto-deletion is permitted |
| ExpiresAt | 2026-12-01T00:00:00Z | Expiration of temporary resources |
| DataClass | public, internal, restricted | Support retention decisions |
| ManagedBy | terraform, platform-scheduler | Lifecycle management source |

Tags are not a standalone security boundary. Anyone allowed to edit tags could mislabel production resources as dev or enable AutoDelete. Restrict tag-modification permissions, enforce policy checks, and cross-reference against account/project, resource type, and inventory.

## 6. Automating Stop/Start Schedules

Schedules can be executed using schedulers, automation services, functions, or workflows. General architecture:

1. Scheduler emits an event based on configured timezone and schedule.
2. Automation queries resources with matching schedule tags.
3. Policy validates environment, state, owner, and exceptions.
4. For stop actions, workloads drain or run pre-stop hooks.
5. Automation calls stop/deallocate APIs.
6. System verifies final state and writes audit logs.
7. At start time, automation starts resources.
8. Health checks confirm readiness and alert on failures.

~~~mermaid
flowchart TD
    A[Scheduler / approved schedule] --> B[Automation workflow]
    B --> C[Read inventory and tags]
    C --> D{Resource eligible?}
    D -- No --> E[Skip and log reason]
    D -- Yes --> F[Check dependencies / exceptions]
    F --> G{Action}
    G -- Stop --> H[Drain workload and flush]
    H --> I[Stop / deallocate]
    G -- Start --> J[Start VM / scale workload]
    I --> K[Verify state and write audit]
    J --> L[Health check / readiness]
    L --> K
~~~

Automation should be idempotent: re-running the same schedule must not trigger errors or destructive actions. For instance, if a VM is already stopped, stopping it again should be treated as desired state already reached, not an error triggering endless retries.

### 6.1. Avoiding Reliance on a Single Scheduler

Schedulers or automation services can also fail. For important workloads:

- Track executed and missed schedules.
- Record the last run timestamp and result.
- Use bounded retries with backoff.
- Alert when start/stop fails to reach desired state.
- Maintain a manual operation runbook when automation fails.
- Prevent stop schedules from firing if policy or dependency checks cannot confirm a safe state.

## 7. Provider-Specific Tool Examples

Service names and capabilities evolve by time, region, and SKU; verify current platform documentation before implementing.

| Platform | Common Mechanisms | Application |
|---|---|---|
| AWS | Amazon EventBridge Scheduler, Systems Manager Automation, Lambda, or Instance Scheduler solution | Schedule EC2 start/stop by tags and schedules |
| Azure | Azure Automation, Automation Runbooks, Logic Apps, or Start/Stop VMs solutions | Schedule VM start/deallocate and act by resource group/tag |
| Google Cloud | Cloud Scheduler combined with Cloud Functions/Cloud Run Jobs/Workflows and Compute Engine API | Invoke instance start/stop APIs by schedule and labels |

Do not grant full account admin privileges to automation just to stop a few VMs. Create dedicated roles scoped to allowed resources/tags, start/stop actions, and specific projects/subscriptions/accounts. If automation reads inventory, grant only required metadata read permissions.

## 8. Tag-Based Scheduling and Exceptions

One schedule can govern many resources, provided an exception mechanism exists.

Example policies:

- Only resources with `Environment=dev` or `test` are evaluated.
- `AutoStop=true` is mandatory.
- `Environment=prod` is always excluded from regular stop schedules.
- If `MaintenanceHold=true` is present, skip.
- If `ExpiresAt` is in the past and `AutoDelete=true`, enter reclamation workflow after checks.
- If owner is missing or tags are incomplete, send alerts and request verification instead of auto-deleting.

Define precedence between user tags and central policies. For instance, user-applied tags must never override production stop-protection lists.

### 8.1. Temporary Exceptions

A team may need to run an after-hours benchmark. Support time-bounded exceptions:

- Owner and reason.
- Exempted resources.
- Start and expiration times.
- Approver if environment governance requires it.
- Automatic reversion to standard schedule upon expiration.

Avoid indefinite exceptions. If an extension is needed, require the owner to renew it so inventory always reflects real demand.

## 9. Safe Shutdown Before Stopping

Stopping a VM while an application writes data can corrupt transactions, lose jobs, or force filesystem recovery. Before stopping:

- Stop accepting new requests via readiness probes or deregistering from load balancers.
- Drain active connections and in-flight requests.
- Stop consumers from pulling new messages.
- Wait for jobs to finish or safely checkpoint/requeue.
- Commit/roll back transactions per database procedures.
- Flush buffers and close files/sockets.
- Verify backups or snapshots per policy.
- Stop services via service manager or graceful shutdown hooks.
- Check instance state before automation finishes.

For production VMs, stop schedules are generally unsuitable unless the service is explicitly built for scheduled downtime with clear notifications, failover, data consistency, and SLAs.

## 10. Starting in Dependency Order

When bringing an environment back up, starting all VMs simultaneously is not always safe. Define dependency order:

1. Network, VPN, private connectivity, and DNS.
2. Required storage or volumes.
3. Databases, caches, or message brokers.
4. Identity/secret retrieval and service discovery.
5. Application backends and workers.
6. Load balancer registration and ingress.
7. Smoke tests and readiness notifications.

If applications start before databases, startup may fail or trigger retry storms. Applications should implement backoff retries, timeouts, and readiness probes reflecting critical dependencies.

For multi-component systems, use workflows with a dependency graph instead of independent schedules prone to race conditions.

## 11. Stopping/Starting Autoscaling Groups, Node Pools, and Clusters

Do not stop individual instances managed by an autoscaling group or cluster scheduler. The control plane may replace instances automatically or mark nodes unhealthy.

Considerations:

- Adjust desired/min/max capacity through approved policies.
- Check autoscalers, scheduled actions, and other policies that might override changes.
- Drain nodes before reducing desired capacity.
- Respect PodDisruptionBudgets and remaining node capacity.
- Do not remove the last node if the control plane or essential services depend on it.
- When scaling from 0, verify node bootstrap, image pulls, secrets, and networking.
- For managed clusters, check whether control plane or management fees continue when workers drop to 0.

Scale to zero suits workloads tolerating cold starts without always-on replicas. For fast-response APIs, maintain minimum replicas or warm capacity.

## 12. Identifying Unused Resources

Orphaned resources are resources no longer used by active workloads that still exist and may incur costs. Do not judge solely by low CPU.

Examples:

- Disks no longer attached to any VM.
- Old snapshots or images outside backup/rollback workflows.
- Public IPs no longer attached to any endpoint.
- Load balancers lacking active backends or DNS records.
- NAT gateways with zero traffic still kept provisioned.
- NICs or volumes left behind by deleted instances.
- VMs with no owner or prolonged inactivity.
- Old container images/tags no longer deployed.
- Backups or log archives exceeding defined retention.

A low-activity resource may still be essential for DR, compliance, warm standby, or failover. Verify owner, dependencies, and purpose before queuing for reclamation.

## 13. Orphaned Resource Detection Workflow

A safe workflow includes:

1. Collect inventory across cloud accounts/projects/subscriptions.
2. Normalize resource ID, type, region, zone, owner, and tags.
3. Cross-reference relationships among VMs, disks, NICs, IPs, snapshots, load balancers, and networks.
4. Check usage metrics, traffic, attachments, and last-active timestamps.
5. Compare against IaC state, deployment inventory, or CMDB if permitted.
6. Flag candidates and record why they are suspected orphans.
7. Notify owners and provide a confirmation window.
8. Place resources into quarantine/retention state if needed.
9. Delete only when policy, owner, and dependency checks pass.
10. Store audit logs, outcomes, and recovery instructions for accidental deletions.

Do not delete a resource merely because it lacks tags. Resources missing metadata should be labeled unknown-owner and routed to review, as they may belong to shared platforms or managed services.

### 13.1. Using Multiple Signals to Identify Unused Resources

| Signal | What It Suggests | Limitation |
|---|---|---|
| Low CPU/network | Minimal recent activity | Could be standby or scheduled workload |
| Unattached | Possibly an orphaned disk | Could be a volume awaiting DR or migration |
| No backends | Load balancer may be unused | Could be staged for blue/green deployment |
| Zero traffic | Endpoint may be rarely used | Could be a standby failover endpoint |
| Missing owner tag | Incomplete metadata | Does not prove the resource is unowned |
| Absent from IaC state | Created manually or by managed service | State may be incomplete or drifted |
| Past `ExpiresAt` | Temporary resource may no longer be needed | Confirm owner and data before deleting |

Combine multiple signals with verification workflows. Never use a single CPU threshold or inactivity window as an auto-delete trigger.

## 14. Retention for Disks, Snapshots, Images, and Backups

Deleting compute resources can leave behind data and copies. Maintain dedicated retention policies:

- Boot disks and data disks: define whether deleted on termination or retained.
- Snapshots: keep recent count or retain by schedule and recovery needs.
- Machine images: keep deployed versions, rollback versions, and approved base images.
- Backups: comply with RPO/RTO, retention, and legal requirements.
- Logs: retain long enough for investigations, audits, and data policies.
- Container images: retain currently deployed tags and rollback releases.

Before deleting, verify backups can restore and data is consistent. An existing snapshot does not guarantee a tested backup. Databases require engine-consistent backups and periodic restore drills.

## 15. Multi-Stage Resource Reclamation Workflow

To lower accidental deletion risk, use a two- or three-stage workflow.

**Stage 1 — Discover:** identify candidates and gather metadata, metrics, dependencies, and estimated cost.

**Stage 2 — Notify/Quarantine:** notify owners, apply a `pending-delete` tag, pause start schedules if appropriate, and wait through a response window. For disks or IPs, detach from workloads only after confirming safety.

**Stage 3 — Delete:** recheck attachments, snapshots, backups, policies, and approvals; then delete via audited automation.

~~~mermaid
flowchart TD
    A[Inventory scan] --> B[Orphan candidate]
    B --> C[Check owner and dependencies]
    C --> D{Eligible for reclamation?}
    D -- Unclear --> E[Retain / request owner verification]
    D -- Yes --> F[Notify and quarantine]
    F --> G[Confirmation window expires]
    G --> H[Recheck attachments, backups, policy]
    H --> I{Eligible to delete?}
    I -- No --> E
    I -- Yes --> J[Delete and write audit]
    J --> K[Verify post-reclamation cost]
~~~

If an owner confirms the resource is still needed, update tags, owner, and a new expiration date to prevent repeat alerts. If there is no response, delete only within published policy and permitted resource scope.

## 16. Guardrails and Automation Permissions

Automation can cause broad damage if roles are over-privileged or tag selectors misfire. Build guardrails before enabling enforcement.

- Separate inventory read permissions from stop/delete permissions.
- Create separate roles for stop schedules and deletion workflows.
- Scope actions by resource type and project/account.
- Block auto-deletion of production, databases, or `DataClass=restricted` resources without explicit approval.
- Maintain an allowlist of environments permitted for auto-stop.
- Require both valid `AutoDelete` and `ExpiresAt` before deletion.
- Mandate owner and cost-center tags for new resources.
- Run dry-runs before enabling enforcement.
- Log full details: selector, resource ID, policy, actor, timestamp, and outcome.
- Provide a kill-switch to pause all schedulers if abnormal behavior occurs.
- Use rate limits or small batches to prevent mass accidental deletion.

Stop permissions and delete permissions must stay separate. Stopping is usually reversible via start; deleting can cause data loss and demands stricter controls.

## 17. Example Policy for a Development Environment

Suppose a development team has multiple sandbox VMs. Proposed rules:

- Every dev VM must carry `Owner`, `CostCenter`, and `Schedule`.
- VMs with `AutoStop=true` stop at 19:00 Vietnam time Monday through Friday.
- VMs start again at 08:00 on the next workday.
- Holidays follow a separate calendar.
- Owners may set `MaintenanceHold=true` for up to 24 hours with a reason.
- Temporary VMs must carry `ExpiresAt`; automation alerts before expiration.
- `AutoDelete` defaults to false. After the owner confirms data is unnecessary, resources enter quarantine before deletion.
- Disks and snapshots are evaluated separately under retention rules.
- Ownerless VMs are reported and flagged for verification, never auto-deleted.

Illustrative schedule:

| Time | Action | Check |
|---|---|---|
| 07:45 workday | Start VM | Running state and active networking |
| 08:00 | Health check | SSH/RDP or management agent ready |
| 18:45 | Upcoming-stop notice | Check active sessions and jobs |
| 18:55 | Drain | Reject new tasks, finish active jobs |
| 19:00 | Stop/deallocate | Verify stopped state |
| Weekly | Orphan inventory scan | Send candidate list to owners |
| Monthly | Retention review | Review old disks, snapshots, and images |

Times are illustrative only. Teams must adjust for timezone, holidays, startup durations, and actual working policies.

## 18. Measuring Savings

Do not report only the count of stopped VMs. Measure before-and-after costs alongside operational impact.

Useful metrics:

- Eliminated compute hours.
- Before/after compute costs by environment and owner.
- Percentage of resources stopped on schedule.
- Percentage of timely successful starts.
- Number of out-of-schedule user restart requests.
- Number of jobs interrupted or failed due to stops.
- Number of confirmed and reclaimed orphan candidates.
- Reduced disk, snapshot, IP, NAT, and load balancer costs.
- Percentage of resources missing owner/expiration.
- Number of automation skips due to policies or dependency checks.

### 18.1. Compute Savings Estimation Formula

If an instance has an hourly compute rate \(P\) and is turned off for \(H\) unneeded hours:

\[
Savings_{compute} \approx P \times H
\]

Across multiple instances:

\[
Savings_{gross} = \sum_i P_i \times H_i
\]

Real savings must subtract automation costs, remaining disk/backup storage, IPs or licenses still billed while stopped, plus startup and operational overhead.

\[
Savings_{net} = Savings_{gross} - C_{remaining} - C_{automation}
\]

This formula is an estimate. Billing may include minimums, rounding units, commitment discounts, or other fee components. Reconcile against cost exports or invoices.

### 18.2. Calculation Example

Suppose a development VM has an illustrative compute rate of 0.12 USD/hour. The VM only needs to run 10 hours/day across 5 workdays. If it previously ran 24 hours/day, stoppable hours per week equal:

\[
H = (24 - 10) \times 5 = 70\text{ hours}
\]

Gross compute savings per week:

\[
0.12 \times 70 = 8.40\text{ USD}
\]

If 1.50 USD/week remains for disk and auxiliary services, estimated net savings are 6.90 USD/week before automation overhead and applicable discounts. Prices are illustrative only, not real cloud pricing.

## 19. Common Mistakes

**Stopping all VMs after hours without classification.** Can shut down databases, workers, or shared services. Use environment allowlists and dependency checks.

**Assuming stopping a VM stops all costs.** Disks, snapshots, IPs, licenses, or managed services can keep billing. Reconcile every resource meter.

**Deleting disks right after VM termination.** Disks may hold unique data. Verify owner, backups, and restore capability before deleting.

**Using tags as the sole source of truth.** Tags can be missing or altered. Combine account, resource type, IaC, inventory, and dependencies.

**Scheduling startup too close to work hours.** VMs may still be booting or apps unready. Measure startup time and add buffers.

**Stopping while jobs are running.** Can drop messages or leave partial transactions. Drain, checkpoint, or requeue before stopping.

**Unlimited automation retries.** Can trigger API storms or state thrashing. Use bounded retries, idempotency, and alerts.

**Deleting orphans after a single scan.** Metrics may look low due to seasonal workloads or standby roles. Use quarantine and verification windows.

**Not tracking execution outcomes.** Schedules may fire while VMs fail to start or another automation turns them back on. Log audits and monitor actual states.

## 20. Checklist for Implementing Start/Stop Schedules and Cleanup

- [ ] Classified resources by environment, owner, stateful/stateless, and criticality.
- [ ] Defined operating hours, timezone, holidays, and exceptions.
- [ ] Measured startup times and added buffers before required readiness.
- [ ] Implemented drain, graceful shutdown, checkpointing, and job handling before stops.
- [ ] Verified whether stop/deallocate halts compute billing and which fees persist.
- [ ] Scheduler runs idempotently with bounded retries, audits, and alerts.
- [ ] Standardized `owner`, `environment`, `schedule`, `AutoStop`, `AutoDelete`, and `ExpiresAt` tags.
- [ ] Protected production and stateful resources with dedicated policies.
- [ ] Adjusted autoscaling groups/node pools properly via control planes.
- [ ] Inventory scans verify attachments, dependencies, traffic, and IaC ownership.
- [ ] Orphan candidates enter quarantine with owner confirmation windows.
- [ ] Checked backups, snapshots, images, and retention before deleting.
- [ ] Separated stop and delete permissions, scoped by resources.
- [ ] Ran dry-runs and verified selectors before enabling enforcement.
- [ ] Established pause/rollback procedures if automation causes unexpected impact.
- [ ] Measured compute hours, net cost, and impact on SLOs/users.

## 21. Conclusion

Start/stop scheduling eliminates idle compute hours in development, test, lab, and predictable-schedule workloads. Cleaning up orphaned resources further trims disk, snapshot, IP, NAT, load balancer, and supporting service costs. To do this safely, classify resources, attach owners and expirations, check dependencies, drain workloads before stopping, and verify data before deleting.

Start with dry-runs and schedules on low-risk environments, measure startup/shutdown times, track outcomes, and expand gradually. Separate stop permissions from delete permissions, quarantine orphan candidates, and reconcile savings against real bills. When resource lifecycles have clear owners, schedules, and reclamation rules, compute costs fall while resilience and operations remain under control.
