# Capacity allocation with capacity reservations

In Azure, creating a virtual machine (VM) does not depend solely on permissions and remaining vCPUs in a quota. At deployment time, the platform must also have **available physical compute capacity** for the exact machine type, region, and availability zone required by the application. When many systems scale simultaneously in the same area, a request to create or restart a VM from a deallocated state may not succeed immediately, even if the subscription is within quota.

For critical workloads, **Azure On-demand Capacity Reservation** helps organizations reserve compute capacity for supported VM configurations. Azure sets aside this capacity for eligible workloads even during periods when no VMs are actively consuming it. In return, reserved yet unused capacity still incurs charges.

This lesson belongs to the **Elastic Compute and Batch Processing** chapter, along our journey exploring the Microsoft Azure ecosystem from subscriptions, resource groups, Microsoft Entra ID, and virtual networking to compute, storage, data, monitoring, security, and cost control. The focus is deciding **when to hold capacity in advance**, **how much to reserve**, **how to allocate it to VMs/VM Scale Sets**, and **how to measure utilization and cost**.

## Learning objectives

After this lesson, you will be able to:

1. Explain why quota, compute demand, and Azure's actual capacity are three distinct concerns.
2. Distinguish **On-demand Capacity Reservation**, **Azure Reserved VM Instances**, **Savings Plans**, and **Spot VMs**.
3. Identify a **Capacity Reservation Group** and reservations by **VM size**, **region**, **availability zone**, and instance count.
4. Design reserved capacity matching baseline demand, peak hours, and recovery plans.
5. Describe how to create a capacity reservation, associate VMs/VM Scale Sets, and verify consumed slots.
6. Understand charges for unused capacity, quota limits, allocation status, and risks when modifying reservations.
7. Troubleshoot failed reservation creation, VM SKU/zone mismatches, and scale-outs exceeding reserved capacity.
8. Establish processes for monitoring, budgeting, tagging, and adjusting reservations as demand evolves.

## 1. The problem: having quota does not mean having VM capacity

Suppose an e-commerce application uses **Standard_D4s_v5** VMs in an Azure region. Operations need to start six machines in a specific availability zone when a promotional campaign begins. The subscription has 24 vCPUs of quota available and valid VM/NSG configs, yet the deployment request can still hit an allocation failure if insufficient compatible hosts are available in that exact zone at that moment.

Separate three concepts:

| Concept | Question answered | What is not guaranteed |
|---|---|---|
| **Quota** | How many resources/vCPUs is the subscription allowed to request under applied limits? | Physical hosts actually available at the moment needed |
| **On-demand allocation** | Can Azure immediately provision a specific VM at create/start time? | Ability to reallocate the same configuration later once capacity is released |
| **Capacity reservation** | Has Azure allocated dedicated capacity for a count of VMs matching a supported configuration? | Capacity for any other SKU/zone or counts exceeding the reservation |

**Quota is an administrative limit, not a capacity commitment.** Raising quota is often required when expected VM counts grow, yet raising quota alone does not hold hosts for your workload. Conversely, creating a reservation checks quota and can fail if capacity is unavailable at reservation time.

### Why must stopping a VM be considered carefully?

In Azure, **stopped (allocated)** and **stopped (deallocated)** are not the same. A **deallocated** VM typically releases compute resources so standard VM compute billing stops, yet restarting it requires Azure to allocate capacity again.

If a workload needs guaranteed room for a later startup, an appropriate **capacity reservation** holds capacity in advance even while VMs are deallocated or not yet created. However, **reservations still incur charges when no VM uses them**. Thus, deallocating a VM no longer means all related compute costs disappear.

## 2. What is On-demand Capacity Reservation?

**On-demand Capacity Reservation (ODCR)** is an Azure Compute feature that reserves VM capacity for supported configurations and scopes. Once a reservation is successfully allocated, a matching number of slots are held for eligible VMs until the organization modifies or deletes the reservation under product terms.

Each slot can be understood as capacity to serve **one VM of the exact specified size**, not an abstract pool of vCPUs interchangeable across any machine type.

Example:

~~~text
Region: Southeast Asia
Availability Zone: 1
VM size: Standard_D4s_v5
Reserved capacity: 4 instances

Status at time A:
  VMs consuming reservation: 3
  Unused reservation slots : 1

Status at time B:
  VMs consuming reservation: 4
  Unused reservation slots : 0
~~~

In this example, slots reserved for **Standard_D4s_v5** cannot automatically be used by **Standard_E4s_v5**, a different VM size, or a different availability zone. Exact constraints must be verified against reservation types and supported SKU features.

### What does "On-demand" mean?

"On-demand" refers to the organization **requesting reservations as needed**, rather than committing upfront to a one-year or three-year discount contract. It does **not** mean capacity is always guaranteed to be available to reserve. Azure must still locate matching capacity when creating/increasing the reservation.

Once successfully reserved, capacity is held until modified or released under corresponding terms. You still **pay for an active reservation** per the service's billing rules, even when no VM occupies the slots.

## 3. Resource structure: Group, Reservation, and VM

Azure manages reserved capacity through management resources:

- **Capacity Reservation Group (CRG):** logical container holding one or more capacity reservations.
- **Capacity Reservation:** specific reservation for a **VM size**, **quantity**, and corresponding **region/availability zone**.
- **Virtual Machine/Virtual Machine Scale Set:** workloads that can be associated to consume capacity in the group when configurations match requirements.

Diagram:

~~~text
Azure subscription
  |
  +-- Resource group: rg-compute-capacity
        |
        +-- Capacity Reservation Group: crg-sales-prod
              |
              +-- Reservation: cr-d4s-zone1
              |     VM size: Standard_D4s_v5
              |     Zone: 1
              |     Quantity: 4
              |     Used: 3, Unused: 1
              |
              +-- Reservation: cr-d4s-zone2
                    VM size: Standard_D4s_v5
                    Zone: 2
                    Quantity: 3
                    Used: 2, Unused: 1

VM or VMSS associated with the same CRG
  -> consumes only reservations matching size/zone and supported conditions
~~~

**A CRG does not create VMs by itself.** When a group exists without allocated reservations inside it, the group represents zero available VM capacity. When a reservation is created without associated VMs, capacity may sit **idle while still incurring charges**.

### Region and availability zone

- **Region** is the Azure region deploying capacity, e.g., **southeastasia**. A reservation in one region does not guarantee allocation in another.
- **Availability zone (AZ)** is an isolated fault domain within an AZ-supported region. A VM configured for a specific zone must match capacity in that zone.
- **VM size/SKU** specifies the compute resource type. Do not assume switching from D-series to E-series or between sizes retains eligibility for old slots.
- **Quantity (capacity)** is the count of VMs of that exact configuration reserved, not free-form vCPUs shared across arbitrary VMs.

Support for zones, SKUs, families, VM features, cross-resource or cross-subscription sharing, and Azure regions can vary. Verify current support matrices, quotas, and features before designing.

### How is a reservation attached to a VM?

In the standard model, the VM references the **Capacity Reservation Group** in its VM resource configuration. Azure matches the VM's size/zone against the corresponding reservation in the group.

Simply placing a VM in the **same resource group** or **same VNet** as a CRG does **not** make the VM automatically consume the reservation. Explicitly select the group or configure the association as supported by Azure, then **verify the association and consumed slot count**.

## 4. Distinguishing capacity reservations from financial/compute options

The word "reservation" makes it easy to confuse reserving **capacity** with reserving a **discount**.

| Service or mechanism | Primary goal | Reserves matching physical capacity? | Cost characteristics |
|---|---|---|---|
| **On-demand Capacity Reservation** | Reduce risk of lacking capacity when needing exact VM configs | Yes, once reservation allocates successfully | Pay for reserved capacity, including unused portion |
| **Azure Reserved VM Instances** | Reduce eligible compute costs via term commitment | Does not guarantee capacity at deployment time | Commitment-based discount mechanism per applicable terms |
| **Azure Savings Plan for Compute** | Reduce eligible compute costs via hourly spend commitment | Does not hold capacity | Discount based on spend commitment terms |
| **Spot VM** | Utilize spare capacity at lower prices under Spot terms | No; subject to eviction | Lower cost with eviction risk |
| **Standard on-demand VM** | Allocate when needed and pay per usage | Holds no slot after deallocation | Billed by VM runtime/type and attached resources |

An enterprise may hold both a **Reserved VM Instance** to optimize pricing and a **Capacity Reservation** to mitigate allocation risk. These are independent decisions. Whether a discount applies to a VM or reserved capacity depends on specific billing rules; **never infer that buying an RI automatically reserves capacity**, nor that ODCR automatically grants RI discounts.

### Do not confuse ODCR with VM Scale Sets

**Azure Virtual Machine Scale Sets (VMSS)** deploy and scale multiple VMs, whereas capacity reservations merely hold matching capacity in advance. An autoscale rule may request scaling from 4 to 8 VMs, but if the capacity reservation quantity is smaller than demand, scaling beyond the reserved amount **is not guaranteed by ODCR**.

Compatibility for associating VMSS with a CRG and actual allocation behavior must be checked per **orchestration mode, SKU, region, and support conditions**. ODCR does not set min/max instance bounds or trigger scale-out on its own.

### Do not confuse ODCR with Availability Zones or Availability Sets

Availability Zones and distribution options manage **failure domains**. Capacity reservations ensure **VM capacity is available for allocation**. A reservation in zone 1 is not a backup for zone 2; surviving a zone outage also requires distributing VMs, data, networking, load balancing, and recovery plans appropriately.

## 5. When should you use a capacity reservation?

**Suitable** when workloads have strict requirements around creating or restarting VMs in specific situations:

1. **Peak-hour critical services:** a payment system needs a guaranteed minimum number of instances available in each zone.
2. **Scheduled workload startups:** reporting or batch machines may be deallocated off-hours yet must restart with the exact size/zone before a deadline.
3. **Disaster recovery:** an organization wants capacity held at a standby location while accepting the cost of unused capacity.
4. **Scaling a capacity-sensitive service tier:** reserving the baseline of hard-to-substitute VM sizes or burst-sensitive tiers.
5. **Planned large migrations:** ensuring room before moving VMs into a region/zone or changing architecture, within supported features.

**Usually unnecessary** when workloads are small, flexible across VM sizes, easily moved across regions/zones, lack tight startup deadlines, or when idle reservation costs outweigh the business impact of an allocation failure.

### What demand should be reserved?

Distinguish:

- **Baseline:** minimum capacity that must exist reliably per system requirements.
- **Burst:** extra demand during peak waves; may not require reservation if allocation risk is acceptable.
- **DR headroom:** standby capacity for recovery events; may sit mostly unused during normal operations while still incurring fees.

Do not take the highest VM count ever observed and blindly reserve all of it year-round. The goal is matching reservation levels to **business risk** and **budget**.

## 6. Sizing the number of slots to reserve

Suppose an API uses **Standard_D4s_v5** VMs distributed across two availability zones. Measured demand:

| Time period | Zone 1 | Zone 2 | Total |
|---|---:|---:|---:|
| Nighttime | 2 VMs | 2 VMs | 4 |
| Business hours | 3 VMs | 3 VMs | 6 |
| Peak | 5 VMs | 4 VMs | 9 |

The application team establishes an SLO requiring **at least three VMs per zone** in case VMs must be replaced or restarted. A plan might look like:

~~~text
Reservation Standard_D4s_v5:
  Zone 1: 3 slots
  Zone 2: 3 slots
  Total : 6 slots

Night:
  Zone 1: 2 VMs used, 1 idle slot
  Zone 2: 2 VMs used, 1 idle slot

Business hours:
  Zone 1: 3 VMs used, 0 idle slots
  Zone 2: 3 VMs used, 0 idle slots

Peak:
  Total needed 9 VMs; only 6 slots fall within reserved scope.
  Remaining capacity must be handled by an appropriate scaling strategy.
~~~

**Note:** This is a planning example, not a guarantee that the three VMs beyond the reservation will certainly allocate. When VMSS or deployment workflows request more than reserved capacity, verify how the service handles allocation, quotas, and changing groups/sizes per architecture.

### Planning formulas

For each configuration tuple **(region, zone, VM size)**, define:

~~~text
reservedSlots = baselineCapacity + approvedSafetyBuffer

unusedSlotsAtTimeT = max(0, reservedSlots - associatedRunningVMsAtTimeT)

coverageAtTimeT = min(1, reservedSlots / requiredVMsAtTimeT)
~~~

These are **self-computed governance metrics**, not official billing formulas or API properties. With 3 slots and 2 consuming VMs, unused slots equal 1. If demand rises to 5 VMs, reserved coverage ratio is only 3/5, while allocating the extra 2 VMs depends on other conditions.

Do not lump slots across availability zones and treat them as interchangeable. Report **per zone and size**, because the system needs capacity in the exact placement location.

### Quotas and VM sizes

A reservation for **4 VMs × 4 vCPUs** ties into compute capacity needs and applicable VM-type/region quota limits. Before planning, check **total vCPU quota** and **VM family quota** where applicable; Azure can reject creating/increasing capacity if limits or current host capacity fall short.

**Getting a quota increase does not mean a reservation will succeed.** If capacity is urgent, prepare fallback options for alternate zones, equivalent VM sizes where the app permits, and escalate through valid support channels.

## 7. Cost: unused capacity is still billed

Key economic rule: **Capacity reservation is not a free hold**.

Typically, Azure charges compute costs corresponding to reserved slots under ODCR pricing rules. When an eligible VM uses a slot, related compute billing is reconciled between the VM and reservation billing mechanisms so you are not confused into thinking you pay **double compute** for an occupied slot. Items like disks, networking, and ancillary services can still carry separate charges.

### Quantitative example

Illustrative assumptions:

- **Assumed** compute rate for an eligible VM: **0.25 USD/hour**.
- Reservation: **4 slots**.
- VMs consuming slots: **3 VMs**.
- Unused slots: **1 slot**.

Visualizing **total compute cost of held capacity**:

~~~text
3 used slots x 0.25 USD/hour   = 0.75 USD/hour
1 unused slot x 0.25 USD/hour  = 0.25 USD/hour
Illustrative total             = 1.00 USD/hour
~~~

If 4 slots remain reserved with zero VMs running, idle capacity still incurs its corresponding charge. To reduce charges, reduce or delete the reservation per supported rules rather than merely stopping VMs.

**0.25 USD/hour is strictly a learning assumption**, not Azure's rate in Southeast Asia or for Standard_D4s_v5. RI/Savings Plan application, billing currency, SKU/zone/region pricing rules, and accompanying resources must be verified against current pricing.

### What else costs money?

- OS/data disks, snapshots, backups, and storage capacity.
- Public IPs, NAT Gateways, Load Balancers/Application Gateways, and network traffic.
- Azure Monitor/Log Analytics, agents, and security services.
- Software licenses and licensed image billing mechanisms.
- Additional VMs running beyond reserved slots when allocated successfully.
- Excess reserved capacity in unused sizes or zones.

Apply **tags** to groups and reservations, such as **application**, **environment**, **costCenter**, and **owner**. Track **Azure Cost Management**, budgets, idle reservation spend, and actual demand reports to drive adjustments.

## 8. Deployment planning workflow

### Step 1: inventory workloads

Record per workload:

| Information | Example | Why needed |
|---|---|---|
| Workload name | sales-api | Identifies demand and owner |
| Subscription | sub-sales-prod | Correct permission/quota/billing scope |
| Region | southeastasia | Reservation and VMs must match region |
| Zone | 1 and 2 | Capacity needs split by zone |
| VM size | Standard_D4s_v5 | Slots are bound to specific sizes |
| Baseline | 3 VMs/zone | Capacity level to hold |
| Burst | 2 additional VMs | Needs a plan beyond baseline |
| Schedule | 24/7 or scheduled | Estimates idle hours |
| Recovery objective | E.g., recreate within approved RTO | Determines reservation criticality |

If a batch VM only runs three days a month, weigh the cost of holding capacity all month against the business cost of failing to start on time.

### Step 2: check support and quotas

Verify VM size, region, zone, subscription, VM type rules, and feature versions. Some VM types, allocation modes, or feature combinations may not support ODCR. Never assume Spot, Dedicated Hosts, all VMSS modes, or specialized VMs work identically.

If quota is insufficient, request a quota increase through proper channels. If a reservation configuration is unsupported, adjust the architecture instead of forcing group assignment.

### Step 3: analyze the cost of the reserve level

Calculate per size/zone:

- Number of slots needed.
- Expected active duration of the reservation.
- Hours slots will be **used** vs. **idle**.
- Projected compute cost and ancillary services.
- Opportunity cost of not reserving and failing to deploy during peak.

Approved plans should have sign-off from both the workload owner and budget owner. **Creating a reservation can incur charges even before deploying VMs**, so never create test reservations in production without approval.

### Step 4: create and verify the reservation

In the Azure portal or supported IaC tools, create the CRG, then add reservations for calculated VM sizes/zones/quantities. Wait for successful provisioning state before treating slots as ready.

If creation fails due to capacity shortage, retrying the exact same template repeatedly does not prove the next attempt will succeed. Check regional conditions, quotas, sizes, zones, and fallback options.

### Step 5: associate VMs or VMSS

Configure eligible VMs/VMSS to reference the CRG per supported features. Cross-check size, location, zone, subscription/resource ownership, and other hardware/deployment conditions.

For **existing VMs**, changing the association may require deallocating or redeploying depending on configuration and API. Never perform this in production without a change window and recovery plan.

### Step 6: acceptance and operations

Verify:

1. Reservation provisioned successfully.
2. VMs are actually associated with the intended group.
3. Consuming VMs and unused slots match the plan.
4. VMs still pass health checks and applications function properly.
5. Monitoring, cost alerts, and capacity adjustment runbooks are in place.

## 9. Working in the Azure portal

Menu names may vary by portal version, but the basic flow is:

1. Sign in to the **Azure portal** and select the right tenant and subscription.
2. Search for **Capacity reservation groups** or **Capacity reservations** under Virtual Machines/Compute.
3. Create a **Capacity Reservation Group**; enter resource group, group name, and matching region.
4. Inside the group, add capacity reservations specifying **VM size**, **availability zone if applicable**, and **slot quantity**.
5. Review quota/limit information and confirm costs before creating.
6. Wait until the reservation shows provisioned/allocated state per the service UI.
7. Create a VM or update an eligible VM to select the appropriate **Capacity Reservation Group**.
8. View associated VMs and the used/unused capacity report inside the group.

For production environments, declare configurations via ARM/Bicep/Terraform to enable code review, drift detection, and repeatability across environments. Portal configuration is great for learning and visual inspection, not a substitute for change management.

### Conceptual declaration structure example

~~~yaml
# Pseudoconfiguration for architectural discussion — NOT a valid Azure manifest.
capacityReservationGroup:
  name: crg-sales-prod
  location: southeastasia
  reservations:
    - name: cr-zone1-d4s
      vmSize: Standard_D4s_v5
      zone: "1"
      count: 3
    - name: cr-zone2-d4s
      vmSize: Standard_D4s_v5
      zone: "2"
      count: 3

virtualMachine:
  name: vm-sales-01
  size: Standard_D4s_v5
  zone: "1"
  capacityReservationGroup: crg-sales-prod
~~~

This example highlights that **size**, **zone**, **count**, and **group association** must align. In real deployments, use Azure-supported ARM/Bicep/Terraform schemas; never copy pseudoconfiguration as an executable file.

## 10. Inspecting configuration with Azure CLI

Examples use Azure CLI to **read state** of groups, reservations, and VMs. Names below are hypothetical; before running, select the right subscription and ensure read permissions.

### Select subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{name:name,id:id}" --output table
~~~

### List groups and view details

~~~bash
az capacity reservation group list \
  --resource-group "rg-compute-capacity" \
  --output table

az capacity reservation group show \
  --resource-group "rg-compute-capacity" \
  --name "crg-sales-prod" \
  --output json
~~~

### List reservations inside a group

~~~bash
az capacity reservation list \
  --resource-group "rg-compute-capacity" \
  --capacity-reservation-group "crg-sales-prod" \
  --output json

az capacity reservation show \
  --resource-group "rg-compute-capacity" \
  --capacity-reservation-group "crg-sales-prod" \
  --name "cr-zone1-d4s" \
  --output json
~~~

In the output, observe **SKU**, zone, capacity, provisioning state, used/available capacity info, and associated VMs if returned by the API. Output field names can vary across Azure CLI/API versions and reservation types; never build monitoring strictly on an unverified field name.

### Verify VM size and zone

~~~bash
az vm show \
  --resource-group "rg-sales-prod" \
  --name "vm-sales-01" \
  --query "{name:name,size:hardwareProfile.vmSize,zones:zones,capacityReservation:capacityReservation}" \
  --output json
~~~

Confirm the VM references the right group and matches a reservation, not merely matching display names. If an existing VM is not associated, simply sitting in the right region/zone/size is insufficient to prove it consumes a slot.

### When should write commands be used?

Azure CLI provides capacity reservation management command groups to create, update, and delete resources where supported by your CLI version. Because these operations can incur costs or affect VMs, in labs you should **use read-only commands**; create/modify commands require owner review and checking help/schema on your exact CLI version:

~~~bash
az capacity reservation group -h
az capacity reservation -h
az vm update -h
~~~

Never run a command modifying a group or quantity in production before confirming its impact on associated VMs and Azure support conditions.

## 11. Capacity reservations with VM Scale Sets and batch processing

### VMSS: holding a baseline level

A system has a VM Scale Set with:

~~~text
VMSS: vmss-api-prod
Min instances: 3
Expected peak: 10
VM size: Standard_D4s_v5
Selected zones: per design
Capacity reservation: 3 slots for matching baseline
~~~

Meaning of this plan: the team wants to reduce capacity-shortage risk for **the three baseline instances**. Additional instances spun up at peak are not automatically guaranteed merely because the scale set references a reservation.

Verify the exact **orchestration mode**, supported VM types, zone distribution, update policy, and scaling behavior once reserved slots are full. To meet SLOs, you may need more slots or multiple configs/zones, weighed against idle capacity cost.

### Batch workloads

Suppose a reporting pipeline runs from 1 AM to 4 AM, needing 12 identically sized VMs to hit its SLA. If capacity is unavailable at that hour, job queues back up and results deliver late.

Two options:

- **No reservation:** saves slot-holding costs while idle, yet requires fallback plans for retry delays, changing VM sizes, or late processing.
- **Partial/full reservation:** pays to hold capacity across the reservation's active lifetime in exchange for lower risk of lacking matching slots.

If work tolerates interruption and reruns, Spot VMs can be evaluated for cost optimization; Spot is **not** used to guarantee capacity for hard deadlines. A sound batch architecture needs queues, checkpoints, retries, idempotency, and progress tracking beyond capacity reservation choices.

### Do not treat slot counts as an autoscaling schedule

Capacity reservations do not automatically decide:

- When to start a batch.
- When to scale instances up or down.
- How many tasks run concurrently.
- Whether checkpointing/rollback happens.
- Which jobs take higher priority.

Those decisions belong to schedulers, VMSS autoscale, Azure Batch, or your application orchestration layer.

## 12. Multi-zone redundancy and disaster recovery strategies

### Reserving across multiple zones

An application needing to stay available if one zone goes down can reserve capacity in two or more supported zones. However, having slots in zone 2 **does not automatically move** VMs or data from zone 1 to zone 2 during a zone 1 outage.

Combine with:

1. Distributing applications across zones.
2. Load balancers/Application Gateways or appropriate routing mechanisms.
3. Data replication and failover matching RPO/RTO.
4. Testing VMs/images/configurations in the standby zone.
5. Compute capacity and quotas for exact SKUs/zones.
6. Monitoring and failover procedures during incidents.

### Regional redundancy

Reservations are tied to their region. If a workload plans to recover in a secondary region, reserving capacity in the primary region **does not** guarantee the secondary region.

Example standby architecture:

~~~text
Primary: Southeast Asia
  Running VMs: 4
  Matching reservation: 4

Secondary: another Azure region
  Standby running VMs: 0
  Matching reservation: 4 (if allocated and supported)
  Data/images/network/runbooks: must be prepared separately
~~~

The secondary reservation can **incur charges even with zero VMs running**. It only solves VM capacity readiness; if backups cannot restore, network links are missing, or DNS lacks a plan, the application still misses RTO.

### Separating placement errors from application errors

Capacity Reservation does not fix:

- Corrupted guest OS, incompatible images, or failing VM extensions.
- Unrecoverable databases or inaccessible storage.
- Misconfigured NSGs, DNS, routes, or firewalls.
- Exhausted quotas/other resources outside reserved scope.
- Application logic bugs or broken deployment code.

Verify **multiple layers** instead of treating reservation status as proof that the entire system is ready.

## 13. Modifying reservation quantities and releasing capacity

Application demand changes over time. Operations need adjustment procedures:

### Increasing slots

1. Identify the size/zone needing expansion and the reason.
2. Check quotas/limits and budget.
3. Request the capacity increase via supported tooling.
4. Treat the new quantity as active only after Azure confirms successful allocation.
5. Re-verify VM/VMSS usage and costs.

**Increasing quantity is not guaranteed to succeed**, because Azure still needs matching additional capacity.

### Decreasing slots

1. Check how many VMs are currently **consuming the reservation**.
2. Calculate how many slots can be removed without violating constraints on running resources.
3. Check VMs scheduled to start/redeploy in the coming days.
4. Apply the change using an Azure-supported method with approval.
5. Verify usage and monitor cost changes after the billing cycle.

Do not assume quantity can drop **below currently consuming VMs**. Azure enforces protective constraints and association states that must be handled before shrinking or deleting.

### Deleting capacity reservations

Deleting reserved slots is a decision to **release capacity**. VMs or VMSS referencing/requiring the reservation may block deletion or require migration/disassociation in a valid sequence.

A safe procedure inspects associated VMs, plans replacements, confirms the app no longer needs guaranteed capacity, and deletes individual reservations per supported guidance before deleting an empty group. Never treat deleting a CRG as equivalent to deallocating VMs, and never run bulk delete commands as experiments.

## 14. Monitoring capacity and cost

In a subscription hosting many workloads, track capacity reservations as an independent operational resource.

### Metrics to monitor

| Metric | Interpretation and action |
|---|---|
| Reserved instance count | Total slots reserved by VM size and zone |
| Associated/consuming VM count | How many VMs actively consume reservations in the checked scope |
| Unused reserved slots | Paid slots with no VMs occupying them |
| Utilization rate | Used/reserved; prolonged low rates call for budget review |
| Allocation/association failures | Failures creating/expanding capacity or VMs mismatching the group |
| VMSS desired vs. actual instances | Detects scale-outs failing to meet demand |
| VM provisioning/start failures | Separates capacity shortages from quota/image/network errors |
| Cost by reservation/group/tag | Identifies workloads holding high idle capacity |
| Planned vs. actual peak demand | Validates whether baseline and buffer levels remain reasonable |

Example:

~~~text
CRG: crg-sales-prod
Zone 1 / Standard_D4s_v5
  Reserved: 4
  Used    : 3
  Unused  : 1
  Utilization: 75%

Zone 2 / Standard_D4s_v5
  Reserved: 3
  Used    : 3
  Unused  : 0
  Utilization: 100%
~~~

If utilization stays consistently low in zone 1, review replacement needs and peak hours before reducing slots. If utilization routinely hits 100% and workloads suffer capacity shortages when scaling, evaluate expanding capacity/zones rather than merely raising quota.

### Azure Monitor and Activity Log

Track group/reservation changes via **Azure Activity Log** and appropriate alert/audit mechanisms. Use capacity/association properties exposed by Azure via portal, Resource Manager, or APIs to compute usage; do not claim every illustrative metric above exists as a default Azure Monitor metric with that exact name.

Alert when:

- Reservation quantity changes or is deleted outside approved workflows.
- VMs/VMSS no longer reference the required CRG.
- A capacity create/increase failure occurs during critical deployment windows.
- Unused capacity stays high for multiple consecutive days.
- Reservation costs exceed approved budgets.

### Permission and change governance

Creating, modifying, or deleting capacity reservations are **Azure control-plane** operations. Apply Azure RBAC to restrict who can modify groups and reservations, alongside policies/approvals and Infrastructure as Code where appropriate.

Never store application secrets in tags or reservation names. Metadata such as cost center, application name, and owner must follow organizational standards without leaking sensitive info.

## 15. Common troubleshooting

| Symptom | Possible cause | What to check |
|---|---|---|
| Cannot create reservation | Region/zone/SKU lacks capacity, insufficient quota, or unsupported VM type | Inspect error code, subscription quota, region, and VM size; prepare fallback sizes/zones |
| CRG created successfully but shows no capacity | Only the group exists; no reservation created or reservation not yet allocated | Check child reservations and provisioning state |
| VM does not use reserved slot | VM not associated with CRG, or size/zone mismatch | Inspect VM model, group reference, zone, and SKU |
| VM creates successfully yet reservation stays unconsumed | VM allocated via another path or association inactive | Verify association state and reservation usage |
| Increasing slot count fails | No matching capacity left or quota exceeded | Check failure details; consider fallback plans |
| Scale set fails to reach desired instances | VMSS config/zone, quota, reservation, or allocation mismatch | Compare model, instance state, scale activity, and events |
| VM deallocated yet charges continue | Unused reservation continues billing | Check idle slot count and reservation billing |
| Cannot reduce/delete reservation | VMs actively consuming or referencing it; quantity constraints | Inspect associated VMs and modify/delete docs |
| VM fails despite free slots | Wrong size/zone, image/VM config/agent/network error, or invalid state | Compare VM requirements against reservation; read detailed error |
| Failover fails to activate after outage | Capacity exists, yet image, data, network, DNS, or runbook missing | Run end-to-end recovery tests |

### Diagnostic workflow

1. Confirm actual **subscription, resource group, region, availability zone, VM size** of the VM.
2. Read **provisioning state** and quantity of the reservation in the right group.
3. Verify the VM/VMSS is **associated** per supported configuration.
4. Check quotas, VM families, and remaining resource constraints.
5. Read the exact Azure allocation error instead of jumping to "out of quota" or "Azure out of capacity."
6. Check image/OS disk/VM Agent/network state if VM provisioning failed on another component.
7. Once fixed, verify the VM runs properly and slot usage changes as expected.

Do not expand capacity groups recklessly over budget because of an unclassified error. Equally, do not rush to cut quantity right before a planned scale-out or recovery drill.

## 16. Case study: order-processing system

An enterprise runs an API on Azure with these requirements:

- Primary region: **Southeast Asia**.
- VM size: **Standard_D4s_v5**, assumed supported for the intended setup.
- Two availability zones selected.
- Each zone needs **two VMs** off-peak, **three VMs** during business hours, and up to **five VMs** during peak season.
- Losing the ability to start three baseline VMs per zone violates the SLO.
- The business is willing to pay for idle capacity yet wants to avoid reserving all ten VMs year-round.

### Tasks

1. Determine the minimum reservation per zone.
2. Explain why a zone 1 reservation cannot substitute for zone 2 capacity.
3. Describe the CRG/reservations to create, including size, zone, and quantity.
4. State how to configure VMs/VMSS so they actually consume the reservation.
5. Propose handling peak season when two extra VMs per zone are needed while capacity reservation only holds three slots.
6. Assuming an illustrative compute rate of 0.30 USD/slot-hour, calculate the reserved capacity cost while running two VMs per zone.
7. List metrics to monitor to tell whether reservations are over- or under-provisioned.
8. State prerequisites to check before reducing quantity and post-incident recovery acceptance steps.

### Solution hints

To guarantee **three baseline VMs per zone**, consider:

~~~text
Standard_D4s_v5 / Southeast Asia
  Zone 1: reserve 3
  Zone 2: reserve 3
  Total : reserve 6

Off-peak: 2 VMs used per zone
  Used = 4
  Unused = 2
  Reservation footprint = 6 slots

Business hours: 3 VMs used per zone
  Used = 6
  Unused = 0

Peak: 5 VMs per zone
  Required = 10
  Reserved = 6
  Unreserved = 4 VMs not covered by the reservation guarantee
~~~

At an **assumed rate of 0.30 USD/slot-hour**, the compute cost for 6 slots is **1.80 USD/hour**: off-peak, four slots are used and two slots sit unused. This figure is not actual Azure billing; it excludes disks, networking, discounts, taxes, or other services.

For peak season, the team can request additional slots for the needed period **if Azure can allocate them**, or rely on standard on-demand scaling with business-approved fallbacks (alternate sizes/zones/throttling incoming jobs). No trick turns six slots into a guarantee for ten VMs.

## 17. Pre-production checklist

| Item | Required evidence |
|---|---|
| Objectives | Baseline, burst, RTO/RPO, or batch deadlines agreed |
| Scope | Subscription, resource group, region, and zones verified |
| SKU | VM size/family and VM features supported |
| Quota | vCPU/family quotas sufficient and allocation verified |
| Structure | CRG and reservations clearly defined by size/zone/quantity |
| Association | VMs/VMSS reference the right group and matching slots |
| Acceptance | Reservations provisioned cleanly; used/unused matches expectations |
| Scaling | Plan exists when demand exceeds reserved capacity |
| Security | RBAC, change approval, tagging, and auditing |
| Availability | Multi-zone/region, images, data, networking, failover tested |
| Financials | Estimated idle cost, quotes, budgets, and ancillary costs reviewed |
| Monitoring | Usage dashboards, cost tracking, capacity-change alerts active |
| Change mgmt | Procedures exist to increase/decrease/delete and handle running VMs |

## 18. Self-check questions

1. Why does spare quota not guarantee a VM will allocate immediately?
2. How does a Capacity Reservation Group differ from an individual Capacity Reservation?
3. Why can a reservation for one VM size not automatically serve any other size?
4. What is the difference between reserving capacity and buying Reserved VM Instances for a discount?
5. Does successfully creating a CRG prove VM slots are reserved?
6. Does a VM in the same region and resource group as a reservation consume slots automatically?
7. Why must reservations be tracked per availability zone?
8. Does stopping/deallocating VMs with ODCR eliminate all related compute charges?
9. A reservation holds four slots and two VMs are consuming them: how many idle slots remain?
10. A VMSS needs ten instances yet only six slots are reserved: what can and cannot be concluded?
11. When should ODCR be considered for scheduled batch jobs, and when might on-demand/Spot fit better?
12. Why does a capacity reservation in the primary region not guarantee DR capacity in a secondary region?
13. Before deleting a reservation, which VMs or associations must be checked?
14. What information distinguishes quota errors, insufficient capacity errors, and VM configuration errors?
15. Which metrics would you use to calculate and monitor idle reservation costs?

## References

- Microsoft Learn — *On-demand Capacity Reservation overview*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-overview
- Microsoft Learn — *Create capacity reservations*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-create
- Microsoft Learn — *Associate a VM with a capacity reservation*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-associate-vm
- Microsoft Learn — *Modify capacity reservations*: https://learn.microsoft.com/azure/virtual-machines/capacity-reservation-change
- Microsoft Learn — *Virtual Machines documentation*: https://learn.microsoft.com/azure/virtual-machines/
- Microsoft Learn — *Azure quotas*: https://learn.microsoft.com/azure/quotas/
- Microsoft Learn — *Azure Cost Management documentation*: https://learn.microsoft.com/azure/cost-management-billing/
