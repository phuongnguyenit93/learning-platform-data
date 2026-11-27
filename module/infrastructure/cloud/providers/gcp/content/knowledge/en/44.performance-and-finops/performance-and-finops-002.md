# VM Rightsizing and Idle Resource Cleanup

A Google Cloud project can run smoothly while still wasting budget: a VM running 24/7 even though it only serves reports for a few hours a week, an application server provisioned with excessive vCPU and RAM, a Persistent Disk detached from its VM yet still incurring charges, or a static IP address no longer attached to any service. In the FinOps model, detecting and handling these resources is done continuously, with evidence and clear accountability — not as an ad-hoc campaign to delete unowned resources at the end of a quarter.

**Rightsizing** means adjusting provisioned resources to match actual demand while still meeting performance, reliability, and safety targets. **Idle resource cleanup** means verifying, decommissioning, or removing resources that no longer deliver value. On Google Cloud, Compute Engine Recommender, Cloud Monitoring, Cloud Billing, and resource management tools help identify candidates; production change decisions still need to be reviewed in the application's context.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between oversized VMs, idle VMs, and unused resources.
- Interpret Compute Engine machine type recommendations and idle VM recommendations.
- Combine CPU, RAM, disk, network, batch schedules, and SLOs to evaluate change authorization.
- Establish a VM resizing workflow with approval, rollback, and verification.
- Detect idle Persistent Disks, custom images, and static external IPs.
- Understand cost differences among stop, suspend, delete, and snapshot.
- Estimate realized savings using billing data instead of list prices alone.
- Establish ownership, labels, alerts, and automation to prevent recurring waste.
- Design a FinOps optimization backlog without impacting critical workloads.

## 1. Rightsizing Does Not Mean Picking the Smallest Machine

A system has three types of requirements to balance:

- **Sufficient capacity**: handling peaks and growth without hitting CPU, memory, storage I/O, or network limits.
- **Availability and recovery**: maintaining headroom to handle failover, rollouts, and unexpected events.
- **Reasonable cost**: not paying for unnecessary vCPU, RAM, or other resources.

A VM using an average of only 8% CPU should not automatically be downsized aggressively. It might run end-of-month batch jobs, serve as a standby node, or consume significant RAM despite low CPU. Conversely, a VM averaging 45% CPU that frequently suffers memory pressure may still need to move to a more suitable machine family.

### Distinguishing Three Action Types

| Situation | Issue | Typically Considered Action |
|---|---|---|
| Oversized VM | VM does real work, but vCPU/RAM is significantly over-provisioned | Change machine type, adjust resources |
| Idle VM | VM does virtually no work during the observation window | Stop, schedule runtime, or remove after verification |
| Unused resource | Disk, image, IP, or other resource no longer referenced | Reclaim, save needed copies, then delete |

Do not choose an action based on a single metric. Analysis must combine workload type, owner, environment lifecycle, and operational constraints.

## 2. The FinOps Loop: Inform, Optimize, Operate

A rightsizing program should run cyclically:

~~~text
Inventory + Labels + Billing
           |
           v
   Usage data / SLO / Recommender
           |
           v
       Triage candidates
           |
           v
 Owner confirmation + Risk assessment
           |
           v
   Pilot / Change / Rollback plan
           |
           v
 Verify performance + Actual billing
           |
           v
   Review + Automation + Next cycle
~~~

**Inform** clarifies who is using and paying for a resource. **Optimize** evaluates and executes changes in the right context. **Operate** turns lessons into labels, policies, review cadences, and continuous controls.

A report with 100 recommendations does not mean 100 guaranteed savings opportunities. They must be grouped by impact, confidence level, effort, dependencies, and risk level.

## 3. Data to Collect Before Resizing

| Data Category | Examples | Why It Is Needed |
|---|---|---|
| Resource | Project, zone, VM name, machine type, disks | Verify the exact target |
| Ownership | Team, service, environment, cost center | Who is authorized to approve changes |
| CPU | Average, p95/p99, peak, spikes | Avoid CPU starvation |
| RAM | Used/available, pressure, swap, OOM | Avoid out-of-memory failures |
| Storage | Capacity, IOPS, throughput, latency | Machine type can affect throughput |
| Network | Throughput, packet rate, egress | Avoid network bottlenecks when downsizing |
| Application | Request throughput, latency, queue depth | Connect to user experience |
| Operations | Batch windows, backups, failover, maintenance | Avoid missing infrequent tasks |
| Cost | Actual SKU paid, discounts, commitments, labels | Estimate savings accurately |
| Architecture | MIG, autoscaling, instance template, HA | Pick the right place to change configuration |

### Measuring CPU and RAM Over Cycles

Cloud Monitoring provides CPU usage, disk, and network metrics for Compute Engine. For memory and process-level metrics, installing the Ops Agent or an appropriate telemetry mechanism can improve evaluation data.

You should review:

- Business hours and off-hours.
- Weekdays vs. weekends.
- Scheduled batch jobs or backups.
- Billing cycles, shopping peaks, and seasonal events.
- Incidents or failovers that may force a VM to carry extra load.

Do not make an immediate decision from a single average number on a dashboard. A service whose p99 latency is sensitive to CPU spikes needs headroom even if average utilization is low.

## 4. Compute Engine Machine Type Recommendations

Compute Engine Recommender suggests VM sizes based on available CPU and memory metrics. According to Google Cloud documentation, the standard mechanism uses the **last 8 days of data**; CPU statistics are typically based on 60-second averaging intervals and may therefore miss very short spikes.

Recommender may suggest:

- Reducing vCPU when CPU utilization is low most of the time.
- Reducing RAM when memory goes unused.
- Increasing vCPU or RAM if the VM is frequently resource-constrained.
- Choosing a standard or custom machine type matching the machine family's constraints.

A recommendation is a **signal to evaluate**, not a command to apply blindly. Some resources do not support recommendations; the documentation also notes limitations for VMs with GPUs/TPUs, certain disk types, memory-optimized machine families, and VMs created by other services.

### Viewing Recommendations in the Console

1. Select the correct project and open Compute Engine → VM instances.
2. Check the Recommendations column to find VMs with change suggestions.
3. Open details to inspect the proposed machine type and estimated savings.
4. Cross-check with Cloud Monitoring, SLOs, and load schedules.
5. Record the decision: accept, defer, or dismiss with a reason.

A VM without a recommendation is not necessarily optimized. Data may be missing, the workload may not be supported, or savings may fall below Recommender's display threshold.

### Viewing Suggestions with gcloud

Read-only command:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.MachineTypeRecommender \
  --format=yaml
~~~

Appropriate recommendation read permissions are required; viewing suggestions does not require permission to modify the VM. The output contains a description, estimated impact, and proposed operations. Verify the resource name and zone in the payload before creating a change ticket.

### Evaluating Suggestion Reliability

| Question | If Unclear |
|---|---|
| Does the data cover weekend/month-end peaks? | Extend observation using other telemetry |
| Does the agent report full memory metrics? | Add the Ops Agent and benchmark |
| Is there a batch job that runs only monthly? | Review scheduler and job history |
| Is the VM a standby or disaster recovery node? | Keep capacity per RTO/RPO |
| Are there license or CPU architecture constraints? | Verify compatibility before resizing |
| Are there minimum disk/network throughput requirements? | Check machine type documentation |
| Does the VM belong to a Managed Instance Group? | Edit the instance template/MIG, not just one VM |

## 5. Pre-Downsizing Evaluation Checklist

A good change request answers the following questions:

1. Which project and environment does this VM belong to?
2. Who are the service owner and approver?
3. Does the machine serve a load balancer, database, job, or instance group?
4. What do peak/p95/p99 metrics look like over a representative period?
5. What are the current CPU/memory and target configuration?
6. What are the storage, network bandwidth, disk count, licensing, and architecture limits?
7. How long must the VM be stopped, and what change window is approved?
8. Are there viable snapshots/backups and rollback procedures?
9. Which SLIs must remain stable after the change?
10. When will recommendations and actual billed costs be re-evaluated?

**Never resize production directly with one click without defining downtime and rollback.** Changing a machine type typically requires stopping the VM, updating the configuration, and starting it again; thus, it can cause disruption.

## 6. Example: Rightsizing a Java Application VM

Suppose a VM serves a Spring Boot API with this profile:

| Attribute | Current State | Observation |
|---|---|---|
| Machine type | 8 vCPU, 32 GiB RAM | Hypothetical example |
| CPU median | 11% | 3 weeks of data |
| CPU p95 | 32% | Not the absolute peak |
| RAM p95 | 14 GiB | One batch job spikes to 20 GiB |
| Disk read/write | Low | No I/O bottleneck |
| Network | Low | Bursts during exports |
| Availability | 99.9% SLO | Runs behind a load balancer |

One option is to test a 4 vCPU, 24 GiB RAM machine (if the machine family/zone allows that shape) rather than dropping all the way to 2 vCPU and 8 GiB. You should benchmark load, scaling/failover behavior, and GC pause times.

### Controlled Change Procedure

**Step 1 – Pre-change inspection**

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,machineType,disks,networkInterfaces,labels)"
~~~

Store the output securely; do not put sensitive information in public tickets. Record the old machine type and monitoring baseline.

**Step 2 – Evaluate backup and recovery readiness**

If the VM stores critical data, verify appropriate backups/snapshots, application consistency, and restore permissions. Do not just take an ad-hoc snapshot and treat it as a complete rollback plan.

**Step 3 – Execute within the maintenance window**

After obtaining approval and verifying machine type constraints:

~~~bash
gcloud compute instances stop VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE

gcloud compute instances set-machine-type VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=TARGET_MACHINE_TYPE

gcloud compute instances start VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

The commands above **mutate production state**. They are an illustrative runbook and must not be executed automatically during analysis. VMs with Local SSDs, GPUs, special licenses, or service management may require different steps.

**Step 4 – Verify**

- The VM is RUNNING and health checks pass.
- The Java service starts and database/secret connections work.
- CPU, RAM, GC, p95/p99 latency, and error rate are within thresholds.
- Batch/scheduler jobs and exports still run properly.
- No increase in timeouts, retries, or queue backlogs.
- Billing after a sufficiently long period reflects the new cost.

**Step 5 – Rollback**

If SLOs/performance degrade, follow the procedure to stop the machine and restore the original machine type. The plan must account for zone capacity/quota and recovery time rather than assuming reverting will always be instantaneous.

### VMs in a Managed Instance Group

If the workload runs inside a MIG, machine type configuration is usually managed through an instance template or MIG update mechanism rather than manually editing one VM and hoping the change survives recreation. Update the configuration source, control rolling update/canary rollout, and measure group capacity.

## 7. Idle VM Recommendations

An **Idle VM** is a VM with very low CPU and network metrics under Recommender's criteria during the observation window. According to current documentation, the idle VM Recommender observes **14 days** by default, and can be configured from 1 to 14 days in some cases.

A VM flagged as idle does not mean it is unowned or safe to delete. It could be:

- A failover standby machine.
- Running end-of-month batch jobs.
- A bastion or operational host kept ready for incidents.
- An irregularly scheduled build agent.
- A test environment temporarily retained for a project.

### Viewing Idle VM Recommendations

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.IdleResourceRecommender \
  --format=yaml
~~~

Appropriate recommendation read permissions in the project are required. Record the VM name, observation period, and owner, then cross-check job schedulers, audit logs, network traffic, and application owner interviews.

### Choosing an Action

| Situation | Recommended Decision |
|---|---|
| Dev VM used only during business hours | Scheduled stop/start if no off-hours dependencies exist |
| Test VM from a completed project | Tag as candidate, quarantine, then delete after approval |
| Warm standby VM for incidents | Keep and document the exception/DR purpose |
| VM running only end-of-month reports | Move to scheduled execution or retain capacity with justification |
| Production VM unexpectedly idle | Investigate routing, workload, or deployment before stopping |
| Oversized VM still needed 24/7 | Rightsize instead of stopping |

## 8. How Stop, Suspend, and Delete Differ in Cost and Risk

| Action | Impact | Things to Note |
|---|---|---|
| Stop VM | Stops CPU/runtime, keeps configuration and disks | Disks, snapshots, and external IPs may still incur charges |
| Suspend VM | Preserves memory state where supported | May incur state storage fees; not supported on all VMs |
| Delete VM | Deletes the instance resource | Auto-delete disks, Local SSDs, and IPs may be affected; requires backup and review |
| Schedule start/stop | Runs only during needed windows | Must consider timezone, batch jobs, and on-call needs |
| Rightsize | Changes vCPU/RAM/machine type | May require downtime and benchmarking |

**Stopping does not mean a zero bill.** Persistent Disks, snapshots, reservations, or static external IPs can still generate charges. Additionally, access permissions, ephemeral external IPs, and Local SSD data must be reviewed before stopping.

### Safe Stop Procedure

1. Confirm the owner and environment.
2. Check workloads, connections, background jobs, and dependencies.
3. Ensure it is not a VM in a MIG/managed system expected to auto-start.
4. Define the stop schedule and observation window.
5. Have a restart runbook, readiness checks, and DNS/IP verification.
6. Record remaining disk/IP costs.
7. Do not delete before the quarantine period ends.

A stopped VM preserves its disks and configuration for faster rollback than deletion. However, long-unused disks continue adding to the bill; after the retention period, decide whether to archive/snapshot or delete per policy.

## 9. Cleaning Up Unused Resources: Disks, Images, and IPs

Compute Engine provides another group of Recommenders to identify several types of idle resources: Persistent Disks, custom images, and external IP addresses. According to Google Cloud documentation, many cases are evaluated after roughly **15 days** of non-use/detachment, though exact criteria vary by resource type.

| Resource | Signs Worth Checking | Risk When Reclaiming |
|---|---|---|
| Persistent Disk | Never attached or detached for a long time | May contain data, snapshots, or forensic evidence |
| Custom image | Not used to create disks and not referenced by templates | May be a golden image used for DR |
| Static external IP | Not attached to any resource | May be in DNS or partner allowlists |
| Snapshot | Old, redundant retention, or missing owner | May be the only recovery point |
| VM image version | Not deployed for a long time | May be needed for rollback or compliance |
| Auxiliary load balancer/resources | Backend no longer in use | May be a backup entry point |

Not every type in the table has a dedicated Recommender or identical threshold. For snapshots and other services, supplemental inventory, policies, or billing analytics are needed.

### Viewing Idle Disk Recommendations

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.disk.IdleResourceRecommender \
  --format=yaml
~~~

For regional external IPs:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=REGION \
  --recommender=google.compute.address.IdleResourceRecommender \
  --format=yaml
~~~

For custom images, location is global:

~~~bash
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=global \
  --recommender=google.compute.image.IdleResourceRecommender \
  --format=yaml
~~~

### Inventory with gcloud

~~~bash
gcloud compute disks list \
  --project=PROJECT_ID \
  --format="table(name,zone,status,sizeGb,users)"

gcloud compute addresses list \
  --project=PROJECT_ID \
  --format="table(name,region,status,address)"

gcloud compute images list \
  --project=PROJECT_ID \
  --no-standard-images \
  --format="table(name,creationTimestamp,status)"
~~~

These commands are read-only. Do not treat an empty `users` field as sufficient proof to delete a disk; the disk may hold critical data or be reserved for recovery.

### Detached Disks

Before deleting a detached disk:

1. Verify it is not part of a restore workflow, GKE PV, or forensic investigation.
2. Check contents, encryption, and application ownership safely.
3. If retention is needed, create an appropriate snapshot and test restore.
4. Record the snapshot ID, retention, owner, and deletion policy.
5. Delete the disk only after owner approval.

Snapshots can be cheaper than disks, though not always; cost depends on disk type, location, actual stored size, and storage policy.

### Unattached Static External IPs

An unattached address may still be listed in DNS, firewall allowlists, or partner configurations. Before releasing it:

- Check Cloud DNS, external DNS records, and partner documentation.
- Verify it is not used for DR/cutover.
- Check whether any service hardcodes the IP.
- Give the owner time to confirm and quarantine.
- Log the change, because a released IP may not be recoverable.

## 10. Estimating Savings Correctly

Distinguish **potential savings** from **realized savings**.

Potential savings is an estimate from a recommender or model. Realized savings is the actual cost reduction after a change, accounting for workload, discounts, and newly incurred costs.

### Hypothetical Example

A VM has:

- Current compute cost: 300 USD/month.
- Projected new machine type: 190 USD/month.
- Implementation and testing cost: 200 USD one-time.
- Disk and network: unchanged.

Projected monthly compute savings:

~~~text
300 - 190 = 110 USD/month
~~~

Over 12 months, before other variables:

~~~text
110 × 12 - 200 = 1,120 USD
~~~

These numbers are illustrative only, not Compute Engine pricing. If the VM receives a committed use discount or sustained use discount, actual savings may differ. If a commitment still has to be paid for, shrinking the VM does not automatically reduce commitment charges.

### Reference Financial Formula

~~~text
Net realized savings
  = Normalized baseline cost
  - New cost for the same workload scope
  - Operational/newly incurred resource cost
  - Amortized change cost per period
~~~

A bill drop caused by lower request volume should not be credited entirely as rightsizing savings. Normalize by demand, such as cost per request, cost per batch, or serving hours.

### Billing Export and Labels

Cloud Billing export to BigQuery enables analysis by project, service, SKU, labels, credits, and time. Use cost allocation labels to tie resources to teams, cost centers, and environments. For financially sensitive tables, restrict IAM and grant only necessary analytical access.

Do not compare two months with different day counts directly without normalizing for hours or request volume. After stopping a VM, disks/IPs may still incur charges; keep them in both baseline and actual comparisons.

## 11. Weekly Operational FinOps Workflow

A workflow can start simply:

| Day/Activity | Responsible | Output |
|---|---|---|
| Start of week: collect recommendations | FinOps/Platform | Candidate backlog |
| Triage and assign owners | Platform + app owners | Risk/impact-ranked list |
| Check telemetry and dependencies | SRE/App team | Accept/defer/dismiss decision |
| Review change plan | Change owner | Downtime, rollback, and approver |
| Execute on schedule | Operations | Change log and verification |
| End of period: reconcile billing | FinOps | Realized savings and lessons learned |

### Statuses of a Recommendation

- **New**: newly discovered, no owner yet.
- **Investigating**: checking metrics and dependencies.
- **Approved**: has a change and rollback plan.
- **Applied**: resource has been modified.
- **Verified**: meets SLO and cost targets.
- **Deferred**: postponed with justification/re-review criteria.
- **Rejected**: unsuitable, with evidence.
- **Exempt**: resource must be kept for standby, DR, or compliance.

Do not just count closed recommendations. Better KPIs include actual money saved, SLO stability, percentage of candidates with an owner, turnaround time, and false-positive rate.

## 12. Automating Cleanup with Guardrails

You can use Cloud Scheduler, Cloud Functions/Cloud Run jobs, Pub/Sub, and Workflows to detect or schedule resource actions. However, automatically deleting resources based on a single low metric carries major risk.

A safe design:

~~~text
Recommender + Cloud Asset Inventory
             |
             v
   Scheduled discovery job
             |
             v
   Labels + owner + exclusion rules
             |
             v
   Candidate report / ticket
             |
             v
   Owner approve + grace period
             |
             v
   Stop / snapshot / release (separate approval)
             |
             v
   Verify + actual billing + audit
~~~

### Recommended Guardrails

- Dry-run by default; never auto-execute destructive actions.
- Denylist/allowlist by project, folder, environment, and resource.
- Labels such as owner, cost-center, environment, lifecycle, retention-until.
- Respect resources with deletion protection or membership in a Managed Instance Group.
- Verify dependencies and batch schedules longer than the Recommender window.
- Two-level approval for databases, data-holding disks, and production.
- Tested backup/restore before deleting critical data.
- Change logs, rollback, and escalation paths.
- Cap the number of resources modified per run.
- Never remove labels or permissions to bypass policies.

### Policy Example

A development VM may only be auto-stopped if:

- It has the label `environment=dev`.
- The owner agrees to the schedule.
- No batch jobs or integration tests run during the stop window.
- It does not belong to an auto-managed MIG/cluster.
- A restart script and smoke test exist.
- Savings are measured after a few cycles.

If any condition is uncertain, open a ticket instead of stopping.

## 13. Practical Scenario: Cleaning Up a Java Test Environment

A Java/Spring development team created:

- 6 VMs running integration tests.
- 3 Persistent Disks detached from older machines.
- 2 unattached static external IPs.
- 1 old custom image no longer in any instance template.
- 1 production standby VM with low CPU.

### Step 1 — Collect and Classify

FinOps pulls idle VM and idle resource reports, mapping each item to an owner, repository, pipeline, or application. The production standby VM is marked as an **exception** with justification and RTO/RPO, rather than deleted based on CPU.

### Step 2 — Check Usage

Logs show the 6 test VMs only need to run 09:00–18:00 on weekdays, except the nightly pipeline runs a test suite at 22:00. The team adjusts the test schedule or keeps an on-demand pool instead of stopping all machines at 18:00.

### Step 3 — Pilot the Changes

In staging:

- Downsize machine types for two VMs after benchmarking.
- Set up an owner-approved stop/start schedule for development VMs.
- Test restarting the test harness.
- Snapshot disks still containing data that needs retention.
- Verify external IPs are not in DNS or allowlists.

### Step 4 — Clean Up Resources

After the quarantine period and approvals:

- Delete disks no longer needed, only after data evaluation.
- Release unused IPs.
- Delete the custom image if it is not part of rollback/DR procedures.
- Keep the standby VM and document the exception rationale.

### Step 5 — Measure Effectiveness

Compare Cloud Billing before and after, isolating the effect of changes in test volume. Also monitor test pass rate, startup time, job duration, and cost per CI run to avoid saving infrastructure money at the expense of team productivity.

## 14. Common Pitfalls

| Pitfall | Consequence | Remedy |
|---|---|---|
| Deciding from one day's average CPU | Misses peaks or batch jobs | Observe multiple cycles and p95/p99 |
| Treating recommendations as mandatory commands | Can break SLOs | Review owner, workload, and constraints |
| Stopping a VM and assuming zero cost | Disks/IPs/snapshots still incur charges | Track all related resources |
| Deleting idle disks without checking data | Data loss or loss of restore points | Quarantine, snapshot, restore test |
| Releasing external IPs without checking partners | Broken DNS/allowlists | Dependency review before release |
| Resizing a VM inside a MIG directly | Config recreated or out of sync | Edit instance template and roll out |
| Picking smaller machines while ignoring IOPS/network | Performance degradation | Check machine type limits |
| Ignoring CUDs and credits | Miscalculated realized savings | Use Billing export and actual pricing |
| Applying the same rule to dev and prod | Accidentally stopping critical workloads | Policy by environment and criticality |
| Auto-deleting due to missing owner label | Data can be lost | Missing owner should trigger a ticket, not deletion |
| Skipping rollback testing | Prolonged downtime during resizing | Runbook, capacity verification, and smoke tests |
| Only counting applied recommendations | Unknown real financial value | Measure savings, SLOs, and operational effort |

## 15. Pre-Production Checklist

### Discovery and Classification

- [ ] Project, zone, resource ID, and owner are confirmed.
- [ ] Cost baseline exists by workload and environment.
- [ ] Machine type and idle resource recommendations have been reviewed.
- [ ] Sufficient CPU, RAM, disk/network, and application telemetry are available.
- [ ] Batch jobs, backups, failovers, and peaks longer than the observation window have been checked.
- [ ] Exceptions are marked: DR, standby, licensed/special hardware.
- [ ] Resources managed by separate orchestrators are excluded.

### Change and Rollback

- [ ] Target machine type satisfies CPU/RAM/IOPS/network constraints.
- [ ] Change ticket, approver, maintenance window, and SLA are in place.
- [ ] Backup/restore strategy exists for data-bearing resources.
- [ ] Runbook exists for stop/resize/start or snapshot/delete.
- [ ] Plan exists to restore machine type, service, and network.
- [ ] No resource is stopped/deleted based on a single metric.
- [ ] Health, SLOs, and business flows are verified after the change.

### FinOps and Continuous Operations

- [ ] Post-change billing is compared against a normalized baseline.
- [ ] Disk, snapshot, external IP, and commitment costs are accounted for.
- [ ] Owner/environment/cost center labels are applied.
- [ ] Periodic reviews, audit trail, and exception policy exist.
- [ ] Automation includes dry-run, approvals, and blast-radius limits.
- [ ] Savings are booked after verification, not just forecasts.
- [ ] No content QA or infrastructure deployment outside the lesson scope is performed.

## Conclusion

VM rightsizing and idle resource cleanup are FinOps practices grounded in data and clear accountability. Compute Engine Recommender helps uncover VMs eligible for resizing, underutilized VMs, and unused disks, images, and IPs. Yet a recommendation is only a starting point: teams must verify workloads, owners, memory, IOPS/network, peaks, SLOs, and rollback procedures before acting. Afterward, Cloud Billing and application telemetry reveal whether realized savings are sustainable. When organized as a guarded feedback loop, rightsizing reduces waste while protecting service reliability on GCP.

## References

- [Compute Engine: Machine type recommendations](https://docs.cloud.google.com/compute/docs/instances/apply-machine-type-recommendations-for-instances)
- [Compute Engine: Idle VM recommendations overview](https://docs.cloud.google.com/compute/docs/instances/idle-vm-recommendations-overview)
- [Compute Engine: View and apply idle VM recommendations](https://docs.cloud.google.com/compute/docs/instances/viewing-and-applying-idle-vm-recommendations)
- [Compute Engine: Idle resources recommendations](https://docs.cloud.google.com/compute/docs/viewing-and-applying-idle-resources-recommendations)
- [Compute Engine: Stop or restart instances](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Compute Engine: Change machine types](https://docs.cloud.google.com/compute/docs/instances/changing-machine-type-of-stopped-instance)
- [Compute Engine: Managed Instance Group rightsizing](https://docs.cloud.google.com/compute/docs/instance-groups/apply-machine-type-recommendations-managed-instance-groups)
- [Cloud Billing: Export billing data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Cloud Billing: Cost optimization](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
- [Google Cloud Recommender documentation](https://docs.cloud.google.com/recommender/docs)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)
