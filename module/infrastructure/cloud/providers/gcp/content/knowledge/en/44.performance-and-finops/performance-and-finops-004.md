# Evaluating Spot VMs, Reservations, and Usage Commitments

When optimizing Compute Engine costs on Google Cloud, a team may look at the same workload and see three very different financial options: running VMs on-demand for flexibility, using **Spot VMs** to lower unit pricing for interruptible tasks, or purchasing **Committed Use Discounts (CUDs)** for steady usage over one to three years. If concerned about failing to launch VMs during peak hours, the team may need **reservations** to hold capacity in a zone.

These mechanisms solve different problems:

- **Spot VM:** uses spare capacity at a low price, accepting the possibility of preemption at any time.
- **Reservation:** sets aside specific VM capacity in advance; typically you still pay for reserved resources even when unused.
- **Commitment/CUD:** trades a long-term financial commitment for discounted unit pricing on eligible usage; a CUD itself does not guarantee VM availability when launching.

Therefore, FinOps should not choose an option solely by discount percentage. You must evaluate workload tolerance, RTO/RPO, load schedules, capacity requirements, baseline usage, governance permissions, and actual costs via Cloud Billing.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish Spot VMs, on-demand VMs, reservations, and CUDs.
- Select workloads suitable for preemption, checkpointing, and retries.
- Design preemption detection, graceful shutdown, and task recovery.
- Understand reservation affinity, automatic consumption vs. specific reservations, and unused capacity charges.
- Distinguish resource-based CUDs from compute flexible CUDs.
- Understand how to combine commitments and reservations without confusing capacity assurance with pricing discounts.
- Calculate baseline usage, reservation utilization, commitment utilization, and hypothetical savings.
- Inspect data in Compute Engine, Cloud Billing, and Recommender to validate options.
- Plan a mix of standard VMs, Spot workers, and reserve capacity for a Java application.
- Avoid over-purchasing commitments or reservations after rightsizing.

## 1. Three Tools, Three Different Goals

| Criterion | On-demand VM | Spot VM | Reservation | Committed Use Discount |
|---|---|---|---|---|
| Goal | Flexibility and standard compute provisioning | Discount for work that tolerates preemption | Guarantee matching capacity in a zone | Discount for steady eligible usage |
| Preempted for Spot capacity? | Not via Spot mechanism | Possible at any time | Capacity is held per reservation | Not directly tied to launch rights |
| Paid when unused? | Typically no VM compute fee when stopped, though disks/IPs still incur fees | No compute-hour charge when stopped; related resources still cost | Yes, while reserved capacity exists and is unconsumed | Commitment fee/obligation applies even if usage is lower |
| Term | Pay-as-you-go | No fixed term required | Reservation lifecycle | 1 or 3 years |
| Conditions | Machine type/quota/availability | Tolerance for preemption and capacity fluctuations | Matching machine/zone/affinity and quota | Eligible SKU, location, amount, and billing scope |
| Guarantees capacity? | No | No | Holds configured capacity | No |
| Best fit | Services needing standard uptime | Batch jobs, CI workers, fault-tolerant tasks | Capacity for failover, peaks, migrations | Steady-state baseline |

A workload can use a **reservation and a CUD together** when eligible; the reservation holds capacity while the CUD provides the discounted rate. Conversely, Spot VMs do not consume standard Compute Engine reservations, and **compute flexible CUDs do not apply to Spot/preemptible VMs**.

## 2. Start from the Workload Profile, Not the Discount

Before deciding, classify your needs:

| Workload | Load Pattern | Interruption Tolerance | Capacity Requirement | Evaluation Direction |
|---|---|---|---|---|
| Java checkout API | 24/7, latency-sensitive | Very low | High | Standard + autoscale, CUD for baseline |
| Report generation batch | Scheduled, retryable | High | Medium | Spot with checkpointing |
| CI integration tests | Bursty, re-runnable | Medium/high | Medium | Spot/MIG or Cloud Build depending on platform |
| Database primary | Continuous, stateful | Low | High | Standard + HA, reservation if capacity constrained |
| Analytics worker | Many independent jobs | High | Low/medium | Spot + queue |
| DR standby | Low traffic, needs capacity on failover | Unsuitable for critical cutover | High | Reservation and recovery plan |
| GPU training | Long-running, checkpointable | Depends on job | GPUs may be scarce by zone | Compare Spot vs. supported reservations/commitments |

There is no single right choice for every environment. A 15-minute batch job may run well on Spot; a period-end batch job with a strict completion deadline may need a standard pool to guarantee progress.

### Analyzing Four Parameters

1. **Interruption tolerance:** can the job restart without losing or duplicating data?
2. **Recovery cost:** how long and how much does it cost to recover when a VM disappears?
3. **Capacity sensitivity:** must you be certain you can spin up a specific number of VMs in a zone?
4. **Demand predictability:** is there a steady baseline of compute over 1–3 years?

Spot mainly optimizes unit price, reservations mainly reduce capacity shortage risk, and CUDs optimize the price of a baseline. Without classifying first, an organization may buy reservations that sit idle or buy CUDs and later move workloads to ineligible services.

## 3. Spot VMs: Lower Cost in Exchange for Interruptibility

Spot VMs use the **spot provisioning model** on Compute Engine. Google Cloud can reclaim capacity by preempting the VM; available Spot capacity varies by zone, machine family, and time.

According to current Compute Engine documentation, Spot discounts can be **up to 91%** for many machine types/GPUs/TPUs/Local SSDs, though exact rates depend on SKU and time. Do not use the maximum figure as the default in business cases.

### Characteristics to Remember

- A Spot VM can be preempted at any time, even immediately after starting a job.
- There is no availability SLA for Spot VMs; Spot is excluded from the Compute Engine SLA.
- There is no guaranteed capacity or minimum/maximum runtime unless separate limits are configured.
- You cannot rely on live migration or automatic restart after host events as with standard VMs.
- Upon preemption, the VM is stopped or deleted according to its instance termination action.
- If stopped, persistent disks remain and continue incurring storage charges; Local SSDs and disk auto-delete settings require separate review.
- Spot discounts do not stack with compute flexible CUDs.

### Good Workloads for Spot

- Sharded processing jobs that can be re-run.
- Independent CI compiles/tests that do not require fixed workers.
- Queue-driven media encoding or data preprocessing.
- Analytics or simulations with checkpointing.
- Queue workers running idempotent jobs.
- Checkpointed GPU batch training, if the GPU/machine type is supported and capacity permits.

### Workloads That Should Not Run Entirely on Spot

- Primary databases without adequate HA/recovery.
- Checkout/payment APIs with strict uptime requirements lacking standard fallback capacity.
- Transactions holding state only in RAM.
- Uncheckpointed jobs running for hours with tight deadlines.
- Workloads constrained by licenses/hardware incompatible with Spot.
- Critical single-instance services where preemption causes immediate downtime.

## 4. Preemption Lifecycle: Key Details to Watch

According to Spot VMs documentation, Google Cloud provides a **preemption notice duration** mechanism for Spot:

- **0 seconds (default):** no separate delay before the system issues ACPI Soft Off; applications can handle preemption during the shutdown phase.
- **120 seconds (if configured):** a separate notice window before shutdown begins, giving workloads extra time to checkpoint proactively.
- After Soft Off, there is a **best-effort shutdown period of up to roughly 30 seconds** before the VM is forcibly terminated.

Never treat 30 seconds or 120 seconds as a guaranteed window to flush all data. Save checkpoints periodically and design for replay before any preemption signal arrives.

~~~text
Spot VM RUNNING
       |
       +--> May be preempted at any time
                   |
                   v
        Metadata preempted = TRUE
                   |
         [0s or 120s notice]
                   |
                   v
             ACPI Soft Off
                   |
          [Best-effort shutdown]
                   |
                   v
        TERMINATED or DELETED
                   |
                   v
       Controller/scheduler retries job
~~~

### Configuring the Termination Action

- **STOP:** the VM stops and can be restarted when capacity becomes available; attached disks may continue incurring charges.
- **DELETE:** the VM is deleted; check boot/data disk auto-delete settings and manage checkpoints externally.

Choose DELETE if workers are completely disposable and checkpoints are stored durably elsewhere. Choose STOP when you need to retain VM metadata/disks, accounting for ongoing storage costs and restart workflows.

## 5. Designing Checkpointing, Retries, and Idempotency

A Spot-friendly Java batch worker must handle:

- A worker dying mid-shard.
- A shard being replayed to another worker.
- Partial results written before losing the VM.
- Events or messages delivered more than once.
- A replacement worker running on another machine or zone.

### Sample Processing Flow

~~~text
Pub/Sub/Cloud Tasks/Batch queue
             |
             v
    Claim work item + deadline
             |
             v
      Process chunk N
             |
             v
   Write durable checkpoint
             |
             v
   Commit result idempotently
             |
             v
   Ack / mark work completed
~~~

Key points:

1. Never acknowledge a message before the business result is durably stored.
2. Use idempotency keys or unique constraints to avoid duplicate writes.
3. Split large jobs into small enough chunks so replays are inexpensive.
4. Set bounded retries and a dead-letter policy for non-recoverable errors.
5. Use Cloud Storage, a database, or storage with appropriate durability for checkpoints.
6. Emit metrics for wasted time from preemption, retry counts, and queue backlog.

### Java Graceful Shutdown Example

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class SpotWorker {
    private static final AtomicBoolean stopping = new AtomicBoolean(false);

    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            stopping.set(true);
            // Mark stop accepting new tasks; flush checkpoint within time budget.
        }));

        while (!stopping.get()) {
            // Claim a chunk, process idempotently, and save a durable checkpoint.
            // Production code needs cancellation, deadlines, and health metrics.
        }
    }
}
~~~

A shutdown hook is only a helper mechanism, not a replacement for periodic checkpointing. If the process is killed, loses network connectivity, or the host is reclaimed abruptly, the hook may not finish. Test the system by simulating stop/delete events in a test environment.

## 6. Illustrative Spot VM Creation

The following command creates a Spot worker and must be reviewed by the infrastructure team before running because it incurs charges and modifies the project.

~~~bash
gcloud compute instances create spot-worker-01 \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=e2-standard-4 \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --image-family=debian-13 \
  --image-project=debian-cloud
~~~

When an extended notice is needed, verify machine type/zone support and configure preemption notice duration according to your gcloud version and current documentation. Never write code that strictly assumes a full 120-second notice will always be available.

Check status:

~~~bash
gcloud compute instances describe spot-worker-01 \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,scheduling,disks,labels)"
~~~

Attach owner/environment/cost-center labels and configure minimal IAM. Never grant Owner permissions to a Spot worker just because the VM will be deleted after the job.

### Spot with Managed Instance Groups

MIGs help maintain a target VM count and recreate instances after preemption. However, a MIG cannot create Spot VMs if the zone runs out of Spot capacity. You may need a multi-zone strategy, autoscaling, a standard fallback pool, or queues that tolerate delayed jobs.

### GKE Spot Node Pools

On GKE, Spot capacity can run Pods that tolerate eviction. Use node affinity/taints/tolerations matching the node pool configuration, Pod disruption handling, and a clear separation between critical and optional workloads.

Do not run all control-plane dependencies or every replica of a high-uptime service on Spot nodes. Use PodDisruptionBudgets, topology spread, and standard node pools for the core tier; PDBs cannot prevent every preemption scenario.

## 7. Evaluating Spot by Total Cost per Completed Job

A low unit price does not automatically mean a lower cost per job. Calculate:

~~~text
Cost per completed job
  = compute charges
  + retry/reprocessing compute
  + checkpoint storage/network
  + scheduler/queue overhead
  + expected business impact of deadline misses
~~~

Hypothetical example, not representative of GCP pricing:

| Attribute | Standard VM | Spot Worker |
|---|---:|---:|
| Hypothetical unit rate | 1.00 USD/hour | 0.30 USD/hour |
| Compute time needed per job | 10 hours | 10 hours |
| Re-run time from preemption | 0 hours | 3 hours |
| Compute cost | 10.00 USD | 3.90 USD |
| Checkpoint/storage overhead | 0.10 USD | 0.80 USD |
| Illustrative total cost | 10.10 USD | 4.70 USD |

Spot in this example is still cheaper, but that does not guarantee the job finishes on time. If missing an SLA causes heavy business impact, the workload may require fallback to standard VMs.

### Tracking Spot Metrics

- Job completion rate and deadline attainment.
- Preemption count/rate by machine type/zone.
- Spot capacity allocation failures.
- Retry and reprocessing hours.
- Average checkpoint age.
- Queue backlog and age of oldest task.
- Cost per successful job.
- Fallback rate to standard VMs.
- Workload RTO/RPO upon preemption.

Never rely solely on historical preemption rates to guarantee future capacity. Spot availability fluctuates over time.

## 8. Reservations: Holding Compute Engine Capacity in Advance

A **Reservation** reserves capacity matching a VM configuration in a specific zone. Once created and capacity is confirmed by the system, resources are held for matching instances until the reservation is deleted or expires per configuration.

Reservations are useful when:

- Expecting a large VM scale-up during a cutover.
- Needing standby capacity for failover.
- Running GPU workloads or machine types that are scarce during peak hours.
- Preparing a migration wave that must launch VMs in a specific zone.
- Securing capacity for a scheduled event/campaign.

Reservations **do not automatically lower prices**. Google Cloud bills reserved resources under the corresponding pricing mechanism even when no VM is consuming the reservation. Eligible CUDs/discounts may apply per rules.

### A Reservation Is Not Backup or HA

A reservation guarantees the ability to launch VMs matching the reserved configuration; it does not automatically:

- Run your application for you.
- Replicate data.
- Shift traffic when an instance fails.
- Guarantee capacity for every external dependency outside the VM.
- Eliminate single-zone risk; a reservation in one zone is not multi-zone DR.

A DR plan still requires database replication, storage, networking, secrets, IAM, DNS, and drills.

## 9. Reservation Types and Consumption

A reservation can be:

- **Single-project:** capacity is reserved within one project's scope.
- **Shared reservation:** allows selected projects to consume capacity under a sharing policy.
- **Automatically consumed:** matching VMs can consume capacity automatically based on reservation affinity and consumption rules.
- **Specifically targeted:** only VMs configured to target that specific reservation can consume its capacity.

### Reservation Affinity

Reservation affinity determines whether a VM:

- Can consume any matching reservation.
- Can only use a specific reservation.
- Cannot use any reservation.

If machine type, CPU platform, GPU/Local SSD, or other properties do not match, the VM may fail to consume the held capacity. Likewise, a full reservation or insufficient quota can prevent VM creation.

**Spot VMs do not consume Compute Engine reservations**, even when machine types match. This is an important boundary when combining workload tiers.

### Example Creating a Single-Project Reservation

The following command **incurs capacity charges even with zero VMs running** and should only be executed with approval and budgeting:

~~~bash
gcloud compute reservations create batch-capacity \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=n2-standard-4 \
  --vm-count=5
~~~

Inspect capacity:

~~~bash
gcloud compute reservations list \
  --project=PROJECT_ID \
  --format="table(name,zone,specificReservation.count,specificReservation.inUseCount)"
~~~

Displayed fields depend on API/CLI version; if the projection returns empty fields, use `--format=yaml` to inspect the response structure.

~~~bash
gcloud compute reservations describe batch-capacity \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format=yaml
~~~

Monitor actual consuming VMs, idle slots, and lifetime. If a reservation supports a migration or short-term peak, schedule its review/deletion date in advance.

## 10. Cost of Unused Reservations

Suppose a reservation holds space for 10 identical VMs in zone A, but only 6 VMs are running and consuming that reservation.

~~~text
Reserved capacity:      10 VMs
Consumed:                6 VMs
Unconsumed:              4 VMs
Reservation utilization: 60%
~~~

Google Cloud bills for reserved capacity throughout the reservation's existence. Thus, the 4 idle VM slots represent opportunity/held-capacity cost. A VM actively consuming a reservation **is not double-billed for compute on the same reserved resources**.

### Questions to Audit

- What event or timeframe does the reservation exist to protect?
- How many VMs are actually consuming it?
- Do VMs have matching machine types and affinity settings?
- Is any project unexpectedly consuming a shared reservation?
- Are unused capacity charges covered in the budget?
- When should the reservation be resized or deleted?
- Is it attached to a commitment that restricts edits or deletion?

An oversized reservation can raise the bill even when no new production VMs exist. Separate **capacity assurance** from **cost savings** in FinOps reporting.

## 11. What Are Committed Use Discounts?

**Committed Use Discounts (CUDs)** provide discounted pricing in exchange for committing to a minimum amount of resource usage or spend over a **1-year or 3-year** term.

Commitments fit workloads with an established, steady baseline. If usage falls below the committed level, the financial obligation does not disappear. If usage exceeds the commitment, overage is billed at applicable rates/discounts depending on SKU and billing policy.

Two common categories:

| CUD Type | Commitment Unit | Best Fit |
|---|---|---|
| Resource-based CUD | Specific amount of vCPU, memory, or eligible resources per rules | Steady Compute Engine baseline by region/machine family |
| Compute flexible CUD | Minimum hourly spend on eligible SKUs | Workloads that may change machines/services while keeping steady eligible spend |

Discount percentages vary by SKU, machine family, term, and Cloud Billing model; never assume one universal rate across all resources.

### Resource-Based Commitments

Characteristics:

- Commits to a set quantity of Compute Engine resources for a 1- or 3-year term.
- Tied to the purchasing project and region; sharing across projects depends on CUD sharing configuration.
- Covers eligible resources such as vCPU, memory, GPUs, Local SSDs, sole-tenant nodes, or certain licenses depending on commitment type.
- Region and resource type can constrain where usage receives coverage.
- Can be combined with reservations, though the commitment itself does not hold capacity.

For Cloud Billing accounts created after certain newer configuration milestones, default CUD sharing rules may differ from older accounts. Check Billing settings and current documentation instead of assuming all projects share discounts automatically.

### Compute Flexible CUDs

Characteristics:

- Purchased at the Cloud Billing account level.
- Commits to a minimum hourly spend over 1 or 3 years.
- Can apply across eligible Compute Engine/GKE/Cloud Run SKUs per documentation.
- Commitment fees are billed each period even if eligible usage falls below the committed amount.
- **Does not apply to Spot/preemptible VMs**.
- Different machine families and resources carry different discount rates and term conditions.

Some accounts may operate under different CUD billing models during transitions to newer consumption/discount mechanisms. When modeling options, use the actual pricing and model active on that Cloud Billing account.

## 12. CUDs Do Not Replace Reservations

Two commonly confused options:

**Buying a CUD without a reservation:** gives discounted pricing for eligible usage, but does not reserve a specific count of VMs in a zone. During capacity shortages, having a financial commitment does not guarantee VMs can launch on time.

**Creating a reservation without a CUD:** holds capacity ready, yet bills corresponding charges for its duration; reserving alone does not grant an extra discount.

**Combining a CUD and a reservation:** when aligned, capacity is held and usage/reserved resources can receive CUD pricing per eligibility rules. Some resource-based commitments allow attaching reservations; certain specialized resources may require attached reservations.

### Coordination Example

An application has 8 baseline VMs running 24/7, observed over several months, and requires failover capacity in a zone. The team can:

1. Rightsize the baseline to 8 VMs based on load and SLOs.
2. Evaluate a resource-based CUD for a portion of steady usage, avoiding buying up to 100% of peak.
3. Create a reservation holding only the capacity that truly needs assurance.
4. Configure VMs/MIGs to consume the reservation appropriately.
5. Track CUD coverage/utilization and reservation consumption separately.

Never buy new commitments based on un-rightsized VM configurations. Reducing usage after purchase can leave commitments underutilized.

## 13. Formulas for Evaluating Commitment Utilization

Teams should track:

~~~text
Commitment utilization
  = covered eligible usage
    / purchased commitment amount

Reservation utilization
  = consumed capacity units
    / total reserved capacity units
~~~

These two ratios measure different problems. Low commitment utilization means paying for commitments not fully used. Low reservation utilization means holding more capacity than actually needed.

### Hypothetical Example

Suppose eligible usage holds steady around 100 on-demand cost units per hour, with daily fluctuations.

- Buying a flexible commitment equivalent to 60 units/hour can capture the steady baseline.
- Buying 120 units/hour risks leaving unused spend during normal hours.
- Only purchase commitments after factoring in growth, planned decommissioning, rightsizing, and workload shifts.

This example is illustrative only and not a conversion guide between commitment fee dollars and eligible usage on a specific Billing account. Use Cloud Billing reports and pricing/commitment calculators for exact figures.

### When to Avoid Long-Term Commitments

- Upcoming major machine family or architecture changes.
- Plans to migrate most workloads to ineligible services/SKUs.
- Unstable baseline or projects scheduled to shut down.
- Uncertain region, volume, or runtime duration.
- Finance has not approved a 1–3 year binding obligation.

Never buy a CUD solely because of a large headline discount. Savings only materialize when eligible usage actually exists throughout the term.

## 14. Inspecting Current State Before Purchasing

### View Reservations

~~~bash
gcloud compute reservations list \
  --project=PROJECT_ID \
  --format=yaml
~~~

For a specific reservation:

~~~bash
gcloud compute reservations describe RESERVATION_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format=yaml
~~~

Inspect reserved capacity, consumption, sharing/affinity, and reserved properties.

### View Resource-Based Commitments

~~~bash
gcloud compute commitments list \
  --project=PROJECT_ID \
  --regions=REGION
~~~

Check term, activation status, region, resource type, amount, and attached reservations if any. Spend-based flexible CUDs may be managed at the Cloud Billing account level and viewed differently; never rely solely on regional Compute Engine commitment lists to assess the organization's entire CUD portfolio.

### View Spot VM Configuration

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,status,machineType,scheduling,labels)"
~~~

Verify provisioning model, termination action, and related settings.

### Cross-Check Billing

Cloud Billing reports and billing exports to BigQuery help verify:

- Eligible spend by SKU, machine family, and project.
- Actual usage hours and stability.
- CUD fees/discounts/credits under the active billing model.
- Reservation unused capacity charges.
- Spot costs, standard fallback costs, and storage.
- Net savings after rightsizing and migrations.

Every commitment purchase decision needs an approved financial plan; never run create/purchase commands during an analysis-only step.

## 15. Strategy Selection Matrix

| Need | Spot VM | Reservation | CUD |
|---|---|---|---|
| 2-hour retryable batch job | Very suitable | Usually unnecessary | Unnecessary if usage is erratic |
| 24/7 production service | Auxiliary components only | May be needed if capacity is critical | Sound for eligible steady baseline |
| Launch needing 100 extra VMs for one day | Spot if shortfalls are acceptable | Consider short-term reservation | Usually not worth a 1–3 year commitment |
| DR needing 20 VMs to boot immediately | Unsuitable for critical recovery | Useful when capacity must be assured | Only discounts if usage/conditions align |
| Pull-request CI workers | Suitable with retries | Not strictly needed | Only for steady baseline portion |
| Checkpointed GPU training | Suitable if Spot capacity exists | Consider when GPUs must be assured | Consider for predictable GPU usage and eligible SKUs |
| Workload leaving Compute Engine soon | Fine for temporary batch | Only with concrete migration plans | Avoid excessive long-term commitments |
| Unpredictable traffic spikes | Can handle opportunistic burst | Reservation if assurance is required | Commit only to baseline; keep bursts elastic |

Do not confuse "suitable" with guaranteed. Spot availability and reservation capacity can depend on machine type, zone, and timing; certain reservation types carry restrictions on GPUs, machine series, or integrated services.

## 16. Combined Architecture Example for a Java Workload

An e-commerce system consists of:

- Java/Spring Checkout API on GKE/Compute Engine.
- Order database on a managed database service.
- Analytics and reporting workers driven by Pub/Sub.
- CI runners executing integration tests.
- Standby VMs for recovery.

### Capacity Tiering

~~~text
                     HTTP users
                         |
                         v
            Production Java API baseline
            Standard VMs / GKE standard nodes
            CUD for eligible stable usage
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Database service         Pub/Sub queue
      HA + backups                  |
                                  v
                           Spot workers
                           Checkpoint + retry
                                  |
                             fallback pool
                           Standard/on-demand

 DR failover capacity: reservations if capacity must be held
~~~

### Decision by Component

| Component | Decision Direction | Conditions |
|---|---|---|
| Checkout API | Standard capacity + baseline CUD | Adequate telemetry/SLOs and steady usage |
| Analytics worker | Spot + idempotent queue | Checkpointing and retries implemented |
| Integration test workers | Spot or ephemeral runners | Tests can restart without corrupting state |
| Failover VMs | Reservation if capacity availability is critical | Backed by DR drills, not just paper capacity |
| Additional peak traffic | On-demand autoscaling | Never buy commitments for rare peaks |

### Sample Cost Review

Before purchasing any commitment:

1. Run rightsizing across a 90-day baseline or representative cycle.
2. Identify the lowest forecastable usage over the coming year.
3. Subtract resources pending decommission, workloads moving to managed services, and portions movable to Spot.
4. Estimate the remaining portion eligible for each CUD type.
5. Compare 1-year, 3-year, and on-demand across multiple growth scenarios.
6. For reservations, separately price unused capacity during expected idle periods.
7. Verify compliance/DR requirements and ability to maintain capacity in the zone.
8. Obtain sign-off from FinOps, application owners, and operations.

## 17. Low Reservation Utilization: Causes and Investigation

If a reservation holds 20 VMs but only 5 VMs use it, possible causes include:

- Delayed migration/cutover plans.
- VMs not matching machine type, min CPU platform, or GPU/Local SSD.
- Misconfigured reservation affinity.
- VMs running in a different zone.
- Shared reservation not shared with the right consumer project.
- Insufficient quota or degraded reservation.
- Owners moved workloads to another region or architecture.

Investigation steps:

1. Inspect reservation `assuredCount`, `count`, and `inUseCount`.
2. Check consumer instance properties and affinity settings.
3. Verify topology and desired capacity.
4. Cross-check migration/campaign schedules.
5. If capacity is no longer needed, evaluate resizing/deleting per reservation rules.
6. If attached to a commitment, verify restrictions before making changes.

Never delete a reservation attached to a specific commitment without checking policy first. Some attached reservations restrict modifications for the entire commitment term.

## 18. Fluctuating Spot Capacity: Designing Fallbacks

A service with a 10-worker Spot pool might temporarily only be able to launch 4 workers. If the queue grows, options include:

- Accepting slower processing within SLA bounds.
- Expanding Spot capacity across other supported zones/machine families.
- Shifting part of the queue to a standard fallback pool.
- Deferring lower-priority tasks.
- Increasing checkpoint frequency to reduce waste when preemption rates spike.

### Priority Separation

| Work Type | Priority | Capacity |
|---|---|---|
| Confirm order / payment | Critical | Standard capacity |
| Generate invoice | High | Standard or hybrid based on deadline |
| Send routine notifications | Medium | Queue + Spot/fallback |
| Build recommendation dataset | Low | Spot |
| Nightly integration tests | Low/Medium | Spot with retries |

Controllers should monitor queue age and deadlines rather than blindly increasing instance counts. When using Standard fallback, configure budget guardrails and alerts if spend exceeds expectations.

## 19. Governance and IAM

Purchasing commitments or creating reservations can create major financial obligations. Separate roles clearly:

- **FinOps analyst:** reads billing, usage, and recommendations.
- **Platform engineer:** evaluates machine types, reservation consumption, and workload topology.
- **App owner:** confirms SLOs, deadlines, and preemption tolerance.
- **Security:** reviews service accounts, networking, and data protection.
- **Financial approver:** approves terms/commitment fees and reservation charges.
- **Operations:** executes changes and rollbacks.

Do not grant commitment-purchasing permissions to every developer. Enforce least-privilege IAM, review/audit trails, and documented change requests.

### Labels and Metadata

Attach labels or tags such as:

- `owner`, `application`, `environment`.
- `cost-center` and `business-unit`.
- `lifecycle`/`retention`.
- `capacity-purpose`: baseline, spot, DR, migration.
- `commitment-owner` or `reservation-review-date` where aligned with conventions.

Avoid putting sensitive data or personal information in label values. Never treat labels as the sole source of truth for financial obligations; tie them to billing contracts and resource inventories.

## 20. Pre-Purchase Approval Workflow

A proposal should contain:

1. Workload inventory and owner.
2. 30/60/90-day baseline or longer cycle depending on workload.
3. Forecast for growth, load reductions, and planned migrations.
4. Region/machine series/SKU/usage eligibility.
5. Discounts/fees/terms under the active Cloud Billing account.
6. Reservation scope, VM count, utilization target, and end date.
7. Comparison across spot, on-demand, CUD, and reservation + CUD.
8. Downside scenarios: frequent preemption, falling demand, zone unavailability.
9. Ancillary costs: storage, egress, retries, operations, DR.
10. Owner, financial approver, change window, and audit trail.

### Do Not Skip Break-Even Analysis

For example, a commitment may be cheaper than on-demand at full utilization while still charging its commitment fee when workloads stop. Calculate the break-even curve by utilization and specific contract type, including scenarios where usage shifts to ineligible SKUs.

Never compare only the headline "discount rate" of Spot vs. CUD. Spot carries preemption risk; CUD creates long-term financial obligations; reservations carry unused capacity charges. The real problem is minimizing total cost to achieve operational goals at an acceptable level of risk.

## 21. Common Pitfalls

| Pitfall | Consequence | Remedy |
|---|---|---|
| Running a DB primary on a single Spot VM | Loss of availability upon preemption | Standard/HA, backups, and recovery |
| Believing Spot can hold capacity | Instances may fail to launch | Fallback or reservations for standard capacity |
| Keeping batch state only in RAM | Lost progress when VM stops | Durable checkpointing |
| Assuming shutdown always gives 30/120 seconds | Jobs lose data or fail to flush | Periodic checkpointing and idempotency |
| Buying a CUD thinking capacity is reserved | Still face VM stockouts at peak | Use reservations when capacity assurance is needed |
| Creating a reservation thinking you got a discount | Paying for unused reserved resources | Track utilization and evaluate CUDs |
| Running Spot and assuming flexible CUD applies | Miscalculated savings | Exclude Spot from eligible flexible usage |
| Buying commitments before rightsizing | Baseline shrinks leading to underutilization | Rightsize first, commit second |
| Using maximum discount rate as default pricing | Overly optimistic forecasts | Price by actual SKU/region/term |
| Skipping reservation affinity checks | VMs fail to consume held slots | Verify VM/reservation matching |
| Forgetting shared reservation billing | Wrong project cost attribution | Review owner/consumer projects and CUD sharing |
| Counting reservation and VM as two separate compute charges | Double-counted costs | Reconcile billing model and credits |
| Setting no reservation review date | Paying for unused capacity indefinitely | Assign owners, reviews, and deletion policies |
| Never testing Spot preemption | Retries/rollback fail in production | Chaos/pilot tests in staging |
| Mixing standard and Spot SLOs | Misjudged service reliability | Separate SLOs for user journeys and worker queues |

## 22. GCP Implementation Checklist

### Spot VMs

- [ ] Workload tolerates VM preemption at any time.
- [ ] Idempotency, retries, and durable checkpointing are implemented.
- [ ] Deadline limits and standard fallback policies exist.
- [ ] STOP/DELETE action is configured with disk impacts understood.
- [ ] 0s/120s notice and best-effort shutdown behavior are accounted for.
- [ ] Interruption rate and cost per completed job are benchmarked.
- [ ] Critical-SLA services do not rely on Spot without fallback.
- [ ] Supported machine series, GPUs, and zones are verified.
- [ ] Metrics exist for preemptions, backlog, retries, cost, and errors.

### Reservations

- [ ] Clear capacity requirement and owner are defined.
- [ ] Zone, machine type, GPU/Local SSD, and quotas are valid.
- [ ] Clear whether reservation is automatic or specifically targeted.
- [ ] VMs are configured with matching affinity.
- [ ] Reservation utilization targets and end/review dates exist.
- [ ] Unconsumed reserved capacity charges are budgeted.
- [ ] Shared reservation billing is verified if used.
- [ ] Attached commitment restrictions are checked before editing/deleting.
- [ ] Spot VMs are not expected to consume reservations.

### CUDs and FinOps

- [ ] Rightsizing completed before purchasing commitments.
- [ ] Usage baseline and growth/migration forecasts exist.
- [ ] Resource-based vs. flexible CUDs are clearly distinguished.
- [ ] Region, account, project sharing, and SKU eligibility are verified.
- [ ] 1-year/3-year terms and commitment fees are reconciled.
- [ ] Commitments are not treated as capacity guarantees.
- [ ] Flexible CUDs are not applied to Spot workloads.
- [ ] Cost scenarios, break-even, and sensitivity analyses are documented.
- [ ] Financial approvals, audit trails, and coverage/utilization monitoring exist.
- [ ] Realized savings are measured via Cloud Billing post-implementation.

## Conclusion

Spot VMs, Compute Engine reservations, and Committed Use Discounts address three distinct problems: **cost reduction for interruptible workloads**, **capacity assurance**, and **discounted pricing for a stable baseline**. Spot fits batch jobs, CI, and checkpointed workers; reservations help with migrations, capacity planning, and DR but cost money even when idle; CUDs can deliver substantial discounts yet create 1–3 year obligations without holding capacity. A sound FinOps strategy starts from utilization data and SLOs, performs rightsizing, and then selects the right lever for each workload tier. Always measure both **reliability and actual cost** to avoid paper discounts that increase operational risk.

## References

- [Compute Engine: Spot VMs overview](https://docs.cloud.google.com/compute/docs/instances/spot)
- [Compute Engine: Create and use Spot VMs](https://docs.cloud.google.com/compute/docs/instances/create-use-spot)
- [Compute Engine: Spot VM best practices](https://docs.cloud.google.com/compute/docs/instances/spot-best-practices)
- [Compute Engine: Reservations overview](https://docs.cloud.google.com/compute/docs/instances/reservations-overview)
- [Compute Engine: Create single-project reservation](https://docs.cloud.google.com/compute/docs/instances/reservations-single-project)
- [Compute Engine: Consume reservations](https://docs.cloud.google.com/compute/docs/instances/reservations-consume)
- [Compute Engine: View reservations](https://docs.cloud.google.com/compute/docs/instances/reservations-view)
- [Compute Engine: Monitor reservation consumption](https://docs.cloud.google.com/compute/docs/instances/reservations-monitor)
- [Compute Engine: Committed use discounts](https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview)
- [Compute Engine: Combine reservations and commitments](https://docs.cloud.google.com/compute/docs/instances/reservations-with-commitments)
- [Compute Engine: View resource-based commitments](https://docs.cloud.google.com/compute/docs/committed-use-discounts/view-resource-based-commitments)
- [Cloud Billing: Cost optimization](https://docs.cloud.google.com/billing/docs/how-to/cost-management)
- [Cloud Billing: Export data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
