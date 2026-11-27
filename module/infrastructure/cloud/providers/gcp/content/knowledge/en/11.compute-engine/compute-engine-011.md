# Reservations and VM Capacity Assurance Strategies in Compute Engine

A Java order-processing application may run on a managed instance group (MIG) and autoscale up during peak hours. However, when the MIG needs additional VMs, a **zone** might lack available hardware for the desired machine type. This can happen even when the project has plenty of quota, sufficient budget, and IAM permissions to create VMs. For production systems, large data migrations, or disaster recovery plans, running out of capacity at the critical moment is a major operational risk.

**Compute Engine reservations** reserve a specific quantity of VM capacity with **defined hardware attributes in a specific zone**. That capacity can be consumed immediately by matching VMs or held for a future rollout. In return, **reservations incur charges for reserved capacity even when unused**. A reservation is therefore a capacity-assurance tool, not a discount mechanism.

This lesson belongs to the **Compute Engine** chapter of the `CLOUD_PROVIDERS_GCP` module. Knowledge of project organization, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, and databases is applied to deployment planning, release automation, reliability maintenance, and cost control. The focus here is selecting the right reservation type, forecasting VM counts, verifying consumption, and managing the lifecycle of reserved capacity.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **quota**, **zonal capacity**, **reservations**, **committed use discounts (CUDs)**, and **Spot VMs**.
2. Explain why reservations are bound to a **zone** and require VMs with matching hardware attributes.
3. Choose between **on-demand reservations**, **future reservations**, and **automatic/specific** consumption modes.
4. Use **shared reservations** across multiple projects and determine who administers and who pays.
5. Estimate capacity across baseline, peak, rolling updates, and incident recovery.
6. Use `gcloud` to create, inspect, consume, modify, and clean up reservations in a lab.
7. Monitor `count`, `assuredCount`, `inUseCount`, and unused capacity costs.
8. Combine reservations with MIGs, GKE, and multi-zone strategies without mistaking a reservation for HA.

## 1. Why Do You Need Reservations When You Already Have Quota?

| Concept | Question It Answers | Example |
| --- | --- | --- |
| **Quota** | What is the maximum resource volume the project is permitted to consume? | Enough N2 CPU quota remaining in the region |
| **Zonal capacity** | Does the zone's physical infrastructure have matching hardware free? | Does zone `asia-southeast1-b` have N2 machines free? |
| **Reservation** | Is capacity already pre-allocated for matching VMs? | 6 `n2-standard-4` VMs reserved in zone b |
| **CUD/commitment** | Is there a usage or spend commitment for discounted rates? | Term-based pricing commitment |
| **Provisioning model** | Under which mode does the VM consume capacity? | Standard vs. Spot |

Having quota **does not guarantee** hardware is available in a zone. Conversely, creating a reservation also **requires sufficient quota**; a reservation is not a way to bypass resource limits.

~~~mermaid
flowchart TD
    A["App needs more VMs"] --> B{"Sufficient quota and create permissions?"}
    B -->|No| C["Check quotas/IAM"]
    B -->|Yes| D{"Matching reservation has free capacity?"}
    D -->|Yes| E["VM consumes reserved capacity"]
    D -->|No| F{"Zone has regular on-demand capacity?"}
    F -->|Yes| G["Create VM from available capacity"]
    F -->|No| H["May fail with resource availability error"]
    E --> I["Proceed with boot, networking, and app checks"]
    G --> I
~~~

**A reservation does not create VMs.** You still must configure images, boot disks, VPC subnets, firewalls, service accounts, startup scripts, and application monitoring.

## 2. What Does a Reservation Actually Reserve?

A Compute Engine reservation typically specifies:

- **Zone**: where physical capacity is held.
- **Machine type**: e.g., `n2-standard-4`.
- **VM count**: number of matching VMs the reservation holds.
- **Minimum CPU platform** if specified.
- **GPU type/count** and **Local SSD count/interface** if supported by the machine type and reservation.
- **Compact placement policy** or additional attributes, if used.

Reservations **do not reserve** boot disks, Persistent Disks, network egress, external IPs, Cloud Load Balancing, Cloud Storage data, or Cloud SQL. Those resources have independent allocation and billing rules.

### 2.1. A Reservation Is a Zonal Resource

~~~text
Project: atlas-commerce-prod
Region: asia-southeast1
Zone: asia-southeast1-b
Reservation: orders-n2-reserved
Machine type: n2-standard-4
VM count: 6
~~~

Capacity in `asia-southeast1-b` does not automatically shift to `asia-southeast1-a`. During a zonal outage, holding a reservation in that zone **does not keep the service running**. Systems requiring HA must distribute workloads and plan capacity across **multiple zones** per recovery scenarios.

### 2.2. VM Attributes Must Match

| Attribute | Typical Requirement | Common Pitfall |
| --- | --- | --- |
| Zone | VM and reservation in the same zone | Same region, different zone |
| Machine type | Exact machine type match | VM `n2-standard-2`, reservation `n2-standard-4` |
| Minimum CPU platform | Matching setting, including default mode | Specifying a different CPU platform |
| GPU | Matching model and count if present | Different GPU model or count |
| Local SSD | Matching count and interface if present | VM adds SSDs not included in reservation |
| Reservation affinity | Matching automatic/specific mode | Forgetting to target a specific reservation |
| Project | Owner or authorized consumer project | VM outside shared reservation scope |
| Placement policy | Matches if reservation requires it | Missing compact placement policy |

Having the same vCPU count or same region is **not enough**. When a VM fails to consume a reservation, check every matching attribute one by one.

### 2.3. Not Every Machine Type Is Supported Identically

GPUs, HPC, TPUs, bare metal, or special provisioning models may have restrictions or distinct reservation types. Examples in this lesson use **Standard N2 VMs** to illustrate on-demand reservations; do not copy commands verbatim for GPUs or Spot VMs. Always consult [Choose a reservation type](https://cloud.google.com/compute/docs/instances/choose-reservation-type) before selecting resources.

## 3. Types of Reservations to Know

| Type | When Capacity Is Allocated | Characteristics | Best Fit |
| --- | --- | --- | --- |
| **On-demand reservation** | Created immediately if the zone has capacity and quotas/conditions hold | Retained until deleted; billed while existing | Event scaling, migrations, or DR |
| **Future reservation request** | Requested to start on a scheduled date/time | Involves approval workflow, lock-in period, and billing obligations | Planned future capacity needs |
| **Future reservation calendar mode** | Scheduled capacity for supported resource types | Time-bounded with specialized allocation rules | Certain GPU/HPC workloads |
| **Long-term negotiated agreements** | Per custom agreements/plans with Google Cloud | Contractual terms and limits | Specialized large-scale capacity |

**Submitting a future reservation request does not mean immediate capacity is granted.** Monitor approval status, start time, provisioned capacity, and cancellation/modification rules. For on-demand reservations, creation fails immediately if the zone lacks capacity.

### 3.1. When Should You Pre-Reserve Capacity?

- Scheduled traffic campaigns requiring guaranteed extra VMs.
- Phased system migrations onto Compute Engine.
- Preparing headroom for MIG scaling or rollout surges.
- DR readiness judged more critical than standby reservation fees.
- Needing a specific machine/GPU shape during a defined window.

### 3.2. When Should You Avoid Reserving?

- Small labs flexible on machine type, zone, or timing.
- Retryable batch workloads able to wait, switch zones, or use Spot.
- Unknown VM counts, zones, or runtime schedules.
- Sole goal is **unit-price savings**: evaluate CUDs and right-sizing separately.

A forgotten reservation left behind after a lab continues billing even with zero running VMs.

## 4. Automatic Consumption vs. Specific Consumption

### 4.1. Automatically Consumed Reservations

By default, an on-demand reservation allows **matching** VMs to consume it automatically. This can apply to **already running VMs** as well as newly created ones, provided zone, hardware properties, project, and affinity match.

~~~mermaid
flowchart LR
    R["Automatic reservation<br/>6 N2 VMs"]
    A["Existing matching N2 VM"]
    B["Newly created matching N2 VM"]
    C["VM in different zone/machine"]
    A -->|"Can consume"| R
    B -->|"Can consume"| R
    C -. "Does not match" .-> X["Does not consume"]
~~~

**Risk:** a lower-priority VM with the exact same shape could consume capacity meant for production. If you must guarantee which workload gets the reserved slots, use a **specific reservation**.

### 4.2. Specifically Targeted Reservations

Create a reservation with `--require-specific-reservation` so only VMs **explicitly targeting that reservation** can consume its capacity.

~~~bash
gcloud compute reservations create orders-reserved \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --vm-count=6 \
  --require-specific-reservation
~~~

Example VM consuming the reservation in the same project:

~~~bash
gcloud compute instances create orders-01 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --reservation-affinity=specific \
  --reservation=orders-reserved \
  --subnet=SUBNET_NAME \
  --no-address
~~~

**Both commands create billable resources**; execute only in authorized projects and subnets. VMs without external IPs need separate management/egress paths if required by the application.

If the reservation belongs to another owner project and is shared, reference it as:

~~~text
projects/OWNER_PROJECT_ID/reservations/RESERVATION_NAME
~~~

| Criterion | Automatic | Specific |
| --- | --- | --- |
| Must VM name the reservation? | No, if attributes match | Yes |
| Can existing running VMs consume it? | Yes | Primarily VMs configured to target it |
| Contention among matching workloads | Possible | Easy to isolate by ownership |
| MIG/VM configuration | Minimal changes if matching | Requires matching template/affinity |
| Deleting while consumers exist | Separate rules apply | Must clear consuming VMs first |

Never edit affinity or delete production reservations without verifying constraints and VM impact.

## 5. Shared Reservations Across Multiple Projects

An organization may have `commerce-prod`, `commerce-batch`, and a central capacity project `capacity-admin`. If both workloads use identical VM shapes in the same zone, a **shared reservation** pools capacity instead of leaving idle slots in separate silos.

~~~mermaid
flowchart TD
    O["Organization Atlas"]
    P["Owner: capacity-admin"]
    R["Shared N2 reservation<br/>zone asia-southeast1-b"]
    A["Consumer: commerce-prod"]
    B["Consumer: commerce-batch"]
    O --> P --> R
    R -. "Matching VMs" .-> A
    R -. "Matching VMs" .-> B
~~~

Example:

~~~bash
gcloud compute reservations create shared-n2-capacity \
  --project=CAPACITY_OWNER_PROJECT \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-4 \
  --vm-count=12 \
  --share-setting=projects \
  --share-with=commerce-prod,commerce-batch
~~~

Key conditions:

1. The owner project must be allowlisted to create shared reservations under Organization Policy `compute.sharedReservationsOwnerProjects`; the allowed list is **empty by default**.
2. Consumer projects must belong to the same organization as the owner.
3. Do not include the owner in `--share-with`, as the owner is already allowed to consume.
4. The owner needs quota for the reserved resources; consumers need quota for VMs created in their projects.
5. The owner manages reservation configuration; consumers cannot automatically see the reservation from their own projects by default.
6. Limit the number of owner projects and assign clear ownership to track utilization cleanly.

### 5.1. Who Gets Billed?

- The **unused portion** of a shared reservation is typically billed to the **owner project**.
- The **consumed portion** is billed to each respective consumer project per billing rules.
- CUDs and custom pricing depend on the billed project or billing account.
- Sharing itself carries no extra surcharge.

For example, a reservation holds 10 VMs: prod uses 4, batch uses 3, and 3 remain idle. Under a simplified model, capacity equivalent to **4 + 3 VMs** is billed to the two consumers, while the **3 idle VMs** are billed to the owner. Compute is not double-billed for the VMs consuming those slots. Disks, networking, and auxiliary services still bill separately.

## 6. Does a Reservation Guarantee the System Stays Up?

**No.** A reservation assures capacity to create/start matching VMs; it does not resolve:

- A full zonal or regional outage.
- Guest OS, JVM, application, or startup script failures.
- IAM, VPC route, firewall, or DNS misconfigurations.
- Database outages, out-of-sync data, or disk failures.
- Autoscalers picking the wrong zone or machine type.
- Health checks, load balancing, RTO/RPO, or rollback plans.

Suppose an API needs at least 8 VMs, split 4 in zone A and 4 in zone B. If zone A goes down and zone B must carry all 8, zone B must be able to spin up **4 additional VMs**. A reservation in zone A **cannot move** to zone B.

~~~text
Normal state: Zone A = 4 VMs, Zone B = 4 VMs, total 8
When zone A fails:
  Zone B currently has 4 VMs
  Zone B needs 4 more VMs to reach 8
  → Must plan capacity in B, not just in A.
~~~

Reliability requires combining **regional MIGs, load balancers, autoscaling, health checks, backups, replication, DR drills**, and per-zone capacity. A reservation is only one piece.

## 7. Sizing Reserved VM Counts

Never pick `--vm-count` by intuition from current running VM counts alone. Factor in:

| Input | Question |
| --- | --- |
| **Baseline** | How many VMs normally run per zone? |
| **Peak** | How many VMs are needed at forecasted peak load? |
| **Scale-out** | Under load spikes, how many extra VMs are needed and how fast? |
| **Rolling surge** | Do deployments create new VMs before deleting old ones? |
| **DR buffer** | If one zone fails, how many VMs must surviving zones add? |
| **Placement** | Are GPUs, Local SSDs, CPU platforms, or compact placement required? |
| **Duration** | Is capacity needed for a few days or a fixed window? |
| **Cost** | How much idle capacity is approved to carry? |

### 7.1. Automatic Reservations Can Be Consumed by Existing VMs

Suppose 4 N2 VMs are already running in zone B and peak needs 10 VMs. If you create a **10-VM automatic reservation**, what happens is:

~~~text
Reservation count                 = 10
Existing matching VMs consuming   = 4
Reserved but unused slots         = 6
Reserved scale-out headroom       = 6
~~~

Therefore, **creating a 6-VM reservation does not automatically yield 6 additional VMs**: 4 existing VMs can claim slots first, leaving only 2. Always check live `inUseCount`.

### 7.2. Count, assuredCount, and inUseCount

- `count`: requested reservation VM count.
- `assuredCount`: VM capacity confirmed as assured in the zone.
- `inUseCount`: number of VMs currently consuming the reservation.

~~~text
Utilization (%) = inUseCount / count × 100
Unused assured capacity = max(assuredCount - inUseCount, 0)

Example:
  count        = 10
  assuredCount = 10
  inUseCount   = 7
  utilization  = 70%
  unused slots = 3 VMs
~~~

If `assuredCount < count`, confirmed capacity is lower than requested; investigate immediately rather than promising all VMs can be created.

**Low utilization is not automatically wrong**: a DR buffer may intentionally sit idle. Evaluate unused capacity against its protective purpose, not just a raw percentage.

## 8. Reservations vs. Committed Use Discounts

| Criterion | Reservation | CUD / Commitment |
| --- | --- | --- |
| Goal | **Guarantee VM capacity** in a zone/config | **Discounted pricing** in exchange for a usage or spend commitment |
| Scope | Zonal | Varies by commitment type |
| Cost when unused | **Yes**, reserved capacity continues billing | Commitment obligation still applies |
| Guarantees hardware scale-out? | Yes, for assured capacity once created | Not by default, unless paired with attached reservations |
| Combinable? | Yes, when eligible | Yes, subject to specific rules |

A reservation can benefit from CUDs, sustained use discounts, or custom contract pricing when eligible. However, **a reservation is not a separate capacity fee stacked on top** of the compute cost of VMs consuming it.

Some **resource-based commitments** require or allow **attached reservations** and restrict modification/deletion during the commitment term, particularly for GPUs or Local SSDs. Never assume every commitment automatically reserves hardware.

### 8.1. Cost Calculation with Hypothetical Numbers

Suppose a reservation holds 8 identical VMs. The **hypothetical** resource rate is `0.10 USD/VM-hour` before discounts, taxes, or disk/network fees.

| Item | Hypothetical Value |
| --- | ---: |
| Reserved capacity | 8 VMs |
| VMs consuming reservation | 5 VMs |
| Unused capacity | 3 VMs |
| Total capacity cost over 24 hours | `8 × 0.10 × 24 = 19.20 USD` |
| Portion corresponding to 5 active VMs | `5 × 0.10 × 24 = 12.00 USD` |
| Portion corresponding to 3 idle VMs | `3 × 0.10 × 24 = 7.20 USD` |

You do not add another 12 USD of compute on top for those 5 consuming VMs as a double charge. However, **Persistent Disks, network egress, IPs, snapshots, logging, and other resources** bill independently.

**Numbers above only explain the billing mechanics.** For real estimates, use Compute Engine regional machine pricing, CUD terms, and Cloud Billing Reports.

## 9. Lab: Creating and Consuming a Specific Reservation

**Goal:** reserve two N2 VMs in one zone, launch one VM consuming the reservation, verify counts, and clean up. This **lab provisions billable resources**: run it only in an authorized project with a budget and accountable owner.

Prerequisites:

- Compute Engine API enabled with valid project billing.
- Permissions to create/view/delete reservations and VMs; avoid broad Owner roles when narrow roles suffice.
- Sufficient quota and capacity in the zone for a reservation-eligible machine type.
- An actual VPC subnet in the matching region; replace `SUBNET_NAME`.
- Sample VM and reservation names do not collide with production resources; lab data is disposable.

### Step 1: Inspect the Environment

~~~bash
gcloud auth list
gcloud config get-value project
gcloud compute zones list

# Read-only check of existing reservations in the project
gcloud compute reservations list --project=PROJECT_ID
~~~

`gcloud compute zones list` confirms catalog zones exist, not that sufficient **quota** or **zonal capacity** is available for new requests.

### Step 2: Create a Specific Reservation

~~~bash
gcloud compute reservations create lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --vm-count=2 \
  --require-specific-reservation
~~~

Once created, the reserved capacity starts accruing charges. If you hit capacity or quota errors, read the message and adjust zone, machine type, count, or quota requests rather than blindly retrying in a loop.

### Step 3: Inspect Reservation Details

~~~bash
gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format=json
~~~

Fields to inspect in the output:

~~~text
name: lab-n2-capacity
specificReservationRequired: true
specificReservation:
  count: 2
  assuredCount: ...
  inUseCount: ...
  instanceProperties:
    machineType: n2-standard-2
~~~

This is an **illustrative field list**, not a literal API JSON dump. Before any VM consumes it, `inUseCount` is typically 0. Verify `assuredCount` instead of assuming it always equals `count`.

### Step 4: Create a VM Consuming the Reservation

~~~bash
gcloud compute instances create lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --machine-type=n2-standard-2 \
  --reservation-affinity=specific \
  --reservation=lab-n2-capacity \
  --subnet=SUBNET_NAME \
  --no-address
~~~

The VM gets a primary internal IP and no external IPv4. To SSH into it, prepare an authorized management path like IAP TCP forwarding or VPN; reservations **do not open network paths**.

### Step 5: Verify the VM Actually Consumes the Capacity

~~~bash
gcloud compute instances describe lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format="json(resourceStatus,reservationAffinity)"

gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --format=json
~~~

Look for `resourceStatus.reservationConsumptionInfo.consumedReservation` on the VM if returned. Cross-check with `specificReservation.inUseCount` on the reservation. Once the VM is RUNNING and consuming cleanly, expect:

~~~text
count        = 2
assuredCount = 2 (if fully assured)
inUseCount   = 1
unused       = 1
~~~

Never assume a VM is using a reservation merely because it sits in the same zone; **checking consumption fields** is the verification step.

### Step 6: Resize Capacity If Needed

~~~bash
gcloud compute reservations update lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b \
  --vm-count=3
~~~

**This changes billing.** Scaling up depends on quota/availability, while scaling down must respect active consumers and commitment terms. If you do not need to increase the count, **skip this step**.

### Step 7: Clean Up the Lab in Order

~~~bash
# Verify no data needs saving before deleting the VM
gcloud compute instances delete lab-reserved-vm-1 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b

# Verify the VM released its reserved slot
gcloud compute reservations describe lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b

# Delete the reservation to stop reserving capacity
gcloud compute reservations delete lab-n2-capacity \
  --project=PROJECT_ID \
  --zone=asia-southeast1-b
~~~

Deletion commands **are real mutating actions with no simple undo**. For specific reservations, remove consumers before deleting. Afterward, check for leftover boot disks, snapshots, external IPs, and delayed billing updates.

## 10. Reservations with Managed Instance Groups

A **MIG** creates VMs from an instance template and scales automatically based on operational metrics. Reservations can assure capacity for **matching VMs** launched by a MIG per supported features.

~~~mermaid
flowchart TD
    LB["Application Load Balancer"] --> MIG["MIG orders-api"]
    AUTO["Autoscaler"] --> MIG
    MIG --> A["VM from instance template"]
    MIG --> B["VM from instance template"]
    RES["Matching zonal reservation"] -. "Capacity" .-> A
    RES -. "Capacity" .-> B
    HC["Health checks and Monitoring"] -. "App health verification" .-> MIG
~~~

### 10.1. Settings That Must Align

- **Instance template** must match machine type, CPU platform, GPU/Local SSD, reservation affinity, and placement policy if used.
- **Zonal alignment:** MIG VMs created in a zone can only consume reservations in **that exact zone**.
- **Autoscaling:** reservations do not control min/max replicas; the autoscaler still scales by policy.
- **MIG autohealing:** monitors VM and app health; reservations do not replace health checks.
- **VM boot/image/disks/networking:** reservations do not configure any of these.
- **Shared reservations:** operators must track which projects' MIGs are allowed to consume capacity.

### 10.2. Rolling Updates Also Need Capacity

When updating an instance template, a MIG may spin up **surge VMs** before deleting old ones. If reserved capacity only fits current VMs, rollouts can stall even with zero traffic growth.

~~~text
Peak capacity needed per zone
  = Running VMs
  + Autoscaling growth VMs
  + Rolling update surge VMs
  + DR buffer if simultaneous
~~~

Do not mechanically sum every maximum if scenarios cannot coincide; factor in `maxSurge`, `maxUnavailable`, zonal distribution policies, and MIG rollout windows.

## 11. GKE, Batch, Dataflow, and Other Workloads

Compute Engine reservations can be consumed by several supported products, including **GKE, Batch, Dataflow, Managed Service for Apache Spark, and Vertex AI**, though **each product carries specific constraints** regarding machine families, affinity, provisioning, and billing.

### 11.1. With GKE

- **Kubernetes requests/limits** declare how much CPU/memory a Pod requests on a node; they are not Compute Engine reservations.
- **Compute Engine reservations** assure **node VM** capacity in a zone.
- **Node pools** must use compatible node shapes and GKE-supported reservation consumption settings.
- **GKE autoscaling** remains governed by quotas, topology, taints/tolerations, IAM, and node availability.

Reserving nodes does not guarantee Pods will schedule cleanly. Check cluster mode (Standard/Autopilot), machine series, node pools, and product-specific docs before applying.

### 11.2. Do Batch Workloads Need Reservations?

If batch jobs can be rescheduled, retried, moved across zones, or run on Spot VMs, long-term reservations are usually **not cost-optimal**. If jobs face **hard deadlines**, specialized GPU/CPU needs, or large fixed processing windows, evaluate reservations or future reservations.

For Dataflow or Vertex AI, never assume every job mode consumes reservations or CUDs identically to standalone VMs. Always verify current **integration, eligibility, and restrictions**.

## 12. IAM, Organization Policy, and Operational Ownership

| Group | Responsibility |
| --- | --- |
| **Organization admin** | Controls which projects may create shared reservations via `compute.sharedReservationsOwnerProjects` |
| **Capacity owner** | Selects zone/machine/count, manages consumer sharing, monitors utilization, cleans up |
| **Workload owner** | Configures VMs/MIGs/templates/GKE to target the right reservation |
| **SRE** | Monitors scaling, utilization, failover, and rollouts |
| **FinOps** | Optimizes unused capacity, allocates shared costs/CUDs, manages budgets |
| **Security** | Enforces least-privilege IAM and audits reservation modifications |

Grant only required Compute Engine IAM permissions. Viewers do not need create/delete rights; never grant `roles/owner` as a shortcut.

### 12.1. IaC Does Not Eliminate Capacity Risk

Terraform provides `google_compute_reservation` where supported by the provider. For production:

1. Use `plan` to inspect changes to count, machine type, zone, or owner project.
2. Separate approval for capacity changes from routine workload deploys.
3. Never let two pipelines manage the same reservation concurrently.
4. Understand which attribute edits force resource recreation.
5. Never delete a specific reservation with active consumers or an attached reservation bound to a commitment.
6. Document owner, review date, and rollback strategy.

**Rolling back IaC config cannot restore lost capacity guarantees** if a reservation was deleted and the zone no longer has hardware to recreate it.

## 13. Monitoring Reservations and Cost

Cloud Monitoring exposes reservation consumption metrics; the Console and `gcloud compute reservations list/describe` display configurations and consumption counts.

| Signal | Question | Action |
| --- | --- | --- |
| `count` | How many VMs were requested? | Reconcile against capacity plan |
| `assuredCount` | How many are actually assured? | Investigate if lower than `count` |
| `inUseCount` | How many are actively consumed? | Compare with VM count and scaling plan |
| Unused capacity | How many slots sit idle? | Separate intentional DR buffers from waste |
| Creation/scaling errors | Are MIGs/VMs launching as planned? | Check quotas, zones, and affinity |
| Billing cost | How much does unused capacity cost? | Allocate owner/consumer shares and CUDs |
| DR readiness | Does the failover zone have needed headroom? | Run failover drills |

Build dashboards and alerts following [Monitor reservation consumption](https://cloud.google.com/compute/docs/instances/reservations-monitor). Look up exact metric/label names in Metrics Explorer rather than guessing.

### 13.1. Example SRE Report

~~~text
Reservation: orders-capacity-b
Zone: asia-southeast1-b
Machine type: n2-standard-4
Count: 10
Assured: 10
In use: 6
Unused: 4
Owner: Commerce Platform
Reason for unused: rolling surge 2 + DR buffer 2
Review: weekly
~~~

If 4 unused slots are an approved DR buffer, do not shrink capacity simply because utilization is 60%. Conversely, if a team keeps 20 slots for weeks while never exceeding 2 VMs, downsize or delete after impact review.

### 13.2. Essential Alerts

- `assuredCount` remains below `count` for a sustained period.
- `inUseCount` approaches `assuredCount` ahead of planned autoscale or rollout events.
- Lab reservations linger past their expiration date.
- VM creation failures or MIGs stuck below target size.
- Unused capacity spend exceeds owner-approved budgets.

Cloud Billing budgets alert only per threshold config; they **never automatically terminate** reservations or VM billing.

## 14. Common Issues

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| Reservation creation reports insufficient capacity | Zone lacks matching hardware | Lower count or deliberately select another zone/type |
| Reservation creation reports insufficient quota | Project/region quota exhausted | Quotas & System Limits; submit quota increase |
| VM created yet `inUseCount` stays unchanged | VM consumed unreserved capacity | Check `consumedReservation`, zone, and affinity |
| Specific reservation not consumed | Missing target flag or wrong reservation name | `--reservation-affinity=specific` and `--reservation` |
| VM mismatches despite equal CPU count | Differing GPU/SSD/minCpuPlatform/machine type | Compare every hardware attribute |
| MIG fails to scale | Wrong zone, surge, quota, or template mismatch | MIG distribution, autoscaler, reservation |
| Cannot create shared reservation | Owner not allowlisted in Organization Policy | `compute.sharedReservationsOwnerProjects` |
| Consumer cannot use shared reservation | Different org, missing share/quota, or attribute mismatch | Share settings, quotas, affinity |
| Reservation empty yet bill rises | Reserved capacity still incurs charges | Billing Reports and count/inUse |
| Cannot delete specific reservation | VMs still consuming it | List consumers; stop/migrate per process |
| VMs keep running after deleting automatic reservation | Deleting a reservation does not delete VMs | Inspect VMs and billing independently |
| Reservation exists yet DR fails | Capacity in wrong zone, or app/data failures | Check HA, replication, IAM, and DR drills |

~~~mermaid
flowchart TD
    A["VM fails to create or consume"] --> B{"Is assuredCount sufficient?"}
    B -->|No| C["Check quota/capacity/reservation status"]
    B -->|Yes| D{"Do zone + CPU/GPU/SSD match?"}
    D -->|No| E["Fix VM/template attributes"]
    D -->|Yes| F{"Are project and affinity valid?"}
    F -->|No| G["Verify sharing and specific/automatic mode"]
    F -->|Yes| H{"Are free slots and quota available?"}
    H -->|No| I["Inspect count, inUse, autoscaler"]
    H -->|Yes| J["Check disk, image, IAM, VPC, provisioning errors"]
~~~

## 15. Reservation Lifecycle and Deletion Constraints

### 15.1. Automatic Reservations

When you delete an **automatically consumed reservation**, consuming VMs **keep running**; however, Google Cloud no longer holds that capacity for future VM creations or restarts. Compute charges for running VMs continue at regular rates.

### 15.2. Specific Reservations

A **specifically targeted reservation** cannot be deleted while VMs are still consuming it. Clear consumers first. For VMs that are **stopped or suspended** with affinity targeting a specific reservation, restarting or resuming later may require recreating a reservation with the exact name, zone, and attributes. Never delete a reservation solely because traffic is temporarily idle.

### 15.3. Local SSDs and VM State

Stopping VMs with **preserved Local SSDs**, or shutting down inside the guest OS rather than through the Compute Engine control plane, can cause reserved capacity to **continue counting as in use**. Never assume a `STOPPED` VM automatically lowers `inUseCount`. Verify actual status and machine/Local SSD rules.

### 15.4. Future Reservations or Commitment-Attached Reservations

Future reservations in their payment-obligation phase, or reservations attached to resource-based commitments, carry **stricter modification and deletion restrictions**. Lab cleanup steps apply to **standalone on-demand reservations**; never apply those steps to long-term commitments without reviewing terms and getting approval.

### 15.5. Cleaning Up a Reservation Differs from Cleaning Up an Environment

After deleting a reservation, separately audit:

- Whether VMs remain active along with attached disks/snapshots.
- Reserved external IPs, Cloud NAT, load balancers, and network egress.
- Instance templates, startup scripts, and automation that might recreate VMs.
- Cloud Billing Reports after reporting lag settles.
- Shared reservation owner/consumer records and cost-allocation reports.

## 16. End-to-End Scenario: Major Retail Sales Event

Atlas runs `orders-api` on a **regional MIG** behind an Application Load Balancer. The backend connects to Cloud SQL, Pub/Sub, and Cloud Storage. A three-day sales campaign will drive a sharp traffic surge.

**Hypothetical requirements:**

- Normal baseline: 6 `n2-standard-4` VMs.
- Peak load: 14 VMs for a short window.
- Must survive a single-zone outage per SLO targets.
- CI/CD must perform rolling updates with bounded disruption.
- Avoid paying for peak capacity across the entire month.

### 16.1. Breaking Down VM Counts by Zone

Suppose the group spans zones A and B:

| Item | Zone A | Zone B | Explanation |
| --- | ---: | ---: | --- |
| Baseline VMs | 3 | 3 | Total 6 |
| Normal peak VMs | 7 | 7 | Total 14 |
| Scale-out from baseline | +4 | +4 | When both zones are healthy |
| Capacity during single-zone loss | Calculate separately | Calculate separately | Must the surviving zone host all 14 VMs? |
| Rolling update surge | Per MIG config | Per MIG config | New VMs created before old ones removed |

**This table is not yet the final reservation count.** If business rules require all 14 VMs to run in B when A fails, B's sizing must cover that. If deployments pause during incidents, you may not need to stack peak DR and rolling surge simultaneously.

### 16.2. Verified Design Roadmap

1. Define SLOs, acceptable degradation, RTO/RPO, and failure domain (single zone vs. region).
2. Use historical CPU, memory, request latency, load tests, and Cloud SQL connection counts to calculate true VM requirements.
3. Configure regional MIG/instance template, autoscaling policies, and zonal distribution.
4. Evaluate reservations **in every zone launching VMs**, keeping machine types and affinity aligned with templates.
5. If spikes are known far ahead and capacity is tight last-minute, evaluate **future reservation requests** rather than holding on-demand reservations too early.
6. Verify quotas, reservation eligibility, costs, and product limits.
7. Test scale-out, rolling surges, and failover; verify `assuredCount`/`inUseCount` and backend health.
8. Monitor SLOs, error rates, p95 latency, Cloud SQL connection pools, Pub/Sub backlogs, and Cloud Billing.
9. After the campaign: shrink or delete authorized standalone on-demand reservations after ensuring no consumers or restart plans depend on them.
10. Document metrics, decisions, owners, and any intentionally retained idle capacity.

~~~mermaid
flowchart LR
    PLAN["Forecast + load test"] --> SIZE["Size by zone/DR/surge"]
    SIZE --> RES["Create matching reservations"]
    RES --> MIG["MIG with matching template"]
    MIG --> LB["Load balancer + health checks"]
    LB --> OBS["SLO + capacity metrics"]
    OBS --> COST["Budget + unused capacity review"]
    COST --> CLOSE["Downsize/delete on time"]
~~~

**Reservations are only part of capacity assurance.** Overall reliability still relies on the Java runtime, database, load balancer, VPC/IAM, data recovery, and incident response during zonal outages.

## 17. Self-Check Exercises

**Question 1.** A project has ample quota, yet N2 VMs fail to create because the zone lacks capacity. Will requesting a quota increase guarantee new VMs can launch?

*Suggested answer:* No. Quota and zonal capacity are distinct. A reservation can hold capacity ahead of time if created within limits and quota.

**Question 2.** You create a 10-VM reservation and currently only 4 VMs consume it. Does Google Cloud bill for 4 or 10 VMs of capacity?

*Suggested answer:* On-demand reservations bill for all reserved capacity whether used or idle—10 VMs in this case. The 4 VMs consuming the reservation are not double-billed separately for that same compute capacity.

**Question 3.** Can a reservation in `asia-southeast1-b` be consumed by a VM in `asia-southeast1-a` if the machine type matches?

*Suggested answer:* No. The zone must match alongside all other hardware attributes.

**Question 4.** Five matching VMs are already running. Does creating an 8-VM automatic reservation guarantee room for 8 more VMs?

*Suggested answer:* No. The 5 running VMs can automatically consume 5 slots; check `inUseCount` to verify free slots.

**Question 5.** Why might a VM fail to use a specifically targeted reservation even when zone and machine type match?

*Suggested answer:* Missing `--reservation-affinity=specific` or wrong `--reservation` target, mismatched CPU platform/GPU/Local SSD, missing share access, or zero remaining free slots.

**Question 6.** In a shared reservation, the owner project reserves 10 VMs; two consumers use 7 VMs total. Who typically pays for the 3 unused slots?

*Suggested answer:* The owner project typically bears unused capacity charges, while used capacity is billed to the respective consumers per billing rules.

**Question 7.** Does buying a CUD automatically reserve enough N2 instances in a zone when the autoscaler scales out?

*Suggested answer:* Not by default. CUDs provide pricing commitments; reservations assure capacity. Certain resource-based commitments include attached reservations under specific rules.

**Question 8.** A regional MIG spans two zones, yet a reservation exists in only one zone. Can you consider full DR assured?

*Suggested answer:* No. Plan capacity in the surviving zone that will absorb failed-over VMs, and verify distribution, autoscaling, data replication, and DR drills.

**Question 9.** `count=12`, `assuredCount=10`, `inUseCount=7`. Are 5 assured VM slots definitely still free?

*Suggested answer:* No. Only 3 assured slots remain unused. Investigate the gap between `count` and `assuredCount`.

**Question 10.** Does deleting all lab VMs automatically stop reservation billing?

*Suggested answer:* No. While the reservation exists, it continues holding and billing for capacity per terms even with zero consumers.

**Question 11.** Does a successfully created reservation prove `orders-api` is healthy?

*Suggested answer:* No. It only reserves compute capacity; VM images, disks, VPC/IAM, Java apps, Cloud SQL, and health checks can still fail.

**Question 12.** Why can capacity run short during a new release even without a traffic spike?

*Suggested answer:* Rolling updates may spawn temporary surge VMs; account for `maxSurge` and per-zone capacity.

**Question 13.** Why should you avoid deleting a specifically targeted reservation while a VM is stopped if it may need to restart during an incident?

*Suggested answer:* The VM may require a matching reservation with the exact name, zone, and properties to restart; deleting capacity early can cause DR startup failure.

## 18. Pre-Production Checklist

- [ ] Confirmed the primary goal is **capacity assurance**, not just pricing discounts.
- [ ] Selected the reservation type matching when VMs are needed.
- [ ] Verified support for machine family, GPUs/Local SSDs, and workload type.
- [ ] Selected explicit zones, verified quotas, and accounted for non-reserved resources.
- [ ] Aligned machine type, CPU platform, GPUs, Local SSDs, affinity, and project/share scope.
- [ ] Chose automatic vs. specific mode and aligned MIG/instance templates.
- [ ] For shared reservations: configured Organization Policy allowlist, owner/consumers, and cost owner.
- [ ] Sized baseline, peak, DR, rolling surge, and overlap assumptions.
- [ ] Inspected `count`, `assuredCount`, `inUseCount`, and live VM consumption fields.
- [ ] Set budgets, forecasted unused capacity, and evaluated CUDs independently.
- [ ] Tested scaling, rolling updates, failover, and VM restarts under simulated scenarios.
- [ ] Documented owner, IaC/change process, review date, and teardown date.
- [ ] Avoided deleting specific reservations with consumers or commitment-bound reservations.
- [ ] Verified Monitoring, logs, IAM, VPC, disks, and application health.

## 19. Key Takeaways

- **Reservations hold capacity by zone and hardware shape**; they do not create VMs or replace app SLOs.
- **Quota is not capacity**: sufficient quota does not guarantee physical hardware in a zone.
- **Automatic** reservations can be claimed by existing matching VMs; **specific** reservations require explicit targeting.
- **Shared reservations** pool capacity across projects but require clear owner, IAM, quota, policy, and billing governance.
- **CUDs target pricing**, while reservations target provisioning assurance; combine them strictly per eligibility rules.
- **Unused capacity still bills**, while disks, networking, and other services incur separate charges.
- **`count`, `assuredCount`, and `inUseCount`** tell you what was requested, confirmed, and actively consumed.
- **HA/DR requires multi-zone design, autoscaling, health checks, and recoverable data**, not just one large reservation.
- **Reservation lifecycles are independent**: deleting VMs does not release reservations automatically.

When architecting on Compute Engine, ask: **"How many VMs, of which type, in which zone, and when? Is capacity truly assured? Who consumes it, who pays for it, and when should it be released?"** Answering these clearly turns reservations into a verifiable reliability and cost decision.

## Official Documentation References

- [About reservations — Compute Engine](https://cloud.google.com/compute/docs/instances/reservations-overview)
- [Choose a reservation type](https://cloud.google.com/compute/docs/instances/choose-reservation-type)
- [Create a single-project reservation](https://cloud.google.com/compute/docs/instances/reservations-single-project)
- [Consume reservations](https://cloud.google.com/compute/docs/instances/reservations-consume)
- [Create shared reservations](https://cloud.google.com/compute/docs/instances/reservations-shared)
- [Best practices for shared reservations](https://cloud.google.com/compute/docs/instances/best-practices-shared-reservations)
- [View reservations and reservation consumption](https://cloud.google.com/compute/docs/instances/reservations-view)
- [Modify reservations](https://cloud.google.com/compute/docs/instances/reservations-modify)
- [Monitor reservations consumption](https://cloud.google.com/compute/docs/instances/reservations-monitor)
- [About future reservation requests](https://cloud.google.com/compute/docs/instances/future-reservations-overview)
- [Troubleshoot reservation creation](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-reservation-creation)
- [Troubleshoot reservation consumption](https://cloud.google.com/compute/docs/troubleshooting/troubleshooting-reservation-consumption)
- [gcloud compute reservations create](https://cloud.google.com/sdk/gcloud/reference/compute/reservations/create)
- [Compute Engine pricing](https://cloud.google.com/compute/all-pricing)
